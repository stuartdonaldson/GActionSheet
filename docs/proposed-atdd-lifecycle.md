# ATDD Testing & Lifecycle Strategy

This document has two layers:

- **Universal principles** — apply to any project regardless of language or platform.
- **GAS/Python implementation notes** — show how each principle is expressed in a Google Apps Script + Python test stack. Teams on a different stack should translate these mechanics, not copy them.

---

## Part 1: Process & Visibility Framework

### 1. Work Item Typology

Every technical task must use one of the following prefixes in its title. The prefix belongs in the title — not only as a tag — because not all issue tracker views surface tags, and the prefix must be visible in any report format.

* `[IMP]`: **Implementation Work.** Writing the core business logic, UI, or platform-specific functions.
* `[TST]`: **Verification & Testing Work.** Writing integration test suites, fixtures, and assertions.
* `[FIX]`: **Defect / Bug Resolution.** Fixing a regression or failing criterion caught outside the active development cycle.
* `[INF]`: **Infrastructure & CI/CD.** Deployment tooling, service account permissions, pipeline configuration.

### 2. The Twin-Ticket Lifecycle

For every user-facing feature or acceptance criterion, an `[IMP]` task and a `[TST]` task must be created **simultaneously** during sprint planning. The two tasks execute in parallel and are designed to proceed independently.

**The critical constraint: no shared context between tracks.**

The `[TST]` owner must not read implementation code. The `[IMP]` owner must not read test assertions. The contract (see Part 2 §1) is the only shared artifact. If either owner reads the other's work before both are complete, the independence guarantee is broken — tests drift toward matching the implementation rather than verifying the AC, and implementations drift toward passing the tests rather than fulfilling the user story.

Merge rules:
* Neither ticket merges until both are green.
* The `[TST]` ticket is opened in the red state intentionally — a failing test is the expected and correct starting point.
* A passing `[IMP]` against a failing `[TST]` is not done. A passing `[TST]` against a failing `[IMP]` is not done. Both green = done.

---

## Part 2: The ATDD Workflow

### 1. The Pre-Code Contract

Before either track starts coding, the `[IMP]` owner and `[TST]` owner must agree on a three-part contract:

1. **Entry-point signature** — the exact function, endpoint, or trigger the implementation exposes.
2. **Completion signal** — the observable event the test harness waits for before asserting (a log tag, a webhook, a status code, a file appearing).
3. **Output schema** — the exact structure of the artifact the test will inspect (columns, fields, XML shape, file format).

This contract is the only document both tracks share. Neither track should need to ask the other a question after this point.

> **GAS/Python note:** The completion signal is a tagged log entry (e.g., `sync.complete`) written by GAS and polled by the Python test. The output schema is the column layout of the XLSX export and the XML structure of the DOCX. Both are documented before GAS coding begins.

### 2. Parallel Tracks

```
                  ┌──► [IMP] Implementation (builds logic, emits completion signal) ──┐
                  │                                                                    │
[Define Contract] │                                                                    ├──► Both green → Merge
                  │                                                                    │
                  └──► [TST] Verification  (builds fixtures and assertions)  ──────────┘
```

The `[TST]` track builds scaffolding against the contract and pushes a red test to CI. The `[IMP]` track builds logic until the test turns green. Neither track waits on the other once the contract is signed.

---

## Part 3: Universal Testing Principles

### 1. Tests are organized by use case, not by module

Each test file corresponds to a user-facing use case, not to an internal code module. The test name states what the user is doing; the assertion checks whether the system delivered it. When a test fails you know immediately which user story broke.

**Rule:** One test file per use case. Name tests after the AC they exercise.

### 2. Each test maps to exactly one AC, stated in the docstring

The docstring quotes or paraphrases the Acceptance Criteria verbatim. This prevents tests from drifting from their original product intent over time and makes a failing test self-explanatory without reading the code.

**Rule:** Every test method has a docstring that states the AC. The docstring is the spec, not commentary.

### 3. Assertions verify durable system state, not return values

Tests inspect the artifact the user would observe — not the API response, not a log entry, not an in-memory value. A function that returns success but writes nothing should still fail.

**Rule:** Assert on what the system persisted. If you are only asserting on a return value or a log message, you are not testing the AC.

> **GAS/Python note:** Tests download the actual sheet as XLSX and the actual document as DOCX after the completion signal fires, then parse them with openpyxl and python-docx. The download happens after the completion signal — not after a sleep — to avoid asserting on stale data. In GAS, call `SpreadsheetApp.flush()` and `document.saveAndClose()` before emitting the completion signal to guarantee the write is committed before Python initiates the download.

### 4. Comprehensive fixture variants, bounded by runtime limits

The canonical test fixture contains every input permutation the system must handle. Variants are cheap to add; execution runs against an external system are expensive. One execution round that checks six variants is vastly better than six separate execution rounds.

**Rule:** One execution round per AC covering all relevant input permutations. Do not add a test function per variant; add variants to the fixture.

> **GAS/Python note:** GAS scripts time out after six minutes. Design fixtures to stay well under this ceiling. The six-minute limit is the reason to batch variants, not just a performance preference.

### 5. Negative cases are first-class

Every test that verifies positive detection must simultaneously verify that inputs which should be excluded are absent. Omitting negative assertions is how false positives ship undetected.

**Rule:** Every test that asserts "X should exist" also asserts "Y should not exist" in the same test run.

### 6. Idempotency is an explicit test, not an assumption

Systems that work correctly on the first operation frequently break on the second by duplicating state, corrupting identifiers, or losing timestamps. Idempotency must be tested as a separate AC — it cannot be inferred from a passing first-run test.

**Rule:** For any operation that should be repeatable, write an explicit idempotency test. Run the operation twice back-to-back and diff the full output state before and after the second run.

### 7. Test fixtures are isolated per run via named clones

Tests must not share mutable state across runs or across parallel executions. Each run gets its own isolated fixture. Fixture state left over from a previous run is a silent source of false positives and unexplained failures.

**Rule:** Each test run creates a fresh fixture from a known master template. The fixture is destroyed after the run. Never mutate a shared static fixture in place.

**Clone naming format:** `{project}-Test-{scenario-slug}-{YYYYMMDD}-{4-char-hex}`

This format is human-readable when browsing a file system or cloud storage, identifies the owning scenario, and is unique enough to avoid collision across parallel runs.

> **GAS/Python note:** The Python conftest clones the master Google Drive template at setup and deletes the clone at teardown. The clone ID is passed to GAS as a script parameter. Generate the name with:
> ```python
> import secrets, datetime
> clone_name = f"GActionSheet-Test-{scenario_slug}-{datetime.date.today():%Y%m%d}-{secrets.token_hex(2)}"
> ```

### 8. Assertions carry context for triage

Every assertion must answer four questions in its failure message: which use case, which AC, what was expected, what was observed. A test that fails in a headless environment must be triageable from the error message alone — without re-running the test or reading the source.

**Rule:** Every assertion message includes a `[uc-name AC#]` tag, the expected value, and the observed value. One line, no ambiguity.

---

## What this strategy does not do (intentionally)

* **No mocking of external platform APIs** — platform behaviors and quotas shift silently; mocking introduces a dangerous divergence from production reality.
* **No unit tests for internal helpers** — internal functions can be refactored freely; as long as the end-to-end use case passes, the test suite should stay green. Unit tests for internal helpers belong only where the helper contains complex pure logic that is difficult to exercise through the integration path.
* **No test-per-variant parametrize explosion** — input permutations live inside the fixture, not as separate test functions.
