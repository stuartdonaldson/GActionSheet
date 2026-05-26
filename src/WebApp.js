/**
 * WebApp.js
 *
 * doGet  — self-registers the canonical WEBAPP_URL script property on first visit.
 * doPost — verifies WEBAPP_SECRET and routes action payloads.
 *
 * The Web App runs as USER_DEPLOYING (sheet owner) so the add-on sidebar
 * (which runs as the active user) can write to the restricted ActionSheet.
 */

function doGet(e) {
  var url = ScriptApp.getService().getUrl();
  // Normalize org-specific URL to the canonical form stored in script properties
  url = url.replace(/https:\/\/script\.google\.com\/a\/[^\/]+\/macros\//, 'https://script.google.com/macros/');
  PropertiesService.getScriptProperties().setProperty('WEBAPP_URL', url);
  return ContentService.createTextOutput('WEBAPP_URL registered: ' + url);
}

function doPost(e) {
  var payload;
  try {
    payload = JSON.parse(e.postData.contents);
  } catch (ex) {
    return _jsonResponse({ error: 'bad JSON' }, 200);
  }

  var expected = PropertiesService.getScriptProperties().getProperty('WEBAPP_SECRET');
  if (!expected || payload.secret !== expected) {
    return ContentService.createTextOutput('unauthorized').setMimeType(ContentService.MimeType.TEXT);
  }

  if (payload.action === 'upsert_action_rows') {
    return _handleUpsertActionRows(payload);
  }

  if (payload.action === 'sync_action_rows') {
    return _handleSyncActionRows(payload);
  }

  if (payload.action === 'verify_action_rows') {
    return _handleVerifyActionRows(payload);
  }

  // Legacy POC — retained for diagnostics
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  sheet.appendRow([new Date(), payload.email || '', payload.message || '']);
  return ContentService.createTextOutput('ok');
}

// ---------------------------------------------------------------------------
// upsert_action_rows handler
// ---------------------------------------------------------------------------

/**
 * Inserts new action rows into the "Actions" sheet.
 * Rows whose namedRangeId already exists are silently skipped (idempotent).
 *
 * Payload shape:
 *   { secret, action: 'upsert_action_rows', docUrl, docTitle, rows: [
 *     { namedRangeId, assigneeEmail, assigneeName, actionText, status }
 *   ] }
 *
 * Response shape:
 *   { upserted: <count> }
 */
function _handleUpsertActionRows(payload) {
  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return _jsonResponse({ error: 'Actions sheet not found' });
  }

  var docUrl   = payload.docUrl   || '';
  var docTitle = payload.docTitle || 'Untitled';
  var rows     = payload.rows     || [];

  var existingMap = _loadExistingRowsByNamedRangeId(actionsSheet);
  var maxId       = _findMaxId(existingMap);

  var upserted = 0;
  var now      = new Date();

  WriteGuard.wrap(function () {
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      if (!row.namedRangeId || existingMap[row.namedRangeId]) continue;

      maxId++;
      var docFormula = '=HYPERLINK("' + docUrl + '","' + _escapeQuotes(docTitle) + '")';
      actionsSheet.appendRow([
        row.namedRangeId,
        maxId,
        row.assigneeEmail || '',
        row.assigneeName  || '',
        row.actionText    || '',
        row.status        || 'Open',
        docFormula,
        now,
        now
      ]);
      upserted++;
    }
  });

  return _jsonResponse({ upserted: upserted });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Returns { namedRangeId: { id, ... } } for every non-blank row in actionsSheet.
 */
function _loadExistingRowsByNamedRangeId(actionsSheet) {
  var lastRow = actionsSheet.getLastRow();
  if (lastRow < 2) return {};

  var data   = actionsSheet.getRange(2, 1, lastRow - 1, SHEET_HEADERS.length).getValues();
  var result = {};

  for (var i = 0; i < data.length; i++) {
    var namedRangeId = data[i][0];
    if (!namedRangeId) continue;
    result[namedRangeId] = {
      rowIndex:      i + 2,
      id:            data[i][1],
      assigneeEmail: data[i][2],
      assigneeName:  data[i][3],
      action:        data[i][4],
      status:        data[i][5],
      dateModified:  data[i][8] instanceof Date ? data[i][8] : null
    };
  }

  return result;
}

function _findMaxId(existingMap) {
  var max = 0;
  for (var k in existingMap) {
    var id = existingMap[k].id;
    if (typeof id === 'number' && id > max) max = id;
  }
  return max;
}

/**
 * Bidirectional sync handler.  Compares the doc state snapshot against the
 * current ActionSheet rows using the last-sync timestamp as the conflict anchor.
 *
 * Payload shape:
 *   { secret, action: 'sync_action_rows', docUrl, docTitle, lastSyncTime: ISO,
 *     docState: [{ namedRangeId, assigneeEmail, assigneeName, actionText, status }] }
 *
 * Response shape:
 *   { upserted, updated, sheetWins: [{ namedRangeId, action, status }] }
 */
function _handleSyncActionRows(payload) {
  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return _jsonResponse({ error: 'Actions sheet not found' });
  }

  var docUrl       = payload.docUrl   || '';
  var docTitle     = payload.docTitle || 'Untitled';
  var docState     = payload.docState || [];
  var lastSyncTime = payload.lastSyncTime ? new Date(payload.lastSyncTime) : new Date(0);

  var existingMap = _loadExistingRowsByNamedRangeId(actionsSheet);
  var maxId       = _findMaxId(existingMap);
  var now         = new Date();
  var upserted    = 0;
  var updated     = 0;
  var sheetWins   = [];

  WriteGuard.wrap(function () {
    for (var i = 0; i < docState.length; i++) {
      var row      = docState[i];
      var existing = existingMap[row.namedRangeId];

      if (!existing) {
        maxId++;
        var docFormula = '=HYPERLINK("' + docUrl + '","' + _escapeQuotes(docTitle) + '")';
        actionsSheet.appendRow([
          row.namedRangeId,
          maxId,
          row.assigneeEmail || '',
          row.assigneeName  || '',
          row.actionText    || '',
          row.status        || 'Open',
          docFormula,
          now,
          now
        ]);
        upserted++;
      } else if (existing.dateModified && existing.dateModified > lastSyncTime) {
        // Sheet was edited after last sync — sheet wins; SyncManager updates doc.
        sheetWins.push({
          namedRangeId: row.namedRangeId,
          action:       existing.action,
          status:       existing.status
        });
      } else {
        // Doc is authoritative — update sheet row only when content values differ.
        var rowIdx = existing.rowIndex;
        var docFormula = '=HYPERLINK("' + docUrl + '","' + _escapeQuotes(docTitle) + '")';
        if (existing.action !== row.actionText || existing.status !== row.status) {
          actionsSheet.getRange(rowIdx, 5).setValue(row.actionText || '');
          actionsSheet.getRange(rowIdx, 6).setValue(row.status     || 'Open');
          actionsSheet.getRange(rowIdx, 9).setValue(now);
          updated++;
        }
        actionsSheet.getRange(rowIdx, 7).setFormula(docFormula);
      }
    }
  });

  return _jsonResponse({ upserted: upserted, updated: updated, sheetWins: sheetWins });
}

/**
 * Returns ActionSheet rows for a single document without mutating any data.
 *
 * Payload shape:
 *   { secret, action: 'verify_action_rows', docUrl }
 *
 * Response shape:
 *   { rows: [{ namedRangeId, id, assigneeEmail, assigneeName, action, status }] }
 */
function _handleVerifyActionRows(payload) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return _jsonResponse({ error: 'Actions sheet not found', rows: [] });
  }

  return _jsonResponse({
    rows: _loadRowsForDocUrl(actionsSheet, payload.docUrl || '')
  });
}

function _loadRowsForDocUrl(actionsSheet, docUrl) {
  var lastRow = actionsSheet.getLastRow();
  if (lastRow < 2) {
    return [];
  }

  var numRows = lastRow - 1;
  var data = actionsSheet.getRange(2, 1, numRows, SHEET_HEADERS.length).getValues();
  var formulas = actionsSheet.getRange(2, 7, numRows, 1).getFormulas();
  var rows = [];

  for (var i = 0; i < data.length; i++) {
    var docFormula = formulas[i][0] || '';
    if (docUrl && docFormula.indexOf(docUrl) === -1) {
      continue;
    }

    rows.push({
      namedRangeId: data[i][0] || '',
      id: data[i][1] || '',
      assigneeEmail: data[i][2] || '',
      assigneeName: data[i][3] || '',
      action: data[i][4] || '',
      status: data[i][5] || 'Open'
    });
  }

  return rows;
}

function _escapeQuotes(s) {
  // Google Sheets formula strings use "" to escape a literal double-quote, not \".
  return String(s).replace(/"/g, '""');
}

function _jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
