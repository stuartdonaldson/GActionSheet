# Technical Debt Plan — 2026-08-20

Source: evaluation of `/tmp/gas-test.log` (full regression sweep, 480 tests, 460
passed / 4 failed / 16 skipped, wall-clock 1:58:56) plus a scan of open `bd`
issues for accumulating debt. Triage beads for the 4 failures are filed under
epic `gts-obry`. This document is the prioritization layer on top of that —
what to fix next to make the suite and codebase cheaper to run and maintain.

**2026-08-21 update (third session): `/tmp/gas-test4.log` — 39 failed / 449
passed / 16 skipped / 6 errors, 2h21m35s.** This is a sharp regression in
failure *count* from the intervening `gas-test3.log` run (19 failed / 14
errors, triaged as epic `gts-f3me`) and from `gas-test2.log` (2 failed) — but
it is **not** mostly a code regression. It is `gts-f3me.4`'s own AC3 soak-test
run (">2h live run to confirm no recurrence" of the stale-auth-session bug),
and it confirms the fix shipped for that bug does not hold: **~38–40 of the 45
fail/error outcomes trace to one root cause — the shared Playwright auth
session (`~/.playwright/sdonaldson.json`) was fully signed out for this run's
entire 2h21m duration**, not merely rotating (the case the shipped fix
handles). Direct evidence: this run's own UI-failure screenshots show the
Google account-chooser page with "Stuart Donaldson … Signed out". New triage
epic **`gts-85x3`** tracks this and 4 genuinely distinct remaining issues; see
§-1 below (inserted ahead of §0, which stays as-is for record).

## -1. Third-session update — `gts-85x3`: gas-test4.log (39 failed / 6 errors)

### Why this run has so many more failures than gas-test2/gas-test3

Not a code regression sweep in the usual sense — a single environmental
failure (dead shared auth session) fans out through **two independent
surfaces** that both depend on it, each producing its own failure per test
that touches it:

1. **`tests/helpers/download.py`** (requests-based xlsx/docx export) — hits
   Google's login HTML page instead of the OOXML file →
   `DownloadError: Response is not xlsx/docx (got b'<!doctype html><html')`.
   ~20 direct hits, plus several more masked behind
   `scn.engine.DrainInvariantError` at `checkpoint()`/teardown (the *real*
   exception is visible only via "During handling of the above exception…" —
   this is `gts-kkwp`'s own finding, reproduced again here).
2. **Playwright browser context** (`browser_page` fixture, and the
   `open_sheet.js` node helper `test_infrastructure.py`'s `TestMenuHandler`
   shells out to) — same dead session, different symptom:
   `Page.wait_for_selector: Timeout 30000ms exceeded` waiting for
   `.docs-title-outer` (the doc/sheet never finishes loading because Google
   shows a sign-in interstitial instead). ~15 hits across
   `test_sidebar.py`, `test_journey.py`, `test_import.py`,
   `test_ui_smoke.py`, `test_link_preview.py`, `test_infrastructure.py`.

`gts-f3me.4` (in progress) already shipped a proactive/reactive
cookie-*rotation* refresh for surface 1, live-verified against a real
rotation case on `gas-test3.log`. That fix is necessarily blind to a fully
signed-out session, by its own docstring's stated scope ("a fully
expired/signed-out session still requires re-running
`tests/playwright/auth.setup.js` by hand") — and it silently re-attempts and
re-writes a still-bad `storage_state.json` on every single call instead of
failing loud once, which is why a dead session was free to burn the entire
2h21m run one test at a time instead of failing in minute one. Full
disambiguation and evidence recorded on `gts-f3me.4`'s notes — read that
before re-deriving any of this.

**The remaining ~5 outcomes are genuinely distinct**, not part of the auth
cluster:

| Test | Symptom | Child bead |
|---|---|---|
| `test_run_fixture_same_opid_is_not_duplicated`, `test_run_fixture_different_opid_is_not_deduped` | Socket-level 120s read timeout — GAS never responds at all | `gts-85x3.2` (**P0** — new code, this session's own branch) |
| `test_table_cell_actions_distinct` | Caught a *foreign* `sync.all.error` from a concurrent sweep — `scn/session.py`'s own error-scan fence has no op/parentOp scoping (known, previously-noted-but-unfixed gap, see §0 below) | `gts-85x3.3` |
| `test_syncall_batches_multi_doc_listing_miss_fallback` (uuse) | One `batchFallback` event found (no more duplicate-event symptom — `gts-f3me.2`'s dedup fix helped), but its `count` is 3 not the expected 2 | `gts-85x3.4` |

### Prioritized staged plan

**Stage A (P0, do first, blocks any further live-suite run):**
1. **Operational, right now:** re-run `node tests/playwright/auth.setup.js`
   by hand for the `sdonaldson` primary role — the account is signed out on
   disk; no amount of automated retry fixes that.
2. `gts-85x3.2` — the two `run_fixture` idempotency tests hung 120s+ on
   their *first* request, not a routing flake. This is new code from this
   session's own branch (`src/TestWebApp.js`'s CacheService-based opId
   dedup, `gts-f3me.2`'s fix). Treat as a likely real hang/deadlock until
   disproven by an isolated re-run — release-blocking if confirmed.

**Stage B (P1, before the next long soak run):**
3. `gts-85x3.1` — give `download.py` a fail-fast circuit breaker: if the
   reactive refresh's retry is *still* stale, raise a distinct
   "session is fully signed out, run auth.setup.js" error immediately
   instead of letting every subsequent test rediscover the same dead
   session one at a time. Extend the same probe to `browser_page` if
   feasible, so the UI-timeout cluster gets the same fast, clear failure.
4. `gts-kkwp` — bounded retry + stop masking `DownloadError` behind
   `DrainInvariantError`. Won't save a fully-dead-session run by itself
   (retrying a dead session just re-fails), but collapses the failure
   signal to one clear message per test and helps the genuinely transient
   case `gts-f3me.4` was originally written for.

**Stage C (P2, real but lower-urgency bugs surfaced this run):**
5. `gts-85x3.3` — scope `scn/session.py`'s own GAS-error-scan fence by
   op/parentOp, same mechanism `gas_log.py::matches_op` already provides
   (extend, don't fork — TD-PLAN rule #2). This is the second contention
   vector §0 already flagged as a known follow-up; this run is the second
   live occurrence.
6. `gts-85x3.4` — disambiguate the uuse `count=3` mismatch (contention vs.
   stale test assertion), same method as `gts-obry.1`/`gts-7vo2.2`.

**Stage D (verification, don't skip):**
7. Once Stage A+B land, re-run a full soak (`pytest -x`, full suite,
   >2h wall-clock) as `gts-f3me.4`'s actual AC3 — this is now the *third*
   attempt at that AC, so budget for the possibility Stage A/B doesn't fully
   close it either and needs a second pass before `gts-f3me.4` can close.
8. Do not treat this branch as merge-ready until `gts-85x3` and its children
   resolve and a subsequent clean run confirms it, per the Backstop rules
   (known failures are not a basis for proceeding autonomously).

**2026-08-20 update (second session, same day):** the external `pytest -x`
run this plan's §1 was waiting on has now happened
(`/tmp/gas-test2.log`, 487 collected, 469 passed / 2 failed / 16 skipped,
1:51:53). Good news: all 4 of `gts-obry`'s original failures are gone —
**`gts-obry` is now closed.** Bad news: 2 *different* tests failed. New
triage epic **`gts-7vo2`** tracks them; see §0 below (inserted ahead of the
now-historical §1-§6, which stay as-is for record but are superseded where
this update says so).

## 0. Second-session update — `gts-7vo2`: 2 new failures on `gas-test2.log`

| Test | Child bead | Class |
|---|---|---|
| `test_sidebar.py::test_sidebar_header_branding` | `gts-7vo2.1` | **Confirmed real test-code bug**, not a flake |
| `test_sync_all.py::test_sync_all_op_propagates_to_webapp` | `gts-7vo2.2` | **Confirmed recurrence** of §2's account-contention theory — this time caught by the op-correlation mechanism §2 itself proposed |

### `gts-7vo2.1` — wrong exception type caught, not flaky UI

`tests/test_sidebar.py:387` has `except TimeoutError:` guarding
`s.ui.open_sidebar(timeout="5s")` on the error-fallback path, where a
timeout is the *expected*, harmless outcome (comment confirms this — the
error card never renders a "Sync" button). But Playwright raises
`playwright._impl._errors.TimeoutError`, which does **not** subclass the
builtin `TimeoutError`
(verified: `issubclass(playwright.TimeoutError, TimeoutError) == False`).
So the except clause can never actually catch it — any time the add-on icon
takes >5s to reappear after the forced-error reload (a real possibility on a
cold Google Docs chrome reload), the exception propagates uncaught and fails
the test. This is not "UI took too long this run," it's "this code path was
never able to do what its own comment says it does." Small, mechanical fix
(catch the right type); low priority only because it's cheap and isolated,
not because it's low-confidence.

### `gts-7vo2.2` — the contention theory from §2 just got direct proof

`test_sync_all_op_propagates_to_webapp` (GTaskSheet-j8cn) is the test
*built* to detect cross-sweep contamination via `op`/`parentOp`
correlation. It failed by finding exactly 2 `sync_action_rows` webapp
entries in its fence window — the expected count — but **both** carried a
`parentOp` belonging to a different sweep, not this test's own. That's a
concurrent `syncAll()` (almost certainly a `gts-li3g`-family installed
trigger) firing during the fence window and producing calls that happen to
match the expected shape closely enough to pass the weaker checks and only
fail the specific-identity check. This elevates §2's "recommended action"
(give `gas_log.py`'s fence matching an `op`/`parentOp` filter) from a
should-do to a should-do-next — it's no longer a hypothesis being defended,
it's the mechanism that just caught a live occurrence and still needs to be
taught to *filter it out* rather than merely flag it as a failure.
**Do not re-run `gts-obry.1`'s installed-trigger disambiguation from
scratch — read its notes first.**

**AC — Stage 0 (`gts-7vo2` epic, both children): ✅ DONE (closed 2026-08-20)**
- [x] `gts-7vo2.1`: except clause in `tests/test_sidebar.py` catches the
      actual exception type(s) `s.ui.open_sidebar(timeout="5s")` can raise on
      its error-fallback path (both Playwright's own `TimeoutError` and the
      builtin one `open_sidebar`'s own deadline path raises) — widened to
      bare `except Exception:` per the bead's own accepted alternative (this
      call site already treats any failure to find the Sync button as
      expected-and-ignorable)
- [x] `gts-7vo2.1`: isolated re-run of `test_sidebar_header_branding` passes
      — PASSED (64.87s)
- [x] `gts-7vo2.2`: trigger-timing cross-check done against the failure
      window — **disproven for this occurrence**: Axiom shows the
      contaminating `parentOp` belongs to a `sync.all.start` series firing
      every ~2–3 min (docCount 118→122 across 22:20:45Z–22:27:30Z), not a
      30-min cadence — `gts-li3g`'s installed trigger is not the source
      here; a concurrent TEST-account session/process is. See bead notes for
      full timestamp cross-reference.
- [x] `gts-7vo2.2`: `gas_log.py` gets an `op`/`parentOp`-aware filtering mode
      — **already existed** (`matches_op`, shipped by `gts-obry.1`,
      unit-tested in `tests/test_gas_log_op_correlation.py`); confirmed via
      prior-art check before writing anything new, per this project's I12
      rule
- [x] `gts-7vo2.2`: `test_sync_all_op_propagates_to_webapp` (j8cn),
      `test_syncall_batches_mark_doc_not_found_and_drive_metadata` (kkm7),
      and `test_syncall_batches_multi_doc_listing_miss_fallback` (uuse) all
      use the filtering mode — kkm7/uuse already did; j8cn updated to mint
      its own `opId` up front (kkm7/uuse convention) and filter both its
      `wait_for_log` and `collect_logs` calls through `matches_op`
- [x] `gts-7vo2.2`: isolated re-run of all three passes — all 3 PASSED
      together in one sequential pytest invocation (j8cn 116.43s, kkm7
      167.89s, uuse 130.52s). Along the way, running j8cn *concurrently*
      with the unrelated `gts-7vo2.1` re-run against the same shared TEST
      account produced a live, self-inflicted contamination failure
      (`scn/session.py`'s error-scan path, a *different* unscoped-fence
      mechanism than `gas_log.py`'s) — direct proof the contention risk is
      real, not just theorized; re-run strictly sequentially afterward
      passed clean.
- [x] `gts-7vo2.2`: `docs/OPERATIONS.md`'s contention Failure Modes row
      updated to say the mechanism now exists and is in use, not just that
      the risk exists
- [x] Both child beads closed 2026-08-20; `gts-7vo2` epic closed; TD-PLAN and
      `work-log.md` updated to record the outcome (this update)

**Follow-up noted, not fixed here (out of this stage's scope):**
`scn/session.py`'s own GAS-error-scan helper (~line 425–459) scans every
`*.error`-tagged log entry after a bare timestamp fence with **no**
op/parentOp scoping at all — a second, independent contention vector from
the one `matches_op` addresses, and the one that caused the concurrent-run
failure observed above. Candidate for a future bead if this recurs.

## How to pick up the next stage

Read this before touching any stage below — it's process, not per-stage
detail, so it isn't repeated per section.

1. **Read the bead's full notes before reading code.** Every stage below has
   a `bd show <id>` history — prior sessions' findings, dead ends, and design
   rationale live there, not in this file. Re-deriving something already on
   the bead (root cause, a ruled-out hypothesis, a design decision) is wasted
   session budget and risks landing a second, slightly different answer next
   to the first one. If the bead's own notes contradict this plan's summary,
   the bead is the source of truth — this file is a snapshot, not synced.
2. **Extend the existing mechanism before adding a new one.** This project
   already has: an `op`/`parentOp` correlation scheme (`GasLogger.startOp`,
   now fed by `scn/session.py::_http_post`'s `opId`/`initiatedAt`), a single
   HTTP choke point (`_http_post`) all live-backend calls funnel through, a
   fence-based log matcher (`tests/helpers/gas_log.py`), and sanctioned
   wrapper scripts (`query_axiom.py`, `call_webapp.py`). A stage that needs
   "a way to correlate calls" or "a way to query logs" almost certainly means
   *extend one of these*, not write a new query helper, a new retry loop, or
   a new correlation field with a different name doing the same job. Before
   writing new plumbing, grep for the existing shape (I12 prior-art check —
   same rule `implementation-gate` already enforces for any implementation
   work) and extend it in place.
3. **One fix per root cause, not one fix per symptom.** Several stages below
   share a root cause family (live-backend flakiness, account contention,
   `/exec` routing). Resist patching the specific failing test in front of
   you if the actual fix belongs one layer down (e.g. in `_http_post`'s retry,
   or in `gas_log.py`'s fence matching) — a local patch that doesn't touch the
   shared layer just means the next test in the same family fails the same
   way later, under a new bead, investigated from scratch again.
4. **Prefer disambiguating over re-guessing.** Several stages are explicitly
   "confirm or disprove" work, not "implement a fix" work — don't skip
   straight to a fix for the hypothesis that seems likeliest. An unconfirmed
   fix for the wrong hypothesis is debt of its own (a change that doesn't
   address the real cause, sitting in the codebase looking like it does).
5. **Close the loop on the same bead.** Append findings, decisions, and
   "ruled out" results to the stage's own bead via `bd update --append-notes`
   rather than opening a fresh bead for the same question — a fresh bead
   loses the thread and invites a second person (or session) to redo the
   investigation. Only open a new bead when the work is genuinely a
   *different* problem discovered along the way (e.g. `gts-obry`'s own
   pattern: one epic, child beads only for actually-distinct failures).
6. **A stage isn't done at "a plausible explanation."** Each stage's AC below
   states what "done" observably means — a passing isolated re-run, a live
   log entry showing a specific field, a bead updated with a verdict. Treat
   "I think this is contention" as a hypothesis to check off the list, not a
   result to close the bead on.

## 1. Regression sweep result (2026-08-20)

4 failed / 460 passed / 16 skipped. All 4 are now tracked under
**`gts-obry`** (epic) with one child bead per failure:

| Test | Child bead | Likely class |
|---|---|---|
| `test_kkm7_batching.py::test_syncall_batches_mark_doc_not_found_and_drive_metadata` | `gts-obry.1` | Suspected shared-account contention (2nd occurrence of this symptom shape — see §2) |
| `test_uuse_scoped_listing.py::test_syncall_batches_multi_doc_listing_miss_fallback` | `gts-obry.1` (same investigation) | Same as above |
| `test_sync_concurrency.py::test_sync_lock_serializes_concurrent_syncdocument_for_same_doc` | `gts-obry.2` | Undetermined — real lock-log regression vs. Axiom lag/contention |
| `test_sidebar.py::test_tab_navigation_docstatus_regression` | `gts-obry.3` | Undetermined — real UI regression vs. load-induced timeout |

None of these are closed as "known issue, ignore" — each child bead requires an
isolated re-run to disambiguate real regression from infra flake before
closing, per the Backstop rules (known failures are not a basis for proceeding
autonomously). **Merge-gate should not treat this branch as green until
`gts-obry`'s children resolve and a subsequent `pytest -x` run is clean.**

**AC — `gts-obry` (epic), all 4 covered:**
- [x] `gts-obry.1`, `.2`, `.3` each closed per their own AC below (not just
      "investigated" — see §2). Status: all 3 ✅ closed (`.1` and `.2` on
      2026-08-20 in a prior session; `.3` closed 2026-08-20 this session).
      Epic itself left OPEN pending the two items below.
- [x] A subsequent full `pytest -x` run shows 0 failures in this set — ✅
      confirmed 2026-08-20 (second session), `/tmp/gas-test2.log`: none of
      `gts-obry`'s original 4 reproduced. 2 *different* tests failed instead
      — tracked under new epic `gts-7vo2` (§0 above), out of this epic's
      scope by definition.
- [x] `regression=verified` — branch-level verification satisfied by the
      above; `gts-obry` closed 2026-08-20.

## 2. Priority 1 — Live-test account contention (root debt behind §1's kkm7/uuse pair)

This is the same failure shape `gts-moy1.2`'s close notes already surfaced and
left unresolved ("3 unrelated failures... consistent with concurrent-sweep
contention... a human should sanity-check the account-contention read before
treating it as fully explained"). It has now recurred in a *second*
independent full-suite run (2026-08-18 → 2026-08-20), on the *same* two test
files, with the *same* "N events instead of 1" shape. That recurrence is
itself signal: this is not a one-off.

**Why this matters beyond the 2 failing tests:** the whole batching-assertion
test family (`test_kkm7_batching.py`, `test_uuse_scoped_listing.py`, and by
extension any future "exactly one webapp/log call for N docs" assertion)
is unreliable against the shared TEST GAS account as currently isolated. Every
future regression run risks reproducing this and burning a triage cycle.

**Recommended action:**
- Finish `gts-obry.1`'s disambiguation (installed triggers? concurrent
  sessions during the run window?).
- If contention is confirmed: stop re-deriving it per-incident. Give
  `tests/helpers/gas_log.py`'s log-fence matching an `op`/`parentOp`
  correlation mode so a test only counts log entries chained from *its own*
  sweep invocation, not anything else in the timestamp window. This is a
  one-time investment that removes an entire class of future false failures.
- Document the shared-account contention risk in OPERATIONS.md as an
  operational constraint (don't run two full sweeps, or a sweep alongside
  manual testing, against the same TEST deployment concurrently) until the
  op-correlation fix lands.

**AC — `gts-obry.1`:**
- [x] Diagnostic instrumentation shipped: `scn/session.py::_http_post` stamps
      `opId`/`initiatedAt` on every call (stable across retries); `doPost`
      logs `initiatedAt`/`queueDelayMs`; unit-tested
      (`tests/test_fixture_invoke_retry.py`, 3 new cases); deployed to TEST;
      live-verified via a real Axiom row (2026-08-20 — see bead notes)
- [ ] **Not yet done — this is the bead's actual close condition:** installed
      TEST-project triggers checked (Apps Script trigger list, not just code)
- [ ] **Not yet done:** confirmed whether another session/account activity ran
      concurrently during the failing window
- [ ] **Not yet done:** `test_kkm7_batching.py` /
      `test_uuse_scoped_listing.py` re-run in isolation to check whether the
      double-event symptom reproduces outside a full sweep
- [ ] Verdict recorded on the bead: contention confirmed (→ implement the
      `gas_log.py` op-correlation fix below, extending the existing fence
      matcher — do not add a second, parallel matching mechanism) *or*
      contention disproven via a `parentOp` mismatch on a real recurrence (→
      escalate as a genuine `SyncManager.js` double-fire bug, root-caused
      before any fix is written)
- [ ] If confirmed: `gas_log.py` fence matching extended (not replaced or
      forked) to correlate by `op`/`parentOp`; OPERATIONS.md notes the
      contention constraint until that lands

## 2a. Priority 1 — `gts-obry.2`: sync-lock (li3g) `sync.locked.skip` log never observed in 60s

New this run, undetermined. Two live hypotheses per the bead: (a) real
regression in `syncDocument`'s lock-skip logging, (b) infra timing —
Axiom lag or the same account-contention pattern as §2.

**AC — `gts-obry.2`: ✅ DONE (closed 2026-08-20)**
- [x] `SyncManager.js`'s lock-skip branch confirmed to still call
      `GasLogger.log('sync.locked.skip', ...)` (grep, not assumption —
      `src/SyncManager.js:149-159`, unconditional on the skip path)
- [x] Test re-run in isolation (not full-suite) to rule out contention/timing
      — PASSED clean (91.46s). Second independent clean pass: `gts-obry.1`'s
      own targeted-subset gate incidentally ran this same test and also
      passed.
- [x] Isolated re-run passed clean → closed as a full-suite-duration
      contention flake, cross-referenced against `gts-obry.1`'s confirmed
      installed 30-min `syncAll` trigger contention family (`gts-li3g`). No
      code change. `docs/OPERATIONS.md`'s Failure Modes contention row
      extended (not duplicated) to note the inverse "expected event missing
      within window" shape alongside the existing duplicate-event shape.
      `regression=verified` set on `gts-obry.2` (isolated scope only — the
      branch-level gate per Backstop rules still needs a subsequent full
      `pytest -x`, out of scope for this bead).
- [ ] N/A — isolated re-run did not fail a second time, so the `clasp logs`
      live-catch path was not needed.

## 2b. Priority 2 — `gts-obry.3`: sidebar UI timeout waiting for per-row status button

New this run. This is the gts-cw5/gts-gdll sign-off regression test, so a
real regression here is higher-signal than an ordinary UI flake.

**AC — `gts-obry.3`: ✅ DONE (closed 2026-08-20)**
- [x] Test re-run in isolation (not full-suite) — PASSED clean (149.50s,
      well within the 15s per-locator budget). No pytest-playwright plugin
      is installed in this project (checked: `plugins:` line in pytest's own
      output lists `allure-pytest`/`anyio`/`dotenv` only, no `playwright`),
      so no `--tracing`/`--video` CLI flags exist to add; the AC's tracing
      intent is already met by the standing `capture_failure()` mechanism
      (`gts-3tkf`), which would have fired automatically had this run failed.
- [x] Isolated re-run passed clean → downgraded to a known
      duration/load-flake (no timeout-budget change made — single
      occurrence, not a recurring pattern, per the AC's own "don't default
      to raising it" guidance).
- [x] Checked against this branch's own
      modified `src/` files (`tmp/pr3-pr4-combined` touches several sidebar-
      adjacent files) for an unintended regression before assuming pre-
      existing flake — done proactively even though the isolated run
      already passed. `WorkspaceAddonCard.js`'s `gts-8py3`/`gts-zg2t`
      doc-scan-gating changes (new `includeDocScan`/`allowCachedState` opts
      on `buildHomepageCard`) do not touch the per-row status button's
      `aria-label` contract — `getStatusIconButtons()` (`SyncManager.js:3544`,
      untouched by this branch) still produces `'Set ' + status`, matching
      `scn/ui.py::sidebar_set_status`'s locator exactly, and `onSyncNow()`
      explicitly passes `includeDocScan: true` so the card the test's
      `sidebar_sync()` triggers does perform the scan and render the
      controls. No code-path mismatch found; no code change made.

## 3. Priority 1 — `gts-ir1f`: permutation-batching retrofit stuck for 2 weeks, blocked on flake not logic

`gts-ir1f` (in progress since 2026-08-06) is the project's own prescribed fix
for full-suite runtime: batch independent scenarios into one live `syncAll()`
sweep instead of one sweep per test (T1-T24/I1-I11 permutation batching). It
has **5 failed attempts across 2 sessions**, every one failing *before test
logic ran at all* on `/exec` routing flake (`gts-pm72`'s class), not on the
retrofit itself. `gts-pm72` was later closed with a bounded-retry fix for
GAS-side Drive 500s — but `gts-ir1f`'s own failures were client-side
`/exec` routing (404, non-JSON echo), a different layer, and it's unclear
whether that layer's retry coverage was ever revisited after `gts-pm72`
closed.

**This is high-leverage debt**: `test_sync_all.py` alone contributes ~700s to
the suite's ~7137s total in this run (`test_sync_all` 227s +
`test_sync_all_op_correlation` 151s + `test_sync_all_integrity_and_listing_miss_batch`
250s + others), largely from N separate live sweeps where the retrofit's own
design doc already says most of that time is sweep cost, not assertion cost.
Landing this would cut meaningful wall-clock off every future full sweep —
directly serving "faster and more cost effective."

**Recommended action:** before a 6th attempt, verify whether `scn/session.py`'s
`_http_post` retry (the layer `gts-ir1f`'s failures were hitting) has been
hardened since attempt #5, independent of `gts-pm72`'s GAS-side fix. If not,
that's the actual blocker to fix first — narrowly scoped, separate from the
retrofit itself.

**Status update (2026-08-20 session):** this section's premise was already
stale relative to the bead — the bead's own notes (which this session read
first, per the plan's own rule #1) show the retry gap was fixed and
live-verified back on 2026-08-07, before this plan document was even
written. Findings appended to `gts-ir1f`'s notes:
- `_http_post`'s retry logic (3 attempts, 404 + non-JSON, 3s backoff) is
  unchanged since before attempt #5 — `git blame` attributes it to a
  pre-Aug-6 commit (`ffbe11f8`). The only change since is `gts-obry.1`'s
  additive `opId`/`initiatedAt` correlation stamping, which doesn't touch
  the retry path.
- The real client-side gap was `invoke_fixture` (`tests/helpers/fixture_invoke.py`)
  — a *separate*, third HTTP implementation with no retry, on the
  session-scoped autouse fixture path — not `_http_post` itself. `gts-z6bx`
  (closed 2026-08-07) fixed this by delegating `invoke_fixture` to
  `_http_post`. Confirmed still in place in current `HEAD`.
- Attempt #6 (2026-08-07, post-`gts-z6bx`) ran clean, live-verifying the fix
  under load. No 7th attempt is needed on this axis.
- `test_team_folder_reconciliation.py`'s 4-scenario batch and
  `test_sync_all.py`'s 3-scenario batch are both present and committed
  (`b77b63b`) with per-file before/after wall-clock already recorded in the
  bead's 2026-08-06 notes (11→2 worst-case sweeps / 393.87s and 228.50s
  totals). No separate unbatched full-suite baseline exists to re-diff
  against — the current full-suite number (§1, 1:58:56) already reflects
  the batched state.

**AC — `gts-ir1f`:**
- [x] Confirmed whether `_http_post`'s bounded retry (3 attempts, `/exec`
      404 + non-JSON echo symptoms) has changed since attempt #5 (2026-08-06)
      — confirmed unchanged (see status update above); the real gap
      (`invoke_fixture`) was already fixed and live-verified 2026-08-07.
- [x] N/A — retry logic itself was never the blocker; `gts-z6bx` fixed the
      actual gap (`invoke_fixture` bypassing `_http_post`'s retry) on
      2026-08-07, before this stage started.
- [x] A 6th retrofit attempt already run (2026-08-07, post-`gts-z6bx`) —
      PASSED clean; no 7th attempt scheduled.
- [x] `test_team_folder_reconciliation.py`'s 4 scenarios batched into one
      `syncAll()` sweep — confirmed present in `HEAD`
      (`test_syncall_team_reconciliation_batch`).
- [x] Full-suite wall-clock re-measurement: per-file before/after already
      recorded on the bead (2026-08-06 notes); no separate unbatched
      full-suite baseline exists to re-diff against — accepted as
      sufficient evidence.
- [ ] **Bead itself remains open, NOT closed by this session** — blocked on
      `gts-lirp` (open, unrelated Import-tab stale-DOM-read bug hit by
      `test_import_flow_forward_sync`'s remaining unbatched item), which is
      outside this stage's scope. `gts-ir1f` stays
      `IN_PROGRESS`/`regression=pending` until `gts-lirp` closes.

## 4. Priority 2 — Governance exporter epic (`gts-283i`) has 7+ open `[TST]` hardening beads, no `[FIX]`/`[IMP]` closure gate visible

Open beads: `gts-283i.5`, `gts-2k9h`, `gts-2g9j`, `gts-e7ca`, `gts-g21w`,
`gts-wido`, `gts-r40j`, plus `gts-ipoy` (`[IMP]`, `regression:pending`) and the
new untracked files in this session's `git status`
(`scripts/export_governance.py`, `tests/test_export_dialog.py`). This is a
large, active surface with many hardening tickets queued but not landing —
worth a session dedicated to sweeping `gts-283i`'s children to green or
explicitly deferring the ones that aren't near-term, rather than letting the
open count grow. Not urgent, but it's the single largest cluster of open
`[TST]` debt in `bd ready`.

**AC — governance exporter sweep (`gts-283i` and children):**
- [ ] Every open child (`gts-283i.5`, `gts-2k9h`, `gts-2g9j`, `gts-e7ca`,
      `gts-g21w`, `gts-wido`, `gts-r40j`, `gts-ipoy`) reviewed in one pass —
      not picked off individually across unrelated sessions, which is how a
      cluster like this grows unnoticed in the first place
- [ ] Each child gets one of: closed as covered, actively worked toward
      close, or explicitly deferred with a reason recorded on the bead —
      "still open, no verdict" is not an acceptable end state for this pass
- [ ] Before writing any new hardening test for this cluster: checked
      `scripts/export_governance.py` / `tests/test_export_dialog.py` (this
      session's untracked files) for whether they already cover part of the
      gap — extend those rather than starting a parallel test file for the
      same surface
- [ ] `gts-ipoy`'s `regression:pending` label resolved (verified or
      re-scoped) as part of the same pass, not left dangling after the rest
      of the cluster closes

## 5. Priority 2 — `gts-moy1.3`: `sheetRuns` bold-run leak (zocq regression) still open

Last remaining child of the 2026-08-18 triage epic (`gts-moy1`). This
section's premise ("real, already-diagnosed regression, not a flake
candidate") turned out to be stale relative to what the bead's own notes
already flagged as unverified ("suspected mechanism ... unverified, check
first") — see status update below.

**Status update (2026-08-20 session):** disambiguated, not fixed —
unreproduced. Two clean re-runs: (1) the test in isolation, (2) the full
`tests/test_inline_formatting.py` file, which runs the bold/italic seed test
immediately before this one against the *same shared* `testSheetId` Actions
sheet — directly exercising the bead's own named "adjacent sheet row/cell
write" bleed hypothesis. Both passed clean (`sheetRuns == []`). Code review
of the write path (`WebApp.js::_handleSyncActionRows`) and read path
(`SyncManager.js::_richTextRunsForCell`/`_runsFromRichTextRuns`) found no
defect in either — the plain-text case never calls `setRichTextValue`, and
the read side correctly returns `[]` whenever nothing in the cell is
bold/italic. The original failure's source log (2026-08-18) is no longer on
disk to re-inspect; the only available later full-sweep log (2026-08-20,
this plan's own §1 source) shows this same test passing. Classified as a
one-off flake in the same family as `gts-obry` (§2 — shared TEST-account
contention), not a reproducible defect. No code change made, per the plan's
own rule 4 (disambiguate before fixing an unconfirmed hypothesis). Full
findings on the bead's notes.

**AC — `gts-moy1.3`: ✅ DONE (closed 2026-08-20, unreproduced/flake — not a
code fix)**
- [x] Root cause re-read from the bead first — bead's own description
      already flagged the mechanism as "unverified, check first"; not a
      settled diagnosis as this section originally implied.
- [x] N/A — no fix applied; disambiguation found no reproducible defect to
      fix (2 clean re-runs, code review clean on both write and read paths).
- [x] N/A — no new regression test added; nothing to prove failing since the
      defect did not reproduce. Existing `test_plain_action_text_has_no_runs`
      already covers this shape and continues to pass.
- [x] `gts-moy1` epic closed 2026-08-20 — its last open child resolved.
- [x] `gts-zocq`'s `regression` flag flipped `pending` → `verified`, noting
      this bead (`gts-zocq.2` state-change event).

## 6. Priority 3 — Process/observability debt

- **`gts-iwa0`** — Axiom `data` field not marked as a map field + dataset
  needs vacuuming. Every `gas_log.py` query pays a tax for this being unfixed
  (less efficient log queries, per this session's own testing-strategy
  guidance to use `query_axiom.py` rather than hand-rolled queries). Cheap,
  infrastructure-only, improves query cost/speed project-wide.
- **`gts-28p`** — reconcile test-organization guidance (journey-embedded
  steps vs. dedicated per-entry-point files). Convention drift risk: without
  resolving this, new tests keep picking one convention or the other
  ad hoc, compounding review/maintenance cost.
- **`gts-m65t`** — the "oracle-driven ordering" lever (test-first vs.
  slice-first choice, now embedded in this project's CLAUDE.md testing
  section) is still flagged "prove then promote to DevStandard T23." Worth
  closing out given it's already being applied here day-to-day — turning
  lived practice into a documented standard reduces onboarding/rework cost
  elsewhere.

**AC — `gts-iwa0`:**
- [x] Axiom `data` field marked as a map field (dataset schema change, not a
      query-side workaround in `query_axiom.py`)
- [x] `nuuts` dataset vacuumed
- [ ] A representative `query_axiom.py` query re-timed before/after to
      confirm the expected cost/speed improvement, not assumed

**AC — `gts-28p`:**
- [ ] One convention chosen for new tests (journey-embedded steps vs.
      dedicated per-entry-point files) — a documented decision, not a
      preference stated in passing
- [ ] Decision recorded as an ADR or in the testing-strategy doc this
      project's CLAUDE.md already points to (extend that doc, don't start a
      second convention-reference doc alongside it)
- [ ] Existing tests audited for which convention they already follow, so
      the decision is grounded in what's actually there, not written in a
      vacuum

**AC — `gts-m65t`:**
- [ ] Oracle-driven ordering lever's current in-project usage reviewed as
      the evidence base (it's already being applied day-to-day per this
      project's CLAUDE.md)
- [ ] Promotion proposal drafted against DevStandard's T23 slot, reusing the
      existing T1-T24/I1-I11 numbering scheme rather than inventing a new
      identifier scheme for the same category of principle
- [ ] Sign-off obtained through whatever process DevStandard promotions
      already use (check for one before proposing a new promotion process)

## Suggested next-session order

1. ~~`gts-obry.1` (contention disambiguation — blocks trusting *any* future
   batching-assertion failure) — **do this first**, it de-risks all future
   triage in this same family.~~ ✅ done.
2. ~~`gts-obry.2`, `gts-obry.3` (isolated re-runs — cheap, fast to clear or
   escalate).~~ ✅ done — both closed as full-suite-duration flakes, no code
   change. **`gts-obry` epic itself still needs a full `pytest -x` run
   (owner: user, external to this session) before it can close.**
3. ~~`gts-ir1f` unblock check (§3) — high runtime payoff if the client-side
   retry gap is real and small to close.~~ ✅ done 2026-08-20 — retry gap was
   already fixed/live-verified 2026-08-07 (`gts-z6bx`), stale premise in this
   plan corrected. Bead itself stays open, blocked on unrelated `gts-lirp`
   (out of this stage's scope).
4. ~~`gts-moy1.3` (zocq) — cheap, already-diagnosed, clears the oldest open
   regression.~~ ✅ done 2026-08-20 — disambiguated, not fixed: unreproduced
   after 2 clean re-runs (including the bead's own named adjacent-row-bleed
   scenario) and a clean code review of both write/read paths. Classified as
   an `gts-obry`-family flake, no code change. `gts-moy1` epic closed;
   `gts-zocq` regression flag flipped to `verified`. **Next up: `gts-iwa0`.**
5. `gts-iwa0` — cheap infra fix, do opportunistically.
6. `gts-283i` sweep and `gts-28p` — schedule as a dedicated session, not
   opportunistic (each is a multi-bead cluster).

**2026-08-20 second-session additions, in order:**

7. ~~`gts-7vo2.1` (sidebar exception-type bug) — trivial, isolated, do first
   opportunistically; zero risk of masking anything else.~~ ✅ done
   2026-08-20 — except clause widened to `Exception`; isolated re-run passed.
8. ~~`gts-7vo2.2` (gas_log.py op/parentOp fence filter) — **do this before the
   next full sweep, not after.**~~ ✅ done 2026-08-20 — the filter
   (`matches_op`) already existed from `gts-obry.1`; `test_sync_all.py`'s
   j8cn test updated to use it alongside kkm7/uuse, all 3 verified green
   together in isolation. Trigger-timing cross-check disproved `gts-li3g`
   as this occurrence's source (concurrent session instead). **Next up:**
   §4's `gts-283i` sweep, or §6's `gts-iwa0`/`gts-28p`/`gts-m65t` cluster —
   nothing currently blocking either.
