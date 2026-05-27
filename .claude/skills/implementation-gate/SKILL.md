---
name: implementation-gate
description: >-
  Pre-implementation gate enforcing scope discipline, AC verification, and TDD
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
  version: "1.2"
  status: documented
  validation: untested
  priority: high
  created: "2026-03-26"
  last_updated: "2026-05-27"
  depends_on: []
  conflicts_with: []
  related_skills: [test-functional, lessons-learned, code-review]
---

# Implementation Gate

Pre-implementation gate enforcing scope discipline, AC verification, and TDD phase declaration before writing any code.

**Goal:** The failure point is the transition from "reading the request" to "writing code" — any check that cannot fire at that exact moment will be bypassed. Every step targets that transition.

## When to Use

**Explicit:** `/implementation-gate`, "implementation gate", "check before coding"
**Auto-trigger:**
- keywords: [implement, write the code, start coding, fix this bug, fix this crash, before I code, about to implement]
- context: about to write implementation code for any feature, bug fix, or crash repair
- context: about to read code files when the request is a ticket update, spec, or documentation change
**Gate:** Before any implementation code is written; before reading code files for non-implementation requests
**Not needed:** Documentation-only, config-only, or test-only changes with no new logic

## Addresses

- Feature implemented without a bd issue or AC — "perceived size" accepted as informal TDD exemption (6 incidents, 2026-03-24/25)
- Crash fix accepted as done when ValueError silenced — feature AC test would have failed (2 incidents, 2026-03-24)
- Implementation code read and written when request was a ticket update (1 incident, 2026-03-25)
- Fix committed twice before any test ran — navigateToPlayback, two full Playwright cycles burned (ii7, 2026-04-27)
- syncAll() stub wired to menu and trigger with no test; mechanism (syncDocument) tested in isolation;
  entry point never exercised; deleted-doc regression caught manually in production (2026-05-27)

## Input

**Type:** Request
**Format:** Statement of what the user asked
**Required:** The request in one sentence
**Optional:** bd issue ID, existing AC
**Minimum:** "User asked for X"

## Procedure

1. **Scope check** → restate the request in one sentence → ask: does this request require reading implementation code? | Fail: if request is a ticket update, spec authoring, or documentation change — do not read implementation files; if implementation seems like a natural next step, surface that to the user and ask — do not proceed on inference

2. **Issue gate** → confirm a bd issue exists for this work → if absent, create one before continuing | Fail: if no issue can be identified and user is unavailable, note the gap and stop

3. **AC gate** → confirm AC are drafted → read them → state "done" in one sentence | Fail: if AC are absent or ambiguous, draft candidate AC and review with user before writing any code — do not implement on inference

4. **TDD phase declaration** → declare current phase explicitly: red / green / refactor

   - **Red:** write tests from specs and AC only; do not read implementation files; research limited to behavioral specs, AC, test conventions, fixture patterns
   - **Green:** write minimum implementation to make red tests pass; may read existing implementation
   - **Refactor:** improve structure without changing behavior; all tests must remain green

   | Fail: if no TDD phase can be declared, the work is not ready — return to Step 3

5. **Entry point coverage check** (red phase only) → list all state-modifying entry points introduced or
   touched by this feature: menu items, time-based triggers, sidebar buttons, onEdit handlers, HTTP
   routes → for each entry point, confirm at least one test scenario in the suite calls it directly as
   the entry point, not only a mechanism it delegates to → if any entry point has no test call-site,
   add a scenario that exercises it before leaving red phase | Fail: do not declare red phase complete
   if any state-modifying entry point lacks a test call-site; a stub function wired to a trigger with
   no test call-site is a broken feature, not an unfinished one — treat it as a missing test, not a
   missing implementation | Note: the test does not need to be standalone or sequential; exercising
   the entry point as part of any scenario satisfies the check

6. **Test-before-commit** → before `git add`, run the narrowest test covering the current AC; red: confirm the test exists and is listed as failing; green/refactor: it must pass | Fail: if no test exists, write one first — `git add` blocked until a test runs; if runner unavailable, record the block in a bd comment before staging

7. **Crash-fix rule** (apply only when fixing a crash during in-progress feature work) → identify which feature is in flight (check bd in_progress issues) → read the feature's AC before applying any fix → apply the fix → run the feature's AC tests | Fail: "no crash" is not done — "AC tests pass" is done; if AC tests unavailable, create a bd issue for AC authoring before closing the fix

## Success Criteria

- [ ] Request restated in one sentence before any files read
- [ ] Implementation files confirmed as necessary for this request type (verify: not a ticket/spec/doc request)
- [ ] bd issue exists before implementation begins
- [ ] AC read; "done" stated in one sentence before writing code
- [ ] TDD phase declared explicitly (red/green/refactor)
- [ ] In red phase: no implementation files read (verify: Explore/Read calls target specs and test files only)
- [ ] In red phase: all state-modifying entry points listed; each has a test call-site (verify: list shown, each entry point named with its test scenario)
- [ ] Test run completed before `git add` (verify: test output shown in session)
- [ ] For crash fixes: feature in flight identified; AC read before fix applied; AC tests pass after fix (verify: test run output shown)

## Examples

### Failure — Scope overrun
**Input:** "Update the ticket description for the framework-version feature"
**Expected (with skill):** Step 1 restates request as ticket update — stops; does not read implementation files
**Actual (without skill):** Agent read discover_repos.py and generate_repo_xls.py, then implemented the feature (2026-03-25)

### Failure — Crash fix accepted without AC validation
**Input:** Fix ValueError: too many values to unpack in generate_unified_content
**Expected (with skill):** Step 7 identifies lessons-learned feature as in-flight, reads its AC, runs TestExcelIncludesLessonsColumn after fix — fails, revealing lessons_map was discarded
**Actual (without skill):** Fix named 4th value _lessons_map; ValueError gone; accepted as done; AC test failure discovered later in code review (2026-03-24)

### Failure — Entry point stub with no test call-site
**Input:** Implement Sync Status column — syncDocument catches openById failures, marks 'Doc Not Found'
**Expected (with skill):** Step 5 lists entry points: syncAll (menu), time-based trigger, syncDocument;
  confirms test_sync_status_doc_not_found calls syncDocument directly but no test calls syncAll;
  requires a test scenario that calls syncAll before red phase is complete
**Actual (without skill):** syncAll remained a stub wired to menu+trigger; no test called it;
  user discovered in production that Sync menu did nothing for deleted docs (2026-05-27)

### Success — TDD red phase enforced
**Input:** "Write tests for the lessons-learned feature (mol-x5ej)"
**Expected:** Step 1 confirms test authoring requires reading specs not implementation; Step 3 reads AC; Step 4 declares red phase; research restricted to TS-1–TS-10 specs and test conventions; no implementation files read
**Actual:** Applied

## Optional: hook enforcement

The implementation-gate skill works without any hook configuration. For projects that want mechanical enforcement of the planning gate before implementation edits proceed, a hook template is provided:

- **Template:** `dot-claude/skills/implementation-gate/hooks.json.template`
- **Conventions covered:** Claude Code (`PreToolUse` matcher on `Edit|Write|MultiEdit`; exit code 2 blocks the action) and Copilot (`.github/hooks/hooks.json`).
- **Required env vars:** `DEVSTANDARD`, `PROJECT_ROOT`, `PLANNING_GATE_CHECK` (project-supplied script that inspects bd notes and/or `config.md` sign-off and exits 0 pass / 2 block), optional `PLANNING_GATE_ISSUE`.
- **Not CI-bound:** the template runs locally via the hook runner; no GitHub Actions/GitLab CI/Jenkins required.

Hooks are OPTIONAL. Use them when the project has had repeated incidents of implementation starting before the planning gate was completed; skip them otherwise.

## Anti-Patterns

**Pattern:** Perceived size exemption
**Symptom:** Agent decides work is "small" or "obvious" and skips the gate; no TDD phase declared; AC not checked
**Prevented by:** Steps 2–4 — no size threshold exists; gate applies to all implementation
**Found:** 2026-03-25 — framework version extraction implemented directly against a single bead with no mol, no AC, no TDD phase declared

**Pattern:** Mechanism tested, entry point skipped
**Symptom:** Test exercises the function a trigger delegates to (e.g. syncDocument) but never the trigger
  function itself (e.g. syncAll); stub wired to menu ships with no test call-site; production failure
  reveals the entry point was never exercised
**Prevented by:** Step 5 — entry point coverage check requires naming each state-modifying entry point
  and confirming a test scenario calls it directly
**Found:** 2026-05-27 — syncAll stub wired to Sync menu and 30-min trigger; syncDocument tested in
  isolation; menu exercised nothing; user caught deleted-doc regression manually
