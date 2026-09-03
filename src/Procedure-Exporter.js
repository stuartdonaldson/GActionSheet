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

const DOC_EXPORT_SCHEMA_VERSION = '2.5'; // gts-284o — governance->document terminology rename (identifiers, log tags, output filename); no schema shape change

/* ========================================================================== *
 * TEXT-PATTERN INFERENCE RULES (heuristic — tune here)
 *
 * Every regex-driven guess the exporter makes lives in this one region.
 * Each rule carries a stable `name` used as `revision`/`semantic_state`
 * evidence (`{ type: 'text_pattern', rule: '<name>' }`) so a reviewer can
 * trace any classification back to exactly one line here.
 * ========================================================================== */

/**
 * Document-unit recognition. Matched against normalized paragraph text
 * regardless of Google Docs heading style — e.g. "Board Safety Procedure
 * 03-03: Emergency Preparedness, Response and Recovery" is recognized as a
 * `procedure` unit even when the paragraph carries no HEADING_* style.
 *
 * `rank` is the heuristic nesting depth used to build unit parent/child
 * relationships (lower rank = higher in the hierarchy; a unit's parent is
 * the nearest preceding unit with a strictly lower rank). It is inherently
 * approximate for documents that mix conventions — tune per-project here.
 */
const DOC_UNIT_PATTERNS = [
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
  // No \b after the closing paren: ")" and a following space are both
  // non-word characters, so \b never matches there — a prior version of
  // this regex (`/^\(OLD\)\b/i`) only matched the unrealistic glued form
  // "(OLD)Something" and silently never fired on real "(OLD) Something"
  // text. Found via gts-2glm hardening test (test_export_document_
  // semantic_state_text_pattern_evidence).
  { name: 'old_paren_prefix', state: 'historical', re: /^\(OLD\)/i },
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

function onDocumentExportMenu(e) { // eslint-disable-line no-unused-vars
  return CardService.newUniversalActionResponseBuilder()
    .setNavigation(CardService.newNavigation().pushCard(_exportDocumentAndGetCard_({ exportPdf: false })))
    .build();
}

function onDocumentExportAndPdfMenu(e) { // eslint-disable-line no-unused-vars
  return CardService.newUniversalActionResponseBuilder()
    .setNavigation(CardService.newNavigation().pushCard(_exportDocumentAndGetCard_({ exportPdf: true })))
    .build();
}

/**
 * Runs the export synchronously and returns the result/error card. Used
 * only by the Extensions-menu universalActions above (onDocumentExportMenu
 * / onDocumentExportAndPdfMenu) — that's a single already-blocking
 * platform round trip with no other card to show interim state in. The
 * classic-menu dialog (gts-s7ut, showDocumentExportDialog_ /
 * ExportProgressDialog.html) does NOT call this; it runs exportDocument_
 * via google.script.run instead, avoiding this path's ~30s ceiling on
 * documents like the Governance Manual.
 */
function _exportDocumentAndGetCard_(options) {
  try {
    const result = exportDocument_(options);
    return _buildDocumentExportResultCard_(result.jsonFile, result.pdfFile);
  } catch (err) {
    GasLogger.log('document_export.error', { msg: err.message, stack: err.stack || '' });
    GasLogger.flush();
    return _buildDocumentExportErrorCard_(err.message);
  }
}

function _buildBackToHomeButton_() {
  return CardService.newTextButton()
    .setText('Action Sync')
    .setOnClickAction(
      CardService.newAction().setFunctionName('onExportBackToHome')
    );
}

function onExportBackToHome(e) { // eslint-disable-line no-unused-vars
  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().updateCard(buildHomepageCard()))
    .build();
}

function _buildDocumentExportResultCard_(jsonFile, pdfFile) {
  return CardService.newCardBuilder()
    .setHeader(
      CardService.newCardHeader()
        .setTitle(_NORTHLAKE_UU_SUITE_NAME)
        .setImageUrl(_NORTHLAKE_UU_EMBLEM_URL)
    )
    .addSection(CardService.newCardSection().addWidget(_buildBackToHomeButton_()))
    .addSection(_buildExportResultSection_({ jsonFile: jsonFile, pdfFile: pdfFile }))
    .build();
}

function _buildDocumentExportErrorCard_(message) {
  return CardService.newCardBuilder()
    .setHeader(
      CardService.newCardHeader()
        .setTitle(_NORTHLAKE_UU_SUITE_NAME)
        .setImageUrl(_NORTHLAKE_UU_EMBLEM_URL)
    )
    .addSection(CardService.newCardSection().addWidget(_buildBackToHomeButton_()))
    .addSection(_buildExportErrorSection_(message))
    .build();
}

/**
 * 'Export complete.' section, built from the live GAS File objects the
 * synchronous universalAction path (_exportDocumentAndGetCard_) returns.
 */
function _buildExportResultSection_(result) {
  const jsonId = result.jsonFile.getId();
  const pdfId = result.pdfFile ? result.pdfFile.getId() : null;

  const section = CardService.newCardSection()
    .addWidget(CardService.newTextParagraph().setText('Export complete.'))
    .addWidget(
      CardService.newTextButton()
        .setText('Open JSON in Drive')
        .setOpenLink(CardService.newOpenLink().setUrl(`https://drive.google.com/file/d/${jsonId}/view`))
    );

  if (pdfId) {
    section.addWidget(
      CardService.newTextButton()
        .setText('Open PDF snapshot')
        .setOpenLink(CardService.newOpenLink().setUrl(`https://drive.google.com/file/d/${pdfId}/view`))
    );
  }
  return section;
}

function _buildExportErrorSection_(message) {
  return CardService.newCardSection().addWidget(
    CardService.newTextParagraph().setText(`Export failed: ${message}`)
  );
}

/** Manual-invocation wrappers (Apps Script editor / ad hoc runs). Not wired
 * to any UI trigger themselves — see onDocumentExportMenu above. */
function exportDocumentJson() {
  return exportDocument_({ exportPdf: false });
}

function exportDocumentJsonAndPdf() {
  return exportDocument_({ exportPdf: true });
}

/* ========================================================================== *
 * ENTRY POINTS — classic "Extensions" menu dialog (gts-s7ut, supersedes the
 * gts-7ca7 sidebar-card + time-based-trigger design below).
 *
 * gts-7ca7 shipped a sidebar 'Export' button backed by a ScriptApp
 * time-based trigger (mirroring EditorAddonCard.js's _scheduleSheetUpdate /
 * _processPendingSheetUpdates queue-drain pattern). Measured against the
 * real Governance Manual doc it worked, but the trigger took 2m47s to fire
 * (Apps Script gives no firing-time guarantee for sub-minute one-off
 * `.after()` triggers — see the export-async-trigger-latency bd memory) for
 * ~8s of actual work — a bad trade for what was supposed to be a progress
 * indicator. Removed in favor of this: a modal dialog
 * (DocumentApp.getUi().showModalDialog, only reachable from the classic
 * bound-script menu below, not from a CardService action) running
 * exportDocument_() via google.script.run. That RPC path has Apps
 * Script's normal ~6-minute execution ceiling (not the ~30s CardService
 * card-action ceiling that made the Extensions-menu universalActions above
 * risky on this same document), so the work can run synchronously inside
 * it with zero scheduling latency, while a second google.script.run poll
 * (getExportProgressForDialog) updates the dialog every ~1.5s from the same
 * EXPORT_STATUS_<docId> property the trigger design also used.
 *
 * Trade-off accepted deliberately (2026-08-13): this dialog runs as the
 * active user (same permission boundary as today, via the classic menu's
 * authorization context) rather than staying reachable from the sidebar
 * card — CardService actions cannot call Ui.showModalDialog, and the only
 * way to keep it in the sidebar would route through the public WebApp
 * (executeAs: USER_DEPLOYING), which would run the export as the deployer
 * rather than the clicking user. See MenuHandler.js's Docs-context menu
 * (menuShowExportDialog) for the entry point.
 * ========================================================================== */

const _EXPORT_STATUS_PROP_PREFIX = 'EXPORT_STATUS_';

/** Ordered stage labels reported via options.onProgress in exportDocument_
 * below — kept in one place so the dialog's poll and the progress callback
 * agree on totalStages. */
function _exportStageList_(exportPdf) {
  const stages = [
    'Reading document',
    'Extracting content',
    'Processing comments',
    'Building document views',
    'Writing export file'
  ];
  if (exportPdf) stages.push('Rendering PDF snapshot');
  return stages;
}

function _readExportStatus_(docId) {
  const raw = PropertiesService.getScriptProperties().getProperty(_EXPORT_STATUS_PROP_PREFIX + docId);
  return raw ? JSON.parse(raw) : null;
}

function _writeExportStatus_(docId, status) {
  status.updatedAt = new Date().toISOString();
  PropertiesService.getScriptProperties().setProperty(_EXPORT_STATUS_PROP_PREFIX + docId, JSON.stringify(status));
}

/**
 * Menu handler (MenuHandler.js's Docs-context 'Action Sync' menu ->
 * 'Export…' -> menuShowExportDialog -> this). Only callable from that
 * classic bound-script authorization path — showModalDialog is unavailable
 * to CardService action handlers.
 */
function showDocumentExportDialog_() {
  const doc = DocumentApp.getActiveDocument();
  const docId = doc ? doc.getId() : '';
  const template = HtmlService.createTemplateFromFile('ExportProgressDialog');
  template.docId = docId;
  template.buildVersion = BUILD_INFO.version;
  const html = template.evaluate().setWidth(440).setHeight(340);
  DocumentApp.getUi().showModalDialog(html, 'Export');
}

/**
 * google.script.run entry point (ExportProgressDialog.html). Runs
 * exportDocument_() synchronously — safe here specifically because this
 * is not a CardService action handler (no ~30s ceiling), just Apps
 * Script's normal per-execution limit. Returns a plain JSON-serializable
 * object (google.script.run cannot marshal a live DriveApp File back to
 * the client) and clears any stale status for this doc before starting so
 * a leftover 'done'/'error' from a previous run can't be momentarily
 * visible to the first poll.
 *
 * @param {string} docId
 * @param {boolean} exportPdf
 * @returns {{jsonFileId: string, pdfFileId: (string|undefined),
 *   jsonContent: string, pdfBase64: (string|undefined)}}
 *   jsonContent/pdfBase64 (gts-283i.2) let the dialog trigger a real
 *   client-side download (Blob/data URL) alongside the existing Drive
 *   file, without a second round trip back through Drive to fetch bytes
 *   already held in this execution.
 */
function runExportForDialog(docId, exportPdf) { // eslint-disable-line no-unused-vars
  const stages = _exportStageList_(exportPdf);
  _writeExportStatus_(docId, {
    state: 'running',
    stage: stages[0],
    stageIndex: 0,
    totalStages: stages.length,
    exportPdf: exportPdf,
    startedAt: new Date().toISOString()
  });

  try {
    const result = exportDocument_({
      docId: docId,
      exportPdf: exportPdf,
      onProgress: (stageIndex, totalStages, stageLabel) => {
        _writeExportStatus_(docId, {
          state: 'running',
          stage: stageLabel,
          stageIndex: stageIndex,
          totalStages: totalStages,
          exportPdf: exportPdf
        });
      }
    });

    _writeExportStatus_(docId, {
      state: 'done',
      stage: stages[stages.length - 1],
      stageIndex: stages.length,
      totalStages: stages.length,
      exportPdf: exportPdf,
      jsonFileId: result.jsonFile.getId(),
      pdfFileId: result.pdfFile ? result.pdfFile.getId() : undefined
    });

    // Reuse the string exportDocument_ already serialized/wrote to Drive
    // (result.jsonString) rather than re-running JSON.stringify(result.json)
    // here — for a large document that second full stringify measurably
    // slowed this entry point (gts-283i.2 regression caught by
    // test_export_dialog_status_transitions_running_then_done going from a
    // ~152s baseline to ~494s).
    const pdfBase64 = result.pdfFile ? Utilities.base64Encode(result.pdfFile.getBlob().getBytes()) : undefined;

    return {
      jsonFileId: result.jsonFile.getId(),
      pdfFileId: result.pdfFile ? result.pdfFile.getId() : undefined,
      jsonContent: result.jsonString,
      pdfBase64: pdfBase64
    };
  } catch (err) {
    _writeExportStatus_(docId, { state: 'error', errorMessage: err.message, exportPdf: exportPdf });
    // gts-diag: catch-and-rethrow above dropped docId, leaving Cloud
    // Logging's error-reporting entry with no way to tell which document
    // Docs.Documents.get() was actually called with — log it explicitly so
    // a repro is diagnosable from clasp logs alone.
    GasLogger.log('export.dialog.error', { docId: docId, msg: err.message, exportPdf: exportPdf });
    // google.script.run's withFailureHandler receives an Error built from
    // this message — rethrow rather than swallow so the dialog's failure
    // path (not just the polled status) sees it even if a poll is missed.
    throw new Error(err.message);
  }
}

/**
 * google.script.run poll target (ExportProgressDialog.html, ~1.5s
 * interval). Plain property read — cheap, no lock needed (single reader,
 * single writer per docId within one dialog session).
 *
 * @param {string} docId
 * @returns {object|null}
 */
function getExportProgressForDialog(docId) { // eslint-disable-line no-unused-vars
  return _readExportStatus_(docId);
}

/**
 * @param {{exportPdf: boolean, docId: (string|undefined), onProgress: (function|undefined)}} options
 *   docId is an optional testability seam (gts-2glm): when supplied, the
 *   export runs against that document instead of
 *   DocumentApp.getActiveDocument(), which only resolves inside a live
 *   add-on UI session. Production entry points (onDocumentExportMenu et
 *   al.) never pass docId — they always omit it and rely on the
 *   active-document default. Only a headless test-support caller (WebApp.js's
 *   export_document_json route) sets it.
 *   onProgress(stageIndex, totalStages, stageLabel) is an optional seam
 *   (gts-s7ut, formerly gts-7ca7) called at each stage boundary below, in
 *   the same order as _exportStageList_(options.exportPdf). Omitted by
 *   every existing synchronous caller (exportDocumentJson/
 *   exportDocumentJsonAndPdf, the universalActions handlers, the WebApp
 *   export_document_json route) — only runExportForDialog (the
 *   Extensions-menu export dialog) passes it, so its absence is a no-op and
 *   behavior for those callers is unchanged.
 *
 *   Stage timing is logged unconditionally (export.stage / export.complete,
 *   see _reportStage below) regardless of caller — this is what showed the
 *   dur_s spread (single digits to 250s+ across the gts-2glm run) in the
 *   Axiom python-side export_document_json events had no GAS-side
 *   breakdown to explain; this instrumentation is that breakdown.
 */
function exportDocument_(options) {
  const documentId = options.docId || DocumentApp.getActiveDocument().getId();
  const _stages = _exportStageList_(options.exportPdf);
  const _t0 = Date.now();
  let _tPrev = _t0;
  const _reportStage = (i) => {
    const now = Date.now();
    GasLogger.log('export.stage', {
      docId: documentId,
      stage: _stages[i],
      stageIndex: i + 1,
      totalStages: _stages.length,
      stepMs: now - _tPrev,
      totalMs: now - _t0
    });
    _tPrev = now;
    if (options.onProgress) options.onProgress(i + 1, _stages.length, _stages[i]);
  };

  // Advanced Google Service: Docs API.
  const apiDoc = Docs.Documents.get(documentId, {
    suggestionsViewMode: 'SUGGESTIONS_INLINE',
    includeTabsContent: true
  });
  _reportStage(0); // 'Reading document' — logged AFTER the work it names, so
  // stepMs is that stage's own cost, not the previous stage's (gts-7ca7
  // follow-up: the original pre-work placement mislabeled every stage by
  // one, attributing e.g. the Docs.Documents.get() call's time to the
  // 'Extracting content' log line instead of 'Reading document').

  const out = {
    schema_version: DOC_EXPORT_SCHEMA_VERSION,
    generated_at: new Date().toISOString(),
    document: {
      id: documentId,
      title: apiDoc.title || documentId,
      revision_id: apiDoc.revisionId || null,
      source_url: `https://docs.google.com/document/d/${documentId}/edit`,
      suggestion_groups: [],
      toc: [],
      images: []
    },
    semantics: {
      baseline: 'Text against which proposed revisions are evaluated.',
      proposed: 'Unchanged baseline plus proposed insertions, excluding deletions.',
      historical: 'Old or superseded material retained for reference.',
      editorial: 'Drafting/reviewer material not intended as document text.'
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
      no_quoted_text_comments: 0,
      explicit_page_breaks: 0,
      distinct_suggestion_ids: 0,
      toc_entries: 0,
      images: 0,
      warnings: []
    }
  };

  // gts-z6j0 — export output goes to the document's own isolated export
  // folder (under EXPORT_ROOT_FOLDER_ID), not the source document's parent
  // folder, so users with access to the source folder don't see export
  // byproducts. Falls back to getSourceFolder_() if export isolation isn't
  // configured -- see src/ExportFolderMap.js. Resolved up front (not just
  // before the JSON/PDF writes, as before gts-283i.4) because embedded-image
  // extraction (§19.3) needs a Drive folder to save image files into during
  // traversal, before the first JSON stringify.
  const folder = getExportFolder_(documentId, out.document.title);

  // Shared across every tab's ctx below so all embedded images from a
  // multi-tab document land in the same single "<title>-images/" subfolder
  // instead of one per tab. Created lazily (see getImagesFolder_) so a
  // document with no images never gets an empty subfolder.
  const driveState = { parentFolder: folder, imagesFolder: null, imagesFolderComputed: false };

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
      listState: {},
      // §19.3 — inlineObjects/positionedObjects live under documentTab, not
      // at the top level of the API response (confirmed live, gts-283i.1).
      inlineObjects: tab.documentTab.inlineObjects || {},
      driveState
    };

    processStructuralContent_(body, ctx);
  });
  _reportStage(1); // 'Extracting content'

  out.comments = getDriveComments_(documentId, out);
  associateCommentsToBlocks_(out);
  buildSuggestionGroups_(out);
  _reportStage(2); // 'Processing comments'

  buildColorSignals_(out);
  buildDocumentViews_(out, options.includeWholeDocumentViews === true);
  finalizeDiagnostics_(out);
  omitEmptyStructuralArrays_(out); // §13.4 — must run after every stage that
  // populates comment_ids/color_signals/evidence, and before serialization.
  _reportStage(3); // 'Building document views'

  let jsonString = JSON.stringify(out, null, 2);
  const jsonBlob = Utilities.newBlob(
    jsonString,
    'application/json',
    `${sanitizeFilename_(out.document.title)}-gas.json`
  );

  // folder resolved up front, before traversal — see the driveState comment
  // near the top of this function.
  const jsonFile = folder ? folder.createFile(jsonBlob) : DriveApp.createFile(jsonBlob);
  _reportStage(4); // 'Writing export file'

  let pdfFile = null;
  if (options.exportPdf) {
    pdfFile = exportPdfSnapshot_(documentId, out.document.title, folder);
    _reportStage(5); // 'Rendering PDF snapshot'
    if (pdfFile) {
      out.document.pdf_snapshot = {
        file_id: pdfFile.getId(),
        file_name: pdfFile.getName()
      };

      // Rewrite JSON once so it contains the PDF snapshot metadata. Keep
      // jsonString in sync so callers (runExportForDialog's jsonContent,
      // gts-283i.2) get the same bytes actually written to Drive instead of
      // paying for a third stringify of a potentially multi-MB object.
      jsonString = JSON.stringify(out, null, 2);
      jsonFile.setContent(jsonString);
    }
  }

  GasLogger.log('export.complete', {
    docId: documentId,
    totalMs: Date.now() - _t0,
    exportPdf: !!options.exportPdf,
    tabsProcessed: out.diagnostics.tabs_processed,
    units: out.diagnostics.units,
    blocks: out.diagnostics.blocks,
    runs: out.diagnostics.runs,
    comments: out.diagnostics.comments,
    images: out.diagnostics.images
  });
  // Flushed here (not left to the caller) so export.stage/export.complete
  // reach Axiom for every entry point — several existing callers only flush
  // on their own error path (_exportDocumentAndGetCard_,
  // _handleExportDocumentJson), which would otherwise strand these events
  // in GasLogger's in-memory buffer for the rest of that execution.
  GasLogger.flush();

  return { jsonFile, pdfFile, json: out, jsonString };
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
      // §7.5: TOC entries are navigation aids, not document content — they
      // must NOT go through processParagraph_/createUnit_/createBlock_ (that
      // was gts-6cq2-era behavior and produced duplicate fake document
      // units, since TOC line text like "Board Policy 1: X\t9" matches
      // DOC_UNIT_PATTERNS same as a real heading). Diverted entirely
      // to document.toc instead; ctx.sourceOrder/allBlocks/currentUnit are
      // untouched by TOC content.
      processTableOfContents_(se.tableOfContents.content || [], ctx);
      return;
    }

    // Section breaks affect layout but do not necessarily start a new page.
  });
}

/** Builds document.toc entries from a tableOfContents structural element's
 * content. Each TOC line is a single paragraph whose text is
 * "Title<TAB>PageNumber" and whose link-bearing run(s) carry
 * textStyle.link.heading.{id, tabId} pointing straight at the target
 * heading — confirmed live via SPIKE-CommentPosition.js's toc_probe op
 * (gts-6cq2 follow-up), so this is a direct deep link, not a text match. */
function processTableOfContents_(content, ctx) {
  (content || []).forEach(item => {
    if (!item.paragraph) return;
    const entry = buildTocEntry_(item.paragraph, ctx);
    if (entry) ctx.out.document.toc.push(entry);
  });
  ctx.out.diagnostics.toc_entries = ctx.out.document.toc.length;
}

function buildTocEntry_(paragraph, ctx) {
  let text = '';
  let heading = null;

  (paragraph.elements || []).forEach(pe => {
    if (!pe.textRun) return;
    text += pe.textRun.content || '';
    const link = pe.textRun.textStyle?.link;
    if (!heading && link?.heading) heading = link.heading;
  });

  const normalized = text.replace(/\n+$/, '');
  if (!normalized.trim()) return null;

  // Docs renders a TOC line as "Title<TAB>PageNumber" — split on the last
  // tab rather than the first, since a title itself could (rarely) contain
  // a tab character.
  const lastTab = normalized.lastIndexOf('\t');
  const title = (lastTab >= 0 ? normalized.slice(0, lastTab) : normalized).trim();
  const displayedPage = lastTab >= 0 ? normalized.slice(lastTab + 1).trim() : null;

  const url = heading
    ? `https://docs.google.com/document/d/${ctx.out.document.id}/edit` +
      (heading.tabId ? `?tab=${heading.tabId}` : '') +
      `#heading=${heading.id}`
    : null;

  return {
    title,
    displayed_page: displayedPage,
    target_tab_id: heading ? (heading.tabId || null) : null,
    target_heading_id: heading ? heading.id : null,
    url
  };
}

function processParagraph_(structuralElement, ctx) {
  const p = structuralElement.paragraph;
  const paragraphElements = p.elements || [];
  const runs = [];
  const inlineImageElements = [];
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

    if (pe.inlineObjectElement) {
      // §19.3 — deferred to a second pass below, after ctx.currentUnit is
      // settled for this paragraph (unit detection runs off allText, which
      // an image-only paragraph never has).
      inlineImageElements.push(pe);
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

  // Skip wholly-empty paragraphs after applying page-break effects — but not
  // an image-only paragraph (§19.3): it has no text, yet still needs a block.
  if (!allText.trim() && !inlineImageElements.length) {
    if (pageBreaksAfterText) ctx.currentPage += pageBreaksAfterText;
    return;
  }

  const namedStyle = p.paragraphStyle?.namedStyleType || 'NORMAL_TEXT';
  const headingLevel = headingLevel_(namedStyle);
  const semanticUnit = detectDocumentUnit_(allText, namedStyle);

  if (semanticUnit) {
    ctx.currentUnit = createUnit_(semanticUnit, structuralElement, ctx);
    ctx.out.units.push(ctx.currentUnit);
    ctx.out.diagnostics.units++;
  } else if (!ctx.currentUnit) {
    ctx.currentUnit = createSyntheticRootUnit_(ctx);
    ctx.out.units.push(ctx.currentUnit);
    ctx.out.diagnostics.units++;
  }

  if (inlineImageElements.length) {
    processInlineImages_(inlineImageElements, ctx);
  }

  // An image-only paragraph produces no text block — the image block(s)
  // above are this paragraph's entire contribution.
  if (!allText.trim()) {
    if (pageBreaksAfterText) ctx.currentPage += pageBreaksAfterText;
    return;
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

/* ========================================================================== *
 * EMBEDDED IMAGES (docs/procedure-exporter.md §19.3, gts-283i.4)
 * ========================================================================== */

/** One `image`-kind block per element, pushed onto ctx.currentUnit/allBlocks
 * the same way a text block is, plus a mirrored document.images[] entry
 * (§19.3's "diverted metadata" convention, matching document.toc/§7.5). A
 * lookup or fetch failure is logged as a diagnostics warning and the element
 * is skipped entirely — never partially recorded (no block whose image_ref
 * doesn't correspond to an actual saved file). */
function processInlineImages_(elements, ctx) {
  elements.forEach(pe => {
    const result = extractInlineImage_(pe, ctx);
    if (!result) return;

    ctx.currentUnit.blocks.push(result.block);
    ctx.allBlocks.push(result.block);
    ctx.out.diagnostics.blocks++;
    ctx.out.diagnostics.images++;
    ctx.out.document.images.push(result.docEntry);
  });
}

/** Fetches and saves one inlineObjectElement's image, per §19.3 "Extraction
 * mechanics": contentUri is a short-lived signed URL and must be fetched via
 * UrlFetchApp during this same execution, never persisted/deferred. Returns
 * null (with a diagnostics warning) if the inline object can't be resolved
 * to a fetchable image or the fetch fails — positioned/floating objects
 * (paragraph.positionedObjectIds) are out of scope for this proposal and are
 * simply never seen here, since this is only reached for inlineObjectElement. */
function extractInlineImage_(pe, ctx) {
  const inlineObjectId = pe.inlineObjectElement.inlineObjectId;
  const inlineObj = ctx.inlineObjects[inlineObjectId];
  const embedded = inlineObj?.inlineObjectProperties?.embeddedObject;
  const contentUri = embedded?.imageProperties?.contentUri;
  const tabLabel = ctx.tabId || 'main';

  if (!contentUri) {
    ctx.out.diagnostics.warnings.push(
      `Embedded object ${inlineObjectId} (tab ${tabLabel}) has no fetchable image contentUri -- ` +
      'skipped, not exported.'
    );
    return null;
  }

  const response = UrlFetchApp.fetch(contentUri, { muteHttpExceptions: true });
  const status = response.getResponseCode();
  if (status < 200 || status >= 300) {
    ctx.out.diagnostics.warnings.push(
      `Embedded image ${inlineObjectId} (tab ${tabLabel}) fetch failed (HTTP ${status}) -- ` +
      'skipped, not exported. contentUri is a short-lived signed URL; this can happen if it ' +
      'expired before this export execution reached it.'
    );
    return null;
  }

  const blob = response.getBlob();
  const ext = imageExtensionFromContentType_(blob.getContentType());
  const imageRef = makeImageRef_(ctx.tabId, pe.startIndex, ext);

  const imagesFolder = getImagesFolder_(ctx);
  const file = imagesFolder
    ? imagesFolder.createFile(blob.setName(imageRef))
    : DriveApp.createFile(blob.setName(imageRef));

  const size = embedded.size || {};
  const location = makeLocation_(pe.startIndex, pe.endIndex, ctx);

  const block = {
    id: makeBlockId_(ctx.tabId, pe.startIndex, pe.endIndex),
    unit_id: ctx.currentUnit.id,
    kind: 'image',
    semantic_state: 'baseline',
    label: null,
    named_style: null,
    heading_level: null,
    source_order: ctx.sourceOrder,
    location,
    list: null,
    runs: [],
    revision_summary: 'unchanged',
    comment_ids: [],
    image_ref: imageRef,
    inline_object_id: inlineObjectId,
    alt_title: embedded.title || null,
    // §19.3 — always null as written by the exporter; a separate local tool
    // fills this in later via a sidecar file (never edits this JSON in
    // place). See ADR-0025.
    alt_description: embedded.description || null,
    width_pt: size.width?.magnitude ?? null,
    height_pt: size.height?.magnitude ?? null,
    description: null
  };
  block.citation_hint = makeCitationHint_(ctx.currentUnit, block);

  const docEntry = {
    id: makeImageId_(ctx.tabId, pe.startIndex),
    image_ref: imageRef,
    drive_file_id: file.getId(),
    tab_id: ctx.tabId,
    source_order: ctx.sourceOrder,
    location
  };

  return { block, docEntry };
}

/** Lazily creates (and caches on ctx.driveState, shared across every tab of
 * this export) the single "<title>-images/" subfolder images are saved
 * into. Returns null — meaning "save at Drive root", mirroring jsonFile's
 * own folder-less fallback — when export folder isolation isn't configured
 * (getExportFolder_ returned null). A document with no embedded images never
 * calls this, so it never creates an empty subfolder. */
function getImagesFolder_(ctx) {
  const state = ctx.driveState;
  if (state.imagesFolderComputed) return state.imagesFolder;
  state.imagesFolderComputed = true;
  if (state.parentFolder) {
    state.imagesFolder = state.parentFolder.createFolder(`${sanitizeFilename_(ctx.out.document.title)}-images`);
  }
  return state.imagesFolder;
}

const IMAGE_CONTENT_TYPE_EXTENSIONS_ = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/gif': 'gif',
  'image/webp': 'webp',
  'image/bmp': 'bmp',
  'image/svg+xml': 'svg'
};

function imageExtensionFromContentType_(contentType) {
  return IMAGE_CONTENT_TYPE_EXTENSIONS_[contentType] || 'png';
}

/** Same derivation as makeBlockId_ (§19.3): tab_id + structural start index,
 * unique within the export by construction and stable across re-exports of
 * an unchanged document. */
function makeImageRef_(tabId, startIndex, ext) {
  return `img-${tabId || 'main'}-${startIndex ?? 0}.${ext}`;
}

function makeImageId_(tabId, startIndex) {
  return `image__${tabId || 'main'}__${startIndex ?? 0}`;
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
 * DOCUMENT UNIT RECOGNITION
 * ========================================================================== */

// Leading semantic-state markers ("(OLD) ", "OLD - ", "END: ", "FYI - ") are
// stripped before DOC_UNIT_PATTERNS matching only — a heading like
// "(OLD) Board Policy 3: Superseded Policy" must still be recognized as a
// `policy` unit (with `historical` semantic_state) rather than falling
// through to the generic heading-style `section` fallback. Only patterns
// anchored at string-start are eligible; title and semantic-state detection
// both continue to run against the full, unstripped text.
const KIND_MATCH_STRIP_PATTERNS = SEMANTIC_STATE_PATTERNS.filter(p => p.re.source.startsWith('^'));

function stripLeadingStateMarker_(t) {
  for (const pattern of KIND_MATCH_STRIP_PATTERNS) {
    const m = pattern.re.exec(t);
    if (m && m.index === 0) return t.slice(m[0].length).trim();
  }
  return t;
}

function detectDocumentUnit_(text, namedStyle) {
  const t = normalizeLine_(text);
  const kindMatchText = stripLeadingStateMarker_(t);

  for (const pattern of DOC_UNIT_PATTERNS) {
    if (pattern.re.test(kindMatchText)) {
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
 * rank. See DOC_UNIT_PATTERNS / HEADING_FALLBACK_BASE_RANK for how
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
  const revisionSummary = summarizeRevision_(runs);

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
    revision_summary: revisionSummary,
    comment_ids: []
  };

  // §13.3: unchanged blocks (93%+ of a typical export) get a single
  // canonical `text` field; blocks with any revision activity get the
  // all_text/baseline_text/proposed_text trio instead. Never both — the
  // trio would be byte-identical copies of `text` on an unchanged block.
  if (revisionSummary === 'unchanged') {
    block.text = buildViewText_(runs, 'all', semantic.state);
  } else {
    block.all_text = buildViewText_(runs, 'all', semantic.state);
    block.baseline_text = buildViewText_(runs, 'baseline', semantic.state);
    block.proposed_text = buildViewText_(runs, 'proposed', semantic.state);
  }

  block.citation_hint = makeCitationHint_(ctx.currentUnit, block);
  return block;
}

/** §13.3 fallback accessor: read the trio when present (revision activity),
 * else the canonical `text` field (unchanged block). Every read site that
 * previously assumed `all_text`/`baseline_text`/`proposed_text` always
 * exist must go through here instead. */
function blockAllText_(b) {
  return b.all_text !== undefined ? b.all_text : (b.text || '');
}

function blockBaselineText_(b) {
  return b.baseline_text !== undefined ? b.baseline_text : (b.text || '');
}

function blockProposedText_(b) {
  return b.proposed_text !== undefined ? b.proposed_text : (b.text || '');
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
 * see the file-level comment on onDocumentExportMenu / makeAutoTextRun_). */
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
  // baseline/proposed document views by default.
  if (view !== 'all' && ['historical', 'editorial'].includes(semanticState)) return '';

  const joined = runs
    .filter(r => r.kind === 'text')
    .filter(r => {
      if (view === 'all') return true;
      if (view === 'baseline') return r.revision.change !== 'inserted';
      if (view === 'proposed') return r.revision.change !== 'deleted';
      return true;
    })
    .map(r => r.text)
    .join('');

  return normalizeDerivedText_(joined);
}

/** §13.5: cosmetic normalization applied ONLY to derived/concatenated text
 * (block.text, all_text/baseline_text/proposed_text, views.*) — never to
 * runs[].text, which stays byte-exact per §17.1's fidelity guarantee.
 * Non-breaking space (U+00A0, common from pasted content) reads as a plain
 * space to a downstream consumer with no loss of meaning. Vertical tab
 * (U+000B) is Docs' internal encoding for a Shift+Enter soft line break
 * within a paragraph — a real, meaningful break, not noise — and renders as
 * an unrecognizable control character to most consumers if left as-is, so
 * it's normalized to '\n' rather than stripped. */
function normalizeDerivedText_(s) {
  return s.replace(/\u00A0/g, ' ').replace(/\u000B/g, '\n');
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
    const exact = blocks.filter(b => normalizeForMatch_(blockAllText_(b)).includes(q));
    if (exact.length) {
      linkCommentToBlocks(comment, exact, exact.length === 1 ? 'quoted_text_exact' : 'quoted_text_multiple');
      return;
    }

    // Tier 2: conservative prefix match (first 80 normalized characters),
    // only accepted when it resolves to exactly one block.
    const prefix = q.slice(0, 80);
    const approx = blocks.filter(b => normalizeForMatch_(blockAllText_(b)).includes(prefix));
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

  out.diagnostics.no_quoted_text_comments = out.comments.filter(c => c.association_basis === 'no_quoted_text').length;
  if (out.diagnostics.no_quoted_text_comments > 0) {
    out.diagnostics.warnings.push(
      `${out.diagnostics.no_quoted_text_comments} comment(s) have no quoted text ` +
      `(Drive's quotedFileContent was empty). Their association_basis is "no_quoted_text" and ` +
      'associated_block_ids/section_path are empty — this is not a matching-tier failure, no ' +
      'anchoring signal was available from Drive at all, so these require manual review.'
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
        const joined = normalizeForMatch_(window.map(b => blockAllText_(b)).join(' '));
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
    const score = jaccardScore_(qWords, wordSet_(normalizeForMatch_(blockAllText_(b))));
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

/**
 * §13.1/13.2: baseline_text/proposed_text are whole-document
 * reconstructions, ~7% of a representative export's bytes on top of the
 * gts-6cq2 per-block dedup, and are needed only by a consumer that wants
 * "the document" rather than "a section" (§2's use case, not the common
 * case). Opt-in via options.includeWholeDocumentViews (default false) —
 * deleted_text/proposed_additions are much smaller extracts, not
 * duplicative in the same way, and always included.
 */
function buildDocumentViews_(out, includeWholeDocumentViews) {
  const blocks = [];
  out.units.forEach(u => (u.blocks || []).forEach(b => blocks.push(b)));

  const views = {
    deleted_text: blocks.flatMap(b => b.runs
      .filter(r => r.kind === 'text' && r.revision.change === 'deleted')
      .map(r => r.text)
    ).join(''),
    proposed_additions: blocks.flatMap(b => b.runs
      .filter(r => r.kind === 'text' && r.revision.change === 'inserted')
      .map(r => r.text)
    ).join('')
  };

  if (includeWholeDocumentViews) {
    views.baseline_text = blocks.map(b => blockBaselineText_(b)).filter(Boolean).join('\n');
    views.proposed_text = blocks.map(b => blockProposedText_(b)).filter(Boolean).join('\n');
  }

  out.views = views;
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

/** §13.4: omit kind_evidence/semantic_state_evidence/color_signals/
 * comment_ids/runs[].revision.evidence entirely when empty, rather than
 * emitting `[]`. Runs as a final pass (not at construction time) because
 * every one of these arrays is populated incrementally by later stages
 * (associateCommentsToBlocks_, buildSuggestionGroups_, buildColorSignals_)
 * that push onto them or reassign them — deleting the key at construction
 * time would break those in-place mutations. Deleting a key that was never
 * present is a no-op, so this is safe to run against any unit/block shape. */
function omitEmptyStructuralArrays_(out) {
  const dropIfEmpty = (obj, key) => {
    if (Array.isArray(obj[key]) && obj[key].length === 0) delete obj[key];
  };

  dropIfEmpty(out.document, 'toc');
  dropIfEmpty(out.document, 'images');

  out.units.forEach(u => {
    dropIfEmpty(u, 'kind_evidence');
    dropIfEmpty(u, 'semantic_state_evidence');
    dropIfEmpty(u, 'color_signals');
    dropIfEmpty(u, 'comment_ids');

    (u.blocks || []).forEach(b => {
      dropIfEmpty(b, 'semantic_state_evidence');
      dropIfEmpty(b, 'comment_ids');
      (b.runs || []).forEach(r => {
        if (r.kind === 'text') dropIfEmpty(r.revision, 'evidence');
      });
    });
  });
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
