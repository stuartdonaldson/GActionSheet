"""
Unit tests for scn/reporter.py — Reporter (GTaskSheet-80mo.16).

The Reporter is the single owner of observability emission: per-step trace
written to .trace.jsonl + .trace.log (always), streamed to a console sink when
enabled, and JUnit user_properties (elapsed.*/ac.*/ep.*) appended when a pytest
request is present. These tests verify Python logic only — no GAS/network.
"""
import contextlib
import io
import json
from unittest.mock import MagicMock

import allure
import pytest

from scn.reporter import NullReporter, Reporter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeNode:
    def __init__(self):
        self.user_properties = []


class _FakeRequest:
    def __init__(self, name="test_demo"):
        self.node = _FakeNode()
        self.node.name = name


def _make(tmp_path, *, request=None, console=None, clock=None):
    times = iter(clock) if clock is not None else None
    clk = (lambda: next(times)) if times is not None else (lambda: 0.0)
    return Reporter(
        start_time=0.0,
        request=request,
        run_dir=str(tmp_path),
        node_name="test_demo",
        console=console,
        clock=clk,
    )


def _read_jsonl(rep):
    return [json.loads(l) for l in rep.jsonl_path.read_text().splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# event() — schema + sinks
# ---------------------------------------------------------------------------

def test_event_writes_jsonl_line_with_schema(tmp_path):
    rep = _make(tmp_path, clock=[3.5])
    rep.event("ACT", "sync_document", detail="x6", result="OK")
    rep.close()

    rows = _read_jsonl(rep)
    assert len(rows) == 1
    r = rows[0]
    # schema keys present
    for k in ("seq", "t_wall", "t_elapsed", "phase", "name", "result"):
        assert k in r, f"missing {k}"
    assert r["phase"] == "ACT"
    assert r["name"] == "sync_document"
    assert r["detail"] == "x6"
    assert r["result"] == "OK"
    assert r["t_elapsed"] == 3.5


def test_event_writes_human_log_line(tmp_path):
    rep = _make(tmp_path, clock=[1.0])
    rep.event("ACT", "append_paragraph", detail="AI-1: ...")
    rep.close()
    text = rep.log_path.read_text()
    assert "ACT" in text and "append_paragraph" in text


def test_seq_increments_per_event(tmp_path):
    rep = _make(tmp_path, clock=[0.1, 0.2, 0.3])
    rep.event("ACT", "a")
    rep.event("ACT", "b")
    rep.event("ACT", "c")
    rep.close()
    seqs = [r["seq"] for r in _read_jsonl(rep)]
    assert seqs == [1, 2, 3]


# ---------------------------------------------------------------------------
# console sink — only when a stream is provided
# ---------------------------------------------------------------------------

def test_console_stream_receives_line_when_enabled(tmp_path):
    buf = io.StringIO()
    rep = _make(tmp_path, console=buf, clock=[2.0])
    rep.event("CHECKPOINT", "INTEGRITY", result="OK")
    rep.close()
    assert "INTEGRITY" in buf.getvalue()


def test_no_console_when_disabled(tmp_path):
    rep = _make(tmp_path, console=None, clock=[2.0])
    rep.event("ACT", "silent")
    rep.close()
    # nothing to assert on a missing stream; ensure file still written
    assert len(_read_jsonl(rep)) == 1


# ---------------------------------------------------------------------------
# step() — timing + failure capture
# ---------------------------------------------------------------------------

def test_step_emits_duration(tmp_path):
    # clock consumed: step-start, step-end
    rep = _make(tmp_path, clock=[10.0, 11.5])
    with rep.step("ACT", "sync"):
        pass
    rep.close()
    rows = _read_jsonl(rep)
    end = [r for r in rows if r["name"] == "sync"][-1]
    assert end["dur_s"] == pytest.approx(1.5)
    assert end["result"] == "OK"


def test_step_marks_fail_and_reraises(tmp_path):
    rep = _make(tmp_path, clock=[10.0, 10.4])
    with pytest.raises(ValueError):
        with rep.step("UIACT", "create_action"):
            raise ValueError("boom")
    rep.close()
    rows = _read_jsonl(rep)
    fail = [r for r in rows if r["result"] == "FAIL"]
    assert fail, "expected a FAIL event recorded before re-raise"
    assert fail[-1]["name"] == "create_action"


# ---------------------------------------------------------------------------
# step() — Allure step wrapping (R6, GTaskSheet-16kh)
# ---------------------------------------------------------------------------

def test_step_wraps_block_in_allure_step(tmp_path, monkeypatch):
    calls = []

    @contextlib.contextmanager
    def fake_allure_step(title):
        calls.append(title)
        yield

    monkeypatch.setattr("scn.reporter.allure.step", fake_allure_step)
    rep = _make(tmp_path, clock=[0.0, 0.1])
    with rep.step("ACT", "sync"):
        pass
    rep.close()
    assert calls == ["ACT sync"]


def test_step_wraps_block_in_allure_step_with_detail(tmp_path, monkeypatch):
    calls = []

    @contextlib.contextmanager
    def fake_allure_step(title):
        calls.append(title)
        yield

    monkeypatch.setattr("scn.reporter.allure.step", fake_allure_step)
    rep = _make(tmp_path, clock=[0.0, 0.1])
    with rep.step("ACT", "edit_sheet", "AI-1 status=Open"):
        pass
    rep.close()
    assert calls == ["ACT edit_sheet AI-1 status=Open"]


# ---------------------------------------------------------------------------
# allure_step() / attach_screenshot() (R6, GTaskSheet-16kh)
# ---------------------------------------------------------------------------

def test_allure_step_delegates_to_allure(tmp_path, monkeypatch):
    sentinel = object()
    calls = []

    def fake_allure_step(title):
        calls.append(title)
        return sentinel

    monkeypatch.setattr("scn.reporter.allure.step", fake_allure_step)
    rep = _make(tmp_path, clock=[0.0])
    result = rep.allure_step("[journey sync-create AC1] DOC")
    rep.close()
    assert calls == ["[journey sync-create AC1] DOC"]
    assert result is sentinel


def test_attach_screenshot_calls_allure_attach(tmp_path, monkeypatch):
    attached = []

    def fake_attach(body, name=None, attachment_type=None):
        attached.append((body, name, attachment_type))

    monkeypatch.setattr("scn.reporter.allure.attach", fake_attach)
    rep = _make(tmp_path, clock=[0.0])
    page = MagicMock()
    page.screenshot.return_value = b"PNG-BYTES"
    rep.attach_screenshot(page, name="[journey sync-create AC1] UI FAIL")
    rep.close()
    assert attached == [
        (b"PNG-BYTES", "[journey sync-create AC1] UI FAIL", allure.attachment_type.PNG)
    ]


def test_attach_screenshot_swallows_exception(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("screenshot failed")

    page = MagicMock()
    page.screenshot.side_effect = boom
    rep = _make(tmp_path, clock=[0.0])
    rep.attach_screenshot(page, name="x")  # must not raise
    rep.close()


def test_attach_screenshot_noop_when_page_none(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("scn.reporter.allure.attach", lambda *a, **k: calls.append((a, k)))
    rep = _make(tmp_path, clock=[0.0])
    rep.attach_screenshot(None, name="x")
    rep.close()
    assert calls == []


# ---------------------------------------------------------------------------
# NullReporter — allure_step/attach_screenshot no-ops (R6, GTaskSheet-16kh)
# ---------------------------------------------------------------------------

def test_null_reporter_allure_step_is_usable_context_manager():
    rep = NullReporter()
    with rep.allure_step("anything"):
        pass


def test_null_reporter_attach_screenshot_is_noop():
    rep = NullReporter()
    rep.attach_screenshot(None, name="x")
    rep.attach_screenshot(MagicMock(), name="x")


# ---------------------------------------------------------------------------
# JUnit emission — format preserved for scripts/check_coverage.py
# ---------------------------------------------------------------------------

def test_junit_property_appended_when_request_present(tmp_path):
    req = _FakeRequest()
    rep = _make(tmp_path, request=req, clock=[0.0])
    rep.junit("ac.[journey sync-create].DOC", "PASS")
    assert ("ac.[journey sync-create].DOC", "PASS") in req.node.user_properties


def test_junit_noop_without_request(tmp_path):
    rep = _make(tmp_path, request=None, clock=[0.0])
    # must not raise
    rep.junit("ac.x.DOC", "PASS")


def test_elapsed_property_format_preserved(tmp_path):
    req = _FakeRequest()
    rep = _make(tmp_path, request=req, clock=[4.2])
    rep.elapsed("MARK.act3", junit=True)
    keys = [k for k, _ in req.node.user_properties]
    assert any(k.startswith("elapsed.") and k.endswith(".MARK.act3") for k in keys)
    # zero-padded 2-digit seq, e.g. elapsed.01.MARK.act3
    k = [k for k in keys if k.endswith(".MARK.act3")][0]
    assert k.split(".")[1].isdigit() and len(k.split(".")[1]) == 2
