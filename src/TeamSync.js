/**
 * TeamSync.js — gts-79dw.4.5; renamed by gts-79dw.4.11 (was BoardSync.js /
 * board_sync_document).
 *
 * doPost action 'team_sync_document', body { assertion, teamId, docId }.
 * Re-verifies the caller's access tier via AccessControl.js's
 * _resolveIdentityAndAccessTier on every call (no trust-on-first-use, R8),
 * requires team-wide EDIT tier, AND (gts-79dw.4.12, R3b) re-authorizes the
 * write against docId specifically via _authorizeDocWrite: EDIT on one
 * folder of a multi-folder team does not confer write over documents under a
 * sibling folder the caller may only have VIEW (or no) access to. Only once
 * both checks pass does the existing deployer-context sync path run
 * (syncDocument(), src/SyncManager.js) — the same function the sidebar's
 * "Sync Now" menu item and the 30-minute trigger already run under the
 * deployer's own auth. Rejected before that path runs either way; no partial
 * execution.
 *
 * See docs/verified-team-portal-plan.md §3 (R14-R15), §10 (R3b) and this
 * bead's / gts-79dw.4.12's `design` fields for the pre-code contract (entry
 * point, log tags, output schema) shared with the twin [TST] ticket
 * (gts-79dw.4.6, consolidated into gts-79dw.4.8).
 */

/**
 * @param {Object} payload { assertion, teamId, docId }
 * @returns {GoogleAppsScript.Content.TextOutput}
 */
function _handleTeamSyncDocument(payload) {
  var assertion = payload.assertion || '';
  var teamId    = payload.teamId    || '';
  var docId     = payload.docId     || '';

  var resolved = _resolveIdentityAndAccessTier(assertion, teamId);
  var identity = _getIdentity();

  if (resolved.tier !== 'EDIT') {
    GasLogger.log('webapp.team.sync', {
      eu: identity.eu, au: resolved.email, docId: docId, outcome: 'rejected-' + resolved.tier
    });
    GasLogger.flush();
    return _jsonResponse({ ok: false, outcome: 'rejected-' + resolved.tier });
  }

  if (!_authorizeDocWrite(resolved, docId)) {
    GasLogger.log('webapp.team.access.denied', { sub: resolved.sub, docId: docId, tier: resolved.tier });
    GasLogger.log('webapp.team.sync', {
      eu: identity.eu, au: resolved.email, docId: docId, outcome: 'rejected-doc-scope'
    });
    GasLogger.flush();
    return _jsonResponse({ ok: false, outcome: 'rejected-doc-scope' });
  }

  var outcome = 'ok';
  try {
    syncDocument(docId);
  } catch (e) {
    outcome = 'error';
    GasLogger.log('webapp.team.sync.error', { docId: docId, message: String(e) });
  }

  GasLogger.log('webapp.team.sync', {
    eu: identity.eu, au: resolved.email, docId: docId, outcome: outcome
  });
  GasLogger.flush();

  return _jsonResponse({ ok: outcome === 'ok', outcome: outcome });
}
