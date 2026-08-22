"""Unit tests for tests/helpers/download.py's auth-refresh path (gts-f3me.4).

Strategy: mock requests.Session.get and _refresh_auth_state directly -- no
real network, no real Playwright browser. Verifies the Python retry/refresh
logic only: a stale-looking response triggers exactly one refresh-and-retry,
a 429 does not, and a proactively-stale on-disk snapshot is refreshed before
the first request even goes out.
"""
import json
import time
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import download as dl


def _resp(status_code=200, content=b"", headers=None, url="https://docs.google.com/x"):
    r = MagicMock()
    r.status_code = status_code
    r.content = content
    r.text = content.decode("utf-8", errors="ignore")
    r.headers = headers or {}
    r.url = url
    r.raise_for_status = MagicMock()
    return r


@pytest.fixture
def auth_file(tmp_path):
    p = tmp_path / "primary.json"
    p.write_text(json.dumps({"cookies": [
        {"name": "SID", "value": "old", "domain": ".google.com", "path": "/"},
    ]}))
    return p


def test_looks_stale_true_for_html_login_page():
    resp = _resp(status_code=200, headers={"Content-Type": "text/html; charset=UTF-8"})
    assert dl._looks_stale(resp) is True


def test_looks_stale_false_for_429_rate_limit():
    """A 429 is a quota issue handled by download_xlsx's own retry loop --
    it must not be treated as an auth-staleness signal."""
    resp = _resp(status_code=429, headers={"Content-Type": "text/html"})
    assert dl._looks_stale(resp) is False


def test_looks_stale_true_for_accounts_google_redirect():
    resp = _resp(status_code=200, url="https://accounts.google.com/RotateCookiesPage")
    assert dl._looks_stale(resp) is True


def test_get_with_refresh_retries_once_on_stale_response(auth_file):
    """A stale first response triggers exactly one _refresh_auth_state call
    and one retry; the retried response is returned."""
    stale = _resp(status_code=200, headers={"Content-Type": "text/html"})
    fresh = _resp(status_code=200, content=dl._OOXML_MAGIC + b"...")

    with patch.object(dl, "resolve_auth_file", return_value=auth_file), \
         patch.object(dl, "_refresh_auth_state", return_value=True) as mock_refresh, \
         patch("requests.Session.get", side_effect=[stale, fresh]) as mock_get:
        got = dl._get_with_refresh(
            "https://docs.google.com/spreadsheets/d/x/export?format=xlsx",
            timeout=10,
            is_stale=dl._looks_stale,
        )

    assert got is fresh
    mock_refresh.assert_called_once()
    assert mock_get.call_count == 2


def test_get_with_refresh_does_not_retry_when_response_is_fresh(auth_file):
    fresh = _resp(status_code=200, content=dl._OOXML_MAGIC + b"...")

    with patch.object(dl, "resolve_auth_file", return_value=auth_file), \
         patch.object(dl, "_refresh_auth_state") as mock_refresh, \
         patch("requests.Session.get", return_value=fresh) as mock_get:
        got = dl._get_with_refresh(
            "https://docs.google.com/spreadsheets/d/x/export?format=xlsx",
            timeout=10,
            is_stale=dl._looks_stale,
        )

    assert got is fresh
    mock_refresh.assert_not_called()
    assert mock_get.call_count == 1


def test_get_with_refresh_raises_auth_session_dead_when_retry_still_stale(auth_file):
    """gts-85x3.1: if the reactive refresh's own retry is STILL stale, the
    session is fully signed out (refresh cannot fix that -- see
    _refresh_auth_state's own docstring) -- fail fast with a distinct error
    instead of returning the still-bad response for a generic caller-side
    check (e.g. download_xlsx's magic-bytes check) to fail on less clearly."""
    stale = _resp(status_code=200, headers={"Content-Type": "text/html"})
    still_stale = _resp(status_code=200, headers={"Content-Type": "text/html"})

    with patch.object(dl, "resolve_auth_file", return_value=auth_file), \
         patch.object(dl, "_refresh_auth_state", return_value=True) as mock_refresh, \
         patch("requests.Session.get", side_effect=[stale, still_stale]) as mock_get:
        with pytest.raises(dl.AuthSessionDeadError, match="auth.setup.js"):
            dl._get_with_refresh(
                "https://docs.google.com/spreadsheets/d/x/export?format=xlsx",
                timeout=10,
                is_stale=dl._looks_stale,
            )

    mock_refresh.assert_called_once()
    assert mock_get.call_count == 2


def test_authed_session_proactively_refreshes_when_file_is_old(auth_file):
    """A storage_state.json older than _STALE_THRESHOLD_S is refreshed
    before a session is built from it, without waiting for a failure."""
    old_mtime = time.time() - (dl._STALE_THRESHOLD_S + 60)
    import os
    os.utime(auth_file, (old_mtime, old_mtime))

    with patch.object(dl, "resolve_auth_file", return_value=auth_file), \
         patch.object(dl, "_refresh_auth_state", return_value=True) as mock_refresh:
        dl._authed_session()

    mock_refresh.assert_called_once_with("primary")


def test_authed_session_skips_refresh_when_file_is_fresh(auth_file):
    with patch.object(dl, "resolve_auth_file", return_value=auth_file), \
         patch.object(dl, "_refresh_auth_state") as mock_refresh:
        dl._authed_session()

    mock_refresh.assert_not_called()


def test_refresh_auth_state_returns_false_without_auth_file(tmp_path):
    missing = tmp_path / "nope.json"
    with patch.object(dl, "resolve_auth_file", return_value=missing):
        assert dl._refresh_auth_state("primary") is False


def test_refresh_auth_state_returns_false_when_playwright_unavailable(auth_file):
    with patch.object(dl, "resolve_auth_file", return_value=auth_file):
        with patch.dict("sys.modules", {"playwright.sync_api": None}):
            assert dl._refresh_auth_state("primary") is False
