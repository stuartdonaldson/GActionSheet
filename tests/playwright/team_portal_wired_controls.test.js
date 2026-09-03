/**
 * team_portal_wired_controls.test.js — Frontend wiring regression for
 * gts-79dw.4.21 (Edit button) + gts-79dw.4.22 (assignee status control),
 * static-portal/src/index.html.
 *
 * Both controls used to be stubs that only toasted "lands in a follow-up
 * bead"; this test drives the actual built page (static-portal/dist/sit/
 * index.html, the exact artifact the publish pipeline ships) in a real
 * browser and asserts the click -> fetch(team_edit_action|team_patch_status)
 * -> DOM-update chain, both on success and on a rejected outcome.
 *
 * Network-isolated by design: backend routes (team_edit_action /
 * team_patch_status, tier/assignee gating) are already covered end-to-end
 * against the live GAS deployment by tests/test_team_write_routes.py — this
 * file's job is the *frontend* wiring, not re-proving server-side
 * authorization. page.route() intercepts calls to the exact GACTIONSHEET_URL
 * baked into the built page (settings.webappTestUrl) and returns canned
 * responses, so this test is fast/deterministic and needs no live doc/team
 * seeding or GIS sign-in (same file:// vs cross-origin rationale as
 * cors_team_portal.test.js — a fixture server stands in for the real
 * nuuc-it.github.io origin).
 */
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const http = require('http');
const path = require('path');
const { loadSettings } = require('./_helpers');

test.use({ storageState: undefined, baseURL: undefined });

const DIST_HTML = path.join(__dirname, '..', '..', 'static-portal', 'dist', 'sit', 'index.html');

function startFixtureServer() {
  const html = fs.readFileSync(DIST_HTML, 'utf8');
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(html);
    });
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

const CACHED_EMAIL = 'wired-controls-test@example.com';
const GLOBAL_ID = 'wired-controls-test-doc/AI-1';

function seedRow(overrides) {
  return Object.assign({
    global_id: GLOBAL_ID,
    action_id: 1,
    action_text: 'Original action text',
    assignee_email: CACHED_EMAIL,
    assignee_name: 'Test Assignee',
    status: 'Open',
    status_bucket: 'Open',
    status_resolved: false,
    status_icon: 'https://example.com/open.png',
    modified_date: new Date().toISOString(),
    doc_id: 'wired-controls-test-doc',
    doc_name: 'Wired Controls Test Doc',
    doc_url: 'https://docs.google.com/document/d/wired-controls-test-doc/edit'
  }, overrides || {});
}

/** Seeds a cached auth record so the page skips GIS sign-in entirely and
 * goes straight to loadTeams() (see index.html's initAuth()/loadCachedAuth()). */
async function primeCachedAuth(page) {
  await page.addInitScript(({ email }) => {
    localStorage.setItem('nuucAsAuth.v1', JSON.stringify({
      assertion: 'fixture.assertion.value',
      exp: Math.floor(Date.now() / 1000) + 3600,
      sub: 'wired-controls-test-sub',
      email
    }));
  }, { email: CACHED_EMAIL });
}

test.describe('@team-portal team portal wired controls (gts-79dw.4.21 / .22)', () => {
  test.beforeAll(() => {
    expect(fs.existsSync(DIST_HTML),
      `${DIST_HTML} missing — run: node -e "require('./scripts/static-pages.js').build('sit')"`).toBe(true);
  });

  test('Edit button saves via team_edit_action and the row reflects the edit without a page reload', async ({ page }) => {
    const settings = loadSettings();
    const gactionsheetUrl = settings.webappTestUrl;
    expect(gactionsheetUrl, 'webappTestUrl must be set in local.settings.json').toBeTruthy();

    const server = await startFixtureServer();
    const port = server.address().port;
    try {
      await primeCachedAuth(page);
      const editedRow = seedRow({ action_text: 'Edited via team_edit_action' });
      let row = seedRow();
      const calls = [];
      // Swap the seeded row to its post-edit form once team_edit_action
      // succeeds, so the follow-up refreshActions() reflects the edit —
      // mirrors what the real backend would return on re-read.
      await page.route(gactionsheetUrl, async (route) => {
        const payload = JSON.parse(route.request().postData());
        calls.push(payload);
        if (payload.action === 'list_my_teams') {
          return route.fulfill({ contentType: 'application/json', body: JSON.stringify({
            teams: [{ teamId: 'TestTeamA', teamName: 'Test Team A', tier: 'EDIT' }]
          }) });
        }
        if (payload.action === 'list_team_actions') {
          return route.fulfill({ contentType: 'application/json', body: JSON.stringify({
            tier: 'EDIT', actions: [row],
            statusOptions: [{ status: 'Open', icon: 'https://example.com/open.png', alt: 'Open' }]
          }) });
        }
        if (payload.action === 'team_edit_action') {
          row = editedRow;
          return route.fulfill({ contentType: 'application/json', body: JSON.stringify({
            ok: true, global_id: payload.global_id, outcome: 'ok'
          }) });
        }
        throw new Error('unexpected action: ' + payload.action);
      });

      await page.goto(`http://127.0.0.1:${port}/`);
      await expect(page.locator('#appView')).toBeVisible();
      await expect(page.locator('.action')).toHaveText('Original action text');

      await page.locator('[data-edit]').click();
      const textInput = page.locator('[data-field="action_text"]');
      await expect(textInput).toBeVisible();
      await textInput.fill('Edited via team_edit_action');
      await page.locator('[data-save-edit]').click();

      await expect(page.locator('.toast')).toHaveText('Saved.');
      await expect(page.locator('.action')).toHaveText('Edited via team_edit_action');
      // Edit form must be gone (row reflects the edit, not still showing the form).
      await expect(page.locator('[data-field="action_text"]')).toHaveCount(0);

      const editCall = calls.find(c => c.action === 'team_edit_action');
      expect(editCall, 'team_edit_action was never called').toBeTruthy();
      expect(editCall.global_id).toBe(GLOBAL_ID);
      expect(editCall.assertion).toBe('fixture.assertion.value');
      expect(editCall.teamId).toBe('TestTeamA');
      expect(editCall.fields.action_text).toBe('Edited via team_edit_action');
    } finally {
      server.close();
    }
  });

  test('Edit rejection leaves the row unchanged and surfaces the error', async ({ page }) => {
    const settings = loadSettings();
    const gactionsheetUrl = settings.webappTestUrl;
    const server = await startFixtureServer();
    const port = server.address().port;
    try {
      await primeCachedAuth(page);
      const row = seedRow();
      await page.route(gactionsheetUrl, async (route) => {
        const payload = JSON.parse(route.request().postData());
        if (payload.action === 'list_my_teams') {
          return route.fulfill({ contentType: 'application/json', body: JSON.stringify({
            teams: [{ teamId: 'TestTeamA', teamName: 'Test Team A', tier: 'EDIT' }]
          }) });
        }
        if (payload.action === 'list_team_actions') {
          return route.fulfill({ contentType: 'application/json', body: JSON.stringify({
            tier: 'EDIT', actions: [row],
            statusOptions: [{ status: 'Open', icon: 'https://example.com/open.png', alt: 'Open' }]
          }) });
        }
        if (payload.action === 'team_edit_action') {
          return route.fulfill({ contentType: 'application/json', body: JSON.stringify({
            ok: false, global_id: payload.global_id, outcome: 'rejected-doc-scope'
          }) });
        }
        throw new Error('unexpected action: ' + payload.action);
      });

      await page.goto(`http://127.0.0.1:${port}/`);
      await expect(page.locator('#appView')).toBeVisible();

      await page.locator('[data-edit]').click();
      await page.locator('[data-field="action_text"]').fill('TAMPERED');
      await page.locator('[data-save-edit]').click();

      await expect(page.locator('.toast')).toHaveText('Edit did not apply: rejected-doc-scope');
      // Row must be unchanged and the edit form gone.
      await expect(page.locator('.action')).toHaveText('Original action text');
      await expect(page.locator('[data-field="action_text"]')).toHaveCount(0);
    } finally {
      server.close();
    }
  });

  test('assignee status control saves via team_patch_status and the row updates without a page reload', async ({ page }) => {
    const settings = loadSettings();
    const gactionsheetUrl = settings.webappTestUrl;
    const server = await startFixtureServer();
    const port = server.address().port;
    try {
      await primeCachedAuth(page);
      let row = seedRow();
      const closedRow = seedRow({
        status: 'Closed', status_bucket: 'Closed', status_resolved: true,
        status_icon: 'https://example.com/closed.png'
      });
      const calls = [];
      await page.route(gactionsheetUrl, async (route) => {
        const payload = JSON.parse(route.request().postData());
        calls.push(payload);
        if (payload.action === 'list_my_teams') {
          return route.fulfill({ contentType: 'application/json', body: JSON.stringify({
            teams: [{ teamId: 'TestTeamA', teamName: 'Test Team A', tier: 'EDIT' }]
          }) });
        }
        if (payload.action === 'list_team_actions') {
          return route.fulfill({ contentType: 'application/json', body: JSON.stringify({
            tier: 'EDIT', actions: [row],
            statusOptions: [
              { status: 'Open', icon: 'https://example.com/open.png', alt: 'Open' },
              { status: 'Closed', icon: 'https://example.com/closed.png', alt: 'Closed' }
            ]
          }) });
        }
        if (payload.action === 'team_patch_status') {
          row = closedRow;
          return route.fulfill({ contentType: 'application/json', body: JSON.stringify({
            ok: true, global_id: payload.global_id, outcome: 'ok'
          }) });
        }
        throw new Error('unexpected action: ' + payload.action);
      });

      await page.goto(`http://127.0.0.1:${port}/`);
      await expect(page.locator('#appView')).toBeVisible();
      await expect(page.locator('.status.mine')).toBeVisible();

      await page.locator('.status.mine').click();
      await expect(page.locator('#statusMenu')).toBeVisible();
      await page.locator('#statusMenu [data-set="Closed"]').click();

      await expect(page.locator('.toast')).toHaveText('Status updated.');
      await expect(page.locator('.status')).toContainText('Closed');

      const statusCall = calls.find(c => c.action === 'team_patch_status');
      expect(statusCall, 'team_patch_status was never called').toBeTruthy();
      expect(statusCall.global_id).toBe(GLOBAL_ID);
      expect(statusCall.status).toBe('Closed');
      expect(statusCall.teamId).toBe('TestTeamA');
    } finally {
      server.close();
    }
  });
});
