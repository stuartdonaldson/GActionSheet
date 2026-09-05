"""scn/outcomes.py — first-class execution outcome classification (H6, I12).

Design: docs/atdd/test-framework-upgrade-plan.md §2b (R3/R4), stage
`boundary-faults` (gts-u6ew.6/.7/.8).

Before this module existed, `scn/session.py`'s `_http_post` raised a bare
`RuntimeError` at every retry-exhaustion site, so a Google/GAS platform fault
(a 404 from the /exec routing quirk, a network error, a socket timeout, an
echo page that never resolved to JSON) was indistinguishable from a real
assertion/application failure by the time it reached the pytest report — the
offline diagnostics tool had to guess from the exception *message* instead,
at ~52% precision against the patterns it assumes.

`BoundaryFault` makes that distinction a type check instead: a fault that
survives the bounded retry policy in `_http_post` is raised as a
`BoundaryFault`, not a bare `RuntimeError`. `classify()` is the one owning
helper (I12) that reads that type — no caller should re-derive this decision
with its own `isinstance`/`except` clause or by re-inspecting the message.
"""
from __future__ import annotations

PASS = "PASS"
ASSERTION_FAILURE = "ASSERTION_FAILURE"
BOUNDARY_FAULT = "BOUNDARY_FAULT"


class BoundaryFault(RuntimeError):
    """A platform/transport fault that survived the bounded retry policy (H7).

    Raised by `scn.session._http_post` at its four retry-exhaustion sites
    instead of a bare `RuntimeError`. Carries an optional `attempts` int —
    the number of attempts actually made for the call that raised this —
    set by the raising site, read by callers that want to record it (H7)
    rather than re-deriving it.

    Must not be converted into a pass or a silently-swallowed failure by any
    caller: a `BoundaryFault` that reaches the report is reported as a
    boundary fault (H6/H7), a distinct outcome class from an assertion
    failure.
    """

    def __init__(self, *args, attempts: int | None = None) -> None:
        super().__init__(*args)
        self.attempts = attempts


def classify(exc: BaseException | None) -> str:
    """Classify one test's outcome as PASS / ASSERTION_FAILURE / BOUNDARY_FAULT.

    The one owning helper (I12) — do not duplicate this decision with a
    per-test `except BoundaryFault` clause or by matching exception text.

    `exc=None` means the test raised nothing (PASS). `BoundaryFault` (even
    when re-raised via `raise ... from`, or wrapped by a context that
    preserves `__cause__`/`__context__` — `isinstance` sees through neither,
    deliberately: only a `BoundaryFault` instance itself, not a lookalike
    message, ever classifies as one) is BOUNDARY_FAULT. Everything else that
    failed is ASSERTION_FAILURE — a type check, not string matching.
    """
    if exc is None:
        return PASS
    if isinstance(exc, BoundaryFault):
        return BOUNDARY_FAULT
    return ASSERTION_FAILURE
