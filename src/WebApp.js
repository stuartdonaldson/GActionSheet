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

  var registered = '';
  if (!BUILD_INFO.webappUrl) {
    PropertiesService.getScriptProperties().setProperty('WEBAPP_URL', url);
    registered = ' (registered to script properties)';
  }

  return ContentService.createTextOutput(
    'GActionSheet ' + BUILD_INFO.version + '\n' +
    'Build:   ' + BUILD_INFO.buildDate + '\n' +
    'WebApp:  ' + url + registered
  );
}

function doPost(e) {
  var payload;
  try {
    payload = JSON.parse(e.postData.contents);
  } catch (ex) {
    return _jsonResponse({ error: 'bad JSON' }, 200);
  }

  // Test fixture route — authenticated by per-deployment TEST_TOKEN, not WEBAPP_SECRET.
  // Must be checked before the WEBAPP_SECRET gate so the deployment script can register
  // the token using WEBAPP_SECRET without the token already being required.
  if (payload.action === 'run_fixture') {
    return _handleRunFixture(payload);
  }

  var expected = PropertiesService.getScriptProperties().getProperty('WEBAPP_SECRET');
  if (!expected || payload.secret !== expected) {
    return ContentService.createTextOutput('unauthorized').setMimeType(ContentService.MimeType.TEXT);
  }

  if (payload.clientVersion && payload.clientVersion !== BUILD_INFO.version) {
    GasLogger.log('webapp.version.mismatch', { client: payload.clientVersion, server: BUILD_INFO.version });
  }

  if (payload.action === 'set_test_token') {
    return _handleSetTestToken(payload);
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

  if (payload.action === 'mark_doc_not_found') {
    return _handleMarkDocNotFound(payload);
  }

  if (payload.action === 'delete_action_row') {
    return _handleDeleteActionRow(payload);
  }

  if (payload.action === 'patch_action_status') {
    return _handlePatchActionStatus(payload);
  }

  // Legacy POC — retained for diagnostics
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  sheet.appendRow([new Date(), payload.email || '', payload.message || '']);
  return ContentService.createTextOutput('ok');
}

// ---------------------------------------------------------------------------
// set_test_token handler  (deployment script only — requires WEBAPP_SECRET)
// ---------------------------------------------------------------------------

/**
 * Stores a per-deployment test token in Script Properties.
 * Called once by the deployment script after each `npm run deploy:test`.
 * The token expires at expiresAt (ISO string); run_fixture rejects expired tokens.
 *
 * Payload shape:
 *   { secret, action: 'set_test_token', testToken: '<uuid>', expiresAt: '<ISO>' }
 *
 * Response shape:
 *   { ok: true, expiresAt }
 */
function _handleSetTestToken(payload) {
  var testToken = payload.testToken || '';
  var expiresAt = payload.expiresAt || '';
  if (!testToken) {
    return _jsonResponse({ error: 'testToken required' });
  }
  var props = PropertiesService.getScriptProperties();
  props.setProperty('TEST_TOKEN', testToken);
  props.setProperty('TEST_TOKEN_EXPIRES', expiresAt);
  GasLogger.log('test.token.set', { expiresAt: expiresAt });
  GasLogger.flush();
  return _jsonResponse({ ok: true, expiresAt: expiresAt });
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

  var upserted = 0;
  var now      = new Date();

  WriteGuard.wrap(function () {
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      if (!row.namedRangeId || existingMap[row.namedRangeId]) continue;

      var docFormula = '=HYPERLINK("' + docUrl + '","' + _escapeQuotes(docTitle) + '")';
      actionsSheet.appendRow([
        row.namedRangeId,
        _extractActionId(row.namedRangeId),
        row.assigneeEmail || '',
        row.assigneeName  || '',
        row.actionText    || '',
        row.status        || 'Open',
        docFormula,
        now,
        now,
        ''  // Sync Status — blank on insert
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
      assigneeName:  data[i][3] || '',
      action:        data[i][4],
      status:        data[i][5],
      dateModified:  data[i][8] instanceof Date ? data[i][8] : null,
      syncStatus:    data[i][9] || ''
    };
  }

  return result;
}

/**
 * Extracts the human-readable action ID from a globalId.
 * globalId format: {docFileId}/AI-{N}  →  returns 'AI-{N}'
 * Falls back to the raw globalId if the format is unexpected.
 */
function _extractActionId(globalId) {
  var parts = (globalId || '').split('/AI-');
  return parts.length >= 2 ? 'AI-' + parts[1] : globalId || '';
}

function _rowIdentityKey(assigneeEmail, action, status) {
  return [
    assigneeEmail || '',
    action || '',
    status || 'Open'
  ].join('\u0001');
}

/**
 * Bidirectional sync handler.  Compares the doc state snapshot against the
 * current ActionSheet rows using the last-sync timestamp as the conflict anchor.
 *
 * Payload shape:
 *   { secret, action: 'sync_action_rows', docUrl, docTitle,
 *     docState: [{ namedRangeId, assigneeEmail, assigneeName, actionText, status }] }
 *
 * Response shape:
 *   { upserted, updated, sheetWins: [{ namedRangeId, action, status, assigneeEmail }] }
 */
function _handleSyncActionRows(payload) {
  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return _jsonResponse({ error: 'Actions sheet not found' });
  }

  var docUrl              = payload.docUrl   || '';
  var docTitle            = payload.docTitle || 'Untitled';
  var docId               = payload.docId    || '';
  var docState            = payload.docState || [];
  var allDocNamedRangeIds = payload.allDocNamedRangeIds || [];

  // Build a set for O(1) membership checks.
  var activeNrIdSet = {};
  for (var ai = 0; ai < allDocNamedRangeIds.length; ai++) {
    activeNrIdSet[allDocNamedRangeIds[ai]] = true;
  }

  var existingMap = _loadExistingRowsByNamedRangeId(actionsSheet);
  var now         = new Date();
  var upserted    = 0;
  var updated     = 0;
  var sheetWins   = [];
  var docStateByNamedRangeId = {};
  var docStateIdentitySet    = {};

  for (var dsi = 0; dsi < docState.length; dsi++) {
    var docRow = docState[dsi];
    docStateByNamedRangeId[docRow.namedRangeId] = true;
    docStateIdentitySet[_rowIdentityKey(docRow.assigneeEmail, docRow.actionText, docRow.status)] = true;
  }

  // Load col 7 formulas for orphan detection (need docId to match rows to this doc).
  var lastRow      = actionsSheet.getLastRow();
  var formulasCol7 = lastRow >= 2
    ? actionsSheet.getRange(2, 7, lastRow - 1, 1).getFormulas()
    : [];
  var duplicateRowIndexes = [];

  WriteGuard.wrap(function () {
    for (var i = 0; i < docState.length; i++) {
      var row      = docState[i];
      var existing = existingMap[row.namedRangeId];

      if (!existing) {
        var docFormula = '=HYPERLINK("' + docUrl + '","' + _escapeQuotes(docTitle) + '")';
        actionsSheet.appendRow([
          row.namedRangeId,
          _extractActionId(row.namedRangeId),
          row.assigneeEmail || '',
          row.assigneeName  || '',
          row.actionText    || '',
          row.status        || 'Open',
          docFormula,
          now,
          now,
          ''  // Sync Status — blank on insert
        ]);
        upserted++;
      } else if (existing.syncStatus === 'Dirty') {
        // Sheet was edited (onActionSheetEdit set Sync Status = 'Dirty') — sheet wins.
        // SyncManager will apply the sheet values back to the doc floating action.
        sheetWins.push({
          namedRangeId:  row.namedRangeId,
          assigneeEmail: existing.assigneeEmail,
          assigneeName:  existing.assigneeName,
          action:        existing.action,
          status:        existing.status
        });
        // Row synced successfully — clear any prior Sync Status.
        actionsSheet.getRange(existing.rowIndex, 10).setValue('');
      } else {
        // Doc is authoritative — update sheet row only when content values differ.
        var rowIdx     = existing.rowIndex;
        var docFormula = '=HYPERLINK("' + docUrl + '","' + _escapeQuotes(docTitle) + '")';
        var correctId = _extractActionId(row.namedRangeId);
        if (existing.id !== correctId) {
          actionsSheet.getRange(rowIdx, 2).setValue(correctId);
        }
        if (existing.assigneeEmail !== row.assigneeEmail ||
            existing.assigneeName !== row.assigneeName ||
            existing.action !== row.actionText ||
            existing.status !== row.status) {
          actionsSheet.getRange(rowIdx, 3).setValue(row.assigneeEmail || '');
          actionsSheet.getRange(rowIdx, 4).setValue(row.assigneeName  || '');
          actionsSheet.getRange(rowIdx, 5).setValue(row.actionText || '');
          actionsSheet.getRange(rowIdx, 6).setValue(row.status     || 'Open');
          actionsSheet.getRange(rowIdx, 9).setValue(now);
          updated++;
        }
        actionsSheet.getRange(rowIdx, 7).setFormula(docFormula);
        // Row synced successfully — clear any prior Sync Status.
        actionsSheet.getRange(rowIdx, 10).setValue('');
      }
    }

    // Detect orphaned rows: rows for this doc whose named range is gone from the doc.
    if (docId) {
      for (var nrId in existingMap) {
        if (docStateByNamedRangeId[nrId]) continue;
        var entry = existingMap[nrId];
        var fIdx  = entry.rowIndex - 2; // formulasCol7 is 0-based from row 2
        var formula = (fIdx >= 0 && fIdx < formulasCol7.length) ? formulasCol7[fIdx][0] : '';
        if (formula.indexOf(docId) === -1) continue; // belongs to a different doc

        // If the current doc still has the same action state under a different
        // named range, this row is a stale duplicate left behind by a re-anchor.
        var identityKey = _rowIdentityKey(entry.assigneeEmail, entry.action, entry.status);
        if (docStateIdentitySet[identityKey]) {
          duplicateRowIndexes.push(entry.rowIndex);
          continue;
        }

        if (activeNrIdSet[nrId]) continue; // still in the doc

        actionsSheet.getRange(entry.rowIndex, 10).setValue('Deleted');
        GasLogger.log('sync.info', { msg: 'Sync Status — Deleted', row: entry.rowIndex, namedRangeId: nrId });
      }

      duplicateRowIndexes.sort(function (a, b) { return b - a; });
      for (var dri = 0; dri < duplicateRowIndexes.length; dri++) {
        actionsSheet.deleteRow(duplicateRowIndexes[dri]);
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

/**
 * Marks all Actions rows whose Document formula references docId as
 * 'Doc Not Found' in the Sync Status column.
 *
 * Payload shape: { secret, action: 'mark_doc_not_found', docId }
 */
function _handleMarkDocNotFound(payload) {
  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return _jsonResponse({ error: 'Actions sheet not found', marked: 0 });
  }

  var docId   = payload.docId || '';
  var lastRow = actionsSheet.getLastRow();
  if (!docId || lastRow < 2) {
    return _jsonResponse({ marked: 0 });
  }

  var numRows      = lastRow - 1;
  var formulasCol7 = actionsSheet.getRange(2, 7, numRows, 1).getFormulas();
  var marked       = 0;

  WriteGuard.wrap(function () {
    for (var i = 0; i < formulasCol7.length; i++) {
      var formula = formulasCol7[i][0] || '';
      if (formula.indexOf(docId) === -1) continue;
      actionsSheet.getRange(i + 2, 10).setValue('Doc Not Found');
      marked++;
    }
  });

  GasLogger.log('sync.warn', { msg: 'Doc Not Found', docId: docId, marked: marked });
  return _jsonResponse({ marked: marked });
}

/**
 * Permanently deletes the ActionSheet row whose NamedRangeId matches
 * payload.namedRangeId.  Called by sidebarDeleteAction after the doc-side
 * paragraph and named range have already been removed.
 *
 * Payload shape:
 *   { secret, action: 'delete_action_row', namedRangeId }
 *
 * Response shape:
 *   { deleted: 0|1 }
 */
function _handleDeleteActionRow(payload) {
  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return _jsonResponse({ error: 'Actions sheet not found', deleted: 0 });
  }

  var namedRangeId = payload.namedRangeId || '';
  if (!namedRangeId) {
    return _jsonResponse({ error: 'namedRangeId required', deleted: 0 });
  }

  var existingMap = _loadExistingRowsByNamedRangeId(actionsSheet);
  var entry       = existingMap[namedRangeId];
  if (!entry) {
    return _jsonResponse({ deleted: 0 });
  }

  WriteGuard.wrap(function () {
    actionsSheet.deleteRow(entry.rowIndex);
  });

  GasLogger.log('sidebar.delete.row', { namedRangeId: namedRangeId, rowIndex: entry.rowIndex });
  return _jsonResponse({ deleted: 1 });
}

/**
 * Updates Status and Date Modified for a single ActionSheet row, identified by
 * namedRangeId.  Also clears Sync Status so a stale 'Dirty' flag cannot cause
 * the next bidirectional sync to overwrite the change.
 *
 * Called by sidebarSetStatus instead of the full syncDocument — avoids the
 * sheet-wins revert bug and is ~10× faster (no doc scan, no full sheet scan).
 *
 * Payload shape:
 *   { secret, action: 'patch_action_status', namedRangeId, newStatus }
 *
 * Response shape:
 *   { patched: 0|1 }
 */
function _handlePatchActionStatus(payload) {
  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return _jsonResponse({ error: 'Actions sheet not found', patched: 0 });
  }

  var namedRangeId = payload.namedRangeId || '';
  var newStatus    = payload.newStatus    || '';
  if (!namedRangeId || !newStatus) {
    return _jsonResponse({ error: 'namedRangeId and newStatus required', patched: 0 });
  }

  var existingMap = _loadExistingRowsByNamedRangeId(actionsSheet);
  var entry       = existingMap[namedRangeId];
  if (!entry) {
    return _jsonResponse({ patched: 0 });
  }

  var now = new Date();
  WriteGuard.wrap(function () {
    actionsSheet.getRange(entry.rowIndex, 6).setValue(newStatus); // Status
    actionsSheet.getRange(entry.rowIndex, 9).setValue(now);       // Date Modified
    actionsSheet.getRange(entry.rowIndex, 10).setValue('');       // clear Sync Status
  });

  GasLogger.log('sidebar.status.patched', { namedRangeId: namedRangeId, newStatus: newStatus, row: entry.rowIndex });
  return _jsonResponse({ patched: 1 });
}

function _escapeQuotes(s) {
  // Google Sheets formula strings use "" to escape a literal double-quote, not \".
  return String(s).replace(/"/g, '""');
}

function _jsonResponse(obj) {
  obj.serverVersion = BUILD_INFO.version;
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
