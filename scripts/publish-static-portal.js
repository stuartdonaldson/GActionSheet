#!/usr/bin/env node
/**
 * Publishes static-portal/dist/<env>/ to the sibling Static repo (local.settings.json's
 * staticPortalRepoPath), which GitHub Pages serves at nuuc-it.github.io/Static/pub/<AS-sit|AS>/
 * (gts-79dw.4.25 — F3Go30's tools/publish-static-pages.js pattern).
 *
 * Normally invoked automatically as the final step of manage-deployments.js's deployToTarget()
 * (pnpm run deploy:test -> --env sit, pnpm run deploy:prod -> --env prod) — see that file's
 * call site. Direct invocation exists for standalone builds and for recovery: retrying a
 * publish whose cross-repo git push failed after a deploy already succeeded.
 *
 * Builds first (via build-static-portal.js) so dist/<env> is never stale, then copies it into
 * <staticPortalRepoPath>/pub/<AS-sit|AS>/ and commits + pushes from that repo.
 *
 * Cross-repo push confirmation: when run standalone (no --yes), this prompts before pushing —
 * same human-in-the-loop norm used for every other cross-repo push in this project. When
 * chained from manage-deployments.js's deploy:test/deploy:prod, it inherits that command's own
 * nonInteractive flag (both already skip all deploy-time confirmation prompts when invoked via
 * `pnpm run deploy:*`, which passes the deploy target as a CLI flag) — this does not introduce
 * a *new* unconfirmed cross-repo push, it follows the confirmation posture that command already
 * has for the GAS side.
 *
 * A missing/unset staticPortalRepoPath is treated as "not configured yet", not a hard failure —
 * it warns and returns so a deploy without the sibling Static repo checked out still succeeds.
 *
 * Usage:
 *   node scripts/publish-static-portal.js --env sit|prod [--yes]
 */
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const { confirm } = require('@inquirer/prompts');
const { buildOne, readBuildInfo_, ENV_MAP } = require('./build-static-portal');

const ROOT = path.resolve(__dirname, '..');
const DIST_ROOT = path.join(ROOT, 'static-portal', 'dist');
const SETTINGS_PATH = path.join(ROOT, 'local.settings.json');

// Portal env -> Static repo's pub/ subfolder (gts-79dw.4.25 item 2: SIT and PROD are real,
// independently-updatable folders, not a symlink/redirect trick).
const DEST_FOLDER = { sit: 'AS-sit', prod: 'AS' };

function loadSettings_() {
  if (!fs.existsSync(SETTINGS_PATH)) {
    console.error(`❌  local.settings.json not found at ${SETTINGS_PATH}`);
    process.exit(1);
  }
  return JSON.parse(fs.readFileSync(SETTINGS_PATH, 'utf8'));
}

function copyDir_(src, dest) {
  fs.rmSync(dest, { recursive: true, force: true });
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dest, entry.name);
    if (entry.isDirectory()) copyDir_(s, d);
    else fs.copyFileSync(s, d);
  }
}

async function publish(env, { nonInteractive = false } = {}) {
  if (!ENV_MAP[env]) throw new Error(`publish-static-portal: unknown env '${env}' (expected sit|prod)`);

  const settings = loadSettings_();
  if (!settings.staticPortalRepoPath) {
    console.warn('⚠️  staticPortalRepoPath not set in local.settings.json — skipping static portal publish.');
    return;
  }
  const staticRepo = path.resolve(ROOT, settings.staticPortalRepoPath);
  if (!fs.existsSync(path.join(staticRepo, '.git'))) {
    console.error(`❌  ${staticRepo} does not look like a git checkout (no .git found)`);
    process.exit(1);
  }

  console.log(`🔨 Building static portal (--env ${env})...`);
  buildOne(env);

  const src = path.join(DIST_ROOT, env);
  const destFolder = path.join('pub', DEST_FOLDER[env]);
  const dest = path.join(staticRepo, destFolder);
  copyDir_(src, dest);
  console.log(`📦 copied static-portal/dist/${env} -> ${path.basename(staticRepo)}/${destFolder}`);

  // Scope the dirty check and staging to just this env's folder — an unscoped `git add pub`
  // would sweep in whatever happened to be sitting modified under the sibling env's folder
  // (e.g. a half-finished PROD publish while doing a SIT one).
  const status = execFileSync('git', ['status', '--porcelain', '--', destFolder], { cwd: staticRepo })
    .toString().trim();
  if (!status) {
    console.log(`✅ Static ${destFolder} already matches build output — nothing to publish.`);
    return;
  }

  if (!nonInteractive) {
    const proceed = await confirm({
      message: `Commit and push ${destFolder} to ${staticRepo} (origin)?`,
      default: true,
    });
    if (!proceed) {
      console.log('❌ Publish cancelled — dist/ copied locally but not committed/pushed.');
      return;
    }
  }

  execFileSync('git', ['add', destFolder], { cwd: staticRepo, stdio: 'inherit' });
  const buildInfo = readBuildInfo_();
  const message = `Publish team-action portal ${ENV_MAP[env].label} ${buildInfo.version}`;
  execFileSync('git', ['commit', '-m', message], { cwd: staticRepo, stdio: 'inherit' });
  execFileSync('git', ['push'], { cwd: staticRepo, stdio: 'inherit' });
  console.log(`🚀 Published to ${path.basename(staticRepo)} and pushed.`);
}

async function main() {
  const args = process.argv.slice(2);
  const envIdx = args.indexOf('--env');
  const env = envIdx !== -1 ? args[envIdx + 1] : null;
  if (!env || !ENV_MAP[env]) {
    console.error('Usage: node scripts/publish-static-portal.js --env sit|prod [--yes]');
    process.exit(1);
  }
  const nonInteractive = args.includes('--yes');
  await publish(env, { nonInteractive });
}

if (require.main === module) {
  main().catch((err) => {
    console.error(`❌  ${err.message}`);
    process.exit(1);
  });
}

module.exports = { publish };
