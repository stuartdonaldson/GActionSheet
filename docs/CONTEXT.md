# CONTEXT — GActionSheet

## Introduction & Goals

### Purpose
GActionSheet synchronizes action items bidirectionally between a Google Sheet hub and multiple Google Docs. Document authors capture actions inline using a lightweight `AI-` prefix syntax; the system normalizes, assigns identifiers, and reconciles records across all registered documents on a 30-minute cycle or on-demand from a sheet menu.

### Quality Goals
| Priority | Quality Goal | Scenario |
|----------|-------------|----------|
| 1 | Idempotence | Running sync twice in succession produces no additional changes to any document or sheet row |
| 2 | Data integrity | No action record is silently overwritten; timestamp precedence determines the winner on every conflict |
| 3 | Operability | A document author can capture an action item by typing a single line in a Doc, with no sheet interaction required |
| 4 | Recoverability | A sync that errors mid-run leaves documents and the sheet in a consistent, non-corrupt state |

### Stakeholders
| Stakeholder | Expectation |
|-------------|-------------|
| Administrator | One-time setup via `initializeTriggers`; clear error messages when configuration is missing |
| Document author | Capture action items inline in any registered Doc without opening the sheet |
| Action owner | Update status and assignee directly in the sheet; changes propagate to the source Doc on next sync |
| Reviewer / manager | Filter and search all open action items across all documents from a single sheet |

---

## Constraints

### Technical Constraints
- Runs as a container-bound Google Apps Script attached to the tracking Spreadsheet
- GAS execution time limit: 6 minutes per run; sync of large document sets may require batching
- DocumentApp quota limits apply; large documents with many paragraphs increase execution time
- All source documents must reside within a single Drive folder tree identified by `DOC_FOLDER_ID`
- The executing user must have edit access to both the Spreadsheet and all source documents in scope
- Simple `onEdit` triggers cannot call external services; the sheet-update trigger is an installable trigger

### Format and Normalization Constraints
- Dates written in Google Docs use the format `YYYY-MM-DD h:m`.
- A partial date such as `5/20` is normalized using the supplied month and day, plus the year and time taken from the document's last-modified timestamp captured at sync start.
- An omitted or empty date is interpreted as the document's last-modified timestamp captured at sync start.
- The literal field separator between action-line tokens is ` | ` (space-pipe-space).
- An assignee token in a document may take one of three forms: bare email (e.g. `user@example.com`), display-name-and-email (e.g. `'Name' <user@example.com>`), or a Google Docs mention chip that embeds the display name and email address.
- An omitted or empty `status` is interpreted as `Open`.

### Organizational Constraints
- No external service dependencies; the system runs entirely within Google Workspace
- No server infrastructure; all logic executes within GAS

---

## Sheet Schema

### Tracking Sheet Columns

| Column | Notes |
|--------|-------|
| ID | Document-scoped sequential integer |
| Assignee Email | Canonical email address extracted from the assignee token |
| Assignee Name | Display name extracted from the assignee token; empty when the token is a bare email |
| Action | Action item text |
| Status | Current status; `Open` when omitted |
| Document | Hyperlink cell — display text is the document title, target is the document URL |
| Date Created | Timestamp when the row was first written to the sheet |
| Date Modified | Last reconcile or edit time; empty means the row has never been synced (no separate Synced column exists). |

Sheet filters are enabled on all columns.

### Tracked-Actions Table Columns

The tracked-actions table inside each Google Doc mirrors the tracking sheet schema minus the Document column:

| Column | Notes |
|--------|-------|
| ID | Document-scoped sequential integer |
| Assignee Email | Canonical email address |
| Assignee Name | Display name; empty for bare-email tokens |
| Action | Action item text |
| Status | Current status |
| Date Created | Timestamp when the row was first written |
| Date Modified | Last reconcile or edit time |

### Hyperlink-Cell Rule

The Document column in the tracking sheet is always written as a hyperlink cell: display text = document title, target = document URL. Plain-text document names are not accepted.

---

## Core Capabilities
- Within a document, the tracked-actions table is the authoritative record of every action; floating action paragraphs are rewritten to match it on every sync. A floating action whose `AI-` identifier is not yet present in the table seeds a new row.
- Detect and parse floating action paragraphs (`AI-<id> @assignee | action | status | dates`) in any Google Doc. The `assignee` token may be either a plain email address or a Google Docs person tile that embeds the display name and email address. The `status` and trailing `dates` fields are optional when detected. The `action` field may contain any text, including spaces, and extends either to the end of the paragraph or to the next `|` delimiter when a `status` field follows. An omitted or empty `status` is interpreted as `Open`. An omitted or empty date is interpreted as the action record's last modification timestamp. Dates written in Google Docs use the format `YYYY-MM-DD h:m`.
- Assign sequential numeric IDs to unnumbered floating actions, persisting them back to the document in the same sync
- Normalize floating actions into a tracked-actions table within the same document
- Reconcile document action records with sheet rows using last-modified-timestamp conflict resolution
- Propagate sheet edits back to source documents on the next timed or on-demand sync
- Discover source documents automatically from a configured Drive folder tree, scanning only documents modified in the last 7 days
- Archive action records with `Status = Closed` that have not been modified in more than 30 days
- Run bidirectional sync on a 30-minute time-based trigger or on-demand via an `Action Sync` sheet menu

---

## Use Cases

### Invariants (apply to every use case below)

- **Authority within a document.** The tracked-actions table is the authoritative representation of every action record. Floating actions are rewritten to match the table on every sync. The single exception is initialization: when a floating action carries an `AI-` identifier (including the placeholder `AI-#`) that does not yet exist in the tracked-actions table, that floating action seeds a new row in the table.
- **Modified-date precedence.** Each action record carries a `Date Modified` timestamp in both the table and the sheet. A blank `Date Modified` is treated as "just updated": the system sets it to the sync-start time and propagates the record outward. When the table row and the sheet row both have timestamps, the newer one wins and is propagated to the other.
- **Sync is eventually consistent.** Authority and precedence are evaluated at sync time, not at edit time.
- **Tie-break rule.** When `Date Modified` is equal on the sheet row and the table row but content differs, the sheet row wins.

Individual use cases do not restate these invariants; their acceptance criteria assume them.

---

### UC-1: Capture a New Floating Action

Actor: Document author

Preconditions:
- The document resides in the folder tree identified by `DOC_FOLDER_ID`
- The document contains exactly one tracked-actions section (`=== Tracked Actions ===`)

Primary Flow:
1. Author types a floating action paragraph anywhere in the document, with an assignee expressed either as a plain email address or a Google Docs person tile, and with `status` and trailing dates optionally omitted: `AI- @assignee@example.com | Complete proposal draft`
2. On the next sync (timed or via menu), the system parses the floating action
3. System assigns the next available sequential ID for that document
4. System rewrites the floating action paragraph with the assigned ID and normalized values, filling in `Open` and the document's last modification timestamp captured at sync start when those fields were omitted; dates written back to the Google Doc use the format `YYYY-MM-DD h:m`
5. System adds a corresponding row to the tracked-actions table
6. System creates a matching row in the tracking sheet with the document as a hyperlink cell

Postconditions:
- The action record exists in the tracked-actions table with a permanent ID
- The sheet contains a matching row keyed on `(Document, ID)`
- The floating action paragraph reflects the assigned ID and normalized status/timestamps using the Google Doc date format `YYYY-MM-DD h:m`

Constraints:
- ID uniqueness is scoped to the document; the same integer may appear in different documents
- The assignee token may be represented in the source document as a plain email address or a Google Docs person tile that embeds the display name and email address
- An omitted or empty status in the source paragraph is interpreted as `Open`
- An omitted or empty date in the source paragraph is interpreted as the action record's last modification timestamp captured from the document at sync start
- A partial date such as `5/20` is normalized to `YYYY-MM-DD h:m` using the supplied month and day, and the year and time from the document's last modification timestamp captured at sync start

Acceptance Criteria:
- After sync, every floating action paragraph has a matching row in the tracked-actions table, keyed on the document-scoped ID.
- After sync, every floating action paragraph has a matching tracking-sheet row keyed on `(Document, ID)`.
- A floating action paragraph without a numeric ID receives the next available document-scoped ID during sync; existing explicit IDs are preserved.
- A floating action paragraph with no `status` is normalized to `Open`.
- A floating action paragraph with no date is normalized to the document's last-modified timestamp captured at sync start.

---

### UC-2: Capture a New Action in the Tracked-Actions Table

Actor: Document author

Preconditions:
- The document resides in the folder tree identified by `DOC_FOLDER_ID`
- The document contains exactly one tracked-actions section (`=== Tracked Actions ===`)
- The tracked-actions table is writable by the executing user

Primary Flow:
1. Author adds a new row to the tracked-actions table in the document, providing an assignee and action text, with `status` and date fields optionally omitted
2. On the next sync (timed or via menu), the system parses the new tracked-actions table row
3. System assigns the next available sequential ID for that document if the row does not already contain an explicit ID
4. System normalizes the row values, filling in `Open` and the document's last modification timestamp captured at sync start when those fields were omitted; dates written in the Google Doc use the format `YYYY-MM-DD h:m`
5. System creates or updates the corresponding floating action paragraph for the same action record in the document
6. System creates a matching row in the tracking sheet with the document as a hyperlink cell

Postconditions:
- The action record exists in the tracked-actions table with a permanent document-scoped ID
- The document contains a matching floating action paragraph for the same action record
- The sheet contains a matching row keyed on `(Document, ID)`

Constraints:
- ID uniqueness is scoped to the document; the same integer may appear in different documents
- The assignee token may be represented in the source document as a plain email address or a Google Docs person tile that embeds the display name and email address
- An omitted or empty status in the source row is interpreted as `Open`
- An omitted or empty date in the source row is interpreted as the action record's last modification timestamp captured from the document at sync start

Acceptance Criteria:
- After sync, every tracked-actions table row has a matching floating action paragraph in the same document.
- After sync, every tracked-actions table row has a matching tracking-sheet row keyed on `(Document, ID)`.
- A new tracked-actions row without an explicit ID receives the next available document-scoped ID during sync.
- A new tracked-actions row with no `status` is normalized to `Open`.
- A new tracked-actions row with no date is normalized to the document's last-modified timestamp captured at sync start.

---

### UC-3: Propagate Sheet Updates to the Table and Floating Actions

Actor: Action owner

Preconditions:
- The action record exists in the tracking sheet
- The source document is accessible by the executing user

Primary Flow:
1. Action owner edits one or more mutable fields for an existing action record in the tracking sheet
2. The installable `onEdit` trigger fires and updates `Date Modified` for that row
3. On the next sync, the sheet row has a later `Date Modified` than the document record
4. System updates the tracked-actions table row in the source document
5. System rewrites the matching floating action paragraph to reflect the new values, filling any previously omitted status or date fields with the normalized values; dates written back to the Google Doc use the format `YYYY-MM-DD h:m`

Postconditions:
- The tracked-actions table and any floating action paragraph reflect the sheet's current values
- `Date Modified` in both sheet and document reflects the time of the original sheet edit, and the floating action paragraph uses the Google Doc date format `YYYY-MM-DD h:m`

Constraints:
- Sheet-to-document propagation is eventually consistent; changes appear in the document on the next sync, not in real time

Acceptance Criteria:
- When the sheet row has the latest `Date Modified`, the next sync rewrites both the matching tracked-actions table row and the matching floating action paragraph to the sheet's values.
- After sync, the tracked-actions table row and the floating action paragraph reflect the same values (the table is authoritative; the floating paragraph mirrors it).
- A blank `Date Modified` on the sheet row is treated as a dirty edit and propagated outward; there is no separate Synced column — reconciliation state is recorded solely in `Date Modified`.
- If the source document is unavailable during sync, the sheet row is not considered successfully applied until a later sync can update both document representations.

---

### UC-4: Archive Closed Actions

Actor: System (timed sync)

Preconditions:
- The tracking sheet contains rows with `Status = Closed`
- Those rows have not been modified in more than 30 days

Primary Flow:
1. During sync, the system identifies eligible rows in the tracking sheet
2. System appends each eligible row to the archive sheet
3. System removes the row from the tracking sheet
4. `Date Modified` is not changed during the move

Postconditions:
- Archived rows are visible in the archive sheet
- The tracking sheet no longer contains closed rows older than 30 days
- No document content is altered by archiving

Constraints:
- Moving a row to the archive sheet does not suppress future syncs for that action record if it reappears in a document

Acceptance Criteria:
- A tracking-sheet row with `Status = Closed` whose `Date Modified` is older than 30 days is moved from the tracking sheet to the archive sheet on the next eligible sync, and removed from the tracking sheet in the same sync.
- An archived row preserves its `Date Modified`.
- Archiving does not alter any document content.
- If a previously archived action record reappears in a document, a later sync may create or restore an active tracking-sheet row for that record.

---

### UC-5: Reference an Existing Action by ID in a Floating Paragraph

Actor: Document author

Preconditions:
- The document resides in the folder tree identified by `DOC_FOLDER_ID`
- The document contains exactly one tracked-actions section (`=== Tracked Actions ===`)
- The tracked-actions table already contains a row for the referenced ID

Primary Flow:
1. Author writes a bare `AI-<n>` floating paragraph in the document, with no other fields, referencing an action record that already exists in the tracked-actions table.
2. On the next sync, the system recognises the bare reference and expands the floating paragraph to mirror the canonical row from the tracked-actions table (assignee, action text, status, date).

Postconditions:
- The floating paragraph reflects the full canonical content of the tracked-actions row for that ID.
- The tracked-actions row is unchanged.

Acceptance Criteria:
- A bare `AI-<n>` floating paragraph whose ID matches an existing tracked-actions table row is rewritten on sync to mirror that row.
- A bare `AI-<n>` whose ID does not match any tracked-actions table row is treated as a new floating action under UC-1 and seeds a new row.

---

### UC-6: Revert a Locally Edited Floating Action to the Table

Actor: Document author

Preconditions:
- A floating action paragraph and its matching tracked-actions table row already exist for the same `(Document, ID)`
- Neither the tracked-actions row nor the corresponding sheet row has a newer `Date Modified` than the existing record

Primary Flow:
1. Author edits the floating action paragraph in place (changes assignee, action text, status, or date) without touching the tracked-actions table or the tracking sheet.
2. On the next sync, because the tracked-actions table is authoritative within the document, the floating paragraph is rewritten back to match the table row.

Postconditions:
- The floating action paragraph matches the tracked-actions table row.
- The tracked-actions table row and the sheet row are unchanged.

Acceptance Criteria:
- If a floating action paragraph diverges from its tracked-actions table row, and neither the table row nor the sheet row carries a newer `Date Modified`, the next sync rewrites the floating paragraph to match the table.
- The table row and the sheet row are not modified by this case.

---

## Error Handling

Sync fails with a clear error (logged to execution transcript and surfaced in the sheet menu) on the following conditions:

- **Duplicate table IDs within a document** — two or more rows in the tracked-actions table share the same document-scoped ID; the sync for that document is aborted and the duplicate is reported.
- **Invalid email token in a floating action** — a floating action's assignee token cannot be parsed as a bare email, a display-name-and-email form, or a mention chip; the affected action record is skipped and the error is reported.
- **Missing required headers on sheet or table** — the tracking sheet or a tracked-actions table is missing one or more expected column headers; sync for the affected document or sheet is aborted and the missing headers are reported.

Partial failures (single document errors) do not abort the full sync run; other documents and sheet rows continue to be processed.

---

## Non-Goals
- Real-time bidirectional sync (sync is eventually consistent via 30-minute cycle)
- Cross-document ID uniqueness or global action identifiers
- Automatic deletion of action records from documents or the sheet
- Preservation of rich text formatting (bold, italic, colour) when rewriting floating action paragraphs
- Multi-tenant or cross-organisation support

---

## Glossary
| Term | Definition |
|------|------------|
| Action record | One tracked task or action item, identified by `(Document, ID)` |
| Archive sheet | The Sheet tab that holds `Closed` action records not modified in more than 30 days |
| Date Modified | A timestamp column present in both the tracking sheet and every tracked-actions table. Records the last reconcile or edit time. An empty value means the record has never been synced. There is no separate Synced column; synchronization state is recorded entirely in this field. |
| Document | A Google Doc in the registered folder tree; identified by its URL and title |
| Floating action | An action item written as plain document text using the `AI-` prefix syntax, outside the tracked-actions table; the assignee may be a plain email address or a Google Docs person tile, `status` and trailing date fields may be omitted, an empty status is treated as `Open`, an empty date is treated as the last modification timestamp, and dates written in the Google Doc use the format `YYYY-MM-DD h:m` |
| Sync | One execution that reads a document, normalizes its actions, and reconciles them bidirectionally with the tracking sheet |
| Tracked-actions section | The document section delimited by a heading paragraph whose exact text is `=== Tracked Actions ===`. If the section is absent when a floating action first seeds a row, the system creates the section and an empty table at the end of the document before writing the row. |
| Tracked-actions table | The table inside the tracked-actions section; the canonical representation of action records within a document |
| Tracking sheet | The Sheet tab that stores active (non-archived) synchronized action records |
| `DOC_FOLDER_ID` | A GAS script property containing the Drive folder ID (or URL) that roots document discovery |
