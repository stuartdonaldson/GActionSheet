# ADR-0008: In-text `AI-N:` token action identity

Status: Accepted
Date: 2026-05-29
Supersedes: ADR-0005

## Context

ADR-0005 chose REST-created **named ranges** as the durable identity for each floating action and
proposed a **two-project** "automation sidecar." Neither survived implementation:

- Smart-chip / rich-link pill elements (`insertRichLink`) do **not** appear in
  `Paragraph.getText()`, so a text-based scanner is required to find actions reliably
  (`work-log.md` 2026-05-28, §Decisions/Research). A named range adds a second source of truth that
  the scanner cannot see from `getText()` and that must be maintained through copy/paste and
  re-anchoring.
- The system was built as a **single** GAS project deployed as both a Workspace Add-on and a Web
  App (ADR-0007), not the two-project sidecar. The add-on and automation code share the same
  codebase and call each other directly.

This ADR records the identity mechanism the code actually uses and confirms the single-project
architecture over ADR-0005's sidecar. Per the project convention, **code is the source of truth
when code and documentation disagree**; this ADR bends the record to the code.

## Decision

Action identity is an **in-text token** `AI-N:` at the start of each floating-action paragraph,
where `N` is a per-document integer assigned on first sync. The cross-document key is
`globalId = {docFileId}/AI-{N}`, stored in ActionSheet column 1. No named ranges are created for
actions; the only named range in the document is the tracker-table heading anchor
(`gactionsheet-tracker-anchor`).

The single-script dual-deployment architecture (ADR-0007) stands. The two-project automation
sidecar of ADR-0005 is not adopted.

## Rationale

- The token is visible to `getText()`, so a cheap in-process scanner (`_scanFloatingActions`) can
  locate every action — including copy/pasted duplicates — without a second anchor store.
- One project, one `.clasp.json`, one deploy pipeline (ADR-0007); no cross-project secret sync.
- Re-anchoring and orphan detection key off `globalId`, which is stable across edits because it is
  literal text the scanner reads directly.

## Consequences

- **Retained alias name.** The ActionSheet column and the in-code field are still named
  `NamedRangeId` / `namedRangeId` — a fossil of the superseded named-range design. They carry a
  `globalId` string. A rename to `globalId` is tracked as cleanup, not done here.
- **In-process write suppression only.** Programmatic write suppression uses the in-process
  `WriteGuard._active` flag. ADR-0005's cross-execution `SYNC_IN_PROGRESS` script property is
  **not** used: Web App `doPost` writes run as the deployer in a separate execution and do not fire
  the installable `onActionSheetEdit` trigger (verified 2026-05-29). `WriteGuard.wrapPersistent` is
  a no-op alias of `wrap`, retained as a re-enable seam.
- **Duplicate handling.** Copy/pasted paragraphs sharing an `AI-N` are detected by the scanner
  (`isDuplicate`) and rewritten to canonical content on flush; only the canonical occurrence syncs
  to the sheet.
- **Single-tenant chip URL.** The action chip link is the single-tenant form
  `https://northlakeuu.org/GActionSheet/action/{globalId}`. A multi-tenant, sheet-ID-encoded URL
  (`…/action/{sheetId}/{globalId}`) remains future work — see `knowledge-base/ROADMAP.md`.

## Supersedes

Fully supersedes ADR-0005 (both the named-range identity and the two-project sidecar). Container
binding of the single script to the ActionSheet remains as described in ADR-0007.
