# Plan — GActionSheet

## Status
Design phase — requirements.md complete with all initial open decisions resolved; foundational documentation initialised; implementation not yet started.

## Open Decisions
- B-NEW: Should a `Synced` column be added to the tracking sheet that is cleared when an edit is detected (by the `onEdit` trigger) and written with the sync date/time when the row has been successfully reconciled? This would give users visible confirmation that a change has propagated and support auditing.

## Recent Findings
- GAS `onEdit` simple trigger cannot call external services; sheet-update trigger must be an installable trigger. Sheet→Doc propagation happens at next timed or on-demand sync, not in real time.
- `DOC_FOLDER_ID` defaults to the spreadsheet's own parent folder when not set on first `initializeTriggers` call.
- Archive move is programmatic and will not fire the installable `onEdit` trigger; guard mechanism needed only for sheet-row writes during reconciliation.
- Heading styles: `HEADING1`–`HEADING6` all accepted as section delimiters; document authors choose the level.
- Assignee token: bare email, display-name form, and Docs mention chips all accepted; token preserved as-is on rewrite (normalization to canonical form deferred).
- Missing tracked-actions section: auto-created at end of document with `HEADING1`; missing table inside an existing section also auto-created.
- Floating-action rewrite: full paragraph text replacement, preserving the paragraph's existing paragraph style.
- Sheet timestamp cells: native Date values (enables filtering/sorting); doc table and floating-action text use ISO 8601 strings.

## Working
```
bdls --ready            # available work (unblocked, prioritized)
bdls                    # all open issues
bd show <id>            # full issue detail with deps
bd update <id> --claim  # claim and start work
bd close <id>           # mark complete
/bd-report              # generate bdreport.md snapshot
```
