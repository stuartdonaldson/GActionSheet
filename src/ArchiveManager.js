/**
 * ArchiveManager.js
 *
 * Moves eligible rows from the "Actions" sheet to the "Archive" sheet, and
 * evicts "DocData" rows once their docId has gone Doc Not Found long enough
 * that nothing is still converging on it (gts-4tnr).
 *
 * Eligibility (DESIGN.md §Archive Manager):
 *   - Actions row: Status == "Closed" (exact, case-sensitive match) and
 *     Date Modified is more than 30 days before the current sync execution time
 *   - Actions row: Sync Status == "Doc Not Found" and Date Modified is more
 *     than 24 hours before the current sync execution time
 *     (a doc the user deleted/lost access to has nothing further to converge
 *     on; it doesn't need the 30-day grace period a normal Closed row gets)
 *   - DocData row: SyncStatus == "Doc Not Found" AND no Actions row still
 *     references that docId. Both conditions are load-bearing. A
 *     "Doc Not Found" docId can only lose all its Actions rows via the
 *     24h-gated sweep above (or explicit deletion), so this is already a
 *     24h-gated signal -- DocData doesn't need its own independent aging
 *     clock to stay in step with Actions. And "no Actions rows" on its own is
 *     NOT an eviction signal: per ADR-0031's 2026-09-01 amendment a DocData
 *     row with no live Actions rows is a normal state (a tracked document
 *     with no open actions), including one just registered by the Team Portal
 *     scan-and-track flow and not yet swept (gts-avvl).
 *
 * Actions/DocData rows are partitioned into keep/evict in one pass over a
 * single bulk read, then written back with at most two range writes per
 * sheet (no per-row appendRow/deleteRow). The whole read-modify-write is
 * wrapped in a script lock scoped to this function only, so a concurrent
 * doPost write (e.g. _handleMarkDocNotFound) can't be clobbered by the
 * archive sweep's write-back, and the lock isn't held across the rest of a
 * sync run.
 *
 * All sheet writes are wrapped in WriteGuard to suppress the onEdit trigger.
 * Date Modified is NOT altered during archival.
 */
var ArchiveManager = (function () {

  var ARCHIVE_THRESHOLD_DAYS        = 30;
  var DOC_NOT_FOUND_THRESHOLD_HOURS = 24;
  var LOCK_TIMEOUT_MS                = 30000;

  // gts-97ol: single source of truth for the test-doc naming prefix, shared
  // by _testDocName() (TestFixtures.js, which CREATES every test Doc under
  // this prefix) and purgeByPrefix below (which DELETES Actions/DocData rows
  // matching it) -- was a literal hardcoded independently in both places.
  var DEFAULT_TEST_DOC_PREFIX = 'GActionSheet-Test-';

  // Column refs resolved lazily inside the functions below — ArchiveManager.js
  // loads before ContractSchema.js alphabetically, so CONTRACT_SCHEMA is not
  // yet defined at IIFE time.

  /**
   * Converts a value to a Date, or returns null.
   *
   * @param {*} v
   * @returns {Date|null}
   */
  function _toDate(v) {
    if (!v) return null;
    if (v instanceof Date) return v;
    var d = new Date(v);
    return isNaN(d.getTime()) ? null : d;
  }

  function _ageHours(date, now) {
    return (now.getTime() - date.getTime()) / (1000 * 60 * 60);
  }

  /**
   * Shared aging predicate for both Actions rows and DocData rows: a row
   * whose syncStatus is "Doc Not Found" expires after
   * DOC_NOT_FOUND_THRESHOLD_HOURS; an Actions row whose status is "Closed"
   * expires after ARCHIVE_THRESHOLD_DAYS. Pass status as null/undefined for
   * DocData rows, which have no "Closed" concept.
   *
   * @param {string}  syncStatus
   * @param {?string} status
   * @param {*}       dateValue  Raw cell value for the row's aging timestamp.
   * @param {Date}    now
   * @returns {boolean}
   */
  function _isExpired(syncStatus, status, dateValue, now) {
    var date = _toDate(dateValue);
    if (!date) return false;
    if (syncStatus === 'Doc Not Found') return _ageHours(date, now) > DOC_NOT_FOUND_THRESHOLD_HOURS;
    if (status === 'Closed') return _ageHours(date, now) > ARCHIVE_THRESHOLD_DAYS * 24;
    return false;
  }

  /**
   * Partitions Actions rows into keep/archive from one bulk read, then writes
   * both sheets back in at most two range writes total.
   *
   * @param {Spreadsheet} ss
   * @param {Date}        now
   * @returns {number}  Count of rows archived.
   */
  function _archiveActionsRows(ss, now) {
    var _AC                = CONTRACT_SCHEMA.sheetAction.columnsByField;
    var COL_STATUS         = _AC.status;
    var COL_DATE_MODIFIED  = _AC.modified_date;
    var COL_SYNC_STATUS    = _AC.sync_status;
    var TOTAL_COLS         = SHEET_HEADERS.length;

    var actionsSheet = ss.getSheetByName('Actions');
    if (!actionsSheet) throw new Error('Actions sheet tab not found.');
    var archiveSheet = ss.getSheetByName('Archive');
    if (!archiveSheet) throw new Error('Archive sheet tab not found.');

    var lastRow = actionsSheet.getLastRow();
    if (lastRow < 2) return 0;

    var numDataRows = lastRow - 1;
    var dataRange    = actionsSheet.getRange(2, 1, numDataRows, TOTAL_COLS);
    var allValues    = dataRange.getValues();
    var allFormulas  = dataRange.getFormulas();

    var keepRows    = [];
    var archiveRows = [];

    for (var r = 0; r < numDataRows; r++) {
      var rowValues    = allValues[r];
      var rowFormulas  = allFormulas[r];
      var status       = rowValues[COL_STATUS        - 1];
      var syncStatus   = rowValues[COL_SYNC_STATUS    - 1];
      var dateModified = rowValues[COL_DATE_MODIFIED  - 1];

      // Build rowData: use formula string where one exists so that column 7's
      // HYPERLINK is preserved (getValues() would lose it to display text).
      // setValues() treats strings starting with '=' as formulas, same as appendRow().
      var rowData = rowValues.map(function (val, i) { return rowFormulas[i] ? rowFormulas[i] : val; });

      if (_isExpired(syncStatus, status, dateModified, now)) {
        archiveRows.push(rowData);
        GasLogger.log('archive.moved', {
          id: rowValues[0],
          originalDateModified: dateModified instanceof Date
            ? dateModified.toISOString()
            : String(dateModified)
        });
      } else {
        keepRows.push(rowData);
      }
    }

    if (archiveRows.length === 0) return 0;

    WriteGuard.wrap(function () {
      archiveSheet.getRange(archiveSheet.getLastRow() + 1, 1, archiveRows.length, TOTAL_COLS).setValues(archiveRows);
      var compactRange = actionsSheet.getRange(2, 1, numDataRows, TOTAL_COLS);
      compactRange.clearContent();
      // gts-a8yh.2: belt-and-suspenders — also strip any per-cell formatting
      // (e.g. a leftover RichTextValue bold/italic run on action_text) so a
      // row compacted into a new physical position starts from a clean
      // slate rather than possibly inheriting a prior occupant's styling.
      // clearFormat() (unlike a bare clear()) does not touch the Status
      // column's data validation rule.
      compactRange.clearFormat();
      if (keepRows.length > 0) {
        actionsSheet.getRange(2, 1, keepRows.length, TOTAL_COLS).setValues(keepRows);
      }
    });

    return archiveRows.length;
  }

  /**
   * Returns the set of docIds still referenced by any row in the Actions
   * sheet, keyed by docId with value true. Reuses _extractDocIdFromString
   * (WebApp.js) -- same HYPERLINK-formula docId extraction already used by
   * syncAll's docId enumeration -- rather than re-deriving the regex here.
   *
   * @param {Spreadsheet} ss
   * @returns {Object<string, boolean>}
   */
  function _collectActiveDocIds(ss) {
    var actionsSheet = ss.getSheetByName('Actions');
    if (!actionsSheet) return {};
    var lastRow = actionsSheet.getLastRow();
    if (lastRow < 2) return {};

    var colFormula = CONTRACT_SCHEMA.sheetAction.columnsByField.document_formula;
    var formulas   = actionsSheet.getRange(2, colFormula, lastRow - 1, 1).getFormulas();
    var docIds     = {};
    for (var i = 0; i < formulas.length; i++) {
      var docId = _extractDocIdFromString(formulas[i][0] || '');
      if (docId) docIds[docId] = true;
    }
    return docIds;
  }

  /**
   * Evicts a DocData row only when BOTH hold: its syncStatus is
   * "Doc Not Found" AND no Actions row still references its docId.
   *
   * The invariant (ADR-0031 amendment 2026-09-01): *absence of Actions rows is
   * not evidence that a document is gone.* A DocData row with no Actions rows
   * is a normal state -- a tracked document with no open actions -- not an
   * integrity problem. Three distinct populations share that shape and only
   * one of them is evictable:
   *
   *   - newborn: registered by the Team Portal scan-and-track flow
   *     (_handleAdminScanTrack) and not yet swept. It has never had Actions
   *     rows, so it is not aged out; it has not been looked at yet.
   *   - zero-action: swept, and the document genuinely contains no floating
   *     actions. It is tracked, and stays tracked -- untracking is an explicit
   *     operator action, never a sweep side effect.
   *   - gone: syncAll (or a doc-context sync) could not reach the document and
   *     _markDocNotFound stamped "Doc Not Found" on DocData. Only this one is
   *     evictable, and only once its Actions rows have themselves aged out via
   *     _archiveActionsRows' 24h-gated sweep above.
   *
   * gts-avvl: the predicate briefly widened to "no Actions row references this
   * docId" (gts-30cq, 2026-08-30), on the premise that such rows were
   * unreachable litter. gts-qkev falsified that premise by making syncAll walk
   * DocData directly -- every such row is now visited, reconciled, and marked
   * "Doc Not Found" if the document is actually gone -- while the scan-and-
   * track flow began minting rows that legitimately have no Actions rows at
   * all. The widened predicate destroyed three of the operator's freshly
   * tracked documents on the next sweep. Eviction is driven by the positive
   * "this document is gone" determination, never by absence.
   *
   * @param {Spreadsheet} ss
   * @returns {number}  Count of DocData rows evicted.
   */
  function _evictStaleDocData(ss) {
    var sheet = ss.getSheetByName('DocData');
    if (!sheet) return 0;
    var lastRow = sheet.getLastRow();
    if (lastRow < 2) return 0;

    var cols          = CONTRACT_SCHEMA.sheetDocData.columnsByField;
    var numCols        = CONTRACT_SCHEMA.sheetDocData.headers.length;
    var range          = sheet.getRange(2, 1, lastRow - 1, numCols);
    var values         = range.getValues();
    var formulas       = range.getFormulas();
    var activeDocIds   = _collectActiveDocIds(ss);

    var keepRows = [];
    var evicted  = 0;

    for (var r = 0; r < values.length; r++) {
      var row          = values[r];
      var rowFormulas  = formulas[r];
      var fileId       = row[cols.file_id - 1];
      var syncStatus   = row[cols.sync_status - 1];

      if (syncStatus === 'Doc Not Found' && !activeDocIds[fileId]) {
        // gts-avvl AC5: name the reason so an eviction is diagnosable from
        // Axiom without reading source. Bounded enum, not a per-doc value --
        // one column, not one per document ever evicted.
        GasLogger.log('archive.docdata_evicted', {
          fileId: fileId,
          reason: 'doc_not_found_and_no_actions_rows'
        });
        evicted++;
      } else {
        // Preserve any live formula (e.g. Doc Name's HYPERLINK) instead of
        // flattening it to display text -- same hazard/fix as
        // _archiveActionsRows above.
        var rowData = row.map(function (val, i) { return rowFormulas[i] ? rowFormulas[i] : val; });
        keepRows.push(rowData);
      }
    }

    if (evicted === 0) return 0;

    WriteGuard.wrap(function () {
      sheet.getRange(2, 1, values.length, numCols).clearContent();
      if (keepRows.length > 0) {
        sheet.getRange(2, 1, keepRows.length, numCols).setValues(keepRows);
      }
    });

    return evicted;
  }

  /**
   * Reads the Config sheet's 'Test Doc Prefix' key. Absent/blank resolves to
   * DEFAULT_TEST_DOC_PREFIX, exactly reproducing the pre-gts-97ol hardcoded
   * literal. Deliberately NOT cached across calls (unlike
   * _getContinuationIndentConfig/_getActionFormatConfig in SyncManager.js):
   * this is read once per menu click or test-doc creation, not per flush, so
   * the extra Config lookup is negligible -- and a module-level cache here
   * would reintroduce the same warm-container staleness hazard those caches
   * have (a human edit to Config sheet has no invalidation hook into a
   * cached value from an earlier GAS execution sharing the same container).
   *
   * @param {Spreadsheet} ss
   * @returns {string}
   */
  function _getTestDocPrefixConfig(ss) {
    var sheet = ss.getSheetByName('Config');
    if (!sheet) return DEFAULT_TEST_DOC_PREFIX;
    var lastRow = sheet.getLastRow();
    if (lastRow < 2) return DEFAULT_TEST_DOC_PREFIX;
    var cols   = CONTRACT_SCHEMA.sheetConfig.columnsByField;
    var values = sheet.getRange(2, 1, lastRow - 1, CONTRACT_SCHEMA.sheetConfig.headers.length).getValues();
    for (var i = 0; i < values.length; i++) {
      if (values[i][cols.key - 1] !== 'Test Doc Prefix') continue;
      var raw = String(values[i][cols.value - 1] || '').trim();
      return raw || DEFAULT_TEST_DOC_PREFIX;
    }
    return DEFAULT_TEST_DOC_PREFIX;
  }

  /**
   * Partitions Actions rows and DocData rows by whether their doc_name
   * STARTS WITH `prefix` (not merely contains it). Actions' doc_name is
   * derived from the document_formula HYPERLINK (col 8) via the existing
   * _extractDocNameFromFormula (WebApp.js) -- same extraction ArchiveManager
   * already trusts nowhere else in this file, but the sibling doc_id
   * extractor (_collectActiveDocIds above) sets the precedent of reusing
   * WebApp.js's formula parsers rather than re-deriving them here. DocData's
   * doc_name is a plain column (CONTRACT_SCHEMA.sheetDocData.columnsByField),
   * no formula involved.
   *
   * `apply=false` is a dry-run: computes match counts only, no sheet write --
   * used for the pre-delete confirmation count. `apply=true` performs the
   * same two-range write-back shape as _archiveActionsRows/_evictStaleDocData
   * (compact keep-rows, clear-then-rewrite), wrapped by the caller in
   * WriteGuard + a script lock (see purgeByPrefix below).
   *
   * A blank/empty `prefix` matches every row via a naive startsWith -- this
   * function refuses that case unconditionally (returns zero matches, no
   * write) rather than trust every caller to have already guarded it.
   *
   * @param {Spreadsheet} ss
   * @param {string} prefix
   * @param {boolean} apply
   * @returns {{actionsMatched: number, docDataMatched: number}}
   */
  function _purgeByPrefix(ss, prefix, apply) {
    if (!prefix) return { actionsMatched: 0, docDataMatched: 0 };

    var actionsSheet = ss.getSheetByName('Actions');
    var actionsMatched = 0;
    if (actionsSheet) {
      var lastRow = actionsSheet.getLastRow();
      if (lastRow >= 2) {
        var _AC        = CONTRACT_SCHEMA.sheetAction.columnsByField;
        var TOTAL_COLS = SHEET_HEADERS.length;
        var numDataRows = lastRow - 1;
        var dataRange   = actionsSheet.getRange(2, 1, numDataRows, TOTAL_COLS);
        var allValues   = dataRange.getValues();
        var allFormulas = dataRange.getFormulas();
        var keepRows    = [];

        for (var r = 0; r < numDataRows; r++) {
          var rowValues   = allValues[r];
          var rowFormulas = allFormulas[r];
          var docName     = _extractDocNameFromFormula(rowFormulas[_AC.document_formula - 1] || '');
          var rowData     = rowValues.map(function (val, i) { return rowFormulas[i] ? rowFormulas[i] : val; });

          if (docName.indexOf(prefix) === 0) {
            actionsMatched++;
          } else {
            keepRows.push(rowData);
          }
        }

        if (apply && actionsMatched > 0) {
          WriteGuard.wrap(function () {
            var compactRange = actionsSheet.getRange(2, 1, numDataRows, TOTAL_COLS);
            compactRange.clearContent();
            compactRange.clearFormat();
            if (keepRows.length > 0) {
              actionsSheet.getRange(2, 1, keepRows.length, TOTAL_COLS).setValues(keepRows);
            }
          });
        }
      }
    }

    var docDataSheet = ss.getSheetByName('DocData');
    var docDataMatched = 0;
    if (docDataSheet) {
      var ddLastRow = docDataSheet.getLastRow();
      if (ddLastRow >= 2) {
        var ddCols    = CONTRACT_SCHEMA.sheetDocData.columnsByField;
        var ddNumCols = CONTRACT_SCHEMA.sheetDocData.headers.length;
        var ddRange   = docDataSheet.getRange(2, 1, ddLastRow - 1, ddNumCols);
        var ddValues  = ddRange.getValues();
        var ddFormulas = ddRange.getFormulas();
        var ddKeepRows = [];

        for (var dr = 0; dr < ddValues.length; dr++) {
          var ddRowValues   = ddValues[dr];
          var ddRowFormulas = ddFormulas[dr];
          var ddDocName     = String(ddRowValues[ddCols.doc_name - 1] || '');
          var ddRowData     = ddRowValues.map(function (val, i) { return ddRowFormulas[i] ? ddRowFormulas[i] : val; });

          if (ddDocName.indexOf(prefix) === 0) {
            docDataMatched++;
          } else {
            ddKeepRows.push(ddRowData);
          }
        }

        if (apply && docDataMatched > 0) {
          WriteGuard.wrap(function () {
            docDataSheet.getRange(2, 1, ddValues.length, ddNumCols).clearContent();
            if (ddKeepRows.length > 0) {
              docDataSheet.getRange(2, 1, ddKeepRows.length, ddNumCols).setValues(ddKeepRows);
            }
          });
        }
      }
    }

    return { actionsMatched: actionsMatched, docDataMatched: docDataMatched };
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  return {
    /**
     * Archives eligible rows from the "Actions" sheet to the "Archive" sheet,
     * then evicts every DocData row that is BOTH marked "Doc Not Found" and no
     * longer referenced by any Actions row (gts-avvl -- absence of Actions
     * rows alone is not an eviction signal; see _evictStaleDocData). The
     * read-modify-write is wrapped in a script lock scoped to this call only.
     *
     * @param {Spreadsheet} ss  The active spreadsheet object.
     * @returns {number}  Count of Actions rows archived.
     */
    archive: function (ss) {
      var now = new Date();
      var lock = LockService.getScriptLock();
      var actionsArchived, docDataEvicted;

      lock.waitLock(LOCK_TIMEOUT_MS);
      try {
        actionsArchived = _archiveActionsRows(ss, now);
        docDataEvicted  = _evictStaleDocData(ss);
      } finally {
        lock.releaseLock();
      }

      GasLogger.log('archive.complete', { count: actionsArchived, docDataEvicted: docDataEvicted });
      return actionsArchived;
    },

    /**
     * gts-97ol: the configured 'Test Doc Prefix' (Config sheet), or
     * DEFAULT_TEST_DOC_PREFIX when absent/blank. Shared by _testDocName()
     * (TestFixtures.js, creation) and purgeByPrefix (deletion) so both sides
     * of the test-doc lifecycle agree on one prefix.
     *
     * @param {Spreadsheet} ss
     * @returns {string}
     */
    getConfiguredTestDocPrefix: function (ss) {
      return _getTestDocPrefixConfig(ss);
    },

    /**
     * gts-97ol: deletes (never archives) every Actions row and DocData row
     * whose doc_name starts with `prefix`. `apply=false` is a count-only dry
     * run (no write) for a pre-delete confirmation; `apply=true` performs
     * the deletion, wrapped in the same script-lock convention as archive()
     * above. A blank/empty `prefix` always matches zero rows (see
     * _purgeByPrefix) -- this is not merely a caller contract, it is
     * enforced here regardless of what apply is.
     *
     * @param {Spreadsheet} ss
     * @param {string} prefix
     * @param {boolean} apply
     * @returns {{actionsMatched: number, docDataMatched: number}}
     */
    purgeByPrefix: function (ss, prefix, apply) {
      var lock = LockService.getScriptLock();
      var result;
      lock.waitLock(LOCK_TIMEOUT_MS);
      try {
        result = _purgeByPrefix(ss, prefix, apply);
      } finally {
        lock.releaseLock();
      }
      return result;
    }
  };
})();
