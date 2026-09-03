"""Unit tests for tests/helpers/auth_probe.py (gts-85x3.1).

Strategy: mock playwright.sync_api.sync_playwright's browser/context/page chain --
no real network, no real browser. Verifies the pure classification logic
(signed-in vs signed-out) and the headed/headless pass-through only.
"""
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import auth_probe as ap


def _mock_playwright(*, final_url, page_content=""):
    """Build a sync_playwright()-shaped mock whose page.goto lands on final_url.

    `page_content` feeds page.inner_text("body") -- the probe classifies on
    visible text, not raw page.content() HTML/JS source (gts-check-auth false
    positive: docs.google.com always embeds the literal string "Signed out"
    in an account-switcher JSON config blob regardless of actual sign-in
    state, so scanning full source falsely flags a live session as dead)."""
    page = MagicMock()
    page.url = final_url
    page.inner_text.return_value = page_content
    ctx = MagicMock()
    ctx.new_page.return_value = page
    browser = MagicMock()
    browser.new_context.return_value = ctx
    pw = MagicMock()
    pw.chromium.launch.return_value = browser
    pw_cm = MagicMock()
    pw_cm.__enter__.return_value = pw
    pw_cm.__exit__.return_value = False
    return pw_cm, browser, ctx, page


def test_probe_ok_when_landed_on_docs_home(tmp_path):
    auth_file = tmp_path / "primary.json"
    auth_file.write_text("{}")
    pw_cm, browser, ctx, page = _mock_playwright(final_url="https://docs.google.com/")

    with patch.object(ap, "resolve_auth_file", return_value=auth_file), \
         patch("playwright.sync_api.sync_playwright", return_value=pw_cm):
        result = ap.probe_auth_session("primary")

    assert result.ok is True
    assert "docs.google.com" in result.final_url


def test_probe_fails_when_redirected_to_signin(tmp_path):
    auth_file = tmp_path / "primary.json"
    auth_file.write_text("{}")
    pw_cm, browser, ctx, page = _mock_playwright(
        final_url="https://accounts.google.com/v3/signin/accountchooser?continue=...",
    )

    with patch.object(ap, "resolve_auth_file", return_value=auth_file), \
         patch("playwright.sync_api.sync_playwright", return_value=pw_cm):
        result = ap.probe_auth_session("primary")

    assert result.ok is False
    assert "accounts.google.com" in result.final_url
    assert "Signed out" in result.message or "signed out" in result.message.lower()


def test_probe_fails_when_page_content_shows_signed_out(tmp_path):
    """Some sign-in interstitials land on a docs.google.com-hosted URL (e.g. a
    passive-login redirect target) without ever showing accounts.google.com in
    page.url -- the account-chooser 'Signed out' text visible in the page body
    is the only positive signal in that case."""
    auth_file = tmp_path / "primary.json"
    auth_file.write_text("{}")
    pw_cm, browser, ctx, page = _mock_playwright(
        final_url="https://docs.google.com/document/d/x/edit",
        page_content="Stuart Donaldson\nSigned out",
    )

    with patch.object(ap, "resolve_auth_file", return_value=auth_file), \
         patch("playwright.sync_api.sync_playwright", return_value=pw_cm):
        result = ap.probe_auth_session("primary")

    assert result.ok is False


def test_probe_ignores_signed_out_string_buried_in_raw_page_source(tmp_path):
    """Regression for the false positive found 2026-08-21: docs.google.com
    always embeds the literal string "Signed out" in a JSON config blob for
    the account-switcher menu, in page.content() (raw HTML/JS), regardless of
    actual sign-in state. The probe must classify on visible text
    (inner_text) only, so a real signed-in session with that boilerplate
    still in its source is not misreported as dead."""
    auth_file = tmp_path / "primary.json"
    auth_file.write_text("{}")
    pw_cm, browser, ctx, page = _mock_playwright(
        final_url="https://docs.google.com/document/u/0/?pli=1&tgif=d",
        page_content="Docs\nRecently used templates\nBlank document\nStart a new document",
    )
    page.content.return_value = (
        '...,"Profile","",1,null,"Signed out","https://accounts.google.com/AccountChooser?...'
    )

    with patch.object(ap, "resolve_auth_file", return_value=auth_file), \
         patch("playwright.sync_api.sync_playwright", return_value=pw_cm):
        result = ap.probe_auth_session("primary")

    assert result.ok is True
    page.content.assert_not_called()


def test_probe_raises_when_auth_file_missing(tmp_path):
    missing = tmp_path / "nope.json"
    with patch.object(ap, "resolve_auth_file", return_value=missing):
        with pytest.raises(ap.AuthSessionDeadError, match="no auth file"):
            ap.probe_auth_session("primary")


def test_probe_launches_headed_when_requested(tmp_path):
    auth_file = tmp_path / "primary.json"
    auth_file.write_text("{}")
    pw_cm, browser, ctx, page = _mock_playwright(final_url="https://docs.google.com/")

    with patch.object(ap, "resolve_auth_file", return_value=auth_file), \
         patch("playwright.sync_api.sync_playwright", return_value=pw_cm) as mock_pw:
        ap.probe_auth_session("primary", headless=False)

    pw_cm.__enter__.return_value.chromium.launch.assert_called_once_with(headless=False)


def test_probe_launches_headless_by_default(tmp_path):
    auth_file = tmp_path / "primary.json"
    auth_file.write_text("{}")
    pw_cm, browser, ctx, page = _mock_playwright(final_url="https://docs.google.com/")

    with patch.object(ap, "resolve_auth_file", return_value=auth_file), \
         patch("playwright.sync_api.sync_playwright", return_value=pw_cm):
        ap.probe_auth_session("primary")

    pw_cm.__enter__.return_value.chromium.launch.assert_called_once_with(headless=True)


def test_assert_alive_raises_auth_session_dead_error_on_failed_probe(tmp_path):
    """assert_alive() is the fail-fast entry point conftest.py's session fixture
    and download.py's reactive-refresh path both call -- it must turn a failed
    probe into AuthSessionDeadError, not just a falsy return value."""
    auth_file = tmp_path / "primary.json"
    auth_file.write_text("{}")
    pw_cm, browser, ctx, page = _mock_playwright(
        final_url="https://accounts.google.com/v3/signin/accountchooser",
    )

    with patch.object(ap, "resolve_auth_file", return_value=auth_file), \
         patch("playwright.sync_api.sync_playwright", return_value=pw_cm):
        with pytest.raises(ap.AuthSessionDeadError, match="auth.setup.js"):
            ap.assert_alive("primary")


def test_probe_calls_before_close_hook_before_browser_closes(tmp_path):
    """scripts/check_auth.py --headed relies on before_close to hold the
    window open for visual debugging instead of it vanishing the instant the
    probe finishes -- verify the hook runs, and runs before browser.close()."""
    auth_file = tmp_path / "primary.json"
    auth_file.write_text("{}")
    pw_cm, browser, ctx, page = _mock_playwright(final_url="https://docs.google.com/")

    calls = []
    browser.close.side_effect = lambda: calls.append("close")

    def hook():
        calls.append("hook")

    with patch.object(ap, "resolve_auth_file", return_value=auth_file), \
         patch("playwright.sync_api.sync_playwright", return_value=pw_cm):
        ap.probe_auth_session("primary", before_close=hook)

    assert calls == ["hook", "close"]


def test_assert_alive_does_not_raise_on_healthy_session(tmp_path):
    auth_file = tmp_path / "primary.json"
    auth_file.write_text("{}")
    pw_cm, browser, ctx, page = _mock_playwright(final_url="https://docs.google.com/")

    with patch.object(ap, "resolve_auth_file", return_value=auth_file), \
         patch("playwright.sync_api.sync_playwright", return_value=pw_cm):
        ap.assert_alive("primary")  # must not raise
