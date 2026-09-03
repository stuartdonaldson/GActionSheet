"""Unit tests for scripts/system_metrics.py (gts-l6h0).

gts-f3me.6 root-caused a 20-700% baseline blowup to host-side contention
(concurrent sessions on the same machine) rather than a GAS-backend or
Google-infra slowdown, but that conclusion was reached from wall-clock
deltas alone -- there was no CPU/memory record for the run window. These
tests cover the pure parsing/math (read_cpu_ticks, cpu_pct, read_mem_pct)
against fixture /proc-style files, and the Sampler background thread's
JSONL sidecar output, without touching the real /proc filesystem for the
deterministic cases.
"""
import itertools
import json
import time

from scripts import system_metrics as sm

import pytest

# gts-aqpk: fast/local tier -- this module makes no live GAS/Google round trip
# (verified offline with sockets blocked). See docs/OPERATIONS.md "Test tiers".
pytestmark = pytest.mark.no_live_session


def _write(path, content):
    path.write_text(content)
    return path


def test_read_cpu_ticks_parses_proc_stat_line(tmp_path):
    # user nice system idle iowait irq softirq steal guest guest_nice
    stat = _write(tmp_path / "stat", "cpu  100 0 50 800 20 0 0 0 0 0\nother lines ignored\n")
    idle, total = sm.read_cpu_ticks(str(stat))
    assert idle == 800 + 20  # idle + iowait
    assert total == 100 + 0 + 50 + 800 + 20


def test_cpu_pct_computes_busy_percent_from_delta():
    prev = (800, 970)  # idle=800, total=970
    curr = (850, 1070)  # +100 total, +50 idle -> 50 busy / 100 total = 50%
    assert sm.cpu_pct(prev, curr) == 50.0


def test_cpu_pct_returns_zero_when_total_delta_non_positive():
    prev = (800, 1000)
    curr = (800, 1000)  # no time elapsed between samples
    assert sm.cpu_pct(prev, curr) == 0.0


def test_cpu_pct_clamps_to_0_100_range():
    # Pathological input (e.g. counter reset) must not yield out-of-range %.
    prev = (0, 1000)
    curr = (2000, 1100)  # idle_delta > total_delta
    assert sm.cpu_pct(prev, curr) == 0.0


def test_read_mem_pct_uses_mem_available(tmp_path):
    meminfo = _write(tmp_path / "meminfo", (
        "MemTotal:       10000 kB\n"
        "MemFree:         1000 kB\n"
        "MemAvailable:    4000 kB\n"
    ))
    # used = 1 - 4000/10000 = 60%
    assert sm.read_mem_pct(str(meminfo)) == 60.0


def test_read_mem_pct_falls_back_to_memfree_when_no_memavailable(tmp_path):
    meminfo = _write(tmp_path / "meminfo", (
        "MemTotal:       10000 kB\n"
        "MemFree:         2500 kB\n"
    ))
    # used = 1 - 2500/10000 = 75%
    assert sm.read_mem_pct(str(meminfo)) == 75.0


def test_sampler_writes_periodic_jsonl_samples(tmp_path, monkeypatch):
    """Sampler background thread writes >=1 JSONL sample line with the
    expected fields, using a short interval so the test stays fast."""
    ticks = itertools.cycle([(0, 100), (10, 200), (25, 300)])
    monkeypatch.setattr(sm, "read_cpu_ticks", lambda *a, **k: next(ticks))
    monkeypatch.setattr(sm, "read_mem_pct", lambda *a, **k: 42.0)

    out_path = tmp_path / "system-metrics.jsonl"
    sampler = sm.Sampler(out_path, interval_s=0.05)
    sampler.start()
    time.sleep(0.18)
    sampler.stop()

    lines = out_path.read_text().strip().splitlines()
    assert len(lines) >= 1
    row = json.loads(lines[0])
    assert set(["ts", "elapsed_s", "cpu_pct", "mem_pct", "loadavg"]) <= set(row.keys())
    assert row["mem_pct"] == 42.0
