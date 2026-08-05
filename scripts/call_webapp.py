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
                                   [--auth testToken|secret|adminSecret|none]

Examples:
    python scripts/call_webapp.py get_test_config
    python scripts/call_webapp.py begin_journey_session
    python scripts/call_webapp.py run_fixture --data '{"fixture": "sync_all"}'
    python scripts/call_webapp.py mark_doc_not_found --data '{"docIds": ["abc123"]}'
    python scripts/call_webapp.py end_journey_session --data '{"docId": "abc123"}'

Admin routes (gts-79dw.4.18, src/Admin.js — mirrors ../NUUC-Dispatch/tools/
call-webapp.js's own bootstrapSecret/setScriptProperties pair for
consistency across both repos). ADMIN_SECRET is a distinct, higher-privilege
credential from webappSecret/testToken above — never reused across routes.
One-time bootstrap (refuses to run again once ADMIN_SECRET is already set):
    python scripts/call_webapp.py bootstrapSecret --data '{"secret": "<32+ char secret>"}'
Then, authenticated by the adminSecret stored in local.settings.json:
    python scripts/call_webapp.py setScriptProperties --data '{"properties": {"KEY": "value"}}'
"""
import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

_SETTINGS_PATH = pathlib.Path(__file__).parent.parent / "local.settings.json"

# Mirrors scn.session._HTTP_POST_MAX_ATTEMPTS/_HTTP_POST_RETRY_DELAY_S — see
# that module for why this is a bounded retry, not a fixed post-deploy delay.
_CALL_MAX_ATTEMPTS = 3
_CALL_RETRY_DELAY_S = 3

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
    failure modes: HTTP errors, network errors, non-JSON/echo-page responses)
    so a one-off manual call fails with the same diagnosable messages a test
    run would produce. The non-JSON case is retried a bounded number of times
    before raising — see scn/session.py's _http_post docstring for why this
    is a redirect-replayed-as-GET quirk (observed recurring long after any
    deploy), not a fixed propagation window a single sleep could paper over.
    """
    data = json.dumps(payload).encode("utf-8")

    for attempt in range(1, _CALL_MAX_ATTEMPTS + 1):
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                final_url = resp.geturl()
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404 and attempt < _CALL_MAX_ATTEMPTS:
                time.sleep(_CALL_RETRY_DELAY_S)
                continue
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
            if attempt < _CALL_MAX_ATTEMPTS:
                time.sleep(_CALL_RETRY_DELAY_S)
                continue
            raise RuntimeError(
                f"Non-JSON response (action={payload.get('action')!r}){redir}: {raw[:500]!r} "
                f"(after {_CALL_MAX_ATTEMPTS} attempts). This is usually GAS deployment "
                "propagation lag or a redirect-replayed-as-GET quirk — if it persists, "
                "run npm run deploy:test again."
            ) from exc


def call_action(action: str, extra: dict | None = None, *,
                env: str = "test", auth: str | None = None) -> dict:
    """Resolve URL + auth from local.settings.json, POST `action`, return the JSON.

    The single entry point for calling the WebApp from Python outside a pytest
    run — main() below is a thin CLI over it, and other scripts import it
    rather than re-deriving the URL/auth rules. `auth` defaults to 'secret' for
    production-gated routes and 'testToken' for everything else, matching
    WebApp.js doPost's gate order.
    """
    settings = _load_settings()
    url = settings.get(_ENV_URL_KEY[env])
    if not url:
        raise RuntimeError(f"{_ENV_URL_KEY[env]} not set in local.settings.json")

    payload = {"action": action, **(extra or {})}
    auth = auth or (
        "secret" if action in _SECRET_ROUTES else
        "none" if action == "bootstrapSecret" else
        "adminSecret" if action == "setScriptProperties" else
        "testToken"
    )
    if auth == "testToken":
        token = settings.get("testToken")
        if not token:
            raise RuntimeError("testToken not set in local.settings.json")
        payload["testToken"] = token
    elif auth == "secret":
        secret = settings.get("webappSecret")
        if not secret:
            raise RuntimeError("webappSecret not set in local.settings.json")
        payload["secret"] = secret
    elif auth == "adminSecret":
        admin_secret = settings.get("adminSecret")
        if not admin_secret:
            raise RuntimeError(
                "adminSecret not set in local.settings.json. Run bootstrapSecret first."
            )
        payload["adminSecret"] = admin_secret

    return call(url, payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", help="The WebApp 'action' field, e.g. sync_action_rows, run_fixture")
    parser.add_argument("--data", default="{}", help="Extra JSON payload fields, e.g. '{\"docId\": \"abc\"}'")
    parser.add_argument("--env", choices=["test", "prod", "dev"], default="test",
                         help="Which deployment to call (default: test)")
    parser.add_argument("--auth", choices=["testToken", "secret", "adminSecret", "none"], default=None,
                         help="Which auth field to send (default: secret for production-gated "
                              "routes, adminSecret for setScriptProperties, none for "
                              "bootstrapSecret, testToken otherwise)")
    args = parser.parse_args()

    try:
        extra = json.loads(args.data)
    except json.JSONDecodeError as exc:
        print(f"ERROR: --data is not valid JSON: {exc}", file=sys.stderr)
        return 1

    try:
        result = call_action(args.action, extra, env=args.env, auth=args.auth)
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
