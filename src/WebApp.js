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

/**
 * ?cmd=version — the deploy-verification contract (GAS-Core gas-deployment RECOMMENDATION §3.2).
 *
 * Answers the one question `clasp deploy` exiting 0 cannot: is this /exec URL actually serving
 * the build that was just stamped, and is it the environment we meant to deploy to? The deploy
 * pipeline (manage-deployments.js -> gas-deploy's assertDeployedVersion) polls this and fails the
 * deploy on a mismatch.
 *
 * Deliberately requires NO secret and is routed ahead of every gate in both doGet and doPost, so
 * it answers on an ANYONE_ANONYMOUS deployment and before WEBAPP_SECRET/TEST_TOKEN/ADMIN_SECRET
 * are bootstrapped. It exposes only the build identity — nothing about documents or users.
 *
 * `version` is reported BARE (no leading 'v'): BUILD_INFO.version carries the 'v' for display
 * (sidebar footer, static portal), the wire contract does not. `target` is the deploy target's
 * label ('TEST'/'PRODUCTION'/'DEV'), which is what catches a deploy landing in the wrong
 * environment — distinct from BUILD_INFO.env ('test'/'production'/'dev'), which remains the
 * source of truth for Axiom's env column.
 */
function _handleVersionRequest() {
  var url = '';
  try { url = ScriptApp.getService().getUrl() || ''; } catch (_) {}
  return ContentService
    .createTextOutput(JSON.stringify({
      ok: true,
      version: String(BUILD_INFO.version || '').replace(/^v/, ''),
      versionDate: BUILD_INFO.buildDate || '',
      target: BUILD_INFO.target || '',
      env: BUILD_INFO.env || '',
      deploymentId: _extractDeploymentId(url)
    }))
    .setMimeType(ContentService.MimeType.JSON);
}

/** 'https://script.google.com/macros/s/<id>/exec' -> '<id>' ('' when it does not match). */
function _extractDeploymentId(url) {
  var m = String(url || '').match(/\/macros\/s\/([^\/]+)\/(?:exec|dev)/);
  return m ? m[1] : '';
}

function doGet(e) {
  // Ahead of the WEBAPP_URL registration and logging below: a version poll must stay cheap and
  // must not depend on any script property or side effect succeeding.
  if (e && e.parameter && e.parameter.cmd === 'version') {
    return _handleVersionRequest();
  }

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

  if (e && e.parameter && e.parameter.cmd === 'register') {
    return _handleRegister(e);
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
 * gts-79dw.4.9 — team handoff (implementation choice (a), see bd notes):
 * when the chip's docId resolves to a DocData.teamId (_readDocDataRow, NOT
 * _walkFolderForTeam -- that walk is only for assigning teamScope at sync
 * time), the rendered page gains a "Sign in for the full view" CTA pointing
 * at the verified per-document view (View B, gts-79dw.4.13) on the static
 * portal frontend (_VERIFIED_TEAM_PORTAL_BASE, src/DocView.js), carrying
 * both docId and the resolved teamId as query params (mirrors the
 * ?team=<teamId> convention DocView.js already uses for View B's own
 * teamPortalUrl/View-A link, R20). An untracked docId or a doc with no
 * DocData.teamId degrades to the plain anonymous notice (no CTA) rather than
 * erroring -- the existing Phase-1 rendering is unchanged in that case.
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
  var teamId     = (docDataRow && docDataRow.teamId) || '';
  var docViewUrl = teamId
    ? (_VERIFIED_TEAM_PORTAL_BASE + '?doc=' + encodeURIComponent(docId) + '&team=' + encodeURIComponent(teamId))
    : '';

  // webapp.team.handoff — completion log for the chip -> verified-portal
  // handoff decision (gts-79dw.4.9 pre-code contract §3). route names which
  // branch was taken: a resolved teamId offers the View B CTA; no teamId
  // (untracked doc or no DocData.teamId) falls back to the plain preview.
  GasLogger.log('webapp.team.handoff', {
    docId:  docId,
    teamId: teamId,
    route:  teamId ? 'docview-cta' : 'anonymous-preview-fallback'
  });
  GasLogger.flush();

  return _renderPreviewNotice({
    docName:    (docDataRow && docDataRow.docName) || '(unknown document)',
    teamName:   teamId,
    actionId:   ain,
    status:     row.status || 'Open',
    docLink:    'https://docs.google.com/document/d/' + encodeURIComponent(docId) + '/edit',
    docId:      docId,
    docViewUrl: docViewUrl
  });
}

/**
 * Renders the ADR-0017 Phase 1 notice page HTML. `model === null` renders the
 * non-leaking not-found variant. `model` must never carry action text.
 *
 * @param {?{docName: string, teamName: string, actionId: string, status: string, docLink: string, docViewUrl: string}} model
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
    var syncLink = ACTION_CHIP_URL_BASE + '?cmd=register&docId=' + encodeURIComponent(model.docId);
    // gts-79dw.4.9 — only rendered when a DocData.teamId resolved (R20).
    var docViewRow = model.docViewUrl
      ? '<p><a href="' + _escapeHtml(model.docViewUrl) + '" target="_top">Sign in for the full view</a></p>'
      : '';
    body =
      '<h1>' + _escapeHtml(model.actionId) + '</h1>' +
      '<p><strong>Document:</strong> ' + _escapeHtml(model.docName) + '</p>' +
      teamRow +
      '<p><strong>Status:</strong> ' + _escapeHtml(model.status) + '</p>' +
      docViewRow +
      '<p><a href="' + _escapeHtml(model.docLink) + '" target="_blank">' +
        'Open the document to view or edit this action</a></p>' +
      '<p><a href="' + _escapeHtml(syncLink) + '" target="_top">Sync this document</a></p>' +
      '<p><a href="' + _escapeHtml(ACTION_CHIP_URL_BASE + '?cmd=register') + '" target="_top">Register a new document</a></p>';
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
 * Effectively unbounded age limit for _readTeamActions' 'closed'/'all'
 * windowDays, so ?cmd=teamview's per-doc counts (below) reflect every
 * resolved action ever recorded, not just a recent slice — matching the
 * un-windowed DocData.actionCount/resolvedCount counters this replaced.
 */
var TEAM_VIEW_ALL_TIME_WINDOW_DAYS = 36500;

/**
 * doGet ?cmd=teamview&team=<teamId> — branded team summary page. Sidebar Team
 * link fallback target when TeamData has no Team Link of its own
 * (_buildTeamViewUrl, SyncManager.js). Discloses the team's contact info and,
 * for every document with at least one open action, the document name (linked
 * to open the doc), open count, and resolved count — never action text.
 *
 * Since gts-79dw.4.11, per-doc counts are derived from the shared
 * _readTeamActions reader (this file) rather than DocData's cached
 * actionCount/resolvedCount columns, so a document whose DocData row is
 * itself Deleted/Doc Not Found (R13b) — or whose action rows are individually
 * orphaned — is excluded the same way list_importable_actions and
 * list_team_actions already are.
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

  var actionRows = _readTeamActions(teamId, {
    statusFilter: 'all',
    windowDays:   TEAM_VIEW_ALL_TIME_WINDOW_DAYS,
    fields:       ['doc_id', 'doc_name', 'status_resolved'],
    ss:           ss
  });

  var countsByDoc = {};
  for (var r = 0; r < actionRows.length; r++) {
    var row = actionRows[r];
    var entry = countsByDoc[row.doc_id];
    if (!entry) {
      entry = countsByDoc[row.doc_id] = { fileId: row.doc_id, docName: row.doc_name, openCount: 0, resolvedCount: 0 };
    }
    if (row.status_resolved) entry.resolvedCount++;
    else entry.openCount++;
  }

  var docRows = Object.keys(countsByDoc)
    .map(function (docId) { return countsByDoc[docId]; })
    .filter(function (d) { return d.openCount > 0; });

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
        openCount:     d.openCount,
        resolvedCount: d.resolvedCount
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
 * doGet ?cmd=register[&docId=<docId-or-url>] — self-service document
 * registration for callers without add-on access. No docId param renders a
 * prompt form; a submitted docId is resolved, gated on Drive folder ancestry
 * (must sit under a TeamData-registered team folder — _walkFolderForTeam,
 * SyncManager.js), and — only on a match — registered/synced via the same
 * syncDocument() entry point the add-on menu uses (MenuHandler.js). A doc
 * outside any team folder is refused rather than silently registered with no
 * team, so every DocData row this route creates always has a resolvable team
 * contact.
 *
 * @param {Object} e doGet event; reads e.parameter.docId.
 * @return {HtmlOutput}
 */
function _handleRegister(e) {
  var input = (e && e.parameter && e.parameter.docId) || '';
  if (!input) {
    return _renderRegisterForm();
  }

  var docId = _parseDocIdInput(input);
  if (!docId) {
    return _renderRegisterResult({ ok: false, reason: 'unparseable', input: input });
  }

  // _walkFolderForTeam swallows Drive errors internally and returns null for
  // both "no matching ancestor" and "doc inaccessible" — check accessibility
  // separately first so a bad/unreadable docId gets its own message instead
  // of the misleading "move it into a team folder" copy.
  try {
    withGasRetry('WebApp._handleRegister:DriveApp.getFileById',
      function () { return DriveApp.getFileById(docId); });
  } catch (ex) {
    GasLogger.log('webapp.register.error', { docId: docId, msg: ex.message });
    GasLogger.flush();
    return _renderRegisterResult({ ok: false, reason: 'not-found', docId: docId });
  }

  var ss = _openActionSheetSpreadsheet();
  var teamDataRows = _readTeamDataRows(ss);
  var walkResult = _walkFolderForTeam(docId, teamDataRows);

  if (!walkResult) {
    GasLogger.log('webapp.register.no-team', { docId: docId });
    GasLogger.flush();
    return _renderRegisterResult({ ok: false, reason: 'no-team', docId: docId });
  }

  syncDocument(docId);
  GasLogger.log('webapp.register.synced', { docId: docId, teamId: walkResult.teamId });
  GasLogger.flush();
  return _renderRegisterResult({ ok: true, docId: docId, teamId: walkResult.teamId });
}

/**
 * Accepts either a bare Drive file ID or a full Google Docs URL and returns
 * the file ID, or '' if neither pattern matches.
 */
function _parseDocIdInput(input) {
  var s = String(input || '').trim();
  if (!s) return '';
  var fromUrl = _extractDocIdFromString(s);
  if (fromUrl) return fromUrl;
  return /^[a-zA-Z0-9_-]{10,}$/.test(s) ? s : '';
}

function _renderRegisterForm() {
  var body =
    '<h1>Register a document</h1>' +
    '<p>Enter the document ID or the full Google Docs URL. The document must ' +
    'live inside a folder that has already been registered for a team.</p>' +
    '<form method="GET" target="_top">' +
      '<input type="hidden" name="cmd" value="register">' +
      '<input type="text" name="docId" placeholder="Document ID or URL" ' +
        'style="width:100%;padding:6px;box-sizing:border-box">' +
      '<p><button type="submit">Register &amp; sync</button></p>' +
    '</form>';
  return _renderBrandedPage('GActionSheet — Register a Document', body);
}

/**
 * @param {{ok: boolean, reason?: string, input?: string, docId?: string, teamId?: string}} model
 */
function _renderRegisterResult(model) {
  var body;
  if (model.ok) {
    var docLink = 'https://docs.google.com/document/d/' + encodeURIComponent(model.docId) + '/edit';
    body =
      '<h1>Document registered</h1>' +
      '<p>Team: <strong>' + _escapeHtml(model.teamId) + '</strong></p>' +
      '<p>The document has been synced.</p>' +
      '<p><a href="' + _escapeHtml(docLink) + '" target="_blank">Open the document</a></p>' +
      '<p><a href="' + _escapeHtml(ACTION_CHIP_URL_BASE + '?cmd=register') + '" target="_top">Register another document</a></p>';
  } else if (model.reason === 'unparseable') {
    body =
      '<h1>Could not read that document</h1>' +
      '<p>"' + _escapeHtml(model.input) + '" is not a recognizable document ID or Google Docs URL.</p>' +
      '<p><a href="' + _escapeHtml(ACTION_CHIP_URL_BASE + '?cmd=register') + '" target="_top">Try again</a></p>';
  } else if (model.reason === 'no-team') {
    body =
      '<h1>Document is not under a registered team folder</h1>' +
      '<p>This document cannot be registered because it is not stored inside ' +
      'a folder that has been set up for a team. Move it into a team folder ' +
      'and try again, or contact your team lead.</p>' +
      '<p><a href="' + _escapeHtml(ACTION_CHIP_URL_BASE + '?cmd=register') + '" target="_top">Try again</a></p>';
  } else {
    body =
      '<h1>Document not found</h1>' +
      '<p>The document could not be opened — it may not exist, or this ' +
      'service may not have access to it.</p>' +
      '<p><a href="' + _escapeHtml(ACTION_CHIP_URL_BASE + '?cmd=register') + '" target="_top">Try again</a></p>';
  }
  return _renderBrandedPage('GActionSheet — Register a Document', body);
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
  // ?cmd=version / action:'version' — deploy verification (see _handleVersionRequest above).
  // First, before the JSON parse and before every auth gate: the deploy pipeline polls this
  // immediately after `clasp deploy`, when nothing else about this deployment is guaranteed yet.
  if (e && e.parameter && e.parameter.cmd === 'version') {
    return _handleVersionRequest();
  }

  var payload;
  try {
    payload = JSON.parse(e.postData.contents);
  } catch (ex) {
    return _jsonResponse({ error: 'bad JSON' }, 200);
  }

  if (payload.action === 'version') {
    return _handleVersionRequest();
  }

  // This execution's own op id, carrying the addon caller's op id (if any) as
  // parentOp on every entry made while handling this request -- the HTTP-
  // boundary leg of gts-65g1's correlation (gts-j8cn). Never
  // adopts payload.opId as this execution's own op (see GasLogger.startOp doc).
  GasLogger.startOp(payload.opId);

  // Log identity and caller context for every request so errors can be
  // attributed to a specific user and surface without needing PROBE.
  var _id = _getIdentity();
  // gts-obry.1: queueDelayMs (execution start vs. the client's own
  // initiatedAt, when the caller sends one) distinguishes "this request sat
  // queued a while before running" from "something re-dispatched it" --
  // read alongside op/parentOp (started above), a second execution sharing
  // this same parentOp is the platform re-dispatching ONE client call, not
  // two independent calls.
  GasLogger.log('webapp.request', {
    action:       payload.action || '(unknown)',
    eu:           _id.eu,
    au:           _id.au,
    caller:       payload.caller || {},
    version:      BUILD_INFO.version,
    initiatedAt:  payload.initiatedAt || null,
    queueDelayMs: payload.initiatedAt ? (Date.now() - payload.initiatedAt) : null
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

  // [SPIKE] gts-79dw.2 — gated on SPIKE_ENABLED, bypasses the secret gate
  // intentionally (mirrors the probe route above). See src/SPIKE.js.
  if (payload.action === 'spike_check_access' && SPIKE_ENABLED) {
    return _handleSpikeCheckAccess(payload);
  }
  if (payload.action === 'spike_seed_access' && SPIKE_ENABLED) {
    return _handleSpikeSeedAccess(payload);
  }

  // [SPIKE] gts-6ls9 — gated on SPIKE_COMMENT_POSITION_ENABLED, bypasses the
  // secret gate intentionally (mirrors the spike routes above). See
  // src/SPIKE-CommentPosition.js.
  if (payload.action === 'spike_comment_position' && SPIKE_COMMENT_POSITION_ENABLED) {
    return _handleSpikeCommentPosition(payload);
  }

  // gts-79dw.4.1 — verified-board-portal identity + access-tier route.
  // Bypasses WEBAPP_SECRET intentionally: callers are external GIS-verified
  // identities that don't (and shouldn't) hold our internal secret. The ID
  // token itself is the authentication; see src/AccessControl.js.
  if (payload.action === 'verify_and_resolve_access') {
    return _handleVerifyAndResolveAccess(payload);
  }

  // gts-79dw.4.3 — verified-team-portal read-only listing route (renamed
  // list_board_actions -> list_team_actions by gts-79dw.4.11). Same bypass
  // rationale as verify_and_resolve_access above: the ID token is the
  // authentication, and the tier is re-verified on every call (R8).
  if (payload.action === 'list_team_actions') {
    return _handleListTeamActions(payload);
  }

  // gts-79dw.4.17 — verified-team-portal team-switcher discovery route (R21).
  // Same bypass rationale as the routes above: the ID token is the
  // authentication. No teamId in the request -- the whole point is
  // discovering every team the caller has ANY access to. See
  // src/AccessControl.js's _handleListMyTeams.
  if (payload.action === 'list_my_teams') {
    return _handleListMyTeams(payload);
  }

  // gts-79dw.4.5 — verified-team-portal sync route (renamed
  // board_sync_document -> team_sync_document by gts-79dw.4.11). Same bypass
  // rationale as the routes above: the ID token is the authentication, and
  // the tier is re-verified on every call (R8). EDIT tier required; rejected
  // before the sync path runs otherwise (no partial execution). See
  // src/TeamSync.js.
  if (payload.action === 'team_sync_document') {
    return _handleTeamSyncDocument(payload);
  }

  // gts-79dw.4.13 — View B: verified per-document action view (sidebar's
  // document view, delivered over the web; distinct from the anonymous
  // ?cmd=preview / ?cmd=teamview doGet routes). Same bypass rationale as the
  // routes above: the signed assertion is the authentication, and the tier
  // is re-verified on every call (R8). See src/DocView.js.
  if (payload.action === 'get_document_actions') {
    return _handleGetDocumentActions(payload);
  }

  // gts-79dw.4.14 — verified-team-portal edit + status-change routes (R16-R18).
  // Same bypass rationale as the routes above: the signed assertion is the
  // authentication, and the tier is re-verified on every call (R8). Two
  // DIFFERENT authorizations (see src/TeamActionWrite.js): team_edit_action
  // requires _authorizeDocWrite (EDIT tier on the target document's folder);
  // team_patch_status accepts EITHER _authorizeDocWrite OR that the row's
  // assignee_email matches the verified caller's email (R17). Both reuse the
  // existing edit_action_row / patch_action_status mutation cores (now
  // factored into _editActionRowCore / _patchActionStatusCore below) rather
  // than re-implementing the Dirty/Date-Modified stamping or status write.
  if (payload.action === 'team_edit_action') {
    return _handleTeamEditAction(payload);
  }
  if (payload.action === 'team_patch_status') {
    return _handleTeamPatchStatus(payload);
  }

  // Admin routes (gts-79dw.4.18) — gated by their OWN ADMIN_SECRET, a
  // distinct, higher-privilege credential from both TEST_TOKEN and
  // WEBAPP_SECRET below; never reachable via either of those gates. See
  // src/Admin.js. Checked before the TEST_TOKEN routes so a testToken alone
  // can never authorize an admin action.
  if (payload.action === 'bootstrapSecret' || payload.action === 'setScriptProperties') {
    return _handleAdminAction(payload);
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
  if (payload.action === 'read_team_actions') {
    return _handleReadTeamActions(payload);
  }
  if (payload.action === 'dump_doc_paragraphs') {
    return _handleDumpDocParagraphs(payload);
  }
  if (payload.action === 'dump_raw_docs_api') {
    return _handleDumpRawDocsApi(payload);
  }
  if (payload.action === 'export_governance_json') {
    return _handleExportGovernanceJson(payload);
  }
  if (payload.action === 'run_export_for_dialog_test') {
    return _handleRunExportForDialogTest(payload);
  }
  if (payload.action === 'get_export_progress_for_dialog_test') {
    return _handleGetExportProgressForDialogTest(payload);
  }
  if (payload.action === 'seed_doc_content') {
    return _handleSeedDocContent(payload);
  }
  if (payload.action === 'rename_doc_for_test') {
    return _handleRenameDocForTest(payload);
  }
  if (payload.action === 'dump_export_index_for_test') {
    return _handleDumpExportIndexForTest(payload);
  }
  if (payload.action === 'create_doc_comment') {
    return _handleCreateDocComment(payload);
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

  if (payload.action === 'set_export_config') {
    return _handleSetExportConfig(payload);
  }

  if (payload.action === 'axiom_probe') {
    return _handleAxiomProbe(payload);
  }

  // Deployment health-check routes — called by manage-deployments.js after deploy:test.
  // No testDocId field: GAS holds no script property for any doc ID
  // (ADR-0006 §4) — the master template ID lives only in local.settings.json.
  if (payload.action === 'get_test_config') {
    var props = PropertiesService.getScriptProperties();
    return _jsonResponse({
      testSheetId:      props.getProperty('TEST_SHEET_ID')        || '',
      gasLoggerFolderId: props.getProperty('GAS_LOGGER_FOLDER_ID') || '',
      webappUrl:        props.getProperty('WEBAPP_URL')           || '',
      version:          BUILD_INFO.version,
      // gts-pfyx: non-null when the most recent Axiom ingest POST came back
      // non-2xx (e.g. dataset column-limit hit) -- lets the test harness
      // distinguish "event never fired" from "Axiom ingest is broken" instead
      // of only discovering the latter as an unexplained 60s timeout.
      axiomIngestDegraded: GasLogger.getAxiomHealth()
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
// set_export_config handler  (deployment script only — requires WEBAPP_SECRET)
// ---------------------------------------------------------------------------

/**
 * Stores the export-isolation root folder in Script Properties (gts-z6j0) so
 * getExportFolder_() (src/ExportFolderMap.js) can create per-document export
 * subfolders under it instead of writing into each document's own source
 * folder. Called once by the deployment script after each `npm run
 * deploy:test`, same pattern as set_axiom_config.
 *
 * Payload shape:
 *   { secret, action: 'set_export_config', exportRootFolderId: '<folderId>' }
 *
 * Response shape:
 *   { ok: true }
 */
function _handleSetExportConfig(payload) {
  var exportRootFolderId = payload.exportRootFolderId || '';
  if (!exportRootFolderId) {
    return _jsonResponse({ error: 'exportRootFolderId required' });
  }
  PropertiesService.getScriptProperties().setProperty('EXPORT_ROOT_FOLDER_ID', exportRootFolderId);
  GasLogger.log('export.config.set', { folderId: exportRootFolderId });
  GasLogger.flush();
  return _jsonResponse({ ok: true });
}

// ---------------------------------------------------------------------------
// axiom_probe handler  (test harness only — requires WEBAPP_SECRET)
// ---------------------------------------------------------------------------

/**
 * Logs a 'test.axiom_probe' entry carrying a caller-supplied sentinel id, then
 * flushes immediately. Exercises the real WebApp -> GAS -> GasLogger.flush() ->
 * UrlFetchApp -> Axiom path -- not a Python-direct-to-Axiom shortcut, which
 * would understate real latency by skipping the GAS/WebApp hop (gts-ishz.5).
 *
 * The caller measures latency by polling Axiom for data.sentinel == sentinel
 * after this responds; this route does not itself wait on Axiom.
 *
 * Payload shape:
 *   { secret, action: 'axiom_probe', sentinel: '<uuid>' }
 *
 * Response shape:
 *   { ok: true }
 */
function _handleAxiomProbe(payload) {
  var sentinel = payload.sentinel || '';
  if (!sentinel) {
    return _jsonResponse({ error: 'sentinel required' });
  }
  GasLogger.log('test.axiom_probe', { sentinel: sentinel });
  var flushOk = GasLogger.flush();
  return _jsonResponse({ ok: true, flushOk: flushOk });
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
        var newText   = _normalizeActionText(row.actionText    || existing.action);
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
          _normalizeActionText(row.actionText) || '',
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
 *
 * When two or more physical rows share the same globalId (gts-binf — a race,
 * manual sheet edit, or bug can leave duplicates behind), this keeps only the
 * LAST-scanned row per globalId (top-to-bottom sheet order) as canonical —
 * pre-existing last-write-wins behavior, unchanged for backward compatibility
 * with every read-only/single-row-lookup caller.
 *
 * Callers that need to detect and collapse those duplicates (currently only
 * the syncAll regular-sweep entry point, _handleSyncActionRows) pass an
 * optional `duplicatesOut` object; this function populates
 * `duplicatesOut[globalId] = [rowIndex, ...]` with every EARLIER-scanned
 * rowIndex for a globalId that turned out to have more than one row, so the
 * caller can collapse them. Omitted/undefined `duplicatesOut` is a no-op —
 * every other call site is unaffected.
 */
function _loadExistingRowsByGlobalId(actionsSheet, duplicatesOut) {
  var lastRow = actionsSheet.getLastRow();
  if (lastRow < 2) return {};

  var data   = actionsSheet.getRange(2, 1, lastRow - 1, SHEET_HEADERS.length).getValues();
  var result = {};

  for (var i = 0; i < data.length; i++) {
    var globalId = data[i][0];
    if (!globalId) continue;
    if (duplicatesOut && result[globalId]) {
      if (!duplicatesOut[globalId]) duplicatesOut[globalId] = [];
      duplicatesOut[globalId].push(result[globalId].rowIndex);
    }
    result[globalId] = {
      rowIndex:      i + 2,
      fileId:        data[i][_ACOL.file_id        - 1],
      id:            data[i][_ACOL.action_id      - 1],
      assigneeEmail: data[i][_ACOL.assignee_email - 1],
      assigneeName:  data[i][_ACOL.assignee_name  - 1] || '',
      action:        data[i][_ACOL.action_text    - 1],
      status:        data[i][_ACOL.status         - 1],
      dateModified:  data[i][_ACOL.modified_date  - 1] instanceof Date ? data[i][_ACOL.modified_date - 1] : null,
      syncStatus:    data[i][_ACOL.sync_status    - 1] || '',
      // gts-u0kh: raw JSON string as stored, not parsed — every comparison
      // site treats this as an opaque diff key against the freshly-encoded
      // JSON.stringify(row.customFields) from the incoming docState.
      customFieldsJson: data[i][_ACOL.custom_fields - 1] || ''
    };
  }

  return result;
}

/**
 * Parses a globalId into its components.
 * globalId format: {docFileId}/ACT-{N} or, for pre-existing rows, {docFileId}/AI-{N}
 * (ADR-0023 rule 2 — AI-N: globalIds remain valid indefinitely and are never rewritten).
 * Returns { docId, N, actionId } where actionId preserves whichever prefix was stored.
 * If the format is unexpected, N is NaN and actionId/docId are empty.
 */
function parseGlobalId(globalId) {
  var m = /^(.*)\/(ACT|AI)-(\d+)$/.exec(globalId || '');
  if (!m) return { docId: '', N: NaN, actionId: globalId || '' };
  return { docId: m[1], N: parseInt(m[3], 10), actionId: m[2] + '-' + m[3] };
}

function _extractActionId(globalId) {
  return parseGlobalId(globalId).actionId;
}

// Normalizes the soft-return spelling of action text on its way into the
// sheet: \r, \r\n, and \v all become \n, so a sheet cell holds the same line
// breaks the author typed with Shift+Enter (gts-dou2). Previously these were
// collapsed to a single space, because flush could not reinsert a soft return
// into the doc and a round-tripped \n would have split the paragraph. Flush
// now converts \n back to U+000B via SyncManager.js's _toSoftReturnText
// (gts-dr8j), so preserving the break here is round-trip safe.
// Built on the same _normalizeLineEndings core (SyncManager.js) the scanner
// uses, so the doc-side and sheet-side notion of a line break stay identical
// — action text compared across the two surfaces still matches.
function _normalizeActionText(text) {
  if (!text) return text;
  return _normalizeLineEndings(text).trim();
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
 *   { secret, action: 'sync_action_rows', docUrl, docTitle, scanned,
 *     docState: [{ globalId, assigneeEmail, assigneeName, actionText, status }] }
 *
 * `scanned: true` is the caller's explicit assertion that the document was
 * actually scanned and docState/allDocGlobalIds reflect its real contents
 * (SyncManager.js's _syncActionRows always sets it, including for a
 * legitimately empty document). Without it, orphan detection — which marks
 * every row missing from docState 'Deleted' — is skipped, so a payload that
 * simply omits docState/allDocGlobalIds (e.g. a hand-made maintenance call
 * sending only {action, docId, secret}) cannot be misread as "document is
 * empty, delete everything" (gts-aiaz).
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
  var scanned              = payload.scanned === true;

  // Build a set for O(1) membership checks.
  var activeGlobalIdSet = {};
  for (var ai = 0; ai < allDocGlobalIds.length; ai++) {
    activeGlobalIdSet[allDocGlobalIds[ai]] = true;
  }

  var sameGlobalIdDuplicates = {};
  var existingMap = _loadExistingRowsByGlobalId(actionsSheet, sameGlobalIdDuplicates);
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

      // gts-zocq: normalize actionText and its inline bold/italic runs
      // together (offsets must shift/clip in lockstep with the same
      // normalize+trim _normalizeActionText applies) before any sheet write.
      var shiftedForWrite = _shiftRunsForNormalize(row.actionText, row.runs);
      var normalizedActionText = shiftedForWrite.text;
      var richTextForWrite = _buildRichTextValueForActionText(normalizedActionText, shiftedForWrite.runs);
      // gts-u0kh: JSON-encode customFields for the custom_fields column
      // (ContractSchema.js sheetAction.columnsByField.custom_fields:12),
      // same additive/optional contract as runs above.
      var newCustomFieldsJson = JSON.stringify(row.customFields || {});

      if (!existing) {
        var syncFileId = parseGlobalId(row.globalId).docId;
        var docFormula = '=HYPERLINK("' + docUrl + '","' + _escapeQuotes(docTitle) + '")';
        actionsSheet.appendRow([
          row.globalId,
          syncFileId,
          _extractActionId(row.globalId),
          row.assigneeEmail || '',
          row.assigneeName  || '',
          normalizedActionText || '',
          row.status        || 'Open',
          docFormula,
          now,
          now,
          ''  // Sync Status — blank on insert
        ]);
        // RichTextValue can't be passed through appendRow's plain-values array
        // — apply it as a follow-up write to the just-appended row (gts-zocq).
        // Always issue this follow-up write, even for the plain-text (null)
        // case: appendRow's plain values array only sets the cell's content,
        // not necessarily its per-character text style, so a physical row
        // recycled from an earlier occupant that carried bold/italic could
        // otherwise leak that styling forward onto unrelated plain text
        // (gts-a8yh.2). Live probes did not reproduce this specific path,
        // but it is the defensive fix the plan prescribes and costs nothing
        // in the common (plain-text) case.
        actionsSheet.getRange(actionsSheet.getLastRow(), _ACOL.action_text).setRichTextValue(
          richTextForWrite || SpreadsheetApp.newRichTextValue().setText(normalizedActionText || '').build()
        );
        // gts-u0kh: appendRow's plain-values array only carries columns 1-11
        // (SHEET_HEADERS through sync_status) — custom_fields (col 12) is a
        // follow-up write, same pattern as the RichTextValue follow-up above.
        actionsSheet.getRange(actionsSheet.getLastRow(), _ACOL.custom_fields).setValue(newCustomFieldsJson);
        upserted++;
      } else if (existing.syncStatus === 'Dirty') {
        // Sheet was edited (onActionSheetEdit set Sync Status = 'Dirty') — sheet wins.
        // SyncManager will apply the sheet values back to the doc floating action.
        sheetWins.push({
          globalId:      row.globalId,
          assigneeEmail: existing.assigneeEmail,
          assigneeName:  existing.assigneeName,
          action:        existing.action,
          status:        existing.status,
          // gts-zocq: read back from the cell's own RichTextValue so a
          // sheet-authored bold/italic edit also survives the flush this
          // sheetWins result drives.
          runs:          _richTextRunsForCell(actionsSheet.getRange(existing.rowIndex, _ACOL.action_text))
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
            existing.status !== row.status ||
            // gts-u0kh: a customFields-only edit (no assignee/text/status
            // change) must still produce a write, or a second sync after a
            // field-line-only doc edit would report no diff when it should.
            (existing.customFieldsJson || '{}') !== newCustomFieldsJson) {
          actionsSheet.getRange(rowIdx, _ACOL.assignee_email).setValue(row.assigneeEmail || '');
          actionsSheet.getRange(rowIdx, _ACOL.assignee_name).setValue(row.assigneeName  || '');
          // gts-a8yh.2: setValue() does not reliably clear a cell's prior
          // RichTextValue run formatting (bold/italic survives on read-back)
          // — always route through setRichTextValue, using a plain builder
          // for the no-runs case, same fix as the appendRow follow-up above.
          actionsSheet.getRange(rowIdx, _ACOL.action_text).setRichTextValue(
            richTextForWrite || SpreadsheetApp.newRichTextValue().setText(normalizedActionText || '').build()
          );
          actionsSheet.getRange(rowIdx, _ACOL.status).setValue(row.status || 'Open');
          actionsSheet.getRange(rowIdx, _ACOL.modified_date).setValue(now);
          actionsSheet.getRange(rowIdx, _ACOL.custom_fields).setValue(newCustomFieldsJson);
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
    // Gated on `scanned` (gts-aiaz) — without an explicit assertion that the
    // document was actually scanned, docState=[]/allDocGlobalIds=[] is
    // indistinguishable from "caller omitted these fields" and must NOT be
    // read as "every row is orphaned".
    if (docId && !scanned) {
      GasLogger.log('sync.orphanDetection.skipped', {
        msg: 'sync_action_rows payload missing scanned:true; orphan detection skipped', docId: docId
      });
    }
    if (docId && scanned) {
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

      // Collapse pre-existing duplicate-globalId rows (gts-binf): two or more
      // physical rows sharing one globalId (race/manual edit/bug) are invisible
      // to the update-in-place branch above, which always resolves
      // existingMap[globalId] to the LAST-scanned physical row and silently
      // ignores any earlier duplicate. _loadExistingRowsByGlobalId reports
      // those earlier rowIndexes via sameGlobalIdDuplicates; collapse to the
      // single canonical (last-scanned, already kept up to date above) row by
      // removing the rest. Gated on `scanned` — same rationale as the orphan
      // pass above: a destructive delete requires the explicit-scan assertion.
      for (var dupGlobalId in sameGlobalIdDuplicates) {
        if (parseGlobalId(dupGlobalId).docId !== docId) continue; // belongs to a different doc
        var dupRows = sameGlobalIdDuplicates[dupGlobalId];
        for (var dri2 = 0; dri2 < dupRows.length; dri2++) {
          duplicateRowIndexes.push(dupRows[dri2]);
        }
        var keptEntry = existingMap[dupGlobalId];
        GasLogger.log('sync.dedup', {
          msg: 'Collapsed duplicate globalId rows', globalId: dupGlobalId, docId: docId,
          removedCount: dupRows.length,
          keptRowIndex: keptEntry ? keptEntry.rowIndex : null
        });
      }

      // De-dupe rowIndexes (belt-and-suspenders — the orphan/identity pass
      // above and the same-globalId pass above populate duplicateRowIndexes
      // from disjoint sources, but deleteRow() on a repeated index would
      // corrupt the sheet if that ever changed) before deleting descending.
      var seenDupIdx = {};
      var uniqueDupIndexes = [];
      for (var udi = 0; udi < duplicateRowIndexes.length; udi++) {
        var idx = duplicateRowIndexes[udi];
        if (seenDupIdx[idx]) continue;
        seenDupIdx[idx] = true;
        uniqueDupIndexes.push(idx);
      }
      uniqueDupIndexes.sort(function (a, b) { return b - a; });
      for (var dri = 0; dri < uniqueDupIndexes.length; dri++) {
        actionsSheet.deleteRow(uniqueDupIndexes[dri]);
      }
    }

    // Refresh DocData.action_count / resolved_count from the just-reconciled
    // Actions sheet (gts-zc21) — counts exclude rows orphaned from this
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
 * Also checks DocData.teamId against the live Drive teamScope appProperty —
 * the one place that pays for ground truth, now that _syncTeamScope (gts-
 * j8cn) trusts the DocData mirror on every sync instead of re-reading Drive.
 * A mismatch means a prior sync's Drive write and DocData write fell out of
 * step (e.g. a crashed execution between the two) — surfaced as a violation
 * here instead of silently going unnoticed forever.
 *
 * Payload shape:
 *   { secret, action: 'verify_action_rows', docUrl }
 *
 * Response shape:
 *   { rows: [...], violations: [{ docId, issue }] }
 */
/**
 * Core of verify_action_rows, factored out so in-process callers (the add-on
 * homepage card, verifyDocumentSync) can get the same answer without a
 * round-trip through UrlFetchApp to this script's own /exec deployment
 * (gts-8py3 — that self-call was measured taking 35-40+s from inside a GAS
 * execution vs. 3-4s for the identical HTTP call issued externally, which
 * blew buildHomepageCard's ~44s platform timeout most of the time). Returns
 * the plain response object; _handleVerifyActionRows wraps it for HTTP
 * callers (the ATDD harness, which has no in-process access).
 *
 * @param {{docId:?string, docUrl:?string}} payload
 * @return {{error:?string, rows:Array, violations:?Array}}
 */
function _verifyActionRowsCore(payload) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return { error: 'Actions sheet not found', rows: [] };
  }
  // testToken path sends docId; WEBAPP_SECRET path sends docUrl — normalise to URL form
  var docId = payload.docId || _extractDocIdFromString(payload.docUrl || '');
  var docUrl = payload.docUrl ||
    (docId ? 'https://docs.google.com/document/d/' + docId + '/edit' : '');

  var violations = [];
  if (docId) {
    var docDataRow = _readDocDataRow(ss, docId);
    if (docDataRow && docDataRow.syncStatus !== 'UpdateDoc') {
      var token = ScriptApp.getOAuthToken();
      var driveTeamScope = _getDocAppProperty(docId, 'teamScope', token) || '';
      var mirroredTeamId = docDataRow.teamId || '';
      if (driveTeamScope !== mirroredTeamId) {
        violations.push({
          docId: docId,
          issue: 'teamScope drift: DocData.teamId=' + JSON.stringify(mirroredTeamId) +
                 ' != Drive teamScope=' + JSON.stringify(driveTeamScope)
        });
        GasLogger.log('verify.teamScope.drift', { docId: docId, docDataTeamId: mirroredTeamId, driveTeamScope: driveTeamScope });
      }
    }
  }

  return {
    rows: _loadRowsForDocUrl(actionsSheet, docUrl),
    violations: violations
  };
}

function _handleVerifyActionRows(payload) {
  return _jsonResponse(_verifyActionRowsCore(payload));
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
  urlToStatus[_ACTION_DEFAULT_IMAGE] = 'other'; // status-other.png = any non-standard status (matches the 'other' exemption in Check 3 below)

  var violations = [];
  var checkedCount = 0;

  for (var i = 0; i < content.length; i++) {
    var para = content[i].paragraph;
    if (!para) continue;
    var elements = para.elements || [];

    // Build plain text from textRuns only to detect the ACT-N:/AI-N: token
    var builtText = '';
    for (var j = 0; j < elements.length; j++) {
      if (elements[j].textRun) builtText += elements[j].textRun.content || '';
    }
    var plainText = builtText.replace(/\n$/, '');
    var tokenMatch = _matchActionTokenPrefixed(plainText);
    if (!tokenMatch || !/\s/.test(plainText.charAt(tokenMatch.match.length))) continue;

    var N = tokenMatch.N;
    var tokenLabel = tokenMatch.prefix + '-' + N;
    checkedCount++;
    var expectedGlobalId = docId + '/' + tokenLabel;

    // Check 1: leading element must be inlineObjectElement with brand-NUUTS sourceUri
    var firstEl = elements[0] || {};
    if (!firstEl.inlineObjectElement) {
      violations.push({ paragraph: tokenLabel, issue: 'no leading inlineObjectElement' });
      continue;
    }
    var inlineObjId = firstEl.inlineObjectElement.inlineObjectId || '';
    var inlineObj = inlineObjects[inlineObjId] || {};
    var sourceUri = (((inlineObj.inlineObjectProperties || {}).embeddedObject || {}).imageProperties || {}).sourceUri || '';
    var iconStatus = Object.prototype.hasOwnProperty.call(urlToStatus, sourceUri) ? urlToStatus[sourceUri] : null;
    if (iconStatus === null) {
      violations.push({ paragraph: tokenLabel, issue: 'sourceUri not a brand-NUUTS image: ' + sourceUri });
    }

    // Check 2: token textRun (element[1]) link.url must resolve to the
    // expected globalId — via either the current docId+ain params or the
    // legacy globalId= param (_globalIdFromChipUrl accepts both).
    var tokenEl = elements[1] || {};
    var linkUrl = (((tokenEl.textRun || {}).textStyle || {}).link || {}).url || '';
    var actualGlobalId = linkUrl ? _globalIdFromChipUrl(linkUrl) : null;
    if (actualGlobalId !== expectedGlobalId) {
      violations.push({ paragraph: tokenLabel, issue: 'token link.url globalId mismatch — expected ' + expectedGlobalId + ', got: ' + linkUrl });
    }

    // Check 3: trailing (Status) token must be consistent with icon
    if (iconStatus !== null) {
      var statusMatch = plainText.match(/\(([^)]*)\)\s*$/);
      if (statusMatch) {
        var docStatus = statusMatch[1].trim().toLowerCase();
        if (iconStatus !== 'other' && iconStatus !== docStatus) {
          violations.push({
            paragraph: tokenLabel,
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
 * Marks all Actions rows whose Document formula references any of docIds as
 * 'Doc Not Found' in the Sync Status column. One sheet read + one batched
 * write regardless of how many docIds are passed (gts-kkm7.1) — a
 * syncAll() sweep that finds N missing docs sends them all in a single call
 * instead of N separate ones, each of which used to re-read the whole Actions
 * sheet and write matched rows one cell at a time.
 *
 * Payload shape: { secret, action: 'mark_doc_not_found', docIds: string[] }
 */
function _handleMarkDocNotFound(payload) {
  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return _jsonResponse({ error: 'Actions sheet not found', marked: 0 });
  }

  var docIds  = payload.docIds || (payload.docId ? [payload.docId] : []);
  var lastRow = actionsSheet.getLastRow();
  if (docIds.length === 0 || lastRow < 2) {
    return _jsonResponse({ marked: 0 });
  }

  var numRows       = lastRow - 1;
  var formulasCol7  = actionsSheet.getRange(2, _ACOL.document_formula, numRows, 1).getFormulas();
  var syncStatusCol = actionsSheet.getRange(2, _ACOL.sync_status, numRows, 1).getValues();

  // One pass over the sheet's in-memory snapshot to find every row matching
  // any docId, instead of repeating the scan once per docId.
  var statusA1s     = [];
  var modifiedA1s    = [];
  var markedByDocId = {};
  for (var i = 0; i < formulasCol7.length; i++) {
    var formula = formulasCol7[i][0] || '';
    var matchedDocId = null;
    for (var di = 0; di < docIds.length; di++) {
      if (formula.indexOf(docIds[di]) !== -1) { matchedDocId = docIds[di]; break; }
    }
    if (!matchedDocId) continue;
    if (syncStatusCol[i][0] === 'Doc Not Found') continue;
    var rowNum = i + 2;
    statusA1s.push(actionsSheet.getRange(rowNum, _ACOL.sync_status).getA1Notation());
    modifiedA1s.push(actionsSheet.getRange(rowNum, _ACOL.modified_date).getA1Notation());
    markedByDocId[matchedDocId] = (markedByDocId[matchedDocId] || 0) + 1;
  }

  var totalMarked = statusA1s.length;

  WriteGuard.wrapPersistent(function () {
    // Stamp the same detection-time timestamp on every row across every docId
    // in this batch so they age out of ArchiveManager's 24h Doc Not Found
    // threshold together, not independently (gts-4tnr) — a doc going
    // missing is a per-doc event, not a per-row one. Only stamp on the actual
    // transition into Doc Not Found: syncAll() already keeps a permanently-
    // missing docId out of this path on later sweeps (its own
    // alreadyDocNotFound skip-list), but syncDocument() is also called
    // directly from doc-context entry points (Sync menu item, sidebar Sync
    // button — MenuHandler.js, WorkspaceAddonCard.js) with no such guard.
    // Without this check, re-confirming an already-marked row on every direct
    // re-sync would keep resetting Date Modified to now, so the 24h grace
    // period would never actually elapse for a persistently missing doc
    // someone keeps clicking Sync on — and it would violate the "Date
    // Modified only changes on a real content change" invariant, since "still
    // missing" isn't one.
    //
    // getRangeList(...).setValue(...) writes the same value to every listed
    // (possibly non-contiguous) cell in one call — this is what collapses the
    // old per-row setValue() loop into a single write per column.
    if (totalMarked > 0) {
      var now = new Date();
      actionsSheet.getRangeList(statusA1s).setValue('Doc Not Found');
      actionsSheet.getRangeList(modifiedA1s).setValue(now);
    }

    // Mirror the Doc Not Found status to DocData (gts-zc21) for every
    // affected docId, preserving any existing Team Id / counts so the row
    // stays a consistent record of the document even after it becomes
    // unreachable. Still one upsert per docId (a sheet op, not a network
    // round trip) — only the Actions-sheet read/write collapsed above.
    for (var dk in markedByDocId) {
      if (!markedByDocId.hasOwnProperty(dk)) continue;
      var existingDocDataRow = _readDocDataRow(ss, dk);
      _getOrUpsertDocDataRow(
        ss, dk,
        existingDocDataRow ? existingDocDataRow.docName : '',
        existingDocDataRow ? existingDocDataRow.lastSyncTime : new Date(),
        existingDocDataRow ? existingDocDataRow.teamId : '',
        'Doc Not Found',
        existingDocDataRow ? existingDocDataRow.actionCount : 0,
        existingDocDataRow ? existingDocDataRow.resolvedCount : 0
      );
    }
  });

  // Log aggregate counts only, not markedByDocId itself (still returned below,
  // full detail, to the HTTP caller) -- a dict keyed by docId would mint a new
  // Axiom column per document ever seen, unbounded (gts-pfyx follow-up).
  GasLogger.log('sync.docNotFound.confirmed', {
    msg: 'Doc not found', docIds: docIds, uniqueDocsMarked: Object.keys(markedByDocId).length, totalMarked: totalMarked
  });
  return _jsonResponse({ marked: totalMarked, markedByDocId: markedByDocId });
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
  var globalId  = payload.globalId  || '';
  var newStatus = payload.newStatus || '';

  var result = _patchActionStatusCore(globalId, newStatus);
  if (!result.ok) {
    return _jsonResponse({ error: result.error, patched: 0 });
  }
  if (!result.found) {
    return _jsonResponse({ patched: 0 });
  }

  GasLogger.log('sidebar.status.patched', { globalId: globalId, newStatus: newStatus, row: result.rowIndex });
  return _jsonResponse({ patched: 1 });
}

/**
 * Core mutation behind patch_action_status (sidebar fast path) and
 * gts-79dw.4.14's GIS-tier-gated team_patch_status -- factored out so both
 * routes write Status/Date-Modified/cleared-Sync-Status via the SAME path
 * (plan §11 reuse constraint) instead of team_patch_status re-implementing
 * the status write. Callers are responsible for their OWN authorization gate
 * before calling this -- it performs the write unconditionally once a row is
 * found.
 *
 * @param {string} globalId
 * @param {string} newStatus
 * @returns {{ok:boolean, error?:string, found?:boolean, rowIndex?:number}}
 */
function _patchActionStatusCore(globalId, newStatus) {
  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return { ok: false, error: 'Actions sheet not found' };
  }
  if (!globalId || !newStatus) {
    return { ok: false, error: 'globalId and newStatus required' };
  }

  var existingMap = _loadExistingRowsByGlobalId(actionsSheet);
  var entry       = existingMap[globalId];
  if (!entry) {
    return { ok: true, found: false };
  }

  var now = new Date();
  WriteGuard.wrapPersistent(function () {
    actionsSheet.getRange(entry.rowIndex, _ACOL.status).setValue(newStatus);
    actionsSheet.getRange(entry.rowIndex, _ACOL.modified_date).setValue(now);
    actionsSheet.getRange(entry.rowIndex, _ACOL.sync_status).setValue('');
  });

  return { ok: true, found: true, rowIndex: entry.rowIndex };
}

// ---------------------------------------------------------------------------
// list_importable_actions handler  (production route, WEBAPP_SECRET-gated,
// gts-eore — EPIC-D AC-1 import list)
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
 * Excludes rows whose source is gone (gts-wdh0): an ActionSheet row
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
 * Core row-building for list_importable_actions (gts-8qe5) — extracted
 * so the import_selected_for_test route can re-derive the same team-scoped
 * importable rows without going through a second HTTP round trip / response
 * wrapper.
 *
 * Since gts-79dw.4.11 slice 1 this is a thin gate-plus-delegate wrapper over
 * _readTeamActions: it resolves docId -> teamId, applies assertTeamAccess as
 * the security gate, and asks the shared reader for open actions from other
 * documents in the same team, projected to the frozen
 * list_importable_actions row schema. Behaviour is unchanged.
 *
 * @param {string} docId
 * @returns {{teamId: string, rows: Array<Object>}}
 */
function _listImportableActionsData(docId) {
  var ss = _openActionSheetSpreadsheet();

  var teamId = _resolveTeamIdForDoc(ss, docId);
  if (!teamId) {
    return { teamId: teamId, rows: [] };
  }

  try {
    assertTeamAccess(teamId, ss);
  } catch (e) {
    GasLogger.log('importList.access_denied', { docId: docId, teamId: teamId, err: e.message });
    return { teamId: teamId, rows: [] };
  }

  var rows = _readTeamActions(teamId, {
    statusFilter:  'open',
    excludeDocId:  docId,
    fields:        IMPORTABLE_ACTION_FIELDS,
    ss:            ss
  });

  var docIds = {};
  for (var j = 0; j < rows.length; j++) docIds[rows[j].doc_id] = true;

  GasLogger.log('importList.done', { teamId: teamId, count: rows.length, docCount: Object.keys(docIds).length });
  return { teamId: teamId, rows: rows };
}

// ---------------------------------------------------------------------------
// _readTeamActions — the one team-scoped action reader (gts-79dw.4.11)
// ---------------------------------------------------------------------------

/**
 * Every field _readTeamActions can emit, in canonical order. A caller that
 * needs a narrower/frozen projection passes a subset as opts.fields.
 */
var TEAM_ACTION_FIELDS = Object.freeze([
  'global_id', 'action_id', 'action_text', 'assignee_email', 'assignee_name',
  // status is the literal the user typed; the three status_* fields are
  // getStatusDisplay()'s answer for it (SyncManager.js). They travel with the
  // row so a surface never re-derives the bucketing — see gts-79dw.4.7.
  'status', 'status_bucket', 'status_resolved', 'status_icon',
  'doc_id', 'doc_name', 'doc_url', 'created_date', 'modified_date'
]);

/**
 * The frozen list_importable_actions row projection (ContractSchema.js
 * messages.list_importable_actions). Kept explicit so a new field added to
 * TEAM_ACTION_FIELDS cannot silently widen that contract.
 */
var IMPORTABLE_ACTION_FIELDS = Object.freeze([
  'global_id', 'action_id', 'action_text', 'assignee_email', 'assignee_name',
  'status', 'doc_id', 'doc_name', 'doc_url', 'created_date'
]);

/** Default age limit, in days, on resolved rows returned by 'closed'/'all'. */
var TEAM_ACTIONS_DEFAULT_WINDOW_DAYS = 60;

/**
 * Resolves a document's Team Id via its DocData row. '' when the document is
 * untracked or has no team.
 *
 * @param {GoogleAppsScript.Spreadsheet.Spreadsheet} ss
 * @param {string} docId
 * @returns {string}
 */
function _resolveTeamIdForDoc(ss, docId) {
  var docDataRow = docId ? _readDocDataRow(ss, docId) : null;
  return docDataRow ? (docDataRow.teamId || '') : '';
}

/**
 * Reads every Actions-sheet row belonging to a document in teamId's scope.
 * Read-only, and deliberately UNGATED — authorization is the caller's job
 * (assertTeamAccess for the add-on routes, the GIS access tier for the
 * portal), because the two surfaces authorize differently over the same data.
 *
 * Always excluded, on every filter:
 *   - action rows whose sync_status is 'Deleted' or 'Doc Not Found'
 *     (the action is gone from its document)
 *   - actions whose source document's DocData row is 'Deleted' or
 *     'Doc Not Found' (the document itself is trashed/inaccessible) — R13b
 *
 * opts:
 *   statusFilter  'open' (default, excludes isResolved() rows) | 'closed'
 *                 (only resolved rows) | 'all' (both). Resolved rows are
 *                 additionally limited to those modified within windowDays.
 *   windowDays    age limit on resolved rows; default
 *                 TEAM_ACTIONS_DEFAULT_WINDOW_DAYS.
 *   excludeDocId  omit rows sourced from this document.
 *   assigneeEmail omit rows not assigned to this address (case-insensitive).
 *   fields        subset of TEAM_ACTION_FIELDS to project; default all.
 *   ss            already-open spreadsheet to read from; opened if absent.
 *
 * Rows are sorted by doc_name ASC then AI-N ASC.
 *
 * @param {string} teamId
 * @param {Object} [opts]
 * @returns {Array<Object>}
 */
function _readTeamActions(teamId, opts) {
  opts = opts || {};
  if (!teamId) return [];

  var statusFilter  = opts.statusFilter || 'open';
  var windowDays    = Number(opts.windowDays) > 0 ? Number(opts.windowDays)
                                                  : TEAM_ACTIONS_DEFAULT_WINDOW_DAYS;
  var excludeDocId  = opts.excludeDocId || '';
  var assigneeEmail = (opts.assigneeEmail || '').toLowerCase();
  var fields        = opts.fields || TEAM_ACTION_FIELDS;
  var ss            = opts.ss || _openActionSheetSpreadsheet();

  // Snapshot the window cutoff before the (corpus-size-scaling, gts-kkm7)
  // DocData/Actions reads below, not after — those getValues() calls can
  // take multiple seconds against a large TEST corpus, and computing the
  // cutoff post-read pushes it later than "now" was when the caller's
  // request actually landed, silently narrowing the retention window.
  var cutoffMs = Date.now() - windowDays * 24 * 60 * 60 * 1000;

  var docDataByFileId = {};
  var docDataRows = _readDocDataRows(ss);
  for (var d = 0; d < docDataRows.length; d++) {
    docDataByFileId[docDataRows[d].fileId] = docDataRows[d];
  }

  var actionsSheet = ss.getSheetByName('Actions');
  var lastRow = actionsSheet ? actionsSheet.getLastRow() : 0;
  if (!actionsSheet || lastRow < 2) return [];

  var data = actionsSheet.getRange(2, 1, lastRow - 1, SHEET_HEADERS.length).getValues();
  var rows = [];

  for (var i = 0; i < data.length; i++) {
    var row = data[i];

    var rowSyncStatus = row[_ACOL.sync_status - 1] || '';
    if (rowSyncStatus === 'Deleted' || rowSyncStatus === 'Doc Not Found') continue;

    var fileId = row[_ACOL.file_id - 1] || '';
    if (!fileId || fileId === excludeDocId) continue;

    var docData = docDataByFileId[fileId];
    if (!docData || docData.teamId !== teamId) continue;
    if (docData.syncStatus === 'Deleted' || docData.syncStatus === 'Doc Not Found') continue;

    if (assigneeEmail &&
        String(row[_ACOL.assignee_email - 1] || '').toLowerCase() !== assigneeEmail) continue;

    var status = row[_ACOL.status - 1] || '';
    var modifiedRaw = row[_ACOL.modified_date - 1];
    if (isResolved(status)) {
      if (statusFilter === 'open') continue;
      var modifiedMs = modifiedRaw instanceof Date ? modifiedRaw.getTime() : -1;
      if (modifiedMs < cutoffMs) continue;
    } else if (statusFilter === 'closed') {
      continue;
    }

    var createdRaw = row[_ACOL.created_date - 1];
    var display    = getStatusDisplay(status);
    rows.push({
      global_id:      row[_ACOL.global_id      - 1] || '',
      action_id:      row[_ACOL.action_id      - 1] || '',
      action_text:    row[_ACOL.action_text    - 1] || '',
      assignee_email: row[_ACOL.assignee_email - 1] || '',
      assignee_name:  row[_ACOL.assignee_name  - 1] || '',
      status:         status,
      status_bucket:  display.bucket,
      status_resolved: display.resolved,
      status_icon:    display.icon,
      doc_id:         fileId,
      doc_name:       docData.docName || '',
      doc_url:        'https://docs.google.com/document/d/' + fileId + '/edit',
      created_date:   createdRaw  instanceof Date ? createdRaw.toISOString()  : (createdRaw  || ''),
      modified_date:  modifiedRaw instanceof Date ? modifiedRaw.toISOString() : (modifiedRaw || '')
    });
  }

  // Sort before projecting — the sort keys are not necessarily in `fields`.
  rows.sort(function (a, b) {
    if (a.doc_name !== b.doc_name) return a.doc_name < b.doc_name ? -1 : 1;
    return parseGlobalId(a.global_id).N - parseGlobalId(b.global_id).N;
  });

  return rows.map(function (row) { return _projectFields(row, fields); });
}

/**
 * Returns a copy of row carrying only `fields`, in `fields` order.
 *
 * @param {Object} row
 * @param {Array<string>} fields
 * @returns {Object}
 */
function _projectFields(row, fields) {
  var projected = {};
  for (var f = 0; f < fields.length; f++) {
    projected[fields[f]] = row[fields[f]];
  }
  return projected;
}

// ---------------------------------------------------------------------------
// import_selected_for_test handler  (testToken-gated, gts-8qe5 —
// interactive-test-entry-point, EPIC gts-pw5x)
// ---------------------------------------------------------------------------

/**
 * Drives _importSelectedRows (the same AC-2/AC-3 core as _submitImport) with
 * an explicit globalIds selection, inserting new floating actions at the end
 * of testDocId's body instead of at a CardService cursor. Unblocks
 * gts-4gsx: the Import tab's CHECK_BOX SelectionInput cannot be driven
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

  var doc   = withGasRetry('WebApp._handleImportSelectedForTest:DocumentApp.openById',
    function () { return DocumentApp.openById(docId); });
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
// gts-st24 — EPIC-D AC-3 forward source actions)
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
 * as the other field writes (gts-wdh0) rather than via a separate
 * post-loop _remarkRowDirty pass, so an error between the two passes can't
 * leave a forwarded row un-flagged.
 *
 * Rows already resolved (e.g. status already 'Forwarded' — a duplicate
 * forward from a stale Import-tab selection or a repeated sourceGlobalId in
 * the same payload) are skipped and omitted from the response's `forwarded`
 * list (gts-wdh0) — re-forwarding would append a second
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

      var newAiToken = parseGlobalId(f.newGlobalId).actionId; // e.g. 'ACT-N' or legacy 'AI-N'
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

  var globalId = payload.global_id || '';
  var fields   = payload.fields    || {};

  var result = _editActionRowCore(globalId, fields);

  // Logged as globalId (camelCase), matching every other call site's Axiom
  // field name -- payload.global_id (snake_case) is this route's own wire
  // contract, unrelated and untouched; the divergence otherwise mints a
  // duplicate near-identical column (gts-pfyx follow-up).
  if (result.ok) {
    GasLogger.log('test.edit_action_row', { globalId: globalId, fields: Object.keys(fields) });
  }
  GasLogger.flush();
  return _jsonResponse(result);
}

/**
 * Core mutation behind edit_action_row (bead .9) and gts-79dw.4.14's
 * GIS-tier-gated team_edit_action -- factored out so both routes replicate
 * onActionSheetEdit's Dirty + Date-Modified stamp via the SAME write path
 * rather than each route re-implementing it (plan §11 reuse constraint).
 * Callers are responsible for their OWN authorization gate before calling
 * this -- it performs the write unconditionally once a row is found.
 *
 * @param {string} globalId
 * @param {Object} fields { assignee_email?, assignee_name?, action_text?, status? }
 * @returns {{ok:boolean, global_id?:string, error?:string, row?:Object}}
 *   Same shape edit_action_row's HTTP response has always returned.
 */
function _editActionRowCore(globalId, fields) {
  var ss           = SpreadsheetApp.getActiveSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) {
    return { ok: false, error: 'Actions sheet not found' };
  }
  if (!globalId) {
    return { ok: false, error: 'global_id required' };
  }

  var existingMap = _loadExistingRowsByGlobalId(actionsSheet);
  var entry       = existingMap[globalId];
  if (!entry) {
    return { ok: false, error: 'row not found', global_id: globalId };
  }

  var now    = new Date();
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
  return {
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
  };
}

// ---------------------------------------------------------------------------
// dump_doc_paragraphs handler  (testRouteNames — testToken-gated)
// ---------------------------------------------------------------------------

/**
 * Read-only structural dump of a document's body: one entry per structural
 * element with its index range, list/bullet status, and text. Strictly a
 * Docs API GET — mutates nothing.
 *
 * Exists to diagnose paragraph-boundary defects (an action merging with the
 * following paragraph or list item after a flush), where the question is
 * exactly which index range a rewrite spanned and whether a paragraph's
 * trailing newline survived. `verify_chip_integrity` answers "are the chips
 * right"; this answers "what is the document's shape".
 *
 * Payload: { action:'dump_doc_paragraphs', testToken, docId }
 * Response: { ok, docId, elements:[{i, start, end, isListItem, nestingLevel,
 *   text}] }
 */
function _handleDumpDocParagraphs(payload) {
  var tokenError = _checkTestToken(payload.testToken || '');
  if (tokenError) return tokenError;

  var docId = payload.docId || '';
  if (!docId) return _jsonResponse({ error: 'docId required', elements: [] });

  var pElems = 'paragraph(bullet,elements(startIndex,endIndex,textRun/content))';
  var fields = 'body.content(startIndex,endIndex,' + pElems +
    ',table/tableRows/tableCells/content(startIndex,endIndex,' + pElems + '))';
  var resp = UrlFetchApp.fetch(
    'https://docs.googleapis.com/v1/documents/' + docId + '?fields=' + encodeURIComponent(fields),
    { headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() }, muteHttpExceptions: true }
  );
  if (resp.getResponseCode() !== 200) {
    return _jsonResponse({ error: 'Docs API error: ' + resp.getResponseCode(), elements: [] });
  }

  var content  = ((JSON.parse(resp.getContentText()).body) || {}).content || [];
  var elements = [];

  // Walk body content and table-cell content alike — the flush's occurrence
  // scan recurses into tables, so a structural dump that stopped at the body
  // would be blind to exactly the paragraphs it rewrites.
  function walk(items, path) {
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      if (item.paragraph) {
        var els  = item.paragraph.elements || [];
        var text = '';
        for (var j = 0; j < els.length; j++) {
          if (els[j].textRun) text += els[j].textRun.content || '';
        }
        elements.push({
          i:            path + i,
          start:        item.startIndex,
          end:          item.endIndex,
          isListItem:   !!item.paragraph.bullet,
          nestingLevel: item.paragraph.bullet ? (item.paragraph.bullet.nestingLevel || 0) : null,
          text:         text
        });
      }
      if (item.table) {
        var rows = item.table.tableRows || [];
        for (var r = 0; r < rows.length; r++) {
          var cells = rows[r].tableCells || [];
          for (var c = 0; c < cells.length; c++) {
            walk(cells[c].content || [], path + i + '.r' + r + 'c' + c + '.');
          }
        }
      }
    }
  }
  walk(content, '');

  GasLogger.log('test.dump_doc_paragraphs', { docId: docId, count: elements.length });
  GasLogger.flush();
  return _jsonResponse({ ok: true, docId: docId, elements: elements });
}

// ---------------------------------------------------------------------------
// dump_raw_docs_api handler  (testRouteNames — testToken-gated, gts-283i.1)
// ---------------------------------------------------------------------------

/**
 * Unfiltered Docs.Documents.get() JSON dump — no `fields` mask, so the full
 * response shape (inlineObjects, positionedObjects, tables, suggestions,
 * tabs) comes back verbatim. Exists solely to seed the gts-283i.1 design
 * spike's raw-capture asset (embedded-image inlineObjectProperties shape,
 * box/table-cell structure) — unlike dump_doc_paragraphs (a curated,
 * fields-masked structural view for paragraph-boundary diagnosis), this
 * route intentionally returns everything so a human/agent can inspect
 * structure not yet known to matter. Read-only: a Docs API GET, mutates
 * nothing.
 *
 * Payload: { action:'dump_raw_docs_api', testToken, docId,
 *   includeTabsContent? (default true) }
 * Response: { ok, docId, document } | { error }
 */
function _handleDumpRawDocsApi(payload) {
  var tokenError = _checkTestToken(payload.testToken || '');
  if (tokenError) return tokenError;

  var docId = payload.docId || '';
  if (!docId) return _jsonResponse({ error: 'docId required' });

  var includeTabsContent = payload.includeTabsContent !== false;
  var url = 'https://docs.googleapis.com/v1/documents/' + docId +
    '?suggestionsViewMode=SUGGESTIONS_INLINE' +
    '&includeTabsContent=' + includeTabsContent;
  var resp = UrlFetchApp.fetch(url, {
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    muteHttpExceptions: true
  });
  if (resp.getResponseCode() !== 200) {
    return _jsonResponse({
      error: 'Docs API error: ' + resp.getResponseCode(),
      body: resp.getContentText()
    });
  }

  var document = JSON.parse(resp.getContentText());
  GasLogger.log('test.dump_raw_docs_api', { docId: docId });
  GasLogger.flush();
  return _jsonResponse({ ok: true, docId: docId, document: document });
}

// ---------------------------------------------------------------------------
// export_governance_json handler  (testToken-gated, gts-2glm)
// ---------------------------------------------------------------------------

/**
 * Headless call-site into src/Procedure-Exporter.js's exportGovernance_(),
 * for the [TST] twin (gts-2glm) of the governance-exporter feature
 * (gts-ipoy). exportGovernance_ only accepted DocumentApp.getActiveDocument()
 * (add-on-UI-session-only) before this bead added the options.docId seam —
 * this route is the seam's only caller; the real UI entry points
 * (onGovernanceExportMenu/onGovernanceExportAndPdfMenu, the Extensions-menu
 * universalActions in Procedure-Exporter.js) never pass docId and always
 * resolve the active document, unchanged. The Extensions-menu Export dialog
 * (runExportForDialog, gts-s7ut) also never passes onProgress through this
 * route — it calls exportGovernance_ directly via google.script.run.
 *
 * Does NOT write the JSON/PDF file to Drive-as-observable-state beyond what
 * exportGovernance_ itself always does (it writes a Drive file as a side
 * effect regardless of caller) — this route additionally returns the JSON
 * body inline so a test can assert against it without a second Drive round
 * trip.
 *
 * Payload: { action:'export_governance_json', testToken, docId,
 *   exportPdf? (default false), includeWholeDocumentViews? (default false) }
 * Response: { ok, json, jsonFileId, exportFolderId, pdfFileId? } | { error }
 *
 * exportFolderId (gts-z6j0) is the Drive folder the JSON/PDF were actually
 * written into -- getExportFolder_()'s per-document isolated export folder
 * when EXPORT_ROOT_FOLDER_ID is configured, or the source document's own
 * parent folder as a fallback otherwise. Exposed so tests can assert export
 * isolation without a direct Drive API call.
 */
function _handleExportGovernanceJson(payload) {
  var tokenError = _checkTestToken(payload.testToken || '');
  if (tokenError) return tokenError;

  var docId = payload.docId || '';
  if (!docId) return _jsonResponse({ error: 'docId required' });

  try {
    var result = exportGovernance_({
      docId: docId,
      exportPdf: !!payload.exportPdf,
      includeWholeDocumentViews: !!payload.includeWholeDocumentViews
    });
    var response = { ok: true, json: result.json, jsonFileId: result.jsonFile.getId() };
    var parents = result.jsonFile.getParents();
    if (parents.hasNext()) response.exportFolderId = parents.next().getId();
    if (result.pdfFile) response.pdfFileId = result.pdfFile.getId();
    return _jsonResponse(response);
  } catch (ex) {
    GasLogger.log('test.export_governance_json.error', { docId: docId, msg: ex.message });
    return _jsonResponse({ error: ex.message });
  }
}

// ---------------------------------------------------------------------------
// run_export_for_dialog_test / get_export_progress_for_dialog_test handlers
// (testToken-gated, gts-0002 — [TST] twin of gts-s7ut)
// ---------------------------------------------------------------------------

/**
 * Headless call-site into src/Procedure-Exporter.js's runExportForDialog(),
 * the google.script.run entry point ExportProgressDialog.html invokes to
 * start a classic-menu export. runExportForDialog is a plain function (not
 * CardService/Ui-bound), so it is directly callable here the same way
 * exportGovernance_ is via export_governance_json (gts-2glm) — no dialog/UI
 * session needed.
 *
 * Payload: { action:'run_export_for_dialog_test', testToken, docId, exportPdf? }
 * Response: { ok, jsonFileId, pdfFileId?, jsonContent, pdfBase64? } | { error }
 * jsonContent/pdfBase64 (gts-283i.2) pass through runExportForDialog's own
 * return value unchanged — the same bytes/string the classic-menu dialog's
 * client-side Blob download now uses, exposed here so a headless caller can
 * download the export artifacts locally without a second Drive round trip.
 *
 * Mirrors runExportForDialog's own contract: on failure it writes the
 * EXPORT_STATUS_ 'error' state and rethrows — this route lets that
 * exception surface as {error} for the caller, while the durable
 * EXPORT_STATUS_ property is asserted separately via
 * get_export_progress_for_dialog_test.
 */
function _handleRunExportForDialogTest(payload) {
  var tokenError = _checkTestToken(payload.testToken || '');
  if (tokenError) return tokenError;

  var docId = payload.docId || '';
  if (!docId) return _jsonResponse({ error: 'docId required' });

  try {
    var result = runExportForDialog(docId, !!payload.exportPdf);
    return _jsonResponse({
      ok: true,
      jsonFileId: result.jsonFileId,
      pdfFileId: result.pdfFileId,
      jsonContent: result.jsonContent,
      pdfBase64: result.pdfBase64
    });
  } catch (ex) {
    GasLogger.log('test.run_export_for_dialog.error', { docId: docId, msg: ex.message });
    return _jsonResponse({ error: ex.message });
  }
}

/**
 * Headless call-site into src/Procedure-Exporter.js's
 * getExportProgressForDialog() — the google.script.run poll target
 * ExportProgressDialog.html calls every ~1.5s. Plain EXPORT_STATUS_<docId>
 * ScriptProperty read, so directly callable here without a dialog/UI
 * session, letting a test read the same durable state runExportForDialog
 * wrote without racing the real ~1.5s poll interval.
 *
 * Payload: { action:'get_export_progress_for_dialog_test', testToken, docId }
 * Response: { ok, status } | { error }  (status is null if no export has
 *   ever run for this docId)
 */
function _handleGetExportProgressForDialogTest(payload) {
  var tokenError = _checkTestToken(payload.testToken || '');
  if (tokenError) return tokenError;

  var docId = payload.docId || '';
  if (!docId) return _jsonResponse({ error: 'docId required' });

  return _jsonResponse({ ok: true, status: getExportProgressForDialog(docId) });
}

/**
 * Generic Docs-API batchUpdate passthrough (testToken-gated, gts-2glm).
 * Lets a test build arbitrary formatted seed content — headings, tables,
 * explicit page breaks, manual highlight colors, bold-colon labels — using
 * the standard Docs API request shape directly, rather than this file
 * growing a bespoke GAS-side builder function per test scenario. Read-only
 * elsewhere in this file's philosophy does not apply here: this route
 * exists ONLY to construct fixture documents, never called by production
 * code or by the exporter itself.
 *
 * Payload: { action:'seed_doc_content', testToken, docId, requests:[...] }
 *   (requests is passed verbatim to Docs.Documents.batchUpdate's body)
 * Response: { ok, replies } | { error }
 */
function _handleSeedDocContent(payload) {
  var tokenError = _checkTestToken(payload.testToken || '');
  if (tokenError) return tokenError;

  var docId = payload.docId || '';
  if (!docId) return _jsonResponse({ error: 'docId required' });
  if (!payload.requests || !payload.requests.length) {
    return _jsonResponse({ error: 'requests (non-empty array) required' });
  }

  try {
    var result = Docs.Documents.batchUpdate({ requests: payload.requests }, docId);
    return _jsonResponse({ ok: true, replies: result.replies || [] });
  } catch (ex) {
    return _jsonResponse({ error: ex.message });
  }
}

/**
 * Test-only rename (gts-es3l). begin_journey_session titles always include a
 * random hex suffix (TestFixtures.js's bjsHex) precisely so two journey docs
 * never collide by accident -- but the export-folder-isolation hardening
 * test (gts-z6j0's docId-keyed-not-name-keyed index) needs a deliberate
 * title collision between two different docIds, which the Docs API's
 * batchUpdate (seed_doc_content, above) cannot produce: title is a Drive
 * file property, not part of document body content. Never called by
 * production code or by the exporter itself.
 *
 * Payload: { action:'rename_doc_for_test', testToken, docId, title }
 * Response: { ok, docId, title } | { error }
 */
function _handleRenameDocForTest(payload) {
  var tokenError = _checkTestToken(payload.testToken || '');
  if (tokenError) return tokenError;

  var docId = payload.docId || '';
  var title = payload.title || '';
  if (!docId || !title) return _jsonResponse({ error: 'docId and title required' });

  try {
    DriveApp.getFileById(docId).setName(title);
    return _jsonResponse({ ok: true, docId: docId, title: title });
  } catch (ex) {
    return _jsonResponse({ error: ex.message });
  }
}

/**
 * Test-only diagnostic (gts-es3l) — see dumpExportIndexRowsForTest_'s
 * docstring (src/ExportFolderMap.js). Never called by production code.
 *
 * Payload: { action:'dump_export_index_for_test', testToken, docId }
 * Response: { ok, rows } | { error }
 */
function _handleDumpExportIndexForTest(payload) {
  var tokenError = _checkTestToken(payload.testToken || '');
  if (tokenError) return tokenError;

  var docId = payload.docId || '';
  if (!docId) return _jsonResponse({ error: 'docId required' });

  try {
    return _jsonResponse({ ok: true, rows: dumpExportIndexRowsForTest_(docId) });
  } catch (ex) {
    return _jsonResponse({ error: ex.message });
  }
}

/**
 * Drive-comment seeding passthrough (testToken-gated, gts-2glm). The
 * governance exporter's comment-to-document traceability (associate
 * CommentsToBlocks_) needs real Drive comments with quoted_text to test
 * against — DriveV3.Comments.create (unlike Docs suggested-edits, which the
 * public API cannot create) is fully supported, so this is a direct
 * passthrough rather than a synthetic fixture.
 *
 * Payload: { action:'create_doc_comment', testToken, docId,
 *   content, quotedText? }
 * Response: { ok, commentId } | { error }
 */
function _handleCreateDocComment(payload) {
  var tokenError = _checkTestToken(payload.testToken || '');
  if (tokenError) return tokenError;

  var docId = payload.docId || '';
  if (!docId) return _jsonResponse({ error: 'docId required' });
  if (!payload.content) return _jsonResponse({ error: 'content required' });

  try {
    var comment = { content: payload.content };
    if (payload.quotedText) {
      comment.quotedFileContent = { mimeType: 'text/plain', value: payload.quotedText };
    }
    var created = DriveV3.Comments.create(comment, docId, { fields: 'id' });
    return _jsonResponse({ ok: true, commentId: created.id });
  } catch (ex) {
    return _jsonResponse({ error: ex.message });
  }
}

// ---------------------------------------------------------------------------
// read_team_actions handler  (testRouteNames — testToken-gated,
// gts-79dw.4.11 slice 1)
// ---------------------------------------------------------------------------

/**
 * Exposes _readTeamActions' full parameter surface so the harness can capture
 * a real fixture for every filter state (open / closed / all / mine / window
 * boundary) that gts-79dw.4.7's View A review needs. Read-only.
 *
 * This exists so the PRODUCTION list_importable_actions contract does not
 * grow optional filter parameters that only a fixture capture would ever
 * send. It is testToken-gated, not WEBAPP_SECRET-gated, and applies no
 * team-access gate of its own — holding the per-deployment test token IS the
 * authorization, as with the other testRouteNames routes.
 *
 * Payload shape (ContractSchema.js messages.read_team_actions):
 *   { action:'read_team_actions', testToken, teamId | docId, statusFilter,
 *     windowDays, excludeDocId, assigneeEmail }
 * `docId` is an alternative to `teamId`: the team is resolved from its
 * DocData row, the same join list_importable_actions performs.
 *
 * Response shape: { ok:true, teamId, rows:[<TEAM_ACTION_FIELDS>], statusOptions }
 * Each row already carries getStatusDisplay()'s answer for its status, so no
 * consumer re-derives the bucketing. `statusOptions` is getStatusIconButtons()
 * — the same canonical picker list the sidebar's status control offers.
 */
function _handleReadTeamActions(payload) {
  var tokenError = _checkTestToken(payload.testToken || '');
  if (tokenError) return tokenError;

  var ss     = _openActionSheetSpreadsheet();
  var teamId = payload.teamId || _resolveTeamIdForDoc(ss, payload.docId || '');

  var rows = _readTeamActions(teamId, {
    statusFilter:  payload.statusFilter,
    windowDays:    payload.windowDays,
    excludeDocId:  payload.excludeDocId,
    assigneeEmail: payload.assigneeEmail,
    ss:            ss
  });

  GasLogger.log('teamActions.read', {
    teamId:       teamId,
    statusFilter: payload.statusFilter || 'open',
    count:        rows.length
  });
  GasLogger.flush();

  return _jsonResponse({
    ok:            true,
    teamId:        teamId,
    rows:          rows,
    statusOptions: getStatusIconButtons()
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

  var docId = payload.docId || '';
  var rows  = _findSheetActionsForDoc(ss, docId);

  GasLogger.log('test.find_sheet_actions', { docId: docId, count: rows.length });
  GasLogger.flush();
  return _jsonResponse({ ok: true, docId: docId, rows: rows });
}

/**
 * Core docId-scoped Actions reader shared by _handleFindSheetActions
 * (TEST_TOKEN-gated, bead .9) and _handleGetDocumentActions (GIS-assertion-
 * gated View B, gts-79dw.4.13) -- the reuse constraint (plan §11) is that
 * View B adds a THIRD gate over this SAME reader rather than a second
 * implementation. Read-only, no mutation. doc_id / doc_name are DERIVED from
 * the document_formula (col 7), not stored columns (Coordination Log .1 §7
 * #1). Returns [] (never throws) when the Actions sheet has no header row
 * yet -- callers needing to distinguish "sheet missing" from "no rows" must
 * check sheet presence themselves before calling (see
 * _handleFindSheetActions above).
 *
 * @param {Spreadsheet} ss
 * @param {string} docId
 * @returns {Array<Object>} SheetAction-shaped rows (ContractSchema.js
 *   sheetAction.fields), filtered to docId when non-empty.
 */
function _findSheetActionsForDoc(ss, docId) {
  var actionsSheet = ss.getSheetByName('Actions');
  if (!actionsSheet) return [];

  var lastRow = actionsSheet.getLastRow();
  if (lastRow < 2) return [];

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

  return rows;
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

  GasLogger.log('test.patch_action_status', { globalId: globalId, status: newStatus });
  GasLogger.flush();
  return _jsonResponse({ ok: true, global_id: globalId });
}

/**
 * ATDD-path forward_action_rows_test: same seen[]/isResolved(entry.status)
 * guard loop as the production _handleForwardActionRows, testToken-gated
 * instead of secret-gated (gts-apcu, UC-E AC4). Lets a test pass an
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

      var newAiToken = parseGlobalId(f.newGlobalId).actionId; // e.g. 'ACT-N' or legacy 'AI-N'
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

  GasLogger.log('test.delete_action_row', { globalId: globalId });
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

  // Idempotency guard (gts-f3me.1): scn/session.py's _http_post retries on HTTP
  // 404 / a non-JSON echo-page response, on the assumption the first attempt
  // never reached this handler. When it DID reach the handler and only the
  // *response* was lost to the /exec -> script.googleusercontent.com routing
  // glitch, a bare retry re-appends the same paragraph a second time (observed
  // as a duplicated Actions row after sync). Dedupe on the client-supplied
  // opId, which _http_post reuses across every retry attempt of one logical
  // call. Cache TTL only needs to cover the retry loop's worst case
  // (_HTTP_POST_MAX_ATTEMPTS=3 * _HTTP_POST_RETRY_DELAY_S=3s + handler time);
  // 120s is a comfortable margin over that.
  var opId = payload.opId || '';
  var cache = opId ? CacheService.getScriptCache() : null;
  var cacheKey = opId ? ('append_doc_paragraph:' + opId) : null;
  if (cache) {
    var cached = cache.get(cacheKey);
    if (cached) {
      return _jsonResponse(JSON.parse(cached));
    }
  }

  var doc = withGasRetry('WebApp._handleAppendDocParagraph:DocumentApp.openById',
    function () { return DocumentApp.openById(docId); });
  doc.getBody().appendParagraph(text);
  doc.saveAndClose();

  var response = { ok: true, docId: docId };
  if (cache) {
    cache.put(cacheKey, JSON.stringify(response), 120);
  }

  GasLogger.log('test.append_doc_paragraph', { docId: docId, textLen: text.length });
  GasLogger.flush();
  return _jsonResponse(response);
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
    var folderIter = sheetId
      ? withGasRetry('WebApp._handleJourneySession.begin:DriveApp.getFileById',
          function () { return DriveApp.getFileById(sheetId).getParents(); })
      : null;
    var parent     = (folderIter && folderIter.hasNext())
                     ? folderIter.next()
                     : DriveApp.getRootFolder();

    var bjsDoc = DocumentApp.create(docName);
    withGasRetry('WebApp._handleJourneySession.begin:DriveApp.getFileById.moveTo',
      function () { DriveApp.getFileById(bjsDoc.getId()).moveTo(parent); });

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
    withGasRetry('WebApp._handleJourneySession.end:DriveApp.getFileById.setTrashed',
      function () { DriveApp.getFileById(docId).setTrashed(true); });
    GasLogger.log('journey.end', { docId: docId });
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
