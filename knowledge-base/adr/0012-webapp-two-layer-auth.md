# ADR-0012: Web App two-layer authentication model

**Status:** Accepted
**Date:** 2026-05-30

## Context

`SyncManager.js` calls the GAS Web App endpoint (`WEBAPP_URL`) via `UrlFetchApp.fetch()` for
bidirectional sync (`sync_action_rows`) and error marking (`mark_doc_not_found`). Two separate
auth layers apply to these calls, and confusing them caused a production outage (HTTP 401 on
every sync) when the Bearer token was removed as "dead code" in the 2026-05-29 design review (L3).

### The two layers

**Layer 1 — GAS HTTP auth gate (Bearer token):**
GAS enforces HTTP-level authentication before executing `doPost`. `UrlFetchApp` does NOT carry
the calling script's Google session automatically — the Bearer token must be sent explicitly:

```javascript
var oauthToken = ScriptApp.getOAuthToken();
UrlFetchApp.fetch(webAppUrl, {
  headers: { 'Authorization': 'Bearer ' + oauthToken },
  ...
});
```

Behaviour by deployment type:
- **`/dev` (HEAD deployment):** Always requires a valid Bearer token, regardless of the `access`
  setting in `appsscript.json`. There is no way to make `/dev` anonymous.
- **`/exec` with `access: ANYONE`:** Requires a Google account credential at the HTTP layer.
  Without a Bearer token, GAS returns HTTP 401.
- **`/exec` with `access: ANYONE_ANONYMOUS`:** No credential required. The Bearer token is
  accepted but not needed — including it unconditionally is safe and simplifies the call site.

**Layer 2 — Application auth (shared secret in payload):**
`doPost` checks `WEBAPP_SECRET` against `payload.secret` before executing any handler. This
prevents unauthorized callers from reaching the sync logic even if they pass Layer 1.

### Why Layer 1 was mistakenly removed

The design review found that `doPost` never reads the `Authorization` header (true — Google does
not propagate caller identity through it). The conclusion was that the header is dead code. This
missed the fact that the header satisfies GAS's own auth gate *before* the script runs, not
inside it. The ADR-0007 tradeoff note ("Bearer tokens not propagated by Apps Script runtime")
describes Layer 1's limitation from `doPost`'s perspective, not its non-existence.

### `ANYONE_ANONYMOUS` vs `ANYONE` for `/exec` deployments

This project uses `access: ANYONE_ANONYMOUS` for the versioned TEST/PROD deployments because:
- Automated test infrastructure (Node.js) POSTs to `/exec` to register test tokens. Node.js
  cannot call `ScriptApp.getOAuthToken()`, so Layer 1 must be skipped.
- `WEBAPP_SECRET` (Layer 2) provides sufficient application-level security.
- GAS callers include the Bearer token anyway (it works on anonymous endpoints too).

`access: ANYONE` (requires a Google account) would block the Node.js test path and offers only
marginal additional security given Layer 2 is present.

## Decision

1. Every `UrlFetchApp.fetch()` call to a GAS Web App endpoint includes
   `headers: { 'Authorization': 'Bearer ' + ScriptApp.getOAuthToken() }` unconditionally.
   This satisfies Layer 1 for all deployment types (`/dev`, `/exec` ANYONE, `/exec`
   ANYONE_ANONYMOUS) without requiring call-site knowledge of which URL is in use.

2. `appsscript.json` sets `"access": "ANYONE_ANONYMOUS"` for the Web App deployment so that
   non-GAS callers (automated test infrastructure) can POST to `/exec` without OAuth.

3. `WEBAPP_SECRET` in `doPost` (Layer 2) remains the authoritative application-level auth gate.

## Tradeoffs

- Adding the Bearer token to every proxy call is a minor overhead but eliminates a category of
  auth failures when `WEBAPP_URL` changes deployment type (e.g. `/dev` during development).
- `ANYONE_ANONYMOUS` means any internet client can reach `doPost`. `WEBAPP_SECRET` must therefore
  be kept confidential (stored in Script Properties, never in source).
- The org admin access constraint documented in ADR-0007 ("Anyone, not org-restricted") applies
  equally to `ANYONE_ANONYMOUS` — the org admin must configure this in the deployment settings;
  it cannot be forced by redeploying an existing deployment.
