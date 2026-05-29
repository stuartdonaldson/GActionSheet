/**
 * TrackerTable.js
 *
 * UC-C: Insert or refresh the in-doc tracker table.
 *
 * The tracker section comprises:
 *   1. A heading paragraph "Action Item Summary" (Heading 1; preserved on refresh)
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

var _TRACKER_HEADING       = 'Action Item Summary';
var _TRACKER_HEADING_OLD   = '=== Tracked Actions ===';
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
function insertTrackerTable(docId, options) {
  if (!docId) {
    GasLogger.log('tracker.error', { msg: 'docId is required' });
    GasLogger.flush();
    return;
  }

  var onlyIfExists = options && options.onlyIfExists;

  try {
    var doc             = DocumentApp.openById(docId);
    var floatingActions = _scanFloatingActions(doc);

    var ss        = _openActionSheetSpreadsheet();
    var sheetRows = _readTrackerSheetRows(ss, docId);
    var dataRows  = _buildTrackerDataRows(floatingActions, sheetRows);

    var removed = _removeTrackerSection(doc);

    if (onlyIfExists && removed.index === -1) {
      doc.saveAndClose();
      GasLogger.log('tracker.skip', { msg: 'no existing tracker, onlyIfExists=true', docId: docId });
      GasLogger.flush();
      return;
    }

    var sectionOut = _insertTrackerSection(doc, dataRows, removed.index, removed.headingKept);

    doc.saveAndClose();

    if (sectionOut.assigneeEmails.length > 0) {
      _insertTrackerAssigneeChips(docId, sectionOut.assigneeEmails, sectionOut.assigneeNames);
    }
    if (sectionOut.globalIds.length > 0) {
      _insertTrackerIdLinks(docId, sectionOut.globalIds);
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
 * @param {Object} sheetRows        Output of _readTrackerSheetRows (keyed by globalId).
 * @returns {Array<{id, assigneeEmail, action, status}>}
 */
function _buildTrackerDataRows(floatingActions, sheetRows) {
  var rows = [];
  for (var i = 0; i < floatingActions.length; i++) {
    var fa    = floatingActions[i];
    var sheet = sheetRows[fa.globalId] || {};
    // AI-N is the user-facing ID; globalId is kept for hyperlink generation
    var nParts = fa.globalId ? fa.globalId.split('/AI-') : [];
    var aiN    = nParts.length >= 2 ? 'AI-' + nParts[1] : (sheet.id || '');
    rows.push({
      id:            aiN,
      globalId:      fa.globalId || '',
      assigneeEmail: fa.assigneeEmail || '',
      assigneeName:  fa.assigneeName  || '',
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
  var isNewHeading = false;
  var i;

  for (i = 0; i < body.getNumChildren(); i++) {
    var child = body.getChild(i);
    var type  = child.getType();
    if (type === DocumentApp.ElementType.PARAGRAPH ||
        type === DocumentApp.ElementType.LIST_ITEM) {
      var txt = child.getText().trim();
      if (txt === _TRACKER_HEADING) {
        headingIndex = i;
        isNewHeading = true;
        break;
      }
      if (txt === _TRACKER_HEADING_OLD) {
        headingIndex = i;
        break;
      }
    }
  }

  if (headingIndex === -1) return { index: -1, headingKept: false };

  // For the new heading, preserve it — only remove the notice + table that follow.
  // For the old heading, remove it too so it gets replaced.
  var startRemove = isNewHeading ? headingIndex + 1 : headingIndex;
  var toRemove    = [];
  for (i = startRemove; i < body.getNumChildren(); i++) {
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

  for (var j = toRemove.length - 1; j >= 0; j--) {
    body.removeChild(body.getChild(toRemove[j]));
  }

  return {
    index:       isNewHeading ? headingIndex + 1 : headingIndex,
    headingKept: isNewHeading
  };
}

// ---------------------------------------------------------------------------
// Section insertion
// ---------------------------------------------------------------------------

/**
 * Inserts the tracker section (heading + notice + table) at insertIndex
 * (or appended if insertIndex is -1).
 *
 * Returns { assigneeEmails, globalIds } for the REST API post-insert steps.
 *
 * @param {Document}  doc
 * @param {Array}     dataRows     Output of _buildTrackerDataRows.
 * @param {number}  insertIndex  Child index returned by _removeTrackerSection.
 * @param {boolean} headingKept  True when the heading was preserved (not removed).
 * @returns {{ assigneeEmails: string[], globalIds: string[] }}
 */
function _insertTrackerSection(doc, dataRows, insertIndex, headingKept) {
  var body      = doc.getBody();
  var appending = (insertIndex === -1);

  var headingPara;
  var noticeIdx;
  if (headingKept) {
    // Heading already in place — insert notice immediately after it.
    var noticePara = body.insertParagraph(insertIndex, _TRACKER_NOTICE);
    noticePara.editAsText().setItalic(true).setFontSize(10);
    noticeIdx  = insertIndex;
    headingPara = body.getChild(insertIndex - 1).asParagraph();
  } else if (appending) {
    headingPara = body.appendParagraph(_TRACKER_HEADING);
    headingPara.setHeading(DocumentApp.ParagraphHeading.HEADING1);
    var np = body.appendParagraph(_TRACKER_NOTICE);
    np.editAsText().setItalic(true).setFontSize(10);
    noticeIdx = body.getChildIndex(np);
  } else {
    headingPara = body.insertParagraph(insertIndex, _TRACKER_HEADING);
    headingPara.setHeading(DocumentApp.ParagraphHeading.HEADING1);
    var noticePara2 = body.insertParagraph(insertIndex + 1, _TRACKER_NOTICE);
    noticePara2.editAsText().setItalic(true).setFontSize(10);
    noticeIdx = insertIndex + 1;
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

  var table;
  if (appending) {
    table = body.appendTable(cells);
  } else {
    table = body.insertTable(noticeIdx + 1, cells);
  }

  // Column alignment (ID, Assignee, Status centered; Action left as-is) + bold header row
  var centeredCols = [0, 1, 3];
  var numRows      = table.getNumRows();
  for (var ri = 0; ri < numRows; ri++) {
    var trow = table.getRow(ri);
    for (var ci = 0; ci < centeredCols.length; ci++) {
      var col = centeredCols[ci];
      if (col < trow.getNumCells()) {
        trow.getCell(col).getChild(0).asParagraph()
          .setAlignment(DocumentApp.HorizontalAlignment.CENTER);
      }
    }
    if (ri === 0) {
      for (var hci = 0; hci < trow.getNumCells(); hci++) {
        trow.getCell(hci).editAsText().setBold(true);
      }
    }
  }

  _setTrackerAnchorNamedRange(doc, headingPara);

  return {
    assigneeEmails: dataRows.map(function(r) { return r.assigneeEmail || ''; }),
    assigneeNames:  dataRows.map(function(r) { return r.assigneeName  || ''; }),
    globalIds:      dataRows.map(function(r) { return r.globalId || ''; })
  };
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
 * @param {string[]} assigneeNames   Parallel list of display names (may be empty strings).
 */
function _insertTrackerAssigneeChips(docId, assigneeEmails, assigneeNames) {
  var token   = ScriptApp.getOAuthToken();
  var baseUrl = 'https://docs.googleapis.com/v1/documents/';

  var getResp = UrlFetchApp.fetch(
    baseUrl + docId + '?fields=body.content',
    { headers: { 'Authorization': 'Bearer ' + token }, muteHttpExceptions: true }
  );
  if (getResp.getResponseCode() !== 200) {
    GasLogger.log('tracker.warn', { msg: 'insertPerson GET failed: HTTP ' + getResp.getResponseCode(), docId: docId });
    return;
  }

  var content = (JSON.parse(getResp.getContentText()).body || {}).content || [];

  var headingFound = false;
  var trackerTable = null;
  for (var i = 0; i < content.length; i++) {
    var elem = content[i];
    if (!headingFound && elem.paragraph) {
      var pt = _extractParaText(elem.paragraph).trim();
      if (pt === _TRACKER_HEADING || pt === _TRACKER_HEADING_OLD) headingFound = true;
    } else if (headingFound && elem.table) {
      trackerTable = elem.table;
      break;
    }
  }

  if (!trackerTable) {
    GasLogger.log('tracker.warn', { msg: 'Tracker table not found in REST response', docId: docId });
    return;
  }

  var cellIndices = [];
  var tableRows   = trackerTable.tableRows || [];
  for (var r = 1; r < tableRows.length; r++) {
    var cells = tableRows[r].tableCells || [];
    if (cells.length < 2) continue;
    var cellContent = cells[1].content || [];
    if (cellContent.length > 0 && cellContent[0].paragraph) {
      cellIndices.push(cellContent[0].startIndex);
    } else {
      cellIndices.push(null);
    }
  }

  var requests = [];
  for (var k = cellIndices.length - 1; k >= 0; k--) {
    var email = assigneeEmails[k] || '';
    var idx   = cellIndices[k];
    if (!email || idx === null) continue;
    requests.push({ insertPerson: { personProperties: { email: email }, location: { index: idx } } });
  }

  if (requests.length === 0) return;

  var batchResp = UrlFetchApp.fetch(baseUrl + docId + ':batchUpdate', {
    method: 'post', muteHttpExceptions: true,
    headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
    payload: JSON.stringify({ requests: requests })
  });
  if (batchResp.getResponseCode() !== 200) {
    GasLogger.log('tracker.warn', { msg: 'insertPerson batchUpdate failed: HTTP ' + batchResp.getResponseCode(), body: batchResp.getContentText().substring(0, 200) });
  }
}

function _insertTrackerIdLinks(docId, globalIds) {
  var chipUrlBase = 'https://northlakeuu.org/GActionSheet/action/';
  var token       = ScriptApp.getOAuthToken();
  var baseUrl     = 'https://docs.googleapis.com/v1/documents/';

  var getResp = UrlFetchApp.fetch(
    baseUrl + docId + '?fields=body.content',
    { headers: { 'Authorization': 'Bearer ' + token }, muteHttpExceptions: true }
  );
  if (getResp.getResponseCode() !== 200) {
    GasLogger.log('tracker.warn', { msg: 'insertIdLinks GET failed: HTTP ' + getResp.getResponseCode(), docId: docId });
    return;
  }

  var content = (JSON.parse(getResp.getContentText()).body || {}).content || [];

  var headingFound    = false;
  var trackerTable    = null;
  var tableStartIndex = null;
  for (var i = 0; i < content.length; i++) {
    var elem = content[i];
    if (!headingFound && elem.paragraph) {
      var pt2 = _extractParaText(elem.paragraph).trim();
      if (pt2 === _TRACKER_HEADING || pt2 === _TRACKER_HEADING_OLD) headingFound = true;
    } else if (headingFound && elem.table) {
      trackerTable    = elem.table;
      tableStartIndex = elem.startIndex;
      break;
    }
  }

  if (!trackerTable) {
    GasLogger.log('tracker.warn', { msg: 'Tracker table not found for ID links', docId: docId });
    return;
  }

  var requests = [];
  if (tableStartIndex !== null) {
    var colWidths = [{ col: 0, pt: 54 }, { col: 1, pt: 144 }, { col: 3, pt: 72 }];
    for (var wi = 0; wi < colWidths.length; wi++) {
      requests.push({
        updateTableColumnProperties: {
          tableStartLocation: { index: tableStartIndex },
          columnIndices: [colWidths[wi].col],
          tableColumnProperties: { widthType: 'FIXED_WIDTH', width: { magnitude: colWidths[wi].pt, unit: 'PT' } },
          fields: 'widthType,width'
        }
      });
    }
  }

  var tableRows = trackerTable.tableRows || [];
  for (var r = 1; r < tableRows.length; r++) {
    var cells    = tableRows[r].tableCells || [];
    var globalId = globalIds[r - 1] || '';
    if (!globalId || cells.length < 1) continue;
    var cellContent = cells[0].content || [];
    if (!cellContent.length || !cellContent[0].paragraph) continue;
    var paraElems = cellContent[0].paragraph.elements || [];
    var cellText  = '';
    for (var e2 = 0; e2 < paraElems.length; e2++) {
      if (paraElems[e2].textRun) cellText += paraElems[e2].textRun.content || '';
    }
    cellText = cellText.replace(/\n$/, '');
    if (!cellText) continue;
    var cellStart = cellContent[0].startIndex;
    var chipUrl   = chipUrlBase + globalId;
    requests.push({ updateTextStyle: { range: { startIndex: cellStart, endIndex: cellStart + cellText.length }, textStyle: { link: { url: chipUrl } }, fields: 'link' } });
    requests.push({ updateTextStyle: {
      range: { startIndex: cellStart, endIndex: cellStart + cellText.length },
      textStyle: { bold: true, underline: false,
        foregroundColor: { color: { rgbColor: { red: 0.298, green: 0.114, blue: 0.584 } } },
        backgroundColor: { color: { rgbColor: { red: 1.0,   green: 1.0,   blue: 1.0   } } },
        weightedFontFamily: { fontFamily: 'Comic Sans MS', weight: 700 }
      },
      fields: 'bold,underline,foregroundColor,backgroundColor,weightedFontFamily'
    }});
  }

  if (requests.length === 0) return;

  var batchResp = UrlFetchApp.fetch(baseUrl + docId + ':batchUpdate', {
    method: 'post', muteHttpExceptions: true,
    headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
    payload: JSON.stringify({ requests: requests })
  });
  if (batchResp.getResponseCode() !== 200) {
    GasLogger.log('tracker.warn', { msg: 'insertIdLinks batchUpdate failed: HTTP ' + batchResp.getResponseCode(), body: batchResp.getContentText().substring(0, 200) });
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
