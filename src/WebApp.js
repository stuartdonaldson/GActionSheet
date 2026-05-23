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
      id:            data[i][1],
      assigneeEmail: data[i][2],
      assigneeName:  data[i][3],
      action:        data[i][4],
      status:        data[i][5]
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

function _escapeQuotes(s) {
  return String(s).replace(/"/g, '\\"');
}

function _jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
