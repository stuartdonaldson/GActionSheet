"""
Parametrized UC scenario matrix tests.

Each scenario follows the standard sync flow:
  1. Clear GAS logs.
  2. Call setup_and_sync(scenario, test_doc_id) — sets up fixtures and triggers sync in GAS.
  3. Wait for the expected log tag to appear.
  4. Download sheet as .xlsx and doc as .docx.
  5. Assert the expected outcome via assert_scenario().

The uc_idempotent scenario runs the flow twice and asserts byte-level equality.

Prerequisites:
  - local.settings.json populated with testSheetId, testDocId, scriptId, gasLogDir
  - Test sheet shared with "Anyone with link (viewer)"
  - Test doc shared with "Anyone with link (viewer)"
  - .auth/user.json present (run `node tests/playwright/authenticate.js` once)
"""
import pytest

from tests.helpers.download import download_xlsx, download_docx
from tests.helpers.gas_log import clear_logs, wait_for_log
from tests.helpers.gas_invoke import setup_and_sync
from tests.helpers.scenario_assertions import assert_scenario

# ---------------------------------------------------------------------------
# Scenario matrix
# Each entry: (scenario_name, expectations_dict)
# ---------------------------------------------------------------------------


# UC-A scenarios (uc1_new_floating, uc_blank_status) have been superseded by
# the chip-led architecture tests in tests/test_uc_a.py.  The AI-prefix
# fixture format is legacy; do not add new AI-prefix scenarios here.

SCENARIO_MATRIX = [
    (
        "uc2_new_table_row",
        {
            "expected_log_tag": "sync.complete",
            "expected_table_rows": [
                {"id": 2, "action": "Review the PR", "status": "Open"},
            ],
            "expected_sheet_rows": [
                {"id": 2, "action": "Review the PR", "status": "Open", "doc_url_contains": "docs.google.com"},
            ],
        },
    ),
    (
        "uc3_sheet_wins",
        {
            "expected_log_tag": "sync.doc-updated",
            "expected_table_rows": [
                {"id": 1, "action": "Fix the bug", "status": "In Review"},
            ],
            "expected_floating_actions": [
                {
                    "id": 1, "action": "Fix the bug", "status": "In Review",
                    "assignee_email": "test@example.com",
                },
            ],
            "expected_sheet_rows": [
                {"id": 1, "action": "Fix the bug", "status": "In Review", "doc_url_contains": "docs.google.com"},
            ],
        },
    ),
    (
        "uc3_doc_wins",
        {
            "expected_log_tag": "sync.sheet-updated",
            "expected_table_rows": [
                {"id": 1, "action": "Fix the bug", "status": "Done"},
            ],
            "expected_floating_actions": [
                {
                    "id": 1, "action": "Fix the bug", "status": "Done",
                    "assignee_email": "test@example.com",
                },
            ],
            "expected_sheet_rows": [
                {"id": 1, "action": "Fix the bug", "status": "Done", "doc_url_contains": "docs.google.com"},
            ],
        },
    ),
    (
        "uc4_archive",
        {
            "expected_log_tag": "sync.complete",
            "expected_xlsx_active_rows": [
                {"id": 2, "action": "Review the PR", "status": "Open"},
            ],
            "expected_xlsx_archive_rows": [
                {"id": 1, "action": "Fix the bug", "status": "Done"},
            ],
        },
    ),
    (
        "uc6_revert_local_edit",
        {
            "expected_log_tag": "sync.complete",
            "expected_table_rows": [
                {"id": 3, "action": "Write tests", "status": "Open"},
            ],
            "expected_floating_actions": [
                {"id": 3, "action": "Write tests", "status": "Open"},
            ],
            "expected_sheet_rows": [
                {"id": 3, "action": "Write tests", "status": "Open", "doc_url_contains": "docs.google.com"},
            ],
        },
    ),
    (
        "uc_idempotent",
        {
            "expected_log_tag": "sync.complete",
        },
    ),
]


# ---------------------------------------------------------------------------
# Parametrized test
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "scenario,expectations",
    SCENARIO_MATRIX,
    ids=[s[0] for s in SCENARIO_MATRIX],
)
def test_uc_scenario(scenario, expectations, test_sheet_id, test_doc_id, gas_log_dir):
    if scenario == "uc_idempotent":
        _run_idempotent(expectations, test_sheet_id, test_doc_id, gas_log_dir)
    else:
        _run_standard(scenario, expectations, test_sheet_id, test_doc_id, gas_log_dir)


def _run_standard(scenario, expectations, test_sheet_id, test_doc_id, gas_log_dir):
    clear_logs(gas_log_dir)
    setup_and_sync(scenario, test_doc_id)
    def _log_matches(e):
        if e.get("tag") != expectations["expected_log_tag"]:
            return False
        doc_id_in_entry = e.get("data", {}).get("docId")
        return doc_id_in_entry is None or doc_id_in_entry == test_doc_id
    wait_for_log(gas_log_dir, _log_matches)
    xlsx_bytes = download_xlsx(test_sheet_id)
    docx_bytes = download_docx(test_doc_id)
    assert_scenario(scenario, expectations, xlsx_bytes, docx_bytes, test_doc_id=test_doc_id)


def _run_idempotent(expectations, test_sheet_id, test_doc_id, gas_log_dir):
    # First sync
    clear_logs(gas_log_dir)
    setup_and_sync("uc_idempotent", test_doc_id)
    wait_for_log(gas_log_dir, lambda e: e.get("tag") == expectations["expected_log_tag"])
    xlsx1 = download_xlsx(test_sheet_id)
    docx1 = download_docx(test_doc_id)

    # Second sync (same setup — fixture is deterministic, re-runs normalize+reconcile)
    clear_logs(gas_log_dir)
    setup_and_sync("uc_idempotent", test_doc_id)
    wait_for_log(gas_log_dir, lambda e: e.get("tag") == expectations["expected_log_tag"])
    xlsx2 = download_xlsx(test_sheet_id)
    docx2 = download_docx(test_doc_id)

    # Compare parsed content, not raw bytes: XLSX/DOCX ZIP headers embed modification
    # timestamps that vary between downloads even when underlying data is unchanged.
    # Date cells are also normalized (YYYY-MM-DD prefix) before comparison to handle
    # ISO vs plain format differences from GAS write-back timing.
    import re as _re
    from tests.helpers.sheet_inspect import load_sheet, rows_as_dicts
    from tests.helpers.doc_inspect import load_doc, floating_actions, tracked_actions_table

    def _normalize_dates(rows):
        """Replace ISO date strings with YYYY-MM-DD prefix for stable comparison."""
        result = []
        for row in rows:
            normalized = {}
            for k, v in row.items():
                if isinstance(v, str) and _re.match(r"\d{4}-\d{2}-\d{2}", v):
                    normalized[k] = v[:10]
                else:
                    normalized[k] = v
            result.append(normalized)
        return result

    rows1 = _normalize_dates(rows_as_dicts(load_sheet(xlsx1, sheet_name="Actions")))
    rows2 = _normalize_dates(rows_as_dicts(load_sheet(xlsx2, sheet_name="Actions")))
    assert rows1 == rows2, "[uc_idempotent] Sheet rows changed on second sync — not idempotent"

    doc1 = load_doc(docx1)
    doc2 = load_doc(docx2)
    fa1 = floating_actions(doc1)
    fa2 = floating_actions(doc2)
    assert fa1 == fa2, "[uc_idempotent] Floating actions changed on second sync — not idempotent"
    ta1 = _normalize_dates(tracked_actions_table(doc1) or [])
    ta2 = _normalize_dates(tracked_actions_table(doc2) or [])
    assert ta1 == ta2, "[uc_idempotent] Tracked-actions table changed on second sync — not idempotent"
