# Plan — 2026-08-06 live-suite flake recovery & `gts-ir1f` close-out

**Owner:** Stuart Donaldson
**Origin:** `HANDOFF-gts-ir1f-2026-08-06.md` + `docs/regression-suite-health-review-2026-08-05.md`
**Purpose:** unblock `gts-ir1f`'s last open item by first removing two harness
defects that were being absorbed as "infra flake", then spend live attempts.

---

## How to use this plan

This plan is written to be executed **one section at a time by an agent with a
clean context**. Each section is self-contained: it states its own entry
condition, the files it may touch, its acceptance criteria, and its exit
condition. An agent picking up a section should need to read only:

1. this file's **Global rules** + its own section, and
2. the `bd show <id>` output for the bead named in that section.

**Do not read other sections' work products** unless a section explicitly says
to. Sections are separated for isolation, not just for tidiness — see
each section's *Isolation rationale*.

### Agent protocol (every section)

1. `bd prime`, then `bd show <bead-id>` for this section's bead.
2. Set the section **Status** in this file to `IN PROGRESS — <agent/date>` and
   `bd update <id> --claim` before making any change.
3. Run `/implementation-gate` before writing implementation code (project rule,
   global CLAUDE.md §8).
4. Do the work. Tick each AC checkbox in this file **only** when that AC is
   demonstrably met — record the evidence inline (command run, log path,
   test nodeid). An unticked box with a note is a correct outcome; a ticked box
   without evidence is not.
5. On completion, set **Status** to `DONE — <date>`, fill the **Result** block,
   and update the bead (`bd close`/`bd update` + `bd set-state <id>
   regression=pending|verified --reason "<what actually ran>"`).
6. If blocked, set **Status** to `BLOCKED — <one-line reason>`, record what you
   tried in **Result**, and stop. Do not improvise around a blocker.

---

## Global rules (binding on every section)

- **No live retries beyond the budget.** Sections that consume live GAS runs
  declare an explicit attempt budget. Exhausting it is a stop-and-report event,
  not a prompt to try again (CLAUDE.md Backstop rules; `gts-ir1f` is already at
  5 failed attempts across 2 sessions).
- **Long runs go to a file, never `| tail`.** `pytest ... > /tmp/jobs/<name>.log
  2>&1` then poll with `tail -30`. Preserve the log path in **Result**.
- **Never `pytest --sw`** for a sweep. One non-stopping pass, triage in bulk.
- **A new assertion must be proven to fail** before it counts as acceptance
  (CLAUDE.md Backstop rules). Green-only is unverified. Every section below that
  adds an assertion carries this as an explicit AC — it is the most commonly
  skipped rule in this project's history.
- **No bead creation without asking**, except where a section says otherwise.
- **Do not commit or push** — Conservative profile. Report changed files and the
  commands you would run.
- Deployment: `pnpm run deploy:test` only (never bare `clasp`). A `pnpm run
  push` alone leaves the WebApp deployment stale.
- Manual WebApp probes: `python scripts/call_webapp.py` only. Never hand-rolled
  `curl`/`urllib`.

---

## Execution order

```
S1 (harness: retry gap) ──┐
                          ├──> S3 (live attempt #6) ──> S4 (triage) ──> S5 (merge gate)
S2 (harness: diagnostics) ┘

S0 (coverage baseline) — independent, run any time, including in parallel
```

S1 and S2 are both prerequisites for S3: S1 removes two of the five observed
failure modes, S2 makes S3's failure artifact trustworthy if it fails anyway.
Running S3 before both is spending a scarce live attempt on a blind run.

| # | Section | Bead | Live GAS cost | Depends on | Status |
|---|---------|------|---------------|-----------|--------|
| S0 | Refresh AC/entry-point coverage baseline | new `[INF]` (create in-section) | none | — | ⬜ NOT STARTED |
| S1 | Fix `invoke_fixture` retry gap | `gts-z6bx` | none (mocked) | — | ✅ DONE 2026-08-06 (regression=pending) |
| S2 | Fix failure-diagnostics ordering (F9) | `gts-hroj` | 1 forced-fail run | — | ✅ DONE 2026-08-06 (regression=pending) |
| S3 | Live attempt #6 on `test_import_flow_forward_sync` | `gts-ir1f` | 1 attempt (budget: 2) | S1, S2 | ✅ DONE 2026-08-07 — PASS (regression=pending) |
| S4 | Triage S3's outcome to the right owner | `gts-lirp` / `gts-ir1f` | none | S3 | ✅ DONE 2026-08-07 — PASS row applied, docs updated, no bead action needed |
| S5 | Merge gate: full `pytest -x`, flip `regression=verified` | all above, `gts-bops`, `gts-lirp` | full suite | S1–S4, `gts-bops`, `gts-lirp` | 🛑 BLOCKED 2026-08-07 — resumption run hit `gts-lirp` (known intermittent bug, confirmed flaky not permanent — same test S3 passed 2026-08-06); F10/`gts-bops` neither reproduced nor contradicted (run stopped before reaching it); human decision needed |

---

## S0 — Refresh the AC/entry-point coverage baseline

**Status:** ⬜ NOT STARTED
**Bead:** none yet — create one `[INF]` bead as the first act of this section
(this is the one sanctioned exception to the no-bead-creation rule; it is
review-doc recommendation #4, already approved in that doc's priority table).
**Live GAS cost:** none.
**Files in scope:** `scripts/check_coverage.py` (run it, fix only if it errors),
the coverage baseline artifact it writes, `package.json` (one new script).

**Isolation rationale:** touches no test-harness code and consumes no live
backend, so it cannot interact with S1–S3 and can run concurrently with any of
them. Kept separate so a coverage-tooling problem never blocks the live track.

**Why:** the baseline is stale (2026-06-11). `gts-ir1f`'s "no coverage loss from
batching" claim is currently asserted, not proven. This makes it provable.

**Acceptance criteria**

- [ ] `[INF]` bead created with `--description` / `--acceptance` / `--design`
      populated (project rule: an `[INF]` design bead with empty content fields
      is incomplete).
- [ ] `scripts/check_coverage.py` runs clean against the current tree; the
      refreshed baseline is written and its diff vs. the 2026-06-11 baseline is
      summarised in **Result**.
- [ ] Any coverage *loss* introduced by `gts-ir1f`'s batching work is either
      shown to be zero, or enumerated explicitly as a finding.
- [ ] The check is wired into `pnpm run test:full`, or into a lighter dedicated
      `test:coverage` script, so it is a standing gate rather than a one-off.
- [ ] The chosen wiring (full vs. lighter script) is stated with a one-line
      rationale in **Result**.

**Exit condition:** baseline refreshed, gate wired, bead closed or left open
with a named remainder.

**Result:**
_(fill in)_

---

## S1 — Fix the `invoke_fixture` bounded-retry gap

**Status:** DONE — 2026-08-06
**Bead:** `gts-z6bx`
**Live GAS cost:** none — the backstop proof must be mocked, not live.
**Files in scope:** `tests/helpers/fixture_invoke.py`, possibly a new shared
retry helper, plus a new test file for the backstop proof. `scn/session.py` may
be read and may be refactored only to *extract* the existing helper — its
retry behaviour must not change.

**Isolation rationale:** this is the only section that may alter the shared HTTP
transport used by every live test. It runs alone and lands green before any
section spends a live attempt, so that if S3 still fails, the transport is a
ruled-out variable rather than a suspect.

**Why:** `invoke_fixture` is a third, non-retrying copy of the WebApp POST. It
sits on the session-scoped autouse `_reset_test_state` path, so one transient
routing blip aborts an entire pytest session. It caused 2 of the 5 failed
`gts-ir1f` attempts. `bd show gts-z6bx` has the full analysis and three
candidate fix shapes — prefer de-duplication over a fourth copy of the loop.

**Acceptance criteria** (mirror of the bead's; tick here and there)

- [x] `invoke_fixture` retries the same two symptoms `_http_post` retries
      (HTTP 404, non-JSON/echo-page body) at the same bound and delay. True by
      construction — it now calls `_http_post` directly rather than reimplementing.
- [x] No fourth copy of the retry loop exists in the tree after the change;
      state in **Result** which of the bead's shapes (1/2/3) was taken and why.
      **Shape (2)** taken: `invoke_fixture` is now a thin wrapper delegating to
      `scn.session._http_post`, mapping its `FixtureTokenError`/`FixtureError`
      onto `fixture_invoke`'s own classes of the same name (preserves the
      `fixture_invoke.FixtureTokenError` reference documented in
      `scn/contract.py:199`). Shape (1) — extracting a *third* shared helper —
      was rejected as unnecessary churn: `scn.session._http_post` already *is*
      the canonical implementation both other copies should point at, so
      delegating directly is the minimal-diff form of "de-duplicate."
      `grep -n "for attempt in range" scn/ tests/ scripts/` shows exactly one
      retry loop (`scn/session.py:170`); `scripts/call_webapp.py`'s own copy
      predates this bead, was already retrying, and is out of scope per the
      bead's file list.
- [x] Non-retryable behaviour unchanged: `FixtureTokenError` on
      `test-token-unauthorized`/`test-token-expired`, `FixtureError` on an
      `{'error': ...}` body, immediate raise on non-404 HTTP status and on
      `URLError`. No retry on timeout. Covered by
      `test_token_rejection_raises_fixture_invoke_token_error`,
      `test_fixture_error_body_raises_fixture_invoke_fixture_error`,
      `test_non_404_http_status_raises_immediately_not_retried`,
      `test_url_error_raises_immediately_not_retried` (all asserting
      `urlopen_mock.call_count == 1` where applicable). Timeout is not caught
      by `_http_post` at all (propagates as `socket.timeout`, unchanged), so
      it is structurally never retried.
- [x] Exhaustion raises with a message naming the attempt count. Covered by
      `test_exhaustion_after_repeated_404_names_attempt_count` (`match=r"3
      attempts"`).
- [x] **Backstop proof:** a test asserts the retry *engages* (forced
      404-then-success, and forced echo-page-then-success), and that same test
      is demonstrated to **fail** against the pre-fix implementation. Record
      both the passing run and the deliberate failing run in **Result**. See
      **Result** — pre-fix log shows 3/7 failing (the two retry-engagement
      tests plus the attempt-count-message test); post-fix log shows 7/7 green.
- [x] `scn/session.py::_http_post`'s observable behaviour is unchanged
      (including `/dev` cookie injection and the reporter FAIL event emitted by
      `ScenarioSession._post`). No line inside `_http_post` or `_post` was
      touched — only `tests/helpers/fixture_invoke.py` was edited.
- [x] Targeted-subset gate green: the new test plus
      `tests/test_infrastructure.py` and any other non-live callers.
      **Partial, by design:** `tests/test_fixture_invoke_retry.py` +
      `tests/test_scn_session.py` executed fully (49 passed,
      `/tmp/jobs/z6bx-subset.log`). `test_infrastructure.py`,
      `test_ai_n_token.py`, `test_epic_a_slice.py` all use `invoke_fixture`
      only inside session-scoped fixtures/tests that hit the **live** GAS
      backend — running them would violate this section's own "Live GAS
      cost: none" declaration. Verified instead via `--collect-only` (clean,
      14 tests collected, `/tmp/jobs/z6bx-collect.log`) plus a direct
      `import`/signature check, since the change is a pure transport swap with
      no signature or call-site change for any of these callers.

**Exit condition:** `bd close gts-z6bx` with
`bd set-state gts-z6bx regression=pending --reason "<subset that ran>"`.
Full `pytest -x` is S5's job, not this section's.

**Result:**

`gts-z6bx` closed. `bd set-state gts-z6bx regression=pending` with reason
naming the subset above.

**Change:** `tests/helpers/fixture_invoke.py::invoke_fixture` rewritten to
delegate to `scn.session._http_post(url, payload, timeout)` instead of running
its own non-retrying `urllib.request.urlopen` call. Module-level `FixtureTokenError`
/`FixtureError` classes kept (same names, same import path for existing
callers) but now populated by catching-and-re-raising `scn.session`'s versions
of the same names. No other file touched.

**New test file:** `tests/test_fixture_invoke_retry.py` (7 tests, all mocked —
no live GAS calls). Mocks `scn.session.urllib.request.urlopen` and
`scn.session.time.sleep` (autouse fixture) since the retry loop now lives
there.

**Backstop proof:**
- Pre-fix run (before the `fixture_invoke.py` edit):
  `/tmp/jobs/z6bx-prefix.log` — `3 failed, 4 passed`. The 3 failures are
  exactly the ones that require retry engagement:
  `test_retries_and_recovers_on_http_404_then_success`,
  `test_retries_and_recovers_on_echo_page_then_success`,
  `test_exhaustion_after_repeated_404_names_attempt_count` (message didn't
  name "3 attempts" — old code raised on attempt 1). The other 4
  (non-retryable-path tests) already passed, as expected, since those
  behaviours were correct even before the fix.
- Post-fix run: `/tmp/jobs/z6bx-postfix.log` — `7 passed`.

**Subset gate:** `/tmp/jobs/z6bx-subset.log` —
`pytest tests/test_fixture_invoke_retry.py tests/test_scn_session.py` →
`49 passed`. `/tmp/jobs/z6bx-collect.log` — collect-only on the three live
callers, 14 tests collected cleanly, no import errors.

**Files changed:** `tests/helpers/fixture_invoke.py` (rewritten),
`tests/test_fixture_invoke_retry.py` (new).

---

## S2 — Fix failure-diagnostics ordering (F9)

**Status:** DONE — 2026-08-06
**Bead:** `gts-hroj`
**Live GAS cost:** one deliberately-failing multi-doc run for the backstop
proof. Budget: 2 runs. Prefer the cheapest multi-doc test available, not
`test_import_flow_forward_sync`.
**Files in scope:** `tests/conftest.py` (the diagnostics hook region), possibly
`scn/ui.py`'s `capture_failure`, plus a test for the backstop proof.
**Explicitly out of scope:** `tests/helpers/fixture_invoke.py` (S1 owns it) and
any change to what the five affected tests assert.

**Isolation rationale:** modifies pytest hook wiring, which affects the failure
path of *every* test in the suite. Any regression here is silent — it degrades
diagnostics, not results — so it gets its own section, its own backstop, and no
concurrent harness edits.

**Why:** the diagnostics hook fires after the test's own `finally:` has already
trashed every doc, so the screenshot always shows "file is in trash" regardless
of the real cause. This has now been mis-diagnosed as a product bug twice
(`gts-lirp` 2026-08-05, `gts-ir1f` attempt #4 2026-08-06). See `bd show
gts-hroj` for the three candidate shapes — shape (1), capturing at
`pytest_runtest_call` level, is preferred; shape (2) is explicitly disallowed as
the primary fix by CLAUDE.md's no-copy-pasted-capture-block rule.

**Shape actually taken — deviates from the bead's stated preference, see
Result:** neither (1) nor (2). Empirically verified (mocked, no live cost)
that shape (1) cannot work: a hookwrapper around `pytest_runtest_call` only
resumes *after* Python has already fully unwound the test function's own
`finally:` — that's basic call-stack semantics, not a pytest quirk, and no
hook anywhere in pytest's chain can observe the exception before it. Took
shape (3) instead (deferred trashing via a pytest fixture finalizer), scoped
tightly: `ScenarioSession.new_doc(request=...)` (`scn/session.py`) now
registers doc-trashing as a `request.addfinalizer`, so it structurally
cannot fire before the call-phase failure report regardless of what any
individual test's `finally:` does.

**Acceptance criteria**

- [x] A failing multi-doc live test's screenshot shows the doc **at the moment
      of failure**, not the post-teardown trashed state. Live-verified: see
      Result — pre-fix backstop run captured `buttons=['Go to Docs home
      screen', 'Take out of trash']`; post-fix run captured the live Docs
      editor toolbar for the same doc/failure shape.
- [x] The fix is structural: holds for all five affected files
      (`test_import.py`, `test_team_scope.py`, `test_journey.py`,
      `test_sync_all.py`, `test_kkm7_batching.py`) with no per-test capture
      block, and holds for a new multi-doc test added later with no wiring.
      All five edited: each `finally:` that used to trash the doc directly
      (or call the old combined `scn.close()`) now calls `scn.engine.close()`
      only (drain-invariant check) or nothing at all (test_journey.py's
      secondary docs) — the trashing itself is auto-registered once, in
      `new_doc()`, so any *future* multi-doc test gets it for free by
      constructing sessions the normal way (`ScenarioSession.new_doc(settings,
      request=request)`) with zero extra wiring.
- [x] **Backstop proof:** live, 2/2 attempt budget. Run 1
      (`HROJ_BACKSTOP_SIMULATE_BUG=1`, reproducing the pre-fix pattern inline
      in the test's own `finally:`) — captured artifact shows Drive's
      post-trash chrome. Run 2 (default — exercises the actual fix) —
      captured artifact shows the live editor. See Result for log/screenshot
      paths.
- [x] Non-UI tests remain a no-op — unchanged, `_find_page` untouched;
      confirmed via full `--collect-only` (447 tests, clean) and a 55-test
      mocked/API subset run (`test_scn_session.py`, `test_fixture_invoke_
      retry.py`, `test_infrastructure.py`), all passing.
- [x] Capture content preserved: screenshot path, `page.frames` URLs,
      per-frame visible-button names, Allure PNG — hook itself (conftest.py's
      `pytest_runtest_makereport`) untouched except a docstring addition;
      both backstop runs show the full capture block intact.
- [x] Live-run budget respected (≤2): exactly 2 runs (bug-repro + fix-verify),
      both against the same test, no re-runs needed.

**Exit condition:** `bd close gts-hroj` with `regression=pending` and the
reason naming exactly what ran. Note in **Result** whether `gts-lirp`'s
description should be updated now that the artifact it describes is fixed.

**Exit condition for the plan, if this section blocks:** S3 may proceed with S2
`BLOCKED`, but only with an explicit human decision recorded here — a failing
S3 will then produce a misleading artifact again.

**Result:**

`gts-hroj` closed, `regression=pending`.

**Root-cause correction to the bead's own design notes:** the bead preferred
shape (1) (capture at `pytest_runtest_call` level). Verified empirically,
mocked, no live cost (`/tmp/claude-.../scratchpad/hookorder/`) that this
cannot work: a `pytest_runtest_call` hookwrapper's post-yield code, and
`pytest_runtest_makereport`'s `report.when == "call"` branch, both only run
*after* `item.runtest()` has fully raised/returned — which means the test
function's own `finally:` (part of the same call-stack unwind) has already
executed. This is unconditional Python semantics, not something any pytest
hook ordering can route around. Confirmed with a 2-line reproduction: a
`finally:` print always appears before either hook's post-yield print fires
on a failing test.

**Fix actually applied (shape 3 — deferred trash via fixture finalizer):**
- `scn/session.py`: `ScenarioSession.__init__` gained `self._trashed = False`
  (idempotency guard). `close()` was split: it still runs `engine.close()`
  first (so the drain-invariant `DrainInvariantError` still surfaces exactly
  where callers expect it) then delegates trashing + reporter-close to a new
  `_deferred_trash()` method (idempotent). `new_doc(..., request=...)` now
  does `request.addfinalizer(instance._deferred_trash)` whenever `request`
  looks like a real pytest `FixtureRequest` (`hasattr(request,
  "addfinalizer")` — guards a `test_scn_session.py` unit test that passes a
  bare `object()` sentinel as `request` purely to opt into Reporter creation,
  not a real fixture request). Fixture finalizers run in pytest's teardown
  phase, which is strictly after the call-phase failure report/diagnostics
  hook — proven by the same mocked experiment (a `request.addfinalizer`
  callback fires after both the failing assert and the hookwrapper's
  post-yield code).
- `tests/conftest.py`: no functional change to
  `pytest_runtest_makereport`; added a docstring paragraph explaining the
  ordering contract (why this hook can never itself be "moved earlier", and
  that the real fix lives in `scn/session.py`).
- `tests/test_import.py` (3 sites), `tests/test_team_scope.py` (1 site),
  `tests/test_sync_all.py` (8 sites), `tests/test_kkm7_batching.py` (2
  sites): each `finally:` that directly trashed the doc (or called the old
  combined `scn.close()`) now calls `scn.engine.close()` only — the
  drain-invariant check stays at the same point in the test as before;
  trashing is left to the auto-registered finalizer.
- `tests/test_journey.py`: `test_journey` gained a `request` param; `ref_scn`
  / `reset_scn` (previously constructed with `request=None`, so they never
  got the auto-finalizer) now pass `request=request`; their `finally:`
  blocks (which only ever did the trash call, no invariant check) reduced to
  `pass`. The module's separate `scn` fixture (function-scoped,
  `yield`-based teardown calling `s.close()`) needed **no change** — a
  `yield`-fixture's post-yield code already runs in the teardown phase, i.e.
  it was never actually broken; useful independent confirmation that the
  "teardown phase = post-diagnostics" model is correct.
- `tests/test_import.py:647` (`test_forward_duplicate_guard`, single-doc,
  no `browser_page`) intentionally left calling `scn.close()` unchanged —
  not a UI test, so the diagnostics hook is a no-op for it regardless;
  changing it would be unnecessary diff.
- `tests/test_sync_all.py` / `tests/test_kkm7_batching.py`: secondary
  sessions created with `request=None` (`scn_b`, `scn_control`, etc.) were
  left on their pre-existing inline-trash pattern — none of these test
  functions take `browser_page`, so the diagnostics hook never fires for
  them either way; not part of the actual bug.

**Backstop proof — new file `tests/test_hroj_diagnostics_backstop.py`**
(`@pytest.mark.hroj_backstop`, `@pytest.mark.skip` by default — an
always-failing-by-design test can't live in the normal suite; module
docstring documents how to run either variant manually). Both runs used the
same test, toggled via `HROJ_BACKSTOP_SIMULATE_BUG` env var (temporarily
un-skipped for the two manual runs, re-skipped immediately after):
- Run 1 (bug repro — `HROJ_BACKSTOP_SIMULATE_BUG=1`, trashes inline in the
  test's own `finally:`, same shape as the pre-fix test bodies):
  `/tmp/jobs/hroj-backstop-prefix.log`,
  `/tmp/jobs/hroj-backstop-prefix.png`. Captured: `buttons=['Go to Docs home
  screen', 'Take out of trash']` — reproduces the exact F9 symptom.
- Run 2 (fix path — default env, trash deferred to the `new_doc(request=
  request)` finalizer): `/tmp/jobs/hroj-backstop-postfix.log`,
  `/tmp/jobs/hroj-backstop-postfix.png`. Captured: the live Docs editor
  toolbar (`'Editing'`, `'\xa0\nShare'`, etc.) — no trash chrome.
- Both runs against the same TEST deployment
  (`v0.2.2 (Rev. Aug 6, 2026 10:35) (TEST)`, confirmed current via
  `get_test_config` before starting).

**Gates run:**
- `--collect-only` on the full suite: 447 tests collected cleanly
  (`/tmp/jobs/hroj-collect3.log`), both before and after the fix.
- Targeted-subset gate:
  `pytest tests/test_scn_session.py tests/test_fixture_invoke_retry.py
  tests/test_infrastructure.py` → 55 passed
  (`/tmp/jobs/hroj-subset2.log`). This subset surfaced one real regression
  during development — `test_new_doc_emits_synthetic_begin_journey_session_
  event` passes `request=object()` (a bare sentinel, not a real
  `FixtureRequest`) and `request.addfinalizer(...)` raised `AttributeError`
  on it. Fixed by guarding the finalizer registration with
  `hasattr(request, "addfinalizer")` instead of `is not None` — logged
  above as part of the applied fix, not left as a known-failure.
- Live budget: 2/2 used on the backstop; no live regression run beyond that
  (full `pytest -x` is S5's job, not this section's, per Global rules).

**`gts-lirp` — no update needed.** Its description already correctly
identifies the "file is in trash" screenshot in its own failure as the
already-diagnosed post-`finally:` artifact (attributing it to `gts-3zl5`,
not the real cause) and separately names the actual suspected defect (zero
`importList.*` events server-side). That diagnosis was already accurate
before this fix; this fix means a *future* recurrence of `gts-lirp`'s
underlying symptom won't need that same manual disambiguation step.

**Files changed:** `scn/session.py`, `tests/conftest.py` (docstring only),
`tests/test_import.py`, `tests/test_team_scope.py`, `tests/test_journey.py`,
`tests/test_sync_all.py`, `tests/test_kkm7_batching.py`,
`tests/test_hroj_diagnostics_backstop.py` (new), `pyproject.toml` (new
`hroj_backstop` marker registered).

**Next action:** S3 (`gts-ir1f`, live attempt #6 on
`test_import_flow_forward_sync`) is now unblocked — both its prerequisites
(S1, S2) are `DONE`. It needs a fresh agent per the plan's per-section
isolation, its own `bd prime` + `bd show gts-ir1f`, and should confirm
`pnpm run deploy:test` freshness before spending its first live attempt.

---

## S3 — Live attempt #6 on `test_import_flow_forward_sync`

**Status:** ✅ DONE — 2026-08-07 (regression=pending)
**Bead:** `gts-ir1f`
**Entry condition:** S1 `DONE` and S2 `DONE` (or S2 `BLOCKED` with a recorded
human decision to proceed anyway).
**Live GAS cost:** attempt budget **2**. This is attempt #6 and #7 of a
sequence that is 0-for-5.
**Files in scope:** none. This section runs a test; it does not change code. If
it finds a code defect, it records it and stops — the fix belongs to a section
or bead of its own.

**Isolation rationale:** this is a pure verification step whose whole value is
that the tree is otherwise untouched. Any edit made here invalidates the
verification it exists to produce.

**Why:** the `scn_other` → `_seed_import_candidate` change in `test_import.py`
is code-complete but never live-verified. It structurally mirrors
`test_import_access_filter`'s already-proven pattern, which is suggestive, not
proof.

**Procedure**

1. Confirm the TEST deployment is current: `pnpm run deploy:test` if there is
   any doubt (a stale deployment reproduces the `sync.warn: Non-JSON response`
   class this plan is trying to eliminate).
2. `pytest tests/test_import.py::test_import_flow_forward_sync -v >
   /tmp/jobs/ir1f-attempt6.log 2>&1`, poll with `tail -30`.
3. Classify the outcome before doing anything else — see S4.

**Acceptance criteria**

- [x] Deployment freshness confirmed and stated in **Result**.
- [x] Attempt #6 run to completion; full log preserved and its path recorded.
- [x] Outcome classified as exactly one of: **PASS**, **`gts-lirp` symptom**
      (empty `read_import_list()` result / no `importList.*` events), **new
      transport failure** (which would mean S1 is incomplete), or **other**.
      → **PASS.**
- [x] If it failed: the diagnostics artifact was checked and is confirmed
      **pre-teardown** (i.e. S2 works). If the artifact is still post-teardown,
      that is an S2 regression — report it, do not work around it.
      **N/A — test passed, no failure artifact produced.**
- [x] Attempt budget respected; a 3rd attempt requires a fresh human decision.
      **1 of 2 used; 1 remains unspent (not needed).**

**Exit condition:** outcome recorded in **Result** and in `bd note gts-ir1f`.
Do not close `gts-ir1f` here — S5 owns that.

**Result:**

**Outcome: PASS.** `test_import_flow_forward_sync` (which exercises the
`scn_other` → `_seed_import_candidate` change) is now live-verified on the
first attempt of this session (attempt #6 overall; attempt #7 not needed —
1/2 of this section's budget spent, sequence is now 1-for-6 rather than
0-for-5).

**Deployment freshness:** `python scripts/call_webapp.py get_test_config` →
`"version": "v0.2.2 (Rev. Aug 6, 2026 10:35) (TEST)"` — same revision already
confirmed current during S2's backstop runs. No redeploy needed: neither S1
nor S2 touched GAS source (`.js`), only Python test-harness files, so the
TEST WebApp deployment was never stale relative to this run.

**Run:** `pytest tests/test_import.py::test_import_flow_forward_sync -v` →
`/tmp/jobs/ir1f-attempt6.log`. Result: `1 passed in 379.58s (0:06:19)`
(`setup=13.66s call=343.87s teardown=15.33s`,
`baseline=793.42s (-53%)` per the project's own duration instrumentation —
consistent with this test predating any batching retrofit and running as a
single scenario).

**No new transport failure** (S1 held: no 404/echo-page abort, no
`invoke_fixture`-path error). **No `gts-lirp` symptom** (no empty
`read_import_list()` / missing `importList.*` events — the test's own
assertions on the imported rows passed). **Diagnostics ordering (S2)** not
exercised by this run since there was no failure to capture — nothing to
verify here; S2's own backstop already proved it live in its own section.

**Operational note:** the initial invocation was launched with a redundant
trailing `&` inside a `run_in_background: true` Bash call, which caused the
outer wrapper to report "completed" a few seconds in (it had only *launched*
pytest, not waited for it) while the actual pytest process (PID 5075)
continued running detached for the full ~6.3 minutes. Caught by checking
`ps aux` against the reported PID; recovered by polling process liveness
directly rather than trusting the premature "completed" status, and by not
starting a duplicate run. No live-attempt budget was consumed by this
mistake — it was the same single live run, correctly observed to completion.
Worth remembering: don't combine `&` with `run_in_background: true` — pick
one.

**Files in scope:** none changed, as declared — this section is
verification-only.

---

## S4 — Triage S3's outcome to the right owner

**Status:** ✅ DONE — 2026-08-07
**Bead:** depends on outcome.
**Live GAS cost:** none.
**Files in scope:** bead notes and `docs/regression-suite-health-review-2026-08-05.md`
(`#3b` section + priority table row #3). No code.

**Isolation rationale:** the failure mode this plan exists to correct is
mis-attribution — treating a real product bug as generic infra flake. Making
classification its own step, with its own agent and its own rules, is what stops
that recurring a third time.

**Routing rules**

| S3 outcome | Action |
|---|---|
| **PASS** | `scn_other` change is live-verified. Note it on `gts-ir1f`; proceed to S5. |
| **`gts-lirp` symptom** | This is a **product/harness bug, not flake**. Append the evidence to `gts-lirp`, mark `gts-ir1f`'s `scn_other` item as blocked-by `gts-lirp`, and stop spending attempts on it. Do **not** re-run. |
| **New transport failure** | S1 is incomplete. Reopen `gts-z6bx` with the evidence. Do not re-run S3. |
| **Other / genuinely novel** | Capture via `/lessons-learned` (capture phase only — never auto-select a resolution) and present to the human. |

**Acceptance criteria**

- [x] Outcome routed per the table; the bead(s) updated with concrete evidence
      (log excerpt, Axiom query, screenshot path), not a summary. **PASS row**
      applied: `gts-ir1f`'s note already carries the concrete evidence (log
      path, pass duration, no-symptom confirmation) from S3 — added there in
      that section, verified still present via `bd show gts-ir1f`. No further
      bead update needed for the PASS route beyond what S3 already recorded.
- [x] `docs/regression-suite-health-review-2026-08-05.md` `#3b` + priority row
      #3 updated so the review doc remains the single source of truth (the
      handoff explicitly defers to it). Row #3 in the priority table, the
      "Next-run pointer," `#3` section's two remaining AC checkboxes (`scn_
      other` live-verify, full-suite-pending note), and `#3b`'s live-
      verification AC checkbox all updated to reflect the 2026-08-07 PASS.
- [x] If the outcome was **not** PASS: N/A — outcome was PASS, no
      accept/defer/block recommendation needed.
- [x] `HANDOFF-gts-ir1f-2026-08-06.md` either updated or explicitly retired as
      superseded by the review doc. **Retired**: a superseded-notice banner
      added at the top pointing to this plan and the updated review-doc
      sections; body left intact as the historical session record.

**Exit condition met:** PASS routed (trivial row — note already on `gts-ir1f`
from S3, review doc updated here). No bead reopened, no new bead filed, no
re-run needed. `gts-ir1f` stays OPEN per its own AC (full-suite `pytest -x`
still outstanding) — S4 does not close it; that's S5's job per the routing
table ("proceed to S5").

**Result:**

Outcome was **PASS** (per S3), so this section applied the trivial row of
the routing table: no bead reopened, no re-run, no `/lessons-learned`
capture needed — this was the expected/hoped-for outcome, not a novel
failure mode requiring a corrective-action decision.

**Files changed this section:**
- `docs/regression-suite-health-review-2026-08-05.md` — priority table row
  #3, "Next-run pointer" paragraph, `#3` section's two open AC items, `#3b`
  section's live-verification AC item. All now read PASS/2026-08-07 instead
  of the stale 4/4-then-5/5-blocked state.
- `HANDOFF-gts-ir1f-2026-08-06.md` — superseded banner added at top; body
  unchanged (kept as historical record).
- This plan file (`plan-0806-flake-recovery.md`) — this Result block, status
  ledger.

**Bead state:** `gts-ir1f` unchanged by this section (still `IN_PROGRESS`,
`regression=pending`) — its S3-authored note already contains the PASS
evidence; nothing in the routing table's PASS row calls for a further bd
action beyond "note it," which S3 already did.

**Next action:** S5 (merge gate) is next and last. Entry condition (S1–S4 all
DONE) is now met. S5 needs: `pnpm run deploy:test` freshness check, full
`pytest -x` to a log file, triage of any failure, then
`bd set-state regression=verified` for `gts-z6bx`/`gts-hroj`/`gts-ir1f` (only
for what the clean run actually covers), a decision on closing `gts-ir1f`,
`/doc-trigger-check`, and a final changed-files/validation report for human
approval — per Conservative profile, S5 does not commit or push on its own.

---

## S5 — Merge gate

**Status:** 🛑 BLOCKED — 2026-08-07 (resumption run, post-`gts-bops`) — routed to `gts-lirp`, needs human decision
**Live GAS cost:** one full suite run (~the dominant cost in this plan).
**Files in scope:** none by default. Fixes for failures found here are scoped
per-failure and may require a human decision first.

**Isolation rationale:** the gate must observe a tree nobody is editing.
Concurrent work invalidates the run.

**Why:** every bead touched above closes at `regression=pending`. Per CLAUDE.md,
merge to master requires every bead in scope to be `regression=verified`, which
means one clean full `pytest -x`.

**Procedure**

1. Confirm S1–S4 are `DONE` (or explicitly accepted as `BLOCKED` by the human)
   and no section is mid-edit.
2. `pnpm run deploy:test` so the suite runs against current GAS source.
3. Full suite to a file. Use `pytest -x` here — fail-fast is correct at the
   merge gate on a tree expected to be green (this is the one place `-x` is
   sanctioned; it is still never `--sw`).
4. Triage any failure against the known classes before treating it as new.

**Acceptance criteria**

- [x] Full `pytest -x` run to completion against a current TEST deployment; log
      path recorded. `/tmp/jobs/s5-full-suite.log`.
- [x] Result is **not clean** — triaged below and presented for an explicit
      human decision. No workaround attempted; no retry issued.
- [ ] `bd set-state <id> regression=verified` for `gts-z6bx`, `gts-hroj`, and
      `gts-ir1f` — **not done.** The run is not clean (stopped at test 82/447
      on `-x`), so per this AC's own text ("only for those actually covered
      by the clean run") and the Backstop rule ("merge-gate... requires...
      full `pytest -x` clean"), nothing flips to `verified` from a failed run
      — even though `gts-z6bx`'s and `gts-hroj`'s own targeted tests
      (`test_fixture_invoke_retry.py`, present in the 80 passed) did pass
      individually within it.
- [ ] `gts-ir1f` closed, or left open with a precisely-named remainder. **Left
      open** — blocked on the human decision below, not on `gts-ir1f`'s own
      scope (its own item, `scn_other`/`_seed_import_candidate`, is already
      live-verified per S3/S4).
- [ ] `/doc-trigger-check` — **not run**; deferred until the human decision
      below is made, since the review doc (`docs/regression-suite-health-
      review-2026-08-05.md`) would need a new F10 entry either way and it's
      more useful to write that once, informed by the decision, than twice.
- [x] Changed files, validation performed reported below. **No commit/push
      commands proposed** — nothing new to commit beyond what S1–S4 already
      produced (unchanged); this section produced no code changes.

**Result:**

**Deployment:** `pnpm run deploy:test` completed clean —
`v0.2.2 (Rev. Aug 7, 2026 05:21) (TEST)`. A script-property drift warning
fired (`TEST_DOC_ID` differs between GAS remote and `local.settings.json`);
declined the tool's interactive "reset to canonical values?" prompt rather
than answer it unattended — the tool's own message says this drift is
expected churn from `beginTestSession`/`endTestSession`, not damage, and a
merge-gate run has no standing to mutate GAS script properties on its own
judgment. Deploy itself was unaffected by declining.

**Run:** `pytest -x` (full suite, 447 collected) →
`/tmp/jobs/s5-full-suite.log`. Stopped at test 82/447:
**`1 failed, 80 passed, 1 skipped in 2082.46s (0:34:42)`**.

**Failure — new class, not a match for any of F1–F9:**

```
tests/test_journey.py::test_journey FAILED
AssertionError: GAS backend error: tracker.error
  {'msg': 'Service Documents failed while accessing document with id
  1vlEy3upi2OGCcqGhsf6lGbgYZvFSE4g4GmS8a2mTXSo.',
   'docId': '1vlEy3upi2OGCcqGhsf6lGbgYZvFSE4g4GmS8a2mTXSo', 'env': 'test'}
```

Traced to `src/TrackerTable.js:49` (`insertTrackerTable`):
`DocumentApp.openById(docId)` throws Google's standard transient-service
message ("Service Documents failed while accessing document with id …"),
caught at `TrackerTable.js:86`, logged as `tracker.error`, and re-thrown.
`scn/session.py::_check_gas_errors()` (the same GAS-error-fence guard that
`gts-pm72` targeted) sees the `.error`-suffixed log tag and fails the test —
correct behavior for the guard; the gap is upstream of it.

**Not the same as `gts-pm72`:** that bead's fix wraps Drive Advanced-Service
calls (`files.list` and siblings) inside `SyncManager.js`'s folder-walk in a
bounded retry. This failure is a `DocumentApp` (Docs service, not Drive)
call inside `TrackerTable.js`, a different file and a different Google
service — outside `gts-pm72`'s stated scope (`src/SyncManager.js` folder-walk
helpers). No existing retry wrapper covers it.

**Not a `gts-lirp` symptom** (that's an empty `read_import_list()`/missing
`importList.*` events pattern; this is a hard exception from
`DocumentApp.openById`, unrelated).

**Diagnostics artifact (S2 check):** captured
`test-results/FAIL-tests-test-journey-py-test-journey.png` plus frame URLs
and per-frame visible-button list, showing the **live Docs editor toolbar**
(`'Editing'`, `'\xa0\nShare'`, the add-on sidebar with `'Sync'`/`'Import'`/
etc.) — **not** post-trash Drive chrome. S2's fix holds: this is a
trustworthy pre-teardown artifact of a real (if transient) GAS-side error,
not a mis-diagnosed teardown race.

**Classification: new finding, filed here as F10 candidate** (not yet added
to the review doc — that edit is part of the deferred `/doc-trigger-check`
above, pending the human decision) — **"GAS-side transient error gap:
`DocumentApp.openById` uncovered by any retry, unlike `gts-pm72`'s Drive-
service coverage."** This is exactly the class of decision Global rules and
this section's own AC reserve for a human: "Known test failures are never a
basis for proceeding autonomously." No retry was issued (would burn a live
run guessing at flakiness rather than confirming it), no fix attempted
(out of this section's file scope by its own header), no bead filed (no-
bead-creation-without-asking).

**Recommendation for the human decision:** likely a `gts-pm72`-shaped fix —
extend `DocumentApp.openById` (and any sibling Docs-service calls reachable
from the same paths, e.g. `TrackerTable.js`'s other `doc.*` calls) with the
same bounded-retry pattern (`_fetchDriveWithRetry`'s GAS-side shape), proven
via the same forced-failure backstop `gts-pm72` used. Scoping that as a new
`[FIX]` bead (twin-ticketed per project convention) is a reasonable default,
but is presented here rather than filed, per the no-bead-creation rule.

**Files changed this section:** none (verification-only, as declared).

**Next action — human decision needed before S5 can complete:**
1. Authorize filing a new `[FIX]`+`[TST]` twin-ticket pair for the
   `DocumentApp.openById` retry gap (F10 candidate), or say if this should
   be folded into `gts-pm72`'s reopened scope instead.
2. Decide whether to re-run `pytest -x` now (this failure is 1/447 and
   plausibly self-resolves on retry, exactly like `gts-pm72`'s pre-fix
   symptoms did) — note this is **not** covered by S3's attempt-budget
   language (that budget was `gts-ir1f`-specific and already spent/closed);
   a fresh budget decision is needed here rather than assuming it carries
   over.
3. Once (1)/(2) are resolved and a clean run exists, this section's
   remaining ACs (regression=verified flips, `gts-ir1f` close decision,
   `/doc-trigger-check`, F10 write-up in the review doc) can complete.

**Human decision (2026-08-07):** authorized one re-run on the theory that F10
was a one-off transient. One re-run spent.

**Re-run #1 result:** `pytest -x` → `/tmp/jobs/s5-full-suite-rerun1.log` —
**`1 failed, 62 passed in 1453.88s (0:24:13)`**. Stopped at test 63,
before reaching `test_journey.py` — so F10 was neither reproduced nor
disproven by this run. Instead hit a **different, already-documented**
failure: `tests/test_floating_action_scanner.py::
test_soft_return_survives_sidebar_status_flush` got `RuntimeError: HTTP 404
from GAS WebApp (action='run_fixture')` **after 3 attempts** —
`scn/session.py::_http_post`'s existing bounded retry (the F1/F7 /
`gts-pm72` class) engaged as designed but the routing blip outlasted all 3
attempts this time. Not a new class; not `gts-z6bx` (that bead's fix is
`invoke_fixture`, a different call site, and it worked as delegated here);
not F10 (different file, different service, different symptom).

Two consecutive full-suite attempts, two different failures from two
different (both pre-existing) causes, neither reaching completion. This is
itself informative: at ~450-test scale against a single live GAS backend,
the already-known F1/F7 flake rate alone is high enough to make a fully
clean `pytest -x` a low-probability event without either (a) raising
`_HTTP_POST_MAX_ATTEMPTS`/backoff, or (b) the fast/slow tiering + `-n`
parallelism reduction already flagged as review-doc priorities #5/#6
(un-started, blocked on human decisions of their own). Re-running a third
time on the same unchanged tree is unlikely to be more informative than
these two runs already were — recommending against a third autonomous
attempt; stopping here per the one-re-run authorization actually given.

**Status held at BLOCKED — awaiting further human direction** (not a new
question about F10 specifically; the open questions now are: (a) still F10's
own triage from before this re-run, unresolved; (b) whether to spend a 3rd
live attempt, raise the retry bound, or accept the current suite as
too-flaky-to-fully-verify-in-one-pass at present and merge on a documented
debt basis instead).

**2026-08-07, later same day — F10 fixed as `gts-bops` (human directed: "fix
the issue by doing retries... make a retry utility wrapper... scan for other
similar calls... make sure we are using the wrapper").** Full detail: bead
`gts-bops` (closed, `regression=pending`). Summary:

- New `src/RetryUtil.js::withGasRetry(label, fn, options)` — bounded retry
  (3 attempts, 1s backoff) for GAS built-in/advanced-service calls that fail
  by *throwing* a transient exception (`DocumentApp.openById`,
  `SpreadsheetApp.openById`, `DriveApp.getFileById`/`getFolderById`) rather
  than returning an HTTP code — the exception-based sibling of `gts-pm72`'s
  `_fetchDriveWithRetry` (which only covers Drive REST response codes).
  Classifies retryable-vs-real errors by message pattern so a genuine
  not-found/permission error still surfaces on attempt 1.
- Scanned and applied across **19 production call sites** in
  `SyncManager.js`, `TrackerTable.js` (including the actual F10 site,
  `TrackerTable.js:49`), `VerifySync.js`, `WebApp.js`,
  `WorkspaceAddonCard.js`, `AccessControl.js`, `SheetSetup.js`. Deliberately
  excluded: `TestFixtures.js`/`SPIKE.js`/`PROBE.js` (test/spike scaffolding,
  not product paths — flagged as a follow-up candidate, not fixed here), and
  `GasLogger.js`'s own internal `DriveApp.getFolderById` call (wrapping it
  would create a circular dependency on `GasLogger.log` from inside
  `GasLogger`'s own folder-resolution path).
- Every retry/exhaustion/recovery logs via `GasLogger` with the
  caller-supplied `label` (so a failure log line names its own origin
  without stack-trace guessing) + attempt count.
- **Backstop proof — 3 live tests, all PASS**
  (`tests/test_bops_gas_retry_backstop.py`, deployed against
  `v0.2.2 Rev. Aug 7 09:40 TEST`): retry-engagement-and-recovery within
  budget (`test_recovers_within_retry_budget`), bounded exhaustion — still
  throws + logs after exactly 3 attempts, `TrackerTable`'s own pre-existing
  `tracker.error` catch fires unchanged (`test_exhaustion_still_bounded_
  and_logged`) — and non-retryable classification, proven via a dedicated
  pure-function self-test fixture rather than a live not-found doc
  (`test_classifier_does_not_retry_real_errors`).
- A direct re-run of `test_journey.py::test_journey` (the test F10 was
  originally caught in) was attempted for extra confidence but was
  **inconclusive** — it failed on an *unrelated*, already-known F1/F7
  client-side transport flake (exhausted `_http_post` retry on a non-JSON
  echo-page response) before reaching the `TrackerTable` code path at all.
  This is the **third** live run today to hit a different instance of the
  same pre-existing transport class (S5's first pass hit F10 itself; S5's
  re-run hit the same client-transport class at a different test; this one
  hit it a third time) — reinforcing rather than changing the earlier
  finding that the suite-wide background flake rate is high enough to make
  a fully clean full-suite pass a low-probability single-attempt event right
  now.
- `gts-bops` closed with `regression=pending` — only the 3 targeted backstop
  tests ran clean against this change; the full-suite `pytest -x` merge gate
  (S5's own job) has not yet been re-run against it.

**Next action for a fresh session:** S5 is still the resumption point. Its
prerequisite work has grown by one bead (`gts-bops`, now closed) since the
last S5 attempt. Recommended sequence: (1) `pnpm run deploy:test` freshness
check (already fresh as of this session, but confirm), (2) full `pytest -x`
to a log file — this is now the first full-suite attempt with the F10 fix
in place, (3) if it fails again on the F1/F7 client-transport class rather
than a code defect, that's the signal to stop attempting live full-suite
runs and instead prioritize the review doc's already-flagged, still-
unstarted priorities #5 (fast/slow tier + `-n` parallelism) and/or raising
`_HTTP_POST_MAX_ATTEMPTS`/backoff, rather than continuing to spend live
attempts hoping for a lucky pass.

---

**2026-08-07, resumption run (this session).** Followed the recommended
sequence above.

**Deployment:** `pnpm run deploy:test` clean —
`v0.2.2 (Rev. Aug 7, 2026 11:05) (TEST)`, includes `gts-bops`'s
`RetryUtil.js` change (working tree at time of deploy). Log:
`/tmp/jobs/s5-resume-deploy.log`.

**Run:** `pytest -x -v` (450 collected — up from 447, reflects new backstop
test files) → `/tmp/jobs/s5-resume-full-suite.log`. Stopped at test 75/450:
**`1 failed, 73 passed, 1 skipped in 2261.50s (0:37:41)`**.

**Failure — routes to an existing known class, `gts-lirp` (NOT F10, NOT
new):**

```
tests/test_import.py::test_import_flow_forward_sync FAILED
AssertionError: expected source docs visible, got []
tests/test_import.py:440
```

This is the identical symptom string `gts-lirp`'s own notes already record
for its second occurrence, in the **same test**. It is also the same test
S3 live-verified as a clean PASS on 2026-08-06
(`/tmp/jobs/ir1f-attempt6.log`, `1 passed in 379.58s`) — no code touching
`scn/ui.py`'s `read_import_list()`/`show_tab()` path landed between the two
runs (S1/S2/`gts-bops` all touched other files). This **confirms the bug is
genuinely intermittent** at the test level: same test, same unmodified code
path, pass on one run and fail on another. Diagnostics artifact (S2 check):
pre-teardown, trustworthy — live editor toolbar, not post-trash chrome.

Per S4's routing table, a `gts-lirp`-symptom failure is **"a product/harness
bug, not flake — append evidence to `gts-lirp`, mark `gts-ir1f`'s `scn_other`
item as blocked-by `gts-lirp`, and stop spending attempts on it. Do not
re-run."** Both actions done: `bd note gts-lirp` (3rd-occurrence evidence,
including the S3-PASS-vs-this-FAIL contrast) and `bd note gts-ir1f` +
`bd dep add gts-ir1f gts-lirp --type blocked-by`. No re-run issued — per the
routing table and the Global "known test failures are not a basis for
proceeding autonomously" rule.

**F10 (`gts-bops`) status this run: cannot confirm or deny.** The suite
stopped at test 75 on the `gts-lirp` failure, one test before it would have
reached `test_journey.py::test_journey` (the original F10 site) in file
order. `gts-bops`'s own targeted backstop (3/3 live PASS, see that bead)
remains the only live evidence the F10 fix works; this run neither
reproduces nor contradicts it.

**Not re-triaged as new/F10/transport:** confirmed distinct from all of
F1–F10 — different symptom shape (empty adapter-filtered `visible_ids`, not
an HTTP/transport error and not a `tracker.error` GAS exception).

**Files changed this section:** none (verification-only, plus `bd note`/
`bd dep` calls, which are data not code).

**Remaining S5 ACs still open, same as before this run:** `regression=verified`
flips, `gts-ir1f` close decision, `/doc-trigger-check`, F10 review-doc
write-up — all still blocked, now on `gts-lirp`'s fix landing (or a human
decision to accept `gts-lirp` as documented debt and merge without a fully
clean full-suite pass).

**Next action for a fresh session:** this is now a human decision point, not
a resumable procedural step. Options: (a) prioritize a `gts-lirp` fix session
(bead already has two candidate root-cause shapes in its Design section —
no-round-trip vs. stale-DOM-parse — a fix needs to cover both per its own
notes) before attempting S5 again; (b) accept `gts-lirp` as known,
documented flake debt and decide whether that's mergeable on its own terms
(would be a deviation from the Backstop rule's "full `pytest -x` clean"
requirement — needs explicit human sign-off, not an autonomous call); (c)
spend a further live `pytest -x` attempt on the theory this too is a one-off
(no budget currently authorized for that, same as F10's re-run required
explicit authorization). No autonomous choice made among these three by this
session, per Global rules.

---

## Status ledger

| Date | Section | Event |
|------|---------|-------|
| 2026-08-06 | — | Plan created; `gts-z6bx` and `gts-hroj` filed. |
| 2026-08-06 | S1 | Done. `invoke_fixture` now delegates to `scn.session._http_post` (shape 2). Backstop proof: `tests/test_fixture_invoke_retry.py` fails 3/7 pre-fix, 7/7 post-fix. Subset gate 49 passed. `gts-z6bx` closed, `regression=pending`. |
| 2026-08-06 | S2 | Done. Diagnostics-ordering fix (F9) landed as shape (3) — deferred trash via `ScenarioSession.new_doc(request=...)`'s pytest finalizer — not the bead's stated-preferred shape (1), which was empirically disproven (mocked, no live cost): no pytest hook can run before a failing test's own `finally:` has already executed, since that's plain Python call-stack unwinding. Live backstop (2/2 budget): pre-fix pattern reproduced `buttons=['Go to Docs home screen','Take out of trash']`; post-fix showed the live editor. `gts-hroj` closed, `regression=pending`. **Next action: S3 (`gts-ir1f`, live attempt #6 on `test_import_flow_forward_sync`) is now unblocked (S1 + S2 both DONE) and is the next section to pick up — fresh agent, its own `bd prime` + `bd show gts-ir1f`, confirm `pnpm run deploy:test` freshness before spending its first live attempt (budget: 2).** |
| 2026-08-07 | S3 | Done. Live attempt #6 on `test_import_flow_forward_sync` **PASSED** (`1 passed in 379.58s`, `/tmp/jobs/ir1f-attempt6.log`) — deployment already fresh (Rev. Aug 6 10:35 TEST, unchanged since S2), 1/2 attempt budget used, 2nd not needed. No `gts-lirp` symptom, no new transport failure — S1's fix held under live load. `scn_other`/`_seed_import_candidate` is now live-verified. `bd note`d on `gts-ir1f`. **Next action: S4 (triage) — routes to the trivial "PASS" row of S4's table (note on `gts-ir1f`, proceed to S5); still needs to be executed as its own section per the plan's isolation model, then S5 (merge gate: full `pytest -x`, flip `regression=verified` for `gts-z6bx`/`gts-hroj`/`gts-ir1f`, decide on closing `gts-ir1f`).** |
| 2026-08-07 | S4 | Done. PASS row of the routing table applied — no bead reopened, no re-run, no `/lessons-learned` capture (not a novel failure mode). Updated `docs/regression-suite-health-review-2026-08-05.md` (priority row #3, "Next-run pointer," `#3`/`#3b` AC checkboxes) to reflect the 2026-08-07 PASS instead of the stale 5/5-blocked state. Retired `HANDOFF-gts-ir1f-2026-08-06.md` with a superseded banner (body kept as historical record). `gts-ir1f` bead unchanged — S3's note already carries the PASS evidence; still `IN_PROGRESS`/`regression=pending` pending S5. **Next action: S5 (merge gate) — the only remaining section. `pnpm run deploy:test` freshness check, full `pytest -x` to a log file, triage any failure as a debt state (not autonomous work-around), then `bd set-state regression=verified` for `gts-z6bx`/`gts-hroj`/`gts-ir1f` (only what the clean run covers), decide on closing `gts-ir1f`, run `/doc-trigger-check`, and report changed files + exact commit/push commands for human approval (Conservative profile — do not commit/push).** |
| 2026-08-07 | S5 | **BLOCKED.** Deployed TEST clean (`v0.2.2 Rev. Aug 7 05:21`), ran full `pytest -x` (447 collected) → stopped at 82/447: `1 failed, 80 passed, 1 skipped in 2082.46s`. Failure is a **new class (F10 candidate)**, not any of F1–F9/`gts-pm72`: `tests/test_journey.py::test_journey` hit `AssertionError: GAS backend error: tracker.error {'msg': 'Service Documents failed while accessing document with id ...'}`, traced to `src/TrackerTable.js:49`'s unretried `DocumentApp.openById(docId)` — a transient Google Docs-service error, structurally identical in spirit to `gts-pm72`'s Drive-service gap but in a different file/service, so outside that bead's closed scope. S2's diagnostics fix held (screenshot shows live editor, not post-trash Drive chrome, confirming this is a real GAS-side transient error and not a mis-diagnosed teardown race). No retry issued, no fix attempted, no bead filed — per Global rules ("known test failures... wait for an explicit human decision") and this section's own file-scope restriction ("Files in scope: none by default"). Full triage + recommendation in S5's Result block. **Next action: human decision needed on (1) filing a `[FIX]`+`[TST]` twin-ticket for the `DocumentApp.openById` retry gap vs. folding into a reopened `gts-pm72`, and (2) whether to spend a fresh `pytest -x` re-run now (this failure is 1/447 and plausibly self-resolves like `gts-pm72`'s pre-fix symptoms) — no attempt budget currently authorized for that re-run.** |
| 2026-08-07 | S5 (re-run) | Human authorized one re-run to test the "F10 was a one-off" theory. `pytest -x` re-run → `/tmp/jobs/s5-full-suite-rerun1.log`: `1 failed, 62 passed in 1453.88s`. Stopped at test 63 (before reaching `test_journey.py`), so F10 neither reproduced nor disproven. Hit a **different, already-known** failure instead: `test_floating_action_scanner.py::test_soft_return_survives_sidebar_status_flush` exhausted `_http_post`'s existing 3-attempt bounded retry on HTTP 404 (the F1/F7/`gts-pm72` class) — the retry engaged as designed, the routing blip just outlasted it this time. Two consecutive full-suite runs, two different pre-existing-class failures, neither completing. Re-run budget (1) now spent; recommending against a 3rd autonomous attempt. **Next action: still needs human direction — F10 triage from the first run remains open, plus a new question of whether to raise `_HTTP_POST_MAX_ATTEMPTS`/backoff, pursue the fast/slow-tier + `-n` parallelism items already flagged in the review doc (priorities #5/#6, unstarted), spend a 3rd live attempt, or accept the suite as currently too-flaky-for-one-clean-pass and consider a documented-debt merge instead.** |
| 2026-08-07 | gts-bops | Human directed: fix F10 with a retry wrapper, scan for and cover similar unretried calls. New `src/RetryUtil.js::withGasRetry` (exception-based sibling of `gts-pm72`'s `_fetchDriveWithRetry`), applied across 19 production `DocumentApp.openById`/`SpreadsheetApp.openById`/`DriveApp.getFileById`\|`getFolderById` call sites (7 files), deliberately excluding `TestFixtures.js`/`SPIKE.js`/`PROBE.js` and `GasLogger.js`'s own internal Drive call. Every retry/exhaustion/recovery logs via `GasLogger` with a caller-supplied call-site label. 3 live backstop tests (`tests/test_bops_gas_retry_backstop.py`) all PASS: retry-engagement-and-recovery, bounded exhaustion, non-retryable classification. Bead closed, `regression=pending` (targeted subset only). A bonus re-run of `test_journey.py::test_journey` was inconclusive — hit an unrelated F1/F7 client-transport flake before reaching the fixed code path; the **3rd** such instance today, reinforcing (not resolving) the suite-wide flake-rate finding. **Next action: S5 resumes with `gts-bops` now folded into its prerequisites — full `pytest -x` re-run is the next step for a fresh session; if it again fails on the F1/F7 transport class rather than a code defect, escalate to the review doc's unstarted priorities #5/#6 (retry-bound/backoff increase, fast/slow tiering, `-n` parallelism) rather than continuing to spend live attempts.** |
| 2026-08-07 | S5 (resumption) | **BLOCKED.** Deployed TEST clean (`v0.2.2 Rev. Aug 7 11:05`, includes `gts-bops`), ran full `pytest -x -v` (450 collected) → stopped at 75/450: `1 failed, 73 passed, 1 skipped in 2261.50s`. Failure: `tests/test_import.py::test_import_flow_forward_sync` — `AssertionError: expected source docs visible, got []` (`tests/test_import.py:440`) — the **identical symptom** already on file for `gts-lirp`, in the same test S3 live-verified PASS on 2026-08-06 with no relevant code change in between, confirming the bug is genuinely intermittent rather than a permanent regression or new class. Routed per S4's routing table: `bd note`d evidence onto `gts-lirp` (3rd occurrence) and `gts-ir1f` (contrast with S3's PASS), added `gts-ir1f` blocked-by `gts-lirp` dependency. No re-run issued (Global rule: known failures need a human decision, not autonomous retry). F10/`gts-bops` neither reproduced nor contradicted — the run stopped one test before reaching `test_journey.py`. **Next action: human decision needed among (a) prioritize a `gts-lirp` fix session before re-attempting S5, (b) accept `gts-lirp` as documented debt and decide on a non-full-clean merge path, (c) authorize one more live `pytest -x` attempt. No option selected autonomously.** |
