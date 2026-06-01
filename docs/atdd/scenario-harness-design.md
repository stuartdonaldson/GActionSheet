# Scenario Harness Design — Python Architecture + Checkpoint-Engine Algorithm

_Bead GTaskSheet-5vwu.1 (`model:opus`, design-only). Deliverable: the written spec that lets the
epic's build beads (`.3 .4 .5 .6 .7 .10 .13`) be authored from a clean context. No production
harness code is written here; no GAS implementation was read._

---

## 1. Scope & sources

This note is the **harness build specification**. It consumes the canonical scenario-author model
in `docs/atdd/atdd-lifecycle.md` **§16** and turns it into a concrete Python package: a module
layout, typed signatures for every §16.9 catalog entry, and — the deepest piece — the
**expectation/checkpoint engine algorithm** (§4).

This note is **not** the scenario-author model. How a scenario *reads* (the `ai` vocabulary, the
three primitives, the worked journey) stays in §16, which is canonical and supersedes §15 naming
(`append_paragraph`/`sync`/`edit_sheet`/`as_text`/`verify`/`verify_all_expectations`). Where §16 and
§15 conflict, §16 wins; §15 is retained only for its contract-ownership and conflict-resolution
detail.

Sources consulted: `docs/atdd/atdd-lifecycle.md` §16 (canonical) + §15 (background),
`src/ContractSchema.js`. §16 vocabulary and the §16.11 resolved decisions are honored verbatim.

**Authoritative-contract rule (from §15).** The harness never restates field tables. Shared shapes
(sheet columns, route names, model names) come from `src/ContractSchema.js` via its JSON export
(bead `.3`); human-readable semantics come from `docs/DESIGN.md`. This note names *which* contract
each module consumes, not the field lists themselves.

---

## 2. Package / module layout

A single `scn/` package (the author-facing driver is the object `scn`). Each module is the
deliverable of exactly one build bead, so the beads partition cleanly with no shared code surface
beyond the contract:

| Module | §16.9 area covered | Build bead |
|---|---|---|
| `scn/ai.py` | the `ai` object, `as_text()`, `assignee_source` (§16.2) | `.4` |
| `scn/contacts.py` | `TEST_CONTACTS`, `expected_name()`, `name_from_email()` (§16.4) | `.4` |
| `scn/engine.py` | expectation queue + checkpoint drain (§16.1, §16.6) | `.5` |
| `scn/surfaces.py` | DOC (`.docx`), SHEET (`.xlsx`, docId-scoped), TRACKER readers (§16.5) | `.6` |
| `scn/session.py` | `ScenarioSession`: lifecycle, acts, queries, expectation delegation (§16.9) | `.7` |
| `scn/ui.py` | the `scn.ui` page-object driver (§16.8) | `.10` |
| `scn/contract.py` | loads the ContractSchema JSON export; exposes headers/columns/routes | `.3` |
| `scn/assertions.py` | standalone per-surface assertion helpers | `.5` (consumed by `.7`) |
| `tests/test_journey.py`, `tests/conftest.py` | the §16.10 journey + module-scoped `scn` fixture | `.13` |

**Ownership rule (from §15).** `ScenarioSession` owns lifecycle, fixture invocation, surface
captures, and `ai`-state accumulation — it does **not** own assertion logic. Evaluation lives in
`engine.py` (the drain procedure) and `assertions.py` (the per-surface comparisons). `session.py`'s
expectation methods are thin enqueuers that hand an `Expectation` to the engine; nothing is asserted
until a checkpoint drains.

**Dependency direction.** `session` → `engine` → (`assertions`, `surfaces`, `contacts`);
`ai` and `contract` are leaf modules depended on by everything; `ui` is depended on only by
`session` (exposed as `scn.ui`). No cycles.

---

## 3. Concrete signatures for every §16.9 catalog entry

Names are verbatim from §16 (§16.11 #5 froze `as_text`, `verify`, `verify_all_expectations`).
Type hints are illustrative of intent, not a binding annotation style for the build beads.

### 3.0 Enums and type aliases (`scn/engine.py`, re-exported from `scn/__init__.py`)

```python
class Surface(Enum):  DOC = "DOC"; SHEET = "SHEET"; TRACKER = "TRACKER"; UI = "UI"
class CheckpointKind(Enum):  STEP = "STEP"; INTEGRITY = "INTEGRITY"
class Severity(Enum):  FAIL = "FAIL"; WARN = "WARN"

# Evaluation target (§16.1). AUTO and INTEGRITY are sentinels; a str is a checkpoint label.
AUTO = object()                      # drain at the earliest checkpoint that can observe it
INTEGRITY_TARGET = CheckpointKind.INTEGRITY   # skip STEPs; evaluate at the next INTEGRITY
Target = Union[type(AUTO), CheckpointKind, str]
```

A synthetic `CONSISTENCY` pseudo-surface (globalId linkage, doc⇄sheet presence parity) is observed
**only** by `INTEGRITY` (§4). It is internal to the engine, not part of the author-facing `Surface`.

### 3.1 The `ai` object — `scn/ai.py` (§16.2)

```python
@dataclass
class ai:
    action: str
    assignee: str | None = None          # email
    action_id: str | None = None         # "AI-N"
    status: str | None = None            # free text; token rendered only if set (§16.2 status rule)
    assignee_source: str | None = None   # "chip" | "parsed"; set by readers on read-back, unset when authored

    def as_text(self) -> str: ...        # §16.2 rendering table + trailing "({status})" iff status set
```

`as_text()` truth table (§16.2): `action`→`AI: {action}`; `+assignee`→`AI: {assignee} {action}`;
`+action_id`→`AI-{N}: …`; all four→`AI-{N}: {assignee} {action}`; append ` ({status})` iff
`status` is set. The author types no raw doc text and never hand-writes a derived name.

The object is **mutable**: the author pins more fields once known (an auto-assigned `action_id`
after sync, `status="Open"` so a tokenless action matches post-sync). Pinning happens *before*
enqueue — see the snapshot rule in §4.

### 3.2 Contacts / name resolution — `scn/contacts.py` (§16.4)

```python
TEST_CONTACTS: dict[str, str] = {                 # the directory/contacts stand-in
    "minister@northlakeuu.org":   "Northlake Minister",
    "sdonaldson@northlakeuu.org": "Stuart Donaldson",
    # aitest@example.com deliberately absent -> exercises the username-derivation path
}

def name_from_email(email: str) -> str: ...        # "jane.smith@x" -> "Jane Smith"
def expected_name(email: str) -> str: ...          # TEST_CONTACTS[email] if present else name_from_email(email)
def autocomplete_expected(email: str) -> bool: ... # email in TEST_CONTACTS (absence -> WARN-only, §16.6)
```

The engine derives the expected assignee name with `expected_name()` rather than the author
hand-writing it (§16.4). `autocomplete_expected` drives only a `severity=WARN` observation.

### 3.3 Lifecycle — `scn/session.py` (§16.9 Lifecycle)

```python
class ScenarioSession:
    @classmethod
    def new_doc(cls, settings) -> "ScenarioSession": ...   # empty-create (§16.11 #1); register for teardown
    def close(self) -> None: ...                            # trash the doc; ASSERT the expectation queue is empty
```

`new_doc` creates a guaranteed-clean empty doc — never a clone (§16.11 #1).
_Reuse hint (non-binding):_ a `begin_journey_session` fixture exists; point it at `DocumentApp.create`
rather than the clone path. `close` _(non-binding: `end_journey_session`)_ trashes the doc and
enforces the drain invariant (§4): a non-empty queue at close is a failure.

### 3.4 Acts — `scn/session.py` (§16.9 Acts; one entry point each, §16.3 #1)

```python
def append_paragraph(self, text: str) -> None: ...         # doc paragraph insert; no action implied until sync
def insert_tracker(self) -> None: ...                      # insert/refresh tracker; sets self.tracker_present = True
def sync(self) -> None: ...                                # syncDocument via doPost; BLOCKS until the
                                                           #   script-properties msg queue drains (§16.11 #4)
def edit_sheet(self, target: ai, **fields) -> None: ...    # sheet-cell edit; addressed by globalId (§16.11 #3);
                                                           #   API path replicates Dirty + Date-Modified (§16.11 #2)
def set_status(self, target: ai, status: str) -> None: ... # sidebar status action (async; converges on next sync)
def delete(self, target: ai) -> None: ...                  # sidebar delete; addressed by globalId
# UI acts live on scn.ui (§3.8)
```

- `sync()` is the convergence primitive (§16.11 #4): an async act (`set_status` via sidebar) is
  forced to convergence by a following `sync()`; the act itself need not block.
- `edit_sheet`/`set_status`/`delete` all address their target row by `globalId` (§16.11 #3), read
  from the `ai`'s synced state (the `ai` must already carry an `action_id`/`globalId` linkage from a
  prior read). On the API/fixture path `edit_sheet` replicates `onActionSheetEdit`'s Dirty +
  Date-Modified stamp because doPost writes otherwise suppress the trigger (§16.11 #2; DESIGN.md
  §Programmatic Write Suppression). Driven through the Playwright UI the real trigger fires and no
  replication is needed.
- `insert_tracker()` flips `self.tracker_present`, which widens the surface set of subsequent
  `verify_all_expectations` calls (§4).

### 3.5 Queries — `scn/session.py` (§16.9 Queries; read, no mutation)

```python
def doc_items(self) -> list[ai]: ...                       # parse floating actions from the .docx (DOC surface)
def sheet_rows(self) -> list[ai]: ...                      # download .xlsx, parse rows, SCOPED to this docId
def find_sheet_actions(self) -> list[ai]: ...              # current-doc sheet rows via webapp/fixture route
def verify_consistency(self, scope=Surface.DOC) -> dict: ...# the §16.7 checklist, docId-scoped; also run by INTEGRITY
```

All reads are docId-scoped (§16.3 #4): the ActionSheet accumulates rows across runs and `globalId`
carries the doc prefix, so doc-scoping is the clean filter. Readers return `ai`-shaped records
(§3.7) the engine compares against the snapshot. `verify_consistency` is callable standalone and is
the data source for the `CONSISTENCY` pseudo-surface at INTEGRITY.

### 3.6 Expectation + checkpoint API — `scn/session.py` thin enqueuers → `scn/engine.py`

```python
def verify_all_expectations(self, target: ai, *, at: Target = AUTO,
                            severity=Severity.FAIL) -> None: ...
def verify(self, target: ai, *, on: Surface, at: Target = AUTO,
           within: str | None = None, severity=Severity.FAIL, **field_overrides) -> None: ...
def expect_absent(self, target: ai, *, on: Surface, at: Target = AUTO) -> None: ...
def checkpoint(self, kind: CheckpointKind, *, on: Surface | set[Surface] | None = None,
               label: str | None = None) -> None: ...
```

- `verify_all_expectations(ai)` — present-and-consistent across **doc + sheet (+ tracker if a
  tracker is present)**; derivable props match (text==`ai.action`, email==`ai.assignee`,
  name==`expected_name(ai.assignee)`, status==`ai.status` if set, id==`ai.action_id` if set else any
  valid `AI-N`, all doc occurrences identical) (§16.6). Surface set computed at enqueue (§4).
- `verify(ai, on=…)` — the same checks on **one** surface (for legitimate cross-surface timing
  divergence). `**field_overrides` (e.g. `status="Open"`) override the snapshot for that surface
  only (§16.10 Act 4).
- `expect_absent(ai, on=…)` — absence/terminal expectation (no live doc action; sheet
  `Sync Status = Deleted`) (§16.6).
- `checkpoint(kind, on=…, label=…)` — drain point (§4). `on` overrides a STEP's read surface set;
  `label` names this checkpoint so an `at="<label>"` expectation can target it.
- Every enqueuer attaches the `[uc AC#]` triage tag (§16.6/§10) so a drain-time failure is
  self-explaining. (Tag source: passed by the author or derived from the calling test id — finalize
  in `.7`.)

### 3.7 Surface readers — `scn/surfaces.py` (§16.5)

```python
class DocReader:      # .docx download/scan -> floating-action ai's; sets assignee_source from chip vs text
    def read(self, docx_path, doc_id) -> list[ai]: ...
class SheetReader:    # .xlsx download -> ai's; columns via contract; SCOPED to doc_id
    def read(self, xlsx_path, doc_id) -> list[ai]: ...
class TrackerReader:  # parse the tracker table in the .docx -> ai's (assignee rendered as chip)
    def read(self, docx_path, doc_id) -> list[ai]: ...
```

Each returns `ai`-shaped records. The reader sets `assignee_source` (`chip`|`parsed`) on read-back
(§16.5): in a synced document the assignee is always a chip, so `assignee_source == "parsed"` where
a chip is expected is itself a consistency error, discovered during parsing and surfaced at
INTEGRITY. Column mapping comes from `scn/contract.py` (contract export), never restated here.

### 3.8 UI driver — `scn/ui.py` (§16.8)

```python
class UiDriver:                       # exposed as scn.ui; owns selectors/frames/waits (scenarios hold none)
    def locate(self, *, text=None, alt=None, occurrence=1, next=False) -> Locator: ...
    def create_action(self, target: ai) -> None: ...          # @-menu Create-action form; autocomplete per §16.4
    def hover(self, locator, *, timeout: str) -> Card: ...     # returns the popped preview card
    def set_status(self, card, status: str) -> None: ...       # click; driver waits out gray/busy (<=10s)

# UI expectations (enqueued on the session, evaluated only on the UI surface, live mid-session):
def expect_visible(self, card, *, timeout: str) -> None: ...
def expect_alt(self, locator, text: str, *, severity=Severity.FAIL) -> None: ...
```

`locate` descriptors: `text=`+`occurrence=` → the nth occurrence of a string/id; `alt=` → element
by alt-text; `next=True` → relative to current position (e.g. inside the just-popped card). Tooltip
/ popped-card observability mechanics are the driver's concern (§16.11 #8), not scenario-level.

---

## 4. The engine — expectation queue + checkpoint drain (deepest piece)

`scn/engine.py`. This is the AC's "precise drain procedure." An expectation is verified **only**
when a checkpoint that can observe it drains it (§16.1).

### 4.1 The `Expectation` record — the per-surface partial-drain carrier

```python
@dataclass
class Expectation:
    seq: int                          # monotonic enqueue order (drain is evaluated in this order)
    expected: dict                    # SNAPSHOT of ai fields at enqueue + explicit field_overrides
    surfaces: frozenset[Surface]      # claim set (see 4.3)
    remaining: set[Surface]           # surfaces not yet drained  <- partial-drain state, starts == surfaces
    target: Target                    # AUTO | CheckpointKind.INTEGRITY | "<label>"
    kind: str                         # "PRESENT_CONSISTENT" | "ABSENT"
    within: str | None                # bounded poll, UI only
    severity: Severity
    needs_consistency: bool           # True for verify_all_expectations -> adds the CONSISTENCY obligation at INTEGRITY
    tag: str                          # [uc AC#]
```

The queue is an ordered list of live `Expectation`s. An expectation leaves the queue only when
`remaining` becomes empty (and, for `verify_all_expectations`, its `CONSISTENCY` obligation has been
discharged at an INTEGRITY).

### 4.2 Snapshot rule (non-obvious — state explicitly)

`expected` is a **deep copy of the relevant `ai` fields taken at enqueue time**, merged with any
explicit `field_overrides`. Later mutation of the `ai` does **not** retroactively change a queued
expectation. This is precisely why the §16.10 journey pins (`ai.status = "Open"`,
`ai.action_id = "AI-1"`) *before* calling `verify_all_expectations`: the pin must be visible to the
snapshot. It also resolves the apparent tension between "`ai` is mutable" (§16.2) and queued
verification — mutability is for *authoring*; the queue captures intent at the moment of enqueue.

### 4.3 Surface-set (`surfaces`) computation at enqueue

| Enqueuer | `surfaces` |
|---|---|
| `verify_all_expectations(ai)` | `{DOC, SHEET}` ∪ (`{TRACKER}` iff `session.tracker_present`), `needs_consistency=True` |
| `verify(ai, on=X)` | `{X}` |
| `expect_absent(ai, on=X)` | `{X}`, `kind="ABSENT"` |
| `expect_visible` / `expect_alt` | `{UI}` |

`TRACKER` is included only when a tracker has been inserted (§16.6 "tracker (if a tracker is
present)"); `insert_tracker()` sets the flag before any later enqueue widens.

### 4.4 Checkpoint observability

- **`INTEGRITY`** — captures DOC (`.docx`) + SHEET (`.xlsx`) + TRACKER and runs
  `verify_consistency` (§16.7). Observable set = **all author surfaces** *plus* the synthetic
  **`CONSISTENCY`** pseudo-surface (globalId linkage, doc⇄sheet presence parity). Expensive; never
  run mid-Playwright (§16.3 #5). Every journey ends with one.
- **`STEP`** — cheap; performs lightweight single-tier reads, runs **no** GAS consistency
  round-trip, and **cannot** observe `CONSISTENCY`. Its observable surface set `OBS` is:
  - `on=` if the author supplied it, else
  - **the union of `remaining` surfaces over the expectations drainable at this checkpoint** (those
    whose `target` is `AUTO`, or whose label == this checkpoint's `label`).

  This default is deterministic, not magic: it reconciles §16.1 ("a single `sheet_rows()` pull sees
  sheet fields but not doc/tracker/globalId") with §16.10's bare `checkpoint(STEP)` after a row of
  `verify(on=TRACKER)` — only `TRACKER` is pending under AUTO there, so the STEP reads `TRACKER`
  only.

### 4.5 The drain decision procedure

For a checkpoint `C` (kind `K`, label `L`, observable set `OBS` per §4.4), iterate pending
expectations `E` in `seq` order:

1. **Is `E` targetable at `C`?**
   - `target is AUTO` → yes.
   - `target is INTEGRITY` → yes **iff** `K == INTEGRITY`.
   - `target == "<label>"` → yes **iff** `L == target`.
   - otherwise → skip (leave `E` queued untouched).
2. **`observable_here = E.remaining ∩ OBS`.** For each surface in it, evaluate the §16.6 derivable
   checks for `E.kind` (`PRESENT_CONSISTENT` → text/email/name/status/id + all-occurrences-identical;
   `ABSENT` → the terminal/absence check) against **freshly captured** state via the §3.7 readers.
   `within` ⇒ bounded poll on the UI surface until pass or timeout.
   - pass → drop the surface from `E.remaining`.
   - fail + `severity=FAIL` → record `(tag, seq, surface, expected, actual)` and abort the journey.
   - fail + `severity=WARN` → record a warning **and still drop the surface** (so it does not dangle
     and trip the drain invariant later).
3. **INTEGRITY consistency obligation.** If `K == INTEGRITY` and `E.needs_consistency`, evaluate the
   `CONSISTENCY` checklist (§16.7) for `E` and mark it discharged (a non-chip assignee where a chip
   is expected, §16.5/§3.7, fails here).
4. **Targeting enforcement.** If `C` *is* `E`'s explicit target — `target is INTEGRITY` and
   `K == INTEGRITY`, or `target == L` — then after evaluation `E.remaining ∩ (surfaces C can
   observe)` **must be empty**; any surface it should have seen but did not pass is a failure
   ("when a checkpoint is the target the expectation must pass there", §16.1). For `AUTO`, surfaces
   not in `OBS` simply stay queued without error.
5. **Retire.** If `E.remaining == ∅` (and the consistency obligation, if any, is discharged) →
   remove `E` from the queue.

### 4.6 The drain invariant (§16.1)

- A `STEP` may leave expectations queued (observability or forward-targeting).
- An `INTEGRITY` may **not** leave any *observable + AUTO/INTEGRITY-targeted* expectation undrained:
  step 4 enforces it for INTEGRITY-targeted ones; AUTO ones are fully observable at INTEGRITY and so
  must drain.
- A label-pinned expectation whose labeled checkpoint never runs rides to `close()`.
- **`close()` requires an empty queue.** A non-empty queue at teardown is a **test failure**
  (an expectation nobody verified), reported as a list of dangling `(seq, remaining surfaces, tag)`.
  Therefore every journey ends with an `INTEGRITY`, and any expectation a `STEP` could not see rides
  the queue to it.

### 4.7 Per-surface partial drain — worked trace

`verify_all_expectations(ai)` (no tracker yet) enqueues **one** `E` with
`surfaces = remaining = {DOC, SHEET}`, `needs_consistency=True`, `target=AUTO`.

1. `checkpoint(STEP, on=SHEET)` → `OBS={SHEET}`; `observable_here = {DOC,SHEET} ∩ {SHEET} = {SHEET}`.
   SHEET checks pass → `remaining = {DOC}`. `E` stays queued (not empty; STEP can't run consistency).
2. `checkpoint(INTEGRITY)` → `OBS = {DOC,SHEET,TRACKER,CONSISTENCY}`;
   `observable_here = {DOC}` drains the DOC obligation → `remaining = ∅`; the `CONSISTENCY`
   obligation runs and discharges → `E` retired.

The single multi-surface expectation drained **across two checkpoints, one surface at a time** —
this is the per-surface partial drain. (Citation note: the bead cited "§16.11 #9"; §16.11 has eight
items and none is named this. The mechanism is the §16.1 *observability* rule — "drain what's
observable, leave the rest queued" — applied to a multi-surface `verify_all_expectations`. Recorded
so siblings don't chase a nonexistent §16.11 #9.)

---

## 5. How the §16 pieces plug into the engine

- **`ai` (§16.2, incl. `assignee_source`).** Authored `ai`s leave `assignee_source` unset; readers
  (§3.7) set it on read-back. The engine compares the snapshot's derivable props against the read
  `ai`; a `parsed` source where a chip is expected fails the consistency obligation at INTEGRITY
  (§16.5).
- **Surface readers (§16.5).** `DocReader`/`SheetReader`/`TrackerReader` return `ai`-shaped records;
  the engine's per-surface step (§4.5 #2) compares them to `E.expected`. All reads docId-scoped
  (§16.3 #4). Column/route knowledge comes from `scn/contract.py`.
- **`TEST_CONTACTS` (§16.4).** The engine derives the expected assignee *name* via `expected_name()`
  instead of the author hand-writing it; `autocomplete_expected()` only yields `severity=WARN`
  observations during `ui.create_action`.
- **`verify` / `verify_all_expectations` (§16.6).** Thin enqueuers (§3.6): build an `Expectation`
  (snapshot + surface set + target/severity + tag) and push it. **No evaluation at enqueue** —
  everything happens at drain. `verify_consistency` (§16.7) is both an author-callable query and the
  data source the INTEGRITY consistency obligation consumes.

---

## 6. The §16.10 canonical journey traced through the engine

Proof the model executes the canonical journey. `Q:` shows the queue (by `ai`/surface) after each
act/checkpoint.

- **Act 1 — append 5 paragraphs.** Pure DOC mutations; no expectations. `Q: ∅`.
- **Act 2 — `sync()`; pin status/ids; `verify_all_expectations(a)` ×5; `verify_consistency(DOC)`;
  `checkpoint(INTEGRITY)`.** Each `verify_all_expectations` snapshots the just-pinned `ai`
  (`status="Open"`, expected `action_id`) → 5 expectations, `surfaces={DOC,SHEET}` (no tracker yet),
  `needs_consistency=True`. `Q:` 5×{DOC,SHEET}. INTEGRITY observes all → DOC+SHEET drain, consistency
  discharges → `Q: ∅`. (The snapshot rule §4.2 is why the pins must precede the calls.)
- **Act 3 — `insert_tracker()` (sets `tracker_present`); `sync()`; `verify(a, on=TRACKER)` ×5;
  `checkpoint(STEP)`.** 5 expectations, `surfaces={TRACKER}`, `target=AUTO`. Bare STEP → `OBS` =
  union of drainable `remaining` = `{TRACKER}`; all 5 TRACKER obligations drain → `Q: ∅`. (Shows the
  §4.4 default reproducing §16.10's bare `checkpoint(STEP)`.)
- **Act 4 — `ui.create_action(created)`; `verify(created, on=DOC, status="Open")`;
  `verify(created, on=SHEET, status="Open", at=INTEGRITY)`.** First is AUTO `{DOC}`; with no
  checkpoint before Act 5 it rides forward. Second is INTEGRITY-targeted `{SHEET}`, snapshot status
  `"Open"`. `Q:` `created`/{DOC,AUTO}, `created`/{SHEET,INTEGRITY,Open}.
- **Act 5 — hover/preview UI expectations; `set_status` → `created.status="In Progress"`;
  `verify(created, on=UI, within="10s")`; `verify(created, on=SHEET, at=INTEGRITY)`.** UI
  expectations evaluate live within the bounded poll (UI surface valid mid-session). The SHEET
  expectation snapshots status `"In Progress"`, INTEGRITY-targeted. `Q:` adds `created`/{UI},
  `created`/{SHEET,INTEGRITY,"In Progress"}.
- **Final `checkpoint(INTEGRITY)`.** Drains the deferred DOC probe and the SHEET expectations;
  consistency runs; `Q: ∅` at `close()`.

**Flag for bead `.13` (Coordination Log).** Act 4 and Act 5 both enqueue
`verify(created, on=SHEET, at=INTEGRITY)` but with **conflicting** snapshot status — `"Open"` then
`"In Progress"` — and with only the final INTEGRITY downstream of both, both target the **same**
checkpoint. The engine semantics are well-defined (`at=INTEGRITY` = the next INTEGRITY after enqueue;
both snapshots are immutable per §4.2), so at the final INTEGRITY the sheet shows `In Progress` and
the Act-4 `"Open"` SHEET obligation **fails**. This is a *journey-modeling* issue, not an engine
defect: `.13` must resolve it (place an intermediate INTEGRITY between Acts 4 and 5, or drop the
stale Act-4 SHEET/Open probe — the DOC/Open probe already covers the immediate create).

---

## 7. Contract observations (deferred — recorded, not acted on)

Per the bead's scope decision this note does **not** edit `src/ContractSchema.js`. The following
implied-shape findings are recorded here and in the epic Coordination Log for bead `.3`
(ContractSchema → JSON export + Python loader) and the build beads:

1. **`doc_id` / `doc_name` are derived, not stored.** `CONTRACT_SCHEMA.sheetAction.fields` lists 12
   fields but `headers`/`columnsByField` map only 10 columns; `doc_id` and `doc_name` are **not**
   columns — both derive from `document_formula` (col 7, a hyperlink formula). `SheetReader` (§3.7)
   must parse the doc id and name out of that formula. `.3` should make the derivation explicit in
   the export/loader (or annotate the contract).
2. **No route for `edit_sheet` / `find_sheet_actions`.** `webApp.routeNames` has no entry matching
   the `edit_sheet` act or the `find_sheet_actions` query. The act→route mapping must resolve one
   (candidates: `upsert_action_rows`, the generic `run_fixture`, or a new route). This is the §15
   "still-open #3" question — whether doc/sheet reads are exposed only via `doPost()` routes or also
   via fixture-only entry points. Route to `docs/DESIGN.md` / `src/ContractSchema.js` when `.7`/`.6`
   are built.
3. **Citation fix.** The bead's "per-surface partial drain (§16.11 #9)" points at a nonexistent
   item — §16.11 has eight resolved decisions. The mechanism is the §16.1 observability rule applied
   to multi-surface `verify_all_expectations` (see §4.7). Recorded so siblings don't search for a
   §16.11 #9.

---

_End of design note. Build beads `.3 .4 .5 .6 .7 .10 .13` are authorable from §2–§6; §7 lists the
contract resolutions they must make._
