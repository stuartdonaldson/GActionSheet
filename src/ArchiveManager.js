/**
 * ArchiveManager.js
 *
 * Moves eligible rows from the "Actions" sheet to the "Archive" sheet.
 *
 * Eligibility (DESIGN.md §Archive Manager):
 *   - Status column == "Closed"  (exact, case-sensitive match)
 *     Date Modified is more than 30 days before the current sync execution time
 *   - Sync Status column == "Doc Not Found"
 *     Date Modified is more than 24 hours before the current sync execution time
 *     (a doc the user deleted/lost access to has nothing further to converge on;
 *     it doesn't need the 30-day grace period a normal Closed row gets)
 *
 * Rows are processed bottom-to-top so that deleting a row does not shift
 * the indices of rows yet to be processed.
 *
 * All sheet writes are wrapped in WriteGuard to suppress the onEdit trigger.
 * Date Modified is NOT altered during archival.
 */
var ArchiveManager = (function () {

  var ARCHIVE_THRESHOLD_DAYS = 30;
  var DOC_NOT_FOUND_THRESHOLD_HOURS = 24;

  // Column refs resolved lazily inside archive() — ArchiveManager.js loads before
  // ContractSchema.js alphabetically, so CONTRACT_SCHEMA is not yet defined at IIFE time.

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

  /**
   * Returns true if the row is eligible for archival.
   *
   * @param {Array}  rowValues  Raw cell-value array (0-based columns).
   * @param {Date}   now        Sync execution time.
   * @returns {boolean}
   */
  function _isEligible(rowValues, now, colStatus, colSyncStatus, colModified) {
    var status     = rowValues[colStatus    - 1];
    var syncStatus = rowValues[colSyncStatus - 1];
    if (status !== 'Closed' && syncStatus !== 'Doc Not Found') return false;

    var dateModified = _toDate(rowValues[colModified - 1]);
    if (!dateModified) return false;

    var ageHours = (now.getTime() - dateModified.getTime()) / (1000 * 60 * 60);

    if (syncStatus === 'Doc Not Found') return ageHours > DOC_NOT_FOUND_THRESHOLD_HOURS;
    return ageHours > ARCHIVE_THRESHOLD_DAYS * 24;
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  return {
    /**
     * Archives eligible rows from the "Actions" sheet to the "Archive" sheet.
     *
     * @param {Spreadsheet} ss  The active spreadsheet object.
     * @returns {number}  Count of rows archived.
     */
    archive: function (ss) {
      // Resolve column positions here (CONTRACT_SCHEMA available by the time this runs).
      var _AC        = CONTRACT_SCHEMA.sheetAction.columnsByField;
      var COL_STATUS        = _AC.status;
      var COL_DATE_MODIFIED = _AC.modified_date;
      var COL_SYNC_STATUS   = _AC.sync_status;
      var TOTAL_COLS        = SHEET_HEADERS.length;

      var actionsSheet = ss.getSheetByName('Actions');
      if (!actionsSheet) {
        throw new Error('Actions sheet tab not found.');
      }

      var archiveSheet = ss.getSheetByName('Archive');
      if (!archiveSheet) {
        throw new Error('Archive sheet tab not found.');
      }

      var now = new Date();
      var lastRow = actionsSheet.getLastRow();
      var count = 0;

      if (lastRow < 2) {
        GasLogger.log('archive.complete', { count: 0 });
        return 0;
      }

      var numDataRows = lastRow - 1;
      var dataRange   = actionsSheet.getRange(2, 1, numDataRows, TOTAL_COLS);
      var allValues   = dataRange.getValues();
      var allFormulas = dataRange.getFormulas();

      // Iterate bottom-to-top to keep row indices stable during deletion.
      for (var r = numDataRows - 1; r >= 0; r--) {
        var rowValues   = allValues[r];
        var rowFormulas = allFormulas[r];

        if (!_isEligible(rowValues, now, COL_STATUS, COL_SYNC_STATUS, COL_DATE_MODIFIED)) continue;

        var sheetRow = r + 2;  // 1-based; row 1 is the header

        // Build rowData: use formula string where one exists so that column 7's
        // HYPERLINK is preserved in Archive (getValues() would lose it to display text).
        // appendRow() treats strings starting with '=' as formulas.
        var rowData = rowValues.map(function(val, i) {
          return rowFormulas[i] ? rowFormulas[i] : val;
        });

        var originalDateModified = rowValues[COL_DATE_MODIFIED - 1];
        WriteGuard.wrap(function () {
          archiveSheet.appendRow(rowData);
          actionsSheet.deleteRow(sheetRow);
        });

        GasLogger.log('archive.moved', {
          id: rowValues[0],
          originalDateModified: originalDateModified instanceof Date
            ? originalDateModified.toISOString()
            : String(originalDateModified)
        });
        count++;
      }

      GasLogger.log('archive.complete', { count: count });
      return count;
    }
  };
})();
