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
| No parent folder found for document (orphan doc) | `teamScope` not assigned; `Team Id` column blank | Expected; no recovery needed unless team tracking is required |
| Document folder has no ancestor in TeamData | `teamScope` not assigned; re-evaluated on next sync | Add the folder or an ancestor to TeamData |
| TeamData tab missing or malformed | Auto-assignment skipped; sync completes without team scope | Restore or recreate the TeamData tab |
| Team ID in document/DocData has no matching TeamData row | Team name cannot be resolved for UI/reporting | Add or restore TeamData row for that Team ID |
| DocData row missing for known document | Sync cannot reconcile DocWins fields | Row is recreated on next sync keyed by `FileId` |
| `SyncStatus='UpdateDoc'` with blank Team Id | `teamScope` cleared to blank and `SyncStatus` cleared (logs `sync.teamScope.override-blank`) — DocData still wins | Set `DocData.Team Id` to the desired team and `SyncStatus='UpdateDoc'` again to assign a team |

---

## Running Tests

The `scn/` package provides the scenario harness (`ai`, `engine`, `session`, `surfaces`, `ui`, `contract` modules). Architecture: `docs/atdd/scenario-harness-design.md`. Strategy: `docs/atdd/atdd-lifecycle.md`.

### Test Accounts

Most tests run as a single primary account. The access-filter journey (`J-ACCESS-FILTER`,
used by the Import and Notify features) additionally requires a **second, restricted**
account so the read-denied path is genuinely exercised rather than simulated.

| Account | Auth artifact | Role | Minimum Drive permissions |
|---------|---------------|------|---------------------------|
| Primary | `.auth/user.json` | Full-access baseline | Reader (or owner) on **all** team folders registered in `TeamData` |
| Restricted | `.auth/user2.json` | Least-privilege subset | Reader on a **strict subset** of team folders only — must have **no** access to at least one team folder the primary can read |

The restricted account is the same second Google account used by the Probe tests
(`npm run probe:user2`). Setup:

1. Capture its storage state: `node tests/playwright/auth.setup.js --output .auth/user2.json`
   (sign in as the restricted account when prompted).
2. In Drive, share `testTeamAChild`'s folder with the restricted account as **Reader**.
   Do **not** share `testTeamA` — that asymmetry is what produces the deny path.
3. Seed one source document with ≥1 team-scoped action in each of `testTeamA` and
   `testTeamAChild` (the access-filter fixture; idempotent check-exists-or-create).

The harness selects the account per run via `PROBE_AUTH_STATE` (defaults to
`.auth/user.json`). Tests that assert the restricted view set `PROBE_AUTH_STATE=.auth/user2.json`.

> This is a **shared test asset** for EPIC-D (Import) and EPIC-E (Notify). The two-account
> fixture matrix and the journey it backs are specified in
> `knowledge-base/staging/j-access-filter-journey.md`.

### Test Patterns

**Python-drives-Playwright pattern.** Scenarios exercise two kinds of entry points:
1. **HTTP fixture shortcuts** (`scn.sync()`, `scn.set_status(ai, status)`, `scn.insert_tracker()`, `scn.delete(ai)`) — fast, synchronous, no browser required. Use for testing the HTTP integration path and internal consistency.
2. **UI sidebar acts** (`scn.ui.sidebar_sync()`, `scn.ui.sidebar_set_status(target, status)`, `scn.ui.insert_tracker_button()`, `scn.ui.sidebar_delete(target)`) — exercise real user entry points through Playwright. Use to verify the UI integration and fire the true add-on code path.

**Cost rule.** Reserve Playwright for surfaces only the UI can show, and for exercising a real UI entry point as the call-site. Everything that does not require the browser stays on the HTTP fixture path (far cheaper). The browser cold start is amortized across all UI acts of one journey — one launch, many acts. During the Playwright phase prefer TARGETED single-surface expectations (verify(on=UI, within=) drained by checkpoint(STEP, on=UI), or a cheap verify(on=DOC) probe) and reserve INTEGRITY for HTTP-phase boundaries and the journey end. This is the explicit answer to "Playwright is expensive to spin up": amortize the one cold start, and keep non-UI acts off the browser entirely.

**One-browser-per-journey fixture.** All UI sidebar acts within a journey share a single module-scoped browser instance, launched once at the journey start and torn down at the end. This pattern amortizes the Chromium cold-start cost across multiple acts. The canonical fixture is `browser_page` in `tests/test_journey.py` (scope="module"), with `.auth/user.json` storage state for authentication. Non-UI acts remain entirely on the HTTP/fixture path and do not touch the browser.

### Running the Tests

```bash
# Always use -x (fail-fast): stop after the first test that fails.
/mnt/c/dev/venvs/uv1/bin/python -m pytest tests/ -x -v

# Parser unit tests only (fast, no GAS/network):
/mnt/c/dev/venvs/uv1/bin/python -m pytest tests/test_floating_action_parser.py -x -v

# UC-A acceptance tests (requires live GAS — npm run deploy:test first):
/mnt/c/dev/venvs/uv1/bin/python -m pytest tests/test_uc_a.py -x -v

# §16.10 canonical ATDD journey — Acts 1–3 (requires live GAS — npm run deploy:test first):
/mnt/c/dev/venvs/uv1/bin/python -m pytest tests/test_journey_acts_1_3.py -x -v

# §16.10 canonical ATDD journey — full Acts 1–5 (also the primary browser smoke test):
# Acts 3/3b/4/5 additionally require the add-on test deployment installed in the test account:
#   Apps Script editor → Deploy → Test deployments → Install as Add-on
/mnt/c/dev/venvs/uv1/bin/python -m pytest tests/test_journey.py -x -v
```

**Add-on install/version pre-flight (Act 0).** `test_journey.py` exercises the
Workspace Add-on homepage card (Sync now, Insert tracker) and the `@`-menu
editor trigger — these only work once the add-on test deployment is installed
in the test Google account (one-time setup, see above) *and* is serving the
revision just pushed by `npm run deploy:test`. Before Act 1, the journey opens
the sidebar and reads its `BUILD_INFO.version` footer (`scn.ui.read_version`),
comparing it against `src/Version.js` (`expected_version` fixture,
`tests/helpers/version.py`):
- Sidebar doesn't load within 15s — the test fails immediately, naming the
  one-time install step above.
- Sidebar loads but shows a different version string — the test fails
  immediately, identifying a stale add-on install (reinstall the test
  deployment).

Either way Acts 3/3b/4/5 never run silently degraded against a missing or
stale add-on — the failure surfaces at Act 0, before any journey state is
created.

Each UC scenario test has significant setup/teardown cost (GAS invocation, up to 300 s). A root-cause failure in an early scenario cascades to all later ones — running to completion wastes time and obscures the real defect. Fix the first failure before proceeding.

### Fixture Invocation

All UC tests use **HTTP fixture invocation** — no browser required for setup. The Python test suite POSTs directly to the Web App `run_fixture` route using the `testToken` from `local.settings.json`.

**Prerequisites for running tests:**
1. `npm run deploy:test` — pushes source, stamps the revision, repoints the TEST Web App deployment, writes `testToken` and `testTokenExpiresAt` to `local.settings.json`.
2. `local.settings.json` must contain `testSheetId`, `testDocId`, `webappSecret`, and `testToken`.

**Token expiry:** `testTokenExpiresAt` in `local.settings.json` records the expiry. If the token expires mid-session, re-run `npm run deploy:test` to rotate it.

> **`webappTestUrl` is auto-managed — do not set it manually.** `deploy:test` derives the TEST Web App URL from the `TEST-WEB-APP` deployment ID returned by `clasp deployments` and always overwrites `webappTestUrl` in `local.settings.json` with the authoritative value. A manually-set URL cannot become stale because it is overwritten on every successful deploy.

Playwright is used only for **UI-level tests** (homepage card rendering, menu presence assertions). It is not used for GAS fixture setup.

### Test observability

Every scenario run writes a per-step trace to `test-results/runs/<node>_<utc>.trace.{log,jsonl}` — a human-readable `.log` and a structured `.jsonl`, written unconditionally. Open the `.log` after a run to see what each step did and how long it took.

- **`SCN_TRACE=1`** — additionally streams the per-step trace live to the console as the run progresses. Use it to watch a long run and see which step it is currently stuck on. Each line shows the phase (`ACT` / `QUERY` / `UIACT` / `CHECK` / `CHECKPOINT` / `MONITOR` / `HTTP`), elapsed timestamp, and duration.
- **`SCN_FAILFAST`** — fail-fast GAS-error monitoring is ON by default: a `*.error` GAS log entry (or an unexpected/non-JSON HTTP response) following any act aborts the run immediately at the source, instead of surfacing 10 minutes later at the consistency checkpoint. Set `SCN_FAILFAST=0` to disable raising (trace-only).
- **`npm run test:ui-smoke`** — the fast (<1 min) high-risk UI smoke test (new doc → floating action → `@`-action → sidebar sync → insert table); streams the live trace.
- **`python scripts/trace_report.py [trace.jsonl]`** — renders a timeline, per-phase totals, slowest steps, and CHECK coverage rollup from a trace. Defaults to the latest run under `test-results/runs/`.

#### `scripts/run_test_exec.py` — self-contained TestExec-NNN/ folders

For investigations (a specific bug, a regression hunt, a one-off run worth
keeping a record of), wrap the pytest invocation in `run_test_exec.py` instead
of calling pytest directly:

```bash
/mnt/c/dev/venvs/uv1/bin/python3 scripts/run_test_exec.py \
  -q "Investigating GTaskSheet-XXXX: <question>" \
  tests/test_journey.py -x -v < /dev/null
```

This creates `test-results/TestExec-NNN/` (zero-padded, auto-incrementing)
containing everything from that single run:
- `runs/` — per-step scn traces (redirected via `SCN_RUN_DIR`)
- `gas-logs/` — archived GAS logs (redirected via `SCN_GAS_LOG_DIR`)
- `allure-results/` + `allure-report/` — raw and generated Allure HTML report
- `junit/pytest.xml` — JUnit results
- `pytest-stdout.log` — full captured console output
- `README.md` — deployed GAS version, test package, investigation question,
  and PASS/FAIL summary

`test-results/INDEX.md` is regenerated after every run, newest-first, linking
to each `TestExec-NNN/README.md` and its Allure report. Only `README.md` and
`INDEX.md` are committed — the bulky generated subdirs (`runs/`, `gas-logs/`,
`allure-results/`, `junit/`, `allure-report/`, `pytest-stdout.log`) are
gitignored.

Without `run_test_exec.py`, traces/GAS-logs/JUnit/Allure output still go to
their default unconditional locations (`test-results/runs/`,
`test-results/gas-logs/`, etc.) as described above — the wrapper only adds
per-invocation grouping and the README/INDEX audit trail.

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
