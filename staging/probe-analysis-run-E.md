# PROBE Analysis — Run E (Second Account, No Add-on Installed)

**Date:** 2026-06-02  
**Account:** sanctuary@northlakeuu.org (user2, non-deployer, in-domain)  
**Clean runId:** 441f85ad-90c7-4c79-bb3f-e9e9575338b8  
**Stale runId:** 567467e2-b092-4b1f-abee-846635708357 (playwright.config.js bug — page fixture used user1 auth; discard page-based entries)  
**Add-on installation:** None (user2 has no add-on installed)  
**Code:** v0.2.0 — DEV @HEAD (PROBE.js present), TEST @153

---

## Run Issues

### playwright.config.js storageState not respecting PROBE_AUTH_STATE (fixed)

E1 (stale): `playwright.config.js` had `storageState` hardcoded to `user.json`. The `page` fixture used the deployer's auth for all page-navigating tests while `playwright.request` contexts (created explicitly with `storageState`) correctly used user2. Fixed: config now reads `PROBE_AUTH_STATE` env var.

### DriveApp authorization triggered mid-run (E2)

When `menuSync()` → `syncAll()` ran as user2, GAS prompted for authorization (user2 had never run the script before). User approved it. This caused two effects:
1. `PROBE.menu` did not log — `GasLogger.flush()` calls `DriveApp.getFolderById()`, which failed before authorization was granted
2. `PROBE.menu.identity` (the subsequent test) logged correctly — DriveApp was now authorized

`PROBE.menu` from E2 is discarded. `PROBE.menu.identity` is valid. User2's authorization is now stored; future runs will not trigger this prompt.

---

## Clean Data — Run E2

| Surface | eu | au | Notes |
|---------|----|----|-------|
| doGet.dev authed | sdonaldson@northlakeuu.org | **sanctuary@northlakeuu.org** | ✓ identity split confirmed |
| doGet.test authed | sdonaldson@northlakeuu.org | **sanctuary@northlakeuu.org** | ✓ |
| doGet.test unauthed | sdonaldson@northlakeuu.org | (empty) | unchanged from single-user runs |
| doPost.test unauthed | sdonaldson@northlakeuu.org | (empty) | unchanged |
| doPost.dev authed | sdonaldson@northlakeuu.org | **sanctuary@northlakeuu.org** | ✓ |
| doPost.test authed | sdonaldson@northlakeuu.org | **sanctuary@northlakeuu.org** | ✓ |
| sidebar | FAILED — panel icon not found | — | Expected: no add-on installed |
| chipHover | not in DOM | — | Manual only |
| menu — Sync | not logged (DriveApp auth mid-run) | — | Invalid — see above |
| **menu.identity** | **sanctuary@northlakeuu.org** | **sanctuary@northlakeuu.org** | ✓ KEY FINDING — see F-E2 |

---

## Findings

### F-E1: executeAs=USER_DEPLOYING confirmed for WebApp surfaces with non-deployer caller

All four WebApp surfaces (doGet.dev, doGet.test, doPost.dev, doPost.test) show:
- `effectiveUser` = `sdonaldson@northlakeuu.org` (the deployer — unchanged)
- `activeUser` = `sanctuary@northlakeuu.org` (user2 — the actual caller)

This is the definitive confirmation the identity model works. The original Runs A–D finding ("identity invariant") was a false-positive caused by testing only with the deployer account. The true behavior is:

| Context | effectiveUser | activeUser |
|---------|--------------|------------|
| Deployer hits WebApp | deployer | deployer |
| Non-deployer hits WebApp | deployer | **non-deployer** |
| Unauthenticated hits WebApp | deployer | (empty) |

**`executeAs=USER_DEPLOYING` isolates the script's execution identity from the caller's identity.** The script always runs as the deployer regardless of who calls it. The caller's identity is visible in `activeUser` only.

---

### F-E2: Sheets menu triggers run as the ACTIVE USER — executeAs does not apply

`menu.identity` (run by user2 from the Sheet menu):
- `effectiveUser` = `sanctuary@northlakeuu.org`
- `activeUser` = `sanctuary@northlakeuu.org`

**`executeAs=USER_DEPLOYING` is a WebApp deployment setting only.** It has no effect on Sheets-bound script triggers (menu items, onOpen, time-based triggers). Those always run as whoever triggered them. There is no way to use `executeAs` to run menu items as the deployer.

Practical implications:
- GasLogger.flush() in a menu context uses the triggering user's Drive credentials — if that user lacks write access to the log folder, logging silently fails
- `getWebAppUrl()` in a menu context will use `BUILD_INFO.webappUrl` (deployer-stamped) if set, or Script Properties if not — Script Properties are shared, so the value written by the deployer's doGet registration is readable by any user's menu execution
- Any menu item that calls APIs requiring the deployer's permissions (e.g., writing to a protected sheet) needs to POST to the WebApp instead of calling directly

---

### F-E3: Non-deployer can access /dev endpoint

HTTP 200 response from doGet.dev with user2 auth means sanctuary@northlakeuu.org has editor access to the script project (as expected for an org domain where scripts may be shared). The `/dev` endpoint is not restricted to the deployer alone — any editor can access it.

---

### F-E4: Probe doGet calls update WEBAPP_URL as a side effect

Hitting the WebApp doGet endpoint for probe purposes also triggers the WEBAPP_URL self-registration. The test order (doGet.dev first, doGet.test second) leaves `Script Properties['WEBAPP_URL']` = `/exec` URL after test 2. Since `getWebAppUrl()` checks `BUILD_INFO.webappUrl` first (set at `deploy:test` time), this only affects DEV context where BUILD_INFO.webappUrl is empty. In TEST/PROD, sync calls are unaffected. Comment added to the probe code in WebApp.js.

---

## Updated Complete Identity Matrix

| Surface | Deployer (Runs A–D) | Non-deployer, authed (Run E2) | Unauthenticated |
|---------|--------------------|-----------------------------|-----------------|
| doGet.dev | eu=au=deployer | eu=deployer, au=**user2** | 401 — no execution |
| doGet.test | eu=au=deployer | eu=deployer, au=**user2** | eu=deployer, au=(empty) |
| doPost.dev | eu=au=deployer | eu=deployer, au=**user2** | 401 — no execution |
| doPost.test | eu=au=deployer | eu=deployer, au=**user2** | eu=deployer, au=(empty) |
| menu (Sheets) | eu=au=deployer | eu=au=**user2** | n/a |
| sidebar | eu=au=deployer (manual) | not tested (no add-on) | n/a |
| chipHover | eu=au=deployer (manual) | not tested (no add-on) | n/a |

---

## Remaining Open Items

| Item | Status |
|------|--------|
| user2 with add-on installed (Run F) | Not yet run — would confirm sidebar/chipHover identity for non-deployer |
| Marketplace SDK install for user2 | Not yet run |
| Cleanup approval | Pending explicit user sign-off per spec §6 |
