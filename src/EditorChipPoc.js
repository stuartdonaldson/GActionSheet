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
var _POC_ACTION_URL_BASE = 'https://stuartdonaldson.github.io/GActionSheet/action/';

/** Status values matching the ActionSheet dropdown. */
var _POC_STATUSES = ['Open', 'In Progress', 'In Review', 'Done', 'Closed'];

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
 * Full implementation: GTaskSheet-6ov.5
 *
 * @param {GoogleAppsScript.Addons.EventObject} e
 * @returns {GoogleAppsScript.Card_Service.Card}
 */
function onLinkPreview(e) { // eslint-disable-line no-unused-vars
  GasLogger.log('LINK_PREVIEW', { url: e && e.docs && e.docs.matchedUrl && e.docs.matchedUrl.url });
  // stub — GTaskSheet-6ov.5
  return _poc_buildPreviewStubCard(e);
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
  var formInput    = (e && e.formInput) || {};
  var actionText   = (formInput.poc_actionText  || '').trim();
  var assigneeEmail = (formInput.poc_assignee   || '').trim();
  var status       = formInput.poc_status || 'Open';

  if (!actionText) {
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('Action text is required.'))
      .build();
  }

  var doc          = DocumentApp.getActiveDocument();
  var namedRangeId = 'poc-' + Utilities.getUuid();
  var docUrl       = doc.getUrl();
  var docTitle     = doc.getName();

  // Write row to ActionSheet via WebApp
  var result = _poc_callWebApp('upsert_action_rows', {
    docUrl:   docUrl,
    docTitle: docTitle,
    rows: [{
      namedRangeId:  namedRangeId,
      actionText:    actionText,
      assigneeEmail: assigneeEmail,
      assigneeName:  assigneeEmail,
      status:        status
    }]
  });

  if (!result || result.error) {
    GasLogger.log('CREATE_ACTION_TRIGGER.error', { err: result && result.error });
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('Failed to create action: ' + (result && result.error || 'unknown error')))
      .build();
  }

  // Insert chip link at cursor
  _poc_insertActionChip(doc, namedRangeId, actionText, assigneeEmail, status);

  GasLogger.log('CREATE_ACTION_TRIGGER.done', { namedRangeId: namedRangeId, upserted: result.upserted });
  return CardService.newActionResponseBuilder()
    .setNotification(CardService.newNotification().setText('Action created: ' + actionText))
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
        .setHint('email address')
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
 * Stub preview card shown on link hover until GTaskSheet-6ov.5 is implemented.
 *
 * @param {GoogleAppsScript.Addons.EventObject} e
 * @returns {GoogleAppsScript.Card_Service.Card}
 */
function _poc_buildPreviewStubCard(e) {
  var url = (e && e.docs && e.docs.matchedUrl && e.docs.matchedUrl.url) || '';
  var namedRangeId = url.replace(_POC_ACTION_URL_BASE, '');

  return CardService.newCardBuilder()
    .setHeader(
      CardService.newCardHeader()
        .setTitle('GActionSheet Action')
        .setImageUrl('https://raw.githubusercontent.com/stuartdonaldson/GActionSheet/master/assets/action-logo-t-32.png')
    )
    .addSection(
      CardService.newCardSection()
        .addWidget(CardService.newTextParagraph().setText(namedRangeId || 'Action preview — GTaskSheet-6ov.5'))
    )
    .build();
}

// ---------------------------------------------------------------------------
// Doc insertion
// ---------------------------------------------------------------------------

/**
 * Inserts an action smart-chip hyperlink at the current cursor position.
 * The URL matches the linkPreviewTriggers pattern so Docs renders it as a chip.
 *
 * @param {GoogleAppsScript.Document.Document} doc
 * @param {string} namedRangeId
 * @param {string} actionText
 * @param {string} assigneeEmail
 * @param {string} status
 */
function _poc_insertActionChip(doc, namedRangeId, actionText, assigneeEmail, status) {
  var cursor = doc.getCursor();
  if (!cursor) return; // no cursor — silent; doc may not be editable at trigger time

  var chipUrl  = _POC_ACTION_URL_BASE + namedRangeId;
  var chipText = actionText + (assigneeEmail ? ' @' + assigneeEmail.split('@')[0] : '') + ' [' + status + ']';

  var element = cursor.insertText(chipText);
  if (!element) return;

  // Apply hyperlink so Docs treats the text as a smart-chip link
  var textRange = element.getParent().editAsText();
  var start     = element.getStartOffset ? element.getStartOffset() : 0;
  var end       = start + chipText.length - 1;
  textRange.setLinkUrl(start, end, chipUrl);
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
  var props     = PropertiesService.getScriptProperties();
  var webAppUrl = props.getProperty('WEBAPP_URL');
  var secret    = props.getProperty('WEBAPP_SECRET');

  if (!webAppUrl) {
    GasLogger.log('poc.webApp.error', { msg: 'WEBAPP_URL not set' });
    return null;
  }

  payload.action = action;
  payload.secret = secret || '';

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
    return JSON.parse(resp.getContentText());
  } catch (err) {
    GasLogger.log('poc.webApp.parseError', { body: resp.getContentText().slice(0, 200) });
    return { error: 'invalid JSON' };
  }
}
