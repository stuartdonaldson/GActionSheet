"""Deployed-build guard (gts-omoy).

The 2026-08-29 proximate cause was a stale bound script predating ADR-0023's
ACT- read support -- the suite ran against it green-ish. `check_deployed_build`
fails fast, with a diagnosable message, unless `?cmd=version` reports the
version+target this checkout last stamped.

No real network: `urllib.request.urlopen` is monkeypatched to a canned
response, proving both the red (mismatch) and green (match) paths offline.
"""
import io
import json

import pytest

from tests.helpers import version as version_mod

pytestmark = pytest.mark.no_live_session


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_urlopen(monkeypatch, body: str):
    def fake_urlopen(url, timeout=20):
        return _FakeResponse(body.encode())

    monkeypatch.setattr(version_mod.urllib.request, "urlopen", fake_urlopen)


def test_fetch_deployed_version_appends_cmd_param(monkeypatch):
    captured = {}

    def fake_urlopen(url, timeout=20):
        captured["url"] = url
        return _FakeResponse(json.dumps({"ok": True, "version": "1.2.3", "target": "TEST"}).encode())

    monkeypatch.setattr(version_mod.urllib.request, "urlopen", fake_urlopen)
    result = version_mod.fetch_deployed_version("https://x/exec")
    assert captured["url"] == "https://x/exec?cmd=version"
    assert result == {"ok": True, "version": "1.2.3", "target": "TEST"}


def test_fetch_deployed_version_raises_diagnosable_on_non_json(monkeypatch):
    """A non-JSON body (GAS deployment-propagation lag) must not surface as a
    bare traceback -- CLAUDE.md's call_webapp.py convention."""
    _patch_urlopen(monkeypatch, "<html>propagating...</html>")
    with pytest.raises(RuntimeError, match="non-JSON"):
        version_mod.fetch_deployed_version("https://x/exec")


# ---------------------------------------------------------------------------
# check_deployed_build -- proven red against a deliberately stale/mismatched
# version AND a mismatched target (gts-omoy AC3).
# ---------------------------------------------------------------------------

def test_check_deployed_build_red_on_stale_version(monkeypatch):
    expected_version = version_mod.read_expected_version()
    expected_target = version_mod.read_expected_target()
    stale = "0.0.0.0"
    assert stale != expected_version
    _patch_urlopen(monkeypatch, json.dumps({"ok": True, "version": stale, "target": expected_target}))
    with pytest.raises(RuntimeError) as excinfo:
        version_mod.check_deployed_build("https://x/exec")
    msg = str(excinfo.value)
    assert expected_version in msg
    assert stale in msg
    assert "pnpm run deploy:test" in msg


def test_check_deployed_build_red_on_wrong_target(monkeypatch):
    expected_version = version_mod.read_expected_version()
    wrong_target = "PRODUCTION"
    assert wrong_target != version_mod.read_expected_target()
    _patch_urlopen(monkeypatch, json.dumps({"ok": True, "version": expected_version, "target": wrong_target}))
    with pytest.raises(RuntimeError) as excinfo:
        version_mod.check_deployed_build("https://x/exec")
    msg = str(excinfo.value)
    assert "TEST" in msg
    assert wrong_target in msg
    assert "pnpm run deploy:test" in msg


def test_check_deployed_build_green_on_match(monkeypatch):
    expected_version = version_mod.read_expected_version()
    expected_target = version_mod.read_expected_target()
    _patch_urlopen(monkeypatch, json.dumps({"ok": True, "version": expected_version, "target": expected_target}))
    version_mod.check_deployed_build("https://x/exec")  # must not raise


def test_check_deployed_build_tolerates_leading_v_on_either_side(monkeypatch):
    """Version.js's expected value is bare; a caller reporting a leading 'v'
    (or vice versa) is the same version, not a mismatch."""
    expected_target = version_mod.read_expected_target()
    bare = version_mod.read_expected_version().lstrip("v")
    _patch_urlopen(monkeypatch, json.dumps({"ok": True, "version": f"v{bare}", "target": expected_target}))
    version_mod.check_deployed_build("https://x/exec")  # must not raise
