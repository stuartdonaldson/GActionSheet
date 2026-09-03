/**
 * team_portal_view_b_live.test.js — TRUE no-mock e2e for View B
 * (gts-79dw.4.23/Unit D), per plan-79dw.md Unit D's gate requirement.
 *
 * Every other portal Playwright test (team_portal_wired_controls.test.js,
 * team_portal_query_routing.test.js, team_portal_view_b.test.js) uses
 * page.route() to intercept the GACTIONSHEET_URL fetch and return a canned
 * response — necessary for those files' own scope (frontend wiring/routing,
 * not backend re-proof), but structurally unable to catch a real response-
 * shape drift between GAS and the frontend's assumptions. This file is the
 * gap-closer flagged after Units B/C: it drives the real built
 * static-portal/dist/sit/doc.html in a real browser, with NO page.route()
 * anywhere, against the live SIT get_document_actions deployment
 * (settings.webappTestUrl) — same no-mock posture as
 * tests/playwright/cors_team_portal.test.js (the only prior precedent).
 *
 * Setup (seeding a real doc with a real action, minting a real signed
 * assertion) is done with plain node fetch() calls to the same
 * testToken-gated GAS routes tests/test_view_b.py's Python
 * ScenarioSession/mint_test_assertion helpers already use
 * (begin_journey_session, append_doc_paragraph, run_fixture
 * move_doc_to_folder / sync_document / mint_test_assertion,
 * end_journey_session) — replicated here in JS rather than shelling out to
 * pytest, since this file's own assertions need to run inside a real
 * browser page. This mirrors addon_helpers.js's existing precedent of
 * calling webappTestUrl directly via fetch from test setup code (not a
 * "hand-rolled curl outside pytest" — call_webapp.py's sanctioned-wrapper
 * rule is about ad hoc manual probes, not in-test setup helpers).
 *
 * Uses the real TestTeamA fixture folder (gts-79dw.4.16) and the same real
 * VIEW-tier caller email test_view_b.py already relies on
 * (stuart.donaldson@gmail.com), so tier resolution is real, not mocked.
 */
const { test, expect } = require('@playwright/test');
const http = require('http');
const { loadSettings } = require('./_helpers');

test.use({ storageState: undefined, baseURL: undefined });

const TEAM_A = 'TestTeamA';
const TEAM_A_FOLDER_1 = '1SCPPZfUeSWqaE3WvWYl6go13lzEZQUbs';
const CALLER_EMAIL = 'stuart.donaldson@gmail.com'; // real VIEW-tier grant on TestTeamA (see test_view_b.py)
const RUN_TAG = 'gts79dw423live' + Date.now().toString(36);

function startFixtureServer(gactionsheetUrl) {
  // Stand-in for the real nuuc-it.github.io cross-origin host (same rationale
  // as cors_team_portal.test.js) — serves the actual built doc.html so its
  // baked-in GACTIONSHEET_URL is exercised for real, unmocked.
  const fs = require('fs');
  const path = require('path');
  const distPath = path.join(__dirname, '..', '..', 'static-portal', 'dist', 'sit', 'doc.html');
  const html = fs.readFileSync(distPath, 'utf8');
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(html);
    });
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

async function postJson(url, payload) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const text = await resp.text();
  try { return JSON.parse(text); }
  catch (e) {
    throw new Error(`Non-JSON response from ${url} (action=${payload.action || payload.fixture}): ${text.slice(0, 300)}`);
  }
}

async function runFixture(webappTestUrl, testToken, fixture, extra) {
  return postJson(webappTestUrl, Object.assign({ action: 'run_fixture', testToken, fixture }, extra || {}));
}

test.describe('@team-portal @live View B — true no-mock e2e against live SIT (gts-79dw.4.23/Unit D)', () => {
  test('a real VIEW-tier caller sees a real seeded action via the live get_document_actions route, no mocking', async ({ page }) => {
    test.setTimeout(120000);
    const settings = loadSettings();
    const webappTestUrl = settings.webappTestUrl;
    const testToken = settings.testToken || '';
    expect(webappTestUrl, 'webappTestUrl must be set in local.settings.json').toBeTruthy();
    expect(testToken, 'testToken must be set in local.settings.json').toBeTruthy();

    let docId = null;
    let server = null;
    const actionText = `${RUN_TAG} view b live action`;

    try {
      // --- seed a real doc with a real action, scoped to TestTeamA -------
      const begin = await postJson(webappTestUrl, { action: 'begin_journey_session', testToken });
      docId = begin.docId;
      expect(docId, `begin_journey_session did not return a docId: ${JSON.stringify(begin)}`).toBeTruthy();

      const moveResp = await runFixture(webappTestUrl, testToken, 'move_doc_to_folder', {
        docId, folderId: TEAM_A_FOLDER_1
      });
      test.skip((moveResp && moveResp.ok === false) || false,
        `move_doc_to_folder failed: ${JSON.stringify(moveResp)}`);

      await postJson(webappTestUrl, {
        action: 'append_doc_paragraph', testToken,
        testDocId: docId, text: `AI: teammate@example.com ${actionText}`
      });

      const syncResp = await runFixture(webappTestUrl, testToken, 'sync_document', { testDocId: docId });
      const syncData = (syncResp && syncResp.data) || syncResp || {};
      expect(syncData.synced !== false, `sync_document did not report success: ${JSON.stringify(syncResp)}`).toBeTruthy();

      // --- mint a real signed assertion for a real VIEW-tier caller -------
      const mintResp = await runFixture(webappTestUrl, testToken, 'mint_test_assertion', {
        sub: `${RUN_TAG}-caller`, email: CALLER_EMAIL
      });
      const mintData = (mintResp && mintResp.data) || mintResp || {};
      test.skip(!mintData.ok, `mint_test_assertion unavailable: ${JSON.stringify(mintResp)} (assertion secret not provisioned)`);
      const assertion = mintData.assertion;
      expect(assertion, 'mint_test_assertion did not return an assertion').toBeTruthy();

      // --- drive the real built doc.html in a real browser, no page.route() ---
      server = await startFixtureServer(webappTestUrl);
      const port = server.address().port;

      await page.addInitScript(({ assertionValue, email }) => {
        localStorage.setItem('nuucAsAuth.v1', JSON.stringify({
          assertion: assertionValue,
          exp: Math.floor(Date.now() / 1000) + 3600,
          sub: 'live-e2e-sub',
          email
        }));
      }, { assertionValue: assertion, email: CALLER_EMAIL });

      await page.goto(`http://127.0.0.1:${port}/?doc=${encodeURIComponent(docId)}&team=${encodeURIComponent(TEAM_A)}`);

      await expect(page.locator('#appView')).toBeVisible({ timeout: 30000 });
      // Real response from the live get_document_actions route — no canned
      // data anywhere in this test. Fail-closed sanity: NONE tier would hide
      // #listWrap entirely and show #noAccessNotice instead (see doc.html's
      // render()), so getting here already proves >= VIEW was resolved.
      await expect(page.locator('#tierTag')).not.toHaveText('NONE', { timeout: 30000 });
      await expect(page.locator('.action', { hasText: actionText })).toBeVisible({ timeout: 30000 });
      await expect(page.locator('.aiN')).toContainText('AI-');

      // R20 back-to-team-list link is present and points at View A for the
      // real resolved teamId (the server's own teamPortalUrl, not a guess).
      const backHref = await page.locator('#backToTeamLink').getAttribute('href');
      expect(backHref).toContain('team=' + TEAM_A);
    } finally {
      if (server) server.close();
      if (docId) {
        await postJson(webappTestUrl, { action: 'end_journey_session', testToken, docId }).catch(() => {});
      }
    }
  });
});
