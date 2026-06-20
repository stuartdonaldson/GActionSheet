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
// Override with PROBE_AUTH_STATE to run as a different account (e.g. test.u2.json).
const storageState = process.env.PROBE_AUTH_STATE
  ? path.resolve(process.cwd(), process.env.PROBE_AUTH_STATE)
  : path.join(__dirname, '..', '..', '.auth', 'user.json');
const gasLogDir = settings.gasLogDir;

// Backend resolved once, mirrors tests/helpers/gas_log.py::_backend(). 'axiom' iff
// axiomDataset+axiomQueryToken are both set in local.settings.json.
const LOG_BACKEND = (settings.axiomDataset && settings.axiomQueryToken) ? 'axiom' : 'file';

async function axiomQuery(afterMs) {
  const start = new Date(afterMs).toISOString();
  const end = new Date().toISOString();
  const apl = `['${settings.axiomDataset}'] | where side == 'gas' | order by _time asc | limit 500`;
  const resp = await fetch('https://api.axiom.co/v1/datasets/_apl?format=legacy', {
    method: 'POST',
    headers: { Authorization: `Bearer ${settings.axiomQueryToken}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ apl, startTime: start, endTime: end }),
  });
  if (!resp.ok) throw new Error(`Axiom query failed (${resp.status}): ${(await resp.text()).slice(0, 500)}`);
  const result = await resp.json();
  return (result.matches || []).map(m => {
    const data = { ...m.data };
    const tag = data.name;
    delete data.name; delete data.version; delete data.op; delete data.parentOp; delete data.side;
    return { ts: m._time, tag, data };
  });
}

// POST a sentinel through the real WebApp -> GAS -> GasLogger.flush() -> Axiom
// path (GTaskSheet-ishz.5's axiom_probe route) -- not a JS-direct-to-Axiom
// shortcut, which would skip the GAS/WebApp hop entirely.
async function postAxiomProbe(sentinel) {
  const resp = await fetch(settings.webappTestUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'axiom_probe', secret: settings.webappSecret, sentinel }),
  });
  if (!resp.ok) throw new Error(`axiom_probe POST failed (${resp.status})`);
}

async function waitForLogEntryAxiom(tagPredicate, timeoutMs, intervalMs, after) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const entries = await axiomQuery(after || 0);
    const found = entries.find(tagPredicate);
    if (found) return found;
    await new Promise(r => setTimeout(r, intervalMs));
  }
  throw new Error(`Timed out after ${timeoutMs}ms waiting for log entry (axiom backend)`);
}

// Sentinel-watermark absence check: a bare timeout is unsound against Axiom's
// ingest-to-queryable latency. POST a fresh sentinel now, wait until IT lands
// (proving ingest has caught up to "now"), then check the suspect tag is
// absent from everything observed up to that point.
async function assertNoLogAxiom(tagPredicate, after, what) {
  const sentinel = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  await postAxiomProbe(sentinel);
  const isSentinel = e => e.tag === 'test.axiom_probe' && e.data && e.data.sentinel === sentinel;
  try {
    await waitForLogEntryAxiom(isSentinel, 30000, 500, after);
  } catch {
    throw new Error(`sentinel-watermark probe never landed in Axiom within 30s -- cannot soundly assert absence (${what})`);
  }
  const entries = await axiomQuery(after || 0);
  const bad = entries.find(tagPredicate);
  if (bad) throw new Error(`unexpected log entry (${what}): ${JSON.stringify(bad)}`);
}

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
  if (LOG_BACKEND === 'axiom') return Date.now() - 2000;
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
  if (LOG_BACKEND === 'axiom') {
    return waitForLogEntryAxiom(tagPredicate, timeoutMs, Math.max(intervalMs, 1000), after);
  }
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

module.exports = { openDocSidebar, clickSyncNow, sidebarActionRows, clearLogs, waitForLogEntry, assertNoLogAxiom };
