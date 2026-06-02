# PROBE Analysis — Run D (Back to Direct /dev Install)

**Date:** 2026-06-02  
**runId:** ee395a03-a194-492c-82dd-3bbd33b0c223  
**State:** Same code as Run C (@152 / v0.2.0 Rev. Jun 1, 2026 22:28 TEST).  
**Change from C:** Uninstalled Marketplace SDK draft; reinstalled direct /dev test deployment.  
**Purpose:** Isolate the effect of install source (Marketplace vs direct) with code held constant.

---

## 1. Run D Surface Data

| Surface | PROBE logged | effectiveUser | activeUser | Notes vs Run C |
|---------|-------------|---------------|------------|----------------|
| doGet.dev authed | ✓ **(×2)** | sdonaldson@northlakeuu.org | sdonaldson@northlakeuu.org | Ran twice — auth redirect double-hit |
| doGet.test authed | ✓ | sdonaldson@northlakeuu.org | sdonaldson@northlakeuu.org | Unchanged |
| doGet.dev unauthed | ✗ expected | — | — | Unchanged |
| doGet.test unauthed | ✓ | sdonaldson@northlakeuu.org | (empty) | Unchanged |
| doPost.dev unauthed | ✗ expected | — | — | Unchanged |
| doPost.test unauthed | ✓ | sdonaldson@northlakeuu.org | (empty) | Unchanged |
| doPost.dev authed | ✓ | sdonaldson@northlakeuu.org | sdonaldson@northlakeuu.org | Unchanged |
| doPost.test authed | ✓ | sdonaldson@northlakeuu.org | sdonaldson@northlakeuu.org | Unchanged |
| sidebar | **FAILED** — icon not found | — | — | **REGRESSION from C** — panel worked in C |
| chipHover | not in DOM | — | — | Unchanged |
| menu | ✓ | sdonaldson@northlakeuu.org | sdonaldson@northlakeuu.org | Unchanged |

---

## 2. Findings

### F-D1: Marketplace SDK install is required for the sidebar panel icon to appear in Google Docs

This is the clearest isolation the probe has produced:

| Install source | Sidebar panel icon visible | PROBE.sidebar logged |
|----------------|--------------------------|---------------------|
| Run A — direct /dev | No | No |
| Run B — direct /dev | No | No |
| Run C — Marketplace SDK draft | **Yes** | No (card cache) |
| Run D — direct /dev (reinstalled) | **No** | No |

Code and deployment revision were identical between C and D (@152). The only variable
was the install source. Conclusion: **the Marketplace SDK installation path registers the
add-on in the Google Docs sidebar panel UI; the direct test deployment path does not.**

The direct test deployment appears only in the Script Editor's "Test deployments" list.
It does not surface the add-on icon in the Docs right-panel column. Users accessing the
add-on via a direct install must use Extensions → [add-on name] → Open rather than the
panel icon.

**Practical implication:** For end users to use the sidebar naturally (panel icon approach),
they must install via the Marketplace listing — even a draft/private listing is sufficient.
The direct /dev install is useful for development but not representative of the user
experience.

---

### F-D2: doGet.dev ran twice — /dev URL triggers an extra auth redirect after reinstall

Run C doGet.dev: 1 PROBE entry, response body = plain GActionSheet text.  
Run D doGet.dev: **2 PROBE entries**, response body = HTML auth-loading page.

The browser navigated to `/dev`, received an HTML auth-loading/redirect response (the
`page.locator('body').textContent()` captured CSS from the loading page), then followed
the redirect back to the same URL — causing a second execution. The GAS function ran
on both legs of the redirect chain. Both executions logged identical identity data.

This extra redirect is specific to the `/dev` endpoint and appears after reinstalling
the test deployment. The `/exec` (TEST) endpoint does not exhibit this — `doGet.test`
produced one entry in both C and D.

**Practical implication:** The `/dev` endpoint is not suitable as a reliable probe seed
point when the auth state is freshly changed. The `/exec` endpoint is more stable. In
future probe runs, consider seeding runId via doPost.test.authed (which is clean and
deterministic) rather than doGet.dev.

---

### F-D3: Identity is fully unchanged by install source switch

Every identity field is identical between Runs C and D on all shared surfaces. Switching
from Marketplace SDK install to direct /dev install — with the same code revision —
produces no change in `effectiveUser`, `activeUser`, `version`, or `serviceUrl`.

Combined with F-C1 (Marketplace install had no identity effect vs direct install in Run B),
the conclusion is now confirmed in both directions: **add-on install source has no effect
on GAS execution identity on any surface this probe can reach.**

---

## 3. Four-Run Consolidated Identity Matrix

All authenticated surfaces across all runs — every cell is sdonaldson@northlakeuu.org
for both effectiveUser and activeUser, except where noted.

| Surface | A | B | C | D |
|---------|---|---|---|---|
| doGet.dev authed | eu=au=donor | eu=au=donor | eu=au=donor | eu=au=donor (×2) |
| doGet.test authed | — (no PROBE) | eu=au=donor | eu=au=donor | eu=au=donor |
| doGet.test unauthed | — | eu=donor, au=**∅** | eu=donor, au=**∅** | eu=donor, au=**∅** |
| doPost.test unauthed | — | — (crash) | eu=donor, au=**∅** | eu=donor, au=**∅** |
| doPost.dev authed | eu=au=donor | eu=au=donor | eu=au=donor | eu=au=donor |
| doPost.test authed | — (no PROBE) | eu=au=donor | eu=au=donor | eu=au=donor |
| menu | eu=au=donor | eu=au=donor | eu=au=donor | eu=au=donor |
| sidebar | — (failed) | — (failed) | — (opened, no log) | — (failed) |

*donor = sdonaldson@northlakeuu.org, ∅ = empty string*

No variation in any identity field across any permutation tested.

---

## 4. What Remains Open

| Question | Status |
|----------|--------|
| sidebar identity (buildHomepageCard) | Uncollected — needs card action step or force-refresh |
| chipHover identity (onLinkPreview) | Uncollected — manual hover required |
| Multi-user: different activeUser from different caller | Not tested — all runs used same account |
| Does Marketplace install change activeUser for a non-deployer user? | Not tested |
