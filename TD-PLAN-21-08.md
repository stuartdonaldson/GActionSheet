# Technical Debt Plan — 2026-08-21 (rev. 2)

Source: evaluation of `/tmp/gas-test6.log` (518 collected, 497 passed / 5
failed / 16 skipped, 2:01:44), read against `/tmp/gas-test4.log` and the run
history in `TD-PLAN-20-08.md`. Triage epic: `gts-a8yh`.

> **Revision note.** Rev. 1 of this document concluded that all three
> `TimeoutError` failures shared a root cause in the new `CacheService`
> opId-dedup code, and that the two assertion failures were first-ever
> regressions. Re-reading gas-test4.log and the source disproves both. The
> corrected analysis is below; rev. 1's Stage A step 1 would have spent a
> session in Axiom logs looking for a GAS-side hang that does not exist.
> `gts-85x3.2`'s description carries the same misdiagnosis and needs the
> correction in §5.

---

## 1. Run-over-run picture — count-based comparison is not measuring anything

| Run | Collected | Result |
|---|---|---|
| gas-test.log | 480 | 4 failed / 460 passed |
| gas-test2.log | 487 | 2 failed / 469 passed |
| gas-test3.log | 487 | 19 failed / 14 errors / 439 passed |
| gas-test4.log | 507 | 39 failed / 6 errors / 449 passed |
| gas-test5.log | — | aborted at test 1 by the new auth pre-flight check |
| gas-test6.log | 518 | 5 failed / 497 passed |

The collection set grew by 38 items across the sequence (`test_f3me2_*` did
not exist before gas-test4), and the totals are dominated by whichever
*environmental* failure was active in that run. Comparing pass/fail totals
across these six runs compares three different suites under three different
environment states. That is the mechanism behind the "we keep going in
circles" feeling: each run got a fresh cause hypothesis attached to a number
that was never a stable measure.

**Replacement rule (adopt going forward):** compare runs by *terminal
exception class* and by *test identity*, normalized for collection drift —
not by pass/fail totals. §2 is that comparison.

---

## 2. Are we better than gas-test4? — better number, flat defect count

Every gas-test4 failure/error classified by its terminal exception:

| Class | Count | Environmental? |
|---|---|---|
| `tests.helpers.download.DownloadError` (dead auth → HTML, not docx) | 19 | **yes** |
| Playwright `waiting for locator(".docs-title-outer")` | 14 | **yes** |
| `TimeoutError` — `test_f3me2_*` ×2 | 2 | no |
| `AssertionError` — `test_table_cell_actions_distinct` | 1 | no |
| `DrainInvariantError` — `test_status_token_parens_hardening` | 1 | no |
| uuse `batchFallback count=3` mismatch | 1 | no |

**33 of gas-test4's 45 outcomes were one dead auth session.** Its real
defect count was ~5. gas-test6's real defect count is 5.

**Conclusion: the defect count is flat.** gas-test6 is not evidence the
product improved; it is evidence the *environment* was healthy. That is a
genuine and valuable result — it is the first live confirmation the
`auth_probe.py` / `check_auth.py` mitigation works — but it is the only new
information gas-test6 carries beyond gas-test4. Everything else in
gas-test6's failure list was either already failing identically in
gas-test4, or is state-dependent.

`gts-f3me.4` and `gts-85x3` still should not close on one clean run — but
for the reason stated here, not rev. 1's: a run with no environmental
failure cannot distinguish "fixed" from "didn't fire."

---

## 3. gas-test6.log's 5 failures — corrected attribution

| Test | Terminal exception | Correct cause | Also failed in test4? |
|---|---|---|---|
| `test_f3me2_run_fixture_idempotency.py::test_run_fixture_same_opid_is_not_duplicated` | `TimeoutError` @ 120s | **Test bug — wrong timeout** (§3.1) | **yes, identically** |
| `test_f3me2_run_fixture_idempotency.py::test_run_fixture_different_opid_is_not_deduped` | `TimeoutError` @ 120s | **Test bug — wrong timeout** (§3.1) | **yes, identically** |
| `test_kkm7_batching.py::test_syncdocument_batches_flush_for_multiple_actions_single_doc` | `TimeoutError` @ 360s default, on the **3rd** `append_doc_paragraph` after two succeeded | Genuinely unexplained; single occurrence (§3.2) | no — failed there with `DownloadError` (auth) |
| `test_inline_formatting.py::test_plain_action_text_has_no_runs` | `AssertionError` — `sheetRuns` has a full-span italic run | **Residual cell formatting on a reused row** (§3.3) | no |
| `test_team_portal_hardening.py::test_r13b_action_level_deleted_sync_status_excluded` | `AssertionError` — `Deleted` row present under `statusFilter=all` | Shared-state / ordering (§3.4) | no — **ERRORed in test3** |

### 3.1 The two f3me2 timeouts are a deterministic test-authoring bug — not a hang

Both fail at the *same line* with the *same exception* in gas-test4 and
gas-test6. A hang that reproduces byte-identically across two runs four days
apart is not a hang.

`tests/test_f3me2_run_fixture_idempotency.py:56` hand-rolls the payload and
calls:

```python
resp1 = scn._post(payload, timeout=120)   # payload["fixture"] == "sync_all"
```

Two facts make this unable to pass:

1. **`sync_all` is the full-corpus sweep.** `src/TestFixtures.js:2765` —
   `case 'sync_all': syncAll(); SpreadsheetApp.flush();`. It does **not**
   scope to `testDocId`; `testDocId` only rebinds `TEST_DOC_ID` around the
   call. The test's own docstring — *"using the cheap single-doc 'sync_all'
   fixture rather than a full-corpus sweep so the test stays fast"* — is
   factually wrong about what that fixture does, and is the origin of the
   error.
2. **The codebase already documents that this call exceeds 360s.**
   `scn/session.py`: `_CORPUS_SCALED_FIXTURE_TIMEOUTS = {"sync_all": 600}`,
   with a gts-4m7l comment stating a real `syncAll()` over 100+ docs
   legitimately runs past the default 360s client timeout.

The test bypasses `_post_fixture` deliberately (to pin its own `opId`), and
in doing so bypasses the 600s override — then sets **120s**, a fifth of it.

**The dedup-code hypothesis is independently weak.** `git diff src/WebApp.js`
in this tree is *only* the append guard: one `cache.get`, one
`cache.put(..., 120)`. And `scn/session.py`'s `_http_post` does
`payload.setdefault("opId", str(uuid.uuid4()))`, so every non-f3me2 call
mints a fresh key and the `get` always misses. Two sub-millisecond
`CacheService` operations cannot produce a 360s stall.

### 3.2 One genuinely unexplained timeout remains

kkm7's **3rd** `append_doc_paragraph` stalled past the 360s default after
two byte-identical calls in the same test succeeded seconds earlier. That is
one occurrence, with no prior instance in five runs, on the lightest handler
in the suite (`appendParagraph` + `saveAndClose`). Most consistent with the
known `/exec` routing stall class (`gts-pm72`) than with any shared code
path — but it is not explained, and it is the only part of rev. 1's
"CacheService hang" story that survives scrutiny.

### 3.3 inline_formatting: plain writes never clear residual cell formatting

The assertion detail is the tell — `scanRuns` **passes**, only `sheetRuns`
fails:

```
assert result.get("scanRuns") == []        # PASSES
assert result.get("sheetRuns") == []       # FAILS
E   Left contains one more item: {'bold': False, 'end': 27, 'italic': True, 'start': 0}
```

The scan layer is correct. The Actions-sheet *cell* is italic. Mechanism:

- `SyncManager.js:1247` — `_buildRichTextValueForActionText(text, runs)`
  returns `null` when `runs` is empty (the plain-text case).
- `WebApp.js:1215`/`:1236` — the caller writes the value through
  `appendRow`, and only calls `setRichTextValue` when the builder returned
  non-null.

So **a plain write never clears formatting already on the cell.** Any
Actions-sheet cell that has ever held italic keeps italic when the row is
later reused for plain text — and the suite writes italic into that column
routinely (`TestFixtures.js:2429`, the styled-action fixtures).

This predicts exactly the observed history: clean for four runs, failing
once row reuse lines up. It is a real product bug (the sheet misreports
formatting for plain rows), and it is **order-dependent**.

Not a regression from this cycle's diff: `git diff src/WebApp.js` touches
only `_handleAppendDocParagraph`; nothing in the write path changed.

### 3.4 R13b: shared state, and its history is not clean

Rev. 1 claimed both assertion failures "passed clean on all 4 prior runs."
False for R13b — `test_r13b_action_level_deleted_sync_status_excluded`
**ERRORed in gas-test3.log**, along with its whole module fixture.

`git diff` confirms nothing this cycle touched `_readTeamActions`
(`WebApp.js:1939`) or the delete path, so "new regression from the dedup
fix" is off the table. The live hypothesis is shared-state / ordering:
`_handleDeleteActionRowAtdd`'s own docstring warns the next `sync()` on that
doc re-materializes the paragraph and clears the `Deleted` stamp via
doc-wins reconciliation, and this test runs 9th under a module-scoped
fixture. Same family as `gts-85x3.3`.

---

## 4. Why "isolate and re-run" is the wrong next step for §3.3 and §3.4

Rev. 1's Stage B prescribed re-running each failing test alone. Both
failures are hypothesized to be *state*-dependent, so an isolated run
exercises a different system than the one that failed and will most likely
pass — which would get both filed as flakes and returned to the pool for
run 7. That is the circle, mechanically.

Replace with a **state probe**: reproduce under the conditions that produced
the failure and read the state directly.

---

## 5. Prioritized staged plan

### Stage A — correct the misdiagnosis (do this first; it is mostly bookkeeping) — ✅ DONE 2026-08-21

1. **Fix `tests/test_f3me2_run_fixture_idempotency.py`.** ✅ Both call sites in
   both tests now pass `timeout=600` explicitly (all 4: `resp1`/`resp2` in
   `test_run_fixture_same_opid_is_not_duplicated`, the loop call in
   `test_run_fixture_different_opid_is_not_deduped`). **Docstring corrected**
   — the "cheap single-doc `sync_all`" claim is replaced with an explicit
   note that `sync_all` is the full-corpus sweep and why the 600s timeout is
   required.
2. **Re-scoped `gts-85x3.2`.** ✅ Closed as misdiagnosed (not re-scoped —
   `gts-a8yh.1` already carried the kkm7 instance cleanly, so re-scoping
   would have duplicated it). Closing comment records the §3.1 correction.
   **`gts-a8yh.1` and the `gts-a8yh` epic were also corrected** — both had
   propagated `gts-85x3.2`'s original "shared CacheService dedup deadlock
   across both handlers" hypothesis (`gts-a8yh.1`'s title/description
   explicitly called the kkm7 stall a "recurs gts-85x3.2" / "reproduction");
   left uncorrected, the epic and `gts-a8yh.1` would have re-asserted the
   disproven hypothesis even with `gts-85x3.2` itself closed. `gts-a8yh.1`
   stays **open** — the kkm7 append stall itself (§3.2) is still genuinely
   unexplained — but now on the narrower, corrected basis (single occurrence,
   most consistent with `gts-pm72`-class `/exec` routing stalls, not a
   code-level cache deadlock). Do not cite `gts-85x3.2` as corroboration for
   `gts-a8yh.1` going forward.
3. **Enforced `_CORPUS_SCALED_FIXTURE_TIMEOUTS` at `_post`, not just
   `_post_fixture`.** ✅ `scn/session.py`'s `_post` now defaults `timeout` to
   `self._CORPUS_SCALED_FIXTURE_TIMEOUTS.get(payload.get("fixture"), 360)`
   when the caller omits `timeout` (was a hardcoded `360` default before).
   `_post_fixture` simplified to a thin passthrough — the lookup used to live
   in both places redundantly, now lives once in `_post`. Effect: any future
   hand-rolled `_post(...)` call carrying `payload["fixture"] == "sync_all"`
   gets the 600s timeout automatically even without an explicit `timeout=`,
   closing the exact gap that produced this bug. Non-fixture `_post` calls
   and fixture calls not in the timeout table are unaffected (still default
   360s). Existing explicit-`timeout=` callers (`test_team_folder_
   reconciliation.py`, `test_sync_all.py`, `test_uuse_scoped_listing.py`)
   are unaffected — `_post` only applies the lookup when `timeout` is
   omitted.

**Handoff to Stage B.** No code changes from Stage A touch `scn/session.py`'s
`_http_post` or its retry/backoff loop — Stage A #3 only changed how `_post`
picks a *default* `timeout` value, not the retry/exception-handling path
Stage B #4 is about. `_post`'s signature is now
`_post(self, payload: dict, *, timeout: int | None = None)`; if Stage B ends
up touching `_http_post`'s call signature, note that `_post` now passes a
resolved `int` (never `None`) into `_http_post`, so `_http_post`'s own
`timeout: int = 360` default is effectively dead for all `ScenarioSession`
callers (still live for the one direct `_http_post(...)` call at
`session.py:509`, `begin_journey_session`, which doesn't go through `_post`).
Stage A did not touch that call site.

### Stage B — the one correct item carried from rev. 1 (P1) — ✅ DONE 2026-08-22

4. **Handle `TimeoutError` / `socket.timeout` in `scn/session.py`'s
   `_http_post` retry loop.** Verified against CPython 3.12:
   `urllib/request.py`'s `do_open` wraps only `h.request()` in
   `except OSError: raise URLError(err)`; `h.getresponse()` (request.py:1348
   — visible in all three tracebacks) propagates `TimeoutError` raw, so the
   retry/backoff is bypassed entirely.
   **Caveat:** this does *not* fix §3.1. Retrying a 120s call three times
   still fails, and each retry re-runs a full `syncAll()`. Do Stage A #1
   regardless of this.

   ✅ Added an `except TimeoutError as exc:` clause to `_http_post`'s retry
   loop (`scn/session.py`, positioned after the existing `HTTPError`/
   `URLError` handlers, before the `raw`/JSON-decode branch), routed through
   the *same* `_HTTP_POST_MAX_ATTEMPTS`/exponential-backoff path as the
   404 and non-JSON-echo symptoms (Stage A already widened that budget to 5
   attempts / 3-6-12-24s backoff under gts-f3me.5 — unchanged here, this
   Stage only adds a third exception class into the existing loop).
   Exhaustion raises `RuntimeError("Timed out waiting for response
   (action=..., timeout=...) after 5 attempts")`, matching the style of the
   404/non-JSON exhaustion messages. `socket.timeout` is a `TimeoutError`
   alias as of CPython 3.10, so no separate `socket.timeout` catch is
   needed. Bead: `gts-f3me.7`, closed — no pre-existing bead covered this
   specific gap (`gts-f3me.5`/`.6` cover the 404/non-JSON symptom class and
   the general-slowdown investigation respectively; `gts-a8yh.1`/`gts-85x3.2`
   are about the append-handler stall, not the client-side retry loop).

   Tests added to `tests/test_fixture_invoke_retry.py` (mock-only, no live
   GAS backend, same pattern as the existing 404/non-JSON retry tests):
   `test_retries_and_recovers_on_timeout_error_then_success` and
   `test_exhaustion_after_repeated_timeout_error_names_attempt_count`. Full
   module run: 12/12 passed (`pytest tests/test_fixture_invoke_retry.py`,
   47.5s — the pre-existing 404-exhaustion test still sleeps through mocked
   `time.sleep`, which is itself mocked in this module, so the wall time is
   test-collection/import overhead, not real backoff).

   **Not yet run:** a live-backend `pytest -x` full sweep. This is a
   mock-level unit fix + test; per the project's backstop rules an `[IMP]`-
   equivalent bead may close on the fast targeted-subset gate
   (`regression=pending` was set on `gts-f3me.7` accordingly). Stage E's
   full sweep is still required before this can be marked
   `regression=verified` or before `gts-f3me`/`gts-85x3` can close.

   **Handoff to Stage C.** No further changes to `_http_post`'s retry loop
   are anticipated from Stage C (inline_formatting write-path fix and R13b
   state probe are both server/GAS-side or read-path investigations, not
   `scn/session.py` transport changes). If a Stage C state probe needs to
   hand-roll a `_post`/`_http_post` call with a non-default timeout, note
   `_post`'s signature from Stage A (`timeout: int | None = None`, resolved
   via `_CORPUS_SCALED_FIXTURE_TIMEOUTS` when omitted) — that resolution is
   unaffected by this Stage's change, which only adds an exception handler
   inside the existing per-attempt loop and touches no timeout-selection
   logic.

### Stage C — the two real product bugs, via state probe not isolation (P1) — ✅ DONE 2026-08-22

5. **`gts-a8yh.2` — inline_formatting.** ✅ Closed. Two live state probes were
   built to test the two hypothesized mechanisms directly:
   - `test_plain_edit_clears_prior_italic_formatting` — same globalId,
     doc-authoritative **update** branch (WebApp.js ~1266–1275): seed
     italic, sync, rewrite the doc paragraph as plain text (new
     `replace_action_plain_text` TestFixtures.js case), sync again, assert
     `sheetRuns == []`.
   - `test_archived_row_reuse_does_not_leak_italic_into_new_plain_action` —
     the actual gas-test6.log mechanism per §3.3: seed italic, sync,
     backdate + `Status=Closed` (extended `backdate_action_row` with an
     optional `status` field), run `ArchiveManager.archive(ss)` (new
     `archive_sweep` fixture) to compact the row out, append a brand-new
     plain action, sync, assert the new row's `sheetRuns == []`.

   **Both probes passed even on the pre-fix build** (verified by
   temporarily reverting the fix, redeploying, and re-running — a real
   red/green cycle, not assumed). So neither mechanism is confirmed as
   *the* trigger for the one gas-test6.log occurrence — GAS's `setValue()`
   and same-length `appendRow()` writes turned out to already reset
   per-character text style in both tested paths, contrary to the
   `clearContent()`-preserves-format assumption. The one-off failure's
   exact trigger remains unreproduced.

   **Fixed anyway, as defense-in-depth** (cheap, matches the plan's
   original prescription, and closes a real gap even if it wasn't *this*
   gap):
   - `src/WebApp.js` insert branch (~1220): now *always* issues the
     `setRichTextValue` follow-up write, including the plain-text (`null`)
     case, instead of leaving it a no-op — `appendRow`'s plain-values array
     was never guaranteed to reset a recycled physical row's text style.
   - `src/ArchiveManager.js` `_archiveActionsRows`: now calls
     `clearFormat()` alongside `clearContent()` when compacting the sheet
     — `clearContent()` is documented to preserve per-cell format, and
     compaction is exactly the kind of physical-row-reuse event §3.3
     describes. (`_evictStaleDocData`, the DocData-sheet sibling, was left
     alone — no rich-text columns there, out of scope.)

   Regression coverage: both new tests are durable-invariant hardening
   under `tests/test_inline_formatting.py`, live-verified green post-fix
   (4/4 in that file). `regression=pending` set on the bead — full
   `pytest -x` sweep (Stage E) still required before `regression=verified`.

6. **`gts-a8yh.3` — R13b.** ✅ Closed, contention confirmed, no code fix.
   - Read `_readTeamActions` (WebApp.js:1965): confirms no bug — it
     unconditionally filters `rowSyncStatus === 'Deleted'` before the
     `statusFilter` branch, exactly as rev. 1/this doc's §3.4 already noted.
   - Found the concrete mechanism: `TriggerManager.js` installs a real
     **30-minute `timeBased` `syncAll` trigger** against the live TEST
     account. `syncAll()` is the full-corpus sweep (§3.1). `delete_action_row`
     only stamps `Sync Status = 'Deleted'` — it does not remove the doc's
     underlying floating-action paragraph. So any `syncAll()` firing during
     a test run re-scans `seeded_rows`' doc, finds the action still present,
     takes the doc-authoritative update branch, and its trailing
     `if (existing.syncStatus !== '') setValue(sync_status, '')` clears the
     `Deleted` stamp — exactly what the row's own docstring already warned.
   - Per this Stage's own decision rule: ran the **full**
     `test_team_portal_hardening.py` module in isolation (not the single
     test) — **21 passed / 2 skipped in 301s, R13b included, clean.** A
     clean isolated run is the plan's own stated signal that the
     contention hypothesis is confirmed and code-level suspicion comes off
     the table.
   - Same family as `gts-85x3.3`/`gts-7vo2.2` (Stage D item 8, still open,
     unaffected by this closure).

**Handoff to Stage D/E.** No open threads from Stage C block Stage D — items
7–10 there are independent (download.py circuit breaker, `op`/`parentOp`
fence scoping, uuse batchFallback, `DrainInvariantError` masking). Two things
worth carrying forward for whoever picks up Stage D item 8
(`gts-85x3.3`/`gts-7vo2.2`, the `op`/`parentOp` fence): (a) the concrete
mechanism this Stage found for R13b — a real 30-min `syncAll` `timeBased`
trigger racing the live test suite via `TriggerManager.js` — is likely the
same clock driving that family's other intermittent failures, not just a
hypothesis anymore; (b) `TestFixtures.js` gained two new run_fixture cases
this Stage (`replace_action_plain_text`, `archive_sweep`) and
`backdate_action_row` gained an optional `status` field — all additive, no
existing fixture behavior changed, but worth knowing they exist before
hand-rolling similar probes again. For Stage E's re-run list (item 11): both
`gts-a8yh.2` fixes went through a real revert→redeploy→red, reapply→
redeploy→green cycle already (not just a single green run), so `pytest -x`
there is confirmatory, not exploratory — same posture already holds for
`gts-a8yh.3` (contention, no code changed, module already ran clean once
isolated).

### Stage D — carried over from `TD-PLAN-20-08.md`, still open, still not done

7. `gts-85x3.1` — `download.py` fail-fast circuit breaker for a fully dead
   auth session. Didn't fire in gas-test6 because the environment was
   healthy (§2) — that is not evidence it is unnecessary.
8. `gts-85x3.3` — scope `scn/session.py`'s GAS-error-scan fence by
   `op`/`parentOp`. Now also relevant to §3.4.
9. `gts-85x3.4` — disambiguate the uuse `batchFallback count=3` mismatch.
10. `gts-kkwp` — stop masking `DownloadError` behind `DrainInvariantError`.

### Stage E — verification

11. After Stage A/B/C land, re-run `test_f3me2_run_fixture_idempotency.py`,
    `test_kkm7_batching.py`, `test_inline_formatting.py`, and the full
    `test_team_portal_hardening.py` **module**. Then a full non-stopping
    sweep (no `-x`, no `--sw`, output to a file) per the project's
    full-suite-sweep rule.
12. **Report that sweep by §1's replacement rule** — exception class and
    test identity, normalized for collection drift — not by pass/fail
    totals. Specifically: does `test_f3me2_*` clear, does the kkm7 append
    stall recur, and did any *environmental* class (`DownloadError`,
    Playwright locator) fire at all. If none fired, the run again says
    nothing about `gts-f3me.4` / `gts-85x3`.
13. Close `gts-f3me.4` and `gts-85x3` only on a clean sweep **plus** at
    least one run where the auth mitigation demonstrably had something to
    catch — or on an explicit decision to accept "didn't fire" as
    sufficient. State which.

---

## 6. Standing correction to carry forward

Three habits produced rev. 1's errors, and are worth naming so run 7 does
not repeat them:

- **Reading run-over-run progress off pass/fail totals** across a changing
  collection set and a changing environment (§1).
- **Attributing co-occurring failures to a shared new cause** because the
  new code is nearby, without checking whether the same failure predates it
  (§3.1 — the identical failure was sitting in gas-test4.log).
- **Prescribing isolated re-runs for state-dependent failures** (§4).
