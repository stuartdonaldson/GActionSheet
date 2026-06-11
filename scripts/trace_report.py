#!/usr/bin/env python3
"""
trace_report.py — Render a readable report from a scn/reporter.py trace (T24-adjacent).

Reads ONE `<node>_<utc>.trace.jsonl` (the structured per-step trace written by
every scenario run under test-results/runs/) and prints:
  1. Header — file path and total wall span.
  2. TIMELINE — every event in seq order.
  3. PER-PHASE TOTALS — event counts and summed dur_s per phase, busiest first.
  4. SLOWEST STEPS — top N events by dur_s.
  5. CHECK COVERAGE — PASS/WARN/FAIL rollup grouped by `checking`.

Use this to see where a long run spent its time, or to find the FAIL/WARN
checks in a completed run without scrolling the .log file.

Usage:
    python scripts/trace_report.py [jsonl] [--top N]

If `jsonl` is omitted, the most recently modified `*.trace.jsonl` under
test-results/runs/ is used.
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

RUNS_DIR = Path("test-results/runs")


def _find_latest() -> Path | None:
    """Return the most recently modified *.trace.jsonl under test-results/runs/, or None."""
    candidates = list(RUNS_DIR.glob("*.trace.jsonl"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _load(jsonl_path: Path) -> list[dict]:
    events = []
    with jsonl_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def _print_timeline(events):
    print("TIMELINE")
    print("=" * 60)
    for rec in events:
        dur = f"({rec['dur_s']:.2f}s)" if rec.get("dur_s") is not None else ""
        line = f"{rec['t_elapsed']:7.2f}s  {rec['phase']:<10} {rec['name']:<32} {dur}"
        result = rec.get("result", "OK")
        if result != "OK":
            line += f" {result}"
        if rec.get("checking"):
            line += f"  check={rec['checking']}"
        print(line.rstrip())
    print()


def _print_phase_totals(events):
    print("PER-PHASE TOTALS")
    print("=" * 60)
    counts = defaultdict(int)
    totals = defaultdict(float)
    for rec in events:
        phase = rec["phase"]
        counts[phase] += 1
        if rec.get("dur_s") is not None:
            totals[phase] += rec["dur_s"]
    for phase, total in sorted(totals.items(), key=lambda kv: kv[1], reverse=True):
        print(f"{phase:<12} count={counts[phase]:<4} total={total:7.2f}s")
    # Phases with events but no durations at all
    for phase in sorted(counts):
        if phase not in totals:
            print(f"{phase:<12} count={counts[phase]:<4} total=   0.00s")
    print()


def _print_slowest(events, top: int):
    print(f"SLOWEST STEPS (top {top})")
    print("=" * 60)
    timed = [rec for rec in events if rec.get("dur_s") is not None]
    timed.sort(key=lambda rec: rec["dur_s"], reverse=True)
    for rec in timed[:top]:
        extra = rec.get("checking") or rec.get("detail") or ""
        print(f"{rec['dur_s']:7.2f}s  {rec['phase']} {rec['name']}  {extra}")
    if not timed:
        print("(no timed events)")
    print()


def _print_check_coverage(events):
    print("CHECK COVERAGE")
    print("=" * 60)
    checks = [rec for rec in events if rec.get("phase") == "CHECK"]
    if not checks:
        print("(no CHECK events)")
        print()
        return

    by_check = defaultdict(lambda: defaultdict(int))
    for rec in checks:
        key = rec.get("checking") or rec.get("name")
        by_check[key][rec.get("result", "OK")] += 1

    for key in sorted(by_check):
        results = by_check[key]
        parts = ", ".join(f"{r}={n}" for r, n in sorted(results.items()))
        print(f"{key}: {parts}")

    fails = {k: v["FAIL"] for k, v in by_check.items() if v.get("FAIL")}
    print()
    if fails:
        print("FAILED CHECKS:")
        for key, n in sorted(fails.items()):
            print(f"  ✗ {key}: {n} FAIL")
    else:
        print("No FAIL checks.")
    print()


def main():
    parser = argparse.ArgumentParser(description="Render a readable report from a scn trace .jsonl")
    parser.add_argument("jsonl", nargs="?", help="Path to a *.trace.jsonl file (default: latest under test-results/runs/)")
    parser.add_argument("--top", type=int, default=10, help="Number of slowest steps to show (default: 10)")
    args = parser.parse_args()

    if args.jsonl:
        jsonl_path = Path(args.jsonl)
    else:
        jsonl_path = _find_latest()
        if jsonl_path is None:
            print(f"ERROR: no *.trace.jsonl found under {RUNS_DIR}/", file=sys.stderr)
            return 1

    if not jsonl_path.exists():
        print(f"ERROR: {jsonl_path} not found", file=sys.stderr)
        return 1

    events = _load(jsonl_path)

    print(f"Trace: {jsonl_path}")
    span = max((rec["t_elapsed"] for rec in events), default=0.0)
    print(f"Total wall span: {span:.2f}s")
    print()

    _print_timeline(events)
    _print_phase_totals(events)
    _print_slowest(events, args.top)
    _print_check_coverage(events)

    return 0


if __name__ == "__main__":
    sys.exit(main())
