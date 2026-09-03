"""test_apt_scanner_lane.py — gts-oaw1, staged plan docdata-litter-apt-speed.md
stage `apt-scanner-migration`.

Batches the `test_floating_action_scanner.py` grammar cases that have a
specifiable oracle onto checked-in APT corpora, executed through the shared
batched runner (`tests/support/apt_lane_runner.py`) rather than one Doc per
case — the same anti-pattern `tests/test_apt_corpus_batch.py` (gts-ph35,
stage `apt-corpus-batching`) already retired for the corpus-check lane.

Three cases from that file are deliberately NOT here — see the retirement
notes in `tests/test_floating_action_scanner.py` for the citations:
tracker-table exclusion (scanner behaviour, explicitly out of APT's scope
per `docs/interfaces/action-portable-text.md` §"List items and table cells
(v2)"), the sidebar-status-flush round trip (exercises flush entry point
6, which the same doc's §"Batched lanes" carves out as staying covered by
its existing UI-driven test), and the fast-path-vs-soft-return PERSON-chip
comparison half of gts-ogev (`test_ogev_soft_return_person_chip_matches_fast_path`)
— kept on its own `append_doc_paragraph_with_chip`/`append_doc_soft_paragraph_with_chip`
construction so both sides of the comparison are built the same mechanical way,
per the frozen AC's own wording ("matching the single-token fast path's
output for the SAME chip"). gts-i0gk (found live during this stage, RESOLVED
2026-08-31) had found a chip on a non-first soft-return line resolved to
nothing through decodeAptIntoDoc too, not just the scanner — both are fixed
now (see gts-mt39's `test_mt39_soft_return_multi_token_person_chip_parity`,
which proves the decodeAptIntoDoc path directly). Only gts-ogev's independent
text-email regression guard migrated onto this batched lane (see
`scanner-ogev.apt.txt`).

Two scenarios need more than a text diff to express their AC, so this file
layers extra assertions on the SAME `scn` `run_lane` leaves open, after the
batch's establishing sync:

  - `unparseable-reporting-verify` (gts-xvlu): the round-trip corpus
    (`unparseable-reporting.apt.txt`, already batched separately under
    `apt-corpus-batch` by stage `apt-corpus-batching`) only proves the
    unparseable paragraph's TEXT survives untouched — it says nothing about
    whether `verify_consistency` actually REPORTS it. This scenario reuses
    the same corpus (extended with cases 2/3) under this lane's own batch
    tag so a live `verify_consistency` call can be asserted here too.
  - `scanner-ogev` (gts-ogev): the AC compares RESOLVED sheet fields
    (assignee/assignee_name) between two records to each other — not
    expressible as a static text diff — so this test reads
    `scn.find_sheet_actions()` after the batch sync and compares rows
    directly, exactly like the original test did.
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

BATCH = "apt-lanes-scanner"


def _lane_scenario_files():
    files = []
    for path in sorted(FIXTURES_DIR.glob("*.scenario.json")):
        scenario = apt_lib.load_scenario(path)
        if scenario.batch == BATCH:
            files.append(path)
    return files


class TestScannerLaneScenariosExist:
    def test_at_least_one_scanner_lane_scenario_exists(self):
        # docs/lessons-learned/resolved/2026-06-02-new-assertion-vacuously-
        # passes-on-empty-result-set.md — guard against this lane passing
        # vacuously because the glob/filter found nothing.
        assert _lane_scenario_files(), (
            f"no *.scenario.json with batch={BATCH!r} found under {FIXTURES_DIR}"
        )


def _find_by_global_id(scn, global_id):
    rows = scn.find_sheet_actions()
    row = next((r for r in rows if r.global_id == global_id), None)
    assert row is not None, (
        f"global_id {global_id!r} not found after sync; "
        f"rows={[(r.global_id, r.action) for r in rows]!r}"
    )
    return row


def test_scanner_lane_batch(settings, request):
    scenarios = {apt_lib.load_scenario(p).name: apt_lib.load_scenario(p) for p in _lane_scenario_files()}
    expected_names = {
        "scanner-soft-return",
        "scanner-jxrw",
        "scanner-ogev",
        "unparseable-reporting-verify",
        "scanner-table-cell",
    }
    assert set(scenarios) == expected_names, f"unexpected scenario set: {sorted(scenarios)!r}"

    # scanner-table-cell is the only table-bearing scenario in this batch --
    # apt_lib.compose_corpora requires it last (gts-i8we, "Batch scale
    # limits"). Never rely on glob/alphabetical order for this.
    ordered = [
        scenarios["scanner-soft-return"],
        scenarios["scanner-jxrw"],
        scenarios["scanner-ogev"],
        scenarios["unparseable-reporting-verify"],
        scenarios["scanner-table-cell"],
    ]

    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        results = apt_lane_runner.run_lane(scn, ordered)
        failed = [r for r in results if not r.clean]  # gts-5ktl: golden diff AND idempotency diff
        if failed:
            pytest.fail(apt_lane_runner.format_failures(results))

        # gts-xvlu: verify_consistency must actually REPORT the malformed
        # token as unparseable, and must not report the well-formed/prose
        # cases alongside it.
        resp = scn._post_fixture("verify_consistency")
        data = resp.get("data") or {}
        assert not data.get("ok"), f"expected verify_consistency to report an issue: {data!r}"
        issues = data.get("issues") or []
        matches = [i for i in issues if "does not parse" in i]
        assert matches, f"expected an unparseable-action-paragraph issue, got: {issues!r}"
        assert "ACT-77 | someone | do the thing" in matches[0]
        assert data.get("counts", {}).get("unparseable") == 1, (
            f"expected exactly 1 unparseable paragraph, got: {data.get('counts')!r}"
        )

        # gts-ogev (partial — see scanner-ogev.apt.txt's own note and gts-i0gk):
        # only the text-based email assignee case migrated here; the
        # fast-path-vs-soft-return PERSON CHIP comparison stays on the
        # original live test.
        text_row = _find_by_global_id(scn, f"{scn.doc_id}/ACT-642")

        assert text_row.assignee == "jane.doe@example.com"
        assert text_row.assignee_name == "Jane Doe"
        assert text_row.action == "text email continuation"
    finally:
        scn.close()
