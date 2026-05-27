---
name: code-review
description: >-
  Code review gate checking correctness, regression coverage, and entry point
  coverage for any change set. Use before merging a PR or marking a feature
  complete. Auto-triggers on: "review this", "code review", "review the
  changes", "pre-merge check", "ready to merge", "review PR". Also checks
  regression coverage for state-modifying entry points regardless of whether
  ATDD was followed — covers legacy code, retroactive gap identification, and
  features shipped before the ATDD lifecycle was adopted.
metadata:
  category: process
  version: "1.0"
  status: documented
  validation: untested
  priority: high
  created: "2026-05-27"
  last_updated: "2026-05-27"
  depends_on: []
  conflicts_with: []
  related_skills: [implementation-gate, lessons-learned]
---

# Code Review

Review gate that checks correctness, regression coverage, and entry point coverage before any change is merged.

**Goal:** Code review is the safety net for coverage gaps that escaped ATDD (Path A) and bug-triggered
remediation (Path B). It fires unconditionally on every change — it does not require a prior failure
event, an ATDD lifecycle, or a [TST] issue to trigger. Its unique role is surfacing gaps in important
features that have no coverage for any reason: shipped before ATDD was adopted, AC refined after tests
were written, or behavior identified late that was never in AC.

## When to Use

**Explicit:** `/code-review`, "code review", "review this", "review the changes", "pre-merge check"
**Auto-trigger:**
- keywords: [ready to merge, review PR, review the code, pre-merge, code review]
- context: any change set is complete and ready to merge or commit
- context: a feature is declared done and a test run has passed
**Gate:** Before `git push` on a feature branch; before closing a [IMP] issue
**Not needed:** Read-only sessions; documentation-only changes with no logic

## Addresses

- State-modifying entry point with no test call-site — mechanism tested in isolation, trigger never
  exercised; caught only by user in production (syncAll, 2026-05-27)
- Important features shipped before ATDD lifecycle adopted — test suite has no coverage for entire
  subsystems; only code review fires unconditionally to surface the gap
- AC refined after tests written — new behavior added to implementation, test suite not updated

## Input

**Type:** Change set or feature description
**Format:** Branch diff, PR description, or list of modified files
**Required:** List of files changed or a description of what was implemented
**Optional:** bd issue IDs, existing test files
**Minimum:** "These files were changed: X, Y, Z"

## Procedure

1. **Diff inventory** → list all files changed → group by: implementation files, test files,
   config/infra | Fail: if no diff available, ask for file list before continuing

2. **Correctness scan** → for each implementation file changed, verify:
   - Logic matches AC (if AC exists)
   - Error paths are handled (not silently swallowed)
   - No obvious off-by-one, null-reference, or type coercion issues
   | Note findings; do not block on style — block only on correctness

3. **Entry point inventory** → scan all changed and related files for state-modifying entry points:
   menu item handlers, time-based trigger functions, onEdit/onOpen handlers, sidebar button actions,
   HTTP route handlers → list every entry point found, including pre-existing ones in changed files
   | Fail: if a file contains a menu registration or trigger setup and no entry point is listed,
   re-scan — registration without a handler list is incomplete

4. **Entry point coverage check** → for each entry point in the inventory:
   a. Search the test suite for a scenario that calls this function directly as the entry point
      (not only a function it delegates to)
   b. Mark: ✓ covered | ✗ no test call-site | ~ pre-existing gap (entry point predates this change)
   | Fail: if any entry point introduced or modified by this change is ✗, block merge and require
   a [TST] issue before proceeding | Pre-existing gaps (~) should be noted but do not block merge
   — they are candidates for a [TST] issue, not a blocker on the current change

5. **Regression coverage scan** → for subsystems touched by this change, ask:
   - Is there any important behavior in this subsystem with no test coverage at all?
   - Would a regression in this subsystem be caught by the current test suite?
   | If a significant coverage gap is found: create a [TST] issue; note it in the review; do not
   block merge unless the gap is in code directly modified by this change

6. **Bug-fix coverage rule** → if this change is a bug fix ([FIX] issue):
   - Confirm a regression test for this specific failure exists or is in a paired [TST] issue
   - Enumerate the entry-point class for the affected subsystem (all entry points in the same
     functional area) and verify each has a test call-site; gaps → [TST] issues
   | Fail: a [FIX] with no regression test is incomplete — require [TST] issue before close

7. **Summary** → produce a review summary:
   ```
   Files changed: N
   Entry points inventoried: [list]
   Coverage: ✓ N covered | ✗ N blocked | ~ N pre-existing gaps
   Correctness findings: [list or "none"]
   [TST] issues required: [list or "none"]
   Verdict: PASS | BLOCK
   ```
   BLOCK if: any ✗ entry point; any correctness finding not yet addressed; [FIX] with no regression test
   PASS with notes if: only ~ pre-existing gaps; only style findings

## Success Criteria

- [ ] All changed files inventoried (verify: file list matches `git diff --name-only`)
- [ ] Every state-modifying entry point in changed files listed by name (verify: list shown)
- [ ] Each entry point marked ✓ / ✗ / ~ with test file and scenario name for ✓ entries
- [ ] No ✗ entry points on changed or new code without a blocking [TST] issue
- [ ] Bug fixes have a regression test or a [TST] issue for one
- [ ] Summary produced with explicit PASS or BLOCK verdict

## Examples

### Failure — Mechanism tested, entry point skipped
**Input:** PR adds Sync Status column; test_sync_status_doc_not_found calls syncDocument(fakeDocId)
**Expected (with skill):** Step 3 lists syncAll, time-based trigger, menuSync as entry points;
  Step 4 finds no test calls syncAll; verdict BLOCK; [TST] issue required
**Actual (without skill):** No code review run; syncAll stub shipped; user caught in production (2026-05-27)

### Success — Pre-existing gap noted, not blocked
**Input:** PR fixes status patching in sidebarSetStatus; archive subsystem has no tests
**Expected:** Step 5 notes archive coverage gap as ~; creates [TST] issue for archive regression;
  does not block current PR; verdict PASS with notes

### Success — Bug fix with regression test
**Input:** [FIX] for syncAll stub; implementation adds doc enumeration loop
**Expected:** Step 6 confirms test_sync_all_marks_deleted_doc_not_found exists in suite;
  entry point coverage: syncAll ✓; verdict PASS

## Anti-Patterns

**Pattern:** Review skipped because tests pass
**Symptom:** All tests green → assume coverage is complete → skip entry point inventory
**Prevented by:** Step 3 — entry point inventory is mandatory regardless of test results;
  a test suite can be entirely green while missing call-sites for entire entry point classes
**Found:** syncAll stub — all sync_status tests passed; syncAll never called; no review ran

**Pattern:** Only changed files reviewed for coverage
**Symptom:** Reviewer checks new test file exists for new code; does not scan pre-existing entry
  points in changed files for coverage gaps
**Prevented by:** Step 3 instruction — "including pre-existing ones in changed files"
**Found:** Would have caught syncAll in the file changed by the Sync Status feature commit
