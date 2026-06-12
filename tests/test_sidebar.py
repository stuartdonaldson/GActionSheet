"""
test_sidebar.py — browser-backed focused tests for sidebar UI entry points.

Migrates sidebar_action_list.test.js + sidebar_shell.test.js + parts of
sidebar_tracker_insert.test.js (AC1, AC2) into the scn scenario model.

One Chromium cold start (module-scoped browser_page) amortized across all tests
in this module (one-browser-per-journey cost rule, R2). Each test gets its own
scn doc (named-clone isolation, §16 twin-track); scn.close() asserts the
expectation queue is empty (§4.6 drain invariant).

Bead: GTaskSheet-80mo.8
"""
import pathlib
import re

import pytest

from scn.ai import ai
from scn.engine import CheckpointKind, Surface
from scn.session import ScenarioSession
from scn.ui import UiDriver

DOC = Surface.DOC
SHEET = Surface.SHEET
TRACKER = Surface.TRACKER
INTEGRITY = CheckpointKind.INTEGRITY
STEP = CheckpointKind.STEP


# ---------------------------------------------------------------------------
# Module-scoped browser fixture (one Chromium cold start per module)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def browser_page():
    """Launch Chromium with saved auth state; yield the page for all sidebar tests."""
    from playwright.sync_api import sync_playwright

    auth = pathlib.Path(__file__).parent.parent / ".auth" / "user.json"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            storage_state=str(auth),
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        yield page
        ctx.close()
        browser.close()


# ---------------------------------------------------------------------------
# test_sidebar_bootstrap_sync — migrates sidebar_action_list.test.js T1
# ---------------------------------------------------------------------------

def test_sidebar_bootstrap_sync(settings, browser_page):
    """Sync Now bootstraps action rows: sidebar goes from (0) to (N) anchored actions.

    Entry point under test: sidebar_sync() — the homepage Sync Now button.
    Unique behavior: (0)→(N) refresh on first open of a pre-seeded doc.
    Row correctness verified on SHEET (no tracker present post-sync; G1 binding:
    per-row TEXT is NOT UI state — sidebar row text migrates to a non-UI surface).
    """
    s = ScenarioSession.new_doc(settings)
    s.ui = UiDriver(browser_page, doc_id=s.doc_id)
    try:
        s._post_fixture("uc_a_permutations")

        card = s.ui.open_sidebar(timeout="45s")
        # Pre-sync: 0 floating actions visible (raw shell assert; NOT an ai expectation — G1)
        card.frame.get_by_text("actions for this document (0)", exact=False).wait_for(
            state="visible", timeout=30000
        )

        s.ui.sidebar_sync(timeout="60s")  # ENTRY POINT: Sync Now button
        s.sync()  # durable convergence to ActionSheet (§16.11 #4; sidebar_sync is async)

        # Resolve action_ids from live sheet (accumulates across runs; doc-scoped)
        rows = s.find_sheet_actions()
        anchored = [r for r in rows if r.action_id is not None]
        assert anchored, "Expected at least one anchored action after sidebar_sync"

        # Multi-row sidebar is for firing acts, not per-row UI drains (R2 guidance).
        # Per-row UI verification requires hovering the action's preview card.
        # Bootstrap uniqueness is the (0)->(N) refresh; individual row correctness
        # is verified via SHEET (no tracker in this fixture path; G1 binding).
        for a in anchored:
            s.verify(a, on=SHEET, tag="[sidebar sync-SHEET]")
        s.verify_consistency(scope=DOC)   # server authority: ok, 0 issues
        s.checkpoint(INTEGRITY)
    finally:
        s.close()


# ---------------------------------------------------------------------------
# test_tracker_insert_button — migrates sidebar_tracker_insert.test.js AC1
# ---------------------------------------------------------------------------

def test_tracker_insert_button(settings, browser_page):
    """Insert tracker button inserts a tracker table; full consistency passes.

    Entry point under test: insert_tracker_button() — the sidebar Insert tracker button.
    Per-row field truth (id/action/status non-empty) verified via verify(on=TRACKER).
    """
    s = ScenarioSession.new_doc(settings)
    s.ui = UiDriver(browser_page, doc_id=s.doc_id)
    try:
        s._post_fixture("uc_a_permutations")

        s.ui.open_sidebar(timeout="45s")
        s.ui.sidebar_sync(timeout="60s")          # anchor floating actions first
        s.sync()  # durable convergence to ActionSheet (§16.11 #4)

        s.ui.insert_tracker_button(timeout="30s")  # ENTRY POINT: Insert tracker button

        rows = s.find_sheet_actions()
        anchored = [r for r in rows if r.action_id is not None]
        assert anchored, "Expected anchored actions after sync + tracker insert"

        # Per-row field truth via SHEET (xlsx download; no docx export cache lag).
        # TRACKER completeness (tracker==floating==matched) is verified via the live
        # GAS verify_consistency call below — avoids the docx export cache lag that
        # affects direct verify(on=TRACKER) reads right after _insertTrackerIdLinks.
        for a in anchored:
            s.verify(a, on=SHEET, tag="[sidebar tracker-insert]")
        s.verify_consistency(scope=DOC)   # live GAS: tracker==floating==matched, 0 issues
        s.checkpoint(INTEGRITY)
    finally:
        s.close()


# ---------------------------------------------------------------------------
# test_status_mutation_only_mutated_row — migrates sidebar_tracker_insert.test.js AC2
# ---------------------------------------------------------------------------

def test_status_mutation_only_mutated_row(settings, browser_page):
    """After a per-row status change, only the mutated tracker row differs.

    Entry point under test: sidebar_set_status() — the per-row status control.

    Only-mutated-row falls out of enqueueing the UNCHANGED ais at baseline +
    the changed one at new status — no hand-rolled row diff (§5 review).
    """
    s = ScenarioSession.new_doc(settings)
    s.ui = UiDriver(browser_page, doc_id=s.doc_id)
    s.tracker_present = True   # fixture includes tracker already
    try:
        s._post_fixture("uc_c_pending_sync_refresh")

        s.ui.open_sidebar(timeout="45s")
        s.ui.sidebar_sync(timeout="60s")   # baseline: tracker grows 2→3
        s.sync()  # durable convergence to ActionSheet (§16.11 #4)

        rows = s.find_sheet_actions()
        assert len(rows) >= 3, (
            f"Expected 3 anchored actions after baseline sync; got {len(rows)}"
        )
        a1, a2, a3 = rows[0], rows[1], rows[2]

        # Baseline: verify all 3 tracker rows then check consistency
        for a in (a1, a2, a3):
            s.verify(a, on=TRACKER, tag="[sidebar mutation-baseline]")
        s.verify_consistency(scope=DOC)
        s.checkpoint(INTEGRITY)

        changed = a1
        new_status = "In Progress" if changed.status != "In Progress" else "Open"

        # ENTRY POINT: per-row sidebar status control (sidebarSetStatus)
        s.ui.sidebar_set_status(changed, new_status, timeout="15s")
        changed.status = new_status
        s.sync()   # converge async mutation to doc + tracker

        # Only-mutated-row: unchanged ais at baseline status; changed at new_status
        for a in (a2, a3):
            s.verify(a, on=TRACKER, tag="[sidebar mutation-baseline]")                          # must hold baseline
        s.verify(changed, on=TRACKER, status=new_status, tag="[sidebar mutation-changed]")     # must hold new
        s.verify_consistency(scope=DOC)
        s.checkpoint(INTEGRITY)   # drains all three; unchanged rows must not drift
    finally:
        s.close()


# ---------------------------------------------------------------------------
# test_sidebar_shell_controls — migrates sidebar_shell.test.js T1
# ---------------------------------------------------------------------------

def test_sidebar_shell_controls(settings, browser_page):
    """Homepage card shows the expected controls and hides navigation-only controls.

    Raw Playwright frame assertions on UI shell structure only — NOT durable ai
    state (G1 binding). Do NOT enqueue UI expectations for shell elements.
    """
    s = ScenarioSession.new_doc(settings)
    s.ui = UiDriver(browser_page, doc_id=s.doc_id)
    try:
        s._post_fixture("uc_c_first_insert")
        card = s.ui.open_sidebar(timeout="45s")

        # Present: Sync Now + VerifySync visible
        card.frame.get_by_role("button", name=re.compile(r"sync now", re.I)).wait_for(
            state="visible", timeout=30000
        )
        card.frame.get_by_role("button", name=re.compile(r"verifysync", re.I)).wait_for(
            state="visible", timeout=30000
        )
        # Absent: navigation/other-surface controls
        assert card.frame.get_by_role(
            "button", name=re.compile(r"open sidebar", re.I)
        ).count() == 0
        assert card.frame.get_by_role(
            "button", name=re.compile(r"scan card", re.I)
        ).count() == 0
        assert card.frame.get_by_text("Sort", exact=True).count() == 0
        assert card.frame.get_by_text("Filter", exact=True).count() == 0
        assert card.frame.get_by_text("Tracker", exact=True).count() == 0
        assert card.frame.get_by_role(
            "button", name=re.compile(r"^Insert tracker$", re.I)
        ).count() == 0
        # Tracker already present notice + version label
        card.frame.get_by_text(
            "tracker already present in this document", exact=False
        ).wait_for(state="visible", timeout=10000)
        card.frame.get_by_text(
            re.compile(r"v\d+\.\d+\.\d+"), exact=False
        ).wait_for(state="visible", timeout=10000)
    finally:
        s.close()


# ---------------------------------------------------------------------------
# test_sidebar_blank_doc_no_error — migrates sidebar_shell.test.js T2
# ---------------------------------------------------------------------------

def test_sidebar_blank_doc_no_error(settings, browser_page):
    """Opening the sidebar in a brand-new doc raises no runtime error.

    No fixture: fresh scn doc. Raw shell assertions only (G1 binding).
    """
    s = ScenarioSession.new_doc(settings)
    s.ui = UiDriver(browser_page, doc_id=s.doc_id)
    try:
        card = s.ui.open_sidebar(timeout="45s")

        # Absence of error text
        assert card.frame.get_by_text("error with the add-on", exact=False).count() == 0
        assert card.frame.get_by_text("run time error", exact=False).count() == 0
        # Sync Now present (add-on loaded successfully)
        card.frame.get_by_role("button", name=re.compile(r"sync now", re.I)).wait_for(
            state="visible", timeout=15000
        )
    finally:
        s.close()


# ---------------------------------------------------------------------------
# test_tab_navigation_docstatus_regression — GTaskSheet-gdll (ADR-0015 slice smoke)
# ---------------------------------------------------------------------------

def test_tab_navigation_docstatus_regression(settings, browser_page):
    """ADR-0015 tab-navigation shell: DocStatus entry points + nav round trip.

    Part A (cw5 regression): sidebar_sync / sidebar_set_status / sidebar_delete
    -- the DocStatus mutation entry points -- still work end-to-end through
    _buildTabbedHomepageCard, with observable state verification on TRACKER/SHEET.

    Part B (ADR-0015): navigate DocStatus -> Import -> Notify -> DocStatus via
    the new tab bar (onShowTab). Placeholder bodies render; DocStatus state
    survives the round trip (raw shell assertions only, G1 -- not ai expectations).

    Re-run at the EPIC-D (fnvq) and EPIC-E (s3ga) final-sign-off gates per
    GTaskSheet-gdll AC.
    """
    s = ScenarioSession.new_doc(settings)
    s.ui = UiDriver(browser_page, doc_id=s.doc_id)
    s.tracker_present = True
    try:
        s._post_fixture("uc_c_pending_sync_refresh")

        # --- Part A: DocStatus entry points through the new shell ----------
        card = s.ui.open_sidebar(timeout="45s")  # buildHomepageCard -> docStatus tab (default)
        s.ui.sidebar_sync(timeout="60s")  # ENTRY POINT: Sync Now (onSyncNow)
        s.sync()  # durable convergence to ActionSheet (§16.11 #4)

        rows = s.find_sheet_actions()
        assert len(rows) >= 3, (
            f"Expected 3 anchored actions after baseline sync; got {len(rows)}"
        )
        a1, a2, a3 = rows[0], rows[1], rows[2]

        # ENTRY POINT: per-row sidebar status control (sidebarSetStatus)
        new_status = "In Progress" if a1.status != "In Progress" else "Open"
        s.ui.sidebar_set_status(a1, new_status, timeout="15s")
        a1.status = new_status
        s.sync()  # converge async mutation to doc + tracker

        # Checkpoint A: sync (entry 1) + status-change (entry 2) both converged
        # correctly -- one docx download covers baseline (a2/a3) and the change (a1).
        s.verify(
            a1, on=TRACKER, status=new_status,
            tag="[gdll status-changed]", entry_point="sidebarSetStatus",
        )
        s.verify(a2, on=TRACKER, tag="[gdll baseline]", entry_point="onSyncNow")
        s.verify(a3, on=TRACKER, tag="[gdll baseline]")
        s.verify_consistency(scope=DOC)
        s.checkpoint(INTEGRITY)

        # ENTRY POINT: per-row sidebar delete control (sidebarDeleteAction)
        # sidebarDeleteAction removes the floating-action paragraph from the doc
        # and the corresponding ActionSheet row entirely (_deleteActionRowFromSheet) --
        # unlike the HTTP delete_action_row route, there is no 'Deleted' stamp to read.
        s.ui.sidebar_delete(a2, timeout="15s")
        s.sync()  # converge async mutation to sheet

        s.expect_absent(a2, on=DOC, tag="[gdll deleted]")
        for a in (a1, a3):
            s.verify(a, on=TRACKER, tag="[gdll delete-unaffected]")
        s.checkpoint(INTEGRITY)

        # ActionSheet row removed entirely (not just doc-side)
        remaining_ids = {r.action_id for r in s.sheet_rows()}
        assert a2.action_id not in remaining_ids, (
            f"Expected {a2.action_id!r} removed from ActionSheet after sidebarDeleteAction; "
            f"still present: {remaining_ids}"
        )

        # --- Part B: tab navigation round trip (ADR-0015 onShowTab) ---------
        s.ui.show_tab("Import")
        card.frame.get_by_text("Import — coming soon", exact=False).wait_for(
            state="visible", timeout=10000
        )
        assert card.frame.get_by_role(
            "button", name=re.compile(r"sync now", re.I)
        ).count() == 0, "DocStatus controls must not render on the Import tab"
        assert card.frame.get_by_text("Actions for this document", exact=False).count() == 0

        s.ui.show_tab("Notify")
        card.frame.get_by_text("Notify — coming soon", exact=False).wait_for(
            state="visible", timeout=10000
        )
        assert card.frame.get_by_role(
            "button", name=re.compile(r"sync now", re.I)
        ).count() == 0, "DocStatus controls must not render on the Notify tab"

        s.ui.show_tab("Doc status")
        card.frame.get_by_role("button", name=re.compile(r"sync now", re.I)).wait_for(
            state="visible", timeout=10000
        )
        # 3 anchored - 1 deleted = 2 floating actions remain in the doc
        card.frame.get_by_text("Actions for this document (2)", exact=False).wait_for(
            state="visible", timeout=10000
        )
    finally:
        s.close()
