"""
test_sync_all.py — GTaskSheet-r3d/grxl/5u2v/nv6g/cduk

One scenario: seed a mixed ActionSheet (invalid-doc, trashed-doc, unmodified-valid,
modified-valid rows), run syncAll ONCE (Sweep 1), drain per-condition expectations,
then run syncAll a SECOND time (Sweep 2) to verify Doc Not Found rows are archived.

All four beads map to expectations on the same two sweeps (§6 permutation batching).

Archive eligibility (ArchiveManager):
  - Status='Closed': Date Modified > 30 days old
  - sync_status='Doc Not Found': Date Modified > 24 hours old
    (_handleMarkDocNotFound stamps modified_date at detection time, so the timer
    starts when the doc is first detected missing — not when the action was last edited)

The invalid-doc row is backdated 2 days after Sweep 1 stamps its modified_date,
making it immediately eligible for archiving on Sweep 2.  The trashed-doc row is
stamped now during Sweep 1 and is not backdated, so it remains in Actions under
the 24-hour grace period.
"""
import secrets
import pytest

from scn.engine import CheckpointKind, Surface
from scn.session import ScenarioSession
from scn.surfaces import SheetReader
from tests.helpers.download import download_xlsx

SHEET = Surface.SHEET
STEP = CheckpointKind.STEP


def _sheet_rows_for(settings: dict, doc_id: str) -> list:
    """Download ActionSheet and return rows scoped to doc_id (Actions tab)."""
    xlsx = download_xlsx(settings["testSheetId"])
    return SheetReader().read(xlsx, doc_id)


def _archive_rows_for(settings: dict, doc_id: str) -> list:
    """Download ActionSheet and return rows scoped to doc_id (Archive tab)."""
    xlsx = download_xlsx(settings["testSheetId"])
    return SheetReader().read(xlsx, doc_id, tab_name="Archive")


@pytest.fixture
def sync_ctx(settings, request):
    """Set up the mixed ActionSheet; yield context; teardown trashes all journey docs.

    Setup order:
      1. scn_mod: create doc, append action, sync, then append more (modified-valid)
      2. scn_unmod: create doc, append action, sync, no further mutation (unmodified-valid)
      3. scn_trash: create doc, append action, sync, then trash the doc (trashed)
      4. Seed one invalid-doc row via seed_row fixture

    The invalid docId is unique per session (secrets.token_urlsafe) to prevent
    accumulated rows from previous test runs bleeding into this session's assertions.
    """
    # Unique-per-session fake docId (44 URL-safe chars, will never resolve in Drive).
    invalid_doc_id = secrets.token_urlsafe(33)[:44]

    scn_mod = ScenarioSession.new_doc(settings, request=request)
    scn_unmod = ScenarioSession.new_doc(settings)
    scn_trash = ScenarioSession.new_doc(settings)

    # modified-valid: sync once to create sheet row, then add more content
    scn_mod.append_paragraph("AI-1: syncall modified valid action")
    scn_mod.sync()
    scn_mod.append_paragraph("AI-2: additional action added after sync — marks doc modified")

    # unmodified-valid: sync once, no further mutation
    scn_unmod.append_paragraph("AI-1: syncall unmodified valid action")
    scn_unmod.sync()

    # to-be-trashed: sync once to create sheet row, then trash the doc
    scn_trash.append_paragraph("AI-1: syncall trashed doc action")
    scn_trash.sync()
    trashed_id = scn_trash.doc_id
    scn_trash._post_fixture("trash_doc")   # trashes scn_trash.doc_id (= testDocId for this call)

    # invalid-doc: seed two raw rows sharing the same unreachable docId, so
    # Sweep 1's Doc Not Found mark and Sweep 2's archive sweep can be checked
    # for GTaskSheet-4tnr's per-docId batching (both rows converge/evict
    # together, not independently).
    # modified_date is left as now — _handleMarkDocNotFound will overwrite it anyway.
    # The globalIds are set explicitly so backdate_action_row can address these
    # rows after Sweep 1 stamps them with a fresh modified_date.
    invalid_formula = (
        f'=HYPERLINK("https://docs.google.com/document/d/{invalid_doc_id}/edit","Invalid Doc")'
    )
    invalid_global_id = f"{invalid_doc_id}/AI-1"
    invalid_global_id_2 = f"{invalid_doc_id}/AI-2"
    scn_mod._post_fixture("seed_row", {
        "globalId": invalid_global_id,
        "actionId": "INVALID-1",
        "actionText": "syncall invalid doc seeded action",
        "status": "Open",
        "documentFormula": invalid_formula,
    })
    scn_mod._post_fixture("seed_row", {
        "globalId": invalid_global_id_2,
        "actionId": "INVALID-2",
        "actionText": "syncall invalid doc seeded action (sibling row, same docId)",
        "status": "Open",
        "documentFormula": invalid_formula,
    })

    yield {
        "settings": settings,
        "scn_mod": scn_mod,
        "scn_unmod": scn_unmod,
        "modified_id": scn_mod.doc_id,
        "unmodified_id": scn_unmod.doc_id,
        "trashed_id": trashed_id,
        "invalid_id": invalid_doc_id,
        "invalid_global_id": invalid_global_id,
        "invalid_global_id_2": invalid_global_id_2,
    }

    # Teardown: end journey sessions (trashes the docs)
    for scn in (scn_mod, scn_unmod):
        try:
            scn._post_route("end_journey_session", {"docId": scn.doc_id})
        except Exception:
            pass
    # scn_trash doc is already trashed; engine has no enqueued expectations, so skip close()


def test_sync_all(sync_ctx):
    settings = sync_ctx["settings"]
    scn_mod = sync_ctx["scn_mod"]
    scn_unmod = sync_ctx["scn_unmod"]
    modified_id = sync_ctx["modified_id"]
    unmodified_id = sync_ctx["unmodified_id"]
    trashed_id = sync_ctx["trashed_id"]
    invalid_id = sync_ctx["invalid_id"]
    invalid_global_id = sync_ctx["invalid_global_id"]
    invalid_global_id_2 = sync_ctx["invalid_global_id_2"]

    # ── Pre-sweep baseline ───────────────────────────────────────────────────
    # unmodified doc: 1 row in Actions, no sync_status
    pre_unmod = _sheet_rows_for(settings, unmodified_id)
    assert len(pre_unmod) >= 1, "[5u2v pre] expected ≥1 row for unmodified doc before syncAll"

    # invalid doc row exists in Actions before sweep
    pre_invalid = _sheet_rows_for(settings, invalid_id)
    assert len(pre_invalid) >= 1, "[r3d pre] seeded invalid-doc row not found before syncAll"

    # ── Sweep 1 ──────────────────────────────────────────────────────────────
    # sync_all fixture calls syncAll() on the production sheet — all rows are processed.
    # Use scn_mod._post_fixture (testDocId = scn_mod.doc_id) but sync_all ignores testDocId.
    scn_mod._post_fixture("sync_all")

    # [r3d] invalid doc → Sync Status = 'Doc Not Found'
    invalid_s1 = _sheet_rows_for(settings, invalid_id)
    assert len(invalid_s1) >= 1, (
        "[r3d] invalid-doc row disappeared from Actions after Sweep 1 (expected Doc Not Found)"
    )
    for row in invalid_s1:
        assert getattr(row, "sync_status", None) == "Doc Not Found", (
            f"[r3d] invalid-doc row: expected 'Doc Not Found', got {row.sync_status!r}"
        )

    # entry_point: syncAll (30-min time-based sweep, ID-map P1-1) — durable-state
    # assertion at the sweep's own call-site (GTaskSheet-rz4k.1). Re-checks the
    # [r3d] invalid-doc condition above via the tagged scn mechanism.
    def _invalid_doc_not_found() -> str | None:
        rows = _sheet_rows_for(settings, invalid_id)
        if not rows:
            return "[r3d] invalid-doc row disappeared from Actions after Sweep 1"
        for row in rows:
            if getattr(row, "sync_status", None) != "Doc Not Found":
                return (
                    f"[r3d] invalid-doc row: expected 'Doc Not Found', got {row.sync_status!r}"
                )
        return None

    scn_mod.expect_callable(
        _invalid_doc_not_found, on=SHEET, tag="[r3d syncAll sweep1]", entry_point="syncAll",
    )
    scn_mod.checkpoint(STEP)

    # [grxl] trashed doc → Sync Status = 'Doc Not Found'
    # Both paths (inaccessible + trashed) produce the same durable status.
    # The trashed-path is disambiguated by err='Document is in Trash' in GAS logs,
    # not by a distinct sync_status — so we assert the durable outcome only.
    trashed_s1 = _sheet_rows_for(settings, trashed_id)
    assert len(trashed_s1) >= 1, (
        "[grxl] trashed-doc row disappeared from Actions after Sweep 1 (expected Doc Not Found)"
    )
    for row in trashed_s1:
        assert getattr(row, "sync_status", None) == "Doc Not Found", (
            f"[grxl] trashed-doc row: expected 'Doc Not Found', got {row.sync_status!r}"
        )

    # entry_point: mark_doc_not_found (GTaskSheet-rz4k.2) -- syncDocument's catch
    # path POSTs this route when the doc is inaccessible/trashed; tag the [grxl]
    # durable-stamp condition above (distinct from the [r3d]/syncAll tag, since
    # both invalid- and trashed-doc rows are stamped via the same route).
    def _trashed_doc_not_found() -> str | None:
        rows = _sheet_rows_for(settings, trashed_id)
        if not rows:
            return "[grxl] trashed-doc row disappeared from Actions after Sweep 1"
        for row in rows:
            if getattr(row, "sync_status", None) != "Doc Not Found":
                return f"[grxl] trashed-doc row: expected 'Doc Not Found', got {row.sync_status!r}"
        return None

    scn_mod.expect_callable(
        _trashed_doc_not_found, on=SHEET, tag="[grxl mark_doc_not_found]", entry_point="mark_doc_not_found",
    )
    scn_mod.checkpoint(STEP)

    # [zc21] DocData mirrors 'Doc Not Found' and keeps Team Id consistent with
    # the document's actual teamScope appProperty.
    trashed_docdata = _docdata(scn_mod, trashed_id)
    assert trashed_docdata is not None, (
        "[zc21] trashed-doc DocData row missing after Sweep 1"
    )
    assert trashed_docdata.get("syncStatus") == "Doc Not Found", (
        f"[zc21] trashed-doc DocData.sync_status: expected 'Doc Not Found', "
        f"got {trashed_docdata.get('syncStatus')!r}"
    )
    trashed_team_scope = (scn_mod._post_fixture("get_team_scope", {"docId": trashed_id})
                           .get("data") or {}).get("teamScope", "")
    assert trashed_docdata.get("teamId", "") == trashed_team_scope, (
        f"[zc21] trashed-doc DocData.team_id ({trashed_docdata.get('teamId')!r}) "
        f"!= teamScope appProperty ({trashed_team_scope!r})"
    )

    # [zc21] invalid doc never had a DocData row before sync_all — one is
    # created on first 'Doc Not Found' mark, with an empty Team Id.
    invalid_docdata = _docdata(scn_mod, invalid_id)
    assert invalid_docdata is not None, (
        "[zc21] invalid-doc DocData row not created after Sweep 1"
    )
    assert invalid_docdata.get("syncStatus") == "Doc Not Found", (
        f"[zc21] invalid-doc DocData.sync_status: expected 'Doc Not Found', "
        f"got {invalid_docdata.get('syncStatus')!r}"
    )
    assert invalid_docdata.get("teamId", "") == "", (
        f"[zc21] invalid-doc DocData.team_id: expected '', got {invalid_docdata.get('teamId')!r}"
    )

    # [5u2v] unmodified valid doc → row count unchanged; NOT marked Doc Not Found
    post_unmod_s1 = _sheet_rows_for(settings, unmodified_id)
    for row in post_unmod_s1:
        assert getattr(row, "sync_status", None) != "Doc Not Found", (
            f"[5u2v] unmodified-valid doc incorrectly marked Doc Not Found: {row.sync_status!r}"
        )

    # modified valid doc → NOT marked Doc Not Found (may have new rows from AI-2)
    mod_s1 = _sheet_rows_for(settings, modified_id)
    for row in mod_s1:
        assert getattr(row, "sync_status", None) != "Doc Not Found", (
            f"[5u2v] modified-valid doc marked Doc Not Found unexpectedly: {row.sync_status!r}"
        )

    # ── Backdate invalid-doc for Sweep 2 ─────────────────────────────────────
    # Sweep 1 stamped modified_date = now on both invalid-doc rows (same docId).
    # The 24-hour Doc Not Found threshold means they won't archive until that
    # date is > 24h ago. Backdate both rows to 2 days ago so Sweep 2 archives
    # them together — GTaskSheet-4tnr's per-docId batching means a docId's
    # sibling rows are not evicted independently of each other.
    scn_mod._post_fixture("backdate_action_row", {
        "globalId": invalid_global_id,
        "daysAgo": 2,
    })
    scn_mod._post_fixture("backdate_action_row", {
        "globalId": invalid_global_id_2,
        "daysAgo": 2,
    })

    # ── Sweep 2 (nv6g) ───────────────────────────────────────────────────────
    # Second sweep: Doc Not Found rows from Sweep 1 are now in alreadyDocNotFound set
    # → ArchiveManager.archive() moves them from Actions to Archive sheet.
    scn_mod._post_fixture("sync_all")

    # [nv6g] both invalid-doc rows → archived together (backdated 2 days, > 24h threshold)
    invalid_archived = _archive_rows_for(settings, invalid_id)
    assert len(invalid_archived) == 2, (
        f"[nv6g] expected both invalid-doc rows archived together as one docId batch, "
        f"got {len(invalid_archived)}"
    )
    invalid_actions_s2 = _sheet_rows_for(settings, invalid_id)
    assert len(invalid_actions_s2) == 0, (
        f"[nv6g] invalid-doc row still in Actions after archive sweep "
        f"(expected 0, got {len(invalid_actions_s2)})"
    )

    # [GTaskSheet-4tnr] once every Actions row for a Doc Not Found docId has
    # aged out and archived, the DocData row for that docId is evicted too —
    # DocData must not keep referencing a docId whose Actions rows are gone.
    invalid_docdata_s2 = _docdata(scn_mod, invalid_id)
    assert invalid_docdata_s2 is None, (
        f"[GTaskSheet-4tnr] invalid-doc DocData row should be evicted once its "
        f"Doc Not Found Actions rows archive past the 24h threshold, got {invalid_docdata_s2!r}"
    )

    # [GTaskSheet-4tnr] trashed-doc is still within its 24h grace period (not
    # backdated) — its DocData row must survive this sweep.
    trashed_docdata_s2 = _docdata(scn_mod, trashed_id)
    assert trashed_docdata_s2 is not None, (
        "[GTaskSheet-4tnr] trashed-doc DocData row evicted prematurely, "
        "before its 24h grace period elapsed"
    )

    # [nv6g §grace] trashed-doc row → still in Actions (modified_date stamped now by Sweep 1,
    # < 24 hours old; not backdated, so the 24-hour grace period applies).
    trashed_actions_s2 = _sheet_rows_for(settings, trashed_id)
    assert len(trashed_actions_s2) >= 1, (
        "[nv6g §grace] trashed-doc row should still be in Actions under 24-hour grace period"
    )
    for row in trashed_actions_s2:
        assert getattr(row, "sync_status", None) == "Doc Not Found", (
            f"[nv6g §grace] trashed-doc row should remain 'Doc Not Found' in Actions, "
            f"got {row.sync_status!r}"
        )

    # [nv6g §7] Valid doc rows unaffected by either sweep
    mod_s2 = _sheet_rows_for(settings, modified_id)
    for row in mod_s2:
        assert getattr(row, "sync_status", None) != "Doc Not Found", (
            f"[nv6g §7] modified-valid doc incorrectly archived or marked: {row.sync_status!r}"
        )
    unmod_s2 = _sheet_rows_for(settings, unmodified_id)
    for row in unmod_s2:
        assert getattr(row, "sync_status", None) != "Doc Not Found", (
            f"[nv6g §7] unmodified-valid doc incorrectly archived or marked: {row.sync_status!r}"
        )


# ---------------------------------------------------------------------------
# Integrity pass — GTaskSheet-cduk
# ---------------------------------------------------------------------------

def _docdata(scn, file_id: str | None = None) -> dict | None:
    """Read the DocData row for scn's doc (or an explicit file_id) as a plain dict."""
    extra = {"fileId": file_id} if file_id else {}
    resp = scn._post_fixture("get_docdata_row", extra)
    return (resp.get("data") or {}).get("row")


def test_docdata_integrity_pass(settings, gas_log_dir, request):
    """GTaskSheet-cduk: syncAll() integrity pass reconciles stale DocData.

    TST-AC1: stale action_count / resolved_count corrected for a doc skipped by main loop.
    TST-AC2: stale doc_name corrected from the HYPERLINK formula title.
    TST-AC3: DocData rows with no corresponding Actions rows are not modified.
    TST-AC4: sync.integrity.complete log event emitted with updated count.
    """
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        # Setup: 2 open actions → sync → DocData has actionCount=2, resolvedCount=0
        scn.append_paragraph("AI-1: cduk integrity pass action one")
        scn.append_paragraph("AI-2: cduk integrity pass action two")
        scn.sync()

        initial = _docdata(scn)
        assert initial is not None, "[cduk] DocData row not created by initial sync"
        assert initial.get("actionCount") == 2, (
            f"[cduk] initial actionCount: expected 2, got {initial.get('actionCount')!r}"
        )
        initial_name = initial.get("docName") or ""

        # Corrupt DocData: wrong counts + wrong doc_name
        scn._post_fixture("set_docdata_row", {
            "actionCount": 99, "resolvedCount": 7, "docName": "Stale Name cduk",
        })
        stale = _docdata(scn)
        assert stale is not None and stale.get("actionCount") == 99, (
            "[cduk] set_docdata_row did not write stale actionCount=99"
        )

        # AC3: seed an orphan DocData row (fake fileId, no Actions rows)
        orphan_id = secrets.token_urlsafe(33)[:44]
        scn._post_fixture("set_docdata_row", {
            "fileId": orphan_id, "actionCount": 55, "resolvedCount": 3, "docName": "Orphan",
        })

        # Run syncAll — real doc is unmodified since its last sync so it should be
        # skipped by the main loop; the integrity pass then corrects DocData for it.
        if gas_log_dir:
            from tests.helpers.gas_log import clear_logs
            fence = clear_logs(gas_log_dir)
        else:
            fence = 0.0

        scn._post_fixture("sync_all")

        # AC1: counts corrected
        after = _docdata(scn)
        assert after is not None, "[cduk AC1] DocData row missing after syncAll"
        assert after.get("actionCount") == 2, (
            f"[cduk AC1] actionCount: expected 2, got {after.get('actionCount')!r}"
        )
        assert after.get("resolvedCount") == 0, (
            f"[cduk AC1] resolvedCount: expected 0, got {after.get('resolvedCount')!r}"
        )

        # AC2: doc_name corrected from HYPERLINK formula title
        assert after.get("docName") != "Stale Name cduk", (
            "[cduk AC2] docName still shows stale value after integrity pass"
        )
        if initial_name:
            assert after.get("docName") == initial_name, (
                f"[cduk AC2] docName: expected {initial_name!r}, got {after.get('docName')!r}"
            )

        # AC3: orphan DocData row untouched (no Actions rows → not in perDocCounts)
        orphan_after = _docdata(scn, file_id=orphan_id)
        assert orphan_after is not None, "[cduk AC3] orphan DocData row was deleted"
        assert orphan_after.get("actionCount") == 55, (
            f"[cduk AC3] orphan actionCount modified: expected 55, got {orphan_after.get('actionCount')!r}"
        )

        # AC4: log event emitted (no-op when gas_log_dir not configured)
        if gas_log_dir:
            from tests.helpers.gas_log import wait_for_log
            wait_for_log(
                gas_log_dir,
                lambda e: e.get("tag") == "sync.integrity.complete",
                timeout_s=60,
                after=fence,
            )
    finally:
        scn.close()
