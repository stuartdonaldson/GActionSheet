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


# Acceptance Criteria Registry (T24 traceability — see GTaskSheet-1wuu)
# Maps AC identifier to description. Used by scripts/check_coverage.py to validate test coverage.
AC_REGISTRY: dict[str, str] = {
    "b7 write-edit": "B7 action edit via web form",
    "b7 write-status": "B7 action status change via web form",
    "journey idempotent": "Journey idempotency across operations",
    "journey status-change": "Journey status change propagation",
    "journey sync-create": "Journey create action → doc+sheet sync",
    "journey tracker-present": "Journey tracker field presence",
    "journey ui-create": "Journey UI create form",
    "sidebar mutation-baseline": "Sidebar baseline state after mutations",
    "sidebar mutation-changed": "Sidebar state change tracking",
    "sidebar sync-SHEET": "Sidebar SHEET surface sync",
    "sidebar tracker-insert": "Sidebar tracker insert operation",
    "t": "Generic test marker",
    "uc AC-1": "Use case AC-1",
    "uc AC-2": "Use case AC-2",
    "uc TEST": "Use case test marker",
    "uc1 AC1": "Use case 1 AC1",
    "uc1 AC2": "Use case 1 AC2",
    "uc1 AC3": "Use case 1 AC3",
    "uc1 AC4": "Use case 1 AC4",
    "t1": "Test scenario 1",
    "t2": "Test scenario 2",
}

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
    "AC_REGISTRY",
]
