# Staged plan — APT testing: replace the self-comparison oracle

**Contract:** `$DEVSTANDARD/doc-framework/planning-guide.md` §"Pattern D: Staged Execution".
Beads own all state (AC, grouping, model, human decisions). This document holds only
sequencing rationale, deliverable previews and handoff notes.

## Why this plan exists

On 2026-08-29 the ADR-0027 canonical reference Doc was found to have 20 of its 21 actions
unscanned (`sync.scanned count:1`, then 20 rows marked *Deleted*). The proximate cause was a
stale add-on build predating ADR-0023's `ACT-` read support. The durable cause is that no test
could have caught it:

- No test touches the canonical Doc — every APT lane calls `ScenarioSession.new_doc()`.
- All 15 scenario triples are `input == expected` under `mutation: sync`, so the assertion is
  `encode(sync(decode(X))) == X`. **A sync that scans nothing satisfies it.**
- Goldens are blessed from the system under test, so they cannot contradict it. 13 records
  missing their `ACT-N:` link header were frozen as expected output.
- `tests/helpers/doc_inspect.py:floating_actions()` — the one independent Python parse — still
  detects actions by `w:numPr` + assignee, the pre-ADR-0027 checklist grammar. It finds almost
  nothing in an ADR-0027 doc and never extracts the token at all.

The correction is a **twin-track oracle** (T-series independence): parse the document in Python
from the spec, and assert the ActionSheet agrees. Nothing derived from the implementation is
allowed to serve as the expected value.

**Never run complete regression test because it is very expensive, that will be run once we get the apt testing actually working for once**

## Stage 0 — beads to file

**Closed 2026-08-28.** All 16 beads created; see the execution-order table below.
Scope changed in one place during creation: the plan asserted `menuForceRefreshActiveDoc`
"currently has none" for entry-point coverage. It has some —
`tests/test_menu_entry_points.py:235` exercises it with observable state verification through
the `menu_force_refresh_active_doc` fixture (`src/TestFixtures.js:3292`). The real gap is the
**WebApp** route: `src/WebApp.js:445` calls `syncDocument(docId)` with no options, so the
force-flush path at `src/SyncManager.js:324` is unreachable off the browser. Stage
`act-force-refresh`'s `[TST]` was re-aimed accordingly (route coverage + a force entry-point
audit) and its *Deliverable* line corrected below.

## Execution-order table

| # | Stage | Bead | Status | Title |
|---|---|---|---|---|
| 1 | `apt-oracle-parser` | `gts-e5cl` | ✓ | [TST] doc_inspect: parse the ADR-0027 floating-action grammar |
| 1 | `apt-oracle-parser` | `gts-9o61` | ✓ | [TST] doc↔sheet agreement assertion, both directions |
| 2 | `act-force-refresh` | `gts-366c` | ✓ | [IMP] WebApp force parameter on the document-sync route |
| 2 | `act-force-refresh` | `gts-gssn` | ✓ | [TST] Force-refresh route coverage and force entry-point audit |
| 3 | `apt-repair` | `gts-imai` | ✓ | [FIX] Repair the canonical reference Doc and its ActionSheet rows |
| 3 | `apt-repair` | `gts-a7ko` | ⊘ | [TST] Re-bless action-reference.apt.txt from the repaired doc *(blocked on `gts-1ibp`)* |
| 3 | `apt-repair` | `gts-1ibp` | ○ | [FIX] Flush shifts every inline bold/italic/link run one character left, cumulatively **(P0, filed at stage 3)** |
| 4 | `apt-lane-guards` | `gts-p150` | ○ | [TST] Pristine-restore fixture for the reference corpus |
| 4 | `apt-lane-guards` | `gts-lu13` | ○ | [TST] Assert sync.scanned count and zero Deleted rows in every live lane |
| 4 | `apt-lane-guards` | `gts-omoy` | ○ | [INF] Deployed-build guard for live lanes |
| 5 | `apt-corpora-rebuild` | `gts-ru4c` | ○ | [TST] Re-author every scenario's expected corpus as the post-sync state |
| 5 | `apt-corpora-rebuild` | `gts-5st5` | ○ | [TST] Lint: input == expected is an error for a non-degenerate mutation |
| 6 | `apt-presentation` | `gts-dxgo` | ○ | [TST] Doc-side presentation assertions: person chip, ACT-N link run, status icon |
| 6 | `apt-presentation` | `gts-gkcy` | ○ | [TST] Sparse expected-parse annotation on hard records |
| 7 | `doc-truth` | `gts-blia` | ✓ | [INF] CONTEXT.md: correct the user-facing surface model |
| 7 | `doc-truth` | `gts-c9dd` | ○ | [INF] Resolve dangling decision-number citations *(blocked on `gts-ru4c`)* |
| 8 | `plan-retention` | `gts-flu4` | ○ | [INF] Staged-plan retirement must preserve the plan |
| — | *(filed at stage 2)* | `gts-c7fp` | ○ | [FIX] doPost's terminal else-branch writes junk rows for any unrecognised secret-gated action |
| — | *(filed at stage 2)* | `gts-pl2k` | ○ | [INF] doPost's unauthorized response is plain text, so every harness caller reports it as deployment lag |
| — | *(filed at stage 1)* | `gts-1ej4` | ○ | [TST] Converge scn/surfaces.py DocReader onto the doc_inspect grammar oracle |
| — | *(filed at stage 7)* | `gts-wxz1` | ○ | [INF] security-architecture.md predates ADR-0021, doesn't document the verified-portal identity boundary |

**Verify:** `bdls --stages` · `bdls --check` · `bdls --goals --stage <name>`
Status above mirrors the tracker, which stays the authority. Audit at authoring
(2026-08-28): **0 errors**, 4 warnings on these stages — all four deliberate, stated in the
stage blocks below (`plan-retention` isolated by anti-pairing; `apt-lane-guards`,
`apt-presentation` and `doc-truth` each hold beads whose internal order genuinely is free).

**Ordering is oracle-driven** (project CLAUDE.md). Every stage here has a **specifiable
oracle** — a parse, a log tag, a row state, a corpus diff — so every stage is test-first.
No stage in this plan qualifies for the Slice path; that is the point of the plan.

## Stages

### 1 — apt-oracle-parser
**Deliverable:** a Python parse of the reference Doc that enumerates, independently of GAS,
exactly which actions and fields the scanner is missing.
**Why paired:** the parser and the assertion that consumes it share one grammar reading; splitting
them means writing the contract twice.
**Model:** opus — grammar work against a spec, where a wrong reading is invisible until much later.
**Work-log:** per-stage.
**Must not:** read `tests/fixtures/*.apt.txt` while authoring the parser. The parser is the
independent track; deriving it from corpora the implementation produced rebuilds the same
circularity in a new place.

### 2 — act-force-refresh
**Deliverable:** the force-flush path reachable over the WebApp route, and covered — plus an
audit naming every force-capable entry point and the test whose call-site exercises it.
*(Corrected at Stage 0: the Docs menu item is already covered; the WebApp route is the gap.
Corrected again at close: there was no WebApp route to thread `force` through — a new
secret-gated doPost route `sync_document` was created. See the handoff.)*
**Why paired:** twin-ticket — the `[IMP]` route and its `[TST]` coverage freeze one contract.
**Model:** sonnet — the shape is settled; `force` already exists in `SyncManager.js:324`.
**Work-log:** per-stage.
**Must not:** widen into other unreachable entry points. Audit them, file them, do not fix them here.

### 3 — apt-repair
**Deliverable:** a canonical reference Doc where all 21 actions render correctly, with the sheet
agreeing — the pristine baseline every later stage restores from.
*(Corrected at close: the scan/sheet half was already correct on arrival and is now verified;
the render half is **not** delivered — `gts-1ibp` found the flush walking every inline
bold/italic/link run one character left per flush, so the Doc is structurally pristine and
typographically drifted. The bless is blocked until that lands. See the handoff.)*
**Why paired:** re-blessing is only trustworthy in the same session that verified the repair.
**Model:** sonnet.
**Work-log:** per-stage.
**Must not:** bless anything the stage-1 parser has not confirmed. This is the exact step that
froze the defect last time.

### 4 — apt-lane-guards
**Deliverable:** a lane that goes red on a stale deployment, a short scan, or a *Deleted* row.
*(Corrected at close: 2 of 3 beads delivered this — `gts-omoy` and `gts-lu13`. `gts-p150`
(pristine-restore fixture) did not: it depends on `gts-a7ko`, still open and blocked on the P0
`gts-1ibp` from stage 3. See the handoff.)*
**Why paired:** three small guards in the same conftest/lane plumbing.
**Model:** sonnet.
**Work-log:** per-stage.
**Order within the stage is free** — `unordered-batch` warning accepted deliberately; the three
guards are independent of one another.
**Must not:** close without demonstrating each guard failing against the 2026-08-29 conditions.
A guard that has only ever shown green is unverified (Backstop rules).

### 5 — apt-corpora-rebuild
**Deliverable:** scenario triples whose expected side differs from their input, so a no-op sync
fails them.
**Why paired:** the lint and the re-authoring define each other.
**Model:** opus — deciding what each mutation *should* produce is the design judgement this plan
turns on.
**Work-log:** per-stage.
**Must not:** batch with stage 1. Authoring expected corpora after reading the parser's internals
re-couples the two tracks (no-shared-context).

### 6 — apt-presentation
**Deliverable:** chip, link-run and status-icon assertions per record, plus a troubleshooting
annotation on the records that are hard to reason about.
**Why paired:** both are per-record annotations of the same corpora.
**Model:** sonnet.
**Work-log:** per-stage.
**Order within the stage is free** — `unordered-batch` warning accepted deliberately.
**Must not:** promote the annotation into a per-item convention or a user-facing feature.

### 7 — doc-truth
**Deliverable:** a CONTEXT.md whose stated surface model matches the system, and no citations
pointing at a deleted document.
*(Corrected at close: the CONTEXT.md half delivered — `gts-blia`. The citation half does not —
`gts-c9dd` is open and blocked on stage `apt-corpora-rebuild`'s `gts-ru4c`. See the handoff.)*
**Why paired:** both are corrections to documents that are currently wrong, not new work.
**Model:** opus — the surface model touches the security boundary.
**Work-log:** per-stage.
**Order within the stage is free** — `unordered-batch` warning accepted deliberately.
**Must not:** re-open the expected-parse design question. That is settled: troubleshooting aid.

### 8 — plan-retention
**Deliverable:** a retirement path that cannot lose a plan's decisions again.
**Why paired:** single concern; consumes the lessons-learned resolution.
**Model:** opus — it changes a DevStandard skill used by every project.
**Work-log:** per-stage.
**Isolated by design** — `isolated-stage` warning accepted deliberately; the anti-pairing below
forbids modelling an edge that would batch it with project work.
**Must not:** land as a project-local workaround. The defect is in the shared skill.

## Anti-pairings

- **1 with 5** — the parser must not be authored against the corpora it will judge.
- **3 with 4** — repairing the Doc and writing the guard that detects an unrepaired Doc in one
  session means the guard is tuned to the state that was just fixed.
- **8 with anything** — a DevStandard change reviewed alongside project work gets the project's
  attention, not the framework's.

## Handoffs

One block appended per stage **at close**, before the stage's commit. Required by planning-guide
§Pattern D Mode B (steps 14–16); restated here because this plan's whole subject is a check that
was skipped on the load-bearing path while being honoured on a cheap one.

Four parts, every time:

- **Done** — real output pasted, not a restatement of the AC. If reality differed from the stage's
  *Deliverable* line above, correct that line in place and say so here.
- **Found** — every observation carries a disposition inline: **fixed now** · **bead `<id>`** ·
  **AC of stage `<name>`** · **deliberately dropped, because…** An observation with no disposition
  is the defect this section exists to prevent.
- **Next stages must know** — what the following session would otherwise rediscover.
- **Deliberately not done** — in scope on paper, not done, and why.

Deferrals land in a bead or a named stage's AC (rule 17). Naming a successor stage in prose is not
a handoff. Owner decisions get the `human` label (rule 18), never a prose "HELD".

### Stage close checklist

1. `bd note` the handoff onto the stage's bead(s)
2. Append the same four-part block here, under a `### <#> — <stage-name>` heading
3. Correct the stage's *Deliverable* line above if reality differed
4. Commit and push — per stage, always, even when the work-log entry batches

<!-- Handoff blocks are appended below this line, in stage order. -->

### 1 — apt-oracle-parser

**Closed 2026-08-28.** Beads `gts-e5cl` ✓ and `gts-9o61` ✓, both `regression=pending`.

**Done**

`tests/helpers/doc_inspect.py:floating_actions()` is now an independent ADR-0027 grammar parse
returning `ParsedAction` records. Detection is the `ACT-N:`/`AI-N:` token, never `w:numPr`; every
`w:p` under the body is walked, so body, list-item and table-cell containers are reached
identically. Soft returns and tabs are read from `w:br`/`w:tab` — `para.text` drops both, which is
why the continuation grammar was previously invisible. Supporting files:
`tests/helpers/docx_build.py` (offline fixture builder) and
`tests/helpers/doc_sheet_agreement.py` (`compare_doc_sheet` pure core + `assert_doc_sheet_agreement`
live wrapper). `scn/surfaces.py:SheetReader` now surfaces the `custom_fields` column.

Sources read while authoring: ADR-0027, `docs/interfaces/action-portable-text.md`, and beads
`gts-v0py`/`gts-28q`/`gts-1tbe` for the status-position refinement. No GAS source, no
`scripts/apt_lib.py`, no `tests/fixtures/*.apt.txt` — the *Must not* held.

Real output, the parser run against the canonical reference Doc (`tests/test_doc_oracle_reference.py`,
4 passed — read-only, no GAS route, no mutation):

```
22 records: 21 tokened actions (ACT-1..ACT-9, AI-10, ACT-11..ACT-21) + 1 rule-6 record
ACT-1  linked=True chip=jane@example.com status='In Progress'
       text="Draft the Q3 budget memo\n- pull last year's actuals\n- and this is bold - ..."
       fields={'Consult With': '\n- Stuart\n- John', 'Due': 'Tuesday'}
ACT-2  fields={'Target': ..., 'Progress': ..., 'Consult With': ..., 'Notes': ...}
ACT-9  'ACT-9:  (Open)'  -> no assignee, action_text=''   (gts-jxrw bare-token truncation)
ACT-13 text='edge case sentence\nthen he said: we should ship it'  (stayed prose, rule 5)
idx=20 error=unparseable-action-paragraph  raw='ACT-77 | someone | do the thing'  (rule 6)
```

Gate: `PYTHONPATH=src pytest tests/test_doc_oracle_parser.py tests/test_doc_sheet_agreement.py
tests/test_scn_surfaces.py` → **63 passed**; `tests/test_doc_oracle_reference.py` → **4 passed**.
Full `pytest -x` not run (project rule: never on own initiative).

Proven to fail, both beads:
`test_short_count_when_actions_are_removed` (parser reports 1 where 21 are expected) and
`test_red_against_the_2026_08_29_state` (21 doc actions vs 1 live row + 20 *Deleted* rows →
exactly 20 problems, all naming Deleted). Ten further tests assert each individual failure mode
red and the agreeing case green.

**Found**

- The reference Doc holds **21 tokened actions plus 1 deliberate rule-6 paragraph** (`ACT-77 |
  someone | do the thing`, the `unparseable-reporting`/gts-thwh case) — 22 records, not 21.
  **Fixed now:** the lane asserts 21 *tokened* actions and asserts rule-6 paragraphs are
  *reported* with a usable diagnostic, rather than asserting none exist.
- **All 21 tokens currently carry their `ACT-N:` chip-badge link**; zero unlinked, zero pending
  triggers. This plan's §"Why this plan exists" claim that *13 records missing their `ACT-N:`
  link header were frozen as expected output* is **not the Doc's state as of this session**.
  **AC of stage `apt-repair`** (noted on `gts-imai`): run the oracle first, repair only what it
  reports. The claim above is left standing as the plan's original premise rather than rewritten,
  since it may still describe the *corpus* file rather than the Doc.
- `scn/surfaces.py:SheetReader` never read the `custom_fields` column (col 12, in the contract
  since ADR-0027 rule 9), and its `_cell_val` raised `IndexError` on a short row.
  **Fixed now** (`scn/surfaces.py`).
- A PERSON chip exports to `.docx` with **the email as its display text** on every chip in the
  canonical Doc, so a doc-side `assignee_name` is not a display-name claim. **Fixed now** in the
  comparator (an email-shaped chip label is not compared against the sheet's resolved name);
  **AC of stage `apt-presentation`** for the chip assertion (noted on `gts-dxgo`).
- `ACT-9` is literally `ACT-9:  (Open)` — no assignee, empty body (gts-jxrw). The oracle reports
  it as a valid action with `action_text ''`. **AC of stage `apt-corpora-rebuild`** (noted on
  `gts-ru4c`): the expected corpus must *state* what a no-body action becomes.
- `custom_fields` values are returned as plain joined text, not ADR-0027 rule 15's
  `{text, runs}`. **AC of stage `apt-presentation`** (`gts-dxgo`), which owns run extraction.
- `scn/surfaces.py:DocReader` is a second, weaker doc-side parser still used by the whole live
  suite (no soft returns, no fields, no rule-4 status scoping, drops empty-body actions like
  ACT-9), and `tests/test_scn_surfaces.py` carries a local docx-fixture builder duplicating
  `tests/helpers/docx_build.py`. **Bead `gts-1ej4`.**

**Next stages must know**

- `floating_actions()` returns **all** records — filter on `.token` for established actions;
  `.error` is a rule-6 paragraph, `.pending` a bare `AI:` trigger, `.token_linked` the chip-badge
  link. Nothing is dropped, which is the whole point.
- `tests/helpers/docx_build.py` constructs any grammar case offline (soft returns, tabs, chips,
  link runs, bold, list items, table cells) — a new grammar assertion needs no live Doc and no
  GAS deploy.
- `compare_doc_sheet` is pure; `assert_doc_sheet_agreement(session, doc_id)` is the live wrapper
  and is **read-only** (a `.docx` export + a `.xlsx` export). Status absence in the doc is treated
  as agreement with the sheet's `Open` default — the oracle reports `None` rather than inventing
  a default.

**Deliberately not done**

- Inline run (bold/italic/link) extraction — stage `apt-presentation`'s scope, stated in the
  module docstring rather than left implicit.
- No live lane calls `assert_doc_sheet_agreement` yet. Wiring it in is stage `apt-lane-guards`
  (`gts-lu13`, noted): doing it here would tune the assertion to a state stage `apt-repair` has
  not yet fixed — the 3-with-4 anti-pairing applied one stage early.
- Full `pytest -x`. Both beads carry `regression=pending`.

### 2 — act-force-refresh

**Closed 2026-08-29.** Beads `gts-366c` ✓ and `gts-gssn` ✓, both `regression=pending`.

**Done**

A new WEBAPP_SECRET-gated doPost route `sync_document` — `src/WebApp.js`'s
`_handleSyncDocument(payload)`, dispatched beside `sync_action_rows` — reaches
`syncDocument(docId, {force: payload.force === true})`. Registered in
`src/ContractSchema.js` (`webApp.routeNames` + `webApp.messages.sync_document`) and in
`scripts/call_webapp.py`'s `_SECRET_ROUTES`. Deployed TEST **v0.2.3.38** (deployment
`AKfycbzVloY3co…`, revision `@509`).

The AC-verification command from the frozen contract, run live:

```
$ python scripts/call_webapp.py sync_document --data '{"force": true}'
{"ok": false, "error": "docId required", "serverVersion": "0.2.3.38"}
```

That one call proves three things at once: the CLI picked the `secret` auth field (a missing
`_SECRET_ROUTES` entry would have answered `unauthorized`), the route is on the deployed
build, and AC-5 refuses without dispatching into `syncDocument('')`.

Red, before the route existed (v0.2.3.37) — **5 failed in 410.09s**, every call falling
through `doPost` to the legacy-POC branch and returning the plain-text body `'ok'`:

```
FAILED test_sync_document_route_force_flushes_converged_action
FAILED test_sync_document_route_without_force_does_not_force_flush
FAILED test_sync_document_route_non_boolean_force_is_not_forced
FAILED test_sync_document_route_requires_doc_id
FAILED test_sync_document_route_rejects_a_bad_secret
E  RuntimeError: Non-JSON response (action='sync_document') …: 'ok' (after 5 attempts)
```

Green, after deploy: `tests/test_force_refresh_route.py` + `tests/test_menu_entry_points.py`
→ **12 passed in 455.76s**.

**Found**

- **The route this stage was written against does not exist.** `gts-366c` said "thread an
  opt-in force flag through doPost to [the `syncDocument` call at] WebApp.js:445". That line
  is inside `_handleRegister` — the **doGet** `?cmd=register` browser-form route, neither
  doPost nor secret-gated. The only doPost paths to `syncDocument()` were
  `team_sync_document` (OAuth assertion + EDIT tier) and the testToken `run_fixture`
  fixture, neither usable by `call_webapp.py`. **Fixed now:** owner decision taken before
  any code was written — a *new* secret-gated doPost route, rather than forcing `register`
  (which has no converged state to re-flush) or the harness fixture (not a WebApp route).
  `gts-366c`'s AC was rewritten to the frozen contract first; the *Deliverable* line above
  is corrected in place.
- **`doPost`'s terminal `else` branch silently mutates the spreadsheet.** Any action name
  that passes the secret gate but matches no route appends
  `[new Date(), payload.email||'', payload.message||'']` to the bound spreadsheet's *active*
  sheet and returns plain-text `'ok'`. A typo'd or not-yet-deployed action therefore writes
  instead of erroring, and the harness — which retries a non-JSON body 5× — writes five rows
  per call. The red run above put **20 rows into TEST `SyncState!A912:A932`**, a sheet whose
  column A is a Doc ID and which `_loadSyncState` reads. **Bead `gts-c7fp`** (root-cause fix
  *and* the row cleanup; not fixed here — the stage's *Must not* forbids widening).
- **`doPost`'s `unauthorized` is plain text, not JSON.** Every sanctioned caller treats a
  non-JSON body as the GAS deployment-propagation symptom, so an auth failure costs ~90s of
  backoff and then reports itself as propagation lag. **Bead `gts-pl2k`.**
- Two of the five tests must assert on *exceptions* rather than responses, because that is
  what the WebApp actually sends: a missing `docId` surfaces as `scn.session.FixtureError`
  (`_post` raises on any response carrying an `error` key) and a bad secret as `RuntimeError`
  on the plain-text body. **Fixed now** — both stated in the test docstrings rather than
  papered over with an invented JSON envelope; `gts-pl2k` covers the second.
- The force entry-point audit came back **complete with no gap**: exactly two production
  call-sites pass `{force}` into `syncDocument()` — `MenuHandler.js:127`
  (`menuForceRefreshActiveDoc`, covered since gts-t78c) and the new route (covered now). The
  full table, including every *non*-forcing `syncDocument()` call-site so the audit is
  falsifiable, is on `gts-gssn` as a note. **Deliberately dropped:** no bead is owed, because
  the audit found nothing uncovered.

**Next stages must know**

- **Stage `apt-repair` now has its tool.** Forcing a re-render of the canonical reference Doc
  from the command line is
  `python scripts/call_webapp.py sync_document --data '{"docId": "<id>", "force": true}'`.
  Check `result` in the response: `'locked-skip'` means it lost the per-doc lock to a
  concurrent execution and **did nothing** — retry rather than believe `ok:true`.
- `force` is compared `=== true`. A shell-quoted `"force": "true"` is silently *not* forced,
  and the response's `forced` field is the only thing that says so. This is deliberate (a
  whole-document re-render is not something a quoting slip should trigger) and is asserted by
  `test_sync_document_route_non_boolean_force_is_not_forced`.
- On an already-converged doc the response proves nothing — a no-op sync also returns
  `ok:true`. `sync.forceFlush {docId, count>=1}` is the oracle. Stage `apt-lane-guards`
  (`gts-lu13`) wants the same log line for its short-scan guard.
- Do not POST an action name that is not on the deployed build until `gts-c7fp` lands: it
  will write junk rows into whichever sheet is active, five per call.

**Deliberately not done**

- The `doPost` fallthrough fix and the `SyncState!A912:A932` cleanup — `gts-c7fp`. Cleaning
  the rows needs a sheet mutation with no sanctioned wrapper; left for an owner decision.
- The plain-text `unauthorized` envelope — `gts-pl2k`.
- Threading `force` through `_handleRegister`, `team_sync_document`, or the `run_fixture`
  fixture. Audited, force-incapable by design, not by omission; enumerated on `gts-gssn`.
- Full `pytest -x`. Both beads carry `regression=pending`.

### 3 — apt-repair

**Partially closed 2026-08-29.** Bead `gts-imai` ✓ (`regression=pending`); `gts-a7ko` remains
**open and blocked** on the P0 filed by this stage, `gts-1ibp`. The stage does not close.

**Done**

AC1, before touching anything — `?cmd=version` → `{"ok":true,"version":"0.2.3.38",
"versionDate":"2026-08-29T07:42:32.259Z","target":"TEST"}`, matching `package.json`'s stamp, on a
clean tree. Pre-mutation capture (the *design* question's "capture first"):
`apt pull action-reference` → `.apt-captures/action-reference/20260829T081258811302Z.apt.txt`.

**The 2026-08-29 defect was already gone before this session began.** Read-only oracle, run
*before* any repair action: `tests/test_doc_oracle_reference.py` → **4 passed** — 21 tokened
actions, all 21 link-headed, zero pending, one deliberate rule-6 paragraph. Sheet side:

```
doc actions=22 sheet rows for doc=21
ACT-1..ACT-9, AI-10, ACT-11..ACT-21   sync_status='' on every row
--- 1 problems ---
  doc paragraph 20: unparseable-action-paragraph — 'ACT-77 | someone | do the thing'
```

Raw audit of the whole `Actions` tab: 499 non-empty rows, exactly **21** mention the reference
doc id, and the string `Deleted` appears nowhere in the sync-status column (`Counter({None: 278,
'Doc Not Found': 230})`). AC3 was therefore satisfied on arrival — **this bead deleted no rows**;
it proved there were none to delete. The non-vacuity of that claim is stage 1's
`test_red_against_the_2026_08_29_state`, which shows the same comparator reporting exactly 20
*Deleted* problems against the failure state.

AC2, the force flush over the new stage-2 route:

```
$ python scripts/call_webapp.py sync_document --data '{"docId": "1PYIU…NO-E", "force": true}'
{"ok": true, "docId": "1PYIU…NO-E", "forced": true, "result": null, "serverVersion": "0.2.3.38"}

axiom op=b2be59e1  sync.scanned count=21 · sync.forceFlush count=21
                   flush.done batchSize=21 copies=21 · sync.complete forced=True upserted=0
```

Post-flush render check — all 21 tokens `token_linked=True`, all 21 carrying a status token,
**20** carrying a person chip; `ACT-9` has none by design (bare-token case, gts-jxrw), so AC2's
"person chip" reads 20/21 and the AC is over-stated, not failed. AC4 post-flush: oracle **4
passed**, comparator back to the single deliberate rule-6 line, no token-level disagreement.
AC5: nothing blessed.

**Found**

- **The flush walks every inline bold/italic/link run one character LEFT, and it compounds.**
  **Bead `gts-1ibp` (P0).** Three captures of the same corpus, one flush apart:

  ```
  20260829T043523Z (intended)   - and this is **bold** - circulate before Friday
  20260829T081258Z (1 flush)    - and this is** bol**d - circulate before Friday
  20260829T081611Z (2 flushes)  - and this i**s bo**ld - circulate before Friday
  ```

  Same −1 walk on italic and on hyperlinks (`ACT-19` `'the[ Q3 dec]k'` → `'th[e Q3 de]ck'`;
  `ACT-20`, `ACT-21`). The raw `.docx` runs confirm it is the **document**, not the APT encoder:
  `ACT-21` exports as `[bold]'e bold th'`, not `[bold]'bold this'`. A constant −1 *write* error
  plus a faithful *read-back* by the next scan is exactly a cumulative left walk; suspected site
  is `actionTextStart + segment` in `src/SyncManager.js` `_buildFlushRequests` (the gts-zocq
  reapply block). This is a live-data defect, not a test-fixture one — it drifts any doc with
  inline formatting, on ordinary dirty flushes as well as forced ones.
- **The forced flush AC2 mandated added the second character of that drift.** Disclosed rather
  than quietly absorbed: the canonical Doc is now two characters off intent on `ACT-1`, `ACT-19`,
  `ACT-20`, `ACT-21`. **AC of `gts-1ibp`** (item 3: restore the four records).
- The plan's premise — *13 records missing their `ACT-N:` link header were frozen as expected
  output* — is **true of the corpus file** and was never true of the Doc this session.
  Stage 1 flagged the ambiguity; it is now settled. **Fixed now** in the record: the golden
  `tests/fixtures/action-reference.apt.txt` carries the header on only 2 of 21 records.
- `compare_doc_sheet` counts the corpus's deliberate rule-6 paragraph as a *problem*, so the
  canonical Doc can never reach zero problems. **AC of stage `apt-lane-guards`** (noted on
  `gts-lu13`): the lane needs an allowance for expected rule-6 records, the same way
  `allow_pending` works — otherwise the guard is red on a healthy corpus.
- Another session was driving TEST concurrently during this stage (`begin_test_session`,
  `debug_action_runs`, `encode_reference_document` under unrelated `parentOp`s, interleaved with
  our `op=b2be59e1`). Nothing collided — the reference Doc is not a scenario clone — but a lane
  guard that asserts on "the last N log events" will be flaky. **Deliberately dropped, because**
  every guard stage 4 plans is scoped by `docId`/`op`, not by recency.

**Next stages must know**

- **Do not flush the canonical reference Doc again until `gts-1ibp` lands.** Every flush costs
  another character of formatting drift on the four records that carry inline runs. Read-only
  work against it (`tests/test_doc_oracle_reference.py`, `compare_doc_sheet`, `apt pull`) is safe
  and unlimited.
- The bless diff is already reviewed record by record and written onto `gts-a7ko` as a note,
  split into the changes that are legitimate (link headers on all 21, bold+tab field names,
  `@`-spelling and chip convergence on ACT-3/4/5, ACT-7's status moving to end of line per
  gts-v0py, `<EMPTY>` records between actions) and the one group that is not (the drifted runs).
  A later session re-pulls and confirms only that second group moved — it does not have to
  re-derive the classification.
- `apt pull action-reference` exits **3** (preservation) purely because the golden is stale; that
  exit code is not evidence about the Doc.
- `sync_document` answered `result: null` on a successful forced flush — the stage-2 handoff's
  `'locked-skip'` sentinel is the only value worth checking; `null` is the ordinary success shape.

**Deliberately not done**

- **The bless (`gts-a7ko`).** In scope for this stage on paper. Blessing now would freeze
  `gts-1ibp`'s drift into the golden — the precise failure mode this plan was written to stop —
  so the bead is open, blocked, and carries the reviewed diff.
- Repairing the four drifted records by hand. It has to follow the writer fix, or the next flush
  re-drifts it; it is item 3 of `gts-1ibp`'s AC.
- Fixing `_buildFlushRequests` here. The stage's *Must not* forbids widening, and the fix is a P0
  with its own oracle (two pulls with a flush between must be byte-identical).
- Full `pytest -x`. `gts-imai` carries `regression=pending`.

### 4 — apt-lane-guards

**Partially closed 2026-08-29.** Beads `gts-omoy` ✓ and `gts-lu13` ✓, both `regression=pending`.
`gts-p150` remains **open and blocked** (depends on `gts-a7ko`, itself blocked on the stage-3 P0
`gts-1ibp`). The stage does not close — same shape as stage 3's partial close, same upstream
blocker.

**Done**

`gts-omoy`: `tests/helpers/version.py` gained `read_expected_target()` and
`check_deployed_build(webapp_url)`, wired as a new session-scoped autouse fixture
`_check_deployed_build` in `tests/conftest.py` (runs before `_check_auth_session_alive`, gated
by `_session_is_no_live_session` like the other pre-flight fixtures). It GETs `?cmd=version` —
answered ahead of every auth gate on both `doGet`/`doPost` (`src/WebApp.js`
`_handleVersionRequest`) — and `pytest.exit`s the whole run on a version *or* target mismatch,
naming expected vs. actual and `pnpm run deploy:test`. Proven red offline
(`tests/test_deployed_build_guard.py`, 6 passed): stale version, wrong target, and a non-JSON
body (propagation lag) each raise a diagnosable `RuntimeError`. Live-verified directly (one GET,
no pytest) against the real TEST deployment — matches — and against a bogus URL — diagnosable
`HTTPError`, not a bare traceback.

`gts-lu13`: the guard is wired directly into `ScenarioSession.sync()` (`scn/session.py`), not a
lane opt-in — every live lane (a real `Reporter`, gated by `isinstance(self._reporter,
NullReporter)`) inherits it automatically. Pure core is
`tests/helpers/sync_coverage.py` (`scan_coverage_problems`/`deleted_row_problems`), unit-tested
offline in `tests/test_sync_coverage.py` (13 passed), including two direct reproductions of the
2026-08-29 state (scanned count=1 vs. 21 declared; 20/21 sheet rows Deleted) and an op-id
correlation test (gts-obry.1's `matches_op`) proving a concurrent session's log entry cannot
satisfy this call's claim. The live wrapper (`assert_sync_coverage`) correlates `sync.scanned` by
a freshly generated `opId` threaded through `_post_fixture`'s `extra` — confirmed live by reading
`src/WebApp.js:543-544`: `doPost` calls `GasLogger.startOp(payload.opId)` for every route, so the
adopted op id chains to `SyncManager.js`'s `sync.scanned` regardless of action name — and calls
`find_sheet_actions` for the Deleted-row check (no doc parse; the design note's "without a doc
parse" cheap guard, distinct from `assert_doc_sheet_agreement`). `expected_min` is
`session._appended_actions`, mirroring the existing `chip.checked_count > 0` convention already
in `verify_all_expectations`.

Both design questions from the bead descriptions are answered by this wiring, not left open:
"where do the guards live so a new lane inherits them by default" → `ScenarioSession.sync()` /
`conftest.py` autouse fixture, not per-lane opt-in. "source of the expected version" →
`src/Version.js` (via `read_expected_version`/`read_expected_target`), the same file the deploy
stamper writes.

**Found**

- `tests/test_scn_session.py` (42 tests, mocked `_http_post`, no `request` passed →
  `NullReporter`) has no `no_live_session` marker, so a real pytest session collecting it also
  ran the new `_check_deployed_build`/`_check_auth_session_alive` autouse fixtures live. Both
  passed silently — **fixed now** by observing rather than editing: this incidentally
  corroborates `gts-omoy`'s guard against the real environment beyond the offline proof, and
  confirms `gts-lu13`'s `NullReporter` gate keeps the mocked-HTTP unit tests from being reached
  by the new `find_sheet_actions`/log-query calls (none of which appear in the mocked
  `captured` payload assertions, which would otherwise have broken).
- No live lane has been observed failing `gts-lu13`'s guard for real: the 2026-08-29 conditions
  no longer reproduce live (stage `apt-repair`'s handoff — the failure was already gone before
  that session began). The plan's AC3 explicitly allows "a synthetic reproduction" for exactly
  this reason; **deliberately not** forced live by re-breaking a shared TEST document.

**Next stages must know**

- `gts-p150` cannot proceed until `gts-1ibp` (stage 3's P0) lands and `gts-a7ko` re-blesses the
  corpus. Nothing in this stage's work depends on that in the other direction — `gts-omoy` and
  `gts-lu13` are unaffected by the drifted inline runs.
- Every `scn.sync()` call in the live suite now makes one extra `find_sheet_actions` HTTP call
  and (when `gasLogDir` is set) one extra log query, scoped by a fresh `opId` per sync. This is
  the same call/query shape `assert_doc_sheet_agreement` already uses elsewhere, so no new
  Axiom/WebApp load pattern — but it is a per-sync cost across the whole suite, not validated
  against a full-suite timing run (full `pytest -x` not run).
- `_check_deployed_build` fires before `_check_auth_session_alive` — a stale TEST deployment now
  aborts the run before Playwright even launches, rather than failing test-by-test.

**Deliberately not done**

- `gts-p150` (pristine-restore fixture). Blocked, not attempted — its own dependency chain
  (`gts-a7ko` → `gts-1ibp`) is stage 3's unresolved P0, outside this session's *Must not*.
- A real live demonstration of `gts-lu13`'s guard failing (as opposed to the offline synthetic
  one) — the failure conditions it detects no longer exist in the live environment to reproduce.
- Full `pytest -x`. Both `gts-omoy` and `gts-lu13` carry `regression=pending`.

### 7 — doc-truth

**Partially closed 2026-08-29.** Bead `gts-blia` ✓ (`regression=pending`); `gts-c9dd` remains
**open and blocked** — it depends on `gts-ru4c` (stage `apt-corpora-rebuild`), still open. The
stage does not close.

**Done**

`docs/CONTEXT.md` corrected (`gts-blia`), all four ACs:

1. Purpose paragraph now names the **verified team portal** (ADR-0021) alongside the Add-on
   sidebar as user-facing surfaces, and states the ActionSheet is edited directly only by an
   administrator.
2. Stakeholders table: `Action owner` and `Reviewer / manager` rows rewritten to name the
   portal (View A team list / View B doc view) as their actual surface — not the ActionSheet,
   which per this bead's premise they never had — with the ActionSheet path kept only as an
   administrator's alternate route.
3. Organizational Constraints gained a bullet: the ActionSheet is administrator-only; team
   visibility for everyone else is the portal's per-team `NONE`/`VIEW`/`EDIT` tier
   (`src/AccessControl.js`), not spreadsheet sharing.
4. Core Capabilities gained a bullet for the portal (GitHub Pages static frontend,
   `list_team_actions`/`get_document_actions` routes, GIS + NUUC-Dispatch signed-assertion
   identity, ADR-0021), distinct from the existing anonymous chip-preview-notice bullet, which
   is now named as the portal's unauthenticated fallback (per ADR-0021's Decision §4).

Full note (the same text) is on `gts-blia`.

**Found**

- **`docs/security-architecture.md` predates ADR-0021 and is silent on the verified-portal
  identity path.** Its §1 identity table and §2 trust-boundary diagram cover only
  Add-on(end-user)/WebApp(deployer) — nothing about the GIS-verified external caller whose
  signed NUUC-Dispatch assertion bypasses `WEBAPP_SECRET` by design
  (`_verifySignedAssertion`/`src/AccessControl.js`, ADR-0021). No contradiction was found with
  what was written into CONTEXT.md — the security doc simply says nothing on the subject, so
  AC4's "the two documents agree" is satisfied only in the weak sense of non-contradiction, not
  active agreement. **Bead `gts-wxz1`** (not fixed here: extending the threat-model findings
  list is a larger piece of judgment than this bead's AC scope).
- **`docs/verified-team-portal-plan.md`'s own header still says "Draft / assumptions unproven —
  do not propagate to CONTEXT.md ... until Spikes S1 + S2 pass,"** but the portal is fully
  built and shipped (ADR-0021, Accepted 2026-07-31; live routes in `src/WebApp.js`,
  `src/AccessControl.js`, `src/DocView.js`, `src/TeamActionWrite.js`). The header is stale.
  **Deliberately dropped, because** the working plan is a spike-planning artifact whose
  retirement is stage `plan-retention`'s general concern (`gts-flu4`), not a fresh finding
  needing its own bead — flagging it here so that stage does not have to rediscover it.
- **UC-B's `Actor: Action owner (ActionSheet side)` line** carries the same stale assumption
  this bead was filed to fix, but AC1–4 scope `gts-blia` to Stakeholders/Constraints/Core
  Capabilities, not Use Cases. **Deliberately dropped** — left as a note for whoever next
  touches UC-B; `use-case-quality-check` applies then, not here.

**Next stages must know**

- `gts-c9dd` cannot proceed until `gts-ru4c` (stage `apt-corpora-rebuild`) closes. Nothing in
  `gts-blia`'s work depends on that in the other direction.
- The corrected surface model's authoritative source, if a later session needs to re-verify it,
  is ADR-0021 plus the live `src/WebApp.js` route list (`verify_and_resolve_access`,
  `list_team_actions`, `list_my_teams`, `team_sync_document`, `get_document_actions`,
  `team_edit_action`, `team_patch_status`) — not `docs/verified-team-portal-plan.md`, which is
  the superseded working draft those routes grew out of.

**Deliberately not done**

- `gts-c9dd` (dangling decision-number citations). Blocked on `gts-ru4c`, outside this session's
  *Must not*.
- Extending `docs/security-architecture.md` for the ADR-0021 gap — `gts-wxz1`.
- Retiring the stale header on `docs/verified-team-portal-plan.md` — left for stage
  `plan-retention`.
- Full `pytest -x` — not applicable; this stage's change is documentation-only.
  `gts-blia` carries `regression=pending`.
