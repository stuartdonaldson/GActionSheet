# LL: Direct clasp push used instead of npm deploy script for test deployment

Date: 2026-05-24
Domain: deployment | process

## Observation
During green-phase implementation of GTaskSheet-mol-dyu (UC-B bidirectional sync),
Claude executed `clasp push` directly via Bash to deploy GAS source code.
The correct path is `npm run deploy:test` (orchestrates `update-revision.js` +
`manage-deployments.js --deploy-test`), which both pushes HEAD and updates the
versioned test deployment in one step.
The stale deployment caused the test WebApp to return `'ok'` instead of
`{ upserted, updated, sheetWins }`, producing a `sync.warn: Non-JSON response`
error and a first-run timeout.
Claude recognised the symptom mid-session and noted "after each clasp push, run
`clasp deploy -i ...`" — but identified the wrong corrective action and did not
capture the root cause (wrong entry point used).
Caught by: user at session end reviewing the session note.

## Why Chain

Branch A — Wrong entry point used for deployment
  Why 1 — Claude invoked `clasp push` directly, skipping the npm script wrapper
  Why 2 — OPERATIONS.md §Pushing documents `npm run push` as the push method
           (which is just `clasp push`) and documents Web App deployment as a
           separate one-time manual step; it does not surface `npm run deploy:test`
           as the mandatory path for test-cycle deployments
  Why 3 — `deploy:test` exists in package.json but is never named in OPERATIONS.md
           or CLAUDE.md as the authoritative test-deployment command; its relationship
           to `npm run push` is implicit, not stated
  Root cause A: No authoritative source (OPERATIONS.md, CLAUDE.md) identifies
  `npm run deploy:test` as the required command for deploying during test cycles,
  nor prohibits direct `clasp push`. The toolchain exists but is undocumented as
  the mandatory path.

Branch B — Process deviation not captured as lessons-learned mid-session
  Why 1 — Session ended with a workaround note ("run clasp deploy -i after push")
           rather than a LL CAPTURE
  Why 2 — The LL CAPTURE trigger did not fire: using a direct tool when an npm
           script should have been used is not listed as a trigger condition in
           the lessons-learned skill
  Why 3 — Session-close protocol checks that code is pushed and issues are closed;
           it has no step to audit whether the deployment method was correct
  Root cause B: The lessons-learned skill's auto-trigger list does not include
  "task required rework because wrong toolchain entry point was used"; process
  deviations of this class pass through session-close unchecked.

## Initial Candidates

Branch A:
  b: CLAUDE.md (project) — add rule: "For GAS deployment, use `npm run deploy:test`
     (test) or `npm run deploy:prod` (prod). Do not invoke `clasp push` directly."
  a+c: OPERATIONS.md §Pushing — rename/reframe section as §Deploying; replace
     `npm run push` example with `npm run deploy:test` as the standard test-cycle
     command; demote `npm run push` to "only if deploying separately"

Branch B:
  c: lessons-learned skill — add trigger: "task required rework or debugging because
     the wrong toolchain entry point was used (direct CLI instead of npm/make/project
     script)"

## Resolution (2026-06-12)

Branch A — already applied. Project `docs/OPERATIONS.md` §Deploying now documents
`npm run deploy:test` / `npm run deploy:prod` as the required commands in a table, and
states explicitly: "Running `clasp push` or `npm run push` alone leaves the versioned Web
App deployment stale — the test suite will call the old revision and produce
`sync.warn: Non-JSON response` failures." This matches candidate a+c verbatim. Selected
lever: a+c (OPERATIONS.md, already implemented).

Branch B — no separate edit. The lessons-learned skill's existing general trigger "A task
requires rework after code was written" already covers this class — this very LL was
captured under that trigger, just later than mid-session. A more specific trigger phrase
would not catch anything the general one doesn't; not adding it.

Verify: a developer/agent reading OPERATIONS.md §Deploying before deploying would now use
`npm run deploy:test`, avoiding the stale-deployment `sync.warn: Non-JSON response` failure
that occurred in this incident.
