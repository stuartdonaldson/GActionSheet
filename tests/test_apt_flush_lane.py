"""test_apt_flush_lane.py — gts-iz9i, staged plan apt-testing.md stage
`apt-lanes`.

Expresses flush entry points 1-4 and 7 (SyncManager.js's toFlush blocks:
sheetWin, newly-assigned, missing-explicit-status materialization,
duplicate-N reconciliation; plus the onEdit-trigger path,
_syncSheetRowToDoc) as declarative scenarios over per-boundary corpora,
executed through the shared batched runner (tests/support/apt_lane_runner.py)
rather than one Doc per scenario — the anti-pattern
tests/test_apt_corpus_check.py already names against itself (7 scenarios,
5.1 min) and this stage's own plan warns against repeating.

Entry points 5 and 6 (preview-card and sidebar status taps) are
deliberately NOT expressed here — a sheet edit reaches the same shared
_buildFlushRequests but not those call sites, and the entry-point-coverage
invariant requires the call site itself; their existing UI-driven tests
(tests/test_field_continuation_flush.py::test_ep5_*/test_ep6_*) stay as
the coverage for those two.

Entry point 7's golden encodes the KNOWN GAP already documented by
tests/test_field_continuation_flush.py::test_ep7_onedit_flush_known_gap
(the onEdit-trigger path has no customFields source — the field line is
dropped, not preserved). This test's own golden will start failing, in a
good way, the day that gap closes; see this file's docstring twin above.
"""
import pathlib

import pytest

from scn.session import ScenarioSession

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"

import sys  # noqa: E402
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "tests" / "support"))

import apt_lib  # noqa: E402
import apt_lane_runner  # noqa: E402

BATCH = "apt-lanes-flush"


def _lane_scenario_files():
    files = []
    for path in sorted(FIXTURES_DIR.glob("*.scenario.json")):
        scenario = apt_lib.load_scenario(path)
        if scenario.batch == BATCH:
            files.append(path)
    return files


class TestFlushLaneScenariosExist:
    def test_at_least_one_flush_lane_scenario_exists(self):
        # docs/lessons-learned/resolved/2026-06-02-new-assertion-vacuously-
        # passes-on-empty-result-set.md — guard against this lane passing
        # vacuously because the glob/filter found nothing.
        assert _lane_scenario_files(), (
            f"no *.scenario.json with batch={BATCH!r} found under {FIXTURES_DIR}"
        )


def test_flush_lane_batch(settings, request):
    scenarios = [apt_lib.load_scenario(p) for p in _lane_scenario_files()]
    assert {s.name for s in scenarios} == {
        "flush-lane-sheetwin",
        "flush-lane-new-assign",
        "flush-lane-missing-status",
        "flush-lane-duplicate",
        "flush-lane-onedit-trigger",
    }, f"unexpected scenario set: {[s.name for s in scenarios]!r}"

    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        results = apt_lane_runner.run_lane(scn, scenarios)
    finally:
        scn.close()

    failed = [r for r in results if not r.clean]  # gts-5ktl: golden diff AND idempotency diff
    if failed:
        pytest.fail(apt_lane_runner.format_failures(results))
