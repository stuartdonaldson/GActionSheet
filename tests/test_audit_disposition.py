"""test_audit_disposition.py — gts-u6ew.9 (stage 6, disposition-enforcement).

Focused tests for scripts/audit_disposition.py's pure logic: scope selection
(--ids / --since) and the two ADR-0011 compliance checks (missing disposition,
malformed disposition). No live `bd` subprocess — every function under test
takes an already-loaded issue list (list of dicts, the shape `bd list --json`
returns), same pattern as tests/test_check_coverage.py.

Coverage inventory (test-functional Step 1, run before authoring): no
tests/test_audit_disposition.py existed before this bead — scripts/
audit_disposition.py is net-new (this stage). No coverage to extend.

Backstop rule (a new assertion must be proven to fail): each check below has a
paired "does not flag a clean issue" test alongside its "flags a violating
issue" test, so a check that always returns empty (silently passing everything)
would fail the positive case rather than passing vacuously.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

# gts-aqpk: fast/local tier -- pure logic, no live GAS/Google round trip, no
# live `bd` subprocess.
pytestmark = pytest.mark.no_live_session

_SPEC = importlib.util.spec_from_file_location(
    "audit_disposition", Path(__file__).parent.parent / "scripts" / "audit_disposition.py"
)
ad = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("audit_disposition", ad)
_SPEC.loader.exec_module(ad)


def _issue(id_, title="[TST] example", labels=None, description="", created_at="2026-09-05T00:00:00Z"):
    return {
        "id": id_,
        "title": title,
        "labels": labels or [],
        "description": description,
        "created_at": created_at,
    }


# --- filter_since / filter_ids ----------------------------------------------

def test_filter_since_excludes_pre_cutoff_tst_issues():
    issues = [
        _issue("old", created_at="2026-06-01T00:00:00Z"),
        _issue("new", created_at="2026-09-06T00:00:00Z"),
    ]
    scoped = ad.filter_since(issues, "2026-09-05")
    assert [i["id"] for i in scoped] == ["new"]


def test_filter_since_excludes_non_tst_issues_even_if_recent():
    issues = [_issue("imp", title="[IMP] example", created_at="2026-09-06T00:00:00Z")]
    assert ad.filter_since(issues, "2026-09-05") == []


def test_filter_ids_selects_only_named_tst_issues():
    issues = [
        _issue("a"),
        _issue("b"),
        _issue("c", title="[IMP] not a TST issue"),
    ]
    scoped = ad.filter_ids(issues, ["a", "c", "nonexistent"])
    assert [i["id"] for i in scoped] == ["a"]


# --- find_missing_disposition ------------------------------------------------

def test_missing_disposition_flags_issue_with_no_disp_label():
    scoped = [_issue("x", labels=["test-framework"])]
    missing = ad.find_missing_disposition(scoped)
    assert [i["id"] for i in missing] == ["x"]


def test_missing_disposition_does_not_flag_issue_with_a_disp_label():
    scoped = [_issue("x", labels=["disp:2"], description="## Disposition\nTarget: ...\nBasis: ...")]
    missing = ad.find_missing_disposition(scoped)
    assert missing == []


# --- find_malformed_disposition ---------------------------------------------

def test_malformed_flags_multiple_disp_labels():
    scoped = [_issue("x", labels=["disp:1", "disp:2"],
                      description="## Disposition\nTarget: ...\nBasis: ...")]
    malformed = ad.find_malformed_disposition(scoped)
    assert [i["id"] for i in malformed] == ["x"]


def test_malformed_flags_missing_disposition_section():
    scoped = [_issue("x", labels=["disp:2"], description="no section here")]
    malformed = ad.find_malformed_disposition(scoped)
    assert [i["id"] for i in malformed] == ["x"]


def test_malformed_does_not_flag_a_single_well_formed_disposition():
    scoped = [_issue("x", labels=["disp:2"], description="## Disposition\nTarget: ...\nBasis: ...")]
    assert ad.find_malformed_disposition(scoped) == []


def test_malformed_does_not_double_report_a_fully_missing_disposition():
    # No disp label at all is find_missing_disposition's finding, not this
    # one's -- reported once, not twice, for the same bead.
    scoped = [_issue("x", labels=[], description="")]
    assert ad.find_malformed_disposition(scoped) == []


# --- audit (both checks together) -------------------------------------------

def test_audit_returns_empty_on_a_clean_scope():
    scoped = [
        _issue("a", labels=["disp:0"], description="## Disposition\nTarget: ...\nBasis: ..."),
        _issue("b", labels=["disp:4"], description="## Disposition\nTarget: ...\nBasis: ...\nReason: ..."),
    ]
    missing, malformed = ad.audit(scoped)
    assert missing == []
    assert malformed == []


def test_audit_reports_both_kinds_of_violation_in_one_pass():
    scoped = [
        _issue("no-label", labels=[]),
        _issue("two-labels", labels=["disp:1", "disp:3"],
               description="## Disposition\nTarget: ...\nBasis: ..."),
    ]
    missing, malformed = ad.audit(scoped)
    assert [i["id"] for i in missing] == ["no-label"]
    assert [i["id"] for i in malformed] == ["two-labels"]
