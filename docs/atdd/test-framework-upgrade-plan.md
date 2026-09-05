# test-framework Upgrade Plan — GActionSheet

**Working scratch. Not a permanent home.** Produced by `$DEVSTANDARD/test-framework/test-bootstrap.md`
Phase 1.5 (Use Case 2 — Upgrade). Retire this file once Phase 3's beads are filed and its
decisions have landed in `docs/atdd/project-testing-guide.md` and `docs/atdd/harness-design.md`.

Branch: `test-framework-upgrade`. Phase 1 confirmed by operator 2026-09-04.

---

## Section 1 — Signal column

Diagnostics run verbatim. `python3 $DEVSTANDARD/tools/test-suite-diagnostics.py --root .
--ac-list-cmd "<python -c 'import scn.contract as c; print(chr(10).join(c.AC_REGISTRY))'>"
--live-pattern "." --format text`, generated 2026-09-05T06:28:10+00:00.

```
run: run-20260905T061655Z   source: test-results/duration-log.jsonl

signal                  measured                                                                    standard        verdict
----------------------  --------------------------------------------------------------------------  --------------  -------
suite size              940 test functions in 101 files; 15 parametrize use(s); 8 collected in run  T6              review
AC ratio                25.4:1 (940 functions / 37 ACs)                                             T24 / ADR-0011  review
duration concentration  4 tests (50.0%) hold 73.2% of 5.3 min; cheapest 0 (0.0%) hold 0.0%          H4              ok
duration budget         1 test(s) over ceiling (1 live > 60.0s, 0 other > 30.0s)                    H4 / H5         review
failure rate            7.6% of 45668 executions failed; 14.6h of 74.2h (19.6%) spent failing       H8              review
boundary faults         11 of 21 classified failures match boundary patterns (52.4%)                H6 / H7         review
ticket-named artifacts  0 name(s) encode a tracker id                                               H11             ok
tier markers            5 declared; 68 module(s) carry none                                         H3              review
AC staleness            36 of 37 AC(s) uncovered across 3 run(s)                                    H10             review

wall-share concentration (H4):
   60.3% of wall time is held by 3 test(s) (37.5% of the suite)
   73.2% of wall time is held by 4 test(s) (50.0% of the suite)
   83.4% of wall time is held by 5 test(s) (62.5% of the suite)
   95.4% of wall time is held by 7 test(s) (87.5% of the suite)

over-budget tests (H5 waiver candidates, slowest first) — against the tool's DEFAULT ceilings
(30s non-live), before this project declares its own:
     93.5s  tests/test_menu_entry_points.py::test_menuSync_sweeps_registered_doc
     47.7s  tests/test_menu_entry_points.py::test_menuSyncActiveDoc_converged_doc_emits_no_forceFlush
     40.6s  tests/test_menu_entry_points.py::test_menuForceRefreshActiveDoc_flushes_converged_action
     32.3s  tests/test_menu_entry_points.py::test_menuSyncActiveDoc_syncs_active_doc
```

**Two signals are not what they appear and must not be read at face value:**

- `ticket-named artifacts: 0 … ok` is a **false negative**. The tool's default pattern
  (`\b[A-Z][A-Za-z]{1,}-(?:\d{2,}|[a-z0-9]{4})\b`) expects a `Prefix-slug` form. This project
  strips the `gts-` prefix in filenames, so `test_b7_write_routes.py`, `test_f3me1_…`,
  `test_f3me2_…`, `test_hroj_…`, `test_hztp_…`, `test_kkm7_…`, `test_p9ra_…`, `test_pulj_…`,
  `test_uuse_…`, `test_zc0w_…` and `test_adr0027_…` all evade it. The true count is ≥11 (F6).
- `duration budget` and the wall-share block are computed over a run that **collected 8 tests**,
  not the 940 the suite holds. They are directionally true (the `test_menu_entry_points` module
  dominates) but are not a suite-wide profile. Same caveat governs `AC staleness: 36 of 37` —
  see escalation **E2**.

**Re-baseline (`R22`, `gts-u6ew.4`, 2026-09-05).** The 10 placeholder entries (`t`, `t1`, `t2`,
`uc AC-1`, `uc AC-2`, `uc TEST`, `uc1 AC1`–`AC4`) were purged from `scn/contract.AC_REGISTRY` into
a separate `AC_SELFTEST_FIXTURES` dict that `scripts/check_coverage.py` does not diff. Diagnostics
re-run against the same `duration-log.jsonl`/JUnit history (`--ac-list-cmd` unchanged, now
enumerating 27 entries):

```
AC ratio       34.8:1 (940 functions / 27 ACs)      — was 25.4:1 (940 / 37)
AC staleness   26 of 27 AC(s) uncovered across 3 run(s)  — was 36 of 37
```

The staleness caveat above still applies (the window is small, real JUnit runs by mtime, not a
verified full-suite profile) — `E2`/`H10` stay `unknown` pending an operator-initiated full sweep
(`gts-u6ew.16`). This re-baseline removes one of `H10`'s two named contributors (the placeholder
entries); the other (6 of 11 journeys draining no tagged AC) is untouched by this stage.

---

## Section 2 — Recommendation table

Each row states the change to make, at the file and symbol level. The substantive ones are
expanded in §2b. Leave `Operator decision` empty until you fill it. Valid entries: `Approve` /
`Modify: <instruction>` / `Escalate` / `Discard`.

| # | Finding | Action | Recommended change | Prereq | Standard | Operator decision |
|---|---------|--------|--------------------|--------|----------|-------------------|
| R1 | F8 — guide/harness-design cite stale ID ranges (`T1`–`T24`, `I1`–`I11`) and omit the new sources | `Conform` | In both docs' §0: widen the ranges to `T1`–`T25` / `I1`–`I12`, and add three rows — `harness-standards.md` (`H1`–`H13`), `ADR-0011` (AC-as-obligation, disposition ordering), `bd/SKILL.md` §Disposition. Repoint the two principle paths from `knowledge-base/methodology/testing/bdd/` to `$DEVSTANDARD/test-framework/`. | none | `ADR-0012` | Approve |
| R2 | F8 — project docs state harness-shaped rules in the project layer | `Conform` | Guide §1's "platform execution ceiling" and §2's tier prose state harness constraints. Replace each statement with its `H` citation and move the project's *number* to harness design §9a, so the value lives in one place (`I6`). | R1 | `ADR-0012` boundary rule | Approve |
| R3 | F1 — no boundary-fault outcome class | `Instrument` | Add `scn/outcomes.py` with a `BoundaryFault(RuntimeError)` type and one `classify(exc) -> PASS\|ASSERTION_FAILURE\|BOUNDARY_FAULT` helper (`I12`). Raise `BoundaryFault` at `scn/session.py`'s four retry-exhaustion sites (lines 218/223/239/260) instead of bare `RuntimeError`. Consume it in the existing `pytest_runtest_makereport` hook (`tests/conftest.py:171`). See §2b. | none | `H6` | Approve |
| R4 | F1 — retry is per-call transport logic, not a harness policy; attempts unrecorded | `Conform` | Keep the existing bounded policy (`_HTTP_POST_MAX_ATTEMPTS=5`, `_HTTP_POST_RETRY_DELAY_S=3`, exponential) but move both constants next to the `H4` ceiling in one settings module, and attach `attempts` to the result via `user_properties` so every result carries it. See §2b. | R3 | `H7` | Approve |
| R5 | F1 — fault rate and failed-wall-time share only computable offline | `Instrument` | Add a session-end summary (`pytest_sessionfinish`) printing execution failure rate and share of wall time spent on failed executions, computed from the records `duration_instrumentation.append_jsonl` already writes. The numbers exist; nothing reports them. | R3 | `H8` | Approve |
| R6 | F2 — journey charter lacks the columns a disposition is decided against | `Author` | Rewrite guide §6 to the template's charter shape: add **entry points it is call-site for**, **AC ids it drains**, and **why separate from each adjacent journey** to the existing 11 rows. Populate the first two from `ENTRY_POINT_REGISTRY`/`AC_REGISTRY`; the third is authored per journey. A journey with no defensible line is recorded as a merge candidate with a bead — not merged here. | registries (exist) | `ADR-0011` §5 | Approve |
| R7 | F3 — no disposition record, audit command, or gate | `Author` | Add guide §9: where a disposition lives (bd `disp:<n>` label + `## Disposition` section), the audit command (the two `bd`/`jq` commands from `bd/SKILL.md` §Disposition), and the gate. Wire the audit into `merge-gate` so a `[TST]` bead with no disposition fails the gate. Seed the escalation log empty. | R6 | `ADR-0011` | Approve |
| R8 | F4 — `test:full` is one invocation over both tiers; no gate | `Conform` | Add `"test:regression"` to `package.json`: run `test:local` to completion, and run `test:live` only on its success (`&&`). Repoint `CLAUDE.md` and the gates at it. Keep `test:full` or retire it — it must not stay the cited entry point. See §2b. | none | `H1`, `H13` | Approve |
| R9 | F4 — no failure-first ordering | `Conform` | Add `--ff` to both tier invocations inside `test:regression`. Assert collection size is unchanged (`--ff` reorders; `--lf` subsets — the latter must stay operator-only). | R8 | `H2` | Approve |
| R10 | F5 — no ceiling declared, no over-ceiling category | `Instrument` | Add `CEILING_LIVE_S` / `CEILING_OTHER_S` to `tests/duration_instrumentation.py` beside the existing `REL_THRESHOLD`/`ABS_SLACK_S`, and an over-ceiling verdict in `build_record`. **Note the design collision in §2b** — that module is deliberately report-only, and `H4` wants a failure. | R8 | `H4` | Approve |
| R11 | F5 — 4 over-budget tests, no waiver list | `Consolidate` | Deferred — see §2a bundle G. When it runs: apply `H5`'s mandatory order to `test_menu_entry_points.py` (`T6` permutations to a shared fixture table → `T12` deterministic logic to focused helpers → `T21` fold the remaining round-trips into an existing journey), and only then waive with a bead id. | R10 + a real profile | `H5` | Approve |
| R12 | F7 — gap-diff cannot separate "uncovered" from "unreached this run" | `Instrument` | Extend `scripts/check_coverage.py`: have `_collect()` also read the outcome class R3 emits, and `_report()` print `uncovered` and `unreached this run` as two sets with distinct exit-code meaning. Today an AC missed because Google 500'd is indistinguishable from one nobody wrote a test for. | R3 | `H9` | Approve |
| R13 | F7 — no AC staleness check | `Author` | Add a check flagging every `AC_REGISTRY` entry with zero drained expectations across the last N=3 full regression runs, reading the same JUnit history. Run it with the gap-diff. Each flagged AC resolves as retire-the-AC (`T25`) or restore-the-coverage — never left standing. | R12 | `H10` | Approve |
| R14 | F6 — ≥11 test files encode a bead id in the filename | `Escalate` | Recommended: add the lint now (see R14a); decide the renames per **E3**. | none | `H11` | Approve — recommended answer |
| R14a | F6 — nothing prevents the next ticket-named file | `Conform` | Add a collection-time check rejecting a new test file whose name matches this project's bead-slug shape, with the existing ≥11 as a named allowlist that only shrinks. This is the durable half of `H11` and is independent of the rename decision. | none | `H11` | Approve |
| R15 | F6 — the diagnostics' default ticket pattern misses this project's shape, so `H11` self-reports green | `Conform` | Record the correct invocation in harness design §9a: `--ticket-pattern '(?:\b(?:gts-)?[a-z0-9]{4}\b)'` or equivalent, so a future diagnostics run measures `H11` rather than passing it by default. One line. | none | `H11` | Approve |
| R16 | `H3` — `conftest.py:78` stamps `live` on unmarked items rather than failing collection | `Escalate` | Recommended: **decline** `H3` with the reason and date in §9a, and change no code. Rationale in **E1**. | none | `H3` | Approve — recommended answer |
| R17 | F7 — 36/37 ACs measured uncovered, over runs too small to be a profile | `Escalate` | Recommended: record `H10` as `unknown` and let the next operator-initiated full sweep settle it. Rationale in **E2**. | none | `T24`, `H10` | Approve — recommended answer |
| R18 | Missing harness-design §9a and §9b | `Author` | Install both template sections into `docs/atdd/harness-design.md`, filling §9a from the verdicts this table settles (including R16's `declined` and R17's `unknown`) and §9b from the existing `ENTRY_POINT_REGISTRY`. The `H5` waiver table is created empty — R11 fills it or it stays empty. | R1 + settled verdicts | `ADR-0012` | Approve |
| R19 | Guide §7 is a hand-maintained view of `ENTRY_POINT_REGISTRY` | `Conform` | Either generate §7 from the registry, or state in §9b the diff that fails when the two disagree. Do not leave a second hand-maintained enumeration (`I6`). | R18 | `H12`, `I6` | Approve |
| R20 | F9 — 940 test functions against 37 ACs (25.4:1) | `Defer` | File one bead recording the ratio and the date measured. No stage in this adoption; revisit when a full-sweep profile exists. | none | `T6` | Approve |
| R21 | `H12` is already met | *(none)* | Record `conformant` in §9a, citing `scn/contract.ENTRY_POINT_REGISTRY` (37 entries, 13 deferred with beads) and `scripts/check_coverage.py` as its reader. No code change. | R18 | `H12` | Approve |

### §2d — Finding raised during Phase 2 (2026-09-05)

**F10 — 10 of the 37 `AC_REGISTRY` entries are placeholders, not acceptance criteria.**
`scn/contract.py:61` and `:78`–`:86` register `t`, `t1`, `t2`, `uc AC-1`, `uc AC-2`, `uc TEST`,
`uc1 AC1`, `uc1 AC2`, `uc1 AC3`, `uc1 AC4` — described in-file as "Generic test marker" / "Use case
AC-1" / "Test scenario 1". These are harness self-test fixtures that were registered into the
production AC registry.

This changes two Phase 1 signals materially: the real AC count is **27, not 37** (AC ratio 34.8:1,
not 25.4:1), and up to 10 of the "36 of 37 uncovered" are ACs that *cannot* be covered because no
production behaviour corresponds to them. It does not overturn E2 — the remaining gap is still
unexplained and still needs a full sweep to settle — but it removes a chunk of it for free.

| # | Finding | Action | Recommended change | Prereq | Standard | Operator decision |
|---|---------|--------|--------------------|--------|----------|-------------------|
| R22 | F10 — 10 placeholder entries pollute the production AC registry | `Conform` | Remove the 10 from `AC_REGISTRY`; if the harness self-tests need them, give them a separate fixture registry that `check_coverage.py` does not diff against. Re-run the diagnostics afterwards to re-baseline the AC ratio and staleness signals. | none | `T24`, `I6` | |

Recommended for increment 1 — it is small, has no prerequisite, and every later coverage number
is measured against a denominator that is currently wrong by 27%.

### §2c — Conflict check (run at the Phase 1.5 gate, 2026-09-04)

All 22 rows approved; the three escalations take their recommended answers (E1 `declined`,
E2 `unknown`, E3 lint-now + partial rename). Four things the approval implies that are not
obvious from the rows themselves:

1. **R18 has a prerequisite break against the increment order, and it resolves by writing state
   rather than by resequencing.** §9a needs a verdict for every `H` id, but `H6`/`H7`/`H8` are
   settled by increment 2 and `H9`/`H10` by increment 4 — while R18 sits in increment 3. §9a is a
   record of *current* state, not final state, so it is written with `waived: <bead id>` for every
   standard a filed bead will later flip to `conformant`. **This makes Phase 3's bead filing a
   hard prerequisite of increment 3**, not merely of the increments that execute the work.
2. **R11 is deferred but still needs a bead filed now.** `H4` cannot be recorded `conformant`
   while 4 over-budget tests stand, so §9a records it `waived` — and `H5` says a waiver without an
   issue id is not a waiver, it is an unrecorded exception. The deferred consolidation gets a bead
   in Phase 3 regardless of having no stage.
3. **Half of R5 does not actually depend on R3.** The execution failure rate and failed-wall-time
   share are computable from the records `append_jsonl` already writes; only the *boundary-fault*
   split needs the classifier. That half can ship in increment 1 for free if convenient — the
   dependency in the table is on the split, not the rate.
4. **Adoption will be partial by design, and that is the expected first-pass end state.** With
   `H3` `declined` and `H10` `unknown`, the bootstrap's success criteria will not all hold when
   Phase 3 completes. `H10` closes on the first operator-initiated full sweep (E2); `H3` never
   closes because it is declined, not waived — there is no issue to chase.

One item to verify at implementation time rather than now: R9's `--ff` interacts with
`test:local`'s `-n 4 --dist worksteal`. Failure-first reorders the collection before xdist
distributes it, so the intent survives, but confirm empirically that previously-failing tests
actually land early under worksteal before claiming `H2` conformant.

### §2b — The three recommendations with real design content

**R3/R4 — where the classifier hooks in.** The wiring already exists and is unused for this
purpose: `tests/conftest.py` has both `pytest_runtest_logreport` (line 110) and a
`pytest_runtest_makereport` hookwrapper (line 171). The missing piece is a *signal* to classify
on. Today `scn/session.py` raises a bare `RuntimeError` at all four retry-exhaustion sites
(218 `HTTP 404` after 5 attempts, 223, 239 read timeout, 260), which is indistinguishable from any
other error by the time it reaches the report. Introducing `BoundaryFault(RuntimeError)` and
raising it at exactly those four sites makes the classification a type check rather than message
matching — and message matching is what the diagnostics has to do offline today, at 52% precision
against patterns it guesses. Everything downstream (R5, R12) reads the class, so this is the one
that must be right.

**R8 — why not just reorder `test:full`.** `test:full` currently runs one pytest invocation and
then Playwright. `H1` requires two invocations with a gate between, so the fast tier's failures
report in seconds instead of at the end of a live run. The change is small — `pnpm run test:local
&& pnpm run test:live` — but it is a *behaviour* change, not a cosmetic one: a red fast tier now
stops the run, where today it does not. That is the point, and it is worth stating explicitly
before approving.

**R10 — a genuine collision to resolve, not just a constant to add.**
`tests/duration_instrumentation.py`'s module docstring says: *"Report-only: nothing here can fail
or skip a test."* `H4` says an over-ceiling test *"is a harness-reported failure, not a slow
pass."* These are incompatible as written. Three ways out, and this needs a decision when R10 is
picked up: (a) add the ceiling to that module as a reported verdict only, and let a separate
gate turn it into a failure — preserves the module's testability contract; (b) relax the
report-only rule and fail in-module; (c) declare `H4` `waived` at report-only, with a bead. I
recommend (a) — it keeps the pure-logic/hook-wiring split the module was deliberately built with
(`T12`), and the failing is the gate's job anyway.

No recommendation in this table deletes, rewrites, or moves a test. R11 proposes consolidation;
R14/E3 proposes renames. Both execute later, each under a disposition of its own.

---

## Section 2a — Value ranking and proposed increments

The `Prerequisite` column above and Phase 3's stage list give a **dependency** order: what cannot
precede what. That is not a value order, and the two disagree in one place worth naming — Phase 3
puts Budget (`H4`/`H5`) at stage 5 as a headline stage, but on this project's measured numbers the
consolidation half of it (R11) is the **lowest**-value item in the table. See A4 below.

Value is judged against measured signal, not against how prominent the standard is. Effort is
S / M / L, and is a shape estimate, not a schedule.

| Bundle | Recommendations | Value evidence | Effort | Verdict |
|--------|-----------------|----------------|--------|---------|
| **A — Feedback loop** | R8, R9 | The framework's own `H1` rationale measures the failure this fixes: 39 failures costing 0.3s combined, last reported 72.7 min into a run. This project has exactly that shape — a fast tier that exists, is separately invocable, and simply is not gated. | **S** — a `package.json` script plus `--ff` | **Do first.** Best cost:value in the table; pays out on every run from the first one. |
| **B — Boundary faults** | R3, R4, R5 | The largest measured cost anywhere in Phase 1: **14.6 of 74.2 hours (19.6%) of wall time spent on failing executions**, at a 7.6% execution failure rate, with **52% of classified failures being platform faults, not defects**. Also unblocks R12 → R13. | **M** — one classifier (`I12`), lift the existing `scn/session.py` retry to the harness layer, add two numbers to the run report | **Highest value.** Independent of everything else; no prerequisite. |
| **C — Adoption binding** | R6, R7, R1, R2, R18, R19, R21 | No measured pain relief — this is what makes the framework *bind* on future work. Without R6/R7 no `[TST]` item can be dispositioned, which is what `blocking-adoption` means. R1/R2/R18/R19/R21 are paperwork with zero operational effect, but they are most of the "adoption complete" criteria. | **M** for R6/R7; **S** for the rest, and the rest batch into one sitting | **Do, but as governance not firefighting.** R6 before R7. |
| **D — Measurement, not yet budget** | R10, R15 | R10 declares the ceiling constant so over-ceiling becomes a reported category. Its value here is *getting the suite-wide profile*, which does not exist yet. R15 is one line that stops `H11` self-reporting green. | **S** | **Do with A.** Cheap, and D is the precondition for judging R11 honestly. |
| **E — Coverage truth** | R12, R13 | Gated on **E2**. If AC coverage really is near-zero, this is second only to B. If 36/37 is a measurement artifact of 8-test runs, it is modest. The evidence genuinely does not settle it. | **M** | **Hold for E2.** Do not build until the signal is real. |
| **F — Naming** | R14a (lint), R14 / E3 (renames), R15 | `H11`'s value is that you can find the test covering a behaviour by name. A lint that blocks *new* ticket-named files captures most of that permanently; renaming the existing ≥11 captures the rest once, against real churn cost (bd bodies, lessons-learned docs, `ID-map.md`, gate history all reference those paths). | **S** lint / **M** renames | **Lint now, renames on next touch.** ~90% of the value at ~10% of the cost. |
| **G — Consolidation** | R11 | The 4 over-budget tests total ~214s. Against 74 hours of measured wall time that is **noise** — and the profile they come from collected 8 tests, so we do not actually know the suite's real duration distribution yet. This is also the only item that touches existing tests, i.e. the highest-risk one. | **L** | **Defer** until D produces a real suite-wide profile. Doing it now optimises a number we have not measured. |
| **H — Suite size** | R20 | 25.4:1 function-to-AC ratio is real but is a standing condition, not a defect this adoption can close. | — | **Already deferred.** Tracker item, no stage. |

### Proposed increments

Each is independently shippable and leaves the project better than it found it — none is a
half-migration that has to be finished to be worth having.

| # | Contents | Why this boundary |
|---|----------|-------------------|
| **1** | A + D (R8, R9, R10, R15) | All-S effort, no prerequisites, immediate payoff on every run, and it produces the measurement that later increments are judged against. |
| **2** | B (R3, R4, R5) | The single largest measured cost. Independent, so it can run in parallel with 1 if you have the capacity. |
| **3** | C (R6, R7, then R1, R2, R18, R19, R21) | Governance. R6/R7 are the blocking pair; the rest is one batched doc sitting. After this, adoption *binds* on new work. |
| **4** | F-lint, then conditionally E and G | E unlocks when **E2** is answered. G unlocks when increment 1's ceiling has produced a full-sweep profile. F's renames ride along on normal touches. |

**If you only do one thing:** increment 1. **If you only do two:** add B.

**What is genuinely optional.** R11 (G) and the rename half of R14 (F) are the only items whose
omission costs nothing measurable today — both are recorded as a stated deviation rather than
silently skipped. Everything else is either cheap enough that skipping it is not a saving, or is
load-bearing for adoption.

---

## Section 3 — Escalation block

### E1 — `H3`: does this project conform, or decline with a reason?

**Question.** `H3` requires that an unmarked test **fails collection**. `tests/conftest.py:78`
instead stamps `live` on every collected item not carrying `no_live_session`, so classification is
total by construction and an unmarked new test defaults into the expensive tier.

**Candidate (a) — Conform.** Replace the stamping hook with one that errors on an unmarked item.
*Cost:* every new test file must remember a marker; a forgotten marker becomes a hard collection
error rather than a slow-but-correct live run. The current design was a deliberate choice
(`gts-aqpk`), and reversing it trades a silent cost for a loud stop.

**Candidate (b) — Decline, with the reason recorded.** Record `declined` in harness design §9a with
the reason and date. *Cost:* `H3`'s stated guarantee weakens on paper. *Argument for:* the failure
`H3` exists to prevent is **directionally impossible here** — `H3`'s rationale is that an unmarked
test "silently joins whichever tier the default selection catches, which is how live tests end up
inside the fast gate and destroy `H1`'s guarantee." This project's default is *live*, not fast. A
forgotten marker can only make the live tier slower; it can never put a live test inside the fast
gate. `H1`'s actual guarantee is preserved by construction.

**Recommendation:** (b). Note this is a `declined`, not a `waived` — there is no issue to close.

### E2 — Is the 36/37 uncovered-AC signal a real coverage gap or a measurement artifact?

**Question.** The last 3 logged runs collected as few as 8 tests. `AC staleness: 36 of 37` and
`AC ratio: 25.4:1` are computed against those. Separately, `$DEVSTANDARD/test-framework/README.md`
§Status notes independently records that "no live end-to-end run has shown nonzero coverage" for
`T24` in this very reference implementation — so the two possibilities are not equally likely, but
neither is settled.

**Candidate (a) — Establish the baseline now.** One operator-initiated full live sweep, its report
becoming the stage-1 measurement. *Cost:* an expensive live run against the shared TEST backend.
Project `CLAUDE.md` explicitly forbids me running the full sweep on my own initiative; this needs
your instruction. It also risks landing during other in-flight work on the shared target.

**Candidate (b) — Carry it as `unknown` and let the next sweep settle it.** `H10`/`H9` beads
(R12, R13) ship, and their acceptance evidence is the first full sweep you run for another reason.
*Cost:* the staleness check ships unvalidated against real data, and `H10` stays `unknown` in the
conformance table until then — which the success criteria explicitly count as not-yet-adopted.

**Recommendation:** (b), unless you already have a full sweep planned — in which case (a) costs
nothing extra.

### E3 — `H11` renames: all at once, or on next touch?

**Question.** ≥11 test files encode a bead id. `H11`'s rationale is that ticket-id naming
structurally defeats `ADR-0011`'s "enumerate the adjacent existing tests" step — you cannot find
the test covering a behaviour by name.

**Candidate (a) — One rename stage.** Rename all ≥11 files to behaviour-derived names in a single
change. *Cost:* one large diff; every external reference to those paths goes stale — bd issue
bodies, `docs/lessons-learned/`, `docs/atdd/ID-map.md`, and the `regression=pending`/gate history
that names them. A `git mv` keeps history, but the references do not follow.

**Candidate (b) — Rename on next touch, plus a lint blocking *new* ticket-named files.** *Cost:*
`H11` stays partly unmet for an unbounded period, and the disposition step stays degraded for
exactly the areas nobody is touching — which are the areas where a stale duplicate test is most
likely to be created.

**Recommendation:** (b) with the lint, plus a bounded exception: rename the files whose bead id
names a *behaviour* nobody can recover from the slug (`test_b7_`, `test_kkm7_`, `test_p9ra_`,
`test_zc0w_`, `test_uuse_`, `test_pulj_`) as one small stage, and leave those whose slug is already
descriptive enough in context (`test_hztp_actionsnapshot_read_coverage`,
`test_hroj_diagnostics_backstop`, `test_f3me1_append_idempotency`,
`test_f3me2_run_fixture_idempotency`, `test_adr0027_reference_document`) to next touch. This is a
third option; say so if you want it, or pick (a) or (b) plain.

---

## Section 4 — Processing instructions

## How to complete this file

1. Put a decision in the `Operator decision` column of every row.
2. Answer each question in the Escalation Block, or write `Defer`.
3. Save, then paste the Resume Prompt below.

### Resume prompt

I have recorded my decisions in <this file>. Please:
1. Read it back and confirm your understanding of each decision.
2. Flag any decisions that conflict with each other or break a prerequisite chain.
3. Produce the revised recommendation table.
4. Confirm readiness to proceed to Phase 2 — Alignment.
5. Do not begin Phase 2 until I confirm.
