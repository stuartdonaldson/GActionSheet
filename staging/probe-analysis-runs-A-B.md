# PROBE Analysis — Runs A & B

**Date:** 2026-06-02  
**Status:** Complete for Runs A & B. Run C pending Marketplace SDK manual update.  
**Raw logs:** `/mnt/g/My Drive/GAS-Logger/GTaskSheet/` — never delete  
**Run registry:** `staging/probe-runs.md`  

---

## 1. Run Context

| | Run A | Run B |
|-|-------|-------|
| runId | 5ae4eb6c-38ae-4440-bd25-e380df40f465 | 7fb4a13c-4a5a-450f-8d02-cd3e4a783aed |
| DEV deployment | PROBE.js present (just pushed) | PROBE.js present (same) |
| TEST deployment | OLD — no PROBE.js (v0.2.0 Rev. 18:38) | NEW — PROBE.js present (v0.2.0 Rev. 22:28, after deploy:test) |
| Installed add-on | direct /dev | direct /dev (same) |

---

## 2. Raw Surface Data

### Run A (5ae4eb6c)

| Surface | HTTP status | PROBE logged | effectiveUser | activeUser | version | serviceUrl |
|---------|------------|-------------|---------------|------------|---------|-----------|
| doGet.dev authed | 200 | ✓ | sdonaldson@northlakeuu.org | sdonaldson@northlakeuu.org | v0.2.0 (Rev. Jun 1, 2026 22:16) **(DEV)** | …/AKfycbyeJ…/dev |
| doGet.test authed | 200 | ✗ expected | — | — | (old version, no PROBE) | — |
| doGet.dev unauthed | 302 redirect | ✗ | — | — | — | — |
| doGet.test unauthed | 302 redirect | ✗ | — | — | (old version, no PROBE) | — |
| doPost.dev authed | 200 `{"probe":"ok"}` | ✓ | sdonaldson@northlakeuu.org | sdonaldson@northlakeuu.org | v0.2.0 (Rev. Jun 1, 2026 22:16) **(DEV)** | …/AKfycbyeJ…/dev |
| doPost.test authed | 200 `unauthorized` | ✗ expected | — | — | (old version, no PROBE) | — |
| doPost.dev unauthed | 401 | ✗ expected | — | — | — | — |
| doPost.test unauthed | 302 redirect | ✗ | — | — | — | — |
| sidebar | FAILED | ✗ | — | — | — | — |
| chipHover | not in DOM | ✗ | — | — | — | — |
| menu | 200 (menu click) | ✓ | sdonaldson@northlakeuu.org | sdonaldson@northlakeuu.org | v0.2.0 (Rev. Jun 1, 2026 22:16) **(DEV)** | …/AKfycbz1l…/exec ⚠️ |

### Run B (7fb4a13c) — after deploy:test

| Surface | HTTP status | PROBE logged | effectiveUser | activeUser | version | serviceUrl |
|---------|------------|-------------|---------------|------------|---------|-----------|
| doGet.dev authed | 200 | ✓ | sdonaldson@northlakeuu.org | sdonaldson@northlakeuu.org | v0.2.0 (Rev. Jun 1, 2026 22:28) **(TEST)** | …/AKfycbyeJ…/dev |
| doGet.test authed | 200 | ✓ | sdonaldson@northlakeuu.org | sdonaldson@northlakeuu.org | v0.2.0 (Rev. Jun 1, 2026 22:28) **(TEST)** | …/AKfycbzVl…/exec |
| doGet.dev unauthed | 302 redirect | ✗ | — | — | — | — |
| doGet.test unauthed | 302 (client) | ✓ **ran!** | sdonaldson@northlakeuu.org | **(empty)** | v0.2.0 (Rev. Jun 1, 2026 22:28) **(TEST)** | …/AKfycbzVl…/exec |
| doPost.dev authed | 200 `{"probe":"ok"}` | ✓ | sdonaldson@northlakeuu.org | sdonaldson@northlakeuu.org | v0.2.0 (Rev. Jun 1, 2026 22:28) **(TEST)** | …/AKfycbyeJ…/dev |
| doPost.test authed | 200 `{"probe":"ok"}` | ✓ | sdonaldson@northlakeuu.org | sdonaldson@northlakeuu.org | v0.2.0 (Rev. Jun 1, 2026 22:28) **(TEST)** | …/AKfycbzVl…/exec |
| doPost.dev unauthed | 401 | ✗ expected | — | — | — | — |
| doPost.test unauthed | network error | ✗ | — | — | — | — |
| sidebar | FAILED | ✗ | — | — | — | — |
| chipHover | not in DOM | ✗ | — | — | — | — |
| menu | 200 (menu click) | ✓ | sdonaldson@northlakeuu.org | sdonaldson@northlakeuu.org | v0.2.0 (Rev. Jun 1, 2026 22:28) **(TEST)** | …/AKfycbz1l…/exec ⚠️ |

---

## 3. Findings

### F-1: effectiveUser = activeUser = deployer for all authenticated surfaces

Across every surface that logged (doGet.dev, doPost.dev, doPost.test, menu), both users
were identical: `sdonaldson@northlakeuu.org`. This is consistent with the script project
being owned by and deployed by that account, and the current `executeAs=USER_DEPLOYING`
setting. There is no identity distinction between the calling user and the executing user
under this configuration when the caller is authenticated as the same account.

**Implication for Run C:** If the Marketplace SDK installs the add-on under a different
OAuth identity path, we would expect to see this change — particularly `activeUser` might
differ from `effectiveUser`.

---

### F-2: Unauthenticated caller gets empty activeUser; GAS function still runs (access=ANYONE)

`doGet.test.unauthed` (Run B) — client received HTTP 302 redirect, but **GAS did execute
the function**. The PROBE log entry was written. Results:

- `effectiveUser` = `sdonaldson@northlakeuu.org` (deployer — unchanged)
- `activeUser` = `""` (empty — anonymous caller has no identity)

**The 302 redirect is not a function-abort.** The function executes fully (writes to
GasLogger, sets ScriptProperties) and then the Google infrastructure redirects the caller.
Since Node's HTTPS client doesn't follow redirects, we observed 302; a browser following
the redirect would see the actual function output.

This means: **any unauthenticated caller can trigger GAS function execution** under
`access=ANYONE`. The function cannot distinguish whether the caller authenticated or not
via `activeUser` alone — it must inspect the cookie/token actively.

The `/dev` endpoint behaves differently: HTTP 401 for unauthenticated POST (function
did NOT run). The `@HEAD` deployment requires editor-level auth.

---

### F-3: deploy:test makes TEST deployment immediately active; DEV version string updates too

Run A: DEV version = `v0.2.0 (Rev. Jun 1, 2026 22:16) (DEV)`  
Run B: DEV version = `v0.2.0 (Rev. Jun 1, 2026 22:28) (TEST)`

After `npm run deploy:test`, the DEV deployment's version string changed from `(DEV)` to
`(TEST)`. This is because `deploy:test` calls `manage-deployments.js --deploy-test` which
re-stamps `Version.js` with a `(TEST)` suffix **and pushes to @HEAD**. So the DEV
deployment now reports a TEST version string. Both deployments run identical code after
`deploy:test` — the only distinction is the `serviceUrl` (deployment ID).

**Implication:** "DEV" and "TEST" labels in the version string reflect which deploy target
was last pushed — they don't indicate which URL is being served. After `deploy:test`, both
`/dev` and `/exec` endpoints run the same code at the same revision.

---

### F-4: menu serviceUrl is a third, unexpected deployment ID

In both Run A and Run B, `PROBE.menu`'s `serviceUrl` field showed:

```
https://script.google.com/a/northlakeuu.org/macros/s/AKfycbz1lHFEHoTHS86IG-1_WYR2brssa5RPNs4CbCWpZXuO1z2iyp8/exec
```

This deployment ID (`AKfycbz1l…`) does not appear in `clasp deployments` output, which
shows only:
- `AKfycbyeJ…` (@HEAD / DEV)
- `AKfycbyn…` (PROD)
- `AKfycbzVl…` (TEST)

`ScriptApp.getService().getUrl()` in a Sheets-bound trigger context (onOpen/menu) does
not return the WebApp URL of either the DEV or TEST deployment. It appears to return the
URL of a separate internal deployment, possibly the Sheets-bound script's own auto-generated
service endpoint or an older deployment no longer visible in the clasp list.

**Implication:** `ScriptApp.getService().getUrl()` is not a reliable way to determine
"which deployment am I running in" from a menu/trigger context. The deployment ID embedded
in `BUILD_INFO.webappUrl` (stamped at deploy time) is the authoritative identifier.

---

### F-5: All serviceUrls use the org-specific domain path

Every logged `serviceUrl` uses `https://script.google.com/a/northlakeuu.org/macros/s/…`
rather than the canonical `https://script.google.com/macros/s/…`. This is the Google
Workspace domain-scoped URL form. The `doGet()` normalization code already strips this
for `WEBAPP_URL` storage, but `ScriptApp.getService().getUrl()` always returns the
org-scoped form at runtime.

---

### F-6: Sidebar automation requires reinstall after each push

Both Run A and Run B: sidebar test failed with "Action Sync side-panel icon was not
available". The add-on panel icon is registered at install time. After `npm run push`
updates @HEAD, the installed test deployment picks up new code automatically for trigger
execution — but the panel icon registration in the Docs UI requires the user to
Uninstall → Install from Script Editor → Deploy → Test deployments.

This surface requires a **manual step** between code push and probe run, and cannot be
automated in the current harness. The identity data for the sidebar surface (homepage
card / `buildHomepageCard()`) remains uncollected and is the primary gap in this probe.

---

### F-7: chipHover not automatable via Playwright DOM inspection

Google Docs renders link elements in a canvas-based layout; `<a href="northlakeuu.org/…">`
elements were not found via `page.locator('a[href*=...]')`. The `onLinkPreview` trigger
requires a cursor hover inside the Google Docs editor which cannot be driven via DOM
selectors in the current approach. Manual verification is required for this surface.

---

## 4. Run A vs B Diff — What deploy:test Changed

| What changed | Run A | Run B |
|-------------|-------|-------|
| TEST deployment has PROBE.js | No | Yes |
| doGet.test authed → logged | No | Yes |
| doPost.test authed → logged | No | Yes |
| doGet.test unauthed → ran (logged) | — (no PROBE code) | Yes — GAS executed, client got 302 |
| Version string on DEV endpoint | `(DEV)` | `(TEST)` |
| Identity data | Identical | Identical |

**Identity is unchanged by deploy:test.** The `effectiveUser` and `activeUser` values are
the same across all surfaces in both runs. Code version is updated; execution identity is
not affected by which deployment ID is active.

---

## 5. Surfaces Not Yet Captured

| Surface | Reason | How to collect |
|---------|--------|----------------|
| sidebar (buildHomepageCard) | Reinstall required after push | Manual: reinstall, then `npm run probe` |
| chipHover (onLinkPreview) | DOM not accessible via Playwright | Manual: open doc, hover chip, check logs |
| doPost.test unauthed | Network error on 302 (fixed in test) | Re-run probe — bug fixed in test code |
| sidebar + chipHover identity | Not collected | Will also be captured in Run C |

---

## 6. Predictions for Run C (Marketplace SDK installed)

Based on Runs A & B, predictions for when Marketplace SDK draft is installed:

| Question | Predicted | Confidence |
|----------|-----------|------------|
| effectiveUser for WebApp surfaces | Unchanged (still deployer) | High — WebApp executeAs is independent of add-on install |
| activeUser for WebApp surfaces | Unchanged | High |
| effectiveUser for sidebar/menu | May change | Medium — Marketplace OAuth flow may create different session context |
| activeUser for sidebar/menu | May change | Medium — depends on whether Marketplace install changes how Google resolves the caller |
| Version strings | Will match TEST deployment | High |
| serviceUrl for menu | Likely unchanged (still the mystery ID) | Medium |

The most interesting unknown: does the Marketplace SDK draft installation change what
`Session.getActiveUser()` returns in add-on card/trigger contexts (sidebar, chipHover)?
Under direct-install (`/dev`), the active user and effective user are identical. Marketplace
OAuth may surface the real end-user identity differently.

---

## 7. Next Steps

1. **Reinstall add-on** → re-run `npm run probe` → collect sidebar data  
2. **Manual chipHover** → open test doc, hover an AI-1: chip, check log for `PROBE.chipHover.*`  
3. **Update GCP Marketplace SDK** → point SDK config to current TEST deployment (@152)  
4. **Run C** → `npm run probe` → compare against Run B  
5. **Analyze Run C** → add to this document or create `probe-analysis-run-C.md`  
6. **Cleanup** → only after explicit user approval (see spec §6)

---

## 8. Grep Reference

```bash
# All entries for Run A
grep -h '"PROBE\.' *.log | grep '5ae4eb6c'

# All entries for Run B
grep -h '"PROBE\.' *.log | grep '7fb4a13c'

# Compare effectiveUser vs activeUser across all runs
grep -h '"PROBE\.' *.log | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        e = json.loads(line.strip())
        d = e.get('data', {})
        print(e['tag'], d.get('effectiveUser'), d.get('activeUser'))
    except: pass
"
```
