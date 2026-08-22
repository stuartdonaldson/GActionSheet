#!/usr/bin/env node

/**
 * Google Apps Script Deployment Manager — GActionSheet
 *
 * The pipeline itself lives in GAS-Core's `gas-deploy` package (auth, version stamping, push,
 * named-deployment update, post-deploy hooks, over-the-wire verification, summary). This file is
 * GActionSheet's configuration of it, plus the two entry points that are not deploys:
 * `--verify*` (Script-Property drift, scripts/deploy-hooks.js) and `--deploy-dev` (a HEAD push).
 *
 *   pnpm run push                 # stamp (DEV) + push to HEAD
 *   pnpm run deploy:test          # stamp (TEST) + redeploy TEST-WEB-APP + verify + summary
 *   pnpm run deploy:prod          # stamp (PROD) + redeploy PROD-WEB-APP + verify + summary
 *   pnpm run verify[:dev|test|prod]
 *   pnpm run manage-deployments   # interactive menu (all targets + list/archive)
 *   node manage-deployments.js --summary --env test|prod   # read-only: what is deployed now?
 *
 * ONE-TIME SETUP
 *   1. Create TEST-WEB-APP and PROD-WEB-APP deployments once in the Apps Script editor
 *      (Deploy > New Deployment > Web App), with the anchor string in the description. Neither
 *      this script nor the package ever creates a deployment — a new URL is a human decision.
 *   2. Ensure appsscript.json has a "webapp" section (access/executeAs).
 *   3. local.settings.json needs `claspAuth` (the clasp credential file this project deploys
 *      with). Without it clasp silently falls back to ~/.clasprc.json and can push to the wrong
 *      script project — the package refuses to run rather than let that happen.
 */

const fs = require('fs');
const path = require('path');
const { checkbox, confirm, select } = require('@inquirer/prompts');
const {
  runCli, deploy, summary, buildInfoStamper, anchorMatch,
  claspEnv, execWithRetry, parseDeployments,
} = require('gas-deploy');

const { publish: publishStaticPortal } = require('./scripts/publish-static-portal');
const hooks = require('./scripts/deploy-hooks');

const ROOT = __dirname;
const SETTINGS_PATH = path.join(ROOT, 'local.settings.json');
const VERSION_PATH = path.join(ROOT, 'src', 'Version.js');

// BUILD_INFO.env is the source of truth for Axiom's top-level `env` column (GasLogger.js) and for
// build-static-portal.js's env guard. It is a different vocabulary from the deploy target's label
// ('TEST'/'PRODUCTION'), which is what the cmd=version contract compares — so both are stamped.
const BUILD_INFO_ENV = { test: 'test', production: 'production', dev: 'dev' };

// The static portal's public URL per target (gts-79dw.4.25): 'test' publishes to Static's
// pub/AS-sit/, 'production' to pub/AS/.
const STATIC_PORTAL_URL = {
  test: 'https://nuuc-it.github.io/Static/pub/AS-sit/',
  production: 'https://nuuc-it.github.io/Static/pub/AS/',
};

function loadSettings() {
  return JSON.parse(fs.readFileSync(SETTINGS_PATH, 'utf8'));
}

/** A hook that only applies to TEST, announced rather than silently skipped. */
function testOnly(name, run) {
  return {
    name,
    run: async (ctx) => {
      if (ctx.targetKey !== 'test') {
        console.log(`   (skipped — ${name} applies to TEST only)`);
        return;
      }
      await run(ctx);
    },
  };
}

const config = {
  root: ROOT,
  rootDir: 'src',

  // The rest of .clasp.json. GActionSheet's is not the two-key file lineage B regenerates: it
  // names the GCP project behind Cloud Logging, the Drive parent, and the extension lists that
  // decide which files `clasp push` actually sends. Regenerating without them changes the push.
  claspFields: (ctx) => ({
    projectId: ctx.settings.projectId,
    parentId: '10UCsEHPL2RjA1IduUSFDSaA2lpkoCuZY79sIjratH_s',
    scriptExtensions: ['.js', '.gs'],
    htmlExtensions: ['.html'],
    jsonExtensions: ['.json'],
    filePushOrder: [],
    skipSubdirectories: false,
  }),

  // Lineage A: one script project holds both named deployments, told apart by an anchor in the
  // description — the case sole-active-deployment resolution cannot express at all.
  targets: {
    test: {
      scriptIdKey: 'scriptId', label: 'TEST', emoji: '🧪', counter: 'build',
      anchor: 'TEST-WEB-APP', resolveDeployment: anchorMatch('TEST-WEB-APP'),
      sheetIdKey: 'testSheetId',
    },
    production: {
      scriptIdKey: 'scriptId', label: 'PRODUCTION', emoji: '🚀', counter: 'version',
      anchor: 'PROD-WEB-APP', resolveDeployment: anchorMatch('PROD-WEB-APP'),
      sheetIdKey: 'prodSheetId',
    },
  },
  envAliases: { prod: 'production', sit: 'test' },

  // The anchor MUST stay in the description: it is what anchorMatch resolves on next deploy.
  describeDeployment: (version, label, target) => `${target.anchor} v${version}`,

  // The deployment must be resolved before the stamp because BUILD_INFO.webappUrl — what the GAS
  // runtime's getWebAppUrl() returns — is this deployment's own /exec URL, and it has to be in
  // the source that gets pushed.
  resolveBeforeStamp: true,
  stamper: buildInfoStamper({
    file: 'src/Version.js',
    // The GAS runtime reads these by name (Version.js, PROBE.js, build-static-portal.js).
    fields: { date: 'buildDate', webAppUrl: 'webappUrl' },
    extraFields: ({ targetKey, version }) => ({
      // Display form only. The wire contract (cmd=version) reports the bare version, so the two
      // can never disagree: handleVersionRequest_ strips this 'v' before answering.
      version: `v${version}`,
      env: BUILD_INFO_ENV[targetKey] || 'test',
    }),
  }),

  postDeploy: [
    // Register WEBAPP_URL in Script Properties before anything reads getWebAppUrl().
    {
      name: 'Register WEBAPP_URL',
      run: ({ deploymentId, label }) => hooks.pingWebappUrl(hooks.webAppUrl(deploymentId), label),
    },
    testOnly('Register test token', ({ deploymentId }) => hooks.registerTestToken(deploymentId)),
    testOnly('Register Axiom config', ({ deploymentId }) => hooks.registerAxiomConfig(deploymentId)),
    testOnly('Register export folder config', ({ deploymentId }) => hooks.registerExportConfig(deploymentId)),
    testOnly('Verify Script Properties', () => hooks.verifyConfig('test')),
    {
      // Depends on the BUILD_INFO the stamp above wrote for this target, so it is last.
      name: 'Publish static portal',
      required: false,
      retryCommand: 'node scripts/publish-static-portal.js --env <sit|prod>',
      run: ({ targetKey }) => publishStaticPortal(targetKey === 'test' ? 'sit' : 'prod', { nonInteractive: true }),
    },
  ],

  extraRows: ({ targetKey }) => [
    { label: 'Static portal', value: STATIC_PORTAL_URL[targetKey], missing: '(static portal not configured)' },
  ],

  // Reading the stamped file is deliberately the consumer's job — the package never reads back
  // what it stamped (RECOMMENDATION.md #5). This exists only so `--summary` can flag a live-vs-
  // local divergence.
  readLocalVersion: () => {
    const src = fs.readFileSync(VERSION_PATH, 'utf8');
    const field = (name) => (src.match(new RegExp('"?' + name + '"?\\s*:\\s*"([^"]*)"')) || [])[1] || '';
    return { version: field('version').replace(/^v/, ''), now: field('buildDate') };
  },

  // deployment-ledger/<target>.jsonl and .deploy-metadata.json predate the package and have
  // readers (write-environment.py, archive/generate-pipeline-report.py, commit-deploy-stamp.js).
  // Their schema is kept exactly so existing lines and new ones stay one format.
  ledgerEntry: ({ targetKey, deploymentId, revision, version, target }) => ({
    timestamp: new Date().toISOString(),
    target: targetKey,
    deploymentId,
    version: revision ? `@${revision}` : '',
    description: `${target.anchor} v${version}`,
    url: hooks.webAppUrl(deploymentId),
  }),
  deployMetadata: ({ deploymentId, revision, version, label, target, now }) => ({
    deploymentId,
    version: revision ? `@${revision}` : '',
    description: `${target.anchor} v${version}`,
    target: label,
    productVersion: `v${version}`,
    at: now,
  }),
};

// ── Entry points that are not deploys ──────────────────────────────────────────────────────────

/**
 * DEV push to HEAD. Deliberately NOT a package target: the package's deploy() has
 * over-the-wire verification as a non-skippable final step, and a HEAD push has no named
 * deployment and no anonymously reachable URL to verify against (/dev requires an authenticated
 * editor session). Rather than add a target mode that must opt out of the package's central
 * invariant, this stays project-local — but it runs clasp through the package's claspEnv, so the
 * credential-fallback bug (#1) is fixed here too.
 */
async function deployDev(nonInteractive) {
  console.log('\n🛠️  DEV push to HEAD');
  const settings = loadSettings();
  const env = claspEnv(settings, config.targets.test.authKey);

  const deployments = parseDeployments(
    execWithRetry('clasp deployments', { cwd: ROOT, env, encoding: 'utf8' })
  );
  console.log(`   ${deployments.length} named deployment(s) in this script project.`);

  // The /dev URL is served by the script project itself, not by a named deployment.
  const devUrl = settings.webappDevUrl || '';
  if (!devUrl) console.warn('⚠️  webappDevUrl not set in local.settings.json — stamping an empty URL.');

  const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, 'package.json'), 'utf8'));
  const version = `${pkg.version}.${pkg.build || 0}`;
  const now = new Date().toISOString();
  config.stamper({ root: ROOT, label: 'DEV', version, now, targetKey: 'dev', webAppUrl: devUrl });

  if (!nonInteractive) {
    const proceed = await confirm({ message: 'Push to HEAD?', default: true });
    if (!proceed) { console.log('❌ Cancelled.'); return; }
  }

  console.log('\n📤 Pushing src/ to Apps Script...');
  execWithRetry('clasp push -f', { stdio: 'inherit', cwd: ROOT, env });
  console.log('\n✅ Push complete.');

  // Warn-only: catches drift early without requiring a full deploy:test cycle.
  try { await hooks.verifyConfig('dev', { warnOnly: true }); } catch { /* non-fatal */ }

  console.log('\n📋 To activate changes:');
  console.log('   1. Open the /dev WebApp URL in a browser to register WEBAPP_URL:');
  if (devUrl) console.log(`      ${devUrl}`);
  console.log('   2. Script editor → Deploy → Test deployments → Uninstall → Install');
  console.log('      (only needed if the sidebar panel icon is in use)');
  console.log('   3. Run pnpm run deploy:test before running the test suite');
}

/** List / archive. Never touches a deployment carrying a target anchor. */
async function manageDeployments() {
  const settings = loadSettings();
  const env = claspEnv(settings, config.targets.test.authKey);
  const raw = execWithRetry('clasp deployments', { cwd: ROOT, env, encoding: 'utf8' }).toString();
  console.log('\n📋 Deployments:\n' + raw);

  const anchors = Object.values(config.targets).map(t => t.anchor);
  const parsed = parseDeployments(raw).filter(d => d.id);
  const archivable = parsed.filter((d, i) => i !== 0 && !anchors.some(a => d.description.includes(a)));
  if (archivable.length === 0) { console.log('ℹ️  No archivable deployments.'); return; }

  const toArchive = await checkbox({
    message: 'Select deployments to archive:',
    choices: archivable.map(d => ({ name: `${d.id} (@${d.revision}) — ${d.description}`, value: d.id })),
  });
  if (toArchive.length === 0) { console.log('ℹ️  Nothing selected.'); return; }
  if (!await confirm({ message: `Archive ${toArchive.length} deployment(s)?`, default: false })) return;
  for (const id of toArchive) {
    execWithRetry(`clasp undeploy ${id}`, { stdio: 'inherit', cwd: ROOT, env });
    console.log(`✅ Archived ${id}`);
  }
}

async function main() {
  const args = process.argv.slice(2);
  const nonInteractive = args.length > 0;

  if (args.includes('--deploy-dev')) return deployDev(nonInteractive);
  if (args.includes('--manage')) return manageDeployments();
  if (args.includes('--verify-dev'))  return hooks.verifyConfig('dev');
  if (args.includes('--verify-test')) return hooks.verifyConfig('test');
  if (args.includes('--verify-prod')) return hooks.verifyConfig('prod');
  if (args.includes('--verify')) {
    const target = await select({
      message: 'Which deployment to verify?',
      choices: [
        { name: '🛠️  DEV  (/dev)', value: 'dev' },
        { name: '🧪 TEST (/exec)', value: 'test' },
      ],
    });
    return hooks.verifyConfig(target);
  }
  if (args.includes('--summary') || args.some(a => a.startsWith('--deploy-'))) {
    return runCli(config);
  }

  const action = await select({
    message: 'What would you like to do?',
    choices: [
      { name: '🛠️  Push to DEV (HEAD)', value: 'deploy-dev' },
      { name: '🧪 Deploy to TEST', value: 'test' },
      { name: '🚀 Deploy to PRODUCTION', value: 'production' },
      { name: '📊 Summary — what is deployed on TEST now?', value: 'summary-test' },
      { name: '🔍 Verify DEV', value: 'verify-dev' },
      { name: '🔍 Verify TEST', value: 'verify-test' },
      { name: '📦 List / archive', value: 'manage' },
      { name: '❌ Exit', value: 'exit' },
    ],
  });

  if (action === 'exit') return;
  if (action === 'deploy-dev') return deployDev(false);
  if (action === 'manage') return manageDeployments();
  if (action === 'summary-test') return summary(config, 'test');
  if (action === 'verify-dev') return hooks.verifyConfig('dev');
  if (action === 'verify-test') return hooks.verifyConfig('test');
  return deploy(config, action);
}

if (require.main === module) {
  main().catch((error) => {
    if (error?.name === 'ExitPromptError') { console.log('\n❌ Cancelled.'); return; }
    console.error('❌ Error:', error.message);
    process.exit(1);
  });
}

module.exports = { config };
