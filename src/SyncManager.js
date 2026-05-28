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
    var assigned = _assignPlaceholderTokens(doc);
    if (assigned > 0) {
      GasLogger.log('sync.assigned', { docId: docId, count: assigned });
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
    var allDocGlobalIds = floatingActions.map(function(a) { return a.globalId; });
    var anchorResults   = floatingActions.map(function(a) {
      return {
        namedRangeId:  a.globalId,
        wasNew:        false,
        assigneeEmail: a.assigneeEmail,
        assigneeName:  a.assigneeName,
        actionText:    a.actionText,
        status:        a.status
      };
    });

    var syncResult = _syncActionRows(anchorResults, docUrl, docTitle, docId, allDocGlobalIds);

    var sheetWins = syncResult.sheetWins || [];
    if (sheetWins.length > 0) {
      var floatingByGlobalId = {};
      for (var fi = 0; fi < floatingActions.length; fi++) {
        floatingByGlobalId[floatingActions[fi].globalId] = floatingActions[fi];
      }
      var docId2 = doc.getId();
      doc.saveAndClose(); // close before REST calls
      var token = ScriptApp.getOAuthToken();
      for (var si = 0; si < sheetWins.length; si++) {
        var win = sheetWins[si];
        var fa  = floatingByGlobalId[win.namedRangeId];
        if (!fa) continue;
        _poc_flushActionParagraph(docId2, token, fa.N, win.namedRangeId,
          win.action, win.status, win.assigneeEmail);
      }
    } else {
      doc.saveAndClose();
    }

    SpreadsheetApp.flush();

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
  try {
    var ss           = SpreadsheetApp.getActiveSpreadsheet();
    var actionsSheet = ss.getSheetByName('Actions');
    if (!actionsSheet) {
      GasLogger.log('sync.all.error', { msg: 'Actions sheet not found' });
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
      var m = formula.match(/\/d\/([a-zA-Z0-9_-]+)\//);
      if (m) docIdSet[m[1]] = true;
    }

    var docIds = Object.keys(docIdSet);
    GasLogger.log('sync.all.start', { docCount: docIds.length });

    for (var j = 0; j < docIds.length; j++) {
      syncDocument(docIds[j]);
    }

    GasLogger.log('sync.all.complete', { docCount: docIds.length });
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
  var dateModified = new Date();
  WriteGuard.wrap(function () {
    sheet.getRange(row, 9).setValue(dateModified);
    sheet.getRange(row, 10).setValue('Dirty');
  });

  _syncSheetRowToDoc(sheet, row);
}

/**
 * Propagates a single ActionSheet row edit to the corresponding floating action
 * in the source document via REST batchUpdate.
 *
 * Reads: NamedRangeId/globalId (col 1), Action (col 5), Status (col 6), Document URL (col 7)
 * Extracts docId from the Document hyperlink formula.
 * Extracts N from the globalId (format: {docId}/AI-{N}).
 *
 * @param {Sheet} sheet    The ActionSheet "Actions" tab
 * @param {number} row     1-based row number (guaranteed >= 2)
 */
function _syncSheetRowToDoc(sheet, row) {
  try {
    var rowData       = sheet.getRange(row, 1, 1, SHEET_HEADERS.length).getValues()[0];
    var namedRangeId  = rowData[0];  // Col 1: globalId (format: {docId}/AI-{N})
    var assigneeEmail = rowData[2];  // Col 3: Assignee Email
    var action        = rowData[4];  // Col 5: Action
    var status        = rowData[5];  // Col 6: Status
    var docFormula    = sheet.getRange(row, 7).getFormula();

    if (!namedRangeId) return;
    if (!docFormula) return;

    var docIdMatch = docFormula.match(/\/d\/([a-zA-Z0-9_-]+)\//);
    if (!docIdMatch) return;
    var docId = docIdMatch[1];

    var parts = namedRangeId.split('/AI-');
    if (parts.length < 2) return;
    var N = parseInt(parts[1], 10);
    if (isNaN(N)) return;

    var token = ScriptApp.getOAuthToken();
    _poc_flushActionParagraph(docId, token, N, namedRangeId, action, status, assigneeEmail);
  } catch (err) {
    GasLogger.log('sync.sheet-to-doc.error', { row: row, msg: err.message });
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

    // Strip leading assignee email from afterToken if present
    var actionText = afterToken;
    var assigneeStrip = afterToken.match(/^([\w.+\-]+@[\w\-]+(?:\.[a-z]{2,})+)\s*/i);
    if (assigneeStrip) actionText = afterToken.slice(assigneeStrip[0].length);

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
      hasExplicitStatus: hasExplicitStatus
    });
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
 * @returns {number} count of placeholders assigned
 */
function _assignPlaceholderTokens(doc) {
  var body = doc.getBody();
  var n    = body.getNumChildren();

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
  var assigned = 0;
  for (var j = 0; j < n; j++) {
    var child2 = body.getChild(j);
    var t2 = child2.getType();
    if (t2 !== DocumentApp.ElementType.PARAGRAPH && t2 !== DocumentApp.ElementType.LIST_ITEM) continue;
    var text = child2.getText().replace(/\n$/, '');
    if (!/^AI:/.test(text)) continue;

    maxN++;
    // Insert '-N' at position 2 (between 'AI' and ':') → 'AI:' becomes 'AI-N:'
    child2.editAsText().insertText(2, '-' + maxN);
    assigned++;
  }

  return assigned;
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
 * Returns { upserted, updated, sheetWins: [{ namedRangeId, action, status, assigneeEmail }] }.
 *
 * @param {Array}  anchorResults       Each element: { namedRangeId (globalId), assigneeEmail, assigneeName, actionText, status }.
 * @param {string} docUrl
 * @param {string} docTitle
 * @param {string} docId               Document ID (for orphan detection).
 * @param {Array}  allDocNamedRangeIds All globalIds currently in the doc.
 * @returns {{upserted: number, updated: number, sheetWins: Array}}
 */
function _syncActionRows(anchorResults, docUrl, docTitle, docId, allDocNamedRangeIds) {
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
      namedRangeId:  a.namedRangeId,
      assigneeEmail: a.assigneeEmail,
      assigneeName:  a.assigneeName,
      actionText:    a.actionText,
      status:        a.status
    });
  }

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
      allDocNamedRangeIds: allDocNamedRangeIds || []
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
 */
function _poc_flushActionParagraph(docId, token, N, globalId, actionText, status, assigneeEmail) {
  var baseUrl = 'https://docs.googleapis.com/v1/documents/';
  var chipUrl = 'https://northlakeuu.org/GActionSheet/action/' + globalId;
  // Docs REST API insertInlineImage does not support SVG — use PNG until PNG status icons exist.
  var imgUrl = 'https://stuartdonaldson.github.io/GActionSheet/assets/action-logo-t-32.png';

  // GET to find paragraph indices. builtText is text-run content only;
  // inline images appear as inlineObjectElement (not textRun) so they are absent.
  // Therefore builtText for [img][AI-N: ][chip] text starts with "AI-N: ".
  var getResp = UrlFetchApp.fetch(baseUrl + docId + '?fields=body.content',
    { headers: { Authorization: 'Bearer ' + token }, muteHttpExceptions: true });
  if (getResp.getResponseCode() !== 200) {
    GasLogger.log('flush.error', { msg: 'GET failed: HTTP ' + getResp.getResponseCode(), globalId: globalId });
    return;
  }

  var content   = (JSON.parse(getResp.getContentText()).body || {}).content || [];
  var tokenStr  = 'AI-' + N + ':';
  var pStart    = null;
  var pEnd      = null;

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
      pStart = content[i].startIndex;
      pEnd   = content[i].endIndex; // includes \n
      break;
    }
  }

  if (pStart === null) {
    GasLogger.log('flush.warn', { msg: 'Paragraph not found', globalId: globalId });
    return;
  }

  var requests = [];

  // 1. Delete paragraph content, preserve \n at pEnd-1
  if (pEnd - 1 > pStart) {
    requests.push({ deleteContentRange: { range: { startIndex: pStart, endIndex: pEnd - 1 } } });
  }

  // Re-insert in reverse order (each inserts at pStart, pushing prior inserts right):
  // Order of final paragraph: [image][AI-N: text][optional person chip][action text (status)]

  // 4. Trailing text (inserted first → pushed rightmost)
  var validEmail = assigneeEmail && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(assigneeEmail);
  if (validEmail) {
    requests.push({ insertText: { text: ' ' + actionText + ' (' + status + ')', location: { index: pStart } } });
    requests.push({ insertPerson: { personProperties: { email: assigneeEmail }, location: { index: pStart } } });
  } else {
    requests.push({ insertText: { text: actionText + ' (' + status + ')', location: { index: pStart } } });
  }

  // 2. AI-N: text (inserted before trailing content)
  requests.push({ insertText: { text: 'AI-' + N + ': ', location: { index: pStart } } });

  // 1. Status image (inserted last → ends up at pStart)
  requests.push({ insertInlineImage: {
    uri: imgUrl, location: { index: pStart },
    objectSize: { height: { magnitude: 16, unit: 'PT' }, width: { magnitude: 16, unit: 'PT' } }
  }});

  // Link: image (1 char at pStart) + AI-N: text (tokenLen chars starting at pStart+1)
  var tokenLen = ('AI-' + N + ': ').length;
  requests.push({ updateTextStyle: {
    range: { startIndex: pStart, endIndex: pStart + 1 + tokenLen },
    textStyle: { link: { url: chipUrl } }, fields: 'link'
  }});

  var batchResp = UrlFetchApp.fetch(baseUrl + docId + ':batchUpdate', {
    method: 'post', muteHttpExceptions: true,
    headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
    payload: JSON.stringify({ requests: requests })
  });

  if (batchResp.getResponseCode() !== 200) {
    GasLogger.log('flush.error', {
      msg:  'batchUpdate failed: HTTP ' + batchResp.getResponseCode(),
      body: batchResp.getContentText().substring(0, 300),
      globalId: globalId
    });
  } else {
    GasLogger.log('flush.done', { globalId: globalId, status: status });
  }
}
