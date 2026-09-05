# Staged Plan — test-framework v1.0.0 Adoption

**Contract:** Pattern D — `$DEVSTANDARD/doc-framework/planning-guide.md` §"Pattern D: Staged
Execution". Rules are cited, not restated.

**Epic:** `gts-u6ew` — [INF] Adopt DevStandard test-framework v1.0.0 (ADR-0011/ADR-0012)
**Plan of record:** `docs/atdd/test-framework-upgrade-plan.md` — value ranking in §2a, prerequisite
breaks in §2c, the finding raised mid-adoption in §2d.
**Branch:** `test-framework-upgrade`

**Status:** Stages 0–8 and 10 complete; stage 9 is the only stage left, and it is deferred (see
below). 18 beads filed, 17 staged, 1 deliberately unstaged. Stage 1 made the first
non-documentation change: `package.json` (`test:regression`) and
`tests/duration_instrumentation.py`/`tests/conftest.py` (H4 ceilings) — no test file touched. Stage
2 made the second: `scn/contract.py` (AC registry denominator) and `tests/conftest.py` (H11
collection-time lint) — no test file touched or renamed. Stage 5 made the first change to journey
test files themselves: six journeys retagged/rewired to drain a real AC id, and
`test_journey_acts_1_3.py` retired. Stage 6 is the plan's governance-binding stage: a new
`scripts/audit_disposition.py` gives `merge-gate` Step 2.5 a real command instead of hand-typed jq.
Stage 7 closes the `H12`/`I6` drift risk named in `harness-design.md` §9b: a new
`scripts/check_entry_point_registry_view.py` checks testing guide §7's and harness-design.md §9a's
stated entry-point counts against the registry's live counts every `test:local` pass. Stage 8 turns
that check around: `scripts/check_entry_point_extraction.py` checks the registry itself against
`src/`, and found 11 state-modifying handlers nobody had enumerated (registry 37 → 48). Stage 10
renamed the six tracker-id-slug test files the escalation decided on to behaviour-derived names and
shrank the `gts-u6ew.5` allowlist by six.

**Next Step:** None to run in this plan right now. Stage 9 (`budget-consolidation`, `gts-u6ew.14`)
is the only stage left open, and it is **deferred, not next**: its block below says do-not-start
until a real suite-wide duration profile exists, and producing one needs an operator-authorized
full live-tier sweep, which `CLAUDE.md`'s backstop rule forbids an agent starting on its own
initiative. It stays deferred until the owner authorizes that run — the same open item that holds
`H10` at `waived` (see §Open items requiring the owner). This plan has no further self-startable
work until that authorization lands.

Bootstrap Phases 1 (discovery), 1.5 (disposition planning) and 2 (alignment) are complete. This
document carries the staged remainder — Phase 3. **No stage here was executed by the bootstrap
prompt**; each runs as an ordinary work session under the normal gates.

---

## Execution order

| # | Stage | Bead | Status | Title |
|---|-------|------|--------|-------|
| 0 | plan-boundary | — | complete | *(gate only — no beads; see roll-up)* |
| 1 | regression-gate | `gts-u6ew.1` | open | [INF] Gate the regression run: network-free tier to completion, live tier only on success |
| 1 | regression-gate | `gts-u6ew.2` | open | [INF] Failure-first ordering within each tier, without subsetting the collection |
| 1 | regression-gate | `gts-u6ew.3` | open | [INF] Declare per-test duration ceilings and report the over-ceiling category |
| 2 | measurement-hygiene | `gts-u6ew.4` | closed | [INF] Purge 10 placeholder entries from the production AC registry |
| 2 | measurement-hygiene | `gts-u6ew.5` | closed | [INF] Block new tracker-id-named test files at collection time |
| 3 | boundary-faults | `gts-u6ew.6` | closed | [INF] Distinguish a boundary fault from an assertion failure as a first-class outcome class |
| 3 | boundary-faults | `gts-u6ew.7` | closed | [INF] Lift the bounded retry to a harness policy and record attempts on every result |
| 3 | boundary-faults | `gts-u6ew.8` | closed | [INF] Emit boundary-fault rate and failed-wall-time share every run |
| 4 | coverage-truth | `gts-u6ew.15` | closed | [INF] Split uncovered from unreached-this-run in the coverage gap-diff |
| 4 | coverage-truth | `gts-u6ew.16` | closed | [INF] Check AC staleness across the last 3 regression runs |
| 5 | journey-tagging | `gts-u6ew.12` | closed | [TST] Tag the six journeys that drain no AC into the traceability report |
| 5 | journey-tagging | `gts-u6ew.13` | closed | [TST] Resolve test_journey_acts_1_3: no defensible failure domain of its own |
| 6 | disposition-enforcement | `gts-u6ew.9` | closed | [INF] Wire the disposition audit into merge-gate |
| 7 | registry-derivation | `gts-u6ew.10` | closed | [INF] Stop testing-guide §7 drifting from the entry-point registry |
| 8 | registry-extraction | `gts-u6ew.11` | closed | [INF] Extract the entry-point registry from src/ instead of hand-authoring it |
| 9 | budget-consolidation | `gts-u6ew.14` | open | [TST] Bring test_menu_entry_points under the duration budget via the H5 resolution order |
| 10 | naming-cleanup | `gts-u6ew.17` | closed | [INF] Rename the six test files whose bead slug names no recoverable behaviour |
| — | *(unstaged, deliberate)* | `gts-u6ew.18` | open | [INF] Record the 25.4:1 test-function-to-AC ratio for later evaluation |

**Verify:** `bdls --stages` · `bdls --check` · `bdls --goals --stage <name>`

`gts-u6ew.18` is deliberately unstaged: plan R20 dispositions it `Defer` — a tracker item with no
stage, revisited only once stage 1 has produced a real suite-wide profile.

## Stage roll-up

| # | Stage | Status | Closed | Handoff |
|---|-------|--------|--------|---------|
| 0 | plan-boundary | complete | 2026-09-05 | §Stage 0 below |
| 1 | regression-gate | complete | 2026-09-05 | §Stage 1 below |
| 2 | measurement-hygiene | complete | 2026-09-05 | §Stage 2 below |
| 3 | boundary-faults | complete | 2026-09-05 | §Stage 3 below |
| 4 | coverage-truth | complete | 2026-09-05 | §Stage 4 below |
| 5 | journey-tagging | complete | 2026-09-05 | §Stage 5 below |
| 6 | disposition-enforcement | complete | 2026-09-05 | §Stage 6 below |
| 7 | registry-derivation | complete | 2026-09-05 | §Stage 7 below |
| 8 | registry-extraction | complete | 2026-09-05 | §Stage 8 below |
| 9 | budget-consolidation | deferred | | blocked on an operator-authorized full live sweep |
| 10 | naming-cleanup | complete | 2026-09-05 | §Stage 10 below |

---

## Stage 0 — plan-boundary *(complete, 2026-09-05)*

Gate only; no beads, so no `bd dep` edges bind stage 1 to it. Four exit conditions, all passed:

- **(a) Buffer discharged** — `docs/PENDING-UPDATES.md` does not exist. Nothing to discharge.
- **(b) Contract is Pattern D** — declared above; this document was authored as Pattern D, not
  converted from a B/C doc.
- **(c) Plan lint clean** — `bdls --check`: 0 errors. The 9 warnings are pre-existing
  `isolated-stage`/`unordered-batch` findings on unrelated stages of other plans; none belongs to
  `gts-u6ew`.
- **(d) Recorded closed** — this block and the roll-up row above.

---

## Stage 1 — regression-gate *(complete, 2026-09-05)*

`pnpm run test:regression` (`test:local -- --ff && test:live -- --ff`) is now the single `H1`/`H13`
entry point, opening no live session unless the network-free tier is green and running both tiers
failure-first. `--ff`'s reorder was verified empirically to survive `test:local`'s
`-n 4 --dist worksteal` (synthetic `lastfailed` injection, not by touching a test — see
`harness-design.md` §9a's `H2` row). `H4` ceilings (`CEILING_LIVE_S`=60.0 / `CEILING_OTHER_S`=30.0)
are declared in `tests/duration_instrumentation.py` and every run now emits an `over_ceiling`
verdict per test; the report-only-vs-fail collision named in the plan was resolved as recommended
(§2b option a — module stays report-only, no `pytest.fail` added; the enforcing gate is separate,
not-yet-built future work, captured via `bd remember`). `harness-design.md` §9a's `waived` rows
already carried real `gts-u6ew.N` ids (from Stage 0's Phase 2 authoring) rather than the `plan R8`
placeholders the plan's §2c anticipated — no repointing was needed; verified by grep before
closing. `H1`/`H2`/`H13` flip to `conformant`; `H4` stays `waived` against `gts-u6ew.14` (deferred
consolidation, stage 9) since the 4 over-budget `test_menu_entry_points` tests are unchanged.
`CLAUDE.md`, `.claude/skills/implementation-gate/SKILL.md` and `docs/OPERATIONS.md` repointed off
`test:full`/raw `pytest -x`. No test file touched. `gts-u6ew.1`/`.2`/`.3` closed
`regression=pending` on a targeted gate (`pnpm run test:local`, 716/716 green); full live-tier
sweep not run, per `CLAUDE.md`'s backstop rule against running it autonomously. Work-log: 2026-09-05
06:20 entry, session `82035a43`. **Handoff:** stage 2 (`measurement-hygiene`,
`gts-u6ew.4`/`.5`) is next per the execution-order table.

---

## Stage 2 — measurement-hygiene *(complete, 2026-09-05)*

`gts-u6ew.4` verified complete from a prior session's diff (not redone): `scn/contract.py`'s
`AC_REGISTRY` holds only the 27 real ACs; the 10 harness self-test markers (`t`, `t1`, `t2`,
`uc AC-1`/`AC-2`/`TEST`, `uc1 AC1`–`AC4`) that had been inflating the denominator by 27% now live in
a new `AC_SELFTEST_FIXTURES` dict, documented as not read by `scripts/check_coverage.py`; `__all__`
updated to export both. Re-verified this session by running `scripts/check_coverage.py` live —
`Registry size: 27`. `gts-u6ew.5` implemented this session: `tests/conftest.py` gained
`TRACKER_ID_ALLOWLIST` (the 11 existing `H11` offenders, the single source the lint reads) and a
`pytest_collect_file` hook that fails collection (`CollectError`, exit 2) for any new `test_*.py`
filename matching the bead-slug shape — a digit inside the first underscore-delimited token, 2–8
chars, mirroring `harness-design.md` §9a's own `H11` `--ticket-pattern` citation — unless it is on
the allowlist. Verified against a synthetic `tests/test_ab12_probe.py` (failed collection as
expected, then removed) and against the full suite (1143 tests still collect clean, zero false
positives against any existing filename). No existing test file renamed — that is stage 10
(`gts-u6ew.17`). Known gap, accepted rather than risking false positives on real descriptive words:
the digit-in-token heuristic will not catch a future letters-only slug in the shape of `hroj`/
`hztp`/`pulj`/`uuse`; a human reviewer remains the backstop for that case. Both beads closed
`regression=pending` on a targeted gate (`pnpm run test:local`, 716/716 green); full live-tier
sweep not run, per `CLAUDE.md`'s backstop rule. Work-log: 2026-09-05 07:00 entry (one entry covering
both beads, per this stage's batching convention), session `b4c13d22`. **Handoff:** stage 3
(`boundary-faults`, `gts-u6ew.6`/`.7`/`.8`) is next per the execution-order table.

---

## Stage 3 — boundary-faults *(complete, 2026-09-05)*

New `scn/outcomes.py`: `BoundaryFault(RuntimeError)` (carries an `attempts` int) and one owning
`classify(exc) -> PASS|ASSERTION_FAILURE|BOUNDARY_FAULT` helper (`I12`) — no per-test `except`
duplication, a type check rather than message matching. `scn/session.py`'s four retry-exhaustion
sites in `_http_post` (previously bare `RuntimeError`) now raise `BoundaryFault`. `gts-u6ew.7`/`H7`:
the retry policy's numbers (`HTTP_POST_MAX_ATTEMPTS`=5, `HTTP_POST_RETRY_DELAY_S`=3, unchanged in
value) moved out of `scn/session.py` into `tests/duration_instrumentation.py`, co-located with the
`H4` ceiling (`I6`); `_http_post` gained an `on_attempts` callback rather than a changed return
type — ~50 existing test files call `_http_post` directly and depend on the returned dict, so the
plan's original "lift the retry" framing was implemented without breaking that surface. Every HTTP
call's attempt count is recorded via the existing `reporter.junit()` user_properties path (the same
one `ac.*`/`ep.*`/`elapsed.*` already use) and summed per test. `tests/conftest.py`'s
`pytest_runtest_makereport` hookwrapper (the site the plan named, §2b) now classifies every
call-phase result and stamps `outcome_class`; `pytest_runtest_logreport` reads it back (plus the
summed `http.attempts`) into every JSONL duration record via `build_record`'s two new fields — a
non-failed call classifies `PASS`, with the raw pytest outcome (e.g. `"skipped"`) preserved
separately on the record's existing `outcome` field, so nothing is lost. `gts-u6ew.8`/`H8`: new pure
helpers `summarize_run()`/`format_run_summary()` in `duration_instrumentation.py` (`I12`) compute
execution failure rate, failed-wall-time share, and boundary-fault share of failures; a new
`pytest_sessionfinish` hook filters `duration-log.jsonl` to the current run and prints the line
every run — verified live in this stage's own targeted gate: `H8 boundary-fault summary: 0/735
executions failed (0.0%); 0.0s of 54.5s wall time (0.0%) spent failing, 0 boundary fault(s) (0.0% of
failures)`. Ordering followed `.6` → `.7` → `.8` as planned (no deviation found — `.8`'s
execution-failure-rate half could have landed independently per the plan's note, but the classifier
was ready first, so there was no reason to split it out). New tests: `tests/test_scn_outcomes.py`
(classify/BoundaryFault), plus additions to `tests/test_duration_instrumentation.py` (`build_record`'s
new fields, `summarize_run`/`format_run_summary`). All three beads closed `regression=pending` on a
targeted gate (`pnpm run test:local`, 735/735 green); full live-tier sweep not run, per `CLAUDE.md`'s
backstop rule. `docs/atdd/harness-design.md` §9a's `H6`/`H7`/`H8` rows flip `waived` → `conformant`.
The stage's "must not" constraint held by construction throughout: a fault surviving the retry
policy still raises/reports as a boundary fault — nothing added converts a surviving fault into a
silent pass, nor retries it further. Work-log: 2026-09-05 08:10 entry, session `b4c13d22`.
**Handoff:** stage 4 (`coverage-truth`, `gts-u6ew.15`/`.16`) is next per the execution-order table —
blocked on this stage via a real `bd dep` edge (`gts-u6ew.15` depends on `gts-u6ew.6`, now closed),
not merely asserted here.

---

## Stage 4 — coverage-truth *(complete, 2026-09-05)*

`scripts/check_coverage.py`'s gap-diff no longer collapses every uncovered AC into one bucket.
New `_split_uncovered_from_missing(missing, boundary_fault_this_run)` (`gts-u6ew.15`/`H9`) splits a
registry gap into confirmed `uncovered` (the run was clean) vs. `unreached this run` (the most
recent run in `test-results/duration-log.jsonl` recorded a `BOUNDARY_FAULT`) — a platform incident
no longer reads as a wave of missing tests. `_report` returns a bitmask (`1`=uncovered,
`2`=unreached-this-run) instead of a flat 0/1, so the two are distinguishable by exit code alone.
**Design correction found while implementing:** the bead description's wording implied reading
`outcome_class` off the JUnit XML being diffed; a live probe (a clean local run) showed zero
`<property>` elements land in `pytest.xml` even though the matching `duration-log.jsonl` record
carries `outcome_class="PASS"` — traced to `_pytest.junitxml.LogXML.finalize()` reading only the
teardown-phase report's `user_properties`, which stage 3's `pytest_runtest_makereport` hookwrapper
never touches (it stamps the call-phase report instead). `test-results/duration-log.jsonl` is this
project's one reliable source for `outcome_class`; `_latest_run_boundary_fault_info` reads it
instead. Not fixed here — `tests/conftest.py` is stage 3's already-closed, uncommitted diff, out of
this stage's contract; recorded for the record in the bead close and the harness-design `H9` row.

`gts-u6ew.16`/`H10`: new `_stale_acs`/`_collect_ac_coverage_per_file`/`_junit_files_by_mtime`, ported
from `$DEVSTANDARD/tools/test-suite-diagnostics.py`'s `stale_acs`/`junit_ac_coverage` (same
algorithm — files ordered oldest-first by mtime, PASS coverage unioned over the last N, any
registry key never seen flagged candidate-stale), sharing `_parse_junit`/`_collect` with the
gap-diff rather than a second JUnit-reading path (`I6`/`I12` — this is what "share the JUnit-history
reading code" meant in practice: one file-parsing/property-extraction path, called once per file for
history instead of once for the live report). Runs by default alongside the gap-diff; **report-only,
does not affect exit code**, and is not treated as settled — per the stage's "must not" constraint
and the plan's escalation E2, no full live sweep was run. `harness-design.md` §9a's `H10` row moves
off `unknown` to `waived` (the instrument now exists and runs every invocation) — **not** to
`conformant`; settling it still needs the first operator-initiated full regression sweep. `H9` flips
`waived` → `conformant`.

New `tests/test_check_coverage.py` (24 tests, pure logic, no live pytest subprocess — first test
file for this script; coverage inventory confirmed net-new before authoring). Both beads closed
`regression=pending` on a targeted gate (`pnpm run test:local`, 759/759 green, up from 735); full
live-tier sweep not run, per `CLAUDE.md`'s backstop rule. Work-log: 2026-09-05 09:12 entry, session
`b4c13d22`. **Handoff:** stage 5 (`journey-tagging`, `gts-u6ew.12`/`.13`) is next per the
execution-order table.

---

## Stage 5 — journey-tagging *(complete, 2026-09-05)*

`gts-u6ew.12`: the six journeys that asserted without reporting (F7) now each drain one real
`scn/contract.AC_REGISTRY` id (`sync-all reconcile`, `scanner tracker-exclude`, `menu
entrypoint-callsite`, `link-preview status`, `link-preview chip-disclosure`, `archive lifecycle`),
reaching the `ac.*` JUnit properties `scripts/check_coverage.py` diffs. Five of six retagged an
existing `scn.verify()`/`expect_callable()` call's bespoke bracket tag in place; the other two
(`test_floating_action_scanner.py`, `test_chip_preview.py`) had no expectation-queue usage at all
(bare `assert`), so their existing durable-state check was routed through
`expect_callable()`/`checkpoint()` — same check, no new assertion. `test_archive.py`'s `scn`
fixture was module-scoped with no `request=` wired (a no-op reporter, q37d); changed to
function-scoped with `request=request` (the file has exactly one test, so no behavior change).

`gts-u6ew.13`: `test_journey_acts_1_3.py` retired and deleted. Read against `test_journey.py`'s own
Acts 1-3, it was a strict subset with nothing left to fold — same 5 seeded items (`test_journey`
adds a 6th), same verify shape, and its Act 3 tracker insert used the `insert_tracker_table`
test-support fixture directly rather than the real `onInsertTrackerTable` UI call-site
`test_journey` exercises. "Cheaper reproduction path" is a convenience argument, not a
failure-domain line (`ADR-0011` §5) — no why-separate line to write, so retirement (not a merge)
satisfied the AC. `docs/OPERATIONS.md`'s run commands and UC-A coverage table, and testing guide
§6's charter (row removed, AC-id column filled in for the other five rows, findings note rewritten
with today's date) updated; `work-log.md`/`pipeline-report.md`/the 2026-08-05 health review are
point-in-time records and were left as-is.

Both beads closed `regression=pending` on the targeted gate (`pnpm run test:local`, 759/759 green —
unchanged count, since every touched file is live-tier and excluded by the `no_live_session`
filter; `--collect-only` across all seven touched files confirmed no import/syntax errors). Full
live-tier sweep not run, per `CLAUDE.md`'s backstop rule — the new `ac.*` tags' live drain is
unverified until that happens. Work-log: 2026-09-05 10:05 entry, session `b4c13d22`. **Handoff:**
stage 6 (`disposition-enforcement`, `gts-u6ew.9`) is next per the execution-order table — its
position right after this stage is a stated sequencing preference, not a real `bd dep` edge (see
§Stage 6 block below).

---

## Stage 6 — disposition-enforcement *(complete, 2026-09-05)*

`gts-u6ew.9`/Plan R7: `docs/atdd/project-testing-guide.md` §9 already named where a disposition
lives (`disp:<n>` label + `## Disposition` section) and the two ad hoc `bd`/`jq` commands from
`bd/SKILL.md` §Disposition that could check it, but nothing actually ran them mechanically — a
`[TST]` bead could still reach the merge boundary with no disposition at all, and `merge-gate`'s
own Step 2.5 ("For every `[TST]` bead in scope, read its disposition...") had no concrete command
to invoke, only prose describing the manual comparison. New `scripts/audit_disposition.py`
mechanizes exactly those two checks as pure functions — `find_missing_disposition` (no `disp:<n>`
label at all) and `find_malformed_disposition` (more than one `disp:<n>` label, or a `disp:<n>`
label with no `## Disposition` section in the description; deliberately does not double-report a
bead `find_missing_disposition` already flagged) — over an already-loaded `bd list --json` issue
list, so the check is unit-testable without a live `bd` subprocess (same shape as
`scripts/check_coverage.py`'s I/O boundary).

Scope is the key design decision, not a detail: `merge-gate` Step 2.5 audits "every `[TST]` bead in
scope" of the diff under review, not the whole tracker, so the script offers two scope modes rather
than one blanket check. `--ids ID,ID,...` audits exactly the named beads — this is the merge-gate
wiring: the reviewer (or a hook) passes the `[TST]` beads closed/touched by the diff, and only those
are checked. `--since DATE` (default `2026-09-05`, this project's ADR-0011 adoption date) audits
every `[TST]` bead created on/after that date, tracker-wide — the periodic health check. This
matters empirically: running the raw `bd`/`jq` commands from `bd/SKILL.md` unscoped against this
project's actual tracker returns **213** pre-adoption `[TST]` beads with no `disp:` label — real
debt, but not this stage's debt, and not something `merge-gate` should ever block a new PR on.
`project-testing-guide.md` §9's "dispositions bind forward from 2026-09-05; closed `[TST]` items are
not re-litigated" line is exactly the rule the `--since` default encodes; without it the audit
command could never return nothing on any tree, clean or not, which would make it useless as a gate.

**Design finding, verified live rather than assumed:** while building the `--since` mode, the script
surfaced two real disposition gaps that were not anticipated going in — `gts-zjrm` and `gts-sxvj`,
two `[TST]` beads created the same day by concurrent, unrelated work sharing this project's Dolt
tracker, both with zero `disp:` labels. This is the backstop rule's "a new assertion must be proven
to fail before acceptance" satisfied by a genuine finding rather than a synthetic one: `--since
2026-09-05` (no other args) prints both as `MISSING` and exits 1; `--ids gts-u6ew.12,gts-u6ew.13`
(this plan's own stage-5 beads, both already dispositioned) returns nothing and exits 0. Those two
external gaps are out of this stage's scope (not part of this diff, not this plan's beads) and were
left unfiled — the audit doing its job is the deliverable here, not chasing every debt item it finds
on first run.

`docs/atdd/project-testing-guide.md` §9 updated: the "Audit command" bullet now names the script and
both scope modes instead of the two bare `bd`/`jq` one-liners; the "Gate that verifies it against
the diff" bullet drops "not yet in force as of 2026-09-05" — Plan R7 is in force. `bd/SKILL.md`
itself (a DevStandard-owned, cross-project skill file, not this repo) was left untouched — its two
commands remain the documented reference shape the script mechanizes, not something this project's
stage owns.

New `tests/test_audit_disposition.py` (11 tests, pure logic — `filter_since`/`filter_ids` scope
selection, both compliance checks positive and negative, and one paired "does not double-report"
test for the missing/malformed overlap). Closed `regression=pending` on the targeted gate (`pnpm run
test:local`, 770/770 green, up from 759); full live-tier sweep not run, per `CLAUDE.md`'s backstop
rule against running it autonomously. Work-log: 2026-09-05 08:15 entry, session `42c4a3ef`.
**Handoff:** stage 7 (`registry-derivation`, `gts-u6ew.10`) is next per the execution-order table.

---

## Stage 7 — registry-derivation *(complete, 2026-09-05)*

`gts-u6ew.10`/`H12`/`I6`: testing guide §7's callout already named the risk — it read "32 entry
points / 22 deferred" against an actual 37/13 until corrected 2026-09-05, and `harness-design.md`
§9b recorded the derivation as "not yet derived." New `scripts/check_entry_point_registry_view.py`
extracts the bold total/covered/deferred numbers each doc states in prose (guide §7's "all **37**
state-modifying entry points" / "24 of the 37 entries..." / "remaining **13**...deferred", and
harness-design.md §9a's H12 row "registry of 37 state-modifying entry points, with 13 explicitly
deferred") via regex, and diffs them against `len(scn.contract.ENTRY_POINT_REGISTRY)` /
`len(ENTRY_POINT_DEFERRED)` — the same two counts `scripts/check_coverage.py` already reads for the
live `ep.*` gap-diff, so no new source of truth was introduced. A doc reworded such that the
expected pattern can no longer be found is its own distinct failure (exit 2, "EXTRACTION ERROR"),
not a silent pass — the check cannot go quiet while a doc drifts under it, whether by wrong numbers
or by prose that stops stating any.

**Design decision, stated rather than defaulted to:** the AC's first option ("generate §7 from the
registry") was rejected in favor of the second ("a check that fails when they disagree"). The
call-site-class table's "Examples"/"Covered"/"Deferred" columns and the per-class deferral rationale
are not mechanically derivable from `ENTRY_POINT_REGISTRY`'s flat `dict[str, str]` without either
losing that narrative or inventing a second structured schema on top of the bracketed `[category]`
prefixes already embedded in each description — a heavier change than this stage's "small,
self-contained" framing (§Stage blocks below) justified. The check guards only the numbers that have
actually drifted so far (the two docs' stated total/covered/deferred counts); the table's
hand-authored commentary is unchanged and still a human's job to keep current. This closes the AC
("no second hand-maintained enumeration remains") because neither doc contains a second full
enumeration today — only summary counts, which are now guarded.

Wired into the regression suite rather than left as a manual CLI-only tool: new
`tests/test_check_entry_point_registry_view.py` (13 tests) includes
`test_check_against_real_project_docs_agrees`, so the check runs — and can fail — on every
`test:local` pass, the same "runs automatically, not only on request" pattern as
`scripts/check_coverage.py`'s gap-diff. Backstop rule's proven-to-fail requirement satisfied against
the real drift shape, not a synthetic one: `test_check_fails_against_a_deliberately_stale_guide_copy`
takes the actual guide text, rewrites it back to the historical wrong 32/22 numbers, and asserts the
check reports all four mismatches; `test_diff_guide_reports_every_kind_of_mismatch` and
`test_diff_harness_design_reports_mismatch` do the same at the pure-function level. Guide §7's
callout and harness-design.md §9b were both updated to point at the new script instead of describing
the gap as open.

Closed `regression=pending` on the targeted gate (`pnpm run test:local`, 783/783 green, up from
770); full live-tier sweep not run, per `CLAUDE.md`'s backstop rule against running it autonomously.
**Work-log: batched with stage 8** — one combined entry, written when stage 8 closed: 2026-09-05
11:30 entry, session `42c4a3ef`. **Handoff:** stage 8 (`registry-extraction`, `gts-u6ew.11`) is next per
the execution-order table — a different failure (the registry itself going stale against `src/`,
not the view going stale against the registry) and a different model label (`opus`), per the
anti-pairing rule already recorded in §Sequencing rationale below.

---

## Stage 8 — registry-extraction *(complete, 2026-09-05)*

`gts-u6ew.11`/`H12`: stage 7 made the registry's *views* honest against the registry; this makes
the *registry* honest against `src/`. New `scripts/check_entry_point_extraction.py` extracts every
UI-handler entry point from the five places GAS wires one by name — `onOpen()`'s
`.addItem('Label','handler')`, `appsscript.json` `addOns.*` `runFunction` values, CardService
`setFunctionName()` and this project's `_buildCardAction()` wrapper, `ScriptApp.newTrigger()`, and
defined simple triggers — and requires every extracted handler to be accounted for in exactly one
of `ENTRY_POINT_REGISTRY` (directly, or via the new `ENTRY_POINT_SOURCE_ALIASES` where the registry
key is not the function name: `onSyncNow` → `syncDocument.onSyncNow`, `_submitImport` →
`importSelectedSubmit`) or the new `ENTRY_POINT_SOURCE_EXEMPT` (14 read-only/navigation handlers,
each with a stated reason). Anything else exits 1; an extraction class yielding nothing exits 2
("EXTRACTION ERROR"), the same anti-quiet rule stage 7 applied to its doc regexes — the check
cannot go silent while `src/` is restructured under it. `ENTRY_POINT_SOURCE_EXEMPT` also replaces
the prose comment in `scn/contract.py` that had been listing the read-only exemptions where nothing
could read them (`I6`).

**First-run finding — the AC proving itself on real drift, not a synthetic case.** Eleven
state-modifying handlers wired in `src/` were absent from the registry entirely: `menuConfigFormat`,
`menuForceRefreshActiveDoc`, `nightlyAdminScanAllTeams`, `_runNearImmediateSyncAll`, and the seven
TestControl-driven Test-menu items (`menuCleanupTestDocs`, `menuBeginTestSession`,
`menuEndTestSession`, `menuSetupFixture`, `menuSyncDocument`, `menuSetupAndSync`,
`menuInsertTrackerTable`). All 11 registered with descriptions and listed in
`ENTRY_POINT_DEFERRED` with reasons — six as permanent exemptions (manual TestControl twins of
routes already covered), the rest as tracked gaps. Registry 37 → 48, deferred 13 → 24, covered
unchanged at 24. The sharpest case is `menuCleanupTestDocs`: it already had a real durable-state
test (`tests/test_cleanup_test_docs.py`, `gts-ve6z`) and was still invisible to the `ep.*` gap-diff
because it was never registered — exactly the silent uncoverage `H12` exists to prevent. Its
deferral reason mirrors the existing `team_sync_document` precedent (covered, but the assertion is
raw XLSX/dict rather than a `scn.verify(..., entry_point=...)` tagged call-site); tagging it is the
work that clears the row.

**Scope limit, stated rather than defaulted to:** the `doPost` route class (~60
`payload.action === '…'` names in `src/WebApp.js`) is deliberately *not* extracted. The registry
holds a chosen state-modifying subset of those routes, so an extractor there needs a
read-only/test-support exemption list roughly the size of the registry itself — judgement, not
extraction — and this stage's deliverable is scoped to "a new `menu*`/`on*` handler in `src/` that
nobody registered" (§Stage blocks below). Routes stay hand-authored into the registry; filed as
**`gts-otmu`** and recorded in both the script's docstring and `harness-design.md` §9b's new
"Residual scope limit" bullet, not left as an unstated gap.

**The two stages verified each other on first contact.** Stage 8's registry growth immediately
failed stage 7's check on all five stated numbers (guide §7's three, `harness-design.md` §9a's
two) — stage 7's check firing on real drift rather than only in its own tests. Both docs were
updated to 48/24/24. It also exposed a defect in stage 7's own proven-to-fail test: it built its
deliberately-stale guide copy by string-replacing the hard-coded `37`/`13` values, so the count
change turned the rewrite into a no-op and left the test asserting nothing while still passing.
Fixed here — the rewrite is now derived from `registry_counts()` with an explicit assertion that it
matched something.

Files touched: new `scripts/check_entry_point_extraction.py`, new
`tests/test_check_entry_point_extraction.py` (17 tests); `scn/contract.py` (11 registry entries +
11 deferral reasons, new `ENTRY_POINT_SOURCE_EXEMPT`/`ENTRY_POINT_SOURCE_ALIASES`, `__all__`,
prose comment replaced); `tests/test_check_entry_point_registry_view.py` (count-derived stale copy);
`docs/atdd/project-testing-guide.md` §7 (counts, new callout paragraph, new Test-menu class row);
`docs/atdd/harness-design.md` §9a `H12` row + §9b (limit replaced, residual scope limit added);
`docs/atdd/ID-map.md` (2026-06-18 counts marked point-in-time with a pointer to the live ones).
Verification: `scripts/check_entry_point_extraction.py --verbose` (44 handlers extracted across
five classes, all accounted for, RC=0), `scripts/check_entry_point_registry_view.py` (RC=0 after
the doc updates), and the targeted gate `pnpm run test:local` — **800/800 green** (up from 783).
Proven-to-fail was satisfied against the real sources, not synthetic ones: one test drops
`menuRunArchive` from a registry copy, another injects a new unregistered `.addItem` into the real
`MenuHandler.js` text; both assert the check reports exactly it. Closed `regression=pending`; full
live-tier sweep not run, per `CLAUDE.md`'s backstop rule against running it autonomously.
Work-log: 2026-09-05 11:30 entry, session `42c4a3ef` — one combined entry covering stages 7 and 8,
per both stage blocks' batching note. **Handoff:** stage 10 (`naming-cleanup`, `gts-u6ew.17`) is
next. Stage 9 (`budget-consolidation`, `gts-u6ew.14`) is **skipped, not next** — its block says
do-not-start until stage 1 has produced a real suite-wide duration profile, which needs an
operator-authorized full live-tier sweep this plan's agents may not start (§Open items requiring
the owner).

---

## Stage 10 — naming-cleanup *(complete, 2026-09-05)*

`gts-u6ew.17`/`H11`: the escalation's decided six — the files whose slug alone names no
recoverable behaviour — renamed via `git mv` to keep history: `test_b7_write_routes.py` →
`test_globalid_write_routes.py`, `test_kkm7_batching.py` → `test_sync_batching.py`,
`test_p9ra_run_fixture_cache_oversize.py` → `test_run_fixture_cache_oversize.py`,
`test_zc0w_probe_parity.py` → `test_probe_parity.py`, `test_uuse_scoped_listing.py` →
`test_scoped_drive_listing.py`, `test_pulj_malformed_teamdata_folder.py` →
`test_malformed_teamdata_folder.py`. Each module docstring's header line now reads `<new
filename>.py — bead: gts-<slug>` instead of folding the slug into the filename, per T4/T10; test
function names and in-body `[b7 …]`/`AC` tag labels were left untouched (the AC covers file paths,
not identifiers, and touching them would have widened the diff into behavioural territory the
stage's own anti-pairing rationale rules out).

**External references repointed.** Grepped the whole tree for the six old filenames and updated
every *live* reference found: `tests/conftest.py`'s `TRACKER_ID_ALLOWLIST` (shrunk from 11 entries
to 5 — the five left to next touch); cross-file docstring/comment mentions in five other test
files (`test_docdata_sync_action_rows_backfill.py`, `test_force_refresh_route.py`,
`test_probe_parity.py` itself citing its sibling, `test_f3me2_run_fixture_idempotency.py`,
`test_access_resolve_dedupe.py`); `src/TestWebApp.js`'s one comment; `docs/OPERATIONS.md` (two
sites) and `docs/atdd/project-testing-guide.md`'s call-site table; three
`docs/lessons-learned/resolved/` entries; and bd issue `gts-a8yh.1`'s title (the one open bd body
found naming an old path — `bd search` against all six old names turned up nothing else).
`docs/atdd/ID-map.md` carried no references to any of the six — nothing to repoint there despite
the bead naming it explicitly.

**Left alone, deliberately:** dated/historical artifacts that record what a past run actually saw
rather than serving as navigation — `work-log.md`'s own prior entries, `TD-PLAN-20-08.md`,
`TD-PLAN-21-08.md`, `HANDOFF-gts-ir1f-2026-08-06.md`, `plan-fix.md`, `plan-0806-flake-recovery.md`,
`pipeline-report.md`, `test-full-run.txt`, `docs/regression-suite-health-review-2026-08-05.md`,
`docs/atdd/archive/open-tst-issues-scenario-approach.md`, `docs/atdd/test-framework-upgrade-plan.md`'s
F6 finding (which is citing the old names as evidence of what a specific past tool run saw), and
`knowledge-base/staging/docdata-litter-apt-speed.md`. Rewriting a dated record to match a rename
that postdates it would misrepresent what that record actually observed. `tests/.pytest_duration_baseline.json`
is gitignored and re-keys itself under the new node ids on next run — no action needed.

**Scope was deliberately partial**, per the bead: the five files whose slug already reads
descriptively in context (`test_hztp_actionsnapshot_read_coverage.py`,
`test_hroj_diagnostics_backstop.py`, `test_f3me1_append_idempotency.py`,
`test_f3me2_run_fixture_idempotency.py`, `test_adr0027_reference_document.py`) are left in the
allowlist, unrenamed, for next touch.

Verification: direct `pytest --collect-only` against all six renamed files (17 tests, zero import
errors, confirming the shrunk allowlist did not re-trip the `H11` tracker-id-shape collection hook
against the new — digit-free — names); targeted gate `pnpm run test:local`
(`pytest -m no_live_session -q -n 4 --dist worksteal`) — **800/800 green**. Closed `gts-u6ew.17`
`regression=pending`; full live-tier `pnpm run test:regression` not run, per `CLAUDE.md`'s backstop
rule against an agent self-initiating that sweep. Work-log: 2026-09-05 09:00 entry, session
`42c4a3ef`. **Handoff:** no further stage to run in this plan right now. Stage 9
(`budget-consolidation`, `gts-u6ew.14`) is the only stage left, and it stays **deferred** — still
blocked on the operator-authorized full live-tier sweep named in stage 8's handoff and in §Open
items requiring the owner. This plan has no self-startable work until that authorization lands.

---

## Stage blocks

### 1 — regression-gate

**Deliverable:** `pnpm run test:regression` — one command that runs the network-free tier to
completion and opens no live session unless it is green, with per-test durations measured against a
declared ceiling.

**Why paired:** all three change how the suite is *invoked and measured*, and all three are `S`
effort against `package.json` and `tests/duration_instrumentation.py`. This is the plan's best
cost-to-value bundle (§2a bundle A + D) and it produces the measurement every later stage is judged
against.

**Must not do:** touch a test. `.3` declares a ceiling and reports over-ceiling; bringing tests
*under* it is stage 9's job, deliberately separated.

**Watch for:** `.3` hits a real design collision — `duration_instrumentation.py`'s docstring says
"nothing here can fail or skip a test" and `H4` wants a failure. Plan §2b recommends keeping the
module report-only and letting a separate gate fail. Resolve it explicitly; do not quietly relax
the module's contract.

**Work-log:** per-stage.

### 2 — measurement-hygiene

**Deliverable:** coverage numbers measured against a denominator that is actually right, and a
collection-time block on the next tracker-id-named test file.

**Why paired:** both stop the harness counting or accepting the wrong thing, both are small, and
both are prerequisites for honest numbers later — `.4` fixes the AC denominator (currently wrong by
27%), `.5` stops `H11` degrading further while the rename decision sits deferred.

**Must not do:** rename an existing file. `.5` builds the allowlist; `.17` (stage 10) shrinks it.

**Work-log:** one entry covering both beads.

### 3 — boundary-faults

**Deliverable:** a red run that says whether it is red because we broke something or because Google
was down.

**Why paired:** one classifier, one policy, one report — `.7` and `.8` both read the outcome class
`.6` introduces, and splitting them across sessions means writing against a class that does not
exist yet.

**Highest-value stage in the plan.** Discovery measured 14.6 of 74.2 hours (19.6%) of wall time
spent on failing executions at a 7.6% execution failure rate, with ~52% of classified failures
matching boundary patterns. A suite where a material share of red is not the project's fault trains
everyone to ignore red.

**Must not do:** convert a surviving fault into a pass or a failure. A fault that outlives the
retry policy is reported as a boundary fault (`H7`).

**Note:** the execution-failure-rate half of `.8` does not depend on `.6` (plan §2c item 3) and can
land early if convenient.

**Work-log:** per-stage.

### 4 — coverage-truth

**Deliverable:** a gap-diff that stays readable during a platform incident, and a staleness check
that makes `H10` answerable at all.

**Why paired:** both are `scripts/check_coverage.py`; `.16` runs with `.15`'s diff, and the two
share the JUnit-history reading code.

**Blocked on stage 3** — modelled as a real `bd dep` edge, not asserted here.

**Must not do:** treat the staleness output as settled. `H10` is recorded `unknown`, not `waived`
— escalation E2 says the first operator-initiated full sweep settles it, and this stage builds the
instrument, it does not run the sweep.

**Work-log:** per-stage.

### 5 — journey-tagging

**Deliverable:** the six journeys that currently assert without reporting become visible to the
traceability report; the one journey with no defensible failure domain is resolved either way.

**Why paired:** both are `[TST]` beads carrying dispositions (`disp:2` each), both edit journeys
against the charter in testing guide §6, and both are the concrete remainder of discovery finding
F7. This is where the "36 of 37 uncovered" signal gets most of its real explanation.

**Must not do:** create a new journey. Both beads are dispositioned `disp:2` — add expectations to
existing journeys. A `disp:4` here would need re-justifying against the charter and a rewritten
`## Disposition` section (`ADR-0011`).

**Work-log:** per-stage.

### 6 — disposition-enforcement

**Deliverable:** a `[TST]` bead can no longer reach the merge boundary without a disposition.

**Why single:** it is the one bead of the plan's governance increment (§2a bundle C) that Phase 2
could not land in a document — everything else in that bundle is already written into
`docs/atdd/project-testing-guide.md` §9 and `harness-design.md` §9a.

**Deliberate ordering preference, not a dependency:** placed after stage 5 so the first beads it
gates are ones authored under the charter it enforces. No `bd dep` edge models this — it is a
preference and could move earlier without breaking anything.

**Work-log:** per-stage.

### 7 — registry-derivation

**Deliverable:** testing guide §7 can no longer silently disagree with `ENTRY_POINT_REGISTRY`.

**Why single:** small and self-contained. It has already drifted once — §7 read "32 entry points /
22 deferred" against an actual 37/13 until corrected 2026-09-05, which is the evidence this is
worth mechanising rather than re-checking by hand.

**Work-log:** batched with stage 8.

### 8 — registry-extraction

**Deliverable:** a new `menu*`/`on*` handler in `src/` that nobody registered fails the harness
instead of being silently undiffed.

**Why separate from stage 7:** stage 7 makes a *view* honest against the registry; this makes the
*registry* honest against the source. Different failure, different code, and different model
(`opus` vs `sonnet`) — batching them would be a batching error under the anti-pairing rule.

**Context:** `H12` is recorded `conformant` today; this closes the remaining hole named in
`harness-design.md` §9b rather than fixing a conformance failure.

**Work-log:** batched with stage 7.

### 9 — budget-consolidation

**Deliverable:** the four over-budget `test_menu_entry_points` tests are under the ceiling, or each
carries a real `H5` waiver row with an issue id.

**Why single, and why last:** the only stage that touches existing tests, so it needs everything
before it to be safe. Plan §2a ranks it the **lowest-value** item in the whole adoption — ~214s
against 74 hours of measured wall time — and §2c item 2 explains why the bead exists anyway: `H5`
says a waiver without an issue id is not a waiver but an unrecorded exception, and
`harness-design.md` §9a records `H4` as `waived` pointing here.

**Do not start** until stage 1 has produced a real suite-wide duration profile. The current profile
comes from a run that collected 8 tests, not 940; consolidating against it optimises a number
nobody has measured.

**Must not do:** waive before applying `H5`'s mandatory resolution order (`T6` → `T12` → `T21`),
and state why each step was insufficient for anything still waived.

**Work-log:** per-stage.

### 10 — naming-cleanup

**Deliverable:** six test files named for the behaviour they cover rather than the bead that
created them; the stage-2 allowlist shrinks by six.

**Why single, and why last:** it is a pure rename touching ≥6 files plus every external reference to
them (bd issue bodies, `docs/lessons-learned/`, `docs/atdd/ID-map.md`). Batching a rename with
behavioural work makes both diffs unreadable — the anti-pairing rule's "never batch across a
deletion" applies to moves for the same reason.

**Scope is deliberately partial** (escalation E3, third option): the five files whose slug already
reads descriptively in context are left to next touch. `.5`'s lint is what stops the population
growing meanwhile.

**Work-log:** per-stage.

---

## Sequencing rationale

**Order is value-ranked, not prerequisite-ranked.** The bootstrap's Phase 3 offers a default stage
ordering (measurement → registries → charter → gating → budget → enforcement). This plan departs
from it in one place and the departure is deliberate: the bootstrap promotes **Budget** to a
headline stage, but on this project's measured numbers its consolidation half is the lowest-value
item in the table. It is stage 9 here, not stage 5, and the reasoning is in plan §2a bundle G.

**Two prerequisite breaks were predicted in plan §2c; one resolved differently.**

- §2c item 1 predicted that writing `harness-design.md` §9a would need bead ids that Phase 3 had not
  yet created. It did — §9a was written in Phase 2 citing plan row numbers (`plan R8`) as
  placeholders. **Follow-up: §9a's `waived` rows must be repointed to the real `gts-u6ew.N` ids**,
  since `H5` requires a waiver to resolve to an issue. Tracked as part of stage 1's close.
- §2c item 2 (a deferred bead still needs filing, so `H4`'s waiver has an id) resolved as predicted:
  `gts-u6ew.14` is filed, staged last, and explicitly marked do-not-start.

**Anti-pairings observed.** Stage 7 and 8 are split despite both touching the entry-point registry —
different failure, different model label. Stage 10's renames are isolated from all behavioural work.
Stages 2 and 10 are split across the same `H11` standard because one builds an allowlist and the
other shrinks it.

**What is asserted rather than modelled.** Stage 6's position is a preference, stated in its block.
Every other ordering constraint carries a real `bd dep` edge, so it survives this document being
deleted.

---

## BD References

| Bead | Role |
|------|------|
| `gts-u6ew` | Epic — the adoption; carries the plan of record in its `--design` field |
| `gts-u6ew.1` – `gts-u6ew.18` | The staged work; see the execution-order table for stage, status and title |
| `gts-u6ew.12`, `gts-u6ew.13`, `gts-u6ew.14` | The three `[TST]` beads — each carries a `disp:` label and a `## Disposition` section per `ADR-0011` |
| `gts-rz4k` (`.1`–`.5`) | Pre-existing epic converting deferred entry points to real call-sites; adjacent to stages 7–8, not owned by this plan |
| `gts-otmu` | Filed by stage 8 — extend the source-extraction check to the `doPost` route class, deliberately out of `gts-u6ew.11`'s scope |
| `gts-0f0s`, `gts-4hqn` | Pre-existing gaps noted in the journey charter (archive threshold; scanner AC-7/AC-8 split) |

## Change Log

| Date | Change |
|------|--------|
| 2026-09-05 | Stage 10 closed. Six tracker-id-slug test files renamed to behaviour-derived names via `git mv`, bead ids kept in module docstrings, `TRACKER_ID_ALLOWLIST` shrunk from 11 to 5, and every live external reference (bd body, cross-test docstrings, `docs/OPERATIONS.md`, `docs/atdd/project-testing-guide.md`, `src/TestWebApp.js`, three `docs/lessons-learned/resolved/` entries) repointed; dated/historical artifacts left untouched by design. Targeted gate green (800/800). Status/Next Step updated: stage 9 is now the only stage left, still deferred pending owner authorization for a full live-tier sweep — no further self-startable work remains in this plan. |
| 2026-09-05 | Stages 7 and 8 closed; one batched work-log entry (11:30, session `42c4a3ef`) covers both. Stage 8's extraction check registered 11 previously unenumerated `src/` handlers (registry 37 → 48, deferred 13 → 24) and filed `gts-otmu` for the deliberately out-of-scope `doPost` route class. Next Step repointed to stage 10; stage 9 recorded `deferred` in the roll-up rather than `pending`, since it is blocked on an operator-authorized full live-tier sweep, not on this plan's own sequence. |
| 2026-09-05 | Authored. Stage 0 closed. 18 beads filed under `gts-u6ew`; 17 staged across 10 stages, `gts-u6ew.18` left unstaged per plan R20. Two batching errors corrected before publication: `gts-u6ew.8` re-labelled `model:opus` to match its stage, and `gts-u6ew.11` split into its own stage `registry-extraction` rather than sharing `registry-derivation` with a differently-modelled bead. One dependency edge added then removed — testing guide §7's derivation (`gts-u6ew.10`) does not in fact require the registry to be extracted from source (`gts-u6ew.11`); they are independent. |

## Open items requiring the owner

- **Escalation E2 is unresolved by design** and is the reason `H10` is recorded `waived` rather
  than `conformant`. Settling it needs one full live sweep, which project `CLAUDE.md` forbids an
  agent starting on its own initiative. Stage 4 builds the instrument; only the owner can authorise
  the run that reads it.
- **Stage 9 (`budget-consolidation`, `gts-u6ew.14`) is deferred on the same authorisation.** Its
  block says do-not-start until a real suite-wide duration profile exists — the current one comes
  from a run that collected 8 tests, not 940 — and producing that profile is the same
  operator-authorized full live-tier sweep. It is the plan's lowest-value item (§2a bundle G), so
  it holds the queue for nothing else: stage 10 proceeds without it.
- **Every closed bead in this plan is `regression=pending`, not `regression=verified`.** That is
  the deliberate default (`CLAUDE.md` backstop rule), and it is what the merge gate will read: this
  branch cannot merge until one full `pnpm run test:regression` flips them. That run is the same
  one the two items above need — one authorised sweep discharges all three.
