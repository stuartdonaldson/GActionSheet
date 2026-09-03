"""Sparse expected-parse annotation (gts-gkcy, stage `apt-presentation`).

A JSON sidecar, tests/fixtures/hard-records-expect-parse.json, names what
the stage-1 parser (tests/helpers/doc_inspect) should yield for a handful of
records whose grammar case is genuinely easy to misread by eye: a
continuation-line field block (rule 5a), a legacy AI-N dual-prefix token
(ADR-0023), a bulleted list-item container, and a table-cell container
(APT v2). Offline and independent of the live doc -- the same
docx_build/twin-track-independence discipline as tests/test_doc_oracle_parser.py.

This file proves the *annotation format* itself (gts-gkcy's AC), not new
grammar cases -- those are already covered by test_doc_oracle_parser.py and
test_adr0027_reference_document.py.
"""
import pytest

from tests.helpers import docx_build
from tests.helpers.doc_inspect import floating_actions, load_doc
from tests.helpers.expect_parse import diff_expect_parse, load_expect_parse

pytestmark = pytest.mark.no_live_session

SIDECAR_PATH = "tests/fixtures/hard-records-expect-parse.json"

_HARD_RECORDS = [
    docx_build.para(docx_build.text(
        "ACT-101: jane@example.com Draft the Q3 budget memo (In Progress)\n"
        "- pull last year's actuals\n"
        "- circulate before Friday\n"
        "Consult With:\n"
        "- Stuart\n"
        "- John\n"
        "Due: Tuesday"
    )),
    docx_build.para(docx_build.text(
        "AI-102: jane@example.com legacy spelling still works (Open)"
    )),
    docx_build.para(
        docx_build.text("ACT-103: jane@example.com list item action (Open)"),
        list_item=True,
    ),
]
_HARD_TABLE = docx_build.table([[[docx_build.para(docx_build.text(
    "ACT-104: jane@example.com table cell action (Open)"
))]]])


@pytest.fixture(scope="module")
def hard_records_by_token():
    actions = floating_actions(docx_build.load(
        docx_build.build_docx(_HARD_RECORDS + [_HARD_TABLE])
    ))
    return {a.token: a for a in actions if a.token}


def test_sidecar_is_sparse_and_covers_only_hard_records():
    expect = load_expect_parse(SIDECAR_PATH)
    assert expect, "the sidecar must annotate at least the documented hard records"
    assert len(expect) <= 6, (
        f"AC2: a handful only -- a troubleshooting aid, not a per-record "
        f"convention; got {len(expect)} entries"
    )
    for token, fields in expect.items():
        assert fields, f"{token}: an empty entry annotates nothing"


def test_every_annotated_record_matches_its_expected_parse(hard_records_by_token):
    expect = load_expect_parse(SIDECAR_PATH)
    problems = []
    for token, fields in expect.items():
        assert token in hard_records_by_token, f"{token} named in the sidecar but not in the fixture doc"
        mismatches = diff_expect_parse(hard_records_by_token[token], fields)
        if mismatches:
            problems.append(f"{token}: {'; '.join(mismatches)}")
    assert not problems, "\n" + "\n".join(problems)


def test_absence_of_an_annotation_is_never_an_error():
    """AC4. ``diff_expect_parse`` is never even called for an unannotated
    record -- there is nothing to assert against, and this must not be
    treated as failure. Demonstrated rather than merely stated: pick a
    genuinely unannotated key and confirm it is simply absent."""
    expect = load_expect_parse(SIDECAR_PATH)
    assert "ACT-999" not in expect
    # No call, no assertion -- an absent key drives no check at all.


def test_missing_sidecar_file_returns_empty_not_an_error(tmp_path):
    assert load_expect_parse(tmp_path / "does-not-exist.json") == {}


def test_a_violated_annotation_shows_expected_vs_actual():
    """AC3, proven directly against the diff function."""
    (action,) = floating_actions(docx_build.load(docx_build.build_docx([
        docx_build.para(docx_build.text("ACT-1: jane@example.com do the thing (Open)")),
    ])))
    mismatches = diff_expect_parse(action, {"container": "table-cell", "action_text": "do the thing"})
    assert mismatches == ["container: expected 'table-cell', got 'body'"]
