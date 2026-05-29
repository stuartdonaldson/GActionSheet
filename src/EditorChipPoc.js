/**
 * EditorChipPoc.js
 *
 * POC: Docs editor add-on action-chip (branch poc/editor-addon-action-chip).
 *
 * ISOLATION CONTRACT
 * ------------------
 * - All private helpers are prefixed `_poc_`.
 * - Entry-point globals (createActionTrigger, onLinkPreview) must be top-level
 *   GAS globals — they cannot be namespaced.
 * - No existing src/ file is modified by POC work. Shared utilities are called
 *   read-only; never altered.
 * - Remove this file and its appsscript.json entries before merging to master.
 *
 * ISSUES
 * ------
 * createActionTrigger  → GTaskSheet-6ov.3 (IMP) / GTaskSheet-6ov.4 (TST)
 * onLinkPreview        → GTaskSheet-6ov.5 (IMP) / GTaskSheet-6ov.6 (TST)
 * insertActionChip     → GTaskSheet-6ov.7 (IMP) / GTaskSheet-6ov.8 (TST)
 */

/** Base URL for action smart-chip links. Matches linkPreviewTriggers hostPattern. */
var _POC_ACTION_URL_BASE = 'https://northlakeuu.org/GActionSheet/action/';

/** Status values matching the ActionSheet dropdown. */
var _POC_STATUSES = ['Open', 'In Progress', 'In Review', 'Done', 'Closed'];

// Docs REST API insertInlineImage does not support SVG — use PNG until PNG status icons exist.
var _POC_DEFAULT_IMAGE = 'https://stuartdonaldson.github.io/GActionSheet/assets/action-logo-t-32.png';
var _POC_STATUS_IMAGES = {}; // empty: all statuses fall through to _POC_DEFAULT_IMAGE

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
  return _poc_buildCreationCard();
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
  GasLogger.log('LINK_PREVIEW', { url: url });
  try {
    return _poc_buildPreviewCard(url);
  } catch (err) {
    GasLogger.log('LINK_PREVIEW.error', { msg: String(err) });
    return _poc_buildMessageCard('Preview error', 'Could not load action preview. Please report this to your administrator.\n\n' + String(err));
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
function _poc_submitCreateAction(e) {
  var formInput      = (e && e.formInput) || {};
  var actionText     = (formInput.poc_actionText  || '').trim();
  var assigneeRaw    = (formInput.poc_assignee    || '').trim();
  var status         = formInput.poc_status || 'Open';

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
    return CardService.newActionResponseBuilder()
      .setNavigation(CardService.newNavigation().updateCard(_poc_buildMessageCard('Required', 'Action text cannot be empty.')))
      .build();
  }

  var doc      = DocumentApp.getActiveDocument();
  var N        = _poc_getNextActionN(doc);
  var globalId = doc.getId() + '/AI-' + N;
  var docUrl   = doc.getUrl();
  var docTitle = doc.getName();

  // Insert chip at cursor first — doc is source of truth; sheet is downstream.
  // NOTE: CardService.newSmartChipConfig / newRenderAction do NOT exist in the
  // current GAS runtime (confirmed 2026-05-27 — TypeError). The REST approach
  // is the correct insertion method.
  var insertError = _poc_insertActionChip(doc, N, globalId, actionText, assigneeEmail, status, assigneeName || assigneeEmail);

  if (insertError) {
    GasLogger.log('CREATE_ACTION_TRIGGER.error', { msg: 'chip insert failed', err: insertError });
    return CardService.newActionResponseBuilder()
      .setNavigation(CardService.newNavigation().updateCard(
        _poc_buildMessageCard('Insert failed', 'Action could not be inserted at the cursor.\n\n' + insertError)
      ))
      .build();
  }

  // Write row to ActionSheet only after doc insertion succeeds.
  var result = _poc_callWebApp('upsert_action_rows', {
    docUrl:   docUrl,
    docTitle: docTitle,
    rows: [{
      namedRangeId:  globalId,
      actionText:    actionText,
      assigneeEmail: assigneeEmail,
      assigneeName:  assigneeName || assigneeEmail,
      status:        status
    }]
  });

  if (!result || result.error) {
    GasLogger.log('CREATE_ACTION_TRIGGER.error', { err: result && result.error });
    return CardService.newActionResponseBuilder()
      .setNavigation(CardService.newNavigation().updateCard(_poc_buildMessageCard('Error', 'Failed to create action: ' + ((result && result.error) || 'unknown error'))))
      .build();
  }

  GasLogger.log('CREATE_ACTION_TRIGGER.done', { globalId: globalId });
  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().updateCard(_poc_buildMessageCard('Action created', 'AI-' + N + ': ' + actionText)))
    .build();
}

// ---------------------------------------------------------------------------
// Card builders
// ---------------------------------------------------------------------------

/**
 * Builds the "Create action" card shown in the Docs @-menu trigger.
 *
 * @returns {GoogleAppsScript.Card_Service.Card}
 */
function _poc_buildCreationCard() {
  var submitAction = CardService.newAction().setFunctionName('_poc_submitCreateAction');

  var section = CardService.newCardSection()
    .addWidget(
      CardService.newTextInput()
        .setFieldName('poc_actionText')
        .setTitle('Action')
        .setHint('What needs to be done?')
    )
    .addWidget(
      CardService.newTextInput()
        .setFieldName('poc_assignee')
        .setTitle('Assignee (optional)')
        .setHint('name or email')
        .setSuggestionsAction(
          CardService.newAction().setFunctionName('_poc_suggestAssignees')
        )
    )
    .addWidget(
      CardService.newSelectionInput()
        .setType(CardService.SelectionInputType.DROPDOWN)
        .setFieldName('poc_status')
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
        .setImageUrl('https://raw.githubusercontent.com/stuartdonaldson/GActionSheet/master/assets/action-logo-t-32.png')
    )
    .addSection(section)
    .build();
}

/**
 * SuggestionsAction for the Assignee field on the Create Action card.
 * Queries the Google People API directory for matching users as the field changes.
 * Returns suggestions in "Display Name <email>" format; submit handler parses this.
 *
 * Requires scope: https://www.googleapis.com/auth/directory.readonly
 *
 * @param {GoogleAppsScript.Addons.EventObject} e
 * @returns {GoogleAppsScript.Card_Service.SuggestionsResponse}
 */
function _poc_suggestAssignees(e) { // eslint-disable-line no-unused-vars
  try {
    var query = (e && e.formInput && e.formInput.poc_assignee) || '';
    GasLogger.log('poc.suggestAssignees', { query: query });
    GasLogger.flush();

    var suggestions = CardService.newSuggestions();

    if (query.length >= 4) {
      var token = ScriptApp.getOAuthToken();
      var url   = 'https://people.googleapis.com/v1/people:searchDirectoryPeople'
        + '?query='    + encodeURIComponent(query)
        + '&readMask=' + encodeURIComponent('emailAddresses,names')
        + '&sources=DIRECTORY_SOURCE_TYPE_DOMAIN_PROFILE';

      var resp = UrlFetchApp.fetch(url, {
        headers:            { Authorization: 'Bearer ' + token },
        muteHttpExceptions: true
      });

      var code = resp.getResponseCode();
      GasLogger.log('poc.suggestAssignees.resp', { code: code });
      GasLogger.flush();

      if (code === 200) {
        _poc_addPeopleSuggestions(suggestions, JSON.parse(resp.getContentText()).people || [], query);
      } else {
        // Directory search failed (likely 403 — scope not granted or domain policy).
        // Fall back to personal contacts search which requires only contacts.readonly.
        GasLogger.log('poc.suggestAssignees.dir_fail', { code: code });
        var contactsUrl = 'https://people.googleapis.com/v1/people:searchContacts'
          + '?query='    + encodeURIComponent(query)
          + '&readMask=' + encodeURIComponent('emailAddresses,names');
        var cresp = UrlFetchApp.fetch(contactsUrl, {
          headers:            { Authorization: 'Bearer ' + token },
          muteHttpExceptions: true
        });
        var ccode = cresp.getResponseCode();
        GasLogger.log('poc.suggestAssignees.contacts', { code: ccode });
        GasLogger.flush();
        if (ccode === 200) {
          var cdata    = JSON.parse(cresp.getContentText());
          var cresults = (cdata.results || []).map(function(r) { return r.person; });
          _poc_addPeopleSuggestions(suggestions, cresults, query);
        } else {
          GasLogger.log('poc.suggestAssignees.contacts_fail', { code: ccode });
        }
      }
    }

    var built = CardService.newSuggestionsResponseBuilder()
      .setSuggestions(suggestions)
      .build();
    GasLogger.log('poc.suggestAssignees.built', { query: query });
    GasLogger.flush();
    return built;
  } catch (err) {
    GasLogger.log('poc.suggestAssignees.fatal', { msg: String(err), stack: err.stack ? err.stack.substring(0, 300) : '' });
    GasLogger.flush();
    return CardService.newSuggestionsResponseBuilder()
      .setSuggestions(CardService.newSuggestions())
      .build();
  }
}

/** Adds up to 4 People API person objects to a Suggestions instance. */
function _poc_addPeopleSuggestions(suggestions, people, query) {
  var added = 0;
  for (var i = 0; i < people.length && added < 4; i++) {
    var emails = (people[i] && people[i].emailAddresses) || [];
    var names  = (people[i] && people[i].names)          || [];
    var email  = emails.length ? emails[0].value      : '';
    var name   = names.length  ? names[0].displayName : '';
    if (!email) continue;
    // Avoid angle brackets — addSuggestion may reject them on some runtimes
    var label = name ? name + ' (' + email + ')' : email;
    try {
      suggestions.addSuggestion(label);
      added++;
    } catch (e) {
      GasLogger.log('poc.suggestAssignees.addSuggestion.err', { label: label, msg: String(e) });
    }
  }
  GasLogger.log('poc.suggestAssignees.results', { query: query, peopleCount: people.length, added: added });
}

/**
 * Builds the smart-chip hover preview card for an action URL.
 * Looks up the action in the ActionSheet by namedRangeId.
 *
 * @param {string} url  The matched action URL
 * @returns {GoogleAppsScript.Card_Service.Card}
 */
function _poc_buildPreviewCard(url) {
  var globalId  = url.replace(_POC_ACTION_URL_BASE, '');
  var idParts   = globalId.split('/AI-');
  var actionId  = idParts.length >= 2 ? 'AI-' + idParts[1] : '';
  GasLogger.log('PREVIEW_CARD.lookup', { globalId: globalId, actionId: actionId });
  var doc      = DocumentApp.getActiveDocument();
  var scanned  = _scanFloatingActions(doc);
  var match    = null;
  for (var fi = 0; fi < scanned.length; fi++) {
    if (scanned[fi].globalId === globalId) { match = scanned[fi]; break; }
  }
  var action = match ? { action: match.actionText, status: match.status, assigneeEmail: match.assigneeEmail, assigneeName: match.assigneeName } : null;
  GasLogger.log('PREVIEW_CARD.result', { found: !!action, action: action ? action.action : null, status: action ? action.status : null });
  GasLogger.flush();

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
    .setImageUrl('https://raw.githubusercontent.com/stuartdonaldson/GActionSheet/master/assets/action-logo-t-32.png')
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
    var _ICON_BASE = 'https://stuartdonaldson.github.io/GActionSheet/assets/';
    var _STATUS_ICONS = [
      { status: 'Open',        icon: _ICON_BASE + 'status-open.svg',       alt: 'Set Open' },
      { status: 'In Progress', icon: _ICON_BASE + 'status-inprogress.svg', alt: 'Set In Progress' },
      { status: 'In Review',   icon: _ICON_BASE + 'status-inreview.svg',   alt: 'Set In Review' },
      { status: 'Done',        icon: _ICON_BASE + 'status-done.svg',       alt: 'Set Done' },
      { status: 'Closed',      icon: _ICON_BASE + 'status-closed.svg',     alt: 'Set Closed' }
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
              .setFunctionName('_poc_setStatusFromPreview')
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
function _poc_setStatusFromPreview(e) { // eslint-disable-line no-unused-vars
  var url       = (e && e.parameters && e.parameters.url)       || '';
  var newStatus = (e && e.parameters && e.parameters.newStatus) || 'Open';

  var globalId = url.replace(_POC_ACTION_URL_BASE, '');
  var idParts  = globalId.split('/AI-');
  var N        = idParts.length >= 2 ? parseInt(idParts[1], 10) : 0;

  // Use getActiveDocument() (already loaded, no network) instead of openById
  var doc    = DocumentApp.getActiveDocument();
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

  var flushed = _poc_flushActionParagraph(docId, token, N, globalId, actionText, newStatus, assigneeEmail, assigneeName);

  if (!flushed) {
    GasLogger.log('POC_EDIT_ACTION.flush_failed', { globalId: globalId });
    GasLogger.flush();
    return CardService.newActionResponseBuilder()
      .setNavigation(CardService.newNavigation().updateCard(_poc_buildMessageCard('Error', 'Failed to update action in document.')))
      .build();
  }

  _poc_scheduleSheetUpdate({
    docUrl:         doc.getUrl(),
    docTitle:       doc.getName(),
    namedRangeId:   globalId,
    actionText:     actionText,
    assigneeEmail:  assigneeEmail,
    assigneeName:   assigneeName,
    status:         newStatus,
    refreshTracker: hasTracker,
    docId:          docId
  });

  GasLogger.log('POC_EDIT_ACTION.complete', { globalId: globalId, status: newStatus });
  GasLogger.flush();

  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().updateCard(_poc_buildPreviewCard(url)))
    .build();
}

// ---------------------------------------------------------------------------
// Async sheet update via time-based trigger
// ---------------------------------------------------------------------------

/**
 * Enqueues sheet upsert params into the POC_QUEUE script property (JSON array)
 * under a script lock, then schedules a drain trigger if none is already pending.
 *
 * @param {Object} params  Fields: docUrl, docTitle, namedRangeId, actionText,
 *                         assigneeEmail, assigneeName, status
 */
function _poc_scheduleSheetUpdate(params) {
  var props = PropertiesService.getScriptProperties();
  var lock  = LockService.getScriptLock();
  var queueLength;
  lock.waitLock(5000);
  try {
    var queue = JSON.parse(props.getProperty('POC_QUEUE') || '[]');
    queue.push(params);
    props.setProperty('POC_QUEUE', JSON.stringify(queue));
    queueLength = queue.length;
  } finally {
    lock.releaseLock();
  }

  var existing = ScriptApp.getProjectTriggers();
  var hasTrigger = false;
  for (var i = 0; i < existing.length; i++) {
    if (existing[i].getHandlerFunction() === '_poc_processPendingSheetUpdates') {
      hasTrigger = true;
      break;
    }
  }
  if (!hasTrigger) {
    ScriptApp.newTrigger('_poc_processPendingSheetUpdates').timeBased().after(2000).create();
  }
  GasLogger.log('poc.asyncSheet.enqueued', { queueLength: queueLength });
}

/**
 * Time-based trigger handler: atomically drains POC_QUEUE under a lock,
 * processes the snapshot, then deletes only this trigger instance.
 * Log tag: POC_ASYNC_SHEET.complete
 *
 * @param {Object} e  GAS trigger event — e.triggerUid used for self-cleanup
 */
function _poc_processPendingSheetUpdates(e) { // eslint-disable-line no-unused-vars
  var props = PropertiesService.getScriptProperties();
  var lock  = LockService.getScriptLock();
  var snapshot;
  lock.waitLock(10000);
  try {
    snapshot = JSON.parse(props.getProperty('POC_QUEUE') || '[]');
    props.setProperty('POC_QUEUE', '[]');
  } finally {
    lock.releaseLock();
  }

  for (var i = 0; i < snapshot.length; i++) {
    var p = snapshot[i];
    try {
      _poc_callWebApp('upsert_action_rows', {
        docUrl:   p.docUrl,
        docTitle: p.docTitle,
        rows: [{
          namedRangeId:  p.namedRangeId,
          actionText:    p.actionText,
          assigneeEmail: p.assigneeEmail,
          assigneeName:  p.assigneeName,
          status:        p.status
        }]
      });
    } catch (err) {
      GasLogger.log('poc.asyncSheet.error', { namedRangeId: p.namedRangeId, msg: String(err) });
    }
    if (p.refreshTracker && p.docId) {
      try {
        insertTrackerTable(p.docId);
      } catch (err) {
        GasLogger.log('poc.asyncTracker.error', { docId: p.docId, msg: String(err) });
      }
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
function _poc_buildMessageCard(title, message) {
  return CardService.newCardBuilder()
    .setHeader(CardService.newCardHeader().setTitle(title)
      .setImageUrl('https://raw.githubusercontent.com/stuartdonaldson/GActionSheet/master/assets/action-logo-t-32.png'))
    .addSection(CardService.newCardSection()
      .addWidget(CardService.newTextParagraph().setText(message)))
    .build();
}

/**
 * Looks up a single action row from the ActionSheet by namedRangeId.
 * Uses verify_action_rows with no docUrl filter (returns all rows) then finds match.
 *
 * @param {string} namedRangeId
 * @returns {Object|null}  Row object {namedRangeId, id, assigneeEmail, assigneeName, action, status} or null
 */
/**
 * Looks up a single action from the source document by namedRangeId.
 * The document (not the sheet) is source of truth; the sheet is downstream.
 *
 * @param {string} namedRangeId  globalId format: {docId}/AI-{N}
 * @returns {{action, status, assigneeEmail, assigneeName}|null}
 */
function _poc_lookupActionFromDoc(namedRangeId) {
  if (!namedRangeId) return null;

  var parts = namedRangeId.split('/AI-');
  if (parts.length < 2) return null;
  var docId = parts[0];

  try {
    var doc     = DocumentApp.openById(docId);
    var actions = _scanFloatingActions(doc);
    GasLogger.log('poc.lookupFromDoc.scan', { namedRangeId: namedRangeId, docId: docId, count: actions.length });
    for (var i = 0; i < actions.length; i++) {
      if (actions[i].globalId === namedRangeId) {
        var a = actions[i];
        return {
          action:        a.actionText,
          status:        a.status,
          assigneeEmail: a.assigneeEmail,
          assigneeName:  a.assigneeName
        };
      }
    }
    GasLogger.log('poc.lookupFromDoc.notfound', { namedRangeId: namedRangeId, scannedIds: actions.map(function(a) { return a.globalId; }) });
  } catch (err) {
    GasLogger.log('poc.lookupFromDoc.error', { namedRangeId: namedRangeId, msg: String(err) });
  }
  return null;
}

function _poc_lookupAction(namedRangeId) {
  if (!namedRangeId) return null;

  var result = _poc_callWebApp('verify_action_rows', { docUrl: '' });
  if (!result || !result.rows) return null;

  for (var i = 0; i < result.rows.length; i++) {
    if (result.rows[i].namedRangeId === namedRangeId) {
      return result.rows[i];
    }
  }
  return null;
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
function _poc_getNextActionN(doc) {
  var body = doc.getBody();
  var n    = body.getNumChildren();
  var maxN = 0;
  for (var i = 0; i < n; i++) {
    var child = body.getChild(i);
    var type  = child.getType();
    if (type !== DocumentApp.ElementType.PARAGRAPH &&
        type !== DocumentApp.ElementType.LIST_ITEM) continue;
    var text = child.getText().replace(/\n$/, '');
    var m = text.match(/^AI-(\d+):/);
    if (m) maxN = Math.max(maxN, parseInt(m[1], 10));
  }
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
function _poc_insertActionChip(doc, N, globalId, actionText, assigneeEmail, status, assigneeName) {
  var cursor = doc.getCursor();
  if (!cursor) {
    GasLogger.log('POC_INSERT_CHIP.warn', { msg: 'no cursor' });
    return 'No cursor position found — click in the document to place your cursor, then try again.';
  }

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
  var paraOffset = cursorOffset;
  var numSiblings = cursorPara.getNumChildren();
  for (var s = 0; s < numSiblings; s++) {
    var sibling = cursorPara.getChild(s);
    if (sibling === cursorElement || sibling.getType() === DocumentApp.ElementType.TEXT &&
        sibling.asText().getText() === cursorElement.getText()) {
      break;
    }
    if (sibling.getType() === DocumentApp.ElementType.TEXT) {
      paraOffset += sibling.asText().getText().length;
    } else {
      paraOffset += 1; // inline image or other non-text element
    }
  }
  var paraText = cursorPara.getText();

  var docId   = doc.getId();
  var chipUrl = _POC_ACTION_URL_BASE + globalId;
  var imgUrl  = _POC_STATUS_IMAGES[status] || _POC_DEFAULT_IMAGE;
  var token   = ScriptApp.getOAuthToken();
  var baseUrl = 'https://docs.googleapis.com/v1/documents/';

  // Step 2 — GET doc before any mutation (DocumentApp changes are deferred).
  var getResp = UrlFetchApp.fetch(
    baseUrl + docId + '?fields=body.content',
    { headers: { Authorization: 'Bearer ' + token }, muteHttpExceptions: true }
  );
  if (getResp.getResponseCode() !== 200) {
    var getErr = 'Could not read document (HTTP ' + getResp.getResponseCode() + ')';
    GasLogger.log('POC_INSERT_CHIP.error', { msg: getErr });
    return getErr;
  }

  var content     = (JSON.parse(getResp.getContentText()).body || {}).content || [];
  var cursorIndex = _poc_findCursorIndex(content, paraText, paraOffset);

  if (cursorIndex === null) {
    var errMsg = 'cursor position not found in document';
    GasLogger.log('POC_INSERT_CHIP.error', { msg: errMsg, paraText: paraText.slice(0, 60), paraOffset: paraOffset });
    return errMsg;
  }

  // Step 3 — single batchUpdate. All inserts target cursorIndex; each successive
  // insert pushes prior inserts rightward, so requests are listed in reverse final order.
  // Final paragraph order: [status image][AI-N: text][optional person chip][action text (status)]
  var validEmail = assigneeEmail && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(assigneeEmail);

  // 1. Trailing text (listed first → ends up rightmost)
  var requests = [];
  if (validEmail) {
    requests.push({ insertText: { text: ' ' + actionText + ' (' + status + ')', location: { index: cursorIndex } } });
    // insertPerson rejects any name field in personProperties — email only
    requests.push({ insertPerson: { personProperties: { email: assigneeEmail }, location: { index: cursorIndex } } });
  } else {
    requests.push({ insertText: { text: actionText + ' (' + status + ')', location: { index: cursorIndex } } });
  }

  // 2. AI-N: text
  requests.push({ insertText: { text: 'AI-' + N + ': ', location: { index: cursorIndex } } });

  // 3. Status image (listed last → ends up at cursorIndex)
  requests.push({
    insertInlineImage: {
      uri: imgUrl, location: { index: cursorIndex },
      objectSize: { height: { magnitude: 16, unit: 'PT' }, width: { magnitude: 16, unit: 'PT' } }
    }
  });

  // 4. Link on image (1 char) + AI-N: text
  var tokenLen = ('AI-' + N + ': ').length;
  requests.push({
    updateTextStyle: {
      range:     { startIndex: cursorIndex, endIndex: cursorIndex + 1 + tokenLen },
      textStyle: { link: { url: chipUrl } },
      fields:    'link'
    }
  });
  // Chip badge: Comic Sans bold dark-purple, no background, no hyperlink underline
  requests.push({
    updateTextStyle: {
      range:     { startIndex: cursorIndex + 1, endIndex: cursorIndex + 1 + tokenLen },
      textStyle: {
        bold: true, underline: false,
        foregroundColor: { color: { rgbColor: { red: 0.298, green: 0.114, blue: 0.584 } } },
        backgroundColor: { color: { rgbColor: { red: 1.0, green: 1.0, blue: 1.0 } } },
        weightedFontFamily: { fontFamily: 'Comic Sans MS', weight: 700 }
      },
      fields: 'bold,underline,foregroundColor,backgroundColor,weightedFontFamily'
    }
  });

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
    GasLogger.log('POC_INSERT_CHIP.error', {
      msg:  'batchUpdate failed: HTTP ' + batchResp.getResponseCode(),
      body: batchResp.getContentText().substring(0, 300)
    });
    return batchErr;
  }

  GasLogger.log('POC_INSERT_CHIP.done', { globalId: globalId, cursorIndex: cursorIndex });
  return null;
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
function _poc_findCursorIndex(content, paraText, offset) {
  for (var i = 0; i < content.length; i++) {
    var para = content[i].paragraph;
    if (!para) continue;

    // Reconstruct paragraph plain text from text runs (strip trailing \n)
    var runs = para.elements || [];
    var builtText = '';
    for (var j = 0; j < runs.length; j++) {
      var tr = runs[j].textRun;
      if (tr && tr.content) builtText += tr.content;
    }
    builtText = builtText.replace(/\n$/, '');

    if (builtText !== paraText) continue;

    // Found the paragraph — locate the character at `offset` across its runs
    var runPos = 0;
    for (var k = 0; k < runs.length; k++) {
      var tr = runs[k].textRun;
      if (!tr || !tr.content) continue;
      var runLen = tr.content.replace(/\n$/, '').length;
      if (offset <= runPos + runLen) {
        return runs[k].startIndex + (offset - runPos);
      }
      runPos += runLen;
    }
    // Offset past all runs — return end of paragraph (before \n)
    if (runs.length > 0) {
      var last = runs[runs.length - 1];
      return last.endIndex - 1;
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// WebApp proxy
// ---------------------------------------------------------------------------

/**
 * POSTs to the project WebApp and returns parsed JSON.
 * Mirrors the pattern in _patchActionStatus (Addon.js) — read-only reuse.
 *
 * @param {string} action  WebApp action name (e.g. 'upsert_action_rows')
 * @param {Object} payload  Additional payload fields
 * @returns {Object|null}  Parsed response JSON, or null on fetch error
 */
function _poc_callWebApp(action, payload) {
  var webAppUrl = getWebAppUrl();
  var secret    = PropertiesService.getScriptProperties().getProperty('WEBAPP_SECRET');

  if (!webAppUrl) {
    GasLogger.log('poc.webApp.error', { msg: 'WEBAPP_URL not set' });
    return null;
  }

  payload.action         = action;
  payload.secret         = secret || '';
  payload.clientVersion  = BUILD_INFO.version;

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
