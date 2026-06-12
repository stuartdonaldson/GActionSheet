"""
ui.py — Playwright page-object UI driver (GTaskSheet-5vwu.10).

Spec: docs/atdd/atdd-lifecycle.md §16.8, §16.11 #8
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

import json
import pathlib
import re
import time
import warnings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import FrameLocator as _PwFrameLocator
    from playwright.sync_api import Locator as _PwLocator
    from playwright.sync_api import Page as _PwPage

from scn.ai import ai
from scn.engine import Severity

# ---------------------------------------------------------------------------
# Add-on display name — matches addOns.common.name in src/appsscript.json.
# Google Docs uses this string as the aria-label for the panel icon.
# Derived at import time so it stays in sync with the manifest automatically.
# ---------------------------------------------------------------------------
_APPSSCRIPT = pathlib.Path(__file__).parent.parent / "src" / "appsscript.json"
try:
    _ADDON_NAME: str = json.loads(_APPSSCRIPT.read_text())["addOns"]["common"]["name"]
except Exception:
    _ADDON_NAME = "GActionSheet"  # fallback if manifest is unreadable

# ---------------------------------------------------------------------------
# Private selector constants — scenarios never see these
# ---------------------------------------------------------------------------

# GAS card iframe pattern (link-preview card rendered by onLinkPreview)
_CARD_IFRAME = (
    'iframe[src*="script.googleusercontent.com"], '
    'iframe[src*="script.google.com"]'
)
# Add-on iframe that hosts the @-menu Create-action form (addons.gsuite.google.com)
_ADDON_FORM_IFRAME = 'iframe[src*="addons.gsuite.google.com"]'
# Anything inside a rendered card
_CARD_BODY = 'body, [role="main"]'
# Busy/loading spinner that may appear after a card status click
_BUSY = '[aria-label="Loading"], .A8Shqc, [role="progressbar"]'
# Workspace Add-on icon button in the Google Docs right side-panel
_SIDEBAR_ICON_TMPL = '[aria-label*="{name}"], [data-tooltip*="{name}"]'
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
# Action-creation form — submit button (the add-on form labels it "Create";
# "Insert"/submit kept as fallbacks for other entry points)
_FORM_SUBMIT = (
    'button[aria-label="Create"], '
    'button:has-text("Create"), '
    'button[aria-label*="nsert"], '
    'button:has-text("Insert"), '
    'button[type="submit"]'
)
# Sidebar homepage card — Sync Now button
_SIDEBAR_SYNC = (
    '[aria-label="Sync now"], '
    '[aria-label="sync now"], '
    'button:has-text("Sync now")'
)
# Sidebar homepage card — Insert tracker button
_SIDEBAR_INSERT_TRACKER = (
    'button:has-text("Insert tracker"), '
    'button:has-text("tracker"), '
    '[aria-label*="Insert tracker"], '
    '[aria-label*="tracker"]'
)
# Sidebar homepage card — per-row Delete action button
_SIDEBAR_DELETE = '[aria-label="Delete action"]'
# Sidebar homepage card — BUILD_INFO.version footer (e.g. "v0.2.1 (Rev. Jun 9, 2026 22:06) (TEST)")
_VERSION_FOOTER_RE = re.compile(r"v\d+\.\d+\.\d+\s*\(Rev\.[^)]*\)(?:\s*\([A-Za-z]+\))?")


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
        # Wired by ScenarioSession.ui setter: trace sink + back-ref for the
        # post-act fail-fast GAS-error check. Defaults keep UiDriver usable alone.
        from scn.reporter import NullReporter
        self.reporter = NullReporter()
        self._session = None

    def _post_act_check(self) -> None:
        """Run the session's fail-fast GAS-error scan after a UI entry-point act."""
        if self._session is not None:
            self._session._check_gas_errors()

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

    def reload(self) -> None:
        """Reload the current page and wait for the Docs editor to be ready.

        REST-API-applied changes (e.g. a chip inserted via batchUpdate during
        an INTEGRITY checkpoint) are not reflected in an already-open editor
        tab without a reload.
        """
        self._page.reload()
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

        GTaskSheet-o5py: force=True bypasses Playwright's "receives pointer
        events" actionability check. The Docs editor renders its own hover
        chrome (a <span jsslot> overlay) on top of smart-chip links, which
        intercepts the synthetic hover event even though the element itself
        is visible and present.
        """
        ms = _parse_timeout(timeout)
        locator.wait_for(state="visible", timeout=ms)
        locator.hover(force=True)

        card_frame = self._page.frame_locator(_CARD_IFRAME).first
        card_frame.locator(_CARD_BODY).first.wait_for(state="visible", timeout=ms)

        card = Card(card_frame)
        self._current_card = card
        return card

    def hover_until(self, locator: _PwLocator, *, timeout: str = "5s") -> Card:
        """Hover and wait until the preview card appears (semantic alias of hover)."""
        return self.hover(locator, timeout=timeout)

    def open_sidebar(self, addon_name: str = _ADDON_NAME, *, timeout: str = "15s") -> Card:
        """Click the add-on icon to open the homepage card; return a Card handle.

        Idempotent: if the sidebar is already open (e.g. from an earlier call
        in the same journey), returns the existing card without re-clicking
        the icon — clicking it again toggles the panel closed.

        Polls all page frames for one that contains the 'Sync now' button —
        the same detection strategy as JS findAddonFrame in _helpers.js.
        Handles the cold-start 'Refresh' button that can appear before the card
        loads (clicks it and waits 4 s before resuming the poll).
        """
        self._ensure_doc()
        ms = _parse_timeout(timeout)

        for frame in self._page.frames:
            try:
                if frame.get_by_role("button", name=re.compile(r"sync now", re.I)).count():
                    card = Card(frame)
                    self._current_card = card
                    return card
            except Exception:
                pass

        btn = self._page.locator(_SIDEBAR_ICON_TMPL.format(name=addon_name)).first
        btn.wait_for(state="visible", timeout=ms)
        btn.click()

        # Allow the sidebar iframe to begin initialising (GAS cold start can
        # take 15–20 s; a brief initial wait avoids hammering too early).
        time.sleep(3.0)

        deadline = time.monotonic() + ms / 1000.0
        refresh_attempted = False
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"open_sidebar: sidebar card did not load within {timeout}"
                )
            for frame in self._page.frames:
                try:
                    if frame.get_by_role(
                        "button", name=re.compile(r"sync now", re.I)
                    ).count():
                        card = Card(frame)
                        self._current_card = card
                        return card
                except Exception:
                    pass

            # Cold-start 'Refresh' button may appear before the card loads
            if not refresh_attempted:
                try:
                    refresh_btn = self._page.get_by_role(
                        "button", name=re.compile(r"^Refresh$", re.I)
                    )
                    if refresh_btn.count() > 0:
                        refresh_btn.click()
                        refresh_attempted = True
                        time.sleep(4.0)
                        continue
                except Exception:
                    pass

            time.sleep(0.5)

    def read_version(self, card: Card, *, timeout: str = "5s") -> str:
        """Read the BUILD_INFO.version footer text from a homepage card.

        Pre-flight smoke check: confirms the add-on test deployment installed
        in this Google account is serving the expected revision
        (tests/helpers/version.read_expected_version, src/Version.js).
        """
        ms = _parse_timeout(timeout)
        locator = card.frame.get_by_text(_VERSION_FOOTER_RE)
        locator.first.wait_for(state="visible", timeout=ms)
        return locator.first.inner_text()

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
        with self.reporter.step("UIACT", "set_status", f"card -> {status}"):
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
                pass
        self._post_act_check()  # no spinner appeared; action completed synchronously

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
        detail = str(target.action_id or target.assignee or target.action or "")[:60]
        with self.reporter.step("UIACT", "create_action", detail):
            self._ensure_doc()

            self._page.locator(_DOC_CONTENT).click()
            # Move to a clean insertion point first. After an upstream
            # append_paragraph the doc has content; clicking the editor lands the
            # caret mid-text, where "@" does NOT start a smart-chip trigger.
            # Ctrl+End + a fresh line gives the trigger a clean line.
            self._page.keyboard.press("Control+End")
            self._page.keyboard.press("Enter")
            # Then type the @-trigger and query CONTINUOUSLY ("@create"), not "@"
            # then a pause then "Create": the add-on smart-chip provider
            # (createActionTriggers) only surfaces "Create action" for a live
            # @-query. Diagnosed 2026-06-10: post-append "@create" mid-doc ->
            # item ABSENT (18s); Ctrl+End + Enter + "@create" -> item present at
            # once. The wait_for below polls the server-side provider.
            self._page.keyboard.type("@create")

            # The provider is fetched server-side (cold start 5-15s); wait_for
            # polls until the "Create action" item becomes visible.
            item = self._page.locator(_AT_MENU_CREATE).first
            try:
                item.wait_for(state="visible", timeout=20000)
            except Exception as exc:
                raise RuntimeError(
                    "createActionTriggers 'Create action' not found in the @-menu after 20s. "
                    "The editor add-on must be installed as a test deployment: "
                    "Apps Script editor → Deploy → Test deployments → Install as Add-on."
                ) from exc
            item.click()

            # The Create-action form renders INSIDE the add-on iframe
            # (addons.gsuite.google.com), not the top-level page — operate within
            # that frame. Diagnosed 2026-06-10: the 'Action' / 'Assignee (optional)'
            # inputs live in that frame ~6s after the click; a top-level
            # wait_for_selector never finds them (25s timeout).
            # Multiple frames can match _ADDON_FORM_IFRAME once the homepage
            # sidebar (Act 3b) is open (sidebar iframe + Docs' own kix-appview
            # iframe), in addition to the Create-action form's iframe — so a
            # single frame_locator(...) is ambiguous (strict-mode violation).
            # Poll page.frames directly for the one frame whose assignee input
            # becomes visible.
            deadline = time.monotonic() + 30.0
            form = None
            while time.monotonic() < deadline:
                for frame in self._page.frames:
                    if "addons.gsuite.google.com" not in frame.url:
                        continue
                    try:
                        candidate = frame.locator(_FORM_ASSIGNEE).first
                        if candidate.is_visible():
                            form = frame
                            break
                    except Exception:
                        continue
                if form is not None:
                    break
                time.sleep(0.5)
            if form is None:
                raise TimeoutError(
                    "create_action: no add-on iframe with a visible assignee "
                    "input found within 30s"
                )
            assignee = form.locator(_FORM_ASSIGNEE).first

            if target.assignee:
                assignee.fill(target.assignee)
                # Poll for the autocomplete option directly (no fixed pre-sleep).
                suggestion = form.locator('[role="option"]').first
                try:
                    suggestion.wait_for(state="visible", timeout=2000)
                    suggestion.click()
                except Exception:
                    # No autocomplete suggestion — plain email, tab to confirm.
                    assignee.press("Tab")

            if target.action:
                form.locator(_FORM_TEXT).first.fill(target.action)

            submit = form.locator(_FORM_SUBMIT).first
            submit.wait_for(state="visible", timeout=5000)
            submit.click()

            # Form closes (chip inserted into doc): the assignee input detaches.
            assignee.wait_for(state="hidden", timeout=10000)
        self._post_act_check()

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

    # ------------------------------------------------------------------
    # Private sidebar helpers
    # ------------------------------------------------------------------

    def _sidebar_card(self) -> Card:
        """Idempotently ensure the sidebar is open; return the current card."""
        if self._current_card is None:
            self._current_card = self.open_sidebar()
        return self._current_card

    def _sidebar_row(self, action_id: str) -> _PwLocator:
        """Return a Locator scoped to the sidebar row whose text starts with action_id."""
        assert self._current_card is not None
        return self._current_card.frame.get_by_text(
            f"{action_id} •", exact=False
        )

    # ------------------------------------------------------------------
    # Sidebar acts — real UI entry points (R2-impl §16.3 #1)
    # ------------------------------------------------------------------

    def sidebar_sync(self, *, timeout: str = "60s") -> None:
        """Click the homepage sidebar Sync Now button; wait out busy.

        Real call-site for scn.sync() (Sync Scenario C). Cold sync can be
        slow — 60s default. Does NOT poll the sheet; durable convergence is
        the journey's responsibility (§16.11 #4).
        """
        with self.reporter.step("UIACT", "sidebar_sync", f"waiting busy<={timeout}"):
            ms = _parse_timeout(timeout)
            self._sidebar_card()
            assert self._current_card is not None
            sync_btn = self._current_card.frame.locator(_SIDEBAR_SYNC)
            sync_btn.wait_for(state="visible", timeout=ms)
            sync_btn.click()

            busy = self._current_card.frame.locator(_BUSY)
            try:
                busy.wait_for(state="visible", timeout=2000)
                busy.wait_for(state="hidden", timeout=ms)
            except Exception:
                pass
        self._post_act_check()

    def insert_tracker_button(self, *, timeout: str = "30s") -> None:
        """Click the homepage sidebar Insert tracker button; wait out busy.

        Real call-site for scn.insert_tracker(). Mutates the doc (tracker
        table inserted/refreshed).
        """
        with self.reporter.step("UIACT", "insert_tracker_button", f"waiting busy<={timeout}"):
            ms = _parse_timeout(timeout)
            self._sidebar_card()
            assert self._current_card is not None
            insert_btn = self._current_card.frame.locator(_SIDEBAR_INSERT_TRACKER)
            insert_btn.wait_for(state="visible", timeout=ms)
            insert_btn.click()

            busy = self._current_card.frame.locator(_BUSY)
            try:
                busy.wait_for(state="visible", timeout=2000)
                busy.wait_for(state="hidden", timeout=ms)
            except Exception:
                pass
        self._post_act_check()

    def sidebar_delete(self, target: ai, *, timeout: str = "15s") -> None:
        """Click the per-row Delete action button for target.action_id; wait out busy.

        Real call-site for scn.delete(ai) (per-row sidebar Delete button).
        Identity addressing is by action_id (§16.11 #3).
        """
        with self.reporter.step("UIACT", "sidebar_delete", str(target.action_id or "")):
            ms = _parse_timeout(timeout)
            self._sidebar_card()
            assert self._current_card is not None
            row = self._sidebar_row(target.action_id or "")
            delete_btn = row.locator(_SIDEBAR_DELETE)
            delete_btn.wait_for(state="visible", timeout=ms)
            delete_btn.click()

            busy = self._current_card.frame.locator(_BUSY)
            try:
                busy.wait_for(state="visible", timeout=2000)
                busy.wait_for(state="hidden", timeout=ms)
            except Exception:
                pass
        self._post_act_check()

    def sidebar_set_status(
        self, target: ai, status: str, *, timeout: str = "15s"
    ) -> None:
        """Click the per-row status control for target.action_id; select status; wait out busy.

        Real call-site for scn.set_status(ai, status) (Sync Scenario A, per-row
        sidebar status control). DISTINCT from set_status(card, status), which
        operates on a hovered preview Card.
        """
        with self.reporter.step("UIACT", "sidebar_set_status", f"{target.action_id} -> {status}"):
            ms = _parse_timeout(timeout)
            self._sidebar_card()
            assert self._current_card is not None
            row = self._sidebar_row(target.action_id or "")
            status_btn = row.locator(
                f'[aria-label="{status}"], button:has-text("{status}")'
            )
            status_btn.wait_for(state="visible", timeout=ms)
            status_btn.click()

            busy = self._current_card.frame.locator(_BUSY)
            try:
                busy.wait_for(state="visible", timeout=2000)
                busy.wait_for(state="hidden", timeout=ms)
            except Exception:
                pass
        self._post_act_check()

    def show_tab(self, label: str, *, timeout: str = "15s") -> None:
        """Click a homepage card tab-bar button (ADR-0015 onShowTab); wait out busy.

        label is one of the _TABS[].label values in src/WorkspaceAddonCard.js
        ("Doc status", "Import", "Notify"). onShowTab responds with
        updateCard(_buildTabbedHomepageCard(tab)) — same re-render shape as
        sidebar_set_status/sidebar_delete, so the busy-wait pattern matches.
        """
        with self.reporter.step("UIACT", "show_tab", label):
            ms = _parse_timeout(timeout)
            self._sidebar_card()
            assert self._current_card is not None
            tab_btn = self._current_card.frame.get_by_role(
                "button", name=label, exact=True
            )
            tab_btn.wait_for(state="visible", timeout=ms)
            tab_btn.click()

            busy = self._current_card.frame.locator(_BUSY)
            try:
                busy.wait_for(state="visible", timeout=2000)
                busy.wait_for(state="hidden", timeout=ms)
            except Exception:
                pass
        self._post_act_check()

    def read_current(self) -> list[ai]:
        """Read the currently-rendered card as list[ai] for queue-drain (R1-impl §1).

        Returns [] if no card context or no 'AI-N:' header found.
        Reads action_id from the 'AI-N:' card header text and status from the rendered
        brand-NUTS status icon (img[alt] preferred over non-button [aria-label], per G1).
        """
        if self._current_card is None:
            return []

        frame = self._current_card.frame
        action_id = None
        status = None

        try:
            # Match both preview-card "AI-N:" and homepage-sidebar "AI-N •" formats
            header = frame.get_by_text(re.compile(r"\bAI-\d+\b")).first
            header_text = header.text_content(timeout=2000) or ""
            m = re.search(r"\b(AI-\d+)\b", header_text)
            if m:
                action_id = m.group(1)
        except Exception:
            pass

        if not action_id:
            return []

        # Status is read from the row container that holds the action_id text.
        # Navigate from the action_id element to its closest ancestor that has an
        # img[alt] descendant (the decorated-text row widget).  This avoids reading
        # the add-on header logo image which appears earlier in the frame DOM.
        try:
            row_el = frame.get_by_text(re.compile(r"\bAI-\d+\b")).first
            row_container = row_el.locator("xpath=ancestor::*[.//img[@alt]][1]")
            for img in row_container.locator("img[alt]").all():
                alt = img.get_attribute("alt", timeout=1000)
                if alt and alt.strip():
                    status = alt.strip()
                    break
        except Exception:
            pass

        # Fallback: scan full frame img[alt], skipping the add-on logo image
        if status is None:
            try:
                for img in frame.locator("img[alt]").all():
                    alt = img.get_attribute("alt", timeout=1000)
                    if alt and alt.strip() and "logo" not in alt.lower():
                        status = alt.strip()
                        break
            except Exception:
                pass

        if status is None:
            try:
                for el in frame.locator('[aria-label]:not(button):not([role="button"])').all():
                    lbl = el.get_attribute("aria-label", timeout=1000)
                    if lbl and lbl.strip():
                        status = lbl.strip()
                        break
            except Exception:
                pass

        return [ai(action="", action_id=action_id, status=status)]
