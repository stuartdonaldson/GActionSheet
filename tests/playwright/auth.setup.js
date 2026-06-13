/**
 * One-time Google auth capture. Run manually:
 *   node tests/playwright/auth.setup.js                       # saves to .auth/user.json (default)
 *   node tests/playwright/auth.setup.js --account=test.u1     # saves to .auth/test.u1.json
 *   node tests/playwright/auth.setup.js --output=.auth/custom.json
 *
 * Canonical account names (see docs/security-architecture.md §5 and .auth/README.md):
 *   user           — Primary / dev deployer session (default)
 *   test.u1        — primary end user, non-deployer (full access, target taxonomy)
 *   test.u2        — restricted end user, single team (J-ACCESS-FILTER P2/P3)
 *   test.u3        — restricted end user, other team (J-ACCESS-FILTER P1/P2 mirror)
 *   nuuts.service  — production service/deployer account (future)
 *
 * Re-run only when the session expires.
 */
const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

(async () => {
  const outputArg = process.argv.find(a => a.startsWith('--output='));
  const accountArg = process.argv.find(a => a.startsWith('--account='));

  let authPath;
  if (outputArg) {
    authPath = path.resolve(process.cwd(), outputArg.slice('--output='.length));
  } else if (accountArg) {
    const account = accountArg.slice('--account='.length);
    authPath = path.join(__dirname, '..', '..', '.auth', `${account}.json`);
  } else {
    authPath = path.join(__dirname, '..', '..', '.auth', 'user.json');
  }
  fs.mkdirSync(path.dirname(authPath), { recursive: true });

  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  console.log(`Saving session to: ${authPath}`);
  console.log('Log in to Google in the browser window, then press Enter here...');
  await page.goto('https://accounts.google.com');
  await new Promise(r => process.stdin.once('data', r));

  await context.storageState({ path: authPath });
  console.log(`Auth saved to ${authPath}`);
  await browser.close();
  process.exit(0);
})();
