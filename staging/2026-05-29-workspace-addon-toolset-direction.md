# Staging Draft: Workspace Add-on Toolset Direction

Date: 2026-05-29
Status: Draft for discussion

## Context
The current project has focused on action-item tracking, which influenced the project name and scope.

A broader direction is under consideration: evolve into a Google Workspace add-on/webapp toolset that supports both Google Docs and Google Sheets workflows, reducing deployment and authorization overhead from separate bound scripts.

## Pain Points Identified
- Bound scripts require repeated copying and authorization per document.
- Managing separate add-on/deployment paths across utilities creates overhead.
- Utilities that could share infrastructure are currently fragmented.

## Candidate Capability Expansion
1. Keep action-item tracking as one module (Sheets-focused).
2. Add Docs utilities as menu-driven tools.
3. Add AI-assisted document compliance/style tooling as a module.

## Example New Utility (Docs)
- A document cleanup utility that removes excessive blank lines and applies formatting normalization after markdown/LLM paste operations.
- Triggered from a Docs menu item.

## Example AI Utility (Docs)
- Analyze a document against a template.
- Suggest or apply updates to align with target style/structure.
- Uses LLM calls with clear preview/confirm flow.

## Directional Recommendation (Draft)
Move toward a unified platform with modular features:
- Shared core: auth/scopes handling, deployment/versioning workflow, logging/telemetry, shared utility libraries.
- Host-specific modules: Docs tools and Sheets tools.
- Keep action tracking as a first-class capability, but not the only product identity.

## Draft Next Steps
1. Define a provisional product framing for this repo as a Workspace automation toolset.
2. Create an initial module map:
   - Core platform
   - Docs deterministic tools (cleanup/normalization)
   - Docs AI-assisted tools (template conformance)
   - Sheets action-tracking tools
3. Define a command contract for tools:
   - Host (Docs/Sheets)
   - Required scopes
   - Inputs/outputs
   - Safe mode (preview/dry-run)
   - Audit log event format
4. Select one pilot migration target:
   - Docs blank-line cleanup utility as first module candidate.
5. Evaluate packaging strategy:
   - Single integrated add-on/webapp versus separate add-ons based on scope/risk/release cadence.
6. Draft an ADR once the package boundary decision is made.

## Open Questions
- Should Docs and Sheets features share one published add-on identity or split by risk/scopes?
- What is the minimum common infrastructure required before first migration?
- Which user workflow should be optimized first: deterministic cleanup or AI conformance?

## Naming Conventions (decided 2026-05-29)

Settled during the M6/M7 cleanup pass, ahead of the toolset build-out. Capture so it is not re-litigated when the new modules start.

### Primary axis: UI technology, not host
The hardest, most durable boundary in Apps Script add-on code is the **rendering
framework**, not the host application — and it is the boundary the toolset is about
to cross (today everything is CardService; the LLM side-chat will be HtmlService).
So surface files are organized by UI tech first, host second.

| Framework | Trigger mechanism | Good for | File suffix |
|-----------|-------------------|----------|-------------|
| **CardService** (Workspace Add-on) | `addOns` manifest triggers (homepage, contextual `@`-menu, linkPreview) | declarative panels, quick actions, status controls | `…Card.js` |
| **HtmlService** (Editor add-on) | `onOpen` menu → `Ui.showSidebar(HtmlOutput)` | rich client-interactive UIs — **LLM side-chat**, complex dialogs, streaming | `…Html.js` |

Both frameworks coexist in one Apps Script project. Convention: `{Surface}Addon{UITech}.js`.

### Current and reserved file layout

```
WorkspaceAddonCard.js   homepage / contextual card (CardService)            [present]
EditorAddonCard.js      @-menu create-action + link-preview chip (CardService) [present]
EditorAddonHtml.js      LLM side-chat / rich dialogs (HtmlService)          [reserved — future]

core / engine (host-agnostic, unsuffixed):
  SyncManager.js  WebApp.js  TrackerTable.js  VerifySync.js  GasLogger.js  Version.js
  + future: LlmClient, shared Config
```

- "Editor" reads as **the Docs-editor host surface**, not the legacy Editor-Add-on
  *framework* type (in strict Google vocabulary both current files are Workspace
  Add-on CardService). The `Card` / `Html` suffix removes the ambiguity either way.
- Host (Docs / Sheets) becomes a filename qualifier only when a surface is
  host-specific and the host is not already obvious from context.
- Shared config has a single source of truth in the engine: e.g.
  `ACTION_CHIP_URL_BASE` (SyncManager.js) is the one chip-URL definition; the
  `appsscript.json` linkPreview `hostPattern`/`pathPrefix` must be hand-synced to it.

### Suite name & URL path scoping (decided 2026-05-29)
- **Internal suite name:** **Northlake Unitarian Tool Suite (NUTS)**. This is the
  umbrella identity the action tracker, Docs cleanup, AI conformance, etc. live under.
  `GActionSheet` stays the name of the *action* tool specifically.
- **URL namespace:** suite tool links live under `https://northlakeuu.org/NUTS/<tool>/…`
  on one host, one `pathPrefix` per tool → each tool gets its own linkPreview pattern.
  - Action chips: `NUTS/action/{globalId}` (`ACTION_CHIP_URL_BASE`, SyncManager.js;
    manifest `hostPattern: northlakeuu.org`, `pathPrefix: NUTS/action`).
  - Reserved siblings: e.g. `NUTS/llm/…` for an `@`-menu LLM trigger.
- **`NUTS` is the top-level scoping prefix** for any suite-wide identifier when one
  is needed, in preference to the action-specific `GActionSheet`.
- **Scope boundary:** this adopts an internal name + URL scheme only. It does **not**
  rename the repo / scriptId / published add-on. The published add-on display name is
  already generic ("Northlake Doc Tools") and could later align to NUTS — that rename
  stays deferred to the product-framing ADR.
- **Migration note:** chips inserted under the old `GActionSheet/action` path will not
  fire `onLinkPreview` until re-flushed; a sync rewrites each chip to the new
  `NUTS/action` URL. Acceptable pre-production (no live deployment yet — GTaskSheet-erc).

### Before building the HtmlService side-chat — open items
- **Two UI delivery paths exist:** (A) HtmlService sidebar via `onOpen` (embedded,
  best UX); (B) serve the chat HTML from the existing Web App (`doGet`) and open it
  from a card button via `setOpenLink` (reuses the deployment, opens as overlay/tab).
  Decide deliberately.
- **Verify current Google guidance** on the Editor-Add-on publishing track before
  committing — the `Ui.showSidebar(HtmlService…)` API is stable, but Google has been
  steering Editor Add-ons toward Workspace Add-ons; confirm the publishing path.

### Deferred to the product-framing ADR (do NOT build yet)
- A formal `core/` platform layer, the tool **command contract** (host, scopes,
  inputs/outputs, safe mode, audit-log event format), and AI-module scaffolding.
- Repo / scriptId / product rename (`GActionSheet` → toolset name). The add-on
  display name is already generic ("Northlake Doc Tools"), which buys time.
- Single-vs-split published add-on identity (Open Question #1 above).

## Boundaries for This Draft
- This note is exploratory only, **except** the Naming Conventions section above,
  which records a decision already applied to the codebase (2026-05-29).
- No implementation or repository-wide document updates are included in this step
  beyond the file renames and chip-URL consolidation that motivated the convention.
