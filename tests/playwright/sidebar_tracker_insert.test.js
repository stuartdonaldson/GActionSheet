/**
 * sidebar_tracker_insert.test.js — UC-C tracker table entry-point coverage.
 *
 * AC1: sidebar "Insert tracker" button inserts a table and full consistency passes.
 * AC2: after a status mutation and sync, tracker reflects only the changed row.
 * AC3: direct tracker cell edit is overwritten on re-insert (view-only enforcement).
 *
 * Bead: GTaskSheet-gxot
 */
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

async function invokeRoute(action, body, settings) {
  const response = await fetch(settings.webappTestUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, testToken: settings.testToken, ...body }),
  });
  const raw = await response.text();
  if (raw === 'test-token-unauthorized' || raw === 'test-token-expired') {
    throw new Error(`Route ${action} rejected token: ${raw}`);
  }
  const result = JSON.parse(raw);
  if (result.error) throw new Error(`Route ${action} failed: ${result.error}`);
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

// ─────────────────────────────────────────────────────────────────────────────
// AC1: sidebar "Insert tracker" button inserts table; full consistency passes
// ─────────────────────────────────────────────────────────────────────────────

test('sidebar Insert tracker button inserts table and consistency passes', async ({ page }) => {
  test.setTimeout(180000);
  const settings = loadSettings();
  const docId = await createBlankDoc(page);

  // uc_a_permutations seeds 3 floating actions but does NOT insert a tracker table.
  await invokeFixture('uc_a_permutations', docId, settings);

  await openDocSidebar(page, docId);
  let addonFrame = await findAddonFrame(page);

  // Sync floating actions so they become Anchored (required for Insert tracker to appear).
  clearLogs();
  await addonFrame.getByRole('button', { name: /sync now/i }).click();
  await waitForLogEntry(
    e => e.tag === 'sync.complete' && (!e.data?.docId || e.data.docId === docId),
    60000
  );

  addonFrame = await findAddonFrame(page);

  // Insert tracker button must be visible — asserts the user-facing entry point (AC1).
  await expect(addonFrame.getByRole('button', { name: /^Insert tracker$/i }))
    .toBeVisible({ timeout: 10000 });

  // Click the sidebar "Insert tracker" button — this is the entry point under test.
  await addonFrame.getByRole('button', { name: /^Insert tracker$/i }).click();

  // After insert the card refreshes; "tracker already present" confirms the table was written.
  addonFrame = await findAddonFrame(page);
  await expect(addonFrame.getByText(/tracker already present in this document/i))
    .toBeVisible({ timeout: 30000 });

  // Full consistency: content correct and structurally complete.
  // Every floating action must appear in the tracker; every tracker row must match
  // a floating action. Do not assert a specific count — that is the fixture's concern.
  const consistency = await invokeFixture('verify_consistency', docId, settings);
  const { counts, tracker: ctTracker, issues: ctIssues, ok: ctOk } = consistency.data;
  expect(ctOk, ctIssues?.join('\n')).toBe(true);
  expect(ctIssues).toHaveLength(0);
  expect(counts.tracker).toBe(counts.floating);
  expect(counts.matched).toBe(counts.floating);

  // Per-row field check — every tracker row must have non-empty id, action, status.
  expect(ctTracker.rows.length).toBeGreaterThan(0);
  for (const row of ctTracker.rows) {
    expect(row.id).toBeTruthy();
    expect(row.action).toBeTruthy();
    expect(row.status).toBeTruthy();
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// AC2: after a status mutation and sync, tracker reflects only the changed row
// ─────────────────────────────────────────────────────────────────────────────

test('sync refreshes tracker after status mutation and only mutated row differs', async ({ page }) => {
  test.setTimeout(180000);
  const settings = loadSettings();
  const docId = await createBlankDoc(page);

  // uc_c_pending_sync_refresh seeds 3 anchored actions with a tracker already present.
  await invokeFixture('uc_c_pending_sync_refresh', docId, settings);

  await openDocSidebar(page, docId);
  let addonFrame = await findAddonFrame(page);

  // Sync the 3rd pending floating action; insertTrackerTable runs as part of
  // sync, so the tracker grows from 2 → 3 rows before we take the baseline.
  clearLogs();
  await addonFrame.getByRole('button', { name: /sync now/i }).click();
  await waitForLogEntry(
    e => e.tag === 'sync.complete' && (!e.data?.docId || e.data.docId === docId),
    60000
  );

  addonFrame = await findAddonFrame(page);
  await expect(addonFrame.getByText(/tracker already present in this document/i))
    .toBeVisible({ timeout: 10000 });

  // Baseline: capture tracker rows and confirm consistency before mutation.
  const baseline = await invokeFixture('verify_consistency', docId, settings);
  expect(baseline.data.ok, baseline.data.issues?.join('\n')).toBe(true);
  const baselineRows = baseline.data.tracker.rows;
  expect(baselineRows).toHaveLength(3);

  // Pick the first tracker row and mutate its status.
  const targetRow = baselineRows[0];
  const targetActionId = targetRow.id;           // e.g. "AI-5"
  const targetGlobalId = `${docId}/${targetActionId}`;
  const originalStatus = targetRow.status || 'Open';
  const newStatus = originalStatus === 'Open' ? 'In Progress' : 'Open';

  await invokeRoute('edit_action_row', {
    global_id: targetGlobalId,
    fields: { status: newStatus },
  }, settings);

  // Re-sync: propagates the sheet mutation to the doc and refreshes the tracker.
  clearLogs();
  addonFrame = await findAddonFrame(page);
  await addonFrame.getByRole('button', { name: /sync now/i }).click();
  await waitForLogEntry(
    e => e.tag === 'sync.complete' && (!e.data?.docId || e.data.docId === docId),
    60000
  );

  // Post-mutation consistency: ok=true, no issues, same row count as baseline.
  const postMutation = await invokeFixture('verify_consistency', docId, settings);
  expect(postMutation.data.ok, postMutation.data.issues?.join('\n')).toBe(true);
  expect(postMutation.data.issues).toHaveLength(0);
  expect(postMutation.data.counts.tracker).toBe(baselineRows.length);
  expect(postMutation.data.counts.matched).toBe(baselineRows.length);

  // Exactly one row has the new status; all other rows are field-identical to baseline.
  let mutatedCount = 0;
  for (const postRow of postMutation.data.tracker.rows) {
    if (String(postRow.id) === String(targetActionId)) {
      expect(postRow.status).toBe(newStatus);
      mutatedCount++;
    } else {
      const baseRow = baselineRows.find(b => b.id === postRow.id);
      if (baseRow) {
        expect(postRow.action).toBe(baseRow.action);
        expect(postRow.status).toBe(baseRow.status);
        expect(postRow.assignee).toBe(baseRow.assignee);
      }
    }
  }
  expect(mutatedCount).toBe(1);
});

// ─────────────────────────────────────────────────────────────────────────────
// AC3: direct tracker cell edit is overwritten on re-insert (view-only enforcement)
// ─────────────────────────────────────────────────────────────────────────────

test('direct tracker cell edit is overwritten on re-insert', async ({ page }) => {
  test.setTimeout(120000);
  const settings = loadSettings();
  const docId = await createBlankDoc(page);

  // uc_c_view_only: seeds actions, syncs, inserts tracker, directly edits a cell,
  // then calls insertTrackerTable again.  The edit must be discarded by the re-insert.
  await invokeFixture('uc_c_view_only', docId, settings);

  // After the fixture the tracker should be consistent; no cell should retain '-EDITED'.
  const consistency = await invokeFixture('verify_consistency', docId, settings);
  expect(consistency.data.ok, consistency.data.issues?.join('\n')).toBe(true);
  expect(consistency.data.issues).toHaveLength(0);

  const trackerRows = consistency.data.tracker?.rows || [];
  expect(trackerRows.length).toBeGreaterThan(0);
  for (const row of trackerRows) {
    for (const [field, value] of Object.entries(row)) {
      expect(
        String(value ?? '').includes('-EDITED'),
        `Tracker row field '${field}' still contains stale cell edit: "${value}"`
      ).toBe(false);
    }
  }
});
