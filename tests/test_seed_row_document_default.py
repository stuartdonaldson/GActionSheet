"""
test_seed_row_document_default.py — gts-zj60 (stage `harness-leaks`,
knowledge-base/staging/docdata-litter-apt-speed.md).

`seed_row` (src/TestFixtures.js) used to default an unset `documentFormula`
to `''`, manufacturing an Actions row with an empty Document column -- a
shape the production scanner never writes (every real row's document_formula
points at the doc it was scanned from). 27 rows seeded this way (mostly by
tests/test_team_listing.py, which never passes documentFormula) then poisoned
the DocData integrity pass, which derives Doc Name from this same formula
with no fallback (docdata-litter-apt-speed.md's Evidence table).

This asserts the fixed default directly at the seed_row entry point: an
unset documentFormula now defaults to the doc's own HYPERLINK (the production
shape), while a caller that explicitly passes documentFormula='' still gets
the blank shape as a deliberate, named opt-in case -- `find_sheet_actions`
(WebApp.js's `_findSheetActionsForDoc`) always excludes a row with a blank
document_formula, so the opt-in row must be invisible to it regardless of the
docId filter.
"""
from scn.session import ScenarioSession


def test_seed_row_defaults_document_to_test_doc(settings, request):
    """[gts-zj60] seed_row with no documentFormula gets the test doc's own
    HYPERLINK, not a blank Document column."""
    scn = ScenarioSession.new_doc(settings, request=request)
    global_id = f"{scn.doc_id}/AI-DEFAULT"
    scn._post_fixture("seed_row", {
        "globalId": global_id,
        "actionId": "DEFAULT-1",
        "actionText": "zj60 default-document probe",
        "status": "Open",
    })

    rows = scn.find_sheet_actions()
    matches = [r for r in rows if r.global_id == global_id]
    assert matches, (
        f"[zj60] seeded row {global_id!r} not visible via find_sheet_actions "
        f"-- its document_formula defaulted to blank (find_sheet_actions "
        f"always excludes a row with no formula)"
    )
    assert matches[0].doc_id == scn.doc_id, (
        f"[zj60] expected the default document_formula to resolve to the "
        f"test doc {scn.doc_id!r}, got doc_id={matches[0].doc_id!r}"
    )
    assert matches[0].doc_name, "[zj60] expected a non-blank doc_name from the default formula"


def test_seed_row_explicit_blank_document_is_a_named_opt_in(settings, request):
    """[gts-zj60] a caller that explicitly passes documentFormula='' still
    gets the blank-Document shape -- the opt-in path is preserved, not
    removed by the new default."""
    scn = ScenarioSession.new_doc(settings, request=request)
    global_id = f"{scn.doc_id}/AI-BLANK"
    scn._post_fixture("seed_row", {
        "globalId": global_id,
        "actionId": "BLANK-1",
        "actionText": "zj60 explicit-blank-document opt-in probe",
        "status": "Open",
        "documentFormula": "",
    })

    rows = scn.find_sheet_actions()
    matches = [r for r in rows if r.global_id == global_id]
    assert not matches, (
        f"[zj60] explicit documentFormula='' should still produce a blank "
        f"document_formula (excluded from find_sheet_actions entirely), but "
        f"the seeded row was visible: {matches!r}"
    )
