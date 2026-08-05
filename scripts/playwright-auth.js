/**
 * Shared Playwright auth-identity resolution, used by auth.setup.js,
 * manage-deployments.js, and gas-inspect.js.
 *
 * Account files live in a directory shared across projects
 * ($PLAYWRIGHT_AUTH_DIR, .envrc, default ~/.playwright), named by the real
 * Google account they hold (e.g. sdonaldson.json) — not by project role.
 * accounts.json in that directory is the identity registry: which email
 * each slug maps to, and when it was last captured.
 *
 * Each project assigns accounts to its own roles via local.settings.json's
 * "playwrightAccounts" map, e.g.:
 *   { "primary": "sdonaldson.json", "test.u2": "sanctuary.json" }
 */
const fs = require('fs');
const os = require('os');
const path = require('path');

const DEFAULT_AUTH_DIR = path.join(os.homedir(), '.playwright');

function authDir() {
  const envDir = process.env.PLAYWRIGHT_AUTH_DIR;
  return envDir ? envDir.replace(/^~/, os.homedir()) : DEFAULT_AUTH_DIR;
}

function registryPath() {
  return path.join(authDir(), 'accounts.json');
}

function loadRegistry() {
  const p = registryPath();
  if (!fs.existsSync(p)) return {};
  try {
    return JSON.parse(fs.readFileSync(p, 'utf8'));
  } catch {
    return {};
  }
}

function saveRegistry(registry) {
  fs.mkdirSync(authDir(), { recursive: true });
  fs.writeFileSync(registryPath(), JSON.stringify(registry, null, 2) + '\n');
}

const _warnedMissingRoles = new Set();

/**
 * Resolve the storageState file for a project role (e.g. "primary", "test.u2").
 * Falls back to the project-local .auth/<role>.json when local.settings.json
 * has no "playwrightAccounts" entry for the role (with a one-time-per-role
 * warning, so the fallback doesn't silently mask that shared auth was never
 * wired up), so the harness keeps working before accounts are migrated.
 */
function resolveAuthFile(role = 'primary', opts = {}) {
  const projectRoot = opts.projectRoot || path.join(__dirname, '..');
  const settingsPath = opts.settingsPath || path.join(projectRoot, 'local.settings.json');

  let slug = null;
  try {
    const settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
    slug = settings.playwrightAccounts && settings.playwrightAccounts[role];
  } catch {
    // no local.settings.json / unreadable — fall through to legacy path
  }

  if (slug) return path.join(authDir(), slug);

  const legacyName = role === 'primary' ? 'user.json' : `${role}.json`;
  const fallback = path.join(projectRoot, '.auth', legacyName);
  if (!_warnedMissingRoles.has(role)) {
    _warnedMissingRoles.add(role);
    console.warn(
      `⚠️  local.settings.json has no "playwrightAccounts" entry for role "${role}" — `
      + `falling back to project-local ${fallback}. See .auth/README.md and `
      + `tests/playwright/auth.setup.js to migrate this role to the shared, cross-project `
      + `auth location (DevStandard docs/standards/playwright-shared-auth.md).`
    );
  }
  return fallback;
}

module.exports = { authDir, registryPath, loadRegistry, saveRegistry, resolveAuthFile };
