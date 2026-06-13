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

`-s` is required so the instructions print and the input() prompt is reachable.
Run from an interactive terminal (not a background/CI context) — it blocks on
stdin by design.
"""
import pathlib

import pytest

from scn.ai import ai
from scn.session import ScenarioSession
from scn.ui import UiDriver, _CHIP_ANCHOR_JS

pytestmark = pytest.mark.interactive


def _banner(title: str, steps: list[str]) -> None:
    """Print a clearly-delimited instruction block for the operator."""
    bar = "═" * 72
    print(f"\n{bar}\n  👤 HUMAN ACTION REQUIRED — {title}\n{bar}")
    for i, step in enumerate(steps, 1):
        print(f"  {i}. {step}")
    print(bar)


def _confirm(question: str) -> bool:
    """Ask the operator a yes/no question; return True for yes."""
    return input(f"  ❓ {question} [y/N] ").strip().lower().startswith("y")


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

    # 2. Reload so the REST-inserted chip is rendered in the editor, then point the
    #    operator at the actual chip (DOM-scan its on-screen position for clarity).
    scn.ui.reload()
    chip = scn.ui.locate(text=action_id, occurrence=1)
    chip.wait_for(state="visible", timeout=15000)
    anchor = scn.ui._page.evaluate(_CHIP_ANCHOR_JS, chip.bounding_box())

    _banner(
        f"link-preview card for {action_id}",
        [
            f"Find the chip “{action_id}: …” in the document"
            + (f" (near x≈{int(anchor['x'])}, y≈{int(anchor['y'])})." if anchor else "."),
            "Hover the mouse over it and HOLD until a preview card pops up.",
            f"Confirm the card header shows “{action_id}: …” and a clickable link.",
            "In that card, open the status control and set it to “In Progress”.",
            "Wait for the card’s busy spinner to clear, then return to this terminal.",
        ],
    )

    card_rendered = _confirm(f"Did the preview card render with “{action_id}:” and a link?")
    status_set = _confirm("Did you set the status to “In Progress” in the card?")
    input("  ⏎ Press Enter to let the harness verify the durable result… ")

    # 3. rwz AC1/AC2 — the rendered card is a human-confirmed fidelity check.
    assert card_rendered, (
        "Operator reported the onLinkPreview card did NOT render on a real hover — "
        "this is a genuine link-preview product gap, not a harness limitation "
        "(see GTaskSheet-s9so analysis)."
    )

    # 4. Durable verification of the in-card status change (Act-5 flow).
    if status_set:
        scn.sync()
        after = scn.find_sheet_actions()
        row = next((r for r in after if r.action_id == action_id), None)
        assert row is not None, f"action {action_id} missing after status change; rows={after}"
        assert (row.status or "").lower() == "in progress", (
            f"expected {action_id} status 'In Progress' after the in-card change, "
            f"got {row.status!r}"
        )
    else:
        pytest.skip("Operator did not perform the in-card status change; durable check skipped.")
