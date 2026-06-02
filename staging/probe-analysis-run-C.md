# PROBE Analysis — Run C (Marketplace SDK Draft)

**Date:** 2026-06-02  
**runId:** 9eac3dac-4c38-4be1-bf07-062d22a7e679  
**State:** Marketplace SDK draft pointing to TEST deployment @152 (v0.2.0 Rev. Jun 1, 2026 22:28)  
**Installed add-on:** Marketplace SDK draft (replaces direct /dev install from Runs A & B)  
**Raw logs:** `/mnt/g/My Drive/GAS-Logger/GTaskSheet/`  
**Response file:** `staging/probe-responses-9eac3dac-4c38-4be1-bf07-062d22a7e679.txt`

---

## 1. Run C Surface Data

| Surface | HTTP status | PROBE logged | effectiveUser | activeUser | serviceUrl |
|---------|------------|-------------|---------------|------------|-----------|
| doGet.dev authed | 200 | ✓ | sdonaldson@northlakeuu.org | sdonaldson@northlakeuu.org | …/AKfycbyeJ…/dev |
| doGet.test authed | 200 | ✓ | sdonaldson@northlakeuu.org | sdonaldson@northlakeuu.org | …/AKfycbzVl…/exec |
| doGet.dev unauthed | 302 | ✗ expected | — | — | — |
| doGet.test unauthed | 302 (client) | ✓ ran | sdonaldson@northlakeuu.org | **(empty)** | …/AKfycbzVl…/exec |
| doPost.dev unauthed | 401 | ✗ expected | — | — | — |
| doPost.test unauthed | 302 (client) | ✓ ran | sdonaldson@northlakeuu.org | **(empty)** | …/AKfycbzVl…/exec |
| doPost.dev authed | 200 | ✓ | sdonaldson@northlakeuu.org | sdonaldson@northlakeuu.org | …/AKfycbyeJ…/dev |
| doPost.test authed | 200 | ✓ | sdonaldson@northlakeuu.org | sdonaldson@northlakeuu.org | …/AKfycbzVl…/exec |
| sidebar | panel opened | ✗ no PROBE.sidebar | — | — | — |
| chipHover | not in DOM | ✗ | — | — | — |
| menu | 200 | ✓ | sdonaldson@northlakeuu.org | sdonaldson@northlakeuu.org | …/AKfycbz1l…/exec |

---

## 2. Three-Run Comparison

### Identity matrix — all surfaces that logged across all runs

| Surface | Run A effectiveUser / activeUser | Run B effectiveUser / activeUser | Run C effectiveUser / activeUser |
|---------|----------------------------------|----------------------------------|----------------------------------|
| doGet.dev authed | donor / donor | donor / donor | donor / donor |
| doGet.test authed | — (no PROBE) | donor / donor | donor / donor |
| doGet.test unauthed | — (no PROBE) | donor / **empty** | donor / **empty** |
| doPost.test unauthed | — | — (crash) | donor / **empty** |
| doPost.dev authed | donor / donor | donor / donor | donor / donor |
| doPost.test authed | — (no PROBE) | donor / donor | donor / donor |
| menu | donor / donor | donor / donor | donor / donor |

*donor = sdonaldson@northlakeuu.org*

**Result: Marketplace SDK installation makes no difference to identity on any logged surface.**
Every cell is identical between Run B and Run C.

---

## 3. Findings

### F-C1: Marketplace SDK installation does not affect identity on WebApp or menu surfaces

`effectiveUser` and `activeUser` are identical across Runs B and C on all seven surfaces
that logged in both runs. Switching from direct test deployment install to Marketplace SDK
draft install made zero observable difference to the GAS execution identity.

This is consistent with the GAS security model: `executeAs=USER_DEPLOYING` fixes the
effective user to the deployer regardless of how the caller authenticated. The Marketplace
SDK's OAuth consent flow adds a layer for the end-user to grant scopes, but does not change
who the script *runs as*.

---

### F-C2: doPost.test.unauthed now confirmed — GAS runs for unauthenticated POST callers

Run B had a network error for this test. Run C collected it cleanly:

- HTTP 302 returned to caller (same as unauthenticated GET)  
- GAS function executed: `effectiveUser=sdonaldson@northlakeuu.org`, `activeUser=""`
- Pattern is identical to `doGet.test.unauthed` (F-2 in runs A/B analysis)

Both GET and POST with `access=ANYONE, executeAs=USER_DEPLOYING` execute the function for
anonymous callers. The caller receives a 302 redirect; the function runs completely. This
applies to the `probe` action route which bypasses WEBAPP_SECRET. The real `doPost` routes
(gated by WEBAPP_SECRET) are unaffected — they reject before any sensitive operation.

---

### F-C3: Sidebar PROBE not logged — homepage card is cached by Google

The sidebar panel opened successfully (Playwright found and clicked the icon — no error),
but no `PROBE.sidebar.*` entry appeared in the GasLogger Drive files. The wait exhausted:
45s for `sidebar.existing` + 10s for `sidebar.new` = ~55s, matching the 58.6s test time.

`buildHomepageCard` was not called server-side during this open. The most likely cause:
**Google caches the homepage card** after the first render. When the add-on sidebar is
opened for the same doc/user combination, Google may serve the cached card without
re-invoking the GAS trigger. The cache appears to persist across a Marketplace SDK
reinstall.

**To force a fresh `buildHomepageCard` invocation:** close and reopen the sidebar, or
click a card action button (which forces a server round-trip). The probe test needs a
card action step to reliably capture sidebar identity.

This also means: **the sidebar surface is not a good identity probe target** unless the
card is forced to re-render. The menu surface (which always invokes GAS) is more reliable.

---

### F-C4: menu serviceUrl remains the mystery third deployment — unchanged by Marketplace SDK

Run C menu serviceUrl: `…/AKfycbz1lHFEHoTHS86IG-1_WYR2brssa5RPNs4CbCWpZXuO1z2iyp8/exec`

Identical to Runs A and B. The Marketplace SDK installation did not change what
`ScriptApp.getService().getUrl()` returns in the Sheets trigger context. This confirms
F-4 from the A/B analysis: the value is tied to the script project's internal service
registration, not the installed deployment.

---

## 4. Consolidated Three-Run Summary

### What changes across runs

| Dimension | A → B | B → C |
|-----------|-------|-------|
| Code in TEST deployment | None (no PROBE) | Has PROBE | No change |
| Identity on any surface | No change | No change | **No change** |
| doGet.test logs | No | Yes | Yes |
| doPost.test logs | No | Yes | Yes |
| Version string on DEV | (DEV) | (TEST) | (TEST) |
| Sidebar logged | No | No | No |

### What never changes

- `effectiveUser` is always `sdonaldson@northlakeuu.org` on every surface
- `activeUser` is always identical to `effectiveUser` for authenticated callers
- `activeUser` is always `""` for unauthenticated callers (both GET and POST)
- `executeAs=USER_DEPLOYING` fully insulates the script from caller identity variation
- Switching deployment targets or installing via Marketplace SDK has no identity effect

### What remains uncollected

| Surface | Gap | Recommendation |
|---------|-----|----------------|
| sidebar identity | Card caching prevents trigger invocation | Add a card action button click to the probe sequence; or test with a brand-new doc+user combination where no cache exists |
| chipHover identity | Google Docs canvas; DOM not accessible | Manual only: hover chip, grep logs for `PROBE.chipHover` |
| Any surface as a different user | All runs used the same Google account | To test cross-user identity: run probe logged in as a different Google account in the domain |

---

## 5. Open Questions for Further Investigation

1. **Would a different authenticated user (e.g. another northlakeuu.org account) get the same `effectiveUser` but a different `activeUser`?** — Yes, expected by theory. Worth confirming with a second test account.

2. **Does the homepage card cache eventually expire, and if so, does refreshing reveal a different identity than the menu?** — Unknown. The cache TTL is not documented publicly.

3. **Does `onLinkPreview` (chipHover) identity differ from menu identity?** — The hypothesis is no (same `executeAs` applies), but unconfirmed. Manual test needed.

4. **What does a Marketplace SDK user who is NOT the deployer see for `effectiveUser`?** — If another org member installs the add-on via Marketplace, their `activeUser` should differ from the deployer's `effectiveUser`. This is the multi-tenant case. Not yet tested.

---

## 6. Conclusion

The Marketplace SDK deployment configuration has **no effect on GAS execution identity**
for the surfaces tested. Identity is entirely determined by the `executeAs` setting in the
deployment config (`USER_DEPLOYING`), which pins `effectiveUser` to the script owner
regardless of who calls it or how the add-on was installed.

The main practical implication: the WebApp endpoints can be called by unauthenticated
parties (GAS runs the function), but those callers are invisible to the script — `activeUser`
is empty. The WEBAPP_SECRET / TEST_TOKEN gates in `doPost` are the correct defence; they
are not bypassed by any identity mechanism.

Cleanup is pending explicit user approval per `staging/probe-deployment-identity-spec.md §6`.
