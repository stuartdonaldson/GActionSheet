"""test_check_entry_point_registry_view.py — gts-u6ew.10 (H12/I6).

Focused tests for scripts/check_entry_point_registry_view.py's pure logic:
extracting the total/covered/deferred counts each doc states in prose, and
diffing them against the registry's actual counts. No live pytest
subprocess or file I/O beyond reading the two real project docs -- every
comparison function under test takes already-parsed strings/dicts, same
shape as tests/test_check_coverage.py and tests/test_audit_disposition.py.

Coverage inventory (test-functional Step 1, run before authoring): no
tests/test_check_entry_point_registry_view.py existed before this bead --
scripts/check_entry_point_registry_view.py had no test file at all (it is
net-new, authored this bead). No coverage to extend; net-new.

Includes the backstop rule's proven-to-fail case (CLAUDE.md "a new
assertion must be proven to fail before acceptance"): test_diff_guide_*
constructs a deliberately wrong `claimed` dict and asserts the diff
functions actually report a mismatch, not just that they pass on agreement.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

# gts-aqpk: fast/local tier -- pure logic, no live GAS/Google round trip.
pytestmark = pytest.mark.no_live_session

# scripts/ is not a package (no __init__.py) and its module name collides
# with nothing else on sys.path, so load it directly by path rather than
# adding scripts/ to sys.path for the whole test session.
_SPEC = importlib.util.spec_from_file_location(
    "check_entry_point_registry_view",
    Path(__file__).parent.parent / "scripts" / "check_entry_point_registry_view.py",
)
cerv = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("check_entry_point_registry_view", cerv)
_SPEC.loader.exec_module(cerv)

GUIDE_SNIPPET = (
    "list of all **37** state-modifying entry points (menu items, ...) lives in "
    "`scn/contract.ENTRY_POINT_REGISTRY`\n\n"
    "24 of the 37 entries are expected to carry a real tagged scenario call-site; "
    "the remaining **13** are explicitly enumerated as **deferred** (not silently "
    "uncovered) in `scn/contract.ENTRY_POINT_DEFERRED`"
)

HARNESS_DESIGN_SNIPPET = (
    "A single machine-readable registry of 37 state-modifying entry points, "
    "with 13 explicitly deferred (each with a tracking bead) rather than "
    "silently uncovered."
)


def test_registry_counts_from_dicts():
    registry = {"a": "x", "b": "x", "c": "x"}
    deferred = {"c": "reason"}
    assert cerv.registry_counts(registry, deferred) == {
        "total": 3,
        "deferred": 1,
        "covered": 2,
    }


def test_extract_guide_counts_matches_real_shape():
    claimed = cerv.extract_guide_counts(GUIDE_SNIPPET)
    assert claimed == {
        "total": 37,
        "total_from_covered_line": 37,
        "covered": 24,
        "deferred": 13,
    }


def test_extract_guide_counts_raises_on_reworded_doc():
    with pytest.raises(cerv.ExtractionError):
        cerv.extract_guide_counts("this text mentions no counts at all")


def test_extract_harness_design_counts_matches_real_shape():
    claimed = cerv.extract_harness_design_counts(HARNESS_DESIGN_SNIPPET)
    assert claimed == {"total": 37, "deferred": 13, "covered": 24}


def test_extract_harness_design_counts_raises_on_reworded_doc():
    with pytest.raises(cerv.ExtractionError):
        cerv.extract_harness_design_counts("no matching pattern here")


def test_diff_guide_agrees_when_numbers_match():
    actual = {"total": 37, "deferred": 13, "covered": 24}
    claimed = {"total": 37, "total_from_covered_line": 37, "covered": 24, "deferred": 13}
    assert cerv.diff_guide(actual, claimed) == []


def test_diff_guide_reports_every_kind_of_mismatch():
    """Proven-to-fail: a claimed dict wrong in all four ways must produce
    four distinct problem messages, not a silent or partial pass."""
    actual = {"total": 37, "deferred": 13, "covered": 24}
    claimed = {
        "total": 32,
        "total_from_covered_line": 22,
        "covered": 10,
        "deferred": 22,
    }
    problems = cerv.diff_guide(actual, claimed)
    assert len(problems) == 4
    assert any("total entry points" in p for p in problems)
    assert any("N of the M entries" in p for p in problems)
    assert any("deferred entries" in p for p in problems)
    assert any("covered entries" in p for p in problems)


def test_diff_harness_design_agrees_when_numbers_match():
    actual = {"total": 37, "deferred": 13, "covered": 24}
    claimed = {"total": 37, "deferred": 13, "covered": 24}
    assert cerv.diff_harness_design(actual, claimed) == []


def test_diff_harness_design_reports_mismatch():
    """Proven-to-fail counterpart for the harness-design.md side."""
    actual = {"total": 37, "deferred": 13, "covered": 24}
    claimed = {"total": 32, "deferred": 22, "covered": 10}
    problems = cerv.diff_harness_design(actual, claimed)
    assert len(problems) == 2


def test_check_against_real_project_docs_agrees():
    """End-to-end against the two real docs in this repo -- this is the
    check that actually guards against §7 drifting from the registry
    again, run every time the fast tier runs."""
    problems, extraction_errors = cerv.check()
    assert extraction_errors == []
    assert problems == []


def test_check_fails_against_a_deliberately_stale_guide_copy(tmp_path):
    """Proven-to-fail against the real registry: a guide copy stating the
    old, drifted 32/22 numbers must be reported as a mismatch, not pass.

    The stale copy is built by rewriting whatever numbers the guide states
    *today* (read back from the registry) rather than hard-coded ones -- the
    counts move whenever the registry grows (gts-u6ew.11 took them 37 -> 48),
    and a hard-coded rewrite would silently become a no-op and leave this
    proven-to-fail case asserting nothing."""
    actual = cerv.registry_counts()
    real_text = Path(cerv.DEFAULT_GUIDE).read_text()
    stale_text = (
        real_text.replace(f"all **{actual['total']}** state-modifying", "all **32** state-modifying")
        .replace(f"{actual['covered']} of the {actual['total']} entries", "10 of the 32 entries")
        .replace(f"remaining **{actual['deferred']}** are explicitly enumerated",
                 "remaining **22** are explicitly enumerated")
    )
    assert stale_text != real_text, "stale-copy rewrite matched nothing -- guide §7 was reworded"
    stale_guide = tmp_path / "stale-guide.md"
    stale_guide.write_text(stale_text)

    problems, extraction_errors = cerv.check(
        guide_path=str(stale_guide), harness_design_path=cerv.DEFAULT_HARNESS_DESIGN
    )
    assert extraction_errors == []
    assert len(problems) == 4


def test_main_exits_zero_against_real_docs(capsys):
    rc = cerv.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "OK:" in out


def test_main_exits_nonzero_on_extraction_error(tmp_path, capsys):
    empty = tmp_path / "empty.md"
    empty.write_text("nothing relevant here")
    rc = cerv.main(["--guide", str(empty)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "EXTRACTION ERROR" in err
