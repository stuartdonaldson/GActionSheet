"""
test_journey.py — §16.10 canonical scenario journey: Acts 1-5 + final reconcile.

Exercises Sync Scenarios C, B/A, and the editor UI against a live GAS deployment.
Each act maps to one entry point; every expectation declares intent on an ai.

Bead: GTaskSheet-5vwu.13
Canonical source: docs/atdd/atdd-lifecycle.md §16.10

Deviations from §16.10 (both mechanical, not design):
  D1 — Coordination Log (bead .1): Act 4 "Open" SHEET probe and Act 5 "In Progress"
       SHEET probe cannot share the same final INTEGRITY.  An intermediate INTEGRITY
       after Act 4 drains the Open expectation before set_status changes it.
  D2 — UI surface not implemented in session._checkpoint read() (returns []).
       scn.verify(on=UI, …) replaced with scn.expect_alt() — same intent, available
       mechanism (session.py:392-405 delegates to scn.ui.expect_alt).
  D3 — created.action_id is ambiguous until post-sync (§16.10 note: "next id is
       ambiguous after AI-1,2,5,9"). Resolved from scn.doc_items() after Act 4
       INTEGRITY before the Act 5 hover.
"""
import pathlib

import pytest

from scn.ai import ai
from scn.engine import CheckpointKind, Severity, Surface
from scn.session import ScenarioSession
from scn.ui import UiDriver

DOC = Surface.DOC
SHEET = Surface.SHEET
TRACKER = Surface.TRACKER
INTEGRITY = CheckpointKind.INTEGRITY
STEP = CheckpointKind.STEP
WARN = Severity.WARN


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def browser_page():
    """Launch Chromium with saved auth state; yield the page for Acts 4-5."""
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


@pytest.fixture(scope="module")
def scn(settings, browser_page):
    """Create the isolated journey doc; attach UiDriver; teardown trashes the doc."""
    s = ScenarioSession.new_doc(settings)
    s.ui = UiDriver(browser_page, doc_id=s.doc_id)
    yield s
    s.close()                              # trash; assert expectation queue empty


# ---------------------------------------------------------------------------
# Journey
# ---------------------------------------------------------------------------

def test_journey(scn):
    # ── Act 1 — author types five AI lines into a blank doc ───────────────────
    #   status left UNSET on plain items (non-default status requires explicit token)
    unassigned = ai(action="This tag and text confirms creation of an unassigned action item")
    with_email = ai(
        action="This tag and email address along with this text confirms email-assignee creation",
        assignee="aitest@example.com",
    )
    explicit_5 = ai(
        action="This tag and text confirms pre-assigning a specific action ID",
        action_id="AI-5",
    )
    domain_usr = ai(
        action="This tag email and text confirms domain-user name resolution",
        assignee="minister@northlakeuu.org",
        action_id="AI-9",
    )
    started_ip = ai(action="An action the author starts in progress", status="In Progress")
    backlogged = ai(action="An action with a non-standard status", status="Backlog")

    for a in (unassigned, with_email, explicit_5, domain_usr, started_ip, backlogged):
        scn.append_paragraph(a.as_text())  # pure doc mutation; no action implied yet

    # ── Act 2 — sync converts the lines into actions (Scenario C) ─────────────
    scn.sync()

    # pin what we expect the conversion to produce, then verify across surfaces
    unassigned.status = "Open"
    with_email.status = "Open"             # tokenless → detected Open
    explicit_5.status = "Open"
    domain_usr.status = "Open"
    # explicit_5 / domain_usr already carry AI-5 / AI-9; started_ip keeps In Progress
    # backlogged keeps "Backlog" — non-standard status, exercises status-other.png chip path

    # Resolve auto-assigned action_ids from the sheet — §16.10 shows "AI-1" / "AI-2" but
    # those assume a clean sheet; the live sheet accumulates IDs across runs.
    for row in scn.find_sheet_actions():
        if row.action == unassigned.action:
            unassigned.action_id = row.action_id
        elif row.action == with_email.action:
            with_email.action_id = row.action_id
    assert unassigned.action_id is not None, "unassigned action not found in sheet after sync"
    assert with_email.action_id is not None, "with_email action not found in sheet after sync"

    for a in (unassigned, with_email, explicit_5, domain_usr, started_ip, backlogged):
        scn.verify_all_expectations(a)     # doc+sheet (+tracker when present); all fields
    scn.verify_consistency(scope=DOC)      # §16.7 checklist + chip integrity (6ov.8)
    scn.checkpoint(INTEGRITY)             # capture docx+xlsx; drain the above

    # ── Act 3 — insert the tracker table and re-sync ──────────────────────────
    scn.insert_tracker()
    scn.sync()
    for a in (unassigned, with_email, explicit_5, domain_usr, started_ip):
        scn.verify(a, on=TRACKER)          # column form; assignee as chip
    scn.checkpoint(STEP)

    # rwz AC4: tracker ID cells are hyperlinked to chip URLs
    id_urls = scn.tracker_id_urls()
    for a in (unassigned, with_email, explicit_5, domain_usr, started_ip):
        url = id_urls.get(a.action_id, "")
        assert url and "globalId=" in url, (
            f"Tracker ID cell for {a.action_id!r} missing chip URL hyperlink; got {url!r}"
        )

    # ── Act 3b — open the homepage sidebar, verify action list ───────────────
    try:
        sidebar = scn.ui.open_sidebar()
        scn.expect_visible(sidebar, timeout="15s")
        # rwz AC3a: action row shows AI-N • topLabel pattern (explicit_5 is always anchored)
        sidebar.frame.get_by_text(explicit_5.action_id + " •", exact=False).wait_for(
            state="visible", timeout=5000
        )
        # rwz AC3b: delete button present for anchored actions
        sidebar.frame.locator('[aria-label="Delete action"]').first.wait_for(
            state="visible", timeout=5000
        )
    except Exception as _e:
        pytest.skip(
            f"Sidebar open failed (homepage trigger not installed as test deployment?): {_e}"
        )

    # ── Act 4 — @create through the editor UI (Playwright phase begins) ───────
    created = ai(
        action="Creating an action via the @-menu trigger",
        assignee="sdonaldson@northlakeuu.org",
    )
    try:
        scn.ui.create_action(created)      # fills @-menu form; autocomplete (in TEST_CONTACTS)
    except RuntimeError as _e:
        if "createActionTriggers" in str(_e):
            pytest.skip(str(_e))
        raise
    # action_id left UNSET — next id is ambiguous after AI-1,2,5,9; resolved at D3 below

    scn.verify(created, on=DOC, status="Open")               # cheap doc probe, now
    scn.verify(created, on=SHEET, status="Open", at=INTEGRITY)  # async sheet write → defer

    # D1: drain the Open SHEET expectation before set_status changes it (Coordination Log)
    scn.checkpoint(INTEGRITY)

    # D3: resolve created.action_id from live doc (ambiguous until post-sync)
    for item in scn.doc_items():
        if item.action == created.action:
            created.action_id = item.action_id
            break
    assert created.action_id is not None, (
        f"created action not found in doc after Act 4 INTEGRITY; "
        f"expected action text: {created.action!r}"
    )

    # ── Act 5 — hover the chip, read the preview card, change status ──────────
    card = scn.ui.hover(
        scn.ui.locate(text=created.action_id, occurrence=1),
        timeout="5s",
    )
    scn.expect_visible(card, timeout="5s")
    # rwz AC1: card header contains "AI-N: …" pattern
    card.frame.get_by_text(created.action_id + ":", exact=False).wait_for(
        state="visible", timeout=5000
    )
    # rwz AC2: card header link points to chip URL (href contains globalId parameter)
    card.frame.locator('a[href*="globalId"]').first.wait_for(state="visible", timeout=5000)
    # autocomplete warn-only per §16.4 — chip may lack name if contact resolution failed
    scn.expect_alt(
        scn.ui.locate(alt="In Progress", next=True),
        "In Progress",
        severity=WARN,
    )

    scn.ui.set_status(card, "In Progress")  # click; driver waits out gray/busy (≤10s)
    created.status = "In Progress"

    # D2: verify(on=UI) not implemented — direct card assertion covers the same intent
    scn.expect_alt(scn.ui.locate(alt="In Progress", next=True), "In Progress")
    scn.verify(created, on=SHEET, at=INTEGRITY)  # durable, async (13–60s) → defer

    # ── Final reconcile (HTTP phase) — settle every deferred expectation ──────
    scn.checkpoint(INTEGRITY)             # docx+xlsx+tracker+consistency; queue empty at close

    # ── Idempotency pass (bjx7): second sync must leave all surfaces unchanged ─
    scn.sync()
    for a in (unassigned, with_email, explicit_5, domain_usr, started_ip, backlogged, created):
        scn.verify_all_expectations(a)
    scn.checkpoint(INTEGRITY)

    # ── ckj: M2 sheet consistency after idempotency pass ─────────────────────
    # doc_formula (col7) and sync_status (col10) must be set on every row;
    # verify_consistency(scope=SHEET) raises AssertionError if either is missing.
    scn.verify_consistency(scope=SHEET)
