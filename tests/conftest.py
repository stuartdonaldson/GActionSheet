"""Pytest configuration and shared fixtures."""
import json
import os
import pathlib
import re

import pytest

_SETTINGS_PATH = pathlib.Path(__file__).parent.parent / "local.settings.json"
_TEST_RESULTS = pathlib.Path(__file__).parent.parent / "test-results"


def _find_page(item):
    """Locate the active Playwright page from a failing test's fixtures.

    Supports the two harness shapes: a direct `browser_page` fixture
    (test_ui_smoke) and a `ScenarioSession` exposing `.ui._page`. Returns None
    for non-UI tests (e.g. mock-based unit tests), which makes the failure
    hook a no-op there.
    """
    fa = getattr(item, "funcargs", {})
    page = fa.get("browser_page")
    if page is not None:
        return page
    for value in fa.values():
        ui = getattr(value, "ui", None)
        if ui is not None and getattr(ui, "_page", None) is not None:
            return ui._page
    return None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Universal UI-failure diagnostics (GTaskSheet-3tkf).

    On ANY failed UI test (timeout or assertion), save a full-page screenshot
    under test-results/, echo its path + the page.frames URLs + each frame's
    visible button names into the failure report, and attach the PNG to
    Allure — so a human can review the failure without a re-run. The button
    list (via scn.ui.describe_visible_buttons — shared with UiDriver's own
    capture_failure(); GTaskSheet-3sgr) reads the same ARIA roles
    get_by_role() queries, so it tells you exactly what was clickable at the
    moment of failure without re-running or eyeballing the screenshot.
    No-op when no active page is found (non-UI tests).
    """
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return
    page = _find_page(item)
    if page is None:
        return
    try:
        _TEST_RESULTS.mkdir(exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", item.nodeid.lower()).strip("-")[:80] or "ui-test"
        shot = _TEST_RESULTS / f"FAIL-{slug}.png"
        page.screenshot(path=str(shot), full_page=True)
        frames = "\n  ".join(getattr(f, "url", "?") for f in page.frames)
        from scn.ui import describe_visible_buttons
        buttons = describe_visible_buttons(page.frames)
        report.sections.append(
            ("UI failure diagnostics (GTaskSheet-3tkf)",
             f"Screenshot: {shot}\nFrames:\n  {frames}\nVisible buttons:\n{buttons}")
        )
        try:
            import allure
            allure.attach(
                page.screenshot(),
                name=f"FAIL {item.name}",
                attachment_type=allure.attachment_type.PNG,
            )
        except Exception:
            pass
    except Exception:
        # Diagnostics must never mask the original failure.
        pass


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
