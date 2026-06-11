"""
test_team_scope.py — GTaskSheet-me6w.6

Entry-point coverage for Team Scope sync (_syncTeamScope, exercised via
syncDocument) and the assertTeamAccess security gate, per the scenario matrix
designed in GTaskSheet-me6w.2 (S1a/S1b/S1c/S2-S8).

Each scenario enqueues one drained `expect_callable` whose check compares the
durable Team Scope state (Drive appProperty `teamScope` + DocData.team_id, or
the full verifyConsistencyForTest for the folder-hierarchy scenarios) to the
expected value, tagged "teamscope <name>" with entry_point="syncDocument" or
"assertTeamAccess" (scn/contract.AC_REGISTRY / ENTRY_POINT_REGISTRY). This is
the single emission path for ac.*/ep.* JUnit properties (T24).

Folder hierarchy (local.settings.json, set up via setup_team_scope_fixture):
  testTeamA      — registered TeamData row TestTeamA
  testTeamAChild — child of testTeamA, registered TeamData row TestTeamAChild
  testTeamADeep  — multi-level descendant of testTeamA, NOT under
                   testTeamAChild, no intermediate TeamData registration
  testTeamNoTeam — sibling of testTeamA, unregistered, no TeamData row
                   (GTaskSheet-u2np); returned dynamically by
                   setup_team_scope_fixture and used by S2/S6 below.

S2/S6 both exercise the folder-walk no-match path, by moving their docs into
testTeamNoTeam. S6's design precondition ("TeamData tab is empty") cannot be
created without disrupting the persistent, idempotent TestTeamA/TestTeamAChild
rows required by S1a/S1b/S1c/S8 — so S6 uses the same no-team-folder setup as
S2, which produces the same observable outcome (blank teamScope, no-match
log).
"""
from scn.engine import CheckpointKind, Surface
from scn.session import ScenarioSession
from tests.helpers.gas_log import assert_log as _assert_log
from tests.helpers.gas_log import assert_no_log as _assert_no_log
from tests.helpers.gas_log import clear_logs

SHEET = Surface.SHEET
STEP = CheckpointKind.STEP


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEAMDATA_TEST_MARKED_IDS = {"TestTeamA", "TestTeamAChild"}


def _team_data_rows(scn):
    """All TeamData rows ({teamId, folderId, contact}) (GTaskSheet-zc21)."""
    resp = scn._post_fixture("get_team_data_rows")
    return (resp.get("data") or {}).get("rows") or []


def _team_scope(scn):
    resp = scn._post_fixture("get_team_scope")
    return (resp.get("data") or {}).get("teamScope", "")


def _docdata_row(scn):
    resp = scn._post_fixture("get_docdata_row")
    return (resp.get("data") or {}).get("row")


def _set_docdata(scn, **fields):
    return scn._post_fixture("set_docdata_row", fields)


def _move_to_folder(scn, folder_id):
    scn._post_fixture("move_doc_to_folder", {"folderId": folder_id})


def _consistency_check(scn, team_id):
    """Durable check via verifyConsistencyForTest(docId, {teamId}) — sole
    assertion mechanism for the folder-hierarchy scenarios (S1a/S1b/S1c/S8)."""
    def check():
        resp = scn._post_fixture("verify_consistency", {"expected": {"teamId": team_id}})
        data = resp.get("data") or {}
        if not data.get("ok"):
            return f"verify_consistency(teamId={team_id!r}) failed: {data.get('issues')}"
        return None
    return check


def _team_scope_check(scn, expected_team_id):
    """Durable check: Drive appProperty teamScope + DocData.team_id == expected."""
    def check():
        actual_scope = _team_scope(scn)
        if actual_scope != expected_team_id:
            return f"teamScope appProperty: expected={expected_team_id!r} actual={actual_scope!r}"
        row = _docdata_row(scn) or {}
        actual_team = row.get("teamId", "")
        if actual_team != expected_team_id:
            return f"DocData.team_id: expected={expected_team_id!r} actual={actual_team!r}"
        return None
    return check


def _team_access_check(scn, team_id):
    def check():
        resp = scn._post_fixture("assert_team_access", {"teamId": team_id})
        data = resp.get("data") or {}
        if not data.get("ok"):
            return f"assert_team_access(teamId={team_id!r}) failed: {data.get('error')}"
        return None
    return check


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

def test_team_scope(settings, gas_log_dir, request):
    sessions = []

    def new_doc():
        s = ScenarioSession.new_doc(settings, request=request)
        sessions.append(s)
        return s

    try:
        # ── S0 — TeamData safety: fixture setup leaves pre-existing rows
        # unchanged; any newly-created rows are test-marked only (GTaskSheet-zc21) ─
        scn_0 = new_doc()
        rows_before = _team_data_rows(scn_0)
        setup_resp = scn_0._post_fixture("setup_team_scope_fixture")
        noteam_folder_id = (setup_resp.get("data") or {}).get("testTeamNoTeam")
        assert noteam_folder_id, "setup_team_scope_fixture did not return testTeamNoTeam"
        rows_after = _team_data_rows(scn_0)

        before_by_id = {r.get("teamId"): r for r in rows_before}
        after_by_id = {r.get("teamId"): r for r in rows_after}

        for team_id, before in before_by_id.items():
            after = after_by_id.get(team_id)
            assert after is not None, (
                f"S0: pre-existing TeamData row {team_id!r} disappeared "
                f"after setup_team_scope_fixture"
            )
            assert after == before, (
                f"S0: pre-existing TeamData row {team_id!r} changed: "
                f"before={before} after={after}"
            )

        new_team_ids = set(after_by_id) - set(before_by_id)

        def check_0(new_team_ids=new_team_ids):
            extra = new_team_ids - _TEAMDATA_TEST_MARKED_IDS
            if extra:
                return (
                    f"setup_team_scope_fixture added non-test-marked TeamData "
                    f"rows: {sorted(extra)}"
                )
            return None

        err = check_0()
        assert err is None, err
        scn_0.expect_callable(
            check_0, on=SHEET, tag="teamscope teamdata-safety",
            entry_point="setup_team_scope_fixture",
        )
        scn_0.checkpoint(STEP)

        # ── S1a — direct-match: doc placed directly in testTeamA ────────────
        scn_a = new_doc()
        _move_to_folder(scn_a, settings["testTeamA"])
        fence = clear_logs(gas_log_dir) if gas_log_dir else 0.0
        scn_a.sync()
        _assert_log(
            gas_log_dir, fence,
            lambda e: e.get("tag") == "sync.teamScope.resolved"
            and e.get("data", {}).get("docId") == scn_a.doc_id
            and e.get("data", {}).get("teamId") == "TestTeamA",
            "S1a sync.teamScope.resolved",
        )
        check_a = _consistency_check(scn_a, "TestTeamA")
        err = check_a()
        assert err is None, err
        scn_a.expect_callable(check_a, on=SHEET, tag="teamscope direct-match", entry_point="syncDocument")
        scn_a.checkpoint(STEP)

        # ── S1b — subteam-match: doc placed directly in testTeamAChild ──────
        scn_b = new_doc()
        _move_to_folder(scn_b, settings["testTeamAChild"])
        fence = clear_logs(gas_log_dir) if gas_log_dir else 0.0
        scn_b.sync()
        _assert_log(
            gas_log_dir, fence,
            lambda e: e.get("tag") == "sync.teamScope.resolved"
            and e.get("data", {}).get("docId") == scn_b.doc_id
            and e.get("data", {}).get("teamId") == "TestTeamAChild",
            "S1b sync.teamScope.resolved",
        )
        check_b = _consistency_check(scn_b, "TestTeamAChild")
        err = check_b()
        assert err is None, err
        scn_b.expect_callable(check_b, on=SHEET, tag="teamscope subteam-match", entry_point="syncDocument")
        scn_b.checkpoint(STEP)

        # ── S1c — deep-walk: doc placed in testTeamADeep, several levels ────
        # below testTeamA, not under testTeamAChild, no intermediate TeamData.
        scn_c = new_doc()
        _move_to_folder(scn_c, settings["testTeamADeep"])
        fence = clear_logs(gas_log_dir) if gas_log_dir else 0.0
        scn_c.sync()
        _assert_log(
            gas_log_dir, fence,
            lambda e: e.get("tag") == "sync.teamScope.resolved"
            and e.get("data", {}).get("docId") == scn_c.doc_id
            and e.get("data", {}).get("teamId") == "TestTeamA",
            "S1c sync.teamScope.resolved",
        )
        check_c = _consistency_check(scn_c, "TestTeamA")
        err = check_c()
        assert err is None, err
        scn_c.expect_callable(check_c, on=SHEET, tag="teamscope deep-walk", entry_point="syncDocument")
        scn_c.checkpoint(STEP)

        # ── S2 — no-match: doc in a folder not registered in TeamData ───────
        scn_2 = new_doc()
        _move_to_folder(scn_2, noteam_folder_id)
        fence = clear_logs(gas_log_dir) if gas_log_dir else 0.0
        scn_2.sync()
        _assert_log(
            gas_log_dir, fence,
            lambda e: e.get("tag") == "sync.teamScope.walk.no-match"
            and e.get("data", {}).get("docId") == scn_2.doc_id,
            "S2 sync.teamScope.walk.no-match",
        )
        check_2 = _team_scope_check(scn_2, "")
        err = check_2()
        assert err is None, err
        scn_2.expect_callable(check_2, on=SHEET, tag="teamscope no-match", entry_point="syncDocument")
        scn_2.checkpoint(STEP)

        # ── S3 — UpdateDoc override: DocData.team_id wins over teamScope ────
        scn_3 = new_doc()
        _move_to_folder(scn_3, settings["testTeamA"])
        scn_3.sync()  # auto-assigns teamScope == 'TestTeamA'
        assert _team_scope(scn_3) == "TestTeamA"
        _set_docdata(scn_3, syncStatus="UpdateDoc", teamId="TestTeamAChild")
        fence = clear_logs(gas_log_dir) if gas_log_dir else 0.0
        scn_3.sync()
        _assert_log(
            gas_log_dir, fence,
            lambda e: e.get("tag") == "sync.teamScope.overridden"
            and e.get("data", {}).get("docId") == scn_3.doc_id
            and e.get("data", {}).get("teamId") == "TestTeamAChild",
            "S3 sync.teamScope.overridden",
        )
        check_3 = _team_scope_check(scn_3, "TestTeamAChild")
        err = check_3()
        assert err is None, err
        row_3 = _docdata_row(scn_3) or {}
        assert row_3.get("syncStatus") == "", f"DocData.sync_status not cleared: {row_3.get('syncStatus')!r}"
        scn_3.expect_callable(check_3, on=SHEET, tag="teamscope updatedoc-override", entry_point="syncDocument")
        scn_3.checkpoint(STEP)

        # ── S4 — idempotency: second sync makes no further teamScope writes ─
        fence = clear_logs(gas_log_dir) if gas_log_dir else 0.0
        scn_a.sync()
        _assert_no_log(
            gas_log_dir, fence,
            lambda e: e.get("tag") in ("sync.teamScope.resolved", "sync.teamScope.overridden")
            and e.get("data", {}).get("docId") == scn_a.doc_id,
            "S4 unexpected resolved/overridden on re-sync",
        )
        check_4 = _team_scope_check(scn_a, "TestTeamA")
        err = check_4()
        assert err is None, err
        scn_a.expect_callable(check_4, on=SHEET, tag="teamscope idempotent", entry_point="syncDocument")
        scn_a.checkpoint(STEP)

        # ── S5 — security gate: assertTeamAccess allows valid team access ───
        check_5 = _team_access_check(scn_a, "TestTeamA")
        err = check_5()
        assert err is None, err
        scn_a.expect_callable(check_5, on=SHEET, tag="teamscope security-gate", entry_point="assertTeamAccess")
        scn_a.checkpoint(STEP)

        # ── S6 — TeamData/no-match: sync completes, no assignment ───────────
        # See module docstring re: equivalence with S2's no-match path.
        scn_6 = new_doc()
        _move_to_folder(scn_6, noteam_folder_id)
        fence = clear_logs(gas_log_dir) if gas_log_dir else 0.0
        scn_6.sync()
        _assert_log(
            gas_log_dir, fence,
            lambda e: e.get("tag") == "sync.teamScope.walk.no-match"
            and e.get("data", {}).get("docId") == scn_6.doc_id,
            "S6 sync.teamScope.walk.no-match",
        )
        check_6 = _team_scope_check(scn_6, "")
        err = check_6()
        assert err is None, err
        scn_6.expect_callable(check_6, on=SHEET, tag="teamscope teamdata-missing", entry_point="syncDocument")
        scn_6.checkpoint(STEP)

        # ── S7 — UpdateDoc with blank Team Id: sync_status cleared, no crash ─
        scn_7 = new_doc()
        scn_7.sync()  # first sync: creates DocData row, no teamScope
        _set_docdata(scn_7, syncStatus="UpdateDoc", teamId="")
        fence = clear_logs(gas_log_dir) if gas_log_dir else 0.0
        scn_7.sync()
        _assert_log(
            gas_log_dir, fence,
            lambda e: e.get("tag") == "sync.teamScope.override-blank"
            and e.get("data", {}).get("docId") == scn_7.doc_id,
            "S7 sync.teamScope.override-blank",
        )
        check_7 = _team_scope_check(scn_7, "")
        err = check_7()
        assert err is None, err
        row_7 = _docdata_row(scn_7) or {}
        assert row_7.get("syncStatus") == "", f"DocData.sync_status not cleared: {row_7.get('syncStatus')!r}"
        scn_7.expect_callable(check_7, on=SHEET, tag="teamscope updatedoc-blank", entry_point="syncDocument")
        scn_7.checkpoint(STEP)

        # ── S8 — sticky-after-move: re-syncing after a move keeps the team ──
        _move_to_folder(scn_a, settings["testTeamAChild"])
        fence = clear_logs(gas_log_dir) if gas_log_dir else 0.0
        scn_a.sync()
        _assert_no_log(
            gas_log_dir, fence,
            lambda e: e.get("tag") in ("sync.teamScope.resolved", "sync.teamScope.overridden")
            and e.get("data", {}).get("docId") == scn_a.doc_id,
            "S8 unexpected resolved/overridden after move",
        )
        check_8 = _consistency_check(scn_a, "TestTeamA")
        err = check_8()
        assert err is None, err
        scn_a.expect_callable(check_8, on=SHEET, tag="teamscope sticky-after-move", entry_point="syncDocument")
        scn_a.checkpoint(STEP)

    finally:
        for scn in sessions:
            try:
                scn._post_route("end_journey_session", {"docId": scn.doc_id})
            except Exception:
                pass
            scn.engine.close()
