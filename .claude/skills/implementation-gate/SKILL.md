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
  version: "2.0"
  status: documented
  validation: untested
  priority: high
  created: "2026-03-26"
  last_updated: "2026-06-08"
  depends_on: []
  conflicts_with: []
  related_skills: [test-functional, lessons-learned]
  references:
    - $DEVSTANDARD/knowledge-base/methodology/testing/bdd/sdlc-implementation-principles.md
    - $DEVSTANDARD/knowledge-base/methodology/testing/bdd/sdlc-testing-principles.md
---

# Implementation Gate

Operational gate that enforces the universal principles at the moment of implementation. It does not restate those principles; it sequences and checks them. Principle IDs below resolve to `$DEVSTANDARD/knowledge-base/methodology/testing/bdd/sdlc-implementation-principles.md` (`In`) and `.../bdd/sdlc-testing-principles.md` (`Tn`).

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

4. **ATDD phase declaration** (enforces I7) → declare the current phase explicitly: red / green / refactor, and comply with that phase's read restriction. The internal unit loop within Green is implementation-track TDD (I8). | **Fail:** if no phase can be declared, the work is not ready — return to Step 3.

5. **Test-before-commit** (enforces I5, T5) → before staging, run the narrowest test covering the current AC; in red, confirm the test exists and is listed failing; in green/refactor, it must pass. | **Fail:** if no test exists, write one first — staging is blocked until a test runs; if the runner is unavailable, record the block on the issue before staging.

6. **Crash-fix rule** (enforces I10) — apply only when fixing a crash during in-progress feature work → identify the feature in flight → read its AC before applying any fix → apply the fix → run the feature's AC tests. | **Fail:** "no crash" is not done — "AC tests pass" is done; if AC tests are unavailable, create an issue for AC authoring before closing the fix.

## Success Criteria

- [ ] Request restated in one sentence before any files read
- [ ] Implementation files confirmed necessary for this request type (not a ticket/spec/doc request)
- [ ] Tracked issue exists before implementation begins
- [ ] AC and contract read; "done" stated in one sentence before writing code
- [ ] ATDD phase declared explicitly (red/green/refactor)
- [ ] In red phase: no implementation files read (verify: read calls target specs and test files only, per I7)
- [ ] Test run completed before staging (verify: test output shown in session)
- [ ] For crash fixes: feature in flight identified; AC read before fix; AC tests pass after fix (verify: test run output shown)

## Examples

### Failure — Scope overrun
**Input:** "Update the ticket description for feature X."
**Expected (with skill):** Step 1 restates the request as a ticket update and stops; no implementation files read.
**Actual (without skill):** Agent read implementation files and implemented the feature.

### Failure — Crash fix accepted without AC validation
**Input:** Fix an unpacking error in a content-generation function.
**Expected (with skill):** Step 6 identifies the in-flight feature, reads its AC, runs the AC test after the fix — which fails, revealing a discarded value.
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
**Prevented by:** Step 6 (I10) — done is "AC tests pass," not "no crash."

---
_Document generated 2026-06-08._
