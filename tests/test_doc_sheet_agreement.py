"""Doc<->sheet agreement, both directions (gts-9o61).

The expected value comes only from the independent Python parse of the
document (gts-e5cl).  Nothing here is blessed off the system under test, which
is what makes this the assertion that would have caught 2026-08-29: a sync
that scanned one of 21 actions and then marked the other 20 rows *Deleted*
satisfies every ``input == expected`` corpus check, but cannot satisfy this.

No network, no GAS, no local.settings.json.
"""
import json

import pytest

from scn.ai import ai
from tests.helpers.doc_inspect import floating_actions, load_doc
from tests.helpers.doc_sheet_agreement import compare_doc_sheet
from tests.helpers.docx_build import build_docx, chip, link, para, text

pytestmark = pytest.mark.no_live_session


def _doc(*paragraph_texts):
    return floating_actions(load_doc(build_docx([para(text(t)) for t in paragraph_texts])))


def _row(action_id, *, action="", assignee=None, assignee_name=None, status="Open",
         sync_status="", custom_fields=None):
    row = ai(action=action, assignee=assignee, action_id=action_id, status=status)
    row.assignee_name = assignee_name
    row.sync_status = sync_status
    row.custom_fields = custom_fields
    return row


def _joined(problems):
    return "\n".join(problems)


# ---------------------------------------------------------------------------
# Agreement
# ---------------------------------------------------------------------------

def test_agreeing_doc_and_sheet_report_no_problems():
    doc = _doc("ACT-1: jane@example.com Draft the memo (In Progress)")
    rows = [_row("ACT-1", action="Draft the memo", assignee="jane@example.com",
                 status="In Progress")]
    assert compare_doc_sheet(doc, rows) == []


def test_absent_doc_status_matches_the_sheet_default():
    """The doc carries no token; the sheet stores 'Open'.  That is agreement."""
    doc = _doc("ACT-1: jane@example.com Draft the memo")
    rows = [_row("ACT-1", action="Draft the memo", assignee="jane@example.com",
                 status="Open")]
    assert compare_doc_sheet(doc, rows) == []


def test_custom_fields_compare_by_value_text():
    doc = _doc("ACT-1: jane@example.com Ship it (Open)\nDue: Tuesday")
    rows = [_row("ACT-1", action="Ship it", assignee="jane@example.com",
                 custom_fields=json.dumps({"Due": {"text": "Tuesday", "runs": []}}))]
    assert compare_doc_sheet(doc, rows) == []


# ---------------------------------------------------------------------------
# Direction 1 — doc action with no sheet row  (AC 1)
# ---------------------------------------------------------------------------

def test_doc_action_with_no_sheet_row_fails():
    doc = _doc("ACT-1: jane@example.com a (Open)", "ACT-2: jane@example.com b (Open)")
    rows = [_row("ACT-1", action="a", assignee="jane@example.com")]
    problems = compare_doc_sheet(doc, rows)
    assert len(problems) == 1
    assert "ACT-2" in problems[0] and "no sheet row" in problems[0]


def test_pending_bare_trigger_fails_by_default_and_is_waivable():
    doc = _doc("AI: schedule the review")
    assert any("pending" in p for p in compare_doc_sheet(doc, []))
    assert compare_doc_sheet(doc, [], allow_pending=True) == []


def test_unparseable_paragraph_fails():
    doc = _doc("ACT-12 jane@example.com missing the colon")
    assert any("unparseable" in p for p in compare_doc_sheet(doc, []))


# ---------------------------------------------------------------------------
# Direction 2 — sheet row with no doc counterpart  (AC 2)
# ---------------------------------------------------------------------------

def test_sheet_row_with_no_doc_counterpart_fails():
    doc = _doc("ACT-1: jane@example.com a (Open)")
    rows = [_row("ACT-1", action="a", assignee="jane@example.com"),
            _row("ACT-9", action="ghost", assignee="jane@example.com")]
    problems = compare_doc_sheet(doc, rows)
    assert len(problems) == 1
    assert "ACT-9" in problems[0] and "no doc counterpart" in problems[0]


def test_deleted_row_with_no_doc_counterpart_still_fails():
    """A Deleted row is not exempt — that exemption is what hid 2026-08-29."""
    doc = _doc("ACT-1: jane@example.com a (Open)")
    rows = [_row("ACT-1", action="a", assignee="jane@example.com"),
            _row("ACT-9", action="ghost", sync_status="Deleted")]
    assert any("ACT-9" in p for p in compare_doc_sheet(doc, rows))


def test_deleted_row_whose_action_is_still_in_the_doc_fails():
    doc = _doc("ACT-1: jane@example.com a (Open)")
    rows = [_row("ACT-1", action="a", assignee="jane@example.com",
                 sync_status="Deleted")]
    problems = compare_doc_sheet(doc, rows)
    assert len(problems) == 1
    assert "Deleted" in problems[0] and "ACT-1" in problems[0]


def test_duplicate_sheet_rows_for_one_token_fail():
    doc = _doc("ACT-1: jane@example.com a (Open)")
    rows = [_row("ACT-1", action="a", assignee="jane@example.com"),
            _row("ACT-1", action="a", assignee="jane@example.com")]
    assert any("2 sheet rows" in p for p in compare_doc_sheet(doc, rows))


# ---------------------------------------------------------------------------
# Field comparison — every disagreement, not just the first  (AC 3)
# ---------------------------------------------------------------------------

def test_every_field_disagreement_is_reported():
    doc = _doc("ACT-1: jane@example.com Draft the memo (In Progress)\nDue: Tuesday")
    rows = [_row("ACT-1", action="Draft the memoo", assignee="john@example.com",
                 status="Open",
                 custom_fields=json.dumps({"Due": {"text": "Wednesday", "runs": []}}))]
    problems = compare_doc_sheet(doc, rows)
    joined = _joined(problems)
    assert len(problems) == 4, joined
    for field in ("assignee_email", "action_text", "status", "custom_fields"):
        assert field in joined


def test_assignee_name_disagreement_is_reported_when_the_doc_has_a_chip():
    docx_bytes = build_docx([para(
        link("ACT-1: ", "https://example.com/chip"),
        chip("jane@example.com", "Jane Doe"),
        text(" Draft the memo (Open)"),
    )])
    doc = floating_actions(load_doc(docx_bytes))
    rows = [_row("ACT-1", action="Draft the memo", assignee="jane@example.com",
                 assignee_name="Janet Doe")]
    assert any("assignee_name" in p for p in compare_doc_sheet(doc, rows))


def test_missing_custom_field_in_the_sheet_is_reported():
    doc = _doc("ACT-1: jane@example.com Ship it (Open)\nDue: Tuesday")
    rows = [_row("ACT-1", action="Ship it", assignee="jane@example.com")]
    assert any("custom_fields" in p for p in compare_doc_sheet(doc, rows))


# ---------------------------------------------------------------------------
# Proven to fail — a synthetic reproduction of 2026-08-29  (gts-9o61 AC)
# ---------------------------------------------------------------------------

def test_red_against_the_2026_08_29_state():
    """Scan of 1 out of 21 actions, the other 20 rows marked Deleted."""
    doc = _doc(*[f"ACT-{n}: jane@example.com item {n} (Open)" for n in range(1, 22)])
    assert len(doc) == 21

    rows = [_row("ACT-1", action="item 1", assignee="jane@example.com")]
    rows += [_row(f"ACT-{n}", action=f"item {n}", assignee="jane@example.com",
                  sync_status="Deleted") for n in range(2, 22)]

    problems = compare_doc_sheet(doc, rows)
    assert len(problems) == 20, _joined(problems)
    assert all("Deleted" in p for p in problems)


def test_email_shaped_chip_label_is_not_an_assignee_name_claim():
    """A .docx-exported chip whose display text is the email itself carries no
    display-name claim — comparing it against the sheet's resolved name would
    make every chip action red for a reason no one typed."""
    docx_bytes = build_docx([para(
        link("ACT-1: ", "https://example.com/chip"),
        chip("jane@example.com", "jane@example.com"),
        text(" Draft the memo (Open)"),
    )])
    doc = floating_actions(load_doc(docx_bytes))
    rows = [_row("ACT-1", action="Draft the memo", assignee="jane@example.com",
                 assignee_name="Jane Doe")]
    assert compare_doc_sheet(doc, rows) == []
