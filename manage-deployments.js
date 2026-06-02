#!/usr/bin/env node

/**
 * Google Apps Script Deployment Manager — GActionSheet
 *
 * Run via npm:
 *   npm run push                 # stamp (DEV) + push to HEAD
 *   npm run deploy:test          # stamp (TEST) + URL + redeploy TEST-WEB-APP
 *   npm run deploy:prod          # stamp URL + redeploy PROD-WEB-APP
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
  console.log('\n📋 To activate changes:');
  console.log('   1. Open the /dev WebApp URL in a browser to register WEBAPP_URL:');

  // Load the DEV deployment URL from local.settings.json if available
  try {
    const s = JSON.parse(fs.readFileSync(SETTINGS_PATH, 'utf8'));
    if (s.webappDevUrl) console.log(`      ${s.webappDevUrl}`);
  } catch { /* settings not available */ }

  console.log('   2. Script editor → Deploy → Test deployments → Uninstall → Install');
  console.log('      (only needed if the sidebar panel icon is in use)\n');
}

async function main() {
  try {
    const args = process.argv.slice(2);
    let action = args.includes('--deploy-dev')  ? 'deploy-dev'
                : args.includes('--deploy-test') ? 'deploy-test'
                : args.includes('--deploy-prod') ? 'deploy-prod'
                : args.includes('--manage')      ? 'manage'
                : await select({
                    message: 'What would you like to do?',
                    choices: [
                      { name: '🛠️  Push to DEV (HEAD)',   value: 'deploy-dev' },
                      { name: '🧪 Deploy to TEST',        value: 'deploy-test' },
                      { name: '🚀 Deploy to PRODUCTION',  value: 'deploy-prod' },
                      { name: '📦 List / archive',        value: 'manage' },
                      { name: '❌ Exit',                  value: 'exit' },
                    ],
                  });

    if (action === 'exit') return;

    const nonInteractive = args.length > 0;

    if (action === 'deploy-dev') {
      await deployDev(nonInteractive);
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
