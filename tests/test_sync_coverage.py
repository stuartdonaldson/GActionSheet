"""Per-sync coverage guard (gts-lu13).

Reproduces the 2026-08-29 failure mode offline: a sync that scanned 1 of 21
declared actions, and 20 sheet rows left marked Deleted. Both conditions must
fail the pure core here (`scan_coverage_problems`/`deleted_row_problems`) --
proof the guard is not the "only ever shown green" kind the Backstop rules
call out.

No network, no GAS, no local.settings.json.
"""
import pytest

from tests.helpers.sync_coverage import (
    assert_sync_coverage,
    deleted_row_problems,
    scan_coverage_problems,
)

pytestmark = pytest.mark.no_live_session


# ---------------------------------------------------------------------------
# scan_coverage_problems
# ---------------------------------------------------------------------------

def test_scan_coverage_red_against_the_2026_08_29_state():
    """1 scanned against 21 declared -- the actual 2026-08-29 log line."""
    problems = scan_coverage_problems(scanned_count=1, expected_min=21)
    assert len(problems) == 1
    assert "count=1" in problems[0]
    assert "21" in problems[0]


def test_scan_coverage_red_when_no_log_entry_found():
    problems = scan_coverage_problems(scanned_count=None, expected_min=3)
    assert len(problems) == 1
    assert "no sync.scanned log entry" in problems[0]


def test_scan_coverage_green_when_count_matches():
    assert scan_coverage_problems(scanned_count=21, expected_min=21) == []


def test_scan_coverage_green_when_count_exceeds_expected():
    """A pre-seeded doc scans more than this session appended -- not a defect."""
    assert scan_coverage_problems(scanned_count=25, expected_min=3) == []


def test_scan_coverage_no_claim_when_nothing_appended():
    """expected_min<=0 mirrors the existing chip.checked_count>0 gate
    (scn/session.py) -- no appended actions, no claim to check."""
    assert scan_coverage_problems(scanned_count=None, expected_min=0) == []
    assert scan_coverage_problems(scanned_count=0, expected_min=0) == []


# ---------------------------------------------------------------------------
# deleted_row_problems
# ---------------------------------------------------------------------------

def test_deleted_rows_red_against_the_2026_08_29_state():
    """20 of 21 rows marked Deleted -- the actual sheet-side failure."""
    rows = [{"global_id": f"doc/ACT-{i}", "sync_status": "Deleted"} for i in range(1, 21)]
    rows.append({"global_id": "doc/ACT-21", "sync_status": ""})
    problems = deleted_row_problems(rows, "doc")
    assert len(problems) == 20
    assert all("Deleted" in p for p in problems)


def test_deleted_rows_green_when_none_marked():
    rows = [{"global_id": "doc/ACT-1", "sync_status": ""}, {"global_id": "doc/ACT-2", "sync_status": "Dirty"}]
    assert deleted_row_problems(rows, "doc") == []


def test_deleted_rows_case_and_whitespace_insensitive():
    rows = [{"global_id": "doc/ACT-1", "sync_status": " deleted "}]
    assert deleted_row_problems(rows, "doc") == ["doc: sheet row doc/ACT-1 marked Deleted"]


def test_deleted_rows_falls_back_to_status_field():
    """find_sheet_actions rows may key the field `status` rather than
    `sync_status` -- tolerate either rather than silently passing."""
    rows = [{"globalId": "doc/ACT-1", "status": "Deleted"}]
    assert deleted_row_problems(rows, "doc") == ["doc: sheet row doc/ACT-1 marked Deleted"]


# ---------------------------------------------------------------------------
# assert_sync_coverage (live wrapper) -- mocked session, no network
# ---------------------------------------------------------------------------

class _FakeSession:
    def __init__(self, *, rows, doc_id="doc-1", gas_log_dir="/fake/log/dir"):
        self.doc_id = doc_id
        self.settings = {"gasLogDir": gas_log_dir}
        self._rows = rows

    def _post_route(self, action, extra=None):
        assert action == "find_sheet_actions"
        return {"rows": self._rows}


def _patch_collect_logs(monkeypatch, entries):
    import tests.helpers.sync_coverage as mod

    def fake_collect_logs(log_dir, match_fn, after=0.0):
        return [e for e in entries if match_fn(e)]

    monkeypatch.setattr("tests.helpers.gas_log.collect_logs", fake_collect_logs)


def test_assert_sync_coverage_raises_on_short_scan(monkeypatch):
    _patch_collect_logs(monkeypatch, [
        {"tag": "sync.scanned", "parentOp": "op-1", "data": {"count": 1}},
    ])
    session = _FakeSession(rows=[])
    with pytest.raises(AssertionError, match="count=1 fewer than 21"):
        assert_sync_coverage(session, op_id="op-1", fence=0.0, expected_min=21)


def test_assert_sync_coverage_raises_on_deleted_row(monkeypatch):
    _patch_collect_logs(monkeypatch, [
        {"tag": "sync.scanned", "parentOp": "op-1", "data": {"count": 5}},
    ])
    session = _FakeSession(rows=[{"global_id": "doc-1/ACT-1", "sync_status": "Deleted"}])
    with pytest.raises(AssertionError, match="marked Deleted"):
        assert_sync_coverage(session, op_id="op-1", fence=0.0, expected_min=5)


def test_assert_sync_coverage_passes_when_healthy(monkeypatch):
    _patch_collect_logs(monkeypatch, [
        {"tag": "sync.scanned", "parentOp": "op-1", "data": {"count": 5}},
    ])
    session = _FakeSession(rows=[{"global_id": "doc-1/ACT-1", "sync_status": ""}])
    assert_sync_coverage(session, op_id="op-1", fence=0.0, expected_min=5)


def test_assert_sync_coverage_ignores_unrelated_op_id(monkeypatch):
    """A concurrent session's sync.scanned (different opId) must not satisfy
    this call's coverage claim -- gts-obry.1's matches_op correlation."""
    _patch_collect_logs(monkeypatch, [
        {"tag": "sync.scanned", "parentOp": "some-other-op", "data": {"count": 99}},
    ])
    session = _FakeSession(rows=[])
    with pytest.raises(AssertionError, match="no sync.scanned log entry"):
        assert_sync_coverage(session, op_id="op-1", fence=0.0, expected_min=1)
