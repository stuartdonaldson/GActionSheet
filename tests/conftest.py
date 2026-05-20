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
    return settings["testDocId"]


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
