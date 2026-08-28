/**
 * PortableText.js
 *
 * Encode/decode between a Google Doc's body paragraphs and Action Portable
 * Text (APT) — a round-trippable, git-diffable text serialization used to
 * check a human-authored canonical reference doc into git as plain text and
 * to regenerate it if lost. Format spec: docs/interfaces/action-portable-text.md
 * (gts-colw, ADR-0027 rule 16).
 *
 * encodeDocToApt(doc)         -> string   (Doc -> APT, "encode")
 * decodeAptIntoDoc(doc, apt)  -> void      (APT -> Doc content, "decode")
 *
 * Both are pure with respect to everything except the Doc argument they are
 * given — no dependency on the Actions sheet, ContractSchema, or any other
 * sync-path state. decodeAptIntoDoc assumes an EMPTY doc body (append-only);
 * it is not a patch/merge operation.
 */

// ---------------------------------------------------------------------------
// Shared constants
// ---------------------------------------------------------------------------

var _APT_SR    = '<SR>';
var _APT_EMPTY = '<EMPTY>';
var _APT_BLANK = '<BLANK>';
var _APT_ESCAPE_CHARS = ['\\', '*', '_', '[', ']', '<', '>', '{', '}'];

// APT v2 (gts-83s5) — list-item and table-cell containers.
var _APT_LI_PREFIX  = '<LI> ';
var _APT_TABLE_OPEN_RE  = /^<TABLE rows=(\d+) cols=(\d+)>$/;
var _APT_TABLE_CLOSE    = '</TABLE>';
var _APT_CELL_RE        = /^<CELL (\d+),(\d+)>$/;

function _aptEscape(text) {
  var out = '';
  for (var i = 0; i < text.length; i++) {
    var c = text[i];
    if (_APT_ESCAPE_CHARS.indexOf(c) !== -1) out += '\\' + c;
    else out += c;
  }
  return out;
}

// ---------------------------------------------------------------------------
// Encode: Doc -> APT
// ---------------------------------------------------------------------------

/**
 * @param {Document} doc
 * @param {{kind: (string|undefined), name: (string|undefined),
 *          serves: (string|undefined)}=} opts Structured-header overrides
 *   (gts-x9un). A raw encode of a live Doc is a *capture* by definition
 *   (Terminology, staged plan) — `kind` defaults to 'capture' and only a
 *   future `bless` (scripts/apt.py, stage apt-cli) is expected to pass
 *   `kind: 'golden'`, since bless is the only writer of a golden (decision
 *   1). `name`/`serves` are opaque strings this function never inspects.
 * @return {string} APT text, including a generated structured preamble.
 */
function encodeDocToApt(doc, opts) {
  var body = doc.getBody();
  var n = body.getNumChildren();
  var records = [];
  for (var i = 0; i < n; i++) {
    var el = body.getChild(i);
    var type = el.getType();
    if (type === DocumentApp.ElementType.TABLE) {
      records = records.concat(_aptEncodeTable(el.asTable()));
      continue;
    }
    if (type !== DocumentApp.ElementType.PARAGRAPH &&
        type !== DocumentApp.ElementType.LIST_ITEM) continue;
    records.push(_aptEncodeParagraph(el));
  }
  opts = opts || {};
  var headerLines = [];
  headerLines.push('<!-- kind: ' + (opts.kind || 'capture') + ' -->');
  if (opts.name) headerLines.push('<!-- name: ' + opts.name + ' -->');
  headerLines.push('<!-- doc: ' + doc.getId() + ' -->');
  if (opts.serves) headerLines.push('<!-- serves: ' + opts.serves + ' -->');
  headerLines.push('<!-- generated: ' + new Date().toISOString() + ' -->');
  return headerLines.join('\n') + '\n\n' + records.join('\n\n') + '\n';
}

/**
 * Encodes one Table element (gts-83s5, APT v2) to a flat sequence of
 * structural-marker + paragraph records: `<TABLE rows=R cols=C>`, then for
 * each cell in row-major order a `<CELL r,c>` marker followed by that cell's
 * own paragraph/list-item records (via _aptEncodeParagraph — a cell's
 * content is ordinary paragraph content, so list items inside a cell reuse
 * the same `<LI>` marker), then `</TABLE>`.
 *
 * v2 restriction (see format spec "Tables" section): a body-level table
 * must be the LAST top-level element(s) in the doc for the round trip to
 * hold — decodeAptIntoDoc always appends table content after all top-level
 * paragraph content, since building it requires a second Docs-API round
 * trip to discover the cells' real indices (Table structural indices are
 * not predictable from a single batchUpdate the way flat paragraph text
 * is). No nested tables — a cell containing a TABLE is not supported (v1's
 * "not a general Docs serialization" non-goal still holds).
 */
function _aptEncodeTable(table) {
  var numRows = table.getNumRows();
  var numCols = numRows > 0 ? table.getRow(0).getNumCells() : 0;
  var records = ['<TABLE rows=' + numRows + ' cols=' + numCols + '>'];
  for (var r = 0; r < numRows; r++) {
    var row = table.getRow(r);
    for (var c = 0; c < row.getNumCells(); c++) {
      records.push('<CELL ' + r + ',' + c + '>');
      var cell = row.getCell(c);
      var cellChildren = cell.getNumChildren();
      for (var ci = 0; ci < cellChildren; ci++) {
        var child = cell.getChild(ci);
        var childType = child.getType();
        if (childType === DocumentApp.ElementType.TABLE) {
          throw new Error('PortableText encode: nested tables are not supported (APT v2 non-goal)');
        }
        if (childType !== DocumentApp.ElementType.PARAGRAPH &&
            childType !== DocumentApp.ElementType.LIST_ITEM) continue;
        records.push(_aptEncodeParagraph(child));
      }
    }
  }
  records.push('</TABLE>');
  return records;
}

/**
 * Encodes one paragraph/list-item element to its APT record body (no
 * surrounding blank-line separators — the caller joins records). A
 * LIST_ITEM (gts-83s5, APT v2) is prefixed on its first physical line with
 * the `<LI> ` marker; nesting level is not encoded — v2 supports only
 * flat (single-level) lists, matching every current use case
 * (test_floating_action_scanner.py AC-1/AC-2/AC-5).
 */
function _aptEncodeParagraph(para) {
  var isListItem = para.getType() === DocumentApp.ElementType.LIST_ITEM;
  var numChildren = para.getNumChildren();
  var lines = ['']; // lines[k] accumulates physical line k's marked-up text
  var sawAnyContent = false;

  for (var ci = 0; ci < numChildren; ci++) {
    var ch = para.getChild(ci);
    var type = ch.getType();
    if (type === DocumentApp.ElementType.INLINE_IMAGE) {
      // Status icon (or any other inline image) is never encoded — rule 8:
      // system-applied presentation is not stored author intent.
      continue;
    }
    if (type === DocumentApp.ElementType.PERSON) {
      sawAnyContent = true;
      var email = ch.asPerson().getEmail() || '';
      lines[lines.length - 1] += '{{chip:' + email + '}}';
      continue;
    }
    if (type !== DocumentApp.ElementType.TEXT) continue;
    var textEl = ch.asText();
    var raw = textEl.getText();
    if (!raw.length) continue;
    sawAnyContent = true;

    // Split this child's text into physical lines on \r/\v (soft return),
    // matching _normalizeLineEndings' treatment of both spellings as one
    // line-break concept. Track each line's offset into raw so run queries
    // (isBold/isItalic/getLinkUrl) land on the correct original character.
    var lineStart = 0;
    for (var pos = 0; pos <= raw.length; pos++) {
      var atBreak = pos === raw.length || raw[pos] === '\r' || raw[pos] === '\v';
      if (!atBreak) continue;
      var lineText = raw.slice(lineStart, pos);
      lines[lines.length - 1] += _aptRenderRun(textEl, lineText, lineStart);
      if (pos < raw.length) lines.push(''); // soft return: start a new physical line
      lineStart = pos + 1;
    }
  }

  if (!sawAnyContent) {
    return isListItem ? _APT_LI_PREFIX + _APT_EMPTY : _APT_EMPTY;
  }

  var out = [];
  for (var li = 0; li < lines.length; li++) {
    var text = lines[li] === '' ? _APT_BLANK : lines[li];
    out.push(li < lines.length - 1 ? text + _APT_SR : text);
  }
  if (isListItem) out[0] = _APT_LI_PREFIX + out[0];
  return out.join('\n');
}

/**
 * Renders one contiguous run of plain (already soft-return-free) text from a
 * single Text element, applying bold/italic/link markup with coalescing —
 * mirrors _extractInlineRuns' "adjacent same-styled characters merge" rule —
 * and backslash-escaping every literal APT syntax character.
 *
 * @param {Text}   textEl    the child Text element (style queries are
 *                           relative to ITS OWN offsets)
 * @param {string} lineText  the physical-line substring to render
 * @param {number} baseOffset offset of lineText[0] within textEl's own text
 */
function _aptRenderRun(textEl, lineText, baseOffset) {
  if (!lineText.length) return '';
  var out = '';
  var i = 0;
  while (i < lineText.length) {
    var off = baseOffset + i;
    var bold = textEl.isBold(off) || false;
    var italic = textEl.isItalic(off) || false;
    var link = textEl.getLinkUrl(off) || null;
    var j = i + 1;
    while (j < lineText.length) {
      var off2 = baseOffset + j;
      if ((textEl.isBold(off2) || false) !== bold) break;
      if ((textEl.isItalic(off2) || false) !== italic) break;
      if ((textEl.getLinkUrl(off2) || null) !== link) break;
      j++;
    }
    var chunk = _aptEscape(lineText.slice(i, j));
    if (bold && italic) chunk = '**_' + chunk + '_**';
    else if (bold) chunk = '**' + chunk + '**';
    else if (italic) chunk = '_' + chunk + '_';
    if (link) chunk = '[' + chunk + '](' + link + ')';
    out += chunk;
    i = j;
  }
  return out;
}

// ---------------------------------------------------------------------------
// Decode: APT -> Doc content
// ---------------------------------------------------------------------------

// PERSON chips cannot be created through DocumentApp's high-level API, and
// DocumentApp#appendText silently mangles a literal U+000B soft-return
// character (confirmed empirically — it round-trips as a plain space). The
// project's one existing chip writer (TrackerTable.js's
// _insertTrackerAssigneeChips) and the one soft-return writer
// (_toSoftReturnText/_buildFlushRequests) both already go through the raw
// Docs REST API `insertText`/`insertPerson` batchUpdate requests instead of
// DocumentApp for exactly this reason. decodeAptIntoDoc follows the same
// path: compute the ENTIRE body text plus every chip/style position as plain
// offsets first, then apply it all as one batchUpdate against the target
// (empty) doc.

/**
 * Parses `apt` and writes every record into `doc`'s body as a fresh
 * paragraph, via the Docs REST API. The doc's body is assumed EMPTY (or
 * containing only the default single empty paragraph GAS gives every new
 * Doc) — this is an append-only regeneration, not a merge/patch of existing
 * content.
 *
 * @param {Document} doc
 * @param {string}   apt
 */
function decodeAptIntoDoc(doc, apt) {
  var docId = doc.getId();
  doc.saveAndClose(); // release the DocumentApp lock; everything below is REST-only
  var records = _aptSplitRecords(apt);
  var blocks = _aptParseBlocks(records);

  var paragraphRecords = [];
  var tableBlocks = [];
  var sawTable = false;
  for (var bi = 0; bi < blocks.length; bi++) {
    var block = blocks[bi];
    if (block.type === 'table') {
      sawTable = true;
      tableBlocks.push(block);
      continue;
    }
    if (sawTable) {
      // Google Docs itself never lets a table be the body's final element —
      // it silently appends an empty paragraph after one that would
      // otherwise be last. An `<EMPTY>` record here documents that real,
      // unavoidable outcome (so encode(decode(x)) == x still holds); decode
      // does nothing for it, since Docs creates it as a side effect of
      // insertTable. Anything else after a table is the ordering
      // restriction's actual violation.
      if (block.record !== _APT_EMPTY) {
        throw new Error('PortableText decode: a body-level table must be the LAST top-level ' +
          'element in the doc, aside from the single trailing <EMPTY> Docs itself requires ' +
          '(APT v2 restriction — see format spec "Tables")');
      }
      continue;
    }
    paragraphRecords.push(block.record);
  }

  var payload = _aptBuildInsertPayload(paragraphRecords);
  _aptApplyPayloadViaRest(docId, payload);

  for (var ti = 0; ti < tableBlocks.length; ti++) {
    _aptDecodeTableBlock(docId, tableBlocks[ti]);
  }
}

/**
 * Parses the flat record list into top-level blocks (gts-83s5, APT v2):
 * `{type:'paragraph', record}` in document order, or `{type:'table', rows,
 * cols, cells: [{row, col, records}]}` for one `<TABLE.../<CELL.../</TABLE>`
 * run. Throws on a malformed marker sequence (wrong cell count, missing
 * close) rather than silently misreading a marker line as paragraph
 * content.
 */
function _aptParseBlocks(records) {
  var blocks = [];
  var i = 0;
  while (i < records.length) {
    var m = _APT_TABLE_OPEN_RE.exec(records[i]);
    if (!m) {
      blocks.push({ type: 'paragraph', record: records[i] });
      i++;
      continue;
    }
    var rows = parseInt(m[1], 10);
    var cols = parseInt(m[2], 10);
    i++;
    var cells = [];
    for (var expected = 0; expected < rows * cols; expected++) {
      if (i >= records.length) {
        throw new Error('PortableText decode: table ended before all ' + (rows * cols) + ' cells were seen');
      }
      var cm = _APT_CELL_RE.exec(records[i]);
      if (!cm) throw new Error('PortableText decode: expected a <CELL r,c> marker, got: ' + records[i]);
      var row = parseInt(cm[1], 10);
      var col = parseInt(cm[2], 10);
      i++;
      var cellRecords = [];
      while (i < records.length && records[i] !== _APT_TABLE_CLOSE && !_APT_CELL_RE.test(records[i])) {
        cellRecords.push(records[i]);
        i++;
      }
      cells.push({ row: row, col: col, records: cellRecords });
    }
    if (i >= records.length || records[i] !== _APT_TABLE_CLOSE) {
      throw new Error('PortableText decode: missing </TABLE> closing marker');
    }
    i++;
    blocks.push({ type: 'table', rows: rows, cols: cols, cells: cells });
  }
  return blocks;
}

/**
 * Materialises one table block into `docId`, always appended at the
 * document's current end (decodeAptIntoDoc's ordering restriction above).
 * Two Docs REST round trips, unlike the flat paragraph path: (1) insertTable
 * creates an empty rows x cols shell, each cell holding Docs' own default
 * single empty paragraph; (2) a documents.get re-read discovers each cell's
 * real paragraph startIndex — a Table's internal index footprint is not
 * reliably predictable from row/column counts alone (undocumented, and
 * varies with cell styling), so this reads it back rather than computing
 * it. Each cell's content is then applied via its own
 * _aptApplyPayloadViaRest call (baseIndex = that cell's paragraph start),
 * independently per cell.
 *
 * Cells are applied in REVERSE document order (last cell first) even
 * though each cell's own content insertion is otherwise independent: every
 * cell's startIndex is read ONCE from `doc2`, before any cell has been
 * written to, and inserting text into an EARLIER cell shifts the real
 * (live) startIndex of every LATER cell in the same table — the same
 * reason chips are applied in descending-offset order in
 * _aptApplyPayloadViaRest. Processing highest-index cell first means a
 * later cell's insertion can never invalidate an earlier cell's
 * already-looked-up index.
 */
function _aptDecodeTableBlock(docId, block) {
  var token = ScriptApp.getOAuthToken();
  var baseUrl = 'https://docs.googleapis.com/v1/documents/' + docId;

  var doc1 = _aptFetchDocument(docId, token);
  var body1 = doc1.body.content;
  var endIndex = body1[body1.length - 1].endIndex;
  var insertAt = endIndex - 1; // before the body's trailing paragraph mark

  var insertResp = UrlFetchApp.fetch(baseUrl + ':batchUpdate', {
    method: 'post', muteHttpExceptions: true,
    headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
    payload: JSON.stringify({ requests: [{ insertTable: {
      rows: block.rows, columns: block.cols, location: { index: insertAt }
    }}]})
  });
  if (insertResp.getResponseCode() !== 200) {
    throw new Error('PortableText decode: insertTable failed HTTP ' + insertResp.getResponseCode() +
      ' ' + insertResp.getContentText().substring(0, 500));
  }

  var doc2 = _aptFetchDocument(docId, token);
  var table = _aptFindLastTable(doc2.body.content, block.rows, block.cols);
  var cellsWithIndex = [];
  for (var ci = 0; ci < block.cells.length; ci++) {
    var cellSpec = block.cells[ci];
    var tableCell = table.tableRows[cellSpec.row].tableCells[cellSpec.col];
    cellsWithIndex.push({ spec: cellSpec, start: tableCell.content[0].startIndex });
  }
  cellsWithIndex.sort(function (a, b) { return b.start - a.start; }); // last cell first
  for (var ei = 0; ei < cellsWithIndex.length; ei++) {
    var entry = cellsWithIndex[ei];
    var cellPayload = _aptBuildInsertPayload(entry.spec.records);
    _aptApplyPayloadViaRest(docId, cellPayload, entry.start);
  }
}

function _aptFetchDocument(docId, token) {
  var resp = UrlFetchApp.fetch('https://docs.googleapis.com/v1/documents/' + docId, {
    method: 'get', muteHttpExceptions: true,
    headers: { 'Authorization': 'Bearer ' + token }
  });
  if (resp.getResponseCode() !== 200) {
    throw new Error('PortableText decode: documents.get failed HTTP ' + resp.getResponseCode() +
      ' ' + resp.getContentText().substring(0, 500));
  }
  return JSON.parse(resp.getContentText());
}

/**
 * The just-inserted table is identified by matching row/column count among
 * the body's top-level content, scanning from the end — safe because
 * decodeAptIntoDoc's ordering restriction guarantees every table block is
 * appended strictly after the last one, so the LAST matching table in
 * document order is always the one just inserted (even when two table
 * blocks in the same doc share identical dimensions).
 */
function _aptFindLastTable(content, rows, cols) {
  for (var i = content.length - 1; i >= 0; i--) {
    var el = content[i];
    if (el.table && el.table.rows === rows && el.table.columns === cols) return el.table;
  }
  throw new Error('PortableText decode: could not find the just-inserted ' + rows + 'x' + cols + ' table');
}

/**
 * Splits raw APT text into an array of record bodies (each still containing
 * its own `<SR>`-suffixed physical lines). The chunk before the first blank
 * line is the preamble and is dropped.
 */
function _aptSplitRecords(apt) {
  var normalized = (apt || '').replace(/\r\n/g, '\n').replace(/\n+$/, '');
  var chunks = normalized.split(/\n\n+/);
  if (!chunks.length) return [];
  if (chunks[0].indexOf('<!--') === 0) chunks = chunks.slice(1);
  return chunks.filter(function (c) { return c.length > 0; });
}

/**
 * Reduces the parsed records to one flat insertion payload:
 *   fullText — the entire body's plain text, records joined by a real "\n"
 *              (hard paragraph break) and physical lines within a record
 *              joined by "\v" (soft return, matching _toSoftReturnText).
 *   chips    — [{offset, email}], offset is the position IN fullText where
 *              the PERSON element belongs (it contributes no characters of
 *              its own to fullText).
 *   runs     — [{start, end, bold, italic, link}], offsets into fullText.
 *   paragraphs — [{start, end, isListItem}], one per record in order —
 *              gts-83s5 (APT v2): isListItem drives a createParagraphBullets
 *              request in _aptApplyPayloadViaRest.
 * All offsets are 0-based against fullText; the REST application step below
 * converts them to real document indices (fullText[0] lives at doc index
 * baseIndex, default 1).
 */
function _aptBuildInsertPayload(records) {
  var fullText = '';
  var chips = [];
  var runs = [];
  var paragraphs = [];

  for (var ri = 0; ri < records.length; ri++) {
    if (ri > 0) fullText += '\n';
    var record = records[ri];
    var isListItem = record.indexOf(_APT_LI_PREFIX) === 0;
    if (isListItem) record = record.slice(_APT_LI_PREFIX.length);
    var paraStart = fullText.length;

    if (record === _APT_EMPTY) {
      paragraphs.push({ start: paraStart, end: fullText.length, isListItem: isListItem });
      continue;
    }

    var physicalLines = record.split('\n').map(function (line) {
      var isSoft = line.slice(-_APT_SR.length) === _APT_SR;
      var text = isSoft ? line.slice(0, -_APT_SR.length) : line;
      if (text === _APT_BLANK) text = '';
      return text;
    });

    for (var li = 0; li < physicalLines.length; li++) {
      if (li > 0) fullText += '\v';
      var parsed = _aptParseLine(physicalLines[li]);
      var base = fullText.length;
      fullText += parsed.text;
      for (var si = 0; si < parsed.spans.length; si++) {
        var span = parsed.spans[si];
        runs.push({ start: base + span.start, end: base + span.end, bold: span.bold, italic: span.italic, link: span.link });
      }
      for (var chi = 0; chi < parsed.chips.length; chi++) {
        chips.push({ offset: base + parsed.chips[chi].offset, email: parsed.chips[chi].email });
      }
    }
    paragraphs.push({ start: paraStart, end: fullText.length, isListItem: isListItem });
  }
  return { fullText: fullText, chips: chips, runs: runs, paragraphs: paragraphs };
}

/**
 * Parses one physical line's marked-up text into {text, spans, chips}, all
 * offsets local to this line's own plain `text` (escapes resolved, markup
 * stripped). Mirrors _aptRenderRun's coalescing in reverse.
 */
function _aptParseLine(line) {
  var i = 0;
  var n = line.length;
  var text = '';
  var spans = [];
  var chips = [];
  while (i < n) {
    if (line.substr(i, 7) === '{{chip:') {
      var closeIdx = line.indexOf('}}', i + 7);
      if (closeIdx !== -1) {
        chips.push({ offset: text.length, email: line.slice(i + 7, closeIdx) });
        i = closeIdx + 2;
        continue;
      }
    }
    var span = _aptMatchSpan(line, i);
    if (span) {
      var spanText = _aptUnescape(span.text);
      spans.push({ start: text.length, end: text.length + spanText.length, bold: span.bold, italic: span.italic, link: span.link });
      text += spanText;
      i = span.nextIndex;
      continue;
    }
    if (line[i] === '\\' && i + 1 < n) {
      text += line[i + 1];
      i += 2;
    } else {
      text += line[i];
      i += 1;
    }
  }
  return { text: text, spans: spans, chips: chips };
}

/**
 * Matches one markup span (`**_x_**`, `**x**`, `_x_`, or `[x](url)`) at
 * position `i` in `line`. Returns {text, bold, italic, link, nextIndex} or
 * null. A link's inner text is checked for a bold/italic marker spanning
 * its ENTIRE width (`[**x**](url)`, matching how _aptRenderRun nests them on
 * encode when a run is both bold/italic and linked over the same range) and
 * unwrapped accordingly; anything less than whole-width nesting stays
 * opaque (v1 limitation, see format spec — a link range that is bold/italic
 * over only PART of its width cannot be represented).
 */
function _aptMatchSpan(line, i) {
  var rest = line.slice(i);
  var m;
  if ((m = /^\*\*_((?:[^_\\]|\\.)*)_\*\*/.exec(rest)) || (m = /^_\*\*((?:[^*\\]|\\.)*)\*\*_/.exec(rest))) {
    return { text: m[1], bold: true, italic: true, link: null, nextIndex: i + m[0].length };
  }
  if ((m = /^\*\*((?:[^*\\]|\\.)*)\*\*/.exec(rest))) {
    return { text: m[1], bold: true, italic: false, link: null, nextIndex: i + m[0].length };
  }
  if ((m = /^_((?:[^_\\]|\\.)*)_/.exec(rest))) {
    return { text: m[1], bold: false, italic: true, link: null, nextIndex: i + m[0].length };
  }
  if ((m = /^\[((?:[^\]\\]|\\.)*)\]\(((?:[^)\\]|\\.)*)\)/.exec(rest))) {
    var inner = m[1];
    var url = m[2];
    var bi;
    if ((bi = /^\*\*_((?:[^_\\]|\\.)*)_\*\*$/.exec(inner)) || (bi = /^_\*\*((?:[^*\\]|\\.)*)\*\*_$/.exec(inner))) {
      return { text: bi[1], bold: true, italic: true, link: url, nextIndex: i + m[0].length };
    }
    if ((bi = /^\*\*((?:[^*\\]|\\.)*)\*\*$/.exec(inner))) {
      return { text: bi[1], bold: true, italic: false, link: url, nextIndex: i + m[0].length };
    }
    if ((bi = /^_((?:[^_\\]|\\.)*)_$/.exec(inner))) {
      return { text: bi[1], bold: false, italic: true, link: url, nextIndex: i + m[0].length };
    }
    return { text: inner, bold: false, italic: false, link: url, nextIndex: i + m[0].length };
  }
  return null;
}

function _aptUnescape(text) {
  return text.replace(/\\(.)/g, '$1');
}

/**
 * Applies a built payload to `docId` in one batchUpdate: the whole body text
 * first, then every chip (in descending-offset order, so a chip not yet
 * applied is never shifted by one applied after it in this same call), then
 * every style run (bold/italic/link — applied last, with each offset bumped
 * by however many chips sit at or before it, since every already-applied
 * chip has shifted the document by exactly one character each).
 *
 * @param {string} docId
 * @param {Object} payload
 * @param {number=} baseIndex Document index that payload.fullText[0] lands
 *   at. Defaults to 1 (the whole-body call); gts-83s5 (APT v2) also calls
 *   this once per table cell with baseIndex = that cell's own paragraph
 *   start index, so a cell's runs/chips/list-bullets apply exactly like a
 *   top-level paragraph's do.
 */
function _aptApplyPayloadViaRest(docId, payload, baseIndex) {
  baseIndex = baseIndex || 1;
  var token   = ScriptApp.getOAuthToken();
  var baseUrl = 'https://docs.googleapis.com/v1/documents/';
  var requests = [];

  if (payload.fullText.length) {
    requests.push({ insertText: { text: payload.fullText, location: { index: baseIndex } } });
  }

  var chipsDesc = payload.chips.slice().sort(function (a, b) { return b.offset - a.offset; });
  for (var ci = 0; ci < chipsDesc.length; ci++) {
    requests.push({ insertPerson: {
      personProperties: { email: chipsDesc[ci].email },
      location: { index: baseIndex + chipsDesc[ci].offset }
    }});
  }

  var chipsAsc = payload.chips.slice().sort(function (a, b) { return a.offset - b.offset; });
  function shiftFor(offset) {
    var n = 0;
    for (var i = 0; i < chipsAsc.length; i++) { if (chipsAsc[i].offset <= offset) n++; }
    return n;
  }
  for (var ri = 0; ri < payload.runs.length; ri++) {
    var run = payload.runs[ri];
    var start = baseIndex + run.start + shiftFor(run.start);
    var end   = baseIndex + run.end   + shiftFor(run.end);
    if (end <= start) continue;
    if (run.bold)   requests.push({ updateTextStyle: { range: { startIndex: start, endIndex: end }, textStyle: { bold: true },   fields: 'bold' } });
    if (run.italic) requests.push({ updateTextStyle: { range: { startIndex: start, endIndex: end }, textStyle: { italic: true }, fields: 'italic' } });
    if (run.link)   requests.push({ updateTextStyle: { range: { startIndex: start, endIndex: end }, textStyle: { link: { url: run.link } }, fields: 'link' } });
  }

  var paragraphs = payload.paragraphs || [];
  for (var pi = 0; pi < paragraphs.length; pi++) {
    var p = paragraphs[pi];
    if (!p.isListItem) continue;
    var pStart = baseIndex + p.start + shiftFor(p.start);
    requests.push({ createParagraphBullets: {
      range: { startIndex: pStart, endIndex: pStart + 1 },
      bulletPreset: 'BULLET_DISC_CIRCLE_SQUARE'
    }});
  }

  if (!requests.length) return;
  var resp = UrlFetchApp.fetch(baseUrl + docId + ':batchUpdate', {
    method: 'post', muteHttpExceptions: true,
    headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
    payload: JSON.stringify({ requests: requests })
  });
  if (resp.getResponseCode() !== 200) {
    throw new Error('PortableText decode: batchUpdate failed HTTP ' + resp.getResponseCode() +
      ' ' + resp.getContentText().substring(0, 500));
  }
}
