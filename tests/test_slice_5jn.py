"""
Slice tests for 5jn: new action capture — parser, normalizer, sheet row creation.

All tests are marked xfail until the 5jn GAS modules are deployed:
  - FloatingActionParser.js
  - DocumentNormalizer.js
  - SheetReconciler.js (new-row path)
  - SyncOrchestrator.js

Each test:
  1. Resets the test doc/sheet to a known fixture state via setupTestFixtures(scenario).
  2. Runs syncDocument(testDocId) via the GAS editor.
  3. Downloads the sheet as .xlsx and the doc as .docx.
  4. Asserts the expected outcome.

The GAS function invocations (setupTestFixtures, syncDocument) are triggered via the
Playwright editor helper. The Playwright integration is not yet wired in Python —
those calls are marked with TODO comments matching the pattern in test_infrastructure.py
and test_acceptance.py.

Prerequisites:
  - local.settings.json populated with testSheetId, testDocId, scriptId, gasLogDir
  - Test sheet and doc shared with "Anyone with link (viewer)"
  - .auth/user.json present (run `node tests/playwright/authenticate.js` once)
"""
import datetime
import pytest

from tests.helpers.download import download_xlsx, download_docx
from tests.helpers.sheet_inspect import load_sheet, find_row, assert_date_cell, headers
from tests.helpers.doc_inspect import (
    load_doc,
    find_table_row,
    floating_actions,
    tracked_actions_table,
)
from tests.helpers.gas_log import clear_logs, wait_for_log
from tests.helpers.gas_invoke import setup_fixture, sync_document

# Expected tracked-actions table column headers (left-to-right)
TRACKED_ACTIONS_HEADERS = [
    "ID",
    "Assignee Email",
    "Assignee Name",
    "Action",
    "Status",
    "Date Created",
    "Date Modified",
]


# ---------------------------------------------------------------------------
# AC-1: New floating action receives next sequential ID
# ---------------------------------------------------------------------------


class TestNewFloatingActionGetsSequentialId:
    """5jn AC-1: a bare AI- floating action is assigned the next sequential ID and
    appears in both the doc tracked-actions table and the sheet Actions tab."""

    def test_new_floating_action_gets_sequential_id(
        self, test_sheet_id, test_doc_id, gas_log_dir
    ):
        """After setupTestFixtures('ac1') + syncDocument(), the AI- paragraph in the
        test doc receives an ID (expected: 1 for a fresh doc), and a matching row
        appears in the sheet 'Actions' tab with a hyperlinked Document cell."""
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        clear_logs(gas_log_dir)
        setup_fixture('ac1')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.complete")

        # --- sheet assertion ---
        xlsx = download_xlsx(test_sheet_id)
        ws = load_sheet(xlsx, sheet_name="Actions")
        row = find_row(
            ws,
            doc_url=f"docs.google.com/document/d/{test_doc_id}",
            action_id=1,
        )
        assert row is not None, (
            "Sheet 'Actions' tab has no row with ID=1 linking to the test doc"
        )
        assert row["Action"] is not None and row["Action"] != "", (
            "Sheet row Action cell is empty"
        )

        # Document cell must be a hyperlink (find_row already checks hyperlink target)
        # so passing find_row means the hyperlink condition is satisfied.

        # --- doc table assertion ---
        docx_bytes = download_docx(test_doc_id)
        doc = load_doc(docx_bytes)
        table_row = find_table_row(doc, action_id=1)
        assert table_row is not None, (
            "Tracked-actions table in doc has no row with ID=1"
        )

    def test_floating_action_id_written_back_to_paragraph(
        self, test_doc_id, gas_log_dir
    ):
        """After sync, the floating-action paragraph itself is rewritten with the
        assigned ID (AI-1 …) — bare AI- must no longer appear."""
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        clear_logs(gas_log_dir)
        setup_fixture('ac1')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.complete")

        docx_bytes = download_docx(test_doc_id)
        doc = load_doc(docx_bytes)
        actions = floating_actions(doc)
        assert any(a["id"] == 1 for a in actions), (
            f"No floating action with id=1 found after sync. Got: {actions}"
        )
        bare = [
            p.text.strip()
            for p in doc.paragraphs
            if p.text.strip().startswith("AI-") and not any(
                c.isdigit() for c in p.text.strip()[3:4]
            )
        ]
        assert not bare, (
            f"Bare 'AI-' paragraph(s) still present after sync: {bare}"
        )


# ---------------------------------------------------------------------------
# AC-2: Existing ID preserved
# ---------------------------------------------------------------------------


class TestExistingIdPreserved:
    """5jn AC-2: a floating action that already carries an explicit ID retains it."""

    def test_existing_id_preserved(self, test_sheet_id, test_doc_id, gas_log_dir):
        """After setupTestFixtures('ac2') + syncDocument(), an AI-5 action retains
        ID=5 in both the doc tracked-actions table and the sheet."""
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        clear_logs(gas_log_dir)
        setup_fixture('ac2')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.complete")

        # --- sheet assertion ---
        xlsx = download_xlsx(test_sheet_id)
        ws = load_sheet(xlsx, sheet_name="Actions")
        row = find_row(
            ws,
            doc_url=f"docs.google.com/document/d/{test_doc_id}",
            action_id=5,
        )
        assert row is not None, "Sheet 'Actions' tab has no row with ID=5"

        # --- doc table assertion ---
        docx_bytes = download_docx(test_doc_id)
        doc = load_doc(docx_bytes)
        table_row = find_table_row(doc, action_id=5)
        assert table_row is not None, (
            "Tracked-actions table in doc has no row with ID=5"
        )


# ---------------------------------------------------------------------------
# Section and table auto-creation
# ---------------------------------------------------------------------------


class TestMissingSectionAutocreated:
    """5jn: when the doc has no 'Tracked Actions' section, normalizer creates it."""

    def test_missing_section_autocreated(self, test_doc_id, gas_log_dir):
        """After setupTestFixtures('no_section') + syncDocument(), the doc must
        contain a HEADING1 paragraph with text 'Tracked Actions'."""
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        clear_logs(gas_log_dir)
        setup_fixture('no_section')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.complete")

        docx_bytes = download_docx(test_doc_id)
        doc = load_doc(docx_bytes)

        heading_texts = [
            p.text.strip()
            for p in doc.paragraphs
            if p.style.name.startswith("Heading 1") or p.style.name == "Heading1"
        ]
        assert "Tracked Actions" in heading_texts, (
            f"HEADING1 'Tracked Actions' not found. Headings present: {heading_texts}"
        )


class TestMissingTableAutocreated:
    """5jn: when the 'Tracked Actions' section exists but has no table, normalizer
    creates the table with the correct 7-column header row."""

    def test_missing_table_autocreated(self, test_doc_id, gas_log_dir):
        """After setupTestFixtures('no_table') + syncDocument(), the tracked-actions
        table must be present under the existing section with all required headers."""
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        clear_logs(gas_log_dir)
        setup_fixture('no_table')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.complete")

        docx_bytes = download_docx(test_doc_id)
        doc = load_doc(docx_bytes)

        rows = tracked_actions_table(doc)
        assert rows is not None, (
            "tracked_actions_table() returned None — section or table not found in doc"
        )

        # Verify headers by inspecting the raw table (rows list excludes the header row,
        # so we inspect the first table under the section directly via doc_inspect internals)
        # Re-derive headers from the first data dict keys as a proxy
        if rows:
            actual_keys = set(rows[0].keys())
        else:
            # Table was created but is empty — check raw header row
            actual_keys = _get_tracked_table_headers(doc)

        missing = [h for h in TRACKED_ACTIONS_HEADERS if h not in actual_keys]
        assert not missing, (
            f"Tracked-actions table missing headers: {missing}. "
            f"Present: {sorted(actual_keys)}"
        )

    def test_table_headers_in_correct_order(self, test_doc_id, gas_log_dir):
        """The 7 required columns must appear in the declared left-to-right order."""
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        clear_logs(gas_log_dir)
        setup_fixture('no_table')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.complete")

        docx_bytes = download_docx(test_doc_id)
        doc = load_doc(docx_bytes)

        actual_headers = _get_tracked_table_headers(doc)
        assert actual_headers is not None, "Could not read header row from tracked-actions table"

        # Filter to only the required headers and check their relative order
        positions = {h: actual_headers.index(h) for h in TRACKED_ACTIONS_HEADERS if h in actual_headers}
        ordered_positions = [positions[h] for h in TRACKED_ACTIONS_HEADERS if h in positions]
        assert ordered_positions == sorted(ordered_positions), (
            f"Headers not in expected order. "
            f"Got: {list(zip(TRACKED_ACTIONS_HEADERS, ordered_positions))}"
        )


def _get_tracked_table_headers(document) -> list[str] | None:
    """Return the header cell texts from the tracked-actions table, or None if not found."""
    from tests.helpers.doc_inspect import _iter_block_items, _SECTION_HEADING
    in_section = False
    for block in _iter_block_items(document):
        if hasattr(block, "text"):
            if block.text.strip() == _SECTION_HEADING:
                in_section = True
                continue
            if in_section and block.style.name.startswith("Heading"):
                break
        elif in_section and hasattr(block, "rows"):
            return [cell.text.strip() for cell in block.rows[0].cells]
    return None


# ---------------------------------------------------------------------------
# Synced column is a datetime value
# ---------------------------------------------------------------------------


class TestSyncedColumnWritten:
    """5jn: the 'Synced' column in the sheet row must be a datetime cell after sync."""

    def test_synced_column_written(self, test_sheet_id, test_doc_id, gas_log_dir):
        """After setupTestFixtures('ac1') + syncDocument(), the 'Synced' cell for
        the newly created row must hold a native datetime value (not a string)."""
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        clear_logs(gas_log_dir)
        setup_fixture('ac1')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.complete")

        xlsx = download_xlsx(test_sheet_id)
        ws = load_sheet(xlsx, sheet_name="Actions")

        col_map = headers(ws)
        assert "Synced" in col_map, "Sheet 'Actions' tab has no 'Synced' column"

        synced_col_idx = col_map["Synced"]
        id_col_idx = col_map["ID"]

        synced_cell = None
        for row in ws.iter_rows(min_row=2, values_only=False):
            if row[id_col_idx - 1].value == 1:
                synced_cell = row[synced_col_idx - 1]
                break

        assert synced_cell is not None, "No sheet row with ID=1 found after sync"
        assert isinstance(synced_cell.value, datetime.datetime), (
            f"'Synced' cell is {type(synced_cell.value).__name__}, expected datetime. "
            f"Value: {synced_cell.value!r}"
        )
