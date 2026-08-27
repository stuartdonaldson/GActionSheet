#!/usr/bin/env node

/**
 * GActionSheet's project-owned deploy hooks and config verification.
 *
 * These moved out of manage-deployments.js when that script became pure config over GAS-Core's
 * `gas-deploy` package (RECOMMENDATION.md Stage 3). Their behaviour is unchanged — the package
 * owns the pipeline (auth, stamp, push, redeploy, verify, summary); everything here is
 * GActionSheet-specific and stays in GActionSheet:
 *
 *   pingWebappUrl        registers WEBAPP_URL in Script Properties right after a deploy
 *   registerTestToken    mints + registers the per-deployment TEST_TOKEN, persists it for pytest
 *   registerAxiomConfig  pushes the Axiom ingest token/dataset so GasLogger.flush() can POST
 *   registerExportConfig pushes the export-isolation root folder id
 *   verifyConfig         diffs live Script Properties against local.settings.json (also the
 *                        --verify/--verify-dev|test|prod entry points, which are NOT deploy steps)
 *
 * verifyConfig deliberately keeps its own `fetch` calls rather than routing through the package's
 * HTTP client: it needs cookie auth for the /dev endpoint (Playwright storageState), which is a
 * browser-session concern the package's anonymous /exec client has no business knowing about.
 */

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { confirm } = require('@inquirer/prompts');
const { resolveAuthFile } = require('./playwright-auth');

const ROOT = path.resolve(__dirname, '..');
const SETTINGS_PATH = path.join(ROOT, 'local.settings.json');

function webAppUrl(deploymentId) {
  return `https://script.google.com/macros/s/${deploymentId}/exec`;
}

/**
 * Hit the WebApp's doGet endpoint to trigger WEBAPP_URL self-registration.
 * Ensures Script Properties['WEBAPP_URL'] is set to the correct URL for this
 * deployment immediately after push/deploy, before anything else reads it.
 *
 * Uses a plain unauthenticated fetch — access=ANYONE means the function runs
 * regardless of auth; the script runs as USER_DEPLOYING.
 *
 * @param {string} url  The full WebApp URL to ping.
 * @param {string} label  Human-readable label for console output.
 */
async function pingWebappUrl(url, label) {
  console.log(`\n🌐 Pinging ${label} to register WEBAPP_URL...`);
  // ?deploy=1 tells doGet() this ping is the post-deploy ping (not a routine
  // health check or browser visit) so it can log a distinct 'webapp.deploy'
  // marker — gives Axiom a clean "this deployment happened" event per deploy.
  const deployUrl = url + (url.includes('?') ? '&' : '?') + 'deploy=1';
  try {
    const resp = await fetch(deployUrl);
    const body = await resp.text();
    const firstLine = body.split('\n')[0].slice(0, 80);
    console.log(`✅ WEBAPP_URL registered. Response: ${firstLine}`);
  } catch (err) {
    console.warn(`⚠️  Could not ping ${label} WebApp (${err.message}) — WEBAPP_URL may be stale.`);
    console.warn(`   Run manually: curl "${url}"`);
  }
}

/**
 * Generates a fresh per-deployment test token, registers it with the GAS WebApp
 * (via set_test_token — protected by WEBAPP_SECRET), and writes it to
 * local.settings.json so Python tests can use it without a browser.
 *
 * Requires local.settings.json to have: webappTestUrl, webappSecret.
 *
 * @param {string} deploymentId  The TEST-WEB-APP deployment ID (for URL construction).
 */
async function registerTestToken(deploymentId) {
  let settings;
  try {
    settings = JSON.parse(fs.readFileSync(SETTINGS_PATH, 'utf8'));
  } catch {
    console.warn('⚠️  Could not read local.settings.json — skipping test token registration.');
    return;
  }

  // Always derive the URL from the deployment ID — never trust a manually-set
  // webappTestUrl, which may be stale from a previous deployment cycle.
  const url = webAppUrl(deploymentId);
  const secret = settings.webappSecret;
  if (!secret) {
    console.warn('⚠️  webappSecret not set in local.settings.json — skipping test token registration.');
    return;
  }

  const testToken  = crypto.randomUUID();
  const expiresAt  = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(); // +24 h

  console.log('\n🔑 Registering test token with GAS WebApp...');
  try {
    const resp = await fetch(url, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ secret, action: 'set_test_token', testToken, expiresAt }),
    });
    const body = await resp.text();
    let parsed;
    try { parsed = JSON.parse(body); } catch { parsed = {}; }
    if (!parsed.ok) {
      console.warn(`⚠️  set_test_token returned unexpected response: ${body}`);
      return;
    }
  } catch (err) {
    console.warn(`⚠️  Failed to register test token: ${err.message}`);
    return;
  }

  // Persist token + derived URL to local.settings.json for Python tests.
  // webappTestUrl is always overwritten with the authoritative derived URL so
  // it can never become stale from a previous deployment cycle.
  settings.webappTestUrl      = url;
  settings.testToken          = testToken;
  settings.testTokenExpiresAt = expiresAt;
  fs.writeFileSync(SETTINGS_PATH, JSON.stringify(settings, null, 2) + '\n');
  console.log(`✅ Test token registered. Expires: ${expiresAt}`);
}

/**
 * Pushes the Axiom ingest config (axiomToken/axiomDataset from local.settings.json)
 * to the GAS WebApp via set_axiom_config — protected by WEBAPP_SECRET, same pattern
 * as registerTestToken() — so GasLogger.flush() can POST server-side events there
 * (docs/atdd/journey-logging-design.md §4.3, gts-ishz.1).
 *
 * No-op (warns only) if axiomToken/axiomDataset aren't set in local.settings.json --
 * Axiom is optional, not required for a deploy to succeed.
 *
 * @param {string} deploymentId  The TEST-WEB-APP deployment ID (for URL construction).
 */
async function registerAxiomConfig(deploymentId) {
  let settings;
  try {
    settings = JSON.parse(fs.readFileSync(SETTINGS_PATH, 'utf8'));
  } catch {
    console.warn('⚠️  Could not read local.settings.json — skipping Axiom config registration.');
    return;
  }

  const url = webAppUrl(deploymentId);
  const secret = settings.webappSecret;
  const axiomToken = settings.axiomToken;
  const axiomDataset = settings.axiomDataset;
  if (!secret || !axiomToken || !axiomDataset) {
    console.warn('⚠️  webappSecret/axiomToken/axiomDataset not all set in local.settings.json — skipping Axiom config registration.');
    return;
  }

  console.log('\n📊 Registering Axiom config with GAS WebApp...');
  try {
    const resp = await fetch(url, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ secret, action: 'set_axiom_config', axiomToken, axiomDataset }),
    });
    const body = await resp.text();
    let parsed;
    try { parsed = JSON.parse(body); } catch { parsed = {}; }
    if (!parsed.ok) {
      console.warn(`⚠️  set_axiom_config returned unexpected response: ${body}`);
      return;
    }
  } catch (err) {
    console.warn(`⚠️  Failed to register Axiom config: ${err.message}`);
    return;
  }
  console.log(`✅ Axiom config registered (dataset: ${axiomDataset}).`);
}

/**
 * Pushes the export-isolation root folder (exportRootFolderId from
 * local.settings.json) to the GAS WebApp via set_export_config — protected by
 * WEBAPP_SECRET, same pattern as registerAxiomConfig() — so
 * getExportFolder_() (src/ExportFolderMap.js, gts-z6j0) creates per-document
 * export subfolders under it instead of writing export output into each
 * document's own source folder.
 *
 * No-op (warns only) if exportRootFolderId isn't set in local.settings.json —
 * export isolation is best-effort, not required for a deploy to succeed
 * (getExportFolder_ falls back to the old source-folder behavior).
 *
 * @param {string} deploymentId  The TEST-WEB-APP deployment ID (for URL construction).
 */
async function registerExportConfig(deploymentId) {
  let settings;
  try {
    settings = JSON.parse(fs.readFileSync(SETTINGS_PATH, 'utf8'));
  } catch {
    console.warn('⚠️  Could not read local.settings.json — skipping export folder config registration.');
    return;
  }

  const url = webAppUrl(deploymentId);
  const secret = settings.webappSecret;
  const exportRootFolderId = settings.exportRootFolderId;
  if (!secret || !exportRootFolderId) {
    console.warn('⚠️  webappSecret/exportRootFolderId not both set in local.settings.json — skipping export folder config registration.');
    return;
  }

  console.log('\n📁 Registering export folder config with GAS WebApp...');
  try {
    const resp = await fetch(url, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ secret, action: 'set_export_config', exportRootFolderId }),
    });
    const body = await resp.text();
    let parsed;
    try { parsed = JSON.parse(body); } catch { parsed = {}; }
    if (!parsed.ok) {
      console.warn(`⚠️  set_export_config returned unexpected response: ${body}`);
      return;
    }
  } catch (err) {
    console.warn(`⚠️  Failed to register export folder config: ${err.message}`);
    return;
  }
  console.log(`✅ Export folder config registered (root: ${exportRootFolderId}).`);
}

/**
 * Loads cookies from a Playwright storageState file for use in authenticated requests.
 * Returns a Cookie header string, or null if the file is missing or unreadable.
 * Used to authenticate requests to the /dev endpoint, which requires editor access.
 *
 * @param {string} [authPath]  Path to storageState JSON. Defaults to the
 *   "primary" role's file, resolved via scripts/playwright-auth.js
 *   (local.settings.json's playwrightAccounts map, or .auth/user.json).
 * @returns {string|null}
 */
function loadAuthCookies(authPath) {
  const p = authPath || resolveAuthFile('primary', { projectRoot: ROOT, settingsPath: SETTINGS_PATH });
  if (!fs.existsSync(p)) return null;
  try {
    const state = JSON.parse(fs.readFileSync(p, 'utf8'));
    const now = Date.now() / 1000;
    const cookieStr = (state.cookies || [])
      .filter(c => c.name && c.value && (!c.expires || c.expires > now))
      .map(c => `${c.name}=${c.value}`)
      .join('; ');
    return cookieStr || null;
  } catch { return null; }
}

/**
 * Verifies a deployment end-to-end: health, version, WEBAPP_URL registration,
 * script property config, and (for test) token validity. Surfaces drift and
 * offers an interactive bootstrap when config properties are out of sync.
 *
 * Can be called from the deploy pipeline or independently via:
 *   pnpm run verify:dev | verify:test | verify:prod
 *
 * @param {'dev'|'test'|'prod'} target
 * @param {Object} [opts]
 * @param {boolean} [opts.warnOnly]  Suppress interactive bootstrap prompt (just warn).
 */
async function verifyConfig(target, opts = {}) {
  const { warnOnly = false } = opts;

  let settings;
  try { settings = JSON.parse(fs.readFileSync(SETTINGS_PATH, 'utf8')); }
  catch { console.error('❌ Cannot read local.settings.json'); return; }

  if (target === 'prod') {
    console.log('\n⚠️  PROD has not been deployed with current code.');
    console.log('   Run pnpm run deploy:prod first, then verify:prod will be meaningful.\n');
    return;
  }

  const urlMap = { dev: settings.webappDevUrl, test: settings.webappTestUrl };
  const url    = urlMap[target];
  const secret = settings.webappSecret;

  if (!url) { console.error(`❌ No URL for target "${target}" in local.settings.json`); return; }
  if (!secret) { console.error('❌ webappSecret not set in local.settings.json'); return; }

  const label = target.toUpperCase();
  console.log(`\n🔍 Verifying ${label} deployment`);
  console.log(`   URL: ${url}\n`);

  const authHeaders = { 'Content-Type': 'application/json' };

  // ── DEV: /dev blocks unauthenticated requests — use cookie auth for everything ──

  if (target === 'dev') {
    const cookies = loadAuthCookies();
    if (!cookies) {
      console.log('  ⚠️  Skipped — no auth session found  (run: node tests/playwright/auth.setup.js)');
      _printSurfaceHint(target);
      return;
    }
    authHeaders['Cookie'] = cookies;
  }

  // ── Level 1: Health check ──────────────────────────────────────────────────
  // For TEST: unauthenticated GET (access=ANYONE, returns plain-text response).
  // For DEV:  skip plain GET (blocked without auth); health confirmed by config POST below.

  let remoteVersion = '', remoteWebappUrl = '';
  if (target === 'test') {
    try {
      const resp = await fetch(url);
      const body = await resp.text();
      console.log(resp.status === 200 ? '  ✅ WebApp responds (200 OK)' : `  ❌ WebApp unhealthy — HTTP ${resp.status}`);
      const vLine = body.split('\n').find(l => l.startsWith('GActionSheet'));
      remoteVersion   = vLine ? vLine.replace('GActionSheet ', '').trim() : '';
      const wLine = body.split('\n').find(l => l.startsWith('WebApp:'));
      remoteWebappUrl = wLine ? wLine.replace('WebApp:', '').trim() : '';
      if (remoteVersion)   console.log(`  ✅ Version:   ${remoteVersion}`);
      if (remoteWebappUrl) {
        const deployId = url.split('/macros/s/')[1]?.split('/')[0] || '';
        console.log(`  ${deployId && remoteWebappUrl.includes(deployId) ? '✅' : '⚠️ '} WEBAPP_URL: ${remoteWebappUrl}`);
      }
    } catch (err) { console.log(`  ❌ WebApp unreachable: ${err.message}`); }
  }

  // ── Level 2: Config check (WEBAPP_SECRET POST) ────────────────────────────

  let remote;
  try {
    const resp = await fetch(url, {
      method: 'POST', headers: authHeaders,
      body: JSON.stringify({ secret, action: 'get_test_config' }),
    });
    const ct = resp.headers.get('content-type') || '';
    if (resp.status !== 200 || !ct.includes('application/json')) {
      const hint = target === 'dev'
        ? 'auth may be expired — re-run: node tests/playwright/auth.setup.js'
        : `unexpected response (HTTP ${resp.status})`;
      console.log(`  ⚠️  Config check skipped — ${hint}`);
      _printSurfaceHint(target);
      return;
    }
    remote = await resp.json();
    if (target === 'dev') {
      // For /dev, the config POST confirms reachability — report version here
      remoteVersion = remote.version || '';
      if (remoteVersion) console.log(`  ✅ WebApp responds (authed) — ${remoteVersion}`);
    }
  } catch (err) {
    console.log(`  ⚠️  Config fetch failed: ${err.message}`);
    _printSurfaceHint(target);
    return;
  }

  // Script property checks — only for dev/test where these are meaningful.
  // TEST_DOC_ID is retired (ADR-0006 §4): GAS holds no script property for
  // any doc ID — beginTestSession/endTestSession take it as a real parameter
  // on every call, sourced from local.settings.json's testDocId, so there is
  // nothing on the GAS side left to drift. Only TEST_SHEET_ID remains
  // meaningful to check here.
  if (target !== 'prod') {
    const checks = [
      { label: 'TEST_SHEET_ID', remote: remote.testSheetId, local: settings.testSheetId },
    ];
    const drifted = checks.filter(c => c.remote !== c.local);
    if (drifted.length === 0) {
      console.log('  ✅ TEST_SHEET_ID matches local.settings.json');
    } else {
      console.warn('\n  ⚠️  Script property drift detected:');
      console.warn('  ────────────────────────────────────────────────────────────────────────');
      console.warn('  Property              GAS (remote)                        local.settings.json');
      console.warn('  ────────────────────────────────────────────────────────────────────────');
      for (const d of drifted) {
        console.warn(`  ${d.label.padEnd(22)} ${(d.remote||'(not set)').padEnd(36)}  ${d.local||'(not set)'}`);
      }
      console.warn('');
      console.warn('  Drift can occur when script properties are manually changed.\n');

      if (warnOnly) {
        console.warn(`  ⚠️  Run pnpm run verify:${target} for the interactive bootstrap prompt.\n`);
      } else {
        const shouldBootstrap = await confirm({
          message: 'Run bootstrap to reset GAS properties to canonical values?',
          default: false,
        });
        if (shouldBootstrap) {
          try {
            const br = await fetch(url, {
              method: 'POST', headers: authHeaders,
              body: JSON.stringify({ secret, action: 'bootstrap' }),
            });
            const bj = await br.json();
            console.log(bj.ok ? '  ✅ Bootstrap complete.' : `  ⚠️  Unexpected: ${JSON.stringify(bj)}`);
          } catch (err) { console.warn(`  ⚠️  Bootstrap failed: ${err.message}`); }
        } else {
          console.log('  Skipped. Investigate the drift before running tests.');
        }
      }
    }
  }

  // Test token validity
  if (target === 'test' && settings.testTokenExpiresAt) {
    const expires = new Date(settings.testTokenExpiresAt);
    const valid   = expires > new Date();
    console.log(`  ${valid ? '✅' : '❌'} Test token ${valid ? `valid until ${settings.testTokenExpiresAt}` : 'EXPIRED — run pnpm run deploy:test to refresh'}`);
  }

  _printSurfaceHint(target);
}

function _printSurfaceHint(target) {
  console.log(`\n  ℹ  Surface checks (sidebar/chipHover/menu): pnpm run probe${target === 'prod' ? '  (ensure correct add-on installed)' : ''}`);
}

module.exports = {
  webAppUrl,
  pingWebappUrl,
  registerTestToken,
  registerAxiomConfig,
  registerExportConfig,
  loadAuthCookies,
  verifyConfig,
};
