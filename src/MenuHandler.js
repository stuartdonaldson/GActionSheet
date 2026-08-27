/**
 * MenuHandler.js
 *
 * Registers the "Action Sync" custom menu and provides the menu item handlers.
 * onOpen() is a simple trigger — must NOT call DriveApp or any authorized service.
 */

function onOpen() {
  // Simple trigger: authorized services (DriveApp, UrlFetchApp, GasLogger.flush()
  // which hits both) are unavailable here. Logger.log() is not — unconditional
  // (not PROBE_ENABLED-gated) so there is at least one signal in `clasp logs`
  // confirming onOpen fired at all and which branch it reached, instead of the
  // total blackout this trigger had before (gts-8py3 follow-up: matches the
  // buildHomepageCard instrumentation gap found investigating the sidebar hang —
  // this trigger had the identical gap and was equally undiagnosable).
  Logger.log(JSON.stringify({
    tag:     'onOpen.start',
    version: BUILD_INFO.version,
    ts:      new Date().toISOString()
  }));

  // Sheets context: ActionSheet management menu.
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
          .addItem('Configure Action Format', 'menuConfigFormat')
      )
      .addSubMenu(
        SpreadsheetApp.getUi().createMenu('Test')
          .addItem('Begin Session', 'menuBeginTestSession')
          .addItem('End Session', 'menuEndTestSession')
          .addItem('Setup Fixture', 'menuSetupFixture')
          .addItem('Sync Document', 'menuSyncDocument')
          .addItem('Setup And Sync', 'menuSetupAndSync')
          .addItem('Verify Consistency', 'menuVerifyConsistency')
          .addItem('Insert Tracker Table', 'menuInsertTrackerTable')
          .addItem('Run Archive', 'menuRunArchive')
          .addItem('Debug Doc Body', 'menuDebugDocBody')
          .addItem('Probe Identity', 'menuProbeIdentity') // [PROBE]
      )
      .addToUi();
    Logger.log(JSON.stringify({ tag: 'onOpen.sheetsMenu.added', ts: new Date().toISOString() }));
  } catch (e) {
    // Not a Sheets context — try Docs context below.
    Logger.log(JSON.stringify({ tag: 'onOpen.sheetsMenu.notApplicable', msg: String(e), ts: new Date().toISOString() }));
  }

  // Docs context: per-document actions available from the menu bar.
  try {
    DocumentApp.getUi()
      .createMenu('Action Sync')
      .addItem('Sync', 'menuSyncActiveDoc')
      .addItem('Insert Tracker', 'menuInsertTrackerActiveDoc')
      .addItem('Export…', 'menuShowExportDialog')
      .addToUi();
    Logger.log(JSON.stringify({ tag: 'onOpen.docsMenu.added', ts: new Date().toISOString() }));
  } catch (e) {
    // Not a Docs context — exit silently.
    Logger.log(JSON.stringify({ tag: 'onOpen.docsMenu.notApplicable', msg: String(e), ts: new Date().toISOString() }));
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

function menuConfigFormat() {
  configFormat();
}

function menuSync() {
  PROBE_log('menu', { menuItem: 'menuSync' }); // [PROBE]
  syncAll();
}

/**
 * getActiveDocument() only resolves when actually invoked from that doc's own
 * UI session (real menu click). run_fixture (TestFixtures.js) executes
 * statelessly via the Sheet-bound web app, so it has no active document —
 * fall back to _TEST_ACTIVE_DOC_ID, a narrow script-property bridge that the
 * 'menu_sync_active_doc' / 'menu_insert_tracker_active_doc' fixture cases
 * (TestFixtures.js) set immediately before calling menuSyncActiveDoc() /
 * menuInsertTrackerActiveDoc() and clear immediately after, to make these
 * wrappers reachable from a test (gts-ez2e) without changing production
 * behavior (the real menu click always has an active document). This is
 * unrelated to any general "which doc is under test" concept — GAS holds no
 * script property for that anywhere (ADR-0006 §4), it is always a real
 * parameter. This one narrow property exists only because a real Docs menu
 * callback takes zero arguments and has no other channel to receive one.
 */
function _activeOrTestDocId() {
  var doc = DocumentApp.getActiveDocument();
  if (doc) return doc.getId();
  return PropertiesService.getScriptProperties().getProperty('_TEST_ACTIVE_DOC_ID') || '';
}

function menuSyncActiveDoc() {
  var docId = _activeOrTestDocId();
  if (docId) syncDocument(docId);
}

function menuInsertTrackerActiveDoc() {
  var docId = _activeOrTestDocId();
  if (docId) insertTrackerTable(docId);
}

/**
 * Opens the Export progress dialog (gts-s7ut, Procedure-Exporter.js's
 * showGovernanceExportDialog_ + ExportProgressDialog.html). Only reachable
 * from this classic menu — showModalDialog is unavailable from CardService
 * action handlers, which is why export isn't a sidebar button.
 */
function menuShowExportDialog() {
  showGovernanceExportDialog_();
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
  // No HTTP payload to carry a cloneId on this bare menu callback — resolve
  // it from TestControl!B1, the session pointer beginTestSession() wrote
  // there, and pass it through as a real parameter. No masterDocId here (no
  // script property to fall back to — ADR-0006 §4), so the B1 restore is
  // simply skipped for this manual path; the automated webapp path (which is
  // how every test actually runs) always supplies masterDocId explicitly.
  var cloneId = _readTestControlB1();
  endTestSession(cloneId);
}

function menuSetupFixture() {
  var scenario = _readTestControlArg();
  setupTestFixtures(scenario, { docId: _readTestControlB1() });
}

function menuSyncDocument() {
  var docId = _readTestControlArg();
  syncDocument(docId);
}

function menuSetupAndSync() {
  var scenario = _readTestControlArg();
  setupAndSync(scenario, _readTestControlB1());
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
  debugDocBody(_readTestControlB1());
}

function _readTestControlArg() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var ctrl = ss.getSheetByName('TestControl');
  if (!ctrl) return null;
  var val = ctrl.getRange('A1').getValue();
  return val ? String(val) : null;
}

/**
 * Reads TestControl!B1 — the session pointer beginTestSession() writes the
 * active clone's ID to, and endTestSession() restores to the master template
 * ID. Returns null when the sheet or cell is empty (no session started yet).
 */
function _readTestControlB1() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var ctrl = ss.getSheetByName('TestControl');
  if (!ctrl) return null;
  var val = ctrl.getRange('B1').getValue();
  return val ? String(val) : null;
}
