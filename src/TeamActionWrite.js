/**
 * TeamActionWrite.js — gts-79dw.4.14; verified-team-portal edit +
 * status-change routes (R16-R18).
 *
 * doPost actions 'team_edit_action', body { assertion, teamId, global_id,
 * fields } and 'team_patch_status', body { assertion, teamId, global_id,
 * status }. Same `assertion`-over-`idToken` convention correction every
 * sibling GIS route already follows (src/DocView.js's file header,
 * src/TeamSync.js, src/AccessControl.js) -- the frozen contract text
 * predates gts-79dw.4.18's move of the identity boundary to NUUC-Dispatch
 * signed assertions; the contract's INTENT (identity proof in the body,
 * re-verified every call, R8) is unchanged.
 *
 * REUSE (plan §11): the mutation cores already exist and are correct --
 * src/WebApp.js's _editActionRowCore (factored out of edit_action_row,
 * bead .9) and _patchActionStatusCore (factored out of patch_action_status).
 * This file adds ONLY the GIS-tier-gated authorization in front of them; it
 * never re-implements the Dirty/Date-Modified stamp or the status write.
 *
 * TWO different authorizations, deliberately (R16/R17):
 *   team_edit_action   -- requires _authorizeDocWrite (EDIT tier on the
 *                          target document's actual folder, gts-79dw.4.12,
 *                          R3b) -- editing an action's fields is a folder-
 *                          scoped EDIT capability, full stop.
 *   team_patch_status  -- requires EITHER _authorizeDocWrite OR that the
 *                          row's assignee_email matches the verified
 *                          caller's email (R17) -- the person an action is
 *                          assigned to may change its own status with only
 *                          VIEW tier on the folder, which is what makes the
 *                          portal useful to an external assignee who lacks
 *                          write access. The match is against
 *                          `resolved.email` (from _verifySignedAssertion),
 *                          NEVER a client-supplied field -- a caller cannot
 *                          claim to be the assignee.
 *
 * Both re-verify the tier on EVERY call (no trust-on-first-use, R8) via
 * AccessControl.js's _resolveIdentityAndAccessTier(assertion, teamId), then
 * re-authorize against the SPECIFIC document the target row belongs to
 * (docId recovered from global_id itself -- format {docId}/AI-{N},
 * WebApp.js's parseGlobalId) via _authorizeDocWrite, mirroring
 * TeamSync.js's team_sync_document pattern exactly. Unauthorized -> rejected
 * BEFORE any mutation runs; no partial execution, row unchanged either way.
 *
 * Completion log tags: webapp.team.edit / webapp.team.status, data
 * { eu, au, global_id, outcome } (R18, ADR-0019/0020) -- eu is this
 * execution's own identity (GasLogger convention, _getIdentity()), au is the
 * verified caller (resolved.email from the assertion), matching
 * team_sync_document's { eu, au, docId, outcome } field-naming convention.
 *
 * Output schema: JSON { ok: boolean, global_id, outcome }.
 */

/**
 * @param {Object} payload { assertion, teamId, global_id, fields }
 * @returns {GoogleAppsScript.Content.TextOutput}
 */
function _handleTeamEditAction(payload) {
  var assertion = payload.assertion || '';
  var teamId    = payload.teamId    || '';
  var globalId  = payload.global_id || '';
  var fields    = payload.fields    || {};

  var docId    = parseGlobalId(globalId).docId;
  var resolved = _resolveIdentityAndAccessTier(assertion, teamId);
  var identity = _getIdentity();

  if (!_authorizeDocWrite(resolved, docId)) {
    var rejectOutcome = !resolved.verified ? 'rejected-unverified' : 'rejected-doc-scope';
    GasLogger.log('webapp.team.edit', {
      eu: identity.eu, au: resolved.email, global_id: globalId, outcome: rejectOutcome
    });
    GasLogger.flush();
    return _jsonResponse({ ok: false, global_id: globalId, outcome: rejectOutcome });
  }

  var result  = _editActionRowCore(globalId, fields);
  var outcome = result.ok ? 'ok' : 'error';

  GasLogger.log('webapp.team.edit', {
    eu: identity.eu, au: resolved.email, global_id: globalId, outcome: outcome
  });
  GasLogger.flush();

  return _jsonResponse({ ok: result.ok, global_id: globalId, outcome: outcome });
}

/**
 * @param {Object} payload { assertion, teamId, global_id, status }
 * @returns {GoogleAppsScript.Content.TextOutput}
 */
function _handleTeamPatchStatus(payload) {
  var assertion = payload.assertion || '';
  var teamId    = payload.teamId    || '';
  var globalId  = payload.global_id || '';
  var newStatus = payload.status    || '';

  var docId    = parseGlobalId(globalId).docId;
  var resolved = _resolveIdentityAndAccessTier(assertion, teamId);
  var identity = _getIdentity();

  // R17: look up the row's CURRENT assignee before authorizing -- the
  // assignee bypass is decided off durable sheet state, never off anything
  // the caller supplied in the request.
  var ss           = _openActionSheetSpreadsheet();
  var actionsSheet = ss.getSheetByName('Actions');
  var entry        = actionsSheet ? _loadExistingRowsByGlobalId(actionsSheet)[globalId] : null;
  var isAssignee   = resolved.verified && !!entry && !!entry.assigneeEmail &&
                      entry.assigneeEmail === resolved.email;

  if (!_authorizeDocWrite(resolved, docId) && !isAssignee) {
    var rejectOutcome = !resolved.verified ? 'rejected-unverified' : 'rejected-doc-scope';
    GasLogger.log('webapp.team.status', {
      eu: identity.eu, au: resolved.email, global_id: globalId, outcome: rejectOutcome
    });
    GasLogger.flush();
    return _jsonResponse({ ok: false, global_id: globalId, outcome: rejectOutcome });
  }

  var result  = _patchActionStatusCore(globalId, newStatus);
  var outcome = result.ok ? 'ok' : 'error';

  GasLogger.log('webapp.team.status', {
    eu: identity.eu, au: resolved.email, global_id: globalId, outcome: outcome
  });
  GasLogger.flush();

  return _jsonResponse({ ok: result.ok, global_id: globalId, outcome: outcome });
}
