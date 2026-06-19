/**
 * ArchiveManager.js
 *
 * Moves eligible rows from the "Actions" sheet to the "Archive" sheet, and
 * evicts "DocData" rows once their docId has gone Doc Not Found long enough
 * that nothing is still converging on it (GTaskSheet-4tnr).
 *
 * Eligibility (DESIGN.md §Archive Manager):
 *   - Actions row: Status == "Closed" (exact, case-sensitive match) and
 *     Date Modified is more than 30 days before the current sync execution time
 *   - Actions row: Sync Status == "Doc Not Found" and Date Modified is more
 *     than 24 hours before the current sync execution time
 *     (a doc the user deleted/lost access to has nothing further to converge
 *     on; it doesn't need the 30-day grace period a normal Closed row gets)
 *   - DocData row: SyncStatus == "Doc Not Found" and no Actions row still
 *     references that docId. A "Doc Not Found" docId can only lose all its
 *     Actions rows via the 24h-gated sweep above (or explicit deletion), so
 *     this is already a 24h-gated signal -- DocData doesn't need its own
 *     independent aging clock to stay in step with Actions.
 *
 * Actions/DocData rows are partitioned into keep/evict in one pass over a
 * single bulk read, then written back with at most two range writes per
 * sheet (no per-row appendRow/deleteRow). The whole read-modify-write is
 * wrapped in a script lock scoped to this function only, so a concurrent
 * doPost write (e.g. _handleMarkDocNotFound) can't be clobbered by the
 * archive sweep's write-back, and the lock isn't held across the rest of a
 * sync run.
 *
 * All sheet writes are wrapped in WriteGuard to suppress the onEdit trigger.
 * Date Modified is NOT altered during archival.
 */
var ArchiveManager = (function () {

  var ARCHIVE_THRESHOLD_DAYS        = 30;
  var DOC_NOT_FOUND_THRESHOLD_HOURS = 24;
  var LOCK_TIMEOUT_MS                = 30000;

  // Column refs resolved lazily inside the functions below — ArchiveManager.js
  // loads before ContractSchema.js alphabetically, so CONTRACT_SCHEMA is not
  // yet defined at IIFE time.

  /**
   * Converts a value to a Date, or returns null.
   *
   * @param {*} v
   * @returns {Date|null}
   */
  function _toDate(v) {
    if (!v) return null;
    if (v instanceof Date) return v;
    var d = new Date(v);
    return isNaN(d.getTime()) ? null : d;
  }

  function _ageHours(date, now) {
    return (now.getTime() - date.getTime()) / (1000 * 60 * 60);
  }

  /**
   * Shared aging predicate for both Actions rows and DocData rows: a row
   * whose syncStatus is "Doc Not Found" expires after
   * DOC_NOT_FOUND_THRESHOLD_HOURS; an Actions row whose status is "Closed"
   * expires after ARCHIVE_THRESHOLD_DAYS. Pass status as null/undefined for
   * DocData rows, which have no "Closed" concept.
   *
   * @param {string}  syncStatus
   * @param {?string} status
   * @param {*}       dateValue  Raw cell value for the row's aging timestamp.
   * @param {Date}    now
   * @returns {boolean}
   */
  function _isExpired(syncStatus, status, dateValue, now) {
    var date = _toDate(dateValue);
    if (!date) return false;
    if (syncStatus === 'Doc Not Found') return _ageHours(date, now) > DOC_NOT_FOUND_THRESHOLD_HOURS;
    if (status === 'Closed') return _ageHours(date, now) > ARCHIVE_THRESHOLD_DAYS * 24;
    return false;
  }

  /**
   * Partitions Actions rows into keep/archive from one bulk read, then writes
   * both sheets back in at most two range writes total.
   *
   * @param {Spreadsheet} ss
   * @param {Date}        now
   * @returns {number}  Count of rows archived.
   */
  function _archiveActionsRows(ss, now) {
    var _AC                = CONTRACT_SCHEMA.sheetAction.columnsByField;
    var COL_STATUS         = _AC.status;
    var COL_DATE_MODIFIED  = _AC.modified_date;
    var COL_SYNC_STATUS    = _AC.sync_status;
    var TOTAL_COLS         = SHEET_HEADERS.length;

    var actionsSheet = ss.getSheetByName('Actions');
    if (!actionsSheet) throw new Error('Actions sheet tab not found.');
    var archiveSheet = ss.getSheetByName('Archive');
    if (!archiveSheet) throw new Error('Archive sheet tab not found.');

    var lastRow = actionsSheet.getLastRow();
    if (lastRow < 2) return 0;

    var numDataRows = lastRow - 1;
    var dataRange    = actionsSheet.getRange(2, 1, numDataRows, TOTAL_COLS);
    var allValues    = dataRange.getValues();
    var allFormulas  = dataRange.getFormulas();

    var keepRows    = [];
    var archiveRows = [];

    for (var r = 0; r < numDataRows; r++) {
      var rowValues    = allValues[r];
      var rowFormulas  = allFormulas[r];
      var status       = rowValues[COL_STATUS        - 1];
      var syncStatus   = rowValues[COL_SYNC_STATUS    - 1];
      var dateModified = rowValues[COL_DATE_MODIFIED  - 1];

      // Build rowData: use formula string where one exists so that column 7's
      // HYPERLINK is preserved (getValues() would lose it to display text).
      // setValues() treats strings starting with '=' as formulas, same as appendRow().
      var rowData = rowValues.map(function (val, i) { return rowFormulas[i] ? rowFormulas[i] : val; });

      if (_isExpired(syncStatus, status, dateModified, now)) {
        archiveRows.push(rowData);
        GasLogger.log('archive.moved', {
          id: rowValues[0],
          originalDateModified: dateModified instanceof Date
            ? dateModified.toISOString()
            : String(dateModified)
        });
      } else {
        keepRows.push(rowData);
      }
    }

    if (archiveRows.length === 0) return 0;

    WriteGuard.wrap(function () {
      archiveSheet.getRange(archiveSheet.getLastRow() + 1, 1, archiveRows.length, TOTAL_COLS).setValues(archiveRows);
      actionsSheet.getRange(2, 1, numDataRows, TOTAL_COLS).clearContent();
      if (keepRows.length > 0) {
        actionsSheet.getRange(2, 1, keepRows.length, TOTAL_COLS).setValues(keepRows);
      }
    });

    return archiveRows.length;
  }

  /**
   * Returns the set of docIds still referenced by any row in the Actions
   * sheet, keyed by docId with value true. Reuses _extractDocIdFromString
   * (WebApp.js) -- same HYPERLINK-formula docId extraction already used by
   * syncAll's docId enumeration -- rather than re-deriving the regex here.
   *
   * @param {Spreadsheet} ss
   * @returns {Object<string, boolean>}
   */
  function _collectActiveDocIds(ss) {
    var actionsSheet = ss.getSheetByName('Actions');
    if (!actionsSheet) return {};
    var lastRow = actionsSheet.getLastRow();
    if (lastRow < 2) return {};

    var colFormula = CONTRACT_SCHEMA.sheetAction.columnsByField.document_formula;
    var formulas   = actionsSheet.getRange(2, colFormula, lastRow - 1, 1).getFormulas();
    var docIds     = {};
    for (var i = 0; i < formulas.length; i++) {
      var docId = _extractDocIdFromString(formulas[i][0] || '');
      if (docId) docIds[docId] = true;
    }
    return docIds;
  }

  /**
   * Evicts DocData rows marked "Doc Not Found" once no Actions row still
   * references that docId. A docId's Actions rows can only disappear via
   * _archiveActionsRows' 24h-gated sweep above (or explicit test/admin
   * deletion) -- never on a faster clock -- so "no remaining Actions rows"
   * is the correct, already-24h-gated signal for DocData eviction, without
   * DocData needing its own independent aging clock.
   *
   * @param {Spreadsheet} ss
   * @returns {number}  Count of DocData rows evicted.
   */
  function _evictStaleDocData(ss) {
    var sheet = ss.getSheetByName('DocData');
    if (!sheet) return 0;
    var lastRow = sheet.getLastRow();
    if (lastRow < 2) return 0;

    var cols          = CONTRACT_SCHEMA.sheetDocData.columnsByField;
    var numCols        = CONTRACT_SCHEMA.sheetDocData.headers.length;
    var values         = sheet.getRange(2, 1, lastRow - 1, numCols).getValues();
    var activeDocIds   = _collectActiveDocIds(ss);

    var keepRows = [];
    var evicted  = 0;

    for (var r = 0; r < values.length; r++) {
      var row        = values[r];
      var fileId     = row[cols.file_id - 1];
      var syncStatus = row[cols.sync_status - 1];

      if (syncStatus === 'Doc Not Found' && !activeDocIds[fileId]) {
        GasLogger.log('archive.docdata_evicted', { fileId: fileId });
        evicted++;
      } else {
        keepRows.push(row);
      }
    }

    if (evicted === 0) return 0;

    WriteGuard.wrap(function () {
      sheet.getRange(2, 1, values.length, numCols).clearContent();
      if (keepRows.length > 0) {
        sheet.getRange(2, 1, keepRows.length, numCols).setValues(keepRows);
      }
    });

    return evicted;
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  return {
    /**
     * Archives eligible rows from the "Actions" sheet to the "Archive" sheet,
     * then evicts DocData rows whose docId no longer has any Actions row
     * (only possible for "Doc Not Found" docIds, since that's the only
     * status this function removes from Actions entirely). The read-modify-
     * write is wrapped in a script lock scoped to this call only.
     *
     * @param {Spreadsheet} ss  The active spreadsheet object.
     * @returns {number}  Count of Actions rows archived.
     */
    archive: function (ss) {
      var now = new Date();
      var lock = LockService.getScriptLock();
      var actionsArchived, docDataEvicted;

      lock.waitLock(LOCK_TIMEOUT_MS);
      try {
        actionsArchived = _archiveActionsRows(ss, now);
        docDataEvicted  = _evictStaleDocData(ss);
      } finally {
        lock.releaseLock();
      }

      GasLogger.log('archive.complete', { count: actionsArchived, docDataEvicted: docDataEvicted });
      return actionsArchived;
    }
  };
})();
