# ADR-0003: TDD Lifecycle Labels for Issue Tracking

Status: Proposed
Date: 2026-05-20

## Context
Issues implementing tests and the corresponding implementation code are distinct lifecycle phases in TDD. Without explicit labels, it is ambiguous whether an open issue represents unfinished test authoring, unverified implementation, or a confirmed failing test awaiting a fix. This ambiguity makes it hard to read project state from `bd ready` or `bd list`.

## Decision
Use two labels on bd issues to mark TDD lifecycle phase:

**`red-phase`** — test implementation work. Applied to issues whose job is to make a test executable and runnable against the implementation. A red-phase issue closes when the test can actually run (regardless of whether it passes or fails). The test result determines next steps.

**`green-phase`** — implementation work. Applied to issues whose job is to make a specific failing test pass. Created reactively — only when a red-phase test is confirmed failing. A green-phase issue closes when the target test passes.

**Lifecycle rule:**
1. Wire test → confirm it runs → close the red-phase issue
2. If the test passes: no green-phase issue is created
3. If the test fails: create a `green-phase` issue scoped to the specific failing assertion; close it when the test passes

Green-phase issues are never created preemptively. They are discovered by running red-phase tests.

The `run-tests` checkpoint (e.g., the molecule `run-tests` step) sits between the two phases. It carries neither label. It is the gate that surfaces which green-phase issues, if any, need to be created.

## Consequences
- `bdls` shows all open issues with their labels inline — red-phase and green-phase issues are visible at a glance without a separate query
- When all `red-phase` issues for a feature are closed, the implementation is either verified correct (no green-phase issues created) or all failures are tracked as explicit `green-phase` issues
- Requires discipline at issue-creation time to apply the correct label
