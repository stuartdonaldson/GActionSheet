/**
 * Shared JavaScript helpers for Playwright tests.
 *
 * This module centralizes utilities used across multiple test files and configuration:
 * - Settings loading (loadSettings)
 * - Add-on frame discovery (findAddonFrame)
 * - Other common utilities
 *
 * Import in test files with: const { name, ... } = require('./_helpers');
 */

const fs = require('fs');
const path = require('path');

/**
 * Load local.settings.json with file-existence validation.
 * Throws an error if the file is not found.
 *
 * @returns {object} Parsed settings object
 */
function loadSettings() {
  const p = path.join(__dirname, '..', '..', 'local.settings.json');
  if (!fs.existsSync(p)) {
    throw new Error('local.settings.json not found');
  }
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

/**
 * Poll all page frames until one contains the "Sync now" button, handling
 * the GAS cold-start "Refresh" button if it appears first.
 *
 * @param {import('@playwright/test').Page} page
 * @param {number} [timeoutMs=30000]
 * @returns {Promise<Frame>} The frame containing the Sync now control
 * @throws {Error} If the frame is not found within the timeout
 */
async function findAddonFrame(page, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  let refreshAttempted = false;

  while (Date.now() < deadline) {
    for (const frame of page.frames()) {
      const syncNow = frame.getByRole('button', { name: /sync now/i });
      if (await syncNow.count().catch(() => 0)) return frame;
    }

    if (!refreshAttempted) {
      const refreshButton = page.getByRole('button', { name: /^Refresh$/i });
      if (await refreshButton.count().catch(() => 0)) {
        refreshAttempted = true;
        await refreshButton.click();
        await page.waitForTimeout(4000);
        continue;
      }
    }

    await page.waitForTimeout(500);
  }

  throw new Error('Timed out locating add-on frame with Sync now control');
}

module.exports = { loadSettings, findAddonFrame };
