/**
 * Helpers for driving the Workspace Add-on sidebar in a Google Doc.
 *
 * Usage (CLI):
 *   node addon_helpers.js sync <docId>
 *
 * Exit codes:
 *   0  — sync.complete log entry detected within timeout
 *   1  — error (message written to stderr)
 *
 * The sidebar is opened via Extensions > Action Sync > Open.
 * "Sync now" is clicked inside the sidebar iframe.
 * Completion is detected by polling gasLogDir for a sync.complete entry.
 */

const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const settings = JSON.parse(
  fs.readFileSync(path.join(__dirname, '..', '..', 'local.settings.json'), 'utf8')
);
const storageState = path.join(__dirname, '..', '..', '.auth', 'user.json');
const gasLogDir = settings.gasLogDir;

// ---------------------------------------------------------------------------
// Log polling
// ---------------------------------------------------------------------------

function clearLogs() {
  if (!gasLogDir || !fs.existsSync(gasLogDir)) return;
  for (const name of fs.readdirSync(gasLogDir)) {
    if (name.endsWith('.log')) fs.rmSync(path.join(gasLogDir, name), { force: true });
  }
}

function waitForLogEntry(tagPredicate, timeoutMs = 60000, intervalMs = 500) {
  return new Promise((resolve, reject) => {
    if (!gasLogDir || !fs.existsSync(gasLogDir)) {
      return reject(new Error(`gasLogDir not set or does not exist: ${gasLogDir}`));
    }
    const deadline = Date.now() + timeoutMs;
    function poll() {
      if (Date.now() >= deadline) {
        return reject(new Error(`Timed out after ${timeoutMs}ms waiting for log entry`));
      }
      let found = null;
      try {
        const files = fs.readdirSync(gasLogDir).filter(f => f.endsWith('.log')).sort();
        outer: for (const name of files) {
          const text = fs.readFileSync(path.join(gasLogDir, name), 'utf8');
          for (const line of text.split('\n')) {
            const t = line.trim();
            if (!t) continue;
            let entry;
            try { entry = JSON.parse(t); } catch { continue; }
            if (tagPredicate(entry)) { found = entry; break outer; }
          }
        }
      } catch { /* transient I/O — keep polling */ }
      if (found) resolve(found);
      else setTimeout(poll, intervalMs);
    }
    poll();
  });
}

// ---------------------------------------------------------------------------
// Sidebar helpers
// ---------------------------------------------------------------------------

/**
 * Open the Google Doc and launch the Action Sync sidebar.
 *
 * @param {import('@playwright/test').Page} page
 * @param {string} docId
 */
async function openDocSidebar(page, docId) {
  const docUrl = `https://docs.google.com/document/d/${docId}/edit`;
  if (!page.url().startsWith(docUrl.replace('/edit', ''))) {
    await page.goto(docUrl);
  }
  await page.waitForSelector('.docs-title-outer', { timeout: 30000 });

  // Extensions > Action Sync (add-on menu trigger)
  await page.getByRole('menuitem', { name: 'Extensions' }).click();
  const addonTrigger = page.locator('[role="menuitem"]').filter({ hasText: 'Action Sync' }).first();
  await addonTrigger.waitFor({ timeout: 10000 });
  await addonTrigger.hover();

  // Click "Open" in the add-on submenu
  await page.getByRole('menuitem', { name: 'Open', exact: true }).waitFor({ timeout: 5000 });
  await page.getByRole('menuitem', { name: 'Open', exact: true }).click();

  // Allow sidebar iframe to initialize
  await page.waitForTimeout(3000);
}

/**
 * Click "Sync now" in the sidebar iframe and wait for sync.complete log entry.
 *
 * @param {import('@playwright/test').Page} page
 * @param {string} [docId]  Optional — used to filter log by docId if present.
 * @param {number} [timeoutMs]
 * @returns {Promise<object>}  The sync.complete log entry.
 */
async function clickSyncNow(page, docId, timeoutMs = 60000) {
  const sidebarFrame = page.frameLocator('iframe[src*="script.googleusercontent.com"], iframe[src*="script.google.com"]').first();
  await sidebarFrame.getByRole('button', { name: /sync now/i }).waitFor({ timeout: 15000 });
  await sidebarFrame.getByRole('button', { name: /sync now/i }).click();

  return waitForLogEntry(entry => {
    if (entry.tag !== 'sync.complete') return false;
    if (!docId) return true;
    const entryDocId = entry.data && entry.data.docId;
    return !entryDocId || entryDocId === docId;
  }, timeoutMs);
}

/**
 * Read sidebar action rows (if the sidebar exposes them as DOM elements).
 * Returns an array of { assignee, action, status } objects.
 * Returns empty array if the sidebar DOM is not accessible (cross-origin).
 *
 * @param {import('@playwright/test').Page} page
 * @returns {Promise<Array<{assignee: string, action: string, status: string}>>}
 */
async function sidebarActionRows(page) {
  try {
    const sidebarFrame = page.frameLocator('iframe[src*="script.googleusercontent.com"], iframe[src*="script.google.com"]').first();
    // Action rows are rendered as list items with data-action-id attribute.
    const rows = await sidebarFrame.locator('[data-action-id]').all();
    const result = [];
    for (const row of rows) {
      result.push({
        assignee: await row.locator('[data-field="assignee"]').textContent().catch(() => ''),
        action:   await row.locator('[data-field="action"]').textContent().catch(() => ''),
        status:   await row.locator('[data-field="status"]').textContent().catch(() => ''),
      });
    }
    return result;
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// CLI entry-point
// ---------------------------------------------------------------------------

if (require.main === module) {
  const command = process.argv[2];
  const docId   = process.argv[3] || settings.testDocId;

  if (command === 'sync') {
    (async () => {
      clearLogs();
      const browser = await chromium.launch({ headless: false });
      const context = await browser.newContext({ storageState });
      const page    = await context.newPage();
      try {
        await openDocSidebar(page, docId);
        const entry = await clickSyncNow(page, docId);
        process.stdout.write(JSON.stringify(entry) + '\n');
        process.exit(0);
      } catch (e) {
        process.stderr.write(e.message + '\n');
        process.exit(1);
      } finally {
        await browser.close();
      }
    })();
  } else {
    process.stderr.write(`Unknown command: ${command}\nUsage: node addon_helpers.js sync <docId>\n`);
    process.exit(1);
  }
}

module.exports = { openDocSidebar, clickSyncNow, sidebarActionRows, clearLogs, waitForLogEntry };
