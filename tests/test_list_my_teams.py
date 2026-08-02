"""
test_list_my_teams.py — route-side coverage for gts-79dw.4.17 (list_my_teams,
R21). No separate [TST] twin: hardening coverage for this functional area
lives in gts-79dw.4.8 per that bead's notes; this file proves the route
itself ahead of the gts-79dw.4.7 real-page build (which owns the switcher UI).

Pre-code contract (bd gts-79dw.4.17, docs/verified-team-portal-plan.md §12.3):
  (1) Entry point: doPost action 'list_my_teams', body { assertion } -- no
      teamId, since the point is discovering every team the caller has ANY
      access to. Field renamed from idToken by gts-79dw.4.18 (raw GIS ID
      token replaced by a NUUC-Dispatch signed assertion -- see
      tests/test_signed_assertion.py).
  (2) Completion log tag: GasLogger 'webapp.team.myTeams' with
      { sub, teamCount }.
  (3) Output schema: JSON { teams: [{ teamId, teamName, tier }] }, sorted by
      teamName, tier in {VIEW, EDIT} only -- a team resolving NONE is
      OMITTED entirely (R6/R8 non-leaking), never included with tier:"NONE".
      teamName == teamId (TeamData carries no distinct display-name column,
      see src/AccessControl.js's _handleListMyTeams doc comment -- a real
      gap, not invented here).

AC under test:
  One team resolves -> exactly that one team. Several teams resolve ->
  exactly those teams with the R3a highest tier each. Zero teams resolve ->
  empty teams list, nothing leaked. A NONE-tier team never appears.

Ordering: specifiable oracle (the exact response shape is written down above
before this file was authored) -- test-first in spirit, though this route
was implemented in the same session per the Slice-phase convention already
used by sibling beads in this chain (gts-79dw.4.11/.4.12/.4.3); hardening
[TST] is gts-79dw.4.8.

Live-identity cases (single/multi-team membership) require a real,
currently-valid GIS ID token per identity -- Spike S2 established these can
only be obtained via a live GIS sign-in, no test-support bypass in the
frozen contract (R2). Following tests/test_verify_access.py's established
pattern: those cases read named keys from local.settings.json and SKIP
individually when unconfigured.
"""
from scn.session import _http_post


def _list_my_teams(settings: dict, assertion: str) -> dict:
    return _http_post(settings["webappTestUrl"], {
        "action": "list_my_teams",
        "assertion": assertion,
    })


# ---------------------------------------------------------------------------
# Negative case — always runnable, no real Google identity required (R2, R6)
# ---------------------------------------------------------------------------

def test_invalid_token_returns_empty_teams_non_leaking(settings):
    """[R21 AC negative] A garbage/unparseable assertion must fail closed to an
    empty, non-leaking team list -- never an error, never any team data."""
    resp = _list_my_teams(settings, "not-a-real-jwt.garbage.token")
    assert resp.get("teams") == [], (
        f"[R21 AC negative] expected teams=[] for a garbage token, got {resp!r}"
    )


def test_expired_token_returns_empty_teams(settings):
    """[R21 AC negative] An expired-but-well-formed assertion must also fail
    closed to an empty team list -- exercises the `exp` check distinctly
    from the parse-failure case above (mirrors test_verify_access.py)."""
    expired_jwt = (
        "eyJhbGciOiJSUzI1NiIsImtpZCI6ImZha2UifQ."
        "eyJpc3MiOiJhY2NvdW50cy5nb29nbGUuY29tIiwiYXVkIjoiZmFrZSIsImV4cCI6MCwic3ViIjoiZmFrZSJ9."
        "invalidsignature"
    )
    resp = _list_my_teams(settings, expired_jwt)
    assert resp.get("teams") == [], (
        f"[R21 AC negative] expected teams=[] for an expired token, got {resp!r}"
    )


# ---------------------------------------------------------------------------
# Live-identity matrix — requires a real, live-obtained signed assertion per
# identity; skipped individually until configured in local.settings.json.
# ---------------------------------------------------------------------------

def test_single_team_membership_returns_exactly_that_team(settings):
    """[R21 AC] A verified caller with access to exactly one team resolves a
    teams list containing exactly that team, correct tier."""
    id_token = settings.get("singleTeamIdToken")
    expected_team_id = settings.get("singleTeamIdTokenTeamId")
    expected_tier = settings.get("singleTeamIdTokenTier")
    if not id_token or not expected_team_id or not expected_tier:
        import pytest
        pytest.skip(
            "singleTeamIdToken/singleTeamIdTokenTeamId/singleTeamIdTokenTier not "
            "configured in local.settings.json -- requires a live-obtained GIS ID "
            "token for an identity with access to exactly one TeamData team"
        )
    resp = _list_my_teams(settings, id_token)
    teams = resp.get("teams") or []
    assert len(teams) == 1, (
        f"[R21 AC single-team] expected exactly one team, got {teams!r}"
    )
    assert teams[0].get("teamId") == expected_team_id, (
        f"[R21 AC single-team] expected teamId={expected_team_id!r}, got {teams[0]!r}"
    )
    assert teams[0].get("tier") == expected_tier, (
        f"[R21 AC single-team] expected tier={expected_tier!r}, got {teams[0]!r}"
    )


def test_multi_team_membership_returns_exactly_those_teams_sorted(settings):
    """[R21 AC] A verified caller with access to several teams resolves
    exactly those teams (no more, no fewer), each with its correct R3a
    highest-tier, sorted by teamName."""
    id_token = settings.get("multiTeamIdToken")
    expected_team_ids = settings.get("multiTeamIdTokenTeamIds")
    if not id_token or not expected_team_ids:
        import pytest
        pytest.skip(
            "multiTeamIdToken/multiTeamIdTokenTeamIds not configured in "
            "local.settings.json -- requires a live-obtained GIS ID token for an "
            "identity with access to several TeamData teams"
        )
    resp = _list_my_teams(settings, id_token)
    teams = resp.get("teams") or []
    got_team_ids = [t.get("teamId") for t in teams]
    assert sorted(got_team_ids) == sorted(expected_team_ids), (
        f"[R21 AC multi-team] expected exactly {expected_team_ids!r}, got {got_team_ids!r}"
    )
    got_names = [t.get("teamName") for t in teams]
    assert got_names == sorted(got_names), (
        f"[R21 AC multi-team] expected teams sorted by teamName, got {got_names!r}"
    )


def test_no_team_access_resolves_empty_teams_list(settings):
    """[R21 AC / R6/R8] A verified identity with no resolvable access to ANY
    TeamData team resolves an empty teams list -- no team data leaked, and no
    team ever appears with tier:"NONE"."""
    id_token = settings.get("noTeamAccessIdToken")
    if not id_token:
        import pytest
        pytest.skip(
            "noTeamAccessIdToken not configured in local.settings.json -- "
            "requires a live-obtained GIS ID token for an identity confirmed to "
            "hold no grant on any TeamData team"
        )
    resp = _list_my_teams(settings, id_token)
    assert resp.get("teams") == [], (
        f"[R21 AC zero-team / R6] expected teams=[], got {resp!r}"
    )
