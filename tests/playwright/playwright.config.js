const { defineConfig } = require('@playwright/test');
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

function getSheetUrl() {
  if (process.env.SHEET_ID) return sheetUrl(process.env.SHEET_ID);
  const settings = loadSettings();
  return sheetUrl(settings.testSheetId);
}

function sheetUrl(sheetId) {
  return `https://docs.google.com/spreadsheets/d/${sheetId}/edit`;
}

function loadSettings() {
  const p = path.join(__dirname, '..', '..', 'local.settings.json');
  if (!fs.existsSync(p)) throw new Error('local.settings.json not found');
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

module.exports = defineConfig({
  testDir: '.',
  timeout: 120000,
  expect: { timeout: 10000 },
  fullyParallel: false,
  workers: 1,
  retries: 1,
  use: {
    baseURL: getSheetUrl(),
    headless: false,
    storageState: path.join(__dirname, '..', '..', '.auth', 'user.json'),
    viewport: { width: 1280, height: 900 },
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
});
