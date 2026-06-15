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
    "import access-readable": "1dxz P1-P3 - list_importable_actions exposes actions for a readable team",
    "import access-absent": "1dxz P4 - list_importable_actions returns rows:[] for a TeamNotFound docId",
    "import ac1-list": "4gsx AC-1 - Import tab list grouped by source doc (doc_name ASC) and AI-N ASC within group",
    "import ac2-select": "4gsx AC-2 - select all + Import selected inserts new sequential AI-N rows",
    "import ac3-forward": "4gsx AC-3 - source rows marked Forwarded, suffixed, and dirty after import",
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
# Maps every *state-modifying* GAS entry point across the project to its description. Each
# scenario tags the entry point it exercises; ScenarioSession emits ep.<entry_point>.<surface>
# JUnit properties alongside ac.<tag>.<surface>. scripts/check_coverage.py diffs these keys
# against the emitted ep.* properties — the entry-point half of the gap-diff (T17), binding on
# new harness work per the ratified T24 status note.
#
# Project-wide buildout per GTaskSheet-z6f8 (T24 follow-up 2(b)): enumerates every
# state-modifying entry point in the four call-site classes the entry-point-coverage invariant
# names — menu items, time-based triggers, sidebar/add-on card actions, HTTP routes — plus the
# state-modifying test-support routes. Each description is prefixed with a [category] tag;
# [test-support ...] flags entries that exist only for the test harness (not product surface).
# Read-only / diagnostic entry points (e.g. onVerifySync, menuVerifyConsistency, find_sheet_actions,
# verify_action_rows, get_test_config, onShowTab, onImportSelectAll) are intentionally NOT
# registered — the invariant scopes to state-modifying call-sites only.
#
# Entry points with no current scenario call-site are listed in ENTRY_POINT_DEFERRED below;
# check_coverage.py treats those as explicitly warn-only (enumerated but not yet asserted),
# so the gap-diff stays green while the deferral backlog (EPIC GTaskSheet-rz4k) converts each
# to a real, tagged, durable-state call-site assertion.
ENTRY_POINT_REGISTRY: dict[str, str] = {
    # ── Core / covered ─────────────────────────────────────────────────────────────
    "syncDocument": "[core] syncDocument(docId) — auto-assign / UpdateDoc-override / idempotent re-sync",
    "assertTeamAccess": "[core] assertTeamAccess(teamId, ss) — team-scoped security gate on filtered reads",
    # ── Workspace add-on card actions (WorkspaceAddonCard.js) ────────────────────────
    "syncDocument.onSyncNow": "[workspace-card] syncDocument(docId) via onSyncNow ('Sync now' button, "
        "doc-context) — distinct call-site from the run_fixture/Web-App path; getActiveSpreadsheet() "
        "is null here (GTaskSheet-yuvq)",
    "onSetActionStatus": "[workspace-card] onSetActionStatus(e) — per-row status control -> sidebarSetStatus",
    "onDeleteAction": "[workspace-card] onDeleteAction(e) — per-row delete control -> sidebarDeleteAction",
    "onInsertTrackerTable": "[workspace-card] onInsertTrackerTable() — 'Insert tracker' button -> insertTrackerTable",
    "importSelectedSubmit": "[workspace-card] _submitImport(e) — Import tab 'Import selected' button: "
        "select+insert+upsert+forward (AC-2/AC-3/EPIC-D). The CHECK_BOX SelectionInput state cannot be "
        "driven via Playwright; importSelectedForTest is the interim surrogate (EPIC GTaskSheet-pw5x)",
    # ── Editor add-on card actions (EditorAddonCard.js) ──────────────────────────────
    "_submitCreateAction": "[editor-card] _submitCreateAction(e) — editor add-on create-action submit",
    "_setStatusFromPreview": "[editor-card] _setStatusFromPreview(e) — link-preview status dropdown -> _scheduleSheetUpdate",
    # ── Installable triggers ─────────────────────────────────────────────────────────
    "syncAll": "[trigger] syncAll() — 30-min time-based sweep (TriggerManager.js); ID-map P1-1 call-site",
    "onActionSheetEdit": "[trigger] onActionSheetEdit(e) — onEdit installable trigger (SyncManager.js); ID-map P1-2",
    "_processPendingSheetUpdates": "[trigger] _processPendingSheetUpdates(e) — async ACTION_SHEET_QUEUE drain (EditorAddonCard.js)",
    # ── Sheets menu items (MenuHandler.js) — state-modifying only ────────────────────
    "menuSync": "[menu] menuSync -> syncAll() (Action Sync > Sync)",
    "menuEnsureSheetStructure": "[menu] menuEnsureSheetStructure -> ensureSheetStructure() (Setup submenu)",
    "menuInitializeTriggers": "[menu] menuInitializeTriggers -> initializeTriggers() (Setup submenu)",
    "menuBootstrap": "[menu] menuBootstrap -> bootstrap() (Setup submenu)",
    "menuRunArchive": "[menu] menuRunArchive -> ArchiveManager.archive() (Test menu)",
    # ── HTTP routes (WebApp.js doPost) — state-modifying production routes ────────────
    "patch_action_status": "[route] patch_action_status — sidebar fast-path status enqueue (unconditional upsert)",
    "edit_action_row": "[route] edit_action_row — stamps Sync Status='Dirty' + Date Modified (onActionSheetEdit surrogate)",
    "upsert_action_rows": "[route] upsert_action_rows — programmatic write path (WEBAPP_SECRET-gated); no Dirty stamp",
    "sync_action_rows": "[route] sync_action_rows — bidirectional reconcile write route",
    "mark_doc_not_found": "[route] mark_doc_not_found — stamps DocData SyncStatus='Doc Not Found'",
    "delete_action_row": "[route] delete_action_row — stamps Sync Status='Deleted' (ADR-0009 §B terminal)",
    "forward_action_rows": "[route] forward_action_rows — AC-3 mark source rows Forwarded + suffix + dirty",
    "importList": "[route] list_importable_actions via Import tab render (show_tab('Import') -> "
        "_buildImportTabSection) — AC-1/EPIC-D team-scoped read; retained as the established import entry point",
    # ── Test-support entry points (harness only; flagged [test-support]) ─────────────
    "importSelectedForTest": "[test-support route] import_selected_for_test testToken route — interactive "
        "test entry point (GTaskSheet-8qe5/EPIC GTaskSheet-pw5x) standing in for the Import tab "
        "'Import selected' (_submitImport) AC-2/AC-3 select+insert+upsert+forward logic until the "
        "CHECK_BOX SelectionInput can be driven via Playwright",
    "setup_team_scope_fixture": "[test-support] setup_team_scope_fixture — idempotent TeamData/folder fixture setup",
    "run_fixture": "[test-support route] run_fixture — seeds doc/sheet fixtures for a scenario",
    "set_test_token": "[test-support route] set_test_token — writes the per-run test token script property",
    "bootstrap": "[test-support route] bootstrap — bootstraps test script properties",
    "begin_journey_session": "[test-support route] begin_journey_session — opens a journey test-session marker",
    "end_journey_session": "[test-support route] end_journey_session — closes a journey test-session marker",
}

# Deferred entry points (GTaskSheet-z6f8 / EPIC GTaskSheet-rz4k). Maps a registered entry point
# with NO current tagged scenario call-site to a one-line reason + tracking bead. check_coverage.py
# treats these as explicitly warn-only (not uncovered), so the T17 gap-diff stays green while the
# epic converts each to a real durable-state call-site assertion. "Warn-only" == enumerated but not
# yet asserted at its own call-site — documented debt, not coverage. Empty this dict as coverage lands.
ENTRY_POINT_DEFERRED: dict[str, str] = {
    # rz4k.3 — workspace/editor card mutations
    "importSelectedSubmit": "real Import-tab submit; CHECK_BOX SelectionInput not Playwright-drivable — covered via importSelectedForTest surrogate, EPIC GTaskSheet-pw5x — GTaskSheet-rz4k.3",
    # rz4k.4 — menu entry points
    "menuSync": "menu click call-site not driven; delegates to covered syncAll — GTaskSheet-rz4k.4",
    "menuEnsureSheetStructure": "menu click call-site not driven — GTaskSheet-rz4k.4",
    "menuInitializeTriggers": "menu click call-site not driven — GTaskSheet-rz4k.4",
    "menuBootstrap": "menu click call-site not driven — GTaskSheet-rz4k.4",
    "menuRunArchive": "menu click call-site not driven — GTaskSheet-rz4k.4",
    # rz4k.5 — test-support routes
    "run_fixture": "exercised as setup everywhere, never as a tagged asserted call-site — GTaskSheet-rz4k.5",
    "set_test_token": "harness plumbing; no tagged call-site assertion — GTaskSheet-rz4k.5",
    "bootstrap": "harness plumbing; no tagged call-site assertion — GTaskSheet-rz4k.5",
    "begin_journey_session": "session marker; no tagged call-site assertion — GTaskSheet-rz4k.5",
    "end_journey_session": "session marker; no tagged call-site assertion — GTaskSheet-rz4k.5",
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
    "ENTRY_POINT_DEFERRED",
]
