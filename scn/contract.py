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
    # gts-u6ew.12 (F7) — six journeys asserted but drained no AC; these tag one existing
    # assertion each so the journey reaches the T24 report. See testing guide §6.
    "sync-all reconcile": "Scenario D - syncAll integrity-pass reconciles DocData row counts and doc_name after a sweep across all registered docs",
    "scanner tracker-exclude": "dq6t AC-6 - AI: tokens inside the Action Item Tracker table are excluded from the floating-action scan",
    "menu entrypoint-callsite": "Sheets/Docs menu wrappers (menuSync et al.) are call-sites in their own right, not merely a pass-through to the delegate they invoke (T17)",
    "link-preview status": "cug8 - Editor add-on onLinkPreview card in-card status control converges the sheet row's status (_setStatusFromPreview)",
    "link-preview chip-disclosure": "ADR-0017 - anonymous chip-preview page discloses only non-confidential metadata and never the action text",
    "archive lifecycle": "d33z - a closed, aged action item is swept out of Actions and lands in Archive with globalId and File Id intact",
}

# Harness self-test fixture registry (gts-u6ew.4 / plan R22, finding F10).
#
# These are NOT acceptance criteria — they are tags the harness's own unit tests (test_scn_engine.py,
# test_scn_session.py) use to exercise ScenarioSession/Engine's verify()/expect_absent()/
# verify_all_expectations() machinery in isolation. They used to live in AC_REGISTRY, where they
# inflated the denominator by 27% (37 nominal vs. 27 real ACs) and were permanently counted as
# "uncovered" by scripts/check_coverage.py, since no production scenario ever tags them.
# scripts/check_coverage.py does NOT diff against this dict — it is documentation only.
AC_SELFTEST_FIXTURES: dict[str, str] = {
    "t": "Generic test marker",
    "t1": "Test scenario 1",
    "t2": "Test scenario 2",
    "uc AC-1": "Use case AC-1",
    "uc AC-2": "Use case AC-2",
    "uc TEST": "Use case test marker",
    "uc1 AC1": "Use case 1 AC1",
    "uc1 AC2": "Use case 1 AC2",
    "uc1 AC3": "Use case 1 AC3",
    "uc1 AC4": "Use case 1 AC4",
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
# Read-only / navigation entry points are intentionally NOT registered — the invariant scopes to
# state-modifying call-sites only. Those exemptions are no longer prose: the UI-handler ones are
# enumerated machine-readably in ENTRY_POINT_SOURCE_EXEMPT below, which
# scripts/check_entry_point_extraction.py reads (gts-u6ew.11). Read-only doPost routes
# (find_sheet_actions, verify_action_rows, get_test_config, ...) remain prose-only, since the
# route class is out of that extractor's scope — see that script's docstring.
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
    "syncDocument.onSyncNow": "[workspace-card] syncDocument(docId) via onSyncNow ('Sync' button, "
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
    "importList": "[route] list_importable_actions via Import card render (show_tab('Import') -> "
        "_buildImportCard/_buildImportTabSection) — AC-1/EPIC-D team-scoped read; retained as the established import entry point",
    "menuSyncActiveDoc": "[menu] menuSyncActiveDoc -> syncDocument(docId) (Docs 'Action Sync > Sync')",
    "menuInsertTrackerActiveDoc": "[menu] menuInsertTrackerActiveDoc -> insertTrackerTable(docId) (Docs 'Action Sync > Insert Tracker')",
    "team_sync_document": "[route] team_sync_document (TeamSync.js, _handleTeamSyncDocument) — team-portal "
        "write route; re-verifies identity/access tier and re-authorizes the doc-specific write (R3b) "
        "before running the existing syncDocument() path — gts-79dw.4.5/4.11/4.12",
    "onDocumentExportMenu": "[menu] onDocumentExportMenu (Procedure-Exporter.js, appsscript.json "
        "addOns.common.universalActions) — Extensions-menu universal action; runs exportDocument_() "
        "against the active document, writes a JSON export file to Drive (exportPdf=false)",
    "onDocumentExportAndPdfMenu": "[menu] onDocumentExportAndPdfMenu (Procedure-Exporter.js, appsscript.json "
        "addOns.common.universalActions) — same as onDocumentExportMenu with exportPdf=true, additionally "
        "writes a PDF export file to Drive",
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
    # ── Source-extraction sweep (gts-u6ew.11) ───────────────────────────────────────
    # Registered because scripts/check_entry_point_extraction.py found them wired in src/
    # (onOpen menu registration / appsscript.json runFunction / CardService action /
    # ScriptApp.newTrigger) and state-modifying, but absent from this registry — i.e. exactly
    # the silent uncoverage H12 exists to prevent. Every one is deferred below with a reason;
    # none was previously enumerated at all.
    "menuConfigFormat": "[menu] menuConfigFormat -> configFormat() (Setup > Configure Action Format) — "
        "samples a reference doc's formatting and writes the Config sheet's style rows",
    "menuForceRefreshActiveDoc": "[menu] menuForceRefreshActiveDoc -> sync_document(force=true) "
        "(Docs 'Action Sync > Force Refresh Style') — unconditional re-render of every ACT/AI paragraph",
    "nightlyAdminScanAllTeams": "[trigger] nightlyAdminScanAllTeams() — nightly admin sweep over every "
        "TeamData team (AdminDocScan.js); writes scan state per team",
    "_runNearImmediateSyncAll": "[trigger] _runNearImmediateSyncAll(e) — one-shot self-deleting trigger "
        "created by onActionSheetEdit to run syncAll() shortly after an edit (SyncManager.js)",
    "menuCleanupTestDocs": "[test-support menu] menuCleanupTestDocs() -> ArchiveManager.purgeByPrefix "
        "(Test > Cleanup Test Docs) — permanently deletes prefix-matching Actions/DocData rows",
    "menuBeginTestSession": "[test-support menu] menuBeginTestSession() -> beginTestSession(masterDocId) "
        "(Test > Begin Session), TestControl!A1-driven manual twin of the begin_journey_session route",
    "menuEndTestSession": "[test-support menu] menuEndTestSession() -> endTestSession(cloneId) "
        "(Test > End Session), TestControl!B1-driven manual twin of the end_journey_session route",
    "menuSetupFixture": "[test-support menu] menuSetupFixture() -> setupTestFixtures(scenario) "
        "(Test > Setup Fixture), manual twin of the run_fixture route",
    "menuSyncDocument": "[test-support menu] menuSyncDocument() -> syncDocument(docId) "
        "(Test > Sync Document), TestControl!A1-driven manual twin of the sync_document route",
    "menuSetupAndSync": "[test-support menu] menuSetupAndSync() -> setupAndSync(scenario, docId) "
        "(Test > Setup And Sync), manual twin of the run_fixture + sync_document pair",
    "menuInsertTrackerTable": "[test-support menu] menuInsertTrackerTable() -> insertTrackerTable(docId) "
        "(Test > Insert Tracker Table), TestControl!A1-driven manual twin of onInsertTrackerTable",
}

# Handlers wired in src/ that scripts/check_entry_point_extraction.py extracts but which are
# deliberately NOT entry points for the T17 invariant: they render or navigate a card, open a
# dialog, or emit a probe log, and modify no durable state. Machine-readable so the exemption
# is auditable (I6) instead of living in a prose comment that nothing reads. Adding a handler
# here is a claim that it is read-only — the reason is the claim's justification.
ENTRY_POINT_SOURCE_EXEMPT: dict[str, str] = {
    "onOpen": "simple trigger; builds the Sheets/Docs 'Action Sync' menus and logs. No durable state.",
    "buildHomepageCard": "add-on homepage card builder (appsscript.json homepageTrigger). Render-only.",
    "createActionTrigger": "Docs 'Create action' trigger — renders _buildCreationCard(); the mutation "
        "is the card's submit, _submitCreateAction, which IS registered.",
    "onLinkPreview": "link-preview card render (appsscript.json linkPreviewTriggers); the mutation is "
        "the preview's status dropdown, _setStatusFromPreview, which IS registered.",
    "onShowImport": "sidebar navigation — pushes the Import tab card.",
    "onShowNotify": "sidebar navigation — pushes the Notify tab card.",
    "onImportBack": "sidebar navigation — returns to the homepage card.",
    "onNotifyBack": "sidebar navigation — returns to the homepage card.",
    "onExportBackToHome": "export card navigation — returns to the homepage card.",
    "onImportSelectAll": "toggles CHECK_BOX selection state inside the rendered Import card only; "
        "nothing is written until _submitImport (registered as importSelectedSubmit).",
    "menuVerifyConsistency": "Test > Verify Consistency -> verifyConsistencyForTest(docId) — reads "
        "sheet+doc and reports; writes nothing.",
    "menuDebugDocBody": "Test > Debug Doc Body -> debugDocBody(docId) — dumps the doc body to the log.",
    "menuProbeIdentity": "Test > Probe Identity -> PROBE_log('menu.identity') — probe log only.",
    "menuShowExportDialog": "Docs 'Export…' -> showDocumentExportDialog_() — opens the modal dialog; "
        "the export write path runs from the dialog and is covered via the export_document_json seam.",
}

# src/ handler name -> ENTRY_POINT_REGISTRY key, for the cases where the registry key is not the
# handler's own function name. Read by scripts/check_entry_point_extraction.py so an aliased
# handler is not reported as unregistered.
ENTRY_POINT_SOURCE_ALIASES: dict[str, str] = {
    "onSyncNow": "syncDocument.onSyncNow",
    "_submitImport": "importSelectedSubmit",
}

# Deferred entry points (GTaskSheet-z6f8 / EPIC GTaskSheet-rz4k). Maps a registered entry point
# with NO current tagged scenario call-site to a one-line reason. check_coverage.py treats
# these as explicitly warn-only (not uncovered), so the T17 gap-diff stays green. Most entries
# here are *backlog* (a tracking bead converts them to a real tagged call-site); rz4k.5's
# entries are *permanent exemptions* with rationale (epic AC alternative (b)) -- pure
# test-harness plumbing exercised implicitly by every scenario, where a dedicated
# entry_point= tag would be redundant with the suite-wide failure a regression here would
# already cause. "Warn-only" == enumerated but not asserted at its own call-site.
ENTRY_POINT_DEFERRED: dict[str, str] = {
    # rz4k.3 — workspace/editor card mutations
    "importSelectedSubmit": "real Import card submit; CHECK_BOX SelectionInput not Playwright-drivable — covered via importSelectedForTest surrogate, EPIC GTaskSheet-pw5x — GTaskSheet-rz4k.3",
    # Docs add-on menu entry points (GTaskSheet-lmsd) — no Playwright test coverage yet; test harness
    # runs in Sheets context so Docs menu items are not reachable without a separate Docs browser session.
    "menuSyncActiveDoc": "Docs menu 'Action Sync > Sync' — drives syncDocument(docId) in Docs context; "
        "covered at the equivalent onSyncNow sidebar call-site. Docs menu harness deferred — GTaskSheet-lmsd.",
    "menuInsertTrackerActiveDoc": "Docs menu 'Action Sync > Insert Tracker' — drives insertTrackerTable(docId); "
        "covered at the equivalent onInsertTrackerTable sidebar call-site. Docs menu harness deferred — GTaskSheet-lmsd.",
    # rz4k.4 — menu entry points. menuSync / menuEnsureSheetStructure / menuRunArchive
    # are now covered at their own menu-wrapper call-sites (tests/test_menu_entry_points.py
    # via the menu_sync / menu_ensure_sheet_structure / menu_run_archive fixtures) and have
    # been removed from this map. The two below are PERMANENT EXEMPTIONS (epic AC alt (b)):
    "menuBootstrap": "menu wrapper over bootstrap() — itself a permanent exemption below. "
        "One-time script-property setup; driving it mid-suite would overwrite "
        "TEST_SHEET_ID and break every subsequent scenario. A dedicated tag "
        "would require save/restore plumbing redundant with the bootstrap-route exemption "
        "— GTaskSheet-rz4k.4.",
    "menuInitializeTriggers": "menu wrapper over initializeTriggers(); driving it mid-suite "
        "delete+recreates the live deployment's installable triggers — shared-deployment "
        "state outside the per-doc scenario sandbox. Trigger registration is exercised "
        "operationally by every `npm run deploy:test` — GTaskSheet-rz4k.4.",
    # rz4k.5 — test-support routes (PERMANENT EXEMPTIONS, resolved GTaskSheet-rz4k.5)
    "run_fixture": "every scn._post_fixture(...) call across the suite POSTs run_fixture "
        "(hundreds of call-sites per run); a regression here surfaces as an immediate "
        "FixtureError/non-JSON response failing essentially every scenario's setup or act -- "
        "a dedicated entry_point= tag would be redundant with that suite-wide signal.",
    "set_test_token": "invoked once per `npm run deploy:test`, outside the pytest run, to mint "
        "the TEST_TOKEN every testToken-gated call depends on; a regression here fails every "
        "such call with test-token-unauthorized/expired (fixture_invoke.FixtureTokenError) "
        "before any test body runs.",
    "bootstrap": "one-time script-properties setup (TEST_SHEET_ID/GAS_LOGGER_FOLDER_ID), "
        "run manually from the Apps Script editor after the first clasp push "
        "(clasp-bootstrap-pattern) -- not part of the per-run pytest harness loop.",
    "begin_journey_session": "every ScenarioSession.new_doc() call POSTs this (hundreds of "
        "call-sites per run); a regression here raises RuntimeError('begin_journey_session "
        "response missing docId') immediately for every test using new_doc.",
    "end_journey_session": "every ScenarioSession.close() call POSTs this; a regression here "
        "fails the engine.close() drain-invariant assertion for every test, surfacing "
        "immediately and suite-wide.",
    # gts-79dw.4.8 review follow-up (PR #5 Copilot review) — team_sync_document has call-site
    # coverage (tests/test_verify_access.py, tests/test_team_portal_hardening.py) but only on
    # the rejection/negative paths, asserted against the raw JSON dict directly -- none of those
    # calls go through scn.verify(..., entry_point=...), and the one positive-path test
    # (test_write_succeeds_at_edit_tier) is skipped pending a configured EDIT-tier identity and,
    # even unskipped, only resolves the caller's tier -- it does not itself call
    # team_sync_document or assert durable post-sync state. Tagging a negative-path assertion
    # with entry_point= here would misrepresent coverage of the success/durable-state path.
    "team_sync_document": "no scn.verify()-based durable-state assertion yet for the success "
        "path; existing coverage is raw-dict assertions on the rejection paths (R14/R15 tier "
        "gate, R3b cross-folder scope) plus a skipped positive test that never calls the route -- "
        "PR #5 review.",
    # Extensions-menu universal actions (Procedure-Exporter.js) are CardService UI card builders
    # with no headless/testToken call-site of their own -- test coverage instead goes through the
    # export_document_json testability seam (exportDocument_() directly, see
    # tests/test_document_export.py's header comment), which is a distinct call-site, not these
    # two menu handlers. No scn.verify() assertion exists at onDocumentExportMenu/
    # onDocumentExportAndPdfMenu's own call-site.
    "onDocumentExportMenu": "CardService universalAction with no headless call-site; covered "
        "indirectly via the export_document_json seam's exportDocument_() call, not at its own "
        "entry point — PR #5 review.",
    "onDocumentExportAndPdfMenu": "same gap as onDocumentExportMenu (exportPdf=true variant) — "
        "PR #5 review.",
    # gts-u6ew.11 (source-extraction sweep) — newly enumerated, none previously registered.
    # Deferred rather than covered: each is state-modifying and now visible to the gap-diff,
    # but none has a scn.verify(..., entry_point=...) tagged call-site today.
    "menuConfigFormat": "opens an interactive SpreadsheetApp.getUi().prompt for a reference doc id "
        "and returns on Cancel — no headless call-site exists; the underlying Config style rows are "
        "asserted through the config fixtures instead — gts-u6ew.11.",
    "menuForceRefreshActiveDoc": "Docs menu 'Force Refresh Style' — drives sync_document(force=true) "
        "in Docs context; same deferral as menuSyncActiveDoc/menuInsertTrackerActiveDoc (the harness "
        "runs in Sheets context, so Docs menu items are unreachable) — GTaskSheet-lmsd.",
    "nightlyAdminScanAllTeams": "nightly time-based admin sweep over every TeamData team; a scenario "
        "call-site would run a full multi-team scan against the shared TEST spreadsheet. Covered "
        "indirectly by the per-team admin_scan_* routes, not at this trigger's own call-site — "
        "gts-u6ew.11.",
    "_runNearImmediateSyncAll": "one-shot self-deleting trigger created by onActionSheetEdit; it "
        "deletes itself and calls syncAll(), both already registered. Time-based trigger firing is "
        "not drivable from a scenario — gts-u6ew.11.",
    "menuCleanupTestDocs": "tests/test_cleanup_test_docs.py drives this entry point through its own "
        "'menu_cleanup_test_docs' run_fixture wrapper and asserts durable row deletion, but with raw "
        "XLSX/dict assertions rather than scn.verify(..., entry_point=...) — same shape as the "
        "team_sync_document deferral above; tagging it is the work that clears this row — gts-u6ew.11.",
    "menuBeginTestSession": "PERMANENT EXEMPTION: manual TestControl!A1-driven twin of the "
        "begin_journey_session route every ScenarioSession.new_doc() already POSTs. Driving the menu "
        "wrapper would require a live Sheets UI session and would re-point TestControl!B1 mid-suite "
        "— gts-u6ew.11.",
    "menuEndTestSession": "PERMANENT EXEMPTION: manual TestControl!B1-driven twin of the "
        "end_journey_session route every ScenarioSession.close() already POSTs — gts-u6ew.11.",
    "menuSetupFixture": "PERMANENT EXEMPTION: manual twin of the run_fixture route, itself a "
        "permanent exemption above (hundreds of call-sites per run) — gts-u6ew.11.",
    "menuSyncDocument": "PERMANENT EXEMPTION: manual TestControl!A1-driven twin of syncDocument(docId), "
        "which is the registry's most heavily covered entry point — gts-u6ew.11.",
    "menuSetupAndSync": "PERMANENT EXEMPTION: manual twin of the run_fixture + sync_document pair, "
        "both already covered at their own call-sites — gts-u6ew.11.",
    "menuInsertTrackerTable": "PERMANENT EXEMPTION: manual TestControl!A1-driven twin of "
        "insertTrackerTable(docId), covered at the onInsertTrackerTable card call-site — gts-u6ew.11.",
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
    "AC_SELFTEST_FIXTURES",
    "ENTRY_POINT_REGISTRY",
    "ENTRY_POINT_DEFERRED",
    "ENTRY_POINT_SOURCE_EXEMPT",
    "ENTRY_POINT_SOURCE_ALIASES",
]
