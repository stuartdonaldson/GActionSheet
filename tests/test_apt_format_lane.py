"""test_apt_format_lane.py — gts-dxz9, staged plan docdata-litter-apt-speed.md
stage `apt-format-migration`.

Batches the migratable slice of the inline-formatting family
(test_inline_formatting.py's bold/italic round trip, and
test_status_token_parens.py's mid-text-vs-trailing status-token boundary)
onto checked-in APT corpora, executed through the shared batched runner
(tests/support/apt_lane_runner.py) instead of one Doc per case — the same
retirement stage `apt-scanner-migration` already did for
test_floating_action_scanner.py (tests/test_apt_scanner_lane.py).

Both corpora here are the degenerate `mutation: {"kind": "sync"}` case — no
sheetEdit/trigger — so `run_lane`'s single establishing sync resolves both;
see each corpus's own per-case annotation for why it is authored statusless
(the establishing sync's flush is the path under test).

Not batched with stage `apt-scanner-migration` (`apt-lanes-scanner`) — batching
anti-pairing, staging doc `apt-format-migration` §"Why NOT batched with stage
9": two instances of the same "retire a one-Doc-per-case file" conversion
never share a session, and each lane's own token-namespace block (gts-i8we)
is independent per composed doc.

test_hyperlink_preservation.py's cases 1/2 are NOT re-migrated here — they
are already covered by `hyperlink-roundtrip.apt.txt` (stage
`apt-corpus-batching`, gts-tz5x cases 1/2), which predates this stage. See
that test file's retirement note.

Cases deliberately NOT migrated (multi-step live state that a static
input/expected corpus pair cannot express — `run_lane` supports exactly one
composed-doc establishing sync plus an optional single `sheetEdit`/`trigger`
mutation, not a second live edit to the DOC itself between two syncs):

  - test_inline_formatting.py's idempotency assertions (a second, no-op
    `scn.sync()` compared against the first) — NO LONGER a gap: gts-5ktl
    (stage `lane-idempotency`) made `run_lane` take a second, no-op-sync
    capture and diff each scenario's slice against its own first capture,
    so every scenario in this lane now asserts idempotency by default.
    (This bullet previously read "run_lane produces one capture per lane
    run, not a before/after pair"; that was true of the runner, and the
    runner changed.)
  - test_inline_formatting.py::test_plain_edit_clears_prior_italic_formatting
    — requires a live doc-content edit (replace_action_plain_text) BETWEEN
    two syncs; not one of run_lane's three supported mutation kinds.
  - test_inline_formatting.py::test_archived_row_reuse_does_not_leak_italic_into_new_plain_action
    — requires backdate_action_row + archive_sweep + a fresh append, three
    sequential live mutations against one growing doc.
  - test_inline_formatting.py::test_plain_action_text_has_no_runs — a
    negative/cost check with no positive shape to migrate; already implied
    by every other corpus in this suite carrying no bold/italic markup and
    round-tripping with no runs.
  - test_hyperlink_preservation.py::test_encodable_url_round_trips_and_is_idempotent
    — same idempotency shape as above, and likewise now covered generically
    by the runner's second capture (gts-5ktl) for every corpus in every
    batch; the live test stays as the link-specific instance.
  - test_continuation_indent_config.py (both tests) — the behaviour under
    test is driven by a Config-sheet key (`SR Indent`/`Field SR Indent`)
    read once per sync, a side channel outside what an APT corpus encodes
    (doc content only). No construct in the format spec represents "sync
    with this Config value set."
  - test_ai_n_token.py — asserts globalId FORMAT and sheet-column plumbing
    via direct xlsx/regex inspection, not a doc-content round trip; it does
    not use ScenarioSession/APT at all. Entry-point-mechanism coverage, out
    of this migration's scope per the staged plan's own scope boundary
    ("entry point coverage... not migrated to APT, by design").
"""
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "tests" / "support"))

import apt_lib  # noqa: E402
import apt_lane_runner  # noqa: E402

from scn.session import ScenarioSession  # noqa: E402

BATCH = "apt-lanes-format"


def _lane_scenario_files():
    files = []
    for path in sorted(FIXTURES_DIR.glob("*.scenario.json")):
        scenario = apt_lib.load_scenario(path)
        if scenario.batch == BATCH:
            files.append(path)
    return files


class TestFormatLaneScenariosExist:
    def test_at_least_one_format_lane_scenario_exists(self):
        # docs/lessons-learned/resolved/2026-06-02-new-assertion-vacuously-
        # passes-on-empty-result-set.md — guard against this lane passing
        # vacuously because the glob/filter found nothing.
        assert _lane_scenario_files(), (
            f"no *.scenario.json with batch={BATCH!r} found under {FIXTURES_DIR}"
        )


def test_format_lane_batch(settings, request):
    scenarios = {apt_lib.load_scenario(p).name: apt_lib.load_scenario(p) for p in _lane_scenario_files()}
    expected_names = {"inline-formatting", "status-token-parens"}
    assert set(scenarios) == expected_names, f"unexpected scenario set: {sorted(scenarios)!r}"

    # Neither corpus carries a body-level table, so composition order has no
    # v2 table-position constraint to satisfy (gts-i8we) — sorted() order is
    # fine here, unlike the scanner/corpus-batch lanes.
    ordered = [scenarios[name] for name in sorted(scenarios)]

    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        results = apt_lane_runner.run_lane(scn, ordered)
    finally:
        scn.close()

    failed = [r for r in results if not r.clean]  # gts-5ktl: golden diff AND idempotency diff
    if failed:
        pytest.fail(apt_lane_runner.format_failures(results))
