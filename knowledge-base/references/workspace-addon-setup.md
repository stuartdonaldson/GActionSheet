# Google Workspace Add-on Setup Guide

Reusable reference for setting up and testing Google Workspace Add-ons (new-style, `addOns` manifest).
Last updated: 2026-05-22 (GActionSheet project, sdonaldson@northlakeuu.org).

---

## Add-on Types

| Type | Manifest key | Notes |
|------|-------------|-------|
| Editor Add-on (old) | `addon` | Simpler setup, deprecated path |
| **Workspace Add-on (new)** | `addOns` | This guide covers this type |

---

## GCP Setup — Required APIs

Enable all of these in the GCP project linked to the Apps Script project:

| API | When needed |
|-----|-------------|
| Google Workspace Add-ons API | Always — without it, test deployments install silently and never appear in Extensions menu |
| Apps Script API | Always |
| Google Workspace Marketplace SDK | Only for publishing (domain-wide install via Admin Console) |
| Google Drive API | If using DriveApp / GasLogger |
| Google Docs API | If using Docs REST API (batchUpdate, namedRanges) |

**Gotcha:** Workspace Add-ons API not being enabled is the most common silent failure. The test deployment installs without error but never shows in the Extensions menu.

---

## GCP OAuth Consent Screen

- **Internal** — for Google Workspace org accounts. No test users needed. All org users are automatically included. No "Testing" status shown (that only applies to External).
- **External** — for personal Gmail accounts or cross-domain testing. Add test users explicitly. Shows "Testing" status.

For development against a personal Gmail account, use External + add the Gmail address as a test user.

---

## clasp Setup Pitfalls

### Creating a project in a subdirectory
`clasp create` walks up the directory tree looking for `.clasp.json`. If one exists in a parent directory, it refuses with "Project file already exists."

**Fix:** Temporarily rename the parent `.clasp.json`, run `clasp create`, then restore it.
```bash
mv ../.clasp.json ../.clasp.json.bak
clasp create --type standalone --title "My Add-on"
mv ../.clasp.json.bak ../.clasp.json
```

### appsscript.json gets overwritten
`clasp create` replaces the local `appsscript.json` with a bare default (no `addOns`, no scopes).

**Fix:** Always restore your custom manifest immediately after `clasp create`. Commit the correct manifest before running `clasp create` so you can diff/restore easily.

### First push after create may skip
`clasp push` sometimes reports "Skipping push" on the first push because it thinks nothing changed.

**Fix:** Use `clasp push --force` after `clasp create`.

### oauthScopes required for versioned deployments
`clasp deploy` (versioned) fails with:
> For Google Workspace Add-ons, you must provide an explicit list of OAuth scopes in the manifest file

`oauthScopes` must be present in `appsscript.json` for any versioned deployment. HEAD deployments don't enforce this but can't be used in the Marketplace SDK.

### Create deployments AFTER linking the GCP project
Deployments created before the GCP project is linked may be tagged to the old default project. The Marketplace SDK will then return:
> Project Key is not associated with the current project or the script version doesn't exist.

**Fix:** Link the GCP project in Apps Script Project Settings first, then run `clasp deploy`.

---

## appsscript.json Manifest

Minimum working manifest for a Docs Workspace Add-on:

```json
{
  "timeZone": "America/New_York",
  "dependencies": {},
  "exceptionLogging": "STACKDRIVER",
  "runtimeVersion": "V8",
  "oauthScopes": [
    "https://www.googleapis.com/auth/drive"
  ],
  "addOns": {
    "common": {
      "name": "MyAddOn",
      "logoUrl": "https://www.gstatic.com/images/branding/product/2x/drive_48dp.png",
      "homepageTrigger": {
        "runFunction": "buildHomepageCard"
      }
    },
    "docs": {
      "homepageTrigger": {
        "runFunction": "buildHomepageCard"
      }
    }
  }
}
```

**Notes:**
- `logoUrl` must be a valid HTTPS URL. `gstatic.com` product branding URLs may return 404. Drive icon URL (`drive_48dp.png`) has been tested and accepted by the manifest validator.
- Do **not** add `"enabled": true` to `homepageTrigger` — it is undocumented and may cause silent failures.
- Declare `homepageTrigger` in **both** `common` and `docs`. Relying on `common` as fallback for `docs` works in principle but is less reliable.
- `"docs": {}` (empty object) signals the add-on extends Docs but relies on `common.homepageTrigger`. Works but explicit is safer.

---

## Testing Approaches

### Test deployments on a managed Google Workspace domain

Test deployments often **do not appear in the Extensions menu** on managed Google Workspace domains, even when:
- The correct GCP project is linked
- Workspace Add-ons API is enabled
- OAuth consent screen is configured (Internal)
- The test deployment is installed (silently, no auth prompt)
- The manifest has no errors

Root cause: domain-level policy or Workspace Add-on platform behavior that suppresses test deployments for managed accounts. No executions are logged — the trigger never fires.

**Diagnostic steps:**
1. Check Workspace Add-ons API is enabled in GCP
2. Check Admin Console → Apps → Google Workspace Marketplace apps → Settings → allow setting is permissive
3. Check Apps Script Executions log after attempting to open add-on — if empty, trigger never fired
4. Run `buildHomepageCard` manually from editor to confirm code is valid

### Option A — Publish as private domain app (for production)

Requires completing the full Marketplace SDK Store Listing, even for Internal apps:
- Icons: 32×32, 48×48, 96×96, 128×128 PNG
- Banner: 220×140 PNG
- At least one screenshot
- Terms of Service URL
- Privacy Policy URL
- Support URL
- Regions selection

**Icon generation** (ffmpeg, when ImageMagick unavailable):
```bash
ffmpeg -i logo.png -vf scale=128:128 logo-128.png -y
ffmpeg -i logo.png -vf scale=96:96  logo-96.png  -y
ffmpeg -i logo.png -vf scale=48:48  logo-48.png  -y
ffmpeg -i logo.png -vf scale=32:32  logo-32.png  -y
ffmpeg -i logo.png -vf scale=220:140 banner-220x140.png -y
```

After publishing, install via Admin Console → Apps → Marketplace → Internal apps.

### Option B — Personal Gmail account (for development/walking skeleton)

Simpler path that bypasses Workspace domain restrictions:
1. GCP → OAuth consent screen → change to **External**
2. Add Gmail address as test user
3. Sign into browser as Gmail
4. Open Apps Script editor as Gmail → Deploy → Test deployments → Install
5. Open a Google Doc as Gmail → check Extensions menu

For production deployment, revert to Internal + complete Marketplace SDK publishing.

---

## Deployment ID Quick Reference

| Context | Use |
|---------|-----|
| Test deployment (developer only) | HEAD or any deployment ID via Deploy → Test deployments UI |
| Marketplace SDK App Configuration | Versioned deployment only (not HEAD) — created with `clasp deploy --description "..."` |
| Admin Console install | Versioned deployment ID from Marketplace SDK App Configuration |

---

## Minimum `npm` Scripts

```json
"scripts": {
  "push:addon": "cd src/addon && clasp push",
  "push:addon:force": "cd src/addon && clasp push --force",
  "deploy:addon": "cd src/addon && clasp deploy --description \"v$(date +%Y%m%d)\""
}
```
