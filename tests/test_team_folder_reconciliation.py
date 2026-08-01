"""
test_team_folder_reconciliation.py — gts-sl64

Retroactive coverage (Path B, twin to gts-b6dm) for syncAll's DocData
integrity pass re-deriving DocData.teamId from a document's CURRENT Drive
folder ancestry, rather than trusting the sticky teamScope cache
(SyncManager.js ~line 469's team-reconciliation block).

This is a *different* call-site than tests/test_team_scope.py's S8
"sticky-after-move" scenario: S8 proves that a per-doc sync (scn.sync() ->
syncDocument() -> _syncTeamScope()) is deliberately sticky by design
(gts-j8cn) — a folder move does NOT change team on a per-doc resync. This
file proves the opposite is true of syncAll's separate, once-per-sweep
integrity pass: driving reconciliation via the sync_all fixture (syncAll()
itself, not syncDocument()) DOES pick up a folder move. Per the entry-point
coverage invariant, every scenario below calls sync_all (not sync()) as its
last mutating step, and entry_point="syncAll" is what's tagged.

No shared context: authored against gts-sl64's frozen Design/AC text in
`bd show gts-sl64`, not by reading gts-b6dm's implementation diff.
"""
import time

import pytest

from scn.engine import CheckpointKind, Surface
from scn.session import ScenarioSession

SHEET = Surface.SHEET
STEP = CheckpointKind.STEP


def _move_to_folder(scn, folder_id):
    scn._post_fixture("move_doc_to_folder", {"folderId": folder_id})


def _sync_all_patient(scn, fixture_name="sync_all", extra=None, timeout=600):
    """Like scn._post_fixture, but with a longer client-side read timeout.

    syncAll() over the real production Actions/DocData backlog has been
    observed (gts-b6dm comments) to take anywhere from ~1 to ~12+ minutes
    depending on how many docs need reconciliation/walking that sweep.
    ScenarioSession's default 360s client timeout occasionally trips on
    this variance (a client-side socket read timeout, not a GAS-side
    failure — the execution completes server-side either way).
    """
    payload = {
        "action": "run_fixture",
        "testToken": scn.settings.get("testToken") or "",
        "fixture": fixture_name,
        "testDocId": scn.doc_id,
    }
    if extra:
        payload.update(extra)
    return scn._post(payload, timeout=timeout)


def _sync_all_until_team(scn, expected_team_id, attempts=4, delay_s=8):
    """Calls sync_all repeatedly until DocData.teamId matches expected_team_id
    (or attempts are exhausted), returning the last-seen row.

    Drive's files.list bulk metadata (the O(1) fast path syncAll's team
    reconciliation prefers, gts-b6dm's directFolderTeamMap) is backed by an
    eventually-consistent search index — a DriveApp.moveTo() immediately
    before syncAll's own files.list call can occasionally be observed with
    the file's PRIOR parent for a few seconds, before the index catches up.
    In production this is a non-issue (syncAll runs on a 30-minute cadence,
    far longer than any observed propagation lag); here, where the test
    drives move + syncAll back-to-back, a short bounded retry absorbs that
    lag without masking a real reconciliation failure (a real bug would
    still fail to reconcile after every retry).
    """
    row = None
    for attempt in range(attempts):
        _sync_all_patient(scn)
        row = _docdata_row(scn) or {}
        if row.get("teamId") == expected_team_id:
            return row
        if attempt < attempts - 1:
            time.sleep(delay_s)
    return row


def _docdata_row(scn):
    resp = scn._post_fixture("get_docdata_row")
    return (resp.get("data") or {}).get("row")


def _team_scope(scn):
    resp = scn._post_fixture("get_team_scope")
    return (resp.get("data") or {}).get("teamScope", "")


def _set_docdata(scn, **fields):
    return scn._post_fixture("set_docdata_row", fields)


@pytest.fixture
def team_folders(settings, request):
    """Ensures the shared TeamScope folder hierarchy + no-team folder exist,
    same fixture test_team_scope.py relies on (idempotent, safe to call from
    a second test module — GTaskSheet-zc21 verifies it never disturbs
    pre-existing TeamData rows)."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        setup_resp = scn._post_fixture("setup_team_scope_fixture")
        data = setup_resp.get("data") or {}
        yield data
    finally:
        scn.close()


# ---------------------------------------------------------------------------
# AC1 — folder move reassigns team via syncAll (not a per-doc resync)
# ---------------------------------------------------------------------------

def test_syncall_reconciles_team_after_folder_move(settings, team_folders, request):
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        _move_to_folder(scn, team_folders["testTeamA"])
        scn.append_paragraph("AI-1: sl64 AC1 folder-move action")
        scn.sync()  # first-pass auto-assignment: DocData.teamId = TestTeamScopeA
        pre = _docdata_row(scn) or {}
        assert pre.get("teamId") == "TestTeamScopeA", (
            f"[sl64 AC1 pre] expected initial teamId=TestTeamScopeA, got {pre.get('teamId')!r}"
        )

        # Move to a DIFFERENT team's folder, then drive reconciliation via
        # syncAll itself — NOT scn.sync() (that per-doc path is deliberately
        # sticky by design, test_team_scope.py S8).
        _move_to_folder(scn, team_folders["testTeamAChild"])
        after = _sync_all_until_team(scn, "TestTeamScopeAChild")
        assert after.get("teamId") == "TestTeamScopeAChild", (
            f"[sl64 AC1] DocData.teamId not reconciled to the doc's new folder team "
            f"after syncAll: expected TestTeamScopeAChild, got {after.get('teamId')!r}"
        )
        assert _team_scope(scn) == "TestTeamScopeAChild", (
            "[sl64 AC1] Drive teamScope appProperty not corrected to match the new team"
        )

        def _reconciled() -> str | None:
            row = _docdata_row(scn) or {}
            if row.get("teamId") != "TestTeamScopeAChild":
                return f"[sl64 AC1] DocData.teamId={row.get('teamId')!r}, expected TestTeamScopeAChild"
            return None

        scn.expect_callable(
            _reconciled, on=SHEET, tag="[sl64 folder-move reassigns team]", entry_point="syncAll",
        )
        scn.checkpoint(STEP)
    finally:
        scn.close()


# ---------------------------------------------------------------------------
# AC2 — UpdateDoc pending override wins over the folder walk
# ---------------------------------------------------------------------------

def test_syncall_leaves_updatedoc_override_untouched(settings, team_folders, request):
    """Isolates the INTEGRITY PASS's own UpdateDoc-skip check (gts-b6dm AC3),
    distinct from _syncTeamScope's separate, pre-existing UpdateDoc-apply-and-
    clear behavior (test_team_scope.py S3, exercised via a per-doc sync). If
    this doc's syncState were never seeded by a prior syncAll() sweep, THIS
    sweep's own main loop would treat it as never-synced-by-syncAll and
    invoke syncDocument() -> _syncTeamScope() first (applying + clearing the
    override) before the integrity pass even runs — a different, confounding
    code path, not the one gts-b6dm AC3 is about. Running sync_all once
    BEFORE setting the override establishes syncState so the main loop skips
    this unchanged doc on the sweep under test, isolating the integrity
    pass's own skip check."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        _move_to_folder(scn, team_folders["testTeamA"])
        scn.append_paragraph("AI-1: sl64 AC2 UpdateDoc-override action")
        scn.sync()  # DocData.teamId = TestTeamScopeA
        _sync_all_patient(scn)  # seeds syncState so the next sweep's main loop skips this doc

        # Operator sets a pending manual override to a DIFFERENT team than the
        # doc's actual current folder location.
        _set_docdata(scn, syncStatus="UpdateDoc", teamId="TestTeamScopeAChild")
        pre = _docdata_row(scn) or {}
        assert pre.get("syncStatus") == "UpdateDoc" and pre.get("teamId") == "TestTeamScopeAChild", (
            f"[sl64 AC2 pre] set_docdata_row override not applied: {pre!r}"
        )

        # Doc's Drive folder still says testTeamA — if the integrity pass's
        # folder walk won, this would resolve back to TestTeamScopeA. It must
        # not: 'UpdateDoc' is a pending manual override, and it, not the
        # folder walk, wins (mirrors _syncTeamScope's own precedence).
        _sync_all_patient(scn)

        after = _docdata_row(scn) or {}
        assert after.get("teamId") == "TestTeamScopeAChild", (
            f"[sl64 AC2] syncAll's integrity pass overwrote a pending UpdateDoc override: "
            f"expected teamId to stay TestTeamScopeAChild, got {after.get('teamId')!r}"
        )
        assert after.get("syncStatus") == "UpdateDoc", (
            f"[sl64 AC2] syncAll's integrity pass should not touch syncStatus for an "
            f"UpdateDoc row, got {after.get('syncStatus')!r}"
        )

        def _override_preserved() -> str | None:
            row = _docdata_row(scn) or {}
            if row.get("teamId") != "TestTeamScopeAChild":
                return f"[sl64 AC2] override clobbered: teamId={row.get('teamId')!r}"
            return None

        scn.expect_callable(
            _override_preserved, on=SHEET, tag="[sl64 UpdateDoc override wins]", entry_point="syncAll",
        )
        scn.checkpoint(STEP)
    finally:
        scn.close()


# ---------------------------------------------------------------------------
# AC3 — moved out of every team folder clears the team
# ---------------------------------------------------------------------------

def test_syncall_clears_team_when_moved_out_of_all_folders(settings, team_folders, request):
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        _move_to_folder(scn, team_folders["testTeamA"])
        scn.append_paragraph("AI-1: sl64 AC3 moved-out-of-folders action")
        scn.sync()  # DocData.teamId = TestTeamScopeA
        pre = _docdata_row(scn) or {}
        assert pre.get("teamId") == "TestTeamScopeA", (
            f"[sl64 AC3 pre] expected initial teamId=TestTeamScopeA, got {pre.get('teamId')!r}"
        )

        _move_to_folder(scn, team_folders["testTeamNoTeam"])
        after = _sync_all_until_team(scn, "") or {}
        assert after.get("teamId", "") == "", (
            f"[sl64 AC3] DocData.teamId not cleared after moving out of every team "
            f"folder; expected '', got {after.get('teamId')!r}"
        )
        assert _team_scope(scn) == "", (
            "[sl64 AC3] Drive teamScope appProperty not cleared to match"
        )

        def _cleared() -> str | None:
            row = _docdata_row(scn) or {}
            if row.get("teamId", "") != "":
                return f"[sl64 AC3] teamId still set: {row.get('teamId')!r}"
            return None

        scn.expect_callable(
            _cleared, on=SHEET, tag="[sl64 moved-out-of-all-folders clears team]", entry_point="syncAll",
        )
        scn.checkpoint(STEP)
    finally:
        scn.close()


# ---------------------------------------------------------------------------
# AC4 — a transient folder-walk error leaves the existing team unchanged
# ---------------------------------------------------------------------------

def test_syncall_leaves_team_unchanged_on_transient_walk_error(settings, team_folders, request):
    """Forces _walkFolderForTeam to return its own 'could not complete'
    sentinel (false) for this doc only, for one syncAll() call
    (sync_all_force_team_walk_error fixture), rather than relying on a real,
    non-deterministic Drive outage. testTeamADeep is used so the doc is NOT
    directly parented by a TeamData folder (rules out the O(1) fast path),
    forcing the actual _walkFolderForTeam call this fixture patches."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        _move_to_folder(scn, team_folders["testTeamADeep"])
        scn.append_paragraph("AI-1: sl64 AC4 transient-walk-error action")
        scn.sync()  # deep-walk auto-assignment: DocData.teamId = TestTeamScopeA
        pre = _docdata_row(scn) or {}
        assert pre.get("teamId") == "TestTeamScopeA", (
            f"[sl64 AC4 pre] expected initial teamId=TestTeamScopeA via deep walk, "
            f"got {pre.get('teamId')!r}"
        )

        _sync_all_patient(scn, "sync_all_force_team_walk_error")

        after = _docdata_row(scn) or {}
        assert after.get("teamId") == "TestTeamScopeA", (
            f"[sl64 AC4] a forced transient folder-walk error clobbered "
            f"DocData.teamId: expected it to stay TestTeamScopeA (unchanged), "
            f"got {after.get('teamId')!r}"
        )

        def _unchanged() -> str | None:
            row = _docdata_row(scn) or {}
            if row.get("teamId") != "TestTeamScopeA":
                return f"[sl64 AC4] teamId changed on walk error: {row.get('teamId')!r}"
            return None

        scn.expect_callable(
            _unchanged, on=SHEET, tag="[sl64 transient walk error preserves team]", entry_point="syncAll",
        )
        scn.checkpoint(STEP)
    finally:
        scn.close()
