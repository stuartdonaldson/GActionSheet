Updated POC Plan

Create the branch and isolate the experiment.
Branch: poc/editor-addon-action-chip
Keep the existing sync flow unchanged.
Put all experimental code behind a separate namespace.

Add a branding decision up front.
Define one canonical chip/menu icon for the POC.
Recommended default: the 32 px PNG at action-logo-t-32.png.
Reason: it matches smart-chip icon scale better than the larger PNG, and is lower risk than relying on SVG rendering in all chip surfaces.

Publish the icon at a stable HTTPS URL before wiring the manifest.
logoUrl must be a public HTTPS asset.
For the POC, either reuse the existing hosted logo location pattern or publish the selected PNG to the same public asset host already used by the add-on.
Do not point the manifest at a local repo path.

Extend the Docs @action proof of concept with branded entry points.
Add a Docs createActionTrigger with:
label text like Create action
logoUrl pointing at the published 32 px logo
a minimal creation flow for action text, optional assignee, optional status
This proves the logo appears in the @ menu as well as on the inserted chip.

Extend link preview metadata with the same logo.
Add linkPreviewTriggers for the action resource URL pattern.
Use the same logoUrl so the inserted chip and preview experience stay visually consistent.
The preview card should use the action title as the chip title and the logo as the small chip graphic.

Keep the document contract unchanged from the prior POC, but make the chip visibly branded.
Target paragraph form:
[GActionSheet chip with logo] [optional assignee token] [freeform action text] [optional trailing status]
Example:
[Action A-1042 chip] @alice@example.com Finish launch checklist (Open)

Add explicit logo-related validation to the POC.
Validate these separately from the sync logic:
the logo appears in the Docs @ menu
the inserted chip shows the logo
the hover preview card preserves the same branding
the chip remains legible at small size
fallback behavior is acceptable if the logo fails to load

Prefer PNG for the first implementation, keep SVG as a secondary test only.
For the POC, use the PNG first.
If you want to test SVG later, do it as a narrow follow-up check, not the baseline, because the POC question is chip viability, not asset-format troubleshooting.

Keep the rest of the POC narrow.
Reuse the existing Web App and ActionSheet path.
Build the experimental scanner separately.
Test edit durability and non-add-on-user readability.
Defer broader Sheets-host work until the Docs chip flow is proven.

Added Success Criteria

The @action item appears in the Docs @ menu with the GActionSheet logo.
The inserted action chip displays the GActionSheet logo.
The chip preview card uses the same branded identity.
The logo remains recognizable at chip scale and does not create visual ambiguity with a native person chip.
The branded chip still degrades acceptably for collaborators without add-on access.
../DevStandard/knowledge-base/gas-addon-guide.md has been updated to cover this editor add-on and smart-chip pattern, and the guide has been restructured as a general Google ecosystem add-on guide.
One design constraint to keep: the logo should signal “GActionSheet resource,” not “fake Google person chip.” That avoids confusing users and makes the new identity model clearer.

---

## POC Findings  (branch poc/editor-addon-action-chip, 2026-05-27)

### What was proven

| Behaviour | Result |
|-----------|--------|
| `@action` item in Docs @-menu with GActionSheet logo | ✓ confirmed |
| New Action form card renders with logo header | ✓ confirmed |
| Link with correct URL inserted at cursor on submit | ✓ confirmed |
| Action row written to ActionSheet via WebApp | ✓ confirmed |
| Confirmation card shown after successful create | ✓ confirmed (updateCard) |
| Hover preview card (`linkPreviewTriggers`) | ⚠ domain Marketplace install active — testing in progress |
| Visual chip pill rendering | ⚠ domain Marketplace install active — testing in progress |

### OAuth scopes required

Two scopes must be added to `appsscript.json` beyond the base set:
- `https://www.googleapis.com/auth/workspace.linkcreate` — required for `createActionTriggers`
- `https://www.googleapis.com/auth/workspace.linkpreview` — required for `linkPreviewTriggers`

Adding these triggers a re-authorization prompt on next add-on open.

### `createActionTriggers` — card action response constraints

Card action callbacks within a `createActionTriggers` card are subject to a strict allowlist. Findings from iterating through all options:

| Response type | Result |
|---------------|--------|
| `setNotification()` | ✗ disallowed — “Disallowed elements for link creation: [notification]” |
| `setNavigation().pushCard()` | ✗ disallowed — “Disallowed elements for link creation: [push_card_item]” |
| `setNavigation().popCard()` | ✗ disallowed — “Disallowed elements for link creation: [pop_card]” |
| `setStateChanged()` | ✗ disallowed |
| `return;` (undefined) | Card stays open — no error, no close |
| `setNavigation().updateCard()` | ✓ **allowed** — replaces form with confirmation card |

**Pattern to use**: `CardService.newActionResponseBuilder().setNavigation(CardService.newNavigation().updateCard(confirmationCard)).build()`

**Non-existent APIs (do not use)**: `CardService.newSmartChipConfig()` and `CardService.newRenderAction()` are not present in the GAS runtime as of 2026-05-27. Attempts to call them throw `TypeError: CardService.newSmartChipConfig is not a function`. These appear in AI-generated code (confirmed Gemini hallucination) but are not in the CardService reference documentation.

### URL scheme and format

- `https://` is the correct scheme — `linkPreviewTriggers` `hostPattern` implies HTTPS; custom schemes (e.g. `action://`) are not supported.
- Inserted URL format: `https://northlakeuu.org/GActionSheet/action/{namedRangeId}`
- This matches the manifest `linkPreviewTriggers` pattern (`hostPattern: “northlakeuu.org”`, `pathPrefix: “/GActionSheet/action/”`)
- Using a real domain the org controls (`northlakeuu.org`) is preferred over GitHub Pages or placeholder domains — Docs may perform URL validation and the domain resolving improves UX when users click the link directly

### Chip conversion is user-prompted, not automatic

Per Google's documentation: “When users type or paste a URL into a document or spreadsheet, Google Docs or Google Sheets **prompts them to replace the link with a smart chip**.”

The conversion prompt fires on **user input only** — typing or pasting. Programmatic insertion via `DocumentApp.getCursor().insertText()` + `Text.setLinkUrl()` creates a plain hyperlink; it does **not** trigger the conversion prompt. The chip pill rendering requires either:
1. The user pastes the URL directly (Docs then offers “replace with chip”), or
2. There may be a right-click / manual “convert to chip” option in the Docs UI.

**Implication**: after `createActionTrigger` inserts the link programmatically, the user sees a styled hyperlink, not a pill chip. The link is functional (clicks to the URL) and the `linkPreviewTriggers` hover card will fire once the add-on is Marketplace-installed — but the rounded pill appearance requires user-initiated conversion.

### Card header title is the chip display title

Per Google's documentation and sample code comments:
> “Uses the text from the card's header for the title of the smart chip.”

The **card header title** returned by `onLinkPreview` becomes the chip's visible label in pill form. The hyperlink display text set by `_poc_insertActionChip` (e.g. `@action: Finish launch checklist`) is what shows in the pre-conversion plain-link state only — it has no effect on the chip pill appearance.

This means `_poc_buildPreviewCard` should set the card header title to a clean, short action label (e.g. the action text truncated to ~40 chars), not a full sentence or URL fragment.

**Current implementation**: the card header title is set to the AI-N id (e.g. `AI-3`); the card subtitle is set to the action text. This produces the intended display at the top of the card.

### Card header title appears twice in the rendered preview card

Google renders the card header title in two places within the preview card:
1. As the clickable chip-link at the very top of the card (the "title" region)
2. Again inside the card body as a repeated title element

This is a platform rendering behaviour — not a code duplication bug. Setting `CardHeader.setTitle(actionId)` and `CardHeader.setSubtitle(actionText)` results in the AI-N id appearing at the top as a link **and** again in the body. The subtitle (action text) appears only once.

**Implication for `_poc_buildPreviewCard`**: do not add any widget in the card section that repeats the header title value — the platform already renders it. Only add section widgets for data not already shown in the header (status, assignee, actions).

### Link preview card widget restrictions

Google's `linkPreviewTriggers` context enforces strict limits on which CardService widgets are allowed:
- **Forbidden**: `TextInput`, `SelectionInput` (includes DROPDOWN) — throws `"Disallowed elements for link preview: [DROPDOWN, text_input]"` at runtime
- **Forbidden**: `pushCard`, `popCard` navigation — throws `"Disallowed elements for link preview: [push_card_item]"`
- **Allowed**: `TextButton`, `ImageButton`, `DecoratedText`, `TextParagraph`, static section content, `updateCard` navigation

This means full edit forms cannot live in the link preview card. Status changes via `ImageButton` are the correct approach for quick mutations from the preview card.

### `createActionTriggers` manifest `id` field

The Google reference manifest includes `”id”` in each `createActionTriggers` entry (e.g. `”id”: “createCase”`). Our manifest now includes `”id”: “createAction”`. The `id` field may be required for correct chip wiring in some contexts; its absence in earlier versions was not confirmed as the cause of any specific failure.

### Chip display text

The hyperlink display text (pre-conversion state) should be a short label — details belong in the hover preview card.  
Current format: `@action: {truncated action text, max 40 chars} ({assignee handle})`  
Full action text as the link label made the chip unreadably long.

### @-menu nesting in developer test installs

In developer test deployments, the @-menu shows a two-level structure: the add-on name (“Action Sync”) is the first level, and “Create action” is a nested item. Published Marketplace add-ons get a flatter treatment. This is normal and not configurable.

### Architectural gap: chip actions vs floating actions

The POC revealed that chip-created actions are a parallel pathway that does not feed the existing document-sync model:

| | Floating action (existing model) | Chip action (POC) |
|---|---|---|
| Doc representation | Checklist item with `@person` token | Hyperlink at cursor |
| Sheet row | Written by sync scanner | Written directly by `upsert_action_rows` |
| Tracker table | ✓ populated during sync | ✗ not scanned |
| Sidebar action list | ✓ displayed | ✗ not displayed |
| Named-range anchor | Set during sync | Embedded in chip URL as `namedRangeId` |

Integrating chip actions into the sidebar and tracker table requires the sync scanner to recognise the chip URL pattern as an action anchor. This is scoped to 6ov.7 (chip document contract).

### WEBAPP_URL must be re-registered when switching deployments

`ScriptProperties` is shared across all deployments of the same script project. `WEBAPP_URL` is set by visiting the WebApp URL once (`doGet` calls `ScriptApp.getService().getUrl()` and stores it). When switching from test deployment to PROD deployment (or vice versa), failing to re-visit the new URL leaves the add-on calling the wrong WebApp endpoint — causing silent failures or stale-version responses.

**Root cause of link preview debugging session (2026-05-28)**: `onLinkPreview` was firing but the backend call was failing because `WEBAPP_URL` still pointed to the old test WebApp. GCP logs showed `CREATE_ACTION_TRIGGER` working (which is less dependent on the WebApp URL) while link preview appeared broken.

**Resolved** — see deployment-stamped WebApp URL section below. Manual re-registration is no longer required for named deployments.

### WEBAPP_URL self-discovery via identity token (superseded)

The identity-token approach (`ScriptApp.getIdentityToken()` + `deployment_id` JWT claim) was investigated as a way to discover the WebApp URL at runtime. It was superseded before testing by the deployment-stamping strategy, which solves the problem at push time without requiring any GAS runtime mechanism. The identity-token path is documented here for reference but is not implemented.

### Deployment-stamped WebApp URL (resolved 2026-05-28)

**Problem**: the WebApp URL (`WEBAPP_URL` script property) had to be manually registered after every deploy by visiting the URL in a browser. This was error-prone when switching between test and prod deployments — stale URLs caused silent backend failures.

**Strategy**: the deployment tool (`manage-deployments.js`) already knows the WebApp URL at push time — the deployment ID is stable and the URL is `https://script.google.com/macros/s/{deploymentId}/exec`. The deployment tool stamps the URL and a deployment-type suffix directly into `src/Version.js` before `clasp push`, so the GAS runtime always has the correct URL baked into its `BUILD_INFO`.

**Version string semantics**

| Deployment | Version suffix | `BUILD_INFO.webappUrl` |
|------------|---------------|------------------------|
| `npm run push` (developer HEAD) | `(DEV)` | `""` (empty) |
| `npm run deploy:test` | `(TEST)` | TEST WebApp URL |
| `npm run deploy:prod` | _(none)_ | PROD WebApp URL |

**Runtime URL resolution** — `getWebAppUrl()` in `Version.js`:
1. If `BUILD_INFO.webappUrl` is non-empty → use it (named deployment, URL is authoritative)
2. If empty → fall back to `ScriptProperties.getProperty('WEBAPP_URL')` (DEV / local override)

**`doGet` behaviour**:
- Always returns version info (version string, build date, WebApp URL) as plain text — useful for confirming which deployment is live
- If `BUILD_INFO.webappUrl` is empty → self-registers `WEBAPP_URL` in script properties (preserves the manual-visit workflow for DEV HEAD deployments)

**Why `npm run push` also stamps `(DEV)` and clears the URL**: a raw push without a deploy type would otherwise leave stale `(TEST)` markers and a stale URL from the previous named deployment in `Version.js`. Stamping on every push keeps the file accurate regardless of push path.

**DEV push workflow**: `npm run push` pushes to HEAD but does not redeploy. For the add-on in Google Docs to pick up the new code, the developer must:
1. In the Apps Script editor: open Deployments → update the test deployment to point to the latest version (or HEAD)
2. In Google Docs: uninstall the test add-on, then reinstall the updated test deployment

This is a Google platform constraint — Docs caches the installed add-on version and does not hot-reload on push.

**Tradeoff**: `src/Version.js` now contains deployment-specific data (a live WebApp URL) that is environment-specific and should not be committed with a named URL. Convention: `Version.js` after any named deploy is considered local state — `npm run push` (and therefore `update-revision`) resets it to the `(DEV)` / empty state before pushing.

### Marketplace listing version must be updated after every deploy

The `linkPreviewTriggers` URL pattern matching is driven by the manifest of the **Marketplace-installed version**, not the current push. After `npm run deploy:prod` creates a new version, the GCP Console → Marketplace SDK → App Configuration → Docs add-on → script version field must be updated manually to the new version number, then the listing re-published.

`createActionTriggers` runs from the PROD deployment directly (always current). `linkPreviewTriggers` patterns are client-side and come from the Marketplace manifest. These are dispatched differently — keeping the Marketplace version stale silently breaks link preview while leaving chip creation working.

### `pathPrefix` format

Both `/GActionSheet/action/` (with leading slash) and `GActionSheet/action` (without) were tested. The Google reference sample uses no leading slash. Our manifest uses the leading slash form. Neither was confirmed as the definitive cause of any pattern-matching failure; the primary issue was the Marketplace version not being updated.

### Publish-gate features

Both the hover preview card and the visual chip pill rendering (rounded pill shape with logo) appear to be activated only for Marketplace-published add-ons. In developer test mode, a URL matching the `linkPreviewTriggers` pattern inserts as a plain hyperlink. This is consistent with Google's documentation that the smart-chip rendering is a Docs client-side feature gated on the add-on being installed through the Workspace Marketplace.

**Implication**: full end-to-end visual verification of 6ov.6 (hover preview) requires a published add-on. The mechanism (URL pattern, preview card handler, manifest entry) is confirmed correct; the rendering is a deployment environment constraint.

---

## Architecture: current, domain-internal, and public multi-tenant

### Architecture A — Current single-tenant (POC / domain internal)

**Purpose**: one organisation, one ActionSheet owned by the add-on developer/admin. All document authors write into the same shared sheet via a central WebApp. Simple to operate; not suitable for distribution.

```mermaid
flowchart TD
    subgraph Google Docs
        D1[Doc author]
        D2[Doc viewer]
    end

    subgraph GAS — single script project
        AO[Add-on\ncard triggers]
        WA[WebApp\ndoPost]
    end

    subgraph Developer Drive
        AS[(ActionSheet\nGoogle Sheet)]
    end

    D1 -->|@action chip creation| AO
    D2 -->|hover linkPreview| AO
    AO -->|upsert / verify rows| WA
    WA -->|read / write| AS
```

**Properties**
- `WEBAPP_URL` and `WEBAPP_SECRET` stored in script-level `ScriptProperties`
- WebApp executes as the deploying user (developer account)
- ActionSheet is the developer's own sheet — all customers share one dataset
- URL pattern: `https://stuartdonaldson.github.io/GActionSheet/action/{namedRangeId}`

**When to use**: POC validation, single-domain internal deployments where a shared ActionSheet is acceptable (e.g. a team installing for a specific workspace with one managed sheet).

---

### Architecture B — Domain-internal install (near-term target)

**Purpose**: same single-tenant data model, but add-on is properly installed for domain users via the Workspace Marketplace (domain-only listing). This unlocks `linkPreviewTriggers` chip rendering and hover preview — the two features blocked in developer test mode.

Identical to Architecture A except for deployment path:

```mermaid
flowchart TD
    subgraph Google Workspace Domain
        U1[Domain user A]
        U2[Domain user B]
    end

    subgraph GAS — same script project
        AO[Installed add-on\ncard triggers]
        WA[PROD WebApp]
    end

    subgraph Admin Drive
        AS[(ActionSheet\nGoogle Sheet)]
    end

    U1 -->|@action — chip renders as pill ✓| AO
    U2 -->|hover — preview card fires ✓| AO
    AO -->|upsert / verify| WA
    WA -->|read / write| AS

    GC[Admin console\ndomain install] -.->|installs add-on for domain| AO
```

**What changes vs A**
- PROD WebApp deployment created and used (not TEST)
- Marketplace SDK configured with visibility = "My domain"
- Admin console installs the add-on domain-wide (or to a specific OU)
- `linkPreviewTriggers` chip rendering becomes active ✓

**Still single-tenant** — every domain user reads/writes the same ActionSheet.

---

### Architecture C — Public multi-tenant (future, Marketplace distribution)

**Purpose**: any Google Workspace user installs the add-on. Each customer gets their own ActionSheet created in their own Drive on first run. No central server or shared data.

```mermaid
flowchart TD
    subgraph Customer A workspace
        DA1[Doc author A]
        DV1[Doc viewer A]
        AS_A[(ActionSheet A\nin A's Drive)]
    end

    subgraph Customer B workspace
        DA2[Doc author B]
        DV2[Doc viewer B]
        AS_B[(ActionSheet B\nin B's Drive)]
    end

    subgraph GAS — release script project
        AO[Installed add-on\ncard triggers]
    end

    DA1 -->|@action| AO
    DV1 -->|hover preview| AO
    AO -->|SpreadsheetApp.openById\nsheetId from URL| AS_A

    DA2 -->|@action| AO
    DV2 -->|hover preview| AO
    AO -->|SpreadsheetApp.openById\nsheetId from URL| AS_B

    AO -.->|first-run setup\ncreates sheet, stores ID\nin UserProperties| AS_A
    AO -.->|first-run setup| AS_B
```

**What changes vs B**

| Concern | B (domain internal) | C (public multi-tenant) |
|---------|---------------------|------------------------|
| ActionSheet location | Admin's Drive (shared) | Each user's own Drive |
| Data access path | Via central WebApp | `SpreadsheetApp.openById()` directly |
| WebApp | Required | Removed |
| Per-user state | `ScriptProperties` (shared) | `UserProperties` (per-user) |
| First-run | Manual setup | Add-on creates sheet automatically |
| Chip URL | `…/action/{namedRangeId}` | `…/action/{sheetId}/{namedRangeId}` |
| Non-owner preview | WebApp lookup | `openById` — sheet must be viewer-accessible |
| GCP project | Shared dev/domain project | Separate release project + GCP |
| Billing | Developer pays nothing extra | Developer pays nothing — no backend |

**Key design constraint**: the chip URL must encode the ActionSheet ID so that `onLinkPreview` can locate the correct sheet regardless of which user's document is open. The document creator's sheet ID is embedded at chip-creation time. For non-owners to see the preview card, the ActionSheet must be shared with at least "viewer" access (same sharing model as the Doc itself).

---

## Chip URL design

### Current URL (POC)
```
https://stuartdonaldson.github.io/GActionSheet/action/poc-8a08ae22-dd91-4c1d-b4ca-c2c6e4a58625
                                                        └── namedRangeId only
```

**Problems with GitHub Pages URL for production**:
- Reveals the developer's GitHub username and repository name — not professional
- Ties the `linkPreviewTriggers` `hostPattern` to `stuartdonaldson.github.io` — breaks if the repo moves or is renamed
- Not brandable; confusing to end users who see the URL

### How `linkPreviewTriggers` pattern matching works

The Google Docs client checks every hyperlink in the document against the `linkPreviewTriggers` patterns from all installed add-ons. Matching is purely string-based — no cryptographic ownership verification:

```json
"patterns": [{ "hostPattern": "stuartdonaldson.github.io", "pathPrefix": "/GActionSheet/action/" }]
```

- `hostPattern` matches the full hostname exactly (no wildcards at this level)
- `pathPrefix` matches the beginning of the URL path
- Scheme is always `https://` — no custom schemes supported
- The URL does **not** need to serve content — the preview comes from the add-on handler, not the URL itself
- If a user clicks the link (vs hovers), they navigate to the URL — a 404 is poor UX in production

### Recommended production URL format

Register a purpose-specific domain, e.g. `gactionsheet.app` (or `actionsheet.app` if available):

```
Architecture B (domain internal):
https://gactionsheet.app/action/{namedRangeId}

Architecture C (public multi-tenant):
https://gactionsheet.app/action/{sheetId}/{namedRangeId}
```

**Manifest change** (`linkPreviewTriggers`):
```json
"hostPattern": "gactionsheet.app",
"pathPrefix": "/action/"
```

**Benefits**:
- Brand-aligned, no GitHub identity exposure
- Stable regardless of repo location
- The domain can serve a minimal landing page / web viewer for when users click the link directly
- Path is short and clean
- `sheetId` can be embedded in the path without making the URL unwieldy

**The URL itself need not resolve to content for the chip mechanism to work** — but having `https://gactionsheet.app/action/{sheetId}/{namedRangeId}` serve a simple read-only action view (via a GitHub Pages or Cloud Run page) significantly improves UX for non-add-on users who click the link in an email or a browser.

### URL migration path

POC → domain internal → public each require a URL format change. Each change requires:
1. Update `_POC_ACTION_URL_BASE` constant in `EditorChipPoc.js`
2. Update `linkPreviewTriggers` `hostPattern` + `pathPrefix` in `appsscript.json`
3. Existing chips in documents continue to work as long as the old pattern remains in the manifest (add both patterns during transition if needed)

---

## GCP and script project topology per architecture

| Architecture | Script project | GCP project | Marketplace listing |
|-------------|---------------|-------------|---------------------|
| A — POC / dev | Single (dev) | Single (existing) | None |
| B — Domain internal | Single (dev) | Single (existing) | Private, domain-only |
| C — Public Marketplace | Separate release project | Separate release GCP | Public listing |

**Why a separate release project for C**: the Marketplace listing is tied to the GCP project and script project. When the listing is public, `clasp push` on dev HEAD would immediately affect published users unless isolated. Separation makes promotion explicit: code is pushed to the release project only after testing on the dev project.

For A and B, separation adds complexity with no benefit — the domain-only listing is low-risk and a single project is sufficient.

