"""
test_archive.py — GTaskSheet-d33z

Journey-based archive lifecycle: a real action item created in a doc, synced
to the sheet (acquiring globalId + fileId), closed, aged, then swept by
ArchiveManager. Verifies the archived row retains globalId and fileId intact.

The archive sweep also acts as the session teardown — after archival the row
is gone from Actions and the journey doc is effectively retired.
"""
import io
import pytest
import openpyxl

from scn.ai import ai
from scn.session import ScenarioSession
from tests.helpers.download import download_xlsx

_ARCHIVE_ACTION_TEXT = "d33z archive lifecycle action"


def _find_archive_row(sheet_id: str, action_text: str) -> dict | None:
    """Return the first Archive tab row whose Action column matches action_text, or None."""
    xlsx = download_xlsx(sheet_id)
    wb = openpyxl.load_workbook(io.BytesIO(xlsx))
    if "Archive" not in wb.sheetnames:
        return None
    ws = wb["Archive"]
    col_names = [cell.value for cell in ws[1]]
    for row in ws.iter_rows(min_row=2, values_only=True):
        if len(row) < len(col_names):
            continue
        row_dict = dict(zip(col_names, row))
        if row_dict.get("Action") == action_text:
            return row_dict
    return None


@pytest.fixture(scope="module")
def scn(settings):
    s = ScenarioSession.new_doc(settings)
    yield s
    s.close()


def test_archive_lifecycle(scn, settings):
    """GTaskSheet-d33z: row created via full lifecycle is archived with globalId + fileId."""
    sheet_id = settings["testSheetId"]

    # SETUP: append action, sync → row lands in sheet with proper globalId + fileId
    target = ai(action=_ARCHIVE_ACTION_TEXT)
    scn.append_paragraph(target.as_text())
    scn.sync()

    # Pin the globalId so we can address the row by it
    rows = scn.find_sheet_actions()
    matching = [r for r in rows if r.action == _ARCHIVE_ACTION_TEXT]
    assert len(matching) == 1, (
        f"[d33z] Expected 1 sheet row matching action text after sync, got {len(matching)}"
    )
    target.action_id = matching[0].action_id

    # ACT: close the action and age the modified_date so it qualifies for archival
    scn.edit_sheet(target, status="Closed")
    scn.sync()   # Dirty → sheet-wins → doc updated; row is now Closed in sheet

    global_id = f"{scn.doc_id}/{target.action_id}"
    scn._post_fixture("backdate_action_row", {"globalId": global_id, "daysAgo": 35})

    # Run the archive sweep
    scn._post_fixture("archive_journey")

    # ASSERT 1: row absent from Actions
    actions_after = scn.sheet_rows()
    assert not any(r.action == _ARCHIVE_ACTION_TEXT for r in actions_after), (
        f"[d33z] '{_ARCHIVE_ACTION_TEXT}' row still present in Actions after archive sweep"
    )

    # ASSERT 2: row present in Archive with globalId and fileId populated
    archived = _find_archive_row(sheet_id, _ARCHIVE_ACTION_TEXT)
    assert archived is not None, (
        f"[d33z] '{_ARCHIVE_ACTION_TEXT}' row not found in Archive tab after sweep"
    )
    assert archived.get("globalId"), (
        f"[d33z] archived row missing globalId; got {archived.get('globalId')!r}"
    )
    assert archived.get("File Id"), (
        f"[d33z] archived row missing File Id; got {archived.get('File Id')!r}"
    )
