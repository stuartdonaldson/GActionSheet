/**
 * TestWebApp.js
 *
 * HTTP fixture dispatcher and test-support routes for integration tests.
 *
 * Provides:
 *   - `run_fixture`: invokes GAS test fixture functions directly.
 *   - `edit_action_row`, `find_sheet_actions`: ATDD test-support routes defined
 *     in ContractSchema.js testRouteNames; operate on production data but have
 *     no production caller (ContractSchema.js webApp.testRouteNames, bead .9).
 *   - `begin_journey_session`, `end_journey_session`: ATDD session lifecycle
 *     (AtddContracts.js sessionRouteNames).
 *
 * Security model:
 *   - All routes in this file are validated by a per-deployment TEST_TOKEN
 *     (separate from WEBAPP_SECRET).
 *   - Token expires TEST_TOKEN_EXPIRES hours after `npm run deploy:test`.
 *   - Token is registered via the `set_test_token` action in WebApp.js.
 *   - Production routes continue to use WEBAPP_SECRET.
 *
 * Flow:
 *   1. Deployment script generates UUID testToken, POSTs set_test_token to WebApp.
 *   2. GAS stores testToken + expiresAt in Script Properties.
 *   3. Deployment script writes testToken to local.settings.json.
 *   4. Python tests POST run_fixture / testRouteNames with testToken — no browser needed.
 *   5. GAS runs the handler synchronously and returns JSON in the body.
 */

/**
 * Validates the incoming testToken against Script Properties.
 * Returns null when the token is valid.
 * Returns a plain-text ContentService response when invalid or expired,
 * matching doPost's unauthorized response style.
 *
 * @param {string} incoming
 * @return {GoogleAppsScript.Content.TextOutput|null}
 */
function _checkTestToken(incoming) {
  var props     = PropertiesService.getScriptProperties();
  var stored    = props.getProperty('TEST_TOKEN')         || '';
  var expiresAt = props.getProperty('TEST_TOKEN_EXPIRES') || '';

  if (!stored || incoming !== stored) {
    return ContentService
      .createTextOutput('test-token-unauthorized')
      .setMimeType(ContentService.MimeType.TEXT);
  }
  if (!expiresAt || new Date() > new Date(expiresAt)) {
    return ContentService
      .createTextOutput('test-token-expired')
      .setMimeType(ContentService.MimeType.TEXT);
  }
  return null;
}

/**
 * HTTP fixture dispatcher.  Called from doPost in WebApp.js when
 * payload.action === 'run_fixture'.
 *
 * Payload shape:
 *   { action: 'run_fixture', testToken, fixture, testDocId? }
 *
 * Response shape (success):
 *   { tag: 'fixture.<name>', data: { ... } }
 *
 * Response shape (error):
 *   { error: '<message>' }
 *
 * Token errors return plain text: 'test-token-unauthorized' or 'test-token-expired'.
 */
function _handleRunFixture(payload) {
  var tokenError = _checkTestToken(payload.testToken || '');
  if (tokenError) return tokenError;

  var props = PropertiesService.getScriptProperties();
  var fixtureName = payload.fixture   || '';
  var testDocId   = payload.testDocId || '';
  var previousTestDocId = props.getProperty('TEST_DOC_ID') || '';

  if (!fixtureName) {
    return _jsonResponse({ error: 'fixture name required' });
  }

  // Allow caller to override TEST_DOC_ID for the duration of this invocation.
  // begin/end session fixtures intentionally manage persistent session state;
  // all other fixtures restore the prior TEST_DOC_ID when they finish.
  var shouldRestoreTestDocId = !!testDocId &&
    fixtureName !== 'begin_test_session' &&
    fixtureName !== 'end_test_session';

  try {
    if (testDocId) {
      props.setProperty('TEST_DOC_ID', testDocId);
    }

    var result = setupTestFixtures(fixtureName);
    return _jsonResponse(result || { tag: 'fixture.' + fixtureName, data: {} });
  } finally {
    if (shouldRestoreTestDocId) {
      if (previousTestDocId) {
        props.setProperty('TEST_DOC_ID', previousTestDocId);
      } else {
        props.deleteProperty('TEST_DOC_ID');
      }
    }
  }
}
