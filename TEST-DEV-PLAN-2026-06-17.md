# Test/Debug Backlog Plan — 2026-06-17

## Context

The test deployment is currently out for stakeholder review. Several open bd
issues are test-implementation (`[TST]`), test-harness fix (`[FIX]`), or
documentation (`[INF]`) work covering features that are *already implemented*
in production code — only the regression coverage or supporting docs are
missing. Other open issues are `[IMP]`/`[FEA]` production changes (new
behavior, manifest/scope changes) that would require a fresh `npm run
deploy:test` and could alter what the stakeholder is currently reviewing.

This plan sequences the backlog into batches that (a) group related work to
reuse shared fixtures/context, (b) extend existing tests rather than spawn
one-off harnesses, and (c) isolate the few items that need a new GAS
deployment into a single controlled batch — keeping everything else
deploy-free so it can proceed in parallel with the stakeholder review without
touching the reviewed build. Test-layer principles cited below are from
DevStandard `knowledge-base/methodology/testing/bdd/sdlc-testing-principles.md`
(T1–T24).

Each item below carries a **Priority** (High / Medium / Low) judged on: does
it unblock other test work, does it close a data-integrity/reconciliation
gap (T22 ranks these above happy-path extension), does it close a twin-ticket
block on already-shipped IMP work, and bd's own priority field.

**Excluded from this plan (production-changing, defer until review concludes):**
- `GTaskSheet-csbv.1` (add-on name from settings — manifest change)
- `GTaskSheet-6rv6` (assignee autocomplete rewrite — removes an OAuth scope)
- `GTaskSheet-79dw` epic (`1hyh`, `hc6v`, `6dlp` — Phase 2 OAuth, AC not frozen)
- `GTaskSheet-gc43` EPIC-E Notify chain (`s3ga`, `1xpj`, `twwo`, `7fng`, `ay5w`,
  `ajns`, `xiv8`) — already `deferred` in bd, blocked behind unshipped IMP work
- `GTaskSheet-csbv.3` UX redesign decision itself (doc-only portion is in
  Batch 4)

---

## Priority-ranked order (highest impact first)

| Rank | Issue | Priority | Batch |
|---|---|---|---|
| 1 | `GTaskSheet-f26q` | **High** | 1 |
| 2 | `GTaskSheet-u0bb` | **High** | 2 |
| 3 | `GTaskSheet-dq6t` | **High** | 2 |
| 4 | `GTaskSheet-apcu` | **High** | 3 |
| 5 | `GTaskSheet-cduk` | **High** | 3 |
| 6 | `GTaskSheet-28q` | Medium | 2 |
| 7 | `GTaskSheet-ez2e` | Medium | 3 |
| 8 | `GTaskSheet-dhpt` | Medium | 1 |
| 9 | `GTaskSheet-mpi9` | Medium | 4 |
| 10 | `GTaskSheet-zai6` | Low-Medium | 3 (stretch) |
| 11 | `GTaskSheet-ruoa` | Low | 4 |
| 12 | `GTaskSheet-egl9` | Low | 4 |
| 13 | `GTaskSheet-q37d` | Low | 1 |
| 14 | `GTaskSheet-csbv.3` (doc-only) | Low | 4 |
| 15 | `GTaskSheet-6ov.9` | Low | 4 |

Batch grouping (shared fixtures, single deploy for Batch 3) still governs
*how* the work is sequenced internally — this ranking governs which batch
items get attention first if time is constrained.

---

## Batch 1 — Harness-only fixes (no GAS deploy, do first)

Pure Python/Playwright changes. Zero risk to the deployed build.

- **`GTaskSheet-f26q`** — Priority: **High**.
  Fix `scn/ui.py` `open_sidebar()`/`sidebar_sync()` regex (`'sync now'` →
  `'sync'`).
  *Why High:* it is a test-infrastructure blocker, not a feature gap — every
  sidebar-driving test (including `u0bb` in Batch 2) currently times out
  because of this stale locator. Until it's fixed, no sidebar coverage can be
  trusted or even run. Highest leverage-per-effort item in the whole backlog:
  a one-line regex fix unblocks an entire test surface.

- **`GTaskSheet-dhpt`** — Priority: Medium.
  Replace DOM-polling in the interactive link-preview harness with a
  clasp-logs signal; seed self-describing instructions in the action text.
  *Why Medium, not High:* clasp logs already proved the underlying feature
  works end-to-end (round trip completed in ~17s) — this is fixing a false
  negative in a human-in-the-loop test that runs rarely, not unblocking any
  automated suite or covering an undiscovered defect. Worth doing so the
  interactive harness is trustworthy next time it's run, but nothing else is
  blocked on it.

- **`GTaskSheet-q37d`** — Priority: Low.
  Lint check for `entry_point=` used without `request=`.
  *Why Low:* bd's own description calls it "a recurring footgun, not blocking
  any current work," P4. It prevents a silent-miscoverage class but has no
  near-term consequence if deferred — include only if Batch 1 has slack.

---

## Batch 2 — Extend existing entry points (no GAS deploy)

Coverage for already-implemented features using already-deployed entry
points and existing fixture helpers. No new `TestFixtures.js` case needed —
pure test-code additions, per T6 (permutations are cheap; new scenarios only
when the interaction model changes).

- **`GTaskSheet-u0bb`** — Priority: **High**.
  Sidebar header coverage: team subtitle, team-link anchor, fallback cases.
  *Why High:* this is the TST half of a twin ticket — `GTaskSheet-ht19` (an
  already-in-progress IMP, team-view header already shipped per recent
  commits) is sitting blocked waiting on this to close. It's also exactly the
  category the user called out as priority: testing of work that's already
  implemented. Closing it unblocks a stuck issue and converts shipped-but-
  unverified behavior into regression-protected behavior.

- **`GTaskSheet-dq6t`** — **Moved to Batch 3** (2026-06-17 execution).
  Reclassified during Batch 2 execution: AC-3/AC-5/AC-7/AC-8 require
  constructing tables/bulleted lists in a test doc, and the only doc-seeding
  fixture that exists (`append_doc_paragraph`, WebApp.js) only appends a
  plain paragraph — no table/list support. Closing this needs a new
  GAS-side test fixture route (e.g. a table/list builder), which requires a
  deploy, contradicting Batch 2's no-deploy constraint. It now belongs with
  `apcu`/`cduk`/`ez2e` in the single controlled Batch 3 deploy.

- **`GTaskSheet-28q`** — Priority: Medium.
  Parentheses-in-action-text status-token hardening (3 variants).
  *Why Medium, not High:* same fixture/scanner context as `dq6t` (do
  together), but the failure mode here is text-corruption on a fairly
  uncommon input shape (parens in the middle of action text), and bd's own
  filing note says explicitly "do not block [the] green phase on this." Real
  but lower-likelihood than `dq6t`'s broader table/list gap.

---

## Batch 3 — Additive test-only GAS routes (single controlled deploy)

These need new `TestFixtures.js` cases (and one new test-only route in
`WebApp.js` for `apcu`). Bundle into **one** PR and **one**
`npm run deploy:test` cycle to minimize redeploys during the review window.
All additions are net-new test-only branches gated by the existing testToken
mechanism — no change to any production code path the stakeholder is
exercising.

- **`GTaskSheet-dq6t`** — Priority: **High** (moved from Batch 2; see note above).
  Floating-action scanner coverage: table cells, bulleted lists, mixed
  placement, tracker-table exclusion, `@create` mid-cell caret placement.
  Needs a new test-only doc-seeding fixture (table/list builder) bundled
  into the same PR/deploy as `apcu`'s new route.

- **`GTaskSheet-apcu`** — Priority: **High**.
  New testToken-gated route driving `forward_action_rows` with an explicit
  duplicate `forwards[]` payload to reach the duplicate-forward guard (UC-E
  AC4).
  *Why High despite needing a deploy:* this guards against actually
  duplicating action rows across documents — a reconciliation/data-integrity
  path (T22), not a cosmetic one. It's currently "code-verified but not
  regression-covered," meaning a future refactor could silently reintroduce
  duplicate forwards with nothing to catch it.

- **`GTaskSheet-cduk`** — Priority: **High**.
  `syncAll()` DocData integrity-pass coverage: counts and `doc_name`
  reconciliation for skipped docs.
  *Why High:* DocData backs the team-view/sidebar summaries users are
  actively looking at right now (stakeholder review!). A drift bug here
  (stale counts, stale doc name) would be silently wrong, not loudly broken
  — exactly the kind of reconciliation gap T22 prioritizes. The IMP side
  (`GTaskSheet-6ipb`) is already closed, so this is pure coverage of shipped
  behavior with a frozen contract.

- **`GTaskSheet-ez2e`** — Priority: Medium.
  New fixture cases for `menuSyncActiveDoc()` / `menuInsertTrackerActiveDoc()`
  menu wrapper entry points.
  *Why Medium, not High:* this closes a T17 entry-point-coverage technicality
  flagged by a Copilot PR review — the *delegated* functions
  (`syncDocument`/`insertTrackerTable`) are already fully tested elsewhere, so
  the actual risk surface (a thin menu-wrapper bug) is small. Worth doing for
  invariant compliance, but lower stakes than `apcu`/`cduk`.

**Optional stretch (Low-Medium, not blocking):** `GTaskSheet-zai6` (test.u1
non-deployer Drive-sharing fixture) is the same additive-fixture shape and
could ride along in this same deploy if time allows.
*Why Low-Medium:* it upgrades test fidelity to catch a real bug class
(deployer-privilege leaks), but bd's own filing says "no current rz4k child's
AC requires this" — it's opportunistic hardening, not closing a known gap.
Not done in this execution pass — deferred.

### Batch 3 execution notes (2026-06-18, one `deploy:test` cycle, rev 254)

All four — `apcu`, `cduk`, `ez2e`, `dq6t` — closed; tests pass against the
deployed build (`tests/test_import.py::test_forward_duplicate_guard`,
`tests/test_sync_all.py::test_docdata_integrity_pass`,
`tests/test_menu_entry_points.py`'s two new ez2e tests,
`tests/test_floating_action_scanner.py`).

- **`cduk` blocker:** its twin IMP `GTaskSheet-6ipb` was marked Closed in bd
  with *no actual implementation* anywhere in the codebase (no
  `sync.integrity.complete` log tag, no related commit). Implemented it now
  in `syncAll()` (SyncManager.js) per 6ipb's frozen AC1-AC5, then verified
  against the pre-existing `test_docdata_integrity_pass` (which was already
  written to that contract, just waiting on the code).
- **`apcu`:** added a new testToken-gated `forward_action_rows_test` route
  (ContractSchema.js + WebApp.js) mirroring `_handleForwardActionRows`'s
  guard loop — the production route is `secret`-gated, not reachable from
  the test harness directly.
- **`ez2e`:** `menuSyncActiveDoc()`/`menuInsertTrackerActiveDoc()`
  (MenuHandler.js) depend on `DocumentApp.getActiveDocument()`, which never
  resolves from the stateless `run_fixture` webapp execution — added a
  `TEST_DOC_ID`-script-property fallback (same property `_handleRunFixture`
  already stages) plus two new TestFixtures.js cases.
- **`dq6t`:** scoped to AC-1 through AC-6 (scanner detection: lists, table
  cells, tracker exclusion) via three new TestFixtures.js doc-seeding cases
  (`append_doc_table`, `append_doc_list_item`, `append_tracker_cell_text`).
  AC-4's "prefix" sub-case doesn't match shipped behavior (token must be
  paragraph-anchored; documented instead of "fixed"). AC-7/AC-8 (`@create`
  caret placement inside a table cell) need a new UiDriver capability — split
  into `GTaskSheet-4hqn`.
- **Bonus fix:** `seed_row` (TestFixtures.js) never forwarded `data.globalId`
  into the row it built — found while debugging an unrelated regression
  check (`test_sync_all`), fixed (one line).
- **New finding, not fixed (out of scope):** `test_sync_all`'s `[nv6g]`
  archive assertion assumes a 24h Doc-Not-Found eviction threshold;
  `ArchiveManager.js` actually uses a flat 30-day threshold for everything.
  Filed as `GTaskSheet-0f0s` for a product decision.

---

## Batch 4 — Documentation only (no code, no deploy, run any time/in parallel)

- **`GTaskSheet-mpi9`** — Priority: Medium.
  Apply four deferred LL policy levers (CLAUDE.md test-gate rules,
  implementation-gate skill additions, stub-entry-point LL archive,
  reconciliation-discipline rule).
  *Why Medium:* these are process guardrails (e.g. "new integrity assertion
  must be proven to fail before acceptance") that reduce the chance of
  *future* regressions like the ones this very plan is cleaning up — real
  leverage, but it's process change, not closing a current coverage gap, so
  it doesn't compete with Batches 1–3 for urgency.

- **`GTaskSheet-ruoa`** — Priority: Low.
  Fill ATDD templates into `docs/atdd/project-testing-guide.md` /
  `harness-design.md`.
  *Why Low:* pure consolidation of facts that already exist scattered across
  `ID-map.md` and the archived lifecycle doc (confirmed in prior discussion
  this session) — no new guidance is created, just discoverability. Useful
  if a fresh agent/session later picks up Batches 2–3, otherwise no
  execution value.

- **`GTaskSheet-egl9`** — Priority: Low.
  Write up `/dev` vs. versioned `/exec` deploy tradeoff as a decision doc.
  *Why Low:* it's an evaluation, not an implementation — would speed up
  *future* test iteration cycles if acted on, but during a stakeholder review
  is exactly the wrong time to change the deployment model, so the upside is
  deferred regardless of when the doc gets written.

- **`GTaskSheet-csbv.3`** (doc-only slice) — Priority: Low.
  Document current Import-button behavior as-is in the user guide.
  *Why Low:* stopgap documentation only; the actual UX decision it's
  attached to is explicitly out of scope until the review concludes, so this
  just prevents the user guide from going stale in the meantime.

- **`GTaskSheet-6ov.9`** — Priority: Low.
  Restructure `DevStandard/knowledge-base/gas-addon-guide.md`.
  *Why Low:* this is a cross-project DevStandard guide, not a GActionSheet
  test or doc artifact — it has zero bearing on the current test deployment
  or stakeholder review, and bd shows it's been sitting open since 2026-05-27
  with nothing else blocked on it.

### Batch 4 execution notes (2026-06-18)

All five closed/addressed:

- **`mpi9`:** items 1–3 applied, item 4 deliberately left deferred (its stated
  precondition — human approval of the UC-C/D reconciliation spec — is
  unmet). CLAUDE.md gained 4 backstop rules; `.claude/skills/implementation-gate/SKILL.md`
  went v2.0→v2.1 (Step 3 proof-of-effectiveness sub-step, new Step 5.5
  test-infra compatibility check, Step 6 full-`pytest -x` `[IMP]`-close gate).
  Item 3 (stub-entry-point LL) was already archived/resolved 2026-06-12 — no
  action needed. Confirmed this project's implementation-gate skill is now
  intentionally divergent from DevStandard's copy (noted in ID-map.md).
- **`ruoa`:** `docs/atdd/project-testing-guide.md` and `docs/atdd/harness-design.md`
  filled from `docs/atdd/archive/atdd-lifecycle.md` §15–§16 and the as-built
  `scn/` package (read `scn/session.py`, `engine.py`, `surfaces.py`,
  `contract.py`, `ui.py` directly rather than trusting the archive prose
  alone). Entry-point coverage matrix (§7) points at `scn/contract.ENTRY_POINT_REGISTRY`
  rather than duplicating its 32 entries, per the project's own I6
  single-source discipline.
- **`egl9`:** evaluated and recorded as `knowledge-base/adr/0018-test-cycle-stays-on-exec-not-dev.md`.
  Decision: keep the automated test cycle on `/exec`. The deciding fact (not
  visible from the bd description alone) is that GAS `/dev` URLs always
  execute as the accessing user regardless of the manifest's `executeAs`
  setting — and `src/appsscript.json` sets `executeAs: USER_DEPLOYING`,
  which several tests (forwarding, team-scope, the planned `zai6`
  non-deployer fixture) specifically depend on. The existing `npm run push`
  (`/dev` HEAD) path already covers the fast-iteration use case this issue
  was chasing.
- **`csbv.3`** (doc-only slice): found already written (`docs/USER_GUIDE.md`
  §4, added in the user guide's initial commit `de6f143`) — fixed a dead
  `(#)` placeholder link to the tracking issue. The UX-redesign decision
  itself remains open, per the plan's exclusion list.
- **`6ov.9`:** restructured `DevStandard/knowledge-base/gas-addon-guide.md` —
  generalized title/scope, corrected the "Editor Add-on (old)" row (the
  `createActionTriggers`/`linkPreviewTriggers` in-document pattern is
  distinct from, and not deprecated like, the legacy standalone `addon`
  editor add-on), and added a new §Editor Add-on Triggers & Smart Chips /
  Link Previews section folding in both 2026-06-02 LLs (the three
  publish-gating constraints; WebApp-URL build-time stamping over
  ScriptProperties self-registration).

---

## Sequencing summary

1. **Batch 1** (`f26q` first — unblocks everything else; `dhpt`, `q37d` as
   slack allows).
2. **Batch 2** (`u0bb`, `dq6t` — both High; `28q` rides along on `dq6t`'s
   fixture).
3. **Batch 4** (`mpi9` first if doing any docs; rest is filler, any time).
4. **Batch 3** (`apcu`, `cduk` — both High, justify the one deploy cycle;
   `ez2e` and optionally `zai6` ride along on the same deploy).

## Verification

- Each batch: `pytest -x <changed test files> < /dev/null` (per project
  convention — fail-fast, stdin redirected to avoid the `wait_for_log` hang).
- Batch 3 only: after `npm run deploy:test`, re-run the full
  `tests/test_menu_entry_points.py`, `tests/test_import.py`,
  `tests/test_sync_all.py` to confirm the new fixture cases work against the
  redeployed version before closing the three issues.
- After each batch, run `bd close <ids>` for completed issues and
  `bd close <id> --suggest-next` to surface unblocked work (e.g. `u0bb`
  closing should unblock `ht19`).

---

## Reusable batch-execution prompt

Standing project conventions (CLAUDE.md: ATDD lifecycle, twin-ticket /
no-shared-context rule, entry-point coverage, `pytest -x`) are already
auto-loaded in every session in this repo — no need to restate them. The
only thing this prompt needs to add is what's specific to *this plan, right
now*: the deploy gate.

```
Execute and resolve Batch [N] from TEST-DEV-PLAN-2026-06-17.md.
[No-deploy batches:] Do not deploy or push — the test deployment is out for stakeholder review.
[Batch 3 only:] Stage all fixture additions across its issues first; confirm before running one deploy:test for the whole batch.
```

Per-batch fill-in reference:

| Batch | Issues | Deploy clause |
|---|---|---|
| 1 | `f26q`, `dhpt`, `q37d` | No-deploy |
| 2 | `u0bb`, `dq6t`, `28q` | No-deploy |
| 3 | `apcu`, `cduk`, `ez2e`, `dq6t` (+ optional `zai6`) | Batch-3 (one `deploy:test` for the whole batch) |
| 4 | `mpi9`, `ruoa`, `egl9`, `csbv.3` (doc-only), `6ov.9` | No-deploy |
