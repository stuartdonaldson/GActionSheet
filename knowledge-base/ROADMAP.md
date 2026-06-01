---
framework-version: "2.3.0"
tier: standard
---
# ROADMAP — GActionSheet

## Funnel
Ideas not yet evaluated. One-liners only. To advance: evaluate at planning review; add lean business case to §Review.

- Assignee token normalization — canonicalize person tiles and bare emails to `Display Name <email>` on rewrite (deferred per requirements §7.10)
- Assignee reminder — menu/card-triggered from any document; scope is all open actions in the GActionSheet for the team identified by the active document's `ActionTeam` property; "open" is defined by a shared `isResolved()` function that returns true for Closed, Done, and Rejected (single source of truth for all resolution checks); card (CardService initially; HtmlService upgrade deferred) shows each assignee with their open-action count; user selects one, many, or all; confirmation step before send; email sent as active user via `GmailApp` with per-action text, status, and source document link; email body rendered from an HTML template using `HtmlService.createTemplateFromFile()` per the pattern in bead **F3Go30-i1m** (renderer + builder + XSS escaping; `GmailApp` sends as active user); requires assignee normalization (§7.10) as prerequisite
- Overdue indicator — mark actions whose created date is past a configurable threshold
- Status preset view — sheet view hiding Closed actions for daily triage
- Document health indicator — warn when a document in scope is missing `=== Tracked Actions ===`
- Bulk re-sync — on-demand full scan ignoring the 7-day discovery window (for initial migration of older documents)

## Review
Initiatives with a lean business case under value/risk evaluation.

*(none — v1 execution is active in beads)*

---

## Execution

v1 work is managed in beads. Run `bd ready` for actionable items.

### Delivering a future feature (v2+)

When an initiative exits §Review and is selected for delivery, create a staging document in
`knowledge-base/staging/`, decompose it into spikes, then pour the feature-delivery molecule:

```bash
bd cook /mnt/c/dev/DevStandard/dot-beads/formulas/mol-feature-delivery.formula.yaml \
  --var feature="<feature name>" \
  --var use_case_id="UC-N" \
  --var target_docs="docs/CONTEXT.md, docs/DESIGN.md"
```

The resulting molecule appears in `bd ready` step by step as dependencies resolve.
Human gate issues pause execution until closed with `bd gate resolve <id>`.
Verify the full DAG with `bd graph <epic-id> --compact`.

---

## Future design: logical team scope with master registry

> Updated 2026-05-31. This is an **unimplemented proposal**, not as-built behaviour.
> Today every document syncs to the single container-bound ActionSheet (the master sheet).
> Related: the multi-tenant chip URL (`…/action/{sheetId}/{globalId}`) is also future work.
> Open bead GTaskSheet-knup tracks a prerequisite documentation fix (identity terminology
> in docs/ must be updated to match the current AI-N / globalId model before this design can
> be decomposed into delivery issues).

### Motivation

Action items in GActionSheet are predominantly associated with meeting minutes and are
naturally scoped to teams — the Board of Directors, the Membership team, and so on each
own a distinct body of documents. A single shared ActionSheet becomes a cross-team
bottleneck for filtering and reporting. The goal is to tag every document with a logical
team scope so users can filter and report by team from the master sheet, without
provisioning per-team spreadsheets or changing the Web App contract.

If data volume or access-visibility requirements later warrant physical separation into
team-owned sheets, the logical `teamScope` property already in place on every document and
row becomes the routing key for that migration. That separation is deferred until there is
a demonstrated need.

### Architecture overview

```
GActionSheet (master, container-bound)
│  — single data store; Team Scope column on every action row
│  — Team Registry tab: Team Label → Folder ID(s)
│  — no per-team sheets created or managed
│
Documents carry:  teamScope = "Board" | "Membership" | ...
                  (assigned automatically on first sync via folder hierarchy)
                  (overridable manually via Settings card)
```

No folder-local tracker spreadsheets are created. The deployer identity model and Web App
contract are unchanged in all phases below.

### Phased delivery

**Phase 1 — Team Registry and auto-assignment on sync**

Add a **Team Registry** tab to the master GActionSheet. Each row maps a Team Label to one
or more Drive Folder IDs that belong to that team. Add a `Team Scope` column to the
existing ActionSheet.

On every sync, if the document does not already have a `teamScope` document property,
the add-on walks the document's Drive folder hierarchy and compares each ancestor folder
ID against the Team Registry. The first match assigns `teamScope` to the document property
and populates `Team Scope` on written rows. No user interaction is required.

This phase requires no change to the Web App contract or the deployer identity model.

**Phase 2 — Settings card: team scope visibility and manual override**

A Settings card section on the existing Workspace Add-on homepage card lets users inspect
and change the team scope assigned to the active document.

**Phase 3 (future, if needed) — Physical partitioning into team-owned sheets**

If reporting performance or access-visibility requirements demand it, introduce per-team
tracker spreadsheets. The existing `teamScope` document property and ActionSheet column
become the routing key with no client behaviour change. Deferred until there is a
demonstrated need.

---

### Auto-assignment algorithm (Phase 1)

On sync, when `teamScope` is not yet set on the document:

1. Retrieve the document's parent folder via `DriveApp`.
2. Walk up the folder hierarchy; at each level check the Team Registry tab for a matching
   Folder ID.
3. First match → write that Team Label to the `teamScope` document property; populate
   `Team Scope` on all rows written in this sync.
4. No match after reaching the root → leave `teamScope` unset; write rows with blank
   `Team Scope`; re-evaluate on the next sync (the registry may have been updated).

Once `teamScope` is set on the document property it is not overwritten by auto-assignment.
Only a manual override via the Settings card changes an existing assignment.

---

### Team Registry tab (master GActionSheet)

A dedicated worksheet tab on the master GActionSheet defining the team-to-folder mapping.
Managed by an administrator; not written by the add-on during normal sync.

| Column | Purpose |
|--------|---------|
| Team Label | Human-readable team name (e.g. `Board`, `Membership`) |
| Folder ID | Drive folder ID associated with this team (one row per folder) |
| Notes | Optional free-text context |

Multiple rows with the same Team Label are allowed — a team may own more than one folder.
The auto-assignment algorithm matches on Folder ID and reads the Team Label from that row.

---

### ActionSheet column addition (Phase 1)

One new column on the existing ActionSheet:

| Column | Purpose |
|--------|---------|
| Team Scope | Team label resolved from the document's `teamScope` property at sync time |

This is the only schema change required for Phase 1. Existing rows written before this
column exists carry a blank value; they are not backfilled automatically.

---

### Settings surface (Phase 2)

> New capability proposed here — not yet in CONTEXT.md or docs/DESIGN.md. When this phase
> is promoted to delivery, both documents require updates before implementation begins.

**Context (proposed)**

The Settings surface gives document authors visibility into and control over the team scope
assigned to their document, without requiring access to the Apps Script editor or the
master ActionSheet.

Actors: Document author, Administrator
Preconditions: Add-on is installed; user has the doc open.

Core capabilities the Settings surface must expose:
- The current `teamScope` for the active document and how it was assigned (auto vs manual)
- A dropdown to manually assign or change the team scope (populated from the Team Registry)
- Confirmation step before overwriting an existing manual assignment

**Design (proposed)**

The Settings surface is a new card section on the existing Workspace Add-on homepage card
(context ①, runs as the active user via CardService). It does not require a new menu item
or a separate HTML sidebar.

Key design constraints:
- Reading and writing document custom properties is available in context ① today —
  `PropertiesService.getDocumentProperties()` works without the Docs REST API.
- Reading the Team Registry requires a `doPost` call (context ③) to the deployer, since
  the master spreadsheet is owned by the deployer account.
- The Settings card section may be hidden when `teamScope` is unset and the document's
  parent folder has no match in the Team Registry (clean default state for unscoped orgs).
- A manual override writes `teamScope` to the document property and records the override
  source so auto-assignment does not overwrite it on the next sync.

---

### Failure modes

These extend the existing failure modes in [docs/OPERATIONS.md](../docs/OPERATIONS.md):

| Failure | Symptom | Recovery |
|---------|---------|---------|
| No parent folder found for document (orphan doc) | `teamScope` not assigned; `Team Scope` column left blank | Expected; no recovery needed unless team tracking is required |
| Multiple parent folders for document | Walk uses the first folder returned by Drive API; logs a warning | Set `teamScope` manually via Settings card to override |
| Document folder has no ancestor in the Team Registry | `teamScope` not assigned; re-evaluated on next sync | Add the folder or an ancestor to the Team Registry |
| Team Registry tab missing or malformed | Auto-assignment skipped; sync completes without team scope | Restore or recreate the Team Registry tab |

---

### Framing

- **Logical identity:** document carries `teamScope` (e.g. `Board`) — not a spreadsheet ID
- **Auto-assignment:** folder hierarchy walk against the Team Registry on first sync
- **Manual override:** Settings card; persists a source flag so auto-assignment does not clobber it
- **Reporting surface:** `Team Scope` column on existing ActionSheet rows
- **Storage:** single master GActionSheet throughout; physical partitioning is a future option

Main rule: once `teamScope` has been manually set, auto-assignment does not overwrite it.
Auto-assigned values may be updated if the Team Registry changes and the document property
has not been manually pinned — this is intentional to keep folder-hierarchy moves consistent.

When Phase 1 is promoted to delivery, a new ADR is required covering the team-scope
assignment model (auto-assignment algorithm, manual override precedence, Team Registry
as the authoritative source). Do not conflate with the action-identity ADR (ADR-0008).
