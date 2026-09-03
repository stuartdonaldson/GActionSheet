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


def build_record(*, run_id: str, index: int, total: int, nodeid: str,
                  outcome: str, setup_s: float, call_s: float, teardown_s: float,
                  baseline_s: Optional[float]) -> dict:
    total_s = round(setup_s + call_s + teardown_s, 4)
    flagged = evaluate_flag(total_s, baseline_s)
    pct_over = round((total_s - baseline_s) / baseline_s * 100, 1) if baseline_s else None
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


def format_finish_line(record: dict) -> str:
    if record["baseline_s"] is None:
        baseline_part = "baseline=n/a (bootstrap)"
    else:
        sign = "+" if record["pct_over"] >= 0 else ""
        baseline_part = f"baseline={record['baseline_s']:.2f}s ({sign}{record['pct_over']:.0f}%)"
    flag_part = " ⚠ SLOW" if record["flagged"] else ""
    return (
        f"[{record['index']}/{record['total']}] FINISH {record['nodeid']} "
        f"{record['outcome'].upper()} total={record['total_s']:.2f}s "
        f"(setup={record['setup_s']:.2f}s call={record['call_s']:.2f}s "
        f"teardown={record['teardown_s']:.2f}s) {baseline_part}{flag_part}"
    )
