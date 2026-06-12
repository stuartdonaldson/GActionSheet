/**
 * Navigate to the test sheet and wait for the Action Sync menu to appear,
 * confirming that onOpen() has run. Used by test_infrastructure.py to trigger
 * the menu.created log entry without going through the Apps Script editor.
 */
const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const settings = JSON.parse(
  fs.readFileSync(path.join(__dirname, '..', '..', 'local.settings.json'), 'utf8')
);
const storageState = path.join(__dirname, '..', '..', '.auth', 'user.json');

(async () => {
  const headless = !process.argv.includes('--headed');
  const browser = await chromium.launch({ headless });
  const context = await browser.newContext({ storageState });
  const page = await context.newPage();

  const sheetUrl = `https://docs.google.com/spreadsheets/d/${settings.testSheetId}/edit`;
  await page.goto(sheetUrl);
  await page.waitForSelector('.docs-title-outer', { timeout: 30000 });
  // Presence of the Action Sync menu confirms onOpen() completed
  await page.getByText('Action Sync', { exact: true }).waitFor({ timeout: 15000 });
  await browser.close();
  process.exit(0);
})().catch(e => {
  console.error(e.message);
  process.exit(1);
});
