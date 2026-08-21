/**
 * Structured server-side logger. Buffers entries in memory and flushes to a
 * Drive folder as NDJSON, and (best-effort) to Axiom, on demand or when the
 * buffer threshold is reached.
 *
 * Setup: set script property GAS_LOGGER_FOLDER_ID to a Drive folder ID that is
 * mapped locally via Drive for Desktop (used by tests to poll log files).
 * Axiom is optional: set AXIOM_TOKEN + AXIOM_DATASET script properties (via the
 * set_axiom_config route, same pattern as set_test_token) to enable it. Once
 * configured, Axiom is the sole sink -- flush() does not also write the Drive
 * file, even if the POST fails (gts-ishz.2/ishz.3). A broken Axiom pipe
 * is meant to surface as a test timeout (polling Axiom for an entry that never
 * lands), not be silently absorbed by a Drive-file fallback. The Drive file
 * remains the path used only when Axiom isn't configured at all.
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
 * queryable id instead of relying on time-proximity (gts-65g1). Module-
 * level state is safe here because each GAS execution gets its own isolated
 * global scope -- concurrent invocations never share this variable.
 *
 * Cross-execution correlation: startOp(receivedOpId) never adopts the caller's
 * op id as this execution's own -- that would collapse concurrent/replayed
 * invocations under one id. Instead this execution still mints its own fresh
 * op, and (if a receivedOpId was passed in) stamps it onto every entry as a
 * separate `parentOp` field. getCurrentOp() lets a caller read its own op id
 * before issuing a UrlFetchApp call so it can pass it along as opId in the
 * request payload (gts-j8cn).
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

  function _writeToFile(entries) {
    var name = new Date().getTime() + '-' + Utilities.getUuid() + '.log';
    _getFolder().createFile(
      name,
      entries.map(function (e) { return JSON.stringify(e); }).join('\n'),
      MimeType.PLAIN_TEXT
    );
  }

  // Script-property flag name (gts-pfyx). Deliberately NOT another GasLogger.log()
  // call -- a self-report event would flow back through this same _postToAxiom
  // path (flattened into new `data` columns) and could itself be rejected by the
  // same column-limit problem it's reporting. Script properties have no such
  // limit, so this is the one channel guaranteed to work even when Axiom ingest
  // is fully wedged. Logger.log (Stackdriver, via `clasp logs`) remains the other.
  var AXIOM_DEGRADED_PROP = 'AXIOM_INGEST_DEGRADED';

  function _setAxiomDegraded(status, bodyText, entries) {
    var tags = [];
    for (var i = 0; i < entries.length && tags.length < 5; i++) {
      if (tags.indexOf(entries[i].tag) === -1) tags.push(entries[i].tag);
    }
    var info = {
      ts: new Date().toISOString(),
      status: status,
      body: (bodyText || '').slice(0, 300),
      sampleTags: tags,
    };
    try {
      PropertiesService.getScriptProperties().setProperty(AXIOM_DEGRADED_PROP, JSON.stringify(info));
    } catch (err) {
      Logger.log('GasLogger: failed to set ' + AXIOM_DEGRADED_PROP + ': ' + err);
    }
  }

  function _clearAxiomDegraded() {
    try {
      var props = PropertiesService.getScriptProperties();
      if (props.getProperty(AXIOM_DEGRADED_PROP)) props.deleteProperty(AXIOM_DEGRADED_PROP);
    } catch (err) {
      Logger.log('GasLogger: failed to clear ' + AXIOM_DEGRADED_PROP + ': ' + err);
    }
  }

  function _postToAxiom(entries) {
    var config = _getAxiomConfig();
    var token = config.token;
    var dataset = config.dataset;
    if (!token || !dataset) return true;
    try {
      // Every event's payload nests under one 'data' field rather than being
      // spread as top-level keys (gts-pfyx follow-up). The 'nuuts' dataset hit
      // its 256-field schema limit because each distinct e.data key, across
      // ~100+ call sites, minted a permanent new column -- and a dynamic-key
      // payload (e.g. WebApp.js markedByDocId, one key per docId ever seen)
      // grows that count without bound. Configure 'data' as an Axiom map
      // field (dataset settings, once) so its many sub-keys count as a single
      // field regardless of how many distinct event shapes flow through it.
      // Query with data.foo / data['foo'] (see scripts/query_axiom.py).
      //
      // A handful of fields stay real top-level columns instead of nesting,
      // because they're exactly what queries filter/group by, and a single
      // column with many distinct VALUES is fine -- unlike markedByDocId,
      // this never mints a new COLUMN per value:
      //   - env: 'test'/'dev'/'production' (BUILD_INFO.env, Version.js) --
      //     previously only readable by substring-matching the free-text
      //     'version' field ("... (TEST)"); now a clean equality filter.
      //   - docId / docIds: hoisted out of e.data when present, since "every
      //     event touching document X" is the single most common cross-
      //     event query shape. Removed from the nested 'data' copy so there
      //     is one source of truth per event, not two copies that could
      //     drift.
      //   - eu: acting-user email (WebApp.js's _getIdentity().eu), hoisted
      //     for the same reason -- "every event by user X" is a common
      //     cross-event query shape, and a single column with many distinct
      //     VALUES is fine here too.
      var _HOISTED_KEYS = ['docId', 'docIds', 'eu'];
      var rows = entries.map(function (e) {
        var payload = e.data || {};
        var row = {
          _time: e.ts, name: e.tag, side: 'gas', app: 'gactionsheet',
          version: e.version,
          env: (typeof BUILD_INFO !== 'undefined' && BUILD_INFO.env) || 'unknown',
        };
        if (e.op) row.op = e.op;
        if (e.parentOp) row.parentOp = e.parentOp;
        var rest = {};
        var hoistedAny = false;
        for (var k in payload) {
          if (_HOISTED_KEYS.indexOf(k) !== -1) {
            row[k] = payload[k];
            hoistedAny = true;
          } else {
            rest[k] = payload[k];
          }
        }
        row.data = hoistedAny ? rest : payload;
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
        // GasLogger.log() itself. Intentionally NOT written to Drive either --
        // a broken Axiom pipe is meant to surface as a test timeout, not be
        // silently absorbed by a file fallback (gts-ishz.2/ishz.3). It IS,
        // however, surfaced via AXIOM_DEGRADED_PROP (gts-pfyx) so a human or
        // test harness can cheaply check "is Axiom ingest currently broken"
        // instead of only discovering it as an unexplained 60s test timeout.
        var bodyText = resp.getContentText();
        Logger.log('GasLogger: Axiom ingest non-2xx ' + resp.getResponseCode() + ': ' + bodyText);
        _setAxiomDegraded(resp.getResponseCode(), bodyText, entries);
        return false;
      }
      _clearAxiomDegraded();
      return true;
    } catch (err) {
      Logger.log('GasLogger: Axiom POST threw: ' + err);
      _setAxiomDegraded('exception', String(err), entries);
      return false;
    }
  }

  return {
    enable: function () { _enabled = true; },
    disable: function () { _enabled = false; },

    // Begin correlating every log() entry until endOp() is called. Returns
    // the generated op id (callers don't need it, but it's handy for tests).
    // receivedOpId (optional): a caller's own op id, propagated in as `parentOp`
    // on every entry -- this execution still mints its own fresh op either way.
    //
    // A nested startOp() call (e.g. syncAll() calling startOp() with no arg
    // from inside a doPost execution that already called
    // startOp(payload.opId)) must NOT wipe an already-established parentOp --
    // it falls back to the existing _parentOp rather than unconditionally
    // resetting to null (gts-obry.1: this reset was silently breaking
    // op/parentOp correlation for every webapp-driven syncAll() call --
    // sync.docNotFound.confirmed and friends were logged AFTER syncAll()'s own
    // startOp() ran, so they always carried parentOp=null regardless of the
    // caller's opId). A genuinely top-level entry point (e.g. syncAll() fired
    // directly by the 30-min trigger, no enclosing doPost) still gets
    // parentOp=null as before, since there is no existing _parentOp to fall
    // back to in that case.
    startOp: function (receivedOpId) {
      _currentOp = Utilities.getUuid();
      _parentOp = receivedOpId || _parentOp || null;
      return _currentOp;
    },

    endOp: function () { _currentOp = null; _parentOp = null; },

    // Lets a caller read its own current op id before issuing a UrlFetchApp
    // call into another execution, so it can pass it along as opId.
    getCurrentOp: function () { return _currentOp; },

    // Lets a caller read the op id IT was invoked under (its own parentOp),
    // as distinct from getCurrentOp() (the fresh op this execution minted for
    // itself). A multi-hop self-call chain (e.g. syncAll() -> _markDocNotFound()
    // UrlFetchApp-POSTing back into the WebApp) should propagate the ROOT
    // caller's opId onward so every hop's log entries correlate back to the
    // same originating call, not just the immediately-enclosing one --
    // callers making such a self-call should pass
    // `GasLogger.getParentOp() || GasLogger.getCurrentOp()` as the outgoing
    // opId (gts-obry.1): getParentOp() when this execution itself has an
    // established caller to chain to, falling back to getCurrentOp() only
    // when this execution IS the root (e.g. syncAll() fired directly by the
    // 30-min trigger, no enclosing doPost).
    getParentOp: function () { return _parentOp; },

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

    // Returns true if the flush's sink write succeeded (or there was nothing to
    // flush), false if the Axiom POST came back non-2xx / threw (gts-pfyx --
    // previously this was never surfaced to the caller at all).
    flush: function () {
      if (_entries.length === 0) return true;
      var axiom = _getAxiomConfig();
      var ok = true;
      if (axiom.token && axiom.dataset) {
        ok = _postToAxiom(_entries);
      } else {
        _writeToFile(_entries);
      }
      _entries = [];
      return ok;
    },

    // Cheap health check for a human or test harness: null if Axiom ingest is
    // (as far as we know) fine, else { ts, status, body, sampleTags } describing
    // the most recent ingest failure (gts-pfyx). Does not itself call Axiom.
    getAxiomHealth: function () {
      var raw = PropertiesService.getScriptProperties().getProperty(AXIOM_DEGRADED_PROP);
      if (!raw) return null;
      try {
        return JSON.parse(raw);
      } catch (err) {
        return { ts: null, status: 'unparseable', body: raw, sampleTags: [] };
      }
    },
  };
})();
