/**
 * Reusable helpers for driving the Google Sheet menu and Apps Script editor.
 * Pattern: gas-sheet-menu-testing (headless: false required).
 */

const fs = require('fs');
const path = require('path');

function _loadSettings() {
  return JSON.parse(
    fs.readFileSync(path.join(__dirname, '..', '..', 'local.settings.json'), 'utf8')
  );
}

function _editorUrl() {
  const settings = _loadSettings();
  return `https://script.google.com/d/${settings.scriptId}/edit`;
}

function _sheetUrl() {
  const settings = _loadSettings();
  return `https://docs.google.com/spreadsheets/d/${settings.testSheetId}/edit`;
}

async function waitForEditorReady(page) {
  await page.getByRole('listbox', { name: 'Select function to run' }).waitFor({ timeout: 30000 });
}

async function selectFunction(page, funcName) {
  const picker = page.getByRole('listbox', { name: 'Select function to run' });
  const option = picker.getByRole('option', { name: funcName, exact: true });
  const isSelected = await option.getAttribute('aria-selected').catch(() => null);
  if (isSelected !== 'true') await option.click();
}

async function runAndWait(page) {
  await page.getByRole('button', { name: 'Run the selected function' }).click();
  await page.getByRole('button', { name: 'Open the execution log panel' }).click();
  await page.locator('text=/Execution (completed|failed)/').first().waitFor({ timeout: 90000 });
  const failed = await page.locator('text=Execution failed').count();
  if (failed > 0) throw new Error('GAS execution failed — check execution log');
}

async function captureLogText(page) {
  const UI_CHROME = new Set(['close', 'Close execution logs', 'Execution log']);
  const lines = await page.locator('.execution-log-panel .log-line').allTextContents().catch(() => []);
  return lines.filter(l => l.trim() && !UI_CHROME.has(l.trim()));
}

async function runFunction(page, funcName) {
  const editorUrl = _editorUrl();
  if (!page.url().startsWith(editorUrl.replace('/edit', ''))) {
    await page.goto(editorUrl);
  }
  await waitForEditorReady(page);
  await selectFunction(page, funcName);
  await runAndWait(page);
  return captureLogText(page);
}

/**
 * Invoke a GAS function via the Sheet's custom menu.
 * Navigates to the sheet if not already there, then clicks menuName → itemName.
 * Returns immediately after the click — the caller polls for side-effects (e.g. log files).
 *
 * @param {import('@playwright/test').Page} page
 * @param {string} menuName  Top-level menu label (e.g. 'Action Sync')
 * @param {string} itemName  Menu item label (e.g. 'Sync')
 */
async function runViaSheetMenu(page, menuName, itemName) {
  const sheetUrl = _sheetUrl();
  if (!page.url().startsWith(sheetUrl.replace('/edit', ''))) {
    await page.goto(sheetUrl);
  }

  // Wait for the spreadsheet chrome, then for the script menu to appear
  await page.waitForSelector('.docs-title-outer', { timeout: 30000 });
  await page.getByText(menuName, { exact: true }).waitFor({ timeout: 15000 });
  await page.getByText(menuName, { exact: true }).click();

  // Menu items in Sheets custom menus use goog-menuitem (role=menuitem)
  await page.getByRole('menuitem', { name: itemName, exact: true }).waitFor({ timeout: 5000 });
  await page.getByRole('menuitem', { name: itemName, exact: true }).click();
}

module.exports = { waitForEditorReady, selectFunction, runAndWait, captureLogText, runFunction, runViaSheetMenu };
