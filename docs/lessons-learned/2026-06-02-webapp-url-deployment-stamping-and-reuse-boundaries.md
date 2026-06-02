# LL: WebApp URL must be deployment-stamped at build time; manual registration is unreliable

Date: 2026-06-02
Domain: platform | deployment | editor-addon

## Observation
`ScriptProperties` is shared across all deployments of the same Apps Script project. The
`WEBAPP_URL` property was originally set by visiting the WebApp URL once after deploy
(`doGet` calls `ScriptApp.getService().getUrl()` and stores it). When switching between test
and prod deployments without re-visiting the new WebApp URL, `WEBAPP_URL` remained stale,
causing `onLinkPreview` to call the wrong (old) endpoint. GCP logs showed `createActionTriggers`
working while link preview appeared broken — the two paths call the WebApp differently and
have different tolerance for a stale URL.

**Resolution: deployment-stamped WEBAPP_URL.**
`manage-deployments.js` knows the WebApp URL at push time (deployment ID is stable;
URL is `https://script.google.com/macros/s/{deploymentId}/exec`). The tool now stamps the URL
directly into `src/Version.js` as `BUILD_INFO.webappUrl` before `clasp push`. The GAS runtime
always has the correct URL baked in without manual registration.

`getWebAppUrl()` resolution order:
1. If `BUILD_INFO.webappUrl` is non-empty → use it (named deployment; URL is authoritative)
2. If empty → fall back to `ScriptProperties.getProperty('WEBAPP_URL')` (DEV / local override)

`npm run push` (DEV HEAD) stamps `(DEV)` suffix and clears the URL. This prevents a stale
`(TEST)` marker and stale URL from persisting after switching back to HEAD development.

**WebApp reuse boundary: `src/Version.js` is environment-specific state after any named deploy.**
After `npm run deploy:test` or `npm run deploy:prod`, `Version.js` contains a live WebApp URL
(environment-specific). Convention: `npm run push` resets it to the DEV/empty state before
pushing. `Version.js` should not be committed with a named URL — it is local state, not a
versioned artifact.

**DEV push constraint: Docs caches the installed add-on version.**
`npm run push` pushes to HEAD but does not redeploy. For the Docs add-on to pick up new code,
the developer must: (1) in Apps Script editor, update the test deployment to point to the latest
version or HEAD; (2) in Google Docs, uninstall and reinstall the test add-on. Hot reload on push
is not supported — this is a Google platform constraint.

## Why Chain

Why 1 — Link preview silently called the wrong WebApp endpoint after a deployment switch.
Why 2 — `ScriptProperties` is shared across all deployments; `WEBAPP_URL` is not
         deployment-scoped by the platform.
Why 3 — Manual URL registration (visit URL → `doGet` self-registers) is a human step that
         is easy to forget when switching between TEST and PROD deployments.
Why 4 — No tooling enforced correct registration; the failure mode (wrong endpoint called) is
         silent — the add-on continues to run, just against the wrong backend version.

Root cause: Deployment-scoped configuration (WebApp URL) was stored in shared script properties
with no enforcement that the value matched the current deployment. Manual registration is
unreliable at scale.

## Guidance (gas-addon-guide.md target)

- **Do not rely on ScriptProperties for deployment-specific configuration** when the same
  script project has multiple deployments. ScriptProperties is shared; a value set by one
  deployment persists for all others.
- **Stamp deployment-specific values at build time** using the deployment tool. If your deploy
  tool knows the WebApp URL (it does — it created the deployment), bake it into a source file
  before push. This is more reliable than any runtime discovery mechanism.
- **The identity-token approach** (`ScriptApp.getIdentityToken()` + JWT claim extraction to
  discover deployment ID at runtime) was investigated and superseded. Do not use it.
- **After every named deploy**, the Marketplace SDK App Configuration must be updated to the
  new version number for `linkPreviewTriggers` to function. Two separate things to update:
  (1) the deployment tool stamps `Version.js` with the URL; (2) GCP Console Marketplace SDK
  must be manually updated to the new version.
- **`npm run deploy:*` is the only supported deploy path.** Running `clasp push` or
  `clasp deploy` directly bypasses `update-revision.js` and `manage-deployments.js`, leaving
  `Version.js` stale and the versioned WebApp deployment pointing to an old revision.

## Initial Candidates

b: add a "WebApp URL and deployment stamping" section to `gas-addon-guide.md` covering the
   shared-ScriptProperties constraint, build-time stamping as the correct pattern, and the
   two manual steps required after every named deploy (Version.js via tooling + SDK version)

b: add a deployment checklist to `OPERATIONS.md` — after `npm run deploy:test` or
   `npm run deploy:prod`: (1) confirm Version.js shows correct URL; (2) update GCP Marketplace
   SDK App Configuration to new version number; (3) in Docs, reinstall the add-on from the
   side panel to pick up the new deployment
