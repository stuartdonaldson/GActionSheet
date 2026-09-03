#!/usr/bin/env node
/**
 * GActionSheet's team-action portal config. The pipeline itself — placeholder stamping, the
 * env-agreement assertion, per-env dist/, the scoped cross-repo publish, the PUBLISHERS.md
 * ownership guard and the published-build verification — lives in GAS-Core's shared `gas-static`
 * package. See that package's README. This file is only what is specific to this project.
 *
 * It replaces scripts/build-static-portal.js and scripts/publish-static-portal.js, both deleted
 * (GAS-Core bead GAS-Core-rgh, stage `convert-gas`). This project's `readBuildInfo_` / env-agreement
 * check was the copy the package's `webappUrl: { from: 'buildInfo' }` mode was extracted FROM
 * (gas-static README §Provenance) — so this conversion is a hand-off of behaviour already proven
 * here, not new plumbing.
 *
 * TWO VOCABULARIES, kept apart exactly as the deleted build-static-portal.js's ENV_MAP did: the
 * *portal* env (`sit`/`prod` — the Static repo's hosting-folder split, and what
 * tests/playwright/team_portal_*.test.js hardcode as `static-portal/dist/<env>/`) is not the same
 * as the *deploy* target (`test`/`production` — the GAS deployment identity, what BUILD_INFO.env
 * carries). `PORTAL_ENV` below is the one mapping between them; `envFor` in manage-deployments.js
 * uses the same map so gas-static's build/publish/verify hooks and the deploy loop agree on it.
 *
 * Never invoked on its own in normal use — manage-deployments.js chains
 * build -> publish -> assertPublishedBuild as required post-deploy steps of
 * `pnpm run deploy:test` / `:prod`, so the published page and the deployment it calls can never
 * diverge.
 *
 *   node -e "require('./scripts/static-pages.js').build('sit')"     # build only, no publish
 *
 * SOURCE OF THE BACKEND URL
 *   `src/Version.js` — the server-side BUILD_INFO literal manage-deployments.js regenerates on
 *   every deploy, carrying the /exec URL of the deployment that deploy just landed in. Building a
 *   portal env whose declared `deployTarget` disagrees with the currently-stamped `env` throws
 *   before anything is written (GAS-Core adr/0001).
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { runStatic, readBuildInfo_ } = require('gas-static');

const ROOT = path.join(__dirname, '..');
const VERSION_JS = 'src/Version.js';

// Identifiers of external resources — the script project and the static host this project
// publishes to — are committed project truth (GAS-Core adr/0004), keyed by DEPLOY target ('test'/
// 'production') because that is also gas-deploy's own vocabulary for gas-project.json's envs block.
const project = JSON.parse(fs.readFileSync(path.join(ROOT, 'gas-project.json'), 'utf8'));

// deploy target -> portal env. The only mapping between the two vocabularies; manage-deployments.js
// imports this same map for its `envFor`.
const PORTAL_ENV = { test: 'sit', production: 'prod' };

// portal env -> human-readable label static-portal/src's build badge shows (index.html / doc.html:
// `if (STATIC_ENV_LABEL_ === 'SIT') …`).
const LABEL = { sit: 'SIT', prod: 'PROD' };

/** Composes gas-static's per-env (portal-env-keyed) config from the committed identifiers. */
function envsFromProject_() {
  const out = {};
  for (const [deployTarget, def] of Object.entries(project.envs)) {
    const portalEnv = PORTAL_ENV[deployTarget];
    if (!portalEnv) throw new Error(`scripts/static-pages.js: no PORTAL_ENV mapping for deploy target '${deployTarget}'`);
    const host = project.staticHosts[def.static.host];
    if (!host) throw new Error(`gas-project.json: env '${deployTarget}' names unknown staticHosts entry '${def.static.host}'`);
    out[portalEnv] = {
      deployTarget,
      repoKey: host.repoKey,
      dest: def.static.dest,
      label: LABEL[portalEnv],
    };
  }
  return out;
}

const envs = envsFromProject_();

/**
 * The live base URL is COMPOSED from the host's Pages URL and this env's folder, never declared
 * separately — so the URL the deploy summary prints and the URL `assertPublishedBuild` polls can
 * never drift from the folder actually published to. Both halves are registered in
 * nuuc-it/Static's PUBLISHERS.md, which is what authorises the publish in the first place
 * (GAS-Core adr/0003) — `pub/AS` and `pub/AS-sit` were already registered to GActionSheet there.
 */
function liveUrl_(portalEnv) {
  const deployTarget = envs[portalEnv].deployTarget;
  return project.staticHosts[project.envs[deployTarget].static.host].pagesUrl + envs[portalEnv].dest + '/';
}

module.exports = runStatic({
  root: ROOT,
  // Must match GActionSheet's entry in nuuc-it/Static's PUBLISHERS.md ownership map.
  projectName: 'GActionSheet',
  srcDir: 'static-portal/src',
  distDir: 'static-portal/dist',
  stampedPages: ['index.html', 'doc.html'],
  webappUrl: { from: 'buildInfo', file: VERSION_JS, envField: 'env' },

  // gas-static stamps STATIC_BUILD_VERSION_ and STATIC_WEBAPP_URL_ itself. STATIC_ENV_LABEL_ is
  // this project's own, carried through the generic `placeholders` map with NO package change —
  // it is not a `var … = null;` declaration's right-hand side, it's the whole statement, which is
  // fine: raw-token substitution makes no assumption about a token's shape (confirmed at RCV's
  // conversion, gas-static README §Provenance).
  placeholders: {
    'var STATIC_ENV_LABEL_ = null;': (ctx) => `var STATIC_ENV_LABEL_ = ${JSON.stringify(ctx.envDef.label)};`,
  },

  envs,
  liveUrl: liveUrl_,
  commitMessage: ({ env }) => `Publish team-action portal ${LABEL[env]} v${readBuildInfo_(path.join(ROOT, VERSION_JS)).version}`,
});

module.exports.PORTAL_ENV = PORTAL_ENV;
module.exports.liveUrl_ = liveUrl_;
module.exports.envsFromProject_ = envsFromProject_;
