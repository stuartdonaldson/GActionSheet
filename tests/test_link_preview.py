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

import pytest

from scn.ai import ai
from scn.session import ScenarioSession
from scn.ui import UiDriver


@pytest.fixture(scope="module")
def browser_page():
    """Launch headless Chromium with saved auth state."""
    from playwright.sync_api import sync_playwright

    auth = pathlib.Path(__file__).parent.parent / ".auth" / "user.json"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            storage_state=str(auth),
            viewport={"width": 1400, "height": 950},
        )
        page = ctx.new_page()
        yield page
        ctx.close()
        browser.close()


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
    # chip's globalId URL — the CardService card body itself binds its status
    # buttons via onClick actions, not a plain href/data-url.
    global_id_enc = f"{scn.doc_id}%2F{action_id}"
    bubble = scn.ui._page.evaluate("""() => {
        const b = document.querySelector('#docs-link-bubble.appsElementsLinkPreview');
        if (!b) return null;
        const a = b.querySelector('a[href*="globalId"], [data-url*="globalId"]');
        return { href: a ? (a.href || null) : null, dataUrl: a ? a.getAttribute('data-url') : null };
    }""")
    bubble_url = (bubble or {}).get("href") or (bubble or {}).get("dataUrl") or ""
    assert global_id_enc in bubble_url, (
        f"native link-preview bubble missing globalId {global_id_enc!r}: {bubble!r}"
    )

    scn.ui.set_status(card, "In Progress")

    scn.sync()
    after = scn.find_sheet_actions()
    row = next((r for r in after if r.action_id == action_id), None)
    status_now = (row.status or "").lower() if row else None
    assert status_now == "in progress", (
        f"expected {action_id} status 'In Progress' after in-card status change, "
        f"got {status_now!r}"
    )
