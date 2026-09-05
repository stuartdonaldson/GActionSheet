# Standard-Docs.md — Google Docs creation, copy, and mutation inventory

**Scope:** every location in this repo (test harness, GAS fixture routes, exporter code,
apt tooling) that creates, copies, renames, or otherwise mutates a real Google Doc — plus
every existing standard/template doc the suite relies on, and (§6) *why* each mutation is
isolated to its own doc vs. shared across a module/session/corpus sweep. Built to speed up
future analysis of doc-lifecycle behavior; treat this as an index, not a tutorial — follow
the file:line references into the actual code before relying on details.

Companion project memory: `bd remember --key standard-docs-inventory` points here.

---

## 1. Existing standard/template docs (config-referenced)

Four permanent, human-maintained docs exist, **all now defined in `local.settings.json`**
(and documented with `_note_*` entries in `local.settings.example.json`, plus a single
`_note_standardDocs` entry there pointing back to this file). They serve different
purposes and must not be conflated despite similarly-shaped config keys.

**2026-09-03 cleanup:** `copyFidelitySourceDocId` used to be a hardcoded constant
(`REFERENCE_DOC_ID`) inside `tests/test_floating_action_copy_fidelity.py`, one letter-case
away from the unrelated `referenceDocId` config key and with the opposite mutation
semantics (stable/read-only vs. mutated-in-place). It is now a config key like the other
three, read via the existing `settings` pytest fixture inside the `synced_copy` fixture
(`tests/test_floating_action_copy_fidelity.py`) and threaded through
`SimpleNamespace.reference_doc_id` to the test methods that need it.

| Config key | Location | Doc ID | Purpose | Mutated directly? |
|---|---|---|---|---|
| `testDocId` | `local.settings.json` | `11jA0FMowlJbyxyJoK6bePVvcO63niVrKcXA0eMJW1F4` | **Master session template.** Cloned once per pytest session. | No — only its clone is touched |
| `exportTestDocId` | `local.settings.json` | `1zQkRAczbRjB0iRD2OhpHsqXvHsmskE8VI7VNx8vE5yE` | Default export source for manual CLI (`scripts/export_gas.py`) and `test_document_export.py`. | No |
| `referenceDocId` | `local.settings.json` | `1PYIU022o5dWNhIkyErjUzF6TRg--r4QrH-h-JbPNO-E` | Canonical Action-Portable-Text (APT) reference doc for the `apt` round-trip tooling. | **Yes** — `decode_reference_document` clears and rewrites its body |
| `copyFidelitySourceDocId` | `local.settings.json` | `1h4QuL7mZVybEj6T4QHAAqk8LMoyNGj0fT9XVTHVs9_E` | Copy-fidelity source doc, read by `tests/test_floating_action_copy_fidelity.py` — only ever cloned, never edited. | No |

### Lifecycle of the master template (`testDocId`)

`test_doc_id` fixture (`tests/conftest.py:456`) → GAS `begin_test_session`
(`src/TestFixtures.js` `beginTestSession(masterDocId)`, ~line 4607) →
`DriveApp.makeCopy()`. The clone name mirrors to `TestControl!B1` for manual debugging.
Clone is trashed at session teardown (`_end_session` finalizer).

---

## 2. Naming convention (single source of truth)

`_testDocName(purpose)` — `src/TestFixtures.js:58` — produces:

```
<configured prefix>purpose-<yyyyMMdd>-<hex4>
```

Prefix comes from the Config sheet's "Test Doc Prefix" cell (default `GActionSheet-Test-`,
via `ArchiveManager.getConfiguredTestDocPrefix`). **Every doc-creation site is required to
route through this** (or the sibling `_testDocSuffix()` for clone naming) so that
`list_test_drive_docs` and the cleanup routes can find every test artifact by one prefix
check. If you add a new creation site, use this helper — do not hand-roll a name.

---

## 3. Mutation points

### `scn/session.py` (Python test harness)
| Location | Action | Notes |
|---|---|---|
| `ScenarioSession.new_doc()` ~line 525 | Create | POSTs `begin_journey_session`; brand-new empty doc, **not** a template clone |
| `close()` / `_deferred_trash()` lines 564-609 | Trash | POSTs `end_journey_session`; registered as a **pytest finalizer**, not inline `finally:` — ordering matters so UI-failure screenshots can still capture before trash (gts-hroj). Idempotent via `self._trashed`. |

### `src/WebApp.js` (GAS webapp routes)
| Location | Route | Action | Notes |
|---|---|---|---|
| `_handleJourneySession` lines 3386-3431 | `begin_journey_session` | Create | `DocumentApp.create(_testDocName('journey'))`, moved into TEST_SHEET's parent folder |
| same | `end_journey_session` | Trash | `DriveApp.getFileById(docId).setTrashed(true)` |
| `_handleRenameDocForTest` lines 2912-2926 | `rename_doc_for_test` | Rename | `DriveApp.setName()` — **test-only**, used solely by the `gts-z6j0` export-folder-isolation collision test; never called by production code |
| `_handleSeedDocContent` lines 2881-2897 | `seed_doc_content` | Body mutation (not create/copy/rename) | `Docs.Documents.batchUpdate` — noted because it's a content-mutation route worth knowing about |

### `src/TestFixtures.js` (dispatched via `run_fixture`)
| Location | Fixture name | Action | Notes |
|---|---|---|---|
| line 2071 / 2089 | `begin_journey_session` / `end_journey_session` | Create / Trash | GAS-side mirror of the WebApp.js handler |
| lines 3225-3253 | `clone_doc_with_test_id` | Copy | `DriveApp.makeCopy()` of an arbitrary source doc (`data.docId`) into the source's own parent folder. Name: `GActionSheet-Test-clone-<suffix> [src:<name>][test:<id>]`. Read-only on source. Used by `test_floating_action_copy_fidelity.py`. |
| lines 2883-2902 | `create_canonical_reference_doc` | Create (one-time) | Creates the permanent APT reference doc |
| lines 2904-2927+ | `encode_reference_document` / `decode_reference_document` | Body mutation | Against `testDocId` or `data.docId`; **decode clears body first** before rewriting — real content-mutation point |
| line 1273 / 1304 | `discovery` / `discovery_subfolder` | Create (memoized) | Script-property-cached `DocumentApp.create()` for Drive-discovery tests (recent/stale/subfolder docs). Deliberately **never reset** by `reset_test_state` — staleness (8+ days) is the point under test. |
| line 3790 / 3798 | `trash_doc` / `untrash_doc` | Trash toggle | Direct `setTrashed()` by `docId` or `testDocId` |
| line 3816 | `purge_stale_test_docs` | Bulk archive | Backdates "Doc Not Found" rows past the 24h grace window, then runs production `ArchiveManager.archive()`. Run once per pytest session to bound corpus growth (gts-4m7l). |
| line 2547 | `list_test_drive_docs` | Read-only enumeration | Files under TEST_SHEET's parent folder matching the `GActionSheet-Test-` prefix. Used for litter audits. |
| line 3715 | `menu_cleanup_test_docs` | Bulk purge | Drives production `menuCleanupTestDocs()` → `ArchiveManager.purgeByPrefix()` as a real entry-point call-site; covered by `tests/test_cleanup_test_docs.py` using a session-unique prefix so concurrent runs can't collide |
| line 2581 | `restamp_docdata_names` | Not a doc mutation | Sheet-cell repair only (rewrites DocData `Doc Name` formula) — listed to avoid false-positive greps |

### `apt` tooling (`scripts/apt.py`, `apt_lib.py`, `capture_team_actions_fixture.py`)
Does **not** create/copy/rename docs itself — it's a thin CLI over
`call_webapp.call_action("run_fixture", ...)` targeting:
- `encode_reference_document` / `decode_reference_document` against `referenceDocId` — real mutation of that one canonical doc's body.
- A fresh `ScenarioSession.new_doc()` throwaway doc in the corpus-batch tests (`test_apt_corpus_batch.py`, `test_apt_corpus_check.py`, `test_apt_create_lane.py`).

### `src/Procedure-Exporter.js` / `src/SPIKE-CommentPosition.js`
No Doc creation/copy/rename. Only `DriveApp.createFile()` / `folder.createFile()` for
export artifacts (JSON, images, PDF blobs) and export-index bookkeeping. AC(a)-(c) in
`test_document_export.py` verify: one export folder per docId, reused on repeat export,
distinct per docId even with duplicate titles.

---

## 4. Verification / checks observed near mutation points

- `test_floating_action_copy_fidelity.py` — asserts the clone (via `clone_doc_with_test_id`) faithfully preserves source content/structure before syncing and trashing it.
- `test_document_export.py` — AC(a)-(c) on export-folder identity/reuse per docId (see above).
- `test_cleanup_test_docs.py` — session-unique prefix isolation so `menu_cleanup_test_docs` can't delete another concurrent run's docs.
- `test_conftest_test_doc_id_finalizer.py` — validates the `test_doc_id` fixture's clone-then-trash finalizer behavior.
- Discovery fixtures (`discovery`, `discovery_subfolder`) rely on **not** being reset so staleness-based assertions (doc age ≥ 8 days) stay valid across runs.

## 5. Cleanup / lifecycle summary

| Mechanism | Scope | Trigger |
|---|---|---|
| `ScenarioSession._deferred_trash` | Single journey doc | pytest finalizer, per-test |
| `end_journey_session` (GAS) | Single journey doc | Called by the above |
| `test_doc_id` fixture teardown | Session master-template clone | Once per pytest session |
| `trash_doc` / `untrash_doc` fixtures | Arbitrary doc by id | Explicit test calls |
| `purge_stale_test_docs` | "Doc Not Found" backlog | Once per pytest session (gts-4m7l) |
| `menu_cleanup_test_docs` → `ArchiveManager.purgeByPrefix()` | All docs under configured test prefix | Explicit entry-point test, or manual menu action in production |

---

## 6. Isolation scope: why a mutation happens alone vs. as part of a shared scenario

Every copy/create/mutate site above lands in one of seven isolation patterns. The scope
choice is deliberate in each case — test authors write the rationale directly into the
fixture docstring/comment, quoted below rather than paraphrased. Before adding a new
doc-mutating test, find the pattern that matches your case and follow its stated reasoning
rather than defaulting to "one fresh doc per test."

### Pattern 1 — Per-test disposable doc (the default)
`ScenarioSession.new_doc()` (`scn/session.py:525`) is not itself scope-bound — it's a plain
classmethod. Isolation is a convention enforced by how test authors wrap it: normally
function-scoped, one call per test, trashed via a `request.addfinalizer` (not inline
`finally:` — trash is deliberately deferred to the teardown *phase* so a UI-failure
screenshot can still capture the doc before its Drive chrome shows "in trash"; misdiagnosed
as a product bug twice before that was understood — gts-hroj).
> `tests/test_journey.py`'s `scn` fixture: *"Function-scoped (not module) so request.node is
> the test item — required for record_property/JUnit `<property>` emission (T24)."*
> `tests/test_sidebar.py`: *"One Chromium cold start (module-scoped browser_page) amortized
> across all tests in this module... Each test gets its own scn doc (named-clone isolation,
> §16 twin-track)."* — module scope buys browser reuse only; doc isolation is preserved.
**Trade:** cleanest isolation, highest Drive-quota/setup cost per test.

### Pattern 2 — Module-shared doc, many read-only assertions
One expensive seed+sync amortized across several tests that only *read* the result —
`test_view_b.py`'s `seeded_doc`, `test_team_write_routes.py`/`test_team_portal_hardening.py`'s
`seeded_rows` (module-scoped, one doc carrying every tagged row a module's assertions need).
Where one test's mutation would corrupt the others' shared state, authors split a **second**
module-scoped doc rather than reuse:
> `test_team_portal_hardening.py`'s `dead_doc` fixture: *"A second, throwaway doc... kept
> separate from seeded_rows' doc so this doesn't also blow away every other case."*
**Trade:** cheap setup reused across a module; requires every consuming test to be
read-only against the shared doc, or a contamination bug follows.

### Pattern 3 — Module-shared doc as pure scratch vehicle (not the subject under test)
`test_admin_doc_scan.py` uses one `driver` session across a module purely to call fixture
routes that ignore the doc entirely:
> *"Those routes ignore the doc entirely (`docAlreadyClosed:true`), so minting a new real
> Google Doc for each one would only add Drive-quota cost and, without `request=...`, leak
> untracked docs (gts-hroj)."*
The doc is never itself asserted against — it exists only because the fixture-route
plumbing requires *a* doc id.

### Pattern 4 — Multi-doc sweep (behavior that only exists across multiple docs)
`test_sync_all.py`'s `sync_ctx` fixture creates **three separate docs** (`scn_mod`,
`scn_unmod`, `scn_trash`) in different row-conditions, then runs `syncAll()` once across the
whole sheet:
> *"One scenario: seed a mixed ActionSheet (invalid-doc, trashed-doc, unmodified-valid,
> modified-valid rows), run syncAll ONCE (Sweep 1), drain per-condition expectations, then
> run syncAll a SECOND time (Sweep 2) to verify Doc Not Found rows are archived."*
This is not a cost optimization — cross-row sequencing and archive-eligibility timing
**cannot be observed** from any single isolated doc. Multiple docs must coexist in the
sheet during one sweep for the behavior under test to exist at all.

### Pattern 5 — Batched multi-scenario single doc (pure speed, no cross-scenario behavior)
`tests/support/apt_lane_runner.py`'s `run_lane` composes many independent scenarios' input
corpora into **one** doc, pays `begin_journey_session`+sync+`end_journey_session` once for
the whole batch, then slices the one capture back apart per scenario:
> *"`test_apt_corpus_check.py` is the shape this replaces... one Doc per scenario, paying
> [session overhead] every time (measured there at 5.1 min for 7 scenarios). `run_lane` pays
> that cost once per lane... by composing every scenario's input corpus into ONE doc...
> and slicing the ONE capture back apart... before diffing each slice against its own
> scenario's expected corpus."*
`test_apt_corpus_batch.py` calls the old one-doc-per-scenario shape *"the anti-pattern."*
**Distinct from Pattern 4:** here scenarios are independent and share a doc purely for cost
amortization, not because the behavior under test spans docs.

### Pattern 6 — Canonical shared-mutable doc (the real risk case)
`referenceDocId` is the **one** doc the whole suite/tooling touches in place, and the
drift/race cost is named explicitly rather than papered over:
> `tests/helpers/reference_corpus.py`: *"the shared canonical reference Doc
> (`settings['referenceDocId']`)... the one Doc every other stage of
> `knowledge-base/staging/apt-oracle.md` repairs and guards by hand, and which stage
> `apt-repair` found **drifts a little more with every flush**."*
`materialize_reference_corpus()` exists specifically so lanes that need reference-shaped
*content* decode the checked-in golden into a **fresh** doc instead of touching the shared
one — enforced by an explicit test assertion:
> `test_reference_corpus_fixture.py`: *"materialize_reference_corpus must not hand back the
> shared canonical reference Doc... a lane writing to it defeats the point of this
> fixture."*
Concurrency risk is named in `knowledge-base/staging/apt-oracle.md:382`: a forced-render
call *"racing concurrent execution and did nothing — retry rather than believe `ok:true`."*
The `apt-repair`/`apt-lane-guards` staged-plan stages (gts-imai, gts-1ibp, gts-a7ko) exist
specifically to periodically detect and hand-fix drift this doc accumulates from being
shared and always-mutated. **If you're about to write to `referenceDocId` directly, stop —
use `materialize_reference_corpus()` instead.**

### Pattern 7 — Stable read-only clone source (`copyFidelitySourceDocId`)
`test_floating_action_copy_fidelity.py`'s `synced_copy` fixture is module-scoped for cost,
same shape as Pattern 2, but the source doc is real and human-authored on purpose:
> *"Module-scoped rather than per-test: a live Playwright menu click that waits on a real
> GAS sync of a ~21-action doc is expensive, and every test below needs the SAME synced
> state, not an independent one (mirrors `test_adr0027_reference_document.py`'s `reference`
> fixture)."*
The source itself is never mutated (`encode_reference_document`'s `DocumentApp.openById()`
read, `clone_doc_with_test_id`'s `DriveApp.makeCopy()` — neither calls `saveAndClose()` on
the source); all mutation happens on a disposable clone trashed at teardown. The same
docstring explicitly contrasts this against Pattern 5's synthetic-corpus approach:
> *"every checked-in scenario corpus round-trips through a FRESH, disposable doc — no live
> human-authored Doc involved."*
**Why bother with a real doc at all** when synthetic corpora are cheaper and faster: a
fresh synthetic doc only proves the round-trip machinery is internally consistent with
itself — it can't surface drift between that machinery and messy real-world authoring
(section-heading prose mixed with actions, orphaned field paragraphs) the way a real
human-authored doc can. That's precisely the gap this pattern exists to catch.

### Quick reference

| Pattern | Scope | Doc is the subject under test? | Chosen for |
|---|---|---|---|
| 1. Per-test disposable | function | Yes | Cleanest isolation |
| 2. Module-shared, read-only consumers | module | Yes (shared) | Amortize expensive setup |
| 3. Module-shared scratch vehicle | module | No — plumbing only | Avoid needless Drive-quota churn |
| 4. Multi-doc sweep | function (3 docs, 1 fixture) | Yes — sweep behavior itself | Cross-doc behavior can't exist in 1 doc |
| 5. Batched multi-scenario | per-lane batch | Yes (sliced back apart) | Pure speed, no cross-scenario claim |
| 6. Canonical shared-mutable | session-long, suite-wide | Yes — and drifts | Only path when unavailable elsewhere — avoid where possible |
| 7. Stable read-only clone source | module | Source no, clone yes | Realism synthetic corpora can't provide |

---

*Generated 2026-09-03 from a full-repo grep/read pass (`scn/session.py`, `src/WebApp.js`,
`src/TestFixtures.js`, `src/Procedure-Exporter.js`, `src/SPIKE-CommentPosition.js`,
`scripts/apt*.py`, `local.settings.json`, and the `tests/test_apt_*` / doc-lifecycle test
files). Re-verify line numbers before citing them in code review — they will drift as the
files change.*

*Updated 2026-09-03: `copyFidelitySourceDocId` moved from a hardcoded constant into
`local.settings.json`/`local.settings.example.json` alongside the other three standard
docs — see §1.*
