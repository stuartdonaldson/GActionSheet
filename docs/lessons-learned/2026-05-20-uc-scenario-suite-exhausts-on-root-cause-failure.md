# LL: UC scenario suite exhausts all slow scenarios despite a root-cause failure in the first

Date: 2026-05-20
Domain: testing

## Observation
During green-phase implementation of GTaskSheet-709/oln/35b, the full test suite was run.
`test_uc_scenarios.py` executed all 8 end-to-end GAS scenarios sequentially.
uc1 failed with `action=''` (root cause: BARE_EMAIL_RE `\s*` eating the field separator).
All remaining scenarios also failed — including uc3_sheet_wins and uc3_doc_wins which each
spent 60 s polling for a GAS log entry that never came.
Total wall time: ~6 minutes for a failure that a 3-second parser unit test would have surfaced.
Caught by: human review of test output after the run completed.

## Why Chain

Branch A — Suite runs to completion despite early cascade failure
  Why 1 — pytest ran all 8 parametrized cases with no fail-fast constraint
  Why 2 — No `-x` flag or suite-level guard was added; each scenario was treated as independent
  Why 3 — The causal dependency (root parser bug → all scenarios fail) was not modelled at design time
  Root cause A: Test suite design assumed scenario independence; no ordering or fail-fast constraint
  was encoded to detect a root-cause failure and short-circuit the downstream 60s-timeout cases.

Branch B — Root cause only detectable at expensive integration level
  Why 1 — The `BARE_EMAIL_RE \s*` bug (action always '') was only caught at UC scenario level
  Why 2 — No unit test covered the `rest` return value of `_parseAssigneeFromText`
  Why 3 — Red-phase test work targeted user-visible outcomes (email parsed, action present)
           but omitted a focused assertion on what `rest` contains after token extraction
  Root cause B: `_parseAssigneeFromText` had no unit test for its `rest` output, so a structural
  parsing gap could only surface at integration level where the symptom multiplies across scenarios.

## Initial Candidates

Branch A:
  f: bd issue — add `pytest -x` (fail-fast) as the default invocation in OPERATIONS.md / test runner docs
  b: CLAUDE.md rule — when running UC scenario tests, always pass -x to stop on first failure
  c: update test-functional skill — note that suites with expensive integration tests should
     encode fail-fast or use a smoke-test pre-check before the full matrix

Branch B:
  c: update test-functional skill — add guidance: for parser/transformer modules, always include
     a unit test for intermediate outputs (e.g. `rest`, parsed sub-fields) not just final results
  f: bd issue — add `_parseAssigneeFromText` unit test covering `rest` value to test_floating_action_parser.py

## Chosen (2026-05-20, Branch A — applied this session)

Selected lever: b (OPERATIONS.md §Running Tests) + e (bd memory `pytest-fail-fast-always-run-pytest-with-x`)
Rationale: OPERATIONS.md makes the `-x` flag the documented default for all pytest invocations;
bd memory ensures the AI applies it in future sessions without the user repeating the instruction.
Within-test assertion accumulation (multiple defects per test) is explicitly preserved — `-x` only
blocks starting the *next* test.
Branch B left open — `_parseAssigneeFromText` unit test for `rest` value is a bd issue candidate.
