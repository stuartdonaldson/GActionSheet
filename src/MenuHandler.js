/**
 * MenuHandler.js
 *
 * Registers the "Action Sync" custom menu and provides the menu item handlers.
 * onOpen() is a simple trigger — must NOT call DriveApp or any authorized service.
 */

function onOpen() {
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
    .addItem('Test: Setup Fixture', 'menuSetupFixture')
    .addItem('Test: Sync Document', 'menuSyncDocument')
    .addItem('Test: Setup And Sync', 'menuSetupAndSync')
    .addItem('Test: Verify Consistency', 'menuVerifyConsistency')
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
