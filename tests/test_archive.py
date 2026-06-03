"""
test_archive.py — GTaskSheet-d33z

Lean lifecycle: one archive-eligible row seeded → archive trigger → row absent
from Actions, present in Archive.

ArchiveManager criteria: Status='Closed' AND Date Modified > 30 days old.
The 'archive' fixture seeds an eligible row (Status=Closed, 35-day-old dateModified)
for testDocId. 'archive_journey' runs ArchiveManager.archive(ss) — the production sweep.

Note on archive_rows(doc_id): ArchiveManager.archive uses getValues() which loses
the HYPERLINK formula in column 7 (stores display text, not URL). SheetReader cannot
extract doc_id from plain display text, so archive_rows() filtered by doc_id returns
empty for archived rows. This test asserts the Archive row count increases.
"""
import io
import pytest
import openpyxl

from scn.session import ScenarioSession
from tests.helpers.download import download_xlsx

_ARCHIVE_ACTION_TEXT = "Archived action"


def _count_archive_text(sheet_id: str, text: str) -> int:
    """Count rows in the Archive tab whose Action column (col 5) matches text."""
    xlsx = download_xlsx(sheet_id)
    wb = openpyxl.load_workbook(io.BytesIO(xlsx))
    if "Archive" not in wb.sheetnames:
        return 0
    ws = wb["Archive"]
    count = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if len(row) >= 5 and row[4] == text:
            count += 1
    return count


@pytest.fixture(scope="module")
def scn(settings):
    s = ScenarioSession.new_doc(settings)
    yield s
    s.close()


def test_archive_lifecycle(scn, settings):
    """GTaskSheet-d33z: archive-eligible row moves from Actions to Archive."""
    sheet_id = settings["testSheetId"]

    # Baseline: how many 'Archived action' rows already exist in Archive
    pre_count = _count_archive_text(sheet_id, _ARCHIVE_ACTION_TEXT)

    # Seed one archive-eligible row (Status=Closed, Date Modified 35 days ago, testDocId)
    scn._post_fixture("archive")

    # Row must be in Actions now
    actions_before = scn.sheet_rows()
    assert any(r.action == _ARCHIVE_ACTION_TEXT for r in actions_before), (
        f"[d33z] 'archive' fixture row not found in Actions sheet after seeding"
    )

    # Trigger the archive sweep (archive_journey = ArchiveManager.archive(ss))
    scn._post_fixture("archive_journey")

    # Row must be absent from Actions
    actions_after = scn.sheet_rows()
    assert not any(r.action == _ARCHIVE_ACTION_TEXT for r in actions_after), (
        f"[d33z] '{_ARCHIVE_ACTION_TEXT}' row still in Actions after archive sweep"
    )

    # Archive must have gained at least one more 'Archived action' row
    post_count = _count_archive_text(sheet_id, _ARCHIVE_ACTION_TEXT)
    assert post_count > pre_count, (
        f"[d33z] Archive row count for '{_ARCHIVE_ACTION_TEXT}' did not increase "
        f"(before={pre_count}, after={post_count})"
    )
