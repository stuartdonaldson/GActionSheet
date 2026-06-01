# ADR-0009: Dirty-flag conflict resolution

Status: Accepted
Date: 2026-05-29
Supersedes: ADR-0002

## Context

ADR-0002 specified `Date Modified` timestamp precedence (latest wins) with three tie-break rules.
The implemented sync does not compare timestamps. `onActionSheetEdit` marks a user-edited row with
`Sync Status = 'Dirty'`, and `_handleSyncActionRows` resolves each row on that flag alone; the
`Date Modified` value it loads is never compared for conflict resolution.

Per the project convention, **code is the source of truth when code and documentation disagree**;
this ADR records the mechanism the code actually uses and supersedes ADR-0002.

## Decision

The conflict winner is determined by the `Sync Status` flag, per row:

- `Sync Status = 'Dirty'` (the row was edited on the sheet since the last sync) → **sheet wins**;
  the sheet values are flushed to the document floating action.
- Otherwise → **doc wins**; the document's scanned state overwrites the sheet row (when values
  differ).

`Date Modified` is retained for archival age (Closed + 30 days) and audit, **not** for conflict
resolution.

## Rationale

- A single explicit edit-intent flag is simpler for non-technical users to reason about than
  timestamp arithmetic, and it is immune to clock skew between local time and GAS execution time.
- The installable `onEdit` trigger already marks the edited row, so the flag is a natural,
  already-present signal — no extra bookkeeping.

## Consequences

- The ADR-0002 tie-break rules (equal-timestamp, timestamp-vs-none, tracker-row-wins) do not apply
  and are not implemented.
- Concurrent edits to both sides between syncs resolve by the flag (a sheet edit wins if `Dirty` is
  set), not by recency; one side's record overwrites the other with no field-level merge.
- A stale `Dirty` flag would wrongly force a sheet win, so mutation paths clear `Sync Status` after
  a successful sync (`patch_action_status`, the sheetWins/doc-wins branches, and
  `_syncSheetRowToDoc` on confirmed flush).
- `Date Modified` clock skew is irrelevant to the conflict outcome.
