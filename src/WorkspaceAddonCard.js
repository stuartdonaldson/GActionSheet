/**
 * WorkspaceAddonCard.js
 *
 * Google Workspace add-on: homepage card builder and button/mutation handlers
 * (surface ① in DESIGN.md). Entry point: buildHomepageCard() — registered as
 * homepageTrigger in appsscript.json. Status/delete handlers rewrite the doc
 * via the shared REST flush in SyncManager.js (_flushActionParagraph).
 */

// Icon constants are defined in Constants.js (generated — see assets/brand-NUUTS/deploy-brand.sh)

/**
 * @param {object=} opts
 * @param {boolean=} opts.skipSheetFetch  When true, omit the verify_action_rows HTTP call.
 *   Used after sidebar mutations where the sheet was just patched and is known correct —
 *   avoids a second ~3s WebApp round-trip just to rebuild the card.
 */
function buildHomepageCard(opts) {
  var skipSheetFetch = !!(opts && opts.skipSheetFetch);

  try {
    var doc = _resolveActiveDocForRead(DocumentApp.getActiveDocument());

    // [PROBE]
    PROBE_log('sidebar.' + PROBE_docState(doc), { docId: doc ? doc.getId() : '' });
    var teamInfo = _safeGetDocTeamInfo(doc);
    var card = CardService.newCardBuilder();

    card.addSection(_buildTeamSection(teamInfo));
    card.addSection(_buildTopButtonsSection());

    if (!doc) {
      card.addSection(
        CardService.newCardSection().addWidget(
          CardService.newTextParagraph().setText('Open a Google Doc to use Action Sync.')
        )
      );
    } else {
      var homepageState = _buildHomepageState(doc, skipSheetFetch);
      card
        .addSection(_buildOverviewSection(homepageState))
        .addSection(_buildActionListSection(homepageState));
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

// ---------------------------------------------------------------------------
// Top-level navigation — 4 action buttons always visible on the homepage.
// Import and Notify navigate to sub-cards (updateCard); back returns home.
// ---------------------------------------------------------------------------

function _buildTopButtonsSection() {
  return CardService.newCardSection().addWidget(
    CardService.newButtonSet()
      .addButton(
        CardService.newTextButton()
          .setText('Sync')
          .setTextButtonStyle(CardService.TextButtonStyle.FILLED)
          .setOnClickAction(_buildCardAction('onSyncNow'))
      )
      .addButton(
        CardService.newTextButton()
          .setText('Import')
          .setOnClickAction(_buildCardAction('onShowImport'))
      )
      .addButton(
        CardService.newTextButton()
          .setText('Notify')
          .setOnClickAction(_buildCardAction('onShowNotify'))
      )
      .addButton(
        CardService.newTextButton()
          .setText('Insert Tracker')
          .setOnClickAction(_buildCardAction('onInsertTrackerTable'))
      )
  );
}

function onShowImport(e) { // eslint-disable-line no-unused-vars
  var doc = DocumentApp.getActiveDocument();
  var docId = doc ? doc.getId() : '';
  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().updateCard(_buildImportCard(docId, false)))
    .build();
}

function onShowNotify(e) { // eslint-disable-line no-unused-vars
  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().updateCard(_buildNotifyCard()))
    .build();
}

function onImportBack(e) { // eslint-disable-line no-unused-vars
  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().updateCard(buildHomepageCard()))
    .build();
}

function onNotifyBack(e) { // eslint-disable-line no-unused-vars
  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().updateCard(buildHomepageCard()))
    .build();
}

function _buildImportCard(docId, selectAll) {
  var sections = _buildImportTabSection(docId, selectAll);
  var card = CardService.newCardBuilder();
  card.addSection(
    CardService.newCardSection().addWidget(
      CardService.newTextButton()
        .setText('Back')
        .setOnClickAction(_buildCardAction('onImportBack'))
    )
  );
  (Array.isArray(sections) ? sections : [sections]).forEach(function (s) {
    card.addSection(s);
  });
  return card.build();
}

function _buildNotifyCard() {
  return CardService.newCardBuilder()
    .addSection(
      CardService.newCardSection()
        .addWidget(
          CardService.newTextButton()
            .setText('Back')
            .setOnClickAction(_buildCardAction('onNotifyBack'))
        )
        .addWidget(
          CardService.newTextParagraph().setText('Notify — coming soon')
        )
    )
    .build();
}

/**
 * Card action handler for the Import card's "Select all" button (AC-2,
 * GTaskSheet-fgh4). Re-renders the Import card with every checklist item
 * across ALL source-doc groups pre-selected — server-side, so the client
 * never needs to be trusted with the full selection set.
 */
function onImportSelectAll(e) { // eslint-disable-line no-unused-vars
  var doc = DocumentApp.getActiveDocument();
  var docId = doc ? doc.getId() : '';
  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().updateCard(_buildImportCard(docId, true)))
    .build();
}

/**
 * Import tab body — AC-1 read+render (GTaskSheet-eore). Calls
 * list_importable_actions for OPEN team-scoped actions from OTHER documents,
 * then renders one CardSection per source document: a header TextParagraph
 * linking to the document, followed by a CHECK_BOX SelectionInput (one item
 * per action, fieldName 'importSelection::'+doc_id, value=global_id) per the
 * frozen contract (epic-d-import-contract-seams). Also renders the "Select
 * all" / "Import selected" buttons (AC-2, GTaskSheet-fgh4): Select all
 * re-renders this section with selectAll=true so every item across all
 * groups is pre-checked server-side; Import selected submits to _submitImport.
 *
 * @param {string} docId  Active document id, or '' if no doc is open.
 * @param {boolean=} selectAll  When true, every checklist item is rendered pre-checked.
 * @return {Array<CardSection>}
 */
function _buildImportTabSection(docId, selectAll) {
  if (!docId) {
    return [
      CardService.newCardSection().addWidget(
        CardService.newTextParagraph().setText('Open a Google Doc to use Action Sync.')
      )
    ];
  }

  var result = _callWebApp('list_importable_actions', { docId: docId });
  if (!result || result.error) {
    return [
      CardService.newCardSection().addWidget(
        CardService.newTextParagraph().setText('Unable to load importable actions right now.')
      )
    ];
  }

  var rows = result.rows || [];
  if (rows.length === 0) {
    return [
      CardService.newCardSection().addWidget(
        CardService.newTextParagraph().setText('No open team actions to import.')
      )
    ];
  }

  // Group by doc_id, then order groups by doc_name ASC and each group's
  // actions by AI-N ASC — applied here regardless of the API's own ordering
  // (epic-d-import-contract-seams).
  var groups = [];
  var groupsByDocId = {};
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    var group = groupsByDocId[row.doc_id];
    if (!group) {
      group = { docId: row.doc_id, docName: row.doc_name, docUrl: row.doc_url, actions: [] };
      groupsByDocId[row.doc_id] = group;
      groups.push(group);
    }
    group.actions.push(row);
  }

  groups.sort(function (a, b) {
    return a.docName < b.docName ? -1 : (a.docName > b.docName ? 1 : 0);
  });

  var sections = [];
  for (var g = 0; g < groups.length; g++) {
    var grp = groups[g];
    grp.actions.sort(function (a, b) {
      return parseGlobalId(a.global_id).N - parseGlobalId(b.global_id).N;
    });

    var section = CardService.newCardSection().addWidget(
      CardService.newTextParagraph().setText(
        '<a href="' + grp.docUrl + '">' + _escapeAddonHtml(grp.docName) + '</a>'
      )
    );

    var selectionInput = CardService.newSelectionInput()
      .setType(CardService.SelectionInputType.CHECK_BOX)
      .setFieldName('importSelection::' + grp.docId);

    for (var a = 0; a < grp.actions.length; a++) {
      var action = grp.actions[a];
      var n = parseGlobalId(action.global_id).N;
      selectionInput.addItem(
        'AI-' + n + ' · ' + _escapeAddonHtml(action.action_text),
        action.global_id,
        !!selectAll
      );
    }

    section.addWidget(selectionInput);
    sections.push(section);
  }

  sections.push(
    CardService.newCardSection().addWidget(
      CardService.newButtonSet()
        .addButton(
          CardService.newTextButton()
            .setText('Select all')
            .setOnClickAction(_buildCardAction('onImportSelectAll'))
        )
        .addButton(
          CardService.newTextButton()
            .setText('Import selected')
            .setOnClickAction(_buildCardAction('_submitImport'))
        )
    )
  );

  return sections;
}

/**
 * Placeholder Notify tab body (GTaskSheet-0r0s). Business logic lands in EPIC-E.
 */
function _buildNotifyTabSection() {
  return CardService.newCardSection().addWidget(
    CardService.newTextParagraph().setText('Notify — coming soon')
  );
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


/**
 * Renders the team name above the tab bar. Always shown:
 *   - Team + link → "Team: <a href=url>name</a>"
 *   - Team, no link → "Team: name"
 *   - No team → "Team: (none)"
 *
 * @param {{team: string, link: string}} teamInfo
 */
function _buildTeamSection(teamInfo) {
  var team  = teamInfo && teamInfo.team;
  var link  = teamInfo && teamInfo.link;
  var label = team
    ? ('Team: ' + (link ? '<a href="' + link + '">' + team + '</a>' : team))
    : 'Team: (none)';
  return CardService.newCardSection()
    .addWidget(CardService.newTextParagraph().setText(label));
}

/**
 * Reads team name and link for the active doc directly from DocData/TeamData
 * (the authoritative source). Does not rely on the teamScope appProperty cache
 * which is only stamped during sync.
 */
function _safeGetDocTeamInfo(doc) {
  if (!doc) return { team: '', link: '' };
  try {
    var ss     = _openActionSheetSpreadsheet();
    var docRow = _readDocDataRow(ss, doc.getId());
    if (!docRow || !docRow.teamId) return { team: '', link: '' };
    var teamRows = _readTeamDataRows(ss);
    for (var i = 0; i < teamRows.length; i++) {
      if (teamRows[i].teamId === docRow.teamId) {
        return { team: docRow.teamId, link: teamRows[i].teamLink || '' };
      }
    }
    return { team: docRow.teamId, link: '' };
  } catch (e) {
    return { team: '', link: '' };
  }
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

function _buildHomepageState(doc, skipSheetFetch) {
  var floatingActions = _collectFloatingActionState(doc);
  var tracker = _readTrackerTableState(doc);
  var sheetRows = [];
  var syncState = 'No actions found';
  var syncMeta = 'Add a floating action and click Sync.';

  if (!skipSheetFetch) {
    try {
      sheetRows = _fetchSheetRowsForVerification(doc.getUrl());
    } catch (e) {
      syncState = 'Status unavailable';
      syncMeta = 'Status check failed.';
    }
  }

  if (floatingActions.length > 0 && syncState !== 'Status unavailable') {
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
      var _STATUS_ICONS = [
        { status: 'Open',        icon: _ACTION_STATUS_IMAGES['Open'],        alt: 'Set Open' },
        { status: 'In Progress', icon: _ACTION_STATUS_IMAGES['In Progress'], alt: 'Set In Progress' },
        { status: 'In Review',   icon: _ACTION_STATUS_IMAGES['In Review'],   alt: 'Set In Review' },
        { status: 'Done',        icon: _ACTION_STATUS_IMAGES['Done'],        alt: 'Set Done' },
        { status: 'Closed',      icon: _ACTION_STATUS_IMAGES['Closed'],      alt: 'Set Closed' }
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
          .setIconUrl(_ACTION_DELETE_IMAGE)
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
  var trackerHeadingSeen = false;
  var trackerTableSkipped = false;
  for (var i = 0; i < body.getNumChildren(); i++) {
    var child = body.getChild(i);
    var t = child.getType();
    if (t === DocumentApp.ElementType.PARAGRAPH || t === DocumentApp.ElementType.LIST_ITEM) {
      var txt = child.getText().trim();
      if (!trackerHeadingSeen && (txt === _TRACKER_HEADING || txt === _TRACKER_HEADING_OLD)) {
        trackerHeadingSeen = true;
      }
      if (child.getText().replace(/\n$/, '').indexOf(tokenPrefix) === 0) return child;
    } else if (t === DocumentApp.ElementType.TABLE) {
      if (trackerHeadingSeen && !trackerTableSkipped) { trackerTableSkipped = true; continue; }
      var table = child.asTable();
      for (var r = 0; r < table.getNumRows(); r++) {
        var row = table.getRow(r);
        for (var c = 0; c < row.getNumCells(); c++) {
          var cell = row.getCell(c);
          for (var p = 0; p < cell.getNumChildren(); p++) {
            var cp  = cell.getChild(p);
            var cpt = cp.getType();
            var elem = cpt === DocumentApp.ElementType.PARAGRAPH ? cp.asParagraph()
                     : cpt === DocumentApp.ElementType.LIST_ITEM  ? cp.asListItem()
                     : null;
            if (elem && elem.getText().replace(/\n$/, '').indexOf(tokenPrefix) === 0) return elem;
          }
        }
      }
    }
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
      caller:        _getIdentity(),
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
      caller:        _getIdentity(),
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
    var card = buildHomepageCard({ skipSheetFetch: true });
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
      buildHomepageCard({ skipSheetFetch: true })
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
