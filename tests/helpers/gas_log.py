"""Poll the Drive-mapped GAS log directory for structured log entries (NDJSON)."""
import json
import os
import pathlib
import sys
import time


def clear_logs(log_dir: str):
    if log_dir and os.path.isdir(log_dir):
        for f in pathlib.Path(log_dir).glob("*.log"):
            f.unlink(missing_ok=True)


def _scan_logs(log_dir: str, match_fn):
    """Return the first matching entry from log_dir, or None."""
    for f in sorted(pathlib.Path(log_dir).glob("*.log")):
        try:
            for line in f.read_text().splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                if match_fn(entry):
                    return entry
        except (json.JSONDecodeError, OSError):
            pass
    return None


def wait_for_log(log_dir: str, match_fn, timeout_s: float = 60.0, poll_s: float = 0.5):
    """Block until an NDJSON log entry matching match_fn is found, or raise TimeoutError.

    In interactive sessions (TTY), prompts the user to continue waiting after each
    timeout period instead of raising immediately.
    """
    interactive = sys.stdin.isatty()

    while True:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            entry = _scan_logs(log_dir, match_fn)
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
