/**
 * Structured server-side logger. Buffers entries in memory and flushes to a
 * Drive folder as NDJSON, and (best-effort) to Axiom, on demand or when the
 * buffer threshold is reached.
 *
 * Setup: set script property GAS_LOGGER_FOLDER_ID to a Drive folder ID that is
 * mapped locally via Drive for Desktop (used by tests to poll log files).
 * Axiom is optional: set AXIOM_TOKEN + AXIOM_DATASET script properties (via the
 * set_axiom_config route, same pattern as set_test_token) to enable it. Missing
 * config or a failed POST never blocks the Drive write (docs/atdd/journey-logging-
 * design.md §4.3, GTaskSheet-ishz.1) -- Axiom is additive, not a dependency.
 *
 * Dependency: every entry is stamped with a `version` field read from the global
 * BUILD_INFO.version (defined in Version.js) so Axiom queries can tell test/prod
 * apart by which build is actually running. This makes GasLogger no longer
 * standalone -- it expects BUILD_INFO to exist in the same Apps Script project
 * (true for every deployment of this project, since clasp bundles all .js files
 * into one global scope). Falls back to 'unknown' rather than throwing if
 * BUILD_INFO is ever missing (e.g. GasLogger copied into a project without it).
 *
 * Usage:
 *   GasLogger.log('sync.complete', { docId, changes: 3 });
 *   GasLogger.flush();  // call in finally block of every entry-point function
 *
 * Correlation: startOp()/endOp() stamp an `op` field (a uuid) onto every log()
 * entry made between the two calls, so a single top-level invocation's
 * sub-events (e.g. syncAll()'s per-doc sync.scanned/sync.complete) share one
 * queryable id instead of relying on time-proximity (GTaskSheet-65g1). Module-
 * level state is safe here because each GAS execution gets its own isolated
 * global scope -- concurrent invocations never share this variable.
 *
 * Cross-execution correlation: startOp(receivedOpId) never adopts the caller's
 * op id as this execution's own -- that would collapse concurrent/replayed
 * invocations under one id. Instead this execution still mints its own fresh
 * op, and (if a receivedOpId was passed in) stamps it onto every entry as a
 * separate `parentOp` field. getCurrentOp() lets a caller read its own op id
 * before issuing a UrlFetchApp call so it can pass it along as opId in the
 * request payload (GTaskSheet-j8cn).
 */
var GasLogger = (function () {
  var _folder = null;
  var _entries = [];
  var _enabled = true;
  var _currentOp = null;
  var _parentOp = null;
  var _axiomConfig = null;
  var FLUSH_THRESHOLD = 25;

  function _getFolder() {
    if (_folder) return _folder;
    var folderId = PropertiesService.getScriptProperties().getProperty('GAS_LOGGER_FOLDER_ID');
    if (folderId) {
      _folder = DriveApp.getFolderById(folderId);
      return _folder;
    }
    var root = DriveApp.getRootFolder();
    var iter = root.getFoldersByName('GActionSheet-Logs');
    _folder = iter.hasNext() ? iter.next() : root.createFolder('GActionSheet-Logs');
    return _folder;
  }

  function _getAxiomConfig() {
    if (_axiomConfig) return _axiomConfig;
    var props = PropertiesService.getScriptProperties();
    _axiomConfig = {
      token: props.getProperty('AXIOM_TOKEN'),
      dataset: props.getProperty('AXIOM_DATASET'),
    };
    return _axiomConfig;
  }

  function _postToAxiom(entries) {
    var config = _getAxiomConfig();
    var token = config.token;
    var dataset = config.dataset;
    if (!token || !dataset) return;
    try {
      var rows = entries.map(function (e) {
        var row = Object.assign({ _time: e.ts, name: e.tag, side: 'gas', version: e.version }, e.data || {});
        if (e.op) row.op = e.op;
        if (e.parentOp) row.parentOp = e.parentOp;
        return row;
      });
      var resp = UrlFetchApp.fetch(
        'https://api.axiom.co/v1/datasets/' + dataset + '/ingest',
        {
          method: 'post',
          contentType: 'application/json',
          headers: { Authorization: 'Bearer ' + token },
          payload: JSON.stringify(rows),
          muteHttpExceptions: true,
        }
      );
      if (resp.getResponseCode() >= 300) {
        // Visible in `clasp logs` (Stackdriver) only -- never recurse through
        // GasLogger.log() itself, and never block the Drive write either way.
        Logger.log('GasLogger: Axiom ingest non-2xx ' + resp.getResponseCode() + ': ' + resp.getContentText());
      }
    } catch (err) {
      // Best-effort only -- never let an Axiom outage block the Drive write.
      Logger.log('GasLogger: Axiom POST threw: ' + err);
    }
  }

  return {
    enable: function () { _enabled = true; },
    disable: function () { _enabled = false; },

    // Begin correlating every log() entry until endOp() is called. Returns
    // the generated op id (callers don't need it, but it's handy for tests).
    // receivedOpId (optional): a caller's own op id, propagated in as `parentOp`
    // on every entry -- this execution still mints its own fresh op either way.
    startOp: function (receivedOpId) {
      _currentOp = Utilities.getUuid();
      _parentOp = receivedOpId || null;
      return _currentOp;
    },

    endOp: function () { _currentOp = null; _parentOp = null; },

    // Lets a caller read its own current op id before issuing a UrlFetchApp
    // call into another execution, so it can pass it along as opId.
    getCurrentOp: function () { return _currentOp; },

    log: function (tag, data) {
      // version on every entry (not just call sites that remember to add it) so
      // Axiom queries can tell test/prod apart by which BUILD_INFO.version is
      // actually running, without touching the other ~190 call sites.
      var version = (typeof BUILD_INFO !== 'undefined' && BUILD_INFO.version) || 'unknown';
      var entry = { ts: new Date().toISOString(), tag: tag, version: version, data: data || {} };
      if (_currentOp) entry.op = _currentOp;
      if (_parentOp) entry.parentOp = _parentOp;
      Logger.log(JSON.stringify(entry));
      if (!_enabled) return;
      _entries.push(entry);
      if (_entries.length >= FLUSH_THRESHOLD) this.flush();
    },

    flush: function () {
      if (_entries.length === 0) return;
      var name = new Date().getTime() + '-' + Utilities.getUuid() + '.log';
      _getFolder().createFile(
        name,
        _entries.map(function (e) { return JSON.stringify(e); }).join('\n'),
        MimeType.PLAIN_TEXT
      );
      _postToAxiom(_entries);
      _entries = [];
    },
  };
})();
