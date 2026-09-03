"""Per-sync coverage guard (gts-lu13).

Reproduces the 2026-08-29 failure mode offline: a sync that scanned 1 of 21
declared actions, and 20 sheet rows left marked Deleted. Both conditions must
fail the pure core here (`scan_coverage_problems`/`deleted_row_problems`) --
proof the guard is not the "only ever shown green" kind the Backstop rules
call out.

No network, no GAS, no local.settings.json.

gts-athl: also covers scan_coverage_problems' no_scan_reason parameter and
assert_sync_coverage's matching wait -- a sync that legitimately took one of
syncDocument()'s two non-scanning early-return branches (doc not found on
open, or trashed) must not be flagged as missing coverage.
"""
import pytest

from tests.helpers.sync_coverage import (
    NO_SCAN_TAGS,
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


def test_scan_coverage_green_when_trashed_branch_fired():
    """gts-athl: syncDocument() took the trashed-doc branch (logs
    sync.docNotFound.trashed, never reaches sync.scanned) -- not a coverage
    gap, since that branch structurally cannot log sync.scanned."""
    assert scan_coverage_problems(
        scanned_count=None, expected_min=5, no_scan_reason="sync.docNotFound.trashed"
    ) == []


def test_scan_coverage_green_when_doc_not_found_on_open():
    """gts-athl: the sibling non-scanning branch (doc failed to open at
    all -- sync.docNotFound.invalid) gets the same treatment."""
    assert scan_coverage_problems(
        scanned_count=None, expected_min=5, no_scan_reason="sync.docNotFound.invalid"
    ) == []


def test_scan_coverage_red_before_the_fix_proves_the_guard_moved():
    """Backstop rules: a new assertion must be proven to fail against the
    condition it checks. Before gts-athl, scan_coverage_problems had no
    no_scan_reason parameter at all -- passing it was not merely ignored,
    it was TypeError. This proves the pre-fix code path (no_scan_reason
    absent/None, matching the OLD call site's unconditional
    scan_coverage_problems(scanned_count, expected_min)) still red-flags a
    missing sync.scanned exactly as before -- the widening is additive, not
    a silent global loosening of the guard."""
    assert scan_coverage_problems(scanned_count=None, expected_min=5) == [
        "no sync.scanned log entry found for this sync (expected count >= 5)"
    ]
    # An unrecognized reason string must NOT be treated as a legitimate
    # no-scan excuse -- only the two audited NO_SCAN_TAGS qualify.
    assert scan_coverage_problems(
        scanned_count=None, expected_min=5, no_scan_reason="sync.someOtherTag"
    ) == ["no sync.scanned log entry found for this sync (expected count >= 5)"]


def test_no_scan_tags_is_exactly_the_audited_pair():
    """Pins the audited set (src/SyncManager.js syncDocument(), 2026-09-01)
    so a future third early-return branch added there without updating this
    set is at least visible in a diff review, not a silent gap."""
    assert NO_SCAN_TAGS == {"sync.docNotFound.invalid", "sync.docNotFound.trashed"}


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
    """Patches wait_for_log, not collect_logs (gts-athl fix, 2026-09-01):
    assert_sync_coverage calls wait_for_log (gts-6pws), and does so via a
    function-local `from tests.helpers.gas_log import ... wait_for_log` --
    monkeypatching the module attribute IS visible to that local import
    (it re-resolves the name from the module at call time), but patching
    collect_logs (as this helper used to) patches a function
    assert_sync_coverage never calls, so the mock silently did nothing and
    every test using it hit the REAL wait_for_log against local.settings.json's
    live Axiom config -- discovered live while fixing gts-athl in this same
    file: 2 of the then-13 tests here were red for this reason, each eating
    a real 15s+ live Axiom timeout instead of returning instantly. First
    match wins; no match raises TimeoutError, same contract as the real
    wait_for_log.
    """
    import tests.helpers.gas_log as gas_log_mod

    def fake_wait_for_log(log_dir, match_fn, timeout_s=60.0, poll_s=1.0, after=0.0):
        for e in entries:
            if match_fn(e):
                return e
        raise TimeoutError(f"No matching log entry within {timeout_s}s (fake)")

    monkeypatch.setattr(gas_log_mod, "wait_for_log", fake_wait_for_log)


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


def test_assert_sync_coverage_passes_on_trashed_doc_no_scan(monkeypatch):
    """gts-athl: the live wrapper end-to-end -- a sync whose op only logged
    sync.docNotFound.trashed (never sync.scanned) must not raise, even
    though this session appended actions it would otherwise expect scanned."""
    _patch_collect_logs(monkeypatch, [
        {"tag": "sync.docNotFound.trashed", "parentOp": "op-1", "data": {"docId": "doc-1"}},
    ])
    session = _FakeSession(rows=[])
    assert_sync_coverage(session, op_id="op-1", fence=0.0, expected_min=5)


def test_assert_sync_coverage_passes_on_doc_not_found_on_open_no_scan(monkeypatch):
    """Sibling of the above for the other audited NO_SCAN_TAGS entry."""
    _patch_collect_logs(monkeypatch, [
        {"tag": "sync.docNotFound.invalid", "parentOp": "op-1", "data": {"docId": "doc-1"}},
    ])
    session = _FakeSession(rows=[])
    assert_sync_coverage(session, op_id="op-1", fence=0.0, expected_min=5)


def test_assert_sync_coverage_still_raises_when_truly_nothing_logged(monkeypatch):
    """gts-athl must not turn into a blanket loosening: an op with NEITHER
    sync.scanned NOR a NO_SCAN_TAGS entry (e.g. the log was genuinely lost,
    or a real code path regressed) still raises."""
    _patch_collect_logs(monkeypatch, [])
    session = _FakeSession(rows=[])
    with pytest.raises(AssertionError, match="no sync.scanned log entry"):
        assert_sync_coverage(session, op_id="op-1", fence=0.0, expected_min=5)
