/**
 * team_portal_query_routing.test.js — Frontend query-string routing
 * regression for gts-79dw.4.24, static-portal/src/index.html.
 *
 * Two URL shapes are generated server-side and used to previously dead-end
 * client-side entirely (no location.search/URLSearchParams handling at
 * all): the chip-link CTA's `?doc=<docId>&team=<teamId>` (src/WebApp.js's
 * _handlePreviewNotice) and this page's own `teamPortalUrl`'s `?team=
 * <teamId>` (src/DocView.js). This test drives the actual built page
 * (static-portal/dist/sit/index.html, the exact artifact the publish
 * pipeline ships) in a real browser and asserts:
 *   1. ?team= preselects that team in the switcher instead of defaulting
 *      to teams[0], for a caller with access to >1 team.
 *   2. ?doc= now redirects to View B (doc.html, gts-79dw.4.23/Unit D) —
 *      updated from the original AC's "visible notice" expectation, which
 *      was an explicitly-interim placeholder for the period before View B
 *      existed (see index.html's QUERY_DOC handling and plan-79dw.md Unit
 *      C's Result note). This is not a regression: the placeholder behavior
 *      this case originally asserted is exactly what Unit D superseded.
 *   3. No-param load still defaults to the first team (regression guard).
 *
 * Network-isolated by design, same rationale/pattern as
 * team_portal_wired_controls.test.js: page.route() intercepts the exact
 * GACTIONSHEET_URL baked into the built page and returns canned responses,
 * so this is a frontend-routing test, not a re-proof of backend
 * authorization or of _handlePreviewNotice's URL construction (that's
 * plan-context.md's job to document and WebApp.js's existing coverage).
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

const CACHED_EMAIL = 'query-routing-test@example.com';

/** Seeds a cached auth record so the page skips GIS sign-in entirely and
 * goes straight to loadTeams() (see index.html's initAuth()/loadCachedAuth()). */
async function primeCachedAuth(page) {
  await page.addInitScript(({ email }) => {
    localStorage.setItem('nuucAsAuth.v1', JSON.stringify({
      assertion: 'fixture.assertion.value',
      exp: Math.floor(Date.now() / 1000) + 3600,
      sub: 'query-routing-test-sub',
      email
    }));
  }, { email: CACHED_EMAIL });
}

function routeTwoTeams(page, gactionsheetUrl) {
  return page.route(gactionsheetUrl, async (route) => {
    const payload = JSON.parse(route.request().postData());
    if (payload.action === 'list_my_teams') {
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({
        teams: [
          { teamId: 'TeamAlpha', teamName: 'Team Alpha', tier: 'VIEW' },
          { teamId: 'TeamBeta', teamName: 'Team Beta', tier: 'EDIT' }
        ]
      }) });
    }
    if (payload.action === 'list_team_actions') {
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({
        tier: payload.teamId === 'TeamBeta' ? 'EDIT' : 'VIEW', actions: [],
        statusOptions: [{ status: 'Open', icon: 'https://example.com/open.png', alt: 'Open' }]
      }) });
    }
    throw new Error('unexpected action: ' + payload.action);
  });
}

test.describe('@team-portal team portal query-string routing (gts-79dw.4.24)', () => {
  test.beforeAll(() => {
    expect(fs.existsSync(DIST_HTML),
      `${DIST_HTML} missing — run: node scripts/build-static-portal.js --env sit`).toBe(true);
  });

  test('?team= preselects that team instead of defaulting to the first team', async ({ page }) => {
    const settings = loadSettings();
    const gactionsheetUrl = settings.webappTestUrl;
    expect(gactionsheetUrl, 'webappTestUrl must be set in local.settings.json').toBeTruthy();

    const server = await startFixtureServer();
    const port = server.address().port;
    try {
      await primeCachedAuth(page);
      await routeTwoTeams(page, gactionsheetUrl);

      await page.goto(`http://127.0.0.1:${port}/?team=TeamBeta`);
      await expect(page.locator('#appView')).toBeVisible();
      await expect(page.locator('#teamSel')).toHaveValue('TeamBeta');
    } finally {
      server.close();
    }
  });

  /** Path-aware variant of startFixtureServer: serves the real built index.html
   * at '/', and a trivial static stub (no redirect script) at '/doc.html' — a
   * plain startFixtureServer() would serve the *same* index.html content at
   * both paths, and since that content still carries ?doc= in its own
   * location.search, the redirect would re-fire against itself forever
   * (location.replace('doc.html'+location.search) resolves to the same URL
   * whether the current path is '/' or already '/doc.html'). The stub here
   * only needs to be reachable — its content is irrelevant, since this case
   * proves index.html performs the redirect, not what doc.html itself does
   * (that's team_portal_view_b_live.test.js's job, Unit D). */
  function startRedirectAwareFixtureServer() {
    const indexHtml = fs.readFileSync(DIST_HTML, 'utf8');
    return new Promise((resolve) => {
      const server = http.createServer((req, res) => {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        if ((req.url || '').startsWith('/doc.html')) {
          res.end('<!doctype html><html><body>doc.html stub reached</body></html>');
        } else {
          res.end(indexHtml);
        }
      });
      server.listen(0, '127.0.0.1', () => resolve(server));
    });
  }

  test('?doc= redirects to View B (doc.html) instead of showing the retired docViewNotice placeholder', async ({ page }) => {
    const settings = loadSettings();
    const gactionsheetUrl = settings.webappTestUrl;
    const server = await startRedirectAwareFixtureServer();
    const port = server.address().port;
    try {
      await primeCachedAuth(page);
      await routeTwoTeams(page, gactionsheetUrl);

      await page.goto(`http://127.0.0.1:${port}/?doc=some-doc-id&team=TeamAlpha`);
      await page.waitForURL(url => url.pathname.endsWith('/doc.html'), { timeout: 5000 });
      const url = new URL(page.url());
      expect(url.pathname.endsWith('/doc.html')).toBe(true);
      expect(url.searchParams.get('doc')).toBe('some-doc-id');
      expect(url.searchParams.get('team')).toBe('TeamAlpha');
    } finally {
      server.close();
    }
  });

  test('no-param load still defaults to the first team (regression guard)', async ({ page }) => {
    const settings = loadSettings();
    const gactionsheetUrl = settings.webappTestUrl;
    const server = await startFixtureServer();
    const port = server.address().port;
    try {
      await primeCachedAuth(page);
      await routeTwoTeams(page, gactionsheetUrl);

      await page.goto(`http://127.0.0.1:${port}/`);
      await expect(page.locator('#appView')).toBeVisible();
      await expect(page.locator('#teamSel')).toHaveValue('TeamAlpha');
      // No redirect must occur without ?doc= present (regression guard).
      expect(new URL(page.url()).pathname.endsWith('/doc.html')).toBe(false);
    } finally {
      server.close();
    }
  });
});
