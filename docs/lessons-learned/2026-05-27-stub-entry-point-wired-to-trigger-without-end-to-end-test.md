# LL: stub entry point wired to trigger without end-to-end test

Date: 2026-05-27
Domain: testing

## Observation
`syncAll()` in `SyncManager.js` was a stub (only logged; returned immediately) from the first commit
(`feat(menu+stubs)`) through to 2026-05-27. It was wired to the "Action Sync → Sync" menu item and
the 30-minute time-based trigger. When Sync Status was shipped (GTaskSheet-ly5, commit de00336),
`_markDocNotFound` was correctly implemented inside `syncDocument`, and `test_sync_status_doc_not_found`
in `test_uc_c.py` verified that calling `syncDocument(fakeDocId)` stamped `'Doc Not Found'` on the
ActionSheet row. The test passed. `syncAll()` remained a stub. User reported in production that a
deleted document's rows showed no status change after running Sync — caught manually, not by tests.

## Why Chain
Why 1 — `syncAll()` was a stub; every Sync-menu and trigger invocation returned immediately
Why 2 — No test exercised `syncAll()` end-to-end; the existing test called `syncDocument` directly, bypassing the entry point
Why 3 — When writing the [TST] for Sync Status, the question "what production entry point calls this code path?" was not asked
Why 4 — No rule requires that the regression suite exercises every state-modifying entry point at least once — testing the underlying mechanism in isolation is treated as sufficient coverage
Root cause: No constraint requires the regression suite to exercise every state-modifying entry point (menu items, time-based triggers, sidebar buttons) at least once with observable state verification — coverage of the mechanism it delegates to is treated as equivalent.

## Refined framing (post-capture discussion)
The fix is not "each menu item needs its own standalone test." The requirement is coverage:
every entry point that modifies system state must be exercised at some point in the full regression
suite, with the resulting state verified. The exercise and verification do not need to be
sequential or in a dedicated test case — they can be embedded in any scenario that reaches that
entry point as part of normal flow. The gap here was that `syncAll()` was never the call-site
in any test; `syncDocument` was always called directly.

## Initial Candidates

### Path A — ATDD followed (pre-code)
c: add check to implementation-gate skill — at [TST] authoring time, list all state-modifying
   entry points for the feature (menu items, triggers, sidebar actions); confirm each is exercised
   at least once somewhere in the suite with state verification; does not require a dedicated test
d: add to [TST] issue template — checklist item: "entry point coverage: list all menu/trigger/
   button entry points for this feature; each appears as call-site in ≥1 test scenario"

### Path B — retroactive (bug report, AC refinement, post-hoc behaviour identification)
b: add to project CLAUDE.md testing strategy section — "when a bug or user-reported failure
   identifies a missing test, the fix must be accompanied by a [TST] issue that closes the
   coverage gap; the [TST] issue audits the full entry-point class, not only the specific
   failure — enumerate all state-modifying entry points in the same subsystem and verify each
   appears as a call-site in ≥1 test scenario; this applies regardless of whether ATDD was
   followed at development time"

### Path C — code review (catches gaps regardless of how code was developed)
c: add check to code-review skill — for any PR or change set touching a state-modifying entry
   point (menu item, trigger, sidebar action), verify: (a) the entry point appears as a call-site
   in ≥1 test scenario in the suite; (b) if no coverage exists, a [TST] issue is open before
   the change is merged; this check applies regardless of whether ATDD was followed and regardless
   of whether the entry point was introduced by this change or pre-existed it
   Note: for important features with no test coverage at all, code review is the only enforcement
   point that currently fires — Path A (pre-code) and Path B (bug-triggered) both require a
   prior event to trigger; code review fires unconditionally on every change

### Shared constraint (all paths)
b: project CLAUDE.md testing strategy — "the regression suite must exercise every state-modifying
   entry point (menu items, time-based triggers, sidebar buttons) at least once with observable
   state verification; the entry point itself must be the call-site, not only a mechanism it
   delegates to; sequential or standalone coverage is not required"

## Levers under test (2026-05-27)
Partial implementation applied to this project to test effectiveness before full resolve:
- Path A (pre-code): Step 5 "Entry point coverage check" added to `.claude/skills/implementation-gate/SKILL.md`
  (project-local override of global skill; v1.1 → v1.2)
- Path B (retroactive): "Regression coverage — retroactive path" and "Entry point coverage invariant"
  rules added to project `CLAUDE.md` (Testing Strategy section)
- Path C (code review): `.claude/skills/code-review/SKILL.md` created as new project-local skill
  with entry point inventory and coverage check in procedure Steps 3–4
- Shared CLAUDE.md rule: "Entry point coverage invariant" added covering all paths

Not yet resolved — staging file remains open. Full resolve (scoring options, selecting lever tier,
archiving to resolved/) deferred to next gate/phase transition. These interim levers are under
observation; effectiveness will be assessed against future incidents.
