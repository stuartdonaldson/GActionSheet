"""
test_link_preview.py — onLinkPreview card rendering + in-card status change.

Replaces the headed, human-instructed tests/test_interactive.py
(GTaskSheet-15e8, epic pw5x): GTaskSheet-cug8 (building on the native-bubble
finding of 39jk) found that placing the text cursor on the AI-N chip link via
Ctrl+F -> type -> Enter -> Escape (no mouse) fires the add-on's onLinkPreview
trigger server-side, and that re-placing the cursor after moving it away
renders the addons.gsuite.google.com CardService card — reproducible headless.
This corrects GTaskSheet-s9so's conclusion that onLinkPreview never fires for
the add-on's plain-hyperlink action chips under synthetic events; the gap was
the gesture (mouse hover) and the stale _CARD_IFRAME selector, not the chip
type.

Covers rwz AC1/AC2: the rendered card's header shows "AI-N: <action text>" and
a control whose URL carries the chip's globalId; then drives the in-card
status control (_setStatusFromPreview) and asserts the durable result.
"""
import pathlib
import time

import pytest

from scn.ai import ai
from scn.engine import CheckpointKind, Surface
from scn.reporter import emit_standalone_event
from scn.session import ScenarioSession
from scn.ui import UiDriver

SHEET = Surface.SHEET
INTEGRITY = CheckpointKind.INTEGRITY


@pytest.fixture(scope="module")
def browser_page(settings):
    """Launch headless Chromium with saved auth state.

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
            viewport={"width": 1400, "height": 950},
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


def test_link_preview_card_status_change(scn):
    """Cursor-place an AI-N chip to render its onLinkPreview card, then set
    its status to "In Progress" via the in-card control (GTaskSheet-cug8)."""
    seed = ai(action="Link-preview card status-change check")
    scn.append_paragraph(seed.as_text())
    scn.sync()

    rows = scn.find_sheet_actions()
    match = next((r for r in rows if "Link-preview card status-change check" in (r.action or "")), None)
    assert match is not None, f"seeded action not found after sync; rows={rows}"
    action_id = match.action_id
    assert action_id, f"synced action has no AI-N id: {match}"

    card = scn.ui.open_link_preview(action_id, timeout="120s")

    # rwz AC1: card header shows "AI-N: <action text>"
    body_text = card.frame.locator("body").first.inner_text()
    assert f"{action_id}:" in body_text, f"card header missing {action_id!r}: {body_text!r}"

    # rwz AC2: the native #docs-link-bubble (GTaskSheet-39jk) carries the
    # chip's preview URL — the CardService card body itself binds its status
    # buttons via onClick actions, not a plain href/data-url.
    # By the time the card iframe renders (the SECOND cursor placement, per
    # open_link_preview), the native bubble from the FIRST placement may have
    # already dismissed and its replacement may not have re-rendered yet --
    # poll briefly rather than checking once.
    # GTaskSheet-0v61/8ca9f0a: chip URLs encode docId+ain as separate query
    # params (?cmd=preview&docId=...&ain=AI-N), not a combined globalId=.
    deadline = time.monotonic() + 8.0
    bubble, bubble_url = None, ""
    while time.monotonic() < deadline:
        bubble = scn.ui._page.evaluate("""() => {
            const b = document.querySelector('#docs-link-bubble.appsElementsLinkPreview');
            if (!b) return null;
            const a = b.querySelector('a[href*="cmd=preview"], [data-url*="cmd=preview"]');
            return { href: a ? (a.href || null) : null, dataUrl: a ? a.getAttribute('data-url') : null };
        }""")
        bubble_url = (bubble or {}).get("href") or (bubble or {}).get("dataUrl") or ""
        if f"docId={scn.doc_id}" in bubble_url and f"ain={action_id}" in bubble_url:
            break
        scn.ui._page.wait_for_timeout(500)
    assert f"docId={scn.doc_id}" in bubble_url and f"ain={action_id}" in bubble_url, (
        f"native link-preview bubble missing docId/ain for {scn.doc_id}/{action_id}: {bubble!r}"
    )

    scn.ui.set_status(card, "In Progress")

    # entry_point: in-card status control (_setStatusFromPreview -> _scheduleSheetUpdate)
    # — durable-state assertion that the sheet row's status converged (GTaskSheet-rz4k.3)
    def _status_converged() -> str | None:
        row = next((r for r in scn.find_sheet_actions() if r.action_id == action_id), None)
        status_now = (row.status or "").lower() if row else None
        if status_now != "in progress":
            return (
                f"expected {action_id} status 'In Progress' after in-card status change, "
                f"got {status_now!r}"
            )
        return None

    scn.sync()
    scn.expect_callable(
        _status_converged, on=SHEET, tag="[cug8 link-preview status]",
        entry_point="_setStatusFromPreview",
    )
    scn.checkpoint(INTEGRITY)
