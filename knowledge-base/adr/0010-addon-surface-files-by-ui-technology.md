# ADR-0010: Organize add-on surface files by UI technology

Status: Accepted
Date: 2026-05-29
Relates to: ADR-0007 (single-script dual-deployment)

## Context

GActionSheet began as a single action-tracking tool and is being promoted from a POC into a
multi-tool Google Workspace suite (Docs cleanup, AI/LLM document tooling, Sheets tools) — see
`staging/2026-05-29-workspace-addon-toolset-direction.md` (repo-root `staging/`, distinct from `knowledge-base/staging/`).

A concrete near-term surface, an LLM side-chat, needs **HtmlService** (a rich, client-interactive
UI), whereas every current surface is **CardService**. The two are structurally different code,
launched by different mechanisms — CardService via `addOns` manifest triggers (homepage,
contextual `@`-menu, linkPreview); HtmlService via an `onOpen` menu calling
`Ui.showSidebar(HtmlOutput)` — and they coexist in one Apps Script project. During the M6/M7
cleanup (de-namespacing the POC `_poc_*` code) the surface files were already being renamed, making
this the cheapest moment to fix the organizing axis before the second UI technology lands.

## Decision

Add-on surface files are organized by **UI technology first, host second**, named
`{Surface}Addon{UITech}.js`, where the suffix marks the rendering framework:

- `…Card.js` — CardService (Workspace Add-on).
- `…Html.js` — HtmlService (Editor add-on; `onOpen` → `Ui.showSidebar`), reserved for rich
  client-interactive UIs such as the planned LLM side-chat.

Host-agnostic logic — the sync engine, Web App proxy, tracker, verification, logger, version, and
shared config — stays **unsuffixed** as the shared core. Host (Docs / Sheets) is a filename
qualifier only when a surface is host-specific and the host is not already obvious.

Current surface files: `WorkspaceAddonCard.js` (homepage/contextual card), `EditorAddonCard.js`
(`@`-menu create-action + smart-chip link preview).

## Rationale

- UI technology is the hardest, most durable boundary in Apps Script add-on code, and the one the
  suite is about to cross; organizing by it keeps CardService and HtmlService code from
  intermingling and reserves an unambiguous slot for each new surface.
- "Editor" in a filename reads as *the Docs-editor host surface*, not the legacy Editor-Add-on
  *framework* type; the `Card` / `Html` suffix removes that ambiguity regardless of reading.
- Naming the convention now, mid-rename, avoids a second churn and corrects the prior `EditorAddon`
  name that had pre-claimed the HtmlService slot for CardService code.

## Consequences

- **Easier:** the LLM HtmlService side-chat and any future rich dialog have a predetermined,
  collision-free home (`EditorAddonHtml.js` / similar); the shared engine is clearly delineated from
  per-surface UI.
- **Harder / constrains:** every new surface file must declare its UI technology in the name; a
  surface that mixes both technologies is disallowed and must be split.
- A formal `core/` directory layer (vs. the current flat unsuffixed convention) is **not** decided
  here; it is deferred to a future ADR once a second tool exists to validate the seam.
- The convention is recorded in `docs/DESIGN.md` §Module Map and bd memory
  `addon-file-naming-convention`; full rationale lives in the toolset-direction staging doc.
