const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const { openDocSidebar } = require('./addon_helpers');

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

test('homepage card renders action rows and refreshes after sync', async ({ page }) => {
  const settings = loadSettings();
  const session = await invokeFixture('begin_test_session', settings.testDocId, settings);
  const docId = session.data.cloneId;

  try {
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
  } finally {
    await invokeFixture('end_test_session', docId, settings).catch(() => {});
  }
});