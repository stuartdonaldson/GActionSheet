"""Poll the Drive-mapped GAS log directory for structured log entries (NDJSON)."""
import json
import os
import pathlib
import shutil
import sys
import time
from datetime import datetime, timezone


def clear_logs(log_dir: str) -> float:
    """Move all .log files in log_dir into log_dir/archive/<timestamp>/ and
    return a fence timestamp (epoch seconds).

    Pass the returned value to wait_for_log as ``after`` to ignore stale entries
    written by a previous or concurrent GAS run.

    Archiving (not deleting) preserves historical runs for trend analysis.
    The fence is set 10 s before now to absorb GAS-server / local clock skew.
    """
    fence = time.time() - 10.0
    if not (log_dir and os.path.isdir(log_dir)):
        return fence
    logs = list(pathlib.Path(log_dir).glob("*.log"))
    if not logs:
        return fence
    ts = time.strftime("%Y-%m-%dT%H-%M-%S")
    repo_root = pathlib.Path(__file__).parent.parent.parent
    archive_dir = repo_root / "test-results" / "gas-logs" / ts
    archive_dir.mkdir(parents=True, exist_ok=True)
    for f in logs:
        shutil.copy2(f, archive_dir / f.name)
        f.unlink()
    return fence


def _scan_logs(log_dir: str, match_fn, after: float = 0.0):
    """Return the first matching entry from log_dir, or None.

    Entries whose ``ts`` predates *after* (epoch seconds) are skipped.
    """
    for f in sorted(pathlib.Path(log_dir).glob("*.log")):
        try:
            for line in f.read_text().splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                if after and entry.get("ts"):
                    try:
                        ts_s = datetime.fromisoformat(
                            entry["ts"].replace("Z", "+00:00")
                        ).timestamp()
                        if ts_s < after:
                            continue
                    except (ValueError, OSError):
                        pass
                if match_fn(entry):
                    return entry
        except (json.JSONDecodeError, OSError):
            pass
    return None


def wait_for_log(
    log_dir: str,
    match_fn,
    timeout_s: float = 60.0,
    poll_s: float = 0.5,
    after: float = 0.0,
):
    """Block until an NDJSON log entry matching match_fn is found, or raise TimeoutError.

    Parameters
    ----------
    after:
        Epoch-seconds fence (return value of clear_logs). Entries whose ``ts``
        predates this value are skipped, preventing stale entries from a
        concurrent GAS run from satisfying the predicate.

    In interactive sessions (TTY), prompts the user to continue waiting after each
    timeout period instead of raising immediately.
    """
    interactive = sys.stdin.isatty()

    while True:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            entry = _scan_logs(log_dir, match_fn, after=after)
            if entry:
                return entry
            time.sleep(poll_s)

        if not interactive:
            raise TimeoutError(f"No matching log entry within {timeout_s}s")

        print(f"\n[wait_for_log] No log entry after {timeout_s:.0f}s. "
              "Press Enter to keep waiting, or Ctrl-C to abort.")
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            raise TimeoutError(f"Aborted by user after {timeout_s}s")
