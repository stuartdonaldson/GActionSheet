# ADR-0013: Review-Fidelity Phasing in the ATDD Lifecycle

Status: Accepted (pilot scope — see Consequences)
Date: 2026-06-05
Extends: ADR-0006 (ATDD Lifecycle). Adds a phase upstream of the twin-ticket cycle; supersedes none of its commitments.

## Context

ADR-0006 commits to test-first twin-ticket development: an `[IMP]` and `[TST]` pair authored
together, no shared context, neither merging until both green. That model assumes the
acceptance criteria are *validated before coding begins* — the spec is trusted to describe the
intended behaviour.

A recurring failure has been observed against that assumption: a `[TST]`/`[IMP]` pair is taken
to green, and only when the human reviews the working result do they find the design itself is
wrong. The rework then hits *both* artifacts, because the test hardened an unvalidated design.
The cost is paid twice.

This is not specific to user-facing UX. The same happens when the reviewable artifact is a data
schema, an interface/entry-point signature, or a test scenario/journey: the human spots the
problem only on seeing a concrete instance, not from the prose spec. Agile practice names the
root cause — we frequently do not know exactly what we want at the start, and learning requires
iterating on something concrete. ADR-0006's pre-code contract surfaces *interface* disagreements
early, but not *design* disagreements that are only visible in a built artifact.

## Decision

Insert an optional **AC-validation phase** upstream of the ADR-0006 twin-ticket cycle.
Acceptance-criteria validation is recognised to have three fidelities; work selects the lowest
fidelity that can actually surface design error:

| Fidelity | Review artifact | Cost |
|----------|-----------------|------|
| Spec | written design field / contract prose | cheap |
| Slice | a thin concrete instance of the artifact (sample schema, stub interface, happy-path journey, rendered card) with smoke checks on durable invariants only | medium |
| Hardened | the industrialised build + full test matrix | expensive |

Commitments:

1. **Test-first is preserved; "first" is relative to the frozen AC.** The slice phase is
   *pre-AC-freeze*. A human review gate freezes the AC; downstream of the gate, ADR-0006's
   red→green twin-ticket runs unchanged against the frozen contract. The slice phase does not
   replace test-first — it sits upstream of it.

2. **Slice fidelity must be justified.** Spec/test-first is the default. Choosing Slice requires
   the author to state *why Spec review is insufficient* — that the design error is only visible
   in a concrete artifact. This prevents the slice phase from becoming a general backdoor around
   test-first.

3. **Twin-track independence is preserved at hardening.** Because the same agent may build the
   slice implementation and its smoke test, the slice implementation is **throwaway**, or the
   hardening `[TST]` is authored by a fresh-context agent against the frozen contract only,
   never reading the slice's code. ADR-0006's no-shared-context guarantee holds for the
   hardening tests.

4. **Smoke asserts durable invariants, not the volatile surface.** Even at Slice fidelity, smoke
   tests assert state that survives design iteration (a row round-trips; an unreadable
   document's actions never appear; an interface returns its contract shape). Volatile
   presentation (column set, field list, journey edge parts, UI copy) is left untested until the
   gate freezes it.

5. **The gate has three outputs, not one verdict.** (a) verdict — approve→harden or redesign the
   slice; (b) **funnel deltas** — newly-seen opportunities captured as one-liners in
   ROADMAP §Funnel, non-committal; (c) **open-seams register** — an explicit "do not foreclose X"
   list recorded in the hardening bead's design field, which *parameterises* hardening so tests
   assert the invariant a known future direction will share rather than pinning the current
   instance.

6. **"Keep open" is not "build now."** An open seam must be expressible as a one-liner plus a
   test parameter. Anything larger is scope creep and goes to §Funnel to be value/risk-evaluated
   at planning review, not pulled into the current slice.

7. **The merge guard is unchanged.** A sliced unit is not done until its hardening `[TST]` is
   green; the entry-point coverage invariant still holds. The slice phase produces a *created,
   blocking* hardening bead, not a promise to write tests later.

## Consequences

**Positive:**
- Design error is caught against a concrete artifact, when redesign is cheap — before assertions
  and full implementation exist to rework. Directly attacks the double-rework observed under
  ADR-0006.
- Applies uniformly to schemas, interfaces, journeys, and UX — any artifact whose flaws are only
  visible concretely.
- The review point becomes generative: it feeds §Funnel and preserves optionality via the
  open-seams register, so hardening preserves futures instead of deleting them by locking in too
  early.

**Negative / tradeoffs:**
- Adds a phase and a gate; justified only where Spec review is genuinely insufficient. Default
  remains Spec/test-first.
- Relaxes no-shared-context during pre-freeze exploration; mitigated by making the slice
  implementation throwaway or routing the hardening `[TST]` through fresh context.
- Risk that "harden later" becomes "harden never" — bounded by commitment 7 (blocking hardening
  bead + entry-point coverage invariant).
- Risk that open seams hoard scope — bounded by commitment 6 (one-liner + parameter, else
  →§Funnel).

**Pilot scope.** This ADR is accepted for the GActionSheet team-scope roadmap (EPIC-A–E) as the
trial. Graduation of review-fidelity phasing to the DevStandard universal testing methodology
(`atdd-bdd.md`) is deferred until the pilot provides evidence via lessons-learned at each epic
gate. The methodology change is itself subject to the iterate-on-concrete-evidence principle it
encodes.
