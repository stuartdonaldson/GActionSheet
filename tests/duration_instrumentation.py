"""tests/duration_instrumentation.py — pure logic for pytest progress/duration
reporting (gts-y1eg).

Kept separate from conftest.py's hook wiring so the decision logic (rolling
baseline, flag threshold, record/line shape) is unit-testable without a live
pytest subprocess (T12 — specifiable oracle). conftest.py owns only the thin
hookimpl wiring that calls into this module.

Report-only: nothing here can fail or skip a test. A "flag" is purely a
marker on the terminal line and the JSONL record.
"""
from __future__ import annotations

import json
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).parent.parent

BASELINE_PATH = Path(__file__).parent / ".pytest_duration_baseline.json"
LOG_PATH = _REPO_ROOT / "test-results" / "duration-log.jsonl"

MAX_SAMPLES = 5
REL_THRESHOLD = 1.5
ABS_SLACK_S = 10.0

# H4 (harness-standards.md) — per-tier duration ceilings. Declared here, beside
# the drift-flag thresholds above, as the one place both this module's
# reporting and any future enforcing gate read the value (I6). Matches the
# standard's own defaults (60s live / 30s other) — see harness-design.md §9a.
#
# gts-u6ew.3 / plan §2b: this module stays report-only by contract ("nothing
# here can fail or skip a test" — see module docstring). `over_ceiling` is a
# verdict on the record and terminal line only, exactly like `flagged` above.
# Turning an over-ceiling verdict into an actual gate failure is deliberately
# left to a separate, later gate (recommendation (a) of the plan's three
# options) — see docs/atdd/harness-design.md §9a's `H4` row for the resolution
# note. Do not add a `pytest.fail`/`skip` call anywhere in this module.
CEILING_LIVE_S = 60.0
CEILING_OTHER_S = 30.0

# H7 (harness-standards.md) — the bounded HTTP retry policy's numbers,
# co-located here with the H4 ceiling above rather than living as per-call
# transport constants inside scn/session.py's _http_post (I6: one place a
# harness-level policy's numbers live). scn/session.py imports these directly
# and is the only site that reads them for retry/backoff timing; this module
# stays their sole declaration.
#
# gts-u6ew.7 / plan R4: unchanged in value from before the move — 5 attempts,
# exponential backoff from a 3s base (3s, 6s, 12s, 24s) — see
# scn/session.py::_http_post's docstring for the incident history behind
# these numbers (gts-f3me.4, gts-f3me.5).
HTTP_POST_MAX_ATTEMPTS = 5
HTTP_POST_RETRY_DELAY_S = 3


def load_baseline(path: Path = BASELINE_PATH) -> dict:
    """Returns {} on missing or corrupt file — a broken/absent baseline is a
    bootstrap condition, never a hard error (this is observability, not a
    gate)."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_baseline(baseline: dict, path: Path = BASELINE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(baseline, indent=2, sort_keys=True))
    tmp.replace(path)


def update_baseline(baseline: dict, nodeid: str, duration_s: float,
                     max_samples: int = MAX_SAMPLES) -> dict:
    """Returns a NEW baseline dict with nodeid's rolling sample window and
    median updated. Does not mutate the input (safe to call speculatively)."""
    updated = dict(baseline)
    entry = dict(updated.get(nodeid, {}))
    samples = list(entry.get("samples", [])) + [duration_s]
    samples = samples[-max_samples:]
    entry["samples"] = samples
    entry["median_s"] = statistics.median(samples)
    updated[nodeid] = entry
    return updated


def evaluate_flag(duration_s: float, baseline_s: Optional[float],
                   rel_threshold: float = REL_THRESHOLD,
                   abs_slack_s: float = ABS_SLACK_S) -> bool:
    """Automated slow-test decision — no human/LLM judgment required.

    Flags only when duration exceeds baseline by BOTH a relative margin and
    an absolute floor, so a trivial sub-second test doubling in duration
    doesn't generate noise, while a real regression on a long test still
    fires. `None` baseline means "no prior sample yet" (bootstrap) — never
    flagged.
    """
    if baseline_s is None:
        return False
    return duration_s > baseline_s * rel_threshold and duration_s > baseline_s + abs_slack_s


def ceiling_for(is_live: bool, live_ceiling_s: float = CEILING_LIVE_S,
                 other_ceiling_s: float = CEILING_OTHER_S) -> float:
    """The H4 ceiling that applies to a test, by tier."""
    return live_ceiling_s if is_live else other_ceiling_s


def build_record(*, run_id: str, index: int, total: int, nodeid: str,
                  outcome: str, setup_s: float, call_s: float, teardown_s: float,
                  baseline_s: Optional[float], is_live: bool = False,
                  outcome_class: Optional[str] = None,
                  attempts: Optional[int] = None) -> dict:
    """Build one per-test JSONL trend record.

    outcome_class (H6, gts-u6ew.6): PASS / ASSERTION_FAILURE / BOUNDARY_FAULT
    from scn.outcomes.classify(), read off the test's `outcome_class`
    user_property (conftest.py's pytest_runtest_makereport hook). None when
    the caller has no classification to report (e.g. a harness self-test
    with no request= — never coerced to a guess).

    attempts (H7, gts-u6ew.7): the sum of every `http.attempts` user_property
    the test's HTTP calls recorded (scn.session._http_post's on_attempts
    callback) — how many attempts this test's HTTP traffic actually took,
    across every call, not just whether a retry happened. None when the test
    made no HTTP calls through that path.
    """
    total_s = round(setup_s + call_s + teardown_s, 4)
    flagged = evaluate_flag(total_s, baseline_s)
    pct_over = round((total_s - baseline_s) / baseline_s * 100, 1) if baseline_s else None
    ceiling_s = ceiling_for(is_live)
    over_ceiling = total_s > ceiling_s
    return {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "run_id": run_id,
        "index": index,
        "total": total,
        "nodeid": nodeid,
        "outcome": outcome,
        "setup_s": round(setup_s, 4),
        "call_s": round(call_s, 4),
        "teardown_s": round(teardown_s, 4),
        "total_s": total_s,
        "baseline_s": baseline_s,
        "pct_over": pct_over,
        "flagged": flagged,
        "is_live": is_live,
        "ceiling_s": ceiling_s,
        "over_ceiling": over_ceiling,
        "outcome_class": outcome_class,
        "attempts": attempts,
    }


def append_jsonl(record: dict, path: Path = LOG_PATH) -> None:
    """Appends one line and flushes+fsyncs before returning (AC4) so a tool
    tailing this file mid-run sees each test as it completes, not only at
    process exit. Opens/closes per call rather than keeping a long-lived
    handle — cheap at this suite's scale and avoids block-buffering by
    construction rather than relying on buffering-mode flags."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass


def format_start_line(index: int, total: int, nodeid: str) -> str:
    return f"[{index}/{total}] START  {nodeid}"


def summarize_run(records: list) -> dict:
    """H8: execution failure rate, failed-wall-time share, and boundary-fault
    share — the numbers that say whether a red run means "we broke something"
    or "the platform was down" (gts-u6ew.8, plan R5).

    Pure aggregation over the records this run's `pytest_runtest_logreport`
    hook already writes to duration-log.jsonl (build_record's shape) — the
    one owning helper (I12), so pytest_sessionfinish only has to call this
    and format the result, not re-derive the counting logic. Computed over
    whatever `records` the caller passes (conftest.py filters to the current
    run_id before calling this, so a run's own summary isn't diluted by
    prior runs' history in the same file).

    `outcome` values follow pytest's own vocabulary: "failed" (assertion or
    boundary fault), "passed", "skipped". Boundary-fault detection reads each
    record's `outcome_class` (H6) — a record with no classification (None,
    e.g. a harness self-test with no request=) counts toward the failure rate
    like any other failed outcome, but never toward the boundary-fault share,
    since "unclassified" and "boundary fault" are not the same claim.

    Returns a dict of counts/rates; every rate is `0.0` (not NaN/None) on an
    empty or all-passing input, and `None` for the two "boundary fault"
    fields only when the input is empty (no denominator to report a rate
    against) — always a number the caller can print with no NaN handling
    once at least one record exists.
    """
    n = len(records)
    if n == 0:
        return {
            "executions": 0,
            "failed": 0,
            "execution_failure_rate": 0.0,
            "wall_time_s": 0.0,
            "failed_wall_time_s": 0.0,
            "failed_wall_time_share": 0.0,
            "boundary_faults": None,
            "boundary_fault_share_of_failures": None,
        }
    failed = [r for r in records if r.get("outcome") == "failed"]
    wall_time_s = sum(r.get("total_s", 0.0) for r in records)
    failed_wall_time_s = sum(r.get("total_s", 0.0) for r in failed)
    boundary_faults = [r for r in failed if r.get("outcome_class") == "BOUNDARY_FAULT"]
    return {
        "executions": n,
        "failed": len(failed),
        "execution_failure_rate": round(len(failed) / n, 4),
        "wall_time_s": round(wall_time_s, 2),
        "failed_wall_time_s": round(failed_wall_time_s, 2),
        "failed_wall_time_share": (
            round(failed_wall_time_s / wall_time_s, 4) if wall_time_s else 0.0
        ),
        "boundary_faults": len(boundary_faults),
        "boundary_fault_share_of_failures": (
            round(len(boundary_faults) / len(failed), 4) if failed else 0.0
        ),
    }


def format_run_summary(summary: dict) -> str:
    """One terminal line for summarize_run's result (H8), emitted at
    pytest_sessionfinish so the numbers are visible every run instead of
    requiring an offline diagnostics pass over duration-log.jsonl."""
    if summary["executions"] == 0:
        return "H8 boundary-fault summary: no executions recorded this run"
    bf = summary["boundary_faults"]
    bf_part = (
        f", {bf} boundary fault(s) ({summary['boundary_fault_share_of_failures']:.1%} of failures)"
        if bf is not None else ""
    )
    return (
        f"H8 boundary-fault summary: {summary['failed']}/{summary['executions']} executions failed "
        f"({summary['execution_failure_rate']:.1%}); "
        f"{summary['failed_wall_time_s']:.1f}s of {summary['wall_time_s']:.1f}s wall time "
        f"({summary['failed_wall_time_share']:.1%}) spent failing{bf_part}"
    )


def format_finish_line(record: dict) -> str:
    if record["baseline_s"] is None:
        baseline_part = "baseline=n/a (bootstrap)"
    else:
        sign = "+" if record["pct_over"] >= 0 else ""
        baseline_part = f"baseline={record['baseline_s']:.2f}s ({sign}{record['pct_over']:.0f}%)"
    flag_part = " ⚠ SLOW" if record["flagged"] else ""
    ceiling_part = (
        f" ⚠ OVER-CEILING ({record['ceiling_s']:.0f}s {'live' if record['is_live'] else 'other'})"
        if record.get("over_ceiling") else ""
    )
    return (
        f"[{record['index']}/{record['total']}] FINISH {record['nodeid']} "
        f"{record['outcome'].upper()} total={record['total_s']:.2f}s "
        f"(setup={record['setup_s']:.2f}s call={record['call_s']:.2f}s "
        f"teardown={record['teardown_s']:.2f}s) {baseline_part}{flag_part}{ceiling_part}"
    )
