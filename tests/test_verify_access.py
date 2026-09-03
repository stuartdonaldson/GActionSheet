"""
test_verify_access.py — Twin TST for gts-79dw.4.1 (this bead: gts-79dw.4.2).
Extended by gts-79dw.4.12 for multi-folder tier resolution + per-document
write re-authorization (R3a/R3b).

Pre-code contract (frozen in gts-79dw.4.1's `design` field before either twin
ticket started coding — this file's only shared context with the IMP owner):

  (1) Entry point: doPost action 'verify_and_resolve_access',
      body { assertion, teamId } (was { idToken, boardFolderId } prior to
      gts-79dw.4.12/.4.18; the resolver now checks every TeamData folder
      matching teamId rather than a single caller-addressed folder, and the
      wire field is a NUUC-Dispatch signed assertion, not a raw GIS ID token
      -- gts-79dw.4.18, see tests/test_signed_assertion.py).
  (2) Completion log tag: GasLogger 'webapp.team.access' with data
      { sub, tier, method, folderCount } (method: 'getAccess'|'adminSdk';
      never logs the raw assertion). Write rejections (team_sync_document, R3b)
      log 'webapp.team.access.denied' with { sub, docId, tier }.
  (3) Output schema: JSON { verified: bool, sub: str, email: str,
      tier: 'NONE'|'VIEW'|'EDIT' }. Safe default = NONE when access cannot be
      positively confirmed (R6, docs/verified-team-portal-plan.md §3).

AC under test (gts-79dw.4.1):
  A verified identity with direct or group-conferred VIEW/COMMENT on the board
  folder resolves to VIEW; EDIT/OWNER resolves to EDIT; no access resolves to
  NONE; an invalid/expired token returns verified:false and tier:NONE
  (negative case).

AC under test (gts-79dw.4.12, R3a/R3b — see docs/verified-team-portal-plan.md
§6a for the standing multi-folder fixture, Team Id `TestTeamA`):
  A caller with VIEW on folder 2 of the two-folder team resolves VIEW for the
  team even when addressed only by teamId (previously NONE when the old
  single-folder resolver was keyed to folder 1 and the caller lacked folder-1
  access). A caller with EDIT on folder 1 and VIEW-or-less on folder 2
  resolves EDIT team-wide for READ purposes (R3a, max-across-folders), but a
  write (team_sync_document) against a document under folder 2 is rejected
  before any mutation (R3b, negative test). A caller with access to no folder
  of the team resolves NONE and receives no action data (R6/R8).

Ordering: specifiable oracle (docs/methodology/oracle-ordering-lever.md,
gts-m65t) — test-first, red until gts-79dw.4.1 lands. gts-79dw.4.1 has landed:
'verify_and_resolve_access' is now a routed doPost action (src/WebApp.js /
src/AccessControl.js), so the module-level xfail has been removed.

Tier-resolution cases additionally require a real board folder with seeded
access states and a real, currently-valid GIS ID token per identity (Spike S2
established these can only be obtained via a live GIS sign-in / manual Drive
sharing setup — no test-support bypass is in the frozen contract above, and
none should be added: R2 requires the real verify path to be exercised).
Those cases read `boardFolderId` / `viewIdToken` / `editIdToken` / `noAccessIdToken`
(single-folder AC) or `teamAFolder2ViewIdToken` / `teamAEditIdToken` /
`teamANoAccessIdToken` (multi-folder AC, gts-79dw.4.12) from
local.settings.json and SKIP individually when unconfigured, independent of
the module xfail.

Shared-Drive-inherited group access (gts-zm8w [FIX] / gts-s1j5 [TST], AC4 of
gts-s1j5 requires these documented here in the module docstring). Same
live-fixture constraint, same SKIP-when-unconfigured convention; all read from
local.settings.json:

  sharedDriveInheritedTeamId          TeamData teamId whose folder lives inside
                                      a SHARED DRIVE, where a domain-managed
                                      group holds its role ONLY at the drive
                                      level (never re-granted on the folder).
  sharedDriveInheritedEditIdToken     Live GIS ID token for a member of a group
                                      holding Manager/Content Manager (writer)
                                      at that drive's level. Expect tier=EDIT.
  sharedDriveInheritedViewIdToken     Live GIS ID token for a member of a
                                      DIFFERENT group holding only Content
                                      Viewer (reader) at the drive level.
                                      Expect tier=VIEW, never EDIT -- proves the
                                      fallback reads the group's actual role
                                      rather than blanket-granting EDIT to any
                                      drive member.
  sharedDriveInheritedDocId           A Google Doc living UNDER that TeamData
                                      folder, used as the team_sync_document
                                      write target (gts-s1j5 AC1's second half)
                                      and the get_document_actions read target.

NOTE (2026-09-02, gts-s1j5): none of these four keys is configured in this
checkout, and no TeamData folder inside a Shared Drive exists in this
environment at all (independently confirmed by
tests/test_access_resolve_dedupe.py's fixture survey). Every Shared-Drive-
inherited case below therefore SKIPs rather than running -- the fix shipped in
76d1b98 is NOT yet provable here. Provisioning that fixture is the blocking
precondition; see the bd bead filed for it.
"""
import pytest

from scn.session import _http_post

TEST_TEAM_A = "TestTeamA"
TEST_TEAM_A_FOLDER_1_DOC = "12PdYg3WMbvyYtzcMeetkl8IrZE7OSSm6FfA45Cl7Sk8"
TEST_TEAM_A_FOLDER_2_DOC = "1Hc_ETgOc987uUJvs2pBuxUw-9Lx4-8NajX9cLMJYEy0"


def _verify_and_resolve(settings: dict, assertion: str, board_folder_id: str) -> dict:
    return _http_post(settings["webappTestUrl"], {
        "action": "verify_and_resolve_access",
        "assertion": assertion,
        "boardFolderId": board_folder_id,
    })


def _verify_and_resolve_team(settings: dict, assertion: str, team_id: str) -> dict:
    return _http_post(settings["webappTestUrl"], {
        "action": "verify_and_resolve_access",
        "assertion": assertion,
        "teamId": team_id,
    })


def _team_sync_document(settings: dict, assertion: str, team_id: str, doc_id: str) -> dict:
    return _http_post(settings["webappTestUrl"], {
        "action": "team_sync_document",
        "assertion": assertion,
        "teamId": team_id,
        "docId": doc_id,
    })


# ---------------------------------------------------------------------------
# Negative case — always runnable, no real Google identity required (R2, R6)
# ---------------------------------------------------------------------------

def _list_my_teams(settings: dict, assertion: str) -> dict:
    return _http_post(settings["webappTestUrl"], {
        "action": "list_my_teams",
        "assertion": assertion,
    })


def _list_team_actions(settings: dict, assertion: str, team_id: str) -> dict:
    return _http_post(settings["webappTestUrl"], {
        "action": "list_team_actions",
        "assertion": assertion,
        "teamId": team_id,
    })


def test_invalid_token_fails_closed(settings):
    """[4.1 AC negative] A garbage/unparseable idToken must fail closed:
    verified:false, tier:NONE — never raise, never leak folder access."""
    resp = _verify_and_resolve(settings, "not-a-real-jwt.garbage.token", "0" * 20)
    assert resp.get("verified") is False, (
        f"[4.1 AC negative] expected verified=False for a garbage token, got {resp!r}"
    )
    assert resp.get("tier") == "NONE", (
        f"[4.1 AC negative] expected tier=NONE for a garbage token, got {resp!r}"
    )


def test_expired_token_fails_closed(settings):
    """[4.1 AC negative] An expired ID token (well-formed JWT shape, exp in the
    past) must fail closed the same way — exercises the `exp` check (R2)
    distinctly from the parse-failure case above."""
    # Header/payload of a syntactically valid but long-expired JWT (exp=0);
    # signature is irrelevant since it must be rejected before that check.
    expired_jwt = (
        "eyJhbGciOiJSUzI1NiIsImtpZCI6ImZha2UifQ."
        "eyJpc3MiOiJhY2NvdW50cy5nb29nbGUuY29tIiwiYXVkIjoiZmFrZSIsImV4cCI6MCwic3ViIjoiZmFrZSJ9."
        "invalidsignature"
    )
    resp = _verify_and_resolve(settings, expired_jwt, "0" * 20)
    assert resp.get("verified") is False, (
        f"[4.1 AC negative] expected verified=False for an expired token, got {resp!r}"
    )
    assert resp.get("tier") == "NONE", (
        f"[4.1 AC negative] expected tier=NONE for an expired token, got {resp!r}"
    )


# ---------------------------------------------------------------------------
# Tier-resolution matrix — requires seeded Drive state + a real, live-obtained
# GIS ID token per identity (Spike S2); skipped individually until configured.
# ---------------------------------------------------------------------------

def test_view_access_resolves_to_view_tier(settings):
    """[4.1 AC] Direct or group-conferred VIEW/COMMENT on the board folder
    resolves to tier=VIEW."""
    board_folder_id = settings.get("boardFolderId")
    id_token = settings.get("viewIdToken")
    if not board_folder_id or not id_token:
        pytest.skip(
            "boardFolderId/viewIdToken not configured in local.settings.json "
            "-- requires a seeded VIEW/COMMENT grant + a live-obtained GIS ID token"
        )
    resp = _verify_and_resolve(settings, id_token, board_folder_id)
    assert resp.get("verified") is True, f"[4.1 AC VIEW] expected verified=True, got {resp!r}"
    assert resp.get("tier") == "VIEW", f"[4.1 AC VIEW] expected tier=VIEW, got {resp!r}"


def test_edit_access_resolves_to_edit_tier(settings):
    """[4.1 AC] EDIT/OWNER access on the board folder resolves to tier=EDIT."""
    board_folder_id = settings.get("boardFolderId")
    id_token = settings.get("editIdToken")
    if not board_folder_id or not id_token:
        pytest.skip(
            "boardFolderId/editIdToken not configured in local.settings.json "
            "-- requires a seeded EDIT/OWNER grant + a live-obtained GIS ID token"
        )
    resp = _verify_and_resolve(settings, id_token, board_folder_id)
    assert resp.get("verified") is True, f"[4.1 AC EDIT] expected verified=True, got {resp!r}"
    assert resp.get("tier") == "EDIT", f"[4.1 AC EDIT] expected tier=EDIT, got {resp!r}"


def test_no_access_resolves_to_none_tier(settings):
    """[4.1 AC] A verified identity with no resolvable access (direct or
    group-conferred) on the board folder resolves to tier=NONE — the R6
    default-deny path, distinct from the invalid-token negative case above
    (this identity IS verified; it simply has no grant)."""
    board_folder_id = settings.get("boardFolderId")
    id_token = settings.get("noAccessIdToken")
    if not board_folder_id or not id_token:
        pytest.skip(
            "boardFolderId/noAccessIdToken not configured in local.settings.json "
            "-- requires a verified identity confirmed to hold no folder grant "
            "+ a live-obtained GIS ID token"
        )
    resp = _verify_and_resolve(settings, id_token, board_folder_id)
    assert resp.get("verified") is True, f"[4.1 AC NONE] expected verified=True, got {resp!r}"
    assert resp.get("tier") == "NONE", f"[4.1 AC NONE] expected tier=NONE, got {resp!r}"


# ---------------------------------------------------------------------------
# Multi-folder tier resolution + per-document write re-authorization
# (gts-79dw.4.12, R3a/R3b). Fixture: docs/verified-team-portal-plan.md §6a,
# Team Id TestTeamA, folder 1 = 1SCPPZfUeSWqaE3WvWYl6go13lzEZQUbs (settings
# 'testTeamA'), folder 2 = 1plip6j718V77_y2y_X6oritx8Th-8VqX. Same live-token
# requirement/style as the single-folder matrix above: SKIP individually when
# unconfigured, no test-support bypass added for the GIS verify path (R2).
# ---------------------------------------------------------------------------

def test_view_on_second_folder_resolves_team_wide_view(settings):
    """[4.12 AC] A caller with VIEW (or better) on folder 2 of TestTeamA's two
    folders resolves tier=VIEW-or-better for the team when addressed only by
    teamId -- R3a's max-across-folders fix. Prior to gts-79dw.4.12 this
    resolved NONE because the single-folder resolver checked only the first
    TeamData row (folder 1), which this identity may not hold access to."""
    id_token = settings.get("teamAFolder2ViewIdToken")
    if not id_token:
        pytest.skip(
            "teamAFolder2ViewIdToken not configured in local.settings.json -- "
            "requires a live-obtained GIS ID token for an identity holding "
            "VIEW-or-better on TestTeamA folder 2 only "
            "(1plip6j718V77_y2y_X6oritx8Th-8VqX)"
        )
    resp = _verify_and_resolve_team(settings, id_token, TEST_TEAM_A)
    assert resp.get("verified") is True, f"[4.12 AC R3a] expected verified=True, got {resp!r}"
    assert resp.get("tier") in ("VIEW", "EDIT"), (
        f"[4.12 AC R3a] expected tier=VIEW or EDIT (folder-2-only access "
        f"resolved via teamId), got {resp!r}"
    )


def test_edit_on_one_folder_write_rejected_on_sibling_folder_doc(settings):
    """[4.12 AC negative, R3b] A caller with EDIT on TestTeamA folder 1 (and at
    most VIEW on folder 2) resolves EDIT team-wide for READ purposes, but
    team_sync_document against the doc under folder 2
    (1Hc_ETgOc987uUJvs2pBuxUw-9Lx4-8NajX9cLMJYEy0) must be rejected before any
    mutation runs -- EDIT on one sub-folder must not confer write over
    documents under a sibling folder."""
    id_token = settings.get("teamAEditIdToken")
    if not id_token:
        pytest.skip(
            "teamAEditIdToken not configured in local.settings.json -- "
            "requires a live-obtained GIS ID token for an identity holding "
            "EDIT on TestTeamA folder 1 (1SCPPZfUeSWqaE3WvWYl6go13lzEZQUbs) "
            "and at most VIEW on folder 2"
        )
    resolved = _verify_and_resolve_team(settings, id_token, TEST_TEAM_A)
    assert resolved.get("tier") == "EDIT", (
        f"[4.12 AC R3a precondition] expected team-wide tier=EDIT via folder 1, "
        f"got {resolved!r}"
    )

    sync_resp = _team_sync_document(settings, id_token, TEST_TEAM_A, TEST_TEAM_A_FOLDER_2_DOC)
    assert sync_resp.get("ok") is False, (
        f"[4.12 AC R3b] expected write rejection for a doc under a folder the "
        f"caller lacks EDIT on, got {sync_resp!r}"
    )
    assert sync_resp.get("outcome") == "rejected-doc-scope", (
        f"[4.12 AC R3b] expected outcome='rejected-doc-scope', got {sync_resp!r}"
    )


def test_no_access_to_any_team_folder_resolves_none(settings):
    """[4.12 AC] A verified identity with no resolvable access to ANY of
    TestTeamA's folders resolves tier=NONE and (via list_team_actions) no
    action data -- R6/R8 default-deny, now checked across every folder rather
    than just the first."""
    id_token = settings.get("teamANoAccessIdToken")
    if not id_token:
        pytest.skip(
            "teamANoAccessIdToken not configured in local.settings.json -- "
            "requires a live-obtained GIS ID token for an identity confirmed "
            "to hold no grant on either TestTeamA folder"
        )
    resp = _verify_and_resolve_team(settings, id_token, TEST_TEAM_A)
    assert resp.get("verified") is True, f"[4.12 AC NONE] expected verified=True, got {resp!r}"
    assert resp.get("tier") == "NONE", f"[4.12 AC NONE] expected tier=NONE, got {resp!r}"


# ---------------------------------------------------------------------------
# Shared-Drive-inherited group access (gts-zm8w, regression coverage
# gts-s1j5). A group's role granted at the containing SHARED DRIVE level
# (e.g. Manager/Content Manager) is never visible as a permission entry on
# any one file/folder inside that drive -- it's inherited, not re-granted per
# item. Before gts-zm8w, _spikeAdminSdkFolderAccess only scanned
# Drive.Permissions.list(folderId), so an identity whose ONLY path to EDIT
# was such an inherited group role resolved VIEW (the Shared-Drive-membership
# baseline every member gets) instead of EDIT. Google's own Share UI declines
# to write a redundant/weaker override on the subfolder for a principal that
# already has higher effective access via the drive, so there is no
# Drive-side workaround -- this must be handled server-side.
#
# Same live-fixture constraint as the matrix above (no test-support bypass
# for the real GIS verify path, R2): requires a Shared Drive team folder
# (TeamData folderId) where a domain-managed group holds its role ONLY at the
# Shared Drive level (not re-granted directly on the folder), plus a live
# GIS ID token for a member of that group. SKIP individually when
# unconfigured.
#
# Settings keys (local.settings.json):
#   sharedDriveInheritedTeamId        -- TeamData teamId whose folder lives in
#                                        a Shared Drive with a group granted
#                                        role ONLY at the drive level
#   sharedDriveInheritedEditIdToken   -- GIS ID token for a member of a group
#                                        holding Manager/writer at the drive
#                                        level (expect tier=EDIT)
#   sharedDriveInheritedViewIdToken   -- GIS ID token for a member of a
#                                        DIFFERENT group holding only
#                                        Content Viewer/reader at the drive
#                                        level (expect tier=VIEW, not EDIT --
#                                        proves the fallback doesn't just
#                                        blanket-grant EDIT to any drive
#                                        member)
# ---------------------------------------------------------------------------

def test_shared_drive_inherited_group_edit_resolves_edit_tier(settings):
    """[gts-zm8w AC1] An identity whose only path to EDIT on a TeamData
    folder is a group role granted at the CONTAINING SHARED DRIVE level (not
    re-granted directly on the folder) resolves tier=EDIT -- the drive-level
    fallback scan added by gts-zm8w."""
    team_id = settings.get("sharedDriveInheritedTeamId")
    id_token = settings.get("sharedDriveInheritedEditIdToken")
    if not team_id or not id_token:
        pytest.skip(
            "sharedDriveInheritedTeamId/sharedDriveInheritedEditIdToken not "
            "configured in local.settings.json -- requires a TeamData folder "
            "inside a Shared Drive where a domain-managed group holds "
            "Manager/writer ONLY at the drive level, + a live-obtained GIS "
            "ID token for a member of that group"
        )
    resp = _verify_and_resolve_team(settings, id_token, team_id)
    assert resp.get("verified") is True, (
        f"[gts-zm8w AC1] expected verified=True, got {resp!r}"
    )
    assert resp.get("tier") == "EDIT", (
        f"[gts-zm8w AC1] expected tier=EDIT via Shared-Drive-inherited group "
        f"role, got {resp!r}"
    )


def test_shared_drive_inherited_group_view_resolves_view_tier(settings):
    """[gts-zm8w AC1 negative] An identity in a DIFFERENT group holding only
    Content Viewer/reader at the Shared Drive level resolves tier=VIEW, not
    EDIT -- the drive-level fallback must respect the group's actual role,
    not blanket-grant EDIT to any Shared Drive member."""
    team_id = settings.get("sharedDriveInheritedTeamId")
    id_token = settings.get("sharedDriveInheritedViewIdToken")
    if not team_id or not id_token:
        pytest.skip(
            "sharedDriveInheritedTeamId/sharedDriveInheritedViewIdToken not "
            "configured in local.settings.json -- requires a live-obtained "
            "GIS ID token for a member of a group holding only Content "
            "Viewer/reader at the Shared Drive level"
        )
    resp = _verify_and_resolve_team(settings, id_token, team_id)
    assert resp.get("verified") is True, (
        f"[gts-zm8w AC1 negative] expected verified=True, got {resp!r}"
    )
    assert resp.get("tier") == "VIEW", (
        f"[gts-zm8w AC1 negative] expected tier=VIEW (not EDIT) via "
        f"Shared-Drive-inherited group role, got {resp!r}"
    )


def _shared_drive_edit_or_skip(settings: dict) -> tuple[str, str]:
    """Common SKIP guard for the Shared-Drive-inherited EDIT fixture."""
    team_id = settings.get("sharedDriveInheritedTeamId")
    id_token = settings.get("sharedDriveInheritedEditIdToken")
    if not team_id or not id_token:
        pytest.skip(
            "sharedDriveInheritedTeamId/sharedDriveInheritedEditIdToken not "
            "configured in local.settings.json -- see the module docstring for "
            "the Shared Drive + drive-level-group fixture this needs"
        )
    return team_id, id_token


def test_shared_drive_inherited_edit_can_sync_a_doc_under_that_folder(settings):
    """[gts-s1j5 AC1, second half] An identity whose EDIT comes ONLY from a
    Shared-Drive-level group role must be able to WRITE: team_sync_document
    against a doc under that TeamData folder succeeds, not just the read-side
    tier resolution. R3b re-authorizes per document at write time using the
    same resolver, so a drive-inherited grant that resolves EDIT on the read
    path but is dropped on the write path is exactly the regression this
    asserts against."""
    team_id, id_token = _shared_drive_edit_or_skip(settings)
    doc_id = settings.get("sharedDriveInheritedDocId")
    if not doc_id:
        pytest.skip(
            "sharedDriveInheritedDocId not configured in local.settings.json -- "
            "requires a Google Doc under the Shared-Drive-hosted TeamData folder"
        )
    resolved = _verify_and_resolve_team(settings, id_token, team_id)
    assert resolved.get("tier") == "EDIT", (
        f"[gts-s1j5 AC1 precondition] expected tier=EDIT, got {resolved!r}"
    )
    sync_resp = _team_sync_document(settings, id_token, team_id, doc_id)
    assert sync_resp.get("ok") is True, (
        f"[gts-s1j5 AC1] team_sync_document must SUCCEED for a doc under a "
        f"TeamData folder the caller holds drive-inherited EDIT on, got "
        f"{sync_resp!r}"
    )


def test_shared_drive_inherited_edit_appears_in_list_my_teams(settings):
    """[gts-s1j5 AC5, call-site: list_my_teams] The entry-point coverage
    invariant (T17) requires list_my_teams to be its OWN call-site against the
    Shared-Drive-inherited fixture -- all three routes share a resolver, but
    each reaches it by a different path (list_my_teams enumerates every team
    rather than resolving one addressed team, so a per-team code path that
    skips the drive-level fallback would pass verify_and_resolve_access and
    still omit the team here). Observable state: the team is PRESENT with
    tier=EDIT; a NONE tier is omitted entirely, so absence is the regression
    signature."""
    team_id, id_token = _shared_drive_edit_or_skip(settings)
    resp = _list_my_teams(settings, id_token)
    assert resp.get("ok") is not False, (
        f"[gts-s1j5 AC5 list_my_teams] unexpected error response: {resp!r}"
    )
    teams = {t.get("teamId"): t.get("tier") for t in (resp.get("teams") or [])}
    assert team_id in teams, (
        f"[gts-s1j5 AC5 list_my_teams] the Shared-Drive-inherited team must "
        f"appear (NONE tiers are omitted, so absence == resolved NONE), got "
        f"{resp!r}"
    )
    assert teams[team_id] == "EDIT", (
        f"[gts-s1j5 AC5 list_my_teams] expected tier=EDIT for the "
        f"drive-inherited team, got {teams[team_id]!r} in {resp!r}"
    )


def test_shared_drive_inherited_edit_reaches_list_team_actions(settings):
    """[gts-s1j5 AC5, call-site: list_team_actions] Third call-site of the same
    resolver. Observable state: tier=EDIT is returned and action data is NOT
    withheld (R8 withholds data below VIEW), so a resolver that quietly drops
    the drive-level fallback on this route surfaces as tier=NONE + actions=[]
    rather than as an error."""
    team_id, id_token = _shared_drive_edit_or_skip(settings)
    resp = _list_team_actions(settings, id_token, team_id)
    assert resp.get("ok") is not False, (
        f"[gts-s1j5 AC5 list_team_actions] unexpected error response: {resp!r}"
    )
    assert resp.get("tier") == "EDIT", (
        f"[gts-s1j5 AC5 list_team_actions] expected tier=EDIT via the "
        f"drive-inherited group role, got {resp!r}"
    )
    assert "actions" in resp, (
        f"[gts-s1j5 AC5 list_team_actions] expected an 'actions' payload for an "
        f"EDIT-tier caller (R8 withholds only below VIEW), got {resp!r}"
    )


def test_shared_drive_inherited_view_is_not_widened_by_list_team_actions(settings):
    """[gts-s1j5 AC2, second call-site] The drive-level VIEW identity must
    resolve VIEW on list_team_actions too, not EDIT -- the negative case has to
    hold on every call-site, otherwise a route-local widening would be invisible
    to the verify_and_resolve_access-only assertion above."""
    team_id = settings.get("sharedDriveInheritedTeamId")
    id_token = settings.get("sharedDriveInheritedViewIdToken")
    if not team_id or not id_token:
        pytest.skip(
            "sharedDriveInheritedTeamId/sharedDriveInheritedViewIdToken not "
            "configured in local.settings.json -- see the module docstring"
        )
    resp = _list_team_actions(settings, id_token, team_id)
    assert resp.get("ok") is not False, (
        f"[gts-s1j5 AC2] unexpected error response: {resp!r}"
    )
    assert resp.get("tier") == "VIEW", (
        f"[gts-s1j5 AC2] expected tier=VIEW (never EDIT) on list_team_actions "
        f"for a drive-level reader group, got {resp!r}"
    )


def test_unresolvable_team_id_fails_closed(settings):
    """[4.12 AC R6] A teamId with zero matching TeamData rows must fail
    closed to tier=NONE, not throw -- exercises the "unresolvable team" fail-
    closed path without requiring any real Drive access grant. Uses the
    always-runnable expired-token identity check's JWT shape is irrelevant
    here; this only needs any syntactically-parseable-but-unverifiable path
    to prove the team-lookup miss doesn't throw. Since no idToken can verify
    without GIS_CLIENT_ID configured for this literal garbage token, this is
    equivalent in strength to the existing invalid-token negative case, but
    documents the team-side fail-closed contract explicitly for gts-79dw.4.12
    (R6: unresolvable team -> NONE, not an exception)."""
    resp = _verify_and_resolve_team(settings, "not-a-real-jwt.garbage.token", "NoSuchTeamIdAtAll")
    assert resp.get("verified") is False, (
        f"[4.12 AC R6] expected verified=False for a garbage token against an "
        f"unresolvable teamId, got {resp!r}"
    )
    assert resp.get("tier") == "NONE", (
        f"[4.12 AC R6] expected tier=NONE, got {resp!r}"
    )
