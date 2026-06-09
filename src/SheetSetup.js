/**
 * SheetSetup.js
 *
 * Creates or validates the "Actions", "Archive", "TeamData", and "DocData"
 * sheet tabs with the required header row, bold/frozen row 1, and a basic
 * filter.  Also resolves and persists the DOC_FOLDER_ID script property.
 */

// Column positions (1-based) are defined in ContractSchema.js.

/**
 * Returns the sheet with the given name, creating it if it does not exist.
 *
 * @param {Spreadsheet} ss
 * @param {string} name
 * @returns {Sheet}
 */
function _getOrCreateSheet(ss, name) {
  var sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
  }
  return sheet;
}

/**
 * Writes the canonical headers to row 1 of the given sheet, makes the row
 * bold, freezes it, and enables a basic filter on the data range.
 * If row 1 already contains the correct headers this function is a no-op for
 * that sheet.
 *
 * @param {Sheet}    sheet
 * @param {string[]} headers  Expected header values in column order.
 */
function _ensureHeaders(sheet, headers) {
  var headerRange = sheet.getRange(1, 1, 1, headers.length);
  var existing = headerRange.getValues()[0];

  var headersMatch = true;
  for (var i = 0; i < headers.length; i++) {
    if (existing[i] !== headers[i]) {
      headersMatch = false;
      break;
    }
  }

  if (!headersMatch) {
    headerRange.setValues([headers]);
    headerRange.setFontWeight('bold');
    sheet.setFrozenRows(1);
  }

  // Enable basic filter if not already present.
  if (!sheet.getFilter()) {
    var lastRow = Math.max(sheet.getLastRow(), 1);
    var lastCol = headers.length;
    sheet.getRange(1, 1, lastRow, lastCol).createFilter();
  }
}

/**
 * Resolves DOC_FOLDER_ID: reads the script property; if absent, derives it
 * from the parent folder of the active spreadsheet and persists the result.
 *
 * @param {Spreadsheet} ss
 * @returns {string} The resolved folder ID.
 */
function _resolveDocFolderId(ss) {
  var props = PropertiesService.getScriptProperties();
  var folderId = props.getProperty('DOC_FOLDER_ID');
  if (folderId) {
    return folderId;
  }

  var file = DriveApp.getFileById(ss.getId());
  var iter = file.getParents();
  folderId = iter.hasNext() ? iter.next().getId() : DriveApp.getRootFolder().getId();

  props.setProperty('DOC_FOLDER_ID', folderId);
  return folderId;
}

/**
 * Creates or validates the "Actions", "Archive", "TeamData", and "DocData"
 * tabs with headers and filtering. Idempotent — safe to run multiple times.
 */
function ensureSheetStructure() {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();

    var actionsSheet  = _getOrCreateSheet(ss, 'Actions');
    var archiveSheet  = _getOrCreateSheet(ss, 'Archive');
    var teamDataSheet = _getOrCreateSheet(ss, 'TeamData');
    var docDataSheet  = _getOrCreateSheet(ss, 'DocData');
    _getOrCreateSheet(ss, 'TestControl');

    var actionHeaders   = CONTRACT_SCHEMA.sheetAction.headers.slice();
    var teamDataHeaders = CONTRACT_SCHEMA.sheetTeamData.headers.slice();
    var docDataHeaders  = CONTRACT_SCHEMA.sheetDocData.headers.slice();

    _ensureHeaders(actionsSheet,  actionHeaders);
    _ensureHeaders(archiveSheet,  actionHeaders);
    _ensureHeaders(teamDataSheet, teamDataHeaders);
    _ensureHeaders(docDataSheet,  docDataHeaders);

    _resolveDocFolderId(ss);

    var actionsRows  = Math.max(actionsSheet.getLastRow()  - 1, 0);
    var archiveRows  = Math.max(archiveSheet.getLastRow()  - 1, 0);
    var teamDataRows = Math.max(teamDataSheet.getLastRow() - 1, 0);
    var docDataRows  = Math.max(docDataSheet.getLastRow()  - 1, 0);

    GasLogger.log('sheet.structure.ensured', {
      actionsRows:  actionsRows,
      archiveRows:  archiveRows,
      teamDataRows: teamDataRows,
      docDataRows:  docDataRows
    });
  } finally {
    GasLogger.flush();
  }
}

/**
 * One-time migration: removes the "Synced" column from "Actions" and "Archive"
 * tabs if present.  Idempotent — safe to run more than once.
 */
function migrateRemoveSyncedColumn() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var tabs = ['Actions', 'Archive'];
  for (var t = 0; t < tabs.length; t++) {
    var tabName = tabs[t];
    var sheet = ss.getSheetByName(tabName);
    if (!sheet) {
      GasLogger.log('migrate.remove-synced', { data: { tab: tabName, status: 'not-found' } });
      continue;
    }
    var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    var colIndex = -1;
    for (var c = 0; c < headers.length; c++) {
      if (headers[c] === 'Synced') {
        colIndex = c + 1; // convert to 1-based
        break;
      }
    }
    if (colIndex > 0) {
      sheet.deleteColumns(colIndex, 1);
      GasLogger.log('migrate.remove-synced', { data: { tab: tabName, col: colIndex } });
    } else {
      GasLogger.log('migrate.remove-synced', { data: { tab: tabName, status: 'not-found' } });
    }
  }
  GasLogger.flush();
}
