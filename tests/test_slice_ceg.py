"""
Slice tests for ceg: idempotence, archive manager, and document discovery.

All tests are marked xfail until the ceg GAS modules are deployed:
  - SyncOrchestrator.js (idempotence pre-check: skip writes when normalized values match)
  - ArchiveManager.js
  - DocumentDiscovery.js (DriveApp.searchFiles wired into timed trigger and Sync menu)

Each test:
  1. Resets the test doc/sheet to a known fixture state via setupTestFixtures(scenario).
  2. Runs syncDocument(testDocId) or syncAll() via the GAS editor.
  3. Downloads the sheet as .xlsx and/or the doc as .docx, or inspects GAS logs.
  4. Asserts the expected outcome.

The GAS function invocations (setupTestFixtures, syncDocument, syncAll) are triggered
via the Playwright editor helper. The Playwright integration is not yet wired in
Python — those calls are marked with TODO comments matching the pattern in
test_slice_5jn.py.

Prerequisites:
  - local.settings.json populated with testSheetId, testDocId, scriptId, gasLogDir
  - Test sheet and doc shared with "Anyone with link (viewer)"
  - .auth/user.json present (run `node tests/playwright/authenticate.js` once)
"""
import pytest

from tests.helpers.download import download_xlsx, download_docx
from tests.helpers.sheet_inspect import load_sheet, find_row, headers, rows_as_dicts
from tests.helpers.doc_inspect import load_doc
from tests.helpers.gas_log import clear_logs, wait_for_log
from tests.helpers.gas_invoke import setup_fixture, sync_document, sync_all


# ---------------------------------------------------------------------------
# AC-5: Idempotence — second sync produces no changes
# ---------------------------------------------------------------------------


class TestIdempotence:
    """ceg AC-5: a second sync immediately after a successful sync makes no writes;
    sync.complete log reports changes == 0; xlsx and docx bytes are identical."""

    def test_second_sync_no_changes(
        self, test_sheet_id, test_doc_id, gas_log_dir
    ):
        """After setupTestFixtures('ac5') + two consecutive syncDocument() calls,
        the second sync.complete log entry must carry changes == 0, and the
        downloaded xlsx and docx must be byte-for-byte identical across both runs.

        Fixture precondition: doc and sheet are already in a consistent, fully-synced
        state (no pending updates on either side).
        """
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        # --- First sync ---
        clear_logs(gas_log_dir)
        setup_fixture('ac5')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.complete")

        xlsx1 = download_xlsx(test_sheet_id)
        docx1 = download_docx(test_doc_id)

        # --- Second sync ---
        clear_logs(gas_log_dir)
        sync_document(test_doc_id)
        second_entry = wait_for_log(
            gas_log_dir,
            lambda e: (
                e.get("tag") == "sync.complete"
                and e.get("data", {}).get("changes") == 0
            ),
        )

        assert second_entry is not None, (
            "Second sync.complete log entry with changes==0 not found"
        )

        xlsx2 = download_xlsx(test_sheet_id)
        docx2 = download_docx(test_doc_id)

        assert xlsx1 == xlsx2, (
            "Sheet content changed on second sync — orchestrator is not idempotent"
        )
        assert docx1 == docx2, (
            "Doc content changed on second sync — orchestrator is not idempotent"
        )


# ---------------------------------------------------------------------------
# Archive manager: Closed + >30 days rows move to Archive tab
# ---------------------------------------------------------------------------


class TestArchiveManager:
    """ceg archive: rows with Status=Closed and Date Modified > 30 days are moved
    from the 'Actions' tab to the 'Archive' tab after sync."""

    def test_closed_old_action_moves_to_archive(
        self, test_sheet_id, test_doc_id, gas_log_dir
    ):
        """After setupTestFixtures('archive') + syncDocument(), the sheet row with
        Status=Closed and Date Modified > 30 days must appear in the 'Archive' tab
        and must be absent from the 'Actions' tab.

        Fixture precondition: 'Actions' tab has one row with ID=1, Status='Closed',
        Date Modified = 35 days ago.
        """
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        clear_logs(gas_log_dir)
        setup_fixture('archive')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.complete")

        xlsx = download_xlsx(test_sheet_id)

        # Row must be absent from Actions tab
        ws_actions = load_sheet(xlsx, sheet_name="Actions")
        actions_rows = rows_as_dicts(ws_actions)
        actions_ids = [r.get("ID") for r in actions_rows]
        assert 1 not in actions_ids, (
            "Closed+old row ID=1 still present in 'Actions' tab after sync; "
            "expected it to be moved to 'Archive'"
        )

        # Row must be present in Archive tab
        ws_archive = load_sheet(xlsx, sheet_name="Archive")
        archive_rows = rows_as_dicts(ws_archive)
        archive_ids = [r.get("ID") for r in archive_rows]
        assert 1 in archive_ids, (
            f"Closed+old row ID=1 not found in 'Archive' tab. "
            f"Archive IDs present: {archive_ids}"
        )

    def test_archive_does_not_update_date_modified(
        self, test_sheet_id, test_doc_id, gas_log_dir
    ):
        """After archival, the archived row's Date Modified value must be
        identical to its pre-sync value — the archive move must not touch timestamps.

        Fixture precondition: same as test_closed_old_action_moves_to_archive;
        the fixture seeds Date Modified = 35 days ago (a known fixed value the
        test can compare against via the log or a secondary fixture query).
        """
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        clear_logs(gas_log_dir)
        setup_fixture('archive')
        sync_document(test_doc_id)
        archive_entry = wait_for_log(
            gas_log_dir, lambda e: e.get("tag") == "archive.moved"
        )

        assert archive_entry is not None, "archive.moved log entry not found"
        original_date_modified = archive_entry.get("data", {}).get("originalDateModified")
        assert original_date_modified is not None, (
            "archive.moved log entry missing data.originalDateModified"
        )

        xlsx = download_xlsx(test_sheet_id)
        ws_archive = load_sheet(xlsx, sheet_name="Archive")
        archive_rows = rows_as_dicts(ws_archive)

        archived_row = next((r for r in archive_rows if r.get("ID") == 1), None)
        assert archived_row is not None, "Archived row ID=1 not found in Archive tab"

        # Date Modified in the archived row must match the original seeded value
        import datetime
        cell_date = archived_row.get("Date Modified")
        assert cell_date is not None, "Date Modified is None in archived row"
        # Compare as ISO date strings to avoid timezone representation differences
        if isinstance(cell_date, datetime.datetime):
            cell_date_str = cell_date.date().isoformat()
        else:
            cell_date_str = str(cell_date)
        assert original_date_modified.startswith(cell_date_str), (
            f"Date Modified changed during archival. "
            f"Original: {original_date_modified!r}, "
            f"After archive: {cell_date_str!r}"
        )

    def test_archive_move_does_not_fire_onedit(
        self, test_sheet_id, test_doc_id, gas_log_dir
    ):
        """The archive move must NOT fire the onEdit trigger. Verified indirectly:
        no onedit.complete log entry appears during the sync run that archives the row.
        """
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        clear_logs(gas_log_dir)
        setup_fixture('archive')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.complete")

        import pathlib, json, os
        # Scan all log entries accumulated during this sync run
        onedit_fired = False
        if gas_log_dir and os.path.isdir(gas_log_dir):
            for f in sorted(pathlib.Path(gas_log_dir).glob("*.log")):
                try:
                    for line in f.read_text().splitlines():
                        if not line.strip():
                            continue
                        entry = json.loads(line)
                        if entry.get("tag") == "onedit.complete":
                            onedit_fired = True
                except (json.JSONDecodeError, OSError):
                    pass

        assert not onedit_fired, (
            "onedit.complete log entry found during archive sync run — "
            "the archive move incorrectly triggered the onEdit handler"
        )


# ---------------------------------------------------------------------------
# Document Discovery: Drive folder scan wired into syncAll
# ---------------------------------------------------------------------------


class TestDocumentDiscovery:
    """ceg discovery: DocumentDiscovery.js finds docs modified within 7 days and
    ignores docs modified 8+ days ago when syncAll() is invoked."""

    def test_discovery_finds_recently_modified_doc(
        self, test_sheet_id, test_doc_id, gas_log_dir
    ):
        """After setupTestFixtures('discovery') + syncAll(), a doc modified within
        the last 7 days must appear in the sync.complete log entry's processed
        docIds list.

        Fixture precondition: two docs exist in the test Drive folder —
          - doc A: last modified 3 days ago (should be discovered)
          - doc B: last modified 8 days ago (should be ignored)
        The fixture stores the expected docId as 'discoveryRecentDocId' in
        local.settings.json so the test can reference it.
        """
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        import json, pathlib
        settings_path = pathlib.Path("local.settings.json")
        if not settings_path.exists():
            pytest.skip("local.settings.json not found")
        settings = json.loads(settings_path.read_text())
        recent_doc_id = settings.get("discoveryRecentDocId")
        if not recent_doc_id:
            pytest.skip("discoveryRecentDocId not set in local.settings.json")

        clear_logs(gas_log_dir)
        setup_fixture('discovery')
        sync_all()
        complete_entry = wait_for_log(
            gas_log_dir, lambda e: e.get("tag") == "sync.complete"
        )

        assert complete_entry is not None, "sync.complete log entry not found after syncAll()"

        processed_ids = complete_entry.get("data", {}).get("docIds", [])
        assert recent_doc_id in processed_ids, (
            f"Recently-modified doc {recent_doc_id!r} was not processed by syncAll(). "
            f"Processed docIds: {processed_ids}"
        )

    def test_discovery_ignores_stale_doc(
        self, test_sheet_id, test_doc_id, gas_log_dir
    ):
        """After setupTestFixtures('discovery') + syncAll(), a doc last modified
        8 days ago must NOT appear in the sync.complete log entry's processed docIds.

        Uses the same fixture as test_discovery_finds_recently_modified_doc.
        """
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        import json, pathlib
        settings_path = pathlib.Path("local.settings.json")
        if not settings_path.exists():
            pytest.skip("local.settings.json not found")
        settings = json.loads(settings_path.read_text())
        stale_doc_id = settings.get("discoveryStaleDocId")
        if not stale_doc_id:
            pytest.skip("discoveryStaleDocId not set in local.settings.json")

        clear_logs(gas_log_dir)
        setup_fixture('discovery')
        sync_all()
        complete_entry = wait_for_log(
            gas_log_dir, lambda e: e.get("tag") == "sync.complete"
        )

        assert complete_entry is not None, "sync.complete log entry not found after syncAll()"

        processed_ids = complete_entry.get("data", {}).get("docIds", [])
        assert stale_doc_id not in processed_ids, (
            f"Stale doc {stale_doc_id!r} (modified 8 days ago) was incorrectly "
            f"included in syncAll() run. Processed docIds: {processed_ids}"
        )

    def test_discovery_finds_doc_in_subfolder(
        self, test_sheet_id, test_doc_id, gas_log_dir
    ):
        """When DOC_FOLDER_ID points to a parent folder, syncAll() must also discover
        docs in subfolders modified within the last 7 days.

        Fixture precondition: setupTestFixtures('discovery_subfolder') places a
        recently-modified doc in a subfolder of the configured DOC_FOLDER_ID.
        The fixture stores the subfolder doc's ID as 'discoverySubfolderDocId'
        in local.settings.json.
        """
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        import json, pathlib
        settings_path = pathlib.Path("local.settings.json")
        if not settings_path.exists():
            pytest.skip("local.settings.json not found")
        settings = json.loads(settings_path.read_text())
        subfolder_doc_id = settings.get("discoverySubfolderDocId")
        if not subfolder_doc_id:
            pytest.skip("discoverySubfolderDocId not set in local.settings.json")

        clear_logs(gas_log_dir)
        setup_fixture('discovery_subfolder')
        sync_all()
        complete_entry = wait_for_log(
            gas_log_dir, lambda e: e.get("tag") == "sync.complete"
        )

        assert complete_entry is not None, "sync.complete log entry not found after syncAll()"

        processed_ids = complete_entry.get("data", {}).get("docIds", [])
        assert subfolder_doc_id in processed_ids, (
            f"Subfolder doc {subfolder_doc_id!r} was not discovered by syncAll() "
            f"when DOC_FOLDER_ID points to parent folder. "
            f"Processed docIds: {processed_ids}"
        )
