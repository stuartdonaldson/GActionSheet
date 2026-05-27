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

import json
import urllib.request
import urllib.error


class FixtureTokenError(RuntimeError):
    """Raised when the GAS WebApp rejects the test token (missing, mismatched, or expired)."""


class FixtureError(RuntimeError):
    """Raised when the GAS fixture itself returns an error in the response body."""


def invoke_fixture(
    fixture_name: str,
    test_doc_id: str,
    settings: dict,
    *,
    timeout: int = 360,
) -> dict:
    """Invoke a GAS test fixture via HTTP POST to the WebApp run_fixture endpoint.

    Args:
        fixture_name: Name of the fixture scenario (e.g. 'sync_status_deleted').
        test_doc_id:  Google Doc ID to pass as TEST_DOC_ID override on the GAS side.
        settings:     Loaded local.settings.json dict.  Must contain 'webappTestUrl'
                      and 'testToken'.
        timeout:      HTTP timeout in seconds (default 360 — GAS can be slow).

    Returns:
        Parsed JSON response body: { 'tag': 'fixture.<name>', 'data': { ... } }

    Raises:
        FixtureTokenError: WebApp returned 'test-token-unauthorized' or
                           'test-token-expired'.
        FixtureError:      Response body contains { 'error': '...' }.
        RuntimeError:      HTTP error or JSON parse failure.
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

    payload = json.dumps({
        'action':    'run_fixture',
        'testToken': token,
        'fixture':   fixture_name,
        'testDocId': test_doc_id,
    }).encode('utf-8')

    req = urllib.request.Request(
        url,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(
            f"HTTP {exc.code} from GAS WebApp for fixture '{fixture_name}': {raw!r}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Network error invoking fixture '{fixture_name}': {exc.reason}"
        ) from exc

    # Token errors are returned as plain text (not JSON).
    if raw in ('test-token-unauthorized', 'test-token-expired'):
        raise FixtureTokenError(
            f"GAS WebApp rejected test token for fixture '{fixture_name}': {raw}. "
            "Run npm run deploy:test to generate a fresh token."
        )

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Non-JSON response from GAS WebApp for fixture '{fixture_name}': {raw!r}"
        ) from exc

    if 'error' in result:
        raise FixtureError(
            f"GAS fixture '{fixture_name}' returned error: {result['error']}"
        )

    return result
