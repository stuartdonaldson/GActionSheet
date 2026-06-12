# ADR-0011: NUTS suite identity and `NUUTS` chip URL namespace

Status: Accepted
Date: 2026-05-29 (amended 2026-06-11)
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

Adopt **Northlake Unitarian Tool Suite (NUTS)** as the internal umbrella name, and namespace all
suite tool chip URLs under a single shared path, `https://northlakeuu.org/NUUTS`, dispatched by
query parameters rather than per-tool path segments.

- The action chip URL base is `https://northlakeuu.org/NUUTS`, defined as
  `ACTION_CHIP_URL_BASE` (`SyncManager.js`). The full action chip URL is
  `ACTION_CHIP_URL_BASE + '?c=view&globalId=' + encodeURIComponent(globalId)` →
  `https://northlakeuu.org/NUUTS?c=view&globalId=<id>`.
- The `appsscript.json` `linkPreview` pattern is `hostPattern: northlakeuu.org`,
  `pathPrefix: NUUTS` — hand-synced to `ACTION_CHIP_URL_BASE`, since the manifest cannot
  read script globals.
- The `c` query parameter is the suite-wide command/tool dispatch key (`c=view` for the
  action preview). One registered `pathPrefix` (`NUUTS`) covers every present and future
  suite tool.
- Sibling tools (e.g. a future `@`-menu LLM trigger) reuse the `NUUTS` path with a
  distinct `c` value, rather than a sibling path segment.
- `NUTS` is the preferred top-level scoping prefix for suite-wide internal identifiers
  (naming, bd memory keys, etc.); `NUUTS` is specifically the chip-URL path token.
  `GActionSheet` continues to denote the action tool specifically.

## Rationale

- A single shared path with `c`-param dispatch lets every suite tool share one
  `linkPreview` registration, rather than each tool needing its own path-based pattern.
- Query-param dispatch decouples the URL scheme from the action-specific product name
  and from any individual tool's lifecycle.
- `ACTION_CHIP_URL_BASE` as a single source of truth, plus documented manual sync to the
  manifest `pathPrefix`, keeps the two unavoidable copies (script + manifest) from
  drifting.
- An internal suite name can be adopted immediately without the cost/risk of renaming
  the repo, scriptId, or published add-on.

## Consequences

- **Refines ADR-0008 §Consequences "Single-tenant chip URL":** the chip link path
  changes from `…/GActionSheet/action/{globalId}` to
  `…/NUUTS?c=view&globalId={globalId}`. ADR-0008's identity decision (the in-text
  `AI-N:` token and `globalId` key) is unchanged and not superseded.
- The published add-on display name is already generic ("Northlake Doc Tools"); a
  published rename to NUTS/NUUTS, and any repo/scriptId rename, are **not** decided
  here.
- The future multi-tenant, sheet-ID-encoded form noted in `knowledge-base/ROADMAP.md`
  remains compatible — it slots in as an additional query parameter under
  `NUUTS?c=view&...`.
- Recorded in bd memory `nuts-suite-name-url-scoping` and the toolset-direction staging
  doc.
