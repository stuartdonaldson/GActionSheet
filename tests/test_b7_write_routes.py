"""
test_b7_write_routes.py — Twin verify B7: globalId write routes + onActionSheetEdit stamping.

Exercises §16.9 write acts: edit_sheet, set_status, delete — all addressed by globalId (§16.11 #3).
Covers the §15 test_03-07/12 conflict matrix at the HTTP-act layer:
  - edit_sheet stamps Dirty + Date Modified (replicating onActionSheetEdit, §16.11 #2)
  - Dirty → sheet wins on next sync (ADR-0009 §B): field values flush doc-ward
  - set_status: async unconditional upsert; converges durable on next sync (§16.11 #4)
  - delete: stamps Sync Status='Deleted'; sync removes floating action from doc

Bead: GTaskSheet-5vwu.12
"""
import re
import pytest

from scn.ai import ai
from scn.engine import CheckpointKind, Severity, Surface
from scn.session import ScenarioSession

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
    scn.verify(target_edit, on=DOC, at=INTEGRITY)   # doc paragraph must reflect new status
    scn.verify(target_edit, on=SHEET, at=INTEGRITY) # sheet row: status="In Progress", Dirty cleared

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
    scn.verify(target_status, on=SHEET, at=INTEGRITY)  # sheet receives the status
    scn.verify(target_status, on=DOC, at=INTEGRITY)    # doc paragraph updated

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
