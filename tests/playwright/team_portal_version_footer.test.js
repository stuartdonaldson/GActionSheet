/**
 * team_portal_version_footer.test.js — the static page interface contract's six
 * runtime requirements, asserted against the BUILT portal pages.
 *
 * Contract source: GAS-Core `best-practices/gas-static-frontend/README.md`
 * §"The static page interface contract". A static front end and the GAS backend it
 * talks to are two independently deployed halves. gas-static's `assertPublishedBuild`
 * closes the PUBLISH window (it polls the live version.json for version, env and
 * webappUrl); these six requirements close the RUNTIME one — a CDN edge still serving
 * the previous page, a visitor holding a cached document, a backend later rolled back.
 * F3Go30's static-pages/src/index.html is the estate's reference implementation and is
 * pinned by its own test/test_static_page_client_invariants.js; this is the same pin
 * for GActionSheet's two portal pages.
 *
 * Network-isolated by design, same rationale/pattern as
 * team_portal_query_routing.test.js: page.route() intercepts the exact
 * GACTIONSHEET_URL baked into the built page and returns canned responses. The point
 * here is what the PAGE does with the `serverVersion` every src/WebApp.js
 * `_jsonResponse` stamps — not a re-proof that the backend stamps it (that is
 * WebApp.js's own coverage) and not a live-backend test.
 *
 * Runs against static-portal/dist/sit/, the exact artifact the publish pipeline ships,
 * so a requirement that only holds in unstamped src/ cannot pass here.
 */
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const http = require('http');
const path = require('path');
const { loadSettings } = require('./_helpers');

test.use({ storageState: undefined, baseURL: undefined });

const REPO_ROOT = path.join(__dirname, '..', '..');
const DIST_DIR = path.join(REPO_ROOT, 'static-portal', 'dist', 'sit');
const SRC_DIR = path.join(REPO_ROOT, 'static-portal', 'src');

// The version stamped into dist/sit by the last build — read from the artifact itself
// rather than hardcoded, so this test never has to be touched on a version bump.
function stampedBuildVersion(file) {
  const m = fs.readFileSync(file, 'utf8').match(/var STATIC_BUILD_VERSION_ = "([^"]+)";/);
  expect(m, `${file} carries no stamped STATIC_BUILD_VERSION_ — run: ` +
    `node -e "require('./scripts/static-pages.js').build('sit')"`).toBeTruthy();
  return m[1];
}

/** Serves one page file at '/', so file:// origin quirks (localStorage, fetch) don't
 * enter into it. */
function startFixtureServer(file) {
  const html = fs.readFileSync(file, 'utf8');
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(html);
    });
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

async function primeCachedAuth(page) {
  await page.addInitScript(() => {
    localStorage.setItem('nuucAsAuth.v1', JSON.stringify({
      assertion: 'fixture.assertion.value',
      exp: Math.floor(Date.now() / 1000) + 3600,
      sub: 'version-footer-test-sub',
      email: 'version-footer-test@example.com'
    }));
  });
}

/** Answers every portal route with a canned body carrying `serverVersion`, and records
 * the request bodies so requirement 6 can be asserted on what actually went over the
 * wire (not on a source grep). */
function routeBackend(page, gactionsheetUrl, serverVersion, seen) {
  return page.route(gactionsheetUrl, async (route) => {
    const payload = JSON.parse(route.request().postData());
    seen.push(payload);
    const body = { serverVersion, tier: 'VIEW', actions: [], statusOptions: [] };
    if (payload.action === 'list_my_teams') {
      body.teams = [{ teamId: 'TeamAlpha', teamName: 'Team Alpha', tier: 'VIEW' }];
    }
    if (payload.action === 'get_document_actions') {
      body.teamId = 'TeamAlpha';
      body.docName = 'Fixture doc';
      body.docUrl = 'https://docs.google.com/document/d/fixture/edit';
      body.teamPortalUrl = 'index.html?team=TeamAlpha';
    }
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
}

const PAGES = [
  { name: 'index.html', file: path.join(DIST_DIR, 'index.html'), query: '' },
  { name: 'doc.html', file: path.join(DIST_DIR, 'doc.html'), query: '?doc=fixture&team=TeamAlpha' },
];

test.describe('@team-portal static page interface contract — version footer', () => {
  test.beforeAll(() => {
    for (const p of PAGES) {
      expect(fs.existsSync(p.file),
        `${p.file} missing — run: node -e "require('./scripts/static-pages.js').build('sit')"`).toBe(true);
    }
  });

  for (const p of PAGES) {
    test(`${p.name}: footer shows the build before any network call, and both versions on mismatch`,
      async ({ page }) => {
        const gactionsheetUrl = loadSettings().webappTestUrl;
        expect(gactionsheetUrl, 'webappTestUrl must be set in local.settings.json').toBeTruthy();
        const build = stampedBuildVersion(p.file);
        const serverVersion = build + '-newer';
        const seen = [];

        const server = await startFixtureServer(p.file);
        try {
          await primeCachedAuth(page);
          // Requirement 1: the footer is populated before any network call, stated in the
          // contract as "a page that cannot reach its backend still shows what it is" —
          // so failing every backend call outright is the honest test of it, not a race.
          await page.route(gactionsheetUrl, (route) => route.abort());
          await page.goto(`http://127.0.0.1:${server.address().port}/${p.query}`);
          await expect(page.locator('#buildBadge')).toHaveText(`SIT · v${build} (build)`);
          await expect(page.locator('#updateBanner')).not.toBeVisible();

          // Requirements 2 + 3: the server's version rides a response the page already
          // makes (every _jsonResponse stamps it — no dedicated version call), and on a
          // mismatch the footer names BOTH, client build first. The version read back off
          // this footer during support must be the one the visitor is actually running.
          await page.unrouteAll();
          await routeBackend(page, gactionsheetUrl, serverVersion, seen);
          await page.reload();
          await expect(page.locator('#buildBadge'))
            .toHaveText(`SIT · v${build} (build) · server v${serverVersion}`);
          await expect(page.locator('#buildBadge')).toHaveClass(/stale/);
          await expect(page.locator('#updateBanner')).toBeVisible();
          await expect(page.locator('#updateReloadBtn')).toBeVisible();

          // Requirement 6: every POST to our own backend carries the client build, so a
          // stale client surfaces in webapp.version.mismatch rather than in a support call.
          expect(seen.length).toBeGreaterThan(0);
          for (const req of seen) expect(req.clientVersion).toBe(build);
        } finally {
          server.close();
        }
      });

    test(`${p.name}: update dismissal is keyed to the version dismissed, not a boolean`,
      async ({ page }) => {
        const gactionsheetUrl = loadSettings().webappTestUrl;
        const build = stampedBuildVersion(p.file);
        const seen = [];

        const server = await startFixtureServer(p.file);
        try {
          await primeCachedAuth(page);
          await routeBackend(page, gactionsheetUrl, build + '-v1', seen);
          await page.goto(`http://127.0.0.1:${server.address().port}/${p.query}`);
          await expect(page.locator('#updateBanner')).toBeVisible();

          await page.click('#updateDismissBtn');
          await expect(page.locator('#updateBanner')).not.toBeVisible();

          // Same server version again: stays dismissed.
          await page.reload();
          await expect(page.locator('#buildBadge')).toContainText(`server v${build}-v1`);
          await expect(page.locator('#updateBanner')).not.toBeVisible();

          // A DIFFERENT server version prompts again. A boolean dismissal would have
          // silenced this one too — that is the whole point of the version key.
          await page.unroute(gactionsheetUrl);
          await routeBackend(page, gactionsheetUrl, build + '-v2', seen);
          await page.reload();
          await expect(page.locator('#updateBanner')).toBeVisible();
        } finally {
          server.close();
        }
      });

    test(`${p.name} (unbuilt src): a null client build is labelled, never reported as stale`,
      async ({ page }) => {
        // Requirement 5: unbuilt src/ served directly (local dev, Playwright) has no build
        // to be behind. Asserted against src/, not dist/, because that IS the condition.
        const srcFile = path.join(SRC_DIR, p.name);
        const server = await startFixtureServer(srcFile);
        try {
          await page.goto(`http://127.0.0.1:${server.address().port}/${p.query}`);
          await expect(page.locator('#buildBadge')).toHaveText('unbuilt source');
          await expect(page.locator('#buildBadge')).not.toHaveClass(/stale/);

          // Even once a server version is known, unbuilt is not staleness: the footer
          // names the server's version and the update prompt stays down.
          await page.evaluate(() => noteServerVersion_({ serverVersion: '99.99.99.99' }));
          await expect(page.locator('#buildBadge')).toHaveText('v99.99.99.99 (server)');
          await expect(page.locator('#updateBanner')).not.toBeVisible();
        } finally {
          server.close();
        }
      });
  }
});
