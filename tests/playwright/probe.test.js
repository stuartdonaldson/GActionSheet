/**
 * probe.test.js — Deployment & identity probe session.
 *
 * Run via the npm script which sets PROBE_RUN_ID:
 *   npm run probe
 *
 * Or manually:
 *   PROBE_RUN_ID=$(node -e "process.stdout.write(require('crypto').randomUUID())") \
 *   PWHEADFUL=1 npx playwright test tests/playwright/probe.test.js \
 *     --config tests/playwright/playwright.config.js --retries=0
 *
 * After running, copy the RUN_ID printed to stdout into staging/probe-runs.md.
 * See staging/probe-deployment-identity-spec.md for full protocol.
 */

const { test } = require('@playwright/test');
const crypto  = require('crypto');
const https   = require('https');
const fs      = require('fs');
const path    = require('path');

const { openDocSidebar, waitForLogEntry } = require('./addon_helpers');
const { runViaSheetMenu }                  = require('./editor_helpers');

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

const settingsPath = path.join(__dirname, '..', '..', 'local.settings.json');
const settings     = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));

// Auth state file — override with PROBE_AUTH_STATE env var to run as a different account.
// Default: .auth/user.json (deployer account). For second-user probes: .auth/test.u2.json
const storageState = process.env.PROBE_AUTH_STATE
  ? path.resolve(process.cwd(), process.env.PROBE_AUTH_STATE)
  : path.join(__dirname, '..', '..', '.auth', 'user.json');

const DEV_URL  = settings.webappDevUrl;   // @HEAD — has PROBE.js after push
const TEST_URL = settings.webappTestUrl;  // versioned — may or may not have PROBE.js
const DOC_ID   = settings.testDocId;
const DOC_URL  = `https://docs.google.com/document/d/${DOC_ID}/edit`;

// ---------------------------------------------------------------------------
// RUN_ID — passed via env var so all worker processes share the same value.
// Generate outside with: node -e "process.stdout.write(require('crypto').randomUUID())"
// The npm run probe script handles this automatically.
// ---------------------------------------------------------------------------

const RUN_ID = process.env.PROBE_RUN_ID || crypto.randomUUID();

console.log('\n╔════════════════════════════════════════════════════════════╗');
console.log('║  PROBE RUN_ID: ' + RUN_ID + '  ║');
console.log('╚════════════════════════════════════════════════════════════╝');
console.log('  → Copy this into staging/probe-runs.md\n');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Plain HTTPS GET — no auth cookies.
 */
function httpGet(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { 'User-Agent': 'PROBE-unauthed/1.0' } }, res => {
      let body = '';
      res.on('data', d => body += d);
      res.on('end', () => resolve({ status: res.statusCode, body }));
    }).on('error', reject);
  });
}

/**
 * Plain HTTPS POST — no auth cookies.
 */
function httpPost(url, payload) {
  return new Promise((resolve) => {
    const data = JSON.stringify(payload);
    const req  = https.request(url, {
      method:  'POST',
      headers: {
        'Content-Type':   'application/json',
        'Content-Length': Buffer.byteLength(data),
        'User-Agent':     'PROBE-unauthed/1.0'
      }
    }, res => {
      let body = '';
      res.on('data', d => body += d);
      res.on('end', () => resolve({ status: res.statusCode, body }));
    });
    // Resolve with error detail rather than reject — keeps test passing
    req.on('error', err => resolve({ status: 0, body: 'network error: ' + err.message }));
    req.write(data);
    req.end();
  });
}

/**
 * Poll gasLogDir for a PROBE entry matching tag and runId.
 * Returns the entry data or null on timeout.
 */
function waitForProbe(surface, timeoutMs) {
  return waitForLogEntry(entry => {
    return entry.tag === ('PROBE.' + surface) &&
           entry.data && entry.data.runId === RUN_ID;
  }, timeoutMs || 45000).catch(() => null);
}

/** Append a labelled response to the session response file. */
const responsesFile = path.join(
  __dirname, '..', '..', 'staging',
  'probe-responses-' + RUN_ID + '.txt'
);
function saveResponse(label, status, body) {
  const line = `\n--- ${label} (HTTP ${status}) ---\n${body}\n`;
  fs.appendFileSync(responsesFile, line, 'utf8');
  const preview = body.slice(0, 120).replace(/\n/g, ' ');
  console.log(`  [${label}] HTTP ${status}: ${preview}…`);
}

function logFound(surface, entry) {
  if (entry) {
    console.log(`  PROBE.${surface}: effectiveUser=${entry.effectiveUser} activeUser=${entry.activeUser} version=${entry.version}`);
  } else {
    console.log(`  PROBE.${surface}: NOT FOUND in logs (expected if this deployment lacks PROBE.js)`);
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('PROBE session', () => {

  test.beforeAll(async () => {
    fs.writeFileSync(responsesFile,
      'PROBE responses — runId: ' + RUN_ID + '\n' +
      'Date: ' + new Date().toISOString() + '\n' +
      'DEV_URL:  ' + DEV_URL  + '\n' +
      'TEST_URL: ' + TEST_URL + '\n',
      'utf8'
    );
    console.log('\n  Response log: ' + responsesFile);
    console.log('  DEV_URL:  ' + DEV_URL);
    console.log('  TEST_URL: ' + TEST_URL + '\n');
  });

  // ── 1. Seed runId via doGet.dev (DEV always has PROBE.js after push) ─────

  test('doGet.dev — authed (seeds runId)', async ({ page }) => {
    const url = `${DEV_URL}?probe_run=${RUN_ID}&probe_surface=doGet.dev`;
    await page.goto(url);
    const body = await page.locator('body').textContent().catch(() => '');
    saveResponse('doGet.dev authed', 200, body || '(empty body)');
    const entry = await waitForProbe('doGet.dev', 30000);
    logFound('doGet.dev', entry && entry.data);
    // runId is now seeded in ScriptProperties for subsequent UI surface tests
  });

  // ── 2. doGet variants ────────────────────────────────────────────────────

  test('doGet.test — authed', async ({ page }) => {
    const url = `${TEST_URL}?probe_run=${RUN_ID}&probe_surface=doGet.test`;
    await page.goto(url);
    const body = await page.locator('body').textContent().catch(() => '');
    saveResponse('doGet.test authed', 200, body || '(empty body)');
    const entry = await waitForProbe('doGet.test', 30000);
    logFound('doGet.test', entry && entry.data);
    // Expected NOT FOUND in Run A (TEST deployment lacks PROBE.js until deploy:test)
  });

  test('doGet.dev — unauthed', async () => {
    const url = `${DEV_URL}?probe_run=${RUN_ID}&probe_surface=doGet.dev.unauthed`;
    const { status, body } = await httpGet(url);
    saveResponse('doGet.dev unauthed', status, body);
    console.log('  doGet.dev unauthed: HTTP ' + status + ' (302=login redirect, 200=ran, 404=wrong URL)');
  });

  test('doGet.test — unauthed', async () => {
    const url = `${TEST_URL}?probe_run=${RUN_ID}&probe_surface=doGet.test.unauthed`;
    const { status, body } = await httpGet(url);
    saveResponse('doGet.test unauthed', status, body);
    console.log('  doGet.test unauthed: HTTP ' + status + ' (302=login redirect expected for ANYONE access)');
  });

  // ── 3. doPost variants ───────────────────────────────────────────────────

  test('doPost.dev — unauthed', async () => {
    const { status, body } = await httpPost(DEV_URL, {
      action: 'probe', probe_run: RUN_ID,
      probe_surface: 'doPost.dev.unauthed', probe_version: 'playwright-probe'
    });
    saveResponse('doPost.dev unauthed', status, body);
    const entry = await waitForProbe('doPost.dev.unauthed', 15000);
    logFound('doPost.dev.unauthed', entry && entry.data);
  });

  test('doPost.test — unauthed', async () => {
    const { status, body } = await httpPost(TEST_URL, {
      action: 'probe', probe_run: RUN_ID,
      probe_surface: 'doPost.test.unauthed', probe_version: 'playwright-probe'
    });
    saveResponse('doPost.test unauthed', status, body);
    const entry = await waitForProbe('doPost.test.unauthed', 30000);
    logFound('doPost.test.unauthed', entry && entry.data);
  });

  test('doPost.dev — authed', async ({ playwright }) => {
    const apiCtx = await playwright.request.newContext({ storageState });
    const res    = await apiCtx.post(DEV_URL, { data: {
      action: 'probe', probe_run: RUN_ID,
      probe_surface: 'doPost.dev.authed', probe_version: 'playwright-probe'
    }});
    const body = await res.text();
    saveResponse('doPost.dev authed', res.status(), body);
    const entry = await waitForProbe('doPost.dev.authed', 30000);
    logFound('doPost.dev.authed', entry && entry.data);
    await apiCtx.dispose();
  });

  test('doPost.test — authed', async ({ playwright }) => {
    const apiCtx = await playwright.request.newContext({ storageState });
    const res    = await apiCtx.post(TEST_URL, { data: {
      action: 'probe', probe_run: RUN_ID,
      probe_surface: 'doPost.test.authed', probe_version: 'playwright-probe'
    }});
    const body = await res.text();
    saveResponse('doPost.test authed', res.status(), body);
    const entry = await waitForProbe('doPost.test.authed', 30000);
    logFound('doPost.test.authed', entry && entry.data);
    await apiCtx.dispose();
  });

  // ── 4. Sidebar ───────────────────────────────────────────────────────────

  test('sidebar — existing doc', async ({ page }) => {
    // NOTE: If this fails with "side-panel icon not available", the test
    // deployment needs to be reinstalled: Script editor → Deploy →
    // Test deployments → Uninstall → Install.
    try {
      await openDocSidebar(page, DOC_ID);
      const entry = await waitForProbe('sidebar.existing', 45000)
                      .catch(() => waitForProbe('sidebar.new', 10000).catch(() => null));
      logFound('sidebar.' + (entry ? entry.data.surface.split('.')[1] : 'unknown'),
               entry && entry.data);
    } catch (err) {
      console.log('  sidebar: FAILED — ' + err.message);
      console.log('  → Check: test deployment reinstalled after last npm run push?');
      saveResponse('sidebar ERROR', 0, err.message);
    }
  });

  // ── 5. Chip hover (best effort) ──────────────────────────────────────────

  test('chipHover — existing doc (best effort)', async ({ page }) => {
    if (!page.url().includes(DOC_ID)) {
      await page.goto(DOC_URL);
      await page.waitForSelector('.docs-title-outer', { timeout: 30000 });
    }

    const chipLink = page.locator('a[href*="northlakeuu.org/NUUTS"]').first();
    const visible  = await chipLink.isVisible().catch(() => false);

    if (visible) {
      await chipLink.hover({ force: true });
      await page.waitForTimeout(3000);
      const entry = await waitForProbe('chipHover.existing', 20000)
                      .catch(() => waitForProbe('chipHover.new', 5000).catch(() => null));
      logFound('chipHover', entry && entry.data);
    } else {
      console.log('  chipHover: chip link not in DOM — trigger requires cursor hover in Google Docs editor; manual verification needed');
    }
  });

  // ── 6. Menu (Sync) ───────────────────────────────────────────────────────

  test('menu — Sync', async ({ page }) => {
    try {
      await runViaSheetMenu(page, 'Action Sync', 'Sync');
      const entry = await waitForProbe('menu', 60000);
      logFound('menu', entry && entry.data);
    } catch (err) {
      console.log('  menu: FAILED — ' + err.message);
      saveResponse('menu ERROR', 0, err.message);
    }
  });

  // ── 7. Menu (Probe Identity) — full identity in authorized context ────────
  // Captures effectiveUser + activeUser from an authorized menu trigger,
  // replacing the onOpen surface which is limited to Logger.log only.

  test('menu — Probe Identity', async ({ page }) => {
    try {
      await runViaSheetMenu(page, 'Action Sync', 'Test: Probe Identity');
      const entry = await waitForProbe('menu.identity', 30000);
      logFound('menu.identity', entry && entry.data);
    } catch (err) {
      console.log('  menu.identity: FAILED — ' + err.message);
      saveResponse('menu.identity ERROR', 0, err.message);
    }
  });

  // ── Summary ──────────────────────────────────────────────────────────────

  test.afterAll(async () => {
    console.log('\n  ═══════════════════════════════════════════════════');
    console.log('  PROBE session complete');
    console.log('  RUN_ID:   ' + RUN_ID);
    console.log('  Responses: ' + responsesFile);
    console.log('  Logs:      ' + settings.gasLogDir);
    console.log('  ═══════════════════════════════════════════════════\n');
  });

});
