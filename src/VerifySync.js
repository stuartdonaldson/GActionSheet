/**
 * VerifySync.js
 *
 * Non-mutating verification for the active document.
 * Compares floating actions in the doc, tracker-table rows when present,
 * and ActionSheet rows for the same document.
 */

var _VERIFY_TRACKER_HEADING     = 'Action Item Summary';
var _VERIFY_TRACKER_HEADING_OLD = '=== Tracked Actions ===';

function verifyDocumentSync(docId) {
  if (!docId) {
    throw new Error('docId is required');
  }

  var result = {
    ok: true,
    progress: [],
    issues: [],
    counts: {
      floating: 0,
      tracker: 0,
      sheet: 0,
      matched: 0,
      unparseable: 0
    }
  };

  var doc = withGasRetry('VerifySync.verifyDocumentSync:DocumentApp.openById',
    function () { return DocumentApp.openById(docId); });
  try {
    var docUrl = doc.getUrl();
    var unparseableParagraphs = [];
    var floatingActions = _collectFloatingActionState(doc, unparseableParagraphs);
    result.counts.floating = floatingActions.length;
    _verifyProgress(result, 'Scanned floating actions: ' + floatingActions.length);

    // ADR-0027 rule 6 / gts-xvlu: a paragraph that starts a token but never
    // completes the grammar (e.g. the gts-tis pipe-delimited spelling) is
    // reported, not silently dropped from the scan.
    result.counts.unparseable = unparseableParagraphs.length;
    for (var upI = 0; upI < unparseableParagraphs.length; upI++) {
      var up = unparseableParagraphs[upI];
      _verifyIssue(
        result,
        'Paragraph looks like an action but does not parse (body index ' + up.bodyChildIndex + '): ' + up.leadingText
      );
    }

    var tracker = _readTrackerTableState(doc);
    result.counts.tracker = tracker.rows.length;
    _verifyProgress(
      result,
      tracker.found
        ? 'Scanned tracker table rows: ' + tracker.rows.length
        : 'Tracker table not found; skipped tracker-table checks'
    );

    var sheetRows = _fetchSheetRowsForVerification(docUrl);
    result.counts.sheet = sheetRows.length;
    _verifyProgress(result, 'Loaded ActionSheet rows for this document: ' + sheetRows.length);

    _compareVerificationState(result, floatingActions, tracker, sheetRows);
    result.ok = result.issues.length === 0;
    _verifyProgress(
      result,
      result.ok
        ? 'Verification finished with no mismatches'
        : 'Verification finished with ' + result.issues.length + ' mismatch(es)'
    );

    GasLogger.log('verify.complete', {
      docId: docId,
      floatingCount: result.counts.floating,
      trackerCount: result.counts.tracker,
      sheetCount: result.counts.sheet,
      matchedCount: result.counts.matched,
      issueCount: result.issues.length,
      ok: result.ok
    });
    return result;
  } finally {
    GasLogger.flush();
  }
}

function _verifyProgress(result, message) {
  result.progress.push(message);
  GasLogger.log('verify.progress', { msg: message });
}

function _collectFloatingActionState(doc, unparseableOut) {
  var floatingActions = _scanFloatingActions(doc, unparseableOut);
  var rows = [];

  for (var i = 0; i < floatingActions.length; i++) {
    var action = floatingActions[i];
    rows.push({
      globalId: action.globalId || '',
      assigneeEmail: action.assigneeEmail || '',
      assigneeName: action.assigneeName || '',
      action: action.actionText || '',
      status: action.status || 'Open',
      hasExplicitStatus: !!action.hasExplicitStatus
    });
  }

  return rows;
}

function _readTrackerTableState(doc) {
  var body = doc.getBody();
  var headingFound = false;
  var tableFound = false;
  var rows = [];

  for (var i = 0; i < body.getNumChildren(); i++) {
    var child = body.getChild(i);
    var type = child.getType();

    if (!headingFound) {
      if ((type === DocumentApp.ElementType.PARAGRAPH ||
           type === DocumentApp.ElementType.LIST_ITEM) &&
          (child.getText().trim() === _VERIFY_TRACKER_HEADING ||
           child.getText().trim() === _VERIFY_TRACKER_HEADING_OLD)) {
        headingFound = true;
      }
      continue;
    }

    if (type === DocumentApp.ElementType.TABLE) {
      tableFound = true;
      rows = _tableToTrackerRows(child.asTable());
      break;
    }

    if (type === DocumentApp.ElementType.PARAGRAPH || type === DocumentApp.ElementType.LIST_ITEM) {
      continue;
    }

    break;
  }

  return {
    found: headingFound && tableFound,
    rows: rows
  };
}

function _tableToTrackerRows(table) {
  if (!table || table.getNumRows() === 0) {
    return [];
  }

  var headers = [];
  var headerRow = table.getRow(0);
  for (var c = 0; c < headerRow.getNumCells(); c++) {
    headers.push(headerRow.getCell(c).getText().trim());
  }

  var rows = [];
  for (var r = 1; r < table.getNumRows(); r++) {
    var row = table.getRow(r);
    var rowObj = {};
    var hasData = false;
    for (var i = 0; i < headers.length; i++) {
      var value = i < row.getNumCells() ? row.getCell(i).getText().trim() : '';
      rowObj[headers[i]] = value;
      if (value) hasData = true;
    }
    if (!hasData) {
      continue;
    }
    rows.push({
      id: rowObj.ID || '',
      assignee: rowObj.Assignee || '',
      action: rowObj.Action || '',
      status: rowObj.Status || ''
    });
  }

  return rows;
}

/**
 * Calls _verifyActionRowsCore (WebApp.js) directly, in-process, rather than
 * round-tripping through UrlFetchApp to this script's own /exec deployment.
 * That self-call previously took 35-40+s from inside a GAS execution vs.
 * 3-4s for the identical HTTP call issued externally, and was the actual
 * cause of buildHomepageCard blowing its ~44s platform timeout most of the
 * time (gts-8py3) — both callers of this function (buildHomepageCard,
 * verifyDocumentSync) always run inside this same script project, so the
 * HTTP hop was pure overhead, never a real cross-deployment call.
 */
function _fetchSheetRowsForVerification(docUrl) {
  var response = _verifyActionRowsCore({ docUrl: docUrl });
  if (response.error) {
    throw new Error(response.error);
  }
  return response.rows || [];
}

function _compareVerificationState(result, floatingActions, tracker, sheetRows) {
  var floatingByGlobalId = {};
  var sheetByGlobalId    = {};
  var sheetById          = {};
  var trackerById        = {};
  var i;

  for (i = 0; i < floatingActions.length; i++) {
    var floating = floatingActions[i];
    if (!floating.globalId) {
      _verifyIssue(
        result,
        'Floating action is missing a globalId: ' + _formatActionLabel(floating.action, floating.status)
      );
      continue;
    }
    if (floatingByGlobalId[floating.globalId]) {
      _verifyIssue(result, 'Duplicate floating action globalId found: ' + floating.globalId);
      continue;
    }
    if (!floating.hasExplicitStatus) {
      _verifyIssue(
        result,
        'Floating action is missing an explicit status token: ' + _formatActionLabel(floating.action, floating.status)
      );
    }
    floatingByGlobalId[floating.globalId] = floating;
  }

  for (i = 0; i < sheetRows.length; i++) {
    var sheetRow = sheetRows[i];
    if (!sheetRow.globalId) {
      _verifyIssue(result, 'ActionSheet row ID ' + (sheetRow.id || '?') + ' is missing globalId');
      continue;
    }
    if (sheetByGlobalId[sheetRow.globalId]) {
      _verifyIssue(result, 'Duplicate ActionSheet globalId found: ' + sheetRow.globalId);
      continue;
    }
    sheetByGlobalId[sheetRow.globalId] = sheetRow;
    if (sheetRow.id) {
      sheetById[String(sheetRow.id)] = sheetRow;
    }
  }

  if (tracker.found) {
    for (i = 0; i < tracker.rows.length; i++) {
      var trackerRow = tracker.rows[i];
      if (!trackerRow.id) {
        _verifyIssue(result, 'Tracker row is missing ID for action: ' + _formatActionLabel(trackerRow.action, trackerRow.status));
        continue;
      }
      if (trackerById[trackerRow.id]) {
        _verifyIssue(result, 'Duplicate tracker-table ID found: ' + trackerRow.id);
        continue;
      }
      trackerById[trackerRow.id] = trackerRow;
    }
  }

  for (var gId in floatingByGlobalId) {
    if (!Object.prototype.hasOwnProperty.call(floatingByGlobalId, gId)) {
      continue;
    }
    var floatingRow = floatingByGlobalId[gId];
    var matchingSheetRow = sheetByGlobalId[gId];
    if (!matchingSheetRow) {
      _verifyIssue(
        result,
        'Floating action is missing from the ActionSheet: ' + _formatActionLabel(floatingRow.action, floatingRow.status)
      );
      continue;
    }

    // Action text is compared through _normalizeLineEndings on every surface
    // below: it may carry soft-return line breaks (gts-dou2/dr8j), and the doc,
    // tracker-cell, and sheet reads do not all spell that break the same way.
    // Comparing raw would report a permanent, unfixable consistency issue.
    if (_normalizeLineEndings(floatingRow.action) !==
        _normalizeLineEndings(matchingSheetRow.action)) {
      _verifyIssue(
        result,
        'Action text mismatch for ID ' + matchingSheetRow.id + ': doc="' + floatingRow.action + '" sheet="' + matchingSheetRow.action + '"'
      );
    }
    if ((floatingRow.status || 'Open') !== (matchingSheetRow.status || 'Open')) {
      _verifyIssue(
        result,
        'Status mismatch for ID ' + matchingSheetRow.id + ': doc="' + floatingRow.status + '" sheet="' + matchingSheetRow.status + '"'
      );
    }
    if ((floatingRow.assigneeEmail || '') !== (matchingSheetRow.assigneeEmail || '')) {
      _verifyIssue(
        result,
        'Assignee mismatch for ID ' + matchingSheetRow.id + ': doc="' + floatingRow.assigneeEmail + '" sheet="' + matchingSheetRow.assigneeEmail + '"'
      );
    }

    if (tracker.found) {
      var matchingTrackerRow = trackerById[String(matchingSheetRow.id || '')];
      if (!matchingTrackerRow) {
        _verifyIssue(result, 'Tracker table is missing action ID ' + matchingSheetRow.id);
      } else {
        if (_normalizeLineEndings(matchingTrackerRow.action) !==
            _normalizeLineEndings(matchingSheetRow.action)) {
          _verifyIssue(
            result,
            'Tracker action mismatch for ID ' + matchingSheetRow.id + ': tracker="' + matchingTrackerRow.action + '" sheet="' + matchingSheetRow.action + '"'
          );
        }
        if ((matchingTrackerRow.status || 'Open') !== (matchingSheetRow.status || 'Open')) {
          _verifyIssue(
            result,
            'Tracker status mismatch for ID ' + matchingSheetRow.id + ': tracker="' + matchingTrackerRow.status + '" sheet="' + matchingSheetRow.status + '"'
          );
        }
      }
    }

    result.counts.matched++;
  }

  for (var sheetGlobalId in sheetByGlobalId) {
    if (!Object.prototype.hasOwnProperty.call(sheetByGlobalId, sheetGlobalId)) {
      continue;
    }
    if (!floatingByGlobalId[sheetGlobalId]) {
      var extraSheetRow = sheetByGlobalId[sheetGlobalId];
      _verifyIssue(
        result,
        'ActionSheet row ID ' + extraSheetRow.id + ' is not listed in the document: ' + _formatActionLabel(extraSheetRow.action, extraSheetRow.status)
      );
    }
  }

  if (tracker.found) {
    for (var trackerId in trackerById) {
      if (!Object.prototype.hasOwnProperty.call(trackerById, trackerId)) {
        continue;
      }
      if (!sheetById[trackerId]) {
        var extraTrackerRow = trackerById[trackerId];
        _verifyIssue(
          result,
          'Tracker row ID ' + trackerId + ' has no matching ActionSheet row: ' + _formatActionLabel(extraTrackerRow.action, extraTrackerRow.status)
        );
      }
    }
  }
}

function _verifyIssue(result, message) {
  result.issues.push(message);
  GasLogger.log('verify.issue', { msg: message });
}

function _formatActionLabel(action, status) {
  if (!status) {
    return action || '(blank action)';
  }
  return (action || '(blank action)') + ' [' + status + ']';
}