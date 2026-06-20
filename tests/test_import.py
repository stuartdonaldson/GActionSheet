"""
test_import.py — GTaskSheet-1dxz + GTaskSheet-4gsx (EPIC-D Import tab, TST coverage).

GTaskSheet-1dxz binds AC-1's (`list_importable_actions`) visibility to the shared
J-ACCESS-FILTER journey (knowledge-base/staging/j-access-filter-journey.md P1-P4),
reduced scope (Primary only, existing testTeamA/testTeamAChild fixtures — see
docs/security-architecture.md §1 for why account-differentiated TeamAccessDenied
is not producible today):
  - readable-team-present (P1-P3)
  - TeamNotFound-absent (P4)

GTaskSheet-4gsx is one end-to-end functional journey AC-1 (list) -> AC-2 (select +
import) -> AC-3 (forward), entry-point call-site = the Import card's
'Import selected' button (_submitImport).

All testing is UI-driven (show_tab('Import') + scn/ui.py driver methods), which
exercises list_importable_actions server-side via _buildImportCard/_buildImportTabSection ->
_callWebApp.
"""
import os
import pathlib

import pytest

from scn.ai import ai
from scn.engine import CheckpointKind, Surface
from scn.session import ScenarioSession
from scn.ui import UiDriver
from tests.helpers.access_filter import assert_visible_set, import_adapter, visible_doc_set
from tests.helpers.gas_log import assert_log, clear_logs

STEP = CheckpointKind.STEP


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def browser_page():
    """Launch Chromium with saved auth state; yield the page for UI-driven acts."""
    from playwright.sync_api import sync_playwright

    auth = pathlib.Path(__file__).parent.parent / ".auth" / "user.json"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=os.environ.get("PWHEADFUL") != "1")
        ctx = browser.new_context(
            storage_state=str(auth),
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        yield page
        ctx.close()
        browser.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _move_to_folder(scn, folder_id):
    scn._post_fixture("move_doc_to_folder", {"folderId": folder_id})


def _set_docdata(scn, **fields):
    return scn._post_fixture("set_docdata_row", fields)


def _docdata_row(scn):
    resp = scn._post_fixture("get_docdata_row")
    return (resp.get("data") or {}).get("row") or {}


def _seed_open_action(scn, action_text, assignee=None):
    """Append an 'AI: ... (Open)' paragraph, sync, and resolve the assigned AI-N."""
    seed = ai(action=action_text, assignee=assignee, status="Open")
    scn.append_paragraph(seed.as_text())
    scn.sync()
    for row in scn.find_sheet_actions():
        if row.action == action_text:
            seed.action_id = row.action_id
            seed.global_id = row.global_id
            seed.created_date = row.created_date
            return seed
    raise AssertionError(f"seeded action {action_text!r} not found in sheet after sync")


def _seed_import_candidate(scn, team_id, action_text, *, sync_status=""):
    """Fabricate the Actions-row + DocData state list_importable_actions reads,
    without opening the doc (no append_paragraph/sync() round trip).

    Why this is safe (GTaskSheet-ishz.1 follow-up, 2026-06-20 perf pass):
    _listImportableActionsData (src/WebApp.js) never reads doc content — it
    only joins an Actions-sheet row (status/file_id, via seed_row) against a
    DocData row (teamId/syncStatus, via set_docdata_row). A real scn.sync()
    additionally pays for DocumentApp.openById + paragraph scan + team-scope
    folder-walk + flush-back (src/SyncManager.js::syncDocument, ~12-19s per
    call) to produce exactly those two rows — none of which this test needs
    to re-verify; that machinery already has its own coverage in
    tests/test_sync_all.py and the team-scope fixture tests. Using this
    helper for scn_sibling/scn_other/scn_trashed cut this test's three-doc
    setup from ~111s of sequential sync_document calls to a handful of cheap
    fixture POSTs.

    CAUTION — re-derive this helper if the contract changes: if
    _listImportableActionsData ever starts reading something only a real
    sync populates (doc title, last-modified time, an in-doc field), this
    helper's fabricated rows will silently stop matching what a real synced
    doc would look like, and this test would keep passing without exercising
    that new path. Check src/WebApp.js::_listImportableActionsData's field
    reads before trusting this shortcut after such a change.
    """
    seed = ai(action=action_text, status="Open")
    seed.global_id = f"{scn.doc_id}/AI-1"
    formula = f'=HYPERLINK("https://docs.google.com/document/d/{scn.doc_id}/edit","")'
    scn._post_fixture("seed_row", {
        "globalId": seed.global_id,
        "actionId": 1,
        "actionText": action_text,
        "status": "Open",
        "documentFormula": formula,
    })
    _set_docdata(scn, teamId=team_id, syncStatus=sync_status)
    return seed


# ---------------------------------------------------------------------------
# GTaskSheet-1dxz — J-ACCESS-FILTER P1-P4 (reduced scope)
# ---------------------------------------------------------------------------

def test_import_access_filter(settings, gas_log_dir, browser_page, request):
    sessions = []

    def new_doc():
        s = ScenarioSession.new_doc(settings, request=request)
        sessions.append(s)
        return s

    try:
        scn_setup = new_doc()
        setup_resp = scn_setup._post_fixture("setup_team_scope_fixture")
        teams = setup_resp.get("data") or {}
        team_a = teams["testTeamA"]

        # ── Readable (P1-P3): target + sibling, both in testTeamA ────────────
        # scn_target is the doc whose sidebar UI is actually driven below, so it
        # needs a real sync() (real DocData row written by the real
        # team-scope folder-walk it's testing the read side of).
        scn_target = new_doc()
        _move_to_folder(scn_target, team_a)
        scn_target.sync()
        scn_target.ui = UiDriver(browser_page, doc_id=scn_target.doc_id)

        # scn_sibling/scn_other below are pure leadup state for the filter
        # check — see _seed_import_candidate's docstring for why they skip
        # the real sync() round trip.
        scn_sibling = new_doc()
        _seed_import_candidate(scn_sibling, "TestTeamA", "Import-filter sibling action")

        # ── Absent — different team (negative half of P1-P3) ────────────────
        scn_other = new_doc()
        _seed_import_candidate(scn_other, "TestTeamAChild", "Import-filter other-team action")

        fence = clear_logs(gas_log_dir) if gas_log_dir else 0.0
        scn_target.ui.show_tab("Import")
        expected = visible_doc_set(scn_target, seeded={scn_sibling.doc_id})
        # testTeamA/testTeamAChild are shared fixture folders that accumulate
        # ActionSheet rows across runs (end_journey_session trashes the doc but
        # not its rows) — scope the comparison to docs this test itself seeded.
        candidates = {scn_sibling.doc_id, scn_other.doc_id}

        def check_readable():
            actual = import_adapter(scn_target.ui.read_import_list()) & candidates
            try:
                assert_visible_set(actual, expected, account="Primary", phase="P1-P3")
            except AssertionError as exc:
                return str(exc)
            return None

        err = check_readable()
        assert err is None, err
        assert_log(
            gas_log_dir, fence,
            lambda e: e.get("tag") == "importList.done"
            and e.get("data", {}).get("count", 0) >= 1,
            "importList.done",
        )
        scn_target.expect_callable(
            check_readable, on=Surface.UI,
            tag="import access-readable", entry_point="importList",
        )
        scn_target.checkpoint(STEP, on=frozenset({Surface.UI}))

        # ── Absent — source doc trashed (GTaskSheet-wdh0) ────────────────────
        # Same-team doc whose DocData row has sync_status='Deleted' (source doc
        # removed/inaccessible) must be excluded from the import list even
        # though its team matches — list_importable_actions filters on
        # DocData.syncStatus in addition to the team-scope join.
        # Same leadup-state shortcut as scn_sibling/scn_other (_seed_import_candidate
        # docstring) — sync_status="Deleted" is set in the same fixture call instead
        # of a real sync() followed by a separate _set_docdata override.
        scn_trashed = new_doc()
        _seed_import_candidate(
            scn_trashed, "TestTeamA", "Import-filter trashed-doc action",
            sync_status="Deleted",
        )

        # scn_target.ui is still showing the Import card from the P1-P3 check
        # above -- its own buttons are Back/Select all/Import selected, not
        # "Import", so show_tab("Import") must return to the tab bar first
        # (same convention as tests/test_sidebar.py's Import/Back/Notify/Back
        # sequence) or its button lookup never finds a match.
        scn_target.ui.show_tab("Back")
        scn_target.ui.show_tab("Import")

        def check_trashed_absent():
            visible_ids = import_adapter(scn_target.ui.read_import_list())
            if scn_trashed.doc_id in visible_ids:
                return f"trashed-source doc unexpectedly visible: {sorted(visible_ids)}"
            return None

        err = check_trashed_absent()
        assert err is None, err
        scn_target.expect_callable(
            check_trashed_absent, on=Surface.UI,
            tag="import source-deleted-absent", entry_point="importList",
        )
        scn_target.checkpoint(STEP, on=frozenset({Surface.UI}))

        # ── Absent — TeamNotFound (P4) ───────────────────────────────────────
        scn_p4 = new_doc()
        scn_p4.sync()
        _set_docdata(scn_p4, teamId="TestTeamNonexistent")
        scn_p4.ui = UiDriver(browser_page, doc_id=scn_p4.doc_id)

        fence2 = clear_logs(gas_log_dir) if gas_log_dir else 0.0
        scn_p4.ui.show_tab("Import")

        def check_absent():
            groups = scn_p4.ui.read_import_list()
            if groups != []:
                return f"P4 expected empty import list, got {groups!r}"
            return None

        err = check_absent()
        assert err is None, err
        assert_log(
            gas_log_dir, fence2,
            lambda e: e.get("tag") == "importList.access_denied"
            and "TeamNotFound:" in (e.get("data", {}).get("err") or ""),
            "importList.access_denied TeamNotFound",
        )
        scn_p4.expect_callable(
            check_absent, on=Surface.UI,
            tag="import access-absent", entry_point="importList",
        )
        scn_p4.checkpoint(STEP, on=frozenset({Surface.UI}))
    finally:
        for scn in sessions:
            try:
                scn._post_route("end_journey_session", {"docId": scn.doc_id})
            except Exception:
                pass
            scn.engine.close()


# ---------------------------------------------------------------------------
# GTaskSheet-2p21 — Team view page (doGet ?cmd=teamview), twin of GTaskSheet-cu55
# ---------------------------------------------------------------------------

def test_team_view_page(settings, gas_log_dir, request):
    """Team-view page lists only open-action docs in the target team, with
    correct open/resolved counts and branded, new-tab doc links — and the
    testTeamA fixture row has no Team Link, exercising the sidebar's fallback
    case (GTaskSheet-cu55) end-to-end via the same page the fallback links to.
    """
    sessions = []

    def new_doc():
        s = ScenarioSession.new_doc(settings, request=request)
        sessions.append(s)
        return s

    try:
        scn_setup = new_doc()
        setup_resp = scn_setup._post_fixture("setup_team_scope_fixture")
        teams = setup_resp.get("data") or {}
        team_a = teams["testTeamA"]
        team_a_child = teams["testTeamAChild"]

        team_rows = {r.get("teamId"): r for r in scn_setup._post_fixture("get_team_data_rows").get("data", {}).get("rows", [])}
        assert not (team_rows.get("TestTeamA") or {}).get("teamLink"), (
            "testTeamA fixture row unexpectedly has a Team Link — this test exercises "
            "the no-link fallback case"
        )

        # ── Doc with 1 open + 1 resolved action, in TestTeamA ────────────────
        scn_open = new_doc()
        _move_to_folder(scn_open, team_a)
        scn_open.sync()
        open_doc_name = _docdata_row(scn_open).get("docName")
        _seed_open_action(scn_open, "Team-view open action")
        resolved = _seed_open_action(scn_open, "Team-view resolved action")
        scn_open.edit_sheet(resolved, status="Done")
        scn_open.sync()

        # ── Doc with zero open actions (all resolved) — must be excluded ────
        scn_all_resolved = new_doc()
        _move_to_folder(scn_all_resolved, team_a)
        scn_all_resolved.sync()
        all_resolved_action = _seed_open_action(scn_all_resolved, "Team-view all-resolved action")
        scn_all_resolved.edit_sheet(all_resolved_action, status="Done")
        scn_all_resolved.sync()

        # ── Doc in a different team — must be excluded ───────────────────────
        scn_other_team = new_doc()
        _move_to_folder(scn_other_team, team_a_child)
        scn_other_team.sync()
        _seed_open_action(scn_other_team, "Team-view other-team action")

        def check_team_view():
            html = scn_setup.fetch_team_view_html("TestTeamA")
            if open_doc_name not in html:
                return f"team view missing open-action doc {open_doc_name!r}: {html!r}"
            if "Team-view open action" in html or "Team-view resolved action" in html:
                return f"team view leaked action text: {html!r}"
            if f"/document/d/{scn_open.doc_id}/edit" not in html:
                return f"team view missing doc link for {scn_open.doc_id}: {html!r}"
            if 'target="_blank"' not in html:
                return f"team view doc link missing target=_blank: {html!r}"
            if "Northlake UU Tool Suite" not in html:
                return f"team view missing suite branding: {html!r}"
            all_resolved_name = _docdata_row(scn_all_resolved).get("docName")
            if all_resolved_name and all_resolved_name in html:
                return f"team view should exclude zero-open-action doc {all_resolved_name!r}: {html!r}"
            other_team_name = _docdata_row(scn_other_team).get("docName")
            if other_team_name and other_team_name in html:
                return f"team view should exclude other-team doc {other_team_name!r}: {html!r}"
            return None

        err = check_team_view()
        assert err is None, err
        scn_setup.expect_callable(
            check_team_view, on=Surface.UI, tag="teamview open-docs-only", entry_point="doGet",
        )
        scn_setup.checkpoint(STEP, on=frozenset({Surface.UI}))

        # ── Unknown teamId: non-leaking not-found page ───────────────────────
        html_unknown = scn_setup.fetch_team_view_html("TestTeamNonexistent")
        assert "not found" in html_unknown.lower(), f"expected not-found page: {html_unknown!r}"
        assert "TestTeamNonexistent" not in html_unknown, (
            f"unknown teamId should not be echoed back: {html_unknown!r}"
        )
    finally:
        for scn in sessions:
            try:
                scn._post_route("end_journey_session", {"docId": scn.doc_id})
            except Exception:
                pass
            scn.engine.close()


# ---------------------------------------------------------------------------
# GTaskSheet-4gsx — AC-1 -> AC-2 -> AC-3 functional journey
# ---------------------------------------------------------------------------

def test_import_flow_forward_sync(settings, gas_log_dir, browser_page, request):
    sessions = []

    def new_doc():
        s = ScenarioSession.new_doc(settings, request=request)
        sessions.append(s)
        return s

    try:
        scn_setup = new_doc()
        setup_resp = scn_setup._post_fixture("setup_team_scope_fixture")
        teams = setup_resp.get("data") or {}
        team_a = teams["testTeamA"]
        team_a_child = teams["testTeamAChild"]

        # ── Seed: target + 2 sources in testTeamA, 1 other-team negative ────
        scn_target = new_doc()
        _move_to_folder(scn_target, team_a)
        scn_target.sync()
        scn_target.ui = UiDriver(browser_page, doc_id=scn_target.doc_id)
        target_doc_name = _docdata_row(scn_target).get("docName")

        scn_src1 = new_doc()
        _move_to_folder(scn_src1, team_a)
        scn_src1.sync()
        src1_action = _seed_open_action(scn_src1, "Import-flow source-1 action")

        scn_src2 = new_doc()
        _move_to_folder(scn_src2, team_a)
        scn_src2.sync()
        src2_action = _seed_open_action(scn_src2, "Import-flow source-2 action")

        scn_other = new_doc()
        _move_to_folder(scn_other, team_a_child)
        scn_other.sync()
        _seed_open_action(scn_other, "Import-flow other-team action")

        # ── AC-1: Import tab list — grouped by doc_name ASC, AI-N ASC within ─
        scn_target.ui.show_tab("Import")

        def check_ac1():
            groups = scn_target.ui.read_import_list()
            doc_names = [g["doc_name"] for g in groups]
            if doc_names != sorted(doc_names):
                return f"groups not doc_name ASC: {doc_names}"
            for group in groups:
                ns = [a["n"] for a in group["actions"]]
                if ns != sorted(ns):
                    return f"actions not AI-N ASC in {group['doc_name']!r}: {ns}"
            visible_ids = import_adapter(groups)
            if scn_src1.doc_id not in visible_ids or scn_src2.doc_id not in visible_ids:
                return f"expected source docs visible, got {sorted(visible_ids)}"
            if scn_other.doc_id in visible_ids:
                return f"other-team doc unexpectedly visible: {sorted(visible_ids)}"
            return None

        err = check_ac1()
        assert err is None, err
        scn_target.expect_callable(
            check_ac1, on=Surface.UI, tag="import ac1-list", entry_point="importList",
        )
        scn_target.checkpoint(STEP, on=frozenset({Surface.UI}))

        # ── Negative: empty selection -> no insert (fresh render, nothing
        # checked). _submitImport short-circuits via _buildMessageCard
        # ('Nothing selected', ...), which replaces the tab bar — reload and
        # reopen the sidebar to get back to a tabbed card for AC-2.
        before_empty = {r.global_id for r in scn_target.find_sheet_actions()}
        scn_target.ui.click_import()
        after_empty = {r.global_id for r in scn_target.find_sheet_actions()}
        assert after_empty == before_empty, "empty-selection Import changed ActionSheet rows"

        scn_target.ui.reload()
        scn_target.ui._current_card = None  # message card replaced the tab bar; force re-open
        scn_target.ui.show_tab("Import")

        # ── AC-2: select the 2 seeded source actions -> Import selected ─────
        # testTeamA accumulates rows across runs (end_journey_session trashes
        # the doc but not its ActionSheet rows), so "Select all" would import
        # every stale row too — select only this test's own seeded actions.
        #
        # The Import tab's CHECK_BOX SelectionInput state cannot be driven via
        # Playwright (CardService Material checkbox wrapper does not bridge to
        # e.formInputs — see GTaskSheet-8qe5). Drive AC-2/AC-3 via the
        # import_selected_for_test interactive-test-entry-point instead, which
        # invokes the same _importSelectedRows core as _submitImport
        # (EPIC GTaskSheet-pw5x tracks migrating this back to a UI call-site).
        before_ids = {r.global_id for r in scn_target.find_sheet_actions()}

        fence = clear_logs(gas_log_dir) if gas_log_dir else 0.0
        result = scn_target._post_route("import_selected_for_test", {
            "testDocId": scn_target.doc_id,
            "globalIds": [src1_action.global_id, src2_action.global_id],
        })
        assert result.get("ok") and result.get("inserted", 0) >= 2, result
        assert_log(
            gas_log_dir, fence,
            lambda e: e.get("tag") == "importSelected.done"
            and e.get("data", {}).get("inserted", 0) >= 2,
            "importSelected.done",
        )

        def check_ac2():
            after_rows = scn_target.find_sheet_actions()
            new_rows = [r for r in after_rows if r.global_id not in before_ids]
            if len(new_rows) < 2:
                return f"expected >=2 new rows, got {len(new_rows)}"
            new_rows.sort(key=lambda r: int(r.action_id.split("-")[1]))
            ns = [int(r.action_id.split("-")[1]) for r in new_rows]
            if ns != list(range(ns[0], ns[0] + len(ns))):
                return f"new AI-N not sequential: {ns}"
            carried = {r.action for r in new_rows}
            if src1_action.action not in carried or src2_action.action not in carried:
                return f"source action text not carried over: {carried}"
            carried_created = {r.action: r.created_date for r in new_rows}
            if carried_created.get(src1_action.action) != src1_action.created_date:
                return (f"created_date not carried over for src1: "
                        f"{carried_created.get(src1_action.action)!r} != {src1_action.created_date!r}")
            if carried_created.get(src2_action.action) != src2_action.created_date:
                return (f"created_date not carried over for src2: "
                        f"{carried_created.get(src2_action.action)!r} != {src2_action.created_date!r}")
            return None

        err = check_ac2()
        assert err is None, err
        scn_target.expect_callable(
            check_ac2, on=Surface.SHEET, tag="import ac2-select", entry_point="importSelectedForTest",
        )
        scn_target.checkpoint(STEP, on=frozenset({Surface.SHEET}))

        # ── AC-3: source rows Forwarded + suffixed + dirty ───────────────────
        assert_log(
            gas_log_dir, fence,
            lambda e: e.get("tag") == "forwardRows.done"
            and e.get("data", {}).get("count", 0) >= 2,
            "forwardRows.done",
        )

        def _forward_check(src_scn, src_action):
            def check():
                rows = src_scn.find_sheet_actions()
                row = next((r for r in rows if r.global_id == src_action.global_id), None)
                if row is None:
                    return f"source row {src_action.global_id} not found after import"
                if row.status != "Forwarded":
                    return f"source row {src_action.global_id} status={row.status!r}, expected 'Forwarded'"
                if f"[Forward:{target_doc_name} AI-" not in row.action:
                    return f"source row {src_action.global_id} action missing forward suffix: {row.action!r}"
                if row.sync_status != "Dirty":
                    return f"source row {src_action.global_id} sync_status={row.sync_status!r}, expected 'Dirty'"
                return None
            return check

        check_src1 = _forward_check(scn_src1, src1_action)
        err = check_src1()
        assert err is None, err
        scn_src1.expect_callable(
            check_src1, on=Surface.SHEET, tag="import ac3-forward", entry_point="importSelectedForTest",
        )
        # entry_point: forward_action_rows (GTaskSheet-rz4k.2) -- _importSelectedRows
        # calls this production route directly (_callWebApp('forward_action_rows', ...),
        # EditorAddonCard.js); tag the same durable Forwarded/suffix/Dirty check.
        scn_src1.expect_callable(
            check_src1, on=Surface.SHEET, tag="[rz4k.2 forward_action_rows]", entry_point="forward_action_rows",
        )
        scn_src1.checkpoint(STEP)

        check_src2 = _forward_check(scn_src2, src2_action)
        err = check_src2()
        assert err is None, err
        scn_src2.expect_callable(
            check_src2, on=Surface.SHEET, tag="import ac3-forward", entry_point="importSelectedForTest",
        )
        scn_src2.checkpoint(STEP)

        # Post-import sync: source docs reconcile their now-Forwarded chip/row.
        scn_src1.sync()
        scn_src2.sync()
    finally:
        for scn in sessions:
            try:
                scn._post_route("end_journey_session", {"docId": scn.doc_id})
            except Exception:
                pass
            scn.engine.close()


# ---------------------------------------------------------------------------
# GTaskSheet-apcu — UC-E AC4 duplicate-forward guard
# ---------------------------------------------------------------------------

def test_forward_duplicate_guard(settings, request):
    """Re-forwarding an already-Forwarded source row is a no-op (UC-E AC4).

    Entry point under test: forward_action_rows — specifically the
    seen[]/isResolved(entry.status) guard in _handleForwardActionRows. The
    production import flow can never reach this guard with a stale/duplicate
    globalId: import_selected_for_test re-derives its row set from
    _listImportableActionsData, which already excludes resolved/Forwarded
    rows before forward_action_rows is ever called. Driven here via
    forward_action_rows_test (testToken-gated mirror of the same guard loop,
    GTaskSheet-apcu) with an explicit forwards[] payload that bypasses that
    filter — the only way to actually reach the guard from a test.
    """
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        src = _seed_open_action(scn, "apcu duplicate-forward guard source action")
        target_doc_name = "apcu-target-doc"
        new_ai = "AI-99"
        forward_payload = {
            "forwards": [{"sourceGlobalId": src.global_id, "newGlobalId": f"{scn.doc_id}/{new_ai}"}],
            "targetDocName": target_doc_name,
        }

        result1 = scn._post_route("forward_action_rows_test", forward_payload)
        assert result1.get("ok") and result1.get("forwarded") == [src.global_id], result1

        def check_forwarded():
            rows = scn.find_sheet_actions()
            row = next((r for r in rows if r.global_id == src.global_id), None)
            if row is None:
                return f"source row {src.global_id} not found"
            if row.status != "Forwarded":
                return f"status={row.status!r}, expected 'Forwarded'"
            if f"[Forward:{target_doc_name} {new_ai}]" not in row.action:
                return f"action missing forward suffix: {row.action!r}"
            return None

        err = check_forwarded()
        assert err is None, err
        scn.expect_callable(
            check_forwarded, on=Surface.SHEET, tag="[apcu forward-once]",
            entry_point="forward_action_rows",
        )
        scn.checkpoint(STEP)

        first_action_text = next(
            r.action for r in scn.find_sheet_actions() if r.global_id == src.global_id
        )

        # Re-forward the SAME already-Forwarded sourceGlobalId: no-op — no
        # second [Forward:...] suffix, no change to status/action text.
        result2 = scn._post_route("forward_action_rows_test", forward_payload)
        assert result2.get("ok") and result2.get("forwarded") == [], result2

        def check_no_duplicate():
            rows = scn.find_sheet_actions()
            row = next((r for r in rows if r.global_id == src.global_id), None)
            if row is None:
                return f"source row {src.global_id} not found"
            if row.action != first_action_text:
                return f"duplicate forward changed action text: {first_action_text!r} -> {row.action!r}"
            if row.status != "Forwarded":
                return f"status drifted: {row.status!r}"
            return None

        err = check_no_duplicate()
        assert err is None, err
        scn.expect_callable(
            check_no_duplicate, on=Surface.SHEET, tag="[apcu duplicate-forward-guard]",
            entry_point="forward_action_rows",
        )
        scn.checkpoint(STEP)
    finally:
        scn.close()
