"""test_apt_fixtures_lint.py — gts-x9un: a `kind: capture` corpus must never
land in tests/fixtures/. Offline, no GAS/Google session.

This is the lint half of gts-x9un's scope; the capture-store retention half
lives in tests/test_apt_differ.py::TestCaptureRetention. Proven to actually
fail (Backstop rules, project CLAUDE.md): TestLintCatchesAViolation writes a
`kind: capture` file into a temp fixtures dir and asserts the lint rejects
it, not just that it accepts the real checked-in corpus.
"""
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
    def test_a_capture_kind_file_fails_the_same_assertion(self, tmp_path):
        offender = tmp_path / "not-a-golden.apt.txt"
        offender.write_text(
            "<!-- kind: capture -->\n<!-- doc: abc123 -->\n\nACT-1: x (Open)\n",
            encoding="utf-8",
        )
        header = apt_lib.parse_header(offender.read_text(encoding="utf-8"))
        assert header.get("kind") != "golden"
