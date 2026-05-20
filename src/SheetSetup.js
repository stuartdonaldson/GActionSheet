/**
 * SheetSetup.js
 *
 * Creates or validates the "Actions" and "Archive" sheet tabs with the
 * required 9-column header row, bold/frozen row 1, and a basic filter.
 * Also resolves and persists the DOC_FOLDER_ID script property.
 */

/** Canonical ordered header columns (9). */
var SHEET_HEADERS = [
  'ID',
  'Assignee Email',
  'Assignee Name',
  'Action',
  'Status',
  'Document',
  'Date Created',
  'Date Modified',
  'Synced'
];

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
 * @param {Sheet} sheet
 */
function _ensureHeaders(sheet) {
  var headerRange = sheet.getRange(1, 1, 1, SHEET_HEADERS.length);
  var existing = headerRange.getValues()[0];

  var headersMatch = true;
  for (var i = 0; i < SHEET_HEADERS.length; i++) {
    if (existing[i] !== SHEET_HEADERS[i]) {
      headersMatch = false;
      break;
    }
  }

  if (!headersMatch) {
    headerRange.setValues([SHEET_HEADERS]);
    headerRange.setFontWeight('bold');
    sheet.setFrozenRows(1);
  }

  // Enable basic filter if not already present.
  if (!sheet.getFilter()) {
    var lastRow = Math.max(sheet.getLastRow(), 1);
    var lastCol = SHEET_HEADERS.length;
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
 * Creates or validates the "Actions" and "Archive" tabs with headers and
 * filtering. Idempotent — safe to run multiple times.
 */
function ensureSheetStructure() {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();

    var actionsSheet = _getOrCreateSheet(ss, 'Actions');
    var archiveSheet = _getOrCreateSheet(ss, 'Archive');
    _getOrCreateSheet(ss, 'TestControl');

    _ensureHeaders(actionsSheet);
    _ensureHeaders(archiveSheet);

    _resolveDocFolderId(ss);

    var actionsRows = Math.max(actionsSheet.getLastRow() - 1, 0); // exclude header
    var archiveRows = Math.max(archiveSheet.getLastRow() - 1, 0);

    GasLogger.log('sheet.structure.ensured', {
      actionsRows: actionsRows,
      archiveRows: archiveRows
    });
  } finally {
    GasLogger.flush();
  }
}
