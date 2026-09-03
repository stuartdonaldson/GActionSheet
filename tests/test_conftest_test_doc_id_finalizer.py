"""
test_conftest_test_doc_id_finalizer.py — gts-z55w (stage `harness-leaks`,
knowledge-base/staging/docdata-litter-apt-speed.md).

28 `GActionSheet-Test-session-*` Docs were found leaked in Drive (alive since
2026-06-11): `test_doc_id` (tests/conftest.py) used to trash its clone as
plain code after `yield`, which pytest's own generator-fixture teardown
machinery must resume the suspended generator to reach — a run that dies
(interrupted, crashed dependency, xdist worker loss) before that resumption
happens leaks the clone with nothing to catch it, unlike
`ScenarioSession.new_doc()`'s clone, which registers its trash via
`request.addfinalizer` (`_deferred_trash`, scn/session.py:556) instead.

This is a Python-logic unit test (no live GAS): it drives `test_doc_id`'s
fixture function directly against a fake `request` that records finalizers
instead of running them via generator resumption, mocking
`scn.session._http_post` so no network call happens. It proves the trash call
is reachable through the registered finalizer callback alone -- "verified
with a deliberately-interrupted session" per gts-z55w's AC -- and that the
callback is idempotent and swallows its own POST failure so a teardown-time
network blip can't mask the real failure that triggered teardown.
"""
import pytest

import scn.session as session_mod
from tests.conftest import test_doc_id as _test_doc_id_fixture

# gts-aqpk: fast/local tier -- this module makes no live GAS/Google round trip
# (verified offline with sockets blocked). See docs/OPERATIONS.md "Test tiers".
pytestmark = pytest.mark.no_live_session

# Unwrap the @pytest.fixture marker to call the underlying generator function
# directly -- pytest fixtures are not callable as plain functions. Named
# without a "test_" prefix so pytest's collector doesn't mistake this
# generator function itself for a test.
_test_doc_id_fn = _test_doc_id_fixture.__wrapped__


SETTINGS = {
    "webappTestUrl": "https://example.com/exec",
    "testToken": "tok-abc",
    "testDocId": "master-doc-1",
}


class _FakeRequest:
    """Minimal stand-in for pytest's FixtureRequest: records finalizers
    without ever running them via generator resumption."""

    def __init__(self):
        self.finalizers = []

    def addfinalizer(self, fn):
        self.finalizers.append(fn)


def _drive_to_yield(gen):
    """Advance a generator-based fixture to its `yield` and return the value."""
    return next(gen)


def test_end_session_reachable_without_generator_resumption(monkeypatch):
    """The clone-trash POST fires via the registered finalizer alone -- the
    generator is never resumed past `yield`, simulating a run that dies
    before pytest's normal teardown would resume it."""
    posts = []

    def fake_http_post(url, payload, timeout=360):
        posts.append(payload)
        return {"ok": True, "data": {"cloneId": "clone-1"}}

    monkeypatch.setattr(session_mod, "_http_post", fake_http_post)

    fake_request = _FakeRequest()
    gen = _test_doc_id_fn(SETTINGS, fake_request)
    clone_id = _drive_to_yield(gen)

    assert clone_id == "clone-1"
    assert len(fake_request.finalizers) == 1, (
        "expected test_doc_id to register exactly one finalizer via "
        "request.addfinalizer, mirroring ScenarioSession.new_doc()"
    )
    end_posts_before = [p for p in posts if p["fixture"] == "end_test_session"]
    assert end_posts_before == [], "end_test_session must not fire before the finalizer runs"

    # Simulate the crash: never call next(gen) again. Invoke the registered
    # finalizer directly, exactly as pytest's teardown machinery would.
    fake_request.finalizers[0]()

    end_posts_after = [p for p in posts if p["fixture"] == "end_test_session"]
    assert len(end_posts_after) == 1
    assert end_posts_after[0]["testDocId"] == "clone-1"
    assert end_posts_after[0]["masterDocId"] == "master-doc-1"


def test_end_session_finalizer_is_idempotent(monkeypatch):
    """A second invocation (e.g. both an explicit call and pytest's own
    teardown reaching it) must not double-POST."""
    posts = []
    monkeypatch.setattr(
        session_mod, "_http_post",
        lambda url, payload, timeout=360: posts.append(payload) or {"ok": True, "data": {"cloneId": "clone-2"}},
    )

    fake_request = _FakeRequest()
    gen = _test_doc_id_fn(SETTINGS, fake_request)
    _drive_to_yield(gen)

    fake_request.finalizers[0]()
    fake_request.finalizers[0]()

    end_posts = [p for p in posts if p["fixture"] == "end_test_session"]
    assert len(end_posts) == 1, "finalizer fired the end_test_session POST more than once"


def test_end_session_finalizer_swallows_post_failure(monkeypatch):
    """A teardown-time network failure must not raise out of the finalizer --
    it would otherwise mask the real failure that triggered teardown."""
    calls = {"begin": 0}

    def fake_http_post(url, payload, timeout=360):
        if payload["fixture"] == "begin_test_session":
            calls["begin"] += 1
            return {"ok": True, "data": {"cloneId": "clone-3"}}
        raise RuntimeError("simulated transient routing blip")

    monkeypatch.setattr(session_mod, "_http_post", fake_http_post)

    fake_request = _FakeRequest()
    gen = _test_doc_id_fn(SETTINGS, fake_request)
    _drive_to_yield(gen)

    fake_request.finalizers[0]()  # must not raise
