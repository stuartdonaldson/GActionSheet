# Project Testing Guide — GActionSheet

Project-specific realization of the universal ATDD principles. Declares only
project facts; every "why" lives in the referenced documents. See
`docs/atdd/ID-map.md` for the legacy → principle-ID crosswalk.

## 0. References (do not restate)

| Document | Owns |
|----------|------|
| `DevStandard/knowledge-base/methodology/testing/bdd/sdlc-testing-principles.md` | Universal testing principles `T1`–`T24`. |
| `DevStandard/knowledge-base/methodology/testing/bdd/sdlc-implementation-principles.md` | Universal implementation/lifecycle principles `I1`–`I11`. |
| `.claude/skills/implementation-gate/SKILL.md` | The operational pre-implementation gate (project-local `v2.1` — see ID-map.md §Open follow-ups for the divergence note). |

## 1. Project identity

- **Project:** GActionSheet
- **Platform / language stack:** Google Apps Script (GAS) backend (`src/*.js`, V8 runtime) driving a Google Sheet (the ActionSheet) and Google Docs (floating actions + tracker table); a Workspace add-on (sidebar/homepage card) and an Editor add-on (link-preview/create-action card) front it. Python (`pytest`) + Playwright drives the test harness against a deployed `/exec` Web App.
- **Test runner / harness:** `pytest`; Playwright (Chromium) for live UI surfaces; the project's `scn/` package (this doc's harness — see `docs/atdd/harness-design.md`) wraps both behind the Act/Expect/Checkpoint scenario API.
- **Platform execution ceiling (if any):** GAS enforces a 6-minute execution ceiling per `doPost`/trigger invocation (T6/T21 driver: batch input variants into one fixture call rather than many round trips; split into a new scenario only when the operation model materially changes, e.g. HTTP phase vs. Playwright phase).

## 2. Stack-specific test conventions

- **Focused-AC test naming convention:** `test_<short-feature-slug>` per file (e.g. `test_sync_all.py`, `test_floating_action_scanner.py`); within a file, multi-case functions are `test_<nn>_<case>` (sequential) or one function per AC variant. AC identity is carried by the triage tag, not the function name (T4).
- **Scenario/journey naming convention:** `test_journey*.py` for the canonical multi-act journey (`test_journey.py` = full Acts 0–5 + final reconcile; `test_journey_acts_1_3.py` = a narrower slice). Theme is stated in the module docstring, not the filename (T2).
- **AC-traceability mechanism:** the `[<scenario> <ac-label>]` triage tag passed to `verify()`/`verify_all_expectations()`/`expect_absent()` calls (T4, T10); drained results are recorded as `AC_REGISTRY` keys in `scn/contract.py` (32 entries as of 2026-06-11) and emitted as JUnit `ac.<tag>.<surface>` properties.
- **Triage-tag format in assertion messages:** `[<uc/scenario> <ac-label>]`, e.g. `[journey sync-create]`, `[b7 write-status]`, `[sidebar mutation-changed]` — carries use-case/scenario + AC; surface and expected/observed values are carried by the `Expectation` record itself, not encoded in the string (T10).
- **BDD convention (if used):** not Given/When/Then prose — the project's own Act/Expect/Checkpoint vocabulary (§16 of the archived `atdd-lifecycle.md`, `T15`) is the realized form of that pattern; Act = When, Expect = Then (declared), Checkpoint = Then (evaluated).

## 2a. Traceability report

- **Report format and emission point:** JUnit XML via pytest's native `--junitxml` flag; `ScenarioSession.checkpoint()` (via `scn/engine.py drain()`) appends one `<property>` per drained `(tag, surface, PASS|WARN)` result through `request.node.user_properties`.
- **Metadata → report-field mapping:** JUnit `testcase name` ← the pytest test function; `classname` ← the test module; `<property name="ac.<tag>.<surface>">` ← one per drained expectation, carrying the T4/T10 triage tag and the surface it was evaluated on. Entry-point coverage uses a parallel `ep.<entry-point-key>` property namespace.
- **Authoritative coverage registry:** `scn/contract.AC_REGISTRY` (AC coverage) and `scn/contract.ENTRY_POINT_REGISTRY` + `ENTRY_POINT_DEFERRED` (entry-point coverage, T17) — not a separate doc; see §7 below.
- **Gap-diff step:** `scripts/check_coverage.py`, run manually or in CI, diffs the registries against the emitted `ac.*`/`ep.*` JUnit properties from a `test-results/junit/pytest.xml` run; exits 1 on an uncovered, non-deferred entry. See `docs/OPERATIONS.md §AC Coverage Check`.

## 3. Observation surfaces

Realizes `T5`, `T11`. Four surfaces (§16.5 of the archived lifecycle doc):

| Surface | How read | Cost | Observable at integrity checkpoint? |
|---------|----------|------|-------------------------------------|
| `DOC` | `.docx` download/parse (`scn/surfaces.DocReader`) — floating-action paragraphs `AI-N: {chip} {text} ({status})` | cheap | yes |
| `SHEET` | `.xlsx` download/parse, scoped to `docId` (`scn/surfaces.SheetReader`) | cheap | yes |
| `TRACKER` | parse the tracker table inside the same `.docx` (`scn/surfaces.TrackerReader`) | cheap | yes |
| `UI` | live Playwright DOM (sidebar card, preview card) via `scn/ui.UiDriver` | live; bounded poll (`within=`) | no — drained separately by targeted `checkpoint(STEP, on=Surface.UI)` calls during the Playwright phase; `INTEGRITY` observes only `{DOC, SHEET, TRACKER}` |

## 4. Fixture isolation

- **Per-run fixture creation:** `ScenarioSession.new_doc(settings, request=request)` creates a fresh, empty Google Doc via the `begin_journey_session` test-support route (GAS-side `DocumentApp.create(name)`); `session.close()` trashes it via `end_journey_session` at teardown (T9).
- **Run identity / clone naming format:** `GActionSheet-Test-journey-{YYYYMMDD}-{4-char-hex}` (human-readable, scenario-identifying, collision-resistant), placed in the same Drive folder as the test sheet.
- **Shared-store accumulation:** the ActionSheet (Google Sheet) is a single shared store accumulating rows across every run/session — every read and invariant is scoped to the run's own `docId`/`globalId` prefix (T19); a whole-sheet count or uniqueness check would read polluted cross-session state.

## 5. Contract schema

- **Authoritative machine-readable contract source:** `src/ContractSchema.js`, exported as `ContractSchema.json` (repo root) and loaded by `scn/contract.py` (I6).
- **Authoritative human-readable semantics source:** `docs/DESIGN.md §ATDD Journey Pre-Code Contract` (boundary names, field meanings, invariants, ownership rules).
- **How tests consume the contract:** `scn/contract.py` loads `ContractSchema.json` once at import and exposes typed constants (`ACTION_ITEM_FIELDS`, `SHEET_ACTION_FIELDS`, `SHEET_HEADERS`, `COLUMNS_BY_FIELD`, `ROUTE_NAMES`, `TEST_ROUTE_NAMES`, `MESSAGES`, `AC_REGISTRY`, `ENTRY_POINT_REGISTRY`); every other `scn/` module imports from there rather than redeclaring fields, so a contract/harness drift fails loudly at import or at the first mismatched field access (I6).

Contract families (full field/route lists live in `ContractSchema.json`/`scn/contract.py` — not duplicated here):

| Family | Entry-point signature | Completion signal | Output schema |
|--------|-----------------------|-------------------|----------------|
| `ActionItem` | doc-seeded via `append_paragraph(ai.as_text())` | paragraph appended to the live doc | `ACTION_ITEM_FIELDS` (`scn/contract.py`) |
| `SheetAction` | written via `upsert_action_rows`/`sync_action_rows`/`edit_action_row` doPost routes | row present/updated in the ActionSheet `Actions` tab | `SHEET_ACTION_FIELDS` + `SHEET_HEADERS`/`COLUMNS_BY_FIELD` (`scn/contract.py`) |
| Web App message (production routes) | one of `ROUTE_NAMES` (`set_test_token`, `upsert_action_rows`, `sync_action_rows`, `verify_action_rows`, `mark_doc_not_found`, `delete_action_row`, `patch_action_status`, `list_importable_actions`, `forward_action_rows`, `run_fixture`) | route-specific `doPost` JSON response | `MESSAGES[<route>]` (`scn/contract.py`) |
| Web App message (test-support routes) | one of `TEST_ROUTE_NAMES` (`edit_action_row`, `find_sheet_actions`, `verify_chip_integrity`, `import_selected_for_test`, `forward_action_rows_test`) — testToken-gated | route-specific JSON response | `MESSAGES[<route>]` (`scn/contract.py`) |
| Document read | `scn/surfaces.DocReader`/`TrackerReader` parse of downloaded `.docx` | parser returns `ai`-shaped records | `MODEL_NAMES` (`scn/contract.py`) |

## 6. Journeys

Realizes `T1`, `T15`, `T21`, `T22`. The canonical journey and its narrower/parallel slices:

| Journey | Theme / failure domain | Risk tier | Status |
|---------|------------------------|-----------|--------|
| `test_journey` (§16.10) | Full Acts 0–5: pre-flight version check, doc seed, sync, tracker insert, sheet-edit conflict resolution, UI create/status-change, final reconcile across Sync Scenarios A/B/C | P0 | built |
| `test_journey_acts_1_3` | Narrower slice of Acts 1–3 (HTTP-phase doc seed → sync → sheet-edit), no Playwright | P1 | built |
| `test_sync_all` (`syncAll` sweep, Scenario D) | Time-based sweep entry point as its own call-site; `DocData` integrity-pass reconciliation (counts, `doc_name`); archive eviction | P0 (reconciliation gap class, T22) | built |
| `test_b7_write_routes` | Direct write-route coverage (`upsert_action_rows`, `edit_action_row`) including the no-op/Dirty-stamp boundary | P1 | built |
| `test_import` | `forward_action_rows`/duplicate-forward guard (UC-E AC4), import-list/select flows | P0 (reconciliation — duplicate-forward guards against actual data duplication, T22) | built |
| `test_floating_action_scanner` | Scanner detection across paragraph/table-cell/list placements; tracker-table exclusion | P1 | built (AC-7/AC-8 caret-in-table-cell split to `GTaskSheet-4hqn`) |
| `test_menu_entry_points` | Sheets/Docs menu wrapper entry points (`menuSync*`, `menuInsertTracker*`) as their own call-sites | P2 (entry-point-coverage technicality, T17) | built |
| `test_sidebar`, `test_team_scope` | Sidebar header/team-view rendering, team-scoped read security gate (`assertTeamAccess`) | P1 | built |
| `test_link_preview`, `test_chip_preview` | Editor add-on link-preview card status-change path (Scenario A, async chip-tap) | P1 | built |
| `test_archive` | Archive sweep eviction thresholds | P2 | built (known gap: `[nv6g]` assumed a 24h Doc-Not-Found threshold that doesn't match the shipped flat 30-day threshold — `GTaskSheet-0f0s`) |

Per-journey invariants (T18) are asserted at `INTEGRITY` via `scn.verify_consistency(scope=DOC)` — the single SERVER-class consistency check (§16.7 of the archived lifecycle doc):

- **`test_journey` invariants:** every queued `ai` present and internally consistent on `{DOC, SHEET, TRACKER}`; every doc `ai` present in the sheet and vice versa, scoped to the journey's own `docId`; doc occurrences of one `action_id` are textually identical; sheet `globalId`/Document-column linkage present.
- **`test_sync_all` invariants:** `DocData` row counts and `doc_name` reconcile against the live doc set after a sweep; skipped/not-found docs are correctly excluded, not silently miscounted.
- **`test_import` invariants:** a duplicate entry in an explicit `forwards[]` payload does not produce a duplicate forwarded row (UC-E AC4) — a data-integrity/no-duplication invariant, not a cosmetic one.

## 7. Entry-point coverage matrix

Realizes `T17`. The authoritative, machine-readable list of all 32 state-modifying entry points (menu items, time-based triggers, sidebar/add-on card actions, HTTP routes, plus test-support routes) lives in `scn/contract.ENTRY_POINT_REGISTRY` and is **not duplicated here** (I6 — a second hand-maintained copy would drift). Summary by call-site class as of 2026-06-18 (`scripts/check_coverage.py -v` against the live journey run):

| Call-site class | Examples | Covered | Deferred (warn-only, tracked) |
|---|---|---|---|
| Core | `syncDocument`, `assertTeamAccess` | yes | — |
| Workspace add-on card | `onSyncNow`, `onSetActionStatus`, `onDeleteAction`, `onInsertTrackerTable`, `importSelectedSubmit` | partial | `importSelectedSubmit` (CHECK_BOX SelectionInput not Playwright-drivable; `importSelectedForTest` is the interim surrogate route) |
| Editor add-on card | `_submitCreateAction`, `_setStatusFromPreview` | yes | — |
| Installable triggers | `syncAll`, `onActionSheetEdit`, `_processPendingSheetUpdates` | yes | — |
| Sheets menu items | `menuSync`, `menuEnsureSheetStructure`, `menuInitializeTriggers`, `menuBootstrap`, `menuRunArchive` | partial | several Setup-submenu items, tracked under EPIC `GTaskSheet-rz4k.4` |
| HTTP routes (production) | `patch_action_status`, `edit_action_row`, `upsert_action_rows`, `sync_action_rows`, `mark_doc_not_found`, `delete_action_row`, `forward_action_rows`, `importList`, `menuSyncActiveDoc`, `menuInsertTrackerActiveDoc` | yes | — |
| Test-support routes | `run_fixture`, `set_test_token`, `bootstrap`, `begin_journey_session`, `end_journey_session`, `setup_team_scope_fixture`, `importSelectedForTest` | n/a (harness-only) | — |

10 of 32 entries have a real tagged scenario call-site; the remaining 22 are explicitly enumerated as **deferred** (not silently uncovered) in `scn/contract.ENTRY_POINT_DEFERRED`, each with a tracking bead, so `scripts/check_coverage.py`'s `ep.*` gap-diff is green by design rather than by omission. Converting deferred entries to real call-sites is tracked under EPIC `GTaskSheet-rz4k` (children `.1` triggers, `.2` routes, `.3` cards, `.4` menu, `.5` test-support).

## 8. AC-validation fidelity log

Realizes `T23`, `I11`. No feature in this project has used the Slice fidelity tier as of 2026-06-18 — all shipped ACs went through Spec review (the default) directly into the twin-ticket Hardened phase. If a future feature invokes Slice (ADR-0013), record it here with its justification and open-seams register at that time; this section is intentionally empty until then.

| Feature / AC | Fidelity (spec/slice/hardened) | Justification (required if slice) | Open seams to preserve |
|--------------|-------------------------------|-----------------------------------|------------------------|
| _(none yet — see note above)_ | | | |

---
_Filled 2026-06-18 (GTaskSheet-ruoa) from `docs/atdd/archive/atdd-lifecycle.md` §15–§16 and the `scn/` module map in `docs/atdd/ID-map.md`._
