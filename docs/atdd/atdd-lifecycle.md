# ATDD Testing & Lifecycle Strategy

> **Canonical sources (extracted 2026-06-03).** The portable principles and the GAS
> mechanics in this document have been extracted to shared repos and are **canonical there**:
> - **Universal scenario-testing principles** → DevStandard
>   `knowledge-base/methodology/testing/atdd-bdd.md` § *Universal Scenario-Testing Engineering Principles*.
> - **GAS+Python acceptance-testing mechanics** → GAS-Practices
>   `best-practices/gas-acceptance-testing/`.
>
> This document is now the **project realization layer** — §15–§16 (the `scn/` scenario
> model, the canonical journey, the `ContractSchema.js` contract) are GActionSheet-specific
> and stay here. Parts 1–3 and the inline "GAS/Python note" callouts below are retained for
> continuity but are **superseded by the canonical sources above**; consult those for the
> authoritative statement of each principle. A follow-up (bd) will repoint §16's internal
> cross-references and thin Parts 1–3 to pointers — until then, where this doc and the
> canonical sources differ, the canonical sources win.

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

_This section originally read as 23 imperative steps. That style is superseded by the Act / Expect / Checkpoint model; the **canonical, structured form of this journey is §16.10**. This intro is retained for narrative orientation and for the concrete seed strings._

**Scenario name:** AI tag import, sidebar sync, tracker insertion, and `@create` interaction.

**Narrative.** Starting from a clean isolated environment, an author types several `AI:`/`AI-N:` lines into a document; a sync converts them into actions across doc and sheet; the tracker table is inserted and re-synced; then the editor add-on UI is exercised — `@create`, preview-card hover, and a status change — with durable state reconciled at the HTTP boundaries. It exercises Sync Scenarios C, B/A, and the editor UI in one realistic journey, providing broad regression coverage without removing the need for focused AC tests for parsing, sync rules, tracker insertion, and status transitions.

**Seed strings** (verbatim text inserted into the document; each triggers one action when scanned by sync):

* `AI: This tag and text confirms creation of an unassigned action item`
* `AI: aitest@example.com This tag and email address along with this text confirms the creation of an action item with an assignee.`
* `AI-5: This tag and text confirms creation of an action item with id AI-5 pre-assigning the specific ID.`
* `AI-9: minister@northlakeuu.org This tag, email and text should result in the creation of the assignee as a person chip, working within our Northlake domain this has a username of 'Northlake Minister' which should appear in the chip.`

See **§16.10** for the canonical structured journey (acts, expectations, checkpoints) and **§16.1–16.9** for the vocabulary it is written in.

---

## What this strategy does not do (intentionally)

* **No mocking of external platform APIs** — platform behaviors and quotas shift silently; mocking introduces a dangerous divergence from production reality.
* **No test-per-variant parametrize explosion** — input permutations live inside the fixture, not as separate test functions.

---

## §15 — Scenario Test Python Architecture

_Background reference (2026-05-29). §16 supersedes this section's API naming — this section is retained for its contract-ownership model and conflict-resolution detail only. The `scn/session.py` module is the as-built implementation._

> **§16 is canonical for the scenario API and supersedes this section's naming where they differ:** `append_doc_item`→`append_paragraph`, `sync_document`→`sync`, `ActionItem`→`ai`, `seed_text()`→`as_text()`, `update_sheet_field`→`edit_sheet`. §15 is retained for its contract-ownership model and conflict-resolution detail, not as the canonical API surface.

### Document initialization

The journey starts with a **new empty Google Doc**, not a clone of the master template. This eliminates template-state contamination entirely — the doc is guaranteed clean, has no pre-existing floating actions, and requires no reset step between runs.

The GAS `begin_journey_session` fixture creates the doc with `DocumentApp.create(name)`, names it `GActionSheet-Test-journey-{YYYYMMDD}-{4-char-hex}`, and places it in the same Drive folder as the test sheet. The Python fixture trashes it at teardown via `end_journey_session`.

Document initialization variants — and when to use each:

| Source | When to use |
|---|---|
| New empty doc (`DocumentApp.create`) | Standard scenario start — guaranteed clean, no template drift |
| Clone of master template | When specific pre-populated structure is required (not currently needed) |
| Existing specific doc | Edge-case tests around docs that already have actions; known to have rough edges around delete-all scenarios — **not prioritized** |

### Contract ownership for scenario tests

This section is **not** the authoritative source for application contracts. It describes how the scenario tests should **consume** contracts that are defined elsewhere.

Recommended ownership model:

- [docs/DESIGN.md](/home/stuar/roots/c-dev/GActionSheet/docs/DESIGN.md) owns the human-readable contract semantics: boundary names, field meanings, invariants, defaults, and ownership rules.
- [src/ContractSchema.js](/home/stuar/roots/c-dev/GActionSheet/src/ContractSchema.js) owns the exact machine-readable shapes currently shared across app code and test consumers.
- [docs/atdd/atdd-lifecycle.md](/mnt/c/dev/GActionSheet/docs/atdd/atdd-lifecycle.md) should only describe how tests use those contracts.

For this system, the likely contract families are:

1. `ActionItem` contract: the minimal action content model used for doc seeding and doc-state assertions.
2. `SheetAction` contract: the ActionSheet row model, including column mapping and derived fields.
3. Web App message contract: every `doPost()` action payload and response shape.
4. Document read contract: the structure returned when test code or fixtures read floating actions, tracker rows, or other doc-derived state.

Preferred single-source pattern:

1. `DESIGN.md` states which contract families exist and who owns them.
2. [src/ContractSchema.js](/home/stuar/roots/c-dev/GActionSheet/src/ContractSchema.js) defines the exact field lists and shared names currently needed by app code and tests.
3. Tests, fixtures, and implementation code all read from that same source or are validated against it.

Applied to this scenario architecture:

- The scenario test should construct `ActionItem` values using the authoritative action-content contract.
- The scenario test should read sheet rows into `SheetAction` values using the authoritative ActionSheet contract.
- Every helper that posts to the Web App should conform to the authoritative `doPost()` message contract.
- Every helper that reads state from the document should conform to the authoritative document-read contract.


The current dedicated interface source file is [src/ContractSchema.js](/home/stuar/roots/c-dev/GActionSheet/src/ContractSchema.js). This document should reference it and avoid restating its field tables.

#### Example: Consuming the contract in Python scenario tests

Scenario tests should consume the contract as data, not by duplicating field lists. This can be done by:

1. Exporting the schema from ContractSchema.js as JSON (e.g., via a build step or script).
2. Loading the JSON in Python test code:

```python
import json
with open('ContractSchema.json') as f:
    contract = json.load(f)
SHEET_HEADERS = contract['SHEET_HEADERS']
```

Alternatively, tests can parse the .js file directly if needed, but a JSON export is preferred for clarity and automation.

**Workflow for contract updates:**
- When a contract field or structure changes in ContractSchema.js, re-export the JSON and update test fixtures to match.
- Tests should fail clearly if the contract and test expectations drift, enforcing single-source discipline.


### `ScenarioSession` — thin driver, not assertion owner
`ScenarioSession` owns: doc lifecycle, fixture invocation, downloads, and `ActionItem`/`SheetAction` state accumulation. It does **not** own assertion logic. Methods return data structures; assertion functions are standalone — either in the test file or a shared `assertions.py` module.

```python
class ScenarioSession:
    # Lifecycle
    @classmethod
    def new_doc(cls, settings) -> ScenarioSession: ...   # creates empty doc, registers for teardown
    def close(self): ...                                  # trashes journey doc

    # Doc mutations (each is one HTTP fixture call)
    def append_doc_item(self, item: ActionItem): ...      # inserts item.seed_text(); registers item on session
    def insert_tracker_table(self): ...

    # Sync (name states the mechanism explicitly)
    def sync_document(self): ...                          # calls GAS syncDocument() via doPost — Scenario C

    # Artifact downloads
    def doc_items(self) -> list[DocItem]: ...             # parse floating action state; includes doc-only presentation details
    def sheet_rows(self) -> list[SheetAction]: ...        # download + parse xlsx; map columns by SHEET_HEADERS

    # Sheet read/write (for manipulation tests)
    def find_sheet_actions(self) -> list[SheetAction]: ...    # fixture/webapp read for current doc only
    def update_sheet_field(self, sheet_action, field, value): ...
                                                # update a SheetAction field using stable identity

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
        action_text="This tag and text confirms creation of an unassigned action item",
    ))
    journey.append_doc_item(ActionItem(
        action_text="This tag and email address along with this text ...",
        assignee_email="aitest@example.com",
    ))
    journey.append_doc_item(ActionItem(
        action_text="This tag and text confirms creation of an action item with id AI-5 ...",
        action_id="AI-5",
    ))
    journey.append_doc_item(ActionItem(
        action_text="This tag, email and text ...",
        assignee_email="minister@northlakeuu.org",
        action_id="AI-9",
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

If new sheet-manipulation fixtures are added, their request/response shapes should be defined in the authoritative Web App message contract rather than here.

For this scenario, the likely fixture/message pair is still:

- `find_sheet_actions`: read-only route returning the current document's ActionSheet rows in the authoritative `SheetAction` shape.
- `update_sheet_field`: write route that updates one logical `SheetAction` field using the authoritative field-to-column mapping.

The important rule is ownership: this document may name the routes the scenario needs, but payload fields, response fields, and stable identifiers belong in the shared contract source.

### Conflict resolution context (from DESIGN.md ADR-0009)

Resolution is per-row by `Sync Status` (col 10), not by timestamp:
- `Sync Status = 'Dirty'` → sheet wins: values flushed doc-ward on next sync, Dirty cleared
- `Sync Status = ''` → doc wins: sheet cells overwritten from scanned doc state on next sync
- `Date Modified` (col 9) is archival only — not used for resolution

`onActionSheetEdit` stamps Dirty + Date Modified when a user edits cols 3–6. **Critical constraint:** doPost writes (including `update_sheet_field`) run as the deployer in a separate execution and do **not** fire `onActionSheetEdit` (confirmed in DESIGN.md §Programmatic Write Suppression). That behavior belongs in the authoritative Web App/message contract; the scenario test should rely on that contract rather than redefining the stamping rules locally.

### Contract status

All decisions are resolved; the authoritative shapes live in `ContractSchema.js` / `DESIGN.md §ATDD Journey Pre-Code Contract`:

1. **Resolved (§16.11 #2):** `edit_sheet` (the renamed `update_sheet_field`) on the API/fixture path **does** replicate a full user edit, stamping Dirty + Date Modified; the Playwright UI path relies on the real `onActionSheetEdit` trigger.
2. **Resolved (§16.11 #3):** write routes use **`globalId`** as the stable identifier.
3. **Deferred:** doc-derived read route architecture documented in `DESIGN.md §ATDD Journey Pre-Code Contract`; refinement deferred to next journey extension.

This document consumes those decisions; it is not where they are finalized.

---

## §16 — Scenario Definition Model (canonical)

_This is the **canonical** definition of how a scenario is written. **Implemented in GTaskSheet-5vwu (2026-05-30).** The `scn/` package (`scn/ai.py`, `engine.py`, `session.py`, `surfaces.py`, `ui.py`, `contract.py`) implements this model; `tests/test_journey.py` is the canonical journey. §14 (prose example) and §15 (early Python architecture) are retained as background._

§14 read as 23 imperative steps. That style does not scale: it bundles unrelated operations into single steps, leaves intent implicit, and makes under-assertion easy. This section replaces the *style* (not the goal) with a small, uniform vocabulary, defines the data object a scenario manipulates, states the level of detail to write at, and catalogs the support functions a scenario author calls.

### 16.1 A scenario is a sequence of three primitives

A scenario is an ordered journey against **one isolated environment**, expressed with three primitives:

| Primitive | What it is | Rule of thumb |
|---|---|---|
| **Act** | One state mutation through **one** user-facing entry point (add a paragraph, sync, edit a sheet field, set a status, delete, insert the tracker, a UI gesture). | One act = one entry point = one user gesture. Never bundle two entry points into one act. |
| **Expect** | A declaration of the outcome an act should produce, enqueued (the §13 queued-verification pattern), with optional arguments for *which surface* and *when* to check it. | State intent where you cause it; if the outcome only becomes true later, target it forward. An act whose outcome is never expected is a coverage hole. |
| **Checkpoint** | The point where enqueued expectations are evaluated against freshly captured state, draining the ones it can observe. Takes an optional `on=frozenset({Surface.X, ...})` to drain only expectations on specified surfaces. Two kinds (below). | Cheap `STEP` checkpoints inline; full `INTEGRITY` checkpoints at mutation boundaries; the queue must be empty by journey end. Targeted `checkpoint(STEP, on=Surface.UI)` drains live-surface observations without triggering expensive INTEGRITY reconciliation. |

Two checkpoint kinds:

- **`STEP`** — validates only the queued expectations its **lightweight read can observe** (e.g. a single `sheet_rows()` pull sees sheet fields but not doc paragraph state, tracker rows, or `globalId` linkage). Drains the ones it satisfied and **leaves the rest queued**. Fast; use after most acts.
- **`INTEGRITY`** — captures the doc (`.docx`), sheet (`.xlsx`), and tracker, runs the GAS-side consistency checklist (§16.7), and can evaluate **every** kind of expectation. Reserve for major mutation boundaries and the journey end. Expensive — **do not run mid-Playwright** (see §16.3 rule 5).

**Drain invariant.** An expectation is verified only when a checkpoint that can observe it drains it. A `STEP` may leave expectations queued; an `INTEGRITY` may not — every queued expectation **it can observe** must be satisfied and drained. Therefore **every expectation must be drained at or before journey end, and the queue must be empty when the session closes.** A non-empty queue at teardown is a test failure (an expectation nobody verified), not a pass. Consequently every journey ends with an `INTEGRITY` checkpoint. Note: `INTEGRITY` observes only {DOC, SHEET, TRACKER} surfaces; UI observations (which are live-only and expensive) are drained separately by targeted `checkpoint(STEP, on=Surface.UI)` calls during the Playwright phase, and an `INTEGRITY` at the phase end will see them already drained. Any expectation an `INTEGRITY` cannot observe (e.g. a UI expectation not yet drained) simply rides the queue to later checkpoints — the invariant is that *every observable expectation drains at its earliest observable checkpoint*.

#### Two reasons an expectation defers — and how to target it

1. **Observability** — the checkpoint's read cannot *see* the surface (a `STEP`'s `sheet_rows()` cannot observe doc paragraph or tracker state). Handled automatically: drain what's observable, leave the rest queued.
2. **Timing / causality** — the outcome is not *true yet* at enqueue time; it only becomes true after a **later act** (an async sidebar status change that converges after the queue drains; a row that archives only after the sweep; a value that reconciles only after a following `sync()`). The author declares this with an **evaluation target**:

| Target | Meaning | Use for |
|---|---|---|
| `at=AUTO` *(default)* | Drain at the **earliest checkpoint that can observe it**; must be satisfied then. | Outcomes true immediately. |
| `at=INTEGRITY` | Skip all `STEP`s; evaluate at the **next `INTEGRITY`**. | Cross-surface / not-yet-true outcomes a `STEP` shouldn't judge prematurely. |
| `at="<label>"` | Evaluate at a **specific labeled checkpoint** placed downstream (`scn.checkpoint(STEP, label="…")`). | An outcome that becomes true only after a particular later act. |

Targeting rules: a checkpoint evaluates an expectation only when it is the target (or, for `AUTO`, the earliest observer) — a pinned expectation is **not** drained early even if observable. When a checkpoint *is* the target the expectation **must** pass there. The drain invariant still governs: a labeled target that never runs leaves a non-empty queue at `close()` — a failure. This makes "check-at-a-specific-step", "check-at-system-integrity", and "check-as-soon-as-visible" one mechanism.

### 16.2 The `ai` object — the noun a scenario manipulates

A scenario manipulates `ai` objects. An `ai` carries **what is known** about one action, **renders its own document text** from those fields, and is **mutable** so the author can pin more once it's known (e.g. an auto-assigned id after sync). The author never types raw document text and never hand-writes a derived value like an assignee name.

```python
aix = ai(action="Creating an action via the @- trigger",
         assignee="sdonaldson@northlakeuu.org")   # only what's known now
aix.as_text()    # → "AI: sdonaldson@northlakeuu.org Creating an action via the @- trigger"
aix.action_id = "AI-9"   # pin later if known; leave unset to just verify a valid AI-N was assigned
aix.status = "Open"      # see status rule below
```

Fields: `action` (text), `assignee` (email, optional), `action_id` (`AI-N`, optional), `status` (free text — common values exist but a user may type anything; optional), `assignee_source` (`chip` | `parsed`, optional — set by the parser when an `ai` is read back from a synced surface, recording whether the assignee came from a chip or from leading-email text; unset on author-constructed `ai`s — §16.5, §16.11 #6).

**`as_text()` rendering** — the string representation of the `ai` exactly as it appears as a paragraph in the document (this is *not* a "seed"; nothing here is meant to change on its own):

| fields known | `as_text()` output |
|---|---|
| `action` | `AI: {action}` |
| `action`, `assignee` | `AI: {assignee} {action}` |
| `action`, `action_id` | `AI-{N}: {action}` |
| `action`, `assignee`, `action_id` | `AI-{N}: {assignee} {action}` |

**Status rendering rule.** The trailing `({status})` token is rendered **only if `status` is set on the `ai`**. If `status` is unset, no token renders. This matters at two moments:

- **Before append:** a user is not expected to type a status unless it is something *other than* `Open`. So a plain action is appended with `status` **unset** (renders no token), and an action the user deliberately starts as `In Progress` is appended with `status="In Progress"` (renders `… (In Progress)`).
- **After append, before expecting:** for the plain action, set `status="Open"` on the `ai` so the post-sync expectation matches — sync detects a tokenless action as `Open` and writes the explicit `(Open)` token. The two cases give two distinct test paths: *default-to-Open detection* and *honor-an-explicit-non-default-status*.

### 16.3 Level of detail — the altitude to write at

Acts at the **entry-point** altitude; expectations at the **observable-state** altitude.

1. **One entry point per act.** `sync()` is one act; "edit the sheet *and* sync" is two. Keeps each failure attributable to one seam and keeps the entry-point coverage matrix honest.
2. **Declare intent in data, not prose.** Mutate the `ai` to what you expect, then enqueue it — the scenario reads as a specification; the assertion code is generic.
3. **Assert observable state only.** Sheet rows from the `.xlsx`, paragraph state from the `.docx`/scan, tracker rows from the rendered table, UI evidence for interactive acts. Never a return value or a log tag (§5).
4. **Scope every read and invariant to the journey's own `docId`.** The ActionSheet accumulates rows across runs; `globalId` carries the doc prefix, so doc-scoping is the clean filter. A whole-sheet count or uniqueness check will read polluted cross-session state.
5. **Checkpoint by cost, never mid-Playwright.** Full `INTEGRITY` reconciliation is expensive and would balloon UI runs. During the Playwright phase prefer **targeted single-surface expectations** (a probe of one `ai` on the docx or xlsx) and reserve `INTEGRITY` for HTTP-phase boundaries and the journey end.
6. **Seed all, then sync once.** You *could* sync-and-verify after each append, but it adds execution time for little value; append the full set, then sync.
7. **Respect the 6-minute GAS ceiling / start clean-room.** Batch input variants into one fixture (§6); split into a new scenario only when the operation model materially changes (e.g. HTTP phase vs. Playwright phase). Let the act sequence build state; don't encode incidental preconditions.

### 16.4 The static test contact list

A single fixture supplies the testing user's directory/contacts stand-in. It drives two things at once: the **expected assignee name** and whether **`@create` autocomplete is expected to fire**.

```python
TEST_CONTACTS = {
    "minister@northlakeuu.org":   "Northlake Minister",
    "sdonaldson@northlakeuu.org": "Stuart Donaldson",
    # aitest@example.com deliberately absent → exercises the username-derivation path
}
```

**Name-resolution rule** (the two paths the system itself uses, so the test *derives* the expectation rather than hand-writing it):

```
expected_name(email) = TEST_CONTACTS[email]      if email in contacts   # chip / directory path
                     = name_from_email(email)     otherwise              # "jane.smith" → "Jane Smith"
```

So `minister@…` → `Northlake Minister`; `aitest@example.com` → `Aitest`. **Autocomplete rule:** an `@create` assignee whose email is in `TEST_CONTACTS` is expected to autocomplete; absence of autocomplete is a **warning-only** observation (§16.6), not a failure.

### 16.5 The four observation surfaces

An action is observable on four surfaces. Every expectation targets one or more; the cheapest surface that can see the claim is used.

| Surface | How it's read | Cost | What an action looks like there |
|---|---|---|---|
| `DOC` | `.docx` download / scan | cheap | Floating-action paragraph: `AI-N: {chip} {text} ({status})`. **All occurrences of an id are identical** — `AI-5` may appear in several paragraphs; every occurrence carries the same canonical content. |
| `SHEET` | `.xlsx` download, scoped to docId | cheap | A row in column form (`globalId`, id, email, name, action, status, …). |
| `TRACKER` | parse the table in the `.docx` | cheap | The id always exists, but **expanded into table columns** (not a floating-action text form), with the **assignee rendered as a chip**. |
| `UI` | live Playwright DOM (sidebar card, preview card); drained via `checkpoint(STEP, on=Surface.UI)` | live; bounded poll with `within=` | Card rows, preview-card fields, status icons. **First-class drainable surface** — expectations on UI are enqueued normally; a `checkpoint(STEP, on=Surface.UI)` drains only the UI-observable subset, leaving non-UI expectations queued. Within-polling applies only to UI observations (other surfaces' `within=` is silently ignored). UI is **live-only** — drained only during the Playwright phase; INTEGRITY excludes UI (§16.7). |

**Assignee is always a chip in a synced document** — in both the floating action and the tracker table. When the test parses a synced document it splits the chip into `email` + `name` for the internal `ai` and records the origin in the **`assignee_source`** field (`chip` | `parsed`, §16.2); for an already-synced document, finding `assignee_source == parsed` (a non-chip assignee) where a chip is expected is itself a consistency error discovered during parsing.

### 16.6 Expectations and verification

The author enqueues expectations against an `ai`. Two breadths:

- **`scn.verify_all_expectations(ai)`** — the action is present and consistent across **doc + sheet + tracker (if a tracker is present)**, and its derivable properties match: action text == `ai.action`; assignee email == `ai.assignee`; assignee name == `expected_name(ai.assignee)`; status == `ai.status` (if set); id matches `ai.action_id` if set, else must be a present, valid `AI-N`; and all doc occurrences are identical (§16.5).
- **`scn.verify(ai, on=SURFACE, ...)`** — the same checks but on **one** surface only, for the cases where surfaces legitimately diverge in time (e.g. doc updated now, sheet async).

Both accept the targeting/severity options:

| Option | Meaning |
|---|---|
| `on=DOC\|SHEET\|TRACKER\|UI` | restrict to one surface (omit on `verify_all_expectations`) |
| `at=AUTO\|INTEGRITY\|"<label>"` | when to evaluate (§16.1) |
| `within="10s"` | bounded poll: keep checking a live surface until true or timeout |
| `severity=WARN` | a miss records a warning and continues, instead of failing the journey |

`scn.expect_absent(ai, on=...)` enqueues an absence/terminal expectation (e.g. no live doc action; sheet `Sync Status = Deleted`). Every expectation carries its `[uc AC#]` triage tag (§10) so a drain-time failure is self-explaining.

### 16.7 The consistency checklist (what an `INTEGRITY` checkpoint verifies)

`verify_consistency(scope=doc)` — callable standalone at any point, and run internally by every `INTEGRITY` checkpoint — checks the three authoritative surfaces {DOC, SHEET, TRACKER}, scoped to the journey's `docId`. **UI is excluded** — it is live-only and drained separately by targeted `checkpoint(STEP, on=Surface.UI)` calls (§16.5).

1. **Queued expectations are met** — the specific AIs expected are present (on DOC/SHEET/TRACKER surfaces); the tracker table is present or absent as expected.
2. **Every doc AI is internally consistent** — `action_id` present; `status` present; `assignee` email (if present) is a valid address; name is valid-for-email or empty. **Doc-specific:** the status icon is present and correct (today one icon; future: must match the status); the chip link is present and valid; all occurrences identical.
3. **Every sheet AI (scoped to this doc) is consistent** — standard column consistency. **Sheet-specific:** `globalId` present; the Document column carries the doc name and link.
4. **Every doc AI is present in the sheet.**
5. **Every sheet AI (scoped to this doc) is present in the doc.**

_(These are grouped deliberately so they can be reused as named expectation bundles; the exact field rules will be finalized against the contract source — see §16.9.)_

### 16.8 Driving the UI (the layer below the scenario)

Scenarios contain **no selectors, frames, or waits**. UI gestures are named intents on `scn.ui`; a driver/page-object layer holds the fragile knowledge (the sidebar/preview-card iframes, alt-text of icons, the busy→return timing). When Google reshuffles the card DOM, one driver method changes, not the scenarios.

**Locating a UI target.** A gesture needs an explicit target, expressed as a small descriptor — not "the action":

```python
scn.ui.locate(text=ai.action_id, occurrence=1)   # the nth occurrence of this text/id in the doc
scn.ui.locate(alt="In Progress", next=True)       # an element by alt-text, in the next area from where we are
```

- `text=` + `occurrence=` targets the *nth* occurrence of a string/id (an action id may appear many times).
- `alt=` targets an element by its alt-text (icon buttons use stable alt-text like `"In Progress"`, not pixels).
- `next=True` means "relative to where we currently are, look in the next area" (e.g. inside the preview card that just popped up). The precise scoping — and whether a popped card is reachable by DOM scan or must be waited for — is a Playwright mechanics detail for the driver layer (open item §16.10).

**Gestures and waits carry timeouts.** A gesture is `click` / `mouse-down-hold` / `hover-until-next-action`. Anything that waits for something to *appear* (the preview card) takes an explicit `timeout`. For the **tooltip**: the displayed text comes from the element's alt-text/title; if that's present in the DOM we assert it by scanning (no wait), but if it only renders inside a popped card we may need a bounded wait — this is left to the driver and flagged in §16.10.

```python
card = scn.ui.hover(scn.ui.locate(text=created.action_id, occurrence=1), timeout="5s")
scn.expect_visible(card, timeout="5s")
scn.expect_alt(scn.ui.locate(alt="In Progress", next=True), "In Progress", severity=WARN)
scn.ui.set_status(card, "In Progress")        # click; driver waits out the gray/busy state (10s)
```

**Draining UI expectations.** UI observations are first-class and drainable (§16.5). A `checkpoint(STEP, on=Surface.UI)` drains only the queued expectations observable on the live DOM, keeping non-UI expectations queued. This allows scenarios to validate rapid UI feedback (e.g. "the card returned the updated status within 10s") without triggering an expensive full-sheet INTEGRITY round-trip. The `within=` polling parameter applies only to UI — Playwright will keep checking until the expectation becomes true or `within` times out.

```python
scn.verify(created, on=Surface.UI, within="10s")            # enqueue bounded-poll expectation
scn.checkpoint(STEP, on=frozenset({Surface.UI}))            # drain UI, in-browser; keep others queued
scn.verify(created, on=SHEET, at=INTEGRITY)                 # sheet update deferred to later INTEGRITY
```

### 16.9 Support-function catalog

The author writes against a thin driver (`ScenarioSession`, "scn") plus standalone assertion helpers; the driver owns lifecycle, fixture invocation, captures, and `ai`-state accumulation, but **not** assertion logic (§15). The catalog below is the **as-built API** implemented in `scn/session.py`. Reuse hints are retained for traceability.

**Lifecycle**

| Function | Purpose | Implemented as |
|---|---|---|
| `ScenarioSession.new_doc(settings)` | Create the isolated journey doc (empty-create, §16.11 #1); register for teardown. | a `begin_journey_session` fixture exists; point it at `DocumentApp.create` rather than the clone path. |
| `scn.close()` | Trash the journey doc; assert the expectation queue is empty. | `end_journey_session`. |

**Acts (state mutations — one entry point each)**

| Act | Entry point | Sync scenario |
|---|---|---|
| `scn.append_paragraph(ai.as_text())` | doc paragraph insert (no action implied until sync) | — |
| `scn.insert_tracker()` | tracker insert/refresh | — |
| `scn.sync()` | `syncDocument` via doPost — bidirectional reconcile | C |
| `scn.edit_sheet(ai, **fields)` | sheet-cell edit (Dirty stamp, sheet-wins) | B |
| `scn.set_status(ai, status)` | sidebar status action | A |
| `scn.delete(ai)` | sidebar delete | — |
| `scn.ui.create_action(ai)` | `@`-menu Create-action form (autocomplete per §16.4) | — |
| `scn.ui.hover` / `set_status` / gestures | live preview-card interaction (§16.8) | — |

> Document-text deletion (removing the `AI-N:` paragraph) and the `syncAll` sweep are **distinct entry points** with their own acts when those journeys are written.

**Write-route semantics (resolved, §16.11).** `edit_sheet`, `set_status`, and `delete` address their target row by `globalId` (#3). `edit_sheet` over the API/fixture path replicates `onActionSheetEdit`'s Dirty + Date-Modified stamp so the act faithfully simulates a user edit (#2); the same gesture driven through the Playwright UI fires the real trigger and needs no replication. `sync()` blocks until the script-properties message queue drains, so a following `sync()` is how the scenario forces an async act (a sidebar `set_status`) to convergence (#4).

**Queries (read, no mutation)** — `scn.doc_items()`, `scn.sheet_rows()` (docId-scoped), `scn.find_sheet_actions()`, `scn.verify_consistency(scope=doc)` (§16.7; also run by `INTEGRITY`).

**Expectation + checkpoint** — `scn.verify_all_expectations(ai, *, at=…)`, `scn.verify(ai, on=…, at=…, within=…, severity=…)`, `scn.expect_absent(ai, on=…, at=…)`, `scn.checkpoint(STEP|INTEGRITY, label=None)`.

### 16.10 Clean worked example — the canonical journey

This is the journey from the human-level notes, restructured. Each act maps to one entry point; each expectation states intent on the `ai`. It exercises Sync Scenarios C, B/A, and the editor UI; it is **representative, not exhaustive**. **Implemented as `tests/test_journey.py` (GTaskSheet-5vwu.13).** See test file header for documented deviations D1–D3.

```python
@pytest.fixture(scope="module")
def scn(settings):
    s = ScenarioSession.new_doc(settings)     # blank journey doc
    yield s
    s.close()                                  # trash; assert queue empty


def test_journey(scn):
    # ── Act 1 — author types four AI lines into a blank doc ───────────────────
    #   status left UNSET on plain items (a user types no status unless non-default)
    unassigned = ai(action="This tag and text confirms creation of an unassigned action item")
    with_email = ai(action="This tag and email address along with this text …",
                    assignee="aitest@example.com")
    explicit_5 = ai(action="This tag and text … pre-assigning the specific ID.", action_id="AI-5")
    domain_usr = ai(action="This tag, email and text …",
                    assignee="minister@northlakeuu.org", action_id="AI-9")
    started_ip = ai(action="An action the author starts in progress", status="In Progress")  # non-default path

    for a in (unassigned, with_email, explicit_5, domain_usr, started_ip):
        scn.append_paragraph(a.as_text())     # pure doc mutation; no action implied yet

    # ── Act 2 — sync converts the lines into actions (Scenario C) ─────────────
    scn.sync()

    # pin what we expect the conversion to produce, then verify across surfaces
    unassigned.status = "Open"; with_email.status = "Open"        # tokenless → detected Open
    explicit_5.status = "Open"; domain_usr.status = "Open"
    unassigned.action_id = "AI-1"; with_email.action_id = "AI-2"  # expected auto-assignment
    # explicit_5 / domain_usr already carry AI-5 / AI-9; started_ip keeps In Progress
    for a in (unassigned, with_email, explicit_5, domain_usr, started_ip):
        scn.verify_all_expectations(a)        # doc+sheet (+tracker if present); text/email/name/id/status
    scn.verify_consistency(scope=DOC)         # the §16.7 checklist, this doc only
    scn.checkpoint(INTEGRITY)                 # capture docx+xlsx; drain the above

    # ── Act 3 — insert the tracker table and re-sync ──────────────────────────
    scn.insert_tracker()
    scn.sync()
    for a in (unassigned, with_email, explicit_5, domain_usr, started_ip):
        scn.verify(a, on=TRACKER)             # column form; assignee as chip
    scn.checkpoint(STEP)

    # ── Act 4 — @create through the editor UI (Playwright phase begins) ───────
    created = ai(action="Creating an action via the @- trigger",
                 assignee="sdonaldson@northlakeuu.org")
    scn.ui.create_action(created)             # fills @-menu form; autocomplete expected (in TEST_CONTACTS)
    # action_id left UNSET — next id is ambiguous after AI-1,2,5,9; just verify a valid AI-N landed
    scn.verify(created, on=DOC, status="Open")                    # cheap doc probe, now
    scn.verify(created, on=SHEET, status="Open", at=INTEGRITY)    # async sheet write → defer

    # ── Act 5 — hover the chip, read the preview card, change status ──────────
    card = scn.ui.hover(scn.ui.locate(text=created.action_id, occurrence=1), timeout="5s")
    scn.expect_visible(card, timeout="5s")
    scn.expect_alt(scn.ui.locate(alt="In Progress", next=True), "In Progress", severity=WARN)

    scn.ui.set_status(card, "In Progress")    # click; driver waits out gray/busy (≤10s)
    created.status = "In Progress"
    scn.verify(created, on=Surface.UI, within="10s")            # enqueue; bounded live poll
    scn.checkpoint(STEP, on=frozenset({Surface.UI}))            # drain UI live, in-browser
    scn.verify(created, on=SHEET, at=INTEGRITY)                 # durable, async (13–60s) → defer

    # ── Final reconcile (HTTP phase) — settle every deferred expectation ──────
    scn.checkpoint(INTEGRITY)                 # docx+xlsx+tracker+consistency; queue empty at close
```

Why this reads well: every act is one entry point; the author only ever fills in or pins fields on an `ai` and the model derives the rest (auto id, assignee name); cheap single-surface `verify(on=…)` probes carry the Playwright phase while the expensive `INTEGRITY` reconciliations sit at the HTTP boundaries; and the closing `INTEGRITY` drains every deferred (`at=INTEGRITY`) expectation — the `created` action's durable sheet state included — so nothing declared goes unverified.

### 16.11 Resolved decisions

These were open when the model was drafted; all are now decided (SD, 2026-05-30). Where a mechanical detail still belongs in `DESIGN.md` / `src/ContractSchema.js` it is noted, but the design decision below is binding and this document consumes it.

1. **`new_doc` — empty-create.** The journey doc is a guaranteed-clean empty doc (`DocumentApp.create`), never a clone of a pre-populated template. No reset step is needed between runs. (Consistent with §15 *Document initialization*.)

2. **`edit_sheet` stamping — path-dependent.** A sheet edit driven through the **Playwright UI** fires the real `onActionSheetEdit` trigger, so the test does nothing extra. A sheet edit driven through the **API/fixture** path must replicate `onActionSheetEdit`'s Dirty + Date-Modified stamp, because the act simulates a user making that change — and doPost writes otherwise suppress the trigger (DESIGN.md §Programmatic Write Suppression).

3. **Write-route stable id — `globalId`.** `edit_sheet`, `set_status`, and `delete` address the target row by `globalId`, not physical row index (simpler and stable across re-sorts).

4. **`set_status` convergence — `sync()` drains the queue.** `scn.sync()` blocks until the script-properties message queue has drained before returning. An async act (e.g. a sidebar status change) is forced to convergence by a following `sync()`; the act itself need not block.

5. **Naming — confirmed.** `as_text()`, `verify()`, and `verify_all_expectations()` are the final names.

6. **Chip-vs-parsed assignee — an `ai` field.** The `ai` records whether the assignee email/name came from a chip vs. parsed leading-email text, in a field on the object (`assignee_source`, §16.2 / §16.5).

7. **Consistency-group reuse — accepted as-is for now.** The §16.7 groups stand as the working expectation bundles; their exact field rules finalize against the contract source when needed.

8. **Tooltip / popped-card observability — driver layer.** Confirmed: deferred to the Playwright driver / page-object layer (§16.8). Not a scenario-level concern.

9. **Partial-drain granularity — per-surface.** A checkpoint drains a multi-surface expectation **per surface** (mark the sheet satisfied now, keep the doc queued); a pinned `at=INTEGRITY` expectation is never partially drained early and is evaluated whole at the boundary.

---

## §17 — Known Enhancement Candidates

Coverage gaps identified in `docs/atdd/scenario-testing-review-2026-05-29.md` not yet in any journey. These are future work items, not defects in the current implementation.

### P0 — Entry-point coverage invariant violations

- **P0-1 (doc-initiated deletion):** removing an `AI-N:` paragraph in-doc, then syncing — verifies orphan reconciliation code path. Not in `test_journey.py`.
- **P0-2 (whole-doc deletion / orphaned rows):** deleting the entire doc or all its actions, verifying `syncAll` stamps `Doc Not Found` / `Deleted` correctly. Highest user-risk path; not in any current journey.

### P1 — Entry-point coverage gaps

- **P1-1 (`syncAll` sweep as call-site):** `syncAll()` (the 30-min time-based trigger) must be exercised end-to-end as the call-site, not only via `syncDocument`. Violates the entry-point coverage invariant until addressed.
- **P1-2 (live `onActionSheetEdit` trigger):** Acts 4–5 skip when the add-on test deployment is not installed; a dedicated `[TST]` journey should exercise the real installable trigger as a call-site.
- **P1-3 (full status lifecycle):** `In Progress → Done` and reopen paths not yet covered.

### P2 — Structural improvements (deferred)

- **Invariant-based assertions** at `INTEGRITY` checkpoints (1:1 doc-row pairing, no duplicate `globalId`, deleted/done actions match tracker).
- **Non-fatal failure mode** so a mid-journey failure records the defect but continues to accumulate observations for later acts.
- **Doc-scoped invariant assertions:** the ActionSheet accumulates rows across test runs; assertions must scope to the journey doc's `globalId` space.

_Track as bd issues when the next journey extension begins._