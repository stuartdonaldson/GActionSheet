/**
 * SyncManager.js
 *
 * UC-A: scan the doc for chip-led checklist items, anchor each with a named
 * range, and upsert rows to the ActionSheet via the Web App proxy (doPost).
 *
 * Detection rule: any BODY paragraph whose first child is a PERSON element.
 * The visual checkbox is not readable (isChecked() returns null) — the chip
 * is the only reliable marker.
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
    var chipActions = _scanChipLedActions(doc);

    GasLogger.log('sync.scanned', { docId: docId, count: chipActions.length });

    if (chipActions.length === 0) {
      GasLogger.log('sync.complete', { docId: docId, anchored: 0, upserted: 0 });
      return;
    }

    var anchoredMap = _buildAnchoredIndexMap(doc);
    var anchorResults = _anchorNewActions(doc, chipActions, anchoredMap);

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
 * Walks the doc body and returns one entry per chip-led paragraph or list item.
 *
 * Both PARAGRAPH and LIST_ITEM elements are scanned — users create chip-led
 * actions in both plain paragraphs and bullet/checklist list items (GAS represents
 * bulleted/checked lists as LIST_ITEM, not PARAGRAPH).
 *
 * @param {GoogleAppsScript.Document.Document} doc
 * @returns {Array<{bodyChildIndex, paragraph, assigneeEmail, assigneeName, actionText, status}>}
 */
function _scanChipLedActions(doc) {
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

    var firstChild = para.getChild(0);
    if (firstChild.getType() !== DocumentApp.ElementType.PERSON) continue;

    var chip          = firstChild.asPerson();
    var assigneeEmail = chip.getEmail() || '';
    var assigneeName  = chip.getName()  || '';

    // Collect text from all children after the chip
    var rawText = '';
    for (var j = 1; j < para.getNumChildren(); j++) {
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
 * For each chip-led action, either records the existing namedRangeId or
 * creates a new named range and records the new ID.
 *
 * @param {GoogleAppsScript.Document.Document} doc
 * @param {Array}  chipActions   Output of _scanChipLedActions.
 * @param {Object} anchoredMap  Output of _buildAnchoredIndexMap.
 * @returns {Array<{namedRangeId, wasNew, assigneeEmail, assigneeName, actionText, status}>}
 */
function _anchorNewActions(doc, chipActions, anchoredMap) {
  var results = [];

  for (var i = 0; i < chipActions.length; i++) {
    var action = chipActions[i];
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
