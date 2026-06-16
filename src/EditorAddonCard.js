/**
 * EditorAddonCard.js
 *
 * Google Docs editor add-on — CardService surface (surface ② in DESIGN.md).
 * Registered in appsscript.json under addOns.docs. (The `Card` suffix marks the
 * UI technology: CardService, as opposed to a future `…Html` HtmlService
 * surface — see the naming-conventions note in the toolset-direction staging doc.)
 *
 * Entry points:
 *   createActionTrigger  → @-menu "Create action" card
 *   onLinkPreview        → smart-chip hover preview card
 *
 * Creates the canonical floating-action fragment at the cursor and keeps the
 * ActionSheet in sync via an async time-based queue drain. The REST paragraph
 * flush this surface shares with the sync engine lives in SyncManager.js
 * (_flushActionParagraph); the chip URL base is ACTION_CHIP_URL_BASE (SyncManager.js).
 */

// Icon and status constants are defined in Constants.js (generated — see assets/brand-NUUTS/deploy-brand.sh)
// _ACTION_STATUSES, _ACTION_STATUS_IMAGES, _ACTION_DEFAULT_IMAGE, _ADDON_LOGO_URL available as GAS globals.

// ---------------------------------------------------------------------------
// Entry points
// ---------------------------------------------------------------------------

/**
 * createActionTrigger
 * Triggered when the user selects "Create action" from the Docs @-menu.
 * Registered via appsscript.json addOns.docs.createActionTrigger.
 * Log tag: CREATE_ACTION_TRIGGER
 *
 * @param {GoogleAppsScript.Addons.EventObject} e
 * @returns {GoogleAppsScript.Card_Service.Card}
 */
function createActionTrigger(e) { // eslint-disable-line no-unused-vars
  GasLogger.log('CREATE_ACTION_TRIGGER', { docId: e && e.docs && e.docs.id });
  return _buildCreationCard();
}

/**
 * onLinkPreview
 * Triggered when a user hovers over an action smart-chip link.
 * Registered via appsscript.json addOns.docs.linkPreviewTriggers.
 * Log tag: LINK_PREVIEW
 *
 * @param {GoogleAppsScript.Addons.EventObject} e
 * @returns {GoogleAppsScript.Card_Service.Card}
 */
function onLinkPreview(e) { // eslint-disable-line no-unused-vars
  var url = (e && e.docs && e.docs.matchedUrl && e.docs.matchedUrl.url) || '';
  var _id = _getIdentity();
  GasLogger.log('LINK_PREVIEW', { url: url, version: BUILD_INFO.version, eu: _id.eu, au: _id.au });

  // [PROBE]
  PROBE_log('chipHover.' + PROBE_docState(DocumentApp.getActiveDocument()), {
    matchedUrl: url,
    globalId:   _globalIdFromChipUrl(url)
  });
  try {
    var card = _buildPreviewCard(url);
    GasLogger.flush();
    return card;
  } catch (err) {
    GasLogger.log('LINK_PREVIEW.error', { msg: String(err), eu: _id.eu, au: _id.au });
    GasLogger.flush();
    return _buildMessageCard('Preview error', 'Could not load action preview. Please report this to your administrator.\n\n' + String(err));
  }
}

// ---------------------------------------------------------------------------
// Form submit handler (called by CardService action)
// ---------------------------------------------------------------------------

/**
 * Handles the Create Action card form submission.
 * Reads formInput, writes to ActionSheet via WebApp, inserts chip in doc.
 *
 * @param {GoogleAppsScript.Addons.EventObject} e
 * @returns {GoogleAppsScript.Card_Service.ActionResponse}
 */
function _submitCreateAction(e) {
  try {
    var formInput      = (e && e.formInput) || {};
    var actionText     = (formInput.actionText  || '').trim();
    var assigneeRaw    = (formInput.assignee    || '').trim();
    var status         = formInput.status || 'Open';

    // Parse "Display Name <email>" format produced by the suggestions lookup.
    // Falls back to treating the whole value as an email address.
    var assigneeEmail  = assigneeRaw;
    var assigneeName   = '';
    var nameEmailMatch = assigneeRaw.match(/^(.*?)\s*<([^>]+)>\s*$/);
    if (nameEmailMatch) {
      assigneeName  = nameEmailMatch[1].trim();
      assigneeEmail = nameEmailMatch[2].trim();
    }

    if (!actionText) {
      GasLogger.log('CREATE_ACTION_TRIGGER.validation', { msg: 'actionText required' });
      GasLogger.flush();
      return CardService.newActionResponseBuilder()
        .setNavigation(CardService.newNavigation().updateCard(_buildMessageCard('Required', 'Action text cannot be empty.')))
        .build();
    }

    var doc      = DocumentApp.getActiveDocument();
    var N        = _getNextActionN(doc);
    var globalId = doc.getId() + '/AI-' + N;

    // Insert chip at cursor — doc is source of truth; the sheet row will be
    // created by the next sync (no separate upsert call here to stay within
    // the 30s execution limit).
    // NOTE: CardService.newSmartChipConfig / newRenderAction do NOT exist in the
    // current GAS runtime (confirmed 2026-05-27 — TypeError). The REST approach
    // is the correct insertion method.
    var insertError = _insertActionChip(doc, N, globalId, actionText, assigneeEmail, status, assigneeName || assigneeEmail);

    if (insertError) {
      GasLogger.log('CREATE_ACTION_TRIGGER.error', { msg: 'chip insert failed', err: insertError });
      GasLogger.flush();
      return CardService.newActionResponseBuilder()
        .setNavigation(CardService.newNavigation().updateCard(
          _buildMessageCard('Insert failed', 'Action could not be inserted at the cursor.\n\n' + insertError)
        ))
        .build();
    }

    GasLogger.log('CREATE_ACTION_TRIGGER.done', { globalId: globalId });
    return CardService.newActionResponseBuilder()
      .setNavigation(CardService.newNavigation().updateCard(_buildMessageCard('Action created', 'AI-' + N + ': ' + actionText + '\n\nSync now to record it in the ActionSheet.')))
      .build();
  } catch (err) {
    GasLogger.log('CREATE_ACTION_TRIGGER.error', { msg: String(err), stack: err.stack ? err.stack.substring(0, 300) : '' });
    GasLogger.flush();
    return CardService.newActionResponseBuilder()
      .setNavigation(CardService.newNavigation().updateCard(
        _buildMessageCard('Error', 'Could not create action. Please report this to your administrator.\n\n' + String(err))
      ))
      .build();
  }
}

/**
 * Handles the Import tab's "Import selected" button (AC-2, GTaskSheet-fgh4).
 *
 * Collects the union of e.formInput values for every 'importSelection::'+docId
 * field (AC-1 renders one CHECK_BOX SelectionInput per source-doc group; each
 * item's value is a source globalId). Re-fetches the authoritative rows via
 * list_importable_actions — client-supplied action text is never trusted
 * (ADR-0008) — and inserts each selected action as a NEW floating action at
 * the cursor with a newly assigned sequential AI-N (baseN computed once via
 * _getNextActionN, then incremented locally per epic-d-import-contract-seams
 * #4). After doc inserts succeed, writes the new rows to the ActionSheet
 * (upsert_action_rows) and marks each source row Forwarded (AC-3,
 * GTaskSheet-st24, forward_action_rows).
 *
 * @param {GoogleAppsScript.Addons.EventObject} e
 * @returns {GoogleAppsScript.Card_Service.ActionResponse}
 */
function _submitImport(e) {
  try {
    var selected = _collectImportSelection(e);
    if (selected.length === 0) {
      GasLogger.log('IMPORT_SELECTED.validation', { msg: 'no selection' });
      GasLogger.flush();
      return CardService.newActionResponseBuilder()
        .setNavigation(CardService.newNavigation().updateCard(_buildMessageCard('Nothing selected', 'Select at least one action.')))
        .build();
    }

    var doc    = DocumentApp.getActiveDocument();
    var cursor = doc.getCursor();
    if (!cursor) {
      GasLogger.log('INSERT_CHIP.warn', { msg: 'no cursor' });
      GasLogger.flush();
      return CardService.newActionResponseBuilder()
        .setNavigation(CardService.newNavigation().updateCard(_buildMessageCard('No cursor', 'No cursor position found — click in the document to place your cursor, then try again.')))
        .build();
    }

    var docId = doc.getId();
    var token = ScriptApp.getOAuthToken();

    // Re-fetch authoritative rows — never trust client-supplied action text (ADR-0008).
    var listResult = _callWebApp('list_importable_actions', { docId: docId });
    if (!listResult || listResult.error) {
      GasLogger.log('IMPORT_SELECTED.error', { msg: 'list_importable_actions failed', err: listResult && listResult.error });
      GasLogger.flush();
      return CardService.newActionResponseBuilder()
        .setNavigation(CardService.newNavigation().updateCard(_buildMessageCard('Error', 'Unable to load importable actions right now.')))
        .build();
    }

    var selectedSet = {};
    for (var s = 0; s < selected.length; s++) selectedSet[selected[s]] = true;

    var importRows = (listResult.rows || []).filter(function (row) {
      return selectedSet[row.global_id];
    });

    if (importRows.length === 0) {
      GasLogger.log('IMPORT_SELECTED.validation', { msg: 'selection not found in importable rows' });
      GasLogger.flush();
      return CardService.newActionResponseBuilder()
        .setNavigation(CardService.newNavigation().updateCard(_buildMessageCard('Nothing selected', 'Select at least one action.')))
        .build();
    }

    // Resolve cursorIndex ONCE — multi-insert advances it arithmetically
    // (REST inserts are not seen by DocumentApp mid-run).
    var cursorResult = _resolveCursorIndex(doc, cursor, token);
    if (cursorResult.index === null) {
      GasLogger.log('IMPORT_SELECTED.error', { msg: cursorResult.error, paraText: (cursorResult.paraText || '').slice(0, 60), paraOffset: cursorResult.paraOffset });
      GasLogger.flush();
      return CardService.newActionResponseBuilder()
        .setNavigation(CardService.newNavigation().updateCard(_buildMessageCard('Insert failed', cursorResult.error)))
        .build();
    }

    var result = _importSelectedRows(doc, docId, token, cursorResult.index, importRows);
    GasLogger.flush();
    if (!result.ok) {
      return CardService.newActionResponseBuilder()
        .setNavigation(CardService.newNavigation().updateCard(_buildMessageCard(result.title, result.error)))
        .build();
    }
    return CardService.newActionResponseBuilder()
      .setNavigation(CardService.newNavigation().updateCard(_buildImportCard(doc.getId(), false)))
      .build();
  } catch (err) {
    GasLogger.log('IMPORT_SELECTED.error', { msg: String(err), stack: err.stack ? err.stack.substring(0, 300) : '' });
    GasLogger.flush();
    return CardService.newActionResponseBuilder()
      .setNavigation(CardService.newNavigation().updateCard(
        _buildMessageCard('Error', 'Could not import selected actions. Please report this to your administrator.\n\n' + String(err))
      ))
      .build();
  }
}

/**
 * Collects the union of selected source globalIds across every
 * 'importSelection::'+docId CHECK_BOX field (AC-1 renders one per source-doc
 * group). Reads e.formInputs (array values) when present, falling back to
 * e.formInput's comma-separated string for fields not present in formInputs.
 *
 * @param {GoogleAppsScript.Addons.EventObject} e
 * @returns {Array<string>}  Selected source globalIds, de-duplicated
 */
function _collectImportSelection(e) {
  var formInputs = (e && e.formInputs) || {};
  var formInput  = (e && e.formInput)  || {};
  var seen       = {};
  var selected   = [];

  function add(value) {
    if (value && !seen[value]) {
      seen[value] = true;
      selected.push(value);
    }
  }

  var key;
  for (key in formInputs) {
    if (key.indexOf('importSelection') !== 0) continue;
    var values = (formInputs[key].stringInputs && formInputs[key].stringInputs.value) || [];
    for (var i = 0; i < values.length; i++) add(values[i]);
  }
  for (key in formInput) {
    if (key.indexOf('importSelection') !== 0) continue;
    if (formInputs[key]) continue; // already collected via formInputs
    var parts = (formInput[key] || '').split(',');
    for (var j = 0; j < parts.length; j++) {
      var v = parts[j].trim();
      if (v) add(v);
    }
  }

  return selected;
}

// ---------------------------------------------------------------------------
// Card builders
// ---------------------------------------------------------------------------

/**
 * Builds the "Create action" card shown in the Docs @-menu trigger.
 *
 * @returns {GoogleAppsScript.Card_Service.Card}
 */
function _buildCreationCard() {
  var submitAction = CardService.newAction().setFunctionName('_submitCreateAction');

  var section = CardService.newCardSection()
    .addWidget(
      CardService.newTextInput()
        .setFieldName('actionText')
        .setTitle('Action')
        .setHint('What needs to be done?')
    )
    .addWidget(
      CardService.newTextInput()
        .setFieldName('assignee')
        .setTitle('Assignee (optional)')
        .setHint('name or email')
    )
    .addWidget(
      CardService.newSelectionInput()
        .setType(CardService.SelectionInputType.DROPDOWN)
        .setFieldName('status')
        .setTitle('Status (optional)')
        .addItem('Open',        'Open',        true)
        .addItem('In Progress', 'In Progress', false)
        .addItem('In Review',   'In Review',   false)
        .addItem('Done',        'Done',        false)
        .addItem('Closed',      'Closed',      false)
    )
    .addWidget(
      CardService.newTextButton()
        .setText('Create')
        .setOnClickAction(submitAction)
    );

  return CardService.newCardBuilder()
    .setHeader(
      CardService.newCardHeader()
        .setTitle('New Action')
        .setImageUrl(_ADDON_LOGO_URL)
    )
    .addSection(section)
    .build();
}

/**
 * Extracts the globalId from a chip URL, reconstructing it as {docId}/AI-{N}.
 *
 * Current chip URLs carry docId and ain (e.g. 'AI-3') as separate params
 * (?cmd=preview&docId=<encoded>&ain=<encoded>) — see _buildChipUrl(). Older
 * chips already inserted in live documents carry a single encoded
 * ?c=view&globalId=<docId>/AI-<N> param; that legacy form is still accepted.
 *
 * @param {string} url  The matched chip/action URL.
 * @return {?string} the decoded globalId ({docId}/AI-{N}), or null if the
 *   URL has neither form of the identity params.
 */
function _globalIdFromChipUrl(url) {
  var docIdM = url.match(/[?&]docId=([^&]+)/);
  var ainM   = url.match(/[?&]ain=([^&]+)/);
  if (docIdM && ainM) {
    return decodeURIComponent(docIdM[1]) + '/' + decodeURIComponent(ainM[1]);
  }
  var m = url.match(/[?&]globalId=([^&]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

/**
 * Builds the smart-chip hover preview card for an action URL.
 * Looks up the action in the ActionSheet by globalId.
 *
 * @param {string} url  The matched action URL
 * @returns {GoogleAppsScript.Card_Service.Card}
 */
function _buildPreviewCard(url, statusOverride, docOverride) {
  var globalId  = _globalIdFromChipUrl(url);
  var actionId  = parseGlobalId(globalId).actionId;
  GasLogger.log('PREVIEW_CARD.lookup', { globalId: globalId, actionId: actionId });
  var doc      = docOverride || DocumentApp.getActiveDocument();
  var scanned  = _scanFloatingActions(doc);
  var match    = null;
  for (var fi = 0; fi < scanned.length; fi++) {
    if (scanned[fi].globalId === globalId) { match = scanned[fi]; break; }
  }
  var action = match ? { action: match.actionText, status: statusOverride || match.status, assigneeEmail: match.assigneeEmail, assigneeName: match.assigneeName } : null;
  GasLogger.log('PREVIEW_CARD.result', { found: !!action, action: action ? action.action : null, status: action ? action.status : null });

  var actionText = (action && action.action)        || '';
  var status     = (action && action.status)         || '';
  var assignee   = (action && action.assigneeEmail)  || '';

  // Defensively strip any leading "AI-N: " prefix the sheet may have stored
  if (actionId) {
    var prefixToStrip = actionId + ':';
    if (actionText.indexOf(prefixToStrip) === 0) {
      actionText = actionText.slice(prefixToStrip.length).trim();
    }
  }

  // In link preview cards, the card header title is rendered as a link to the
  // matched URL — AI-N as the title is the clickable identifier at the top.
  var header = CardService.newCardHeader()
    .setTitle( (actionId || 'Action') + ': ' + actionText )
    .setImageUrl(_ADDON_LOGO_URL)
    .setImageStyle(CardService.ImageStyle.SQUARE);

  var section = CardService.newCardSection();

  // Status and assignee
  var assigneeLabel = (status ? status : '') +
    (status && assignee ? ' • ' : '') +
    (assignee ? assignee : '');
  if (assigneeLabel) {
    section.addWidget(
      CardService.newDecoratedText()
        .setTopLabel('Assignee / Status')
        .setText(assigneeLabel)
    );
  }

  if (!actionId && !status && !assignee) {
    section.addWidget(CardService.newTextParagraph().setText('No details available.'));
  }

  // Status icon buttons — one per status, fire directly without an intermediate card
  if (globalId) {
    var _STATUS_ICONS = [
      { status: 'Open',        icon: _ACTION_STATUS_IMAGES['Open'],        alt: 'Set Open' },
      { status: 'In Progress', icon: _ACTION_STATUS_IMAGES['In Progress'], alt: 'Set In Progress' },
      { status: 'In Review',   icon: _ACTION_STATUS_IMAGES['In Review'],   alt: 'Set In Review' },
      { status: 'Done',        icon: _ACTION_STATUS_IMAGES['Done'],        alt: 'Set Done' },
      { status: 'Closed',      icon: _ACTION_STATUS_IMAGES['Closed'],      alt: 'Set Closed' }
    ];
    var statusRow = CardService.newButtonSet();
    for (var si = 0; si < _STATUS_ICONS.length; si++) {
      var sIcon = _STATUS_ICONS[si];
      statusRow.addButton(
        CardService.newImageButton()
          .setIconUrl(sIcon.icon)
          .setAltText(sIcon.alt)
          .setOnClickAction(
            CardService.newAction()
              .setFunctionName('_setStatusFromPreview')
              .setParameters({ url: url, newStatus: sIcon.status })
          )
      );
    }
    section.addWidget(statusRow);
  }

  return CardService.newCardBuilder()
    .setHeader(header)
    .addSection(section)
    .build();
}

// ---------------------------------------------------------------------------
// Preview card status action
// ---------------------------------------------------------------------------

/**
 * Handles a status icon tap directly from the preview card.
 * Updates doc paragraph, refreshes tracker, schedules async sheet update.
 * Log tag: POC_EDIT_ACTION.complete
 *
 * @param {GoogleAppsScript.Addons.EventObject} e
 * @returns {GoogleAppsScript.Card_Service.ActionResponse}
 */
function _setStatusFromPreview(e, docOverride) { // eslint-disable-line no-unused-vars
  var url       = (e && e.parameters && e.parameters.url)       || '';
  var newStatus = (e && e.parameters && e.parameters.newStatus) || 'Open';

  var globalId = _globalIdFromChipUrl(url);
  var N        = parseGlobalId(globalId).N || 0;

  var doc    = docOverride || DocumentApp.getActiveDocument();
  var docId  = doc.getId();
  var token  = ScriptApp.getOAuthToken();
  var hasTracker = _readTrackerTableState(doc).found;

  // Scan the already-open doc directly — avoids a second openById round-trip
  var scanned = _scanFloatingActions(doc);
  var match = null;
  for (var si = 0; si < scanned.length; si++) {
    if (scanned[si].globalId === globalId) { match = scanned[si]; break; }
  }
  var actionText    = (match && match.actionText)    || '';
  var assigneeEmail = (match && match.assigneeEmail) || '';
  var assigneeName  = (match && match.assigneeName)  || '';

  var flushed = _flushActionParagraph(docId, token, N, globalId, actionText, newStatus, assigneeEmail, assigneeName);

  if (!flushed) {
    GasLogger.log('POC_EDIT_ACTION.flush_failed', { globalId: globalId });
    GasLogger.flush();
    return CardService.newActionResponseBuilder()
      .setNavigation(CardService.newNavigation().updateCard(_buildMessageCard('Error', 'Failed to update action in document.')))
      .build();
  }

  _scheduleSheetUpdate({
    docUrl:         doc.getUrl(),
    docTitle:       doc.getName(),
    globalId:       globalId,
    actionText:     actionText,
    assigneeEmail:  assigneeEmail,
    assigneeName:   assigneeName,
    status:         newStatus,
    refreshTracker: hasTracker,
    docId:          docId
  });

  GasLogger.log('POC_EDIT_ACTION.complete', { globalId: globalId, status: newStatus });

  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().updateCard(_buildPreviewCard(url, newStatus, doc)))
    .build();
}

// ---------------------------------------------------------------------------
// Async sheet update via time-based trigger
// ---------------------------------------------------------------------------

/**
 * Enqueues sheet upsert params into the ACTION_SHEET_QUEUE script property (JSON array)
 * under a script lock, then schedules a drain trigger if none is already pending.
 *
 * @param {Object} params  Fields: docUrl, docTitle, globalId, actionText,
 *                         assigneeEmail, assigneeName, status
 */
function _scheduleSheetUpdate(params) {
  var props = PropertiesService.getScriptProperties();
  var lock  = LockService.getScriptLock();
  var queueLength;
  lock.waitLock(5000);
  try {
    var queue = JSON.parse(props.getProperty('ACTION_SHEET_QUEUE') || '[]');
    queue.push(params);
    props.setProperty('ACTION_SHEET_QUEUE', JSON.stringify(queue));
    queueLength = queue.length;
  } finally {
    lock.releaseLock();
  }

  var existing = ScriptApp.getProjectTriggers();
  var hasTrigger = false;
  for (var i = 0; i < existing.length; i++) {
    if (existing[i].getHandlerFunction() === '_processPendingSheetUpdates') {
      hasTrigger = true;
      break;
    }
  }
  if (!hasTrigger) {
    ScriptApp.newTrigger('_processPendingSheetUpdates').timeBased().after(2000).create();
  }
  GasLogger.log('poc.asyncSheet.enqueued', { queueLength: queueLength });
}

/**
 * Time-based trigger handler: atomically drains ACTION_SHEET_QUEUE under a lock,
 * processes the snapshot, then deletes only this trigger instance.
 * Log tag: POC_ASYNC_SHEET.complete
 *
 * @param {Object} e  GAS trigger event — e.triggerUid used for self-cleanup
 */
function _processPendingSheetUpdates(e) { // eslint-disable-line no-unused-vars
  var props = PropertiesService.getScriptProperties();
  var lock  = LockService.getScriptLock();
  var snapshot;
  lock.waitLock(10000);
  try {
    snapshot = JSON.parse(props.getProperty('ACTION_SHEET_QUEUE') || '[]');
    props.setProperty('ACTION_SHEET_QUEUE', '[]');
  } finally {
    lock.releaseLock();
  }

  var trackerDocIds = {};
  for (var i = 0; i < snapshot.length; i++) {
    var p = snapshot[i];
    try {
      _callWebApp('upsert_action_rows', {
        docUrl:   p.docUrl,
        docTitle: p.docTitle,
        rows: [{
          globalId:      p.globalId,
          actionText:    p.actionText,
          assigneeEmail: p.assigneeEmail,
          assigneeName:  p.assigneeName,
          status:        p.status
        }]
      });
    } catch (err) {
      GasLogger.log('poc.asyncSheet.error', { globalId: p.globalId, msg: String(err) });
    }
    if (p.refreshTracker && p.docId) {
      trackerDocIds[p.docId] = true;
    }
  }

  // Refresh each affected doc's tracker table once, after all sheet updates complete
  var trackerDocs = Object.keys(trackerDocIds);
  for (var j = 0; j < trackerDocs.length; j++) {
    try {
      insertTrackerTable(trackerDocs[j]);
    } catch (err) {
      GasLogger.log('poc.asyncTracker.error', { docId: trackerDocs[j], msg: String(err) });
    }
  }

  // Delete only this trigger instance, not all pending instances of the handler
  var triggerUid = e && e.triggerUid;
  if (triggerUid) {
    var triggers = ScriptApp.getProjectTriggers();
    for (var j = 0; j < triggers.length; j++) {
      if (triggers[j].getUniqueId() === triggerUid) {
        ScriptApp.deleteTrigger(triggers[j]);
        break;
      }
    }
  }

  GasLogger.log('POC_ASYNC_SHEET.complete', { processed: snapshot.length });
  GasLogger.flush();
}

/**
 * Builds a minimal single-message card (used for success/error feedback in
 * createActionTrigger context, where setNotification is disallowed).
 *
 * @param {string} title
 * @param {string} message
 * @returns {GoogleAppsScript.Card_Service.Card}
 */
function _buildMessageCard(title, message) {
  return CardService.newCardBuilder()
    .setHeader(CardService.newCardHeader().setTitle(title)
      .setImageUrl(_ADDON_LOGO_URL))
    .addSection(CardService.newCardSection()
      .addWidget(CardService.newTextParagraph().setText(message)))
    .build();
}

// ---------------------------------------------------------------------------
// Doc insertion
// ---------------------------------------------------------------------------

/**
 * Scans the doc body for the highest existing AI-N: token and returns N+1.
 * Returns 1 if no AI-N: tokens are present.
 *
 * @param {GoogleAppsScript.Document.Document} doc
 * @returns {number}
 */
function _getNextActionN(doc) {
  var found = _collectTokenParagraphs(doc.getBody());
  var maxN  = 0;
  for (var i = 0; i < found.numbered.length; i++) maxN = Math.max(maxN, found.numbered[i]);
  return maxN + 1;
}

/**
 * Inserts the canonical floating-action fragment at the cursor position via
 * the Docs REST API (single batchUpdate):
 *
 *   [status image, linked]  [AI-N: text, linked]  [optional person chip]  action text (status)
 *
 * Strategy: capture cursor paragraph text + offset via DocumentApp BEFORE any
 * mutation, GET the document (pre-mutation = in sync), locate the cursor index
 * in the response, then issue one batchUpdate to insert the full fragment.
 *
 * @param {GoogleAppsScript.Document.Document} doc
 * @param {number} N
 * @param {string} globalId
 * @param {string} actionText
 * @param {string} assigneeEmail
 * @param {string} status
 * @param {string=} assigneeName  Optional display name for person chip
 */
function _insertActionChip(doc, N, globalId, actionText, assigneeEmail, status, assigneeName) {
  var cursor = doc.getCursor();
  if (!cursor) {
    GasLogger.log('INSERT_CHIP.warn', { msg: 'no cursor' });
    return 'No cursor position found — click in the document to place your cursor, then try again.';
  }

  var docId = doc.getId();
  var token = ScriptApp.getOAuthToken();

  var cursorResult = _resolveCursorIndex(doc, cursor, token);
  if (cursorResult.index === null) {
    GasLogger.log('INSERT_CHIP.error', { msg: cursorResult.error, paraText: (cursorResult.paraText || '').slice(0, 60), paraOffset: cursorResult.paraOffset });
    return cursorResult.error;
  }

  var fragResult = _applyActionFragment(docId, token, cursorResult.index, {
    N: N, globalId: globalId, actionText: actionText,
    assigneeEmail: assigneeEmail, status: status, assigneeName: assigneeName
  }, false);

  if (!fragResult.ok) return fragResult.error;

  GasLogger.log('INSERT_CHIP.done', { globalId: globalId, cursorIndex: cursorResult.index });
  return null;
}

/**
 * Resolves the Docs REST API character index for the document's current
 * cursor position.
 *
 * Strategy: capture cursor paragraph text + offset via DocumentApp BEFORE any
 * mutation, GET the document (pre-mutation = in sync), then locate the cursor
 * index in the response.
 *
 * Shared by _insertActionChip (single create) and _submitImport (multi-import
 * — cursor resolved ONCE; subsequent fragment positions are advanced
 * arithmetically via _applyActionFragment's insertedLength, since REST inserts
 * are not seen by DocumentApp mid-run).
 *
 * @param {GoogleAppsScript.Document.Document} doc
 * @param {GoogleAppsScript.Document.Position} cursor
 * @param {string} token  OAuth token from ScriptApp.getOAuthToken()
 * @returns {{index: number}|{index: null, error: string, paraText: string, paraOffset: number}}
 */
function _resolveCursorIndex(doc, cursor, token) {
  // Step 1 — capture cursor position via DocumentApp before any mutation.
  var cursorOffset  = cursor.getOffset();
  var cursorElement = cursor.getElement();
  // Walk up to the containing paragraph to get its full text.
  var cursorPara = cursorElement;
  while (cursorPara.getType() !== DocumentApp.ElementType.PARAGRAPH &&
         cursorPara.getType() !== DocumentApp.ElementType.LIST_ITEM) {
    cursorPara = cursorPara.getParent();
  }
  // Offset within the paragraph accounting for preceding sibling text elements.
  // Use element index to avoid false matches when two siblings have identical text.
  var paraOffset = cursorOffset;
  // Empty paragraph (no Text child yet): getElement() returns the paragraph
  // itself, which is not its own child — getChildIndex would throw. No
  // preceding siblings exist, so paraOffset is already correct.
  if (cursorElement !== cursorPara) {
    var targetChildIdx = cursorPara.getChildIndex(cursorElement);
    for (var s = 0; s < targetChildIdx; s++) {
      var sibling = cursorPara.getChild(s);
      if (sibling.getType() === DocumentApp.ElementType.TEXT) {
        paraOffset += sibling.asText().getText().length;
      } else {
        paraOffset += 1; // inline image or other non-text element
      }
    }
  }
  var paraText = cursorPara.getText();

  // Detect table-cell context; capture row/col/para indices so _findCursorInCell
  // targets the exact paragraph without any text-based search ambiguity.
  var cellRowIdx  = -1;
  var cellColIdx  = -1;
  var cellParaIdx = -1;
  if (cursorPara.getParent &&
      cursorPara.getParent() &&
      cursorPara.getParent().getType() === DocumentApp.ElementType.TABLE_CELL) {
    var tableCell_ = cursorPara.getParent();
    var tableRow_  = tableCell_.getParent();
    var table_     = tableRow_.getParent();
    cellRowIdx  = table_.getChildIndex(tableRow_);
    cellColIdx  = tableRow_.getChildIndex(tableCell_);
    cellParaIdx = tableCell_.getChildIndex(cursorPara);
  }
  var inTableCell = cellRowIdx >= 0;

  var docId   = doc.getId();
  var baseUrl = 'https://docs.googleapis.com/v1/documents/';

  // Step 2 — GET doc before any mutation (DocumentApp changes are deferred).
  // Field mask: only the text run content + indices needed by _findCursorIndex.
  // Includes table cell paragraphs so table-cell cursor resolution works.
  var _CURSOR_FIELDS = [
    'paragraph/elements(startIndex,endIndex,textRun/content)',
    'table/tableRows/tableCells/content/paragraph/elements(startIndex,endIndex,textRun/content)'
  ].join(',');
  var getResp = UrlFetchApp.fetch(
    baseUrl + docId + '?fields=body.content(' + _CURSOR_FIELDS + ')',
    { headers: { Authorization: 'Bearer ' + token }, muteHttpExceptions: true }
  );
  if (getResp.getResponseCode() !== 200) {
    return { index: null, error: 'Could not read document (HTTP ' + getResp.getResponseCode() + ')', paraText: paraText, paraOffset: paraOffset };
  }

  var content     = (JSON.parse(getResp.getContentText()).body || {}).content || [];
  var cursorIndex = inTableCell
    ? _findCursorInCell(content, paraText, paraOffset, cellRowIdx, cellColIdx, cellParaIdx)
    : _findCursorIndex(content, paraText, paraOffset);

  if (cursorIndex === null) {
    return { index: null, error: 'cursor position not found in document', paraText: paraText, paraOffset: paraOffset };
  }

  return { index: cursorIndex };
}

/**
 * Resolves the Docs REST API character index for the end of the document body
 * (just before the body's trailing newline) — the insertion point used by the
 * import_selected_for_test route (GTaskSheet-8qe5), which has no cursor.
 *
 * @param {string} docId
 * @param {string} token  OAuth token from ScriptApp.getOAuthToken()
 * @returns {{index: number}|{index: null, error: string}}
 */
function _resolveEndIndex(docId, token) {
  var baseUrl = 'https://docs.googleapis.com/v1/documents/';
  var getResp = UrlFetchApp.fetch(
    baseUrl + docId + '?fields=body.content',
    { headers: { Authorization: 'Bearer ' + token }, muteHttpExceptions: true }
  );
  if (getResp.getResponseCode() !== 200) {
    return { index: null, error: 'Could not read document (HTTP ' + getResp.getResponseCode() + ')' };
  }
  var content = (JSON.parse(getResp.getContentText()).body || {}).content || [];
  if (!content.length) {
    return { index: null, error: 'document body is empty' };
  }
  return { index: content[content.length - 1].endIndex - 1 };
}

/**
 * Inserts each selected importable row as a new floating action at `index`,
 * upserts the new rows into the current doc's ActionSheet (AC-2), and marks
 * each source row Forwarded (AC-3, forward_action_rows).
 *
 * Shared core extracted from _submitImport (epic-d-import-contract-seams #4,
 * GTaskSheet-8qe5) — reused by the production CardService handler (cursor-
 * resolved index) and the import_selected_for_test route (end-of-body index,
 * explicit globalIds selection instead of CardService form-collected
 * checkboxes).
 *
 * @param {GoogleAppsScript.Document.Document} doc
 * @param {string} docId
 * @param {string} token  OAuth token from ScriptApp.getOAuthToken()
 * @param {number} index  Target REST character index for the first insert
 * @param {Array<Object>} importRows  Rows from list_importable_actions, filtered to the selection
 * @returns {{ok: true, inserted: number, baseN: number}
 *          |{ok: false, title: string, error: string}}
 */
function _importSelectedRows(doc, docId, token, index, importRows) {
  var baseN    = _getNextActionN(doc);
  var newRows  = [];
  var forwards = [];

  for (var k = 0; k < importRows.length; k++) {
    var src         = importRows[k];
    var N           = baseN + k;
    var newGlobalId = docId + '/AI-' + N;

    var fragResult = _applyActionFragment(docId, token, index, {
      N:             N,
      globalId:      newGlobalId,
      actionText:    src.action_text,
      assigneeEmail: src.assignee_email,
      status:        src.status,
      assigneeName:  src.assignee_name || src.assignee_email
    }, k > 0);

    if (!fragResult.ok) {
      GasLogger.log('IMPORT_SELECTED.error', { msg: 'chip insert failed', err: fragResult.error, k: k });
      return {
        ok: false, title: 'Insert failed',
        error: 'Action ' + (k + 1) + ' of ' + importRows.length + ' could not be inserted.\n\n' + fragResult.error
      };
    }

    index += fragResult.insertedLength;

    newRows.push({
      globalId:      newGlobalId,
      actionText:    src.action_text,
      assigneeEmail: src.assignee_email,
      assigneeName:  src.assignee_name || src.assignee_email,
      status:        src.status
    });
    forwards.push({ sourceGlobalId: src.global_id, newGlobalId: newGlobalId });
  }

  // Write new rows to the current doc's ActionSheet only after doc inserts succeed.
  var upsertResult = _callWebApp('upsert_action_rows', {
    docUrl:   doc.getUrl(),
    docTitle: doc.getName(),
    rows:     newRows
  });

  if (!upsertResult || upsertResult.error) {
    GasLogger.log('IMPORT_SELECTED.error', { msg: 'upsert failed', err: upsertResult && upsertResult.error });
    return {
      ok: false, title: 'Error',
      error: 'Actions were inserted in the document but could not be saved: ' + ((upsertResult && upsertResult.error) || 'unknown error')
    };
  }

  // AC-3 — mark each source row Forwarded (status + suffix + dirty).
  var forwardResult = _callWebApp('forward_action_rows', {
    forwards:      forwards,
    targetDocName: doc.getName()
  });
  if (!forwardResult || forwardResult.error) {
    GasLogger.log('IMPORT_SELECTED.error', { msg: 'forward failed', err: forwardResult && forwardResult.error });
  }

  GasLogger.log('IMPORT_SELECTED.done', { inserted: newRows.length, baseN: baseN });
  return { ok: true, inserted: newRows.length, baseN: baseN };
}

/**
 * Builds and applies the Docs REST batchUpdate request set for one canonical
 * floating-action fragment:
 *
 *   [status image, linked]  [AI-N: text, linked]  [optional person chip]  action text (status)
 *
 * Step-3 request-build extracted from _insertActionChip so single-create and
 * multi-import (_submitImport) share one builder (epic-d-import-contract-seams
 * #3 — do NOT fork the chip path). All ranges are relative to `index`.
 * `insertedLength` tells the caller how far to advance `index` for the next
 * fragment — REST inserts are not seen by DocumentApp mid-run, so multi-insert
 * advances arithmetically rather than re-resolving the cursor.
 *
 * @param {string} docId
 * @param {string} token  OAuth token from ScriptApp.getOAuthToken()
 * @param {number} index  Target REST character index
 * @param {{N:number, globalId:string, actionText:string, assigneeEmail:string,
 *          status:string, assigneeName:(string|undefined)}} fields
 * @param {boolean} precedeWithNewline  Insert a paragraph break before the fragment
 *   (used for the 2nd+ fragment in a multi-import — each lands on its own paragraph)
 * @returns {{ok: boolean, error: (string|null), insertedLength: number}}
 */
function _applyActionFragment(docId, token, index, fields, precedeWithNewline) {
  var N             = fields.N;
  var globalId      = fields.globalId;
  var actionText    = fields.actionText;
  var assigneeEmail = fields.assigneeEmail;
  var status        = fields.status;

  var chipUrl = _buildChipUrl(globalId);
  var imgUrl  = _ACTION_STATUS_IMAGES[status] || _ACTION_DEFAULT_IMAGE;
  var baseUrl = 'https://docs.googleapis.com/v1/documents/';

  // Single batchUpdate. All inserts target fragIndex; each successive insert
  // pushes prior inserts rightward, so requests are listed in reverse final order.
  // Final paragraph order: [status image][AI-N: text][optional person chip][action text (status)]
  var validEmail = assigneeEmail && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(assigneeEmail);
  var tokenLen   = ('AI-' + N + ': ').length;
  var fragIndex  = precedeWithNewline ? index + 1 : index;

  var requests = [];
  if (precedeWithNewline) {
    requests.push({ insertText: { text: '\n', location: { index: index } } });
  }

  // 1. Trailing text (listed first → ends up rightmost)
  if (validEmail) {
    requests.push({ insertText: { text: ' ' + actionText + ' (' + status + ')', location: { index: fragIndex } } });
    // insertPerson rejects any name field in personProperties — email only
    requests.push({ insertPerson: { personProperties: { email: assigneeEmail }, location: { index: fragIndex } } });
  } else {
    requests.push({ insertText: { text: actionText + ' (' + status + ')', location: { index: fragIndex } } });
  }

  // 2. AI-N: text
  requests.push({ insertText: { text: 'AI-' + N + ': ', location: { index: fragIndex } } });

  // 3. Status image (listed last → ends up at fragIndex)
  requests.push({
    insertInlineImage: {
      uri: imgUrl, location: { index: fragIndex },
      objectSize: { height: { magnitude: 16, unit: 'PT' }, width: { magnitude: 16, unit: 'PT' } }
    }
  });

  // 4. Link on image (1 char) + AI-N: text
  requests.push({
    updateTextStyle: {
      range:     { startIndex: fragIndex, endIndex: fragIndex + 1 + tokenLen },
      textStyle: { link: { url: chipUrl } },
      fields:    'link'
    }
  });
  requests.push(_chipBadgeStyleRequest(fragIndex + 1, fragIndex + 1 + tokenLen));

  var trailingLen = validEmail
    ? 1 + (' ' + actionText + ' (' + status + ')').length
    : (actionText + ' (' + status + ')').length;
  var insertedLength = (precedeWithNewline ? 1 : 0) + 1 + tokenLen + trailingLen;

  var batchResp = UrlFetchApp.fetch(
    baseUrl + docId + ':batchUpdate',
    {
      method:             'post',
      headers:            { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      payload:            JSON.stringify({ requests: requests }),
      muteHttpExceptions: true
    }
  );

  if (batchResp.getResponseCode() !== 200) {
    var batchErr = 'HTTP ' + batchResp.getResponseCode() + ': ' + batchResp.getContentText().substring(0, 200);
    GasLogger.log('INSERT_CHIP.error', {
      msg:  'batchUpdate failed: HTTP ' + batchResp.getResponseCode(),
      body: batchResp.getContentText().substring(0, 300)
    });
    return { ok: false, error: batchErr, insertedLength: insertedLength };
  }

  return { ok: true, error: null, insertedLength: insertedLength };
}

/**
 * Finds the REST API character index for a given offset within a paragraph
 * identified by its plain text content.
 *
 * @param {Array}  content    body.content from REST GET response
 * @param {string} paraText   plain text of the target paragraph (no trailing \n)
 * @param {number} offset     character offset within that paragraph
 * @returns {number|null}
 */
/**
 * Matches a REST paragraph against paraText and returns the REST character
 * index at `offset`, or null if the paragraph text doesn't match.
 */
function _matchParaIndex(para, paraText, offset) {
  var runs      = para.elements || [];
  var builtText = '';
  for (var j = 0; j < runs.length; j++) {
    var tr = runs[j].textRun;
    if (tr && tr.content) builtText += tr.content;
  }
  builtText = builtText.replace(/\n$/, '');
  if (builtText !== paraText) return null;

  var runPos = 0;
  for (var k = 0; k < runs.length; k++) {
    var tr2 = runs[k].textRun;
    if (!tr2 || !tr2.content) continue;
    var runLen = tr2.content.replace(/\n$/, '').length;
    if (offset <= runPos + runLen) return runs[k].startIndex + (offset - runPos);
    runPos += runLen;
  }
  if (runs.length > 0) return runs[runs.length - 1].endIndex - 1;
  return null;
}

/**
 * Searches body-level paragraphs in a REST body.content array for the
 * paragraph matching paraText and returns the REST character index at `offset`.
 * Does not descend into tables — use _findCursorInCell for table-cell cursors.
 */
function _findCursorIndex(content, paraText, offset) {
  for (var i = 0; i < content.length; i++) {
    if (content[i].paragraph) {
      var idx = _matchParaIndex(content[i].paragraph, paraText, offset);
      if (idx !== null) return idx;
    }
  }
  return null;
}

/**
 * Finds the cursor REST character index when the caret is inside a specific
 * table cell, identified by exact (rowIdx, colIdx, paraIdx) captured from
 * DocumentApp via getChildIndex.  Goes directly to the named paragraph — no
 * text-based search within the cell — so multiple empty or identical paragraphs
 * in the same cell cannot cause a false match.
 *
 * @param {Array}  content   body.content from REST GET
 * @param {string} paraText  plain text of the cursor paragraph (for _matchParaIndex)
 * @param {number} offset    character offset within that paragraph
 * @param {number} rowIdx    0-based row index from DocumentApp
 * @param {number} colIdx    0-based column index from DocumentApp
 * @param {number} paraIdx   0-based paragraph index within the cell from DocumentApp
 */
function _findCursorInCell(content, paraText, offset, rowIdx, colIdx, paraIdx) {
  for (var i = 0; i < content.length; i++) {
    if (!content[i].table) continue;
    var tableRows = content[i].table.tableRows || [];
    if (rowIdx >= tableRows.length) continue;
    var cells = tableRows[rowIdx].tableCells || [];
    if (colIdx >= cells.length) continue;
    var cellContent = cells[colIdx].content || [];
    if (paraIdx >= cellContent.length) continue;
    var item = cellContent[paraIdx];
    if (!item || !item.paragraph) continue;
    return _matchParaIndex(item.paragraph, paraText, offset);
  }
  return null;
}

// ---------------------------------------------------------------------------
// WebApp proxy
// ---------------------------------------------------------------------------

/**
 * POSTs to the project WebApp and returns parsed JSON.
 * Mirrors the pattern in _patchActionStatus (WorkspaceAddonCard.js) — read-only reuse.
 *
 * @param {string} action  WebApp action name (e.g. 'upsert_action_rows')
 * @param {Object} payload  Additional payload fields
 * @returns {Object|null}  Parsed response JSON, or null on fetch error
 */
function _callWebApp(action, payload) {
  var webAppUrl = getWebAppUrl();
  var secret    = PropertiesService.getScriptProperties().getProperty('WEBAPP_SECRET');

  if (!webAppUrl) {
    GasLogger.log('poc.webApp.error', { msg: 'WEBAPP_URL not set' });
    return null;
  }

  payload.action         = action;
  payload.secret         = secret || '';
  payload.clientVersion  = BUILD_INFO.version;
  payload.caller         = _getIdentity();

  var resp = UrlFetchApp.fetch(webAppUrl, {
    method:             'post',
    contentType:        'application/json',
    muteHttpExceptions: true,
    headers:            { 'Authorization': 'Bearer ' + ScriptApp.getOAuthToken() },
    payload:            JSON.stringify(payload)
  });

  if (resp.getResponseCode() !== 200) {
    GasLogger.log('poc.webApp.error', { status: resp.getResponseCode(), body: resp.getContentText().slice(0, 200) });
    return { error: 'HTTP ' + resp.getResponseCode() };
  }

  try {
    var parsed = JSON.parse(resp.getContentText());
    _logVersionMismatch(parsed, 'poc.webApp');
    return parsed;
  } catch (err) {
    GasLogger.log('poc.webApp.parseError', { body: resp.getContentText().slice(0, 200) });
    return { error: 'invalid JSON' };
  }
}
