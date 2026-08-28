"""apt_lane_runner.py — the batched scenario runner stage `apt-lanes` (staged
plan knowledge-base/staging/apt-testing.md, gts-iz9i/gts-pi1s) writes once and
shares between its two lanes (Sheet-edit-driven flush scenarios and the
`@create` boundary lane) — and that `act-retire` migrates the retired
scanner cases into later, so its shape is load-bearing past this stage.

Materialise once -> apply declarative mutations -> sync once -> assert every
scenario against that one convergence. `tests/test_apt_corpus_check.py` is
the shape this replaces for THESE scenarios: one Doc per scenario, paying
begin_journey_session + sync + end_journey_session every time (measured
there at 5.1 min for 7 scenarios). `run_lane` pays that cost once per lane,
regardless of scenario count, by composing every scenario's input corpus
into ONE doc (`apt_lib.compose_corpora`) and slicing the ONE capture back
apart (`apt_lib.slice_records`) before diffing each slice against its own
scenario's expected corpus.

Two non-degenerate mutation kinds this runner adds beyond stage
`apt-scenarios`' plain "sync" (docs/interfaces/action-portable-text.md
"Scenario triples"):

  sheetEdit  {"kind": "sheetEdit", "token": "AI-101", "fields": {"status": "In Progress"}}
             Addresses an already-established record by its literal
             (never-renumbered) N token and edits sheet field(s) via
             ScenarioSession.edit_sheet — the sheetWin path (SyncManager.js's
             toFlush 'sheetWins' block). Its flush lands on the NEXT sync,
             not immediately (Dirty-flag path), so run_lane always issues a
             second sync when any sheetEdit mutation was applied.

  trigger    {"kind": "trigger", "token": "AI-107", "field": "status", "value": "Done"}
             Drives the onEdit-trigger entry point (_syncSheetRowToDoc) via
             the edit_cell_via_trigger fixture — applies its own flush
             immediately, no second sync needed for it specifically (a
             harmless second sync still runs if ANOTHER scenario in the same
             batch needs one for its own sheetEdit).

A `kind: "sync"` scenario in a batch needs no per-scenario action at all —
its input corpus already encodes the flush-triggering condition (a bare
`AI:` token, a duplicate occurrence, a missing status token, an insertion
position), and the batch's own single establishing sync resolves it, exactly
as stage `apt-scenarios`' generic per-scenario lane already does for the
degenerate case.
"""
from __future__ import annotations

import dataclasses
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import apt_lib  # noqa: E402

from scn.ai import ai  # noqa: E402


@dataclasses.dataclass
class LaneResult:
    scenario: "apt_lib.Scenario"
    diff: "apt_lib.AptDiffResult"


def corpus_text(name: str, fixtures_dir: pathlib.Path = FIXTURES_DIR) -> str:
    path = fixtures_dir / f"{name}.apt.txt"
    assert path.exists(), f"corpus {name!r} not found: {path}"
    return path.read_text(encoding="utf-8")


def run_lane(scn, scenarios: list, fixtures_dir: pathlib.Path = FIXTURES_DIR) -> list[LaneResult]:
    """Executes every scenario in `scenarios` against ONE materialised Doc on
    `scn` (a live ScenarioSession) and returns one LaneResult per scenario,
    each carrying its own apt_lib.diff_apt result — the caller decides how
    to fail (see tests/test_apt_flush_lane.py for the "report every failing
    scenario, not just the first" convention)."""
    named_inputs = [(s.name, corpus_text(s.input_corpus, fixtures_dir)) for s in scenarios]
    composed, ranges = apt_lib.compose_corpora(named_inputs)

    resp = scn._post_fixture("decode_reference_document", {"apt": composed})
    assert (resp.get("data") or {}).get("ok"), f"decode_reference_document failed: {resp}"

    scn.sync()  # establish; also resolves every plain "sync"-kind scenario in this batch

    needs_second_sync = False
    for s in scenarios:
        kind = s.mutation.get("kind")
        if kind == "sheetEdit":
            target = ai(action="", action_id=s.mutation["token"])
            scn.edit_sheet(target, **s.mutation["fields"])
            needs_second_sync = True
        elif kind == "trigger":
            global_id = f"{scn.doc_id}/{s.mutation['token']}"
            resp = scn._post_fixture("edit_cell_via_trigger", {
                "globalId": global_id,
                "field": s.mutation["field"],
                "value": s.mutation["value"],
            })
            data = resp.get("data") or {}
            assert data.get("applied"), f"{s.name}: edit_cell_via_trigger did not apply: {resp}"
        elif kind == "sync":
            pass
        else:
            raise ValueError(
                f"{s.name}: mutation kind {kind!r} not supported by run_lane "
                "(supported: sync, sheetEdit, trigger)"
            )

    if needs_second_sync:
        scn.sync()  # flushes every sheetWin queued above

    resp = scn._post_fixture("encode_reference_document")
    data = resp.get("data") or {}
    assert data.get("ok"), f"encode_reference_document failed: {resp}"
    # A chip-badge preview link (any token flushed for the first time, or
    # re-flushed) carries THIS run's own randomly-generated scn.doc_id
    # (decision 7: a scenario corpus is doc-less, materialised into a fresh
    # ScenarioSession.new_doc() every run) -- unlike the doc-BACKED corpora
    # (dual-prefix, hyperlink-roundtrip, ...) whose already-materialised chip
    # links never get rewritten because nothing in those scenarios forces a
    # re-flush. A golden that forces one (every scenario in this lane does)
    # cannot hardcode the docId, so it spells it as the literal placeholder
    # DOC_ID and this is the one substitution point that makes the two sides
    # comparable.
    captured = data["apt"].replace(scn.doc_id, "DOC_ID")

    results = []
    for s in scenarios:
        start, end = ranges[s.name]
        captured_slice = apt_lib.slice_records(captured, start, end)
        expected_text = corpus_text(s.expected_corpus, fixtures_dir)
        results.append(LaneResult(s, apt_lib.diff_apt(expected_text, captured_slice)))
    return results


def format_failures(results: list) -> str:
    lines = []
    for r in results:
        if r.diff.clean:
            continue
        lines.append(f"{r.scenario.name} ({r.scenario.input_corpus} -> {r.scenario.expected_corpus}):")
        for entry in r.diff.entries:
            lines.append(f"  [{entry.klass}] record {entry.record_index}: {entry.summary}")
    return "\n".join(lines)
