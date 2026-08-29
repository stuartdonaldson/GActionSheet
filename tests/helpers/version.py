"""version.py — read the deployed BUILD_INFO.version from src/Version.js.

Used as a smoke-test pre-flight: compares the version string the add-on
sidebar reports (live, via UiDriver.read_version) against the version stamped
into the source by `pnpm run deploy:test`, confirming the
test deployment installed in the test Google account is serving this build.
"""
import json
import pathlib
import re
import urllib.error
import urllib.request

_VERSION_JS = pathlib.Path(__file__).parent.parent.parent / "src" / "Version.js"
# The deploy stamper writes a JSON-shaped literal ("version": "…"); the pre-package stamp wrote
# a bare key (version: "…"). Both are valid JS and both occur in checkouts.
_VERSION_FIELD_RE = re.compile(r'"?version"?\s*:\s*"([^"]+)"')
_TARGET_FIELD_RE = re.compile(r'"?target"?\s*:\s*"([^"]+)"')


def read_expected_version() -> str:
    """Return BUILD_INFO.version from src/Version.js (e.g. 'v0.2.2.7')."""
    text = _VERSION_JS.read_text()
    m = _VERSION_FIELD_RE.search(text)
    if not m:
        raise ValueError(f"Could not find BUILD_INFO.version in {_VERSION_JS}")
    return m.group(1)


def read_expected_target() -> str:
    """Return BUILD_INFO.target from src/Version.js (e.g. 'TEST')."""
    text = _VERSION_JS.read_text()
    m = _TARGET_FIELD_RE.search(text)
    if not m:
        raise ValueError(f"Could not find BUILD_INFO.target in {_VERSION_JS}")
    return m.group(1)


def fetch_deployed_version(webapp_url: str, timeout: int = 20) -> dict:
    """GET ?cmd=version — answered before every auth gate, on both doGet and
    doPost (src/WebApp.js's _handleVersionRequest); no secret required.

    Returns {ok, version, versionDate, target, env, deploymentId} or raises
    RuntimeError with the raw body on a non-JSON/HTTP-error response (e.g. the
    GAS deployment-propagation lag every sanctioned caller in this repo treats
    as diagnosable rather than a bare traceback — see CLAUDE.md's
    `call_webapp.py` note).
    """
    url = webapp_url.rstrip("?") + ("&" if "?" in webapp_url else "?") + "cmd=version"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"?cmd=version request failed: {exc}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(f"?cmd=version returned non-JSON (deploy propagation lag?): {body[:300]!r}")


def check_deployed_build(webapp_url: str) -> None:
    """gts-omoy: fail fast, with a diagnosable message, unless the deployment
    reachable at `webapp_url` is serving the version and target stamped into
    this checkout by the last `pnpm run deploy:test`.

    Raises RuntimeError naming expected vs. actual version/target and the
    remediation, rather than letting a stale-build run limp through the whole
    suite green-ish (the 2026-08-29 proximate cause).
    """
    expected_version = read_expected_version()
    expected_target = read_expected_target()
    actual = fetch_deployed_version(webapp_url)
    actual_version = str(actual.get("version") or "").lstrip("v")
    actual_target = str(actual.get("target") or "")
    if actual_version == expected_version.lstrip("v") and actual_target == expected_target:
        return
    raise RuntimeError(
        f"Deployed build mismatch at {webapp_url}: "
        f"expected version={expected_version!r} target={expected_target!r}, "
        f"got version={actual_version!r} target={actual_target!r}. "
        f"Re-run 'pnpm run deploy:test' and re-run the suite."
    )
