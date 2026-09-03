"""scripts/system_metrics.py — lightweight CPU/memory sampler for full-suite
pytest sweeps (gts-l6h0).

gts-f3me.6 root-caused a 20-700% baseline blowup in gas-test3.log to
test-runner-side contention (other Claude Code sessions running concurrently
on the same machine), not a GAS-backend or Google-infra slowdown -- but that
conclusion had to be reasoned from wall-clock deltas alone, with no CPU/
memory record for the run window. This module gives a future run that
record.

Reads /proc/stat and /proc/meminfo directly (Linux-only; this project's dev
env is WSL2) rather than adding psutil as a new dependency. Used by
scripts/run_test_exec.py, which starts a Sampler alongside the wrapped
pytest subprocess and stops it when the subprocess exits.
"""
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

_PROC_STAT = "/proc/stat"
_PROC_MEMINFO = "/proc/meminfo"


def read_cpu_ticks(stat_path=_PROC_STAT):
    """Return (idle_ticks, total_ticks) from the aggregate 'cpu' line of
    /proc/stat (man proc(5)): user nice system idle iowait irq softirq ..."""
    with open(stat_path) as f:
        line = f.readline()
    fields = [int(x) for x in line.split()[1:]]
    idle = fields[3] + (fields[4] if len(fields) > 4 else 0)  # idle + iowait
    total = sum(fields)
    return idle, total


def cpu_pct(prev, curr):
    """Busy CPU percent over the interval between two read_cpu_ticks()
    samples. Clamped to [0, 100] to stay sane across a counter reset."""
    idle_delta = curr[0] - prev[0]
    total_delta = curr[1] - prev[1]
    if total_delta <= 0:
        return 0.0
    pct = 100.0 * (1.0 - (idle_delta / total_delta))
    return max(0.0, min(100.0, pct))


def read_mem_pct(meminfo_path=_PROC_MEMINFO):
    """Memory-used percent, using MemAvailable (falls back to MemFree if a
    kernel doesn't report it)."""
    values = {}
    with open(meminfo_path) as f:
        for line in f:
            key, _, rest = line.partition(":")
            parts = rest.strip().split()
            if parts:
                values[key] = int(parts[0])
    total = values.get("MemTotal", 0)
    if total <= 0:
        return 0.0
    available = values.get("MemAvailable", values.get("MemFree", 0))
    return max(0.0, min(100.0, 100.0 * (1.0 - (available / total))))


class Sampler:
    """Background thread that samples CPU%/mem%/loadavg at a fixed interval
    and appends each sample as one JSON line to `out_path`, for the
    duration of a wrapped subprocess. Negligible overhead: two small file
    reads per interval, no polling loop tighter than `interval_s`."""

    def __init__(self, out_path, interval_s=30.0):
        self._out_path = Path(out_path)
        self._interval_s = interval_s
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._out_path.parent.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval_s + 5)

    def _run(self):
        start = time.monotonic()
        try:
            prev = read_cpu_ticks()
        except OSError:
            return  # /proc/stat unavailable (non-Linux) -- sampler is a no-op
        with open(self._out_path, "a", encoding="utf-8") as out:
            while not self._stop.wait(self._interval_s):
                try:
                    curr = read_cpu_ticks()
                    mem = read_mem_pct()
                    load = list(os.getloadavg())
                except Exception:
                    break  # e.g. /proc unavailable mid-run -- stop quietly, don't crash the thread
                sample = {
                    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "elapsed_s": round(time.monotonic() - start, 1),
                    "cpu_pct": round(cpu_pct(prev, curr), 1),
                    "mem_pct": round(mem, 1),
                    "loadavg": load,
                }
                out.write(json.dumps(sample) + "\n")
                out.flush()
                prev = curr
