"""test_apt_corpus_batch.py — gts-ph35, staged plan docdata-litter-apt-speed.md
stage `apt-corpus-batching`.

Routes the six `test_apt_corpus_check.py` scenarios that had no batch of
their own (dual-prefix, field-continuation, grammar-matrix,
hyperlink-roundtrip, list-and-table-containers, unparseable-reporting)
through the shared batched runner (tests/support/apt_lane_runner.py) instead
of paying one Doc per scenario — the same anti-pattern
tests/test_apt_flush_lane.py and tests/test_apt_create_lane.py already moved
their own scenarios off of. `test_apt_corpus_check.py` itself already skips
any scenario carrying a `batch`, so giving these six a `batch` here is what
retires their per-scenario Doc, not a change to that file.

Every scenario here is the degenerate `mutation: {"kind": "sync"}` case —
no sheetEdit/trigger — so `run_lane`'s single establishing sync resolves
all six at once; no second sync is needed.
"""
import pathlib
import sys

from scn.session import ScenarioSession

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "tests" / "support"))

import apt_lib  # noqa: E402
import apt_lane_runner  # noqa: E402

import pytest  # noqa: E402

BATCH = "apt-corpus-batch"


def _lane_scenario_files():
    files = []
    for path in sorted(FIXTURES_DIR.glob("*.scenario.json")):
        scenario = apt_lib.load_scenario(path)
        if scenario.batch == BATCH:
            files.append(path)
    return files


class TestCorpusBatchScenariosExist:
    def test_at_least_one_corpus_batch_scenario_exists(self):
        assert _lane_scenario_files(), (
            f"no *.scenario.json with batch={BATCH!r} found under {FIXTURES_DIR}"
        )


def test_apt_corpus_batch(settings, request):
    scenarios = [apt_lib.load_scenario(p) for p in _lane_scenario_files()]
    names = {s.name for s in scenarios}
    assert names == {
        "dual-prefix", "field-continuation", "grammar-matrix",
        "hyperlink-roundtrip", "list-and-table-containers",
        "unparseable-reporting",
    }, f"unexpected scenario set: {sorted(names)!r}"

    # v2 restriction: a body-level table must be the doc's LAST content —
    # list-and-table-containers is the only one of the six carrying a
    # <TABLE...> record, so it must be composed last (compose_corpora raises
    # otherwise). Explicit order per gts-i8we (stage apt-batch-limits): never
    # rely on glob/alphabetical order, which would otherwise put it in the
    # middle of this set.
    order = {
        "dual-prefix": 0,
        "field-continuation": 1,
        "grammar-matrix": 2,
        "hyperlink-roundtrip": 3,
        "unparseable-reporting": 4,
        "list-and-table-containers": 5,
    }
    scenarios.sort(key=lambda s: order[s.name])

    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        results = apt_lane_runner.run_lane(scn, scenarios)
    finally:
        scn.close()

    failed = [r for r in results if not r.clean]  # gts-5ktl: golden diff AND idempotency diff
    if failed:
        pytest.fail(apt_lane_runner.format_failures(results))
