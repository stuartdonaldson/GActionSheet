"""test_apt_corpus_check.py — gts-ndb8, stage `apt-scenarios`.

The "apt check"-equivalent pytest lane the staged plan's stage-4 deliverable
names: it runs every checked-in scenario triple (`tests/fixtures/*.scenario.json`)
through the SAME differ `scripts/apt.py` uses (`apt_lib.diff_apt` — decision 8,
one implementation shared by CLI and pytest) and fails on any non-clean exit.
Live-backend, not offline: applying a mutation and capturing the result needs
a real Doc (decision 3 keeps the differ itself network-free; this lane is
what supplies the Doc that differ then compares against).

This stage (`apt-scenarios`) only implements the degenerate mutation kind
`sync` (Terminology: "read-only reference = degenerate case, mutation is
'sync once'") — a corpus is decoded into a fresh doc, synced once, captured,
and must diff clean against its own golden (encode(decode(x)) survives a
sync unchanged). Non-degenerate kinds (a sheet edit, an `@create` insertion)
are stage `apt-lanes`' job; a scenario naming one here fails loudly with a
"not yet implemented" message naming that stage, rather than silently
skipping — a skipped scenario is a coverage gap wearing a green checkmark.

This lane is DISTINCT from tests/test_adr0027_reference_document.py, which
asserts field-by-field grammar semantics against the single legacy
action-reference.apt.txt corpus. This lane asserts a cheaper, generic
invariant — round-trip fidelity — across every split per-boundary corpus
(gts-vr24/act-triage decides the legacy file's fate; both coexist until
then, per the staged plan's own thesis that stages don't collapse until
`act-retire`).
"""
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import apt_lib  # noqa: E402

from scn.session import ScenarioSession  # noqa: E402


def _scenario_files():
    return sorted(FIXTURES_DIR.glob("*.scenario.json"))


def _corpus_text(name: str) -> str:
    path = FIXTURES_DIR / f"{name}.apt.txt"
    assert path.exists(), f"scenario names corpus {name!r} but {path} does not exist"
    return path.read_text(encoding="utf-8")


class TestAtLeastOneScenarioExists:
    def test_scenario_files_exist(self):
        # docs/lessons-learned/resolved/2026-06-02-new-assertion-vacuously-
        # passes-on-empty-result-set.md — guard against this lane passing
        # vacuously because the glob found nothing.
        assert _scenario_files(), f"no *.scenario.json found under {FIXTURES_DIR}"


@pytest.mark.parametrize("path", _scenario_files(), ids=lambda p: p.stem.removesuffix(".scenario"))
class TestScenarioRoundTrip:
    def test_scenario_diffs_clean(self, settings, path):
        scenario = apt_lib.load_scenario(path)
        if scenario.batch:
            pytest.skip(
                f"{path.name}: owned by batched runner {scenario.batch!r} "
                "(tests/support/apt_lane_runner.py, stage `apt-lanes`) — executing "
                "it here too would reintroduce the one-doc-per-scenario shape that "
                "runner exists to avoid. See tests/test_apt_flush_lane.py."
            )
        kind = scenario.mutation.get("kind")
        if kind != "sync":
            pytest.fail(
                f"{path.name}: mutation kind {kind!r} is not implemented by stage "
                "`apt-scenarios` — non-degenerate mutations (sheet edits, @create) "
                "are stage `apt-lanes`' job (gts-iz9i/gts-pi1s). Not skipping: an "
                "unimplemented mutation is a coverage gap, not a pass."
            )

        input_text = _corpus_text(scenario.input_corpus)
        expected_text = _corpus_text(scenario.expected_corpus)

        scn = ScenarioSession.new_doc(settings)
        try:
            resp = scn._post_fixture("decode_reference_document", {"apt": input_text})
            assert (resp.get("data") or {}).get("ok"), (
                f"{path.name}: decode_reference_document failed: {resp}"
            )
            scn.sync()  # the degenerate scenario's mutation: "sync once"

            resp = scn._post_fixture("encode_reference_document")
            data = resp.get("data") or {}
            assert data.get("ok"), f"{path.name}: encode_reference_document failed: {resp}"
            # A chip-badge preview link on any token this sync flushed carries
            # THIS run's own randomly-generated doc id (decision 7: a scenario
            # corpus is doc-less and materialises into a fresh new_doc() every
            # run), so a golden cannot hardcode it and spells the placeholder
            # DOC_ID instead. Same single substitution point, for the same
            # reason, as tests/support/apt_lane_runner.py::run_lane — the
            # batched lane needed it first only because every scenario in it
            # forces a re-flush; stage `apt-corpora-rebuild` (gts-ru4c) made
            # the scenarios in THIS lane force one too.
            captured_text = data["apt"].replace(scn.doc_id, "DOC_ID")
        finally:
            scn.close()

        result = apt_lib.diff_apt(expected_text, captured_text)
        if not result.clean:
            lines = [f"{path.name}: {scenario.input_corpus} -> sync -> "
                     f"{scenario.expected_corpus} did not diff clean:"]
            for entry in result.entries:
                lines.append(f"  [{entry.klass}] record {entry.record_index}: {entry.summary}")
            pytest.fail("\n".join(lines))
