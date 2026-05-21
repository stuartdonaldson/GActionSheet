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

SCENARIO_MATRIX = [
    (
        "uc1_new_floating",
        {
            "expected_log_tag": "sync.complete",
            "expected_floating_actions": [
                {"id": 1, "action": "Fix the bug", "status": "Open"},
            ],
            "expected_table_rows": [
                {"id": 1, "action": "Fix the bug", "status": "Open"},
            ],
            "expected_sheet_rows": [
                {"id": 1, "action": "Fix the bug", "status": "Open", "doc_url_contains": "docs.google.com"},
            ],
        },
    ),
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
                {"id": 1, "action": "Fix the bug", "status": "In Review"},
            ],
        },
    ),
    (
        "uc3_doc_wins",
        {
            "expected_log_tag": "sync.sheet-updated",
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
        "uc5_bare_reference",
        {
            "expected_log_tag": "sync.complete",
            "expected_floating_actions": [
                {"id": 5, "action": "Deploy to staging", "status": "Open"},
            ],
            "expected_sheet_rows": [
                {"id": 5, "action": "Deploy to staging", "status": "Open", "doc_url_contains": "docs.google.com"},
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
    wait_for_log(gas_log_dir, lambda e: e.get("tag") == expectations["expected_log_tag"])
    xlsx_bytes = download_xlsx(test_sheet_id)
    docx_bytes = download_docx(test_doc_id)
    assert_scenario(scenario, expectations, xlsx_bytes, docx_bytes)


def _run_idempotent(expectations, test_sheet_id, test_doc_id, gas_log_dir):
    # First sync
    clear_logs(gas_log_dir)
    setup_and_sync("uc_idempotent", test_doc_id)
    wait_for_log(gas_log_dir, lambda e: e.get("tag") == expectations["expected_log_tag"])
    xlsx1 = download_xlsx(test_sheet_id)
    docx1 = download_docx(test_doc_id)

    # Second sync (no setup — repeat sync only)
    clear_logs(gas_log_dir)
    setup_and_sync("uc_idempotent", test_doc_id)
    wait_for_log(gas_log_dir, lambda e: e.get("tag") == expectations["expected_log_tag"])
    xlsx2 = download_xlsx(test_sheet_id)
    docx2 = download_docx(test_doc_id)

    assert xlsx1 == xlsx2, "[uc_idempotent] Sheet content changed on second sync — not idempotent"
    assert docx1 == docx2, "[uc_idempotent] Doc content changed on second sync — not idempotent"
