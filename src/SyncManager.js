/**
 * SyncManager.js
 *
 * UC-A: scan the doc for floating actions, anchor each with a named range,
 * and upsert rows to the ActionSheet via the Web App proxy (doPost).
 *
 * Detection rules (either satisfies):
 *   1. PERSON chip — first child of the paragraph is a PERSON element.
 *   2. Email-at-start — first child is TEXT whose content begins with a
 *      valid email address (word@word.tld).  The assignee name is derived
 *      from the username portion (punctuation → spaces, title-cased).
 *
 * Identity: DocumentApp.Document.addNamedRange() creates a named range that
 * is also visible (and deletable) via the Docs REST API. getId() returns the
 * same namedRangeId stored in the ActionSheet.
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

    var props        = PropertiesService.getScriptProperties();
    var lastSyncStr  = props.getProperty('LAST_SYNC_TIME_' + docId);
    var lastSyncTime = lastSyncStr ? new Date(lastSyncStr) : new Date(0);

    var doc;
    try {
      doc = DocumentApp.openById(docId);
    } catch (openErr) {
      GasLogger.log('sync.warn', { msg: 'Doc not found', docId: docId, err: openErr.message });
      _markDocNotFound(docId);
      return;
    }
    var floatingActions = _scanFloatingActions(doc);

    GasLogger.log('sync.scanned', { docId: docId, count: floatingActions.length });

    if (floatingActions.length === 0) {
      doc.saveAndClose();
      props.setProperty('LAST_SYNC_TIME_' + docId, new Date().toISOString());
      GasLogger.log('sync.complete', { docId: docId, anchored: 0, upserted: 0, updated: 0 });
      return;
    }

    // Normalize missing status tokens BEFORE building the anchor map.
    // setText() on a LIST_ITEM paragraph shifts any named range anchored to it
    // to the next paragraph; creating NRs after normalization avoids the shift.
    _normalizeMissingFloatingActionStatuses(floatingActions);

    var anchoredMap  = _buildAnchoredIndexMap(doc);
    var anchorResults = _anchorNewActions(doc, floatingActions, anchoredMap);

    var docUrl   = doc.getUrl();
    var docTitle = doc.getName();

    // Collect all named range IDs still present in the doc so the WebApp can
    // detect orphaned sheet rows (named range deleted along with its paragraph).
    var allNamedRanges = doc.getNamedRanges();
    var allDocNamedRangeIds = [];
    for (var nri = 0; nri < allNamedRanges.length; nri++) {
      allDocNamedRangeIds.push(allNamedRanges[nri].getId());
    }

    // Keep doc open until sheetWins updates are applied.
    var syncResult = _syncActionRows(anchorResults, docUrl, docTitle, lastSyncTime.toISOString(), docId, allDocNamedRangeIds);

    var sheetWins = syncResult.sheetWins || [];
    for (var i = 0; i < sheetWins.length; i++) {
      _applySheetWinToDoc(doc, sheetWins[i].namedRangeId, sheetWins[i].action, sheetWins[i].status);
    }

    doc.saveAndClose();
    SpreadsheetApp.flush();
    props.setProperty('LAST_SYNC_TIME_' + docId, new Date().toISOString());

    GasLogger.log('sync.complete', {
      docId:    docId,
      anchored: _countNew(anchorResults),
      upserted: syncResult.upserted || 0,
      updated:  syncResult.updated  || 0
    });
  } finally {
    GasLogger.flush();
  }
}

function syncAll() {
  try {
    GasLogger.log('sync.all.complete', {});
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

  // Stamp Date Modified to trigger sync
  var dateModified = new Date();
  WriteGuard.wrap(function () {
    sheet.getRange(row, 9).setValue(dateModified);
  });

  // Sheet→Doc sync: read the edited row and propagate to the floating action
  _syncSheetRowToDoc(sheet, row);
}

/**
 * Propagates a single ActionSheet row edit to the corresponding floating action
 * in the source document via the NamedRangeId.
 *
 * Reads: NamedRangeId (col 1), Action (col 5), Status (col 6), Document URL (col 7)
 * Extracts docId from the Document hyperlink formula.
 * Finds the floating action paragraph by its named range and updates it.
 *
 * @param {Sheet} sheet    The ActionSheet "Actions" tab
 * @param {number} row     1-based row number (guaranteed >= 2)
 */
function _syncSheetRowToDoc(sheet, row) {
  try {
    var rowData = sheet.getRange(row, 1, 1, SHEET_HEADERS.length).getValues()[0];
    var namedRangeId = rowData[0];  // Col 1: NamedRangeId
    var action       = rowData[4];  // Col 5: Action
    var status       = rowData[5];  // Col 6: Status
    // getValues() returns the display text for HYPERLINK formulas; getFormula() returns the raw
    // formula string which contains the URL we need to extract the docId.
    var docFormula   = sheet.getRange(row, 7).getFormula();

    if (!namedRangeId) return; // No anchor — can't sync
    if (!docFormula) return;   // No document link

    // Extract docId from =HYPERLINK("https://docs.google.com/document/d/DOCID/edit", "Title")
    var docIdMatch = docFormula.match(/\/d\/([a-zA-Z0-9_-]+)\//);
    if (!docIdMatch) return;
    var docId = docIdMatch[1];

    // Open the doc and apply the sheet-side edits
    var doc = DocumentApp.openById(docId);
    _applySheetWinToDoc(doc, namedRangeId, action, status);
    doc.saveAndClose();
  } catch (err) {
    GasLogger.log('sync.sheet-to-doc.error', {
      row:    row,
      msg:    err.message
    });
  }
}

// ---------------------------------------------------------------------------
// Scanner
// ---------------------------------------------------------------------------

/**
 * Walks the doc body and returns one entry per floating-action paragraph or
 * list item.  Two detection strategies are tried in order:
 *
 *   1. PERSON chip — first child is a PERSON element.
 *   2. Email-at-start — first child is TEXT beginning with word@word.tld.
 *
 * Both PARAGRAPH and LIST_ITEM body elements are scanned.
 *
 * @param {GoogleAppsScript.Document.Document} doc
 * @returns {Array<{bodyChildIndex, paragraph, assigneeEmail, assigneeName, actionText, status}>}
 */
function _scanFloatingActions(doc) {
  var body    = doc.getBody();
  var n       = body.getNumChildren();
  var actions = [];

  for (var i = 0; i < n; i++) {
    var child     = body.getChild(i);
    var childType = child.getType();
    var isPara     = childType === DocumentApp.ElementType.PARAGRAPH;
    var isListItem = childType === DocumentApp.ElementType.LIST_ITEM;
    if (!isPara && !isListItem) continue;

    var para = isPara ? child.asParagraph() : child.asListItem();
    if (para.getNumChildren() === 0) continue;

    var firstChild    = para.getChild(0);
    var assigneeEmail = '';
    var assigneeName  = '';
    var rawText       = '';
    var textStart     = 1;

    if (firstChild.getType() === DocumentApp.ElementType.PERSON) {
      var chip      = firstChild.asPerson();
      assigneeEmail = chip.getEmail() || '';
      assigneeName  = chip.getName()  || '';
    } else if (firstChild.getType() === DocumentApp.ElementType.TEXT) {
      var leadText   = firstChild.asText().getText();
      var emailMatch = leadText.match(/^([\w.+\-]+@[\w\-]+(?:\.[a-z]{2,})+)\s*/i);
      if (!emailMatch) continue;
      assigneeEmail = emailMatch[1];
      assigneeName  = _nameFromEmail(assigneeEmail);
      rawText       = leadText.slice(emailMatch[0].length);
    } else {
      continue;
    }

    for (var j = textStart; j < para.getNumChildren(); j++) {
      var c = para.getChild(j);
      if (c.getType() === DocumentApp.ElementType.TEXT) {
        rawText += c.asText().getText();
      }
    }
    rawText = rawText.trim();

    // Parse trailing (Status) token — any text inside parens at the end
    var status     = 'Open';
    var actionText = rawText;
    var m = rawText.match(/\(([^)]*)\)\s*$/);
    var hasExplicitStatus = !!m;
    if (m) {
      status     = m[1].trim() || 'Open';
      actionText = rawText.slice(0, rawText.length - m[0].length).trim();
    }

    actions.push({
      bodyChildIndex: i,
      paragraph:      para,
      assigneeEmail:  assigneeEmail,
      assigneeName:   assigneeName,
      actionText:     actionText,
      status:         status,
      hasExplicitStatus: hasExplicitStatus
    });
  }

  return actions;
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
// Named range management
// ---------------------------------------------------------------------------

/**
 * Returns a map of { bodyChildIndex: namedRangeId } for all existing named
 * ranges whose first covered element is a direct body paragraph.
 *
 * @param {GoogleAppsScript.Document.Document} doc
 * @returns {Object}
 */
function _buildAnchoredIndexMap(doc) {
  var body        = doc.getBody();
  var namedRanges = doc.getNamedRanges();
  var map         = {};

  for (var i = 0; i < namedRanges.length; i++) {
    var nr       = namedRanges[i];
    var elements = nr.getRange().getRangeElements();
    if (elements.length === 0) continue;

    var el   = elements[0].getElement();
    var para = null;

    if (el.getType() === DocumentApp.ElementType.PARAGRAPH) {
      para = el.asParagraph();
    } else if (el.getType() === DocumentApp.ElementType.LIST_ITEM) {
      para = el.asListItem();
    } else if (el.getType() === DocumentApp.ElementType.TEXT) {
      var parent = el.getParent();
      if (parent && parent.getType() === DocumentApp.ElementType.PARAGRAPH) {
        para = parent.asParagraph();
      } else if (parent && parent.getType() === DocumentApp.ElementType.LIST_ITEM) {
        para = parent.asListItem();
      }
    }

    if (!para) continue;

    try {
      var idx = body.getChildIndex(para);
      if (idx >= 0) map[idx] = nr.getId();
    } catch (e) {
      // paragraph no longer in body — skip
    }
  }

  return map;
}

/**
 * For each floating action, either records the existing namedRangeId or
 * creates a new named range and records the new ID.
 *
 * @param {GoogleAppsScript.Document.Document} doc
 * @param {Array}  floatingActions  Output of _scanFloatingActions.
 * @param {Object} anchoredMap      Output of _buildAnchoredIndexMap.
 * @returns {Array<{namedRangeId, wasNew, assigneeEmail, assigneeName, actionText, status}>}
 */
function _anchorNewActions(doc, floatingActions, anchoredMap) {
  var results = [];

  for (var i = 0; i < floatingActions.length; i++) {
    var action = floatingActions[i];
    var idx    = action.bodyChildIndex;

    if (anchoredMap[idx]) {
      results.push({
        namedRangeId:  anchoredMap[idx],
        wasNew:        false,
        assigneeEmail: action.assigneeEmail,
        assigneeName:  action.assigneeName,
        actionText:    action.actionText,
        status:        action.status
      });
    } else {
      var range = doc.newRange().addElement(action.paragraph).build();
      var nr    = doc.addNamedRange(
        'gactionsheet-' + Utilities.getUuid(),
        range
      );
      results.push({
        namedRangeId:  nr.getId(),
        wasNew:        true,
        assigneeEmail: action.assigneeEmail,
        assigneeName:  action.assigneeName,
        actionText:    action.actionText,
        status:        action.status
      });
    }
  }

  return results;
}

function _countNew(anchorResults) {
  var count = 0;
  for (var i = 0; i < anchorResults.length; i++) {
    if (anchorResults[i].wasNew) count++;
  }
  return count;
}

// ---------------------------------------------------------------------------
// ActionSheet proxy — bidirectional sync
// ---------------------------------------------------------------------------

/**
 * POSTs the doc state to the Web App for conflict resolution and sheet writes.
 * Returns { upserted, updated, sheetWins: [{ namedRangeId, action, status }] }.
 *
 * @param {Array}  anchorResults       Output of _anchorNewActions.
 * @param {string} docUrl
 * @param {string} docTitle
 * @param {string} lastSyncTimeIso     ISO timestamp of previous sync (or epoch).
 * @param {string} docId               Document ID (for orphan detection).
 * @param {Array}  allDocNamedRangeIds All named range IDs currently in the doc.
 * @returns {{upserted: number, updated: number, sheetWins: Array}}
 */
function _syncActionRows(anchorResults, docUrl, docTitle, lastSyncTimeIso, docId, allDocNamedRangeIds) {
  var props     = PropertiesService.getScriptProperties();
  var webAppUrl = props.getProperty('WEBAPP_URL');
  var secret    = props.getProperty('WEBAPP_SECRET');

  if (!webAppUrl) {
    GasLogger.log('sync.error', { msg: 'WEBAPP_URL script property not set' });
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
      docUrl:             docUrl,
      docTitle:           docTitle,
      docId:              docId              || '',
      lastSyncTime:       lastSyncTimeIso,
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
    return JSON.parse(resp.getContentText());
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
  var props     = PropertiesService.getScriptProperties();
  var webAppUrl = props.getProperty('WEBAPP_URL');
  var secret    = props.getProperty('WEBAPP_SECRET');
  if (!webAppUrl) return;
  var oauthToken = ScriptApp.getOAuthToken();
  UrlFetchApp.fetch(webAppUrl, {
    method:             'post',
    contentType:        'application/json',
    muteHttpExceptions: true,
    headers:            { 'Authorization': 'Bearer ' + oauthToken },
    payload:            JSON.stringify({
      secret: secret || '',
      action: 'mark_doc_not_found',
      docId:  docId
    })
  });
  GasLogger.flush();
}

/**
 * Applies a sheet-wins update to the floating action paragraph in the doc.
 * Finds the paragraph via its named range ID and updates the TEXT child element,
 * preserving any leading email prefix or chip separator space.
 *
 * @param {GoogleAppsScript.Document.Document} doc
 * @param {string} namedRangeId
 * @param {string} newAction
 * @param {string} newStatus
 */
function _applySheetWinToDoc(doc, namedRangeId, newAction, newStatus) {
  var namedRanges = doc.getNamedRanges();
  for (var i = 0; i < namedRanges.length; i++) {
    if (namedRanges[i].getId() !== namedRangeId) continue;
    var elements = namedRanges[i].getRange().getRangeElements();
    if (elements.length === 0) break;
    var el   = elements[0].getElement();
    var type = el.getType();
    var para = null;
    if (type === DocumentApp.ElementType.LIST_ITEM) {
      para = el.asListItem();
    } else if (type === DocumentApp.ElementType.PARAGRAPH) {
      para = el.asParagraph();
    } else if (type === DocumentApp.ElementType.TEXT) {
      var parent = el.getParent();
      var pType  = parent.getType();
      if (pType === DocumentApp.ElementType.LIST_ITEM)  para = parent.asListItem();
      else if (pType === DocumentApp.ElementType.PARAGRAPH) para = parent.asParagraph();
    }
    if (para) _updateParaTextFromSheet(para, newAction, newStatus);
    break;
  }
}

function _normalizeMissingFloatingActionStatuses(floatingActions) {
  for (var i = 0; i < floatingActions.length; i++) {
    var action = floatingActions[i];
    if (action.hasExplicitStatus) {
      continue;
    }
    _updateParaTextFromSheet(action.paragraph, action.actionText, action.status || 'Open');
  }
}

/**
 * Replaces the text content of a floating action paragraph with updated values
 * from the ActionSheet.  Preserves the email prefix (email-led items) or the
 * leading space that follows a person chip (chip-led items).
 *
 * Status is always written explicitly so the floating action text is fully
 * normalized after sync.
 *
 * @param {GoogleAppsScript.Document.Paragraph|ListItem} para
 * @param {string} newAction
 * @param {string} newStatus
 */
function _updateParaTextFromSheet(para, newAction, newStatus) {
  var n = para.getNumChildren();
  for (var i = 0; i < n; i++) {
    var child = para.getChild(i);
    if (child.getType() !== DocumentApp.ElementType.TEXT) continue;
    var textEl  = child.asText();
    var current = textEl.getText();

    var prefix     = '';
    var emailMatch = current.match(/^([\w.+\-]+@[\w\-]+(?:\.[a-z]{2,})+\s+)/i);
    if (emailMatch) {
      prefix = emailMatch[1];
    } else if (current.length > 0 && current.charAt(0) === ' ') {
      prefix = ' ';
    }

    var normalizedStatus = newStatus || 'Open';
    var newContent = newAction + ' (' + normalizedStatus + ')';
    textEl.setText(prefix + newContent);
    return;
  }
}
