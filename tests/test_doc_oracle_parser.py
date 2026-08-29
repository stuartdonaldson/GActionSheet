"""Independent-track parser for ADR-0027 floating actions (gts-e5cl).

Offline unit tests for ``tests/helpers/doc_inspect.floating_actions`` — the
Python-side oracle.  Every expectation here is derived from the written spec
(``knowledge-base/adr/0027-floating-action-paragraph-grammar.md`` and
``docs/interfaces/action-portable-text.md``), never from GAS output or from a
blessed ``tests/fixtures/*.apt.txt`` corpus: a parser taught by the system it
is meant to judge cannot contradict it (the 2026-08-29 circularity).

No network, no GAS, no local.settings.json.
"""
import pytest

from tests.helpers.doc_inspect import floating_actions, load_doc
from tests.helpers.docx_build import (
    bold,
    build_docx,
    chip,
    link,
    para,
    table,
    text,
)

pytestmark = pytest.mark.no_live_session

CHIP_URL = "https://script.google.com/exec?c=view&globalId=DOC%2FACT-1"


def _parse(blocks):
    return floating_actions(load_doc(build_docx(blocks)))


# ---------------------------------------------------------------------------
# Header line: token, assignee, status  (ADR-0027 rules 1, 3, 4)
# ---------------------------------------------------------------------------

def test_chip_assignee_linked_token_header_only():
    (a,) = _parse([
        para(link("ACT-1: ", CHIP_URL), chip("jane@example.com", "Jane Doe"),
             text(" Draft the Q3 budget memo (In Progress)")),
    ])
    assert a.token == "ACT-1"
    assert a.assignee_email == "jane@example.com"
    assert a.assignee_name == "Jane Doe"
    assert a.assignee_source == "chip"
    assert a.action_text == "Draft the Q3 budget memo"
    assert a.status == "In Progress"
    assert a.has_explicit_status is True
    assert a.custom_fields == {}
    assert a.token_linked is True
    assert a.token_url == CHIP_URL
    assert a.error is None


def test_text_email_assignee_accepts_at_sigil():
    """Rule 3 — '@jane@example.com' parses identically; the sigil is not stored."""
    (a,) = _parse([para(text("AI-7: @jane@example.com finish the report (Open)"))])
    assert a.token == "AI-7"
    assert a.assignee_email == "jane@example.com"
    assert a.assignee_name == ""
    assert a.assignee_source == "text"
    assert a.action_text == "finish the report"
    assert a.status == "Open"


def test_no_assignee_is_not_a_parse_failure():
    (a,) = _parse([para(text("ACT-2: unassigned work item (Done)"))])
    assert a.assignee_email is None
    assert a.action_text == "unassigned work item"
    assert a.status == "Done"
    assert a.error is None


def test_status_absent_reports_none_not_a_default():
    """The oracle must not invent 'Open' — that is the system's default, not the doc's."""
    (a,) = _parse([para(text("ACT-3: jane@example.com no status here"))])
    assert a.status is None
    assert a.has_explicit_status is False
    assert a.action_text == "no status here"


@pytest.mark.parametrize(
    "header, expect_status, expect_text",
    [
        # gts-1tbe: a group followed by plain-word text is literal, not a status
        ("ACT-4: jane@example.com Review the (draft) proposal",
         None, "Review the (draft) proposal"),
        # last group qualifies; the mid-text parenthetical survives verbatim
        ("ACT-4: jane@example.com Review the (draft) proposal (In Progress)",
         "In Progress", "Review the (draft) proposal"),
        # parens only at the end — ambiguous, treated as the status (gts-28q case 3)
        ("ACT-4: jane@example.com Review (draft)", "draft", "Review"),
        # gts-v0py: trailing text after the token is preserved, not dropped
        ("ACT-4: jane@example.com Confirm Wednesdays work (Open) - done",
         "Open", "Confirm Wednesdays work - done"),
    ],
)
def test_status_token_position_rule(header, expect_status, expect_text):
    (a,) = _parse([para(text(header))])
    assert a.status == expect_status
    assert a.action_text == expect_text


def test_status_is_scoped_to_the_header_line():
    """Rule 4 — parentheses in a continuation field value are always literal."""
    (a,) = _parse([para(text(
        "ACT-5: jane@example.com Draft the memo (In Progress)\n"
        "Progress: revenue section (blocked)"
    ))])
    assert a.status == "In Progress"
    assert a.action_text == "Draft the memo"
    assert a.custom_fields == {"Progress": "revenue section (blocked)"}


# ---------------------------------------------------------------------------
# Continuation lines  (ADR-0027 rules 5, 5a, 8)
# ---------------------------------------------------------------------------

def test_soft_return_prose_is_absorbed_into_action_text():
    """Rule 5a first-block case — prose before any field line joins actionText."""
    (a,) = _parse([para(text(
        "ACT-4: jane@example.com Draft the Q3 budget memo (In Progress)\n"
        "Still waiting on finance numbers before this can close."
    ))])
    assert a.action_text == (
        "Draft the Q3 budget memo\n"
        "Still waiting on finance numbers before this can close."
    )
    assert a.custom_fields == {}


def test_rule_5a_worked_example():
    """The ADR's own worked example, verbatim (rule 5a)."""
    (a,) = _parse([para(text(
        "ACT-9: jane@example.com Draft the Q3 budget memo (In Progress)\n"
        "- pull last year's actuals\n"
        "- circulate before Friday\n"
        "Consult With:\n"
        "- Stuart\n"
        "- John\n"
        "Due: Tuesday"
    ))])
    assert a.action_text == (
        "Draft the Q3 budget memo\n- pull last year's actuals\n- circulate before Friday"
    )
    assert a.custom_fields == {
        "Consult With": "\n- Stuart\n- John",
        "Due": "Tuesday",
    }
    assert list(a.custom_fields) == ["Consult With", "Due"]  # document order


def test_flush_rendered_form_parses_back_to_the_same_blocks():
    """Rule 8's rendering — 5-space indent, bold label, tab — is stripped on read."""
    (a,) = _parse([para(
        text("ACT-9: jane@example.com Draft the Q3 budget memo (In Progress)\n"
             "     - pull last year's actuals\n     "),
        bold("Consult With:"),
        text("\t\n     - Stuart\n     "),
        bold("Due:"),
        text("\tTuesday"),
    )])
    assert a.action_text == "Draft the Q3 budget memo\n- pull last year's actuals"
    assert a.custom_fields == {"Consult With": "\n- Stuart", "Due": "Tuesday"}


def test_lowercase_colon_prose_is_not_a_field_line():
    """Rule 5 — every word must be Title Case, so sentence prose stays prose."""
    (a,) = _parse([para(text(
        "ACT-6: jane@example.com Ship it (Open)\nthen he said: we should ship it"
    ))])
    assert a.action_text == "Ship it\nthen he said: we should ship it"
    assert a.custom_fields == {}


def test_field_name_over_32_chars_is_prose():
    long_name = "Extremely Long Field Name Beyond Bound"
    assert len(long_name) > 32
    (a,) = _parse([para(text(f"ACT-6: jane@example.com Ship it (Open)\n{long_name}: x"))])
    assert a.custom_fields == {}
    assert a.action_text.endswith(f"{long_name}: x")


def test_repeated_field_name_appends_rather_than_overwrites():
    (a,) = _parse([para(text(
        "ACT-8: jane@example.com Ship it (Open)\nDue: Tuesday\nDue: Wednesday"
    ))])
    assert a.custom_fields == {"Due": "Tuesday\nWednesday"}


def test_hard_paragraph_break_ends_the_action():
    """SR is not a paragraph break — a real Enter starts unrelated content."""
    actions = _parse([
        para(text("ACT-10: jane@example.com Ship it (Open)")),
        para(text("Due: Tuesday")),
    ])
    assert len(actions) == 1
    assert actions[0].custom_fields == {}


# ---------------------------------------------------------------------------
# Detection  (must not depend on w:numPr — gts-e5cl AC)
# ---------------------------------------------------------------------------

def test_detection_covers_plain_list_and_table_cell_containers():
    actions = _parse([
        para(text("ACT-60: jane@example.com body level action (Open)")),
        para(text("ACT-61: jane@example.com body level list item action (Open)"),
             list_item=True),
        table([[[para(text("ACT-62: jane@example.com table cell action (Open)"))],
                [para(text("just prose"))]]]),
    ])
    assert [a.token for a in actions] == ["ACT-60", "ACT-61", "ACT-62"]
    assert [a.container for a in actions] == ["body", "list-item", "table-cell"]


def test_plain_prose_paragraph_is_not_an_action():
    assert _parse([para(text("Case 1 (gts-ucdz): @-sigil email assignee."))]) == []


# ---------------------------------------------------------------------------
# The 2026-08-29 failure modes  (gts-e5cl AC)
# ---------------------------------------------------------------------------

def test_unlinked_token_is_reported_present_but_unlinked_not_dropped():
    (a,) = _parse([para(text("ACT-11: jane@example.com Draft the memo (Open)"))])
    assert a.token == "ACT-11"
    assert a.token_linked is False
    assert a.token_url is None
    assert a.error is None


def test_paragraph_starting_with_a_token_that_fails_the_grammar_is_reported():
    """Rule 6 — reported as unparseable, carrying its index and leading text."""
    (a,) = _parse([
        para(text("prose")),
        para(text("ACT-12 jane@example.com missing the colon")),
    ])
    assert a.error == "unparseable-action-paragraph"
    assert a.token is None
    assert a.body_index == 1
    assert a.raw_text.startswith("ACT-12 ")


def test_bare_trigger_is_reported_as_pending_not_as_an_action():
    (a,) = _parse([para(text("AI: schedule the review"))])
    assert a.token is None
    assert a.pending is True
    assert a.error is None
    assert a.action_text == "schedule the review"


def test_short_count_when_actions_are_removed():
    """Proven to fail — the parser reports the shortfall the sheet cannot see."""
    full = [para(text(f"ACT-{n}: jane@example.com item {n} (Open)")) for n in range(1, 22)]
    assert len(_parse(full)) == 21

    truncated = full[:1] + [para(text("unrelated prose"))] * 20
    parsed = _parse(truncated)
    assert len(parsed) == 1
    assert [a.token for a in parsed] == ["ACT-1"]
