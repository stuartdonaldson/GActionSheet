"""
Parametrized UC scenario matrix tests.

Each scenario follows the standard sync flow:
  1. invoke_fixture(scenario) — sets up doc/sheet state via HTTP (no browser).
  2. invoke_fixture("sync_document") — runs the sync synchronously via HTTP.
  3. Download sheet as .xlsx and doc as .docx.
  4. Assert the expected outcome via assert_scenario().

The uc_idempotent scenario runs the flow twice and asserts content equality.

Prerequisites:
  - local.settings.json populated with testSheetId, testDocId, scriptId, testToken
  - Test sheet shared with "Anyone with link (viewer)"
  - Test doc shared with "Anyone with link (viewer)"
"""
import pytest

from tests.helpers.download import download_xlsx, download_docx
from tests.helpers.fixture_invoke import invoke_fixture
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
            "expected_table_rows": [
                {"id": 2, "action": "UCS-2: Review the PR", "status": "Open"},
            ],
            "expected_sheet_rows": [
                {"id": 2, "action": "UCS-2: Review the PR", "status": "Open", "doc_url_contains": "docs.google.com"},
            ],
        },
    ),
    (
        "uc3_sheet_wins",
        {
            "expected_table_rows": [
                {"id": 1, "action": "UCS-3SW: Fix the bug", "status": "In Review"},
            ],
            "expected_floating_actions": [
                {
                    "id": 1, "action": "UCS-3SW: Fix the bug", "status": "In Review",
                    "assignee_email": "test@example.com",
                },
            ],
            "expected_sheet_rows": [
                {"id": 1, "action": "UCS-3SW: Fix the bug", "status": "In Review", "doc_url_contains": "docs.google.com"},
            ],
        },
    ),
    (
        "uc3_doc_wins",
        {
            "expected_table_rows": [
                {"id": 1, "action": "UCS-3DW: Fix the bug", "status": "Done"},
            ],
            "expected_floating_actions": [
                {
                    "id": 1, "action": "UCS-3DW: Fix the bug", "status": "Done",
                    "assignee_email": "test@example.com",
                },
            ],
            "expected_sheet_rows": [
                {"id": 1, "action": "UCS-3DW: Fix the bug", "status": "Done", "doc_url_contains": "docs.google.com"},
            ],
        },
    ),
    (
        "uc4_archive",
        {
            "active_rows_prefix": "UCS-4: ",
            "expected_xlsx_active_rows": [
                {"id": 2, "action": "UCS-4: Review the PR", "status": "Open"},
            ],
            "expected_xlsx_archive_rows": [
                {"id": 1, "action": "UCS-4: Fix the bug", "status": "Done"},
            ],
        },
    ),
    (
        "uc6_revert_local_edit",
        {
            "expected_table_rows": [
                {"id": 3, "action": "UCS-6: Write tests", "status": "Open"},
            ],
            "expected_floating_actions": [
                {"id": 3, "action": "UCS-6: Write tests", "status": "Open"},
            ],
            "expected_sheet_rows": [
                {"id": 3, "action": "UCS-6: Write tests", "status": "Open", "doc_url_contains": "docs.google.com"},
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
def test_uc_scenario(scenario, expectations, test_sheet_id, test_doc_id, settings):
    if scenario == "uc_idempotent":
        _run_idempotent(test_sheet_id, test_doc_id, settings)
    else:
        _run_standard(scenario, expectations, test_sheet_id, test_doc_id, settings)


def _run_standard(scenario, expectations, test_sheet_id, test_doc_id, settings):
    invoke_fixture(scenario, test_doc_id, settings, timeout=300)
    invoke_fixture("sync_document", test_doc_id, settings, timeout=180)
    xlsx_bytes = download_xlsx(test_sheet_id)
    docx_bytes = download_docx(test_doc_id)
    assert_scenario(scenario, expectations, xlsx_bytes, docx_bytes, test_doc_id=test_doc_id)


def _run_idempotent(test_sheet_id, test_doc_id, settings):
    # First sync
    invoke_fixture("uc_idempotent", test_doc_id, settings, timeout=300)
    invoke_fixture("sync_document", test_doc_id, settings, timeout=180)
    xlsx1 = download_xlsx(test_sheet_id)
    docx1 = download_docx(test_doc_id)

    # Second sync (same setup — fixture is deterministic, re-runs normalize+reconcile)
    invoke_fixture("uc_idempotent", test_doc_id, settings, timeout=300)
    invoke_fixture("sync_document", test_doc_id, settings, timeout=180)
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
