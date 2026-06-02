/**
 * SyncManager.js
 *
 * UC-A: scan the doc for floating actions (identified by AI-N: text token)
 * and upsert rows to the ActionSheet via the Web App proxy (doPost).
 *
 * Identity: a doc-scoped sequential integer N embedded as "AI-N:" text in each
 * floating action paragraph. Global ID = {docFileId}/AI-{N}, stored in sheet col 1.
 * No DocumentApp named ranges are created or required.
 */

// ---------------------------------------------------------------------------
// Shared config
// ---------------------------------------------------------------------------

/**
 * Single source of truth for the action smart-chip link base. Used by the chip
 * insert/flush paths (EditorAddonCard, SyncManager) and the tracker ID links
 * (TrackerTable).
 *
 * Path is namespaced under `NUTS/` — the suite-level scope (Northlake Unitarian
 * Tool Suite). The action chip URL lives at `NUTS/action`; future tools take
 * sibling paths (e.g. `NUTS/llm` for an @-menu LLM trigger).
 *
 * The linkPreview `pathPrefix` in appsscript.json is `NUTS` (the suite root),
 * so any northlakeuu.org/NUTS/... URL triggers the preview. The redirect at
 * northlakeuu.org/NUTS/action → the /exec deployment must point to /exec (not
 * /dev) so Google's URL validation fetch succeeds for non-editor users.
 *
 * NOTE: `hostPattern` (`northlakeuu.org`) in appsscript.json must be kept in
 * sync manually — the manifest cannot read script globals.
 */
var ACTION_CHIP_URL_BASE = 'https://northlakeuu.org/NUTS/action';

// ---------------------------------------------------------------------------
// Public entry points
// ---------------------------------------------------------------------------

function syncDocument(docId) {
  try {
    if (!docId) {
      GasLogger.log('sync.error', { msg: 'docId is required' });
      return;
    }

    var doc;
    try {
      doc = DocumentApp.openById(docId);
    } catch (openErr) {
      GasLogger.log('sync.warn', { msg: 'Doc not found', docId: docId, err: openErr.message });
      _markDocNotFound(docId);
      return;
    }
    // DocumentApp.openById() succeeds on trashed docs — check explicitly.
    try {
      if (DriveApp.getFileById(docId).isTrashed()) {
        GasLogger.log('sync.warn', { msg: 'Doc not found', docId: docId, err: 'Document is in Trash' });
        _markDocNotFound(docId);
        return;
      }
    } catch (driveErr) {
      // Drive API unavailable or permission denied — proceed with sync.
    }
    var assignResult = _assignPlaceholderTokens(doc);
    if (assignResult.count > 0) {
      GasLogger.log('sync.assigned', { docId: docId, count: assignResult.count });
    }

    var floatingActions = _scanFloatingActions(doc);

    GasLogger.log('sync.scanned', { docId: docId, count: floatingActions.length });

    // Capture docUrl and docTitle before closing — needed even when empty
    // so WebApp can run orphan detection on existing rows.
    var docUrl   = doc.getUrl();
    var docTitle = doc.getName();

    if (floatingActions.length === 0) {
      doc.saveAndClose();
      var emptySync = _syncActionRows([], docUrl, docTitle, docId, []);
      SpreadsheetApp.flush();
      GasLogger.log('sync.complete', {
        docId: docId, anchored: 0,
        upserted: emptySync.upserted || 0,
        updated:  emptySync.updated  || 0
      });
      return;
    }

    // No named range anchoring needed — globalId IS the identity.
    // Duplicates (same AI-N copied) are excluded from the sheet sync to avoid
    // duplicate rows; they are flushed to doc separately so the copy paragraph
    // matches the canonical content.
    var canonicalByGlobalId = {};
    var hasDuplicateN       = {};
    for (var fi = 0; fi < floatingActions.length; fi++) {
      var fai = floatingActions[fi];
      if (!fai.isDuplicate) {
        canonicalByGlobalId[fai.globalId] = fai;
      } else {
        hasDuplicateN[fai.globalId] = true;
      }
    }

    var allDocGlobalIds = Object.keys(canonicalByGlobalId);
    var anchorResults   = allDocGlobalIds.map(function(gId) {
      var a = canonicalByGlobalId[gId];
      return {
        globalId:      a.globalId,
        wasNew:        false,
        assigneeEmail: a.assigneeEmail,
        assigneeName:  a.assigneeName,
        actionText:    a.actionText,
        status:        a.status
      };
    });

    var syncResult = _syncActionRows(anchorResults, docUrl, docTitle, docId, allDocGlobalIds);

    // Build the set of globalIds that need a REST flush:
    //   - sheetWins: sheet edited → push sheet data back to doc (all occurrences)
    //   - newly assigned: AI: → AI-N: just created → need chip link + badge applied
    //   - duplicates without a sheetWin: copy paragraphs → sync to canonical doc data
    var toFlush = {};
    var sheetWins = syncResult.sheetWins || [];
    for (var si = 0; si < sheetWins.length; si++) {
      var win = sheetWins[si];
      var cf  = canonicalByGlobalId[win.globalId];
      if (!cf) continue;
      toFlush[win.globalId] = {
        N:             cf.N,
        globalId:      win.globalId,
        action:        win.action,
        status:        win.status,
        assigneeEmail: win.assigneeEmail,
        assigneeName:  win.assigneeName
      };
    }
    for (var ni = 0; ni < assignResult.newGlobalIds.length; ni++) {
      var ngId = assignResult.newGlobalIds[ni];
      if (toFlush[ngId]) continue; // sheetWin already covers it
      var cfn = canonicalByGlobalId[ngId];
      if (!cfn) continue;
      toFlush[ngId] = {
        N:             cfn.N,
        globalId:      ngId,
        action:        cfn.actionText,
        status:        cfn.status,
        assigneeEmail: cfn.assigneeEmail,
        assigneeName:  cfn.assigneeName
      };
    }
    for (var gId in hasDuplicateN) {
      if (toFlush[gId]) continue; // sheetWin or new-assign already covers it
      var cf2 = canonicalByGlobalId[gId];
      if (!cf2) continue;
      toFlush[gId] = {
        N:             cf2.N,
        globalId:      gId,
        action:        cf2.actionText,
        status:        cf2.status,
        assigneeEmail: cf2.assigneeEmail,
        assigneeName:  cf2.assigneeName
      };
    }

    // Materialize missing explicit status tokens as '(Open)' in the doc.
    for (var gId3 in canonicalByGlobalId) {
      if (toFlush[gId3]) continue;
      var cfm = canonicalByGlobalId[gId3];
      if (!cfm.hasExplicitStatus) {
        toFlush[gId3] = {
          N:             cfm.N,
          globalId:      gId3,
          action:        cfm.actionText,
          status:        cfm.status,
          assigneeEmail: cfm.assigneeEmail,
          assigneeName:  cfm.assigneeName
        };
      }
    }

    var flushIds = Object.keys(toFlush);
    if (flushIds.length > 0) {
      var docId2 = doc.getId();
      doc.saveAndClose(); // close before REST calls
      var token = ScriptApp.getOAuthToken();
      for (var ti = 0; ti < flushIds.length; ti++) {
        var f  = toFlush[flushIds[ti]];
        var ok = _flushActionParagraph(docId2, token, f.N, f.globalId,
          f.action, f.status, f.assigneeEmail, f.assigneeName);
        if (!ok) _remarkRowDirty(f.globalId);
      }
    } else {
      doc.saveAndClose();
    }

    SpreadsheetApp.flush();

    // Refresh tracker table if the doc has one and anything changed during this sync.
    // "Changed" means: sheetWins flushed to doc, docWins updated the sheet, or new rows inserted.
    var hadChanges = flushIds.length > 0 ||
                     (syncResult.updated || 0) > 0 ||
                     (syncResult.upserted || 0) > 0;
    if (hadChanges) {
      try {
        insertTrackerTable(docId, { onlyIfExists: true });
      } catch (trackerErr) {
        GasLogger.log('sync.tracker-failed', { docId: docId, msg: trackerErr.message });
      }
    }

    GasLogger.log('sync.complete', {
      docId:    docId,
      anchored: 0,
      upserted: syncResult.upserted || 0,
      updated:  syncResult.updated  || 0
    });
  } finally {
    GasLogger.flush();
  }
}

/**
 * Syncs every document referenced by an existing ActionSheet row.
 *
 * Enumerates unique docIds from the Document HYPERLINK formulas in column 7,
 * then calls syncDocument() for each one.  If a document has been deleted or
 * is no longer accessible, syncDocument() stamps 'Doc Not Found' on every row
 * for that docId.  If a document exists but some actions were removed, the
 * orphan-detection pass in _handleSyncActionRows stamps those rows 'Deleted'.
 *
 * Called by:
 *   - Action Sync > Sync menu item (menuSync)
 *   - 30-minute time-based trigger
 */
function syncAll() {
  var _syncEu = ''; var _syncAu = '';
  try { _syncEu = Session.getEffectiveUser().getEmail(); } catch (_) {}
  try { _syncAu = Session.getActiveUser().getEmail();    } catch (_) {}
  GasLogger.log('sync.all.start.identity', { eu: _syncEu, au: _syncAu, version: BUILD_INFO.version });
  try {
    var ss           = SpreadsheetApp.getActiveSpreadsheet();
    var actionsSheet = ss.getSheetByName('Actions');
    if (!actionsSheet) {
      GasLogger.log('sync.all.error', { msg: 'Actions sheet not found', eu: _syncEu, au: _syncAu });
      return;
    }

    var lastRow = actionsSheet.getLastRow();
    if (lastRow < 2) {
      GasLogger.log('sync.all.complete', { docCount: 0 });
      return;
    }

    // Extract unique docIds from the HYPERLINK formula in column 7.
    // Formula shape: =HYPERLINK("https://docs.google.com/document/d/DOCID/edit", "Title")
    var numRows      = lastRow - 1;
    var formulasCol7 = actionsSheet.getRange(2, 7, numRows, 1).getFormulas();
    var docIdSet     = {};
    for (var i = 0; i < formulasCol7.length; i++) {
      var formula = formulasCol7[i][0] || '';
      var m = formula.match(/(?:\/d\/|[?&]id=)([a-zA-Z0-9_-]+)/);
      if (m) docIdSet[m[1]] = true;
    }

    var docIds = Object.keys(docIdSet);
    GasLogger.log('sync.all.start', { docCount: docIds.length });

    var syncStateSheet = _getOrCreateSyncStateSheet(ss);
    var syncState      = _loadSyncState(syncStateSheet);

    // Read cols 1 + 10 once for dirty-row detection across all docs.
    var actionData = actionsSheet.getRange(2, 1, numRows, 10).getValues();

    // Pre-build dirty-doc set in one pass — avoids O(docs × rows) scan per doc.
    var dirtyDocIds = {};
    for (var d = 0; d < actionData.length; d++) {
      if (actionData[d][9] === 'Dirty') {
        var gid   = actionData[d][0];
        var slash = gid.indexOf('/');
        if (slash > 0) dirtyDocIds[gid.substring(0, slash)] = true;
      }
    }

    var synced = 0, skipped = 0;
    for (var j = 0; j < docIds.length; j++) {
      var docId = docIds[j];

      // Single Drive call: trash check + last-modified timestamp.
      var driveFile, isTrashed, lastModified, docTitle;
      try {
        driveFile    = DriveApp.getFileById(docId);
        isTrashed    = driveFile.isTrashed();
        lastModified = driveFile.getLastUpdated();
        docTitle     = driveFile.getName();
      } catch (driveErr) {
        // Can't reach Drive — fall through to syncDocument which handles open failure.
        syncDocument(docId);
        _updateSyncState(syncStateSheet, docId, new Date(), '', syncState);
        synced++;
        continue;
      }

      if (isTrashed) {
        GasLogger.log('sync.warn', { msg: 'Doc not found', docId: docId, err: 'Document is in Trash' });
        _markDocNotFound(docId);
        continue;
      }

      var lastSynced = syncState[docId] ? syncState[docId].syncedAt : null;
      if (lastSynced && lastModified <= lastSynced && !dirtyDocIds[docId]) {
        GasLogger.log('sync.skip', { docId: docId });
        skipped++;
        continue;
      }

      syncDocument(docId);
      _updateSyncState(syncStateSheet, docId, new Date(), docTitle, syncState);
      synced++;
    }

    GasLogger.log('sync.all.complete', { docCount: docIds.length, synced: synced, skipped: skipped });
  } catch (e) {
    GasLogger.log('sync.all.error', { msg: e.message });
  } finally {
    GasLogger.flush();
  }
}

function onActionSheetEdit(e) {
  if (WriteGuard.isActive()) return;
  var range = e.range;
  var row   = range.getRow();
  if (row < 2) return;
  var col = range.getColumn();
  if ([3, 4, 5, 6].indexOf(col) === -1) return; // Assignee Email, Name, Action, Status
  var sheet = range.getSheet();
  if (sheet.getName() !== 'Actions') return;

  // Stamp Date Modified and mark Sync Status = 'Dirty' so the next bidirectional
  // sync knows this row was edited on the sheet side (sheet wins conflict resolution).
  // For multi-row pastes, stamp ALL rows in the range — if only the first row is
  // marked Dirty, the subsequent syncDocument call treats the other pasted rows as
  // doc-wins and overwrites them with old doc values.
  var numRows = range.getNumRows();
  var dateModified = new Date();
  WriteGuard.wrap(function () {
    if (numRows === 1) {
      sheet.getRange(row, 9).setValue(dateModified);
      sheet.getRange(row, 10).setValue('Dirty');
    } else {
      var dates    = [];
      var dirtyCol = [];
      for (var r = 0; r < numRows; r++) {
        dates.push([dateModified]);
        dirtyCol.push(['Dirty']);
      }
      sheet.getRange(row, 9, numRows, 1).setValues(dates);
      sheet.getRange(row, 10, numRows, 1).setValues(dirtyCol);
    }
  });

  _syncSheetRowToDoc(sheet, row);
}

/**
 * Propagates a single ActionSheet row edit to the corresponding floating action
 * in the source document via REST batchUpdate.
 *
 * Reads: globalId (col 1), Action (col 5), Status (col 6), Document URL (col 7)
 * Extracts docId from the Document hyperlink formula.
 * Extracts N from the globalId (format: {docId}/AI-{N}).
 *
 * @param {Sheet} sheet    The ActionSheet "Actions" tab
 * @param {number} row     1-based row number (guaranteed >= 2)
 */
function _syncSheetRowToDoc(sheet, row) {
  try {
    var rowData       = sheet.getRange(row, 1, 1, SHEET_HEADERS.length).getValues()[0];
    var globalId      = rowData[0];  // Col 1: globalId (format: {docId}/AI-{N})
    var assigneeEmail = rowData[2];  // Col 3: Assignee Email
    var assigneeName  = rowData[3];  // Col 4: Assignee Name
    var action        = rowData[4];  // Col 5: Action
    var status        = rowData[5];  // Col 6: Status
    var docFormula    = sheet.getRange(row, 7).getFormula();

    if (!globalId) return;
    if (!docFormula) return;

    var docIdMatch = docFormula.match(/(?:\/d\/|[?&]id=)([a-zA-Z0-9_-]+)/);
    if (!docIdMatch) return;
    var docId = docIdMatch[1];

    var parsed = parseGlobalId(globalId);
    if (isNaN(parsed.N)) return;
    var N = parsed.N;

    var token = ScriptApp.getOAuthToken();
    var ok = _flushActionParagraph(docId, token, N, globalId, action, status, assigneeEmail, assigneeName || '');
    if (ok) {
      // Flush confirmed — clear Dirty immediately rather than waiting for WebApp round-trip.
      WriteGuard.wrap(function () { sheet.getRange(row, 10).setValue(''); });
      GasLogger.log('sync.sheet-to-doc.done', { globalId: globalId });

      // Full doc scan: writes chip-resolved assigneeName back to sheet (docWins branch),
      // clears any residual Dirty, and keeps the sheet consistent with the doc's canonical
      // floating action state. WriteGuard cross-execution property suppresses the
      // onActionSheetEdit trigger that would otherwise re-set Dirty on these writes.
      try {
        syncDocument(docId);
      } catch (syncErr) {
        GasLogger.log('sync.sheet-to-doc.sync-failed', { globalId: globalId, msg: syncErr.message });
      }
    } else {
      GasLogger.log('sync.sheet-to-doc.flush-failed', { globalId: globalId });
    }
  } catch (err) {
    GasLogger.log('sync.sheet-to-doc.error', { row: row, msg: err.message });
  } finally {
    GasLogger.flush();
  }
}

// ---------------------------------------------------------------------------
// Scanner
// ---------------------------------------------------------------------------

/**
 * Walks the doc body and returns one entry per floating-action paragraph or
 * list item that contains an AI-N: token.
 *
 * Detection: paragraph full text starts with "AI-N:" (optionally preceded by
 * an inline image, which does not appear in DocumentApp getText()).
 *
 * @param {GoogleAppsScript.Document.Document} doc
 * @returns {Array<{bodyChildIndex, paragraph, globalId, N, assigneeEmail, assigneeName, actionText, status, hasExplicitStatus}>}
 */
function _scanFloatingActions(doc) {
  var body    = doc.getBody();
  var docId   = doc.getId();
  var n       = body.getNumChildren();
  var actions = [];
  var seenN   = {};

  for (var i = 0; i < n; i++) {
    var child      = body.getChild(i);
    var childType  = child.getType();
    var isPara     = childType === DocumentApp.ElementType.PARAGRAPH;
    var isListItem = childType === DocumentApp.ElementType.LIST_ITEM;
    if (!isPara && !isListItem) continue;

    var para = isPara ? child.asParagraph() : child.asListItem();
    // getText() strips inline images; AI-N: token must be at start of text content
    var fullText   = para.getText().replace(/\n$/, '');
    var tokenMatch = fullText.match(/^AI-(\d+):\s*/);
    if (!tokenMatch) continue;

    var N        = parseInt(tokenMatch[1], 10);
    var globalId = docId + '/AI-' + N;
    var afterToken = fullText.slice(tokenMatch[0].length);

    // Walk children: skip leading INLINE_IMAGE, then find the AI-N: TEXT element,
    // then look for an optional assignee chip or email-text after it.
    var numChildren        = para.getNumChildren();
    var assigneeEmail      = '';
    var assigneeName       = '';
    var assigneeSearchStart = 0;
    for (var ci = 0; ci < numChildren; ci++) {
      var ch = para.getChild(ci);
      if (ch.getType() === DocumentApp.ElementType.INLINE_IMAGE) continue;
      if (ch.getType() === DocumentApp.ElementType.TEXT) {
        assigneeSearchStart = ci + 1;
        break;
      }
    }
    for (var ai = assigneeSearchStart; ai < numChildren; ai++) {
      var ac = para.getChild(ai);
      if (ac.getType() === DocumentApp.ElementType.PERSON) {
        assigneeEmail = ac.asPerson().getEmail() || '';
        assigneeName  = ac.asPerson().getName()  || '';
        break;
      }
      if (ac.getType() === DocumentApp.ElementType.TEXT) {
        var t  = ac.asText().getText();
        var em = t.match(/^[\s]*([\w.+\-]+@[\w\-]+(?:\.[a-z]{2,})+)\s*/i);
        if (em) { assigneeEmail = em[1]; assigneeName = _nameFromEmail(assigneeEmail); }
        break;
      }
    }

    // Strip leading assignee email from afterToken if present; also covers the plain-text
    // case where the email shares child 0 with the AI-N: token (append_doc_paragraph path).
    var actionText = afterToken;
    var assigneeStrip = afterToken.match(/^([\w.+\-]+@[\w\-]+(?:\.[a-z]{2,})+)\s*/i);
    if (assigneeStrip) {
      actionText = afterToken.slice(assigneeStrip[0].length);
      if (!assigneeEmail) {
        assigneeEmail = assigneeStrip[1];
        assigneeName  = _nameFromEmail(assigneeEmail);
      }
    }

    // Parse trailing (status) token
    var status     = 'Open';
    var statusMatch = actionText.match(/\(([^)]*)\)\s*$/);
    var hasExplicitStatus = !!statusMatch;
    if (statusMatch) {
      status     = statusMatch[1].trim() || 'Open';
      actionText = actionText.slice(0, actionText.length - statusMatch[0].length).trim();
    }

    actions.push({
      bodyChildIndex:    i,
      paragraph:         para,
      globalId:          globalId,
      N:                 N,
      assigneeEmail:     assigneeEmail,
      assigneeName:      assigneeName,
      actionText:        actionText,
      status:            status,
      hasExplicitStatus: hasExplicitStatus,
      isDuplicate:       seenN[N] === true
    });
    seenN[N] = true;
  }
  return actions;
}

/**
 * Finds paragraphs starting with the bare "AI:" placeholder (no number) and
 * rewrites them as "AI-N:" using the next available N in the document.
 * Called in syncDocument before _scanFloatingActions so the scanner always
 * sees fully-formed AI-N: tokens.
 *
 * @param {GoogleAppsScript.Document.Document} doc
 * @returns {{ count: number, newGlobalIds: string[] }}
 */
function _assignPlaceholderTokens(doc) {
  var docId = doc.getId();
  var body  = doc.getBody();
  var n     = body.getNumChildren();

  // First pass: find current max N
  var maxN = 0;
  for (var i = 0; i < n; i++) {
    var child = body.getChild(i);
    var t = child.getType();
    if (t !== DocumentApp.ElementType.PARAGRAPH && t !== DocumentApp.ElementType.LIST_ITEM) continue;
    var m = child.getText().replace(/\n$/, '').match(/^AI-(\d+):/);
    if (m) maxN = Math.max(maxN, parseInt(m[1], 10));
  }

  // Second pass: assign next N to each bare "AI:" placeholder
  var assigned     = 0;
  var newGlobalIds = [];
  for (var j = 0; j < n; j++) {
    var child2 = body.getChild(j);
    var t2 = child2.getType();
    if (t2 !== DocumentApp.ElementType.PARAGRAPH && t2 !== DocumentApp.ElementType.LIST_ITEM) continue;
    var text = child2.getText().replace(/\n$/, '');
    if (!/^AI:/.test(text)) continue;

    maxN++;
    // Insert '-N' at position 2 (between 'AI' and ':') → 'AI:' becomes 'AI-N:'
    child2.editAsText().insertText(2, '-' + maxN);
    newGlobalIds.push(docId + '/AI-' + maxN);
    assigned++;
  }

  return { count: assigned, newGlobalIds: newGlobalIds };
}

/**
 * Derives a display name from an email address username.
 * Punctuation (. _ -) is treated as a word separator and each word is
 * title-cased.  e.g. "jane.smith@example.com" → "Jane Smith".
 */
function _nameFromEmail(email) {
  var username = email.split('@')[0];
  return username
    .replace(/[._\-]+/g, ' ')
    .replace(/\b\w/g, function(c) { return c.toUpperCase(); });
}

// ---------------------------------------------------------------------------
// ActionSheet proxy — bidirectional sync
// ---------------------------------------------------------------------------

/**
 * POSTs the doc state to the Web App for conflict resolution and sheet writes.
 * Returns { upserted, updated, sheetWins: [{ globalId, action, status, assigneeEmail }] }.
 *
 * @param {Array}  anchorResults  Each element: { globalId, assigneeEmail, assigneeName, actionText, status }.
 * @param {string} docUrl
 * @param {string} docTitle
 * @param {string} docId          Document ID (for orphan detection).
 * @param {Array}  allDocGlobalIds All globalIds currently in the doc.
 * @returns {{upserted: number, updated: number, sheetWins: Array}}
 */
function _syncActionRows(anchorResults, docUrl, docTitle, docId, allDocGlobalIds) {
  var webAppUrl = getWebAppUrl();
  var secret    = PropertiesService.getScriptProperties().getProperty('WEBAPP_SECRET');

  if (!webAppUrl) {
    GasLogger.log('sync.error', { msg: 'WEBAPP_URL not set' });
    return { upserted: 0, updated: 0, sheetWins: [] };
  }

  var docState = [];
  for (var i = 0; i < anchorResults.length; i++) {
    var a = anchorResults[i];
    docState.push({
      globalId:      a.globalId,
      assigneeEmail: a.assigneeEmail,
      assigneeName:  a.assigneeName,
      actionText:    a.actionText,
      status:        a.status
    });
  }

  // Bearer token is required: UrlFetchApp does not carry the caller's Google session
  // automatically. Without it, GAS returns HTTP 401 before doPost runs, regardless of
  // deployment type (/dev always enforces this; /exec with access:ANYONE also requires it).
  // The token satisfies GAS's auth gate only — doPost uses WEBAPP_SECRET for app-level auth.
  var oauthToken = ScriptApp.getOAuthToken();
  var resp = UrlFetchApp.fetch(webAppUrl, {
    method:             'post',
    contentType:        'application/json',
    muteHttpExceptions: true,
    headers:            { 'Authorization': 'Bearer ' + oauthToken },
    payload:            JSON.stringify({
      secret:             secret || '',
      action:             'sync_action_rows',
      clientVersion:      BUILD_INFO.version,
      docUrl:             docUrl,
      docTitle:           docTitle,
      docId:              docId || '',
      docState:           docState,
      allDocGlobalIds: allDocGlobalIds || []
    })
  });

  var code = resp.getResponseCode();
  if (code !== 200) {
    GasLogger.log('sync.error', {
      msg:  'sync_action_rows failed: HTTP ' + code,
      body: resp.getContentText().substring(0, 200)
    });
    return { upserted: 0, updated: 0, sheetWins: [] };
  }

  try {
    var parsed = JSON.parse(resp.getContentText());
    _logVersionMismatch(parsed, 'sync');
    return parsed;
  } catch (e) {
    GasLogger.log('sync.warn', { msg: 'Non-JSON sync_action_rows response', body: resp.getContentText().substring(0, 100) });
    return { upserted: 0, updated: 0, sheetWins: [] };
  }
}

/**
 * POSTs mark_doc_not_found to the WebApp so it can stamp 'Doc Not Found' on
 * all Actions rows whose Document formula references this docId.
 *
 * @param {string} docId
 */
function _markDocNotFound(docId) {
  var webAppUrl = getWebAppUrl();
  var secret    = PropertiesService.getScriptProperties().getProperty('WEBAPP_SECRET');
  if (!webAppUrl) return;
  var oauthToken = ScriptApp.getOAuthToken();
  UrlFetchApp.fetch(webAppUrl, {
    method:             'post',
    contentType:        'application/json',
    muteHttpExceptions: true,
    headers:            { 'Authorization': 'Bearer ' + oauthToken },
    payload:            JSON.stringify({
      secret:        secret || '',
      action:        'mark_doc_not_found',
      clientVersion: BUILD_INFO.version,
      docId:  docId
    })
  });
  GasLogger.flush();
}

/**
 * Re-marks an Actions sheet row as 'Dirty' so the next sync retries the
 * flush to doc.  Called when _flushActionParagraph returns false.
 * Searches column 1 (globalId) for the matching row.
 *
 * @param {string} globalId
 */
function _remarkRowDirty(globalId) {
  try {
    var ss    = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName('Actions');
    if (!sheet) return;
    var lastRow = sheet.getLastRow();
    if (lastRow < 2) return;
    var ids = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
    for (var i = 0; i < ids.length; i++) {
      if (ids[i][0] === globalId) {
        sheet.getRange(i + 2, 10).setValue('Dirty');
        GasLogger.log('flush.remarked-dirty', { globalId: globalId });
        return;
      }
    }
  } catch (e) {
    GasLogger.log('flush.remark-dirty.error', { globalId: globalId, msg: e.message });
  }
}

// ---------------------------------------------------------------------------
// SyncState sheet — per-doc last-synced-at tracking
// ---------------------------------------------------------------------------

/**
 * Returns the SyncState sheet, creating it with a header row if absent.
 * Columns: Doc ID | Last Synced At | Doc Title
 */
function _getOrCreateSyncStateSheet(ss) {
  var sheet = ss.getSheetByName('SyncState');
  if (!sheet) {
    sheet = ss.insertSheet('SyncState');
    sheet.getRange(1, 1, 1, 3).setValues([['Doc ID', 'Last Synced At', 'Doc Title']]);
    sheet.setFrozenRows(1);
  }
  return sheet;
}

/**
 * Reads the SyncState sheet into a map: { docId: { syncedAt: Date, row: number } }.
 * row is the 1-based sheet row so _updateSyncState can write in place.
 */
function _loadSyncState(syncStateSheet) {
  var state   = {};
  var lastRow = syncStateSheet.getLastRow();
  if (lastRow < 2) return state;

  var data = syncStateSheet.getRange(2, 1, lastRow - 1, 2).getValues();
  for (var i = 0; i < data.length; i++) {
    var docId    = data[i][0];
    var syncedAt = data[i][1];
    if (!docId) continue;
    state[docId] = {
      syncedAt: syncedAt instanceof Date ? syncedAt : new Date(syncedAt),
      row:      i + 2
    };
  }
  return state;
}

/**
 * Writes or updates a SyncState row for docId.
 * Mutates stateMap so subsequent lookups in the same run see the new timestamp.
 */
function _updateSyncState(syncStateSheet, docId, syncedAt, docTitle, stateMap) {
  if (stateMap[docId]) {
    syncStateSheet.getRange(stateMap[docId].row, 2, 1, 2).setValues([[syncedAt, docTitle || '']]);
    stateMap[docId].syncedAt = syncedAt;
  } else {
    var newRow = syncStateSheet.getLastRow() + 1;
    syncStateSheet.getRange(newRow, 1, 1, 3).setValues([[docId, syncedAt, docTitle || '']]);
    stateMap[docId] = { syncedAt: syncedAt, row: newRow };
  }
}


// ---------------------------------------------------------------------------
// Shared chip styling
// ---------------------------------------------------------------------------

/**
 * Returns the updateTextStyle request that applies the AI-N chip badge style
 * over [startIndex, endIndex): bold Comic Sans, purple text (#4C1D95), no
 * hyperlink underline. No background is set — the badge is purple text only.
 *
 * Shared by _flushActionParagraph (sync flush), _insertActionChip (creation),
 * and _insertTrackerIdLinks (tracker ID column) so the badge appearance is
 * defined in exactly one place.
 *
 * @param {number} startIndex
 * @param {number} endIndex
 * @returns {Object} A Docs REST batchUpdate request object.
 */
function _chipBadgeStyleRequest(startIndex, endIndex) {
  return {
    updateTextStyle: {
      range: { startIndex: startIndex, endIndex: endIndex },
      textStyle: {
        bold: true, underline: false,
        foregroundColor: { color: { rgbColor: { red: 0.298, green: 0.114, blue: 0.584 } } },
        weightedFontFamily: { fontFamily: 'Comic Sans MS', weight: 700 }
      },
      fields: 'bold,underline,foregroundColor,weightedFontFamily'
    }
  };
}

// ---------------------------------------------------------------------------
// REST flush — rewrites an AI-N: paragraph in place
// ---------------------------------------------------------------------------

/**
 * Rewrites the content of an AI-N: paragraph via REST API batchUpdate.
 * Preserves the paragraph node (does not delete the trailing \n).
 * Caller must have called doc.saveAndClose() before invoking this.
 *
 * @param {string} docId
 * @param {string} token          OAuth token from ScriptApp.getOAuthToken()
 * @param {number} N              The integer from the AI-N: token
 * @param {string} globalId       {docId}/AI-{N}
 * @param {string} actionText     Action text (no trailing status token)
 * @param {string} status         Status string
 * @param {string} assigneeEmail  May be empty
 * @param {string=} assigneeName  Optional display name for person chip
 */
function _flushActionParagraph(docId, token, N, globalId, actionText, status, assigneeEmail, assigneeName) {
  var baseUrl = 'https://docs.googleapis.com/v1/documents/';
  var chipUrl = ACTION_CHIP_URL_BASE + '?c=view&globalId=' + encodeURIComponent(globalId);
  // Docs REST API insertInlineImage does not support SVG — use PNG until PNG status icons exist.
  var imgUrl = 'https://stuartdonaldson.github.io/GActionSheet/assets/action-logo-t-32.png';

  var validEmail = assigneeEmail && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(assigneeEmail);
  var tokenLen   = ('AI-' + N + ': ').length;

  // GET to find paragraph indices.
  // builtText is text-run content only — inline images appear as inlineObjectElement.
  var getResp = UrlFetchApp.fetch(baseUrl + docId + '?fields=body.content(startIndex,endIndex,paragraph/elements(textRun/content))',
    { headers: { Authorization: 'Bearer ' + token }, muteHttpExceptions: true });
  if (getResp.getResponseCode() !== 200) {
    GasLogger.log('flush.error', { msg: 'GET failed: HTTP ' + getResp.getResponseCode(), globalId: globalId });
    return false;
  }

  var getBody = JSON.parse(getResp.getContentText());
  var content = (getBody.body || {}).content || [];

  // Collect ALL occurrences of this AI-N: token (handles copy-pasted paragraphs).
    // Process descending so lower-index paragraphs are unaffected by higher-index changes.
    var occurrences = [];
    for (var i = 0; i < content.length; i++) {
      var para = content[i].paragraph;
      if (!para) continue;
      var runs = para.elements || [];
      var builtText = '';
      for (var j = 0; j < runs.length; j++) {
        if (runs[j].textRun) builtText += runs[j].textRun.content || '';
      }
      var plainText = builtText.replace(/\n$/, '');
      var m = plainText.match(/^AI-(\d+):/);
      if (m && parseInt(m[1], 10) === N) {
        occurrences.push({ pStart: content[i].startIndex, pEnd: content[i].endIndex });
      }
    }

    if (occurrences.length === 0) {
      GasLogger.log('flush.warn', { msg: 'Paragraph not found', globalId: globalId });
      return false;
    }

    occurrences.sort(function(a, b) { return b.pStart - a.pStart; });

    var requests = [];
    for (var oi = 0; oi < occurrences.length; oi++) {
      var pStart = occurrences[oi].pStart;
      var pEnd   = occurrences[oi].pEnd;

      // Delete existing paragraph content, preserving the trailing \n at pEnd-1.
      if (pEnd - 1 > pStart) {
        requests.push({ deleteContentRange: { range: { startIndex: pStart, endIndex: pEnd - 1 } } });
      }

      // Re-insert in reverse order (each inserts at pStart, pushing prior content right).
      // Final paragraph order: [image][AI-N: text][optional person chip][action text (status)]
      if (validEmail) {
        requests.push({ insertText: { text: ' ' + actionText + ' (' + status + ')', location: { index: pStart } } });
        // insertPerson rejects any name field in personProperties — email only
        requests.push({ insertPerson: { personProperties: { email: assigneeEmail }, location: { index: pStart } } });
      } else {
        requests.push({ insertText: { text: actionText + ' (' + status + ')', location: { index: pStart } } });
      }
      requests.push({ insertText: { text: 'AI-' + N + ': ', location: { index: pStart } } });
      requests.push({ insertInlineImage: {
        uri: imgUrl, location: { index: pStart },
        objectSize: { height: { magnitude: 16, unit: 'PT' }, width: { magnitude: 16, unit: 'PT' } }
      }});
      requests.push({ updateTextStyle: {
        range: { startIndex: pStart, endIndex: pStart + 1 + tokenLen },
        textStyle: { link: { url: chipUrl } }, fields: 'link'
      }});
      requests.push(_chipBadgeStyleRequest(pStart + 1, pStart + 1 + tokenLen));
    }

    var batchResp = UrlFetchApp.fetch(baseUrl + docId + ':batchUpdate', {
      method: 'post', muteHttpExceptions: true,
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      payload: JSON.stringify({ requests: requests })
    });

    if (batchResp.getResponseCode() === 200) {
      GasLogger.log('flush.done', { globalId: globalId, status: status, copies: occurrences.length });
      return true;
    }

  GasLogger.log('flush.error', { msg: 'batchUpdate failed: HTTP ' + batchResp.getResponseCode(), body: batchResp.getContentText().substring(0, 300), globalId: globalId });
  return false;
}
