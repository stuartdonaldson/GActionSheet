/**
 * Addon.js
 *
 * Workspace Add-on card builder and button handlers.
 * Entry point: buildHomepageCard() — registered as homepageTrigger in appsscript.json.
 */

function buildHomepageCard(eventOrVerificationResult) {
  var verificationResult = _isVerificationResult(eventOrVerificationResult)
    ? eventOrVerificationResult
    : null;
  var controls = _resolveCardControls(verificationResult ? null : eventOrVerificationResult);
  var doc = DocumentApp.getActiveDocument();
  var card = CardService.newCardBuilder()
    .setHeader(_buildHomepageHeader(doc));

  if (!doc) {
    card.addSection(
      CardService.newCardSection().addWidget(
        CardService.newTextParagraph().setText('Open a Google Doc to use Action Sync.')
      )
    );
  } else {
    var homepageState = _buildHomepageState(doc, verificationResult, controls);
    card
      .addSection(_buildOverviewSection(homepageState))
      .addSection(_buildActionButtonsSection(homepageState))
      .addSection(_buildCardControlsSection(homepageState))
      .addSection(_buildActionListSection(homepageState));
  }

  if (verificationResult) {
    card.addSection(_buildVerificationSection(verificationResult));
  }

  card.addSection(
    CardService.newCardSection().addWidget(
      CardService.newTextParagraph().setText(BUILD_INFO.version)
    )
  );

  return card.build();
}

function onOpenSidebar() {
  var doc = DocumentApp.getActiveDocument();
  if (!doc) {
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('No active document'))
      .build();
  }

  try {
    var template = HtmlService.createTemplateFromFile('Sidebar');
    template.docName = doc.getName();
    template.buildVersion = BUILD_INFO.version;

    DocumentApp.getUi().showSidebar(
      template.evaluate().setTitle('Action Sync')
    );

    GasLogger.log('sidebar.open.complete', { docId: doc.getId() });
    GasLogger.flush();

    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('Sidebar opened'))
      .build();
  } catch (e) {
    GasLogger.log('addon.sidebar.error', { msg: e.message });
    GasLogger.flush();
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('Open Sidebar failed: ' + e.message))
      .build();
  }
}

function onInsertTrackerTable() {
  var doc = DocumentApp.getActiveDocument();
  if (!doc) {
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('No active document'))
      .build();
  }

  try {
    insertTrackerTable(doc.getId());
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('Tracker refreshed'))
      .setNavigation(CardService.newNavigation().updateCard(buildHomepageCard()))
      .build();
  } catch (e) {
    GasLogger.log('addon.tracker.error', { msg: e.message });
    GasLogger.flush();
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('Tracker refresh failed: ' + e.message))
      .build();
  }
}

function onScanCard(e) {
  return CardService.newActionResponseBuilder()
    .setNotification(CardService.newNotification().setText('Card refreshed'))
    .setNavigation(CardService.newNavigation().updateCard(buildHomepageCard(e)))
    .build();
}

function onCardControlsChange(e) {
  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().updateCard(buildHomepageCard(e)))
    .build();
}

function onSyncNow() {
  var doc = DocumentApp.getActiveDocument();
  if (!doc) {
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('No active document'))
      .build();
  }
  try {
    syncDocument(doc.getId());
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('Sync complete'))
      .setNavigation(CardService.newNavigation().updateCard(buildHomepageCard()))
      .build();
  } catch (e) {
    GasLogger.log('addon.sync.error', { msg: e.message });
    GasLogger.flush();
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('Sync failed: ' + e.message))
      .build();
  }
}

function onVerifySync() {
  var doc = DocumentApp.getActiveDocument();
  if (!doc) {
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('No active document'))
      .build();
  }

  try {
    var verificationResult = verifyDocumentSync(doc.getId());
    var message = verificationResult.ok
      ? 'VerifySync complete: no issues found'
      : 'VerifySync complete: ' + verificationResult.issues.length + ' issue(s) found';

    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText(message))
      .setNavigation(CardService.newNavigation().updateCard(buildHomepageCard(verificationResult)))
      .build();
  } catch (e) {
    GasLogger.log('addon.verify.error', { msg: e.message });
    GasLogger.flush();
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('VerifySync failed: ' + e.message))
      .build();
  }
}

function _buildVerificationSection(verificationResult) {
  var section = CardService.newCardSection().setHeader('VerifySync Results');
  var summary = [
    verificationResult.ok ? 'Status: OK' : 'Status: issues found',
    'Floating actions: ' + verificationResult.counts.floating,
    'Tracker rows: ' + verificationResult.counts.tracker,
    'ActionSheet rows: ' + verificationResult.counts.sheet,
    'Matched actions: ' + verificationResult.counts.matched
  ];
  section.addWidget(
    CardService.newTextParagraph().setText('<b>Summary</b><br>' + _htmlLines(summary))
  );

  if (verificationResult.progress && verificationResult.progress.length) {
    section.addWidget(
      CardService.newTextParagraph().setText('<b>Progress</b><br>' + _htmlLines(verificationResult.progress))
    );
  }

  if (verificationResult.issues && verificationResult.issues.length) {
    section.addWidget(
      CardService.newTextParagraph().setText('<b>Findings</b><br>' + _htmlLines(_limitVerificationLines(verificationResult.issues, 20)))
    );
  }

  return section;
}

function _buildHomepageHeader(doc) {
  var header = CardService.newCardHeader()
    .setTitle('Action Sync')
    .setImageUrl('https://stuartdonaldson.github.io/GActionSheet/assets/action-logo-t-128.png')
    .setImageAltText('Action Sync logo');

  if (doc) {
    header.setSubtitle(doc.getName());
  }

  return header;
}

function _buildHomepageState(doc, verificationResult, controls) {
  var floatingActions = _collectFloatingActionState(doc);
  var tracker = _readTrackerTableState(doc);
  var sheetRows = [];
  var trackerState = tracker.found ? 'Tracker table present' : 'No tracker table yet';
  var syncState = 'No actions found';
  var syncMeta = 'Add a floating action and click Sync now.';

  try {
    sheetRows = _fetchSheetRowsForVerification(doc.getUrl());
  } catch (e) {
    syncState = 'Status unavailable';
    syncMeta = 'VerifySync can confirm the current state.';
  }

  if (verificationResult) {
    syncState = verificationResult.ok ? 'In sync' : 'Needs review';
    syncMeta = verificationResult.ok
      ? 'VerifySync found no mismatches across doc, tracker, and ActionSheet.'
      : verificationResult.issues.length + ' VerifySync issue(s) found.';
  } else if (floatingActions.length > 0 && syncState !== 'Status unavailable') {
    var missingAnchors = _countMissingAnchors(floatingActions);
    if (missingAnchors > 0) {
      syncState = 'Needs sync';
      syncMeta = missingAnchors + ' action(s) still need a named-range anchor.';
    } else if (sheetRows.length === floatingActions.length) {
      syncState = 'Tracked';
      syncMeta = sheetRows.length + ' action(s) recorded for this document.';
    } else {
      syncState = 'Review suggested';
      syncMeta = floatingActions.length + ' doc action(s), ' + sheetRows.length + ' sheet row(s).';
    }
  }

  return {
    docName: doc.getName(),
    floatingActions: floatingActions,
    visibleActions: _applyCardControls(floatingActions, controls),
    controls: controls,
    trackerFound: tracker.found,
    trackerState: trackerState,
    sheetRowCount: sheetRows.length,
    syncState: syncState,
    syncMeta: syncMeta,
    statusBreakdown: _summarizeStatuses(floatingActions)
  };
}

function _buildOverviewSection(homepageState) {
  var section = CardService.newCardSection();
  section
    .addWidget(
      CardService.newDecoratedText()
        .setTopLabel('Sync status')
        .setText(homepageState.syncState)
        .setBottomLabel(homepageState.syncMeta)
        .setWrapText(true)
    )
    .addWidget(
      CardService.newDecoratedText()
        .setTopLabel('Tracker')
        .setText(homepageState.trackerState)
        .setBottomLabel(homepageState.statusBreakdown)
        .setWrapText(true)
    );
  return section;
}

function _buildActionButtonsSection(homepageState) {
  var buttonSet = CardService.newButtonSet()
    .addButton(
      CardService.newTextButton()
        .setText('Scan card')
        .setOnClickAction(_buildSidebarAction('onScanCard'))
    )
    .addButton(
      CardService.newTextButton()
        .setText('Sync now')
        .setTextButtonStyle(CardService.TextButtonStyle.FILLED)
        .setOnClickAction(_buildSidebarAction('onSyncNow'))
    )
    .addButton(
      CardService.newTextButton()
        .setText('VerifySync')
        .setOnClickAction(_buildSidebarAction('onVerifySync'))
    )
    .addButton(
      CardService.newTextButton()
        .setText(homepageState.trackerFound ? 'Refresh tracker' : 'Insert tracker')
        .setOnClickAction(_buildSidebarAction('onInsertTrackerTable'))
    );

  return CardService.newCardSection().addWidget(buttonSet);
}

function _buildCardControlsSection(homepageState) {
  var section = CardService.newCardSection();

  section
    .addWidget(
      CardService.newSelectionInput()
        .setType(CardService.SelectionInputType.DROPDOWN)
        .setFieldName('sortBy')
        .setTitle('Sort')
        .addItem('Document order', 'document-order', homepageState.controls.sortBy === 'document-order')
        .addItem('Open first', 'open-first', homepageState.controls.sortBy === 'open-first')
        .addItem('By assignee', 'assignee', homepageState.controls.sortBy === 'assignee')
        .setOnChangeAction(_buildSidebarAction('onCardControlsChange'))
    )
    .addWidget(
      CardService.newSelectionInput()
        .setType(CardService.SelectionInputType.DROPDOWN)
        .setFieldName('filterBy')
        .setTitle('Filter')
        .addItem('All', 'all', homepageState.controls.filterBy === 'all')
        .addItem('Open', 'Open', homepageState.controls.filterBy === 'Open')
        .addItem('In Progress', 'In Progress', homepageState.controls.filterBy === 'In Progress')
        .addItem('Closed', 'Closed', homepageState.controls.filterBy === 'Closed')
        .setOnChangeAction(_buildSidebarAction('onCardControlsChange'))
    );

  return section;
}

function _buildActionListSection(homepageState) {
  var header = 'Actions for this document (' + homepageState.visibleActions.length;
  if (homepageState.visibleActions.length !== homepageState.floatingActions.length) {
    header += ' shown of ' + homepageState.floatingActions.length;
  }
  header += ')';
  var section = CardService.newCardSection().setHeader(header);

  if (homepageState.floatingActions.length === 0) {
    section.addWidget(
      CardService.newTextParagraph().setText('No detected actions in this document.')
    );
    return section;
  }

  if (homepageState.visibleActions.length === 0) {
    section.addWidget(
      CardService.newTextParagraph().setText('No actions match the current filter.')
    );
    return section;
  }

  for (var i = 0; i < homepageState.visibleActions.length; i++) {
    var action = homepageState.visibleActions[i];
    var assignee = action.assigneeName || action.assigneeEmail || 'Unassigned';
    var anchorState = action.namedRangeId ? 'Anchored' : 'Needs sync';
    section.addWidget(
      CardService.newDecoratedText()
        .setTopLabel(assignee)
        .setText(_escapeAddonHtml(action.action || '(blank action)'))
        .setBottomLabel('Status: ' + (action.status || 'Open') + ' • ' + anchorState)
        .setWrapText(true)
    );
  }

  return section;
}

function _countMissingAnchors(floatingActions) {
  var count = 0;
  for (var i = 0; i < floatingActions.length; i++) {
    if (!floatingActions[i].namedRangeId) {
      count++;
    }
  }
  return count;
}

function _summarizeStatuses(floatingActions) {
  if (!floatingActions.length) {
    return 'No actions to summarize.';
  }

  var counts = {};
  for (var i = 0; i < floatingActions.length; i++) {
    var status = floatingActions[i].status || 'Open';
    counts[status] = (counts[status] || 0) + 1;
  }

  var parts = [];
  for (var statusName in counts) {
    if (Object.prototype.hasOwnProperty.call(counts, statusName)) {
      parts.push(statusName + ': ' + counts[statusName]);
    }
  }

  return parts.join(' • ');
}

function _resolveCardControls(event) {
  return {
    sortBy: _readCardInput(event, 'sortBy') || 'document-order',
    filterBy: _readCardInput(event, 'filterBy') || 'all'
  };
}

function _readCardInput(event, fieldName) {
  try {
    return event.commonEventObject.formInputs[fieldName].stringInputs.value[0] || '';
  } catch (e) {
    return '';
  }
}

function _applyCardControls(floatingActions, controls) {
  var filtered = [];
  for (var i = 0; i < floatingActions.length; i++) {
    var action = floatingActions[i];
    if (controls.filterBy !== 'all' && (action.status || 'Open') !== controls.filterBy) {
      continue;
    }
    filtered.push(action);
  }

  filtered.sort(function(left, right) {
    if (controls.sortBy === 'assignee') {
      var leftAssignee = left.assigneeName || left.assigneeEmail || '';
      var rightAssignee = right.assigneeName || right.assigneeEmail || '';
      return leftAssignee.localeCompare(rightAssignee) || left.action.localeCompare(right.action);
    }

    if (controls.sortBy === 'open-first') {
      return _statusSortWeight(left.status) - _statusSortWeight(right.status) || left.bodyChildIndex - right.bodyChildIndex;
    }

    return left.bodyChildIndex - right.bodyChildIndex;
  });

  return filtered;
}

function _statusSortWeight(status) {
  if (status === 'Open') return 0;
  if (status === 'In Progress') return 1;
  if (status === 'Blocked') return 2;
  if (status === 'Closed') return 3;
  return 4;
}

function _limitVerificationLines(lines, maxLines) {
  if (lines.length <= maxLines) {
    return lines;
  }

  var limited = lines.slice(0, maxLines);
  limited.push('... ' + (lines.length - maxLines) + ' more');
  return limited;
}

function _htmlLines(lines) {
  var escaped = [];
  for (var i = 0; i < lines.length; i++) {
    escaped.push(_escapeAddonHtml(lines[i]));
  }
  return escaped.join('<br>');
}

function _escapeAddonHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function _isVerificationResult(value) {
  return !!(
    value &&
    value.counts &&
    typeof value.counts.floating !== 'undefined' &&
    typeof value.counts.tracker !== 'undefined' &&
    typeof value.counts.sheet !== 'undefined' &&
    typeof value.counts.matched !== 'undefined'
  );
}

function _buildSidebarAction(functionName) {
  var action = CardService.newAction().setFunctionName(functionName);
  if (action.setLoadIndicator && CardService.LoadIndicator) {
    action.setLoadIndicator(CardService.LoadIndicator.SPINNER);
  }
  return action;
}

// Smoke-test helpers (retained for diagnostics)

function smokeDocsApi() {
  var docId = DocumentApp.getActiveDocument().getId();
  var url   = 'https://docs.googleapis.com/v1/documents/' + docId;
  var resp  = UrlFetchApp.fetch(url, {
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    muteHttpExceptions: true
  });
  var code = resp.getResponseCode();
  if (code !== 200) throw new Error('Expected 200, got ' + code + ': ' + resp.getContentText());
  return code;
}
