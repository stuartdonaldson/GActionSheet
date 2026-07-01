#!/usr/bin/env python3
"""
call_webapp.py — POST to the GAS WebApp without re-deriving the URL/auth shape
every time (GTaskSheet-kkm7 perf work; mirrors query_axiom.py's role for Axiom).

Reads webappTestUrl/webappProdUrl/webappDevUrl, testToken, and webappSecret from
local.settings.json (same settings file every other test/script in this repo
uses — see tests/conftest.py:_load_settings()). Auth lives entirely in the JSON
body (testToken for test-support routes, secret for production routes) — the
WebApp deployment is access:ANYONE_ANONYMOUS, so no OAuth/Authorization header
is needed or supported for external callers. Never prints the secret/token.

This is the only sanctioned way to call the WebApp manually (curl/raw urllib
against it directly is error-prone — see GTaskSheet-kkm7 session notes: wrong
auth field, POST-vs-GET redirect handling, and env mix-ups are exactly the
mistakes this script exists to prevent).

Usage:
    python scripts/call_webapp.py ACTION [--data '{"key": "value"}'] [--env test|prod|dev]
                                   [--auth testToken|secret|none]

Examples:
    python scripts/call_webapp.py get_test_config
    python scripts/call_webapp.py begin_journey_session
    python scripts/call_webapp.py run_fixture --data '{"fixture": "sync_all"}'
    python scripts/call_webapp.py mark_doc_not_found --data '{"docIds": ["abc123"]}'
    python scripts/call_webapp.py end_journey_session --data '{"docId": "abc123"}'
"""
import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request

_SETTINGS_PATH = pathlib.Path(__file__).parent.parent / "local.settings.json"

_ENV_URL_KEY = {
    "test": "webappTestUrl",
    "prod": "webappProdUrl",
    "dev":  "webappDevUrl",
}

# Routes whose production (non-test-harness) callers authenticate with
# webappSecret rather than testToken — see WebApp.js doPost's secret gate.
# Everything NOT in WebApp.js's testToken-gated block above the secret check
# (run_fixture, edit_action_row, find_sheet_actions, begin/end_journey_session,
# append_doc_paragraph, verify_*, import_selected_for_test,
# forward_action_rows_test) defaults to testToken instead.
_SECRET_ROUTES = {
    "upsert_action_rows", "sync_action_rows", "mark_doc_not_found",
    "delete_action_row", "forward_action_rows", "list_importable_actions",
    "get_test_config", "bootstrap", "set_test_token", "set_axiom_config", "axiom_probe",
}


def _load_settings() -> dict:
    if not _SETTINGS_PATH.exists():
        raise FileNotFoundError(
            "local.settings.json not found. Copy local.settings.example.json and fill in IDs."
        )
    return json.loads(_SETTINGS_PATH.read_text())


def call(url: str, payload: dict, *, timeout: int = 360) -> dict:
    """POST payload to the WebApp and return the parsed JSON response.

    Mirrors scn.session.ScenarioSession._http_post's error handling (same
    failure modes: HTTP errors, network errors, non-JSON/echo-page responses
    from a stale or mid-propagation deployment) so a one-off manual call
    fails with the same diagnosable messages a test run would produce.
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            final_url = resp.geturl()
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"HTTP {exc.code} from GAS WebApp (action={payload.get('action')!r}): {raw[:500]!r}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Network error (action={payload.get('action')!r}): {exc.reason}"
        ) from exc

    if raw in ("test-token-unauthorized", "test-token-expired"):
        raise RuntimeError(
            f"GAS rejected test token for action={payload.get('action')!r}: {raw}. "
            "Re-register with: python scripts/refresh_test_token.py (or npm run deploy:test)."
        )
    if raw == "unauthorized":
        raise RuntimeError(
            f"GAS rejected action={payload.get('action')!r}: missing/wrong 'secret'. "
            "Production routes need --auth secret (default is testToken)."
        )

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        redir = f" (redirected to {final_url!r})" if final_url != url else ""
        raise RuntimeError(
            f"Non-JSON response (action={payload.get('action')!r}){redir}: {raw[:500]!r}. "
            "This is usually GAS deployment propagation lag right after a redeploy — "
            "wait a bit and retry, or run npm run deploy:test again."
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", help="The WebApp 'action' field, e.g. sync_action_rows, run_fixture")
    parser.add_argument("--data", default="{}", help="Extra JSON payload fields, e.g. '{\"docId\": \"abc\"}'")
    parser.add_argument("--env", choices=["test", "prod", "dev"], default="test",
                         help="Which deployment to call (default: test)")
    parser.add_argument("--auth", choices=["testToken", "secret", "none"], default=None,
                         help="Which auth field to send (default: secret for production-gated "
                              "routes, testToken otherwise)")
    args = parser.parse_args()

    settings = _load_settings()
    url = settings.get(_ENV_URL_KEY[args.env])
    if not url:
        print(f"ERROR: {_ENV_URL_KEY[args.env]} not set in local.settings.json", file=sys.stderr)
        return 1

    try:
        extra = json.loads(args.data)
    except json.JSONDecodeError as exc:
        print(f"ERROR: --data is not valid JSON: {exc}", file=sys.stderr)
        return 1

    auth = args.auth or ("secret" if args.action in _SECRET_ROUTES else "testToken")
    payload = {"action": args.action, **extra}
    if auth == "testToken":
        token = settings.get("testToken")
        if not token:
            print("ERROR: testToken not set in local.settings.json", file=sys.stderr)
            return 1
        payload["testToken"] = token
    elif auth == "secret":
        secret = settings.get("webappSecret")
        if not secret:
            print("ERROR: webappSecret not set in local.settings.json", file=sys.stderr)
            return 1
        payload["secret"] = secret

    try:
        result = call(url, payload)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
