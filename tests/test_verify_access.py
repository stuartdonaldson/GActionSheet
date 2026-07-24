"""
test_verify_access.py — Twin TST for gts-79dw.4.1 (this bead: gts-79dw.4.2).

Pre-code contract (frozen in gts-79dw.4.1's `design` field before either twin
ticket started coding — this file's only shared context with the IMP owner):

  (1) Entry point: doPost action 'verify_and_resolve_access',
      body { idToken, boardFolderId }.
  (2) Completion log tag: GasLogger 'webapp.board.access' with data
      { sub, tier, method } (method: 'getAccess'|'adminSdk'; never logs the
      raw idToken).
  (3) Output schema: JSON { verified: bool, sub: str, email: str,
      tier: 'NONE'|'VIEW'|'EDIT' }. Safe default = NONE when access cannot be
      positively confirmed (R6, docs/verified-board-portal-plan.md §3).

AC under test (gts-79dw.4.1):
  A verified identity with direct or group-conferred VIEW/COMMENT on the board
  folder resolves to VIEW; EDIT/OWNER resolves to EDIT; no access resolves to
  NONE; an invalid/expired token returns verified:false and tier:NONE
  (negative case).

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
from local.settings.json and SKIP individually when unconfigured, independent
of the module xfail.
"""
import pytest

from scn.session import _http_post


def _verify_and_resolve(settings: dict, id_token: str, board_folder_id: str) -> dict:
    return _http_post(settings["webappTestUrl"], {
        "action": "verify_and_resolve_access",
        "idToken": id_token,
        "boardFolderId": board_folder_id,
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
