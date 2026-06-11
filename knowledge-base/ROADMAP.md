---
framework-version: "2.3.0"
tier: standard
---
# ROADMAP — GActionSheet

## Table Of Contents
- [ROADMAP — GActionSheet](#roadmap--gactionsheet)
- [Funnel](#funnel)
- [Review](#review)
- [Planning](#planning)
- [Execution](#execution)
- [Future design: team scope with TeamData and DocData](#future-design-team-scope-with-teamdata-and-docdata)
- [Future design: sidebar tabs — Import and Notify](#future-design-sidebar-tabs--import-and-notify)

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

## Planning
Planned epics prepared for decomposition into beads. No beads are created yet.

### Model-recommendation legend

Each draft bead below carries a recommended model tag. When the bead is created, apply it
as the existing bd label (`model:opus` / `model:sonnet` / `model:haiku` — already in use on
~12 issues; see `.beads/issues.jsonl`). The tag is a default, not a lock: escalate a level
if the work proves harder than the contract implied; downgrade if it is more mechanical.

| Tag | Use for |
|-----|---------|
| `model:opus` | Design/ADR authoring, security-sensitive logic, AI-N identity handling, DocWins precedence, cross-cutting test-journey design, debugging non-obvious regressions |
| `model:sonnet` | Implementation and test authoring against a settled contract — sync paths, CRUD, fixture suites, UI shells, binding assertions to a defined journey |
| `model:haiku` | Mechanical/scaffolding work with a clear template — flag clears, boilerplate helpers, simple parity smoke checks |

### Epic structure (each epic below)

- **Goal** — one sentence.
- **Depends on** — upstream epic(s) that must land first (sequencing is enforced here, not just in §Sequencing).
- **Supporting files** — staging contract + docs to update before the first bead starts.
- **Beads to create** — twin-ticketed (`[IMP]`+`[TST]` per AC), each tagged with a recommended model.
- **Acceptance test scenario** — the AC the twin-ticket pair must drive to green.

Twin-ticket rule (CLAUDE.md §Testing): every `[IMP]` has a paired `[TST]` created at the
same time; neither merges until both are green; the pre-code contract (entry-point signature,
completion log tag, output schema) is the only shared artifact between them.

### EPIC-A — Adopt TeamData/DocData schema and keep regression green — DELIVERED

Closed as `GTaskSheet-5r4l`. TeamData/DocData schema, `File Id` column, and ADR-0014 are
as-built. See `docs/DESIGN.md` §Team Scope Schema (ADR-0014).

### EPIC-B — Add Team Scope document property and bidirectional sync to sheet — DELIVERED

Closed as `GTaskSheet-me6w` (children `.1`-`.7`). `teamScope` document property,
folder-walk auto-assignment, DocWins sync, `assertTeamAccess` security gate, and
`UpdateDoc` write-back are all as-built and covered by `tests/test_team_scope.py`
(scenarios S0-S8). These primitives are the reuse foundation for EPIC-D/E below —
do not reimplement.

### EPIC-C — Reassign team from spreadsheet via DocData and sync — DELIVERED VIA EPIC-B

The full EPIC-C acceptance scenario (DocData row set to `SyncStatus='UpdateDoc'` with a
new Team Id → sync applies the change, clears `SyncStatus`, idempotent on re-sync) was
implemented as part of `GTaskSheet-me6w.4` (DocWins + UpdateDoc write-back,
`src/SyncManager.js` `_syncTeamScopeForDoc`) and is covered by `tests/test_team_scope.py`
S3 (UpdateDoc override) and S4 (idempotency). No new `[IMP]`/`[TST]` twin is needed.

Remaining gap: an operator-facing runbook in `docs/OPERATIONS.md` for this workflow.
Tracked as `GTaskSheet-fk98` (`[INF]`, `model:haiku`).

### EPIC-D-PRE — Tabbed-shell architecture slice + J-ACCESS-FILTER — `GTaskSheet-uz7h`

EPIC-D/E's "tabbed sidebar" (below) was specified before the `html-sidebar-card-pivot`
decision (2026-05-27, `GTaskSheet-cw5`) which committed the project to a CardService-only
UI (no HtmlService sidebar). This prerequisite epic resolves that conflict and authors the
shared `J-ACCESS-FILTER` journey, with a regression-proof-out gate before any EPIC-D/E
`[IMP]` work, since the navigation refactor touches `buildHomepageCard()` — the production
entry point for every user.

Review fidelity: **Slice** (ADR-0013).
Open seam: tab model must remain extensible for a Settings tab (Phase 2) without
re-architecting.

Depends on: EPIC-B (closed).

Beads (all created):
- `[INF] Design: CardService tab-navigation model for DocStatus/Import/Notify` —
  `model:opus` — `GTaskSheet-fi0w`
- `[INF] Design: J-ACCESS-FILTER shared journey + two-account fixture matrix` —
  `model:opus` — `GTaskSheet-z1fr`
- `[IMP] Slice: render placeholder Import/Notify tab cards via shared navigation shell` —
  `model:sonnet` — `GTaskSheet-0r0s`
- `[TST] Slice smoke: tab navigation round-trip + DocStatus regression check` —
  `model:sonnet` — `GTaskSheet-gdll` (re-run at EPIC-D and EPIC-E gates)
- `[GATE] Freeze EPIC-D-PRE slice — accept nav design, register open seams` —
  `GTaskSheet-5fha`

### EPIC-D — Add Import tab and action forwarding workflow — `GTaskSheet-yb2w`

Goal: add Import capability to pull open team-scoped actions into the current document and
forward source actions safely.

Review fidelity: **Slice** (ADR-0013). Depends on: EPIC-D-PRE gate (`GTaskSheet-5fha`).

Access rule: Import must only list and import actions whose source documents are readable
by the current user (J-ACCESS-FILTER).

Reuse (do not reimplement): `DocData`/`File Id` join (EPIC-A/B), `assertTeamAccess`
(EPIC-B), `isResolved()` (extend for `Forwarded`), `_remarkRowDirty` for dirty-flagging,
and the Token Manager / `_insertActionChip` AI-N insertion path in
`src/EditorAddonCard.js`.

Beads (all created):
- `[IMP] Team-scoped Import list grouped by source document` — `model:sonnet` — `GTaskSheet-eore`
- `[IMP] Import selected actions at cursor with new AI-N numbering` — `model:opus` — `GTaskSheet-fgh4`
- `[IMP] Forward source actions (Status=Forwarded, suffix, dirty flag)` — `model:sonnet` — `GTaskSheet-st24`
- `[TST] Bind Import assertions to J-ACCESS-FILTER (P1-P4)` — `model:sonnet` — `GTaskSheet-1dxz`
- `[TST] Functional coverage: import flow, forwarded status, post-import sync` — `model:sonnet` — `GTaskSheet-4gsx`
- `[FIX] Import edge cases (duplicate forwarding, numbering drift, dirty-flag miss)` — `model:sonnet` (escalate to `model:opus` for numbering-drift) — `GTaskSheet-wdh0`
- `[GATE] Final sign-off for EPIC-D` (re-runs EPIC-D-PRE DocStatus regression smoke) — `GTaskSheet-fnvq`

Acceptance test scenario:
- Given two open team-scoped actions selected in Import from documents readable by the current user, when Import is executed at the current paragraph, then both actions are inserted as new floating actions with new AI-N values, source rows are set to `Forwarded` with `[Forward:<DocName> AI-N]` suffixes, rows are marked dirty, and a post-import sync updates the document action table; actions from unreadable source documents are never listed.

### EPIC-E — Add Notify tab and assignee reminder email flow — `GTaskSheet-gc43`

Goal: add Notify capability to send reminders to selected assignees with unresolved
team-scoped actions.

Review fidelity: **Slice** (ADR-0013). Depends on: EPIC-D (reuses its tabbed shell and
J-ACCESS-FILTER bindings, not rebuilt).
Open seam: email-template contract must be reusable for the Assignee Reminder funnel entry
when it is promoted.

Access rule: Notify must only aggregate and present actions from source documents readable
by the current user.

Beads (all created):
- `[INF] Align email-template approach with Funnel "Assignee reminder" entry` — `model:opus` — `GTaskSheet-tv54`
- `[IMP] Notify tab: assignee aggregation with unresolved counts` — `model:sonnet` — `GTaskSheet-xiv8`
- `[IMP] Send reminder emails (HtmlService template + GmailApp, XSS escaping)` — `model:opus` — `GTaskSheet-f3v9`
- `[IMP] Reuse team-scope security gate + access filter on Notify reads` — `model:sonnet` — `GTaskSheet-ajns`
- `[TST] Bind Notify assertions to J-ACCESS-FILTER (P1-P4)` — `model:sonnet` — `GTaskSheet-ay5w`
- `[TST] Cross-feature parity assertion (Import document set == Notify document set)` — `model:haiku` — `GTaskSheet-7fng`
- `[TST] Template rendering and escaping checks for notification emails` — `model:sonnet` — `GTaskSheet-twwo`
- `[FIX] Notification count drift and send failures` — `model:sonnet` — `GTaskSheet-1xpj`
- `[GATE] Final sign-off for EPIC-E` (re-runs EPIC-D-PRE DocStatus regression smoke) — `GTaskSheet-s3ga`

Acceptance test scenario:
- Given team-scoped unresolved actions across multiple assignees from documents readable by the current user, when two assignees are selected in Notify and send is triggered, then only those assignees receive templated reminder emails with correct unresolved-action lists and counts, and actions from unreadable source documents are excluded from counts and emails.

### Shared test asset requirement (EPIC-D and EPIC-E)

Access-control validation for Import/Notify requires at least two authenticated test accounts:

- Primary account: has read access to the full baseline test set.
- Secondary restricted account: the additional auth account used in prior Probe tests; has read access to only a subset of source team documents.

`GTaskSheet-z1fr` ([INF] Design: J-ACCESS-FILTER) is responsible for documenting this in
`docs/OPERATIONS.md` (account roles, minimum permissions, setup steps) before EPIC-D/E
`[IMP]` beads start.

### J-ACCESS-FILTER shared journey (P1-P4)

Single source of truth for visibility/authorization across Import and Notify, authored by
`GTaskSheet-z1fr` and bound by `GTaskSheet-1dxz` (Import) / `GTaskSheet-ay5w` (Notify).
Full spec (scenario list, two-account fixture matrix, entry-point call-site table, shared
`tests/helpers/access_filter.py` assertion contract): `knowledge-base/staging/j-access-filter-journey.md`.

1. `P1-PrimaryFullAccess`: primary account sees all eligible source documents.
2. `P2-SecondaryRestrictedAccess`: restricted account sees only permitted documents.
3. `P3-NoTeamFolderAccess`: read denied path returns no rows + explicit error.
4. `P4-FeatureParity`: same visibility set drives both Import list and Notify aggregation
   (`GTaskSheet-7fng`).

Packaging guidance:
- Integration package includes full journey (`P1`..`P4`) plus feature-specific assertions.
- Regression package includes fast-path `P2` + `P3` + parity smoke (`P4`) to guard access drift.
- Weekly/full regression runs full `P1`..`P4` for both Import and Notify.

Sequencing:
1. ~~EPIC-A~~ — done
2. ~~EPIC-B~~ — done (also delivers EPIC-C's acceptance scenario)
3. EPIC-C closure doc (`GTaskSheet-fk98`)
4. EPIC-D-PRE (`GTaskSheet-uz7h`) — nav-architecture design + regression-proof-out gate
5. EPIC-D (`GTaskSheet-yb2w`) — Import tab and forwarding workflow
6. EPIC-E (`GTaskSheet-gc43`) — Notify tab and reminder flow

---

## Execution

v1 work is managed in beads. Run `bd ready` for actionable items. Slice gates (EPIC-A, J-ACCESS-FILTER, EPIC-D, EPIC-E) each produce a verdict and funnel deltas added to §Funnel; see ADR-0013.

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

## Future design: team scope with TeamData and DocData

> Updated 2026-06-04. This is an **unimplemented proposal**, not as-built behaviour.
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
│  — TeamData tab: Team Id, Folder Id, Contact
│  — DocData tab: per-document sync metadata and counters
│  — no per-team sheets created or managed
│
Documents carry:  teamScope = "<team-id>"
                  (assigned automatically on first sync via folder hierarchy)
                  (overridable from DocData via SyncStatus='UpdateDoc')
```

`teamScope` stores **Team Id** — the stable team identifier from the matching TeamData row
(e.g. `Board`, `Membership`). Auto-assignment finds the matching row via `Folder Id` and
stores that row's `Team Id`. Team display names are resolved by TeamData lookup on `Team Id`.

No folder-local tracker spreadsheets are created. The deployer identity model and Web App
contract are unchanged in all phases below.

### Phased delivery

**Phase 1 — TeamData, DocData, and auto-assignment on sync**

Add a **TeamData** tab to the master GActionSheet with `Team Name`, `Folder Id`, and
`Contact`. Add a **DocData** tab with `DocID`, `Doc Name`, `Doc Modified`, `Doc Updated`,
`SyncStatus`, `Team`, `Action Count`, and `Resolved Count`. Add a `Team Scope` document
custom property on each tracked document.

On every sync, if the document does not already have a `teamScope` document custom property,
the add-on walks the document's Drive folder hierarchy (current parent first, then each
ancestor up to root/drive) and compares each folder ID against `TeamData.Folder Id`.
First match identifies the team; `teamScope` is set to the **`Team Id`** value from that
TeamData row. When team name is needed, resolve it via TeamData lookup by `Team Id`.
If no match exists, `teamScope` remains blank.

This phase requires no change to the Web App contract or the deployer identity model.

**Phase 2 — DocWins synchronization and DocData-driven override**

`DocData` is synchronized using a DocWins strategy:
- If the document has been modified since last sync, update `DocData` from document state.
- Maintain `DocData.Action Count` as total actions for the document.
- Maintain `DocData.Resolved Count` using the shared resolved-status helper already used by
  the codebase (do not redefine resolved status values in this plan).

On sync, if `DocData.SyncStatus == 'UpdateDoc'`, update document team information from
`DocData.TeamId`, then clear `SyncStatus`. This supports reassigning a document to a new team
from the master GActionSheet.

**Phase 3 (future, if needed) — Physical partitioning into team-owned sheets**

If reporting performance or access-visibility requirements demand it, introduce per-team
tracker spreadsheets. The existing `teamScope` document property and ActionSheet column
become the routing key with no client behaviour change. Deferred until there is a
demonstrated need.

---

### Auto-assignment algorithm (Phase 1)

On sync, when `teamScope` is not yet set on the document:

1. Retrieve the document's parent folder via `DriveApp`.
2. Walk up the folder hierarchy from current parent to root/drive.
3. For each folder ID in order, look for an exact match in `TeamData.Folder Id`.
4. First match → set `teamScope` on the document to the **`Team Id`** value from that
  TeamData row.
5. No match after reaching root/drive → leave `teamScope` blank.

If `DocData.SyncStatus == 'UpdateDoc'`, the team assignment in `DocData.TeamId` is written
to the document as `teamScope` and `SyncStatus` is cleared.

---

### TeamData tab (master GActionSheet)

A dedicated worksheet tab on the master GActionSheet defining the team-to-folder mapping.
Managed by an administrator; not written by the add-on during normal sync.

| Column | Purpose |
|--------|---------|
| Team Id | Stable team identifier used as the routing key (e.g. `Board`, `Membership`); stored as `teamScope` on the document |
| Folder Id | Drive folder ID associated with this team; the folder-walk match key |
| Contact | Team contact for coordination/notifications |

Multiple rows may share a Team Id — a team may own more than one folder.
The auto-assignment algorithm matches on `Folder Id` and stores the matched row's `Team Id`
as the document's `teamScope`.

---

### DocData tab (master GActionSheet)

Per-document synchronization state, team assignment mirror, and aggregate counters.

| Column | Purpose |
|--------|---------|
| DocID | Stable document ID |
| Doc Name | Current document name |
| Doc Modified | Document modified timestamp (source-of-truth check) |
| Doc Updated | Last time DocData row was written by sync |
| SyncStatus | Sync control flag (`UpdateDoc` triggers document update on next sync) |
| Team | Team ID assigned to the document (matches TeamData `Folder Id`) |
| Action Count | Total actions for the document |
| Resolved Count | Total actions considered resolved by shared helper |

DocData follows DocWins for modified metadata and counters when the source document has
changed since last sync.

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
- The current `teamScope` for the active document and its mapped `DocData.TeamId`
- A way to request reassignment by setting `DocData.TeamId` and `DocData.SyncStatus='UpdateDoc'`
- Confirmation step before requesting reassignment

**Design (proposed)**

The Settings surface is a new card section on the existing Workspace Add-on homepage card
(context ①, runs as the active user via CardService). It does not require a new menu item
or a separate HTML sidebar.

Key design constraints:
- Reading and writing document custom properties is available in context ① today —
  `PropertiesService.getDocumentProperties()` works without the Docs REST API.
- Reading TeamData requires a `doPost` call (context ③) to the deployer, since
  the master spreadsheet is owned by the deployer account.
- The Settings card section may be hidden when `teamScope` is unset and the document's
  parent folder has no match in TeamData (clean default state for unscoped orgs).
- Reassignment is mediated through DocData (`Team`, `SyncStatus='UpdateDoc'`) and applied
  on the next sync.

---

### Acceptance checks (test cycle)

- After sync, `Doc.teamScope == DocData[docid].TeamId`.
- Team name rendering uses TeamData lookup by Team ID (`Doc.teamScope` / `DocData.TeamId`).
- After sync, `Doc.Modified == DocData[docid].Doc Modified`.
- If team lookup fails across the full folder ancestry, `Doc.teamScope` remains blank.
- If `DocData.SyncStatus == 'UpdateDoc'`, sync updates document team from DocData and clears
  `SyncStatus`.

---

### Failure modes

These extend the existing failure modes in [docs/OPERATIONS.md](../docs/OPERATIONS.md):

| Failure | Symptom | Recovery |
|---------|---------|---------|
| No parent folder found for document (orphan doc) | `teamScope` not assigned; `Team Scope` column left blank | Expected; no recovery needed unless team tracking is required |
| Multiple parent folders for document | Walk uses the first folder returned by Drive API; logs a warning | Set `teamScope` manually via Settings card to override |
| Document folder has no ancestor in TeamData | `teamScope` not assigned; re-evaluated on next sync | Add the folder or an ancestor to TeamData |
| TeamData tab missing or malformed | Auto-assignment skipped; sync completes without team scope | Restore or recreate the TeamData tab |
| Team ID exists in document/DocData but no TeamData row matches | Team name cannot be resolved for UI/reporting | Add or restore TeamData row for that Team ID |
| DocData row missing for known document | Sync cannot reconcile DocWins fields | Recreate row keyed by `DocID` on next sync |
| `SyncStatus='UpdateDoc'` with blank/invalid Team | Team write-back skipped and status retained | Correct `DocData.TeamId`, then sync again |

---

### Framing

- **Logical identity:** document carries `teamScope` as `Team Id` (from matching TeamData row)
- **Auto-assignment:** folder hierarchy walk against TeamData `Folder Id`; stores `Team Id` on match
- **Reassignment path:** DocData `UpdateDoc` applies team changes back to documents
- **Name resolution:** Team name is derived by TeamData lookup using `Team Id`
- **Reporting surface:** `Team Scope` column on existing ActionSheet rows
- **Storage:** single master GActionSheet throughout; physical partitioning is a future option

Main rule: team resolution is folder-first when `teamScope` is empty; reassignment is explicit
through `DocData.SyncStatus='UpdateDoc'` and then synchronized to the document property.

### Security rule: team-scoped action reads

**Guiding rule (applies to all phases):** whenever actions are read from the GActionSheet
filtered by document ID or team ID, the implementation must perform an access check
before returning results: resolve the `Folder Id` from TeamData using the `Team Id`, then
verify that the current user (active user in context ①) has read access via
`DriveApp.getFolderById(folderId)`. If the check fails, return no results and surface an
appropriate error to the caller; do not surface rows belonging to a team the user cannot access.

When Phase 1 is promoted to delivery, a new ADR is required covering the team-scope
assignment model (auto-assignment algorithm, DocData write-back precedence, TeamData
as the authoritative source). Do not conflate with the action-identity ADR (ADR-0008).

---

## Future design: sidebar tabs — Import and Notify

> Updated 2026-06-04. Unimplemented proposal.
> Depends on the team-scope + TeamData / DocData design above.
> Related funnel entry: Assignee reminder (§Funnel) covers similar email mechanics;
> when both are promoted, align on a shared email-template approach.

### Sidebar tab model

The current sidebar (single-purpose DocStatus view) is refactored into a tabbed sidebar
with three tabs:

| Tab | Purpose |
|-----|---------|
| DocStatus | Existing sync-status functionality (unchanged) |
| Import | Browse and import open team actions into the current document |
| Notify | Email open-action reminders to assignees |

---

### Import tab

**Preconditions:** current document has a non-blank `teamScope`; sidebar is open.

**Behaviour:**

1. Load all actions from the GActionSheet scoped to `Doc.teamScope` (Team ID).
   Apply the team-scoped security check (see §Security rule above) before fetching.
2. Filter to open actions only — use `isResolved()` as the shared resolved check;
   actions with status `Forwarded` are considered resolved and are excluded.
3. Display results grouped by source document name. Each action shows a checkbox.
4. An **Import** button is shown at the bottom of the list.

**Import action (on button press):**

For each selected action:

1. Insert the action as a floating action in the current document at the paragraph
   position of the cursor, assigning new local action numbers (AI-N).
2. In the GActionSheet, update the original action row:
   - Set `Status` to `Forwarded`.
   - Append `[Forward:<CurrentDocName> AI-N]` to the action text.
   - Call `markDirty()` on the row to flag it for sync to the source document on the
     next sync cycle.
3. After all selected actions are imported, trigger a sync of the current document
   to update its action table.

**`markDirty()` function:** must be created or refactored from existing dirty-flagging
logic. Marks a GActionSheet row so the next sync pass writes the updated state back
to the source document.

**`isResolved()` extension:** `Forwarded` must be added as a resolved status in the
shared `isResolved()` function. Do not define the full status set in this plan —
use the canonical implementation as the reference.

---

### Notify tab

**Preconditions:** current document has a non-blank `teamScope`; sidebar is open.

**Behaviour:**

1. Load all actions scoped to `Doc.teamScope`. Apply the team-scoped security check.
2. Aggregate by assignee, counting unresolved actions (`!isResolved()`).
3. Display a list of assignees with their unresolved action count. Each has a checkbox.
4. A **Notify** button sends email reminders to all checked assignees.

**Email send:**

- Email is sent as the active user via `GmailApp`.
- Body is rendered from an HTML template using `HtmlService.createTemplateFromFile()`.
- Template receives: assignee name, list of their open actions (text, status, source
  document link).
- XSS escaping is required on all interpolated values.

> **GAS email-sending practices:** no canonical standard exists yet in this project.
> When this feature is promoted to delivery, define and record the standard (template
> location, escaping contract, `GmailApp` vs `MailApp` choice) before implementation.
> Cross-reference the Assignee reminder Funnel entry — both features must use the
> same standard.

---

### Acceptance checks (Import)

- Imported action appears in the current document at the cursor paragraph, with a
  valid new AI-N assignment.
- Original action row in GActionSheet: `Status == 'Forwarded'` and action text ends
  with `[Forward:<DocName> AI-N]`.
- Original action row is marked dirty.
- `isResolved()` returns `true` for `Status == 'Forwarded'`.
- After import, the current document's action table reflects the imported actions.
- Security check: a user without read access to the team folder receives no actions
  and an appropriate error.

### Acceptance checks (Notify)

- Notify tab shows only assignees with at least one unresolved action.
- Email is sent only to checked assignees; no email is sent to unchecked assignees.
- Email body lists the correct open actions for the assignee.
- Security check: same team-folder access gate as Import.
