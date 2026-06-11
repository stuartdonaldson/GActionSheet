"""
scn/reporter.py — the single owner of test-execution observability.

One Reporter per ScenarioSession. It is the ONE place that emits:
  * the per-step trace, always written to two sibling files under
    test-results/runs/:  <node>_<utc>.trace.jsonl  (structured, for tooling)
    and  <node>_<utc>.trace.log  (human-readable, for scanning);
  * a live console stream of the same human lines when SCN_TRACE=1 (so a hung
    run shows the step it is stuck on);
  * the JUnit user_properties (elapsed.* / ac.* / ep.*) — routed THROUGH here so
    there is a single emission path, not the two duplicated blocks that used to
    live in ScenarioSession.mark() and .checkpoint() (GTaskSheet-80mo.16, R1).

Event schema (one JSONL object per line):
    {seq, t_wall, t_elapsed, phase, name, detail, surface, checking, result, dur_s}
    phase ∈ ACT | QUERY | UIACT | CHECK | CHECKPOINT | MARK | MONITOR | HTTP
    result ∈ OK | PASS | WARN | FAIL

Pure-Python; no GAS/network. Network-free so it is unit-testable in isolation.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import allure

_UNSET = object()

# Phases (documented for callers; not enforced — kept open for new surfaces).
PHASES = ("ACT", "QUERY", "UIACT", "CHECK", "CHECKPOINT", "MARK", "MONITOR", "HTTP")


def _slug(text: str) -> str:
    """Filesystem-safe slug for a pytest node name."""
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", text or "scn").strip("-")
    return s or "scn"


def _console_from_env(console):
    """Resolve the console sink: explicit value wins; else SCN_TRACE=1 → stdout."""
    if console is not _UNSET:
        return console
    return sys.stdout if os.environ.get("SCN_TRACE") == "1" else None


class Reporter:
    def __init__(
        self,
        *,
        start_time: float,
        request=None,
        run_dir: str | None = None,
        node_name: str | None = None,
        console=_UNSET,
        clock=time.monotonic,
    ) -> None:
        self._start = start_time
        self._request = request
        self._clock = clock
        self._console = _console_from_env(console)
        self._seq = 0          # event sequence (every event())
        self._elapsed_seq = 0  # elapsed.* property sequence (mark()+checkpoint())

        name = node_name or (
            getattr(getattr(request, "node", None), "name", None) or "scn"
        )
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        # SCN_RUN_DIR (set by scripts/run_test_exec.py) redirects trace files into a
        # TestExec-NNN/ folder for that invocation; default unchanged otherwise (np7s).
        base = Path(run_dir or os.environ.get("SCN_RUN_DIR", "test-results/runs"))
        base.mkdir(parents=True, exist_ok=True)
        stem = f"{_slug(name)}_{ts}.trace"
        self.jsonl_path = base / f"{stem}.jsonl"
        self.log_path = base / f"{stem}.log"
        # Line-buffered so a killed/hung run still leaves a complete trail.
        self._jsonl = open(self.jsonl_path, "w", buffering=1, encoding="utf-8")
        self._log = open(self.log_path, "w", buffering=1, encoding="utf-8")

    # ------------------------------------------------------------------
    # core emission
    # ------------------------------------------------------------------

    def _now_elapsed(self) -> float:
        return round(self._clock() - self._start, 3)

    def event(
        self,
        phase: str,
        name: str,
        *,
        detail: str = "",
        surface=None,
        checking: str | None = None,
        result: str = "OK",
        dur_s: float | None = None,
        _t_elapsed: float | None = None,
    ) -> None:
        """Emit one trace event to all sinks (jsonl + log + optional console)."""
        self._seq += 1
        t_elapsed = self._now_elapsed() if _t_elapsed is None else _t_elapsed
        rec = {
            "seq": self._seq,
            "t_wall": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "t_elapsed": t_elapsed,
            "phase": phase,
            "name": name,
            "detail": detail,
            "surface": (surface.value if hasattr(surface, "value") else surface),
            "checking": checking,
            "result": result,
            "dur_s": (round(dur_s, 3) if dur_s is not None else None),
        }
        self._jsonl.write(json.dumps(rec, ensure_ascii=False) + "\n")
        line = self._format(rec)
        self._log.write(line + "\n")
        if self._console is not None:
            self._console.write(line + "\n")
            try:
                self._console.flush()
            except Exception:
                pass

    @staticmethod
    def _format(rec: dict) -> str:
        """Aligned human line, e.g.
        14.10s ACT   sync_document  detail=x6                 (1.83s) OK
        """
        dur = f"({rec['dur_s']:.2f}s)" if rec.get("dur_s") is not None else ""
        bits = []
        if rec.get("checking"):
            bits.append(f"check={rec['checking']}")
        elif rec.get("detail"):
            bits.append(str(rec["detail"]))
        if rec.get("surface"):
            bits.append(f"[{rec['surface']}]")
        tail = "  ".join(bits)
        res = rec.get("result", "OK")
        res_str = "" if res == "OK" else f" {res}"
        return (
            f"{rec['t_elapsed']:7.2f}s {rec['phase']:<10} "
            f"{rec['name']:<32} {tail:<40} {dur:>8}{res_str}"
        ).rstrip()

    # ------------------------------------------------------------------
    # step() — time a block, capture failures
    # ------------------------------------------------------------------

    @contextlib.contextmanager
    def step(self, phase: str, name: str, detail: str = "", *, surface=None):
        """Time the wrapped block; emit an end event with dur_s.

        On exception, emit a result=FAIL event (detail = exception message) BEFORE
        re-raising, so the trace ends on the real step, not a bare traceback.

        The block also runs inside an Allure step named "<phase> <name>[ <detail>]"
        (R6, GTaskSheet-16kh) — every ACT/QUERY/UIACT/CHECK/CHECKPOINT call routed
        through step() gets a uniform Allure step for free. allure.step() is a
        no-op outside an active allure-pytest run.
        """
        title = f"{phase} {name}" + (f" {detail}" if detail else "")
        start = self._now_elapsed()
        with allure.step(title):
            try:
                yield
            except BaseException as exc:  # noqa: BLE001 — emit then re-raise unchanged
                end = self._now_elapsed()
                self.event(
                    phase, name,
                    detail=(detail or str(exc))[:200],
                    surface=surface, result="FAIL",
                    dur_s=end - start, _t_elapsed=end,
                )
                raise
            else:
                end = self._now_elapsed()
                self.event(
                    phase, name, detail=detail, surface=surface,
                    result="OK", dur_s=end - start, _t_elapsed=end,
                )

    def allure_step(self, name: str):
        """Return an Allure step context manager named `name` (R6, GTaskSheet-16kh).

        Used by engine.drain() for per-surface CHECK granularity below the
        coarser step() wrapping in session.checkpoint(). No-op outside an active
        allure-pytest run.
        """
        return allure.step(name)

    def attach_screenshot(self, page, name: str) -> None:
        """Attach a PNG screenshot of `page` to the Allure report (R6, GTaskSheet-16kh).

        No-op if `page` is None. Screenshot failures are swallowed so they never
        mask the original AssertionError they're attached alongside.
        """
        if page is None:
            return
        try:
            allure.attach(page.screenshot(), name=name, attachment_type=allure.attachment_type.PNG)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # JUnit user_properties — single emission path (R1)
    # ------------------------------------------------------------------

    def junit(self, key: str, value: str) -> None:
        """Append a (key, value) to the pytest node's user_properties (no-op if no request)."""
        if self._request is not None:
            self._request.node.user_properties.append((key, value))

    def elapsed(self, name: str, *, junit: bool = False) -> float:
        """Record an elapsed.{seq:02d}.{name} milestone; return the elapsed value.

        Format preserved exactly for scripts/check_coverage.py compatibility.
        """
        self._elapsed_seq += 1
        value = self._now_elapsed()
        if junit:
            self.junit(f"elapsed.{self._elapsed_seq:02d}.{name}", f"{value:.2f}")
        return value

    # ------------------------------------------------------------------
    def close(self) -> None:
        for fh in (self._jsonl, self._log):
            try:
                fh.close()
            except Exception:
                pass


class NullReporter:
    """No-op reporter used when there is no run context (harness unit tests).

    Mirrors the historical behaviour where mark()/checkpoint() did nothing when
    ScenarioSession had no pytest request — keeps unit runs from writing trace
    files, while the real Reporter is always active for scenario journeys.
    """

    jsonl_path = None
    log_path = None

    def event(self, *a, **k) -> None:  # noqa: D401
        pass

    @contextlib.contextmanager
    def step(self, *a, **k):
        yield

    def junit(self, *a, **k) -> None:
        pass

    def elapsed(self, *a, **k) -> float:
        return 0.0

    @contextlib.contextmanager
    def allure_step(self, name: str):
        yield

    def attach_screenshot(self, page, name: str) -> None:
        pass

    def close(self) -> None:
        pass
