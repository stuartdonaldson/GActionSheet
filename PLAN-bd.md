# Plan — GActionSheet

This file is a pre-bd-adoption artifact. Current state, open decisions, and work items are
tracked in **bd** — this file is no longer updated and should not be read as current status.

```
bdls --ready            # available work (unblocked, prioritized)
bdls                    # all open issues
bd show <id>            # full issue detail with deps
bd update <id> --claim  # claim and start work
bd close <id>           # mark complete
bd prime                # full workflow context + persistent memories
/bd-report              # generate bdreport.md snapshot
```

## Historical record (resolved, kept for context only)

- B-NEW (resolved): no separate `Synced` column was added. `Last Modified` blank means
  never synced — see `docs/CONTEXT.md`.
- GAS `onEdit` simple trigger cannot call external services; sheet-update trigger must be
  an installable trigger. Sheet→Doc propagation happens at next timed or on-demand sync,
  not in real time.
- `DOC_FOLDER_ID` defaults to the spreadsheet's own parent folder when not set on first
  `initializeTriggers` call.
- Archive move is programmatic and will not fire the installable `onEdit` trigger; guard
  mechanism needed only for sheet-row writes during reconciliation.
- Heading styles: `HEADING1`–`HEADING6` all accepted as section delimiters; document
  authors choose the level.
- Assignee token: bare email, display-name form, and Docs mention chips all accepted;
  token preserved as-is on rewrite (normalization to canonical form deferred).
- Missing tracked-actions section: auto-created at end of document with `HEADING1`;
  missing table inside an existing section also auto-created.
- Floating-action rewrite: full paragraph text replacement, preserving the paragraph's
  existing paragraph style.
- Sheet timestamp cells: native Date values (enables filtering/sorting); doc table and
  floating-action text use ISO 8601 strings.
