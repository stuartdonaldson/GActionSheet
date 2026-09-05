/**
 * AdminDocScan.js — admin-only scan of a team's registered Drive folder(s)
 * for Google Docs that look action-bearing but aren't yet tracked in DocData.
 *
 * gts-gwyg introduced this as a single synchronous scan bounded by an
 * in-request wall-clock budget. gts-lgpx replaced that with a RESUMABLE scan
 * whose progress lives in a Script Property, advanced by a self-rescheduling
 * one-shot trigger. The reason is measured, not theoretical: against a real
 * team folder (TEST v0.2.3.86, op 80a84bf2) the old scan reported
 * scanned=261 matched=0 complete=false elapsedMs=271215 — ~1.04s per doc,
 * essentially all of it DocumentApp.openById — and, because it rebuilt its
 * DFS stack from the folder root on every call with no persisted cursor,
 * re-running it re-scanned the same first 261 docs forever. Anything past
 * the cutoff was unreachable, while the UI cheerfully said "run again to
 * continue".
 *
 * TWO PHASES. The UI has to show "N of M", and a single fused walk can never
 * report M until it has finished. So:
 *   phase 'enumerate' — DriveApp folder walk only, NO doc opens. Cheap (the
 *     doc opens were ~100% of the old runtime). Produces the queue of
 *     untracked candidate fileIds, and therefore M.
 *   phase 'match'     — pops fileIds off that queue, doing the bounded
 *     doc-open check. The cursor is a plain integer index, so progress is
 *     monotonic and a resume never redoes finished work.
 *
 * STORAGE. Script Property values cap at 9KB and a real queue blows past
 * that (261 ids ≈ 11.5KB), so the queue and the candidate list are both
 * written through _scanListWrite/_scanListRead, which shard across
 * <key>_0, <key>_1, … One helper, two callers (I12) — the small JSON state
 * blob itself stays well under the cap because neither list is ever inlined
 * into it. The status-blob-in-a-property shape follows the existing
 * _readExportStatus_/_writeExportStatus_ precedent in Procedure-Exporter.js
 * rather than inventing a second convention.
 *
 * Entry points (all routed in src/WebApp.js):
 *   admin_scan_start   — clears state, seeds the folder stack for ONE team,
 *                        schedules the one-shot, returns immediately (no
 *                        doc reads).
 *   admin_scan_status  — read-only progress, for UI polling.
 *   admin_scan_resume  — reschedules a stalled/incomplete scan.
 *   resumeAdminDocScan — the trigger handler itself (global, GAS-callable).
 *   nightlyAdminScanAllTeams — installed by TriggerManager.js as a daily
 *                        1am trigger. Seeds the SAME state machine with every
 *                        team's teamId queued up (state.teamsQueue); when one
 *                        team's match phase drains, _advanceToNextTeamOrDone
 *                        rolls the state onto the next team's enumerate phase
 *                        instead of finishing, so candidates accumulate
 *                        across the whole run rather than being scanned and
 *                        discarded team by team. A manual single-team scan
 *                        (admin_scan_start) is the same machinery with an
 *                        empty teamsQueue — it finishes after one team.
 *
 * Each queue/candidate entry carries teamId and path (the Drive folder
 * breadcrumb from the team's registered root down to the doc's immediate
 * parent) so the untracked-docs list can show which team a candidate
 * belongs to and where it lives — necessary once a single scan (the nightly
 * run) can span every team at once.
 *
 * Admin identity is NOT the ADMIN_SECRET gate (src/Admin.js) — the caller is
 * the verified-team-portal client, which cannot hold that secret. The
 * caller's verified email (_verifySignedAssertion, src/AccessControl.js) is
 * checked against the Config sheet's 'AdminUsers' row (_isAdminUser), the
 * same identity resolution TeamListing.js's _handleListTeamActions already
 * uses for its isAdmin response field. Every route above is gated, including
 * the read-only status route.
 */

/** Single JSON progress blob. Lists live in sharded siblings, never inline. */
var ADMIN_DOC_SCAN_STATE_PROP = 'ADMIN_DOC_SCAN_STATE';
var ADMIN_DOC_SCAN_QUEUE_PROP = 'ADMIN_DOC_SCAN_QUEUE';
var ADMIN_DOC_SCAN_CANDIDATES_PROP = 'ADMIN_DOC_SCAN_CANDIDATES';

/** Per-pass wall-clock budget. Well under GAS's 6-minute execution ceiling so
 *  a pass always gets to persist its cursor and reschedule before being
 *  killed — an unpersisted pass is wasted work, not just a slow one. */
var ADMIN_DOC_SCAN_PASS_BUDGET_MS = 4 * 60 * 1000;

/** Delay before the next one-shot resume fires. */
var ADMIN_DOC_SCAN_RESUME_DELAY_MS = 60 * 1000;

/** A pass claiming status:'running' with a heartbeat older than this crashed
 *  mid-flight (GAS caps execution at 6 min, so a live pass cannot be quieter
 *  than this). Such a scan is resumable rather than wedged forever. */
var ADMIN_DOC_SCAN_STALE_MS = 7 * 60 * 1000;

/** Trigger handler name — must match the global function at the bottom. */
var ADMIN_DOC_SCAN_TRIGGER_HANDLER = 'resumeAdminDocScan';

/** Ids per sharded list property. ~44 bytes each; 150 keeps a shard ≈6.6KB,
 *  comfortably inside the 9KB per-value cap with JSON overhead. */
var ADMIN_DOC_SCAN_SHARD_SIZE = 150;

/** Cap on candidates retained for display, so a pathological folder cannot
 *  grow the candidate list without bound. */
var ADMIN_DOC_SCAN_MAX_CANDIDATES = 500;

/**
 * @param {string} email
 * @returns {boolean} true if email (case/whitespace-insensitive) appears in
 *   the Config sheet's 'AdminUsers' comma-separated value.
 */
function _isAdminUser(email) {
  if (!email) return false;
  var normalized = String(email).trim().toLowerCase();
  var ss = _openActionSheetSpreadsheet();
  var sheet = ss.getSheetByName('Config');
  if (!sheet) return false;
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return false;
  var cols = CONTRACT_SCHEMA.sheetConfig.columnsByField;
  var values = sheet.getRange(2, 1, lastRow - 1, CONTRACT_SCHEMA.sheetConfig.headers.length).getValues();
  for (var i = 0; i < values.length; i++) {
    if (values[i][cols.key - 1] !== 'AdminUsers') continue;
    var rawValue = values[i][cols.value - 1] || '';
    var admins = String(rawValue).split(',');
    for (var a = 0; a < admins.length; a++) {
      if (admins[a].trim().toLowerCase() === normalized) return true;
    }
    return false;
  }
  return false;
}

/**
 * Cheap "does this Doc look action-bearing" check via a plain-text read of
 * the doc's body. Fails closed (returns false, never throws) on any read
 * error — an unreadable/unsupported file is simply not surfaced as a
 * candidate rather than aborting the whole scan.
 *
 * Three different Advanced Drive Service export approaches were tried live
 * (gts-gwyg, 2026-09-01) and each failed in a distinct way: (1)
 * `Drive.Files.export(fileId, mimeType, {alt:'media'})` throws even on a
 * successful response because the library expects a JSON envelope and gets
 * raw bytes instead -- and its exception message embeds the ENTIRE
 * document body (this leaked real content, including a live team's meeting
 * notes with real names, into Axiom logs the first time this ran against a
 * real team folder -- see gts-gwyg's bd notes); (2) `Drive.Files.get(fileId,
 * {fields:'exportLinks'})` consistently threw GoogleJsonResponseException;
 * (3) fetching the resulting export link via UrlFetchApp threw a generic
 * Exception, most likely urlFetchWhitelist (src/appsscript.json) not
 * covering the actual export-link host/path. Given three distinct failures
 * in the "avoid DocumentApp" direction, this uses the same
 * DocumentApp.openById(...).getBody().getText() pattern every other reader
 * in this codebase (SyncManager.js) already relies on -- it takes a
 * doc-open lock DriveApp/UrlFetchApp wouldn't have, but it is proven
 * reliable here, and still never runs the full sync/parse pipeline (no
 * floating-action detection, no table scan, no row parsing) -- just a
 * regex check against the plain text, which is what the AC actually
 * requires.
 *
 * gts-vsjv: the pattern is _ACTION_TOKEN_SCAN_REGEX (src/ActionToken.js),
 * derived from the shared _ACTION_TOKEN_READ_PREFIXES. The previous
 * hand-rolled /ACT(-\d+)?:/ here matched only the ACT spelling and so could
 * never match a legacy AI-N: document — which is precisely the untracked
 * population this scan exists to find. That bug is why a real Board-folder
 * run returned matched=0 across 261 successfully-read docs.
 *
 * @param {string} fileId
 * @returns {boolean}
 */
function _quickMatchActionDoc(fileId) {
  try {
    var text = DocumentApp.openById(fileId).getBody().getText();
    return _ACTION_TOKEN_SCAN_REGEX.test(text);
  } catch (e) {
    // Never log e.message/String(e) here -- an exception on a doc-content
    // read can embed that content (confirmed live, see comment above).
    GasLogger.log('admin.scanTeamDocs.exportError', { fileId: fileId });
    return false;
  }
}

// ---------------------------------------------------------------------------
// Progress state
// ---------------------------------------------------------------------------

/** @returns {Object|null} the persisted scan state, or null when idle. */
function _readScanState() {
  var raw = PropertiesService.getScriptProperties().getProperty(ADMIN_DOC_SCAN_STATE_PROP);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (e) {
    // A corrupt blob must not wedge the feature permanently — treat it as
    // idle so a fresh start can overwrite it.
    return null;
  }
}

/** Persists state, stamping updatedAt (the heartbeat running/waiting and the
 *  stale check both read). Mirrors _writeExportStatus_ in Procedure-Exporter.js. */
function _writeScanState(state) {
  state.updatedAt = new Date().toISOString();
  PropertiesService.getScriptProperties()
    .setProperty(ADMIN_DOC_SCAN_STATE_PROP, JSON.stringify(state));
  return state;
}

/**
 * Writes an array across sharded properties (<key>_0, <key>_1, …), because a
 * real queue exceeds the 9KB per-value cap. Deletes shards beyond the new
 * length so a shorter list never leaves a stale tail behind.
 * @returns {number} shard count written.
 */
function _scanListWrite(key, items) {
  var props = PropertiesService.getScriptProperties();
  var chunks = Math.ceil(items.length / ADMIN_DOC_SCAN_SHARD_SIZE);
  for (var i = 0; i < chunks; i++) {
    props.setProperty(key + '_' + i,
      JSON.stringify(items.slice(i * ADMIN_DOC_SCAN_SHARD_SIZE, (i + 1) * ADMIN_DOC_SCAN_SHARD_SIZE)));
  }
  // Clear any shards left over from a previously longer list.
  for (var j = chunks; ; j++) {
    if (props.getProperty(key + '_' + j) === null) break;
    props.deleteProperty(key + '_' + j);
  }
  return chunks;
}

/** Reads back a sharded list written by _scanListWrite. */
function _scanListRead(key, chunks) {
  var props = PropertiesService.getScriptProperties();
  var out = [];
  for (var i = 0; i < (chunks || 0); i++) {
    var raw = props.getProperty(key + '_' + i);
    if (!raw) continue;
    try {
      out = out.concat(JSON.parse(raw));
    } catch (e) {
      // A single unreadable shard degrades the list rather than killing the
      // scan; the cursor still advances past it.
    }
  }
  return out;
}

/** Removes every property this feature owns — state plus both sharded lists. */
function _clearScanState() {
  var props = PropertiesService.getScriptProperties();
  props.deleteProperty(ADMIN_DOC_SCAN_STATE_PROP);
  var keys = [ADMIN_DOC_SCAN_QUEUE_PROP, ADMIN_DOC_SCAN_CANDIDATES_PROP];
  for (var k = 0; k < keys.length; k++) {
    for (var i = 0; ; i++) {
      if (props.getProperty(keys[k] + '_' + i) === null) break;
      props.deleteProperty(keys[k] + '_' + i);
    }
  }
}

/**
 * True when a state claims to be executing but its heartbeat is older than a
 * full GAS execution ceiling — i.e. the pass died without persisting. Such a
 * scan must stay resumable; otherwise one crashed pass wedges the team's
 * scan until someone manually clears a Script Property.
 */
function _isScanStale(state) {
  if (!state || state.status !== 'running') return false;
  var updated = Date.parse(state.updatedAt || '');
  if (!updated) return true;
  return (Date.now() - updated) > ADMIN_DOC_SCAN_STALE_MS;
}

/** A scan still has work to do (whether running, waiting, or stale). */
function _isScanIncomplete(state) {
  return !!state && state.phase !== 'done';
}

// ---------------------------------------------------------------------------
// Trigger lifecycle — self-rescheduling one-shot (human decision D1)
// ---------------------------------------------------------------------------

/**
 * Deletes every existing one-shot for this handler. Called before scheduling
 * a new one and on completion, so repeated scans cannot accumulate orphaned
 * triggers against the 20-per-script quota that the standing 30-min syncAll
 * trigger (src/TriggerManager.js) also draws from.
 */
function _deleteScanTriggers() {
  var triggers = ScriptApp.getProjectTriggers();
  var removed = 0;
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === ADMIN_DOC_SCAN_TRIGGER_HANDLER) {
      ScriptApp.deleteTrigger(triggers[i]);
      removed++;
    }
  }
  return removed;
}

/** Replaces any pending one-shot with a fresh one. Idempotent by construction
 *  — two resume calls leave exactly one trigger, never two. */
function _scheduleScanTrigger() {
  _deleteScanTriggers();
  ScriptApp.newTrigger(ADMIN_DOC_SCAN_TRIGGER_HANDLER)
    .timeBased()
    .after(ADMIN_DOC_SCAN_RESUME_DELAY_MS)
    .create();
}

// ---------------------------------------------------------------------------
// The scan itself
// ---------------------------------------------------------------------------

/**
 * Advances the scan by one bounded pass and persists the result. Safe to call
 * with no scan pending (returns null without touching anything) — the trigger
 * can fire after a scan already finished.
 *
 * @returns {Object|null} the state after this pass.
 */
function _advanceScanPass() {
  var state = _readScanState();
  if (!_isScanIncomplete(state)) return state;

  // Claim the pass. If another execution is genuinely mid-flight (fresh
  // heartbeat), don't double-advance the same cursor.
  if (state.status === 'running' && !_isScanStale(state)) return state;

  var startTime = Date.now();
  state.status = 'running';
  _writeScanState(state);

  try {
    if (state.phase === 'enumerate') {
      _advanceEnumeratePass(state, startTime);
    }
    if (state.phase === 'match') {
      _advanceMatchPass(state, startTime);
    }
  } catch (e) {
    // Never surface a doc-content-bearing message (see _quickMatchActionDoc).
    state.status = 'error';
    state.error = String(e && e.name || 'Error');
    _writeScanState(state);
    _deleteScanTriggers();
    GasLogger.log('admin.scanTeamDocs.pass', {
      teamId: state.teamId, phase: state.phase, scanned: state.scanned,
      total: state.total, matched: state.matched, complete: false
    });
    GasLogger.flush();
    return state;
  }

  var complete = state.phase === 'done';
  state.status = complete ? 'done' : 'waiting';
  _writeScanState(state);

  if (complete) {
    _deleteScanTriggers();
    GasLogger.log('admin.scanTeamDocs.complete', {
      teamId: state.teamId, scanned: state.scanned, total: state.total,
      matched: state.matched, elapsedMs: Date.now() - Date.parse(state.startedAt)
    });
  } else {
    _scheduleScanTrigger();
  }

  GasLogger.log('admin.scanTeamDocs.pass', {
    teamId: state.teamId, phase: state.phase, scanned: state.scanned,
    total: state.total, matched: state.matched, complete: complete
  });
  GasLogger.flush();
  return state;
}

/**
 * Phase 1: walk the folder stack collecting untracked Google Doc ids. No doc
 * bodies are opened here, which is what makes producing the total cheap.
 * The stack itself is the resume cursor and is persisted every pass.
 *
 * Stack entries are {id, path} — path is the breadcrumb of folder NAMES from
 * the team's registered root down to (not including) this folder's own
 * name, so a queued file's full path is computed once, cheaply, as this
 * folder is opened (one getName() call per folder visited, not per file).
 */
function _advanceEnumeratePass(state, startTime) {
  var queue = _scanListRead(ADMIN_DOC_SCAN_QUEUE_PROP, state.queueChunks);
  var ss = _openActionSheetSpreadsheet();
  var trackedFileIds = {};
  var docDataRows = _readDocDataRows(ss);
  for (var d = 0; d < docDataRows.length; d++) trackedFileIds[docDataRows[d].fileId] = true;

  while (state.folderStack.length) {
    if (Date.now() - startTime > ADMIN_DOC_SCAN_PASS_BUDGET_MS) break;
    var stackEntry = state.folderStack.pop();
    var folder;
    try {
      folder = DriveApp.getFolderById(stackEntry.id);
    } catch (e) {
      continue; // an unreadable/removed folder skips, it doesn't abort
    }
    var parentPath = stackEntry.path || '';
    var thisPath = parentPath ? parentPath + '/' + folder.getName() : folder.getName();

    var subfolders = folder.getFolders();
    while (subfolders.hasNext()) {
      state.folderStack.push({ id: subfolders.next().getId(), path: thisPath });
    }

    var files = folder.getFilesByType(MimeType.GOOGLE_DOCS);
    while (files.hasNext()) {
      var file = files.next();
      var fileId = file.getId();
      if (trackedFileIds[fileId]) continue;
      queue.push({ id: fileId, name: file.getName(), url: file.getUrl(), teamId: state.teamId, path: thisPath });
    }
  }

  state.queueChunks = _scanListWrite(ADMIN_DOC_SCAN_QUEUE_PROP, queue);
  // Progress signal while total is still unknown: how many candidate docs the
  // walk has turned up so far. Lets the UI say "Enumerating — 261 found"
  // rather than an uninformative "0 of ?".
  state.queued = queue.length;
  if (!state.folderStack.length) {
    // Enumeration finished: the total is now exactly known.
    state.phase = 'match';
    state.total = queue.length;
  }
  _writeScanState(state);
}

/**
 * Phase 2: open each queued doc and test it. `cursor` is an index into the
 * persisted queue, so a resume never re-reads a doc an earlier pass already
 * paid ~1s for.
 */
function _advanceMatchPass(state, startTime) {
  var queue = _scanListRead(ADMIN_DOC_SCAN_QUEUE_PROP, state.queueChunks);
  var candidates = _scanListRead(ADMIN_DOC_SCAN_CANDIDATES_PROP, state.candidateChunks);
  var dirty = false;

  while (state.cursor < queue.length) {
    if (Date.now() - startTime > ADMIN_DOC_SCAN_PASS_BUDGET_MS) break;
    var entry = queue[state.cursor];
    state.cursor++;
    state.scanned++;
    if (entry && _quickMatchActionDoc(entry.id)) {
      if (candidates.length < ADMIN_DOC_SCAN_MAX_CANDIDATES) {
        candidates.push({ docId: entry.id, docName: entry.name, url: entry.url, teamId: entry.teamId, path: entry.path });
        dirty = true;
      }
      state.matched++;
    }
  }

  if (dirty) state.candidateChunks = _scanListWrite(ADMIN_DOC_SCAN_CANDIDATES_PROP, candidates);
  if (state.cursor >= queue.length) _advanceToNextTeamOrDone(state);
  _writeScanState(state);
}

/**
 * @param {Array<Object>} teamDataRows from _readTeamDataRows
 * @param {string} teamId
 * @returns {Array<string>} registered folder ids for that team.
 */
function _teamFolderIds(teamDataRows, teamId) {
  var folderIds = [];
  for (var t = 0; t < teamDataRows.length; t++) {
    if (teamDataRows[t].teamId === teamId && teamDataRows[t].folderId) folderIds.push(teamDataRows[t].folderId);
  }
  return folderIds;
}

/**
 * Called when a team's match-phase queue drains. A plain single-team scan
 * (admin_scan_start) leaves state.teamsQueue empty, so this always falls
 * through to 'done' — same behavior as before multi-team scans existed.
 * The nightly all-teams scan (nightlyAdminScanAllTeams)
 * seeds teamsQueue with every remaining teamId; this rolls the SAME state
 * object onto the next team's enumerate phase, WITHOUT touching
 * state.scanned/matched/candidateChunks — those accumulate across the whole
 * run, which is what lets the untracked-docs list show results from every
 * team in one place rather than being reset team by team.
 *
 * A team with no registered folders is skipped (no empty enumerate pass).
 */
function _advanceToNextTeamOrDone(state) {
  var ss = _openActionSheetSpreadsheet();
  var teamDataRows = _readTeamDataRows(ss);
  while (state.teamsQueue && state.teamsQueue.length) {
    var nextTeamId = state.teamsQueue.shift();
    var folderIds = _teamFolderIds(teamDataRows, nextTeamId);
    if (!folderIds.length) continue;
    state.teamId = nextTeamId;
    state.phase = 'enumerate';
    state.folderStack = folderIds.map(function (fid) { return { id: fid, path: '' }; });
    state.cursor = 0;
    state.queued = 0;
    state.total = null;
    state.queueChunks = _scanListWrite(ADMIN_DOC_SCAN_QUEUE_PROP, []);
    return;
  }
  state.phase = 'done';
}

// ---------------------------------------------------------------------------
// Routes
// ---------------------------------------------------------------------------

/**
 * Resolves the caller's identity for the admin scan routes.
 *
 * No live GIS ID token / shared HS256 assertion secret is available
 * non-interactively in this project's test environment (same documented gap
 * as tests/test_signed_assertion.py's mint_test_assertion path) — so, same
 * pattern as WebApp.js's testToken-gated variants of production routes
 * (e.g. patch_action_status/delete_action_row), a valid TEST_TOKEN lets a
 * test supply the identity email directly instead of a signed assertion.
 * This bypasses ONLY the assertion-signing step; _isAdminUser's Config!
 * AdminUsers check downstream still runs for real in both paths — a test
 * cannot grant itself admin status this way, only claim an identity to be
 * checked against the real admin list.
 *
 * @param {Object} payload { assertion } or { testToken, email }
 * @returns {{verified: boolean, email: string}}
 */
function _resolveScanIdentity(payload) {
  if (payload.testToken) {
    var tokenError = _checkTestToken(payload.testToken);
    if (tokenError) return { verified: false, email: '' };
    return { verified: !!payload.email, email: payload.email || '' };
  }
  var identity = _verifySignedAssertion(payload.assertion || '');
  return { verified: identity.verified, email: identity.email };
}

/** Shared gate for all three routes. @returns {null} when authorized. */
function _denyScanIfNotAdmin(payload, teamId) {
  var identity = _resolveScanIdentity(payload);
  if (!identity.verified || !_isAdminUser(identity.email)) {
    GasLogger.log('admin.scanTeamDocs.forbidden', { teamId: teamId });
    GasLogger.flush();
    return _jsonResponse({ ok: false, reason: 'forbidden' });
  }
  return null;
}

/** Public progress shape, shared by every route's response so the UI has one
 *  thing to render regardless of which call it came from. */
function _scanStatusPayload(state) {
  if (!state) {
    return { ok: true, teamId: '', phase: 'idle', status: 'idle', scanned: 0,
             total: null, queued: 0, foldersRemaining: 0, matched: 0,
             candidates: [], updatedAt: null, complete: false, error: null,
             allTeams: false, teamsRemaining: 0 };
  }
  return {
    ok: true,
    teamId: state.teamId,
    phase: state.phase,
    // A crashed pass still claims 'running' in storage; report what is
    // actually true so the UI offers Resume instead of a frozen spinner.
    status: _isScanStale(state) ? 'stale' : state.status,
    scanned: state.scanned,
    total: typeof state.total === 'number' ? state.total : null,
    queued: state.queued || 0,
    foldersRemaining: (state.folderStack || []).length,
    matched: state.matched,
    candidates: _scanListRead(ADMIN_DOC_SCAN_CANDIDATES_PROP, state.candidateChunks),
    updatedAt: state.updatedAt || null,
    complete: state.phase === 'done',
    error: state.error || null,
    // nightlyAdminScanAllTeams sets allTeams:true and seeds teamsQueue with
    // every other team; teamsRemaining lets the UI say "N more team(s)
    // queued" while state.teamId names the team currently being walked.
    allTeams: !!state.allTeams,
    teamsRemaining: (state.teamsQueue || []).length
  };
}

/** admin_scan_start — clears prior state and enqueues. Does NO doc reads. */
function _handleAdminScanStart(payload) {
  var teamId = payload.teamId || '';
  var denied = _denyScanIfNotAdmin(payload, teamId);
  if (denied) return denied;
  if (!teamId) return _jsonResponse({ ok: false, reason: 'teamId required' });

  var ss = _openActionSheetSpreadsheet();
  var teamDataRows = _readTeamDataRows(ss);
  var folderIds = _teamFolderIds(teamDataRows, teamId);
  if (!folderIds.length) return _jsonResponse({ ok: false, reason: 'no folders registered for team' });

  _clearScanState();
  var state = _writeScanState({
    teamId: teamId, teamsQueue: [], allTeams: false, phase: 'enumerate', status: 'waiting',
    startedAt: new Date().toISOString(),
    total: null, scanned: 0, matched: 0,
    folderStack: folderIds.map(function (fid) { return { id: fid, path: '' }; }), cursor: 0, queued: 0,
    queueChunks: 0, candidateChunks: 0, error: null
  });
  _scheduleScanTrigger();

  GasLogger.log('admin.scanTeamDocs.start', { teamId: teamId });
  GasLogger.flush();
  return _jsonResponse(_scanStatusPayload(state));
}

/** admin_scan_status — read-only progress for UI polling. Still admin-gated. */
function _handleAdminScanStatus(payload) {
  var teamId = payload.teamId || '';
  var denied = _denyScanIfNotAdmin(payload, teamId);
  if (denied) return denied;
  return _jsonResponse(_scanStatusPayload(_readScanState()));
}

/** admin_scan_resume — reschedules an incomplete or stale scan. */
function _handleAdminScanResume(payload) {
  var teamId = payload.teamId || '';
  var denied = _denyScanIfNotAdmin(payload, teamId);
  if (denied) return denied;

  var state = _readScanState();
  if (!_isScanIncomplete(state)) {
    return _jsonResponse({ ok: false, reason: 'no_scan_in_progress' });
  }
  // A live pass is already advancing this cursor; rescheduling on top of it
  // would just contend for the same work.
  if (state.status === 'running' && !_isScanStale(state)) {
    return _jsonResponse(_scanStatusPayload(state));
  }
  state.status = 'waiting';
  state.error = null;
  _writeScanState(state);
  _scheduleScanTrigger();
  return _jsonResponse(_scanStatusPayload(state));
}

/**
 * admin_scan_track — registers selected scan candidates into DocData so the
 * background sync (syncAll, gts-qkev) discovers and syncs them on its next
 * sweep. Deliberately CHEAP and synchronous, unlike syncDocument(): no doc
 * open, no floating-action scan, no Drive round trip. Every candidate was
 * already found under this team's registered folder by the scan itself
 * (AdminDocScan.js's enumerate phase), so teamId is known outright — no
 * folder walk needed, unlike _syncTeamScope's general case.
 *
 * Payload: { assertion|testToken+email, teamId, docs: [{docId, docName, teamId}] }
 * Response: { ok, teamId, tracked: [docId, ...] }
 *
 * A nightly all-teams scan's candidates span multiple teams in one list, so
 * each doc in the payload carries its OWN teamId (round-tripped from the
 * candidate the UI rendered); the top-level payload.teamId (still required,
 * possibly the ALL_TEAMS_ID sentinel) is used only as a fallback for older
 * callers that don't send a per-doc teamId, and for the forbidden-check log.
 *
 * The UI's job after this call is done (per human direction 2026-09-01): the
 * candidate list is simply cleared client-side. Whether a tracked doc's
 * Actions actually populate on the next sweep is syncAll's job, not this
 * route's — this route only makes the doc visible to that sweep.
 *
 * gts-f0vd: also prunes every tracked docId out of the SERVER-side persisted
 * candidate list (ADMIN_DOC_SCAN_CANDIDATES_PROP). Client-side clearing is
 * per-page-instance only — admin_scan_status replays the persisted list to
 * every later page load (or second portal) until a fresh scan resets it, so
 * without this a tracked doc reappeared as an untracked candidate.
 */
function _handleAdminScanTrack(payload) {
  var teamId = payload.teamId || '';
  var denied = _denyScanIfNotAdmin(payload, teamId);
  if (denied) return denied;
  if (!teamId) return _jsonResponse({ ok: false, reason: 'teamId required' });

  var docs = payload.docs || [];
  if (!docs.length) return _jsonResponse({ ok: false, reason: 'docs required' });

  var ss = _openActionSheetSpreadsheet();
  var tracked = [];
  var trackedIds = {};
  for (var i = 0; i < docs.length; i++) {
    var docId = docs[i] && docs[i].docId;
    if (!docId) continue;
    var docTeamId = (docs[i].teamId) || teamId;
    if (!docTeamId || docTeamId === TEAM_LISTING_ALL_TEAMS_ID) continue; // no real team to file it under
    var existing = _readDocDataRow(ss, docId);
    _getOrUpsertDocDataRow(
      ss, docId,
      docs[i].docName || (existing ? existing.docName : '') || '',
      existing ? existing.lastSyncTime : null,
      docTeamId,
      existing ? existing.syncStatus : '',
      existing ? existing.actionCount : 0,
      existing ? existing.resolvedCount : 0
    );
    tracked.push(docId);
    trackedIds[docId] = true;
  }
  SpreadsheetApp.flush();

  // Prune the just-tracked docs out of the persisted candidate list so a
  // later admin_scan_status (this portal or the other lineage-A env sharing
  // the same Script Properties) doesn't replay them as still-untracked.
  // Candidates NOT in this call's docs stay listed (no wholesale clear).
  var state = _readScanState();
  if (state && tracked.length) {
    var candidates = _scanListRead(ADMIN_DOC_SCAN_CANDIDATES_PROP, state.candidateChunks);
    var kept = [];
    var prunedCount = 0;
    for (var c = 0; c < candidates.length; c++) {
      if (trackedIds[candidates[c].docId]) {
        prunedCount++;
      } else {
        kept.push(candidates[c]);
      }
    }
    if (prunedCount) {
      state.candidateChunks = _scanListWrite(ADMIN_DOC_SCAN_CANDIDATES_PROP, kept);
      // Keep the displayed "N match(es)" count consistent with what's still
      // listed, rather than a stale total that outlives the docs it counted.
      state.matched = Math.max(0, state.matched - prunedCount);
      _writeScanState(state);
    }
  }

  GasLogger.log('admin.scanTeamDocs.track', { teamId: teamId, count: tracked.length });
  GasLogger.flush();
  return _jsonResponse({ ok: true, teamId: teamId, tracked: tracked });
}

/**
 * Time-driven trigger handler (installed as a self-rescheduling one-shot by
 * _scheduleScanTrigger). Global by necessity — GAS resolves trigger handlers
 * by name against the global scope. A no-op when nothing is pending, since a
 * one-shot can fire moments after a scan already finished.
 */
function resumeAdminDocScan() {
  _advanceScanPass();
}

/**
 * Daily 1am trigger handler (installed by TriggerManager.js's
 * initializeTriggers). Kicks off an all-teams untracked-doc scan: every
 * TeamData teamId is queued into the SAME resumable state machine
 * admin_scan_start uses, so it self-reschedules and survives the 6-minute
 * execution ceiling exactly like a manual scan — just walking every team's
 * folders instead of one before finishing.
 *
 * Refuses to clobber a scan that is genuinely still moving (fresh
 * heartbeat, not error) — whether that's an admin's manual scan or last
 * night's run still catching up — rather than resetting it out from under
 * itself. A stale (crashed) or errored scan IS overwritten: a wedged prior
 * run must not block tonight's run forever, and the trigger already
 * exists to give scans that kind of self-healing.
 */
function nightlyAdminScanAllTeams() {
  var ss = _openActionSheetSpreadsheet();
  var teamDataRows = _readTeamDataRows(ss);
  var teamIds = [];
  var seen = {};
  for (var i = 0; i < teamDataRows.length; i++) {
    var tid = teamDataRows[i].teamId;
    if (tid && !seen[tid]) { seen[tid] = true; teamIds.push(tid); }
  }
  if (!teamIds.length) {
    GasLogger.log('admin.scanTeamDocs.nightlySkip', { reason: 'no_teams' });
    GasLogger.flush();
    return;
  }

  var existing = _readScanState();
  if (existing && _isScanIncomplete(existing) && existing.status !== 'error' && !_isScanStale(existing)) {
    GasLogger.log('admin.scanTeamDocs.nightlySkip', { reason: 'scan_in_progress', teamId: existing.teamId });
    GasLogger.flush();
    return;
  }

  _clearScanState();
  var firstFolderIds = _teamFolderIds(teamDataRows, teamIds[0]);
  var state = _writeScanState({
    teamId: teamIds[0], teamsQueue: teamIds.slice(1), allTeams: true,
    phase: 'enumerate', status: 'waiting',
    startedAt: new Date().toISOString(),
    total: null, scanned: 0, matched: 0,
    folderStack: firstFolderIds.map(function (fid) { return { id: fid, path: '' }; }),
    cursor: 0, queued: 0, queueChunks: 0, candidateChunks: 0, error: null
  });
  if (!firstFolderIds.length) {
    // teams[0] has no registered folders — roll straight to the next team
    // rather than running a pointless empty enumerate pass.
    _advanceToNextTeamOrDone(state);
    _writeScanState(state);
  }

  GasLogger.log('admin.scanTeamDocs.nightlyStart', { teams: teamIds.length });
  GasLogger.flush();
  _advanceScanPass();
}
