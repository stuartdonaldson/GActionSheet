# ADR-0026: Document export derives its JSON from a downloaded .docx parsed in local Python, not from the Docs API in Apps Script

**Status:** Accepted
**Date:** 2026-08-25
**Amended:** 2026-08-25 — "fate of the GAS exporter" resolved in favour of preservation as a
comparison baseline (Decision 7); it is no longer an open question.
**Superseded (partial):** 2026-08-26 — ADR-0029 supersedes Decision 4 ("Schema shape is
preserved") for `document.suggestion_groups` (renamed `revision_groups`), `semantic_state`/
`semantics` (removed), and run-level `revision.state` (removed). Decision 4's default — schema
shape otherwise preserved — stands.
**Amended:** 2026-08-27 — gts-284o completed the governance→document terminology migration this
ADR's §Terminology anticipated; see that section for the identifier mapping.
**Relates to:** gts-283i (epic), gts-283i.1 (design spike — this resolves its AC #3), gts-6ls9
(comment-position spike, the dead end this supersedes), gts-11rq (multi-tab export behavior,
deferred), gts-284o (terminology migration), ADR-0025 (image-description sidecar — unaffected),
docs/procedure-exporter.md §10.1 (comment anchoring), §19.3 (image blocks)

## Terminology

This ADR uses **document** for the class of content the exporter processes: any structured
authoritative document — policy, procedure, standard, specification, technical manual, work
instruction. The existing code says *governance* throughout, which names the corpus that happened
to seed the tool (the Governance Manual) rather than what the tool does. That noun is retired going
forward; the rename of existing identifiers, filenames, log tags and docs is tracked separately as
**gts-284o** and deliberately not folded into this decision.

Consequently, identifiers cited below in their current form — `GOV_EXPORT_SCHEMA_VERSION`,
`exportGovernance_`, `<title>-governance.json`, `docs/procedure-exporter.md` — were accurate
descriptions of the code as of this ADR's acceptance date, not the intended names. "Governance
Manual" where it appears is a proper noun naming an actual document and stays.

**gts-284o completed (2026-08-27):** the rename this section anticipates has landed. Read every
identifier above by its migration mapping — `GOV_EXPORT_SCHEMA_VERSION` → `DOC_EXPORT_SCHEMA_VERSION`,
`exportGovernance_` → `exportDocument_`, `<title>-governance.json` → `<title>-gas.json` (renamed
again from the initially-landed `-document.json`, to keep it distinct from the Python side's
`<title>-docx.json` — see `docs/interfaces/document-export-contract.md` §7.4). The WebApp `action`
string and GasLogger tag prefix were included in the rename (`export_governance_json` →
`export_document_json`, `governance_export.*` → `document_export.*`) — see
`docs/suite-composition-deployment.md` §A.5. `docs/procedure-exporter.md`'s rename to
`docs/document-exporter.md` and its content restructuring remain open, tracked separately as
gts-fadg.

## Context

`src/Procedure-Exporter.js` (~1970 lines of Apps Script) builds the export JSON from
`Docs.Documents.get(..., {suggestionsViewMode: 'SUGGESTIONS_INLINE', includeTabsContent: true})`.
The original intent was that the whole pipeline live in GAS, invoked from the document's own
Extensions menu.

Three properties the LLM-ingestion artifact needs are not obtainable that way:

1. **Comment position.** gts-6ls9 established that the Drive Comments API `anchor` field is an
   opaque `kix.<token>` with no positional structure and no relationship to the Docs API's
   `startIndex`/`endIndex` — confirmed against a real corpus document at 57/57 comments with zero
   decodable position. `associateCommentsToBlocks_` therefore resorts to matching comment
   `quoted_text` against exported block text across four tiers (exact substring → 80-char prefix →
   3-block sliding window → Jaccard word-overlap at ≥0.7 with a 0.15 margin), and comments that
   survive all four land in an `association_basis: "unmatched"` bucket requiring manual review.
2. **Suggestion authorship.** `documents.get` attaches no author or timestamp to a
   `suggestedInsertionIds`/`suggestedDeletionIds` value. The export records this openly
   (`suggestion_authorship.resolvable_via_documents_get: false`) and offers
   `possible_authors: [{confidence: 'low', basis: 'co-located comment, unverified'}]` — a guess,
   labelled as one.
3. **Drive-hosted `.docx` files.** `Docs.Documents.get()` accepts only Google-native documents. Any
   real `.docx` in the corpus is not merely degraded, it is **invisible** to the exporter.

The gts-283i.1 follow-up spike (2026-08-14, `_spikeCpDocxExportProbe`) established that a `.docx`
export of the same document carries 62 `commentRangeStart`/`commentRangeEnd`/`commentReference`
triplets, the first of which demonstrably wraps real text (`<w:t>ORGANIZATIONAL CHART</w:t>`).

A follow-up probe (2026-08-25) against corpus file `1aK1jDQY6kfGs4op1t8hZrpN-pzrAMPNF` — a
Drive-hosted native `.docx`, i.e. one of the files in category (3) above — confirmed the rest:

```
word/comments.xml           54 <w:comment>, 6 named authors, 54 w:date attrs
word/commentsExtended.xml   54 <w15:commentEx>       (resolved/threading part present)
54 × commentRangeStart / commentRangeEnd / commentReference
5 × <w:ins>, 7 × <w:del>    w:author="Diane Slota"   (tracked changes WITH authorship)
word/numbering.xml          present
word/media/                 7 files, matching 7 <w:drawing>
154 × <w:br>                soft returns preserved
```

That document carries 54 comments from six named people and is not visible to the current
exporter at all.

## Decision

**The export JSON is built by a local Python tool from a downloaded `.docx`.**

1. **Source artifact.** `https://docs.google.com/document/d/<docId>/export?format=docx`, constructed
   from a document ID alone. This endpoint was verified to work for *both* Google-native documents
   and Drive-hosted `.docx` files, so no mimeType probe or endpoint branch is required. (The Drive
   *REST* API does require branching — `files.export` for native, `files.get?alt=media` for binary
   — but the cookie/web endpoint does not.)
2. **Authentication.** The shared Playwright storage state resolved by
   `scn.session.resolve_auth_file` (`~/.playwright/sdonaldson.json`), reusing
   `tests/helpers/download.py`'s session builder and its cookie-rotation refresh (gts-f3me.4,
   gts-85x3.1). See "Consequences" for what this costs.
3. **Parsing.** Local Python, stdlib `zipfile` + `xml.etree.ElementTree`. `python-docx` is
   available and appropriate for paragraph/run/table traversal, but **not** for comment ranges —
   its native comment support is weak and `w:commentRangeStart`/`End` handling is the whole point.
4. **Schema shape is preserved.** The schema version constant remains the contract, and the Python
   implementation targets the same output shape. That makes the existing GAS exporter a
   differential oracle: run both against the same Google-native document and diff. (The constant is
   renamed and the version bumped under gts-284o; this decision does not change the schema's
   *shape*, only where it is produced.)
5. **Comment anchoring comes from `w:commentRangeStart`/`w:commentRangeEnd`.** The four-tier
   quoted-text matching, its tuning constants (`COMMENT_MATCH_WINDOW_BLOCKS`,
   `COMMENT_FUZZY_MIN_SCORE`, `COMMENT_FUZZY_MIN_MARGIN`), and the `unmatched` bucket are retired,
   not ported.
6. **A multi-tab document warns loudly and processes what it can — it does not fail.** See
   Consequences.
7. **The existing GAS exporter is preserved, not retired.** It stays in place and keeps its
   in-document Extensions-menu entry points. Its purpose is now twofold: it remains the only
   user-invocable export surface, and it serves as the **comparison baseline** for the Python
   implementation — run both against the same Google-native document and diff the JSON. It is
   frozen: preserved for comparison, not developed further.

## Rationale

- **Three heuristics become facts.** Comment→block association goes from four fallback tiers plus a
  manual-review bucket to exact ranges. Suggestion authorship goes from
  `confidence: 'low', basis: 'unverified'` to `w:author` read off the markup. `inferOrderedList_`'s
  `return null` ("we avoid inventing numbering") becomes an answer from `numbering.xml`. Deleting a
  heuristic is worth more than optimizing one, because every one of them is a place the artifact
  can be quietly wrong in a way an LLM consumer cannot detect.
- **It closes a corpus-coverage hole no amount of hardening reaches.** The Docs API cannot read a
  Drive-hosted `.docx`. This is architectural, not a bug to fix — and the corpus demonstrably
  contains such files, with real review activity on them.
- **Image extraction loses a failure mode.** `extractInlineImage_` currently fetches
  `imageProperties.contentUri` — a short-lived signed URL that must be retrieved during the same
  execution, with an explicit expiry-warning path when it isn't. In a `.docx` the bytes are already
  in `word/media/`. Reading a zip entry cannot expire.
- **`positionedObjects` come along for free.** Floating/anchored images are currently out of scope
  (only `inlineObjectElement` is handled); they are ordinary `w:drawing` elements with media
  entries in OOXML.
- **Library capability.** GAS has `Utilities.unzip` + `XmlService` and could technically do this;
  the local Python toolchain is materially better suited to OOXML traversal. This is the weakest of
  the reasons and is recorded last deliberately — it was the initial motivation, but it is not the
  one that justifies the change.

## Consequences

- **TOC deep links are lost.** `processTableOfContents_` currently reads
  `textStyle.link.heading.{id, tabId}` and emits clickable
  `docs.google.com/document/d/<id>/edit#heading=<id>` URLs — a citation a human can follow back to
  the live document. A `.docx` TOC carries Word-generated `_Toc…` bookmarks instead, which do not
  map to Google heading IDs. `document.toc[].url` therefore degrades to `null` unless a separate
  Docs API call is retained purely to recover heading IDs.
- **Tab boundaries are lost, and the behavior is unverified.** OOXML has no equivalent of a Google
  Docs tab, so `location.tab_id` cannot be derived from the `.docx`. What Google's converter does
  with a multi-tab document — concatenate, emit only the first tab, or something else — has not
  been tested (gts-11rq). No corpus document currently uses tabs. **The pipeline warns loudly and
  continues rather than failing**: a hard failure would assume the worst-case converter behavior
  without evidence and would turn a partially-usable document into no output at all, which is worse
  for corpus coverage than annotated partial content. The warning is emitted on two channels —
  `diagnostics.warnings[]`, so it travels with the artifact to the LLM consumer, and stderr, so the
  operator running the pull sees it — and it must instruct the reader to **verify what was actually
  downloaded**, not merely note that tabs were present. `diagnostics.tabs_detected` carries the
  count as a structured field. This follows the exporter's established posture for
  unreliable-but-usable output (unmatched comments, approximate page numbers, ambiguous color
  signals all warn and continue).
- **Cookie auth is accepted for now, with one known gap.** `download.py`'s proactive + reactive
  rotation refresh makes the shared storage state durable in practice. But cookies do not
  authenticate the Docs REST API, so the pipeline **cannot count tabs at all** — meaning today it
  cannot reliably emit the warning above for a Google-native document. Recorded as a limitation
  rather than resolved; obtaining an OAuth credential would close it and is the natural trigger for
  revisiting gts-11rq.
- **The two download endpoints disagree on comment count.** The 2026-08-25 probe returned 54
  comments via `/uc?export=download` and 55 via `/export?format=docx` on the same file; the
  2026-08-14 spike saw 62 in the `.docx` against 57 from the Drive Comments API. The most likely
  explanation is stored-bytes versus live-render, but it is unexplained. `/export?format=docx` is
  chosen partly because current state is what an LLM corpus wants, but the discrepancy should be
  reconciled before the count is treated as authoritative.
- **Resolved-comment round-trip is unproven.** `word/commentsExtended.xml` is emitted and carries
  `w15:commentEx` entries, but the probe document had zero resolved comments, so whether a resolved
  comment appears with `w15:done="1"` or is omitted from the export entirely is untested. If
  omitted, `drive.comments.list` returns as a second source for that field alone.
- **Open hardening beads need re-triage before they are worked.** `gts-g21w` is explicitly
  "comment-match tiers 2-4" — hardening tests for machinery this decision retires. `gts-2k9h`,
  `gts-e7ca`, `gts-wido` and `gts-r40j` target the same implementation. Working them as written
  would invest test effort in code scheduled for deletion.
- **Two implementations now exist against one schema, and that is deliberate.** The GAS exporter
  keeps the in-document Extensions-menu surface a local Python tool cannot provide
  (`ExportProgressDialog.html`, the universalActions handlers, `ExportFolderMap.js`'s export-folder
  isolation, the runs-as-clicking-user permission model), and doubles as the differential oracle for
  the Python implementation. The cost is that the two will diverge in output — by design, since the
  Python side anchors comments correctly and the GAS side guesses. **The diff is the deliverable,
  not a defect**: every difference is either a Python-side gain (a comment moving out of
  `unmatched`, an author appearing where `possible_authors` guessed) or a Python-side regression
  (TOC `url` going `null`, `tab_id` absent). Expect and classify them rather than driving the diff
  to zero.
- **The frozen baseline needs no new hardening tests.** Because the GAS exporter is preserved but
  not developed, tests written to protect it against drift protect nothing — nothing will modify it.
  This is the basis on which `gts-g21w` was closed rather than reworked (2026-08-25). It does *not*
  apply to coverage of behavior the Python implementation must also satisfy, which is portable and
  should be carried forward instead (see `gts-qjkj`).

## Open questions this ADR does not resolve

- **Block-correlation contract.** Mapping `w:commentReference w:id` and surrounding run positions
  onto the existing `block__<tab>__<start>__<end>` identity scheme is the substantive design work
  this ADR authorizes but does not specify. OOXML run offsets and Docs API structural indices are
  different coordinate systems; the ID scheme may need to change, which is a schema-version
  question. Needs its own `[INF]` design bead before implementation starts.
- **Multi-tab converter behavior** — gts-11rq, deferred by decision.
