"""Pytest configuration and shared fixtures."""
import datetime
import json
import os
import pathlib
import re

import pytest

from tests import duration_instrumentation as di

_SETTINGS_PATH = pathlib.Path(__file__).parent.parent / "local.settings.json"
_TEST_RESULTS = pathlib.Path(__file__).parent.parent / "test-results"

_pytest_config = None

# --- gts-y1eg: progress counter + duration/baseline instrumentation state --
# Session-lifetime, single-process, serial suite (no xdist) — plain module
# globals are safe here; see duration_instrumentation.py for the pure logic.
_duration_total = 0
_duration_index_map: dict[str, int] = {}
_duration_next_index = 0
_duration_run_id = None
_duration_baseline: dict = {}
_duration_phases: dict[str, dict[str, float]] = {}
_duration_outcome: dict[str, str] = {}


def pytest_configure(config):
    global _pytest_config, _duration_run_id, _duration_baseline
    _pytest_config = config
    _duration_run_id = datetime.datetime.now(datetime.timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    _duration_baseline = di.load_baseline()


def pytest_collection_modifyitems(session, config, items):
    global _duration_total
    _duration_total = len(items)


def _timestamp() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def _terminal_writeline(line: str) -> None:
    """Write directly via the terminal reporter (gts-jukj).

    Bypasses pytest's per-test stdout capture (same mechanism the built-in
    PASSED/FAILED progress line uses), so the timestamp lands in a captured
    run log (e.g. test-full-run.txt) even without -s.
    """
    if _pytest_config is None:
        return
    tr = _pytest_config.pluginmanager.get_plugin("terminalreporter")
    if tr is not None:
        tr.write_line(line)


def pytest_runtest_logstart(nodeid, location):
    global _duration_next_index
    _duration_next_index += 1
    _duration_index_map[nodeid] = _duration_next_index
    _terminal_writeline(f"[{_timestamp()}] {di.format_start_line(_duration_next_index, _duration_total, nodeid)}")


def pytest_runtest_logreport(report):
    """gts-y1eg AC1-AC4: per-phase durations -> [n/total] FINISH line +
    flushed JSONL trend record + self-calibrating baseline update.

    Report-only: this never raises and never touches the test outcome — a
    failure anywhere in here must not mask the real pass/fail signal.
    """
    if report.when not in ("setup", "call", "teardown"):
        return
    global _duration_baseline
    try:
        nodeid = report.nodeid
        phases = _duration_phases.setdefault(nodeid, {})
        phases[report.when] = report.duration
        if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
            _duration_outcome[nodeid] = report.outcome
        if report.when != "teardown":
            return

        phases = _duration_phases.pop(nodeid, {})
        outcome = _duration_outcome.pop(nodeid, report.outcome)
        index = _duration_index_map.pop(nodeid, _duration_next_index)
        entry = _duration_baseline.get(nodeid)
        baseline_s = entry["median_s"] if entry else None

        record = di.build_record(
            run_id=_duration_run_id, index=index, total=_duration_total,
            nodeid=nodeid, outcome=outcome,
            setup_s=phases.get("setup", 0.0), call_s=phases.get("call", 0.0),
            teardown_s=phases.get("teardown", 0.0), baseline_s=baseline_s,
        )
        _terminal_writeline(f"[{_timestamp()}] {di.format_finish_line(record)}")
        di.append_jsonl(record)
        if outcome == "passed":
            _duration_baseline = di.update_baseline(_duration_baseline, nodeid, record["total_s"])
            di.save_baseline(_duration_baseline)
    except Exception:
        # Instrumentation must never mask or alter the real test result.
        pass


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

    Ordering contract (gts-hroj): this hook fires for report.when == "call",
    i.e. once the test function has already fully unwound (any `finally:`
    inside the test body has already run). A test that trashes its own
    journey doc(s) from its own `finally:` will therefore always beat this
    hook — the screenshot shows the post-trash Drive-trash chrome regardless
    of the real failure. There is no hookwrapper ordering fix for this
    (verified empirically: pytest_runtest_call's post-yield resume and every
    report.when=="call" hook fire only after the test's own finally has
    already executed, since that finally is part of the same call-stack
    unwind). The actual fix lives in scn/session.py: ScenarioSession.new_doc(
    request=...) registers doc-trashing as a pytest fixture *finalizer*
    (teardown phase, which runs after this hook) instead of leaving it to the
    test's own finally. Multi-doc tests must call `scn.engine.close()` (not
    `scn.close()` / not a manual end_journey_session call) from their own
    `finally:` if they need the drain-invariant assertion at that point.
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
    settings = json.loads(_SETTINGS_PATH.read_text())
    _warn_missing_playwright_accounts(settings)
    return settings


def _warn_missing_playwright_accounts(settings: dict) -> None:
    """Surface a missing shared-auth mapping through the terminal reporter (GTaskSheet-jukj),
    not just stderr — resolve_auth_file()'s own warning can get swallowed by pytest's
    default capture, and this feature is easy to miss entirely if nothing points at it.

    Only checks "primary": every browser_page fixture in this suite resolves that role.
    """
    if "primary" in settings.get("playwrightAccounts", {}):
        return
    _terminal_writeline(
        '⚠️  local.settings.json has no "playwrightAccounts" entry for role "primary" — '
        "tests are using the project-local .auth/user.json fallback instead of a shared, "
        "cross-project auth session. See .auth/README.md and "
        "node tests/playwright/auth.setup.js to migrate "
        "(DevStandard docs/standards/playwright-shared-auth.md)."
    )


@pytest.fixture(scope="session")
def settings():
    return _load_settings()


@pytest.fixture(scope="session", autouse=True)
def _check_auth_session_alive():
    """Probe the shared Playwright auth session once, before any other
    session fixture or test runs, and hard-abort the whole run if it's
    signed out (gts-85x3.1).

    gts-f3me.4's proactive/reactive cookie-*rotation* refresh
    (tests/helpers/download.py) cannot repair a fully signed-out session --
    by its own docstring, that's out of scope for automated refresh. Without
    this check, a dead session is only discovered test-by-test, each one
    burning its own setup/timeout cost before failing -- confirmed live
    2026-08-21 (gas-test4.log): 39 failed / 6 errors over a full 2h21m run,
    all traced back to one dead session that nothing caught until the very
    last test. There is no point running the suite at all in that state, so
    this fails the whole session immediately (pytest.exit, not a single
    failed test) with a clear "re-run auth.setup.js" message.

    Runs headless and skips silently if Playwright isn't installed (e.g. a
    pure-download-helper-only environment) -- browser_page-based tests would
    already fail loudly on their own in that case, this check just isn't the
    right layer for that particular gap.
    """
    try:
        import playwright  # noqa: F401
    except ImportError:
        return
    from tests.helpers.auth_probe import AuthSessionDeadError, probe_auth_session

    try:
        result = probe_auth_session("primary", headless=True)
    except AuthSessionDeadError as exc:
        pytest.exit(f"Auth session pre-flight check failed: {exc}", returncode=1)
        return
    if not result.ok:
        pytest.exit(
            f"Auth session pre-flight check failed: {result.message} "
            f"Re-run 'node tests/playwright/auth.setup.js' by hand for role "
            f"'primary', then re-run the suite. (Or diagnose visually: "
            f"python scripts/check_auth.py --headed)",
            returncode=1,
        )


@pytest.fixture(scope="session", autouse=True)
def _reset_test_state(settings):
    """Clear transient '_TEST_*' script-property toggles before this session's
    first test runs (gts-rvwu follow-up).

    A crashed or interrupted prior run can leave a toggle like
    '_TEST_FORCE_HOMEPAGE_ERROR' set — every doc opened afterwards then hits
    the add-on's error-fallback card, since these toggles are global to the
    GAS deployment rather than scoped to one test's doc. Runs once per pytest
    session, before any test executes.

    Deliberately does not touch DISCOVERY_*/TEAMSCOPE_FOLDER_* — those are
    memoized fixture caches meant to persist across sessions (see
    'reset_test_state' in src/TestFixtures.js for the full rationale).
    """
    from tests.helpers.fixture_invoke import invoke_fixture

    invoke_fixture("reset_test_state", "", settings, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def _purge_stale_test_docs(settings, _reset_test_state):
    """Bound the shared TEST corpus's growth by evicting aged-out 'Doc Not
    Found' rows before this session's first test runs (gts-4m7l).

    ArchiveManager's 24h grace window is correct for production but means
    every doc trashed by a prior pytest session lingers in Actions/DocData
    for a full day on the shared TEST deployment -- across a day of repeated
    runs, docCount (and so syncAll()'s real execution time) climbs steadily,
    eventually racing past the sync_all fixture's client-side read timeout
    (observed docCount 106 -> 171 in one session). Runs once per pytest
    session, after _reset_test_state, via the 'purge_stale_test_docs' GAS
    fixture (src/TestFixtures.js), which backdates every currently-'Doc Not
    Found' Actions row past the 24h window and then runs the unmodified
    production ArchiveManager.archive() sweep.
    """
    from tests.helpers.fixture_invoke import invoke_fixture

    invoke_fixture("purge_stale_test_docs", "", settings, timeout=120)


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
