# OPERATIONS.md — GActionSheet

## Architecture

Single Apps Script project, container-bound to the ActionSheet spreadsheet.
Deployed two ways from the same scriptId:

| Deployment | Purpose | Runs as |
|------------|---------|---------|
| Web App | Proxy endpoint — receives POSTs from the add-on card and writes to the sheet | Deployer (sheet owner) |
| Add-on (test/production) | Docs sidebar UI | Active user |

The add-on card calls the Web App URL via `UrlFetchApp`. Because the Web App
runs as the deployer, it retains write authority to the bound spreadsheet even
when the sidebar user does not have direct sheet access.

## Clasp Project

| Field | Value |
|-------|-------|
| Script ID | `12EKX7dQiO1Wf7rvv94Adgpbh3nac0OetsZMTD_1lme3y2o1KLYdKcTXi` |
| Bound spreadsheet | `10UCsEHPL2RjA1IduUSFDSaA2lpkoCuZY79sIjratH_s` |
| Root dir | `src/` |
| GCP project | shared — see knowledge-base/adr/ |

### Deploying

For normal development and test cycles, use the npm deploy script — it pushes HEAD
**and** updates the versioned WebApp deployment in one step:

```bash
npm run deploy:test   # push + update test WebApp revision
npm run deploy:prod   # push + update prod WebApp revision
```

`npm run push` alone (`clasp push`) updates HEAD but leaves the versioned deployment
stale. The test suite calls the versioned WebApp endpoint, so a push-only will cause
`sync.warn: Non-JSON response` failures until the deployment is also updated.

If clasp reports `Skipping push.` (hash cache) during a deploy, run:

```bash
clasp push --force && npm run deploy:test
```

### Checking deployment status

**Live health check** — verify a running deployment is reachable, on the expected version,
and has correct script properties:

```bash
npm run verify:test   # TEST deployment (full check — health, version, config, token)
npm run verify:dev    # DEV /dev endpoint (requires .auth/user.json from auth.setup.js)
npm run verify        # interactive — pick target
```

Output includes version, WEBAPP_URL registration, TEST_DOC_ID/TEST_SHEET_ID match against
`local.settings.json`, test token validity, and a reminder to run `npm run probe` for
surface-level checks (sidebar, chip hover, menu).

**Deployment history** — every `deploy:test` / `deploy:prod` / `push` commits `Version.js`
with the environment tag and revision timestamp. The full deploy history is in git:

```bash
git log --format="%h %ai %s" -- src/Version.js
```

To see what version is currently live in each environment:

```bash
# What's in the git working tree right now
grep version src/Version.js

# What was at a specific commit
git show <hash>:src/Version.js | grep version
```

The revision timestamp in the version string (e.g. `Rev. Jun 2, 2026 10:22`) is the
moment `deploy:test` stamped the code — effectively the deploy time. GCP Marketplace SDK
publish time is not captured automatically and must be noted manually if needed.

## Deployment Steps (one-time per environment)

### 1. Deploy the Web App

1. Open the Apps Script editor for the automation project.
2. **Deploy > New Deployment** → gear icon → select **Web app**.
3. Configure:
   - **Execute as:** `Me (your-admin-email@org)`
   - **Who has access:** `Anyone within [Your Organization]`
4. Click **Deploy** and complete authorization.
5. Copy the generated **Web App URL**.
6. Go to **Project Settings > Script Properties**, add property `WEBAPP_URL` with that URL.

### 2. Install the Add-on Test Deployment

1. **Deploy > Test deployments** → click **Install** next to the Add-on row.
2. Open any Google Doc — the GActionSheet sidebar should appear.

## First-time Setup (new machine)

1. `clasp login` (or restore `.auth/user.json` to `~/.clasprc.json`)
2. `npm run deploy:test` to verify the project is reachable and update the test deployment.
3. Open the Apps Script editor and run `bootstrap()` from `TestFixtures.js`
   to set script properties (`TEST_DOC_ID`, `TEST_SHEET_ID`, `GAS_LOGGER_FOLDER_ID`).

## POC Verification Checklist

- [ ] `npm run deploy:test` succeeds (push + test WebApp revision updated)
- [ ] Web App deployed; `WEBAPP_URL` set in script properties
- [ ] Add-on test deployment installed
- [ ] **Test 1 (sheet macro):** Refresh ActionSheet → custom menu appears → item executes and writes a row
- [ ] **Test 2 (proxy write):** Open a Google Doc → GActionSheet sidebar → type message → "Test Proxy Write" → notification "Proxy write sent" → row appears in ActionSheet

## Running Tests

```bash
npm run test:smoke   # Playwright smoke test (requires sheet URL configured)
```

GAS test invocation: open the ActionSheet in Sheets, use the **Action Sync**
custom menu. See the `gas-test-invocation` bd memory for selector details.

### AC Coverage Check (T24 Step 3)

After running tests, check AC coverage against the authoritative registry:

```bash
python scripts/check_coverage.py               # Brief report; exit 1 if gaps exist
python scripts/check_coverage.py --verbose     # Show covered, warn-only, and uncovered ACs
```

This diff's JUnit properties (`ac.*` tags emitted by `ScenarioSession.checkpoint()`)
against the AC registry in `scn/contract.AC_REGISTRY`. Uncovered ACs indicate missing
test scenarios and block the build if used in CI. The registry lives in `scn/contract.py`
and is co-located with the contract for drift detection.

## Consistency Verification

Consistency verification ensures that actions are correctly synchronized across the Document, ActionSheet, and Tracker table. There are three classes of verification:

### SERVER — GAS-side authoritative verification

**Path:** `scn.verify_consistency(scope=DOC)` in Python test code; calls GAS `verify_action_rows` + `verify_chip_integrity` routes.

**When to use:** Test journeys at HTTP-phase boundaries and the journey end to validate the full integration through GAS. This is the **only authoritative path** to GAS-computed consistency checks.

**Observes:** Document (parsed via GAS API), ActionSheet rows (scoped to docId), Tracker table (if present), plus GAS-side field validation.

### ARTIFACT — Python-side file parsing

**Path:** `scn.verify(ai, on=DOC|SHEET|TRACKER, ...)` per-surface probes in Python test code; parses downloaded .docx and .xlsx files.

**When to use:** Focused single-surface assertions or when testing cross-surface divergence without triggering expensive GAS round-trips. Useful for unit-level verification of document/sheet structure.

**Observes:** Document (via python-docx), ActionSheet (via openpyxl), Tracker table (via docx parsing). **Does not** run GAS-side verification routes.

### smoke/probe — UI surface only

**Path:** Playwright tests in JavaScript (`tests/playwright/*.test.js`).

**When to use:** Fast gate smoke tests and surface-level UI regression checks. Never assert artifact or consistency state in smoke tests — use server/artifact verification for that.

**Observes:** Sidebar card, preview card, and DOM state only. UI is live-only and not durable.

### Single-source discipline

There is **only one** path to GAS-side consistency verification: `scn.verify_consistency()`. Competing paths (e.g., a separate Python wrapper around GAS routes) are explicitly prohibited. This enforces a single source of truth for end-to-end system state.
