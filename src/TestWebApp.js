/**
 * TestWebApp.js
 *
 * HTTP fixture dispatcher for integration tests.
 *
 * Provides a doPost route (`run_fixture`) that invokes GAS test fixture
 * functions directly, bypassing the Sheets UI and Playwright.
 *
 * Security model:
 *   - Validated by a per-deployment TEST_TOKEN (separate from WEBAPP_SECRET).
 *   - Token expires TEST_TOKEN_EXPIRES hours after `npm run deploy:test`.
 *   - Token is registered via the `set_test_token` action in WebApp.js.
 *   - Only the `run_fixture` action uses this token; all production routes
 *     continue to use WEBAPP_SECRET.
 *
 * Flow:
 *   1. Deployment script generates UUID testToken, POSTs set_test_token to WebApp.
 *   2. GAS stores testToken + expiresAt in Script Properties.
 *   3. Deployment script writes testToken to local.settings.json.
 *   4. Python tests POST run_fixture with testToken — no browser needed.
 *   5. GAS runs the fixture synchronously and returns { tag, data } in the body.
 */

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
 * Token errors return plain text (not JSON) to match doPost's unauthorized
 * response style: 'test-token-unauthorized' or 'test-token-expired'.
 */
function _handleRunFixture(payload) {
  var props     = PropertiesService.getScriptProperties();
  var stored    = props.getProperty('TEST_TOKEN')         || '';
  var expiresAt = props.getProperty('TEST_TOKEN_EXPIRES') || '';
  var incoming  = payload.testToken || '';

  // Token presence + match check.
  if (!stored || incoming !== stored) {
    return ContentService
      .createTextOutput('test-token-unauthorized')
      .setMimeType(ContentService.MimeType.TEXT);
  }

  // TEST_TOKEN_EXPIRES must be set and in the future; deploy:test always writes it.
  if (!expiresAt || new Date() > new Date(expiresAt)) {
    return ContentService
      .createTextOutput('test-token-expired')
      .setMimeType(ContentService.MimeType.TEXT);
  }

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
