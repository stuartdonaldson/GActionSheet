# ADR-0014: Team-Scope Schema and Folder-Walk Assignment Model

Status: Proposed
Date: 2026-06-05

> Proposed during the EPIC-A slice phase (ADR-0013). Accepted at the EPIC-A freeze gate
> (`GTaskSheet-5r4l.3`) once the schema slice validates the model. Working contract:
> `knowledge-base/staging/epic-a-schema-adoption.md`.

## Context

Action items in GActionSheet are predominantly meeting minutes naturally scoped to teams (Board,
Membership, …). Today every document syncs to a single container-bound master ActionSheet, which
becomes a cross-team bottleneck for filtering and reporting. We want to tag each document with a
logical team scope so users can filter/report by team from the master sheet, without provisioning
per-team spreadsheets or changing the Web App contract or deployer identity model.

A schema and an assignment rule are needed. The question is *where team identity lives*, *how a
document acquires it*, and *which side wins on conflict* — and these must be settled before the
read/write paths are hardened, because tests will assert against them.

This decision is distinct from ADR-0008 (AI-N in-text token action identity). Team scope is a
*document/row* attribute, not an action identity.

## Decision

Adopt a single-master-sheet team-scope schema with folder-walk auto-assignment and DocData-mediated
override:

1. **TeamData is the authority for team identity.** A master-sheet TeamData tab maps `Team Name`,
   `Folder Id`, `Contact`. The **`Folder Id` value is the Team ID.** Team display names are resolved
   by TeamData lookup on Team ID. A team may own multiple folders (multiple rows, same Team Name).

2. **A document carries `teamScope` = Team ID** as a document custom property. Auto-assignment, on
   sync when `teamScope` is unset: walk the document's Drive folder ancestry from current parent to
   root; the first folder whose ID matches a `TeamData.Folder Id` sets `teamScope` to that ID; no
   match leaves it blank.

3. **DocData mirrors per-document sync state** (`DocID`, `Doc Name`, `Doc Modified`, `Doc Updated`,
   `SyncStatus`, `Team`, `Action Count`, `Resolved Count`) and follows **DocWins**: when the document
   changed since last sync, DocData is updated from document state. `Resolved Count` is computed by
   the existing shared `isResolved()` authority — this ADR does **not** define the resolved status set.

4. **Reassignment is explicit via DocData.** When `DocData.SyncStatus == 'UpdateDoc'`, sync writes
   `DocData.Team` to the document `teamScope` and clears `SyncStatus`. Document-first otherwise.

5. **Team-scoped reads are access-checked.** Any read filtered by document/team ID first verifies the
   active user can access the team's `Folder Id` (`DriveApp.getFolderById`); on failure, no rows + an
   error. (Becomes load-bearing for the later Import/Notify epics.)

6. **Storage stays a single master sheet.** Physical partitioning into per-team sheets is explicitly
   deferred (Phase 3); `teamScope` is the routing key that would enable it without a client change.

## Consequences

**Positive:**
- Team identity has one authority (TeamData) and one resolution rule (folder-first, then explicit
  DocData override) — no ambiguity for the hardened read/write paths to test against.
- No Web App contract or deployer identity change in Phase 1.
- `teamScope` as routing key preserves the Phase-3 physical-partitioning option without locking it in.

**Negative / tradeoffs:**
- Folder-walk assignment depends on Drive folder hygiene; orphan/multi-parent docs assign blank or
  by first-returned parent (failure modes enumerated in the staging contract / OPERATIONS).
- TeamData is admin-maintained; a missing/malformed tab silently skips assignment.
- DocWins + `UpdateDoc` is a two-way precedence rule — the one place reconciliation bugs can hide;
  flagged for `model:opus` at harden.

**Open question (resolved at Accept):** does the schema slice (`GTaskSheet-5r4l.2`) confirm the
column set and the resolved-count single-authority round-trip before this ADR is Accepted? Pending
the freeze gate per ADR-0013.
