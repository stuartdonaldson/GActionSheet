# Candidate methodology lever: oracle-driven ordering

> **STATUS: CANDIDATE / LEVER UNDER TEST — not ratified.**
> Trial owner: GActionSheet · Tracking: `gts-m65t` · Opened: 2026-07-01
> Promotion target: DevStandard `sdlc-testing-principles.md` **T23** (amend, not a new ID) + project ADR-0013.
> This file is the single portable artifact: it is what you copy to trial the lever on
> another project, and what you review for DevStandard integration once proven.

## The rule (one paragraph)

"Test-first" bundles two claims; only one is load-bearing.
**Coverage-before-merge** — the durable invariants and every state-modifying entry point
(T17) are tested before merge — is non-negotiable.
**Ordering** — whether the test is written *before* the implementation — is negotiable and
is chosen by the **oracle**:

- **Specifiable oracle** — correct is a precise value/state you can write down *before* coding
  (parsed value, row status, contract shape). → **Test-first** (red → green). Debugging the
  test *is* debugging the contract.
- **Perceptual oracle** — correct is recognized on sight but cannot be cheaply pre-specified
  (most UI/UX, rendered output, layout/feel). → **Slice**: implement a thin instance → human
  review → freeze the AC → author the hardening test against the frozen contract. A pre-written
  assertion here is both expensive *and* blind to the emergent anomaly the human eye catches.

## Why this is a refinement of T23, not a new principle

T23 already defines Spec / Slice / Hardened fidelities and the durable-invariant smoke rule.
This lever contributes four things T23 does not yet state:

1. **The ordering-vs-coverage split** — the unifying frame that ties T23's Slice, the
   durable-invariant rule, the blocking hardening bead, and proof-of-effectiveness into one
   decision procedure.
2. **The oracle test as the trigger** — sharper and more actionable than T23's current trigger
   ("design error visible only in a built artifact"), and it reframes Slice from a *review gate*
   into an *ordering* decision (the human eye is the oracle; the test is authored after).
3. **Cost-asymmetry-is-diagnostic** — if the test is dramatically harder to write than the
   implementation, that asymmetry names the regime: immature harness (invest and amortize),
   perceptual oracle (use review, harden only the invariant), or a churning contract (slice first).
4. **The three guardrails bound to the relaxed ordering** (below).

## Guardrails (what keeps coverage-before-merge honest when you implement-first)

All three already exist independently; the lever binds them to the Slice ordering:

1. **Harden the durable invariant, not the volatile surface** still under review
   (T23 durable-invariant rule).
2. **Blocking hardening test bead** — the slice is not done until it is green (ADR-0013).
3. **Prove the hardening assertion fails** against the frozen contract before accepting it
   (proof-of-effectiveness).

## Deploying this lever to another project

Two paste-in edits. Adjust principle IDs (T17/T23) only if the target project cites the
DevStandard IDs; otherwise keep as-is.

### 1. Project CLAUDE.md — Testing Strategy section

Paste the rule + guardrails as a subsection titled
**"Ordering is oracle-driven; coverage-before-merge is the invariant (lever under test)"**,
citing the target project's own review-fidelity/ADR reference. (See this project's CLAUDE.md
for the exact block.)

### 2. Project implementation-gate skill — the ATDD phase-declaration step

Rename it **"Oracle & phase declaration"** and add, *before* the red/green/refactor
declaration: declare the oracle type (specifiable → test-first; perceptual → Slice), and for
perceptual state why an assertion cannot cheaply pre-specify "correct." Add the guardrails and
the diagnostic. Add a Success-Criteria checkbox for the oracle declaration. (See this project's
`.claude/skills/implementation-gate/SKILL.md` Step 4 for the exact wording.)

### 3. Record the trial

Add the deploying project as a trial site on `gts-m65t` (or its successor tracker) so
evidence aggregates across projects toward the promotion criteria.

## Promotion criteria (when to ratify into DevStandard)

Promotion is justified when:

1. ≥3 features (across ≥1 project) declared an oracle type at the gate and followed the chosen ordering;
2. ≥1 perceptual-oracle feature completed Slice → review → freeze → harden with all three guardrails observed;
3. Evidence is logged on the tracker (feature id, oracle type, outcome, friction);
4. No unresolved counter-example where the oracle partition failed (e.g. a mixed-oracle feature
   the two-way split could not classify).

On meeting these: amend T23 + ADR-0013, update the shared skills (implementation-gate,
test-strategy, tailoring), and move this file to a `promoted/` marker.

## Evidence log

| Date | Project | Feature / bead | Oracle type | Outcome / friction |
|------|---------|----------------|-------------|--------------------|
| _(none yet — deployed 2026-07-01)_ | | | | |
