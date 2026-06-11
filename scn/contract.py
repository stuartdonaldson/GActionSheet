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
    "teamscope teamdata-safety": "S0 - TeamData fixture setup leaves pre-existing rows unchanged; new rows are test-marked only",
    "teamscope direct-match": "S1a - auto-assign when doc is directly in a registered team's folder",
    "teamscope subteam-match": "S1b - auto-assign matches a more specific sub-team folder over its registered parent",
    "teamscope deep-walk": "S1c - auto-assign walks multiple unregistered ancestor levels to the nearest registered folder",
    "teamscope no-match": "S2 - no TeamData match leaves teamScope blank",
    "teamscope updatedoc-override": "S3 - DocData SyncStatus=UpdateDoc overrides document teamScope (DocData wins)",
    "teamscope idempotent": "S4 - second sync with no changes makes no further teamScope writes",
    "teamscope security-gate": "S5 - assertTeamAccess allows valid team-folder access",
    "teamscope teamdata-missing": "S6 - sync completes without assignment when TeamData is empty",
    "teamscope updatedoc-blank": "S7 - UpdateDoc with blank Team Id clears SyncStatus without crash",
    "teamscope sticky-after-move": "S8 - moving an already-assigned doc to another team's folder does not reassign",
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

# Entry-Point Registry (T1/T17 entry-point coverage; T24 gap-diff — see GTaskSheet-me6w.2)
# Maps a state-modifying GAS entry point to its description. Each scenario tags the entry
# point it exercises; ScenarioSession emits ep.<entry_point>.<surface> JUnit properties
# alongside ac.<tag>.<surface>. scripts/check_coverage.py diffs these keys against the
# emitted ep.* properties — the entry-point half of the gap-diff, binding on new harness
# work per the ratified T24 status note. Seeded with EPIC-B's two entry points; this is the
# minimal slice that proves the entry-point diff shape for GTaskSheet-me6w.6.
ENTRY_POINT_REGISTRY: dict[str, str] = {
    "syncDocument": "syncDocument(docId) — auto-assign / UpdateDoc-override / idempotent re-sync",
    "syncDocument.onSyncNow": "syncDocument(docId) via onSyncNow (WorkspaceAddonCard.js 'Sync now' "
        "button, doc-context) — distinct call-site from the run_fixture/Web-App path; "
        "getActiveSpreadsheet() is null here (GTaskSheet-yuvq)",
    "assertTeamAccess": "assertTeamAccess(teamId, ss) — team-scoped security gate on filtered reads",
    "setup_team_scope_fixture": "setup_team_scope_fixture — idempotent TeamData/folder fixture setup for team-scope scenarios",
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
    "ENTRY_POINT_REGISTRY",
]
