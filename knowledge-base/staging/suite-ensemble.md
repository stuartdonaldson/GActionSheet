# Staged plan — regression suite: ensemble execution

> **Transient working contract** (framework staging). Deleted when the last stage closes and the
> durable content has graduated to `docs/atdd/ID-map.md` (the ensemble/beat/coda vocabulary and its
> place in the testing model), `docs/OPERATIONS.md` (how to run and triage an ensemble) and
> `CLAUDE.md` §Testing Strategy (the eligibility rule and the entry-point-coverage restatement).
> **TTL exception:** `doc-standard.md` caps staging documents at two weeks; this plan is five
> stages. It decomposes fully into beads (Stage 0). Review it against that test, not the calendar.
> Review fidelity: **Spec** (ADR-0013) — the eligibility rule and the failure-containment semantics
> are the only places design error can hide, and both are visible from contract prose plus offline
> unit tests against the runner.
> **Supersedes nothing.** `docs/regression-suite-health-review-2026-08-05.md` F3/F5 and the stalled
> `gts-ir1f` are inputs, not casualties — see *Reuses* in Stage 0.

Pattern D staged execution. The contract lives in
`$DEVSTANDARD/doc-framework/planning-guide.md` §"Pattern D: Staged Execution" — not restated here.
Beads own all state (AC, grouping, model, owner decisions); this document holds sequencing
rationale, deliverable previews and handoffs only.

**Never run a complete regression `pytest` or `pytest -x` unless explicitly directed.** Every stage
below closes on a targeted gate with `regression=pending`, per CLAUDE.md's Backstop default. This
plan is *about* suite cost; running the full suite to prove each increment would be self-defeating.

- Update each stage in this document with Handoff notes that should be highlighted for other stages.

## Thesis

The suite costs ~150 min (median, `tests/.pytest_duration_baseline.json`, 750 nodes). The intuition
that "setup/teardown is the problem" is **half right, and the half that is right is the smaller
half**. The measurement:

| Where the time is | | |
|---|---|---|
| pytest `setup` + `teardown` phases | **14 min** of 143 | fixtures are *not* the cost |
| pytest `call` phase | **129 min** of 143 | the cost is inside the test body |
| 534 offline nodes | 0.1 min | already free |
| 80 nodes in the 15–45 s band | 33.5 min | **fixed doc-lifecycle floor** — this is the setup/teardown intuition, and it is real |
| 50 nodes over 45 s | **98.6 min** | real work: `syncAll()` sweeps, imports, UI drives |

So there are two distinct levers, and they are not the same size:

1. **The floor.** `ScenarioSession.new_doc() → mutate → sync() → close()` costs **~25–30 s** before
   any assertion runs, and it is paid **194 times** across `tests/`. In the 15–45 s band that floor
   *is* the test. Collapsing it saves **~22 min (15%)**.
2. **The sweep.** `syncAll()` crawls the whole shared TEST corpus; its cost scales with corpus size
   (this is why `conftest.py::_purge_stale_test_docs` exists at all — docCount observed climbing
   106 → 171 within one session). `test_sync_all.py` alone holds 56 `syncAll` references across 10
   tests / 21.5 min. This is the **98.6-min tail**, and it is where the sustainable win is.

Both levers are the same move: **stop re-establishing a state the previous test just discarded.**
One setup, many mutate/assert beats, one closing assertion.

## What the measurement changes about the ask

Three corrections worth carrying into the beads, because each one invalidates an obvious plan:

**The pattern is already the repo's convention — where it was applied, it made triage worse.**
`test_team_scope.py` (360 s, 1 test, 11 `new_doc`) and `test_team_folder_reconciliation.py` (361 s,
1 test, 39 `syncAll` references) are *already* one-setup-many-assertions. They are also two of the
worst tests in the suite to debug: a six-minute opaque unit that reports one boolean. `gts-ir1f` has
been **in progress since 2026-08-06 across five failed attempts** to extend that pattern to
`test_sync_all.py`. It is not stalled on the batching idea; it is stalled because nobody wants to
convert twenty legible tests into one six-minute failure.

> The deliverable of this plan is therefore **not batching**. Batching is known, tracked and
> correct. The deliverable is the **reporting and containment machinery that makes batching safe to
> adopt** — per-beat pass/fail, containment of the first failure, and one-command re-isolation of a
> single beat. Without that, this plan reproduces `gts-ir1f`'s stall at larger scale.

**Consolidation is not only a saving — it is coverage the suite does not have today.** N isolated
docs cannot observe cross-case interference: a mutation in case 3 corrupting case 7 is invisible
when each gets a fresh doc. The **coda** (below) asserts whole-doc/whole-sheet consistency after
every beat has run, which is a strictly new assertion class. This is what keeps the plan from being
a pure isolation-for-speed trade, and it is the argument to make at the increment gate.

**The exemplar already exists.** `tests/test_status_token_parens.py::test_status_token_parens_hardening`
is one doc, three cases, one `checkpoint(INTEGRITY)`, 32.7 s. The equivalent work in
`test_floating_action_scanner.py` is 18 tests × ~30 s = 9.2 min. The machinery
(`scn/engine.py::CheckpointEngine`, the expectation queue, `AUTO`/`INTEGRITY_TARGET` draining) is
built and shipped. This plan generalises an existing pattern; it invents no new assertion model.

## The domain axis — what a "full regression of one area" can mean

Owner proposal (2026-08-28): decompose into **actions parse/sync/flush · team org/access ·
web UI · addon sidebar · doc export**, and run or skip an area whole. Classified against the
baseline, that decomposition covers **100% of the suite** with two files left over
(`tests/helpers/*`, ~0 min). It is the right organizing idea. Three corrections make it safe.

**1. These are not five peers — they are a layered graph, and that determines what "skip" means.**
Measured from `src/`: `syncDocument`/`syncAll` are called from `MenuHandler.js`, `TeamSync.js`,
`WebApp.js`, `WorkspaceAddonCard.js` and `TriggerManager.js` — every surface funnels into
`SyncManager.js`. `AccessControl.js` is called from `WebApp.js`, `DocView.js`, `TeamListing.js`,
`TeamActionWrite.js` and `TeamSync.js` — team/access sits *under* the entry surfaces, not beside
them. `Procedure-Exporter.js` references core sync **zero** times.

| Role | Area | Cost | Skip semantics |
|------|------|------|----------------|
| **Trunk A** | action grammar (doc-local parse/flush) | 37.9m | never skipped when any other area ran |
| **Trunk B** | sync engine (corpus-scale `syncAll`) | 42.3m | never skipped when any other area ran |
| **Layer** | team org / access control | 22.5m | skippable only if no entry-surface area ran |
| **Leaf** | web portal / import | 12.1m | independently skippable |
| **Leaf** | addon sidebar + Docs-native chips | 12.8m | independently skippable |
| **Branch** | doc export | 15.8m | independently skippable; *guaranteed* once `gts-6zed` lands |
| **Spine** | canonical journey | 4.5m | always — it is the integration proof, not an area |
| **Free** | offline harness/unit (534 nodes) | ~0m | always — already free (`gts-aqpk`) |
| **Backstops** | retry / idempotency / logging / concurrency | 2.2m | always — a risk axis, not a product area |

The consequence is worth stating plainly: **"skip export" is a guarantee; "skip team" is a risk
judgment.** Those are different promises and must not share a word. Only the branch is decoupled
outward — and core still names the exporter in five files (`MenuHandler.js`, `WebApp.js`,
`WorkspaceAddonCard.js`, `ContractSchema.js`, `ExportFolderMap.js`), which is exactly the coupling
`suite-composition` stage `plugin-register` exists to remove. **Domain 5 and the sub-app boundary
must be the same boundary**, not two parallel decompositions of the same code.

**2. "Actions" at 59.4 min is two areas.** Grammar (doc-local: scanner, field continuation, inline
formatting, hyperlink, APT corpora) and the sync engine (corpus-scale `syncAll`) have different
failure domains, different cost drivers, and different flake profiles — `syncAll` owns essentially
all of the `/exec` routing flake surface (`gts-pm72`) and its cost scales with the shared TEST
corpus. Split, "grammar only" becomes a **38-minute** slice; unsplit, it is 59 and always drags the
flakiest tests in the suite along with it.

**3. The label must attach to the beat, not the file.** File-level markers would lie today:
`test_sidebar.py` carries 23 sidebar, 23 team and 18 doc-sync signals; `test_import.py` carries 78
team, 45 doc-sync and 9 UI; `test_team_folder_reconciliation.py` is 83 team and 39 `syncAll`.
Marking those files "team" would silently skip sync coverage, and marking them "sync" would silently
skip access-control coverage. **This is the axis on which the domain decomposition and this plan's
beat protocol are the same work**: a beat is the smallest unit that can honestly carry one domain
label, so `beat-triage` must emit a domain per beat, not per file.

### What the domain axis does and does not buy

It is a **targeting** fix, not a cost fix. Because everything sits on the trunk, most single-area
profiles still pay for it:

| Profile | Cost today |
|---------|-----------|
| doc export only | **16m** |
| action grammar only | **38m** |
| actions (grammar + sync + spine + backstops) | 87m |
| sidebar (+ trunk + spine) | 98m |
| team (+ trunk + spine) | 107m |

So the two axes multiply and neither substitutes for the other: **domains decide what you are
allowed to skip; ensembles and sweep batching decide what the trunk costs when you cannot skip it.**
Sequencing follows — `sweep-batching` (stage 4) is what collapses Trunk B, and every domain profile
above drops with it.

**4. Selection should be change-driven, not chosen.** The durable artifact is a
`src/` module → area map, so `git diff --name-only` mechanically yields the areas a change forces
(`SyncManager`/`ActionToken`/`TrackerTable`/`PortableText` → trunk; `AccessControl`/`TeamListing`/
`TeamSync`/`TeamActionWrite`/`WriteGuard`/`VerifySync` → layer; `WebApp`/`webSurvey`/`DocView` →
web leaf; `EditorAddonCard`/`WorkspaceAddonCard`/`MenuHandler` → sidebar leaf;
`Procedure-Exporter`/`ExportFolderMap` → branch). That removes the per-session judgment call, which
is the part that does not survive contact with a tired Friday.


## Sequencing against `apt-testing.md` — that plan runs first

`apt-testing.md` has two stages left (`apt-lanes`, then `act-retire`). **This plan waits for both.**
Three reasons, in decreasing order of force:

1. **`beat-triage` would classify tests `act-retire` is about to delete.** The retirement list
   centres on `tests/test_floating_action_scanner.py` — 11.0 min, and simultaneously this plan's
   single largest `ensemble-convert` target (18 beats, 9.2 → ~2.3 min est). Running triage first
   spends `model:opus` judgment on ~20 doomed tests, and running `ensemble-convert` first converts
   tests that are then deleted. Either order but this one wastes the work twice over.
2. **`apt-testing` is two stages from collecting its own promise.** Its thesis is explicit: "The
   shift is only realised when the superseded tests are deleted. Stages `act-triage` and
   `act-retire` are not cleanup; they are where the promised simplification is actually collected."
   Six stages are closed. Suspending at stage 6 pays all of that cost and banks none of it.
3. **`act-retire` moves this plan's own baseline.** Its deliverable is net test count *down*; the
   `gts-y1eg` rolling baseline re-medians on each pass, so triage should read a post-retirement
   suite rather than a snapshot that is about to be invalidated.

**One constraint this plan places on `apt-lanes` (stage 6), which has not started:** its scenario
runner must not be one-doc-per-scenario. `tests/test_apt_corpus_check.py` is that shape today — 7
scenarios, 5.1 min, paying `begin`+`sync`+`end` seven times — and `apt-lanes` is about to write the
runner that `act-retire` then migrates the scanner tests *into*. An APT scenario is already an
ensemble by another name (one corpus → one doc → declarative mutations → one diff), so it should be
written to the `mutate-all / sync-once / assert-all` shape of decision 5, and scoped so this plan's
runner can host it later rather than competing with it. `apt_lib._normalize_n` rewrites every N to
`#` per record, so **composing several corpora into one doc is diff-safe** — corpora stay split for
review (stage 4's deliberate choice) while the runner composes them for execution.

If that constraint is not taken, this plan's stage 1 inherits a second runner to reconcile, and the
`gts-ir1f` pattern — infrastructure built per-consumer and never unified — repeats inside the
replacement for the tests it was meant to retire.

## Terminology

Settled here so it lands in fixture names, markers and bead titles.

| Term | Meaning |
|------|---------|
| **ensemble** | one live doc (and its `ScenarioSession`) shared by an ordered run of beats — the unit of setup |
| **beat** | one `(mutation, assertion)` pair against the shared doc; the unit that replaces today's test function, and the unit pytest still reports on |
| **coda** | the closing assertion after the last beat: drain invariant, whole-doc/whole-sheet consistency, and beat-count completeness |
| **solo** | a test that keeps its own doc because it fails the eligibility rule; a first-class outcome, not a failure to convert |
| **poisoned** | the state of an ensemble after a beat fails — later beats report *skipped, with a pointer to the root failure*, never *failed* |

"Batch" is deliberately **not** used: it already names `syncAll()`'s per-doc REST batching
(`gts-kkm7`) and the `batch:` label, and would be genuinely ambiguous.

## Design decisions this plan assumes

Recorded here because they are sequencing-load-bearing; they graduate to `docs/atdd/ID-map.md` and
`CLAUDE.md` at Mode C.

1. **A beat stays a pytest test function.** The ensemble is a module-scoped fixture; beats are
   ordinary test functions in file order. This preserves per-beat PASSED/FAILED, `--lf`, `-k`,
   allure, and the `gts-y1eg` duration instrumentation — all of which a single looping test
   destroys. It is also the smallest possible diff from today: converting a file deletes its
   `new_doc()`/`close()` lines and changes nothing else.
2. **The first failing beat poisons the ensemble; it does not fail the rest.** Later beats report
   `skipped` naming the root beat. One root cause produces one red line, not N. This is the direct
   answer to the source incident `2026-06-02-test-failures-observed-but-not-elevated-to-blocker.md`:
   a wall of cascading red is how a real failure gets waved through.
3. **Any beat can be promoted back to a solo by one flag**, with no edit to the test. Triage of a
   failing beat must never require unpicking the ensemble by hand — that cost is exactly what has
   kept `gts-ir1f` open for three weeks.
4. **Eligibility is an invariance property, and it is asserted, not asserted-by-hope.** A beat may
   join an ensemble iff its assertions are invariant to (a) pre-existing doc content, (b)
   pre-existing sheet rows, and (c) the N counter's starting value. The practical consequence:
   **a beat addresses actions by unique action text or `globalId`, never by positional `AI-1`.**
   The runner enforces (c) by starting ensembles at a non-1 N where the platform allows it, so a
   positional assumption fails immediately and locally rather than as a mystery ordering bug.
5. **Sharing the `sync()` matters more than sharing the doc — a beat declares its mutation and its
   assertion separately.** Measured over 4,403 recorded acts (`test-results/runs/*.jsonl`):
   `begin_journey_session` 4.6 s + `end_journey_session` 2.7 s = **7.3 s** of doc lifecycle, but
   `sync` alone is **12.6 s** — 1.7x the lifecycle it is nested inside, and `sync_all` is **47.4 s**
   (n=248). An ensemble that shares only the doc but still syncs per beat leaves the larger half of
   the saving on the table. So the runner must let a stage of beats declare mutations, take **one**
   sync, and then let every beat assert against that single convergence — the `mutate-all /
   sync-once / assert-all` shape, which is also exactly `gts-ir1f`'s sweep shape at a different
   scale (decision 8). A beat that genuinely needs its own convergence declares so and pays for it;
   that is a per-beat cost, not the default.

6. **The coda is a real assertion, not a teardown hook.** It runs as its own reported test function
   at the end of the module. A coda that cannot fail is the vacuous-assertion defect
   (`2026-06-02-new-assertion-vacuously-passes-on-empty-result-set.md`) and must be proven to fail
   before acceptance, per CLAUDE.md's Backstop rules.
7. **Order is explicit and asserted.** The ensemble records the beat sequence; the coda asserts the
   expected beat count actually ran. A partial run (`-k one_beat`) is detected and either promoted
   to solo or reports the coda as skipped — never as passed. A green coda on a two-beat run of a
   nine-beat ensemble would be the worst possible outcome of this plan.
8. **Entry-point coverage is unchanged by consolidation.** CLAUDE.md's invariant requires the entry
   point itself to be the call-site. A beat calls the same entry point the test it replaces called;
   sharing a doc changes the fixture, not the call-site. Every conversion commit names the entry
   points its beats cover, so the `scripts/check_coverage.py` (T24) diff stays meaningful.
9. **Sweep batching consumes the runner; it does not reimplement it.** `gts-ir1f`'s one-`syncAll()`-
   many-assertions shape is a *coda-heavy ensemble* — the sweep is the mutation, each scenario's
   expectation is a beat. Rebasing it onto the runner is what unblocks it, and is why it sequences
   after `ensemble-runner` rather than beside it.
10. **No parallelism in this plan.** `bd remember: no-concurrent-pytest-runs` is explicit that two
   concurrent suites against this project mis-report, and `gts-xvgl` owns that decision separately.
   Consolidation reduces the *number* of live round trips, which is safe under a serial constraint;
   parallelism relaxes the constraint itself and is a different risk conversation.

## Stage 0 — beads to file

**Not yet created — owner confirmation required.** Five proposed beads below; `Reuses` lists what
already exists and must not be duplicated. Nothing is created until the scope summary is confirmed.

**Reuses (already in the tracker):**

| Bead | Role in this plan |
|------|-------------------|
| `gts-ir1f` | [TST] retrofit live `syncAll()` tests to batch scenarios per sweep. **In progress since 2026-08-06, five failed attempts, all on `/exec` routing flakes during verification — not on the design.** Becomes stage `sweep-batching`, rebased onto the ensemble runner. Its own description already cites T6/T21 and `CheckpointEngine`; this plan supplies the machinery it was hand-rolling. |
| `gts-aqpk` | [INF] fast/local vs live tiering via markers. **Complementary, not competing** — tiering decides *what runs*, this plan decides *what a live run costs*. The 534 offline nodes it protects are already ~free; the two levers multiply. Sequenced outside this plan. |
| `gts-xvgl` | [INF] parallelism decision. Explicitly out of scope here (decision 10); its answer changes if consolidation lands first, so it should be re-asked after, not before. |
| `gts-28p` | [TD] reconcile journey-embedded-step vs dedicated-per-entry-point placement. **This plan supplies the missing default** its scope item 3 asks for (the eligibility rule *is* the placement rule). Should close against stage `beat-triage`'s output rather than being answered independently. |
| `gts-8xef` | [TST] thin webapp client, port exporter tests off `ScenarioSession`. Overlaps `test_document_export.py` (20 beats, 8.4 min). Whichever lands first, the other's scope shrinks — **decide the order before either starts** (see `human` decision, Stage 0 note). |

**New (proposed):**

| Bead | One-sentence scope |
|------|--------------------|
| `[INF] Ensemble runner — shared-doc fixture, beat protocol, coda` | A module-scoped `ensemble` fixture over `ScenarioSession` plus the beat/coda protocol per decisions 1, 2, 6 and 7: per-beat pytest reporting preserved, first failure poisons and later beats skip with a pointer, coda asserts drain invariant + whole-doc/sheet consistency + beat-count completeness, with the coda proven to fail before acceptance. |
| `[INF] Beat isolation — promote any beat to a solo by flag` | A pytest option/marker (decision 3) that gives one named beat its own fresh doc with no source edit, so triaging an ensemble failure costs one command; plus the eligibility guard from decision 4 (non-1 starting N) that turns a positional-`AI-1` assumption into an immediate local failure. |
| `[TST] Eligibility audit — classify every live test as beat or solo` | Apply decision 4's invariance criteria across the ~114 live doc-driven tests, producing a per-file conversion list with each solo carrying the criterion it fails **and each beat carrying its area label** (see *The domain axis*); judgment only, no conversions, and the output is also `gts-28p`'s missing placement default. |
| `[TST] Convert the floor-dominated files` | Convert the files whose per-test cost is dominated by the doc-lifecycle floor — scanner, field-continuation, `b7` write routes, team listing, team portal hardening, menu entry points — to ensembles, each conversion commit naming the entry points its beats cover (decision 8). |
| `[INF] Area map — module → area, and the beat-level area label` | The `src/` module → area map above, the beat-level marker that carries it, and the change-driven selector that turns `git diff --name-only` into the set of areas a change forces; states which areas are *guaranteed* skippable (branch) versus a *risk judgment* (layer, leaves), and names the trunk as never-skippable. |
| `[INF] Runtime budget + timeout ceiling` | Discharge health-review F5: declare a per-beat and per-solo wall-clock budget and enforce it (`pytest-timeout` or equivalent), so a beat regressing from 4 s to 90 s fails loud instead of quietly re-inflating everything this plan removes. |

**Proposed dependency edges** (`bd dep add`, type `blocks`): isolation ← runner; convert ← runner,
isolation, triage; `gts-ir1f` ← runner, isolation; budget ← convert. `beat-triage` takes no edge
from the runner — it is pure classification and runs concurrently.

**Owner decisions to file with the `human` label, not settled here:**
- Order of `gts-8xef` (thin webapp client) vs converting `test_document_export.py`. Doing both
  independently means porting the same 20 tests twice.
- Whether `gts-28p`'s "fault isolation deprioritized" call becomes the project default. Decisions 2
  and 3 are this plan's answer — containment and one-command re-isolation *buy back* the fault
  isolation that consolidation spends — but adopting that as the standing default is the owner's.

## Execution order

| # | Stage | Bead | Status | Title |
|---|-------|------|--------|-------|
| 1 | `ensemble-runner` | *(to file)* | — | [INF] Ensemble runner — shared-doc fixture, beat protocol, coda |
| 1 | `ensemble-runner` | *(to file)* | — | [INF] Beat isolation — promote any beat to a solo by flag |
| 2 | `beat-triage` | *(to file)* | — | [TST] Eligibility audit — classify every live test as beat or solo |
| 2 | `beat-triage` | *(to file)* | — | [INF] Area map — module → area, and the beat-level area label |
| 3 | `ensemble-convert` | *(to file)* | — | [TST] Convert the floor-dominated files |
| 4 | `sweep-batching` | `gts-ir1f` | in_progress | [TST] Retrofit live syncAll() regression tests to batch independent scenarios per sweep |
| 5 | `suite-budget` | *(to file)* | — | [INF] Runtime budget + timeout ceiling |

Regenerable via `bd list --label stage:<name>` or `bdls --stage <name>` once Stage 0 closes; Status
mirrors bd, which stays the authority.

**Verify:** `bdls --stages` (roll-up) · `bdls --check` (audit) · `bdls --goals --stage <name>` (one
stage in context). No tracker output is pasted into this document.

## Stages

Named, not numbered; `#` is execution order and lives here only.

### 1. `ensemble-runner` — the machinery that makes consolidation safe
**Deliverable:** a module of three beats plus a coda runs against one doc; killing a beat's assertion
produces **one** FAILED and two SKIPPED-with-pointer, and `--ensemble-solo <beat>` re-runs that beat
alone against a fresh doc without touching the source.
**Why paired:** the runner and the isolation flag are one design — poisoning semantics (decision 2)
and re-isolation (decision 3) are the same question asked from the failing side and the recovering
side, and the eligibility guard (decision 4) has to be built into the fixture that hands out the
doc. Split, the containment story gets designed twice and the second half never ships, which is the
observed failure mode in `gts-ir1f`.
**Must not:** convert a single existing test. This stage ships machinery plus its own throwaway
demonstration module; a conversion here would tune the runner to one file's shape. Also must not
make a beat anything other than a pytest test function (decision 1).
**Work-log:** one entry covering the stage's beads.

### 2. `beat-triage` — classify before anything is converted
**Deliverable:** a per-file conversion list over the ~114 live doc-driven tests — each solo naming
the eligibility criterion it fails, each beat naming its area — plus the module → area map that
turns `git diff --name-only` into the set of areas a change forces.
**Why paired:** eligibility and area are the same read of the same 114 test bodies, one asking
"can this share a doc?" and the other "what breaks if this is skipped?". Done separately, the
second pass re-derives the first pass's understanding of every file. Together they gate stage 3
and supply `gts-28p`'s missing default. Neither depends on the runner, so the stage runs **first
and in parallel** with `ensemble-runner`.
**Must not:** invent an area boundary for the exporter that differs from the sub-app boundary
`suite-composition` is already building — domain 5 and the sub-app are the same cut, and two
parallel decompositions of the same code is the failure this stage exists to prevent. Attach an
area label at file granularity where the file straddles areas (`test_sidebar.py`,
`test_import.py`, `test_team_folder_reconciliation.py` all do). Convert anything. Classification
only — mixing the two is how a test that needed a
fresh doc quietly becomes a beat and starts passing for the wrong reason. Also must not treat
"solo" as a failure to be minimised: a bootstrap/first-sync, doc-not-found, archive-lifecycle or
`@create`-at-doc-start case is *correctly* a solo, and forcing it into an ensemble deletes coverage.
**Work-log:** per-stage.

### 3. `ensemble-convert` — collect the floor saving
**Deliverable:** the floor-dominated files run as ensembles; measured wall-clock for those files
drops from ~22 min toward ~9 min, evidenced by the `gts-y1eg` duration baseline before and after.
**Why paired:** one mechanical pass against a settled runner and a settled classification; the
files share no design question between them.
**Must not:** start before `beat-triage`'s list exists. Convert a test the audit marked solo.
Weaken an assertion in the port — the pre-conversion and post-conversion assertion sets are diffed
and shown equal, the same discipline `gts-8xef` already sets for its own port. Drop an entry point:
every conversion commit names the entry points its beats cover (decision 8).
**Work-log:** per-stage.

### 4. `sweep-batching` — the 98-minute tail
**Deliverable:** `test_sync_all.py`'s independent scenarios assert against a shared `syncAll()`
sweep instead of one sweep each; the file's 21.5 min falls materially, with per-scenario reporting
**preserved** — which is the property its five prior attempts could not offer.
**Why paired:** `gts-ir1f` alone, rebased. This is the largest single lever in the plan and the one
that has already failed five times; it gets its own stage and its own session precisely so the
rebase onto the runner is a deliberate act rather than a detail inside a conversion sweep.
**Must not:** re-attempt the hand-rolled batching. If the runner does not fit the sweep shape, that
is a finding against stage 1, filed as such — not worked around locally. Must not run the full
sweep to verify: verification is scoped to the touched files, `regression=pending`, per the
Backstop default and this plan's own header.
**Work-log:** per-stage.

### 5. `suite-budget` — stop the saving from silently re-inflating
**Deliverable:** a declared per-beat and per-solo wall-clock budget, enforced, so a regression fails
loud; health-review F5 closes.
**Why paired:** single bead, and it is deliberately last — a budget set before the conversions land
would be calibrated against the costs this plan is removing.
**Must not:** set a budget that turns an infrastructure flake into a red build. `/exec` routing
blips (`gts-pm72`) are the documented ambient failure mode here and are exactly what killed five
`gts-ir1f` attempts; the ceiling must be far enough above the median that it catches a structural
regression and not a slow Tuesday.
**Work-log:** per-stage.

## Sequencing rationale

`beat-triage` first and independent: it is cheap, it is pure judgment, it sizes stages 3 and 4, and
it answers a question (`gts-28p`) that is already open. It deliberately shares no session with the
runner — its context is the eligibility rule and 114 test bodies, and mixing it with fixture design
would contaminate classification with "I could make the runner handle that".

`ensemble-runner` before every conversion because the containment and re-isolation semantics are
*features of the runner*, not of any converted file. Converting first would mean inventing a
placeholder fixture per file and then replacing all of them — which is a description of how
`test_team_scope.py` and `test_team_folder_reconciliation.py` came to be shaped the way they are.

`ensemble-convert` before `sweep-batching` even though the sweep is the bigger prize: the
floor-dominated files are the cheap, low-variance proving ground for the runner. Taking the
five-times-failed sweep retrofit as the runner's first real customer would confound "the runner is
wrong" with "`/exec` was flaky again", which is precisely the ambiguity that has kept `gts-ir1f`
open.

`suite-budget` last, necessarily — a ceiling is calibrated against the costs that remain.

**Order is asserted, not modelled** for `beat-triage` relative to `ensemble-runner`: they have no
dependency edge because they genuinely can run concurrently. That is a preference (triage first if
sequential), not a constraint.

## Shared session context

Two stages share a session profitably when they share the *mental model*, not merely the files.

**Runs well as one session:**
- `ensemble-runner` — the poisoning semantics, the re-isolation flag and the eligibility guard are
  one design conversation about what happens when a shared doc goes wrong. Splitting them costs a
  re-derivation of the containment model.
- `ensemble-convert` — one mechanical pass with one assertion-set diff per file.

**Must not share a session:**
- `beat-triage` with any conversion stage — classification must not be able to reach for a fix, and
  must not be able to reclassify a stubborn solo into a beat to make the sweep look better.
- `ensemble-runner` with `ensemble-convert` — the runner's value is that it is file-agnostic;
  sharing a session with the first conversion is how one file's shape leaks into the fixture.
- `ensemble-runner` with `sweep-batching` — see the sequencing rationale: co-designing them makes
  "the runner is wrong" and "`/exec` was flaky" indistinguishable.

**Model:** `ensemble-runner` is `model:opus` — failure-containment semantics under a shared mutable
resource are the correctness-critical judgment in this plan, and getting decision 7 wrong produces a
suite that passes vacuously. `beat-triage` is `model:opus`: misclassifying a solo as a beat deletes
live coverage silently. `sweep-batching` is `model:opus` — it has failed five times and needs
judgment about when to stop and file a finding. `ensemble-convert` and `suite-budget` are mechanical
against a settled contract and suit `model:sonnet`.

## Deliberately out of scope

- **Parallelism** (`gts-xvgl`). Decision 10. Its answer changes once consolidation lands, so it is
  better re-asked after this plan than merged into it.
- **Fast/live tiering** (`gts-aqpk`). Complementary and independently tracked; the two levers
  multiply and neither blocks the other.
- **Making `syncAll()` itself cheaper** — scoping the sweep to a folder, or bounding the shared TEST
  corpus more aggressively than `_purge_stale_test_docs` already does. A real lever on the same 98
  min, but it is a **product** change to `SyncManager`, not a test-structure change, and it must not
  ride in on a test-refactor commit. → `ROADMAP.md §Funnel`.
- **Retiring duplicated live coverage** (health-review F4: `test_journey.py` vs
  `test_journey_acts_1_3.py`, 4.5 min + 1.4 min). Genuine, but it is a coverage-equivalence
  argument, not a structural one, and it needs a read of both files' assertions rather than this
  plan's machinery. → its own bead, sequenced independently.

# Revision Log

- **Created 2026-08-28.** Stage 0 authored and awaiting owner confirmation; no beads created. Source
  measurements: `tests/.pytest_duration_baseline.json` (750 nodes, 150.3 min median) and
  `test-results/duration-log.jsonl` (run-20260827T160037Z, 637 items, 143.3 min — setup 6.8 /
  call 129.1 / teardown 7.4).
