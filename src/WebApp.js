/**
 * WebApp.js
 *
 * doGet  — self-registers the canonical WEBAPP_URL script property on first visit.
 * doPost — verifies WEBAPP_SECRET and routes action payloads.
 *
 * The Web App runs as USER_DEPLOYING (sheet owner) so the add-on sidebar
 * (which runs as the active user) can write to the restricted ActionSheet.
 */

/**
 * Returns the effective and active user emails for the current execution context.
 * Safe to call from any surface — catches and ignores unavailable identity APIs
 * (e.g. simple triggers where Session is restricted).
 *
 * On WebApp surfaces (doGet/doPost): eu = deployer, au = caller.
 * On add-on trigger surfaces (sidebar, chipHover, menu): eu = au = active user.
 *
 * @returns {{ eu: string, au: string }}
 */
// 1-based column numbers from the authoritative schema — use these everywhere
// instead of magic integers so a future column change only touches ContractSchema.js.
var _ACOL = CONTRACT_SCHEMA.sheetAction.columnsByField;

function _getIdentity() {
  var eu = ''; var au = '';
  try { eu = Session.getEffectiveUser().getEmail(); } catch (_) {}
  try { au = Session.getActiveUser().getEmail();    } catch (_) {}
  return { eu: eu, au: au, version: BUILD_INFO.version };
}

function doGet(e) {
  var url = ScriptApp.getService().getUrl();
  // Normalize org-specific URL to the canonical form stored in script properties
  url = url.replace(/https:\/\/script\.google\.com\/a\/[^\/]+\/macros\//, 'https://script.google.com/macros/');

  var props      = PropertiesService.getScriptProperties();
  var storedUrl  = props.getProperty('WEBAPP_URL') || '';
  var urlStatus;

  if (!storedUrl) {
    props.setProperty('WEBAPP_URL', url);
    urlStatus = 'registered (was unset)';
  } else if (storedUrl !== url) {
    props.setProperty('WEBAPP_URL', url);
    urlStatus = 'updated (was: ' + storedUrl + ')';
  } else {
    urlStatus = 'unchanged';
  }

  GasLogger.log('webapp.doGet', { url: url, urlStatus: urlStatus });
  if (e && e.parameter && e.parameter.deploy === '1') {
    // Distinct from webapp.doGet so "a deployment just went live" is its own
    // queryable Axiom event, not buried in every routine ping/visit.
    GasLogger.log('webapp.deploy', { url: url });
  }
  GasLogger.flush();

  // [PROBE] — note: hitting this URL also updates WEBAPP_URL (above) as a side effect.
  // Since getWebAppUrl() checks BUILD_INFO.webappUrl first, this only affects DEV context
  // where BUILD_INFO.webappUrl is empty. Test ordering (doGet.dev then doGet.test) leaves
  // WEBAPP_URL = /exec by the time any sync runs, so impact is contained.
  var _probeRun     = (e && e.parameter && e.parameter.probe_run)     || '';
  var _probeSurface = (e && e.parameter && e.parameter.probe_surface) || 'doGet';
  PROBE_setRunId(_probeRun);
  PROBE_log(_probeSurface, {
    queryString: (e && e.queryString)  || '',
    parameter:   JSON.stringify((e && e.parameter) || {}),
    pathInfo:    (e && e.pathInfo)     || ''
  });

  if (e && e.parameter && e.parameter.cmd === 'preview') {
    return _handlePreviewNotice(e);
  }

  if (e && e.parameter && e.parameter.cmd === 'teamview') {
    return _handleTeamView(e);
  }

  if (e && e.parameter && e.parameter.cmd === 'survey') {
    return _handleSurvey(e);
  }

  var params = (e && e.parameter) ? JSON.stringify(e.parameter) : '{}';
  return ContentService.createTextOutput(
    'GActionSheet ' + BUILD_INFO.version + '\n' +
    'Build:      ' + BUILD_INFO.buildDate + '\n' +
    'WebApp:     ' + url + '\n' +
    'URL:        ' + urlStatus + '\n' +
    '\n--- Request ---\n' +
    'queryString:   ' + ((e && e.queryString)  || '(none)') + '\n' +
    'parameter:     ' + params + '\n' +
    'pathInfo:      ' + ((e && e.pathInfo)     || '(none)') + '\n' +
    'contentLength: ' + ((e && e.contentLength != null) ? e.contentLength : '-1')
  );
}

/**
 * doGet ?cmd=preview&docId=<docId>&ain=AI-N — ADR-0017 Phase 1 anonymous chip
 * notice. Discloses only non-confidential metadata (doc name, team, AI-N,
 * status, doc link) and never the action text. Unknown/missing globalId
 * renders a non-leaking not-found variant.
 *
 * @param {Object} e doGet event; reads e.parameter.docId and e.parameter.ain.
 * @return {HtmlOutput}
 */
function _handlePreviewNotice(e) {
  var docId = (e && e.parameter && e.parameter.docId) || '';
  var ain   = (e && e.parameter && e.parameter.ain)   || '';
  var globalId = docId + '/' + ain;

  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  var row          = actionsSheet ? _loadExistingRowsByGlobalId(actionsSheet)[globalId] : null;

  GasLogger.log('webapp.preview.notice', { docId: docId, ain: ain, found: !!row });
  GasLogger.flush();

  if (!row) {
    return _renderPreviewNotice(null);
  }

  var docDataRow = _readDocDataRow(ss, docId);
  return _renderPreviewNotice({
    docName:  (docDataRow && docDataRow.docName) || '(unknown document)',
    teamName: (docDataRow && docDataRow.teamId) || '',
    actionId: ain,
    status:   row.status || 'Open',
    docLink:  'https://docs.google.com/document/d/' + encodeURIComponent(docId) + '/edit'
  });
}

/**
 * Renders the ADR-0017 Phase 1 notice page HTML. `model === null` renders the
 * non-leaking not-found variant. `model` must never carry action text.
 *
 * @param {?{docName: string, teamName: string, actionId: string, status: string, docLink: string}} model
 * @return {HtmlOutput}
 */
function _renderPreviewNotice(model) {
  var body;
  if (!model) {
    body =
      '<h1>Action not found</h1>' +
      '<p>This link no longer points to a known action.</p>';
  } else {
    var teamRow = model.teamName
      ? '<p><strong>Team:</strong> ' + _escapeHtml(model.teamName) + '</p>'
      : '';
    body =
      '<h1>' + _escapeHtml(model.actionId) + '</h1>' +
      '<p><strong>Document:</strong> ' + _escapeHtml(model.docName) + '</p>' +
      teamRow +
      '<p><strong>Status:</strong> ' + _escapeHtml(model.status) + '</p>' +
      '<p><a href="' + _escapeHtml(model.docLink) + '" target="_blank">' +
        'Open the document to view or edit this action</a></p>';
  }

  return _renderBrandedPage('GActionSheet', body);
}

/**
 * Wraps a body fragment in the suite-branded HTML shell (logo + suite name
 * header, shared styling) so every anonymous WebApp page — chip preview
 * notice, team view — carries consistent branding from the single source of
 * truth in Constants.js (generated by assets/brand-NUUTS/deploy-brand.sh)
 * rather than each page hard-coding its own name/logo.
 *
 * @param {string} title document <title> / HtmlOutput title.
 * @param {string} bodyHtml pre-escaped HTML fragment for the page body.
 * @return {HtmlOutput}
 */
function _renderBrandedPage(title, bodyHtml) {
  var html =
    '<!DOCTYPE html><html><head><meta charset="utf-8"><title>' + _escapeHtml(title) + '</title>' +
    '<style>body{font-family:Arial,sans-serif;max-width:560px;margin:40px auto;' +
    'padding:0 16px;color:#202124}h1{font-size:1.25rem}a{color:#1a73e8}' +
    '.brand{display:flex;align-items:center;gap:8px;margin-bottom:24px}' +
    '.brand img{height:28px}.brand span{font-size:0.95rem;color:#5f6368}' +
    'table{border-collapse:collapse;width:100%}th,td{padding:6px 8px;text-align:left;' +
    'border-bottom:1px solid #e0e0e0}</style>' +
    '</head><body>' +
    '<div class="brand"><img src="' + _NORTHLAKE_UU_EMBLEM_URL + '" alt=""><span>' +
      _escapeHtml(_NORTHLAKE_UU_SUITE_NAME) + '</span></div>' +
    bodyHtml +
    '</body></html>';

  return HtmlService.createHtmlOutput(html).setTitle(title);
}

/**
 * doGet ?cmd=teamview&team=<teamId> — branded team summary page. Sidebar Team
 * link fallback target when TeamData has no Team Link of its own
 * (_buildTeamViewUrl, SyncManager.js). Discloses the team's contact info and,
 * for every document with at least one open action, the document name (linked
 * to open the doc), open count, and resolved count — never action text.
 *
 * @param {Object} e doGet event; reads e.parameter.team.
 * @return {HtmlOutput}
 */
function _handleTeamView(e) {
  var teamId = (e && e.parameter && e.parameter.team) || '';

  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var teamRows = _readTeamDataRows(ss);
  var teamRow = null;
  for (var i = 0; i < teamRows.length; i++) {
    if (teamRows[i].teamId === teamId) { teamRow = teamRows[i]; break; }
  }

  GasLogger.log('webapp.teamview', { team: teamId, found: !!teamRow });
  GasLogger.flush();

  if (!teamRow) {
    return _renderTeamView(null);
  }

  var docRows = _readDocDataRows(ss).filter(function (d) {
    if (d.teamId !== teamId) return false;
    var openCount = (Number(d.actionCount) || 0) - (Number(d.resolvedCount) || 0);
    return openCount > 0;
  });
  docRows.sort(function (a, b) {
    return String(a.docName) < String(b.docName) ? -1 : (String(a.docName) > String(b.docName) ? 1 : 0);
  });

  return _renderTeamView({
    teamId:  teamId,
    contact: teamRow.contact || '',
    docs: docRows.map(function (d) {
      return {
        docName:       d.docName || '(untitled document)',
        docLink:       'https://docs.google.com/document/d/' + encodeURIComponent(d.fileId) + '/edit',
        openCount:     (Number(d.actionCount) || 0) - (Number(d.resolvedCount) || 0),
        resolvedCount: Number(d.resolvedCount) || 0
      };
    })
  });
}

/**
 * Renders the team-view page HTML. `model === null` renders the non-leaking
 * not-found variant (unknown teamId).
 *
 * @param {?{teamId: string, contact: string, docs: Array<{docName: string, docLink: string, openCount: number, resolvedCount: number}>}} model
 * @return {HtmlOutput}
 */
function _renderTeamView(model) {
  var body;
  if (!model) {
    body =
      '<h1>Team not found</h1>' +
      '<p>This link no longer points to a known team.</p>';
  } else {
    var contactRow = model.contact
      ? '<p><strong>Contact:</strong> ' + _escapeHtml(model.contact) + '</p>'
      : '';

    var rows = model.docs.map(function (d) {
      return '<tr><td><a href="' + _escapeHtml(d.docLink) + '" target="_blank">' +
        _escapeHtml(d.docName) + '</a></td><td>' + d.openCount + '</td><td>' + d.resolvedCount + '</td></tr>';
    }).join('');

    var table = model.docs.length
      ? '<table><thead><tr><th>Document</th><th>Open</th><th>Resolved</th></tr></thead>' +
        '<tbody>' + rows + '</tbody></table>'
      : '<p>No documents with open actions.</p>';

    body =
      '<h1>Team: ' + _escapeHtml(model.teamId) + '</h1>' +
      contactRow +
      table;
  }

  return _renderBrandedPage('GActionSheet — Team View', body);
}

/**
 * Escapes HTML special characters for safe interpolation into the notice page.
 */
function _escapeHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
}

function doPost(e) {
  var payload;
  try {
    payload = JSON.parse(e.postData.contents);
  } catch (ex) {
    return _jsonResponse({ error: 'bad JSON' }, 200);
  }

  // Log identity and caller context for every request so errors can be
  // attributed to a specific user and surface without needing PROBE.
  var _id = _getIdentity();
  GasLogger.log('webapp.request', {
    action:  payload.action || '(unknown)',
    eu:      _id.eu,
    au:      _id.au,
    caller:  payload.caller || {},
    version: BUILD_INFO.version
  });

  // [PROBE] — gated only on probe_run presence; bypasses secret gate intentionally.
  if (payload.action === 'probe' && payload.probe_run) {
    PROBE_setRunId(payload.probe_run);
    PROBE_log(payload.probe_surface || 'doPost', {
      action:        'probe',
      senderVersion: payload.probe_version || ''
    });
    return _jsonResponse({ probe: 'ok', version: BUILD_INFO.version }, 200);
  }

  // Test-token-gated routes — authenticated by per-deployment TEST_TOKEN, not WEBAPP_SECRET.
  // Checked before the WEBAPP_SECRET gate. Includes run_fixture (fixture dispatcher) and
  // ATDD test-support routes from ContractSchema.js webApp.testRouteNames (bead .9) and
  // AtddContracts.js sessionRouteNames (bead .8).
  if (payload.action === 'run_fixture') {
    return _handleRunFixture(payload);
  }
  if (payload.action === 'edit_action_row') {
    return _handleEditActionRow(payload);
  }
  if (payload.action === 'find_sheet_actions') {
    return _handleFindSheetActions(payload);
  }
  if (payload.action === 'begin_journey_session' ||
      payload.action === 'end_journey_session') {
    return _handleJourneySession(payload);
  }
  if (payload.action === 'append_doc_paragraph') {
    return _handleAppendDocParagraph(payload);
  }
  if (payload.action === 'verify_action_rows') {
    return _handleVerifyActionRows(payload);
  }
  if (payload.action === 'verify_chip_integrity') {
    return _handleVerifyChipIntegrity(payload);
  }
  if (payload.action === 'import_selected_for_test') {
    return _handleImportSelectedForTest(payload);
  }
  if (payload.action === 'forward_action_rows_test') {
    return _handleForwardActionRowsAtdd(payload);
  }
  // patch_action_status and delete_action_row are production routes (WEBAPP_SECRET-gated
  // when called by the add-on). When called by the ATDD harness they arrive with a
  // testToken and snake_case field names per ContractSchema.js messages (§16.11 #3).
  if (payload.testToken && payload.action === 'patch_action_status') {
    return _handlePatchActionStatusAtdd(payload);
  }
  if (payload.testToken && payload.action === 'delete_action_row') {
    return _handleDeleteActionRowAtdd(payload);
  }

  var expected = PropertiesService.getScriptProperties().getProperty('WEBAPP_SECRET');
  if (!expected || payload.secret !== expected) {
    return ContentService.createTextOutput('unauthorized').setMimeType(ContentService.MimeType.TEXT);
  }

  if (payload.clientVersion && payload.clientVersion !== BUILD_INFO.version) {
    GasLogger.log('webapp.version.mismatch', { client: payload.clientVersion, server: BUILD_INFO.version });
  }

  if (payload.action === 'set_test_token') {
    return _handleSetTestToken(payload);
  }

  if (payload.action === 'set_axiom_config') {
    return _handleSetAxiomConfig(payload);
  }

  // Deployment health-check routes — called by manage-deployments.js after deploy:test.
  if (payload.action === 'get_test_config') {
    var props = PropertiesService.getScriptProperties();
    return _jsonResponse({
      testDocId:        props.getProperty('TEST_DOC_ID')          || '',
      testSheetId:      props.getProperty('TEST_SHEET_ID')        || '',
      gasLoggerFolderId: props.getProperty('GAS_LOGGER_FOLDER_ID') || '',
      webappUrl:        props.getProperty('WEBAPP_URL')           || '',
      version:          BUILD_INFO.version
    }, 200);
  }

  if (payload.action === 'bootstrap') {
    bootstrap();
    GasLogger.flush();
    return _jsonResponse({ ok: true, version: BUILD_INFO.version }, 200);
  }

  var result;
  if (payload.action === 'upsert_action_rows') {
    result = _handleUpsertActionRows(payload);
  } else if (payload.action === 'sync_action_rows') {
    result = _handleSyncActionRows(payload);
  } else if (payload.action === 'verify_action_rows') {
    result = _handleVerifyActionRows(payload);
  } else if (payload.action === 'mark_doc_not_found') {
    result = _handleMarkDocNotFound(payload);
  } else if (payload.action === 'delete_action_row') {
    result = _handleDeleteActionRow(payload);
  } else if (payload.action === 'patch_action_status') {
    result = _handlePatchActionStatus(payload);
  } else if (payload.action === 'list_importable_actions') {
    result = _handleListImportableActions(payload);
  } else if (payload.action === 'forward_action_rows') {
    result = _handleForwardActionRows(payload);
  } else {
    // Legacy POC — retained for diagnostics
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    sheet.appendRow([new Date(), payload.email || '', payload.message || '']);
    result = ContentService.createTextOutput('ok');
  }

  GasLogger.flush();
  return result;
}

// ---------------------------------------------------------------------------
// set_test_token handler  (deployment script only — requires WEBAPP_SECRET)
// ---------------------------------------------------------------------------

/**
 * Stores a per-deployment test token in Script Properties.
 * Called once by the deployment script after each `npm run deploy:test`.
 * The token expires at expiresAt (ISO string); run_fixture rejects expired tokens.
 *
 * Payload shape:
 *   { secret, action: 'set_test_token', testToken: '<uuid>', expiresAt: '<ISO>' }
 *
 * Response shape:
 *   { ok: true, expiresAt }
 */
function _handleSetTestToken(payload) {
  var testToken = payload.testToken || '';
  var expiresAt = payload.expiresAt || '';
  if (!testToken) {
    return _jsonResponse({ error: 'testToken required' });
  }
  var props = PropertiesService.getScriptProperties();
  props.setProperty('TEST_TOKEN', testToken);
  props.setProperty('TEST_TOKEN_EXPIRES', expiresAt);
  GasLogger.log('test.token.set', { expiresAt: expiresAt });
  GasLogger.flush();
  return _jsonResponse({ ok: true, expiresAt: expiresAt });
}

// ---------------------------------------------------------------------------
// set_axiom_config handler  (deployment script only — requires WEBAPP_SECRET)
// ---------------------------------------------------------------------------

/**
 * Stores Axiom ingest config in Script Properties so GasLogger.flush() can POST
 * server-side events there (docs/atdd/journey-logging-design.md §4.3).
 * Called once by the deployment script after each `npm run deploy:test`, same
 * pattern as set_test_token.
 *
 * Payload shape:
 *   { secret, action: 'set_axiom_config', axiomToken: '<token>', axiomDataset: '<name>' }
 *
 * Response shape:
 *   { ok: true }
 */
function _handleSetAxiomConfig(payload) {
  var axiomToken = payload.axiomToken || '';
  var axiomDataset = payload.axiomDataset || '';
  if (!axiomToken || !axiomDataset) {
    return _jsonResponse({ error: 'axiomToken and axiomDataset required' });
  }
  var props = PropertiesService.getScriptProperties();
  props.setProperty('AXIOM_TOKEN', axiomToken);
  props.setProperty('AXIOM_DATASET', axiomDataset);
  GasLogger.log('axiom.config.set', { dataset: axiomDataset });
  GasLogger.flush();
  return _jsonResponse({ ok: true });
}

// ---------------------------------------------------------------------------
// upsert_action_rows handler
// ---------------------------------------------------------------------------

/**
 * Inserts or updates action rows in the "Actions" sheet.
 * Existing rows (matched by globalId) have assigneeEmail, assigneeName, actionText,
 * status, and dateModified updated in place when values differ. Absent rows are appended.
 *
 * Payload shape:
 *   { secret, action: 'upsert_action_rows', docUrl, docTitle, rows: [
 *     { globalId, assigneeEmail, assigneeName, actionText, status, createdDate }
 *   ] }
 * createdDate is optional — on insert, falls back to now if absent. Used by
 * import (AC-2) to preserve the original action's created_date on the clone.
 *
 * Date Created / Date Modified contract (see also DESIGN.md §ActionSheet —
 * Date Created / Date Modified contract):
 * - Date Created is a property of the ACTION, not of its current document.
 *   Importing/forwarding relocates an action to another doc; it does not
 *   modify it (text/assignee/status are unchanged), so Date Created must
 *   survive the move — hence createdDate is threaded through on insert
 *   instead of defaulting to now.
 * - Date Modified should, by the same logic, also be preserved on import
 *   (an import is not a content change). It currently is NOT — the insert
 *   branch below always stamps `now`. Known gap, not fixed here.
 *
 * Response shape:
 *   { inserted: <count>, updated: <count> }
 */
function _handleUpsertActionRows(payload) {
  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return _jsonResponse({ error: 'Actions sheet not found' });
  }

  var docUrl   = payload.docUrl   || '';
  var docTitle = payload.docTitle || 'Untitled';
  var rows     = payload.rows     || [];

  var existingMap = _loadExistingRowsByGlobalId(actionsSheet);

  var inserted = 0;
  var updated  = 0;
  var now      = new Date();

  WriteGuard.wrapPersistent(function () {
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      if (!row.globalId) continue;

      var existing = existingMap[row.globalId];
      if (existing) {
        var r         = existing.rowIndex;
        var newId     = _extractActionId(row.globalId);
        var newEmail  = row.assigneeEmail || existing.assigneeEmail;
        var newName   = row.assigneeName  || existing.assigneeName;
        var newText   = row.actionText    || existing.action;
        var newStatus = row.status        || existing.status;
        var changed = newId    !== existing.id           ||
                      newEmail !== existing.assigneeEmail ||
                      newName  !== existing.assigneeName  ||
                      newText  !== existing.action        ||
                      newStatus !== existing.status;
        if (changed) {
          actionsSheet.getRange(r, _ACOL.action_id).setValue(newId);
          actionsSheet.getRange(r, _ACOL.assignee_email).setValue(newEmail);
          actionsSheet.getRange(r, _ACOL.assignee_name).setValue(newName);
          actionsSheet.getRange(r, _ACOL.action_text).setValue(newText);
          actionsSheet.getRange(r, _ACOL.status).setValue(newStatus);
          actionsSheet.getRange(r, _ACOL.modified_date).setValue(now);
          updated++;
        }
      } else {
        var fileId     = parseGlobalId(row.globalId).docId;
        var docFormula = '=HYPERLINK("' + docUrl + '","' + _escapeQuotes(docTitle) + '")';
        var createdDate = row.createdDate ? new Date(row.createdDate) : now;
        actionsSheet.appendRow([
          row.globalId,
          fileId,
          _extractActionId(row.globalId),
          row.assigneeEmail || '',
          row.assigneeName  || '',
          row.actionText    || '',
          row.status        || 'Open',
          docFormula,
          createdDate,
          now,
          ''  // Sync Status — blank on insert
        ]);
        inserted++;
      }
    }
  });

  GasLogger.log('upsert.complete', { inserted: inserted, updated: updated, rows: rows.map(function(r) { return { globalId: r.globalId, status: r.status }; }) });
  return _jsonResponse({ inserted: inserted, updated: updated });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Returns { globalId: { id, ... } } for every non-blank row in actionsSheet.
 */
function _loadExistingRowsByGlobalId(actionsSheet) {
  var lastRow = actionsSheet.getLastRow();
  if (lastRow < 2) return {};

  var data   = actionsSheet.getRange(2, 1, lastRow - 1, SHEET_HEADERS.length).getValues();
  var result = {};

  for (var i = 0; i < data.length; i++) {
    var globalId = data[i][0];
    if (!globalId) continue;
    result[globalId] = {
      rowIndex:      i + 2,
      fileId:        data[i][_ACOL.file_id        - 1],
      id:            data[i][_ACOL.action_id      - 1],
      assigneeEmail: data[i][_ACOL.assignee_email - 1],
      assigneeName:  data[i][_ACOL.assignee_name  - 1] || '',
      action:        data[i][_ACOL.action_text    - 1],
      status:        data[i][_ACOL.status         - 1],
      dateModified:  data[i][_ACOL.modified_date  - 1] instanceof Date ? data[i][_ACOL.modified_date - 1] : null,
      syncStatus:    data[i][_ACOL.sync_status    - 1] || ''
    };
  }

  return result;
}

/**
 * Parses a globalId into its components.
 * globalId format: {docFileId}/AI-{N}
 * Returns { docId, N, actionId } where actionId = 'AI-{N}'.
 * If the format is unexpected, N is NaN and actionId/docId are empty.
 */
function parseGlobalId(globalId) {
  var parts = (globalId || '').split('/AI-');
  if (parts.length < 2) return { docId: '', N: NaN, actionId: globalId || '' };
  return { docId: parts[0], N: parseInt(parts[1], 10), actionId: 'AI-' + parts[1] };
}

function _extractActionId(globalId) {
  return parseGlobalId(globalId).actionId;
}

function _rowIdentityKey(assigneeEmail, action, status) {
  return [
    assigneeEmail || '',
    action || '',
    status || 'Open'
  ].join('\u0001');
}

/**
 * Bidirectional sync handler.  Compares the doc state snapshot against the
 * current ActionSheet rows using the last-sync timestamp as the conflict anchor.
 *
 * Payload shape:
 *   { secret, action: 'sync_action_rows', docUrl, docTitle,
 *     docState: [{ globalId, assigneeEmail, assigneeName, actionText, status }] }
 *
 * Response shape:
 *   { upserted, updated, sheetWins: [{ globalId, action, status, assigneeEmail }] }
 */
function _handleSyncActionRows(payload) {
  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return _jsonResponse({ error: 'Actions sheet not found' });
  }

  // §16.11 #4: drain ACTION_SHEET_QUEUE before reconciliation so all pending
  // chip-click upserts are applied before the sync response is returned.
  var queueDrained = 0;
  (function () {
    var props = PropertiesService.getScriptProperties();
    var lock  = LockService.getScriptLock();
    var snapshot;
    lock.waitLock(5000);
    try {
      snapshot = JSON.parse(props.getProperty('ACTION_SHEET_QUEUE') || '[]');
      props.setProperty('ACTION_SHEET_QUEUE', '[]');
    } finally {
      lock.releaseLock();
    }
    for (var qi = 0; qi < snapshot.length; qi++) {
      var q = snapshot[qi];
      _handleUpsertActionRows({
        action:   'upsert_action_rows',
        docUrl:   q.docUrl,
        docTitle: q.docTitle,
        rows: [{ globalId: q.globalId, actionText: q.actionText,
                 assigneeEmail: q.assigneeEmail, assigneeName: q.assigneeName,
                 status: q.status }]
      });
    }
    queueDrained = snapshot.length;
  })();

  var docUrl              = payload.docUrl   || '';
  var docTitle            = payload.docTitle || 'Untitled';
  var docId               = payload.docId    || '';
  var docState            = payload.docState || [];
  var allDocGlobalIds = payload.allDocGlobalIds || [];

  // Build a set for O(1) membership checks.
  var activeGlobalIdSet = {};
  for (var ai = 0; ai < allDocGlobalIds.length; ai++) {
    activeGlobalIdSet[allDocGlobalIds[ai]] = true;
  }

  var existingMap = _loadExistingRowsByGlobalId(actionsSheet);
  var now         = new Date();
  var upserted    = 0;
  var updated     = 0;
  var sheetWins   = [];
  var docStateByGlobalId  = {};
  var docStateIdentitySet = {};

  for (var dsi = 0; dsi < docState.length; dsi++) {
    var docRow = docState[dsi];
    docStateByGlobalId[docRow.globalId] = true;
    docStateIdentitySet[_rowIdentityKey(docRow.assigneeEmail, docRow.actionText, docRow.status)] = true;
  }

  // Load document-formula column for orphan detection (need docId to match rows to this doc).
  var lastRow      = actionsSheet.getLastRow();
  var formulasCol7 = lastRow >= 2
    ? actionsSheet.getRange(2, _ACOL.document_formula, lastRow - 1, 1).getFormulas()
    : [];
  var duplicateRowIndexes = [];

  WriteGuard.wrapPersistent(function () {
    for (var i = 0; i < docState.length; i++) {
      var row      = docState[i];
      var existing = existingMap[row.globalId];

      if (!existing) {
        var syncFileId = parseGlobalId(row.globalId).docId;
        var docFormula = '=HYPERLINK("' + docUrl + '","' + _escapeQuotes(docTitle) + '")';
        actionsSheet.appendRow([
          row.globalId,
          syncFileId,
          _extractActionId(row.globalId),
          row.assigneeEmail || '',
          row.assigneeName  || '',
          row.actionText    || '',
          row.status        || 'Open',
          docFormula,
          now,
          now,
          ''  // Sync Status — blank on insert
        ]);
        upserted++;
      } else if (existing.syncStatus === 'Dirty') {
        // Sheet was edited (onActionSheetEdit set Sync Status = 'Dirty') — sheet wins.
        // SyncManager will apply the sheet values back to the doc floating action.
        sheetWins.push({
          globalId:      row.globalId,
          assigneeEmail: existing.assigneeEmail,
          assigneeName:  existing.assigneeName,
          action:        existing.action,
          status:        existing.status
        });
        // Row synced successfully — clear any prior Sync Status.
        actionsSheet.getRange(existing.rowIndex, _ACOL.sync_status).setValue('');
      } else {
        // Doc is authoritative — update sheet row only when content values differ.
        var rowIdx     = existing.rowIndex;
        var docFormula = '=HYPERLINK("' + docUrl + '","' + _escapeQuotes(docTitle) + '")';
        var correctId = _extractActionId(row.globalId);
        if (existing.id !== correctId) {
          actionsSheet.getRange(rowIdx, _ACOL.action_id).setValue(correctId);
        }
        if (existing.assigneeEmail !== row.assigneeEmail ||
            existing.assigneeName !== row.assigneeName ||
            existing.action !== row.actionText ||
            existing.status !== row.status) {
          actionsSheet.getRange(rowIdx, _ACOL.assignee_email).setValue(row.assigneeEmail || '');
          actionsSheet.getRange(rowIdx, _ACOL.assignee_name).setValue(row.assigneeName  || '');
          actionsSheet.getRange(rowIdx, _ACOL.action_text).setValue(row.actionText || '');
          actionsSheet.getRange(rowIdx, _ACOL.status).setValue(row.status || 'Open');
          actionsSheet.getRange(rowIdx, _ACOL.modified_date).setValue(now);
          updated++;
        }
        var fIdx = rowIdx - 2;
        var existingFormula = (fIdx >= 0 && fIdx < formulasCol7.length) ? formulasCol7[fIdx][0] : '';
        if (existingFormula !== docFormula) {
          actionsSheet.getRange(rowIdx, _ACOL.document_formula).setFormula(docFormula);
        }
        if (existing.syncStatus !== '') {
          actionsSheet.getRange(rowIdx, _ACOL.sync_status).setValue('');
        }
      }
    }

    // Detect orphaned rows: rows for this doc whose globalId is gone from the doc.
    if (docId) {
      for (var gId in existingMap) {
        if (docStateByGlobalId[gId]) continue;
        var entry = existingMap[gId];
        var fIdx  = entry.rowIndex - 2; // formulasCol7 is 0-based from row 2
        var formula = (fIdx >= 0 && fIdx < formulasCol7.length) ? formulasCol7[fIdx][0] : '';
        if (formula.indexOf(docId) === -1) continue; // belongs to a different doc

        // If the current doc still has the same action state under a different
        // globalId, this row is a stale duplicate left behind by a re-anchor.
        var identityKey = _rowIdentityKey(entry.assigneeEmail, entry.action, entry.status);
        if (docStateIdentitySet[identityKey]) {
          duplicateRowIndexes.push(entry.rowIndex);
          continue;
        }

        if (activeGlobalIdSet[gId]) continue; // still in the doc

        actionsSheet.getRange(entry.rowIndex, _ACOL.sync_status).setValue('Deleted');
        GasLogger.log('sync.info', { msg: 'Sync Status — Deleted', row: entry.rowIndex, globalId: gId });
      }

      duplicateRowIndexes.sort(function (a, b) { return b - a; });
      for (var dri = 0; dri < duplicateRowIndexes.length; dri++) {
        actionsSheet.deleteRow(duplicateRowIndexes[dri]);
      }
    }

    // Refresh DocData.action_count / resolved_count from the just-reconciled
    // Actions sheet (GTaskSheet-zc21) — counts exclude rows orphaned from this
    // doc (Deleted/Doc Not Found) so they track the document's live floating
    // actions, preserving doc_name/last_sync_time/team_id/sync_status.
    if (docId) {
      var dcLastRow = actionsSheet.getLastRow();
      var dcActionCount   = 0;
      var dcResolvedCount = 0;
      if (dcLastRow >= 2) {
        var dcData = actionsSheet.getRange(2, 1, dcLastRow - 1, SHEET_HEADERS.length).getValues();
        var _DCF   = CONTRACT_SCHEMA.sheetAction.columnsByField;
        for (var dci = 0; dci < dcData.length; dci++) {
          var dcGlobalId = String(dcData[dci][_DCF.global_id - 1] || '');
          if (dcGlobalId.indexOf(docId + '/') !== 0) continue;
          var dcSyncStatus = dcData[dci][_DCF.sync_status - 1];
          if (dcSyncStatus === 'Deleted' || dcSyncStatus === 'Doc Not Found') continue;
          dcActionCount++;
          if (isResolved(dcData[dci][_DCF.status - 1])) dcResolvedCount++;
        }
      }
      var dcExisting = _readDocDataRow(ss, docId);
      _getOrUpsertDocDataRow(
        ss, docId,
        dcExisting ? dcExisting.docName : (docTitle || ''),
        dcExisting ? dcExisting.lastSyncTime : now,
        dcExisting ? dcExisting.teamId : '',
        dcExisting ? dcExisting.syncStatus : '',
        dcActionCount, dcResolvedCount
      );
    }
  });

  return _jsonResponse({ ok: true, upserted: upserted, updated: updated, sheetWins: sheetWins, queueDrained: queueDrained });
}

/**
 * Returns ActionSheet rows for a single document without mutating any data.
 *
 * Payload shape:
 *   { secret, action: 'verify_action_rows', docUrl }
 *
 * Response shape:
 *   { rows: [{ globalId, id, assigneeEmail, assigneeName, action, status }] }
 */
function _handleVerifyActionRows(payload) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return _jsonResponse({ error: 'Actions sheet not found', rows: [] });
  }
  // testToken path sends docId; WEBAPP_SECRET path sends docUrl — normalise to URL form
  var docUrl = payload.docUrl ||
    (payload.docId ? 'https://docs.google.com/document/d/' + payload.docId + '/edit' : '');
  return _jsonResponse({
    rows: _loadRowsForDocUrl(actionsSheet, docUrl)
  });
}

/**
 * Walks every paragraph in the Docs REST JSON for the given doc.
 * For each AI-N: paragraph checks:
 *   1. Leading inlineObjectElement sourceUri matches a brand-NUUTS status image.
 *   2. AI-N: textRun link.url contains the expected globalId.
 *   3. Trailing (Status) token is consistent with the icon status.
 *
 * Payload: { testToken, action: 'verify_chip_integrity', docId }
 * Response: { violations: [{ paragraph, issue }], checked_count: number }
 */
function _handleVerifyChipIntegrity(payload) {
  var docId = payload.docId || '';
  if (!docId) return _jsonResponse({ error: 'docId required', violations: [] });

  var token = ScriptApp.getOAuthToken();
  var baseUrl = 'https://docs.googleapis.com/v1/documents/';

  var resp = UrlFetchApp.fetch(
    baseUrl + docId + '?fields=body.content(paragraph/elements(inlineObjectElement,textRun)),inlineObjects',
    { headers: { Authorization: 'Bearer ' + token }, muteHttpExceptions: true }
  );
  if (resp.getResponseCode() !== 200) {
    return _jsonResponse({ error: 'Docs API error: ' + resp.getResponseCode(), violations: [] });
  }

  var doc = JSON.parse(resp.getContentText());
  var content = (doc.body || {}).content || [];
  var inlineObjects = doc.inlineObjects || {};

  // Build reverse map: imageUrl → status label (lowercase)
  var urlToStatus = {};
  var statusKeys = Object.keys(_ACTION_STATUS_IMAGES);
  for (var si = 0; si < statusKeys.length; si++) {
    urlToStatus[_ACTION_STATUS_IMAGES[statusKeys[si]]] = statusKeys[si].toLowerCase();
  }
  urlToStatus[_ACTION_DEFAULT_IMAGE] = 'unknown'; // status-unknown.png = any non-standard status

  var violations = [];
  var checkedCount = 0;

  for (var i = 0; i < content.length; i++) {
    var para = content[i].paragraph;
    if (!para) continue;
    var elements = para.elements || [];

    // Build plain text from textRuns only to detect AI-N: token
    var builtText = '';
    for (var j = 0; j < elements.length; j++) {
      if (elements[j].textRun) builtText += elements[j].textRun.content || '';
    }
    var plainText = builtText.replace(/\n$/, '');
    var tokenMatch = plainText.match(/^AI-(\d+):\s/);
    if (!tokenMatch) continue;

    var N = tokenMatch[1];
    checkedCount++;
    var expectedGlobalId = docId + '/AI-' + N;

    // Check 1: leading element must be inlineObjectElement with brand-NUUTS sourceUri
    var firstEl = elements[0] || {};
    if (!firstEl.inlineObjectElement) {
      violations.push({ paragraph: 'AI-' + N, issue: 'no leading inlineObjectElement' });
      continue;
    }
    var inlineObjId = firstEl.inlineObjectElement.inlineObjectId || '';
    var inlineObj = inlineObjects[inlineObjId] || {};
    var sourceUri = (((inlineObj.inlineObjectProperties || {}).embeddedObject || {}).imageProperties || {}).sourceUri || '';
    var iconStatus = Object.prototype.hasOwnProperty.call(urlToStatus, sourceUri) ? urlToStatus[sourceUri] : null;
    if (iconStatus === null) {
      violations.push({ paragraph: 'AI-' + N, issue: 'sourceUri not a brand-NUUTS image: ' + sourceUri });
    }

    // Check 2: AI-N: textRun (element[1]) link.url must resolve to the
    // expected globalId — via either the current docId+ain params or the
    // legacy globalId= param (_globalIdFromChipUrl accepts both).
    var tokenEl = elements[1] || {};
    var linkUrl = (((tokenEl.textRun || {}).textStyle || {}).link || {}).url || '';
    var actualGlobalId = linkUrl ? _globalIdFromChipUrl(linkUrl) : null;
    if (actualGlobalId !== expectedGlobalId) {
      violations.push({ paragraph: 'AI-' + N, issue: 'AI-N: link.url globalId mismatch — expected ' + expectedGlobalId + ', got: ' + linkUrl });
    }

    // Check 3: trailing (Status) token must be consistent with icon
    if (iconStatus !== null) {
      var statusMatch = plainText.match(/\(([^)]*)\)\s*$/);
      if (statusMatch) {
        var docStatus = statusMatch[1].trim().toLowerCase();
        if (iconStatus !== 'other' && iconStatus !== docStatus) {
          violations.push({
            paragraph: 'AI-' + N,
            issue: 'icon status "' + iconStatus + '" != doc status "' + docStatus + '"'
          });
        }
        // iconStatus === 'other' accepts any non-standard status (e.g. 'backlog')
      }
    }
  }

  GasLogger.log('verify.chipIntegrity.done', { docId: docId, checked: checkedCount, violations: violations.length });
  return _jsonResponse({ violations: violations, checked_count: checkedCount });
}

function _loadRowsForDocUrl(actionsSheet, docUrl) {
  var lastRow = actionsSheet.getLastRow();
  if (lastRow < 2) {
    return [];
  }

  var targetDocId = _extractDocIdFromString(docUrl);
  var numRows = lastRow - 1;
  var data = actionsSheet.getRange(2, 1, numRows, SHEET_HEADERS.length).getValues();
  var formulas = actionsSheet.getRange(2, _ACOL.document_formula, numRows, 1).getFormulas();
  var rows = [];

  for (var i = 0; i < data.length; i++) {
    var docFormula = formulas[i][0] || '';
    if (docUrl && _extractDocIdFromString(docFormula) !== targetDocId) {
      continue;
    }

    rows.push({
      globalId:     data[i][_ACOL.global_id      - 1] || '',
      fileId:       data[i][_ACOL.file_id         - 1] || '',
      id:           data[i][_ACOL.action_id       - 1] || '',
      assigneeEmail:data[i][_ACOL.assignee_email  - 1] || '',
      assigneeName: data[i][_ACOL.assignee_name   - 1] || '',
      action:       data[i][_ACOL.action_text     - 1] || '',
      status:       data[i][_ACOL.status          - 1] || 'Open'
    });
  }

  return rows;
}

/**
 * Marks all Actions rows whose Document formula references docId as
 * 'Doc Not Found' in the Sync Status column.
 *
 * Payload shape: { secret, action: 'mark_doc_not_found', docId }
 */
function _handleMarkDocNotFound(payload) {
  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return _jsonResponse({ error: 'Actions sheet not found', marked: 0 });
  }

  var docId   = payload.docId || '';
  var lastRow = actionsSheet.getLastRow();
  if (!docId || lastRow < 2) {
    return _jsonResponse({ marked: 0 });
  }

  var numRows      = lastRow - 1;
  var formulasCol7 = actionsSheet.getRange(2, _ACOL.document_formula, numRows, 1).getFormulas();
  var marked       = 0;

  WriteGuard.wrapPersistent(function () {
    // Stamp the same detection-time timestamp on every row for this docId so
    // they age out of ArchiveManager's 24h Doc Not Found threshold together,
    // not independently (GTaskSheet-4tnr) — a doc going missing is a per-doc
    // event, not a per-row one.
    var now = new Date();
    for (var i = 0; i < formulasCol7.length; i++) {
      var formula = formulasCol7[i][0] || '';
      if (formula.indexOf(docId) === -1) continue;
      actionsSheet.getRange(i + 2, _ACOL.sync_status).setValue('Doc Not Found');
      actionsSheet.getRange(i + 2, _ACOL.modified_date).setValue(now);
      marked++;
    }

    if (marked > 0) {
      // Mirror the Doc Not Found status to DocData (GTaskSheet-zc21), preserving
      // any existing Team Id / counts so the row stays a consistent record of
      // the document even after it becomes unreachable.
      var existingDocDataRow = _readDocDataRow(ss, docId);
      _getOrUpsertDocDataRow(
        ss, docId,
        existingDocDataRow ? existingDocDataRow.docName : '',
        existingDocDataRow ? existingDocDataRow.lastSyncTime : new Date(),
        existingDocDataRow ? existingDocDataRow.teamId : '',
        'Doc Not Found',
        existingDocDataRow ? existingDocDataRow.actionCount : 0,
        existingDocDataRow ? existingDocDataRow.resolvedCount : 0
      );
    }
  });

  GasLogger.log('sync.docNotFound.confirmed', { msg: 'Doc not found', docId: docId, markedCount: marked });
  return _jsonResponse({ marked: marked });
}

/**
 * Permanently deletes the ActionSheet row whose globalId matches
 * payload.globalId.  Called by sidebarDeleteAction after the doc-side
 * paragraph has been removed.
 *
 * Payload shape:
 *   { secret, action: 'delete_action_row', globalId }
 *
 * Response shape:
 *   { deleted: 0|1 }
 */
function _handleDeleteActionRow(payload) {
  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return _jsonResponse({ error: 'Actions sheet not found', deleted: 0 });
  }

  var globalId = payload.globalId || '';
  if (!globalId) {
    return _jsonResponse({ error: 'globalId required', deleted: 0 });
  }

  var existingMap = _loadExistingRowsByGlobalId(actionsSheet);
  var entry       = existingMap[globalId];
  if (!entry) {
    return _jsonResponse({ deleted: 0 });
  }

  WriteGuard.wrapPersistent(function () {
    actionsSheet.deleteRow(entry.rowIndex);
  });

  GasLogger.log('sidebar.delete.row', { globalId: globalId, rowIndex: entry.rowIndex });
  return _jsonResponse({ deleted: 1 });
}

/**
 * Updates Status and Date Modified for a single ActionSheet row, identified by
 * globalId.  Also clears Sync Status so a stale 'Dirty' flag cannot cause
 * the next bidirectional sync to overwrite the change.
 *
 * Called by sidebarSetStatus instead of the full syncDocument — avoids the
 * sheet-wins revert bug and is ~10× faster (no doc scan, no full sheet scan).
 *
 * Payload shape:
 *   { secret, action: 'patch_action_status', globalId, newStatus }
 *
 * Response shape:
 *   { patched: 0|1 }
 */
function _handlePatchActionStatus(payload) {
  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return _jsonResponse({ error: 'Actions sheet not found', patched: 0 });
  }

  var globalId  = payload.globalId  || '';
  var newStatus = payload.newStatus || '';
  if (!globalId || !newStatus) {
    return _jsonResponse({ error: 'globalId and newStatus required', patched: 0 });
  }

  var existingMap = _loadExistingRowsByGlobalId(actionsSheet);
  var entry       = existingMap[globalId];
  if (!entry) {
    return _jsonResponse({ patched: 0 });
  }

  var now = new Date();
  WriteGuard.wrapPersistent(function () {
    actionsSheet.getRange(entry.rowIndex, _ACOL.status).setValue(newStatus);
    actionsSheet.getRange(entry.rowIndex, _ACOL.modified_date).setValue(now);
    actionsSheet.getRange(entry.rowIndex, _ACOL.sync_status).setValue('');
  });

  GasLogger.log('sidebar.status.patched', { globalId: globalId, newStatus: newStatus, row: entry.rowIndex });
  return _jsonResponse({ patched: 1 });
}

// ---------------------------------------------------------------------------
// list_importable_actions handler  (production route, WEBAPP_SECRET-gated,
// GTaskSheet-eore — EPIC-D AC-1 import list)
// ---------------------------------------------------------------------------

/**
 * Lists OPEN actions from documents OTHER than docId that share docId's
 * Team Id, for the Import tab's read+render (AC-1). Read-only.
 *
 * Reuse (per epic-d-e-reuse-inventory): Team Id resolution via
 * _readDocDataRow's docId -> DocData join; assertTeamAccess(teamId, ss) as
 * the security gate (TeamNotFound:/TeamAccessDenied: -> zero rows, never a
 * leak); isResolved(status) for the open-actions filter.
 *
 * Excludes rows whose source is gone (GTaskSheet-wdh0): an ActionSheet row
 * with sync_status 'Deleted' (action removed from its doc) or 'Doc Not
 * Found', or whose source doc's DocData row has sync_status 'Deleted'/'Doc
 * Not Found' (doc trashed/inaccessible).
 *
 * Response rows are pre-sorted by doc_name ASC then AI-N ASC so callers/tests
 * can assert order, though the renderer groups/sorts again regardless
 * (epic-d-import-contract-seams).
 *
 * Payload: { action:'list_importable_actions', docId, secret, clientVersion, caller }
 * Response: { ok:true, teamId, rows:[ {global_id, action_id, action_text,
 *   assignee_email, assignee_name, status, doc_id, doc_name, doc_url,
 *   created_date(ISO)} ] }
 */
function _handleListImportableActions(payload) {
  var data = _listImportableActionsData(payload.docId || '');
  GasLogger.flush();
  return _jsonResponse({ ok: true, teamId: data.teamId, rows: data.rows });
}

/**
 * Core row-building for list_importable_actions (GTaskSheet-8qe5) — extracted
 * so the import_selected_for_test route can re-derive the same team-scoped
 * importable rows without going through a second HTTP round trip / response
 * wrapper. No behaviour change versus the inlined version.
 *
 * @param {string} docId
 * @returns {{teamId: string, rows: Array<Object>}}
 */
function _listImportableActionsData(docId) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  var currentDocDataRow = _readDocDataRow(ss, docId);
  var teamId = currentDocDataRow ? currentDocDataRow.teamId : '';
  if (!teamId) {
    return { teamId: teamId, rows: [] };
  }

  try {
    assertTeamAccess(teamId, ss);
  } catch (e) {
    GasLogger.log('importList.access_denied', { docId: docId, teamId: teamId, err: e.message });
    return { teamId: teamId, rows: [] };
  }

  var actionsSheet = ss.getSheetByName('Actions');
  var lastRow = actionsSheet ? actionsSheet.getLastRow() : 0;
  if (!actionsSheet || lastRow < 2) {
    return { teamId: teamId, rows: [] };
  }

  var data = actionsSheet.getRange(2, 1, lastRow - 1, SHEET_HEADERS.length).getValues();

  var docDataByFileId = {};
  var docDataRows = _readDocDataRows(ss);
  for (var i = 0; i < docDataRows.length; i++) {
    docDataByFileId[docDataRows[i].fileId] = docDataRows[i];
  }

  var rows = [];
  for (var i = 0; i < data.length; i++) {
    var status = data[i][_ACOL.status - 1] || '';
    if (isResolved(status)) continue;

    var rowSyncStatus = data[i][_ACOL.sync_status - 1] || '';
    if (rowSyncStatus === 'Deleted' || rowSyncStatus === 'Doc Not Found') continue;

    var fileId = data[i][_ACOL.file_id - 1] || '';
    if (!fileId || fileId === docId) continue;

    var docData = docDataByFileId[fileId];
    if (!docData || docData.teamId !== teamId) continue;
    if (docData.syncStatus === 'Deleted' || docData.syncStatus === 'Doc Not Found') continue;

    var createdRaw = data[i][_ACOL.created_date - 1];
    rows.push({
      global_id:      data[i][_ACOL.global_id      - 1] || '',
      action_id:      data[i][_ACOL.action_id       - 1] || '',
      action_text:    data[i][_ACOL.action_text     - 1] || '',
      assignee_email: data[i][_ACOL.assignee_email  - 1] || '',
      assignee_name:  data[i][_ACOL.assignee_name   - 1] || '',
      status:         status,
      doc_id:         fileId,
      doc_name:       docData.docName || '',
      doc_url:        'https://docs.google.com/document/d/' + fileId + '/edit',
      created_date:   createdRaw instanceof Date ? createdRaw.toISOString() : (createdRaw || '')
    });
  }

  rows.sort(function (a, b) {
    if (a.doc_name !== b.doc_name) return a.doc_name < b.doc_name ? -1 : 1;
    return parseGlobalId(a.global_id).N - parseGlobalId(b.global_id).N;
  });

  var docIds = {};
  for (var j = 0; j < rows.length; j++) docIds[rows[j].doc_id] = true;

  GasLogger.log('importList.done', { teamId: teamId, count: rows.length, docCount: Object.keys(docIds).length });
  return { teamId: teamId, rows: rows };
}

// ---------------------------------------------------------------------------
// import_selected_for_test handler  (testToken-gated, GTaskSheet-8qe5 —
// interactive-test-entry-point, EPIC GTaskSheet-pw5x)
// ---------------------------------------------------------------------------

/**
 * Drives _importSelectedRows (the same AC-2/AC-3 core as _submitImport) with
 * an explicit globalIds selection, inserting new floating actions at the end
 * of testDocId's body instead of at a CardService cursor. Unblocks
 * GTaskSheet-4gsx: the Import tab's CHECK_BOX SelectionInput cannot be driven
 * via Playwright (clicking the widget toggles the underlying <input>'s
 * checked state, but the add-on host iframe's form-state bridge to
 * e.formInputs does not pick it up).
 *
 * Payload shape: { action: 'import_selected_for_test', testToken, testDocId, globalIds }
 * Response shape: { ok: true, inserted, baseN } | { error }
 */
function _handleImportSelectedForTest(payload) {
  var tokenError = _checkTestToken(payload.testToken || '');
  if (tokenError) return tokenError;

  var docId     = payload.testDocId || '';
  var globalIds = payload.globalIds || [];
  if (!docId) {
    return _jsonResponse({ error: 'testDocId required for import_selected_for_test' });
  }
  if (globalIds.length === 0) {
    return _jsonResponse({ ok: true, inserted: 0, baseN: null });
  }

  var listData    = _listImportableActionsData(docId);
  var selectedSet = {};
  for (var s = 0; s < globalIds.length; s++) selectedSet[globalIds[s]] = true;
  var importRows = (listData.rows || []).filter(function (row) {
    return selectedSet[row.global_id];
  });

  if (importRows.length === 0) {
    GasLogger.flush();
    return _jsonResponse({ ok: true, inserted: 0, baseN: null });
  }

  var doc   = DocumentApp.openById(docId);
  var token = ScriptApp.getOAuthToken();

  var indexResult = _resolveEndIndex(docId, token);
  if (indexResult.index === null) {
    GasLogger.flush();
    return _jsonResponse({ error: indexResult.error });
  }

  var result = _importSelectedRows(doc, docId, token, indexResult.index, importRows);
  GasLogger.flush();
  if (!result.ok) {
    return _jsonResponse({ error: result.error });
  }
  return _jsonResponse({ ok: true, inserted: result.inserted, baseN: result.baseN });
}

// ---------------------------------------------------------------------------
// forward_action_rows handler  (production route, WEBAPP_SECRET-gated,
// GTaskSheet-st24 — EPIC-D AC-3 forward source actions)
// ---------------------------------------------------------------------------

/**
 * Marks each SOURCE action (addressed by global_id, like patch_action_status)
 * as Forwarded — it leaves the open/import pool ('forwarded' is already a
 * isDelegated word, so isResolved() treats it as resolved with no further
 * change needed) and records where it went.
 *
 * Per row: Status = 'Forwarded'; append ' [Forward:<targetDocName> AI-<n>]'
 * to the Action text (newAiToken parsed from newGlobalId); sync_status =
 * 'Dirty' so the source document reflects 'Forwarded' on the next
 * sync_action_rows. The Dirty stamp is written in the same WriteGuard batch
 * as the other field writes (GTaskSheet-wdh0) rather than via a separate
 * post-loop _remarkRowDirty pass, so an error between the two passes can't
 * leave a forwarded row un-flagged.
 *
 * Rows already resolved (e.g. status already 'Forwarded' — a duplicate
 * forward from a stale Import-tab selection or a repeated sourceGlobalId in
 * the same payload) are skipped and omitted from the response's `forwarded`
 * list (GTaskSheet-wdh0) — re-forwarding would append a second
 * '[Forward:...]' suffix to the action text.
 *
 * Payload shape (ContractSchema.js messages.forward_action_rows):
 *   { secret, action: 'forward_action_rows',
 *     forwards: [ { sourceGlobalId, newGlobalId } ], targetDocName }
 *
 * Response shape:
 *   { ok: true, forwarded: [sourceGlobalId, ...] }
 */
function _handleForwardActionRows(payload) {
  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return _jsonResponse({ error: 'Actions sheet not found', forwarded: [] });
  }

  var forwards      = payload.forwards      || [];
  var targetDocName = payload.targetDocName || '';
  if (forwards.length === 0) {
    return _jsonResponse({ ok: true, forwarded: [] });
  }

  var existingMap = _loadExistingRowsByGlobalId(actionsSheet);
  var now         = new Date();
  var forwarded   = [];
  var seen        = {};

  WriteGuard.wrapPersistent(function () {
    for (var i = 0; i < forwards.length; i++) {
      var f      = forwards[i];
      var entry  = existingMap[f.sourceGlobalId];
      if (!entry) continue;
      if (seen[f.sourceGlobalId]) continue;       // duplicate within this payload
      if (isResolved(entry.status)) continue;     // already forwarded/resolved — no re-forward
      seen[f.sourceGlobalId] = true;

      var newAiToken = parseGlobalId(f.newGlobalId).actionId; // 'AI-N'
      var newText    = entry.action + ' [Forward:' + targetDocName + ' ' + newAiToken + ']';

      actionsSheet.getRange(entry.rowIndex, _ACOL.action_text).setValue(newText);
      actionsSheet.getRange(entry.rowIndex, _ACOL.status).setValue('Forwarded');
      actionsSheet.getRange(entry.rowIndex, _ACOL.modified_date).setValue(now);
      actionsSheet.getRange(entry.rowIndex, _ACOL.sync_status).setValue('Dirty');
      forwarded.push(f.sourceGlobalId);
    }
  });

  // Cross-execution read visibility (same pattern as _syncTeamScope's
  // SpreadsheetApp.flush() — SyncManager.js): the test harness's next
  // find_sheet_actions runs as a separate doPost execution and would not
  // otherwise see these writes.
  SpreadsheetApp.flush();

  GasLogger.log('forwardRows.done', { count: forwarded.length });
  GasLogger.flush();
  return _jsonResponse({ ok: true, forwarded: forwarded });
}

// ---------------------------------------------------------------------------
// edit_action_row handler  (testRouteNames — testToken-gated, bead .9)
// ---------------------------------------------------------------------------

/**
 * Simulates a user editing one or more ActionSheet fields over the API path.
 * Addressed by globalId (§16.11 #3). Replicates onActionSheetEdit's Dirty +
 * Date-Modified stamp because doPost writes run as the deployer in a separate
 * execution and do not fire the installable trigger (§16.11 #2; §Programmatic
 * Write Suppression). The row's Sync Status = 'Dirty' makes it sheet-wins on
 * the next sync_action_rows call.
 *
 * Payload shape (ContractSchema.js messages.edit_action_row):
 *   { action: 'edit_action_row', testToken, global_id,
 *     fields: { assignee_email?, assignee_name?, action_text?, status? } }
 *
 * Response shape:
 *   { ok: true, global_id, row: <SheetAction fields> }
 */
function _handleEditActionRow(payload) {
  var tokenError = _checkTestToken(payload.testToken || '');
  if (tokenError) return tokenError;

  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return _jsonResponse({ error: 'Actions sheet not found' });
  }

  var globalId = payload.global_id || '';
  var fields   = payload.fields    || {};
  if (!globalId) {
    return _jsonResponse({ error: 'global_id required' });
  }

  var existingMap = _loadExistingRowsByGlobalId(actionsSheet);
  var entry       = existingMap[globalId];
  if (!entry) {
    return _jsonResponse({ error: 'row not found', global_id: globalId });
  }

  var now = new Date();
  var rowIdx = entry.rowIndex;

  WriteGuard.wrapPersistent(function () {
    if (fields.assignee_email !== undefined) {
      actionsSheet.getRange(rowIdx, _ACOL.assignee_email).setValue(fields.assignee_email);
    }
    if (fields.assignee_name !== undefined) {
      actionsSheet.getRange(rowIdx, _ACOL.assignee_name).setValue(fields.assignee_name);
    }
    if (fields.action_text !== undefined) {
      actionsSheet.getRange(rowIdx, _ACOL.action_text).setValue(fields.action_text);
    }
    if (fields.status !== undefined) {
      actionsSheet.getRange(rowIdx, _ACOL.status).setValue(fields.status);
    }
    // Replicate onActionSheetEdit: stamp Date Modified + Sync Status = 'Dirty'.
    actionsSheet.getRange(rowIdx, _ACOL.modified_date).setValue(now);
    actionsSheet.getRange(rowIdx, _ACOL.sync_status).setValue('Dirty');
  });

  // Re-read the row to return authoritative post-write state.
  var updated = _loadExistingRowsByGlobalId(actionsSheet)[globalId] || {};
  GasLogger.log('test.edit_action_row', { global_id: globalId, fields: Object.keys(fields) });
  GasLogger.flush();
  return _jsonResponse({
    ok:        true,
    global_id: globalId,
    row: {
      global_id:      globalId,
      action_id:      updated.id            || '',
      assignee_email: updated.assigneeEmail || '',
      assignee_name:  updated.assigneeName  || '',
      action_text:    updated.action        || '',
      status:         updated.status        || '',
      modified_date:  updated.dateModified  ? updated.dateModified.toISOString() : '',
      sync_status:    updated.syncStatus    || ''
    }
  });
}

// ---------------------------------------------------------------------------
// find_sheet_actions handler  (testRouteNames — testToken-gated, bead .9)
// ---------------------------------------------------------------------------

/**
 * Returns the current ActionSheet rows scoped to a single document, in the
 * authoritative SheetAction shape (ContractSchema.js sheetAction.fields).
 * Read-only — no mutation. doc_id / doc_name are DERIVED from the
 * document_formula (col 7), not stored columns (Coordination Log .1 §7 #1).
 *
 * Payload shape (ContractSchema.js messages.find_sheet_actions):
 *   { action: 'find_sheet_actions', testToken, docId }
 *
 * Response shape:
 *   { ok: true, docId, rows: [<SheetAction>] }
 */
function _handleFindSheetActions(payload) {
  var tokenError = _checkTestToken(payload.testToken || '');
  if (tokenError) return tokenError;

  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return _jsonResponse({ error: 'Actions sheet not found', rows: [] });
  }

  var docId   = payload.docId || '';
  var lastRow = actionsSheet.getLastRow();
  if (lastRow < 2) {
    return _jsonResponse({ ok: true, docId: docId, rows: [] });
  }

  var numRows  = lastRow - 1;
  var data     = actionsSheet.getRange(2, 1, numRows, SHEET_HEADERS.length).getValues();
  var formulas = actionsSheet.getRange(2, _ACOL.document_formula, numRows, 1).getFormulas();
  var rows     = [];

  for (var i = 0; i < data.length; i++) {
    var formula = formulas[i][0] || '';
    if (!formula) continue;
    var formulaDocId = _extractDocIdFromString(formula);
    if (docId && formulaDocId !== docId) continue;

    var docName     = _extractDocNameFromFormula(formula);
    var createdRaw  = data[i][_ACOL.created_date  - 1];
    var modifiedRaw = data[i][_ACOL.modified_date  - 1];

    rows.push({
      global_id:        data[i][_ACOL.global_id      - 1] || '',
      file_id:          data[i][_ACOL.file_id         - 1] || '',
      action_id:        data[i][_ACOL.action_id       - 1] || '',
      assignee_email:   data[i][_ACOL.assignee_email  - 1] || '',
      assignee_name:    data[i][_ACOL.assignee_name   - 1] || '',
      action_text:      data[i][_ACOL.action_text     - 1] || '',
      status:           data[i][_ACOL.status          - 1] || '',
      document_formula: formula,
      doc_id:           formulaDocId,
      doc_name:         docName,
      created_date:     createdRaw  instanceof Date ? createdRaw.toISOString()  : (createdRaw  || ''),
      modified_date:    modifiedRaw instanceof Date ? modifiedRaw.toISOString() : (modifiedRaw || ''),
      sync_status:      data[i][_ACOL.sync_status    - 1] || ''
    });
  }

  GasLogger.log('test.find_sheet_actions', { docId: docId, count: rows.length });
  GasLogger.flush();
  return _jsonResponse({ ok: true, docId: docId, rows: rows });
}

// ---------------------------------------------------------------------------
// ATDD wrappers for production routes (testToken-gated, snake_case fields)
// ---------------------------------------------------------------------------

/**
 * ATDD-path patch_action_status: updates Status for a row addressed by global_id.
 * Field names follow ContractSchema.js messages.patch_action_status (§16.11 #3):
 * request { action, testToken, global_id, status }; response { ok, global_id }.
 *
 * The production add-on calls the same route with WEBAPP_SECRET + camelCase fields
 * (globalId / newStatus). Both paths share _handlePatchActionStatus logic via
 * this thin adapter rather than duplicating the sheet-write code.
 */
function _handlePatchActionStatusAtdd(payload) {
  var tokenError = _checkTestToken(payload.testToken || '');
  if (tokenError) return tokenError;

  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return _jsonResponse({ error: 'Actions sheet not found' });
  }

  var globalId  = payload.global_id || '';
  var newStatus = payload.status    || '';
  if (!globalId || !newStatus) {
    return _jsonResponse({ error: 'global_id and status required' });
  }

  var existingMap = _loadExistingRowsByGlobalId(actionsSheet);
  var entry       = existingMap[globalId];
  if (!entry) {
    return _jsonResponse({ error: 'row not found', global_id: globalId });
  }

  var now = new Date();
  WriteGuard.wrapPersistent(function () {
    actionsSheet.getRange(entry.rowIndex, _ACOL.status).setValue(newStatus);
    actionsSheet.getRange(entry.rowIndex, _ACOL.modified_date).setValue(now);
    actionsSheet.getRange(entry.rowIndex, _ACOL.sync_status).setValue('Dirty');
  });

  GasLogger.log('test.patch_action_status', { global_id: globalId, status: newStatus });
  GasLogger.flush();
  return _jsonResponse({ ok: true, global_id: globalId });
}

/**
 * ATDD-path forward_action_rows_test: same seen[]/isResolved(entry.status)
 * guard loop as the production _handleForwardActionRows, testToken-gated
 * instead of secret-gated (GTaskSheet-apcu, UC-E AC4). Lets a test pass an
 * explicit forwards[] entry whose sourceGlobalId is already Forwarded/
 * resolved — a state the production import flow's own
 * _listImportableActionsData filter would never let through, so the guard
 * is otherwise unreachable from any test entry point.
 *
 * Payload shape: { action, testToken, forwards: [{sourceGlobalId, newGlobalId}], targetDocName }
 * Response shape: { ok: true, forwarded: [sourceGlobalId, ...] } — entries
 * skipped by the duplicate/already-resolved guard are simply absent.
 */
function _handleForwardActionRowsAtdd(payload) {
  var tokenError = _checkTestToken(payload.testToken || '');
  if (tokenError) return tokenError;

  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return _jsonResponse({ error: 'Actions sheet not found', forwarded: [] });
  }

  var forwards      = payload.forwards      || [];
  var targetDocName = payload.targetDocName || '';
  if (forwards.length === 0) {
    return _jsonResponse({ ok: true, forwarded: [] });
  }

  var existingMap = _loadExistingRowsByGlobalId(actionsSheet);
  var now         = new Date();
  var forwarded   = [];
  var seen        = {};

  WriteGuard.wrapPersistent(function () {
    for (var i = 0; i < forwards.length; i++) {
      var f      = forwards[i];
      var entry  = existingMap[f.sourceGlobalId];
      if (!entry) continue;
      if (seen[f.sourceGlobalId]) continue;       // duplicate within this payload
      if (isResolved(entry.status)) continue;     // already forwarded/resolved — no re-forward
      seen[f.sourceGlobalId] = true;

      var newAiToken = parseGlobalId(f.newGlobalId).actionId; // 'AI-N'
      var newText    = entry.action + ' [Forward:' + targetDocName + ' ' + newAiToken + ']';

      actionsSheet.getRange(entry.rowIndex, _ACOL.action_text).setValue(newText);
      actionsSheet.getRange(entry.rowIndex, _ACOL.status).setValue('Forwarded');
      actionsSheet.getRange(entry.rowIndex, _ACOL.modified_date).setValue(now);
      actionsSheet.getRange(entry.rowIndex, _ACOL.sync_status).setValue('Dirty');
      forwarded.push(f.sourceGlobalId);
    }
  });

  SpreadsheetApp.flush();

  GasLogger.log('forwardRowsTest.done', { count: forwarded.length });
  GasLogger.flush();
  return _jsonResponse({ ok: true, forwarded: forwarded });
}

/**
 * ATDD-path delete_action_row: stamps Sync Status='Deleted' on the row addressed
 * by global_id. Does NOT physically remove the row (contrast with the production
 * sidebar path which physically deletes after removing the doc paragraph).
 *
 * Field names follow ContractSchema.js messages.delete_action_row (§16.11 #3):
 * request { action, testToken, global_id }; response { ok, global_id }.
 *
 * After this call, the next sync() that scans the doc will see the doc paragraph
 * still present and apply doc-wins (clearing Deleted). The 'Deleted+removed' AC
 * is verified at the HTTP layer by asserting the stamp immediately after the call
 * (before the next sync). Removal from doc via the full production flow is covered
 * by the Playwright/UI path (§15 test_12).
 */
function _handleDeleteActionRowAtdd(payload) {
  var tokenError = _checkTestToken(payload.testToken || '');
  if (tokenError) return tokenError;

  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return _jsonResponse({ error: 'Actions sheet not found' });
  }

  var globalId = payload.global_id || '';
  if (!globalId) {
    return _jsonResponse({ error: 'global_id required' });
  }

  var existingMap = _loadExistingRowsByGlobalId(actionsSheet);
  var entry       = existingMap[globalId];
  if (!entry) {
    return _jsonResponse({ error: 'row not found', global_id: globalId });
  }

  WriteGuard.wrapPersistent(function () {
    actionsSheet.getRange(entry.rowIndex, _ACOL.sync_status).setValue('Deleted');
  });

  GasLogger.log('test.delete_action_row', { global_id: globalId });
  GasLogger.flush();
  return _jsonResponse({ ok: true, global_id: globalId });
}

// ---------------------------------------------------------------------------
// append_doc_paragraph handler  (ATDD doc-seeding route — testToken-gated)
// ---------------------------------------------------------------------------

/**
 * Appends a single paragraph to a journey doc over the API path.
 * Implements the session.py append_paragraph() act (§16.9).
 * The text is inserted as a plain paragraph (no chip, no list item).
 *
 * Payload shape:
 *   { action: 'append_doc_paragraph', testToken, testDocId, text }
 * Response shape:
 *   { ok: true, docId }
 */
function _handleAppendDocParagraph(payload) {
  var tokenError = _checkTestToken(payload.testToken || '');
  if (tokenError) return tokenError;

  var docId = payload.testDocId || '';
  var text  = payload.text      || '';
  if (!docId) {
    return _jsonResponse({ error: 'testDocId required for append_doc_paragraph' });
  }
  if (!text) {
    return _jsonResponse({ error: 'text required for append_doc_paragraph' });
  }

  var doc = DocumentApp.openById(docId);
  doc.getBody().appendParagraph(text);
  doc.saveAndClose();

  GasLogger.log('test.append_doc_paragraph', { docId: docId, textLen: text.length });
  GasLogger.flush();
  return _jsonResponse({ ok: true, docId: docId });
}

// ---------------------------------------------------------------------------
// begin/end_journey_session handler  (AtddContracts — testToken-gated, bead .8/.9)
// ---------------------------------------------------------------------------

/**
 * Creates or trashes an ATDD journey doc (§16.11 #1 empty-create).
 * Addressed by testToken; no WEBAPP_SECRET required.
 *
 * begin_journey_session payload:
 *   { action: 'begin_journey_session', testToken }
 * Response:
 *   { ok: true, docId, docName, docUrl }    — session.py reads result.get("docId")
 *
 * end_journey_session payload:
 *   { action: 'end_journey_session', testToken, docId }
 * Response:
 *   { ok: true, trashed: docId }
 */
function _handleJourneySession(payload) {
  var tokenError = _checkTestToken(payload.testToken || '');
  if (tokenError) return tokenError;

  var props = PropertiesService.getScriptProperties();

  if (payload.action === 'begin_journey_session') {
    var now       = new Date();
    var dateStr   = Utilities.formatDate(now, Session.getScriptTimeZone(), 'yyyyMMdd');
    var hexSuffix = ('000' + Math.floor(Math.random() * 0xFFFF).toString(16)).slice(-4);
    var docName   = 'GActionSheet-Test-journey-' + dateStr + '-' + hexSuffix;

    var sheetId    = props.getProperty('TEST_SHEET_ID') || '';
    var folderIter = sheetId ? DriveApp.getFileById(sheetId).getParents() : null;
    var parent     = (folderIter && folderIter.hasNext())
                     ? folderIter.next()
                     : DriveApp.getRootFolder();

    var bjsDoc = DocumentApp.create(docName);
    DriveApp.getFileById(bjsDoc.getId()).moveTo(parent);

    GasLogger.log('journey.begin', { docId: bjsDoc.getId(), docName: docName });
    GasLogger.flush();
    return _jsonResponse({
      ok:     true,
      docId:  bjsDoc.getId(),
      docName: docName,
      docUrl: bjsDoc.getUrl()
    });
  }

  if (payload.action === 'end_journey_session') {
    var docId = payload.docId || '';
    if (!docId) {
      return _jsonResponse({ error: 'docId required for end_journey_session' });
    }
    DriveApp.getFileById(docId).setTrashed(true);
    GasLogger.log('journey.end', { trashed: docId });
    GasLogger.flush();
    return _jsonResponse({ ok: true, trashed: docId });
  }

  return _jsonResponse({ error: 'unknown journey action: ' + (payload.action || '') });
}

/**
 * Extracts the display name (second argument) from a HYPERLINK formula.
 * =HYPERLINK("url","name") → "name"
 * Returns '' when the formula does not match or has no name.
 */
function _extractDocNameFromFormula(formula) {
  var m = formula.match(/HYPERLINK\s*\(\s*"[^"]*"\s*,\s*"([^"]*)"/i);
  return m ? m[1] : '';
}

function _extractDocIdFromString(s) {
  if (!s) return '';
  var m = s.match(/(?:\/d\/|[?&]id=)([a-zA-Z0-9_-]+)/);
  return m ? m[1] : '';
}

function _escapeQuotes(s) {
  // Google Sheets formula strings use "" to escape a literal double-quote, not \".
  return String(s).replace(/"/g, '""');
}

function _jsonResponse(obj) {
  obj.serverVersion = BUILD_INFO.version;
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
