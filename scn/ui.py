"""
ui.py — Playwright page-object UI driver (GTaskSheet-5vwu.10).

Spec: docs/proposed-atdd-lifecycle.md §16.8, §16.11 #8
Design: docs/atdd/scenario-harness-design.md §3.8

Public API exposed as scn.ui (attach to ScenarioSession after creation):
    scn.ui = UiDriver(page, doc_id=scn.doc_id)

  locate(*, text, alt, occurrence, next) -> Locator
  hover(locator, *, timeout) -> Card
  hover_until(locator, *, timeout) -> Card
  click(locator, *, timeout) -> None
  mouse_down_hold(locator, *, timeout) -> None
  set_status(card, status) -> None
  create_action(target) -> None
  expect_visible(card, *, timeout) -> None
  expect_alt(locator, text, *, severity) -> None

Ownership rule (§16.8): this driver owns ALL selectors, iframe traversal, and
wait/timeout knowledge — scenarios call named intents only; no Playwright objects
leak up to the scenario layer.

playwright package is a runtime dependency only when using a live browser.
Unit tests may mock the Page object; playwright need not be installed.
"""
from __future__ import annotations

import re
import warnings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import FrameLocator as _PwFrameLocator
    from playwright.sync_api import Locator as _PwLocator
    from playwright.sync_api import Page as _PwPage

from scn.ai import ai
from scn.engine import Severity

# ---------------------------------------------------------------------------
# Private selector constants — scenarios never see these
# ---------------------------------------------------------------------------

# GAS card iframe pattern (link-preview card rendered by onLinkPreview)
_CARD_IFRAME = (
    'iframe[src*="script.googleusercontent.com"], '
    'iframe[src*="script.google.com"]'
)
# Anything inside a rendered card
_CARD_BODY = 'body, [role="main"]'
# Busy/loading spinner that may appear after a card status click
_BUSY = '[aria-label="Loading"], .A8Shqc, [role="progressbar"]'
# Google Docs content editable area
_DOC_CONTENT = '.kix-appview-editor'
# @-menu "Create action" item
_AT_MENU_CREATE = (
    '[role="option"]:has-text("Create action"), '
    '[role="menuitem"]:has-text("Create action")'
)
# Action-creation form — assignee input
_FORM_ASSIGNEE = (
    'input[aria-label*="ssignee"], '
    'input[placeholder*="ssignee"], '
    '[role="dialog"] input'
)
# Action-creation form — action-text input
_FORM_TEXT = (
    'textarea[aria-label*="ction"], '
    'input[aria-label*="ction"], '
    '[role="dialog"] textarea'
)
# Action-creation form — submit / insert button
_FORM_SUBMIT = (
    'button[aria-label*="nsert"], '
    'button:has-text("Insert"), '
    'button[type="submit"]'
)


# ---------------------------------------------------------------------------
# _parse_timeout
# ---------------------------------------------------------------------------

_TIMEOUT_RE = re.compile(r"^(\d+(?:\.\d+)?)(s|ms)$")


def _parse_timeout(t: str) -> int:
    """Parse a timeout string ('5s', '500ms') into milliseconds.

    >>> _parse_timeout('5s')
    5000
    >>> _parse_timeout('250ms')
    250
    """
    m = _TIMEOUT_RE.match(t)
    if not m:
        raise ValueError(
            f"Invalid timeout: {t!r}. Expected a value like '5s' or '500ms'."
        )
    val, unit = m.groups()
    return int(float(val) * (1000 if unit == "s" else 1))


# ---------------------------------------------------------------------------
# Card — handle to a popped preview card
# ---------------------------------------------------------------------------


class Card:
    """Handle to a popped GAS link-preview card.

    Wraps the FrameLocator for the card iframe so callers interact with it
    via named intents, never via raw iframe selectors.
    """

    def __init__(self, frame: _PwFrameLocator) -> None:
        self._frame = frame

    @property
    def frame(self) -> _PwFrameLocator:
        return self._frame


# ---------------------------------------------------------------------------
# UiDriver — page-object layer
# ---------------------------------------------------------------------------


class UiDriver:
    """Playwright page-object driver for §16.8 scenario journeys.

    Owns all selectors, iframe traversal, and timing knowledge (§16.11 #8).
    Scenarios call named intents only — no Playwright objects leak up.

    Attach to a ScenarioSession after creation:
        scn.ui = UiDriver(page, doc_id=scn.doc_id)
    """

    def __init__(self, page: _PwPage, *, doc_id: str) -> None:
        self._page = page
        self._doc_id = doc_id
        self._current_card: Card | None = None  # context for next=True locate()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _doc_url(self) -> str:
        return f"https://docs.google.com/document/d/{self._doc_id}/edit"

    def _ensure_doc(self) -> None:
        """Navigate to the journey doc if the page is not already there."""
        if not self._page.url.startswith(
            f"https://docs.google.com/document/d/{self._doc_id}"
        ):
            self._page.goto(self._doc_url())
            self._page.wait_for_selector(".docs-title-outer", timeout=30000)

    # ------------------------------------------------------------------
    # locate — builds a Playwright locator (lazy, no DOM touch)
    # ------------------------------------------------------------------

    def locate(
        self,
        *,
        text: str | None = None,
        alt: str | None = None,
        occurrence: int = 1,
        next: bool = False,  # noqa: A002  (matches §16.8 API verbatim)
    ) -> _PwLocator:
        """Build a locator for a UI target without touching the DOM.

        text= + occurrence=: the nth element containing this string/id
            (occurrence=1 → first, occurrence=2 → second, …).
        alt=: element by aria-label, alt, or title attribute.
        next=True: scope inside the last-popped preview card context.
        """
        ctx = (
            self._current_card.frame
            if (next and self._current_card)
            else self._page
        )

        if text is not None:
            # nth(occurrence - 1) for the nth-occurrence targeting rule.
            return ctx.get_by_text(text, exact=False).nth(occurrence - 1)

        if alt is not None:
            # Union of stable identity attributes; stable alt-text is preferred
            # for icon buttons (§16.8 "stable alt-text like 'In Progress'").
            return ctx.locator(
                f'[aria-label="{alt}"], [alt="{alt}"], [title="{alt}"]'
            ).first

        raise ValueError("locate() requires text= or alt=")

    # ------------------------------------------------------------------
    # Gestures
    # ------------------------------------------------------------------

    def hover(self, locator: _PwLocator, *, timeout: str = "5s") -> Card:
        """Hover over a locator; return the preview card that pops up.

        Waits up to timeout for the element to be visible and for the GAS
        link-preview card iframe to render its body.
        Sets the current card context for subsequent next=True locate() calls.
        """
        ms = _parse_timeout(timeout)
        locator.wait_for(state="visible", timeout=ms)
        locator.hover()

        card_frame = self._page.frame_locator(_CARD_IFRAME).first
        card_frame.locator(_CARD_BODY).first.wait_for(state="visible", timeout=ms)

        card = Card(card_frame)
        self._current_card = card
        return card

    def hover_until(self, locator: _PwLocator, *, timeout: str = "5s") -> Card:
        """Hover and wait until the preview card appears (semantic alias of hover)."""
        return self.hover(locator, timeout=timeout)

    def click(self, locator: _PwLocator, *, timeout: str = "5s") -> None:
        """Click a locator after waiting up to timeout for it to be visible."""
        ms = _parse_timeout(timeout)
        locator.wait_for(state="visible", timeout=ms)
        locator.click()

    def mouse_down_hold(self, locator: _PwLocator, *, timeout: str = "5s") -> None:
        """Click and hold on a locator (useful for drag or selection gestures)."""
        ms = _parse_timeout(timeout)
        locator.wait_for(state="visible", timeout=ms)
        locator.click(button="left", delay=100)

    # ------------------------------------------------------------------
    # set_status — card interaction with busy-state wait (§16.11 #8)
    # ------------------------------------------------------------------

    def set_status(self, card: Card, status: str) -> None:
        """Click a status button inside the preview card; wait out the busy state (≤10s).

        The driver owns the busy→return timing knowledge (§16.11 #8, §16.8):
        after the click the card may briefly show a spinner while GAS processes
        the update.  The driver absorbs that wait; scenarios do not.
        """
        status_btn = card.frame.locator(
            f'[aria-label="{status}"], button:has-text("{status}")'
        )
        status_btn.wait_for(state="visible", timeout=10000)
        status_btn.click()

        busy = card.frame.locator(_BUSY)
        try:
            busy.wait_for(state="visible", timeout=2000)
            busy.wait_for(state="hidden", timeout=10000)
        except Exception:
            pass  # no spinner appeared; action completed synchronously

    # ------------------------------------------------------------------
    # create_action — @-menu form (§16.4 autocomplete path)
    # ------------------------------------------------------------------

    def create_action(self, target: ai) -> None:
        """Drive the @-menu Create-action form; fills assignee + action text.

        Autocomplete (§16.4): target.assignee is typed into the assignee field;
        if a suggestion appears (email in TEST_CONTACTS) it is accepted; otherwise
        the plain email is tabbed through and a severity=WARN is expected at
        verify time (§16.4 / §16.8).
        """
        self._ensure_doc()

        self._page.locator(_DOC_CONTENT).click()
        self._page.keyboard.type("@")

        # Wait for @-menu dropdown.
        self._page.wait_for_selector(
            "[role='listbox'], [data-at-menu], .docs-at-picker-container",
            timeout=5000,
        )
        self._page.keyboard.type("Create")
        self._page.wait_for_timeout(500)

        item = self._page.locator(_AT_MENU_CREATE).first
        item.wait_for(state="visible", timeout=5000)
        item.click()

        # Wait for the action creation form to appear.
        self._page.wait_for_selector(_FORM_ASSIGNEE, timeout=10000)

        if target.assignee:
            inp = self._page.locator(_FORM_ASSIGNEE).first
            inp.fill(target.assignee)
            self._page.wait_for_timeout(800)
            suggestion = self._page.locator('[role="option"]').first
            try:
                suggestion.wait_for(state="visible", timeout=2000)
                suggestion.click()
            except Exception:
                # No autocomplete suggestion — plain email, tab to confirm.
                inp.press("Tab")

        if target.action:
            self._page.locator(_FORM_TEXT).first.fill(target.action)

        submit = self._page.locator(_FORM_SUBMIT).first
        submit.wait_for(state="visible", timeout=5000)
        submit.click()

        # Wait for the form to close (chip inserted into doc).
        self._page.wait_for_selector("[role='dialog']", state="hidden", timeout=10000)

    # ------------------------------------------------------------------
    # UI expectations (live mid-session; §16.8, §16.11 #8)
    # ------------------------------------------------------------------

    def expect_visible(self, card: Card, *, timeout: str = "5s") -> None:
        """Assert the preview card is visible within timeout.

        Called directly — not enqueued — because UI observations are live and
        bounded (§16.8: "if it only renders inside a popped card we may need a
        bounded wait").
        """
        ms = _parse_timeout(timeout)
        card.frame.locator(_CARD_BODY).first.wait_for(state="visible", timeout=ms)

    def expect_alt(
        self,
        locator: _PwLocator,
        text: str,
        *,
        severity: Severity = Severity.FAIL,
    ) -> None:
        """Assert aria-label / alt / title attribute of element equals text.

        severity=WARN records a warning without failing — used by §16.4
        autocomplete path where a missing contact is expected to produce a
        imperfect chip.
        """
        for attr in ("aria-label", "alt", "title"):
            val = locator.get_attribute(attr)
            if val is not None:
                if val == text:
                    return
                msg = f"expect_alt: expected {text!r}, got {val!r} (attr={attr!r})"
                if severity == Severity.FAIL:
                    raise AssertionError(msg)
                warnings.warn(msg, stacklevel=2)
                return
        msg = (
            f"expect_alt: no aria-label/alt/title attribute found on element "
            f"(expected {text!r})"
        )
        if severity == Severity.FAIL:
            raise AssertionError(msg)
        warnings.warn(msg, stacklevel=2)
