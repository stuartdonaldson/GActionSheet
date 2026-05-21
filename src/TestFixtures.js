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
 * Builds a sheet row array in SHEET_HEADERS order.
 *
 * SHEET_HEADERS = [ID, Assignee Email, Assignee Name, Action, Status,
 *                  Document, Date Created, Date Modified]
 *
 * @param {object} opts
 * @param {string|number} opts.id
 * @param {string}  opts.assigneeEmail
 * @param {string}  opts.assigneeName
 * @param {string}  opts.action
 * @param {string}  opts.status
 * @param {string}  opts.docFormula   Full =HYPERLINK(…) formula string.
 * @param {Date}    opts.dateCreated
 * @param {Date}    opts.dateModified
 * @returns {Array}  8-element array.
 */
function _tfSheetRow(opts) {
  return [
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

    // -- Step 1: clear both sheets and reset the doc body -------------------
    _tfClearSheetTab(ss, 'Actions');
    _tfClearSheetTab(ss, 'Archive');
    _tfResetDocBody(body);

    // -- Step 2: seed per scenario ------------------------------------------
    switch (resolvedScenario) {

      case 'ac1':
      case 'default':
        // New unnumbered floating action.
        _tfInsertFloatingAction(
          body,
          'AI- @test@example.com | Test action one | Todo | 2026-01-01 | 2026-01-01'
        );
        break;

      case 'ac2':
        // Existing ID preserved.
        _tfInsertFloatingAction(
          body,
          'AI-5 @test@example.com | Test action five | Todo | 2026-01-01 | 2026-01-01'
        );
        break;

      case 'ac3':
        // Document wins: doc dateModified (2026-05-10) is 1 day newer than
        // the sheet row's dateModified (2026-05-09).
        _tfInsertFloatingAction(
          body,
          'AI-1 @test@example.com | Action from doc | Todo | 2026-01-01 | 2026-05-10'
        );
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'Action from sheet',
          status: 'Todo',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: new Date('2026-05-09')
        }));
        break;

      case 'ac4':
        // Sheet wins: sheet dateModified (2026-05-10) is 1 day newer than
        // the floating action's dateModified (2026-05-09).
        _tfInsertFloatingAction(
          body,
          'AI-1 @test@example.com | Action from doc | Todo | 2026-01-01 | 2026-05-09'
        );
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'Action from sheet',
          status: 'In Progress',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: new Date('2026-05-10')
        }));
        break;

      case 'ac5':
        // Already synced: consistent state in floating paragraph, table row,
        // and sheet row — all with the same values and dateModified.
        _tfInsertFloatingAction(
          body,
          'AI-1 @test@example.com | Completed action | Done | 2026-01-01 | 2026-04-01'
        );
        // Append table with matching data row.
        var table5 = _tfAppendEmptyTable(body);
        _tfAppendTableRow(table5, [
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
        // User-added data row in table, no ID, no dates — sync should assign them.
        var tableUc2 = _tfAppendEmptyTable(body);
        _tfAppendTableRow(tableUc2, [
          '',
          'test@example.com',
          '',
          'Action added directly to table',
          '',
          '',
          ''
        ]);
        break;

      case 'uc5_bare_reference':
        // Bare reference floating action (just ID, no other fields).
        var tableUc5 = _tfAppendEmptyTable(body);
        _tfAppendTableRow(tableUc5, [
          '7',
          'owner@example.com',
          'Owner Name',
          'Canonical action text',
          'Open',
          '2026-01-01',
          '2026-01-01'
        ]);
        _tfInsertFloatingAction(body, 'AI-7');
        break;

      case 'uc6_revert_local_edit':
        // Floating paragraph diverges from table row (different action and status),
        // same dateModified — table should win.
        var tableUc6 = _tfAppendEmptyTable(body);
        _tfAppendTableRow(tableUc6, [
          '3',
          'test@example.com',
          '',
          'Original',
          'Open',
          '2026-01-01',
          '2026-01-01'
        ]);
        _tfInsertFloatingAction(
          body,
          'AI-3 @test@example.com | Locally edited | Done | 2026-01-01 | 2026-01-01'
        );
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 3,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'Original',
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

      default:
        // Unknown scenario — fall through to ac1 behaviour.
        GasLogger.log('fixture.warn', {
          msg: 'Unknown scenario, falling back to ac1 behaviour',
          scenario: resolvedScenario
        });
        _tfInsertFloatingAction(
          body,
          'AI- @test@example.com | Test action one | Todo | 2026-01-01 | 2026-01-01'
        );
        break;
    }

    doc.saveAndClose();

    GasLogger.log('fixture.setup', { scenario: resolvedScenario });
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

// syncDocument() is defined in SyncOrchestrator.js — the real implementation
// replaced this stub.  Do not redefine it here.

/**
 * One-time bootstrap: sets all script properties needed for testing.
 * Run once from the Apps Script editor function picker, then never again.
 *
 * Properties set:
 *   TEST_SHEET_ID        — the bound spreadsheet used for testing
 *   TEST_DOC_ID          — the Google Doc used for testing
 *   GAS_LOGGER_FOLDER_ID — the Drive folder GasLogger writes .log files to
 */
function bootstrap() {
  var props = PropertiesService.getScriptProperties();
  props.setProperties({
    'TEST_SHEET_ID':        '10UCsEHPL2RjA1IduUSFDSaA2lpkoCuZY79sIjratH_s',
    'TEST_DOC_ID':          '11jA0FMowlJbyxyJoK6bePVvcO63niVrKcXA0eMJW1F4',
    'GAS_LOGGER_FOLDER_ID': '1lg2CWtOmDGglMVasSjEk3jTaW9SXcO6s'
  });
  GasLogger.log('bootstrap.complete', {
    testSheetId:     '10UCsEHPL2RjA1IduUSFDSaA2lpkoCuZY79sIjratH_s',
    testDocId:       '11jA0FMowlJbyxyJoK6bePVvcO63niVrKcXA0eMJW1F4',
    logFolderId:     '1lg2CWtOmDGglMVasSjEk3jTaW9SXcO6s'
  });
  GasLogger.flush();
}
