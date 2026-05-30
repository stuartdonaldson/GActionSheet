"""
contract.py — load and expose ContractSchema.json (GTaskSheet-5vwu.3).

Single source of truth for field names, headers, column indices, and route names.
Consumed by all scenario harness modules (scn/ai, scn/engine, scn/surfaces, etc.)
to avoid duplicating contract definitions.

Contract semantics: docs/DESIGN.md §ATDD Journey Pre-Code Contract.
Machine-readable schema: src/ContractSchema.js (exported to ContractSchema.json).
"""
import json
from pathlib import Path

# Load ContractSchema.json — path is relative to this file's parent (scn/).
_contract_path = Path(__file__).parent.parent / "ContractSchema.json"
with open(_contract_path) as f:
    _schema = json.load(f)

# Top-level contract shapes
_action_item = _schema.get("actionItem", {})
_sheet_action = _schema.get("sheetAction", {})
_web_app = _schema.get("webApp", {})
_doc_read = _schema.get("documentRead", {})

# ActionItem contract
ACTION_ITEM_FIELDS: list[str] = list(_action_item.get("fields", []))

# SheetAction contract (10 stored columns + 2 derived fields)
SHEET_ACTION_FIELDS: list[str] = list(_sheet_action.get("fields", []))
SHEET_HEADERS: list[str] = list(_sheet_action.get("headers", []))
COLUMNS_BY_FIELD: dict[str, int] = dict(_sheet_action.get("columnsByField", {}))

# Derived fields — not stored columns; resolved from document_formula (col 7)
DERIVED_FIELDS: frozenset[str] = frozenset(["doc_id", "doc_name"])

# WebApp routes (production + test-support)
ROUTE_NAMES: list[str] = list(_web_app.get("routeNames", []))
TEST_ROUTE_NAMES: list[str] = list(_web_app.get("testRouteNames", []))

# Per-route request/response/completion-signal shapes
MESSAGES: dict = dict(_web_app.get("messages", {}))

# Document read model names
MODEL_NAMES: list[str] = list(_doc_read.get("modelNames", []))


__all__ = [
    "ACTION_ITEM_FIELDS",
    "SHEET_ACTION_FIELDS",
    "SHEET_HEADERS",
    "COLUMNS_BY_FIELD",
    "DERIVED_FIELDS",
    "ROUTE_NAMES",
    "TEST_ROUTE_NAMES",
    "MESSAGES",
    "MODEL_NAMES",
]
