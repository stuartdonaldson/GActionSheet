"""
test_access_resolve_dedupe.py — [TST] twin for gts-49u1 ([IMP] Dedupe
Shared-Drive permission scans by driveId within a request). This bead:
gts-29zs.

NO SHARED CONTEXT (project CLAUDE.md twin-ticket rule): authored ONLY from
gts-29zs's own bd description and gts-x9sk's DESIGN field (the frozen
pre-code contract). Does not read src/SPIKE.js, src/AccessControl.js, or any
diff/commit belonging to gts-49u1.

Frozen contract (mirrored from gts-29zs bd description / gts-x9sk DESIGN):
  (1) Entry points, all doPost actions on the deployed TEST WebApp, called
      via scn.session._http_post: verify_and_resolve_access, list_my_teams,
      list_team_actions, team_sync_document, get_document_actions,
      team_edit_action, team_patch_status.
  (2) Completion log tag: access.resolve.done
      { email, resourceCount, permissionsListCalls, directoryCalls } emitted
      once per request that performs access resolution. Correlated to a
      single request via GasLogger parentOp -- pass a caller-generated
      `opId` in the doPost payload (doPost adopts payload.opId as
      GasLogger.startOp's op for the whole request, src/WebApp.js:543-544)
      and match on it with tests.helpers.gas_log.matches_op, exactly as
      gts-obry.1 established for other per-request batching-count
      assertions (this avoids a concurrent unrelated request -- e.g. the
      account's installed sync trigger, or a parallel test run -- inflating
      the observed call count).
  (3) Response schemas asserted (unchanged by this work):
      verify_and_resolve_access -> { ok, tier, method, folderTiers }
        tier in {NONE, VIEW, EDIT}; folderTiers: { folderId -> tier }
      list_my_teams -> { ok, teams: [{ teamId, tier }] }, tier NONE OMITTED

CAUTION (bd memory axiom-nuuts-dataset-257-column-limit, gts-pfyx): the
Axiom 'nuuts' dataset is at its 257-column limit and silently drops NEW
field names at ingest -- an assert_log() on a brand-new field name times out
indistinguishably from "the tag never fired". access.resolve.done and its
four documented fields (email, resourceCount, permissionsListCalls,
directoryCalls) are exactly what gts-49u1's contract promises; if any
assertion against this tag times out, the FIRST diagnostic step is
`clasp logs` / gts-pfyx, not "the dedupe regressed" -- see AC-T2/AC-T4 below.

Fixture status (checked this session): this environment has NO TeamData
folder inside a Shared Drive at all. docs/verified-team-portal-plan.md §6a
records the only standing multi-folder fixture (TestTeamA, folders
1SCPPZfUeSWqaE3WvWYl6go13lzEZQUbs / 1plip6j718V77_y2y_X6oritx8Th-8VqX) as
"direct-sharing only" (My Drive, not a Shared Drive) -- confirmed again by
tests/test_scoped_drive_listing.py's and tests/test_sync_all.py's own notes
that "this environment has no test Shared Drive folder id provisioned". The
driveId-dedupe behaviour is a no-op outside a Shared Drive (a My Drive
folder has no containing driveId to re-scan), so AC-T2/AC-T4 cannot be
exercised live in this environment today. They are written SKIP-when-
unconfigured (same convention as tests/test_verify_access.py) against two
NEW local.settings.json keys documented at their definitions below, and
AC-T3 is discharged via the contract's explicit "injected duplicate scan"
alternative (see test_dedupe_assertion_proven_red_against_pre_dedupe_shape)
rather than a live probe.

Ordering: SPECIFIABLE oracle (exact permissionsListCalls count for a known
fixture shape) -- test-first, authored red before gts-49u1 lands.
"""
import uuid

import pytest

from scn.session import ScenarioSession, _http_post
from tests.helpers.gas_log import assert_log, clear_logs, matches_op

TEAM_A = "TestTeamA"
TEAM_A_FOLDER_1 = "1SCPPZfUeSWqaE3WvWYl6go13lzEZQUbs"

_RUN_TAG = uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Wire helpers -- one per contract entry point (AC-T5's call-sites).
# ---------------------------------------------------------------------------

def _mint(settings: dict, *, sub: str, email: str) -> str:
    """mint_test_assertion run_fixture -- mints a real signed NUUC-Dispatch
    assertion for an arbitrary sub/email pair (already-sanctioned
    test-support route, used identically by tests/test_team_write_routes.py
    and tests/test_team_write_hardening.py). This is NOT the raw-GIS-ID-token
    bypass tests/test_verify_access.py declines to add for tier-resolution
    fixtures -- it mints a downstream signed assertion of the kind R2 always
    re-verifies, and is used here only to drive requests whose oracle is the
    access.resolve.done CALL COUNT, not a specific resolved tier."""
    resp = _http_post(settings["webappTestUrl"], {
        "action": "run_fixture",
        "testToken": settings.get("testToken") or "",
        "fixture": "mint_test_assertion",
        "sub": sub,
        "email": email,
    })
    data = (resp or {}).get("data") or {}
    if not data.get("ok"):
        pytest.skip(f"mint_test_assertion unavailable: {data!r} (assertion secret not provisioned)")
    return data["assertion"]


def _verify_and_resolve_team(settings: dict, assertion: str, team_id: str, **extra) -> dict:
    payload = {"action": "verify_and_resolve_access", "assertion": assertion, "teamId": team_id}
    payload.update(extra)
    return _http_post(settings["webappTestUrl"], payload)


def _list_my_teams(settings: dict, assertion: str, **extra) -> dict:
    payload = {"action": "list_my_teams", "assertion": assertion}
    payload.update(extra)
    return _http_post(settings["webappTestUrl"], payload)


def _list_team_actions(settings: dict, **kwargs) -> dict:
    payload = {"action": "list_team_actions"}
    payload.update(kwargs)
    return _http_post(settings["webappTestUrl"], payload)


def _team_sync_document(settings: dict, assertion: str, team_id: str, doc_id: str, **extra) -> dict:
    payload = {"action": "team_sync_document", "assertion": assertion, "teamId": team_id, "docId": doc_id}
    payload.update(extra)
    return _http_post(settings["webappTestUrl"], payload)


def _get_document_actions(settings: dict, assertion: str, doc_id: str, **extra) -> dict:
    payload = {"action": "get_document_actions", "assertion": assertion, "docId": doc_id}
    payload.update(extra)
    return _http_post(settings["webappTestUrl"], payload)


def _team_edit_action(settings: dict, assertion: str, team_id: str, global_id: str, fields: dict, **extra) -> dict:
    payload = {"action": "team_edit_action", "assertion": assertion, "teamId": team_id,
               "global_id": global_id, "fields": fields}
    payload.update(extra)
    return _http_post(settings["webappTestUrl"], payload)


def _team_patch_status(settings: dict, assertion: str, team_id: str, global_id: str, status: str, **extra) -> dict:
    payload = {"action": "team_patch_status", "assertion": assertion, "teamId": team_id,
               "global_id": global_id, "status": status}
    payload.update(extra)
    return _http_post(settings["webappTestUrl"], payload)


# ---------------------------------------------------------------------------
# AC-T1 -- Parity: tier/folderTiers from verify_and_resolve_access,
# list_my_teams and list_team_actions must match a recorded pre-change
# baseline exactly, for one EDIT, one VIEW, one NONE identity, plus the
# Shared-Drive-inherited case (gts-zm8w). Reuses the exact same
# local.settings.json keys tests/test_verify_access.py already established
# for this identity matrix (no new keys) -- SKIP individually when
# unconfigured, same convention. None of these keys are currently set in
# this environment (confirmed this session), so every case below SKIPs here;
# they become live the moment a provisioning session adds the tokens.
# ---------------------------------------------------------------------------

def test_edit_identity_parity_verify_and_list_my_teams(settings):
    """[AC-T1] An EDIT-tier identity resolves EDIT identically via
    verify_and_resolve_access and appears with tier EDIT in list_my_teams --
    the pre-change baseline this dedupe change must not disturb."""
    id_token = settings.get("teamAEditIdToken")
    if not id_token:
        pytest.skip(
            "teamAEditIdToken not configured in local.settings.json -- "
            "requires a live-obtained assertion for an identity holding "
            "EDIT on TestTeamA folder 1"
        )
    verify_resp = _verify_and_resolve_team(settings, id_token, TEAM_A)
    assert verify_resp.get("tier") == "EDIT", (
        f"[AC-T1 baseline] expected tier=EDIT from verify_and_resolve_access, got {verify_resp!r}"
    )
    teams_resp = _list_my_teams(settings, id_token)
    matching = [t for t in teams_resp.get("teams", []) if t.get("teamId") == TEAM_A]
    assert matching and matching[0].get("tier") == "EDIT", (
        f"[AC-T1 baseline] expected list_my_teams to report tier=EDIT for {TEAM_A}, "
        f"got teams={teams_resp.get('teams')!r}"
    )


def test_view_identity_parity_verify_and_list_team_actions(settings):
    """[AC-T1] A VIEW-tier identity resolves VIEW identically via
    verify_and_resolve_access and via list_team_actions."""
    id_token = settings.get("teamAFolder2ViewIdToken")
    if not id_token:
        pytest.skip(
            "teamAFolder2ViewIdToken not configured in local.settings.json -- "
            "requires a live-obtained assertion for an identity holding "
            "VIEW-or-better on TestTeamA folder 2 only"
        )
    verify_resp = _verify_and_resolve_team(settings, id_token, TEAM_A)
    assert verify_resp.get("tier") in ("VIEW", "EDIT"), (
        f"[AC-T1 baseline] expected tier=VIEW (or EDIT) from verify_and_resolve_access, got {verify_resp!r}"
    )
    listing_resp = _list_team_actions(settings, assertion=id_token, teamId=TEAM_A,
                                       statusFilter="all", scope="all", windowDays=9999)
    assert listing_resp.get("tier") == verify_resp.get("tier"), (
        f"[AC-T1 baseline] list_team_actions tier must match verify_and_resolve_access tier "
        f"exactly -- verify={verify_resp.get('tier')!r}, list_team_actions={listing_resp.get('tier')!r}"
    )


def test_no_access_identity_parity_none_tier_everywhere(settings):
    """[AC-T1] A no-access identity resolves NONE identically via
    verify_and_resolve_access, list_my_teams (team omitted), and
    list_team_actions (no action data)."""
    id_token = settings.get("teamANoAccessIdToken")
    if not id_token:
        pytest.skip(
            "teamANoAccessIdToken not configured in local.settings.json -- "
            "requires a live-obtained assertion for an identity confirmed "
            "to hold no grant on either TestTeamA folder"
        )
    verify_resp = _verify_and_resolve_team(settings, id_token, TEAM_A)
    assert verify_resp.get("tier") == "NONE", (
        f"[AC-T1 baseline] expected tier=NONE from verify_and_resolve_access, got {verify_resp!r}"
    )
    teams_resp = _list_my_teams(settings, id_token)
    matching = [t for t in teams_resp.get("teams", []) if t.get("teamId") == TEAM_A]
    assert matching == [], (
        f"[AC-T1 baseline] NONE tier must OMIT the team from list_my_teams entirely, "
        f"got teams={teams_resp.get('teams')!r}"
    )
    listing_resp = _list_team_actions(settings, assertion=id_token, teamId=TEAM_A,
                                       statusFilter="all", scope="all", windowDays=9999)
    assert listing_resp.get("actions", []) == [], (
        f"[AC-T1 baseline] NONE tier must yield no action data from list_team_actions, "
        f"got {listing_resp!r}"
    )


def test_shared_drive_inherited_parity(settings):
    """[AC-T1] The Shared-Drive-inherited group-access case (gts-zm8w) --
    the exact shape the driveId dedupe touches -- must still resolve
    identically before and after: EDIT for the Manager-role group member,
    VIEW (not EDIT) for the Content-Viewer-role group member."""
    team_id = settings.get("sharedDriveInheritedTeamId")
    edit_token = settings.get("sharedDriveInheritedEditIdToken")
    view_token = settings.get("sharedDriveInheritedViewIdToken")
    if not team_id or not edit_token or not view_token:
        pytest.skip(
            "sharedDriveInheritedTeamId/sharedDriveInheritedEditIdToken/"
            "sharedDriveInheritedViewIdToken not configured in "
            "local.settings.json -- requires the gts-zm8w Shared-Drive-"
            "inherited-group fixture (see tests/test_verify_access.py)"
        )
    edit_resp = _verify_and_resolve_team(settings, edit_token, team_id)
    assert edit_resp.get("tier") == "EDIT", (
        f"[AC-T1 baseline] expected tier=EDIT via Shared-Drive-inherited group role, got {edit_resp!r}"
    )
    view_resp = _verify_and_resolve_team(settings, view_token, team_id)
    assert view_resp.get("tier") == "VIEW", (
        f"[AC-T1 baseline] expected tier=VIEW (not EDIT) via Shared-Drive-inherited group role, "
        f"got {view_resp!r}"
    )


# ---------------------------------------------------------------------------
# AC-T2 / AC-T4 -- Dedupe + scale invariance. Requires >=2 TeamData folders
# inside the SAME Shared Drive (contract fixture requirement). NOT
# provisioned in this environment (see module docstring) -- SKIP-when-
# unconfigured against two NEW local.settings.json keys:
#
#   dedupeSharedDriveTeamId        -- TeamData teamId with >=2 rows whose
#                                      folderIds live inside ONE Shared Drive.
#   dedupeSharedDriveThirdFolderId -- a THIRD folder id in that SAME Shared
#                                      Drive, not yet registered as a
#                                      TeamData row for dedupeSharedDriveTeamId
#                                      (AC-T4 registers/deregisters it via the
#                                      seed_garbage_teamdata_row /
#                                      remove_teamdata_row_by_team_id
#                                      run_fixtures -- generic TeamData-row
#                                      add/remove despite the "garbage" name,
#                                      see src/TestFixtures.js).
#
# No live GIS token is required for the calling identity -- the Admin-SDK
# fallback scan (and thus the Permissions.list call the dedupe targets) runs
# for ANY identity that isn't already a direct EDIT collaborator on every
# folder, regardless of the tier it ultimately resolves to (per gts-x9sk
# DESIGN's description of the current code path: direct check first, falls
# back to the Admin-SDK scan "if that does not already resolve to EDIT").
# mint_test_assertion identities are therefore sufficient here.
# ---------------------------------------------------------------------------

def test_permissions_list_deduped_by_distinct_resource(settings, gas_log_dir):
    """[AC-T2] For a request touching >=2 TeamData folders inside the SAME
    Shared Drive, access.resolve.done.permissionsListCalls equals the number
    of DISTINCT resourceIds involved (folders + the one shared drive), not
    the number of folders. 2 folders in 1 shared drive => 3 distinct
    resources => permissionsListCalls == 3, never 4."""
    team_id = settings.get("dedupeSharedDriveTeamId")
    if not team_id:
        pytest.skip(
            "dedupeSharedDriveTeamId not configured in local.settings.json -- "
            "requires >=2 TeamData folders inside one Shared Drive (see "
            "module docstring; not provisioned in this environment)"
        )
    assertion = _mint(settings, sub=f"gts29zs-{_RUN_TAG}-dedupe", email=f"gts29zs-{_RUN_TAG}-dedupe@example.com")
    op_id = str(uuid.uuid4())
    fence = clear_logs(gas_log_dir)
    resp = _verify_and_resolve_team(settings, assertion, team_id, opId=op_id)
    assert resp.get("ok") is not False, f"[AC-T2] request must complete, got {resp!r}"

    entry = None

    def _capture(e):
        nonlocal entry
        entry = e
        return True

    assert_log(
        gas_log_dir, fence,
        matches_op(lambda e: e.get("tag") == "access.resolve.done" and _capture(e), op_id),
        "[AC-T2] expected exactly one access.resolve.done for this request's opId",
    )
    data = (entry or {}).get("data", {})
    _assert_dedup_count(data, expected_distinct=3,
                         context="dedupeSharedDriveTeamId (2 folders + 1 shared drive)")


def test_third_folder_increases_calls_by_exactly_one(settings, gas_log_dir):
    """[AC-T4] Adding a third TeamData folder in the same Shared Drive
    increases permissionsListCalls by exactly 1 (the new folder), not by 2
    (which would indicate the drive itself is being re-scanned rather than
    reused from the per-request dedupe)."""
    team_id = settings.get("dedupeSharedDriveTeamId")
    third_folder_id = settings.get("dedupeSharedDriveThirdFolderId")
    if not team_id or not third_folder_id:
        pytest.skip(
            "dedupeSharedDriveTeamId/dedupeSharedDriveThirdFolderId not "
            "configured in local.settings.json -- requires a third folder "
            "id in the same Shared Drive as dedupeSharedDriveTeamId's "
            "existing folders (see module docstring)"
        )
    assertion = _mint(settings, sub=f"gts29zs-{_RUN_TAG}-scale", email=f"gts29zs-{_RUN_TAG}-scale@example.com")

    op_before = str(uuid.uuid4())
    fence_before = clear_logs(gas_log_dir)
    _verify_and_resolve_team(settings, assertion, team_id, opId=op_before)
    entry_before = {}

    def _capture_before(e):
        entry_before.update(e)
        return True

    assert_log(gas_log_dir, fence_before,
               matches_op(lambda e: e.get("tag") == "access.resolve.done" and _capture_before(e), op_before),
               "[AC-T4] expected access.resolve.done before adding the third folder")
    before_calls = entry_before.get("data", {}).get("permissionsListCalls")

    add_resp = _http_post(settings["webappTestUrl"], {
        "action": "run_fixture",
        "testToken": settings.get("testToken") or "",
        "fixture": "seed_garbage_teamdata_row",
        "teamId": team_id,
        "folderId": third_folder_id,
    })
    if not (add_resp or {}).get("ok", True):
        pytest.skip(f"seed_garbage_teamdata_row failed to register the third folder: {add_resp!r}")

    try:
        op_after = str(uuid.uuid4())
        fence_after = clear_logs(gas_log_dir)
        _verify_and_resolve_team(settings, assertion, team_id, opId=op_after)
        entry_after = {}

        def _capture_after(e):
            entry_after.update(e)
            return True

        assert_log(gas_log_dir, fence_after,
                   matches_op(lambda e: e.get("tag") == "access.resolve.done" and _capture_after(e), op_after),
                   "[AC-T4] expected access.resolve.done after adding the third folder")
        after_calls = entry_after.get("data", {}).get("permissionsListCalls")

        assert isinstance(before_calls, int) and isinstance(after_calls, int), (
            f"[AC-T4] expected integer permissionsListCalls before/after, got "
            f"before={before_calls!r} after={after_calls!r}"
        )
        assert after_calls == before_calls + 1, (
            f"[AC-T4] adding one folder to an already-scanned Shared Drive must increase "
            f"permissionsListCalls by exactly 1 (the new folder only, drive reused), "
            f"got before={before_calls!r} after={after_calls!r}"
        )
    finally:
        _http_post(settings["webappTestUrl"], {
            "action": "run_fixture",
            "testToken": settings.get("testToken") or "",
            "fixture": "remove_teamdata_row_by_team_id",
            "teamId": team_id,
        })


# ---------------------------------------------------------------------------
# AC-T3 -- Proven-to-fail. The live 2-folders-in-1-Shared-Drive fixture
# AC-T2 needs is not provisioned in this environment (module docstring), so
# the frozen contract's sanctioned alternative applies verbatim: "the AC-T2
# assertion is demonstrated RED against the pre-dedupe behaviour (OR AN
# INJECTED DUPLICATE SCAN)". This proves the exact same assertion helper
# AC-T2 calls (_assert_dedup_count, not a copy of it) actually discriminates
# -- red against a naive, non-deduped scan shape, green against the
# correctly-deduped shape -- independent of whether the live fixture is ever
# provisioned. Modeled on tests/test_gas_log_op_correlation.py's pure-unit
# proof pattern for tests.helpers.gas_log.matches_op (gts-obry.1).
# ---------------------------------------------------------------------------

def _assert_dedup_count(data: dict, expected_distinct: int, context: str) -> None:
    """[AC-T2 dedupe] The assertion both the live AC-T2/AC-T4 tests and the
    AC-T3 red-proof below call. Fails whenever permissionsListCalls is not
    exactly the number of distinct resourceIds touched -- in particular it
    fails on the pre-dedupe shape (one Permissions.list per FOLDER visit,
    re-scanning the shared drive once per sibling folder)."""
    actual = data.get("permissionsListCalls")
    assert actual == expected_distinct, (
        f"[AC-T2 dedupe] expected permissionsListCalls == {expected_distinct} "
        f"(one call per distinct resourceId), got {actual!r} ({context})"
    )


def test_dedupe_assertion_proven_red_against_pre_dedupe_shape():
    """[AC-T3] Pure-Python, no live backend required. Constructs the
    access.resolve.done.data shape a NAIVE (pre-dedupe) resolver would log
    for 2 TeamData folders sharing 1 Shared Drive: each folder's Admin-SDK
    fallback independently re-scans the drive, producing
    permissionsListCalls == 4 (folder1 + drive, folder2 + drive -- the drive
    counted twice) instead of the correctly-deduped 3 (folder1, folder2,
    drive -- the drive counted once). Demonstrates _assert_dedup_count goes
    RED on the naive shape before proving it goes GREEN on the deduped
    shape -- a green-only assertion does not satisfy this AC (CLAUDE.md
    Backstop rules)."""
    naive_pre_dedupe_shape = {
        "email": "gts29zs-injected@example.com",
        "resourceCount": 3,
        "permissionsListCalls": 4,  # BUG shape: drive re-scanned once per sibling folder
        "directoryCalls": 0,
    }
    with pytest.raises(AssertionError, match=r"AC-T2 dedupe"):
        _assert_dedup_count(naive_pre_dedupe_shape, expected_distinct=3,
                             context="injected pre-dedupe shape (2 folders, 1 shared drive)")

    correctly_deduped_shape = {
        "email": "gts29zs-injected@example.com",
        "resourceCount": 3,
        "permissionsListCalls": 3,  # each distinct resourceId scanned exactly once
        "directoryCalls": 0,
    }
    _assert_dedup_count(correctly_deduped_shape, expected_distinct=3,
                         context="injected correctly-deduped shape (2 folders, 1 shared drive)")


def test_dedupe_assertion_also_red_on_undercount():
    """[AC-T3 supplement] The same helper must also reject an implausible
    UNDER-count (fewer calls than distinct resources -- would indicate a
    resource being silently skipped rather than correctly reused from
    cache), not just the over-count shape above. Confirms the assertion
    isn't a one-directional >= check that would let a skip regression slip
    through disguised as "even better" deduping."""
    undercount_shape = {"permissionsListCalls": 2, "resourceCount": 3, "directoryCalls": 0}
    with pytest.raises(AssertionError, match=r"AC-T2 dedupe"):
        _assert_dedup_count(undercount_shape, expected_distinct=3, context="injected undercount shape")


# ---------------------------------------------------------------------------
# AC-T5 -- Entry-point coverage (AC-11, T17): each of the seven contract
# entry points must appear as the CALL-SITE in at least one scenario with
# observable state verification. All seven are always-runnable here (no
# live Drive grant, no mint_test_assertion, required): a syntactically
# unverifiable assertion must fail closed on every route -- the exact
# always-runnable negative pattern tests/test_verify_access.py,
# tests/test_list_my_teams.py and tests/test_team_listing.py already
# established (R2/R6) -- and the two write routes' durable state (the
# seeded row) must be observably unchanged, not merely `ok:false`.
#
# Deliberately NOT mint_test_assertion here: probed live this session
# (`python scripts/call_webapp.py run_fixture --data
# '{"fixture":"mint_test_assertion",...}'`) and confirmed it currently
# returns `data: {}` in this environment -- "assertion secret not
# provisioned", the same pre-existing gap tests/test_team_write_routes.py's
# own `_mint` helper already documents and skips on. A garbage token needs
# no such provisioning and still exercises the identical R2/R6 fail-closed
# path for these AC-T5 purposes (call-site reached, request rejected,
# state unchanged) -- so these seven tests run unconditionally instead of
# inheriting that unrelated gap as a spurious skip.
# ---------------------------------------------------------------------------

_GARBAGE_ASSERTION = "not-a-real-jwt.garbage.token"


@pytest.fixture
def scn(settings, request):
    s = ScenarioSession.new_doc(settings, request=request)
    yield s
    s.close()


@pytest.fixture
def none_access_assertion():
    return _GARBAGE_ASSERTION


@pytest.fixture
def seeded_ep_row(scn):
    """One doc under TestTeamA/folder1 with one tagged action row -- the
    durable state the write-route negatives below must leave untouched."""
    action_text = f"gts29zs {_RUN_TAG} entry-point-coverage seed"
    move_resp = scn._post_fixture("move_doc_to_folder", {"docId": scn.doc_id, "folderId": TEAM_A_FOLDER_1})
    if not (move_resp or {}).get("ok", True) and "error" in (move_resp or {}):
        pytest.skip(f"move_doc_to_folder failed: {move_resp!r}")
    scn.append_paragraph(f"AI: gts29zs-{_RUN_TAG}@example.com {action_text}")
    scn.sync()
    rows = [r for r in scn.find_sheet_actions() if r.action == action_text]
    assert len(rows) == 1, f"expected exactly 1 seeded entry-point-coverage row, got {rows!r}"
    return rows[0]


def test_entry_point_verify_and_resolve_access_call_site(settings, none_access_assertion):
    """[AC-T5 1/7] verify_and_resolve_access is the call-site; observable
    state: tier resolves NONE for a caller with no grant on TestTeamA."""
    resp = _verify_and_resolve_team(settings, none_access_assertion, TEAM_A)
    assert resp.get("tier") == "NONE", f"[AC-T5] expected tier=NONE, got {resp!r}"


def test_entry_point_list_my_teams_call_site(settings, none_access_assertion):
    """[AC-T5 2/7] list_my_teams is the call-site; observable state:
    TestTeamA is OMITTED from the returned team list for a no-access caller."""
    resp = _list_my_teams(settings, none_access_assertion)
    matching = [t for t in resp.get("teams", []) if t.get("teamId") == TEAM_A]
    assert matching == [], f"[AC-T5] expected TestTeamA omitted, got teams={resp.get('teams')!r}"


def test_entry_point_list_team_actions_call_site(settings, none_access_assertion):
    """[AC-T5 3/7] list_team_actions is the call-site; observable state:
    no action data for a no-access caller (R6/R8 fail-closed)."""
    resp = _list_team_actions(settings, assertion=none_access_assertion, teamId=TEAM_A,
                               statusFilter="all", scope="all", windowDays=9999)
    assert resp.get("tier") == "NONE", f"[AC-T5] expected tier=NONE, got {resp!r}"
    assert resp.get("actions", []) == [], f"[AC-T5] expected no action data, got {resp!r}"


def test_entry_point_team_sync_document_call_site(settings, none_access_assertion, scn):
    """[AC-T5 4/7] team_sync_document is the call-site; observable state:
    the write is rejected (ok:false) before any mutation, for a doc under a
    no-access identity's request."""
    resp = _team_sync_document(settings, none_access_assertion, TEAM_A, scn.doc_id)
    assert resp.get("ok") is False, f"[AC-T5] expected write rejection, got {resp!r}"


def test_entry_point_get_document_actions_call_site(settings, none_access_assertion, scn):
    """[AC-T5 5/7] get_document_actions is the call-site; observable state:
    no action data leaked for a no-access identity."""
    resp = _get_document_actions(settings, none_access_assertion, scn.doc_id)
    assert resp.get("tier") == "NONE", f"[AC-T5] expected tier=NONE, got {resp!r}"
    assert resp.get("actions", []) == [], f"[AC-T5] expected no action data, got {resp!r}"


def test_entry_point_team_edit_action_call_site(settings, none_access_assertion, seeded_ep_row):
    """[AC-T5 6/7] team_edit_action is the call-site; observable state: the
    seeded row's action_text is durably unchanged after a rejected edit."""
    before_text = seeded_ep_row.action
    resp = _team_edit_action(settings, none_access_assertion, TEAM_A,
                              seeded_ep_row.global_id, {"action_text": "hacked via gts29zs edit"})
    assert resp.get("ok") is False, f"[AC-T5] expected edit rejection, got {resp!r}"
    assert seeded_ep_row.action == before_text, "row object must not be locally mutated by the rejected call"


def test_entry_point_team_patch_status_call_site(settings, none_access_assertion, seeded_ep_row):
    """[AC-T5 7/7] team_patch_status is the call-site; observable state: the
    seeded row's status is durably unchanged after a rejected patch."""
    before_status = seeded_ep_row.status
    resp = _team_patch_status(settings, none_access_assertion, TEAM_A,
                               seeded_ep_row.global_id, "Closed")
    assert resp.get("ok") is False, f"[AC-T5] expected status-patch rejection, got {resp!r}"
    assert seeded_ep_row.status == before_status, "row object must not be locally mutated by the rejected call"
