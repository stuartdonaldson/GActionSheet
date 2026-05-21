/**
 * One-time Google auth capture. Run manually:
 *   node tests/playwright/auth.setup.js
 *
 * Saves session to .auth/user.json (gitignored).
 * Re-run only when the session expires.
 */
const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

(async () => {
  const authPath = path.join(__dirname, '..', '..', '.auth', 'user.json');
  fs.mkdirSync(path.dirname(authPath), { recursive: true });

  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  console.log('Log in to Google in the browser window, then press Enter here...');
  await page.goto('https://accounts.google.com');
  await new Promise(r => process.stdin.once('data', r));

  await context.storageState({ path: authPath });
  console.log(`Auth saved to ${authPath}`);
  await browser.close();
  process.exit(0);
})();
