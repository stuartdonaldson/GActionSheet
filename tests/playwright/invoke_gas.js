/**
 * Invoke a GAS menu item via the Google Sheet custom menu.
 *
 * Usage:
 *   node invoke_gas.js <menuItem> [arg]
 *
 * If [arg] is provided, it is written to TestControl!A1 before the menu click
 * so the GAS handler can read it as its argument.
 *
 * Exit codes:
 *   0  — menu item clicked successfully
 *   1  — error (message written to stderr)
 *
 * Examples:
 *   node invoke_gas.js "Test: Setup Fixture" "ac1"
 *   node invoke_gas.js "Test: Sync Document" "1BxiM..."
 *   node invoke_gas.js "Sync"
 */

const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const settings = JSON.parse(
  fs.readFileSync(path.join(__dirname, '..', '..', 'local.settings.json'), 'utf8')
);
const storageState = path.join(__dirname, '..', '..', '.auth', 'user.json');

const menuItem = process.argv[2];
const arg = process.argv[3];

if (!menuItem) {
  console.error('Usage: node invoke_gas.js <menuItem> [arg]');
  process.exit(1);
}

(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ storageState });
  const page = await context.newPage();

  const sheetUrl = `https://docs.google.com/spreadsheets/d/${settings.testSheetId}/edit`;
  await page.goto(sheetUrl);
  await page.waitForSelector('.docs-title-outer', { timeout: 30000 });
  await page.getByText('Action Sync', { exact: true }).waitFor({ timeout: 15000 });

  if (arg !== undefined) {
    // Write arg to TestControl!A1 via the Name Box
    const nameBox = page.locator('[aria-label="Name Box"]');
    await nameBox.click();
    await page.keyboard.press('Control+a');
    await page.keyboard.type('TestControl!A1');
    await page.keyboard.press('Enter');
    // Brief pause for sheet navigation to settle
    await page.waitForTimeout(600);
    // Type the value — this starts inline cell editing
    await page.keyboard.type(String(arg));
    await page.keyboard.press('Enter');
    await page.waitForTimeout(400);
  }

  // Click Action Sync > menuItem
  await page.getByText('Action Sync', { exact: true }).click();
  await page.getByRole('menuitem', { name: menuItem, exact: true }).waitFor({ timeout: 5000 });
  await page.getByRole('menuitem', { name: menuItem, exact: true }).click();

  // Allow the browser to dispatch the menu-click event before closing
  await page.waitForTimeout(1000);

  await browser.close();
  process.exit(0);
})().catch(e => {
  console.error(e.message);
  process.exit(1);
});
