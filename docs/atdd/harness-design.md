# Project Harness Design — GActionSheet

Build specification of the `scn/` scenario harness. Declares module layout,
support-function signatures, surface readers, contract loading, and the
expectation/checkpoint engine algorithm. Project facts already stated in
`docs/atdd/project-testing-guide.md` (surfaces §3, fixture isolation §4,
contract schema §5, journeys §6, entry-point coverage §7) are cited, not
repeated.

## 0. References (do not restate)

| Document | Owns |
|----------|------|
| `DevStandard/knowledge-base/methodology/testing/bdd/sdlc-testing-principles.md` | `T1`–`T24`, esp. `T11` checkpoints, `T13` queued verification, `T15` Act/Expect/Checkpoint + drain invariant, `T16` one entry point per act, `T24` generated traceability. |
| `DevStandard/knowledge-base/methodology/testing/bdd/sdlc-implementation-principles.md` | `I6` single-source contract ownership. |
| `docs/atdd/project-testing-guide.md` | Project surfaces (§3), fixture isolation (§4), contract schema (§5), journeys (§6), entry-point coverage matrix (§7). |
| `docs/atdd/archive/atdd-lifecycle.md` §16 | Source narrative this spec is extracted from — canonical for the scenario model. |

**Authoritative-contract rule (I6):** field tables are never restated here. `scn/contract.py` loads `ContractSchema.json` (exported from `src/ContractSchema.js`) and every other module imports from it.

## 1. Scope

- **Scenario-author model this harness implements:** the Act/Expect/Checkpoint vocabulary, `docs/atdd/archive/atdd-lifecycle.md` §16.1–§16.10 (canonicalized in `tests/test_journey.py`, bead GTaskSheet-5vwu.13).
- **What this spec produces:** module layout (§2), typed signatures for every support-function the author calls (§4–§7), and the engine drain algorithm (§8).
- **What this spec does not contain:** how a journey reads (the author model, §16 / `test_journey.py`), and any universal principle (referenced by ID only).

## 2. Package / module layout

| Module | Responsibility | Realizes | Build unit |
|--------|----------------|----------|------------|
| `scn/ai.py` | The `ai` domain-noun object: action fields, `as_text()` self-rendering. | `T15` | GTaskSheet-5vwu (built) |
| `scn/contacts.py` | Static `TEST_CONTACTS` directory stand-in; `expected_name(email)` derivation. | — | built |
| `scn/engine.py` | `CheckpointEngine` — expectation queue + checkpoint drain; `Surface`/`CheckpointKind`/`Severity` enums; `Expectation` dataclass. | `T11`, `T13`, `T15` | built |
| `scn/surfaces.py` | Per-surface readers: `DocReader`, `SheetReader`, `TrackerReader`. | `T5`, `T19` | built |
| `scn/session.py` | `ScenarioSession` — thin driver: lifecycle, acts, queries, expectation delegation. | `T16`, `I6` | built |
| `scn/ui.py` | `UiDriver`/`Card` — page-object driver for the live UI surface (sidebar, preview card). | — | built |
| `scn/contract.py` | Loads `ContractSchema.json`; exposes field/route/AC/entry-point registries. | `I6` | built |
| `scn/assertions.py` | Standalone per-surface comparison helpers (`check_present_consistent`, `check_absent`). | `T5`, `T10` | built |
| `scn/reporter.py` | `Reporter`/`NullReporter` — harvests drained-expectation results into JUnit properties + console/Allure steps. | `T24` | built |
| `tests/test_journey.py` + `tests/conftest.py` | The canonical journey + the per-run isolated session fixture (`scn`, `browser_page`). | `T9`, `T21` | built |

## 3. Ownership and dependency direction

- **Assertion ownership:** `ScenarioSession` owns lifecycle, fixture invocation, surface captures, and `ai`-state accumulation; it does **not** own assertion logic. Evaluation lives in `CheckpointEngine.drain()` and `scn/assertions.py`. `verify*`/`expect_absent` calls on `ScenarioSession` are thin enqueuers (`_enqueue`) — nothing is asserted until a `checkpoint()` drains.
- **Dependency direction (acyclic):** `session.py` → `engine.py` → (`assertions.py`, `surfaces.py`, `contacts.py`); `ai.py` and `contract.py` are leaf modules consumed by all of the above; `ui.py` is depended on only by `session.py` (via the `scn.ui` property) and `tests/test_journey.py`.

## 4. The domain noun object

Realizes `T15`. `scn/ai.py::ai`.

- **Fields:** `action` (text); `assignee` (email, optional); `action_id` (`AI-N`, optional — author-set to pin, or left unset to accept the next auto-assigned id); `status` (free text, optional — unset means "render no status token, expect detection as Open after sync"); `assignee_source` (`"chip"` | `"parsed"`, optional — set only when an `ai` is read back from a synced surface, recording chip-vs-parsed-text assignee origin; unset on author-constructed `ai`s).
- **Self-rendering rule (`as_text()`):** `AI: {action}` → adds `{assignee}` when set → `AI-{N}:` prefix replaces `AI:` when `action_id` is set → trailing `({status})` token appended only if `status` is set. See project-testing-guide.md §6 journey table and archived `atdd-lifecycle.md` §16.2 for the full truth table.
- **Mutability / pinning rule:** the author mutates an `ai` after an act to pin newly-known fields (e.g. `created.action_id = scn.doc_items()[...].action_id` after a sync assigns it) — pinning happens before the following `verify*`/`expect_absent` enqueue call, since enqueue snapshots the noun's pinned fields at that instant (§8 snapshot rule).

## 5. Support-function catalog signatures

Realizes `T15`, `T16`. As-built in `scn/session.py` and `scn/ui.py`.

**Lifecycle**

| Function | Purpose | Realizes |
|----------|---------|----------|
| `ScenarioSession.new_doc(settings, *, request=None) -> ScenarioSession` | Create the per-run isolated fixture (testing guide §4) via `begin_journey_session`; register teardown. | `T9` |
| `session.close() -> None` | Tear down via `end_journey_session`; assert the expectation queue is empty. | `T15` drain invariant |

**Acts (one entry point each — `T16`)**

| Act | Entry point | Sync scenario |
|-----|-------------|----------------|
| `session.append_paragraph(text)` | doc paragraph insert | — |
| `session.insert_tracker()` | tracker insert/refresh via HTTP fixture | — |
| `session.sync()` | `syncDocument` via doPost (`sync_action_rows`) | C |
| `session.edit_sheet(target, **fields)` | sheet-cell edit, replicates `onActionSheetEdit`'s Dirty + Date-Modified stamp | B |
| `session.set_status(target, status)` | sheet status action via HTTP fixture | A |
| `session.link_preview_status_change(target, status)` | editor link-preview card status dropdown | A (UI path) |
| `session.delete(target)` | sheet delete via HTTP fixture | — |
| `ui.create_action(target)` | `@`-menu Create-action form | — |
| `ui.sidebar_sync(timeout="60s")` | Sync Now button in sidebar card | C (UI path) |
| `ui.insert_tracker_button(timeout="30s")` | Insert tracker button in sidebar card | — |
| `ui.sidebar_delete(target, timeout="15s")` | Per-row Delete action button in sidebar card | — |
| `ui.sidebar_set_status(target, status, timeout="15s")` | Per-row status control in sidebar card | A (UI path) |
| `ui.hover(locator, timeout="5s") -> Card`, `ui.set_status(card, status)` | live preview-card hover + status gesture | A (UI path) |

**Queries (read, no mutation)**

| Query | Returns | Scope |
|-------|---------|-------|
| `session.doc_items() -> list[ai]` | floating-action paragraphs parsed from `.docx` | run-identity-scoped (docId) per `T19` |
| `session.sheet_rows() -> list[ai]` | ActionSheet rows parsed from `.xlsx` | docId-scoped |
| `session.find_sheet_actions() -> list[ai]` | fixture/webapp read for current doc only | docId-scoped |
| `session.archive_rows(doc_id) -> list[ai]` | archived rows for a doc | doc-scoped |
| `session.tracker_id_urls() -> dict` | id → chip-link URL map from the tracker table | docId-scoped |

**Expectation + checkpoint**

| Function | Purpose |
|----------|---------|
| `session.verify_all_expectations(ai, *, at=AUTO) -> None` | Enqueue a cross-surface expectation (DOC+SHEET+TRACKER if present). |
| `session.verify(ai, on=SURFACE, *, at=AUTO, within=None, severity=Severity.FAIL) -> None` | Enqueue a single-surface expectation. |
| `session.expect_absent(ai, on=SURFACE, *, at=AUTO) -> None` | Enqueue an absence/terminal expectation. |
| `session.checkpoint(kind, *, on=None, label=None) -> None` | Drain observable expectations (`T11`); `kind` is `STEP` or `INTEGRITY`; `on=frozenset({Surface.X,...})` restricts which surfaces a `STEP` drains. |
| `session.verify_consistency(scope=Surface.DOC) -> dict` | The SERVER-class consistency check (testing-guide §6/§16.7); called standalone or internally by every `INTEGRITY` checkpoint. |

## 6. Surface readers

Realizes `T5`, `T19`. One reader per surface declared in **testing-guide §3** — not re-declared here.

| Surface (testing-guide §3) | Reader signature | Returns |
|---------------------------------|------------------|---------|
| `DOC` | `scn.surfaces.DocReader().read(docx_bytes, doc_id) -> list[ai]` | `ai`-shaped records, one per floating-action paragraph, docId-scoped |
| `SHEET` | `scn.surfaces.SheetReader().read(xlsx_bytes, doc_id, tab_name="Actions") -> list[ai]` | `ai`-shaped records, one per ActionSheet row, docId-scoped |
| `TRACKER` | `scn.surfaces.TrackerReader().read(docx_bytes, doc_id) -> list[ai]` | `ai`-shaped records parsed from the tracker table, docId-scoped |
| `UI` | `scn.ui.UiDriver` methods (`locate`, `hover`, `read_current`, etc.) | live `Card`/DOM evidence; `read_current() -> list[ai]` for the sidebar list |

## 7. Contract module

Realizes `I6`. `scn/contract.py` loads `ContractSchema.json` (exported from `src/ContractSchema.js`, path resolved relative to `scn/`'s parent) once at import.

- **Load mechanism:** module-level `json.load` at import time; exposes typed constants (`ACTION_ITEM_FIELDS`, `SHEET_ACTION_FIELDS`, `SHEET_HEADERS`, `COLUMNS_BY_FIELD`, `DERIVED_FIELDS`, `ROUTE_NAMES`, `TEST_ROUTE_NAMES`, `MESSAGES`, `MODEL_NAMES`, `AC_REGISTRY`, `ENTRY_POINT_REGISTRY`, `ENTRY_POINT_DEFERRED`) that every other `scn/` module imports rather than redeclaring.
- **Drift behavior:** a missing/renamed field surfaces as an immediate `KeyError`/`AttributeError` at import or first access — there is no silent default-fallback path, so contract drift between `ContractSchema.js` and the harness fails loudly rather than producing a stale or partially-correct read.

## 8. Expectation / checkpoint engine algorithm

Realizes `T11`, `T13`, `T15`. As-built in `scn/engine.py::CheckpointEngine`.

- **Expectation record shape:** `Expectation` dataclass — snapshot of the noun's expected fields, the surface set still `remaining` to check, the evaluation `target` (`AUTO` | `INTEGRITY_TARGET` | a label string), and `severity` (`FAIL` | `WARN`); the triage tag (`T10`) travels with the call that created it for failure messages.
- **Snapshot rule:** `verify*`/`expect_absent` capture the noun's currently-pinned fields into the `Expectation` at enqueue time; later mutation of the `ai` object does not change an already-queued expectation.
- **Observable set per checkpoint:** `_INTEGRITY_OBS = {DOC, SHEET, TRACKER}` (UI is excluded — drained only by a targeted `checkpoint(STEP, on=Surface.UI)`); a `STEP`'s observable set is whichever surfaces its `on=` argument names (defaults to all non-UI surfaces it has fresh reads for).
- **Per-surface evaluation:** for each expectation, `observable_here = remaining ∩ OBS`; `scn/assertions.check_present_consistent`/`check_absent` evaluate the derivable checks per surface; a pass drops that surface from `remaining`; a `FAIL` records and (per severity) aborts or is accumulated; a `WARN` records and still drops the surface.
- **Integrity consistency obligation:** at `INTEGRITY`, `session.verify_consistency(scope=DOC)` runs the §16.7 SERVER-class checklist (queued expectations met; per-surface internal consistency; cross-surface presence both ways) for the run's `docId` scope (`T19`).
- **Targeting enforcement:** `_is_targetable(exp, kind, label)` gates whether a given checkpoint may evaluate an expectation — `AUTO` targets the earliest checkpoint that can observe it; `INTEGRITY_TARGET` skips all `STEP`s; a labeled target (`session.mark(label)` + `checkpoint(..., label=label)`) evaluates only at that specific later checkpoint. A pinned/targeted expectation is not drained early even if technically observable sooner.
- **Retire rule:** an expectation is removed from the queue once `remaining` is empty and any consistency obligation (`INTEGRITY`'s `verify_consistency`) is discharged.
- **Drain invariant:** `STEP` may leave expectations queued; `INTEGRITY` may not leave an observable, non-forward-targeted expectation undrained — `session.close()` raises `DrainInvariantError` (listing the dangling expectations) if the queue is non-empty at teardown. Every journey therefore ends with an `INTEGRITY` checkpoint.
- **Report emission (`T24`):** `drain()` returns one `(tag, surface, PASS|WARN)` record per drained expectation; `Reporter`/`NullReporter` (`scn/reporter.py`) and `ScenarioSession.checkpoint()` append each as a JUnit `ac.<tag>.<surface>` property via `request.node.user_properties` — no separate matrix is built; `scripts/check_coverage.py` diffs these against `scn.contract.AC_REGISTRY`/`ENTRY_POINT_REGISTRY`.

## 9. Engine-execution proof

Traced through `tests/test_journey.py` Act 1–2 (testing-guide §6 journey table): Act 1 appends five `ai.as_text()` paragraphs (pure DOC mutation, no expectations enqueued yet — nothing is true to check until sync). Act 2 calls `session.sync()`, then pins the post-sync expected fields (`status="Open"` for tokenless items, auto-assigned `action_id`s for `unassigned`/`with_email`) and calls `verify_all_expectations(a)` for all five `ai`s plus `verify_consistency(scope=DOC)`, then `checkpoint(INTEGRITY)`. At that `INTEGRITY`: `remaining = {DOC, SHEET}` for each of the five (no tracker exists yet — `TRACKER` was never in `remaining` since `insert_tracker()` hasn't run); both surfaces are in `_INTEGRITY_OBS`, both get fresh reads, both evaluate and drop, queue empties, `verify_consistency`'s checklist passes, `INTEGRITY` retires every expectation. No journey-modeling conflicts found in this trace — the documented deviations D1/D3 in the test file header (the Coordination-Log split-INTEGRITY for Act 4/5, and resolving `created.action_id` post-sync before the Act 5 hover) are the only departures from a straight-line trace, and both are mechanical (ordering), not modeling conflicts.

## 10. Deferred contract observations

| # | Observation | Route to |
|---|-------------|----------|
| 1 | `doc_id`/`doc_name` are derived fields resolved from the Document-column formula (col 7), not stored columns — `scn/contract.DERIVED_FIELDS = frozenset(["doc_id", "doc_name"])`; any contract consumer treating them as plain stored fields will read stale/absent values. | `src/ContractSchema.js` (already modeled — flagging for any future contract consumer that assumes all `SHEET_ACTION_FIELDS` are stored columns). |
| 2 | `test_sync_all`'s `[nv6g]` archive assertion assumed a 24h Doc-Not-Found eviction threshold; `ArchiveManager.js` actually uses a flat 30-day threshold for everything — found during Batch 3 execution (2026-06-18), not yet resolved. | `GTaskSheet-0f0s` (product decision pending). |

---
_Filled 2026-06-18 (GTaskSheet-ruoa) from `docs/atdd/archive/atdd-lifecycle.md` §16.8–§16.10 and the as-built `scn/` package._
