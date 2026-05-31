# ADR-0006: ATDD Lifecycle — Twin-Ticket Workflow, Issue Prefixes, and Named Clone Isolation

Status: Accepted
Date: 2026-05-25

## Context

Several recurring friction points emerged across the first two UC implementations:

- No consistent way to tell from `bdls` whether an open issue is implementation work, test work, or infrastructure — labels are not surfaced in all report views.
- GAS implementation and Python test authoring were done sequentially by the same person, meaning tests were written with knowledge of the implementation. This is a known source of bias: tests verify the code that was written rather than the AC that was intended.
- The test fixture uses a single shared `TEST_DOC_ID` reset by GAS mutation. One pre-existing failing test (`uc2_new_table_row`) is attributable to fixture state left over from a prior run. Parallel CI runs would cause systematic collisions.
- The interface between GAS and the Python test harness (log tag, output schema) was agreed informally during implementation. This created rework when assumptions differed.

ADR-0003 addressed part of this with red-phase/green-phase labels, but those labels are reactive — green-phase issues are only created after a red-phase test confirms failure. That model does not enforce parallel execution or prevent a single person from writing both tracks with shared context.

## Decision

Adopt the ATDD lifecycle defined in `docs/atdd/atdd-lifecycle.md`. The specific commitments are:

**1. Issue title prefixes.**
All new issues use `[IMP]`, `[TST]`, `[FIX]`, or `[INF]` as the first token of the title. The prefix lives in the title, not only as a tag, so it is visible in every bd report format regardless of tag display. Existing open issues are not retroactively renamed.

**2. Twin-ticket pairing with no shared context.**
Every new feature AC spawns an `[IMP]` issue and a `[TST]` issue created simultaneously. The two are worked in parallel. The `[TST]` owner must not read GAS implementation code; the `[IMP]` owner must not read test assertions. The contract (see below) is the only shared artifact. Neither ticket merges until both are green.

This supersedes the reactive green-phase creation model in ADR-0003. The label convention from ADR-0003 is retired; the prefix system replaces it.

**3. Pre-code contract.**
Before either track starts coding, both owners document in the issue (or a shared note): (a) the GAS entry-point function signature, (b) the exact log tag GAS emits on completion, (c) the output schema the Python test will assert against (XLSX column names and order, or DOCX XML structure). No coding begins until the contract is written.

**4. Named clone fixture isolation.**
Each test run clones the master template Google Drive file rather than mutating a shared static fixture. Clone naming format: `{project}-Test-{scenario-slug}-{YYYYMMDD}-{4-char-hex}` (e.g., `GActionSheet-Test-UC-B-doc-wins-20260525-c12e`). The clone ID is passed to GAS as a parameter. Clones are destroyed at teardown. Implementation tracked in GTaskSheet-cby.

## Consequences

**Positive:**
- `[IMP]`/`[TST]`/`[FIX]`/`[INF]` prefix gives immediate visual classification in any `bdls` output without requiring tag display support.
- Twin-ticket enforces test-first at the process level rather than relying on individual discipline. A failing `[TST]` issue is the expected and correct starting state; the `[IMP]` issue closes it.
- No-shared-context rule means `[TST]` assertions verify the AC, not the incidental implementation — the most common source of tests that pass while the user story is still broken.
- Pre-code contract surfaces interface disagreements before either track invests coding time.
- Named clone isolation eliminates fixture state contamination between runs and unblocks parallel CI.

**Negative / tradeoffs:**
- Twin-ticket adds overhead for very small changes. `[FIX]` issues are single-ticket by convention; only `[IMP]` features require a companion `[TST]`.
- Pre-code contract requires a synchronization point before parallel work begins — a short but real delay when only one person is working.
- Named clone adds setup/teardown complexity to conftest and creates Drive file churn (mitigated by teardown cleanup).
- No-shared-context is a discipline constraint, not a mechanical one. It relies on the `[TST]` owner not reading the `[IMP]` branch before their assertions are written.
- Existing open issues lack prefixes, creating visual inconsistency in `bdls` during the transition period.
