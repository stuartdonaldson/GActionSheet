# .auth/ — captured Playwright sessions (git-ignored)

This directory holds Playwright `storageState` JSON files (raw Google session
cookies). The files themselves are git-ignored; only this README is committed.

Account-role taxonomy and rationale: `../docs/security-architecture.md` §5.

| File | Account role | Notes |
|------|---------------|-------|
| `user.json` | Primary / dev deployer | Default `storageState` for the whole suite. Currently the same human account as the deployer; the target taxonomy splits this into `nuuts.service` (deployer) + `test.u1` (primary end user). |
| `test.u1.json` | Primary end user, non-deployer *(target — not yet captured)* | Full access on all team folders, but **not** the deployer account — exercises the add-on's "caller's own access" path rather than deployer privilege. |
| `test.u2.json` | Restricted end user — single team | Reader on one team folder only (e.g. `testTeamAChild`). Used via `PROBE_AUTH_STATE=.auth/test.u2.json` / `npm run probe:test.u2`. |
| `test.u3.json` | Restricted end user — other team *(not yet captured)* | Reader on a *different* single team than `test.u2` — J-ACCESS-FILTER's `TeamA-only` account, the P1/P2 mirror. |
| `nuuts.service.json` | Production service/deployer *(future, not yet captured)* | Captured once the `nuuts.service@northlakeuu.org` robot account is provisioned (security-architecture.md §4/§8). |
| `user1.json` | **Stale** | Predates this naming convention; not referenced by any script. Safe to delete after confirming no local workflow depends on it. |

## Capturing a session

```bash
node tests/playwright/auth.setup.js                          # → user.json (default)
node tests/playwright/auth.setup.js --account=<name>          # → <name>.json
```

or via npm: `npm run auth:test.u1`, `auth:test.u2`, `auth:test.u3`, `auth:nuuts.service`.

Sign in as the intended account in the browser window that opens, then press
Enter in the terminal to save the session. Re-run only when a session expires.
