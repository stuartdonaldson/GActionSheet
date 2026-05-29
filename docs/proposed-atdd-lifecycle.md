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

---

## §15 — Scenario Test Python Architecture

_Working design from the 2026-05-29 session. Captures architectural decisions and open questions for the implementation of the §14 scenario in Python._

### Document initialization

The journey starts with a **new empty Google Doc**, not a clone of the master template. This eliminates template-state contamination entirely — the doc is guaranteed clean, has no pre-existing floating actions, and requires no reset step between runs.

The GAS `begin_journey_session` fixture creates the doc with `DocumentApp.create(name)`, names it `GActionSheet-Test-journey-{YYYYMMDD}-{4-char-hex}`, and places it in the same Drive folder as the test sheet. The Python fixture trashes it at teardown via `end_journey_session`.

Document initialization variants — and when to use each:

| Source | When to use |
|---|---|
| New empty doc (`DocumentApp.create`) | Standard scenario start — guaranteed clean, no template drift |
| Clone of master template | When specific pre-populated structure is required (not currently needed) |
| Existing specific doc | Edge-case tests around docs that already have actions; known to have rough edges around delete-all scenarios — **not prioritized** |

### `ActionItem` — internal representation

An `ActionItem` holds what we know about one action across its full lifecycle. Field names match the ActionSheet column schema so that find/update fixture calls do not require a translation layer.

```
ActionItem
  seed_text          # full string inserted into doc, e.g. "AI: aitest@example.com Some text"
  action_text        # body only — without the AI: prefix and email
  assignee_email     # None for unassigned
  assignee_name      # None for unassigned; resolved display name for domain users
  expected_id        # None = auto-assigned; integer = explicit (e.g. 5 for AI-5:)
  global_id          # populated after sync, e.g. "docId/AI-3"
  status             # "Open" initially
  sync_status        # "" (clean) or "Dirty"; read back from find_sheet_actions
  last_modified      # read back from find_sheet_actions; archival, not used for conflict resolution
  row_id             # sheet row number; populated by find_sheet_actions for use with update_sheet_field
```

### `ScenarioSession` — thin driver, not assertion owner

`ScenarioSession` owns: doc lifecycle, fixture invocation, downloads, and `ActionItem` state accumulation. It does **not** own assertion logic. Methods return data structures; assertion functions are standalone — either in the test file or a shared `assertions.py` module.

```python
class ScenarioSession:
    # Lifecycle
    @classmethod
    def new_doc(cls, settings) -> ScenarioSession: ...   # creates empty doc, registers for teardown
    def close(self): ...                                  # trashes journey doc

    # Doc mutations (each is one HTTP fixture call)
    def append_doc_item(self, item: ActionItem): ...      # inserts seed text; registers item on session
    def insert_tracker_table(self): ...

    # Sync (name states the mechanism explicitly)
    def sync_document(self): ...                          # calls GAS syncDocument() via doPost — Scenario C

    # Artifact downloads
    def doc_items(self) -> list[DocItem]: ...             # download + parse docx; return floating action structs
    def sheet_rows(self) -> list[ActionItem]: ...         # download + parse xlsx; filter for this doc's rows

    # Sheet read/write (for manipulation tests)
    def find_sheet_actions(self) -> list[ActionItem]: ... # doPost find_sheet_actions — returns rows with row_id
    def update_sheet_field(self, row_id, field, value): ...  # doPost update_sheet_field — see open question below

    # GAS-side consistency (doc ↔ sheet verification)
    def verify_consistency(self) -> dict: ...             # calls verify_consistency fixture; returns data dict
```

Assertion functions receive the data structures returned by these methods and carry the `[UC AC#]` context tag:

```python
def assert_all_imported(doc_items, sheet_rows, items: list[ActionItem]): ...
def assert_doc_sheet_consistent(consistency_data): ...
def assert_tracker_rows(consistency_data, items: list[ActionItem]): ...
def assert_field_propagated(doc_items, sheet_rows, item, field, expected): ...
def assert_sync_status_clear(sheet_rows, item): ...
def assert_unassigned_deleted(sheet_rows, item): ...
```

### Module-scoped fixture carries state across test functions

```python
@pytest.fixture(scope="module")
def journey(settings):
    session = ScenarioSession.new_doc(settings)
    yield session
    session.close()
```

Each test function receives `journey` and operates on accumulated state. `append_doc_item` both inserts the item into the doc and registers it on `session.items` (and named attributes like `session.unassigned`, `session.with_email`, `session.explicit_5`, `session.domain_user`), so later test functions can reference them without re-declaring.

Pytest module ordering guarantees the test sequence. Dependency between tests is intentional and explicit: this is a scenario, not isolated unit tests.

### Explicit seeding in test_01

Each item is declared inline in the test — not buried in a `seed()` helper. The test reads as a specification:

```python
def test_01_seed_and_import(journey):
    journey.append_doc_item(ActionItem(
        seed_text="AI: This tag and text confirms creation of an unassigned action item",
        action_text="This tag and text confirms creation of an unassigned action item",
        assignee_email=None, assignee_name=None, expected_id=None,
    ))
    journey.append_doc_item(ActionItem(
        seed_text="AI: aitest@example.com This tag and email address ...",
        action_text="This tag and email address along with this text ...",
        assignee_email="aitest@example.com", assignee_name="Aitest", expected_id=None,
    ))
    journey.append_doc_item(ActionItem(
        seed_text="AI-5: This tag and text confirms creation of an action item with id AI-5 ...",
        action_text="This tag and text confirms creation of an action item with id AI-5 ...",
        assignee_email=None, assignee_name=None, expected_id=5,
    ))
    journey.append_doc_item(ActionItem(
        seed_text="AI-9: minister@northlakeuu.org This tag, email and text ...",
        action_text="This tag, email and text ...",
        assignee_email="minister@northlakeuu.org", assignee_name="Northlake Minister", expected_id=9,
    ))

    journey.sync_document()

    doc_items = journey.doc_items()
    sheet_rows = journey.sheet_rows()
    consistency = journey.verify_consistency()

    assert_all_imported(doc_items, sheet_rows, journey.items)
    assert_doc_sheet_consistent(consistency)
```

**Note on doc verification:** after sync, `AI:` items must appear promoted to `AI-N:` with auto-assigned integers; `AI-5:` and `AI-9:` must be unchanged; the domain user must have a resolved display name. Named range IDs (now called `globalId`) are Google Docs metadata and do not survive the docx export — `globalId` linkage is verified through the GAS-side `verify_consistency` call, not by parsing the docx directly.

### Sync naming

`sync_document()` maps to Scenario C (DESIGN.md §Sync Scenarios): direct call to `syncDocument()` via doPost. This is the bidirectional full reconcile. Other sync entry points are distinct and named explicitly when used:

| Method | Mechanism | DESIGN.md scenario |
|---|---|---|
| `sync_document()` | doPost → `sync_action_rows` | Scenario C |
| Playwright: sidebar "Sync Now" | CardService button → `onSyncNow` → `syncDocument` | Scenario C (UI path) |
| `onActionSheetEdit` stamp + flush | Installable trigger, auto-fires on col 3–6 edit | Scenario B |
| `syncAll` sweep | Time-based trigger | Scenario C (automated) |

### Full test sequence

```
test_01  doc: seed 4 items explicitly → sync_document() → verify doc + sheet + consistency
test_02  doc: insert_tracker_table → sync_document() → verify tracker rows

         — sheet manipulation phase (HTTP only, conflict resolution coverage) —

test_03  sheet: update assignee_email on one row → sync_document() → verify propagated to doc
test_04  sheet: update action_text → sync_document() → verify
test_05  sheet: update status → sync_document() → verify
test_06  doc: edit status token in paragraph → sync_document() → verify sheet updated (doc wins)
test_07  conflict: set field on both sides; sheet has Dirty → verify sheet wins
test_08  idempotency: sync_document() twice with no changes → verify no new rows, no mutations

         — Playwright phase (deferred) —

test_09  UI: open sidebar, verify Sync Now, verify actions visible
test_10  UI: @create flow → verify action in doc, sheet, tracker
test_11  UI: preview card status change → verify propagation
test_12  UI: mark item deleted via preview card → verify Deleted in sheet, removed from doc
```

### Sheet manipulation fixtures — GAS side

Two new `doPost` routes needed in `TestFixtures.js` (or `WebApp.js`):

**`find_sheet_actions`**
- Input: `docId` (sufficient; no filter needed — the doc's globalId prefix uniquely scopes results)
- Returns: array of row objects with field names matching `ActionItem` plus `row_id` (sheet row number)
- Read-only; safe to call at any time

**`update_sheet_field`**
- Input: `row_id`, `field` (ActionItem field name), `value`
- Writes one cell to the Actions sheet using the field→column mapping

### Conflict resolution context (from DESIGN.md ADR-0009)

Resolution is per-row by `Sync Status` (col 10), not by timestamp:
- `Sync Status = 'Dirty'` → sheet wins: values flushed doc-ward on next sync, Dirty cleared
- `Sync Status = ''` → doc wins: sheet cells overwritten from scanned doc state on next sync
- `Date Modified` (col 9) is archival only — not used for resolution

`onActionSheetEdit` stamps Dirty + Date Modified when a user edits cols 3–6. **Critical constraint:** doPost writes (including `update_sheet_field`) run as the deployer in a separate execution and do **not** fire `onActionSheetEdit` (confirmed in DESIGN.md §Programmatic Write Suppression). This means the `update_sheet_field` fixture must handle Dirty stamping explicitly.

### Open questions (unresolved as of 2026-05-29)

**Q1: Should `update_sheet_field` auto-stamp Dirty + Date Modified for data columns?**

Option A: Yes — fixture replicates `onActionSheetEdit` behaviour when writing cols 3–6. A single call means "simulate a user sheet edit," which is the intended test scenario. Simpler test code.

Option B: No — test explicitly calls `update_sheet_field` twice (value, then Dirty). Makes the "what is being tested" more explicit — the test shows it's setting up a Dirty row. Slightly more verbose.

Lean toward Option A for readability, but needs confirmation.

**Q2: What is the stable identifier for `update_sheet_field`?**

Option A: Raw sheet row number (`row_id`). Simple, but fragile if rows shift during the test.

Option B: `globalId` (e.g. `docId/AI-3`). Already unique per action, already in ActionItem. `update_sheet_field` resolves it to a row number server-side.

Lean toward Option B — `globalId` is the system's own stable identity and does not depend on physical row position.
