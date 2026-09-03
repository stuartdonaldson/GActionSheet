/**
 * ActionSnapshot.js
 *
 * gts-5kyu Stage 1: per-execution memo of the Actions sheet.
 *
 * AC0 instrumentation lives here first (a bare read-counter, no caching
 * behavior yet) so the baseline can be measured BEFORE any snapshot/caching
 * code exists. _actionsReadCount is module-level state, which is safe: each
 * Apps Script execution gets its own fresh global scope, so this never
 * leaks between executions (same reasoning GasLogger.js documents for its
 * own op-correlation state).
 */
var _actionsReadCount = { getValues: 0, getFormulas: 0 };

/**
 * Counts one Sheets round trip charged to the Actions sheet in this
 * execution. Call immediately after issuing the real getValues()/
 * getFormulas() call it is charging for.
 *
 * @param {string} kind  'getValues' | 'getFormulas'
 */
function _countActionsRead(kind) {
  _actionsReadCount[kind] = (_actionsReadCount[kind] || 0) + 1;
}

/** Total Actions-sheet Sheets round trips charged so far in this execution. */
function _actionsReadTotal() {
  return (_actionsReadCount.getValues || 0) + (_actionsReadCount.getFormulas || 0);
}

// ---------------------------------------------------------------------------
// gts-5kyu Stage 1: the snapshot itself.
//
// AC0's baseline (recorded on the bead) showed the win is concentrated in
// the doc-scoped repeated-read case (N insertTrackerTable() calls inside one
// execution paying 2 Actions-sheet round trips EACH); syncAll's own sheet
// scan and a single sidebar status-set were already O(1). This module exists
// to collapse the former without touching the latter.
//
// Every reader routed through _actionsSnapshot(ss) keeps its OWN per-row
// extraction/filter code completely unchanged -- only the two lines that
// used to call sheet.getRange(...).getValues()/.getFormulas() directly are
// swapped for snap.data / snap.formulas. This is deliberate: AC3 requires
// byte-identical output, and the safest way to guarantee that is to change
// WHERE the two arrays come from, never HOW a reader turns them into its
// result. The snapshot itself carries no doc/globalId index -- that would
// require re-deriving (and risk subtly changing) each reader's own matching
// semantics, some of which differ (TrackerTable's plain substring
// formula.indexOf(docId) vs. WebApp's _extractDocIdFromString(...) equality
// match -- see gts-5kyu description "WHY doc_id NEEDS AN INDEX...").
// ---------------------------------------------------------------------------
var _actionsSnapshotCache = null;
var _actionsSnapshotExecIdVal = null;

function _actionsSnapshotExecId() {
  if (!_actionsSnapshotExecIdVal) _actionsSnapshotExecIdVal = Utilities.getUuid();
  return _actionsSnapshotExecIdVal;
}

/**
 * Per-execution memo of the Actions sheet's two Sheets round trips
 * (getValues() over every column, getFormulas() over the document_formula
 * column only -- the same two reads every routed reader already made).
 * Built at most once per execution; every subsequent call in the same
 * execution returns the cached object with zero additional Sheets I/O.
 *
 * Logging contract (shared with the twin [TST] bead, gts-hztp -- do not
 * change without updating both sides): tag 'actioncache.build' on a real
 * build, 'actioncache.reuse' on a memo hit, each carrying
 * { execId, reads, rows, docs }. `reads` is _actionsReadTotal() -- the
 * oracle for AC1/AC2, not wall time.
 *
 * Failure posture: a throw while reading the sheet is caught here and never
 * reaches the caller. Returns null on failure so the caller can fall back to
 * its own original inline read (every routed reader keeps that fallback).
 *
 * @param {Spreadsheet} ss
 * @returns {?{gen:string, numRows:number, data:?Array, formulas:?Array, docCount:number}}
 */
function _actionsSnapshot(ss) {
  try {
    if (_actionsSnapshotCache) {
      GasLogger.log('actioncache.reuse', {
        execId: _actionsSnapshotExecId(),
        reads:  _actionsReadTotal(),
        rows:   _actionsSnapshotCache.numRows,
        docs:   _actionsSnapshotCache.docCount
      });
      return _actionsSnapshotCache;
    }

    var sheet   = ss.getSheetByName('Actions');
    var lastRow = sheet ? sheet.getLastRow() : 0;
    var numRows = lastRow >= 2 ? lastRow - 1 : 0;
    var data     = null;
    var formulas = null;
    var docCount = 0;

    if (numRows > 0) {
      var _AC = CONTRACT_SCHEMA.sheetAction.columnsByField;
      data = sheet.getRange(2, 1, numRows, SHEET_HEADERS.length).getValues();
      _countActionsRead('getValues');
      formulas = sheet.getRange(2, _AC.document_formula, numRows, 1).getFormulas();
      _countActionsRead('getFormulas');

      var docSet = {};
      for (var i = 0; i < formulas.length; i++) {
        var docId = _extractDocIdFromString(formulas[i][0] || '');
        if (docId) docSet[docId] = true;
      }
      docCount = Object.keys(docSet).length;
    }

    _actionsSnapshotCache = {
      gen:      Utilities.getUuid(),
      numRows:  numRows,
      data:     data,
      formulas: formulas,
      docCount: docCount
    };

    GasLogger.log('actioncache.build', {
      execId: _actionsSnapshotExecId(),
      reads:  _actionsReadTotal(),
      rows:   numRows,
      docs:   docCount
    });

    return _actionsSnapshotCache;
  } catch (err) {
    GasLogger.log('actioncache.error', { msg: String(err && err.message || err) });
    return null;
  }
}

/**
 * Nulls the memo. Every writer that mutates the Actions sheet must call this
 * immediately after its write commits (AC9) -- a snapshot rebuilt on next
 * demand costs one round trip; a stale one risks a wrong read (AC1's build/
 * reuse counting still holds: invalidation just means the NEXT
 * _actionsSnapshot() call is a build, not a reuse).
 *
 * Hooked centrally into WriteGuard.wrap()/wrapPersistent() (src/WriteGuard.js)
 * -- the choke point every production Actions-sheet write already goes
 * through -- rather than scattered at each individual writer, so a future
 * writer gets this for free and none can be missed. Over-invalidation (e.g.
 * a WriteGuard.wrap() around a write to some OTHER sheet also nulling this
 * memo) is harmless -- one extra rebuilt read, never a wrong answer.
 */
function _invalidateActionsSnapshot() {
  _actionsSnapshotCache = null;
}
