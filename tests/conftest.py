"""Pytest configuration and shared fixtures."""
import datetime
import json
import os
import pathlib
import re

import pytest

from tests import duration_instrumentation as di
from scn.outcomes import classify

_SETTINGS_PATH = pathlib.Path(__file__).parent.parent / "local.settings.json"
_TEST_RESULTS = pathlib.Path(__file__).parent.parent / "test-results"

_pytest_config = None

# --- gts-u6ew.5 / H11: block new tracker-id-named test files at collection time -----
#
# >=11 existing test files encode a bead/ticket id in the filename (test_b7_,
# test_f3me1_, ...) instead of the behaviour the file covers. H11's rationale
# (docs/atdd/harness-design.md S9a) is that this structurally defeats ADR-0011's
# "enumerate the adjacent existing tests" step -- a slug tells a reader nothing about
# what the file exercises. The existing offenders are grandfathered here (renaming
# them is stage naming-cleanup, gts-u6ew.17, out of scope for this hook); this hook's
# only job is to stop a new one from joining the list.
#
# TRACKER_ID_ALLOWLIST is the single source of truth both this hook and any future
# audit must read -- do not duplicate this list elsewhere. It only shrinks (stage
# naming-cleanup removes entries as files are renamed); do not add to it without that
# stage's review.
TRACKER_ID_ALLOWLIST: frozenset[str] = frozenset({
    "test_f3me1_append_idempotency.py",
    "test_f3me2_run_fixture_idempotency.py",
    "test_hroj_diagnostics_backstop.py",
    "test_hztp_actionsnapshot_read_coverage.py",
    "test_adr0027_reference_document.py",
})

# A bead/ticket slug reliably mixes a digit into its short alnum token (bd's own
# short-id alphabet does this -- u6ew, 79dw, kkm7, zc0w, ... -- and harness-design.md's
# own H11 --ticket-pattern citation is `(?:\b(?:gts-)?[a-z0-9]{4}\b)`). No legitimate
# descriptive first-token among this suite's non-allowlisted test_*.py files contains a
# digit (checked against every current filename at authoring time: ai, ui, apt, doc,
# gas, poc, scn, bops, call, chip, epic, link, list, menu, seed, sync, team, view,
# admin, field, force, access, decode, ... none carry a digit) -- so "the first
# underscore-delimited token contains a digit" is a zero-false-positive proxy for
# "looks like a tracker id" against the current suite, without needing a dictionary of
# real words. It will not catch a future letters-only slug (e.g. a repeat of hroj/
# hztp/pulj/uuse's shape) -- that gap is accepted rather than risking false positives
# on real words; a human reviewer is still the backstop for that case.
_TRACKER_ID_SHAPE_RE = re.compile(r"^test_(?=[a-z0-9]*[0-9])[a-z0-9]{2,8}_")


class _TrackerIdBlockedFile(pytest.File):
    """A collectible standing in for an offending file -- collect() always fails.

    Using pytest's own file-collection hook (rather than raising inside
    pytest_collectstart) is what keeps this a normal, reported CollectError
    instead of an INTERNALERROR: pytest_collect_file is the documented
    extension point for "this file needs custom/blocked collection".
    """

    def collect(self):
        raise self.CollectError(
            f"{self.path.name}: filename looks like a bead/ticket slug (H11) -- name "
            "the file for the behaviour it covers, not a tracker id. If this is a "
            "deliberate, reviewed exception, add it to TRACKER_ID_ALLOWLIST in "
            "tests/conftest.py (the allowlist only shrinks per gts-u6ew.17 -- do not "
            "grow it casually)."
        )


def pytest_collect_file(file_path, parent):
    """H11: fail collection of a new tracker-id-shaped test filename.

    Runs ahead of module import, so an offending file's body never executes --
    it is reported as a collection error naming the file, same as a real
    ImportError would be. TRACKER_ID_ALLOWLIST (above) is the only carve-out.
    """
    name = file_path.name
    if not (name.startswith("test_") and name.endswith(".py")):
        return None
    if name in TRACKER_ID_ALLOWLIST:
        return None
    if _TRACKER_ID_SHAPE_RE.match(name):
        return _TrackerIdBlockedFile.from_parent(parent, path=file_path)
    return None


# --- gts-y1eg: progress counter + duration/baseline instrumentation state --
# Session-lifetime, single-process state; see duration_instrumentation.py for
# the pure logic.
#
# gts-xvgl (xdist): under `-n`, BOTH the worker process and the controller run
# pytest_runtest_logstart/logreport for the same test — the worker natively,
# the controller again when the worker's report is forwarded to it. Left
# ungated that double-counts everything: measured 132 JSONL records for 66
# tests, every nodeid twice, plus N+1 processes read-modify-WRITING the single
# tests/.pytest_duration_baseline.json through one fixed `.tmp` name
# (di.save_baseline replaces the whole file) — a last-writer-wins race that
# silently discards other workers' samples. `_duration_enabled` therefore gates
# the instrumentation off in WORKERS only (`workerinput` exists only there).
# The controller is a single process that sees every test exactly once, so it
# keeps doing the accounting: under `-n` the counter, the JSONL trend records
# and the baseline update all still work, and remain race-free. What is lost is
# only per-phase fidelity ordering — [n/total] counts completions, not starts.
_duration_enabled = True
_duration_total = 0
_duration_index_map: dict[str, int] = {}
_duration_next_index = 0
_duration_run_id = None
_duration_baseline: dict = {}
_duration_phases: dict[str, dict[str, float]] = {}
_duration_outcome: dict[str, str] = {}
# gts-u6ew.6/.7 (H6/H7): classification (PASS/ASSERTION_FAILURE/BOUNDARY_FAULT,
# from scn.outcomes.classify -- stamped onto the call-phase report's
# user_properties by pytest_runtest_makereport below) and the summed
# http.attempts user_property, read back here once teardown fires so
# build_record can carry both on the same JSONL record pytest_sessionfinish's
# H8 summary reads.
_duration_outcome_class: dict[str, str] = {}
_duration_attempts: dict[str, int] = {}


def pytest_configure(config):
    global _pytest_config, _duration_run_id, _duration_baseline, _duration_enabled
    _pytest_config = config
    # gts-xvgl: `workerinput` exists only on an xdist worker's config.
    _duration_enabled = not hasattr(config, "workerinput")
    _duration_run_id = datetime.datetime.now(datetime.timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    _duration_baseline = di.load_baseline() if _duration_enabled else {}


def pytest_collection_modifyitems(session, config, items):
    """Progress-counter total, plus gts-aqpk's tier classification.

    Tiering is one explicit opt-in marker (`no_live_session`, applied per
    module) with its complement derived here, rather than two hand-applied
    markers or a directory split:

    * `-m no_live_session` selects the fast/local tier -- and, because
      `_session_is_no_live_session` below sees an all-marked `session.items`
      once the deselection has happened, the four live-session autouse
      pre-flights skip themselves automatically. One marker does both jobs;
      a separate `local` marker would have to be kept in sync with it.
    * `live` is stamped here onto everything NOT carrying `no_live_session`,
      so `-m live` is exact and every collected item is classified by
      construction. A new test file added tomorrow with no marker at all
      lands in `live` -- the safe default (it pays the pre-flight and the
      round-trip cost it may or may not need) rather than silently joining a
      tier that skips the pre-flights it depends on.

    This hook runs ahead of pytest's own mark-expression deselection (conftest
    plugins are registered after, and so are called before, the builtin `mark`
    plugin), which is what makes `-m live` resolvable at all.
    """
    global _duration_total
    for item in items:
        if item.get_closest_marker("no_live_session") is None:
            item.add_marker(pytest.mark.live)
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
    if not _duration_enabled:
        return
    _duration_next_index += 1
    _duration_index_map[nodeid] = _duration_next_index
    _terminal_writeline(f"[{_timestamp()}] {di.format_start_line(_duration_next_index, _duration_total, nodeid)}")


def pytest_runtest_logreport(report):
    """gts-y1eg AC1-AC4: per-phase durations -> [n/total] FINISH line +
    flushed JSONL trend record + self-calibrating baseline update.

    Report-only: this never raises and never touches the test outcome — a
    failure anywhere in here must not mask the real pass/fail signal.
    """
    if not _duration_enabled or report.when not in ("setup", "call", "teardown"):
        return
    global _duration_baseline
    try:
        nodeid = report.nodeid
        phases = _duration_phases.setdefault(nodeid, {})
        phases[report.when] = report.duration
        if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
            _duration_outcome[nodeid] = report.outcome
        if report.when == "call":
            # gts-u6ew.6/.7 (H6/H7): pytest_runtest_makereport (below) has
            # already stamped these onto the call-phase report's
            # user_properties by the time this hook fires for it (pytest
            # calls makereport, THEN fires logreport with the report it
            # built) -- read them back here, once, rather than re-deriving.
            props = dict(report.user_properties)
            if "outcome_class" in props:
                _duration_outcome_class[nodeid] = props["outcome_class"]
            attempts = [
                int(v) for k, v in report.user_properties if k == "http.attempts"
            ]
            if attempts:
                _duration_attempts[nodeid] = sum(attempts)
        if report.when != "teardown":
            return

        phases = _duration_phases.pop(nodeid, {})
        outcome = _duration_outcome.pop(nodeid, report.outcome)
        outcome_class = _duration_outcome_class.pop(nodeid, None)
        attempts_total = _duration_attempts.pop(nodeid, None)
        index = _duration_index_map.pop(nodeid, _duration_next_index)
        entry = _duration_baseline.get(nodeid)
        baseline_s = entry["median_s"] if entry else None
        # H4 tier lookup: `report.keywords` carries every marker name as a
        # key, including `live`, which pytest_collection_modifyitems stamps
        # dynamically on every item lacking `no_live_session` (gts-aqpk) — so
        # this reads the same classification the tier split itself uses,
        # rather than re-deriving it.
        is_live = "live" in report.keywords

        record = di.build_record(
            run_id=_duration_run_id, index=index, total=_duration_total,
            nodeid=nodeid, outcome=outcome,
            setup_s=phases.get("setup", 0.0), call_s=phases.get("call", 0.0),
            teardown_s=phases.get("teardown", 0.0), baseline_s=baseline_s,
            is_live=is_live, outcome_class=outcome_class, attempts=attempts_total,
        )
        _terminal_writeline(f"[{_timestamp()}] {di.format_finish_line(record)}")
        di.append_jsonl(record)
        if outcome == "passed":
            _duration_baseline = di.update_baseline(_duration_baseline, nodeid, record["total_s"])
            di.save_baseline(_duration_baseline)
    except Exception:
        # Instrumentation must never mask or alter the real test result.
        pass


def pytest_sessionfinish(session, exitstatus):
    """H8 (gts-u6ew.8): print this run's execution failure rate, failed-
    wall-time share, and boundary-fault share -- the numbers that say
    whether a red run means "we broke something" or "the platform was
    down." Previously computable only by running
    $DEVSTANDARD/tools/test-suite-diagnostics.py offline over
    duration-log.jsonl after the fact; now emitted every run.

    Report-only, like the rest of this module's instrumentation: never
    raises, never touches exitstatus. Gated on `_duration_enabled` (gts-xvgl:
    only the xdist controller process, never a worker, does the duration
    accounting -- see that bead's note above `_duration_enabled`'s
    declaration), and filters duration-log.jsonl down to this run's own
    `_duration_run_id` before summarizing, so a run's numbers aren't diluted
    by history from earlier runs appended to the same file.
    """
    if not _duration_enabled:
        return
    try:
        if not di.LOG_PATH.exists():
            return
        records = []
        with open(di.LOG_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("run_id") == _duration_run_id:
                    records.append(rec)
        summary = di.summarize_run(records)
        _terminal_writeline(di.format_run_summary(summary))
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
    if report.when == "call":
        # gts-u6ew.6 (H6): classify this test's outcome (scn.outcomes.classify
        # -- the one owning helper, I12) and stamp it as a user_property, so
        # both the JUnit XML and tests/duration_instrumentation.py's per-test
        # JSONL record (pytest_runtest_logreport fires after this hook, on
        # this same report object) carry PASS/ASSERTION_FAILURE/BOUNDARY_FAULT
        # without a second classification path. A non-failed call phase
        # (passed or skipped) classifies as PASS -- the raw pytest outcome
        # ("passed"/"skipped") is preserved separately on the JSONL record's
        # existing `outcome` field, so nothing is lost; this property only
        # ever needs to answer "was this a boundary fault," which a skip
        # never is.
        exc = call.excinfo.value if (call.excinfo is not None and report.failed) else None
        report.user_properties.append(("outcome_class", classify(exc)))
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


def _session_is_no_live_session(session: pytest.Session) -> bool:
    """gts-2moy: True only when EVERY collected item carries
    `@pytest.mark.no_live_session`.

    Opt-in-to-skip, not opt-in-to-run (gts-85x3.1's safety net stays the
    default): a plain `pytest` invocation of an offline-only module (e.g.
    tests/test_document_export_harness.py) needs no live Google/GAS session
    and must not block on one, but a mixed run that pulls in even one
    unmarked (live-session) test still gets the full live-session preflight
    -- marking one file doesn't opt the whole suite out.

    `session.items` is only fully populated after collection; every caller
    here is a session-scoped autouse fixture, which pytest runs during the
    test-execution phase, after collection completes -- so this is always
    reading a finished list, never a partial one.
    """
    items = session.items
    if not items:
        return False
    return all(item.get_closest_marker("no_live_session") is not None for item in items)


@pytest.fixture(scope="session", autouse=True)
def _check_deployed_build(request):
    """gts-omoy: fail the whole run fast, before any lane does work, unless
    the TEST deployment reachable at webappTestUrl is serving the version and
    target this checkout last stamped via `pnpm run deploy:test`.

    The 2026-08-29 proximate cause was a stale bound script predating
    ADR-0023's ACT- read support, and the suite ran against it green-ish
    (`sync.scanned count:1`). `?cmd=version` answers ahead of every auth
    gate on both doGet and doPost (src/WebApp.js), so this is a bare HTTP GET
    -- no browser, no test token, no secret -- and runs before the (heavier,
    Playwright-based) auth-session probe below.
    """
    if _session_is_no_live_session(request.session):
        return
    settings = _load_settings()
    url = settings.get("webappTestUrl") or ""
    if not url:
        return
    from tests.helpers.version import check_deployed_build

    try:
        check_deployed_build(url)
    except RuntimeError as exc:
        pytest.exit(f"Deployed-build pre-flight check failed: {exc}", returncode=1)


@pytest.fixture(scope="session", autouse=True)
def _check_auth_session_alive(request):
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
    if _session_is_no_live_session(request.session):
        return
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


def _invoke_preflight_fixture(name, settings, **kwargs):
    """invoke_fixture, with GAS test-token rejection turned into a single
    pytest.exit instead of a raised exception (gts-d6nz).

    Both session-scoped autouse fixtures below (_reset_test_state,
    _purge_stale_test_docs) already make the first live GAS calls of the
    session, each carrying the real testToken -- gts-5959 root-caused a
    177-failure sweep to exactly this call rejecting the token
    ('test-token-unauthorized') while local.settings.json's cached
    testTokenExpiresAt was still in the future (a *second* deploy:test run,
    concurrent or later, silently overwrote the single server-side token
    value). Left as a bare raise, a session-scoped autouse fixture's setup
    failure is cached by pytest and replayed as an identical ERROR on every
    one of the suite's ~635 tests -- exactly the fan-out the incident
    reported. There is no additional live call here: this wraps the call
    these fixtures were already making, so it adds no per-test overhead
    (session-scoped, runs once, same two round trips as before).

    A test that constructs FixtureTokenError itself by calling invoke_fixture
    directly (tests/test_fixture_invoke_retry.py) never goes through this
    helper or these fixtures, so it is unaffected.
    """
    from tests.helpers.fixture_invoke import FixtureTokenError, invoke_fixture

    try:
        return invoke_fixture(name, "", settings, **kwargs)
    except FixtureTokenError as exc:
        pytest.exit(
            f"Test token pre-flight check failed ({name}): {exc} "
            "Run 'pnpm run deploy:test' to mint and register a fresh token, "
            "then re-run the suite.",
            returncode=1,
        )


@pytest.fixture(scope="session", autouse=True)
def _reset_test_state(request):
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

    gts-d6nz: this is also the suite's test-token pre-flight -- the first
    live call carrying the real testToken, before any test body runs. See
    _invoke_preflight_fixture for why a token rejection here exits the whole
    session instead of failing every test individually.

    gts-aqpk: `settings` is loaded inside the body, not requested as a fixture
    parameter. pytest resolves a fixture's arguments before it runs the body,
    so taking `settings` here made _load_settings() -- and therefore the
    existence of local.settings.json -- a hard precondition of EVERY test in
    the suite, including the fast/local tier that never makes a live call
    (measured: 626 errors with the file moved aside, all from this argument).
    The no_live_session early-return above is only reachable if nothing is
    eagerly resolved ahead of it.
    """
    if _session_is_no_live_session(request.session):
        return
    _invoke_preflight_fixture("reset_test_state", _load_settings(), timeout=60)


@pytest.fixture(scope="session", autouse=True)
def _purge_stale_test_docs(request, _reset_test_state):
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
    if _session_is_no_live_session(request.session):
        return
    _invoke_preflight_fixture("purge_stale_test_docs", _load_settings(), timeout=120)


@pytest.fixture(scope="session")
def test_sheet_id(settings):
    return settings["testSheetId"]


@pytest.fixture(scope="session")
def test_doc_id(settings, request):
    """Per-run clone of the master template doc.

    Creates a named clone at session start, yields the clone ID to all tests,
    then trashes the clone and restores the master at teardown. Both the
    master doc ID and the clone ID are threaded through as real parameters on
    every call — GAS holds no shared script property for either on this path
    (ADR-0006 §4); a script property is only in play for the bare, no-payload
    menu-driven equivalent (menuBeginTestSession/menuEndTestSession).

    Uses HTTP fixture invocation (invoke_fixture) — no browser required.

    gts-z55w: teardown is registered via request.addfinalizer — the same
    backstop ScenarioSession.new_doc() uses for its own clone (_deferred_trash,
    scn/session.py:556) — rather than left as code after `yield`. A finalizer
    callback is reachable directly by pytest's teardown machinery without
    depending on this generator being resumed past `yield`; 28
    `GActionSheet-Test-session-*` clones were found leaked in Drive (alive
    since 2026-06-11) from runs that never reached that point. The callback is
    idempotent (guarded by `_ended`) and swallows its own POST failure so a
    teardown-time network blip can't mask the real test failure that
    triggered teardown.
    """
    from tests.helpers.fixture_invoke import invoke_fixture

    master_doc_id = settings["testDocId"]
    result = invoke_fixture("begin_test_session", master_doc_id, settings, timeout=180)
    clone_id = result["data"]["cloneId"]

    _ended = {"done": False}

    def _end_session():
        if _ended["done"]:
            return
        _ended["done"] = True
        try:
            invoke_fixture(
                "end_test_session", clone_id, settings,
                extra={"masterDocId": master_doc_id}, timeout=120,
            )
        except Exception:
            pass

    request.addfinalizer(_end_session)

    yield clone_id


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
