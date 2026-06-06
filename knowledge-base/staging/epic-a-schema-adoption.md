# Staging — EPIC-A: TeamData/DocData schema adoption

> **Transient working contract** (framework staging, ≤2 weeks). Deleted when EPIC-A enters
> the harden phase and the durable parts have graduated to docs/DESIGN.md, docs/OPERATIONS.md,
> and the team-scope schema ADR. Slice pilot of ADR-0013.
> Schema source: `knowledge-base/ROADMAP.md` §Future design: team scope with TeamData and DocData.

## Scope of this epic

Phase 1 of the team-scope design: introduce the **TeamData** tab, the **DocData** tab, the
ActionSheet **Team Scope** column, and folder-walk auto-assignment on sync — with the existing
regression suite green against the updated schema. No Web App contract change; no deployer
identity change; no per-team sheets.

## Schema contract

### TeamData tab (master GActionSheet) — admin-managed, not written by sync

| Column | Purpose |
|--------|---------|
| Team Name | Human-readable team name (e.g. `Board`, `Membership`) |
| Folder Id | Drive folder ID for this team; **this value is the Team ID** |
| Contact | Team contact for coordination/notifications |

Multiple rows may share a Team Name (a team may own several folders). Auto-assignment matches on
Folder Id.

### DocData tab (master GActionSheet) — per-document sync state

| Column | Purpose |
|--------|---------|
| DocID | Stable document ID (key) |
| Doc Name | Current document name |
| Doc Modified | Document modified timestamp (DocWins source-of-truth check) |
| Doc Updated | Last time the DocData row was written by sync |
| SyncStatus | Sync control flag (`UpdateDoc` → push team to document on next sync) |
| Team | Team ID assigned to the document (matches TeamData.Folder Id) |
| Action Count | Total actions for the document |
| Resolved Count | Total actions resolved per the **shared `isResolved()` authority** |

### ActionSheet — one new column

| Column | Purpose |
|--------|---------|
| Team Scope | Team label resolved from the document's `teamScope` property at sync time |

Rows written before this column existed carry blank; not backfilled automatically.

## Behaviour (Phase 1)

**Auto-assignment (on sync, when `teamScope` unset on the document):**
1. Get the document's parent folder via `DriveApp`.
2. Walk ancestors from current parent up to root/drive.
3. For each folder ID in order, look for an exact match in `TeamData.Folder Id`.
4. First match → set document `teamScope` to that Folder Id (Team ID).
5. No match after root → leave `teamScope` blank.

**DocWins precedence (Phase 2 boundary, contracted now):**
- If the document was modified since last sync, DocData is updated from document state.
- `Action Count` = total actions; `Resolved Count` via the shared `isResolved()` authority — **the
  resolved status set is NOT redefined here.**
- If `DocData.SyncStatus == 'UpdateDoc'`: write `DocData.Team` to the document `teamScope`, then
  clear `SyncStatus`.

**Security rule (all phases):** any read filtered by document or team ID must first verify the
active user can access the team's `Folder Id` (`DriveApp.getFolderById(teamId)` succeeds); on
failure return no rows + an error.

## Slice instance (what `5r4l.2` builds)

A **thin** concrete instance for human review — *not* the production write-path:
- Sample TeamData tab with ~2 teams (e.g. Board, Membership), one with two folders.
- Sample DocData tab with ~3 rows covering: matched team, blank team (no ancestor match),
  and a `SyncStatus=UpdateDoc` row.

## Smoke spec (durable invariants ONLY)

1. **Round-trip:** a DocData row written then read back is identical across all columns.
2. **Single resolved authority:** `Resolved Count` is produced by the shared `isResolved()`
   helper — assert it equals the helper's count over the row's actions; assert no second
   definition of the resolved status set exists in the slice.

**Deliberately NOT asserted at slice** (volatile surface, frozen at the gate): exact column set
and order, header strings, full auto-assignment across deep ancestries, the UpdateDoc write-back
matrix, security-denial paths. These belong to the harden phase.

## Open seam (ADR-0013 register)

- Keep `teamScope` usable as the **routing key** for future Phase-3 per-team physical sheets —
  harden tests should assert teamScope-as-routing-key invariance, not single-master-sheet
  specifics. (One-liner + test parameter; not built now.)

## Exit (freeze gate `5r4l.3`)

On approval: schema ADR Proposed→Accepted; create harden twin-tickets ([INF] scaffolding,
[IMP] read/write paths, [TST] regression-green, [FIX] regressions) test-first from the frozen AC;
graduate durable schema text to docs/DESIGN.md + docs/OPERATIONS.md; delete this staging file.
