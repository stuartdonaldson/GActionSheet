# Staged plan — team portal, sync-read performance, and harness/suite tiering

**Contract:** `$DEVSTANDARD/doc-framework/planning-guide.md` §"Pattern D: Staged Execution".
Beads own all state (AC, `stage:` grouping, `model:`, `human`). This document holds only
sequencing rationale, deliverable previews and handoff notes.

**Status:** Stages 4-9 complete as of 2026-09-02 (agent-launchable orchestration run — `gts-5kyu`, `gts-hztp`*, `gts-p9ra`, `gts-232z`, `gts-h7br`, `gts-d6nz`, `gts-aqpk`, `gts-xvgl`, `gts-e34d`, `gts-9a4j`, `gts-xgms`). Stage 1 `access-resolution` opened 2026-09-02 and remains **blocked, not closed**. Stage 2 `all-teams-view` executed 2026-09-02 and is **not closed** — the code is built, deployed and evidenced; it is waiting on one human look. See the Handoff log. *`gts-hztp` is the one stage-4-9 exception: closed as far as an agent could take it, but left OPEN pending `gts-tz3j` rather than force-closed over an undischarged integrity obligation.
**Next Step:** four, independent of each other.
1. **`gts-zxes`'s Operator check — now unblocked.** `gts-avvl`, the P0 that made the 2026-09-02 gate
   inconclusive, is fixed and deployed to TEST as **v0.2.3.95**. Five minutes, needs a human and
   nothing else. Open <https://nuuc-it.github.io/Static/pub/AS-sit/>, sign in, pick **All teams**.
   Read the *re-run precondition* block at the end of the handoff doc first — the three destroyed
   registrations must be re-tracked, and `Action Sync > Sync` must be run by hand because the
   background trigger is off (`gts-bxa6`). This is the AC-freeze gate; stage 3 cannot be authored
   until it passes.
2. `gts-x1ka` (**P0, ready**) — the `[TST]` twin of `gts-avvl`, unblocked by its close. It carries
   one branch the fix deliberately left uncovered (`_handleMarkDocNotFound`'s zero-Actions-row
   DocData mirror) plus an open GAS-side red-first obligation. It belongs to the neighbour plan's
   `sync-coverage` stage, but it gates this plan's confidence in the gate above.
3. `gts-a37j` (`human`, P1) — provision the verified-identity + Shared-Drive test fixture. It blocks both stage-1 beads and stage 3's *automated* coverage. **Scope correction (2026-09-02):** it blocks the test harness, not a human — see the stage-2 handoff.
4. `gts-tz3j` (**human, P1**) — a decision this session's run surfaced, not a plan stage: an `[IMP]` bead's close-time deploy can make its `[TST]` twin's PROVEN-TO-FAIL obligation undischargeable without violating no-shared-context. Blocks `gts-hztp` closing and, transitively, `gts-dmk5` (stage 6) ever starting.

## In plain language

Between 2026-08-27 and 2026-09-01, 53 new pieces of work landed in the tracker. Most arrived one
at a time, from live incidents rather than from a plan. Three coherent groups inside that intake
already had plans of their own; this document picks up everything else and puts it in an order.

The leftover work falls into four themes. **The team portal** shipped a group-access fix and an
All-teams view that nothing yet proves correct. **Sync reads the Actions spreadsheet far more often
than it needs to**, and a two-step fix for that is half-built. **The test harness produces failures
that are not real**, which makes any full-suite result ambiguous. And **flushed text is missing an
indent** that ADR-0027 requires. Nine stages, in that order, each one session's worth of work.

## Glossary

| Term | Meaning here |
|---|---|
| **Stage** | One session's worth of work: one or more beads sharing files and context. Named, never numbered in a label. |
| **Twin ticket** | The project rule (CLAUDE.md §Testing Strategy) that an `[IMP]` and its `[TST]` are separate beads worked by separate sessions that do not read each other's code. |
| **Operator check** | One cheap manual look, minutes not hours, that answers *did we build the intended thing* — distinct from the regression sweep, which answers *did we break something*. Per ADR-0013, a Spec- or Slice-fidelity look. |
| **Cold read** | An Actions-sheet read paid at the start of a GAS execution because nothing was carried over from the previous one. |

## Why this plan exists

Three bodies of work inside the same intake already have staging documents. **Do not restage them here:**

| Body of work | Stages | Document |
|---|---|---|
| Sync entry points, DocData walk, admin doc-scan | `scan-resumable` → `scan-coverage`, `sync-docdata-walk` → `sync-surface-truth` → `sync-style-conformance` → `sync-harness-truth` → `sync-coverage` | `knowledge-base/staging/sync-alignment.md` |
| Suite composition / ADR-0030 sub-app plugin chain | `plugin-contract` → `deploy-compose` → `gdx-namespace` → `route-registry` → `menu-registry` → `plugin-register` → `test-surface` → `module-decision` | `knowledge-base/staging/suite-composition.md` |
| Measured full sweep, regression flip | `regression-verify` | `knowledge-base/staging/docdata-litter-apt-speed.md` §16 |

**Deliberately out of scope:** the document-export family (`docx-verify`, `document-docs`,
`document-rename`, and `gts-tbs8`), excluded at the owner's instruction. The `suite-composition`
chain still *touches* the exporter (`gts-hcic`, `gts-6zed`, `gts-8xef`) — that is plugin
architecture, not export feature work, and stays in that plan.

`gts-x46z` ([INF] brace-prefixed structured action body as a `custom_fields` alternative) is left
unstaged on purpose: an exploration with no committed consumer belongs in ROADMAP §Funnel for
value/risk evaluation, not in an execution stage.

## Execution order

| # | Stage | Bead | Status | Title |
|---|---|---|---|---|
| 1 | `access-resolution` | `gts-vkui` | ◐ | [TST] Access resolution: parity, single-Directory-call, and cache-staleness coverage |
| 1 | `access-resolution` | `gts-s1j5` | ◐ | [TST] Regression coverage for Shared-Drive-inherited group access resolution |
| 1 | `access-resolution` | `gts-a37j` | ○ | [INF] `human` — Provision the verified-identity test fixtures that gate access-resolution coverage |
| 2 | `all-teams-view` | `gts-zxes` | ◐ | [IMP] All-teams aggregate view + team-access resolution perf fix |
| 3 | `all-teams-coverage` | `gts-lkaa` | ○ | [TST] Regression coverage for All-teams aggregate view + resolver de-dupe |
| 3 | `all-teams-coverage` | `gts-l632` | ○ | [TST] Playwright coverage: All-teams grouped/collapsible view + expand/collapse-all |
| 3 | `all-teams-coverage` | `gts-m8ll` | ○ | [IMP] Instrument `_readTeamDataRows` / spreadsheet-open count so `gts-zxes` AC-4 has a black-box oracle |
| 4 | `actions-snapshot-memo` | `gts-5kyu` | ◐ | [IMP] Stage 1: per-execution Actions-sheet snapshot memo |
| 5 | `actions-snapshot-coverage` | `gts-hztp` | ○ | [TST] Stage 1 snapshot memo: per-execution read-count coverage |
| 6 | `actions-snapshot-persist` | `gts-dmk5` | ○ | [IMP] Stage 2: persist the Actions snapshot across executions (ScriptProperties) |
| 7 | `harness-resilience` | `gts-p9ra` | ✓ | [FIX] run_fixture's opId dedupe cache throws on oversized response (CacheService 100KB cap) |
| 7 | `harness-resilience` | `gts-232z` | ✓ | [FIX] _syncActionRows' internal GAS self-call has no retry on the /exec routing glitch |
| 7 | `harness-resilience` | `gts-h7br` | ✓ | [TST] scn.engine.drain()'s bounded poll only covers Surface.UI, not TRACKER |
| 7 | `harness-resilience` | `gts-d6nz` | ✓ | [INF] pytest session setup: proactively verify test token before full sweep |
| 8 | `suite-tiering` | `gts-aqpk` | ✓ | [INF] Split suite into fast/local and live tiers via pytest markers |
| 8 | `suite-tiering` | `gts-xvgl` | ✓ | [INF] Decide + enable pytest parallelism for the fixture-isolated tier |
| 9 | `rule8-continuation` | `gts-9a4j` | ✓ | [FIX] Flush does not apply ADR-0027 rule 8's 5-space continuation indent |
| 9 | `rule8-continuation` | `gts-xgms` | ✓ | [TST] field-continuation's ACT-12/17/18 carry pre-rule-8 field-label spelling frozen from an old flush |

**Verify:** `bdls --stages` (roll-up) · `bdls --check` (audit) · `bdls --goals --stage <name>`
(one stage in context). Status above mirrors bd; bd is the authority.

## Artifact ownership

Guide §"Deriving stages from beads" step 4 — no two stages own the same artifact. Declared at
**mechanism** granularity, not file: `src/WebApp.js` is a large co-tenanted file, and whole-file
granularity would report overlap between stages that never touch the same lines.

| # | Stage | Artifacts owned |
|---|---|---|
| 1 | `access-resolution` | `tests/test_access_*`, access fixtures — reads `AccessControl.js`, edits none |
| 2 | `all-teams-view` | `AccessControl.js` resolver, `TeamListing.js`, `WebApp.js::_readTeamActions`, `static-portal/src/index.html` |
| 3 | `all-teams-coverage` | `tests/` All-teams scenarios, Playwright All-teams spec, plus `SyncManager.js::_readTeamDataRows` / `TeamListing.js` read instrumentation (`gts-m8ll`, added 2026-09-02 — no other stage claims it) |
| 4 | `actions-snapshot-memo` | the Actions row-read cluster — `TrackerTable.js::_readTrackerSheetRows`, `WebApp.js::_loadRowsForDocUrl` / `_loadExistingRowsByGlobalId` / `_findSheetActionsForDoc`, new `ActionSnapshot.js` |
| 5 | `actions-snapshot-coverage` | `tests/` read-count scenario |
| 6 | `actions-snapshot-persist` | **same cluster as #4**, plus `TriggerManager.js`, `WriteGuard.js` |
| 7 | `harness-resilience` | `tests/helpers/`, `scn/engine.py`, `tests/conftest.py`, `WebApp.js::_syncActionRows` self-call |
| 8 | `suite-tiering` | `pytest.ini` / markers, `tests/conftest.py` collection |
| 9 | `rule8-continuation` | `PortableText.js` flush path, `tests/fixtures/field-continuation*` |

**One declared overlap, deliberate:** stages 4 and 6 own the same mechanism. They are not merged
because stage 6 is *conditional* — it is only worth building if stage 5's measured read count shows
the per-execution win is real, and it may never run. Ownership is strictly sequential and
single-owner, never concurrent. Stage 7's `gts-232z` edits `_syncActionRows`, which stage 4
restructures around; stage 7 is ordered after stages 4–6 so the restructure lands first and
`gts-232z` rebases onto it rather than the reverse.

**On single-bead stages** (2, 4, 5, 6): guide step 5 warns that a plan whose stages each hold one
bead has not found real overlap. Four of nine hold one bead here, and each is a twin-ticket half —
the stage layer is carrying the project's no-shared-context rule, which is a session boundary the
tracker cannot express. Five stages hold two or more beads on genuine artifact overlap.

### GAS-side red-first proofs

CLAUDE.md's Backstop rule requires a new assertion to be shown failing when the condition it
checks is violated. For a Python-side assertion, violate it locally. **For a GAS-side one, a local
revert does not work**: the resolver runs server-side, the suite's deployed-build guard refuses to
run reverted source against an unreverted backend, and the only shared target is TEST. Proven on
stage 1 (2026-09-02) — the guard aborted the run with `expected version='0.2.3.38' ... got
'0.2.3.94'`, and every detecting test skipped rather than failed.

So a GAS-side red-first proof needs its own deployment. `manage-deployments.js --deploy-dev`
(a HEAD push) and `webappDevUrl` exist and are the obvious candidate — **untested for this
purpose**; whether the suite can be pointed at DEV is an open question recorded in `gts-a37j`'s
design field, not a solved one. Until it is answered, a GAS-side Operator check is an
*observation* of the intended behaviour, and the red-first obligation stays open on the bead.

**Second, sharper collision found on `gts-hztp` (2026-09-02):** even a working DEV-deploy path
only solves the shared-infrastructure half of this. `gts-hztp` (the `[TST]` twin of `gts-5kyu`)
needed to construct a build that VIOLATES its own new AC4/AC5 integrity guards to prove them
provable — but by the time it started, `gts-5kyu` had already deployed the guard to shared TEST,
and constructing the violating build requires knowing what to revert, which means reading the
`[IMP]`'s source: the same action no-shared-context forbids. Filed as `gts-tz3j` (`human`, P1) —
a decision on how PROVEN-TO-FAIL is discharged for a live-backend `[TST]` twin is needed before
any future stage's `[TST]` bead hits the same wall. `gts-hztp` stays open, not closed, pending it.

## Stages

### 1 — `access-resolution`

**Deliverable:** ~~the Shared-Drive-inherited group-access fix shipped in `76d1b98` becomes provable~~ — **corrected at handoff (2026-09-02):** the coverage is *authored* but not *provable* in this environment. No Shared-Drive-hosted TeamData folder and no verified-identity fixture exist, so every load-bearing assertion SKIPs. What the stage actually delivered: the full assertion set exists and runs unmodified the moment the fixture is provisioned (`gts-a37j`), plus the one AC that needed neither — `flush_access_cache` — is green with a pasted red proof.
**Why paired:** both are `[TST]` retrofits over the same `AccessControl.js` resolution path; `gts-s1j5`'s Shared-Drive case is one input class of `gts-vkui`'s parity matrix, so splitting them duplicates the fixture. `bdls --check` reports `isolated-stage` — deliberate: nothing blocks this stage and the two beads commute.
**Operator check:** *(revised twice on 2026-09-02 — see §GAS-side red-first)* sign in to the portal in a browser, then read `access.resolve.done` in Axiom for that op: `directoryCalls` must be 1 and `permissionsListCalls` must equal `resourceCount`. **Executable today** — a browser supplies the verified identity. `gts-a37j` blocks the *automated* proof, not this manual look.
**Work-log:** per-stage.

### 2 — `all-teams-view`

**Deliverable:** ~~an operator opening the team portal sees an All-teams aggregate view, and the team-access resolution behind it no longer re-resolves per team~~ — **corrected at handoff (2026-09-02):** the code for both halves shipped in `76d1b98` on 2026-08-30, before this stage opened, and is deployed and serving. What this stage actually delivered is *evidence and a gate*: proof that the ALL branch is live and fails closed, proof from live Axiom data that the per-request de-dupe holds, a static trace of the write path, and a rescoping of who is actually blocked from looking at it.
**Why alone:** implementation half of a twin ticket. This is a perceptual-oracle slice (ADR-0013) — "the grouped view reads correctly" is recognised on sight, not pre-specified — so the AC freezes at this stage's review gate and stage 3 is authored against the frozen contract without reading this code.
**Operator check:** *(revised 2026-09-02 — the original said "signed in as a member of three teams", which read as blocked by `gts-a37j`; it is not. `gts-a37j` blocks the test harness, not a human's own browser.)* Executable today, by a human, in about five minutes — the full script and the four failure signatures are in the stage-2 handoff block below.
**Work-log:** per-stage.

### 3 — `all-teams-coverage`

**Deliverable:** the All-teams view is covered at both levels — server-side (aggregate contents, resolver de-dupe) and browser-side (grouping, expand/collapse-all) — so the durable invariants survive the next resolver change.
**Why paired:** one frozen AC, two surfaces of the same feature, one multi-team fixture. `gts-m8ll` joined 2026-09-02 — `gts-zxes` AC-4 has no black-box oracle, so the instrumentation and the test that reads it belong in one session; modelled as `gts-m8ll` blocks `gts-lkaa`. `bdls --check` still reports `unordered-batch` — deliberate: `gts-l632` commutes with the other two.
**Operator check:** add a second membership row putting one user in the same team twice and re-run the de-dupe assertion — it must go red. This is a *data-side* violation, so no deploy is needed, but it still needs a verified identity: **blocked by `gts-a37j`** until one exists.
**Work-log:** per-stage.

### 4 — `actions-snapshot-memo`

**Deliverable:** a sync execution reads the Actions sheet once instead of once per document.
**Why alone:** `[IMP]` half of a twin ticket. The read-count oracle is specifiable, so stage 5 is written test-first against the contract, in a separate session.
**Operator check:** run one sync over three documents and read the `sheet.read` count in Axiom (`python scripts/query_axiom.py --side gas`). It must be 1, not 3.
**Must not do:** change what the read path returns. This stage removes repeat reads; any behavioural delta is a defect, not an optimisation.
**Work-log:** per-stage.

### 5 — `actions-snapshot-coverage`

**Deliverable:** a regression that fails if the memo is removed or defeated — the read count is asserted, not observed.
**Why alone:** authored against stage 4's contract without reading its implementation. Modelled: `gts-5kyu` blocks `gts-hztp`, `gts-hztp` blocks `gts-dmk5`.
**Operator check:** *(revised 2026-09-02)* read the `sheet.read` count for a three-document sync in Axiom and confirm the test asserts that same number. The red-first proof — memo disabled, count back to 3 — is a GAS-side behaviour change and needs a DEV deploy, not a local delete; see §GAS-side red-first.
**Work-log:** per-stage.

### 6 — `actions-snapshot-persist`

**Deliverable:** the snapshot survives across GAS executions via ScriptProperties, so a trigger-driven or self-rescheduling sync does not pay the cold read on every wake.
**Why alone and last:** conditional on stage 5's measurement. If the per-execution win is smaller than expected, this stage is cancelled rather than started — record that outcome in the bead, do not start on the strength of the design alone.
**Operator check:** let the 30-minute syncAll trigger fire twice and compare `sheet.read` on the second wake against the first in Axiom. The second must show no cold read. **Not executable as written (2026-09-02):** that trigger is currently disabled — `gts-bxa6` must be discharged first, or this check rewritten to drive two sweeps by hand.
**Work-log:** per-stage.

### 7 — `harness-resilience`

**Deliverable:** the four standing false-failure sources in the test harness are gone — an oversized `run_fixture` response no longer throws, a transient `/exec` routing glitch inside `_syncActionRows` retries instead of failing the run, `drain()` bounds the TRACKER surface as well as UI, and an expired-on-the-server test token is caught at session setup rather than mid-sweep.
**Why paired:** all four are harness truth, not product behaviour, and each one makes a green sweep ambiguous. They are the precondition for `gts-u947`'s measured sweep (neighbour plan `docdata-litter-apt-speed.md` §16) being worth running. `bdls --check` reports `isolated-stage` and the beads carry no edges between them — deliberate: they genuinely commute, and the order below is a preference, not a constraint. Suggested order `p9ra` → `232z` → `h7br` → `d6nz`, cheapest verification first.
**Why not earlier, despite gating the sweep:** nothing in stages 1–6 depends on it, and stage 1 is in-flight P1 work. Pulling this forward would stall a P1 to accelerate a sweep that is not scheduled. If a full sweep gets scheduled before stage 6 closes, run this stage first — that is the one condition that reorders the plan.
**Must not do:** change any product code path to make a test pass. Anything that turns out to be a product defect becomes a new `[FIX]` bead (rule 4, do not widen).
**Work-log:** one entry covering the stage.

### 8 — `suite-tiering`

**Deliverable:** `pnpm run test:fast` runs the local tier with no live GAS backend, and a recorded decision on whether the fixture-isolated live tier runs in parallel — with parallelism enabled if the answer is yes.
**Selector correction (2026-09-02, `gts-aqpk` closed):** the marker is `no_live_session`, not a new `fast` — it already existed (`gts-2moy`) and already gates the live pre-flights, so a second marker would only have needed keeping in sync with it. `-m fast` above was a preview, not a contract. Real selectors: `pnpm run test:fast` = `-m "no_live_session and not slow"`, `pnpm run test:local` = `-m no_live_session`, `pnpm run test:live` = `-m live` (auto-derived complement).
**Why paired and why after stage 7:** `gts-xvgl`'s parallelism decision is only answerable once markers exist to name the parallel-safe set, and only measurable once the harness stops producing transient failures that parallelism would be blamed for. Modelled: `gts-aqpk` blocks `gts-xvgl`.
**Operator check:** rename `local.settings.json` aside and run `pnpm run test:fast`. It must pass — anything that fails was mis-marked as local. **Run 2026-09-02: passed, 626 passed / 0 failed / ~28 s.** It failed the first time (626 errors) and that was a real finding, not a mis-marking: two autouse pre-flights took `settings` as a fixture *parameter*, which pytest resolves before the body's `no_live_session` early-return, making `local.settings.json` a precondition of the whole suite. Fixed in `tests/conftest.py`.
**Must not do:** widen into fixture redesign. If parallelism needs shared-fixture changes rather than a flag, stop and label the bead `human` (rule 4).
**Work-log:** per-stage.

### 9 — `rule8-continuation`

**Deliverable:** flushed field continuations carry ADR-0027 rule 8's 5-space indent, and the `field-continuation` fixtures assert that spelling instead of the pre-rule-8 one frozen into ACT-12/17/18.
**Why paired, and why the twin-ticket split does not apply:** `gts-xgms` is a fixture re-baseline, not an independent oracle — the expected files encode the *old* spelling, so the APT lane goes red the moment `gts-9a4j` lands. Splitting them would knowingly leave a red lane between sessions. Modelled: `gts-9a4j` blocks `gts-xgms`.
**Operator check:** flush one field continuation into a live test doc and look at the indent in Google Docs. Five spaces, not the old spelling — read it, do not infer it from the fixture diff.
**Must not do:** re-baseline any fixture whose diff is not explained by rule 8. An unexplained delta is a finding, not a rebaseline.
**Work-log:** per-stage.

## Handoff log

Per-stage handoffs live in `knowledge-base/staging/portal-perf-harness-handoffs.md` (split out
2026-09-02 — nine four-part handoffs do not fit this doc's 300-line cap, and the guide requires
the content). Same notes on the beads via `bd show`.

| Stage | Closed | Outcome |
|---|---|---|
| 1 `access-resolution` | ✗ | Both beads advanced, 18 passed / 21 skipped. Blocked: `gts-a37j` — no verified identity for the *automated* harness. |
| 8 `suite-tiering` (half) | ✗ | `gts-aqpk` closed. Suite partitioned exactly: fast 626 / local 716 / live 421 (716+421 = 1137 = full collection). Fast tier 22 s, proven network-free with sockets blocked and with `local.settings.json` moved aside. `gts-xvgl` unblocked and carries the classification as a bd comment. Stage stays open for `gts-xvgl`. |
| 2 `all-teams-view` | ✗ | No code needed changing — `gts-zxes` shipped complete in `76d1b98`. ALL branch proved live and failing closed; AC-3 evidenced from live Axiom. **Review gate ran 2026-09-02 and is INCONCLUSIVE** — it surfaced a P0 (`gts-avvl`) that destroyed the operator's freshly-tracked docs before any action could render, so AC-1's "every action appears exactly once" was never observable. **`gts-avvl` closed 2026-09-02, deployed v0.2.3.95 — the gate is re-runnable; see the handoff doc's re-run precondition block.** AC-1 still unobserved. |

## Cross-plan notes

- `gts-qsr8` (re-verify the `gts-49u1`/`gts-dige`/`gts-pulj` targeted gates against the rebuilt
  docData/Actions data) joined `regression-verify`, blocked by `gts-u947`: the re-verification is
  only meaningful against the same sweep that flips `regression=pending` → `verified`.
- `gts-cw8t` (`sidebarSetStatus` doc-scan/flush proxy shape) joined `plugin-contract` and is now
  `human`-labelled with acceptance and design fields. It does **not** block `gts-3gw1` — ADR-0030
  explicitly leaves both of its questions open, so writing the ADR does not depend on answering
  them. It does gate `gts-8v8w`'s route table if the answer is "generalized route".
- `gts-gekv` (`human`, filed 2026-09-01) raises that `suite-composition.md` sequences its human
  module-model decision (`gts-ddhb`) *after* six stages that commit to a namespacing and
  composition shape. It blocks `gts-qeis` until answered. That is a defect in the neighbour plan,
  recorded here because this audit found it.

## Change Log

| Date | Change |
|---|---|
| 2026-09-02 | **`gts-xgms` (Stage 9 `rule8-continuation`) closed — stage 9 and the whole stage 4-9 sequence complete.** Chose **de-converge** over annotate: the three records (ACT-212/217/218, not 12/17/18 — the bead title uses the pre-split numbering) were stripped of their frozen preview-link prefix and `(Open)` status and re-authored in plain typed form, so the establishing sync re-renders them and the corpus now carries ONE field-label spelling (`**Name:**`, rule 8) instead of two. Annotate was rejected because the staging deliverable states the fixtures should *assert* the rule-8 spelling, and because de-converging also cleared the stale foreign `docId` those three froze into both corpora. **The de-converge surfaced two silently-vacuous cases** that annotating would have preserved: ACT-217's case 11 ('repeated field name appends in document order') had only ONE `Due:` line in its input, because the old flush had already appended them; ACT-218's case 6 ('a field value's own hyperlink survives round-trip') had no link in its value at all. Both authored preconditions restored — and both passed live on the first run, so the appended-in-order and field-value-link behaviours are now genuinely asserted rather than assumed. Verified: `tests/test_apt_corpus_batch.py` 2/2 green against TEST v0.2.3.99 (277 s), `apt.py lint` clean. `regression=pending` (targeted lane only). **New tech debt filed:** `gts-96yv` — seeding a scenario input corpus from an old flush's output silently vacuates the case its annotation names, and nothing detects it; other corpora need the same record-by-record audit (5 fixture files still carry the hardcoded foreign docId that marks a flush-seeded record). |
| 2026-09-02 | **`gts-9a4j` (Stage 9 `rule8-continuation`) closed.** Was already implemented and once-verified pre-session (v0.2.3.48, 2026-08-29); this close re-verified against the CURRENT TEST deploy (v0.2.3.99, many intervening deploys since) rather than trusting the stale result -- 4/4 green, no regression, the old environmental flake did not recur. doc-trigger-check found 3 real owed updates (CONTEXT.md's Continuation-rendering bullet was stale, asserting a fixed 5-space indent; missing Core Capabilities/Glossary entries for the two new Config keys; OPERATIONS.md had no Config-sheet key reference at all) -- all made. `gts-1h5g`/`gts-3koi` (the other two bugs from the same original investigation) were assumed still-open by the task brief but are already closed under other beads -- confirmed, not touched. **New tech debt filed:** `gts-2ysk` -- Config-sheet key writes (SR Indent/Field SR Indent and future keys) have no structural test-isolation guard, only per-test finally-block discipline; the 2026-08-29 pollution incident is exactly this class of bug and will recur the next time someone forgets the pattern. Suite-wide 2-6x latency drift observed across all 4 tests, not filed as debt -- read as cumulative TEST corpus growth over this long session, already covered by existing purge/eviction mechanisms (gts-4m7l) rather than a new finding. |
| 2026-09-02 | **Stage 8 `suite-tiering` fully complete.** `gts-e34d` closed: root cause was stale test assertions, not a regression -- `document_export/schema.py`'s `SCHEMA_VERSION` was deliberately bumped 3.0->3.1 by `b6d712e` (ADR-0029), which added its own passing 3.1 test but missed two older assertions elsewhere in the same file. GAS-side `DOC_EXPORT_SCHEMA_VERSION` is a separate, deliberately-frozen scheme (ADR-0026 Decision 7) -- untouched. The zero-test placeholder stub (`test_webapp_unrecognized_action.py`) was restored to what its own duration-baseline history and `gts-c7fp`'s close reason showed it was meant to hold -- a direct `_http_post` test of the unrecognized-action fallthrough; the "writes nothing" half is deliberately not re-verified via a sheet-row-count diff (would need a new GAS read route, coupling to the shared mutable TEST sheet) and that gap is documented in the test's own docstring, not left implicit. `pnpm run test:local` 716/716 green, `regression=verified`. |
| 2026-09-02 | **`gts-xvgl` (Stage 8 `suite-tiering`) closed — both halves delivered.** Local tier (716 tests) parallelised: `pytest-xdist>=3.5`, `pnpm run test:local` now `-n 4 --dist worksteal` (1.8x, 65s->36-44s wall); `-n auto`/`-n 12` measured SLOWER than `-n 4` on a 12-core box because every worker independently collects all 1137 tests -- documented as wrong here, not just unneeded. 8 parallel runs diffed against serial by JUnit nodeid->outcome: 0 missing/extra/differing across 716 nodeids each time. The duration-instrumentation prerequisite gts-aqpk flagged was real but the mechanism was worse than assumed -- proven by disabling the gate first: both worker AND controller process report the same test under `-n`, double-counting (132 records for 66 tests) on top of the file-race; fix scopes instrumentation to the controller only (`not hasattr(config, "workerinput")`). Live tier (421 tests): written serial-required decision, not forced -- 4 independent shared-identity blockers found (global `_TEST_*` toggles racing across per-worker session resets, a shared master doc restored at teardown, deliberately cross-session-persisted team/folder discovery caches spanning 19 files so even `--dist loadfile` doesn't help, and script-global `LockService` serializing the actual writes) plus GAS's own lock queue converting any parallelism into timeout flakes -- safe `-n` for live is 1. **Stage flagged not-clean by the implementer despite both planned beads closing:** `gts-e34d` (filed after `gts-aqpk`) makes `pnpm run test:local` red out of the box; recommend closing it before calling stage 8 done. New debt noted, not filed: `test_apt_fixtures_lint.py`'s one runtime-file-creating test is safe under xdist today only because collection is cross-checked before execution -- a future per-file runtime assertion in that style would be a real flake risk. |
| 2026-09-02 | **`gts-aqpk` (Stage 8 `suite-tiering`) closed; stage stays open for `gts-xvgl`.** Chose *one opt-in marker plus an auto-derived complement* over two hand-applied markers and over a directory split: `no_live_session` already existed and already gates the four live pre-flights, so reusing it makes tier selection and pre-flight skipping the same fact; `live` is stamped in `pytest_collection_modifyitems` on everything unmarked, so classification is total by construction and an unmarked new file defaults to the safe (live) tier with nothing to keep in sync. A directory split was rejected as a same-drift-different-shape move that would also have forced a large `git mv` across a tree already carrying nine beads' uncommitted work. **No separate fast-tier conftest was needed** — design question 3 answers itself once the tier is selected by the marker the existing gate already reads. 12 modules promoted to local after an empirical proof (each file run with `socket.socket.connect` patched to raise *and* the marker force-applied, so the probe measured the test body's own need rather than the pre-flight's); `test_apt_corpus_check.py` passed that probe and was still classified live, because it passes only by skipping — it drives a real `ScenarioSession`. Third marker `slow` added as a cost attribute, not a tier, for the one network-free-but-52 s module (`test_document_export_harness.py`, a CLI subprocess per test) so `test:fast` holds a sub-30 s budget without misclassifying it. **Tech debt:** (a) that module is 52 of the local tier's 61 s and is the obvious first `-n` target for `gts-xvgl`, recorded there; (b)/(c) `tests/test_webapp_unrecognized_action.py`'s zero-test placeholder stub and `test_document_export_harness.py`'s 2 pre-existing `schema_version` 3.1-vs-3.0 failures (not actually covered by `gts-vr24`, which is unrelated ACT-migration triage — checked) are real, and now block a clean `test:local` run — filed as **`gts-e34d`**. |
| 2026-09-02 | **Stage 7 `harness-resilience` complete — all 4 beads closed.** `gts-d6nz` closed last: root cause was narrower than the bead's own framing suggested -- not a missing pre-flight probe, but that `_reset_test_state`'s live `FixtureTokenError` was an uncaught exception pytest caches and replays as an identical ERROR on every one of ~635 tests. Fix reuses that fixture's existing live call (zero added round trips) and turns the first failure into one `pytest.exit()` naming `pnpm run deploy:test`. Confirmed `?cmd=version` cannot serve as a token probe -- it is deliberately answered ahead of every auth gate, before `TEST_TOKEN` is even bootstrapped. No GAS-side change. Table above refreshed from bd (was stale, still showing all four as open). Stage's own execution-order table is otherwise not auto-synced from bd -- future stages should treat it as a snapshot, not a live view; `bdls --stages` is the authority. |
| 2026-09-02 | **`gts-h7br` (Stage 7 `harness-resilience`) closed.** Chose the test-local bounded retry (shape 2) over extending `_poll_until_pass`'s engine-level surface gate (shape 1), on a real prior-art finding: `session.py`'s per-`checkpoint()` docx-bytes cache means an engine-level poll would silently re-parse cached bytes instead of re-observing live state -- shape 1 needs a force-refresh mechanism through that shared read closure first, which is out of this bead's scope. Recorded on the bead for any future generalization attempt. Two live re-runs of the originally-failing test passed; the rare race itself (~1/799) was not reproduced, so the retry's own firing was not observed live -- reported as a verification limit, not closed over. `regression=pending`, no GAS deploy needed. |
| 2026-09-02 | **`gts-232z` (Stage 7 `harness-resilience`) closed.** Bounded retry (3 attempts, 1s backoff) added around `_syncActionRows`' self-call, reusing `_fetchDriveWithRetry`'s response-code retry shape (gts-pm72) rather than the exception-based `withGasRetry`. Widened to any non-200, not just 5xx -- the glitch is a routing/redirect artifact, not a REST error family. Both retry-recovers and exhausts-and-logs proven with new tests against a fault-injection fixture. Targeted gate 2/2 green on TEST v0.2.3.99; `regression=pending`. Noted, not filed: 3 near-identical response-code retry shapes now exist in SyncManager.js -- worth generalizing if a 4th self-call site appears, deliberately not done here to keep the fix minimally scoped. |
| 2026-09-02 | **`gts-p9ra` (Stage 7 `harness-resilience`) closed.** Fix was already live in the uncommitted working tree from an earlier sweep; this bead added the missing regression coverage (Path B retroactive, per CLAUDE.md) and verified end-to-end at the `run_fixture` HTTP entry point across all three fixtures the design named as plausibly oversized. Targeted gate 3/3 green on TEST v0.2.3.98; `regression=pending`. Minor gap noted, not filed as a bead: the `fixture.cachePutSkipped` log line itself has never been observed firing live (no deterministic way to force a >100KB response against the current TEST corpus) — verified by code-shape review only. |
| 2026-09-02 | **`gts-hztp` (Stage 5 `actions-snapshot-coverage`) run and left OPEN by design.** AC1/AC2/AC3/AC6 green (6/6 targeted gate) against live TEST. AC4/AC5's PROVEN-TO-FAIL obligation could not be discharged -- `gts-5kyu`'s close-time deploy made the pre-change/unguarded build unreachable without violating no-shared-context. Filed `gts-tz3j` (`human`, P1) -- a general twin-ticket/Backstop collision for this project class, not specific to this bead. `gts-dmk5` (Stage 6) stays correctly blocked; not urgent, it is conditional on Stage 5's measurement anyway. |
| 2026-09-02 | **Stage 4 `actions-snapshot-memo` closed (`gts-5kyu`).** Shipped `src/ActionSnapshot.js` and routed the readers named in the design; most of the routing was already present uncommitted in the working tree and was verified/extended/closed rather than built fresh. AC0-AC3 green with live Axiom evidence (`reads` constant at 2 across docs ranging 1-53). AC4/AC9 reviewed structurally sound but NOT proven-to-fail live -- that obligation stays entirely on `gts-hztp`, whose contract already named every entry point this session left untested. Targeted gate 25/25 green on TEST v0.2.3.97; `regression=pending`. **New tech debt filed:** `gts-d4q9` -- the bundled getValues+getFormulas snapshot regresses a single-read-only caller (`patch_action_status`) by one round trip on a cold miss, which is also why `ArchiveManager.js:95/167` and some whole-sheet WebApp.js readers were deliberately left unrouted despite being named in the design ("expect no gain" undersold a possible net loss). Also created and then closed `gts-lu5t` as a duplicate of `gts-hztp`'s existing AC4-AC6 -- folded its live-incident framing into `gts-hztp` instead of leaving two beads for the same ground. |
| 2026-09-02 | **`gts-avvl` (P0) closed — the stage-2 gate's blocker is cleared.** Restored `ArchiveManager._evictStaleDocData`'s predicate to ("Doc Not Found" AND no Actions row), reverting `gts-30cq`'s widening; ADR-0031's 2026-09-01 amendment already decided the question, so no schema change was needed. Fixed a companion mirror gap in `WebApp.js::_handleMarkDocNotFound` that would have made deleted zero-Actions-row registrations immortal under the restored predicate. Inverted the two assertions that encoded the falsified premise (`test_docdata_orphan_eviction.py`, `test_sync_all.py` cduk AC3). Targeted gate 6/6 green on v0.2.3.95; `regression=pending`. Filed `gts-bxa6` (`human`) for the Background Sync trigger the operator disabled during diagnosis, and corrected stage 6's operator check, which depends on it. |
| 2026-09-02 | **Stage 2 `all-teams-view` executed; not closed, gate pending.** Found the bead's implementation already complete in `76d1b98` — the working-tree diff in its four artifacts belongs to nine other beads. Proved the ALL branch live and failing closed, proved the published portal current with source, and evidenced AC-3's de-dupe from live Axiom data. Corrected stage 2's Deliverable and Operator check. Established that `gts-a37j` blocks the harness, not a human, and that Playwright cannot substitute a captured Google session for it (FedCM). Filed `gts-m8ll` for AC-4's missing black-box oracle and added it to stage 3. |
| 2026-09-01 | Plan authored. Nine stages created from the unstaged half of the 2026-08-27 → 2026-09-01 intake; `stage:`/`model:` labels and ordering edges applied. `gts-qsr8` routed to `regression-verify`, `gts-cw8t` to `plugin-contract`. `gts-hztp` split out of `actions-snapshot-memo` to preserve the twin-ticket split. |
| 2026-09-02 | **Stage 1 `access-resolution` opened and blocked.** `gts-dige` landed mid-stage, making AC-T7's route half green; the rest of both beads' ACs are unrunnable for want of a verified-identity / Shared-Drive fixture. Filed `gts-a37j` (`human`) and wired it as a blocker of both beads. Corrected stage 1's Deliverable line. Recorded that the Operator check as written is not executable, and that the same defect applies to stages 3, 5 and 9. |
| 2026-09-01 | **Audit against staged-plan + planning-guide §Pattern D.** Removed five fabricated `blocks` edges added only to silence `isolated-stage`/`unordered-batch` warnings — they had pushed `gts-232z`, `gts-h7br`, `gts-d6nz` and `gts-s1j5` out of `bd ready`. Preference ordering now lives in the stage blocks, per guide §"Auditing the plan against the tracker". Dropped the `gts-cw8t` → `gts-3gw1` edge (ADR-0030 leaves those questions open by design) and made `gts-cw8t` workable: `human` label, acceptance, design. Filed `gts-gekv`. Added the plain-language summary, glossary, artifact-ownership table, per-stage Operator checks and the Handoff log — all required by the guide and all missing from the first draft. |

## BD References

Regenerate any grouping below from the tracker; this list is a pointer, not a copy.

- Stages owned here: `access-resolution`, `all-teams-view`, `all-teams-coverage`,
  `actions-snapshot-memo`, `actions-snapshot-coverage`, `actions-snapshot-persist`,
  `harness-resilience`, `suite-tiering`, `rule8-continuation`
- Roll-up `bdls --stages` · Audit `bdls --check` · One stage `bdls --goals --stage <name>` ·
  Open owner decisions `bd human list`
- Handoff record: `knowledge-base/staging/portal-perf-harness-handoffs.md`
- Neighbour plans: `knowledge-base/staging/sync-alignment.md`,
  `knowledge-base/staging/suite-composition.md`,
  `knowledge-base/staging/docdata-litter-apt-speed.md`
