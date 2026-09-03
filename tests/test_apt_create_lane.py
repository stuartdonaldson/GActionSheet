"""test_apt_create_lane.py — gts-pi1s, staged plan apt-testing.md stage
`apt-lanes`.

Expresses the `@create` boundary lane: a bare `AI:` trigger inserted at
document start / middle / end of an already-populated doc, plus inside a
body-level table cell, all resolved by the SAME establishing sync a plain
"sync" scenario already needs (a bare trigger's own presence in the input
corpus IS the mutation — no sheetEdit/trigger call needed). What this lane
actually exercises is `_buildFlushRequests`' general occurrence scanner
(`_collectFlushOccurrences`) locating and rewriting a freshly-assigned
token wherever it lands in document order — the non-append path
`decodeAptIntoDoc` (append-only against an empty body) never reaches, since
every corpus it decodes ends up flush-appended in file order regardless of
which "boundary" a scenario's own record occupies relative to its sibling
records.

Shares tests/support/apt_lane_runner.py with tests/test_apt_flush_lane.py
(gts-iz9i) — one runner, two lanes, per the staged plan's own "Why paired"
note for stage `apt-lanes`.
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

BATCH = "apt-lanes-create"


def _lane_scenario_files():
    files = []
    for path in sorted(FIXTURES_DIR.glob("*.scenario.json")):
        scenario = apt_lib.load_scenario(path)
        if scenario.batch == BATCH:
            files.append(path)
    return files


class TestCreateLaneScenariosExist:
    def test_at_least_one_create_lane_scenario_exists(self):
        assert _lane_scenario_files(), (
            f"no *.scenario.json with batch={BATCH!r} found under {FIXTURES_DIR}"
        )


def test_create_boundary_lane_batch(settings, request):
    scenarios = [apt_lib.load_scenario(p) for p in _lane_scenario_files()]
    names = {s.name for s in scenarios}
    assert names == {
        "create-lane-start", "create-lane-middle", "create-lane-end", "create-lane-table-cell",
    }, f"unexpected scenario set: {sorted(names)!r}"

    # v2 restriction: a body-level table must be the doc's LAST content —
    # the table-cell scenario must therefore be composed last (compose_corpora
    # raises otherwise). Scenario files are batch-selected then globbed
    # alphabetically above (see _lane_scenario_files), which already sorts
    # "create-lane-table-cell" after "-end"/"-middle"/"-start" -- reordered
    # here explicitly so that invariant does not depend on filename sort
    # order staying lucky.
    order = {"create-lane-start": 0, "create-lane-middle": 1, "create-lane-end": 2,
             "create-lane-table-cell": 3}
    scenarios.sort(key=lambda s: order[s.name])

    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        results = apt_lane_runner.run_lane(scn, scenarios)
    finally:
        scn.close()

    failed = [r for r in results if not r.clean]  # gts-5ktl: golden diff AND idempotency diff
    if failed:
        pytest.fail(apt_lane_runner.format_failures(results))
