# LL: Molecule-formula placeholder issues stayed open for 3 weeks after their scope was delivered under unrelated bead IDs

Date: 2026-06-12
Domain: process

## Observation

- `GTaskSheet-mol-dhd` (mol-feature-delivery molecule for "UC-D archive closed actions",
  created 2026-05-22) had 11 children mapping to the formula's linear steps (draft UC/AC,
  UC/AC gate, develop-tests, implement, verify, independent review, review gate,
  address-findings, update-docs, final gate).
- The actual UC-D archive feature (`ArchiveManager.js`, `test_archive.py`, syncAll
  auto-archive, `docs/CONTEXT.md` §UC-D, `docs/DESIGN.md`, `docs/OPERATIONS.md`) was
  implemented, tested, and documented between 2026-06-01 and 2026-06-08 under a separate
  set of beads (`d33z`, `r3d`, `grxl`, `5u2v`, `nv6g`, `eg8x`, `hnes`, `vx91`, `elnv`,
  `sma8`, `por0`, `hie7`, `cwm0` — all closed), created through an organic syncAll-epic
  decomposition rather than through `mol-dhd`.
- 8 of `mol-dhd`'s children (`mol-87e` develop-tests, `mol-o5f` implement, `mol-7vm` verify,
  `mol-ddz` independent review, `mol-bm9` review gate, `mol-380` address-findings,
  `mol-4r5` update-docs, `mol-no8` final gate) remained OPEN with empty descriptions
  (`DESCRIPTION (none)`) and `Updated: 2026-05-22` — never touched again — until closed in
  this session (2026-06-12) as superseded.
- `bd stale` (run 2026-06-12) returned "No stale issues found" despite these 8 issues having
  zero activity for 21 days while their entire planned scope had already been delivered.
- A sibling molecule, `GTaskSheet-mol-66r` (UC-C insert/refresh in-doc tracker table, also
  created 2026-05-22, also a core already-shipped feature), shows the same pattern:
  `mol-4d0`, `mol-4nt`, `mol-87z`, `mol-eal` remain open and unreviewed.
- An existing staged LL (`2026-06-02-no-aggregate-technical-debt-surface.md`) already
  identified "implicitly-resolved issues remain open in the backlog" as a debt category and
  proposed a `/technical-debt` skill. That skill now exists
  (`DevStandard/dot-claude/skills/technical-debt/SKILL.md`) and its "implicit-resolve
  candidates" check works by matching recent commit messages against open-issue
  *descriptions*. `mol-dhd`'s open children all have empty descriptions, so this check has
  no text to match against — the existing lever cannot catch this specific instance even
  when run.

## Why Chain (branched)

Branch A — empty descriptions defeat the implicit-resolve check
Why 1 — The technical-debt skill's implicit-resolve check matches commit text against issue
        *descriptions*; `mol-dhd`'s children have no description.
Why 2 — The `mol-feature-delivery` formula generates step *titles* only (e.g. "Implement
        {{feature}}"); it does not populate a description linking the step to the
        use-case/feature identity in a way later text searches can match.
Why 3 — `bd cook` instantiates the formula's generic step text verbatim with no requirement
        to backfill description/scope once the feature is identified.
Root cause A: The feature-delivery molecule produces placeholder issues with no searchable
scope text, so any later automated reconciliation (commit↔issue matching) has nothing to
match on.

Branch B — `bd stale` did not flag 21-day-untouched issues
Why 1 — `bd stale` returned empty for 8 issues last updated 2026-05-22 (21 days prior to
        this session).
Why 2 — `bd stale`'s threshold/criteria apparently do not treat "task with parent epic still
        open and zero activity since creation" as stale, or its default window exceeds
        21 days.
Why 3 — No one has tuned or verified `bd stale`'s threshold against this project's actual
        planning cadence, where multi-week epics with dormant placeholder children are
        normal.
Root cause B: `bd stale`'s default staleness window/criteria have not been validated against
this project's epic/molecule lifecycles, so genuinely dormant planning artifacts are not
surfaced by the tool the technical-debt skill relies on.

Branch C — no reconciliation step when organic work supersedes a planned molecule step
Why 1 — When `d33z`/`eg8x`/etc. closed (2026-06-01 to 2026-06-08), nothing checked whether
        their scope corresponded to an existing planned molecule step.
Why 2 — The session that created `d33z`/`eg8x` etc. (per work-log 2026-06-02) explicitly
        reasoned about syncAll/archive scope but was not framed as "does this satisfy any
        open `mol-dhd` step?" — the two planning tracks (`mol-kqr` v1-ship molecules vs.
        the syncAll-epic ad hoc decomposition) were never cross-referenced.
Why 3 — There is no convention requiring a check, when closing a `[TST]`/`[IMP]`/`[FIX]`
        bead, for sibling/overlapping open issues describing the same capability —
        regardless of which epic/molecule they live under.
Root cause C: No process step cross-references newly-closed implementation/test work against
open molecule/epic children describing the same capability under a different identifier.

## Initial Candidates

- f: audit `GTaskSheet-mol-66r` (UC-C) open children (`mol-4d0`, `mol-4nt`, `mol-87z`,
  `mol-eal`) for the same superseded-by-organic-work pattern and close if confirmed — same
  action as this session's `mol-dhd` cleanup, immediate.
- c: update `/technical-debt` skill's implicit-resolve check — in addition to
  commit↔description matching, also match recently-closed bead titles/close-reasons against
  the *titles* of open molecule-formula step children sharing a parent epic (titles encode
  the feature name even when descriptions are empty), e.g. "UC-D archive closed actions"
  appears in `mol-dhd`'s children titles and could be matched against `d33z`'s title
  "Archive scenario coverage — rows moving Actions→Archive sheet".
- b: update `mol-feature-delivery.formula.yaml` (or add a CLAUDE.md note on `bd cook` usage)
  — require each generated step's description to be populated with the use-case ID and a
  one-line scope statement at pour time, so later text-matching has something to match.
- e: `bd remember` — before starting new beads for a capability, check `bd list` for open
  molecule/epic children with overlapping feature names that might already cover (or be
  superseded by) the new work.

## Note on resolve sequencing

This overlaps with the still-staged `2026-06-02-no-aggregate-technical-debt-surface.md`
(root cause: no aggregate debt surface for implicitly-resolved issues). That LL's proposed
`/technical-debt` skill now exists but its staging file was never moved to `resolved/`.
Recommend resolving both together at the next gate: confirm the skill addresses LL-2026-06-02's
category-2 "implicitly-resolved issues" in general, then layer this LL's Branch A/B/C
refinements (title-matching, `bd stale` tuning, cross-track reconciliation) on top, and move
both files to `resolved/`.

## Follow-up audit (2026-06-11 session): all issues created >1 week ago

Per candidate **f**, audited every open issue created before 2026-06-04 for the same
superseded-but-never-closed pattern, plus a related but distinct variant.

### Confirmed same pattern — `GTaskSheet-mol-66r` (UC-C tracker table)

Sibling molecule to `mol-dhd`, created the same day (2026-05-22), same formula. 5 of 9
children (`mol-6dl` verify, `mol-7ui` UC/AC gate, `mol-bgq` develop-tests, `mol-crb` draft-AC,
`mol-hzj` independent review) were already closed; the same 4 step-types as `mol-dhd`
(`mol-4d0` address-findings, `mol-4nt` gate-review-findings, `mol-87z` gate-final-signoff,
`mol-eal` update-docs) sat open with empty descriptions since 2026-05-22. Evidence of organic
delivery: `mol-vzk` (commit `c40f14c`, implement `insertTrackerTable`), `mol-bgq`
(`4ec70ee`, UC-C fixtures), `gxot` (`a859c21`/`47d4ae7`/`2864daf`, tracker Playwright coverage,
all green), `docs/CONTEXT.md` §UC-C + §In-Doc Action Tracker Table, `docs/DESIGN.md`
TrackerTable/Tracker Table Renderer sections. **Action taken this session:** closed `mol-4d0`, `mol-4nt`, `mol-eal`, `mol-87z`, and (after
explicit human confirmation — the auto-mode permission classifier initially blocked closing
`mol-66r` as "beyond the explicit 'evaluate and add to LL' request") `mol-66r` itself, all
as superseded (same reasoning as `mol-dhd`'s children). This is a second independent
confirmation of root causes A/B/C, not a new root cause. Note for candidate g/Branch D:
closing `mol-66r` unblocks `mol-29y` (its dependency on `mol-66r`, `mol-dhd`, `mol-vea` are
now all closed) — but `mol-29y` is reviewed below as genuinely still-open work, not a further
instance of this pattern.

### New variant — `GTaskSheet-cw5` (closed this session)

`cw5` ("[IMP] Deliver rich sidebar for Docs add-on", epic, created 2026-05-27) had **10/10
children closed** and `bd show` itself displayed "✓ 10/10 complete (100%) — eligible for
close" — yet the epic bead was left open. This is a *simpler* variant of the same family:
no empty-description placeholders, no cross-track reconciliation needed — `bd`'s own
completeness check already had the answer, but nothing acts on "eligible for close" signals.
**Action taken:** closed `cw5` citing the 100% child completion and `html-sidebar-card-pivot`
(CardService delivery). Suggests a 4th branch:

Branch D — `bd`'s "eligible for close" signal on fully-complete parents is not surfaced/acted on
Why 1 — `bd show <epic>` prints "✓ N/N complete (100%) — eligible for close" only when a
        human runs `bd show` on that specific bead.
Why 2 — No periodic/aggregate check lists epics where all children are closed but the
        parent is still open.
Why 3 — `bd stale`/`bd doctor --check=conventions` do not include "100% children closed,
        parent open" as a convention violation.
Root cause D: `bd`'s own "eligible for close" completeness signal has no aggregate surface
or session-start check, so it only fires when a human happens to inspect that exact bead.

### Reviewed, NOT superseded — still valid, no action taken

- **`GTaskSheet-mol-kqr`** (v1 Ship epic) and its remaining open children (`mol-29y`
  independent review, `mol-7gg` update OPERATIONS.md, `mol-b4e`/`mol-e9j` gates, `mol-isu`
  address-findings) for "All-UC verification and test suite sign-off" — genuinely blocked on
  `GTaskSheet-erc` (production deployment), which work-log line 1027 explicitly confirms is
  "not yet done" (pre-production). `mol-vea` (the implement step) was already closed
  2026-05-20 as "already complete", but the surrounding review/gate/docs steps legitimately
  await production rollout. No closure action.
- **`GTaskSheet-erc`** + `erc.1`-`.3` (production deployment) — depends on `mol-kqr`;
  production has not been configured. Still valid backlog.
- **`GTaskSheet-6ov.9`** ("Update gas-addon-guide.md: restructure as general Google ecosystem
  add-on guide") — `gas-addon-guide.md` does not exist anywhere in the repo; work not done.
  Still valid (parent `6ov` correctly stays open because of this one child).
- **`GTaskSheet-egl9`** (evaluate `/dev` vs versioned `/exec` deployment for test cycle) —
  recorded in work-log 2026-06-01 but no decision/evaluation recorded since. Still valid,
  undecided.
- **`GTaskSheet-w6vg`** (test_b7/test_uc_scenarios/test_uc_sidebar failures) — already
  re-scoped 2026-06-02 with its own verification steps. Step 1 (re-run current suite) appears
  satisfied — work-log 1530 shows `test_b7_write_routes` now PASSED and 1817 shows a 230-test
  full-suite green run (commit `cb88d91`). Step 3 (session-scoped teardown in
  `tests/conftest.py` marking journey-clone rows `mark_doc_not_found`+archive) was checked
  and is **not present** in `tests/conftest.py`. Still valid — narrowed to step 3 only.
- **`GTaskSheet-mpi9`** (LL resolve: CLAUDE.md pytest-x backstop rules + implementation-gate
  v1.3 additions, created 2026-06-03) — checked project `CLAUDE.md` and
  `.claude/skills/implementation-gate/SKILL.md` for the four described rules (pytest -x
  before [IMP] close, known-failure escalation, verify_consistency/verify_all_expectations
  pairing, proof-of-effectiveness for new assertions) — none present yet. Still valid,
  awaiting human review as its own description states.

### Updated Initial Candidates

- f: **done** — `mol-66r` and its 4 step children all closed this session (human-confirmed).
- g (new): add a session-start or `bd doctor` check for Branch D — epics where all children
  are closed (bd's own "eligible for close") but the epic remains open. Lower-cost than
  Branch A/B/C's title-matching since it needs no text search, just child-status aggregation.
- c, b, e: unchanged from original capture.
