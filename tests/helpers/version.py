"""version.py — read the deployed BUILD_INFO.version from src/Version.js.

Used as a smoke-test pre-flight: compares the version string the add-on
sidebar reports (live, via UiDriver.read_version) against the version stamped
into the source by `pnpm run deploy:test`, confirming the
test deployment installed in the test Google account is serving this build.
"""
import pathlib
import re

_VERSION_JS = pathlib.Path(__file__).parent.parent.parent / "src" / "Version.js"
# The deploy stamper writes a JSON-shaped literal ("version": "…"); the pre-package stamp wrote
# a bare key (version: "…"). Both are valid JS and both occur in checkouts.
_VERSION_FIELD_RE = re.compile(r'"?version"?\s*:\s*"([^"]+)"')


def read_expected_version() -> str:
    """Return BUILD_INFO.version from src/Version.js (e.g. 'v0.2.2.7')."""
    text = _VERSION_JS.read_text()
    m = _VERSION_FIELD_RE.search(text)
    if not m:
        raise ValueError(f"Could not find BUILD_INFO.version in {_VERSION_JS}")
    return m.group(1)
