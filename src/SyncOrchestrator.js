/**
 * SyncOrchestrator.js
 *
 * Top-level entry-points that wire together DocumentDiscovery, DocumentNormalizer,
 * SheetReconciler, and ArchiveManager.
 *
 * Entry-points:
 *   syncAll()              — timed scan / Sync menu command (all registered docs)
 *   syncDocument(docId)    — single-document sync (test / manual invocation)
 */

// ---------------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------------

/**
 * Reads all integer ID values from column 1 (ID) of the "Actions" sheet tab,
 * skipping the header row.  Returns an array of integers.
 *
 * @param {Sheet} sheet  The "Actions" sheet tab.
 * @returns {number[]}
 */
function _getExistingSheetIds(sheet) {
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];

  var numDataRows = lastRow - 1;
  var values = sheet.getRange(2, 1, numDataRows, 1).getValues();
  var ids = [];
  for (var r = 0; r < values.length; r++) {
    var v = values[r][0];
    if (v !== '' && v !== null && v !== undefined) {
      var n = parseInt(v, 10);
      if (!isNaN(n)) ids.push(n);
    }
  }
  return ids;
}

/**
 * Returns the last-sync timestamp (ms since epoch) stored for a given doc,
 * or 0 if never synced.
 *
 * Key format: 'lastSync_' + docId
 *
 * @param {Properties} props  Script properties service.
 * @param {string}     docId  Drive document ID.
 * @returns {number}
 */
function _getLastSyncTs(props, docId) {
  var raw = props.getProperty('lastSync_' + docId);
  if (!raw) return 0;
  var n = parseInt(raw, 10);
  return isNaN(n) ? 0 : n;
}

/**
 * Persists the sync timestamp for a document.
 *
 * @param {Properties} props    Script properties service.
 * @param {string}     docId    Drive document ID.
 * @param {Date}       syncTs   Timestamp to store.
 */
function _setLastSyncTs(props, docId, syncTs) {
  props.setProperty('lastSync_' + docId, String(syncTs.getTime()));
}

// ---------------------------------------------------------------------------
// Core single-document sync logic (shared by syncDocument and syncAll)
// ---------------------------------------------------------------------------

/**
 * Syncs one document against the active spreadsheet.
 * Returns { changes, sheetWinsCount } for caller aggregation.
 *
 * @param {string}      docId   Drive document ID.
 * @param {Spreadsheet} ss      Active spreadsheet.
 * @param {Sheet}       sheet   "Actions" sheet tab.
 * @returns {{ changes: number, sheetWinsCount: number }}
 */
function _syncOneDoc(docId, ss, sheet) {
  var existingIds = _getExistingSheetIds(sheet);
  GasLogger.log('sync.existingIds', { count: existingIds.length });

  var doc = DocumentApp.openById(docId);
  var actions = DocumentNormalizer.normalize(doc, existingIds);
  GasLogger.log('sync.normalized', { docId: docId, actionCount: actions.length });

  var result = SheetReconciler.reconcile(actions, ss.getId());

  // Sheet-wins: propagate updated values back to the document.
  var sheetWinsCount = result.sheetWins.length;
  if (sheetWinsCount > 0) {
    GasLogger.log('sync.sheetWins.propagating', { docId: docId, count: sheetWinsCount });
    DocumentNormalizer.applySheetWins(doc, result.sheetWins);
  }

  return { changes: result.written, sheetWinsCount: sheetWinsCount };
}

// ---------------------------------------------------------------------------
// Public entry-points
// ---------------------------------------------------------------------------

/**
 * Syncs all Google Docs modified in the last 7 days in the configured folder.
 *
 * Steps:
 *   1. Discover modified docs via DocumentDiscovery.
 *   2. For each doc, skip if dateModified has not changed since last sync
 *      (idempotence pre-check — requirements §14.3).
 *   3. Normalize and reconcile each doc.
 *   4. Archive eligible rows.
 *   5. Log summary.
 */
function syncAll() {
  var props = PropertiesService.getScriptProperties();
  var folderId = props.getProperty('DOC_FOLDER_ID') || '';

  var docsProcessed = 0;
  var totalChanges  = 0;
  var archived      = 0;

  try {
    GasLogger.log('sync.all.start', { folderId: folderId });

    var docs = DocumentDiscovery.findModifiedDocs(folderId);

    var ss    = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName('Actions') || ss.getSheets()[0];
    var processedDocIds = [];

    for (var i = 0; i < docs.length; i++) {
      var docMeta = docs[i];
      var docId   = docMeta.id;

      // Idempotence pre-check: skip if doc has not been modified since last sync.
      var lastSyncTs = _getLastSyncTs(props, docId);
      if (lastSyncTs > 0 && docMeta.dateModified.getTime() <= lastSyncTs) {
        GasLogger.log('sync.skip', { docId: docId, reason: 'unchanged since last sync' });
        continue;
      }

      GasLogger.log('sync.doc.start', { docId: docId });
      try {
        var syncResult = _syncOneDoc(docId, ss, sheet);
        totalChanges += syncResult.changes;
        _setLastSyncTs(props, docId, new Date());
        docsProcessed++;
        processedDocIds.push(docId);
        GasLogger.log('sync.doc.complete', { docId: docId, changes: syncResult.changes });
      } catch (docErr) {
        GasLogger.log('sync.error', {
          docId:   docId,
          message: docErr.message,
          stack:   docErr.stack || ''
        });
        // Continue processing remaining docs even if one fails.
      }
    }

    archived = ArchiveManager.archive(ss);

    // Final summary entry — matches the sync.complete predicate used by tests.
    GasLogger.log('sync.complete', {
      docIds:        processedDocIds,
      docsProcessed: docsProcessed,
      changes:       totalChanges,
      archived:      archived
    });
  } catch (err) {
    GasLogger.log('sync.all.error', { message: err.message, stack: err.stack || '' });
    throw err;
  } finally {
    GasLogger.flush();
  }
}

/**
 * Syncs a single Google Doc against the active spreadsheet.
 *
 * Resolution order for docId:
 *   1. testDocId parameter
 *   2. Script property TEST_DOC_ID
 *   3. Fallback string 'stub' (exercises the logger path without a real doc)
 *
 * @param {string} [testDocId]  Optional Drive document ID.
 */
function syncDocument(testDocId) {
  var docId = testDocId
    || PropertiesService.getScriptProperties().getProperty('TEST_DOC_ID')
    || 'stub';

  try {
    GasLogger.log('sync.start', { docId: docId });

    if (docId === 'stub') {
      GasLogger.log('sync.skip', { reason: 'stub docId — no real document to sync' });
      GasLogger.log('sync.complete', { docId: docId, changes: 0 });
      return;
    }

    var ss    = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName('Actions') || ss.getSheets()[0];

    var syncResult = _syncOneDoc(docId, ss, sheet);

    GasLogger.log('sync.complete', { docId: docId, changes: syncResult.changes });
  } catch (err) {
    GasLogger.log('sync.error', { docId: docId, message: err.message, stack: err.stack || '' });
    throw err;
  } finally {
    GasLogger.flush();
  }
}
