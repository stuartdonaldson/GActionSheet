"""
test_signed_assertion.py — regression coverage for gts-79dw.4.18's assertion
verifier (_verifySignedAssertion, src/AccessControl.js), which replaced the
raw-GIS-tokeninfo verify path (_verifyGisIdToken, now dead code retained for
reference only) per ../NUUC-Dispatch's ADR-0002.

Wire contract (authoritative): ../NUUC-Dispatch/docs/interfaces/signed-
identity-assertion.md. Reference verifier this repo's implementation mirrors:
../NUUC-Dispatch/src/Assertion.js's Assertion_verify.

BLOCKING PROVISIONING GAP (confirmed at gts-79dw.4.18, 2026-07-28): the
shared HMAC secret Script Property (kid=ASSERTION_KEY_GACTIONSHEET_1,
../NUUC-Dispatch/docs/OPERATIONS.md §Assertion keys) does NOT yet exist on
this deployment's Script Properties. `mint_test_assertion` (the test-harness
signer added alongside this verifier, src/TestFixtures.js) confirms this by
returning {ok: false, error: 'missing_secret'} rather than fabricating a
value. Every case below that needs a REAL correctly-signed token (positive
verify, tampered signature, wrong aud, expired exp) SKIPS individually until
an operator provisions the secret identically on both sides -- see
_mint_or_skip. The structural-rejection cases (malformed shape, wrong alg,
unknown kid, raw Google ID token) need no secret at all: the verifier
rejects each of them before ever reaching the property lookup or signature
check, so they run unconditionally and already prove the verification
boundary genuinely moved (a raw ID token is not merely a second accepted
shape -- it is rejected).
"""
import base64
import json
import time

import pytest

from scn.session import _http_post


def _b64url(value) -> str:
    if isinstance(value, dict):
        raw = json.dumps(value).encode("utf-8")
    elif isinstance(value, str):
        raw = value.encode("utf-8")
    else:
        raw = value
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _craft_assertion(header: dict, payload: dict, sig_bytes: bytes = b"x" * 32) -> str:
    """Hand-assembles a JWT-shaped string with an arbitrary (not necessarily
    valid) signature -- sufficient for cases the verifier rejects before it
    ever reaches the signature check (bad alg, unknown kid), and for the
    raw-ID-token/malformed-shape negative cases where any signature bytes
    will do since the token must be rejected on shape/claims grounds alone.
    """
    header_seg = _b64url(header)
    payload_seg = _b64url(payload)
    sig_seg = _b64url(sig_bytes)
    return f"{header_seg}.{payload_seg}.{sig_seg}"


def _verify_and_resolve(settings: dict, assertion: str, team_id: str = "NoSuchTeamIdAtAll") -> dict:
    return _http_post(settings["webappTestUrl"], {
        "action": "verify_and_resolve_access",
        "assertion": assertion,
        "teamId": team_id,
    })


def _mint(settings: dict, **kwargs) -> dict:
    payload = {
        "action": "run_fixture",
        "testToken": settings.get("testToken") or "",
        "fixture": "mint_test_assertion",
    }
    payload.update(kwargs)
    resp = _http_post(settings["webappTestUrl"], payload)
    return (resp or {}).get("data") or {}


def _mint_or_skip(settings, **kwargs) -> str:
    result = _mint(settings, **kwargs)
    if not result.get("ok"):
        pytest.skip(
            f"Shared assertion secret not provisioned on this deployment "
            f"(mint_test_assertion returned {result!r}) -- see "
            f"../NUUC-Dispatch/docs/OPERATIONS.md §Assertion keys for "
            f"provisioning steps. gts-79dw.4.18 flagged this as a blocking "
            f"gap rather than fabricating a secret."
        )
    return result["assertion"]


# ---------------------------------------------------------------------------
# Structural rejection — no shared secret required (the verifier fails
# before ever reaching the property lookup / signature check for these).
# ---------------------------------------------------------------------------

def test_raw_google_id_token_rejected_as_assertion(settings):
    """[gts-79dw.4.18 AC] A raw Google-issued ID token (RS256, `kid` naming a
    Google signing key, never a GActionSheet Script Property) must be
    rejected as an invalid assertion -- proves the verification boundary
    genuinely moved to signed assertions, not merely gained a second
    accepted input shape."""
    raw_google_id_token = _craft_assertion(
        {"alg": "RS256", "typ": "JWT", "kid": "google-signing-key-abc123"},
        {
            "iss": "accounts.google.com", "aud": "some-gis-client-id",
            "sub": "1234567890", "email": "real.user@gmail.com",
            "exp": int(time.time()) + 3600,
        },
    )
    resp = _verify_and_resolve(settings, raw_google_id_token)
    assert resp.get("verified") is False, (
        f"[4.18 AC] a raw Google ID token must not verify as a signed "
        f"assertion, got {resp!r}"
    )
    assert resp.get("tier") == "NONE", f"[4.18 AC] expected tier=NONE, got {resp!r}"


def test_malformed_assertion_fails_closed(settings):
    """Not a 3-segment JWT shape at all — must fail closed, never throw."""
    resp = _verify_and_resolve(settings, "not-a-jwt-shape-at-all")
    assert resp.get("verified") is False, f"expected verified=False, got {resp!r}"
    assert resp.get("tier") == "NONE", f"expected tier=NONE, got {resp!r}"


def test_wrong_alg_fails_closed(settings):
    """[4.18 AC] alg != 'HS256' must be rejected outright, even when kid
    names a real (or real-looking) target property — no real secret needed
    since the alg check runs strictly before the property lookup."""
    assertion = _craft_assertion(
        {"alg": "RS256", "typ": "JWT", "kid": "ASSERTION_KEY_GACTIONSHEET_1"},
        {
            "iss": "nuuc-dispatch", "aud": "gactionsheet", "sub": "x",
            "email": "x@example.com", "exp": int(time.time()) + 3600,
        },
    )
    resp = _verify_and_resolve(settings, assertion)
    assert resp.get("verified") is False, f"expected verified=False, got {resp!r}"
    assert resp.get("tier") == "NONE", f"expected tier=NONE, got {resp!r}"


def test_unknown_kid_fails_closed(settings):
    """[4.18 AC] A `kid` naming no Script Property at all must fail closed —
    no real secret needed since the property lookup itself is what fails."""
    assertion = _craft_assertion(
        {"alg": "HS256", "typ": "JWT", "kid": "ASSERTION_KEY_DEFINITELY_NOT_PROVISIONED"},
        {
            "iss": "nuuc-dispatch", "aud": "gactionsheet", "sub": "x",
            "email": "x@example.com", "exp": int(time.time()) + 3600,
        },
    )
    resp = _verify_and_resolve(settings, assertion)
    assert resp.get("verified") is False, f"expected verified=False, got {resp!r}"
    assert resp.get("tier") == "NONE", f"expected tier=NONE, got {resp!r}"


# ---------------------------------------------------------------------------
# Signature/claim rejection + positive path — require the real shared secret
# (Script Property named by kid) provisioned identically on both sides
# (../NUUC-Dispatch/docs/OPERATIONS.md §Assertion keys). SKIP individually
# until provisioned — confirmed missing as of gts-79dw.4.18.
# ---------------------------------------------------------------------------

def test_valid_assertion_verifies_with_correct_sub_email(settings):
    """[4.18 AC] A correctly-signed assertion minted with the real shared
    secret must verify and yield the exact sub/email it carries."""
    sub = "gts-79dw-4-18-sub-001"
    email = "assertion-valid@example.com"
    assertion = _mint_or_skip(settings, sub=sub, email=email)
    resp = _verify_and_resolve(settings, assertion)
    assert resp.get("verified") is True, f"[4.18 AC] valid assertion must verify, got {resp!r}"
    assert resp.get("sub") == sub, f"[4.18 AC] expected sub={sub!r}, got {resp!r}"
    assert resp.get("email") == email, f"[4.18 AC] expected email={email!r}, got {resp!r}"


def test_tampered_signature_fails_closed(settings):
    """[4.18 AC negative] A correctly-shaped, correctly-claimed assertion
    whose signature has been tampered with must fail closed."""
    assertion = _mint_or_skip(settings, tamperSignature=True)
    resp = _verify_and_resolve(settings, assertion)
    assert resp.get("verified") is False, (
        f"[4.18 AC negative] tampered signature must fail closed, got {resp!r}"
    )
    assert resp.get("tier") == "NONE", f"expected tier=NONE, got {resp!r}"


def test_wrong_aud_fails_closed(settings):
    """[4.18 AC negative] A correctly-signed assertion scoped to a different
    target (aud != 'gactionsheet') must fail closed."""
    assertion = _mint_or_skip(settings, aud="some-other-target")
    resp = _verify_and_resolve(settings, assertion)
    assert resp.get("verified") is False, (
        f"[4.18 AC negative] wrong aud must fail closed, got {resp!r}"
    )
    assert resp.get("tier") == "NONE", f"expected tier=NONE, got {resp!r}"


def test_expired_assertion_fails_closed(settings):
    """[4.18 AC negative] A correctly-signed assertion past its exp must fail
    closed."""
    assertion = _mint_or_skip(settings, exp=int(time.time()) - 60)
    resp = _verify_and_resolve(settings, assertion)
    assert resp.get("verified") is False, (
        f"[4.18 AC negative] expired assertion must fail closed, got {resp!r}"
    )
    assert resp.get("tier") == "NONE", f"expected tier=NONE, got {resp!r}"
