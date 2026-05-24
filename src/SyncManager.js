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

    var doc = DocumentApp.openById(docId);
    var floatingActions = _scanFloatingActions(doc);

    GasLogger.log('sync.scanned', { docId: docId, count: floatingActions.length });

    if (floatingActions.length === 0) {
      GasLogger.log('sync.complete', { docId: docId, anchored: 0, upserted: 0 });
      return;
    }

    var anchoredMap = _buildAnchoredIndexMap(doc);
    var anchorResults = _anchorNewActions(doc, floatingActions, anchoredMap);

    var docUrl   = doc.getUrl();
    var docTitle = doc.getName();
    doc.saveAndClose();

    var upsertResult = _upsertActionRows(anchorResults, docUrl, docTitle);

    GasLogger.log('sync.complete', {
      docId: docId,
      anchored: _countNew(anchorResults),
      upserted: upsertResult.upserted || 0
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
  // UC-B: timestamp stamping — implementation pending.
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
      status:         status
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
      // Paragraph is not a direct body child (e.g. inside a table) — skip
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
// ActionSheet proxy write
// ---------------------------------------------------------------------------

/**
 * Sends the anchored actions to the Web App doPost endpoint for sheet writes.
 *
 * @param {Array}  anchorResults  Output of _anchorNewActions.
 * @param {string} docUrl
 * @param {string} docTitle
 * @returns {{upserted: number}}
 */
function _upsertActionRows(anchorResults, docUrl, docTitle) {
  var props      = PropertiesService.getScriptProperties();
  var webAppUrl  = props.getProperty('WEBAPP_URL');
  var secret     = props.getProperty('WEBAPP_SECRET');

  if (!webAppUrl) {
    GasLogger.log('sync.error', { msg: 'WEBAPP_URL script property not set' });
    return { upserted: 0 };
  }

  var rows = [];
  for (var i = 0; i < anchorResults.length; i++) {
    var a = anchorResults[i];
    rows.push({
      namedRangeId:  a.namedRangeId,
      assigneeEmail: a.assigneeEmail,
      assigneeName:  a.assigneeName,
      actionText:    a.actionText,
      status:        a.status
    });
  }

  // Include the caller's OAuth token so the Web App (access: ANYONE) accepts
  // the request without redirecting to a Google login page.
  var oauthToken = ScriptApp.getOAuthToken();
  var resp = UrlFetchApp.fetch(webAppUrl, {
    method:          'post',
    contentType:     'application/json',
    muteHttpExceptions: true,
    headers:         { 'Authorization': 'Bearer ' + oauthToken },
    payload:         JSON.stringify({
      secret:   secret || '',
      action:   'upsert_action_rows',
      docUrl:   docUrl,
      docTitle: docTitle,
      rows:     rows
    })
  });

  var code = resp.getResponseCode();
  if (code !== 200) {
    GasLogger.log('sync.error', {
      msg:  'doPost upsert failed: HTTP ' + code,
      body: resp.getContentText().substring(0, 200)
    });
    return { upserted: 0 };
  }

  try {
    return JSON.parse(resp.getContentText());
  } catch (e) {
    GasLogger.log('sync.warn', { msg: 'Non-JSON doPost response', body: resp.getContentText().substring(0, 100) });
    return { upserted: 0 };
  }
}
