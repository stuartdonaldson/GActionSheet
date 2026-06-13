"""
Unit tests for scn/ui.py — UiDriver + Card (GTaskSheet-5vwu.10).

All tests use mocked Page objects; playwright does not need to be installed.
AC: scenarios call named intents only; locate targets nth-occurrence and alt-text;
    gestures carry timeouts; set_status waits out the busy state (§16.8).
"""
import warnings
from unittest.mock import MagicMock, patch

import pytest

from scn.ui import Card, UiDriver, _parse_timeout
from scn.engine import Severity


# ---------------------------------------------------------------------------
# _parse_timeout
# ---------------------------------------------------------------------------

class TestParseTimeout:
    def test_seconds(self):
        assert _parse_timeout("5s") == 5000

    def test_milliseconds(self):
        assert _parse_timeout("500ms") == 500

    def test_decimal_seconds(self):
        assert _parse_timeout("1.5s") == 1500

    def test_zero_seconds(self):
        assert _parse_timeout("0s") == 0

    def test_invalid_unit_raises(self):
        with pytest.raises(ValueError, match="Invalid timeout"):
            _parse_timeout("5x")

    def test_bare_number_raises(self):
        with pytest.raises(ValueError):
            _parse_timeout("5")

    def test_ms_exact(self):
        assert _parse_timeout("250ms") == 250


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_page():
    page = MagicMock()
    page.url = "https://docs.google.com/document/d/DOCID123/edit"
    return page


@pytest.fixture
def driver(mock_page):
    return UiDriver(mock_page, doc_id="DOCID123")


# ---------------------------------------------------------------------------
# locate()
# ---------------------------------------------------------------------------

class TestLocate:
    def test_text_calls_get_by_text_with_nth(self, driver, mock_page):
        driver.locate(text="AI-1", occurrence=1)
        mock_page.get_by_text.assert_called_once_with("AI-1", exact=False)
        mock_page.get_by_text.return_value.nth.assert_called_once_with(0)

    def test_occurrence_n_maps_to_nth_index_n_minus_1(self, driver, mock_page):
        driver.locate(text="AI-3", occurrence=3)
        mock_page.get_by_text.return_value.nth.assert_called_once_with(2)

    def test_alt_builds_combined_selector(self, driver, mock_page):
        driver.locate(alt="In Progress")
        call_arg = mock_page.locator.call_args[0][0]
        assert 'aria-label="In Progress"' in call_arg
        assert 'alt="In Progress"' in call_arg
        assert 'title="In Progress"' in call_arg

    def test_alt_returns_first_match(self, driver, mock_page):
        result = driver.locate(alt="In Progress")
        assert result is mock_page.locator.return_value.first

    def test_next_true_scopes_to_card_frame(self, driver):
        card_frame = MagicMock()
        driver._current_card = Card(card_frame)
        driver.locate(text="AI-1", next=True)
        card_frame.get_by_text.assert_called_once_with("AI-1", exact=False)

    def test_next_true_without_card_falls_back_to_page(self, driver, mock_page):
        driver._current_card = None
        driver.locate(text="AI-1", next=True)
        mock_page.get_by_text.assert_called_once()

    def test_no_args_raises_value_error(self, driver):
        with pytest.raises(ValueError, match="locate\\(\\) requires text= or alt="):
            driver.locate()

    def test_text_default_occurrence_is_first(self, driver, mock_page):
        driver.locate(text="AI-5")
        mock_page.get_by_text.return_value.nth.assert_called_once_with(0)


# ---------------------------------------------------------------------------
# hover()
# ---------------------------------------------------------------------------

class TestHover:
    # GTaskSheet-s9so: hover() drives a real mouse trajectory to the chip's link
    # anchor (located by a doc-DOM scan, _CHIP_ANCHOR_JS) and polls for the card
    # body, rather than a single locator.hover(force=True). These tests assert
    # that new contract.
    def _setup(self, mock_page, locator, *, anchor=None):
        """Wire frame_locator + mouse + DOM-scan so hover() succeeds offline.

        anchor=None → page.evaluate returns no anchor, so hover() falls back to
        the located element's left edge (both paths yield real numeric coords).
        """
        frame = MagicMock()
        frame.locator.return_value.first = MagicMock()  # card-body wait_for() succeeds
        mock_page.frame_locator.return_value.first = frame
        mock_page.evaluate.return_value = anchor
        locator.bounding_box.return_value = {"x": 100, "y": 200, "width": 150, "height": 20}
        return frame

    def test_waits_for_locator_visible(self, driver, mock_page):
        locator = MagicMock()
        self._setup(mock_page, locator)
        driver.hover(locator, timeout="5s")
        locator.wait_for.assert_called_once_with(state="visible", timeout=5000)

    def test_drives_real_mouse_to_target(self, driver, mock_page):
        locator = MagicMock()
        self._setup(mock_page, locator)
        driver.hover(locator, timeout="3s")
        assert mock_page.mouse.move.called  # real trajectory, not locator.hover

    def test_targets_link_anchor_when_found(self, driver, mock_page):
        locator = MagicMock()
        self._setup(mock_page, locator, anchor={"x": 50, "y": 60, "width": 10, "height": 10})
        driver.hover(locator, timeout="5s")
        # anchor centre (55, 65) is the final glide-to point
        final_move = [c for c in mock_page.mouse.move.call_args_list if c.kwargs.get("steps") == 12]
        assert final_move and final_move[-1].args == (55.0, 65.0)

    def test_returns_card_instance(self, driver, mock_page):
        locator = MagicMock()
        self._setup(mock_page, locator)
        result = driver.hover(locator, timeout="5s")
        assert isinstance(result, Card)

    def test_sets_current_card_context(self, driver, mock_page):
        locator = MagicMock()
        self._setup(mock_page, locator)
        card = driver.hover(locator, timeout="5s")
        assert driver._current_card is card

    def test_polls_card_body_for_visibility(self, driver, mock_page):
        locator = MagicMock()
        frame = self._setup(mock_page, locator)
        driver.hover(locator, timeout="7s")
        # body visibility is polled in short slices (1s), not one full-timeout wait
        frame.locator.return_value.first.wait_for.assert_called_with(
            state="visible", timeout=1000
        )

    def test_hover_until_delegates_to_hover(self, driver):
        with patch.object(driver, "hover", return_value=MagicMock()) as mock_hover:
            locator = MagicMock()
            driver.hover_until(locator, timeout="8s")
            mock_hover.assert_called_once_with(locator, timeout="8s")


# ---------------------------------------------------------------------------
# capture_failure() — centralized UI-failure diagnostics (GTaskSheet-3tkf)
# ---------------------------------------------------------------------------

class TestCaptureFailure:
    def _wire_frames(self, mock_page, urls, *, probe_count=0, visible=True, bbox=None):
        frames = []
        for url in urls:
            f = MagicMock()
            f.url = url
            loc = f.locator.return_value
            loc.count.return_value = probe_count
            loc.first.is_visible.return_value = visible
            loc.first.bounding_box.return_value = bbox
            frames.append(f)
        mock_page.frames = frames

    def test_saves_screenshot_to_test_results(self, driver, mock_page):
        self._wire_frames(mock_page, ["https://docs.google.com/document/d/X/edit"])
        msg = driver.capture_failure("My Label Timeout")
        # screenshot taken at a slugified test-results path, path echoed in message
        assert mock_page.screenshot.called
        assert "test-results/my-label-timeout.png" in msg

    def test_lists_all_frame_urls(self, driver, mock_page):
        urls = ["https://docs.google.com/a", "https://addons.gsuite.google.com/b"]
        self._wire_frames(mock_page, urls)
        msg = driver.capture_failure("x")
        assert all(u in msg for u in urls)

    def test_probe_reports_match_count_when_found(self, driver, mock_page):
        self._wire_frames(
            mock_page, ["https://addons.gsuite.google.com/form"],
            probe_count=1, visible=True, bbox={"x": 1, "y": 2, "width": 3, "height": 4},
        )
        msg = driver.capture_failure("create_action timeout", probes={"FORM": "input"})
        assert "match_count=1" in msg and "is_visible=True" in msg

    def test_probe_reports_no_match(self, driver, mock_page):
        self._wire_frames(mock_page, ["https://docs.google.com/a"], probe_count=0)
        msg = driver.capture_failure("x", probes={"FORM": "input"})
        assert "(no frame matched)" in msg

    def test_never_raises_on_screenshot_failure(self, driver, mock_page):
        mock_page.screenshot.side_effect = RuntimeError("boom")
        self._wire_frames(mock_page, ["https://docs.google.com/a"])
        msg = driver.capture_failure("x")  # must not raise
        assert "(screenshot capture failed)" in msg


# ---------------------------------------------------------------------------
# click() and mouse_down_hold()
# ---------------------------------------------------------------------------

class TestGestures:
    def test_click_waits_then_clicks(self, driver):
        locator = MagicMock()
        driver.click(locator, timeout="3s")
        locator.wait_for.assert_called_once_with(state="visible", timeout=3000)
        locator.click.assert_called_once_with()

    def test_click_respects_ms_timeout(self, driver):
        locator = MagicMock()
        driver.click(locator, timeout="250ms")
        locator.wait_for.assert_called_with(state="visible", timeout=250)

    def test_mouse_down_hold_waits_then_holds(self, driver):
        locator = MagicMock()
        driver.mouse_down_hold(locator, timeout="2s")
        locator.wait_for.assert_called_once_with(state="visible", timeout=2000)
        locator.click.assert_called_once()

    def test_mouse_down_hold_passes_delay(self, driver):
        locator = MagicMock()
        driver.mouse_down_hold(locator, timeout="2s")
        _, kwargs = locator.click.call_args
        assert "delay" in kwargs


# ---------------------------------------------------------------------------
# set_status()
# ---------------------------------------------------------------------------

class TestSetStatus:
    def _make_card(self):
        """Card whose frame returns status_btn then busy on successive locator() calls."""
        frame = MagicMock()
        status_btn = MagicMock()
        busy = MagicMock()
        frame.locator.side_effect = [status_btn, busy]
        return Card(frame), status_btn, busy

    def test_finds_status_button_by_aria_label(self, driver):
        card, status_btn, _ = self._make_card()
        driver.set_status(card, "In Progress")
        call_arg = card.frame.locator.call_args_list[0][0][0]
        assert 'aria-label="In Progress"' in call_arg

    def test_waits_for_status_button_visibility(self, driver):
        card, status_btn, _ = self._make_card()
        driver.set_status(card, "In Progress")
        status_btn.wait_for.assert_called_with(state="visible", timeout=10000)

    def test_clicks_status_button(self, driver):
        card, status_btn, _ = self._make_card()
        driver.set_status(card, "In Progress")
        status_btn.click.assert_called_once()

    def test_checks_for_busy_state(self, driver):
        card, _, busy = self._make_card()
        driver.set_status(card, "Open")
        # At least one wait_for call on the busy locator
        assert busy.wait_for.call_count >= 1

    def test_no_spinner_does_not_raise(self, driver):
        card, status_btn, busy = self._make_card()
        # Spinner never appears — timeout exception should be swallowed
        busy.wait_for.side_effect = Exception("Timeout — no spinner appeared")
        driver.set_status(card, "Open")  # must not raise
        status_btn.click.assert_called_once()

    def test_spinner_appears_then_clears(self, driver):
        card, _, busy = self._make_card()
        busy.wait_for.side_effect = [None, None]  # visible, then hidden
        driver.set_status(card, "Open")
        assert busy.wait_for.call_count == 2


# ---------------------------------------------------------------------------
# expect_visible()
# ---------------------------------------------------------------------------

class TestExpectVisible:
    def test_waits_for_card_body_visible(self, driver):
        frame = MagicMock()
        inner = MagicMock()
        frame.locator.return_value.first = inner
        card = Card(frame)

        driver.expect_visible(card, timeout="5s")

        inner.wait_for.assert_called_once_with(state="visible", timeout=5000)

    def test_respects_custom_timeout(self, driver):
        frame = MagicMock()
        inner = MagicMock()
        frame.locator.return_value.first = inner
        card = Card(frame)

        driver.expect_visible(card, timeout="10s")

        inner.wait_for.assert_called_once_with(state="visible", timeout=10000)


# ---------------------------------------------------------------------------
# expect_alt()
# ---------------------------------------------------------------------------

class TestExpectAlt:
    def test_passes_when_aria_label_matches(self, driver):
        locator = MagicMock()
        locator.get_attribute.side_effect = lambda a: "In Progress" if a == "aria-label" else None
        driver.expect_alt(locator, "In Progress")  # no exception

    def test_passes_when_alt_attribute_matches(self, driver):
        locator = MagicMock()
        locator.get_attribute.side_effect = lambda a: "In Progress" if a == "alt" else None
        driver.expect_alt(locator, "In Progress")

    def test_passes_when_title_matches(self, driver):
        locator = MagicMock()
        locator.get_attribute.side_effect = lambda a: "In Progress" if a == "title" else None
        driver.expect_alt(locator, "In Progress")

    def test_fails_on_mismatch_severity_fail(self, driver):
        locator = MagicMock()
        locator.get_attribute.side_effect = lambda a: "Open" if a == "aria-label" else None
        with pytest.raises(AssertionError, match="expect_alt"):
            driver.expect_alt(locator, "In Progress", severity=Severity.FAIL)

    def test_warns_on_mismatch_severity_warn(self, driver):
        locator = MagicMock()
        locator.get_attribute.side_effect = lambda a: "Open" if a == "aria-label" else None
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            driver.expect_alt(locator, "In Progress", severity=Severity.WARN)
        assert len(caught) == 1
        assert "expect_alt" in str(caught[0].message)

    def test_fails_no_attribute_found_severity_fail(self, driver):
        locator = MagicMock()
        locator.get_attribute.return_value = None
        with pytest.raises(AssertionError, match="no aria-label"):
            driver.expect_alt(locator, "In Progress")

    def test_warns_no_attribute_found_severity_warn(self, driver):
        locator = MagicMock()
        locator.get_attribute.return_value = None
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            driver.expect_alt(locator, "In Progress", severity=Severity.WARN)
        assert len(caught) == 1


# ---------------------------------------------------------------------------
# open_sidebar() — existing; referenced by new sidebar acts
# ---------------------------------------------------------------------------

class TestOpenSidebar:
    def _setup_sidebar_frame(self, mock_page):
        # Simulate a GAS sidebar frame that has 'Sync now' (findAddonFrame pattern)
        frame = MagicMock()
        sync_now_locator = MagicMock()
        sync_now_locator.count.return_value = 1
        frame.get_by_role.return_value = sync_now_locator
        mock_page.frames = [frame]
        mock_page.locator.return_value.first = MagicMock()
        return frame

    def test_sets_current_card(self, driver, mock_page):
        self._setup_sidebar_frame(mock_page)
        result = driver.open_sidebar()
        assert driver._current_card is not None
        assert isinstance(result, Card)

    def test_current_card_is_returned_card(self, driver, mock_page):
        self._setup_sidebar_frame(mock_page)
        card = driver.open_sidebar()
        assert driver._current_card is card


# ---------------------------------------------------------------------------
# sidebar_sync()
# ---------------------------------------------------------------------------

class TestSidebarSync:
    def _make_driver_with_sidebar(self, mock_page):
        """Driver with _current_card pre-set (sidebar already open)."""
        frame = MagicMock()
        sync_btn = MagicMock()
        busy = MagicMock()
        # card frame: locator calls → [sync_btn, busy]
        frame.locator.side_effect = [sync_btn, busy]
        card = Card(frame)
        driver = UiDriver(mock_page, doc_id="DOCID123")
        driver._current_card = card
        return driver, frame, sync_btn, busy

    def test_locates_sync_button_inside_card_frame(self, mock_page):
        driver, frame, sync_btn, busy = self._make_driver_with_sidebar(mock_page)
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            driver.sidebar_sync(timeout="60s")
        selector = frame.locator.call_args_list[0][0][0]
        assert "sync" in selector.lower() or "Sync" in selector

    def test_clicks_sync_button(self, mock_page):
        driver, frame, sync_btn, busy = self._make_driver_with_sidebar(mock_page)
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            driver.sidebar_sync(timeout="60s")
        sync_btn.click.assert_called_once()

    def test_waits_for_busy_state(self, mock_page):
        driver, frame, sync_btn, busy = self._make_driver_with_sidebar(mock_page)
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            driver.sidebar_sync(timeout="60s")
        assert busy.wait_for.call_count >= 1

    def test_no_spinner_does_not_raise(self, mock_page):
        driver, frame, sync_btn, busy = self._make_driver_with_sidebar(mock_page)
        busy.wait_for.side_effect = Exception("Timeout — no spinner")
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            driver.sidebar_sync(timeout="60s")  # must not raise
        sync_btn.click.assert_called_once()

    def test_returns_none(self, mock_page):
        driver, frame, sync_btn, busy = self._make_driver_with_sidebar(mock_page)
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            result = driver.sidebar_sync(timeout="60s")
        assert result is None

    def test_opens_sidebar_if_no_current_card(self, mock_page):
        frame = MagicMock()
        frame.locator.return_value = MagicMock()
        card = Card(frame)
        driver = UiDriver(mock_page, doc_id="DOCID123")
        driver._current_card = None
        with patch.object(driver, "open_sidebar", return_value=card) as mock_open:
            driver.sidebar_sync(timeout="5s")
        mock_open.assert_called_once()


# ---------------------------------------------------------------------------
# insert_tracker_button()
# ---------------------------------------------------------------------------

class TestInsertTrackerButton:
    def _make_driver_with_sidebar(self, mock_page):
        frame = MagicMock()
        insert_btn = MagicMock()
        busy = MagicMock()
        frame.locator.side_effect = [insert_btn, busy]
        card = Card(frame)
        driver = UiDriver(mock_page, doc_id="DOCID123")
        driver._current_card = card
        return driver, frame, insert_btn, busy

    def test_locates_insert_tracker_button_inside_card_frame(self, mock_page):
        driver, frame, insert_btn, busy = self._make_driver_with_sidebar(mock_page)
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            driver.insert_tracker_button(timeout="30s")
        selector = frame.locator.call_args_list[0][0][0]
        assert "tracker" in selector.lower() or "insert" in selector.lower()

    def test_clicks_insert_button(self, mock_page):
        driver, frame, insert_btn, busy = self._make_driver_with_sidebar(mock_page)
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            driver.insert_tracker_button(timeout="30s")
        insert_btn.click.assert_called_once()

    def test_waits_for_busy_state(self, mock_page):
        driver, frame, insert_btn, busy = self._make_driver_with_sidebar(mock_page)
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            driver.insert_tracker_button(timeout="30s")
        assert busy.wait_for.call_count >= 1

    def test_no_spinner_does_not_raise(self, mock_page):
        driver, frame, insert_btn, busy = self._make_driver_with_sidebar(mock_page)
        busy.wait_for.side_effect = Exception("no spinner")
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            driver.insert_tracker_button(timeout="30s")  # must not raise
        insert_btn.click.assert_called_once()

    def test_returns_none(self, mock_page):
        driver, frame, insert_btn, busy = self._make_driver_with_sidebar(mock_page)
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            result = driver.insert_tracker_button(timeout="30s")
        assert result is None

    def test_opens_sidebar_if_no_current_card(self, mock_page):
        frame = MagicMock()
        frame.locator.return_value = MagicMock()
        card = Card(frame)
        driver = UiDriver(mock_page, doc_id="DOCID123")
        driver._current_card = None
        with patch.object(driver, "open_sidebar", return_value=card) as mock_open:
            driver.insert_tracker_button(timeout="5s")
        mock_open.assert_called_once()


# ---------------------------------------------------------------------------
# sidebar_delete()
# ---------------------------------------------------------------------------

class TestSidebarDelete:
    def _make_driver_for_delete(self, mock_page, action_id="AI-3"):
        from scn.ai import ai as Ai
        target = Ai(action="some action", action_id=action_id)

        frame = MagicMock()
        label = MagicMock()        # the "AI-N •" DecoratedText label (frame.get_by_text)
        row_locator = MagicMock()  # _sidebar_row result: label.locator(xpath sibling)
        delete_btn = MagicMock()   # actual button: row.locator('[aria-label="Delete action"]')
        busy = MagicMock()
        # _sidebar_row: label = frame.get_by_text("AI-N •"); row = label.locator(xpath).
        # sidebar_delete then locates the button via row.locator(_SIDEBAR_DELETE).
        label.locator.return_value = row_locator
        row_locator.locator.return_value = delete_btn
        frame.get_by_text.return_value = label
        frame.locator.return_value = busy

        card = Card(frame)
        driver = UiDriver(mock_page, doc_id="DOCID123")
        driver._current_card = card
        return driver, frame, row_locator, delete_btn, busy, target

    def test_scopes_to_action_id_row(self, mock_page):
        driver, frame, row_locator, delete_btn, busy, target = (
            self._make_driver_for_delete(mock_page)
        )
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            driver.sidebar_delete(target, timeout="15s")
        call_args = frame.get_by_text.call_args
        assert "AI-3" in str(call_args)

    def test_locates_delete_button_by_aria_label(self, mock_page):
        driver, frame, row_locator, delete_btn, busy, target = (
            self._make_driver_for_delete(mock_page)
        )
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            driver.sidebar_delete(target, timeout="15s")
        selector = row_locator.locator.call_args[0][0]
        assert "Delete action" in selector or "delete" in selector.lower()

    def test_clicks_delete_button(self, mock_page):
        driver, frame, row_locator, delete_btn, busy, target = (
            self._make_driver_for_delete(mock_page)
        )
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            driver.sidebar_delete(target, timeout="15s")
        delete_btn.click.assert_called_once()

    def test_waits_for_busy_state(self, mock_page):
        driver, frame, row_locator, delete_btn, busy, target = (
            self._make_driver_for_delete(mock_page)
        )
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            driver.sidebar_delete(target, timeout="15s")
        assert busy.wait_for.call_count >= 1

    def test_no_spinner_does_not_raise(self, mock_page):
        driver, frame, row_locator, delete_btn, busy, target = (
            self._make_driver_for_delete(mock_page)
        )
        busy.wait_for.side_effect = Exception("no spinner")
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            driver.sidebar_delete(target, timeout="15s")  # must not raise
        delete_btn.click.assert_called_once()

    def test_returns_none(self, mock_page):
        driver, frame, row_locator, delete_btn, busy, target = (
            self._make_driver_for_delete(mock_page)
        )
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            result = driver.sidebar_delete(target, timeout="15s")
        assert result is None


# ---------------------------------------------------------------------------
# sidebar_set_status()
# ---------------------------------------------------------------------------

class TestSidebarSetStatus:
    def _make_driver_for_set_status(self, mock_page, action_id="AI-2"):
        from scn.ai import ai as Ai
        target = Ai(action="some action", action_id=action_id)

        frame = MagicMock()
        label = MagicMock()        # the "AI-N •" DecoratedText label (frame.get_by_text)
        row_locator = MagicMock()  # _sidebar_row result: label.locator(xpath sibling)
        status_btn = MagicMock()   # actual button: row.locator('[aria-label="Set <status>"]')
        busy = MagicMock()
        # _sidebar_row: label = frame.get_by_text("AI-N •"); row = label.locator(xpath).
        # sidebar_set_status then locates the button via row.locator('[aria-label="Set ..."]').
        label.locator.return_value = row_locator
        row_locator.locator.return_value = status_btn
        frame.get_by_text.return_value = label
        frame.locator.return_value = busy

        card = Card(frame)
        driver = UiDriver(mock_page, doc_id="DOCID123")
        driver._current_card = card
        return driver, frame, row_locator, status_btn, busy, target

    def test_scopes_to_action_id_row(self, mock_page):
        driver, frame, row_locator, status_btn, busy, target = (
            self._make_driver_for_set_status(mock_page)
        )
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            driver.sidebar_set_status(target, "In Progress", timeout="15s")
        call_args = frame.get_by_text.call_args
        assert "AI-2" in str(call_args)

    def test_locates_status_control_inside_row(self, mock_page):
        driver, frame, row_locator, status_btn, busy, target = (
            self._make_driver_for_set_status(mock_page)
        )
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            driver.sidebar_set_status(target, "In Progress", timeout="15s")
        selector = row_locator.locator.call_args[0][0]
        assert "In Progress" in selector or "status" in selector.lower() or "aria-label" in selector

    def test_clicks_status_control(self, mock_page):
        driver, frame, row_locator, status_btn, busy, target = (
            self._make_driver_for_set_status(mock_page)
        )
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            driver.sidebar_set_status(target, "In Progress", timeout="15s")
        status_btn.click.assert_called_once()

    def test_waits_for_busy_state(self, mock_page):
        driver, frame, row_locator, status_btn, busy, target = (
            self._make_driver_for_set_status(mock_page)
        )
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            driver.sidebar_set_status(target, "In Progress", timeout="15s")
        assert busy.wait_for.call_count >= 1

    def test_no_spinner_does_not_raise(self, mock_page):
        driver, frame, row_locator, status_btn, busy, target = (
            self._make_driver_for_set_status(mock_page)
        )
        busy.wait_for.side_effect = Exception("no spinner")
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            driver.sidebar_set_status(target, "In Progress", timeout="15s")  # must not raise
        status_btn.click.assert_called_once()

    def test_returns_none(self, mock_page):
        driver, frame, row_locator, status_btn, busy, target = (
            self._make_driver_for_set_status(mock_page)
        )
        with patch.object(driver, "open_sidebar", return_value=driver._current_card):
            result = driver.sidebar_set_status(target, "In Progress", timeout="15s")
        assert result is None

    def test_distinct_from_existing_set_status(self, driver):
        """sidebar_set_status(ai, status) is distinct from set_status(card, status)."""
        import inspect
        sig_new = inspect.signature(driver.sidebar_set_status)
        sig_old = inspect.signature(driver.set_status)
        # bound methods: parameters list excludes 'self'
        new_params = list(sig_new.parameters)
        old_params = list(sig_old.parameters)
        assert new_params[0] == "target"
        assert old_params[0] == "card"


# ---------------------------------------------------------------------------
# ScenarioSession.expect_visible / .expect_alt delegation
# ---------------------------------------------------------------------------

class TestSessionUiDelegation:
    """expect_visible and expect_alt on the session delegate to scn.ui."""

    def test_session_expect_visible_requires_ui(self):
        from scn.session import ScenarioSession
        scn = ScenarioSession(doc_id="D", sheet_id="S", settings={})
        with pytest.raises(RuntimeError, match="scn.expect_visible requires scn.ui"):
            scn.expect_visible(MagicMock())

    def test_session_expect_alt_requires_ui(self):
        from scn.session import ScenarioSession
        scn = ScenarioSession(doc_id="D", sheet_id="S", settings={})
        with pytest.raises(RuntimeError, match="scn.expect_alt requires scn.ui"):
            scn.expect_alt(MagicMock(), "In Progress")

    def test_session_expect_visible_delegates_to_ui(self, mock_page):
        from scn.session import ScenarioSession
        scn = ScenarioSession(doc_id="DOCID123", sheet_id="S", settings={})
        scn.ui = UiDriver(mock_page, doc_id="DOCID123")
        card = Card(MagicMock())
        card.frame.locator.return_value.first = MagicMock()
        with patch.object(scn.ui, "expect_visible") as mock_ev:
            scn.expect_visible(card, timeout="3s")
            mock_ev.assert_called_once_with(card, timeout="3s")

    def test_session_expect_alt_delegates_to_ui(self, mock_page):
        from scn.session import ScenarioSession
        scn = ScenarioSession(doc_id="DOCID123", sheet_id="S", settings={})
        scn.ui = UiDriver(mock_page, doc_id="DOCID123")
        locator = MagicMock()
        with patch.object(scn.ui, "expect_alt") as mock_ea:
            scn.expect_alt(locator, "Open", severity=Severity.WARN)
            mock_ea.assert_called_once_with(locator, "Open", severity=Severity.WARN)
