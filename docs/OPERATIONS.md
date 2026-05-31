# OPERATIONS — GActionSheet

## Deployment Model

GActionSheet is a **single GAS project** (`scriptId: 12EKX7dQiO1Wf7rvv94Adgpbh3nac0OetsZMTD_1lme3y2o1KLYdKcTXi`), container-bound to the ActionSheet spreadsheet. It is deployed simultaneously in two modes:

| Mode | Purpose |
|------|---------|
| **Workspace Add-on** | Homepage card in active Google Docs — Sync now, VerifySync, Insert / refresh tracker |
| **Web App** | `doPost` proxy endpoint for sheet writes (runs as deployer identity) |

The same script also hosts the **automation feature set** (timed sweep trigger, `onEdit` timestamp stamper, archive job) activated by installable triggers on the ActionSheet container.

No server infrastructure. No separate projects. One push updates both deployment modes.

---

## Prerequisites

Before the first deployment, complete these one-time setup steps:

### GCP Project
- The GCP project linked to the script must have the **Google Docs REST API** enabled.
- Required OAuth scopes (declared in `src/appsscript.json`):
  - `https://www.googleapis.com/auth/documents` — read/write docs
  - `https://www.googleapis.com/auth/script.external_request` — call the Docs REST API via `UrlFetchApp`
  - `https://www.googleapis.com/auth/spreadsheets` — read/write the ActionSheet

### Web App Access
- **Access:** "Anyone" (not "Anyone within org") — org SSO enforces auth on `UrlFetchApp` regardless of headers when restricted to org.
- **Execute as:** "USER_DEPLOYING" — required for sheet-write authority.

### `urlFetchWhitelist`
Declared in `src/appsscript.json`. Covers northlakeuu.org URL format variants:
```json
"urlFetchWhitelist": [
  "https://script.google.com/a/macros/northlakeuu.org/s/",
  "https://script.google.com/a/northlakeuu.org/macros/s/",
  "https://script.google.com/macros/s/"
]
```
Omitting this causes a hard runtime error on the first `UrlFetchApp.fetch` call.

---

## Deployment

Use the npm scripts — never invoke `clasp` directly.

| Goal | Command |
|------|---------|
| Deploy for test cycle | `npm run deploy:test` |
| Deploy to production | `npm run deploy:prod` |
| Push source only (no new version) | `npm run push` |

**`npm run deploy:test`** runs `update-revision.js` (stamps `src/Version.js`) then `manage-deployments.js --deploy-prod` (pushes source and repoints the TEST Web App deployment). Running `clasp push` or `npm run push` alone leaves the versioned Web App deployment stale — the test suite will call the old revision and produce `sync.warn: Non-JSON response` failures.

**Deployment IDs** are maintained via `clasp deploy -i <id>` so Web App URLs never change across pushes. IDs are stored in `.deploy-metadata.json`.

### Static Assets (GitHub Pages)
Logo and other static assets are served from GitHub Pages:
1. GitHub repo → Settings → Pages
2. Source: Deploy from a branch; Branch: `master`; Folder: `/`
3. Asset URL pattern: `https://stuartdonaldson.github.io/GActionSheet/assets/<filename>`

The `.nojekyll` file at the repo root suppresses Jekyll processing so PNG files are served without path rewriting.

---

## First-Time Configuration

### Script Properties
Set via Apps Script editor → Project Settings → Script Properties, or programmatically by `initializeTriggers`:

| Property | Required | Set by | Description |
|----------|----------|--------|-------------|
| `WEBAPP_SECRET` | Yes | Manual | Shared secret for authenticating `doPost` requests from the add-on |
| `WEBAPP_URL` | Auto | `doGet` | Normalized Web App URL; set automatically on first Web App visit |
| `DOC_FOLDER_ID` | Yes | Auto-set on first `initializeTriggers` | Drive folder ID that roots document discovery for the sweep |
| `SYNC_IN_PROGRESS` | Internal | Sync / Sweep | Guard flag during programmatic sheet writes — do not set manually |
| `GAS_LOGGER_FOLDER_ID` | Test only | Manual | Drive folder for GasLogger output during test cycles |

### Initialize Triggers
After the first push, run `initializeTriggers` once to install the time-based sweep trigger and the `onEdit` timestamp stamper:

```
Apps Script editor → Run → initializeTriggers
```

Confirm success: the `Action Sync` menu appears in the ActionSheet and the Executions log shows the next timed run scheduled.

`initializeTriggers` is idempotent — calling it again does not create duplicate triggers.

---

## Using the Add-on

The homepage card opens when the user activates the add-on in a Google Doc. It shows the doc's current sync state and provides action buttons.

| Button | Behavior |
|--------|---------|
| **Sync now** | Scans the active doc, creates/updates named-range anchors, reconciles ActionSheet rows for this doc in one round using `Last Modified` precedence |
| **VerifySync** | Read-only scan — compares floating actions, in-doc tracker table (when present), and ActionSheet rows; reports mismatches in the verification card without writing anything |
| **Insert tracker** | Inserts or refreshes the in-doc tracker table at its anchor; visible only when the active doc has no tracker yet |

When a tracker table already exists, **Insert tracker** is replaced with the message "Tracker already present in this document."

Opening the add-on in a blank doc shows the card with a **Sync now** button and the message "No detected actions in this document."

---

## Automation

The automation feature set runs on the ActionSheet container and requires no user interaction after initialization.

| Feature | Cadence | Effect |
|---------|---------|--------|
| Timed sweep | Every 30 minutes | Groups ActionSheet rows by document URL; opens each doc; reconciles just as **Sync now** would |
| `onEdit` timestamp stamper | On every ActionSheet edit | Stamps `Last Modified` on the edited row; skipped when `SYNC_IN_PROGRESS` is set |
| Archive job | On demand or as part of sweep | Moves rows with `Status = Closed` and `Last Modified > 30 days` to the archive sheet |

**Re-initialize triggers** after a script re-creation:
```
Apps Script editor → Run → initializeTriggers
```

---

## Monitoring

**Log location:** Apps Script editor → Executions (left sidebar). Each sync run logs `sync.start`, `sync.complete`, documents processed, rows created/updated, and any errors.

**Health indicators:**
- No ERROR entries in the execution log = healthy
- `Action Sync` menu present in the ActionSheet = triggers initialized
- Archive sheet tab exists = archiving has run at least once
- `WEBAPP_URL` script property is set = Web App has been visited at least once

---

## Failure Modes

| Failure | Symptom | Recovery |
|---------|---------|---------|
| `WEBAPP_SECRET` not set | `doPost` returns "unauthorized"; Sync now shows an error notification | Set the `WEBAPP_SECRET` script property in the Apps Script editor |
| `WEBAPP_URL` not set | UrlFetchApp call fails; Sync now shows an error notification | Visit the Web App URL once in a browser tab to trigger `doGet` auto-registration |
| Docs REST API not enabled | `batchUpdate` fails with "API not enabled"; Sync now shows an error | Enable Google Docs REST API in the GCP project linked to the script |
| `urlFetchWhitelist` missing or wrong | Hard runtime error on first `UrlFetchApp.fetch` | Verify `src/appsscript.json` matches the three-entry pattern above; redeploy |
| `DOC_FOLDER_ID` not set | Sweep logs "DOC_FOLDER_ID not set, defaulting to spreadsheet parent folder" | Override via script property if the default parent folder is wrong |
| GAS execution timeout (> 6 min) | Execution log shows "Exceeded maximum execution time" | Reduce folder scope via `DOC_FOLDER_ID`; or run **Sync now** manually on smaller sets |
| Named range lost or deleted | Orphaned ActionSheet row — scanner can't re-anchor; surfaced in sidebar | If the action text and assignee still match a paragraph, Sync will re-anchor automatically; otherwise resolve in the ActionSheet manually |
| Doc inaccessible during sweep | Sweep skips that doc with a logged error | Grant the deploying user edit access to the document |
| Permission denied writing the ActionSheet | `doPost` returns an error; Sync now notification | Verify the deploying user has edit access to the ActionSheet |
| Duplicate `Last Modified` on both sides | Tie — ActionSheet row wins | Expected behavior; no recovery needed |

---

## Running Tests

The `scn/` package provides the scenario harness (`ai`, `engine`, `session`, `surfaces`, `ui`, `contract` modules). Architecture: `docs/atdd/scenario-harness-design.md`. Strategy: `docs/atdd/atdd-lifecycle.md`.

```bash
# Always use -x (fail-fast): stop after the first test that fails.
/mnt/c/dev/venvs/uv1/bin/python -m pytest tests/ -x -v

# Parser unit tests only (fast, no GAS/network):
/mnt/c/dev/venvs/uv1/bin/python -m pytest tests/test_floating_action_parser.py -x -v

# UC-A acceptance tests (requires live GAS — npm run deploy:test first):
/mnt/c/dev/venvs/uv1/bin/python -m pytest tests/test_uc_a.py -x -v

# §16.10 canonical ATDD journey — Acts 1–3 (requires live GAS — npm run deploy:test first):
/mnt/c/dev/venvs/uv1/bin/python -m pytest tests/test_journey_acts_1_3.py -x -v

# §16.10 canonical ATDD journey — full Acts 1–5:
# Acts 4–5 additionally require the add-on test deployment installed in the test account:
#   Apps Script editor → Deploy → Test deployments → Install as Add-on
/mnt/c/dev/venvs/uv1/bin/python -m pytest tests/test_journey.py -x -v
```

Each UC scenario test has significant setup/teardown cost (GAS invocation, up to 300 s). A root-cause failure in an early scenario cascades to all later ones — running to completion wastes time and obscures the real defect. Fix the first failure before proceeding.

### Fixture Invocation

All UC tests use **HTTP fixture invocation** — no browser required for setup. The Python test suite POSTs directly to the Web App `run_fixture` route using the `testToken` from `local.settings.json`.

**Prerequisites for running tests:**
1. `npm run deploy:test` — pushes source, stamps the revision, repoints the TEST Web App deployment, writes `testToken` and `testTokenExpiresAt` to `local.settings.json`.
2. `local.settings.json` must contain `testSheetId`, `testDocId`, `testToken`, and `webappTestUrl`.

**Token expiry:** `testTokenExpiresAt` in `local.settings.json` records the expiry. If the token expires mid-session, re-run `npm run deploy:test` to rotate it.

Playwright is used only for **UI-level tests** (homepage card rendering, menu presence assertions). It is not used for GAS fixture setup.

### UC-A Tests
**Prerequisites:** `npm run deploy:test` (pushes `src/`, stamps the revision, repoints the TEST deployment).

The `uc_a_clear` fixture sets up the test doc automatically:
1. Clears the ActionSheet and removes all named ranges from the test doc.
2. Inserts a chip-led bullet list item via the Docs REST API (`insertPerson` + `createParagraphBullets`).
3. Appends an email-led bullet list item via a second REST API call.

**Tests:**
- `test_uc_a_ac1_multi_format_detection` — one Sync; verifies chip-led and email-led items both appear in the ActionSheet with correct email, name, action text, and status.
- `test_uc_a_ac2_idempotent_second_sync` — second Sync; verifies no duplicate rows, named range IDs unchanged, sheet rows and doc floating actions identical.

---

## Recovery Procedures

### Sync wrote stale values to the sheet
1. Identify the affected row using the `Date Modified` column.
2. Edit the correct field values directly in the sheet.
3. The `onEdit` trigger stamps `Last Modified` to now.
4. On the next sync, the sheet row's newer timestamp will win and propagate to the document.

### Triggers missing after script re-creation
1. Open the ActionSheet.
2. Open Apps Script editor.
3. Run `initializeTriggers` manually.
4. Confirm `Action Sync` menu reappears and the Executions log shows the next timed run scheduled.

### Web App URL changed after redeployment
Visit the new Web App URL once in a browser tab — `doGet` auto-normalizes and stores the URL in `WEBAPP_URL`. No manual copy-paste required.

### testToken expired (tests fail with "test-token-expired")
Run `npm run deploy:test`. The deployment script generates a fresh UUID, POSTs it to the Web App, stores it in script properties, and writes the new token and expiry to `local.settings.json`.
