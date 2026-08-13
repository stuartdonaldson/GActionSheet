"""
test_fixture_invoke_retry.py — backstop for GTaskSheet-z6bx.

`invoke_fixture` used to be a third, non-retrying copy of the WebApp POST
implementation. It sat on the session-scoped autouse `_reset_test_state`
fixture path (tests/conftest.py), so a single transient `/exec` routing
symptom (HTTP 404, or the GAS echo page arriving instead of JSON) aborted an
entire pytest session before any test code ran.

These tests prove the retry actually *engages* for both symptoms — not just
that a happy-path call succeeds — and that non-retryable failures still raise
immediately, unretried. No live GAS backend is used; `urllib.request.urlopen`
and `time.sleep` are mocked at the `scn.session` module the retry now lives
in, since `invoke_fixture` delegates its transport there (GTaskSheet-z6bx,
shape 2 — see bd show gts-z6bx).
"""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers.fixture_invoke import FixtureError, FixtureTokenError, invoke_fixture

SETTINGS = {"webappTestUrl": "https://example.com/exec", "testToken": "tok-123"}


def _fake_response(body: str, url: str = SETTINGS["webappTestUrl"]):
    """A context-manager stand-in for urllib.request.urlopen's return value."""
    resp = MagicMock()
    resp.read.return_value = body.encode("utf-8")
    resp.geturl.return_value = url
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def _http_error(code: int, body: str = "Page Not Found"):
    return urllib.error.HTTPError(
        url=SETTINGS["webappTestUrl"], code=code, msg="err", hdrs=None,
        fp=io.BytesIO(body.encode("utf-8")),
    )


@pytest.fixture(autouse=True)
def _no_real_sleep():
    """Every test in this module runs the retry path; never actually sleep 3s."""
    with patch("scn.session.time.sleep") as sleep_mock:
        yield sleep_mock


def test_retries_and_recovers_on_http_404_then_success():
    """A 404 on attempt 1 (the Drive 'Page Not Found' routing symptom) is retried
    and a subsequent success is returned — not raised on the first attempt."""
    ok = _fake_response(json.dumps({"tag": "fixture.x", "data": {}}))
    with patch(
        "scn.session.urllib.request.urlopen",
        side_effect=[_http_error(404), ok],
    ) as urlopen_mock:
        result = invoke_fixture("x", "doc123", SETTINGS)

    assert result == {"tag": "fixture.x", "data": {}}
    assert urlopen_mock.call_count == 2, (
        "retry did not engage — invoke_fixture must retry once on HTTP 404, "
        "not raise on the first attempt"
    )


def test_retries_and_recovers_on_echo_page_then_success():
    """A non-JSON echo-page body on attempt 1 is retried and a subsequent
    JSON response is returned."""
    echo_page = _fake_response("<html>google apps script echo</html>")
    ok = _fake_response(json.dumps({"tag": "fixture.x", "data": {}}))
    with patch(
        "scn.session.urllib.request.urlopen",
        side_effect=[echo_page, ok],
    ) as urlopen_mock:
        result = invoke_fixture("x", "doc123", SETTINGS)

    assert result == {"tag": "fixture.x", "data": {}}
    assert urlopen_mock.call_count == 2, (
        "retry did not engage — invoke_fixture must retry once on a non-JSON "
        "echo-page body, not raise on the first attempt"
    )


def test_exhaustion_after_repeated_404_names_attempt_count():
    with patch(
        "scn.session.urllib.request.urlopen",
        side_effect=[_http_error(404), _http_error(404), _http_error(404)],
    ):
        with pytest.raises(RuntimeError, match=r"3 attempts"):
            invoke_fixture("x", "doc123", SETTINGS)


def test_non_404_http_status_raises_immediately_not_retried():
    with patch(
        "scn.session.urllib.request.urlopen",
        side_effect=[_http_error(500, "server error")],
    ) as urlopen_mock:
        with pytest.raises(RuntimeError):
            invoke_fixture("x", "doc123", SETTINGS)
    assert urlopen_mock.call_count == 1


def test_url_error_raises_immediately_not_retried():
    with patch(
        "scn.session.urllib.request.urlopen",
        side_effect=[urllib.error.URLError("network down")],
    ) as urlopen_mock:
        with pytest.raises(RuntimeError):
            invoke_fixture("x", "doc123", SETTINGS)
    assert urlopen_mock.call_count == 1


def test_token_rejection_raises_fixture_invoke_token_error():
    rejected = _fake_response("test-token-unauthorized")
    with patch("scn.session.urllib.request.urlopen", side_effect=[rejected]):
        with pytest.raises(FixtureTokenError):
            invoke_fixture("x", "doc123", SETTINGS)


def test_fixture_error_body_raises_fixture_invoke_fixture_error():
    error_body = _fake_response(json.dumps({"error": "boom"}))
    with patch("scn.session.urllib.request.urlopen", side_effect=[error_body]):
        with pytest.raises(FixtureError):
            invoke_fixture("x", "doc123", SETTINGS)
