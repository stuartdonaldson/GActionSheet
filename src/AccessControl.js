/**
 * AccessControl.js — gts-79dw.4.1; multi-folder tier resolution + per-doc
 * write re-authorization added by gts-79dw.4.12. Identity verification
 * boundary moved from raw-GIS-tokeninfo to NUUC-Dispatch signed assertions
 * by gts-79dw.4.18 (see _verifySignedAssertion below) -- GActionSheet's own
 * GCP project's OAuth consent screen is Internal-only (required to keep the
 * Workspace add-on installable) and structurally cannot register the
 * External-facing GIS client a personal @gmail visitor needs, so it can no
 * longer be the one verifying a real external caller's raw ID token itself.
 *
 * doPost action 'verify_and_resolve_access', body { assertion, teamId }.
 * Verifies a NUUC-Dispatch-issued signed identity assertion server-side
 * (_verifySignedAssertion: HMAC-SHA256 recomputed with the Script Property
 * named by the assertion's own `kid` claim, then iss/aud/exp checked), then
 * resolves the caller's effective access tier against EVERY TeamData folder
 * belonging to teamId (a team may own more than one folder, ADR-0014 §1):
 * direct DriveApp getAccess() first per folder, falling back to the Admin
 * SDK Members.get() group-membership walk from Spike S2
 * (_spikeAdminSdkFolderAccess, src/SPIKE.js) for domain-managed-group-
 * conferred access. The team-wide READ tier is the MAX tier across all
 * folders (R3a, docs/verified-team-portal-plan.md §10) -- you see the
 * team's list if you can see any part of it. Fails closed at every step
 * (R6): a bad/expired/tampered assertion, an unresolvable team, zero
 * folders, or no resolvable folder access all resolve to tier NONE rather
 * than throwing or defaulting open.
 *
 * WRITE is NOT authorized off this team-wide tier -- see _authorizeDocWrite
 * below, which re-checks EDIT against the specific folder a target document
 * actually resides under (R3b), so EDIT on one sub-folder never confers
 * write over documents under a sibling folder.
 *
 * See docs/verified-team-portal-plan.md §3 (R1-R8), §10 (R3a/R3b) for the
 * frozen requirements and gts-79dw.4.1's/gts-79dw.4.12's/gts-79dw.4.18's
 * `design` fields for the pre-code contract (entry point, log tags, output
 * schema).
 */

var _GIS_TOKENINFO_URL   = 'https://oauth2.googleapis.com/tokeninfo?id_token=';
var _GIS_ID_TOKEN_ISSUERS = ['accounts.google.com', 'https://accounts.google.com'];

// NUUC-Dispatch signed-assertion contract (ADR-0002,
// ../NUUC-Dispatch/docs/interfaces/signed-identity-assertion.md).
var _ASSERTION_ISS = 'nuuc-dispatch';
var _ASSERTION_AUD = 'gactionsheet';

/**
 * @param {Object} payload { assertion, teamId }
 * @returns {GoogleAppsScript.Content.TextOutput}
 */
function _handleVerifyAndResolveAccess(payload) {
  var assertion = payload.assertion || '';
  var teamId    = payload.teamId    || '';

  var resolved = _resolveIdentityAndAccessTier(assertion, teamId);

  GasLogger.log('webapp.team.access', {
    sub:         resolved.sub,
    tier:        resolved.tier,
    method:      resolved.method,
    folderCount: Object.keys(resolved.folderTiers || {}).length
  });
  GasLogger.flush();

  return _jsonResponse({
    verified: resolved.verified,
    sub:      resolved.sub,
    email:    resolved.email,
    tier:     resolved.tier
  }, 200);
}

/**
 * Shared resolver behind 'verify_and_resolve_access' and every other route
 * that must re-verify a caller's tier (e.g. gts-79dw.4.3's team-listing
 * route) rather than trust a client-supplied tier from a prior call.
 * Verifies the signed NUUC-Dispatch assertion (_verifySignedAssertion, gts-
 * 79dw.4.18), then resolves teamId -> every matching TeamData row -> folder
 * id, and checks each folder via DriveApp.getAccess() first, falling back
 * to the Admin SDK group-membership walk (Spike S2). The returned `tier` is
 * the MAX across all of the team's folders (R3a); `method` reflects
 * whichever folder produced that max tier. `folderTiers` carries the
 * per-folder resolution so callers needing a document-scoped write check can
 * re-authorize against the specific folder a document resides under
 * (R3b, see _authorizeDocWrite) rather than trusting the team-wide max.
 * Fails closed (R6): a bad/expired/tampered assertion, an unresolvable team,
 * zero folders, or no resolvable folder access all yield tier NONE.
 *
 * @param {string} assertion
 * @param {string} teamId
 * @returns {{verified: boolean, sub: string, email: string,
 *   tier: 'NONE'|'VIEW'|'EDIT', method: string,
 *   folderTiers: Object<string, 'NONE'|'VIEW'|'EDIT'>}}
 */
function _resolveIdentityAndAccessTier(assertion, teamId) {
  var identity = _verifySignedAssertion(assertion);
  if (!identity.verified) {
    return { verified: false, sub: '', email: '', tier: 'NONE', method: 'getAccess', folderTiers: {} };
  }

  var teamResolved = { tier: 'NONE', method: 'getAccess', folderTiers: {} };
  if (teamId) {
    var ss           = _openActionSheetSpreadsheet();
    var teamDataRows = _readTeamDataRows(ss);
    teamResolved     = _resolveTeamTierForVerifiedIdentity(identity.email, teamId, teamDataRows);
  }

  return {
    verified:    true,
    sub:         identity.sub,
    email:       identity.email,
    tier:        teamResolved.tier,
    method:      teamResolved.method,
    folderTiers: teamResolved.folderTiers
  };
}

/**
 * Resolves ONE team's tier for an identity whose signed assertion has
 * ALREADY been verified (R2/R8) -- factored out of
 * _resolveIdentityAndAccessTier so that gts-79dw.4.17's list_my_teams route
 * (_handleListMyTeams below) can verify the caller's assertion exactly ONCE
 * and then resolve every distinct teamId's tier against that single
 * verified identity, rather than paying a separate verify per team. This
 * does NOT weaken R2/R8: the assertion is still fully verified before any
 * Drive access is checked, just once instead of N times for the same
 * already-parsed assertion.
 *
 * @param {string} email verified caller email (identity.email from
 *   _verifySignedAssertion -- never a client-supplied value).
 * @param {string} teamId
 * @param {Array<{teamId: string, folderId: string}>} teamDataRows all
 *   TeamData rows (caller reads once and reuses across teams).
 * @returns {{tier: 'NONE'|'VIEW'|'EDIT', method: string,
 *   folderTiers: Object<string, 'NONE'|'VIEW'|'EDIT'>}}
 */
function _resolveTeamTierForVerifiedIdentity(email, teamId, teamDataRows) {
  var tier        = 'NONE';
  var method      = 'getAccess';
  var folderTiers = {};

  var folderIds = [];
  for (var i = 0; i < teamDataRows.length; i++) {
    if (teamDataRows[i].teamId === teamId && teamDataRows[i].folderId) {
      folderIds.push(teamDataRows[i].folderId);
    }
  }

  for (var f = 0; f < folderIds.length; f++) {
    var folderId     = folderIds[f];
    var folderTier   = 'NONE';
    var folderMethod = 'getAccess';

    try {
      folderTier = _accessLevelToTier(_spikeAccessLevel(
        withGasRetry('AccessControl.folder.getAccess:DriveApp.getFolderById',
          function () { return DriveApp.getFolderById(folderId).getAccess(email); })
      ));
    } catch (e) {
      GasLogger.log('webapp.team.access.error', { where: 'folder.getAccess', folderId: folderId, message: String(e) });
    }

    if (folderTier === 'NONE') {
      var fallback = _spikeAdminSdkFolderAccess(folderId, email);
      if (fallback.level !== 'NONE') {
        folderTier   = _accessLevelToTier(fallback.level);
        folderMethod = 'adminSdk';
      }
    }

    folderTiers[folderId] = folderTier;
    if (_tierRank(folderTier) > _tierRank(tier)) {
      tier   = folderTier;
      method = folderMethod;
    }
  }

  return { tier: tier, method: method, folderTiers: folderTiers };
}

/**
 * doPost action 'list_my_teams' (R21, gts-79dw.4.17), body { assertion }.
 * Assertion-gated like verify_and_resolve_access -- no teamId, since the
 * whole point is discovering which teams the caller has ANY access to.
 * Verifies the signed assertion ONCE (_verifySignedAssertion, gts-79dw.4.18),
 * then enumerates every DISTINCT teamId present in TeamData and resolves
 * that team's tier against the single verified identity via
 * _resolveTeamTierForVerifiedIdentity -- the same multi-folder
 * MAX-across-folders resolution gts-79dw.4.12 built, just invoked per-team
 * without re-verifying the assertion each time.
 *
 * Non-leaking (R6/R8): a team whose resolved tier is NONE is OMITTED from
 * the response entirely -- never included with tier:"NONE". An unverified
 * caller (bad/expired/tampered assertion) gets an empty team list, not an
 * error that reveals whether the assertion was merely invalid vs. simply
 * lacking access.
 *
 * teamName gap: TeamData rows (src/SyncManager.js's _readTeamDataRows) carry
 * teamId, folderId, contact, teamLink -- no distinct display-name column.
 * Absent that column, teamName below is the teamId itself; a real display
 * name would require a schema addition, which is out of this bead's scope.
 *
 * @param {Object} payload { assertion }
 * @returns {GoogleAppsScript.Content.TextOutput}
 */
function _handleListMyTeams(payload) {
  var assertion = payload.assertion || '';
  var identity  = _verifySignedAssertion(assertion);

  var teams = [];
  if (identity.verified) {
    var ss           = _openActionSheetSpreadsheet();
    var teamDataRows = _readTeamDataRows(ss);

    var teamIds = [];
    var seen    = {};
    for (var i = 0; i < teamDataRows.length; i++) {
      var teamId = teamDataRows[i].teamId;
      if (teamId && !seen[teamId]) {
        seen[teamId] = true;
        teamIds.push(teamId);
      }
    }

    for (var t = 0; t < teamIds.length; t++) {
      var teamResolved = _resolveTeamTierForVerifiedIdentity(identity.email, teamIds[t], teamDataRows);
      if (teamResolved.tier !== 'NONE') {
        teams.push({ teamId: teamIds[t], teamName: teamIds[t], tier: teamResolved.tier });
      }
    }

    teams.sort(function (a, b) {
      if (a.teamName < b.teamName) return -1;
      if (a.teamName > b.teamName) return 1;
      return 0;
    });
  }

  GasLogger.log('webapp.team.myTeams', {
    sub:       identity.sub,
    teamCount: teams.length
  });
  GasLogger.flush();

  return _jsonResponse({ teams: teams }, 200);
}

/**
 * Re-authorizes a write against ONE specific document (R3b): a caller's
 * team-wide MAX tier (R3a, `_resolveIdentityAndAccessTier`'s `tier`/
 * `folderTiers`) never by itself grants write -- EDIT on one folder of a
 * multi-folder team must not confer write over documents under a sibling
 * folder. Resolves docId's actual TeamData folder via the same Drive-
 * ancestry walk `_walkFolderForTeam` uses (src/SyncManager.js) and requires
 * EDIT on THAT folder specifically from `resolved.folderTiers`. Must be
 * called -- and must return true -- before any mutation runs; no partial
 * execution. Fails closed (R6): an unverified caller, a document whose
 * folder can't be resolved, or a folder tier below EDIT all deny.
 *
 * @param {{verified: boolean, folderTiers: Object<string,string>}} resolved
 *   the object returned by _resolveIdentityAndAccessTier.
 * @param {string} docId
 * @returns {boolean} true only if resolved holds EDIT on docId's actual folder.
 */
function _authorizeDocWrite(resolved, docId) {
  if (!resolved || !resolved.verified || !docId) return false;

  var ss           = _openActionSheetSpreadsheet();
  var teamDataRows = _readTeamDataRows(ss);
  var walkResult   = _walkFolderForTeam(docId, teamDataRows);
  if (!walkResult || !walkResult.folderId) return false;

  return (resolved.folderTiers || {})[walkResult.folderId] === 'EDIT';
}

/**
 * Ordinal rank for MAX-tier comparison (R3a): NONE < VIEW < EDIT.
 * @param {'NONE'|'VIEW'|'EDIT'} tier
 * @returns {number}
 */
function _tierRank(tier) {
  if (tier === 'EDIT') return 2;
  if (tier === 'VIEW') return 1;
  return 0;
}

/**
 * Verifies a NUUC-Dispatch-issued signed identity assertion (gts-79dw.4.18).
 * Wire format is JWT-compatible HS256: base64url(header).base64url(payload).
 * base64url(signature) -- see ../NUUC-Dispatch/docs/interfaces/signed-
 * identity-assertion.md (ADR-0002, authoritative) and its reference
 * implementation ../NUUC-Dispatch/src/Assertion.js's Assertion_verify, which
 * this function mirrors byte-for-byte on the verify side.
 *
 * Recomputes HMAC-SHA256 over the raw "header.payload" segment string using
 * the Script Property named by the token's own `kid` header claim as the
 * UTF-8 HMAC key -- the property string itself IS the key, never base64-
 * decoded first (both sides must treat it identically per the key-management
 * section of the interface doc). Rejects an unknown `kid` or `alg !==
 * 'HS256'` outright -- this is also what correctly rejects a raw Google ID
 * token (RS256, `kid` naming a Google signing key, never a Script Property)
 * presented in place of a real assertion: the boundary has genuinely moved,
 * not merely gained a second accepted shape.
 *
 * Compares the signature with a constant-time byte comparison
 * (_assertionConstantTimeEquals) rather than `===` -- a naive string compare
 * on a security-relevant signature check is a timing side-channel.
 *
 * Then verifies iss === 'nuuc-dispatch', aud === 'gactionsheet' (this
 * target's own registered identifier, ../NUUC-Dispatch/src/Assertion.js's
 * ASSERTION_TARGETS), and exp not expired. Identity keys on `sub`, never
 * `email` (verifier obligation) -- callers use identity.sub, not
 * identity.email, wherever the caller's stable identity matters.
 *
 * Never throws -- any parse/verify failure (malformed segments, bad JSON,
 * missing secret, bad signature, wrong iss/aud, expired) returns
 * verified:false so callers fail closed (R6). Never logs the assertion
 * string or the HMAC secret (verifier obligation, security-relevant).
 *
 * @param {string} assertion
 * @returns {{verified: boolean, sub: string, email: string}}
 */
function _verifySignedAssertion(assertion) {
  var failed = { verified: false, sub: '', email: '' };
  if (!assertion || typeof assertion !== 'string') return failed;

  var parts = assertion.split('.');
  if (parts.length !== 3) return failed;

  var headerSeg = parts[0];
  var payloadSeg = parts[1];
  var sigSeg = parts[2];

  var header, payload;
  try {
    header  = JSON.parse(_assertionB64urlToString(headerSeg));
    payload = JSON.parse(_assertionB64urlToString(payloadSeg));
  } catch (e) {
    return failed;
  }
  if (!header || typeof header !== 'object' || !payload || typeof payload !== 'object') {
    return failed;
  }

  if (header.alg !== 'HS256' || !header.kid) return failed;

  var secret = PropertiesService.getScriptProperties().getProperty(String(header.kid));
  if (!secret) return failed;

  var expectedSig;
  try {
    expectedSig = _assertionB64urlFromBytes(
      Utilities.computeHmacSha256Signature(headerSeg + '.' + payloadSeg, secret)
    );
  } catch (e) {
    return failed;
  }
  if (!_assertionConstantTimeEquals(expectedSig, sigSeg)) return failed;

  if (payload.iss !== _ASSERTION_ISS) return failed;
  if (payload.aud !== _ASSERTION_AUD) return failed;
  if (typeof payload.exp !== 'number' || Math.floor(Date.now() / 1000) > payload.exp) return failed;
  if (!payload.sub || !payload.email) return failed;

  return { verified: true, sub: payload.sub, email: payload.email };
}

function _assertionB64urlToString(segment) {
  return Utilities.newBlob(Utilities.base64DecodeWebSafe(segment)).getDataAsString();
}

function _assertionB64urlFromBytes(bytes) {
  return Utilities.base64EncodeWebSafe(bytes).replace(/=+$/, '');
}

/**
 * Length-then-XOR compare so a signature check never short-circuits on the
 * first differing byte (timing side-channel on a security-relevant
 * comparison). Mirrors ../NUUC-Dispatch/src/Assertion.js's
 * _assertionConstantTimeEquals exactly.
 */
function _assertionConstantTimeEquals(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false;
  var diff = 0;
  for (var i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

/**
 * DEAD CODE, retained for reference only -- gts-79dw.4.18 moved the
 * verification boundary to _verifySignedAssertion above. This raw-tokeninfo
 * verifier is now provably the WRONG boundary for a genuinely external
 * caller: it can only ever succeed for an ID token whose `aud` matches a GIS
 * OAuth client registered on GActionSheet's OWN GCP project, and that
 * project's consent screen must stay Internal-only to keep the Workspace
 * add-on installable (ADR-0002's premise) -- so no true external @gmail
 * visitor's ID token can ever satisfy it. No route calls this function
 * anymore; left in place (rather than deleted) purely as a historical
 * record of the pre-gts-79dw.4.18 verification path.
 *
 * @param {string} idToken
 * @returns {{verified: boolean, sub: string, email: string}}
 */
function _verifyGisIdToken(idToken) {
  var failed = { verified: false, sub: '', email: '' };
  if (!idToken) return failed;

  var response;
  try {
    response = UrlFetchApp.fetch(_GIS_TOKENINFO_URL + encodeURIComponent(idToken), {
      muteHttpExceptions: true
    });
  } catch (e) {
    GasLogger.log('webapp.team.access.error', { where: 'tokeninfo.fetch', message: String(e) });
    return failed;
  }

  if (response.getResponseCode() !== 200) return failed;

  var info;
  try {
    info = JSON.parse(response.getContentText());
  } catch (e) {
    return failed;
  }

  // aud must match our configured GIS OAuth client id (R2). No positive
  // confirmation possible without it configured -- fail closed rather than
  // skip the check (R6).
  var expectedAud = PropertiesService.getScriptProperties().getProperty('GIS_CLIENT_ID');
  if (!expectedAud || info.aud !== expectedAud) return failed;
  if (_GIS_ID_TOKEN_ISSUERS.indexOf(info.iss) === -1) return failed;
  if (!info.exp || Number(info.exp) <= Math.floor(Date.now() / 1000)) return failed;
  if (!info.sub || !info.email) return failed;

  return { verified: true, sub: info.sub, email: info.email };
}

/**
 * Collapses the SPIKE 5-level access scale (_spikeAccessLevel, src/SPIKE.js)
 * to this route's 3-tier output schema (R4/R5): VIEW/COMMENT -> VIEW,
 * EDIT/OWNER -> EDIT, NONE -> NONE.
 * @param {'NONE'|'VIEW'|'COMMENT'|'EDIT'|'OWNER'} level
 * @returns {'NONE'|'VIEW'|'EDIT'}
 */
function _accessLevelToTier(level) {
  if (level === 'VIEW' || level === 'COMMENT') return 'VIEW';
  if (level === 'EDIT' || level === 'OWNER')   return 'EDIT';
  return 'NONE';
}
