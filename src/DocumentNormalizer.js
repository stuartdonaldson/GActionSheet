/**
 * DocumentNormalizer.js
 *
 * Normalizes a Google Doc:
 *  - Ensures the tracked-actions section (=== Tracked Actions ===) exists.
 *  - Ensures the tracked-actions table exists inside that section.
 *  - Assigns IDs to unnumbered floating actions.
 *  - Rewrites floating-action paragraphs with normalized values.
 *  - Upserts rows in the tracked-actions table.
 *
 * Normalization rules (requirements §10):
 *  - If same ID appears in both floating action and table, the side with the
 *    later dateModified wins. If one side has no dateModified, the timestamped
 *    side wins. If neither has a timestamp, the table row wins.
 *  - After normalization every floating action is rewritten to reflect the
 *    winning values.
 *
 * Returns an IIFE exposing { normalize }.
 */
var DocumentNormalizer = (function () {

  /** Exact heading text for the tracked-actions section (requirements §5). */
  var SECTION_HEADING = '=== Tracked Actions ===';

  /** Headers for the tracked-actions table (requirements §6). */
  var TABLE_HEADERS = [
    'ID',
    'Assignee Email',
    'Assignee Name',
    'Action',
    'Status',
    'Date Created',
    'Date Modified'
  ];

  /** Heading paragraph styles counted as section boundaries (requirements §5.3). */
  var HEADING_STYLES = [
    DocumentApp.ParagraphHeading.HEADING1,
    DocumentApp.ParagraphHeading.HEADING2,
    DocumentApp.ParagraphHeading.HEADING3,
    DocumentApp.ParagraphHeading.HEADING4,
    DocumentApp.ParagraphHeading.HEADING5,
    DocumentApp.ParagraphHeading.HEADING6
  ];

  /**
   * Returns true if the paragraph element uses a heading style.
   * @param {Paragraph} para
   * @returns {boolean}
   */
  function _isHeading(para) {
    var heading = para.getHeading();
    for (var i = 0; i < HEADING_STYLES.length; i++) {
      if (heading === HEADING_STYLES[i]) return true;
    }
    return false;
  }

  /**
   * Formats a Date (or null) as an ISO 8601 string, or '' if null.
   * @param {Date|null} d
   * @returns {string}
   */
  function _isoOrEmpty(d) {
    if (!d) return '';
    return d.toISOString();
  }

  /**
   * Selects the winning action record between a floating action and a table
   * record, per requirements §10.4–10.6.
   *
   * @param {object} floating  Floating action object (or null).
   * @param {object} tableRec  Table record object (or null).
   * @returns {object} The winning record.
   */
  function _resolveConflict(floating, tableRec) {
    if (!floating) return tableRec;
    if (!tableRec) return floating;

    var fm = floating.dateModified;
    var tm = tableRec.dateModified;

    if (fm && tm) {
      return fm.getTime() >= tm.getTime() ? floating : tableRec;
    }
    if (fm && !tm) return floating;
    if (!fm && tm) return tableRec;
    // Neither has a modified timestamp — table wins (§10.6).
    return tableRec;
  }

  // ---------------------------------------------------------------------------
  // Tracked-actions section / table helpers
  // ---------------------------------------------------------------------------

  /**
   * Finds the tracked-actions section heading paragraph index, or -1.
   * Also validates that at most one such section exists (requirements §5.4 / §5.7).
   *
   * @param {Body} body
   * @returns {number} Index into body.getParagraphs() of the heading, or -1.
   */
  function _findSectionHeadingIndex(body) {
    var paras = body.getParagraphs();
    var found = -1;
    for (var i = 0; i < paras.length; i++) {
      if (paras[i].getText() === SECTION_HEADING) {
        if (found >= 0) {
          throw new Error('Document contains more than one tracked-actions section.');
        }
        found = i;
      }
    }
    return found;
  }

  /**
   * Creates the tracked-actions section heading at the end of the body.
   * Appends a blank paragraph first to ensure separation from existing content.
   *
   * @param {Body} body
   * @returns {Paragraph} The created heading paragraph.
   */
  function _createSectionHeading(body) {
    var heading = body.appendParagraph(SECTION_HEADING);
    heading.setHeading(DocumentApp.ParagraphHeading.HEADING1);
    return heading;
  }

  /**
   * Builds a column-index map from the header row of a table.
   * Throws if any required header is missing.
   *
   * @param {Table} table
   * @returns {Object} Map of header name → zero-based column index.
   */
  function _buildColMap(table) {
    var headerRow = table.getRow(0);
    var map = {};
    for (var c = 0; c < headerRow.getNumCells(); c++) {
      map[headerRow.getCell(c).getText().trim()] = c;
    }
    for (var h = 0; h < TABLE_HEADERS.length; h++) {
      if (!(TABLE_HEADERS[h] in map)) {
        throw new Error('Tracked-actions table is missing required header: ' + TABLE_HEADERS[h]);
      }
    }
    return map;
  }

  /**
   * Reads all rows from the tracked-actions table (skipping the header row).
   *
   * @param {Table} table
   * @param {Object} colMap  Column-index map from _buildColMap.
   * @returns {Object} Map of integer ID → action record object.
   */
  function _readTableRows(table, colMap) {
    var records = {};
    for (var r = 1; r < table.getNumRows(); r++) {
      var row = table.getRow(r);
      var idStr = row.getCell(colMap['ID']).getText().trim();
      if (!idStr) continue;
      var id = parseInt(idStr, 10);
      if (isNaN(id)) continue;

      var dcStr = row.getCell(colMap['Date Created']).getText().trim();
      var dmStr = row.getCell(colMap['Date Modified']).getText().trim();
      var rec = {
        id: id,
        assigneeEmail: row.getCell(colMap['Assignee Email']).getText().trim(),
        assigneeName: row.getCell(colMap['Assignee Name']).getText().trim(),
        action: row.getCell(colMap['Action']).getText().trim(),
        status: row.getCell(colMap['Status']).getText().trim(),
        dateCreated: dcStr ? new Date(dcStr) : null,
        dateModified: dmStr ? new Date(dmStr) : null
      };

      if (id in records) {
        throw new Error('Duplicate ID ' + id + ' in tracked-actions table.');
      }
      records[id] = rec;
    }
    return records;
  }

  /**
   * Finds the tracked-actions table inside the section bounded by the heading
   * at sectionParaIdx and the next heading (or end of body).
   *
   * Returns null if no table is found in the section.
   *
   * @param {Body} body
   * @param {number} sectionParaIdx
   * @returns {Table|null}
   */
  function _findTableInSection(body, sectionParaIdx) {
    var paras = body.getParagraphs();
    // Determine the end boundary of the section.
    var sectionEnd = paras.length;
    for (var i = sectionParaIdx + 1; i < paras.length; i++) {
      if (_isHeading(paras[i]) && paras[i].getText() !== SECTION_HEADING) {
        sectionEnd = i;
        break;
      }
    }

    // Walk the body children to find a Table element that sits after the
    // section heading and before sectionEnd.
    // We map paragraph indices to body child indices by scanning.
    var numChildren = body.getNumChildren();
    var paraCounter = 0;
    var inSection = false;

    for (var ci = 0; ci < numChildren; ci++) {
      var child = body.getChild(ci);
      var childType = child.getType();

      if (childType === DocumentApp.ElementType.PARAGRAPH) {
        if (paraCounter === sectionParaIdx) {
          inSection = true;
        } else if (paraCounter >= sectionEnd) {
          inSection = false;
        }
        paraCounter++;
      } else if (childType === DocumentApp.ElementType.TABLE) {
        if (inSection) {
          return child.asTable();
        }
      }
    }

    return null;
  }

  /**
   * Creates an empty tracked-actions table with the header row at the end of
   * the body (after the section heading already exists).
   *
   * @param {Body} body
   * @returns {Table}
   */
  function _createTable(body) {
    // appendTable with a 2D array creates header + one placeholder data row.
    // We pass just the headers and one empty row (GAS requires at least 1 data row).
    var tableData = [TABLE_HEADERS, new Array(TABLE_HEADERS.length).join(',').split(',')];
    // Build as array-of-arrays: header row + one blank row.
    var blank = [];
    for (var i = 0; i < TABLE_HEADERS.length; i++) {
      blank.push('');
    }
    var table = body.appendTable([TABLE_HEADERS, blank]);
    // Make the header row bold.
    var headerRow = table.getRow(0);
    for (var c = 0; c < TABLE_HEADERS.length; c++) {
      headerRow.getCell(c).setText(TABLE_HEADERS[c]);
      headerRow.getCell(c).setBackgroundColor('#D9D9D9');
    }
    return table;
  }

  /**
   * Upserts an action record into the tracked-actions table.
   * Inserts a new row if the ID is not found; updates the existing row if found.
   *
   * @param {Table} table
   * @param {Object} colMap
   * @param {object} action  Normalized action record.
   */
  function _upsertTableRow(table, colMap, action) {
    var idStr = String(action.id);
    var targetRow = -1;

    for (var r = 1; r < table.getNumRows(); r++) {
      if (table.getRow(r).getCell(colMap['ID']).getText().trim() === idStr) {
        targetRow = r;
        break;
      }
    }

    var row;
    if (targetRow < 0) {
      // Insert a new row at the end.
      row = table.appendTableRow();
      // Ensure the row has the right number of cells.
      while (row.getNumCells() < TABLE_HEADERS.length) {
        row.appendTableCell('');
      }
    } else {
      row = table.getRow(targetRow);
    }

    row.getCell(colMap['ID']).setText(idStr);
    row.getCell(colMap['Assignee Email']).setText(action.assigneeEmail || '');
    row.getCell(colMap['Assignee Name']).setText(action.assigneeName || '');
    row.getCell(colMap['Action']).setText(action.action || '');
    row.getCell(colMap['Status']).setText(action.status || '');
    row.getCell(colMap['Date Created']).setText(_isoOrEmpty(action.dateCreated));
    row.getCell(colMap['Date Modified']).setText(_isoOrEmpty(action.dateModified));
  }

  /**
   * Rewrites the text of a floating-action paragraph to reflect normalized
   * values, preserving the paragraph's existing style (requirements §10.8).
   *
   * @param {Paragraph} para
   * @param {object} action   Normalized action record.
   * @param {string} originalAssigneeToken  The original assignee token text.
   */
  function _rewriteParagraph(para, action, originalAssigneeToken) {
    var newText = 'AI-' + action.id + ' ' + originalAssigneeToken
      + ' | ' + (action.action || '')
      + ' | ' + (action.status || '')
      + ' | ' + _isoOrEmpty(action.dateCreated)
      + ' | ' + _isoOrEmpty(action.dateModified);
    para.setText(newText);
  }

  /**
   * Extracts the original assignee token string from a paragraph's text,
   * given the post-prefix portion (text after 'AI-N ').
   *
   * Returns the token as it appears in the original text.
   *
   * @param {string} postPrefix  Text after the AI- prefix and integer.
   * @returns {string}
   */
  function _extractOriginalAssigneeToken(postPrefix) {
    // The assignee token ends at the first ' | ' or end-of-string.
    var pipeIdx = postPrefix.indexOf(' | ');
    if (pipeIdx >= 0) {
      return postPrefix.slice(0, pipeIdx).trim();
    }
    return postPrefix.trim();
  }

  /**
   * Returns the next available ID given the current maximum.
   * @param {number} maxExisting  Current maximum ID (0 if none exist).
   * @returns {number}
   */
  function _nextId(maxExisting) {
    return maxExisting + 1;
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  return {
    /**
     * Normalizes the document: assigns IDs to unnumbered floating actions,
     * ensures the tracked-actions section and table exist, upserts rows, and
     * rewrites floating-action paragraphs.
     *
     * @param {Document} doc              Open DocumentApp Document.
     * @param {number[]} existingSheetIds Array of integer IDs already in the sheet.
     * @returns {Array} Array of normalized action objects:
     *   { id, assigneeEmail, assigneeName, action, status,
     *     dateCreated, dateModified, docId, docTitle, docUrl }
     */
    normalize: function (doc, existingSheetIds) {
      var body = doc.getBody();
      var docId = doc.getId();
      var docTitle = doc.getName();
      var docUrl = doc.getUrl();
      var syncTime = new Date();

      // 1. Parse all floating actions.
      var floatingActions = FloatingActionParser.parse(doc);

      // 2. Locate or create the tracked-actions section.
      var sectionIdx = _findSectionHeadingIndex(body);
      if (sectionIdx < 0) {
        _createSectionHeading(body);
        sectionIdx = _findSectionHeadingIndex(body);
      }

      // 3. Locate or create the tracked-actions table.
      var table = _findTableInSection(body, sectionIdx);
      if (!table) {
        table = _createTable(body);
      }

      // 4. Build column map and read existing table records.
      var colMap = _buildColMap(table);
      var tableRecords = _readTableRows(table, colMap);

      // 5. Determine next available ID.
      //    Max of: IDs in table + IDs in sheet + IDs from floating actions that already have IDs.
      var maxId = 0;
      var id;
      for (id in tableRecords) {
        if (tableRecords.hasOwnProperty(id)) {
          var tableId = parseInt(id, 10);
          if (tableId > maxId) maxId = tableId;
        }
      }
      for (var si = 0; si < existingSheetIds.length; si++) {
        if (existingSheetIds[si] > maxId) maxId = existingSheetIds[si];
      }
      for (var fi = 0; fi < floatingActions.length; fi++) {
        if (floatingActions[fi].id !== null && floatingActions[fi].id > maxId) {
          maxId = floatingActions[fi].id;
        }
      }

      // 6. Assign IDs to unnumbered floating actions and resolve conflicts.
      var normalizedById = {};

      // First, seed normalizedById from table records.
      for (var tid in tableRecords) {
        if (tableRecords.hasOwnProperty(tid)) {
          normalizedById[parseInt(tid, 10)] = tableRecords[tid];
        }
      }

      // Process floating actions.
      var body_paras = body.getParagraphs();
      for (var fai = 0; fai < floatingActions.length; fai++) {
        var fa = floatingActions[fai];

        // Assign ID if missing.
        if (fa.id === null) {
          maxId = _nextId(maxId);
          fa.id = maxId;
        }

        // Apply timestamp defaults (requirements §9.6–9.7).
        if (!fa.dateCreated && !fa.dateModified) {
          fa.dateCreated = syncTime;
          fa.dateModified = syncTime;
        } else if (fa.dateCreated && !fa.dateModified) {
          fa.dateModified = fa.dateCreated;
        }

        // Resolve conflict with any existing table record.
        var existing = normalizedById[fa.id] || null;
        var winner = _resolveConflict(fa, existing);
        // Preserve the winning ID.
        winner.id = fa.id;
        normalizedById[fa.id] = winner;

        // Rewrite the floating-action paragraph using the winner's values.
        var para = body_paras[fa.paragraphIndex];
        var paraText = para.getText();
        // Extract original assignee token from paragraph text.
        var AI_PREFIX_RE = /^AI-(\d*)\s+/;
        var prefixMatch = AI_PREFIX_RE.exec(paraText);
        var postPrefix = prefixMatch ? paraText.slice(prefixMatch[0].length) : paraText;
        var originalToken = _extractOriginalAssigneeToken(postPrefix);
        _rewriteParagraph(para, winner, originalToken);
      }

      // 7. Also include any table-only records (not referenced by a floating action).
      // They are already in normalizedById from step 6 seeding.

      // 8. Upsert all normalized records into the tracked-actions table.
      for (var nid in normalizedById) {
        if (normalizedById.hasOwnProperty(nid)) {
          _upsertTableRow(table, colMap, normalizedById[parseInt(nid, 10)]);
        }
      }

      // 9. Build and return the output array.
      var result = [];
      for (var rid in normalizedById) {
        if (normalizedById.hasOwnProperty(rid)) {
          var rec = normalizedById[parseInt(rid, 10)];
          result.push({
            id: rec.id,
            assigneeEmail: rec.assigneeEmail,
            assigneeName: rec.assigneeName,
            action: rec.action,
            status: rec.status,
            dateCreated: rec.dateCreated,
            dateModified: rec.dateModified,
            docId: docId,
            docTitle: docTitle,
            docUrl: docUrl
          });
        }
      }

      return result;
    },

    /**
     * Rewrites floating-action paragraphs and table rows for actions where the
     * sheet won the conflict resolution (sheet values override doc values).
     *
     * Called after SheetReconciler.reconcile() returns sheetWins actions.
     *
     * @param {Document} doc      The open Google Doc.
     * @param {Array}    actions  Array of action objects with sheet-winning values.
     */
    applySheetWins: function (doc, actions) {
      if (!actions || actions.length === 0) return;

      var body = doc.getBody();
      var body_paras = body.getParagraphs();

      // Build a lookup of floating actions by ID to find their paragraph indices.
      var parsed = FloatingActionParser.parse(doc);
      var paraByID = {};
      for (var p = 0; p < parsed.length; p++) {
        if (parsed[p].id !== null) {
          paraByID[parsed[p].id] = body_paras[parsed[p].paragraphIndex];
        }
      }

      // Locate the tracked-actions table.
      var sectionIdx = _findSectionHeadingIndex(body);
      var table = sectionIdx >= 0 ? _findTableInSection(body, sectionIdx) : null;

      for (var a = 0; a < actions.length; a++) {
        var action = actions[a];

        // Rewrite the floating-action paragraph if present.
        if (paraByID[action.id]) {
          var para = paraByID[action.id];
          var paraText = para.getText();
          var AI_PREFIX_RE = /^AI-(\d*)\s+/;
          var prefixMatch = AI_PREFIX_RE.exec(paraText);
          var postPrefix = prefixMatch ? paraText.slice(prefixMatch[0].length) : paraText;
          var originalToken = _extractOriginalAssigneeToken(postPrefix);
          _rewriteParagraph(para, action, originalToken);
        }

        // Update the table row if the table exists.
        if (table) {
          var colMap = _buildColMap(table);
          _upsertTableRow(table, colMap, action);
        }
      }

      GasLogger.log('sync.sheetWins.applied', { count: actions.length });
    }
  };
})();
