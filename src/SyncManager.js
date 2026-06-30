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
// Public entry points
// ---------------------------------------------------------------------------

function syncDocument(docId) {
  try {
    if (!docId) {
      GasLogger.log('sync.error', { msg: 'docId is required' });
      return;
    }

    var doc;
    try {
      doc = DocumentApp.openById(docId);
    } catch (openErr) {
      GasLogger.log('sync.docNotFound.invalid', { msg: 'Doc not found', docId: docId, err: openErr.message });
      _markDocNotFound(docId);
      return;
    }
    // DocumentApp.openById() succeeds on trashed docs — check explicitly.
    try {
      if (DriveApp.getFileById(docId).isTrashed()) {
        GasLogger.log('sync.docNotFound.trashed', { msg: 'Doc not found', docId: docId, err: 'Document is in Trash' });
        _markDocNotFound(docId);
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
        status:        a.status
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
      toFlush[win.globalId] = {
        N:             cf.N,
        globalId:      win.globalId,
        action:        win.action,
        status:        win.status,
        assigneeEmail: win.assigneeEmail,
        assigneeName:  win.assigneeName
      };
    }
    for (var ni = 0; ni < assignResult.newGlobalIds.length; ni++) {
      var ngId = assignResult.newGlobalIds[ni];
      if (toFlush[ngId]) continue; // sheetWin already covers it
      var cfn = canonicalByGlobalId[ngId];
      if (!cfn) continue;
      toFlush[ngId] = {
        N:             cfn.N,
        globalId:      ngId,
        action:        cfn.actionText,
        status:        cfn.status,
        assigneeEmail: cfn.assigneeEmail,
        assigneeName:  cfn.assigneeName
      };
    }
    for (var gId in hasDuplicateN) {
      if (toFlush[gId]) continue; // sheetWin or new-assign already covers it
      var cf2 = canonicalByGlobalId[gId];
      if (!cf2) continue;
      toFlush[gId] = {
        N:             cf2.N,
        globalId:      gId,
        action:        cf2.actionText,
        status:        cf2.status,
        assigneeEmail: cf2.assigneeEmail,
        assigneeName:  cf2.assigneeName
      };
    }

    // Materialize missing explicit status tokens as '(Open)' in the doc.
    for (var gId3 in canonicalByGlobalId) {
      if (toFlush[gId3]) continue;
      var cfm = canonicalByGlobalId[gId3];
      if (!cfm.hasExplicitStatus) {
        toFlush[gId3] = {
          N:             cfm.N,
          globalId:      gId3,
          action:        cfm.actionText,
          status:        cfm.status,
          assigneeEmail: cfm.assigneeEmail,
          assigneeName:  cfm.assigneeName
        };
      }
    }

    var flushIds = Object.keys(toFlush);
    if (flushIds.length > 0) {
      var docId2 = doc.getId();
      doc.saveAndClose(); // close before REST calls
      var token = ScriptApp.getOAuthToken();
      for (var ti = 0; ti < flushIds.length; ti++) {
        var f  = toFlush[flushIds[ti]];
        var ok = _flushActionParagraph(docId2, token, f.N, f.globalId,
          f.action, f.status, f.assigneeEmail, f.assigneeName);
        if (!ok) _remarkRowDirty(f.globalId);
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
      updated:  syncResult.updated  || 0
    });
  } finally {
    GasLogger.flush();
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
  // sync.complete) in Axiom -- see GasLogger.startOp() (GTaskSheet-65g1).
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

    var synced = 0, skipped = 0;
    for (var j = 0; j < docIds.length; j++) {
      var docId = docIds[j];

      // Skip docs already permanently marked Doc Not Found — no Drive call needed.
      if (alreadyDocNotFound[docId]) {
        skipped++;
        continue;
      }

      // Single Drive call: trash check + last-modified timestamp.
      var driveFile, isTrashed, lastModified, docTitle;
      try {
        driveFile    = DriveApp.getFileById(docId);
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

      if (isTrashed) {
        GasLogger.log('sync.docNotFound.trashed', { msg: 'Doc not found', docId: docId, err: 'Document is in Trash' });
        _markDocNotFound(docId);
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

    GasLogger.log('sync.all.complete', { docCount: docIds.length, synced: synced, skipped: skipped });

    // ── DocData integrity pass (GTaskSheet-6ipb) ──────────────────────────
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

    var integrityUpdated = 0;
    for (var docIdKey in docIdsWithAnyRows) {
      if (!docIdsWithAnyRows.hasOwnProperty(docIdKey)) continue;
      var existingRow = _readDocDataRow(ss, docIdKey);
      if (!existingRow) continue; // no DocData row to reconcile yet — first-pass write happens elsewhere
      var computed = integrityCounts[docIdKey] || { actionCount: 0, resolvedCount: 0 };
      var computedName = docTitleByDocId[docIdKey] || existingRow.docName;
      var changed = (
        existingRow.actionCount !== computed.actionCount ||
        existingRow.resolvedCount !== computed.resolvedCount ||
        existingRow.docName !== computedName
      );
      if (!changed) continue;
      _getOrUpsertDocDataRow(
        ss, docIdKey,
        computedName,
        existingRow.lastSyncTime,
        existingRow.teamId,
        existingRow.syncStatus,
        computed.actionCount,
        computed.resolvedCount
      );
      integrityUpdated++;
    }
    GasLogger.log('sync.integrity.complete', { updated: integrityUpdated });
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

    if (!globalId) return;
    if (!docFormula) return;

    var docIdMatch = docFormula.match(/(?:\/d\/|[?&]id=)([a-zA-Z0-9_-]+)/);
    if (!docIdMatch) return;
    var docId = docIdMatch[1];

    var parsed = parseGlobalId(globalId);
    if (isNaN(parsed.N)) return;
    var N = parsed.N;

    var token = ScriptApp.getOAuthToken();
    var ok = _flushActionParagraph(docId, token, N, globalId, action, status, assigneeEmail, assigneeName || '');
    if (ok) {
      // Flush confirmed — clear Dirty immediately rather than waiting for WebApp round-trip.
      WriteGuard.wrap(function () { sheet.getRange(row, _SCOL.sync_status).setValue(''); });
      GasLogger.log('sync.sheet-to-doc.done', { globalId: globalId });
      // Note: syncDocument() was removed here. It caused a race condition: the trigger
      // fires in a separate GAS execution, opens the doc via DocumentApp.openById with a
      // stale cached view (status=pre-edit), and the doc-wins path overwrites the sheet
      // back to the old value. Chip-resolved assigneeName propagation is deferred to the
      // next scheduled syncAll sweep.
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
  var fullText   = para.getText().replace(/\n$/, '');
  var tokenMatch = fullText.match(/^AI-(\d+):\s*/);
  if (!tokenMatch) return null;

  var N          = parseInt(tokenMatch[1], 10);
  var globalId   = docId + '/AI-' + N;
  var afterToken = fullText.slice(tokenMatch[0].length);

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
      var em = t.match(/^[\s]*([\w.+\-]+@[\w\-]+(?:\.[a-z]{2,})+)\s*/i);
      if (em) { assigneeEmail = em[1]; assigneeName = _nameFromEmail(assigneeEmail); }
      break;
    }
  }

  var actionText    = afterToken;
  var assigneeStrip = afterToken.match(/^([\w.+\-]+@[\w\-]+(?:\.[a-z]{2,})+)\s*/i);
  if (assigneeStrip) {
    actionText = afterToken.slice(assigneeStrip[0].length);
    if (!assigneeEmail) {
      assigneeEmail = assigneeStrip[1];
      assigneeName  = _nameFromEmail(assigneeEmail);
    }
  }

  var status            = 'Open';
  var statusMatch       = actionText.match(/\(([^)]*)\)\s*$/);
  var hasExplicitStatus = !!statusMatch;
  if (statusMatch) {
    status     = statusMatch[1].trim() || 'Open';
    actionText = actionText.slice(0, actionText.length - statusMatch[0].length).trim();
  }

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
    isDuplicate:       seenN[N] === true
  };
  seenN[N] = true;
  return action;
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
 * Handles paragraphs containing one or more AI-N: tokens that appear after
 * soft-return (\n) lines — the pattern where the user writes contextual text
 * on the first line(s) and AI-N: tokens on subsequent lines within a single
 * paragraph element.
 *
 * Returns an array of action objects (one per AI-N: token found).
 * Text-based email assignee detection only; PERSON chips are handled by the
 * single-token fast path in _collectActionsFromParagraph.
 */
function _parseSoftReturnParagraphActions(para, bodyIdx, docId, seenN, fullText) {
  // Normalize all line-separator variants (soft returns in DocumentApp may be
  // \r, \r\n, or \v depending on the GAS runtime version).
  var normalized = fullText.replace(/\r\n/g, '\n').replace(/[\r\v]/g, '\n');
  var lines   = normalized.split('\n');
  var results = [];
  var curN    = null;
  var curLines = [];

  function flush() {
    if (curN === null) return;
    var rawText = curLines.join('\n').trim();
    var assigneeEmail = '';
    var assigneeName  = '';
    var emailMatch = rawText.match(/^([\w.+\-]+@[\w\-]+(?:\.[a-z]{2,})+)\s*/i);
    if (emailMatch) {
      assigneeEmail = emailMatch[1];
      assigneeName  = _nameFromEmail(assigneeEmail);
      rawText = rawText.slice(emailMatch[0].length);
    }
    var status = 'Open';
    var hasExplicitStatus = false;
    var statusMatch = rawText.match(/\(([^)]*)\)\s*$/);
    if (statusMatch) {
      status = statusMatch[1].trim() || 'Open';
      rawText = rawText.slice(0, rawText.length - statusMatch[0].length).trim();
      hasExplicitStatus = true;
    }
    var N = curN;
    results.push({
      bodyChildIndex:    bodyIdx,
      paragraph:         para,
      globalId:          docId + '/AI-' + N,
      N:                 N,
      assigneeEmail:     assigneeEmail,
      assigneeName:      assigneeName,
      actionText:        rawText,
      status:            status,
      hasExplicitStatus: hasExplicitStatus,
      isDuplicate:       seenN[N] === true
    });
    seenN[N] = true;
  }

  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    var m = line.match(/^AI-(\d+):\s*/);
    if (m) {
      flush();
      curN    = parseInt(m[1], 10);
      curLines = [line.slice(m[0].length)];
    } else if (curN !== null) {
      curLines.push(line); // continuation line
    }
    // else: contextual text before first AI token — skip (AC-3)
  }
  flush();
  return results;
}

/**
 * Collects floating actions from a single paragraph/list-item, dispatching
 * to the correct parser based on whether the paragraph has a single leading
 * AI-N: token (fast path, PERSON chip support) or uses the soft-return
 * multi-token pattern (new path, text-based assignee only).
 *
 * Appends any found actions to the `actions` array in place.
 */
function _collectActionsFromParagraph(para, bodyIdx, docId, seenN, actions) {
  // Normalize line endings before scanning so \r, \r\n, and \v (soft return
  // variants across GAS runtime versions) all work.
  var raw  = para.getText();
  var text = raw.replace(/\r\n/g, '\n').replace(/[\r\v]/g, '\n').replace(/\n$/, '');
  var tokenCount = (text.match(/(?:^|\n)AI-\d+:/g) || []).length;
  if (tokenCount === 0) return;

  // Single token at paragraph start: use existing logic (handles PERSON chips).
  if (tokenCount === 1 && /^AI-\d+:/.test(text)) {
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
 * @returns {Array<{bodyChildIndex, paragraph, globalId, N, assigneeEmail, assigneeName, actionText, status, hasExplicitStatus, isDuplicate}>}
 */
function _scanFloatingActions(doc) {
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
    _collectActionsFromParagraph(para, i, docId, seenN, actions);
  }
  return actions;
}

/**
 * Finds paragraphs starting with the bare "AI:" placeholder (no number) and
 * rewrites them as "AI-N:" using the next available N in the document.
 * Called in syncDocument before _scanFloatingActions so the scanner always
 * sees fully-formed AI-N: tokens.
 *
 * @param {GoogleAppsScript.Document.Document} doc
 * @returns {{ count: number, newGlobalIds: string[] }}
 */
/**
 * Collects all paragraph elements (including those in table cells, excluding
 * the tracker table) that have AI-N: or AI: tokens, for use in
 * _assignPlaceholderTokens.
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
    var text  = raw.replace(/\r\n/g, '\n').replace(/[\r\v]/g, '\n').replace(/\n$/, '');
    var lines = text.split('\n');
    var lineOffset = 0;
    for (var li = 0; li < lines.length; li++) {
      var line = lines[li];
      var m = line.match(/^AI-(\d+):/);
      if (m) {
        numbered.push(parseInt(m[1], 10));
      } else if (/^AI:/.test(line)) {
        // lineOffset is the character offset into the normalized text.
        // The actual paragraph text may use different byte widths for the
        // line separator; editAsText offsets work on the raw getText() bytes.
        // Recompute offset from raw text using a search from lineOffset onward.
        var rawOffset = raw.indexOf(line, lineOffset);
        if (rawOffset === -1) rawOffset = lineOffset; // fallback
        placeholders.push({ para: para, offset: rawOffset });
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
      newGlobalIds.push(docId + '/AI-' + maxN);
      assigned++;
    }
    // Insert '-N' right-to-left within the paragraph to avoid offset drift.
    // offset+2 is the position between 'AI' and ':'.
    for (var k = pi - 1; k >= groupStart; k--) {
      groupPara.editAsText().insertText(found.placeholders[k].offset + 2, '-' + groupNs[k - groupStart]);
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
 * @param {Array}  anchorResults  Each element: { globalId, assigneeEmail, assigneeName, actionText, status }.
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
      status:        a.status
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
      opId:               GasLogger.getCurrentOp(),
      docUrl:             docUrl,
      docTitle:           docTitle,
      docId:              docId || '',
      docState:           docState,
      allDocGlobalIds: allDocGlobalIds || []
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
 * all Actions rows whose Document formula references this docId.
 *
 * @param {string} docId
 */
function _markDocNotFound(docId) {
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
      opId:          GasLogger.getCurrentOp(),
      docId:         docId
    })
  });
  GasLogger.flush();
}

// ---------------------------------------------------------------------------
// Team Scope: Drive appProperty read/write and folder-walk auto-assignment
// (GTaskSheet-me6w.3 — see knowledge-base/staging/epic-b-team-property-sync.md)
// ---------------------------------------------------------------------------

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
  var url = 'https://www.googleapis.com/drive/v3/files/' + docId + '?fields=appProperties';
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
  var url     = 'https://www.googleapis.com/drive/v3/files/' + docId + '?fields=appProperties';
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
 * @param {string} docId
 * @param {Array<{teamId: string, folderId: string, teamLink: string}>} teamDataRows
 * @return {?{teamId: string, teamLink: string}} the matched team, or null if no
 *   ancestor matches (or on Drive error).
 */
function _walkFolderForTeam(docId, teamDataRows) {
  try {
    var parents = DriveApp.getFileById(docId).getParents();
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
      for (var i = 0; i < teamDataRows.length; i++) {
        if (teamDataRows[i].folderId === folderId) {
          return { teamId: teamDataRows[i].teamId, teamLink: teamDataRows[i].teamLink || '' };
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
    return null;
  } catch (e) {
    GasLogger.log('sync.teamScope.walk.error', { docId: docId, msg: e.message });
    return null;
  }
}

// ---------------------------------------------------------------------------
// Team Scope: security gate
// (GTaskSheet-me6w.5 — see knowledge-base/staging/epic-b-team-property-sync.md)
// ---------------------------------------------------------------------------

/**
 * Verifies that the active user can access the given team's folder. Standalone
 * gate — not called from syncDocument(); intended for future team-scoped
 * filtered reads (Import/Notify, EPIC-D/E).
 *
 * Throws rather than returning a boolean: callers catch the error message
 * prefix ('TeamNotFound: ' or 'TeamAccessDenied: ') and respond with no rows
 * plus a surfaced error — never partial/leaked data.
 *
 * @param {string} teamId
 * @param {Spreadsheet} ss
 * @throws {Error} 'TeamNotFound: <teamId>' if no TeamData row matches teamId.
 * @throws {Error} 'TeamAccessDenied: <teamId>' if the active user cannot
 *   access the team's folder (DriveApp.getFolderById throws).
 */
function assertTeamAccess(teamId, ss) {
  var teamDataRows = _readTeamDataRows(ss);
  var match = null;
  for (var i = 0; i < teamDataRows.length; i++) {
    if (teamDataRows[i].teamId === teamId) {
      match = teamDataRows[i];
      break;
    }
  }
  if (!match) {
    throw new Error('TeamNotFound: ' + teamId);
  }
  try {
    DriveApp.getFolderById(match.folderId);
  } catch (e) {
    throw new Error('TeamAccessDenied: ' + teamId);
  }
}

// ---------------------------------------------------------------------------
// Team Scope: DocData sync (DocWins + UpdateDoc write-back)
// (GTaskSheet-me6w.4 — see knowledge-base/staging/epic-b-team-property-sync.md)
// ---------------------------------------------------------------------------

/**
 * DocData field contract (GTaskSheet-rename, was Doc Modified/Doc Updated):
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
 * (e.g. for Import's per-action Team Id join, GTaskSheet-eore) without calling
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

  var rowValues = [];
  rowValues[cols.file_id - 1]        = fileId;
  rowValues[cols.doc_name - 1]       = docName;
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

  // DocData.teamId mirrors the Drive teamScope appProperty -- both are written
  // together, only by this function (the .overridden/.resolved branches below),
  // so in the steady state (no override pending, already resolved) they're
  // provably identical. Trusting the mirror skips a Drive REST round trip on
  // every sync of an already-resolved doc -- the common case, ~2-4s saved per
  // sync (GTaskSheet-j8cn perf pass). The narrow risk this introduces (a crashed
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
// Shared chip styling
// ---------------------------------------------------------------------------

/**
 * Returns the updateTextStyle request that applies the AI-N chip badge style
 * over [startIndex, endIndex): bold Comic Sans, purple text (#4C1D95), no
 * hyperlink underline. No background is set — the badge is purple text only.
 *
 * Shared by _flushActionParagraph (sync flush), _insertActionChip (creation),
 * and _insertTrackerIdLinks (tracker ID column) so the badge appearance is
 * defined in exactly one place.
 *
 * @param {number} startIndex
 * @param {number} endIndex
 * @returns {Object} A Docs REST batchUpdate request object.
 */
function _chipBadgeStyleRequest(startIndex, endIndex) {
  return {
    updateTextStyle: {
      range: { startIndex: startIndex, endIndex: endIndex },
      textStyle: {
        bold: true, underline: false,
        foregroundColor: { color: { rgbColor: { red: 0.298, green: 0.114, blue: 0.584 } } },
        weightedFontFamily: { fontFamily: 'Comic Sans MS', weight: 700 }
      },
      fields: 'bold,underline,foregroundColor,weightedFontFamily'
    }
  };
}

// ---------------------------------------------------------------------------
// REST flush — rewrites an AI-N: paragraph in place
// ---------------------------------------------------------------------------

/**
 * Rewrites the content of an AI-N: paragraph via REST API batchUpdate.
 * Preserves the paragraph node (does not delete the trailing \n).
 * Caller must have called doc.saveAndClose() before invoking this.
 *
 * @param {string} docId
 * @param {string} token          OAuth token from ScriptApp.getOAuthToken()
 * @param {number} N              The integer from the AI-N: token
 * @param {string} globalId       {docId}/AI-{N}
 * @param {string} actionText     Action text (no trailing status token)
 * @param {string} status         Status string
 * @param {string} assigneeEmail  May be empty
 * @param {string=} assigneeName  Optional display name for person chip
 */
function _flushActionParagraph(docId, token, N, globalId, actionText, status, assigneeEmail, assigneeName) {
  var baseUrl = 'https://docs.googleapis.com/v1/documents/';
  var chipUrl = _buildChipUrl(globalId);
  var imgUrl = getStatusIconUrl(status);

  var validEmail = assigneeEmail && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(assigneeEmail);
  var tokenLen   = ('AI-' + N + ': ').length;

  // GET to find paragraph indices — include table cell content so AI-N tokens
  // inside table cells are found. Element startIndex/endIndex are needed to
  // map text-run character offsets back to absolute document positions, which
  // is required for soft-return paragraphs where the token is mid-paragraph.
  var _FLUSH_FIELDS = [
    'startIndex,endIndex,paragraph/elements(startIndex,endIndex,textRun/content)',
    'table/tableRows/tableCells/content(startIndex,endIndex,paragraph/elements(startIndex,endIndex,textRun/content))'
  ].join(',');
  var getResp = UrlFetchApp.fetch(baseUrl + docId + '?fields=body.content(' + _FLUSH_FIELDS + ')',
    { headers: { Authorization: 'Bearer ' + token }, muteHttpExceptions: true });
  if (getResp.getResponseCode() !== 200) {
    GasLogger.log('flush.error', { msg: 'GET failed: HTTP ' + getResp.getResponseCode(), globalId: globalId });
    return false;
  }

  var getBody = JSON.parse(getResp.getContentText());
  var content = (getBody.body || {}).content || [];

  // Collect ALL occurrences of this AI-N: token from top-level paragraphs and
  // table cells. Process descending so lower-index paragraphs are unaffected
  // by higher-index changes.
  function _collectOccurrences(items) {
    var found = [];
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
        // Find AI-N: at position 0 or immediately after a soft-return char.
        var prefix = 'AI-' + N + ':';
        var tokenTextIdx = -1;
        if (fullText.substr(0, prefix.length) === prefix) {
          tokenTextIdx = 0;
        } else {
          for (var si = 0; si < fullText.length - prefix.length; si++) {
            var ch = fullText[si];
            if ((ch === '\n' || ch === '\r' || ch === '\v') &&
                fullText.substr(si + 1, prefix.length) === prefix) {
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
          var nlTextIdx       = tokenTextIdx === 0 ? -1 : tokenTextIdx - 1;
          var afterNlTextIdx  = nlTextIdx + 1; // == tokenTextIdx; == 0 at para start
          var tokenDocIdx = -1;
          var lineDocIdx  = -1;
          for (var ri = 0; ri < runMap.length; ri++) {
            var run    = runMap[ri];
            var runEnd = run.startTextIdx + run.len;
            if (tokenDocIdx < 0 && tokenTextIdx >= run.startTextIdx && tokenTextIdx < runEnd) {
              tokenDocIdx = run.startDocIdx + (tokenTextIdx - run.startTextIdx);
            }
            if (lineDocIdx < 0 && afterNlTextIdx >= run.startTextIdx && afterNlTextIdx <= runEnd) {
              lineDocIdx = run.startDocIdx + (afterNlTextIdx - run.startTextIdx);
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
            var nested = _collectOccurrences(cells[c].content || []);
            for (var ni = 0; ni < nested.length; ni++) found.push(nested[ni]);
          }
        }
      }
    }
    return found;
  }

  var occurrences = _collectOccurrences(content);

  if (occurrences.length === 0) {
    GasLogger.log('flush.warn', { msg: 'Paragraph not found', globalId: globalId });
    return false;
  }

    occurrences.sort(function(a, b) { return b.pStart - a.pStart; });

    var requests = [];
    for (var oi = 0; oi < occurrences.length; oi++) {
      var pEnd     = occurrences[oi].pEnd;
      // insertAt: for simple paragraphs this equals pStart; for soft-return
      // paragraphs it is the document index right after the preceding \n,
      // which also clears any image placed there by a previous flush.
      var insertAt = occurrences[oi].lineDocIdx !== undefined
                       ? occurrences[oi].lineDocIdx
                       : occurrences[oi].pStart;

      // Delete from insertAt to pEnd-1, preserving any contextual prefix text
      // and the mandatory trailing \n of the paragraph node.
      if (pEnd - 1 > insertAt) {
        requests.push({ deleteContentRange: { range: { startIndex: insertAt, endIndex: pEnd - 1 } } });
      }

      // Re-insert in reverse order (each inserts at insertAt, pushing prior content right).
      // Final line order: [image][AI-N: text][optional person chip][action text (status)]
      if (validEmail) {
        requests.push({ insertText: { text: ' ' + actionText + ' (' + status + ')', location: { index: insertAt } } });
        // insertPerson rejects any name field in personProperties — email only
        requests.push({ insertPerson: { personProperties: { email: assigneeEmail }, location: { index: insertAt } } });
      } else {
        requests.push({ insertText: { text: actionText + ' (' + status + ')', location: { index: insertAt } } });
      }
      requests.push({ insertText: { text: 'AI-' + N + ': ', location: { index: insertAt } } });
      requests.push({ insertInlineImage: {
        uri: imgUrl, location: { index: insertAt },
        objectSize: { height: { magnitude: 16, unit: 'PT' }, width: { magnitude: 16, unit: 'PT' } }
      }});
      requests.push({ updateTextStyle: {
        range: { startIndex: insertAt, endIndex: insertAt + 1 + tokenLen },
        textStyle: { link: { url: chipUrl } }, fields: 'link'
      }});
      requests.push(_chipBadgeStyleRequest(insertAt + 1, insertAt + 1 + tokenLen));
    }

    var batchResp = UrlFetchApp.fetch(baseUrl + docId + ':batchUpdate', {
      method: 'post', muteHttpExceptions: true,
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      payload: JSON.stringify({ requests: requests })
    });

    if (batchResp.getResponseCode() === 200) {
      GasLogger.log('flush.done', { globalId: globalId, status: status, copies: occurrences.length });
      return true;
    }

  GasLogger.log('flush.error', { msg: 'batchUpdate failed: HTTP ' + batchResp.getResponseCode(), body: batchResp.getContentText().substring(0, 300), globalId: globalId });
  return false;
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

function isOpen(status) {
  const words = ["open", "pending", "planned", "queued", "unstarted", "new"];
  return typeof status === "string" &&
    words.includes(status.trim().toLowerCase());
}

function isInProgress(status) {
  const words = ["active", "in-progress", "working", "running", "executing", "processing"];
  return typeof status === "string" &&
    words.includes(status.trim().toLowerCase());
}

function isWaiting(status) {
  const words = ["waiting", "blocked", "on-hold", "stalled", "paused"];
  return typeof status === "string" &&
    words.includes(status.trim().toLowerCase());
}

function isDelegated(status) {
  const words = ["delegated", "routed", "forwarded", "escalated", "handed-off", "transferred"];
  return typeof status === "string" &&
    words.includes(status.trim().toLowerCase());
}

function isClosed(status) {
  const words = ["done", "complete", "finished", "closed", "resolved", "finalized"];
  return typeof status === "string" &&
    words.includes(status.trim().toLowerCase());
}

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
  if (_ACTION_STATUS_IMAGES.hasOwnProperty(status)) return _ACTION_STATUS_IMAGES[status];
  if (isResolved(status)) return _ACTION_STATUS_IMAGES['Closed'];
  return _ACTION_DEFAULT_IMAGE;
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