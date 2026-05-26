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
def test_doc_id(settings, gas_log_dir):
    """Per-run clone of the master template doc.

    Creates a named clone at session start (TEST_DOC_ID script property is
    updated to the clone ID), yields the clone ID to all tests, then trashes
    the clone and restores the master at teardown.
    """
    from tests.helpers import gas_invoke as gi
    from tests.helpers.gas_log import clear_logs, wait_for_log

    clear_logs(gas_log_dir)
    gi.begin_test_session(settings["testDocId"])
    entry = wait_for_log(
        gas_log_dir,
        lambda e: e.get("tag") == "session.begin",
        timeout_s=120.0,
    )
    clone_id = entry["data"]["cloneId"]

    yield clone_id

    clear_logs(gas_log_dir)
    gi.end_test_session()
    wait_for_log(
        gas_log_dir,
        lambda e: e.get("tag") == "session.end",
        timeout_s=60.0,
    )


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
    """Returns the gas_invoke module for calling GAS functions via Playwright."""
    from tests.helpers import gas_invoke as _gas_invoke
    return _gas_invoke
