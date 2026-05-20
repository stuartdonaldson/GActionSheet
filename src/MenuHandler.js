/**
 * MenuHandler.js
 *
 * Simple trigger that adds the "Action Sync" menu to the spreadsheet UI.
 * onOpen() is a reserved GAS simple trigger name — no installable trigger
 * is needed for container-bound scripts.
 */

/**
 * Installs the "Action Sync" menu when the spreadsheet is opened.
 * Called automatically by the GAS runtime; no explicit trigger installation
 * required.
 */
// Simple triggers cannot call DriveApp — GasLogger.flush() is not available here.
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Action Sync')
    .addItem('Sync', 'syncAll')
    .addSeparator()
    .addItem('Test: Setup Fixture', '_testSetupFixture')
    .addItem('Test: Sync Document', '_testSyncDocument')
    .addToUi();
}

function _testSetupFixture() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var ctrl = ss.getSheetByName('TestControl');
  var scenario = (ctrl ? ctrl.getRange('A1').getValue() : '') || 'default';
  setupTestFixtures(scenario);
}

function _testSyncDocument() {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var ctrl = ss.getSheetByName('TestControl');
    var docId = ctrl ? ctrl.getRange('A1').getValue() : '';
    if (!docId) {
      GasLogger.log('test.error', { msg: 'TestControl!A1 is empty — no docId provided' });
      return;
    }
    syncDocument(docId);
  } finally {
    GasLogger.flush();
  }
}
