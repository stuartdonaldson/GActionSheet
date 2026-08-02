/**
 * DocView.js — gts-79dw.4.13; View B: verified per-document action view.
 *
 * doPost action 'get_document_actions', body { assertion, docId }. The
 * pre-code contract (bd issue design field) was drafted before gts-79dw.4.18
 * moved the verified-identity boundary from a raw GIS ID token to a
 * NUUC-Dispatch signed assertion (see src/AccessControl.js's file header) --
 * every sibling verified route (list_team_actions, team_sync_document,
 * list_my_teams, verify_and_resolve_access) already reads `payload.assertion`,
 * not `payload.idToken`. This route follows that established, current
 * convention rather than the now-stale field name in the frozen contract
 * text; the contract's INTENT (identity proof in the body, re-verified every
 * call, R8) is unchanged.
 *
 * Resolves teamId from DocData.teamId for docId via _readDocDataRow
 * (src/SyncManager.js) -- explicitly NOT _walkFolderForTeam, which exists
 * for a different purpose (ADR-0014: assigning teamScope to a not-yet-scoped
 * doc at sync time, and re-authorizing a WRITE against a document's actual
 * folder in _authorizeDocWrite). View B is read-only (R19 caveat -- edit and
 * status-change land in gts-79dw.4.14), so no _authorizeDocWrite call is
 * needed here.
 *
 * Then resolves the caller's tier via gts-79dw.4.12's
 * _resolveIdentityAndAccessTier(assertion, teamId) (src/AccessControl.js) --
 * the MAX tier across every TeamData folder for that team (R3a). Fails
 * closed at every step (R6): an unresolvable docId (no DocData row, no
 * teamId) resolves an empty teamId, which _resolveIdentityAndAccessTier
 * itself already treats as tier NONE.
 *
 * Reuses the existing docId-scoped reader (_findSheetActionsForDoc,
 * src/WebApp.js -- factored out of _handleFindSheetActions by this bead) as
 * the data source rather than writing a second reader (plan §11 reuse
 * constraint).
 *
 * Output schema: { tier, teamId, docName, docUrl, actions: [...],
 * teamPortalUrl }. A NONE-tier caller receives no action data (R8) --
 * `actions` is always [] at NONE tier. `docName`/`docUrl`/`teamPortalUrl` are
 * still populated regardless of tier: they carry no more information than
 * the docId the caller already supplied (the same convention
 * list_team_actions follows, always echoing the caller-supplied `teamId`
 * regardless of resolved tier) -- R8's "no action data" is about the
 * action rows, not the caller's own input echoed back.
 *
 * teamPortalUrl (R20 navigation to View A) points at the static verified-
 * portal frontend's expected origin (docs/verified-team-portal-plan.md §4a,
 * confirmed reachable by Spike S1/A1) with the resolved teamId. NOTE: as of
 * this bead, gts-79dw.4.7 (View A's own page) has not shipped a live page at
 * that origin yet -- this field is forward-wired for R20, not yet clickable
 * end-to-end. Tracked by gts-79dw.4.7, not a gap in this bead.
 */

// Verified-portal static frontend origin (docs/verified-team-portal-plan.md
// §4a; confirmed reachable cross-origin by Spike S1/A1,
// tests/playwright/cors_team_portal.test.js). Mirrors the
// ACTION_CHIP_URL_BASE-style base-URL constant pattern (src/SyncManager.js)
// for the anonymous routes.
var _VERIFIED_TEAM_PORTAL_BASE = 'https://nuuc-it.github.io/Static/pub/AS/';

/**
 * @param {Object} payload { assertion, docId }
 * @returns {GoogleAppsScript.Content.TextOutput}
 */
function _handleGetDocumentActions(payload) {
  var assertion = payload.assertion || '';
  var docId     = payload.docId     || '';

  var ss         = _openActionSheetSpreadsheet();
  var docDataRow = docId ? _readDocDataRow(ss, docId) : null;
  var teamId     = docDataRow ? (docDataRow.teamId || '') : '';

  var resolved = _resolveIdentityAndAccessTier(assertion, teamId);

  var actions = [];
  if (resolved.tier !== 'NONE') {
    actions = _findSheetActionsForDoc(ss, docId);
  }

  GasLogger.log('webapp.team.docview', {
    sub:   resolved.sub,
    tier:  resolved.tier,
    docId: docId,
    count: actions.length
  });
  GasLogger.flush();

  return _jsonResponse({
    tier:          resolved.tier,
    teamId:        teamId,
    docName:       docDataRow ? (docDataRow.docName || '') : '',
    docUrl:        docId ? ('https://docs.google.com/document/d/' + encodeURIComponent(docId) + '/edit') : '',
    actions:       actions,
    teamPortalUrl: teamId ? (_VERIFIED_TEAM_PORTAL_BASE + '?team=' + encodeURIComponent(teamId)) : ''
  }, 200);
}
