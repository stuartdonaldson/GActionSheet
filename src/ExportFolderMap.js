/**
 * ExportFolderMap.js — gts-z6j0
 *
 * Keeps governance-exporter output (JSON export, PDF snapshot, and future
 * image-extraction/docx-cache artifacts, gts-283i epic) out of the source
 * document's own folder. Previously Procedure-Exporter.js's
 * getSourceFolder_() wrote export output directly into the source doc's
 * parent folder -- visible to every user with access to that folder
 * alongside the real document.
 *
 * Design: a single well-known Script Property EXPORT_ROOT_FOLDER_ID (set via
 * the set_export_config WebApp route -- see WebApp.js -- pushed at deploy
 * time from local.settings.json's exportRootFolderId, mirroring
 * registerAxiomConfig()'s set_axiom_config pattern in manage-deployments.js)
 * names a Drive folder. Each exported document gets its own subfolder
 * underneath it, named to match the document for human scanning.
 *
 * Document titles collide (two docs can share a name), so the docId ->
 * folder mapping is never derived by name lookup -- it is tracked in a small
 * index spreadsheet (CONTRACT_SCHEMA.sheetExportIndex) created inside the
 * root folder on first use. The index spreadsheet's own ID is cached in a
 * second Script Property (EXPORT_INDEX_SHEET_ID) so normal calls don't pay
 * for a folder listing; if that cached ID no longer resolves (spreadsheet
 * deleted out of band), it is recreated.
 *
 * If EXPORT_ROOT_FOLDER_ID is unset, resolution falls back to the pre-fix
 * behavior (the source document's own parent folder) so an unconfigured
 * deployment still exports successfully -- isolation is best-effort, not a
 * hard requirement of the export path.
 */

var _EXPORT_INDEX_SHEET_NAME = 'GActionSheet Export Index';

/**
 * Resolves (creating if necessary) the Drive folder that export output for
 * `documentId` should be written into. Same return contract as the
 * getSourceFolder_() it replaces at the exportGovernance_() call site:
 * a Drive Folder, or null if none could be resolved.
 *
 * @param {string} documentId
 * @param {string} title  Document title, used only for the folder's
 *   human-readable name -- never as the lookup key.
 * @return {?GoogleAppsScript.Drive.Folder}
 */
function getExportFolder_(documentId, title) {
  var root = _getExportRootFolder_();
  if (!root) {
    GasLogger.log('export.folder.fallback_source', { docId: documentId, reason: 'EXPORT_ROOT_FOLDER_ID not set' });
    return getSourceFolder_(documentId);
  }

  var sheet = _getOrCreateExportIndexSheet_(root);
  if (!sheet) {
    GasLogger.log('export.folder.fallback_source', { docId: documentId, reason: 'export index sheet unavailable' });
    return getSourceFolder_(documentId);
  }

  var cols = CONTRACT_SCHEMA.sheetExportIndex.columnsByField;
  var existing = _findExportIndexRow_(sheet, cols, documentId);
  var now = new Date();

  if (existing) {
    var folder = _openFolderById_(existing.folderId);
    if (folder) {
      sheet.getRange(existing.rowNum, cols.last_exported_at).setValue(now);
      GasLogger.log('export.folder.resolved', { docId: documentId, folderId: existing.folderId, created: false });
      return folder;
    }
    // Folder was deleted out of band -- fall through and recreate it,
    // overwriting the stale row rather than appending a duplicate.
  }

  var newFolder = root.createFolder(sanitizeFilename_(title) + ' - ' + documentId);
  var newFolderId = newFolder.getId();
  if (existing) {
    sheet.getRange(existing.rowNum, 1, 1, CONTRACT_SCHEMA.sheetExportIndex.headers.length).setValues([[
      documentId, title || '', newFolderId, now, now, '{}'
    ]]);
  } else {
    sheet.appendRow([documentId, title || '', newFolderId, now, now, '{}']);
  }
  GasLogger.log('export.folder.resolved', { docId: documentId, folderId: newFolderId, created: true });
  return newFolder;
}

/**
 * @return {?GoogleAppsScript.Drive.Folder}
 */
function _getExportRootFolder_() {
  var id = PropertiesService.getScriptProperties().getProperty('EXPORT_ROOT_FOLDER_ID');
  if (!id) return null;
  return _openFolderById_(id);
}

/**
 * @param {string} id
 * @return {?GoogleAppsScript.Drive.Folder} null if id is falsy, not found, or trashed.
 */
function _openFolderById_(id) {
  if (!id) return null;
  try {
    var folder = DriveApp.getFolderById(id);
    if (folder.isTrashed()) return null;
    return folder;
  } catch (e) {
    return null;
  }
}

/**
 * Finds or creates the export-index spreadsheet inside `root`, using the
 * cached EXPORT_INDEX_SHEET_ID script property to skip a folder listing on
 * the common path.
 *
 * @param {GoogleAppsScript.Drive.Folder} root
 * @return {?GoogleAppsScript.Spreadsheet.Sheet} the single data sheet/tab.
 */
function _getOrCreateExportIndexSheet_(root) {
  var props = PropertiesService.getScriptProperties();
  var cachedId = props.getProperty('EXPORT_INDEX_SHEET_ID');

  if (cachedId) {
    try {
      var ss = SpreadsheetApp.openById(cachedId);
      return _firstSheetWithHeaders_(ss);
    } catch (e) {
      // Stale/deleted -- fall through and recreate.
    }
  }

  // Reuse an existing index spreadsheet already sitting in the root folder
  // (e.g. survives a Script Property reset) before creating a new one.
  var files = root.getFilesByName(_EXPORT_INDEX_SHEET_NAME);
  if (files.hasNext()) {
    var found = SpreadsheetApp.openById(files.next().getId());
    props.setProperty('EXPORT_INDEX_SHEET_ID', found.getId());
    return _firstSheetWithHeaders_(found);
  }

  var created = SpreadsheetApp.create(_EXPORT_INDEX_SHEET_NAME);
  var createdFile = DriveApp.getFileById(created.getId());
  root.addFile(createdFile);
  DriveApp.getRootFolder().removeFile(createdFile); // move, don't duplicate-list, out of My Drive root
  var sheet = created.getSheets()[0];
  sheet.getRange(1, 1, 1, CONTRACT_SCHEMA.sheetExportIndex.headers.length)
    .setValues([CONTRACT_SCHEMA.sheetExportIndex.headers]);
  props.setProperty('EXPORT_INDEX_SHEET_ID', created.getId());
  return sheet;
}

function _firstSheetWithHeaders_(ss) {
  var sheet = ss.getSheets()[0];
  if (sheet.getLastRow() < 1) {
    sheet.getRange(1, 1, 1, CONTRACT_SCHEMA.sheetExportIndex.headers.length)
      .setValues([CONTRACT_SCHEMA.sheetExportIndex.headers]);
  }
  return sheet;
}

/**
 * @param {GoogleAppsScript.Spreadsheet.Sheet} sheet
 * @param {Object} cols  CONTRACT_SCHEMA.sheetExportIndex.columnsByField
 * @param {string} documentId
 * @return {?{rowNum: number, folderId: string}}
 */
function _findExportIndexRow_(sheet, cols, documentId) {
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return null;
  var numCols = CONTRACT_SCHEMA.sheetExportIndex.headers.length;
  var values = sheet.getRange(2, 1, lastRow - 1, numCols).getValues();
  for (var i = 0; i < values.length; i++) {
    if (values[i][cols.doc_id - 1] === documentId) {
      return { rowNum: i + 2, folderId: values[i][cols.folder_id - 1] };
    }
  }
  return null;
}

/**
 * Test-only diagnostic (gts-es3l): returns every export-index row matching
 * `documentId`, so a test can assert the index stays at exactly one row per
 * doc (idempotent upsert, not append-on-every-export) — durable state the
 * WebApp's export_governance_json response alone can't reveal. Never called
 * by production code.
 *
 * @param {string} documentId
 * @return {Array<{docId: string, docTitle: string, folderId: string}>}
 *   Empty if EXPORT_ROOT_FOLDER_ID isn't configured or the index has no match.
 */
function dumpExportIndexRowsForTest_(documentId) {
  var root = _getExportRootFolder_();
  if (!root) return [];
  var sheet = _getOrCreateExportIndexSheet_(root);
  if (!sheet) return [];

  var cols = CONTRACT_SCHEMA.sheetExportIndex.columnsByField;
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  var numCols = CONTRACT_SCHEMA.sheetExportIndex.headers.length;
  var values = sheet.getRange(2, 1, lastRow - 1, numCols).getValues();
  var rows = [];
  for (var i = 0; i < values.length; i++) {
    if (values[i][cols.doc_id - 1] === documentId) {
      rows.push({
        docId: values[i][cols.doc_id - 1],
        docTitle: values[i][cols.doc_title - 1],
        folderId: values[i][cols.folder_id - 1]
      });
    }
  }
  return rows;
}
