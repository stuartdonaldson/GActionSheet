"""Pytest configuration and shared fixtures."""
import json
import os
import pathlib
import pytest

_SETTINGS_PATH = pathlib.Path(__file__).parent.parent / "local.settings.json"


def _load_settings() -> dict:
    if not _SETTINGS_PATH.exists():
        raise FileNotFoundError(
            f"local.settings.json not found. Copy local.settings.example.json and fill in IDs."
        )
    return json.loads(_SETTINGS_PATH.read_text())


@pytest.fixture(scope="session")
def settings():
    return _load_settings()


@pytest.fixture(scope="session")
def test_sheet_id(settings):
    return settings["testSheetId"]


@pytest.fixture(scope="session")
def test_doc_id(settings):
    """Per-run clone of the master template doc.

    Creates a named clone at session start (TEST_DOC_ID script property is
    updated to the clone ID), yields the clone ID to all tests, then trashes
    the clone and restores the master at teardown.

    Uses HTTP fixture invocation (invoke_fixture) — no browser required.
    """
    from tests.helpers.fixture_invoke import invoke_fixture

    result = invoke_fixture("begin_test_session", settings["testDocId"], settings, timeout=180)
    clone_id = result["data"]["cloneId"]

    yield clone_id

    invoke_fixture("end_test_session", clone_id, settings, timeout=120)


@pytest.fixture(scope="session")
def expected_version():
    """BUILD_INFO.version stamped into src/Version.js by npm run deploy:test.

    Used as a smoke-test pre-flight (test_journey.py Act 0): the live add-on
    sidebar's version footer is compared against this to confirm the test
    deployment installed in the test Google account is serving this build.
    """
    from tests.helpers.version import read_expected_version
    return read_expected_version()


@pytest.fixture(scope="session")
def script_id(settings):
    return settings["scriptId"]


@pytest.fixture(scope="session")
def gas_log_dir(settings):
    d = settings.get("gasLogDir")
    if d and os.path.isdir(d):
        return d
    return None


@pytest.fixture(scope="session")
def gas_invoke():
    """Returns the gas_invoke module (Playwright-based).

    Retained for UI-level tests (e.g. TestMenuHandler) that require a browser.
    Fixture setup uses invoke_fixture (HTTP) instead — see fixture_invoke.py.
    """
    from tests.helpers import gas_invoke as _gas_invoke
    return _gas_invoke
