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

  var fixtureName = payload.fixture   || '';
  var testDocId   = payload.testDocId || '';

  if (!fixtureName) {
    return _jsonResponse({ error: 'fixture name required' });
  }

  // Idempotency guard (gts-f3me.2 — same class as gts-f3me.1's
  // _handleAppendDocParagraph fix). scn/session.py's _http_post retries on
  // HTTP 404 / a non-JSON echo-page response, on the assumption the first
  // attempt never reached this handler. Fixture calls routed through here
  // include long-running full-corpus sweeps (e.g. sync_all_force_listing_
  // miss_multi's syncAll()) that can legitimately still be running -- or
  // may have already completed and only had its *response* lost to the
  // /exec -> script.googleusercontent.com routing glitch -- by the time a
  // same-opId retry arrives. A bare retry re-runs the fixture from scratch,
  // producing a real second execution (observed as two
  // sync.driveMetadata.batchFallback.fetched events sharing one parentOp,
  // ~3 minutes apart, in test_scoped_drive_listing.py). Dedupe on the
  // client-supplied opId (reused across every retry attempt of one logical
  // call), same as append_doc_paragraph: 21600s (CacheService's own max TTL)
  // comfortably covers even the slowest full-corpus fixture plus the retry
  // delay, and the key is scoped to a fresh uuid4 per logical call so a
  // stale entry can never collide with an unrelated later invocation.
  var opId     = payload.opId || '';
  var rfCache  = opId ? CacheService.getScriptCache() : null;
  var rfCacheKey = opId ? ('run_fixture:' + opId) : null;
  if (rfCache) {
    var rfCached = rfCache.get(rfCacheKey);
    if (rfCached) {
      return _jsonResponse(JSON.parse(rfCached));
    }
  }

  try {
    // Extract caller-supplied fixture data: everything except framework keys.
    // docId is threaded through as a real parameter (fixtureData.docId) rather
    // than staged into a shared script property — the previous TEST_DOC_ID
    // mutate/restore shim raced when two run_fixture calls were in flight
    // concurrently (parallel test workers): call B's restore could stomp
    // call A's still-in-progress override, or vice versa.
    var fixtureData = {};
    var _reserved = ['action', 'testToken', 'fixture', 'testDocId'];
    for (var _k in payload) {
      if (_reserved.indexOf(_k) === -1) {
        fixtureData[_k] = payload[_k];
      }
    }
    // gts-8gev: don't clobber a caller-supplied docId (e.g. move_doc_to_folder
    // callers that pass {docId: ...} directly instead of testDocId) with an
    // empty testDocId -- only backfill when the caller didn't already set one.
    if (!fixtureData.docId) {
      fixtureData.docId = testDocId;
    }

    var result = setupTestFixtures(fixtureName, fixtureData);
    var response = result || { tag: 'fixture.' + fixtureName, data: {} };
    if (rfCache) {
      // gts-u947 (stage regression-verify): CacheService.put() has a hard
      // ~100KB per-value cap in Apps Script. A whole-sheet-audit fixture
      // (e.g. dump_all_action_rows) can legitimately exceed that once the
      // live corpus grows large enough during a long sweep, throwing
      // "Argument too large: value" -- previously unguarded, so this whole
      // request 500'd to an HTML Apps Script error page instead of
      // returning the (perfectly good) JSON response computed above. The
      // opId dedupe cache is a best-effort optimization (guards against a
      // retried request re-running a fixture from scratch, gts-f3me.2) --
      // losing it for one oversized response just means a same-opId retry
      // re-executes the fixture instead of hitting the cache, which is
      // harmless for a read-only audit dump and only a minor cost even for
      // a mutating one. Skip-and-log beats failing the whole call.
      try {
        rfCache.put(rfCacheKey, JSON.stringify(response), 21600);
      } catch (cacheErr) {
        GasLogger.log('fixture.cachePutSkipped', {
          fixture: fixtureName,
          message: String(cacheErr && cacheErr.message || cacheErr)
        });
      }
    }
    return _jsonResponse(response);
  } finally {
    // gts-7389: this dispatcher previously never flushed GasLogger's buffer.
    // Any GasLogger.log() calls made by a fixture (or by the entry points it
    // drives, e.g. syncDocument()'s locked-skip early return, which itself
    // has no flush()) sat in the in-memory buffer -- per-execution state,
    // not carried by anything durable -- until either FLUSH_THRESHOLD (25
    // entries) was crossed by a later, unrelated request reusing a warm GAS
    // instance, or the instance was recycled and the entry was lost outright.
    // Either way the entry's `ts` is stamped at log() time, so a delayed
    // flush still lands in Axiom with a timestamp inside the *original*
    // request's window -- looking, to a human cross-referencing timestamps
    // after the fact, like the event "was there all along" while the live
    // test's own bounded wait_for_log poll (tests/helpers/gas_log.py) never
    // saw it in time and timed out. Flushing unconditionally here (mirrors
    // every other WebApp.js route) makes every run_fixture response
    // synchronously durable before the HTTP response returns, closing the
    // gap deterministically instead of leaving it to threshold/warm-reuse
    // luck.
    GasLogger.flush();
  }
}
