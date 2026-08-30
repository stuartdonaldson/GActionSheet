/**
 * TeamListing.js — gts-79dw.4.3; folded onto the shared reader + renamed by
 * gts-79dw.4.11 (was BoardListing.js / list_board_actions).
 *
 * doPost action 'list_team_actions', body { assertion, teamId,
 * statusFilter: 'open'|'closed'|'all', scope: 'all'|'mine', windowDays? }.
 * Re-verifies the caller's access tier via AccessControl.js's
 * _resolveIdentityAndAccessTier on every call (no trust-on-first-use, R8)
 * and, for VIEW/EDIT tiers, lists every tracked action across every document
 * whose DocData.teamId matches teamId, via the shared _readTeamActions
 * reader (src/WebApp.js) — the same reader list_importable_actions and
 * ?cmd=teamview use. Bypasses WEBAPP_SECRET intentionally, same as
 * verify_and_resolve_access: callers are external identities verified via a
 * NUUC-Dispatch signed assertion (gts-79dw.4.18), not GActionSheet's own
 * WEBAPP_SECRET.
 *
 * Tier resolution is via AccessControl.js's _resolveIdentityAndAccessTier(
 * assertion, teamId), which as of gts-79dw.4.12 checks EVERY TeamData folder
 * matching teamId and resolves the team-wide READ tier as the MAX across all
 * of them (R3a) -- a caller with access to any one folder of a multi-folder
 * team sees the team's list.
 *
 * Contract frozen at the gts-79dw.4.7 human review gate (2026-07-27):
 * docs/verified-team-portal-plan.md §12.1 — this is the authoritative field
 * list/behaviour where it differs from this bead's own (earlier) `design`
 * field. Response rows carry exactly TEAM_ACTION_FIELDS (WebApp.js); the
 * page re-derives none of them. `scope=mine` filters to the VERIFIED
 * caller's own email (resolved.email) — never a client-supplied field
 * (R13a) — and composes with every statusFilter in the single
 * _readTeamActions call below (no client-side merge of two calls).
 *
 * See docs/verified-team-portal-plan.md §3 (R9-R13), §11 (Reuse inventory),
 * §12.1 (frozen read contract) for the pre-code contract (entry point, log
 * tag, output schema).
 */

var TEAM_LISTING_DEFAULT_WINDOW_DAYS = 60;

/**
 * Sentinel teamId (gts-zm8w) requesting the aggregate 'All teams' view:
 * every action across every team the caller has ANY (VIEW-or-better) access
 * to, in one call. Not a real TeamData teamId -- never matches a row.
 */
var TEAM_LISTING_ALL_TEAMS_ID = 'ALL';

/**
 * @param {Object} payload { assertion, teamId, statusFilter, scope, windowDays }
 * @returns {GoogleAppsScript.Content.TextOutput}
 */
function _handleListTeamActions(payload) {
  var assertion    = payload.assertion || '';
  var teamId       = payload.teamId  || '';
  var statusFilter = (payload.statusFilter === 'closed' || payload.statusFilter === 'all')
    ? payload.statusFilter : 'open';
  var scope       = payload.scope === 'mine' ? 'mine' : 'all';
  var windowDays  = Number(payload.windowDays);
  if (!(windowDays > 0)) windowDays = TEAM_LISTING_DEFAULT_WINDOW_DAYS;

  // gts-zm8w: read TeamData ONCE here and pass it into
  // _resolveIdentityAndAccessTier below instead of letting it open the
  // spreadsheet and re-read TeamData a second time internally.
  var ss           = _openActionSheetSpreadsheet();
  var teamDataRows = _readTeamDataRows(ss);

  var resolved;
  var teams = null; // only populated for the ALL-teams aggregate response

  if (teamId === TEAM_LISTING_ALL_TEAMS_ID) {
    var identity = _verifySignedAssertion(assertion);
    teams = identity.verified ? _resolveAllVisibleTeams(identity.email, teamDataRows) : [];
    resolved = {
      verified: identity.verified,
      sub:      identity.sub,
      email:    identity.email,
      tier:     teams.length ? 'VIEW' : 'NONE'
    };
  } else {
    resolved = _resolveIdentityAndAccessTier(assertion, teamId, ss, teamDataRows);
  }

  var actions = [];
  if (teamId === TEAM_LISTING_ALL_TEAMS_ID) {
    if (teams.length) {
      var allReadOpts = {
        statusFilter: statusFilter, windowDays: windowDays, ss: ss,
        teamIds: teams.map(function (t) { return t.teamId; }),
        fields:  TEAM_ACTION_FIELDS_WITH_TEAM
      };
      if (scope === 'mine') allReadOpts.assigneeEmail = resolved.email;
      actions = _readTeamActions(null, allReadOpts);
    }
  } else if (resolved.tier !== 'NONE') {
    var readOpts = { statusFilter: statusFilter, windowDays: windowDays, ss: ss };
    if (scope === 'mine') readOpts.assigneeEmail = resolved.email;
    actions = _readTeamActions(teamId, readOpts);
  }

  GasLogger.log('webapp.team.list', {
    sub:          resolved.sub,
    tier:         resolved.tier,
    statusFilter: statusFilter,
    scope:        scope,
    count:        actions.length,
    teamCount:    teams ? teams.length : 1
  });
  GasLogger.flush();

  var response = {
    tier:          resolved.tier,
    teamId:        teamId,
    actions:       actions,
    statusOptions: getStatusIconButtons()
  };
  if (teams) response.teams = teams;

  return _jsonResponse(response, 200);
}
