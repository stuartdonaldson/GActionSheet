> **SUPERSEDED 2026-08-07.** The open item this handoff describes (live
> verification of `test_import.py`'s `scn_other` change) has since **PASSED**
> — see `plan-0806-flake-recovery.md` (S1–S3) and the updated `#3`/`#3b`
> entries in `docs/regression-suite-health-review-2026-08-05.md`. F9, the
> diagnostic-capture-ordering bug this handoff flagged and left unfiled, is
> also now fixed (`gts-hroj`, that plan's S2). This file is kept as the raw
> session record of the investigation that led there; it is not maintained
> further and the review doc is the current source of truth.

# Handoff — gts-ir1f live verification + F9 discovery (2026-08-06)

Session picked up recommendation #3 from `docs/regression-suite-health-review-2026-08-05.md`
(the retrofit-sync-batching bead, `gts-ir1f`) at its documented next step, then
investigated an apparent escalation and ran a human-authorized retry. Both are
now fully written up in the review doc's `#3b` section and priority table row
#3 — this handoff is a compressed pointer + the raw findings, not a
replacement for that doc.

## State at start of session

`gts-ir1f` in progress. syncAll-batching scope fully done for all 4 files
(2 files batched, 2 confirmed N/A — zero `syncAll()` calls). One adjacent,
already-applied code change remained unverified: `test_import.py`'s
`scn_other` leadup doc converted from a real `_move_to_folder` + `scn.sync()`
+ `_seed_open_action` (2 live round trips) to the file's existing
`_seed_import_candidate` fixture-shortcut (0 round trips). 3 prior live
attempts (previous session) had each failed on a different GAS infra
symptom, none touching the changed code path.

## What this session did

1. **Attempt #4** (resume, per the prior session's own "re-run once"
   instruction): `pytest tests/test_import.py::test_import_flow_forward_sync -v`.
   Failed — but for the first time reached the actual AC1 assertion, not a
   setup barrier: `AssertionError: expected source docs visible, got []`.
   The failure-diagnostics screenshot (GTaskSheet-3tkf hook) showed
   `scn_target`'s Drive chrome offering `['Go to Docs home screen', 'Take out
   of trash']` — i.e. `scn_target` appeared to be in trash at that moment.
   This looked identical to attempt #3's symptom from the prior session
   (`open_sidebar` timeout on `scn_target`, same "Take out of trash" button),
   so it was initially escalated as a possible recurring lifecycle bug and
   reported to the user rather than retried again.

2. **User asked to investigate.** Root cause found by reading code, not by
   running anything further:
   - `test_import_flow_forward_sync`'s `finally:` block
     (`tests/test_import.py:561`) unconditionally calls `end_journey_session`
     (which trashes the doc — `src/AtddContracts.js`) for every session in
     `sessions`, on any exit path including an exception.
   - That `finally` runs as part of the test function's own exception
     unwinding, which completes **before** pytest's
     `pytest_runtest_makereport` hookwrapper (`tests/conftest.py:123`, the
     GTaskSheet-3tkf universal UI-failure-diagnostics hook) ever fires for
     the "call" phase.
   - So the diagnostics screenshot **always** shows every doc in `sessions`
     already trashed, for *any* assertion failure in this test — regardless
     of the real cause. It is not evidence of a recurring product bug; it's
     an artifact of hook-ordering vs. test-owned teardown.
   - Confirmed via grep that the same `sessions` list + `finally:
     end_journey_session` shape is used in `test_import.py`,
     `test_team_scope.py`, `test_journey.py`, `test_sync_all.py`, and
     `test_kkm7_batching.py` — so this is a structural gap in the
     diagnostics feature for this whole class of multi-doc live tests, not
     specific to one test.
   - **Filed as new finding F9** in
     `docs/regression-suite-health-review-2026-08-05.md` (full text there),
     including a fix-shape sketch (capture diagnostics before the test's own
     `finally` teardown runs — either a `pytest_runtest_call`-level hook, or
     each affected test's `finally` calling `capture_failure`-equivalent
     logic itself before trashing). **No bead filed per this session's
     explicit instruction not to create beads — do that next session if
     picking this up.**
   - With the "trash" clue debunked, attempts #3 (`open_sidebar` timeout)
     and #4 (empty `read_import_list()` result — note: `read_import_list()`
     already polls up to 15s for render, so this isn't a simple UI race)
     are two independent failures, not one recurring bug. Both still read as
     members of the pre-existing `/exec`-routing / Drive-lag flake class
     (F1/F7, `gts-pm72`), not proven conclusively.

3. **User authorized one more retry. Attempt #5**: failed even earlier than
   #1–#4 — the session-scoped `_reset_test_state` autouse fixture
   (`tests/conftest.py:223`) got an **HTTP 404 "Page Not Found"** from Drive
   on its very first `run_fixture` POST, before any doc in the test was even
   created. 44s total, zero test code reached. Same general class as
   attempt #1 from the prior session (non-JSON/echo response on the same
   fixture) — a different specific flavor of "the `/exec` endpoint routed
   somewhere wrong," but the same fixture, same failure point.

## Where this leaves things

- **5 live attempts across 2 sessions, 5 distinct symptoms, 0 passes.**
  Every failure is upstream of or unrelated to the `scn_other`/
  `_seed_import_candidate` code change under test. All 5 are consistent with
  the already-tracked F1/F7 `/exec`-routing flake class (`gts-pm72`) — this
  is not a pattern specific to `test_import_flow_forward_sync` or to this
  code change.
- **Per this project's Backstop rules, did not attempt a 6th live run**
  without another explicit human decision.
- `gts-ir1f` stays **open**, `regression=pending`. The `scn_other` change
  itself is still code-complete but **not live-verified** — it structurally
  mirrors an already-proven-live pattern (`test_import_access_filter`'s
  identical use of `_seed_import_candidate` for its own `scn_other`), but
  that is not the same as this specific test passing live post-change.
- Full-suite `pytest -x` is also still outstanding for `gts-ir1f` overall
  (unrelated to this specific sub-issue — it's the standing merge-gate
  requirement, not newly blocked by anything found this session).

## Recommended next actions (not yet decided by the user)

1. **Decide how to handle the still-unverified `scn_other` change**: retry
   again later (maybe conditions improve), accept it as
   structurally-verified-only and move on, or find another way to prove it
   live (e.g. run just that one assertion path in isolation with lighter
   setup).
2. **Consider F9 as a quick, well-scoped `[TST]` bead** — it's fully
   diagnosed (root cause, affected files, fix shape) and independent of
   `gts-ir1f`'s own scope. Not filed this session per explicit instruction.
3. **Consider whether 5/5 attempts hitting the F1/F7 flake class is itself
   grounds to re-prioritize that class** — specifically, whether
   `gts-pm72`'s GAS-side retry pattern (currently only wraps
   `SyncManager`'s Drive metadata calls) should be extended to cover the
   WebApp's own `/exec` routing/entry point, since 3 of the 5 failures this
   session-pair landed there (non-JSON echo, Drive 404, and this session's
   404-on-`reset_test_state`).
4. Per the review doc's own "Next-run pointer" (still current), if the
   `scn_other` question stays undecided, the next unblocked item in
   priority order is **#4**: run `scripts/check_coverage.py` to refresh the
   stale (2026-06-11) AC/entry-point coverage baseline and wire it into
   `pnpm run test:full` (or a lighter `test:coverage` script).

## Source documents

- `docs/regression-suite-health-review-2026-08-05.md` — full detail, `#3b`
  section and priority table row #3 have the complete, current record of
  everything in this handoff (this handoff is a summary of that content,
  not a separate source of truth — if they ever disagree, the review doc
  wins, it was updated last).
- `gts-ir1f` bd notes — same findings recorded there in bd for continuity.
- Attempt logs (not preserved past session end, paths recorded for
  reference only):
  - `/tmp/claude-1000/-home-stuar-proj-GActionSheet/e0918cc8-9c38-4dc2-a640-cfc7b087dc79/scratchpad/ir1f-import-flow-resume.log`
    (attempt #4)
  - `/tmp/claude-1000/-home-stuar-proj-GActionSheet/e0918cc8-9c38-4dc2-a640-cfc7b087dc79/scratchpad/ir1f-import-flow-attempt5.log`
    (attempt #5)
