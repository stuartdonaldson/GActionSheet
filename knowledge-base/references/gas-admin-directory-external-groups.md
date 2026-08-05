# Group-Conferred Drive Access for External Members (Admin SDK Directory)

Reusable reference: resolving whether an arbitrary email — including one **external**
to the Workspace domain — has Drive access to a folder/file **via a domain-managed
Google Group**, not just direct sharing. Captured during Spike S2
(`gts-79dw.2`, `docs/verified-team-portal-plan.md` §6) against a real Shared
Drive folder, 2026-07-23.

**Candidate for elevation to `GAS-Core/best-practices/`** once a second project needs
this pattern (see `GAS-Core/best-practices/gas-webapp-admin/README.md` for the
"provenance / second use elevates it" convention this repo follows). Until then, this
file is the source of truth; `src/SPIKE.js` is the reference implementation.

---

## The mechanism (proven working)

1. `DriveApp.getFolderById(folderId).getAccess(email)` — resolves **direct** grants
   (viewer/editor added by email) correctly, including for external accounts. Returns
   `DriveApp.Permission.NONE` if the only access is via a group the email is a member
   of — **it does not expand group membership**.
2. Fallback for group-conferred access: `Drive.Permissions.list(folderId, {
   supportsAllDrives: true })` (Drive **v2** advanced service) → filter to `type ===
   'group'` entries → for each, check membership with `AdminDirectory.Members.get(
   groupKey, memberEmail)` (Admin SDK Directory advanced service), catching the thrown
   exception as "not a member." Effective access = highest-ranked role among all groups
   the email is a confirmed member of.
3. This resolves case (c) correctly for a genuinely external (`@gmail.com`) member of a
   domain-managed group, and does not falsely grant access to an unrelated external
   email (verified negative case).

---

## Gotchas (each cost real debugging time — check these in order for a "permission
denied" or "invalid input" error on a newly-added advanced service)

### 1. Manifest scope ≠ consent-screen scope

Adding a scope to `appsscript.json`'s `oauthScopes` is necessary but **not sufficient**.
The scope must *also* be registered on the OAuth consent screen (GCP Console → APIs &
Services → OAuth consent screen → Scopes, sometimes surfaced under a "Data Access" tab)
— otherwise Google silently refuses to grant it. No error surfaces at the consent-screen
step; the failure only appears later as a runtime "You do not have permission to call
..." from the API itself.

### 2. Advanced service declared ≠ underlying API enabled

Declaring `enabledAdvancedServices` in the manifest (e.g. `admin`/`directory_v1`) does
not by itself enable the underlying **Admin SDK API** in GCP Console → APIs & Services →
Library. Both steps are required. A disabled API can also *suppress* the OAuth consent
prompt entirely (no dialog appears at all, even for a from-scratch authorization) —
enable the API first if a consent prompt for a new scope never appears when re-running
an authorizing function.

### 3. Forcing re-authorization after adding a scope

Apps Script does not always detect that new scopes require re-consent, especially for a
script that was previously authorized. If re-running an authorizing function shows no
consent dialog and the same permission error persists:
1. Revoke the app's grant at `myaccount.google.com/permissions` (search by project/app
   name).
2. Re-run an editor function that actually **calls** the new service (a function that
   returns early without calling it will "authorize successfully" with an incomplete
   token — same class of gotcha as NUUC-Dispatch's `script.external_request` finding,
   `GAS-Core/best-practices/` TBD, currently in NUUC-Dispatch `docs/OPERATIONS.md`).
3. This must be the *same Google account* used to deploy the script (`clasp
   login`/`USER_DEPLOYING`) — confirmed in this session they were the same account, so a
   mismatch was ruled out as the cause here, but is worth checking first in a
   multi-account setup.
4. Redeploy (`pnpm run deploy:test` or equivalent) is *not* itself sufficient to pick up
   a new grant — the grant is tied to the developer account's authorization state, not
   the deployed version.

### 4. `AdminDirectory.Members.hasMember()` rejects external memberKeys

`AdminDirectory.Members.hasMember(groupKey, memberKey)` throws
`GoogleJsonResponseException: Invalid Input: memberKey` when `memberKey` is an external
(non-domain) email — **even when that email genuinely is a member of the group**.
Reproduced directly via `AdminDirectory.Members.hasMember(groupKey, 'user@gmail.com')`
under the same identity that succeeded with a domain-internal memberKey seconds
earlier — ruling out an auth/identity cause.

**Fix:** use `AdminDirectory.Members.get(groupKey, memberKey)` instead. A thrown
exception (404-style "Resource Not Found: memberKey") means "not a member"; a
successful return means confirmed membership. This is the reliable call for external
members; `hasMember()` is not.

### 5. `DriveApp.setSharing()` doesn't support Shared Drive items

`folder.setSharing(access, permission)` throws `Exception: Cannot use this operation on
a shared drive item` for a folder inside a Shared Drive (a `0A...`-prefixed folder ID).
No mutation occurs (confirmed safe to retry with a different approach — nothing needs
reverting after this specific error).

**Fix:** use the Drive v2 advanced service directly:
```js
var inserted = Drive.Permissions.insert(
  { role: 'reader', type: 'anyone' },
  folderId,
  { supportsAllDrives: true, sendNotificationEmails: false }
);
// inserted.id — save this to precisely revert:
Drive.Permissions.remove(folderId, inserted.id, { supportsAllDrives: true });
```

---

## Manifest additions required

```json
{
  "dependencies": {
    "enabledAdvancedServices": [
      { "userSymbol": "Drive", "serviceId": "drive", "version": "v2" },
      { "userSymbol": "AdminDirectory", "serviceId": "admin", "version": "directory_v1" }
    ]
  },
  "oauthScopes": [
    "...",
    "https://www.googleapis.com/auth/admin.directory.group.readonly",
    "https://www.googleapis.com/auth/admin.directory.group.member.readonly"
  ]
}
```

Plus the OAuth-consent-screen scope registration and Admin SDK API enablement from
gotchas #1–2 above — neither is expressible in the manifest.

---

## Reference implementation

`src/SPIKE.js` (`_spikeAdminSdkFolderAccess`, `_spikeAccessLevel`, `_spikeRoleToLevel`) —
throwaway spike code, `SPIKE_ENABLED`-gated. Read it alongside this doc before building
a permanent version; the code is the up-to-date mechanism, this doc is the up-to-date
list of why each gotcha happens.
