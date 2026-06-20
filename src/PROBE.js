/**
 * PROBE.js — Deployment & identity instrumentation.
 *
 * Set PROBE_ENABLED = false to silence all probes without removing call sites.
 * Delete this file + all lines marked [PROBE] from call sites to strip permanently.
 *
 * All GasLogger tags are prefixed "probe." — one grep finds everything.
 * RunId is the primary correlation key; seed it via a doGet/doPost hit before
 * exercising UI surfaces (sidebar, chip hover, menu).
 *
 * See staging/probe-deployment-identity-spec.md for full protocol.
 */

var PROBE_ENABLED = false;
var PROBE_RUN_ID_KEY = 'PROBE_RUN_ID';

/**
 * Store runId received from Playwright. Idempotent — last write wins.
 * @param {string} runId
 */
function PROBE_setRunId(runId) {
  if (!PROBE_ENABLED || !runId) return;
  try {
    PropertiesService.getScriptProperties().setProperty(PROBE_RUN_ID_KEY, runId);
  } catch (e) {
    Logger.log('PROBE.setRunId.error: ' + e.message);
  }
}

/**
 * Read back the stored runId. Returns empty string if not set.
 * @returns {string}
 */
function PROBE_getRunId() {
  if (!PROBE_ENABLED) return '';
  try {
    return PropertiesService.getScriptProperties().getProperty(PROBE_RUN_ID_KEY) || '';
  } catch (e) {
    return '';
  }
}

/**
 * Log a probe entry.
 * @param {string} surface  Surface ID from spec §1.3 (e.g. 'doGet.test', 'sidebar.existing')
 * @param {Object} extraData  Merged into the log entry (caller wins on collision)
 */
function PROBE_log(surface, extraData) {
  if (!PROBE_ENABLED) return;

  var serviceUrl = '';
  try { serviceUrl = ScriptApp.getService().getUrl(); } catch (_) {}

  var effectiveUser = '';
  var activeUser = '';
  try { effectiveUser = Session.getEffectiveUser().getEmail(); } catch (_) {}
  try { activeUser    = Session.getActiveUser().getEmail();    } catch (_) {}

  var entry = {
    runId:         PROBE_getRunId(),
    surface:       surface,
    timestamp:     new Date().toISOString(),
    effectiveUser: effectiveUser,
    activeUser:    activeUser,
    version:       BUILD_INFO.version,
    buildDate:     BUILD_INFO.buildDate,
    webappUrl:     BUILD_INFO.webappUrl || '',
    serviceUrl:    serviceUrl
  };

  var extra = extraData || {};
  var keys = Object.keys(extra);
  for (var i = 0; i < keys.length; i++) entry[keys[i]] = extra[keys[i]];

  GasLogger.log('probe.' + surface, entry);
  GasLogger.flush();
}

/**
 * Returns 'existing' if the doc body contains AI-N tokens, 'new' otherwise.
 * Returns 'unknown' if doc is null or body is unreadable.
 * @param {GoogleAppsScript.Document.Document|null} doc
 * @returns {'new'|'existing'|'unknown'}
 */
function PROBE_docState(doc) {
  if (!doc) return 'unknown';
  try {
    return /AI-\d+:/.test(doc.getBody().getText()) ? 'existing' : 'new';
  } catch (_) { return 'unknown'; }
}
