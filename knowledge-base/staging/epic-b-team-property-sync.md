# Staging — EPIC-B: Team Scope Document Property and Bidirectional Sync

> **Transient working contract** (framework staging). Deleted when EPIC-B completes and
> durable content has graduated to `docs/DESIGN.md` and `docs/OPERATIONS.md`.
> Builds on: ADR-0014 (Accepted) and the schema baseline from EPIC-A.
> Review fidelity: **Spec** (ADR-0013) — design error visible from contract prose; no Slice phase.

## Scope

Phase 2 of the team-scope design: make `teamScope` a live Google Docs custom document
property, synchronise it bidirectionally with `DocData.Team Id`, apply folder-walk
auto-assignment on first sync, and enforce the team-scoped security gate on all filtered reads.

No Web App contract change. No deployer identity change. The schema (TeamData/DocData/File Id)
is already in place from EPIC-A.

## Property lifecycle

| State | Trigger | Action |
|-------|---------|--------|
| Unset (first sync) | `PropertiesService` returns no `teamScope` | Run folder-walk; set to matched Folder Id if found |
| Set, no override | `DocData.SyncStatus != 'UpdateDoc'` | `DocData.Team Id` := `document.teamScope` (DocWins) |
| Override pending | `DocData.SyncStatus == 'UpdateDoc'` | `document.teamScope` := `DocData.Team Id`; clear `SyncStatus` |
| No folder match | Walk reaches root with no TeamData hit | Leave blank; log warning; re-evaluate next sync |

## Sync contract (DocWins precedence)

- If the document was modified since last sync (`Doc Modified` changed): update `DocData`
  from document state. `DocData.Team Id` := `document.teamScope`.
- If `DocData.SyncStatus == 'UpdateDoc'`: write `DocData.Team Id` to document property,
  then clear `SyncStatus`. **This is the only path where DocData wins over the document.**

DocWins is not redefined here — this epic applies the rule already stated in ADR-0014.

## Folder-walk auto-assignment

Runs only when `teamScope` is unset on the document.

1. `DriveApp.getFileById(docId).getParents()` to get the current parent folder(s).
2. Walk ancestors from current parent up to root/drive.
3. For each folder ID, exact-match against `TeamData.Folder Id`.
4. First match → set `document.teamScope` to that Folder Id (Team ID).
5. No match after root → `teamScope` remains blank.

Multiple parents: walk uses the first folder returned by Drive API; log a warning.

## Security gate

Before returning any rows filtered by document ID or Team Id, call
`DriveApp.getFolderById(teamId)` as the active user. On failure (no access), return no rows
and surface an error. Applied to any team-scoped read in this epic and all future epics.

## Entry-point signatures (pre-code contract for twin-tickets)

| Entry point | GAS function | Completion log tag |
|-------------|-------------|-------------------|
| Sync (menu / timed trigger) | `syncDocument(docId)` (existing — extended) | `sync.teamScope.resolved` |
| DocData override write-back | internal to `syncDocument` path | `sync.teamScope.overridden` |
| Security gate | `assertTeamAccess(teamId)` (new) | none — throws `TeamAccessDeniedError` on failure |

## Output schema the test will assert against

- After sync (auto-assign path): `document.teamScope == DocData[fileId].Team Id`.
- After sync (UpdateDoc path): `document.teamScope == new Team Id` AND `DocData.SyncStatus` is blank.
- Security-deny path: call returns no rows; error is surfaced to caller; no data leaks.
- Idempotency: a second sync with no changes produces no further writes.

## Open seams (ADR-0013 register)

- `teamScope` must remain usable as a routing key for future Phase-3 per-team sheets —
  harden tests should assert the value identity (Folder Id string), not single-master-sheet
  assumptions.
- `assertTeamAccess` signature must accommodate a caller-supplied user identity for future
  service-account impersonation without restructuring. Expressed as a one-liner + test parameter
  in the hardening `[TST]` bead; not built now.

## Bead decomposition

### IMP track

| Bead | Model | Depends on |
|------|-------|-----------|
| `[INF] Design: Team Scope sync logic (DocWins, folder-walk, security gate)` | opus | — |
| `[IMP] Add Team Scope property read/write and folder-walk auto-assignment` | sonnet | INF design |
| `[IMP] Sync Team Scope with DocData.Team Id (DocWins + UpdateDoc write-back)` | sonnet | INF design |
| `[IMP] Enforce team-scoped security gate on all filtered reads` | sonnet | INF design |

The `[INF] Design` bead produces: entry-point signatures, state-machine, edge-case
enumeration, and data-access call sequence. This becomes the sole design input for the three
`[IMP]` beads.

### TST track

| Bead | Model | Depends on |
|------|-------|-----------|
| `[INF] Design: test strategy and scenario matrix for Team Scope sync` | opus | — |
| `[TST] Entry-point coverage for Team Scope sync and security guard` | sonnet | TST design + all [IMP] beads |
| `[FIX] Resolve Team Scope mismatches and edge-case defects` | sonnet | [TST] |

The `[INF] Design` bead produces: scenario list (happy-path, no-match, override,
security-deny, idempotency), entry-point call-site table, fixture requirements. This becomes
the sole design input for the `[TST]` bead. No shared context with the IMP track.

## Failure modes (to be added to OPERATIONS.md on exit)

| Failure | Symptom | Recovery |
|---------|---------|---------|
| Drive quota exceeded during folder walk | Walk aborted; `teamScope` stays blank | Retry on next sync |
| `getFolderById` throws for valid team | Security gate blocks user | Verify folder sharing; check Drive permissions |
| `SyncStatus=UpdateDoc` with blank/invalid Team Id | Write-back skipped; status retained | Correct `DocData.Team Id`, then sync again |

## Exit (when all beads green)

1. Graduate failure modes table above to `docs/OPERATIONS.md §Failure Modes`.
2. Graduate `teamScope` property lifecycle and security gate placement to `docs/DESIGN.md §Team Scope Schema`.
3. Delete this staging file.
4. Close the EPIC-B epic bead.
5. Add funnel deltas (if any) to `ROADMAP.md §Funnel`.
