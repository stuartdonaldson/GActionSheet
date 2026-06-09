"""
Unit tests for scn/session.py — ScenarioSession (GTaskSheet-5vwu.7).

Strategy: mock _post (controls all HTTP) and download_docx/download_xlsx
(controls surface bytes). Tests verify Python logic only — no real GAS calls.
"""
from unittest.mock import MagicMock, call, patch

import pytest

from scn.ai import ai
from scn.engine import (
    AUTO,
    INTEGRITY_TARGET,
    CheckpointKind,
    DrainInvariantError,
    Severity,
    Surface,
)
import scn.session as session_mod
from scn.session import FixtureTokenError, ScenarioSession, _row_dict_to_ai, _snapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SETTINGS = {
    "webappTestUrl": "https://example.com/exec",
    "testToken": "tok-abc",
    "testSheetId": "sheet-999",
}

DOC_ID = "doc-111"


def _make_session(**kwargs) -> ScenarioSession:
    defaults = dict(doc_id=DOC_ID, sheet_id="sheet-999", settings=SETTINGS)
    defaults.update(kwargs)
    return ScenarioSession(**defaults)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def _patch_http(monkeypatch, fn):
    """Patch the module-level _http_post used by both new_doc and instance methods."""
    monkeypatch.setattr(session_mod, "_http_post", fn)


def test_new_doc_calls_begin_session(monkeypatch):
    """new_doc posts begin_journey_session and stores returned docId."""
    captured = {}

    def fake_http(url, payload, timeout=360):
        captured["payload"] = payload
        return {"ok": True, "docId": "doc-created", "docName": "Test Doc", "docUrl": "http://x"}

    _patch_http(monkeypatch, fake_http)

    scn = ScenarioSession.new_doc(SETTINGS)
    assert captured["payload"]["action"] == "begin_journey_session"
    assert captured["payload"]["testToken"] == "tok-abc"
    assert scn.doc_id == "doc-created"
    assert scn.sheet_id == "sheet-999"


def test_new_doc_raises_on_missing_doc_id(monkeypatch):
    _patch_http(monkeypatch, lambda url, payload, timeout=360: {"ok": True})
    with pytest.raises(RuntimeError, match="docId"):
        ScenarioSession.new_doc(SETTINGS)


def test_close_calls_end_session_then_engine_close(monkeypatch):
    """close() posts end_journey_session then calls engine.close()."""
    actions = []

    def fake_http(url, payload, timeout=360):
        actions.append(payload["action"])
        return {"ok": True}

    engine_closed = []

    _patch_http(monkeypatch, fake_http)
    scn = _make_session()
    scn.engine.close = lambda: engine_closed.append(True)

    scn.close()

    assert actions == ["end_journey_session"]
    assert engine_closed == [True]


def test_close_propagates_payload(monkeypatch):
    """close() sends the session's doc_id in the end_journey_session payload."""
    captured = {}

    def fake_http(url, payload, timeout=360):
        captured.update(payload)
        return {"ok": True}

    _patch_http(monkeypatch, fake_http)
    scn = _make_session()
    scn.close()

    assert captured["docId"] == DOC_ID


def test_close_raises_drain_invariant_error_on_nonempty_queue(monkeypatch):
    """close() propagates DrainInvariantError when expectations remain undrained."""
    _patch_http(monkeypatch, lambda url, payload, timeout=360: {"ok": True})

    scn = _make_session()
    a = ai(action="do thing")
    scn.verify(a, on=Surface.SHEET, tag="[uc1 AC1]")

    with pytest.raises(DrainInvariantError):
        scn.close()


# ---------------------------------------------------------------------------
# Acts
# ---------------------------------------------------------------------------

def test_sync_posts_correct_route(monkeypatch):
    captured = {}

    def fake_http(url, payload, timeout=360):
        captured.update(payload)
        # run_fixture returns { tag, data: { synced, docId } }
        return {"tag": "fixture.sync_document", "data": {"synced": True, "docId": DOC_ID}}

    _patch_http(monkeypatch, fake_http)
    scn = _make_session()
    scn.sync()

    assert captured["action"] == "run_fixture"
    assert captured["fixture"] == "sync_document"
    assert captured["testDocId"] == DOC_ID


def test_sync_raises_if_synced_not_true(monkeypatch):
    _patch_http(monkeypatch, lambda url, p, timeout=360: {"tag": "fixture.sync_document", "data": {}})
    scn = _make_session()
    with pytest.raises(RuntimeError, match="sync_document fixture returned unexpected response"):
        scn.sync()


def test_insert_tracker_sets_flag(monkeypatch):
    _patch_http(monkeypatch, lambda url, p, timeout=360: {"ok": True})
    scn = _make_session()
    assert not scn.tracker_present
    scn.insert_tracker()
    assert scn.tracker_present


def test_edit_sheet_constructs_global_id(monkeypatch):
    captured = {}

    def fake_http(url, payload, timeout=360):
        captured.update(payload)
        return {"ok": True, "global_id": "x", "row": {}}

    _patch_http(monkeypatch, fake_http)
    scn = _make_session()
    a = ai(action="edit me", action_id="AI-3")
    scn.edit_sheet(a, status="In Progress")

    assert captured["action"] == "edit_action_row"
    assert captured["global_id"] == f"{DOC_ID}/AI-3"
    assert captured["fields"] == {"status": "In Progress"}


def test_edit_sheet_raises_without_action_id(monkeypatch):
    _patch_http(monkeypatch, lambda url, p, timeout=360: {"ok": True})
    scn = _make_session()
    a = ai(action="no id")
    with pytest.raises(ValueError, match="action_id"):
        scn.edit_sheet(a, status="Open")


def test_set_status_posts_patch_route(monkeypatch):
    captured = {}

    def fake_http(url, payload, timeout=360):
        captured.update(payload)
        return {"ok": True, "global_id": "x"}

    _patch_http(monkeypatch, fake_http)
    scn = _make_session()
    a = ai(action="act", action_id="AI-1")
    scn.set_status(a, "Done")

    assert captured["action"] == "patch_action_status"
    assert captured["status"] == "Done"
    assert captured["global_id"] == f"{DOC_ID}/AI-1"


def test_delete_posts_delete_route(monkeypatch):
    captured = {}

    def fake_http(url, payload, timeout=360):
        captured.update(payload)
        return {"ok": True, "global_id": "x"}

    _patch_http(monkeypatch, fake_http)
    scn = _make_session()
    a = ai(action="act", action_id="AI-2")
    scn.delete(a)

    assert captured["action"] == "delete_action_row"
    assert captured["global_id"] == f"{DOC_ID}/AI-2"


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def test_find_sheet_actions_parses_rows(monkeypatch):
    rows = [
        {"action_text": "foo", "assignee_email": "a@b.com", "action_id": "AI-1",
         "status": "Open", "global_id": "doc/AI-1", "assignee_name": "A B", "sync_status": ""},
    ]
    _patch_http(monkeypatch, lambda url, p, timeout=360: {"ok": True, "docId": DOC_ID, "rows": rows})
    scn = _make_session()
    result = scn.find_sheet_actions()
    assert len(result) == 1
    assert result[0].action == "foo"
    assert result[0].assignee == "a@b.com"
    assert result[0].action_id == "AI-1"
    assert result[0].global_id == "doc/AI-1"


def test_find_sheet_actions_empty_rows(monkeypatch):
    _patch_http(monkeypatch, lambda url, p, timeout=360: {"ok": True, "docId": DOC_ID, "rows": []})
    scn = _make_session()
    assert scn.find_sheet_actions() == []


def test_verify_consistency_posts_verify_route(monkeypatch):
    calls = []

    def fake_http(url, payload, timeout=360):
        calls.append(payload.get("action"))
        return {"ok": True, "consistent": True, "violations": []}

    _patch_http(monkeypatch, fake_http)
    scn = _make_session()
    result = scn.verify_consistency()

    assert "verify_action_rows" in calls
    assert "verify_chip_integrity" in calls
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# Expectation delegation
# ---------------------------------------------------------------------------

def test_verify_all_no_tracker_correct_surfaces():
    scn = _make_session()
    a = ai(action="go", action_id="AI-1", status="Open")
    scn.verify_all_expectations(a, tag="[uc1 AC1]")

    assert len(scn.engine.queue) == 1
    exp = scn.engine.queue[0]
    assert exp.surfaces == frozenset({Surface.DOC, Surface.SHEET})
    assert exp.needs_consistency is True
    assert exp.kind == "PRESENT_CONSISTENT"
    assert exp.tag == "[uc1 AC1]"


def test_verify_all_with_tracker_includes_tracker(monkeypatch):
    _patch_http(monkeypatch, lambda url, p, timeout=360: {"ok": True})
    scn = _make_session()
    scn.insert_tracker()

    a = ai(action="go", action_id="AI-1")
    scn.verify_all_expectations(a, tag="[uc1 AC2]")

    exp = scn.engine.queue[0]
    assert Surface.TRACKER in exp.surfaces


def test_verify_single_surface_and_field_override():
    scn = _make_session()
    a = ai(action="go", action_id="AI-1", status="In Progress")
    scn.verify(a, on=Surface.SHEET, status="Open", tag="[uc1 AC3]")

    exp = scn.engine.queue[0]
    assert exp.surfaces == frozenset({Surface.SHEET})
    assert exp.expected["status"] == "Open"  # override applied
    assert exp.needs_consistency is False


def test_expect_absent_kind():
    scn = _make_session()
    a = ai(action="gone", action_id="AI-5")
    scn.expect_absent(a, on=Surface.SHEET, tag="[uc1 AC4]")

    exp = scn.engine.queue[0]
    assert exp.kind == "ABSENT"
    assert exp.surfaces == frozenset({Surface.SHEET})


def test_snapshot_immutability():
    """Mutating the ai after enqueue must NOT affect the queued snapshot (§4.2)."""
    scn = _make_session()
    a = ai(action="original", action_id="AI-1", status="Open")
    scn.verify_all_expectations(a, tag="[t]")

    a.status = "Mutated After Enqueue"

    exp = scn.engine.queue[0]
    assert exp.expected.get("status") == "Open"


def test_seq_increments_per_enqueue():
    scn = _make_session()
    a = ai(action="go")
    scn.verify(a, on=Surface.DOC, tag="t1")
    scn.verify(a, on=Surface.SHEET, tag="t2")

    exps = scn.engine.queue
    assert exps[0].seq == 0
    assert exps[1].seq == 1


# ---------------------------------------------------------------------------
# Checkpoint wiring
# ---------------------------------------------------------------------------

def test_checkpoint_step_calls_engine_drain(monkeypatch):
    """checkpoint(STEP) calls engine.drain with the correct kind."""
    drain_calls = []

    def fake_drain(kind, label=None, on=None, read=None, read_consistency=None):
        drain_calls.append({"kind": kind, "label": label, "on": on})
        return [], []

    scn = _make_session()
    scn.engine.drain = fake_drain
    scn.checkpoint(CheckpointKind.STEP, label="after-act-1")

    assert len(drain_calls) == 1
    assert drain_calls[0]["kind"] == CheckpointKind.STEP
    assert drain_calls[0]["label"] == "after-act-1"


def test_checkpoint_read_closure_shares_docx_download(monkeypatch):
    """DOC and TRACKER reads share a single download_docx call per checkpoint."""
    download_count = {"docx": 0, "xlsx": 0}

    def fake_download_docx(doc_id):
        download_count["docx"] += 1
        return b"PK\x03\x04fake-docx"

    def fake_download_xlsx(sheet_id):
        download_count["xlsx"] += 1
        return b"PK\x03\x04fake-xlsx"

    def fake_doc_reader_read(self, docx, doc_id):
        return []

    def fake_tracker_reader_read(self, docx, doc_id):
        return []

    def fake_sheet_reader_read(self, xlsx, doc_id):
        return []

    monkeypatch.setattr("tests.helpers.download.download_docx", fake_download_docx)
    monkeypatch.setattr("tests.helpers.download.download_xlsx", fake_download_xlsx)
    monkeypatch.setattr("scn.surfaces.DocReader.read", fake_doc_reader_read)
    monkeypatch.setattr("scn.surfaces.TrackerReader.read", fake_tracker_reader_read)
    monkeypatch.setattr("scn.surfaces.SheetReader.read", fake_sheet_reader_read)

    called_surfaces = []

    def fake_drain(kind, label=None, on=None, read=None, read_consistency=None):
        for s in [Surface.DOC, Surface.TRACKER, Surface.SHEET]:
            read(s)
            called_surfaces.append(s)
        return [], []

    scn = _make_session()
    scn.engine.drain = fake_drain
    scn.checkpoint(CheckpointKind.INTEGRITY)

    assert download_count["docx"] == 1, "download_docx should be called exactly once per checkpoint"
    assert download_count["xlsx"] == 1, "download_xlsx should be called exactly once per checkpoint"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_row_dict_to_ai_maps_fields():
    row = {
        "action_text": "Do X",
        "assignee_email": "a@b.com",
        "action_id": "AI-7",
        "status": "Open",
        "global_id": "doc123/AI-7",
        "assignee_name": "A B",
        "sync_status": "Dirty",
        "doc_id": "doc123",
        "doc_name": "My Doc",
    }
    item = _row_dict_to_ai(row)
    assert item.action == "Do X"
    assert item.assignee == "a@b.com"
    assert item.action_id == "AI-7"
    assert item.status == "Open"
    assert item.global_id == "doc123/AI-7"
    assert item.sync_status == "Dirty"


def test_snapshot_excludes_none_fields():
    a = ai(action="go")  # assignee, action_id, status all None
    snap = _snapshot(a)
    assert "assignee" not in snap
    assert "action_id" not in snap
    assert snap["action"] == "go"


# ---------------------------------------------------------------------------
# Checkpoint read closure — Surface.UI delegation (R1-impl §1)
# ---------------------------------------------------------------------------

def test_checkpoint_read_ui_delegates_to_ui_read_current():
    """read(Surface.UI) calls self.ui.read_current() when ui is attached."""
    expected_list = [ai(action="", action_id="AI-1", status="In Progress")]
    mock_ui = MagicMock()
    mock_ui.read_current.return_value = expected_list

    captured = {}

    def fake_drain(kind, label=None, on=None, read=None, read_consistency=None):
        captured["result"] = read(Surface.UI)
        return [], []

    scn = _make_session()
    scn.ui = mock_ui
    scn.engine.drain = fake_drain
    scn.checkpoint(CheckpointKind.STEP)

    mock_ui.read_current.assert_called_once()
    assert captured["result"] == expected_list


def test_checkpoint_read_ui_returns_empty_when_no_ui_driver():
    """read(Surface.UI) returns [] when self.ui is None."""
    captured = {}

    def fake_drain(kind, label=None, on=None, read=None, read_consistency=None):
        captured["result"] = read(Surface.UI)
        return [], []

    scn = _make_session()
    scn.ui = None
    scn.engine.drain = fake_drain
    scn.checkpoint(CheckpointKind.STEP)

    assert captured["result"] == []
