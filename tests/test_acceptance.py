"""
Acceptance criteria tests (§19 of requirements.md).

Each test follows the same pattern:
  1. Reset fixtures to a known state via the GAS `setupTestFixtures(scenario)` function
     (triggered via the Playwright editor helper in conftest — not yet wired; marked xfail).
  2. Run `syncDocument(testDocId)` via the GAS editor.
  3. Download the sheet as .xlsx and the doc as .docx.
  4. Assert the expected outcome.

Prerequisites:
  - local.settings.json populated with testSheetId, testDocId, scriptId, gasLogDir
  - Test sheet shared with "Anyone with link (viewer)"
  - Test doc shared with "Anyone with link (viewer)"
  - .auth/user.json present (run `node tests/playwright/authenticate.js` once)
"""
import pytest

from tests.helpers.download import download_xlsx, download_docx
from tests.helpers.sheet_inspect import load_sheet, find_row, assert_date_cell
from tests.helpers.doc_inspect import load_doc, find_table_row, floating_actions
from tests.helpers.gas_log import clear_logs, wait_for_log
from tests.helpers.gas_invoke import setup_fixture, sync_document


class TestAC1NewFloatingActionReceivesId:
    """AC-1: A new floating action with no numeric ID receives next sequential ID
    and appears in both the tracked-actions table and the sheet after sync."""

    def test_floating_action_id_assigned(self, test_sheet_id, test_doc_id, gas_log_dir):
        # Precondition: doc contains `AI- @test@example.com | Fix the bug | Open`
        # tracked-actions table is empty. Sync has not run yet.
        clear_logs(gas_log_dir)
        setup_fixture('ac1')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.complete")

        xlsx = download_xlsx(test_sheet_id)
        ws = load_sheet(xlsx, sheet_name="Actions")
        row = find_row(ws, doc_url=f"docs.google.com/document/d/{test_doc_id}", action_id=1)
        assert row is not None, "Sheet row with ID=1 not found"
        assert row["Action"] == "Fix the bug"
        assert row["Status"] == "Open"
        assert_date_cell(ws, row, "Date Created")
        assert_date_cell(ws, row, "Date Modified")

    def test_floating_action_rewritten_in_doc(self, test_doc_id, gas_log_dir):
        docx_bytes = download_docx(test_doc_id)
        doc = load_doc(docx_bytes)
        actions = floating_actions(doc)
        assert any(a["id"] == 1 and a["action"] == "Fix the bug" for a in actions), (
            f"Floating action AI-1 not found. Got: {actions}"
        )

    def test_table_row_created_in_doc(self, test_doc_id):
        docx_bytes = download_docx(test_doc_id)
        doc = load_doc(docx_bytes)
        row = find_table_row(doc, action_id=1)
        assert row is not None, "Tracked-actions table row with ID=1 not found"
        assert row["Action"] == "Fix the bug"


class TestAC2ExistingIdPreserved:
    """AC-2: A floating action that already has an ID preserves that ID after sync."""

    def test_id_preserved(self, test_sheet_id, test_doc_id, gas_log_dir):
        # Precondition: doc contains `AI-5 @test@example.com | Review PR | Open`
        clear_logs(gas_log_dir)
        setup_fixture('ac2')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.complete")

        xlsx = download_xlsx(test_sheet_id)
        ws = load_sheet(xlsx, sheet_name="Actions")
        row = find_row(ws, doc_url=f"docs.google.com/document/d/{test_doc_id}", action_id=5)
        assert row is not None, "Sheet row with ID=5 not found"
        assert row["Action"] == "Review PR"

        docx_bytes = download_docx(test_doc_id)
        doc = load_doc(docx_bytes)
        table_row = find_table_row(doc, action_id=5)
        assert table_row is not None, "Table row with ID=5 not found"


class TestAC3DocWinsOnNewerTimestamp:
    """AC-3: When the document record has a later modified timestamp,
    the sheet row is updated from the document."""

    def test_sheet_row_updated_from_doc(self, test_sheet_id, test_doc_id, gas_log_dir):
        # Precondition: sheet row Date Modified = T-1h; table row Date Modified = T; Status="Done"
        clear_logs(gas_log_dir)
        setup_fixture('ac3')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.sheet-updated")

        xlsx = download_xlsx(test_sheet_id)
        ws = load_sheet(xlsx, sheet_name="Actions")
        row = find_row(ws, doc_url=f"docs.google.com/document/d/{test_doc_id}", action_id=1)
        assert row is not None
        assert row["Status"] == "Done"
        assert_date_cell(ws, row, "Date Modified")


class TestAC4SheetWinsOnNewerTimestamp:
    """AC-4: When the sheet row has a later modified timestamp,
    the document table row and matching floating action are updated."""

    def test_doc_updated_from_sheet(self, test_doc_id, gas_log_dir):
        # Precondition: table row Date Modified = T-1h; sheet row Date Modified = T; Status="In Review"
        clear_logs(gas_log_dir)
        setup_fixture('ac4')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.doc-updated")

        docx_bytes = download_docx(test_doc_id)
        doc = load_doc(docx_bytes)

        table_row = find_table_row(doc, action_id=1)
        assert table_row is not None
        assert table_row["Status"] == "In Review"

        actions = floating_actions(doc)
        matching = [a for a in actions if a["id"] == 1]
        assert matching, "Floating action AI-1 not found after sync"
        assert matching[0]["status"] == "In Review"


class TestAC5IdempotentSecondSync:
    """AC-5: A second sync immediately after a successful sync makes no additional changes."""

    def test_second_sync_no_changes(self, test_sheet_id, test_doc_id, gas_log_dir):
        # First sync
        clear_logs(gas_log_dir)
        setup_fixture('ac5')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.complete")

        xlsx1 = download_xlsx(test_sheet_id)
        docx1 = download_docx(test_doc_id)

        # Second sync
        clear_logs(gas_log_dir)
        sync_document(test_doc_id)
        wait_for_log(
            gas_log_dir,
            lambda e: e.get("tag") == "sync.complete" and e.get("data", {}).get("changes") == 0,
        )

        xlsx2 = download_xlsx(test_sheet_id)
        docx2 = download_docx(test_doc_id)

        assert xlsx1 == xlsx2, "Sheet content changed on second sync — not idempotent"
        assert docx1 == docx2, "Doc content changed on second sync — not idempotent"
