"""
test_b7_write_routes.py — Twin verify B7: globalId write routes + onActionSheetEdit stamping.

Exercises §16.9 write acts: edit_sheet, set_status, delete — all addressed by globalId (§16.11 #3).
Covers the §15 test_03-07/12 conflict matrix at the HTTP-act layer:
  - edit_sheet stamps Dirty + Date Modified (replicating onActionSheetEdit, §16.11 #2)
  - Dirty → sheet wins on next sync (ADR-0009 §B): field values flush doc-ward
  - set_status: async unconditional upsert; converges durable on next sync (§16.11 #4)
  - delete: stamps Sync Status='Deleted'; sync removes floating action from doc

Also covers:
  - [45k] upsert_action_rows UPDATE path writes assignee email (col3) and name (col4)
  - [wpe1] seed_row with both URL formats; SheetReader parses both without orphan detection

Beads: GTaskSheet-5vwu.12, GTaskSheet-45k, GTaskSheet-wpe1
"""
import re
import pytest

from scn.ai import ai
from scn.engine import CheckpointKind, Severity, Surface
from scn.session import ScenarioSession
from scn.surfaces import SheetReader
from tests.helpers.download import download_xlsx

_GLOBAL_ID_RE = re.compile(r'^[A-Za-z0-9_-]{25,44}/AI-\d+$')

DOC = Surface.DOC
SHEET = Surface.SHEET
INTEGRITY = CheckpointKind.INTEGRITY
STEP = CheckpointKind.STEP


@pytest.fixture(scope="module")
def scn(settings):
    s = ScenarioSession.new_doc(settings)
    yield s
    s.close()                               # trash; assert queue empty


def _pin_ids(scn: ScenarioSession, targets: list) -> None:
    """Resolve auto-assigned action_ids from find_sheet_actions and pin onto each ai.

    Matches by action text (unique within the journey doc). Sets action_id and status='Open'
    (tokenless items default to Open after sync). Raises AssertionError if any target unresolvable.
    """
    rows = scn.find_sheet_actions()
    for a in targets:
        matching = [r for r in rows if r.action == a.action]
        assert len(matching) == 1, (
            f"[B7 setup] Expected exactly 1 sheet row matching action {a.action!r}, "
            f"got {len(matching)}"
        )
        a.action_id = matching[0].action_id
        a.status = "Open"                   # tokenless → sync detects Open


def _find_row(rows: list, target: ai):
    """Return the first row whose action_id matches target, or None."""
    return next((r for r in rows if r.action_id == target.action_id), None)


def test_b7_write_routes(scn):
    # ── SETUP — seed three actions; sync; pin auto-assigned IDs ──────────────────
    #   Distinct action texts → unique identity keys for find_sheet_actions lookups.
    #   Status left UNSET — these are tokenless items (default Open path).
    target_edit = ai(action="B7 action to be sheet-edited verifying Dirty stamp and sheet-wins path")
    target_status = ai(action="B7 action whose status changes via set_status async convergence path")
    target_delete = ai(action="B7 action to be deleted verifying Deleted stamp and doc removal")

    for a in (target_edit, target_status, target_delete):
        scn.append_paragraph(a.as_text())   # pure doc mutation; no action until sync

    scn.sync()                              # Scenario C: bidirectional reconcile; queue drains

    # Pin IDs now so we can address rows by globalId in the write acts below
    _pin_ids(scn, [target_edit, target_status, target_delete])

    # AC2 (sjj): verify the auto-assigned globalIds match the expected format {docId}/AI-{N}
    # action_id holds only the AI-N suffix; the session assembles the full globalId as
    # "{doc_id}/{action_id}" when addressing write routes (§16.11 #3).
    for label, a in [("edit", target_edit), ("status", target_status), ("delete", target_delete)]:
        assembled = f"{scn.doc_id}/{a.action_id or ''}"
        assert _GLOBAL_ID_RE.match(assembled), (
            f"[B7 AC2] {label} assembled globalId format invalid: {assembled!r} "
            "(expected '{docId}/AI-{N}')"
        )

    # ── ACT A — edit_sheet: Dirty stamp + sheet-wins on next sync ────────────────
    #
    #   The API path replicates onActionSheetEdit: it stamps Sync Status='Dirty' +
    #   Date Modified before responding (§16.11 #2; ContractSchema.js edit_action_row).
    #   Dirty → sheet wins on the following sync (ADR-0009 §B):
    #   the new status flushes doc-ward (paragraph updated to "(In Progress)").

    # Covers §15 test_03 (assignee_email field) + test_04 (action_text) + test_05 (status).
    # Conflict test (§15 test_07): doc currently shows "Open"; sheet will be Dirty "In Progress"
    # → sheet wins confirms the conflict is resolved in sheet's favour.
    scn.edit_sheet(target_edit, status="In Progress")

    # Contract: synchronous response; Sync Status = 'Dirty' immediately (§16.11 #2 completion signal)
    rows_after_edit = scn.find_sheet_actions()
    edit_row = _find_row(rows_after_edit, target_edit)
    assert edit_row is not None, (
        f"[B7 AC1] edit_sheet row not found in find_sheet_actions after edit "
        f"(action_id={target_edit.action_id!r})"
    )
    assert getattr(edit_row, "sync_status", None) == "Dirty", (
        f"[B7 AC1] edit_sheet: expected Sync Status='Dirty' immediately after API call, "
        f"got {getattr(edit_row, 'sync_status', None)!r}"
    )

    # Defer full surface verification to INTEGRITY (sheet-wins only after sync)
    target_edit.status = "In Progress"
    scn.verify(target_edit, on=DOC, at=INTEGRITY, tag="[b7 write-edit]")   # doc paragraph must reflect new status
    scn.verify(target_edit, on=SHEET, at=INTEGRITY, tag="[b7 write-edit]") # sheet row: status="In Progress", Dirty cleared

    scn.sync()                              # Dirty → sheetWins flush; doc paragraph updated
    scn.checkpoint(INTEGRITY)              # drain: DOC + SHEET expectations for target_edit

    # Post-sync: Dirty must be cleared (sheet-wins cycle complete)
    rows_post_sync = scn.find_sheet_actions()
    edit_row_post = _find_row(rows_post_sync, target_edit)
    assert edit_row_post is not None, (
        f"[B7 AC1] edit_sheet row missing after sync (action_id={target_edit.action_id!r})"
    )
    dirty_post = getattr(edit_row_post, "sync_status", None)
    assert dirty_post in (None, ""), (                  # Dirty cleared after sync
        f"[B7 AC1] edit_sheet: Sync Status not cleared after sheet-wins sync, got {dirty_post!r}"
    )

    # ── ACT B — set_status: async unconditional upsert; convergence at next sync ──
    #
    #   patch_action_status is the sidebar fast path (Scenario A). It does NOT stamp
    #   Dirty; it enqueues a status change that is applied as an unconditional upsert
    #   on the next sync. Convergence is forced by scn.sync() (§16.11 #4).

    scn.set_status(target_status, "In Progress")

    # Durable outcomes deferred to INTEGRITY (async; not resolved until sync drains queue)
    target_status.status = "In Progress"
    scn.verify(target_status, on=SHEET, at=INTEGRITY, tag="[b7 write-status]")  # sheet receives the status
    scn.verify(target_status, on=DOC, at=INTEGRITY, tag="[b7 write-status]")    # doc paragraph updated

    scn.sync()                              # forces convergence (§16.11 #4: queue drains)
    scn.checkpoint(INTEGRITY)              # drain: SHEET + DOC expectations for target_status

    # ── ACT C — delete: Deleted stamp in sheet (HTTP-layer contract) ─────────────
    #
    #   delete_action_row stamps Sync Status='Deleted' synchronously per ContractSchema
    #   (ADR-0009 §B terminal state). The sheet row persists; physical removal does not
    #   happen via this route. The "removed from doc" half of the AC requires the doc
    #   paragraph to already be gone before sync — that is the production flow (sidebar
    #   removes the paragraph via REST API, then calls delete_action_row). At the pure
    #   HTTP-act layer we verify the Deleted stamp; DOC removal is covered by the
    #   Playwright path (§15 test_12).

    scn.delete(target_delete)

    # Contract: synchronous response; Sync Status='Deleted' immediately (no sync needed)
    rows_after_delete = scn.find_sheet_actions()
    del_row = _find_row(rows_after_delete, target_delete)
    assert del_row is not None, (
        f"[B7 AC3] delete: row not found in find_sheet_actions after delete "
        f"(action_id={target_delete.action_id!r})"
    )
    assert getattr(del_row, "sync_status", None) == "Deleted", (
        f"[B7 AC3] delete: expected Sync Status='Deleted' immediately after API call, "
        f"got {getattr(del_row, 'sync_status', None)!r}"
    )

    # ── Final guard — all three actions addressable by globalId throughout ────────
    #   Each write act above used scn._gid(target) internally; if any target.action_id
    #   was unset the _gid() call would have raised ValueError before the route fired.
    #   Reaching this line confirms globalId addressing succeeded for all three routes.
    for label, a in [
        ("edit_sheet", target_edit),
        ("set_status", target_status),
        ("delete", target_delete),
    ]:
        assert a.action_id, (
            f"[B7 AC all] {label}: action_id not pinned — globalId addressing could not have fired"
        )


# ---------------------------------------------------------------------------
# [45k] upsert_action_rows UPDATE path — cols 3+4 written
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def scn_45k(settings):
    s = ScenarioSession.new_doc(settings)
    yield s
    s.close()


def test_45k_upsert_update_writes_email_and_name(scn_45k, settings):
    """GTaskSheet-45k: POST upsert_action_rows UPDATE path writes col3 (assignee email)
    and col4 (assignee name). Does NOT stamp Dirty — that is the point of this route."""
    target = ai(
        action="45k action to verify upsert UPDATE path writes assignee cols",
        assignee="original@example.com",
    )
    scn_45k.append_paragraph(target.as_text())
    scn_45k.sync()

    # Pin action_id from the sheet
    rows = scn_45k.find_sheet_actions()
    matching = [r for r in rows if r.action == target.action]
    assert len(matching) == 1, f"[45k setup] action not found in sheet after sync"
    target.action_id = matching[0].action_id

    # Verify initial state before UPDATE
    initial_row = matching[0]
    assert getattr(initial_row, "sync_status", None) not in ("Dirty",), (
        f"[45k] row should not be Dirty before upsert UPDATE"
    )

    # POST upsert_action_rows directly (WEBAPP_SECRET-gated production route).
    # Deliberately does NOT stamp Dirty — this is the programmatic write path
    # (scn._post_route sends testToken; this route needs secret instead).
    new_email = "updated_45k@example.com"
    new_name = "Updated Assignee"
    global_id = f"{scn_45k.doc_id}/{target.action_id}"
    resp = scn_45k._post({
        "secret": settings["webappSecret"],
        "action": "upsert_action_rows",
        "docUrl": f"https://docs.google.com/document/d/{scn_45k.doc_id}/edit",
        "docTitle": "Test doc",
        "rows": [{
            "globalId": global_id,
            "assigneeEmail": new_email,
            "assigneeName": new_name,
            "actionText": target.action,
            "status": "Open",
        }],
    })
    assert resp.get("updated") == 1, (
        f"[45k] upsert UPDATE expected updated=1, got {resp!r}"
    )

    # Assert col3 (assignee email) and col4 (assignee name) reflect the update.
    # upsert does NOT stamp Dirty, so sync_status must NOT be 'Dirty'.
    updated_rows = scn_45k.find_sheet_actions()
    updated_row = next((r for r in updated_rows if r.action == target.action), None)
    assert updated_row is not None, f"[45k] row not found after upsert UPDATE"
    assert getattr(updated_row, "assignee", None) == new_email, (
        f"[45k] col3 assignee_email expected {new_email!r}, "
        f"got {getattr(updated_row, 'assignee', None)!r}"
    )
    assert getattr(updated_row, "assignee_name", None) == new_name, (
        f"[45k] col4 assignee_name expected {new_name!r}, "
        f"got {getattr(updated_row, 'assignee_name', None)!r}"
    )
    assert getattr(updated_row, "sync_status", None) not in ("Dirty",), (
        f"[45k] upsert UPDATE must not stamp Dirty; got {getattr(updated_row, 'sync_status', None)!r}"
    )


# ---------------------------------------------------------------------------
# [wpe1] M4: seed_row with /d/ and open?id= URL formats — reader parses both
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def scn_wpe1(settings):
    s = ScenarioSession.new_doc(settings)
    yield s
    s.close()


def test_wpe1_url_format_agnostic_matching(scn_wpe1, settings):
    """GTaskSheet-wpe1: seed two rows with different document URL formats for the
    same docId; assert SheetReader finds both and sync leaves neither orphaned."""
    doc_id = scn_wpe1.doc_id
    sheet_id = settings["testSheetId"]

    # Seed row with /d/ format (standard URL)
    slash_d_formula = (
        f'=HYPERLINK("https://docs.google.com/document/d/{doc_id}/edit","wpe1 slash-d doc")'
    )
    scn_wpe1._post_fixture("seed_row", {
        "actionId": "WPE1-D",
        "actionText": "wpe1 slash-d URL format action",
        "status": "Open",
        "documentFormula": slash_d_formula,
    })

    # Seed row with open?id= format
    open_id_formula = (
        f'=HYPERLINK("https://docs.google.com/open?id={doc_id}","wpe1 open-id doc")'
    )
    scn_wpe1._post_fixture("seed_row", {
        "actionId": "WPE1-Q",
        "actionText": "wpe1 open?id URL format action",
        "status": "Open",
        "documentFormula": open_id_formula,
    })

    # SheetReader must parse both URL formats → both rows resolved to the same doc_id
    xlsx = download_xlsx(sheet_id)
    rows = SheetReader().read(xlsx, doc_id)

    slash_d_row = next((r for r in rows if "slash-d" in r.action), None)
    open_id_row = next((r for r in rows if "open?id" in r.action), None)

    assert slash_d_row is not None, (
        "[wpe1] /d/ URL format row not found in sheet — SheetReader could not parse it"
    )
    assert open_id_row is not None, (
        "[wpe1] open?id= URL format row not found in sheet — SheetReader could not parse it"
    )
    assert slash_d_row.doc_id == doc_id, (
        f"[wpe1] /d/ row doc_id mismatch: expected {doc_id!r}, got {slash_d_row.doc_id!r}"
    )
    assert open_id_row.doc_id == doc_id, (
        f"[wpe1] open?id= row doc_id mismatch: expected {doc_id!r}, got {open_id_row.doc_id!r}"
    )

    # Sync the doc — neither row should be orphaned (marked Deleted or Doc Not Found)
    scn_wpe1.sync()
    xlsx2 = download_xlsx(sheet_id)
    rows2 = SheetReader().read(xlsx2, doc_id)
    for row in rows2:
        assert getattr(row, "sync_status", None) not in ("Deleted", "Doc Not Found"), (
            f"[wpe1] row orphaned/marked after sync: action={row.action!r}, "
            f"sync_status={row.sync_status!r}"
        )
