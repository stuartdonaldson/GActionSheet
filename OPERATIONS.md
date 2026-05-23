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

### Pushing

```bash
npm run push       # clasp push from project root (rootDir: src/)
```

If clasp reports `Skipping push.` (hash cache), use:

```bash
clasp push --force
```

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
2. `npm run push` to verify the project is reachable.
3. Open the Apps Script editor and run `bootstrap()` from `TestFixtures.js`
   to set script properties (`TEST_DOC_ID`, `TEST_SHEET_ID`, `GAS_LOGGER_FOLDER_ID`).

## POC Verification Checklist

- [ ] `npm run push` succeeds
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
