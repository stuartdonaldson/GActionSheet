/**
 * Execute multiple GAS menu items in a single Playwright session.
 *
 * Commands are read from stdin as a JSON array:
 *   [{menuItem, arg?, parent?, awaitTag?, timeoutMs?}, ...]
 *
 * - arg: written to TestControl!A1 before the menu click (same as invoke_gas.js)
 * - parent: submenu name to hover into before clicking menuItem
 * - awaitTag: NDJSON log tag to wait for before proceeding to the next command.
 *             Logs are cleared before each click that has an awaitTag so that
 *             the poller only sees entries produced by that command.
 * - timeoutMs: per-command timeout for awaitTag polling (default 240000)
 *
 * Stdout: JSON object mapping awaitTag → log entry for every command that had
 * an awaitTag.  Commands without awaitTag are not represented in the output.
 *
 * Exit codes: 0 success, 1 error (message on stderr).
 *
 * Usage:
 *   echo '[{"menuItem":"Test: Setup Fixture","arg":"uc_c_first_insert","awaitTag":"fixture.uc_c_first_insert"}]' \
 *     | node invoke_gas_batch.js
 */

const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const settings = JSON.parse(
  fs.readFileSync(path.join(__dirname, '..', '..', 'local.settings.json'), 'utf8')
);
const storageState = path.join(__dirname, '..', '..', '.auth', 'user.json');
const logDir = settings.gasLogDir || null;

// Backend resolved once, mirrors tests/helpers/gas_log.py::_backend(). 'axiom' iff
// axiomDataset+axiomQueryToken are both set in local.settings.json.
const LOG_BACKEND = (settings.axiomDataset && settings.axiomQueryToken) ? 'axiom' : 'file';
let logFence = 0; // axiom backend only -- set by clearLogs(), consumed by waitForLogTag()

// ---------------------------------------------------------------------------
// Log helpers (mirrors tests/helpers/gas_log.py)
// ---------------------------------------------------------------------------

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

function clearLogs() {
  if (LOG_BACKEND === 'axiom') {
    logFence = Date.now() - 2000;
    return;
  }
  if (!logDir || !fs.existsSync(logDir)) return;
  for (const f of fs.readdirSync(logDir)) {
    if (f.endsWith('.log')) {
      try { fs.unlinkSync(path.join(logDir, f)); } catch {}
    }
  }
}

async function waitForLogTag(tag, timeoutMs = 240000) {
  if (LOG_BACKEND === 'axiom') {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const entries = await axiomQuery(logFence);
      const found = entries.find(e => e.tag === tag);
      if (found) return found;
      await new Promise(r => setTimeout(r, 1000));
    }
    throw new Error(`Timeout (${timeoutMs}ms) waiting for log tag: ${tag} (axiom backend)`);
  }
  if (!logDir || !fs.existsSync(logDir)) {
    process.stderr.write(`[batch] No logDir — skipping wait for tag: ${tag}\n`);
    return null;
  }
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    let files;
    try { files = fs.readdirSync(logDir).filter(f => f.endsWith('.log')); }
    catch { files = []; }
    for (const f of files) {
      try {
        const lines = fs.readFileSync(path.join(logDir, f), 'utf8')
          .split('\n').filter(l => l.trim());
        for (const line of lines) {
          const entry = JSON.parse(line);
          if (entry.tag === tag) return entry;
        }
      } catch {}
    }
    await new Promise(r => setTimeout(r, 1000));
  }
  throw new Error(`Timeout (${timeoutMs}ms) waiting for log tag: ${tag}`);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(commands) {
  const headless = !process.argv.includes('--headed');
  const browser = await chromium.launch({ headless });
  const context = await browser.newContext({ storageState });
  const page    = await context.newPage();

  const sheetUrl = `https://docs.google.com/spreadsheets/d/${settings.testSheetId}/edit`;
  await page.goto(sheetUrl);
  await page.waitForSelector('.docs-title-outer', { timeout: 30000 });
  await page.getByText('Action Sync', { exact: true }).waitFor({ timeout: 15000 });

  const results = {};

  for (const cmd of commands) {
    const { menuItem, arg, parent, awaitTag, timeoutMs = 240000 } = cmd;

    // Clear logs before each command that has an awaitTag so the poller only
    // sees entries produced by this command.
    if (awaitTag) clearLogs();

    // Write arg to TestControl!A1 if provided.
    if (arg !== undefined) {
      const tab = page.locator('.docs-sheet-tab-name').filter({ hasText: /^TestControl$/ });
      await tab.waitFor({ timeout: 10000 });
      await tab.click();
      await page.waitForTimeout(500);
      await page.keyboard.press('Escape');
      await page.keyboard.press('Control+Home');
      await page.waitForTimeout(300);
      await page.keyboard.type(String(arg));
      await page.keyboard.press('Enter');
      await page.waitForTimeout(400);
    }

    // Open top-level menu.
    await page.getByText('Action Sync', { exact: true }).click();

    if (parent) {
      const submenuTrigger = page.locator('[role="menuitem"]')
        .filter({ hasText: parent }).first();
      await submenuTrigger.waitFor({ timeout: 5000 });
      await submenuTrigger.hover();
      await page.waitForTimeout(400);
    }

    await page.getByRole('menuitem', { name: menuItem, exact: true })
      .waitFor({ timeout: 5000 });
    await page.getByRole('menuitem', { name: menuItem, exact: true }).click();
    await page.waitForTimeout(1000);

    if (awaitTag) {
      process.stderr.write(`[batch] waiting for tag: ${awaitTag}\n`);
      const entry = await waitForLogTag(awaitTag, timeoutMs);
      results[awaitTag] = entry;
      process.stderr.write(`[batch] received tag: ${awaitTag}\n`);
    }
  }

  await browser.close();
  process.stdout.write(JSON.stringify(results) + '\n');
  process.exit(0);
}

let inputData = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { inputData += chunk; });
process.stdin.on('end', () => {
  let commands;
  try {
    commands = JSON.parse(inputData);
  } catch (e) {
    process.stderr.write(`Failed to parse commands from stdin: ${e.message}\n`);
    process.exit(1);
  }
  main(commands).catch(e => {
    process.stderr.write(e.message + '\n');
    process.exit(1);
  });
});
