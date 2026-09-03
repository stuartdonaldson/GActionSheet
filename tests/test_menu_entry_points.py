"""
test_menu_entry_points.py — GTaskSheet-rz4k.4

Entry-point coverage for the state-modifying Sheets-menu items (MenuHandler.js),
driven via their own menu wrappers (the call-site the entry-point-coverage
invariant scopes to — NOT the core function each delegates to). Each menu wrapper
is invoked through a dedicated TestFixtures.js case (menu_sync /
menu_ensure_sheet_structure / menu_run_archive) so the menu function itself is the
recorded call-site, then a durable-state assertion is tagged with entry_point=.

Covers three of the five registered menu entry points; menuBootstrap and
menuInitializeTriggers are permanent exemptions (scn/contract.ENTRY_POINT_DEFERRED)
because driving them mid-suite mutates shared deployment state.
"""
import datetime
import secrets

import pytest

from scn import contract
from scn.ai import ai
from scn.engine import CheckpointKind, Surface
from scn.session import ScenarioSession
from tests.helpers.download import download_xlsx
from tests.helpers.sheet_inspect import load_sheet, headers, rows_for_doc

SHEET = Surface.SHEET
STEP = CheckpointKind.STEP

# 35 days ago, past ArchiveManager's 30-day threshold. Note: action text below must
# avoid trailing "(...)" — the status parser strips a trailing parenthetical (GTaskSheet-28q).
_35_DAYS_AGO = (
    datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=35)
).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def scn(settings, request):
    # request=request wires JUnit ac.*/ep.* emission to this test node (T24) — without it
    # the session is a no-op reporter and no coverage properties reach pytest.xml (q37d).
    s = ScenarioSession.new_doc(settings, request=request)
    yield s
    s.close()


# ---------------------------------------------------------------------------
# menuSync -> syncAll() — Action Sync > Sync
# ---------------------------------------------------------------------------

def test_menuSync_sweeps_registered_doc(scn):
    """menuSync() runs syncAll(), which re-sweeps every doc already present in the
    Actions sheet. Modified-valid pattern: sync once to register the doc, append a
    second action, then drive menuSync — the second action must propagate to the
    sheet, proving the menu wrapper invoked the sweep at its own call-site."""
    first = ai(action="menuSync registered-doc action synced before menu sweep")
    second = ai(action="menuSync post-registration action must appear after menu sweep")

    scn.append_paragraph(first.as_text())
    scn.sync()                                  # registers this doc in the Actions sheet

    scn.append_paragraph(second.as_text())      # doc-side change not yet in the sheet
    scn._post_fixture("menu_sync")              # menuSync() -> syncAll() re-sweeps the doc

    def _second_action_swept() -> str | None:
        rows = scn.find_sheet_actions()
        if not any(r.action == second.action for r in rows):
            present = [r.action for r in rows]
            return (
                "[rz4k.4 menuSync] post-registration action not propagated to the sheet "
                f"after menuSync sweep; sheet actions for this doc: {present!r}"
            )
        return None

    scn.expect_callable(
        _second_action_swept, on=SHEET, tag="[rz4k.4 menuSync]", entry_point="menuSync",
    )
    scn.checkpoint(STEP)


# ---------------------------------------------------------------------------
# menuEnsureSheetStructure -> ensureSheetStructure() — Setup submenu
# ---------------------------------------------------------------------------

def test_menuEnsureSheetStructure_creates_canonical_headers(scn):
    """menuEnsureSheetStructure() runs ensureSheetStructure(); the Actions tab must
    carry the canonical contract.SHEET_HEADERS in left-to-right order afterwards
    (idempotent — safe to drive against the shared sheet)."""
    scn._post_fixture("menu_ensure_sheet_structure")

    def _actions_headers_canonical() -> str | None:
        ws = load_sheet(download_xlsx(scn.settings["testSheetId"]), sheet_name="Actions")
        actual = headers(ws)                    # {header_name: col_index}
        missing = [h for h in contract.SHEET_HEADERS if h not in actual]
        if missing:
            return f"[rz4k.4 menuEnsureSheetStructure] Actions tab missing headers: {missing}"
        positions = [actual[h] for h in contract.SHEET_HEADERS]
        if positions != sorted(positions):
            return (
                "[rz4k.4 menuEnsureSheetStructure] Actions headers out of order: "
                f"{list(zip(contract.SHEET_HEADERS, positions))}"
            )
        return None

    scn.expect_callable(
        _actions_headers_canonical, on=SHEET,
        tag="[rz4k.4 menuEnsureSheetStructure]", entry_point="menuEnsureSheetStructure",
    )
    scn.checkpoint(STEP)


# ---------------------------------------------------------------------------
# menuRunArchive -> ArchiveManager.archive(ss) — Test menu
# ---------------------------------------------------------------------------

def test_menuRunArchive_moves_eligible_row_to_archive(scn):
    """menuRunArchive() runs ArchiveManager.archive(ss). Seed an archive-eligible row
    (Status='Closed' + Date Modified 35 days old, > the 30-day threshold) under a
    session-unique docId, then drive menuRunArchive — the row must leave Actions and
    appear in the Archive tab. Session-unique docId isolates the assertion from other
    rows in the shared sheet."""
    archive_doc_id = secrets.token_urlsafe(33)[:44]   # unique, never resolves in Drive
    sheet_id = scn.settings["testSheetId"]
    formula = (
        f'=HYPERLINK("https://docs.google.com/document/d/{archive_doc_id}/edit",'
        f'"menuRunArchive eligible doc")'
    )

    scn._post_fixture("seed_row", {
        "actionId": "MENU-ARCH-1",
        "actionText": "menuRunArchive archive-eligible seeded action",
        "status": "Closed",
        "documentFormula": formula,
        "dateModified": _35_DAYS_AGO,
    })

    # Pre-condition: row is in Actions, not yet in Archive.
    pre = rows_for_doc(load_sheet(download_xlsx(sheet_id), sheet_name="Actions"), archive_doc_id)
    assert len(pre) >= 1, (
        "[rz4k.4 menuRunArchive] seeded eligible row not present in Actions before archive sweep"
    )

    scn._post_fixture("menu_run_archive")        # menuRunArchive() -> ArchiveManager.archive(ss)

    def _row_moved_to_archive() -> str | None:
        xlsx = download_xlsx(sheet_id)
        in_actions = rows_for_doc(load_sheet(xlsx, sheet_name="Actions"), archive_doc_id)
        in_archive = rows_for_doc(load_sheet(xlsx, sheet_name="Archive"), archive_doc_id)
        if in_actions:
            return (
                "[rz4k.4 menuRunArchive] eligible row still in Actions after menuRunArchive "
                f"({len(in_actions)} row(s)) — archive sweep did not run via the menu wrapper"
            )
        if not in_archive:
            return "[rz4k.4 menuRunArchive] eligible row not found in Archive tab after sweep"
        return None

    scn.expect_callable(
        _row_moved_to_archive, on=SHEET,
        tag="[rz4k.4 menuRunArchive]", entry_point="menuRunArchive",
    )
    scn.checkpoint(STEP)


# ---------------------------------------------------------------------------
# menuSyncActiveDoc -> syncDocument(docId) — Docs menu "Sync" (GTaskSheet-ez2e)
# ---------------------------------------------------------------------------

def test_menuSyncActiveDoc_syncs_active_doc(scn):
    """menuSyncActiveDoc() runs syncDocument(docId) for the active document
    (MenuHandler.js), distinct from the already-covered syncDocument() core and
    from the Sheets-side menuSync (-> syncAll()). DocumentApp.getActiveDocument()
    only resolves inside a real Docs UI session; outside one (this fixture's
    stateless webapp execution) it falls back to _TEST_ACTIVE_DOC_ID, a
    case-scoped script-property bridge the 'menu_sync_active_doc' fixture
    case sets for the duration of this call only."""
    seed = ai(action="menuSyncActiveDoc unsynced floating action")
    scn.append_paragraph(seed.as_text())        # doc-side change, no Actions row yet

    scn._post_fixture("menu_sync_active_doc")   # menuSyncActiveDoc() -> syncDocument(docId)

    def _action_synced() -> str | None:
        rows = scn.find_sheet_actions()
        if not any(r.action == seed.action for r in rows):
            present = [r.action for r in rows]
            return (
                "[ez2e menuSyncActiveDoc] action not propagated to the sheet after "
                f"menuSyncActiveDoc; sheet actions for this doc: {present!r}"
            )
        return None

    scn.expect_callable(
        _action_synced, on=SHEET, tag="[ez2e menuSyncActiveDoc]", entry_point="menuSyncActiveDoc",
    )
    scn.checkpoint(STEP)


# ---------------------------------------------------------------------------
# menuInsertTrackerActiveDoc -> insertTrackerTable(docId) — Docs menu
# "Insert Tracker" (GTaskSheet-ez2e)
# ---------------------------------------------------------------------------

def test_menuInsertTrackerActiveDoc_inserts_tracker(scn):
    """menuInsertTrackerActiveDoc() runs insertTrackerTable(docId) for the active
    document, distinct from the already-covered insertTrackerTable() core."""
    seed = ai(action="menuInsertTrackerActiveDoc pre-tracker floating action")
    scn.append_paragraph(seed.as_text())
    scn.sync()  # anchor the action first

    scn._post_fixture("menu_insert_tracker_active_doc")  # menuInsertTrackerActiveDoc()

    rows = scn.find_sheet_actions()
    assert any(r.action_id is not None for r in rows), (
        "[ez2e menuInsertTrackerActiveDoc] expected an anchored action before tracker insert"
    )

    def _tracker_consistency_ok() -> str | None:
        try:
            scn.verify_consistency(scope=Surface.DOC)
        except AssertionError as exc:
            return f"[ez2e menuInsertTrackerActiveDoc] verify_consistency failed: {exc}"
        return None

    scn.expect_callable(
        _tracker_consistency_ok, on=SHEET,
        tag="[ez2e menuInsertTrackerActiveDoc]", entry_point="menuInsertTrackerActiveDoc",
    )
    scn.checkpoint(STEP)


# ---------------------------------------------------------------------------
# menuForceRefreshActiveDoc -> syncDocument(docId, {force:true}) — Docs menu
# "Force Refresh Style" (gts-t78c)
# ---------------------------------------------------------------------------

def test_menuForceRefreshActiveDoc_flushes_converged_action(scn, gas_log_dir):
    """menuForceRefreshActiveDoc() must rewrite an action paragraph's rendering
    even when sheet and doc data already agree (no pending delta) -- the whole
    point of "force" is bypassing the diff a plain sync relies on. A plain
    second sync of an already-converged doc is a no-op for that item, so the
    only observable proof force actually did something extra is the
    sync.forceFlush {docId,count} GAS log line (gts-t78c AC-5)."""
    if not gas_log_dir:
        pytest.skip("gas_log_dir not configured — force-flush proof requires GAS log access")

    from tests.helpers.gas_log import assert_log, clear_logs

    seed = ai(action="menuForceRefreshActiveDoc converged floating action")
    scn.append_paragraph(seed.as_text())
    scn.sync()  # converge doc <-> sheet: no pending delta remains for this item

    fence = clear_logs(gas_log_dir)
    scn._post_fixture("menu_force_refresh_active_doc")  # menuForceRefreshActiveDoc()

    assert_log(
        gas_log_dir, fence,
        lambda e: e.get("tag") == "sync.forceFlush"
        and e.get("data", {}).get("docId") == scn.doc_id
        and (e.get("data", {}).get("count") or 0) >= 1,
        "[t78c menuForceRefreshActiveDoc] expected sync.forceFlush with count>=1 for a "
        "converged doc (proves force bypassed the diff, not just re-ran a no-op sync)",
    )
    scn.checkpoint(STEP)


def test_menuSyncActiveDoc_converged_doc_emits_no_forceFlush(scn, gas_log_dir):
    """Non-regression (gts-t78c AC-2): the default (non-forced) menuSyncActiveDoc
    path on an already-converged doc must stay diff-only -- no sync.forceFlush
    line, proving force is opt-in and did not change default sync behavior."""
    if not gas_log_dir:
        pytest.skip("gas_log_dir not configured — force-flush proof requires GAS log access")

    from tests.helpers.gas_log import assert_no_log, clear_logs

    seed = ai(action="menuSyncActiveDoc no-force converged floating action")
    scn.append_paragraph(seed.as_text())
    scn.sync()  # converge doc <-> sheet

    fence = clear_logs(gas_log_dir)
    scn._post_fixture("menu_sync_active_doc")  # menuSyncActiveDoc() -- force defaults false

    assert_no_log(
        gas_log_dir, fence,
        lambda e: e.get("tag") == "sync.forceFlush" and e.get("data", {}).get("docId") == scn.doc_id,
        "[t78c menuSyncActiveDoc] non-forced sync of a converged doc must not emit sync.forceFlush",
    )
    scn.checkpoint(STEP)
