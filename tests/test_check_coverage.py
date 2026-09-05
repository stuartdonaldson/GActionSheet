"""test_check_coverage.py — gts-u6ew.15 (H9) / gts-u6ew.16 (H10).

Focused tests for scripts/check_coverage.py's pure logic: the
uncovered/unreached-this-run split (H9), the duration-log boundary-fault
lookup it's keyed on, and the AC-staleness window computation (H10). No
live pytest subprocess or real JUnit run — every function under test takes
already-parsed data (sets, dicts, lists of records) rather than doing its
own file I/O, so this is a specifiable oracle (T12), same shape as
tests/test_duration_instrumentation.py and tests/test_scn_outcomes.py.

Coverage inventory (test-functional Step 1, run before authoring): no
tests/test_check_coverage.py existed before this bead — scripts/
check_coverage.py had no test file at all. No coverage to extend; net-new.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

# gts-aqpk: fast/local tier -- pure logic, no live GAS/Google round trip.
pytestmark = pytest.mark.no_live_session

# scripts/ is not a package (no __init__.py) and its module name collides
# with nothing else on sys.path, so load it directly by path rather than
# adding scripts/ to sys.path for the whole test session.
_SPEC = importlib.util.spec_from_file_location(
    "check_coverage", Path(__file__).parent.parent / "scripts" / "check_coverage.py"
)
cc = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("check_coverage", cc)
_SPEC.loader.exec_module(cc)


# --- _split_uncovered_from_missing (H9) -------------------------------------

def test_split_reports_confirmed_uncovered_when_run_was_clean():
    uncovered, unreached = cc._split_uncovered_from_missing({"a", "b"}, boundary_fault_this_run=False)
    assert uncovered == {"a", "b"}
    assert unreached == set()


def test_split_reports_unreached_this_run_when_boundary_fault_present():
    uncovered, unreached = cc._split_uncovered_from_missing({"a", "b"}, boundary_fault_this_run=True)
    assert uncovered == set()
    assert unreached == {"a", "b"}


def test_split_is_empty_both_ways_with_no_missing_keys():
    uncovered, unreached = cc._split_uncovered_from_missing(set(), boundary_fault_this_run=True)
    assert uncovered == set()
    assert unreached == set()


# --- _latest_run_boundary_fault_info (H9) -----------------------------------

def test_latest_run_info_empty_on_no_records():
    run_id, faults, total = cc._latest_run_boundary_fault_info([])
    assert (run_id, faults, total) == (None, 0, 0)


def test_latest_run_info_counts_only_the_most_recent_run_id():
    records = [
        {"run_id": "run-1", "outcome_class": "BOUNDARY_FAULT"},
        {"run_id": "run-1", "outcome_class": "PASS"},
        {"run_id": "run-2", "outcome_class": "PASS"},
        {"run_id": "run-2", "outcome_class": "PASS"},
        {"run_id": "run-2", "outcome_class": "ASSERTION_FAILURE"},
    ]
    run_id, faults, total = cc._latest_run_boundary_fault_info(records)
    # run-2 is last in append order -> the "latest run", 0 boundary faults,
    # even though an earlier run (run-1) had one.
    assert run_id == "run-2"
    assert faults == 0
    assert total == 3


def test_latest_run_info_detects_boundary_fault_in_latest_run():
    records = [
        {"run_id": "run-1", "outcome_class": "PASS"},
        {"run_id": "run-2", "outcome_class": "PASS"},
        {"run_id": "run-2", "outcome_class": "BOUNDARY_FAULT"},
    ]
    run_id, faults, total = cc._latest_run_boundary_fault_info(records)
    assert run_id == "run-2"
    assert faults == 1
    assert total == 2


def test_latest_run_info_tolerates_missing_outcome_class():
    # A harness self-test record (no request=) carries outcome_class=None --
    # must count toward total but never toward faults.
    records = [{"run_id": "run-1", "outcome_class": None}]
    run_id, faults, total = cc._latest_run_boundary_fault_info(records)
    assert run_id == "run-1"
    assert faults == 0
    assert total == 1


# --- _report exit-code bitmask (H9: "distinct exit-code meaning") ----------

def test_report_rc_zero_when_fully_covered(capsys):
    rc = cc._report("L", "things", {"a": "desc"}, covered={"a"}, warn_only=set(), verbose=False)
    assert rc == 0


def test_report_rc_bit0_for_confirmed_uncovered(capsys):
    rc = cc._report("L", "things", {"a": "desc"}, covered=set(), warn_only=set(), verbose=False,
                     boundary_fault_this_run=False)
    assert rc == 1


def test_report_rc_bit1_for_unreached_this_run(capsys):
    rc = cc._report("L", "things", {"a": "desc"}, covered=set(), warn_only=set(), verbose=False,
                     boundary_fault_this_run=True)
    assert rc == 2


def test_report_rc_combines_both_bits_across_two_registries():
    rc = 0
    rc |= cc._report("L1", "things", {"a": "desc"}, covered=set(), warn_only=set(), verbose=False,
                      boundary_fault_this_run=False)
    rc |= cc._report("L2", "things", {"b": "desc"}, covered=set(), warn_only=set(), verbose=False,
                      boundary_fault_this_run=True)
    assert rc == 3


def test_report_deferred_entries_still_count_as_warn_only_not_uncovered():
    rc = cc._report(
        "L", "entry points", {"a": "desc"}, covered=set(), warn_only=set(), verbose=False,
        deferred={"a": "no call-site yet"}, boundary_fault_this_run=False,
    )
    assert rc == 0


# --- _stale_acs (H10) -------------------------------------------------------

def test_stale_acs_not_checked_with_no_coverage_history():
    result = cc._stale_acs({"a": "d"}, coverage_by_run={}, window=3)
    assert result == {"checked": False, "reason": "no JUnit ac.* PASS coverage found in any file"}


def test_stale_acs_flags_registry_key_never_seen_in_window():
    coverage_by_run = {
        "run-1": {"a"},
        "run-2": {"a"},
        "run-3": {"a"},
    }
    result = cc._stale_acs({"a": "d", "b": "d"}, coverage_by_run, window=3)
    assert result["checked"] is True
    assert result["candidate_stale"] == ["b"]
    assert result["runs_considered"] == 3
    assert result["registry_size"] == 2
    assert result["covered_in_window"] == 1


def test_stale_acs_window_slices_to_most_recent_n_only():
    # "a" is covered only in the oldest run, outside a window of 2 -- must
    # still be flagged stale even though it has coverage somewhere in history.
    coverage_by_run = {
        "run-1": {"a"},
        "run-2": {"b"},
        "run-3": {"b"},
    }
    result = cc._stale_acs({"a": "d", "b": "d"}, coverage_by_run, window=2)
    assert result["candidate_stale"] == ["a"]
    assert result["runs_considered"] == 2


def test_stale_acs_no_candidates_when_everything_seen_in_window():
    coverage_by_run = {"run-1": {"a", "b"}}
    result = cc._stale_acs({"a": "d", "b": "d"}, coverage_by_run, window=3)
    assert result["candidate_stale"] == []


# --- _collect / _parse_junit / _load_duration_log (file I/O, shared path) --

def _write_junit(path, properties):
    """properties: list of (name, value) tuples on one <testcase>."""
    props_xml = "".join(f'<property name="{n}" value="{v}"/>' for n, v in properties)
    path.write_text(
        '<?xml version="1.0"?><testsuites><testsuite name="pytest">'
        f'<testcase classname="t" name="t1"><properties>{props_xml}</properties></testcase>'
        "</testsuite></testsuites>"
    )


def test_parse_junit_returns_none_for_missing_file(tmp_path):
    assert cc._parse_junit(tmp_path / "nope.xml") is None


def test_parse_junit_returns_none_for_corrupt_file(tmp_path):
    p = tmp_path / "bad.xml"
    p.write_text("<not-closed>")
    assert cc._parse_junit(p) is None


def test_collect_reads_pass_and_warn_from_parsed_junit(tmp_path):
    p = tmp_path / "pytest.xml"
    _write_junit(p, [("ac.foo.DOC", "PASS"), ("ac.bar.SHEET", "WARN")])
    root = cc._parse_junit(p)
    covered, warn = cc._collect(root, "ac.")
    assert covered == {"foo"}
    assert warn == {"bar"}


def test_collect_ac_coverage_per_file_keys_by_file_stem(tmp_path):
    p1 = tmp_path / "run-1.xml"
    p2 = tmp_path / "run-2.xml"
    _write_junit(p1, [("ac.foo.DOC", "PASS")])
    _write_junit(p2, [("ac.bar.DOC", "PASS")])
    coverage = cc._collect_ac_coverage_per_file([str(p1), str(p2)])
    assert coverage == {"run-1": {"foo"}, "run-2": {"bar"}}


def test_collect_ac_coverage_per_file_skips_unparseable(tmp_path):
    good = tmp_path / "good.xml"
    bad = tmp_path / "bad.xml"
    _write_junit(good, [("ac.foo.DOC", "PASS")])
    bad.write_text("<broken")
    coverage = cc._collect_ac_coverage_per_file([str(good), str(bad)])
    assert coverage == {"good": {"foo"}}


def test_load_duration_log_missing_file_returns_empty(tmp_path):
    assert cc._load_duration_log(tmp_path / "nope.jsonl") == []


def test_load_duration_log_skips_bad_lines(tmp_path):
    p = tmp_path / "log.jsonl"
    p.write_text('{"run_id": "r1", "outcome_class": "PASS"}\nnot json\n\n')
    records = cc._load_duration_log(p)
    assert records == [{"run_id": "r1", "outcome_class": "PASS"}]


def test_junit_files_by_mtime_orders_oldest_first(tmp_path):
    import os
    import time

    p1 = tmp_path / "a.xml"
    p2 = tmp_path / "b.xml"
    p1.write_text("<x/>")
    time.sleep(0.01)
    p2.write_text("<x/>")
    files = cc._junit_files_by_mtime(str(tmp_path / "*.xml"))
    assert files == [str(p1), str(p2)]
