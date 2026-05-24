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
 * Replaces the test doc body with just the section heading paragraph
 * ("=== Tracked Actions ===") using HEADING1 style.
 * All previous content is removed.
 *
 * @param {Body} body  DocumentApp Body object.
 * @returns {Paragraph}  The heading paragraph that was appended.
 */
function _tfResetDocBody(body) {
  body.clear();
  var heading = body.appendParagraph('=== Tracked Actions ===');
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

  // GET the document body to determine the current content layout.
  var getResp = UrlFetchApp.fetch(
    baseUrl + docId + '?fields=body.content',
    { headers: authHeader, muteHttpExceptions: true }
  );
  if (getResp.getResponseCode() !== 200) {
    throw new Error('Docs GET failed (' + getResp.getResponseCode() + '): ' +
                    getResp.getContentText());
  }
  var docData = JSON.parse(getResp.getContentText());
  var content = (docData.body && docData.body.content) || [];

  // Find the last paragraph element to determine what needs to be cleared.
  // The Docs API never allows deleting the last paragraph; we clear its content.
  var lastParaStartIndex = null;
  var lastParaEndIndex   = null;
  for (var ci = content.length - 1; ci >= 0; ci--) {
    if (content[ci].paragraph) {
      lastParaStartIndex = content[ci].startIndex;
      lastParaEndIndex   = content[ci].endIndex;
      break;
    }
  }
  if (lastParaStartIndex === null) {
    throw new Error('_tfInsertPersonChipListItem: no paragraph found in doc body');
  }

  var requests = [];

  // Clear the doc body to a single empty paragraph.
  //
  // The Docs API never allows deleting the last paragraph in the body — it is the
  // mandatory section-end marker. We must KEEP it but delete its content.
  //
  // Two cases:
  //  A) Multiple paragraphs — delete everything before the last paragraph, which
  //     shifts the last (empty) paragraph to index 1.  If the last paragraph also
  //     has content, delete that content too.
  //  B) Single paragraph (e.g. the chip from a previous fixture run) — delete its
  //     content (indices 1..endIndex-2 inclusive) leaving only the trailing \n.
  //     We cannot use lastParaStartIndex == 1 as a "nothing to delete" guard here.
  if (lastParaStartIndex > 1) {
    // Case A: remove all paragraphs before the last one.
    requests.push({ deleteContentRange: { range: { startIndex: 1, endIndex: lastParaStartIndex } } });
    // After this deletion, the last paragraph sits at index 1.  It should normally
    // be empty, but delete any residual content just in case.
    var lastParaContentLen = lastParaEndIndex - lastParaStartIndex - 1;
    if (lastParaContentLen > 0) {
      requests.push({ deleteContentRange: { range: { startIndex: 1, endIndex: 1 + lastParaContentLen } } });
    }
  } else if (lastParaEndIndex > 2) {
    // Case B: single paragraph with content — delete content, preserve trailing \n.
    // endIndex is exclusive, so delete [1, endIndex-1) to keep only the \n at endIndex-1.
    requests.push({ deleteContentRange: { range: { startIndex: 1, endIndex: lastParaEndIndex - 1 } } });
  }
  // After clearing: one empty paragraph at index 1-2 (just the \n).

  // batchUpdate requests (applied in order; indices shift after each):
  //  1. createParagraphBullets — marks the paragraph as a bulleted list item.
  //     floating_actions() in the Python test detects this via w:numPr in .docx.
  //  2. insertPerson           — inserts the @mention chip at index 1.
  //     The chip occupies exactly 1 index in the Docs character stream.
  //  3. insertText             — appends " <actionText>" after the chip (now at index 2).
  requests.push({
    createParagraphBullets: {
      range: { startIndex: 1, endIndex: 2 },
      bulletPreset: 'BULLET_DISC_CIRCLE_SQUARE'
    }
  });
  requests.push({
    insertPerson: {
      personProperties: { email: email },
      location: { index: 1 }
    }
  });
  requests.push({
    insertText: {
      location: { index: 2 },
      text: ' ' + actionText
    }
  });

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
 * Builds a sheet row array in SHEET_HEADERS order.
 *
 * SHEET_HEADERS = [NamedRangeId, ID, Assignee Email, Assignee Name, Action,
 *                  Status, Document, Date Created, Date Modified]
 *
 * @param {object} opts
 * @param {string}  opts.namedRangeId  Named range anchor ID (empty until anchor written).
 * @param {string|number} opts.id
 * @param {string}  opts.assigneeEmail
 * @param {string}  opts.assigneeName
 * @param {string}  opts.action
 * @param {string}  opts.status
 * @param {string}  opts.docFormula   Full =HYPERLINK(…) formula string.
 * @param {Date}    opts.dateCreated
 * @param {Date}    opts.dateModified
 * @returns {Array}  9-element array.
 */
function _tfSheetRow(opts) {
  return [
    opts.namedRangeId || '',
    opts.id,
    opts.assigneeEmail || '',
    opts.assigneeName || '',
    opts.action || '',
    opts.status || '',
    opts.docFormula || '',
    opts.dateCreated || '',
    opts.dateModified || ''
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
function setupTestFixtures(scenario) {
  var resolvedScenario = scenario || 'default';
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

    // -- Step 1: clear both sheets -----------------------------------------
    _tfClearSheetTab(ss, 'Actions');
    _tfClearSheetTab(ss, 'Archive');

    // -- Step 2: clear doc body -------------------------------------------
    // UC-A clears via the Docs REST API deleteContentRange inside
    // _tfInsertPersonChipListItem (called later, after saveAndClose).
    // All other scenarios use DocumentApp to reset to the standard heading.
    if (resolvedScenario !== 'uc_a_clear' && resolvedScenario !== 'uc_a_permutations') {
      _tfResetDocBody(body);
    }

    // -- Step 3: seed per scenario; track whether doc was already closed ----
    var docAlreadyClosed = false;
    switch (resolvedScenario) {

      case 'uc_a_clear':
        // Remove all named ranges (unanchors existing actions).
        var namedRanges = doc.getNamedRanges();
        for (var nri = 0; nri < namedRanges.length; nri++) {
          namedRanges[nri].remove();
        }
        // Flush DocumentApp writes before using the Docs REST API —
        // the REST API must see the cleared body before inserting the chip.
        doc.saveAndClose();
        docAlreadyClosed = true;
        // Insert a chip-led list item via the Docs REST API batchUpdate.
        // The chip is the assignee; the action text follows it on the same line.
        var ucaToken  = ScriptApp.getOAuthToken();
        var ucaEmail  = props.getProperty('TEST_ASSIGNEE_EMAIL')
                     || Session.getActiveUser().getEmail();
        var ucaChipOk = false;
        try {
          _tfInsertPersonChipListItem(ucaToken, testDocId, ucaEmail,
                                      'Review the budget report');
          ucaChipOk = true;
        } catch (chipErr) {
          GasLogger.log('fixture.uc_a_clear', {
            namedRangesRemoved: namedRanges.length,
            assigneeEmail: ucaEmail,
            error: 'chip insert: ' + chipErr.message
          });
        }
        if (ucaChipOk) {
          // Also insert an email-led list item to exercise email-at-start detection.
          // Use the REST API (not DocumentApp) to avoid GAS document caching between
          // the chip batchUpdate and the subsequent syncDocument call.
          try {
            _tfAppendTextListItem(
              ucaToken, testDocId,
              'jane.smith@example.com Approve the budget proposal (In Progress)'
            );
            GasLogger.log('fixture.uc_a_clear', {
              namedRangesRemoved: namedRanges.length,
              assigneeEmail:      ucaEmail,
              emailItemInserted:  true
            });
          } catch (emailErr) {
            GasLogger.log('fixture.uc_a_clear', {
              namedRangesRemoved: namedRanges.length,
              assigneeEmail: ucaEmail,
              error: 'email item append: ' + emailErr.message
            });
          }
        }
        break;

      case 'uc_a_permutations':
        // Full permutation coverage for floating-action detection.
        // Items inserted (4 total; 3 produce rows, 1 is a negative case):
        //   1. Chip item WITH explicit "(Done)" status token
        //   2. Email item with NO status token (defaults to Open)
        //   3. Email with underscore username bob_jones@example.com (name → "Bob Jones")
        //   4. Plain-text list item with no chip and no email (no row expected)
        var permNangedRanges = doc.getNamedRanges();
        for (var permNri = 0; permNri < permNangedRanges.length; permNri++) {
          permNangedRanges[permNri].remove();
        }
        doc.saveAndClose();
        docAlreadyClosed = true;
        var permToken = ScriptApp.getOAuthToken();
        var permEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                     || Session.getActiveUser().getEmail();
        var permChipOk = false;
        try {
          _tfInsertPersonChipListItem(permToken, testDocId, permEmail,
                                      'Review the budget report (Done)');
          permChipOk = true;
        } catch (permChipErr) {
          GasLogger.log('fixture.uc_a_permutations', {
            namedRangesRemoved: permNangedRanges.length,
            error: 'chip insert: ' + permChipErr.message
          });
        }
        if (permChipOk) {
          var permErrors = [];
          try {
            _tfAppendTextListItem(permToken, testDocId,
              'jane.smith@example.com Approve the budget proposal');
          } catch (e2) { permErrors.push('email-no-status: ' + e2.message); }
          try {
            _tfAppendTextListItem(permToken, testDocId,
              'bob_jones@example.com Review the Q2 report');
          } catch (e3) { permErrors.push('underscore-email: ' + e3.message); }
          try {
            _tfAppendTextListItem(permToken, testDocId,
              'Complete the project documentation');
          } catch (e4) { permErrors.push('plain-text: ' + e4.message); }
          if (permErrors.length > 0) {
            GasLogger.log('fixture.uc_a_permutations', {
              namedRangesRemoved: permNangedRanges.length,
              error: permErrors.join('; ')
            });
          } else {
            GasLogger.log('fixture.uc_a_permutations', {
              namedRangesRemoved: permNangedRanges.length,
              itemsInserted: 4
            });
          }
        }
        break;

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
          'AI-1 @test@example.com | Fix the bug | Done | 2026-01-01 | 2026-05-10'
        );
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'Fix the bug',
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
          'AI-1 @test@example.com | Fix the bug | Open | 2026-01-01 | 2026-05-09'
        );
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'Fix the bug',
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
          'AI-1 @test@example.com | Completed action | Done | 2026-01-01 | 2026-04-01'
        );
        // Append table with matching data row.
        var tableAc5 = _tfAppendEmptyTable(body);
        _tfAppendTableRow(tableAc5, [
          '1',
          'test@example.com',
          '',
          'Completed action',
          'Done',
          '2026-01-01',
          '2026-04-01'
        ]);
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'Completed action',
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
          action: 'Fix the bug',
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
          'Review the PR',
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
          action: 'Fix the bug',
          status: 'Closed',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: archiveDateUc4
        }));
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 2,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'Review the PR',
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
          'Review the PR',
          'Open',
          '2026-01-01',
          '2026-01-01'
        ]);
        _tfInsertFloatingAction(
          body,
          'AI-2 @test@example.com | Review the PR | Open | 2026-01-01 | 2026-01-01'
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
          'Write tests',
          'Open',
          '2026-01-01',
          '2026-01-01'
        ]);
        _tfInsertFloatingAction(
          body,
          'AI-3 @test@example.com | Write tests (locally edited) | Done | 2026-01-01 | 2026-01-01'
        );
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 3,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'Write tests',
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
        // _tfResetDocBody() already set up the heading; nothing more to do.
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
  } catch (outerErr) {
    // Catch errors that escape the per-scenario try blocks so the test always
    // receives a log entry instead of timing out on an empty flush.
    GasLogger.log('fixture.error', { msg: outerErr.message, scenario: resolvedScenario });
    GasLogger.log('fixture.' + resolvedScenario, { error: outerErr.message });
  } finally {
    GasLogger.flush();
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

/**
 * Diagnostic: logs the body element types of the test doc to GasLogger.
 * Run via "Test: Debug Doc Body" menu item to verify fixture state.
 */
function debugDocBody() {
  var props   = PropertiesService.getScriptProperties();
  var testDocId = props.getProperty('TEST_DOC_ID');
  GasLogger.log('debug.props', {
    webAppUrl:    props.getProperty('WEBAPP_URL'),
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
