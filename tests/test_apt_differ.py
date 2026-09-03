"""test_apt_differ.py — gts-snub (APT semantic differ) + gts-x9un (structured
header), stage `apt-differ`.

Offline, no GAS/Google session (gts-2moy's opt-out marker) — the differ's
whole value proposition (decision 3) is that it is pure file x file, so its
correctness is provable without a live Doc. Exercises the four difference
classes (decision 4), N normalisation (decision 5) and the header parser
(gts-x9un) directly against scripts/apt_lib.py.

Each case below is deliberately hand-built rather than pulled from the
checked-in golden — the golden is the differ's future *consumer*
(apt-scenarios, stage 4), not its own test fixture; keeping this file
self-contained means the differ's classification contract can be verified
before a single scenario corpus exists.
"""
import pathlib
import sys

import pytest

pytestmark = pytest.mark.no_live_session

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import apt_lib  # noqa: E402


def _doc(*records, header="<!-- kind: capture -->\n<!-- doc: abc123 -->\n<!-- generated: 2026-08-27T00:00:00.000Z -->"):
    return header + "\n\n" + "\n\n".join(records) + "\n"


# ---------------------------------------------------------------------------
# Header parsing (gts-x9un)
# ---------------------------------------------------------------------------


class TestHeader:
    def test_parses_every_field(self):
        text = _doc(
            "ACT-1: jane@example.com do the thing (Open)",
            header=(
                "<!-- kind: golden -->\n"
                "<!-- name: action-reference -->\n"
                "<!-- doc: 1PYIU022o5dWNhIkyErjUzF6TRg--r4QrH-h-JbPNO-E -->\n"
                "<!-- serves: gts-colw, gts-ucdz -->\n"
                "<!-- generated: 2026-08-27T21:51:31.347Z -->"
            ),
        )
        header = apt_lib.parse_header(text)
        assert header == {
            "kind": "golden",
            "name": "action-reference",
            "doc": "1PYIU022o5dWNhIkyErjUzF6TRg--r4QrH-h-JbPNO-E",
            "serves": "gts-colw, gts-ucdz",
            "generated": "2026-08-27T21:51:31.347Z",
        }

    def test_missing_fields_simply_absent(self):
        text = _doc("ACT-1: x (Open)", header="<!-- kind: capture -->")
        assert apt_lib.parse_header(text) == {"kind": "capture"}

    def test_no_preamble_returns_empty_dict(self):
        text = "ACT-1: x (Open)\n"
        assert apt_lib.parse_header(text) == {}

    def test_legacy_freeform_comment_ignored_not_errored(self):
        text = "<!-- Action Portable Text v1; source doc abc; generated now -->\n\nACT-1: x (Open)\n"
        assert apt_lib.parse_header(text) == {}

    def test_format_header_round_trips_through_parse_header(self):
        fields = {"kind": "golden", "name": "n", "doc": "d", "serves": "gts-x", "generated": "t"}
        rendered = apt_lib.format_header(fields) + "\n\nACT-1: x (Open)\n"
        assert apt_lib.parse_header(rendered) == fields


# ---------------------------------------------------------------------------
# Positional — N renumbering normalised away entirely (decision 4, 5)
# ---------------------------------------------------------------------------


class TestPositional:
    def test_n_only_change_produces_no_diff_entries(self):
        golden = _doc("ACT-3: jane@example.com finish the report (Open)")
        capture = _doc("ACT-9: jane@example.com finish the report (Open)")
        result = apt_lib.diff_apt(golden, capture)
        assert result.clean
        assert result.exit_code() == 0

    def test_ai_prefix_n_change_also_normalised(self):
        golden = _doc("AI-3: jane@example.com finish the report (Open)")
        capture = _doc("AI-14: jane@example.com finish the report (Open)")
        assert apt_lib.diff_apt(golden, capture).clean

    def test_identical_records_are_clean(self):
        text = _doc("ACT-1: jane@example.com finish the report (Open)")
        assert apt_lib.diff_apt(text, text).clean

    def test_n_change_normalised_through_flushed_chip_badge_markup(self):
        # gts-iz9i, stage `apt-lanes`: a token that has been flushed at least
        # once renders as a bold link-badge, `[**ACT-N: **](url)` -- the raw
        # N-token regex is anchored at record position 0 and does not match
        # this shape without seeing through the leading `[**` the same way
        # record_token/_looks_like_plain_prose already do. Proven to fail
        # first (Backstop rules): before this fix, digits-only differing
        # inside the badge classified as `structural` ("content changed"),
        # not positional.
        golden = _doc(
            "[**ACT-999: **](https://x/y?ain=ACT-999)finish the report (Open)"
        )
        capture = _doc(
            "[**ACT-1: **](https://x/y?ain=ACT-999)finish the report (Open)"
        )
        result = apt_lib.diff_apt(golden, capture)
        assert result.clean, result.entries

    def test_n_change_normalised_through_ain_query_param_too(self):
        # gts-iz9i, flush-lane-new-assign live run: a re-flushed badge's N
        # changes in BOTH places at once -- the leading label AND the
        # chip-preview URL's `ain=` query param (test above only varied the
        # label, leaving `ain=` fixed, so it never caught this). Proven to
        # fail first: before this fix, the label normalised but `ain=ACT-999`
        # vs `ain=ACT-1` still differed, classifying as `presentational`
        # ("formatting/whitespace only") instead of clean/positional.
        golden = _doc(
            "[**ACT-999: **](https://x/y?docId=D&ain=ACT-999)finish the report (Open)"
        )
        capture = _doc(
            "[**ACT-1: **](https://x/y?docId=D&ain=ACT-1)finish the report (Open)"
        )
        result = apt_lib.diff_apt(golden, capture)
        assert result.clean, result.entries


# ---------------------------------------------------------------------------
# Bare-trigger -> assigned-token first flush (gts-py21).
#
# A hand-authored doc writes a bare `ACT: ` trigger with no markup, no N and
# no status. Its FIRST sync mints all three at once (ADR-0027 rule 4) and
# rewrites the record's continuation fields into their canonical
# `**Label:**\t` spelling. Diffing that doc's own pre-sync APT against a
# synced copy of it (tests/test_floating_action_copy_fidelity.py) must read
# that one transition as the system doing its job -- while still catching
# anything else the same flush changed.
# ---------------------------------------------------------------------------


def _bare(body):
    return _doc(f"ACT: {body}")


def _assigned(body, n=7, status=" (Open)"):
    return _doc(
        f"[**ACT-{n}: **](https://northlakeuu.org/NUUTS?cmd=preview&docId=D&ain=ACT-{n})"
        f"{body}{status}"
    )


class TestBareTriggerFirstFlush:
    def test_bare_trigger_to_assigned_token_is_clean(self):
        # The whole transition at once: bare -> bold preview-linked token,
        # N minted, ` (Open)` minted. Proven to fail first (Backstop rules):
        # before this normalisation the pair classified `structural`
        # ("content changed"), then -- after the N and status halves alone
        # were normalised -- `presentational`, which still left
        # AptDiffResult.clean False.
        golden = _bare("{{chip:jane@example.com}} finish the report")
        capture = _assigned("{{chip:jane@example.com}} finish the report")
        assert apt_lib.diff_apt(golden, capture).clean

    def test_continuation_fields_canonicalised_on_the_same_flush_are_clean(self):
        # ADR-0027 rule 5/5a: a hand-typed `Field-1: v` line comes back from
        # its first flush as `**Field-1:**\tv` (_renderCustomFieldLines).
        golden = _bare("finish the report<SR>\nField-1: first value<SR>\nField-2: second")
        capture = _assigned(
            "finish the report", status=" (Open)"
        ).replace(
            "finish the report (Open)",
            "finish the report (Open)<SR>\n**Field-1:**\tfirst value<SR>\n**Field-2:**\tsecond",
        )
        assert apt_lib.diff_apt(golden, capture).clean

    def test_li_prefixed_bare_trigger_transition_is_clean(self):
        golden = _doc("<LI> ACT: {{chip:jane@example.com}} finish the report")
        capture = _doc(
            "<LI> [**ACT-4: **](https://x/y?docId=D&ain=ACT-4)"
            "{{chip:jane@example.com}} finish the report (Open)"
        )
        assert apt_lib.diff_apt(golden, capture).clean

    def test_token_on_a_continuation_line_transitions_too(self):
        # The live shape this bead's GAS fixes were about: a list item whose
        # own intro text comes first and whose ACT: trigger sits on a soft-
        # return continuation line. src/SyncManager.js scans every line of a
        # paragraph for a token, so the differ must normalise N (and this
        # transition) on every line too -- not only a record's first.
        # Proven to fail first: with the record-first-line-only anchoring,
        # these pairs classified `structural` ("content changed") because the
        # token's own digits were never normalised at all.
        golden = _doc(
            "<LI> This is a numbered entry and an act starts next:<SR>\n"
            "ACT: {{chip:jane@example.com}} finish the report"
        )
        capture = _doc(
            "<LI> This is a numbered entry and an act starts next:<SR>\n"
            "[**ACT-13: **](https://x/y?docId=D&ain=ACT-13)"
            "{{chip:jane@example.com}} finish the report (Open)"
        )
        assert apt_lib.diff_apt(golden, capture).clean

    def test_continuation_line_token_still_reports_a_dropped_chip(self):
        golden = _doc(
            "<LI> This is a numbered entry and an act starts next:<SR>\n"
            "ACT: {{chip:jane@example.com}} finish the report"
        )
        capture = _doc(
            "<LI> This is a numbered entry and an act starts next:<SR>\n"
            "[**ACT-13: **](https://x/y?docId=D&ain=ACT-13)finish the report (Open)"
        )
        assert not apt_lib.diff_apt(golden, capture).clean

    # --- negative proofs: the normalisation must not swallow a real change ---

    def test_person_chip_dropped_on_the_same_flush_is_still_reported(self):
        # The live defect this bead fixed on the GAS side (list-item records
        # whose token follows an intro line lost their PERSON chip on flush).
        # If the transition normalisation hid this, the copy-fidelity oracle
        # would have gone green over a real data loss.
        golden = _bare("{{chip:jane@example.com}} finish the report")
        capture = _assigned("finish the report")
        assert not apt_lib.diff_apt(golden, capture).clean

    def test_trailing_blank_line_dropped_on_the_same_flush_is_still_reported(self):
        golden = _bare("finish the report<SR>\n+ a plus bullet<SR>\n<BLANK>")
        capture = _assigned("finish the report").replace(
            "finish the report (Open)", "finish the report (Open)<SR>\n+ a plus bullet"
        )
        result = apt_lib.diff_apt(golden, capture)
        # Class is left unpinned on purpose: _strip_markup() drops the
        # <SR>/<BLANK> sentinels, so a record whose ONLY loss is a trailing
        # blank line reaches the plain-text-equality shortcut before the
        # line-count check and lands `presentational` rather than
        # `preservation`. Pre-existing differ ordering, unrelated to this
        # normalisation; what matters here is that the transition rule does
        # not make it clean.
        assert not result.clean

    def test_prose_edited_on_the_same_flush_is_still_reported(self):
        golden = _bare("finish the report")
        capture = _assigned("finish the OTHER report")
        assert not apt_lib.diff_apt(golden, capture).clean

    def test_hand_authored_status_is_not_normalised_away(self):
        # A status the original already carried is an INPUT to the flush, not
        # something the flush minted -- so a status that changes across the
        # transition must still diff.
        golden = _bare("finish the report (Done)")
        capture = _assigned("finish the report", status=" (Open)")
        assert not apt_lib.diff_apt(golden, capture).clean

    def test_hand_authored_status_preserved_across_the_transition_is_clean(self):
        golden = _bare("finish the report (Done)")
        capture = _assigned("finish the report", status=" (Done)")
        assert apt_lib.diff_apt(golden, capture).clean

    def test_normalisation_does_not_apply_to_an_already_assigned_record(self):
        # No bare trigger on the golden side => not a first flush => the
        # status suffix and field canonicalisation stay fully visible.
        golden = _doc("ACT-7: finish the report (Open)")
        capture = _doc("ACT-7: finish the report (Done)")
        assert not apt_lib.diff_apt(golden, capture).clean


# ---------------------------------------------------------------------------
# List-item container (gts-83s5, APT v2) — N normalisation and the
# decision-9 annotation lint must see through the `<LI> ` marker exactly as
# they do a plain paragraph's absence of any marker.
# ---------------------------------------------------------------------------


class TestListItemContainer:
    def test_li_prefixed_record_still_gets_n_normalised(self):
        golden = _doc("<LI> ACT-3: jane@example.com finish the report (Open)")
        capture = _doc("<LI> ACT-9: jane@example.com finish the report (Open)")
        assert apt_lib.diff_apt(golden, capture).clean

    def test_li_prefixed_record_content_change_still_detected(self):
        golden = _doc("<LI> ACT-3: jane@example.com finish the report (Open)")
        capture = _doc("<LI> ACT-3: jane@example.com finish the OTHER report (Open)")
        result = apt_lib.diff_apt(golden, capture)
        assert not result.clean

    def test_unannotated_li_action_is_flagged(self):
        text = _doc("<LI> ACT-3: jane@example.com finish the report (Open)")
        assert apt_lib.unannotated_records(text) == [0]

    def test_annotated_li_action_is_not_flagged(self):
        text = _doc(
            "Case 1: a bulleted list item carrying an action.",
            "<LI> ACT-3: jane@example.com finish the report (Open)",
        )
        assert apt_lib.unannotated_records(text) == []


# ---------------------------------------------------------------------------
# Presentational — indent, tab-vs-space, bold, field render order (decision 4)
# ---------------------------------------------------------------------------


class TestPresentational:
    def test_bold_marker_added_is_presentational(self):
        golden = _doc("ACT-1: jane@example.com finish the report (Open)")
        capture = _doc("ACT-1: jane@example.com **finish** the report (Open)")
        result = apt_lib.diff_apt(golden, capture)
        assert result.classes_present == {apt_lib.PRESENTATIONAL}
        assert result.exit_code() == 1

    def test_tab_vs_space_indent_is_presentational(self):
        golden = _doc("ACT-1: jane@example.com x (Open)<SR>\nDue: Tuesday")
        capture = _doc("ACT-1: jane@example.com x (Open)<SR>\n  Due: Tuesday")
        result = apt_lib.diff_apt(golden, capture)
        assert result.classes_present == {apt_lib.PRESENTATIONAL}

    def test_bulk_blessable_means_every_entry_is_presentational_only(self):
        golden = _doc(
            "ACT-1: jane@example.com x (Open)",
            "ACT-2: jane@example.com y (Open)",
        )
        capture = _doc(
            "ACT-1: jane@example.com **x** (Open)",
            "ACT-2: jane@example.com _y_ (Open)",
        )
        result = apt_lib.diff_apt(golden, capture)
        assert len(result.entries) == 2
        assert result.classes_present == {apt_lib.PRESENTATIONAL}


# ---------------------------------------------------------------------------
# Structural — record/field added or removed (decision 4)
# ---------------------------------------------------------------------------


class TestStructural:
    def test_field_added_is_structural(self):
        golden = _doc("ACT-1: jane@example.com x (Open)")
        capture = _doc("ACT-1: jane@example.com x (Open)<SR>\nDue: Tuesday")
        result = apt_lib.diff_apt(golden, capture)
        assert result.classes_present == {apt_lib.STRUCTURAL}
        assert "added" in result.entries[0].summary

    def test_field_removed_is_structural(self):
        # Same line count on both sides (a field line replaced by a plain
        # prose line, not deleted outright) isolates "field removed" from
        # the line-count-reduced preservation case below — decision 4's
        # ambiguity rule means a field removal that ALSO shrinks the line
        # count must classify as preservation instead (the stricter tier),
        # which is exercised separately in TestPreservation.
        golden = _doc("ACT-1: jane@example.com x (Open)<SR>\nDue: Tuesday<SR>\nNotes: ok")
        capture = _doc("ACT-1: jane@example.com x (Open)<SR>\nsome unrelated prose<SR>\nNotes: ok")
        result = apt_lib.diff_apt(golden, capture)
        assert result.classes_present == {apt_lib.STRUCTURAL}
        assert "removed" in result.entries[0].summary

    def test_record_added_is_structural(self):
        golden = _doc("ACT-1: jane@example.com x (Open)")
        capture = _doc(
            "ACT-1: jane@example.com x (Open)",
            "ACT-2: jane@example.com y (Open)",
        )
        result = apt_lib.diff_apt(golden, capture)
        assert result.classes_present == {apt_lib.STRUCTURAL}
        assert result.entries[0].summary == "record added"

    def test_record_removed_is_structural(self):
        golden = _doc(
            "ACT-1: jane@example.com x (Open)",
            "ACT-2: jane@example.com y (Open)",
        )
        capture = _doc("ACT-1: jane@example.com x (Open)")
        result = apt_lib.diff_apt(golden, capture)
        assert result.classes_present == {apt_lib.STRUCTURAL}
        assert result.entries[0].summary == "record removed"
        assert result.exit_code() == 2


# ---------------------------------------------------------------------------
# Preservation — dropped link, lost run, shortened value, reduced line count
# (decision 4) — itemised, never bulk-blessable.
# ---------------------------------------------------------------------------


class TestPreservation:
    def test_link_dropped_is_preservation(self):
        golden = _doc("ACT-1: jane@example.com see [the doc](https://example.com/x) (Open)")
        capture = _doc("ACT-1: jane@example.com see the doc (Open)")
        result = apt_lib.diff_apt(golden, capture)
        assert result.classes_present == {apt_lib.PRESERVATION}
        assert result.entries[0].summary == "link dropped"
        assert result.exit_code() == 3

    def test_line_count_reduced_is_preservation(self):
        golden = _doc(
            "ACT-1: jane@example.com x (Open)<SR>\nConsult With:<SR>\n- Stuart<SR>\n- John"
        )
        capture = _doc("ACT-1: jane@example.com x (Open)<SR>\nConsult With:<SR>\n- Stuart")
        result = apt_lib.diff_apt(golden, capture)
        assert result.classes_present == {apt_lib.PRESERVATION}
        assert result.entries[0].summary == "line count reduced"

    def test_value_shortened_is_preservation(self):
        golden = _doc("ACT-1: jane@example.com x (Open)<SR>\nNotes: the full detailed explanation")
        capture = _doc("ACT-1: jane@example.com x (Open)<SR>\nNotes: the full")
        result = apt_lib.diff_apt(golden, capture)
        assert result.classes_present == {apt_lib.PRESERVATION}
        assert result.entries[0].summary == "value shortened"

    def test_field_removed_and_line_count_reduced_resolves_to_preservation(self):
        # A field line deleted outright is BOTH "field removed" (structural)
        # and "line count reduced" (preservation) — decision 4's ambiguity
        # rule picks the stricter tier.
        golden = _doc("ACT-1: jane@example.com x (Open)<SR>\nDue: Tuesday")
        capture = _doc("ACT-1: jane@example.com x (Open)")
        result = apt_lib.diff_apt(golden, capture)
        assert result.classes_present == {apt_lib.PRESERVATION}

    def test_ambiguous_case_resolves_to_strictest_tier(self):
        # A link dropped AND a bold marker added on the same record: the
        # presentational-looking bold change must not mask the preservation
        # concern (decision 4: ambiguity classifies to the strictest tier).
        golden = _doc("ACT-1: jane@example.com see [the doc](https://example.com/x) (Open)")
        capture = _doc("ACT-1: jane@example.com see **the doc** (Open)")
        result = apt_lib.diff_apt(golden, capture)
        assert result.classes_present == {apt_lib.PRESERVATION}


# ---------------------------------------------------------------------------
# New-assertion backstop: prove the differ can actually fail (Backstop
# rules, project CLAUDE.md) — a clean pair produces zero entries and exit 0.
# ---------------------------------------------------------------------------


class TestCleanPairBackstop:
    def test_identical_multi_record_corpus_is_clean(self):
        golden = _doc(
            "ACT-1: jane@example.com x (Open)",
            "ACT-2: jane@example.com y (Open)<SR>\nDue: Tuesday",
        )
        result = apt_lib.diff_apt(golden, golden)
        assert result.clean
        assert result.exit_code() == 0


# ---------------------------------------------------------------------------
# Capture-store retention helper (gts-x9un)
# ---------------------------------------------------------------------------


class TestCaptureRetention:
    def test_keeps_last_n_evicts_oldest(self):
        names = ["c1", "c2", "c3", "c4", "c5"]
        assert apt_lib.captures_to_evict(names, keep_last_n=2) == ["c1", "c2", "c3"]

    def test_no_eviction_when_under_the_limit(self):
        assert apt_lib.captures_to_evict(["c1", "c2"], keep_last_n=5) == []

    def test_keep_zero_evicts_everything(self):
        assert apt_lib.captures_to_evict(["c1", "c2"], keep_last_n=0) == ["c1", "c2"]

    def test_negative_keep_last_n_rejected(self):
        with pytest.raises(ValueError):
            apt_lib.captures_to_evict(["c1"], keep_last_n=-1)
