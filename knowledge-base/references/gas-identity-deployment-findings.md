# GAS Identity & Deployment Behavior — Reference Findings

**Source project:** GActionSheet  
**Date:** 2026-06-02  
**Method:** Automated Playwright probe (PROBE.js) across 9 runs, 2 accounts, 4 deployment states  
**Probe code:** `src/PROBE.js`, `tests/playwright/probe.test.js`

---

## 1. executeAs=USER_DEPLOYING — What It Actually Does

**Setting location:** `appsscript.json` → `webapp.executeAs`  
**Scope:** WebApp deployments only. Has no effect on any other trigger type.

| Surface | effectiveUser | activeUser |
|---------|--------------|------------|
| WebApp doGet/doPost — authenticated caller | Deployer | Caller |
| WebApp doGet/doPost — unauthenticated caller | Deployer | `""` (empty) |
| Sheets menu trigger | Caller | Caller |
| Docs add-on homepage trigger (sidebar) | Caller | Caller |
| Docs add-on linkPreview trigger (chip hover) | Caller | Caller |
| Sheets onOpen simple trigger | (not accessible — see §6) | (not accessible) |

**Key insight:** `executeAs=USER_DEPLOYING` pins `Session.getEffectiveUser()` to the deployer regardless of who calls the WebApp. `Session.getActiveUser()` still reflects the caller on WebApp surfaces. On all non-WebApp surfaces (menu, sidebar, chipHover), both fields reflect the person who triggered the execution — `executeAs` is irrelevant there.

---

## 2. /dev vs /exec Endpoint Differences

| Behaviour | `/dev` (@HEAD) | `/exec` (versioned deployment) |
|-----------|---------------|-------------------------------|
| Unauthenticated GET | 401 — function does NOT run | 302 redirect, but function RUNS |
| Unauthenticated POST | 401 — function does NOT run | 302 redirect, but function RUNS |
| Code version | Always @HEAD (latest push) | Locked to deployment version |
| Access requirement | Script editor access only | Governed by `access` setting |
| Auth redirect on fresh reinstall | Double-fires (auth redirect loop) | Single execution, stable |

**The 302 surprise:** With `access=ANYONE`, unauthenticated callers to `/exec` see an HTTP 302 redirect, but the GAS function **executes fully** before the redirect is issued. `activeUser` is empty but `effectiveUser` is the deployer. Log entries, Script Properties writes, and all other side effects happen. The HTTP client just gets a redirect rather than the response body.

---

## 3. Add-on Panel Icon vs Extensions Menu

| Install method | Panel icon in Docs right column | Appears in Extensions menu |
|---------------|--------------------------------|---------------------------|
| Marketplace SDK (draft or published) | Yes | No |
| Direct test deployment (`/dev` install) | Yes | No |

The add-on panel icon `aria-label` matches `addOns.common.name` in `appsscript.json`. In Playwright automation, derive it from the manifest rather than hardcoding:

```javascript
const manifest = JSON.parse(fs.readFileSync('src/appsscript.json', 'utf8'));
const ADDON_NAME = manifest.addOns.common.name;
page.locator(`[aria-label="${ADDON_NAME}"]`);
```

The add-on does NOT appear in the Google Docs Extensions menu under either install method.

---

## 4. Homepage Card Caching

`buildHomepageCard()` (the Workspace Add-on homepage trigger) is cached by Google after the first render. Subsequent sidebar opens serve the cached card without invoking the GAS trigger. This means:
- Logging inside `buildHomepageCard` will not fire on every open
- Identity instrumentation of the sidebar requires a card action button click to force a server round-trip
- Reinstalling the add-on does NOT clear the cache

---

## 5. ScriptApp.getService().getUrl() in Add-on Trigger Contexts

`ScriptApp.getService().getUrl()` returns different values depending on context:

| Context | Returns |
|---------|---------|
| `doGet` / `doPost` | The URL of the deployment being called |
| Sheets menu, Docs sidebar, chip hover | An internal framework deployment URL (not visible in `clasp deployments`) |

The internal URL is stable within a project lifetime but is not one of the DEV/TEST/PROD deployments you manage. **Do not rely on `ScriptApp.getService().getUrl()` to identify which deployment is running in add-on trigger contexts.** Use a version string stamped into `Version.js` at deploy time instead.

---

## 6. onOpen / Simple Triggers — Identity Not Available

`onOpen` is a simple trigger. Authorized services (`Session.getActiveUser()`, `DriveApp`, etc.) are not available. Identity cannot be captured from simple triggers. Workaround: add a dedicated menu item that calls `PROBE_log()` in an authorized context and invoke it from tests.

---

## 7. OAuth Authorization for Non-Deployer Menu Users

When a non-deployer user runs a Sheets menu item for the first time, GAS shows them an OAuth authorization dialog for the script's requested scopes. Until they approve:
- The script execution is deferred/cancelled
- GasLogger and any other authorized-service calls in that execution will not run
- Any time-sensitive polling (e.g., test waitForLogEntry) may expire during the auth dialog

After authorization is granted once, all subsequent executions run without prompting.

**Note:** Drive folder sharing settings (`anyone with link can edit`) are irrelevant to this. The OAuth gate is at the script scope level, not the file permission level.

---

## 8. WEBAPP_URL Self-Registration

`doGet()` writes `Script Properties['WEBAPP_URL']` to the URL it was called from. `getWebAppUrl()` checks `BUILD_INFO.webappUrl` first (stamped at deploy time into `Version.js`) before falling back to Script Properties.

**Consequence:** If someone hits the `/dev` URL, Script Properties gets updated to the `/dev` URL. This is operationally safe when `BUILD_INFO.webappUrl` is set (which it is after `deploy:test`/`deploy:prod`). It only matters in DEV context where `BUILD_INFO.webappUrl` is empty.

**Best practice:** After each deployment, immediately GET the WebApp URL to trigger self-registration. Automate this in the deploy script:

```javascript
async function pingWebappUrl(url) {
  await fetch(url).catch(() => {});  // side effect: registers WEBAPP_URL
}
// call after clasp deploy -i ...
```

---

## 9. GasLogger in Multi-User Contexts

GasLogger writes to a Drive folder using the executing user's credentials. With `executeAs=USER_DEPLOYING` on WebApp surfaces, all logging uses the deployer's credentials (works reliably). On menu/trigger surfaces, logging uses the triggering user's credentials — they must have authorized the script's OAuth scopes and have write access to the log folder.

Setting the log folder to "anyone with link can edit" ensures write access. OAuth authorization remains a separate gate that each new user must grant once.

---

## 10. Deployment Permutations — Identity Impact Summary

| Change | Identity effect |
|--------|----------------|
| `npm run push` only (DEV) | None |
| `npm run deploy:test` | None |
| Switch Marketplace SDK version | None |
| Reinstall add-on (direct ↔ Marketplace) | None on WebApp/menu; affects panel icon visibility |
| Different caller account | `activeUser` differs on WebApp; both fields differ on menu/triggers |
| Unauthenticated caller | `activeUser` empty on `/exec`; function blocked entirely on `/dev` |

Identity is fully determined by:
1. `executeAs` (WebApp surfaces only)
2. Who triggered the execution (all surfaces)

All other deployment configuration variables have no identity effect.

---

## 11. Probe Infrastructure (Reuse)

The probe implementation can be reused for any GAS project:

| Artifact | Purpose |
|----------|---------|
| `src/PROBE.js` | `PROBE_log(surface, data)`, `PROBE_setRunId()`, `PROBE_getRunId()`, `PROBE_docState()` |
| `tests/playwright/probe.test.js` | Automated surface exerciser; set `PROBE_AUTH_STATE` env var for multi-account runs |
| `npm run probe` | Single-account probe run |
| `npm run probe:test.u2` | Second-account probe run (requires `.auth/test.u2.json`) |
| `staging/probe-runs.md` | Run registry — copy runId before exercising any surface |

Enable/disable: set `PROBE_ENABLED = true/false` in `PROBE.js`. All call sites remain; they become no-ops when disabled.

Cleanup when done: delete `PROBE.js`, remove `// [PROBE]` call sites, remove `probe` action branch from `doPost()`.
