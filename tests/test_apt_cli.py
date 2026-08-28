"""test_apt_cli.py — gts-4bop, stage `apt-cli`. Offline, no GAS/Google
session: `call_webapp.call_action` is monkeypatched to a fake so these tests
exercise apt.py's own logic (corpus/doc-id resolution, capture-store
writing/eviction, the push drift guard, bless's tiered acknowledgment, exit
codes) without a live WebApp. `scripts/apt_lib.py`'s differ itself is covered
by tests/test_apt_differ.py; this file is the CLI glue on top of it.
"""
import pathlib
import sys

import pytest

pytestmark = pytest.mark.no_live_session

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import apt  # noqa: E402
import apt_lib  # noqa: E402

_GOLDEN = (
    "<!-- kind: golden -->\n"
    "<!-- name: sample -->\n"
    "<!-- doc: DOC123 -->\n"
    "<!-- serves: gts-4bop -->\n"
    "<!-- generated: 2026-08-28T00:00:00.000Z -->\n"
    "\n"
    "ACT-1: do the thing (Open)\n"
)


@pytest.fixture(autouse=True)
def _isolated_dirs(tmp_path, monkeypatch):
    """Redirects apt.py's module-level paths into a scratch tree so no test
    touches the real tests/fixtures/ or .apt-captures/."""
    fixtures_dir = tmp_path / "fixtures"
    captures_dir = tmp_path / "captures"
    fixtures_dir.mkdir()
    monkeypatch.setattr(apt, "FIXTURES_DIR", fixtures_dir)
    monkeypatch.setattr(apt, "CAPTURES_DIR", captures_dir)
    monkeypatch.setattr(apt, "_SETTINGS_PATH", tmp_path / "local.settings.json")
    return fixtures_dir, captures_dir


def _write_golden(fixtures_dir, name="sample", text=_GOLDEN):
    (fixtures_dir / f"{name}.apt.txt").write_text(text, encoding="utf-8")


class _FakeWebapp:
    """Records every call and replays a scripted queue of responses, so a
    test can assert exactly which fixture/docId apt.py sent without a real
    HTTP round trip."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, action, extra=None, *, env="test", auth=None):
        self.calls.append((action, extra, env))
        if not self.responses:
            raise AssertionError(f"unexpected extra call_action: {action} {extra}")
        return self.responses.pop(0)


# ---------------------------------------------------------------------------
# Doc-id resolution
# ---------------------------------------------------------------------------

class TestResolveDocId:
    def test_explicit_flag_wins(self):
        assert apt.resolve_doc_id("sample", _GOLDEN, "OVERRIDE") == "OVERRIDE"

    def test_falls_back_to_golden_header(self):
        assert apt.resolve_doc_id("sample", _GOLDEN, None) == "DOC123"

    def test_action_reference_falls_back_to_settings(self, tmp_path):
        apt._SETTINGS_PATH.write_text('{"referenceDocId": "CANON1"}', encoding="utf-8")
        assert apt.resolve_doc_id("action-reference", "", None) == "CANON1"

    def test_unresolvable_raises(self):
        with pytest.raises(apt.AptCliError):
            apt.resolve_doc_id("mystery-corpus", "", None)


# ---------------------------------------------------------------------------
# pull
# ---------------------------------------------------------------------------

class TestPull:
    def test_clean_pull_exits_zero_and_writes_no_new_capture_content_mismatch(self, _isolated_dirs, monkeypatch):
        fixtures_dir, captures_dir = _isolated_dirs
        _write_golden(fixtures_dir)
        fake = _FakeWebapp([
            {"data": {"ok": True, "apt": "\n\nACT-1: do the thing (Open)\n"}},
        ])
        monkeypatch.setattr(apt.call_webapp, "call_action", fake)
        rc = apt.cmd_pull("sample", doc=None, env="test", keep_last_n=10)
        assert rc == 0
        assert fake.calls == [("run_fixture", {"fixture": "encode_reference_document", "docId": "DOC123"}, "test")]
        captured = list((captures_dir / "sample").glob("*.apt.txt"))
        assert len(captured) == 1

    def test_dirty_pull_reports_highest_class_exit_code(self, _isolated_dirs, monkeypatch):
        fixtures_dir, captures_dir = _isolated_dirs
        _write_golden(fixtures_dir)
        # Capture drops the whole record -- structural (record removed).
        fake = _FakeWebapp([{"data": {"ok": True, "apt": "\n\n"}}])
        monkeypatch.setattr(apt.call_webapp, "call_action", fake)
        rc = apt.cmd_pull("sample", doc=None, env="test", keep_last_n=10)
        assert rc == 2  # structural (record removed) -- see apt_lib._STRICTNESS

    def test_no_golden_yet_still_captures_and_reports(self, _isolated_dirs, monkeypatch):
        fixtures_dir, captures_dir = _isolated_dirs
        fake = _FakeWebapp([{"data": {"ok": True, "apt": "\n\nACT-1: new corpus (Open)\n"}}])
        monkeypatch.setattr(apt.call_webapp, "call_action", fake)
        rc = apt.cmd_pull("sample", doc="DOC999", env="test", keep_last_n=10)
        assert rc != 0  # no golden -> capture's record reads as "added" (structural)
        assert list((captures_dir / "sample").glob("*.apt.txt"))

    def test_fixture_failure_raises(self, _isolated_dirs, monkeypatch):
        fixtures_dir, captures_dir = _isolated_dirs
        _write_golden(fixtures_dir)
        fake = _FakeWebapp([{"data": {"ok": False, "error": "boom"}}])
        monkeypatch.setattr(apt.call_webapp, "call_action", fake)
        with pytest.raises(apt.AptCliError):
            apt.cmd_pull("sample", doc=None, env="test", keep_last_n=10)

    def test_capture_retention_evicts_oldest(self, _isolated_dirs, monkeypatch):
        fixtures_dir, captures_dir = _isolated_dirs
        _write_golden(fixtures_dir)
        corpus_dir = captures_dir / "sample"
        corpus_dir.mkdir(parents=True)
        for stamp in ("20260101T000000000000Z", "20260102T000000000000Z", "20260103T000000000000Z"):
            (corpus_dir / f"{stamp}.apt.txt").write_text("<!-- kind: capture -->\n\nACT-1: x (Open)\n", encoding="utf-8")
        fake = _FakeWebapp([{"data": {"ok": True, "apt": "\n\nACT-1: do the thing (Open)\n"}}])
        monkeypatch.setattr(apt.call_webapp, "call_action", fake)
        apt.cmd_pull("sample", doc=None, env="test", keep_last_n=2)
        remaining = sorted(p.name for p in corpus_dir.glob("*.apt.txt"))
        assert len(remaining) == 2  # kept the newest 2 of the 3 pre-existing + this pull's own


# ---------------------------------------------------------------------------
# push
# ---------------------------------------------------------------------------

class TestPush:
    def test_clean_doc_pushes_without_force(self, _isolated_dirs, monkeypatch):
        fixtures_dir, captures_dir = _isolated_dirs
        _write_golden(fixtures_dir)
        fake = _FakeWebapp([
            {"data": {"ok": True, "apt": "\n\nACT-1: do the thing (Open)\n"}},  # pre-push guard encode
            {"data": {"ok": True, "docId": "DOC123"}},  # decode
        ])
        monkeypatch.setattr(apt.call_webapp, "call_action", fake)
        rc = apt.cmd_push("sample", file=None, doc=None, env="test", force=False)
        assert rc == 0
        assert fake.calls[0][0:2] == ("run_fixture", {"fixture": "encode_reference_document", "docId": "DOC123"})
        assert fake.calls[1][0] == "run_fixture"
        assert fake.calls[1][1]["fixture"] == "decode_reference_document"
        assert fake.calls[1][1]["docId"] == "DOC123"

    def test_drifted_doc_refused_without_force(self, _isolated_dirs, monkeypatch):
        fixtures_dir, captures_dir = _isolated_dirs
        _write_golden(fixtures_dir)
        fake = _FakeWebapp([
            {"data": {"ok": True, "apt": "\n\nACT-1: SOMEONE HAND-EDITED THIS (Open)\n"}},
        ])
        monkeypatch.setattr(apt.call_webapp, "call_action", fake)
        rc = apt.cmd_push("sample", file=None, doc=None, env="test", force=False)
        assert rc == 1
        assert len(fake.calls) == 1  # decode never called -- refused before the write

    def test_force_overwrites_drifted_doc(self, _isolated_dirs, monkeypatch):
        fixtures_dir, captures_dir = _isolated_dirs
        _write_golden(fixtures_dir)
        fake = _FakeWebapp([
            {"data": {"ok": True, "docId": "DOC123"}},  # decode only -- guard skipped
        ])
        monkeypatch.setattr(apt.call_webapp, "call_action", fake)
        rc = apt.cmd_push("sample", file=None, doc=None, env="test", force=True)
        assert rc == 0
        assert len(fake.calls) == 1
        assert fake.calls[0][1]["fixture"] == "decode_reference_document"

    def test_no_golden_yet_skips_guard(self, _isolated_dirs, monkeypatch, tmp_path):
        fixtures_dir, captures_dir = _isolated_dirs
        source = tmp_path / "new-corpus.apt.txt"
        source.write_text("ACT-1: brand new (Open)\n", encoding="utf-8")
        fake = _FakeWebapp([{"data": {"ok": True, "docId": "DOC999"}}])
        monkeypatch.setattr(apt.call_webapp, "call_action", fake)
        rc = apt.cmd_push("sample", file=source, doc="DOC999", env="test", force=False)
        assert rc == 0
        assert len(fake.calls) == 1  # no golden -> no drift guard call


# ---------------------------------------------------------------------------
# bless
# ---------------------------------------------------------------------------

class TestBless:
    def _seed_capture(self, captures_dir, name, text, stamp="20260828T060000000000Z"):
        corpus_dir = captures_dir / name
        corpus_dir.mkdir(parents=True, exist_ok=True)
        path = corpus_dir / f"{stamp}.apt.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def test_no_capture_raises(self, _isolated_dirs):
        with pytest.raises(apt.AptCliError):
            apt.cmd_bless("sample", accept_presentational=False, assume_yes=True)

    def test_clean_capture_is_a_noop(self, _isolated_dirs):
        fixtures_dir, captures_dir = _isolated_dirs
        _write_golden(fixtures_dir)
        self._seed_capture(captures_dir, "sample", _GOLDEN)
        rc = apt.cmd_bless("sample", accept_presentational=False, assume_yes=True)
        assert rc == 0
        # Golden untouched (still exactly what was written).
        assert (fixtures_dir / "sample.apt.txt").read_text(encoding="utf-8") == _GOLDEN

    def test_presentational_only_auto_accepted_with_flag(self, _isolated_dirs):
        fixtures_dir, captures_dir = _isolated_dirs
        _write_golden(fixtures_dir)
        capture_text = (
            "<!-- kind: capture -->\n<!-- doc: DOC123 -->\n\n"
            "ACT-1:   do the thing   (Open)\n"  # whitespace-only change -- presentational
        )
        self._seed_capture(captures_dir, "sample", capture_text)
        rc = apt.cmd_bless("sample", accept_presentational=True, assume_yes=False)
        assert rc == 0
        new_golden = (fixtures_dir / "sample.apt.txt").read_text(encoding="utf-8")
        header = apt_lib.parse_header(new_golden)
        assert header["kind"] == "golden"
        assert header["serves"] == "gts-4bop"  # carried over from the prior golden

    def test_structural_diff_requires_confirmation_and_declining_aborts(self, _isolated_dirs, monkeypatch):
        fixtures_dir, captures_dir = _isolated_dirs
        _write_golden(fixtures_dir)
        capture_text = "<!-- kind: capture -->\n<!-- doc: DOC123 -->\n\nACT-1: do the thing (Open)\nDue: Monday\n"
        self._seed_capture(captures_dir, "sample", capture_text)
        monkeypatch.setattr("builtins.input", lambda *_: "n")
        rc = apt.cmd_bless("sample", accept_presentational=False, assume_yes=False)
        assert rc == 1
        assert (fixtures_dir / "sample.apt.txt").read_text(encoding="utf-8") == _GOLDEN  # untouched

    def test_preservation_diff_requires_a_reason_and_persists_it(self, _isolated_dirs, monkeypatch):
        fixtures_dir, captures_dir = _isolated_dirs
        _write_golden(fixtures_dir)
        # Drop the whole record's content down to nothing -- preservation
        # ("line count reduced") per apt_lib's classifier.
        capture_text = "<!-- kind: capture -->\n<!-- doc: DOC123 -->\n\nACT-1:\n"
        self._seed_capture(captures_dir, "sample", capture_text)
        answers = iter(["intentionally trimmed for this test", "y"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))
        rc = apt.cmd_bless("sample", accept_presentational=False, assume_yes=False)
        assert rc == 0
        new_golden = (fixtures_dir / "sample.apt.txt").read_text(encoding="utf-8")
        header = apt_lib.parse_header(new_golden)
        assert "intentionally trimmed for this test" in header.get("bless_notes", "")

    def test_preservation_diff_blank_reason_aborts(self, _isolated_dirs, monkeypatch):
        fixtures_dir, captures_dir = _isolated_dirs
        _write_golden(fixtures_dir)
        capture_text = "<!-- kind: capture -->\n<!-- doc: DOC123 -->\n\nACT-1:\n"
        self._seed_capture(captures_dir, "sample", capture_text)
        monkeypatch.setattr("builtins.input", lambda *_: "")
        rc = apt.cmd_bless("sample", accept_presentational=False, assume_yes=False)
        assert rc == 1
        assert (fixtures_dir / "sample.apt.txt").read_text(encoding="utf-8") == _GOLDEN


# ---------------------------------------------------------------------------
# diff (offline, no corpus resolution)
# ---------------------------------------------------------------------------

class TestDiff:
    def test_identical_files_exit_zero(self, tmp_path):
        a = tmp_path / "a.apt.txt"
        b = tmp_path / "b.apt.txt"
        a.write_text(_GOLDEN, encoding="utf-8")
        b.write_text(_GOLDEN, encoding="utf-8")
        assert apt.cmd_diff(a, b) == 0

    def test_missing_file_raises(self, tmp_path):
        a = tmp_path / "missing.apt.txt"
        b = tmp_path / "b.apt.txt"
        b.write_text(_GOLDEN, encoding="utf-8")
        with pytest.raises(apt.AptCliError):
            apt.cmd_diff(a, b)


# ---------------------------------------------------------------------------
# CLI wiring (main/_build_parser) -- argument plumbing only.
# ---------------------------------------------------------------------------

class TestMainWiring:
    def test_diff_verb_reaches_cmd_diff(self, tmp_path, monkeypatch):
        a = tmp_path / "a.apt.txt"
        b = tmp_path / "b.apt.txt"
        a.write_text(_GOLDEN, encoding="utf-8")
        b.write_text(_GOLDEN, encoding="utf-8")
        assert apt.main(["diff", str(a), str(b)]) == 0

    def test_apt_cli_error_from_main_prints_and_returns_1(self, tmp_path, capsys):
        a = tmp_path / "missing.apt.txt"
        b = tmp_path / "b.apt.txt"
        b.write_text(_GOLDEN, encoding="utf-8")
        rc = apt.main(["diff", str(a), str(b)])
        assert rc == 1
        assert "does not exist" in capsys.readouterr().err
