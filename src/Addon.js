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
      var homepageState = _buildHomepageState(doc, verificationResult);
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

function _buildHomepageState(doc, verificationResult) {
  var floatingActions = _collectFloatingActionState(doc);
  var tracker = _readTrackerTableState(doc);
  var sheetRows = [];
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
    docName: _safeGetDocTitle(doc),
    floatingActions: floatingActions,
    trackerFound: tracker.found,
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
        .setOnClickAction(_buildSidebarAction('onSyncNow'))
    )
    .addButton(
      CardService.newTextButton()
        .setText('VerifySync')
        .setOnClickAction(_buildSidebarAction('onVerifySync'))
    );

  if (!homepageState.trackerFound) {
    buttonSet.addButton(
      CardService.newTextButton()
        .setText('Insert tracker')
        .setOnClickAction(_buildSidebarAction('onInsertTrackerTable'))
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
    var anchorState = action.namedRangeId ? 'Anchored' : 'Needs sync';
    section.addWidget(
      CardService.newDecoratedText()
        .setTopLabel(assignee)
        .setText(_escapeAddonHtml(action.action || '(blank action)'))
        .setBottomLabel('Status: ' + (action.status || 'Open') + ' • ' + anchorState)
        .setWrapText(true)
    );

    // Per-action mutations — only shown when the action is anchored.
    if (action.namedRangeId) {
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
                .setParameters({ namedRangeId: action.namedRangeId, newStatus: sIcon.status })
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
              .setParameters({ namedRangeId: action.namedRangeId })
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

// ---------------------------------------------------------------------------
// Sidebar mutation functions
// ---------------------------------------------------------------------------

/**
 * Updates the status of a floating action by namedRangeId and syncs to the
 * ActionSheet.  Complete round-trip: doc + sheet updated before returning.
 *
 * Log tag: sidebar.status-set.complete
 *
 * @param {string} namedRangeId
 * @param {string} newStatus
 * @param {string=} docId  Optional — resolved from getActiveDocument() when omitted.
 */
function sidebarSetStatus(namedRangeId, newStatus, docId) {
  if (!docId) {
    var activeDoc = DocumentApp.getActiveDocument();
    docId = activeDoc ? activeDoc.getId() : '';
  }
  var doc = DocumentApp.openById(docId);

  var namedRanges = doc.getNamedRanges();
  var found = false;
  for (var i = 0; i < namedRanges.length; i++) {
    var nr = namedRanges[i];
    if (nr.getId() !== namedRangeId) continue;

    var elements = nr.getRange().getRangeElements();
    if (elements.length === 0) break;

    var el     = elements[0].getElement();
    var type   = el.getType();
    var para   = null;
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

    if (para) {
      // Read current action text and assignee, then rewrite with the new status.
      var currentAction = _readActionTextFromPara(para);
      _updateParaTextFromSheet(para, currentAction, newStatus, '');
      found = true;
    }
    break;
  }

  doc.saveAndClose();

  if (found) {
    // Targeted sheet update — avoids the full syncDocument round-trip (slow) and the
    // sheetWins revert bug (syncDocument could overwrite the paragraph back to the old
    // status if the row carried a stale 'Dirty' Sync Status from a prior onEdit).
    _patchActionStatus(namedRangeId, newStatus);
    GasLogger.log('sidebar.status-set.complete', { namedRangeId: namedRangeId, newStatus: newStatus });
  } else {
    GasLogger.log('sidebar.status-set.warn', { msg: 'Named range not found', namedRangeId: namedRangeId });
  }
  GasLogger.flush();
}

/**
 * Deletes a floating action (paragraph + named range) from the doc and removes
 * the corresponding ActionSheet row.  Complete round-trip before returning.
 *
 * Log tag: sidebar.delete.complete
 *
 * @param {string} namedRangeId
 * @param {string=} docId  Optional — resolved from getActiveDocument() when omitted.
 */
function sidebarDeleteAction(namedRangeId, docId) {
  if (!docId) {
    var activeDoc = DocumentApp.getActiveDocument();
    docId = activeDoc ? activeDoc.getId() : '';
  }
  var doc = DocumentApp.openById(docId);

  var namedRanges = doc.getNamedRanges();
  var deleted = false;
  for (var i = 0; i < namedRanges.length; i++) {
    var nr = namedRanges[i];
    if (nr.getId() !== namedRangeId) continue;

    var elements = nr.getRange().getRangeElements();
    nr.remove(); // delete the named range first

    if (elements.length > 0) {
      var el     = elements[0].getElement();
      var type   = el.getType();
      var para   = null;
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
      if (para) {
        // Guard: append a blank paragraph so the target is never the last
        // element in the body section. GAS throws "Can't remove the last
        // paragraph in a document section" without this guard.
        doc.getBody().appendParagraph('');
        para.removeFromParent();
      }
    }
    deleted = true;
    break;
  }

  doc.saveAndClose();

  if (deleted) {
    _deleteActionRowFromSheet(namedRangeId);
    GasLogger.log('sidebar.delete.complete', { namedRangeId: namedRangeId });
  } else {
    GasLogger.log('sidebar.delete.warn', { msg: 'Named range not found', namedRangeId: namedRangeId });
  }
  GasLogger.flush();
}

/**
 * Extracts the action text from a floating action paragraph (strips the
 * leading chip/email and the trailing (Status) token).
 */
function _readActionTextFromPara(para) {
  var rawText = '';
  var startIdx = 0;
  var firstChild = para.getNumChildren() > 0 ? para.getChild(0) : null;

  if (firstChild && firstChild.getType() === DocumentApp.ElementType.PERSON) {
    startIdx = 1; // skip the chip
  }

  for (var j = startIdx; j < para.getNumChildren(); j++) {
    var c = para.getChild(j);
    if (c.getType() === DocumentApp.ElementType.TEXT) {
      rawText += c.asText().getText();
    }
  }
  rawText = rawText.trim();

  // Strip leading email prefix for email-led items
  var emailMatch = rawText.match(/^([\w.+\-]+@[\w\-]+(?:\.[a-z]{2,})+)\s+/i);
  if (emailMatch) rawText = rawText.slice(emailMatch[0].length).trim();

  // Strip trailing (Status) token
  var m = rawText.match(/\(([^)]*)\)\s*$/);
  if (m) rawText = rawText.slice(0, rawText.length - m[0].length).trim();

  return rawText;
}

/**
 * Calls the Web App proxy to update Status + Date Modified for a single ActionSheet
 * row, and clears any stale 'Dirty' Sync Status flag.  Used by sidebarSetStatus in
 * place of the full syncDocument round-trip.
 */
function _patchActionStatus(namedRangeId, newStatus) {
  var props     = PropertiesService.getScriptProperties();
  var webAppUrl = props.getProperty('WEBAPP_URL');
  var secret    = props.getProperty('WEBAPP_SECRET');

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
      namedRangeId:  namedRangeId,
      newStatus:     newStatus
    })
  });

  if (resp.getResponseCode() !== 200) {
    GasLogger.log('sidebar.patch.error', { msg: 'patch_action_status HTTP ' + resp.getResponseCode() });
  }
}

/**
 * Calls the Web App proxy to permanently delete an ActionSheet row by namedRangeId.
 */
function _deleteActionRowFromSheet(namedRangeId) {
  var props     = PropertiesService.getScriptProperties();
  var webAppUrl = props.getProperty('WEBAPP_URL');
  var secret    = props.getProperty('WEBAPP_SECRET');

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
      namedRangeId:  namedRangeId
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
  var namedRangeId = e.parameters.namedRangeId;
  var newStatus    = e.parameters.newStatus;

  if (!newStatus) {
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('No status specified'))
      .build();
  }

  try {
    sidebarSetStatus(namedRangeId, newStatus);
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('Status set to ' + newStatus))
      .setNavigation(CardService.newNavigation().updateCard(buildHomepageCard()))
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
 * Called with e.parameters.namedRangeId.
 */
function onDeleteAction(e) {
  var namedRangeId = e.parameters.namedRangeId;
  sidebarDeleteAction(namedRangeId);
  return CardService.newActionResponseBuilder()
    .setNotification(CardService.newNotification().setText('Action deleted'))
    .setNavigation(CardService.newNavigation().updateCard(buildHomepageCard()))
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
