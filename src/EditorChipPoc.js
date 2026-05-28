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

var _POC_STATUS_IMAGES = {
  'Open':        'https://stuartdonaldson.github.io/GActionSheet/assets/status-open.svg',
  'In Progress': 'https://stuartdonaldson.github.io/GActionSheet/assets/status-inprogress.svg',
  'In Review':   'https://stuartdonaldson.github.io/GActionSheet/assets/status-inreview.svg',
  'Done':        'https://stuartdonaldson.github.io/GActionSheet/assets/status-done.svg',
  'Closed':      'https://stuartdonaldson.github.io/GActionSheet/assets/status-closed.svg'
};
var _POC_DEFAULT_IMAGE = 'https://stuartdonaldson.github.io/GActionSheet/assets/action-logo-t-32.png';

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
  var formInput     = (e && e.formInput) || {};
  var actionText    = (formInput.poc_actionText  || '').trim();
  var assigneeEmail = (formInput.poc_assignee    || '').trim();
  var status        = formInput.poc_status || 'Open';

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

  // Write row to ActionSheet via WebApp
  var result = _poc_callWebApp('upsert_action_rows', {
    docUrl:   docUrl,
    docTitle: docTitle,
    rows: [{
      namedRangeId:  globalId,
      actionText:    actionText,
      assigneeEmail: assigneeEmail,
      assigneeName:  assigneeEmail,
      status:        status
    }]
  });

  if (!result || result.error) {
    GasLogger.log('CREATE_ACTION_TRIGGER.error', { err: result && result.error });
    return CardService.newActionResponseBuilder()
      .setNavigation(CardService.newNavigation().updateCard(_poc_buildMessageCard('Error', 'Failed to create action: ' + ((result && result.error) || 'unknown error'))))
      .build();
  }

  // Insert chip at cursor via REST API batchUpdate.
  // NOTE: CardService.newSmartChipConfig / newRenderAction do NOT exist in the
  // current GAS runtime (confirmed 2026-05-27 — TypeError). The REST approach
  // is the correct insertion method.
  var insertError = _poc_insertActionChip(doc, N, globalId, actionText, assigneeEmail, status);

  GasLogger.log('CREATE_ACTION_TRIGGER.done', { globalId: globalId, upserted: result.upserted });
  // updateCard is the only allowed response in createActionTriggers context.
  if (insertError) {
    return CardService.newActionResponseBuilder()
      .setNavigation(CardService.newNavigation().updateCard(
        _poc_buildMessageCard('Action saved — insert failed',
          'Action was saved to the sheet but could not be inserted at the cursor.\n\n' + insertError)
      ))
      .build();
  }
  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().updateCard(_poc_buildMessageCard('Action created', actionText)))
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
 * Builds the smart-chip hover preview card for an action URL.
 * Looks up the action in the ActionSheet by namedRangeId.
 *
 * @param {string} url  The matched action URL
 * @returns {GoogleAppsScript.Card_Service.Card}
 */
function _poc_buildPreviewCard(url) {
  var namedRangeId = url.replace(_POC_ACTION_URL_BASE, '');
  var action       = _poc_lookupAction(namedRangeId);

  var title  = (action && action.action)        || namedRangeId || 'GActionSheet Action';
  var status = (action && action.status)         || '';
  var assignee = (action && action.assigneeEmail) || '';

  var header = CardService.newCardHeader()
    .setTitle(title)
    .setImageUrl('https://raw.githubusercontent.com/stuartdonaldson/GActionSheet/master/assets/action-logo-t-32.png')
    .setImageStyle(CardService.ImageStyle.SQUARE);

  var section = CardService.newCardSection();
  if (status) {
    section.addWidget(CardService.newDecoratedText().setTopLabel('Status').setText(status));
  }
  if (assignee) {
    section.addWidget(CardService.newDecoratedText().setTopLabel('Assignee').setText(assignee));
  }
  if (!status && !assignee) {
    section.addWidget(CardService.newTextParagraph().setText('No details available.'));
  }

  return CardService.newCardBuilder()
    .setHeader(header)
    .addSection(section)
    .build();
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
 */
function _poc_insertActionChip(doc, N, globalId, actionText, assigneeEmail, status) {
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
