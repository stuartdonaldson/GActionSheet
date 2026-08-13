# Regression Suite Health Review — 2026-08-05

Prepared for human review. Not an ADR, not yet actioned — findings and priority
recommendation only. Source material: `HANDOFF-regression-flake-2026-08-05.md`
(prior session), `docs/atdd/ID-map.md` / `sdlc-testing-principles.md` (T1–T24),
open beads `gts-pm72`, `gts-ir1f`, `gts-lirp`, and a structural scan of `tests/`
(39 files, 418 tests, 12,651 lines) run this session.

## Bottom line

The prior handoff correctly diagnosed one class of problem (Google `/exec`
routing flakiness) and proposed a tactical fix (`--sw` → single non-stopping
pass). That's necessary but not sufficient. The scan below surfaces a second,
structural class: **the suite's own shape is inflating wall-clock time and
flake surface independent of Google's infrastructure** — no parallelism, no
fast/slow tier separation, and at least one file group with duplicated live
coverage. Recommendation order below treats the handoff's items as Tier 1
(do first, cheap, already scoped) and adds Tier 2 items this scan found.

## Findings

### F1 — No fast/slow tier separation; every run pays live-backend cost

`pyproject.toml` defines exactly one marker (`smoke`). Of 39 test files, 28
drive a live `ScenarioSession` against the real TEST GAS deployment; only 11
(`test_contract.py`, `test_scn_engine.py`, `test_scn_reporter.py`,
`test_scn_surfaces.py`, `test_scn_ai.py`, etc. — the `scn/` harness's own unit
tests, plus a few contract/infra checks) run with no live round trip. There is
no marker distinguishing these, and `pnpm run test:full` runs everything in
one pass with no tiering. A contributor who breaks a pure `scn/engine.py`
helper pays the same multi-hour live-backend cost to find out as one who
breaks live sync — the fast, deterministic 11-file layer that *could* run in
seconds on every commit is not set up to do so.

**Why it matters for flake, not just speed:** every test in the 28-file live
tier is exposed to the Google `/exec` routing flakiness `gts-pm72` documents.
Fewer live round trips per commit-to-signal cycle means fewer chances to eat a
transient blip before you learn whether your change is correct.

### F2 — Fully serial execution against a single live backend; no parallelism

No `pytest-xdist` (or equivalent) in use; `addopts` in `pyproject.toml` has no
`-n` flag. 418 tests run strictly one at a time. This is very plausibly
*deliberate* — tests appear to share fixed team/folder identities (e.g.
`TestTeamScopeA` recurs across `test_team_scope.py`, `test_import.py`,
`gts-lirp`'s notes), so naive parallelism could introduce cross-test
contamination that T9 (fixture isolation) is specifically designed to
prevent. This needs a **decision, not a default**: either (a) confirm
per-file/per-test fixture identities are already unique enough to parallelize
safely and turn on `-n auto` (or file-level `-n` for known-independent
files), or (b) confirm they aren't and document why serial execution is a
hard constraint, so it stops being re-litigated per session. Currently
neither is written down anywhere the scan found.

### F3 — Confirmed violation of the project's own T21/T6 batching principle, beyond what's already tracked

`gts-ir1f` (open, P3) already tracks retrofitting `test_sync_all.py` and
`test_team_folder_reconciliation.py` to batch independent scenarios per live
`syncAll()` sweep, and was updated 2026-08-05 to add `test_import.py`. The
scan confirms the scope: `test_import.py` alone has 15 sync-call sites,
`test_sync_all.py` has 29, `test_team_folder_reconciliation.py` 10,
`test_team_scope.py` 11. That's ~65 live round trips concentrated in 4 files
before touching the rest of the suite. This matches T21 ("themed journeys...
one monolithic journey couples unrelated failure domains and risks timeout")
and T6 (permutation batching) almost exactly — `gts-ir1f`'s own description
already cites T1–T24. **This finding doesn't change the diagnosis, it
confirms the bead's scope is right and quantifies the remaining size of the
job.**

### F4 — Likely duplicated live coverage: `test_journey.py` vs `test_journey_acts_1_3.py`

`test_journey_acts_1_3.py` docstring: "Drives §16.10 Acts 1-3 of the canonical
journey against a live GAS deployment." `test_journey.py` docstring: "Acts
1-5 + final reconcile... Exercises Sync Scenarios C, B/A, and the editor UI."
Both are live, both claim Acts 1-3 territory. `test_journey_acts_1_3.py`'s
docstring labels itself "Twin verify B6" (a distinct verification purpose —
plausibly an intentional independent replay to catch convergence bugs the
main journey wouldn't), but nothing in either file cross-references why the
duplication is intentional rather than historical accretion (e.g., B6 was
authored before Acts 1-3 were folded into the canonical journey, and never
retired). This needs a **read of both files' actual assertions**, not just
docstrings, to determine: genuinely distinct AC coverage (keep both,
document why) vs. redundant live-backend cost (retire one, or fold the B6
assertion into `test_journey.py`'s existing Acts 1-3).

### F5 — No runtime budget or CI-style timeout ceiling declared anywhere

T21 says themed journeys should "stay within platform execution ceilings,"
but no file in `tests/`, `pyproject.toml`, or OPERATIONS.md states what that
ceiling is, either per-test or per-suite. Without a stated budget, "this test
takes 13-20 minutes" (as `test_import_flow_forward_sync` does per the prior
handoff) has no threshold to be flagged against — it just becomes normal.
Recommend picking numbers (even provisional ones) and asserting via
`pytest-timeout` or similar, so a test regressing from 2 min to 15 min fails
loud instead of being discovered by a human staring at a slow terminal.

### F6 — Traceability/coverage gap-diff (T24) is built but not run as a gate

Per `docs/atdd/ID-map.md`, `scripts/check_coverage.py` exists and works
end-to-end, but its "Open follow-ups" section shows it was last exercised
2026-06-11 with 3/32 ACs and 0/3 entry points covered — clearly stale
relative to current suite size (418 tests now vs. the state at that
measurement). It is not wired into `pnpm run test:full` or any gate. This is
adjacent to (not the cause of) the flake problem, but it's the tool that
would tell you, authoritatively, whether the retrofit in F3/`gts-ir1f` loses
coverage — which is literally one of `gts-ir1f`'s own acceptance criteria
("No loss of coverage... documented"). Running it now would also reset the
baseline so future drift is visible.

### F7 — GAS-side retry gap (from prior handoff, restated for completeness)

`gts-pm72` — no argument with the diagnosis or fix shape; restated here only
so this doc is a complete picture without requiring a second document.
Client-side (`scn/session.py::_http_post`) retries; GAS-side
(`DriveApp`/`UrlFetchApp` self-calls inside `SyncManager`) does not. This is
the one item in this list with a clear owner, clear fix shape, and a Backstop
rule (prove the retry fires on an injected 500) already specified in the bead.

### F8 — Import-tab read race (from prior handoff, restated for completeness)

`gts-lirp` — two distinct root causes under one symptom, still open. Real
product/harness bug, not infra noise. Independent of the performance
findings above; included for completeness since it was found in the same
regression run and is P2.

## Recommendations, in priority order

Status legend: ✅ done · ⏳ in progress · ⬜ not started

| # | Action | Bead / new? | Why this order | Status |
|---|--------|-------------|-----------------|--------|
| 1 | Stop using `--sw` for full sweeps; run one non-stopping pass and triage in bulk (per prior handoff) | process change, no bead needed | Zero-cost, immediately reduces wasted human/agent time on every future run regardless of what else changes | ✅ done 2026-08-06 — codified in `CLAUDE.md` §Testing Strategy so it's not re-litigated per session (see AC below) |
| 2 | Fix GAS-side retry gap | `gts-pm72` (existing, P2, CLOSED) | Clear scope, clear Backstop proof, directly stops the single most expensive failure mode measured (`test_import_flow_forward_sync`, 4 consecutive 7-20 min failures) | ✅ done 2026-08-06 — closed, `regression=pending` (targeted-subset gate only; full `pytest -x` not yet run — see AC below) |
| 3 | Retrofit sync-batching in the 4 confirmed files (`test_import.py`, `test_sync_all.py`, `test_team_folder_reconciliation.py`, `test_team_scope.py`) | `gts-ir1f` (existing, P2 — re-prioritized 2026-08-06) | Largest structural wall-clock win available; principle-grounded (T21/T6); already scoped, just needs to move up the queue given F1/F5's cost evidence | ⏳ in progress 2026-08-07 — syncAll-batching scope fully done/N-A'd for all 4 files (see AC below). The one remaining open item, live-verifying `test_import.py`'s `scn_other` fixture-shortcut, **PASSED 2026-08-07** (`plan-0806-flake-recovery.md` S1/S2 fixed the two harness defects absorbing prior attempts as flake, then S3's attempt #6 passed clean on the first try: `1 passed in 379.58s`, `/tmp/jobs/ir1f-attempt6.log`; 1 of 2 budgeted attempts used). No `gts-lirp` symptom, no new transport failure — S1's retry fix held under live load. Full-suite `pytest -x` (S5 in the same plan) still outstanding before `gts-ir1f` can flip to `regression=verified` and close. |
| 4 | Run `scripts/check_coverage.py` now to refresh the stale (2026-06-11) AC/entry-point baseline, and wire it into `pnpm run test:full` (or a lighter dedicated `test:coverage` script) as a standing check | new `[INF]` bead | Makes #3's "no coverage loss" claim provable instead of asserted; cheap once run once | ⬜ not started — bead not yet created |
| 5 | Decide and document the parallelism question (F2) — either enable `-n` for the confirmed-independent tier or write down why not | new `[INF]` bead, needs a human decision on fixture isolation guarantees first | Second-largest potential wall-clock win, but blocked on a correctness judgment call this doc can't make unilaterally — flagging, not deciding | ⬜ not started — blocked on human decision; bead not yet created |
| 6 | Split the suite into a fast/local tier and a live tier via markers (F1), and give the fast tier its own quick script/CI step | new `[INF]` bead | Doesn't reduce live-suite cost directly, but shortens the feedback loop for the ~28% of the suite that doesn't need it, and reduces incidental live-flake exposure per commit | ⬜ not started — bead not yet created |
| 7 | Resolve the `test_journey.py` / `test_journey_acts_1_3.py` overlap (F4) — read both, keep-with-rationale or merge/retire | new `[TST]` bead (retroactive-path, Path B applies) | Real but smaller cost than #3; needs a content read this doc didn't do, so scoped as follow-up rather than solved here | ⬜ not started — bead not yet created |
| 8 | Set explicit per-test/per-suite runtime budgets with `pytest-timeout` (F5) | new `[INF]` bead | Prevents future regressions of this exact kind from being silently absorbed again; low cost, best done once #3 establishes a new baseline "normal" so the threshold isn't set against today's inflated numbers | ⬜ not started — bead not yet created; deliberately sequenced after #3 |
| 9 | Fix Import-tab read race | `gts-lirp` (existing, P2) | Real bug, independent of performance track — sequence after the performance items only because it doesn't compound the wall-clock problem, not because it's less important | ⬜ not started — bead not yet created |

**Next-run pointer (read this first):** #1, #2, and #3 are all closed out —
#3's remaining live-verify item (`test_import.py`'s `scn_other`
fixture-shortcut) **PASSED live 2026-08-07** on `plan-0806-flake-recovery.md`
S3's attempt #6, after S1/S2 in that plan fixed the two harness defects
(`invoke_fixture`'s retry gap, and F9's diagnostic-capture ordering) that had
been absorbing the prior 5 attempts as generic infra flake. See that plan's
S3/S4 Result blocks and the updated `#3` priority-table row above for the
full record — this doc's own `#3b` section below is left as historical
record of the investigation, not updated further. **Next unblocked item is
#4** (`scripts/check_coverage.py` refresh — not blocked on anything, pure
audit/wiring work; already picked up as `plan-0806-flake-recovery.md` S0),
followed by S5 in that plan (full-suite `pytest -x`, flips `gts-ir1f`,
`gts-z6bx`, `gts-hroj` to `regression=verified`).
`test_team_folder_reconciliation.py` and `test_sync_all.py`'s
batchable subset are both done and verified live (see AC below).
`test_import.py` and `test_team_scope.py` have now both been **audited and
found to contain zero `syncAll()` call sites** — every sync in both files is
`.sync()` (per-doc `syncDocument()`), which the syncAll()-sweep-batching
technique used for the first two files does not apply to at all (there is no
shared sweep across docs to consolidate; each `syncDocument()` call is
inherently scoped to one doc's own content). **This narrows `gts-ir1f`'s
remaining scope to zero further syncAll-batching work** — see the "What this
narrows" note below.

One adjacent, smaller optimization was found and applied in `test_import.py`:
`test_import_flow_forward_sync`'s `scn_other` (other-team negative-visibility
leadup doc) was converted from a real `_move_to_folder` + `scn.sync()` +
`_seed_open_action` (2 live `syncDocument()` round trips) to the file's own
already-established `_seed_import_candidate` fixture-shortcut (fabricates the
Actions-row + DocData join `list_importable_actions` actually reads, same
pattern already used for the identical negative-visibility check in
`test_import_access_filter`). Code change is applied
(`tests/test_import.py`) but **not yet live-verified**: 3 consecutive live
runs of `test_import_flow_forward_sync` each failed on a different GAS-side
symptom before/independent of the reached-or-not code path — (1) non-JSON
echo-page response from the session-scoped `reset_test_state` fixture (fails
before any test code runs), (2) bare HTTP 404 "Page Not Found" from
`find_sheet_actions` on `scn_src1` (unrelated doc, unrelated code path) after
exhausting `_http_post`'s built-in 3-attempt retry, (3) `open_sidebar` timeout
on `scn_target` with the doc unexpectedly showing a "Take out of trash"
button. All three are the documented `/exec`-routing flake class (F1/F7,
`gts-pm72`), not attributable to this change — none of the three failures
touched `scn_other` or `_seed_import_candidate` at all. Per this project's
Backstop rules, retried was not repeated a 4th time; **whoever resumes should
re-run `pytest tests/test_import.py::test_import_flow_forward_sync -v`
once, and if it stays flaky, treat 3 different infra symptoms in 3
consecutive live runs as its own signal worth flagging (possible worsening
of the F1/F7 class) rather than routine bad luck.**

`test_team_scope.py` (file 4) needs no code change — it also has 0
`syncAll()` calls, and unlike `test_import.py` it has no equivalent
fixture-shortcut opportunity already established in-file to extend (each
test there directly asserts `syncDocument()`'s own team-scope-resolution
behavior — `_syncTeamScope`/`assertTeamAccess` are the entry points under
test, so a real sync is the point, not overhead to shortcut around).

`test_sync_all.py`
itself is now fully triaged and does NOT need revisiting: `test_sync_all`
is already the batched exemplar the file is named for (untouched);
`test_mark_doc_not_found_no_restamp_on_reconfirm`,
`test_sync_all_collapses_duplicate_globalid_rows`, and
`test_sync_all_duplicate_globalid_dedup_does_not_regress_reanchor_path`
drive `scn.sync()` (per-doc `syncDocument()`), not `syncAll()` — a cheap
entry point, out of this retrofit's scope regardless of tag wording;
`test_sync_all_op_correlation` / `test_sync_all_op_propagates_to_webapp`
are inherently about op-id identity *differing* across separate `syncAll()`
invocations, so batching would defeat the assertion — correctly a
"when NOT to batch" case, left solo; `test_sync_all_retries_transient_drive_5xx`
/ `..._exhausted_drive_5xx_retry_still_recovers_via_fallback` use a
**globally-scoped** fault counter (`_TEST_FORCE_DRIVE_5XX_COUNT` — unlike
the per-doc-scoped `*_force_listing_miss`/`*_force_team_walk_error`
fixtures, this one intercepts the first N Drive REST calls in the sweep
regardless of doc), so combining them with any other scenario's sweep
would leak the forced failure onto that scenario's doc too — also
correctly left solo. Note for whoever continues #3: `gts-pm72`'s fix added
that `sync_all_force_drive_5xx` fixture and the two tests just named.
Also carry forward the pattern discovered while batching
`test_team_folder_reconciliation.py` and confirmed again here:
`syncAll()` sweeps the *entire* shared backlog spreadsheet regardless of
which doc's session calls it (`testDocId` only scopes fixture setup, not
the sweep — see `src/TestWebApp.js::_handleRunFixture`), and per-doc
`*_force_*` fault fixtures (`sync_all_force_team_walk_error`,
`sync_all_force_listing_miss` — but explicitly NOT
`sync_all_force_drive_5xx`, see above) intercept only their target doc, so
`sync_all_force_drive_5xx`) intercept only their target doc, so multiple
independent scenarios' fault-injection can share one sweep as long as at
most one fault fixture is invoked per shared sweep.

## Action log

### #1 — Stop using `--sw` for full sweeps (done 2026-08-06)

Scan for a pre-existing enforced default first: `package.json`'s `test:full`
script already omits `--sw` (uses no stepwise flag at all), so the only real
gap was that the *policy* wasn't written down anywhere a future session would
find it before reaching for `--sw` out of habit (as the prior handoff's own
session did — see `work-log.md` around 2026-08-05, "Diagnose gts-pytest5.log
failure and resume pytest --sw"). Fix: document the policy in `CLAUDE.md`
where testing-process guidance already lives, next to the existing "route
long-running test output to a file" rule.

**AC:**
- [x] Confirm no build script (`package.json`, CI config) currently defaults
      to `--sw` for full sweeps — checked, none do.
- [x] Document the no-`--sw`-for-full-sweeps policy in a location a future
      session will read before starting a full run — added to
      `CLAUDE.md` §Testing Strategy & Issue Conventions, immediately after
      the existing long-running-test-output rule.
- [x] Policy statement names the alternative (non-stopping full pass +
      bulk triage from the persisted log) so it's actionable, not just a
      prohibition.
- [x] Cross-reference back to this doc so the rationale (Google `/exec`
      routing flakiness, `gts-pm72`) isn't orphaned from the rule.
- [x] No bd bead required (doc says "process change, no bead needed") —
      confirmed, none created.

### #2 — Fix GAS-side retry gap, `gts-pm72` (done 2026-08-06)

Added a shared `_fetchDriveWithRetry` helper in `src/SyncManager.js` (3
attempts, 1s backoff, mirroring `scn/session.py::_http_post`'s convention)
and wired it into the two Drive REST call sites in SyncManager's
folder-walk/metadata path: `_fetchDriveDocMetadata` (the `files.list` bulk
listing whose uncaught 500 was the measured incident) and
`_fetchSingleDocMetadata` (the per-doc fallback "sibling" the AC named).
Only 5xx is retried — a 4xx is a real answer, not transient noise, and
surfaces immediately as before. Test-only fault injection
(`_TEST_FORCE_DRIVE_5XX_COUNT` script property, consulted by
`_driveFetchTestOverrideCode`, swept automatically by `reset_test_state`'s
existing `_TEST_` prefix convention) lets a test simulate N consecutive
transient 500s without depending on a real Google-side outage lining up
with a test run — new `sync_all_force_drive_5xx` fixture in
`src/TestFixtures.js`, following the existing monkey-patch-fixture
convention (`sync_all_force_listing_miss`, `sync_all_force_team_walk_error`).

**AC** (from the bd issue, verbatim scope):

- [x] GAS-side Drive/Sheets Advanced-Service calls known to intermittently
      return 5xx (files.list and siblings used by SyncManager's team-scope
      folder-walk) are wrapped in a bounded retry (~3 attempts, short
      backoff) inside the GAS source — `_fetchDriveWithRetry` in
      `src/SyncManager.js`, applied to `_fetchDriveDocMetadata` and
      `_fetchSingleDocMetadata`.
- [x] A single transient 500 no longer surfaces as `sync.driveMetadata.error`
      and does not fail a live test — proven by
      `tests/test_sync_all.py::test_sync_all_retries_transient_drive_5xx`
      (forces 1 failure, asserts `assert_no_log` on
      `sync.driveMetadata.error`, asserts row state unchanged). **PASSED**
      against live TEST deployment, 2026-08-06 (85s).
- [x] **Backstop rule** — the new resilience path is proven to actually work
      on an injected/simulated 500, not just assumed: same test above is the
      proof (pre-fix, any forced-5xx count throws and logs the error tag
      immediately — this assertion would fail against that build).
- [x] Retry is bounded, not silently infinite or skipped, and the
      pre-existing per-doc fallback (gts-rskf) still keeps a sweep correct
      once the bound is exhausted — proven by
      `tests/test_sync_all.py::test_sync_all_exhausted_drive_5xx_retry_still_recovers_via_fallback`
      (forces 5 failures, i.e. beyond the 3-attempt budget; asserts the
      error tag DOES eventually log, but no row is misclassified
      'Doc Not Found'). **PASSED** against live TEST deployment, 2026-08-06
      (187s). This case isn't in the bd AC verbatim but closes the obvious
      "what if it's not transient" gap the AC's wording leaves open.
- [x] bd issue closed with resolution note; `regression=pending` set (fast,
      targeted-subset gate only — `pytest tests/test_sync_all.py -k
      drive_5xx`, 2 passed in ~5 min against live TEST GAS deployment; full
      `pytest -x` not yet run against this change). Per this project's
      Backstop rules (CLAUDE.md §Testing Strategy), flip to
      `regression=verified` the next time a full `pytest -x` run is clean
      and covers this change — do not merge to master before that.
- [ ] Full-suite `pytest -x` confirmation — **not yet run**; this is the one
      open item carried forward. Whoever next runs the full suite: run
      `bd set-state gts-pm72 regression=verified --reason "pytest -x clean"`
      once it passes clean.

### #3 — Retrofit sync-batching, `gts-ir1f` (in progress, started 2026-08-06)

Scope is 4 files (~65 sync-call-sites total per the doc's own count).
This session converted the first two — `test_team_folder_reconciliation.py`
(its 4 `gts-sl64` scenarios) and `test_sync_all.py`'s batchable subset
(GTaskSheet-cduk + `gts-m33k`'s listing-miss + revival scenarios) — end to
end and proved both live. `test_sync_all.py` is now fully triaged: no
further scenarios in that file qualify for batching (see the "Next-run
pointer" above for why each remaining test stays solo). 2 files remain
(`test_import.py`, `test_team_scope.py`). Re-prioritized P3→P2 in bd per
this doc's own recommendation before starting.

**Shape used (`test_team_folder_reconciliation.py`):** the 4 original
tests each drove their own independent `syncAll()` sweep(s) against the
*entire* shared backlog spreadsheet (confirmed: `syncAll()` is not scoped
to `testDocId` — that field only steers fixture setup, per
`src/TestWebApp.js::_handleRunFixture`). Collapsed into ONE test,
`test_syncall_team_reconciliation_batch`: 4 independent docs are set up
first (still isolated per-doc, per run-isolated-clones), then exactly 2
shared sweeps — one seed sweep (needed because AC2's UpdateDoc-skip check
requires syncState to already exist, a real sequencing dependency, not
force-fit away) and one final verification sweep. The final sweep uses
`sync_all_force_team_walk_error` (needed for AC4's fault injection) and
relies on that fixture intercepting only its target `docId` — every other
batched doc reconciles for real in the same call. Per-scenario assertions
kept individually tagged (`[sl64 AC1]` etc.) so a failure still names which
scenario broke.

**Shape used (`test_sync_all.py`):** audited all 11 non-exemplar tests in
the file (see Next-run pointer for the full per-test disposition); only 3
turned out to be genuine batching candidates — `test_docdata_integrity_pass`
(cduk, 1 sweep), `test_sync_all_survives_drive_listing_miss` (m33k, 1
sweep, per-doc-scoped fault), and `test_sync_all_revived_before_24h_not_archived`
(m33k, inherently 2 sweeps — trash-detect then untrash-revive). Collapsed
into ONE test, `test_sync_all_integrity_and_listing_miss_batch`: cduk's
DocData corruption, the listing-miss doc's normal sync, and the revival
doc's trash all set up first, then a SEED sweep driven by
`sync_all_force_listing_miss` (targeting only the listing-miss doc — cduk's
and the revival doc's docs reconcile for real in the same call, same
per-doc-fault-scoping pattern as `test_team_folder_reconciliation.py`)
covers cduk's integrity-pass correction, the listing-miss survival check,
AND the revival doc's Sweep-1 trash-detection simultaneously. A FINAL
sweep (plain `sync_all`, revival-only — untrash then re-sweep) is needed
only because revival's own AC is inherently sequential; cduk and
listing-miss need nothing further from it. 4 sweeps across 3 original
tests collapsed to 2 shared sweeps.

**AC** (from the bd issue, verbatim scope — this entry covers files 1-2 of 4):

- [x] Candidate test files/scenario groups identified — confirmed
      `test_team_folder_reconciliation.py`'s 4 `gts-sl64` scenarios as a
      genuine batching candidate (not just "clearest" per the bead's
      description): each scenario is on an independent doc, and the two
      apparent NOT-to-batch flags (AC2's 2-sweep dependency, AC4's fault
      fixture) both turned out to be per-doc-scoped or satisfiable via a
      seed+final split rather than disqualifying.
- [x] Identified batchable group converted to single-sweep-per-batch shape
      (here: seed+final, 2 sweeps instead of up to 11) — per-scenario
      assertions remain independently attributable (tagged, see shape
      above).
- [x] Wall-clock measured for the converted file — **PASSED** against live
      TEST deployment, 2026-08-06: `total=393.87s (setup=86.03s call=305.01s
      teardown=2.83s)`, single pytest invocation
      (`pytest tests/test_team_folder_reconciliation.py -v`, exit 0, full
      log preserved at
      `/tmp/claude-1000/-home-stuar-proj-GActionSheet/b3a47bce-3849-422a-9901-6dce66639437/scratchpad/ir1f-batch-test.log`).
      **Improvement is structural/code-verified, not a re-measured
      before/after**: the old file's 4 tests called `syncAll()`-driving
      fixtures 5 times in the no-retry-needed case (AC1×1 + AC2×2 + AC3×1 +
      AC4×1) up to 11 times in the worst case (AC1's and AC3's
      `_sync_all_until_team` retry loops each allow up to 4 attempts on
      Drive-index lag); the batched version calls exactly 2 in the observed
      no-retry-needed run (confirmed by the single PASSED result with no
      retry-loop sleep visible in the timing), up to 5 in the same worst
      case. That's a 55-60% reduction in live `syncAll()` sweeps for this
      file. The old 4-test file was not re-run for a literal side-by-side
      timing (would cost another live-GAS cycle for a number this
      structural count already establishes) — if a literal before number is
      needed later, the pre-retrofit file is recoverable via
      `git show <commit-before-this-one>:tests/test_team_folder_reconciliation.py`.
- [x] No loss of coverage or Backstop-rule compliance — all 4 original
      assertions (AC1 reconcile, AC2 override-preserved, AC3 cleared, AC4
      unchanged-on-fault) are present verbatim in the batched test with the
      same tags and the same `entry_point="syncAll"` `expect_callable` +
      `checkpoint(STEP)` calls as before; nothing was dropped to make the
      batch fit.
- [x] Sequencing-dependent tests explicitly handled, not force-fit — AC2's
      2-sweep requirement is preserved as the batch's seed+final split
      rather than collapsed into 1 sweep (see Shape above).
- [x] `test_sync_all.py` batchable group converted and measured —
      **PASSED** against live TEST deployment, 2026-08-06:
      `total=228.50s (setup=4.14s call=224.35s teardown=0.01s)`, single
      pytest invocation
      (`pytest tests/test_sync_all.py::test_sync_all_integrity_and_listing_miss_batch -v`,
      exit 0, full log preserved at
      `/tmp/claude-1000/-home-stuar-proj-GActionSheet/b3a47bce-3849-422a-9901-6dce66639437/scratchpad/ir1f-sync-all-batch-test.log`).
      3 original tests' 4 sweeps (cduk×1 + listing-miss×1 + revival×2) →
      2 shared sweeps, a 50% reduction, code-verified the same way as file
      1 (no separate before/after re-run of the pre-retrofit tests).
- [x] No loss of coverage for the `test_sync_all.py` batch — all 3
      original tests' assertions (cduk AC1-AC4, m33k listing-miss survival,
      m33k revival) are present verbatim with the same tags and the same
      `entry_point="syncAll"` `expect_callable` + `checkpoint(STEP)` calls.
- [x] Sequencing-dependent test explicitly handled, not force-fit —
      revival's 2-sweep requirement is preserved as the batch's seed+final
      split (see Shape above), matching the same pattern used for
      `test_team_folder_reconciliation.py`'s AC2.
- [x] Remaining tests in `test_sync_all.py` audited and correctly excluded
      from batching, not silently skipped — see "Next-run pointer" above
      for the full per-test disposition (3 use `scn.sync()` not
      `syncAll()`, out of scope; 2 are inherently about per-invocation op-id
      identity, batching would defeat them; 2 use a globally-scoped fault
      counter incompatible with sharing a sweep).
- [x] Remaining 2 files (`test_import.py`, `test_team_scope.py`) — audited
      2026-08-06. **Both contain zero `syncAll()` call sites** — this
      finding is documented in full in the "Next-run pointer" section above
      and in the `#3b` action-log entry below, and narrows `gts-ir1f`'s
      syncAll-batching scope to files 1-2 only (fully covered). No
      syncAll-batching work remains to be started for these 2 files; the
      bead's original description scoped them as candidates without yet
      confirming they use the same entry point as files 1-2, and this audit
      is that confirmation, in the negative.
- [x] `test_import.py`'s one applicable adjacent optimization (the
      `scn_other` fixture-shortcut, not a syncAll-batching change — see `#3b`
      below) is code-complete and **live-verified 2026-08-07** —
      `plan-0806-flake-recovery.md` S3, attempt #6:
      `pytest tests/test_import.py::test_import_flow_forward_sync -v` →
      `1 passed in 379.58s`, log at `/tmp/jobs/ir1f-attempt6.log`. The prior
      3 consecutive infra-symptom failures were resolved not by luck but by
      that plan's S1 (fixed `invoke_fixture`'s non-retrying transport, the
      cause of 2 of the 5 prior failures) and S2 (fixed the F9
      diagnostic-capture-ordering bug that had been mis-rendering unrelated
      failures as a "doc in trash" recurrence).
- [ ] bd issue `gts-ir1f` stays OPEN. `regression=pending` on the changed
      files — targeted-subset/single-test gate only so far
      (`test_team_folder_reconciliation.py`, `test_sync_all.py`'s converted
      tests, and now `test_import.py`'s `scn_other` change all have live PASS
      above). No full-file or cross-file
      `pytest tests/test_sync_all.py -v` /
      `pytest tests/test_team_folder_reconciliation.py tests/test_sync_all.py -v`
      run yet either — only the individual new/changed tests were run.
      Full-suite `pytest -x` not yet run against this change (tracked as
      `plan-0806-flake-recovery.md` S5); per Backstop rules, do not merge to
      master before that run is clean and this flips to
      `regression=verified`.

### #3b — `test_import.py` / `test_team_scope.py` audit + partial adjacent fix (2026-08-06)

Continuation of `gts-ir1f`, files 3-4 of 4. Audited both files' sync-call
sites (`grep -c 'syncAll\|sync_all'` — 0 hits in either file; every sync site
in both is `.sync()` i.e. `syncDocument()` per `scn/session.py::sync`'s
docstring, which calls the `sync_document` fixture — GAS's `syncDocument()`,
not `syncAll()`). This is a structurally different entry point from the one
`gts-ir1f`'s batching technique targets: `syncAll()` sweeps the *entire*
shared backlog spreadsheet regardless of which doc's session calls it (the
property this whole retrofit exploits — see the "Shape used" notes on files
1-2 above), so N independent docs' `syncAll()`-driven scenarios can share one
sweep. `syncDocument()` has no such property — it operates on exactly the one
doc `DocumentApp.openById` was pointed at, so there is no shared-sweep
consolidation possible across N docs' `syncDocument()` calls; each one is
already minimal for what it does. **Conclusion: neither file has any
syncAll-batching work to do. This is a scope-narrowing finding for
`gts-ir1f`, not a gap.**

That said, `test_import.py` already contains a *different*, file-local
optimization pattern — `_seed_import_candidate` (added prior to this
session), which fabricates the Actions-row + DocData join
`list_importable_actions` reads via cheap fixture POSTs instead of paying for
a real `syncDocument()` round trip, for leadup docs where only the read/list
path is under test (not sync mechanics themselves). `test_import_access_filter`
already used this for its `scn_sibling`/`scn_other`/`scn_trashed` leadup
docs. Checked whether `test_import_flow_forward_sync`'s equivalent leadup doc
(`scn_other`, the other-team negative-visibility check) qualified: yes — it
is read-only leadup for the identical `importList`/`read_import_list` check,
never opened/synced for any other purpose in that test. Converted it from
`_move_to_folder` + `scn.sync()` + `_seed_open_action` (2 real
`syncDocument()` round trips) to `_seed_import_candidate(scn_other,
"TestTeamScopeAChild", "Import-flow other-team action")` (0 round trips),
removing the now-dead `team_a_child` local. This is NOT a `gts-ir1f`
syncAll-batching change — flagging it under this bead only because it was
found while auditing this bead's remaining scope, and it's the same
Google-API-exposure-reduction goal the bead's own description cites for
`test_import.py`.

Checked `test_team_view_page`'s equivalent other-team negative doc
(`scn_other_team`) for the same shortcut: `_handleTeamView`'s
`_readTeamActions` reads the same Actions-row + DocData join shape
(confirmed by reading `src/WebApp.js::_readTeamActions`, lines ~1814-1892),
so the shortcut is *structurally* eligible — but `_seed_import_candidate`
only sets `teamId`/`syncStatus` via `set_docdata_row`, never `docName`, and
`test_team_view_page`'s negative check
(`if other_team_name and other_team_name in html`) depends on
`_docdata_row(scn_other_team).get("docName")` being truthy — if a
fixture-only doc's `docName` comes back empty, that assertion would
short-circuit False and silently stop checking exclusion at all (a vacuous
assertion, exactly the class of bug `docs/lessons-learned/resolved/2026-06-02-new-assertion-vacuously-passes-on-empty-result-set.md`
already names). Did not verify whether `set_docdata_row`/`new_doc()`
populates `docName` without a real sync, so this conversion was **not
applied** — left as a real `sync()` rather than force-fit. If someone wants
this one too: confirm `docName` behavior first, then either extend the
fixture or set `docName` explicitly via `_set_docdata`.

**Live verification status:** the `scn_other` code change was exercised 3x
live (`pytest tests/test_import.py::test_import_flow_forward_sync -v`, no
`--sw`, each run in its own background invocation, logs at
`/tmp/claude-1000/.../scratchpad/ir1f-import-flow-test{,-retry,-retry2}.log`
in this session's scratchpad — not preserved past session end). All 3 failed
before or independent of the changed code:
1. `[12:16:45]→[12:17:29]`, 39s — session-scoped `_reset_test_state`
   autouse fixture (runs before any test body) got a non-JSON echo/debug page
   back from the WebApp instead of JSON for `run_fixture('reset_test_state')`.
2. `[12:17:50]→[12:24:44]`, 413s — `scn_src1.find_sheet_actions()` inside
   `_seed_open_action` (a helper this session did not touch) got a bare
   HTTP 404 "Page Not Found" from Drive after `_http_post`'s built-in
   3-attempt retry was exhausted.
3. (retry 2), 234s — `scn_target`'s `open_sidebar()` timed out at 15s;
   failure screenshot shows the doc's Drive chrome offering "Take out of
   trash" — unexplained, but again on `scn_target`, not `scn_other`.

None of the 3 failures reached or were caused by the `scn_other`/
`_seed_import_candidate` code path changed this session. All 3 match the
documented `/exec`-routing flake class (F1/F7 above, `gts-pm72`). Per this
project's Backstop rules ("known test failures are not a basis for
proceeding autonomously... wait for an explicit human decision"), did not
retry a 4th time. **3 different infra symptoms across 3 consecutive live
attempts of the same test in one session is itself worth flagging** — either
routine bad luck on a historically flaky test (`test_import_flow_forward_sync`
already has a documented history of exactly this per `gts-ir1f`'s own notes:
"failed 4 consecutive live-regression attempts on 4 different transient
Google-side symptoms... 2026-08-05"), or a sign the flake rate is worsening.
Not enough evidence either way from one session to conclude which.

**2026-08-06 continuation (resume run, attempt #4 overall this session-pair):**
Per this doc's own "Next-run pointer," re-ran
`pytest tests/test_import.py::test_import_flow_forward_sync -v` once, no
`--sw`, single foreground invocation
(log: `/tmp/claude-1000/-home-stuar-proj-GActionSheet/e0918cc8-9c38-4dc2-a640-cfc7b087dc79/scratchpad/ir1f-import-flow-resume.log`,
not preserved past session end). Result: **failed again**, `total=653.36s
(0:11:01)`, but for the first time reached and failed inside the actual test
body (AC1's `check_ac1()`), not a pre-test/setup barrier:
`AssertionError: expected source docs visible, got []` — `import_adapter`
returned zero visible doc ids, so neither `scn_src1` nor `scn_src2` (both
same-team, both should be visible) appeared in the Import tab list at all.
The UI failure diagnostics attached to the assertion show `scn_target`'s doc
chrome offering `['Go to Docs home screen', 'Take out of trash']` — i.e.
`scn_target` was in Drive trash at the moment `read_import_list()` ran.

**This is the same "target doc unexpectedly in trash" symptom as attempt #3
from the immediately preceding live-verification round** (documented above:
`open_sidebar` timeout on `scn_target`, "Take out of trash" button). Two
occurrences of the identical symptom on the identical doc role
(`scn_target`), across two consecutive live sessions of the same test,
originally read as a stronger and more specific signal than "3 different
infra symptoms" — investigated further per explicit instruction (see below).

**Investigation (2026-08-06, same session): the "trash" symptom is a false
lead — a diagnostic-capture ordering artifact, not a recurring product/infra
bug.** Root cause: `test_import_flow_forward_sync`'s `finally:` block
(tests/test_import.py:561-567) calls `end_journey_session` — which trashes
the doc (`src/AtddContracts.js` "trash the journey doc at teardown") — for
every session in `sessions`, including `scn_target`, unconditionally on any
exit path (success or exception). This `finally` executes as part of
Python's normal exception unwinding *inside* the test function, which
completes (finally included) before pytest's `pytest_runtest_makereport`
hookwrapper (`tests/conftest.py:123`, the GTaskSheet-3tkf diagnostics hook)
ever runs — that hook only fires once the "call" phase is fully resolved.
So by the time the hook takes its screenshot and describes visible buttons,
**`scn_target` has already been trashed by the test's own teardown**,
regardless of what actually caused the assertion to fail. This applies to
*any* assertion failure in this test, not something specific to attempt #3
or #4 — grep confirms the same `sessions` + `finally: ... end_journey_session`
shape is used by `test_import.py`, `test_team_scope.py`, `test_journey.py`,
`test_sync_all.py`, and `test_kkm7_batching.py`, so this is a structural gap
in the GTaskSheet-3tkf diagnostics feature for this whole class of
multi-doc live tests, not a one-off. **Filed as new finding F9** (below) —
worth a dedicated fix independent of this bead.

With the "trash" clue debunked, attempts #3 and #4 are two *different*
underlying failures that happen to render the same misleading screenshot,
not one recurring bug:
- Attempt #3: `open_sidebar` timed out (15s) — the sidebar iframe carrying
  the "Sync" button never appeared in time.
- Attempt #4: `read_import_list()` (which already polls up to 15s for the
  card to render — `scn/ui.py:1037`, ruling out a simple render race) came
  back with zero groups for both `scn_src1` and `scn_src2`.

Neither points at the `scn_other`/`_seed_import_candidate` change (unrelated
doc, unrelated code path in both cases). Both are consistent with — though
not conclusively proven to be — the already-documented `/exec`-routing /
Drive-listing-lag flake class (F1/F7, `gts-pm72`): attempt #2 in the same
run hit a literal Drive 404 on a sibling doc via the same class of call, and
an empty (not partial/wrong) import list is more consistent with the
server-side read failing outright than with an app-logic bug picking the
wrong rows. Not proven without another live reproduction. Per Backstop
rules, **not retried a 5th time without explicit go-ahead** — the earlier
"needs investigation" blocker is resolved (no new bug found), but live
verification of the `scn_other` change is still outstanding; see AC below
and the prioritization table's Status column.

**AC** (adjacent-fix scope, not `gts-ir1f`'s core AC):
- [x] `test_import.py`/`test_team_scope.py` audited for syncAll() call
      sites — 0 found in either file, confirmed via grep + `scn/session.py`
      docstring cross-check.
- [x] `test_import_flow_forward_sync`'s `scn_other` converted to
      `_seed_import_candidate` — code change applied, diff is 2 lines
      removed (real sync leadup) for 1 line added (fixture-shortcut call) +
      1 dead-local removal (`team_a_child`).
- [x] `test_team_view_page`'s equivalent `scn_other_team` conversion
      evaluated and explicitly NOT applied — vacuous-assertion risk
      identified and documented (docName dependency), not force-fit.
- [x] Investigate the recurring "`scn_target` in trash" symptom (2/4
      attempts) — **root-caused, not a product/infra bug**: it's a
      diagnostic-capture-ordering artifact of the test's own
      `finally`-block teardown racing pytest's failure-screenshot hook (full
      analysis above, filed as new finding **F9**). No lifecycle bug found
      in `_move_to_folder`/`.sync()` or any concurrent cleanup fixture — the
      trash is real, but it's this test's own intentional teardown, already
      executed by the time the diagnostic screenshot is taken, for any
      failure reason whatsoever.
- [x] Live verification of the `scn_other` change — **PASSED 2026-08-07**,
      attempt #6 (`plan-0806-flake-recovery.md` S3), on the first try after
      the two harness defects behind attempts #1–#5's symptoms were fixed:
      `pytest tests/test_import.py::test_import_flow_forward_sync -v` →
      `1 passed in 379.58s`, log `/tmp/jobs/ir1f-attempt6.log`. 1 of the
      2-attempt budget authorized for attempt #6/#7 was used; the 2nd was not
      needed. This closes out the item this doc's prior "5 distinct symptoms,
      all F1/F7-class" analysis had left open — that analysis is preserved
      above as the historical record of why 5 attempts failed; it was correct
      that none of them pointed at a bug in the `scn_other` change itself, and
      the eventual pass confirms that reading.

## What this doc deliberately does not decide

- Whether to enable parallelism (#5) — needs your call on whether the
  team/folder test fixtures are actually run-isolated per T9 today, not just
  a scan-level guess.
- Whether `test_journey_acts_1_3.py` is intentional double coverage or
  accretion (#7) — needs someone to read both files' assertions, not just
  docstrings.
- Concrete runtime budget numbers for #8 — should be set from a real
  baseline, not this scan's spot numbers.

## Not covered here

`gts-lirp`'s root cause investigation and `gts-pm72`'s implementation are
already fully scoped in their respective beads; this doc doesn't re-derive
them, only sequences them against the new structural findings.

### F9 — GTaskSheet-3tkf failure diagnostics captured after test's own teardown already trashed the docs (found 2026-08-06)

For any live UI test that (a) creates multiple `ScenarioSession`s into a
`sessions` list and (b) trashes them all in a `finally:` block via
`end_journey_session` — confirmed present in `test_import.py`,
`test_team_scope.py`, `test_journey.py`, `test_sync_all.py`, and
`test_kkm7_batching.py` — the `finally` block runs as part of the test
function's own exception unwinding, which completes *before*
`pytest_runtest_makereport` (`tests/conftest.py:123`, the GTaskSheet-3tkf
diagnostics hook) fires for the "call" phase. Result: the failure
screenshot/button-description always reflects the *post-teardown* (already
trashed) state of every doc in `sessions`, not the state at the moment the
assertion actually failed. This isn't wrong data exactly — the doc really
is in trash by the time the screenshot is taken — but it's a **misleading
signal for root-causing**: any assertion failure in these tests will show
"Take out of trash" in the diagnostics regardless of the real cause,
inviting exactly the false "recurring trash bug" reading this doc's own #3b
section made before investigating (see corrected `#3b` entry above).

**Fix shape (not yet built):** capture the GTaskSheet-3tkf diagnostics
*before* the test's own `finally`-block teardown runs, not after. Two ways
to get there: (a) move diagnostic capture into a `pytest_runtest_call`
hookwrapper that snapshots on exception *before* the test function's own
`finally` executes (requires hooking earlier in the phase, not after "call"
resolves) — likely the more general fix since it covers all 5 affected
files without touching each one; or (b) have each affected test's `finally`
block call `capture_failure`-equivalent logic itself before trashing, mirroring
the existing convention CLAUDE.md already states for bounded waits ("Add a
new bounded wait? Route its failure through `capture_failure`"). Needs a
design decision on which approach, then a `[TST]`-prefixed retroactive-path
bead per this project's Path B convention (regression coverage gap: the
diagnostics feature silently produces misleading output for a known test
shape, a real defect in test tooling itself).
