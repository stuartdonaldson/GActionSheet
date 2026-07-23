/**
 * SPIKE.js — Spike S2 (GTaskSheet-79dw.2): folder/doc access verification for
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
 * See ../docs/verified-board-portal-plan.md §6 for the full spike contract,
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

var _SPIKE_ACCESS_RANK = { NONE: 0, VIEW: 1, COMMENT: 2, EDIT: 3, OWNER: 4 };

/**
 * Fallback path (A5): list the folder's group-type permissions, then check
 * whether `email` is a member of each via the Admin SDK Directory advanced
 * service. Effective access = highest role of any group email is a confirmed
 * member of. Requires the Drive (v2) and AdminDirectory advanced services
 * enabled in appsscript.json + the matching APIs enabled on the GCP project.
 *
 * @param {string} folderId
 * @param {string} email
 * @returns {{level: string, groupsChecked: Array<string>}}
 */
function _spikeAdminSdkFolderAccess(folderId, email) {
  var result = { level: 'NONE', groupsChecked: [] };

  var perms;
  try {
    perms = Drive.Permissions.list(folderId, { supportsAllDrives: true }).items || [];
  } catch (e) {
    GasLogger.log('webapp.spike.access.error', { where: 'Drive.Permissions.list', message: String(e) });
    return result;
  }

  for (var i = 0; i < perms.length; i++) {
    var p = perms[i];
    if (p.type !== 'group' || !p.emailAddress) continue;

    result.groupsChecked.push(p.emailAddress);

    // Members.hasMember() rejects external (non-domain) memberKeys with
    // "Invalid Input: memberKey" even though external members are valid in a
    // domain-managed group (confirmed via SPIKE_authProbeExternal). Members.get()
    // is the reliable call for external members: a thrown 404 means "not a
    // member," success means confirmed membership.
    var isMember = false;
    try {
      AdminDirectory.Members.get(p.emailAddress, email);
      isMember = true;
    } catch (e) {
      // Not-a-member and lookup-failed both land here — treat as "not
      // confirmed," never as a grant.
      GasLogger.log('webapp.spike.access.error', {
        where: 'AdminDirectory.Members.get', group: p.emailAddress, message: String(e)
      });
      continue;
    }

    if (!isMember) continue;

    var level = _spikeRoleToLevel(p.role);
    if (_SPIKE_ACCESS_RANK[level] > _SPIKE_ACCESS_RANK[result.level]) {
      result.level = level;
    }
  }

  return result;
}
