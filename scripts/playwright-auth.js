/**
 * Re-export shim -- the actual resolver lives in DevStandard, the shared
 * canonical source (docs/standards/playwright-shared-auth.md). Kept here so
 * every existing require('./scripts/playwright-auth') / require('../../scripts/playwright-auth')
 * call site in this project doesn't need touching; this project carries no
 * forked copy of the resolution logic to drift out of sync.
 *
 * All call sites in this project already pass an explicit `projectRoot` to
 * resolveAuthFile(), so the DevStandard module's own default
 * (path.join(__dirname, '..'), which would resolve relative to DevStandard's
 * own directory if ever hit) is never exercised here.
 */
const path = require('path');

const devstandard = process.env.DEVSTANDARD;
if (!devstandard) {
  throw new Error(
    '$DEVSTANDARD is not set -- required to resolve the shared Playwright auth scripts ' +
    '(see /home/stuar/.claude/CLAUDE.md §10a: export DEVSTANDARD=/mnt/c/dev/DevStandard in your shell profile).'
  );
}

module.exports = require(path.join(devstandard, 'tools', 'playwright-auth', 'playwright-auth.js'));
