/**
 * WorkspaceAddonCard.js
 *
 * Google Workspace add-on: homepage card builder and button/mutation handlers
 * (surface ① in DESIGN.md). Entry point: buildHomepageCard() — registered as
 * homepageTrigger in appsscript.json. Status/delete handlers rewrite the doc
 * via the shared REST flush in SyncManager.js (_flushActionParagraph).
 */

/**
 * @param {object=} eventOrVerificationResult
 * @param {object=} opts
 * @param {boolean=} opts.skipSheetFetch  When true, omit the verify_action_rows HTTP call.
 *   Used after sidebar mutations where the sheet was just patched and is known correct —
 *   avoids a second ~3s WebApp round-trip just to rebuild the card.
 */
function buildHomepageCard(eventOrVerificationResult, opts) {
  var verificationResult = _isVerificationResult(eventOrVerificationResult)
    ? eventOrVerificationResult
    : null;
  var skipSheetFetch = !!(opts && opts.skipSheetFetch);

  try {
    var doc = _resolveActiveDocForRead(DocumentApp.getActiveDocument());
    var card = CardService.newCardBuilder()
      .setHeader(_buildHomepageHeader(doc));

    if (!doc) {
      card.addSection(
        CardService.newCardSection().addWidget(
          CardService.newTextParagraph().setText('Open a Google Doc to use Action Sync.')
        )
      );
    } else {
      var homepageState = _buildHomepageState(doc, verificationResult, skipSheetFetch);
      card
        .addSection(_buildOverviewSection(homepageState))
        .addSection(_buildActionButtonsSection(homepageState))
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
  } catch (e) {
    GasLogger.log('addon.homepage.error', { msg: e.message, stack: e.stack || '' });
    GasLogger.flush();

    return CardService.newCardBuilder()
      .setHeader(
        CardService.newCardHeader()
          .setTitle('Action Sync')
          .setImageUrl('https://stuartdonaldson.github.io/GActionSheet/assets/action-logo-t-128.png')
          .setImageAltText('Action Sync logo')
      )
      .addSection(
        CardService.newCardSection().addWidget(
          CardService.newTextParagraph().setText('Unable to load the document state right now.')
        )
      )
      .addSection(
        CardService.newCardSection().addWidget(
          CardService.newTextParagraph().setText(BUILD_INFO.version)
        )
      )
      .build();
  }
}

function _resolveActiveDocForRead(doc) {
  if (!doc) {
    return null;
  }

  try {
    return DocumentApp.openById(doc.getId());
  } catch (e) {
    GasLogger.log('addon.doc.reopen_failed', { msg: e.message });
    GasLogger.flush();
    return doc;
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

function onSyncNow() {
  var doc = DocumentApp.getActiveDocument();
  if (!doc) {
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('No active document'))
      .build();
  }
  try {
    var trackerPresent = _readTrackerTableState(doc).found;
    syncDocument(doc.getId());
    if (trackerPresent) {
      insertTrackerTable(doc.getId());
    }
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
    var docTitle = _safeGetDocTitle(doc);
    if (docTitle) {
      header.setSubtitle(docTitle);
    }
  }

  return header;
}

function _safeGetDocTitle(doc) {
  try {
    return doc.getName();
  } catch (e) {
    GasLogger.log('addon.header.doc_name_unavailable', { msg: e.message });
    GasLogger.flush();
    return '';
  }
}

function _buildHomepageState(doc, verificationResult, skipSheetFetch) {
  var floatingActions = _collectFloatingActionState(doc);
  var tracker = _readTrackerTableState(doc);
  var sheetRows = [];
  var syncState = 'No actions found';
  var syncMeta = 'Add a floating action and click Sync now.';

  if (!skipSheetFetch) {
    try {
      sheetRows = _fetchSheetRowsForVerification(doc.getUrl());
    } catch (e) {
      syncState = 'Status unavailable';
      syncMeta = 'VerifySync can confirm the current state.';
    }
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
    } else if (skipSheetFetch) {
      // Post-mutation fast path: sheet was just patched, doc is source of truth.
      syncState = 'Tracked';
      syncMeta = floatingActions.length + ' action(s) recorded for this document.';
    } else if (sheetRows.length === floatingActions.length) {
      syncState = 'Tracked';
      syncMeta = sheetRows.length + ' action(s) recorded for this document.';
    } else {
      syncState = 'Review suggested';
      syncMeta = floatingActions.length + ' doc action(s), ' + sheetRows.length + ' sheet row(s).';
    }
  }

  return {
    docName: _safeGetDocTitle(doc),
    floatingActions: floatingActions,
    trackerFound: tracker.found,
    sheetRowCount: skipSheetFetch ? floatingActions.length : sheetRows.length,
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
        .setText('Sync status: ' + homepageState.syncState)
        .setBottomLabel(homepageState.syncMeta)
        .setWrapText(true)
    );
  return section;
}

function _buildActionButtonsSection(homepageState) {
  var buttonSet = CardService.newButtonSet()
    .addButton(
      CardService.newTextButton()
        .setText('Sync now')
        .setTextButtonStyle(CardService.TextButtonStyle.FILLED)
        .setOnClickAction(_buildCardAction('onSyncNow'))
    )
    .addButton(
      CardService.newTextButton()
        .setText('VerifySync')
        .setOnClickAction(_buildCardAction('onVerifySync'))
    );

  if (!homepageState.trackerFound) {
    buttonSet.addButton(
      CardService.newTextButton()
        .setText('Insert tracker')
        .setOnClickAction(_buildCardAction('onInsertTrackerTable'))
    );
  }

  var section = CardService.newCardSection().addWidget(buttonSet);
  if (homepageState.trackerFound) {
    section.addWidget(
      CardService.newTextParagraph().setText('Tracker already present in this document.')
    );
  }

  return section;
}

function _buildActionListSection(homepageState) {
  var header = 'Actions for this document (' + homepageState.floatingActions.length + ')';
  var section = CardService.newCardSection().setHeader(header);

  if (homepageState.floatingActions.length === 0) {
    section.addWidget(
      CardService.newTextParagraph().setText('No detected actions in this document.')
    );
    return section;
  }

  for (var i = 0; i < homepageState.floatingActions.length; i++) {
    var action = homepageState.floatingActions[i];
    var assignee = action.assigneeName || action.assigneeEmail || 'Unassigned';
    var actionId = action.globalId ? parseGlobalId(action.globalId).actionId : '';
    // Compact: AI-N • Assignee • Status on the top label line
    var topParts = [];
    if (actionId) topParts.push(actionId);
    topParts.push(assignee);
    topParts.push(action.status || 'Open');
    var topLabel = topParts.join(' • ');
    var bottomLabel = action.globalId ? '' : 'Needs sync';
    section.addWidget(
      CardService.newDecoratedText()
        .setTopLabel(topLabel)
        .setText(_escapeAddonHtml(action.action || '(blank action)'))
        .setBottomLabel(bottomLabel)
        .setWrapText(true)
    );

    // Per-action mutations — only shown when the action is anchored.
    if (action.globalId) {
      // One ImageButton per status + one delete button, all in a single row.
      var _ICON_BASE = 'https://stuartdonaldson.github.io/GActionSheet/assets/';
      var _STATUS_ICONS = [
        { status: 'Open',        icon: _ICON_BASE + 'status-open.svg',        alt: 'Set Open' },
        { status: 'In Progress', icon: _ICON_BASE + 'status-inprogress.svg',  alt: 'Set In Progress' },
        { status: 'In Review',   icon: _ICON_BASE + 'status-inreview.svg',    alt: 'Set In Review' },
        { status: 'Done',        icon: _ICON_BASE + 'status-done.svg',        alt: 'Set Done' },
        { status: 'Closed',      icon: _ICON_BASE + 'status-closed.svg',      alt: 'Set Closed' }
      ];
      var mutationRow = CardService.newButtonSet();
      for (var si = 0; si < _STATUS_ICONS.length; si++) {
        var sIcon = _STATUS_ICONS[si];
        mutationRow.addButton(
          CardService.newImageButton()
            .setIconUrl(sIcon.icon)
            .setAltText(sIcon.alt)
            .setOnClickAction(
              CardService.newAction()
                .setFunctionName('onSetActionStatus')
                .setParameters({ globalId: action.globalId, newStatus: sIcon.status })
            )
        );
      }
      mutationRow.addButton(
        CardService.newImageButton()
          .setIconUrl(_ICON_BASE + 'action-delete.svg')
          .setAltText('Delete action')
          .setOnClickAction(
            CardService.newAction()
              .setFunctionName('onDeleteAction')
              .setParameters({ globalId: action.globalId })
          )
      );
      section.addWidget(mutationRow);
    }
  }

  return section;
}

function _countMissingAnchors(floatingActions) {
  var count = 0;
  for (var i = 0; i < floatingActions.length; i++) {
    if (!floatingActions[i].globalId) {
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

function _buildCardAction(functionName) {
  var action = CardService.newAction().setFunctionName(functionName);
  if (action.setLoadIndicator && CardService.LoadIndicator) {
    action.setLoadIndicator(CardService.LoadIndicator.SPINNER);
  }
  return action;
}

// ---------------------------------------------------------------------------
// Sidebar mutation functions
// ---------------------------------------------------------------------------

/**
 * Finds a floating action paragraph by its globalId (format: {docId}/AI-{N}).
 * Returns the paragraph/list-item element, or null if not found.
 *
 * @param {GoogleAppsScript.Document.Document} doc
 * @param {string} globalId
 * @returns {GoogleAppsScript.Document.Paragraph|GoogleAppsScript.Document.ListItem|null}
 */
function _findParaByGlobalId(doc, globalId) {
  var parsed = parseGlobalId(globalId);
  if (isNaN(parsed.N)) return null;
  var tokenPrefix = parsed.actionId + ':';
  var body = doc.getBody();
  for (var i = 0; i < body.getNumChildren(); i++) {
    var child = body.getChild(i);
    var t = child.getType();
    if (t !== DocumentApp.ElementType.PARAGRAPH && t !== DocumentApp.ElementType.LIST_ITEM) continue;
    if (child.getText().replace(/\n$/, '').indexOf(tokenPrefix) === 0) return child;
  }
  return null;
}

/**
 * Updates the status of a floating action by globalId and syncs to the
 * ActionSheet.  Uses REST flush to rewrite the paragraph with the new status.
 *
 * Log tag: sidebar.status-set.complete
 *
 * @param {string} globalId  globalId (format: {docId}/AI-{N})
 * @param {string} newStatus
 * @param {string=} docId  Optional — resolved from getActiveDocument() when omitted.
 */
function sidebarSetStatus(globalId, newStatus, docId) {
  var t0 = Date.now();
  if (!docId) {
    var activeDoc = DocumentApp.getActiveDocument();
    docId = activeDoc ? activeDoc.getId() : '';
  }

  var doc = DocumentApp.openById(docId);
  var t1  = Date.now();

  // Scan to get current action state for the flush
  var floatingActions = _scanFloatingActions(doc);
  var currentAction   = null;
  for (var i = 0; i < floatingActions.length; i++) {
    if (floatingActions[i].globalId === globalId) {
      currentAction = floatingActions[i];
      break;
    }
  }

  var hasTracker = currentAction ? _readTrackerTableState(doc).found : false;
  doc.saveAndClose(); // close before REST calls
  var t2 = Date.now();

  if (currentAction) {
    var N     = parseGlobalId(globalId).N;
    var token = ScriptApp.getOAuthToken();
    _flushActionParagraph(docId, token, N, globalId,
      currentAction.actionText, newStatus, currentAction.assigneeEmail, currentAction.assigneeName);
    var t3 = Date.now();

    _patchActionStatus(globalId, newStatus);
    var t4 = Date.now();

    if (hasTracker) insertTrackerTable(docId);
    var t5 = Date.now();

    GasLogger.log('sidebar.status-set.complete', {
      globalId: globalId,
      newStatus:    newStatus,
      hasTracker:   hasTracker,
      ms: {
        openById:       t1 - t0,
        scanAndClose:   t2 - t1,
        restFlush:      t3 - t2,
        patchHttp:      t4 - t3,
        trackerRefresh: t5 - t4,
        total:          t5 - t0
      }
    });
  } else {
    GasLogger.log('sidebar.status-set.warn', { msg: 'Action not found', globalId: globalId });
  }
  GasLogger.flush();
}

/**
 * Deletes a floating action paragraph from the doc and removes the
 * corresponding ActionSheet row.  Complete round-trip before returning.
 *
 * Log tag: sidebar.delete.complete
 *
 * @param {string} globalId  globalId (format: {docId}/AI-{N})
 * @param {string=} docId  Optional — resolved from getActiveDocument() when omitted.
 */
function sidebarDeleteAction(globalId, docId) {
  if (!docId) {
    var activeDoc = DocumentApp.getActiveDocument();
    docId = activeDoc ? activeDoc.getId() : '';
  }
  var doc  = DocumentApp.openById(docId);
  var para = _findParaByGlobalId(doc, globalId);

  var deleted = false;
  if (para) {
    // Guard: append a blank paragraph so the target is never the last element
    // in the body section. GAS throws without this when removing the last paragraph.
    doc.getBody().appendParagraph('');
    para.removeFromParent();
    deleted = true;
  }

  doc.saveAndClose();

  if (deleted) {
    _deleteActionRowFromSheet(globalId);
    GasLogger.log('sidebar.delete.complete', { globalId: globalId });
  } else {
    GasLogger.log('sidebar.delete.warn', { msg: 'Action not found', globalId: globalId });
  }
  GasLogger.flush();
}

/**
 * Calls the Web App proxy to update Status + Date Modified for a single ActionSheet
 * row, and clears any stale 'Dirty' Sync Status flag.  Used by sidebarSetStatus in
 * place of the full syncDocument round-trip.
 */
function _patchActionStatus(globalId, newStatus) {
  var webAppUrl = getWebAppUrl();
  var secret    = PropertiesService.getScriptProperties().getProperty('WEBAPP_SECRET');

  if (!webAppUrl) {
    GasLogger.log('sidebar.patch.error', { msg: 'WEBAPP_URL not set' });
    return;
  }

  var oauthToken = ScriptApp.getOAuthToken();
  var resp = UrlFetchApp.fetch(webAppUrl, {
    method:             'post',
    contentType:        'application/json',
    muteHttpExceptions: true,
    headers:            { 'Authorization': 'Bearer ' + oauthToken },
    payload:            JSON.stringify({
      secret:        secret || '',
      action:        'patch_action_status',
      clientVersion: BUILD_INFO.version,
      globalId:      globalId,
      newStatus:     newStatus
    })
  });

  if (resp.getResponseCode() !== 200) {
    GasLogger.log('sidebar.patch.error', { msg: 'patch_action_status HTTP ' + resp.getResponseCode() });
  }
}

/**
 * Calls the Web App proxy to permanently delete an ActionSheet row by globalId.
 */
function _deleteActionRowFromSheet(globalId) {
  var webAppUrl = getWebAppUrl();
  var secret    = PropertiesService.getScriptProperties().getProperty('WEBAPP_SECRET');

  if (!webAppUrl) {
    GasLogger.log('sidebar.delete.error', { msg: 'WEBAPP_URL not set' });
    return;
  }

  var oauthToken = ScriptApp.getOAuthToken();
  var resp = UrlFetchApp.fetch(webAppUrl, {
    method:             'post',
    contentType:        'application/json',
    muteHttpExceptions: true,
    headers:            { 'Authorization': 'Bearer ' + oauthToken },
    payload:            JSON.stringify({
      secret:        secret || '',
      action:        'delete_action_row',
      clientVersion: BUILD_INFO.version,
      globalId:      globalId
    })
  });

  if (resp.getResponseCode() !== 200) {
    GasLogger.log('sidebar.delete.error', { msg: 'delete_action_row HTTP ' + resp.getResponseCode() });
  }
}

// ---------------------------------------------------------------------------
// Card action handlers for sidebar mutations
// ---------------------------------------------------------------------------

/**
 * Card ImageButton handler: set the action status to the value in
 * e.parameters.newStatus.  No form input required — status is baked into
 * the button's action parameters at render time.
 */
function onSetActionStatus(e) {
  var globalId  = e.parameters.globalId;
  var newStatus = e.parameters.newStatus;

  if (!newStatus) {
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('No status specified'))
      .build();
  }

  try {
    var tA = Date.now();
    sidebarSetStatus(globalId, newStatus);
    var tB = Date.now();
    var card = buildHomepageCard(null, { skipSheetFetch: true });
    var tC = Date.now();
    GasLogger.log('sidebar.status-set.handler', {
      ms: { sidebarSetStatus: tB - tA, buildHomepageCard: tC - tB, total: tC - tA }
    });
    GasLogger.flush();
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('Status set to ' + newStatus))
      .setNavigation(CardService.newNavigation().updateCard(card))
      .build();
  } catch (err) {
    GasLogger.log('addon.setstatus.error', { msg: err.message });
    GasLogger.flush();
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('Set status failed: ' + err.message))
      .build();
  }
}

/**
 * Card button handler: delete the action from doc and ActionSheet.
 * Called with e.parameters.globalId.
 */
function onDeleteAction(e) {
  var globalId = e.parameters.globalId;
  sidebarDeleteAction(globalId);
  return CardService.newActionResponseBuilder()
    .setNotification(CardService.newNotification().setText('Action deleted'))
    .setNavigation(CardService.newNavigation().updateCard(
      buildHomepageCard(null, { skipSheetFetch: true })
    ))
    .build();
}

// ---------------------------------------------------------------------------
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
