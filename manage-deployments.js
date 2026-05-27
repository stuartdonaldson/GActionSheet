#!/usr/bin/env node

/**
 * Google Apps Script Deployment Manager — GActionSheet
 *
 * Run via npm — do not call directly, as that skips update-revision:
 *   npm run deploy:test          # stamp revision + redeploy TEST-WEB-APP
 *   npm run deploy:prod          # stamp revision + redeploy PROD-WEB-APP
 *   npm run manage-deployments   # interactive menu (list/archive/deploy)
 *
 * ONE-TIME SETUP
 *   1. Create TEST-WEB-APP and PROD-WEB-APP deployments once in the Apps Script
 *      editor (Deploy > New Deployment > Web App), with description containing
 *      the anchor string. This script never creates new deployments.
 *   2. Ensure appsscript.json has a "webapp" section (access/executeAs).
 *   3. After deploy:test, visit the TEST URL once — doGet self-registers
 *      WEBAPP_URL in script properties.
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
  console.log(`🔗 ${label} URL: ${webAppUrl(match.deploymentId)}`);
  console.log(`   Visit that URL once in a browser to self-register WEBAPP_URL in script properties.\n`);

  if (target === 'test') {
    await registerTestToken(match.deploymentId);
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

  const url    = settings.webappTestUrl || webAppUrl(deploymentId);
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

  // Persist token to local.settings.json for Python tests.
  settings.testToken          = testToken;
  settings.testTokenExpiresAt = expiresAt;
  fs.writeFileSync(SETTINGS_PATH, JSON.stringify(settings, null, 2) + '\n');
  console.log(`✅ Test token registered. Expires: ${expiresAt}`);
}

async function main() {
  try {
    if (!process.env.npm_lifecycle_event) {
      console.warn('⚠️  Warning: called directly, not via npm. update-revision will NOT run.\n');
    }

    const args = process.argv.slice(2);
    let action = args.includes('--deploy-test') ? 'deploy-test'
                : args.includes('--deploy-prod') ? 'deploy-prod'
                : args.includes('--manage')       ? 'manage'
                : await select({
                    message: 'What would you like to do?',
                    choices: [
                      { name: '🧪 Deploy to TEST',        value: 'deploy-test' },
                      { name: '🚀 Deploy to PRODUCTION',  value: 'deploy-prod' },
                      { name: '📦 List / archive',        value: 'manage' },
                      { name: '❌ Exit',                  value: 'exit' },
                    ],
                  });

    if (action === 'exit') return;

    const deployments = await getDeployments();
    const nonInteractive = args.length > 0;

    if (action === 'deploy-test')  await deployToTarget('test', deployments, nonInteractive);
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
