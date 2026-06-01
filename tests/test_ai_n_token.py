"""
test_ai_n_token.py — GTaskSheet-sjj AC1, AC2, AC5 (create entry point).

Exercises the AI-N token scanner and bare-AI: upgrade path directly via HTTP fixture,
without requiring the editor add-on to be installed as a test deployment.

AC1: Scanner returns globalId with correct format {docId}/AI-{N} and the expected
     action text.
AC2: The sheet row written by syncDocument stores the same globalId in col-1
     (globalId column), confirming the create path sets the correct value.
AC5 (partial): syncDocument is the call-site exercised here for the AI: → AI-N:
     upgrade sub-path; sidebarSetStatus / sidebarDeleteAction are covered by
     test_uc_sidebar_mutations.py.
"""

import re
import pytest

from tests.helpers.fixture_invoke import invoke_fixture
from tests.helpers.download import download_xlsx
from tests.helpers.sheet_inspect import load_sheet, rows_as_dicts

_GLOBAL_ID_RE = re.compile(r'^[A-Za-z0-9_-]{25,44}/AI-\d+$')
_ACTION_TEXT   = 'ANT: verify AI-N token format and globalId assignment'


@pytest.fixture(scope="module")
def ai_n_state(test_doc_id, test_sheet_id, settings):
    """Invoke ai_n_token_scan fixture and download the resulting sheet."""
    result = invoke_fixture("ai_n_token_scan", test_doc_id, settings, timeout=180)
    xlsx   = download_xlsx(test_sheet_id)
    yield {
        "global_id":  (result.get("data") or {}).get("globalId", ""),
        "action_text": (result.get("data") or {}).get("actionText", ""),
        "doc_id":     (result.get("data") or {}).get("docId", test_doc_id),
        "xlsx":       xlsx,
    }


def test_ai_n_globalid_format(ai_n_state):
    """AC1: Scanner assigns a globalId with the expected {docId}/AI-{N} format."""
    gid = ai_n_state["global_id"]
    assert gid, "[sjj AC1] Fixture returned empty globalId — scanner did not assign a token"
    assert _GLOBAL_ID_RE.match(gid), (
        f"[sjj AC1] globalId format invalid: {gid!r} (expected '{{docId}}/AI-{{N}}')"
    )


def test_ai_n_doc_id_prefix(ai_n_state):
    """AC1: The docId prefix of globalId matches the test document."""
    gid    = ai_n_state["global_id"]
    doc_id = ai_n_state["doc_id"]
    assert gid.startswith(doc_id + "/AI-"), (
        f"[sjj AC1] globalId {gid!r} does not start with doc_id {doc_id!r}/AI-"
    )


def test_ai_n_sheet_row_col1(ai_n_state):
    """AC2: Sheet col-1 (globalId) for the new row equals the returned globalId."""
    gid  = ai_n_state["global_id"]
    ws   = load_sheet(ai_n_state["xlsx"], sheet_name="Actions")
    rows = [r for r in rows_as_dicts(ws) if _ACTION_TEXT in (r.get("Action") or "")]

    assert rows, (
        f"[sjj AC2] No sheet row found with action text {_ACTION_TEXT!r} — "
        "syncDocument may not have written the row"
    )
    assert len(rows) == 1, (
        f"[sjj AC2] Expected exactly 1 sheet row for the new action, got {len(rows)}: {rows}"
    )
    sheet_gid = rows[0].get("globalId") or ""
    assert sheet_gid == gid, (
        f"[sjj AC2] Sheet col-1 (globalId) {sheet_gid!r} does not match "
        f"fixture-returned globalId {gid!r}"
    )
