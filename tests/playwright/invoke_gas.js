/**
 * Invoke a GAS menu item via the Google Sheet custom menu.
 *
 * Usage:
 *   node invoke_gas.js <menuItem> [arg] [--parent=<submenu>]
 *
 * --parent=<submenu>  Navigate into a submenu before clicking <menuItem>.
 *                     E.g. --parent="Setup" for items under Action Sync > Setup.
 *
 * If [arg] is provided (and is not a --flag), it is written to TestControl!A1
 * before the menu click so the GAS handler can read it as its argument.
 *
 * Exit codes:
 *   0  — menu item clicked successfully
 *   1  — error (message written to stderr)
 *
 * Examples:
 *   node invoke_gas.js "Test: Setup Fixture" "ac1"
 *   node invoke_gas.js "Test: Sync Document" "1BxiM..."
 *   node invoke_gas.js "Sync"
 *   node invoke_gas.js "Ensure Sheet Structure" --parent="Setup"
 *   node invoke_gas.js "Initialize Triggers" --parent="Setup"
 */

const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const settings = JSON.parse(
  fs.readFileSync(path.join(__dirname, '..', '..', 'local.settings.json'), 'utf8')
);
const storageState = path.join(__dirname, '..', '..', '.auth', 'user.json');

const menuItem = process.argv[2];

// Parse remaining args: --parent=<name> flags vs positional arg for TestControl
let parentMenu = null;
let arg = undefined;
for (let i = 3; i < process.argv.length; i++) {
  const a = process.argv[i];
  const m = a.match(/^--parent=(.+)$/);
  if (m) {
    parentMenu = m[1];
  } else {
    arg = a;
  }
}

if (!menuItem) {
  console.error('Usage: node invoke_gas.js <menuItem> [arg] [--parent=<submenu>]');
  process.exit(1);
}

(async () => {
  const headless = !process.argv.includes('--headed');
  const browser = await chromium.launch({ headless });
  const context = await browser.newContext({ storageState });
  const page = await context.newPage();

  const sheetUrl = `https://docs.google.com/spreadsheets/d/${settings.testSheetId}/edit`;
  await page.goto(sheetUrl);
  await page.waitForSelector('.docs-title-outer', { timeout: 30000 });
  await page.getByText('Action Sync', { exact: true }).waitFor({ timeout: 15000 });

  if (arg !== undefined) {
    // Navigate to TestControl sheet tab and write arg to A1.
    const testControlTab = page.locator('.docs-sheet-tab-name').filter({ hasText: /^TestControl$/ });
    await testControlTab.waitFor({ timeout: 10000 });
    await testControlTab.click();
    await page.waitForTimeout(500);

    await page.keyboard.press('Escape');
    await page.keyboard.press('Control+Home');
    await page.waitForTimeout(300);
    await page.keyboard.type(String(arg));
    await page.keyboard.press('Enter');
    await page.waitForTimeout(400);
  }

  // Click Action Sync top-level menu
  await page.getByText('Action Sync', { exact: true }).click();

  if (parentMenu) {
    // Hover into the submenu. Use a text filter rather than exact role name match
    // because Google Sheets appends a ► arrow to submenu items' accessible names.
    const submenuTrigger = page.locator('[role="menuitem"]').filter({ hasText: parentMenu }).first();
    await submenuTrigger.waitFor({ timeout: 5000 });
    await submenuTrigger.hover();
    await page.waitForTimeout(400);
  }

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
