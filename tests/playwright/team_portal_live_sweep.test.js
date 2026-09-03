/**
 * team_portal_live_sweep.test.js — Unit E.5 (plan-79dw.md): true no-mock e2e
 * sweep over the remaining portal functionality that, before this file, was
 * only ever exercised through page.route() mocks (team_portal_wired_controls
 * .test.js, team_portal_query_routing.test.js) or Python
 * (tests/test_team_write_routes.py). Every other portal Playwright file
 * mocks GACTIONSHEET_URL; only cors_team_portal.test.js and
 * team_portal_view_b_live.test.js (Unit D) are true no-mock precedents —
 * this file follows their exact pattern (fixture server standing in for the
 * real nuuc-it.github.io cross-origin host, plain node fetch() for
 * testToken-gated setup, zero page.route() calls anywhere).
 *
 * Covers, all against the live SIT get build/GAS deployment:
 *   1. team list load (list_my_teams / list_team_actions) for a real
 *      VIEW-tier caller, driving the actual built static-portal/dist/sit/
 *      index.html.
 *   2. status change (team_patch_status) via a real UI click on the
 *      assignee status chip -- R17's VIEW-tier assignee-bypass path, which
 *      is the one write path a VIEW-tier identity CAN exercise end-to-end
 *      through the real UI.
 *   3. sync (team_sync_document) and Edit (team_edit_action) rejection
 *      shapes at VIEW tier -- invoked via the built page's OWN postJson()
 *      helper and its own baked-in GACTIONSHEET_URL/state (not a
 *      hand-rolled fetch), because the Sync/Edit UI controls are only
 *      rendered/enabled at EDIT tier (index.html's render()/rowHtml()), and
 *      no identity with EDIT (rather than VIEW) access to TestTeamA is
 *      currently configured -- the exact same documented gap
 *      tests/test_team_write_routes.py and tests/test_team_portal_hardening.py
 *      already carry (local.settings.json key 'teamAEditEmail', unset).
 *      This still catches real response-shape drift for those two routes;
 *      it just can't click through a control that structurally can't render
 *      without an access grant this suite doesn't have.
 *   4. (conditional, skipped with a clear reason if 'teamAEditEmail' is not
 *      configured, same convention as the Python precedents) an EDIT-tier
 *      caller's real sync + edit success paths, driven by an actual button
 *      click through the built page -- the one thing #3 above cannot do.
 *
 * Explicitly NOT re-testing: the authorization matrix (VIEW vs NONE vs
 * cross-folder EDIT, etc.) -- that's tests/test_team_write_routes.py's job
 * and stays Python/backend-only. This file's job is response-shape drift a
 * mocked test structurally cannot catch.
 */
const { test, expect } = require('@playwright/test');
const http = require('http');
const fs = require('fs');
const path = require('path');
const { loadSettings } = require('./_helpers');

test.use({ storageState: undefined, baseURL: undefined });

const TEAM_A = 'TestTeamA';
const TEAM_A_FOLDER_1 = '1SCPPZfUeSWqaE3WvWYl6go13lzEZQUbs';
const CALLER_EMAIL = 'stuart.donaldson@gmail.com'; // real VIEW-tier grant on TestTeamA (see test_view_b.py / test_team_write_routes.py)
const RUN_TAG = 'gts79dwe5live' + Date.now().toString(36);

const DIST_HTML = path.join(__dirname, '..', '..', 'static-portal', 'dist', 'sit', 'index.html');

function startFixtureServer() {
  // Stand-in for the real nuuc-it.github.io cross-origin host (same
  // rationale as cors_team_portal.test.js / team_portal_view_b_live.test.js)
  // -- serves the actual built index.html so its baked-in GACTIONSHEET_URL
  // is exercised for real, unmocked.
  const html = fs.readFileSync(DIST_HTML, 'utf8');
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

/** Seeds a real doc with a real AI-tagged action under TEAM_A_FOLDER_1,
 * synced, assigned to assigneeEmail. Returns { docId, actionText }. */
async function seedDoc(webappTestUrl, testToken, assigneeEmail, tag) {
  const begin = await postJson(webappTestUrl, { action: 'begin_journey_session', testToken });
  const docId = begin.docId;
  expect(docId, `begin_journey_session did not return a docId: ${JSON.stringify(begin)}`).toBeTruthy();

  const moveResp = await runFixture(webappTestUrl, testToken, 'move_doc_to_folder', {
    docId, folderId: TEAM_A_FOLDER_1
  });
  test.skip((moveResp && moveResp.ok === false) || false,
    `move_doc_to_folder failed: ${JSON.stringify(moveResp)}`);

  const actionText = `${RUN_TAG} ${tag} action`;
  await postJson(webappTestUrl, {
    action: 'append_doc_paragraph', testToken,
    testDocId: docId, text: `AI: ${assigneeEmail} ${actionText}`
  });

  const syncResp = await runFixture(webappTestUrl, testToken, 'sync_document', { testDocId: docId });
  const syncData = (syncResp && syncResp.data) || syncResp || {};
  expect(syncData.synced !== false, `sync_document did not report success: ${JSON.stringify(syncResp)}`).toBeTruthy();

  return { docId, actionText };
}

async function mintAssertion(webappTestUrl, testToken, sub, email) {
  const mintResp = await runFixture(webappTestUrl, testToken, 'mint_test_assertion', { sub, email });
  const mintData = (mintResp && mintResp.data) || mintResp || {};
  test.skip(!mintData.ok, `mint_test_assertion unavailable: ${JSON.stringify(mintResp)} (assertion secret not provisioned)`);
  const assertion = mintData.assertion;
  expect(assertion, 'mint_test_assertion did not return an assertion').toBeTruthy();
  return assertion;
}

test.describe('@team-portal @live Unit E.5 — full live portal sweep (no mocks)', () => {
  test.beforeAll(() => {
    expect(fs.existsSync(DIST_HTML),
      `${DIST_HTML} missing — run: node -e "require('./scripts/static-pages.js').build('sit')"`).toBe(true);
  });

  test('live team list load + assignee status change (R17) + VIEW-tier sync/edit rejection shapes -- real backend, no page.route()', async ({ page }) => {
    test.setTimeout(120000);
    const settings = loadSettings();
    const webappTestUrl = settings.webappTestUrl;
    const testToken = settings.testToken || '';
    expect(webappTestUrl, 'webappTestUrl must be set in local.settings.json').toBeTruthy();
    expect(testToken, 'testToken must be set in local.settings.json').toBeTruthy();

    let docId = null;
    let server = null;

    try {
      // --- seed a real doc/action assigned to the real VIEW-tier caller ---
      const seeded = await seedDoc(webappTestUrl, testToken, CALLER_EMAIL, 'live-sweep');
      docId = seeded.docId;
      const actionText = seeded.actionText;

      const assertion = await mintAssertion(webappTestUrl, testToken, `${RUN_TAG}-caller`, CALLER_EMAIL);

      // --- drive the real built index.html in a real browser, no page.route() ---
      server = await startFixtureServer();
      const port = server.address().port;

      await page.addInitScript(({ assertionValue, email }) => {
        localStorage.setItem('nuucAsAuth.v1', JSON.stringify({
          assertion: assertionValue,
          exp: Math.floor(Date.now() / 1000) + 3600,
          sub: 'live-e2e-sweep-sub',
          email
        }));
      }, { assertionValue: assertion, email: CALLER_EMAIL });

      // ---- 1. live team list load (list_my_teams / list_team_actions) ----
      await page.goto(`http://127.0.0.1:${port}/?team=${encodeURIComponent(TEAM_A)}`);
      await expect(page.locator('#appView')).toBeVisible({ timeout: 30000 });
      await expect(page.locator('#teamSel')).toHaveValue(TEAM_A, { timeout: 30000 });
      await expect(page.locator('.action', { hasText: actionText })).toBeVisible({ timeout: 30000 });

      let row = page.locator('.row', { has: page.locator('.action', { hasText: actionText }) });
      const globalId = await row.locator('[data-status-for]').getAttribute('data-status-for');
      expect(globalId, 'row did not carry a data-status-for global_id').toBeTruthy();

      // ---- 2. status change via a real UI click (team_patch_status, R17
      // assignee bypass -- the assignee is only VIEW tier here, no EDIT
      // grant needed for this route). Switch the status filter to "All"
      // FIRST: the default filter is statusFilter='open' (index.html's
      // state.status), so once the row's real status becomes "Closed" the
      // very refreshActions() the app fires after a successful patch would
      // filter the row straight out of the default view -- that's real
      // product behavior, not a bug, but it means the row would vanish from
      // the DOM rather than show "Closed" if we stayed on the default
      // filter. "All" keeps the row visible across the transition so the
      // live round trip is actually observable. ----
      await page.locator('#statusSeg [data-status="all"]').click();
      await expect(page.locator('.action', { hasText: actionText })).toBeVisible({ timeout: 30000 });
      row = page.locator('.row', { has: page.locator('.action', { hasText: actionText }) });

      const statusChip = row.locator('.status.mine');
      await expect(statusChip, 'assignee status chip (.status.mine) not found -- assignee_email must match the caller for R17 bypass to render as clickable').toBeVisible({ timeout: 15000 });
      await statusChip.click();
      await expect(page.locator('#statusMenu')).toBeVisible();
      await page.locator('#statusMenu [data-set="Closed"]').click();
      await expect(page.locator('.toast')).toHaveText('Status updated.', { timeout: 30000 });
      row = page.locator('.row', { has: page.locator('.action', { hasText: actionText }) });
      await expect(row.locator('.status')).toContainText('Closed', { timeout: 15000 });

      // ---- 3. sync + edit at VIEW tier: rejection response-shape, invoked
      // via the built page's own postJson()/GACTIONSHEET_URL/state (top-level
      // const/function declarations in a classic <script> share the page's
      // global lexical scope, so these are the same live identifiers the
      // Sync/Edit buttons would use -- not a hand-rolled fetch, and not
      // page.route()-mocked). The Sync/Edit buttons themselves are absent/
      // disabled at VIEW tier (index.html's render()/rowHtml()), so a real
      // click isn't possible without an EDIT-tier identity (see test below,
      // conditional on 'teamAEditEmail'). ----
      const syncResult = await page.evaluate((docIdArg) => {
        return postJson(GACTIONSHEET_URL, {
          action: 'team_sync_document', assertion: state.assertion, teamId: state.teamId, docId: docIdArg
        });
      }, docId);
      expect(syncResult.ok, `team_sync_document real response: ${JSON.stringify(syncResult)}`).toBe(false);
      expect(syncResult.outcome, `team_sync_document real response: ${JSON.stringify(syncResult)}`).toBe('rejected-VIEW');

      const editResult = await page.evaluate((gid) => {
        return postJson(GACTIONSHEET_URL, {
          action: 'team_edit_action', assertion: state.assertion, teamId: state.teamId,
          global_id: gid, fields: { action_text: 'SHOULD-NOT-APPLY-view-tier-edit' }
        });
      }, globalId);
      expect(editResult.ok, `team_edit_action real response: ${JSON.stringify(editResult)}`).toBe(false);
      expect(editResult.outcome, `team_edit_action real response: ${JSON.stringify(editResult)}`).toBe('rejected-doc-scope');

      // ---- durable-state check: the rejected edit attempt above must not
      // have mutated the real row; the status change from step 2 must have
      // (get_document_actions, a second live route, confirms both) ----
      const docView = await postJson(webappTestUrl, { action: 'get_document_actions', assertion, docId });
      const durableRow = (docView.actions || []).find(a => a.global_id === globalId);
      expect(durableRow, `get_document_actions did not return the seeded row: ${JSON.stringify(docView)}`).toBeTruthy();
      expect(durableRow.action_text, 'rejected team_edit_action must not have mutated durable state').toBe(actionText);
      expect(durableRow.status, 'team_patch_status change from step 2 must be durable').toBe('Closed');
    } finally {
      if (server) server.close();
      if (docId) {
        await postJson(webappTestUrl, { action: 'end_journey_session', testToken, docId }).catch(() => {});
      }
    }
  });

  test('EDIT-tier caller: real sync + edit success via actual UI button clicks (skipped if teamAEditEmail not configured)', async ({ page }) => {
    test.setTimeout(120000);
    const settings = loadSettings();
    const webappTestUrl = settings.webappTestUrl;
    const testToken = settings.testToken || '';
    const editEmail = settings.teamAEditEmail;
    test.skip(!editEmail,
      "teamAEditEmail not configured in local.settings.json -- no known identity holds " +
      "EDIT (vs VIEW) access to TestTeamA folder 1. Same documented gap as " +
      "tests/test_team_write_routes.py / tests/test_team_portal_hardening.py. " +
      "Configure teamAEditEmail with a real EDIT-granted identity to unskip.");
    expect(webappTestUrl, 'webappTestUrl must be set in local.settings.json').toBeTruthy();
    expect(testToken, 'testToken must be set in local.settings.json').toBeTruthy();

    let docId = null;
    let server = null;

    try {
      const seeded = await seedDoc(webappTestUrl, testToken, editEmail, 'edit-tier-live');
      docId = seeded.docId;
      const actionText = seeded.actionText;

      const assertion = await mintAssertion(webappTestUrl, testToken, `${RUN_TAG}-edit`, editEmail);

      // Precondition, mirroring test_team_portal_hardening.py's own gate:
      // confirm this identity really does resolve EDIT before trusting a
      // click-through success as meaningful (not fabricated).
      const resolved = await postJson(webappTestUrl, {
        action: 'verify_and_resolve_access', assertion, teamId: TEAM_A
      });
      expect(resolved.tier, `[precondition] teamAEditEmail must resolve EDIT on TestTeamA, got ${JSON.stringify(resolved)}`).toBe('EDIT');

      server = await startFixtureServer();
      const port = server.address().port;

      await page.addInitScript(({ assertionValue, email }) => {
        localStorage.setItem('nuucAsAuth.v1', JSON.stringify({
          assertion: assertionValue,
          exp: Math.floor(Date.now() / 1000) + 3600,
          sub: 'live-e2e-edit-tier-sub',
          email
        }));
      }, { assertionValue: assertion, email: editEmail });

      await page.goto(`http://127.0.0.1:${port}/?team=${encodeURIComponent(TEAM_A)}`);
      await expect(page.locator('#appView')).toBeVisible({ timeout: 30000 });
      await expect(page.locator('.action', { hasText: actionText })).toBeVisible({ timeout: 30000 });

      const group = page.locator('.docgroup', { has: page.locator('.action', { hasText: actionText }) });

      // ---- real sync via a real button click (team_sync_document, EDIT tier) ----
      const syncBtn = group.locator('[data-sync]');
      await expect(syncBtn).toBeEnabled({ timeout: 15000 });
      await syncBtn.click();
      await expect(page.locator('.toast')).toHaveText('Synced.', { timeout: 30000 });

      // ---- real edit via a real button click (team_edit_action, EDIT tier) ----
      const row = page.locator('.row', { has: page.locator('.action', { hasText: actionText }) });
      await row.locator('[data-edit]').click();
      const editedText = actionText + ' EDITED-BY-EDIT-TIER-LIVE';
      await page.locator('[data-field="action_text"]').fill(editedText);
      await page.locator('[data-save-edit]').click();
      await expect(page.locator('.toast')).toHaveText('Saved.', { timeout: 30000 });
      await expect(page.locator('.action', { hasText: editedText })).toBeVisible({ timeout: 15000 });

      // durable-state confirmation
      const docView = await postJson(webappTestUrl, { action: 'get_document_actions', assertion, docId });
      const durableRow = (docView.actions || []).find(a => a.action_text === editedText);
      expect(durableRow, `edited row not found durably: ${JSON.stringify(docView)}`).toBeTruthy();
    } finally {
      if (server) server.close();
      if (docId) {
        await postJson(webappTestUrl, { action: 'end_journey_session', testToken, docId }).catch(() => {});
      }
    }
  });
});
