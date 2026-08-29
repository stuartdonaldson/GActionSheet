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
| 2 | `act-force-refresh` | `gts-366c` | ○ | [IMP] WebApp force parameter on the document-sync route |
| 2 | `act-force-refresh` | `gts-gssn` | ○ | [TST] Force-refresh route coverage and force entry-point audit |
| 3 | `apt-repair` | `gts-imai` | ○ | [FIX] Repair the canonical reference Doc and its ActionSheet rows |
| 3 | `apt-repair` | `gts-a7ko` | ○ | [TST] Re-bless action-reference.apt.txt from the repaired doc |
| 4 | `apt-lane-guards` | `gts-p150` | ○ | [TST] Pristine-restore fixture for the reference corpus |
| 4 | `apt-lane-guards` | `gts-lu13` | ○ | [TST] Assert sync.scanned count and zero Deleted rows in every live lane |
| 4 | `apt-lane-guards` | `gts-omoy` | ○ | [INF] Deployed-build guard for live lanes |
| 5 | `apt-corpora-rebuild` | `gts-ru4c` | ○ | [TST] Re-author every scenario's expected corpus as the post-sync state |
| 5 | `apt-corpora-rebuild` | `gts-5st5` | ○ | [TST] Lint: input == expected is an error for a non-degenerate mutation |
| 6 | `apt-presentation` | `gts-dxgo` | ○ | [TST] Doc-side presentation assertions: person chip, ACT-N link run, status icon |
| 6 | `apt-presentation` | `gts-gkcy` | ○ | [TST] Sparse expected-parse annotation on hard records |
| 7 | `doc-truth` | `gts-blia` | ○ | [INF] CONTEXT.md: correct the user-facing surface model |
| 7 | `doc-truth` | `gts-c9dd` | ○ | [INF] Resolve dangling decision-number citations |
| 8 | `plan-retention` | `gts-flu4` | ○ | [INF] Staged-plan retirement must preserve the plan |
| — | *(filed at stage 1)* | `gts-1ej4` | ○ | [TST] Converge scn/surfaces.py DocReader onto the doc_inspect grammar oracle |

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
*(Corrected at Stage 0: the Docs menu item is already covered; the WebApp route is the gap.)*
**Why paired:** twin-ticket — the `[IMP]` route and its `[TST]` coverage freeze one contract.
**Model:** sonnet — the shape is settled; `force` already exists in `SyncManager.js:324`.
**Work-log:** per-stage.
**Must not:** widen into other unreachable entry points. Audit them, file them, do not fix them here.

### 3 — apt-repair
**Deliverable:** a canonical reference Doc where all 21 actions render correctly, with the sheet
agreeing — the pristine baseline every later stage restores from.
**Why paired:** re-blessing is only trustworthy in the same session that verified the repair.
**Model:** sonnet.
**Work-log:** per-stage.
**Must not:** bless anything the stage-1 parser has not confirmed. This is the exact step that
froze the defect last time.

### 4 — apt-lane-guards
**Deliverable:** a lane that goes red on a stale deployment, a short scan, or a *Deleted* row.
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
