# ADR-0024: `custom_fields` Column for Team-Defined Action Data

Status: Accepted
Date: 2026-08-05
Accepted: 2026-08-26 (Stuart Donaldson, gts-4l1a)

## Context

A markup-spec review proposed letting an action record carry team-defined `FieldName: value`
lines in the document (soft-return-separated, following the header line) — e.g. `Target:`,
`Progress:` — so teams can attach whatever contextual fields matter to them without a schema
change per team. The document remains the source of truth: a user types plain `Field: value`
lines directly in the paragraph, same as they type the header line today.

`sheetAction` (`ContractSchema.js:60-74`) is a fixed, positional column list —
`assignee_email`, `action_text`, `status`, `modified_date`, etc. — with no slot for arbitrary
key/value data. Two storage options were considered for where the parsed fields land once synced
to the sheet:

- Overload `action_text` with a JSON representation of the whole record (description + fields).
- Add a new column holding only the flexible fields, JSON-encoded, alongside the unchanged
  canonical columns.

`action_text` is read as a plain atomic string by existing comparison logic — row-identity/diff
checks (`TrackerTable.js`'s row-match logic, `VerifySync.js:88`) and display surfaces
(`WorkspaceAddonCard.js`, chip preview text) all assume it is a short human description, not a
serialized object. The sheet itself is admin-only, not a user-facing surface, but `action_text`
also round-trips into the document paragraph on flush — though on that path the value is always
re-parsed/re-rendered into `Field: value` lines rather than copied verbatim, so document
readability does not by itself decide between the two options.

## Decision

Add a new column, `custom_fields`, to `sheetAction`, holding the team-defined fields as a single
JSON-encoded object (`{"Target": "September meeting", "Progress": "..."}`). The existing canonical
columns (`assignee_email`/`assignee_name`, `action_text`, `status`, `modified_date`, etc.) are
unchanged in meaning and continue to hold only what they hold today — the header line's owner,
description, and status, and sheet-tracked timestamps. `action_text` never carries JSON.

The column is additive and optional, following the precedent set by the `runs` field
(`gts-zocq`, `SyncManager.js:157-162`): a row with no custom fields either omits the column value
or stores `{}`/empty, and every code path that predates this ADR keeps working unchanged.

## Examples

`<BR>` denotes a soft return (Shift+Enter) inside a single paragraph — the continuation-line
boundary this ADR's `custom_fields` column and ADR-0027's grammar both key off. All three
paragraphs below are otherwise identical (same token, assignee, status).

**Without fields — header line only, no continuation:**
```
ACT-3: jane@example.com Draft the Q3 budget memo (In Progress)
```
`custom_fields` is omitted (or stored as `{}`); `action_text` is `Draft the Q3 budget memo`.

**Soft return, no fields — continuation is prose, not a field:**
```
ACT-4: jane@example.com Draft the Q3 budget memo (In Progress)<BR>
Still waiting on finance numbers before this can close.
```
The continuation line doesn't match the `fieldLine` production (ADR-0027 rule 5 — no leading
`Name:` shape), so it's absorbed as prose into `action_text` rather than parsed as a field:
`action_text` becomes `Draft the Q3 budget memo\nStill waiting on finance numbers before this can close.`
`custom_fields` is still omitted/`{}` — this column only ever holds recognized `Field: value`
lines, never absorbed continuation prose.

**Soft return with fields:**
```
ACT-5: jane@example.com Draft the Q3 budget memo (In Progress)<BR>
Target: September board meeting<BR>
Progress: revenue section drafted, expenses pending
```
Each continuation line matches the `fieldLine` production. `action_text` remains
`Draft the Q3 budget memo` (unchanged by the fields); `custom_fields` becomes:
```json
{"Target": "September board meeting", "Progress": "revenue section drafted, expenses pending"}
```

## Consequences

**Positive:**
- `action_text`'s existing role as a comparable atomic value for row-identity/diff logic is
  preserved — no risk of spurious sync noise from JSON key-order or formatting differences.
- Every consumer that reads `action_text` expecting a plain description (sorting, chip preview,
  compact card labels) needs no change.
- Additive/optional column matches an established pattern in this schema; low blast radius for
  callers that don't touch custom fields.

**Negative / tradeoffs:**
- A new column is schema surface that has to be carried through the sheet-write path
  (`TeamActionWrite.js`), the Web App contract (`ContractSchema.js` messages), and any place that
  enumerates `sheetAction.fields`/`headers`/`columnsByField` in lockstep — three parallel arrays
  today (`ContractSchema.js:60-88`), each needing the new entry kept in sync.
- JSON in a sheet cell is opaque to Sheets-native sort/filter; acceptable since the sheet is
  admin-only and these fields are explicitly team-variable, not meant to drive sheet-level views.
- Parsing `FieldName: value` lines out of the document requires resolving three open grammar
  questions before the AC can freeze: (1) how a field-name line is distinguished from a
  continuation line that happens to contain a colon, (2) how a field-name line is distinguished
  from a new `ACT-N:`/`AI-N:` token line (ADR-0023) starting the next record, (3) what happens to
  a continuation line that appears before any `Field:` header has been seen in the record. These
  are parser-design questions, not schema questions, and are out of scope for this ADR.

**Resolved at Accept (2026-08-26):** no per-team allowlist. ADR-0027 rule 5 answers this with a
bounded `fieldLine` production (leading letter, ≤32 chars from `[A-Za-z0-9 _-]`, then `: `) instead
of a per-team enforced list — any team-typed field name matching that shape is accepted verbatim.

## Related

Depends on the token format defined in ADR-0023 for where a record starts and ends, but is
independently adoptable — this ADR's schema decision does not require ADR-0023 to be accepted.
