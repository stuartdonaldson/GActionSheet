/**
 * SPIKE.js — Spike S2 (gts-79dw.2): folder/doc access verification for
 * an external, GIS-verified email, including access conferred only through a
 * domain-managed Google Group.
 *
 * Set SPIKE_ENABLED = false to keep the route inert in real deployments (same
 * pattern as PROBE_ENABLED in PROBE.js). ADR-0002 (NUUC-Dispatch) puts
 * authorization decisions in the target app, not the identity dispatcher —
 * this project owns the board folder's ACL, so the access check lives here
 * rather than in NUUC-Dispatch.
 *
 * doPost action 'spike_check_access' — body { email, folderId, docId }.
 * Runs in deployer context (executeAs: USER_DEPLOYING), so getAccess()/the
 * Admin SDK fallback see whatever the deployer can see, same as any other
 * WebApp route in this project.
 *
 * See ../docs/verified-team-portal-plan.md §6 for the full spike contract,
 * assumptions (A4/A5/A6), and the test matrix.
 */

var SPIKE_ENABLED = false;

/**
 * @param {Object} payload { email, folderId, docId }
 * @returns {GoogleAppsScript.Content.TextOutput}
 */
function _handleSpikeCheckAccess(payload) {
  var email    = payload.email    || '';
  var folderId = payload.folderId || '';
  var docId    = payload.docId    || '';

  var folderAccess    = 'NONE';
  var docAccess       = 'NONE';
  var method          = 'getAccess';
  var groupExpandUsed = false;

  if (!email || !folderId) {
    return _jsonResponse({
      email: email, folderId: folderId, docId: docId,
      folderAccess: folderAccess, docAccess: docAccess,
      method: method, groupExpandUsed: groupExpandUsed,
      error: 'email and folderId required'
    });
  }

  try {
    folderAccess = _spikeAccessLevel(DriveApp.getFolderById(folderId).getAccess(email));
  } catch (e) {
    GasLogger.log('webapp.spike.access.error', { where: 'folder.getAccess', message: String(e) });
  }

  if (docId) {
    try {
      docAccess = _spikeAccessLevel(DriveApp.getFileById(docId).getAccess(email));
    } catch (e) {
      GasLogger.log('webapp.spike.access.error', { where: 'doc.getAccess', message: String(e) });
    }
  }

  // Fallback (A5): getAccess() didn't positively resolve the folder — walk the
  // folder's group permissions and check membership via Admin SDK. Only meaningful
  // for external members of a DOMAIN-MANAGED group (Admin SDK can't see arbitrary
  // consumer-Gmail groups, but that's not the case under test here).
  if (folderAccess === 'NONE') {
    var fallback = _spikeAdminSdkFolderAccess(folderId, email);
    if (fallback.level !== 'NONE') {
      folderAccess    = fallback.level;
      method           = 'adminSdk';
      groupExpandUsed  = true;
    }
  }

  GasLogger.log('webapp.spike.access', {
    folderAccess: folderAccess,
    docAccess: docAccess,
    method: method,
    groupExpandUsed: groupExpandUsed
  });
  GasLogger.flush();

  return _jsonResponse({
    email: email, folderId: folderId, docId: docId,
    folderAccess: folderAccess, docAccess: docAccess,
    method: method, groupExpandUsed: groupExpandUsed
  });
}

/**
 * Manual test-matrix helper — doPost action 'spike_seed_access', gated by
 * SPIKE_ENABLED same as spike_check_access. Temporarily mutates real sharing
 * state on a folder to exercise matrix cases (a)/(b)/(e), always returning
 * the pre-change state so the caller can restore it afterward.
 *
 * @param {Object} payload { op, folderId, email, permissionId }
 *   op: 'inspect' | 'add_viewer' | 'add_editor' | 'remove_direct'
 *     | 'insert_anyone_permission' (case e — Shared-Drive-safe, via Drive v2 API)
 *     | 'remove_permission' (revert insert_anyone_permission by id)
 */
function _handleSpikeSeedAccess(payload) {
  var folderId = payload.folderId = payload.folderId || '';
  var email    = payload.email    || '';
  var op       = payload.op       || 'inspect';

  if (!folderId) return _jsonResponse({ error: 'folderId required' });

  var folder = DriveApp.getFolderById(folderId);
  var before = _spikeInspectFolder(folder);
  var extra = {};

  try {
    switch (op) {
      case 'inspect':
        break;
      case 'add_viewer':
        folder.addViewer(email);
        break;
      case 'add_editor':
        folder.addEditor(email);
        break;
      case 'remove_direct':
        try { folder.removeEditor(email); } catch (e1) {}
        try { folder.removeViewer(email); } catch (e2) {}
        break;
      case 'insert_anyone_permission':
        // DriveApp.setSharing() doesn't support Shared Drive items ("Cannot use
        // this operation on a shared drive item") — Drive v2 Permissions.insert
        // does. Returns the inserted permission's id so it can be precisely
        // removed afterward instead of guessing at a "restore" state.
        var inserted = Drive.Permissions.insert(
          { role: 'reader', type: 'anyone' },
          folderId,
          { supportsAllDrives: true, sendNotificationEmails: false }
        );
        extra.insertedPermissionId = inserted.id;
        break;
      case 'remove_permission':
        Drive.Permissions.remove(folderId, payload.permissionId, { supportsAllDrives: true });
        break;
      default:
        return _jsonResponse({ error: 'unknown op: ' + op, before: before });
    }
  } catch (e) {
    GasLogger.log('webapp.spike.seed.error', { op: op, message: String(e) });
    return _jsonResponse({ error: String(e), op: op, before: before });
  }

  var after = _spikeInspectFolder(folder);

  // gts-dige AC-8: bust the resource-side cross-request cache for this
  // folderId before returning, so an immediate re-resolve observes the
  // permission this call just mutated rather than a cached pre-seed value.
  var accessCacheFlushed = _accessCacheFlushResource(CacheService.getScriptCache(), folderId);
  GasLogger.log('access.cache.flush', { flushed: accessCacheFlushed });

  GasLogger.log('webapp.spike.seed', { op: op, email: email, before: before, after: after, extra: extra });
  GasLogger.flush();
  var response = { op: op, email: email, before: before, after: after };
  for (var k in extra) response[k] = extra[k];
  return _jsonResponse(response);
}

function _spikeInspectFolder(folder) {
  var viewers = folder.getViewers().map(function(u) { return u.getEmail(); });
  var editors = folder.getEditors().map(function(u) { return u.getEmail(); });
  var access, permission;
  try { access = folder.getSharingAccess().toString(); } catch (e) { access = 'unknown'; }
  try { permission = folder.getSharingPermission().toString(); } catch (e) { permission = 'unknown'; }
  return { viewers: viewers, editors: editors, sharingAccess: access, sharingPermission: permission };
}

/**
 * Maps a DriveApp.Permission enum (or null/undefined on no resolvable access)
 * to the output schema's access-level string.
 * @param {GoogleAppsScript.Drive.Permission} permission
 * @returns {'NONE'|'VIEW'|'COMMENT'|'EDIT'|'OWNER'}
 */
function _spikeAccessLevel(permission) {
  if (!permission) return 'NONE';
  var p = permission.toString();
  // ORGANIZER/FILE_ORGANIZER only appear on Shared Drives; both confer write,
  // so fold them into EDIT for this schema's purposes.
  if (p === 'ORGANIZER' || p === 'FILE_ORGANIZER') return 'EDIT';
  if (p === 'OWNER' || p === 'EDIT' || p === 'COMMENT' || p === 'VIEW') return p;
  return 'NONE';
}

/**
 * @param {string} role Drive Permissions API role string ('owner'|'writer'|'commenter'|'reader')
 * @returns {'NONE'|'VIEW'|'COMMENT'|'EDIT'|'OWNER'}
 */
function _spikeRoleToLevel(role) {
  switch (role) {
    case 'owner':      return 'OWNER';
    case 'organizer':
    case 'writer':     return 'EDIT';
    case 'commenter':  return 'COMMENT';
    case 'reader':     return 'VIEW';
    default:           return 'NONE';
  }
}

/**
 * Manual-run-only helper (Apps Script editor: select this function, Run).
 * Newly-added sensitive scopes (admin.directory.group*.readonly) are silently
 * dropped from the deployer's OAuth grant until an editor run actually calls
 * the service that needs them (same gotcha S1 hit for script.external_request
 * — see NUUC-Dispatch docs/OPERATIONS.md §Failure Modes). This trips the
 * consent prompt in the browser so the grant picks up the new scopes.
 */
function SPIKE_authProbe() {
  var result;
  try {
    result = AdminDirectory.Members.hasMember('driveadmin@northlakeuu.org', Session.getEffectiveUser().getEmail());
    Logger.log('SPIKE_authProbe OK: ' + JSON.stringify(result));
  } catch (e) {
    Logger.log('SPIKE_authProbe FAILED: ' + e);
  }
}

/**
 * Manual-run-only diagnostic (Apps Script editor: select this function, Run).
 * Members.hasMember() rejects external (non-domain) memberKeys with "Invalid
 * Input: memberKey" — confirmed via this function before the fix. Now uses
 * Members.get(), the call that actually works for external members: a thrown
 * 404 means "not a member," a returned Member resource means confirmed.
 */
function SPIKE_authProbeExternal() {
  var groups = ['driveadmin@northlakeuu.org', 'communications-chair@northlakeuu.org', 'communications@northlakeuu.org'];
  for (var i = 0; i < groups.length; i++) {
    try {
      var member = AdminDirectory.Members.get(groups[i], 'stuart.donaldson@gmail.com');
      Logger.log('SPIKE_authProbeExternal MEMBER (' + groups[i] + '): ' + JSON.stringify(member));
    } catch (e) {
      Logger.log('SPIKE_authProbeExternal NOT-MEMBER-OR-ERROR (' + groups[i] + '): ' + e);
    }
  }
}

/**
 * VERIFICATION V1 (gts-dige / gts-x9sk DESIGN, Q1 — nested groups).
 * Manual-run-only diagnostic (Apps Script editor: select this function, Run;
 * same pattern as SPIKE_authProbeExternal above). Uses the ALREADY-GRANTED
 * scope admin.directory.group.member.readonly -- no new scope, no consent
 * re-prompt, no new API enablement.
 *
 * For each of the five group emails ever observed on a TeamData folder or
 * its containing Shared Drive, lists that group's members and logs any
 * member whose type === 'GROUP' (a nested group). An empty result on all
 * five confirms Q1's DECISION (nesting is not in play for team folder
 * access) and Part A ships as designed. ANY non-empty result means STOP --
 * reopen the Cloud Identity transitive-membership question in gts-x9sk
 * before merging Part A; do not paper over it here.
 *
 * Record the result in gts-x9sk's notes (AC-12) -- this function only logs
 * to the Apps Script execution log, it does not write anywhere durable.
 */
function SPIKE_probeNestedGroupsV1() {
  var groups = [
    'driveadmin@northlakeuu.org',
    'board@northlakeuu.org',
    'governance@northlakeuu.org',
    'nominating@northlakeuu.org',
    'communications-chair@northlakeuu.org'
  ];
  for (var i = 0; i < groups.length; i++) {
    try {
      var members = AdminDirectory.Members.list(groups[i]).members || [];
      var nested = [];
      for (var j = 0; j < members.length; j++) {
        if (members[j].type === 'GROUP') nested.push(members[j].email);
      }
      Logger.log('SPIKE_probeNestedGroupsV1 ' + groups[i] + ': ' + members.length +
        ' members, ' + nested.length + ' nested (GROUP) -- ' + JSON.stringify(nested));
    } catch (e) {
      Logger.log('SPIKE_probeNestedGroupsV1 ' + groups[i] + ' FAILED: ' + e);
    }
  }
}

/**
 * VERIFICATION V2 (gts-dige / gts-x9sk DESIGN, "NEW FINDING V2" -- blocking
 * risk on Part A for external identities). Manual-run-only diagnostic (Apps
 * Script editor: select this function, Run; same pattern as
 * SPIKE_authProbeExternal above).
 *
 * The portal's PRIMARY use case is an external (@gmail) identity.
 * AdminDirectory.Groups.list({userKey}) documents userKey as "a user in the
 * domain" -- it was UNVERIFIED whether it accepts an external member email
 * before this probe. Logs the result (group list) or the thrown error.
 *
 * Part A is written to survive EITHER outcome (per-identity fallback to
 * today's Members.get loop on throw, see _spikeResolveIdentityGroupSet
 * below) -- this probe does not block implementation, it only converts the
 * open question to a recorded fact (AC-12).
 */
function SPIKE_probeGroupsListExternalV2() {
  try {
    var result = AdminDirectory.Groups.list({ userKey: 'stuart.donaldson@gmail.com' });
    Logger.log('SPIKE_probeGroupsListExternalV2 OK: ' + JSON.stringify(result));
  } catch (e) {
    Logger.log('SPIKE_probeGroupsListExternalV2 FAILED: ' + e);
  }
}

var _SPIKE_ACCESS_RANK = { NONE: 0, VIEW: 1, COMMENT: 2, EDIT: 3, OWNER: 4 };

// ---------------------------------------------------------------------------
// Two-sided cross-request cache (gts-dige Part B, gts-x9sk DESIGN "Q2" /
// "NEW FINDING R8-TENSION"). Caches INPUT FACTS ONLY -- never a resolved
// tier/method/verdict. The signed assertion (AccessControl.js's
// _verifySignedAssertion) is still verified on EVERY call before any cache
// is consulted, and the tier is still recomputed from scratch on every call
// from whatever facts are in cache (which may be up to
// _ACCESS_CACHE_TTL_SECONDS old) -- R8 unchanged (AC-6).
//
// Side 1: resourceId -> [{ groupEmail, role, ... }]  (Drive.Permissions.list
//         result, raw `items` array)
// Side 2: email      -> [groupEmail]                 (Groups.list result, or
//         the accumulated confirmed-member set from the Members.get
//         fallback -- see _spikeResolveIdentityGroupSet /
//         _spikeFinalizeIdentityGroupCache)
//
// TTL is a hard-coded constant per gts-x9sk's Q2 resolution (15 min). Open
// seam recorded for the hardening [TST]: parameterize rather than hard-code
// if TTL ever needs to be per-deployment configurable.
// ---------------------------------------------------------------------------

var _ACCESS_CACHE_TTL_SECONDS  = 900; // 15 min, gts-x9sk Q2
var _ACCESS_CACHE_RES_PREFIX   = 'ac:res:';
var _ACCESS_CACHE_ID_PREFIX    = 'ac:id:';
var _ACCESS_CACHE_REGISTRY_KEY = 'ac:registry';

function _accessCacheResKey(resourceId) { return _ACCESS_CACHE_RES_PREFIX + resourceId; }

/**
 * AC-7: namespaced per identity so an entry keyed on one verified email is
 * never consulted for a different email -- the email is baked directly into
 * the CacheService key, not looked up through any shared/aliased index.
 */
function _accessCacheIdKey(email) { return _ACCESS_CACHE_ID_PREFIX + email; }

/**
 * Best-effort read: a CacheService read failure, a missing key, or a value
 * that fails to JSON.parse are ALL treated as a cache MISS (returns null).
 * AC-10 (fail-open prohibited): every caller of this function falls back to
 * a live lookup on null -- never to a granted tier.
 * @param {GoogleAppsScript.Cache.Cache} cache
 * @param {string} key
 * @param {{cacheHits: number, cacheMisses: number}} [stats]
 * @returns {*} the parsed cached value, or null on any miss/failure
 */
function _accessCacheGet(cache, key, stats) {
  if (!cache) return null;
  var raw;
  try {
    raw = cache.get(key);
  } catch (e) {
    if (stats) stats.cacheMisses++;
    return null;
  }
  if (!raw) {
    if (stats) stats.cacheMisses++;
    return null;
  }
  try {
    var parsed = JSON.parse(raw);
    if (stats) stats.cacheHits++;
    return parsed;
  } catch (e2) {
    if (stats) stats.cacheMisses++;
    return null;
  }
}

/**
 * Best-effort write: a CacheService write failure (including exceeding the
 * 100KB per-key value cap) is NON-FATAL to the request (AC-10) -- swallowed
 * here so a cache write never surfaces as a request error.
 * @param {GoogleAppsScript.Cache.Cache} cache
 * @param {string} key
 * @param {*} value JSON-serializable
 */
function _accessCachePut(cache, key, value) {
  if (!cache) return;
  try {
    cache.put(key, JSON.stringify(value), _ACCESS_CACHE_TTL_SECONDS);
    _accessCacheRegisterKey(cache, key);
  } catch (e) {
    // non-fatal, AC-10
  }
}

/**
 * Tracks every key this module has written so flush_access_cache -- which
 * has no per-key enumeration API in CacheService -- can remove them all in
 * one shot. Best-effort: a registry read/write failure never blocks the
 * actual cache write in _accessCachePut above, it only means that one key
 * might survive an eventual flush_access_cache call until its own TTL
 * expires naturally.
 */
function _accessCacheRegisterKey(cache, key) {
  try {
    var raw  = cache.get(_ACCESS_CACHE_REGISTRY_KEY);
    var keys = raw ? JSON.parse(raw) : [];
    if (keys.indexOf(key) === -1) {
      keys.push(key);
      cache.put(_ACCESS_CACHE_REGISTRY_KEY, JSON.stringify(keys), _ACCESS_CACHE_TTL_SECONDS);
    }
  } catch (e) {
    // best-effort only
  }
}

/**
 * doPost action 'flush_access_cache' support (AC-9) -- removes every key
 * this module has written (both cache sides), via the registry above.
 * @param {GoogleAppsScript.Cache.Cache} cache
 * @returns {number} flushed count -- keys TARGETED for removal.
 *   CacheService.remove/removeAll report no per-key success/failure, so this
 *   is a best-effort count of keys attempted, not a confirmed-removed count.
 */
function _accessCacheFlushAll(cache) {
  if (!cache) return 0;
  var keys = [];
  try {
    var raw = cache.get(_ACCESS_CACHE_REGISTRY_KEY);
    keys = raw ? JSON.parse(raw) : [];
  } catch (e) {
    keys = [];
  }
  try {
    if (keys.length) cache.removeAll(keys);
    cache.remove(_ACCESS_CACHE_REGISTRY_KEY);
  } catch (e) {
    // best-effort
  }
  return keys.length;
}

/**
 * spike_seed_access bust (AC-8): removes the resource-side cache entry for
 * ONE folderId -- the folder spike_seed_access just mutated -- so an
 * immediate re-resolve observes the new permission instead of a cached
 * pre-seed value. Does not touch the identity side: spike_seed_access
 * mutates folder SHARING, never group MEMBERSHIP.
 * @param {GoogleAppsScript.Cache.Cache} cache
 * @param {string} folderId
 * @returns {number} flushed count (best-effort, see _accessCacheFlushAll)
 */
function _accessCacheFlushResource(cache, folderId) {
  if (!cache || !folderId) return 0;
  try {
    cache.remove(_accessCacheResKey(folderId));
  } catch (e) {
    // best-effort
  }
  return 1;
}

/**
 * doPost action 'flush_access_cache' handler (gts-dige, AC-9). Routed by
 * WebApp.js's doPost AFTER the WEBAPP_SECRET gate check -- an invalid or
 * missing secret never reaches this function; that gate already returns
 * { ok:false, error:'unauthorized' } and flushes nothing, satisfying AC-9's
 * negative case with no code needed here.
 * @param {Object} payload { secret } (secret already verified by doPost)
 * @returns {GoogleAppsScript.Content.TextOutput}
 */
function _handleFlushAccessCache(payload) {
  var cache   = CacheService.getScriptCache();
  var flushed = _accessCacheFlushAll(cache);
  GasLogger.log('access.cache.flush', { flushed: flushed });
  GasLogger.flush();
  return _jsonResponse({ ok: true, flushed: flushed });
}

/**
 * gts-dige Part A: resolves the FULL set of groups `email` belongs to via
 * ONE AdminDirectory.Groups.list({userKey: email}) call per identity per
 * request (AC-3), replacing the old N-calls-per-resource
 * AdminDirectory.Members.get probe loop. Checked against the two-sided
 * cache (side 2, email -> [groupEmail]) first (AC-5/AC-7).
 *
 * V2 (gts-x9sk DESIGN "NEW FINDING V2"): it was UNVERIFIED whether
 * Groups.list accepts an external (non-domain) userKey. This function
 * survives either outcome: on ANY throw from Groups.list, returns
 * path:'perGroup', groupSet:null, signalling the caller
 * (_spikeScanResourceGroupPermissions) to fall back to today's per-group
 * Members.get loop for this identity -- AC-4. The throw itself is NOT
 * tagged .error: for a V2-negative (external) identity this would become
 * the identity's *every-request* outcome, recreating exactly the log-noise
 * problem gts-q2sq already solved for the notmember tag on the sibling
 * fallback path. Never throws.
 *
 * @param {string} email verified caller email
 * @param {GoogleAppsScript.Cache.Cache} [cache]
 * @param {{directoryCalls: number, cacheHits: number, cacheMisses: number}} [stats]
 * @returns {{path: 'inverted'|'perGroup', groupSet: ?Object<string,boolean>,
 *   fromCache: boolean}}
 */
function _spikeResolveIdentityGroupSet(email, cache, stats) {
  var cached = _accessCacheGet(cache, _accessCacheIdKey(email), stats);
  if (cached && Object.prototype.toString.call(cached.groups) === '[object Array]') {
    var set = {};
    for (var i = 0; i < cached.groups.length; i++) set[cached.groups[i]] = true;
    return { path: cached.path === 'perGroup' ? 'perGroup' : 'inverted', groupSet: set, fromCache: true };
  }

  var groups;
  try {
    if (stats) stats.directoryCalls++;
    var resp = AdminDirectory.Groups.list({ userKey: email });
    groups = (resp && resp.groups) ? resp.groups.map(function (g) { return g.email; }) : [];
  } catch (e) {
    return { path: 'perGroup', groupSet: null, fromCache: false };
  }

  var groupSet = {};
  for (var j = 0; j < groups.length; j++) groupSet[groups[j]] = true;
  _accessCachePut(cache, _accessCacheIdKey(email), { path: 'inverted', groups: groups });
  return { path: 'inverted', groupSet: groupSet, fromCache: false };
}

/**
 * Writes cache side 2 (email -> [groupEmail]) at the end of a request when
 * the perGroup fallback path ran FRESH this request (not from a prior cache
 * hit) -- the accumulated set of groups CONFIRMED as members among whatever
 * groups this request's resource scan actually encountered. No-op for the
 * inverted path (already cached inside _spikeResolveIdentityGroupSet) and
 * no-op when this request's identity groups already came from a cache hit
 * (nothing new learned).
 *
 * ACCEPTED TRADEOFF (per gts-x9sk DESIGN, "cache the fallback outcome under
 * Part B exactly the same way"): unlike the inverted path's Groups.list
 * result (the identity's genuinely COMPLETE group membership), this cached
 * array only covers groups actually probed THIS request. A later request
 * against the SAME team/folders re-encounters the same candidate groups and
 * is therefore sound (AC-5's latency win holds). A request that later
 * touches a group never probed under this identity's existing cache entry
 * is treated, once this entry is written, as "not a member" rather than
 * triggering a fresh per-group check for just that group -- the same
 * staleness class already accepted for R8-TENSION, bounded by the 15-min
 * TTL. Flagged as an open seam for the hardening [TST] rather than solved
 * here (finer per-(email,group) caching would close it, at the cost of one
 * CacheService key per group instead of one per identity).
 *
 * @param {string} email
 * @param {GoogleAppsScript.Cache.Cache} cache
 * @param {{path: string, fromCache: boolean}} identityGroups
 * @param {Array<string>} confirmedGroupsAccumulator
 */
function _spikeFinalizeIdentityGroupCache(email, cache, identityGroups, confirmedGroupsAccumulator) {
  if (!identityGroups || identityGroups.path !== 'perGroup' || identityGroups.fromCache) return;
  _accessCachePut(cache, _accessCacheIdKey(email), { path: 'perGroup', groups: confirmedGroupsAccumulator || [] });
}

/**
 * access.resolve.done's groupCount field: the number of DISTINCT group
 * emails encountered across every resource scanned this request (union of
 * every resourceScanMemo entry's groupsChecked), regardless of path or
 * cache hit/miss.
 * @param {Object<string, {groupsChecked: Array<string>}>} resourceScanMemo
 * @returns {number}
 */
function _spikeDistinctGroupCount(resourceScanMemo) {
  var seen  = {};
  var count = 0;
  for (var key in resourceScanMemo) {
    if (!Object.prototype.hasOwnProperty.call(resourceScanMemo, key)) continue;
    var groups = resourceScanMemo[key].groupsChecked || [];
    for (var i = 0; i < groups.length; i++) {
      if (!seen[groups[i]]) { seen[groups[i]] = true; count++; }
    }
  }
  return count;
}

/**
 * Fallback path (A5): list the folder's group-type permissions, then check
 * whether `email` is a member of each via the Admin SDK Directory advanced
 * service. Effective access = highest role of any group email is a confirmed
 * member of. Requires the Drive (v2) and AdminDirectory advanced services
 * enabled in appsscript.json + the matching APIs enabled on the GCP project.
 *
 * gts-zm8w: a group's ROLE GRANTED AT THE SHARED DRIVE LEVEL (e.g. Manager)
 * is never returned by Drive.Permissions.list(folderId) when it is inherited
 * rather than re-granted directly on the folder -- Shared Drive membership
 * roles live on the drive resource, not as a per-file permission entry, and
 * Google's own Share UI declines to write a redundant/weaker override onto a
 * subfolder for a principal that already has higher effective access via the
 * drive. So after the folder-level scan, also resolve the folder's
 * containing Shared Drive (if any) and repeat the same group+membership scan
 * against Drive.Permissions.list(driveId) -- the union of both, MAX by rank,
 * is `email`'s true effective access for this folder.
 *
 * gts-49u1: `resourceScanMemo` and `stats` are optional, threaded from the
 * caller (AccessControl.js's _resolveTeamTierForVerifiedIdentity) so that
 * MULTIPLE folders sharing the same containing Shared Drive scan that
 * drive's group permissions at most ONCE per request instead of once per
 * folder -- see _spikeScanResourceGroupPermissions below for the memo
 * itself. Both are undefined for callers outside the dedupe path (e.g.
 * _handleSpikeCheckAccess's spike_check_access route), which preserves this
 * function's original always-fresh-scan behavior exactly.
 *
 * @param {string} folderId
 * @param {string} email
 * @param {Object<string, {level: string, groupsChecked: Array<string>}>} [resourceScanMemo]
 *   optional per-request memo keyed by resourceId (folder id OR Shared
 *   Drive id) -- NOT keyed by folderId with a special case for drives, so
 *   the same memo naturally dedupes both folder-level and drive-level
 *   scans that happen to collide (open seam recorded in gts-x9sk's DESIGN
 *   for the follow-on cross-request cache to key off the same axis).
 * @param {{permissionsListCalls: number, directoryCalls: number, cacheHits: number, cacheMisses: number}} [stats]
 *   optional per-request counters, incremented once per ACTUAL API round-
 *   trip (cache hits make none) -- the source for access.resolve.done's
 *   permissionsListCalls / directoryCalls / cacheHits / cacheMisses fields.
 * @param {GoogleAppsScript.Cache.Cache} [cache]
 *   gts-dige Part B: optional CacheService.getScriptCache() handle, threaded
 *   down to cache resource-side permission lists (side 1) across requests.
 *   Absent for callers outside the cross-request-cache path (e.g.
 *   _handleSpikeCheckAccess), which preserves this function's original
 *   always-fresh-scan behavior exactly.
 * @param {{path: 'inverted'|'perGroup', groupSet: ?Object<string,boolean>, fromCache: boolean}} [identityGroups]
 *   gts-dige Part A: the result of _spikeResolveIdentityGroupSet for `email`,
 *   resolved ONCE per request by the caller (not per folder). A non-null
 *   groupSet means the inverted query succeeded (live or cached) and
 *   membership is a local lookup; a null groupSet means the per-group
 *   Members.get fallback runs, unchanged from pre-gts-dige behavior.
 * @param {Array<string>} [confirmedGroupsAccumulator]
 *   gts-dige Part A/B: optional array, mutated in place, collecting every
 *   group email CONFIRMED as a member during the fallback (perGroup) path
 *   this request -- the caller caches this at the end of the request
 *   (_spikeFinalizeIdentityGroupCache) so a subsequent request against the
 *   same team/folders can skip the Members.get loop entirely.
 * @returns {{level: string, groupsChecked: Array<string>}}
 */
function _spikeAdminSdkFolderAccess(folderId, email, resourceScanMemo, stats, cache, identityGroups, confirmedGroupsAccumulator) {
  var result = { level: 'NONE', groupsChecked: [] };

  _spikeScanResourceGroupPermissions(folderId, email, result, resourceScanMemo, stats, cache, identityGroups, confirmedGroupsAccumulator);

  var driveId = _spikeContainingDriveId(folderId);
  if (driveId) {
    _spikeScanResourceGroupPermissions(driveId, email, result, resourceScanMemo, stats, cache, identityGroups, confirmedGroupsAccumulator);
  }

  return result;
}

/**
 * Resolves the Shared Drive id containing `folderId`, or null for a plain
 * My Drive folder / on any lookup failure (fails closed to "no drive-level
 * check" rather than throwing -- gts-zm8w AC3).
 *
 * @param {string} folderId
 * @returns {?string}
 */
function _spikeContainingDriveId(folderId) {
  try {
    var file = Drive.Files.get(folderId, { supportsAllDrives: true, fields: 'teamDriveId' });
    return file.teamDriveId || null;
  } catch (e) {
    GasLogger.log('webapp.spike.access.error', { where: 'Drive.Files.get', message: String(e) });
    return null;
  }
}

/**
 * Scans one Drive resource's (folder OR Shared Drive) group-type permissions
 * and folds any confirmed membership into `result` (MAX by rank across
 * however many resources are scanned for the same `email`).
 *
 * gts-49u1: when `resourceScanMemo` is supplied and already holds an entry
 * for `resourceId`, the cached {level, groupsChecked} contribution is
 * folded straight into `result` with ZERO Drive/Directory API calls -- this
 * is what collapses N folders sharing one containing Shared Drive down to a
 * single Drive.Permissions.list + per-group AdminDirectory.Members.get set
 * for that drive within one request (AC-2/AC-2b). The memo is keyed on
 * `resourceId` alone (folder id OR drive id, same axis) and is safe to
 * reuse across every folder in the request because it, like the sibling
 * folderAccessMemo in AccessControl.js, is a fresh object scoped to one
 * request for one already-verified email -- never a cross-request or
 * cross-user cache (R8 unchanged, AC-R8).
 *
 * gts-dige Part A: when `identityGroups.groupSet` is non-null (the inverted
 * Groups.list query succeeded, live or from cache), membership per group is
 * a pure local Set lookup -- ZERO AdminDirectory.Members.get calls, and the
 * webapp.spike.access.notmember tag is never emitted (there is no per-group
 * probe left to fail). When `identityGroups` is absent or its groupSet is
 * null (Groups.list threw for this identity, or no caller supplied it),
 * this falls back to the ORIGINAL per-group Members.get loop unchanged --
 * same tags, same semantics, same call count (AC-4).
 *
 * gts-dige Part B: the resource's own Drive.Permissions.list result (side 1
 * of the two-sided cache) is checked via CacheService (`cache`) BEFORE the
 * in-memory `resourceScanMemo` short-circuit above returns, i.e. only
 * reached on a resourceScanMemo miss -- a cross-request cache hit still
 * costs zero Drive.Permissions.list calls (AC-5) even on the first time this
 * resourceId is seen within THIS request.
 *
 * @param {string} resourceId a folderId or a Shared Drive id
 * @param {string} email
 * @param {{level: string, groupsChecked: Array<string>}} result mutated in place
 * @param {Object<string, {level: string, groupsChecked: Array<string>}>} [resourceScanMemo]
 *   optional per-request memo, keyed by resourceId; see _spikeAdminSdkFolderAccess.
 * @param {{permissionsListCalls: number, directoryCalls: number, cacheHits: number, cacheMisses: number}} [stats]
 *   optional per-request counters; see _spikeAdminSdkFolderAccess.
 * @param {GoogleAppsScript.Cache.Cache} [cache] see _spikeAdminSdkFolderAccess.
 * @param {{path: string, groupSet: ?Object<string,boolean>}} [identityGroups] see _spikeAdminSdkFolderAccess.
 * @param {Array<string>} [confirmedGroupsAccumulator] see _spikeAdminSdkFolderAccess.
 */
function _spikeScanResourceGroupPermissions(resourceId, email, result, resourceScanMemo, stats, cache, identityGroups, confirmedGroupsAccumulator) {
  if (resourceScanMemo && Object.prototype.hasOwnProperty.call(resourceScanMemo, resourceId)) {
    var cached = resourceScanMemo[resourceId];
    if (_SPIKE_ACCESS_RANK[cached.level] > _SPIKE_ACCESS_RANK[result.level]) {
      result.level = cached.level;
    }
    result.groupsChecked = result.groupsChecked.concat(cached.groupsChecked);
    return;
  }

  // localResult holds THIS resource's own contribution, independent of
  // whatever `result` already carries from a prior resource in this same
  // _spikeAdminSdkFolderAccess call -- it's what gets cached, so a later
  // folder sharing this resourceId reuses exactly this resource's outcome,
  // not a value contaminated by another resource's level.
  var localResult = { level: 'NONE', groupsChecked: [] };

  var perms = _accessCacheGet(cache, _accessCacheResKey(resourceId), stats);
  if (!perms) {
    try {
      if (stats) stats.permissionsListCalls++;
      perms = Drive.Permissions.list(resourceId, { supportsAllDrives: true }).items || [];
      _accessCachePut(cache, _accessCacheResKey(resourceId), perms);
    } catch (e) {
      GasLogger.log('webapp.spike.access.error', { where: 'Drive.Permissions.list', message: String(e) });
      if (resourceScanMemo) resourceScanMemo[resourceId] = localResult;
      return;
    }
  }

  var invertedPath = !!(identityGroups && identityGroups.groupSet);

  for (var i = 0; i < perms.length; i++) {
    var p = perms[i];
    if (p.type !== 'group' || !p.emailAddress) continue;

    localResult.groupsChecked.push(p.emailAddress);

    var isMember = false;

    if (invertedPath) {
      // gts-dige Part A: pure local lookup against the already-resolved
      // group set for this identity -- zero AdminDirectory calls.
      isMember = !!identityGroups.groupSet[p.emailAddress];
    } else {
      // Fallback (V2-negative identity, or Groups.list threw): today's
      // per-group probe, unchanged. Members.hasMember() rejects external
      // (non-domain) memberKeys with "Invalid Input: memberKey" even though
      // external members are valid in a domain-managed group (confirmed via
      // SPIKE_authProbeExternal). Members.get() is the reliable call for
      // external members: a thrown 404 means "not a member," success means
      // confirmed membership.
      try {
        if (stats) stats.directoryCalls++;
        AdminDirectory.Members.get(p.emailAddress, email);
        isMember = true;
      } catch (e) {
        // Not-a-member and lookup-failed both land here — treat as "not
        // confirmed," never as a grant. But only the *unexpected* failures
        // (scope/permission/network — anything that isn't a plain "not a
        // member" 404) get the .error-suffixed tag: 404 is the common,
        // expected outcome for most groups on most folders, and tagging it
        // .error trips the shared pytest fail-fast log scanner
        // (scn/session.py::_check_gas_errors) for unrelated tests that never
        // touch this code path (gts-q2sq).
        var msg = String(e);
        var tag = /not found/i.test(msg)
          ? 'webapp.spike.access.notmember'
          : 'webapp.spike.access.error';
        GasLogger.log(tag, {
          where: 'AdminDirectory.Members.get', group: p.emailAddress, message: msg
        });
        continue;
      }
      if (isMember && confirmedGroupsAccumulator) {
        confirmedGroupsAccumulator.push(p.emailAddress);
      }
    }

    if (!isMember) continue;

    var level = _spikeRoleToLevel(p.role);
    if (_SPIKE_ACCESS_RANK[level] > _SPIKE_ACCESS_RANK[localResult.level]) {
      localResult.level = level;
    }
  }

  if (resourceScanMemo) resourceScanMemo[resourceId] = localResult;

  if (_SPIKE_ACCESS_RANK[localResult.level] > _SPIKE_ACCESS_RANK[result.level]) {
    result.level = localResult.level;
  }
  result.groupsChecked = result.groupsChecked.concat(localResult.groupsChecked);
}
