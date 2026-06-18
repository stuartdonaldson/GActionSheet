# Testing Doc ID-Map — Legacy → bdd Principles

**Status:** active landing doc for this project's testing strategy.
**Adopted:** 2026-06-09.

This project's bespoke testing strategy has been **re-based** onto the shared,
ID-referenced universal layer in DevStandard. The old project-authored documents
were a hand-rolled realization of that same model; they are now **archived**
(`docs/atdd/archive/`) and superseded. Use this map to translate any legacy
reference you encounter (in code comments, issues, ADRs, CLAUDE.md, or git
history) into the new authoritative source.

## Authoritative sources (the new home)

| Layer | Location | Owns |
|-------|----------|------|
| Universal testing principles `T1`–`T24` | `/mnt/c/dev/DevStandard/knowledge-base/bdd/sdlc-testing-principles.md` | every testing "why" |
| Universal implementation/lifecycle principles `I1`–`I11` | `/mnt/c/dev/DevStandard/knowledge-base/bdd/sdlc-implementation-principles.md` | process, contract, ATDD phases |
| Operational pre-code gate | `/mnt/c/dev/DevStandard/knowledge-base/bdd/SKILL.md` (`implementation-gate`) | sequences the principles at the code-writing moment |
| Project testing guide (fill-in) | `/mnt/c/dev/DevStandard/knowledge-base/bdd/project-testing-guide-template.md` | project facts: stack, surfaces, journeys, coverage matrix |
| Project harness-design (fill-in) | `/mnt/c/dev/DevStandard/knowledge-base/bdd/project-harness-design-template.md` | the `scn/` build spec |

Relative from this repo root: `../DevStandard/knowledge-base/bdd/`.

**Rule:** cite the `T`/`I` ID. Do not restate the principle text in project docs —
that duplication is exactly what this re-base removed.

## Crosswalk — archived `atdd-lifecycle.md` → new IDs

### Part 1 & 2 (process)

| Legacy section | New ID | Source file |
|----------------|--------|-------------|
| Part 1 §1 — Work Item Typology (`[IMP]`/`[TST]`/`[FIX]`/`[INF]`) | `I1` | implementation-principles |
| Part 1 §2 — Twin-Ticket Lifecycle | `I2` (+`I5` both-green merge rule) | implementation-principles |
| Part 2 §1 — The Pre-Code Contract | `I4` | implementation-principles |
| Part 2 §2 — Parallel Tracks / no shared context | `I3` (+`I8` inner TDD loop) | implementation-principles |

### Part 3 — "Universal Testing Principles" #1–14

| Legacy # | Title (abbrev.) | New ID |
|----------|-----------------|--------|
| 1 | Two complementary test layers | `T1` |
| 2 | Organized by use case/workflow, not module | `T2` |
| 3 | ACs modular / reusable across scenarios | `T3` |
| 4 | Each focused AC test maps to one AC (docstring) | `T4` |
| 5 | Assertions verify durable, user-observable state | `T5` |
| 6 | Data-driven variants and scenarios both first-class | `T6` |
| 7 | Negative cases first-class | `T7` |
| 8 | Idempotency is an explicit test | `T8` |
| 9 | Fixtures isolated per run via named clones | `T9` |
| 10 | Assertions carry triage context | `T10` |
| 11 | Checkpoints balance confidence/runtime | `T11` |
| 12 | Pure logic may use focused helper tests | `T12` |
| 13 | Test architecture makes intended outcomes explicit | `T13` |
| 14 | Worked example (doc→sheet sync) | illustrative — see `T15` example, `T18` invariants |

> Note: `T14` (external boundaries not mocked) had no numbered Part-3 entry but
> was already practiced (real GAS boundary). `T15`/`T16` (Act/Expect/Checkpoint
> primitives, one-entry-point-per-act) lived in §16, not Part 3 — see below.

### §15 / §16 / §17 / §18

| Legacy section | New ID(s) | Notes |
|----------------|-----------|-------|
| §15 — Scenario Test Python Architecture | harness-design template + `I6` (contract ownership) | `scn/` is the filled-in build spec |
| §16.1 — scenario = three primitives | `T15` | Act / Expect / Checkpoint |
| §16.2 — the `ai` noun object | `T15` (domain noun) | |
| §16.3 — altitude / one entry point per act | `T16` | |
| §16.5 — four observation surfaces | `T5` | |
| §16.6 — expectations & verification | `T13` | queued verification |
| §16.7 — consistency / single-source authority | `T18` + `I6` | invariants at integrity checkpoints |
| §18 — AC-Validation Phase (ADR-0013) | `T23` + `I11` | review-fidelity phasing |
| §17 — Known Enhancement Candidates | `T17`–`T22` | see backlog mapping below |

### §17 backlog → newly-ratified coverage principles

The project's deferred enhancement candidates now have authoritative principle
homes. File these as `[TST]` beads tagged with the principle they discharge:

| §17 item | New ID | Meaning |
|----------|--------|---------|
| P0-1, P0-2 (doc/whole-doc deletion paths) | `T17` | entry-point coverage invariant |
| P1-1 (`syncAll` sweep as call-site) | `T17` | sweep entry point must be its own call-site |
| P1-2 (live `onActionSheetEdit` trigger) | `T17` | installable trigger as call-site |
| P1-3 (full status lifecycle) | `T22` | risk-ordered coverage extension |
| P2 — invariant-based assertions at INTEGRITY | `T18` | system-wide invariants |
| P2 — non-fatal failure mode | `T20` | accumulate-and-report |
| P2 — doc-scoped invariant assertions | `T19` | run-identity-scoped reads |

## Crosswalk — other legacy references

| Legacy reference | New ID(s) / source |
|------------------|--------------------|
| CLAUDE.md "Testing Strategy" — issue prefixes | `I1` |
| CLAUDE.md — twin-ticket rule | `I2`, `I5` |
| CLAUDE.md — pre-code contract | `I4` |
| CLAUDE.md — no shared context | `I3` |
| CLAUDE.md — review-fidelity phasing (ADR-0013) | `T23`, `I11` |
| CLAUDE.md — entry-point coverage invariant | `T17` |
| CLAUDE.md — regression coverage Path B (retroactive audit) | project overlay on `T17` (no universal ID — retroactive procedure stays project-local) |
| CLAUDE.md — red/green/refactor phases | `I7` (+`I8` inner loop) |
| CLAUDE.md — scope discipline / crash-fix rule | `I9`, `I10` |
| DevStandard `knowledge-base/methodology/testing/atdd-bdd.md` | superseded by `T1`–`T24`; its Given/When/Then framing maps to `T15` Act/Expect/Checkpoint |

## `scn/` package → harness-design template module map

| `scn/` module | Template role | Realizes |
|---------------|---------------|----------|
| `ai.py` | domain-noun object | `T15` |
| `contacts.py` | static contact list / name resolution | — |
| `engine.py` | expectation queue + checkpoint drain | `T11`, `T13`, `T15` |
| `surfaces.py` | per-surface readers | `T5`, `T19` |
| `session.py` | thin driver: lifecycle, acts, queries | `T16`, `I6` |
| `ui.py` | live-surface page-object driver | — |
| `contract.py` | loads authoritative contract export | `I6` |
| `assertions.py` | standalone per-surface comparison helpers | `T5`, `T10` |

## Open follow-ups (not done by this re-base)

Tracked under GTaskSheet-k22t. Status as of 2026-06-11:

- ~~CLAUDE.md pointers still cite archived paths~~ — **resolved**: this
  project's CLAUDE.md §Testing Strategy now cites `T1`–`T24`/`I1`–`I11` and
  this map as the starting point; the archived `atdd-lifecycle.md §15–§16` is
  cited only as the source material for the `scn/` realization, not as an
  authoritative reference.
- **`T24` (generated traceability) — reference implementation built 2026-06-09.**
  Emission: `scn/engine.py drain()` returns drained `(tag, surface, PASS|WARN)`
  records; `ScenarioSession.checkpoint()` appends each as a JUnit
  `ac.<tag>.<surface>` property via `request.node.user_properties`. AC
  registry: `scn/contract.AC_REGISTRY` (32 entries). Gap-diff:
  `scripts/check_coverage.py` diffs the registry against emitted `ac.*`/`ep.*`
  properties, exit 1 on gaps (see OPERATIONS.md §AC Coverage Check). Call-site
  tag format: `[<scenario> <ac-label>]`, e.g. `[journey sync-create]`.
  - ~~(a) not yet exercised end-to-end against a live journey run~~ —
    **resolved**: `scripts/check_coverage.py -v` run against the live
    `test_journey` run's `test-results/junit/pytest.xml` (2026-06-11) produces
    a correct AC/EP diff (3/32 ACs covered, 0/3 entry points covered),
    confirming the mechanism works end-to-end against real journey output.
  - ~~(b) the entry-point half of the gap-diff (`T17`) is built but only
    seeded (3 of the project's state-modifying entry points registered)~~ —
    **resolved (GTaskSheet-z6f8)**: `scn/contract.ENTRY_POINT_REGISTRY` now
    enumerates all 32 state-modifying entry points across the four call-site
    classes (menu items, time-based triggers, sidebar/add-on card actions, HTTP
    routes) plus state-modifying test-support routes — each description carries a
    `[category]` prefix; `[test-support …]` flags harness-only entries; read-only
    /diagnostic entry points are deliberately excluded. 10 are covered by tagged
    scenario call-sites; the remaining 22 are explicitly **warn-only** via
    `scn/contract.ENTRY_POINT_DEFERRED` (key → reason + tracking bead), which
    `scripts/check_coverage.py` treats as deferred (enumerated-but-not-yet-asserted)
    so the `ep.*` gap-diff is green (0 uncovered). Converting each deferred entry
    to a real tagged call-site assertion is tracked under EPIC GTaskSheet-rz4k
    (children rz4k.1 triggers, rz4k.2 routes, rz4k.3 cards, rz4k.4 menu, rz4k.5
    test-support). GTaskSheet-yuvq delivered the narrower onSyncNow doc-context
    slice first.
- ~~Two `implementation-gate` skills exist~~ — **resolved 2026-06-09**: at that
  time this project's `.claude/skills/implementation-gate/SKILL.md` was
  identical (byte-for-byte) to DevStandard's
  `dot-claude/skills/implementation-gate/SKILL.md` (both `v2.0`,
  `last_updated: 2026-06-08`). **Note (2026-06-18, GTaskSheet-mpi9):** the
  project copy has since diverged intentionally — it is now `v2.1` with
  three project-local additions (proof-of-effectiveness sub-step, test-infra
  compatibility check, full-suite `[IMP]`-close gate). This is a deliberate
  project-local override per the original 2026-05-27 LL's lever design, not
  drift to reconcile.
- ~~Fill the two templates~~ — **resolved 2026-06-18**: `docs/atdd/project-testing-guide.md`
  and `docs/atdd/harness-design.md` filled from §15/§16 and the `scn/` module
  map above. Tracked as GTaskSheet-ruoa.
