# Test Implementation & Strategy Review — 2026-06-05

**Scope.** Review the testing implementation and strategy for completeness and consistency,
with specific attention to (1) the divergence between the Playwright tests and the `scn/`
scenario model, and (2) how the two stacks could be unified so a Python scenario/journey can
drive Playwright as a mutation/verification step without paying repeated browser-startup cost.

**Sources reviewed.** `docs/atdd/atdd-lifecycle.md` (§14–§17), `docs/atdd/scenario-harness-design.md`,
`docs/atdd/scenario-testing-review-2026-05-29.md`, `docs/atdd/open-tst-issues-scenario-approach.md`,
`docs/DESIGN.md` (§Test Model, §Sync Scenarios, §ATDD Pre-Code Contract), `docs/OPERATIONS.md`
(§Running Tests), `README.md`, `package.json`, the `scn/` package (`ai`, `engine`, `session`,
`surfaces`, `ui`, `contract`, `assertions`), `tests/test_journey.py`, `tests/conftest.py`, and the
Playwright suite (`tests/playwright/*.test.js`, `addon_helpers.js`).

---

## 1. Current architecture — two test worlds

There are **two independent end-to-end stacks** that do not share vocabulary, drivers, or
consistency logic.

### World A — the `scn/` Python scenario harness (~4,200 lines incl. its own unit tests)

A mature realization of `atdd-lifecycle.md §16`:

- **`ai` object** — the noun a scenario manipulates; renders its own doc text via `as_text()`.
- **Expectation/checkpoint engine** (`scn/engine.py`) — queued expectations, per-surface partial
  drain, `STEP`/`INTEGRITY` checkpoints, `AUTO`/`INTEGRITY`/labeled evaluation targets, the
  drain invariant enforced at `close()`.
- **Four surfaces** (`scn/surfaces.py`) — `DOC` (.docx), `SHEET` (.xlsx, docId-scoped),
  `TRACKER` (table in .docx), `UI` (live Playwright).
- **`scn/ui.py` — a Playwright page-object driver** wrapping `playwright.sync_api`: `locate`,
  `hover`, `create_action`, `set_status`, `open_sidebar`, `expect_visible`, `expect_alt`.
- **`tests/test_journey.py`** — the canonical Acts 1–5 journey. Acts 3b/4/5 already fire live UI
  gestures (sidebar render, `@`-create, chip hover, status change) **interleaved with HTTP acts**,
  inside a single module-scoped `browser_page` fixture.

**The integration the request describes already exists in Python.** A scenario already calls
`scn.ui.create_action(...)` as a *mutation* and reads the card / doc / sheet as *verification*,
and the browser is launched once per journey (`scope="module"`), not per act — directly addressing
"Playwright is expensive to spin up."

### World B — the standalone JS Playwright suite (~900 lines, `tests/playwright/*.test.js`)

`smoke.test.js`, `sidebar_shell.test.js`, `sidebar_action_list.test.js`,
`sidebar_tracker_insert.test.js`, `probe.test.js`. These are written directly against
`@playwright/test` with **no** `ai` object, **no** expectation queue, **no** checkpoint model, and a
**separate** consistency path (the GAS `verify_consistency` fixture, asserted with raw `expect()`).
Each test re-implements its own setup, frame discovery, and fixture invocation.

---

## 2. Observations

1. **The two stacks run Playwright two different ways.** World A uses `playwright.sync_api`
   inside pytest; World B uses the Node `@playwright/test` runner via npm scripts. They share only
   `.auth/user.json`. `test:full` runs pytest first, then the Node runner — so in a full cycle
   Playwright is effectively spun up under two runtimes.

2. **World B duplicates boilerplate across files.** `loadSettings`, `invokeFixture`,
   `findAddonFrame`, and `createBlankDoc` are copy-pasted in `sidebar_action_list`, `sidebar_shell`,
   and `sidebar_tracker_insert`; `findAddonFrame` *also* exists in `addon_helpers.js` (so it is
   defined four times). `invokeRoute`/`openSidebarInCurrentDoc` are local one-offs. There is no
   shared JS test module.

3. **Consistency is verified by two different engines.** World A downloads the .docx/.xlsx and
   compares with its surface readers **and** calls GAS `verify_action_rows` + `verify_chip_integrity`.
   World B relies solely on the GAS `verify_consistency` fixture. The two can drift: a rule added to
   the Python readers is invisible to the JS tests and vice-versa.

4. **World B already follows an implicit act→verify rhythm — without the model.** e.g.
   `sidebar_tracker_insert.test.js` AC2: seed (act) → sync (act) → baseline consistency (checkpoint)
   → `edit_action_row` (act) → sync (act) → post-mutation consistency (checkpoint), then asserts only
   the mutated row changed. This is exactly the §16 act/expect/checkpoint shape, expressed as
   ad-hoc imperative code with inline `expect()` calls instead of queued expectations.

5. **UI is not yet a first-class drained surface even in World A.** `session.checkpoint()`'s `read()`
   returns `[]` for `Surface.UI` (`scn/session.py:507`), so `verify(on=UI)` cannot drain. The journey
   works around this (deviation **D2**) by calling `scn.ui.expect_alt(...)` and raw
   `card.frame.get_by_text(...).wait_for(...)` directly — i.e. UI assertions **bypass the expectation
   queue**. So the one place the model and live UI meet is the place the model is not actually applied.

6. **Allure already aggregates both stacks** (`allure-playwright` reporter + pytest `--alluredir`
   into a shared `test-results/allure-results`, unified by `test:report`). But World A's *UI* steps run
   under `sync_playwright`, not `allure-playwright`, so they produce **no** Playwright traces/videos
   in Allure — only pytest step output. World B produces rich traces but **no** `[uc AC#]` tags or
   `ai`-level intent. The report is unified in name but inconsistent in content.

7. **Strategy/implementation drift in the docs.** `README.md` still describes the superseded
   chip-led/named-range design ("recognized natively as a checklist item led by a person chip — no
   typed prefix syntax … anchored with named ranges") — contradicted by ADR-0008 and the as-built
   `AI-N:` token model that the entire test suite asserts against. `DESIGN.md §Test Model` still lists
   "one end-to-end test per Use Case" and a `setupTestFixtures()` naming that the `scn` model and
   HTTP-fixture approach have moved past. `atdd-lifecycle.md §15` is explicitly superseded by §16 but
   retained inline, so a reader meets stale API names (`append_doc_item`, `seed_text`) before the
   canonical ones.

8. **Known coverage gaps are catalogued but not closed** (`atdd-lifecycle.md §17`, the
   `open-tst-issues` doc): P0 doc-initiated deletion and whole-doc deletion, P1 `syncAll` sweep and
   live `onActionSheetEdit` as call-sites, P1 full status lifecycle. These violate the project's own
   *entry-point coverage invariant* (every state-modifying entry point exercised as the call-site).

---

## 3. Findings

### Completeness

- **F1 — UI surface is half-built.** The model defines `UI` as a fourth surface with `verify(on=UI,
  within=…)` semantics, but the engine cannot drain it and the journey routes around it. UI evidence
  is therefore asserted outside the queue and outside the drain invariant — exactly the
  "under-assertion via weak architecture" §13 warns against.

- **F2 — Entry-point coverage invariant is not met.** Doc-initiated deletion, whole-doc deletion,
  `syncAll`, and the live `onActionSheetEdit` trigger are not exercised as call-sites in any green
  journey. The JS tests that *do* touch the sidebar/tracker entry points are not counted by the
  Python coverage matrix because they live in a separate stack.

- **F3 — No single source of truth for "consistent."** Two consistency implementations (Python
  readers vs GAS fixture) means a contract change must be made in two places to be enforced
  everywhere; nothing fails if only one is updated.

### Consistency

- **F4 — Duplicated, drift-prone JS harness.** Four-way duplication of frame/fixture helpers means a
  Google DOM change (cold-start "Refresh" handling, iframe `src`) must be fixed in up to four files.
  The Python `UiDriver` already centralizes this knowledge; the JS tests re-derive it.

- **F5 — Two Playwright runtimes, two auth code paths.** `sync_playwright` (pytest) and
  `@playwright/test` (node), plus the cookie-injection shim in `session.py` for `/dev` URLs. Browser
  startup, auth, and selector knowledge are paid for twice and maintained twice.

- **F6 — Inconsistent reporting granularity.** Allure mixes richly-traced JS tests with
  trace-less Python UI steps and lacks uniform `[uc AC#]` tagging across both, undermining the §10
  "triageable from the failure alone" rule at the report level.

- **F7 — Doc set contradicts itself and the code** (Observation 7), so the authoritative strategy a
  new contributor reads depends on which file they open first.

---

## 4. Recommendations

The strategic choice is **where the scenario model lives**. It already lives, working, in Python.
The cheapest path to completeness *and* consistency is to make Python the single journey driver and
demote JS to a thin, fast pre-deploy smoke gate — rather than rebuild the engine a second time in JS.

### R1 — Make `UI` a first-class drained surface (closes F1)

Implement `read(Surface.UI)` in `session.checkpoint()` so the engine can drain UI expectations,
and route `scn.expect_visible`/`expect_alt`/`verify(on=UI, within=…)` through the queue like every
other surface. The `UiDriver` already exposes the live reads; the missing piece is the engine read
closure and a `within=` bounded poll on the UI surface. Once done, the journey's D2 workaround is
removed and live UI evidence obeys the drain invariant. *This is the single highest-leverage change:
it completes the model exactly where the request points.*

### R2 — Adopt "Python journey fires Playwright as an act/verification" as the standard, and codify the cost rule

The pattern exists; formalize it so all new UI coverage uses it:

- **UI acts are mutations** (`scn.ui.create_action`, `scn.ui.set_status`, a future
  `scn.ui.sidebar_sync`, `scn.ui.delete`) — one entry point per act, same as HTTP acts.
- **UI reads are verifications** (`verify(on=UI, within=…)`), drained at checkpoints (after R1).
- **One browser per journey, never per act** — the module-scoped `browser_page` fixture is already
  correct; make it the documented contract. Everything that does *not* require the browser stays on
  the HTTP fixture path (it is far cheaper); reserve Playwright for surfaces only the UI can show
  (`§16.3 #5`). This is the explicit answer to "Playwright is expensive to spin up": amortize the
  one cold start across all UI acts of a journey, and keep non-UI acts off the browser entirely.

### R3 — Migrate the JS suite's unique coverage into Python `scn` journeys/focused tests (closes F2, F4)

Each JS test maps cleanly onto the model:

| JS test | scn equivalent |
|---|---|
| `sidebar_action_list` (homepage renders rows, refresh after sync) | `scn.ui.open_sidebar()` act + `verify(on=UI)` on each `ai` (extends existing Act 3b) |
| `sidebar_tracker_insert` AC1 (Insert tracker button) | `scn.ui.insert_tracker_button()` act + `verify(on=TRACKER)` + `verify_consistency` |
| `sidebar_tracker_insert` AC2 (status mutation, only mutated row differs) | `edit_sheet`/`set_status` act + per-row `verify(on=TRACKER)`; "only mutated row" is naturally expressed by enqueuing unchanged `ai`s and the changed one |
| `sidebar_tracker_insert` AC3 (cell edit overwritten on re-insert) | a focused `scn` test (no UI needed — already a fixture path) |
| `sidebar_shell` (single-surface card, control presence) | `verify(on=UI)` on control alt-text |

The migrated coverage is then counted by the same entry-point matrix and uses the same
`ai`/queue/consistency machinery, eliminating F4's duplication outright.

### R4 — Keep a *minimal* JS Playwright layer only for what Python should not own

Retain `smoke.test.js` and `probe.test.js` as a **fast, pre-deploy gate** (auth works, add-on is
installed, deployed revision reachable, chip renders) — they are deliberately shallow and benefit
from the Node runner's trace/video. Extract the shared helpers (`loadSettings`, `invokeFixture`,
`findAddonFrame`, `createBlankDoc`) into a single `tests/playwright/_helpers.js` so even this slim
layer stops duplicating (closes F4 for the residual JS).

### R5 — Single source of truth for consistency (closes F3)

Pick one consistency authority. Recommended: the GAS-side `verify_consistency`/`verify_action_rows`
+ `verify_chip_integrity` routes remain the *server* truth (they see live doc state the download
can miss), and the Python surface readers assert the *artifact* truth (what the user downloads).
Document which checks belong to which, and have the JS smoke layer call the same GAS route — so no
test invents a third notion of "consistent."

### R6 — Unify Allure content, not just the directory (closes F6)

After R1–R3, most UI coverage runs under pytest; add `allure-pytest` step/attachment hooks so the
`scn.ui` driver attaches a screenshot on UI-expectation failure and every enqueued expectation
carries its `[uc AC#]` tag into the Allure step name. The residual JS smoke layer keeps
`allure-playwright` traces. The report then reads uniformly regardless of stack.

### R7 — Reconcile the doc set (closes F7)

- Rewrite `README.md §How It Works` to the as-built `AI-N:` token model (ADR-0008); drop the
  named-range/chip-led prose.
- Update `DESIGN.md §Test Model` to reference the `scn` journey + focused-test split as canonical
  and retire the `setupTestFixtures()`/one-test-per-UC framing.
- Thin `atdd-lifecycle.md §15` to a pointer to §16 (the follow-up the doc's own header promises).

---

## 5. Refactor sketch — what a unified UI act reads like

Today (JS, World B — imperative, no model):

```js
await invokeFixture('uc_c_pending_sync_refresh', docId, settings);
await openDocSidebar(page, docId);
let frame = await findAddonFrame(page);
await frame.getByRole('button', { name: /sync now/i }).click();
await waitForLogEntry(e => e.tag === 'sync.complete', 60000);
const c = await invokeFixture('verify_consistency', docId, settings);
expect(c.data.ok).toBe(true);
// …hand-rolled row diff…
```

After (Python `scn`, World A — same intent, model-native; UI act + drained verification):

```python
scn.ui.sidebar_sync()                 # act: one entry point (the Sync Now button)
for a in (a1, a2, a3):
    scn.verify(a, on=TRACKER)         # enqueue; only-mutated-row falls out of the unchanged set
scn.verify(changed, on=TRACKER, status="In Progress")
scn.checkpoint(INTEGRITY)            # drains; runs the single consistency authority (R5)
```

The browser is the journey's one `browser_page`; the sync ran through the real sidebar button (a
true call-site), and consistency is the same engine the HTTP acts use.

**If JS must remain a full E2E stack** (not recommended), the equivalent is a `ScenarioPage` class in
JS mirroring `scn` — `.act()`, `.expect()`, `.checkpoint()` over the GAS consistency route. This buys
the *visual* model parity the request asks for but re-implements (and must keep in sync with) the
Python engine, so it trades F4 for a worse maintenance burden. R1–R3 avoid that by not forking.

---

## 6. Suggested sequencing (file as `[TST]`/`[INF]` bd issues)

1. **R1** `[TST]` — implement `read(UI)` + queue-routed UI expectations; remove journey deviation D2.
2. **R7** `[INF]` — doc reconciliation (README/DESIGN/§15); cheap, removes contributor confusion.
3. **R3** `[TST]` — migrate `sidebar_*` coverage into `scn` journeys/focused tests; delete the JS
   duplicates as each lands (twin to R1 since the tracker/sidebar acts need the UI surface).
4. **R4** `[TST]` — extract `tests/playwright/_helpers.js`; trim JS to smoke + probe.
5. **R5/R6** `[INF]` — consistency single-source + Allure content unification.
6. **F2 backlog** — close the §17 P0/P1 entry-point gaps (doc-deletion, whole-doc deletion,
   `syncAll`, live `onActionSheetEdit`, status lifecycle) as `scn` journeys now that UI is first-class.

---

_Review date: 2026-06-05._
