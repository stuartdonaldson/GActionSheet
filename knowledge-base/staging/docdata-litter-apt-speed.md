# Staged plan — DocData litter, and APT for regression speed

**Contract:** `$DEVSTANDARD/doc-framework/planning-guide.md` §"Pattern D: Staged Execution".
Beads own all state (AC, grouping, model, human decisions). This document holds only
sequencing rationale, deliverable previews and handoff notes.

## Why this plan exists

A read-only pull of the live TEST spreadsheet on 2026-08-29 found `DocData` holding **303 rows,
every one written that same day** (earliest `Last Sync Time` 01:35). Three separate defects and
one harness leak are visible in that snapshot:

| Evidence | Cause |
|---|---|
| 139 rows carry a live `=HYPERLINK(...)` Doc Name; **147 carry plain text** | `ArchiveManager._evictStaleDocData` (`src/ArchiveManager.js:203-226`) reads with `getValues()` and writes back with `setValues()`, so every surviving row's formula is flattened to its display text. `_archiveActionsRows` 80 lines above does the `getFormulas()` merge correctly and carries a comment warning about this exact hazard. |
| **17 rows have a blank Doc Name**, 13 of them unrepairable | `syncAll`'s integrity backstop (`src/SyncManager.js:731-739`) derives the name only from the Actions `document_formula`. 27 Actions rows seeded by the `seed_row` fixture (`src/TestFixtures.js:3538`) have an empty Document column, so the row is minted with `docName: ''` — then made permanent by `WebApp.js:1423` and `WebApp.js:1763`, which both propagate `existing.docName` with no fallback. |
| **41 rows have no Actions row at all**; 38 have a blank syncStatus; 22 still advertise a non-zero Action Count | Eviction requires `syncStatus === 'Doc Not Found'` *and* no Actions rows (`ArchiveManager.js:213`). Anything orphaned by another route is immortal. |
| **28 `GActionSheet-Test-session-*` Docs alive in Drive** since 2026-06-11 | `end_test_session` trashes the clone, but there is no finalizer backstop like `ScenarioSession.new_doc()`'s (`scn/session.py:556`), so any run that dies before teardown leaks the file. |

The plain-text degradation cannot be legacy: the HYPERLINK write landed 2026-07-01 (`0c2ace3`) and
every row in the snapshot was written after it.

**A sibling defect, same failure shape, different sheet.** A 2026-08-30 read of the team-actions
webapp (TestTeamA) surfaced 3 rows whose `action_id` is the bare malformed string `AI-ACT-1` /
`AI-ACT-3` / `AI-ACT-7` — not a `docId/ACT-N` or legacy `docId/AI-N` global_id, but a raw,
unparseable string being displayed verbatim. Traced to `parseGlobalId()` (`WebApp.js:1097`): on a
match failure it silently returns the *raw input string* as `actionId` instead of logging or
rejecting it, so a `global_id` written once in a malformed state (most likely by a mid-refactor
TEST deployment on 2026-08-26, the same day the ACT-N centralization refactor — `gts-mmyc` —
closed with `regression=pending`, never verified end-to-end) displays forever with zero
diagnostic trail. Every current write site is provably single-prefix-safe as of HEAD, so it is not
reproducible against today's code — but exactly like the flattened Doc Name and the sticky blank
name above, nothing detects or repairs a bad value that already made it into a sheet. Filed as
`gts-2226`/`gts-5jrn` (guard + regression test) and `gts-rzgv` (cleanup of the specific stale rows,
seeded by `tests/test_team_portal_hardening.py`'s `seeded_rows` fixture) — folded into this plan as
stage `actions-token-guard` and `litter-purge` respectively (see Stage 0 and the execution-order
table below).

**No test can see the first defect.** `tests/test_sync_all.py:690` does assert on `docName` after the
integrity pass, but reads through `get_docdata_row` → `_readDocDataRow` → `getValues()`, which returns
identical display text for a formula and a string. The assertion is structurally blind.

The second half of the plan attacks the volume itself. 236 of the day's 303 rows are
`GActionSheet-Test-journey-*` — one Google Doc created, synced and trashed per assertion. Measured
per-test cost (allure history):

| shape | cost |
|---|---|
| one doc per case (`test_floating_action_scanner`) | 37.6 s / assertion |
| one doc per scenario (`test_apt_corpus_check`) | 26.6 s / scenario |
| batched APT lane (`test_apt_flush_lane`) | ~72 s for 5 scenarios — **marginal scenario ≈ 0** |

`tests/support/apt_lane_runner.py` already implements the batched shape, and `act-retire` already
migrated scanner AC-1/2/3/5 into `list-and-table-containers.apt.txt`. This plan finishes that
migration for the cases that have a specifiable oracle, and states which cases must *not* move.

**Do not run the full `pytest -x` sweep on your own initiative** (project CLAUDE.md, Backstop rules).
Every `[FIX]`/`[TST]` stage here closes on a targeted gate with `regression=pending`; stage
`regression-verify` is the single authorised full sweep.

## Stage 0 — beads to file

**Confirmed and filed 2026-08-30.** All 13 beads below were created with dependencies wired per
the execution-order table (docdata-oracle → docdata-repair → docdata-eviction → litter-purge;
harness-leaks parallel to the docdata chain but also a prerequisite of litter-purge;
apt-batch-limits → {apt-corpus-batching, apt-scanner-migration} → apt-format-migration;
regression-verify depends on litter-purge, apt-corpus-batching, apt-scanner-migration and
apt-format-migration). See the execution-order table for bead IDs.

*Amended 2026-08-31:* stages 11–15 are inserted ahead of `regression-verify`. Only
`lane-idempotency` (`gts-5ktl`) needed a new bead; the rest sequence beads that already existed.
`flush-lane-retire`'s `gts-crae` was already wired as a blocker of `gts-u947` on 2026-08-30 and
keeps that edge — it moved stage, not dependency.

Two kinds of stage, deliberately wired differently:

- **Hard blockers of `gts-u947`** — stages 12, 13 and 15. Each changes *what the sweep runs*
  (`flush-lane-retire` removes five docs; `lane-idempotency` adds an assertion to 21 scenarios) or
  *whether its result means anything* (`red-clearance`). Wired as `blocks: gts-u947` in the tracker.
- **Bookkeeping, not gating** — stages 11 and 14. Closing an already-discharged bead and retitling a
  bead to its real residual scope do not change a single test. They should complete alongside, and
  the plan is not finished while they are outstanding, but they must not hold the sweep hostage.
  Carried as `stage:` labels only.

**Three more filed 2026-08-30, later the same day**, after the sibling Actions-sheet defect above
was found: `gts-2226` (`[FIX]`), `gts-5jrn` (`[TST]`, blocks `gts-2226` per the twin-ticket rule),
and `gts-rzgv` (`[TST]`/chore, `discovered-from:gts-2226`). Wired in as a new stage
`actions-token-guard` (parallel to `harness-leaks`, also a prerequisite of `litter-purge`), with
`gts-rzgv`'s cleanup folded into `litter-purge`'s scope alongside `gts-dgw8`.

**One more filed 2026-08-31**, from the open-`[TST]` triage that produced stages 11–15 (below):
`gts-5ktl` (`[TST]`, P1, `blocks: gts-u947`) — the `run_lane` second-capture change that stage
`lane-idempotency` exists to deliver. It is the only *new* bead the triage produced; stages 11, 12,
14 and 15 sequence beads that already existed and were sitting unsequenced.

| Prefix | Title | Scope | Model |
|---|---|---|---|
| `[TST]` | Lane runner: second no-op sync capture, so every batched lane asserts idempotency (`gts-5ktl`) | One extra sync + capture per *lane*, diffed per scenario slice against the first capture. Closes the structural gap stages 9 and 10 both had to strand their idempotency assertions on. | opus |

| Prefix | Proposed title | Scope | Model |
|---|---|---|---|
| `[TST]` | DocData Doc Name oracle: shape and presence | A read path that can distinguish a HYPERLINK formula from its display text (`getFormulas()` through `get_docdata_row`), plus an assertion that every synced doc's Doc Name is non-blank. Proven to fail against today's sheet before acceptance. | opus |
| `[FIX]` | `_evictStaleDocData` flattens the Doc Name HYPERLINK | Mirror `_archiveActionsRows`' `getFormulas()`/`getValues()` merge in the DocData compaction path. | sonnet |
| `[FIX]` | Blank Doc Name is sticky and never backfilled | Stop propagating `''` from `WebApp.js:1423`/`1763`; give the integrity pass a real-title fallback when the Actions formula carries none. | opus |
| `[FIX]` | DocData eviction cannot reach non-`Doc Not Found` orphans | Widen the predicate to "no Actions row references this docId", keeping the existing 24h gate. | opus |
| `[TST]` | DocData lifecycle entry-point audit (Path B) | Enumerate every writer — syncAll integrity pass, `sync_action_rows`, `mark_doc_not_found`, `_syncTeamScope`, `ArchiveManager.archive`, `set_docdata_row` — and verify each appears as a call-site with observable state verification. | opus |
| `[FIX]` | `seed_row` writes Actions rows with an empty Document column | The production scanner never does; the fixture manufactures a state that then poisons the integrity pass. Supply a formula, or make the blank path an explicit, asserted case. | sonnet |
| `[FIX]` | `end_test_session` leaks its clone when a run dies before teardown | Add the finalizer backstop `new_doc()` already has. 28 Docs leaked since 2026-06-11. | sonnet |
| `[FIX]` | `parseGlobalId` silently returns garbage instead of flagging a malformed dual-prefix `global_id` (`gts-2226`) | On a match failure, log instead of returning the raw input verbatim; guard `_handleUpsertActionRows` against writing a malformed `global_id` through undetected. | opus |
| `[TST]` | Malformed dual-prefix `global_id` is logged, not silently accepted (`gts-5jrn`) | Twin of `gts-2226`, Path B retroactive coverage — a malformed-`global_id` docState row logs once and a normal row does not (negative control); `parseGlobalId('AI-ACT-1')` logs and returns a safe fallback. | opus |
| `[INF]` | One-shot cleanup of the TEST spreadsheet and Drive | 41 orphan DocData rows, 147 degraded plain-text names, 17 blanks, 27 Document-less Actions rows, 599 aged `Doc Not Found` rows, 28 leaked Drive Docs, 3 malformed `AI-ACT-N` Actions rows (`gts-rzgv`, in `GActionSheet-Test-journey-20260827-b309`). Re-stamp names only after the writers are fixed. | opus |
| `[INF]` | APT batching scale limits | Decide and document two constraints before batches grow: `AI-N` token-namespace allocation across composed scenarios, and the v2 rule that a body-level table must be the doc's last content (caps a batch at one table scenario, hand-ordered today in `test_apt_create_lane`). | opus |
| `[TST]` | Batch the six un-batched `test_apt_corpus_check` scenarios | Route them through `apt_lane_runner.run_lane`. The runner already exists; this is the cheapest win and it validates the constraint decisions. | sonnet |
| `[TST]` | Migrate `test_floating_action_scanner`'s grammar cases to APT | 18 `new_doc` sites of "seed a paragraph shape, sync, assert the row". Entry-point-bound cases stay. | opus |
| `[TST]` | Migrate the inline-formatting family to APT | `test_inline_formatting`, `test_hyperlink_preservation`, `test_status_token_parens`, `test_continuation_indent_config`, `test_ai_n_token`. | opus |
| `[INF]` | Measured full sweep: verify the speed and coverage claims | The single authorised `pytest -x`. Records wall-clock and journey-doc count before/after, and flips every `regression=pending` bead in this plan to `verified`. | opus |

Existing beads folded in rather than duplicated:

- **`gts-46qv`** (open, P3, *"DocData sheet's Doc Name column is a HYPERLINK to the document"*) shipped
  on 2026-07-01 but is only half-true while eviction flattens it. It closes in stage `docdata-repair`.
- **`gts-3koi`** (`decodeAptToRequests` never inserts the flush status icon) and **`gts-1ej4`**
  (converge `scn/surfaces.py` DocReader onto the `doc_inspect` oracle) are owned by the existing
  `apt-oracle.md` plan. Both are external prerequisites of the migration stages, not beads of this one.

## Execution-order table

*(populated at bead creation — Status mirrors the tracker, which stays the authority)*

| # | Stage | Bead | Status | Title |
|---|---|---|---|---|
| 1 | `docdata-oracle` | `gts-axll` | ✅ | DocData Doc Name oracle: shape and presence |
| 2 | `docdata-repair` | `gts-t9f9`, `gts-pz8o` | ✅ | Eviction flattens the HYPERLINK · sticky blank name · `gts-46qv` |
| 3 | `docdata-eviction` | `gts-30cq` ✅, `gts-qjnf` ✅ | ✅ | Orphan eviction predicate · DocData entry-point audit |
| 4 | `harness-leaks` | `gts-zj60`, `gts-z55w` | ✅ | `seed_row` Document column · `end_test_session` clone leak |
| 5 | `actions-token-guard` | `gts-2226` ✅, `gts-5jrn` ✅ | ✅ | `parseGlobalId` malformed-token guard · its regression twin |
| 6 | `litter-purge` | `gts-dgw8` ✅, `gts-rzgv` ✅ | ✅ | One-shot TEST spreadsheet and Drive cleanup, incl. `AI-ACT-N` rows |
| 7 | `apt-batch-limits` | `gts-i8we` | ✅ | APT batching scale limits |
| 8 | `apt-corpus-batching` | `gts-ph35` | ✅ | Batch the six un-batched corpus-check scenarios |
| 9 | `apt-scanner-migration` | `gts-oaw1` | ✅ | Migrate the scanner's grammar cases to APT |
| 10 | `apt-format-migration` | `gts-dxz9` | ✅ | Migrate the inline-formatting family to APT |
| 11 | `tst-litter-close` | `gts-95wl`, `gts-jxnw`, `gts-76pp`, `gts-sx60` | ✅ | Close four `[TST]`/`[FIX]` beads whose deliverable already exists in the tree |
| 12 | `flush-lane-retire` | `gts-crae` | ✅ | Retire `test_field_continuation_flush` EP1/2/3/4/7, superseded by `test_apt_flush_lane` |
| 13 | `lane-idempotency` | `gts-5ktl` | ✅ | Second no-op sync capture in `run_lane`, so every batched lane asserts idempotency |
| 14 | `act-fields-closeout` | `gts-ucdz`, `gts-tz5x`, `gts-82s2`, `gts-thwh`, `gts-nrxn` | ✅ | Close or narrow the five ACT-fields `[TST]` beads to their true residual scope |
| 15 | `red-clearance` | `gts-mtw0` ✅, `gts-6pws` ✅, `gts-i0gk`+`gts-mt39`+`gts-ogev` ✅, `gts-lu5k` ✅, `gts-85x3.4` ✅, `gts-1h5g`+`gts-ttns`+`gts-guux` ✅ | ✅ | Clear the standing reds so the sweep measures the suite, not known failures. All clusters and mechanical items closed 2026-09-01 (see stage 15 below) |
| 16 | `regression-verify` | `gts-u947` | ◐ | Measured full sweep (document-export family excluded); flip `regression=pending` → `verified` |
| 16 | `regression-verify` | `gts-qsr8` | ○ | Re-verify the `gts-49u1`/`gts-dige`/`gts-pulj` targeted gates against the rebuilt docData/Actions data (blocked by `gts-u947`) |

**Verify:** `bdls --stages` · `bdls --check` · `bdls --goals --stage <name>`

## Stages

### 1 — docdata-oracle

**Deliverable:** a test that fails red against the live sheet today, distinguishing a HYPERLINK Doc
Name from its flattened display text — the discrimination no current assertion can make.

**Why alone:** it is the whole point of the first half. Ordering is oracle-driven and this oracle is
specifiable (a formula string vs. a value string), so it is test-first without qualification. Pairing
it with its own fix would let the fix define the assertion.

**Work-log:** per-stage.

**Closed 2026-08-30 (gts-axll).** Added `get_all_docdata_rows` (src/TestFixtures.js) —
returns every DocData row's Doc Name as both `docName` (getValues() display text) and
`docNameFormula` (getFormulas() raw formula), ignoring `testDocId` (whole-sheet audit,
not a per-doc lookup). `tests/test_docdata_docname_oracle.py` asserts every row's Doc
Name is a live `=HYPERLINK(...)` formula and non-blank. Deployed to TEST (v0.2.3.49) and
run: **fails red** with 166 flattened rows (up from the 2026-08-29 snapshot's 147; no
blanks flagged in this pass). `regression=pending` — targeted gate only, per Backstop
rules. Stage 2 (`docdata-repair`, `gts-t9f9`/`gts-pz8o`) turns this green.

### 2 — docdata-repair

**Deliverable:** Doc Name survives an eviction sweep as a link, and a blank name repairs itself on
the next sync instead of becoming permanent. Closes `gts-46qv` for real.

**Why paired:** both beads are writers of the same column, and both are read-modify-write bugs about
the same value. One session holds the whole Doc Name write path in context.

**Must not do:** touch the eviction *predicate* — that is stage 3, and mixing the two makes the
stage-1 assertion ambiguous about which fix turned it green.

**Work-log:** per-stage.

**Closed 2026-08-30 (gts-t9f9, gts-pz8o, gts-46qv).** `_evictStaleDocData`
(`src/ArchiveManager.js`) now mirrors `_archiveActionsRows`' `getFormulas()`/`getValues()` merge —
a kept row's cell value is its formula when one exists, so eviction no longer flattens every
surviving row's HYPERLINK on each compaction sweep. `SyncManager.js`'s integrity pass now falls
back to `driveMetadata[docId].name` (the real Drive title, already fetched that sweep) before the
sticky `existingRow.docName` when the Actions formula carries no title; `WebApp.js:1423`
(`sync_action_rows`) only reuses `dcExisting.docName` when it is non-blank, else uses the request's
own `docTitle`. `WebApp.js:1763` (`mark_doc_not_found`) is unchanged by design — no real title is
obtainable for a doc that's unreachable. Deployed to TEST (v0.2.3.50). Targeted gate
`tests/test_sync_all.py::test_sync_all` **PASSED**. `regression=pending` on both beads, per
Backstop rules.

**Stage 1's oracle (`gts-axll`) is still red** against the live sheet — 166 rows were already
flattened by prior eviction sweeps *before* this fix landed, and a row with no formula left in the
cell has nothing to preserve; today's fix only stops the bleeding going forward. Repairing those
already-corrupted rows is explicitly stage 6's job (`litter-purge`, `gts-dgw8`, "re-stamp names
only after the writers are fixed") — `gts-dgw8` already depends on both beads closed here, so the
dependency graph has this right even though the oracle doesn't go green until stage 6 runs.

### 3 — docdata-eviction

**Deliverable:** an orphaned DocData row is reachable by eviction regardless of how it was orphaned,
and every DocData writer is a named call-site in a test.

**Why paired:** the Path B entry-point audit has to enumerate the writers anyway; the eviction fix is
the one that changes what the audit must assert about lifetime. Same file, same sweep.

**Ordering:** after stage 2 — both change `ArchiveManager._evictStaleDocData`, and sequencing them
avoids a conflict in one function.

**Work-log:** per-stage.

**`gts-30cq` closed 2026-08-30.** `_evictStaleDocData` (`src/ArchiveManager.js`) now evicts any
DocData row with no Actions row referencing its docId, regardless of syncStatus — widened from
`syncStatus === 'Doc Not Found' && !activeDocIds[fileId]` to just `!activeDocIds[fileId]`. The 24h
gate is unchanged and still inherited from `_archiveActionsRows`' own 24h-gated sweep (a real
docId's Actions rows can only disappear via that sweep or explicit test/admin action — never on a
faster clock), so no new aging field was needed on DocData itself.

New targeted test `tests/test_docdata_orphan_eviction.py` seeds a synthetic orphan (blank
syncStatus, non-zero actionCount, no referencing Actions row) and asserts one archive sweep evicts
it — confirmed red against the narrow predicate (temporarily reverted, redeployed, reran) before
confirming green against the fix, satisfying the "proven to fail" Backstop rule. Deployed to TEST
across v0.2.3.51–53.

A full-file diagnostic run (`test_sync_all.py` + `test_archive.py`, 12 items, run once as extra
confirmation beyond the narrow gate — see the retrospective note below) surfaced 4 failures. 3 were
traced to causes unrelated to this fix: `test_sync_all_exhausted_drive_5xx_retry_still_recovers_via_fallback`
passed clean on an isolated rerun; `test_mark_doc_not_found_no_restamp_on_reconfirm` and
`test_sync_all_op_propagates_to_webapp` were traced to a missing-retry pattern in two `collect_logs`
call sites racing Axiom ingestion lag (confirmed directly — the "missing" log entry existed in
Axiom, just hadn't landed by query time) and filed as `gts-6pws` rather than reworked here. The 4th,
`test_sync_all_integrity_and_listing_miss_batch`'s `[cduk AC3]`, was a real and expected consequence:
that pre-existing test seeded a synthetic orphan (via `set_docdata_row`) and asserted it *survived*
a sweep — exactly the immortal-orphan bug this stage fixes. Updated to assert eviction instead,
reran, green.

**Process note for later stages:** the full-file diagnostic run cost ~22 minutes against ~30s for
the narrow test alone. In hindsight the change was analytically safe as a strict predicate widening
(every row the old code evicted still satisfies the new condition; survival is still gated on a
live Actions reference, untouched by this change) — the narrow test plus that argument would have
been sufficient per the project's Backstop rules ("whatever runs in well under a couple minutes"),
and did in fact surface the one real regression (`[cduk AC3]`) on its own once written correctly.
The broader run was still useful *this time* (it surfaced `gts-6pws`), but stage `docdata-eviction`
(`gts-qjnf`, next) should default to narrow/targeted verification and reserve a full-file run for
cases with a real logical reason to doubt a narrow test's coverage.

**`gts-qjnf` closed 2026-08-30.** Enumerated all six named DocData writers and confirmed each is a
named call-site with a durable-state assertion on the DocData row itself (not just the Actions
sheet it usually accompanies):

| Writer | Call site | Durable-state coverage |
|---|---|---|
| `syncAll` integrity pass (`SyncManager.js:796`) | `sync_all_force_listing_miss` sweep | `tests/test_sync_all.py` `[cduk AC1/AC2]` (actionCount/resolvedCount/docName) + `[r3d syncAll sweep1]` |
| `sync_action_rows` (`WebApp.js:1421`) | `_syncActionRows`'s `UrlFetchApp` POST, fired by every `syncDocument()`/`scn.sync()` | **Gap found and closed**: `tests/test_b7_write_routes.py`'s `[rz4k.2 sync_action_rows]` only asserted the Actions row; the `gts-pz8o` blank-docName fallback at this call site had no DocData-level assertion of its own (existing `[cduk AC2]` coverage reaches `WebApp.js:1421` only transitively through a `syncAll` sweep, tagged to that entry point instead). New `tests/test_docdata_sync_action_rows_backfill.py` seeds a blank `docName`, calls `scn.sync()` directly (no `syncAll` involved), and asserts the backfill — confirmed green against TEST (v deployed at audit time). |
| `mark_doc_not_found` (`WebApp.js:1765`) | `_markDocNotFound`, batched once per sweep (`gts-kkm7.1`) | `tests/test_sync_all.py` `[grxl mark_doc_not_found]` / `[zc21]` (DocData mirrors `Doc Not Found` + Team Id) |
| `_syncTeamScope` (`SyncManager.js:3051`) | called from `syncDocument()` before the `sync_action_rows` POST | `tests/test_team_scope.py` S3/S7/S9 (`DocData.team_id`/`sync_status` durable checks via `_docdata_row`) |
| `ArchiveManager.archive` (`_evictStaleDocData`) | `archive_journey` fixture / 30-min trigger | `tests/test_archive.py`, `tests/test_docdata_orphan_eviction.py` (`gts-30cq`), `tests/test_sync_all.py` `[cduk AC3]` |
| `set_docdata_row` (`TestFixtures.js:2981`, harness-only) | `_post_fixture("set_docdata_row", ...)` | `tests/test_sync_all.py:643` and `tests/test_docdata_orphan_eviction.py` both assert the seeded row lands before exercising the writer under test — the fixture's own write is durable-state-checked, not just trusted |

The one real gap — `sync_action_rows`'s own DocData backfill had no entry-point-tagged durable
assertion — is now closed rather than merely documented, since this bead's AC required every writer
to be a named call-site with coverage, not just an inventory. No other writer needed a new test.
`regression=pending` (targeted gate only, per Backstop rules) — the new test file is itself the
targeted gate and ran green.

### 4 — harness-leaks

**Deliverable:** the test harness stops manufacturing states production cannot reach, and stops
leaking Drive files on a crashed run.

**Why paired:** both are harness-teardown/seeding defects, neither touches `src/` production sync
code. Deliberately isolated from stages 1–3 so a harness change never explains away a production fix.

**Work-log:** per-stage.

**Closed 2026-08-30 (gts-zj60, gts-z55w).**

- **`gts-zj60`:** `seed_row` (`src/TestFixtures.js`) now defaults an unset `documentFormula` to the
  dispatcher's own `docFormula` (the test doc's HYPERLINK, already computed once per invocation) —
  matching the production scanner's shape — instead of `''`. A caller can still opt into the blank
  shape as a named case by passing `documentFormula: ''` explicitly. New
  `tests/test_seed_row_document_default.py` asserts both paths via `find_sheet_actions`, which
  derives `doc_id`/`doc_name` from the same formula and always excludes a row with a blank one.
  Proven red against the deployed v0.2.3.55 (default case only visible via find_sheet_actions after
  the fix), green against v0.2.3.56. No regression: `tests/test_team_listing.py` (7/7, its 8 blank-
  Document call sites are the ones this bead targets) and `test_sync_all.py`'s two seed_row callers
  with explicit `documentFormula` (green in isolation; a shared-backend Axiom-log false-positive when
  run together, unrelated to this change — same class as the `gts-6pws` note in stage 3).
- **`gts-z55w`:** `test_doc_id` (`tests/conftest.py`) now registers its clone-trash teardown via
  `request.addfinalizer`, mirroring `ScenarioSession.new_doc()`'s `_deferred_trash` backstop
  (idempotent, swallows its own POST failure). New `tests/test_conftest_test_doc_id_finalizer.py`
  (pure Python unit test, no live GAS) drives the fixture to `yield` against a fake `request`, then
  invokes the registered finalizer *without* resuming the generator — proving the trash call is
  reachable independent of generator resumption, i.e. survives a run that dies before pytest's normal
  teardown would reach it. Proven red against the prior signature (`TypeError: test_doc_id() takes 1
  positional argument but 2 were given` — no `request` param, no finalizer registered), green against
  the fix.

Both `regression=pending` (targeted gates only, per Backstop rules).

### 5 — actions-token-guard

**Deliverable:** a malformed dual-prefix `global_id` (e.g. `AI-ACT-1`) is logged the moment it would
be written or parsed, instead of silently round-tripping as an unparseable string with no diagnostic
trail — closing the same class of gap as stage 2's flattened HYPERLINK and sticky blank name, but on
the Actions sheet's `global_id` rather than DocData's Doc Name.

**Why paired:** `gts-2226` (the guard) and `gts-5jrn` (its regression twin) are a single twin-ticket
pair — Path B retroactive coverage, since the underlying write-time defect predates this stage and
isn't reproducible against current code (see "A sibling defect" above). One session holds the whole
`parseGlobalId`/`_handleUpsertActionRows` contract.

**Must not do:** attempt to repair the 3 already-malformed rows here — that is deletion/cleanup, not
a guard, and belongs to stage 6 (`litter-purge`) via `gts-rzgv`.

**Why parallel to `harness-leaks`, not sequenced after it:** same shape as stage 4 — a production-code
guard fix that shares no file with the DocData chain (stages 1–3) or with `harness-leaks`'s test-side
fixtures (`seed_row`, `end_test_session`). Independent sessions can run stages 4 and 5 in either order.

**Work-log:** per-stage.

**Closed 2026-08-30 (gts-2226, gts-5jrn).** `parseGlobalId` (`src/WebApp.js`) now logs
`sync.globalId.malformed` (with the offending value) from its regex-fallback branch instead of
silently returning the raw string as `actionId`. `_handleUpsertActionRows` parses each row's
`globalId` once up front and skips (never inserts or updates) any row whose parse fails
(`isNaN(parsed.N)`) — the `actionId`/`docId` derived from that one parse are reused for both the
update and insert branches, replacing the separate `_extractActionId`/`parseGlobalId` calls so a
malformed value is logged exactly once per upsert call, not twice.

New `tests/test_actions_malformed_globalid_guard.py`: case 1 posts `upsert_action_rows` with a
malformed `'AI-ACT-<N>'` globalId (no docId) and asserts `inserted=0`/`updated=0`, no sheet row,
and exactly one `sync.globalId.malformed` log entry correlated to the call's own `opId` — proven
red against TEST v0.2.3.57 (pre-fix: silently `inserted=1`), green against v0.2.3.58 (the fix).
Case 2 is the negative control: a well-formed `docId/ACT-N` globalId in the same request shape
inserts normally and fires no malformed-token log. Design case 3 (parseGlobalId's fallback
returns a safe, non-crashing shape) is folded into case 1 — no direct GAS unit-invocation of a
bare function exists in this harness, so it's proven via the webapp responding cleanly
(`inserted: 0, updated: 0`, no error) rather than throwing.

Regression: `tests/test_b7_write_routes.py` (6/6, exercises the same `_handleUpsertActionRows`
insert/update branches from a different angle) green against the fix. `regression=pending` on
both beads, per Backstop rules — full sweep deferred to stage `regression-verify`.

**Must-not-do held:** the 3 already-malformed `AI-ACT-N` rows in
`GActionSheet-Test-journey-20260827-b309` were not touched here — that cleanup is `gts-rzgv`,
stage `litter-purge`, which now has both its dependencies (`gts-2226`/`gts-5jrn`, and stages 2–4)
closed.

### 6 — litter-purge

**Deliverable:** a clean TEST spreadsheet and Drive, with the counts before and after pasted into the
handoff. Now also covers the 3 malformed `AI-ACT-N` rows in
`GActionSheet-Test-journey-20260827-b309` (`gts-rzgv`) — first confirm whether
`test_team_portal_hardening.py`'s `seeded_rows` fixture recreates a fresh doc each run (safe to
delete outright) or reuses a fixed one (clean before the next run adds more).

**Why alone:** this is the plan's only deletion. Batching anti-pairing — nothing that reads these rows
runs in the same session. It is also the one stage that must come *after* every cause is fixed, or the
litter simply re-accumulates on the next sweep.

**Ordering:** hard prerequisite on stages 2, 3, 4 and 5.

**Work-log:** per-stage.

**Closed 2026-08-30 (gts-dgw8, gts-rzgv), deployed v0.2.3.60.** Real live-sheet counts diverged
from the 2026-08-29 snapshot in both directions (some categories had already partly self-healed
via ongoing sessions + stages 2–5's fixes; Drive leakage was worse than estimated, since no prior
audit had ever actually enumerated it). Three new fixtures added to `src/TestFixtures.js` to make
this pass possible at all — no lister/dumper existed before:

- `dump_all_action_rows` — whole-Actions-sheet audit (read-only), same shape as `gts-axll`'s
  `get_all_docdata_rows`: both `getValues()` and `getFormulas()` for the Document column.
- `list_test_drive_docs` — enumerates Drive files beside the TEST sheet matching the harness's own
  naming (`GActionSheet-Test-session-*` / `GActionSheet-Test-journey-*`); read-only.
- `restamp_docdata_names` — the actual repair. `SyncManager.js:792`'s own integrity pass only
  rewrites Doc Name when `computedName !== existingRow.docName`, which is **false** for an
  already-flattened row (the display text is unchanged, only the formula wrapper is gone) — so a
  normal sync sweep can never self-heal this class of damage. This fixture rewrites just the Doc
  Name cell to a fresh `HYPERLINK`, using the row's own existing text + fileId — the same
  construction `_getOrUpsertDocDataRow` already uses, just targeted at an existing row instead of
  a fresh upsert.

| Category | 2026-08-29 snapshot | Live before this pass | After |
|---|---|---|---|
| DocData rows (total) | — | 180 | 76 |
| Orphan DocData rows | 41 | 6 | 0 (evicted as a side effect of archiving Actions rows below) |
| Degraded (flattened) Doc Names | 147 | 109 | 0 (75 repaired directly by `restamp_docdata_names`; the rest belonged to rows the archive sweep evicted first) |
| Blank Doc Name | 17 | 1 | 0 |
| Actions rows (total) | — | 472 | 252 |
| `Doc Not Found` Actions rows | 599 | 220 | 0 (159 backdated+archived via the existing `purge_stale_test_docs` fixture, now effective because stage 3 fixed the eviction predicate it feeds) |
| Document-less Actions rows | 27 | 30 | **30, deliberately untouched** — see below |
| Leaked live Drive test docs | 28 (since 06-11) | 86 (dating to 06-10 — the true figure; nothing had audited this before) | 0, all trashed via the existing `trash_doc` fixture |
| Malformed `AI-ACT-N` rows | 3 (specific `...-b309` doc) | 1 (`AI-ACT-835511`, a different, generic-titled row) | 0 |

**`gts-rzgv` closed without action.** The `...-b309` doc was already trashed (absent from
`list_test_drive_docs`'s live listing) and its 3 `AI-ACT-1/3/7` rows were already gone from Actions
— prior `purge_stale_test_docs` runs since 2026-08-27 had already swept them via the normal
`Doc Not Found` aging path. A different stray malformed row (`AI-ACT-835511`, predating today's
`gts-2226` guard deploy) was found instead and cleared incidentally by the same archive sweep.

**Deliberately not touched — the 30 Document-less Actions rows.** These span 19 fileIds and dates
from 2024-01-01 to 2026-08-27. At least one 2026-08-27 cluster looks like it could be
`test_seed_row_document_default.py`'s own intentional opt-in blank-Document case (`gts-zj60`:
"a caller can still opt into the blank shape as a named case by passing `documentFormula: ''`").
Deleting indiscriminately risked breaking that regression test; deleting nothing left real litter
(the 2024-01-01 row predates this project's current conventions entirely) — this needs per-fileId
triage, not a blanket sweep. Filed as `gts-kne5`, not folded into this stage.

**Verification:** targeted gate `tests/test_docdata_docname_oracle.py` (the stage-1 oracle, red
since 2026-08-30) **PASSED** — every live DocData Doc Name is now a live `HYPERLINK`, none blank.
A broader diagnostic run (`test_docdata_orphan_eviction.py` + `test_archive.py` + `test_sync_all.py`,
12 items, run as extra confirmation beyond the narrow gate) surfaced 4 failures, all the identical
`gts-6pws` signature (`tests/helpers/sync_coverage.py:79`, "no `sync.scanned` log entry found" —
Axiom ingestion lag, already filed 2026-08-30 during an unrelated stage) — unrelated to anything
this stage touched. `regression=pending` on `gts-dgw8` per Backstop rules; the full authorised
sweep is stage `regression-verify` (`gts-u947`).

### 7 — apt-batch-limits

**Deliverable:** a written answer to "how many scenarios can share one composed doc, and what breaks
first" — the constraint every migration stage below inherits.

**Why alone, and why first:** the two known limits (token-namespace collision, table-must-be-last) are
invisible at five scenarios and load-bearing at thirty. Deciding them after the migrations means
redoing the migrations.

**External prerequisites:** `gts-3koi` and `gts-1ej4` (`apt-oracle.md`). A presentation assertion
cannot round-trip while decode omits the status icon, and migrating tests onto APT while two doc
parsers disagree just relocates the divergence.

**Work-log:** per-stage.

**Closed 2026-08-30 (gts-i8we), docs-only — no deploy/gate needed.** Both constraints were
already enforced or observable in existing code/tests, not previously written down anywhere a
future batch author would find them. Documented in
`docs/interfaces/action-portable-text.md` §"Batch scale limits (gts-i8we)" (new subsection,
between "Batched lanes" and "Tooling design decisions"):

1. **Table position** — `apt_lib.compose_corpora` already raises if a body-level `<TABLE...>`
   corpus isn't last, which also means at most one table-bearing scenario per batch (two can never
   both be "last"). Decision: every batch call must sort its scenario list explicitly (never rely
   on glob/alphabetical order, per `test_apt_create_lane.py`'s existing precedent) and cap at one
   table scenario per `run_lane` call; a second table shape goes in a separate batch/doc.
2. **`AI-N`/`ACT-N` token allocation** — scoped per batch (per shared doc), not per project, since
   `sheetEdit`/`trigger` address a record via a doc-scoped `global_id`. Decision: hand-pick a
   `<block><index>` convention per batch (already the unwritten practice — `apt-lanes-flush` uses
   `10<entry-point>`, `apt-lanes-create` uses `2<scenario><filler>`), documented in each batch's own
   scenario-triple prose annotation. No shared registry; a collision surfaces immediately as a
   wrong-row assertion failure or an obvious duplicate at PR review, not silently. Bare `AI:`
   triggers need no coordination — `maxN+1` assignment plus positional N-normalisation in the diff
   (decision 5) means the literal resolved number is never asserted.

**External prerequisites still open:** `gts-3koi` and `gts-1ej4` remain unresolved — this stage's
own deliverable (the batching policy) did not require them, since it decides *how tokens/tables
are allocated*, not *what a decoded/rendered doc looks like*. Stages 8–10 (which actually migrate
and assert presentation-bearing corpora) still inherit the blocking reasoning above and should not
start ahead of those two beads closing.

#### `gts-1ej4` closed 2026-08-30

`scn/surfaces.py`'s `DocReader` now derives its records from
`tests/helpers/doc_inspect.py`'s `floating_actions()` (the ADR-0027 grammar oracle) instead of its
own second, weaker parser — no more `w:t`-only text extraction (soft returns and continuation
lines were invisible), no more unscoped status-token scan, and the empty-body-drop bug is fixed:
an `ACT-9:  (Open)` style header-only-no-body action is now returned instead of silently dropped.
Zero shape/vocab change to the `ai` records the live `scn/` suite consumes —
`assignee_source` stays `'chip'`/`'parsed'`/`None` (mapped from doc_inspect's `'chip'`/`'text'`/`None`),
and a bare `AI:`/`ACT:` trigger or an unparseable paragraph (both `token is None` in doc_inspect's
output) are excluded, matching what the old regex-based parser already never matched.
`tests/test_scn_surfaces.py`'s `DocReader` fixture builder (`_make_docx_bytes`) now goes through
`tests/helpers/docx_build.py` instead of maintaining its own duplicate OOXML-building code.

Verified via a **targeted gate only** (Backstop rules — full sweep deferred to stage
`regression-verify`): `tests/test_scn_surfaces.py` 26/26; `tests/test_doc_oracle_parser.py` +
`tests/test_expect_parse_annotation.py` 27/27 (both exercise `doc_inspect.floating_actions`
directly, confirming the shared module took no regression); plus a direct repro proving the
empty-body ACT-9 case now returns 1 record (`action_id='ACT-9'`, `status='Open'`) instead of 0.
`regression=pending` on `gts-1ej4` per Backstop rules.

#### `gts-3koi` closed 2026-08-30

`decodeAptIntoDoc` (`src/PortableText.js`) now inserts the flush-shaped status icon for every
established action it decodes, mirroring `_buildFlushRequests`' `getStatusIconUrl`/
`insertInlineImage` request ordering (`[image][token][text]`, each inserted at the same offset so
later inserts push earlier ones right). Status is extracted from each header line via the same
last-paren-group rule `_extractStatusTokenTracked` (`src/SyncManager.js`) already uses, so decode
and a live rescan agree on what counts as a status token. Deployed to TEST through v0.2.3.62.

New `tests/test_decode_status_icon.py` asserts a fresh `materialize_reference_corpus()` doc
(decode-only, no force flush) shows `has_status_icon=True` on every established record — **PASSED**.
Verified via a **targeted gate only** (Backstop rules — full sweep deferred to stage
`regression-verify`): `tests/test_reference_corpus_fixture.py` (4/4) +
`tests/test_decode_status_icon.py` (1/1), 5/5 green. No re-flush of the shared canonical
`referenceDocId` was required. `regression=pending` on `gts-3koi` per Backstop rules.

**Both external prerequisites of stage `apt-batch-limits` are now closed** — `gts-1ej4` and
`gts-3koi`. Stages 8–10 are unblocked to start.

### 8 — apt-corpus-batching

**Deliverable:** six scenarios that each pay a doc creation today pay one between them — the first
measured drop, and a live check of stage 7's constraints against real corpora.

**Why alone:** it is the cheapest possible test of the batching decision. If a constraint is wrong,
it is wrong here, before two large migrations are built on it.

**Work-log:** batched with stage 9.

**Closed 2026-08-30 (gts-ph35).** New `tests/test_apt_corpus_batch.py` routes
dual-prefix / field-continuation / grammar-matrix / hyperlink-roundtrip /
list-and-table-containers / unparseable-reporting through
`apt_lane_runner.run_lane`, each tagged `"batch": "apt-corpus-batch"` so
`test_apt_corpus_check.py`'s existing skip logic stops running them one-Doc-
per-scenario.

**Live check of stage 7's constraints found a real, previously invisible one.**
The token-namespace-collision constraint gts-i8we documented (§"Batch scale
limits") was correct but this stage's six corpora — each authored
independently, one per its own single-scenario doc — had never been checked
against it: `ACT-11` appeared in three of the six files, `ACT-9`/`AI-10`/`ACT-3`
in two each. Composing all six into one doc and syncing once triggered the
duplicate-N reconciliation flush path across unrelated records, corrupting
content (a `Notes` field silently dropped, prose reclassified) — confirmed by
reproducing the corruption red, then green after renumbering. Every input +
expected corpus pair was renumbered onto its own hundreds-block (dual-prefix
100s, field-continuation 200s, grammar-matrix 300s, hyperlink-roundtrip 400s,
list-and-table-containers 500s; unparseable-reporting's `ACT-77` was already
unique and left untouched) — the "hand-pick a block convention" decision
gts-i8we already made, applied for the first time to corpora that were never
built with batching in mind. `list-and-table-containers` (the only file with a
body-level table) is explicitly ordered last in the composed batch, mirroring
`test_apt_create_lane.py`'s existing precedent for the same v2 restriction.

**Measured drop:** `tests/test_apt_corpus_batch.py` PASSED live against TEST
twice in a row, ~103s and ~80s for all 6 scenarios — down from the un-batched
shape's measured 5.1 min for 7 scenarios (docstring, `apt_lane_runner.py`).
Verified via a **targeted gate only** (Backstop rules — full sweep deferred to
stage `regression-verify`): the new test file (2/2) plus offline
`test_apt_fixtures_lint.py` + `test_apt_scenario_format.py` + `test_apt_differ.py`
+ `test_apt_lane_lib.py` + `test_apt_cli.py` (202 items), confirming the
renumbering broke no lint/format/differ invariant. `regression=pending` on
`gts-ph35` per Backstop rules.

### 9 — apt-scanner-migration

**Deliverable:** `test_floating_action_scanner`'s grammar cases run from checked-in corpora instead of
18 per-case documents.

**Must not do:** move the entry-point-bound cases. The coverage invariant requires the call site
itself, and `test_field_continuation_flush` EP5/EP6 already sets the precedent for what stays behind.
Anything ambiguous becomes a bead, not a judgement call in flight.

**Work-log:** batched with stage 8.

**Closed 2026-08-31 (gts-oaw1).** 15 of the file's 18 `new_doc` sites migrated onto 5 new
checked-in APT corpora, run through a new batched lane
(`tests/test_apt_scanner_lane.py`, `batch: "apt-lanes-scanner"`, mirroring stage `apt-lanes`'
`run_lane` shape): `scanner-table-cell` (AC-4 suffix/prefix, one table scenario, ordered last per
the table-position constraint), `scanner-soft-return` (AC-T1–T4), `scanner-jxrw` (gts-jxrw's two
cases plus gts-v0py's case, folded into the same corpus — a lone already-established record with
nothing else in its own file would trip the degenerate-scenario lint, gts-5st5), and
`unparseable-reporting` extended with gts-xvlu's Cases 2/3 (reused a second time under this
stage's own batch tag, `unparseable-reporting-verify.scenario.json`, so a live
`verify_consistency` call — not just the text-diff round trip stage `apt-corpus-batching` already
runs — could be asserted against the same open `scn`). `scanner-ogev` carries only gts-ogev's
independent text-email regression guard; see below for why the rest of that bead stayed put. One
of gts-jxrw's two original cases (`test_jxrw_bare_token_alone_yields_empty_action_text`) needed no
new corpus at all — `grammar-matrix.apt.txt` Case 7 (stage `apt-corpus-batching`) already covers
the identical shape and cites `gts-jxrw` by name; retired with a citation instead of duplicated.

Two lookup-based extra assertions ride the same `run_lane`-opened `scn` after its establishing
sync, layered on top of the plain text-diff (extending the pattern `run_lane`'s own callers
already use for pass/fail reporting to also read live state): gts-xvlu's `verify_consistency`
counts/issue-message check, and gts-ogev's `find_sheet_actions()` field check. This is the
mechanism that made two field-level (not text-diff-expressible) originals migratable at all.

**3 sites deliberately NOT moved:**
- `test_tracker_table_tokens_excluded` (AC-6) — `docs/interfaces/action-portable-text.md`
  §"List items and table cells (v2)" states outright that tracker-table exclusion is scanner
  behaviour, not an APT concern; there is no construct for "this table is the tracker" to
  round-trip against.
- `test_soft_return_survives_sidebar_status_flush` (gts-dr8j) — exercises flush entry point 6
  (`sidebar_set_status`), which the same doc's §"Batched lanes" explicitly carves out as staying
  covered by its existing UI-driven test; a sheet edit never reaches that call site.
- `test_ogev_soft_return_person_chip_matches_fast_path` (gts-ogev) — live during this stage, a
  PERSON chip placed on a soft-return continuation line (not a paragraph's first physical line)
  turned out not to be reproducible through `decodeAptIntoDoc` at all (the chip vanishes; the
  resulting sheet row's assignee comes back `None`). Filed **gts-i0gk** (P2) rather than resolved
  in flight, since it's ambiguous whether the gap is in `decodeAptIntoDoc` or in APT's own
  chip-placement assumption. **Found while verifying this decision, unrelated to it:** re-running
  the ORIGINAL, unmodified test (its own construction path — `insertPerson` directly, not
  `decodeAptIntoDoc`) against live TEST (v0.2.3.64) **also fails the same way** — `soft_row.assignee`
  is `None` there too. This is a pre-existing regression this stage's targeted gate happened to
  surface, not one it caused; not fixed here (no `src/` changes are in this stage's scope). Left
  red, documented on gts-i0gk, and reported rather than worked around, per the project's Backstop
  rules on known test failures.

**Verification (targeted gate, per Backstop rules — full sweep deferred to `regression-verify`):**
`tests/test_apt_scanner_lane.py` 2/2 green against TEST v0.2.3.64. Together with
`tests/test_floating_action_scanner.py`'s 3 remaining tests: 2/3 green
(tracker-table exclusion, sidebar-flush round trip); the 3rd (gts-ogev PERSON-chip parity) red as
documented above, pre-existing and out of scope. `regression=pending` on `gts-oaw1`.

**Next stages must know:** `apt-format-migration` (stage 10) inherits the same
`_normalize_n`/annotation-escaping lessons this stage re-learned the hard way — a hand-authored
golden for a bare-trigger record must use the record's REAL assigned N when the token isn't at the
record's start (`_normalize_n` only strips a *leading* `ACT-`/`AI-` token and the `ain=` URL
param; a mid-record token's literal digits are compared as-is), and any literal `_` in hand-typed
annotation prose needs an explicit `\_` escape or the round trip reports a spurious presentational
diff.

### 10 — apt-format-migration

**Deliverable:** the inline-formatting family runs from corpora.

**Why NOT batched with stage 9:** batching anti-pairing — two instances of the same conversion never
share a session. Stage 9's handoff is the input to this one.

**Known ceiling:** APT v1 cannot represent bold or italic covering only *part* of a link's width, so
some of `test_inline_formatting` cannot move. Name what stays and why, in the handoff.

**Work-log:** per-stage.

**Closed 2026-08-31 (gts-dxz9), deployed v0.2.3.65.** Two new checked-in corpora,
`tests/fixtures/inline-formatting.apt.txt` (2 cases) and
`tests/fixtures/status-token-parens.apt.txt` (3 cases), batched through a new
lane `tests/test_apt_format_lane.py` (`batch: "apt-lanes-format"`, mirroring
stage `apt-scanner-migration`'s shape). Both corpora are the degenerate
`mutation: {"kind": "sync"}` case, authored statusless so the establishing
sync's flush is the path under test (same reasoning `hyperlink-roundtrip.apt.txt`
already used).

**Migrated, with citation in the retired test file:**
- `test_inline_formatting.py`'s two base bold/italic scan->sheet->flush->rescan
  round trips (with and without an assignee chip) → `inline-formatting.apt.txt`
  Cases 1/2.
- `test_hyperlink_preservation.py`'s cases 1 (link mid action text) and 2
  (link-only action, ADR-0027 rule 12) → **already covered**, no new corpus:
  both were already present in `hyperlink-roundtrip.apt.txt` (stage
  `apt-corpus-batching`, gts-ph35, predating this stage). The test functions
  retired with a citation to that existing corpus instead.
- `test_status_token_parens.py`'s all 3 cases (mid-text parens no-status,
  mid-text parens with trailing status, ambiguous trailing-only parens) →
  `status-token-parens.apt.txt` Cases 1/2/3. This file now carries no test
  functions of its own.

**Deliberately NOT migrated** (named per this bead's AC), each cited inline
in its own file:
- Every idempotency assertion (a second, no-op `scn.sync()` compared against
  the first) across `test_inline_formatting.py` and
  `test_hyperlink_preservation.py` — at the time, `apt_lane_runner.run_lane`
  produced one capture per lane run, not a before/after pair to diff against
  each other, so no corpus-shaped equivalent existed without a runner change.
  **Superseded 2026-08-31 by stage 13 (`lane-idempotency`, gts-5ktl):** the
  runner change was made, and the idempotency half of this bullet is now
  covered — every scenario in every batch is diffed against a second, no-op-
  sync capture of itself. The remaining bullets below stand unchanged.
- `test_inline_formatting.py::test_plain_edit_clears_prior_italic_formatting`
  and `::test_archived_row_reuse_does_not_leak_italic_into_new_plain_action` —
  both need a second live mutation (a doc-content edit; a backdate+archive+
  append sequence) between two syncs, outside run_lane's three supported
  mutation kinds (`sync`/`sheetEdit`/`trigger`).
- `test_inline_formatting.py::test_plain_action_text_has_no_runs` — a
  negative/cost check with no positive shape to migrate; already implied by
  every corpus in the suite carrying no bold/italic markup.
- `test_continuation_indent_config.py` (both tests) — driven by a Config-sheet
  key (`SR Indent`/`Field SR Indent`) read once per sync, a side channel
  outside what an APT corpus encodes (doc content only); no format construct
  represents "sync with this Config value set."
- `test_ai_n_token.py` — asserts globalId FORMAT and sheet-column plumbing via
  direct xlsx/regex inspection, doesn't use ScenarioSession/APT at all;
  entry-point-mechanism coverage, per the plan's own scope boundary.
- The APT v1 known ceiling (bold/italic covering only *part* of a link's
  width) named in this bead's own description did not block anything here —
  neither migrated test's shape needed partial-width nesting; noted for
  completeness since no future case in this family needs it either.

**Found live, filed rather than fixed in flight (out of scope for a [TST]-file
migration bead):** `test_hyperlink_preservation.py::test_encodable_url_round_trips_and_is_idempotent`
fails deterministically (reproduced 2x, not a flake) against TEST v0.2.3.65 —
`seed_link_action`'s returned `text` field carries the `AI-N: ` token prefix,
but `debug_action_runs`' `scanActionText` correctly omits it; the test's own
assertion compares against the wrong baseline shape. A pre-existing
fixture-return-shape bug, unrelated to this migration (the test body was not
touched, only its module docstring). Filed as `gts-mtw0`
(`discovered-from:gts-dxz9`).

**Verification (targeted gate, per Backstop rules — full sweep deferred to
`regression-verify`):** `tests/test_apt_format_lane.py` 2/2, plus the
surviving tests in all four touched files (`test_inline_formatting.py` 3/3,
`test_status_token_parens.py` 0/0 — no functions left,
`test_hyperlink_preservation.py`'s one surviving test excluded from this
count as the known, filed `gts-mtw0` failure above) — 5/5 green against TEST
v0.2.3.65. Offline lint/format suite unaffected:
`scripts/apt.py lint` clean, `test_apt_fixtures_lint.py` +
`test_apt_scenario_format.py` + `test_apt_differ.py` + `test_apt_lane_lib.py`
+ `test_apt_cli.py` (252 items) all green. `regression=pending` on `gts-dxz9`
per Backstop rules.

**Corpus-authoring lesson re-confirmed** (same class stage 9's handoff
flagged): a literal `_`-prefixed identifier or a literal `->` arrow in
hand-typed annotation prose needs its escape (`\_`, `-\>`) or the round trip
reports a spurious presentational diff; and a chip-badge-wrapped token with
NO assignee has no separating space before the action text (the space lives
inside the bold+link range's own `"TOKEN: "` content, not after it) — only
an assignee chip's own glyph introduces a following space. Both caught by
the lane's first live run and fixed before this stage closed.

---

**Stages 11–15 — why they exist.** Added 2026-08-31, from a triage of the 30 open `[TST]`/red beads,
run against the tree rather than against bead text. It found three things this plan is the right
owner of:

1. **Four beads whose deliverable already exists.** Two of them (`gts-76pp`, `gts-sx60`) target a
   fixture constant this plan's own stage 10 *deleted*. They are not red; they are gone.
2. **One structural gap, stranded twice.** Stages 9 and 10 each hit the same wall — `run_lane`
   cannot express an idempotency assertion — and each wrote the same "deliberately NOT migrated"
   paragraph rather than fixing it. It is also the sole residual scope of three open ACT-fields
   beads. Fixing it once in the runner discharges all of that and adds coverage to 21 scenarios.
3. **The standing reds are not all benign.** One of them (`gts-i0gk`, filed *by* stage 9) is
   evidence of a real `src/` regression, not a known-flaky test.

All three are prerequisites of a sweep that measures the suite instead of measuring known failures.
Stages 11–15 sequence them; none of them is new work this plan invented, except `gts-5ktl`.

**Deliberately NOT pulled in** — real, open, and owned elsewhere: the team-access coverage cluster
(`gts-s1j5` narrowed to its AC5 remainder, `gts-lkaa`, `gts-l632`) is a live-Drive-fixture regime,
not a doc-count one; `gts-2g9j` and `gts-8xef` are document-export surface, excluded from this plan
per stage 16; `gts-ir1f` is blocked on `gts-lirp` and should be split rather than sequenced here.
See §Scope boundaries.

### 11 — tst-litter-close

**Deliverable:** four beads closed, no code written, each with the citation that discharges it.

| Bead | Evidence | Disposition |
|---|---|---|
| `gts-95wl` (P1) | `tests/playwright/team_portal_version_footer.test.js` exists; the bead's own description is a completion report carrying a five-mutation backstop table | close as done |
| `gts-jxnw` (P1) | `tests/fixtures/inline-formatting.apt.txt` Case 2 names this bead by ID (`gts-1ibp/gts-jxnw`) and carries the `{{chip:jane@example.com}}` assignee — the exact `validEmail`/`insertPerson` branch the bead was written for; run by `test_apt_format_lane.py` | close, citing the corpus case |
| `gts-76pp` (P2) | `_EXPECTED_RUNS` no longer exists. Both tests it names were retired by stage 10 (`gts-dxz9`). The one surviving test it cites, `test_plain_action_text_has_no_runs`, asserts `== []` — no run-shape dict, so no `link` key to be missing | close obsolete |
| `gts-sx60` (P2) | Same object as `gts-76pp`, filed independently and never reconciled. Its blocker ("a human must run the test to verify") is moot — the test is gone | close obsolete, noting the duplication |

**Why first:** zero risk, zero live cost, and it removes two entries from the standing-red list
before stage 15 tries to explain them.

**Must not do:** delete `test_plain_action_text_has_no_runs`. Stage 10 already named it as a
deliberate non-migration (a negative/cost check with no positive shape); `gts-76pp` merely cited it.
(Held: not deleted.)

**Closed 2026-09-01, all four, docs-only — no deploy/gate needed.** Verified each row of the table
above against the tree before closing (files exist, corpus case names the bead, fixture is gone):

- `gts-95wl` closed as done — `tests/playwright/team_portal_version_footer.test.js` present (6
  cases), 5-mutation backstop table already on the bead.
- `gts-jxnw` closed citing `tests/fixtures/inline-formatting.apt.txt` Case 2, which names
  `gts-1ibp/gts-jxnw` by ID and seeds `{{chip:jane@example.com}}` on the bold+italic action — the
  `validEmail`/`insertPerson` flush branch the bead was written to cover — run by
  `tests/test_apt_format_lane.py` (stage `apt-format-migration`, `gts-dxz9`).
  `gts-76pp` closed obsolete — `_EXPECTED_RUNS` confirmed absent from `tests/test_inline_formatting.py`
  (`grep` returned nothing); the one surviving test it cited,
  `test_plain_action_text_has_no_runs`, asserts `== []`, no run-shape dict to be missing a key.
- `gts-sx60` closed obsolete, noting the duplication with `gts-76pp` in the close reason — its
  stated blocker ("a human must run the test to verify") is moot with the fixture gone.

**Work-log:** folded into stage 12's entry.

### 12 — flush-lane-retire

**Deliverable:** `gts-crae` — `test_field_continuation_flush.py`'s EP1/EP2/EP3/EP4/EP7 retired to
citation stubs; five Docs per sweep become zero.

**Promoted out of `regression-verify` 2026-08-31.** It was folded into that stage on 2026-08-30 as a
blocker of `gts-u947`. Now that stages 11–15 exist, it belongs where the other retirements are: it
is the same same-family, no-new-corpus, citation-stub pattern stages 9 and 10 already used, and it
is the last un-executed doc-count win in the plan. `tests/test_apt_flush_lane.py`'s `apt-lanes-flush`
batch (`gts-iz9i`, predates this plan) already exercises the identical seed/mutation/assertion shape
via `flush-lane-sheetwin`/`-new-assign`/`-duplicate`/`-missing-status`/`-onedit-trigger` — one doc
instead of five.

**Must not do:** touch EP5/EP6. They exercise call sites (`preview-card` tap, `sidebar_set_status`)
`run_lane` has no mutation kind for — the same carve-out stage 9 respected.

**Ordering:** before stage 13, and independent of it. Doing 13 first would mean re-running the
retired tests once more under the new idempotency assertion for no reason.

**Work-log:** per-stage, batched with stage 11.

**Closed 2026-08-31 (gts-crae), test-only — no `src/` change, no deploy.**
`tests/test_field_continuation_flush.py`'s `test_ep1_sheetwin_flush`,
`test_ep2_new_assign_flush`, `test_ep3_duplicate_reconciliation_flush`,
`test_ep4_missing_status_flush`, and `test_ep7_onedit_flush_known_gap` are
removed, each replaced by a citation comment pointing at the matching
`tests/fixtures/flush-lane-*.apt.txt` scenario run through
`tests/test_apt_flush_lane.py`'s `apt-lanes-flush` batch — same
retirement-citation style stage 10 (`gts-dxz9`) used on
`test_hyperlink_preservation.py`/`test_status_token_parens.py`. The
now-unused `_find_by_global_id` helper and `paragraph_bold_text` import
were removed with them (`_scan_custom_fields`/`_paras_containing` stay —
EP5/EP6 still use both). `test_ep5_preview_card_status_flush` and
`test_ep6_sidebar_status_flush` are untouched (AC #2 held).

**AC #3 (assertion-coverage check) confirmed before retiring anything:**
the five `flush-lane-*.apt.txt`/`-expected.apt.txt` pairs already assert,
via their golden diff, every property the five retired tests asserted —
field survival, the bold `**Target:**` run, the tab-after-colon
(`**Target:**\tvalue`) formatting, and round-trip-recognized-on-rescan
(a field the flush stopped recognizing would re-encode as prose and the
diff would go red). EP7's `flush-lane-onedit-trigger-expected.apt.txt`
still encodes the same KNOWN GAP the retired test marked directly (no
`Target:` line in the expected doc) — nothing was strengthened or
weakened by the retirement. No golden needed extending; the existing
lane was sufficient as documented on the bead.

**Targeted gate (Backstop rules — full sweep deferred to
`regression-verify`):** `tests/test_field_continuation_flush.py` (2
remaining, EP5/EP6) + `tests/test_apt_flush_lane.py` (2 tests, including
the 5-scenario `apt-lanes-flush` batch) — **4/4 PASSED**, 196.33s wall
clock. `regression=pending` on `gts-crae` per Backstop rules.

The plan's own Scope-boundary line (§Scope boundaries, "Not migrated to
APT, by design") already named only EP5/EP6 rather than the whole file —
written ahead of this closure during the 2026-08-31 amendment that added
stages 11–15, so AC #4 needed no further edit here.

### 13 — lane-idempotency

**Deliverable:** `gts-5ktl` — `run_lane` issues one further no-op sync, captures again, and diffs
each scenario's slice against its own first capture.

**Why this is the highest-leverage bead in the plan.** Stage 10's close says it outright:
*"`apt_lane_runner.run_lane` produces one capture per lane run, not a before/after pair to diff
against each other; no corpus-shaped equivalent exists without a runner change."* Stage 9 hit the
same wall. The retirement comment left in `tests/test_inline_formatting.py:55-66` says it a third
time. Three stages wrote the same paragraph instead of making the change.

Marginal cost is one sync **per lane**, not per scenario — no new Doc, no new
`begin_journey_session`, no new corpus. It fires across every existing batch:

| Batch | Scenarios with no idempotency coverage today |
|---|---|
| `apt-corpus-batch` | 6 |
| `apt-lanes-flush` | 5 |
| `apt-lanes-create` | 4 |
| `apt-lanes-scanner` | 4 |
| `apt-lanes-format` | 2 |
| | **21** |

**Must not do:** silently skip a scenario that fails the new diff. A scenario that is legitimately
non-idempotent declares `"idempotent": false` in its `scenario.json` with the reason recorded —
default ON, opt-out is a decision on record. This is the plan's own precedent from stage 9's
"anything ambiguous becomes a bead, not a judgement call in flight."

**Backstop:** the assertion must be proven to fail before acceptance. A green-only run is
unverified — and this one is unusually easy to write in a permanently-green form, since a converged
doc re-synced is idempotent by construction. Introduce a deliberate non-idempotent flush and show it
goes red.

**It acquired a second consumer on 2026-08-31, outside this plan.** ADR-0031 (sync entry points and
rendering conformance) promises that a Document Sync — one with a document context — leaves that
document *idempotently* correct against Config. That promise needs an executable assertion behind it, and
this is it — so `gts-5ktl` is now wired as a blocker of `gts-ttns` and `gts-0wmm` as well as of
`gts-u947`. Its value is higher than the doc-count case alone suggested: it is the only thing in the
suite that would catch a conformance predicate that flushes forever because its render and its scan
disagree by one space.

**Work-log:** per-stage.

**Closed 2026-08-31 (gts-5ktl), test-only — no `src/` change, no deploy.**
`tests/support/apt_lane_runner.py::run_lane` now ends every lane run with one
further no-op `scn.sync()` + `encode_reference_document` capture, and diffs each
scenario's slice of that second capture against its slice of the first through the
same `apt_lib.slice_records` + `diff_apt` path the golden comparison uses.
`LaneResult` gained `idem_diff` and a `clean` property (golden AND idempotency);
all five lane tests now fail on `not r.clean` rather than `not r.diff.clean`, and
`format_failures` reports a `<scenario> NOT IDEMPOTENT (gts-5ktl)` block naming the
scenario. Record-count drift is checked once at the LANE level before slicing — a
record appended past the last scenario's range falls outside every slice and would
otherwise be invisible; that one is reported for the lane, since it cannot be
attributed to a scenario. Opt-out is `"idempotent": false` + `"idempotentReason"`
in a `scenario.json` (`apt_lib.Scenario.idempotent`, default True, non-boolean is a
load error); `docs/interfaces/action-portable-text.md` §"Batched lanes" documents
both.

**AC #3 — no opt-out was needed.** All five batches pass with the assertion ON:
21 scenarios (`apt-corpus-batch` 6, `apt-lanes-flush` 5, `apt-lanes-create` 4,
`apt-lanes-scanner` 4, `apt-lanes-format` 2) gained idempotency coverage and none
declared `"idempotent": false`. The opt-out mechanism ships unused, with
`tests/test_apt_lane_idempotency.py::TestCheckedInScenariosDeclareTheirOptOut`
guarding the day it is first used (an opt-out with no stated reason fails).

**AC #2 — proven to fail** (`tests/test_apt_lane_idempotency.py`, offline). A live
lane against a correct build is idempotent by construction, so a green live run
proves nothing; making it go red live would need a deliberately non-idempotent
build on shared TEST, which the deploy tooling refuses (same constraint
`test_inline_formatting.py`'s own backstop note records). Instead the runner's live
surface (`sync`/`_post_fixture`/`edit_sheet`/`doc_id`) is stubbed by a fake session
whose SECOND capture drifts, driven through the real
`run_lane`/`diff_apt`/`format_failures` path: a one-space drift in one scenario
fails naming that scenario and leaves its sibling green; an appended record and a
removed record both trip the lane-level count guard. 10/10 offline tests, 4.4s.

**AC #4 — measured, per lane, before → after (median baseline → this run):**

| Lane | Scenarios | Before | After | Added |
|---|---|---|---|---|
| `apt-corpus-batch` | 6 | 79.98s | 136.59s | +56.6s |
| `apt-lanes-flush` | 5 | 76.25s | 100.83s | +24.6s |
| `apt-lanes-create` | 4 | 49.64s | 71.36s | +21.7s |
| `apt-lanes-scanner` | 4 | 61.51s | 107.01s | +45.5s |
| `apt-lanes-format` | 2 | 41.46s | 76.88s | +35.4s |
| | **21** | | | **+183.8s total** |

The added cost does not track scenario count (2 scenarios cost +35s, 4 cost +22s) —
it is one sync + one capture per LANE, in the same 20-55s band a single live sync
occupies, with run-to-run GAS variance dominating the spread. Per-scenario would
have been ~21 syncs (roughly 10 min). The structural half of AC #4 is also asserted
offline rather than left to wall clock:
`TestSecondCaptureIsTaken::test_costs_exactly_one_extra_sync_and_capture_per_lane`
pins `sync_calls == 2` / `encode_calls == 2` for a two-scenario lane. Note the
duration instrumentation flags three lanes ⚠ SLOW against their old baselines —
expected, and the rolling baseline re-converges over the next few runs.

**AC #5 — retirement comments corrected:** `tests/test_inline_formatting.py`
(module docstring + the `:55-66` retirement comment),
`tests/test_hyperlink_preservation.py` (docstring), `tests/test_apt_format_lane.py`
(both "deliberately NOT migrated" idempotency bullets), and stage 10's own
"Deliberately NOT migrated" bullet above all now say the idempotency half is
covered by the runner, each keeping the superseded claim on the record rather than
deleting it.

**Targeted gate (Backstop rules — full sweep deferred to `regression-verify`):**
`test_apt_corpus_batch.py`, `test_apt_flush_lane.py`, `test_apt_create_lane.py`,
`test_apt_scanner_lane.py`, `test_apt_format_lane.py`, plus
`test_apt_lane_idempotency.py`, `test_apt_lane_lib.py`, `test_apt_scenario_format.py`
— **163/163 PASSED**, 518.79s. `regression=pending` on `gts-5ktl`.

### 14 — act-fields-closeout

**Deliverable:** the five ACT-fields `[TST]` beads at their true residual scope — closed where the
scope is empty, retitled where it is not.

`tests/test_adr0027_reference_document.py` (`gts-colw`) already discharges every doc-content case of
all five, and its module docstring and per-class comments say exactly which. Nobody went back and
acted on that. What is actually left:

| Bead | Residual after the reference doc | After stage 13 | Disposition |
|---|---|---|---|
| `gts-ucdz` grammar matrix (P1) | *none stated* | — | **close now** |
| `gts-tz5x` hyperlink round-trip (P1) | case 5 idempotency, case 6 no-link-key negative | case 5 covered | close if case 6 is confirmed covered by the corpus; else narrow to case 6 |
| `gts-82s2` field continuation (P2) | case 7 idempotency | covered | **close** |
| `gts-thwh` unparseable reporting (P1) | case 4 persists-across-sync-then-verify, case 5 entry-point audit | case 4 covered | narrow to the entry-point audit only, and **retitle** |
| `gts-nrxn` dual-prefix (P1) | live create-flow cases | not covered — needs a real create flow | narrow to the create-flow cases, and **retitle** |

**Why retitling matters here:** all five read today as full-matrix beads. Anyone picking one up
re-derives coverage that has existed since `gts-colw` closed. The retitle *is* the deliverable for
the two that stay open.

**Ordering:** after stage 13. `gts-ucdz` can close before it.

**Must not do:** close `gts-thwh` or `gts-nrxn`. Their remainders are genuine and neither the
reference doc nor the lane runner reaches them — an entry-point audit and a live create flow are
behavioral, not doc content.

**Executed 2026-08-31.** Actual disposition, three beads stayed open (not two — `gts-tz5x` also
narrowed rather than closed, and `gts-nrxn`'s residual is wider than "the create-flow cases"):

- `gts-ucdz` — **closed.** No residual stated; `TestGrammarMatrix` fully discharges it.
- `gts-82s2` — **closed.** Cases 1-6, 8-11 in `TestFieldContinuation`; case 7 (idempotency)
  covered generically by the batched lane runner (`gts-5ktl`).
- `gts-tz5x` — **narrowed, stayed open**, retitled to "hyperlink run with no link key produces no
  spurious diff". Case 6 is *not* confirmed covered by the corpus (`test_hyperlink_preservation.py`'s
  own docstring calls its coverage merely indirect and flags it "tracked as follow-up, not
  blocking") — the stage's own disposition rule ("close if case 6 is confirmed covered by the
  corpus; else narrow") therefore resolves to narrow, not close.
- `gts-thwh` — narrowed to the entry-point audit (case 5) only, retitled to "entry-point audit for
  unparseable-paragraph reporting". No such audit exists yet for this specific reporting behavior.
- `gts-nrxn` — narrowed and retitled, but to a wider residual than this table's "create-flow cases"
  implied: `test_adr0027_reference_document.py`'s own `TestDualPrefix` docstring is more precise
  than this row — it names cases 2, 3, 5, **and 6** (not just case 2) as needing a live
  create/flush flow the static reference doc cannot exercise. Retitled to "dual-prefix live
  create/flush flow (create, duplicate-flag, AI-N rewrite, chip URL)" to carry all four.

**Work-log:** per-stage.

### 15 — red-clearance

**Deliverable:** the standing-red list is empty or explicitly justified, so stage 16's sweep measures
the suite rather than re-measuring known failures.

| Bead | P | State | Action |
|---|---|---|---|
| `gts-i0gk` + `gts-mt39` + `gts-ogev` | ✅ | **CLOSED 2026-08-31.** Human decision: prefer the real fix over gts-i0gk's documented-v2-limitation fallback — it proved feasible. The parser-side gts-ogev fix was already correct; v0.2.3.64's red was staleness, not regression. gts-mt39's own construction (two tokens in one paragraph) surfaced a SEPARATE real defect: the flush write-back path (`_collectFlushOccurrences`/`_flushActionParagraphs`, `src/SyncManager.js`) bounded a token's delete/reinsert range to the WHOLE paragraph instead of its own record, HTTP 400 on `deleteContentRange`. Fixed (per-token `pEnd` + descending-`lineDocIdx` sort tie-break). Deployed TEST v0.2.3.70. | Landed for real — see gts-i0gk/gts-mt39/gts-ogev closing notes for the live-green test list (`test_floating_action_scanner.py` 4/4, `test_apt_scanner_lane.py` 2/2, `test_kkm7_batching.py` 2/2). `regression=verified` on gts-ogev |
| `gts-lu5k` | ✅ | **CLOSED 2026-08-31.** `doc_inspect.floating_actions()` now dispatches on token count the same way `src/SyncManager.js`'s `_collectActionsFromParagraph` does — a lone token after an intro line, or multiple tokens in one paragraph, each yield their own record instead of being silently dropped. Regression coverage added and proven to fail pre-fix; full offline suite green, live reference-doc oracle unaffected. | Cleared |
| `gts-mtw0` | ✅ | **CLOSED 2026-09-01.** `seed_link_action` (`src/TestFixtures.js`) now returns the scanner's prefix-free `actionText` shape instead of the raw seeded paragraph text (which carried the `AI-N: ` token prefix), matching what `debug_action_runs`' `scanActionText` always returns (the scanner strips the token before returning `actionText`). New assertion added comparing `scanActionText` to the seed's `text` right after the FIRST sync (previously unasserted at that point — only the second/no-op sync's equivalent comparison existed). Deployed TEST v0.2.3.72. Verified: `test_encodable_url_round_trips_and_is_idempotent` PASSED (91s). | Cleared. `regression=pending` (targeted gate only) |
| `gts-6pws` | ✅ | **CLOSED 2026-09-01.** Both call sites hardened: `tests/helpers/sync_coverage.py`'s `assert_sync_coverage` now calls `wait_for_log` (15s) instead of a single-shot `collect_logs`; `tests/test_sync_all.py:509`'s `webapp_entries` lookup now polls `collect_logs` in a short retry loop (15s). Verified live: `test_sync_all_op_propagates_to_webapp` PASSED (176s) — exercises site 2 directly and confirms the polling fix. Site 1's designated verification test (`test_mark_doc_not_found_no_restamp_on_reconfirm`) still FAILED on rerun, but diagnosed via a `matches_op`-scoped Axiom query as a **different, pre-existing bug**, not this bead's Axiom-lag flake: the test's second `scn.sync()` (right after `trash_doc`) hits `syncDocument()`'s trashed-doc branch, which deterministically logs `sync.docNotFound.trashed` and never logs `sync.scanned` at all — no polling can find an event that's never emitted. Confirmed pre-existing by reproducing identically against the unmodified pre-fix `sync_coverage.py` (`git stash`). **This directly narrows stage 3's and stage 6's original diagnosis** (both attributed this same test/signature to pure ingestion lag, "confirmed directly" — see lines ~236 and ~419 below): that may still be true on *some* runs (Drive trash-propagation is itself racy — `isTrashed()` sometimes returns false right after `trash_doc`, so the normal scan path runs and `sync.scanned` lands late), but on this run the trashed branch fired immediately and no lag-based fix applies. Filed `gts-athl` (`discovered-from:gts-6pws`) to track the branch-mismatch case; a comment on it flags this nuance explicitly so it isn't mistaken for a re-litigation of the closed lag fix. | Cleared. `regression=pending` (targeted gate only) |
| `gts-85x3.4` | ✅ | **CLOSED 2026-09-01 as duplicate of `gts-1aqj`.** Verified byte-for-byte: `tests/test_uuse_scoped_listing.py`'s assertion (`count==2` → `count>=2`) already carries this exact fix, with a comment citing `gts-1aqj` by name and matching its close-note root cause (`missingDocIds` computed over the whole tracked backlog, not just the test's 2 forced-miss docs). No separate action needed — `gts-1aqj` already verified this test PASSED (274s). | Cleared |

**Two tests this stage did NOT clear as of 2026-08-31 — both now RESOLVED FOR REAL 2026-08-31 (same
day, later session).** Human decision: implement the real fixes rather than carry these as red.

1. **The `gts-1h5g` → `gts-ttns` → `gts-guux` indent-drift/rendering-conformance cluster —
   CLOSED 2026-08-31**, in dependency order:
   - **`gts-1h5g`** (field-value link/bold/italic runs dropped on flush): the fix was already
     present in the uncommitted working tree, landed under the same-root-cause `gts-py21` fix.
     Verified live — the full targeted set (`test_floating_action_copy_fidelity.py` +
     `test_adr0027_reference_document.py`, 32 tests) ran 31 passed / 1 bootstrap skip / 0 failed,
     including this bead's own required regression test
     (`test_case6_field_value_hyperlink_survives`) and `test_copy_matches_original`.
   - **`gts-ttns`** (indent conformance on Document Sync, ADR-0031 scope): implemented.
     `src/SyncManager.js`'s `_parseFieldContinuationBlocksTracked` now computes `indentConforms`
     unconditionally at scan time (actual leading-space count vs. currently configured `SR
     Indent`/`Field SR Indent`, category-aware for action-body vs. field lines), threaded through
     `_parseActionHeaderLineTracked` into both action scanners; `syncDocument()` gained
     `opts.conform` and a new toFlush loop (parallel to the missing-status-materialize loop) gated
     on it, logging `sync.indentDrift {docId, count}`. `src/WebApp.js`'s `_handleSyncDocument` — the
     one shared seam `menuSyncActiveDoc`/sidebar `onSyncNow`/web-UI doc sync all route through — now
     passes `conform: true` unconditionally, so `syncAll`'s direct in-process calls and the bare
     `sync_document` test fixture stay non-conforming by construction, exactly as ADR-0031 requires.
     Deployed TEST v0.2.3.71, verified serving.
   - **`gts-guux`**: `tests/test_indent_drift_sync.py`'s existing three tests were narrowed to drive
     the real Document Sync seam (`menu_sync_active_doc` fixture) instead of the bare, non-conforming
     `sync_document` fixture they were vacuously passing against before; the required new negative
     case, `test_background_sync_never_reflushes_indent_drift`, drives BOTH no-document-context
     entry points (`sync_all` for the trigger path, `menu_sync` for Spreadsheet Sync All) and asserts
     neither emits `sync.indentDrift` nor touches the doc. All 4 tests green against TEST v0.2.3.71.
   - Targeted gate for the cluster: `tests/test_indent_drift_sync.py` (4) +
     `tests/test_menu_entry_points.py` (7, non-regression) + `tests/test_continuation_indent_config.py`
     (2, non-regression) = **13/13 passed**. `regression=pending` on all three beads (targeted gate
     only per Backstop rules; full `pytest -x` deferred to stage 16 `regression-verify`).
2. **The `gts-i0gk`/`gts-mt39`/`gts-ogev` cluster** — **RESOLVED 2026-08-31**, no longer an open
   question. See its own closing notes (this stage's table, row 1).

**Updated 2026-08-31 (same day, later session):** both decision-gated clusters are now closed for
real — see above. `gts-mtw0`, `gts-6pws`, and `gts-85x3.4` (the three mechanical entries in this
stage's table) remain open; they were out of scope for this session, which was scoped specifically
to the indent-drift/rendering-conformance cluster. `red-clearance` is not yet fully clear — three
mechanical reds are the entire residual now, with no open design questions behind any of them.

**Updated 2026-09-01: all three mechanical entries closed — see the table above for each bead's
closing detail.** `red-clearance` is fully clear. One new bead (`gts-athl`, `discovered-from:gts-6pws`)
was filed for a real, pre-existing, previously-undetected coverage-guard gap found while verifying
`gts-6pws` live (a sync that legitimately doesn't scan — the doc-trashed detection branch — still
gets held to the "sync.scanned must appear" guard). It is not itself a standing red in this stage's
scope (the test failure it explains was already counted under `gts-6pws`'s signature); it's new,
separately-tracked residual work, not a blocker for calling this stage done.

**Must not do:** work around any of these to get a clean sweep. Project Backstop rules — "known test
failures are not a basis for proceeding autonomously" — apply to this stage more than any other in
the plan, because a clean number is exactly what it is tempting to manufacture here.

**Recommended before the sweep, not a blocker:** `gts-d6nz` (session-start test-token liveness probe)
is out of this plan's scope but is direct insurance for stage 16 — `gts-5959` cost a full 177-failure
sweep to a stale token that the local expiry check could not see, and `gts-u947`'s own last run lost
12 tests to a stale auth session over its 3-hour wall clock.

**Work-log:** per-stage.

### 16 — regression-verify

**Deliverable:** the measured claim — suite wall-clock and journey-doc count, before and after — and
every bead in this plan at `regression=verified`.

**Why alone:** it is the plan's only authorised full sweep, and per the Backstop rules it is also the
merge gate for everything above it.

**Scope exclusion — the document-export family (added 2026-08-31).** This sweep does **not** cover,
and does not gate on:

- `tests/test_document_export.py` (23 `new_doc` sites — the largest single doc-count centre left in
  the suite), `tests/test_document_export_harness.py`, `tests/test_export_dialog.py`;
- the beads behind them: `gts-pczo` and children (ADR-0029 schema/hierarchy response), `gts-2g9j`
  (`no_quoted_text` diagnostics), `gts-0002`/`gts-s7ut` (export dialog), `gts-a15z`/`gts-sc14`/
  `gts-etm4`/`gts-qhoz` (docx-verify).

**Why excluded.** Three independent reasons, and any one of them is sufficient:

1. **Owned by other plans.** `knowledge-base/staging/document-export.md` and
   `knowledge-base/staging/suite-composition.md` own this surface. `gts-8xef` (stage `test-surface`)
   ports the exporter tests **off `ScenarioSession` entirely** onto a thin webapp client — which
   means measuring their doc count under this plan measures something scheduled to be deleted.
2. **Already excluded once, by explicit instruction.** `gts-u947`'s 2026-08-31 sweep notes record
   `test_document_export_harness.py`'s two `schema_version` cases as "excluded from scope per
   explicit user instruction — out of scope for this plan." This stage now states the boundary for
   the whole family instead of re-deciding it per test.
3. **It is not this plan's mechanism.** The export tests are a file/folder surface, already named in
   §Scope boundaries as "not migrated to APT, by design." Their cost is real but it is a
   *composition* problem, not a doc-churn one.

**What this means for the numbers.** The reported wall-clock and journey-doc figures are for the
**core-sync suite**, stated as such — not the whole of `pytest`. A separate total may be recorded for
context, but this plan's before/after claim is made on the excluded-export basis, and the invocation
used must be written down alongside the result so the comparison is reproducible.

**What this does NOT mean.** The export tests are not exempt from the merge gate — they are exempt
from *this plan's* gate. Their `regression=pending` beads flip under their own plan, not this one.

**Work-log:** per-stage, and the plan retires (Mode C) once it closes.

## Scope boundaries

- **`gts-aqpk`** (fast/local vs. live pytest tiers) and **`gts-xvgl`** (parallelism) are adjacent
  speed levers on a *different* mechanism — scheduling, not doc-count. Deliberately out of scope;
  they compose with this plan's result rather than competing with it. They are, however, the natural
  *successors*: once stages 12–13 have settled the file set, `aqpk`'s enumeration has a stable thing
  to enumerate.
- **The document-export family is excluded from stage 16's sweep** — test files, beads, and the
  reasoning are stated in that stage. It is the one exclusion that changes what the plan's headline
  number means, so it is recorded there rather than only here.
- **The team-access coverage cluster is out of scope:** `gts-s1j5` (already half-written —
  `tests/test_verify_access.py:293,318` cover its AC1/AC2; only the AC5 `list_my_teams` /
  `list_team_actions` call-site audit remains, and it should be retitled to say so), `gts-lkaa`, and
  `gts-l632`. All three need live Shared-Drive fixture identities, which is a different regime from
  doc churn. They group cleanly as one session of their own.
- **`gts-ir1f`** (batch live `syncAll()` tests) shares this plan's goal but not its scope: files 1
  and 2 of 4 are done and committed (`b77b63b`), and the bead is blocked on `gts-lirp`, a genuine
  Import-tab DOM race. Split it — close the completed half, re-file `test_import.py` /
  `test_team_scope.py` as a bead not blocked on `lirp` — rather than sequencing it here.
- **Not migrated to APT, by design:** entry-point coverage (`test_menu_entry_points`, `test_sidebar`,
  `test_field_continuation_flush` EP5/EP6 — EP1/2/3/4/7 retired to `test_apt_flush_lane.py` under
  `gts-crae`, stage `flush-lane-retire`); cross-document state (`test_sync_all`, `test_archive`,
  `test_team_scope`, `test_team_folder_reconciliation`) where "two docs in two folders" *is* the
  subject; file/folder surfaces (`test_import`, `test_document_export`); and anything with a
  perceptual oracle (Playwright/UI).
- **APT reduces doc churn but does not fix the litter.** A lane still creates a doc. Stages 1–6 stand
  on their own merits and do not become unnecessary if the migration stalls.
