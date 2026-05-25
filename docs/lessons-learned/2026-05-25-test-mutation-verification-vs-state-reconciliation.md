# LL: Test suite verifies mutations but not full-state reconciliation

Date: 2026-05-25
Domain: testing

## Observation

UC-B test suite (`tests/test_uc_b.py`) validates that specific mutations propagate correctly between floating actions and ActionSheet rows (delta-proof pattern: inject mutation → run sync → assert mutation visible in destination), but does NOT verify comprehensive state consistency. Tests parse actual DOCX and XLSX files but only check specific variant rows that were mutated. They never verify: "do ALL floating actions, ALL ActionSheet rows, and (for UC-C) ALL tracker table rows maintain complete data consistency after sync?" Consistency includes: assignee email/name, action text, status, NamedRangeId, ID, Assigned Date, Last Modified, and document name (the display text of the ActionSheet Document hyperlink, as returned by doc.getName()) — not just text and status. Test helpers exist (`floating_actions()`, `load_sheet()`, `rows_for_doc()`) but are used only for mutation validation, not full-state consistency verification. Same pattern observed in `test_uc_a` tests and Playwright smoke tests — mutation-focused is the suite default. Discovered during test strategy review for UC-C/D implementation (2026-05-25). Additionally, review of `_handleSyncActionRows` in `src/WebApp.js` reveals that the Document column HYPERLINK display text (the document name, from doc.getName()) is only written on new row insert; subsequent syncs never refresh it — so a document rename produces permanently stale name display in the ActionSheet. Note: the variable `docTitle` in WebApp.js and SyncManager.js is a misnomer; should be `docName` to match the Apps Script getName() API. This is both a test gap (not verified) and an implementation defect (not refreshed).

## Why Chain

Why 1 — UC-B tests check "did Variant 1 status change from Open to Done?" but not "do all N floating actions match all N ActionSheet rows for that doc?"
- Because the test design applied a delta-proof pattern: inject mutations → verify they appear in destination.

Why 2 — Delta-proof pattern was applied to an e2e sync test instead of a reconciliation test.
- Because AC language in `docs/CONTEXT.md` §UC-B is mutation-scoped: "A sheet edit to Status, Action, or Assignee **reaches** the floating action paragraph after Sync" (emphasis on the mutation reaching the destination).

Why 3 — AC language is mutation-scoped even though UC-B's postcondition says "Both authoritative sides match."
- Because the postcondition is stated informally in prose above the AC bullets, but the AC bullets themselves are mutation-specific ("Var 1 status changed", "Var 2 action text changed"). The test author operationalized the AC bullets (the operationalized scope) rather than the postcondition (the intended scope).

Why 4 — The postcondition-vs-bullets split exists in the AC structure.
- Because AC writing convention in `doc-framework/` does not require that postconditions be expressed as verifiable reconciliation invariants. Postconditions can be informal prose; AC bullets are the only operationalized part.

Root cause: Acceptance criteria language allows postconditions to be informal and mutation-scoped AC bullets, so test design naturally inherits the mutation-scoped interpretation. No checklist item or gate requires that postconditions be expressed as verifiable state invariants that would drive test structure toward reconciliation-based assertions.

## Why Chain (branched variant)

### Branch A — AC Writing Convention Gap
Why 1 — AC postconditions in `docs/CONTEXT.md` are informal prose ("Both sides match") rather than operationalized invariants ("every floating action and its ActionSheet row agree on action text, status, assignee").
- Because `doc-standard.md` and `doc-framework/` do not require postconditions to be expressed as falsifiable state invariants.

Root cause A: AC authoring convention does not require that postconditions be operationalized as reconciliation invariants; this gap cascades into test design.

### Branch B — Test Design Convention Gap
Why 1 — Test design applied delta-proof (mutation verification) to a state-convergence feature (bidirectional sync).
- Because there is no test-design gate or checklist that distinguishes mutation-verification tests from reconciliation-verification tests, and no precedent in the codebase for full-state reconciliation loops.

Why 2 — The test helpers for full-state parsing exist (`floating_actions()`, `load_sheet()`) but were never used in a reconciliation loop.
- Because reconciliation was not part of the test-design pattern; once the initial tests passed on mutation verification, there was no prompt to consider reconciliation.

Root cause B: Test design lacks a convention distinguishing "did this mutation apply?" from "is the system in a valid state?" When AC language defaults to mutation-scope, test design has no reason to build reconciliation checks.

## Initial Candidates

- a: Add postcondition-as-invariant rule to `doc-standard.md` so AC for sync/state-mutation features must define consistency invariants (all fields across all three storage locations: floating action, ActionSheet, tracker table) in the postcondition.
- b: Update project `CLAUDE.md` with test-design discipline: every UC that calls sync or mutates state must include a full-data consistency phase in addition to mutation verification. Consistency includes: assignee (email + name), action text, status, NamedRangeId, ID, Assigned Date, Last Modified.
- c: Create or update gate skill to check that test AC operationalizes consistency invariants and that test code includes full-data reconciliation assertions (not just text/status) before marking test task complete.
- d: Add to merge-gate or test-design-gate template: "For tests touching state mutation (sync, archive, reconciliation), verify that tests check all-field consistency (not just text/status) across all storage locations (floating action, ActionSheet, tracker table) with no orphaned rows."
- e: No lever here — the fix is structural, not a memory.
- f: Create implementation issues to retrofit UC-B, UC-A tests with full-data consistency verification; create test-design gate (GTaskSheet-qea) blocking UC-C/D until reconciliation strategy (including all-field consistency) is approved.

[Developed fully at resolve phase]
