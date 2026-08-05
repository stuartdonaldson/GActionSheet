/**
 * team_portal_view_b.test.js — Frontend wiring regression for View B
 * (gts-79dw.4.23/Unit D), static-portal/src/doc.html.
 *
 * This is the fast/targeted mocked gate for Unit D's own AC: "a verified
 * caller with >= VIEW tier ... sees that document's actions with the same
 * information the sidebar document view presents ... a NONE-tier caller
 * sees no action data; a link/button navigates to View A for the same
 * team." Drives the actual built page (static-portal/dist/sit/doc.html, the
 * exact artifact the publish pipeline ships) in a real browser;
 * page.route() intercepts calls to the exact GACTIONSHEET_URL baked into
 * the built page and returns canned responses shaped exactly like
 * get_document_actions' real output schema (src/DocView.js) — this is a
 * frontend-rendering test, not a re-proof of the backend route (that's
 * tests/test_view_b.py's job, already closed/green). The true no-mock
 * counterpart (live GAS, no page.route()) is
 * team_portal_view_b_live.test.js, per plan-79dw.md Unit D's gate
 * requirement (cors_team_portal.test.js pattern).
 *
 * Important schema note (see plan-context.md / DocView.js): get_document_actions'
 * `actions` reuses _findSheetActionsForDoc's RAW SheetAction shape verbatim
 * (global_id, action_id, assignee_email, assignee_name, action_text, status,
 * doc_id, doc_name, created_date, modified_date, sync_status) — NOT the
 * list_team_actions-enriched shape (status_bucket/status_icon/status_resolved).
 * Rows here are seeded without those enriched fields on purpose, to prove
 * doc.html doesn't assume they exist.
 */
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const http = require('http');
const path = require('path');
const { loadSettings } = require('./_helpers');

test.use({ storageState: undefined, baseURL: undefined });

const DIST_HTML = path.join(__dirname, '..', '..', 'static-portal', 'dist', 'sit', 'doc.html');

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

const CACHED_EMAIL = 'view-b-test@example.com';
const DOC_ID = 'view-b-test-doc';

function seedRow(overrides) {
  return Object.assign({
    global_id: DOC_ID + '/AI-1',
    file_id: 'file-1',
    action_id: 1,
    assignee_email: 'teammate@example.com',
    assignee_name: 'Test Assignee',
    action_text: 'View B seeded action',
    status: 'Open',
    document_formula: '=HYPERLINK(...)',
    doc_id: DOC_ID,
    doc_name: 'View B Test Doc',
    created_date: new Date().toISOString(),
    modified_date: new Date().toISOString(),
    sync_status: 'synced'
  }, overrides || {});
}

/** Same auth-cache seeding convention as index.html's tests (Units B/C). */
async function primeCachedAuth(page) {
  await page.addInitScript(({ email }) => {
    localStorage.setItem('nuucAsAuth.v1', JSON.stringify({
      assertion: 'fixture.assertion.value',
      exp: Math.floor(Date.now() / 1000) + 3600,
      sub: 'view-b-test-sub',
      email
    }));
  }, { email: CACHED_EMAIL });
}

test.describe('@team-portal View B — per-document verified view (gts-79dw.4.23)', () => {
  test.beforeAll(() => {
    expect(fs.existsSync(DIST_HTML),
      `${DIST_HTML} missing — run: node scripts/build-static-portal.js --env sit`).toBe(true);
  });

  test('VIEW-tier caller sees the document actions with sidebar-parity fields, no write controls', async ({ page }) => {
    const settings = loadSettings();
    const gactionsheetUrl = settings.webappTestUrl;
    expect(gactionsheetUrl, 'webappTestUrl must be set in local.settings.json').toBeTruthy();

    const server = await startFixtureServer();
    const port = server.address().port;
    try {
      await primeCachedAuth(page);
      const row = seedRow();
      const calls = [];
      await page.route(gactionsheetUrl, async (route) => {
        const payload = JSON.parse(route.request().postData());
        calls.push(payload);
        if (payload.action === 'get_document_actions') {
          return route.fulfill({ contentType: 'application/json', body: JSON.stringify({
            tier: 'VIEW',
            teamId: 'TestTeamA',
            docName: 'View B Test Doc',
            docUrl: 'https://docs.google.com/document/d/' + DOC_ID + '/edit',
            actions: [row],
            teamPortalUrl: 'https://example.invalid/pub/AS-sit/index.html?team=TestTeamA'
          }) });
        }
        throw new Error('unexpected action: ' + payload.action);
      });

      await page.goto(`http://127.0.0.1:${port}/?doc=${DOC_ID}&team=TestTeamA`);
      await expect(page.locator('#appView')).toBeVisible();

      // Sidebar-parity fields present.
      await expect(page.locator('.action')).toHaveText('View B seeded action');
      await expect(page.locator('.aiN')).toHaveText('AI-1');
      await expect(page.locator('.rowmeta')).toContainText('Test Assignee');
      await expect(page.locator('.status')).toHaveText('Open');
      await expect(page.locator('#tierTag')).toContainText('VIEW');

      // Deliberately absent (R19 — write path, read-only view): no Edit
      // button, no clickable/editable status control.
      await expect(page.locator('[data-edit]')).toHaveCount(0);
      await expect(page.locator('[data-save-edit]')).toHaveCount(0);
      await expect(page.locator('.status.mine')).toHaveCount(0);

      // R20 navigation back to View A uses the server's own teamPortalUrl.
      await expect(page.locator('#backToTeamLink')).toHaveAttribute(
        'href', 'https://example.invalid/pub/AS-sit/index.html?team=TestTeamA');

      const call = calls.find(c => c.action === 'get_document_actions');
      expect(call, 'get_document_actions was never called').toBeTruthy();
      expect(call.docId).toBe(DOC_ID);
      expect(call.assertion).toBe('fixture.assertion.value');
    } finally {
      server.close();
    }
  });

  test('NONE-tier caller sees no action data, only the access notice', async ({ page }) => {
    const settings = loadSettings();
    const gactionsheetUrl = settings.webappTestUrl;
    const server = await startFixtureServer();
    const port = server.address().port;
    try {
      await primeCachedAuth(page);
      await page.route(gactionsheetUrl, async (route) => {
        const payload = JSON.parse(route.request().postData());
        if (payload.action === 'get_document_actions') {
          return route.fulfill({ contentType: 'application/json', body: JSON.stringify({
            tier: 'NONE',
            teamId: 'TestTeamA',
            docName: 'View B Test Doc',
            docUrl: 'https://docs.google.com/document/d/' + DOC_ID + '/edit',
            actions: [],
            teamPortalUrl: ''
          }) });
        }
        throw new Error('unexpected action: ' + payload.action);
      });

      await page.goto(`http://127.0.0.1:${port}/?doc=${DOC_ID}&team=TestTeamA`);
      await expect(page.locator('#appView')).toBeVisible();
      await expect(page.locator('#noAccessNotice')).toBeVisible();
      await expect(page.locator('#listWrap')).toBeHidden();
      await expect(page.locator('.row')).toHaveCount(0);
    } finally {
      server.close();
    }
  });

  test('missing ?doc= shows the no-document notice instead of prompting sign-in', async ({ page }) => {
    const server = await startFixtureServer();
    const port = server.address().port;
    try {
      await primeCachedAuth(page);
      await page.goto(`http://127.0.0.1:${port}/`);
      await expect(page.locator('#noDocView')).toBeVisible();
      await expect(page.locator('#signinView')).toBeHidden();
      await expect(page.locator('#appView')).toBeHidden();
    } finally {
      server.close();
    }
  });
});
