# ADR-0022: Inline character formatting takes precedence over Config's uniform action-text style

**Status:** Accepted — confirmed by Stuart Donaldson 2026-08-01. Implementation (already live in
the working tree per plan-fix.md Session 9) requires no further change.
**Date:** 2026-08-01 (confirmed 2026-08-01)
**Relates to:** gts-zocq (inline bold/italic round-trip), gts-d99c/gts-1pk (configFormat sampling,
ADR-context in plan-fix.md Session 8), gts-dr8j (soft-return round-trip — the analogous precedent
for treating doc-authored intent as authoritative over a mechanical flatten)

## Context

`_actionTextStyleRequest` (`SyncManager.js`) applies one `updateTextStyle` request over the
**entire** action-text range on every flush, sourced from the Config sheet's `action_text` row
(gts-d99c, opt-in — `null` until `configFormat()` is run). Before this decision, that request's
`fields` mask included `bold` and `italic`, so every flush **unconditionally reasserted** the
Config-sampled bold/italic over the whole range — destroying any inline (per-word) bold/italic
the author actually typed in the doc. This is the flattening gts-zocq exists to fix; it is
conditional on Config being configured (see the bead's own 2026-07-26 comment), which makes the
defect worse, not better: formatting silently survives for most users and is destroyed for the
subset who ran `configFormat()`.

Three composition options were on file (gts-zocq DESIGN §1):
- (a) Config sets a base style; inline runs applied after as narrower overrides in the same
  batch — requires provable request ordering inside one `batchUpdate`.
- (b) Drop `bold`/`italic` from Config's uniform-style fields mask; inline runs own those two
  attributes exclusively; Config keeps font family/size/color/underline.
- (c) Config style is authoritative; inline formatting is accepted as lost.

No existing test asserted uniform bold/italic on action text before this change (confirmed via
grep, per the bead's own comment) — there is no recorded executable intent this decision breaks.

## Decision

**Option (b).** `_actionTextStyleRequest` no longer sets or asserts `bold`/`italic`; its `fields`
mask is now `underline,foregroundColor,weightedFontFamily[,fontSize]`. Inline runs
(`_buildFlushRequests`'s new per-run `updateTextStyle` requests, gts-zocq) exclusively own
bold/italic going forward. Config's `action_text` row still uniformly controls font family, size,
color, and underline exactly as gts-d99c intended.

## Rationale

- Smallest change that makes the two features compose rather than compete — no ordering
  guarantee needed between a base-style request and per-run overrides inside one `batchUpdate`.
- Preserves gts-d99c's visual intent for every attribute a user actually configures
  `action_text` for, except the two this decision hands to inline runs.
- Consistent with this project's repeated precedent (gts-dr8j, Sessions 1-3): when a mechanical
  uniform transform collides with author-typed intent, author intent wins rather than being
  silently discarded.

## Consequences

- **Behavior change:** a user who previously ran `configFormat()` against a bold- or
  italic-styled sample, expecting **all** future action text to render uniformly bold/italic,
  no longer gets that — inline runs (or their absence) now decide bold/italic per character
  range. No test exercised the old behavior, but it did exist and this ADR changes it.
- Font family, size, color, and underline are unaffected — still uniform, still Config-owned.
- This ADR's decision is **assumed, not confirmed**, per the plan-fix.md Session 9 brief's
  explicit instruction to implement the on-file recommendation behind an isolated, clearly
  flagged, cheaply-reversible change when synchronous user confirmation isn't available in-session,
  rather than silently assume approval. Reverting is a two-line diff
  (`_actionTextStyleRequest` in `SyncManager.js`) if the user vetoes this reading.

## Downstream dependency (added 2026-08-31)

**ADR-0031** (sync entry points and rendering conformance) compares a document's rendered
character style against Config on user-initiated single-document syncs. This ADR's split is what
tells that comparison which attributes it may look at:

- `ai_token` range — Config owns all six (`bold`, `italic`, `underline`, `foregroundColor`,
  `weightedFontFamily`, `fontSize`; see `_aiTokenStyleRequest`'s `fields` mask,
  `SyncManager.js:3391`). The token is machine-rendered, never author-typed, so there is no
  author intent to protect.
- `action_text` range — Config owns **four only**: `fontFamily`, `fontSize`, `color`, `underline`
  (`_actionTextStyleRequest`'s mask, `SyncManager.js:3437`). **`bold` and `italic` are excluded and
  must never be compared or asserted**, because this ADR handed them to author-typed inline runs.

A conformance check that compared `action_text` bold/italic would re-flatten per-word author
formatting on every user sync — reintroducing precisely the defect this ADR exists to prevent.
The exclusion is recorded here as well as in ADR-0031 because this is where a reader will look
for it.

## Open question this ADR does not resolve

Whether options (a) or (c) would be preferred if the user disagrees with (b) — not evaluated
further here since (b) is the on-file recommendation this session is authorized to implement
pending veto, not a fresh design exercise.
