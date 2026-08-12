/**
 * Governance Manual -> structured JSON exporter for Google Docs.
 *
 * Intended use:
 *   - Runs inside the shared GActionSheet Workspace Add-on (same clasp project
 *     as MenuHandler.js / WorkspaceAddonCard.js) — NOT its own bound script.
 *   - Enable Advanced Google Services: Google Docs API and Drive API.
 *   - Entry point is the add-on's Extensions-menu universal actions
 *     (appsscript.json addOns.common.universalActions), NOT onOpen()/
 *     DocumentApp.getUi(). This file must never define onOpen() — that
 *     collides with MenuHandler.js's onOpen() in the same script project.
 *
 * The exporter is READ-ONLY with respect to the source document.
 *
 * Revision semantics:
 *   baseline + unchanged  = baseline text retained
 *   baseline + deleted    = baseline text proposed for deletion
 *   proposed + inserted   = proposed insertion
 *   historical            = retained old/superseded material (heuristic)
 *   editorial             = drafting/reviewer material (heuristic)
 *
 * Deletion evidence:
 *   - google_docs_suggestion
 *   - strikethrough
 *
 * Multi-contributor signals (see docs/procedure-exporter.md §6.4):
 *   - document.suggestion_groups is the RELIABLE same-edit-event grouping
 *     signal (same Docs suggestion ID = same edit action), regardless of
 *     section. The Docs API does not expose the author/timestamp behind a
 *     suggestion ID, so possible_authors on each group is a best-effort,
 *     confidence-labeled hint from co-located comments only.
 *   - unit.color_signals is a LOCAL clustering hint only. Manual highlight
 *     colors are not guaranteed to mean the same thing in two different
 *     units, so no document-wide color legend is built or implied.
 *
 * Page numbers:
 *   Google Docs does not expose a universal body-range -> rendered-page map.
 *   This exporter assigns best-effort pages using explicit page breaks and
 *   records the basis/limitations in the JSON.
 */

const GOV_EXPORT_SCHEMA_VERSION = '2.1';

/* ========================================================================== *
 * TEXT-PATTERN INFERENCE RULES (heuristic — tune here)
 *
 * Every regex-driven guess the exporter makes lives in this one region.
 * Each rule carries a stable `name` used as `revision`/`semantic_state`
 * evidence (`{ type: 'text_pattern', rule: '<name>' }`) so a reviewer can
 * trace any classification back to exactly one line here.
 * ========================================================================== */

/**
 * Governance-unit recognition. Matched against normalized paragraph text
 * regardless of Google Docs heading style — e.g. "Board Safety Procedure
 * 03-03: Emergency Preparedness, Response and Recovery" is recognized as a
 * `procedure` unit even when the paragraph carries no HEADING_* style.
 *
 * `rank` is the heuristic nesting depth used to build unit parent/child
 * relationships (lower rank = higher in the hierarchy; a unit's parent is
 * the nearest preceding unit with a strictly lower rank). It is inherently
 * approximate for documents that mix conventions — tune per-project here.
 */
const GOVERNANCE_UNIT_PATTERNS = [
  {
    name: 'policy_numbered',
    kind: 'policy',
    rank: 2,
    re: /^(Church|Cabinet|Board(?: Meeting| Leader| Committee| Safety)?|Communications Committee|Facilities Committee|Finance Committee|Governance Committee|HRC|Human Resources Committee|Nominating Committee)\s+Policy\s+\d+\s*:/i
  },
  {
    name: 'procedure_numbered',
    kind: 'procedure',
    rank: 3,
    re: /^(Church|Cabinet|Board(?: Meeting| Leader| Committees?| Safety)?|CC|FAC|FIC|GC|HRC|NC)\s+Procedure(?:s)?\s+\d+(?:[-:]\d+)?\s*:/i
  },
  { name: 'charter_suffix', kind: 'charter', rank: 1, re: /\bCHARTER\s*$/i },
  { name: 'article_prefix', kind: 'article', rank: 1, re: /^ARTICLE\s+(?:[A-Z]+|\w+)\b/i },
  { name: 'exhibit_prefix', kind: 'exhibit', rank: 1, re: /^EXHIBIT\s+[A-Z0-9]+\b/i },
  { name: 'standing_rules_prefix', kind: 'standing_rules', rank: 1, re: /^STANDING RULES\b/i },
  { name: 'organizational_chart_mention', kind: 'organizational_chart', rank: 1, re: /ORGANIZATIONAL CHART/i },
  { name: 'glossary_mention', kind: 'glossary', rank: 1, re: /GLOSSARY/i },
  { name: 'numbered_section_prefix', kind: 'section', rank: 2, re: /^\d+\s*[-–—]\s+.+/ }
];

/** Rank assigned to a generic heading-style fallback unit (no named pattern
 * matched, but the paragraph carries a HEADING_n style). Nested under
 * `procedure` by default — tune if a project's headings represent a
 * shallower level than that. */
const HEADING_FALLBACK_BASE_RANK = 3;

/** Historical/editorial drafting-material detection, applied to unit titles
 * and block text alike. */
const SEMANTIC_STATE_PATTERNS = [
  { name: 'old_paren_prefix', state: 'historical', re: /^\(OLD\)\b/i },
  { name: 'old_dash_prefix', state: 'historical', re: /^OLD\s*[-:]/i },
  { name: 'end_prefix', state: 'editorial', re: /^END\s*[-:]/i },
  { name: 'fyi_prefix', state: 'editorial', re: /^FYI\s*[-:]/i },
  { name: 'tbd_marker', state: 'editorial', re: /\bTBD\b/i },
  { name: 'question_marks_marker', state: 'editorial', re: /\?\?\?+/ },
  { name: 'link_placeholder_marker', state: 'editorial', re: /\blink\?\?/i },
  { name: 'placeholder_word_marker', state: 'editorial', re: /\bplaceholder\b/i }
];

/** Bold-run + colon labeled-paragraph heuristic tuning (e.g. `Intent:`). */
const LABEL_MAX_LEN = 80;
const LABEL_SCAN_MAX_LEN = 100;

/** Comment-to-block association tuning (see associateCommentsToBlocks_).
 * The Drive Comments API `anchor` field is an opaque, undocumented "kix"
 * encoding that does not map onto the Docs API's startIndex/endIndex
 * addressing, so quoted-text matching against exported block text is the
 * only available mechanism. These constants gate the last-resort fuzzy pass
 * used when exact/prefix/multi-block substring matching all fail. */
const COMMENT_MATCH_WINDOW_BLOCKS = 3; // consecutive blocks joined for cross-paragraph quotes
const COMMENT_FUZZY_MIN_SCORE = 0.7;   // minimum Jaccard word-overlap to accept
const COMMENT_FUZZY_MIN_MARGIN = 0.15; // required lead over the second-best candidate

/* ========================================================================== *
 * ENTRY POINTS — Extensions-menu universal actions
 * (registered in appsscript.json addOns.common.universalActions)
 * ========================================================================== */

function onGovernanceExportMenu(e) { // eslint-disable-line no-unused-vars
  return CardService.newUniversalActionResponseBuilder()
    .setNavigation(CardService.newNavigation().pushCard(_exportGovernanceAndGetCard_({ exportPdf: false })))
    .build();
}

function onGovernanceExportAndPdfMenu(e) { // eslint-disable-line no-unused-vars
  return CardService.newUniversalActionResponseBuilder()
    .setNavigation(CardService.newNavigation().pushCard(_exportGovernanceAndGetCard_({ exportPdf: true })))
    .build();
}

/**
 * Sidebar homepage-card button handlers (WorkspaceAddonCard.js's
 * _buildGovernanceExportSection) — added as a fallback entry point to the
 * same export, since Extensions-menu universalActions were not appearing
 * for this test install (Extensions menu rendering appears to need
 * Marketplace SDK config beyond just the manifest; unconfirmed, tracked
 * separately). Share _exportGovernanceAndGetCard_ with the universal-action
 * handlers above rather than duplicating the try/catch — only the response
 * builder type differs (ActionResponseBuilder here vs.
 * UniversalActionResponseBuilder there).
 */
function onExportGovernanceJson() { // eslint-disable-line no-unused-vars
  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().pushCard(_exportGovernanceAndGetCard_({ exportPdf: false })))
    .build();
}

function onExportGovernanceJsonAndPdf() { // eslint-disable-line no-unused-vars
  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().pushCard(_exportGovernanceAndGetCard_({ exportPdf: true })))
    .build();
}

/**
 * Runs the export and returns the result/error card — shared core between
 * the Extensions-menu universalActions and the sidebar button fallback.
 */
function _exportGovernanceAndGetCard_(options) {
  try {
    const result = exportGovernance_(options);
    return _buildGovernanceExportResultCard_(result.jsonFile, result.pdfFile);
  } catch (err) {
    GasLogger.log('governance_export.error', { msg: err.message, stack: err.stack || '' });
    GasLogger.flush();
    return _buildGovernanceExportErrorCard_(err.message);
  }
}

function _buildGovernanceExportResultCard_(jsonFile, pdfFile) {
  const jsonId = jsonFile.getId();
  const jsonView = `https://drive.google.com/file/d/${jsonId}/view`;

  const section = CardService.newCardSection()
    .addWidget(CardService.newTextParagraph().setText('Governance export complete.'))
    .addWidget(
      CardService.newTextButton()
        .setText('Open JSON in Drive')
        .setOpenLink(CardService.newOpenLink().setUrl(jsonView))
    );

  if (pdfFile) {
    const pdfView = `https://drive.google.com/file/d/${pdfFile.getId()}/view`;
    section.addWidget(
      CardService.newTextButton()
        .setText('Open PDF snapshot')
        .setOpenLink(CardService.newOpenLink().setUrl(pdfView))
    );
  }

  return CardService.newCardBuilder()
    .setHeader(
      CardService.newCardHeader()
        .setTitle(_NORTHLAKE_UU_SUITE_NAME)
        .setImageUrl(_NORTHLAKE_UU_EMBLEM_URL)
    )
    .addSection(section)
    .build();
}

function _buildGovernanceExportErrorCard_(message) {
  return CardService.newCardBuilder()
    .setHeader(
      CardService.newCardHeader()
        .setTitle(_NORTHLAKE_UU_SUITE_NAME)
        .setImageUrl(_NORTHLAKE_UU_EMBLEM_URL)
    )
    .addSection(
      CardService.newCardSection().addWidget(
        CardService.newTextParagraph().setText(`Governance export failed: ${message}`)
      )
    )
    .build();
}

/** Manual-invocation wrappers (Apps Script editor / ad hoc runs). Not wired
 * to any UI trigger themselves — see onGovernanceExportMenu above. */
function exportGovernanceJson() {
  return exportGovernance_({ exportPdf: false });
}

function exportGovernanceJsonAndPdf() {
  return exportGovernance_({ exportPdf: true });
}

function exportGovernance_(options) {
  const appDoc = DocumentApp.getActiveDocument();
  const documentId = appDoc.getId();

  // Advanced Google Service: Docs API.
  const apiDoc = Docs.Documents.get(documentId, {
    suggestionsViewMode: 'SUGGESTIONS_INLINE',
    includeTabsContent: true
  });

  const out = {
    schema_version: GOV_EXPORT_SCHEMA_VERSION,
    generated_at: new Date().toISOString(),
    document: {
      id: documentId,
      title: apiDoc.title || appDoc.getName(),
      revision_id: apiDoc.revisionId || null,
      source_url: `https://docs.google.com/document/d/${documentId}/edit`,
      suggestion_groups: []
    },
    semantics: {
      baseline: 'Text against which proposed revisions are evaluated.',
      proposed: 'Unchanged baseline plus proposed insertions, excluding deletions.',
      historical: 'Old or superseded material retained for reference.',
      editorial: 'Drafting/reviewer material not intended as governance text.'
    },
    page_numbering: {
      exact_rendered_page_map_available: false,
      default_basis: 'explicit_page_break_count',
      warning:
        'Google Docs does not expose a universal body-text range to final rendered page mapping. ' +
        'Page values are best effort unless the source uses explicit page breaks.'
    },
    suggestion_authorship: {
      resolvable_via_documents_get: false,
      note:
        'The Docs API documents.get response does not attach an author or timestamp to a ' +
        'suggestedInsertionIds/suggestedDeletionIds value. document.suggestion_groups groups runs ' +
        'by suggestion ID (a reliable same-edit-event signal) and attaches possible_authors only as ' +
        'a best-effort hint from co-located Drive comments.'
    },
    units: [],
    comments: [],
    views: {},
    diagnostics: {
      tabs_processed: 0,
      units: 0,
      blocks: 0,
      runs: 0,
      proposed_insertions: 0,
      suggested_deletions: 0,
      strikethrough_deletions: 0,
      historical_blocks: 0,
      editorial_blocks: 0,
      comments: 0,
      unresolved_comments: 0,
      unmatched_comments: 0,
      explicit_page_breaks: 0,
      distinct_suggestion_ids: 0,
      warnings: []
    }
  };

  const tabs = flattenTabs_(apiDoc.tabs || []);

  tabs.forEach(tab => {
    if (!tab.documentTab) return;
    out.diagnostics.tabs_processed++;

    const tabId = tab.tabProperties?.tabId || null;
    const tabTitle = tab.tabProperties?.title || null;
    const body = tab.documentTab.body?.content || [];

    const ctx = {
      out,
      tabId,
      tabTitle,
      currentPage: 1,
      explicitBreaksSoFar: 0,
      unitStack: [],
      currentUnit: null,
      sourceOrder: 0,
      allBlocks: [],
      listState: {}
    };

    processStructuralContent_(body, ctx);
  });

  out.comments = getDriveComments_(documentId, out);
  associateCommentsToBlocks_(out);
  buildSuggestionGroups_(out);
  buildColorSignals_(out);
  buildDocumentViews_(out);
  finalizeDiagnostics_(out);

  const jsonBlob = Utilities.newBlob(
    JSON.stringify(out, null, 2),
    'application/json',
    `${sanitizeFilename_(out.document.title)}-governance.json`
  );

  const folder = getSourceFolder_(documentId);
  const jsonFile = folder ? folder.createFile(jsonBlob) : DriveApp.createFile(jsonBlob);

  let pdfFile = null;
  if (options.exportPdf) {
    pdfFile = exportPdfSnapshot_(documentId, out.document.title, folder);
    if (pdfFile) {
      out.document.pdf_snapshot = {
        file_id: pdfFile.getId(),
        file_name: pdfFile.getName()
      };

      // Rewrite JSON once so it contains the PDF snapshot metadata.
      jsonFile.setContent(JSON.stringify(out, null, 2));
    }
  }

  return { jsonFile, pdfFile, json: out };
}

/* ========================================================================== *
 * STRUCTURAL TRAVERSAL
 * ========================================================================== */

function flattenTabs_(tabs) {
  const all = [];
  (tabs || []).forEach(tab => {
    all.push(tab);
    if (tab.childTabs?.length) all.push(...flattenTabs_(tab.childTabs));
  });
  return all;
}

function processStructuralContent_(content, ctx) {
  (content || []).forEach(se => {
    ctx.sourceOrder++;

    if (se.paragraph) {
      processParagraph_(se, ctx);
      return;
    }

    if (se.table) {
      processTable_(se.table, ctx);
      return;
    }

    if (se.tableOfContents) {
      processStructuralContent_(se.tableOfContents.content || [], ctx);
      return;
    }

    // Section breaks affect layout but do not necessarily start a new page.
  });
}

function processParagraph_(structuralElement, ctx) {
  const p = structuralElement.paragraph;
  const paragraphElements = p.elements || [];
  const runs = [];
  let pageBreaksBeforeText = 0;
  let pageBreaksAfterText = 0;
  let sawText = false;

  paragraphElements.forEach(pe => {
    if (pe.pageBreak) {
      ctx.out.diagnostics.explicit_page_breaks++;
      ctx.explicitBreaksSoFar++;
      if (sawText) pageBreaksAfterText++;
      else pageBreaksBeforeText++;
      return;
    }

    if (pe.autoText) {
      // AutoText commonly represents generated page numbers in headers/footers.
      // Preserved as a non-text run for audit (kind: 'auto_text') — see
      // mergeAdjacentRuns_, which passes these through unmerged rather than
      // dropping them. It does not map body text to a rendered page.
      runs.push(makeAutoTextRun_(pe, ctx));
      return;
    }

    if (!pe.textRun) return;

    const run = makeTextRun_(pe, ctx);
    if (run.text !== '') {
      runs.push(run);
      sawText = true;
    }
  });

  if (pageBreaksBeforeText) ctx.currentPage += pageBreaksBeforeText;

  const mergedRuns = mergeAdjacentRuns_(runs);
  const allText = mergedRuns.filter(r => r.kind === 'text').map(r => r.text).join('');

  // Skip empty paragraphs after applying page-break effects.
  if (!allText.trim()) {
    if (pageBreaksAfterText) ctx.currentPage += pageBreaksAfterText;
    return;
  }

  const namedStyle = p.paragraphStyle?.namedStyleType || 'NORMAL_TEXT';
  const headingLevel = headingLevel_(namedStyle);
  const semanticUnit = detectGovernanceUnit_(allText, namedStyle);

  if (semanticUnit) {
    ctx.currentUnit = createUnit_(semanticUnit, structuralElement, ctx);
    ctx.out.units.push(ctx.currentUnit);
    ctx.out.diagnostics.units++;
  } else if (!ctx.currentUnit) {
    ctx.currentUnit = createSyntheticRootUnit_(ctx);
    ctx.out.units.push(ctx.currentUnit);
    ctx.out.diagnostics.units++;
  }

  const block = createBlock_(structuralElement, p, mergedRuns, ctx, {
    namedStyle,
    headingLevel,
    allText
  });

  ctx.currentUnit.blocks.push(block);
  ctx.allBlocks.push(block);
  ctx.out.diagnostics.blocks++;
  ctx.out.diagnostics.runs += block.runs.length;

  block.runs.forEach(r => {
    if (r.kind !== 'text') return;
    if (r.revision.state === 'proposed' && r.revision.change === 'inserted') {
      ctx.out.diagnostics.proposed_insertions++;
    }
    if (r.revision.change === 'deleted') {
      const types = (r.revision.evidence || []).map(e => e.type);
      if (types.includes('google_docs_suggestion')) ctx.out.diagnostics.suggested_deletions++;
      if (types.includes('strikethrough')) ctx.out.diagnostics.strikethrough_deletions++;
    }
  });

  if (block.semantic_state === 'historical') ctx.out.diagnostics.historical_blocks++;
  if (block.semantic_state === 'editorial') ctx.out.diagnostics.editorial_blocks++;

  if (pageBreaksAfterText) ctx.currentPage += pageBreaksAfterText;
}

function processTable_(table, ctx) {
  (table.tableRows || []).forEach((row, rowIndex) => {
    (row.tableCells || []).forEach((cell, colIndex) => {
      // Snapshot the flat, traversal-order block list — NOT ctx.currentUnit's
      // own blocks array, which may point at a different unit object by the
      // time this cell finishes (e.g. a heading/EXHIBIT-style line inside the
      // cell opens a new unit mid-cell). ctx.allBlocks is stable across unit
      // switches, so the before/after slice always names the blocks this
      // cell actually produced.
      const before = ctx.allBlocks.length;
      processStructuralContent_(cell.content || [], ctx);
      const after = ctx.allBlocks.length;
      for (let i = before; i < after; i++) {
        ctx.allBlocks[i].table = { row: rowIndex, column: colIndex };
      }
    });
  });
}

/* ========================================================================== *
 * GOVERNANCE UNIT RECOGNITION
 * ========================================================================== */

function detectGovernanceUnit_(text, namedStyle) {
  const t = normalizeLine_(text);

  for (const pattern of GOVERNANCE_UNIT_PATTERNS) {
    if (pattern.re.test(t)) {
      const semantic = detectSemanticState_(t);
      return {
        kind: pattern.kind,
        title: t,
        rank: pattern.rank,
        kind_evidence: [{ type: 'text_pattern', rule: pattern.name }],
        semantic_state: semantic.state,
        semantic_state_evidence: semantic.evidence
      };
    }
  }

  // Heading styles can introduce a generic section even when no named
  // pattern matches. Rank nests it under HEADING_FALLBACK_BASE_RANK by
  // heading depth — see the constant's doc comment for the caveat.
  const level = headingLevel_(namedStyle);
  if (level && t.length < 180) {
    const semantic = detectSemanticState_(t);
    return {
      kind: 'section',
      title: t,
      rank: HEADING_FALLBACK_BASE_RANK + level,
      kind_evidence: [{ type: 'style_pattern', rule: 'heading_style', named_style: namedStyle }],
      semantic_state: semantic.state,
      semantic_state_evidence: semantic.evidence
    };
  }

  return null;
}

function createUnit_(u, se, ctx) {
  const unit = {
    id: makeUnitId_(u.kind, u.title, ctx.tabId, se.startIndex),
    kind: u.kind,
    title: u.title,
    parent_unit_id: null,
    kind_evidence: u.kind_evidence,
    semantic_state: u.semantic_state,
    semantic_state_evidence: u.semantic_state_evidence,
    source_order: ctx.sourceOrder,
    location: makeLocation_(se.startIndex, se.endIndex, ctx),
    citation_hint: null,
    color_signals: [],
    blocks: []
  };
  pushUnitOntoStack_(unit, u.rank, ctx);
  return unit;
}

function createSyntheticRootUnit_(ctx) {
  const unit = {
    id: `document-root__${ctx.tabId || 'main'}`,
    kind: 'document_part',
    title: ctx.tabTitle || 'Document',
    parent_unit_id: null,
    kind_evidence: [],
    semantic_state: 'baseline',
    semantic_state_evidence: [],
    source_order: 0,
    location: {
      tab_id: ctx.tabId,
      tab_title: ctx.tabTitle,
      start_index: null,
      end_index: null,
      page: ctx.currentPage,
      page_basis: 'explicit_page_break_count',
      page_approximate: ctx.explicitBreaksSoFar === 0
    },
    citation_hint: null,
    color_signals: [],
    blocks: []
  };
  pushUnitOntoStack_(unit, -1, ctx);
  return unit;
}

/** Maintains ctx.unitStack (a rank-ordered containment stack) and sets
 * unit.parent_unit_id to the nearest preceding unit with a strictly lower
 * rank. See GOVERNANCE_UNIT_PATTERNS / HEADING_FALLBACK_BASE_RANK for how
 * rank is assigned. */
function pushUnitOntoStack_(unit, rank, ctx) {
  while (ctx.unitStack.length && ctx.unitStack[ctx.unitStack.length - 1].rank >= rank) {
    ctx.unitStack.pop();
  }
  const parent = ctx.unitStack.length ? ctx.unitStack[ctx.unitStack.length - 1].unit : null;
  unit.parent_unit_id = parent ? parent.id : null;
  ctx.unitStack.push({ unit, rank });
}

/* ========================================================================== *
 * BLOCK CLASSIFICATION
 * ========================================================================== */

function createBlock_(se, paragraph, runs, ctx, meta) {
  const label = detectBoldColonLabel_(paragraph.elements || []);
  const semantic = detectSemanticState_(meta.allText);
  const kind = classifyBlock_(paragraph, meta.namedStyle, label, semantic.state);

  const block = {
    id: makeBlockId_(ctx.tabId, se.startIndex, se.endIndex),
    unit_id: ctx.currentUnit.id,
    kind,
    semantic_state: semantic.state,
    semantic_state_evidence: semantic.evidence,
    label: label ? label.text : null,
    named_style: meta.namedStyle,
    heading_level: meta.headingLevel,
    source_order: ctx.sourceOrder,
    location: makeLocation_(se.startIndex, se.endIndex, ctx),
    list: paragraph.bullet ? {
      list_id: paragraph.bullet.listId || null,
      nesting_level: paragraph.bullet.nestingLevel || 0,
      ordered: inferOrderedList_(paragraph.bullet, ctx)
    } : null,
    runs,
    all_text: buildViewText_(runs, 'all', semantic.state),
    baseline_text: buildViewText_(runs, 'baseline', semantic.state),
    proposed_text: buildViewText_(runs, 'proposed', semantic.state),
    revision_summary: summarizeRevision_(runs),
    comment_ids: []
  };

  block.citation_hint = makeCitationHint_(ctx.currentUnit, block);
  return block;
}

function classifyBlock_(paragraph, namedStyle, label, semanticState) {
  if (semanticState === 'historical') return 'historical_note';
  if (semanticState === 'editorial') return 'editorial_note';
  if (headingLevel_(namedStyle)) return 'heading';
  if (paragraph.bullet) return 'list_item';
  if (label) return label.normalized === 'historical note' ? 'historical_note' : 'labeled_paragraph';
  return 'paragraph';
}

function detectBoldColonLabel_(elements) {
  let collected = '';
  let sawBold = false;

  for (const pe of elements) {
    if (!pe.textRun) continue;
    const text = pe.textRun.content || '';
    const bold = pe.textRun.textStyle?.bold === true;

    if (!collected && !bold) return null;
    if (bold) sawBold = true;

    // Once non-bold text begins before a colon, this is not a bold-label pattern.
    if (!bold && !collected.includes(':')) return null;

    collected += text;
    const colon = collected.indexOf(':');
    if (colon >= 0) {
      const label = collected.slice(0, colon).trim();
      if (sawBold && label && label.length <= LABEL_MAX_LEN && !/[\n\r]/.test(label)) {
        return {
          text: label,
          normalized: label.toLowerCase().replace(/\s+/g, ' ')
        };
      }
      return null;
    }

    if (collected.length > LABEL_SCAN_MAX_LEN) return null;
  }

  return null;
}

/** Returns { state, evidence } — see SEMANTIC_STATE_PATTERNS. */
function detectSemanticState_(text) {
  const t = normalizeLine_(text);

  for (const pattern of SEMANTIC_STATE_PATTERNS) {
    if (pattern.re.test(t)) {
      return { state: pattern.state, evidence: [{ type: 'text_pattern', rule: pattern.name }] };
    }
  }

  return { state: 'baseline', evidence: [] };
}

/* ========================================================================== *
 * TEXT RUNS / REVISION EVIDENCE
 * ========================================================================== */

function makeTextRun_(pe, ctx) {
  const tr = pe.textRun;
  const style = tr.textStyle || {};

  // Docs API models normally put these on the TextRun. Keep a fallback to the
  // paragraph element to tolerate response-library variations.
  const deletionIds = tr.suggestedDeletionIds || pe.suggestedDeletionIds || [];
  const insertionIds = tr.suggestedInsertionIds || pe.suggestedInsertionIds || [];
  const strike = style.strikethrough === true;

  const evidence = [];
  let state = 'baseline';
  let change = 'unchanged';

  if (deletionIds.length) {
    state = 'baseline';
    change = 'deleted';
    evidence.push({
      type: 'google_docs_suggestion',
      action: 'deletion',
      suggestion_ids: deletionIds
    });
  } else if (insertionIds.length) {
    state = 'proposed';
    change = 'inserted';
    evidence.push({
      type: 'google_docs_suggestion',
      action: 'insertion',
      suggestion_ids: insertionIds
    });
  }

  if (strike) {
    evidence.push({ type: 'strikethrough' });
    // Strikethrough alone is interpreted as proposed deletion.
    if (change === 'unchanged') {
      state = 'baseline';
      change = 'deleted';
    }
  }

  const foregroundColor = optionalColorToHex_(style.foregroundColor);
  const backgroundColor = optionalColorToHex_(style.backgroundColor);

  // Manual highlight colors are a multi-contributor clustering signal (see
  // docs/procedure-exporter.md §6.4) — recorded as evidence regardless of
  // whether they influenced baseline/proposed classification above. They
  // must NOT be used to infer revision state; see the file-level comment.
  if (foregroundColor || backgroundColor) {
    evidence.push({
      type: 'style_pattern',
      rule: 'manual_highlight_color',
      foreground_color: foregroundColor,
      background_color: backgroundColor
    });
  }

  return {
    kind: 'text',
    text: tr.content || '',
    revision: { state, change, evidence },
    format: {
      bold: style.bold === true,
      italic: style.italic === true,
      underline: style.underline === true,
      strikethrough: strike,
      foreground_color: foregroundColor,
      background_color: backgroundColor,
      link: style.link?.url || null
    },
    location: makeLocation_(pe.startIndex, pe.endIndex, ctx)
  };
}

function makeAutoTextRun_(pe, ctx) {
  return {
    kind: 'auto_text',
    auto_text_type: pe.autoText?.type || null,
    suggested_insertion_ids: pe.autoText?.suggestedInsertionIds || [],
    suggested_deletion_ids: pe.autoText?.suggestedDeletionIds || [],
    location: makeLocation_(pe.startIndex, pe.endIndex, ctx)
  };
}

/** Merges adjacent `text`-kind runs that share identical revision/format.
 * `auto_text`-kind runs are never merged into a neighbor — they pass through
 * standalone so they survive into block.runs (previously dropped entirely;
 * see the file-level comment on onGovernanceExportMenu / makeAutoTextRun_). */
function mergeAdjacentRuns_(runs) {
  const out = [];
  runs.forEach(run => {
    const prev = out[out.length - 1];
    if (prev && prev.kind === 'text' && run.kind === 'text' && equivalentRunSemantics_(prev, run)) {
      prev.text += run.text;
      prev.location.end_index = run.location.end_index;
    } else {
      out.push(run);
    }
  });
  return out;
}

function equivalentRunSemantics_(a, b) {
  return JSON.stringify(a.revision) === JSON.stringify(b.revision) &&
         JSON.stringify(a.format) === JSON.stringify(b.format);
}

function buildViewText_(runs, view, semanticState) {
  // Historical/editorial content is preserved in all_text but excluded from
  // baseline/proposed governance views by default.
  if (view !== 'all' && ['historical', 'editorial'].includes(semanticState)) return '';

  return runs
    .filter(r => r.kind === 'text')
    .filter(r => {
      if (view === 'all') return true;
      if (view === 'baseline') return r.revision.change !== 'inserted';
      if (view === 'proposed') return r.revision.change !== 'deleted';
      return true;
    })
    .map(r => r.text)
    .join('');
}

function summarizeRevision_(runs) {
  const textRuns = runs.filter(r => r.kind === 'text');
  const hasInsert = textRuns.some(r => r.revision.change === 'inserted');
  const hasDelete = textRuns.some(r => r.revision.change === 'deleted');
  if (hasInsert && hasDelete) return 'mixed';
  if (hasInsert) return 'insertions';
  if (hasDelete) return 'deletions';
  return 'unchanged';
}

/* ========================================================================== *
 * COMMENTS
 * ========================================================================== */

function getDriveComments_(fileId, out) {
  const comments = [];
  let pageToken = null;

  do {
    // Advanced Google Service: Drive API v3 (bound as DriveV3; the plain
    // Drive symbol is pinned to v2 for SPIKE.js's Permissions calls).
    const response = DriveV3.Comments.list(fileId, {
      fields:
        'nextPageToken,comments(' +
        'id,content,createdTime,modifiedTime,resolved,deleted,anchor,' +
        'author(displayName,photoLink),' +
        'quotedFileContent(mimeType,value),' +
        'replies(id,content,createdTime,modifiedTime,deleted,author(displayName,photoLink))' +
        ')',
      includeDeleted: false,
      pageSize: 100,
      pageToken: pageToken
    });

    (response.comments || []).forEach(c => {
      comments.push({
        id: c.id || null,
        author: c.author?.displayName || null,
        created_at: c.createdTime || null,
        modified_at: c.modifiedTime || null,
        resolved: c.resolved === true,
        content: c.content || '',
        quoted_text: c.quotedFileContent?.value || null,
        quoted_mime_type: c.quotedFileContent?.mimeType || null,
        drive_anchor: c.anchor || null,
        associated_block_ids: [],
        associated_unit_ids: [],
        association_basis: null,
        section_path: [],
        citation_hint: null,
        replies: (c.replies || []).map(r => ({
          id: r.id || null,
          author: r.author?.displayName || null,
          created_at: r.createdTime || null,
          modified_at: r.modifiedTime || null,
          content: r.content || ''
        }))
      });
    });

    pageToken = response.nextPageToken || null;
  } while (pageToken);

  out.diagnostics.comments = comments.length;
  out.diagnostics.unresolved_comments = comments.filter(c => !c.resolved).length;
  return comments;
}

/**
 * Associates each Drive comment to the exported block(s) its quoted text
 * appears in, then derives full document traceability from that block link:
 * comment -> block -> unit -> section_path (root..leaf breadcrumb), and the
 * reverse index unit.comment_ids / block.comment_ids so a section retrieved
 * by an LLM can be annotated with its comments without a second lookup.
 *
 * The Drive Comments API `anchor` field is not usable for this: it is an
 * opaque "kix" encoding, undocumented, and addressed in a scheme unrelated
 * to the Docs API's startIndex/endIndex. Quoted-text matching against
 * exported block text is therefore the only available anchor mechanism, so
 * this runs a tiered match (exact -> cross-paragraph window -> fuzzy) before
 * giving up and marking the comment unmatched — never silently returning an
 * empty association only findable by re-reading this function.
 */
function associateCommentsToBlocks_(out) {
  const blocks = [];
  out.units.forEach(u => (u.blocks || []).forEach(b => blocks.push(b)));
  const blocksByUnit = {};
  out.units.forEach(u => { blocksByUnit[u.id] = u.blocks || []; });

  const unitById = {};
  out.units.forEach(u => { unitById[u.id] = u; });

  function linkCommentToBlocks(comment, matchedBlocks, basis) {
    comment.associated_block_ids = matchedBlocks.map(b => b.id);
    comment.association_basis = basis;
    matchedBlocks.forEach(b => b.comment_ids.push(comment.id));

    const unitIds = {};
    matchedBlocks.forEach(b => { unitIds[b.unit_id] = true; });
    comment.associated_unit_ids = Object.keys(unitIds);

    const primaryUnit = unitById[matchedBlocks[0].unit_id] || null;
    comment.section_path = primaryUnit ? unitAncestryPath_(primaryUnit, unitById) : [];
    comment.citation_hint = matchedBlocks[0].citation_hint || (primaryUnit ? primaryUnit.citation_hint : null);
  }

  out.comments.forEach(comment => {
    const q = normalizeForMatch_(comment.quoted_text || '');
    comment.associated_unit_ids = [];
    comment.section_path = [];

    if (!q || q.length < 4) {
      comment.association_basis = 'no_quoted_text';
      return;
    }

    // Tier 1: exact substring match within a single block.
    const exact = blocks.filter(b => normalizeForMatch_(b.all_text).includes(q));
    if (exact.length) {
      linkCommentToBlocks(comment, exact, exact.length === 1 ? 'quoted_text_exact' : 'quoted_text_multiple');
      return;
    }

    // Tier 2: conservative prefix match (first 80 normalized characters),
    // only accepted when it resolves to exactly one block.
    const prefix = q.slice(0, 80);
    const approx = blocks.filter(b => normalizeForMatch_(b.all_text).includes(prefix));
    if (approx.length === 1) {
      linkCommentToBlocks(comment, approx, 'quoted_text_prefix');
      return;
    }

    // Tier 3: cross-paragraph quotes — Docs comments can span a paragraph
    // boundary, which no single block's all_text will ever contain. Slide a
    // window of up to COMMENT_MATCH_WINDOW_BLOCKS consecutive blocks within
    // the same unit and test the joined text.
    const windowMatch = findMultiBlockMatch_(q, blocksByUnit);
    if (windowMatch) {
      linkCommentToBlocks(comment, windowMatch, 'quoted_text_multiblock');
      return;
    }

    // Tier 4: last-resort fuzzy word-overlap match. Google truncates/elides
    // quoted_text in ways Tier 1-3 substring matching cannot always absorb
    // (mid-quote ellipsis, reflowed whitespace). Only accepted when there is
    // a single, unambiguous best-scoring block.
    const fuzzy = findFuzzyBlockMatch_(q, blocks);
    if (fuzzy) {
      linkCommentToBlocks(comment, [fuzzy], 'quoted_text_fuzzy');
      return;
    }

    // No match at any tier: say so explicitly rather than leaving an
    // ambiguous empty array indistinguishable from "not yet processed".
    comment.association_basis = 'unmatched';
  });

  out.units.forEach(u => {
    const ids = {};
    (u.blocks || []).forEach(b => (b.comment_ids || []).forEach(id => { ids[id] = true; }));
    u.comment_ids = Object.keys(ids);
  });

  out.diagnostics.unmatched_comments = out.comments.filter(c => c.association_basis === 'unmatched').length;
  if (out.diagnostics.unmatched_comments > 0) {
    out.diagnostics.warnings.push(
      `${out.diagnostics.unmatched_comments} comment(s) could not be associated with any exported block ` +
      '(quoted text not found via exact, prefix, cross-paragraph, or fuzzy matching). Their ' +
      'association_basis is "unmatched" and associated_block_ids/section_path are empty — the Drive ' +
      'anchor field is not decodable into Docs API indices, so these require manual review.'
    );
  }
}

/** Slides a window of up to COMMENT_MATCH_WINDOW_BLOCKS consecutive blocks
 * within each unit and tests the joined normalized text for the quote.
 * Returns the matched blocks array, or null if the quote produced zero or
 * more than one candidate window anywhere in the document (kept conservative
 * like the single-block tiers — an ambiguous quote yields no guess). For a
 * given start position only the smallest matching window is kept, so a
 * longer window that trivially still contains an already-matched quote
 * doesn't get counted as a second, competing candidate. */
function findMultiBlockMatch_(q, blocksByUnit) {
  const candidates = [];

  Object.keys(blocksByUnit).forEach(unitId => {
    const unitBlocks = blocksByUnit[unitId];
    for (let start = 0; start < unitBlocks.length; start++) {
      for (let size = 2; size <= COMMENT_MATCH_WINDOW_BLOCKS && start + size <= unitBlocks.length; size++) {
        const window = unitBlocks.slice(start, start + size);
        const joined = normalizeForMatch_(window.map(b => b.all_text).join(' '));
        if (joined.includes(q)) {
          candidates.push(window);
          break; // smallest window at this start is enough; don't also test larger ones
        }
      }
    }
  });

  return candidates.length === 1 ? candidates[0] : null;
}

/** Jaccard word-overlap match against every block's normalized text.
 * Accepted only when the top score clears COMMENT_FUZZY_MIN_SCORE and leads
 * the runner-up by COMMENT_FUZZY_MIN_MARGIN, so an ambiguous quote yields no
 * match rather than a guessed one. */
function findFuzzyBlockMatch_(q, blocks) {
  const qWords = wordSet_(q);
  let best = null;
  let bestScore = 0;
  let secondScore = 0;

  blocks.forEach(b => {
    const score = jaccardScore_(qWords, wordSet_(normalizeForMatch_(b.all_text)));
    if (score > bestScore) {
      secondScore = bestScore;
      bestScore = score;
      best = b;
    } else if (score > secondScore) {
      secondScore = score;
    }
  });

  if (best && bestScore >= COMMENT_FUZZY_MIN_SCORE && (bestScore - secondScore) >= COMMENT_FUZZY_MIN_MARGIN) {
    return best;
  }
  return null;
}

/** Root..leaf breadcrumb of a unit's ancestry via parent_unit_id, for
 * comment.section_path (comment -> section/policy/procedure traceability). */
function unitAncestryPath_(unit, unitById) {
  const path = [];
  let current = unit;
  const seen = {};
  while (current && !seen[current.id]) {
    seen[current.id] = true;
    path.unshift({ id: current.id, kind: current.kind, title: current.title });
    current = current.parent_unit_id ? unitById[current.parent_unit_id] : null;
  }
  return path;
}

/* ========================================================================== *
 * MULTI-CONTRIBUTOR SIGNALS
 * (document.suggestion_groups, unit.color_signals — see docs §6.4)
 * ========================================================================== */

function buildSuggestionGroups_(out) {
  const groups = {}; // suggestion_id -> { run_count, blockIds: Set-like object, first_location, last_location }

  out.units.forEach(u => (u.blocks || []).forEach(b => (b.runs || []).forEach(r => {
    if (r.kind !== 'text') return;
    (r.revision.evidence || []).forEach(ev => {
      if (ev.type !== 'google_docs_suggestion') return;
      (ev.suggestion_ids || []).forEach(id => {
        if (!groups[id]) {
          groups[id] = { runCount: 0, blockIds: {}, firstLocation: r.location, lastLocation: r.location };
        }
        const g = groups[id];
        g.runCount++;
        g.blockIds[b.id] = true;
        g.lastLocation = r.location;
      });
    });
  })));

  const list = Object.keys(groups).map(id => {
    const g = groups[id];
    const blockIds = Object.keys(g.blockIds);
    const authors = {};
    out.comments.forEach(c => {
      const overlap = (c.associated_block_ids || []).some(bid => g.blockIds[bid]);
      if (overlap && c.author) authors[c.author] = true;
    });

    return {
      suggestion_id: id,
      run_count: g.runCount,
      block_ids: blockIds,
      first_location: g.firstLocation,
      last_location: g.lastLocation,
      possible_authors: Object.keys(authors).map(name => ({
        name,
        confidence: 'low',
        basis: 'co-located comment, unverified'
      }))
    };
  });

  out.document.suggestion_groups = list;
  out.diagnostics.distinct_suggestion_ids = list.length;
}

function buildColorSignals_(out) {
  let anyColorSeen = false;

  out.units.forEach(u => {
    const signals = {};

    (u.blocks || []).forEach(b => (b.runs || []).forEach(r => {
      if (r.kind !== 'text') return;
      const fg = r.format.foreground_color;
      const bg = r.format.background_color;
      if (!fg && !bg) return;

      const key = `${fg || ''}|${bg || ''}`;
      if (!signals[key]) {
        signals[key] = { foreground_color: fg, background_color: bg, runCount: 0, blockIds: {} };
      }
      signals[key].runCount++;
      signals[key].blockIds[b.id] = true;
    }));

    u.color_signals = Object.keys(signals).map(key => {
      anyColorSeen = true;
      const s = signals[key];
      return {
        foreground_color: s.foreground_color,
        background_color: s.background_color,
        run_count: s.runCount,
        block_ids: Object.keys(s.blockIds)
      };
    });
  });

  if (anyColorSeen) {
    out.diagnostics.warnings.push(
      'Manual highlight colors are used in this document. Color meaning is not derivable from the ' +
      'API and is not guaranteed consistent across sections — do not assume the same color denotes ' +
      'the same author/round in two different units. Treat unit.color_signals as a local clustering ' +
      'hint only; document.suggestion_groups (Docs suggestion IDs) is the reliable same-edit-event ' +
      'grouping signal.'
    );
  }
}

/* ========================================================================== *
 * DOCUMENT VIEWS / DIAGNOSTICS
 * ========================================================================== */

function buildDocumentViews_(out) {
  const blocks = [];
  out.units.forEach(u => (u.blocks || []).forEach(b => blocks.push(b)));

  out.views = {
    baseline_text: blocks.map(b => b.baseline_text).filter(Boolean).join('\n'),
    proposed_text: blocks.map(b => b.proposed_text).filter(Boolean).join('\n'),
    deleted_text: blocks.flatMap(b => b.runs
      .filter(r => r.kind === 'text' && r.revision.change === 'deleted')
      .map(r => r.text)
    ).join(''),
    proposed_additions: blocks.flatMap(b => b.runs
      .filter(r => r.kind === 'text' && r.revision.change === 'inserted')
      .map(r => r.text)
    ).join('')
  };
}

function finalizeDiagnostics_(out) {
  if (out.diagnostics.explicit_page_breaks === 0) {
    out.diagnostics.warnings.push(
      'No explicit page breaks were detected. Exported page numbers are not reliable for normal flowing pagination.'
    );
  } else {
    out.diagnostics.warnings.push(
      'Page numbers are based on explicit page-break counting and may diverge from final rendered pagination if text reflows.'
    );
  }

  out.units.forEach(unit => {
    const first = unit.blocks?.[0];
    if (first) {
      unit.location.page = first.location.page;
      unit.location.page_basis = first.location.page_basis;
      unit.location.page_approximate = first.location.page_approximate;
      unit.citation_hint = makeCitationHint_(unit, first);
    }
  });
}

/* ========================================================================== *
 * LISTS
 * ========================================================================== */

function inferOrderedList_(bullet, ctx) {
  // Docs paragraph.bullet provides list ID and nesting level but not always the
  // rendered glyph/number in paragraph content. We avoid inventing numbering.
  // Return null unless project-specific logic is later added using tab.list data.
  return null;
}

/* ========================================================================== *
 * LOCATION / CITATION
 * ========================================================================== */

function makeLocation_(startIndex, endIndex, ctx) {
  return {
    tab_id: ctx.tabId,
    tab_title: ctx.tabTitle,
    start_index: startIndex ?? null,
    end_index: endIndex ?? null,
    page: ctx.currentPage,
    page_basis: 'explicit_page_break_count',
    // True only while no explicit page break has been seen yet in this tab —
    // i.e. `page` is still the untouched default rather than an explicit
    // count. Once explicit breaks start informing the counter this is false;
    // the residual "may still reflow" risk is covered by the document-level
    // diagnostics warning (finalizeDiagnostics_), not repeated per-location.
    page_approximate: ctx.explicitBreaksSoFar === 0
  };
}

function makeCitationHint_(unit, block) {
  const parts = [];
  if (block?.location?.page) parts.push(`p. ${block.location.page}`);
  if (unit?.title) parts.push(unit.title);
  if (block?.label) parts.push(block.label);
  return parts.length ? parts.join(', ') : null;
}

/* ========================================================================== *
 * OUTPUT FILES
 * ========================================================================== */

function getSourceFolder_(sourceFileId) {
  const file = DriveApp.getFileById(sourceFileId);
  const parents = file.getParents();
  return parents.hasNext() ? parents.next() : null;
}

function exportPdfSnapshot_(documentId, title, folder) {
  const url = `https://docs.google.com/document/d/${documentId}/export?format=pdf`;
  const response = UrlFetchApp.fetch(url, {
    headers: { Authorization: `Bearer ${ScriptApp.getOAuthToken()}` },
    muteHttpExceptions: true
  });

  if (response.getResponseCode() < 200 || response.getResponseCode() >= 300) {
    return null;
  }

  const blob = response.getBlob().setName(`${sanitizeFilename_(title)}-snapshot.pdf`);
  return folder ? folder.createFile(blob) : DriveApp.createFile(blob);
}

/* ========================================================================== *
 * UTILITIES
 * ========================================================================== */

function headingLevel_(namedStyle) {
  const m = /^HEADING_([1-6])$/.exec(namedStyle || '');
  return m ? Number(m[1]) : null;
}

function makeUnitId_(kind, title, tabId, startIndex) {
  const slug = slugify_(title).slice(0, 90) || kind;
  return `${tabId || 'main'}__${kind}__${slug}__${startIndex ?? 0}`;
}

function makeBlockId_(tabId, startIndex, endIndex) {
  return `block__${tabId || 'main'}__${startIndex ?? 0}__${endIndex ?? 0}`;
}

function slugify_(s) {
  return String(s || '')
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function normalizeLine_(s) {
  return String(s || '').replace(/[\r\n]+/g, ' ').replace(/\s+/g, ' ').trim();
}

function normalizeForMatch_(s) {
  return normalizeLine_(s)
    .toLowerCase()
    // Fold typographic variants Google Docs/Drive silently substitute
    // (curly quotes, en/em dash, ellipsis glyph) so quoted-comment text
    // compares equal to exported block text that differs only cosmetically.
    .replace(/[‘’‚‛]/g, "'")
    .replace(/[“”„‟]/g, '"')
    .replace(/[–—]/g, '-')
    .replace(/…/g, '...')
    // Drive comment quoted_text is frequently truncated with a leading
    // and/or trailing ellipsis marking "...more text on either side" —
    // strip it so a truncated quote can still match the fuller block text.
    .replace(/^\.{3,}\s*/, '')
    .replace(/\s*\.{3,}$/, '');
}

/** Splits normalized text into a word set for Jaccard overlap scoring. */
function wordSet_(s) {
  const words = String(s || '').split(/[^a-z0-9]+/).filter(Boolean);
  const set = {};
  words.forEach(w => { set[w] = true; });
  return set;
}

function jaccardScore_(setA, setB) {
  const keysA = Object.keys(setA);
  const keysB = Object.keys(setB);
  if (!keysA.length || !keysB.length) return 0;
  let intersection = 0;
  keysA.forEach(k => { if (setB[k]) intersection++; });
  const union = keysA.length + keysB.length - intersection;
  return union ? intersection / union : 0;
}

function sanitizeFilename_(s) {
  return String(s || 'document')
    .replace(/[\\/:*?"<>|]+/g, '-')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
}

function optionalColorToHex_(optionalColor) {
  const rgb = optionalColor?.color?.rgbColor;
  if (!rgb) return null;

  const c = n => Math.max(0, Math.min(255, Math.round((n || 0) * 255)))
    .toString(16).padStart(2, '0');

  return `#${c(rgb.red)}${c(rgb.green)}${c(rgb.blue)}`.toUpperCase();
}
