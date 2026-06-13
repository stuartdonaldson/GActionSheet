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
import queue
import subprocess
import threading
import time

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
    print(bar, flush=True)


def _clasp_log_stream():
    """Start `clasp logs --watch` and return (proc, queue-of-lines).

    Server-truth signal for the operator's gesture: the onLinkPreview round
    trip and the in-card status edit both log distinctive tags (PREVIEW_CARD.*,
    POC_EDIT_ACTION.complete) within seconds, even when the card iframe takes
    much longer to become visible in the DOM (GTaskSheet-mxmh).
    """
    proc = subprocess.Popen(
        ["clasp", "logs", "--watch"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, bufsize=1,
    )
    q: "queue.Queue[str]" = queue.Queue()

    def _reader():
        for line in proc.stdout:
            q.put(line)

    threading.Thread(target=_reader, daemon=True).start()
    return proc, q


def _wait_for_log(q: "queue.Queue[str]", *, contains: list[str], timeout_s: float) -> bool:
    """True once a log line containing every string in `contains` arrives."""
    deadline = time.monotonic() + timeout_s
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        try:
            line = q.get(timeout=remaining)
        except queue.Empty:
            return False
        if all(s in line for s in contains):
            return True


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
    #    hyperlink exactly as the journey does. The instruction lives in the
    #    action text itself (GTaskSheet-mxmh) so an operator working purely
    #    from the doc — without the terminal banner — still knows the target
    #    status.
    seed = ai(
        action=(
            "Interactive link-preview check — hover this chip, wait for the "
            "preview card, then set its status to In Progress"
        )
    )
    scn.append_paragraph(seed.as_text())
    scn.sync()

    rows = scn.find_sheet_actions()
    match = next((r for r in rows if "link-preview check" in (r.action or "")), None)
    assert match is not None, f"seeded action not found after sync; rows={rows}"
    action_id = match.action_id
    assert action_id, f"synced action has no AI-N id: {match}"
    global_id = f"{scn.doc_id}/{action_id}"

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
            "The action text itself says what to do — hover, wait for the card, "
            "then set status to “In Progress”.",
            "Hover and HOLD still — the card can take up to ~2 minutes to render "
            "(GTaskSheet-mxmh); the harness watches clasp logs, not the screen.",
            "Once the card appears, open its status control and set it to “In Progress”.",
            "Leave the browser as-is; the harness verifies the result on its own.",
        ],
    )

    # 3. rwz AC1/AC2 — auto-detect the rendered card and the status edit via
    #    clasp logs (server-truth, GTaskSheet-mxmh). The DOM iframe can lag
    #    the server round trip by minutes, so it is no longer the signal.
    log_proc, log_q = _clasp_log_stream()
    try:
        card_rendered = _wait_for_log(
            log_q,
            contains=["PREVIEW_CARD.lookup", global_id],
            timeout_s=180,
        )
        if card_rendered:
            print("  ✅ onLinkPreview card requested (PREVIEW_CARD.lookup seen).", flush=True)
        else:
            print("  ⚠️  No PREVIEW_CARD.lookup observed within 180s.", flush=True)

        # 4. Give the operator time to set the status in the card, then verify durably.
        print("  → Now set the card status to “In Progress”. Verifying via clasp logs…", flush=True)
        status_seen = _wait_for_log(
            log_q,
            contains=["POC_EDIT_ACTION.complete", global_id, '"status":"In Progress"'],
            timeout_s=180,
        )
    finally:
        log_proc.terminate()

    scn.sync()
    after = scn.find_sheet_actions()
    row = next((r for r in after if r.action_id == action_id), None)
    status_now = (row.status or "").lower() if row else None

    assert card_rendered, (
        "onLinkPreview was never requested (no PREVIEW_CARD.lookup in clasp logs) "
        "for a real human hover within 180s — this is a genuine link-preview "
        "product gap (Google Docs doesn't fire onLinkPreview for the add-on's "
        "plain-hyperlink action chips), not a harness limitation. File a follow-up "
        "bead (see GTaskSheet-s9so analysis)."
    )
    assert status_seen and status_now == "in progress", (
        f"expected {action_id} status 'In Progress' after the in-card change, got "
        f"{status_now!r} (clasp log saw POC_EDIT_ACTION.complete: {status_seen}). "
        "If the card rendered but status didn't change, the _setStatusFromPreview "
        "flow needs review."
    )
