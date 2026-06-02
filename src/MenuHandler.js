/**
 * MenuHandler.js
 *
 * Registers the "Action Sync" custom menu and provides the menu item handlers.
 * onOpen() is a simple trigger — must NOT call DriveApp or any authorized service.
 */

function onOpen() {
  // [PROBE] — simple trigger: authorized services unavailable; Logger only.
  if (PROBE_ENABLED) {
    Logger.log(JSON.stringify({
      tag:     'PROBE.onOpen',
      version: BUILD_INFO.version,
      ts:      new Date().toISOString()
    }));
  }

  // onOpen is a Sheets simple trigger. When this script also runs as a Docs/
  // Slides/Forms add-on, SpreadsheetApp.getUi() is not available in that
  // context. getActiveSpreadsheet() returns null rather than throwing, so
  // checking it is insufficient — wrap the entire body in try/catch instead.
  try {
    SpreadsheetApp.getUi()
      .createMenu('Action Sync')
      .addItem('Sync', 'menuSync')
      .addSeparator()
      .addSubMenu(
        SpreadsheetApp.getUi().createMenu('Setup')
          .addItem('Ensure Sheet Structure', 'menuEnsureSheetStructure')
          .addItem('Initialize Triggers', 'menuInitializeTriggers')
          .addItem('Bootstrap Test Properties', 'menuBootstrap')
      )
      .addSeparator()
      .addItem('Test: Begin Session', 'menuBeginTestSession')
      .addItem('Test: End Session', 'menuEndTestSession')
      .addItem('Test: Setup Fixture', 'menuSetupFixture')
      .addItem('Test: Sync Document', 'menuSyncDocument')
      .addItem('Test: Setup And Sync', 'menuSetupAndSync')
      .addItem('Test: Verify Consistency', 'menuVerifyConsistency')
      .addItem('Test: Insert Tracker Table', 'menuInsertTrackerTable')
      .addItem('Test: Run Archive', 'menuRunArchive')
      .addItem('Test: Debug Doc Body', 'menuDebugDocBody')
      .addItem('Test: Probe Identity', 'menuProbeIdentity') // [PROBE]
      .addToUi();
  } catch (e) {
    // Not a Sheets context (e.g. running as a Docs add-on) — exit silently.
  }
}

function menuEnsureSheetStructure() {
  ensureSheetStructure();
}

function menuInitializeTriggers() {
  initializeTriggers();
}

function menuBootstrap() {
  bootstrap();
}

function menuSync() {
  PROBE_log('menu', { menuItem: 'menuSync' }); // [PROBE]
  syncAll();
}

// [PROBE] — dedicated identity probe callable from the sheet menu and Playwright.
// Captures full identity in an authorized context, filling the onOpen gap.
// Surface tag 'menu.identity' distinguishes it from the operational menuSync probe.
function menuProbeIdentity() {
  PROBE_log('menu.identity', { menuItem: 'menuProbeIdentity' });
}

function menuBeginTestSession() {
  var masterDocId = _readTestControlArg();
  beginTestSession(masterDocId);
}

function menuEndTestSession() {
  endTestSession();
}

function menuSetupFixture() {
  var scenario = _readTestControlArg();
  setupTestFixtures(scenario);
}

function menuSyncDocument() {
  var docId = _readTestControlArg();
  syncDocument(docId);
}

function menuSetupAndSync() {
  var scenario = _readTestControlArg();
  setupAndSync(scenario);
}

function menuVerifyConsistency() {
  var docId = _readTestControlArg();
  verifyConsistencyForTest(docId);
}

function menuInsertTrackerTable() {
  var docId = _readTestControlArg();
  insertTrackerTable(docId);
}

function menuRunArchive() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var count = ArchiveManager.archive(ss);
  GasLogger.log('archive.complete', { count: count });
  GasLogger.flush();
}

function menuDebugDocBody() {
  debugDocBody();
}

function _readTestControlArg() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var ctrl = ss.getSheetByName('TestControl');
  if (!ctrl) return null;
  var val = ctrl.getRange('A1').getValue();
  return val ? String(val) : null;
}
