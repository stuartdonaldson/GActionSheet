# Google Workspace Add-on Setup Guide

Reusable reference for setting up, testing, and architecting Google Workspace Add-ons (new-style, `addOns` manifest).
Last updated: 2026-05-22 (GActionSheet project, sdonaldson@northlakeuu.org, stuart.donaldson@gmail.com).

---

## Add-on Types

| Type | Manifest key | Notes |
|------|-------------|-------|
| Editor Add-on (old) | `addon` | Simpler setup, deprecated path |
| **Workspace Add-on (new)** | `addOns` | This guide covers this type |

---

## UI Location & Visibility

**New-style Workspace Add-on surfaces (`homepageTrigger` cards, `universalActions`) do not reliably appear in the top Extensions menu dropdown.** They are designed to appear as custom icons in the vertical side panel on the far-right edge of the host application (Gmail, Docs, Calendar, etc.), and that is the surface to build a fallback entry point around — see "universalActions not appearing" below.

- **Collapsed panel gotcha:** The right-side panel is often collapsed by default. To reveal it, click the tiny chevron (`<` / "Show side panel") in the absolute **bottom-right corner** of the screen.
- **Extensions > Add-ons > Get add-ons / Manage add-ons** is a Marketplace storefront shortcut only — installing from there still routes Workspace Add-ons to the side panel, not the Extensions menu. A greyed-out **"View document add-ons"** entry alongside those two is normal/expected, not a misconfiguration signal.
- **+ Button Illusion:** The `+` button on the right side panel also opens the Marketplace storefront. It cannot be used to install a test deployment by ID — that must be done from the Apps Script editor (Deploy → Test deployments → Install).

### What *does* legitimately show up under Extensions — and why it's easy to mistake for the add-on

A **container-bound script's legacy `onOpen()` simple trigger** (`SpreadsheetApp.getUi().createMenu(...)` / `DocumentApp.getUi().createMenu(...)`) is a *different* mechanism from the new-style `addOns` manifest, but current Google Workspace UI nests its output **under the Extensions dropdown** (as `Extensions > <Your Menu Name> > items...`), not as its own top-level menu bar entry the way older Google Workspace UI used to render it. Google also auto-appends a generic **`Help`** item after your own menu items in that submenu — you did not add it, and it links to generic script help, not anything in your code.

**This is easy to confuse with the new-style add-on surface not working, especially when the project is bound to one host but installed as an add-on on another:** a script can be container-bound to e.g. a Google **Sheet** while also being configured (via `addOns.docs`) as an installable add-on for **Docs**. When installed on a Doc, Google invokes that same script's `onOpen(e)` simple trigger too — as part of the add-on's editor lifecycle — even though the script isn't bound to that Doc. The result: a legacy bound-script menu (e.g. "Action Sync") shows up correctly under a Doc's Extensions menu, which looks like confirmation the add-on install is fully working — but it proves nothing about whether `homepageTrigger`/`universalActions` (the actual new-style add-on surfaces) are reachable at all. Check those independently, in the side panel, not by inference from the legacy menu appearing.

### `universalActions` not appearing under Extensions — build a card fallback

Manifest-declared `addOns.common.universalActions` entries are *supposed to* surface via the add-on's own entry point (side panel card overflow, or `Extensions > Add-ons > <Add-on Name>` on some hosts), separately from the legacy bound-script menu above. In practice, on at least one test-install configuration (GActionSheet, 2026-08), these entries did not appear anywhere in the Extensions menu at all, and it was never conclusively root-caused whether that requires additional Marketplace SDK configuration beyond a correct `appsscript.json`.

**Don't block a feature's usability on resolving that.** Add a `CardService` button (or button set) directly to the add-on's `homepageTrigger` card as a fallback entry point that calls the same handler function the `universalActions` entry points at. The side panel card is the one surface confirmed to work reliably across configurations; treat `universalActions` as a bonus surface, not the primary one, until proven otherwise in your specific install.

### The Marketplace SDK "Application Configuration" deployment version is a separate binding per host app — and it's easy to break silently

The GCP Marketplace SDK's **Application Configuration** page has its own explicit field selecting *which Apps Script deployment version* the Workspace apps (Docs, Sheets, etc.) are bound to. This is **not** the same thing as `clasp`'s deployment ID/version, and it is **not** automatically kept in sync with it — it's a separate pointer you set (and can forget you set) in the GCP console.

If that pointer references a deployment version that no longer exists (e.g. it was deleted/pruned via `clasp deployments` cleanup, or a new versioned deployment was cut and the old one removed), the practical symptom is **partial, asymmetric breakage**: surfaces that route through the Marketplace SDK binding (the new-style add-on's homepage card, universal actions) can stop working for the affected host app(s), while surfaces that don't depend on that binding (a bound-script's own `onOpen()` menu, since it fires via direct container binding/editor-add-on install lifecycle rather than through the Marketplace SDK config) **keep working fine**. This asymmetry — "the doc side is broken but the sheet side is fine" or vice versa — looks exactly like a code regression between two host-app configs (`addOns.docs` vs `addOns.common`) and can send you bisecting commits for a problem that isn't in the code at all.

**Diagnostic:** if one host app's add-on surface (say, Docs) stops working while the same code's other surface (say, the Sheets container-bound menu) keeps working, check the Marketplace SDK Application Configuration's referenced deployment version *before* suspecting a manifest/code regression — confirm it still exists and points at a current deployment, not a pruned one.

---

## GCP Setup — Required APIs

Enable all of these in the GCP project linked to the Apps Script project:

| API | When needed |
|-----|-------------|
| Google Workspace Add-ons API | Always — without it, test deployments install silently and never appear in the right-side panel |
| Apps Script API | Always |
| Google Workspace Marketplace SDK | Only for publishing (domain-wide install via Admin Console) |
| Google Drive API | If using DriveApp / GasLogger |
| Google Docs API | If using Docs REST API (batchUpdate, namedRanges) |

**Gotcha:** Workspace Add-ons API not being enabled is the most common silent failure. The test deployment installs without error but never shows in the right-side panel.

---

## GCP OAuth Consent Screen

- **Internal** — for Google Workspace org accounts. No test users needed. All org users are automatically included. No "Testing" status shown.
- **External** — for personal Gmail accounts or cross-domain testing. Add test users explicitly. Shows "Testing" status.

For development against a personal Gmail account, use External + add the Gmail address as a test user.

---

## Users vs. Service Accounts (Data Access Control)

Workspace Add-ons enforce a split identity model depending on the execution context:

### 1. User Identity (Default)
The add-on runs strictly under the identity of the active user. It can only view or modify resources that user has permission to access. Boundaries are controlled via the `oauthScopes` array in `appsscript.json`.

### 2. Service Account Proxy (Admin/Hidden Resources)
If the add-on needs to read or write a centralized master resource (e.g., a global tracking Sheet) that regular users must not see or edit, standard calls like `SpreadsheetApp.openById()` will fail — they run as the active user. Instead, implement an **OAuth2 Service Account Proxy** that processes backend calls as a background robot identity.

---

## Secure Data Logging via Service Account Proxy

To log add-on metrics to a hidden master sheet without exposing it to end users:

### Step 1: Provision the Service Account (GCP Console)
1. Navigate to your linked GCP project → IAM & Admin → Service Accounts.
2. Create a service account (e.g., `addon-logger@yourorg.iam.gserviceaccount.com`).
3. Click the account → Keys → Add Key → Create new key (JSON). Download and store the file securely.

### Step 2: Share and Store Credentials
1. Open the master logging Sheet. Click Share and add the service account email as an **Editor**.
2. Apps Script Editor → Project Settings (gear icon) → Script Properties. Add two properties:
   - `SERVICE_ACCOUNT_EMAIL` — the service account email
   - `PRIVATE_KEY` — the full key block from the JSON file, including `-----BEGIN PRIVATE KEY-----` wrapper strings

### Step 3: Script & Manifest Integration

Add the external fetch scope to `appsscript.json`:
```json
"oauthScopes": [
  "https://www.googleapis.com/auth/script.external_request"
]
```

Install the **OAuth2 for Apps Script** library (library ID: `1B7FSrk5Zi6L1rSxxTDgDEUsPzlukDsi4KGuTMorsTQHhGBzBkMun4iDF`). Then implement the proxy:

```javascript
function logInternalMetrics(userAction) {
  const service = getProxyService_();
  if (!service.hasAccess()) {
    console.error('Service Account Auth Failure: ' + service.getLastError());
    return;
  }
  const spreadsheetId = 'YOUR_HIDDEN_MASTER_SPREADSHEET_ID';
  const range = 'Sheet1!A:C';
  const url = `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${range}:append?valueInputOption=USER_ENTERED`;
  const payload = {
    values: [[new Date().toISOString(), Session.getActiveUser().getEmail(), userAction]]
  };
  UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + service.getAccessToken() },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
}

function getProxyService_() {
  const props = PropertiesService.getScriptProperties();
  return OAuth2.createService('ProxyLogger')
    .setTokenUrl('https://oauth2.googleapis.com/token')
    .setPrivateKey(props.getProperty('PRIVATE_KEY').replace(/\\n/g, '\n'))
    .setIssuer(props.getProperty('SERVICE_ACCOUNT_EMAIL'))
    .setPropertyStore(props)
    .setScope('https://www.googleapis.com/auth/spreadsheets');
}
```

---

## clasp Setup Pitfalls

### Creating a project in a subdirectory
`clasp create` walks up the directory tree looking for `.clasp.json`. If one exists in a parent directory, it refuses with "Project file already exists."

**Fix:** Temporarily rename the parent `.clasp.json`, run `clasp create`, then restore it.
```bash
mv ../.clasp.json ../.clasp.json.bak
clasp create --type standalone --title "My Add-on"
mv ../.clasp.json.bak ../.clasp.json
```

### appsscript.json gets overwritten
`clasp create` replaces the local `appsscript.json` with a bare default (no `addOns`, no scopes).

**Fix:** Always restore your custom manifest immediately after `clasp create`. Commit the correct manifest before running `clasp create` so you can diff/restore easily.

### First push after create may skip
`clasp push` sometimes reports "Skipping push" on the first push because it thinks nothing changed.

**Fix:** Use `clasp push --force` after `clasp create`.

### oauthScopes required for versioned deployments
`clasp deploy` (versioned) fails with:
> For Google Workspace Add-ons, you must provide an explicit list of OAuth scopes in the manifest file

`oauthScopes` must be present in `appsscript.json` for any versioned deployment. HEAD deployments don't enforce this but can't be used in the Marketplace SDK.

### Create deployments AFTER linking the GCP project
Deployments created before the GCP project is linked may be tagged to the old default project. The Marketplace SDK will then return:
> Project Key is not associated with the current project or the script version doesn't exist.

**Fix:** Link the GCP project in Apps Script Project Settings first, then run `clasp deploy`.

---

## logoUrl — Static Asset Hosting

The `logoUrl` must resolve to a direct public image URL (not an HTML viewer page).

### Option A: GitHub Pages (recommended)

With the repository public and GitHub Pages enabled (Settings → Pages → master / root):

```
https://<github-user>.github.io/<repo>/assets/logo-128.png
```

Add a `.nojekyll` file at the repo root so Jekyll does not interfere with asset paths. See
ADR-0004 for the full decision rationale.

### Option B: Google Drive (fallback)

Standard Drive sharing links point to an HTML viewer and will fail to load as an icon. Use the
direct image stream format instead:

1. Set the Drive file sharing to "Anyone with the link is a viewer."
2. Extract the File ID from the sharing link.
3. Use this format in `appsscript.json`:
   ```
   https://drive.google.com/uc?export=view&id=YOUR_FILE_ID
   ```

---

## appsscript.json Manifest

Minimum working manifest for a Docs Workspace Add-on:

```json
{
  "timeZone": "America/New_York",
  "dependencies": {},
  "exceptionLogging": "STACKDRIVER",
  "runtimeVersion": "V8",
  "oauthScopes": [
    "https://www.googleapis.com/auth/drive"
  ],
  "addOns": {
    "common": {
      "name": "MyAddOn",
      "logoUrl": "https://<github-user>.github.io/<repo>/assets/logo-128.png",
      "homepageTrigger": {
        "runFunction": "buildHomepageCard"
      }
    },
    "docs": {
      "homepageTrigger": {
        "runFunction": "buildHomepageCard"
      }
    }
  }
}
```

**Notes:**
- `logoUrl` must be a direct public asset URL (see Static Asset Hosting section above).
- Do **not** add `"enabled": true` to `homepageTrigger` — it is undocumented and may cause silent failures.
- Declare `homepageTrigger` in **both** `common` and `docs`. Relying on `common` as fallback for `docs` works in principle but is less reliable.

---

## Testing & Distribution Approaches

### Admin Console Controls for Test Deployments

**Obsolete setting:** The "Developer Preview" checkbox under Marketplace settings no longer exists in the modern Workspace Admin interface. A test deployment successfully installed via its deployment ID is already implicitly allowed.

**Blocked by org API restrictions:** If the org restricts third-party API access and blocks the test deployment, an admin must explicitly trust the app:
1. Admin Console → Security → Access and data control → API controls → Manage Third-Party App Access
2. Click **Add app**, search for the script's GCP **OAuth Client ID**
3. Set the app to **Trusted**

---

### Test Deployments on a Managed Google Workspace Domain

Test deployments may not appear in the right-side panel on managed Google Workspace domains, even when:
- The correct GCP project is linked
- Workspace Add-ons API is enabled
- OAuth consent screen is configured (Internal)
- The test deployment is installed (silently, no auth prompt)
- The manifest has no errors

Root cause: domain-level policy or Workspace Add-on platform behavior that suppresses test deployments for managed accounts. No executions are logged — the trigger never fires.

**Diagnostic steps:**
1. Check Workspace Add-ons API is enabled in GCP
2. Check Admin Console → Apps → Google Workspace Marketplace apps → Settings → allow setting is permissive
3. Check Apps Script Executions log after attempting to open add-on — if empty, trigger never fired
4. Run `buildHomepageCard` manually from editor to confirm code is valid
5. Confirm you are looking in the **right-side panel** (chevron icon, bottom-right) — Workspace Add-ons never appear in the Extensions dropdown
6. If org restricts third-party API access, see Admin Console controls above to trust the OAuth client

---

### Distribution Workflows

#### Option A — Shared Developer Code Bypass (low-friction testing)

Because unpublished test deployments are a developer-only mechanism, sharing them requires granting code access:

1. In the Apps Script editor, click **Share** and grant the tester **Editor** access (required by Google's backend security model).
2. The tester opens the Apps Script project, then Deploy → Test deployments → Install.
3. The add-on binds to their account and appears in the right-side panel across all their documents.

#### Option B — URL Developer Flag (desirable but unverified)

> **Not verified in practice as of 2026-05-22** — documented by Google but could not be made to work. Treat as a fallback to investigate, not a reliable path.

The tester (also an Editor on the script) appends `?add_on_developer_mode=true` to a Google Doc URL and reloads. This is supposed to reveal Extensions → Add-ons → View Document Add-ons, where a test deployment ID can be pasted.

- If that menu option is grayed out, likely cause is multiple Google accounts active in the same browser session — test in a clean Incognito window.

#### Option C — Private Marketplace Publishing (zero-friction production)

If org compliance blocks sharing source code access with testers, route through the Workspace Marketplace SDK. Private internal publishing requires no review cycle:

1. Build a versioned deployment in Apps Script via Deploy → New Deployment. Copy the versioned Deployment ID.
2. GCP Console → Marketplace SDK → set **App Visibility** to **Private (My Organization)**.
3. Because the app is private, Google drops manual evaluation. Placeholder values are accepted:
   - **Legal links:** Paste your org homepage (e.g., `https://northlakeuu.org`) into the Privacy Policy, Terms of Service, and Support URL fields — the validator accepts it.
   - **Graphics:** Upload one screenshot (1280×800) and two square icons (32×32 and 128×128). No banner or additional sizes required.
4. Click **Publish**. The add-on is immediately available for single-click installation via the `+` side panel button for all domain users — no review delay.

**Icon generation** (ffmpeg, when ImageMagick unavailable):
```bash
ffmpeg -i logo.png -vf scale=128:128 logo-128.png -y
ffmpeg -i logo.png -vf scale=32:32  logo-32.png  -y
```

---

## Deployment ID Quick Reference

| Context | Use |
|---------|-----|
| Test deployment (developer only) | HEAD or any deployment ID via Deploy → Test deployments UI |
| Marketplace SDK App Configuration | Versioned deployment only (not HEAD) — created with `clasp deploy --description "..."` |
| Admin Console install | Versioned deployment ID from Marketplace SDK App Configuration |

---

## GCP Infrastructure Multiplexing

### Multiple Apps Script projects per GCP project

**Shared sandbox (allowed):** Multiple distinct Apps Script projects can be linked to a single GCP project. They share the same API configuration, OAuth consent screen, and log outputs, and each auto-generates its own OAuth Client ID. Use this for a central organizational scripting sandbox covering daily tools and test deployments.

**Marketplace publishing (one per GCP):** A single GCP project can only house one instance of the Google Workspace Marketplace SDK. Attempting to configure a second add-on overwrites the first app's deployment parameters.

### Recommended Pattern

| Stage | GCP Project |
|-------|-------------|
| Development & test deployments | One shared sandbox GCP project |
| Internal Marketplace production | Dedicated GCP project per published add-on |

**Project quota note:** Workspace for Nonprofits plans have no domain-level limit on total project creation, but individual admin profiles face a soft starting quota of ~12–30 projects. To expand capacity or avoid continuity risk, route production GCP deployments through a dedicated functional admin account (e.g., `gcp-manager@northlakeuu.org`) rather than an individual employee's mailbox.

---

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
    "common": { },
    "docs": { }
  },
  "urlFetchWhitelist": [
    "https://script.google.com/macros/s/"
  ]
}
```

**`urlFetchWhitelist` is mandatory** for any Workspace Add-on that calls `UrlFetchApp`. Omitting it produces a hard error at call time, not a manifest validation error.

### Authentication

**Two separate auth layers apply to every Web App call:**

**Layer 1 — GAS HTTP auth gate (Bearer token required):**
`UrlFetchApp` does not carry the calling script's Google session automatically. Every `UrlFetchApp.fetch()` to a GAS Web App endpoint must include an explicit `Authorization: Bearer` header, regardless of deployment type:

```javascript
var oauthToken = ScriptApp.getOAuthToken();
UrlFetchApp.fetch(webAppUrl, {
  method:  'post',
  headers: { 'Authorization': 'Bearer ' + oauthToken },
  payload: JSON.stringify({ secret: secret, ... })
});
```

This applies to both `/dev` (HEAD) and versioned `/exec` deployments with `access: ANYONE`. The `/dev` endpoint always enforces this. The `/exec` endpoint with `ANYONE` access also requires a valid Google account credential at the HTTP layer. The `/exec` endpoint with `ANYONE_ANONYMOUS` access does not require it, but including the Bearer token is harmless — add it unconditionally so the same call works against all deployment types.

**`ANYONE_ANONYMOUS` vs `ANYONE` for versioned `/exec` deployments:** `ANYONE_ANONYMOUS` is the better choice when non-GAS callers (e.g. Node.js test infrastructure) need to POST to the endpoint without OAuth. `WEBAPP_SECRET` in the payload provides application-level auth, making the HTTP-layer credential unnecessary for security. `ANYONE` provides one extra layer (requires a Google account) but breaks non-GAS callers that cannot obtain a Bearer token.

Note: the Bearer token satisfies GAS's own auth gate only — `doPost` cannot read it to identify the caller (Google does not propagate caller identity through headers). Application-level auth is handled separately by the shared secret in the payload (Layer 2).

**Layer 2 — Application auth (shared secret in payload):**

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

---

## Minimum `npm` Scripts

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
