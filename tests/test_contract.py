"""
Contract-bridge tests (GTaskSheet-5vwu.3).

These tests pin sentinel values from ContractSchema.js via the JSON export.
A deliberate field rename in ContractSchema.js + re-export will make
test_sentinel_field_names fail loudly — that is intentional.
"""
import pytest
import scn.contract as contract


def test_contract_loads():
    assert isinstance(contract.SHEET_HEADERS, list)
    assert len(contract.SHEET_HEADERS) > 0
    assert isinstance(contract.COLUMNS_BY_FIELD, dict)
    assert isinstance(contract.ROUTE_NAMES, list)
    assert isinstance(contract.TEST_ROUTE_NAMES, list)


def test_sentinel_field_names():
    # Critical harness identifiers — rename any of these in ContractSchema.js
    # and this test fails after re-export.
    assert 'global_id' in contract.SHEET_ACTION_FIELDS
    assert 'document_formula' in contract.SHEET_ACTION_FIELDS
    assert contract.SHEET_HEADERS[0] == 'NamedRangeId'  # retained alias for global_id
    assert 'sync_action_rows' in contract.ROUTE_NAMES
    assert 'edit_action_row' in contract.TEST_ROUTE_NAMES
    assert 'find_sheet_actions' in contract.TEST_ROUTE_NAMES


def test_derived_fields_not_in_columns():
    # doc_id and doc_name are derived from document_formula (col 7), not stored columns.
    for field in contract.DERIVED_FIELDS:
        assert field in contract.SHEET_ACTION_FIELDS, f"{field} must be in SHEET_ACTION_FIELDS"
        assert field not in contract.COLUMNS_BY_FIELD, f"{field} must NOT be in COLUMNS_BY_FIELD (it is derived)"


def test_column_count_coherence():
    # COLUMNS_BY_FIELD and SHEET_HEADERS must have the same count (both represent the 10 stored columns).
    assert len(contract.COLUMNS_BY_FIELD) == len(contract.SHEET_HEADERS), (
        f"COLUMNS_BY_FIELD has {len(contract.COLUMNS_BY_FIELD)} entries "
        f"but SHEET_HEADERS has {len(contract.SHEET_HEADERS)} — they must match"
    )
