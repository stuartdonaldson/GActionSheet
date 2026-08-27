"""
fixture_invoke.py

HTTP-based GAS fixture invocation — no browser, no Playwright.

Uses the per-deployment TEST_TOKEN written to local.settings.json by
`npm run deploy:test`.  The token is validated and expiry-checked by
_handleRunFixture in TestWebApp.js (GAS side).

Usage:
    from tests.helpers.fixture_invoke import invoke_fixture

    result = invoke_fixture('sync_status_deleted', test_doc_id, settings)
    # result == { 'tag': 'fixture.sync_status_deleted', 'data': {} }

    result = invoke_fixture('sync_status_on_edit', test_doc_id, settings)
    sentinel = result['data']['sentinelDateModified']
"""

from __future__ import annotations

import scn.session as _session


class FixtureTokenError(RuntimeError):
    """Raised when the GAS WebApp rejects the test token (missing, mismatched, or expired)."""


class FixtureError(RuntimeError):
    """Raised when the GAS fixture itself returns an error in the response body."""


def invoke_fixture(
    fixture_name: str,
    test_doc_id: str,
    settings: dict,
    *,
    extra: dict | None = None,
    timeout: int = 360,
) -> dict:
    """Invoke a GAS test fixture via HTTP POST to the WebApp run_fixture endpoint.

    Args:
        fixture_name: Name of the fixture scenario (e.g. 'sync_status_deleted').
        test_doc_id:  Google Doc ID, threaded through as a real parameter on the
                      GAS side (setupTestFixtures's data.docId) — GAS holds no
                      shared script property for this (ADR-0006 §4).
        settings:     Loaded local.settings.json dict.  Must contain 'webappTestUrl'
                      and 'testToken'.
        extra:        Additional fixture-specific fields merged into the payload
                      (e.g. {'masterDocId': ...} for 'end_test_session').
        timeout:      HTTP timeout in seconds (default 360 — GAS can be slow).

    Returns:
        Parsed JSON response body: { 'tag': 'fixture.<name>', 'data': { ... } }

    Raises:
        FixtureTokenError: WebApp returned 'test-token-unauthorized' or
                           'test-token-expired'.
        FixtureError:      Response body contains { 'error': '...' }.
        RuntimeError:      HTTP error or JSON parse failure.

    Transport + retry (GTaskSheet-z6bx): delegates to scn.session._http_post,
    which bounds-retries the two known /exec -> script.googleusercontent.com
    routing symptoms (HTTP 404; non-JSON echo-page body) instead of raising on
    the first attempt. invoke_fixture used to be a third, independent copy of
    this POST logic with no retry at all; because it sits on the session-scoped
    autouse _reset_test_state path (tests/conftest.py), one transient routing
    blip there used to abort an entire pytest session before any test code ran.
    _http_post's exception taxonomy (scn.session.FixtureTokenError /
    FixtureError) is mapped back onto this module's own classes below so
    existing callers and their `except fixture_invoke.FixtureTokenError`-style
    usage are unaffected.
    """
    url    = settings.get('webappTestUrl') or ''
    token  = settings.get('testToken')     or ''

    if not url:
        raise RuntimeError(
            "webappTestUrl not set in local.settings.json. "
            "Add it and run npm run deploy:test to register a test token."
        )
    if not token:
        raise RuntimeError(
            "testToken not set in local.settings.json. "
            "Run npm run deploy:test to generate and register a fresh token."
        )

    payload = {
        'action':    'run_fixture',
        'testToken': token,
        'fixture':   fixture_name,
        'testDocId': test_doc_id,
    }
    if extra:
        payload.update(extra)

    try:
        return _session._http_post(url, payload, timeout)
    except _session.FixtureTokenError as exc:
        raise FixtureTokenError(str(exc)) from exc
    except _session.FixtureError as exc:
        raise FixtureError(str(exc)) from exc
