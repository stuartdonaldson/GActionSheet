"""
test_tracker_view_only.py — HTTP-only focused test for tracker view-only enforcement.

Migrates sidebar_tracker_insert.test.js AC3 into the scn scenario model.
No browser required (no UiDriver): the uc_c_view_only fixture exercises the full
'edit cell → re-insert overwrites' path entirely on the server side.

Bead: GTaskSheet-80mo.8
"""
from scn.engine import Surface
from scn.session import ScenarioSession
from scn.surfaces import TrackerReader

DOC = Surface.DOC


# ---------------------------------------------------------------------------
# AC3: direct tracker cell edit is overwritten on re-insert (view-only enforcement)
# ---------------------------------------------------------------------------

def test_cell_edit_overwritten(settings):
    """Cell edits to the tracker table are discarded when the table is re-inserted.

    uc_c_view_only fixture: seeds actions → syncs → inserts tracker → edits a cell
    (adds '-EDITED' sentinel) → calls insertTrackerTable again.  The re-insert must
    overwrite the sentinel: no tracker row field may contain '-EDITED' after the fixture.

    HTTP-only path (no UI): the fixture exercises the GAS-side insert/edit/re-insert
    cycle without a browser; verify_consistency() is the single consistency authority
    (server truth); TrackerReader gives artifact truth (downloaded docx).
    """
    from tests.helpers.download import download_docx

    s = ScenarioSession.new_doc(settings)
    try:
        s._post_fixture("uc_c_view_only")

        # Server authority: consistency must pass after re-insert
        s.verify_consistency(scope=DOC)

        # Artifact truth: no tracker row field may retain the '-EDITED' sentinel
        docx = download_docx(s.doc_id)
        tracker_rows = TrackerReader().read(docx, s.doc_id)
        assert tracker_rows, "Expected tracker rows in doc after uc_c_view_only fixture"

        for row in tracker_rows:
            for value in (row.action_id, row.action, row.status, row.assignee):
                assert "-EDITED" not in str(value or ""), (
                    f"Tracker row field still contains stale cell edit: {value!r}"
                )
    finally:
        s.close()
