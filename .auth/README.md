# .auth/ — legacy/fallback location for captured Playwright sessions

Mechanics (identity registry, resolver contract, capture-tool contract) are a
reusable cross-project standard: `/mnt/c/dev/DevStandard/docs/standards/playwright-shared-auth.md`.
This file documents only GActionSheet's own role taxonomy and current state.

Account files now live in a directory **shared across projects**
(`$PLAYWRIGHT_AUTH_DIR`, set in `.envrc`, default `~/.playwright`), named by
the real Google account they hold (e.g. `sdonaldson.json`) — not by the role
that account plays in a given project. `$PLAYWRIGHT_AUTH_DIR/accounts.json`
is the identity registry `auth.setup.js` maintains automatically: which
email each slug maps to, and when it was last captured.

This project assigns accounts to its own roles via `local.settings.json`'s
`"playwrightAccounts"` map — account-role taxonomy and rationale:
`../docs/security-architecture.md` §5.

```json
"playwrightAccounts": {
  "primary": "sdonaldson.json",
  "test.u2": "sanctuary.json"
}
```

`scn.session.resolve_auth_file(role)` (Python) and
`scripts/playwright-auth.js`'s `resolveAuthFile(role)` (Node — used by
`auth.setup.js`, `manage-deployments.js`, `gas-inspect.js`) both read this
map. **This `.auth/` directory is only the fallback** for a role with no
`playwrightAccounts` entry — `.auth/<role>.json` (`.auth/user.json` for
`primary`). Files here are git-ignored; only this README is committed.

Falling back is silent-but-not-quiet: both resolvers print a one-time warning
per role when a `playwrightAccounts` entry is missing, and `tests/conftest.py`
additionally surfaces it through pytest's terminal reporter (bypassing output
capture) so a full green test run can't hide that the shared-auth mapping was
never configured for `primary`.

| Role | Notes |
|------|-------|
| `primary` | Full-access baseline (currently also the dev deployer). Target taxonomy splits this into `nuuts.service` (deployer) + `test.u1` (primary end user). |
| `test.u1` | Primary end user, non-deployer *(target — not yet captured)*. Full access on all team folders, but **not** the deployer account — exercises the add-on's "caller's own access" path rather than deployer privilege. |
| `test.u2` | Restricted end user — single team. Reader on one team folder only (e.g. `testTeamAChild`). Used via `pnpm run probe:test.u2`. |
| `test.u3` | Restricted end user — other team *(not yet captured)*. Reader on a *different* single team than `test.u2` — J-ACCESS-FILTER's `TeamA-only` account, the P1/P2 mirror. |
| `nuuts.service` | Production service/deployer *(future, not yet captured)*. Captured once the `nuuts.service@northlakeuu.org` robot account is provisioned (security-architecture.md §4/§8). |

`user1.json` in this directory, if present, predates this convention and is
stale — safe to delete.

## Capturing a session

```bash
node tests/playwright/auth.setup.js                      # slug auto-derived from the detected email
node tests/playwright/auth.setup.js --account=<slug>      # explicit slug override
```

Sign in as the intended account in the browser window that opens, then press
Enter in the terminal. The script then reads the signed-in email off the
Google account page and, unless you passed `--account`, derives the slug
from it (the part before `@`) — you don't need to know or type the slug in
advance. It records the email and a capture timestamp in
`$PLAYWRIGHT_AUTH_DIR/accounts.json`, and warns if an explicit `--account`
doesn't match the email already on file for that slug (signed into the
wrong account).

If the email can't be auto-detected, it prompts for a slug on the spot
rather than throwing the login away — re-authenticating is the expensive
part, naming the file isn't. If you leave that prompt blank (or aren't at a
terminal), the session is staged instead of lost, with a printed command to
finish naming it: `node tests/playwright/auth.setup.js --apply=<path> --account=<slug>`.

Re-run only when a session expires.

`pnpm run auth:primary`, `auth:test.u1`, `auth:test.u2`, `auth:test.u3`,
`auth:nuuts.service` pass explicit generic role-shaped slugs — use these if
you'd rather the file be named by role than by the auto-detected account, or
prefer a consistent default before deciding on account-specific slugs.
