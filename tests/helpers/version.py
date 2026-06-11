"""version.py — read the deployed BUILD_INFO.version from src/Version.js.

Used as a smoke-test pre-flight: compares the version string the add-on
sidebar reports (live, via UiDriver.read_version) against the version stamped
into the source by `npm run deploy:test` (update-revision.js), confirming the
test deployment installed in the test Google account is serving this build.
"""
import pathlib
import re

_VERSION_JS = pathlib.Path(__file__).parent.parent.parent / "src" / "Version.js"
_VERSION_FIELD_RE = re.compile(r'version:\s*"([^"]+)"')


def read_expected_version() -> str:
    """Return BUILD_INFO.version from src/Version.js (e.g. 'v0.2.1 (Rev. Jun 9, 2026 22:06) (TEST)')."""
    text = _VERSION_JS.read_text()
    m = _VERSION_FIELD_RE.search(text)
    if not m:
        raise ValueError(f"Could not find BUILD_INFO.version in {_VERSION_JS}")
    return m.group(1)
