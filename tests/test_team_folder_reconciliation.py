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

Batched (gts-ir1f, 2026-08-06): AC1-AC4 previously ran as 4 independent
tests, each driving its own full syncAll() sweep against the shared
backlog spreadsheet (syncAll() sweeps ALL docs regardless of which doc's
scn session calls it — testDocId only scopes fixture setup, not the sweep
itself, per src/TestWebApp.js::_handleRunFixture). Batched into ONE test:
4 independent docs set up, then exactly 2 shared syncAll() sweeps (a seed
sweep + a final verification sweep, both retried only for Drive
eventual-consistency lag) instead of up to ~11 sweeps across the 4
original tests. See plan-context.md "Test execution convention — batch
scenario setups per live syncAll() sweep" for the general shape and the
"when NOT to batch" exceptions this design respects (AC2's own two-sweep
dependency is preserved as the batch's seed+final split, not force-fit
into one sweep).
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


def _sync_all_batch_until(scn, checks, fixture_name="sync_all", extra=None,
                           attempts=4, delay_s=8):
    """Batched analogue of _sync_all_until_team (gts-ir1f).

    Runs ONE shared syncAll()-driving fixture call (via `scn`, but the
    sweep itself covers every doc in the backlog, not just `scn`'s), then
    evaluates every scenario's zero-arg `checks` callable (None = satisfied,
    else a failure string, same contract as scn.expect_callable's CALLABLE
    kind). Retries the SAME shared sweep — not a per-scenario sweep — only
    while eventual Drive-index-consistency lag leaves any check
    unsatisfied, so N independent scenarios still share one sweep per
    attempt instead of each polling independently. Returns the list of
    still-failing check messages (empty = all satisfied).
    """
    failures = []
    for attempt in range(attempts):
        _sync_all_patient(scn, fixture_name, extra=extra)
        failures = [msg for msg in (check() for check in checks) if msg]
        if not failures:
            return failures
        if attempt < attempts - 1:
            time.sleep(delay_s)
    return failures


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
# AC1-AC4 batched — see module docstring for the retrofit shape (gts-ir1f)
# ---------------------------------------------------------------------------

def test_syncall_team_reconciliation_batch(settings, team_folders, request):
    """Batches AC1 (folder-move reassigns team), AC2 (UpdateDoc override
    wins over the folder walk), AC3 (moved out of every team folder clears
    the team), and AC4 (a transient folder-walk error leaves the existing
    team unchanged) behind ONE seed syncAll() sweep + ONE final syncAll()
    sweep, instead of each scenario driving its own sweep(s)."""
    sessions = []
    try:
        # --- Setup: 4 independent docs, no shared syncAll yet ---------------
        ac1 = ScenarioSession.new_doc(settings, request=request)
        sessions.append(ac1)
        _move_to_folder(ac1, team_folders["testTeamA"])
        ac1.append_paragraph("AI-1: sl64 AC1 folder-move action")
        ac1.sync()  # first-pass auto-assignment: DocData.teamId = TestTeamScopeA
        pre1 = _docdata_row(ac1) or {}
        assert pre1.get("teamId") == "TestTeamScopeA", (
            f"[sl64 AC1 pre] expected initial teamId=TestTeamScopeA, got {pre1.get('teamId')!r}"
        )

        ac2 = ScenarioSession.new_doc(settings, request=request)
        sessions.append(ac2)
        _move_to_folder(ac2, team_folders["testTeamA"])
        ac2.append_paragraph("AI-1: sl64 AC2 UpdateDoc-override action")
        ac2.sync()  # DocData.teamId = TestTeamScopeA

        ac3 = ScenarioSession.new_doc(settings, request=request)
        sessions.append(ac3)
        _move_to_folder(ac3, team_folders["testTeamA"])
        ac3.append_paragraph("AI-1: sl64 AC3 moved-out-of-folders action")
        ac3.sync()  # DocData.teamId = TestTeamScopeA
        pre3 = _docdata_row(ac3) or {}
        assert pre3.get("teamId") == "TestTeamScopeA", (
            f"[sl64 AC3 pre] expected initial teamId=TestTeamScopeA, got {pre3.get('teamId')!r}"
        )

        # testTeamADeep so the doc is NOT directly parented by a TeamData
        # folder (rules out the O(1) fast path), forcing the actual
        # _walkFolderForTeam call the AC4 fixture below patches.
        ac4 = ScenarioSession.new_doc(settings, request=request)
        sessions.append(ac4)
        _move_to_folder(ac4, team_folders["testTeamADeep"])
        ac4.append_paragraph("AI-1: sl64 AC4 transient-walk-error action")
        ac4.sync()  # deep-walk auto-assignment: DocData.teamId = TestTeamScopeA
        pre4 = _docdata_row(ac4) or {}
        assert pre4.get("teamId") == "TestTeamScopeA", (
            f"[sl64 AC4 pre] expected initial teamId=TestTeamScopeA via deep walk, "
            f"got {pre4.get('teamId')!r}"
        )

        # --- Shared SEED sweep -----------------------------------------------
        # ONE syncAll() seeds syncState for every doc in the backlog so AC2's
        # UpdateDoc-skip check below isolates the integrity pass's own skip
        # logic (see original AC2 docstring) rather than confounding with the
        # main loop's never-synced-by-syncAll path. AC1/AC3/AC4 haven't moved
        # to their post-move location yet, so this sweep is a no-op
        # reconciliation for them (same team, no observable change).
        _sync_all_patient(ac1)

        # --- Post-seed mutation: each doc moves to its "under test" state ---
        _move_to_folder(ac1, team_folders["testTeamAChild"])  # different team's folder

        _set_docdata(ac2, syncStatus="UpdateDoc", teamId="TestTeamScopeAChild")
        pre2 = _docdata_row(ac2) or {}
        assert pre2.get("syncStatus") == "UpdateDoc" and pre2.get("teamId") == "TestTeamScopeAChild", (
            f"[sl64 AC2 pre] set_docdata_row override not applied: {pre2!r}"
        )

        _move_to_folder(ac3, team_folders["testTeamNoTeam"])  # out of every team folder
        # AC4: no further per-doc mutation — the walk-error is forced by the
        # fixture below, for this doc only, during the shared final sweep.

        # --- Shared FINAL sweep ------------------------------------------------
        # ONE syncAll() (retried only for Drive index lag) reconciles AC1 and
        # AC3, leaves AC2's pending override untouched, and forces AC4's walk
        # to fail — all in the same sweep. sync_all_force_team_walk_error only
        # intercepts the walk for ac4.doc_id (src/TestFixtures.js ~line 2737);
        # every other doc in the same sweep walks for real.
        checks = [
            lambda: (
                None if (_docdata_row(ac1) or {}).get("teamId") == "TestTeamScopeAChild"
                else f"[sl64 AC1] teamId={(_docdata_row(ac1) or {}).get('teamId')!r}, expected TestTeamScopeAChild"
            ),
            lambda: (
                None if (_docdata_row(ac3) or {}).get("teamId", "") == ""
                else f"[sl64 AC3] teamId still set: {(_docdata_row(ac3) or {}).get('teamId')!r}"
            ),
        ]
        failures = _sync_all_batch_until(
            ac4, checks, "sync_all_force_team_walk_error", extra={"docId": ac4.doc_id},
        )
        assert not failures, "; ".join(failures)

        # --- AC1: folder move reassigns team via syncAll ---
        after1 = _docdata_row(ac1) or {}
        assert after1.get("teamId") == "TestTeamScopeAChild", (
            f"[sl64 AC1] DocData.teamId not reconciled to the doc's new folder team "
            f"after syncAll: expected TestTeamScopeAChild, got {after1.get('teamId')!r}"
        )
        assert _team_scope(ac1) == "TestTeamScopeAChild", (
            "[sl64 AC1] Drive teamScope appProperty not corrected to match the new team"
        )

        # --- AC2: UpdateDoc pending override wins over the folder walk ---
        after2 = _docdata_row(ac2) or {}
        assert after2.get("teamId") == "TestTeamScopeAChild", (
            f"[sl64 AC2] syncAll's integrity pass overwrote a pending UpdateDoc override: "
            f"expected teamId to stay TestTeamScopeAChild, got {after2.get('teamId')!r}"
        )
        assert after2.get("syncStatus") == "UpdateDoc", (
            f"[sl64 AC2] syncAll's integrity pass should not touch syncStatus for an "
            f"UpdateDoc row, got {after2.get('syncStatus')!r}"
        )

        # --- AC3: moved out of every team folder clears the team ---
        after3 = _docdata_row(ac3) or {}
        assert after3.get("teamId", "") == "", (
            f"[sl64 AC3] DocData.teamId not cleared after moving out of every team "
            f"folder; expected '', got {after3.get('teamId')!r}"
        )
        assert _team_scope(ac3) == "", (
            "[sl64 AC3] Drive teamScope appProperty not cleared to match"
        )

        # --- AC4: transient folder-walk error leaves the existing team unchanged ---
        after4 = _docdata_row(ac4) or {}
        assert after4.get("teamId") == "TestTeamScopeA", (
            f"[sl64 AC4] a forced transient folder-walk error clobbered "
            f"DocData.teamId: expected it to stay TestTeamScopeA (unchanged), "
            f"got {after4.get('teamId')!r}"
        )

        # --- Durability + entry-point tagging (T1/T17/T24), one per scenario ---
        def _ac1_reconciled():
            row = _docdata_row(ac1) or {}
            if row.get("teamId") != "TestTeamScopeAChild":
                return f"[sl64 AC1] DocData.teamId={row.get('teamId')!r}, expected TestTeamScopeAChild"
            return None

        def _ac2_preserved():
            row = _docdata_row(ac2) or {}
            if row.get("teamId") != "TestTeamScopeAChild":
                return f"[sl64 AC2] override clobbered: teamId={row.get('teamId')!r}"
            return None

        def _ac3_cleared():
            row = _docdata_row(ac3) or {}
            if row.get("teamId", "") != "":
                return f"[sl64 AC3] teamId still set: {row.get('teamId')!r}"
            return None

        def _ac4_unchanged():
            row = _docdata_row(ac4) or {}
            if row.get("teamId") != "TestTeamScopeA":
                return f"[sl64 AC4] teamId changed on walk error: {row.get('teamId')!r}"
            return None

        ac1.expect_callable(
            _ac1_reconciled, on=SHEET, tag="[sl64 folder-move reassigns team]", entry_point="syncAll",
        )
        ac1.checkpoint(STEP)
        ac2.expect_callable(
            _ac2_preserved, on=SHEET, tag="[sl64 UpdateDoc override wins]", entry_point="syncAll",
        )
        ac2.checkpoint(STEP)
        ac3.expect_callable(
            _ac3_cleared, on=SHEET, tag="[sl64 moved-out-of-all-folders clears team]", entry_point="syncAll",
        )
        ac3.checkpoint(STEP)
        ac4.expect_callable(
            _ac4_unchanged, on=SHEET, tag="[sl64 transient walk error preserves team]", entry_point="syncAll",
        )
        ac4.checkpoint(STEP)
    finally:
        for scn in sessions:
            scn.close()
