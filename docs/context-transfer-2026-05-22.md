# Context Transfer — 2026-05-22

## Prompt for new session

Load this file at the start of a fresh session:

> Read `/mnt/c/dev/GActionSheet/docs/context-transfer-2026-05-22.md` and execute all merge tasks listed. For each task, check whether the target file exists; if not, create it from the provided template. Commit all changes with a single atomic commit when done. Then close beads issues GTaskSheet-urx (POC verified) and GTaskSheet-ehr (architecture bootstrap complete) if still open.

---

## Task 1 — Create CONTEXT.md

File does not exist. Create `/mnt/c/dev/GActionSheet/CONTEXT.md` with this content:

```markdown
# GActionSheet — Context

## Purpose

GActionSheet is a Google Workspace Add-on that surfaces action items from Google Docs meeting notes into a central Google Sheet (the ActionSheet). It targets organizations using Google Workspace where meeting notes are in Docs and accountability tracking needs to be centralized without requiring participants to manually copy items.

## Core Capabilities

- **Add-on sidebar** — appears in the right-side panel of Google Docs (and Sheets); provides UI for triggering sync and displaying status
- **Web App proxy endpoint** — the same GAS script is deployed as a Web App; the add-on uses `UrlFetchApp` to call `doPost`, which runs as the deployer identity with write authority over the ActionSheet
- **Proxy-write pattern** — bridges the cross-identity boundary: add-on runs as the active user (read-only doc access); Web App runs as the deployer (sheet-write authority); no service account required for this pattern
- **Action extraction** — (planned) parse checklist items with assigned-person chips from meeting Docs
- **ActionSheet write** — (planned) append structured action rows (date, owner, text, source doc) to a central Google Sheet

## Architecture Summary

Single GAS script project, container-bound to the ActionSheet spreadsheet. Deployed in two modes simultaneously:

| Deployment | Purpose |
|-----------|---------|
| Workspace Add-on (test/prod) | Sidebar card in Docs/Sheets |
| Web App (test/prod) | Proxy endpoint called by add-on via UrlFetchApp |

Both deployments point to the same script source. Stable deployment IDs are maintained via `clasp deploy -i <id>` so URLs never change across pushes.

## Use Cases

### UC1 — Sync meeting doc actions
Actor: Staff member viewing a meeting doc in Google Docs
Flow: Opens add-on sidebar → clicks Sync → add-on sends doc ID to Web App → Web App extracts actions → writes rows to ActionSheet

### UC2 — View action status
Actor: Team lead
Flow: Opens ActionSheet directly; rows are appended with date, owner, message, source doc link

## Stakeholders

| Role | Name / Group |
|------|-------------|
| Primary user | northlakeuu.org staff |
| Deployer / Admin | sdonaldson@northlakeuu.org |
| ActionSheet owner | Bound spreadsheet (GAS parent) |

## Quality Goals

- **Zero-friction for end users** — single click to sync; no OAuth prompts after initial install
- **Stable URLs** — deployment IDs never change; WEBAPP_URL auto-registers via doGet
- **Auditable** — every proxy write carries timestamp + user email

## Glossary

| Term | Definition |
|------|-----------|
| ActionSheet | The central Google Sheet where action items are written; also the container script's parent |
| Add-on | The Workspace Add-on deployment of the GAS script |
| Web App | The Web App deployment of the same GAS script; receives POST from the add-on |
| Proxy-write | The pattern where the add-on calls the Web App to perform writes under the deployer identity |
| BUILD_INFO | Version/timestamp object stamped into `src/Version.js` before each deployment |
| WEBAPP_URL | Script property storing the normalized Web App URL; set automatically by `doGet` |
| WEBAPP_SECRET | Shared secret script property used to authenticate `doPost` requests |
| TEST-WEB-APP | Anchor string in deployment description used to discover the test Web App deployment ID |
| PROD-WEB-APP | Anchor string in deployment description used to discover the prod Web App deployment ID |
```

---

## Task 2 — Create DESIGN.md

File does not exist. Create `/mnt/c/dev/GActionSheet/DESIGN.md` with this content:

```markdown
# GActionSheet — Design

## Architecture

### Single-script dual-deployment

One GAS project (`scriptId: 12EKX7dQiO1Wf7rvv94Adgpbh3nac0OetsZMTD_1lme3y2o1KLYdKcTXi`) is container-bound to the ActionSheet spreadsheet. It is deployed simultaneously as:

- A **Workspace Add-on** (sidebar card in Docs/Sheets)
- A **Web App** (HTTP endpoint for proxy writes)

Both modes share the same source files. The `rootDir` in `.clasp.json` is `src/`; `appsscript.json` declares both `addOns` and `webapp` sections.

### Identity boundary and proxy-write pattern

Workspace Add-ons run as the active user. The ActionSheet is a restricted resource — end users should not have direct edit access. The Web App runs as the deployer (`executeAs: USER_DEPLOYING`), which has sheet-write authority.

```
[Add-on sidebar]
      |
      | UrlFetchApp.fetch(WEBAPP_URL, { method: 'post', payload: JSON })
      v
[doPost — runs as deployer]
      |
      | sheet.appendRow(...)
      v
[ActionSheet]
```

Authentication between add-on and Web App uses a shared secret (`WEBAPP_SECRET` script property), not Bearer tokens. Apps Script Web Apps do not propagate Google identity via Bearer auth.

### URL stability

Deployments use `clasp deploy -i <deploymentId>` to redeploy in-place. The URL never changes across pushes. `WEBAPP_URL` is stored in script properties and updated automatically when the Web App is visited via `doGet` (which also normalizes org-specific URL format variants).

### Org URL normalization

On northlakeuu.org, `ScriptApp.getService().getUrl()` returns:
`https://script.google.com/a/northlakeuu.org/macros/s/<id>/exec`

This format is normalized in `doGet` to the canonical form:
`https://script.google.com/macros/s/<id>/exec`

so that a single `urlFetchWhitelist` entry (`https://script.google.com/macros/s/`) matches.

## Module Map

| File | Role |
|------|------|
| `src/Addon.js` | Card builder, button handlers, UrlFetchApp proxy call |
| `src/WebApp.js` | `doGet` (self-register URL), `doPost` (verify secret, write to sheet) |
| `src/Version.js` | `BUILD_INFO` — stamped by `update-revision.js` before each deploy |
| `src/appsscript.json` | Manifest — addOns, webapp, oauthScopes, urlFetchWhitelist |

## Deployment Pipeline

```
npm run deploy:test
  └─ update-revision.js        → stamps src/Version.js with version + timestamp
  └─ manage-deployments.js     → finds TEST-WEB-APP deployment by anchor string
                                  clasp push (force if needed)
                                  clasp deploy -i <id> -d "<description>"
                                  writes .deploy-metadata.json
```

Release pipeline additionally runs `commit-deploy-stamp.js` which reads `.deploy-metadata.json` and commits `src/Version.js` with deployment metadata.

## Script Properties

| Property | Set by | Purpose |
|----------|--------|---------|
| `WEBAPP_URL` | `doGet` (auto) | Normalized Web App URL for UrlFetchApp calls |
| `WEBAPP_SECRET` | Manual (script editor) | Shared secret for doPost authentication |
| `GAS_LOGGER_FOLDER_ID` | Manual | Drive folder for GasLogger output (TDD phase) |
| `TEST_DOC_ID` | Manual / bootstrap() | Test Google Doc ID for smoke tests |
| `TEST_SHEET_ID` | Manual / bootstrap() | Test Sheet ID for smoke tests |

## urlFetchWhitelist

Required in `appsscript.json` for any Workspace Add-on that calls `UrlFetchApp`. Three entries cover all URL format variants produced by northlakeuu.org:

```json
"urlFetchWhitelist": [
  "https://script.google.com/a/macros/northlakeuu.org/s/",
  "https://script.google.com/a/northlakeuu.org/macros/s/",
  "https://script.google.com/macros/s/"
]
```

## Constraints

- Web App access must be **"Anyone"** (not "Anyone within org") — the org SSO policy enforces authentication on `UrlFetchApp` requests regardless of headers if set to org-restricted
- Web App `executeAs` must be **"USER_DEPLOYING"** to have sheet-write authority
- `urlFetchWhitelist` is mandatory — omitting it produces a hard error at call time, not a manifest validation error
```

---

## Task 3 — Add Web App proxy section to workspace-addon-setup.md

Append the following section to BOTH:
- `/mnt/c/dev/GActionSheet/knowledge-base/references/workspace-addon-setup.md`
- `/home/stuar/.claude/docs/workspace-addon-setup.md`

Insert before the "Minimum npm Scripts" section, or append at end:

```markdown
---

## Web App Proxy Pattern (Add-on + Web App, Single Script)

A single GAS project can simultaneously serve as a Workspace Add-on and a Web App endpoint. This pattern is useful when the add-on needs to write to a resource the active user may not have permission to access directly.

### Architecture

```
[Add-on sidebar (runs as active user)]
      |
      | UrlFetchApp.fetch(WEBAPP_URL, { method: 'post', payload: JSON })
      v
[doPost — runs as deployer (executeAs: USER_DEPLOYING)]
      |
      | sheet.appendRow(...)
      v
[Target resource (ActionSheet / restricted Sheet)]
```

### Manifest requirements

Both `addOns` and `webapp` sections must coexist in `appsscript.json`:

```json
{
  "webapp": {
    "access": "ANYONE",
    "executeAs": "USER_DEPLOYING"
  },
  "addOns": {
    "common": { ... },
    "docs": { ... }
  },
  "urlFetchWhitelist": [
    "https://script.google.com/macros/s/"
  ]
}
```

**`urlFetchWhitelist` is mandatory** for any Workspace Add-on that calls `UrlFetchApp`. Omitting it produces a hard error at call time, not a manifest validation error.

### Authentication

Bearer token forwarding does not work for Apps Script Web App endpoints — Google does not propagate the caller's identity. Use a **shared secret** instead:

```javascript
// doPost
var expected = PropertiesService.getScriptProperties().getProperty('WEBAPP_SECRET');
if (!expected || payload.secret !== expected) {
  return ContentService.createTextOutput('unauthorized');
}
```

### Org policy requirement

Web App access must be set to **"Anyone"** — not "Anyone within org". When set to org-restricted, Google enforces SSO on all incoming requests including those from `UrlFetchApp`, returning HTTP 401 regardless of any auth header sent.

This is an **org admin setting**, not a script setting. The deploying admin must change it in the deployment configuration.

### URL self-registration and normalization

On Google Workspace org accounts, `ScriptApp.getService().getUrl()` may return an org-specific URL format (`/a/<org>/macros/`) that differs from the standard form. Normalize in `doGet` and store in script properties:

```javascript
function doGet(e) {
  var url = ScriptApp.getService().getUrl();
  url = url.replace(/https:\/\/script\.google\.com\/a\/[^\/]+\/macros\//, 'https://script.google.com/macros/');
  PropertiesService.getScriptProperties().setProperty('WEBAPP_URL', url);
  return ContentService.createTextOutput('WEBAPP_URL registered: ' + url);
}
```

This eliminates manual URL copy-paste after each redeployment.

### urlFetchWhitelist — org URL variants

If the whitelist must cover org-specific URL forms (e.g., before normalization is in place), add all variants:

```json
"urlFetchWhitelist": [
  "https://script.google.com/a/macros/<orgdomain>/s/",
  "https://script.google.com/a/<orgdomain>/macros/s/",
  "https://script.google.com/macros/s/"
]
```

### Stable deployment URLs

Use `clasp deploy -i <deploymentId>` to redeploy in-place. The URL never changes across pushes; only the internal version number increments. Discover deployment IDs programmatically by matching an anchor string in the deployment description (e.g., `TEST-WEB-APP`).
```

---

## Task 4 — Update Minimum npm Scripts section in workspace-addon-setup.md

Replace the existing "Minimum npm Scripts" section (references old `cd src/addon` pattern) in both copies with:

```markdown
## Minimum npm Scripts

```json
"scripts": {
  "push": "clasp push",
  "push:force": "clasp push --force",
  "update-revision": "node update-revision.js",
  "deploy:test": "npm run update-revision && node manage-deployments.js --deploy-test",
  "deploy:prod": "npm run update-revision && node manage-deployments.js --deploy-prod",
  "release:patch": "npm version patch && npm run deploy:prod && node commit-deploy-stamp.js && git push --follow-tags"
}
```

**Notes:**
- `clasp push --force` needed only when clasp 3.x hash cache skips unchanged files
- `manage-deployments.js` discovers deployment IDs by anchor string in description; no hardcoded IDs in scripts
- `commit-deploy-stamp.js` reads `.deploy-metadata.json` written by `manage-deployments.js` and commits `src/Version.js` with deployment metadata
- Add `.deploy-metadata.json` to `.gitignore`
```

---

## Task 5 — Create ADR: single-script dual-architecture

Create `/mnt/c/dev/GActionSheet/knowledge-base/adr/001-single-script-dual-deployment.md`:

```markdown
# ADR-001: Single-script dual-deployment architecture

**Status:** Accepted
**Date:** 2026-05-22

## Context

GActionSheet needs to (a) display a sidebar card in Google Docs as a Workspace Add-on and (b) write to a central ActionSheet spreadsheet that end users do not have direct edit access to. These two goals create an identity boundary: add-ons run as the active user; sheet writes require deployer identity.

Options considered:
1. **Two GAS projects** — separate add-on project and automation project; add-on calls automation Web App. Simpler identity model but doubles deployment surface.
2. **Service account proxy** — add-on calls Sheets API using OAuth2 library + service account credentials stored in script properties. Eliminates Web App but adds credential management complexity.
3. **Single-script dual-deployment** — one project deployed as both Workspace Add-on and Web App; add-on calls its own Web App endpoint via `UrlFetchApp`.

## Decision

Use single-script dual-deployment (option 3).

## Rationale

- One codebase, one `.clasp.json`, one deploy pipeline
- No credential files or OAuth2 library required
- POC verified end-to-end 2026-05-22: add-on → doPost → sheet.appendRow succeeded

## Tradeoffs

- Web App access must be "Anyone" (not org-restricted) — org admin must set this; cannot be controlled in code
- Shared secret is the only viable auth mechanism (Bearer tokens not propagated by Apps Script runtime)
- Both add-on and Web App deployments must be updated in sync on each release
```

---

## Task 6 — Cleanup: commit pending Addon.js change

`src/Addon.js` has an uncommitted change (replaced debug card notification with `Logger.log()`). After all doc tasks are committed, run:

```bash
npm run deploy:test
git add src/Addon.js src/Version.js
git commit -m "fix(addon): replace debug notification with Logger.log in relayPocToSheet"
git push
```

Then close beads issues GTaskSheet-urx (POC verified) and GTaskSheet-ehr (architecture bootstrap complete).
