/**
 * TrackerTable.js
 *
 * UC-C: Insert or refresh the in-doc tracker table.
 *
 * The tracker section comprises:
 *   1. A heading paragraph "=== Tracked Actions ==="
 *   2. A read-only notice paragraph
 *   3. A table: ID | Assignee | Action | Status  (header row + one data row per action)
 *
 * The heading is anchored by a named range ('gactionsheet-tracker-anchor') so refresh
 * can locate it even if surrounding content shifts.
 *
 * Assignee cells require insertPerson (Docs REST API batchUpdate).  Plain-text email
 * addresses do not create person chips.  Strategy: insert the table via DocumentApp
 * with empty assignee cells, save, then fire insertPerson requests per row in reverse
 * body-index order.
 */

var _TRACKER_HEADING       = '=== Tracked Actions ===';
var _TRACKER_ANCHOR_NAME   = 'gactionsheet-tracker-anchor';
var _TRACKER_NOTICE        = (
  'This table is read-only. ' +
  'Edits made directly in these cells are discarded on the next refresh; ' +
  'rendered values are derived from the floating actions and the ActionSheet.'
);
var _TRACKER_COL_HEADERS   = ['ID', 'Assignee', 'Action', 'Status'];

// ---------------------------------------------------------------------------
// Public entry point
// ---------------------------------------------------------------------------

/**
 * Insert or refresh the in-doc tracker table for the given document.
 *
 * @param {string} docId
 */
function insertTrackerTable(docId) {
  if (!docId) {
    GasLogger.log('tracker.error', { msg: 'docId is required' });
    GasLogger.flush();
    return;
  }

  try {
    var doc             = DocumentApp.openById(docId);
    var floatingActions = _scanFloatingActions(doc);
    var anchoredMap     = _buildAnchoredIndexMap(doc);

    var ss        = _openActionSheetSpreadsheet();
    var sheetRows = _readTrackerSheetRows(ss, docId);
    var dataRows  = _buildTrackerDataRows(floatingActions, anchoredMap, sheetRows);

    var insertIndex    = _removeTrackerSection(doc);
    var assigneeEmails = _insertTrackerSection(doc, dataRows, insertIndex);

    doc.saveAndClose();

    if (assigneeEmails.length > 0) {
      _insertTrackerAssigneeChips(docId, assigneeEmails);
    }

    GasLogger.log('tracker.insert.complete', { docId: docId, rowCount: dataRows.length });
  } catch (e) {
    GasLogger.log('tracker.error', { msg: e.message, docId: docId });
    throw e;
  } finally {
    GasLogger.flush();
  }
}

function _openActionSheetSpreadsheet() {
  var activeSpreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  if (activeSpreadsheet) {
    return activeSpreadsheet;
  }

  var props = PropertiesService.getScriptProperties();
  var spreadsheetId = props.getProperty('ACTION_SHEET_ID') || props.getProperty('TEST_SHEET_ID');
  if (!spreadsheetId) {
    throw new Error('ActionSheet spreadsheet is unavailable in this context');
  }

  return SpreadsheetApp.openById(spreadsheetId);
}

// ---------------------------------------------------------------------------
// Data collection
// ---------------------------------------------------------------------------

/**
 * Reads ActionSheet rows for the given document, keyed by namedRangeId.
 * Returns { [namedRangeId]: { id, status } }.
 *
 * @param {Spreadsheet} ss
 * @param {string}      docId
 * @returns {Object}
 */
function _readTrackerSheetRows(ss, docId) {
  var sheet = ss.getSheetByName('Actions');
  if (!sheet || sheet.getLastRow() < 2) return {};

  var numRows  = sheet.getLastRow() - 1;
  var data     = sheet.getRange(2, 1, numRows, SHEET_HEADERS.length).getValues();
  var formulas = sheet.getRange(2, 7, numRows, 1).getFormulas();
  var result   = {};

  for (var i = 0; i < data.length; i++) {
    var formula = formulas[i][0] || '';
    if (formula.indexOf(docId) === -1) continue;
    var nrId = data[i][0];
    if (!nrId) continue;
    result[nrId] = {
      id:     data[i][1],
      status: data[i][5] || 'Open'
    };
  }

  return result;
}

/**
 * Builds the ordered list of data rows for the tracker table.
 * One row per floating action, in body order.
 *
 * @param {Array}  floatingActions  Output of _scanFloatingActions.
 * @param {Object} anchoredMap      Output of _buildAnchoredIndexMap.
 * @param {Object} sheetRows        Output of _readTrackerSheetRows.
 * @returns {Array<{id, assigneeEmail, action, status}>}
 */
function _buildTrackerDataRows(floatingActions, anchoredMap, sheetRows) {
  var rows = [];
  for (var i = 0; i < floatingActions.length; i++) {
    var fa    = floatingActions[i];
    var nrId  = anchoredMap[fa.bodyChildIndex] || '';
    var sheet = sheetRows[nrId] || {};
    rows.push({
      id:            sheet.id     || '',
      assigneeEmail: fa.assigneeEmail || '',
      action:        fa.actionText    || '',
      status:        sheet.status || fa.status || 'Open'
    });
  }
  return rows;
}

// ---------------------------------------------------------------------------
// Section removal
// ---------------------------------------------------------------------------

/**
 * Removes the existing tracker section from the document body.
 * Returns the child index where the heading was (for re-insertion), or -1 if absent.
 *
 * The section is: heading paragraph + zero or more notice paragraphs + one table.
 *
 * @param {Document} doc
 * @returns {number}
 */
function _removeTrackerSection(doc) {
  var body         = doc.getBody();
  var headingIndex = -1;
  var i;

  for (i = 0; i < body.getNumChildren(); i++) {
    var child = body.getChild(i);
    var type  = child.getType();
    if ((type === DocumentApp.ElementType.PARAGRAPH ||
         type === DocumentApp.ElementType.LIST_ITEM) &&
        child.getText().trim() === _TRACKER_HEADING) {
      headingIndex = i;
      break;
    }
  }

  if (headingIndex === -1) return -1;

  // Collect indices: heading + any paragraphs that follow + the table
  var toRemove = [headingIndex];
  for (i = headingIndex + 1; i < body.getNumChildren(); i++) {
    var el  = body.getChild(i);
    var elt = el.getType();
    if (elt === DocumentApp.ElementType.TABLE) {
      toRemove.push(i);
      break;
    }
    if (elt === DocumentApp.ElementType.PARAGRAPH ||
        elt === DocumentApp.ElementType.LIST_ITEM) {
      toRemove.push(i);
    } else {
      break;
    }
  }

  // Remove in reverse order so earlier indices stay valid
  for (var j = toRemove.length - 1; j >= 0; j--) {
    body.removeChild(body.getChild(toRemove[j]));
  }

  return headingIndex;
}

// ---------------------------------------------------------------------------
// Section insertion
// ---------------------------------------------------------------------------

/**
 * Inserts the tracker section (heading + notice + table) at insertIndex
 * (or appended if insertIndex is -1).
 *
 * Returns the ordered list of assignee email addresses for person-chip insertion.
 *
 * @param {Document}  doc
 * @param {Array}     dataRows     Output of _buildTrackerDataRows.
 * @param {number}    insertIndex  Child index returned by _removeTrackerSection.
 * @returns {string[]}
 */
function _insertTrackerSection(doc, dataRows, insertIndex) {
  var body       = doc.getBody();
  var appending  = (insertIndex === -1);

  var headingPara;
  if (appending) {
    headingPara = body.appendParagraph(_TRACKER_HEADING);
    body.appendParagraph(_TRACKER_NOTICE);
  } else {
    headingPara = body.insertParagraph(insertIndex, _TRACKER_HEADING);
    body.insertParagraph(insertIndex + 1, _TRACKER_NOTICE);
  }

  // Build 2D cells array: header row + one data row per action
  var cells = [_TRACKER_COL_HEADERS.slice()];
  for (var i = 0; i < dataRows.length; i++) {
    cells.push([
      String(dataRows[i].id || ''),
      '',   // Assignee: populated with insertPerson after saveAndClose
      dataRows[i].action || '',
      dataRows[i].status || 'Open'
    ]);
  }

  if (appending) {
    body.appendTable(cells);
  } else {
    body.insertTable(insertIndex + 2, cells);
  }

  _setTrackerAnchorNamedRange(doc, headingPara);

  return dataRows.map(function(r) { return r.assigneeEmail || ''; });
}

/**
 * Sets (or replaces) the named range anchor on the heading paragraph.
 *
 * @param {Document}  doc
 * @param {Paragraph} headingPara
 */
function _setTrackerAnchorNamedRange(doc, headingPara) {
  var existing = doc.getNamedRanges(_TRACKER_ANCHOR_NAME);
  for (var i = 0; i < existing.length; i++) {
    existing[i].remove();
  }
  var range = doc.newRange().addElement(headingPara).build();
  doc.addNamedRange(_TRACKER_ANCHOR_NAME, range);
}

// ---------------------------------------------------------------------------
// Assignee person chips (Docs REST API)
// ---------------------------------------------------------------------------

/**
 * Inserts person chips into the Assignee column of the tracker table via
 * the Docs REST API batchUpdate.
 *
 * Strategy:
 *   1. GET the document body content to locate the tracker table.
 *   2. Collect the startIndex of each data row's Assignee cell (column 1, 0-indexed).
 *   3. Fire insertPerson requests in reverse body-index order so earlier
 *      insertions do not shift the indices used by later ones.
 *
 * @param {string}   docId
 * @param {string[]} assigneeEmails  Ordered list matching tracker table data rows.
 */
function _insertTrackerAssigneeChips(docId, assigneeEmails) {
  var token   = ScriptApp.getOAuthToken();
  var baseUrl = 'https://docs.googleapis.com/v1/documents/';

  var getResp = UrlFetchApp.fetch(
    baseUrl + docId + '?fields=body.content',
    { headers: { 'Authorization': 'Bearer ' + token }, muteHttpExceptions: true }
  );
  if (getResp.getResponseCode() !== 200) {
    GasLogger.log('tracker.warn', {
      msg:   'insertPerson GET failed: HTTP ' + getResp.getResponseCode(),
      docId: docId
    });
    return;
  }

  var content = (JSON.parse(getResp.getContentText()).body || {}).content || [];

  // Find tracker table: first TABLE element after the heading paragraph
  var headingFound = false;
  var trackerTable = null;
  for (var i = 0; i < content.length; i++) {
    var elem = content[i];
    if (!headingFound && elem.paragraph) {
      if (_extractParaText(elem.paragraph).trim() === _TRACKER_HEADING) {
        headingFound = true;
      }
    } else if (headingFound && elem.table) {
      trackerTable = elem.table;
      break;
    }
  }

  if (!trackerTable) {
    GasLogger.log('tracker.warn', { msg: 'Tracker table not found in REST response', docId: docId });
    return;
  }

  // Collect Assignee cell startIndex for each data row (skip header row at index 0)
  var cellIndices = [];
  var tableRows   = trackerTable.tableRows || [];
  for (var r = 1; r < tableRows.length; r++) {
    var cells = tableRows[r].tableCells || [];
    if (cells.length < 2) continue;
    var cellContent = cells[1].content || [];  // column 1 = Assignee
    if (cellContent.length > 0 && cellContent[0].paragraph) {
      cellIndices.push(cellContent[0].startIndex);
    } else {
      cellIndices.push(null);
    }
  }

  // Build insertPerson requests in reverse order
  var requests = [];
  for (var k = cellIndices.length - 1; k >= 0; k--) {
    var email = assigneeEmails[k] || '';
    var idx   = cellIndices[k];
    if (!email || idx === null) continue;
    requests.push({
      insertPerson: {
        personProperties: { email: email },
        location:         { index: idx }
      }
    });
  }

  if (requests.length === 0) return;

  var batchResp = UrlFetchApp.fetch(
    baseUrl + docId + ':batchUpdate',
    {
      method:             'post',
      headers:            { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
      payload:            JSON.stringify({ requests: requests }),
      muteHttpExceptions: true
    }
  );
  if (batchResp.getResponseCode() !== 200) {
    GasLogger.log('tracker.warn', {
      msg:  'insertPerson batchUpdate failed: HTTP ' + batchResp.getResponseCode(),
      body: batchResp.getContentText().substring(0, 200)
    });
  }
}

/**
 * Extracts plain text from a Docs REST API paragraph object.
 *
 * @param {object} para  paragraph object from REST API content element
 * @returns {string}
 */
function _extractParaText(para) {
  var text     = '';
  var elements = para.elements || [];
  for (var i = 0; i < elements.length; i++) {
    if (elements[i].textRun) {
      text += (elements[i].textRun.content || '');
    }
  }
  return text;
}
