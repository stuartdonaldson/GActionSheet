"""test_apt_fixtures_lint.py — fixture-directory lints. Offline, no
GAS/Google session.

Two lints live here, both proven to actually fail (Backstop rules, project
CLAUDE.md) against a deliberately offending fixture rather than only shown
green against the checked-in ones:

  gts-x9un — a `kind: capture` corpus must never land in tests/fixtures/;
             the capture-store retention half of that bead's scope lives in
             tests/test_apt_differ.py::TestCaptureRetention.
  gts-5st5 — a scenario declaring a state-changing mutation whose input and
             expected corpora carry identical records (modulo N) is an error
             unless it is on apt_lib's reasoned degenerate allowlist. This is
             the shape that let a sync scanning 1 of 21 actions pass every
             APT lane on 2026-08-29 (knowledge-base/staging/apt-oracle.md).
             The same `apt_lib.lint_scenarios` runs from the CLI as
             `python scripts/apt.py lint` (AC1: tooling AND pytest lane, one
             implementation).
"""
import json
import pathlib
import sys

import pytest

pytestmark = pytest.mark.no_live_session

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import apt_lib  # noqa: E402


def _apt_corpus_files():
    return sorted(FIXTURES_DIR.glob("*.apt.txt"))


class TestCheckedInFixturesAreGolden:
    def test_at_least_one_corpus_exists(self):
        # Guards against this lint passing vacuously because the glob found
        # nothing (docs/lessons-learned/resolved/2026-06-02-new-assertion-
        # vacuously-passes-on-empty-result-set.md).
        assert _apt_corpus_files(), f"no *.apt.txt found under {FIXTURES_DIR}"

    @pytest.mark.parametrize("path", _apt_corpus_files(), ids=lambda p: p.name)
    def test_corpus_declares_kind_golden(self, path):
        header = apt_lib.parse_header(path.read_text(encoding="utf-8"))
        assert header.get("kind") == "golden", (
            f"{path.relative_to(REPO_ROOT)} must declare '<!-- kind: golden -->' "
            f"(got {header.get('kind')!r}) — a 'capture' file belongs in the "
            f"gitignored .apt-captures/ store, never tests/fixtures/ (decision 1)."
        )


class TestLintCatchesAViolation:
    def test_a_capture_kind_file_fails_the_same_assertion(self):
        """Real backstop: run TestCheckedInFixturesAreGolden's own
        test_corpus_declares_kind_golden logic (not a restated inline
        assertion) against a deliberately offending file, and prove it
        fails. If the real lint check is ever removed or weakened, this
        pytest.raises would stop catching anything and fail loudly.

        The offender is written into FIXTURES_DIR itself (not tmp_path)
        because the real check's failure message calls
        path.relative_to(REPO_ROOT), which requires the path to actually
        live under the repo -- using the identical code path end-to-end is
        the point. Cleaned up in finally regardless of outcome."""
        offender = FIXTURES_DIR / "not-a-golden.apt-lint-backstop.apt.txt"
        offender.write_text(
            "<!-- kind: capture -->\n<!-- doc: abc123 -->\n\nACT-1: x (Open)\n",
            encoding="utf-8",
        )
        try:
            bound = TestCheckedInFixturesAreGolden()
            with pytest.raises(AssertionError):
                bound.test_corpus_declares_kind_golden(offender)
        finally:
            offender.unlink()


# ---------------------------------------------------------------------------
# Degenerate-scenario lint (gts-5st5)
# ---------------------------------------------------------------------------


def _write_triple(fixtures_dir, name, input_body, expected_body, *,
                  expected_name=None, kind="sync"):
    """Writes one (input corpus, mutation, expected corpus) triple into a temp
    fixtures dir. `expected_name=None` means the degenerate on-disk shape the
    lint exists to catch: the manifest's `expected` names the input corpus
    itself, so the two sides are literally the same file."""
    expected_name = expected_name or name
    (fixtures_dir / f"{name}.apt.txt").write_text(
        f"<!-- kind: golden -->\n<!-- name: {name} -->\n<!-- serves: gts-5st5 -->\n\n{input_body}\n",
        encoding="utf-8")
    if expected_name != name:
        (fixtures_dir / f"{expected_name}.apt.txt").write_text(
            f"<!-- kind: golden -->\n<!-- name: {expected_name} -->\n<!-- serves: gts-5st5 -->\n\n{expected_body}\n",
            encoding="utf-8")
    (fixtures_dir / f"{name}.scenario.json").write_text(
        json.dumps({"name": name, "input": name, "mutation": {"kind": kind},
                    "expected": expected_name, "serves": ["gts-5st5"]}),
        encoding="utf-8")


class TestCheckedInScenariosAreNotDegenerate:
    def test_at_least_one_scenario_exists(self):
        # Same vacuity guard as above: an empty glob must not read as a pass
        # (docs/lessons-learned/resolved/2026-06-02-new-assertion-vacuously-
        # passes-on-empty-result-set.md).
        assert sorted(FIXTURES_DIR.glob("*.scenario.json")), (
            f"no *.scenario.json found under {FIXTURES_DIR}")

    def test_no_scenario_is_silently_degenerate(self):
        problems = apt_lib.lint_scenarios(FIXTURES_DIR)
        assert not problems, "\n".join(problems)

    def test_every_allowlist_entry_states_a_reason(self):
        # AC3 read directly off the data structure, not only via a scenario
        # that happens to be exempt — a future entry added with an empty
        # reason must fail here even before it is exercised end to end.
        for name, reason in apt_lib.DEGENERATE_SCENARIO_ALLOWLIST.items():
            assert reason and reason.strip(), (
                f"DEGENERATE_SCENARIO_ALLOWLIST[{name!r}] states no reason")


class TestDegenerateLintCatchesAViolation:
    """Proven to fail (gts-5st5 AC4). Each case runs the SAME
    apt_lib.lint_scenarios the checked-in fixtures and `apt.py lint` run —
    never a restated inline assertion — against a deliberately offending
    fixtures dir, so weakening the real lint makes these stop catching
    anything and fail loudly."""

    def test_input_identical_to_expected_is_reported(self, tmp_path):
        # The pre-rebuild shape of all six un-batched scenarios (gts-ru4c):
        # `"expected"` naming the input corpus itself under `mutation: sync`.
        _write_triple(tmp_path, "offender",
                      "Case 1: annotation.\n\nACT-1: jane@example.com do it (Open)", None)
        problems = apt_lib.lint_scenarios(tmp_path, allowlist={})
        assert len(problems) == 1, problems
        assert "identical records" in problems[0]

    def test_a_copied_expected_file_is_still_reported(self, tmp_path):
        # Byte-identity on whole FILES would miss this: the two corpora differ
        # in their own `<!-- name: -->` preamble line while carrying identical
        # records. Comparing records is what makes the lint see through it.
        body = "Case 1: annotation.\n\nACT-1: jane@example.com do it (Open)"
        _write_triple(tmp_path, "offender", body, body, expected_name="offender-expected")
        assert (tmp_path / "offender.apt.txt").read_bytes() \
            != (tmp_path / "offender-expected.apt.txt").read_bytes()
        problems = apt_lib.lint_scenarios(tmp_path, allowlist={})
        assert len(problems) == 1, problems
        assert "identical records" in problems[0]

    def test_an_n_only_difference_is_still_reported(self, tmp_path):
        # The byte-vs-normalised design question (gts-5st5's `design` field),
        # answered: `diff_apt` normalises N positionally (decision 5), so a
        # pair differing only in its N digits is indistinguishable — to the
        # assertion this lint protects — from a pair that is identical. Raw
        # byte comparison would pass a scenario the lane still cannot fail.
        _write_triple(tmp_path, "offender",
                      "Case 1: annotation.\n\nACT-1: jane@example.com do it (Open)",
                      "Case 1: annotation.\n\nACT-77: jane@example.com do it (Open)",
                      expected_name="offender-expected")
        problems = apt_lib.lint_scenarios(tmp_path, allowlist={})
        assert len(problems) == 1, problems
        assert "identical records" in problems[0]

    def test_a_real_mutation_is_not_reported(self, tmp_path):
        # The complement: the lint must not fire on a genuine post-sync
        # expectation, or it would just be noise the next author suppresses.
        _write_triple(tmp_path, "honest",
                      "Case 1: annotation.\n\nACT-1: jane@example.com do it",
                      "Case 1: annotation.\n\nACT-1: jane@example.com do it (Open)",
                      expected_name="honest-expected")
        assert apt_lib.lint_scenarios(tmp_path, allowlist={}) == []

    def test_an_allowlisted_scenario_is_exempt(self, tmp_path):
        _write_triple(tmp_path, "degenerate-on-purpose",
                      "Case 1: annotation.\n\nACT-1 | not a token | at all", None)
        allowlist = {"degenerate-on-purpose": "rule 6: reported, never rewritten"}
        assert apt_lib.lint_scenarios(tmp_path, allowlist=allowlist) == []

    def test_an_allowlist_entry_without_a_reason_is_reported(self, tmp_path):
        _write_triple(tmp_path, "degenerate-on-purpose",
                      "Case 1: annotation.\n\nACT-1 | not a token | at all", None)
        problems = apt_lib.lint_scenarios(tmp_path, allowlist={"degenerate-on-purpose": "   "})
        assert len(problems) == 1, problems
        assert "no stated reason" in problems[0]

    def test_a_stale_allowlist_entry_is_reported(self, tmp_path):
        # An exemption that outlives the degeneracy it excused would keep a
        # real mutation permanently unasserted — the same defect one level up.
        _write_triple(tmp_path, "honest",
                      "Case 1: annotation.\n\nACT-1: jane@example.com do it",
                      "Case 1: annotation.\n\nACT-1: jane@example.com do it (Open)",
                      expected_name="honest-expected")
        problems = apt_lib.lint_scenarios(tmp_path, allowlist={"honest": "was degenerate once"})
        assert len(problems) == 1, problems
        assert "no longer" in problems[0] or "now differ" in problems[0]

    def test_an_allowlist_entry_naming_no_scenario_is_reported(self, tmp_path):
        _write_triple(tmp_path, "honest",
                      "Case 1: annotation.\n\nACT-1: jane@example.com do it",
                      "Case 1: annotation.\n\nACT-1: jane@example.com do it (Open)",
                      expected_name="honest-expected")
        problems = apt_lib.lint_scenarios(tmp_path, allowlist={"deleted-long-ago": "reason"})
        assert len(problems) == 1, problems
        assert "stale exemption" in problems[0]
