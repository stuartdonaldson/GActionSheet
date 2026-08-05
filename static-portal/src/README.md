# static-portal/src — Team Action Portal (published static frontend)

Source of truth for the team-action portal's static frontend (`gts-79dw.4.25`,
migrated from hand-editing `Static/pub/AS/index.html` directly). Built and
published by `scripts/build-static-portal.js` + `scripts/publish-static-portal.js`,
following the `F3Go30` `tools/build-static-pages.js` / `publish-static-pages.js`
pattern — see those scripts' headers for the stamping/publish mechanics.

- `index.html` — the team portal page. Three placeholders are stamped at build
  time from `src/Version.js`'s `BUILD_INFO` (already stamped by
  `manage-deployments.js`'s `stampVersionInfo` earlier in the same deploy):
  `STATIC_BUILD_VERSION_`, `STATIC_WEBAPP_URL_`, `STATIC_ENV_LABEL_`.
- `privacy/`, `terms/` — OAuth-consent-screen-linked pages for NUUC-Dispatch's
  identity-verification scope (`openid email`, no Drive/Doc access) — carried
  over verbatim from the original spike content, not specific to this page's
  own functionality.
- `icon-{32,48,96,128}.png` — visual identity, copied from GActionSheet's
  `assets/store-details/`.
- `consent-screen-text.md` — the exact text/links pasted into the GCP OAuth
  consent screen form for NUUC-Dispatch.

Published to the sibling `Static` repo (`local.settings.json`'s
`staticPortalRepoPath`) — SIT to `pub/AS-sit/`, PROD to `pub/AS/` — as the
automatic last step of `pnpm run deploy:test` / `pnpm run deploy:prod`. See
`scripts/publish-static-portal.js` for standalone/recovery invocation.
