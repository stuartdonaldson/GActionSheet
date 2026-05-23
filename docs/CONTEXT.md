# CONTEXT — GActionSheet

## Introduction & Goals

### Purpose
GActionSheet captures and tracks action items inside Google Docs and aggregates them in a central spreadsheet (the **ActionSheet**) for cross-doc roll-up. Authors create actions natively — a checklist item that begins with a Google Docs person chip is an action assigned to that person. Each action is anchored with a named range so its identity survives edits. The sidebar (a Workspace Add-on) is the user-facing surface for the active document; the ActionSheet is the cross-doc store.

### Quality Goals
| Priority | Quality Goal | Scenario |
|----------|-------------|----------|
| 1 | Idempotence | Clicking **Sync now** twice in succession with no edits produces no further writes to the doc or the ActionSheet |
| 2 | Data integrity | No action record is silently overwritten; `Last Modified` precedence determines the winner on every conflict |
| 3 | Operability | A document author can capture an action by adding a checklist item that begins with a person chip — no typed prefix, no separate sheet interaction |
| 4 | Stable identity | An action's anchor (named range) survives edits elsewhere in the doc; no duplicate ActionSheet rows are produced |

### Stakeholders
| Stakeholder | Expectation |
|-------------|-------------|
| Administrator | One-time deploy of the add-on (private or admin-deployed) and the container-bound automation; clear errors when configuration is missing |
| Document author | Capture and update actions in a Doc without leaving the document; the sidebar reflects the doc's current state |
| Action owner | Edit status, action text, or assignee in the ActionSheet; changes propagate to the doc on the next Sync |
| Reviewer / manager | Filter and search all open actions across all docs from the ActionSheet |

---

## Constraints

### Technical Constraints
- The sidebar is a Google Workspace Add-on for Docs (standalone script with an add-on manifest); the cross-doc automation is a separate container-bound script on the ActionSheet
- The two Apps Script projects share no code and never call each other — they communicate only through ActionSheet rows
- The GCP project linked to the add-on must have the **Google Docs REST API** enabled (used for `createNamedRange`, `deleteNamedRange`, and tracker-table `batchUpdate` operations); the add-on requires the `https://www.googleapis.com/auth/script.external_request` scope to call the REST API
- DocumentApp is used for read-side traversal because it exposes PERSON chips ergonomically; the REST API is used for write-side anchoring and table mutation
- GAS execution time limit: 6 minutes per run. The timed sweep batches docs to stay within the limit
- The executing user (sidebar) must have edit access to the active doc; the automation script's owner must have access to all docs referenced by ActionSheet rows
- Simple `onEdit` triggers cannot call external services; the ActionSheet timestamp stamper is an installable trigger
- The visual checked state of a checklist item is **not** readable through any Google API; the source of truth for status is the trailing `(Status)` token

### Action Format
- An **action** is a checklist item (Google Docs checklist; visually a checkbox) whose first inline child is a Google Docs PERSON chip
- The assignee email and display name come from the chip
- Action text is everything after the chip on the same paragraph, with any trailing `(Status)` token stripped
- Status lives in a trailing parenthesized token at the end of the paragraph; `(Open)` is the default written when missing; `(Closed)` is recognized for archiving; any other value is preserved verbatim as a free-form status
- Each action is anchored by a named range whose `namedRangeId` is the durable identity stored in the ActionSheet
- Dates are stored in the ActionSheet as native sheet date values; in the in-doc tracker table they are written using the sheet's locale-formatted date

### Organizational Constraints
- No external service dependencies; both projects run entirely within Google Workspace
- No server infrastructure

---

## ActionSheet Schema

### ActionSheet Columns

| Column | Notes |
|--------|-------|
| NamedRangeId | The durable identity of the action; matches the `namedRangeId` of the anchor named range in the source doc |
| ID | Document-scoped sequential integer for human reference (e.g. shown in the tracker table) |
| Assignee Email | Canonical email address from the person chip |
| Assignee Name | Display name from the person chip |
| Action | Action item text (chip stripped, trailing `(Status)` stripped) |
| Status | Current status; `Open` by default, `Closed` recognized for archiving, otherwise free-form |
| Document | Hyperlink cell — display text is the document title, target is the document URL |
| Assigned Date | Date the action was first written to the ActionSheet |
| Last Modified | Most recent reconcile or user edit time; empty means the row has never been synced (no separate Synced column) |

Sheet filters are enabled on all columns. The Document column is always written as a hyperlink cell; plain-text document names are not accepted.

### In-Doc Action Tracker Table

The in-doc tracker is a table inserted by the **Insert / refresh tracker** button, preceded by a short instructional paragraph summarizing the sync rules:

| Column | Notes |
|--------|-------|
| ID | Document-scoped sequential integer |
| Assignee | Display name (or email if name is empty) |
| Action | Action text |
| Status | Current status |
| Assigned Date | Date first synced |
| Last Modified | Most recent reconcile or edit time |

The tracker table is itself anchored by a named range so refresh can replace its contents in place without disturbing surrounding doc content.

---

## Core Capabilities
- Detect actions in the **active doc** (the doc the sidebar is attached to) as checklist items beginning with a PERSON chip
- Anchor each action with a named range; the `namedRangeId` is the stable identity recorded in the ActionSheet
- Maintain a trailing `(Status)` token on each action paragraph; default `(Open)`, recognize `(Closed)` for archiving, preserve any other value as a free-form custom status
- Sync the active doc to the ActionSheet on demand from the sidebar — a single **Sync now** action that scans the doc and reconciles ActionSheet rows in one round (push/pull resolved by `Last Modified`)
- Insert or refresh the in-doc tracker table on demand, prefixed with concise instructional text summarizing the sync rules
- Periodic timed sweep (owned by the ActionSheet automation script) reconciles all docs referenced by ActionSheet rows, catching docs no one opened recently
- Archive ActionSheet rows with `Status = Closed` and `Last Modified > 30 days` to the archive sheet

---

## Use Cases

### Invariants (apply to every use case)

- **Identity is the named range.** The `namedRangeId` of the action's anchor is the durable key. ActionSheet rows are keyed on `NamedRangeId`. The doc-scoped `ID` is for human reference only.
- **Status is the trailing parenthesized token.** The visual checkbox state is decorative; the parenthesized status string is the truth.
- **Modified-date precedence.** Each row carries a `Last Modified` timestamp on both sides. Later wins. On tie, the ActionSheet row wins. A blank `Last Modified` means "just edited" — it is stamped to sync-start time and propagated.
- **Sync is eventually consistent.** Per-doc Sync is on-demand from the sidebar; cross-doc consistency is provided by the timed sweep.

---

### UC-A: Capture and track a new action

Actor: Document author

Preconditions:
- The add-on is installed and the user has the doc open

Primary Flow:
1. Author writes a checklist item that begins with a person chip and optional action text.
2. Author opens the sidebar and clicks **Sync now**.
3. The add-on scans the doc, recognizes the new chip-led checklist item as an action, creates a named range anchoring it, and writes a row to the ActionSheet with `Status = Open`.
4. The sidebar refreshes and shows the new action.

Postconditions:
- The action has a `namedRangeId`-anchored row in the ActionSheet.
- The action's paragraph ends with `(Open)` (added by the add-on if absent).

Acceptance Criteria:
- After clicking Sync, a newly typed chip-led checklist item appears in the sidebar and in the ActionSheet, with the assignee email resolved from the chip and `Status = Open`.
- The action's anchor survives an unrelated edit elsewhere in the doc — a second Sync does not produce a duplicate row.
- A second Sync with no further edits produces no writes to the doc or the ActionSheet.

---

### UC-B: Update an action from either side and converge

Actor: Action owner (ActionSheet side) **or** Document author (floating action side)

Preconditions:
- The action already exists with a row on the ActionSheet and a chip-led checklist paragraph in the doc, sharing a `namedRangeId`

Authoritative edit surfaces:
- The **floating action paragraph** (chip + action text + trailing `(Status)`) is the doc-side authority.
- The **ActionSheet row** is the cross-doc authority.
- The **in-doc tracker table is view-only**. Edits made directly inside its cells are not propagated and are overwritten on the next **Insert / refresh tracker** click. (See UC-C.)

Primary Flow:
1. Either the action owner edits `Status`, `Action`, or `Assignee` in the ActionSheet row, or the author edits the floating action paragraph in the doc (changing the trailing `(Status)`, the action text, or replacing the person chip with a different person).
2. The next Sync (sidebar click or timed sweep) detects the difference and applies the later-modified side's values to the other.

Postconditions:
- Both authoritative sides match.
- `Last Modified` on both sides reflects the time of the original user edit.

Acceptance Criteria:
- A sheet edit to `Status`, `Action`, or `Assignee` reaches the floating action paragraph after Sync, regardless of which side was edited last; later `Last Modified` wins.
- A doc edit to the floating action propagates to the ActionSheet after Sync for all three mutation types: trailing `(Status)` change (free-form value preserved verbatim), action text change, and chip-replaced assignee change.
- The action's named-range anchor survives every edit type above, and no duplicate ActionSheet rows are created.
- Edits typed directly into the in-doc tracker table cells are **not** reflected on the ActionSheet by any Sync; the next tracker refresh restores the rendered values from the floating actions (covered by UC-C).

---

### UC-C: Insert / refresh the in-doc tracker table

Actor: Document author

Preconditions:
- The doc contains at least one action

Primary Flow:
1. Author clicks **Insert / refresh tracker** in the sidebar.
2. The add-on inserts (or refreshes) the tracker table at its anchor, prefixed with the instructional paragraph, with one row per current action in document order.

Postconditions:
- The tracker table reflects the current set of actions in document order.

Acceptance Criteria:
- First click on a doc with N actions produces the instructional paragraph plus a table with N rows in document order, anchored so subsequent refreshes update in place.
- A subsequent click after the user closes one action and adds another produces a table that reflects both changes, in the same location, without leaving stale rows.
- The tracker table is **view-only**: any edit a user types directly into its cells is discarded on the next refresh and replaced by the rendered values from the floating actions and ActionSheet. The instructional paragraph above the table states this explicitly.

---

### UC-D: Archive closed actions

Actor: System (timed sweep on the ActionSheet)

Acceptance Criteria:
- An ActionSheet row with `Status = Closed` and `Last Modified > 30 days` is moved from the ActionSheet to the archive sheet on the next sweep, preserving `Last Modified`.
- Archiving does not alter any document content.
- If a previously archived action reappears (its named range still exists in the doc), a later Sync may restore an active ActionSheet row for it.

---

## Error Handling

Errors are surfaced in the sidebar (for add-on operations) or logged to the automation script's execution transcript (for sweep/archive). The full sync run is never aborted by a single-doc failure; other docs continue.

- **Checklist item missing a person chip** — surfaced as a warning row in the sidebar (`⚠ no assignee chip — fix in doc`); the row is not written to the ActionSheet.
- **Named range lost or deleted** — the scanner attempts to re-anchor if the action text and assignee still match a chip-led checklist item; otherwise the orphaned ActionSheet row is flagged in the sidebar for human resolution.
- **Doc inaccessible during sweep** — that doc is skipped with a logged error; other docs continue.
- **Docs REST API quota / scope error** — surfaced in the sidebar with the underlying message; no doc or sheet writes are made for that Sync.

---

## Non-Goals
- Real-time bidirectional sync (Sync is on-demand or on the sweep cadence)
- Reading the visual checked state of a checklist item (not exposed by any API)
- Cross-document `ID` uniqueness (`ID` is doc-scoped; the cross-doc key is `NamedRangeId`)
- Preservation of rich text formatting (bold, italic, colour) on the action paragraph when rewriting the trailing `(Status)` token
- Multi-tenant or cross-organisation support

---

## Glossary
| Term | Definition |
|------|------------|
| Action item (action) | A checklist item in a Google Doc whose first inline child is a PERSON chip. The chip is the assignee. The trailing parenthesized token is the status. |
| ActionSheet | The central Google Spreadsheet that aggregates actions across docs. The cross-doc store. |
| Add-on | The Google Workspace Add-on (Docs) that provides the sidebar UI. |
| Anchor (named range anchor) | The named range covering an action's checklist paragraph; its `namedRangeId` is the action's durable identity. |
| Automation script | The container-bound Apps Script on the ActionSheet that owns the `onEdit` timestamp stamper, the timed sweep trigger, and the archive job. |
| Last Modified | A timestamp column on each ActionSheet row and (implicitly) each anchored action. Records the most recent reconcile or user edit time. Empty means never synced. |
| Sidebar | The HTML UI shown by the add-on in the active doc. |
| Status | The recognized values are `Open` (default) and `Closed` (eligible for archive); any other parenthesized value is preserved as a free-form custom status. |
| Sweep | The time-based reconcile run on the ActionSheet that iterates rows grouped by document and pulls updates from docs no one opened recently. |
| Sync | One on-demand round in the sidebar that scans the active doc and reconciles ActionSheet rows for that doc in one shot. |
| Tracker table | The in-doc summary table written by **Insert / refresh tracker**, preceded by an instructional paragraph summarizing the sync rules. |
