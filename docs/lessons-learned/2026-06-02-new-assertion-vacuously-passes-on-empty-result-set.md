# LL: New test assertion silently passes because the set it checks is empty

Date: 2026-06-02
Domain: testing

## Observation
During 6ov.8, `verify_doc_chip_integrity` was wired into the `uc_b_state` module fixture
(now deleted). It returned `[]` (no violations) on every run. This appeared to confirm chip
integrity was passing. The actual cause: the `verify_chip_integrity` GAS route walks AI-N:
paragraphs and returns a violation list — but when `sync.scanned count:0` (no items detected
by the scanner), no chips are ever written, so there are zero AI-N: paragraphs, and the
violation list is vacuously empty. The chip integrity check was "green" because there was
nothing to check, not because the chips were correct. The underlying test failure
(`len(rows)==0`) was unrelated and surfaced separately; without it, the chip integrity
assertion would have continued to provide false assurance.

The same gap exists in the current `ScenarioSession.verify_consistency()`: if `scn.sync()`
produces zero detected items (e.g. fixture helpers use the wrong format), `verify_chip_integrity`
returns `[]` and `verify_consistency` passes. In test_journey.py this is masked by
`verify_all_expectations(a)` which fails if each specific action is not found — but that
defense is implicit in the journey test structure, not a stated convention, and would be absent
in any test that calls `verify_consistency()` without preceding per-action expectations.

## Why Chain

### Branch A — The check itself is vacuously true on an empty set

Why 1 — `verify_chip_integrity` returns `[]` when there are 0 AI-N: paragraphs.
Why 2 — The check walks the set and reports violations; an empty set has no violations.
Why 3 — No minimum-count precondition was added ("assert there are at least N AI-N: paragraphs
         before checking their properties").
Why 4 — When designing the check, the assumption was that a preceding sync had written chips;
         no defensive assertion was added to verify that assumption holds.
Why 5 — No convention requires that a property assertion over a set also assert the set is non-empty.

Root cause A: `verify_chip_integrity` can return vacuous green when the sync that should have
written chips produced no output. No minimum-count precondition guards against this.

### Branch B — Adding a new assertion does not require proving it can fail

Why 1 — `verify_doc_chip_integrity` was wired into UC-B tests and passed; no further validation
         was done.
Why 2 — The standard for adding a new assertion to the test suite is "does it pass?" not
         "does it fail when the thing it checks is broken?"
Why 3 — There is no convention requiring that a new assertion be demonstrated to fail (a
         "proof of effectiveness" step) before it is accepted into the suite.
Why 4 — The red-phase / green-phase ATDD cycle applies to functional tests (write failing test,
         then write code to make it pass) but not to quality/integrity checks added to existing
         passing tests; those are treated as additive and assumed effective.

Root cause B: No process requires proving that a new quality/integrity assertion would fail if
the thing it checks is absent or broken. Assertions can be added and silently provide no coverage.

## Residual gap in current design

`ScenarioSession.verify_consistency()` now calls `verify_chip_integrity`. The journey test
protects against vacuous green via `verify_all_expectations(a)` per action — but this is not
a stated requirement; it is implicit in the journey test's structure. Any future test that
calls `verify_consistency()` without preceding per-action expectations is exposed to Branch A.

The `ai.as_text()` method already produces `AI:` or `AI-N:` format (confirmed in `scn/ai.py`),
so tests using `scn.append_paragraph(a.as_text())` will always produce scanner-compatible items.
The risk is narrowed to: (a) tests that use fixture helpers rather than `scn.append_paragraph`,
or (b) tests where the fixture helper format drifts from `ai.as_text()` format.

## Relation to existing LLs
`2026-05-25-test-mutation-verification-vs-state-reconciliation.md` — that LL addresses whether
tests verify full state vs. mutations only. This LL is about whether a check is triggered at all:
a check that passes vacuously is worse than a missing check because it provides false confidence.

## Initial Candidates

Branch A (fix the check):
  f: bd issue — add minimum-count assertion to `verify_chip_integrity` GAS handler: if the doc
     has AI: or AI-N: text in it (i.e. the scanner ran) but zero chips were written, return a
     violation rather than []; or return a metadata field `checked_count` so the caller can assert
  f: bd issue — add `ScenarioSession.verify_consistency()` guard: after calling verify_chip_integrity,
     assert `chip["checked_count"] > 0` if any actions were previously added via `append_paragraph`
     (the session tracks how many actions were added, so it can require at least that many chips)

Branch B (fix the process):
  c: update implementation-gate or test-functional skill — add step: "for any new quality/integrity
     assertion added to a passing test (not a red-phase test), prove effectiveness: verify the
     assertion fails when the behavior it checks is absent; document the failure mode"
  b: add to project CLAUDE.md testing strategy — "a new integrity/quality assertion wired into an
     existing test must be accompanied by a demonstration that it fails when the condition is violated;
     a new assertion that only shows green is unverified"

Shared (improve the journey test convention):
  b: add to project CLAUDE.md — "every scenario test that calls verify_consistency() must also call
     verify_all_expectations(a) for at least one action; this prevents verify_consistency from passing
     vacuously if the preceding sync produced no output"
