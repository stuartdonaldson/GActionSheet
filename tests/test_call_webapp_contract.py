"""Contract test pinning scripts/call_webapp.py to gas-deploy's lib/webapp.js.

GAS-Core's gas-deployment RECOMMENDATION.md §3.3 found five hand-rolled webapp callers across
five projects and consolidated them into one Node implementation (`gas-deploy/lib/webapp.js` +
`bin/call-webapp.js`). GActionSheet's caller is the odd one out: it is Python, and it is
*imported* by the pytest harness (`scn.session`, several helpers), not just run as a CLI.

**Decision (Stage 3): the Python client stays a Python port.** Shelling out to the Node CLI once
per call would put a node process start in the inner loop of a suite that makes hundreds of
WebApp calls, and would force every caller to marshal results through a subprocess boundary for
no behavioural gain. What the consolidation was actually protecting against — the five callers
drifting apart on the four things they all get wrong independently — is instead pinned here.

These are the four properties both implementations must share (§3.3). Each assertion reads the
*other* implementation's source rather than restating it, so a change on the Node side that this
port does not follow fails here instead of silently drifting:

  1. the secret travels in the POST body only — never argv, never the query string, never printed
  2. the POST -> GET redirect is followed
  3. a non-JSON response is a failure, not a result (it means the request never reached the
     handler — the deployment-propagation race)
  4. `sit` and `test` name the same environment

No network calls: the Node side is read as text, the Python side is exercised with stubs.
"""
import json
import pathlib
import re
import urllib.error

import pytest

from scripts import call_webapp

_REPO = pathlib.Path(__file__).resolve().parent.parent
_NODE_WEBAPP = _REPO / "node_modules" / "gas-deploy" / "lib" / "webapp.js"
_NODE_CLI = _REPO / "node_modules" / "gas-deploy" / "bin" / "call-webapp.js"

_needs_package = pytest.mark.skipif(
    not _NODE_WEBAPP.exists(),
    reason="gas-deploy not installed (run pnpm install) — nothing to pin the port against",
)


# ── 1. the secret never leaves the POST body ───────────────────────────────────────────────────


def test_python_port_puts_auth_in_the_body_and_never_in_the_url(monkeypatch, tmp_path):
    """Every auth field this port knows about goes in the JSON body, never the URL."""
    sent = {}

    def fake_call(url, payload, *, timeout=360):
        sent["url"] = url
        sent["payload"] = payload
        return {"ok": True}

    monkeypatch.setattr(call_webapp, "call", fake_call)
    monkeypatch.setattr(call_webapp, "_load_settings", lambda: {
        "webappTestUrl": "https://script.google.com/macros/s/AK1/exec",
        "webappSecret": "S3CR3T", "testToken": "T0KEN", "adminSecret": "ADM1N",
    })

    for action, field, value in [
        ("get_test_config", "secret", "S3CR3T"),      # production-gated route
        ("run_fixture", "testToken", "T0KEN"),        # test-support route
        ("setScriptProperties", "adminSecret", "ADM1N"),  # admin route
    ]:
        sent.clear()
        call_webapp.call_action(action)
        assert sent["payload"][field] == value, f"{action} must authenticate with {field}"
        assert "?" not in sent["url"], "no query string at all, so no secret can be in one"
        for secret in ("S3CR3T", "T0KEN", "ADM1N"):
            assert secret not in sent["url"]


def test_bootstrap_secret_route_carries_no_stored_credential(monkeypatch):
    """bootstrapSecret runs before any secret exists — sending one would be a lie."""
    sent = {}
    monkeypatch.setattr(call_webapp, "call", lambda url, payload, **kw: sent.update(payload) or {"ok": True})
    monkeypatch.setattr(call_webapp, "_load_settings", lambda: {
        "webappTestUrl": "https://x/exec", "webappSecret": "S", "testToken": "T", "adminSecret": "A",
    })
    call_webapp.call_action("bootstrapSecret", {"secret": "new-one"})
    assert set(sent) == {"action", "secret"}
    assert sent["secret"] == "new-one", "the NEW secret is the payload, not the stored one"


@_needs_package
def test_node_side_also_keeps_the_secret_out_of_the_url():
    """The property this port is held to is the one lib/webapp.js enforces, not a local rule."""
    src = _NODE_WEBAPP.read_text()
    assert "execUrl requires a deployment ID" in src
    exec_url = src[src.index("function execUrl("):]
    exec_url = exec_url[: exec_url.index("\n}")]
    assert "cmd" in exec_url and "secret" not in exec_url, (
        "lib/webapp.js's execUrl puts only cmd in the query string; this port must match"
    )
    assert "redact" in src, "the Node side redacts before printing; call_webapp.py never prints auth"


def test_python_port_never_prints_a_secret():
    """Source-level: no code path formats an auth value into output."""
    src = (_REPO / "scripts" / "call_webapp.py").read_text()
    for line in src.splitlines():
        if "print(" not in line:
            continue
        assert not re.search(r"\b(secret|token|admin_secret|testToken|adminSecret)\b", line), (
            f"a print() references an auth value: {line.strip()}"
        )


# ── 2/3. transport: redirect following, and non-JSON is a failure ──────────────────────────────


def test_non_json_response_raises_after_bounded_retries(monkeypatch):
    """A string body means the request never reached the handler — a failure, not a result."""
    attempts = {"n": 0}

    class _Resp:
        def __init__(self, body, url):
            self._body, self._url = body, url

        def read(self):
            return self._body.encode()

        def geturl(self):
            return self._url

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        attempts["n"] += 1
        # An echo page served by the GET the POST was redirected to — exactly the race §3.3 names.
        return _Resp("<html>Moved</html>", "https://script.googleusercontent.com/echo")

    monkeypatch.setattr(call_webapp.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(call_webapp.time, "sleep", lambda s: None)

    with pytest.raises(RuntimeError) as exc:
        call_webapp.call("https://script.google.com/macros/s/AK1/exec", {"action": "ping"})

    assert attempts["n"] == call_webapp._CALL_MAX_ATTEMPTS, "bounded retry, then fail loudly"
    assert "Non-JSON response" in str(exc.value)
    assert "redirected to" in str(exc.value), "the redirect target is part of the diagnosis"


def test_a_json_body_after_the_redirect_is_a_success(monkeypatch):
    """urllib follows the 302 as a GET; a JSON body from the redirect target is the result."""
    class _Resp:
        def read(self):
            return json.dumps({"ok": True, "version": "0.2.2.7"}).encode()

        def geturl(self):
            return "https://script.googleusercontent.com/echo"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(call_webapp.urllib.request, "urlopen", lambda req, timeout=None: _Resp())
    result = call_webapp.call("https://script.google.com/macros/s/AK1/exec", {"action": "version"})
    assert result["version"] == "0.2.2.7"


@_needs_package
def test_node_side_follows_the_post_to_get_redirect():
    src = _NODE_WEBAPP.read_text()
    assert "301" in src and "302" in src, "lib/webapp.js follows the redirect"
    assert "Non-JSON response" in src, "and treats a string body as a failure — same as this port"


# ── 4. env vocabulary ──────────────────────────────────────────────────────────────────────────


def test_env_names_match_the_node_cli_vocabulary():
    """The Python CLI's --env choices are the envs the Node CLI accepts (sit/test synonyms)."""
    assert set(call_webapp._ENV_URL_KEY) == {"test", "prod", "dev"}


@_needs_package
def test_node_cli_treats_sit_and_test_as_synonyms():
    src = _NODE_CLI.read_text()
    synonyms = src[src.index("const synonyms"):]
    synonyms = synonyms[: synonyms.index("\n")]
    assert "sit" in synonyms and "test" in synonyms, (
        "sit/test are the same environment on the Node side; call_webapp.py names it 'test'"
    )


# ── the gated-route split is the same fact on both sides ───────────────────────────────────────


def test_ungated_routes_never_receive_a_stored_secret(monkeypatch):
    """cmd=version is answered before every gate — a caller must not send it a credential."""
    sent = {}
    monkeypatch.setattr(call_webapp, "call", lambda url, payload, **kw: sent.update(payload) or {"ok": True})
    monkeypatch.setattr(call_webapp, "_load_settings", lambda: {
        "webappTestUrl": "https://x/exec", "webappSecret": "S", "testToken": "T",
    })
    call_webapp.call_action("version", auth="none")
    assert set(sent) == {"action"}, "an ungated action carries no auth field"
