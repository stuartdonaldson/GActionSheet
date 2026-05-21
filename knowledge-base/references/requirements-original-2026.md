---
**ARCHIVED:** Original requirements document, superseded by docs/CONTEXT.md on 2026-05-20. Preserved for historical context only.
---

# Requirements: Google Docs and Google Sheets Action Sync

## 1. Purpose

The system shall track and synchronize action items between one Google Sheet and multiple Google Docs.

## 2. Definitions

- Action record: one tracked task/action item.
- Source document: the Google Doc that contains a given action record.
- Tracking sheet: the Google Sheet tab configured to store active synchronized action records.
- Archive sheet: the Google Sheet tab that stores action records with `Status` = `Closed` that have not been modified for more than 30 days.
- Floating action: an action written as normal document text outside the tracked-actions table.
- Tracked-actions section: the document section headed by the paragraph `=== Tracked Actions ===`.
- Tracked-actions table: the table inside the tracked-actions section that stores the normalized action records for that document.
- Sync: one execution that reads a document, normalizes document actions, and reconciles them bidirectionally with the tracking sheet.

## 3. Record Identity

1. Each action record shall be identified by the pair `(Document, ID)`.
2. `ID` values need only be unique within a single document.
3. The `Document` field shall be stored as a single cell whose display text is the document title and whose hyperlink is the document URL.
4. If two different documents contain the same `ID`, they shall be treated as distinct action records.

## 4. Tracking Sheet Schema

The tracking sheet and archive sheet shall each contain the following columns:

1. `ID`
2. `Assignee Email`
3. `Assignee Name`
4. `Action`
5. `Status`
6. `Document`
7. `Date Created`
8. `Date Modified`
9. `Synced`

The system shall treat the header names above as authoritative. Column order may vary if the required headers are present. The `Document` cell shall use the document title as display text and include a hyperlink to the document URL. Both sheets shall have spreadsheet column filtering enabled.

The `Synced` column shall behave as follows:
- When sync successfully reconciles a row (whether the sheet or document wins), sync shall write the sync execution time as a native Date value to the `Synced` cell for that row.
- When the `onEdit` trigger detects a direct user edit to `Assignee Email`, `Assignee Name`, `Action`, or `Status`, it shall clear the `Synced` cell for that row (set to empty), indicating the row has a pending change not yet propagated.
- The `onEdit` trigger shall not clear `Synced` when the edit originates from the sync script.
- Clearing or writing `Synced` shall not update `Date Modified`.

## 5. Document Structure

1. A tracked-actions section shall begin at a paragraph whose full text is exactly `=== Tracked Actions ===`.
2. That start paragraph shall use a `HEADING1` through `HEADING6` style.
3. The tracked-actions section shall end immediately before the next paragraph that uses a `HEADING1` through `HEADING6` style.
4. Each document shall contain at most one tracked-actions section.
5. If the tracked-actions section is missing, sync shall create it at the end of the document using `HEADING1` style, then create an empty tracked-actions table with the required headers inside it.
6. If the tracked-actions section exists but contains no table, sync shall create the tracked-actions table with the required headers inside the section.
7. If more than one tracked-actions section is found, sync shall fail with a clear error.

## 6. Tracked-Actions Table Schema

The tracked-actions table shall contain the following columns:

1. `ID`
2. `Assignee Email`
3. `Assignee Name`
4. `Action`
5. `Status`
6. `Date Created`
7. `Date Modified`

The table shall contain at most one row for a given `ID` within a document. Column order may vary if the required headers are present.

## 7. Floating Action Format

1. A floating action may appear anywhere in the document, including outside the tracked-actions section.
2. A floating action shall be recognized when a paragraph begins with `AI-` followed by either:
	- an integer identifier, for example `AI-12`, or
	- no identifier digits, for example `AI-`.
3. The floating action shall next contain an assignee token in one of the following forms:
   - Bare email preceded by `@`, for example `@email@example.com`
   - Display-name form, for example `@Display Name <email@example.com>`
   - A Google Docs mention chip whose underlying email can be extracted
4. The full floating-action format shall be:

	`AI-<optional integer> <assignee token> | action | status | date created | date modified`

5. The separator token shall be the literal string ` | `.
6. The `action`, `status`, `date created`, and `date modified` fields may be omitted from the right side, but field order shall remain fixed.
7. If a paragraph contains a valid `AI-` prefix and a recognized assignee token, it shall be treated as a floating action even when one or more trailing fields are missing.
8. The `Action` and `Status` values shall be treated as case-preserving free text.
9. The `Action` field shall not contain the separator token ` | `.
10. The system shall preserve the assignee token in its existing form when rewriting a floating action paragraph; normalization to a canonical display-name form is deferred to a future revision.
11. The `Assignee Email` field shall be extracted from the assignee token regardless of form. The `Assignee Name` field shall be extracted from the display-name form when present; it shall be left empty for bare-email and mention-chip forms where no display name is present.

## 8. ID Assignment

1. If a floating action contains `AI-<integer>`, that integer shall be used as the action `ID`.
2. If a floating action contains `AI-` with no integer, sync shall assign the next available positive integer for that document.
3. The next available integer shall be `max(existing IDs in that document) + 1`.
4. Assigned IDs shall be persisted back into the document during the same sync.

## 9. Timestamp Rules

1. Each action record shall have `Date Created` and `Date Modified` values.
2. Timestamps shall be compared at the action-record level, not at the whole-document level.
3. Timestamps shall be stored and compared in UTC.
4. When written into the document tracked-actions table or floating-action text, timestamps shall use ISO 8601 format strings.
5. When written into sheet cells (`Date Created`, `Date Modified`), timestamps shall be stored as native Google Sheets Date values to enable date-based filtering and sorting.
6. If a newly discovered floating action has no timestamps, sync shall set both created and modified timestamps to the sync time.
7. If a newly discovered floating action has a created timestamp but no modified timestamp, sync shall set modified equal to created.

## 10. Document Normalization Rules

1. During sync, the system shall read both the tracked-actions table and all floating actions in the document.
2. The tracked-actions table shall be the canonical representation inside the document.
3. Any floating action not already represented in the tracked-actions table shall be added to the tracked-actions table.
4. If the same `ID` appears in both a floating action and the tracked-actions table, the version with the later modified timestamp shall win.
5. If the same `ID` appears in both places and one side has no modified timestamp, the side with a modified timestamp shall win.
6. If the same `ID` appears in both places and neither side has a modified timestamp, the tracked-actions table row shall win.
7. After normalization, the tracked-actions table shall contain one row for every action record in the document.
8. After normalization, every floating action paragraph that matched a tracked action shall be rewritten to reflect the normalized values. The rewrite shall replace the full paragraph text content while preserving the paragraph's existing paragraph style (e.g., Normal text, Heading level).

## 11. Sheet Reconciliation Rules

1. Sync shall reconcile each normalized document action record with the matching sheet row using `(Document, ID)`.
2. If the sheet has no matching row, sync shall create one.
3. If the document has no matching record for an existing sheet row for that same document, sync shall leave the sheet row unchanged.
4. If both the sheet row and document record exist, the version with the later modified timestamp shall win.
5. If the document record wins, sync shall update the matching sheet row.
6. If the sheet row wins, sync shall update the tracked-actions table row and any matching floating action paragraph in the document.
7. If both sides have equal modified timestamps and different content, the sheet row shall win.
8. Sync shall search both the tracking sheet and the archive sheet when looking for an existing row matching `(Document, ID)`.
9. Sheet-to-document propagation (rules 6 and 7 above) occurs during the same sync execution — either from the `Sync` menu command or the 30-minute timed scan.

## 12. Sync Invocation

1. The script shall add a custom menu named `Action Sync` to the tracking sheet UI when the sheet is opened.
2. The `Action Sync` menu shall contain a `Sync` command that runs sync for all registered documents.
3. The script shall expose an `initializeTriggers` function that an administrator calls once to install all required triggers.
4. `initializeTriggers` shall install an installable `onEdit` trigger bound to the tracking sheet to run the sheet update logic.
5. `initializeTriggers` shall install a time-based trigger that runs a full document-folder scan every 30 minutes.
6. The 30-minute scan shall process every registered document in sequence, syncing each one in turn.
7. `initializeTriggers` shall be idempotent: calling it a second time shall not create duplicate triggers.
8. Existing triggers of the same type and function name shall be deleted before new ones are created.

## 13. Document Discovery

1. The system shall use a script property named `DOC_FOLDER_ID` to identify the root folder for document discovery.
2. `DOC_FOLDER_ID` may contain either a Google Drive folder ID or a full folder URL; the system shall extract the folder ID from either form.
3. If `DOC_FOLDER_ID` is not set when `initializeTriggers` is called, the system shall set it to the folder ID of the folder that contains the script's parent spreadsheet.
4. Document discovery shall search the root folder and all descendant folders recursively.
5. Discovery shall return only Google Docs files (MIME type `application/vnd.google-apps.document`).
6. Discovery shall return only documents whose last-modified time is within the last seven days.
7. The document list produced by discovery is the input set for both the 30-minute timed scan and the `Sync` menu command.

## 14. Sync Scope and Idempotence

1. A sync execution shall process one document at a time.
2. A sync execution shall only read and write sheet rows for the current document.
3. Re-running sync without any user-visible changes shall produce no further content changes in the document or sheet.

## 15. Deletion Behavior

1. Removing a floating action paragraph shall not delete the corresponding tracked-actions table row or sheet row if that action still exists in the tracked-actions table.
2. Removing a tracked-actions table row shall not delete the corresponding sheet row if the action still exists as a floating action in the same document.
3. Sync shall not delete sheet rows automatically.
4. Sync shall not delete tracked-actions table rows automatically unless an explicit delete feature is added in a future revision.

## 16. Archive Behavior

1. During sync, the system shall move rows from the tracking sheet to the archive sheet when their `Status` is exactly `Closed` and their `Date Modified` is more than 30 days before the sync execution time.
2. Moving a row to the archive sheet shall not alter its `Date Modified` value.
3. The sheet update trigger shall not fire — and `Date Modified` shall not be updated — as a result of the sync script writing to either the tracking sheet or the archive sheet.
4. Applying or clearing a spreadsheet column filter on either sheet tab shall not cause `Date Modified` to be updated.
5. After archiving, the row shall be appended to the archive sheet and removed from the tracking sheet.

## 17. Sheet Update Trigger

1. The tracking sheet shall have an installable `onEdit` trigger.
2. The trigger shall run only for edits on the tracking sheet tab; edits on the archive sheet tab or any other tab shall be ignored.
3. The trigger shall ignore the header row.
4. If a user directly edits `Assignee Email`, `Assignee Name`, `Action`, or `Status`, the trigger shall update `Date Modified` for that row to the trigger execution time and clear the `Synced` cell for that row.
5. If a user edits any other column, the trigger shall not modify `Date Modified` or `Synced`.
6. The trigger shall update only the edited row.
7. The trigger shall not update `Date Modified` or `Synced` when the edit originates from the sync script. The script shall use a guard mechanism (such as a script property flag or `LockService` token) to suppress the trigger during programmatic writes.

## 18. Error Handling

1. Sync shall fail with a clear error if a document contains duplicate tracked-actions table rows for the same `ID`.
2. Sync shall fail with a clear error if a floating action has an invalid email token.
3. Sync shall fail with a clear error if the tracking sheet is missing any required header.
4. Sync shall fail with a clear error if the tracked-actions table is missing any required header.

## 19. Acceptance Criteria

1. A new floating action with no numeric ID shall receive the next sequential ID and appear in both the tracked-actions table and the sheet after sync.
2. A floating action that already has an ID shall preserve that ID after sync.
3. When the document record has a later modified timestamp than the matching sheet row, the sheet row shall be updated from the document.
4. When the sheet row has a later modified timestamp than the matching document record, the document table row and matching floating action shall be updated from the sheet.
5. A second sync immediately after a successful sync shall make no additional changes.

