## 2026-05-20 00:19:54

### Summary
Initialised the GActionSheet project from scratch: requirements review and gap analysis, requirements completion, documentation scaffolding, bd initialisation, and TDD/BDD test infrastructure.

### Details

**Requirements review and gap analysis**
- Reviewed requirements.md against GAS feasibility; identified 18 gaps (B1–B18)
- Confirmed achievable as container-bound GAS on the Sheet with caveats (6-min limit, installable trigger for onEdit, slow DocumentApp)

**Requirements completed (B1–B11, B17)**
- B1: Added §12 Sync Invocation — `Action Sync` sheet menu, `initializeTriggers` (idempotent), 30-min timed scan
- B2: Added §13 Document Discovery — `DOC_FOLDER_ID` script property, auto-defaults to spreadsheet parent folder, recursive folder scan, 7-day modified filter
- B3: §11 clarified — sheet→doc propagation happens in same sync execution (timed or menu)
- B4: Doc table columns aligned with sheet schema; same names, no Document column in doc
- B5: `Document` column is a single hyperlink cell (title as text, URL as hyperlink)
- B6: Heading styles scoped to `HEADING1`–`HEADING6`; author chooses level
- B7: Assignee token accepts bare email, display-name form, and Docs mention chips; token preserved as-is on rewrite
- B9: Missing tracked-actions section auto-created at end of doc with HEADING1; missing table inside section also auto-created
- B10: Floating-action rewrite replaces full paragraph text, preserving paragraph style
- B11: Added §16 Archive Behavior — `Status=Closed` + 30 days → moved to archive sheet; programmatic write guard; filter operations excluded from `Date Modified` updates
- B17: Sheet timestamp cells stored as native Date values; doc table and floating-action text use ISO 8601 strings
- Remaining open decision: whether to add a `Synced` column (B-NEW)

**Documentation scaffolding (Standard tier, bd in use)**
- Created folder structure: `docs/`, `knowledge-base/adr/`, `src/`, `doc-framework/` (copied from DevStandard)
- README.md, CLAUDE.md, PLAN-bd.md, docs/README.md
- docs/CONTEXT.md — fully populated: purpose, quality goals, stakeholders, constraints, 3 use cases, non-goals, glossary
- docs/DESIGN.md — runtime architecture diagram, 7-component building block table, data model ERD, crosscutting concepts, dependency rules
- docs/OPERATIONS.md — deployment model, config (DOC_FOLDER_ID), failure modes table, recovery procedures
- knowledge-base/adr/0001 — container-bound GAS on Sheet (Accepted)
- knowledge-base/adr/0002 — timestamp-based conflict resolution (Accepted)

**bd initialised**
- `bd init` run; embedded Dolt database created in `.beads/`
- AGENTS.md generated; Claude hooks registered; `.claude/settings.json` created

**TDD/BDD test infrastructure**
- DESIGN.md §Test Model added: framework declaration, fixture scope architecture (Session/Suite/Workflow/Function), all 5 AC workflow sequences as Given/When/Then, atomic test categories, anti-patterns
- `tests/helpers/download.py` — `download_xlsx` + `download_docx` via unauthenticated Google export URLs
- `tests/helpers/sheet_inspect.py` — openpyxl helpers: `find_row` (hyperlink-aware), `assert_date_cell`
- `tests/helpers/doc_inspect.py` — python-docx helpers: `floating_actions`, `tracked_actions_table`, `find_table_row`
- `tests/helpers/gas_log.py` — Drive-mapped NDJSON log polling (`wait_for_log`, `clear_logs`)
- `tests/conftest.py` — session-scoped pytest fixtures from `local.settings.json`
- `tests/test_acceptance.py` — all 5 ACs as workflow test classes; marked `xfail` pending GAS fixture functions
- `tests/playwright/playwright.config.js` — gas-editor-testing config (headless: false, 1 worker)
- `tests/playwright/editor_helpers.js` — `runFunction(page, funcName)` helper
- `tests/playwright/auth.setup.js` — one-time Google auth capture
- `src/GasLogger.js` — server-side NDJSON logger with Drive flush and 25-entry buffer
- `local.settings.example.json`, `pyproject.toml`, `.gitignore` additions

### Key Learnings
- WSL `/mnt/c/` filesystem invalidates the Edit tool's file-state cache after every write; workaround is to re-read before each Edit call (not add delays — it is a cache invalidation issue, not a timing issue)
- GAS `onEdit` simple trigger cannot call external services; sheet-update trigger must be installable — sheet→doc propagation is therefore eventually consistent, not real-time
- Export URLs (`/export?format=xlsx` and `/export?format=docx`) require the file to be shared "Anyone with link (viewer)" — no OAuth needed for test downloads
- gas-editor-testing pattern (Playwright drives the Apps Script IDE) is the right trigger mechanism for a bound script with no `doGet` endpoint


## 2026-05-20 12:45:00

### Summary
Full TDD code phase complete (13 GAS source files + 32 xfail tests). Clasp project created, code deployed, GAS functions bootstrapped. Playwright smoke test not yet passing — blocked on test invocation architecture decision.

### GAS Project Bootstrap — Key Learnings

**clasp project creation**
- `clasp create --type sheets --title "Name" --rootDir src` creates both a Google Sheet and a bound Apps Script project in a single command. Outputs Sheet ID and Script ID.
- clasp overwrites `appsscript.json` on create, removing any `oauthScopes` defined there. This is expected — GAS auto-detects required scopes from the code. Do not fight it.
- `.clasp.json` is created at the project root. Commit it (it's project config). Add `local.settings.json` to `.gitignore` (it holds real IDs/paths).

**Bootstrap function pattern (critical)**
- Script properties (`TEST_DOC_ID`, `TEST_SHEET_ID`, `GAS_LOGGER_FOLDER_ID`) cannot be set via any API without complex GCP setup. Add a `bootstrap()` function to a GAS file that calls `PropertiesService.getScriptProperties().setProperties({...})` with all needed values hard-coded.
- Run `bootstrap()` once from the Apps Script editor after first `clasp push`. Verify it worked by checking the Drive-synced log folder for a `.log` file.
- File location matters: tell the user which `.gs` file contains the function before asking them to run it — the editor only shows functions for the currently-open file.
- `bootstrap()`, `ensureSheetStructure()`, and `initializeTriggers()` must all be run once manually in this order before any tests can work.

**clasp OAuth token scopes**
- clasp's stored token at `~/.clasprc.json` (`tokens.default.access_token`) has `drive.file` scope — sufficient to create Google Docs and Sheets via the Drive REST API (file creation, not arbitrary Drive access).
- To create a test Google Doc programmatically: `POST https://www.googleapis.com/drive/v3/files` with `mimeType: application/vnd.google-apps.document` using the clasp access token.
- Docs API (`docs.googleapis.com`) requires a broader scope not in the clasp token — use Drive API instead.

**GasLogger / Drive for Desktop**
- GasLogger writes NDJSON `.log` files to a Drive folder identified by `GAS_LOGGER_FOLDER_ID` script property. The test harness polls these files locally.
- This polling only works if Drive for Desktop is running and the folder is synced locally. Get both the Drive folder URL (for the script property) and the local filesystem path (for `local.settings.json gasLogDir`) from the user upfront — they are different things.
- Local path on this machine: `/mnt/g/My Drive/GAS-Logger/GActionSheet`
- Test log files appear as `{timestamp}-{uuid}.log` NDJSON files. Verified working.

### Playwright Setup — Key Learnings

**Version pinning is mandatory**
- `npm install @playwright/test` pulls the latest version, which requires downloading new browser binaries. If another project already has Playwright working, check its version first (`package.json`) and pin to the same exact version.
- On this machine: AudioTrackCombiner uses `1.59.1` with `chromium-1217`. Installing `^1.60.0` tried to download `chromium-1223` plus 20+ missing system libs.
- Fix: pin to `"@playwright/test": "1.59.1"` (no caret) and run `npm install`.

**auth.setup.js — do NOT put in globalSetup**
- `auth.setup.js` is an interactive script that opens a browser and waits for `process.stdin`. If listed as `globalSetup` in `playwright.config.js`, it blocks every automated test run.
- Remove it from `globalSetup`. Run it manually once: `node tests/playwright/auth.setup.js`. Session saved to `.auth/user.json`.

**Editor URL format**
- Correct: `https://script.google.com/d/{scriptId}/edit`
- Wrong (used in config): `https://script.google.com/home/projects/{scriptId}/edit`
- `page.goto('/')` in Playwright navigates to the domain root (`script.google.com/`), NOT the full baseURL path. Must use the explicit full URL in `goto()`.

**Apps Script editor function picker — new editor is not automatable with standard locators**
- The old locator `getByRole('listbox', { name: 'Select function to run' })` does NOT work in the 2024+ Apps Script editor.
- The function picker is a plain `div.Q45Bi` with text "No functions" — no ARIA role, no stable label. Class names are obfuscated and will change.
- Files that only export via IIFE (e.g., `var Foo = (function(){...})()`) show "No functions" in the picker. Only top-level `function` declarations appear.
- Conclusion: **do not automate the Apps Script editor function picker**. It is not designed for automation.

### Test Invocation Architecture — Decision Pending

Three approaches evaluated for triggering GAS functions from pytest:

| Approach | Browser needed | Fragility | Setup effort |
|---|---|---|---|
| Playwright → editor function picker | Yes | High (no stable selectors) | High |
| Web app `doGet` endpoint | No | Low (plain HTTP) | Medium (one deploy step) |
| Sheet menu + Playwright | Yes | Medium (stable text selectors) | Medium |

**Recommendation on record:** Web app `doGet` is cleanest for automation. Sheet menu is viable if manual QA triggering from the sheet has value. Editor-picker approach is not viable.

**Decision not yet made** — context clearing before implementation. Resume with this choice.

### Continuation State (post-context-clear)

- All 14 GAS source files pushed: `clasp push` verified 14 files
- Script properties set: `bootstrap()` confirmed via log file (`bootstrap.complete` tag)
- Sheet structure created: `ensureSheetStructure()` confirmed (`sheet.structure.ensured` tag, 0 rows)
- Triggers installed: `initializeTriggers()` confirmed (`triggers.initialized`, onEditCount=1, timeBasedCount=1)
- Auth captured: `.auth/user.json` present and valid
- 32 xfail tests written, all collecting clean: `pytest tests/ → 32 xfailed`
- bd issue `GActionSheet-93d` open: "Deploy GAS source and verify integration tests"
- **Next action:** Choose web app vs sheet menu, implement test invocation, get first test passing


## 2026-05-20 13:40:58

### Summary
Ran and fixed Playwright smoke test (step 5 of GActionSheet-93d); fixed test_infrastructure.py to pass 3 of 4 tests (step 6); pushed updated MenuHandler.js via clasp.

### Changes
- `tests/playwright/editor_helpers.js:82` — updated menu item selector from `[id*="menucell"]` to `getByRole('menuitem', { name, exact: true })` (stale selector, Google Sheets now uses `goog-menuitem` with `role=menuitem`)
- `tests/helpers/download.py` — added `_authed_session()` that loads cookies from `.auth/user.json` (Playwright storage state) into a `requests.Session`; used for authenticated XLSX export
- `tests/playwright/open_sheet.js` — new Node.js helper that navigates to the sheet and exits 0 when `Action Sync` menu is visible (confirms `onOpen()` ran)
- `tests/test_infrastructure.py` — removed module-level `xfail` pytestmark; added per-test `xfail` on `test_initialize_triggers_is_idempotent` only; rewrote `test_menu_item_exists` to use Node.js UI check instead of log polling
- `src/MenuHandler.js` — removed `GasLogger.log/flush` calls from `onOpen()` (simple triggers cannot access DriveApp)

### Key Learnings (GAS-Practices)

**GAS: Simple triggers cannot use authorized services**
`onOpen()`, `onEdit()` (reserved names) run as simple triggers. They cannot call DriveApp, ScriptApp, GmailApp, or any service requiring OAuth scope. Attempting `DriveApp.getFolderById()` throws: *"Specified permissions are not sufficient."* Remove any logging/flush calls from simple trigger functions. Verify behavior via UI side-effects (menu appearance, sheet changes) — not log files.

**GAS: Testing onOpen — use Playwright UI check, not log polling**
Since `onOpen()` cannot write to Drive, the only reliable test signal is the UI: navigate to the sheet with a stored auth session, wait for the custom menu label to appear. Node.js Playwright (`open_sheet.js`) exits 0 on success; pytest asserts on exit code.

**Playwright: Google Sheets custom menu selector (2026)**
The `[id*="menucell"]` selector for GAS custom menu items is stale. Current Sheets DOM uses `class="goog-menuitem"` with `role="menuitem"`. Use `page.getByRole('menuitem', { name: itemName, exact: true })` for reliable clicks.

**Playwright: Authenticated `requests` download from Google Docs**
Playwright storage state (`.auth/user.json`) contains raw browser cookies. Extract them into a `requests.Session` to make authenticated Google Docs export requests without re-running OAuth. Works for `/spreadsheets/d/{id}/export?format=xlsx` and `/document/d/{id}/export?format=docx`.


## 2026-05-20 18:48:24

### Summary
Reviewed AC.md (recently updated) against docs/CONTEXT.md use-case ACs and identified gaps. Rewrote docs/CONTEXT.md §Use Cases to align authority model, conflict resolution, and AC detail level with AC.md intent.

### Changes
- **docs/CONTEXT.md — §Use Cases Invariants (new):** stated once for all UCs — table is master within document (floating seeds table only on initialization); Modified-date precedence (blank = dirty, set to sync-start time and pushed; newer timestamp wins); sync is eventually consistent.
- **docs/CONTEXT.md — UC-1..UC-4 ACs rewritten:** outcome + key-normalization level. Dropped exact-format assertions (`YYYY-MM-DD h:m`, partial-date expansion, verbose worked example). Kept: row existence after sync, ID assignment, blank-status → Open, blank-date → doc-modified.
- **docs/CONTEXT.md — UC-5 added:** bare `AI-<n>` floating paragraph (author reference to existing record) expands from the table on sync.
- **docs/CONTEXT.md — UC-6 added:** floating paragraph locally edited by author is reverted to match the tracked-actions table on next sync.
- **docs/CONTEXT.md — §Constraints:** new "Format and Normalization Constraints" subsection holds date format, partial-date normalization, person-tile assignee, and blank-field defaults.
- **docs/CONTEXT.md — §Core Capabilities:** added authority-rule bullet (table is authoritative; floating seeds only on initialization).

### Key Learnings
AC.md was a cleaner statement of the same system intent — specifically: (1) the asymmetric authority model (table master, floating slave except on init) was never made explicit in CONTEXT.md; (2) the bare-ID reference case (`AI-2` with no fields) and the floating-edit-revert scenario were entirely absent from the use cases.

## 2026-05-22 16:45:48

### Summary
Implemented j02 walking-skeleton Workspace Add-on (src/addon/): manifest, Code.js with buildHomepageCard + onPing + GasLogger copy, .clasp.json, push:addon npm script. Worked through extensive GCP/deployment troubleshooting to get the add-on showing in Google Docs Extensions menu. Blocked by managed Workspace domain restrictions on test deployments; pivoted to Option B (External OAuth + personal Gmail) for lifecycle verification next session. Created reusable Workspace Add-on setup guide at ~/.claude/docs/workspace-addon-setup.md.

### Details
- Created src/addon/ with appsscript.json (Workspace Add-on manifest, addOns.docs.homepageTrigger), Code.js, and .clasp.json
- Resolved clasp create blocking on parent .clasp.json by temporarily moving root .clasp.json
- Restored manifest after clasp create overwrote appsscript.json with bare default
- Enabled Workspace Add-ons API and Google Workspace Marketplace SDK in GCP project 640030365693
- Configured OAuth consent screen (Internal, northlakeuu.org)
- Discovered test deployments silently fail on managed Workspace domains — trigger never fires, nothing in Executions log
- Confirmed buildHomepageCard executes correctly when run directly from Apps Script editor
- Created versioned deployments (v1, v2, v3) after GCP project was linked to avoid "Project Key not associated" error
- Attempted Marketplace SDK publishing path; blocked by required store listing assets (screenshots, banner, 5 icon sizes, ToS/privacy URLs)
- Generated logo-32.png and logo-128.png from NUUC-ActionTrackLogo.png using ffmpeg
- Captured all learnings in reusable guide: ~/.claude/docs/workspace-addon-setup.md + knowledge-base/references/workspace-addon-setup.md
- Session ends with Option B prompt ready for next session

### Key Learnings
- Workspace Add-ons API must be enabled in GCP — silent failure if missing
- clasp create overwrites appsscript.json; always restore custom manifest immediately after
- oauthScopes required in manifest for versioned deployments (clasp deploy), not enforced for HEAD
- Create versioned deployments AFTER linking GCP project to avoid Project Key association errors
- Test deployments on managed Google Workspace domains do not show in Extensions menu regardless of configuration
- Option B (External OAuth + personal Gmail test user) is the reliable path for walking-skeleton lifecycle verification

## 2026-05-22 22:07:53

### Summary
Validated single-script dual-architecture POC end-to-end; adopted GAS-Practices deployment/versioning pattern; resolved all auth and URL whitelist issues blocking proxy write.

### Accomplished
- **Architectural pivot**: dropped two-project split; confirmed one container-bound GAS script can serve as both Workspace Add-on (sidebar card) and Web App proxy endpoint
- **POC verified end-to-end**: Add-on card → UrlFetchApp → doPost → sheet.appendRow succeeded; wrote `5/22/2026 21:56:15  sdonaldson@northlakeuu.org  (empty)` to ActionSheet
- Implemented shared-secret auth (`WEBAPP_SECRET` script property) for doPost — Bearer token auth does not work for Apps Script Web Apps
- `doGet` self-registers `WEBAPP_URL` with regex normalization of org-specific URL format (`/a/northlakeuu.org/macros/` → `/macros/`) so whitelist entry always matches
- Added all three URL format variants to `urlFetchWhitelist` in manifest (`/a/macros/northlakeuu.org/s/`, `/a/northlakeuu.org/macros/s/`, `/macros/s/`)
- Merged `addOns` block, `webapp` section, and all six oauthScopes into single `src/appsscript.json`
- Adopted GAS-Practices deployment pattern: `manage-deployments.js` discovers TEST-WEB-APP/PROD-WEB-APP anchor by description, redeploys in-place with `clasp deploy -i <id>` keeping URL stable
- `update-revision.js` stamps `src/Version.js` with BUILD_INFO (version + timestamp) before every deploy; version footer displays in add-on sidebar
- `commit-deploy-stamp.js` reads `.deploy-metadata.json` and commits `src/Version.js` with deployment metadata
- Replaced debug card notification in `relayPocToSheet` with `Logger.log()` per user feedback

### Key Learnings
- Workspace org "Anyone within org" access enforces SSO on UrlFetchApp requests regardless of auth header — must set Web App access to "Anyone" at org admin level
- `ScriptApp.getService().getUrl()` returns org-specific format (`/a/northlakeuu.org/macros/`) which does not match the standard whitelist entry — normalize with regex in doGet
- `clasp push --force` / `clasp push -f` needed only when clasp 3.x hash cache skips unchanged files; normal code changes push without force
- Logger.log() is the correct GAS debugging tool during development; GasLogger reserved for TDD/BDD phase when it can be checked programmatically
- Stable deployment URLs require `clasp deploy -i <deploymentId>` — only bumps version number, URL never changes

## 2026-05-23 06:00:13

### Summary
Completed three prereq issues: removed legacy AI-prefix modules (ii7), restructured to single clasp project with menu+stubs (urx), and added NamedRangeId as first sheet column (v4v). Added Playwright submenu support and a session fixture so ensureSheetStructure runs automatically before header tests — no more manual GAS editor steps for CI/CD.

### Issues Closed
- **GTaskSheet-ii7** — Deleted FloatingActionParser, DocumentDiscovery, DocumentNormalizer, SheetReconciler, SyncOrchestrator, MenuHandler, onEditTrigger from src/. Deleted test_floating_action_parser.py. Removed AI- prefix references from UC scenario expectations and doc_inspect helpers. Stubbed floating_actions() for future checkbox+person-chip parser.
- **GTaskSheet-urx** — Added MenuHandler.js (onOpen, Setup submenu, test menu items) and SyncManager.js (syncDocument/syncAll/onActionSheetEdit stubs). Custom menu registers on sheet open.
- **GTaskSheet-v4v** — Added NamedRangeId as first column of SHEET_HEADERS. Updated ArchiveManager column indices (STATUS 5→6, DATE_MODIFIED 8→9). Updated TestFixtures._tfSheetRow and test_infrastructure.py headers.

### Key Learnings
- Google Sheets renders submenu trigger items with a ► arrow in the accessible name — `getByRole('menuitem', { name: 'Setup', exact: true })` fails; use `.locator('[role="menuitem"]').filter({ hasText: parentMenu }).first()` instead.
- Drive log sync latency can exceed 60s; session fixtures that depend on log-wait should catch TimeoutError and let the test assertion carry the error rather than failing setup.
- Playwright scripts with `headless: false` hardcoded will open a browser window even from pytest — tracked as GTaskSheet-4qd (P3).
- Utility GAS functions (ensureSheetStructure, initializeTriggers) should be in the custom menu from the start so CI/CD can invoke them without the Apps Script editor.


## 2026-05-23 09:12:17

### Summary
UC-A full TDD cycle (red → green) plus ADR for Workspace Add-on architecture.

### Completed
- **mol-75k (red phase):** `tests/test_uc_a.py` — 4 E2E tests covering AC1 (action appears in ActionSheet), AC2 (no duplicate on second sync), AC3 (idempotent). New Playwright helper `addon_helpers.js` for driving the Doc sidebar; Python wrapper `addon_invoke.py`. `uc_a_clear` fixture in `TestFixtures.js` clears ActionSheet + named ranges while preserving chip-led checklist items. Old AI-prefix UC-A scenarios removed from `test_uc_scenarios.py`.
- **nmo (ADR):** `knowledge-base/adr/0005-workspace-addon-with-automation-sidecar.md` — captures two-project architecture, identity via namedRangeId, proxy-write pattern, and why alternatives were rejected. ADR-0001 status updated to Superseded.
- **mol-uv8 (green phase):** `SyncManager.js` — `_scanChipLedActions` (PERSON chip as first child), `_buildAnchoredIndexMap`, `_anchorNewActions` (DocumentApp.addNamedRange), `_upsertActionRows` (doPost proxy). `Addon.js` — "Sync now" button and `onSyncNow` handler. `WebApp.js` — `_handleUpsertActionRows` with idempotent namedRangeId key and WriteGuard-wrapped appendRow. `appsscript.json` — add-on name changed to "Action Sync". `doc_inspect.py` — `floating_actions()` parser (mailto hyperlink → email, regex fallback).

### Key Learnings
- `DocumentApp.Document.addNamedRange()` creates the same named range as the REST API `createNamedRange`; `getId()` returns the stable `namedRangeId` — REST API batchUpdate not needed for MVP anchoring.
- Workspace Add-on sidebar in Google Docs is accessible via Extensions > [add-on name]; manifest `name` field controls the Extensions menu label.
- Google Docs exports PERSON chips to .docx as hyperlinks (not plain text); `floating_actions()` parser needs both mailto: and email= query-param strategies; exact format requires real-doc verification.
- `isChecked()` returns null for all checklist items — chip presence as first paragraph child is the only reliable detection marker.

### Blocked / Next
- E2E test run for `tests/test_uc_a.py` requires: `clasp push`, add-on sidebar visible in test doc (chip-led checklist items pre-configured), `.auth/user.json`. Run: `uv run pytest tests/test_uc_a.py -x -v`
- `floating_actions()` parser needs verification against an actual exported .docx from the test doc once sync is running.

## 2026-05-23 21:03:44

### Summary
UC-A green phase complete — all 4 acceptance tests passing end-to-end. Independent code review done. Key bugs found and fixed.

### Fixes
- `TestFixtures.js`: replaced `body.clear()` with Docs REST API `deleteContentRange` to avoid GAS "can't remove last paragraph" error; handles both single-paragraph (clear content) and multi-paragraph (delete preceding paragraphs) cases
- `TestFixtures.js`: added outer `catch` to `setupTestFixtures` so errors always produce a log entry instead of timing out silently
- `SyncManager.js` `_scanChipLedActions`: added `LIST_ITEM` handling alongside `PARAGRAPH` — `createParagraphBullets` REST API converts paragraphs to GAS `LIST_ITEM` type
- `SyncManager.js` `_buildAnchoredIndexMap`: added `LIST_ITEM` handling so named ranges on list items are found on second sync (was creating duplicates)
- `SyncManager.js` `_upsertActionRows`: added `Authorization: Bearer` OAuth header — `UrlFetchApp` calling a Web App with `access: ANYONE` needs credentials, otherwise Google redirects to login (HTTP 401)
- `WebApp.js` `_escapeQuotes`: changed `\"` to `""` — Google Sheets formulas use `""` to escape double-quotes, not backslash
- `doc_inspect.py` `floating_actions()`: changed `find(qn('w:numPr'))` to `find('.//' + qn('w:numPr'))` — `w:numPr` is nested inside `w:pPr`, not a direct child of `w:p`
- `addon_helpers.js`: changed panel icon locator from `[aria-label="GActionSheet"]` to `[aria-label="Action Sync"]` (add-on name from manifest)

### Architectural Findings
- Workspace Add-on card iframes are sandboxed — not accessible via Playwright CDP. Replaced `sync_via_sidebar` with GAS menu `syncDocument` invocation (same underlying function, much more reliable)
- `insertPerson` REST API chip creates GAS `LIST_ITEM` when combined with `createParagraphBullets` — scanner must handle both element types
- Drive for Desktop sync latency requires 120–180s poll window for log file to appear locally

### Test Changes
- `test_uc_a.py`: replaced `sync_via_sidebar` with GAS menu path throughout; combined fixture + first sync into single browser session (`setup_and_sync`); dropped supplemental docx test (not an acceptance criterion); reduced from ~10 to ~6 browser sessions across 3 tests
- Independent review (mol-oib) complete: 5 blocking, 10 non-blocking findings; `_escapeQuotes` fix applied this session

### Issues Closed
- `GTaskSheet-mol-88d` — Verify UC-A passes full test suite
- `GTaskSheet-mol-oib` — Independent agent review: UC-A

## 2026-05-24 02:05:06

### Summary
Extended UC-A floating action detection to email-at-start format; refactored tests to multi-example ATDD paradigm; updated beads to reflect expanded permutation strategy.

### Changes
- **`src/SyncManager.js`**: Added email-at-start detection in `_scanFloatingActions` (renamed from `_scanChipLedActions`). Added `_nameFromEmail(email)` helper — splits username on `[._-]`, title-cases each word. Scanner now detects both PERSON chip and `word@word.tld` at start of text element.
- **`src/TestFixtures.js`**: Added `_tfAppendTextListItem(token, docId, text)` — REST API only (no DocumentApp) to avoid GAS document caching between fixture and sync calls. `uc_a_clear` now inserts chip item + email item via REST API `batchUpdate`.
- **`tests/test_uc_a.py`**: Replaced 3 single-example tests with 2 multi-example tests (AC1 + AC2). Added `_clear_logs_stable()` to handle Drive log sync race condition (GAS flush may still be syncing when next test's `clear_logs` runs — re-deletes until empty). Fixture inserts chip item ("Review the budget report") + email item ("jane.smith@example.com Approve the budget proposal (In Progress)").
- **`src/SheetSetup.js`**: Added column-position comment above `SHEET_HEADERS`.
- **Docs** (`CONTEXT.md`, `DESIGN.md`, `OPERATIONS.md`): Updated to describe both detection forms, name derivation, and UC-A test structure.

### ATDD Strategy (Improved)
Current AC1 covers 2 permutations (chip+default-status, email+explicit-status). Four permutations remain uncovered:
1. Chip item WITH explicit status token (e.g., `(Done)`) — verifies status parsing for chip items
2. Email item with NO status token — verifies default `Open` for email-led items
3. Email with underscore username (`bob_jones@example.com`) — verifies name derivation handles `_` punctuation
4. Negative case: plain text list item (no chip, no email) — verifies no false-positive ActionSheet row

Strategy: all items in a single doc, single Sync. Expect 3 rows (chip, email, email-underscore) and zero row for plain text. One browser session, maximum coverage per execution run.

Tracked as **GTaskSheet-ly7** (blocks mol-p30 sign-off gate).

**UC-B test design** (GTaskSheet-5vk, notes updated): same multi-example paradigm — construct doc with multiple forms, make sheet edits, one Sync, assert all propagated. Include regression checks for append-instead-of-replace and duplicate tracker table insertion.

### Issues
- **GTaskSheet-ly7** (new, open): Expand UC-A fixture + tests to full permutation coverage
- **GTaskSheet-mol-p30**: Blocked on ly7; sign-off criteria documented in notes
- **GTaskSheet-5vk**: Notes updated with ATDD paradigm for UC-B

## 2026-05-24 07:23:23

### Summary
Session-start check; reviewed UC-B readiness and test strategy; designed canonical test doc architecture for all UC tests; created hardening issue for parentheses corner case.

### Details
- Confirmed UC-B mol workflow state: use-cases, AC, and gate all closed; `mol-745` (Develop tests) is next
- Resolved staged LL incident review: Branch A already applied (OPERATIONS.md + bd memory); Branch B still open
- Reviewed UC-A test structure as the model for UC-B: batching multiple format variants into one Sync execution
- Established that UC-B test variants are defined by **floating action format** (email-only, chip+status, chip+no-status, non-default status, etc.), not by edit direction
- Designed canonical test doc: 7 floating action variants shared across all UCs; GAS fixture resets to or builds from this state per UC
- Updated `GTaskSheet-mol-745` with full test architecture: 3 scenarios (doc-wins, sheet-wins, conflict-resolution), batching principle documented
- Created `GTaskSheet-28q` (P3, hardening): parentheses-in-action-text corner case for status token parser
- Persisted canonical test doc principle as bd memory (`canonical-test-doc-shared-fixture-across-all-ucs`)

### Key Learnings
- Execution runs are expensive (browser, GAS, Drive sync); format variants are cheap — invest in variant coverage in the document, not in separate test runs
- UC-C and UC-D should build from the same canonical doc state rather than defining their own fixtures independently

## 2026-05-24 07:41:07

### Summary
Implemented UC-B test suite (GTaskSheet-mol-745): GAS fixture scenarios for all three UC-B cases plus the Python xfail test file.

### Changes
- `src/TestFixtures.js`: Added `_tfAppendPersonChipListItem` REST API helper (appends a chip-led bullet to end of doc without clearing). Added `uc_b_doc_wins`, `uc_b_sheet_wins`, and `uc_b_conflict` fixture scenarios — each builds the canonical 7-item state (3 chip + 3 email + 1 plain-text negative), runs an intermediate `syncDocument()` call to anchor named ranges, then applies scenario-specific mutations. Extended `_tfResetDocBody` exclusion list to cover all three UC-B scenarios.
- `tests/test_uc_b.py`: New file with three `@pytest.mark.xfail(strict=True)` tests covering AC1 (doc wins), AC2 (sheet wins), and AC3+conflict resolution. All tests collect cleanly; all will remain xfail until `GTaskSheet-mol-dyu` (UC-B implementation) is complete.

### Key Learnings
- UC-B fixture flow uses two GAS invocations per test: `setup_fixture('uc_b_XXX')` triggers the full canonical setup + intermediate sync + mutations; `sync_document(test_doc_id)` triggers the final convergence sync. Separating these avoids ambiguous `sync.complete` log entries from the intermediate sync.
- `WriteGuard.wrap` is synchronous, so the classic IIFE loop-closure fix is unnecessary — capture the row number in a local variable instead.
- The `_handleUpsertActionRows` Web App handler is INSERT-only (skips rows where `namedRangeId` already exists), confirming UC-B assertions will correctly xfail until bidirectional sync is implemented.

## 2026-05-24 10:15:00

### Summary
Captured and analyzed deployment process deviation (direct `clasp push` vs `npm run deploy:test`). Implemented corrective controls in CLAUDE.md and OPERATIONS.md. Verified UC-B green phase — all 6 tests pass.

### Work Completed
1. **Lessons Learned capture** — documented incident where Claude bypassed npm deploy toolchain; staged file with 5-why analysis (two root causes: undocumented npm script path + missing LL trigger for process deviations)
2. **Option A1** — Added GAS Deployment section to CLAUDE.md with table: `npm run deploy:test` (test), `npm run deploy:prod` (prod), `npm run push` (push-only, deprecated). Explained stale deployment symptom.
3. **Option A2** — Updated OPERATIONS.md §Pushing → §Deploying; led with npm deploy scripts; updated First-time Setup and POC Checklist to use `npm run deploy:test`.
4. **Test suite verification** — Ran full UC-B + UC-A test suite: 6/6 pass (292s wall time). Closed GTaskSheet-mol-b7d.

### Key Learnings
- Structural gaps (undocumented mandatory paths) accumulate into repeated process deviations. Documenting the npm deploy toolchain as the authoritative path in CLAUDE.md prevents the next agent from using direct `clasp` commands.
- Lessons-learned auto-trigger list should include "task required rework because wrong toolchain entry point was used" to catch process deviations earlier in the session.

### Status
- GTaskSheet-mol-dyu: closed (UC-B bidirectional sync implementation)
- GTaskSheet-mol-b7d: closed (verification gate)
- LL incident: staged (resolution deferred per user)
- Ready: GTaskSheet-mol-4vr (independent review) and 14 other open issues


## 2026-05-24 22:14:53

### Summary
Completed GTaskSheet-5vk (UC-B: Sheet→Doc sync). All 3 UC-B acceptance tests now pass; UC-A regressions clean.

### Changes
- `src/SyncManager.js`: added `_syncSheetRowToDoc` (real-time `onActionSheetEdit` path) + call from `onActionSheetEdit`; fixed bug where Document column read via `getValues()` returned HYPERLINK display text instead of URL — changed to `sheet.getRange(row, 7).getFormula()`
- `tests/test_uc_b.py`: updated module docstring to reflect active (non-xfail) state

### Key Learnings
`getValues()` returns the computed display value for formula cells (e.g. `=HYPERLINK("url","title")` → `"title"`); use `getFormula()` / `getFormulas()` when you need the raw formula string containing embedded URLs.

### Tests
- `test_uc_b_doc_wins` PASSED
- `test_uc_b_sheet_wins` PASSED
- `test_uc_b_conflict_resolution` PASSED
- UC-A: 3/3 PASSED (no regressions)

### Commit
`7666507` feat(uc-b): complete Sheet→Doc sync — _syncSheetRowToDoc + activate UC-B tests
## 2026-05-25 14:50:53

### Summary
Fixed named range anchor shift bug in UC-B sync; all 3 UC-B tests now pass. Fixed Python test helper to correctly parse chip-led floating actions from docx. Defaulted Playwright to headless.

### Changes
- **`src/SyncManager.js`**: Moved `_normalizeMissingFloatingActionStatuses` to run before `_buildAnchoredIndexMap` and `_anchorNewActions`. Root cause: GAS shifts a named range anchor to the next paragraph when `setText()` is called on a TEXT child after the NR is created for its parent LIST_ITEM. Normalizing text before NR creation eliminates the phantom 7th sheet row in UC-B sheet_wins and conflict_resolution tests. Removed debug logging from `_buildAnchoredIndexMap`.
- **`tests/helpers/doc_inspect.py`**: Rewrote `floating_actions()` to exclude person-chip hyperlink display text from `action_text`. In docx export, a PERSON chip becomes a `<w:hyperlink>` whose display text is the person's name — that must not be included in the action string or `_verify_consistency` key matching fails.
- **`src/TestFixtures.js`**: Fixed Var 3 mutation in `uc_b_doc_wins` to strip any existing status token before appending `(In Progress)`, preventing double token `(Open) (In Progress)` when the intermediate sync had already normalized the item.
- **`tests/playwright/invoke_gas.js`**: Changed browser launch to `headless: true` by default; pass `--headed` flag to run visible.

### Key Learnings
- GAS named range anchor shift: calling `textEl.setText(...)` on a TEXT element whose parent LIST_ITEM already has a named range will shift that NR to the next paragraph in the document. Fix: stabilize all text before creating any named ranges.
- Google Docs PERSON chip exports to docx as `<w:hyperlink>` with email in the URL; the display text (person's name) is inside the hyperlink element and is included in `para.text` — must be excluded when extracting action text.

### Issues
- GTaskSheet-1ar: closed (NR shift fix delivered)
- GTaskSheet-x2s: filed — UC-A permutations test downloads 0 rows from xlsx despite sync logging `upserted:3`; likely Google Sheets export caching lag

