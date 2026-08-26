# static-portal/src — Team Action Portal (published static frontend)

Source of truth for the team-action portal's static frontend (`gts-79dw.4.25`,
migrated from hand-editing `Static/pub/AS/index.html` directly). Built and
published through GAS-Core's shared `gas-static` package, configured by
`scripts/static-pages.js` — see that file's header and
`packages/gas-static/README.md` (GAS-Core) for the stamping/publish mechanics.

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
automatic last step of `pnpm run deploy:test` / `pnpm run deploy:prod`. For a
standalone build or a recovery publish:
`node -e "require('./scripts/static-pages.js').build('sit')"` /
`.publish('sit', { yes: true })`.
