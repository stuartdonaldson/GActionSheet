# PROBE Manual Data Supplement

**Date:** 2026-06-02  
**runId:** c06dd021-c413-4a22-8934-4c3defc078c3 (last automated run's ScriptProperties still active)  
**Context:** Direct /dev install. User manually opened sidebar, hovered two chips, reloaded sheet, clicked /dev webapp URL.  
**State:** Same code as Runs C & D — v0.2.0 (Rev. Jun 1, 2026 22:28) (TEST)

---

## Data Captured

### PROBE.sidebar.existing — 2026-06-02T08:30:02

```json
{
  "effectiveUser": "sdonaldson@northlakeuu.org",
  "activeUser":    "sdonaldson@northlakeuu.org",
  "version":       "v0.2.0 (Rev. Jun 1, 2026 22:28) (TEST)",
  "webappUrl":     "https://…/AKfycbzVl…/exec",
  "serviceUrl":    "https://…/AKfycbz1lH…/exec",
  "docId":         "1LG5SofIJOH_qs6BbXuDy99pJHpejDYJPj0oqkzhUprI"
}
```

### PROBE.chipHover.existing — 2026-06-02T08:31:10 (AI-10)

```json
{
  "effectiveUser": "sdonaldson@northlakeuu.org",
  "activeUser":    "sdonaldson@northlakeuu.org",
  "version":       "v0.2.0 (Rev. Jun 1, 2026 22:28) (TEST)",
  "serviceUrl":    "https://…/AKfycbz1lH…/exec",
  "matchedUrl":    "https://northlakeuu.org/NUTS/action?c=view&globalId=1LG5SofI…%2FAI-10",
  "globalId":      "1LG5SofIJOH_qs6BbXuDy99pJHpejDYJPj0oqkzhUprI/AI-10"
}
```

### PROBE.chipHover.existing — 2026-06-02T08:31:29 (AI-5)

```json
{
  "effectiveUser": "sdonaldson@northlakeuu.org",
  "activeUser":    "sdonaldson@northlakeuu.org",
  "serviceUrl":    "https://…/AKfycbz1lH…/exec",
  "matchedUrl":    "https://northlakeuu.org/NUTS/action?c=view&globalId=1LG5SofI…%2FAI-5",
  "globalId":      "1LG5SofIJOH_qs6BbXuDy99pJHpejDYJPj0oqkzhUprI/AI-5"
}
```

### PROBE.doGet — 2026-06-02T08:35:35 (user clicked /dev webapp URL directly)

```json
{
  "effectiveUser": "sdonaldson@northlakeuu.org",
  "activeUser":    "sdonaldson@northlakeuu.org",
  "serviceUrl":    "https://…/AKfycbyeJ…/dev",
  "queryString":   "",
  "parameter":     "{}",
  "pathInfo":      ""
}
```

---

## Findings

### FM-1: sidebar and chipHover identity confirmed — matches all other surfaces

Both previously uncollected surfaces now have data. Identity is identical across every
surface in the entire probe run series:

| Surface | effectiveUser | activeUser |
|---------|--------------|------------|
| doGet.dev | donor | donor |
| doGet.test | donor | donor |
| doPost.dev | donor | donor |
| doPost.test | donor | donor |
| menu | donor | donor |
| **sidebar** | **donor** | **donor** |
| **chipHover** | **donor** | **donor** |

*donor = sdonaldson@northlakeuu.org*

The identity model is now complete across all seven surfaces. No surface produces a
different result.

---

### FM-2: All add-on trigger surfaces share the mystery serviceUrl

sidebar, chipHover, and menu all report `serviceUrl = …/AKfycbz1lH…/exec`.
This is now confirmed across three distinct surface types. The mystery deployment
(`AKfycbz1lH…`) is returned by `ScriptApp.getService().getUrl()` in every add-on
trigger context regardless of which surface fires it. This is distinct from the
WebApp endpoints (DEV `AKfycbyeJ…`, TEST `AKfycbzVl…`).

---

### FM-3: chipHover matchedUrl confirms new query-param format is working

Both chip hovers matched URLs in the correct format:
`https://northlakeuu.org/NUTS/action?c=view&globalId=<encoded>`

The `onLinkPreview` trigger fired, `_globalIdFromChipUrl()` correctly decoded the
globalId, and PROBE_log received the right values. The URL format change from Run A
is working end-to-end.

---

### FM-4: WEBAPP_URL updated to /dev by direct click — operationally safe

Clicking the /dev webapp URL caused `doGet()` to update `Script Properties['WEBAPP_URL']`
to the /dev URL (it was previously the /exec URL). However:

```javascript
function getWebAppUrl() {
  if (BUILD_INFO.webappUrl) return BUILD_INFO.webappUrl;  // ← takes this path
  return PropertiesService.getScriptProperties().getProperty('WEBAPP_URL');
}
```

`BUILD_INFO.webappUrl` is set to the /exec URL at `deploy:test` time and is non-empty.
`getWebAppUrl()` returns it unconditionally, never reaching Script Properties. **Sync
and all WebApp POST calls are unaffected.**

The Script Properties `WEBAPP_URL` is now stale (points to /dev). It will self-correct
on the next `doGet` hit on the /exec URL. No manual remediation needed.

---

### FM-5: Sidebar panel icon IS visible with direct /dev install — Playwright selector is stale

The user opened the sidebar successfully via the panel icon with the /dev install active.
Our Playwright automation fails with `[aria-label="Action Sync"]` — this aria-label is
no longer present in the current Google Docs UI. The add-on does NOT appear in the
Extensions menu (confirmed by user inspection). It appears only as a panel icon in the
right-side column.

The Extensions menu fallback added to `addon_helpers.js` should be removed or replaced
with a correct panel icon selector. The selector needs to be identified from the live
DOM (e.g. via browser devtools while the panel is visible).

---

## Complete Identity Matrix — All Surfaces, All Runs

| Surface | A | B | C | D | Manual |
|---------|---|---|---|---|--------|
| doGet.dev authed | eu=au=✓ | eu=au=✓ | eu=au=✓ | eu=au=✓ | — |
| doGet.test authed | — | eu=au=✓ | eu=au=✓ | eu=au=✓ | — |
| doGet unauthed | — | eu=✓,au=∅ | eu=✓,au=∅ | eu=✓,au=∅ | — |
| doPost authed | eu=au=✓ | eu=au=✓ | eu=au=✓ | eu=au=✓ | — |
| doPost unauthed | — | — | eu=✓,au=∅ | eu=✓,au=∅ | — |
| menu | eu=au=✓ | eu=au=✓ | eu=au=✓ | eu=au=✓ | eu=au=✓ |
| sidebar | — | — | — | — | **eu=au=✓** |
| chipHover | — | — | — | — | **eu=au=✓ ×2** |

✓ = sdonaldson@northlakeuu.org, ∅ = empty string

**All surfaces confirmed. Identity is fully invariant across all deployment configurations,
install sources, and code versions tested.**

---

## Remaining Open Items

1. **Fix Playwright panel icon selector** — find correct aria-label or role for the add-on panel icon in current Google Docs UI; update `addon_helpers.js`
2. **Multi-user identity** — all runs used the same Google account; a second user's `activeUser` is still untested
3. **Cleanup approval** — awaiting user sign-off per spec §6
