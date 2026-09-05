"""test_scn_outcomes.py — gts-u6ew.6 (H6).

Focused tests for scn/outcomes.py's classify() and BoundaryFault: the one
owning classification helper (I12) that distinguishes a boundary fault from
an assertion failure by type, not by message-matching. Pure logic, no live
GAS/Google round trip (T12 — specifiable oracle).
"""
import pytest

from scn.outcomes import ASSERTION_FAILURE, BOUNDARY_FAULT, PASS, BoundaryFault, classify

pytestmark = pytest.mark.no_live_session


def test_classify_none_is_pass():
    assert classify(None) == PASS


def test_classify_boundary_fault_instance():
    assert classify(BoundaryFault("timed out")) == BOUNDARY_FAULT


def test_classify_bare_runtime_error_is_assertion_failure():
    # A bare RuntimeError (e.g. FixtureError/FixtureTokenError, or any
    # non-boundary raise) must NOT be swept into BOUNDARY_FAULT just because
    # BoundaryFault also subclasses RuntimeError — classification is a type
    # check on BoundaryFault specifically, not "any RuntimeError".
    assert classify(RuntimeError("some other failure")) == ASSERTION_FAILURE


def test_classify_assertion_error_is_assertion_failure():
    assert classify(AssertionError("expected X, got Y")) == ASSERTION_FAILURE


def test_classify_boundary_fault_raised_from_another_exception():
    # `raise BoundaryFault(...) from exc` (scn/session.py's actual pattern at
    # its four retry-exhaustion sites) must still classify as BOUNDARY_FAULT
    # -- classify() reads the exception's own type, not what it was chained
    # from.
    try:
        try:
            raise TimeoutError("socket timeout")
        except TimeoutError as exc:
            raise BoundaryFault("timed out after 5 attempts", attempts=5) from exc
    except BoundaryFault as bf:
        assert classify(bf) == BOUNDARY_FAULT
        assert isinstance(bf.__cause__, TimeoutError)


def test_boundary_fault_carries_attempts():
    bf = BoundaryFault("non-JSON response", attempts=5)
    assert bf.attempts == 5


def test_boundary_fault_attempts_defaults_to_none():
    bf = BoundaryFault("network error")
    assert bf.attempts is None


def test_boundary_fault_message_preserved():
    bf = BoundaryFault("HTTP 404 from GAS WebApp", attempts=5)
    assert str(bf) == "HTTP 404 from GAS WebApp"


def test_boundary_fault_is_a_runtime_error():
    # Existing callers that catch RuntimeError broadly (e.g. FixtureError/
    # FixtureTokenError siblings, or generic `except Exception`) must still
    # catch a BoundaryFault -- it is a narrowing, not a divergent hierarchy.
    with pytest.raises(RuntimeError):
        raise BoundaryFault("x")
