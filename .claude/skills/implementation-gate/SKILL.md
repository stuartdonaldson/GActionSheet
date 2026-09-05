---
name: implementation-gate
description: >-
  Pre-implementation gate enforcing scope discipline, AC verification, and ATDD
  phase declaration before writing any code. Use before writing any
  implementation code for a new feature, bug fix, or capability — whether
  starting fresh or mid-feature. Auto-triggers when about to write
  implementation code, when about to read code files in response to a ticket,
  spec, or doc request, or when fixing a crash during in-progress feature work.
  Also triggers on: "start coding", "implement this", "write the code", "fix
  this crash", "fix this bug", "before I code". Not needed for
  documentation-only, config-only, or test-only changes with no new logic.
metadata:
  category: process
  version: "2.3"
  status: documented
  validation: untested
  priority: high
  created: "2026-03-26"
  last_updated: "2026-08-20"
  depends_on: []
  conflicts_with: []
  related_skills: [test-functional, lessons-learned]
  references:
    - $DEVSTANDARD/test-framework/sdlc-implementation-principles.md
    - $DEVSTANDARD/test-framework/sdlc-testing-principles.md
---

# Implementation Gate

Operational gate that enforces the universal principles at the moment of implementation. It does not restate those principles; it sequences and checks them. Principle IDs below resolve to `$DEVSTANDARD/test-framework/sdlc-implementation-principles.md` (`In`) and `$DEVSTANDARD/test-framework/sdlc-testing-principles.md` (`Tn`).

**Goal:** The failure point is the transition from "reading the request" to "writing code" — any check that cannot fire at that exact moment is bypassed. Every step targets that transition.

## When to Use

**Explicit:** `/implementation-gate`, "implementation gate", "check before coding"
**Auto-trigger:**
- keywords: [implement, write the code, start coding, fix this bug, fix this crash, before I code, about to implement]
- context: about to write implementation code for any feature, bug fix, or crash repair
- context: about to read code files when the request is a ticket update, spec, or documentation change
**Gate:** Before any implementation code is written; before reading code files for non-implementation requests
**Not needed:** Documentation-only, config-only, or test-only changes with no new logic

## Addresses

Recurring failures this gate exists to prevent (operational evidence, not principles):

- Feature implemented with no tracked issue or AC, justified by "perceived size."
- Crash fix accepted as done when the error was silenced but the in-flight feature's AC test would have failed.
- Implementation code read and written when the request was a ticket update.
- Fix committed before any test ran, burning full verification cycles.

## Procedure

Each step enforces a named principle and adds the gate-specific fail condition that stops work when the principle is unmet.

1. **Scope check** (enforces I9) → restate the request in one sentence → decide whether it requires reading implementation code. | **Fail:** if the request is a ticket update, spec authoring, or documentation change, do not read implementation files; if implementation seems a natural next step, surface it and ask — do not proceed on inference.

2. **Issue gate** (enforces I1, I2) → confirm a tracked issue exists for this work; create one if absent. | **Fail:** if no issue can be identified and the user is unavailable, record the gap and stop.

3. **AC / contract gate** (enforces I4, T4) → confirm AC and the pre-code contract are drafted and frozen → read them → state "done" in one sentence. | **Fail:** if AC are absent or ambiguous, draft candidate AC and review with the user before any code — do not implement on inference.
   - **Proof-of-effectiveness sub-step:** if the AC introduces a new integrity/quality assertion (not a first-pass functional red-phase test), the contract must also state how the assertion will be proven to fail — i.e. that it actually catches the violation it claims to check, not only that it passes. | **Fail:** an assertion with no stated failure-demonstration is not contract-complete; add one before proceeding.

4. **Oracle & phase declaration** (enforces I7, T23) → first declare the **oracle type**, which sets the ordering:
   - **Specifiable oracle** — correct is a precise value/state writable *before* coding (parsed value, row status, contract shape) → **test-first**: proceed red → green → refactor.
   - **Perceptual oracle** — correct is recognized on sight but not cheaply pre-specifiable (most UI/UX, rendered output, layout/feel) → **Slice** (T23): implement a thin instance → human review → freeze the AC → then author the hardening `[TST]` against the frozen contract. State explicitly why an assertion cannot cheaply pre-specify "correct."

   Then declare the current phase (red / green / refactor, or slice / hardening) and comply with its read restriction. The internal unit loop within Green is implementation-track TDD (I8).

   **Ordering is negotiable; coverage-before-merge is not** — whichever path, the durable invariants and every state-modifying entry point (T17) are tested before merge. When implement-first (Slice) is chosen, three guardrails keep that invariant honest: (1) harden the durable invariant, not the volatile surface still under review (T23 durable-invariant rule); (2) a blocking hardening `[TST]` bead exists and the slice is not done until it is green (ADR-0013); (3) the hardening assertion is proven to fail against the frozen contract (Step 3 proof-of-effectiveness). *Diagnostic:* if the test is dramatically harder to write than the implementation, that asymmetry names the regime — immature harness (invest and amortize), perceptual oracle (use review, harden only the invariant), or a churning contract (slice first). | **Fail:** if no oracle/phase can be declared, the work is not ready — return to Step 3.
   *(Lever under test — gts-m65t; pending DevStandard T23 promotion.)*

   - **Evidence-log entry (enforces gts-m65t's promotion AC):** immediately after declaring the oracle type, append one row to `docs/methodology/oracle-ordering-lever.md`'s Evidence log table: `Date` = today; `Project` = this project's name; `Feature / bead` = the issue id from Step 2; `Oracle type` = as just declared; `Outcome / friction` = `pending — declared, ordering not yet followed to close`. This is what makes the declaration durable across sessions instead of evaporating at session end (the gap that left the log empty for 7 weeks after the lever's 2026-07-01 deploy — see `gts-m65t` bead notes). | **Fail:** if Step 4 completes without this row appended, the declaration is not gate-complete — do not proceed to Step 5.
   - **Evidence-log closure (enforces gts-m65t's promotion AC):** at the point this feature's ordering is actually followed to completion — the `[IMP]` close gate (Step 6) for a specifiable/test-first feature, or the hardening `[TST]`'s close for a perceptual/Slice feature — find that feature's row (grep the table for its bead id) and edit its `Outcome / friction` cell in place: replace the `pending` placeholder with what happened (ordering followed cleanly / friction encountered — describe it / oracle partition failed to classify the work — describe why). A perceptual/Slice row must also confirm whether all three guardrails (durable-invariant-only smoke, blocking hardening bead, proven-to-fail assertion) were observed. | **Fail:** if oracle type was declared under this feature's bead but its row still reads `pending` when the feature closes, closure is not gate-complete — update the row before closing the issue.

5. **Test-before-commit** (enforces I5, T5) → before staging, run the narrowest test covering the current AC; in red, confirm the test exists and is listed failing; in green/refactor, it must pass. | **Fail:** if no test exists, write one first — staging is blocked until a test runs; if the runner is unavailable, record the block on the issue before staging.

5.5. **Test-infrastructure compatibility check** — before committing to an implementation approach, confirm it is compatible with the existing test harness: detection/seed format the harness expects, route/contract shape the test fixtures call, sheet/doc structure assumptions, and log tags the harness waits on. | **Fail:** if the approach would change any of these without a corresponding harness update, surface the mismatch and resolve it before writing code — do not let it surface later as a harness false-negative or false-positive.

6. **[IMP] close gate** (enforces I5, T5) → before closing any `[IMP]` issue or merging, run the full regression suite via `pnpm run test:regression` (this project's `H13` entry point — CLAUDE.md Backstop rules), not only the narrowest test for the current AC. | **Fail:** if the suite has pre-existing failures unrelated to this change, do not close or merge autonomously — present the debt state and wait for an explicit decision (CLAUDE.md backstop rule).
   - If Step 4 declared an oracle type for this feature, this is also the evidence-log closure point for a specifiable/test-first feature — see Step 4's closure sub-step.

7. **Crash-fix rule** (enforces I10) — apply only when fixing a crash during in-progress feature work → identify the feature in flight → read its AC before applying any fix → apply the fix → run the feature's AC tests. | **Fail:** "no crash" is not done — "AC tests pass" is done; if AC tests are unavailable, create an issue for AC authoring before closing the fix.

## Success Criteria

- [ ] Request restated in one sentence before any files read
- [ ] Implementation files confirmed necessary for this request type (not a ticket/spec/doc request)
- [ ] Tracked issue exists before implementation begins
- [ ] AC and contract read; "done" stated in one sentence before writing code
- [ ] For new integrity/quality assertions: contract states how the assertion's effectiveness will be proven (failure demonstration), not just that it passes
- [ ] Oracle type declared (specifiable → test-first; perceptual → Slice); for perceptual, why an assertion can't cheaply pre-specify "correct" is stated
- [ ] Evidence-log row appended to `docs/methodology/oracle-ordering-lever.md` at declaration (pending outcome), and that row's outcome updated at close (verify: row no longer reads `pending`)
- [ ] ATDD phase declared explicitly (red/green/refactor, or slice/hardening)
- [ ] In red phase: no implementation files read (verify: read calls target specs and test files only, per I7)
- [ ] Test run completed before staging (verify: test output shown in session)
- [ ] Test-infrastructure compatibility confirmed (detection format, route/contract, sheet structure, log tags) before committing to the approach
- [ ] Full regression suite run via `pnpm run test:regression` (not just narrowest test) before any `[IMP]` close or merge; pre-existing failures surfaced for explicit decision, not bypassed
- [ ] For crash fixes: feature in flight identified; AC read before fix; AC tests pass after fix (verify: test run output shown)

## Examples

### Failure — Scope overrun
**Input:** "Update the ticket description for feature X."
**Expected (with skill):** Step 1 restates the request as a ticket update and stops; no implementation files read.
**Actual (without skill):** Agent read implementation files and implemented the feature.

### Failure — Crash fix accepted without AC validation
**Input:** Fix an unpacking error in a content-generation function.
**Expected (with skill):** Step 7 identifies the in-flight feature, reads its AC, runs the AC test after the fix — which fails, revealing a discarded value.
**Actual (without skill):** Fix silenced the error; accepted as done; AC-test failure found later in review.

### Success — ATDD red phase enforced
**Input:** "Write tests for feature Y."
**Expected:** Step 1 confirms test authoring needs specs not implementation; Step 3 reads AC; Step 4 declares red; research restricted to specs and test conventions; no implementation files read.

## Optional: hook enforcement

The skill works without hooks. For projects with repeated incidents of implementation starting before the gate completes, a hook template provides mechanical enforcement:

- **Template:** `dot-claude/skills/implementation-gate/hooks.json.template`
- **Conventions covered:** Claude Code (`PreToolUse` matcher on `Edit|Write|MultiEdit`; exit code 2 blocks) and Copilot (`.github/hooks/hooks.json`).
- **Required env vars:** `DEVSTANDARD`, `PROJECT_ROOT`, `PLANNING_GATE_CHECK` (project-supplied script: exit 0 pass / 2 block), optional `PLANNING_GATE_ISSUE`.
- **Not CI-bound:** runs locally via the hook runner; no CI service required.

Hooks are OPTIONAL — use them only after repeated gate-bypass incidents; skip otherwise.

## Anti-Patterns

**Pattern:** Perceived-size exemption
**Symptom:** Work deemed "small" or "obvious"; gate skipped; no phase declared; AC unchecked.
**Prevented by:** Steps 2–4 — no size threshold exists (I9); the gate applies to all implementation.

**Pattern:** Crash silenced and closed
**Symptom:** Error suppressed; feature behavior left broken; closed before the in-flight AC test ran.
**Prevented by:** Step 7 (I10) — done is "AC tests pass," not "no crash."

---
_Document generated 2026-06-08; updated 2026-06-18 (gts-mpi9: proof-of-effectiveness sub-step, test-infra compatibility check, full-suite close gate); updated 2026-07-01 (gts-m65t: oracle & phase declaration — lever under test, pending DevStandard T23 promotion); updated 2026-08-20 (gts-m65t: evidence-log entry/closure sub-steps — the declaration step was disconnected from `docs/methodology/oracle-ordering-lever.md`'s Evidence log, leaving it empty 7 weeks after deploy; Step 4 now appends a row at declaration and Step 6 (or the hardening `[TST]`'s close, for Slice) closes it out)._
