/**
 * SyncManager.js
 *
 * UC-A: scan the doc for floating actions (identified by AI-N: text token)
 * and upsert rows to the ActionSheet via the Web App proxy (doPost).
 *
 * Identity: a doc-scoped sequential integer N embedded as "AI-N:" text in each
 * floating action paragraph. Global ID = {docFileId}/AI-{N}, stored in sheet col 1.
 * No DocumentApp named ranges are created or required.
 */

// ---------------------------------------------------------------------------
// Shared config
// ---------------------------------------------------------------------------

/**
 * Single source of truth for the action smart-chip link base. Used by the chip
 * insert/flush paths (EditorAddonCard, SyncManager) and the tracker ID links
 * (TrackerTable).
 *
 * Path is namespaced under `NUUTS` — the suite-level scope (Northlake Unitarian
 * Tool Suite). The full chip URL is
 * `https://northlakeuu.org/NUUTS?cmd=preview&docId=<docId>&ain=AI-<N>` — see
 * _buildChipUrl(). `docId`/`ain` are passed as separate params (rather than a
 * single `globalId={docId}/AI-{N}`) because the encoded '/' in globalId
 * confuses downstream URL-rewrite tooling. The legacy `globalId=<docId>/AI-<N>`
 * form is still accepted on parse (_globalIdFromChipUrl) for chips already
 * inserted in live documents.
 *
 * The linkPreview `pathPrefix` in appsscript.json is `NUUTS` (the suite root),
 * so any northlakeuu.org/NUUTS... URL triggers the preview. The redirect at
 * northlakeuu.org/NUUTS → the /exec deployment must point to /exec (not /dev)
 * so Google's URL validation fetch succeeds for non-editor users.
 *
 * NOTE: `hostPattern` (`northlakeuu.org`) in appsscript.json must be kept in
 * sync manually — the manifest cannot read script globals.
 */
var ACTION_CHIP_URL_BASE = 'https://northlakeuu.org/NUUTS';

/**
 * Builds the chip/link-preview URL for a globalId ({docId}/AI-{N}), encoding
 * docId and the AI-N action-item designation as separate query params.
 *
 * @param {string} globalId  {docFileId}/AI-{N}
 * @return {string} chip URL of the form
 *   `ACTION_CHIP_URL_BASE + '?cmd=preview&docId=<docId>&ain=AI-<N>'`
 */
function _buildChipUrl(globalId) {
  var parsed = parseGlobalId(globalId);
  return ACTION_CHIP_URL_BASE + '?cmd=preview&docId=' + encodeURIComponent(parsed.docId) +
    '&ain=' + encodeURIComponent(parsed.actionId);
}

/**
 * Builds the branded team-view URL for a TeamData teamId — the sidebar Team
 * link's fallback target when TeamData has no Team Link of its own.
 *
 * @param {string} teamId
 * @return {string} URL of the form `ACTION_CHIP_URL_BASE + '?cmd=teamview&team=<teamId>'`
 */
function _buildTeamViewUrl(teamId) {
  return ACTION_CHIP_URL_BASE + '?cmd=teamview&team=' + encodeURIComponent(teamId);
}

// 1-based column numbers from the authoritative schema.
var _SCOL = CONTRACT_SCHEMA.sheetAction.columnsByField;

// ---------------------------------------------------------------------------
// Per-docId sync lock (gts-li3g)
// ---------------------------------------------------------------------------

var _SYNC_LOCK_PREFIX = 'SYNC_LOCK_';
// Long enough to cover a slow live sync (Drive/Docs REST round trips can run
// tens of seconds under load), short enough that a crashed execution's lock
// self-heals well within one 30-min trigger cycle rather than wedging a doc
// out of sync indefinitely.
var _SYNC_LOCK_TTL_MS = 5 * 60 * 1000;

/**
 * Per-docId advisory lock so two overlapping syncDocument() executions for
 * the SAME docId (e.g. the 30-min time-based trigger firing mid-manual-sync,
 * or two surfaces/users syncing the same doc at once) cannot race each other
 * and revert a Dirty (sheet-authoritative) row back to the doc's stale value
 * (gts-li3g).
 *
 * GAS's LockService has no native per-key variant (only script/user/document-
 * bound locks), so this uses PropertiesService as the keyed store and
 * LockService.getScriptLock() only for the brief atomic check-and-set —
 * mirroring the existing ACTION_SHEET_QUEUE pattern (WebApp.js's
 * _handleSyncActionRows queue-drain).
 *
 * Deliberately a SKIP on contention, not a blocking wait: a GAS execution
 * cannot cheaply block on another execution's PropertiesService write
 * without burning its own time budget polling, and "sync this doc again
 * next sweep" is a strictly safer failure mode than a busy-wait. A held
 * lock older than _SYNC_LOCK_TTL_MS is treated as abandoned (the prior
 * holder crashed or hit the execution time limit without releasing) and is
 * reclaimed rather than wedging the doc out of sync forever.
 *
 * @param {string} docId
 * @return {boolean} true if this call acquired the lock
 */
function _acquireDocSyncLock(docId) {
  var props = PropertiesService.getScriptProperties();
  var key   = _SYNC_LOCK_PREFIX + docId;
  var lock  = LockService.getScriptLock();
  try {
    lock.waitLock(5000);
  } catch (lockErr) {
    // Couldn't even get the short-lived script lock for the check-and-set —
    // treat conservatively as busy rather than risk a torn read/write.
    return false;
  }
  try {
    var existing = props.getProperty(key);
    if (existing) {
      var heldSince = parseInt(existing, 10);
      if (!isNaN(heldSince) && (Date.now() - heldSince) < _SYNC_LOCK_TTL_MS) {
        return false; // still legitimately held by another in-flight sync
      }
      // Stale — previous holder never released (crash/timeout). Reclaim.
    }
    props.setProperty(key, String(Date.now()));
    return true;
  } finally {
    lock.releaseLock();
  }
}

/**
 * Releases the per-docId sync lock acquired by _acquireDocSyncLock(). Safe
 * to call even if the lock was never held (no-op).
 *
 * @param {string} docId
 */
function _releaseDocSyncLock(docId) {
  PropertiesService.getScriptProperties().deleteProperty(_SYNC_LOCK_PREFIX + docId);
}

// ---------------------------------------------------------------------------
// Public entry points
// ---------------------------------------------------------------------------

function syncDocument(docId, opts) {
  if (!docId) {
    GasLogger.log('sync.error', { msg: 'docId is required' });
    return;
  }
  var force = !!(opts && opts.force);
  if (!_acquireDocSyncLock(docId)) {
    GasLogger.log('sync.locked.skip', {
      docId: docId,
      msg: 'Another syncDocument() execution is already in flight for this doc; skipping rather than proceeding against a stale pre-lock read. Will retry next sweep.'
    });
    // Distinct sentinel (not just falsy/undefined) so callers that need a
    // durable-convergence guarantee (e.g. TestFixtures.js's sync_document
    // fixture) can tell "raced a concurrent execution and did nothing" apart
    // from every other exit path, and retry instead of reporting synced:true
    // on a no-op (gts-kkm7 sidebar_bootstrap_sync race, 2026-08-14).
    return 'locked-skip';
  }
  try {
    var doc;
    try {
      doc = withGasRetry('SyncManager.syncDocument:DocumentApp.openById',
        function () { return DocumentApp.openById(docId); });
    } catch (openErr) {
      GasLogger.log('sync.docNotFound.invalid', { msg: 'Doc not found', docId: docId, err: openErr.message });
      _markDocNotFound([docId]);
      return;
    }
    // DocumentApp.openById() succeeds on trashed docs — check explicitly.
    try {
      if (withGasRetry('SyncManager.syncDocument:DriveApp.getFileById.isTrashed',
        function () { return DriveApp.getFileById(docId).isTrashed(); })) {
        GasLogger.log('sync.docNotFound.trashed', { msg: 'Doc not found', docId: docId, err: 'Document is in Trash' });
        _markDocNotFound([docId]);
        return;
      }
    } catch (driveErr) {
      // Drive API unavailable or permission denied — proceed with sync.
    }

    // Team Scope: folder-walk auto-assignment, UpdateDoc override, and DocData
    // sync. See knowledge-base/staging/epic-b-team-property-sync.md.
    // syncDocument() runs from doc-context entry points (e.g. onSyncNow) where
    // getActiveSpreadsheet() is null — use _openActionSheetSpreadsheet() (TrackerTable.js)
    // for the ACTION_SHEET_ID/TEST_SHEET_ID fallback.
    _syncTeamScope(_openActionSheetSpreadsheet(), docId, ScriptApp.getOAuthToken(), doc.getName());
    // Flush the DocData row written above so it's visible to the separate
    // doPost execution (_handleSyncActionRows, invoked via UrlFetchApp below)
    // — cross-execution reads of the spreadsheet do not see unflushed writes.
    SpreadsheetApp.flush();

    var assignResult = _assignPlaceholderTokens(doc);
    if (assignResult.count > 0) {
      GasLogger.log('sync.assigned', { docId: docId, count: assignResult.count });
    }

    var floatingActions = _scanFloatingActions(doc);

    GasLogger.log('sync.scanned', { docId: docId, count: floatingActions.length });

    // Capture docUrl and docTitle before closing — needed even when empty
    // so WebApp can run orphan detection on existing rows.
    var docUrl   = doc.getUrl();
    var docTitle = doc.getName();

    if (floatingActions.length === 0) {
      doc.saveAndClose();
      var emptySync = _syncActionRows([], docUrl, docTitle, docId, []);
      SpreadsheetApp.flush();
      GasLogger.log('sync.complete', {
        docId: docId,
        upserted: emptySync.upserted || 0,
        updated:  emptySync.updated  || 0
      });
      return;
    }

    // No named range anchoring needed — globalId IS the identity.
    // Duplicates (same AI-N copied) are excluded from the sheet sync to avoid
    // duplicate rows; they are flushed to doc separately so the copy paragraph
    // matches the canonical content.

    // Builds one toFlush[] entry from a canonical (doc-scanned) action record,
    // shared by every path below that adds to toFlush (sheetWin, newly-
    // assigned, duplicate copy, missing-status materialize, force refresh —
    // gts-t78c) so the object shape lives in one place instead of five.
    // `overrides` lets the sheetWin path substitute the sheet's own action/
    // status/assignee/runs values while still sourcing customFields from cf
    // (the doc-canonical record) — gts-t6xs: the sheet does not persist
    // custom_fields yet, so a sheetWin flush must preserve whatever field
    // lines the doc scan (cf, not the sheet win) just found for this
    // globalId; the doc is the only source of truth for them until sheet
    // persistence ships.
    function _buildFlushEntry(cf, globalId, overrides) {
      overrides = overrides || {};
      return {
        N:             cf.N,
        globalId:      globalId,
        action:        overrides.action !== undefined ? overrides.action : cf.actionText,
        status:        overrides.status !== undefined ? overrides.status : cf.status,
        assigneeEmail: overrides.assigneeEmail !== undefined ? overrides.assigneeEmail : cf.assigneeEmail,
        assigneeName:  overrides.assigneeName !== undefined ? overrides.assigneeName : cf.assigneeName,
        runs:          (overrides.runs !== undefined ? overrides.runs : cf.runs) || [],
        customFields:  cf.customFields || {}
      };
    }

    var canonicalByGlobalId = {};
    var hasDuplicateN       = {};
    for (var fi = 0; fi < floatingActions.length; fi++) {
      var fai = floatingActions[fi];
      if (!fai.isDuplicate) {
        canonicalByGlobalId[fai.globalId] = fai;
      } else {
        hasDuplicateN[fai.globalId] = true;
      }
    }

    var allDocGlobalIds = Object.keys(canonicalByGlobalId);
    var anchorResults   = allDocGlobalIds.map(function(gId) {
      var a = canonicalByGlobalId[gId];
      return {
        globalId:      a.globalId,
        wasNew:        false,
        assigneeEmail: a.assigneeEmail,
        assigneeName:  a.assigneeName,
        actionText:    a.actionText,
        status:        a.status,
        runs:          a.runs || [], // gts-zocq: scanned inline bold/italic runs
        customFields:  a.customFields || {} // gts-u0kh: scanned ADR-0027 rule 5/5a field-line blocks
      };
    });

    var syncResult = _syncActionRows(anchorResults, docUrl, docTitle, docId, allDocGlobalIds);

    // Build the set of globalIds that need a REST flush:
    //   - sheetWins: sheet edited → push sheet data back to doc (all occurrences)
    //   - newly assigned: AI: → AI-N: just created → need chip link + badge applied
    //   - duplicates without a sheetWin: copy paragraphs → sync to canonical doc data
    var toFlush = {};
    var sheetWins = syncResult.sheetWins || [];
    for (var si = 0; si < sheetWins.length; si++) {
      var win = sheetWins[si];
      var cf  = canonicalByGlobalId[win.globalId];
      if (!cf) continue;
      // gts-zocq: win.runs is read back from the sheet's RichTextValue.
      toFlush[win.globalId] = _buildFlushEntry(cf, win.globalId, {
        action: win.action, status: win.status,
        assigneeEmail: win.assigneeEmail, assigneeName: win.assigneeName, runs: win.runs
      });
    }
    for (var ni = 0; ni < assignResult.newGlobalIds.length; ni++) {
      var ngId = assignResult.newGlobalIds[ni];
      if (toFlush[ngId]) continue; // sheetWin already covers it
      var cfn = canonicalByGlobalId[ngId];
      if (!cfn) continue;
      toFlush[ngId] = _buildFlushEntry(cfn, ngId);
    }
    for (var gId in hasDuplicateN) {
      if (toFlush[gId]) continue; // sheetWin or new-assign already covers it
      var cf2 = canonicalByGlobalId[gId];
      if (!cf2) continue;
      toFlush[gId] = _buildFlushEntry(cf2, gId);
    }

    // Materialize missing explicit status tokens as '(Open)' in the doc.
    for (var gId3 in canonicalByGlobalId) {
      if (toFlush[gId3]) continue;
      var cfm = canonicalByGlobalId[gId3];
      if (!cfm.hasExplicitStatus) {
        toFlush[gId3] = _buildFlushEntry(cfm, gId3);
      }
    }

    // Force refresh (gts-t78c): re-render every canonical (non-duplicate)
    // action paragraph to current rendering style, even when sheet and doc
    // data already agree and the natural diff above found nothing to flush.
    // Reuses the same toFlush map / _flushActionParagraphs path — force only
    // changes which globalIds land in it, not how they're flushed.
    var forceAddedCount = 0;
    if (force) {
      for (var gIdX in canonicalByGlobalId) {
        if (toFlush[gIdX]) continue;
        toFlush[gIdX] = _buildFlushEntry(canonicalByGlobalId[gIdX], gIdX);
        forceAddedCount++;
      }
      if (forceAddedCount > 0) {
        GasLogger.log('sync.forceFlush', { docId: docId, count: forceAddedCount });
      }
    }

    var flushIds = Object.keys(toFlush);
    if (flushIds.length > 0) {
      var docId2 = doc.getId();
      doc.saveAndClose(); // close before REST calls
      var token = ScriptApp.getOAuthToken();
      // One GET + one batchUpdate for every action item needing a flush in
      // this doc, instead of one GET + one batchUpdate per item
      // (gts-kkm7.3).
      var flushItems = flushIds.map(function (gid) {
        var f = toFlush[gid];
        return { N: f.N, globalId: f.globalId, actionText: f.action, status: f.status,
                 assigneeEmail: f.assigneeEmail, assigneeName: f.assigneeName,
                 runs: f.runs || [], customFields: f.customFields || {} }; // gts-t6xs
      });
      var flushResults = _flushActionParagraphs(docId2, token, flushItems);
      for (var ti = 0; ti < flushIds.length; ti++) {
        if (!flushResults[flushIds[ti]]) _remarkRowDirty(flushIds[ti]);
      }
    } else {
      doc.saveAndClose();
    }

    SpreadsheetApp.flush();

    // Refresh tracker table if the doc has one and anything changed during this sync.
    // "Changed" means: sheetWins flushed to doc, docWins updated the sheet, or new rows inserted.
    var hadChanges = flushIds.length > 0 ||
                     (syncResult.updated || 0) > 0 ||
                     (syncResult.upserted || 0) > 0;
    if (hadChanges) {
      try {
        insertTrackerTable(docId, { onlyIfExists: true });
      } catch (trackerErr) {
        GasLogger.log('sync.tracker-failed', { docId: docId, msg: trackerErr.message });
      }
    }

    GasLogger.log('sync.complete', {
      docId:    docId,
      upserted: syncResult.upserted || 0,
      updated:  syncResult.updated  || 0,
      forced:   force
    });
  } finally {
    GasLogger.flush();
    _releaseDocSyncLock(docId);
  }
}

/**
 * Syncs every document referenced by an existing ActionSheet row.
 *
 * Enumerates unique docIds from the Document HYPERLINK formulas in column 7,
 * then calls syncDocument() for each one.  If a document has been deleted or
 * is no longer accessible, syncDocument() stamps 'Doc Not Found' on every row
 * for that docId.  If a document exists but some actions were removed, the
 * orphan-detection pass in _handleSyncActionRows stamps those rows 'Deleted'.
 *
 * Called by:
 *   - Action Sync > Sync menu item (menuSync)
 *   - 30-minute time-based trigger
 */
function syncAll() {
  // opId correlates this invocation's sub-events (per-doc sync.scanned/
  // sync.complete) in Axiom -- see GasLogger.startOp() (gts-65g1).
  GasLogger.startOp();
  var _syncId = _getIdentity();
  GasLogger.log('sync.all.start.identity', { eu: _syncId.eu, au: _syncId.au });
  try {
    var ss           = SpreadsheetApp.getActiveSpreadsheet();
    var actionsSheet = ss.getSheetByName('Actions');
    if (!actionsSheet) {
      GasLogger.log('sync.all.error', { msg: 'Actions sheet not found', eu: _syncEu, au: _syncAu });
      return;
    }

    var lastRow = actionsSheet.getLastRow();
    if (lastRow < 2) {
      GasLogger.log('sync.all.complete', { docCount: 0 });
      return;
    }

    // Extract unique docIds from the document-formula column.
    // Formula shape: =HYPERLINK("https://docs.google.com/document/d/DOCID/edit", "Title")
    var numRows      = lastRow - 1;
    var formulasCol7 = actionsSheet.getRange(2, _SCOL.document_formula, numRows, 1).getFormulas();
    var docIdSet     = {};
    for (var i = 0; i < formulasCol7.length; i++) {
      var formula = formulasCol7[i][0] || '';
      var m = formula.match(/(?:\/d\/|[?&]id=)([a-zA-Z0-9_-]+)/);
      if (m) docIdSet[m[1]] = true;
    }

    var docIds = Object.keys(docIdSet);
    GasLogger.log('sync.all.start', { docCount: docIds.length });

    var syncStateSheet = _getOrCreateSyncStateSheet(ss);
    var syncState      = _loadSyncState(syncStateSheet);

    // Read globalId + sync_status once for dirty-row detection across all docs.
    var actionData = actionsSheet.getRange(2, 1, numRows, SHEET_HEADERS.length).getValues();

    // Pre-build dirty-doc set in one pass — avoids O(docs × rows) scan per doc.
    var dirtyDocIds = {};
    var alreadyDocNotFound = {};
    for (var d = 0; d < actionData.length; d++) {
      var gidD  = String(actionData[d][_SCOL.global_id   - 1] || '');
      var slashD = gidD.indexOf('/');
      if (actionData[d][_SCOL.sync_status - 1] === 'Dirty' && slashD > 0) {
        dirtyDocIds[gidD.substring(0, slashD)] = true;
      }
      if (actionData[d][_SCOL.sync_status - 1] === 'Doc Not Found' && slashD > 0) {
        alreadyDocNotFound[gidD.substring(0, slashD)] = true;
      }
    }

    // Archive rows that were ALREADY marked 'Doc Not Found' before this sweep starts.
    // Running archive BEFORE the main loop is the grace-period mechanism: rows first
    // marked 'Doc Not Found' in this sweep cannot be archived in the same pass because
    // ArchiveManager runs before those marks are written.
    if (Object.keys(alreadyDocNotFound).length > 0) {
      ArchiveManager.archive(ss);
      GasLogger.log('sync.archive.doc_not_found', { docIds: Object.keys(alreadyDocNotFound) });
    }

    // Read TeamData once, up front, so its folder ids can scope the Drive
    // listing below (gts-uuse) -- team reconciliation further down in this
    // function reuses this same array rather than re-reading the sheet.
    var teamDataRows = _readTeamDataRows(ss);

    // Single batched Drive call for trash/modified/name metadata, scoped to
    // the known team folders (gts-uuse) instead of every Google Doc the
    // executing identity can see account-wide (gts-kkm7.2's original,
    // unscoped version: confirmed 5448 files/12 pages for a 171-doc tracked
    // corpus -- see gts-uuse). Falls back to the old per-doc DriveApp path if
    // the batch fetch itself fails, so a transient Drive/network error
    // degrades to the slower-but-correct behavior rather than misclassifying
    // every doc as not-found.
    //
    // Scoping narrows the *listing* to each team folder's DIRECT children --
    // it does not recurse into subfolders, so a tracked doc nested deeper
    // under a team folder (or legitimately living outside every configured
    // team folder) is simply absent from driveMetadata. That is exactly the
    // "absent from batch listing" case the loop below already treats as
    // inconclusive (gts-rskf) rather than proof of deletion: it is resolved
    // by an authoritative per-doc lookup (now batched -- see
    // _fetchDriveDocMetadataBatch below), never by assuming absence == gone.
    var scopedFolderIds = [];
    var seenFolderIds   = {};
    for (var tf = 0; tf < teamDataRows.length; tf++) {
      var tfId = teamDataRows[tf].folderId;
      if (tfId && !seenFolderIds[tfId]) {
        seenFolderIds[tfId] = true;
        scopedFolderIds.push(tfId);
      }
    }
    var driveMetadata = null;
    try {
      driveMetadata = _fetchDriveDocMetadata(scopedFolderIds);
    } catch (metaErr) {
      GasLogger.log('sync.driveMetadata.error', { msg: metaErr.message });
    }
    // gts-moy1.2: a thrown listing call must NOT also suppress the per-doc
    // fallback safety net below. Treat a failed listing as "every doc is
    // absent from the listing" (map with zero entries) rather than null --
    // downstream code already treats listing-absence as inconclusive and
    // routes it through the same batched fallback lookup a normal listing
    // miss would use, instead of silently skipping metadata for the whole
    // sweep.
    if (!driveMetadata) driveMetadata = {};

    // Batch the per-doc fallback lookups (gts-uuse point 3) for every tracked
    // doc absent from the scoped listing, instead of firing
    // _fetchSingleDocMetadata once per doc inside the main loop below. Only
    // attempted when there is more than one such doc -- a single miss is
    // cheaper as a direct call than as a one-item "batch".
    var fallbackProbes = {};
    var missingDocIds = [];
    for (var mi = 0; mi < docIds.length; mi++) {
      if (!driveMetadata[docIds[mi]]) missingDocIds.push(docIds[mi]);
    }
    if (missingDocIds.length === 1) {
      fallbackProbes[missingDocIds[0]] = _fetchSingleDocMetadata(missingDocIds[0]);
    } else if (missingDocIds.length > 1) {
      fallbackProbes = _fetchDriveDocMetadataBatch(missingDocIds);
    }

    var synced = 0, skipped = 0;
    var notFoundDocIds = [];
    for (var j = 0; j < docIds.length; j++) {
      var docId = docIds[j];

      // Docs already marked 'Doc Not Found' stay skipped unless Drive now shows
      // them ALIVE — present in the listing and not trashed. Skipping them
      // unconditionally (the original behaviour) made the mark ONE-WAY: a doc
      // wrongly marked could never recover, so gts-rskf's Shared Drive
      // misclassification was permanent and the rows were archived 24h later.
      // But falling through on mere presence is just as wrong: files.list
      // returns TRASHED files too, so ~150 legitimately dead docs would be
      // re-processed and re-marked on every sweep (measured: notFound 3 -> 154,
      // 1053 trashed events in one window, and syncAll slow enough to time the
      // harness out). Only a live document is worth the round trip.
      if (alreadyDocNotFound[docId]) {
        var revivedMeta = driveMetadata ? driveMetadata[docId] : null;
        if (!revivedMeta || revivedMeta.trashed) {
          skipped++;
          continue;
        }
        GasLogger.log('sync.docNotFound.revived', {
          docId: docId, msg: 'Previously marked not-found but live in Drive; re-syncing'
        });
      }

      var isTrashed, lastModified, docTitle;
      if (driveMetadata) {
        var meta = driveMetadata[docId];
        if (!meta) {
          // Absent from the batch listing. This is NOT proof the doc is gone
          // (gts-rskf): a paginated files.list is not a consistent snapshot,
          // and its observed size has swung by hundreds of docs between
          // consecutive runs. Confirm with an authoritative per-doc lookup
          // before marking anything not-found — the previous code marked on
          // absence alone and silently archived live documents' actions.
          var probe = fallbackProbes[docId] || _fetchSingleDocMetadata(docId);
          if (probe.status === 'gone') {
            GasLogger.log('sync.docNotFound.missing', {
              msg: 'Doc not found', docId: docId,
              err: 'Absent from Drive metadata listing; per-doc lookup confirms deleted'
            });
            notFoundDocIds.push(docId);
            continue;
          }
          if (probe.status === 'unknown') {
            // Drive could not answer either way (transient error, quota, or a
            // permission blip). Leave the doc and its rows exactly as they
            // are and retry next cycle — never archive on an inconclusive read.
            GasLogger.log('sync.driveMetadata.indeterminate', {
              msg: 'Doc reachability unknown; skipped without marking',
              docId: docId, err: probe.err
            });
            skipped++;
            continue;
          }
          meta = probe.meta;
          GasLogger.log('sync.driveMetadata.listingMiss', {
            msg: 'Doc absent from batch listing but reachable per-doc', docId: docId
          });
        }
        isTrashed    = meta.trashed;
        lastModified = meta.lastModified;
        docTitle     = meta.name;
      } else {
        // Fallback: batch fetch failed above, check this doc individually.
        try {
          var driveFile = withGasRetry('SyncManager.syncAll:DriveApp.getFileById(fallback)',
            function () { return DriveApp.getFileById(docId); });
          isTrashed    = driveFile.isTrashed();
          lastModified = driveFile.getLastUpdated();
          docTitle     = driveFile.getName();
        } catch (driveErr) {
          // Can't reach Drive — fall through to syncDocument which handles open failure.
          syncDocument(docId);
          _updateSyncState(syncStateSheet, docId, new Date(), '', syncState);
          synced++;
          continue;
        }
      }

      if (isTrashed) {
        GasLogger.log('sync.docNotFound.trashed', { msg: 'Doc not found', docId: docId, err: 'Document is in Trash' });
        notFoundDocIds.push(docId);
        continue;
      }

      var lastSynced = syncState[docId] ? syncState[docId].syncedAt : null;
      if (lastSynced && lastModified <= lastSynced && !dirtyDocIds[docId]) {
        GasLogger.log('sync.skip', { msg: 'unchanged since last sync', docId: docId });
        skipped++;
        continue;
      }

      syncDocument(docId);
      _updateSyncState(syncStateSheet, docId, new Date(), docTitle, syncState);
      synced++;
    }

    // One webapp call for every not-found doc found this sweep, instead of one
    // per doc (gts-kkm7.1).
    if (notFoundDocIds.length > 0) {
      _markDocNotFound(notFoundDocIds);
    }

    GasLogger.log('sync.all.complete', { docCount: docIds.length, synced: synced, skipped: skipped, notFound: notFoundDocIds.length });

    // ── DocData integrity pass (gts-6ipb) ──────────────────────────
    // Docs skipped above by the lastModified<=lastSynced optimization never
    // refresh their DocData row even if Actions rows changed state since the
    // last sync (e.g. closed via sheet edit). Recompute action_count/
    // resolved_count/doc_name for every docId seen in Actions from the
    // in-memory actionData/formulasCol7 already loaded above — no extra
    // sheet reads. Mirrors the per-doc reconciliation in WebApp.js's
    // sync_action_rows handler, but applied across all docs in one pass.
    var docTitleByDocId  = {};
    for (var ti = 0; ti < formulasCol7.length; ti++) {
      var tFormula = formulasCol7[ti][0] || '';
      var tIdMatch = tFormula.match(/(?:\/d\/|[?&]id=)([a-zA-Z0-9_-]+)/);
      if (!tIdMatch) continue;
      var tTitleMatch = tFormula.match(/,\s*"([^"]*)"\s*\)\s*$/);
      if (tTitleMatch && !docTitleByDocId[tIdMatch[1]]) {
        docTitleByDocId[tIdMatch[1]] = tTitleMatch[1];
      }
    }

    var docIdsWithAnyRows = {}; // any docId appearing in Actions, any status
    var integrityCounts   = {}; // docId -> { actionCount, resolvedCount }, Deleted/Doc Not Found excluded
    for (var ii = 0; ii < actionData.length; ii++) {
      var iGlobalId = String(actionData[ii][_SCOL.global_id - 1] || '');
      var iSlash    = iGlobalId.indexOf('/');
      if (iSlash <= 0) continue;
      var iDocId = iGlobalId.substring(0, iSlash);
      docIdsWithAnyRows[iDocId] = true;
      var iSyncStatus = actionData[ii][_SCOL.sync_status - 1];
      if (iSyncStatus === 'Deleted' || iSyncStatus === 'Doc Not Found') continue;
      if (!integrityCounts[iDocId]) integrityCounts[iDocId] = { actionCount: 0, resolvedCount: 0 };
      integrityCounts[iDocId].actionCount++;
      if (isResolved(actionData[ii][_SCOL.status - 1])) integrityCounts[iDocId].resolvedCount++;
    }

    // Team reconciliation (gts-b6dm): teamScope resolution is otherwise sticky
    // (_syncTeamScope trusts the DocData mirror once resolved, by design —
    // gts-j8cn), so a document moved to a different team's folder in Drive
    // never gets its DocData.teamId corrected on its own. Re-derive it here,
    // in the same once-per-sweep pass, from the doc's actual current folder
    // ancestry. folderTeamCache memoizes folderId -> team across docs in this
    // sweep so documents under common ancestor folders share the walk cost —
    // see _walkFolderForTeam's doc comment for the caching contract and a
    // noted-but-not-implemented further optimization.
    //
    // directFolderTeamMap is an O(1) fast path built from TeamData itself (no
    // Drive calls): most tracked docs sit directly inside a team's configured
    // folder, and driveMetadata (fetched above for the trashed/modified sweep)
    // already carries each doc's immediate parent folder id at zero extra
    // cost. Only docs nested deeper than one level under a team folder (or
    // absent from driveMetadata, e.g. the per-doc fallback path) fall through
    // to the full _walkFolderForTeam walk. Without this, re-deriving team for
    // every tracked doc every sweep was measured to push syncAll's GAS
    // execution past its time budget on a sheet with a large docId backlog.
    // teamDataRows was already read above (gts-uuse), before the scoped
    // driveMetadata fetch -- reused here rather than re-reading the sheet.
    var folderTeamCache = {};
    var teamToken        = null; // fetched lazily, only if a correction is actually written
    var directFolderTeamMap = {};
    for (var dtIdx = 0; dtIdx < teamDataRows.length; dtIdx++) {
      var dtRow = teamDataRows[dtIdx];
      if (dtRow.folderId && !Object.prototype.hasOwnProperty.call(directFolderTeamMap, dtRow.folderId)) {
        directFolderTeamMap[dtRow.folderId] = dtRow;
      }
    }

    // Hard time budget for the EXPENSIVE fallback only (_walkFolderForTeam,
    // 1+ Drive calls per doc) -- the O(1) directFolderTeamMap path above is
    // unmetered since it costs no Drive calls. Confirmed by a live GAS
    // execution-ceiling failure during this feature's own test run: a sheet
    // with a large docId backlog made the per-doc walk fallback alone run
    // long enough to hit Apps Script's ~6-minute execution limit and silently
    // kill the whole syncAll invocation (observed as a client-side socket
    // timeout with no sync.all.complete log ever written). Once the budget is
    // exhausted, remaining docs simply keep their current DocData.teamId
    // un-reconciled this sweep -- no worse than pre-gts-b6dm behavior -- and
    // get picked up on a later sweep instead of taking the whole sync down.
    var TEAM_WALK_BUDGET_MS = 120000;
    var teamWalkStartMs        = new Date().getTime();
    var teamWalkBudgetExceeded = false;

    var integrityUpdated = 0;
    var integrityCreated = 0;
    var teamReconciled   = 0;
    for (var docIdKey in docIdsWithAnyRows) {
      if (!docIdsWithAnyRows.hasOwnProperty(docIdKey)) continue;
      var existingRow = _readDocDataRow(ss, docIdKey);
      var computed = integrityCounts[docIdKey] || { actionCount: 0, resolvedCount: 0 };

      // A doc can reach here with no DocData row at all -- e.g. its Actions
      // rows were seeded by a path that never called syncDocument/_syncTeamScope
      // (the normal first-pass writer), or a first-pass write was interrupted
      // before flush. Such a doc has no team, so it's invisible to every
      // team-scoped read even though its rows are otherwise live. Backstop by
      // treating "no row" as "row needing to be created" -- but ONLY when the
      // doc still has at least one currently-active (non-Deleted/non-Doc-Not-
      // Found) row: docIdsWithAnyRows/integrityCounts were built from the
      // actionData snapshot read at the TOP of syncAll, before this sweep's
      // ArchiveManager.archive() call ran. A docId whose only rows were 'Doc
      // Not Found' and just aged past the 24h threshold has its DocData row
      // correctly evicted by ArchiveManager (gts-4tnr) earlier in this same
      // sweep -- computed.actionCount === 0 for exactly that case, so this
      // guard stops the backstop from resurrecting a row eviction just removed.
      var isNewRow = !existingRow && computed.actionCount > 0;
      if (!existingRow && !isNewRow) continue;
      if (isNewRow) {
        existingRow = {
          fileId: docIdKey, docName: '', lastSyncTime: null, docUpdated: null,
          syncStatus: '', teamId: '', actionCount: 0, resolvedCount: 0
        };
      }
      var computedName = docTitleByDocId[docIdKey] || existingRow.docName;

      // 'UpdateDoc' is a pending manual override — it, not the folder walk,
      // must win (mirrors _syncTeamScope's own precedence). 'Doc Not Found'/
      // 'Deleted' docs are unreachable or gone — walking Drive for them would
      // only throw and waste a call.
      var resolvedTeamId   = existingRow.teamId;
      var resolvedTeamLink = null;
      var teamChanged       = false;
      if (existingRow.syncStatus !== 'UpdateDoc' &&
          existingRow.syncStatus !== 'Doc Not Found' &&
          existingRow.syncStatus !== 'Deleted') {
        var docMeta       = driveMetadata ? driveMetadata[docIdKey] : null;
        var directTeamRow = (docMeta && docMeta.parentId)
          ? directFolderTeamMap[docMeta.parentId]
          : null;
        var walkResult;
        if (directTeamRow) {
          walkResult = { teamId: directTeamRow.teamId, teamLink: directTeamRow.teamLink || '', folderId: directTeamRow.folderId };
        } else if (teamWalkBudgetExceeded) {
          walkResult = false; // budget already spent this sweep — defer to next sweep, don't clobber
        } else {
          if (new Date().getTime() - teamWalkStartMs > TEAM_WALK_BUDGET_MS) {
            teamWalkBudgetExceeded = true;
            GasLogger.log('sync.teamScope.walk.budgetExceeded', { docId: docIdKey });
            walkResult = false;
          } else {
            walkResult = _walkFolderForTeam(docIdKey, teamDataRows, folderTeamCache);
          }
        }
        // false = walk errored (e.g. transient Drive failure) — not proof of
        // "no team"; leave DocData.teamId exactly as it was rather than clobber it.
        if (walkResult !== false) {
          var newTeamId = walkResult ? walkResult.teamId : '';
          if (newTeamId !== existingRow.teamId) {
            resolvedTeamId   = newTeamId;
            resolvedTeamLink = walkResult ? (walkResult.teamLink || '') : '';
            teamChanged       = true;
          }
        }
      }

      var changed = (
        isNewRow ||
        existingRow.actionCount !== computed.actionCount ||
        existingRow.resolvedCount !== computed.resolvedCount ||
        existingRow.docName !== computedName ||
        teamChanged
      );
      if (!changed) continue;
      _getOrUpsertDocDataRow(
        ss, docIdKey,
        computedName,
        existingRow.lastSyncTime || new Date(),
        resolvedTeamId,
        existingRow.syncStatus,
        computed.actionCount,
        computed.resolvedCount
      );
      if (isNewRow) {
        GasLogger.log('sync.docData.created', {
          docId: docIdKey, msg: 'Actions row(s) had no DocData row; created during integrity pass',
          teamId: resolvedTeamId
        });
        integrityCreated++;
      }
      if (teamChanged) {
        if (!teamToken) teamToken = ScriptApp.getOAuthToken();
        _setDocAppProperty(docIdKey, 'teamScope', resolvedTeamId, teamToken);
        _setDocAppProperty(docIdKey, 'teamLink', resolvedTeamLink || '', teamToken);
        GasLogger.log('sync.teamScope.reconciled', {
          docId: docIdKey, oldTeamId: existingRow.teamId, newTeamId: resolvedTeamId
        });
        teamReconciled++;
      }
      integrityUpdated++;
    }
    GasLogger.log('sync.integrity.complete', {
      updated: integrityUpdated, created: integrityCreated, teamReconciled: teamReconciled
    });
  } catch (e) {
    GasLogger.log('sync.all.error', { msg: e.message });
  } finally {
    GasLogger.flush();
    GasLogger.endOp();
  }
}

function onActionSheetEdit(e) {
  if (WriteGuard.isActive()) return;
  var range = e.range;
  var row   = range.getRow();
  if (row < 2) return;
  var col = range.getColumn();
  if ([_SCOL.assignee_email, _SCOL.assignee_name, _SCOL.action_text, _SCOL.status].indexOf(col) === -1) return;
  var sheet = range.getSheet();
  if (sheet.getName() !== 'Actions') return;

  // Stamp Date Modified and mark Sync Status = 'Dirty' so the next bidirectional
  // sync knows this row was edited on the sheet side (sheet wins conflict resolution).
  // For multi-row pastes, stamp ALL rows in the range — if only the first row is
  // marked Dirty, the subsequent syncDocument call treats the other pasted rows as
  // doc-wins and overwrites them with old doc values.
  var numRows = range.getNumRows();
  var dateModified = new Date();
  WriteGuard.wrap(function () {
    if (numRows === 1) {
      sheet.getRange(row, _SCOL.modified_date).setValue(dateModified);
      sheet.getRange(row, _SCOL.sync_status).setValue('Dirty');
    } else {
      var dates    = [];
      var dirtyCol = [];
      for (var r = 0; r < numRows; r++) {
        dates.push([dateModified]);
        dirtyCol.push(['Dirty']);
      }
      sheet.getRange(row, _SCOL.modified_date, numRows, 1).setValues(dates);
      sheet.getRange(row, _SCOL.sync_status,   numRows, 1).setValues(dirtyCol);
    }
  });

  _syncSheetRowToDoc(sheet, row);
}

/**
 * Propagates a single ActionSheet row edit to the corresponding floating action
 * in the source document via REST batchUpdate.
 *
 * Reads: globalId, action_text, status, document_formula (from SHEET_HEADERS positions).
 * Extracts docId from the Document hyperlink formula.
 * Extracts N from the globalId (format: {docId}/AI-{N}).
 *
 * @param {Sheet} sheet    The ActionSheet "Actions" tab
 * @param {number} row     1-based row number (guaranteed >= 2)
 */
function _syncSheetRowToDoc(sheet, row) {
  try {
    var rowData       = sheet.getRange(row, 1, 1, SHEET_HEADERS.length).getValues()[0];
    var globalId      = rowData[_SCOL.global_id      - 1];
    var assigneeEmail = rowData[_SCOL.assignee_email - 1];
    var assigneeName  = rowData[_SCOL.assignee_name  - 1];
    var action        = rowData[_SCOL.action_text    - 1];
    var status        = rowData[_SCOL.status         - 1];
    var docFormula    = sheet.getRange(row, _SCOL.document_formula).getFormula();
    // gts-zocq: this sheet-edit flush path re-reads the cell's own
    // RichTextValue so bold/italic the user just typed directly INTO the
    // sheet cell (not merely round-tripped from the doc) also survives the
    // flush, not only the syncDocument()-driven paths.
    var runs = _richTextRunsForCell(sheet.getRange(row, _SCOL.action_text));

    if (!globalId) return;
    if (!docFormula) return;

    var docIdMatch = docFormula.match(/(?:\/d\/|[?&]id=)([a-zA-Z0-9_-]+)/);
    if (!docIdMatch) return;
    var docId = docIdMatch[1];

    var parsed = parseGlobalId(globalId);
    if (isNaN(parsed.N)) return;
    var N = parsed.N;

    var token = ScriptApp.getOAuthToken();
    // gts-t6xs: this onEdit-trigger flush has no customFields source (the
    // sheet does not persist custom_fields, and this path -- unlike the
    // batch syncAll loop -- has no fresh doc scan to read them back from).
    // customFields is omitted here, so a field-line continuation still gets
    // dropped on THIS specific trigger until sheet persistence ships or this
    // path gains its own scan. Known, tracked gap -- see gts-t6xs.
    var ok = _flushActionParagraph(docId, token, N, globalId, action, status, assigneeEmail, assigneeName || '', runs);
    if (ok) {
      // Flush confirmed — clear Dirty immediately rather than waiting for WebApp round-trip.
      WriteGuard.wrap(function () { sheet.getRange(row, _SCOL.sync_status).setValue(''); });
      GasLogger.log('sync.sheet-to-doc.done', { globalId: globalId });
      // Note: syncDocument() was removed here. It caused a race condition: the trigger
      // fires in a separate GAS execution, opens the doc via DocumentApp.openById with a
      // stale cached view (status=pre-edit), and the doc-wins path overwrites the sheet
      // back to the old value. Chip-resolved assigneeName propagation is deferred to the
      // next scheduled syncAll sweep.
      //
      // Refresh the tracker table (gts-m2gf). Removing syncDocument() above also removed
      // the only tracker refresh on the edit path, so a sheet edit updated the floating
      // action while the Action Item Summary kept the old text — permanently, because a
      // later syncDocument sees Dirty already cleared and doc==sheet, computes
      // hadChanges=false, and skips the refresh too.
      //
      // This does NOT reintroduce the race above: that was syncDocument()'s doc->sheet
      // reconciliation overwriting the sheet from a stale doc read. insertTrackerTable
      // only READS the sheet (TrackerTable.js _readTrackerSheetRows) and writes the
      // document's table, so it cannot clobber the row we just flushed. It is the same
      // call syncDocument makes after its own flush, and it already no-ops via
      // _trackerRowsMatch when nothing changed.
      try {
        insertTrackerTable(docId, { onlyIfExists: true });
      } catch (trackerErr) {
        GasLogger.log('sync.tracker-failed', { docId: docId, globalId: globalId, msg: trackerErr.message });
      }
    } else {
      GasLogger.log('sync.sheet-to-doc.flush-failed', { globalId: globalId });
    }
  } catch (err) {
    GasLogger.log('sync.sheet-to-doc.error', { row: row, msg: err.message });
  } finally {
    GasLogger.flush();
  }
}

// ---------------------------------------------------------------------------
// Scanner
// ---------------------------------------------------------------------------

/**
 * Parses a single paragraph/list-item for an AI-N: floating action token.
 * Returns a populated action object or null if the paragraph is not an action.
 *
 * @param {GoogleAppsScript.Document.Paragraph|GoogleAppsScript.Document.ListItem} para
 * @param {number} bodyIdx  body-child index of this paragraph (or its containing table)
 * @param {string} docId
 * @param {Object} seenN   mutable duplicate-tracking map
 */
function _parseParagraphAsFloatingAction(para, bodyIdx, docId, seenN) {
  // Normalize here too, not just in the soft-return parser: this fast path
  // owns single-token paragraphs, whose action text may still carry \r/\v
  // continuation breaks. Without it the two parsers would hand back the same
  // action with different line-break spellings, and doc-vs-sheet action-text
  // comparisons would spuriously differ (gts-dou2).
  var rawParaText  = para.getText();
  var normTracked  = _normalizeLineEndingsTracked(rawParaText);
  var fullText     = normTracked.text.replace(/\n$/, '');
  var fullOffsets  = normTracked.offsets.slice(0, fullText.length);
  // gts-jxrw: only consume space/tab after the colon here, NOT \n — a bare
  // "\s*" would silently swallow the paragraph's first line break, making a
  // bare "AI-N: " immediately followed by a soft-return continuation line
  // indistinguishable from a single-line "AI-N: <that line's text>". Keeping
  // the \n in afterToken is what lets the empty-first-line check below
  // detect the bare-token case.
  var tokenMatch = _matchActionTokenPrefixed(fullText);
  if (!tokenMatch) return null;
  // gts-jxrw: only consume space/tab after the colon here, NOT \n — see comment above.
  var trailingWs = fullText.slice(tokenMatch.match.length).match(/^[ \t]*/)[0];
  var consumedLen = tokenMatch.match.length + trailingWs.length;

  var N          = tokenMatch.N;
  var globalId   = docId + '/' + tokenMatch.prefix + '-' + N;
  var afterToken = fullText.slice(consumedLen);
  var afterOffsets = fullOffsets.slice(consumedLen);

  // gts-jxrw: an empty first line after the token ("AI-N: " with nothing
  // else on that line) means the user left the action bare. Do NOT absorb
  // any soft-return continuation line(s) that follow within this same
  // paragraph — those are the "next unrelated line" case reported live
  // (a following line typed under a bare token got merged into the action
  // and round-tripped back into the doc as one merged line). Truncate to
  // the (empty) first line only; the remainder of the paragraph text is
  // simply not part of this action's actionText.
  //
  // Deliberately narrow: this does NOT attempt to distinguish "legitimate
  // multi-line action" from "unrelated next line" when the first line is
  // NON-empty — soft-return continuation after real action text is still
  // absorbed to end-of-paragraph, unchanged, because that is the
  // intentional multi-line-action model (gts-dr8j) already covered by
  // test_soft_return_survives_sidebar_status_flush and the AC-T2/T3/T4
  // scanner tests. Distinguishing "real continuation" from "next unrelated
  // line" in the non-empty-first-line case is an open, perceptual design
  // question the frozen AC for gts-jxrw does not require solving — see
  // plan-fix.md Session 3 Result for the explicit scope note.
  var firstBreakIdx = afterToken.indexOf('\n');
  if (firstBreakIdx !== -1) {
    var firstLine = afterToken.slice(0, firstBreakIdx);
    if (firstLine.trim() === '') {
      afterToken = firstLine;
      afterOffsets = afterOffsets.slice(0, firstBreakIdx);
    }
  }

  // Walk children: skip leading INLINE_IMAGE, find the AI-N: TEXT, then look
  // for an optional assignee chip or email-text after it.
  var numChildren         = para.getNumChildren();
  var assigneeEmail       = '';
  var assigneeName        = '';
  var assigneeSearchStart = 0;
  for (var ci = 0; ci < numChildren; ci++) {
    var ch = para.getChild(ci);
    if (ch.getType() === DocumentApp.ElementType.INLINE_IMAGE) continue;
    if (ch.getType() === DocumentApp.ElementType.TEXT) { assigneeSearchStart = ci + 1; break; }
  }
  for (var ai = assigneeSearchStart; ai < numChildren; ai++) {
    var ac = para.getChild(ai);
    if (ac.getType() === DocumentApp.ElementType.PERSON) {
      assigneeEmail = ac.asPerson().getEmail() || '';
      assigneeName  = ac.asPerson().getName()  || '';
      break;
    }
    if (ac.getType() === DocumentApp.ElementType.TEXT) {
      var t  = ac.asText().getText();
      var em = t.match(_ASSIGNEE_TEXT_REGEX_LEADING_WS);
      if (em) { assigneeEmail = em[1]; assigneeName = _nameFromEmail(assigneeEmail); }
      break;
    }
  }

  // gts-q23h: the assignee strip and the header-line-scoped status extraction
  // both live in _parseActionHeaderLineTracked, shared with the soft-return
  // parser. A PERSON chip found in the child walk above still wins over a
  // text assignee found here (chips are the richer source: they carry a real
  // display name), but the text form is stripped off actionText either way.
  var header            = _parseActionHeaderLineTracked(afterToken, afterOffsets);
  var actionText        = header.actionText;
  var actionOffsets     = header.offsets;
  var status            = header.status;
  var hasExplicitStatus = header.hasExplicitStatus;
  if (!assigneeEmail && header.assigneeEmail) {
    assigneeEmail = header.assigneeEmail;
    assigneeName  = header.assigneeName;
  }

  // gts-zocq SCAN: bold/italic runs over the final actionText, sampled from
  // the paragraph's own Text element at each surviving character's original
  // offset. [] when nothing in range is bold/italic (common case).
  var runs = _extractInlineRuns(para.editAsText(), actionText, actionOffsets);
  // gts-eezz: ADR-0027 rule 5/5a continuation fields, {} when none.
  var customFields = _buildCustomFieldsFromBlocks(para.editAsText(), header.customFieldBlocks || []);

  var action = {
    bodyChildIndex:    bodyIdx,
    paragraph:         para,
    globalId:          globalId,
    N:                 N,
    assigneeEmail:     assigneeEmail,
    assigneeName:      assigneeName,
    actionText:        actionText,
    status:            status,
    hasExplicitStatus: hasExplicitStatus,
    isDuplicate:       seenN[N] === true,
    runs:              runs,
    customFields:      customFields
  };
  seenN[N] = true;
  return action;
}

/**
 * Normalizes soft-return line-ending variants (\r, \r\n, \v — DocumentApp
 * represents Shift+Enter differently across GAS runtime versions) to a plain
 * \n. Shared core used by every paragraph scanner and by the sheet-write
 * normalizers in WebApp.js, so the doc-side and sheet-side notion of "one
 * line break" never drifts apart (gts-dou2).
 */
function _normalizeLineEndings(text) {
  return (text || '').replace(/\r\n/g, '\n').replace(/[\r\v]/g, '\n');
}

// ---------------------------------------------------------------------------
// Inline bold/italic run tracking (gts-zocq)
//
// The scanner derives actionText through several string transforms (token
// strip, assignee strip, line-ending normalization, status-token extraction/
// rejoin) before it reaches its final form. To know which DOCUMENT character
// offset (the index _sampleActionItemStyle-style Text.isBold(offset)/
// isItalic(offset) calls expect, relative to the paragraph's own raw text)
// each surviving actionText character came from, every transform below has a
// "tracked" twin that carries a parallel offsets[] array through the same
// slice/trim/join operations. offsets[i] === -1 marks a synthetic character
// (e.g. the single space _extractStatusTokenTracked inserts when rejoining a
// before/after split, or a line-join point in the soft-return parser) with no
// single source offset — treated as unformatted (bold:false, italic:false),
// a deliberate, documented simplification (see plan-fix.md Session 9 Result).
// ---------------------------------------------------------------------------

/**
 * Tracked twin of _normalizeLineEndings: returns the normalized text AND a
 * parallel offsets[] array mapping each output character back to its index
 * in the raw input (the \r\n -> \n two-to-one case keeps the \r's offset).
 *
 * @param {string} raw
 * @returns {{text: string, offsets: Array<number>}}
 */
function _normalizeLineEndingsTracked(raw) {
  raw = raw || '';
  var text = '';
  var offsets = [];
  for (var i = 0; i < raw.length; i++) {
    var ch = raw[i];
    if (ch === '\r' && raw[i + 1] === '\n') {
      text += '\n'; offsets.push(i); i++;
    } else if (ch === '\r' || ch === '\v') {
      text += '\n'; offsets.push(i);
    } else {
      text += ch; offsets.push(i);
    }
  }
  return { text: text, offsets: offsets };
}

/**
 * Tracked twin of String.prototype.trim() — trims text and drops the
 * corresponding entries from offsets in lockstep.
 */
function _trimTracked(text, offsets) {
  var start = 0, end = text.length;
  while (start < end && /\s/.test(text[start])) start++;
  while (end > start && /\s/.test(text[end - 1])) end--;
  return { text: text.slice(start, end), offsets: offsets.slice(start, end) };
}

/**
 * Splits tracked (text, offsets) on '\n' into per-line {text, offsets} pairs,
 * dropping the '\n' separators themselves (mirrors String.split('\n')).
 */
function _splitTrackedLines(text, offsets) {
  var lines = [];
  var startIdx = 0;
  for (var i = 0; i <= text.length; i++) {
    if (i === text.length || text[i] === '\n') {
      lines.push({ text: text.slice(startIdx, i), offsets: offsets.slice(startIdx, i) });
      startIdx = i + 1;
    }
  }
  return lines;
}

/**
 * Tracked twin of _extractStatusToken (see its own doc comment for the
 * status-token extraction/rejoin rule, gts-v0py/gts-1tbe) — returns the same
 * {status, hasExplicitStatus, actionText} shape plus a parallel `offsets`
 * array for the returned actionText.
 *
 * gts-1tbe fix: gts-v0py's "last paren group anywhere in the text" rule
 * regressed gts-28q's mid-text-parens hardening — 'Review the (draft)
 * proposal' had its ONLY paren group treated as a status token purely
 * because it was the last (only) one found, silently dropping '(draft)'
 * from the stored action text even though 'proposal' after it is plainly a
 * continuation of the same sentence, not a trailing status annotation.
 *
 * Rule (position-based, per gts-28q, refined to still honor gts-v0py): the
 * last '(...)' group only qualifies as the status token if what follows it,
 * once trimmed, is EMPTY (the pre-v0py anchored case) OR begins with a
 * non-word character (e.g. 'Peter (Open) - done' — a dash-led trailing
 * annotation, gts-v0py's frozen case). Trailing text that begins with a
 * plain word character ('(draft) proposal') reads as sentence continuation,
 * not an annotation, so the group is left as literal text and no status is
 * detected. A non-qualifying last group is never treated as a status
 * candidate — earlier groups in the same text are not considered either,
 * consistent with "only the trailing token" being the only sanctioned
 * status-token grammar.
 *
 * @param {string} actionText
 * @param {Array<number>} offsets  same length as actionText
 * @returns {{status: string, hasExplicitStatus: boolean, actionText: string, offsets: Array<number>}}
 */
function _extractStatusTokenTracked(actionText, offsets) {
  var status  = 'Open';
  var lastMatch = null;
  var re = /\(([^)]*)\)/g;
  var m;
  while ((m = re.exec(actionText)) !== null) lastMatch = m;
  if (!lastMatch) {
    return { status: status, hasExplicitStatus: false, actionText: actionText, offsets: offsets };
  }
  var beforeRaw = actionText.slice(0, lastMatch.index);
  var afterRaw  = actionText.slice(lastMatch.index + lastMatch[0].length);
  var beforeTrim = _trimTracked(beforeRaw, offsets.slice(0, lastMatch.index));
  var afterTrim  = _trimTracked(afterRaw, offsets.slice(lastMatch.index + lastMatch[0].length));
  var before = beforeTrim.text, after = afterTrim.text;
  // gts-1tbe: reject a non-trailing group up front — mid-sentence prose
  // continuation ('proposal') disqualifies the group entirely, leaving the
  // original text untouched rather than rejoining around it.
  if (after !== '' && /^\w/.test(after)) {
    return { status: status, hasExplicitStatus: false, actionText: actionText, offsets: offsets };
  }
  status = lastMatch[1].trim() || 'Open';
  var rejoined, rejoinedOffsets;
  if (before && after) {
    rejoined = before + ' ' + after;
    rejoinedOffsets = beforeTrim.offsets.concat([-1], afterTrim.offsets);
  } else if (before) {
    rejoined = before; rejoinedOffsets = beforeTrim.offsets;
  } else {
    rejoined = after; rejoinedOffsets = afterTrim.offsets;
  }
  return { status: status, hasExplicitStatus: true, actionText: rejoined, offsets: rejoinedOffsets };
}

/**
 * Converts a Sheets RichTextValue's getRuns() array (each run the longest
 * substring with consistent styling) into gts-zocq's {start,end,bold,italic,link}
 * shape, using cumulative run-text length for offsets (Sheets' RichTextValue
 * API exposes runs in order but not their own start/end indices directly).
 * Link uses RichTextValue's native per-run getLinkUrl() (ADR-0028 — no new
 * sheet column). Returns [] when nothing in the cell is bold/italic/linked
 * (mirrors _extractInlineRuns' "empty means plain" convention).
 *
 * @param {Array<GoogleAppsScript.Spreadsheet.RichTextValue>} richRuns
 * @returns {Array<{start:number,end:number,bold:boolean,italic:boolean,link:?string}>}
 */
function _runsFromRichTextRuns(richRuns) {
  var runs = [];
  var offset = 0;
  var hasFormatting = false;
  for (var i = 0; i < richRuns.length; i++) {
    var seg   = richRuns[i];
    var text  = seg.getText();
    var style = seg.getTextStyle();
    var bold   = !!style.isBold();
    var italic = !!style.isItalic();
    var link   = seg.getLinkUrl() || null;
    var start = offset;
    var end   = offset + text.length;
    runs.push({ start: start, end: end, bold: bold, italic: italic, link: link });
    if (bold || italic || link) hasFormatting = true;
    offset = end;
  }
  return hasFormatting ? runs : [];
}

/**
 * Reads back gts-zocq inline runs from a single Actions-sheet action_text
 * cell's RichTextValue — the "flush a sheetWins/Dirty row" read path.
 *
 * @param {GoogleAppsScript.Spreadsheet.Range} range  a single-cell range
 * @returns {Array<{start:number,end:number,bold:boolean,italic:boolean,link:?string}>}
 */
function _richTextRunsForCell(range) {
  var rtv = range.getRichTextValue();
  if (!rtv) return [];
  return _runsFromRichTextRuns(rtv.getRuns());
}

/**
 * Builds a RichTextValue applying gts-zocq inline bold/italic/link `runs`
 * over `text`, or null when runs is empty — callers fall back to the
 * pre-existing setValue(text) for the common unformatted case (zero
 * behavior/perf change for plain action text). Link uses RichTextValue's
 * native setLinkUrl (ADR-0028 — no new sheet column).
 *
 * @param {string} text
 * @param {Array<{start:number,end:number,bold:boolean,italic:boolean,link:?string}>} runs
 * @returns {?GoogleAppsScript.Spreadsheet.RichTextValue}
 */
function _buildRichTextValueForActionText(text, runs) {
  if (!runs || !runs.length) return null;
  var builder = SpreadsheetApp.newRichTextValue().setText(text || '');
  var applied = false;
  for (var i = 0; i < runs.length; i++) {
    var r = runs[i];
    var start = Math.max(0, Math.min(r.start, (text || '').length));
    var end   = Math.max(start, Math.min(r.end, (text || '').length));
    if (end <= start) continue;
    var style = SpreadsheetApp.newTextStyle().setBold(!!r.bold).setItalic(!!r.italic).build();
    builder.setTextStyle(start, end, style);
    if (r.link) builder.setLinkUrl(start, end, r.link);
    applied = true;
  }
  return applied ? builder.build() : null;
}

/**
 * Shifts/clips gts-zocq run offsets to match _normalizeActionText's
 * (WebApp.js) normalize+trim of the same raw text — analogous to the
 * leading-whitespace-shift _buildFlushRequests applies on the flush side, so
 * runs computed at scan time (which may include untrimmed leading/trailing
 * whitespace when no status token was found) still land on the correct
 * characters of the text actually stored in the sheet.
 *
 * @param {string} rawText
 * @param {Array<{start:number,end:number,bold:boolean,italic:boolean,link:?string}>} runs
 * @returns {{text:string, runs:Array<Object>}}
 */
function _shiftRunsForNormalize(rawText, runs) {
  var normalized = _normalizeLineEndings(rawText || '');
  var leadWs = (normalized.match(/^\s*/) || [''])[0].length;
  var trimmed = normalized.trim();
  var shifted = [];
  for (var i = 0; i < (runs || []).length; i++) {
    var r = runs[i];
    var start = Math.max(0, r.start - leadWs);
    var end   = Math.min(trimmed.length, r.end - leadWs);
    if (end > start) shifted.push({ start: start, end: end, bold: !!r.bold, italic: !!r.italic, link: r.link || null });
  }
  return { text: trimmed, runs: shifted };
}

/**
 * Collapses actionText's per-character bold/italic/link (sampled at each
 * offsets[i] via textEl.isBold/isItalic/getLinkUrl(offset), -1 offsets
 * treated as unformatted) into a minimal set of {start,end,bold,italic,link}
 * runs. Returns [] (not a single all-false run) when nothing in the range is
 * bold, italic, or linked — the common, unformatted case stays cheap and the
 * sheet/transit payload carries no `runs` noise for plain text (gts-zocq
 * transit decision, extended to links by ADR-0028 rule 3).
 *
 * ADR-0028 boundary: offsets covers actionText only (post token/assignee
 * strip) — a link sampled here never extends into the chip token range.
 *
 * @param {GoogleAppsScript.Document.Text} textEl  para.editAsText()
 * @param {string} actionText
 * @param {Array<number>} offsets  same length as actionText, -1 = synthetic
 * @returns {Array<{start:number,end:number,bold:boolean,italic:boolean,link:?string}>}
 */
function _extractInlineRuns(textEl, actionText, offsets) {
  var runs = [];
  var cur  = null;
  for (var i = 0; i < actionText.length; i++) {
    var off    = offsets[i];
    var bold   = off >= 0 ? !!textEl.isBold(off)   : false;
    var italic = off >= 0 ? !!textEl.isItalic(off) : false;
    var link   = off >= 0 ? (textEl.getLinkUrl(off) || null) : null;
    if (cur && cur.bold === bold && cur.italic === italic && cur.link === link) {
      cur.end = i + 1;
    } else {
      if (cur) runs.push(cur);
      cur = { start: i, end: i + 1, bold: bold, italic: italic, link: link };
    }
  }
  if (cur) runs.push(cur);
  var hasFormatting = false;
  for (var ri = 0; ri < runs.length; ri++) {
    if (runs[ri].bold || runs[ri].italic || runs[ri].link) { hasFormatting = true; break; }
  }
  return hasFormatting ? runs : [];
}

/**
 * Extracts a trailing-parenthetical status token '(Status)' from actionText.
 * Shared by both _parseParagraphAsFloatingAction (single-token fast path) and
 * _parseSoftReturnParagraphActions (soft-return path) so the two parsers
 * cannot drift on this rule (gts-v0py).
 *
 * gts-v0py fix: the previous implementation anchored the status token to the
 * END of actionText (/\(([^)]*)\)\s*$/). Any user text typed AFTER the status
 * token (e.g. "text (Open) - done") broke that anchor, so hasExplicitStatus
 * came back false, the literal "(Open) - done" stayed embedded inside
 * actionText, and the next flush appended a SECOND status token — producing
 * the doubled "(Open) ... (Open)" reported live.
 *
 * Fix: find the LAST '(...)' group anywhere in actionText (not requiring it
 * to be at the very end), treat its contents as the status, and rejoin the
 * text before and after it. Decision on trailing text (documented per the
 * AC's explicit requirement to not leave this implicit): trailing text is
 * PRESERVED, not rejected — dropping user-typed text silently would be a
 * data-loss regression consistent with the pattern this project has
 * repeatedly fixed elsewhere (Session 1/2). 'text (Status) trailing' ->
 * actionText='text trailing', status='Status'.
 *
 * A single trailing group (the pre-fix common case, '(Status)' with nothing
 * after it) is unaffected: after-text is empty, so the result is identical
 * to the old anchored match.
 *
 * gts-1tbe refinement: the LAST-group-anywhere rule above regressed gts-28q's
 * mid-text-parens hardening — a paren group is now only accepted as the
 * status token when the text after it is empty OR begins with a non-word
 * character (a dash-led annotation like ' - done'). Trailing text that
 * starts with a plain word ('(draft) proposal') reads as sentence
 * continuation, not a status annotation, so the group is left untouched and
 * no status is detected. See _extractStatusTokenTracked's doc comment for
 * the full rule and worked examples.
 *
 * @param {string} actionText
 * @returns {{status: string, hasExplicitStatus: boolean, actionText: string}}
 */
function _extractStatusToken(actionText) {
  // Thin wrapper over _extractStatusTokenTracked (gts-zocq) — identity
  // offsets (offsets[i] === i) since callers of this untracked form don't
  // need per-character formatting, only the string/status result. Behavior
  // is unchanged; see _extractStatusTokenTracked's doc comment for the rule.
  var identityOffsets = [];
  for (var oi = 0; oi < actionText.length; oi++) identityOffsets.push(oi);
  var tracked = _extractStatusTokenTracked(actionText, identityOffsets);
  return { status: tracked.status, hasExplicitStatus: tracked.hasExplicitStatus, actionText: tracked.actionText };
}

/**
 * ADR-0027 rule 5/5a: bounded fieldLine production, gts-eezz.
 *
 * fieldLine := fieldName ':' ( [ \t] inlineValue? | EOL )
 * fieldName := [A-Za-z] [A-Za-z0-9 _-]{0,31}
 *
 * gts-eezz resolution (human decision, 2026-08-26 — the written grammar's
 * charset alone cannot separate a field name like 'Consult With' from prose
 * that happens to contain a colon, e.g. 'then he said: we should ship it' —
 * 'then he said' is 12 chars, all letters/spaces, and satisfies the charset
 * exactly like 'Consult With' does; ADR-0027's own stated reason for
 * rejecting it ("exceeds 32 characters") is not actually true of that
 * example): every space-separated WORD in fieldName must start with an
 * uppercase letter, matching every field-name example on file (Target,
 * Progress, Notes, Consult With, Due) and excluding lowercase sentence
 * continuations. This is a narrowing of the written production, not
 * documented in ADR-0027/CONTEXT.md itself — tracked as a gap to fold back
 * into those docs (see gts-eezz).
 *
 * The 32-char total-length bound (ADR-0027 Consequences: "a judgment call")
 * is enforced separately, after the regex match, since regex quantifier
 * bounds compose awkwardly with the per-word uppercase constraint.
 */
var _FIELD_LINE_REGEX = /^([A-Z][A-Za-z0-9_-]*(?: [A-Z][A-Za-z0-9_-]*)*):(?:[ \t](.*))?$/;
var _FIELD_NAME_MAX_LENGTH = 32;

/**
 * Splits the continuation text following an action's header line (ADR-0027
 * rule 5a) into the action-text prose block and an ordered list of
 * custom-field blocks.
 *
 * A paragraph's continuation is an ordered sequence of blocks: the action
 * body opens block 0 (unnamed — its lines fold back into actionText); each
 * recognized fieldLine closes the currently open block and opens a new one
 * named by its field. A prose line (no leading whitespace, no match for
 * _FIELD_LINE_REGEX, or a field name over _FIELD_NAME_MAX_LENGTH chars)
 * belongs to whichever block is open when it is read — it never jumps back
 * to block 0 once a field has been opened. A repeated field name reopens its
 * EXISTING block (append, not overwrite) rather than starting a new one, so
 * field order in the output is first-appearance order.
 *
 * `restText`/`restOffsets` is the tracked continuation text starting with the
 * leading '\n' after the header line (i.e. exactly what
 * `_parseActionHeaderLineTracked` used to append to actionText verbatim), or
 * '' when the action has no continuation at all.
 *
 * @param {string} restText
 * @param {Array<number>} restOffsets  same length as restText
 * @returns {{actionTextExtra: string, actionTextExtraOffsets: Array<number>,
 *            customFieldBlocks: Array<{name: string, text: string, offsets: Array<number>}>}}
 */
function _parseFieldContinuationBlocksTracked(restText, restOffsets) {
  if (!restText) {
    return { actionTextExtra: '', actionTextExtraOffsets: [], customFieldBlocks: [] };
  }

  function joinTrackedLines(lines, offsetsList) {
    if (!lines.length) return { text: '', offsets: [] };
    var text = lines[0];
    var offsets = offsetsList[0];
    for (var i = 1; i < lines.length; i++) {
      text += '\n' + lines[i];
      offsets = offsets.concat([-1], offsetsList[i]);
    }
    return { text: text, offsets: offsets };
  }

  // allLines[0] is always '' — the (empty) text before the leading '\n' this
  // rest string starts with — and is not a continuation line.
  var allLines = _splitTrackedLines(restText, restOffsets).slice(1);

  var block0 = { lines: [], offsetsList: [] };
  var current = block0;
  var fieldsByName = {};
  var fieldOrder = [];

  for (var i = 0; i < allLines.length; i++) {
    var line = allLines[i];
    var m = _FIELD_LINE_REGEX.exec(line.text);
    if (m && m[1].length <= _FIELD_NAME_MAX_LENGTH) {
      var name  = m[1];
      var value = m[2] || '';
      var valueStart   = line.text.length - value.length;
      var valueOffsets = line.offsets.slice(valueStart);
      var block = fieldsByName[name];
      if (!block) {
        block = { lines: [], offsetsList: [] };
        fieldsByName[name] = block;
        fieldOrder.push(name);
      }
      block.lines.push(value);
      block.offsetsList.push(valueOffsets);
      current = block;
    } else {
      current.lines.push(line.text);
      current.offsetsList.push(line.offsets);
    }
  }

  var actionExtra = joinTrackedLines(block0.lines, block0.offsetsList);
  var customFieldBlocks = fieldOrder.map(function (name) {
    var block  = fieldsByName[name];
    var joined = joinTrackedLines(block.lines, block.offsetsList);
    return { name: name, text: joined.text, offsets: joined.offsets };
  });

  return {
    actionTextExtra:        actionExtra.text,
    actionTextExtraOffsets: actionExtra.offsets,
    customFieldBlocks:      customFieldBlocks
  };
}

/**
 * Converts the {name, text, offsets} blocks from
 * _parseFieldContinuationBlocksTracked into the custom_fields shape
 * (ADR-0024 / ADR-0028 rule 6): {FieldName: {text, runs}}. `{}` when there
 * are no blocks — the additive-optional convention `runs` established
 * (gts-zocq), extended here to the whole field.
 *
 * @param {GoogleAppsScript.Document.Text} textEl  para.editAsText()
 * @param {Array<{name: string, text: string, offsets: Array<number>}>} blocks
 * @returns {Object<string, {text: string, runs: Array<Object>}>}
 */
function _buildCustomFieldsFromBlocks(textEl, blocks) {
  var customFields = {};
  for (var i = 0; i < blocks.length; i++) {
    var b = blocks[i];
    customFields[b.name] = { text: b.text, runs: _extractInlineRuns(textEl, b.text, b.offsets) };
  }
  return customFields;
}

/**
 * ADR-0027 rules 1-4: the shared header-line parser.
 *
 * `text`/`offsets` are the tracked (gts-zocq) action body — everything after
 * the ACT-N:/AI-N: token, INCLUDING any soft-return continuation lines. This
 * helper owns the three header-line rules so the two paragraph parsers
 * (_parseParagraphAsFloatingAction's single-token fast path and
 * _parseSoftReturnParagraphActions' soft-return path) cannot drift on them —
 * the same drift _extractStatusTokenTracked was extracted to prevent
 * (gts-v0py, gts-q23h).
 *
 * Rule 1 — assignee: an optional leading '@' sigil is accepted and is NOT
 * stored ('@jane@example.com' and 'jane@example.com' both yield
 * assigneeEmail='jane@example.com'). The trailing '\s*' is deliberately
 * whitespace-general, not '[ \t]*': a bare 'ACT-7: jane@example.com' followed
 * by a continuation line has always consumed that line break here, and rule 7
 * (strict superset) requires that output stay identical.
 *
 * Rule 4 — status scope: the status token is extracted from the HEADER LINE
 * only (the text up to the first soft return, after the assignee strip), then
 * the continuation remainder is re-appended verbatim. Scanning the whole
 * paragraph, as this code did before, silently missed a header-line status
 * once continuation lines existed and could read a field value's trailing
 * parenthesis as the status. The position rule WITHIN the header line
 * (gts-28q/v0py/1tbe) is unchanged — see _extractStatusTokenTracked.
 *
 * Rule 3 — '|' carries no meaning: it is literal text everywhere. There is no
 * delimiter and no escape, so there is deliberately no pipe handling here or
 * anywhere else in the scanner.
 *
 * A paragraph with no continuation lines takes the identical path it took
 * before this helper existed (rest is empty), so rule 7 holds by construction.
 *
 * @param {string} text
 * @param {Array<number>} offsets  same length as text
 * @returns {{assigneeEmail: string, assigneeName: string, actionText: string,
 *            offsets: Array<number>, status: string, hasExplicitStatus: boolean}}
 */
function _parseActionHeaderLineTracked(text, offsets) {
  var assigneeEmail = '';
  var assigneeName  = '';
  var m = text.match(_ASSIGNEE_TEXT_REGEX);
  if (m) {
    assigneeEmail = m[1];
    assigneeName  = _nameFromEmail(assigneeEmail);
    text    = text.slice(m[0].length);
    offsets = offsets.slice(m[0].length);
  }

  var breakIdx      = text.indexOf('\n');
  var header        = breakIdx === -1 ? text : text.slice(0, breakIdx);
  var headerOffsets = breakIdx === -1 ? offsets : offsets.slice(0, breakIdx);
  var rest          = breakIdx === -1 ? '' : text.slice(breakIdx);
  var restOffsets   = breakIdx === -1 ? [] : offsets.slice(breakIdx);

  var tracked = _extractStatusTokenTracked(header, headerOffsets);

  // gts-eezz: rest (continuation lines) is no longer appended to actionText
  // verbatim. ADR-0027 rule 5a splits it into the action-text prose block
  // (block 0, folded back in below — identical output to the old verbatim
  // append for a paragraph with no Field: lines, preserving rule 7's
  // strict-superset guarantee) and an ordered list of custom-field blocks.
  var continuation  = _parseFieldContinuationBlocksTracked(rest, restOffsets);
  var actionText    = tracked.actionText;
  var actionOffsets = tracked.offsets;
  if (continuation.actionTextExtra) {
    actionText    = actionText + '\n' + continuation.actionTextExtra;
    actionOffsets = actionOffsets.concat([-1], continuation.actionTextExtraOffsets);
  }

  return {
    assigneeEmail:      assigneeEmail,
    assigneeName:       assigneeName,
    actionText:         actionText,
    offsets:            actionOffsets,
    status:             tracked.status,
    hasExplicitStatus:  tracked.hasExplicitStatus,
    customFieldBlocks:  continuation.customFieldBlocks
  };
}

/**
 * Inverse of _normalizeLineEndings for the flush (sheet -> doc) direction:
 * turns each normalized \n into the one character the Docs REST API's
 * insertText accepts as a genuine soft line break inside a single paragraph,
 * U+000B (vertical tab) — the same break Shift+Enter produces in the editor.
 *
 * Why U+000B specifically (gts-dr8j): InsertTextRequest documents that
 * "some control characters (U+0000-U+0008, U+000C-U+001F) ... will be stripped
 * out of the inserted text". That is exactly why the earlier \r-based attempt
 * concatenated the lines with no separator at all (gts-kkm7.5) — \r is U+000D,
 * inside the stripped range. \n (U+000A) survives but is documented to
 * "implicitly create a new Paragraph", i.e. a hard return. U+000B is the only
 * line-break character that is neither stripped nor paragraph-splitting.
 */
function _toSoftReturnText(text) {
  if (!text) return text;
  return _normalizeLineEndings(text).replace(/\n/g, '\v').trim();
}

/**
 * Scans all paragraphs in a table's cells for AI-N: tokens, appending any
 * found to `actions`.  Only call this for non-tracker tables.
 */
function _collectTableCellActions(table, tableBodyIdx, docId, actions, seenN) {
  for (var r = 0; r < table.getNumRows(); r++) {
    var row = table.getRow(r);
    for (var c = 0; c < row.getNumCells(); c++) {
      var cell = row.getCell(c);
      for (var p = 0; p < cell.getNumChildren(); p++) {
        var cp   = cell.getChild(p);
        var cpt  = cp.getType();
        var para = cpt === DocumentApp.ElementType.PARAGRAPH ? cp.asParagraph()
                 : cpt === DocumentApp.ElementType.LIST_ITEM  ? cp.asListItem()
                 : null;
        if (!para) continue;
        _collectActionsFromParagraph(para, tableBodyIdx, docId, seenN, actions);
      }
    }
  }
}

/**
 * gts-ogev: looks for a PERSON chip structurally adjacent to `rawOffset` — a
 * character index into this SAME paragraph's raw para.getText() string (the
 * offset space _normalizeLineEndingsTracked/_splitTrackedLines already track
 * everywhere else in this file).
 *
 * PERSON (like INLINE_IMAGE) contributes zero characters to getText(), so a
 * chip can never be located BY a text offset — only by which two TEXT
 * children straddle it. This walks the paragraph's structural children
 * (para.getChild(ci)), accumulating TEXT lengths until the running total
 * equals rawOffset (i.e. we are exactly at the boundary rawOffset points to),
 * then checks the immediately following non-TEXT-before-it sibling(s) for a
 * PERSON element. This is the same walk _parseParagraphAsFloatingAction uses
 * (skip to the first TEXT child, then look at what comes after it) — just
 * entered at an arbitrary boundary instead of always the first TEXT child,
 * which is what a multi-line soft-return paragraph requires (see ADR-0027
 * open question / this bead's design note).
 *
 * @param {GoogleAppsScript.Document.Paragraph|GoogleAppsScript.Document.ListItem} para
 * @param {number} rawOffset  index into para.getText(); null skips the search
 * @returns {{email: string, name: string}|null}
 */
function _personChipAtParaOffset(para, rawOffset) {
  if (rawOffset === null || rawOffset === undefined) return null;
  var numChildren = para.getNumChildren();
  var cum = 0;
  for (var ci = 0; ci < numChildren; ci++) {
    var ch = para.getChild(ci);
    if (ch.getType() === DocumentApp.ElementType.TEXT) {
      var len = ch.asText().getText().length;
      if (cum + len === rawOffset) {
        for (var ni = ci + 1; ni < numChildren; ni++) {
          var nc = para.getChild(ni);
          var nt = nc.getType();
          if (nt === DocumentApp.ElementType.PERSON) {
            return { email: nc.asPerson().getEmail() || '', name: nc.asPerson().getName() || '' };
          }
          if (nt === DocumentApp.ElementType.TEXT) break; // next line's text starts here first — no chip at this boundary
        }
        return null;
      }
      cum += len;
    }
    // PERSON / INLINE_IMAGE contribute 0 chars — do not advance cum.
  }
  return null;
}

/**
 * Handles paragraphs containing one or more AI-N: tokens that appear after
 * soft-return (\n) lines — the pattern where the user writes contextual text
 * on the first line(s) and AI-N: tokens on subsequent lines within a single
 * paragraph element.
 *
 * Returns an array of action objects (one per AI-N: token found).
 *
 * gts-ogev: a PERSON chip placed immediately after the AI-N: token (same
 * position the single-token fast path reads it from) is detected via
 * _personChipAtParaOffset and takes priority over a text-based email, exactly
 * as on the fast path — see flush()'s chip-vs-header-text precedence below.
 */
function _parseSoftReturnParagraphActions(para, bodyIdx, docId, seenN, fullText) {
  var normalized = _normalizeLineEndings(fullText);
  var lines   = normalized.split('\n');
  var results = [];
  var curN    = null;
  var curPrefix = null;
  var curLines = [];
  var curOffsets = []; // gts-zocq: parallel per-line offsets[], see below
  var curChip = null;  // gts-ogev: {email, name} PERSON chip found right after this action's token, or null

  // gts-zocq: independently re-derive a tracked (text, offsets) view of this
  // SAME paragraph's raw text so each line's characters can be traced back to
  // a document offset for bold/italic sampling. `lines` above (the untracked,
  // behavior-preserving path every pre-existing test exercises) is left
  // untouched; `trackedLineOffsets[i]` is only consulted for runs and is
  // degraded to all -1 (unformatted) if it and `lines` ever disagree in
  // length — a defensive fallback, not expected in normal operation since
  // both derive from the same _normalizeLineEndings semantics.
  var paraTracked        = _normalizeLineEndingsTracked(para.getText());
  var normalizedFullText = paraTracked.text.replace(/\n$/, '');
  var fullOffsetsForLines = paraTracked.offsets.slice(0, normalizedFullText.length);
  var trackedLineList     = _splitTrackedLines(normalizedFullText, fullOffsetsForLines);
  var trackedLineOffsets  = (trackedLineList.length === lines.length)
    ? trackedLineList.map(function (l) { return l.offsets; })
    : lines.map(function (l) { var arr = []; for (var k = 0; k < l.length; k++) arr.push(-1); return arr; });

  function flush() {
    if (curN === null) return;
    var rawText = curLines.join('\n');
    var rawOffsets = curOffsets.length ? curOffsets[0] : [];
    for (var oi = 1; oi < curOffsets.length; oi++) rawOffsets = rawOffsets.concat([-1], curOffsets[oi]);
    var trimmed = _trimTracked(rawText, rawOffsets);
    rawText = trimmed.text;
    var offsets = trimmed.offsets;

    // gts-q23h: same shared header-line parser the single-token fast path uses.
    var header            = _parseActionHeaderLineTracked(rawText, offsets);
    var assigneeEmail     = header.assigneeEmail;
    var assigneeName      = header.assigneeName;
    var status            = header.status;
    var hasExplicitStatus = header.hasExplicitStatus;
    rawText               = header.actionText;
    offsets               = header.offsets;
    // gts-ogev: a PERSON chip wins over a text-based assignee, matching the
    // single-token fast path's precedence (_parseParagraphAsFloatingAction).
    if (curChip) {
      assigneeEmail = curChip.email;
      assigneeName  = curChip.name;
    }
    var N = curN;
    var runs = _extractInlineRuns(para.editAsText(), rawText, offsets);
    // gts-eezz: ADR-0027 rule 5/5a continuation fields, {} when none.
    var customFields = _buildCustomFieldsFromBlocks(para.editAsText(), header.customFieldBlocks || []);
    results.push({
      bodyChildIndex:    bodyIdx,
      paragraph:         para,
      globalId:          docId + '/' + curPrefix + '-' + N,
      N:                 N,
      assigneeEmail:     assigneeEmail,
      assigneeName:      assigneeName,
      actionText:        rawText,
      status:            status,
      hasExplicitStatus: hasExplicitStatus,
      isDuplicate:       seenN[N] === true,
      runs:              runs,
      customFields:      customFields
    });
    seenN[N] = true;
  }

  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    var lineOffsets = trackedLineOffsets[i];
    var m = _matchActionTokenPrefixed(line);
    if (m) {
      flush();
      curN    = m.N;
      curPrefix = m.prefix;
      var consumed = m.match.length + (line.slice(m.match.length).match(/^\s*/) || [''])[0].length;
      curLines = [line.slice(consumed)];
      curOffsets = [lineOffsets.slice(consumed)];
      // gts-ogev: locate a PERSON chip sitting right after the token, the
      // same position the fast path reads it from. rawOffset is the raw
      // para.getText() index of the first character following the
      // token+whitespace on this line — or, when the token consumed the
      // entire line (no trailing text before the paragraph's own line
      // break), one past the line's last raw character.
      var chipRawOffset = consumed < lineOffsets.length
        ? lineOffsets[consumed]
        : (lineOffsets.length > 0 ? lineOffsets[lineOffsets.length - 1] + 1 : null);
      curChip = _personChipAtParaOffset(para, chipRawOffset);
    } else if (curN !== null) {
      curLines.push(line); // continuation line
      curOffsets.push(lineOffsets);
    }
    // else: contextual text before first AI token — skip (AC-3)
  }
  flush();
  return results;
}

/**
 * Collects floating actions from a single paragraph/list-item, dispatching
 * to the correct parser based on whether the paragraph has a single leading
 * AI-N: token (fast path) or uses the soft-return multi-token pattern (new
 * path). gts-ogev: both paths detect a PERSON chip after the token.
 *
 * Appends any found actions to the `actions` array in place.
 *
 * @param {Array} [unparseableOut]  ADR-0027 rule 6 / gts-xvlu. When provided,
 *   a paragraph whose text begins with a token (ACT|AI)-\d+ but does not
 *   complete the grammar (no trailing colon — e.g. the gts-tis pipe-delimited
 *   spelling) is pushed here as {bodyChildIndex, leadingText} instead of
 *   being silently dropped. A prose paragraph with no token-like prefix is
 *   never pushed. Optional and additive: omitted (every pre-existing caller)
 *   is a no-op, unchanged from before this parameter existed.
 */
function _collectActionsFromParagraph(para, bodyIdx, docId, seenN, actions, unparseableOut) {
  var raw  = para.getText();
  var text = _normalizeLineEndings(raw).replace(/\n$/, '');
  var tokenCount = (text.match(new RegExp('(?:^|\\n)(?:' + _ACTION_TOKEN_READ_PREFIXES.join('|') + ')-\\d+:', 'g')) || []).length;
  if (tokenCount === 0) {
    if (unparseableOut && _ACTION_TOKEN_LOOKS_LIKE_REGEX_ANCHORED.test(text)) {
      unparseableOut.push({ bodyChildIndex: bodyIdx, leadingText: text.split('\n')[0] });
    }
    return;
  }

  // Single token at paragraph start: use existing logic.
  if (tokenCount === 1 && _ACTION_TOKEN_REGEX_ANCHORED.test(text)) {
    var action = _parseParagraphAsFloatingAction(para, bodyIdx, docId, seenN);
    if (action) actions.push(action);
    return;
  }

  // Multi-token or soft-return (token not at paragraph start): new parser.
  var softActions = _parseSoftReturnParagraphActions(para, bodyIdx, docId, seenN, text);
  for (var i = 0; i < softActions.length; i++) actions.push(softActions[i]);
}

/**
 * Walks the doc body and returns one entry per floating-action paragraph or
 * list item that contains an AI-N: token, including those inside non-tracker
 * table cells (see _collectTableCellActions).
 *
 * Detection: paragraph full text starts with "AI-N:" (optionally preceded by
 * an inline image, which does not appear in DocumentApp getText()), or contains
 * one or more AI-N: tokens after soft-return (\n) lines.
 *
 * @param {GoogleAppsScript.Document.Document} doc
 * @param {Array} [unparseableOut]  ADR-0027 rule 6 / gts-xvlu — optional
 *   out-array; see _collectActionsFromParagraph. Top-level body paragraphs/
 *   list items only, not table cells — out of scope for the frozen AC.
 * @returns {Array<{bodyChildIndex, paragraph, globalId, N, assigneeEmail, assigneeName, actionText, status, hasExplicitStatus, isDuplicate}>}
 */
function _scanFloatingActions(doc, unparseableOut) {
  var body    = doc.getBody();
  var docId   = doc.getId();
  var n       = body.getNumChildren();
  var actions = [];
  var seenN   = {};
  var trackerHeadingSeen  = false;
  var trackerTableSkipped = false;

  for (var i = 0; i < n; i++) {
    var child     = body.getChild(i);
    var childType = child.getType();

    if (childType === DocumentApp.ElementType.TABLE) {
      // Skip the tracker table (first TABLE after the tracker heading).
      if (trackerHeadingSeen && !trackerTableSkipped) { trackerTableSkipped = true; continue; }
      _collectTableCellActions(child.asTable(), i, docId, actions, seenN);
      continue;
    }

    var isPara     = childType === DocumentApp.ElementType.PARAGRAPH;
    var isListItem = childType === DocumentApp.ElementType.LIST_ITEM;
    if (!isPara && !isListItem) continue;

    // Track the tracker heading so we know which TABLE to skip.
    if (!trackerHeadingSeen) {
      var txt = child.getText().trim();
      if (txt === _TRACKER_HEADING || txt === _TRACKER_HEADING_OLD) {
        trackerHeadingSeen = true;
        continue;
      }
    }

    var para = isPara ? child.asParagraph() : child.asListItem();
    _collectActionsFromParagraph(para, i, docId, seenN, actions, unparseableOut);
  }
  return actions;
}

/**
 * Finds paragraphs starting with the bare "AI:" or "ACT:" placeholder (no
 * number) and rewrites them as canonical "ACT-N:" using the next available N
 * in the document. Called in syncDocument before _scanFloatingActions so the
 * scanner always sees fully-formed ACT-N:/AI-N: tokens.
 *
 * @param {GoogleAppsScript.Document.Document} doc
 * @returns {{ count: number, newGlobalIds: string[] }}
 */
/**
 * Collects all paragraph elements (including those in table cells, excluding
 * the tracker table) that have a numbered token (ACT-N:/AI-N:) or a bare
 * trigger (AI:/ACT:), for use in _assignPlaceholderTokens.
 *
 * @returns {{ numbered: number[], placeholders: GoogleAppsScript.Document.Paragraph[] }}
 */
function _collectTokenParagraphs(body) {
  var n = body.getNumChildren();
  var numbered     = [];
  var placeholders = [];
  var trackerHeadingSeen  = false;
  var trackerTableSkipped = false;

  function scanPara(para) {
    var raw   = para.getText();
    var text  = _normalizeLineEndings(raw).replace(/\n$/, '');
    var lines = text.split('\n');
    var lineOffset = 0;
    for (var li = 0; li < lines.length; li++) {
      var line = lines[li];
      var m = _ACTION_TOKEN_REGEX_ANCHORED.exec(line);
      var bareTrigger = m ? null : _matchActionTokenBareTrigger(line);
      if (m) {
        numbered.push(parseInt(m[1], 10));
      } else if (bareTrigger) {
        // lineOffset is the character offset into the normalized text.
        // The actual paragraph text may use different byte widths for the
        // line separator; editAsText offsets work on the raw getText() bytes.
        // Recompute offset from raw text using a search from lineOffset onward.
        var rawOffset = raw.indexOf(line, lineOffset);
        if (rawOffset === -1) rawOffset = lineOffset; // fallback
        placeholders.push({ para: para, offset: rawOffset, triggerLen: bareTrigger.match.length });
      }
      lineOffset += lines[li].length + 1; // +1 for the normalized \n
    }
  }

  for (var i = 0; i < n; i++) {
    var child = body.getChild(i);
    var ct    = child.getType();

    if (ct === DocumentApp.ElementType.TABLE) {
      if (trackerHeadingSeen && !trackerTableSkipped) { trackerTableSkipped = true; continue; }
      var table = child.asTable();
      for (var r = 0; r < table.getNumRows(); r++) {
        var row = table.getRow(r);
        for (var c = 0; c < row.getNumCells(); c++) {
          var cell = row.getCell(c);
          for (var p = 0; p < cell.getNumChildren(); p++) {
            var cp  = cell.getChild(p);
            var cpt = cp.getType();
            if (cpt === DocumentApp.ElementType.PARAGRAPH) scanPara(cp.asParagraph());
            else if (cpt === DocumentApp.ElementType.LIST_ITEM) scanPara(cp.asListItem());
          }
        }
      }
      continue;
    }

    if (ct !== DocumentApp.ElementType.PARAGRAPH && ct !== DocumentApp.ElementType.LIST_ITEM) continue;
    if (!trackerHeadingSeen) {
      var txt = child.getText().trim();
      if (txt === _TRACKER_HEADING || txt === _TRACKER_HEADING_OLD) { trackerHeadingSeen = true; continue; }
    }
    scanPara(ct === DocumentApp.ElementType.PARAGRAPH ? child.asParagraph() : child.asListItem());
  }

  return { numbered: numbered, placeholders: placeholders };
}

function _assignPlaceholderTokens(doc) {
  var docId   = doc.getId();
  var body    = doc.getBody();
  var found   = _collectTokenParagraphs(body);

  var maxN = 0;
  for (var i = 0; i < found.numbered.length; i++) maxN = Math.max(maxN, found.numbered[i]);

  var assigned     = 0;
  var newGlobalIds = [];

  // placeholders is [{para, offset}, ...] in left-to-right document order.
  // Assign N values left-to-right so earlier occurrences get lower numbers.
  // Within a paragraph, insert right-to-left to avoid offset drift.
  var pi = 0;
  while (pi < found.placeholders.length) {
    var groupPara  = found.placeholders[pi].para;
    var groupStart = pi;
    while (pi < found.placeholders.length && found.placeholders[pi].para === groupPara) pi++;
    // Assign N values for this group (left-to-right)
    var groupNs = [];
    for (var k = groupStart; k < pi; k++) {
      maxN++;
      groupNs.push(maxN);
      newGlobalIds.push(docId + '/' + _actionTokenId(maxN));
      assigned++;
    }
    // Replace the bare 'AI:'/'ACT:' placeholder right-to-left within the
    // paragraph (to avoid offset drift) with the canonical 'ACT-N:' token —
    // new actions are always written as ACT-N: (ADR-0023 rule 1), regardless
    // of which bare-trigger spelling the user typed.
    for (var k = pi - 1; k >= groupStart; k--) {
      var offset = found.placeholders[k].offset;
      var triggerLen = found.placeholders[k].triggerLen;
      groupPara.editAsText().deleteText(offset, offset + triggerLen - 1);
      groupPara.editAsText().insertText(offset, _actionTokenPrefix(groupNs[k - groupStart]));
    }
  }

  return { count: assigned, newGlobalIds: newGlobalIds };
}

/**
 * Derives a display name from an email address username.
 * Punctuation (. _ -) is treated as a word separator and each word is
 * title-cased.  e.g. "jane.smith@example.com" → "Jane Smith".
 */
function _nameFromEmail(email) {
  var username = email.split('@')[0];
  return username
    .replace(/[._\-]+/g, ' ')
    .replace(/\b\w/g, function(c) { return c.toUpperCase(); });
}

// ---------------------------------------------------------------------------
// ActionSheet proxy — bidirectional sync
// ---------------------------------------------------------------------------

/**
 * POSTs the doc state to the Web App for conflict resolution and sheet writes.
 * Returns { upserted, updated, sheetWins: [{ globalId, action, status, assigneeEmail }] }.
 *
 * @param {Array}  anchorResults  Each element: { globalId, assigneeEmail, assigneeName, actionText, status,
 *                                runs, customFields } (runs/customFields optional — gts-zocq/gts-u0kh).
 * @param {string} docUrl
 * @param {string} docTitle
 * @param {string} docId          Document ID (for orphan detection).
 * @param {Array}  allDocGlobalIds All globalIds currently in the doc.
 * @returns {{upserted: number, updated: number, sheetWins: Array}}
 */
function _syncActionRows(anchorResults, docUrl, docTitle, docId, allDocGlobalIds) {
  var webAppUrl = getWebAppUrl();
  var secret    = PropertiesService.getScriptProperties().getProperty('WEBAPP_SECRET');

  if (!webAppUrl) {
    GasLogger.log('sync.error', { msg: 'WEBAPP_URL not set' });
    return { upserted: 0, updated: 0, sheetWins: [] };
  }

  var docState = [];
  for (var i = 0; i < anchorResults.length; i++) {
    var a = anchorResults[i];
    docState.push({
      globalId:      a.globalId,
      assigneeEmail: a.assigneeEmail,
      assigneeName:  a.assigneeName,
      actionText:    a.actionText,
      status:        a.status,
      // gts-zocq: additive, optional — an older WebApp/client that ignores
      // this field keeps working unmodified (contract-compatible per the
      // bead's own transit-representation decision).
      runs:          a.runs || [],
      // gts-u0kh: additive, optional — same contract-compatible pattern as
      // runs above; {FieldName:{text,runs}} from the ADR-0027 rule 5/5a scanner.
      customFields:  a.customFields || {}
    });
  }

  // Bearer token is required: UrlFetchApp does not carry the caller's Google session
  // automatically. Without it, GAS returns HTTP 401 before doPost runs, regardless of
  // deployment type (/dev always enforces this; /exec with access:ANYONE also requires it).
  // The token satisfies GAS's auth gate only — doPost uses WEBAPP_SECRET for app-level auth.
  var oauthToken = ScriptApp.getOAuthToken();
  var resp = UrlFetchApp.fetch(webAppUrl, {
    method:             'post',
    contentType:        'application/json',
    muteHttpExceptions: true,
    headers:            { 'Authorization': 'Bearer ' + oauthToken },
    payload:            JSON.stringify({
      secret:             secret || '',
      action:             'sync_action_rows',
      clientVersion:      BUILD_INFO.version,
      caller:             _getIdentity(),
      opId:               (GasLogger.getParentOp() || GasLogger.getCurrentOp()),
      docUrl:             docUrl,
      docTitle:           docTitle,
      docId:              docId || '',
      docState:           docState,
      allDocGlobalIds: allDocGlobalIds || [],
      // Explicit "the document was actually scanned" assertion (gts-aiaz).
      // Distinguishes a legitimate empty-document sync (docState=[],
      // allDocGlobalIds=[], scanned=true) from a payload that simply omits
      // both fields — which must NOT be read as "delete everything".
      scanned:            true
    })
  });

  var code = resp.getResponseCode();
  if (code !== 200) {
    GasLogger.log('sync.error', {
      msg:  'sync_action_rows failed: HTTP ' + code,
      body: resp.getContentText().substring(0, 200)
    });
    return { upserted: 0, updated: 0, sheetWins: [] };
  }

  try {
    var parsed = JSON.parse(resp.getContentText());
    _logVersionMismatch(parsed, 'sync');
    return parsed;
  } catch (e) {
    GasLogger.log('sync.warn', { msg: 'Non-JSON sync_action_rows response', body: resp.getContentText().substring(0, 100) });
    return { upserted: 0, updated: 0, sheetWins: [] };
  }
}

/**
 * POSTs mark_doc_not_found to the WebApp so it can stamp 'Doc Not Found' on
 * all Actions rows whose Document formula references any of docIds. One HTTP
 * round trip regardless of how many docs are being marked (gts-kkm7.1)
 * — callers (syncDocument's own-doc not-found paths, syncAll's sweep) collect
 * every not-found docId for this invocation and call this once.
 *
 * @param {string[]} docIds
 */
function _markDocNotFound(docIds) {
  if (!docIds || docIds.length === 0) return;
  var webAppUrl = getWebAppUrl();
  var secret    = PropertiesService.getScriptProperties().getProperty('WEBAPP_SECRET');
  if (!webAppUrl) return;
  var oauthToken = ScriptApp.getOAuthToken();
  UrlFetchApp.fetch(webAppUrl, {
    method:             'post',
    contentType:        'application/json',
    muteHttpExceptions: true,
    headers:            { 'Authorization': 'Bearer ' + oauthToken },
    payload:            JSON.stringify({
      secret:        secret || '',
      action:        'mark_doc_not_found',
      clientVersion: BUILD_INFO.version,
      caller:        _getIdentity(),
      opId:          (GasLogger.getParentOp() || GasLogger.getCurrentOp()),
      docIds:        docIds
    })
  });
  GasLogger.flush();
}

// ---------------------------------------------------------------------------
// Drive REST helpers (gts-rskf)
// ---------------------------------------------------------------------------

/**
 * Drive v3 query parameters that make a request see Shared Drive ("all
 * drives") content as well as My Drive. Omitting these is what caused
 * gts-rskf: every document hosted on a Shared Drive was invisible to
 * files.list, and syncAll read that invisibility as deletion, archiving the
 * document's actions out of the sheet. Every Drive REST call in this file
 * goes through _driveUrl so the flags cannot be forgotten at one call site.
 *
 * `corpora=allDrives` applies to files.list only; it is harmless on
 * files.get/patch, which ignore unknown-but-valid query params, but we keep
 * it list-only for clarity.
 */
var _DRIVE_ITEM_PARAMS = 'supportsAllDrives=true';
var _DRIVE_LIST_PARAMS = 'supportsAllDrives=true&includeItemsFromAllDrives=true&corpora=allDrives';

/**
 * Builds a Drive v3 files endpoint URL with the all-drives flags applied.
 *
 * @param {string} path   '' for the collection (files.list), or '/<fileId>'
 * @param {string} params already-encoded query string, without leading '?'
 * @param {boolean} isList true to add the list-only corpora/include flags
 * @return {string}
 */
function _driveUrl(path, params, isList) {
  return 'https://www.googleapis.com/drive/v3/files' + path +
    '?' + params + '&' + (isList ? _DRIVE_LIST_PARAMS : _DRIVE_ITEM_PARAMS);
}

/** Bounded-retry convention for Drive REST calls, mirroring scn/session.py's
 *  _http_post (3 attempts, short backoff) -- see _fetchDriveWithRetry. */
var _DRIVE_FETCH_MAX_ATTEMPTS   = 3;
var _DRIVE_FETCH_RETRY_DELAY_MS = 1000;

/**
 * Executes a Drive REST UrlFetchApp.fetch call with a bounded retry on
 * transient 5xx responses (gts-pm72). files.list/files.get failing with a
 * one-off HTTP 500 mid-execution is Google-side transient noise, not a code
 * defect (scn/session.py::_http_post already retries the analogous /exec
 * routing flakiness client-side); this is the GAS-side equivalent for the
 * Advanced-Service-adjacent Drive REST calls SyncManager's folder-walk
 * depends on. Only 5xx is retried -- a 4xx (auth/not-found/bad-request) is a
 * real answer, not noise, and must surface on the first attempt.
 *
 * @param {function(): HTTPResponse} fetchFn  zero-arg thunk performing the
 *   UrlFetchApp.fetch call (muteHttpExceptions:true expected, so failures
 *   arrive as response codes, not thrown exceptions).
 * @return {{response: HTTPResponse, code: number, attempts: number}}
 *   code is the response code the retry loop decided on (see
 *   _driveFetchTestOverrideCode -- overridden only under test fixture
 *   fault-injection, real otherwise); attempts is how many calls were made.
 */
function _fetchDriveWithRetry(fetchFn) {
  var resp, code;
  for (var attempt = 1; attempt <= _DRIVE_FETCH_MAX_ATTEMPTS; attempt++) {
    resp = fetchFn();
    code = _driveFetchTestOverrideCode(resp.getResponseCode());
    if (code < 500 || attempt === _DRIVE_FETCH_MAX_ATTEMPTS) {
      return { response: resp, code: code, attempts: attempt };
    }
    GasLogger.log('sync.driveFetch.retry', { attempt: attempt, status: code });
    Utilities.sleep(_DRIVE_FETCH_RETRY_DELAY_MS);
  }
  return { response: resp, code: code, attempts: _DRIVE_FETCH_MAX_ATTEMPTS };
}

/**
 * Test-only fault injection hook for _fetchDriveWithRetry (gts-pm72 Backstop
 * proof) -- never trips outside the test harness. TestFixtures.js's
 * 'sync_all_force_drive_5xx_recovery' fixture monkey-patches UrlFetchApp.fetch
 * itself to simulate the transient-500 symptom without touching real Drive;
 * this override exists only so a test can also exercise the "already-500
 * response, does the retry loop's own bookkeeping treat it as retryable"
 * path directly. No-op (returns realCode unchanged) unless a test has set
 * the counter via PropertiesService.
 *
 * @param {number} realCode
 * @return {number}
 */
function _driveFetchTestOverrideCode(realCode) {
  var props = PropertiesService.getScriptProperties();
  var raw   = props.getProperty('_TEST_FORCE_DRIVE_5XX_COUNT');
  if (!raw) return realCode;
  var remaining = parseInt(raw, 10);
  if (!remaining || remaining <= 0) return realCode;
  props.setProperty('_TEST_FORCE_DRIVE_5XX_COUNT', String(remaining - 1));
  return 500;
}

/**
 * True when `id` looks like a real Drive resource id rather than a TeamData
 * placeholder such as '-NA-' (meaning "no dedicated folder for this team" --
 * gts-moy1.2). Real Drive ids are opaque alphanumeric-plus-`_-` tokens with
 * no fixed length Google guarantees, but every real id observed in this
 * account is well over the length of any placeholder in use, so a short
 * minimum length plus a charset check is a cheap, low-risk filter -- it
 * exists only to keep one malformed TeamData row from making Drive reject
 * the entire combined `in parents` query with a 404, not to fully validate
 * the id round-trips to a real file (Drive itself is the source of truth for
 * that; an id that passes this check but doesn't exist just yields zero
 * results for its clause, same as today).
 *
 * @param {string} id
 * @return {boolean}
 */
function _isPlausibleDriveId(id) {
  if (!id) return false;
  var trimmed = String(id).trim();
  if (trimmed.length < 10) return false;
  return /^[a-zA-Z0-9_-]+$/.test(trimmed);
}

/**
 * Fetches trashed/modifiedTime/name metadata for tracked Google Docs, in a
 * single (paginated) Drive REST call, replacing one DriveApp.getFileById()
 * call per tracked doc in syncAll()'s loop (gts-kkm7.2). Throws on any
 * non-200 page (after exhausting the bounded retry — gts-pm72) so callers can
 * fall back to the per-doc path rather than silently treating every doc as
 * not-found.
 *
 * When folderIds is non-empty, the listing is scoped to Docs that are DIRECT
 * children of one of those folders (gts-uuse) instead of every Google Doc
 * visible to the calling identity account-wide — confirmed live at 5448
 * files/12 pages for a 171-doc tracked corpus before this change, completely
 * independent of how many docs the Actions sheet actually tracks. Scoping
 * does not recurse into subfolders: a tracked doc nested deeper than one
 * level under a team folder, or living outside every configured team folder,
 * is simply absent from the returned map. That is intentional — callers
 * already treat "absent from the batch listing" as inconclusive rather than
 * proof of deletion (gts-rskf) and resolve it with an authoritative per-doc
 * lookup, so under-scoping degrades to a slower-but-still-correct path
 * instead of misclassifying a live doc as gone. When folderIds is empty (no
 * TeamData folders configured), the listing is unscoped, matching the
 * original pre-gts-uuse behavior.
 *
 * Also carries each file's immediate parent folder id (parentId) at zero
 * extra Drive calls -- gts-b6dm's syncAll team-reconciliation pass uses it as
 * an O(1) fast path (immediate parent is directly a TeamData folder) before
 * falling back to a per-doc _walkFolderForTeam call for docs nested deeper
 * under a team folder.
 *
 * @param {Array<string>=} folderIds  TeamData folder ids to scope the listing
 *   to (direct children only). Omit or pass an empty array for the original
 *   unscoped, account-wide listing. Entries that don't look like a real Drive
 *   resource id (gts-moy1.2 -- e.g. a '-NA-' placeholder meaning "no team
 *   folder") are silently dropped rather than poisoning the combined query:
 *   a single bad id previously made Drive reject the WHOLE `in parents` OR
 *   clause with a 404, which threw and knocked out both the scoped listing
 *   AND its own fallback safety net for every tracked doc account-wide.
 * @return {Object<string, {trashed: boolean, lastModified: Date, name: string, parentId: ?string}>}
 *   map of docId -> metadata, covering every Google Doc the listing returns.
 */
function _fetchDriveDocMetadata(folderIds) {
  var token      = ScriptApp.getOAuthToken();
  var fields     = 'nextPageToken,files(id,trashed,modifiedTime,name,parents)';
  var qParts     = ["mimeType='application/vnd.google-apps.document'"];
  if (folderIds && folderIds.length > 0) {
    var validFolderIds = [];
    var rejectedFolderIds = [];
    for (var v = 0; v < folderIds.length; v++) {
      if (_isPlausibleDriveId(folderIds[v])) {
        validFolderIds.push(folderIds[v]);
      } else {
        rejectedFolderIds.push(folderIds[v]);
      }
    }
    if (rejectedFolderIds.length > 0) {
      GasLogger.log('sync.driveMetadata.folderIdRejected', {
        rejected: rejectedFolderIds,
        msg: 'TeamData folder id is not a plausible Drive resource id; excluded from scoped listing query'
      });
    }
    var folderClauses = [];
    for (var f = 0; f < validFolderIds.length; f++) {
      folderClauses.push("'" + validFolderIds[f].replace(/'/g, "\\'") + "' in parents");
    }
    if (folderClauses.length > 0) {
      qParts.push('(' + folderClauses.join(' or ') + ')');
    }
  }
  var q          = qParts.join(' and ');
  var map        = {};
  var pageToken  = null;
  var pages      = 0;

  do {
    var url = _driveUrl('', 'q=' + encodeURIComponent(q) +
      '&fields=' + encodeURIComponent(fields) +
      '&pageSize=1000' +
      (pageToken ? '&pageToken=' + encodeURIComponent(pageToken) : ''), true);
    var result = _fetchDriveWithRetry(function () {
      return UrlFetchApp.fetch(url, {
        headers:            { Authorization: 'Bearer ' + token },
        muteHttpExceptions: true
      });
    });
    if (result.code !== 200) {
      throw new Error('files.list failed: HTTP ' + result.code +
        (result.attempts > 1 ? ' (after ' + result.attempts + ' attempts)' : ''));
    }
    var body  = JSON.parse(result.response.getContentText());
    var files = body.files || [];
    for (var i = 0; i < files.length; i++) {
      map[files[i].id] = {
        trashed:      !!files[i].trashed,
        lastModified: new Date(files[i].modifiedTime),
        name:         files[i].name,
        parentId:     (files[i].parents && files[i].parents[0]) || null
      };
    }
    pageToken = body.nextPageToken || null;
    pages++;
  } while (pageToken);

  GasLogger.log('sync.driveMetadata.fetched', {
    count: Object.keys(map).length, pages: pages, scoped: !!(folderIds && folderIds.length)
  });
  return map;
}

/**
 * Batched per-doc fallback lookup (gts-uuse) for tracked docs absent from
 * _fetchDriveDocMetadata's scoped listing — groups multiple files.get calls
 * into one HTTP round trip via Drive API's batch endpoint
 * (https://www.googleapis.com/batch/drive/v3), instead of firing
 * _fetchSingleDocMetadata once per doc in a loop. syncAll only calls this
 * when more than one doc needs the fallback in the same sweep; a single miss
 * goes straight to _fetchSingleDocMetadata.
 *
 * Falls back to sequential _fetchSingleDocMetadata calls if the batch request
 * itself fails, times out, or its response can't be parsed into exactly one
 * part per requested doc -- a malformed or short batch response must never
 * silently leave a doc unresolved (same "never assume, always confirm"
 * principle as gts-rskf).
 *
 * @param {Array<string>} docIds  tracked docs absent from the scoped listing.
 * @return {Object<string, {status: string, meta: ?Object, err: string}>}
 *   docId -> the same three-state contract as _fetchSingleDocMetadata.
 */
function _fetchDriveDocMetadataBatch(docIds) {
  if (!docIds || docIds.length === 0) return {};

  function sequentialFallback() {
    var seq = {};
    for (var s = 0; s < docIds.length; s++) {
      seq[docIds[s]] = _fetchSingleDocMetadata(docIds[s]);
    }
    return seq;
  }

  var boundary = 'gactionsheet_' + Utilities.getUuid();
  var token    = ScriptApp.getOAuthToken();
  var fields   = encodeURIComponent('id,trashed,modifiedTime,name');
  var partsArr = [];
  for (var i = 0; i < docIds.length; i++) {
    partsArr.push(
      '--' + boundary + '\r\n' +
      'Content-Type: application/http\r\n' +
      'Content-ID: <item' + i + '>\r\n\r\n' +
      'GET /drive/v3/files/' + docIds[i] + '?fields=' + fields + ' HTTP/1.1\r\n\r\n'
    );
  }
  partsArr.push('--' + boundary + '--');
  var body = partsArr.join('');

  try {
    var result = _fetchDriveWithRetry(function () {
      return UrlFetchApp.fetch('https://www.googleapis.com/batch/drive/v3', {
        method:             'post',
        contentType:        'multipart/mixed; boundary=' + boundary,
        headers:            { Authorization: 'Bearer ' + token },
        payload:            body,
        muteHttpExceptions: true
      });
    });
    if (result.code !== 200) {
      throw new Error('batch/drive/v3 failed: HTTP ' + result.code +
        (result.attempts > 1 ? ' (after ' + result.attempts + ' attempts)' : ''));
    }

    var headers       = result.response.getHeaders();
    var contentType   = headers['Content-Type'] || headers['content-type'] || '';
    var boundaryMatch = /boundary=(?:"([^"]+)"|([^;]+))/.exec(contentType);
    var respBoundary  = boundaryMatch ? (boundaryMatch[1] || boundaryMatch[2]).trim() : null;
    if (!respBoundary) {
      throw new Error('batch/drive/v3: no boundary in response Content-Type: ' + contentType);
    }

    // Each requested doc gets exactly one part back, in the SAME order the
    // requests were sent (Drive's batch endpoint preserves request order) --
    // relied on here rather than parsing the echoed Content-ID, which carries
    // a "response-" prefix that isn't documented as a stable contract.
    var rawParts = result.response.getContentText().split('--' + respBoundary);
    var results  = {};
    var docIndex = 0;
    for (var p = 0; p < rawParts.length && docIndex < docIds.length; p++) {
      var part = rawParts[p];
      var statusMatch = /HTTP\/1\.\d\s+(\d+)/.exec(part);
      if (!statusMatch) continue; // preamble/epilogue/boundary-only segment

      var docId      = docIds[docIndex++];
      var httpStatus = parseInt(statusMatch[1], 10);
      if (httpStatus === 404) {
        results[docId] = { status: 'gone', meta: null, err: 'HTTP 404' };
        continue;
      }
      if (httpStatus !== 200) {
        results[docId] = { status: 'unknown', meta: null, err: 'HTTP ' + httpStatus };
        continue;
      }
      var jsonMatch = /\{[\s\S]*\}/.exec(part);
      if (!jsonMatch) {
        results[docId] = { status: 'unknown', meta: null, err: 'batch response part had no JSON body' };
        continue;
      }
      var file = JSON.parse(jsonMatch[0]);
      results[docId] = {
        status: 'found',
        meta: {
          trashed:      !!file.trashed,
          lastModified: new Date(file.modifiedTime),
          name:         file.name
        },
        err: ''
      };
    }
    if (docIndex < docIds.length) {
      throw new Error('batch/drive/v3: expected ' + docIds.length + ' response parts, parsed ' + docIndex);
    }

    GasLogger.log('sync.driveMetadata.batchFallback.fetched', { count: docIds.length });
    return results;
  } catch (batchErr) {
    // Batch request or parse failed -- degrade to the slower-but-correct
    // sequential per-doc path rather than leaving any doc unresolved.
    GasLogger.log('sync.driveMetadata.batchFallback.error', { msg: batchErr.message, count: docIds.length });
    return sequentialFallback();
  }
}

// ---------------------------------------------------------------------------
// Team Scope: Drive appProperty read/write and folder-walk auto-assignment
// (gts-me6w.3 — see knowledge-base/staging/epic-b-team-property-sync.md)
// ---------------------------------------------------------------------------

/**
 * Authoritative single-document reachability check (gts-rskf), used to
 * confirm or refute a document's absence from _fetchDriveDocMetadata's bulk
 * listing before syncAll marks it Doc Not Found.
 *
 * Deliberately distinguishes three outcomes, because only one of them may
 * ever cost a user their rows:
 *   'found'   — metadata in the same shape as _fetchDriveDocMetadata's entries
 *   'gone'    — Drive positively reports the file does not exist (404)
 *   'unknown' — any other failure; the caller must NOT mark the doc not-found
 *
 * @param {string} docId
 * @return {{status: string, meta: ?Object, err: string}}
 */
function _fetchSingleDocMetadata(docId) {
  var url = _driveUrl('/' + docId, 'fields=' + encodeURIComponent('id,trashed,modifiedTime,name'), false);
  try {
    // Bounded retry (gts-pm72) so a transient 500 on this per-doc fallback
    // doesn't need a second, slower syncAll sweep just to resolve a doc a
    // fresh call would have confirmed live in under a second.
    var result = _fetchDriveWithRetry(function () {
      return UrlFetchApp.fetch(url, {
        method:             'get',
        headers:            { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
        muteHttpExceptions: true
      });
    });
    var resp = result.response;
    var code = result.code;
    if (code === 404) {
      return { status: 'gone', meta: null, err: 'HTTP 404' };
    }
    if (code !== 200) {
      return { status: 'unknown', meta: null, err: 'HTTP ' + code + ' (after ' + result.attempts + ' attempts)' };
    }
    var file = JSON.parse(resp.getContentText());
    return {
      status: 'found',
      meta: {
        trashed:      !!file.trashed,
        lastModified: new Date(file.modifiedTime),
        name:         file.name
      },
      err: ''
    };
  } catch (e) {
    return { status: 'unknown', meta: null, err: e.message };
  }
}

/**
 * Reads a Drive file appProperty via the Drive REST API. Works in any
 * execution context (unlike PropertiesService.getDocumentProperties(), which
 * is only valid when the script is bound to the active document).
 *
 * @param {string} docId
 * @param {string} key
 * @param {string} token  OAuth token from ScriptApp.getOAuthToken()
 * @return {?string} the property value, or null if absent or on API error.
 */
function _getDocAppProperty(docId, key, token) {
  var url = _driveUrl('/' + docId, 'fields=appProperties', false);
  try {
    var resp = UrlFetchApp.fetch(url, {
      method:             'get',
      headers:            { 'Authorization': 'Bearer ' + token },
      muteHttpExceptions: true
    });
    if (resp.getResponseCode() !== 200) {
      GasLogger.log('sync.teamScope.property.read.error', { docId: docId, key: key, status: resp.getResponseCode() });
      return null;
    }
    var props = JSON.parse(resp.getContentText()).appProperties || {};
    return Object.prototype.hasOwnProperty.call(props, key) ? props[key] : null;
  } catch (e) {
    GasLogger.log('sync.teamScope.property.read.error', { docId: docId, key: key, msg: e.message });
    return null;
  }
}

/**
 * Writes a Drive file appProperty via the Drive REST API. Logs a warning and
 * returns without throwing on failure — callers treat this as best-effort.
 *
 * @param {string} docId
 * @param {string} key
 * @param {string} value
 * @param {string} token  OAuth token from ScriptApp.getOAuthToken()
 */
function _setDocAppProperty(docId, key, value, token) {
  var url     = _driveUrl('/' + docId, 'fields=appProperties', false);
  var payload = { appProperties: {} };
  payload.appProperties[key] = value;
  try {
    var resp = UrlFetchApp.fetch(url, {
      method:             'patch',
      contentType:        'application/json',
      headers:            { 'Authorization': 'Bearer ' + token },
      payload:            JSON.stringify(payload),
      muteHttpExceptions: true
    });
    if (resp.getResponseCode() !== 200) {
      GasLogger.log('sync.teamScope.property.write.error', { docId: docId, key: key, status: resp.getResponseCode() });
    }
  } catch (e) {
    GasLogger.log('sync.teamScope.property.write.error', { docId: docId, key: key, msg: e.message });
  }
}

/**
 * Reads all TeamData rows from the 'TeamData' tab.
 *
 * @param {Spreadsheet} ss
 * @return {Array<{teamId: string, folderId: string, contact: string, teamLink: string}>}
 *   Empty array if the tab is missing or has no data rows. Blank rows
 *   (both Team Id and Folder Id empty) are skipped.
 */
function _readTeamDataRows(ss) {
  var sheet = ss.getSheetByName('TeamData');
  if (!sheet) return [];
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  var cols    = CONTRACT_SCHEMA.sheetTeamData.columnsByField;
  var numCols = CONTRACT_SCHEMA.sheetTeamData.headers.length;
  var values  = sheet.getRange(2, 1, lastRow - 1, numCols).getValues();
  var rows    = [];
  for (var i = 0; i < values.length; i++) {
    var teamId   = values[i][cols.team_id - 1];
    var folderId = values[i][cols.folder_id - 1];
    if (!teamId && !folderId) continue;
    rows.push({ teamId: teamId, folderId: folderId, contact: values[i][cols.contact - 1], teamLink: values[i][cols.team_link - 1] || '' });
  }
  return rows;
}

/**
 * Walks the Drive folder ancestry of docId, looking for the nearest ancestor
 * folder (starting at the doc's immediate parent) whose ID matches a
 * TeamData row's Folder Id.
 *
 * A TeamData folderId is not guaranteed 1:1 with teamId -- one folder may
 * legitimately be listed under more than one team (e.g. a shared folder).
 * This walk returns the FIRST matching teamDataRows entry, same as before
 * caching was added; it does not attempt to resolve or report multi-team
 * folder ownership (DocData.teamId is a scalar field).
 *
 * folderTeamCache, if passed, memoizes folderId -> resolved-team-or-null for
 * the lifetime of the caller's run (e.g. one syncAll sweep) so documents that
 * share common ancestor folders don't repeat the same Drive folder.getParents()
 * calls. Every folder visited on the way to a cache hit (or to a fresh
 * resolution) is back-filled with that resolution before returning, so a
 * later doc under a deeper shared folder still gets a single-hop cache hit.
 *
 * (A further optimization -- enumerating every folder under each TeamData
 * folder up front and building one reverse folderId->teamId map, so per-doc
 * resolution is an O(1) lookup against the doc's immediate parent with zero
 * incremental Drive calls -- was considered but not implemented; revisit if
 * per-doc parent walks become a measured bottleneck at scale.)
 *
 * @param {string} docId
 * @param {Array<{teamId: string, folderId: string, teamLink: string}>} teamDataRows
 * @param {?Object.<string, (?{teamId: string, teamLink: string, folderId: string})>} folderTeamCache
 *   optional folderId -> result memo, shared across calls within one run.
 * @return {(?{teamId: string, teamLink: string, folderId: string}|false)} the
 *   matched team (folderId is the specific TeamData folder the doc actually
 *   sits under -- used by gts-79dw.4.12's _authorizeDocWrite for per-document
 *   write re-authorization, R3b); null if the walk completed and confirmed no
 *   ancestor matches; false if the walk could not complete (Drive error) --
 *   callers must NOT treat false the same as null, since false is not proof
 *   of "no team" and should never overwrite existing data.
 */
function _walkFolderForTeam(docId, teamDataRows, folderTeamCache) {
  var visitedFolderIds = [];
  function memoize(result) {
    if (folderTeamCache) {
      for (var v = 0; v < visitedFolderIds.length; v++) {
        folderTeamCache[visitedFolderIds[v]] = result;
      }
    }
    return result;
  }
  try {
    var parents = withGasRetry('SyncManager._walkFolderForTeam:DriveApp.getFileById',
      function () { return DriveApp.getFileById(docId).getParents(); });
    if (!parents.hasNext()) {
      GasLogger.log('sync.teamScope.walk.no-match', { docId: docId });
      return null;
    }
    var folder = parents.next();
    if (parents.hasNext()) {
      GasLogger.log('sync.teamScope.walk.multi-parent', { docId: docId });
    }

    while (folder) {
      var folderId = folder.getId();
      if (folderTeamCache && Object.prototype.hasOwnProperty.call(folderTeamCache, folderId)) {
        return memoize(folderTeamCache[folderId]);
      }
      visitedFolderIds.push(folderId);
      for (var i = 0; i < teamDataRows.length; i++) {
        if (teamDataRows[i].folderId === folderId) {
          return memoize({ teamId: teamDataRows[i].teamId, teamLink: teamDataRows[i].teamLink || '', folderId: folderId });
        }
      }
      var folderParents = folder.getParents();
      if (!folderParents.hasNext()) break;
      folder = folderParents.next();
      if (folderParents.hasNext()) {
        GasLogger.log('sync.teamScope.walk.multi-parent', { docId: docId });
      }
    }

    GasLogger.log('sync.teamScope.walk.no-match', { docId: docId });
    return memoize(null);
  } catch (e) {
    GasLogger.log('sync.teamScope.walk.error', { docId: docId, msg: e.message });
    // Do not memoize -- a transient error is not a confirmed "no team" result
    // for this folder chain, and must not poison the cache for other docs.
    return false;
  }
}

// ---------------------------------------------------------------------------
// Team Scope: security gate
// (gts-me6w.5 — see knowledge-base/staging/epic-b-team-property-sync.md)
// ---------------------------------------------------------------------------

/**
 * Verifies that the active user can access the given team's folder. Standalone
 * gate — not called from syncDocument(); intended for future team-scoped
 * filtered reads (Import/Notify, EPIC-D/E).
 *
 * A team can own more than one TeamData row (multiple folders, ADR-0014 §1).
 * Grants access if the caller can reach ANY of teamId's matching folders —
 * fixed by gts-79dw.4.11; previously this broke at the FIRST matching row, so
 * a multi-folder team was authorized against an arbitrary single folder
 * instead of considering all of them (plan §11 audit finding). Only denies
 * once every matching folder has been tried and failed.
 *
 * Throws rather than returning a boolean: callers catch the error message
 * prefix ('TeamNotFound: ' or 'TeamAccessDenied: ') and respond with no rows
 * plus a surfaced error — never partial/leaked data.
 *
 * @param {string} teamId
 * @param {Spreadsheet} ss
 * @throws {Error} 'TeamNotFound: <teamId>' if no TeamData row matches teamId.
 * @throws {Error} 'TeamAccessDenied: <teamId>' if the active user cannot
 *   access ANY of the team's folders (DriveApp.getFolderById throws for all
 *   of them).
 */
function assertTeamAccess(teamId, ss) {
  var teamDataRows = _readTeamDataRows(ss);
  var matches = [];
  for (var i = 0; i < teamDataRows.length; i++) {
    if (teamDataRows[i].teamId === teamId) {
      matches.push(teamDataRows[i]);
    }
  }
  if (!matches.length) {
    throw new Error('TeamNotFound: ' + teamId);
  }
  for (var m = 0; m < matches.length; m++) {
    try {
      withGasRetry('SyncManager.assertTeamAccess:DriveApp.getFolderById',
        function () { return DriveApp.getFolderById(matches[m].folderId); });
      return; // reachable via this folder -- grant
    } catch (e) {
      // try the next folder before giving up
    }
  }
  throw new Error('TeamAccessDenied: ' + teamId);
}

// ---------------------------------------------------------------------------
// Team Scope: DocData sync (DocWins + UpdateDoc write-back)
// (gts-me6w.4 — see knowledge-base/staging/epic-b-team-property-sync.md)
// ---------------------------------------------------------------------------

/**
 * DocData field contract (gts-rename, was Doc Modified/Doc Updated):
 *
 * - lastSyncTime: timestamp of the last time a FULL document sync ran for
 *   this doc (_syncTeamScope, below). Set unconditionally on every full sync
 *   — NOT Drive's true last-modified time (that value is read transiently in
 *   syncAll's skip-check and never persisted). Preserved as-is by any caller
 *   that upserts this row without running a full sync (e.g. the integrity
 *   pass, WebApp's sync_action_rows handler).
 * - docUpdated: timestamp of the last write to THIS ROW, for any reason —
 *   full sync, count-only reconciliation, or Doc Not Found marking. Set
 *   unconditionally by _getOrUpsertDocDataRow on every call. ArchiveManager
 *   relies on this freezing once a row is marked Doc Not Found (no other
 *   upsert path touches such a row) to drive the 24h eviction timer.
 *
 * The two diverge only when action counts are reconciled (sheet-side edit)
 * without the doc itself changing: docUpdated bumps, lastSyncTime does not.
 */

/**
 * Reads the single DocData row whose FileId matches docId. Read-only.
 *
 * @param {Spreadsheet} ss
 * @param {string} docId
 * @return {?{fileId: string, docName: string, lastSyncTime: Date, docUpdated: Date,
 *   syncStatus: string, teamId: string, actionCount: number, resolvedCount: number}}
 *   the matching row, or null if the DocData tab is missing or has no match.
 */
function _readDocDataRow(ss, docId) {
  var sheet = ss.getSheetByName('DocData');
  if (!sheet) return null;
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return null;
  var cols   = CONTRACT_SCHEMA.sheetDocData.columnsByField;
  var values = sheet.getRange(2, 1, lastRow - 1, CONTRACT_SCHEMA.sheetDocData.headers.length).getValues();
  for (var i = 0; i < values.length; i++) {
    var row = values[i];
    if (row[cols.file_id - 1] === docId) {
      return {
        fileId:        row[cols.file_id - 1],
        docName:       row[cols.doc_name - 1],
        lastSyncTime:  row[cols.last_sync_time - 1],
        docUpdated:    row[cols.doc_updated - 1],
        syncStatus:    row[cols.sync_status - 1],
        teamId:        row[cols.team_id - 1],
        actionCount:   row[cols.action_count - 1],
        resolvedCount: row[cols.resolved_count - 1]
      };
    }
  }
  return null;
}

/**
 * Reads all DocData rows. Read-only. Used to build a fileId -> row lookup map
 * (e.g. for Import's per-action Team Id join, gts-eore) without calling
 * _readDocDataRow once per ActionSheet row.
 *
 * @param {Spreadsheet} ss
 * @return {Array<{fileId: string, docName: string, lastSyncTime: Date, docUpdated: Date,
 *   syncStatus: string, teamId: string, actionCount: number, resolvedCount: number}>}
 *   Empty array if the DocData tab is missing or has no data rows. Rows with
 *   no FileId are skipped.
 */
function _readDocDataRows(ss) {
  var sheet = ss.getSheetByName('DocData');
  if (!sheet) return [];
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  var cols   = CONTRACT_SCHEMA.sheetDocData.columnsByField;
  var values = sheet.getRange(2, 1, lastRow - 1, CONTRACT_SCHEMA.sheetDocData.headers.length).getValues();
  var rows   = [];
  for (var i = 0; i < values.length; i++) {
    var row = values[i];
    if (!row[cols.file_id - 1]) continue;
    rows.push({
      fileId:        row[cols.file_id - 1],
      docName:       row[cols.doc_name - 1],
      lastSyncTime:  row[cols.last_sync_time - 1],
      docUpdated:    row[cols.doc_updated - 1],
      syncStatus:    row[cols.sync_status - 1],
      teamId:        row[cols.team_id - 1],
      actionCount:   row[cols.action_count - 1],
      resolvedCount: row[cols.resolved_count - 1]
    });
  }
  return rows;
}

/**
 * Finds the DocData row matching fileId and overwrites it with the given
 * values, or appends a new row if none exists. doc_updated is always set to
 * the current time.
 *
 * @param {Spreadsheet} ss
 * @param {string} fileId
 * @param {string} docName
 * @param {Date} lastSyncTime
 * @param {string} teamId
 * @param {string} syncStatus
 * @param {number} actionCount
 * @param {number} resolvedCount
 * @return {?Object} the row data as written, or null if the DocData tab is missing.
 */
function _getOrUpsertDocDataRow(ss, fileId, docName, lastSyncTime, teamId, syncStatus, actionCount, resolvedCount) {
  var sheet = ss.getSheetByName('DocData');
  if (!sheet) return null;
  var cols       = CONTRACT_SCHEMA.sheetDocData.columnsByField;
  var numCols    = CONTRACT_SCHEMA.sheetDocData.headers.length;
  var docUpdated = new Date();

  // Doc Name is a HYPERLINK formula, not a plain string, so clicking it opens
  // the document (gts-46qv) -- same pattern as the Actions sheet's
  // document_formula column. fileId is the Drive doc ID already required by
  // every caller, so the edit URL needs no extra plumbing. Read side is
  // unaffected: getValues() returns a HYPERLINK formula's computed display
  // text (the title), identical to today's plain-string read.
  var docNameFormula = '=HYPERLINK("https://docs.google.com/document/d/' + fileId +
    '/edit","' + _escapeQuotes(docName) + '")';

  var rowValues = [];
  rowValues[cols.file_id - 1]        = fileId;
  rowValues[cols.doc_name - 1]       = docNameFormula;
  rowValues[cols.last_sync_time - 1]   = lastSyncTime;
  rowValues[cols.doc_updated - 1]    = docUpdated;
  rowValues[cols.sync_status - 1]    = syncStatus;
  rowValues[cols.team_id - 1]        = teamId;
  rowValues[cols.action_count - 1]   = actionCount;
  rowValues[cols.resolved_count - 1] = resolvedCount;

  var lastRow   = sheet.getLastRow();
  var targetRow = -1;
  if (lastRow >= 2) {
    var ids = sheet.getRange(2, cols.file_id, lastRow - 1, 1).getValues();
    for (var i = 0; i < ids.length; i++) {
      if (ids[i][0] === fileId) {
        targetRow = i + 2;
        break;
      }
    }
  }
  if (targetRow === -1) targetRow = lastRow + 1;

  sheet.getRange(targetRow, 1, 1, numCols).setValues([rowValues]);

  return {
    fileId: fileId, docName: docName, lastSyncTime: lastSyncTime, docUpdated: docUpdated,
    syncStatus: syncStatus, teamId: teamId, actionCount: actionCount, resolvedCount: resolvedCount
  };
}

/**
 * Orchestrates Team Scope resolution for a single document and mirrors the
 * result to DocData:
 *
 * - If DocData.SyncStatus == 'UpdateDoc': DocData.Team Id wins. The doc's
 *   teamScope appProperty is overwritten and SyncStatus is cleared.
 * - Else if the doc has no teamScope yet: folder-walk auto-assignment
 *   (sticky — only runs once per document).
 * - Else: teamScope is left unchanged (sticky).
 *
 * In all cases, DocData is upserted with the resulting Team Id. Action/
 * resolved counts and Doc Name are left for the WebApp's sync_action_rows
 * handler to populate — this is a first-pass write so DocData always has a
 * row for the document, even if the doc has no floating actions.
 *
 * @param {Spreadsheet} ss
 * @param {string} docId
 * @param {string} token  OAuth token from ScriptApp.getOAuthToken()
 * @param {string} docName  Current document title (doc.getName()), persisted to
 *   DocData.doc_name on every sync so the row is populated even before the
 *   document has any floating actions.
 */
function _syncTeamScope(ss, docId, token, docName) {
  var docDataRow = _readDocDataRow(ss, docId);
  var newSyncStatus = docDataRow ? docDataRow.syncStatus : '';

  // Self-heal a stale 'Doc Not Found' (gts-rskf). Reaching here means
  // syncDocument already opened and read this document, so a not-found mark
  // left by an earlier sweep is false by construction. Without this the mark
  // is one-way: syncAll skips every doc already marked 'Doc Not Found'
  // (alreadyDocNotFound), so a document wrongly marked can never recover on
  // its own, and its rows are archived 24h later.
  if (newSyncStatus === 'Doc Not Found') {
    GasLogger.log('sync.docNotFound.cleared', {
      docId: docId, msg: 'Document opened successfully; clearing stale not-found mark'
    });
    newSyncStatus = '';
  }

  // DocData.teamId mirrors the Drive teamScope appProperty -- both are written
  // together, only by this function (the .overridden/.resolved branches below),
  // so in the steady state (no override pending, already resolved) they're
  // provably identical. Trusting the mirror skips a Drive REST round trip on
  // every sync of an already-resolved doc -- the common case, ~2-4s saved per
  // sync (gts-j8cn perf pass). The narrow risk this introduces (a crashed
  // execution leaving Drive and DocData out of sync) is no longer self-healed
  // here on the next sync as it was before; verify_consistency(scope=DOC) is
  // the deliberate place to catch that drift instead, not paid on every sync.
  var teamScope = (docDataRow && newSyncStatus !== 'UpdateDoc' && docDataRow.teamId)
    ? docDataRow.teamId
    : _getDocAppProperty(docId, 'teamScope', token);

  if (docDataRow && docDataRow.syncStatus === 'UpdateDoc') {
    teamScope = docDataRow.teamId || '';
    _setDocAppProperty(docId, 'teamScope', teamScope, token);
    if (teamScope) {
      var allTeamRows = _readTeamDataRows(ss);
      var matchedRow  = null;
      for (var j = 0; j < allTeamRows.length; j++) {
        if (allTeamRows[j].teamId === teamScope) { matchedRow = allTeamRows[j]; break; }
      }
      _setDocAppProperty(docId, 'teamLink', (matchedRow && matchedRow.teamLink) || '', token);
      GasLogger.log('sync.teamScope.overridden', { docId: docId, teamId: teamScope });
    } else {
      _setDocAppProperty(docId, 'teamLink', '', token);
      GasLogger.log('sync.teamScope.override-blank', { docId: docId });
    }
    newSyncStatus = '';
  } else if (!teamScope) {
    var teamDataRows = _readTeamDataRows(ss);
    var walkResult   = _walkFolderForTeam(docId, teamDataRows);
    if (walkResult) {
      teamScope = walkResult.teamId;
      _setDocAppProperty(docId, 'teamScope', teamScope, token);
      _setDocAppProperty(docId, 'teamLink', walkResult.teamLink || '', token);
      GasLogger.log('sync.teamScope.resolved', { docId: docId, teamId: teamScope });
    }
  }

  var existingActionCount   = docDataRow ? docDataRow.actionCount   : 0;
  var existingResolvedCount = docDataRow ? docDataRow.resolvedCount : 0;
  _getOrUpsertDocDataRow(ss, docId, docName || '', new Date(), teamScope || '', newSyncStatus, existingActionCount, existingResolvedCount);
}

/**
 * Re-marks an Actions sheet row as 'Dirty' so the next sync retries the
 * flush to doc.  Called when _flushActionParagraph returns false.
 * Searches column 1 (globalId) for the matching row.
 *
 * @param {string} globalId
 */
function _remarkRowDirty(globalId) {
  try {
    var ss    = _openActionSheetSpreadsheet();
    var sheet = ss.getSheetByName('Actions');
    if (!sheet) return;
    var lastRow = sheet.getLastRow();
    if (lastRow < 2) return;
    var ids = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
    for (var i = 0; i < ids.length; i++) {
      if (ids[i][0] === globalId) {
        sheet.getRange(i + 2, _SCOL.sync_status).setValue('Dirty');
        GasLogger.log('flush.remarked-dirty', { globalId: globalId, row: i + 2 });
        return;
      }
    }
    GasLogger.log('flush.remark-dirty.no-match', { globalId: globalId, lastRow: lastRow, sampleIds: ids.slice(0, 3).map(function (r) { return r[0]; }) });
  } catch (e) {
    GasLogger.log('flush.remark-dirty.error', { globalId: globalId, msg: e.message });
  }
}

// ---------------------------------------------------------------------------
// SyncState sheet — per-doc last-synced-at tracking
// ---------------------------------------------------------------------------

/**
 * Returns the SyncState sheet, creating it with a header row if absent.
 * Columns: Doc ID | Last Synced At | Doc Title
 */
function _getOrCreateSyncStateSheet(ss) {
  var sheet = ss.getSheetByName('SyncState');
  if (!sheet) {
    sheet = ss.insertSheet('SyncState');
    sheet.getRange(1, 1, 1, 3).setValues([['Doc ID', 'Last Synced At', 'Doc Title']]);
    sheet.setFrozenRows(1);
  }
  return sheet;
}

/**
 * Reads the SyncState sheet into a map: { docId: { syncedAt: Date, row: number } }.
 * row is the 1-based sheet row so _updateSyncState can write in place.
 */
function _loadSyncState(syncStateSheet) {
  var state   = {};
  var lastRow = syncStateSheet.getLastRow();
  if (lastRow < 2) return state;

  var data = syncStateSheet.getRange(2, 1, lastRow - 1, 2).getValues();
  for (var i = 0; i < data.length; i++) {
    var docId    = data[i][0];
    var syncedAt = data[i][1];
    if (!docId) continue;
    state[docId] = {
      syncedAt: syncedAt instanceof Date ? syncedAt : new Date(syncedAt),
      row:      i + 2
    };
  }
  return state;
}

/**
 * Writes or updates a SyncState row for docId.
 * Mutates stateMap so subsequent lookups in the same run see the new timestamp.
 */
function _updateSyncState(syncStateSheet, docId, syncedAt, docTitle, stateMap) {
  if (stateMap[docId]) {
    syncStateSheet.getRange(stateMap[docId].row, 2, 1, 2).setValues([[syncedAt, docTitle || '']]);
    stateMap[docId].syncedAt = syncedAt;
  } else {
    var newRow = syncStateSheet.getLastRow() + 1;
    syncStateSheet.getRange(newRow, 1, 1, 3).setValues([[docId, syncedAt, docTitle || '']]);
    stateMap[docId] = { syncedAt: syncedAt, row: newRow };
  }
}


// ---------------------------------------------------------------------------
// Shared chip styling — configurable via configFormat() (gts-d99c)
// ---------------------------------------------------------------------------

// Style applied to the 'AI-N:' token when the Config sheet has no 'ai_token'
// row yet — exactly the hardcoded style this project used before configFormat()
// existed, so behavior is unchanged until someone runs it.
var _DEFAULT_AI_TOKEN_STYLE = Object.freeze({
  fontFamily: 'Comic Sans MS', fontSize: null, color: '#4C1D95',
  bold: true, italic: false, underline: false
});

var _actionFormatConfigCache = null;

/**
 * Reads the Config sheet's 'ai_token'/'action_text' rows once per GAS
 * execution (module-level cache — each execution gets a fresh global scope,
 * so this never serves stale data across separate requests). Falls back to
 * _DEFAULT_AI_TOKEN_STYLE for ai_token and null for action_text (meaning "no
 * override, inherit whatever the doc already has") when the Config sheet or
 * a given row doesn't exist yet — configFormat() is opt-in (gts-d99c).
 *
 * @returns {{aiToken: Object, actionText: ?Object}}
 */
function _getActionFormatConfig() {
  if (_actionFormatConfigCache) return _actionFormatConfigCache;
  _actionFormatConfigCache = _readActionFormatConfig(_openActionSheetSpreadsheet());
  return _actionFormatConfigCache;
}

function _readActionFormatConfig(ss) {
  var result = { aiToken: _DEFAULT_AI_TOKEN_STYLE, actionText: null };
  var sheet = ss.getSheetByName('Config');
  if (!sheet) return result;
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return result;
  var cols   = CONTRACT_SCHEMA.sheetConfig.columnsByField;
  var values = sheet.getRange(2, 1, lastRow - 1, CONTRACT_SCHEMA.sheetConfig.headers.length).getValues();
  for (var i = 0; i < values.length; i++) {
    var row = values[i];
    var key = row[cols.key - 1];
    if (key !== 'ai_token' && key !== 'action_text') continue;
    var parsed;
    try {
      parsed = JSON.parse(row[cols.value - 1] || '{}');
    } catch (e) {
      GasLogger.log('configFormat.parseError', { key: key, msg: e.message });
      continue;
    }
    var entry = {
      fontFamily: parsed.fontFamily || 'Arial',
      fontSize:   parsed.fontSize   || null,
      color:      parsed.color     || '#000000',
      bold:       !!parsed.bold,
      italic:     !!parsed.italic,
      underline:  !!parsed.underline
    };
    if (key === 'ai_token') result.aiToken = entry;
    else result.actionText = entry;
  }
  return result;
}

/**
 * Converts a '#rrggbb' hex string to the {red,green,blue} 0..1 float triple
 * the Docs REST API's rgbColor expects. Returns black on malformed input.
 *
 * @param {string} hex
 * @returns {{red:number, green:number, blue:number}}
 */
function _hexToRgbColor(hex) {
  var h = String(hex || '').replace('#', '');
  if (h.length !== 6) return { red: 0, green: 0, blue: 0 };
  return {
    red:   parseInt(h.substr(0, 2), 16) / 255,
    green: parseInt(h.substr(2, 2), 16) / 255,
    blue:  parseInt(h.substr(4, 2), 16) / 255
  };
}

/**
 * Returns the updateTextStyle request that applies the AI-N chip badge style
 * (font/size/color/bold/italic/underline, sourced from the Config sheet's
 * 'ai_token' row — gts-d99c) over [startIndex, endIndex).
 *
 * Shared by _flushActionParagraph (sync flush), _applyActionFragment
 * (creation/import), and _insertTrackerIdLinks (tracker ID column) so the
 * badge appearance is defined in exactly one place.
 *
 * @param {number} startIndex
 * @param {number} endIndex
 * @returns {Object} A Docs REST batchUpdate request object.
 */
function _chipBadgeStyleRequest(startIndex, endIndex) {
  var cfg   = _getActionFormatConfig().aiToken;
  var style = {
    bold: !!cfg.bold, italic: !!cfg.italic, underline: !!cfg.underline,
    foregroundColor: { color: { rgbColor: _hexToRgbColor(cfg.color) } },
    weightedFontFamily: { fontFamily: cfg.fontFamily, weight: cfg.bold ? 700 : 400 }
  };
  var fields = 'bold,italic,underline,foregroundColor,weightedFontFamily';
  if (cfg.fontSize) {
    style.fontSize = { magnitude: cfg.fontSize, unit: 'PT' };
    fields += ',fontSize';
  }
  return { updateTextStyle: { range: { startIndex: startIndex, endIndex: endIndex }, textStyle: style, fields: fields } };
}

/**
 * Returns the updateTextStyle request that applies the action-text style
 * (font/size/color/underline, sourced from the Config sheet's 'action_text'
 * row — gts-d99c) over [startIndex, endIndex), or null when no 'action_text'
 * row exists yet — callers must skip pushing a null result, leaving the
 * doc's default/inherited formatting untouched (opt-in, no behavior change
 * until configFormat() is run).
 *
 * gts-zocq composition-rule decision (IMPLEMENTED PER THE BEAD'S OWN ON-FILE
 * RECOMMENDATION, comment 2026-07-26 — PENDING EXPLICIT USER CONFIRMATION,
 * see plan-fix.md Session 9 Result for the flagged-open-question writeup):
 * 'bold' and 'italic' were REMOVED from this request's style/fields mask.
 * Before this change, every flush unconditionally reasserted the Config
 * 'action_text' row's bold/italic over the ENTIRE action-text range,
 * clobbering any inline (per-word) bold/italic the author typed in the doc
 * — the exact flattening gts-zocq exists to fix. Dropping them here lets
 * gts-zocq's per-run updateTextStyle requests (_buildFlushRequests) own
 * bold/italic exclusively, while Config keeps owning font family/size/
 * color/underline uniformly, same as before. This is a BEHAVIOR CHANGE for
 * any user who ran configFormat() against a bold- or italic-styled sample
 * expecting ALL future action text to inherit that uniform bold/italic —
 * per the bead's own comment, no test asserted that behavior before this
 * change (grepped clean), but it is still a real, shipped-feature behavior
 * change and is called out prominently rather than assumed silently
 * approved. See knowledge-base/adr/0022-inline-formatting-vs-config-uniform-style.md.
 *
 * @param {number} startIndex
 * @param {number} endIndex
 * @returns {?Object} A Docs REST batchUpdate request object, or null.
 */
function _actionTextStyleRequest(startIndex, endIndex) {
  var cfg = _getActionFormatConfig().actionText;
  if (!cfg) return null;
  var style = {
    underline: !!cfg.underline,
    foregroundColor: { color: { rgbColor: _hexToRgbColor(cfg.color) } },
    weightedFontFamily: { fontFamily: cfg.fontFamily }
  };
  var fields = 'underline,foregroundColor,weightedFontFamily';
  if (cfg.fontSize) {
    style.fontSize = { magnitude: cfg.fontSize, unit: 'PT' };
    fields += ',fontSize';
  }
  return { updateTextStyle: { range: { startIndex: startIndex, endIndex: endIndex }, textStyle: style, fields: fields } };
}

// ---------------------------------------------------------------------------
// configFormat — samples action-item style from a reference doc (gts-d99c)
// ---------------------------------------------------------------------------

/**
 * Menu entry point (Setup > Configure Action Format, MenuHandler.js). Thin
 * UI-prompt shell (gts-d99c/gts-1pk extraction): prompts for a Doc ID/URL,
 * parses it, and delegates to _configFormatForDoc(docId) for the actual
 * sampling/write work — then renders the same ui.alert()s as before. This
 * function is a documented entry-point-coverage EXEMPTION (same class as
 * menuBootstrap/menuInitializeTriggers, rz4k.4): SpreadsheetApp.getUi().
 * prompt() cannot execute in the run_fixture/doPost headless context
 * (Execution-API-style calls have no bound editor UI), so regression
 * coverage exercises _configFormatForDoc(docId) directly instead (see the
 * 'config_format' run_fixture case in TestFixtures.js).
 */
function configFormat() {
  var ui = SpreadsheetApp.getUi();
  var resp = ui.prompt(
    'Configure Action Format',
    'Enter the Doc ID (or URL) of a document whose first action item has the formatting you want to use:',
    ui.ButtonSet.OK_CANCEL
  );
  if (resp.getSelectedButton() !== ui.Button.OK) return;

  var raw = resp.getResponseText().trim();
  if (!raw) {
    ui.alert('No Doc ID entered.');
    return;
  }
  var idMatch = raw.match(/(?:\/d\/|[?&]id=)([a-zA-Z0-9_-]+)/);
  var docId = idMatch ? idMatch[1] : raw;

  var result = _configFormatForDoc(docId);
  if (!result.ok) {
    ui.alert(result.message);
    return;
  }

  var sample = result.sample;
  ui.alert(
    'Action format updated from ' + result.actionId + ' in "' + result.docName + '".\n\n' +
    _actionTokenPrefix('N') + ' token — ' + sample.aiToken.fontFamily + ', ' + sample.aiToken.fontSize + 'pt, ' + sample.aiToken.color +
      (sample.aiToken.bold ? ', bold' : '') + (sample.aiToken.italic ? ', italic' : '') + (sample.aiToken.underline ? ', underline' : '') + '\n' +
    'Action text — ' + sample.actionText.fontFamily + ', ' + sample.actionText.fontSize + 'pt, ' + sample.actionText.color +
      (sample.actionText.bold ? ', bold' : '') + (sample.actionText.italic ? ', italic' : '') + (sample.actionText.underline ? ', underline' : '')
  );
}

/**
 * Core of configFormat(), extracted (gts-d99c/gts-1pk) so it can be driven
 * headlessly by run_fixture ('config_format' case, TestFixtures.js) without
 * going through SpreadsheetApp.getUi().prompt(), which has no bound editor
 * UI in that context. Opens docId, finds its first floating action in
 * document order, samples the 'AI-N:' token's and the action text's font/
 * size/color/bold/italic/underline, and upserts them into the Config sheet.
 * Every subsequent chip write (sync flush, sidebar/preview status change,
 * Import create-chip, Tracker Table ID links) picks up the new style via
 * _getActionFormatConfig() — forward-only, nothing already written is
 * reformatted by this call.
 *
 * Uses _openActionSheetSpreadsheet() (TrackerTable.js) rather than
 * SpreadsheetApp.getActiveSpreadsheet() directly — that helper tries
 * getActiveSpreadsheet() first and only falls back to the ACTION_SHEET_ID/
 * TEST_SHEET_ID script property when it's null, so the interactive
 * menu-triggered path (which always has a bound active spreadsheet) behaves
 * identically to before this extraction; only the headless run_fixture path
 * (no bound spreadsheet) newly depends on the fallback.
 *
 * @param {string} docId
 * @returns {{ok:boolean, message:string}|{ok:boolean, docId:string, N:number, docName:string, sample:{aiToken:Object, actionText:Object}}}
 */
function _configFormatForDoc(docId) {
  var doc;
  try {
    doc = withGasRetry('SyncManager._configFormatForDoc:DocumentApp.openById',
      function () { return DocumentApp.openById(docId); });
  } catch (e) {
    return { ok: false, message: 'Could not open document: ' + e.message };
  }

  var actions = _scanFloatingActions(doc);
  if (actions.length === 0) {
    return { ok: false, message: 'No action items (' + _actionTokenPrefix('N') + ') found in that document.' };
  }

  var first     = actions[0];
  var firstToken = parseGlobalId(first.globalId).actionId;
  var sample    = _sampleActionItemStyle(first);
  if (!sample) {
    return { ok: false, message: 'Could not determine text style for the first action item (' + firstToken + ').' };
  }

  _writeActionFormatConfig(_openActionSheetSpreadsheet(), sample);
  _actionFormatConfigCache = null; // invalidate so later writes in this same execution see the new config

  var docName = doc.getName();
  GasLogger.log('configFormat.complete', { docId: docId, N: first.N, aiToken: sample.aiToken, actionText: sample.actionText });
  GasLogger.flush();

  return { ok: true, docId: docId, N: first.N, actionId: firstToken, docName: docName, sample: sample };
}

/**
 * Samples font family/size/color/bold/italic/underline separately for the
 * 'AI-N:' token text and the action-text content of one floating action,
 * using DocumentApp's per-character Text style getters. Returns null if the
 * token text can't be located within its own paragraph (shouldn't happen —
 * action came from _scanFloatingActions, which only returns matched tokens).
 *
 * @param {{N:number, paragraph:GoogleAppsScript.Document.Paragraph}} action
 * @returns {?{aiToken:Object, actionText:Object}}
 */
function _sampleActionItemStyle(action) {
  var para     = action.paragraph;
  var text     = para.editAsText();
  var fullText = para.getText();
  var prefix = null, tokenStart = -1;
  for (var pfxi = 0; pfxi < _ACTION_TOKEN_READ_PREFIXES.length; pfxi++) {
    var candidate = _ACTION_TOKEN_READ_PREFIXES[pfxi] + '-' + action.N + ':';
    var idx = fullText.indexOf(candidate);
    if (idx >= 0) { prefix = candidate; tokenStart = idx; break; }
  }
  if (tokenStart < 0) return null;

  var tokenSampleOffset = tokenStart + 1; // safely inside the token prefix
  var tokenEnd          = tokenStart + prefix.length; // just after ':'
  var afterToken         = fullText.slice(tokenEnd);
  var leadingSpace        = afterToken.match(/^\s*/)[0].length;
  var actionSampleOffset  = tokenEnd + leadingSpace;
  if (actionSampleOffset >= fullText.length) {
    actionSampleOffset = Math.max(tokenSampleOffset, fullText.length - 1);
  }

  function sampleAt(offset) {
    var color = text.getForegroundColor(offset);
    return {
      fontFamily: text.getFontFamily(offset) || 'Arial',
      fontSize:   text.getFontSize(offset)   || 11,
      color:      color || '#000000',
      bold:       !!text.isBold(offset),
      italic:     !!text.isItalic(offset),
      underline:  !!text.isUnderline(offset)
    };
  }

  return { aiToken: sampleAt(tokenSampleOffset), actionText: sampleAt(actionSampleOffset) };
}

/**
 * Upserts the 'ai_token' and 'action_text' rows in the Config sheet (creating
 * the sheet with its header row if absent).
 *
 * @param {Spreadsheet} ss
 * @param {{aiToken:Object, actionText:Object}} sample
 */
function _writeActionFormatConfig(ss, sample) {
  var sheet = ss.getSheetByName('Config');
  if (!sheet) {
    sheet = ss.insertSheet('Config');
    sheet.getRange(1, 1, 1, CONTRACT_SCHEMA.sheetConfig.headers.length).setValues([CONTRACT_SCHEMA.sheetConfig.headers]);
    sheet.setFrozenRows(1);
  }
  _upsertConfigRow(sheet, 'ai_token', sample.aiToken);
  _upsertConfigRow(sheet, 'action_text', sample.actionText);
}

function _upsertConfigRow(sheet, key, style) {
  var cols    = CONTRACT_SCHEMA.sheetConfig.columnsByField;
  var lastRow = sheet.getLastRow();
  var targetRow = -1;
  if (lastRow >= 2) {
    var ids = sheet.getRange(2, cols.key, lastRow - 1, 1).getValues();
    for (var i = 0; i < ids.length; i++) {
      if (ids[i][0] === key) { targetRow = i + 2; break; }
    }
  }
  if (targetRow === -1) targetRow = lastRow + 1;

  var rowValues = [];
  rowValues[cols.key - 1]   = key;
  rowValues[cols.value - 1] = JSON.stringify({
    fontFamily: style.fontFamily,
    fontSize:   style.fontSize,
    color:      style.color,
    bold:       !!style.bold,
    italic:     !!style.italic,
    underline:  !!style.underline
  });
  sheet.getRange(targetRow, 1, 1, CONTRACT_SCHEMA.sheetConfig.headers.length).setValues([rowValues]);
}

// ---------------------------------------------------------------------------
// REST flush — rewrites an AI-N: paragraph in place
// ---------------------------------------------------------------------------

// Fields fetched for a flush GET — include table cell content so AI-N tokens
// inside table cells are found. Element startIndex/endIndex are needed to
// map text-run character offsets back to absolute document positions, which
// is required for soft-return paragraphs where the token is mid-paragraph.
var _FLUSH_FIELDS = [
  'startIndex,endIndex,paragraph/elements(startIndex,endIndex,textRun/content)',
  'table/tableRows/tableCells/content(startIndex,endIndex,paragraph/elements(startIndex,endIndex,textRun/content))'
].join(',');

/**
 * Collects every occurrence of the 'AI-N:' token (at paragraph start, or
 * immediately after a soft-return) within a Docs REST body.content tree,
 * searching top-level paragraphs and table cells. Shared by
 * _flushActionParagraphs so a doc's content tree is parsed once per GET
 * regardless of how many distinct N values are being flushed in that GET.
 *
 * @param {Array} items   body.content (or a table cell's content) array
 * @param {number} N      the integer from the AI-N: token being searched for
 * @returns {Array<{pStart:number, pEnd:number, tokenDocIdx:number, lineDocIdx:number}>}
 */
function _collectFlushOccurrences(items, N) {
  var found = [];
  // ADR-0023 consequence: this exact-string paragraph lookup must try both
  // prefixes or flush will fail to locate a pre-existing AI-N: paragraph.
  var candidates = _ACTION_TOKEN_READ_PREFIXES.map(function (p) { return p + '-' + N + ':'; });
  function prefixAt(text, idx) {
    for (var ci = 0; ci < candidates.length; ci++) {
      if (text.substr(idx, candidates[ci].length) === candidates[ci]) return candidates[ci];
    }
    return null;
  }
  for (var ii = 0; ii < items.length; ii++) {
    var item = items[ii];
    if (item.paragraph) {
      var elements = item.paragraph.elements || [];
      // Build a concatenated text string and a position map from textRun
      // elements only (images and person chips are skipped in text but still
      // consume a document-index slot, so each run's startIndex is used
      // directly rather than recomputing from character counts).
      var fullText = '';
      var runMap   = []; // {startDocIdx, startTextIdx, len}
      for (var jj = 0; jj < elements.length; jj++) {
        var el = elements[jj];
        if (!el.textRun || el.startIndex === undefined) continue;
        var tc = el.textRun.content || '';
        runMap.push({ startDocIdx: el.startIndex, startTextIdx: fullText.length, len: tc.length });
        fullText += tc;
      }
      // Find the ACT-N:/AI-N: token at position 0 or immediately after a soft-return char.
      var tokenTextIdx = -1;
      if (prefixAt(fullText, 0)) {
        tokenTextIdx = 0;
      } else {
        for (var si = 0; si < fullText.length; si++) {
          var ch = fullText[si];
          if ((ch === '\n' || ch === '\r' || ch === '\v') && prefixAt(fullText, si + 1)) {
            tokenTextIdx = si + 1;
            break;
          }
        }
      }
      if (tokenTextIdx >= 0) {
        // Map tokenTextIdx to its absolute document index, and also compute
        // lineDocIdx — the document index of the character right after the
        // preceding newline (= pStart when the token is at paragraph start).
        // lineDocIdx is the delete/insert anchor: it correctly clears any
        // image that a previous flush may have placed on this line.
        //
        // When the token is at the start of the paragraph (tokenTextIdx===0)
        // lineDocIdx is item.startIndex — the paragraph node boundary, which
        // is BEFORE any existing inlineObjectElement. Searching the runMap for
        // afterNlTextIdx=0 would land on the first textRun (pStart+1, after
        // the image), skipping the image and leaving stale images in place.
        var tokenDocIdx = -1;
        var lineDocIdx  = tokenTextIdx === 0 ? item.startIndex : -1;
        for (var ri = 0; ri < runMap.length; ri++) {
          var run    = runMap[ri];
          var runEnd = run.startTextIdx + run.len;
          if (tokenDocIdx < 0 && tokenTextIdx >= run.startTextIdx && tokenTextIdx < runEnd) {
            tokenDocIdx = run.startDocIdx + (tokenTextIdx - run.startTextIdx);
          }
          if (lineDocIdx < 0) {
            // Soft-return case: find doc index of char immediately after the
            // preceding \n (afterNlTextIdx = tokenTextIdx).
            var afterNlTextIdx = tokenTextIdx;
            if (afterNlTextIdx >= run.startTextIdx && afterNlTextIdx <= runEnd) {
              lineDocIdx = run.startDocIdx + (afterNlTextIdx - run.startTextIdx);
            }
          }
          if (tokenDocIdx >= 0 && lineDocIdx >= 0) break;
        }
        if (tokenDocIdx >= 0) {
          if (lineDocIdx < 0) lineDocIdx = item.startIndex;
          found.push({ pStart: item.startIndex, pEnd: item.endIndex,
                       tokenDocIdx: tokenDocIdx, lineDocIdx: lineDocIdx });
        }
      }
    }
    if (item.table) {
      var tableRows = item.table.tableRows || [];
      for (var r = 0; r < tableRows.length; r++) {
        var cells = tableRows[r].tableCells || [];
        for (var c = 0; c < cells.length; c++) {
          var nested = _collectFlushOccurrences(cells[c].content || [], N);
          for (var ni = 0; ni < nested.length; ni++) found.push(nested[ni]);
        }
      }
    }
  }
  return found;
}

/**
 * Builds the ordered batchUpdate request list for one AI-N: occurrence —
 * delete the existing paragraph content, then re-insert
 * [image][AI-N: text][optional person chip][action text (status)] in reverse
 * order (each insertText/insertPerson/insertInlineImage call targets the same
 * insertAt index, pushing prior content right).
 *
 * @param {{pEnd:number, lineDocIdx:number, pStart:number}} occurrence
 * @param {{N:number, globalId:string, actionText:string, status:string,
 *          assigneeEmail:string, assigneeName:string,
 *          customFields:(Object<string,{text:string}>|undefined)}} item
 *          customFields is optional (gts-t6xs) -- {} or undefined omits
 *          field lines entirely, preserving pre-existing flush behavior.
 * @returns {Array<Object>} requests to append to one batchUpdate call
 */
/**
 * ADR-0027 rules 4/5a, write side: renders an action body with its status
 * token at the end of the HEADER LINE rather than at the end of the whole
 * multi-line body.
 *
 * The read side (_parseActionHeaderLineTracked) extracts the status from the
 * header line only, so a flush that appended '(Status)' after the last
 * continuation line — as this code did before gts-q23h — would write a token
 * the very next rescan could no longer see: the action would silently revert
 * to 'Open' and accumulate a second token on the following flush. Placement
 * and extraction have to agree, and the header line is where the grammar puts
 * it (`actionBody := text [ statusToken ]`, rule 5a's "the action body's first
 * line is the header line's text ... status token stripped").
 *
 * `text` is post-_toSoftReturnText, so its line breaks are U+000B.
 * `splitIdx` is where the suffix was inserted, which run offsets (gts-zocq)
 * relative to the un-suffixed body must be mapped across.
 *
 * @param {string} text    action body, soft-return spelling
 * @param {string} status
 * @returns {{text: string, splitIdx: number, suffixLen: number}}
 */
function _renderActionBodyWithStatus(text, status) {
  text = text || '';
  var suffix   = ' (' + status + ')';
  var breakIdx = text.indexOf('\v');
  var splitIdx = breakIdx === -1 ? text.length : breakIdx;
  return {
    text:      text.slice(0, splitIdx) + suffix + text.slice(splitIdx),
    splitIdx:  splitIdx,
    suffixLen: suffix.length
  };
}

/**
 * ADR-0027 rule 5a, write side (gts-t6xs fix): serializes action.customFields
 * back into the doc as 'FieldName:<TAB>value' soft-return continuation
 * lines, mirroring the read side (_parseFieldContinuationBlocksTracked /
 * _buildCustomFieldsFromBlocks) so flush is a real round trip instead of a
 * silent delete. Without this, any flush of a paragraph carrying a
 * field-line continuation rebuilds the paragraph from actionText alone
 * (_buildFlushRequests/_applyActionFragment) and permanently drops the
 * field lines from the document (gts-t6xs).
 *
 * gts-po8t correction (2026-08-27): the original layout indented each field
 * line two tabs (three on wrapped continuation lines) for visual
 * subordination under the header. That directly violated the documented
 * fieldLine grammar's "no leading whitespace" rule (docs/CONTEXT.md, ADR-0027
 * rule 5a) and _FIELD_LINE_REGEX's own `^[A-Z]` anchor -- a field line
 * written that way could never be recognized as a field line on the NEXT
 * scan, so it silently degraded into fused actionText prose one flush cycle
 * later (confirmed live: seed a field line -> sync -> sync again -> the
 * field vanishes from custom_fields and reappears merged into action_text).
 * Field lines are now written flush-left, matching the grammar exactly, so a
 * written field line parses as the same field again on the next scan. The
 * field name is bolded; the colon is followed by a literal tab (U+0009, not
 * a space) before the value -- this exactly reproduces _FIELD_LINE_REGEX's
 * own `[ \t]inlineValue?` production. A value spanning multiple original
 * lines is written back with no added indentation on its continuation
 * lines either, so a multi-line value round-trips byte-for-byte (any
 * indentation was never part of the stored value to begin with).
 *
 * @param {Object<string,{text:string}>} customFields  Object.keys() order
 *   is first-appearance order -- see _buildCustomFieldsFromBlocks.
 * @returns {{text: string, boldRanges: Array<[number,number]>}}
 *   text: soft-return continuation to append after the action body (starts
 *   with '\v'; '' when there are no fields).
 *   boldRanges: [start,end) offsets into `text` covering each field name +
 *   its trailing ':', for the caller to bold via updateTextStyle.
 */
function _renderCustomFieldLines(customFields) {
  var names = customFields ? Object.keys(customFields) : [];
  if (!names.length) return { text: '', boldRanges: [] };
  var text = '';
  var boldRanges = [];
  for (var i = 0; i < names.length; i++) {
    var name  = names[i];
    var raw   = (customFields[name] && customFields[name].text) || '';
    var lines = _normalizeLineEndings(raw).split('\n');
    text += '\v';
    var labelStart = text.length;
    text += name + ':';
    boldRanges.push([labelStart, text.length]);
    text += '\t' + lines[0];
    for (var li = 1; li < lines.length; li++) {
      text += '\v' + lines[li];
    }
  }
  return { text: text, boldRanges: boldRanges };
}

function _buildFlushRequests(occurrence, item) {
  var chipUrl    = _buildChipUrl(item.globalId);
  var imgUrl     = getStatusIconUrl(item.status);
  var validEmail = item.assigneeEmail && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(item.assigneeEmail);
  // Reproduce item.globalId's OWN prefix (ACT or legacy AI), not a freshly
  // canonicalized one: globalId is the durable identity key stored in the
  // sheet, and a rescan re-derives it from whatever token text is literally
  // in the doc. Forcing ACT-N here on every reformat-flush of a pre-existing
  // AI-N action would silently mint a NEW globalId on the next scan, losing
  // the mapping to the sheet row this flush just updated. New tokens (chip
  // create, placeholder assignment) still write canonical ACT-N — see
  // _actionTokenText's other call sites.
  var tokenText  = parseGlobalId(item.globalId).actionId + ': ';
  var tokenLen   = tokenText.length;
  var pEnd       = occurrence.pEnd;
  // actionText arrives with two different line-break spellings depending on
  // its source: the document's raw soft-return character (\r or \v) on a live
  // doc rescan (sidebar/preview-card status taps), or a plain \n from the
  // sheet (WebApp.js's _normalizeActionText). _toSoftReturnText folds both to
  // the single spelling insertText below reproduces as a real soft return,
  // U+000B — a bare \n would split the paragraph and a bare \r would be
  // stripped outright (gts-dr8j, superseding the space-collapse of
  // gts-kkm7.5). This is the one place every flush call site funnels through,
  // so no caller has to know which spelling it holds.
  var actionText = _toSoftReturnText(item.actionText);
  // gts-q23h / ADR-0027 rule 4: the status token goes at the end of the HEADER
  // LINE, not after the last continuation line — see
  // _renderActionBodyWithStatus for why placement and extraction must agree.
  var rendered   = _renderActionBodyWithStatus(actionText, item.status);
  // gts-t6xs fix: append any custom field-line continuations after the
  // status-suffixed body, so a flush preserves them instead of silently
  // deleting them (see _renderCustomFieldLines). Appended strictly after
  // rendered.text, so the run-offset math below (which is relative to
  // rendered.text's own length) is unaffected.
  var fieldLines = _renderCustomFieldLines(item.customFields);
  var bodyText   = rendered.text + fieldLines.text;
  // insertAt: for simple paragraphs this equals pStart; for soft-return
  // paragraphs it is the document index right after the preceding \n, which
  // also clears any image placed there by a previous flush.
  var insertAt   = occurrence.lineDocIdx !== undefined ? occurrence.lineDocIdx : occurrence.pStart;

  var requests = [];
  // Delete from insertAt to pEnd-1, preserving any contextual prefix text
  // and the mandatory trailing \n of the paragraph node.
  if (pEnd - 1 > insertAt) {
    requests.push({ deleteContentRange: { range: { startIndex: insertAt, endIndex: pEnd - 1 } } });
  }
  if (validEmail) {
    requests.push({ insertText: { text: ' ' + bodyText, location: { index: insertAt } } });
    // insertPerson rejects any name field in personProperties — email only
    requests.push({ insertPerson: { personProperties: { email: item.assigneeEmail }, location: { index: insertAt } } });
  } else {
    requests.push({ insertText: { text: bodyText, location: { index: insertAt } } });
  }
  requests.push({ insertText: { text: tokenText, location: { index: insertAt } } });
  requests.push({ insertInlineImage: {
    uri: imgUrl, location: { index: insertAt },
    objectSize: { height: { magnitude: 16, unit: 'PT' }, width: { magnitude: 16, unit: 'PT' } }
  }});
  requests.push({ updateTextStyle: {
    range: { startIndex: insertAt, endIndex: insertAt + 1 + tokenLen },
    textStyle: { link: { url: chipUrl } }, fields: 'link'
  }});
  requests.push(_chipBadgeStyleRequest(insertAt + 1, insertAt + 1 + tokenLen));

  // Action-text style (gts-d99c) — final layout left-to-right is
  // [image][token][optional person chip][' '?actionText (status)]; only push
  // when a Config 'action_text' row exists, else leave today's inherited
  // default formatting untouched. Uniform style no longer covers bold/italic
  // (ADR-0022/gts-zocq) — those are applied per-run immediately below.
  var trailingText  = (validEmail ? ' ' : '') + bodyText;
  // actionTextStart lands exactly at the first character of actionText itself
  // (past the image, token, and optional leading assignee-chip space) — the
  // same anchor gts-zocq's per-run requests below need.
  var actionTextStart = insertAt + 1 + tokenLen + (validEmail ? 1 : 0);
  var actionTextStyleReq = _actionTextStyleRequest(actionTextStart, actionTextStart + trailingText.length);
  if (actionTextStyleReq) requests.push(actionTextStyleReq);

  // gts-t6xs fix: bold each field name (+ its colon) in the field lines just
  // appended to bodyText. fieldLineBase is the doc index of the first
  // character of fieldLines.text, i.e. right after rendered.text.
  var fieldLineBase = actionTextStart + rendered.text.length;
  for (var fbi = 0; fbi < fieldLines.boldRanges.length; fbi++) {
    var fbr = fieldLines.boldRanges[fbi];
    requests.push({ updateTextStyle: {
      range: { startIndex: fieldLineBase + fbr[0], endIndex: fieldLineBase + fbr[1] },
      textStyle: { bold: true }, fields: 'bold'
    }});
  }

  // gts-zocq FLUSH: reapply inline bold/italic/link runs sampled at scan time
  // (or read back from the sheet's RichTextValue for a sheetWins flush), so
  // this delete+reinsert does not flatten formatting the author actually
  // typed (link extended by ADR-0028). item.runs offsets are relative to
  // item.actionText BEFORE _toSoftReturnText's own line-ending-normalize +
  // trim (that trim can shift indices — see _extractInlineRuns' offsets
  // contract); compute the same leading-whitespace shift _toSoftReturnText's
  // trim() applies and adjust run offsets by it, then clip to the final
  // actionText's bounds. Ranges stay within [actionTextStart, actionTextStart
  // + finalLen) — never widened past actionText, so a run link can never
  // overwrite the chip link on the token (ADR-0028 rule 5).
  if (item.runs && item.runs.length) {
    var rawActionText   = item.actionText || '';
    var normalizedRuns  = _normalizeLineEndings(rawActionText);
    var leadingWsLen    = (normalizedRuns.match(/^\s*/) || [''])[0].length;
    var finalLen        = actionText.length;
    var splitIdx        = rendered.splitIdx;
    var suffixLen       = rendered.suffixLen;
    for (var rui = 0; rui < item.runs.length; rui++) {
      var run = item.runs[rui];
      if (!run.bold && !run.italic && !run.link) continue;
      var rStart = Math.max(0, run.start - leadingWsLen);
      var rEnd   = Math.min(finalLen, run.end - leadingWsLen);
      if (rEnd <= rStart) continue;
      // gts-q23h: run offsets index the body WITHOUT the status suffix, which
      // is now inserted mid-string at rendered.splitIdx. Map each run across
      // that insertion; a run straddling the split emits two ranges so the
      // status token itself is never swept into the author's formatting.
      var style = { bold: !!run.bold, italic: !!run.italic, link: run.link ? { url: run.link } : null };
      var segments = (rEnd <= splitIdx)   ? [[rStart, rEnd]]
                   : (rStart >= splitIdx) ? [[rStart + suffixLen, rEnd + suffixLen]]
                   : [[rStart, splitIdx], [splitIdx + suffixLen, rEnd + suffixLen]];
      for (var segi = 0; segi < segments.length; segi++) {
        if (segments[segi][1] <= segments[segi][0]) continue;
        requests.push({ updateTextStyle: {
          range: { startIndex: actionTextStart + segments[segi][0], endIndex: actionTextStart + segments[segi][1] },
          textStyle: style,
          fields: 'bold,italic,link'
        }});
      }
    }
  }

  return requests;
}

/**
 * Rewrites the content of every item's AI-N: paragraph via ONE Docs REST GET
 * + ONE batchUpdate for the whole doc, regardless of how many action items
 * are being flushed (gts-kkm7.3) — replaces what was previously one
 * GET + one batchUpdate per item. Preserves each paragraph node (does not
 * delete its trailing \n). Caller must have called doc.saveAndClose() before
 * invoking this.
 *
 * Fault granularity: a missing paragraph for one item only fails that item
 * (others still flush). A GET failure fails every item (shared fetch, no
 * fallback). A batchUpdate failure fails every item that had a request in
 * that one call — this is coarser than the old per-item batchUpdate, but
 * callers already remark a failed item Dirty for retry on the next sync
 * (_remarkRowDirty), so a transient combined-batch failure self-heals on the
 * next sweep exactly like an individual failure did before.
 *
 * @param {string} docId
 * @param {string} token  OAuth token from ScriptApp.getOAuthToken()
 * @param {Array<{N:number, globalId:string, actionText:string, status:string,
 *                assigneeEmail:string, assigneeName:string}>} items
 * @returns {Object<string, boolean>} globalId -> whether that item flushed
 */
function _flushActionParagraphs(docId, token, items) {
  var t0      = Date.now();
  var baseUrl = 'https://docs.googleapis.com/v1/documents/';
  var results = {};

  var getResp = UrlFetchApp.fetch(baseUrl + docId + '?fields=body.content(' + _FLUSH_FIELDS + ')',
    { headers: { Authorization: 'Bearer ' + token }, muteHttpExceptions: true });
  if (getResp.getResponseCode() !== 200) {
    GasLogger.log('flush.error', { msg: 'GET failed: HTTP ' + getResp.getResponseCode(), docId: docId, batchSize: items.length });
    for (var fi = 0; fi < items.length; fi++) results[items[fi].globalId] = false;
    return results;
  }
  var tGet = Date.now();

  var getBody = JSON.parse(getResp.getContentText());
  var content = (getBody.body || {}).content || [];

  // Find every item's occurrence(s) against the one parsed content tree, then
  // flatten into a single globally-sorted request list so requests targeting
  // a higher document index always run before ones targeting a lower index —
  // required because batchUpdate applies requests in array order and earlier
  // edits shift the indices of everything after them in the document.
  var pending = []; // {occurrence, item}
  for (var ii = 0; ii < items.length; ii++) {
    var occurrences = _collectFlushOccurrences(content, items[ii].N);
    if (occurrences.length === 0) {
      GasLogger.log('flush.warn', { msg: 'Paragraph not found', globalId: items[ii].globalId });
      results[items[ii].globalId] = false;
      continue;
    }
    results[items[ii].globalId] = true; // tentative — flipped to false below if the shared batchUpdate fails
    for (var oi = 0; oi < occurrences.length; oi++) {
      pending.push({ occurrence: occurrences[oi], item: items[ii] });
    }
  }

  if (pending.length === 0) return results;

  pending.sort(function (a, b) { return b.occurrence.pStart - a.occurrence.pStart; });

  var requests = [];
  for (var pi = 0; pi < pending.length; pi++) {
    var built = _buildFlushRequests(pending[pi].occurrence, pending[pi].item);
    for (var bi = 0; bi < built.length; bi++) requests.push(built[bi]);
  }

  var batchResp = UrlFetchApp.fetch(baseUrl + docId + ':batchUpdate', {
    method: 'post', muteHttpExceptions: true,
    headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
    payload: JSON.stringify({ requests: requests })
  });
  var tBatch = Date.now();

  if (batchResp.getResponseCode() === 200) {
    GasLogger.log('flush.done', {
      docId: docId, batchSize: items.length, copies: pending.length,
      ms: { get: tGet - t0, batchUpdate: tBatch - tGet, total: tBatch - t0 }
    });
    return results;
  }

  GasLogger.log('flush.error', {
    msg: 'batchUpdate failed: HTTP ' + batchResp.getResponseCode(),
    body: batchResp.getContentText().substring(0, 300), docId: docId, batchSize: items.length
  });
  for (var gi in results) {
    if (results.hasOwnProperty(gi) && results[gi] === true) results[gi] = false;
  }
  return results;
}

/**
 * Single-item convenience wrapper over _flushActionParagraphs for the
 * interactive call sites (preview-card status tap, sidebar status set) that
 * only ever flush one action at a time.
 *
 * @param {string} docId
 * @param {string} token          OAuth token from ScriptApp.getOAuthToken()
 * @param {number} N              The integer from the AI-N: token
 * @param {string} globalId       {docId}/AI-{N}
 * @param {string} actionText     Action text (no trailing status token)
 * @param {string} status         Status string
 * @param {string} assigneeEmail  May be empty
 * @param {string=} assigneeName  Optional display name for person chip
 * @param {Array=} runs           gts-zocq — optional inline bold/italic/link runs
 * @param {Object=} customFields  gts-t6xs — optional {FieldName:{text}}
 *   field-line continuations to preserve on this flush; defaults to {}
 *   (no field lines rewritten), same as omitting the argument entirely.
 * @returns {boolean} whether the item flushed
 */
function _flushActionParagraph(docId, token, N, globalId, actionText, status, assigneeEmail, assigneeName, runs, customFields) {
  var results = _flushActionParagraphs(docId, token, [{
    N: N, globalId: globalId, actionText: actionText, status: status,
    assigneeEmail: assigneeEmail, assigneeName: assigneeName || '',
    runs: runs || [], // gts-zocq — optional, defaults to no inline formatting
    customFields: customFields || {} // gts-t6xs — optional, defaults to no field lines
  }]);
  return !!results[globalId];
}


/**
 * Single shared authority for canonical action status states and resolution.
 * Five canonical states: Open, InProgress, Waiting, Delegated, Closed.
 * isResolved() returns true for Delegated or Closed states only—meaning no further action is required.
 * DocData.Resolved Count must be computed exclusively through isResolved().
 * All status matching is case-insensitive.
 *
 * @param {string} status  The action status string.
 * @returns {boolean}
 */

/**
 * The one table mapping each canonical state to the free-text values users
 * actually type. Every is<State>() below reads it, and getStatusDisplay()
 * resolves a status through it once, server-side — so a surface that has to
 * bucket or display an arbitrary status string never restates these words nor
 * re-implements the matching.
 */
var _STATUS_SYNONYMS = {
  Open:       ["open", "pending", "planned", "queued", "unstarted", "new"],
  InProgress: ["active", "in-progress", "working", "running", "executing", "processing"],
  Waiting:    ["waiting", "blocked", "on-hold", "stalled", "paused"],
  Delegated:  ["delegated", "routed", "forwarded", "escalated", "handed-off", "transferred"],
  Closed:     ["done", "complete", "finished", "closed", "resolved", "finalized"]
};

/** Separator- and case-blind, so 'In Progress', 'in-progress' and 'in progress'
 *  are one value. Canonical statuses are spelled with spaces and the synonym
 *  lists with hyphens; without this the canonical value misses its own state. */
function _normalizeStatus(status) {
  return typeof status === "string" ? status.trim().toLowerCase().replace(/[^a-z0-9]/g, "") : "";
}

function _matchesState(status, state) {
  var key = _normalizeStatus(status);
  return key !== "" && _STATUS_SYNONYMS[state].some(function (word) {
    return _normalizeStatus(word) === key;
  });
}

function isOpen(status)       { return _matchesState(status, 'Open'); }
function isInProgress(status) { return _matchesState(status, 'InProgress'); }
function isWaiting(status)    { return _matchesState(status, 'Waiting'); }
function isDelegated(status)  { return _matchesState(status, 'Delegated'); }
function isClosed(status)     { return _matchesState(status, 'Closed'); }

/**
 * Determines if an action is resolved (no longer tracked in this document).
 * Returns true for Delegated or Closed states—meaning no further action is required.
 *
 * @param {string} status  The action status string.
 * @returns {boolean}
 */
function isResolved(status) {
  return isDelegated(status) || isClosed(status);
}

/**
 * Resolves a status string to its icon URL.
 * Exact canonical matches win; otherwise resolved statuses fall back to the
 * Closed icon, and anything else falls back to the unknown/default icon.
 *
 * @param {string} status
 * @returns {string} Icon URL
 */
function getStatusIconUrl(status) {
  return getStatusDisplay(status).icon;
}

/**
 * Everything a surface needs to DISPLAY a free-text status: which canonical
 * state it falls in, whether the Open/Closed filter treats it as resolved, and
 * its icon. Computed here so a surface that cannot call these functions — the
 * web portal — renders the server's answer instead of re-deriving one.
 *
 * @param {string} status
 * @returns {{bucket: string, resolved: boolean, icon: string}}
 *          bucket is a _STATUS_SYNONYMS key, or 'Other' for a value in no state.
 */
function getStatusDisplay(status) {
  var bucket = 'Other';
  for (var state in _STATUS_SYNONYMS) {
    if (_matchesState(status, state)) { bucket = state; break; }
  }
  var resolved = isResolved(status);
  // Exact canonical matches win; otherwise resolved statuses fall back to the
  // Closed icon, and anything else to the unknown/default icon.
  var icon = _ACTION_STATUS_IMAGES.hasOwnProperty(status) ? _ACTION_STATUS_IMAGES[status]
           : resolved                                    ? _ACTION_STATUS_IMAGES['Closed']
           : _ACTION_DEFAULT_IMAGE;
  return { bucket: bucket, resolved: resolved, icon: icon };
}

/**
 * Canonical {status, icon, alt} list for status-picker button rows.
 *
 * @returns {Array<{status: string, icon: string, alt: string}>}
 */
function getStatusIconButtons() {
  return _ACTION_STATUSES.map(function(status) {
    return { status: status, icon: _ACTION_STATUS_IMAGES[status], alt: 'Set ' + status };
  });
}

