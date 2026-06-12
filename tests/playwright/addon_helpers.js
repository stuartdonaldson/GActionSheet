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
 * The sidebar is opened via the add-on panel icon in the Google Docs right-hand
 * column. The icon's aria-label matches addOns.common.name in src/appsscript.json.
 * "Sync now" is clicked inside the sidebar iframe.
 * Completion is detected by polling gasLogDir for a sync.complete entry.
 */

const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const settings = JSON.parse(
  fs.readFileSync(path.join(__dirname, '..', '..', 'local.settings.json'), 'utf8')
);
// Override with PROBE_AUTH_STATE to run as a different account (e.g. user2.json).
const storageState = process.env.PROBE_AUTH_STATE
  ? path.resolve(process.cwd(), process.env.PROBE_AUTH_STATE)
  : path.join(__dirname, '..', '..', '.auth', 'user.json');
const gasLogDir = settings.gasLogDir;

// Add-on display name — must match addOns.common.name in src/appsscript.json.
// Google Docs uses this as the aria-label for the panel icon in the right column.
const manifest = JSON.parse(
  fs.readFileSync(path.join(__dirname, '..', '..', 'src', 'appsscript.json'), 'utf8')
);
const ADDON_NAME = manifest.addOns.common.name;

// ---------------------------------------------------------------------------
// Log polling
// ---------------------------------------------------------------------------

/**
 * Move all .log files in gasLogDir into gasLogDir/archive/<timestamp>/ and
 * return a fence epoch-ms value. Pass the returned value to waitForLogEntry as
 * `after` to ignore stale entries written by a previous or concurrent GAS run.
 *
 * Archiving (not deleting) preserves historical runs for trend analysis.
 * The fence is set 10 s before now to absorb GAS-server / local clock skew.
 */
function clearLogs() {
  const fence = Date.now() - 10000;
  if (!gasLogDir || !fs.existsSync(gasLogDir)) return fence;
  const logs = fs.readdirSync(gasLogDir).filter(n => n.endsWith('.log'));
  if (logs.length === 0) return fence;
  const archiveDir = path.join(
    __dirname, '..', '..', 'test-results', 'gas-logs',
    new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19),
  );
  fs.mkdirSync(archiveDir, { recursive: true });
  for (const name of logs) {
    fs.copyFileSync(path.join(gasLogDir, name), path.join(archiveDir, name));
    fs.rmSync(path.join(gasLogDir, name), { force: true });
  }
  return fence;
}

/**
 * @param {function} tagPredicate  Predicate applied to each parsed log entry.
 * @param {number}   timeoutMs     Total wait budget in ms (default 60 000).
 * @param {number}   intervalMs    Poll interval in ms (default 500).
 * @param {number}   after         Epoch-ms fence: skip entries whose ts predates
 *                                 this value. Pass the return value of clearLogs()
 *                                 to filter out stale entries from concurrent runs.
 */
function waitForLogEntry(tagPredicate, timeoutMs = 60000, intervalMs = 500, after = 0) {
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
            if (after && entry.ts && Date.parse(entry.ts) < after) continue;
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

  // The panel icon aria-label matches addOns.common.name in src/appsscript.json.
  // If that name ever changes, update ADDON_NAME here or derive it dynamically.
  const panelIcon = page.locator(`[aria-label="${ADDON_NAME}"]`).first();
  await panelIcon.waitFor({ state: 'visible', timeout: 15000 });
  await panelIcon.click();

  // Allow sidebar iframe to load — GAS cold start can take 15-20s.
  await page.waitForTimeout(5000);
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
  await sidebarFrame.getByRole('button', { name: /sync now/i }).waitFor({ timeout: 30000 });
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
      const headless = !process.argv.includes('--headed');
      const browser = await chromium.launch({ headless });
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
