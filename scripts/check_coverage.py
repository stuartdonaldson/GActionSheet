#!/usr/bin/env python3
"""
check_coverage.py — Compare JUnit coverage properties against the registries (T24 Step 3).

Parses test-results/junit/pytest.xml for ac.* and ep.* properties (emitted by
ScenarioSession), extracts AC tags and entry-point keys, and diffs them against
scn/contract.AC_REGISTRY and scn/contract.ENTRY_POINT_REGISTRY respectively. Reports
covered, uncovered, and warn-only items for each. Exits 1 if either diff has gaps.

H9 (gts-u6ew.15): a registry key with no PASS/WARN coverage is split into
'uncovered' (confirmed — the run that produced the JUnit file was clean) and
'unreached this run' (the run had at least one BOUNDARY_FAULT execution, so
absence of coverage does not confirm no test exists — see
_latest_run_boundary_fault_info's docstring for why this reads
test-results/duration-log.jsonl rather than the JUnit file itself).

H10 (gts-u6ew.16): a report-only, non-gating check for AC_REGISTRY entries with
zero PASS coverage across the last N JUnit files on disk (by mtime). NOT a
settled signal — see docs/atdd/harness-design.md §9a's H10 row (`unknown`) and
docs/atdd/test-framework-upgrade-plan.md escalation E2. This stage builds the
instrument; it does not run the full sweep that would settle it.

Usage:
    python scripts/check_coverage.py [--xml <path>] [--verbose]
    python scripts/check_coverage.py --duration-log <path> --junit-glob <glob> --stale-window N
"""
import glob as globlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scn.contract import AC_REGISTRY, ENTRY_POINT_REGISTRY, ENTRY_POINT_DEFERRED

DEFAULT_XML = "test-results/junit/pytest.xml"
DEFAULT_DURATION_LOG = "test-results/duration-log.jsonl"
DEFAULT_JUNIT_GLOB = "test-results/junit/*.xml"
DEFAULT_STALE_WINDOW = 3


def _parse_junit(path) -> ET.Element | None:
    """Parse one JUnit XML file into its root element.

    Tolerant of a missing or corrupt file (returns None). Shared by both the
    live gap-diff (today's single --xml file) and the H10 staleness window
    (many files, gts-u6ew.16) — one JUnit-reading path (I6/I12), not two.
    """
    p = Path(path)
    if not p.exists():
        return None
    try:
        return ET.parse(p).getroot()
    except ET.ParseError:
        return None


def _collect(root, prefix):
    """Collect covered (PASS) and warn-only keys from <prefix>.<key>.<surface> properties."""
    covered = set()
    warn_only = set()
    for testcase in root.iter("testcase"):
        for prop in testcase.iter("property"):
            name = prop.get("name", "")
            value = prop.get("value", "")
            if name.startswith(prefix):
                parts = name.split(".")
                if len(parts) >= 3:
                    key = ".".join(parts[1:-1])
                    if value == "PASS":
                        covered.add(key)
                    elif value == "WARN":
                        warn_only.add(key)
    return covered, warn_only


def _load_duration_log(path) -> list:
    """Read the JSONL duration/outcome-class log. Tolerates a missing file and
    bad lines — this is observability input, never a hard error (matches
    tests/duration_instrumentation.load_baseline's own tolerance convention)."""
    p = Path(path)
    if not p.exists():
        return []
    records = []
    for line in p.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _latest_run_boundary_fault_info(records: list) -> tuple:
    """H9 (gts-u6ew.15): does the most recent run in the duration log carry any
    BOUNDARY_FAULT execution?

    outcome_class (H6, scn.outcomes.classify) does not reach JUnit XML
    properties in this project: ScenarioSession's ac.*/ep.* properties
    (scn/reporter.py::Reporter.junit) append to `item.user_properties`, which
    survives into _pytest.junitxml.LogXML.finalize()'s teardown-phase
    snapshot — but tests/conftest.py's pytest_runtest_makereport hookwrapper
    appends outcome_class directly onto the already-built call-phase
    TestReport's `report.user_properties`, a separate list finalize() never
    reads (it reads only the teardown report passed to it). Verified
    empirically 2026-09-05: a clean local run writes zero <property> elements
    to pytest.xml, while every duration-log.jsonl record for that same run
    carries outcome_class="PASS" (tests/conftest.py's pytest_runtest_logreport
    reads report.user_properties directly off the call-phase report before
    teardown, so it sees the stamp; junitxml does not).
    test-results/duration-log.jsonl is therefore this project's one reliable
    source for outcome_class, and this function reads it rather than the
    JUnit file being diffed. (Not this stage's fix to make — conftest.py is
    stage 3's closed, uncommitted diff; noted for the record.)

    Returns (run_id, boundary_fault_count, total_records) for the most recent
    run_id present in `records` (last record in file-append order);
    (None, 0, 0) if records is empty.
    """
    if not records:
        return None, 0, 0
    latest_run_id = records[-1].get("run_id")
    run_records = [r for r in records if r.get("run_id") == latest_run_id]
    faults = sum(1 for r in run_records if r.get("outcome_class") == "BOUNDARY_FAULT")
    return latest_run_id, faults, len(run_records)


def _split_uncovered_from_missing(missing: set, boundary_fault_this_run: bool) -> tuple:
    """H9: split registry keys with no PASS/WARN coverage into (uncovered,
    unreached_this_run).

    boundary_fault_this_run True — the run that produced the JUnit file being
    diffed had at least one BOUNDARY_FAULT execution, so an absent-coverage
    key does not confirm "nobody wrote a test for this": a platform outage
    could have stopped a covering test before it reached its checkpoint.
    Everything in `missing` is reported 'unreached this run' rather than
    'uncovered' — the report stays readable during a platform incident
    instead of reading every gap as a missing test, at a measured 7.6%
    baseline execution failure rate (docs/atdd/test-framework-upgrade-plan.md
    §1).

    boundary_fault_this_run False — the run was clean; every key still
    missing is a confirmed gap: 'uncovered'.
    """
    if boundary_fault_this_run:
        return set(), set(missing)
    return set(missing), set()


def _report(label, noun, registry, covered, warn_only, verbose, deferred=None,
            boundary_fault_this_run=False):
    """Print a coverage section; return a bitmask distinguishing the two gap
    kinds (H9): bit 0 (1) = confirmed 'uncovered' present, bit 1 (2) =
    'unreached this run' present. 0 means fully covered/warned.

    deferred (T17, GTaskSheet-z6f8): a dict {key: reason} of registered entry
    points with no current scenario call-site. These are treated as
    explicitly warn-only — enumerated but not yet asserted — so the gap-diff
    stays green while EPIC GTaskSheet-rz4k converts each to a real tagged
    call-site. A deferred key that gains real PASS coverage is reported as
    covered, not warn-only.
    """
    deferred = deferred or {}
    # Registry-declared deferrals count as warn-only unless a scenario already covers them.
    deferred_warn = (set(deferred) & set(registry)) - covered
    warn_only = set(warn_only) | deferred_warn
    missing = set(registry.keys()) - covered - warn_only
    uncovered, unreached = _split_uncovered_from_missing(missing, boundary_fault_this_run)

    print(label)
    print("=" * 60)
    print(f"Registry size: {len(registry)}")
    print(f"Covered (PASS): {len(covered)}")
    print(f"Warn-only: {len(warn_only)}")
    print(f"Uncovered: {len(uncovered)}")
    print(f"Unreached this run: {len(unreached)}")
    print()

    if verbose:
        if covered:
            print(f"Covered {noun}:")
            for key in sorted(covered):
                print(f"  ✓ {key}")
            print()
        if warn_only:
            print(f"Warn-only {noun}:")
            for key in sorted(warn_only):
                reason = deferred.get(key)
                suffix = f" (deferred: {reason})" if key in deferred_warn and reason else ""
                print(f"  ⚠ {key}{suffix}")
            print()

    rc = 0
    if uncovered:
        print(f"Uncovered {noun}:")
        for key in sorted(uncovered):
            print(f"  ✗ {key}: {registry[key]}")
        print()
        rc |= 1
    if unreached:
        print(f"Unreached this run {noun} (a boundary fault occurred this run — "
              f"not confirmed missing, see H9):")
        for key in sorted(unreached):
            print(f"  ? {key}: {registry[key]}")
        print()
        rc |= 2

    if not uncovered and not unreached:
        print(f"All {noun} covered!")
        print()
    return rc


def _collect_ac_coverage_per_file(paths: list) -> dict:
    """Map JUnit file stem -> set of AC keys with PASS coverage in that file.

    Reuses `_parse_junit`/`_collect` (I6/I12) — the same reading path the
    live gap-diff uses for the current run's single file, applied per file
    across the H10 staleness window (gts-u6ew.16).
    """
    coverage = {}
    for path in paths:
        root = _parse_junit(path)
        if root is None:
            continue
        covered, _warn = _collect(root, "ac.")
        if covered:
            coverage[Path(path).stem] = covered
    return coverage


def _stale_acs(ac_registry: dict, coverage_by_run: dict, window: int) -> dict:
    """H10 (gts-u6ew.16): AC_REGISTRY entries with zero PASS coverage across
    the last `window` runs.

    Ported from $DEVSTANDARD/tools/test-suite-diagnostics.py's
    junit_ac_coverage/stale_acs (same algorithm: `coverage_by_run` is ordered
    oldest-first by file mtime — see `_junit_files_by_mtime` — so the window
    is the last N *runs*, not the last N *names*; PASS coverage is unioned
    over the most recent `window` entries; any registry key never seen in
    that union is 'candidate stale').

    NOT a settled signal — docs/atdd/harness-design.md §9a's H10 row stays
    `unknown`/`waived` (escalation E2,
    docs/atdd/test-framework-upgrade-plan.md). This is the instrument only:
    the caller must treat the result as report-only, never gating, and the
    window is whatever JUnit files this project happens to have on disk —
    not a verified full-suite profile.
    """
    if not coverage_by_run:
        return {"checked": False, "reason": "no JUnit ac.* PASS coverage found in any file"}
    recent = list(coverage_by_run.values())[-window:]
    seen = set()
    for entry in recent:
        seen |= entry
    registry_keys = set(ac_registry.keys())
    stale = sorted(k for k in registry_keys if k not in seen)
    return {
        "checked": True,
        "runs_considered": len(recent),
        "registry_size": len(registry_keys),
        "covered_in_window": len(seen & registry_keys),
        "candidate_stale": stale,
    }


def _junit_files_by_mtime(pattern: str) -> list:
    """Glob `pattern`, oldest-first by mtime — the ordering _stale_acs's
    window slicing (`[-window:]`) depends on to mean "the last N runs"."""
    files = globlib.glob(pattern)
    files.sort(key=lambda f: Path(f).stat().st_mtime)
    return files


def _print_staleness(result: dict, window: int) -> None:
    """H10: print the staleness instrument's output. Always report-only —
    never contributes to main()'s exit code (see module docstring)."""
    print("AC Staleness Check (H10)")
    print("=" * 60)
    print("NOT SETTLED — report-only, does not affect exit status. See")
    print("docs/atdd/harness-design.md §9a's H10 row and")
    print("docs/atdd/test-framework-upgrade-plan.md escalation E2: settling")
    print("this needs one operator-initiated full regression sweep.")
    if not result["checked"]:
        print(f"Not checked: {result['reason']}")
        print()
        return
    print(f"Runs considered: {result['runs_considered']} (window={window})")
    print(f"Registry size: {result['registry_size']}")
    print(f"Covered in window: {result['covered_in_window']}")
    print(f"Candidate stale: {len(result['candidate_stale'])}")
    if result["candidate_stale"]:
        print("Candidate-stale ACs (zero PASS coverage across the window — "
              "resolve each as retire-the-AC or restore-the-coverage, T25):")
        for key in result["candidate_stale"]:
            print(f"  ? {key}: {AC_REGISTRY.get(key, '(no description)')}")
    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Check AC and entry-point coverage against JUnit properties")
    parser.add_argument("--xml", default=DEFAULT_XML, help="Path to JUnit XML for the live gap-diff")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all items and coverage")
    parser.add_argument("--duration-log", default=DEFAULT_DURATION_LOG,
                         help="Path to duration-log.jsonl (H9 boundary-fault context)")
    parser.add_argument("--junit-glob", default=DEFAULT_JUNIT_GLOB,
                         help="Glob of JUnit XML files for the H10 staleness window")
    parser.add_argument("--stale-window", type=int, default=DEFAULT_STALE_WINDOW,
                         help="Number of most-recent runs the H10 staleness check spans")
    parser.add_argument("--no-staleness", action="store_true",
                         help="Skip the H10 staleness check section")
    args = parser.parse_args()

    root = _parse_junit(args.xml)
    if root is None:
        print(f"ERROR: {args.xml} not found or unparseable", file=sys.stderr)
        return 1

    duration_records = _load_duration_log(args.duration_log)
    run_id, fault_count, run_total = _latest_run_boundary_fault_info(duration_records)
    boundary_fault_this_run = fault_count > 0
    if duration_records:
        print(f"Latest run (duration log): {run_id} — {run_total} execution(s), "
              f"{fault_count} boundary fault(s)")
    else:
        print(f"No duration log at {args.duration_log} — boundary-fault context "
              f"unavailable; gaps reported as 'uncovered' with no unreached-this-run split")
    print()

    ac_covered, ac_warn = _collect(root, "ac.")
    ep_covered, ep_warn = _collect(root, "ep.")

    rc = 0
    rc |= _report("AC Coverage Report", "ACs", AC_REGISTRY, ac_covered, ac_warn, args.verbose,
                  boundary_fault_this_run=boundary_fault_this_run)
    rc |= _report("Entry-Point Coverage Report", "entry points", ENTRY_POINT_REGISTRY,
                  ep_covered, ep_warn, args.verbose, deferred=ENTRY_POINT_DEFERRED,
                  boundary_fault_this_run=boundary_fault_this_run)

    if not args.no_staleness:
        files = _junit_files_by_mtime(args.junit_glob)
        coverage_by_run = _collect_ac_coverage_per_file(files)
        stale = _stale_acs(AC_REGISTRY, coverage_by_run, args.stale_window)
        _print_staleness(stale, args.stale_window)

    return rc


if __name__ == "__main__":
    sys.exit(main())
