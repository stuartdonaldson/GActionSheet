# LL: Technical debt accumulates across sessions without an aggregate surface for review

Date: 2026-06-02
Domain: process

## Observation
Across this sprint, three distinct categories of invisible technical debt accumulated and were
only discovered through unrelated downstream work:

1. **Failing tests** (GTaskSheet-w6vg): 11 test failures filed after the 2026-05-31 session.
   Tracked individually, attributed to a plausible-but-unverified cause, classified P3, and
   the merge proceeded. Root cause (scanner regression) not identified until 6ov.8.

2. **Implicitly-resolved issues**: Several bd issues were found during this sprint to have
   already been addressed by other work without being marked in-progress or closed. They
   remained open in the backlog, making the true state of outstanding work unclear.

3. **Stale/orphaned issues**: bd doctor and bd stale produce signals about drift, but these
   are run ad hoc rather than as part of a regular review cadence.

In each case, the debt item was technically trackable — a test failure bd issue existed, the
beads backlog existed, bd commands could query state. What was missing was an aggregate view
that organized all debt across categories, made the total picture visible before new work
started, and required a human decision about how to proceed.

The technical-debt review also never happened as a group. Individual items were addressed
(one test failure filed, one issue closed) but the pattern — "we have accumulated N items
of unresolved debt across M categories; what is our posture before the next sprint?" — was
never surfaced. Without the aggregate view, individual items look like isolated maintenance
tasks rather than signals of a systemic accumulation.

## Why Chain

Why 1 — Failing tests, stale issues, and implicitly-resolved beads accumulated invisibly.
Why 2 — Each category has a query mechanism (pytest, bd stale, bd doctor, bd list) but no
         single skill aggregates them, organizes by importance, and presents them for review.
Why 3 — Debt review is not part of any session cadence; it is ad hoc and only happens when
         something breaks visibly enough to prompt investigation.
Why 4 — The session-start-check skill surfaces the current sprint and immediate blockers
         but does not include a structured debt review across all categories.
Why 5 — No convention requires reviewing accumulated debt as a group before proceeding;
         items are addressed individually when noticed, which misses patterns and allows
         the aggregate to grow.

Root cause: There is no skill, cadence, or gate that aggregates technical debt across
categories (test failures, stale issues, implicitly-resolved beads, unverified assertions)
into a single prioritized view for human review. Debt accumulates in individually-trackable
but collectively-invisible form until it produces a visible failure.

## Connection to existing LLs in this batch
All three other LLs from this session are instances of this gap:

- LL-1 (scanner-change-did-not-audit-fixture-producers): the scanner regression became
  invisible debt the moment 6ov.7 merged without triggering any aggregate debt review.

- LL-2 (new-assertion-vacuously-passes-on-empty-result-set): unverified assertions are a
  form of hidden technical debt — tests that appear to cover something but may not fire.
  No aggregate surface would make these visible today.

- LL-3 (test-failures-observed-but-not-elevated): the 11 failures were individual tickets;
  an aggregate debt review would have shown "11 open test failures + 2 stale issues + N
  implicitly-resolved beads" as a total picture requiring a group decision.

## Note on group-before-individual resolution
The resolution of debt items should follow the same principle as LL resolve: review the full
set before addressing individual items. An individual P3 test failure looks like maintenance.
Eleven P3 test failures across three test files, all attributable to one mechanism change,
is a sprint-blocking pattern that changes the proceed/address decision.

A technical-debt review skill should present the full picture and ask for a single
proceed/address decision covering all categories — not invite piecemeal triage that obscures
the aggregate signal.

## Proposed skill concept: /technical-debt

Trigger: session start (if backlog has items matching debt criteria), before starting a new
[IMP] issue, at any gate/merge transition.

Sources the skill would aggregate:
- **Test failures**: last pytest run status; open bd issues with [FIX] or [TST] prefix and
  "fail" / "broken" / "regression" in description; sync.scanned count:0 in recent GAS logs
- **Implicitly-resolved issues**: recently merged commits (git log since last sprint close);
  for each, scan bd list --status=open for issues whose description overlaps the commit scope;
  flag for human confirmation ("this commit may have addressed this issue — confirm or defer")
- **Stale issues**: bd stale output; issues with no activity in N days
- **Orphaned/blocked issues**: bd orphans, bd blocked
- **Unverified assertions**: bd issues or CLAUDE.md notes marked "needs proof-of-effectiveness"
  (a tag added by LL-2 resolution if adopted)

Output format:
```
## Technical Debt Review — [date]

### Category: Test failures (N items)
[ordered by risk: unknown-cause > known-unresolved > known-deferred]

### Category: Implicitly-resolved issues (N candidates)
[ordered by age]

### Category: Stale / orphaned issues (N items)

### Category: Unverified assertions (N items)

---
Total debt: N items across M categories
Decision required: address before proceeding / accept and track / defer with date
```

The skill does not resolve any item. It presents the aggregate for human decision. Resolution
of individual items proceeds only after the human has seen the full picture and chosen a posture.

## Why individual titles look like noise

The granularity of individual debt items and the absence of context clues in their titles
makes a list of open issues read as routine maintenance rather than a structural signal.

Example contrast:
  Noise-title:  "[FIX] 11 pre-existing test failures — shared test doc accumulated legacy rows"
  Signal-title: "[DEBT:TEST-REGRESSION] scanner rewrite broke all chip-led fixture helpers — 11 tests"

The signal title encodes three things the noise title omits:
  1. A debt category marker ([DEBT:TEST-REGRESSION]) that groups it with similar items on scan
  2. The root cause or mechanism (scanner rewrite broke fixture helpers)
  3. The scope signal (11 tests) that shifts interpretation from "one broken test" to "pattern"

Without these, even a well-intentioned debt review requires opening each issue to understand
its weight. A list of noise-titled items looks like a backlog to triage; a list of signal-titled
items reads as a structured debt picture at a glance.

Two complementary resolution directions:

**Direction 1 — Better issue title conventions**
Debt issues need a richer title schema that encodes category, mechanism, and scope without
requiring the body to be opened. The existing [IMP]/[TST]/[FIX]/[INF] prefix encodes work type
but not debt class or causal signal. A debt-class marker (e.g. [DEBT:TEST-REGRESSION],
[DEBT:STALE], [DEBT:IMPLICIT-RESOLVE], [DEBT:UNVERIFIED]) layered on top of the existing
prefix would make category visible on scan. Mechanism and scope in the title (even brief:
"scanner change broke N fixture helpers") complete the signal.

**Direction 2 — LLM synthesis before presenting the list**
Even with better titles, a list of 15 items requires synthesis to reveal the aggregate pattern.
The /technical-debt skill (and the AI in any debt-review context) should read the full item set
before presenting it, and synthesize the pattern first:

  "I see 11 test failures across 3 test files, all attributable to a single mechanism change
   (scanner rewrite). Plus 3 stale issues from the same sprint and 2 implicitly-resolved beads.
   The test failures are not isolated — they are one incident. Presenting as: 1 structural
   test-regression incident (high severity) + 3 stale items + 2 implicit-resolves."

This is what changes "noise list" to "signal summary." The LLM is the right layer to do this
synthesis because it can read issue bodies, trace commonality across titles, and recognize
when N individually-P3 items are collectively a sprint-blocking pattern.

## Initial Candidates

c: create `/technical-debt` skill — aggregates pytest status, bd stale, bd orphans, bd doctor,
   open [FIX]/[TST] issues, and recently-merged commits vs. open issues; synthesizes aggregate
   pattern before presenting (groups related items, names the pattern, recalibrates severity);
   requires explicit human proceed/address/defer decision before closing

c: update session-start-check skill — add a debt-summary step: run bd stale, bd doctor --check=conventions,
   and check for open [FIX]/[TST] issues; if any found, surface synthesized summary (not raw list)
   before surfacing the sprint's ready work; require the human to acknowledge the debt state

c: update merge-gate skill — as part of the gate, run the technical-debt aggregation and synthesis;
   include the debt summary in the gate report; require explicit human posture decision
   (proceed/address) before the gate closes

b: update bd issue title convention in project CLAUDE.md — debt issues should encode:
   (1) a debt-class marker beyond the work-type prefix (e.g. TEST-REGRESSION, STALE, IMPLICIT-RESOLVE),
   (2) the causal mechanism or root cause in brief, (3) the scope signal (N tests, N files, etc.);
   example: "[FIX][DEBT:TEST-REGRESSION] scanner rewrite broke chip-led fixture helpers — 11 tests"

b: add to project CLAUDE.md — "when filing or reviewing debt issues, synthesize before listing:
   read all items, identify shared root causes or mechanisms, group related items, present the
   pattern summary first; N individually-P3 items with a shared root cause are not N separate
   P3 items — they are one incident with N symptoms, and severity is assessed on the incident,
   not the symptoms"

Preferred ordering: the /technical-debt skill (c) is the primary lever — it combines the
synthesis capability (Direction 2) with the aggregate surface. The title convention (b) makes
synthesis easier and the list scannable without requiring the skill. Both are needed: the skill
handles real-time review; the title convention degrades gracefully when the skill isn't run.

## Note on resolve sequencing for this LL batch
The four LLs from this session (scanner-audit, vacuous-checks, debt-not-elevated, this file)
share overlapping lever targets: merge-gate skill, session-start-check skill, CLAUDE.md.
They should be resolved as a group in a single batch, not individually, to avoid applying
four separate incremental patches to the same artifacts. The aggregate resolution should
produce one updated merge-gate skill, one updated session-start-check, and one coherent
CLAUDE.md testing strategy section — not four separate edits that may contradict or duplicate.

## Resolution (2026-06-12)

Largely applied as a group, per the note above. `/technical-debt` skill v1.0 exists
(`/home/stuar/.claude/skills/technical-debt/SKILL.md`) and implements Direction 2 (LLM
synthesis before presenting): it aggregates test failures, open [FIX]/[TST] issues,
`bd stale`, `bd doctor --check=conventions`, and implicit-resolve candidates (commit↔description
matching), groups them into named incidents, and requires an explicit a/b/c human decision.
`merge-gate` v1.1 Step 0 invokes it. Selected lever: c (the skill itself), as preferred.

Residual, not blocking: the title-convention (Direction 1, "[DEBT:...]" markers) was not
added — the synthesis-first skill makes it optional polish rather than load-bearing.
Category-2 (implicitly-resolved issues) refinements — title-matching against molecule-step
children, `bd stale` threshold tuning, and the "100%-children-closed-parent-open" check —
are carried forward in `2026-06-12-molecule-placeholder-issues-stayed-open-after-scope-delivered-elsewhere.md`
(still staged), which itself proposes a follow-up bd issue for `/technical-debt` v1.1.

Verify: had this skill existed before 2026-06-01, `merge-gate` Step 0 would have aggregated
the 11 failures into one named "scanner rewrite" incident and required a proceed/address
decision — addressing this LL's category 1 directly (categories 2/3 addressed to the extent
described above).
