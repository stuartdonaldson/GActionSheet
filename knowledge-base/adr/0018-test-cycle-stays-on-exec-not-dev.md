# ADR-0018: Automated test cycle stays on versioned `/exec`, not `/dev` (HEAD)

Status: Accepted
Date: 2026-06-18

## Context

`GTaskSheet-egl9` asked whether the automated test cycle (`npm run deploy:test` +
`pytest`/Playwright suite) should switch from the versioned `/exec` Web App
deployment to the unversioned `/dev` (HEAD) URL, since `/dev` only requires
`clasp push` — no `manage-deployments.js --deploy-test` repoint/version-bump
step. The motivating upside: every test iteration that just changes GAS code
would shave the deploy step down to a plain push.

A `/dev` (HEAD) push path already exists and is used today: `npm run push`
(`manage-deployments.js --deploy-dev`) stamps `src/Version.js`, runs
`clasp push -f`, and warn-only-verifies the `/dev` URL using Playwright cookie
auth loaded from `.auth/user.json` (`webappDevUrl` in `local.settings.json`).
The Python harness (`scn/session.py::_load_auth_cookie_header`) already loads
the same cookie file unconditionally and falls through to an unauthenticated
request if it's absent — so the *harness* could already talk to `/dev` with no
new auth plumbing.

Two properties of Apps Script Web Apps are decisive here:

1. **`/dev` always executes as the accessing user**, regardless of the
   manifest's `executeAs` setting. `src/appsscript.json` sets
   `"executeAs": "USER_DEPLOYING"` (`docs/OPERATIONS.md §Web App Access` —
   "required for sheet-write authority"). `/exec` honors that setting; `/dev`
   does not.
2. **`/dev` requires editor access** to the script (cookie-authenticated),
   while the TEST `/exec` deployment is `access: ANYONE_ANONYMOUS` — the
   harness's unauthenticated health check and the `WEBAPP_SECRET`-gated
   production routes rely on that being true.

## Decision

Keep the automated test cycle (`npm run deploy:test`, the full `pytest`/
Playwright suite) on the versioned `/exec` TEST deployment. Do not switch its
primary HTTP calls to the `/dev` URL.

The existing `/dev` (HEAD) push path (`npm run push`, `npm run verify:dev`)
remains the right tool for fast exploratory iteration (e.g. checking a log
line, eyeballing a sidebar render) — that need is already met and is not
reopened by this decision.

## Rationale

- **Execution-identity correctness, not just convenience.** Several test
  paths specifically assert deployer-privileged behavior: cross-document
  forwarding (`forward_action_rows`, UC-E), team-scoped reads gated by
  `assertTeamAccess`, and the planned `GTaskSheet-zai6` non-deployer
  Drive-sharing fixture (testing that a *non-deployer* test account does
  **not** get deployer-level Drive access). Running these against `/dev`
  would silently execute as the test account instead of the deployer,
  changing — not just slowing — what the test actually proves. A test suite
  whose execution identity differs from production's is not equivalent
  coverage; it is a different system under test.
- **`/exec`'s unauthenticated health check and `ANYONE_ANONYMOUS` access are
  load-bearing for harness simplicity.** Switching wholesale to `/dev` would
  require valid, non-expired Playwright cookies (`.auth/user.json`) for every
  one of the suite's HTTP calls, not just the few that already opt into
  cookie auth — turning an auth-state refresh into a hard dependency of the
  entire regression suite, not an optional improvement.
- **The actual pain point (redeploy ceremony during GAS-code iteration) is
  already addressed** by `npm run push` for manual/exploratory cycles. The
  remaining cost — `manage-deployments.js --deploy-test`'s repoint step —
  applies only to the automated suite's run, which is run far less
  frequently than ad-hoc manual pushes during active development.

## Consequences

- No change to `docs/OPERATIONS.md §Deployment` or `manage-deployments.js`.
- `GTaskSheet-egl9` closes as "evaluated, no change" rather than as
  implementation work.
- If a future change makes deployer-identity-dependent behavior obsolete
  (e.g. `USER_DEPLOYING` is dropped from the manifest), this ADR's premise
  changes and the question should be reopened — not assumed permanently
  closed.
