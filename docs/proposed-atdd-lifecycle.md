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

**The critical constraint: no shared implementation/test design context beyond the agreed contract.**

When AI assistance is used, the `[TST]` track and `[IMP]` track must not share the same LLM design context, prompt history, or generated artifacts beyond the contract (see Part 2 §1). The goal is independent design pressure: tests should be derived from the requirement contract, not from implementation details, and implementation should be derived from the requirement contract, not from the test assertions.

Human reviewers and maintainers may cross-read implementation and tests later for diagnosis, repair, and refactoring. The independence rule applies to initial design and first-pass authoring, not to ongoing maintenance after the contract has been exercised.

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

### 1. Two complementary test layers

The test strategy has two required layers:

1. **Focused AC verification tests** — prove one acceptance criterion directly with targeted assertions.
2. **Scenario workflow tests** — exercise a realistic sequence of user operations that may cover multiple acceptance criteria, integration seams, and UI transitions in one run.

Focused AC tests are the coverage baseline. Scenario workflow tests provide broad interaction coverage and regression confidence across feature boundaries. Scenario tests may include and satisfy AC coverage when the AC is written in a modular, reusable way that does not over-constrain the setup or teardown beyond a clean isolated environment.

**Rule:** Every delivered AC must be covered by at least one focused verification path. Scenario workflow tests may cover multiple ACs efficiently, but they do not replace the need for explicit AC traceability.

### 2. Tests are organized by use case or workflow, not by module

Each test file corresponds to either a user-facing use case or a named workflow, not to an internal code module. The test name states what the user is doing; the assertion checks whether the system delivered it. When a test fails you should know immediately which use case or workflow broke.

**Rule:** Group tests by user-visible behavior. Focused AC tests should be named after the AC they exercise. Scenario tests should be named after the workflow they exercise.

### 3. ACs are modular and reusable across scenarios

Acceptance criteria should be written so they can be verified in more than one valid execution path. An AC that assumes a clean isolated environment is compatible with data-driven scenario testing as long as it does not over-prescribe incidental preconditions or postconditions that are unrelated to the user-visible outcome.

This allows a single scenario to validate several ACs while still preserving clear traceability. The AC remains the unit of requirement coverage; the scenario is one reusable vehicle for exercising it.

**Rule:** Write ACs so they can be verified from observable outcomes in any valid clean-room scenario, unless the requirement genuinely depends on a specific setup sequence.

### 4. Each focused AC test maps to one AC, stated in the docstring

The docstring quotes or paraphrases the Acceptance Criteria verbatim. This prevents tests from drifting from their original product intent over time and makes a failing test self-explanatory without reading the code.

**Rule:** Every focused AC test has a docstring that states the AC. Scenario tests must list the AC identifiers they are expected to exercise.

### 5. Assertions verify durable system state and user-observable behavior

Tests inspect what the user would actually observe. For persisted mutations, that means the durable artifact — not the API response, not a log entry, not an in-memory value. For interactive editor behavior, that may also include UI-observable state such as a visible sidebar row, hover card, tooltip, icon state, or disabled control.

**Rule:** Assert on durable state for persisted changes and on direct UI evidence for interactive behavior. If you are only asserting on a return value or a log message, you are not testing the user outcome.

> **GAS/Python note:** Tests download the actual sheet as XLSX and the actual document as DOCX after the completion signal fires, then parse them with openpyxl and python-docx. The download happens after the completion signal — not after a sleep — to avoid asserting on stale data. In GAS, call `SpreadsheetApp.flush()` and `document.saveAndClose()` before emitting the completion signal to guarantee the write is committed before Python initiates the download.

### 6. Data-driven variants and scenarios are both first-class

The canonical test fixture should contain meaningful input permutations the system must handle. Data-driven variants are cheap to add; execution runs against an external system are expensive. One execution round that checks several meaningful permutations is often better than several separate execution rounds.

Use data-driven permutations when the setup sequence is the same and only the inputs or expected outcomes vary. Use distinct scenario tests when the user workflow materially changes.

**Rule:** Do not create a separate test function for every trivial permutation. Put input variants inside a shared fixture or scenario table when the workflow is the same. Split into a separate scenario only when the operation sequence or interaction model changes.

> **GAS/Python note:** GAS scripts time out after six minutes. Design fixtures to stay well under this ceiling. The six-minute limit is the reason to batch variants, not just a performance preference.

### 7. Negative cases are first-class

Every test that verifies positive detection must simultaneously verify that inputs which should be excluded are absent. Omitting negative assertions is how false positives ship undetected.

**Rule:** Every test that asserts "X should exist" also asserts "Y should not exist" in the same test run.

### 8. Idempotency is an explicit test, not an assumption

Systems that work correctly on the first operation frequently break on the second by duplicating state, corrupting identifiers, or losing timestamps. Idempotency must be tested as a separate AC — it cannot be inferred from a passing first-run test.

**Rule:** For any operation that should be repeatable, write an explicit idempotency test. Run the operation twice back-to-back and diff the full output state before and after the second run.

### 9. Test fixtures are isolated per run via named clones

Tests must not share mutable state across runs or across parallel executions. Each run gets its own isolated fixture. Fixture state left over from a previous run is a silent source of false positives and unexplained failures.

**Rule:** Each test run creates a fresh fixture from a known master template. The fixture is destroyed after the run. Never mutate a shared static fixture in place.

**Clone naming format:** `{project}-Test-{scenario-slug}-{YYYYMMDD}-{4-char-hex}`

This format is human-readable when browsing a file system or cloud storage, identifies the owning scenario, and is unique enough to avoid collision across parallel runs.

> **GAS/Python note:** The Python conftest clones the master Google Drive template at setup and deletes the clone at teardown. The clone ID is passed to GAS as a script parameter. Generate the name with:
> ```python
> import secrets, datetime
> clone_name = f"GActionSheet-Test-{scenario_slug}-{datetime.date.today():%Y%m%d}-{secrets.token_hex(2)}"
> ```

### 10. Assertions carry context for triage

Every assertion must answer four questions in its failure message: which use case, which AC, what was expected, what was observed. A test that fails in a headless environment must be triageable from the error message alone — without re-running the test or reading the source.

**Rule:** Every assertion message includes a `[uc-name AC#]` tag, the expected value, and the observed value. One line, no ambiguity.

### 11. Use checkpoints to balance confidence and runtime

Long-running scenario tests should not perform a full artifact reconciliation after every UI action. Instead, they should use explicit checkpoints:

1. **Step checkpoint** — validate only the state introduced by the most recent action.
2. **Integrity checkpoint** — reconcile the document, spreadsheet, and any rendered tracker table for end-to-end consistency.

This keeps scenario tests informative without turning every intermediate interaction into a full export-and-parse cycle.

**Rule:** Use lightweight step checkpoints during multi-step UI flows and reserve full integrity reconciliation for scenario end or major mutation boundaries.

### 12. Pure logic may use focused helper tests

End-to-end verification is the primary safety net for this system, but deterministic pure logic does not need to wait on a cloud round-trip to be validated. Parsing, normalization, identifier derivation, and similar side-effect-free logic may use focused helper tests when that reduces runtime and improves diagnosis without coupling the suite to implementation trivia.

**Rule:** Allow focused helper tests only for deterministic logic with stable inputs and outputs. Do not use helper tests as a substitute for end-to-end verification of user-visible behavior.

### 13. Test architecture must make intended outcomes explicit

Many test failures come from weak test architecture rather than weak product code. A scenario that performs many operations but does not explicitly record what each operation is expected to produce becomes difficult to diagnose and easy to under-assert.

Scenario drivers should register expected outcomes as they mutate the system. These expectations can then be consumed by later checkpoints instead of re-deriving intent from the final document state.

Typical queued verification items include:

1. expected action creation from an `AI:` or `AI-N:` tag;
2. expected assignee resolution from an email token;
3. expected tracker-table row creation or update;
4. expected sidebar visibility after sync;
5. expected status transition after a UI gesture.

This pattern keeps the scenario readable: the action step declares what it intends to change, and the checkpoint verifies that those declared changes actually landed.

**Rule:** Each scenario step that mutates state should either assert the result immediately or enqueue a specific verification item for the next relevant checkpoint. Do not rely on a final broad consistency pass alone to prove that an intermediate behavior worked correctly.

> **GAS/Python note:** The integrity code that verifies AI-tag import, Playwright-created actions, and status changes may maintain a queue of expected mutations. After an integrity/consistency check completes, the harness should evaluate the queued items against the downloaded DOCX/XLSX artifacts and any captured UI state, then clear only the items that were satisfied.

### 14. Example scenario: document-to-sheet sync plus editor interactions

The following example shows how a single scenario can efficiently exercise multiple ACs and code paths while preserving focused checkpoints.

**Scenario name:** AI tag import, sidebar sync, tracker insertion, and `@create` interaction

**Environment:** Fresh clone of a known template in an isolated test run.

**Seed data inserted into the test document:**

AI creation from the AI-N tagging creation can be tested by inserting the following text. This can be done by calling test functions from the dev environment test scripts. The following text can be inserted verbatim as examples and, when scanned by a sync operation, will trigger the creation of action items.

* `AI: This tag and text confirms creation of an unassigned action item`
* `AI: aitest@example.com This tag and email address along with this text confirms the creation of an action item with an assignee.`
* `AI-5: This tag and text confirms creation of an action item with id AI-5 pre-assigning the specific ID.`
* `AI-9: minister@northlakeuu.org This tag, email and text should result in the creation of the assignee as a person chip, working within our Northlake domain this has a username of 'Northlake Minister' which should appear in the chip.`

**Scenario flow:**

1. Start with a cloned copy of the known test template.
2. Insert the seed data above into the test document.
3. Trigger sync by calling `doPost()` for the test document.
4. Queue the expected results for the four inserted AI-tag examples.
5. Run an integrity checkpoint against the test document and its sheet only.
6. Consume the queued verification items for AI-tag parsing, ID assignment, assignee extraction, and chip resolution.
7. Verify that all actions in the sheet are present in the document and vice versa, and that action text and assignee information match.
8. Verify the expected seed outcomes:
    * the first `AI:` tag creates a new action with a generated ID, no assignee, and the action text `This tag and text confirms creation of an unassigned action item`;
    * the second `AI:` tag creates a new action with a generated ID, the assignee `aitest@example.com`, and the action text `This tag and email address along with this text confirms the creation of an action item with an assignee.`;
    * `AI-5` is preserved as an explicit ID and retains the action text `This tag and text confirms creation of an action item with id AI-5 pre-assigning the specific ID.`;
    * `AI-9` is preserved as an explicit ID, parses `minister@northlakeuu.org` as the assignee, retains the remaining sentence as the action text, and resolves the assignee chip name to `Northlake Minister`.
9. Open the test document in Playwright.
10. Open the sidebar from the editor add-on icon.
11. Verify the displayed version.
12. Run Sync Now, queue the expected sidebar-visible results, and verify that the seeded actions appear in the sidebar.
13. Insert the tracker table, queue the expected tracker rows, and run Sync Now again.
14. On a new line in the document, type `@create`, choose Create Action from the `@` menu, set the action text to `Creating an action via the @- trigger`, and set the assignee to `sdonaldson@northlakeuu.org`.
15. Queue verification items for the newly created action across document text, sidebar state, and tracker-table state.
16. Treat missing autocomplete as a warning-only observation unless the AC explicitly requires autocomplete for completion.
17. Verify that the newly created action appears in the document, sidebar, and tracker table where applicable.
18. Hover over the newly created `AI-N` action and verify that the preview card appears.
19. Hover over the In Progress icon and verify that the tooltip appears.
20. Click In Progress, queue the expected status transition, allow the temporary busy state to clear, and verify within 10 seconds that the action status has updated.
21. Run a final integrity checkpoint by downloading the DOCX/XLSX artifacts and reconciling document actions, sheet actions, and tracker-table rows for the test document only.
22. Consume the remaining queued verification items for Playwright-created actions and status changes.
23. Verify the two actions created through editor interaction have the correct text, status, and assignee in all durable representations.

**Why this is a scenario test:** It exercises several ACs and interaction seams in one realistic journey. It provides broad regression coverage efficiently, but it does not remove the need for focused AC tests for parsing, sync rules, tracker insertion, and status transitions.

---

## What this strategy does not do (intentionally)

* **No mocking of external platform APIs** — platform behaviors and quotas shift silently; mocking introduces a dangerous divergence from production reality.
* **No test-per-variant parametrize explosion** — input permutations live inside the fixture, not as separate test functions.
