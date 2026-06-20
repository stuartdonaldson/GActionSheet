"""
test_ui_smoke.py — fast (<1 min) web-UI surface smoke (GTaskSheet-80mo.17).

Covers the high-risk UI entry points in one short scenario so breakage is caught
without the full ~10-minute journey:

    new doc → floating action → @action (@-menu) → sidebar sync → insert table

Built entirely from the existing scenario primitives (ScenarioSession, UiDriver,
ai) — no bespoke helpers. Asserts durable invariants only (smoke discipline,
CLAUDE.md ATDD slice rules). Every act is guarded by the default-on fail-fast
monitor: an unexpected GAS response or a `*.error` log entry aborts at the act.

Run:  npm run test:ui-smoke     (streams the live trace; -s enabled)
"""
import pathlib
import time

import pytest

from scn.ai import ai
from scn.reporter import emit_standalone_event
from scn.session import ScenarioSession
from scn.ui import UiDriver


@pytest.fixture(scope="module")
def browser_page(settings):
    """Launch Chromium with saved auth state; yield the page for the UI acts.

    Module-scoped, so launch/teardown is outside any single test's Reporter
    lifetime — timed and emitted directly via emit_standalone_event
    (GTaskSheet-j8cn gap-instrumentation).
    """
    from playwright.sync_api import sync_playwright

    auth = pathlib.Path(__file__).parent.parent / ".auth" / "user.json"
    run_id = pathlib.Path(__file__).stem
    t0 = time.monotonic()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
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


@pytest.fixture
def scn(settings, browser_page, request):
    """Fresh isolated doc + attached UiDriver; teardown trashes the doc."""
    s = ScenarioSession.new_doc(settings, request=request)
    s.ui = UiDriver(browser_page, doc_id=s.doc_id)
    yield s
    s.close()


@pytest.mark.smoke
def test_ui_smoke(scn):
    # 1. new doc — provided by the scn fixture (begin_journey_session).

    # 2. floating action — author a plain AI line (fast HTTP author act).
    floating = ai(action="Smoke: a floating action authored before sync")
    scn.append_paragraph(floating.as_text())

    # 2.5. Warm the add-on before the @-menu act: open the homepage sidebar so the
    # editor add-on (createActionTriggers provider + Create-action form) is
    # initialised. On a stone-cold add-on the @-menu provider and the form render
    # are slow AND run-to-run variable (GTaskSheet-1rqm) — the full journey never
    # hits this because Act 0/3b open the sidebar before Act 4's create_action.
    scn.ui.open_sidebar()

    # 3. @action — high-risk @-menu Create-action entry point.
    created = ai(
        action="Smoke: action created via the @-menu trigger",
        assignee="aitest@example.com",
    )
    scn.ui.create_action(created)

    # 4. sidebar sync — high-risk entry point; converts author + @action to rows.
    scn.ui.sidebar_sync()

    # 5. insert table — high-risk entry point (tracker inserted/refreshed).
    scn.ui.insert_tracker_button()

    # Durable-invariant smoke checks only. Converge once, then assert.
    scn.sync()
    rows = scn.find_sheet_actions()
    assert len(rows) >= 2, (
        f"expected >=2 actions after author + @action + sync, got {len(rows)}: {rows}"
    )
    assert scn.tracker_id_urls(), "tracker table has no ID-linked rows after insert"
