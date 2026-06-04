const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const { openDocSidebar } = require('./addon_helpers');

const manifest = JSON.parse(
  fs.readFileSync(path.join(__dirname, '..', '..', 'src', 'appsscript.json'), 'utf8')
);
const ADDON_NAME = manifest.addOns.common.name;

function loadSettings() {
  return JSON.parse(
    fs.readFileSync(path.join(__dirname, '..', '..', 'local.settings.json'), 'utf8')
  );
}

async function invokeFixture(fixture, testDocId, settings) {
  const response = await fetch(settings.webappTestUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      action: 'run_fixture',
      testToken: settings.testToken,
      fixture,
      testDocId,
    }),
  });

  const raw = await response.text();
  if (raw === 'test-token-unauthorized' || raw === 'test-token-expired') {
    throw new Error(`Fixture token rejected for ${fixture}: ${raw}`);
  }

  const result = JSON.parse(raw);
  if (result.error) {
    throw new Error(`Fixture ${fixture} failed: ${result.error}`);
  }
  return result;
}

async function findAddonFrame(page, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  let refreshAttempted = false;

  while (Date.now() < deadline) {
    for (const frame of page.frames()) {
      const syncNow = frame.getByRole('button', { name: /sync now/i });
      if (await syncNow.count().catch(() => 0)) {
        return frame;
      }
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

async function createBlankDoc(page) {
  await page.goto('https://docs.google.com/document/create');
  await page.waitForURL(/\/document\/d\/[a-zA-Z0-9_-]+\/edit/, { timeout: 30000 });
  await page.waitForSelector('.docs-title-outer', { timeout: 30000 });

  const match = page.url().match(/\/document\/d\/([a-zA-Z0-9_-]+)\/edit/);
  if (!match) {
    throw new Error(`Could not determine doc ID from URL: ${page.url()}`);
  }

  return match[1];
}

async function openSidebarInCurrentDoc(page) {
  await page.waitForSelector('.docs-title-outer', { timeout: 30000 });

  const panelIcon = page.locator(`[aria-label="${ADDON_NAME}"]`).first();
  try {
    await panelIcon.waitFor({ state: 'visible', timeout: 15000 });
    await panelIcon.click();
  } catch {
    throw new Error('Action Sync side-panel icon was not available');
  }

  await page.waitForTimeout(5000);
}

test('homepage card stays single-surface and shows card controls', async ({ page }) => {
  const settings = loadSettings();
  const docId = await createBlankDoc(page);

  await invokeFixture('uc_c_first_insert', docId, settings);
  await openSidebarInCurrentDoc(page);

  const addonFrame = await findAddonFrame(page);

  await expect(addonFrame.getByRole('button', { name: /sync now/i })).toBeVisible({ timeout: 30000 });
  await expect(addonFrame.getByRole('button', { name: /verifysync/i })).toBeVisible({ timeout: 30000 });
  await expect(addonFrame.getByRole('button', { name: /open sidebar/i })).toHaveCount(0);
  await expect(addonFrame.getByRole('button', { name: /scan card/i })).toHaveCount(0);
  await expect(addonFrame.getByText(/^Sort$/i)).toHaveCount(0);
  await expect(addonFrame.getByText(/^Filter$/i)).toHaveCount(0);
  await expect(addonFrame.getByText(/^Tracker$/i)).toHaveCount(0);
  await expect(addonFrame.getByText(/sync status:/i).first()).toBeVisible({ timeout: 10000 });
  await expect(addonFrame.getByText(/actions for this document/i)).toBeVisible({ timeout: 10000 });
  await expect(addonFrame.getByText(/^v\d+\.\d+\.\d+/i)).toBeVisible({ timeout: 10000 });
  await expect(addonFrame.getByRole('button', { name: /^Insert tracker$/i })).toHaveCount(0);
  await expect(addonFrame.getByText(/tracker already present in this document/i)).toBeVisible({ timeout: 10000 });
});

test('homepage card opens in a brand-new blank doc without a runtime error', async ({ page }) => {
  test.setTimeout(90000);
  await createBlankDoc(page);
  await openSidebarInCurrentDoc(page);

  const addonFrame = await findAddonFrame(page, 30000);

  await expect(addonFrame.getByText(/error with the add-on/i)).toHaveCount(0);
  await expect(addonFrame.getByText(/run time error/i)).toHaveCount(0);
  await expect(addonFrame.getByRole('button', { name: /sync now/i })).toBeVisible({ timeout: 15000 });
});