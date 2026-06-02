/**
 * One-time Google auth capture. Run manually:
 *   node tests/playwright/auth.setup.js                        # saves to .auth/user.json
 *   node tests/playwright/auth.setup.js --output=.auth/user2.json  # saves to custom path
 *
 * Re-run only when the session expires.
 */
const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

(async () => {
  const outputArg = process.argv.find(a => a.startsWith('--output='));
  const authPath = outputArg
    ? path.resolve(process.cwd(), outputArg.slice('--output='.length))
    : path.join(__dirname, '..', '..', '.auth', 'user.json');
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
