/**
 * TestFixtures.js
 *
 * GAS entry-point functions for setting up test fixtures and exercising the
 * sync path in isolation. Both functions are selectable in the Apps Script
 * editor function picker and must work when called with no arguments.
 */

/**
 * TABLE_HEADERS order (mirrors DocumentNormalizer.js — 7 columns).
 * Redeclared here as a local constant so TestFixtures.js has no hidden
 * dependency on load order at test time.
 */
var _TF_TABLE_HEADERS = [
  'ID',
  'Assignee Email',
  'Assignee Name',
  'Action',
  'Status',
  'Date Created',
  'Date Modified'
];

/**
 * Holds the structured return value for the most recent setupTestFixtures call.
 * Set by fixture cases that produce meaningful data (e.g. sentinelDateModified).
 * Read by _handleRunFixture in TestWebApp.js to build the HTTP response body.
 * Resets to null at the start of each setupTestFixtures invocation.
 */
var _TF_RESULT = null;

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------


/**
 * Clears all data rows (keeps header in row 1) from a named sheet tab.
 * If the tab does not exist, logs a warning and returns.
 *
 * @param {Spreadsheet} ss
 * @param {string}      tabName
 */
function _tfClearSheetTab(ss, tabName) {
  var sheet = ss.getSheetByName(tabName);
  if (!sheet) {
    GasLogger.log('fixture.warn', { msg: 'Tab not found, skipping clear', tab: tabName });
    return;
  }
  var lastRow = sheet.getLastRow();
  if (lastRow > 1) {
    WriteGuard.wrap(function () {
      sheet.getRange(2, 1, lastRow - 1, SHEET_HEADERS.length).clearContent();
    });
  }
}

/**
 * Replaces the test doc body with just the "Floating Actions" heading paragraph
 * using HEADING1 style. All previous content is removed.
 *
 * @param {Body} body  DocumentApp Body object.
 * @returns {Paragraph}  The heading paragraph that was appended.
 */
function _tfResetDocBody(body) {
  body.clear();
  var heading = body.appendParagraph('Floating Actions');
  heading.setHeading(DocumentApp.ParagraphHeading.HEADING1);
  return heading;
}

/**
 * Appends a tracked-actions table (header row only) to the doc body.
 * GAS requires at least one data row when constructing via appendTable([]),
 * so a blank placeholder row is added and is the only data row.
 *
 * @param {Body} body
 * @returns {Table}
 */
function _tfAppendEmptyTable(body) {
  var blank = [];
  for (var i = 0; i < _TF_TABLE_HEADERS.length; i++) {
    blank.push('');
  }
  var table = body.appendTable([_TF_TABLE_HEADERS, blank]);
  var headerRow = table.getRow(0);
  for (var c = 0; c < _TF_TABLE_HEADERS.length; c++) {
    headerRow.getCell(c).setText(_TF_TABLE_HEADERS[c]);
    headerRow.getCell(c).setBackgroundColor('#D9D9D9');
  }
  return table;
}

/**
 * Appends a data row to the tracked-actions table.
 * Cells must be provided in _TF_TABLE_HEADERS order.
 *
 * @param {Table}    table
 * @param {string[]} cells  7-element array matching TABLE_HEADERS order.
 */
function _tfAppendTableRow(table, cells) {
  var row = table.appendTableRow();
  while (row.getNumCells() < _TF_TABLE_HEADERS.length) {
    row.appendTableCell('');
  }
  for (var i = 0; i < _TF_TABLE_HEADERS.length; i++) {
    row.getCell(i).setText(cells[i] || '');
  }
}

/**
 * Inserts a floating-action paragraph at index 0 of the body (before the
 * section heading) using Normal text style.
 *
 * @param {Body}   body
 * @param {string} text  Full floating-action line, e.g. "AI- @x | ... | ..."
 */
function _tfInsertFloatingAction(body, text) {
  var para = body.insertParagraph(0, text);
  para.setHeading(DocumentApp.ParagraphHeading.NORMAL);
}

/**
 * Inserts a chip-led bulleted list item at the start of the document via the
 * Docs REST API batchUpdate.  Must be called AFTER doc.saveAndClose() so the
 * DocumentApp changes are flushed and the REST API sees the current state.
 *
 * The person chip (@mention) is created with insertPerson; the list format is
 * applied with createParagraphBullets.  Both happen in one atomic batchUpdate.
 *
 * @param {string} token     OAuth2 access token from ScriptApp.getOAuthToken()
 * @param {string} docId     Document ID
 * @param {string} email     Assignee email — must be in the user's contacts or
 *                           Google Workspace directory, otherwise insertPerson
 *                           will fail with a 400.
 * @param {string} actionText Text to append after the chip on the same line
 */
function _tfInsertPersonChipListItem(token, docId, email, actionText) {
  var baseUrl    = 'https://docs.googleapis.com/v1/documents/';
  var authHeader = { 'Authorization': 'Bearer ' + token };

  var getResp = UrlFetchApp.fetch(
    baseUrl + docId + '?fields=body.content',
    { headers: authHeader, muteHttpExceptions: true }
  );
  if (getResp.getResponseCode() !== 200) {
    throw new Error('Docs GET failed (' + getResp.getResponseCode() + '): ' +
                    getResp.getContentText());
  }
  var content = (JSON.parse(getResp.getContentText()).body || {}).content || [];

  var lastParaEndIndex = null;
  for (var ci = content.length - 1; ci >= 0; ci--) {
    if (content[ci].paragraph) {
      lastParaEndIndex = content[ci].endIndex;
      break;
    }
  }
  if (lastParaEndIndex === null) {
    throw new Error('_tfInsertPersonChipListItem: no paragraph found in doc body');
  }

  // Insert a chip-led bullet item: 'AI: ' placeholder + PERSON chip + action text.
  // _assignPlaceholderTokens (called during sync) converts 'AI: ' → 'AI-N:'.
  var insertAt = lastParaEndIndex - 1;
  var aiPlaceholder = 'AI: ';
  var aiPlaceholderLen = aiPlaceholder.length;
  var requests = [
    { insertText: { location: { index: insertAt }, text: '\n' } },
    { createParagraphBullets: {
        range: { startIndex: lastParaEndIndex, endIndex: lastParaEndIndex + 1 },
        bulletPreset: 'BULLET_DISC_CIRCLE_SQUARE'
      }
    },
    { insertText: {
        location: { index: lastParaEndIndex },
        text: aiPlaceholder
      }
    },
    { insertPerson: {
        personProperties: { email: email },
        location: { index: lastParaEndIndex + aiPlaceholderLen }
      }
    },
    { insertText: {
        location: { index: lastParaEndIndex + aiPlaceholderLen + 1 },
        text: ' ' + actionText
      }
    }
  ];

  var batchResp = UrlFetchApp.fetch(
    baseUrl + docId + ':batchUpdate',
    {
      method: 'post',
      headers: Object.assign({ 'Content-Type': 'application/json' }, authHeader),
      payload: JSON.stringify({ requests: requests }),
      muteHttpExceptions: true
    }
  );
  if (batchResp.getResponseCode() !== 200) {
    throw new Error('Docs batchUpdate failed (' + batchResp.getResponseCode() + '): ' +
                    batchResp.getContentText());
  }
}

/**
 * Appends a plain-text bullet list item to the end of the document via the
 * Docs REST API, without opening the document through DocumentApp.
 *
 * Strategy: GET the doc to find the last paragraph's endIndex, then split it
 * by inserting \n before its terminal \n, then insert the text and apply
 * createParagraphBullets — all in one batchUpdate.
 *
 * @param {string} token   OAuth token (ScriptApp.getOAuthToken())
 * @param {string} docId   Google Doc ID
 * @param {string} text    Text content of the new list item (no \n needed)
 */
function _tfAppendTextListItem(token, docId, text) {
  var baseUrl    = 'https://docs.googleapis.com/v1/documents/';
  var authHeader = { 'Authorization': 'Bearer ' + token };

  var getResp = UrlFetchApp.fetch(
    baseUrl + docId + '?fields=body.content',
    { headers: authHeader, muteHttpExceptions: true }
  );
  if (getResp.getResponseCode() !== 200) {
    throw new Error('_tfAppendTextListItem GET failed: HTTP ' + getResp.getResponseCode());
  }
  var content = (JSON.parse(getResp.getContentText()).body || {}).content || [];

  var lastParaEndIndex = null;
  for (var ci = content.length - 1; ci >= 0; ci--) {
    if (content[ci].paragraph) {
      lastParaEndIndex = content[ci].endIndex;
      break;
    }
  }
  if (lastParaEndIndex === null) {
    throw new Error('_tfAppendTextListItem: no paragraph found in doc');
  }

  // Split the last paragraph by inserting \n before its terminal \n at
  // (lastParaEndIndex - 1).  After the split, an empty paragraph begins at
  // lastParaEndIndex.  Then fill that paragraph with the text and apply
  // BULLET formatting.  All three requests apply in order within one call.
  var insertAt = lastParaEndIndex - 1;
  var textLen  = text.length;

  var requests = [
    { insertText: { location: { index: insertAt }, text: '\n' } },
    { insertText: { location: { index: lastParaEndIndex }, text: text } },
    { createParagraphBullets: {
        range: { startIndex: lastParaEndIndex, endIndex: lastParaEndIndex + textLen + 1 },
        bulletPreset: 'BULLET_DISC_CIRCLE_SQUARE'
      }
    }
  ];

  var batchResp = UrlFetchApp.fetch(
    baseUrl + docId + ':batchUpdate',
    {
      method: 'post',
      headers: Object.assign({ 'Content-Type': 'application/json' }, authHeader),
      payload: JSON.stringify({ requests: requests }),
      muteHttpExceptions: true
    }
  );
  if (batchResp.getResponseCode() !== 200) {
    throw new Error('_tfAppendTextListItem batchUpdate failed: HTTP ' +
                    batchResp.getResponseCode() + ': ' +
                    batchResp.getContentText().substring(0, 200));
  }
}

/**
 * Appends an AI-N: token + PERSON chip bulleted list item to the end of the document.
 *
 * Inserts: <aiNPrefix> <chip(email)> <actionText> as a bullet.
 * The scanner reads the PERSON chip's getName() (Google contact resolution) rather
 * than deriving a display name from the email username.
 *
 * @param {string} token      OAuth2 access token from ScriptApp.getOAuthToken()
 * @param {string} docId      Document ID
 * @param {string} aiNPrefix  Token prefix, e.g. "AI-9:"
 * @param {string} email      Assignee email (must be in contacts or Workspace directory)
 * @param {string} actionText Text to append after the chip
 */
function _tfAppendAINPersonChipListItem(token, docId, aiNPrefix, email, actionText) {
  var baseUrl    = 'https://docs.googleapis.com/v1/documents/';
  var authHeader = { 'Authorization': 'Bearer ' + token };

  var getResp = UrlFetchApp.fetch(
    baseUrl + docId + '?fields=body.content',
    { headers: authHeader, muteHttpExceptions: true }
  );
  if (getResp.getResponseCode() !== 200) {
    throw new Error('_tfAppendAINPersonChipListItem GET failed: HTTP ' + getResp.getResponseCode());
  }
  var content = (JSON.parse(getResp.getContentText()).body || {}).content || [];

  var lastParaEndIndex = null;
  for (var ci = content.length - 1; ci >= 0; ci--) {
    if (content[ci].paragraph) {
      lastParaEndIndex = content[ci].endIndex;
      break;
    }
  }
  if (lastParaEndIndex === null) {
    throw new Error('_tfAppendAINPersonChipListItem: no paragraph found in doc body');
  }

  var insertAt  = lastParaEndIndex - 1;
  var prefix    = aiNPrefix + ' ';   // e.g. "AI-9: "
  var prefixLen = prefix.length;

  var requests = [
    { insertText: { location: { index: insertAt }, text: '\n' } },
    { createParagraphBullets: {
        range: { startIndex: lastParaEndIndex, endIndex: lastParaEndIndex + 1 },
        bulletPreset: 'BULLET_DISC_CIRCLE_SQUARE'
      }
    },
    { insertText: {
        location: { index: lastParaEndIndex },
        text: prefix
      }
    },
    { insertPerson: {
        personProperties: { email: email },
        location: { index: lastParaEndIndex + prefixLen }
      }
    },
    { insertText: {
        location: { index: lastParaEndIndex + prefixLen + 1 },
        text: ' ' + actionText
      }
    }
  ];

  var batchResp = UrlFetchApp.fetch(
    baseUrl + docId + ':batchUpdate',
    {
      method: 'post',
      headers: Object.assign({ 'Content-Type': 'application/json' }, authHeader),
      payload: JSON.stringify({ requests: requests }),
      muteHttpExceptions: true
    }
  );
  if (batchResp.getResponseCode() !== 200) {
    throw new Error('_tfAppendAINPersonChipListItem batchUpdate failed: HTTP ' +
                    batchResp.getResponseCode() + ': ' +
                    batchResp.getContentText().substring(0, 200));
  }
}

/**
 * Appends a chip-led bulleted list item to the END of the document via the
 * Docs REST API, without clearing existing content.
 *
 * Mirrors _tfAppendTextListItem but inserts a PERSON chip before the action text.
 * Must be called AFTER doc.saveAndClose() so the REST API sees current content.
 *
 * @param {string} token      OAuth2 access token from ScriptApp.getOAuthToken()
 * @param {string} docId      Document ID
 * @param {string} email      Assignee email (must be in contacts or Workspace directory)
 * @param {string} actionText Text to append after the chip on the same line
 */
function _tfAppendPersonChipListItem(token, docId, email, actionText) {
  var baseUrl    = 'https://docs.googleapis.com/v1/documents/';
  var authHeader = { 'Authorization': 'Bearer ' + token };

  var getResp = UrlFetchApp.fetch(
    baseUrl + docId + '?fields=body.content',
    { headers: authHeader, muteHttpExceptions: true }
  );
  if (getResp.getResponseCode() !== 200) {
    throw new Error('_tfAppendPersonChipListItem GET failed: HTTP ' + getResp.getResponseCode());
  }
  var content = (JSON.parse(getResp.getContentText()).body || {}).content || [];

  var lastParaEndIndex = null;
  for (var ci = content.length - 1; ci >= 0; ci--) {
    if (content[ci].paragraph) {
      lastParaEndIndex = content[ci].endIndex;
      break;
    }
  }
  if (lastParaEndIndex === null) {
    throw new Error('_tfAppendPersonChipListItem: no paragraph found in doc');
  }

  // Mirror _tfAppendTextListItem's splitting strategy:
  //   1. Insert \n at (lastParaEndIndex - 1) to split the last (mandatory) paragraph.
  //   2. Apply bullet formatting to the new paragraph starting at lastParaEndIndex.
  //   3. Insert 'AI: ' placeholder text at lastParaEndIndex (_assignPlaceholderTokens converts → AI-N:).
  //   4. Insert the person chip after the placeholder.
  //   5. Insert the action text after the chip.
  var insertAt  = lastParaEndIndex - 1;
  var aiPlaceholder = 'AI: ';
  var aiPlaceholderLen = aiPlaceholder.length;

  var requests = [
    { insertText: { location: { index: insertAt }, text: '\n' } },
    { createParagraphBullets: {
        range: { startIndex: lastParaEndIndex, endIndex: lastParaEndIndex + 1 },
        bulletPreset: 'BULLET_DISC_CIRCLE_SQUARE'
      }
    },
    { insertText: {
        location: { index: lastParaEndIndex },
        text: aiPlaceholder
      }
    },
    { insertPerson: {
        personProperties: { email: email },
        location: { index: lastParaEndIndex + aiPlaceholderLen }
      }
    },
    { insertText: {
        location: { index: lastParaEndIndex + aiPlaceholderLen + 1 },
        text: ' ' + actionText
      }
    }
  ];

  var batchResp = UrlFetchApp.fetch(
    baseUrl + docId + ':batchUpdate',
    {
      method: 'post',
      headers: Object.assign({ 'Content-Type': 'application/json' }, authHeader),
      payload: JSON.stringify({ requests: requests }),
      muteHttpExceptions: true
    }
  );
  if (batchResp.getResponseCode() !== 200) {
    throw new Error('_tfAppendPersonChipListItem batchUpdate failed: HTTP ' +
                    batchResp.getResponseCode() + ': ' +
                    batchResp.getContentText().substring(0, 200));
  }
}

/**
 * Builds a sheet row array in SHEET_HEADERS order.
 *
 * SHEET_HEADERS = [globalId, ID, Assignee Email, Assignee Name, Action,
 *                  Status, Document, Date Created, Date Modified, Sync Status]
 *
 * @param {object} opts
 * @param {string}  opts.globalId  globalId (format: {docId}/AI-{N}); empty until first sync.
 * @param {string|number} opts.id
 * @param {string}  opts.assigneeEmail
 * @param {string}  opts.assigneeName
 * @param {string}  opts.action
 * @param {string}  opts.status
 * @param {string}  opts.docFormula   Full =HYPERLINK(…) formula string.
 * @param {Date}    opts.dateCreated
 * @param {Date}    opts.dateModified
 * @param {string}  opts.syncStatus
 * @returns {Array}  Row array aligned to SHEET_HEADERS.
 */
function _tfSheetRow(opts) {
  var fileId = opts.fileId || (opts.globalId ? opts.globalId.split('/AI-')[0] : '');
  return [
    opts.globalId || '',
    fileId,
    opts.id,
    opts.assigneeEmail || '',
    opts.assigneeName || '',
    opts.action || '',
    opts.status || '',
    opts.docFormula || '',
    opts.dateCreated || '',
    opts.dateModified || '',
    opts.syncStatus || ''
  ];
}

/**
 * Appends a data row to the "Actions" sheet tab using WriteGuard.
 * Logs a warning and skips if the tab does not exist.
 *
 * @param {Spreadsheet} ss
 * @param {Array}       rowData  8-element row array.
 */
function _tfAppendSheetRow(ss, rowData) {
  var sheet = ss.getSheetByName('Actions');
  if (!sheet) {
    GasLogger.log('fixture.warn', { msg: 'Actions tab not found, skipping row insert' });
    return;
  }
  WriteGuard.wrap(function () {
    sheet.appendRow(rowData);
  });
}

// ---------------------------------------------------------------------------
// Public entry-point
// ---------------------------------------------------------------------------

/**
 * Sets up test fixtures for the given scenario.
 * When called from the function picker, scenario defaults to 'default'.
 *
 * @param {string} [scenario] - Name of the fixture scenario to set up.
 */
function setupTestFixtures(scenario, data) {
  var resolvedScenario = scenario || 'default';
  data = data || {};
  _TF_RESULT = null; // reset for this invocation
  var _SF = CONTRACT_SCHEMA.sheetAction.columnsByField;
  try {
    // -- Read test IDs from script properties --------------------------------
    var props = PropertiesService.getScriptProperties();
    var testDocId   = props.getProperty('TEST_DOC_ID');
    var testSheetId = props.getProperty('TEST_SHEET_ID');

    if (!testDocId || !testSheetId) {
      GasLogger.log('fixture.error', {
        msg: 'TEST_DOC_ID and/or TEST_SHEET_ID script properties not set'
      });
      return;
    }

    var doc = DocumentApp.openById(testDocId);
    var ss  = SpreadsheetApp.openById(testSheetId);
    var body = doc.getBody();

    var docUrl     = doc.getUrl();
    var docFormula = '=HYPERLINK("' + docUrl + '","Test Doc")';

    // -- Step 1: seed per scenario; track whether doc was already closed ----
    var docAlreadyClosed = false;
    switch (resolvedScenario) {

      case 'uc_a_clear':
        // Flush DocumentApp writes before using the Docs REST API.
        doc.saveAndClose();
        docAlreadyClosed = true;
        var ucaToken  = ScriptApp.getOAuthToken();
        var ucaEmail  = props.getProperty('TEST_ASSIGNEE_EMAIL')
                     || Session.getActiveUser().getEmail();
        var ucaChipOk = false;
        try {
          _tfInsertPersonChipListItem(ucaToken, testDocId, ucaEmail,
                                      'AC1: Review the project budget');
          ucaChipOk = true;
        } catch (chipErr) {
          GasLogger.log('fixture.uc_a_clear', {
            assigneeEmail: ucaEmail,
            error: 'chip insert: ' + chipErr.message
          });
        }
        if (ucaChipOk) {
          try {
            _tfAppendTextListItem(
              ucaToken, testDocId,
              'jane.smith@example.com AC1: Approve the project proposal (In Progress)'
            );
            GasLogger.log('fixture.uc_a_clear', {
              assigneeEmail: ucaEmail, emailItemInserted: true
            });
          } catch (emailErr) {
            GasLogger.log('fixture.uc_a_clear', {
              assigneeEmail: ucaEmail,
              error: 'email item append: ' + emailErr.message
            });
          }
        }
        break;

      case 'uc_a_permutations':
        // Items (4 total; 3 produce rows, 1 is a negative case):
        //   1. Chip item WITH explicit "(Done)" status token
        //   2. Email item with NO status token (defaults to Open)
        //   3. Email with underscore username bob_jones@example.com (name → "Bob Jones")
        //   4. Plain-text list item with no chip and no email (no row expected)
        doc.saveAndClose();
        docAlreadyClosed = true;
        var permToken = ScriptApp.getOAuthToken();
        var permEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                     || Session.getActiveUser().getEmail();
        var permChipOk = false;
        try {
          _tfInsertPersonChipListItem(permToken, testDocId, permEmail,
                                      'Perm: Schedule the kickoff (Done)');
          permChipOk = true;
        } catch (permChipErr) {
          GasLogger.log('fixture.uc_a_permutations', {
            error: 'chip insert: ' + permChipErr.message
          });
        }
        if (permChipOk) {
          var permErrors = [];
          try {
            _tfAppendTextListItem(permToken, testDocId,
              'AI: jane.smith@example.com Perm: Draft the committee agenda');
          } catch (e2) { permErrors.push('email-no-status: ' + e2.message); }
          try {
            _tfAppendTextListItem(permToken, testDocId,
              'AI: bob_jones@example.com Perm: Review the meeting minutes');
          } catch (e3) { permErrors.push('underscore-email: ' + e3.message); }
          try {
            _tfAppendTextListItem(permToken, testDocId,
              'Perm: Write the project documentation');
          } catch (e4) { permErrors.push('plain-text: ' + e4.message); }
          if (permErrors.length > 0) {
            GasLogger.log('fixture.uc_a_permutations', { error: permErrors.join('; ') });
          } else {
            GasLogger.log('fixture.uc_a_permutations', { itemsInserted: 4 });
          }
        }
        break;

      case 'uc_c_pending_sync_refresh': {
        var ucCPendingToken = ScriptApp.getOAuthToken();
        var ucCPendingEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                          || Session.getActiveUser().getEmail();

        doc.saveAndClose();
        docAlreadyClosed = true;

        _tfInsertPersonChipListItem(ucCPendingToken, testDocId, ucCPendingEmail,
                                    'UCC-PENDING: Schedule the kickoff meeting (Open)');
        _tfAppendPersonChipListItem(ucCPendingToken, testDocId, ucCPendingEmail,
                                    'UCC-PENDING: Review the project charter (In Review)');

        syncDocument(testDocId);
        insertTrackerTable(testDocId);

        _tfAppendPersonChipListItem(ucCPendingToken, testDocId, ucCPendingEmail,
                                    'UCC-PENDING: Add the follow-up action (Open)');

        GasLogger.log('fixture.uc_c_pending_sync_refresh', { trackerRows: 2, pendingFloatingActions: 3 });
        break;
      }

      case 'uc1_new_floating':
      case 'default':
        // Legacy: AI-prefix floating action — sync assigns id=1.
        _tfInsertFloatingAction(
          body,
          'AI- @test@example.com | Fix the bug | Open | 2026-01-01 | 2026-01-01'
        );
        break;

      case 'ac1':
        // Legacy: new unnumbered floating action (old naming).
        _tfInsertFloatingAction(
          body,
          'AI- @test@example.com | Test action one | Open | 2026-01-01 | 2026-01-01'
        );
        break;

      case 'ac2':
        // Legacy: existing ID preserved.
        _tfInsertFloatingAction(
          body,
          'AI-5 @test@example.com | Test action five | Open | 2026-01-01 | 2026-01-01'
        );
        break;

      case 'ac3':
      case 'uc3_doc_wins':
        // Document wins: doc dateModified (2026-05-10) is 1 day newer than
        // the sheet row's dateModified (2026-05-09).
        _tfInsertFloatingAction(
          body,
          'AI-1 @test@example.com | UCS-3DW: Fix the bug | Done | 2026-01-01 | 2026-05-10'
        );
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'UCS-3DW: Fix the bug',
          status: 'Open',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: new Date('2026-05-09')
        }));
        break;

      case 'ac4':
      case 'uc3_sheet_wins':
        // Sheet wins: sheet dateModified (2026-05-10) is 1 day newer than
        // the floating action's dateModified (2026-05-09).
        _tfInsertFloatingAction(
          body,
          'AI-1 @test@example.com | UCS-3SW: Fix the bug | Open | 2026-01-01 | 2026-05-09'
        );
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'UCS-3SW: Fix the bug',
          status: 'In Review',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: new Date('2026-05-10')
        }));
        break;

      case 'ac5':
      case 'uc_idempotent':
        // Already fully synced: consistent state in floating paragraph, table row,
        // and sheet row — all with the same values and dateModified. Sync is a no-op.
        _tfInsertFloatingAction(
          body,
          'AI-1 @test@example.com | UCSIDM: Completed action | Done | 2026-01-01 | 2026-04-01'
        );
        // Append table with matching data row.
        var tableAc5 = _tfAppendEmptyTable(body);
        _tfAppendTableRow(tableAc5, [
          '1',
          'test@example.com',
          '',
          'UCSIDM: Completed action',
          'Done',
          '2026-01-01',
          '2026-04-01'
        ]);
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'UCSIDM: Completed action',
          status: 'Done',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: new Date('2026-04-01')
        }));
        break;

      case 'uc2_new_table_row':
        // User-added data row in table, no ID, no dates — sync should assign id=2
        // (id=1 is pre-existing in the sheet, so next available is 2).
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'UCS-2: Fix the bug',
          status: 'Open',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: new Date('2026-01-01')
        }));
        var tableUc2 = _tfAppendEmptyTable(body);
        _tfAppendTableRow(tableUc2, [
          '',
          'test@example.com',
          '',
          'UCS-2: Review the PR',
          '',
          '',
          ''
        ]);
        break;

      case 'uc4_archive':
        // Archive-eligible row (id=1, Closed, old dateModified, no floating action)
        // plus an active row (id=2, Open, table row present).
        var archiveDateUc4 = new Date(Date.now() - 35 * 24 * 60 * 60 * 1000);
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'UCS-4: Fix the bug',
          status: 'Closed',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: archiveDateUc4
        }));
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 2,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'UCS-4: Review the PR',
          status: 'Open',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: new Date('2026-01-01')
        }));
        var tableUc4 = _tfAppendEmptyTable(body);
        _tfAppendTableRow(tableUc4, [
          '2',
          'test@example.com',
          '',
          'UCS-4: Review the PR',
          'Open',
          '2026-01-01',
          '2026-01-01'
        ]);
        _tfInsertFloatingAction(
          body,
          'AI-2 @test@example.com | UCS-4: Review the PR | Open | 2026-01-01 | 2026-01-01'
        );
        break;

      case 'uc5_bare_reference':
        // Bare reference floating action (just ID, no other fields).
        var tableUc5 = _tfAppendEmptyTable(body);
        _tfAppendTableRow(tableUc5, [
          '5',
          'test@example.com',
          '',
          'Deploy to staging',
          'Open',
          '2026-01-01',
          '2026-01-01'
        ]);
        _tfInsertFloatingAction(body, 'AI-5');
        break;

      case 'uc6_revert_local_edit':
        // Floating paragraph diverges from table row (different action and status),
        // same dateModified — table wins and floating action is reverted.
        var tableUc6 = _tfAppendEmptyTable(body);
        _tfAppendTableRow(tableUc6, [
          '3',
          'test@example.com',
          '',
          'UCS-6: Write tests',
          'Open',
          '2026-01-01',
          '2026-01-01'
        ]);
        _tfInsertFloatingAction(
          body,
          'AI-3 @test@example.com | UCS-6: Write tests (locally edited) | Done | 2026-01-01 | 2026-01-01'
        );
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 3,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'UCS-6: Write tests',
          status: 'Open',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: new Date('2026-01-01')
        }));
        break;

      case 'archive':
        // Archive-eligible row: no floating action, sheet row Status=Closed,
        // Date Modified 35 days before today.
        var archiveDate = new Date(Date.now() - 35 * 24 * 60 * 60 * 1000);
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'Archived action',
          status: 'Closed',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: archiveDate
        }));
        break;

      case 'no_section':
        // Doc body has no heading at all — normalizer must auto-create the section.
        body.clear();
        break;

      case 'no_table':
        // Doc has heading but no table — normalizer must auto-create the table.
        break;

      case 'onedit':
        // Row with a known Date Modified — onEdit on a mutable field (Assignee)
        // must stamp Date Modified with the current timestamp.
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'Test action',
          status: 'Todo',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: new Date('2026-01-01')
        }));
        break;

      case 'onedit_id':
        // Row with a known Date Modified — onEdit on the immutable ID column must
        // NOT update Date Modified.
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'Test action',
          status: 'Todo',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: new Date('2026-01-01')
        }));
        break;

      case 'discovery':
        var discProps = PropertiesService.getScriptProperties();
        var recentId = discProps.getProperty('DISCOVERY_RECENT_DOC_ID');
        var staleId  = discProps.getProperty('DISCOVERY_STALE_DOC_ID');
        if (!recentId) {
          var recentDoc = DocumentApp.create('GActionSheet Test - Discovery Recent');
          recentId = recentDoc.getId();
          recentDoc.saveAndClose();
          discProps.setProperty('DISCOVERY_RECENT_DOC_ID', recentId);
        }
        if (!staleId) {
          var staleDoc = DocumentApp.create('GActionSheet Test - Discovery Stale');
          staleId = staleDoc.getId();
          staleDoc.saveAndClose();
          discProps.setProperty('DISCOVERY_STALE_DOC_ID', staleId);
          GasLogger.log('fixture.warn', {
            msg: 'Discovery stale doc created now — it will not be stale for 8 days. ' +
                 'Run this scenario again after 8 days or set DISCOVERY_STALE_DOC_ID manually.',
            staleId: staleId
          });
        }
        GasLogger.log('fixture.discovery.ids', {
          recentId: recentId,
          staleId: staleId
        });
        break;

      case 'discovery_subfolder':
        var sfProps = PropertiesService.getScriptProperties();
        var subfolderId = sfProps.getProperty('DISCOVERY_SUBFOLDER_ID');
        var subfolderDocId = sfProps.getProperty('DISCOVERY_SUBFOLDER_DOC_ID');
        var parentFolderId = sfProps.getProperty('DOC_FOLDER_ID');
        if (!parentFolderId) {
          GasLogger.log('fixture.error', { msg: 'DOC_FOLDER_ID script property not set — run ensureSheetStructure first' });
          break;
        }
        if (!subfolderId) {
          var parentFolder = DriveApp.getFolderById(parentFolderId);
          var subFolder = parentFolder.createFolder('GActionSheet Test - Discovery Subfolder');
          subfolderId = subFolder.getId();
          sfProps.setProperty('DISCOVERY_SUBFOLDER_ID', subfolderId);
        }
        if (!subfolderDocId) {
          var sfFolder = DriveApp.getFolderById(subfolderId);
          var sfDoc = DocumentApp.create('GActionSheet Test - Discovery Subfolder Doc');
          DriveApp.getFileById(sfDoc.getId()).moveTo(sfFolder);
          subfolderDocId = sfDoc.getId();
          sfDoc.saveAndClose();
          sfProps.setProperty('DISCOVERY_SUBFOLDER_DOC_ID', subfolderDocId);
        }
        GasLogger.log('fixture.discovery.subfolder.id', { subfolderDocId: subfolderDocId });
        break;

      case 'uc_blank_status':
        // Floating action with blank status — sync must default to Open.
        _tfInsertFloatingAction(
          body,
          'AI- @test@example.com | Fix the bug |  | 2026-01-01 | 2026-01-01'
        );
        break;

      // -----------------------------------------------------------------------
      // UC-B scenarios: update an action from either side and converge.
      //
      // All three build a canonical 7-item doc (6 detected + 1 negative), run
      // an intermediate sync to anchor named ranges and seed the ActionSheet,
      // then apply mutations before returning.  The Python test triggers the
      // final convergence sync and asserts the outcome.
      //
      // Canonical floating action variants:
      //   Var 1: chip + "Review the budget report (Open)"         testAssigneeEmail
      //   Var 2: chip + "Draft the Q3 plan (In Review)"           testAssigneeEmail
      //   Var 3: chip + "Update the meeting notes"  (→ Open)      testAssigneeEmail
      //   Var 4: email + "Schedule the follow-up (Done)"          jane.smith@example.com
      //   Var 5: email + "Approve the budget proposal"  (→ Open)  jane.smith@example.com
      //   Var 6: email + "Review the Q2 report"  (→ Open)         bob_jones@example.com
      //   Var 7: plain text (negative) — never appears in ActionSheet
      //   Var 8: chip + "Prioritize the backlog items (Backlog)"  testAssigneeEmail  → status-other.png
      // -----------------------------------------------------------------------

      case 'uc_b_doc_wins':
      case 'uc_b_sheet_wins':
      case 'uc_b_sheet_assignee_wins':
      case 'uc_b_conflict': {
        // -- Phase 1: build canonical 7-item state ---------------------------
        var ucbPrefix = resolvedScenario === 'uc_b_doc_wins'   ? 'UCB-DW: '
                      : resolvedScenario === 'uc_b_sheet_wins' ? 'UCB-SW: '
                      : resolvedScenario === 'uc_b_sheet_assignee_wins' ? 'UCB-SA: '
                      : 'UCB-CF: ';

        doc.saveAndClose();
        docAlreadyClosed = true;

        var ucbToken = ScriptApp.getOAuthToken();
        var ucbEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                    || Session.getActiveUser().getEmail();

        // Var 1: chip + action text + (Open)
        _tfInsertPersonChipListItem(ucbToken, testDocId, ucbEmail,
                                    ucbPrefix + 'Review the budget report (Open)');
        // Var 2: chip + action text + (In Review)
        _tfAppendPersonChipListItem(ucbToken, testDocId, ucbEmail,
                                    ucbPrefix + 'Draft the Q3 plan (In Review)');
        // Var 3: chip + action text only (no status → Open)
        _tfAppendPersonChipListItem(ucbToken, testDocId, ucbEmail,
                                    ucbPrefix + 'Update the meeting notes');
        // Var 4: email + action text + (Done)
        _tfAppendTextListItem(ucbToken, testDocId,
                              'jane.smith@example.com ' + ucbPrefix + 'Schedule the follow-up (Done)');
        // Var 5: email + action text only (no status → Open)
        _tfAppendTextListItem(ucbToken, testDocId,
                              'jane.smith@example.com ' + ucbPrefix + 'Approve the budget proposal');
        // Var 6: underscore email + action text (no status → Open)
        _tfAppendTextListItem(ucbToken, testDocId,
                              'bob_jones@example.com ' + ucbPrefix + 'Review the Q2 report');
        // Var 8: chip + action text + non-standard status → exercises status-other.png fallback
        _tfAppendPersonChipListItem(ucbToken, testDocId, ucbEmail,
                                    ucbPrefix + 'Prioritize the backlog items (Backlog)');
        // Var 7: plain text (negative — no chip, no email)
        _tfAppendTextListItem(ucbToken, testDocId,
                              ucbPrefix + 'Complete the project documentation');

        // -- Phase 2: intermediate sync to anchor named ranges + seed sheet --
        syncDocument(testDocId);

        // -- Phase 3: apply scenario-specific mutations -----------------------
        if (resolvedScenario === 'uc_b_doc_wins') {
          // Mutate variants 1-3 on the doc side (chip text children).
          // The final sync should propagate these to the ActionSheet.
          var ucbDocMut = DocumentApp.openById(testDocId);
          var ucbBody   = ucbDocMut.getBody();
          var ucbN      = ucbBody.getNumChildren();
          for (var ucbI = 0; ucbI < ucbN; ucbI++) {
            var ucbChild = ucbBody.getChild(ucbI);
            if (ucbChild.getType() !== DocumentApp.ElementType.LIST_ITEM) continue;
            var ucbItem = ucbChild.asListItem();
            if (ucbItem.getNumChildren() === 0) continue;
            if (ucbItem.getChild(0).getType() !== DocumentApp.ElementType.PERSON) continue;
            if ((ucbItem.getChild(0).asPerson().getEmail() || '') !== ucbEmail) continue;
            // Find the TEXT child that carries the action text + status
            for (var ucbJ = 1; ucbJ < ucbItem.getNumChildren(); ucbJ++) {
              if (ucbItem.getChild(ucbJ).getType() !== DocumentApp.ElementType.TEXT) continue;
              var ucbTextEl = ucbItem.getChild(ucbJ).asText();
              var ucbTxt    = ucbTextEl.getText();
              if (ucbTxt.indexOf(ucbPrefix + 'Review the budget report') !== -1) {
                // Var 1: (Open) → (Done)
                ucbTextEl.setText(ucbTxt.replace('(Open)', '(Done)'));
              } else if (ucbTxt.indexOf(ucbPrefix + 'Draft the Q3 plan') !== -1) {
                // Var 2: change action text (preserve status token)
                ucbTextEl.setText(ucbTxt.replace(ucbPrefix + 'Draft the Q3 plan', ucbPrefix + 'Draft the revised Q3 plan'));
              } else if (ucbTxt.indexOf(ucbPrefix + 'Update the meeting notes') !== -1) {
                // Var 3: set (In Progress) status; strip any existing token first
                // (the intermediate sync may have normalized this item to (Open))
                var ucbBase3 = ucbTxt.trim().replace(/\s*\([^)]*\)\s*$/, '');
                ucbTextEl.setText(ucbBase3 + ' (In Progress)');
              }
              break;
            }
          }
          ucbDocMut.saveAndClose();
          GasLogger.log('fixture.uc_b_doc_wins', { mutationsApplied: 3, assigneeEmail: ucbEmail });

        } else if (resolvedScenario === 'uc_b_sheet_wins') {
          // Mutate variants 4-6 on the sheet side.
          // The final sync should propagate these to the doc floating actions.
          var ucbSheet  = ss.getSheetByName('Actions');
          var ucbLastR  = ucbSheet ? ucbSheet.getLastRow() : 1;
          if (ucbSheet && ucbLastR > 1) {
            var ucbData    = ucbSheet.getRange(2, 1, ucbLastR - 1, SHEET_HEADERS.length).getValues();
            // Filter by testDocId (Document column formula) to avoid matching rows from prior
            // test sessions that accumulated in the sheet (accumulate-without-reset design).
            var ucbDocFmls = ucbSheet.getRange(2, _SF.document_formula, ucbLastR - 1, 1).getFormulas();
            for (var ucbRi = 0; ucbRi < ucbData.length; ucbRi++) {
              if (ucbDocFmls[ucbRi][0].indexOf(testDocId) === -1) continue;
              var ucbAssignee = ucbData[ucbRi][_SF.assignee_email - 1];
              var ucbAction   = ucbData[ucbRi][_SF.action_text - 1];
              if (ucbAssignee === 'jane.smith@example.com') {
                if (ucbAction.indexOf(ucbPrefix + 'Schedule the follow-up') !== -1) {
                  // Var 4: Status Done → Closed; set Dirty so sheet wins conflict resolution.
                  var ucbRow4 = ucbRi + 2;
                  WriteGuard.wrap(function () {
                    ucbSheet.getRange(ucbRow4, 7).setValue('Closed');
                    ucbSheet.getRange(ucbRow4, 10).setValue(new Date());
                    ucbSheet.getRange(ucbRow4, 11).setValue('Dirty');
                  });
                } else if (ucbAction.indexOf(ucbPrefix + 'Approve the budget proposal') !== -1) {
                  // Var 5: Action text change; set Dirty so sheet wins conflict resolution.
                  var ucbRow5 = ucbRi + 2;
                  WriteGuard.wrap(function () {
                    ucbSheet.getRange(ucbRow5, 6).setValue(ucbPrefix + 'Approve the revised budget');
                    ucbSheet.getRange(ucbRow5, 10).setValue(new Date());
                    ucbSheet.getRange(ucbRow5, 11).setValue('Dirty');
                  });
                }
              } else if (ucbAssignee === 'bob_jones@example.com' &&
                         ucbAction.indexOf(ucbPrefix + 'Review the Q2 report') !== -1) {
                // Var 6: Status Open → In Review; set Dirty so sheet wins conflict resolution.
                var ucbRow6 = ucbRi + 2;
                WriteGuard.wrap(function () {
                  ucbSheet.getRange(ucbRow6, 7).setValue('In Review');
                  ucbSheet.getRange(ucbRow6, 10).setValue(new Date());
                  ucbSheet.getRange(ucbRow6, 11).setValue('Dirty');
                });
              }
            }
          }
          GasLogger.log('fixture.uc_b_sheet_wins', { mutationsApplied: 3 });

        } else if (resolvedScenario === 'uc_b_sheet_assignee_wins') {
          // Mutate variant 6 assignee on the sheet side only.
          // The final sync should propagate the assignee change to the doc.
          var ucbASheet = ss.getSheetByName('Actions');
          var ucbALastR = ucbASheet ? ucbASheet.getLastRow() : 1;
          if (ucbASheet && ucbALastR > 1) {
            var ucbAData    = ucbASheet.getRange(2, 1, ucbALastR - 1, SHEET_HEADERS.length).getValues();
            var ucbADocFmls = ucbASheet.getRange(2, _SF.document_formula, ucbALastR - 1, 1).getFormulas();
            for (var ucbARi = 0; ucbARi < ucbAData.length; ucbARi++) {
              if (ucbADocFmls[ucbARi][0].indexOf(testDocId) === -1) continue;
              var ucbAAssignee = ucbAData[ucbARi][_SF.assignee_email - 1];
              var ucbAAction   = ucbAData[ucbARi][_SF.action_text - 1];
              if (ucbAAssignee === 'bob_jones@example.com' &&
                  ucbAAction.indexOf(ucbPrefix + 'Review the Q2 report') !== -1) {
                var ucbARow = ucbARi + 2;
                WriteGuard.wrap(function () {
                  ucbASheet.getRange(ucbARow, 4).setValue('jane.smith@example.com');
                  ucbASheet.getRange(ucbARow, 5).setValue('Jane Smith');
                  ucbASheet.getRange(ucbARow, 10).setValue(new Date());
                  ucbASheet.getRange(ucbARow, 11).setValue('Dirty');
                });
                break;
              }
            }
          }
          GasLogger.log('fixture.uc_b_sheet_assignee_wins', { mutationsApplied: 1 });

        } else {
          // uc_b_conflict: one action where the doc is the newer edit (var 1),
          // one where the sheet is the newer edit (var 4).
          var ucbCSheet = ss.getSheetByName('Actions');
          var ucbCLastR = ucbCSheet ? ucbCSheet.getLastRow() : 1;
          if (ucbCSheet && ucbCLastR > 1) {
            var ucbCData    = ucbCSheet.getRange(2, 1, ucbCLastR - 1, SHEET_HEADERS.length).getValues();
            // Filter by testDocId to avoid matching rows from prior sessions in the shared sheet.
            var ucbCDocFmls = ucbCSheet.getRange(2, _SF.document_formula, ucbCLastR - 1, 1).getFormulas();
            for (var ucbCRi = 0; ucbCRi < ucbCData.length; ucbCRi++) {
              if (ucbCDocFmls[ucbCRi][0].indexOf(testDocId) === -1) continue;
              var ucbCAssignee = ucbCData[ucbCRi][_SF.assignee_email - 1];
              var ucbCAction   = ucbCData[ucbCRi][_SF.action_text - 1];
              if (ucbCAssignee === ucbEmail &&
                  ucbCAction.indexOf(ucbPrefix + 'Review the budget report') !== -1) {
                // Stale sheet Date Modified far in the past so the doc edit wins.
                var ucbCRowA = ucbCRi + 2;
                WriteGuard.wrap(function () {
                  ucbCSheet.getRange(ucbCRowA, 10).setValue(new Date('2020-01-01'));
                });
              }
            }
          }
          // Mutate var 1 on doc side (doc is now "newer" per Date Modified)
          var ucbCDoc  = DocumentApp.openById(testDocId);
          var ucbCBody = ucbCDoc.getBody();
          var ucbCN    = ucbCBody.getNumChildren();
          for (var ucbCI = 0; ucbCI < ucbCN; ucbCI++) {
            var ucbCChild = ucbCBody.getChild(ucbCI);
            if (ucbCChild.getType() !== DocumentApp.ElementType.LIST_ITEM) continue;
            var ucbCItem = ucbCChild.asListItem();
            if (ucbCItem.getNumChildren() === 0) continue;
            if (ucbCItem.getChild(0).getType() !== DocumentApp.ElementType.PERSON) continue;
            if ((ucbCItem.getChild(0).asPerson().getEmail() || '') !== ucbEmail) continue;
            for (var ucbCJ = 1; ucbCJ < ucbCItem.getNumChildren(); ucbCJ++) {
              if (ucbCItem.getChild(ucbCJ).getType() !== DocumentApp.ElementType.TEXT) continue;
              var ucbCTxtEl = ucbCItem.getChild(ucbCJ).asText();
              var ucbCTxt   = ucbCTxtEl.getText();
              if (ucbCTxt.indexOf(ucbPrefix + 'Review the budget report') !== -1) {
                ucbCTxtEl.setText(ucbCTxt.replace('(Open)', '(In Progress)'));
                break;
              }
              break;
            }
          }
          ucbCDoc.saveAndClose();
          // Mutate var 4 on sheet side — set Dirty so sheet wins conflict resolution.
          if (ucbCSheet && ucbCLastR > 1) {
            var ucbCData2 = ucbCSheet.getRange(2, 1, ucbCLastR - 1, SHEET_HEADERS.length).getValues();
            for (var ucbCRi2 = 0; ucbCRi2 < ucbCData2.length; ucbCRi2++) {
              if (ucbCDocFmls[ucbCRi2][0].indexOf(testDocId) === -1) continue;
              if (ucbCData2[ucbCRi2][_SF.assignee_email - 1] === 'jane.smith@example.com' &&
                  ucbCData2[ucbCRi2][_SF.action_text - 1].indexOf(ucbPrefix + 'Schedule the follow-up') !== -1) {
                var ucbCRowB = ucbCRi2 + 2;
                WriteGuard.wrap(function () {
                  ucbCSheet.getRange(ucbCRowB, 7).setValue('Closed');
                  ucbCSheet.getRange(ucbCRowB, 10).setValue(new Date());
                  ucbCSheet.getRange(ucbCRowB, 11).setValue('Dirty');
                });
                break;
              }
            }
          }
          GasLogger.log('fixture.uc_b_conflict', { conflictSetupDone: true });
        }
        break;
      }

      // -----------------------------------------------------------------------
      // UC-C scenarios: insert / refresh the in-doc tracker table (GTaskSheet-mol-bgq)
      //
      // All three scenarios accumulate on the shared clone doc without resetting.
      // Scenario prefixes: UCC-FIRST: / UCC-REFRESH: / UCC-VIEWONLY:
      //
      // RED PHASE: insertTrackerTable() is defined by the UC-C implementation
      // (GTaskSheet-mol-vzk). Until that lands these scenarios will log an error
      // tag and the Python tests will fail as expected.
      // -----------------------------------------------------------------------

      case 'uc_c_first_insert': {
        // Insert two chip-led floating actions, sync to anchor them, then call
        // insertTrackerTable for the first time. Logs fixture.uc_c_first_insert.
        var ucCFIToken = ScriptApp.getOAuthToken();
        var ucCFIEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                      || Session.getActiveUser().getEmail();

        doc.saveAndClose();
        docAlreadyClosed = true;

        _tfInsertPersonChipListItem(ucCFIToken, testDocId, ucCFIEmail,
                                    'UCC-FIRST: Schedule the kickoff meeting (Open)');
        _tfAppendPersonChipListItem(ucCFIToken, testDocId, ucCFIEmail,
                                    'UCC-FIRST: Review the project charter (In Review)');

        syncDocument(testDocId);
        insertTrackerTable(testDocId);

        GasLogger.log('fixture.uc_c_first_insert', { rowsInserted: 2 });
        break;
      }

      case 'uc_c_refresh': {
        // Insert two chip-led FAs, sync+insert tracker, then simulate close+add:
        //   close: set first UCC-REFRESH: row Status=Closed in sheet
        //   add: append a new chip-led FA
        // Final sync+refresh should reflect both changes.
        var ucCRefToken = ScriptApp.getOAuthToken();
        var ucCRefEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                       || Session.getActiveUser().getEmail();

        doc.saveAndClose();
        docAlreadyClosed = true;

        _tfInsertPersonChipListItem(ucCRefToken, testDocId, ucCRefEmail,
                                    'UCC-REFRESH: Approve the proposal (Open)');
        _tfAppendPersonChipListItem(ucCRefToken, testDocId, ucCRefEmail,
                                    'UCC-REFRESH: Update the risk register (Done)');

        syncDocument(testDocId);
        insertTrackerTable(testDocId);

        // Close the first UCC-REFRESH: row in the sheet.
        var ucCRefActSheet = ss.getSheetByName('Actions');
        var ucCRefLastR    = ucCRefActSheet ? ucCRefActSheet.getLastRow() : 1;
        if (ucCRefActSheet && ucCRefLastR > 1) {
          var ucCRefData = ucCRefActSheet.getRange(2, 1, ucCRefLastR - 1, _SF.action_text).getValues();
          var ucCRefFmls = ucCRefActSheet.getRange(2, _SF.document_formula, ucCRefLastR - 1, 1).getFormulas();
          for (var ucCRefI = 0; ucCRefI < ucCRefData.length; ucCRefI++) {
            if (ucCRefFmls[ucCRefI][0].indexOf(testDocId) !== -1 &&
                (ucCRefData[ucCRefI][_SF.action_text - 1] || '').indexOf('UCC-REFRESH: Approve') !== -1) {
              var ucCRefRowNum = ucCRefI + 2;
              WriteGuard.wrap(function () {
                ucCRefActSheet.getRange(ucCRefRowNum, 7).setValue('Closed');
                ucCRefActSheet.getRange(ucCRefRowNum, 10).setValue(new Date());
              });
              break;
            }
          }
        }

        // Add a new chip-led FA.
        _tfAppendPersonChipListItem(ucCRefToken, testDocId, ucCRefEmail,
                                    'UCC-REFRESH: Draft the status report');

        // Sync to propagate the Closed status to the doc and anchor the new FA.
        syncDocument(testDocId);
        insertTrackerTable(testDocId);

        GasLogger.log('fixture.uc_c_refresh', { refreshDone: true });
        break;
      }

      case 'uc_c_view_only': {
        // Insert two chip-led FAs, sync+insert tracker, then directly edit a tracker
        // table cell (simulating a forbidden user edit). A second insertTrackerTable
        // call should discard the edit and render the correct values.
        var ucCVOToken = ScriptApp.getOAuthToken();
        var ucCVOEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                      || Session.getActiveUser().getEmail();

        doc.saveAndClose();
        docAlreadyClosed = true;

        _tfInsertPersonChipListItem(ucCVOToken, testDocId, ucCVOEmail,
                                    'UCC-VIEWONLY: Prepare the budget summary (Open)');
        _tfAppendPersonChipListItem(ucCVOToken, testDocId, ucCVOEmail,
                                    'UCC-VIEWONLY: Finalize the agenda (Open)');

        syncDocument(testDocId);
        insertTrackerTable(testDocId);

        // Directly edit the first data cell of the tracker table to dirty it.
        var ucCVODoc  = DocumentApp.openById(testDocId);
        var ucCVOBody = ucCVODoc.getBody();
        var ucCVOHdg  = false;
        var ucCVOTbl  = null;
        var ucCVON    = ucCVOBody.getNumChildren();
        for (var ucCVOI = 0; ucCVOI < ucCVON; ucCVOI++) {
          var ucCVOChild = ucCVOBody.getChild(ucCVOI);
          if (!ucCVOHdg) {
            if ((ucCVOChild.getType() === DocumentApp.ElementType.PARAGRAPH ||
                 ucCVOChild.getType() === DocumentApp.ElementType.LIST_ITEM) &&
                (ucCVOChild.getText().trim() === 'Action Item Summary' ||
                 ucCVOChild.getText().trim() === '=== Tracked Actions ===')) {
              ucCVOHdg = true;
            }
          } else if (ucCVOChild.getType() === DocumentApp.ElementType.TABLE) {
            ucCVOTbl = ucCVOChild.asTable();
            break;
          }
        }
        if (ucCVOTbl && ucCVOTbl.getNumRows() > 1) {
          ucCVOTbl.getRow(1).getCell(0).setText(
            ucCVOTbl.getRow(1).getCell(0).getText() + '-EDITED'
          );
        }
        ucCVODoc.saveAndClose();

        // Refresh — should overwrite the direct edit with the correct values.
        insertTrackerTable(testDocId);

        GasLogger.log('fixture.uc_c_view_only', { viewOnlyTestDone: true });
        break;
      }

      // -----------------------------------------------------------------------
      // Sync Status column scenarios (GTaskSheet-ly5 AC1–AC7)
      //
      // Each scenario accumulates on the shared clone doc without resetting.
      // Scenario prefixes: SS-DEL: / SS-NF: / SS-REC: / SS-EDIT: / SS-ARCH:
      // -----------------------------------------------------------------------

      case 'sync_status_migration': {
        // Simulate a legacy sheet missing the Sync Status column by deleting col 10
        // (if present), then call ensureSheetStructure() to trigger migration.
        var ssMigSheet = ss.getSheetByName('Actions');
        if (ssMigSheet && ssMigSheet.getMaxColumns() >= 10) {
          WriteGuard.wrap(function () {
            ssMigSheet.deleteColumn(10);
          });
        }
        ensureSheetStructure();
        GasLogger.log('fixture.sync_status_migration', { migrationTriggered: true });
        break;
      }

      case 'sync_status_deleted': {
        // Insert a chip-led floating action (SS-DEL: prefix), run an intermediate
        // sync to anchor it, then DELETE THE ENTIRE PARAGRAPH from the doc so the
        // final sync writes 'Deleted' to Sync Status.
        //
        // Deleting only the named range (not the paragraph) causes re-anchoring on
        // the next sync, which the duplicate detector treats as a stale duplicate
        // and removes — never writing 'Deleted'.  Removing the paragraph entirely
        // means no floating action survives to match, so the orphan path fires cleanly.
        var ssDelToken = ScriptApp.getOAuthToken();
        var ssDelEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                      || Session.getActiveUser().getEmail();

        doc.saveAndClose();
        docAlreadyClosed = true;

        _tfInsertPersonChipListItem(ssDelToken, testDocId, ssDelEmail,
                                    'SS-DEL: Review the access log');

        syncDocument(testDocId);

        // After the first sync, read the NR ID for the SS-DEL row from the sheet.
        // GAS does NOT auto-remove named ranges when their paragraph is deleted, so
        // the NR would appear in allDocGlobalIds during the second syncDocument,
        // causing the orphan-detection loop to skip the row (activeNrIdSet check).
        // We must explicitly remove the NR from the doc after paragraph deletion.
        var ssDelSheet   = ss.getSheetByName('Actions');
        var ssDelLastRow = ssDelSheet ? ssDelSheet.getLastRow() : 1;
        var ssDelNRId    = null;
        if (ssDelSheet && ssDelLastRow > 1) {
          var ssDelSheetData = ssDelSheet.getRange(2, 1, ssDelLastRow - 1, _SF.action_text).getValues();
          var ssDelSheetFmls = ssDelSheet.getRange(2, _SF.document_formula, ssDelLastRow - 1, 1).getFormulas();
          for (var sdi = 0; sdi < ssDelSheetData.length; sdi++) {
            if (ssDelSheetFmls[sdi][0].indexOf(testDocId) !== -1 &&
                (ssDelSheetData[sdi][_SF.action_text - 1] || '').indexOf('SS-DEL:') !== -1) {
              ssDelNRId = ssDelSheetData[sdi][0]; // col 1 = globalId
              break;
            }
          }
        }

        // Remove the SS-DEL: list-item paragraph from the doc body.
        // Append a blank paragraph first — GAS throws if you try to remove
        // the last element in a document section.
        var ssDelDoc  = DocumentApp.openById(testDocId);
        var ssDelBody = ssDelDoc.getBody();
        ssDelBody.appendParagraph(''); // guard against last-element removal error
        var ssDelN    = ssDelBody.getNumChildren();
        for (var ssDelCI = ssDelN - 1; ssDelCI >= 0; ssDelCI--) {
          var ssDelChild = ssDelBody.getChild(ssDelCI);
          if (ssDelChild.getType() !== DocumentApp.ElementType.LIST_ITEM) continue;
          if (ssDelChild.asListItem().getText().indexOf('SS-DEL:') === -1) continue;
          ssDelBody.removeChild(ssDelChild);
          break;
        }

        // Explicitly remove the named range — GAS doesn't auto-delete it on paragraph removal.
        if (ssDelNRId) {
          var ssDelDocNRs = ssDelDoc.getNamedRanges();
          for (var ssDelNRI = 0; ssDelNRI < ssDelDocNRs.length; ssDelNRI++) {
            if (ssDelDocNRs[ssDelNRI].getId() === ssDelNRId) {
              ssDelDocNRs[ssDelNRI].remove();
              break;
            }
          }
        }

        ssDelDoc.saveAndClose();

        syncDocument(testDocId);

        GasLogger.log('fixture.sync_status_deleted', { scenario: 'paragraph-deleted' });
        break;
      }

      case 'sync_status_doc_not_found': {
        // Append a row referencing a non-existent doc ID, then call syncDocument
        // with that fake ID — SyncManager should catch openById failure and write
        // 'Doc Not Found' to every row in the sheet referencing this fake doc.
        var ssNFDocId   = '1_FAKEID_SYNCSTATUS_DOCNOTFOUND_FIXTURE_001';
        var ssNFFormula = '=HYPERLINK("https://docs.google.com/document/d/' +
                          ssNFDocId + '/edit","SS-NF: Fake Doc")';
        WriteGuard.wrap(function () {
          var ssNFSheet = ss.getSheetByName('Actions');
          if (ssNFSheet) {
            ssNFSheet.appendRow([
              'SS-NF-ANCHOR-FAKE-001',
              'SS-NF-ANCHOR-FAKE-001',  // fileId == globalId prefix (fake, no /AI-)
              999,
              'test@example.com',
              '',
              'SS-NF: Review the compliance doc',
              'Open',
              ssNFFormula,
              new Date('2026-01-01'),
              new Date('2026-01-01'),
              ''
            ]);
          }
        });

        try {
          syncDocument(ssNFDocId);
        } catch (ssNFErr) {
          GasLogger.log('fixture.sync_status_doc_not_found.warn', { msg: ssNFErr.message });
        }

        GasLogger.log('fixture.sync_status_doc_not_found', { fakeDocId: ssNFDocId });
        break;
      }

      case 'sync_status_recovery': {
        // Insert a chip-led floating action (SS-REC: prefix), anchor it via sync,
        // then manually set Sync Status = 'Deleted' to simulate a previously-flagged
        // state.  A final sync finds the named range still present and clears the flag.
        var ssRecToken = ScriptApp.getOAuthToken();
        var ssRecEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                      || Session.getActiveUser().getEmail();

        doc.saveAndClose();
        docAlreadyClosed = true;

        _tfInsertPersonChipListItem(ssRecToken, testDocId, ssRecEmail,
                                    'SS-REC: Update the access policy');

        syncDocument(testDocId);

        var ssRecSheet = ss.getSheetByName('Actions');
        var ssRecLastR = ssRecSheet ? ssRecSheet.getLastRow() : 1;
        if (ssRecSheet && ssRecLastR > 1) {
          var ssRecData = ssRecSheet.getRange(2, 1, ssRecLastR - 1, _SF.action_text).getValues();
          var ssRecFmls = ssRecSheet.getRange(2, _SF.document_formula, ssRecLastR - 1, 1).getFormulas();
          for (var ssRecI = 0; ssRecI < ssRecData.length; ssRecI++) {
            if (ssRecFmls[ssRecI][0].indexOf(testDocId) !== -1 &&
                (ssRecData[ssRecI][_SF.action_text - 1] || '').indexOf('SS-REC:') !== -1) {
              var ssRecRowNum = ssRecI + 2;
              WriteGuard.wrap(function () {
                ssRecSheet.getRange(ssRecRowNum, 11).setValue('Deleted');
              });
              break;
            }
          }
        }

        syncDocument(testDocId);

        GasLogger.log('fixture.sync_status_recovery', { setupDone: true });
        break;
      }

      case 'sync_status_on_edit': {
        // Insert a chip-led floating action (SS-EDIT: prefix), sync to stamp a
        // real Date Modified, then call onEdit() with a synthetic col-11 event to
        // verify that editing Sync Status does NOT update Date Modified.
        // Logs sentinelDateModified so the Python test can assert no change.
        var ssEditToken = ScriptApp.getOAuthToken();
        var ssEditEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                       || Session.getActiveUser().getEmail();

        doc.saveAndClose();
        docAlreadyClosed = true;

        _tfInsertPersonChipListItem(ssEditToken, testDocId, ssEditEmail,
                                    'SS-EDIT: Approve the request');

        syncDocument(testDocId);

        var ssEditSheet    = ss.getSheetByName('Actions');
        var ssEditLastR    = ssEditSheet ? ssEditSheet.getLastRow() : 1;
        var ssEditSentinel = null;
        var ssEditRowNum   = -1;
        if (ssEditSheet && ssEditLastR > 1) {
          var ssEditData = ssEditSheet.getRange(2, 1, ssEditLastR - 1, 11).getValues();
          var ssEditFmls = ssEditSheet.getRange(2, 8, ssEditLastR - 1, 1).getFormulas();
          for (var ssEditI = 0; ssEditI < ssEditData.length; ssEditI++) {
            if (ssEditFmls[ssEditI][0].indexOf(testDocId) !== -1 &&
                (ssEditData[ssEditI][5] || '').indexOf('SS-EDIT:') !== -1) {
              ssEditSentinel = ssEditData[ssEditI][9]; // col 10 (0-indexed: 9) = Date Modified
              ssEditRowNum   = ssEditI + 2;
              break;
            }
          }
        }

        if (ssEditRowNum > 0 && ssEditSheet) {
          var ssEditFakeEvent = { range: ssEditSheet.getRange(ssEditRowNum, 11) };
          onActionSheetEdit(ssEditFakeEvent);
        }

        _TF_RESULT = {
          tag:  'fixture.sync_status_on_edit',
          data: { sentinelDateModified: ssEditSentinel }
        };
        GasLogger.log('fixture.sync_status_on_edit', { sentinelDateModified: ssEditSentinel });
        break;
      }

      case 'sync_status_archive': {
        // Insert a chip-led floating action (SS-ARCH: prefix), anchor it via sync,
        // then mark it Closed with a 35-day-old Date Modified and Sync Status='Deleted'
        // so the archive sweep moves it from Actions to Archive sheet.
        var ssArchToken = ScriptApp.getOAuthToken();
        var ssArchEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                       || Session.getActiveUser().getEmail();

        doc.saveAndClose();
        docAlreadyClosed = true;

        _tfInsertPersonChipListItem(ssArchToken, testDocId, ssArchEmail,
                                    'SS-ARCH: Archive the policy doc');

        syncDocument(testDocId);
        SpreadsheetApp.flush(); // ensure syncDocument's appended row is visible to ss

        var ssArchSheet   = ss.getSheetByName('Actions');
        var ssArchLastR   = ssArchSheet ? ssArchSheet.getLastRow() : 1;
        var ssArchOldDate = new Date(Date.now() - 35 * 24 * 60 * 60 * 1000);
        if (ssArchSheet && ssArchLastR > 1) {
          var ssArchData = ssArchSheet.getRange(2, 1, ssArchLastR - 1, _SF.action_text).getValues();
          var ssArchFmls = ssArchSheet.getRange(2, _SF.document_formula, ssArchLastR - 1, 1).getFormulas();
          for (var ssArchI = 0; ssArchI < ssArchData.length; ssArchI++) {
            if (ssArchFmls[ssArchI][0].indexOf(testDocId) !== -1 &&
                (ssArchData[ssArchI][_SF.action_text - 1] || '').indexOf('SS-ARCH:') !== -1) {
              var ssArchRowNum = ssArchI + 2;
              WriteGuard.wrap(function () {
                ssArchSheet.getRange(ssArchRowNum, 7).setValue('Closed');
                ssArchSheet.getRange(ssArchRowNum, 10).setValue(ssArchOldDate);
                ssArchSheet.getRange(ssArchRowNum, 11).setValue('Deleted');
              });
              break;
            }
          }
        }

        ArchiveManager.archive(ss);

        GasLogger.log('fixture.sync_status_archive', { archiveTriggered: true });
        break;
      }

      case 'sync_document': {
        // Sync the clone doc. Called between fixture steps in the HTTP test runner.
        // testDocId was stored in TEST_DOC_ID by _handleRunFixture before calling us.
        syncDocument(testDocId);
        _TF_RESULT = { tag: 'fixture.sync_document', data: { synced: true, docId: testDocId } };
        docAlreadyClosed = true;
        break;
      }

      case 'begin_journey_session': {
        // Empty-create a fresh journey doc (§16.11 #1 — never a template clone).
        // Does NOT update TEST_DOC_ID or TEST_DOC_TEMPLATE_ID — safe to run
        // alongside an active begin_test_session clone in the same pytest session.
        var bjsNow    = new Date();
        var bjsDate   = Utilities.formatDate(bjsNow, Session.getScriptTimeZone(), 'yyyyMMdd');
        var bjsHex    = ('000' + Math.floor(Math.random() * 0xFFFF).toString(16)).slice(-4);
        var bjsName   = 'GActionSheet-Test-journey-' + bjsDate + '-' + bjsHex;
        var bjsSheetId = PropertiesService.getScriptProperties().getProperty('TEST_SHEET_ID');
        var bjsFolderIter = DriveApp.getFileById(bjsSheetId).getParents();
        var bjsParent = bjsFolderIter.hasNext() ? bjsFolderIter.next() : DriveApp.getRootFolder();
        var bjsDoc    = DocumentApp.create(bjsName);
        DriveApp.getFileById(bjsDoc.getId()).moveTo(bjsParent);
        _TF_RESULT = {
          tag:  'fixture.begin_journey_session',
          data: { ok: true, docId: bjsDoc.getId(), docName: bjsName, docUrl: bjsDoc.getUrl() }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'end_journey_session': {
        // Trash the journey clone identified by testDocId.
        DriveApp.getFileById(testDocId).setTrashed(true);
        _TF_RESULT = { tag: 'fixture.end_journey_session', data: { trashed: testDocId } };
        docAlreadyClosed = true;
        break;
      }

      case 'scenario_journey_seed': {
        // Insert the four §14 AI-token seed items into the journey doc.
        doc.saveAndClose();
        docAlreadyClosed = true;
        var sjsToken = ScriptApp.getOAuthToken();
        _tfAppendTextListItem(sjsToken, testDocId,
          'AI: This tag and text confirms creation of an unassigned action item');
        _tfAppendTextListItem(sjsToken, testDocId,
          'AI: aitest@example.com This tag and email address along with this text confirms the creation of an action item with an assignee.');
        _tfAppendTextListItem(sjsToken, testDocId,
          'AI-5: This tag and text confirms creation of an action item with id AI-5 pre-assigning the specific ID.');
        _tfAppendAINPersonChipListItem(sjsToken, testDocId,
          'AI-9:', 'minister@northlakeuu.org',
          'This tag, email and text should result in the creation of the assignee as a person chip,' +
          ' working within our Northlake domain this has a username of \'Northlake Minister\'' +
          ' which should appear in the chip.');
        _TF_RESULT = { tag: 'fixture.scenario_journey_seed', data: { itemsSeeded: 4 } };
        break;
      }

      case 'insert_tracker_table': {
        // Standalone tracker table insert — no seeding bundled in.
        doc.saveAndClose();
        docAlreadyClosed = true;
        insertTrackerTable(testDocId);
        _TF_RESULT = { tag: 'fixture.insert_tracker_table', data: { inserted: true } };
        break;
      }

      case 'scenario_delete_unassigned': {
        // Find the §14 unassigned action by its exact seeded text and delete it.
        var sduTarget  = 'This tag and text confirms creation of an unassigned action item';
        var sduActions = _scanFloatingActions(doc);
        var sduId      = '';
        for (var sdui = 0; sdui < sduActions.length; sdui++) {
          if (sduActions[sdui].actionText === sduTarget) {
            sduId = sduActions[sdui].globalId || '';
            break;
          }
        }
        if (!sduId) {
          GasLogger.log('fixture.scenario_delete_unassigned', { error: 'not found', target: sduTarget });
          _TF_RESULT = { tag: 'fixture.scenario_delete_unassigned', data: { error: 'not found' } };
          break;
        }
        doc.saveAndClose();
        docAlreadyClosed = true;
        sidebarDeleteAction(sduId, testDocId);
        _TF_RESULT = { tag: 'fixture.scenario_delete_unassigned', data: { globalId: sduId } };
        break;
      }

      case 'ensure_sheet_structure': {
        // Ensure the ActionSheet has the correct tab layout and headers.
        // Used by test_infrastructure.py before header-layout assertions.
        ensureSheetStructure();
        _TF_RESULT = { tag: 'fixture.ensure_sheet_structure', data: { ensured: true } };
        docAlreadyClosed = true;
        break;
      }

      case 'assert_team_access': {
        // Calls the assertTeamAccess(teamId, ss) security gate (GTaskSheet-me6w.5)
        // and reports the outcome instead of letting the thrown error propagate,
        // so the test harness can assert on TeamNotFound / TeamAccessDenied.
        var atfTeamId = data.teamId || '';
        try {
          assertTeamAccess(atfTeamId, ss);
          _TF_RESULT = { tag: 'fixture.assert_team_access', data: { ok: true, teamId: atfTeamId } };
        } catch (atfErr) {
          _TF_RESULT = { tag: 'fixture.assert_team_access', data: { ok: false, error: atfErr.message } };
        }
        docAlreadyClosed = true;
        break;
      }

      case 'sidebar_set_status': {
        // Mutation: change an action from "Open" to "Done" using sidebarSetStatus.
        // Resolves globalId by scanning floating actions for the target text.
        var sssTargetText = 'AC1: Review the project budget';
        var sssNewStatus  = 'Done';
        var sssFloating   = _scanFloatingActions(doc);
        var sssNrId       = '';
        for (var ssi = 0; ssi < sssFloating.length; ssi++) {
          if (sssFloating[ssi].actionText === sssTargetText) {
            sssNrId = sssFloating[ssi].globalId || '';
            break;
          }
        }
        if (!sssNrId) {
          GasLogger.log('fixture.sidebar_set_status', { error: 'action not found', target: sssTargetText });
          _TF_RESULT = { tag: 'fixture.sidebar_set_status', data: { error: 'action not found' } };
          docAlreadyClosed = false;
          break;
        }
        doc.saveAndClose();
        docAlreadyClosed = true;
        sidebarSetStatus(sssNrId, sssNewStatus, testDocId);
        _TF_RESULT = { tag: 'fixture.sidebar_set_status', data: { globalId: sssNrId, newStatus: sssNewStatus } };
        break;
      }

      case 'sidebar_delete_action': {
        // Mutation: delete an action using sidebarDeleteAction.
        // Resolves globalId by scanning floating actions for the target text + email.
        var sdaTargetText  = 'AC1: Approve the project proposal';
        var sdaTargetEmail = 'jane.smith@example.com';
        var sdaFloating    = _scanFloatingActions(doc);
        var sdaNrId        = '';
        for (var sdai = 0; sdai < sdaFloating.length; sdai++) {
          var sdaFa = sdaFloating[sdai];
          if (sdaFa.actionText === sdaTargetText && sdaFa.assigneeEmail === sdaTargetEmail) {
            sdaNrId = sdaFa.globalId || '';
            break;
          }
        }
        if (!sdaNrId) {
          GasLogger.log('fixture.sidebar_delete_action', { error: 'action not found', target: sdaTargetText });
          _TF_RESULT = { tag: 'fixture.sidebar_delete_action', data: { error: 'action not found' } };
          docAlreadyClosed = false;
          break;
        }
        doc.saveAndClose();
        docAlreadyClosed = true;
        sidebarDeleteAction(sdaNrId, testDocId);
        _TF_RESULT = { tag: 'fixture.sidebar_delete_action', data: { globalId: sdaNrId } };
        break;
      }

      case 'ai_n_token_scan': {
        // Append a bare AI: paragraph, then call syncDocument so the scanner upgrades it
        // to AI-N: and writes a sheet row.  Returns the assigned globalId and action text
        // so the Python test can assert format and cross-check the sheet row.
        var antText = 'ANT: verify AI-N token format and globalId assignment';
        body.appendParagraph('AI: ' + antText);
        doc.saveAndClose();
        docAlreadyClosed = true;
        syncDocument(testDocId);
        SpreadsheetApp.flush();
        var antSheet = ss.getSheetByName('Actions');
        var antData  = antSheet.getDataRange().getValues();
        var antHdr   = antData[0];
        var antColId = antHdr.indexOf('globalId');
        var antColAc = antHdr.indexOf('Action');
        var antColDo = antHdr.indexOf('Document');
        var antRow   = null;
        for (var anti = 1; anti < antData.length; anti++) {
          if ((antData[anti][antColAc] || '').indexOf(antText) !== -1 &&
              (antData[anti][antColId] || '').indexOf(testDocId) !== -1) {
            antRow = antData[anti];
            break;
          }
        }
        var antGlobalId = antRow ? (antRow[antColId] || '') : '';
        _TF_RESULT = {
          tag:  'fixture.ai_n_token_scan',
          data: { globalId: antGlobalId, actionText: antText, docId: testDocId }
        };
        break;
      }

      case 'begin_test_session': {
        // masterDocId was stored in TEST_DOC_ID by _handleRunFixture from the HTTP payload.
        // beginTestSession creates a named clone and updates TEST_DOC_ID to the clone.
        beginTestSession(testDocId);
        var btsCloneId = props.getProperty('TEST_DOC_ID');
        _TF_RESULT = {
          tag:  'fixture.begin_test_session',
          data: { cloneId: btsCloneId }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'end_test_session': {
        // Trash the clone and restore TEST_DOC_ID to the master template.
        endTestSession(testDocId);
        _TF_RESULT = { tag: 'fixture.end_test_session', data: {} };
        docAlreadyClosed = true;
        break;
      }

      case 'verify_consistency': {
        _TF_RESULT = {
          tag: 'fixture.verify_consistency',
          data: verifyConsistencyForTest(testDocId, data.expected || null)
        };
        docAlreadyClosed = true;
        break;
      }

      case 'get_team_scope': {
        // Returns the document's Drive appProperty 'teamScope' (GTaskSheet-me6w.6).
        var gtsDocId = data.docId || testDocId;
        var gtsToken = ScriptApp.getOAuthToken();
        _TF_RESULT = {
          tag: 'fixture.get_team_scope',
          data: { teamScope: _getDocAppProperty(gtsDocId, 'teamScope', gtsToken) || '' }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'get_docdata_row': {
        // Returns the DocData row for fileId (default testDocId), or null (GTaskSheet-me6w.6).
        var gddFileId = data.fileId || testDocId;
        _TF_RESULT = {
          tag: 'fixture.get_docdata_row',
          data: { row: _readDocDataRow(ss, gddFileId) }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'get_team_data_rows': {
        // Returns all TeamData rows ({teamId, folderId, contact}) (GTaskSheet-zc21).
        // Used to verify TeamData fixture setup never mutates pre-existing rows.
        _TF_RESULT = {
          tag: 'fixture.get_team_data_rows',
          data: { rows: _readTeamDataRows(ss) }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'set_docdata_row': {
        // Upserts a DocData row, overriding only the fields supplied (GTaskSheet-me6w.6).
        // Used to set up the UpdateDoc-override scenarios (S3/S7) on a row already
        // created by a prior sync.
        var sdrFileId = data.fileId || testDocId;
        var sdrExisting = _readDocDataRow(ss, sdrFileId) || {
          docName: '', docModified: new Date(), syncStatus: '', teamId: '',
          actionCount: 0, resolvedCount: 0
        };
        var sdrTeamId     = data.hasOwnProperty('teamId')     ? data.teamId     : sdrExisting.teamId;
        var sdrSyncStatus = data.hasOwnProperty('syncStatus') ? data.syncStatus : sdrExisting.syncStatus;
        var sdrUpdated = _getOrUpsertDocDataRow(
          ss, sdrFileId,
          sdrExisting.docName, sdrExisting.docModified,
          sdrTeamId, sdrSyncStatus,
          sdrExisting.actionCount, sdrExisting.resolvedCount
        );
        _TF_RESULT = { tag: 'fixture.set_docdata_row', data: { row: sdrUpdated } };
        docAlreadyClosed = true;
        break;
      }

      case 'move_doc_to_folder': {
        // Moves a doc into the given folder (GTaskSheet-me6w.6) — used by the
        // sticky-after-move scenario (S8) and the folder-hierarchy fixture.
        var mdtfDocId    = data.docId || testDocId;
        var mdtfFolderId = data.folderId;
        if (!mdtfFolderId) throw new Error('move_doc_to_folder: folderId required');
        DriveApp.getFileById(mdtfDocId).moveTo(DriveApp.getFolderById(mdtfFolderId));
        _TF_RESULT = {
          tag: 'fixture.move_doc_to_folder',
          data: { docId: mdtfDocId, folderId: mdtfFolderId }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'setup_team_scope_fixture': {
        // Idempotent (check-exists-or-create, no cleanup) folder hierarchy +
        // TeamData rows for the S1a/S1b/S1c/S8 folder-walk scenarios
        // (GTaskSheet-me6w.6). Folder IDs are persisted in script properties so
        // repeat runs reuse the same Drive folders.
        //
        //   testTeamA (parent, registered TestTeamA)
        //   |- testTeamAChild (child, registered TestTeamAChild)
        //   `- testTeamAMid (unregistered)
        //      `- testTeamADeep (unregistered, no TeamData row)
        var stsfProps = PropertiesService.getScriptProperties();

        var stsfRootIter = DriveApp.getFileById(testSheetId).getParents();
        var stsfRoot = stsfRootIter.hasNext() ? stsfRootIter.next() : DriveApp.getRootFolder();

        var stsfParentId = stsfProps.getProperty('TEAMSCOPE_FOLDER_A');
        var stsfParent = stsfParentId ? DriveApp.getFolderById(stsfParentId)
                                       : stsfRoot.createFolder('GActionSheet Test - TeamScope A');
        stsfParentId = stsfParent.getId();
        stsfProps.setProperty('TEAMSCOPE_FOLDER_A', stsfParentId);

        var stsfChildId = stsfProps.getProperty('TEAMSCOPE_FOLDER_A_CHILD');
        var stsfChild = stsfChildId ? DriveApp.getFolderById(stsfChildId)
                                     : stsfParent.createFolder('GActionSheet Test - TeamScope A Child');
        stsfChildId = stsfChild.getId();
        stsfProps.setProperty('TEAMSCOPE_FOLDER_A_CHILD', stsfChildId);

        var stsfMidId = stsfProps.getProperty('TEAMSCOPE_FOLDER_A_MID');
        var stsfMid = stsfMidId ? DriveApp.getFolderById(stsfMidId)
                                 : stsfParent.createFolder('GActionSheet Test - TeamScope A Mid');
        stsfMidId = stsfMid.getId();
        stsfProps.setProperty('TEAMSCOPE_FOLDER_A_MID', stsfMidId);

        var stsfDeepId = stsfProps.getProperty('TEAMSCOPE_FOLDER_A_DEEP');
        var stsfDeep = stsfDeepId ? DriveApp.getFolderById(stsfDeepId)
                                   : stsfMid.createFolder('GActionSheet Test - TeamScope A Deep');
        stsfDeepId = stsfDeep.getId();
        stsfProps.setProperty('TEAMSCOPE_FOLDER_A_DEEP', stsfDeepId);

        // Idempotent TeamData rows: TestTeamA -> A, TestTeamAChild -> Child
        var stsfTeamSheet = _getOrCreateSheet(ss, 'TeamData');
        if (stsfTeamSheet.getLastRow() < 1) {
          stsfTeamSheet.getRange(1, 1, 1, 3).setValues([['Team Id', 'Folder Id', 'Contact']]).setFontWeight('bold');
        }
        var stsfRows = _readTeamDataRows(ss);
        var stsfHasA = false, stsfHasChild = false;
        for (var stsfI = 0; stsfI < stsfRows.length; stsfI++) {
          if (stsfRows[stsfI].teamId === 'TestTeamA') stsfHasA = true;
          if (stsfRows[stsfI].teamId === 'TestTeamAChild') stsfHasChild = true;
        }
        var stsfNewRows = [];
        if (!stsfHasA) stsfNewRows.push(['TestTeamA', stsfParentId, '']);
        if (!stsfHasChild) stsfNewRows.push(['TestTeamAChild', stsfChildId, '']);
        if (stsfNewRows.length > 0) {
          var stsfLastRow = stsfTeamSheet.getLastRow();
          stsfTeamSheet.getRange(stsfLastRow + 1, 1, stsfNewRows.length, 3).setValues(stsfNewRows);
        }

        _TF_RESULT = {
          tag: 'fixture.setup_team_scope_fixture',
          data: {
            testTeamA:      stsfParentId,
            testTeamAChild: stsfChildId,
            testTeamAMid:   stsfMidId,
            testTeamADeep:  stsfDeepId
          }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'sync_all': {
        syncAll();
        SpreadsheetApp.flush();
        _TF_RESULT = { tag: 'fixture.sync_all', data: { ok: true } };
        docAlreadyClosed = true;
        break;
      }

      case 'trash_doc': {
        var trashDocId = data.docId || testDocId;
        DriveApp.getFileById(trashDocId).setTrashed(true);
        _TF_RESULT = { tag: 'fixture.trash_doc', data: { trashed: trashDocId } };
        docAlreadyClosed = true;
        break;
      }

      case 'archive_journey': {
        ArchiveManager.archive(ss);
        _TF_RESULT = { tag: 'fixture.archive_journey', data: { archiveTriggered: true } };
        docAlreadyClosed = true;
        break;
      }

      case 'backdate_action_row': {
        var backdateGlobalId = data.globalId || '';
        var daysAgo = data.daysAgo != null ? Number(data.daysAgo) : 35;
        if (!backdateGlobalId) throw new Error('backdate_action_row: globalId required');
        var actionsSheet = ss.getSheetByName('Actions');
        if (!actionsSheet) throw new Error('backdate_action_row: Actions sheet not found');
        var existingMap = _loadExistingRowsByGlobalId(actionsSheet);
        var backdateEntry = existingMap[backdateGlobalId];
        if (!backdateEntry) throw new Error('backdate_action_row: row not found for globalId=' + backdateGlobalId);
        var backdateDate = new Date();
        backdateDate.setDate(backdateDate.getDate() - daysAgo);
        actionsSheet.getRange(backdateEntry.rowIndex, _ACOL.modified_date).setValue(backdateDate);
        _TF_RESULT = { tag: 'fixture.backdate_action_row', data: { globalId: backdateGlobalId, daysAgo: daysAgo } };
        docAlreadyClosed = true;
        break;
      }

      case 'seed_row': {
        _tfAppendSheetRow(ss, _tfSheetRow({
          id:            data.actionId        || 1,
          assigneeEmail: data.assigneeEmail   || '',
          assigneeName:  data.assigneeName    || '',
          action:        data.actionText      || 'Seeded action',
          status:        data.status          || 'Open',
          docFormula:    data.documentFormula || '',
          dateCreated:   new Date(),
          dateModified:  data.dateModified ? new Date(data.dateModified) : new Date()
        }));
        _TF_RESULT = { tag: 'fixture.seed_row', data: { appended: true } };
        break;
      }

      case 'set_status_from_preview': {
        var sspE = { parameters: { url: data.url || '', newStatus: data.newStatus || 'Open' } };
        _setStatusFromPreview(sspE, doc);
        _TF_RESULT = { tag: 'fixture.set_status_from_preview', data: { ok: true } };
        docAlreadyClosed = true;
        break;
      }

      case 'process_pending_sheet_updates': {
        var ppsuE = { triggerUid: null };
        _processPendingSheetUpdates(ppsuE);
        _TF_RESULT = { tag: 'fixture.process_pending_sheet_updates', data: { ok: true } };
        docAlreadyClosed = true;
        break;
      }

      case 'team_data_slice': {
        // Slice-BUILD for EPIC-A (GTaskSheet-5r4l.2, ADR-0013).
        // Creates sample TeamData + DocData tabs and performs the two durable-invariant
        // smoke checks in-process, returning results for Python assertion:
        //   (a) round-trip: rows written then read back are identical (non-date cols)
        //   (b) resolved authority: Resolved Count computed exclusively via isResolved()

        // --- TeamData tab --------------------------------------------------
        var tdsTeamSheet = _getOrCreateSheet(ss, 'TeamData');
        tdsTeamSheet.clearContents();
        var tdsTeamHeaders = [['Team Id', 'Folder Id', 'Contact']];
        var tdsTeamRows = [
          ['Board',      'board-folder-001', 'board@northlakeuu.org'],
          ['Board',      'board-folder-002', 'board@northlakeuu.org'],
          ['Membership', 'mem-folder-001',   'membership@northlakeuu.org']
        ];
        tdsTeamSheet.getRange(1, 1, 1, 3).setValues(tdsTeamHeaders).setFontWeight('bold');
        tdsTeamSheet.getRange(2, 1, tdsTeamRows.length, 3).setValues(tdsTeamRows);

        // --- DocData rows (action-status sets drive Resolved Count via isResolved()) ---
        // Row 1: matched-team doc — 2 actions (Done + Open) → 1 resolved
        // Row 2: no-team doc     — 1 action  (Open)         → 0 resolved
        // Row 3: UpdateDoc row   — 1 action  (Closed)       → 1 resolved
        var tdsActionSets = [
          ['Done', 'Open'],
          ['Open'],
          ['Closed']
        ];
        function _tdsCountResolved(statuses) {
          var n = 0;
          for (var i = 0; i < statuses.length; i++) { if (isResolved(statuses[i])) n++; }
          return n;
        }
        var tdsNow = new Date();
        var tdsDocDataRows = [
          ['doc-id-slice-001', 'Board Meeting Notes', tdsNow, tdsNow, '',          'board-folder-001', 2, _tdsCountResolved(tdsActionSets[0])],
          ['doc-id-slice-002', 'Membership Report',   tdsNow, tdsNow, '',          '',                 1, _tdsCountResolved(tdsActionSets[1])],
          ['doc-id-slice-003', 'Finance Review',      tdsNow, tdsNow, 'UpdateDoc', 'board-folder-001', 1, _tdsCountResolved(tdsActionSets[2])]
        ];
        var tdsDocHeaders = [['FileId', 'Doc Name', 'Doc Modified', 'Doc Updated', 'SyncStatus', 'Team Id', 'Action Count', 'Resolved Count']];

        var tdsDocSheet = _getOrCreateSheet(ss, 'DocData');
        tdsDocSheet.clearContents();
        tdsDocSheet.getRange(1, 1, 1, 8).setValues(tdsDocHeaders).setFontWeight('bold');
        tdsDocSheet.getRange(2, 1, tdsDocDataRows.length, 8).setValues(tdsDocDataRows);

        // --- Round-trip smoke (a): read back non-date columns ---------------
        var tdsReadBack = tdsDocSheet.getRange(2, 1, tdsDocDataRows.length, 8).getValues();
        var tdsRTDiff = [];
        // Date cols (index 2 and 3) are skipped — GAS serialises dates; values survive.
        var tdsSkipCols = { 2: true, 3: true };
        for (var tdsR = 0; tdsR < tdsDocDataRows.length; tdsR++) {
          for (var tdsC = 0; tdsC < tdsDocDataRows[tdsR].length; tdsC++) {
            if (tdsSkipCols[tdsC]) continue;
            var tdsW = String(tdsDocDataRows[tdsR][tdsC]);
            var tdsV = String(tdsReadBack[tdsR][tdsC]);
            if (tdsW !== tdsV) {
              tdsRTDiff.push({ row: tdsR + 1, col: tdsC + 1, written: tdsW, readBack: tdsV });
            }
          }
        }

        _TF_RESULT = {
          tag: 'fixture.team_data_slice',
          data: {
            teamDataRows: tdsTeamRows.length,
            docDataRows:  tdsDocDataRows.length,
            resolvedCounts: [
              _tdsCountResolved(tdsActionSets[0]),
              _tdsCountResolved(tdsActionSets[1]),
              _tdsCountResolved(tdsActionSets[2])
            ],
            roundTripDiff: tdsRTDiff
          }
        };
        docAlreadyClosed = true;
        break;
      }

      default:
        // Unknown scenario — fall through to default (uc1_new_floating) behaviour.
        GasLogger.log('fixture.warn', {
          msg: 'Unknown scenario, falling back to default behaviour',
          scenario: resolvedScenario
        });
        _tfInsertFloatingAction(
          body,
          'AI- @test@example.com | Fix the bug | Open | 2026-01-01 | 2026-01-01'
        );
        break;
    }

    if (!docAlreadyClosed) {
      doc.saveAndClose();
    }

    GasLogger.log('fixture.setup', { scenario: resolvedScenario });
    // Return structured result for HTTP callers (_handleRunFixture in TestWebApp.js).
    // Playwright callers ignore the return value and use GasLogger.flush() instead.
    return _TF_RESULT || { tag: 'fixture.' + resolvedScenario, data: {} };
  } catch (outerErr) {
    // Catch errors that escape the per-scenario try blocks so the test always
    // receives a log entry instead of timing out on an empty flush.
    GasLogger.log('fixture.error', { msg: outerErr.message, scenario: resolvedScenario });
    GasLogger.log('fixture.' + resolvedScenario, { error: outerErr.message });
    return { tag: 'fixture.' + resolvedScenario, error: outerErr.message };
  } finally {
    GasLogger.flush(); // still fires after return — needed for Playwright log-polling compat
  }
}

/**
 * Combined fixture setup and sync in one invocation.
 * Reads the scenario from TestControl!A1 and the doc ID from script properties.
 *
 * @param {string} [scenario] - Name of the fixture scenario to set up.
 */
function setupAndSync(scenario) {
  try {
    setupTestFixtures(scenario);
    var props = PropertiesService.getScriptProperties();
    var testDocId = props.getProperty('TEST_DOC_ID');
    if (!testDocId) {
      GasLogger.log('sync.error', {
        msg: 'TEST_DOC_ID script property not set'
      });
      return;
    }
    syncDocument(testDocId);
    GasLogger.log('sync.complete', { scenario: scenario });
  } finally {
    GasLogger.flush();
  }
}

// syncDocument() is defined in SyncManager.js.

// ---------------------------------------------------------------------------
// Post-sync consistency verification (test helper)
// ---------------------------------------------------------------------------

/**
 * Full-field consistency check between floating actions, ActionSheet rows, and
 * (when present) tracker-table rows.  Reads the test doc and test sheet directly
 * so all nine ActionSheet columns (including dates and Document formula) are
 * available without going through the WebApp.
 *
 * Checked invariants (floating action ↔ ActionSheet row, keyed by globalId):
 *   assigneeEmail, assigneeName — exact match
 *   action                      — exact text match
 *   status                      — exact match (default 'Open' on both sides)
 *   dateCreated, dateModified   — present and non-empty on ActionSheet row
 *   Document column display text — must equal the current document title
 *
 * When a tracker table is present, each tracker row is also verified against
 * the ActionSheet row for action and status.
 *
 * Logs verify.consistency.complete with the result object so Playwright tests
 * can poll gasLogDir and assert result.ok === true.
 *
 * @param {string} [docId]  Defaults to TEST_DOC_ID script property.
 * @param {?{teamId: string}} [expected]  Optional Team Scope expectation
 *   (GTaskSheet-me6w.6). When expected.teamId is set, additionally asserts:
 *     - the document's Drive appProperty 'teamScope' === expected.teamId
 *     - DocData[fileId].team_id === expected.teamId
 *     - DocData[fileId] exists with doc_name, doc_modified, action_count,
 *       resolved_count populated and consistent with the current scan
 */
function verifyConsistencyForTest(docId, expected) {
  var props = PropertiesService.getScriptProperties();
  var resolvedDocId = docId || props.getProperty('TEST_DOC_ID');
  var testSheetId   = props.getProperty('TEST_SHEET_ID');

  if (!resolvedDocId || !testSheetId) {
    GasLogger.log('verify.consistency.complete', {
      ok: false,
      issues: ['TEST_DOC_ID or TEST_SHEET_ID script properties not set'],
      counts: { floating: 0, sheet: 0, tracker: 0, matched: 0 },
      docTitle: ''
    });
    GasLogger.flush();
    return {
      ok: false,
      issues: ['TEST_DOC_ID or TEST_SHEET_ID script properties not set'],
      counts: { floating: 0, sheet: 0, tracker: 0, matched: 0 },
      docTitle: ''
    };
  }

  var result = {
    ok: true,
    issues: [],
    counts: { floating: 0, sheet: 0, tracker: 0, matched: 0 },
    docTitle: ''
  };

  try {
    var doc = DocumentApp.openById(resolvedDocId);
    result.docTitle = doc.getName();

    // Collect floating actions with globalIds (reuses VerifySync.js helpers).
    var floatingActions = _collectFloatingActionState(doc);
    result.counts.floating = floatingActions.length;

    var tracker = _readTrackerTableState(doc);
    result.counts.tracker = tracker.rows.length;
    result.tracker = tracker;

    // Read ActionSheet rows directly (all 9 columns) to get dates and Document formula.
    var ss = SpreadsheetApp.openById(testSheetId);
    var actionsSheet = ss.getSheetByName('Actions');
    var sheetRows = [];
    if (actionsSheet && actionsSheet.getLastRow() > 1) {
      var numRows = actionsSheet.getLastRow() - 1;
      var data     = actionsSheet.getRange(2, 1, numRows, SHEET_HEADERS.length).getValues();
      var _VF = CONTRACT_SCHEMA.sheetAction.columnsByField;
      var formulas = actionsSheet.getRange(2, _VF.document_formula, numRows, 1).getFormulas();
      for (var i = 0; i < data.length; i++) {
        var formula = formulas[i][0] || '';
        // Extract display name from =HYPERLINK("url","title")
        var titleMatch = formula.match(/HYPERLINK\s*\(\s*"[^"]*"\s*,\s*"([^"]*)"\s*\)/i);
        sheetRows.push({
          globalId:      data[i][_VF.global_id       - 1] ? String(data[i][_VF.global_id - 1]) : '',
          id:            data[i][_VF.action_id       - 1] || '',
          assigneeEmail: data[i][_VF.assignee_email  - 1] || '',
          assigneeName:  data[i][_VF.assignee_name   - 1] || '',
          action:        data[i][_VF.action_text     - 1] || '',
          status:        data[i][_VF.status          - 1] || 'Open',
          docTitle:      titleMatch ? titleMatch[1] : '',
          dateCreated:   data[i][_VF.created_date    - 1],
          dateModified:  data[i][_VF.modified_date   - 1]
        });
      }
    }
    // Scope to the tested doc only — the ActionSheet accumulates rows from all
    // test runs, and globalId encodes the docId as the leading segment.
    sheetRows = sheetRows.filter(function(r) {
      return r.globalId.indexOf(resolvedDocId + '/') === 0;
    });
    result.counts.sheet = sheetRows.length;

    // Build set of IDs that were archived for this doc so orphan tracker rows
    // for archived actions are not reported as consistency failures.
    var archivedIds = {};
    var archiveSheet = ss.getSheetByName('Archive');
    if (archiveSheet && archiveSheet.getLastRow() > 1) {
      var archNumRows = archiveSheet.getLastRow() - 1;
      var archData    = archiveSheet.getRange(2, 1, archNumRows, 1).getValues();
      for (var ai = 0; ai < archData.length; ai++) {
        var archGid = archData[ai][0] || '';
        if (archGid.indexOf(resolvedDocId + '/') === 0) {
          archivedIds[archGid.substring(archGid.indexOf('/') + 1)] = true;
        }
      }
    }

    _runConsistencyChecks(result, floatingActions, tracker, sheetRows, result.docTitle, archivedIds);

    // DocData consistency (GTaskSheet-zc21) — runs whenever a DocData row exists
    // for this doc, independent of `expected`. Verifies DocData.team_id matches
    // the document's actual teamScope appProperty, and that DocData.action_count
    // / resolved_count match BOTH the document's floating actions AND the
    // ActionSheet rows.
    var vcfDocDataRow = _readDocDataRow(ss, resolvedDocId);
    var vcfToken      = ScriptApp.getOAuthToken();
    var vcfTeamScope  = _getDocAppProperty(resolvedDocId, 'teamScope', vcfToken) || '';
    if (vcfDocDataRow) {
      if (vcfDocDataRow.teamId !== vcfTeamScope) {
        result.issues.push(
          'DocData.team_id mismatch vs teamScope appProperty: docData=' + vcfDocDataRow.teamId + ' appProperty=' + vcfTeamScope
        );
      }
      if (vcfDocDataRow.actionCount !== floatingActions.length) {
        result.issues.push(
          'DocData.action_count mismatch vs document: docData=' + vcfDocDataRow.actionCount + ' document=' + floatingActions.length
        );
      }
      if (vcfDocDataRow.actionCount !== sheetRows.length) {
        result.issues.push(
          'DocData.action_count mismatch vs sheet: docData=' + vcfDocDataRow.actionCount + ' sheet=' + sheetRows.length
        );
      }
      var vcfFloatingResolvedCount = 0;
      for (var vcfFI = 0; vcfFI < floatingActions.length; vcfFI++) {
        if (isResolved(floatingActions[vcfFI].status)) vcfFloatingResolvedCount++;
      }
      var vcfSheetResolvedCount = 0;
      for (var vcfSI = 0; vcfSI < sheetRows.length; vcfSI++) {
        if (isResolved(sheetRows[vcfSI].status)) vcfSheetResolvedCount++;
      }
      if (vcfDocDataRow.resolvedCount !== vcfFloatingResolvedCount) {
        result.issues.push(
          'DocData.resolved_count mismatch vs document: docData=' + vcfDocDataRow.resolvedCount + ' document=' + vcfFloatingResolvedCount
        );
      }
      if (vcfDocDataRow.resolvedCount !== vcfSheetResolvedCount) {
        result.issues.push(
          'DocData.resolved_count mismatch vs sheet: docData=' + vcfDocDataRow.resolvedCount + ' sheet=' + vcfSheetResolvedCount
        );
      }
    }

    // Team Scope consistency (GTaskSheet-me6w.6) — only when requested.
    if (expected && expected.teamId !== undefined && expected.teamId !== null) {
      if (vcfTeamScope !== expected.teamId) {
        result.issues.push(
          'teamScope appProperty mismatch: expected=' + expected.teamId + ' actual=' + vcfTeamScope
        );
      }
      if (!vcfDocDataRow) {
        result.issues.push('DocData row missing for fileId=' + resolvedDocId);
      } else {
        if (vcfDocDataRow.teamId !== expected.teamId) {
          result.issues.push(
            'DocData.team_id mismatch: expected=' + expected.teamId + ' actual=' + vcfDocDataRow.teamId
          );
        }
        if (!vcfDocDataRow.docName) {
          result.issues.push('DocData.doc_name is empty for fileId=' + resolvedDocId);
        }
        if (!vcfDocDataRow.docModified) {
          result.issues.push('DocData.doc_modified is empty for fileId=' + resolvedDocId);
        }
      }
    }

    result.ok = result.issues.length === 0;

    GasLogger.log('verify.consistency.complete', result);
  } catch (e) {
    result.ok = false;
    result.issues.push('Error during consistency check: ' + e.message);
    GasLogger.log('verify.consistency.complete', result);
  }

  GasLogger.flush();
  return result;
}

/**
 * Compares floating actions, tracker rows, and sheet rows for full-field agreement.
 * Appends mismatch descriptions to result.issues.
 *
 * @param {object}   result
 * @param {Array}    floatingActions  From _collectFloatingActionState.
 * @param {object}   tracker         {found, rows} from _readTrackerTableState.
 * @param {Array}    sheetRows       Direct ActionSheet read (all 9 fields + docTitle).
 * @param {string}   docTitle        Current document title from doc.getName().
 */
function _isEmailDerivedName(email, name) {
  if (!email || !name) return false;
  var derived = email.split('@')[0]
    .replace(/[._\-]+/g, ' ')
    .replace(/\b\w/g, function(c) { return c.toUpperCase(); });
  return derived === name;
}

function _runConsistencyChecks(result, floatingActions, tracker, sheetRows, docTitle, archivedIds) {
  archivedIds = archivedIds || {};
  var floatingByNrId = {};
  var sheetByNrId    = {};
  var sheetById      = {};
  var trackerById    = {};
  var i;

  for (i = 0; i < floatingActions.length; i++) {
    var f = floatingActions[i];
    if (!f.globalId) {
      result.issues.push('Floating action without globalId: ' + (f.action || '(blank)'));
      continue;
    }
    floatingByNrId[f.globalId] = f;
  }

  for (i = 0; i < sheetRows.length; i++) {
    var s = sheetRows[i];
    if (!s.globalId) continue;
    if (sheetByNrId[s.globalId]) {
      result.issues.push('Duplicate globalId in ActionSheet: ' + s.globalId);
      continue;
    }
    sheetByNrId[s.globalId] = s;
    if (s.id) sheetById[String(s.id)] = s;
  }

  if (tracker.found) {
    for (i = 0; i < tracker.rows.length; i++) {
      var t = tracker.rows[i];
      if (!t.id) {
        result.issues.push('Tracker row missing ID for action: ' + (t.action || '(blank)'));
        continue;
      }
      trackerById[String(t.id)] = t;
    }
  }

  // Check each floating action against its ActionSheet pair.
  for (var nrId in floatingByNrId) {
    if (!Object.prototype.hasOwnProperty.call(floatingByNrId, nrId)) continue;
    var floating = floatingByNrId[nrId];
    var sheet    = sheetByNrId[nrId];
    if (!sheet) {
      result.issues.push('Floating action has no ActionSheet row: ' + (floating.action || '(blank)'));
      continue;
    }

    if (floating.assigneeEmail !== sheet.assigneeEmail) {
      result.issues.push('assigneeEmail mismatch (ID ' + sheet.id + '): doc="' +
        floating.assigneeEmail + '" sheet="' + sheet.assigneeEmail + '"');
    }
    if (floating.assigneeName !== sheet.assigneeName) {
      // When sync converts a plain-text email to a PERSON chip, getName() returns ""
      // for emails not in the directory.  The sheet keeps the derived username name,
      // which is correct — skip the mismatch for this case.
      var docNameEmpty   = floating.assigneeName === '';
      var sheetDerived   = _isEmailDerivedName(floating.assigneeEmail, sheet.assigneeName);
      if (!(docNameEmpty && sheetDerived)) {
        result.issues.push('assigneeName mismatch (ID ' + sheet.id + '): doc="' +
          floating.assigneeName + '" sheet="' + sheet.assigneeName + '"');
      }
    }
    if (floating.action !== sheet.action) {
      result.issues.push('action mismatch (ID ' + sheet.id + '): doc="' +
        floating.action + '" sheet="' + sheet.action + '"');
    }
    var fStatus = floating.status || 'Open';
    var sStatus = sheet.status   || 'Open';
    if (fStatus !== sStatus) {
      result.issues.push('status mismatch (ID ' + sheet.id + '): doc="' +
        fStatus + '" sheet="' + sStatus + '"');
    }
    if (!sheet.dateCreated) {
      result.issues.push('dateCreated empty for ID ' + sheet.id);
    }
    if (!sheet.dateModified) {
      result.issues.push('dateModified empty for ID ' + sheet.id);
    }
    if (docTitle && sheet.docTitle && sheet.docTitle !== docTitle) {
      result.issues.push('Document title mismatch (ID ' + sheet.id + '): expected="' +
        docTitle + '" sheet="' + sheet.docTitle + '"');
    }

    if (tracker.found) {
      var trackerRow = trackerById[String(sheet.id || '')];
      if (!trackerRow) {
        result.issues.push('Tracker table missing row for ID ' + sheet.id);
      } else {
        if (trackerRow.action !== sheet.action) {
          result.issues.push('Tracker action mismatch (ID ' + sheet.id + '): tracker="' +
            trackerRow.action + '" sheet="' + sheet.action + '"');
        }
        var tStatus = trackerRow.status || 'Open';
        if (tStatus !== sStatus) {
          result.issues.push('Tracker status mismatch (ID ' + sheet.id + '): tracker="' +
            tStatus + '" sheet="' + sStatus + '"');
        }
      }
    }

    result.counts.matched++;
  }

  // ActionSheet rows with no corresponding floating action.
  for (var snrId in sheetByNrId) {
    if (!Object.prototype.hasOwnProperty.call(sheetByNrId, snrId)) continue;
    if (!floatingByNrId[snrId]) {
      var extra = sheetByNrId[snrId];
      result.issues.push('ActionSheet row ID ' + extra.id + ' has no floating action in doc');
    }
  }

  // Tracker rows with no ActionSheet row.
  // Only flag when the floating action still exists — if neither sheet nor doc has it,
  // the action was fully deleted and the stale tracker row is expected.
  if (tracker.found) {
    var floatingByAIN = {};
    for (var fgid in floatingByNrId) {
      if (!Object.prototype.hasOwnProperty.call(floatingByNrId, fgid)) continue;
      var ainMatch = fgid.match(/\/?(AI-\d+)$/);
      if (ainMatch) floatingByAIN[ainMatch[1]] = true;
    }
    for (var tid in trackerById) {
      if (!Object.prototype.hasOwnProperty.call(trackerById, tid)) continue;
      if (!sheetById[tid] && !archivedIds[tid] && floatingByAIN[tid]) {
        result.issues.push('Tracker row ID ' + tid + ' has no ActionSheet row');
      }
    }
  }
}

/**
 * Diagnostic: logs the body element types of the test doc to GasLogger.
 * Run via "Test: Debug Doc Body" menu item to verify fixture state.
 */
function debugDocBody() {
  var props   = PropertiesService.getScriptProperties();
  var testDocId = props.getProperty('TEST_DOC_ID');
  GasLogger.log('debug.props', {
    webAppUrl:    getWebAppUrl(),
    hasSecret:    !!props.getProperty('WEBAPP_SECRET'),
    testSheetId:  props.getProperty('TEST_SHEET_ID'),
    testDocId:    testDocId
  });
  var doc  = DocumentApp.openById(testDocId);
  var body = doc.getBody();
  var n    = body.getNumChildren();
  var items = [];
  for (var i = 0; i < n; i++) {
    var child = body.getChild(i);
    var type  = child.getType().toString();
    var item  = { index: i, type: type };
    var isPara = child.getType() === DocumentApp.ElementType.PARAGRAPH;
    var isList = child.getType() === DocumentApp.ElementType.LIST_ITEM;
    if (isPara || isList) {
      var para = isPara ? child.asParagraph() : child.asListItem();
      item.numChildren = para.getNumChildren();
      if (para.getNumChildren() > 0) {
        item.firstChildType = para.getChild(0).getType().toString();
        if (para.getChild(0).getType() === DocumentApp.ElementType.PERSON) {
          item.personEmail = para.getChild(0).asPerson().getEmail();
        }
      }
      item.text = para.getText().substring(0, 40);
    }
    items.push(item);
  }
  GasLogger.log('debug.docBody', { docId: testDocId, numChildren: n, items: items });
  GasLogger.flush();
}

/**
 * One-time bootstrap: sets all script properties needed for testing.
 * Run once from the Apps Script editor function picker after each fresh deploy.
 *
 * Properties set:
 *   TEST_SHEET_ID        — the bound spreadsheet used for testing
 *   TEST_DOC_ID          — the Google Doc used for testing
 *   GAS_LOGGER_FOLDER_ID — the Drive folder GasLogger writes .log files to
 *   TEST_ASSIGNEE_EMAIL  — email used for the chip-led list item in UC-A fixtures
 *   TEST_ASSIGNEE_NAME   — display name for the chip (optional; email used as fallback)
 */
function bootstrap() {
  var props = PropertiesService.getScriptProperties();
  props.setProperties({
    'TEST_SHEET_ID':        '10UCsEHPL2RjA1IduUSFDSaA2lpkoCuZY79sIjratH_s',
    'TEST_DOC_ID':          '11jA0FMowlJbyxyJoK6bePVvcO63niVrKcXA0eMJW1F4',
    'GAS_LOGGER_FOLDER_ID': '1lg2CWtOmDGglMVasSjEk3jTaW9SXcO6s',
    'TEST_ASSIGNEE_EMAIL':  'stuart.donaldson@gmail.com',
    'TEST_ASSIGNEE_NAME':   'Stuart Donaldson'
  });
  GasLogger.log('bootstrap.complete', {
    testSheetId:     '10UCsEHPL2RjA1IduUSFDSaA2lpkoCuZY79sIjratH_s',
    testDocId:       '11jA0FMowlJbyxyJoK6bePVvcO63niVrKcXA0eMJW1F4',
    logFolderId:     '1lg2CWtOmDGglMVasSjEk3jTaW9SXcO6s',
    assigneeEmail:   'stuart.donaldson@gmail.com'
  });
  GasLogger.flush();
}

// ---------------------------------------------------------------------------
// Session lifecycle — named-clone fixture isolation (ATDD lifecycle §Principle 7)
// ---------------------------------------------------------------------------

/**
 * Creates a named clone of the master template doc in the same Drive folder as
 * the test sheet, sets TEST_DOC_ID to the clone, and stores the master ID in
 * TEST_DOC_TEMPLATE_ID so endTestSession can restore it.
 *
 * Called by menuBeginTestSession; masterDocId is read from TestControl!A1.
 *
 * @param {string} masterDocId  ID of the master template doc (read-only).
 */
function beginTestSession(masterDocId) {
  try {
    var props       = PropertiesService.getScriptProperties();
    var testSheetId = props.getProperty('TEST_SHEET_ID');

    var sheetFile = DriveApp.getFileById(testSheetId);
    var folderIter = sheetFile.getParents();
    var folder = folderIter.hasNext() ? folderIter.next() : null;

    if (!folder || (folder.isTrashed && folder.isTrashed())) {
      folder = DriveApp.getRootFolder();
    }

    var now      = new Date();
    var dateStr  = Utilities.formatDate(now, Session.getScriptTimeZone(), 'yyyyMMdd');
    var hexSuffix = ('000' + Math.floor(Math.random() * 0xFFFF).toString(16)).slice(-4);
    var cloneName = 'GActionSheet-Test-session-' + dateStr + '-' + hexSuffix;

    var cloneFile = DriveApp.getFileById(masterDocId).makeCopy(cloneName, folder);
    if (cloneFile.setTrashed) {
      cloneFile.setTrashed(false);
    }
    var cloneId   = cloneFile.getId();

    props.setProperty('TEST_DOC_TEMPLATE_ID', masterDocId);
    props.setProperty('TEST_DOC_ID', cloneId);

    var ss   = SpreadsheetApp.openById(testSheetId);
    var ctrl = ss.getSheetByName('TestControl');
    if (ctrl) {
      ctrl.getRange('B1').setValue(cloneId);
    }

    GasLogger.log('session.begin', {
      cloneId: cloneId,
      cloneName: cloneName,
      masterDocId: masterDocId,
      folderId: folder.getId(),
      folderName: folder.getName()
    });
  } catch (err) {
    GasLogger.log('session.begin.error', { msg: err.message, masterDocId: masterDocId });
  }
  GasLogger.flush();
}

/**
 * Trashes the clone created by beginTestSession and restores TEST_DOC_ID to
 * the master template ID stored in TEST_DOC_TEMPLATE_ID.
 *
 * @param {string} [cloneIdOverride]  Explicit clone ID to end. Falls back to TEST_DOC_ID.
 */
function endTestSession(cloneIdOverride) {
  try {
    var props      = PropertiesService.getScriptProperties();
    var cloneId    = cloneIdOverride || props.getProperty('TEST_DOC_ID');
    var masterId   = props.getProperty('TEST_DOC_TEMPLATE_ID');

    if (cloneId && cloneId !== masterId) {
      DriveApp.getFileById(cloneId).setTrashed(true);
    }
    if (masterId) {
      props.setProperty('TEST_DOC_ID', masterId);
    }
    props.deleteProperty('TEST_DOC_TEMPLATE_ID');

    GasLogger.log('session.end', { cloneId: cloneId, masterDocId: masterId });
  } catch (err) {
    GasLogger.log('session.end.error', { msg: err.message });
  }
  GasLogger.flush();
}
