/**
 * Smoke test: trigger syncAll via the Sheet "Action Sync > Sync" menu and confirm
 * a sync.complete log entry appears in the Drive-mapped log directory within 30 seconds.
 *
 * Prerequisites:
 *   - .auth/user.json present (run auth.setup.js once)
 *   - GAS deployed (clasp push)
 *   - gasLogDir in local.settings.json points to a Drive-for-Desktop folder
 *   - testSheetId in local.settings.json is the bound spreadsheet ID
 */

const { test, expect } = require('@playwright/test');
const { runViaSheetMenu } = require('./editor_helpers');
const { clearLogs, waitForLogEntry } = require('./addon_helpers');

test('syncDocument emits sync.complete log entry', async ({ page }) => {
  clearLogs();

  await runViaSheetMenu(page, 'Action Sync', 'Sync');

  const entry = await waitForLogEntry(e => e.tag === 'sync.complete', 60000);

  expect(entry).toBeTruthy();
  expect(entry.tag).toBe('sync.complete');
  expect(typeof entry.ts).toBe('string');
});
