"""test_apt_lane_lib.py — offline unit tests for the pure half of stage
`apt-lanes`' batched runner (staged plan apt-testing.md, gts-iz9i/gts-pi1s):
`apt_lib.record_token`, `apt_lib.compose_corpora`, `apt_lib.slice_records`.
No GAS/Google session (decision 3 — these are text-only operations; the live
half lives in tests/support/apt_lane_runner.py and is exercised by
tests/test_apt_flush_lane.py).
"""
import pathlib
import sys

import pytest

pytestmark = pytest.mark.no_live_session

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import apt_lib  # noqa: E402


class TestRecordToken:
    def test_plain_paragraph_token(self):
        assert apt_lib.record_token("ACT-3: jane@example.com do it (Open)") == "ACT-3"

    def test_legacy_ai_prefix(self):
        assert apt_lib.record_token("AI-10: do it (Open)") == "AI-10"

    def test_list_item_marker_seen_through(self):
        assert apt_lib.record_token("<LI> ACT-60: jane@example.com do it (Open)") == "ACT-60"

    def test_soft_return_first_line(self):
        assert apt_lib.record_token("ACT-1: header<SR>\nNotes: continued") == "ACT-1"

    def test_no_token_returns_none(self):
        assert apt_lib.record_token("just some prose, not an action") is None
        assert apt_lib.record_token("<EMPTY>") is None


class TestComposeCorpora:
    def _corpus(self, *records):
        return "<!-- kind: golden -->\n<!-- name: x -->\n\n" + "\n\n".join(records)

    def test_composes_records_in_order_with_ranges(self):
        a = self._corpus("ACT-1: a (Open)", "ACT-2: b (Open)")
        b = self._corpus("ACT-3: c (Open)")
        composed, ranges = apt_lib.compose_corpora([("a", a), ("b", b)])
        assert apt_lib.split_records(composed) == [
            "ACT-1: a (Open)", "ACT-2: b (Open)", "ACT-3: c (Open)",
        ]
        assert ranges == {"a": (0, 2), "b": (2, 3)}

    def test_table_corpus_must_be_last(self):
        table = self._corpus("<TABLE rows=1 cols=1>", "<CELL 0,0>", "ACT-1: a (Open)", "</TABLE>")
        plain = self._corpus("ACT-2: b (Open)")
        with pytest.raises(ValueError, match="not last"):
            apt_lib.compose_corpora([("table", table), ("plain", plain)])

    def test_table_corpus_last_is_fine(self):
        plain = self._corpus("ACT-2: b (Open)")
        table = self._corpus("<TABLE rows=1 cols=1>", "<CELL 0,0>", "ACT-1: a (Open)", "</TABLE>")
        composed, ranges = apt_lib.compose_corpora([("plain", plain), ("table", table)])
        assert ranges["table"][1] == len(apt_lib.split_records(composed))


class TestSliceRecords:
    def test_round_trips_through_compose(self):
        a = "<!-- kind: golden -->\n<!-- name: a -->\n\nACT-1: a (Open)\n\nACT-2: b (Open)"
        b = "<!-- kind: golden -->\n<!-- name: b -->\n\nACT-3: c (Open)"
        composed, ranges = apt_lib.compose_corpora([("a", a), ("b", b)])
        assert apt_lib.slice_records(composed, *ranges["a"]) == "ACT-1: a (Open)\n\nACT-2: b (Open)"
        assert apt_lib.slice_records(composed, *ranges["b"]) == "ACT-3: c (Open)"
