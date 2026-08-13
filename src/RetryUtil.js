/**
 * RetryUtil.js
 *
 * Bounded-retry wrapper for GAS built-in/advanced-service calls that fail by
 * *throwing* a transient exception (DocumentApp.openById, SpreadsheetApp.
 * openById/open, DriveApp.getFileById/getFolderById, and similar) rather than
 * returning an HTTP response code.
 *
 * This is the exception-based analog of SyncManager.js::_fetchDriveWithRetry
 * (gts-pm72), which retries Drive REST UrlFetchApp.fetch calls on a 5xx
 * response code. That wrapper cannot cover built-in/advanced-service calls
 * because they never surface a response code to inspect -- Google-side
 * transience there shows up only as a thrown Error whose message happens to
 * match a known shape (e.g. "Service Documents failed while accessing
 * document with id ..."). gts-bops closes that gap with a second wrapper
 * shaped for the exception case, plus a scan-and-apply pass across the
 * production call sites known to hit it (see gts-bops description for the
 * file list and exclusions).
 */

/** Bounded-retry convention, matching _fetchDriveWithRetry's own constants
 *  (3 attempts, 1s backoff) so both wrappers behave identically by default. */
var _GAS_RETRY_MAX_ATTEMPTS = 3;
var _GAS_RETRY_DELAY_MS     = 1000;

/**
 * Error-message patterns that identify Google-side transient noise rather
 * than a real answer (invalid id, permission denied, not found, etc. all
 * produce distinctly different messages and are deliberately NOT matched
 * here, so they still fail on attempt 1 -- mirrors _fetchDriveWithRetry only
 * retrying 5xx, never 4xx).
 */
var _GAS_RETRYABLE_ERROR_PATTERNS = [
  /^Service \w+ failed/i,
  /^Service invoked too many times/i,
  /^Internal error/i,
  /server error occurred/i
];

/**
 * Classifies a caught error as retryable (transient Google-side noise) or
 * not (a real answer that should surface immediately). Exposed as the
 * default `isRetryable` for withGasRetry; callers may override per call.
 *
 * @param {Error} e
 * @return {boolean}
 */
function _isRetryableGasError(e) {
  var msg = (e && e.message) || String(e);
  for (var i = 0; i < _GAS_RETRYABLE_ERROR_PATTERNS.length; i++) {
    if (_GAS_RETRYABLE_ERROR_PATTERNS[i].test(msg)) return true;
  }
  return false;
}

/**
 * Test-only fault injection (Backstop proof, gts-bops) -- mirrors
 * _driveFetchTestOverrideCode's Script-Properties-counter pattern rather
 * than monkey-patching DocumentApp/SpreadsheetApp/DriveApp globals directly
 * (those are not safely reassignable at the top level the way pm72's
 * UrlFetchApp.fetch override was). Never trips outside the test harness --
 * a real caller's label will simply never have this property set.
 *
 * A fixture sets `_TEST_FORCE_GAS_RETRY_FAIL_COUNT:<label>` in Script
 * Properties to N; the next N calls to withGasRetry(label, ...) throw a
 * synthetic retryable error instead of invoking fn(), decrementing the
 * counter each time, so real fn() only actually runs once the count is
 * exhausted (or on a fresh, unset label).
 *
 * @param {string} label
 * @return {boolean} true if this attempt should be forced to fail
 */
function _gasRetryTestShouldForceFailure(label) {
  var props = PropertiesService.getScriptProperties();
  var key   = '_TEST_FORCE_GAS_RETRY_FAIL_COUNT:' + label;
  var raw   = props.getProperty(key);
  if (!raw) return false;
  var remaining = parseInt(raw, 10);
  if (!remaining || remaining <= 0) return false;
  props.setProperty(key, String(remaining - 1));
  return true;
}

/**
 * Executes `fn` with a bounded retry on transient GAS built-in/advanced-
 * service exceptions.
 *
 * @param {string} label  Human-readable call-site tag, logged verbatim on
 *   every retry/exhaustion/recovery event so a failure log line names its
 *   own origin without a stack-trace guessing game (e.g.
 *   'TrackerTable.insertTrackerTable:DocumentApp.openById'). Convention:
 *   '<File>.<function>:<call>'.
 * @param {function(): *} fn  Zero-arg thunk performing the risky call (and
 *   any immediately-chained calls that should be retried together, e.g.
 *   `DriveApp.getFileById(id).isTrashed()`).
 * @param {{maxAttempts:?number, delayMs:?number, isRetryable:?function(Error):boolean}} [options]
 * @return {*} fn()'s return value on success.
 * @throws rethrows fn()'s last exception once attempts are exhausted, or
 *   immediately if the exception is classified non-retryable.
 */
function withGasRetry(label, fn, options) {
  options = options || {};
  var maxAttempts = options.maxAttempts || _GAS_RETRY_MAX_ATTEMPTS;
  var delayMs     = (options.delayMs != null) ? options.delayMs : _GAS_RETRY_DELAY_MS;
  var isRetryable = options.isRetryable || _isRetryableGasError;

  for (var attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      if (_gasRetryTestShouldForceFailure(label)) {
        throw new Error('Service Documents failed while accessing document with id TEST-FORCED.');
      }
      var result = fn();
      if (attempt > 1) {
        GasLogger.log('gasRetry.recovered', { label: label, attempts: attempt });
      }
      return result;
    } catch (e) {
      var retryable = isRetryable(e);
      if (!retryable || attempt === maxAttempts) {
        GasLogger.log('gasRetry.exhausted', {
          label:     label,
          attempts:  attempt,
          retryable: retryable,
          msg:       e && e.message
        });
        throw e;
      }
      GasLogger.log('gasRetry.attempt', {
        label:       label,
        attempt:     attempt,
        maxAttempts: maxAttempts,
        msg:         e && e.message
      });
      Utilities.sleep(delayMs);
    }
  }
  // Unreachable -- the loop always returns or throws.
}
