/**
 * AccessControl.js — gts-79dw.4.1
 *
 * doPost action 'verify_and_resolve_access', body { idToken, boardFolderId }.
 * Verifies a GIS ID token server-side (aud/iss/exp/signature via Google's
 * tokeninfo endpoint, keyed on sub), then resolves the caller's effective
 * access tier against the board folder: direct DriveApp getAccess() first,
 * falling back to the Admin SDK Members.get() group-membership walk from
 * Spike S2 (_spikeAdminSdkFolderAccess, src/SPIKE.js) for domain-managed-
 * group-conferred access. Fails closed at every step (R6): a bad/expired
 * token, an unconfigured client id, or no resolvable folder access all
 * resolve to tier NONE rather than throwing or defaulting open.
 *
 * See docs/verified-board-portal-plan.md §3 (R1-R8) for the frozen
 * requirements and gts-79dw.4.1's `design` field for the pre-code contract
 * (entry point, log tag, output schema) shared with the twin [TST] ticket.
 */

var _GIS_TOKENINFO_URL   = 'https://oauth2.googleapis.com/tokeninfo?id_token=';
var _GIS_ID_TOKEN_ISSUERS = ['accounts.google.com', 'https://accounts.google.com'];

/**
 * @param {Object} payload { idToken, boardFolderId }
 * @returns {GoogleAppsScript.Content.TextOutput}
 */
function _handleVerifyAndResolveAccess(payload) {
  var idToken       = payload.idToken       || '';
  var boardFolderId = payload.boardFolderId || '';

  var resolved = _resolveIdentityAndAccessTier(idToken, boardFolderId);

  GasLogger.log('webapp.board.access', { sub: resolved.sub, tier: resolved.tier, method: resolved.method });
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
 * that must re-verify a caller's tier (e.g. gts-79dw.4.3's board-listing
 * route) rather than trust a client-supplied tier from a prior call.
 * Verifies the GIS ID token, then resolves the caller's effective access
 * tier against boardFolderId via DriveApp.getAccess() first, falling back to
 * the Admin SDK group-membership walk (Spike S2). Fails closed (R6): a
 * bad/expired token or no resolvable folder access both yield tier NONE.
 *
 * @param {string} idToken
 * @param {string} boardFolderId
 * @returns {{verified: boolean, sub: string, email: string, tier: 'NONE'|'VIEW'|'EDIT', method: string}}
 */
function _resolveIdentityAndAccessTier(idToken, boardFolderId) {
  var identity = _verifyGisIdToken(idToken);
  if (!identity.verified) {
    return { verified: false, sub: '', email: '', tier: 'NONE', method: 'getAccess' };
  }

  var tier   = 'NONE';
  var method = 'getAccess';

  if (boardFolderId) {
    try {
      tier = _accessLevelToTier(_spikeAccessLevel(
        DriveApp.getFolderById(boardFolderId).getAccess(identity.email)
      ));
    } catch (e) {
      GasLogger.log('webapp.board.access.error', { where: 'folder.getAccess', message: String(e) });
    }

    if (tier === 'NONE') {
      var fallback = _spikeAdminSdkFolderAccess(boardFolderId, identity.email);
      if (fallback.level !== 'NONE') {
        tier   = _accessLevelToTier(fallback.level);
        method = 'adminSdk';
      }
    }
  }

  return { verified: true, sub: identity.sub, email: identity.email, tier: tier, method: method };
}

/**
 * Verifies a GIS ID token server-side via Google's tokeninfo endpoint (A3):
 * a non-200 response means tokeninfo itself already rejected the token
 * (bad signature/shape/expiry), so the aud/iss/exp/sub/email checks below
 * are a second, explicit line of defense (R2) rather than the sole gate.
 * Never throws -- any failure (network, parse, malformed/unconfigured
 * client id) returns verified:false so callers fail closed (R6).
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
    GasLogger.log('webapp.board.access.error', { where: 'tokeninfo.fetch', message: String(e) });
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
