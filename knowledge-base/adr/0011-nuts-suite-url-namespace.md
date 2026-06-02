# ADR-0011: NUTS suite identity and `NUTS/<tool>` URL namespace

Status: Accepted
Date: 2026-05-29
Refines: ADR-0008 (chip-URL consequence only — identity decision unchanged)

## Context

The project name `GActionSheet` is action-specific, but the project is becoming a multi-tool suite
(see `staging/2026-05-29-workspace-addon-toolset-direction.md`). Action smart-chip links currently
use the action-named path `https://northlakeuu.org/GActionSheet/action/{globalId}` (the value noted
in ADR-0008 §Consequences). As additional tools arrive — e.g. an `@`-menu LLM trigger — each needs
its own `linkPreview` / URL pattern, and the action-specific path does not scale to a suite.

A naming decision is needed for the suite umbrella and the URL scheme, separately from how add-on
files are organized (ADR-0010) and from the action-identity mechanism (ADR-0008).

## Decision

Adopt **Northlake Unitarian Tool Suite (NUTS)** as the internal umbrella name and namespace all
suite tool URLs under `https://northlakeuu.org/NUTS/<tool>/…` — one host, one `pathPrefix` per
tool, so each tool registers a distinct `linkPreview` (and future `@`-menu) pattern.

- The action chip URL base is `https://northlakeuu.org/NUTS/action`, defined as
  `ACTION_CHIP_URL_BASE` (`SyncManager.js`). The `appsscript.json` `linkPreview`
  `hostPattern` (`northlakeuu.org`) / `pathPrefix` (`NUTS` — the suite root) is
  hand-synced — the manifest cannot read script globals.
- The `pathPrefix` is `NUTS` (not `NUTS/action`) so that Google's URL validation
  succeeds for the action chip URL and all future sibling tools with one pattern.
- Sibling tools take sibling paths under `NUTS/`, e.g. `NUTS/llm`.
- `NUTS` is the preferred top-level scoping prefix for any suite-wide identifier; `GActionSheet`
  continues to denote the action tool specifically.

## Rationale

- A per-tool path under one host lets each tool own its `linkPreview` pattern without a new host or
  domain, and decouples the URL scheme from the action-specific product name.
- A single source of truth (`ACTION_CHIP_URL_BASE`) plus a documented manual sync to the manifest
  keeps the two unavoidable copies (script + manifest) from drifting.
- An internal suite name can be adopted immediately without the cost/risk of renaming the repo,
  scriptId, or published add-on.

## Consequences

- **Refines ADR-0008 §Consequences "Single-tenant chip URL":** the chip link path changes from
  `…/GActionSheet/action/{globalId}` to `…/NUTS/action/{globalId}`. ADR-0008's identity decision
  (the in-text `AI-N:` token and `globalId` key) is unchanged and not superseded.
- **pathPrefix amendment (2026-06-02):** changed from `NUTS/action` to `NUTS`. Root cause:
  Google validates the chip URL (fetches it) before calling `onLinkPreview`; a narrower prefix
  that points at a redirect to an auth-gated endpoint causes a system error for non-editor users.
  The suite-root prefix `NUTS` is broader, leaves room for sibling tools, and the northlakeuu.org
  redirect at `/NUTS/action` points to the `/exec` deployment (publicly accessible).
- **Migration:** chips inserted under the old `GActionSheet/action` path stop firing
  `onLinkPreview` until re-flushed; a sync rewrites each chip to the new `NUTS/action` URL.
  Acceptable pre-production — no live deployment yet (GTaskSheet-erc). The manifest change takes
  effect only after `npm run deploy:test`.
- The published add-on display name is already generic ("Northlake Doc Tools"); a published rename
  to NUTS, and any repo/scriptId rename, are **not** decided here.
- The future multi-tenant, sheet-ID-encoded form (`…/action/{sheetId}/{globalId}`) noted in
  `knowledge-base/ROADMAP.md` remains compatible — it slots under `NUTS/action/…`.
- Recorded in bd memory `nuts-suite-name-url-scoping` and the toolset-direction staging doc.
