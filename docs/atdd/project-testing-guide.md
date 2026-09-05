# Project Testing Guide — GActionSheet

Project-specific realization of the universal ATDD principles. Declares only
project facts; every "why" lives in the referenced documents. See
`docs/atdd/ID-map.md` for the legacy → principle-ID crosswalk.

## 0. References (do not restate)

| Document | Owns |
|----------|------|
| `$DEVSTANDARD/test-framework/sdlc-testing-principles.md` | Universal testing principles `T1`–`T25`. |
| `$DEVSTANDARD/test-framework/sdlc-implementation-principles.md` | Universal implementation/lifecycle principles `I1`–`I12`. |
| `$DEVSTANDARD/test-framework/harness-standards.md` | Normative harness conventions `H1`–`H13` (tier gating and run ordering, duration budget and waivers, boundary-fault classification, naming, entry-point registry, regression entry point). **This project's values, conformance states and waivers live in `docs/atdd/harness-design.md` §9a — not here.** |
| `$DEVSTANDARD/knowledge-base/adr/ADR-0011.md` | The unit of test obligation is the AC; the five-row disposition ordering; the rule that escalation carries a stated reason. |
| `$DEVSTANDARD/knowledge-base/adr/ADR-0012.md` | Establishes the harness-standards layer and its boundary rule. |
| `~/.claude/skills/bd/SKILL.md` §"Disposition on `[TST]` Issues" | The tracker shape a disposition is recorded in — see §9 below. |
| `.claude/skills/implementation-gate/SKILL.md` | The operational pre-implementation gate (project-local `v2.1` — see ID-map.md §Open follow-ups for the divergence note). |

**Layer rule (`ADR-0012`).** A statement that holds regardless of harness or runner belongs to
`T`/`I`; one that constrains how a harness is built, invoked or reports belongs to `H`; only what
*this project chose* belongs here. This guide may not weaken an `H` standard — it records
conformance, or a waiver under `H5`, and it does so in the harness design's §9a.

## 1. Project identity

- **Project:** GActionSheet
- **Platform / language stack:** Google Apps Script (GAS) backend (`src/*.js`, V8 runtime) driving a Google Sheet (the ActionSheet) and Google Docs (floating actions + tracker table); a Workspace add-on (sidebar/homepage card) and an Editor add-on (link-preview/create-action card) front it. Python (`pytest`) + Playwright drives the test harness against a deployed `/exec` Web App.
- **Test runner / harness:** `pytest`; Playwright (Chromium) for live UI surfaces; the project's `scn/` package (this doc's harness — see `docs/atdd/harness-design.md`) wraps both behind the Act/Expect/Checkpoint scenario API.
- **Platform execution ceiling (if any):** GAS enforces a 6-minute execution ceiling per `doPost`/trigger invocation. This is a platform fact. The *response* to it — batch input variants into one fixture call rather than many round trips, and split into a new scenario only when the operation model materially changes (e.g. HTTP phase vs. Playwright phase) — is `T6`/`T21`, and the per-test duration ceiling this project enforces against it is `H4`, whose value lives in `docs/atdd/harness-design.md` §9a (`I6`).

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

## 6. Journeys — journey charter

Realizes `T1`, `T15`, `T17`, `T21`, `T22`; satisfies `ADR-0011` §Decision 5.

**This table is the charter.** It is the document a `[TST]` author reads to decide which journey to
extend before creating a new one, and the input `test-functional` Step 1 selects a disposition
against. A journey with no "why separate" line is a merge candidate, recorded with a bead rather
than merged silently. A `disp:4` (new journey) is justified against this table or not at all.

AC ids are `scn/contract.AC_REGISTRY` keys; entry points are `scn/contract.ENTRY_POINT_REGISTRY`
keys. Neither list is restated here (`I6`) — the columns name which subset each journey claims.

| Journey | Theme / failure domain | Entry points it is call-site for (`T17`) | AC ids it drains | Why separate from each adjacent journey | Risk | Status |
|---------|------------------------|------------------------------------------|------------------|------------------------------------------|------|--------|
| `test_journey` (§16.10) | Full Acts 0–5: pre-flight version check, doc seed, sync, tracker insert, sheet-edit conflict resolution, UI create/status-change, final reconcile across Sync Scenarios A/B/C | `syncDocument`, `syncDocument.onSyncNow`, `onSetActionStatus`, `onInsertTrackerTable`, `_submitCreateAction`, `onActionSheetEdit`, `_processPendingSheetUpdates` | `journey sync-create`, `journey tracker-present`, `journey status-change`, `journey ui-create`, `journey idempotent` | The only journey crossing HTTP *and* Playwright phases in one isolated session; conflict resolution between a sheet edit and a doc state is unreachable from any single-phase journey | P0 | built |
| `test_sync_all` (Scenario D) | Time-based sweep entry point as its own call-site; `DocData` integrity-pass reconciliation (counts, `doc_name`); archive eviction | `syncAll` | `sync-all reconcile` | The sweep visits *all* registered docs, so cross-document reconciliation errors (miscount, stale `doc_name`, wrongly-excluded not-found doc) exist only here — a single-doc journey cannot reach them | P0 (`T22` reconciliation) | built |
| `test_globalid_write_routes` | Direct write-route coverage including the no-op/Dirty-stamp boundary | `upsert_action_rows`, `edit_action_row` | `b7 write-edit`, `b7 write-status` | Exercises the write routes without a document round trip, so a route-contract regression is isolated from doc-sync behaviour | P1 | built |
| `test_import` | `forward_action_rows`/duplicate-forward guard, import-list/select flows | `forward_action_rows`, `importList`, `importSelectedForTest`, `assertTeamAccess` | `import ac1-list`, `import ac2-select`, `import ac3-forward`, `import access-readable`, `import access-absent` | Cross-document data movement: duplication and access-scoping failures require two docs with different ownership, which no single-doc journey holds | P0 (`T22` reconciliation) | built |
| `test_team_scope` | Team auto-assignment from Drive folder ancestry; team-scoped read security gate | `assertTeamAccess`, `team_sync_document` | `teamscope` × 12 (`direct-match`, `subteam-match`, `deep-walk`, `no-match`, `updatedoc-override`, `updatedoc-blank`, `idempotent`, `security-gate`, `teamdata-missing`, `teamdata-safety`, `sticky-after-move`) | Folder-ancestry resolution is a Drive-topology failure domain; it needs a fixture tree no other journey builds | P1 | built |
| `test_sidebar` | Sidebar header/team-view rendering and post-mutation state | `syncDocument.onSyncNow`, `onSetActionStatus`, `onDeleteAction`, `onInsertTrackerTable` | `sidebar sync-SHEET`, `sidebar tracker-insert`, `sidebar mutation-baseline`, `sidebar mutation-changed` | Add-on card rendering is observable only on the `UI` surface, which `INTEGRITY` cannot observe (§3) | P1 | built |
| `test_floating_action_scanner` | Scanner detection across paragraph/table-cell/list placements; tracker-table exclusion | `syncDocument` | `scanner tracker-exclude` | Document-structure parsing; the failure is in *what the scanner sees*, upstream of any sync behaviour | P1 | built (AC-7/AC-8 caret-in-table-cell split to `gts-4hqn`) |
| `test_menu_entry_points` | Sheets/Docs menu wrappers as their own call-sites | `menuSync`, `menuSyncActiveDoc`, `menuInsertTrackerActiveDoc`, `menuEnsureSheetStructure`, `menuRunArchive` | `menu entrypoint-callsite` | ⚠ Exists to satisfy `T17` call-site coverage, not a distinct failure domain. Also holds all 4 `H4` over-budget tests — the `H5` consolidation candidate (plan R11) | P2 (`T17` technicality) | built |
| `test_link_preview`, `test_chip_preview` | Editor add-on link-preview card status-change path (Scenario A, async chip-tap) | `_setStatusFromPreview` | `link-preview status`, `link-preview chip-disclosure` | The Editor add-on is a separate GAS surface from the Workspace add-on, with its own async chip-tap trigger path | P1 | built |
| `test_archive` | Archive sweep eviction thresholds | `menuRunArchive` | `archive lifecycle` | Time-threshold eviction; needs aged fixture state no other journey creates | P2 | built (known gap: `[nv6g]` assumed a 24h Doc-Not-Found threshold that doesn't match the shipped flat 30-day threshold — `gts-0f0s`) |

**Charter findings recorded here, resolved 2026-09-05 (`ADR-0011` §5, `gts-u6ew.12`/`.13`):**

- `test_journey_acts_1_3` had no defensible "why separate" line and was a **merge candidate**
  (`gts-u6ew.13`). Resolved as **retired**: it was a strict prefix of `test_journey` Acts 1–3 with
  no expectation, entry point, or AC id it drained that `test_journey` does not already drain at
  least as strongly (`test_journey`'s Act 1–3 covers the same 5 items plus a 6th `backlogged` case,
  and reaches Act 3's tracker insert through the real `onInsertTrackerTable` UI call-site rather
  than the `insert_tracker_table` test-support fixture this file used) — nothing to fold, so the
  file was deleted rather than merged. "Cheaper reproduction path" is a convenience argument, not a
  failure-domain line, per `ADR-0011` §5. See `tests/test_journey.py` Acts 1–3.
- **6 of the 11 journeys drained no tagged AC at all** (`gts-u6ew.12`). They asserted, but nothing
  they asserted reached the `T24` traceability report, so they were invisible to the gap-diff — the
  largest single contributor to the measured coverage gap and the concrete shape of Phase 1's F7.
  Resolved: each of `test_sync_all`, `test_floating_action_scanner`, `test_menu_entry_points`,
  `test_link_preview`, `test_chip_preview`, and `test_archive` now tags one existing durable-state
  assertion with a new `AC_REGISTRY` id (disp:2 — add an expectation/tag to an existing journey; no
  new test artifact). `test_menu_entry_points`'s tag documents `T17` call-site coverage rather than
  a distinct behavioural AC, matching that row's own "why separate" line above.

Per-journey invariants (T18) are asserted at `INTEGRITY` via `scn.verify_consistency(scope=DOC)` — the single SERVER-class consistency check (§16.7 of the archived lifecycle doc):

- **`test_journey` invariants:** every queued `ai` present and internally consistent on `{DOC, SHEET, TRACKER}`; every doc `ai` present in the sheet and vice versa, scoped to the journey's own `docId`; doc occurrences of one `action_id` are textually identical; sheet `globalId`/Document-column linkage present.
- **`test_sync_all` invariants:** `DocData` row counts and `doc_name` reconcile against the live doc set after a sweep; skipped/not-found docs are correctly excluded, not silently miscounted.
- **`test_import` invariants:** a duplicate entry in an explicit `forwards[]` payload does not produce a duplicate forwarded row (UC-E AC4) — a data-integrity/no-duplication invariant, not a cosmetic one.

## 7. Entry-point coverage matrix

Realizes `T17`; the registry itself realizes `H12`. The authoritative, machine-readable list of all **48** state-modifying entry points (menu items, time-based triggers, sidebar/add-on card actions, HTTP routes, plus test-support routes) lives in `scn/contract.ENTRY_POINT_REGISTRY` and is **not duplicated here** (`I6` — a second hand-maintained copy would drift).

> **This section is a *view* of that registry, not a second copy of it** (`H12`, `I6`). It is
> hand-maintained and has already drifted once — it read "32 entry points / 22 deferred" against an
> actual 37 / 13 until corrected 2026-09-05. `scripts/check_entry_point_registry_view.py`
> (`gts-u6ew.10`) now checks the bold total/covered/deferred numbers below (and the equivalent H12
> row in `docs/atdd/harness-design.md` §9a) against the registry's live counts and fails loudly on
> the next drift, rather than waiting for another manual catch. It is a pure prose-vs-registry count
> check, not a generator — the table itself (call-site class assignments, examples, deferral
> reasons) stays hand-authored commentary; only the numbers are guarded.
>
> **The registry itself is checked against `src/`** by
> `scripts/check_entry_point_extraction.py` (`gts-u6ew.11`): every handler wired in `src/` by
> a menu `addItem`, an `appsscript.json` `runFunction`, a CardService action, a
> `ScriptApp.newTrigger`, or a simple-trigger definition must appear in
> `ENTRY_POINT_REGISTRY` (or, when read-only, in `ENTRY_POINT_SOURCE_EXEMPT` with a reason) —
> otherwise the harness fails. Its first run registered **11** previously unenumerated
> state-modifying handlers (37 → 48), which is why the counts above moved. The `doPost` route
> class is deliberately out of that extractor's scope and is still hand-authored into the
> registry; see the script's docstring for why.

Summary by call-site class (counts refreshed 2026-09-05 from `scn/contract.py`; class assignments as of 2026-06-18 via `scripts/check_coverage.py -v`):

| Call-site class | Examples | Covered | Deferred (warn-only, tracked) |
|---|---|---|---|
| Core | `syncDocument`, `assertTeamAccess` | yes | — |
| Workspace add-on card | `onSyncNow`, `onSetActionStatus`, `onDeleteAction`, `onInsertTrackerTable`, `importSelectedSubmit` | partial | `importSelectedSubmit` (CHECK_BOX SelectionInput not Playwright-drivable; `importSelectedForTest` is the interim surrogate route) |
| Editor add-on card | `_submitCreateAction`, `_setStatusFromPreview` | yes | — |
| Installable triggers | `syncAll`, `onActionSheetEdit`, `_processPendingSheetUpdates` | yes | — |
| Sheets menu items | `menuSync`, `menuEnsureSheetStructure`, `menuInitializeTriggers`, `menuBootstrap`, `menuRunArchive` | partial | several Setup-submenu items, tracked under EPIC `gts-rz4k.4` |
| Test-menu items (`gts-u6ew.11`) | `menuCleanupTestDocs`, `menuBeginTestSession`, `menuEndTestSession`, `menuSetupFixture`, `menuSyncDocument`, `menuSetupAndSync`, `menuInsertTrackerTable` | partial | all seven — TestControl-driven manual twins of routes already covered; `menuCleanupTestDocs` has a real test but an untagged assertion |
| HTTP routes (production) | `patch_action_status`, `edit_action_row`, `upsert_action_rows`, `sync_action_rows`, `mark_doc_not_found`, `delete_action_row`, `forward_action_rows`, `importList`, `menuSyncActiveDoc`, `menuInsertTrackerActiveDoc` | yes | — |
| Test-support routes | `run_fixture`, `set_test_token`, `bootstrap`, `begin_journey_session`, `end_journey_session`, `setup_team_scope_fixture`, `importSelectedForTest` | n/a (harness-only) | — |

24 of the 48 entries are expected to carry a real tagged scenario call-site; the remaining **24** are explicitly enumerated as **deferred** (not silently uncovered) in `scn/contract.ENTRY_POINT_DEFERRED`, each with a tracking bead, so `scripts/check_coverage.py`'s `ep.*` gap-diff is green by design rather than by omission. Converting deferred entries to real call-sites is tracked under EPIC `gts-rz4k` (children `.1` triggers, `.2` routes, `.3` cards, `.4` menu, `.5` test-support).

## 8. AC-validation fidelity log

Realizes `T23`, `I11`. No feature in this project has used the Slice fidelity tier as of 2026-06-18 — all shipped ACs went through Spec review (the default) directly into the twin-ticket Hardened phase. If a future feature invokes Slice (ADR-0013), record it here with its justification and open-seams register at that time; this section is intentionally empty until then.

| Feature / AC | Fidelity (spec/slice/hardened) | Justification (required if slice) | Open seams to preserve |
|--------------|-------------------------------|-----------------------------------|------------------------|
| _(none yet — see note above)_ | | | |

## 9. Disposition record

Realizes `ADR-0011`. The disposition ordering itself is **not** restated here — it lives in
`ADR-0011`, and the label semantics in `bd/SKILL.md` §"Disposition on `[TST]` Issues". This section
records only where this project keeps dispositions, how they are audited, and what it has accepted.

- **Where a disposition is recorded:** on the `[TST]` bead — the `disp:<n>` label (the enumerated
  half, matchable) plus a `## Disposition` section in the description carrying `Target:`, `Basis:`,
  and on escalation `Reason:` (the free-text half, read not matched).
- **Audit command:** `python scripts/audit_disposition.py` (gts-u6ew.9) mechanizes the two ad hoc
  `bd`/`jq` commands from `bd/SKILL.md` §Disposition into one script — same two checks (no
  `disp:` label; more than one `disp:` label or no `## Disposition` section), same closed-value-set
  reasoning. `bd --validate` does not see the description section, so the script's own scan of it
  is required — no combination of `bd lint`/`--validate` flags substitutes.
  - `--ids ID,ID,...` audits exactly the named beads — this is what `merge-gate` Step 2.5 passes
    (the `[TST]` beads in scope for the diff under review).
  - `--since DATE` (default: `2026-09-05`, this project's ADR-0011 adoption date) audits every
    `[TST]` bead created on/after that date, tracker-wide — the periodic health check. It
    deliberately does not flag the ~213 pre-adoption `[TST]` beads: dispositions bind forward, and
    closed `[TST]` items are not re-litigated (below).
  - Prints nothing and exits 0 on a clean scope; prints one line per violation and exits 1
    otherwise. Verified live 2026-09-05: `--since 2026-09-05` (no other args) surfaced two real
    gaps — `gts-zjrm`/`gts-sxvj`, `[TST]` beads from concurrent unrelated work with no disposition
    at all — proving the check finds a real violation rather than passing vacuously; `--ids`
    scoped to this stage's own beads (`gts-u6ew.12`/`.13`) returned clean.
- **Gate that verifies it against the diff:** `merge-gate` Step 2.5 (`ADR-0011` §Decision 4) — a
  `[TST]` bead reaching the merge boundary without a disposition, or whose diff contradicts its
  declared disposition, is a blocking finding. The audit script above is what Step 2.5 runs
  mechanically instead of hand-typing the `bd`/`jq` commands per invocation. *(Plan R7 — in force as
  of 2026-09-05, gts-u6ew.9.)*
- **Which journey a disposition is decided against:** the charter in §6. A `disp:4` (new journey)
  is justified against that table's "why separate" column or it is not justified at all.

**Escalation log** — every `disp:3` and `disp:4` accepted. This is where suite growth becomes a
governed quantity rather than a side effect:

| Work item | Disposition | Artifact created | Reason cheaper dispositions did not serve |
|-----------|-------------|------------------|-------------------------------------------|
| _(empty — dispositions bind forward from 2026-09-05; closed `[TST]` items are not re-litigated per `test-bootstrap.md` Phase 2 §5)_ | | | |

---
_Filled 2026-06-18 (gts-ruoa) from `docs/atdd/archive/atdd-lifecycle.md` §15–§16 and the `scn/` module map in `docs/atdd/ID-map.md`._
_Aligned to `test-framework` v1.0.0 (`ADR-0011`, `ADR-0012`) 2026-09-05 on branch `test-framework-upgrade`; see `docs/atdd/test-framework-upgrade-plan.md`._
