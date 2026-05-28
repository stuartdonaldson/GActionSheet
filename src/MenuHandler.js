/**
 * MenuHandler.js
 *
 * Registers the "Action Sync" custom menu and provides the menu item handlers.
 * onOpen() is a simple trigger — must NOT call DriveApp or any authorized service.
 */

function onOpen() {
  // Guard: onOpen is a Sheets simple trigger. When the script runs as a
  // Docs/Slides/Forms add-on, SpreadsheetApp.getUi() throws — exit silently.
  try { SpreadsheetApp.getActiveSpreadsheet(); } catch (e) { return; }
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
    .addToUi();
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
  syncAll();
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
