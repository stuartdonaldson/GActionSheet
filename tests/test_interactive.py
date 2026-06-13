"""
test_interactive.py — headed, human-instructed tests for UI interactions that
Playwright cannot drive with synthetic events (GTaskSheet-15e8, epic pw5x).

WHY THIS FILE EXISTS
Some Workspace Add-on / Google Docs interactions only respond to a real human
gesture. The first confirmed case is the onLinkPreview link-preview card
(GTaskSheet-s9so): the add-on inserts action links as plain hyperlinks, which
Google Docs fires onLinkPreview for ONLY when a human hovers the converted
chip — a synthetic page.mouse / locator.hover never invokes it (cloud logs show
zero PREVIEW_CARD.lookup). The standard automated journey drives the equivalent
durable change through the patch_action_status core
(ScenarioSession.link_preview_status_change); THIS file is the periodic
human-fidelity check that the real rendered card still works.

HOW IT RUNS
These tests are marked `interactive` and are EXCLUDED from the default suite
(pyproject addopts: -m 'not interactive'). The harness sets up the doc, then
prints numbered on-screen instructions and PAUSES for the operator; after the
human performs the gesture the harness verifies the durable result.

    pytest -m interactive tests/test_interactive.py -s

`-s` is required so the instructions and live progress print. The test does NOT
read stdin: it prints what to do, then AUTO-DETECTS the result (polls for the
preview card to render, and re-reads the sheet for the status change) within
timed windows — so it works whether a human launches it or an orchestrator does.
A visible Chromium opens; perform the gestures it asks for while it waits.
"""
import pathlib
import time

import pytest

from scn.ai import ai
from scn.session import ScenarioSession
from scn.ui import UiDriver, _CARD_BODY, _CARD_IFRAME, _CHIP_ANCHOR_JS

pytestmark = pytest.mark.interactive


def _banner(title: str, steps: list[str]) -> None:
    """Print a clearly-delimited instruction block for the operator."""
    bar = "═" * 72
    print(f"\n{bar}\n  👤 HUMAN ACTION REQUIRED — {title}\n{bar}")
    for i, step in enumerate(steps, 1):
        print(f"  {i}. {step}")
    print(bar, flush=True)


def _card_visible(page) -> bool:
    """True if the onLinkPreview card iframe body is currently visible."""
    try:
        return page.frame_locator(_CARD_IFRAME).first.locator(_CARD_BODY).first.is_visible()
    except Exception:
        return False


def _wait_until(cond, *, timeout_s: float, waiting_msg: str, poll_s: float = 1.0) -> bool:
    """Poll cond() until True or timeout; print a one-time waiting message."""
    deadline = time.monotonic() + timeout_s
    announced = False
    while time.monotonic() < deadline:
        if cond():
            return True
        if not announced:
            print(f"  ⏳ {waiting_msg}", flush=True)
            announced = True
        time.sleep(poll_s)
    return False


@pytest.fixture
def browser_page():
    """Launch a VISIBLE Chromium with saved auth state for hands-on interaction."""
    from playwright.sync_api import sync_playwright

    auth = pathlib.Path(__file__).parent.parent / ".auth" / "user.json"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=150)
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


def test_link_preview_hover_human(scn):
    """Operator hovers an action chip; confirm the onLinkPreview card renders and
    drives a durable status change (rwz AC1/AC2 + Act-5 status flow, s9so).
    """
    # 1. Seed an action and sync — sync's _flushActionParagraph inserts the chip
    #    hyperlink exactly as the journey does.
    seed = ai(action="Interactive link-preview check")
    scn.append_paragraph(seed.as_text())
    scn.sync()

    rows = scn.find_sheet_actions()
    match = next((r for r in rows if "link-preview check" in (r.action or "")), None)
    assert match is not None, f"seeded action not found after sync; rows={rows}"
    action_id = match.action_id
    assert action_id, f"synced action has no AI-N id: {match}"

    # 2. Open the doc fresh in the browser (the page starts at about:blank — the
    #    seed+sync above were HTTP, no navigation). A fresh load renders the
    #    REST-inserted chip; then point the operator at the actual chip.
    scn.ui._ensure_doc()
    chip = scn.ui.locate(text=action_id, occurrence=1)
    chip.wait_for(state="visible", timeout=15000)
    anchor = scn.ui._page.evaluate(_CHIP_ANCHOR_JS, chip.bounding_box())

    where = f" (near x≈{int(anchor['x'])}, y≈{int(anchor['y'])})" if anchor else ""
    _banner(
        f"link-preview card for {action_id}",
        [
            f"Find the chip “{action_id}: …” in the document{where}.",
            "Hover the mouse over it and HOLD still until a preview card pops up.",
            f"   → the harness is watching and will detect the card automatically.",
            f"Confirm the card header shows “{action_id}: …” and a clickable link.",
            "Then, in that card, open the status control and set it to “In Progress”.",
            "Leave the browser as-is; the harness verifies the result on its own.",
        ],
    )

    page = scn.ui._page

    # 3. rwz AC1/AC2 — auto-detect the rendered card on a real human hover (120s).
    card_rendered = _wait_until(
        lambda: _card_visible(page),
        timeout_s=120,
        waiting_msg="watching for the onLinkPreview card — hover the chip and hold…",
    )
    if card_rendered:
        print("  ✅ onLinkPreview card detected on hover.", flush=True)
    else:
        print("  ⚠️  No preview card detected within 120s.", flush=True)

    # 4. Give the operator time to set the status in the card, then verify durably.
    print("  → Now set the card status to “In Progress”. Verifying shortly…", flush=True)
    time.sleep(40)
    scn.sync()
    after = scn.find_sheet_actions()
    row = next((r for r in after if r.action_id == action_id), None)
    status_now = (row.status or "").lower() if row else None

    assert card_rendered, (
        "onLinkPreview card did NOT render on a real human hover within 120s — this is "
        "a genuine link-preview product gap (Google Docs doesn't convert the add-on's "
        "plain-hyperlink action chips into smart chips), not a harness limitation. "
        "File a follow-up bead (see GTaskSheet-s9so analysis)."
    )
    assert status_now == "in progress", (
        f"expected {action_id} status 'In Progress' after the in-card change, got "
        f"{status_now!r}. If the card rendered but status didn't change, the "
        f"_setStatusFromPreview flow needs review."
    )
