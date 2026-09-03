# Staged plan — Sync alignment: entry points, DocData walk, and the admin doc-scan

**Contract:** `$DEVSTANDARD/doc-framework/planning-guide.md` §"Pattern D: Staged Execution".
Beads own all state (AC, grouping, model, human decisions). This document holds only
sequencing rationale, deliverable previews and handoff notes.

## Why this plan exists

ADR-0031 (`knowledge-base/adr/0031-sync-entry-points-and-rendering-conformance.md`) named six
sync entry points and decided which of them conform rendering to Config. The audit that produced
it, plus the 2026-09-01 live admin-scan run, left nine implementation gaps where the code does
not yet match the decision:

- **Spreadsheet Sync All** builds its doc list by regexing docIds out of the Actions sheet
  (`SyncManager.js:517-524`) instead of walking DocData, the canonical registry — and reports
  nothing to the operator, not even success.
- **Web-UI / team-portal Sync** is classified as a Document Sync but calls `syncDocument(docId)`
  with no options (`TeamSync.js`), so it silently skips the conformance ADR-0031 promises it does.
- **Character-style conformance** (`ai_token` / `action_text`) is unimplemented; the doc scan
  samples no character style at all. Indent conformance landed in gts-ttns; style is the other half.
- **The two `Action Sync > Sync` menu items** carry identical labels while now making *different*
  promises about the document — the shared label went from unhelpful to misleading.
- **The admin doc-scan** cannot finish: live proof (2026-09-01, TEST v0.2.3.86, op 80a84bf2)
  `teamId=Board → scanned=261 matched=0 complete=False elapsedMs=271215`. Two independent defects
  in one run — no persisted cursor, so re-running restarts the identical traversal; and a
  quick-match regex that only accepts `ACT`, so the legacy `AI-N:` population this feature exists
  to find is invisible.
- **The sync test harness produces two false-failure signatures** on `tests/test_sync_all.py`
  (`assert_sync_coverage` demands a `sync.scanned` event from a code path that provably never
  emits one; the real 30-minute trigger lands inside a test's op fence ~2% of runs). Both must be
  fixed *before* the batched coverage run, or that run reports noise as regression.

## Ordering deviation, deliberate and recorded

The repo's twin-ticket rule wires each `[TST]` as a blocker of its `[IMP]`. **Four of those edges
were inverted on 2026-09-01 when this plan was authored** (`gts-lk8w`, `gts-05rj`, `gts-ccve`,
`gts-vpeq` now depend on their `[IMP]` rather than blocking it), and the four `[TST]`s were
collected into one `sync-coverage` stage.

**Why.** Project CLAUDE.md's oracle-ordering lever (gts-m65t) makes *coverage-before-merge* the
invariant and *ordering* the oracle's choice. Every assertion in these four beads runs against the
live GAS backend and needs a deployed build. Authored independently they pay four separate
deploy + live-sync cycles and build four overlapping scenario setups over the same entry-point
matrix (`syncAll`, `menuSync`, `sync_document`, `team_sync_document`). Batched, they pay it once
and the negative cases that keep ADR-0031 honest — *background sync never restyles* — get asserted
across the whole matrix instead of once per bead.

**What this does not relax.** Three guardrails stay in force and are load-bearing here:

1. **Coverage-before-merge is untouched.** No bead in this plan reaches `regression=verified`, and
   no merge gate passes, until its coverage is green.
2. **Proven-to-fail still applies** (Backstop rules, CLAUDE.md). With implementation already
   landed, each new assertion is proven by temporarily reverting the single line it targets —
   `conform: true` in `_handleTeamSyncDocument`, the DocData doc-list source in `syncAll`, the
   `(?:ACT|AI)` alternation in `AdminDocScan.js`, the style mask in the conformance loop. Every
   implementation bead in this plan is small enough at its seam for that to be a one-line revert.
   **A coverage bead that cannot demonstrate its assertion failing is not closed.**
3. **No-shared-context is preserved by authoring, not by ordering.** The `sync-coverage` and
   `scan-coverage` stages are authored against the frozen contracts in each `[IMP]`'s
   description/design fields. Those contracts are frozen *now*, before implementation starts.

**Regression policy for this plan (human direction, 2026-09-01):** no full `pytest -x` sweep. Every
bead closes on a targeted gate with `bd set-state <id> regression=pending --reason "<what ran>"`.
The two coverage stages run the targeted sync/scan regression only. Flipping the tree to
`regression=verified` is a separate, explicitly-requested act.

## Execution-order table

| # | Stage | Bead | Status | Title |
|---|---|---|---|---|
| 1 | `scan-resumable` | `gts-vsjv` | ○ | [FIX] AdminDocScan quick-match misses legacy AI-N: tokens |
| 1 | `scan-resumable` | `gts-lgpx` | ○ | [IMP] Resumable admin doc-scan: Script-Property progress + self-rescheduling trigger |
| 2 | `scan-coverage` | `gts-m4cq` | ○ | [TST] Resumable admin doc-scan: progress persistence, trigger resume, status route |
| 2 | `scan-coverage` | `gts-4wk7` | ○ | [TST] Coverage gap: admin scan real-identity path, isAdmin flag, static-portal button surface |
| 3 | `sync-docdata-walk` | `gts-qkev` | ○ | [IMP] Context-free syncs walk DocData, not Actions-derived docIds |
| 3 | `sync-docdata-walk` | `gts-xqce` | ○ | [IMP] Spreadsheet Sync All: UI notice when DocData integrity repairs occurred |
| 4 | `sync-surface-truth` | `gts-gvs8` | ○ | [FIX] team_sync_document does not pass conform:true — web UI Sync silently skips conformance |
| 4 | `sync-surface-truth` | `gts-w9kx` | ○ | [IMP] Disambiguate the two 'Action Sync > Sync' menu items |
| 5 | `sync-style-conformance` | `gts-0wmm` | ○ | [IMP] Rendering conformance: ai_token / action_text character style on Document Sync |
| 6 | `sync-harness-truth` | `gts-athl` | ○ | [FIX] assert_sync_coverage's expected_min ignores the trashed-doc non-scanning branch |
| 6 | `sync-harness-truth` | `gts-i9xc` | ○ | [FIX] test_sync_all_op_correlation flakes when the 30-min syncAll trigger fires mid-fence |
| 7 | `sync-coverage` | `gts-lk8w` | ○ | [TST] syncAll DocData-walk + Actions-referential-integrity coverage |
| 7 | `sync-coverage` | `gts-05rj` | ○ | [TST] Spreadsheet Sync All repair-notice coverage |
| 7 | `sync-coverage` | `gts-ccve` | ○ | [TST] team_sync_document conform coverage — SR Indent drift synced via web UI must self-correct |
| 7 | `sync-coverage` | `gts-vpeq` | ○ | [TST] Rendering conformance: character-style drift, and that background sync never restyles |

**Verify:** `bdls --stages` · `bdls --check` · `bdls --goals --stage <name>`
Status above mirrors the tracker, which stays the authority. Audit at authoring (2026-09-01):
**0 errors**, 2 warnings on these stages — `unordered-batch` on `sync-surface-truth` and
`sync-harness-truth`, both deliberate and stated in their blocks.

## Parallel lanes

The `#` column is execution order for a *single* worker. Three lanes share no source file and may
run simultaneously:

| Lane | Stages | Files it owns |
|---|---|---|
| **A — admin scan** | 1 → 2 | `src/AdminDocScan.js`, `src/TestWebApp.js`, `static-portal/src/index.html`, `tests/test_admin_doc_scan.py` |
| **B — sync entry points** | 3 → 4 → 5 | `src/SyncManager.js`, `src/MenuHandler.js`, `src/TeamSync.js`, `src/WebApp.js` |
| **C — harness truth** | 6 | `tests/helpers/sync_coverage.py`, `scn/session.py`, `tests/test_sync_all.py` |

**Lane B does not parallelise internally.** Stages 3, 4 and 5 all touch `SyncManager.js` or
`MenuHandler.js` — stage 3's `menuSync` change and stage 4's menu-label change land in the same
function region. Run them in order; do not fan them out.

**Stage 7 waits on B *and* C.** It is the only stage with two upstream lanes, and that is modelled
(`gts-athl`, `gts-i9xc` → `gts-lk8w`), not merely asserted.

**Stage 2 waits on stage 1 and cannot be deferred.** `gts-lgpx` *retires* the `admin_scan_team_docs`
action; all three existing tests in `tests/test_admin_doc_scan.py` call it. Stage 1 cannot get a
green targeted gate without stage 2 re-authoring that file. Lane A is a two-stage unit.

## Acceptance checkpoints — deliberately not at the end

Batching the *regression* cost to stages 2 and 7 is correct: it is expensive, it runs against the
live backend, and it guards against breakage. Batching the *acceptance* signal with it is not, and
was the error in this plan's first draft.

The two answer different questions. Regression asks *did we break something*; acceptance asks *did
we build the intended thing*. Only the first is expensive. Deferring the second to stage 7 means
design drift surfaces after five stages of development — which is how a plan becomes unworkable near
its end, and a plan that becomes unworkable near its end never reaches its final step. The
documentation and preservation steps that live at that final step are therefore unreachable in
exactly the case they exist for. This has now happened three times in this repo's history (an
earlier plan abandoned and deleted, losing its rationale → the litter plan to clean up after it →
the admin doc-scan feature as fallout from that).

So every implementation stage carries an **Operator check**: a specific thing to look at on TEST,
by hand, in minutes, with no pytest run at all. It gates the stage close alongside the targeted gate.
If the check fails, the drift is a new bead or a new stage *now* — at stage 1, not stage 7.

This is ADR-0013 Slice fidelity applied to feature shape rather than only to UI copy. It costs
nothing against the regression budget.

## Capture every stage; integrate the docs once per feature

Two obligations, deliberately at different granularities. Conflating them is what produced this
plan's first draft, which asked seven stages to each edit DESIGN.md.

**Capture — every stage, before its commit.** Findings, measurements, constraints and rationale go
into the bead (`bd note` / `bd remember`) and into this file, and **this file is committed with that
stage** (contract rule 7). Additive, never wrong-because-partial, and cheap enough to be
unconditional. This is what survives if the plan is abandoned at stage 4. Anything with no durable
home gets an explicit *deliberately dropped, because…*, the same disposition rule findings carry.

**Integration — once per feature.** The coherent edit to CONTEXT.md / DESIGN.md / OPERATIONS.md
happens at the completion of a *feature*, not a stage: a tier document describing half a design is
worse than one describing none of it. This plan has **two features**, which are exactly the two
parallel lanes that carry a doc surface:

| Feature | Stages | Integrates at | Documents |
|---|---|---|---|
| **admin doc-scan** | 1, 2 | close of stage 2 | DESIGN.md (two-phase enumerate/match, chunked-property storage), OPERATIONS.md (scan lifecycle: start, resume, stale recovery, trigger hygiene) |
| **sync entry points** | 3, 4, 5, 7 | close of stage 7 | DESIGN.md (DocData as canonical doc-list source; conformance seam), OPERATIONS.md (repair notice, which Sync does what), CONTEXT.md §Glossary + ADR-0031 (reconciled six-name vocabulary) |
| *(none — enabling work)* | 6 | — | no doc surface; capture only |

**Intent is written first, and it is a drift detector.** Before stage 1, draft the *intended*
end-state of those DESIGN.md / OPERATIONS.md sections — as the specification, marked as intent. Then
every stage close reconciles against it: does what we built match what we said we would build? A
divergence is either a doc correction or a drift finding, and it surfaces at stage 1 instead of
stage 7. This is the complement of the Operator check — that asks *does it work*, this asks *is it
the thing we designed* — and like it, it costs nothing against the regression budget.

Retirement (§Retirement) is then an audit that nothing remains ungraduated, not the moment
graduation happens. See `gts-flu4` and DevStandard's `terminal-boundary-repair` plan for the
framework fix; this plan does not wait on them.

## Stages

### 1 — scan-resumable  (`gts-vsjv`, `gts-lgpx` · opus)

**Deliverable:** the portal's Scan button returns in ~1s instead of hanging for 4.5 minutes, a
261-doc team folder finishes unattended across automatic trigger passes, and legacy `AI-N:` docs
finally appear in the results — the whole reason the feature exists.

**Why paired:** one file (`src/AdminDocScan.js`), and the edge is real — `gts-lgpx`'s phase-2
matcher *is* the consumer of `gts-vsjv`'s corrected pattern. Fixing the regex without the resumable
walk still leaves matches past the budget cutoff unreachable; the resumable walk without the regex
finishes fast and still returns `matched=0`. Neither is shippable alone. Modelled as a dependency,
so the intra-stage order is a constraint, not a preference.

**Must not do:** log a doc-read exception's message or `String(e)` — `AdminDocScan.js:99` records
that this leaked a real team's meeting notes into Axiom. Unchanged and load-bearing.

**Operator check (gates the close):** on TEST, click Scan on the same `teamId=Board` folder that
produced `scanned=261 matched=0 complete=False`. The button returns in ~1s; status moves through
running/waiting; the scan finishes with no further clicks; `matched > 0` and the results name real
legacy `AI-N:` docs you recognise. This is the whole feature — if it does not read as finished and
correct here, that is design drift, and it becomes a bead now, not a stage-7 discovery.

**Captures at close:** the two-phase enumerate/match design, the 9KB chunked-property constraint
and the measured per-doc scan cost → bead + this file. Integration of these into DESIGN.md /
OPERATIONS.md happens at the close of stage 2 (feature: admin doc-scan), not here.

**Work-log cadence:** per-stage.

### 2 — scan-coverage  (`gts-m4cq`, `gts-4wk7` · opus)

**Deliverable:** the admin scan's four state-modifying entry points and the portal's button-visibility
rule each become a test call-site — closing the gap named in
`docs/lessons-learned/2026-09-01-bead-closed-green-with-user-facing-entry-point-untested.md`, where
`gts-gwyg` closed green while the surface the operator actually clicks had none.

**Why paired:** both re-author `tests/test_admin_doc_scan.py` against the same fixture set
(`setup_team_scope_fixture`, `set_config_row append:true`, `move_doc_to_folder`, `set_docdata_row`).
Split across sessions they collide in one file. `gts-m4cq` → `gts-4wk7` is modelled: the file must be
re-authored against the new contract before the identity/isAdmin gaps are layered on.

**Must not do:** read `src/AdminDocScan.js`. Author against `gts-lgpx`'s frozen contract only.

**Answer first (in `gts-4wk7`'s design field):** whether the operator's "I do not see the option"
report reproduces as `isAdmin=false` or as `isAdmin=true` suppressed by the All-teams branch. That
determines which of the three gaps is load-bearing; the other two can be covered cheaply once known.

**Work-log cadence:** one entry covering stages 1–2 (lane A closes as a unit). Commit and push
per-stage regardless.

### 3 — sync-docdata-walk  (`gts-qkev`, `gts-xqce` · opus)

**Deliverable:** Spreadsheet Sync All sweeps the canonical registry rather than a regex over a
formula column, and — for the first time — tells the operator when it repaired something instead of
silently succeeding.

**Why paired:** `gts-xqce` consumes the return value `gts-qkev` introduces; the field names are
literally undecided until `gts-qkev` picks them (its AC5 says "or-similar"). Two sessions would
freeze that contract by guess. Modelled as a dependency.

**Must not do:** give `syncAll()` a parameter. It stays zero-argument — GAS binds a trigger event
object positionally to the first arg and `TriggerManager.js:53` registers it by name. And
`syncAll()` must never call `getUi()`; the alert lives in `menuSync()` only.

**Resolve, don't defer:** `gts-qkev`'s design field leaves one question open — whether "walk DocData"
means DocData alone or `union(DocData, docIds-with-live-Actions-rows)`. Resolve it against AC2 (the
`isNewRow` backstop must not regress) and record the answer on the bead before coding, since stage 7
authors against it.

**Operator check (gates the close):** run Sync from the tracker spreadsheet's menu against a sheet
with a known DocData gap. The alert fires, names counts you can verify against the sheet, and says
something an operator can act on. Then run it again with nothing to repair — silence. Read the
message as an operator, not as its author: if it reports a number nobody can use, that is drift.

**Captures at close:** DocData as the canonical doc-list source for context-free syncs, the
resolved DocData-vs-union question, and the final field names of `syncAll()`'s return value → bead
+ this file. The ADR-0031 amendment and the tier-doc edits integrate at the close of stage 7
(feature: sync entry points).

**Work-log cadence:** per-stage.

### 4 — sync-surface-truth  (`gts-gvs8`, `gts-w9kx` · sonnet)

**Deliverable:** every Sync surface tells the truth about what it does — the web-UI button actually
performs the conforming Document Sync ADR-0031 says it does, and the two menu items stop making
different promises under one label.

**Why paired:** the same defect class in two surfaces (behaviour and copy diverging from ADR-0031's
Decision table), and both amend the same ADR sections. One session holds the ADR reconciliation
context; two would amend it twice.

**`unordered-batch` warning is deliberate:** these two genuinely commute — different files
(`TeamSync.js` vs `MenuHandler.js`), no shared symbol. The order in the table is a preference.

**Oracle split inside the stage:** `gts-gvs8` is specifiable (a route either passes `conform: true`
or does not) — its assertion is stage 7's `gts-ccve`. `gts-w9kx` is perceptual (UI copy) and takes
ADR-0013 Slice fidelity: change the labels, look at both menus, confirm. Its only durable assertion
is `tests/test_menu_entry_points.py` staying green, which already exists.

**Must not do:** add a `force` field to `team_sync_document`. Explicitly out of scope (`gts-gvs8`
AC2). And if the chosen labels diverge from ADR-0031's Terminology names, update ADR-0031 in the
same change rather than leaving two vocabularies.

**Operator check (gates the close):** open both menus and read the two labels without their
surrounding menu — that is how they get discussed, logged and supported. Then, in the team portal,
edit SR Indent in Config, click Sync, and confirm the document actually re-conforms. `gts-w9kx`
carries the `human` label; this check is where that decision gets made.

**Captures at close:** the chosen labels and the reconciled UI-label ↔ ADR-0031 Terminology
vocabulary → bead + this file. Glossary and ADR-0031 edits integrate at the close of stage 7.

**Work-log cadence:** per-stage.

### 5 — sync-style-conformance  (`gts-0wmm` · opus)

**Deliverable:** changing `ai_token` colour or `action_text` font in Config finally propagates on an
ordinary Document Sync instead of requiring Force Refresh — the last unimplemented half of ADR-0031's
rendering conformance.

**Single-bead stage, and it earns the layer:** it is the largest change in the plan (the doc scan
captures *no* character style today — `_runsFromRichTextRuns` reads only the sheet-side
`RichTextValue`), it is the only stage whose cost must be measured and reported, and its negative
cases are what keep the whole entry-point split honest. It gets its own session and its own handoff.

**Must not do — the trap, and ADR-0022 is the authority:** compare **six** attributes on the
`ai_token` range (fontFamily, fontSize, color, bold, italic, underline) but **four only** on
`action_text` (fontFamily, fontSize, color, underline). Bold and italic are excluded; ADR-0022 gave
those exclusively to author-typed inline runs, and including them re-flattens per-word author
formatting on every user sync — the exact defect ADR-0022 exists to prevent.

**Report, don't absorb:** state the measured added scan time for a representative doc. If sampling is
expensive enough to be felt on the user path, say so.

**Operator check (gates the close):** change `ai_token` colour in Config, run Document Sync from
inside a Doc, and look at the document — the tokens restyle, and a paragraph where you typed bold or
italic by hand is byte-identical afterwards. Then let the 30-minute sweep run over the same doc and
confirm it changed nothing. Also feel the sync: if the added scan cost is noticeable at this point,
that is the finding, not a footnote.

**Captures at close:** the six-vs-four attribute rule with its ADR-0022 rationale, and the measured
added scan cost → bead + this file. Both integrate at the close of stage 7.

**Work-log cadence:** per-stage.

### 6 — sync-harness-truth  (`gts-athl`, `gts-i9xc` · sonnet)

**Deliverable:** `tests/test_sync_all.py` stops producing failures that are not defects — the
prerequisite for reading stage 7's batched run as signal.

**Why paired:** both are false-failure signatures in the same test file's harness, and both were
misdiagnosed once already. `gts-athl`'s comment records the trap directly: the *identical* assertion
message ("no `sync.scanned` log entry found") has two distinct causes — Axiom ingestion lag, already
fixed by `gts-6pws`, and `syncDocument()` taking the trashed-doc branch and never emitting the event.
Verify which branch fired via an op-scoped (`matches_op`) Axiom query before choosing the fix; do not
assume one diagnosis supersedes the other.

**`unordered-batch` warning is deliberate:** the two fixes are independent. Order is a preference.

**Runs any time before stage 7.** Modelled as blocking `gts-lk8w`, so the graph enforces it.

**Work-log cadence:** per-stage.

### 7 — sync-coverage  (`gts-lk8w`, `gts-05rj`, `gts-ccve`, `gts-vpeq` · opus)

**Deliverable:** one coherent regression suite over the sync entry-point matrix — `syncAll`,
`menuSync`, `sync_document`, `team_sync_document` — asserting both what each surface *does* and, for
the background pair, what it must *never* do. This is the batched deliverable the plan exists for:
the four coverage beads share one deploy, one live-backend run, and one set of scenario fixtures.

**Why batched:** they cover one mechanism from four angles. `gts-vpeq`'s two load-bearing cases are
not about style drift at all — *a background sync (30-min trigger **and** `menuSync`) leaves a
drifted doc untouched*, and *`action_text` bold/italic are never compared* — and both are cheaper and
stronger asserted alongside `gts-lk8w`'s `syncAll` scenarios than in isolation. Internal order is
modelled (`lk8w` → `05rj`, `ccve` → `vpeq`), because `05rj` asserts a helper over `qkev`'s field names
and `vpeq` reuses `ccve`'s conformance scenario shape.

**Every assertion must be proven to fail.** See §"Ordering deviation" above for the mechanism
(one-line revert at each seam). A coverage bead that shows only green is not closed.

**Must not do:** leak Config rows. `_openActionSheetSpreadsheet()` opens the ONE shared live tracker
spreadsheet, so a stray `ai_token` / `action_text` row pollutes every other test in the run *and*
production. Clear in a `finally`, unconditionally — reuse
`tests/test_continuation_indent_config.py`'s `clear_config_rows` fixture. `gts-9a4j` hit exactly this.

**Also required:** any scenario calling `verify_consistency()` must also call
`verify_all_expectations(a)` for at least one action (backstop rule — prevents a vacuous pass on an
empty result set).

**Regression scope:** targeted sync regression only — the touched test files plus
`tests/test_sync_all.py`, `tests/test_menu_entry_points.py`, `tests/test_continuation_indent_config.py`.
**No full `pytest -x` sweep.** Route output to a file, never pipe to `tail`. On close, set every
bead in stages 1–7 to `regression=pending` with the actual command in `--reason`.

**Work-log cadence:** per-stage.

## Handoff log

*(Written as stages close. Four parts each: Done — with real output pasted, and the stage's
Deliverable line corrected above if it differed · Found · Next stages must know · Deliberately not
done. Every finding carries a disposition: fixed now / bead `<id>` / AC of stage `<n>` /
deliberately dropped, because…)*

### Stage 1 — scan-resumable
*not started*

### Stage 2 — scan-coverage
*not started*

### Stage 3 — sync-docdata-walk
*not started*

### Stage 4 — sync-surface-truth
*not started*

### Stage 5 — sync-style-conformance
*not started*

### Stage 6 — sync-harness-truth
*not started*

### Stage 7 — sync-coverage
*not started*

## Retirement — an audit, not a graduation

Graduation happens at each stage close (§"Durable content graduates at stage close"). By the time
stage 7 closes, every stage's durable content is already in its permanent home and this file is
already in git history from stage 1 onward. Retirement therefore only *checks*:

1. `bdls --stages` shows all seven complete.
2. Walk each stage's *Captures at close* line and each feature's *Integration* row and confirm both
   actually landed. Anything missed graduates now — this is the backstop, not the mechanism.
3. Every *Found* item carries a disposition; anything dropped says why.
4. Archive or remove the file **from a committed state**, per `gts-flu4`. Never `rm` an untracked
   staging doc: as of 2026-09-01 this file, `docdata-litter-apt-speed.md` and
   `py21-reference-doc-copy-fidelity.md` were all untracked, which is that bead's defect live in the
   working tree.

**If this plan is abandoned instead of completed** — the outcome its own §Acceptance checkpoints
section exists to make survivable — steps 2 and 3 still run, against the stages that did close. An
abandoned plan gets retired, not deleted.

The tree still carries `regression=pending` at retirement by design. Flipping it to `verified`
requires a full sweep, which is a separate explicitly-requested act, not part of this plan.
