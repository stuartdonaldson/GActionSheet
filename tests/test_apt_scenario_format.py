"""test_apt_scenario_format.py — gts-ndb8 (stage `apt-scenarios`): the
scenario-triple loader (`apt_lib.load_scenario`) and the decision-9
annotation lint (`apt_lib.unannotated_records`). Offline, no GAS/Google
session — pure data marshaling and text inspection (decision 3).
"""
import pathlib
import sys

import pytest

pytestmark = pytest.mark.no_live_session

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import apt_lib  # noqa: E402


def _scenario_files():
    return sorted(FIXTURES_DIR.glob("*.scenario.json"))


def _corpus_files():
    # Every *.apt.txt except the legacy monolith, which predates decision 9's
    # per-record annotation convention (gts-colw closed before gts-ndb8
    # existed) and is not itself a scenario-triple corpus.
    return sorted(p for p in FIXTURES_DIR.glob("*.apt.txt") if p.name != "action-reference.apt.txt")


# ---------------------------------------------------------------------------
# Scenario triple loader
# ---------------------------------------------------------------------------


class TestLoadScenario:
    def test_at_least_one_scenario_exists(self):
        assert _scenario_files(), f"no *.scenario.json found under {FIXTURES_DIR}"

    @pytest.mark.parametrize("path", _scenario_files(), ids=lambda p: p.name)
    def test_scenario_parses(self, path):
        scenario = apt_lib.load_scenario(path)
        assert scenario.input_corpus
        assert scenario.expected_corpus
        assert scenario.mutation.get("kind")
        assert (FIXTURES_DIR / f"{scenario.input_corpus}.apt.txt").exists(), (
            f"{path.name} names input corpus {scenario.input_corpus!r} which "
            "does not exist"
        )
        assert (FIXTURES_DIR / f"{scenario.expected_corpus}.apt.txt").exists(), (
            f"{path.name} names expected corpus {scenario.expected_corpus!r} "
            "which does not exist"
        )

    @pytest.mark.parametrize("path", _scenario_files(), ids=lambda p: p.name)
    def test_every_scenario_names_a_bead(self, path):
        # gts-ndb8's own "must not" clause is about the CORPUS header's
        # serves: field; scenario manifests get the same expectation for the
        # same reason -- an unattributed scenario is how goldens proliferate
        # and then rot.
        scenario = apt_lib.load_scenario(path)
        assert scenario.serves, f"{path.name} names no bead in 'serves'"

    def test_missing_required_key_rejected(self, tmp_path):
        bad = tmp_path / "broken.scenario.json"
        bad.write_text('{"input": "x", "expected": "x"}', encoding="utf-8")
        with pytest.raises(ValueError, match="mutation"):
            apt_lib.load_scenario(bad)

    def test_mutation_without_kind_rejected(self, tmp_path):
        bad = tmp_path / "broken.scenario.json"
        bad.write_text('{"input": "x", "mutation": {}, "expected": "x"}', encoding="utf-8")
        with pytest.raises(ValueError, match="kind"):
            apt_lib.load_scenario(bad)

    def test_degenerate_case_detected(self, tmp_path):
        path = tmp_path / "reflexive.scenario.json"
        path.write_text(
            '{"input": "x", "mutation": {"kind": "sync"}, "expected": "x"}',
            encoding="utf-8",
        )
        scenario = apt_lib.load_scenario(path)
        assert scenario.is_degenerate

    def test_non_sync_mutation_is_not_degenerate(self, tmp_path):
        path = tmp_path / "mutated.scenario.json"
        path.write_text(
            '{"input": "x", "mutation": {"kind": "sheet_edit"}, "expected": "y"}',
            encoding="utf-8",
        )
        scenario = apt_lib.load_scenario(path)
        assert not scenario.is_degenerate


# ---------------------------------------------------------------------------
# Decision-9 annotation lint
# ---------------------------------------------------------------------------


class TestAnnotationLint:
    def test_at_least_one_split_corpus_exists(self):
        assert _corpus_files(), f"no split corpora found under {FIXTURES_DIR}"

    @pytest.mark.parametrize("path", _corpus_files(), ids=lambda p: p.name)
    def test_every_action_record_is_annotated(self, path):
        text = path.read_text(encoding="utf-8")
        offenders = apt_lib.unannotated_records(text)
        assert not offenders, (
            f"{path.relative_to(REPO_ROOT)}: record(s) {offenders} carry an "
            "action token with no preceding plain-prose annotation (decision 9)"
        )

    def test_lint_catches_an_unannotated_record(self):
        # Backstop rules: a new assertion must be proven to fail before
        # acceptance. Two action records back-to-back, no annotation between
        # them -- the second must be flagged.
        text = (
            "<!-- kind: golden -->\n<!-- name: x -->\n\n"
            "ACT-1: jane@example.com first (Open)\n\n"
            "ACT-2: jane@example.com second (Open)\n"
        )
        assert apt_lib.unannotated_records(text) == [0, 1]

    def test_lint_accepts_a_properly_annotated_record(self):
        text = (
            "<!-- kind: golden -->\n<!-- name: x -->\n\n"
            "Case 1: demonstrates something.\n\n"
            "ACT-1: jane@example.com first (Open)\n"
        )
        assert apt_lib.unannotated_records(text) == []


# ---------------------------------------------------------------------------
# Every split corpus declares serves: (must-not clause, stage apt-scenarios)
# ---------------------------------------------------------------------------


class TestCorpusServes:
    @pytest.mark.parametrize("path", _corpus_files(), ids=lambda p: p.name)
    def test_corpus_names_a_bead(self, path):
        header = apt_lib.parse_header(path.read_text(encoding="utf-8"))
        assert header.get("serves"), (
            f"{path.relative_to(REPO_ROOT)} declares no 'serves:' -- a corpus "
            "naming no bead is how goldens proliferate and then rot."
        )
