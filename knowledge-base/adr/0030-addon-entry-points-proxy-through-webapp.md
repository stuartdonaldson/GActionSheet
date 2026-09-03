# ADR-0030: Add-on entry points execute via the Web App proxy, not the Marketplace-pinned binding

**Status:** Accepted
**Date:** 2026-08-30
**Relates to:** ADR-0012 (Web App two-layer auth model — reused unchanged), gts-addon-install-deploy-lag
(bd memory), `gas-workspace-addons/README.md` §"The Marketplace SDK 'Application Configuration'
deployment version is a separate binding per host app" and §"Web App Proxy Pattern (Add-on + Web
App, Single Script)" (GAS-Core best-practices), `docs/OPERATIONS.md` Deployment Model.

## Context

### The incident

2026-08-30, ~00:40 UTC: a "Force Refresh Style" menu click (`menuForceRefreshActiveDoc`,
`src/MenuHandler.js`) against the canonical reference Doc
(`1PYIU022o5dWNhIkyErjUzF6TRg--r4QrH-h-JbPNO-E`, TEST/SIT environment) produced output missing the
`SR Indent`/`Field SR Indent` continuation formatting (`gts-9a4j`, shipped 2026-08-29) and with bold
misapplied to action text and field values.

Axiom confirmed the executing code, not a data problem: every `flush.done`/`sync.forceFlush` entry
for that docId in the incident window carries `version: "0.2.3.37"` — a build from **2026-08-28**.
Every other document flushed in the same window (`00:16`–`00:23` UTC) carries `version: "0.2.3.62"`,
the version actually live on the TEST-WEB-APP deployment (repointed at `2026-08-30T22:11:26Z`,
2.5 hours *before* the incident). Two flushes 23 minutes apart against the reference doc both ran
`0.2.3.37` — not a one-off race, and not something that would have cleared by waiting: the current
revision was already live on the deployment ID the whole time.

### Root cause

`clasp deployments` shows exactly three deployments for this script project: `@HEAD`,
`PROD-WEB-APP @471`, `TEST-WEB-APP @533`. There is no fourth, add-on-specific deployment. The
project is distributed as a Google Workspace Add-on (`appsscript.json` `addOns.docs`:
`homepageTrigger`, `createActionTriggers`, `linkPreviewTriggers`, plus the classic
`DocumentApp.getUi()` menu `onOpen()` installs into any Doc the add-on is installed on) via the GCP
Marketplace SDK. The Marketplace SDK's **Application Configuration** page carries its own field
selecting which Apps Script deployment *version* the add-on's host-app surfaces bind to — a pointer
independent of `clasp`'s deployment ID/version, not kept in sync by `pnpm run deploy:test`/
`deploy:prod` (which only repoint the two named clasp deployments), and easy to forget.
`gas-workspace-addons/README.md` already documents this pointer and one failure mode: it referencing
a **pruned** deployment version, producing outright, visible breakage on the affected host app.

This incident is the same pointer, but the failure mode that doc doesn't yet name: the pinned
version was never pruned — it still exists, still executes, and produces no error. It's just old.
Nothing in this project's tooling checks or bumps this pointer as part of a deploy, so it silently
diverges further from `clasp`'s TEST-WEB-APP/PROD-WEB-APP revision with every redeploy that doesn't
also touch the Marketplace config by hand. The Sheets-side "Action Sync" menu (`menuSync` and the
Setup/Test submenus, `MenuHandler.js`) is unaffected — it's a container-bound script on the tracker
Spreadsheet itself, not reached through the Marketplace SDK binding, so it always runs at HEAD.

### What's already the right shape

Part of this pattern is already built and working. `WorkspaceAddonCard.js`'s `_patchActionStatus`
and `_deleteActionRowFromSheet` already proxy through `UrlFetchApp.fetch(getWebAppUrl(), ...)` with
the `WEBAPP_SECRET` payload field (ADR-0012 Layer 2) and the OAuth Bearer header (Layer 1) to reach
the `patch_action_status`/`delete_action_row` WEBAPP_SECRET-gated routes in `WebApp.js` — the sheet
side of a sidebar status/delete action never runs the sheet-write logic under the add-on binding.

`BUILD_INFO.webappUrl` (`src/Version.js`, `getWebAppUrl()`) is what makes this reliable even from
stale code: it's a fixed `/exec` URL keyed to the deployment ID, and that ID never changes across a
`clasp deploy -i` repoint — only the revision it serves does. So even a menu handler executing a
build from days ago still resolves the *current* webapp endpoint. `WEBAPP_SECRET` is likewise safe
to read from stale code: Script Properties are shared across every deployment of one script project,
not versioned per-deployment, so there's no distribution lag for the secret itself.

What's missing is the **document** half of the same pattern. `menuSyncActiveDoc`,
`menuForceRefreshActiveDoc`, and `menuInsertTrackerActiveDoc` (`MenuHandler.js`) call
`syncDocument()`/`insertTrackerTable()` directly, in-process, under the add-on binding — exactly the
code path that ran stale in the incident. `sidebarSetStatus`'s own `DocumentApp.openById`/scan/
`_flushActionParagraph` sequence (`WorkspaceAddonCard.js`) has the same shape for the doc-mutation
half of a status change, even though its sheet-mutation half already proxies correctly.

A `sync_document` WEBAPP_SECRET-gated route already exists in `WebApp.js` (`_handleSyncDocument`,
added for `gts-366c` specifically because "before this route that path was reachable only from the
Docs menu... i.e. only from a browser") and is covered by `tests/test_force_refresh_route.py`. No
equivalent route exists yet for `insertTrackerTable`.

## Decision

Every add-on-bound entry point that **mutates state** (a Doc's content, the tracker Spreadsheet, or
both) executes that mutation via an authenticated `UrlFetchApp.fetch()` call to the Web App
(`getWebAppUrl()` + `WEBAPP_SECRET`, ADR-0012's existing two-layer model, unchanged) rather than
calling the mutating function in-process. The add-on-bound code that remains — menu registration
(`onOpen`), card construction (`buildHomepageCard` and friends), and the thin handler functions
themselves — only ever needs to change when the *menu/manifest/card surface* changes, which is
exactly the surface the Marketplace SDK pinned-version binding is supposed to gate. Logic changes
(rendering rules, sync behavior, format config) ride the `clasp`-repointed TEST-WEB-APP/PROD-WEB-APP
deployment instead, which this project already redeploys and verifies over-the-wire on every push
(`manage-deployments.js`).

This extends the pattern `_patchActionStatus`/`_deleteActionRowFromSheet` already established to the
document-mutation half of the same entry points, rather than introducing a new one.

**In scope (state-mutating, currently direct, converts to a proxy call):**

- `menuSyncActiveDoc`, `menuForceRefreshActiveDoc` (`MenuHandler.js`) → `sync_document` route
  (exists).
- `menuInsertTrackerActiveDoc` (`MenuHandler.js`), `onInsertTrackerTable`/`onSyncNow`'s
  tracker-insert call, `sidebarSetStatus`'s `if (hasTracker) insertTrackerTable(docId)`
  (`WorkspaceAddonCard.js`) → a new `insert_tracker_table` route (does not exist yet — new
  WEBAPP_SECRET-gated handler + twin-ticket `[TST]`, per this project's ATDD convention).
- `sidebarSetStatus`'s doc-scan-and-flush half (`_flushActionParagraph` call,
  `WorkspaceAddonCard.js`) → folds into `sync_document` or a dedicated route; the doc-read used to
  build the flush payload (current action text/runs/customFields) either moves server-side too, or
  the route accepts a client-supplied snapshot the server re-validates. Left as an implementation
  decision, not fixed by this ADR — see "Not decided here" below.

**Out of scope (unaffected, no reason to change):**

- The Sheets-context "Action Sync" menu (`menuSync` and the Setup/Test submenus) — a directly
  bound container script, not reached through the Marketplace SDK binding, always runs at HEAD.
- `_patchActionStatus`/`_deleteActionRowFromSheet` — already proxy correctly; unchanged by this ADR.
- Read-only card painting (`buildHomepageCard`'s initial render, card list-building) that doesn't
  mutate anything — no correctness risk from running under a stale pin, only a presentation-lag
  risk, and folding it into this pattern is a much larger lift (moving `DocumentApp`/`CardService`
  response construction server-side). Deferred; not this ADR's problem to solve.

**Not decided here** (left to the implementing bead(s), per this project's twin-ticket convention):

- Whether `sidebarSetStatus`'s doc-scan step moves server-side wholesale, or the client sends a
  snapshot the server treats as advisory input, re-validated against its own scan before flushing.
- Whether a single generalized `run_addon_action` route replaces the growing list of
  one-action-per-route handlers, or the existing one-route-per-action shape (`sync_document`,
  `patch_action_status`, `delete_action_row`, the new `insert_tracker_table`) continues.

## Consequences

- **Fixes the incident class outright.** A menu/card action's actual behavior can no longer diverge
  from what's live on TEST-WEB-APP/PROD-WEB-APP, regardless of how stale the Marketplace SDK's
  pinned deployment version gets, because the pinned version's own code does nothing but dispatch a
  network call to a URL (`BUILD_INFO.webappUrl`) that resolves correctly even when the dispatching
  code itself is old.
- **The Marketplace SDK pin still matters**, but for a much smaller, slower-changing surface: menu
  item labels/registration, `addOns.docs` manifest shape (trigger names, card structure), and
  anything CardService-rendered without a mutation behind it. That surface should still get bumped
  when it changes — this ADR does not remove the need for `gas-workspace-addons/README.md`'s
  existing diagnostic ("check the Marketplace SDK Application Configuration's referenced deployment
  version before suspecting a code regression"), it shrinks how often that pointer actually matters.
- **Added latency per action**: an HTTP round trip (~1–2s observed for `sync_document` today) is
  strictly worse than an in-process call. Menu items and sidebar buttons already show a UI-blocking
  wait for a sync/flush, so this is a magnitude change, not a new category of wait — but error
  handling needs a real user-facing path (toast/alert) for a failed `UrlFetchApp` call, not just an
  uncaught exception, since a network failure is now a normal outcome to design for, not a corner
  case.
- **No new auth surface.** ADR-0012's two-layer model (OAuth Bearer for GAS's own HTTP gate,
  `WEBAPP_SECRET` in the payload for application auth) is reused exactly as-is — this ADR adds
  callers, not a new credential or a new gate.
- **Server-side routes gain callers they weren't originally scoped for.** `sync_document` was built
  for `gts-366c`'s corpus-repair use case (`scripts/apt.py`/pytest); it becomes the add-on's own
  production sync path too. No interface change needed — the payload shape already matches
  (`{secret, action: 'sync_document', docId, force}`) — but its regression coverage
  (`tests/test_force_refresh_route.py`) now protects a live user-facing path, not just tooling, and
  should be treated accordingly when changed.
