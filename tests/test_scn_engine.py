"""
Unit tests for scn/engine.py and scn/assertions.py (GTaskSheet-5vwu.5).

Pure unit — no network, no GAS, no local.settings.json required.
Covers every AC from the bead plus supporting invariants from §4:
  1. Queued expectation rides STEPs until an observer drains it
  2. at=INTEGRITY not drained early by a STEP
  3. Multi-surface expectation drains per-surface (partial drain §4.7)
  4. close() with non-empty queue fails
"""
import contextlib
import copy
import re
import pytest

from scn.ai import ai
from scn.engine import (
    AUTO,
    INTEGRITY_TARGET,
    CheckpointEngine,
    CheckpointKind,
    DrainInvariantError,
    Expectation,
    Severity,
    Surface,
)
from scn.assertions import check_absent, check_present_consistent


# ---------------------------------------------------------------------------
# Helpers — build Expectations and mock readers
# ---------------------------------------------------------------------------

_SEQ = 0


def _seq():
    global _SEQ
    _SEQ += 1
    return _SEQ


def _exp(
    surfaces,
    *,
    kind="PRESENT_CONSISTENT",
    target=AUTO,
    severity=Severity.FAIL,
    needs_consistency=False,
    tag="[uc TEST]",
    action="Do the thing",
    action_id=None,
    assignee=None,
    status=None,
    entry_point="",
):
    s = frozenset(surfaces)
    expected = {"action": action}
    if action_id:
        expected["action_id"] = action_id
    if assignee:
        expected["assignee"] = assignee
    if status:
        expected["status"] = status
    return Expectation(
        seq=_seq(),
        expected=expected,
        surfaces=s,
        remaining=set(s),
        target=target,
        kind=kind,
        within=None,
        severity=severity,
        needs_consistency=needs_consistency,
        tag=tag,
        entry_point=entry_point,
    )


def _matching_ai(action="Do the thing", action_id="AI-1", status="Open", assignee=None):
    return ai(
        action=action,
        action_id=action_id,
        status=status,
        assignee=assignee,
        assignee_source="chip" if assignee else None,
    )


def _reader_pass(surface, action="Do the thing", action_id="AI-1", status="Open"):
    """Returns a reader that yields one matching ai for any surface."""
    return lambda s: [_matching_ai(action=action, action_id=action_id, status=status)]


def _reader_fail(surface):
    """Returns a reader that yields an empty list (nothing matches → present check fails)."""
    return lambda s: []


def _reader_present(action="Do the thing", action_id="AI-1", status="Open"):
    return lambda s: [_matching_ai(action=action, action_id=action_id, status=status)]


def _reader_absent():
    return lambda s: []


# ---------------------------------------------------------------------------
# TestEnqueueAndSnapshot — seq assignment + snapshot immutability (§4.2)
# ---------------------------------------------------------------------------

class TestEnqueueAndSnapshot:
    def test_seq_assigned_monotonically(self):
        engine = CheckpointEngine()
        e1 = _exp({Surface.DOC})
        e2 = _exp({Surface.SHEET})
        engine.enqueue(e1)
        engine.enqueue(e2)
        assert e1.seq < e2.seq

    def test_queue_length_after_enqueue(self):
        engine = CheckpointEngine()
        engine.enqueue(_exp({Surface.DOC}))
        engine.enqueue(_exp({Surface.SHEET}))
        assert len(engine.queue) == 2

    def test_snapshot_immutability(self):
        """Mutating the original ai after enqueue must not change the snapshot (§4.2)."""
        engine = CheckpointEngine()
        orig_ai = ai("Do the thing")
        snapshot = {"action": orig_ai.action}
        e = _exp({Surface.DOC}, action=orig_ai.action)
        engine.enqueue(e)
        # mutate: simulate the author pinning more fields post-enqueue
        orig_ai.action_id = "AI-7"
        orig_ai.status = "Open"
        # the snapshot in Expectation must be unchanged
        assert e.expected.get("action_id") is None
        assert e.expected.get("status") is None
        assert e.expected["action"] == "Do the thing"


# ---------------------------------------------------------------------------
# TestAutoTargeting — AC 1: rides STEPs until an observer can drain it
# ---------------------------------------------------------------------------

class TestAutoTargeting:
    def test_auto_drained_at_first_observable_step(self):
        engine = CheckpointEngine()
        e = _exp({Surface.DOC}, action="Do the thing", action_id="AI-1", status="Open")
        engine.enqueue(e)
        warnings, _ = engine.drain(
            CheckpointKind.STEP,
            on=frozenset({Surface.DOC}),
            read=_reader_present(action_id="AI-1"),
        )
        assert len(engine.queue) == 0
        assert warnings == []

    def test_auto_rides_step_when_surface_not_in_obs(self):
        """AC 1: expectation for DOC rides a SHEET-only STEP, stays queued."""
        engine = CheckpointEngine()
        e = _exp({Surface.DOC}, action="Do the thing", action_id="AI-1", status="Open")
        engine.enqueue(e)
        engine.drain(
            CheckpointKind.STEP,
            on=frozenset({Surface.SHEET}),
            read=_reader_present(action_id="AI-1"),
        )
        assert len(engine.queue) == 1  # still queued

    def test_auto_drained_when_surface_eventually_observed(self):
        engine = CheckpointEngine()
        e = _exp({Surface.DOC}, action="Do the thing", action_id="AI-1", status="Open")
        engine.enqueue(e)
        # First STEP can't see DOC
        engine.drain(CheckpointKind.STEP, on=frozenset({Surface.SHEET}), read=_reader_present(action_id="AI-1"))
        assert len(engine.queue) == 1
        # Second STEP can see DOC
        engine.drain(CheckpointKind.STEP, on=frozenset({Surface.DOC}), read=_reader_present(action_id="AI-1"))
        assert len(engine.queue) == 0

    def test_auto_obs_computed_from_remaining_when_on_not_supplied(self):
        """STEP without on= drains only surfaces in pending AUTO remainders (§4.4)."""
        engine = CheckpointEngine()
        e = _exp({Surface.TRACKER}, action="Do the thing", action_id="AI-1", status="Open")
        engine.enqueue(e)
        engine.drain(
            CheckpointKind.STEP,
            on=None,
            read=_reader_present(action_id="AI-1"),
        )
        assert len(engine.queue) == 0


# ---------------------------------------------------------------------------
# TestIntegrityTargeting — AC 2: at=INTEGRITY not drained early
# ---------------------------------------------------------------------------

class TestIntegrityTargeting:
    def test_integrity_target_not_drained_by_step(self):
        """AC 2: at=INTEGRITY expectation stays queued through a STEP even when observable."""
        engine = CheckpointEngine()
        e = _exp(
            {Surface.SHEET},
            target=INTEGRITY_TARGET,
            action="Do the thing",
            action_id="AI-1",
            status="Open",
        )
        engine.enqueue(e)
        engine.drain(
            CheckpointKind.STEP,
            on=frozenset({Surface.SHEET}),
            read=_reader_present(action_id="AI-1"),
        )
        assert len(engine.queue) == 1  # must NOT have been drained

    def test_integrity_target_drained_at_integrity(self):
        engine = CheckpointEngine()
        e = _exp(
            {Surface.SHEET},
            target=INTEGRITY_TARGET,
            action="Do the thing",
            action_id="AI-1",
            status="Open",
        )
        engine.enqueue(e)
        engine.drain(
            CheckpointKind.INTEGRITY,
            on=None,
            read=_reader_present(action_id="AI-1"),
        )
        assert len(engine.queue) == 0

    def test_auto_and_integrity_coexist(self):
        """AUTO drains at STEP; INTEGRITY-targeted one waits."""
        engine = CheckpointEngine()
        e_auto = _exp({Surface.DOC}, target=AUTO, action="Auto thing", action_id="AI-1", status="Open")
        e_int = _exp({Surface.DOC}, target=INTEGRITY_TARGET, action="Deferred thing", action_id="AI-2", status="Open")
        engine.enqueue(e_auto)
        engine.enqueue(e_int)
        engine.drain(
            CheckpointKind.STEP,
            on=frozenset({Surface.DOC}),
            read=lambda s: [
                _matching_ai(action="Auto thing", action_id="AI-1"),
                _matching_ai(action="Deferred thing", action_id="AI-2"),
            ],
        )
        # AUTO drained; INTEGRITY-target stays
        assert e_auto not in engine.queue
        assert e_int in engine.queue


# ---------------------------------------------------------------------------
# TestLabelTargeting — at="<label>" only drains at the named checkpoint
# ---------------------------------------------------------------------------

class TestLabelTargeting:
    def test_label_target_not_drained_at_unlabeled_step(self):
        engine = CheckpointEngine()
        e = _exp({Surface.SHEET}, target="after-sync", action="Do the thing", action_id="AI-1", status="Open")
        engine.enqueue(e)
        engine.drain(
            CheckpointKind.STEP,
            label=None,
            on=frozenset({Surface.SHEET}),
            read=_reader_present(action_id="AI-1"),
        )
        assert len(engine.queue) == 1

    def test_label_target_not_drained_at_wrong_label(self):
        engine = CheckpointEngine()
        e = _exp({Surface.SHEET}, target="after-sync", action="Do the thing", action_id="AI-1", status="Open")
        engine.enqueue(e)
        engine.drain(
            CheckpointKind.STEP,
            label="different-label",
            on=frozenset({Surface.SHEET}),
            read=_reader_present(action_id="AI-1"),
        )
        assert len(engine.queue) == 1

    def test_label_target_drained_at_matching_label(self):
        engine = CheckpointEngine()
        e = _exp({Surface.SHEET}, target="after-sync", action="Do the thing", action_id="AI-1", status="Open")
        engine.enqueue(e)
        engine.drain(
            CheckpointKind.STEP,
            label="after-sync",
            on=frozenset({Surface.SHEET}),
            read=_reader_present(action_id="AI-1"),
        )
        assert len(engine.queue) == 0


# ---------------------------------------------------------------------------
# TestPerSurfacePartialDrain — AC 3: §4.7 worked trace
# ---------------------------------------------------------------------------

class TestPerSurfacePartialDrain:
    def test_partial_drain_step_drains_sheet_integrity_drains_doc(self):
        """§4.7: one Expectation with surfaces={DOC,SHEET}, drained across two checkpoints."""
        engine = CheckpointEngine()
        e = _exp(
            {Surface.DOC, Surface.SHEET},
            action="Do the thing",
            action_id="AI-1",
            status="Open",
        )
        engine.enqueue(e)

        # STEP with on=SHEET → drains SHEET portion only
        engine.drain(
            CheckpointKind.STEP,
            on=frozenset({Surface.SHEET}),
            read=_reader_present(action_id="AI-1"),
        )
        assert e in engine.queue          # still queued (DOC not yet drained)
        assert Surface.SHEET not in e.remaining
        assert Surface.DOC in e.remaining

        # INTEGRITY → drains DOC; Expectation retired
        engine.drain(
            CheckpointKind.INTEGRITY,
            on=None,
            read=_reader_present(action_id="AI-1"),
        )
        assert e not in engine.queue
        assert len(engine.queue) == 0

    def test_partial_drain_does_not_re_drain_already_drained_surface(self):
        """Surface dropped from remaining once; second STEP with same surface is a no-op for that E."""
        engine = CheckpointEngine()
        e = _exp(
            {Surface.DOC, Surface.SHEET},
            action="Do the thing",
            action_id="AI-1",
            status="Open",
        )
        engine.enqueue(e)
        call_count = {"n": 0}

        def counting_reader(s):
            call_count["n"] += 1
            return [_matching_ai(action_id="AI-1")]

        engine.drain(CheckpointKind.STEP, on=frozenset({Surface.SHEET}), read=counting_reader)
        first_count = call_count["n"]
        engine.drain(CheckpointKind.STEP, on=frozenset({Surface.SHEET}), read=counting_reader)
        # e has no SHEET remaining → reader should not be called again for this e on SHEET
        # (SHEET was already dropped from remaining; second STEP has no drainable SHEET for this e)
        assert call_count["n"] == first_count


# ---------------------------------------------------------------------------
# TestDrainInvariantClose — AC 4
# ---------------------------------------------------------------------------

class TestDrainInvariantClose:
    def test_close_empty_queue_is_silent(self):
        engine = CheckpointEngine()
        engine.close()  # must not raise

    def test_close_non_empty_queue_raises(self):
        engine = CheckpointEngine()
        e = _exp({Surface.DOC}, tag="[uc AC-1]")
        engine.enqueue(e)
        with pytest.raises(DrainInvariantError) as exc:
            engine.close()
        info = str(exc.value)
        assert "[uc AC-1]" in info

    def test_close_reports_all_dangling(self):
        engine = CheckpointEngine()
        engine.enqueue(_exp({Surface.DOC}, tag="[uc AC-1]"))
        engine.enqueue(_exp({Surface.SHEET}, tag="[uc AC-2]"))
        with pytest.raises(DrainInvariantError) as exc:
            engine.close()
        info = str(exc.value)
        assert "[uc AC-1]" in info
        assert "[uc AC-2]" in info


# ---------------------------------------------------------------------------
# TestSeverityWarn — WARN records warning but drops surface (§4.5 step 2)
# ---------------------------------------------------------------------------

class TestSeverityWarn:
    def test_warn_drops_surface_and_does_not_dangle(self):
        """WARN miss: surface dropped, no exception; close() succeeds."""
        engine = CheckpointEngine()
        e = _exp(
            {Surface.SHEET},
            severity=Severity.WARN,
            action="Do the thing",
            action_id="AI-99",  # won't match reader
            status="Open",
        )
        engine.enqueue(e)
        warnings, _ = engine.drain(
            CheckpointKind.STEP,
            on=frozenset({Surface.SHEET}),
            read=_reader_absent(),  # returns nothing → present check fails
        )
        assert len(warnings) >= 1
        assert len(engine.queue) == 0  # surface dropped even on WARN
        engine.close()  # must not raise

    def test_fail_severity_raises_on_mismatch(self):
        """FAIL severity + miss → exception raised."""
        engine = CheckpointEngine()
        e = _exp(
            {Surface.SHEET},
            severity=Severity.FAIL,
            action="Do the thing",
            action_id="AI-99",
            status="Open",
        )
        engine.enqueue(e)
        with pytest.raises(AssertionError):
            engine.drain(
                CheckpointKind.STEP,
                on=frozenset({Surface.SHEET}),
                read=_reader_absent(),
            )

    def test_on_ui_fail_not_called_for_non_ui_surface(self):
        """R6 (GTaskSheet-16kh): on_ui_fail only fires for Surface.UI FAIL misses."""
        engine = CheckpointEngine()
        e = _exp(
            {Surface.SHEET},
            severity=Severity.FAIL,
            action="Do the thing",
            action_id="AI-99",
            status="Open",
        )
        engine.enqueue(e)
        calls = []
        with pytest.raises(AssertionError):
            engine.drain(
                CheckpointKind.STEP,
                on=frozenset({Surface.SHEET}),
                read=_reader_absent(),
                on_ui_fail=lambda *a: calls.append(a),
            )
        assert calls == []


# ---------------------------------------------------------------------------
# TestDrainedRecords — T24: drain() returns (tag, surface, severity) tuples
# ---------------------------------------------------------------------------

class TestDrainedRecords:
    def test_pass_surface_emits_pass_record(self):
        engine = CheckpointEngine()
        e = _exp({Surface.DOC}, action="Do the thing", action_id="AI-1", status="Open")
        e.tag = "[journey sync-create]"
        engine.enqueue(e)
        warnings, records = engine.drain(
            CheckpointKind.STEP,
            on=frozenset({Surface.DOC}),
            read=_reader_present(action_id="AI-1"),
        )
        assert warnings == []
        assert len(records) == 1
        assert records[0] == ("[journey sync-create]", "DOC", "PASS", "")

    def test_warn_surface_emits_warn_record(self):
        engine = CheckpointEngine()
        e = _exp(
            {Surface.SHEET},
            severity=Severity.WARN,
            action="Do the thing",
            action_id="AI-99",
            status="Open",
        )
        e.tag = "[journey warn-ac]"
        engine.enqueue(e)
        warnings, records = engine.drain(
            CheckpointKind.STEP,
            on=frozenset({Surface.SHEET}),
            read=_reader_absent(),
        )
        assert len(warnings) == 1
        assert len(records) == 1
        assert records[0] == ("[journey warn-ac]", "SHEET", "WARN", "")

    def test_multiple_surfaces_emit_one_record_each(self):
        engine = CheckpointEngine()
        e = _exp(
            {Surface.DOC, Surface.SHEET},
            action="Do the thing",
            action_id="AI-1",
            status="Open",
        )
        e.tag = "[journey multi]"
        engine.enqueue(e)
        _, records = engine.drain(
            CheckpointKind.STEP,
            on=frozenset({Surface.DOC, Surface.SHEET}),
            read=_reader_present(action_id="AI-1"),
        )
        assert len(records) == 2
        surfaces = {r[1] for r in records}
        assert surfaces == {"DOC", "SHEET"}
        assert all(r[2] == "PASS" for r in records)

    def test_no_match_emits_no_record(self):
        engine = CheckpointEngine()
        e = _exp({Surface.DOC}, action="Do the thing", action_id="AI-1", status="Open")
        engine.enqueue(e)
        _, records = engine.drain(
            CheckpointKind.STEP,
            on=frozenset({Surface.SHEET}),  # DOC not in obs — not evaluated
            read=_reader_present(action_id="AI-1"),
        )
        assert records == []

    def test_step_cm_invoked_once_per_expectation_surface(self):
        """R6 (GTaskSheet-16kh): step_cm(name) wraps each per-surface check."""
        engine = CheckpointEngine()
        e = _exp(
            {Surface.DOC, Surface.SHEET},
            action="Do the thing",
            action_id="AI-1",
            status="Open",
        )
        e.tag = "[journey sync-create AC1]"
        engine.enqueue(e)

        calls = []

        @contextlib.contextmanager
        def step_cm(name):
            calls.append(name)
            yield

        _, records = engine.drain(
            CheckpointKind.STEP,
            on=frozenset({Surface.DOC, Surface.SHEET}),
            read=_reader_present(action_id="AI-1"),
            step_cm=step_cm,
        )
        assert len(records) == 2
        assert sorted(calls) == [
            "[journey sync-create AC1] DOC",
            "[journey sync-create AC1] SHEET",
        ]

    def test_entry_point_propagates_into_record(self):
        # T1/T17: an expectation tagging an entry point carries it into the drained
        # record so the session can emit ep.<entry_point>.<surface> (GTaskSheet-me6w.2).
        engine = CheckpointEngine()
        e = _exp(
            {Surface.SHEET},
            action="Do the thing",
            action_id="AI-1",
            status="Open",
            entry_point="syncDocument",
        )
        e.tag = "[teamscope direct-match]"
        engine.enqueue(e)
        _, records = engine.drain(
            CheckpointKind.STEP,
            on=frozenset({Surface.SHEET}),
            read=_reader_present(action_id="AI-1"),
        )
        assert records == [("[teamscope direct-match]", "SHEET", "PASS", "syncDocument")]


# ---------------------------------------------------------------------------
# TestIntegrityConsistency — needs_consistency=True evaluated at INTEGRITY only
# ---------------------------------------------------------------------------

class TestIntegrityConsistency:
    def test_consistency_not_called_at_step(self):
        engine = CheckpointEngine()
        e = _exp(
            {Surface.DOC},
            needs_consistency=True,
            action="Do the thing",
            action_id="AI-1",
            status="Open",
        )
        engine.enqueue(e)
        called = {"n": 0}

        def cons():
            called["n"] += 1
            return {}

        engine.drain(
            CheckpointKind.STEP,
            on=frozenset({Surface.DOC}),
            read=_reader_present(action_id="AI-1"),
            read_consistency=cons,
        )
        # DOC drained at STEP but consistency NOT called (STEP can't observe CONSISTENCY)
        assert called["n"] == 0

    def test_consistency_called_at_integrity(self):
        engine = CheckpointEngine()
        e = _exp(
            {Surface.DOC},
            needs_consistency=True,
            action="Do the thing",
            action_id="AI-1",
            status="Open",
        )
        engine.enqueue(e)
        called = {"n": 0}

        def cons():
            called["n"] += 1
            return {}  # empty = pass

        engine.drain(
            CheckpointKind.INTEGRITY,
            on=None,
            read=_reader_present(action_id="AI-1"),
            read_consistency=cons,
        )
        assert called["n"] == 1
        assert len(engine.queue) == 0

    def test_needs_consistency_expectation_not_retired_until_consistency_discharged(self):
        """An Expectation with needs_consistency stays queued until the INTEGRITY where consistency runs."""
        engine = CheckpointEngine()
        e = _exp(
            {Surface.DOC, Surface.SHEET},
            needs_consistency=True,
            action="Do the thing",
            action_id="AI-1",
            status="Open",
        )
        engine.enqueue(e)
        # STEP drains SHEET portion → DOC remains; consistency not yet discharged
        engine.drain(
            CheckpointKind.STEP,
            on=frozenset({Surface.SHEET}),
            read=_reader_present(action_id="AI-1"),
        )
        assert e in engine.queue  # consistency not discharged at STEP

        # INTEGRITY drains DOC + discharges consistency
        engine.drain(
            CheckpointKind.INTEGRITY,
            on=None,
            read=_reader_present(action_id="AI-1"),
            read_consistency=lambda: {},
        )
        assert e not in engine.queue


# ---------------------------------------------------------------------------
# TestTargetingEnforcement — §4.5 step 4
# ---------------------------------------------------------------------------

class TestTargetingEnforcement:
    def test_integrity_target_fail_raises_when_surface_not_satisfied(self):
        """Explicit at=INTEGRITY target: surface must pass at INTEGRITY or it's a hard failure."""
        engine = CheckpointEngine()
        e = _exp(
            {Surface.SHEET},
            target=INTEGRITY_TARGET,
            action="Do the thing",
            action_id="AI-99",  # reader returns nothing → check fails
            status="Open",
        )
        engine.enqueue(e)
        with pytest.raises(AssertionError):
            engine.drain(
                CheckpointKind.INTEGRITY,
                on=None,
                read=_reader_absent(),
            )

    def test_label_target_fail_raises_at_matching_checkpoint(self):
        """Explicit at=label: surface must pass when the named checkpoint runs."""
        engine = CheckpointEngine()
        e = _exp(
            {Surface.SHEET},
            target="post-sync",
            action="Do the thing",
            action_id="AI-99",
            status="Open",
        )
        engine.enqueue(e)
        with pytest.raises(AssertionError):
            engine.drain(
                CheckpointKind.STEP,
                label="post-sync",
                on=frozenset({Surface.SHEET}),
                read=_reader_absent(),
            )


# ---------------------------------------------------------------------------
# TestExpectAbsent — kind="ABSENT" absence checks
# ---------------------------------------------------------------------------

class TestExpectAbsent:
    def test_absent_passes_when_no_match(self):
        engine = CheckpointEngine()
        e = _exp(
            {Surface.SHEET},
            kind="ABSENT",
            action="Gone thing",
            action_id="AI-3",
        )
        engine.enqueue(e)
        engine.drain(
            CheckpointKind.STEP,
            on=frozenset({Surface.SHEET}),
            read=_reader_absent(),  # nothing in sheet → absent expectation passes
        )
        assert len(engine.queue) == 0

    def test_absent_fails_when_action_still_present(self):
        engine = CheckpointEngine()
        e = _exp(
            {Surface.SHEET},
            kind="ABSENT",
            action="Gone thing",
            action_id="AI-3",
        )
        engine.enqueue(e)
        with pytest.raises(AssertionError):
            engine.drain(
                CheckpointKind.STEP,
                on=frozenset({Surface.SHEET}),
                read=lambda s: [_matching_ai(action="Gone thing", action_id="AI-3")],
            )


# ---------------------------------------------------------------------------
# TestAssertionsModule — standalone assertion helpers (scn/assertions.py)
# ---------------------------------------------------------------------------

class TestCheckPresentConsistent:
    def _ai(self, action="Do the thing", action_id="AI-1", status="Open", assignee=None):
        return ai(action=action, action_id=action_id, status=status, assignee=assignee,
                  assignee_source="chip" if assignee else None)

    def test_pass_matching_action_id(self):
        expected = {"action": "Do the thing", "action_id": "AI-1", "status": "Open"}
        result = check_present_consistent(expected, [self._ai()], Surface.SHEET, "[uc T]")
        assert result is None

    def test_fail_no_match_found(self):
        expected = {"action": "Do the thing", "action_id": "AI-99"}
        result = check_present_consistent(expected, [self._ai()], Surface.SHEET, "[uc T]")
        assert result is not None
        assert "AI-99" in result or "not found" in result.lower()

    def test_fail_status_mismatch(self):
        expected = {"action": "Do the thing", "action_id": "AI-1", "status": "Closed"}
        result = check_present_consistent(expected, [self._ai(status="Open")], Surface.SHEET, "[uc T]")
        assert result is not None

    def test_pass_no_action_id_any_valid_ai_n(self):
        """If action_id not in expected, any valid AI-N in actual passes."""
        expected = {"action": "Do the thing"}
        result = check_present_consistent(expected, [self._ai(action_id="AI-7")], Surface.SHEET, "[uc T]")
        assert result is None

    def test_fail_no_action_id_no_match_by_action_text(self):
        expected = {"action": "Different thing"}
        result = check_present_consistent(expected, [self._ai()], Surface.SHEET, "[uc T]")
        assert result is not None

    def test_doc_surface_all_occurrences_must_be_identical(self):
        """DOC: multiple occurrences with same action_id must be identical (§16.5)."""
        expected = {"action": "Do the thing", "action_id": "AI-1", "status": "Open"}
        differing = [
            self._ai(action="Do the thing", action_id="AI-1", status="Open"),
            self._ai(action="Do the thing", action_id="AI-1", status="WRONG"),
        ]
        result = check_present_consistent(expected, differing, Surface.DOC, "[uc T]")
        assert result is not None

    def test_doc_surface_identical_occurrences_pass(self):
        expected = {"action": "Do the thing", "action_id": "AI-1", "status": "Open"}
        same = [self._ai(), self._ai()]
        result = check_present_consistent(expected, same, Surface.DOC, "[uc T]")
        assert result is None

    def test_assignee_name_derived_via_expected_name(self):
        """Name is checked against expected_name(email), not raw value (§16.6)."""
        expected = {
            "action": "Do the thing",
            "action_id": "AI-1",
            "status": "Open",
            "assignee": "sdonaldson@northlakeuu.org",
        }
        actual_ai = self._ai(assignee="sdonaldson@northlakeuu.org")
        actual_ai.assignee_name = "Stuart Donaldson"  # simulated read-back field
        result = check_present_consistent(expected, [actual_ai], Surface.SHEET, "[uc T]")
        # Should pass: sdonaldson@northlakeuu.org → "Stuart Donaldson" via TEST_CONTACTS
        assert result is None


class TestCheckAbsent:
    def _ai(self, action_id="AI-1"):
        return ai(action="Gone thing", action_id=action_id, status="Open")

    def test_pass_when_empty_list(self):
        expected = {"action": "Gone thing", "action_id": "AI-1"}
        result = check_absent(expected, [], Surface.SHEET, "[uc T]")
        assert result is None

    def test_fail_when_matching_action_found(self):
        expected = {"action": "Gone thing", "action_id": "AI-1"}
        result = check_absent(expected, [self._ai()], Surface.SHEET, "[uc T]")
        assert result is not None

    def test_pass_when_non_matching_action_in_list(self):
        expected = {"action": "Gone thing", "action_id": "AI-1"}
        other = ai(action="Different thing", action_id="AI-2", status="Open")
        result = check_absent(expected, [other], Surface.SHEET, "[uc T]")
        assert result is None


# ---------------------------------------------------------------------------
# TestUIDrainableAndWithin — R1-impl: UI as first-class drained surface (§3)
# ---------------------------------------------------------------------------

def _ui_ai(*, action_id="AI-1", status="Open"):
    """Minimal ai as returned by UiDriver.read_current(): action='', id+status set."""
    return ai(action="", action_id=action_id, status=status)


def _ui_exp(
    *,
    action_id="AI-1",
    status="Open",
    within=None,
    severity=Severity.FAIL,
    tag="[uc TEST]",
):
    """Build an Expectation for Surface.UI with an action_id+status snapshot."""
    surfaces = frozenset({Surface.UI})
    expected = {"action": "the action text", "action_id": action_id, "status": status}
    return Expectation(
        seq=_seq(),
        expected=expected,
        surfaces=surfaces,
        remaining=set(surfaces),
        target=AUTO,
        kind="PRESENT_CONSISTENT",
        within=within,
        severity=severity,
        needs_consistency=False,
        tag=tag,
    )


class TestUIDrainableAndWithin:
    """verify(on=UI) drains at STEP; within= polls live; INTEGRITY excludes UI (R1-impl §3)."""

    def test_ui_drains_at_step_with_ui_in_obs(self):
        """verify(on=UI) drains at STEP when obs includes UI and read returns matching ai."""
        engine = CheckpointEngine()
        engine.enqueue(_ui_exp(action_id="AI-1", status="Open"))
        warns, _ = engine.drain(
            CheckpointKind.STEP,
            on=frozenset({Surface.UI}),
            read=lambda s: [_ui_ai(action_id="AI-1", status="Open")],
        )
        assert warns == []
        assert engine.queue == []

    def test_ui_does_not_drain_at_step_without_ui_obs(self):
        """verify(on=UI) stays queued at a SHEET-only STEP."""
        engine = CheckpointEngine()
        engine.enqueue(_ui_exp(action_id="AI-1", status="Open"))
        engine.drain(
            CheckpointKind.STEP,
            on=frozenset({Surface.SHEET}),
            read=lambda s: [_ui_ai(action_id="AI-1", status="Open")],
        )
        assert len(engine.queue) == 1

    def test_integrity_excludes_ui_expectation(self):
        """INTEGRITY does NOT drain a queued UI expectation → rides to close() → DrainInvariantError."""
        engine = CheckpointEngine()
        engine.enqueue(_ui_exp(action_id="AI-1", status="Open"))
        engine.drain(
            CheckpointKind.INTEGRITY,
            read=lambda s: [_ui_ai(action_id="AI-1", status="Open")],
        )
        assert len(engine.queue) == 1  # still queued
        with pytest.raises(DrainInvariantError):
            engine.close()

    def test_within_retries_until_status_matches(self):
        """within poll: read returns wrong status first, correct on 2nd call → drains; read called >1."""
        from unittest.mock import MagicMock, patch

        engine = CheckpointEngine()
        engine.enqueue(_ui_exp(action_id="AI-1", status="In Progress", within="1s"))

        reads = []

        def read(surface):
            reads.append(surface)
            if len(reads) == 1:
                return [_ui_ai(action_id="AI-1", status="Open")]  # wrong status
            return [_ui_ai(action_id="AI-1", status="In Progress")]  # correct

        with patch("scn.engine.time") as m:
            m.monotonic.side_effect = [0.0, 0.1]  # deadline=1.0s; 2nd monotonic check at 0.1s < 1.0
            m.sleep = MagicMock()
            warns, _ = engine.drain(
                CheckpointKind.STEP,
                on=frozenset({Surface.UI}),
                read=read,
            )

        assert warns == []
        assert len(reads) == 2  # read called twice (cache bypassed)
        assert engine.queue == []

    def test_within_fails_on_timeout(self):
        """within poll: read never matches → AssertionError (FAIL severity) at timeout."""
        from unittest.mock import MagicMock, patch

        engine = CheckpointEngine()
        engine.enqueue(_ui_exp(action_id="AI-1", status="Done", within="200ms"))

        with patch("scn.engine.time") as m:
            m.monotonic.side_effect = [0.0, 1.0]  # deadline=0.2s; check at 1.0s > deadline
            m.sleep = MagicMock()
            with pytest.raises(AssertionError):
                engine.drain(
                    CheckpointKind.STEP,
                    on=frozenset({Surface.UI}),
                    read=lambda s: [_ui_ai(action_id="AI-1", status="Open")],
                )

    def test_on_ui_fail_called_before_raise_for_ui_fail(self):
        """R6 (GTaskSheet-16kh): on_ui_fail(surface, tag, error) fires, then raises."""
        engine = CheckpointEngine()
        e = _ui_exp(action_id="AI-1", status="Done", tag="[journey ui-fail AC1]")
        engine.enqueue(e)
        calls = []

        with pytest.raises(AssertionError):
            engine.drain(
                CheckpointKind.STEP,
                on=frozenset({Surface.UI}),
                read=lambda s: [_ui_ai(action_id="AI-1", status="Open")],
                on_ui_fail=lambda surface, tag, error: calls.append((surface, tag, error)),
            )

        assert len(calls) == 1
        surface, tag, error = calls[0]
        assert surface == Surface.UI
        assert tag == "[journey ui-fail AC1]"
        assert isinstance(error, str) and error

    def test_on_ui_fail_not_called_for_warn(self):
        """R6 (GTaskSheet-16kh): WARN-severity UI miss does not trigger a screenshot."""
        engine = CheckpointEngine()
        e = _ui_exp(action_id="AI-1", status="Done", severity=Severity.WARN, tag="[journey ui-warn AC1]")
        engine.enqueue(e)
        calls = []

        warns, _ = engine.drain(
            CheckpointKind.STEP,
            on=frozenset({Surface.UI}),
            read=lambda s: [_ui_ai(action_id="AI-1", status="Open")],
            on_ui_fail=lambda *a: calls.append(a),
        )

        assert len(warns) == 1
        assert calls == []

    def test_within_warn_drops_surface_and_records_warning(self):
        """within poll: WARN severity records warning + drops surface at timeout."""
        from unittest.mock import MagicMock, patch

        engine = CheckpointEngine()
        engine.enqueue(_ui_exp(action_id="AI-1", status="Done", within="200ms", severity=Severity.WARN))

        with patch("scn.engine.time") as m:
            m.monotonic.side_effect = [0.0, 1.0]
            m.sleep = MagicMock()
            warns, _ = engine.drain(
                CheckpointKind.STEP,
                on=frozenset({Surface.UI}),
                read=lambda s: [_ui_ai(action_id="AI-1", status="Open")],
            )

        assert len(warns) == 1
        assert "WARN" in warns[0]
        assert engine.queue == []  # surface dropped; no dangle


# ---------------------------------------------------------------------------
# TestCheckPresentConsistentUI — UI surface assertion carve-out (R1-impl §2)
# ---------------------------------------------------------------------------

class TestCheckPresentConsistentUI:
    """UI surface: only action_id + status enforced; text/assignee/name skipped."""

    def _actual(self, action_id="AI-1", status="Open", assignee=None):
        return ai(action="", action_id=action_id, status=status, assignee=assignee)

    def test_pass_action_id_and_status_match(self):
        expected = {"action": "does not matter for UI check", "action_id": "AI-1", "status": "In Progress"}
        result = check_present_consistent(expected, [self._actual(status="In Progress")], Surface.UI, "[t]")
        assert result is None

    def test_fail_status_mismatch(self):
        expected = {"action": "x", "action_id": "AI-1", "status": "In Progress"}
        result = check_present_consistent(expected, [self._actual(status="Open")], Surface.UI, "[t]")
        assert result is not None
        assert "status" in result.lower()

    def test_fail_action_id_not_found(self):
        """Action not in actuals → 'not found' error."""
        expected = {"action": "x", "action_id": "AI-99", "status": "Open"}
        result = check_present_consistent(expected, [self._actual(action_id="AI-1")], Surface.UI, "[t]")
        assert result is not None

    def test_pass_action_text_mismatch_ignored(self):
        """UI carve-out: action text mismatch is not enforced."""
        expected = {"action": "completely different text", "action_id": "AI-1", "status": "Open"}
        result = check_present_consistent(expected, [self._actual(status="Open")], Surface.UI, "[t]")
        assert result is None

    def test_pass_assignee_mismatch_ignored(self):
        """UI carve-out: assignee is not enforced."""
        expected = {"action": "x", "action_id": "AI-1", "status": "Open", "assignee": "someone@example.com"}
        result = check_present_consistent(expected, [self._actual(assignee=None)], Surface.UI, "[t]")
        assert result is None
