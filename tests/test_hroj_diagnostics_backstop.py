"""gts-hroj backstop proof — diagnostics-ordering fix (F9).

Not a normal regression test: it deliberately fails so the UI-failure-
diagnostics hook (tests/conftest.py::pytest_runtest_makereport, GTaskSheet-3tkf)
fires, and the point of the exercise is to *read* the artifact it produces
(screenshot + captured button list), not to assert inside this test — that's
the same "human reviews the failure" contract the hook itself was built for.

Skipped by default (an always-failing test can't live in the regular suite).
To reproduce the backstop proof:

    # Run 1 — reproduces the pre-fix bug: trash happens directly inside this
    # test's own `finally:`, i.e. during the call phase, before the
    # diagnostics hook (report.when == "call") ever gets to run. Expect the
    # captured button list to show Drive's post-trash chrome
    # ("Go to Docs home screen" / "Take out of trash").
    HROJ_BACKSTOP_SIMULATE_BUG=1 pytest -p no:cacheprovider \\
        tests/test_hroj_diagnostics_backstop.py -m hroj_backstop --no-skip -v

    # Run 2 — the actual fix: trashing is deferred to the pytest finalizer
    # registered by ScenarioSession.new_doc(request=request) (scn/session.py),
    # which runs in the teardown phase, after the hook has already fired.
    # Expect the captured button list to show the live Docs editor UI, not
    # trash chrome.
    pytest -p no:cacheprovider tests/test_hroj_diagnostics_backstop.py \\
        -m hroj_backstop --no-skip -v

See plan-0806-flake-recovery.md S2 Result for the two log paths and the
observed diff between these two runs.

`--no-skip` is a local marker convention, not a real pytest flag — the
`skip` below is unconditional; comment it out (or pass -k with a direct
nodeid and delete the skip line) to actually execute either variant. Left
unconditional so this file is inert in normal collection/CI runs.
"""
import os
import time

import pytest

from scn.reporter import emit_standalone_event
from scn.session import ScenarioSession, resolve_auth_file
from scn.ui import UiDriver


@pytest.fixture
def browser_page(settings, request):
    """Same shape as tests/test_import.py's fixture of the same name — not
    shared via conftest.py, so duplicated here rather than importing a test
    module. Throwaway tool; see module docstring."""
    from playwright.sync_api import sync_playwright

    auth = resolve_auth_file()
    run_id = request.node.name
    t0 = time.monotonic()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=os.environ.get("PWHEADFUL") != "1")
        ctx = browser.new_context(
            storage_state=str(auth),
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        emit_standalone_event(settings, run_id=run_id, name="browser_launch", dur_s=time.monotonic() - t0)
        yield page
        t1 = time.monotonic()
        ctx.close()
        browser.close()
        emit_standalone_event(settings, run_id=run_id, name="browser_teardown", dur_s=time.monotonic() - t1)


@pytest.mark.hroj_backstop
@pytest.mark.skip(
    reason="gts-hroj backstop tool: always fails by design. "
    "See module docstring for how to run each variant manually."
)
def test_hroj_backstop_diagnostics_capture_precedes_trash(settings, browser_page, request):
    scn = ScenarioSession.new_doc(settings, request=request)
    scn.ui = UiDriver(browser_page, doc_id=scn.doc_id)
    scn.ui.show_tab("Import")  # forces real navigation to the doc + sidebar
    try:
        assert False, "gts-hroj deliberate failure — backstop proof for diagnostics ordering"
    finally:
        if os.environ.get("HROJ_BACKSTOP_SIMULATE_BUG") == "1":
            # Pre-fix bug repro ONLY — trash inline, beating the diagnostics
            # hook to it, exactly like the pre-fix test bodies this bead
            # fixed (see tests/test_import.py etc. before this change).
            try:
                scn._post_route("end_journey_session", {"docId": scn.doc_id})
            except Exception:
                pass
        scn.engine.close()
