/**
 * ArchiveManager.js
 *
 * Moves eligible rows from the "Actions" sheet to the "Archive" sheet.
 *
 * Eligibility (requirements §13 / §16):
 *   - Status column == "Closed"  (exact, case-sensitive match)
 *   - Date Modified is more than 30 days before the current sync execution time
 *
 * Rows are processed bottom-to-top so that deleting a row does not shift
 * the indices of rows yet to be processed.
 *
 * All sheet writes are wrapped in WriteGuard to suppress the onEdit trigger
 * (requirements §16.3).  Date Modified is NOT altered during archival (§16.2).
 */
var ArchiveManager = (function () {

  var ARCHIVE_THRESHOLD_DAYS = 30;

  // 1-based column indices (matching SHEET_HEADERS with NamedRangeId as col 1).
  var COL_STATUS        = 6;
  var COL_DATE_MODIFIED = 9;
  var TOTAL_COLS        = 10;

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
  function _isEligible(rowValues, now) {
    var status = rowValues[COL_STATUS - 1];
    if (status !== 'Closed') return false;

    var dateModified = _toDate(rowValues[COL_DATE_MODIFIED - 1]);
    if (!dateModified) return false;

    var ageDays = (now.getTime() - dateModified.getTime()) / (1000 * 60 * 60 * 24);
    return ageDays > ARCHIVE_THRESHOLD_DAYS;
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
      var allValues = actionsSheet.getRange(2, 1, numDataRows, TOTAL_COLS).getValues();

      // Iterate bottom-to-top to keep row indices stable during deletion.
      for (var r = numDataRows - 1; r >= 0; r--) {
        var rowValues = allValues[r];

        if (!_isEligible(rowValues, now)) continue;

        var sheetRow = r + 2;  // 1-based; row 1 is the header

        var originalDateModified = rowValues[COL_DATE_MODIFIED - 1];
        WriteGuard.wrap(function () {
          // Append a copy of the row to Archive (preserves all values including
          // Date Modified without alteration).
          archiveSheet.appendRow(rowValues);

          // Remove from Actions.
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
