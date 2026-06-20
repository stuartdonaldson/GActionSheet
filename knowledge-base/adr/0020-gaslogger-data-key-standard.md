# ADR-0020: GasLogger data-parameter-key standard

Status: Accepted
Date: 2026-06-19
Relates to: `src/GasLogger.js`, ADR-0019 (GasLogger tag-naming standard),
GTaskSheet-9dss

## Context

The same audit that produced ADR-0019 (`knowledge-base/staging/gaslogger-tag-taxonomy.md`)
also surveyed the `data` object's keys across all `GasLogger.log(tag, data)` call
sites and found two independent inconsistencies, distinct from the tag-casing
problem:

1. **`err` vs `error`.** The majority convention pairs `msg` (human-readable
   description) with `err` (the underlying error value/exception). `src/TestFixtures.js`'s
   `fixture.*` tags instead used a single `error:` key, sometimes with no `msg` at
   all, conflating both roles under a differently-named field.
2. **Redundant/shadowing `version` field.** `GasLogger.log()` already auto-stamps a
   top-level `version` from `BUILD_INFO.version` on every entry, and `_postToAxiom`'s
   row-building spreads `e.data` *after* the base object — so a call site that also
   passes `version` inside `data` silently overwrites the auto-stamped field on the
   Axiom row. Two call sites did this (`EditorAddonCard.js`'s `linkPreview.start`,
   `SyncManager.js`'s `sync.all.start.identity`); harmless today since both passed
   the same value, but fragile against a future edit to either field independently.

## Decision

| Concept | Key | Notes |
|---|---|---|
| Human-readable description | `msg` | Pairs with `err` when there's an underlying error |
| Error value/exception | `err` | String or `Error`; never `error` |
| Operation succeeded | `ok` | Boolean |
| Entity exists / was matched | `found` | Boolean |
| Count of N | `<noun>Count` | e.g. `docCount`, `rowCount`, `topicCount` |
| Entity ids | `docId`, `globalId`, `teamId`, `sheetId`, ... | camelCase; snake_case only when deliberately echoing a wire-contract field (see below) |
| Reserved — never set inside `data` | `version`, `op`, `ts`, `tag` | Auto-stamped by `GasLogger.log()` / `startOp()` |

Two things surveyed and deliberately left alone, so a future pass doesn't "fix" them:

- `global_id` (snake_case) on the `test.*` WebApp routes mirrors the WebApp JSON
  wire-contract field name (`src/ContractSchema.js`) — that contract is itself
  snake_case by design, distinct from internal GAS camelCase. Every other call site
  uses `globalId`.
- `docId` vs `masterDocId` vs `testDocId`/`cloneId` are three genuinely distinct
  entity roles in `TestFixtures.js`/`WebApp.js` (template doc / per-session clone /
  generic "doc this event is about"), not duplicate names for one thing.

`src/TestFixtures.js`'s `fixture.*` tags' bare `error:` keys were renamed to `err:`,
with an added `msg:` describing the failure where one wasn't already present. The
two call sites that redundantly passed `version: BUILD_INFO.version` inside `data`
had that key removed.

## Applying this to new call sites

1. If the call can fail, use `msg` (what was being attempted, plain English) + `err`
   (the exception/error value). Don't invent a third spelling.
2. Never set `version`, `op`, `ts`, or `tag` inside `data` — they're auto-stamped.
3. Count fields are `<noun>Count`; boolean success/match fields are `ok`/`found`.
4. Entity ids are camelCase (`docId`, `globalId`, ...) unless the call is echoing a
   wire-contract payload field that's deliberately snake_case (`src/ContractSchema.js`)
   — in that case, match the wire, not the GAS-side convention.

## Consequences

- **Easier:** an error-path call site's `data` shape is predictable; a reviewer
  spots a bare `error:` key or an explicit `version`/`op`/`ts`/`tag` as an immediate
  regression against this standard.
- **Constrains:** new call sites that need a different concept (not in the table
  above) should extend this ADR's table via a superseding ADR rather than inventing
  an ad hoc key silently.
