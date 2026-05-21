/**
 * SheetReconciler.js
 *
 * Writes and updates action rows in the "Actions" sheet tab.
 *
 * Match key: (Document URL, ID) — requirements §11.1 / §3.1.
 *
 * New-row path  (§11.2): if no row exists for the (docUrl, id) pair, append one.
 * Update path   (§11.4–7): if a row already exists, compare dateModified values
 *   and apply the timestamp-wins rule.  Tie → sheet wins (§11.7).
 *
 * Column order follows SHEET_HEADERS (defined in SheetSetup.js):
 *   ID | Assignee Email | Assignee Name | Action | Status | Document |
 *   Date Created | Date Modified
 *
 * Returns an IIFE exposing { reconcile }.
 *
 * reconcile() returns an object:
 *   { written: number, sheetWins: object[] }
 *
 *   sheetWins is an array of action objects updated with sheet values.
 *   The caller (SyncOrchestrator) must pass these back to DocumentNormalizer
 *   to rewrite the doc.
 */
var SheetReconciler = (function () {

  // 1-based column indices matching SHEET_HEADERS.
  var COL_ID            = 1;
  var COL_ASSIGNEE_EMAIL = 2;
  var COL_ASSIGNEE_NAME  = 3;
  var COL_ACTION        = 4;
  var COL_STATUS        = 5;
  var COL_DOCUMENT      = 6;
  var COL_DATE_CREATED  = 7;
  var COL_DATE_MODIFIED = 8;
  var TOTAL_COLS        = 8;

  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  /**
   * Extracts the URL from a HYPERLINK formula or returns the raw string.
   *
   * @param {*} cellValue
   * @returns {string}
   */
  function _extractUrl(cellValue) {
    if (typeof cellValue !== 'string') return '';
    var hm = /^=HYPERLINK\("([^"]+)"/.exec(cellValue);
    return hm ? hm[1] : cellValue;
  }

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
   * Reads all data rows from the sheet and returns:
   *   - keySet:  { key → rowIndex (1-based, data starts at row 2) }
   *   - rowData: array of row value arrays (0-indexed, first element = row 2)
   *
   * @param {Sheet} sheet
   * @returns {{ keySet: Object, rowData: Array }}
   */
  function _readSheet(sheet) {
    var lastRow = sheet.getLastRow();
    var keySet = {};
    var rowData = [];

    if (lastRow < 2) return { keySet: keySet, rowData: rowData };

    var numDataRows = lastRow - 1;
    var dataRange = sheet.getRange(2, 1, numDataRows, TOTAL_COLS);
    var values   = dataRange.getValues();
    // Also read formulas so =HYPERLINK("url","text") cells expose the URL.
    var formulas = dataRange.getFormulas();

    for (var r = 0; r < numDataRows; r++) {
      var rowId = values[r][COL_ID - 1];
      // Prefer the formula string (may be =HYPERLINK(...)) over the computed value.
      var docCell = formulas[r][COL_DOCUMENT - 1] || values[r][COL_DOCUMENT - 1];
      var docUrl  = _extractUrl(docCell);

      rowData.push(values[r]);

      if (rowId !== '' && rowId !== null && rowId !== undefined) {
        var key = docUrl + '||' + String(rowId);
        keySet[key] = r;  // 0-based index into rowData
      }
    }

    return { keySet: keySet, rowData: rowData };
  }

  /**
   * Builds the 8-element row array for a single action.
   *
   * @param {object} action   Normalized action object.
   * @returns {Array}
   */
  function _buildRow(action) {
    var hyperlinkFormula = '=HYPERLINK("' + action.docUrl + '","' + action.docTitle.replace(/"/g, '\\"') + '")';
    return [
      action.id,
      action.assigneeEmail  || '',
      action.assigneeName   || '',
      action.action         || '',
      action.status         || '',
      hyperlinkFormula,
      action.dateCreated    || '',
      action.dateModified   || ''
    ];
  }

  /**
   * Writes an updated row back to the sheet for the doc-wins case.
   * Columns updated: Action, Status, Date Modified.
   * Wrapped in WriteGuard to suppress the onEdit trigger.
   *
   * @param {Sheet}  sheet
   * @param {number} sheetRow  1-based row number.
   * @param {object} action
   */
  function _applyDocWins(sheet, sheetRow, action) {
    WriteGuard.wrap(function () {
      sheet.getRange(sheetRow, COL_ACTION).setValue(action.action || '');
      sheet.getRange(sheetRow, COL_STATUS).setValue(action.status || '');
      sheet.getRange(sheetRow, COL_DATE_MODIFIED).setValue(action.dateModified || '');
    });
  }

  /**
   * Builds an updated action object from the sheet row values (sheet-wins case).
   *
   * @param {object} action    Original action from the doc.
   * @param {Array}  sheetRow  Raw row value array (0-based columns).
   * @returns {object}  Action updated with sheet values.
   */
  function _buildSheetWinsAction(action, sheetRow) {
    return {
      id:            action.id,
      docUrl:        action.docUrl,
      docTitle:      action.docTitle,
      assigneeEmail: sheetRow[COL_ASSIGNEE_EMAIL - 1] || action.assigneeEmail,
      assigneeName:  sheetRow[COL_ASSIGNEE_NAME  - 1] || action.assigneeName,
      action:        sheetRow[COL_ACTION         - 1] || action.action,
      status:        sheetRow[COL_STATUS         - 1] || action.status,
      dateCreated:   sheetRow[COL_DATE_CREATED   - 1] || action.dateCreated,
      dateModified:  sheetRow[COL_DATE_MODIFIED  - 1] || action.dateModified
    };
  }

  /**
   * Validates that the "Actions" sheet has the required header columns.
   * Throws a SyncError with kind 'missing-header' if any are absent.
   * This must be called before any document processing begins so that a
   * missing sheet header aborts the entire sync run without partial writes.
   *
   * @param {Sheet} sheet  The "Actions" sheet tab.
   */
  function _validateSheetHeaders(sheet) {
    var lastCol = sheet.getLastColumn();
    if (lastCol < 1) {
      var err = new Error('Actions sheet has no headers.');
      err.syncErrorKind = 'missing-header';
      err.syncErrorData = { kind: 'missing-header', where: 'Actions-sheet', missing: SHEET_HEADERS };
      throw err;
    }
    var headerValues = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
    var headerMap = {};
    for (var c = 0; c < headerValues.length; c++) {
      if (headerValues[c] !== '') headerMap[String(headerValues[c]).trim()] = c;
    }
    var missing = [];
    for (var h = 0; h < SHEET_HEADERS.length; h++) {
      if (!(SHEET_HEADERS[h] in headerMap)) missing.push(SHEET_HEADERS[h]);
    }
    if (missing.length > 0) {
      var err2 = new Error('Actions sheet is missing required header(s): ' + missing.join(', '));
      err2.syncErrorKind = 'missing-header';
      err2.syncErrorData = { kind: 'missing-header', where: 'Actions-sheet', missing: missing };
      throw err2;
    }
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  return {
    /**
     * Validates the "Actions" sheet headers before any document processing.
     * Call this at the very start of a sync run (before normalize) so that a
     * missing sheet header aborts the entire run without partial doc writes.
     *
     * Throws a SyncError with kind 'missing-header' if validation fails.
     *
     * @param {string} sheetId  Spreadsheet ID.
     */
    validateSheetHeaders: function (sheetId) {
      var ss = SpreadsheetApp.openById(sheetId);
      var sheet = ss.getSheetByName('Actions');
      if (!sheet) {
        var err = new Error('Actions sheet tab not found in spreadsheet ' + sheetId);
        err.syncErrorKind = 'missing-header';
        err.syncErrorData = {
          kind: 'missing-header',
          where: 'Actions-sheet',
          missing: SHEET_HEADERS
        };
        throw err;
      }
      _validateSheetHeaders(sheet);
    },

    /**
     * Reconciles normalized document actions against the "Actions" sheet tab.
     *
     * New rows are appended.  Existing rows are updated per the timestamp-wins
     * rule (§11.4–7).  All sheet writes are wrapped in WriteGuard.
     *
     * @param {object[]} actions  Normalized action objects from DocumentNormalizer.
     * @param {string}   sheetId  Spreadsheet ID.
     * @returns {{ written: number, sheetWins: object[], docWins: number }}
     *   written    — count of new rows appended + existing rows updated from doc
     *   sheetWins  — actions updated with sheet values (caller rewrites the doc)
     *   docWins    — count of existing rows updated because the doc had a newer timestamp
     */
    reconcile: function (actions, sheetId) {
      if (!actions || actions.length === 0) return { written: 0, sheetWins: [], docWins: 0 };

      var ss = SpreadsheetApp.openById(sheetId);
      var sheet = ss.getSheetByName('Actions');
      if (!sheet) {
        throw new Error('Actions sheet tab not found in spreadsheet ' + sheetId);
      }

      var data = _readSheet(sheet);
      var keySet  = data.keySet;
      var rowData = data.rowData;

      var written   = 0;
      var docWins   = 0;
      var sheetWins = [];

      for (var i = 0; i < actions.length; i++) {
        var action = actions[i];
        var key = (action.docUrl || '') + '||' + String(action.id);

        if (!(key in keySet)) {
          // ── New row ──────────────────────────────────────────────────────
          var row = _buildRow(action);
          WriteGuard.wrap(function () { sheet.appendRow(row); });
          keySet[key] = rowData.length;  // prevent duplicates within this call
          rowData.push(row);
          written++;
        } else {
          // ── Existing row — compare dateModified ─────────────────────────
          var dataRowIdx  = keySet[key];
          var sheetRowArr = rowData[dataRowIdx];
          var sheetRowNum = dataRowIdx + 2;  // 1-based; row 1 is header

          var docDate   = _toDate(action.dateModified);
          var sheetDate = _toDate(sheetRowArr[COL_DATE_MODIFIED - 1]);

          // Doc wins when it has a strictly later dateModified.
          if (docDate && sheetDate && docDate.getTime() > sheetDate.getTime()) {
            _applyDocWins(sheet, sheetRowNum, action);
            GasLogger.log('reconcile.doc.wins', { id: action.id, docId: action.docUrl });
            written++;
            docWins++;
          } else {
            // Sheet wins: equal timestamps (§11.7), sheet newer, or either null.
            var updatedAction = _buildSheetWinsAction(action, sheetRowArr);

            GasLogger.log('reconcile.sheet.wins', { id: action.id, docId: action.docUrl });
            sheetWins.push(updatedAction);
          }
        }
      }

      return { written: written, sheetWins: sheetWins, docWins: docWins };
    }
  };
})();
