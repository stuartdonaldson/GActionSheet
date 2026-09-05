"""
test_malformed_teamdata_folder.py — bead: gts-pulj

Retroactive coverage (CLAUDE.md "Regression coverage — retroactive path
(Path B)") for gts-pulj: a TeamData row whose folderId is a placeholder like
'-NA-' (not a real Drive resource id) was walked into two guaranteed-to-fail
Drive round-trips per access-resolution request -- Drive.Files.get and
Drive.Permissions.list inside src/SPIKE.js's Admin SDK fallback
(_spikeContainingDriveId / _spikeScanResourceGroupPermissions, called from
_resolveTeamTierForVerifiedIdentity in src/AccessControl.js) -- each logged
as webapp.spike.access.error, the tag scn/session.py::_check_gas_errors
fail-fast-scans for every test in the suite, regardless of whether that test
ever touches access resolution.

Pre-code contract (frozen before this test was written):
  (1) Entry point under test: the folder-tier resolution loop inside
      _resolveTeamTierForVerifiedIdentity (src/AccessControl.js), which
      backs the real 'verify_and_resolve_access' doPost route
      (tests/test_verify_access.py covers that route's signed-assertion
      boundary; a real live GIS-verified identity is not required to
      exercise the folder-tier loop itself, so this file calls the resolver
      directly via a new 'resolve_team_tier_for_email' test-support fixture,
      src/TestFixtures.js -- same pattern as the existing
      'seed_garbage_teamdata_row' / 'get_team_data_rows' fixtures).
  (2) Completion log tags: a skipped malformed folderId logs
      'webapp.team.access.folderIdSkipped' (data: { folderId }) -- a
      distinct, non-.error tag (AC2) -- and MUST NOT log
      'webapp.spike.access.error' for that row.
  (3) Output schema: fixture.resolve_team_tier_for_email's data is
      { teamId, email, tier, method, folderTiers }.

AC under test (gts-pulj):
  1. A TeamData folderId that is not a plausible Drive resource id is
     skipped before any Drive API call is made -- zero Drive.Files.get and
     zero Drive.Permissions.list round-trips for that row.
  2. No webapp.spike.access.error is logged for a skipped malformed
     folderId (a distinct, non-.error tag is logged instead).
  3. A team whose only TeamData folder is malformed resolves tier NONE
     (fail closed, R6) -- never an exception, never a widened tier.
  4. Existing parity: teams with valid (plausibly-formatted) folderIds still
     go through the normal Drive resolution path -- the guard only short-
     circuits genuinely implausible ids.
  5. Proven-to-fail: assertion 1 (via its log-based proxy, assertion 2) is
     demonstrated red against the pre-fix build. Confirmed manually before
     the fix landed: this test's `no webapp.spike.access.error` assertion
     failed against the then-deployed TEST build (2 error events per
     resolving request over the '-NA-' row, matching gts-pulj's live Axiom
     finding of 6 such errors / 72h == 2 per resolving request), and passed
     once src/AccessControl.js's implausible-folderId guard was deployed.

Ordering: specifiable oracle (docs/methodology/oracle-ordering-lever.md) --
the correct log/tier outcome is precisely specifiable before the fix
(zero .error events, tier NONE), so this is a red -> green regression test,
not a Slice review.
"""
import uuid

import pytest

from scn.session import ScenarioSession

GARBAGE_TEAM_ID = "_TEST_GTPULJ_GARBAGE"


def test_malformed_folderid_skipped_no_drive_round_trip_fails_closed(settings, gas_log_dir, request):
    """[gts-pulj AC1/AC2/AC3] A TeamData row with folderId '-NA-' is skipped
    before any Drive API call, logs a distinct non-.error tag instead of
    webapp.spike.access.error, and the team resolves tier NONE (fail
    closed) rather than throwing."""
    if not gas_log_dir:
        pytest.skip("gas_log_dir not configured — log-based assertions require GAS log access")

    from tests.helpers.gas_log import clear_logs, collect_logs, wait_for_log

    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        seed_result = scn._post_fixture("seed_garbage_teamdata_row", {
            "teamId": GARBAGE_TEAM_ID, "folderId": "-NA-",
        })
        assert (seed_result.get("data") or {}).get("folderId") == "-NA-", (
            f"[pulj] seed_garbage_teamdata_row did not write the expected placeholder: "
            f"{seed_result!r}"
        )

        fence = clear_logs(gas_log_dir)
        resolve_result = scn._post_fixture("resolve_team_tier_for_email", {
            "teamId": GARBAGE_TEAM_ID, "email": "nobody-pulj@example.invalid",
        })
        data = resolve_result.get("data") or {}
        assert not resolve_result.get("error"), (
            f"[pulj] resolve_team_tier_for_email raised instead of resolving NONE: {resolve_result!r}"
        )

        # AC3: fail closed -- the team's ONLY folder is malformed, so the
        # whole team resolves NONE, never an exception, never a widened tier.
        assert data.get("tier") == "NONE", (
            f"[pulj] team with only a malformed folderId should resolve tier NONE, got: {data!r}"
        )
        assert (data.get("folderTiers") or {}).get("-NA-") == "NONE", (
            f"[pulj] the malformed folder's own per-folder tier should be NONE, got: {data!r}"
        )

        # Wait for SOME log from this call to land before asserting absence
        # of another tag -- avoids a false-green race against Axiom ingest
        # lag (a bare collect_logs right after a synchronous POST has no
        # such guarantee; wait_for_log tolerates it). Matches EITHER the
        # post-fix skip tag OR the pre-fix .error tag so this wait itself
        # succeeds (and the assertions below get a fair, ingest-settled
        # shot) on both sides of the fix -- the proven-to-fail assertion is
        # the one below, not this wait.
        wait_for_log(
            gas_log_dir,
            lambda e: e.get("tag") in (
                "webapp.team.access.folderIdSkipped", "webapp.spike.access.error",
            ),
            timeout_s=60,
            after=fence,
        )

        # AC1/AC2, and the assertion proven red pre-fix (AC5): ingest for
        # this call is now confirmed landed by the wait_for_log above, so an
        # absence check here is trustworthy, not a race. Pre-fix, the
        # '-NA-' row drove Drive.Files.get + Drive.Permissions.list inside
        # SPIKE.js's Admin SDK fallback, each logging webapp.spike.access.error
        # -- confirmed live via `query_axiom.py --name spike`, 6 events/72h
        # == 2 per resolving request. This assertion fails against that
        # build (non-empty error_events) and passes once the implausible-
        # folderId guard (src/AccessControl.js) skips the row before any
        # Drive call is attempted.
        error_events = collect_logs(
            gas_log_dir,
            lambda e: e.get("tag") == "webapp.spike.access.error",
            after=fence,
        )
        assert not error_events, (
            f"[pulj] expected ZERO webapp.spike.access.error events for a skipped malformed "
            f"folderId (proves no Drive.Files.get / Drive.Permissions.list round-trip was "
            f"attempted) -- this is the assertion proven red against the pre-fix build "
            f"(2 such events per resolving request, confirmed live via Axiom): {error_events!r}"
        )

        skipped_events = collect_logs(
            gas_log_dir,
            lambda e: e.get("tag") == "webapp.team.access.folderIdSkipped"
            and (e.get("data") or {}).get("folderId") == "-NA-",
            after=fence,
        )
        assert skipped_events, (
            "[pulj] expected a webapp.team.access.folderIdSkipped event (distinct, non-.error "
            "tag) recording that the malformed row was skipped but still visible to an operator"
        )
    finally:
        scn._post_fixture("remove_teamdata_row_by_team_id", {"teamId": GARBAGE_TEAM_ID})
        scn.engine.close()


def test_valid_folderid_parity_still_attempts_resolution(settings, gas_log_dir, request):
    """[gts-pulj AC4] A TeamData row whose folderId merely LOOKS like a real
    Drive resource id (passes the plausibility filter) but doesn't resolve
    to anything real is NOT short-circuited by the new guard -- it still
    goes through the normal getAccess/adminSdk resolution path (and
    resolves NONE for the unrelated reason that the id doesn't exist),
    proving the guard is scoped to implausible ids only, not a blanket skip."""
    if not gas_log_dir:
        pytest.skip("gas_log_dir not configured — log-based assertions require GAS log access")

    from tests.helpers.gas_log import clear_logs, collect_logs, wait_for_log

    team_id = "_TEST_GTPULJ_PARITY_" + uuid.uuid4().hex[:8]
    # 33 chars, alphanumeric -- passes _isPlausibleDriveId's length+charset
    # filter but is not a real Drive file (well-formed nonsense id).
    plausible_but_nonexistent_folder_id = "1" + uuid.uuid4().hex + uuid.uuid4().hex[:6]

    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        seed_result = scn._post_fixture("seed_garbage_teamdata_row", {
            "teamId": team_id, "folderId": plausible_but_nonexistent_folder_id,
        })
        assert (seed_result.get("data") or {}).get("folderId") == plausible_but_nonexistent_folder_id

        fence = clear_logs(gas_log_dir)
        resolve_result = scn._post_fixture("resolve_team_tier_for_email", {
            "teamId": team_id, "email": "nobody-pulj-parity@example.invalid",
        })
        data = resolve_result.get("data") or {}
        assert not resolve_result.get("error"), (
            f"[pulj parity] resolve_team_tier_for_email raised for a well-formed-but-nonexistent "
            f"folderId: {resolve_result!r}"
        )
        assert data.get("tier") == "NONE", (
            f"[pulj parity] nonexistent folder should still resolve NONE: {data!r}"
        )

        # A well-formed-but-nonexistent id still reaches DriveApp.getFolderById,
        # which fails with a normal webapp.team.access.error -- wait for it so
        # the absence check below is ingest-settled, not a race (same pattern
        # as the malformed-id test above).
        wait_for_log(
            gas_log_dir,
            lambda e: e.get("tag") == "webapp.team.access.error"
            and (e.get("data") or {}).get("folderId") == plausible_but_nonexistent_folder_id,
            timeout_s=60,
            after=fence,
        )

        skipped_events = collect_logs(
            gas_log_dir,
            lambda e: e.get("tag") == "webapp.team.access.folderIdSkipped"
            and (e.get("data") or {}).get("folderId") == plausible_but_nonexistent_folder_id,
            after=fence,
        )
        assert not skipped_events, (
            f"[pulj parity] a plausibly-formatted folderId must NOT be short-circuited by the "
            f"gts-pulj guard -- got a folderIdSkipped event for it: {skipped_events!r}"
        )
    finally:
        scn._post_fixture("remove_teamdata_row_by_team_id", {"teamId": team_id})
        scn.engine.close()
