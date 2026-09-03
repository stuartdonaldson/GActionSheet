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
  //
  // LABEL COLLISION (ADR-0031 Terminology + Consequences): this menu and the
  // Docs one below are BOTH named 'Action Sync' and BOTH have an item
  // labelled 'Sync' -- but they call different handlers with different
  // promises. This one ('Spreadsheet Sync All', menuSync -> syncAll) has NO
  // document context and never conforms rendering; the Docs one
  // (menuSyncActiveDoc) does both. ADR-0031 records that these labels should
  // be made distinguishable; until they are, do not assume a reader knows
  // which 'Sync' anyone means.
  try {
    SpreadsheetApp.getUi()
      .createMenu('Action Sync')
      .addItem('Sync', 'menuSync')  // "Spreadsheet Sync All" -- no doc context
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
          .addItem('Cleanup Test Docs', 'menuCleanupTestDocs')
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
  // See the label-collision note on the Sheets menu above -- this 'Sync' is
  // NOT that 'Sync'.
  try {
    DocumentApp.getUi()
      .createMenu('Action Sync')
      .addItem('Sync', 'menuSyncActiveDoc')          // "Document Sync" -- has doc context
      .addItem('Force Refresh Style', 'menuForceRefreshActiveDoc')
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

/**
 * "Spreadsheet Sync All" — the SPREADSHEET's Action Sync > Sync item.
 *
 * NOT to be confused with menuSyncActiveDoc, the Docs Extensions > Action
 * Sync > Sync item. Both menus are named 'Action Sync' and both items are
 * labelled 'Sync', but they have different handlers and, under ADR-0031,
 * different behaviour — see ADR-0031 §Terminology.
 *
 * NO DOCUMENT CONTEXT: this sweeps every tracked doc. Under ADR-0031 that
 * puts it with the 30-minute trigger — converges data, never conforms
 * rendering to Config. Document context is the discriminator, not whether a
 * human clicked it.
 */
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

/**
 * "Document Sync" — the DOCS Extensions > Action Sync > Sync item.
 *
 * NOT to be confused with menuSync, the tracker spreadsheet's Action Sync >
 * Sync item. Both menus are named 'Action Sync' and both items are labelled
 * 'Sync', but they are on OPPOSITE sides of ADR-0031's decision — see
 * ADR-0031 Terminology.
 *
 * HAS A DOCUMENT CONTEXT: the user is looking at this specific doc and asked
 * for it to be made right. Under ADR-0031 this is a conformance path -- it
 * converges data AND brings each action's indent into line with the current
 * Config ('SR Indent'/'Field SR Indent'), flushing only actions that do not
 * already match (idempotent; a matching action is not touched). Same promise
 * as the sidebar and the web UI doc sync, which share this sync_document seam
 * (ADR-0030) -- WebApp.js's _handleSyncDocument sets `conform: true`
 * unconditionally for every caller of that route.
 *
 * PARTIALLY IMPLEMENTED: gts-ttns (indent) landed; gts-0wmm
 * (ai_token/action_text character style) has not, and is gated on this same
 * conformance seam plus its own new per-paragraph style sampling on the scan
 * path (ADR-0031 §Rationale). Until it lands, Force Refresh Style remains the
 * only way to propagate a Config STYLE change (indent now self-corrects here
 * without it).
 */
function menuSyncActiveDoc() {
  var docId = _activeOrTestDocId();
  if (docId) _menuProxyAction('sync_document', { docId: docId, force: false });
}

/**
 * Force refresh (gts-t78c): re-renders EVERY ACT/AI action paragraph in the
 * active doc unconditionally, without consulting any diff.
 *
 * ADR-0031 narrows what this is for. It is the unconditional REPAIR tool —
 * reach for it when detection is wrong or a document's rendering is corrupt.
 * It is no longer "the thing you have to remember to run after changing
 * Config indent": under ADR-0031 an ordinary Document Sync (menuSyncActiveDoc,
 * the sidebar, the web UI) already conforms each action's continuation-line
 * indent to the current Config, flushing only the actions that do not match
 * (gts-ttns). Character style (ai_token/action_text) is not yet conforming —
 * gts-0wmm — so Force Refresh Style remains the only way to propagate a
 * Config STYLE change until it lands.
 *
 * The three promises, in full (ADR-0031 §Decision) — the discriminator is
 * DOCUMENT CONTEXT, not whether a human clicked it:
 *   no document context   — 30-min trigger, Spreadsheet Sync All (menuSync):
 *                           converges sheet<->doc DATA only
 *   Document Sync         — menuSyncActiveDoc / sidebar / web UI:
 *                           data + indent conformance (gts-ttns), idempotent
 *   Force Refresh (here)  — the above, plus rewrite even when nothing differs
 */
function menuForceRefreshActiveDoc() {
  var docId = _activeOrTestDocId();
  if (docId) _menuProxyAction('sync_document', { docId: docId, force: true });
}

function menuInsertTrackerActiveDoc() {
  var docId = _activeOrTestDocId();
  if (docId) _menuProxyAction('insert_tracker_table', { docId: docId });
}

/**
 * ADR-0030 (knowledge-base/adr/0030-addon-entry-points-proxy-through-webapp.md):
 * dispatches a state-mutating Docs-menu action through the Web App proxy
 * (_callWebAppProxy, WorkspaceAddonCard.js — same helper the sidebar card
 * actions use) instead of calling syncDocument()/insertTrackerTable() directly
 * under the Marketplace-pinned add-on binding, so a menu click's actual
 * behavior always matches the currently deployed TEST-WEB-APP/PROD-WEB-APP
 * revision. Surfaces a UI alert on failure — a network failure is a normal
 * outcome to design for now, not an uncaught exception; when no live UI
 * session exists (the test-fixture bridge that drives these menu wrappers
 * outside a real Docs session), the alert call itself throws and is ignored —
 * the failure is already recorded via GasLogger inside _callWebAppProxy.
 */
function _menuProxyAction(action, payload) {
  var resp = _callWebAppProxy(action, payload, 'menu.proxy.error');
  if (!resp || resp.ok !== true) {
    try {
      DocumentApp.getUi().alert(
        'Action failed: ' + action + (resp && resp.error ? ' (' + resp.error + ')' : '')
      );
    } catch (e) {
      // No live UI session — already logged by _callWebAppProxy.
    }
  }
  return resp;
}

/**
 * Opens the Export progress dialog (gts-s7ut, Procedure-Exporter.js's
 * showDocumentExportDialog_ + ExportProgressDialog.html). Only reachable
 * from this classic menu — showModalDialog is unavailable from CardService
 * action handlers, which is why export isn't a sidebar button.
 */
function menuShowExportDialog() {
  showDocumentExportDialog_();
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

/**
 * gts-97ol: deletes (not archives) every Actions row and DocData row whose
 * doc_name starts with the configured 'Test Doc Prefix' (Config sheet,
 * default 'GActionSheet-Test-' — ArchiveManager.getConfiguredTestDocPrefix,
 * the same value _testDocName() uses to CREATE those rows in the first
 * place). Sheet rows only — the underlying Drive files are never touched
 * (see 'list_test_drive_docs' / the discovery-scan fixtures for the
 * separate Drive-side cleanup path).
 *
 * Confirmation: when an interactive Sheets UI is available (a real menu
 * click), shows the exact match counts and requires YES before deleting —
 * Cancel or a zero-count case writes nothing. SpreadsheetApp.getUi() throws
 * when there is no interactive UI (run_fixture / webapp invocation, same
 * "not applicable" shape onOpen() above already handles for the Docs-vs-
 * Sheets menu split) — in that case this deliberately SKIPS the confirm and
 * proceeds, since the only headless caller is the test harness's own
 * testToken-gated 'menu_cleanup_test_docs' run_fixture route (gts-ve6z),
 * which is a trusted, already-decided caller in exactly the same sense
 * run_fixture's testToken gate already is. This is a documented bypass of
 * the confirm-dialog branch, not an accidental one — the interactive confirm
 * path itself has no headless equivalent and is verified manually only.
 */
function menuCleanupTestDocs() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var prefix = ArchiveManager.getConfiguredTestDocPrefix(ss);
  var counts = ArchiveManager.purgeByPrefix(ss, prefix, false);

  var ui = null;
  try { ui = SpreadsheetApp.getUi(); } catch (e) { ui = null; }

  if (ui) {
    if (counts.actionsMatched === 0 && counts.docDataMatched === 0) {
      ui.alert('Cleanup Test Docs', 'No rows match prefix "' + prefix + '". Nothing to do.', ui.ButtonSet.OK);
      return { actionsDeleted: 0, docDataDeleted: 0, prefix: prefix };
    }
    var response = ui.alert(
      'Cleanup Test Docs',
      'This will permanently delete ' + counts.actionsMatched + ' Actions row(s) and ' +
        counts.docDataMatched + ' DocData row(s) whose Doc Name starts with "' + prefix +
        '". This cannot be undone. Continue?',
      ui.ButtonSet.YES_NO
    );
    if (response !== ui.Button.YES) return { actionsDeleted: 0, docDataDeleted: 0, prefix: prefix };
  } else if (counts.actionsMatched === 0 && counts.docDataMatched === 0) {
    return { actionsDeleted: 0, docDataDeleted: 0, prefix: prefix };
  }

  var result = ArchiveManager.purgeByPrefix(ss, prefix, true);
  var summary = { actionsDeleted: result.actionsMatched, docDataDeleted: result.docDataMatched, prefix: prefix };
  GasLogger.log('cleanup.testDocs.complete', summary);
  GasLogger.flush();
  return summary;
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
