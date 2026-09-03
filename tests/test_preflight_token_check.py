"""test_preflight_token_check.py — gts-d6nz (stage `harness-resilience`,
knowledge-base/staging/portal-perf-harness.md, final bead).

gts-5959 root-caused a 177-failure sweep to the GAS WebApp rejecting the test
token ('test-token-unauthorized') even though local.settings.json's cached
testTokenExpiresAt was still in the future -- a second `pnpm run deploy:test`
run (concurrent, later, CI) silently overwrote the single server-side token
value. The rejection was first surfaced by `_reset_test_state`
(tests/conftest.py), a session-scoped autouse fixture that already makes the
suite's first live call carrying the real testToken -- but a bare raise there
is cached by pytest and replayed as an identical ERROR on every one of the
suite's ~635 tests, which is exactly the fan-out the incident reported.

`_invoke_preflight_fixture` (tests/conftest.py) wraps that *same* existing
call (no new live call added) and turns a FixtureTokenError into a single
`pytest.exit` naming `pnpm run deploy:test`, mirroring the established
`_check_deployed_build` fail-fast convention.

No live GAS backend: `scn.session._http_post` is monkeypatched, following the
pattern in tests/test_conftest_test_doc_id_finalizer.py and
tests/test_fixture_invoke_retry.py.
"""
import pytest
from _pytest.outcomes import Exit

import scn.session as session_mod
from tests.conftest import _invoke_preflight_fixture

pytestmark = pytest.mark.no_live_session

SETTINGS = {"webappTestUrl": "https://example.com/exec", "testToken": "tok-abc"}


def test_token_rejection_exits_session_with_single_clear_message(monkeypatch):
    calls = {"n": 0}

    def fake_http_post(url, payload, timeout=360):
        calls["n"] += 1
        raise session_mod.FixtureTokenError(
            "GAS rejected test token for action='run_fixture': test-token-unauthorized."
        )

    monkeypatch.setattr(session_mod, "_http_post", fake_http_post)

    with pytest.raises(Exit) as excinfo:
        _invoke_preflight_fixture("reset_test_state", SETTINGS, timeout=60)

    assert calls["n"] == 1, "pre-flight must make exactly one live call, not retry into a fan-out"
    assert "pnpm run deploy:test" in excinfo.value.msg
    assert "reset_test_state" in excinfo.value.msg
    assert excinfo.value.returncode == 1


def test_successful_call_returns_normally_with_no_added_overhead(monkeypatch):
    """Confirms the wrapper adds no second call/round trip on the happy path
    -- AC: 'does NOT add meaningful per-test overhead' -- by asserting the
    call count stays at the one invoke_fixture already made."""
    calls = {"n": 0}

    def fake_http_post(url, payload, timeout=360):
        calls["n"] += 1
        return {"ok": True, "data": {}}

    monkeypatch.setattr(session_mod, "_http_post", fake_http_post)

    result = _invoke_preflight_fixture("reset_test_state", SETTINGS, timeout=60)

    assert calls["n"] == 1
    assert result == {"ok": True, "data": {}}


def test_non_token_fixture_error_still_raises_uncaught(monkeypatch):
    """Only test-token rejection is turned into pytest.exit -- any other GAS
    fixture error (e.g. a real bug in the fixture) must still surface as a
    normal exception, not be swallowed or misreported as a token problem."""
    def fake_http_post(url, payload, timeout=360):
        raise session_mod.FixtureError("GAS returned error for action='run_fixture': boom")

    monkeypatch.setattr(session_mod, "_http_post", fake_http_post)

    with pytest.raises(Exception) as excinfo:
        _invoke_preflight_fixture("reset_test_state", SETTINGS, timeout=60)
    assert not isinstance(excinfo.value, Exit)
