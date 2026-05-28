/**
 * VerifySync.js
 *
 * Non-mutating verification for the active document.
 * Compares floating actions in the doc, tracker-table rows when present,
 * and ActionSheet rows for the same document.
 */

var _VERIFY_TRACKER_HEADING = '=== Tracked Actions ===';

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
      matched: 0
    }
  };

  var doc = DocumentApp.openById(docId);
  try {
    var docUrl = doc.getUrl();
    var floatingActions = _collectFloatingActionState(doc);
    result.counts.floating = floatingActions.length;
    _verifyProgress(result, 'Scanned floating actions: ' + floatingActions.length);

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

function _collectFloatingActionState(doc) {
  var floatingActions = _scanFloatingActions(doc);
  var rows = [];

  for (var i = 0; i < floatingActions.length; i++) {
    var action = floatingActions[i];
    rows.push({
      namedRangeId: action.globalId || '',
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
          child.getText().trim() === _VERIFY_TRACKER_HEADING) {
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

function _fetchSheetRowsForVerification(docUrl) {
  var response = _callVerifyWebApp({
    action: 'verify_action_rows',
    docUrl: docUrl
  });
  if (response.error) {
    throw new Error(response.error);
  }
  return response.rows || [];
}

function _callVerifyWebApp(payload) {
  var webAppUrl = getWebAppUrl();
  var secret = PropertiesService.getScriptProperties().getProperty('WEBAPP_SECRET');

  if (!webAppUrl) {
    throw new Error('WEBAPP_URL not set');
  }

  var oauthToken = ScriptApp.getOAuthToken();
  var resp = UrlFetchApp.fetch(webAppUrl, {
    method: 'post',
    contentType: 'application/json',
    muteHttpExceptions: true,
    headers: { Authorization: 'Bearer ' + oauthToken },
    payload: JSON.stringify(_mergeVerifyPayload(payload, { secret: secret || '', clientVersion: BUILD_INFO.version }))
  });

  if (resp.getResponseCode() !== 200) {
    throw new Error('Verify request failed: HTTP ' + resp.getResponseCode());
  }

  try {
    var parsed = JSON.parse(resp.getContentText());
    _logVersionMismatch(parsed, 'verify');
    return parsed;
  } catch (e) {
    throw new Error('Verify request returned non-JSON response');
  }
}

function _mergeVerifyPayload(left, right) {
  var merged = {};
  var key;

  for (key in left) {
    if (Object.prototype.hasOwnProperty.call(left, key)) {
      merged[key] = left[key];
    }
  }

  for (key in right) {
    if (Object.prototype.hasOwnProperty.call(right, key)) {
      merged[key] = right[key];
    }
  }

  return merged;
}

function _compareVerificationState(result, floatingActions, tracker, sheetRows) {
  var floatingByNamedRangeId = {};
  var sheetByNamedRangeId = {};
  var sheetById = {};
  var trackerById = {};
  var i;

  for (i = 0; i < floatingActions.length; i++) {
    var floating = floatingActions[i];
    if (!floating.namedRangeId) {
      _verifyIssue(
        result,
        'Floating action is missing a named-range anchor: ' + _formatActionLabel(floating.action, floating.status)
      );
      continue;
    }
    if (floatingByNamedRangeId[floating.namedRangeId]) {
      _verifyIssue(result, 'Duplicate floating action anchor found: ' + floating.namedRangeId);
      continue;
    }
    if (!floating.hasExplicitStatus) {
      _verifyIssue(
        result,
        'Floating action is missing an explicit status token: ' + _formatActionLabel(floating.action, floating.status)
      );
    }
    floatingByNamedRangeId[floating.namedRangeId] = floating;
  }

  for (i = 0; i < sheetRows.length; i++) {
    var sheetRow = sheetRows[i];
    if (!sheetRow.namedRangeId) {
      _verifyIssue(result, 'ActionSheet row ID ' + (sheetRow.id || '?') + ' is missing NamedRangeId');
      continue;
    }
    if (sheetByNamedRangeId[sheetRow.namedRangeId]) {
      _verifyIssue(result, 'Duplicate ActionSheet NamedRangeId found: ' + sheetRow.namedRangeId);
      continue;
    }
    sheetByNamedRangeId[sheetRow.namedRangeId] = sheetRow;
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

  for (var namedRangeId in floatingByNamedRangeId) {
    if (!Object.prototype.hasOwnProperty.call(floatingByNamedRangeId, namedRangeId)) {
      continue;
    }
    var floatingRow = floatingByNamedRangeId[namedRangeId];
    var matchingSheetRow = sheetByNamedRangeId[namedRangeId];
    if (!matchingSheetRow) {
      _verifyIssue(
        result,
        'Floating action is missing from the ActionSheet: ' + _formatActionLabel(floatingRow.action, floatingRow.status)
      );
      continue;
    }

    if (floatingRow.action !== matchingSheetRow.action) {
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
        if (matchingTrackerRow.action !== matchingSheetRow.action) {
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

  for (var sheetNamedRangeId in sheetByNamedRangeId) {
    if (!Object.prototype.hasOwnProperty.call(sheetByNamedRangeId, sheetNamedRangeId)) {
      continue;
    }
    if (!floatingByNamedRangeId[sheetNamedRangeId]) {
      var extraSheetRow = sheetByNamedRangeId[sheetNamedRangeId];
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