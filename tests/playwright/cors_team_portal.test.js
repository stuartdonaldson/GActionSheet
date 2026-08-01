/**
 * cors_team_portal.test.js — Cross-origin regression for the verified team
 * portal (gts-79dw.4.10).
 *
 * Reproduces the mechanism that proved Spike S1 (docs/verified-team-portal-plan.md
 * §5, A1/A7): a *browser* fetch() from a genuinely different origin than
 * script.google.com, using a text/plain body so the request stays a CORS-simple
 * request (no preflight). Node/Python HTTP clients never enforce CORS, so this
 * has to run inside a real browser context — hence Playwright, not scn/session.py.
 *
 * This test does NOT drive a live GIS sign-in (that requires an interactive
 * Google consent flow with no stable test hook — see tests/test_verify_access.py's
 * skip-if-unconfigured convention for the same limitation). Instead it sends a
 * syntactically-valid-but-unverifiable assertion string and asserts on the
 * fail-closed contract (tier: 'NONE' / ok: false) documented in
 * src/AccessControl.js (_handleListMyTeams, _handleListTeamActions) and
 * src/TeamSync.js (_handleTeamSyncDocument). The point under test is CORS
 * reachability + response shape, not identity verification (that's
 * tests/test_verify_access.py's job).
 *
 * Fixture page: a tiny local static server on 127.0.0.1 (ephemeral port) —
 * genuinely cross-origin from https://script.google.com, standing in for
 * https://nuuc-it.github.io (not yet pushed live — see gts-79dw.4.10 report).
 * Uses the exact fetch() idiom from Static/pub/AS/index.html's postJson().
 */

const { test, expect } = require('@playwright/test');
const http = require('http');
const { loadSettings } = require('./_helpers');

test.use({ storageState: undefined, baseURL: undefined });

function startFixtureServer(html) {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(html);
    });
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

function fixtureHtml(gactionsheetUrl) {
  return `<!doctype html>
<html><body>
<script>
  window.__results = {};
  function postJson(url, payload) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body: JSON.stringify(payload)
    }).then(r => r.text()).then(text => {
      try { return { ok: true, json: JSON.parse(text) }; }
      catch (e) { return { ok: true, json: null, raw: text }; }
    }).catch(e => ({ ok: false, error: String(e && e.message || e) }));
  }

  window.__run = async function(gactionsheetUrl, bogusAssertion) {
    window.__results.listMyTeams = await postJson(gactionsheetUrl, {
      action: 'list_my_teams', assertion: bogusAssertion
    });
    window.__results.listTeamActions = await postJson(gactionsheetUrl, {
      action: 'list_team_actions', assertion: bogusAssertion, teamId: 'TestTeamA'
    });
    window.__results.teamSyncDocument = await postJson(gactionsheetUrl, {
      action: 'team_sync_document', assertion: bogusAssertion, teamId: 'TestTeamA', docId: 'nonexistent'
    });
    window.__done = true;
  };
</script>
</body></html>`;
}

test('@cors cross-origin browser fetch reaches list_my_teams/list_team_actions/team_sync_document', async ({ page }) => {
  test.setTimeout(60000);
  const settings = loadSettings();
  const gactionsheetUrl = settings.webappTestUrl;
  expect(gactionsheetUrl, 'webappTestUrl must be set in local.settings.json').toBeTruthy();

  const server = await startFixtureServer(fixtureHtml(gactionsheetUrl));
  const port = server.address().port;

  try {
    await page.goto(`http://127.0.0.1:${port}/`);

    // Confirm the fixture page's origin is genuinely different from script.google.com —
    // the whole point of this test vs. a plain Python HTTP call.
    const origin = await page.evaluate(() => window.location.origin);
    expect(origin).toBe(`http://127.0.0.1:${port}`);
    expect(origin).not.toContain('google.com');

    await page.evaluate(([url]) => window.__run(url, 'bogus.not-a-real-assertion.value'), [gactionsheetUrl]);
    await page.waitForFunction(() => window.__done === true, { timeout: 30000 });
    const results = await page.evaluate(() => window.__results);

    // --- list_my_teams: CORS must not block the request; fail-closed on a bad assertion ---
    expect(results.listMyTeams.ok, 'list_my_teams fetch blocked/failed: ' + JSON.stringify(results.listMyTeams)).toBe(true);
    expect(results.listMyTeams.json, 'list_my_teams did not return JSON: ' + JSON.stringify(results.listMyTeams)).toBeTruthy();
    expect(results.listMyTeams.json.teams).toEqual([]);

    // --- list_team_actions: same shape, tier resolves to NONE, no rows leaked ---
    expect(results.listTeamActions.ok, 'list_team_actions fetch blocked/failed: ' + JSON.stringify(results.listTeamActions)).toBe(true);
    expect(results.listTeamActions.json, 'list_team_actions did not return JSON').toBeTruthy();
    expect(results.listTeamActions.json.tier).toBe('NONE');
    expect(results.listTeamActions.json.actions).toEqual([]);

    // --- team_sync_document: same shape, write rejected before any mutation ---
    expect(results.teamSyncDocument.ok, 'team_sync_document fetch blocked/failed: ' + JSON.stringify(results.teamSyncDocument)).toBe(true);
    expect(results.teamSyncDocument.json, 'team_sync_document did not return JSON').toBeTruthy();
    expect(results.teamSyncDocument.json.ok).toBe(false);
    expect(results.teamSyncDocument.json.outcome).toBe('rejected-NONE');
  } finally {
    server.close();
  }
});
