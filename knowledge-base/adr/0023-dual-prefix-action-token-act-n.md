# ADR-0023: Dual-Prefix Action Token — `ACT-N:` Canonical, `AI-N:` Read-Compatible

Status: Accepted
Date: 2026-08-05
Accepted: 2026-08-26 (Stuart Donaldson, gts-4l1a)
Supersedes: ADR-0008 (token spelling only — identity model, chip URL shape, and
single-project architecture from ADR-0008 are retained, not reopened)

## Context

ADR-0008 chose the in-text token `AI-N:` as action identity, with `globalId = docId + '/AI-' + N`
as the cross-document sync key. A markup-spec review raised `ACT-N:` as the preferred spelling
going forward (clearer as an abbreviation of "action" than "AI", which reads as "artificial
intelligence" in a Workspace add-on context).

The token literal is hard-coded at every call site that builds or matches it — chip URL
construction, REST verify checks, badge-splice length math, UI sort/display labels, and the
`TestFixtures.js` fixture surface (~9 files, ~40 occurrences) — rather than drawn from one shared
constant. That is the actual cost driver for this change, independent of which spelling is chosen,
and is closed as part of this decision rather than carried forward again.

Documents already live with `AI-N:` tokens embedded as literal paragraph text, hyperlinks, and
status-icon links (ADR-0008, in production since 2026-05-29). Those documents must keep working
without a migration pass.

## Decision

1. **`ACT-N:` is canonical for all new writes.** Every code path that emits a token (add-on
   "create action" flow, sheet-triggered doc rewrite, REST flush) writes `ACT-N:`.
2. **`AI-N:` remains valid on read, indefinitely.** The scanner regex matches
   `(?:ACT|AI)-(\d+):` at paragraph start or immediately after a soft return. No migration pass
   rewrites existing documents; both spellings are supported permanently, not as a transitional
   state.
3. **N is one shared namespace across both prefixes.** `_nextAvailableN`-style scans (see
   `EditorAddonCard.js:637`) consider `ACT-N:` and `AI-N:` tokens together when computing the
   next available integer and when detecting duplicates — an `AI-3:` and an `ACT-3:` in the same
   document are the same identity slot, never two different actions.
4. **The token literal is centralized.** A single shared constant (e.g. `_ACTION_TOKEN_PREFIX =
   'ACT'` plus `_ACTION_TOKEN_READ_PREFIXES = ['ACT', 'AI']`) replaces every hard-coded `'AI-'`
   string currently duplicated across `SyncManager.js`, `EditorAddonCard.js`, `WebApp.js`,
   `WorkspaceAddonCard.js`, and `TestFixtures.js`. All emit/match sites are refactored to read
   from it. This is what makes rule 2 (permanent dual-read) cheap to sustain rather than a forked
   maintenance burden.
5. **`globalId` format is unchanged in shape** (`docId + '/' + token`), only the token spelling
   changes for new writes; existing stored `globalId`s containing `AI-N` remain valid keys and are
   not rewritten.

## Consequences

**Positive:**
- Closes a real design gap (hard-coded token string) that predates this decision and would have
  made any future token change expensive regardless of spelling.
- No migration pass, no risk to already-synced production documents, no user-visible disruption.
- Centralizing the token makes a *third* prefix (if ever needed) a one-line change instead of
  another multi-file sweep.

**Negative / tradeoffs:**
- Two valid spellings live in the codebase and in documents permanently — `AI-N:` never fully
  retires. Any future contributor reading a document or a token-matching regex needs to know both
  are legitimate, not that one is a bug.
- Add-on-facing copy (card confirmation text, help text) must be audited so it doesn't show a
  stale `AI-N:` example once `ACT-N:` is canonical for new actions — tracked as an implementation
  task under this ADR, not a design question.
- `_findAiTokenParagraph`-style exact-string paragraph lookups (`SyncManager.js:2788`) must be
  updated to try both prefixes or they will fail to locate pre-existing `AI-N:` paragraphs during
  flush — a correctness requirement of rule 4, called out explicitly so it isn't missed during
  implementation.

**Resolved at Accept (2026-08-26):** yes — the centralizing refactor (rule 4) is numbered as its
own `[IMP]`/`[TST]` twin-ticket pair (gts-mmyc et al.) ahead of the `custom_fields` work in
ADR-0024, since ADR-0024's implementation touches many of the same call sites.
