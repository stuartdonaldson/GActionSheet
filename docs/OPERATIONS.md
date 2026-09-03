# OPERATIONS — GActionSheet

## Deployment Model

GActionSheet is a **single GAS project** (`scriptId: 12EKX7dQiO1Wf7rvv94Adgpbh3nac0OetsZMTD_1lme3y2o1KLYdKcTXi`), container-bound to the ActionSheet spreadsheet. It is deployed simultaneously in two modes:

| Mode | Purpose |
|------|---------|
| **Workspace Add-on** | Homepage card in active Google Docs — Sync now, VerifySync, Insert / refresh tracker |
| **Web App** | `doPost` proxy endpoint for sheet writes (runs as deployer identity) |

The same script also hosts the **automation feature set** (timed sweep trigger, `onEdit` timestamp stamper, archive job) activated by installable triggers on the ActionSheet container.

No server infrastructure. No separate projects. One push updates both deployment modes.

### Test vs. Prod: what's actually isolated

`pnpm run deploy:test` and `pnpm run deploy:prod` repoint two different **Web App deployments** (`TEST-WEB-APP` / production), each with its own deployment ID and URL, each serving whatever code was pushed to HEAD at the moment that deployment was last repointed. That per-deployment pinning is real for Web App (`doGet`/`doPost`) traffic — a caller hitting the TEST URL keeps getting the code snapshot from the last `deploy:test`, even after a later `clasp push`, until TEST is repointed again.

**Installable triggers do not have this isolation.** Time-based triggers (`syncAll`) and the `onEdit` trigger always execute against the script's HEAD — the single most-recently-pushed version of the code — regardless of which Web App deployment (test or prod) is currently pinned to which version. There is exactly one script project (`scriptId` above) and one HEAD; a trigger created via `ScriptApp.newTrigger()` (as `TriggerManager.js` does) is not bound to a specific deployment ID. So a `clasp push` made while iterating on TEST immediately changes what code the trigger runs in production too — there is no trigger-level separation between "test" and "prod" today.

Practically, the real difference between the TEST and production deployments is **which population of users is calling which URL**, not which code is running in the background:
- **TEST** — the URL/version used during active development and by `pytest`; also what add-on users enrolled in the test program are pointed at.
- **Production** — the URL/version tied to the production, user-installable add-on listing in the Google Workspace Marketplace / GCP project; the population that installed the real add-on.

Consequence for anyone touching `TriggerManager.js` or reasoning about trigger behavior: don't assume "test" and "prod" trigger executions can be told apart or gated independently without a genuinely separate script/deployment. See `gts-li3g` for a concrete bug this caused (the 30-min `syncAll` trigger racing an in-flight sync) and why disabling the trigger was rejected as a fix.

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

### Verified Team Portal Identity (GIS / NUUC-Dispatch) — no OAuth client needed here
The verified team portal's identity (GIS sign-in, signed assertion, `_verifySignedAssertion`
in `src/AccessControl.js`) is provisioned entirely on the **NUUC-Dispatch** project, not
this one (ADR-0021, `../../NUUC-Dispatch/knowledge-base/adr/0002-signed-identity-assertion.md`).
GActionSheet only needs the shared per-target HMAC secret (the Script Property named by
the assertion's `kid` claim) — **no OAuth 2.0 Web client, no Authorized redirect URI, and
no `GIS_CLIENT_ID`/`GIS_CLIENT_SECRET` are required on this project's GCP project.**
`gts-hc6v` tracked provisioning such a client here under ADR-0017 Phase 2's now-superseded
auth-code-redirect design; it was closed as superseded once confirmed that the live
verification path never reads `GIS_CLIENT_ID` (the one function that did,
`_verifyGisIdToken`, is dead code — see its in-source comment). See
`docs/verified-team-portal-plan.md` for the NUUC-Dispatch-side provisioning steps that
*are* required (on that project, not this one).

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

Use the pnpm scripts — never invoke `clasp` directly.

| Goal | Command |
|------|---------|
| Deploy for test cycle | `pnpm run deploy:test` |
| Deploy to production | `pnpm run deploy:prod` |
| Push source only (no new version) | `pnpm run push` |

| What is deployed right now? | `node manage-deployments.js --summary --env test\|prod` |

**`pnpm run deploy:test`** stamps `src/Version.js`, pushes `src/`, repoints the TEST Web App deployment, runs the post-deploy hooks, verifies over the wire, and prints the deploy summary. Running `clasp push` or `pnpm run push` alone leaves the versioned Web App deployment stale — the test suite will call the old revision and produce `sync.warn: Non-JSON response` failures.

**The pipeline itself is GAS-Core's `gas-deploy` package**, pinned as a git dependency in `package.json` and documented in `GAS-Core/packages/gas-deploy/README.md`. `manage-deployments.js` is this project's *configuration* of it: the two targets and their anchors, the `BUILD_INFO` stamper, the ordered post-deploy hooks, and the ledger/metadata record shapes. Two entry points in that file are deliberately not deploys and stay project-local: `--verify*` (Script-Property drift, `scripts/deploy-hooks.js`) and `--deploy-dev` (a HEAD push, which has no named deployment to verify against).

**Credentials.** `local.settings.json` must carry `claspAuth` — the clasp credential file this project deploys with (`~/.clasprc-sdonaldson.json`). Every clasp invocation goes through the package's `claspEnv()`, which always sets `clasp_config_auth`; there is no code path that runs bare `clasp` and silently falls back to `~/.clasprc.json`, which is how a push lands in the wrong script project.

**Deployment IDs** are maintained via `clasp deploy --deploymentId <id>` so Web App URLs never change across pushes. The deployment is resolved from the *live* `clasp deployments` list by matching the `TEST-WEB-APP` / `PROD-WEB-APP` anchor in its description — so a stale recorded ID can never be deployed into, and the anchor must stay in the deployment description. Neither the script nor the package ever creates a deployment: a new URL is always a deliberate human decision, made in the Apps Script editor.

**Deploy verification (`?cmd=version`).** The deployed webapp answers `{ok, version, versionDate, target, deploymentId}` with no secret required, routed ahead of every auth gate in both `doGet` and `doPost` (so it works on an `ANYONE_ANONYMOUS` deployment and before any secret is bootstrapped). The deploy polls it until both the version and the target match what was just stamped, and fails the deploy on a mismatch — printing the summary anyway, so the operator can see what *is* deployed. `clasp deploy` exiting 0 only proves a version was created, not that the /exec URL is serving it; the `target` check is the only thing that catches a deploy landing in the wrong environment.

**Version numbering.** `package.json` is the sole source of truth for both counters. A TEST deploy bumps the integer `build` and stamps `v<version>.<build>`; a PROD deploy bumps the semver patch, resets `build` to 0, and stamps `v<version>`. `BUILD_INFO.env` (`test`/`production`/`dev`) remains the source of truth for Axiom's `env` column — the version string is a human-readable derivative, never the reverse. `src/Version.js` is generated output: never hand-edit it, and nothing reads a version back out of it.

**Records.** Every deploy appends one line to `deployment-ledger/<target>.jsonl` (`timestamp`, `target`, `deploymentId`, `version` as `@<revision>`, `description`, `url` — the schema `write-environment.py` and the pipeline report read) and overwrites `.deploy-metadata.json`, which `commit-deploy-stamp.js` consumes during `release:*`.

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

### Config Sheet Keys (rendering)

The ActionSheet's `Config` tab is a `Key`/`Value` sheet read by Sync. The rendering keys below are
optional — every one of them has a working default and the sheet itself may be absent:

| Key | Value | Default | Effect |
|-----|-------|---------|--------|
| `ai_token` | JSON style object (`fontFamily`, `fontSize`, `color`, `bold`, `italic`, `underline`) | built-in token style | Uniform character style applied to the `ACT-N:` token on flush |
| `action_text` | JSON style object (same shape) | none (author formatting untouched) | Uniform font family/size/colour/underline for action text (ADR-0022) |
| `SR Indent` | Non-negative integer | `0` | Leading spaces applied to each action-text continuation line on flush (ADR-0027 rule 8) |
| `Field SR Indent` | Non-negative integer | `0` | Leading spaces applied to each custom-field continuation line on flush; independent of `SR Indent` |

A blank, negative or non-numeric indent value falls back to `0` rather than failing the flush. Both
indent keys are presentational: the parser strips leading whitespace on read, so changing them never
alters stored action text or field values. Values are cached per GAS execution — an edit takes
effect on the next sync run, not mid-run.

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

## Team Reassignment Runbook

To move a document to a different team, edit the master GActionSheet's `DocData`
tab — no code changes or redeployment needed:

1. In `DocData`, find the row for the target document and set `Team Id` to the
   new team and `Sync Status` to `UpdateDoc`.
2. Run a sync for that document — menu **Action Sync > Sync** from the doc, or
   wait for the 30-minute `syncAll` sweep (see §Automation).
3. Verify the change took effect: the document's `teamScope` app property and
   `DocData.Team Id` should both equal the new Team Id, and `Sync Status` should
   be cleared back to empty.

This is handled by `_syncTeamScope` (`src/SyncManager.js`): when
`DocData.Sync Status === 'UpdateDoc'`, it overwrites the document's `teamScope`
app property from `DocData.Team Id`, logs `sync.teamScope.overridden`, and
clears `Sync Status`. The folder-walk auto-assignment (used when `teamScope` is
blank) is bypassed in this path. `assertTeamAccess` (`src/SyncManager.js`)
gates team-scoped reads on Drive folder access for the calling user.

Regression coverage: `tests/test_team_scope.py` S3 (UpdateDoc override) and S4
(idempotent re-sync — re-running sync without further DocData changes makes no
additional writes).

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

### Axiom (`nuuts` dataset)

Structured logs from both sides (GAS via `GasLogger.js`, Python tests via
`scn/reporter.py`) are also shipped to Axiom dataset `nuuts` — see
`scripts/query_axiom.py` to query it and `scripts/call_webapp.py` for the
manual-probe path. Config lives in `local.settings.json`
(`axiomDataset`/`axiomToken`/`axiomQueryToken`), written by `pnpm run
deploy:test`.

**Account owner (as of 2026-07-30):** `stuart.donaldson@gmail.com`. This is
a placeholder owner, not the intended long-term one — expect this to move to
an org-owned account later. Only the Axiom web console (login as the owner
above) can manage org/dataset-admin operations (map fields, vacuum, member
access); neither API token in `local.settings.json` has that permission
(both are scoped to ingest/query only — confirmed via 403 on `PUT
/v2/datasets/nuuts/mapfields`).

**Known issue:** `nuuts` is at Axiom's 256/257-field-per-dataset cap (bead
`gts-pfyx`). GAS-side events now nest their payload under one `data` field
(`GasLogger.js`) instead of spreading it flat, but that alone doesn't free
existing columns — `data` still needs to be marked as an Axiom **map field**
(console: Datasets → nuuts → mark `data` as map field) *before* it can
absorb new sub-keys without growing the column count further, and a
**vacuum** (console: Datasets → nuuts → Vacuum fields; once/day limit) is
needed to reclaim the ~257 already-registered legacy columns. Data is not
lost by either operation — only unused field *definitions* are dropped.

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
| New advanced-service scope added to `appsscript.json` (e.g. Admin SDK) | Deployed WebApp call fails with "You do not have permission to call ..." even after re-running an authorizing function in the editor | The scope must ALSO be registered on the OAuth consent screen (GCP Console → APIs & Services → OAuth consent screen → Scopes/Data Access) — adding it to the manifest alone is not enough. Then revoke the app's grant at `myaccount.google.com/permissions` and re-run an editor function that calls the new service to force a fresh consent prompt. See `knowledge-base/references/gas-admin-directory-external-groups.md`. |
| Admin SDK Directory API disabled at the GCP-project level | Same "permission" error as above, persists even after consent-screen scope registration | Enable **Admin SDK API** in GCP Console → APIs & Services → Library (separate from declaring it as an Apps Script advanced service in the manifest) |
| `AdminDirectory.Members.hasMember(groupKey, externalEmail)` | Throws `GoogleJsonResponseException: Invalid Input: memberKey` for a non-domain (external) member email, even when that email IS a real member | Use `AdminDirectory.Members.get(groupKey, memberKey)` instead — catch the thrown 404 as "not a member," a successful return as confirmed membership. `hasMember` only reliably works for domain-internal memberKeys. |
| `DriveApp.setSharing(...)` on a Shared Drive folder | Throws `Exception: Cannot use this operation on a shared drive item` | Use the Drive v2 advanced service instead: `Drive.Permissions.insert({role, type}, fileId, {supportsAllDrives: true})` / `Drive.Permissions.remove(fileId, permissionId, {supportsAllDrives: true})` |
| Shared TEST-account contention during a full pytest sweep | A "call this fires exactly ONCE" assertion (e.g. batching-count tests) sees N>1 events in its fence window; the inverse shape also occurs — an expected event never appears within its bounded wait, because the same background trigger/session activity delayed it (or a differently-tagged event) past the window instead of duplicating a tag | The account's installed 30-min `syncAll` time-based trigger (`TriggerManager.js`) or a second concurrent test/session can log the identical tag inside the same window (confirmed incidents: `gts-li3g`, `gts-moy1.2`; `gts-obry.2` reproduced the missing-event shape on `test_sync_lock_serializes_concurrent_syncdocument_for_same_doc` during a ~2h full sweep, then passed clean twice in isolation — no code change; `gts-7vo2.2` caught a live recurrence via `test_sync_all_op_propagates_to_webapp` and cross-checked it against Axiom — the contaminating `sync.all.start` had a growing `docCount` (118→122 across ~7 min, ~2–3 min apart), a cadence inconsistent with the 30-min trigger, pointing at concurrent test-session activity rather than `TriggerManager.js` for that specific occurrence). Don't run two full sweeps, or a sweep alongside manual TEST-deployment testing, concurrently. **The `op`/`parentOp`-correlation filtering mode this row used to recommend now exists and is in use**: `tests/helpers/gas_log.py::matches_op` (`gts-obry.1`) scopes `collect_logs`/`wait_for_log` to entries chained from one call's own `opId`, and all three batching-assertion tests it was built for — `test_kkm7_batching.py`, `test_uuse_scoped_listing.py`, and `test_sync_all.py::test_sync_all_op_propagates_to_webapp` (`gts-7vo2.2`) — now mint their own opId up front and filter through it, rather than relying on the raw tag+timestamp fence alone. |

---

## Running Tests

The `scn/` package provides the scenario harness (`ai`, `engine`, `session`, `surfaces`, `ui`, `contract` modules). Architecture: `docs/atdd/scenario-harness-design.md`. Strategy: `docs/atdd/atdd-lifecycle.md`.

### Test Accounts

Most tests run as a single primary account. The access-filter journey (`J-ACCESS-FILTER`,
used by the Import and Notify features) additionally requires one or more **restricted**
accounts so the read-denied path is genuinely exercised rather than simulated.

Auth files are account-identity files shared across projects under
`$PLAYWRIGHT_AUTH_DIR` (`.envrc`, default `~/.playwright`), named by the real
Google account they hold. This project maps each role below to a specific
account file via `local.settings.json`'s `"playwrightAccounts"` map (e.g.
`{"primary": "sdonaldson.json"}`); a role with no entry there falls back to
`.auth/<role>.json`. Mechanics are the reusable
`/mnt/c/dev/DevStandard/docs/standards/playwright-shared-auth.md` standard;
this project's own role taxonomy is in this project's `.auth/README.md` and
`docs/security-architecture.md` §5.

| Account role | `playwrightAccounts` key | Minimum Drive permissions |
|--------------|--------------------------|----------------------------|
| Primary | `primary` | Full-access baseline (currently also the dev deployer). Reader (or owner) on **all** team folders registered in `TeamData`. |
| `test.u1` | `test.u1` *(not yet captured)* | Same Drive access as Primary, but a separate account from the deployer — primary end user, non-deployer, target taxonomy (see `docs/security-architecture.md` §5). |
| `test.u2` | `test.u2` | Restricted — single-team subset. Reader on a **strict subset** of team folders only — must have **no** access to at least one team folder the primary can read. |
| `test.u3` | `test.u3` *(not yet captured)* | Restricted — other-team subset (J-ACCESS-FILTER's `TeamA-only`). Reader on a *different* single team than `test.u2`, no access to the rest. |
| `nuuts.service` | `nuuts.service` *(future)* | Production service/deployer account. Reader/Editor on team folders + the ActionSheet only. |

`test.u2` is the same second Google account used by the Probe tests
(`pnpm run probe:test.u2`). Setup for a restricted account:

1. Capture its storage state: `node tests/playwright/auth.setup.js --account=<slug>`
   (sign in as the restricted account when prompted; pick a slug that names
   the real account, e.g. `sanctuary`). Or `pnpm run auth:test.u2` for a
   generic default slug.
2. Add `"test.u2": "<slug>.json"` to `local.settings.json`'s `playwrightAccounts`.
3. In Drive, share the intended team folder with the restricted account as **Reader**.
   Do **not** share the other team folders — that asymmetry is what produces the deny path.
4. Seed one source document with ≥1 team-scoped action in each relevant team folder
   (the access-filter fixture; idempotent check-exists-or-create).

The harness selects the account per run via `PROBE_AUTH_STATE` (an explicit
file path, defaults to the primary account's file). Tests that assert a
restricted view point it directly at the `test.u2`/`test.u3` account file.

> This is a **shared test asset** for EPIC-D (Import) and EPIC-E (Notify). The account
> fixture matrix and the journey it backs are specified in
> `knowledge-base/staging/j-access-filter-journey.md`. The full account-role taxonomy
> and naming rationale are in `docs/security-architecture.md` §5 and `.auth/README.md`.

### Test Patterns

**Python-drives-Playwright pattern.** Scenarios exercise two kinds of entry points:
1. **HTTP fixture shortcuts** (`scn.sync()`, `scn.set_status(ai, status)`, `scn.insert_tracker()`, `scn.delete(ai)`) — fast, synchronous, no browser required. Use for testing the HTTP integration path and internal consistency.
2. **UI sidebar acts** (`scn.ui.sidebar_sync()`, `scn.ui.sidebar_set_status(target, status)`, `scn.ui.insert_tracker_button()`, `scn.ui.sidebar_delete(target)`) — exercise real user entry points through Playwright. Use to verify the UI integration and fire the true add-on code path.

**Cost rule.** Reserve Playwright for surfaces only the UI can show, and for exercising a real UI entry point as the call-site. Everything that does not require the browser stays on the HTTP fixture path (far cheaper). The browser cold start is amortized across all UI acts of one journey — one launch, many acts. During the Playwright phase prefer TARGETED single-surface expectations (verify(on=UI, within=) drained by checkpoint(STEP, on=UI), or a cheap verify(on=DOC) probe) and reserve INTEGRITY for HTTP-phase boundaries and the journey end. This is the explicit answer to "Playwright is expensive to spin up": amortize the one cold start, and keep non-UI acts off the browser entirely.

**One-browser-per-journey fixture.** All UI sidebar acts within a journey share a single module-scoped browser instance, launched once at the journey start and torn down at the end. This pattern amortizes the Chromium cold-start cost across multiple acts. The canonical fixture is `browser_page` in `tests/test_journey.py` (scope="module"), with `.auth/user.json` storage state for authentication. Non-UI acts remain entirely on the HTTP/fixture path and do not touch the browser.

### APT Corpus Tooling (`scripts/apt.py`)

Format spec + tool contract: `docs/interfaces/action-portable-text.md`. `scripts/apt.py` is the
one entry point for authoring/reviewing `.apt.txt` corpora under `tests/fixtures/`, sharing its
differ (`scripts/apt_lib.py::diff_apt`) with `tests/test_apt_corpus_check.py` (decision 8 — one
implementation, not a CLI copy and a pytest copy).

```bash
# Diff two files directly -- no network, no corpus resolution.
python scripts/apt.py diff a.apt.txt b.apt.txt

# Capture the canonical Doc, diff against the checked-in golden, exit 0 on a clean tree.
python scripts/apt.py pull action-reference

# Materialise a corpus file into its Doc (overwrites; refuses on drift unless --force).
python scripts/apt.py push action-reference

# Promote the LAST capture (not a fresh re-capture) into the golden.
# --accept-presentational auto-accepts only when presentational is the highest class present;
# structural changes always need an overall y/N; every preservation-tier entry needs a reason.
python scripts/apt.py bless action-reference --accept-presentational
```

Exit codes mirror `apt_lib.AptDiffResult.exit_code()`: 0 clean, 1 presentational, 2 structural,
3 preservation — script the exit code, don't parse the printed diff. Doc-id resolution for
`push`/`pull`/`bless`: `--doc` > the golden's own `<!-- doc: ... -->` header > (canonical
`action-reference` corpus only) `referenceDocId` in `local.settings.json`. A scenario corpus under
`tests/fixtures/` (anything with a `.scenario.json` sibling) is doc-less by design (materialises
into a fresh `ScenarioSession.new_doc()`) — `push`/`pull`/`bless` against one without `--doc` or a
golden `doc:` header errors naming that.

### Test tiers

Every collected test belongs to exactly one tier, decided by one **opt-in** marker and its
**auto-derived** complement (`gts-aqpk`):

| Tier | Selector | Marker source | Size / cost |
|---|---|---|---|
| **fast** | `pnpm run test:fast` (`-m "no_live_session and not slow"`) | opt-in | 626 tests, ~25 s, zero network |
| **local** | `pnpm run test:local` (`-m no_live_session`, `-n 4 --dist worksteal`) | opt-in | 716 tests, ~36 s parallel (~65 s serial), zero network |
| **live** | `pnpm run test:live` (`-m live`) | auto-derived | 421 tests, hours — real GAS/Drive round trips. **Serial by decision — see Parallelism below** |
| **everything** | `pnpm run test:full` | — | all 1137 + the Playwright specs (merge-gate) |

**`no_live_session` is the only marker anyone applies by hand**, once per module as
`pytestmark = pytest.mark.no_live_session`, and only for a module proven to make no live
GAS/Google round trip. It does two jobs at once: it selects the tier, *and* it is what
`tests/conftest.py::_session_is_no_live_session` reads to skip the four session-scoped
autouse pre-flights (`_check_deployed_build`, `_check_auth_session_alive`,
`_reset_test_state`, `_purge_stale_test_docs`). Those pre-flights skip only when **every**
collected item is marked — which `-m no_live_session` guarantees by deselecting everything
else, and which a mixed run deliberately does not. So the fast tier needs no conftest of its
own: the existing gate already does the work a separate conftest would have done.

**`live` is never written in a test file.** `tests/conftest.py::pytest_collection_modifyitems`
stamps it on every collected item that does not carry `no_live_session`. Two consequences worth
knowing: classification is total by construction (fast+local and live partition the suite
exactly — 716 + 421 = 1137), and **a new test file with no marker at all lands in `live`**,
which is the safe default: it pays the pre-flight and round-trip cost it may or may not need,
rather than silently joining a tier that skips the pre-flights it depends on. Nothing needs
updating when a test file is added.

**`slow` is a cost attribute, not a tier.** `tests/test_document_export_harness.py` is
genuinely network-free but takes ~52 s on its own (it spawns a fresh `python scripts/...`
subprocess per test), which is most of the local tier's wall time. It carries
`[pytest.mark.no_live_session, pytest.mark.slow]`; `test:fast` excludes it to hold a sub-30 s
budget, `test:local` includes it.

**The fast and local tiers need no `local.settings.json` and no captured Google session.**
Move the file aside and `pnpm run test:fast` still passes (verified: 626 passed, ~28 s). That
holds because the two live pre-flight fixtures load settings *inside* their bodies rather than
requesting the `settings` fixture as a parameter — pytest resolves a fixture's arguments before
running its body, so taking `settings` there made the file's existence a hard precondition of
every test in the suite, `no_live_session` or not. Keep it that way: any new session-scoped
autouse fixture must do its `_session_is_no_live_session(request.session)` early-return before
anything live is resolved, not after.

**To move a module into the fast tier**, prove it network-free rather than asserting it: run it
with sockets blocked (`socket.socket.connect` patched to raise) via a `-p` plugin and confirm it
passes with no test skipped for a network reason. Passing while *skipping* is not proof —
`tests/test_apt_corpus_check.py` passes offline today only because every current scenario is
owned by a batched runner and skips; it drives a real `ScenarioSession` and stays in `live`.

### Parallelism (`gts-xvgl`)

**Only the local tier runs in parallel, and only it ever will without refactoring.** The split is
not a default, it is a measured decision; the numbers and the reasoning are here so no future
session re-derives them.

| Selector | serial | `-n 4 --dist worksteal` | verdict |
|---|---|---|---|
| local (`-m no_live_session`, 716) | 64.8 s (72 s wall) | **36.4 s (44 s wall)** | **parallel — 1.8x** |
| `tests/test_document_export_harness.py` alone (90) | 47.7 s (55 s wall) | **23.8 s @ `-n 6`** | the whole of the win |
| fast (`-m "no_live_session and not slow"`, 626) | 23.7 s | 23.2 s | **serial — no gain** |
| live (`-m live`, 421) | — | — | **serial — unsafe, see below** |

Three things the sweep (`-n` 2/3/4/6/8/12, both `--dist load` and `--dist worksteal`) settled:

* **`-n 4` is the knee, not `-n auto`.** On a 12-core box `-n 12` is *slower than `-n 4`*
  (47–53 s vs 36 s): each worker independently imports and collects the full 1137-test suite, so
  past ~4 workers the fixed per-worker startup grows faster than the shared work shrinks. Do not
  "improve" this to `-n auto`.
* **`--dist worksteal`, not the default `--dist load`.** The local tier's cost is nine tests of
  3–8 s (each spawns a `python scripts/...` subprocess) inside a long tail of sub-10 ms tests.
  `load` pre-assigns in chunks and strands a heavy test behind a full worker; `worksteal`
  rebalances. On the export harness alone: 30.8 s (`load`) vs 23.8 s (`worksteal`).
* **The fast tier stays serial.** 23.2 s vs 23.7 s is a wash — its cost is per-worker startup, not
  test execution — and running it serially keeps the `[n/total]` duration instrumentation at full
  fidelity in the tier developers actually run on every edit.

**No cross-test contamination.** Eight parallel runs (n = 2, 3, 4, 6, 8, 12 across both dist modes)
were diffed against the serial baseline by JUnit XML nodeid → outcome: 716 nodeids in every run,
zero missing, zero extra, zero outcome differences. The only two failures are the pre-existing
`test_document_export_harness` `schema_version` 3.1-vs-3.0 pair (tracked by `gts-e34d`),
identical in serial and in all eight parallel runs.

**Duration instrumentation is worker-gated, not disabled.** Under `-n`, *both* the worker and the
controller run `pytest_runtest_logstart`/`logreport` for the same test, so ungated the
instrumentation double-counts (measured: 132 JSONL records for 66 tests, every nodeid twice) and
N+1 processes read-modify-write the single `tests/.pytest_duration_baseline.json` through one
fixed `.tmp` name — last writer wins, other workers' samples silently discarded.
`tests/conftest.py::_duration_enabled` gates the hooks off in **workers only** (`workerinput`
exists only there). The controller is one process that sees every test exactly once, so the
counter, the JSONL trend log and the baseline update all keep working under `-n`; the only loss is
that `[n/total]` counts completions rather than starts.

**Adding a local-tier test: the one rule.** Write durable state under `tmp_path`, never under a
shared repo directory. One existing test deliberately breaks this —
`test_apt_fixtures_lint.py::test_a_capture_kind_file_fails_the_same_assertion` creates and deletes
`tests/fixtures/not-a-golden.apt-lint-backstop.apt.txt` in the real fixtures dir, because the check
it backstops calls `path.relative_to(REPO_ROOT)`. That is safe today only because every other
consumer of that glob (`test_apt_scenario_format.py`) parametrizes at **collection** time, and
xdist completes and cross-checks collection in all workers before any test executes. A new
*runtime* glob of `tests/fixtures/*.apt.txt` that asserts per-file properties would turn this into
a real flake. Prefer `tmp_path`.

#### Why the live tier is serial — decision, not an omission

`gts-xvgl` design questions Q1–Q4, answered against the live tier. Parallelising it is **not**
blocked on a `-n` flag; it is blocked on four shared identities that no worker count can
disambiguate. Revisit only if someone first removes these.

1. **The `_TEST_*` toggles are global to the GAS deployment, not to a doc.**
   `tests/conftest.py::_reset_test_state` clears them once per *pytest session*. Under `-n` each
   worker is its own session, so worker B's start-up reset would clear a toggle worker A set
   mid-test. `src/TestFixtures.js::reset_test_state` documents the same scoping. This alone is
   disqualifying.
2. **One session-scoped clone, one shared master.** `test_doc_id` clones the master template once
   per session and, at teardown, calls `end_test_session` to **restore the master**. N workers = N
   concurrent restores of the same Google Doc, interleaved with other workers' still-running tests.
3. **Fixed team identities are shared across files, so file-affinity does not help.**
   `TestTeamScopeA` / `TestTeamA` / `TestTeamScopeAChild` appear in 19 test files
   (`test_team_scope`, `test_import`, `test_team_folder_reconciliation`, `test_team_write_*`,
   `test_admin_doc_scan`, …), several of which mutate that team's folder and membership, backed by
   `DISCOVERY_*` / `TEAMSCOPE_FOLDER_*` script-property caches deliberately persisted *across*
   sessions. `--dist loadfile` pins a file to a worker but the identity is shared between files, so
   it buys nothing. Likewise the single shared TEST spreadsheet (`testSheetId`) — one Actions and
   one DocData sheet per deployment — is the durable state most live tests assert on, and
   `_purge_stale_test_docs` runs a global archive sweep over it at session start.
4. **The GAS side would serialise it anyway, at a worse price.** The hot write paths take
   `LockService.getScriptLock()` — a *script*-global lock (`src/SyncManager.js`,
   `src/ArchiveManager.js`, `src/WebApp.js`, `src/EditorAddonCard.js`), several with
   `waitLock(5000)`. Concurrent workers hitting one TEST deployment do not execute in parallel;
   they queue, and the ones that exceed the wait fail. Parallelism there converts wall-clock into
   lock-timeout flakes. The safe `-n` for the live tier (Q4) is therefore **1**.

The live tier's wall-clock problem is real, but the lever is fewer/cheaper live round trips and
better batching — not workers. Do not add `-n` to `test:live` or `test:full`.

### Running the Tests

```bash
# Fast tier — no GAS, no network, no browser. The first thing to run after any edit.
pnpm run test:fast

# Local tier — fast tier plus the slow-but-offline document-export harness.
# Runs on 4 xdist workers (`-n 4 --dist worksteal`); see "Parallelism" above for why 4 and
# not `auto`. Drop the -n to get per-test [n/total] duration lines back at full fidelity:
#   /mnt/c/dev/venvs/uv1/bin/python3 -m pytest -m no_live_session -q
pnpm run test:local

# Live tier — real GAS round trips; requires `pnpm run deploy:test` first.
pnpm run test:live

# Always use -x (fail-fast) on a scoped or known-green run: stop after the first failure.
# (For triaging a fresh full sweep, drop -x and let it run to completion — see CLAUDE.md.)
/mnt/c/dev/venvs/uv1/bin/python -m pytest tests/ -x -v

# §16.10 canonical ATDD journey — Acts 1–3 (requires live GAS — pnpm run deploy:test first):
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
revision just pushed by `pnpm run deploy:test`. Before Act 1, the journey opens
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
1. `pnpm run deploy:test` — pushes source, stamps the revision, repoints the TEST Web App deployment, writes `testToken` and `testTokenExpiresAt` to `local.settings.json`.
2. `local.settings.json` must contain `testSheetId`, `testDocId`, `webappSecret`, and `testToken`.

**Token expiry:** `testTokenExpiresAt` in `local.settings.json` records the expiry. If the token expires mid-session, re-run `pnpm run deploy:test` to rotate it.

> **`webappTestUrl` is auto-managed — do not set it manually.** `deploy:test` derives the TEST Web App URL from the `TEST-WEB-APP` deployment ID returned by `clasp deployments` and always overwrites `webappTestUrl` in `local.settings.json` with the authoritative value. A manually-set URL cannot become stale because it is overwritten on every successful deploy.

Playwright is used only for **UI-level tests** (homepage card rendering, menu presence assertions). It is not used for GAS fixture setup.

### Test observability

Every scenario run writes a per-step trace to `test-results/runs/<node>_<utc>.trace.{log,jsonl}` — a human-readable `.log` and a structured `.jsonl`, written unconditionally. Open the `.log` after a run to see what each step did and how long it took.

- **`SCN_TRACE=1`** — additionally streams the per-step trace live to the console as the run progresses. Use it to watch a long run and see which step it is currently stuck on. Each line shows the phase (`ACT` / `QUERY` / `UIACT` / `CHECK` / `CHECKPOINT` / `MONITOR` / `HTTP`), elapsed timestamp, and duration.
- **`SCN_FAILFAST`** — fail-fast GAS-error monitoring is ON by default: a `*.error` GAS log entry (or an unexpected/non-JSON HTTP response) following any act aborts the run immediately at the source, instead of surfacing 10 minutes later at the consistency checkpoint. Set `SCN_FAILFAST=0` to disable raising (trace-only).
- **`pnpm run test:ui-smoke`** — the fast (<1 min) high-risk UI smoke test (new doc → floating action → `@`-action → sidebar sync → insert table); streams the live trace.
- **`python scripts/trace_report.py [trace.jsonl]`** — renders a timeline, per-phase totals, slowest steps, and CHECK coverage rollup from a trace. Defaults to the latest run under `test-results/runs/`.

#### Allure step naming and UI-failure screenshots

`engine.drain()` wraps each per-surface CHECK in an Allure step named
`"<tag> <surface>"` (e.g. `journey sync-create UI`), giving the Allure report
one step per (expectation, surface) pair regardless of which checkpoint
drained it. On a `Surface.UI` FAIL-severity miss, a screenshot of the live
page is attached to the report named `"<tag> UI FAIL"`. Both apply uniformly
to every pytest scenario — no per-test opt-in.

**Screenshot on every UI failure (gts-3tkf).** Beyond drained-checkpoint
misses, *any* failing UI test — timeout or assertion — automatically saves a
full-page PNG and reports diagnostics, via two layers so there is no
copy-pasted capture logic:

- **Bounded driver waits** (`scn/ui.py`: `hover`, `create_action`, …) call
  `UiDriver.capture_failure(label, probes={...})` before raising. It saves
  `test-results/<label>.png`, attaches it to Allure, and embeds the screenshot
  path + every `page.frames` URL + each probe selector's per-frame
  `match_count` / `is_visible` / `bounding_box` into the raised error — so a
  selector/frame miss (count 0) is distinguishable from a visibility-detection
  problem (count > 0 but not visible) without a re-run.
- **A catch-all** `pytest_runtest_makereport` hook in `tests/conftest.py`
  screenshots the active page (found via the `browser_page` fixture or a
  `ScenarioSession.ui._page`) on any failed UI test, saving
  `test-results/FAIL-<nodeid>.png`, echoing the path + frame URLs into the
  failure report, and attaching the PNG to Allure. It is a no-op for non-UI
  (mock-based) tests.

**DOM-derived state over OCR/screenshot-reading (gts-3tkf follow-up,
gts-3sgr).** Both capture layers above also embed `scn.ui.describe_visible_buttons(frames)`
output ("Visible buttons: ...") — each frame's currently-visible interactive
button accessible names, read via the same `get_by_role("button")` signature
the bounded waits themselves query, not a screenshot a human (or model) has
to visually parse. This is now the project's default convention for any new
UI-failure diagnostic: prefer a DOM-derived list of what's actually
present/visible over asking anyone to read it off a PNG. Validated
(gts-3sgr) against real failures: the original `test_import_access_filter`
"Import" locator bug (gts-y8a0) took several screenshot reads, a headed
re-run, and multiple exploratory passes to diagnose before this diagnostic
existed. After it shipped, three separate follow-up reports
(gts-70wo, gts-t6hx, gts-1o7g) each ruled out "missing/broken button" as the
cause in a single read of the "Visible buttons" list (the button was present
every time — pointing instead at a render-timing race or backend-load
symptom, not a selector defect) — exactly the diagnosis-time reduction the
diagnostic was built for. Use `describe_visible_buttons()` (or extend it) for
any future custom UI-failure capture point rather than reinventing a
screenshot-only diagnostic.

#### Op/parentOp correlation for batching-count assertions (`gts-obry.1`)

`scn/session.py::_http_post` stamps every outgoing call with a client-
generated `opId` (a uuid4, stable across retry attempts) as `payload.opId`.
GAS's `doPost` already calls `GasLogger.startOp(payload.opId)`
(`src/WebApp.js`, `gts-j8cn`), which stamps that id as `parentOp` on every
`GasLogger.log(...)` entry the execution makes. A test asserting "exactly ONE
call of tag X for this sweep" should pass its own `opId` explicitly (via
`extra={"opId": ...}` on `_post_fixture`/`_post_route`) and filter with
`tests/helpers/gas_log.py::matches_op(match_fn, op_id)` instead of a bare
tag+timestamp fence — this scopes the count to log entries chained from THAT
call specifically, immune to an unrelated concurrent syncAll (the account's
30-min trigger, or another session) landing in the same window. See
`tests/test_kkm7_batching.py` / `tests/test_uuse_scoped_listing.py` for the
pattern, and the Failure Modes table above for the contention constraint this
closes.

Known gap: `scripts/call_webapp.py` (manual probes) does not populate `opId`
today, so `parentOp` is `null` for entries it produces — not on the
live-suite failure path this exists for, but worth porting if manual-probe
correlation ever matters.

#### onLinkPreview card rendering — `tests/test_link_preview.py`

The `onLinkPreview` add-on card (rendered via `addons.gsuite.google.com`) was
previously believed to require a real human mouse hover (gts-s9so) and
was covered only by a headed, human-instructed interactive test. gts-39jk
and gts-cug8 found that placing the text cursor on the `AI-N:` chip link
via `Ctrl+F` -> type -> `Enter` -> `Escape` (no mouse) fires the add-on's
`onLinkPreview` trigger, and re-placing the cursor after moving it away renders
the card — reproducible headless. `tests/test_link_preview.py` drives this
automatically, asserts the rendered card header + the native link-preview
bubble's `globalId` (rwz AC1/AC2), then sets the status via the in-card control
and asserts the durable result. It runs as part of the default suite — no
human interaction required. See `UiDriver.open_link_preview` (`scn/ui.py`).

The JS Playwright smoke layer (`tests/playwright/*.test.js`) already retains
its own traces and screenshots: `playwright.config.js` sets `screenshot:
'only-on-failure'`, `video: 'retain-on-failure'`, and reports through
`allure-playwright` into the same `test-results/allure-results/` directory as
the pytest suite. Combined with the pytest-side step naming and screenshots
above, the Allure report is uniform across both stacks — failures in either
stack carry a screenshot, and pytest steps carry their `[uc AC#]`-style tag.

#### `scripts/run_test_exec.py` — self-contained TestExec-NNN/ folders

For investigations (a specific bug, a regression hunt, a one-off run worth
keeping a record of), wrap the pytest invocation in `run_test_exec.py` instead
of calling pytest directly:

```bash
/mnt/c/dev/venvs/uv1/bin/python3 scripts/run_test_exec.py \
  -q "Investigating gts-XXXX: <question>" \
  tests/test_journey.py -x -v < /dev/null
```

This creates `test-results/TestExec-NNN/` (zero-padded, auto-incrementing)
containing everything from that single run:
- `runs/` — per-step scn traces (redirected via `SCN_RUN_DIR`)
- `gas-logs/` — archived GAS logs (redirected via `SCN_GAS_LOG_DIR`)
- `allure-results/` + `allure-report/` — raw and generated Allure HTML report
- `junit/pytest.xml` — JUnit results
- `pytest-stdout.log` — full captured console output
- `system-metrics.jsonl` — host CPU%/mem%/loadavg, sampled every 30s for the
  run's duration (`scripts/system_metrics.py`, gts-l6h0). Triaging a run
  whose per-test wall time is blown out vs its own baseline (gts-f3me.6):
  check this file first — sustained `cpu_pct`/`mem_pct` well above idle
  points to host-side contention (e.g. another session running concurrently
  on the same machine) rather than a GAS-backend or Google-infra slowdown,
  without depending on recalling what else was running at the time.
- `README.md` — deployed GAS version, test package, investigation question,
  and PASS/FAIL summary

`test-results/INDEX.md` is regenerated after every run, newest-first, linking
to each `TestExec-NNN/README.md` and its Allure report. Only `README.md` and
`INDEX.md` are committed — the bulky generated subdirs (`runs/`, `gas-logs/`,
`allure-results/`, `junit/`, `allure-report/`, `pytest-stdout.log`,
`system-metrics.jsonl`) are gitignored.

Without `run_test_exec.py`, traces/GAS-logs/JUnit/Allure output still go to
their default unconditional locations (`test-results/runs/`,
`test-results/gas-logs/`, etc.) as described above — the wrapper only adds
per-invocation grouping and the README/INDEX audit trail.

### UC Test Coverage & Sign-off

The five use cases in `CONTEXT.md` (UC-A capture/track, UC-B update from
either side, UC-C insert/refresh tracker table, UC-D archive closed actions,
UC-E import/forward across docs) are covered by the following test files:

| Use case | Covered by |
|----------|------------|
| UC-A — capture and track a new action (multi-format detection, idempotent re-sync) | `tests/test_journey.py`, `tests/test_journey_acts_1_3.py` (Acts 1–3) |
| UC-B — update an action from either side and converge | `tests/test_team_scope.py`, later acts of `tests/test_journey.py` |
| UC-C — insert/refresh the in-doc tracker table | `tests/test_tracker_view_only.py`, `tests/test_journey.py` |
| UC-D — archive closed actions | `tests/test_archive.py` |
| UC-E — import an open action from a teammate's doc (forward) | `tests/test_import.py` (`test_import_access_filter` AC1; `test_import_flow_forward_sync` AC2–AC4, incl. `created_date` carry-over) |
| Timed sweep (`syncAll`) | `tests/test_sync_all.py` |

**Sign-off (gts-mol06g, 2026-05-21):** all 8 UC scenarios pass — 14
passed, 2 xfailed (pipe-delimited assignee, tracked under `gts-tis`).
This is the last full-suite run across the UC matrix; later regression runs
(e.g. `gts-gdll`) are targeted spot-checks against specific surfaces,
not a re-run of the full UC matrix. UC-E (EPIC-D import/forward) was added
later and is not part of the mol06g 8-scenario sign-off baseline above.

> **Note (2026-08-26):** the two xfails above are void. They covered the
> pipe-delimited assignee form, which belonged to `FloatingActionParser.js` —
> deleted the day after this sign-off by `fd3249b` (GTaskSheet-ii7) together with
> `test_floating_action_parser.py`, the file the xfail markers lived in. ADR-0027
> records that `|` carries no meaning in an action paragraph; `gts-tis` is closed
> obsolete. The sign-off is otherwise unchanged: read it as 14 passed against the
> parser of that date. See bd memory `act-fields-pipe-separator-provenance`.

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

### ActionSheet is missing a newly-added schema column (e.g. `Custom Fields`)
`ensureSheetStructure()` (Setup submenu, `Extensions > Action Sync > Setup > Ensure Sheet
Structure`) is idempotent and header-driven off `CONTRACT_SCHEMA.sheetAction.headers`
(`SheetSetup.js`'s `_ensureHeaders`): it compares the sheet's header row against the current
schema and rewrites it — growing the row to add any new trailing column — whenever they don't
match. It is NOT run automatically by `syncDocument`/`syncAll`, so an existing ActionSheet
created before a schema-additive change (e.g. gts-nuur's `custom_fields` column, ADR-0024) will
not pick up the new header on its own. Run the menu item once per existing spreadsheet after
deploying a schema-additive change. No data loss: existing rows are untouched, and the new
column simply reads/writes blank until a caller populates it.

### testToken expired (tests fail with "test-token-expired")
Run `pnpm run deploy:test`. The deployment script generates a fresh UUID, POSTs it to the Web App, stores it in script properties, and writes the new token and expiry to `local.settings.json`.

### A pushed/deployed code change doesn't show up in the Extensions menu or add-on UI
`pnpm run deploy:test`/`deploy:prod` only repoint the **Web App** deployments (`TEST-WEB-APP`/
`PROD-WEB-APP`). The classic `Extensions > Action Sync` menu and the sidebar/card add-on surfaces
run through a **third, independent pointer** — a specific user's installed add-on binding — which
does not follow either the Web App deployments or a GCP Marketplace SDK App Configuration change
automatically. Confirmed 2026-08-13/14 (`bd remember gts-addon-install-deploy-lag`): updating the
Marketplace SDK App Configuration to a new version did not make a stale Extensions-menu error go
away until real wall-clock time passed for the per-account install to catch up, and consecutive
attempts surfaced under *different* deployment IDs, neither present in `clasp deployments` output.

Checklist, in order:
1. **Confirm the code actually reflects your change.** `clasp deployments` lists Web App
   deployments only — it will not show the add-on's installed deployment ID. Reproduce the
   failure, then run `clasp logs --json` and read `serviceContext.deployment_id`/`version` off
   the matching error entry. Compare that ID against `clasp deployments`; if it's absent, you're
   looking at the add-on-install pointer, not a Web App deployment.
2. **If it's a `linkPreviewTriggers` pattern-match failure** (chip preview never fires, zero log
   activity): check the GCP Marketplace SDK App Configuration's pinned deployment version — see
   `docs/lessons-learned/resolved/2026-06-02-smart-chip-rendering-is-publish-gated.md` Gate 2.
   Update it to the latest version and re-save/re-publish.
3. **If it's any other menu/card entry point failing with stale behavior** (this is the add-on
   install pointer, not the SDK config): a browser reload of the doc is not sufficient. Force a
   fresh binding — reinstall the add-on (`Extensions > Add-ons > Manage add-ons` → remove, then
   reinstall from the Marketplace listing), or, for a dev/test account, explicitly reselect the
   deployment via the Apps Script editor: `Deploy → Test deployments → Install as Add-on`.
4. **If reinstalling isn't practical right now,** wait and retry — this has resolved on its own
   with enough wall-clock time in observed cases, with no documented SLA.

Don't spend multiple redeploy-and-retry cycles guessing here — step 1 tells you definitively
whether you're chasing a stale Web App deployment (fixed by `deploy:test`), stale SDK config
(fixed by step 2), or a stale per-account install (fixed by step 3), before you touch anything.
