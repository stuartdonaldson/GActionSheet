"""test_duration_instrumentation.py — gts-y1eg AC1-AC6.

Focused tests for the pure logic in tests/duration_instrumentation.py: baseline
rolling-window/median update, the automated flag decision, JSONL record shape,
and file round-trips. No live pytest subprocess here (specifiable oracle, T12);
the conftest.py hook wiring itself is proven separately by a manual smoke run
(see gts-y1eg notes) rather than a pytester-based test, per this issue's scope.
"""
import json

import pytest

from tests import duration_instrumentation as di

# gts-aqpk: fast/local tier -- this module makes no live GAS/Google round trip
# (verified offline with sockets blocked). See docs/OPERATIONS.md "Test tiers".
pytestmark = pytest.mark.no_live_session


# --- update_baseline (AC5: rolling window of last N samples, median) -------

def test_update_baseline_bootstraps_first_sample():
    baseline = di.update_baseline({}, "t1", 10.0)
    assert baseline["t1"]["samples"] == [10.0]
    assert baseline["t1"]["median_s"] == 10.0


def test_update_baseline_keeps_rolling_window_of_max_samples():
    baseline = {}
    for d in [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]:
        baseline = di.update_baseline(baseline, "t1", d, max_samples=5)
    # oldest sample (1.0) dropped once the 6th arrives
    assert baseline["t1"]["samples"] == [2.0, 3.0, 4.0, 5.0, 6.0]
    assert baseline["t1"]["median_s"] == 4.0


def test_update_baseline_does_not_mutate_input():
    original = {"t1": {"samples": [1.0], "median_s": 1.0}}
    frozen = json.dumps(original, sort_keys=True)
    di.update_baseline(original, "t1", 99.0)
    assert json.dumps(original, sort_keys=True) == frozen


def test_update_baseline_is_independent_per_nodeid():
    baseline = di.update_baseline({}, "t1", 10.0)
    baseline = di.update_baseline(baseline, "t2", 20.0)
    assert baseline["t1"]["median_s"] == 10.0
    assert baseline["t2"]["median_s"] == 20.0


# --- evaluate_flag (AC3: relative-AND-absolute threshold) ------------------

def test_evaluate_flag_false_with_no_baseline_bootstrap():
    assert di.evaluate_flag(999.0, None) is False


def test_evaluate_flag_false_when_under_relative_threshold():
    # 1.4x baseline: fails the 1.5x relative bar even though absolute gap is large
    assert di.evaluate_flag(140.0, 100.0) is False


def test_evaluate_flag_false_when_under_absolute_floor():
    # 2x baseline but tiny absolute values: fails the +10s absolute bar
    assert di.evaluate_flag(2.0, 1.0) is False


def test_evaluate_flag_true_when_both_thresholds_exceeded():
    # 1.87x baseline AND +65s over baseline
    assert di.evaluate_flag(140.0, 75.0) is True


def test_evaluate_flag_boundary_is_strictly_greater_not_equal():
    # exactly at both thresholds: not flagged (">" not ">=")
    assert di.evaluate_flag(150.0, 100.0) is False  # 150 == 100*1.5 exactly
    assert di.evaluate_flag(110.0, 100.0) is False  # 110 == 100+10 exactly


# --- build_record (AC2, AC3, AC4: record shape) -----------------------------

def _kwargs(**overrides):
    base = dict(
        run_id="run-2026-08-05T12:00:00Z", index=3, total=418,
        nodeid="tests/test_x.py::test_y", outcome="passed",
        setup_s=0.1, call_s=2.3, teardown_s=0.05, baseline_s=None,
    )
    base.update(overrides)
    return base


def test_build_record_sums_total_from_three_phases():
    rec = di.build_record(**_kwargs(setup_s=0.10, call_s=2.30, teardown_s=0.05))
    assert rec["total_s"] == pytest.approx(2.45)


def test_build_record_bootstrap_has_no_flag_and_no_pct():
    rec = di.build_record(**_kwargs(baseline_s=None))
    assert rec["flagged"] is False
    assert rec["baseline_s"] is None
    assert rec["pct_over"] is None


def test_build_record_flags_slow_test_with_pct_over():
    rec = di.build_record(**_kwargs(setup_s=0, call_s=140.0, teardown_s=0, baseline_s=75.0))
    assert rec["flagged"] is True
    assert rec["pct_over"] == pytest.approx(86.7, abs=0.1)


def test_build_record_carries_progress_and_identity_fields():
    rec = di.build_record(**_kwargs(index=42, total=418, nodeid="tests/test_x.py::test_y"))
    assert rec["index"] == 42
    assert rec["total"] == 418
    assert rec["nodeid"] == "tests/test_x.py::test_y"
    assert rec["run_id"] == "run-2026-08-05T12:00:00Z"
    assert "ts" in rec


# --- build_record: outcome_class / attempts (H6/H7, gts-u6ew.6/.7) ---------

def test_build_record_defaults_outcome_class_and_attempts_to_none():
    rec = di.build_record(**_kwargs())
    assert rec["outcome_class"] is None
    assert rec["attempts"] is None


def test_build_record_carries_outcome_class_and_attempts_when_given():
    rec = di.build_record(**_kwargs(outcome_class="BOUNDARY_FAULT", attempts=5))
    assert rec["outcome_class"] == "BOUNDARY_FAULT"
    assert rec["attempts"] == 5


# --- summarize_run (H8, gts-u6ew.8) -----------------------------------------

def _rec(outcome="passed", total_s=1.0, outcome_class=None):
    return {"outcome": outcome, "total_s": total_s, "outcome_class": outcome_class}


def test_summarize_run_empty_input_is_all_zero_not_error():
    summary = di.summarize_run([])
    assert summary["executions"] == 0
    assert summary["execution_failure_rate"] == 0.0
    assert summary["failed_wall_time_share"] == 0.0
    assert summary["boundary_faults"] is None
    assert summary["boundary_fault_share_of_failures"] is None


def test_summarize_run_all_passed_has_zero_failure_rate():
    records = [_rec(), _rec(), _rec()]
    summary = di.summarize_run(records)
    assert summary["executions"] == 3
    assert summary["failed"] == 0
    assert summary["execution_failure_rate"] == 0.0
    assert summary["failed_wall_time_share"] == 0.0
    assert summary["boundary_faults"] == 0
    assert summary["boundary_fault_share_of_failures"] == 0.0


def test_summarize_run_execution_failure_rate():
    records = [_rec()] * 9 + [_rec(outcome="failed")]
    summary = di.summarize_run(records)
    assert summary["executions"] == 10
    assert summary["failed"] == 1
    assert summary["execution_failure_rate"] == pytest.approx(0.1)


def test_summarize_run_failed_wall_time_share():
    records = [
        _rec(outcome="passed", total_s=10.0),
        _rec(outcome="failed", total_s=30.0),
    ]
    summary = di.summarize_run(records)
    assert summary["wall_time_s"] == pytest.approx(40.0)
    assert summary["failed_wall_time_s"] == pytest.approx(30.0)
    assert summary["failed_wall_time_share"] == pytest.approx(0.75)


def test_summarize_run_boundary_fault_share_of_failures():
    records = [
        _rec(outcome="failed", outcome_class="BOUNDARY_FAULT"),
        _rec(outcome="failed", outcome_class="ASSERTION_FAILURE"),
        _rec(outcome="passed"),
    ]
    summary = di.summarize_run(records)
    assert summary["boundary_faults"] == 1
    assert summary["boundary_fault_share_of_failures"] == pytest.approx(0.5)


def test_summarize_run_unclassified_failure_never_counts_as_boundary_fault():
    # A record with outcome_class=None (e.g. no request= context) must not be
    # silently swept into the boundary-fault count -- "unclassified" and
    # "boundary fault" are different claims.
    records = [_rec(outcome="failed", outcome_class=None)]
    summary = di.summarize_run(records)
    assert summary["boundary_faults"] == 0
    assert summary["boundary_fault_share_of_failures"] == 0.0


# --- format_run_summary (H8) -------------------------------------------------

def test_format_run_summary_empty_run():
    line = di.format_run_summary(di.summarize_run([]))
    assert "no executions" in line


def test_format_run_summary_includes_rate_and_boundary_share():
    records = [
        _rec(outcome="passed", total_s=10.0),
        _rec(outcome="failed", total_s=30.0, outcome_class="BOUNDARY_FAULT"),
    ]
    line = di.format_run_summary(di.summarize_run(records))
    assert "1/2 executions failed" in line
    assert "50.0%" in line  # execution failure rate
    assert "boundary fault" in line


# --- baseline file round-trip (AC5) -----------------------------------------

def test_save_and_load_baseline_round_trips(tmp_path):
    path = tmp_path / "baseline.json"
    baseline = di.update_baseline({}, "t1", 12.5)
    di.save_baseline(baseline, path)
    loaded = di.load_baseline(path)
    assert loaded == baseline


def test_load_baseline_missing_file_returns_empty_dict(tmp_path):
    assert di.load_baseline(tmp_path / "does-not-exist.json") == {}


def test_load_baseline_corrupt_file_returns_empty_dict(tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text("{not valid json")
    assert di.load_baseline(path) == {}


# --- JSONL append (AC4: flushed, tailable) ----------------------------------

def test_append_jsonl_writes_one_line_per_record(tmp_path):
    path = tmp_path / "duration-log.jsonl"
    rec1 = di.build_record(**_kwargs(index=1))
    rec2 = di.build_record(**_kwargs(index=2))
    di.append_jsonl(rec1, path)
    di.append_jsonl(rec2, path)
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["index"] == 1
    assert json.loads(lines[1])["index"] == 2


def test_append_jsonl_flushes_immediately_readable_before_close(tmp_path):
    """AC4: an external tailing tool must see the line without waiting on
    process exit. Simulated here by reading the file via a second independent
    file handle right after append_jsonl returns, before any explicit close
    of a long-lived writer (append_jsonl itself owns open/write/flush/close
    per call, so this mainly guards against a future refactor introducing
    block buffering via a kept-open handle)."""
    path = tmp_path / "duration-log.jsonl"
    di.append_jsonl(di.build_record(**_kwargs()), path)
    with open(path) as f:
        content = f.read()
    assert content.strip() != ""
    assert json.loads(content.strip())["nodeid"] == "tests/test_x.py::test_y"


# --- format_finish_line / format_start_line (AC1) ---------------------------

def test_format_start_line_includes_progress_counter():
    line = di.format_start_line(7, 418, "tests/test_x.py::test_y")
    assert "[7/418]" in line
    assert "tests/test_x.py::test_y" in line


def test_format_finish_line_bootstrap_says_na_not_a_flag():
    rec = di.build_record(**_kwargs(baseline_s=None))
    line = di.format_finish_line(rec)
    assert "n/a" in line
    assert "SLOW" not in line


def test_format_finish_line_shows_durations_and_flag_when_slow():
    rec = di.build_record(**_kwargs(setup_s=0.1, call_s=140.0, teardown_s=0.05, baseline_s=75.0))
    line = di.format_finish_line(rec)
    assert "setup=0.10s" in line
    assert "call=140.00s" in line
    assert "teardown=0.05s" in line
    assert "SLOW" in line


def test_format_finish_line_no_flag_marker_when_not_slow():
    rec = di.build_record(**_kwargs(setup_s=0.1, call_s=10.0, teardown_s=0.05, baseline_s=100.0))
    line = di.format_finish_line(rec)
    assert "SLOW" not in line
