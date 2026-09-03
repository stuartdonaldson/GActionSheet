"""
test_continuation_indent_config.py — [TST] for gts-9a4j, extended for gts-x8wy.

Regression coverage for ADR-0027 rule 8's continuation-line indent, made
configurable (human decision 2026-08-29, recorded on gts-9a4j): the Config
sheet's 'SR Indent' key controls the leading-space indent applied to
action-text soft-return continuation lines on flush; 'Field SR Indent'
independently controls the same for a custom field's own LABEL line
(_renderCustomFieldLines). Both default to '' (flush-left) when absent, which
is why every pre-existing flush test (tests/test_field_continuation_flush.py)
is unaffected by this change -- it never sets either key.

This file proves the positive case those tests don't cover: with both keys
set to distinct positive values, a flush indents each kind of continuation
line by its own configured amount, and a subsequent re-scan (independent of
what was just written -- debug_action_runs opens the doc fresh) reads back
the same action text and field values, unindented, exactly as the parser's
leading-whitespace-stripping (ADR-0027 rule 5) requires -- proving the fix
threads through _parseFieldContinuationBlocksTracked, which previously had
no such strip on the JS side (found live while researching gts-9a4j,
2026-08-29 -- doc_inspect.py's Python oracle already stripped it, but the
GAS scanner used by every live sync did not).

gts-x8wy (2026-09-02) extended the same Config keys two ways, covered below
rather than in a new file (test-functional coverage-inventory: this suite
already owns the SR-indent oracle, so the extension belongs here):
  - A Config value that isn't a plain number is now a literal \\t/\\s escape
    template (\\t -> tab, \\s -> space), not just N spaces.
  - A new 'Field SR SR Indent' key controls a continuation line WITHIN a
    field's own multi-line value, independently of 'Field SR Indent' (which
    now covers only that field's LABEL line). Unset, it defaults to
    'Field SR Indent' + 'SR Indent' concatenated -- which is why
    test_configured_indent_applies_on_flush_and_round_trips' expected
    "- more detail" indent below is 8 spaces (3 + 5), not the pre-gts-x8wy 3.
"""
from scn.session import ScenarioSession

from tests.helpers.doc_inspect import (
    load_doc,
    paragraph_bold_text,
    paragraph_texts_with_breaks,
)
from tests.helpers.download import download_docx


def _paras_containing(scn, needle):
    return [
        p for p in paragraph_texts_with_breaks(load_doc(download_docx(scn.doc_id)))
        if needle in p
    ]


def _scan(scn, n: int = 1) -> dict:
    resp = scn._post_fixture("debug_action_runs", {"n": n})
    data = resp.get("data") or {}
    assert data.get("ok"), f"debug_action_runs fixture failed: {resp!r}"
    return data


def test_configured_indent_applies_on_flush_and_round_trips(settings, request):
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        set_sr = scn._post_fixture("set_config_row", {"key": "SR Indent", "value": 5})
        assert (set_sr.get("data") or {}).get("ok"), f"set_config_row(SR Indent) failed: {set_sr!r}"
        set_field_sr = scn._post_fixture("set_config_row", {"key": "Field SR Indent", "value": 3})
        assert (set_field_sr.get("data") or {}).get("ok"), (
            f"set_config_row(Field SR Indent) failed: {set_field_sr!r}"
        )

        scn._post_fixture(
            "append_doc_soft_paragraph",
            {"text": "AI: draft the memo\n- pull last actuals\nTarget: Sep 12 meeting\n- more detail"},
        )
        # Bare 'AI:' with no explicit status: the establishing sync promotes
        # it to a canonical ACT-1 and flushes (materializes the status
        # token) -- same promotion test_field_continuation_flush.py's entry
        # point 2 documents (bare 'AI:' -> 'ACT-N:' on first sync, never
        # legacy 'AI-N:', which is reserved for a pre-existing token that
        # already carried that prefix in the doc).
        scn.sync()

        hits = _paras_containing(scn, "draft the memo")
        assert len(hits) == 1, f"expected one paragraph, got {hits!r}"
        assert hits[0] == (
            "ACT-1: draft the memo (Open)\n"
            "     - pull last actuals\n"
            "   Target:\tSep 12 meeting\n"
            "        - more detail"
        ), (
            # gts-x8wy: "- more detail" is a continuation WITHIN the Target
            # field's own value, not the field's label line -- with 'Field SR
            # SR Indent' unset it defaults to 'Field SR Indent'(3) + 'SR
            # Indent'(5) = 8 spaces, not 3.
            f"continuation lines not indented per configured SR Indent/Field SR Indent/"
            f"(defaulted) Field SR SR Indent: {hits[0]!r}"
        )

        bold_hits = [
            b for b in paragraph_bold_text(load_doc(download_docx(scn.doc_id)))
            if "Target:" in b
        ]
        assert bold_hits and bold_hits[0] == "Target:", (
            f"bold run should cover exactly the field name + colon (indent excluded): {bold_hits!r}"
        )

        # --- round trip: a fresh scan reads the SAME unindented text back ---
        scanned = _scan(scn, n=1)
        assert scanned["scanActionText"] == "draft the memo\n- pull last actuals", (
            f"indent leaked into stored action_text on rescan: {scanned['scanActionText']!r}"
        )
        fields = scanned.get("scanCustomFields") or {}
        assert fields.get("Target", {}).get("text") == "Sep 12 meeting\n- more detail", (
            f"indent leaked into stored field value on rescan: {fields!r}"
        )
    finally:
        # 'SR Indent'/'Field SR Indent' live on the Config sheet of the one
        # shared tracker spreadsheet (_openActionSheetSpreadsheet has no
        # per-test-doc scoping) -- leaving them set here leaks a non-default
        # indent into every other test's flush, and into production, until
        # someone notices. Clear unconditionally, including on assertion
        # failure above.
        scn._post_fixture("clear_config_rows", {})
        scn.close()


def test_zero_indent_default_matches_flush_left(settings, request):
    """Absent Config rows (the untouched default for every other test in this
    suite) reproduce gts-po8t's flush-left byte-for-byte -- the same
    assertion tests/test_field_continuation_flush.py::test_ep1_sheetwin_flush
    makes, restated here as this bead's own proof that the default did not
    change."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture(
            "append_doc_soft_paragraph",
            {"text": "AI: default indent base\nTarget: default value"},
        )
        scn.sync()

        hits = _paras_containing(scn, "default indent base")
        assert len(hits) == 1
        assert hits[0] == "ACT-1: default indent base (Open)\nTarget:\tdefault value", (
            f"default (no Config rows) must stay flush-left: {hits[0]!r}"
        )
    finally:
        scn.close()


def test_escape_template_indent_value_applies_literal_tabs_and_spaces(settings, request):
    """gts-x8wy: a Config value that doesn't parse as a number is a literal
    \\t/\\s escape template, not a space count. 'SR Indent' = '\\t\\s\\t'
    (six literal characters: backslash-t, backslash-s, backslash-t) resolves
    to tab+space+tab -- three real characters, not three spaces."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        set_sr = scn._post_fixture("set_config_row", {"key": "SR Indent", "value": "\\t\\s\\t"})
        assert (set_sr.get("data") or {}).get("ok"), f"set_config_row(SR Indent) failed: {set_sr!r}"

        scn._post_fixture(
            "append_doc_soft_paragraph",
            {"text": "AI: escape template base\n- continuation line"},
        )
        scn.sync()

        hits = _paras_containing(scn, "escape template base")
        assert len(hits) == 1, f"expected one paragraph, got {hits!r}"
        assert hits[0] == (
            "ACT-1: escape template base (Open)\n"
            "\t \t- continuation line"
        ), f"'\\t\\s\\t' must resolve to tab+space+tab, not 3 spaces: {hits[0]!r}"

        # --- round trip: rule 5's strip covers tabs and spaces alike ---
        scanned = _scan(scn, n=1)
        assert scanned["scanActionText"] == "escape template base\n- continuation line", (
            f"tab/space template indent leaked into stored action_text on rescan: {scanned['scanActionText']!r}"
        )
    finally:
        scn._post_fixture("clear_config_rows", {})
        scn.close()


def test_field_sr_sr_indent_overrides_default_and_is_independent(settings, request):
    """gts-x8wy: an EXPLICIT 'Field SR SR Indent' controls a field's own
    value-continuation lines independently of both 'Field SR Indent' (that
    field's label line) and the default-composition rule
    (test_configured_indent_applies_on_flush_and_round_trips above) --
    Field SR Indent=2 + SR Indent=5 would default-compose to 7, but the
    explicit Field SR SR Indent=4 here must win instead."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture("set_config_row", {"key": "SR Indent", "value": 5})
        scn._post_fixture("set_config_row", {"key": "Field SR Indent", "value": 2})
        set_field_sr_sr = scn._post_fixture("set_config_row", {"key": "Field SR SR Indent", "value": 4})
        assert (set_field_sr_sr.get("data") or {}).get("ok"), (
            f"set_config_row(Field SR SR Indent) failed: {set_field_sr_sr!r}"
        )

        scn._post_fixture(
            "append_doc_soft_paragraph",
            {"text": "AI: field sr sr base\nTarget: first line\n- second line"},
        )
        scn.sync()

        hits = _paras_containing(scn, "field sr sr base")
        assert len(hits) == 1, f"expected one paragraph, got {hits!r}"
        assert hits[0] == (
            "ACT-1: field sr sr base (Open)\n"
            "  Target:\tfirst line\n"
            "    - second line"
        ), (
            f"explicit Field SR SR Indent(4) must win over the default composition "
            f"Field SR Indent(2) + SR Indent(5) = 7: {hits[0]!r}"
        )
    finally:
        scn._post_fixture("clear_config_rows", {})
        scn.close()
