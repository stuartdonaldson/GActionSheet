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
