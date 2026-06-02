# LL: Implementation change silently invalidated test infrastructure with no merge-time gate

Date: 2026-06-02
Domain: testing | process

## Observation
`d37af7d` (6ov.7 POC squash) rewrote `_scanFloatingActions` in `SyncManager.js` from chip-led
detection (first child is a PERSON element) to AI-N: token detection (paragraph text starts with
`AI:` or `AI-N:`). The fixture helpers `_tfInsertPersonChipListItem` and `_tfAppendPersonChipListItem`
in `TestFixtures.js` create items the scanner reads; they were not updated and continued inserting
`[PERSON chip][action text]` without an `AI:` placeholder. All seven old-model test files were
silently broken: every `syncDocument` invocation produced `sync.scanned count:0`, upserted 0 rows,
and assertions either failed (`len==0`) or passed vacuously (chip integrity on an empty set).

The regression persisted undetected for one full sprint. It was only caught when 6ov.8 ran the tests.

The scanner is not unique. Any change to a core mechanism can silently invalidate test infrastructure
without touching production code or failing compilation. Other examples in this codebase:
- ActionSheet column layout change → breaks column-index assertions in sheet_inspect.py
- globalId format change → breaks regex patterns in test_b7_write_routes.py
- GasLogger tag rename → breaks fixture polling in fixture_invoke.py
- WebApp route contract change → breaks _post_route callers in session tests

In all cases, the test infrastructure has no type system or imports to enforce compatibility —
it can drift silently from the production code it exercises.

## Why Chain

Why 1 — The scanner change broke fixture helpers that create items the scanner reads.
Why 2 — When 6ov.7 closed, the test suite was not run; the broken helpers were not discovered.
Why 3 — The ATDD lifecycle has no gate at [IMP] close (or at merge, when working on master) that
         requires: (a) the full regression suite to pass, and (b) explicit review of whether the
         change affects any code that existing tests depend on (fixture format, detection behavior,
         route contracts, column layout, log tag names).
Why 4 — Rapid iteration during implementation is intentionally ungated — the lifecycle is designed
         to allow fast commits without constant test runs. The missing gate is specifically at the
         transition point: merge to master / [IMP] close.
Why 5 — No checklist item at that transition asks "does this change affect any mechanism that
         test infrastructure (fixtures, helpers, assertion code, polling patterns) depends on?"

Root cause: There is no gate at the merge / [IMP]-close transition requiring (1) regression suite
green and (2) explicit review of test-infrastructure compatibility. Rapid iteration is correctly
unconstrained; the gap is the absence of a quality gate at the point of declaring the work done.

## Note on iteration vs. gate discipline
The user explicitly does not want to preclude rapid implementation iterations. This LL is not
proposing a gate on every commit. The gate belongs at the merge/[IMP]-close boundary:

- During iteration on a feature branch or rapid-cycle commits: unconstrained
- Before [IMP] is closed / before merge to master: run pytest -x; ask "does this change affect
  any code that existing tests depend on?"

This maps onto the existing merge-gate skill as the natural enforcement point.

## Relation to existing LLs
`2026-05-27-stub-entry-point-wired-to-trigger-without-end-to-end-test.md` — that LL addresses
entry-point coverage (production code). This LL addresses test-infrastructure compatibility
(fixture helpers, assertion helpers) — a different class of artifact with no compilation checks.

`2026-05-25-test-mutation-verification-vs-state-reconciliation.md` — covers test design quality
(mutation vs. reconciliation). This LL is about whether tests run at all after a mechanism change.

## Initial Candidates

c: update merge-gate skill — add an explicit step: "does this change affect any mechanism that
   test infrastructure depends on? Enumerate: (1) floating-action detection format (scanner /
   ai.as_text() / fixture helpers must stay aligned), (2) route/contract shape (WebApp routes,
   response field names), (3) sheet structure (column layout, header names), (4) log tag format
   (fixture polling). If yes: confirm test suite passes and the affected infrastructure was updated."

c: update implementation-gate skill — add to the [IMP]-close checklist: "run pytest -x against
   the TEST deployment; regression suite must be green before this issue is closed; if no TST
   twin exists, the existing suite is the gate"

b: add to project CLAUDE.md — "before closing any [IMP] issue or merging to master: run pytest -x;
   the full existing regression suite must pass regardless of whether a [TST] twin was written for
   this IMP; a regression in pre-existing tests blocks [IMP] closure"

d: add to merge-gate template (if one exists) — checklist item: "test infrastructure compatibility:
   list any changed mechanisms (scanner, routes, sheet columns, log tags) and confirm fixture helpers,
   assertion helpers, and polling code remain compatible; run pytest -x"

Preferred ordering: c (merge-gate skill update) is most durable — fires automatically at the right
transition point without requiring recall; b (CLAUDE.md) is a backstop for sessions without a merge gate.
