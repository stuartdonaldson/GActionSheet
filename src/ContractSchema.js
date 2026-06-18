/**
 * ContractSchema.js
 *
 * Authoritative machine-readable contract definitions shared by the GAS app,
 * GAS fixtures, and external test consumers.
 *
 * Human-readable semantics, invariants, and ownership rules live in docs/DESIGN.md.
 */

var CONTRACT_SCHEMA = Object.freeze({
  actionItem: Object.freeze({
    fields: Object.freeze([
      'action_id',
      'assignee_email',
      'action_text',
      'status'
    ])
  }),

  sheetTeamData: Object.freeze({
    headers: Object.freeze(['Team Id', 'Folder Id', 'Contact', 'Team Link']),
    columnsByField: Object.freeze({
      team_id: 1,
      folder_id: 2,
      contact: 3,
      team_link: 4
    })
  }),

  sheetDocData: Object.freeze({
    headers: Object.freeze(['FileId', 'Doc Name', 'Doc Modified', 'Doc Updated', 'SyncStatus', 'Team Id', 'Action Count', 'Resolved Count']),
    columnsByField: Object.freeze({
      file_id: 1,
      doc_name: 2,
      doc_modified: 3,
      doc_updated: 4,
      sync_status: 5,
      team_id: 6,
      action_count: 7,
      resolved_count: 8
    })
  }),

  sheetAction: Object.freeze({
    fields: Object.freeze([
      'global_id',
      'file_id',
      'action_id',
      'assignee_email',
      'assignee_name',
      'action_text',
      'status',
      'document_formula',
      'doc_id',
      'doc_name',
      'created_date',
      'modified_date',
      'sync_status'
    ]),

    headers: Object.freeze([
      'globalId',
      'File Id',
      'ID',
      'Assignee Email',
      'Assignee Name',
      'Action',
      'Status',
      'Document',
      'Date Created',
      'Date Modified',
      'Sync Status'
    ]),

    columnsByField: Object.freeze({
      global_id: 1,
      file_id: 2,
      action_id: 3,
      assignee_email: 4,
      assignee_name: 5,
      action_text: 6,
      status: 7,
      document_formula: 8,
      created_date: 9,
      modified_date: 10,
      sync_status: 11
    })
  }),

  webApp: Object.freeze({
    routeNames: Object.freeze([
      'set_test_token',
      'upsert_action_rows',
      'sync_action_rows',
      'verify_action_rows',
      'mark_doc_not_found',
      'delete_action_row',
      'patch_action_status',
      'list_importable_actions',
      'forward_action_rows',
      'run_fixture'
    ]),

    // Routes that run in the WebApp but exist to support the ATDD harness — they
    // operate on production data/behaviour yet have no production caller. Kept out
    // of routeNames so production route enumeration stays clean. Gated to the test
    // token. Pre-code contract for GTaskSheet-5vwu.2; implemented by .9.
    testRouteNames: Object.freeze([
      'edit_action_row',          // the §16.9 `edit_sheet` act
      'find_sheet_actions',       // the §16.9 `find_sheet_actions` read query
      'verify_chip_integrity',    // post-sync doc chip assertion (6ov.8)
      'import_selected_for_test', // GTaskSheet-8qe5: interactive-test-entry-point for
                                   // AC-2/AC-3 (Import tab CHECK_BOX selection cannot be
                                   // driven via Playwright — EPIC GTaskSheet-pw5x)
      'forward_action_rows_test'  // GTaskSheet-apcu: drives _handleForwardActionRows'
                                   // core loop directly with an explicit forwards[]
                                   // payload, bypassing _listImportableActionsData's
                                   // resolved/Forwarded filter — the only way to reach
                                   // the seen[]/isResolved(entry.status) duplicate-
                                   // forward guard (UC-E AC4) from a test
    ]),

    // Per-route request/response shapes + completion signals. Field names that
    // denote a sheet row reuse the authoritative `sheetAction.fields` above; only
    // the message envelope is listed here (never the column table). Semantics:
    // docs/DESIGN.md §ATDD Journey Pre-Code Contract. Decisions: §16.11 #2/#3/#4.
    messages: Object.freeze({

      // sync_action_rows — bidirectional reconcile (Scenario C). The doPost handler
      // BLOCKS until the script-properties message queue (ACTION_SHEET_QUEUE) has
      // drained, so the harness's convergence primitive is simply "await the
      // response" — no log polling (§16.11 #4).
      //   Completion signal: the synchronous JSON response, returned only post-drain.
      sync_action_rows: Object.freeze({
        request:  Object.freeze(['action', 'testToken', 'docId']),
        response: Object.freeze(['ok', 'sheetWins', 'docWins', 'queueDrained']),
        completionSignal: 'synchronous response after ACTION_SHEET_QUEUE drains (§16.11 #4)'
      }),

      // edit_action_row — simulate a user editing one ActionSheet field over the API.
      // Addressed by globalId (§16.11 #3). On this API path it MUST replicate
      // onActionSheetEdit's Dirty + Date-Modified stamp, because doPost writes run
      // as the deployer in a separate execution and do not fire the installable
      // trigger (§16.11 #2; DESIGN.md §Programmatic Write Suppression). `fields`
      // carries one or more of sheetAction's editable fields (assignee_email,
      // action_text, status). Sheet-wins on the next sync.
      //   Completion signal: synchronous response; Sync Status = 'Dirty' on the row.
      edit_action_row: Object.freeze({
        request:  Object.freeze(['action', 'testToken', 'global_id', 'fields']),
        response: Object.freeze(['ok', 'global_id', 'row']),
        completionSignal: "synchronous response; row stamped Sync Status='Dirty' + Date Modified"
      }),

      // patch_action_status — sidebar status fast path (Scenario A). Addressed by
      // globalId (§16.11 #3). Async/unconditional upsert (no conflict resolution);
      // converges when a following sync() drains the queue (§16.11 #4).
      //   Completion signal: synchronous { ok } ack; durable convergence at next sync.
      patch_action_status: Object.freeze({
        request:  Object.freeze(['action', 'testToken', 'global_id', 'status']),
        response: Object.freeze(['ok', 'global_id']),
        completionSignal: 'synchronous ack; durable status converges on the next sync_action_rows'
      }),

      // delete_action_row — sidebar delete. Addressed by globalId (§16.11 #3); the
      // row is stamped Sync Status = 'Deleted' (not physically removed by this route).
      //   Completion signal: synchronous response; Sync Status = 'Deleted'.
      delete_action_row: Object.freeze({
        request:  Object.freeze(['action', 'testToken', 'global_id']),
        response: Object.freeze(['ok', 'global_id']),
        completionSignal: "synchronous response; row stamped Sync Status='Deleted'"
      }),

      // find_sheet_actions — read the current document's ActionSheet rows, scoped to
      // docId (§16.3 #4). Read-only; no mutation. Each row carries the authoritative
      // sheetAction.fields; `doc_id` / `doc_name` are DERIVED from `document_formula`
      // (col 7), not stored columns — the loader/reader resolves them (see .3).
      //   Completion signal: synchronous response carrying the docId-scoped rows.
      find_sheet_actions: Object.freeze({
        request:  Object.freeze(['action', 'testToken', 'docId']),
        response: Object.freeze(['ok', 'docId', 'rows']),
        completionSignal: 'synchronous response; rows scoped to docId'
      }),

      // list_importable_actions — Import tab AC-1 (GTaskSheet-eore). Read-only;
      // returns OPEN actions from OTHER documents in the current doc's team
      // scope (DocData join on docId -> Team Id), gated by assertTeamAccess.
      // Access failure or unknown team -> { ok:true, teamId, rows:[] }, never
      // an error leak. rows are pre-sorted by doc_name ASC then AI-N ASC, but
      // the renderer groups/sorts again per the frozen contract (epic-d-import-
      // contract-seams).
      //   Completion signal: synchronous response; GasLogger 'IMPORT_LIST.done'.
      list_importable_actions: Object.freeze({
        request:  Object.freeze(['action', 'secret', 'docId', 'clientVersion', 'caller']),
        response: Object.freeze(['ok', 'teamId', 'rows']),
        completionSignal: "synchronous response; rows scoped to current doc's team, excluding current doc"
      }),

      // forward_action_rows — Import tab AC-3 (GTaskSheet-st24). Marks each
      // imported SOURCE action as 'Forwarded' (already counted as resolved
      // via isDelegated's 'forwarded' word), appends a
      // ' [Forward:<targetDocName> AI-<n>]' suffix to its Action text, and
      // re-marks it Dirty (_remarkRowDirty) so the source document reflects
      // 'Forwarded' on the next sync_action_rows.
      //   Completion signal: synchronous response; GasLogger 'FORWARD_ROWS.done'.
      forward_action_rows: Object.freeze({
        request:  Object.freeze(['action', 'secret', 'forwards', 'targetDocName', 'clientVersion', 'caller']),
        response: Object.freeze(['ok', 'forwarded']),
        completionSignal: "synchronous response; source rows stamped Status='Forwarded' + Sync Status='Dirty'"
      }),

      // import_selected_for_test — GTaskSheet-8qe5 interactive-test-entry-point
      // (EPIC GTaskSheet-pw5x). Drives the same core logic as _submitImport's
      // AC-2/AC-3 loop (_importSelectedRows: insert chip fragment, upsert
      // ActionSheet rows, forward source rows) with an explicit globalIds
      // selection instead of CardService form-collected checkboxes. Inserts at
      // the end of the document body (_resolveEndIndex), not at a cursor.
      //   Completion signal: synchronous response; GasLogger 'IMPORT_SELECTED.done'.
      import_selected_for_test: Object.freeze({
        request:  Object.freeze(['action', 'testToken', 'testDocId', 'globalIds']),
        response: Object.freeze(['ok', 'inserted', 'baseN']),
        completionSignal: "synchronous response; same as _submitImport's IMPORT_SELECTED.done"
      }),

      // forward_action_rows_test — GTaskSheet-apcu test-only route. Same
      // forwards[]/targetDocName shape and seen[]/isResolved guard as the
      // production forward_action_rows, testToken-gated instead of
      // secret-gated so a test can pass an explicit duplicate/already-
      // resolved sourceGlobalId that _listImportableActionsData would
      // otherwise have filtered out before forward_action_rows is ever
      // called in the production flow.
      //   Completion signal: synchronous response; GasLogger 'FORWARD_ROWS_TEST.done'.
      forward_action_rows_test: Object.freeze({
        request:  Object.freeze(['action', 'testToken', 'forwards', 'targetDocName']),
        response: Object.freeze(['ok', 'forwarded']),
        completionSignal: "synchronous response; same stamping behavior as forward_action_rows"
      })
    })
  }),

  documentRead: Object.freeze({
    modelNames: Object.freeze([
      'floating_action',
      'tracker_row',
      'verification_sheet_row'
    ])
  })
});

var SHEET_HEADERS = CONTRACT_SCHEMA.sheetAction.headers.slice();