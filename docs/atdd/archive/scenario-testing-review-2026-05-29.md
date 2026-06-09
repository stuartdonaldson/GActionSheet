# Review: Scenario Testing Approach for Broad Coverage

_Reviewer note, 2026-05-29. Subject: `docs/atdd/atdd-lifecycle.md` §11–§15 — the scenario-workflow test layer. Goal of the review: assess how well the documented approach achieves **broad coverage of varied functionality** through scenarios, and recommend extensions for under-covered lifecycle paths (deleted actions, sheet-side modifications, deleted files, and similar)._

---

## Summary

The scenario layer is well-conceived as a *mechanism*: the queued-expectation pattern (§13), the two-tier checkpoint model (§11), and the thin-driver / standalone-assertion split (§15) are the right primitives for exercising long, realistic user journeys cheaply against an expensive external system. The approach is sound.

The weakness is **coverage breadth and failure-domain isolation**, not mechanism. The documented `test_01`–`test_12` sequence is essentially one happy-path creation-and-edit journey with a single conflict case and a single delete case bolted on the end. It does not yet exercise the destructive and reconciliation paths that carry the highest data-loss risk: document-initiated deletion, whole-document deletion / orphaned rows, the time-based `syncAll` sweep, and the live `onActionSheetEdit` trigger. The document even flags one of these as known-fragile and explicitly *deprioritizes* it (§15, init-variants table: "rough edges around delete-all scenarios — **not prioritized**"), which inverts the correct risk ordering.

Two structural changes would convert the approach from "one long happy path" into genuine broad coverage: (1) make **system-wide invariants** — not just per-item expected values — the backbone of each checkpoint, so the suite catches regressions nobody enumerated; and (2) split the single 23-step monolith into a small set of **themed journeys** that isolate failure domains and stay clear of the six-minute GAS ceiling.

---

## Findings, ordered by priority

Each finding is tagged **[COV]** (a coverage gap — functionality not exercised) or **[METH]** (a methodology issue with the approach itself). P0 = correctness/data-loss risk currently uncovered; P3 = lower-risk or structural polish.

> **Scope note on "uncovered."** Several reconciliation paths below already have **atomic-test or HTTP-fixture** coverage (e.g. `setupTestFixtures` cases `sync_status_deleted`, `sync_status_doc_not_found`, `sync_status_recovery`, `sync_status_on_edit`, plus the §Atomic Tests "Duplicate / orphan reconciliation" entry). The gap these findings address is the **scenario-journey** layer: the end-to-end user journey where the destructive action is itself the call-site and the post-state is reconciled across doc + sheet + tracker together. "Uncovered" here means "not in the journey," not "untested anywhere," except where stated otherwise.

### P0 — Critical

**P0-1 [COV] Document-initiated deletion is not in the journey.**
The only deletion path in the journey is `test_12` (mark deleted via the preview card → `Deleted` in sheet, removed from doc). The far more common real-world action — a user deleting the `AI-N:` paragraph text directly in the document and then syncing — is not exercised end to end. The orphan pass in `_handleSyncActionRows` is the code that must handle it (a row whose `globalId` is no longer present in the doc is stamped `Deleted`, or removed as a stale duplicate if the same text+assignee reappears under a new token); the `sync_status_deleted` fixture and the atomic orphan-reconciliation test touch this logic, but no journey drives it through the **doc-text-deletion call-site** and reconciles the result across doc + sheet + tracker. This is the highest-risk reconciliation path: the system must not silently drop sheet-side data (status/assignee a human entered) and must distinguish a genuine deletion from a re-token. Add a journey step: seed → sync → delete the paragraph in-doc → sync → assert the sheet row reaches `Deleted` **and** the tracker row reflects it. Include the negative assertion that the action no longer appears among live doc actions, and a paired case where the same text+assignee reappears under a new `AI-N` (must dedup, not orphan).

**P0-2 [COV] Whole-document deletion / orphaned sheet rows are not in the journey ("deleted files").**
When a tracked Google Doc is trashed, `syncDocument` fails to `openById`, calls `_markDocNotFound`, and stamps `Doc Not Found` on every row for that `docId`; the `syncAll` sweep is what reaches those rows in production. Fixtures `sync_status_doc_not_found` and `sync_status_recovery` exercise the stamping/recovery logic, but no journey drives the **whole-document-trash → sweep** path end to end, and the sweep enumerates docIds from the column-7 `HYPERLINK` formulas — a parse step with its own failure surface. This is the user's "deleted files" case. Add a dedicated journey: create doc + actions → sync → trash the doc → run `syncAll` → assert rows reach `Doc Not Found`, the sweep completes cleanly for surviving documents, and recovery (un-trash → sweep) restores a live row (mirrors `sync_status_recovery`). Use a multi-doc fixture so the negative — "other docs' rows unaffected" — is assertable.

### P1 — High

**P1-1 [COV] `syncAll` time-based sweep is never exercised as a call-site.**
The sync table (§15) lists `syncAll` as a distinct entry point, but no test invokes it. Per the project's **entry-point coverage invariant** (CLAUDE.md), every state-modifying entry point must be the call-site in ≥1 scenario with observable state verification — testing `syncDocument()` does not discharge the obligation for the sweep that *calls* it across all docs. Cover it via the orphan journey (P0-2) and via a multi-doc happy-path sweep.

**P1-2 [COV] The live `onActionSheetEdit` installable trigger is not exercised as a real edit.**
`test_07` sets `Dirty` programmatically because doPost writes run as the deployer and do **not** fire `onActionSheetEdit` (Programmatic Write Suppression, verified 2026-05-29). That correctly tests the *resolution* rule. Fixtures `onedit` / `onedit_id` / `sync_status_on_edit` seed rows for the stamp logic, but the trigger that actually fires on a real cols-3–6 user edit — stamping `Date Modified` + `Dirty`, then flushing to the doc and re-syncing (Scenario B) — is not driven by a real edit in any journey. This is a state-modifying entry point whose live call-site has no journey coverage. Exercise it through the path that fires it (Playwright sheet-cell edit) and assert the stamp lands *and* the doc paragraph updates, since the handler does both.

**P1-3 [COV] Status lifecycle is only partially walked.**
Coverage touches `Open → In Progress` (`test_11`) and `→ Deleted` (`test_12`). Missing: `In Progress → Done`, reopen (`Done → Open`/`In Progress`), and the propagation/tracker consequences of each. Status is a primary user-facing behavior; the lifecycle should be walked end to end at least once, with the tracker row re-rendering asserted at each transition.

**P1-4 [METH] Strict linear ordering makes one early failure mask all later coverage.**
The module-scoped, order-dependent design (§15) is deliberate, but for a *broad-coverage* suite it means a failure in `test_03` hides whether `test_04`–`test_12` would have passed — the opposite of broad signal. The queued-verification pattern (§13) already supports the fix: let non-fatal step failures record the failure and continue, then evaluate the full expectation queue at the end. Reserve hard aborts for setup/teardown and integrity-checkpoint failures. This preserves the intentional dependency while recovering coverage signal after a mid-journey defect.

**P1-5 [METH] The ActionSheet accumulates across runs with no reset — invariant assertions must be doc-scoped.**
The fixtures filter every sheet read by `testDocId` (matching the column-7 `HYPERLINK` formula) precisely because the shared ActionSheet is **accumulate-without-reset**: rows from prior sessions persist. The journey's fresh-empty-doc start (§15) isolates the *doc* side but not the *sheet* side. This is a correctness trap for the invariant approach recommended in P2-1: a naive "no two rows share a `globalId`" or "row count == N" invariant will read polluted cross-session state and either false-pass or false-fail. Every scenario invariant and every `sheet_rows()` read must be scoped to the journey's own `docId` (the journey doc is unique per run, so its `globalId` prefix is a clean scope). State this constraint explicitly in the scenario-architecture section so invariant authors do not assert over the whole sheet. A periodic test-tab cleanup (or a dedicated test ActionSheet) would harden it further but is not required if scoping is disciplined.

### P2 — Medium

**P2-1 [METH] Assertions are enumerated per-item, not invariant-based — this caps achievable breadth.**
`test_01`–`test_12` assert specific expected values for specific seeded items. That catches regressions someone thought to enumerate; it misses the unanticipated ones. For broad coverage, every integrity checkpoint should also assert **system-wide invariants**, scoped to the journey's own `docId` (see P1-5), e.g.:
- every live doc `AI-N` has exactly one non-terminal sheet row and vice versa;
- no two rows for this doc share a `globalId`;
- every `Deleted`/`Done` action's tracker row matches its status;
- the `AI-N` token / `globalId` is preserved across every mutation (no re-token churn).

Invariants are what turn a single journey into broad coverage, because they hold over *all* state the journey produced, not just the items the author listed. The system already relies on these properties (1:1 doc-row pairing, stable `globalId`, dedup of re-token duplicates) — asserting them as invariants is cheap and catches the regressions enumerated expectations miss.

**P2-2 [COV] Sheet-side modification coverage is shallow.**
`test_03`–`test_05` each change one field on one clean row and confirm propagation. Missing variants the system must handle: multi-field edits in one sync window; clearing a field (e.g. removing an assignee) rather than setting it; an edit to an identity-bearing value; and an edit on a row whose doc paragraph also changed in the same window (beyond the single `test_07` Dirty case). Per §6 these belong inside a data-driven variant table within one sync round, not as separate execution rounds.

**P2-3 [COV] Malformed / negative inputs are under-covered (regression risk).**
A recent fix ("invalid email in floating action skips — no abort") has no scenario guarding it. §7 mandates negative cases as first-class, yet the example scenario asserts mostly presence. Add malformed-tag, invalid-email, and duplicate-`AI-N` inputs to the seed table, each with an explicit absence/skip assertion, so the skip-not-abort behavior is locked in.

**P2-4 [COV] Tracker table only tested on insert, not update/re-render.**
`test_02` inserts the tracker table once. Nothing asserts the tracker updating when an action's status changes, when an action is deleted, or when a new action is added after the table already exists. Fold tracker re-render assertions into the status-lifecycle (P1-3) and deletion (P0-1) journeys.

**P2-5 [COV] Multi-document scoping has no negative test.**
A standing project invariant is that action lookups are document-qualified and must never return actions globally. No scenario seeds a *second* document's rows to prove the first journey's reads exclude them. Add a second-doc fixture and an absence assertion in the integrity checkpoint (this fixture is also reused by P0-2 and P1-1).

**P2-6 [METH] §15 architecture has already drifted from the implementing fixtures — reconcile before extending.**
The §15 note states the journey "starts with a **new empty Google Doc** … `DocumentApp.create(name)`," but the implemented `begin_journey_session` fixture **clones the master template** (`DriveApp.getFileById(testDocId).makeCopy(...)`). Separately, the `sync_status_deleted` fixture — the closest existing thing to P0-1 — still removes a **named range** and reasons about `getNamedRanges()`, which is the superseded ADR-0008 identity model (the live scanner is token-based on `globalId`); that fixture's NR handling is likely dead code against current behavior. Both are signs the scenario layer is being designed in `atdd-lifecycle.md` while the fixtures evolve separately. Before building the P0/P1 journeys, reconcile §15 with the fixtures (clone-vs-create; token-vs-NR deletion) so new journeys are written against real behavior, not a stale spec.

### P3 — Lower / structural

**P3-1 [METH] Split the monolith into themed journeys.**
One 23-step scenario risks the six-minute GAS ceiling (§6) and couples unrelated failure domains. Recommend a small suite of independent journeys, each a module-scoped session: **(A)** Creation & Import; **(B)** Sheet-side edit & conflict; **(C)** Deletion & lifecycle; **(D)** File/orphan & sweep. Each stays short, isolates failures, and runs (or skips) independently.

**P3-2 [COV] Idempotency is tested only for the no-op case.**
`test_08` re-runs sync with no changes. Idempotency of *mutating* operations is not covered: delete twice, sync after a delete, re-run the sweep over already-reconciled orphans. §8 requires idempotency to be an explicit test per repeatable operation — extend it to the destructive paths.

**P3-3 [COV] Resurrection / ID reuse is untested.**
Delete an `AI-N` action (doc or sheet side), then re-introduce the same `AI-N` token and sync. Does the system reuse, collide, or re-derive the `globalId`? Undefined-and-untested; cheap to add to journey C.

**P3-4 [COV] Assignee edge cases beyond the domain-chip happy path.**
Non-domain email, chip↔plain-email transitions, and assignee clearing are not exercised. Add as data-driven variants within journey A/B.

---

## Recommendation

Adopt the scenario mechanism as documented, with three changes, in this order:

1. **Re-order by risk.** Build the two P0 destructive journeys (document-initiated deletion; whole-document deletion / orphan sweep) before extending the happy path further. Reverse the §15 stance that delete-all is "not prioritized" — known-fragile + high-impact is exactly what scenario coverage exists to protect.

2. **Make invariants the checkpoint backbone (P2-1) and let the expectation queue survive non-fatal failures (P1-4).** Together these convert a linear happy path into genuine broad coverage: the suite then asserts properties over *all* state each journey produces and keeps reporting coverage past the first defect.

3. **Split into themed journeys (P3-1) and publish an entry-point coverage matrix.** The matrix maps every state-modifying entry point — `syncDocument`/doPost, sidebar Sync Now, `onActionSheetEdit`, `syncAll`, `@create`, preview-card actions — to the journey step that is its call-site, making the CLAUDE.md entry-point invariant auditable. The matrix immediately exposes the current `syncAll` (P1-1) and live-`onActionSheetEdit` (P1-2) gaps.

These are additive to the existing `test_01`–`test_12` design; none require discarding the documented architecture. The `ScenarioSession` / standalone-assertion split already accommodates invariant assertion functions and multiple module-scoped sessions without modification.

---

## Coverage matrix (current vs. recommended)

| Functional area | Covered today | Gap | Finding |
|---|---|---|---|
| AI-tag import, ID assignment, assignee/chip | `test_01` | — | — |
| Tracker insert | `test_02` | update / re-render / delete | P2-4 |
| Sheet→doc propagation | `test_03`–`05` | multi-field, clear, identity edits | P2-2 |
| Doc-wins / Dirty conflict | `test_06`–`07` | live trigger stamp path | P1-2 |
| No-op idempotency | `test_08` | mutating-op idempotency | P3-2 |
| Sidebar / `@create` / preview-card status | `test_09`–`11` | full status lifecycle, reopen | P1-3 |
| Delete via preview card | `test_12` | **doc-initiated delete** | **P0-1** |
| Whole-doc delete / orphans | — | **entire path** | **P0-2** |
| `syncAll` sweep entry point | — | call-site coverage | P1-1 |
| Multi-doc scoping (negative) | — | absence assertion | P2-5 |
| Malformed input / invalid email | — | skip-not-abort regression | P2-3 |
| Resurrection / ID reuse | — | entire path | P3-3 |

"Covered today" = the `test_01`–`test_12` journey. Several "—" rows have **atomic-test or HTTP-fixture** coverage (`sync_status_deleted`, `sync_status_doc_not_found`, `sync_status_recovery`, `sync_status_on_edit`, orphan-reconciliation atomic) — the gap is journey/entry-point coverage, per the scope note above.

---

_2026-05-29_
