/**
 * BoardListing.js — gts-79dw.4.3
 *
 * doPost action 'list_board_actions', body { idToken, boardFolderId,
 * filter: 'open'|'all', windowDays? }. Re-verifies the caller's access tier
 * via AccessControl.js's _resolveIdentityAndAccessTier on every call (no
 * trust-on-first-use, R8) and, for VIEW/EDIT tiers, lists every tracked
 * action across every document whose DocData.teamId matches the TeamData row
 * for boardFolderId. Bypasses WEBAPP_SECRET intentionally, same as
 * verify_and_resolve_access: callers are external GIS-verified identities.
 *
 * See docs/verified-board-portal-plan.md §3 (R9-R13) and this bead's `design`
 * field for the pre-code contract (entry point, log tag, output schema).
 */

var BOARD_LISTING_DEFAULT_WINDOW_DAYS = 60;

/**
 * @param {Object} payload { idToken, boardFolderId, filter, windowDays }
 * @returns {GoogleAppsScript.Content.TextOutput}
 */
function _handleListBoardActions(payload) {
  var idToken       = payload.idToken       || '';
  var boardFolderId = payload.boardFolderId || '';
  var filter        = payload.filter === 'all' ? 'all' : 'open';
  var windowDays     = Number(payload.windowDays);
  if (!(windowDays > 0)) windowDays = BOARD_LISTING_DEFAULT_WINDOW_DAYS;

  var resolved = _resolveIdentityAndAccessTier(idToken, boardFolderId);

  var actions = (resolved.tier === 'NONE')
    ? []
    : _listBoardActionsData(boardFolderId, filter, windowDays);

  GasLogger.log('webapp.board.list', {
    sub:    resolved.sub,
    tier:   resolved.tier,
    filter: filter,
    count:  actions.length
  });
  GasLogger.flush();

  return _jsonResponse({ tier: resolved.tier, actions: actions }, 200);
}

/**
 * Reads every Actions-sheet row belonging to a document under boardFolderId's
 * team (DocData.teamId matched via the TeamData row whose Folder Id ==
 * boardFolderId). Read-only.
 *
 * Default filter='open' excludes resolved (Closed/Delegated, isResolved())
 * rows entirely. filter='all' includes resolved rows only when their
 * Date Modified falls within the last windowDays days. Rows orphaned from
 * their document (Sync Status Deleted / Doc Not Found) are always excluded.
 *
 * @param {string} boardFolderId
 * @param {'open'|'all'} filter
 * @param {number} windowDays
 * @returns {Array<{globalId: string, docId: string, docName: string, status: string, assigneeName: string, lastUpdated: string}>}
 */
function _listBoardActionsData(boardFolderId, filter, windowDays) {
  var ss = _openActionSheetSpreadsheet();

  var teamId = '';
  var teamDataRows = _readTeamDataRows(ss);
  for (var t = 0; t < teamDataRows.length; t++) {
    if (teamDataRows[t].folderId === boardFolderId) {
      teamId = teamDataRows[t].teamId;
      break;
    }
  }
  if (!teamId) return [];

  var docNameById = {};
  var docDataRows = _readDocDataRows(ss);
  for (var d = 0; d < docDataRows.length; d++) {
    if (docDataRows[d].teamId !== teamId) continue;
    docNameById[docDataRows[d].fileId] = docDataRows[d].docName || '';
  }
  if (!Object.keys(docNameById).length) return [];

  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) return [];
  var lastRow = actionsSheet.getLastRow();
  if (lastRow < 2) return [];

  var cols = CONTRACT_SCHEMA.sheetAction.columnsByField;
  var data = actionsSheet.getRange(2, 1, lastRow - 1, SHEET_HEADERS.length).getValues();

  var cutoffMs = Date.now() - windowDays * 24 * 60 * 60 * 1000;
  var results = [];

  for (var i = 0; i < data.length; i++) {
    var row = data[i];
    var fileId = row[cols.file_id - 1];
    if (!Object.prototype.hasOwnProperty.call(docNameById, fileId)) continue;

    var syncStatus = row[cols.sync_status - 1];
    if (syncStatus === 'Deleted' || syncStatus === 'Doc Not Found') continue;

    var status   = row[cols.status - 1] || 'Open';
    var modified = row[cols.modified_date - 1];

    if (isResolved(status)) {
      if (filter !== 'all') continue;
      var modifiedMs = (modified instanceof Date) ? modified.getTime() : -1;
      if (modifiedMs < cutoffMs) continue;
    }

    results.push({
      globalId:     row[cols.global_id - 1] || '',
      docId:        fileId || '',
      docName:      docNameById[fileId] || '',
      status:       status,
      assigneeName: row[cols.assignee_name - 1] || '',
      lastUpdated:  (modified instanceof Date) ? modified.toISOString() : ''
    });
  }

  return results;
}
