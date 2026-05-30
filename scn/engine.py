"""
engine.py — expectation queue + checkpoint drain (GTaskSheet-5vwu.5).

Spec: docs/proposed-atdd-lifecycle.md §16.1, §16.6
Design: docs/atdd/scenario-harness-design.md §4 (authoritative algorithm reference)

Public API consumed by scn/session.py (.7) thin enqueuers:
  - Surface, CheckpointKind, Severity, AUTO, INTEGRITY_TARGET (enums + sentinels)
  - Expectation (dataclass — built by session, stored here)
  - CheckpointEngine  (enqueue, drain, close, queue)
  - DrainInvariantError
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class Surface(Enum):
    DOC = "DOC"
    SHEET = "SHEET"
    TRACKER = "TRACKER"
    UI = "UI"


class CheckpointKind(Enum):
    STEP = "STEP"
    INTEGRITY = "INTEGRITY"


class Severity(Enum):
    FAIL = "FAIL"
    WARN = "WARN"


# Evaluation-target sentinels (§16.1)
AUTO = object()                          # drain at the earliest checkpoint that can observe it
INTEGRITY_TARGET = CheckpointKind.INTEGRITY  # skip STEPs; evaluate at the next INTEGRITY


@dataclass
class Expectation:
    """Per-expectation record stored in the engine queue (§4.1).

    `expected` is a deep-copy snapshot of ai fields taken at enqueue time (§4.2).
    `remaining` starts equal to `surfaces` and shrinks as surfaces drain.
    """
    seq: int
    expected: dict                    # snapshot of ai fields at enqueue (§4.2)
    surfaces: frozenset               # claim set — immutable; set at enqueue
    remaining: set                    # surfaces not yet drained; mutable
    target: object                    # AUTO | INTEGRITY_TARGET | "<label>"
    kind: str                         # "PRESENT_CONSISTENT" | "ABSENT"
    within: str | None
    severity: Severity
    needs_consistency: bool           # True for verify_all_expectations
    tag: str                          # [uc AC#] triage tag
    consistency_discharged: bool = field(default=False)


class DrainInvariantError(Exception):
    """Raised by close() when expectations remain in the queue (§4.6)."""

    def __init__(self, dangling: list[tuple]):
        self.dangling = dangling
        parts = [
            f"seq={seq} remaining={surfaces} tag={tag}"
            for seq, surfaces, tag in dangling
        ]
        super().__init__(f"Non-empty expectation queue at close(): {'; '.join(parts)}")


_ALL_AUTHOR_SURFACES = frozenset(Surface)


def _is_targetable(e: Expectation, kind: CheckpointKind, label: str | None) -> bool:
    """True iff expectation E may be evaluated at checkpoint (kind, label) — §4.5 step 1."""
    if e.target is AUTO:
        return True
    if e.target is INTEGRITY_TARGET:
        return kind == CheckpointKind.INTEGRITY
    if isinstance(e.target, str):
        return e.target == label
    return False


class CheckpointEngine:
    """Queue-based expectation evaluator implementing the §4 drain decision procedure.

    Session (.7) builds Expectation objects and calls enqueue(); checkpoint() calls drain();
    close() enforces the drain invariant — a non-empty queue at teardown is a test failure.
    """

    def __init__(self) -> None:
        self._queue: list[Expectation] = []

    def enqueue(self, exp: Expectation) -> None:
        self._queue.append(exp)

    @property
    def queue(self) -> list[Expectation]:
        return list(self._queue)

    def drain(
        self,
        kind: CheckpointKind,
        label: str | None = None,
        on: frozenset | None = None,
        read: Callable[[Surface], list] | None = None,
        read_consistency: Callable[[], dict] | None = None,
    ) -> list[str]:
        """Evaluate queued expectations at checkpoint (kind, label) and return warnings.

        Raises AssertionError on a FAIL-severity miss.
        Implements §4.5 steps 1–5 verbatim.

        Args:
            kind: STEP or INTEGRITY.
            label: optional checkpoint label (for at="<label>" targeting).
            on: explicit observable surface set for STEP; if None, computed from pending remainders.
            read: callable Surface → list[ai]; called at most once per surface per drain.
            read_consistency: called at INTEGRITY for needs_consistency expectations; None = skip.
        """
        # Delayed import avoids circular dependency (assertions.py imports Surface from here)
        from scn.assertions import check_present_consistent, check_absent

        if read is None:
            read = lambda s: []

        warnings: list[str] = []
        targetable = [e for e in self._queue if _is_targetable(e, kind, label)]

        # §4.4 OBS computation
        if kind == CheckpointKind.INTEGRITY:
            obs = _ALL_AUTHOR_SURFACES          # CONSISTENCY handled via needs_consistency flag
        elif on is not None:
            obs = on
        else:
            obs = (
                frozenset().union(*(e.remaining for e in targetable))
                if targetable
                else frozenset()
            )

        # Read each surface at most once across all expectations in this drain
        _cache: dict[Surface, list] = {}

        def get_actuals(surface: Surface) -> list:
            if surface not in _cache:
                _cache[surface] = read(surface)
            return _cache[surface]

        to_retire: list[Expectation] = []

        for e in targetable:
            # §4.5 step 2 — evaluate only surfaces observable here and still remaining
            observable_here = e.remaining & obs

            for surface in list(observable_here):
                actuals = get_actuals(surface)
                error = (
                    check_present_consistent(e.expected, actuals, surface, e.tag)
                    if e.kind == "PRESENT_CONSISTENT"
                    else check_absent(e.expected, actuals, surface, e.tag)
                )

                if error is None:
                    e.remaining.discard(surface)
                elif e.severity == Severity.WARN:
                    # WARN: record warning AND drop surface to prevent dangling (§4.5 step 2)
                    warnings.append(f"WARN [{e.tag}] surface={surface.value}: {error}")
                    e.remaining.discard(surface)
                else:
                    raise AssertionError(error)

            # §4.5 step 3 — INTEGRITY consistency obligation (CONSISTENCY pseudo-surface)
            if (
                kind == CheckpointKind.INTEGRITY
                and e.needs_consistency
                and not e.consistency_discharged
            ):
                if read_consistency is not None:
                    read_consistency()
                e.consistency_discharged = True

            # §4.5 step 4 — targeting enforcement: explicit target must fully satisfy OBS
            is_explicit_target = (e.target is INTEGRITY_TARGET and kind == CheckpointKind.INTEGRITY) or (
                isinstance(e.target, str) and e.target == label
            )
            if is_explicit_target:
                undrained = e.remaining & obs
                if undrained:
                    raise AssertionError(
                        f"[{e.tag}] explicit target checkpoint reached but surfaces not "
                        f"satisfied: {[s.value for s in undrained]}"
                    )

            # §4.5 step 5 — retire when remaining is empty and consistency obligation met
            consistency_ok = not e.needs_consistency or e.consistency_discharged
            if not e.remaining and consistency_ok:
                to_retire.append(e)

        for e in to_retire:
            self._queue.remove(e)

        return warnings

    def close(self) -> None:
        """Assert the queue is empty; raise DrainInvariantError if not (§4.6).

        A non-empty queue means an expectation was declared but never verified — a test failure.
        """
        if self._queue:
            dangling = [
                (e.seq, {s.value for s in e.remaining}, e.tag)
                for e in self._queue
            ]
            raise DrainInvariantError(dangling)
