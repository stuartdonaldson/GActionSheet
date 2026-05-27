const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const { clearLogs, openDocSidebar, waitForLogEntry } = require('./addon_helpers');

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

test('homepage card renders action rows and refreshes after sync', async ({ page }) => {
  const settings = loadSettings();
  const docId = await createBlankDoc(page);

  await invokeFixture('uc_a_permutations', docId, settings);

  await openDocSidebar(page, docId);
  let addonFrame = await findAddonFrame(page);

  await expect(addonFrame.getByText(/actions for this document \(3\)/i)).toBeVisible({ timeout: 30000 });
  await expect(addonFrame.getByText(/Perm: Schedule the kickoff/i)).toBeVisible();
  await expect(addonFrame.getByText(/Perm: Draft the committee agenda/i)).toBeVisible();
  await expect(addonFrame.getByText(/Perm: Review the meeting minutes/i)).toBeVisible();
  await expect(addonFrame.getByText(/Needs sync/i).first()).toBeVisible();

  await addonFrame.getByRole('button', { name: /sync now/i }).click();

  addonFrame = await findAddonFrame(page);
  await expect(addonFrame.getByText(/actions for this document \(3\)/i)).toBeVisible({ timeout: 30000 });
  await expect(addonFrame.getByText(/Anchored/i).first()).toBeVisible({ timeout: 30000 });
  await expect(addonFrame.getByText(/Perm: Schedule the kickoff/i)).toBeVisible();
});

test('sync now refreshes an existing tracker table', async ({ page }) => {
  const settings = loadSettings();
  const docId = await createBlankDoc(page);

  await invokeFixture('uc_c_pending_sync_refresh', docId, settings);

  await openDocSidebar(page, docId);
  const addonFrame = await findAddonFrame(page);

  await expect(addonFrame.getByRole('button', { name: /^Insert tracker$/i })).toHaveCount(0);
  await expect(addonFrame.getByText(/tracker already present in this document/i)).toBeVisible({ timeout: 10000 });
  clearLogs();
  await addonFrame.getByRole('button', { name: /sync now/i }).click();
  await waitForLogEntry(entry => {
    if (entry.tag !== 'sync.complete') return false;
    const entryDocId = entry.data && entry.data.docId;
    return !entryDocId || entryDocId === docId;
  }, 60000);

  const consistency = await invokeFixture('verify_consistency', docId, settings);
  expect(consistency.data.counts.floating).toBe(3);
  expect(consistency.data.counts.tracker).toBe(3);
  expect(consistency.data.counts.matched).toBe(3);
});