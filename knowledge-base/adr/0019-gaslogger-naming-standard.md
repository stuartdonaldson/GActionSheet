# ADR-0019: GasLogger tag-naming standard

Status: Accepted
Date: 2026-06-19
Relates to: `src/GasLogger.js`, ADR-0020 (GasLogger data-parameter-key standard),
GTaskSheet-x94a, GTaskSheet-aa7j (deferred — overloaded `sync.warn` split, not part
of this ADR), GTaskSheet-ecs1 (deferred — GAS/Python naming bridge, not part of
this ADR)

## Context

An audit of all `GasLogger.log(tag, data)` call sites (192 at audit time,
`knowledge-base/staging/gaslogger-tag-taxonomy.md`) found three coexisting
tag-casing conventions with no documented rule: the lowercase dot-namespaced
majority (`sync.warn`, `sidebar.delete.error`), a SCREAMING_SNAKE minority (15
distinct tags, ~27 call sites, all in `src/EditorAddonCard.js`/`WebApp.js`/
`PROBE.js` — the calling function's name uppercased), and one snake_case-domain
outlier (`verify_chip_integrity.done`). Not a functional break — Axiom can filter on
any string — but a dashboard faceting on tag name silently splits what should be
one bucket across casings, and the split grows every time a new call site is
copy-pasted from an inconsistent neighbor.

## Decision

Every `GasLogger.log()` tag follows `domain.event[.subEvent...]`:

- `domain` — lowercase, camelCase if multi-word, names the feature/entry point
  (`sync`, `teamScope`, `actionTrigger`, `importSelected`) — not the file it lives in.
- `event` — lowercase verb/state (`start`, `done`, `error`, `warn`, `complete`).
- No bare domain with no event. Every call site logs at a specific point in the
  function's life — give it an explicit `.start` if nothing more specific applies.
- The historical `kebab-case` vs `snake_case` split for multi-word
  events/sub-events (`flush-failed` vs `doc_not_found`) is **not** addressed by this
  standard — lower-impact than the casing/domain problem, left as-is.

All SCREAMING_SNAKE tags (`CREATE_ACTION_TRIGGER` → `actionTrigger.start`,
`IMPORT_SELECTED.error` → `importSelected.error`, etc.) and the snake_case-domain
outlier (`verify_chip_integrity.done` → `verify.chipIntegrity.done`) were renamed to
this convention in `src/EditorAddonCard.js`, `src/WebApp.js`, and the corresponding
test assertions in `tests/test_import.py`, `tests/test_journey.py`,
`tests/test_poc_features.py`. `src/PROBE.js`'s dynamic `'probe.' + surface` tag
already satisfied the rule once lowercased.

## Applying this to new call sites

1. Pick `domain.event[.subEvent]` — lowercase, camelCase domain, verb/state event.
2. Don't reuse a domain unless the call is genuinely the same feature/entry point.
3. Don't add a bare domain with no event — pick the specific lifecycle point
   (`.start`, `.done`, `.error`, `.warn`) the call actually represents.

## Consequences

- **Easier:** Axiom dashboards facet cleanly on tag casing with no normalizing
  query; a glance at any neighboring call site shows the convention to follow.
- **Constrains:** code review should flag a new SCREAMING_SNAKE or snake_case-domain
  tag as a regression against this standard.
- **Deferred, not part of this ADR:** GTaskSheet-aa7j (splitting the overloaded
  `sync.warn` tag into distinct doc-not-found sub-events, and the `Doc not found` /
  `Doc Not Found` msg-casing split) and GTaskSheet-ecs1 (documenting/bridging this
  `domain.event` taxonomy against the Python side's raw action/fixture names) are
  separate, larger-blast-radius decisions that need their own pass.
