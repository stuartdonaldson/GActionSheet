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
| Hover preview card (`linkPreviewTriggers`) | ✗ publish-gate — untestable in dev |
| Visual chip pill rendering | ✗ publish-gate — untestable in dev |

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
- Inserted URL format: `https://stuartdonaldson.github.io/GActionSheet/action/{namedRangeId}`
- This matches the manifest `linkPreviewTriggers` pattern (`hostPattern: “stuartdonaldson.github.io”`, `pathPrefix: “/GActionSheet/action/”`)

### Chip display text

The link display text should be a short label — details belong in the hover preview card.  
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

