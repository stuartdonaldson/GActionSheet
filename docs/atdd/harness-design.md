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
| `$DEVSTANDARD/test-framework/sdlc-testing-principles.md` | `T1`–`T25`, esp. `T11` checkpoints, `T13` queued verification, `T15` Act/Expect/Checkpoint + drain invariant, `T16` one entry point per act, `T24` generated traceability, `T25` AC retirement. |
| `$DEVSTANDARD/test-framework/sdlc-implementation-principles.md` | `I1`–`I12`, esp. `I6` single-source contract ownership, `I12` one owning helper rather than per-test duplication. |
| `$DEVSTANDARD/test-framework/harness-standards.md` | `H1`–`H13` — how a harness is built, invoked and reports. **This project's values, conformance states and waivers are recorded in §9a below; the standards themselves are never restated.** |
| `$DEVSTANDARD/knowledge-base/adr/ADR-0012.md` | Establishes the harness-standards layer and its boundary rule. |
| `docs/atdd/project-testing-guide.md` | Project surfaces (§3), fixture isolation (§4), contract schema (§5), journeys (§6), entry-point coverage matrix (§7). |
| `docs/atdd/archive/atdd-lifecycle.md` §16 | Source narrative this spec is extracted from — canonical for the scenario model. |

**Authoritative-contract rule (I6):** field tables are never restated here. `scn/contract.py` loads `ContractSchema.json` (exported from `src/ContractSchema.js`) and every other module imports from it.

## 1. Scope

- **Scenario-author model this harness implements:** the Act/Expect/Checkpoint vocabulary, `docs/atdd/archive/atdd-lifecycle.md` §16.1–§16.10 (canonicalized in `tests/test_journey.py`, bead gts-5vwu.13).
- **What this spec produces:** module layout (§2), typed signatures for every support-function the author calls (§4–§7), and the engine drain algorithm (§8).
- **What this spec does not contain:** how a journey reads (the author model, §16 / `test_journey.py`), and any universal principle (referenced by ID only).

## 2. Package / module layout

| Module | Responsibility | Realizes | Build unit |
|--------|----------------|----------|------------|
| `scn/ai.py` | The `ai` domain-noun object: action fields, `as_text()` self-rendering. | `T15` | gts-5vwu (built) |
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

## 9a. Harness-standards conformance

Realizes `ADR-0012`. One row per `H` standard: this project's value or mechanism, and the single
place it lives (`I6` — a number repeated in two files is a defect, not a convention).

**State** is one of `conformant` / `waived` / `not applicable` / `declined`, per
`$DEVSTANDARD/README.md` §Conformance States. There is no `partial`: a standard partially met is
`waived` with the unmet part named. A `waived` row carries an issue id; a `declined` row carries a
reason and a date.

Recorded 2026-09-05 against the state on branch `test-framework-upgrade`. Rows marked `waived`
with a `gts-` id are scheduled by `docs/atdd/test-framework-upgrade-plan.md` — **this table is a
record of current state, not target state**, and each such row flips to `conformant` when its bead
closes.

| `H` | This project's value / mechanism | Single source (file · symbol) | State |
|-----|----------------------------------|-------------------------------|-------|
| `H1` tier gating | Two tiers exist and are separately invocable (`pnpm run test:local` = `-m no_live_session`; `pnpm run test:live` = `-m live`); `pnpm run test:regression` composes them with a real gate (`test:local -- --ff && test:live -- --ff`), opening no live session unless the local tier is green. `test:full` still exists (one invocation, no gate) but is no longer the cited entry point | `package.json` · `scripts.test:regression` | **`conformant`** (`gts-u6ew.1`, closed 2026-09-05) |
| `H2` failure-first ordering within a tier | `--ff` passed to both tier invocations inside `test:regression` (via `pnpm run test:local -- --ff` / `test:live -- --ff`). `--lf`/`--sw` stay banned as regression defaults by project `CLAUDE.md` (they subset rather than reorder) | `package.json` · `scripts.test:regression` | **`conformant`** (`gts-u6ew.2`, closed 2026-09-05) — collection size verified unchanged (716/716 items, same set, under `-m no_live_session`) before/after `--ff`. xdist interaction measured empirically: with two nodeids injected into `.pytest_cache/v/cache/lastfailed`, `--collect-only -n 4 --dist worksteal` puts them at collection positions 1–2 (vs. 442/716 without `--ff`) — `--ff` reorders at collection time, strictly before xdist's worksteal distribution, so previously-failing tests do land early under this project's `-n 4 --dist worksteal` (plan §2c's open verification item, now closed) |
| `H3` declared tier markers | 5 markers declared in one place. An **unmarked test does not fail collection**: `tests/conftest.py` stamps `live` on every collected item not carrying `no_live_session`, so classification is total by construction and the default is the expensive tier | `pyproject.toml` · `[tool.pytest.ini_options] markers`; `tests/conftest.py:78` | **`declined` (2026-09-05)** — `H3` exists to stop unmarked tests leaking into the *fast* gate and destroying `H1`. This project's default is `live`, so that leak is directionally impossible: a forgotten marker can only make the live tier slower, never put a live test inside the fast gate. `H1`'s actual guarantee holds by construction. Deliberate design (`gts-aqpk`); no issue to close |
| `H4` duration ceiling | `CEILING_LIVE_S`=60.0 / `CEILING_OTHER_S`=30.0 declared beside `REL_THRESHOLD`/`ABS_SLACK_S` (`I6`); every run's JSONL record and terminal FINISH line now carries `is_live`, `ceiling_s`, `over_ceiling`. Against these ceilings 4 tests are still over, all in `tests/test_menu_entry_points.py` | `tests/duration_instrumentation.py` · `CEILING_LIVE_S`, `CEILING_OTHER_S`, `build_record` | `waived` — **`gts-u6ew.14`** (mechanism landed 2026-09-05 via `gts-u6ew.3`; the 4 over-budget tests remain unconsolidated — see `H5` row). **Report-only/fail collision, resolved:** `duration_instrumentation.py`'s docstring says "nothing here can fail or skip a test"; `H4` wants over-ceiling treated as "a harness-reported failure, not a slow pass." Resolution is plan §2b option (a) — the module stays report-only (verdict on the record/line only, no `pytest.fail`/`skip` added), and turning `over_ceiling` into an actual gate failure is left to a separate, not-yet-built gate. This preserves the module's `T12` pure-logic/hook-wiring split; the module's report-only contract was not relaxed |
| `H5` waiver protocol | The table below. Empty: the 4 over-budget tests are neither consolidated nor waived yet | this section | `waived` — **`gts-u6ew.14`** (deferred; `H5`'s resolution order `T6`→`T12`→`T21` must be applied before any waiver is earned) |
| `H6` three outcome classes | `scn/outcomes.py` (`BoundaryFault(RuntimeError)` + one `classify()` helper, `I12`) is the single classification path. `scn/session.py`'s four retry-exhaustion sites (formerly bare `RuntimeError`) now raise `BoundaryFault`; `tests/conftest.py`'s `pytest_runtest_makereport` classifies every call-phase result and stamps `outcome_class` as a user_property, read back into every JSONL duration record | `scn/outcomes.py`; `scn/session.py::_http_post`; `tests/conftest.py::pytest_runtest_makereport` | **`conformant`** (`gts-u6ew.6`, closed 2026-09-05) |
| `H7` harness-level retry | Retry policy numbers (`HTTP_POST_MAX_ATTEMPTS`=5, `HTTP_POST_RETRY_DELAY_S`=3, exponential) moved to `tests/duration_instrumentation.py`, co-located with the `H4` ceiling (`I6`); `scn/session.py` imports them under their original private names. `_http_post` gained an `on_attempts` callback (its return type — a plain dict — is unchanged, since ~50 existing test call sites depend on it directly) so every call records its attempt count via `reporter.junit("http.attempts", ...)`, the same user_properties path `ac.*`/`ep.*`/`elapsed.*` already use; `conftest.py` sums it per test into `build_record`'s new `attempts` field. A fault surviving the policy still raises `BoundaryFault` — never silently retried further or converted to a pass | `tests/duration_instrumentation.py` · `HTTP_POST_MAX_ATTEMPTS`, `HTTP_POST_RETRY_DELAY_S`; `scn/session.py::_http_post` | **`conformant`** (`gts-u6ew.7`, closed 2026-09-05) |
| `H8` boundary-fault rate emitted | `tests/duration_instrumentation.py` gained `summarize_run()`/`format_run_summary()` (pure aggregation, `I12`); `tests/conftest.py`'s new `pytest_sessionfinish` hook filters `duration-log.jsonl` to the current run and prints the line every run — no longer offline-only. Verified live in the stage-3 targeted gate: `H8 boundary-fault summary: 0/735 executions failed (0.0%); 0.0s of 54.5s wall time (0.0%) spent failing, 0 boundary fault(s) (0.0% of failures)` | `tests/duration_instrumentation.py` · `summarize_run`, `format_run_summary`; `tests/conftest.py::pytest_sessionfinish` | **`conformant`** (`gts-u6ew.8`, closed 2026-09-05) |
| `H9` traceability carries outcome class | Carried. `scripts/check_coverage.py::_split_uncovered_from_missing` splits every registry gap into `uncovered` (confirmed — the run was clean) vs. `unreached this run` (the run's latest `test-results/duration-log.jsonl` entries include a `BOUNDARY_FAULT`, so absence of coverage is not confirmed). Read from the duration log, not JUnit properties — `outcome_class` does not survive into JUnit XML in this project (`_pytest.junitxml.LogXML.finalize()` reads only the teardown-phase report's `user_properties`; `tests/conftest.py`'s `pytest_runtest_makereport` stamps the call-phase report instead — see `_latest_run_boundary_fault_info`'s docstring for the verified mechanism). `_report` returns a bitmask (`1`=uncovered, `2`=unreached this run) for distinct exit-code meaning | `scripts/check_coverage.py` · `_collect`, `_report`, `_split_uncovered_from_missing`, `_latest_run_boundary_fault_info` | **`conformant`** (`gts-u6ew.15`, closed 2026-09-05) |
| `H10` AC staleness check | Instrument built: `scripts/check_coverage.py::_stale_acs` (ported from `$DEVSTANDARD/tools/test-suite-diagnostics.py`'s `junit_ac_coverage`/`stale_acs`) flags `AC_REGISTRY` entries with zero PASS coverage across the last N=3 JUnit files on disk (by mtime), sharing `_parse_junit`/`_collect` with `H9`'s gap-diff (`I6`/`I12`). Runs by default with the gap-diff, report-only — does not affect exit code. Against the current `test-results/junit/*.xml`: 26 of 27 candidate-stale (window=3) — directionally consistent with the diagnostics' earlier reading, but the window is still whatever files happen to be on disk by mtime, not a verified full-suite profile | `scripts/check_coverage.py` · `_stale_acs`, `_collect_ac_coverage_per_file`, `_junit_files_by_mtime` | **`waived`** — **`gts-u6ew.16`** (instrument landed 2026-09-05) + escalation E2. Moved off `unknown` because the check now exists and runs every gap-diff invocation; **still not settled** — settling needs the first operator-initiated full regression sweep, which `gts-u6ew.16` explicitly did not run (`CLAUDE.md` backstop rule against an agent starting one on its own initiative). First staleness contributor resolved earlier: 10 placeholder registry entries purged into `scn/contract.AC_SELFTEST_FIXTURES` (`gts-u6ew.4`, closed 2026-09-05). Second contributor remains: 6 of 11 journeys draining no tagged AC (testing guide §6, stage 5) |
| `H11` behaviour/journey-derived names | Not met. ≥11 test files encode a bead id: `test_b7_`, `test_f3me1_`, `test_f3me2_`, `test_hroj_`, `test_hztp_`, `test_kkm7_`, `test_p9ra_`, `test_pulj_`, `test_uuse_`, `test_zc0w_`, `test_adr0027_`. Nothing prevents the next one | `tests/` | `waived` — **`gts-u6ew.5`** (lint blocking new ones) + **`gts-u6ew.17`** (partial rename, escalation E3). **The diagnostics does not detect this by default** — see the invocation note below |
| `H12` entry-point registry | A single machine-readable registry of 48 state-modifying entry points, with 24 explicitly deferred (each with a tracking bead) rather than silently uncovered. Read by the gap-diff; the testing guide §7 table is a view of it, checked against it (`gts-u6ew.10`); the registry itself is checked against `src/` (`gts-u6ew.11`, §9b) | `scn/contract.py` · `ENTRY_POINT_REGISTRY`, `ENTRY_POINT_DEFERRED`, `ENTRY_POINT_SOURCE_EXEMPT` | **`conformant`** |
| `H13` one regression entry point | `pnpm run test:regression` is the single named full-suite entry point (`CLAUDE.md` Backstop rules and `.claude/skills/implementation-gate/SKILL.md` both cite it, replacing the prior open-coded `pytest -x`/`pytest --alluredir=...` references). `test:full` still exists but is not cited as the regression entry point | `package.json` · `scripts.test:regression` | **`conformant`** (`gts-u6ew.1`, closed 2026-09-05) |

**Diagnostics invocation (`H11`).** `test-suite-diagnostics.py`'s default `--ticket-pattern`
expects a `Prefix-slug` form and does **not** match this project's bare 4-char bead slugs, so
`H11` self-reports green against the default. Run it with an explicit pattern
(`--ticket-pattern '(?:\b(?:gts-)?[a-z0-9]{4}\b)'` or equivalent) or the signal is meaningless
here. Recorded 2026-09-05; no bead needed.

**Waivers (`H5`)** — a waiver names the test, the observed value, the reason, and an issue id. A
row without an issue id is not a waiver, it is an unrecorded exception:

| Test | Standard waived | Observed value | Reason | Issue id |
|------|-----------------|----------------|--------|----------|
| _(none yet)_ — the 4 over-budget `test_menu_entry_points` tests (93.5s / 47.7s / 40.6s / 32.3s against a 30s default) are **not** waived: `H5` requires the `T6`→`T12`→`T21` resolution order to be tried and stated insufficient first | `H4` | see plan §1 | consolidation deferred pending a real suite-wide profile | **`gts-u6ew.14`** |

## 9b. Entry-point registry

Realizes `H12`, feeding `T17`. The testing guide §7 coverage matrix is a **view** of this list,
not a second copy of it (`I6`).

- **Registry location and format:** `scn/contract.py` · `ENTRY_POINT_REGISTRY` (a `dict[str, str]`
  mapping entry-point key → description), with `ENTRY_POINT_DEFERRED` naming the subset that is
  knowingly uncovered. Loaded at import; consumed by `scripts/check_coverage.py` and by
  `ScenarioSession`, which emits `ep.<entry_point>.<surface>` JUnit properties.
- **How the coverage matrix is derived from it:** testing guide §7 stays hand-maintained prose (its
  call-site class assignments and deferral rationale are not mechanically derivable from a
  `dict[str, str]` without losing that narrative), but its stated total/covered/deferred numbers —
  and this row's own 37/13 — are now checked against the registry's live counts by
  `scripts/check_entry_point_registry_view.py` (**`gts-u6ew.10`**, closed 2026-09-05), run every
  `test:local` pass via `tests/test_check_entry_point_registry_view.py`. It fails loudly (not
  silently) if either doc's numbers stop matching `len(ENTRY_POINT_REGISTRY)` /
  `len(ENTRY_POINT_DEFERRED)`, or if a doc is reworded such that the check can no longer even find
  the numbers to compare.
- **What happens to an entry point absent from the registry:** the harness fails
  (**`gts-u6ew.11`**, closed 2026-09-05). `scripts/check_entry_point_extraction.py` extracts every
  UI-handler entry point wired in `src/` — menu `addItem` registrations, `appsscript.json`
  `runFunction` values, CardService actions (`setFunctionName`/`_buildCardAction`),
  `ScriptApp.newTrigger` names, and defined simple triggers — and requires each to be accounted
  for in exactly one of `ENTRY_POINT_REGISTRY` (directly, or via `ENTRY_POINT_SOURCE_ALIASES`
  where the registry key differs from the function name) or `ENTRY_POINT_SOURCE_EXEMPT` (read-only
  / navigation handlers, each with a stated reason). Anything else exits 1; an extraction class
  going empty exits 2, so the check cannot go quiet while `src/` is restructured under it. It runs
  every `test:local` pass via `tests/test_check_entry_point_extraction.py`. Its first run
  registered 11 previously unenumerated state-modifying handlers (registry 37 → 48, deferred
  13 → 24).
- **Residual scope limit:** the `doPost` route class (`payload.action === '…'` in
  `src/WebApp.js`) is **not** extracted — ~60 route names of which the registry holds a chosen
  state-modifying subset, so an extractor there needs a read-only exemption list roughly the size
  of the registry itself: judgement, not extraction. Routes are still hand-authored into the
  registry. Tracked as **`gts-otmu`**.

## 10. Deferred contract observations

| # | Observation | Route to |
|---|-------------|----------|
| 1 | `doc_id`/`doc_name` are derived fields resolved from the Document-column formula (col 7), not stored columns — `scn/contract.DERIVED_FIELDS = frozenset(["doc_id", "doc_name"])`; any contract consumer treating them as plain stored fields will read stale/absent values. | `src/ContractSchema.js` (already modeled — flagging for any future contract consumer that assumes all `SHEET_ACTION_FIELDS` are stored columns). |
| 2 | `test_sync_all`'s `[nv6g]` archive assertion assumed a 24h Doc-Not-Found eviction threshold; `ArchiveManager.js` actually uses a flat 30-day threshold for everything — found during Batch 3 execution (2026-06-18), not yet resolved. | `gts-0f0s` (product decision pending). |

---
_Filled 2026-06-18 (gts-ruoa) from `docs/atdd/archive/atdd-lifecycle.md` §16.8–§16.10 and the as-built `scn/` package._
_Aligned to `test-framework` v1.0.0 (`ADR-0011`, `ADR-0012`) 2026-09-05 on branch `test-framework-upgrade`: §0 repointed, §9a conformance table and §9b entry-point registry added. See `docs/atdd/test-framework-upgrade-plan.md`._
_Stage 1 (`regression-gate`, `gts-u6ew.1`–`.3`) closed 2026-09-05: §9a's `H1`/`H2`/`H13` rows flip to `conformant`; `H4`'s ceiling-declaration mechanism lands (row repointed to `gts-u6ew.14`, still `waived` — the 4 over-budget tests are unconsolidated). See `knowledge-base/staging/test-framework-adoption.md` §Stage 1._
_Stage 4 (`coverage-truth`, `gts-u6ew.15`–`.16`) closed 2026-09-05: §9a's `H9` row flips to `conformant`; `H10` moves off `unknown` to `waived` (instrument built, sweep not run — still not settled). See `knowledge-base/staging/test-framework-adoption.md` §Stage 4._
