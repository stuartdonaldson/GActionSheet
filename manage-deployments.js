#!/usr/bin/env node

/**
 * Google Apps Script Deployment Manager — GActionSheet
 *
 * Run via npm:
 *   npm run push                 # stamp (DEV) + push to HEAD
 *   npm run deploy:test          # stamp (TEST) + URL + redeploy TEST-WEB-APP
 *   npm run deploy:prod          # stamp URL + redeploy PROD-WEB-APP
 *   npm run verify               # interactive config verification (pick target)
 *   npm run verify:dev           # verify DEV deployment
 *   npm run verify:test          # verify TEST deployment
 *   npm run verify:prod          # verify PROD deployment
 *   npm run manage-deployments   # interactive menu (all targets + list/archive)
 *
 * ONE-TIME SETUP
 *   1. Create TEST-WEB-APP and PROD-WEB-APP deployments once in the Apps Script
 *      editor (Deploy > New Deployment > Web App), with description containing
 *      the anchor string. This script never creates new deployments.
 *   2. Ensure appsscript.json has a "webapp" section (access/executeAs).
 *   3. For DEV (HEAD) pushes, WEBAPP_URL falls back to the script property.
 *      Named deployments (TEST/PROD) have the URL stamped into Version.js.
 *
 * Deployment URLs are stable for the lifetime of the deployment. Redeploying
 * with `clasp deploy -i <id>` bumps the version but keeps the same URL.
 */

const { execSync } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { checkbox, confirm, select } = require('@inquirer/prompts');

const SETTINGS_PATH = path.join(__dirname, 'local.settings.json');

const TARGETS = {
  test:       { anchor: 'TEST-WEB-APP', label: 'TEST',       emoji: '🧪' },
  production: { anchor: 'PROD-WEB-APP', label: 'PRODUCTION', emoji: '🚀' },
};

function getVersionFromBuildInfo() {
  const content = fs.readFileSync(path.join(__dirname, 'src', 'Version.js'), 'utf8');
  const match = content.match(/version:\s*"([^"]+)"/);
  return match ? match[1] : 'unknown';
}

function buildDeploymentDescription(anchor) {
  return `${anchor} ${getVersionFromBuildInfo()}`;
}

function stampVersionInfo(target, deploymentId) {
  const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, 'package.json'), 'utf8'));
  const appVersion = `v${pkg.version}`;
  const now = new Date();
  const dateStr = now.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  const timeStr = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
  const suffix = target === 'test' ? ' (TEST)' : target === 'dev' ? ' (DEV)' : '';
  const versionStr = `${appVersion} (Rev. ${dateStr} ${timeStr})${suffix}`;
  const url = deploymentId ? webAppUrl(deploymentId) : '';

  const versionPath = path.join(__dirname, 'src', 'Version.js');
  let data = fs.readFileSync(versionPath, 'utf8');
  data = data.replace(/version: "[^"]*"/, `version: "${versionStr}"`);
  data = data.replace(/buildDate: "[^"]*"/, `buildDate: "${now.toISOString()}"`);
  data = data.replace(/webappUrl: "[^"]*"/, `webappUrl: "${url}"`);
  fs.writeFileSync(versionPath, data, 'utf8');

  console.log(`\n📝 Version stamped: ${versionStr}`);
  if (url) console.log(`   WebApp URL:      ${url}`);
}

function webAppUrl(deploymentId) {
  return `https://script.google.com/macros/s/${deploymentId}/exec`;
}

async function getDeployments() {
  console.log('📋 Fetching deployments...');
  const output = execSync('clasp deployments', { encoding: 'utf8' });
  return parseDeployments(output);
}

function parseDeployments(output) {
  const lines = output.split('\n').filter(l => l.trim());
  const deployments = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed.startsWith('- ')) continue;
    const content = trimmed.substring(2);
    const parts = content.split(' - ');
    const mainParts = parts[0].trim().split(/\s+/);
    if (mainParts.length >= 2) {
      deployments.push({
        deploymentId: mainParts[0],
        version: mainParts[1],
        description: parts.slice(1).join(' - ').trim(),
        isHead: mainParts[1] === '@HEAD',
      });
    }
  }
  deployments.sort((a, b) => {
    if (a.isHead) return -1;
    if (b.isHead) return 1;
    return (parseInt(b.version.replace('@', '')) || 0) - (parseInt(a.version.replace('@', '')) || 0);
  });
  return deployments;
}

async function deployToTarget(target, deployments, nonInteractive) {
  const { anchor, label, emoji } = TARGETS[target];
  const match = deployments.find(d => !d.isHead && d.description && d.description.includes(anchor));
  if (!match) {
    console.log(`\n❌ No deployment found with description containing "${anchor}".`);
    console.log(`   Create it once in the Apps Script editor as a Web App.`);
    return;
  }

  console.log(`\n${emoji} Deploying to ${label}`);
  console.log(`   Target:  ${match.deploymentId}  ${match.version}  "${match.description}"`);
  console.log(`   URL:     ${webAppUrl(match.deploymentId)}\n`);

  if (!nonInteractive) {
    const proceed = await confirm({ message: `Push and redeploy ${label}?`, default: true });
    if (!proceed) { console.log('❌ Cancelled.'); return; }
  }

  stampVersionInfo(target, match.deploymentId);
  console.log('\n📤 Pushing src/ to Apps Script...');
  execSync('clasp push -f', { stdio: 'inherit' });

  const description = buildDeploymentDescription(anchor);
  console.log(`\n🚀 Repointing ${label} deployment...`);
  execSync(`clasp deploy -i ${match.deploymentId} -d "${description}"`, { stdio: 'inherit' });

  const updatedDeployments = await getDeployments();
  const updated = updatedDeployments.find(d => d.deploymentId === match.deploymentId && !d.isHead);
  if (updated) {
    fs.writeFileSync(
      path.join(__dirname, '.deploy-metadata.json'),
      JSON.stringify({ deploymentId: match.deploymentId, version: updated.version, description: updated.description, target: label }, null, 2)
    );
  }

  console.log(`\n✅ ${label} deploy complete.`);
  console.log(`🔗 ${label} URL: ${webAppUrl(match.deploymentId)}\n`);

  // Ping the deployed URL so doGet() registers WEBAPP_URL in Script Properties
  // immediately — before any test token or other caller reads getWebAppUrl().
  await pingWebappUrl(webAppUrl(match.deploymentId), label);

  if (target === 'test') {
    await registerTestToken(match.deploymentId);
    await verifyConfig('test');
  }
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
  try {
    const resp = await fetch(url);
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
 * Loads cookies from a Playwright storageState file for use in authenticated requests.
 * Returns a Cookie header string, or null if the file is missing or unreadable.
 * Used to authenticate requests to the /dev endpoint, which requires editor access.
 *
 * @param {string} [authPath]  Path to storageState JSON. Defaults to .auth/user.json.
 * @returns {string|null}
 */
function loadAuthCookies(authPath) {
  const p = authPath || path.join(__dirname, '.auth', 'user.json');
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
 *   npm run verify:dev | verify:test | verify:prod
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
    console.log('   Run npm run deploy:prod first, then verify:prod will be meaningful.\n');
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
      console.log('  ⚠️  Skipped — no .auth/user.json  (run: node tests/playwright/auth.setup.js)');
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

  // Script property checks — only for dev/test where these are meaningful
  if (target !== 'prod') {
    const checks = [
      { label: 'TEST_DOC_ID',   remote: remote.testDocId,   local: settings.testDocId },
      { label: 'TEST_SHEET_ID', remote: remote.testSheetId, local: settings.testSheetId },
    ];
    const drifted = checks.filter(c => c.remote !== c.local);
    if (drifted.length === 0) {
      console.log('  ✅ TEST_DOC_ID   matches local.settings.json');
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
      console.warn('  Drift can occur when beginTestSession/endTestSession updates TEST_DOC_ID');
      console.warn('  or script properties are manually changed.\n');

      if (warnOnly) {
        console.warn(`  ⚠️  Run npm run verify:${target} for the interactive bootstrap prompt.\n`);
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
    console.log(`  ${valid ? '✅' : '❌'} Test token ${valid ? `valid until ${settings.testTokenExpiresAt}` : 'EXPIRED — run npm run deploy:test to refresh'}`);
  }

  _printSurfaceHint(target);
}

function _printSurfaceHint(target) {
  console.log(`\n  ℹ  Surface checks (sidebar/chipHover/menu): npm run probe${target === 'prod' ? '  (ensure correct add-on installed)' : ''}`);
}

async function deployDev(nonInteractive) {
  console.log('\n🛠️  DEV push to HEAD');
  stampVersionInfo('dev', null);

  if (!nonInteractive) {
    const proceed = await confirm({ message: 'Push to HEAD?', default: true });
    if (!proceed) { console.log('❌ Cancelled.'); return; }
  }

  console.log('\n📤 Pushing src/ to Apps Script...');
  execSync('clasp push -f', { stdio: 'inherit' });

  console.log('\n✅ Push complete.');

  // Verify config using /dev URL + Playwright auth cookies (warn-only — no interactive prompt).
  // Catches drift early without requiring a full deploy:test cycle.
  try {
    await verifyConfig('dev', { warnOnly: true });
  } catch { /* non-fatal */ }

  console.log('\n📋 To activate changes:');
  console.log('   1. Open the /dev WebApp URL in a browser to register WEBAPP_URL:');

  try {
    const s = JSON.parse(fs.readFileSync(SETTINGS_PATH, 'utf8'));
    if (s.webappDevUrl) console.log(`      ${s.webappDevUrl}`);
  } catch { /* settings not available */ }

  console.log('   2. Script editor → Deploy → Test deployments → Uninstall → Install');
  console.log('      (only needed if the sidebar panel icon is in use)');
  console.log('   3. Run npm run deploy:test before running the test suite');
  console.log('      (deploy:test offers interactive bootstrap if config has drifted)\n');
}

async function main() {
  try {
    const args = process.argv.slice(2);
    let action = args.includes('--deploy-dev')   ? 'deploy-dev'
                : args.includes('--deploy-test')  ? 'deploy-test'
                : args.includes('--deploy-prod')  ? 'deploy-prod'
                : args.includes('--verify-dev')   ? 'verify-dev'
                : args.includes('--verify-test')  ? 'verify-test'
                : args.includes('--verify-prod')  ? 'verify-prod'
                : args.includes('--verify')       ? 'verify'
                : args.includes('--manage')       ? 'manage'
                : await select({
                    message: 'What would you like to do?',
                    choices: [
                      { name: '🛠️  Push to DEV (HEAD)',      value: 'deploy-dev' },
                      { name: '🧪 Deploy to TEST',            value: 'deploy-test' },
                      { name: '🚀 Deploy to PRODUCTION',      value: 'deploy-prod' },
                      { name: '🔍 Verify DEV',                value: 'verify-dev' },
                      { name: '🔍 Verify TEST',               value: 'verify-test' },
                      { name: '📦 List / archive',            value: 'manage' },
                      { name: '❌ Exit',                      value: 'exit' },
                    ],
                  });

    if (action === 'exit') return;

    const nonInteractive = args.length > 0;

    if (action === 'deploy-dev')  { await deployDev(nonInteractive); return; }
    if (action === 'verify-dev')  { await verifyConfig('dev');  return; }
    if (action === 'verify-test') { await verifyConfig('test'); return; }
    if (action === 'verify-prod') { await verifyConfig('prod'); return; }
    if (action === 'verify') {
      const target = await select({
        message: 'Which deployment to verify?',
        choices: [
          { name: '🛠️  DEV  (/dev)',   value: 'dev' },
          { name: '🧪 TEST (/exec)',   value: 'test' },
        ],
      });
      await verifyConfig(target);
      return;
    }

    const deployments = await getDeployments();

    if (action === 'deploy-test')      await deployToTarget('test', deployments, nonInteractive);
    else if (action === 'deploy-prod') await deployToTarget('production', deployments, nonInteractive);
    else if (action === 'manage') {
      displayDeployments(deployments);
      const toArchive = await getUserSelection(deployments);
      if (toArchive.length === 0) { console.log('ℹ️  Nothing selected.'); return; }
      if (!await confirm({ message: `Archive ${toArchive.length} deployment(s)?`, default: false })) return;
      for (const id of toArchive) {
        execSync(`clasp undeploy ${id}`, { stdio: 'inherit' });
        console.log(`✅ Archived ${id}`);
      }
    }
  } catch (error) {
    if (error?.name === 'ExitPromptError') { console.log('\n❌ Cancelled.'); return; }
    console.error('❌ Error:', error.message);
    process.exit(1);
  }
}

function displayDeployments(deployments) {
  console.log('\n📋 Deployments:\n');
  deployments.forEach((d, i) => {
    const status = d.isHead ? '🏷️  @HEAD' : i === 0 ? '🆕 Most Recent' : '📦 Archivable';
    console.log(`${i + 1}. ${d.deploymentId}  ${d.version}  ${status}`);
    console.log(`   ${d.description || 'No description'}\n`);
  });
}

async function getUserSelection(deployments) {
  const anchors = Object.values(TARGETS).map(t => t.anchor);
  const archivable = deployments.filter((d, i) =>
    !d.isHead && i !== 0 && !anchors.some(a => d.description && d.description.includes(a))
  );
  if (archivable.length === 0) { console.log('ℹ️  No archivable deployments.'); return []; }
  return checkbox({
    message: 'Select deployments to archive:',
    choices: archivable.map(d => ({ name: `${d.deploymentId} (${d.version}) — ${d.description}`, value: d.deploymentId })),
  });
}

if (require.main === module) main().catch(console.error);
module.exports = { getDeployments, parseDeployments };
