const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const { openDocSidebar } = require('./addon_helpers');

function loadSettings() {
  return JSON.parse(
    fs.readFileSync(path.join(__dirname, '..', '..', 'local.settings.json'), 'utf8')
  );
}

async function findAddonFrame(page, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    for (const frame of page.frames()) {
      const syncNow = frame.getByRole('button', { name: /sync now/i });
      if (await syncNow.count().catch(() => 0)) {
        return frame;
      }
    }
    await page.waitForTimeout(500);
  }

  throw new Error('Timed out locating add-on frame with Sync now control');
}

test('homepage card stays single-surface and shows card controls', async ({ page }) => {
  const settings = loadSettings();
  await openDocSidebar(page, settings.testDocId);

  const addonFrame = await findAddonFrame(page);

  await expect(addonFrame.getByRole('button', { name: /scan card/i })).toBeVisible({ timeout: 30000 });
  await expect(addonFrame.getByRole('button', { name: /sync now/i })).toBeVisible({ timeout: 30000 });
  await expect(addonFrame.getByRole('button', { name: /verifysync/i })).toBeVisible({ timeout: 30000 });
  await expect(addonFrame.getByRole('button', { name: /open sidebar/i })).toHaveCount(0);
  await expect(addonFrame.getByText(/^Sort$/i).first()).toBeVisible({ timeout: 10000 });
  await expect(addonFrame.getByText(/^Filter$/i).first()).toBeVisible({ timeout: 10000 });
  await expect(addonFrame.getByText(/actions for this document/i)).toBeVisible({ timeout: 10000 });
  await expect(addonFrame.getByText(/^v0\.1\.0/i)).toBeVisible({ timeout: 10000 });
});