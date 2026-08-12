# Policy JSON Exporter — Requirements

## 1. Purpose

Create a reliable, machine-readable JSON representation of a Google Docs policy manual for use in an LLM/RAG project while preserving enough structure and review metadata to distinguish:

- the **baseline** text,
- text proposed for insertion,
- baseline text proposed for deletion,
- manually struck-through deletion text,
- historical/superseded material retained in the working document,
- editorial/drafting notes,
- comments and comment threads,
- policies, procedures, charters, exhibits, articles, headings, labeled paragraphs, and lists,
- locations that help a human reviewer find the source text in the Google Doc/PDF.

The exporter must not collapse revision information into a single plain-text representation. The JSON is intended to be the canonical interchange format for downstream LLM ingestion and retrieval.

## 2. Context

The policy manual is maintained in Google Docs as a working document. Editing conventions include several overlapping mechanisms:

1. Existing/baseline language that remains unchanged.
2. Google Docs **Suggested insertions**.
3. Google Docs **Suggested deletions**.
4. Manual **strikethrough formatting** used to indicate text proposed for deletion.
5. Whole policies or procedures explicitly marked as old, superseded, or retained for comparison.
6. Drafting/editorial notes mixed into the document.
7. Google Docs comments and replies used during review.
8. Governance-specific document structure, including policies, procedures, charters, articles, exhibits, labeled paragraphs such as `Intent:` or `Authority:`, and enumerated or bulleted lists.

The representation must support queries such as:

- What does the baseline say about a topic?
- What would the proposed version say?
- What language is proposed for deletion?
- Which deletions are strikethrough versus Google Docs suggestions?
- What additions are proposed?
- Which comments concern a particular policy, procedure, or paragraph?
- Which unresolved comments affect proposed changes?
- Show the baseline and proposed version of a section side by side.
- Where in the source document can a reviewer find the cited language?
- Which policies contain a particular `Authority:`, `Intent:`, or `Custodian:` statement?
- What does item 4 of a specific procedure require?

## 3. Terminology

### 3.1 Baseline

**Baseline** means the text against which the proposed revision is being evaluated.

It must not be described as "current policy" because the working document may contain drafts, superseded sections, or material whose formal governance status differs from its editing status.

### 3.2 Proposed view

The **proposed view** is reconstructed by:

- including unchanged baseline text,
- including proposed insertions,
- excluding proposed deletions.

### 3.3 Baseline view

The **baseline view** is reconstructed by:

- including unchanged baseline text,
- including text proposed for deletion,
- excluding proposed insertions.

Manual strikethrough is treated as baseline text proposed for deletion unless explicitly overridden by a semantic classification rule.

## 4. Source APIs

The implementation may use the Google Docs API and Google Drive API.

Use `documents.get` with:

- `suggestionsViewMode=SUGGESTIONS_INLINE`, so unresolved suggestions are represented inline;
- `includeTabsContent=true`, so all document tabs can be processed.

Google Docs API `TextRun` and other structural elements may expose `suggestedInsertionIds` and `suggestedDeletionIds`. These must be preserved.

Use Google Drive API Comments to capture stable comment metadata, including comment content, replies, resolved state, author, timestamps, quoted file content, and the Drive anchor where available.

Native comment/suggestion range APIs that are only in Developer Preview are not required for this implementation.

## 5. Required JSON Model

The exporter must produce one canonical JSON file.

Recommended top-level structure:

```json
{
  "schema_version": "2.1",
  "generated_at": "...",
  "document": {
    "suggestion_groups": []
  },
  "semantics": {},
  "page_numbering": {},
  "suggestion_authorship": {},
  "units": [],
  "comments": [],
  "views": {},
  "diagnostics": {}
}
```

`semantics`, `page_numbering`, and `suggestion_authorship` are self-describing companions to the schema, restating for the consuming LLM what `units[].semantic_state`, `location.page`/`page_basis`/`page_approximate`, and `document.suggestion_groups` mean and their known limitations — see §6.4 and §18. Each unit additionally carries `parent_unit_id` (§14.1) and `color_signals` (§6.4).

## 6. Revision Model

Revision semantics and evidence must be separate.

Each textual run should contain a simple semantic status plus evidence explaining why it was classified that way.

Example unchanged baseline run:

```json
{
  "text": "Northlake supports ",
  "revision": {
    "state": "baseline",
    "change": "unchanged",
    "evidence": []
  }
}
```

Example Google Docs suggested deletion:

```json
{
  "text": "members",
  "revision": {
    "state": "baseline",
    "change": "deleted",
    "evidence": [
      {
        "type": "google_docs_suggestion",
        "suggestion_ids": ["..."]
      }
    ]
  }
}
```

Example manual strikethrough deletion:

```json
{
  "text": "members",
  "revision": {
    "state": "baseline",
    "change": "deleted",
    "evidence": [
      {
        "type": "strikethrough"
      }
    ]
  }
}
```

Example proposed insertion:

```json
{
  "text": "everyone",
  "revision": {
    "state": "proposed",
    "change": "inserted",
    "evidence": [
      {
        "type": "google_docs_suggestion",
        "suggestion_ids": ["..."]
      }
    ]
  }
}
```

### 6.1 Supported semantic states

At minimum:

- `baseline`
- `proposed`
- `historical`
- `editorial`

### 6.2 Supported changes

At minimum:

- `unchanged`
- `inserted`
- `deleted`

### 6.3 Evidence types

At minimum:

- `google_docs_suggestion`
- `strikethrough`
- `text_pattern`
- `style_pattern`
- `manual_rule`

A run may have more than one evidence item. A Google Docs suggested deletion takes precedence over strikethrough for classification, but both evidence items may be retained.

### 6.4 Multi-contributor signals

Reviewers commonly use manual highlight colors to distinguish different people's or different rounds' proposed edits, in addition to (or instead of) Google Docs' own suggestion mechanism. The exporter has no advance knowledge of a color-to-person mapping, and that mapping is not guaranteed stable across the document — the same color may mean different things in different sections. Given that constraint, the exporter surfaces two signals of different reliability rather than attempting to resolve identity itself:

1. **`document.suggestion_groups` — reliable, document-wide.** One entry per distinct Google Docs `suggestion_id` found anywhere in the document (`run_count`, `block_ids`, `first_location`, `last_location`). A shared suggestion ID means the same literal Docs edit action, regardless of section, even though the API does not expose *who* performed it (§18). Each group also carries `possible_authors`: names pulled from Drive comments whose `associated_block_ids` overlap the group's `block_ids`, each explicitly labeled `confidence: "low"`, `basis: "co-located comment, unverified"`. This is a hint, not a resolved identity.
2. **`unit.color_signals` — local clustering hint only, scoped per unit.** The distinct `(foreground_color, background_color)` pairs observed within that unit's blocks, with `run_count` and `block_ids`. There is no document-wide color legend and no `label` field to fill in — the exporter does not assert that a color means the same thing in two different units. Every export where any non-default color is detected carries a permanent `diagnostics.warnings` entry restating this.

Consuming LLMs comparing or summarizing multiple contributors' proposals should treat `suggestion_groups` as ground truth for "same edit action" and `color_signals` + comment proximity as supporting, section-local evidence only — never as a standalone identity signal.

Each colored run also carries `revision.evidence` of `{ type: 'style_pattern', rule: 'manual_highlight_color', foreground_color, background_color }` regardless of whether color affected baseline/proposed classification (it does not — see §9) — this is what feeds `unit.color_signals` and lets a consumer trace a specific run back to its color evidence.

## 7. Semantic Structure

Document structure must not be inferred later by the LLM when it can be captured during preprocessing.

### 7.1 Governance units

Recognize, where possible:

- `document_part`
- `section`
- `policy`
- `procedure`
- `charter`
- `article`
- `exhibit`
- `standing_rules`
- `organizational_chart`
- `glossary`

Text-pattern recognition should supplement Google Docs heading styles. Examples include:

- `Church Policy 04: Member Meetings`
- `Church Procedure 04-01: Member Meeting Guidelines`
- `Board Safety Policy 02: Conflict Management`
- `Board Safety Procedure 02-03: Board Intervention`
- `CABINET CHARTER`
- `ARTICLE TEN – BOARD & OFFICERS`
- `EXHIBIT C`

### 7.2 Content blocks

Recognize:

- `heading`
- `paragraph`
- `labeled_paragraph`
- `list`
- `list_item`
- `table`
- `table_cell`
- `editorial_note`
- `historical_note`

### 7.3 Labeled paragraphs

A paragraph beginning with bold text followed by a colon should normally be represented as a `labeled_paragraph`.

Examples:

- `Intent:`
- `Purpose:`
- `Authority:`
- `Schedule:`
- `Method:`
- `Custodian:`
- `Historical Note:`
- `Accountability:`
- `Collaboration:`
- `Reporting:`

Store the label separately from its content.

Example:

```json
{
  "kind": "labeled_paragraph",
  "label": "Intent",
  "runs": []
}
```

### 7.4 Pattern rules (implementation pointer)

All text-pattern/heading heuristics referenced in this section — governance-unit recognition (§7.1), historical/editorial detection (§11) — live together in one bannered code region in `src/Procedure-Exporter.js`: `GOVERNANCE_UNIT_PATTERNS`, `HEADING_FALLBACK_BASE_RANK`, and `SEMANTIC_STATE_PATTERNS`, immediately following the schema-version constant. Each rule has a stable `name`/`rule` identifier that appears verbatim in the exported `text_pattern`/`style_pattern` evidence (§6.3), so any classification in the JSON can be traced back to exactly one line in that region. Keep this doc's examples and that region in sync — do not add a new pattern in one without the other.

## 8. Lists

Do not flatten enumerated or bulleted lists into ordinary paragraphs.

Preserve:

- list ID,
- nesting level,
- ordered versus unordered classification where determinable,
- item sequence within the exported document,
- each list item as an addressable block,
- revision runs inside each item.

The exact displayed glyph/number generated by Google Docs is not always available directly from the paragraph content; where exact numbering cannot be recovered reliably, preserve list ID, nesting level, and source order rather than inventing a displayed number.

## 9. Formatting Metadata

Retain formatting that may aid interpretation or auditing, including:

- bold,
- italic,
- underline,
- strikethrough,
- foreground color,
- background color,
- hyperlink.

Formatting is evidence, not the primary semantic model. For example, red text should not automatically mean `proposed` unless a configured project rule explicitly says so.

## 10. Comments

Export comments separately from governance text.

For each comment capture, where available:

- ID,
- author,
- created timestamp,
- modified timestamp,
- resolved/unresolved state,
- comment text,
- quoted source text,
- Drive anchor,
- replies and reply authors/timestamps,
- a best-effort association to an exported block based on quoted text.

Comments must never be included in baseline or proposed governance text views.

### 10.1 Comment-to-document traceability

The Drive Comments API `anchor` field is not a usable location anchor: it is an opaque, undocumented "kix" encoding, and it is addressed in a scheme unrelated to the Docs API's `startIndex`/`endIndex` offsets used everywhere else in this schema. There is no supported way to decode it into a block location. Quoted-text matching against exported block text is therefore the only mechanism available, and it is tiered to fail closed rather than guess silently:

1. `quoted_text_exact` — the normalized quote is a substring of exactly one block's `all_text`, or `quoted_text_multiple` if it matches more than one.
2. `quoted_text_prefix` — the first 80 normalized characters of the quote match exactly one block (Drive sometimes truncates `quoted_file_content.value`).
3. `quoted_text_multiblock` — the quote spans a paragraph boundary; a sliding window of up to 3 consecutive blocks within the same unit is joined and tested.
4. `quoted_text_fuzzy` — last resort. Jaccard word-overlap against every block's text, accepted only when the best match clears a minimum score and leads the runner-up by a minimum margin (see `COMMENT_FUZZY_MIN_SCORE`/`COMMENT_FUZZY_MIN_MARGIN` in `src/Procedure-Exporter.js`).
5. `unmatched` — no tier produced an acceptable match. `associated_block_ids`/`associated_unit_ids`/`section_path` are empty; the comment needs manual review. `diagnostics.unmatched_comments` counts these and a `diagnostics.warnings` entry is added whenever the count is nonzero.
6. `no_quoted_text` — the comment has no `quoted_text` (e.g. a document-level or non-text-anchored comment) — matching was never attempted.

Text normalization folds curly quotes/dashes/ellipsis to plain ASCII equivalents and strips a leading/trailing ellipsis before comparison, since Drive's `quoted_file_content.value` frequently differs from the source text only cosmetically.

Each comment carries the full traceability chain derived from its matched block(s), so an LLM can go from a comment to the exact document location and back:

- `associated_block_ids` — the matched block ID(s).
- `associated_unit_ids` — the unit ID(s) (policy/procedure/section) those blocks belong to.
- `section_path` — the root→leaf breadcrumb of ancestor units for the primary matched block, e.g. `[{id, kind: "policy", title: "..."}, {id, kind: "procedure", title: "..."}]`.
- `citation_hint` — the human-readable citation of the primary matched block (page, unit title, label).

The reverse direction — retrieving a section and seeing what comments apply to it — does not require re-deriving the association: every `block` carries `comment_ids`, and every `unit` carries an aggregated `comment_ids` (the union of its blocks' comment IDs), so a unit fetched by ID already lists which comments (by ID, looked up in the top-level `comments` array) apply anywhere within it.

## 11. Historical and Editorial Material

The exporter should apply conservative text-pattern classification for obviously non-operative drafting material, for example:

- headings beginning with `(OLD)` → `historical` candidate;
- paragraphs beginning with `END -`, `FYI -`, `NOTE:`, or containing obvious drafting placeholders such as `TBD`, `????`, or `link??` → `editorial` candidate.

These classifications should be recorded as heuristic and reviewable. The exporter should not silently remove such content.

## 12. Location and Reviewer Navigation

Every meaningful block should contain location metadata.

At minimum:

```json
{
  "location": {
    "tab_id": "...",
    "tab_title": "...",
    "start_index": 8432,
    "end_index": 8579,
    "page": 76,
    "page_basis": "...",
    "page_approximate": false
  }
}
```

`page_approximate` is `true` only while no explicit page break has yet been seen in the current tab — i.e. `page` is still the untouched default rather than an explicit count. It is `false` once explicit page-break counting has started informing `page` for that location. It is not a guarantee against reflow past that point; the residual "may still diverge from final rendered pagination" risk is carried once, document-wide, in `diagnostics.warnings` (§12.1), not repeated per-location.

Also generate a human-readable `citation_hint` when possible, such as:

`Governance Manual, p. 76, Board Safety Policy 02: Conflict Management, Intent`

### 12.1 Page-number limitation

Google Docs exposes document structure, explicit page-break elements, and page-number `AutoText` fields in headers/footers, but it does not provide a general API mapping from every body-text range to its final rendered page after pagination.

Therefore page numbers in this exporter are **best effort** unless the document contains enough explicit page-break structure to map pages deterministically.

The exporter should:

1. Track explicit page breaks and increment a page counter.
2. Record `page_basis="explicit_page_break_count"` when based on that method.
3. Mark page values as approximate when flowing text can repaginate without explicit breaks.
4. Preserve start/end indexes and hierarchy even when page mapping is approximate.
5. Optionally export a PDF copy for human review, but exact PDF text-to-page alignment is outside the required scope of this Apps Script because Apps Script does not natively parse PDF text positions.

A future production enhancement may align exported block text against a PDF-derived text layer outside Apps Script to assign exact rendered page numbers.

## 13. Derived Views

Generate, at minimum:

- `views.baseline_text`
- `views.proposed_text`
- `views.deleted_text`
- `views.proposed_additions`

Per block/unit, also generate:

- `all_text`
- `baseline_text`
- `proposed_text`

### 13.1 Baseline reconstruction

Include:

- unchanged baseline,
- suggested deletions,
- strikethrough deletions.

Exclude:

- proposed insertions,
- editorial/historical material unless the consumer explicitly requests it.

### 13.2 Proposed reconstruction

Include:

- unchanged baseline,
- proposed insertions.

Exclude:

- suggested deletions,
- strikethrough deletions,
- editorial/historical material unless explicitly requested.

## 14. Stable IDs

Every unit and block must have an ID.

Indexes in Google Docs are useful source locators but are not permanent identifiers because edits can move them. The exporter should therefore generate deterministic IDs using a combination of:

- tab ID,
- unit type,
- normalized title where available,
- source index as a final disambiguator.

Example:

`t0__policy__board-safety-policy-02-conflict-management__7601`

For unnamed paragraphs, an index-based block ID is acceptable.

### 14.1 Unit hierarchy

Governance units nest (Article → Charter/Policy → Procedure → generic heading sections), and downstream queries ("which procedures belong under Policy 02") depend on that containment being recoverable. Each unit therefore carries `parent_unit_id` (nullable): the ID of the nearest preceding unit with a strictly lower heuristic nesting rank, per §7.4's pattern table. This is a best-effort structural inference, not a guarantee — a document that mixes conventions inconsistently (e.g. a Procedure at the same heading level as its parent Policy) can produce a flatter or misattributed hierarchy. Consumers needing certainty should cross-check `parent_unit_id` against `source_order` and `location` rather than trusting it blindly for edge cases.

Each block conversely carries `unit_id`, naming the unit it belongs to — the inverse edge of `unit.blocks[]` — so a block reached independently (e.g. via a comment's `associated_block_ids`, §10.1) can be walked back up to its unit and, from there, its `parent_unit_id` chain to the containing policy/procedure without a linear scan of `units[]`.

## 15. Output

The script must:

1. Run inside the shared GActionSheet Workspace Add-on's single clasp project (same script as `MenuHandler.js` / `WorkspaceAddonCard.js`) — it does **not** get its own bound-script project, and it must never define its own `onOpen()`: that collides with `MenuHandler.js`'s `onOpen()` in the same script and silently breaks whichever one loses.
2. Expose two entry points as add-on **universal actions** under the Extensions menu (`appsscript.json` `addOns.common.universalActions`): "Export Governance JSON" and "Export JSON + PDF Snapshot". These are the add-on's Extensions-menu items, not a Docs custom menu and not a homepage-card button.
3. Export one JSON file to the same Drive folder as the source Google Doc when possible.
4. Present a Drive file link for the exported JSON via a CardService result card (universal actions cannot show an `HtmlService` modal dialog).
5. Optionally export a PDF snapshot into the same folder, linked from the same result card.
6. Never modify the source document.

Suggested output names:

- `<document-name>-governance.json`
- `<document-name>-snapshot.pdf`

## 16. Diagnostics

The JSON should include diagnostics such as:

- number of tabs processed,
- number of units,
- number of blocks,
- number of runs,
- number of proposed insertions,
- number of suggested deletions,
- number of strikethrough deletions,
- number of comments,
- number of unresolved comments,
- number of blocks classified as editorial/historical,
- number of explicit page breaks,
- warnings about approximate page mapping.

## 17. Safety and Fidelity Principles

1. Preserve source text exactly in `runs[].text`.
2. Do not silently correct spelling, punctuation, grammar, numbering, or duplicated text.
3. Do not infer governance approval status from revision formatting.
4. Do not treat comments as governance text.
5. Do not discard deleted, historical, or editorial material.
6. Prefer explicit evidence over heuristic classification.
7. Keep enough source metadata to audit how a classification was produced.
8. Keep baseline/proposed derivation deterministic so different LLMs receive the same source representation.

## 18. Google API Assumptions

This design assumes the current Google Workspace APIs support:

- `documents.get` with `suggestionsViewMode` and `includeTabsContent`;
- inline suggestion metadata such as suggested insertion/deletion IDs;
- tabs and nested tabs;
- paragraph structural elements including text runs, page breaks, and AutoText;
- Drive Comments API access to comment content, replies, resolved status, quoted content, and anchors.

The script intentionally avoids requiring Developer Preview comment/suggestion thread APIs.

**Known limitation — suggestion authorship.** `documents.get` does not attach an author or timestamp to a `suggestedInsertionIds`/`suggestedDeletionIds` value. There is no supported way to resolve "who proposed this suggestion" from the Docs API alone. The exporter works around this by (a) grouping runs by suggestion ID as an identity-agnostic but reliable "same edit action" signal (`document.suggestion_groups`, §6.4), and (b) attaching comment-author names found in the same blocks as a labeled, unverified hint. A future enhancement could improve on (b) using the Drive Activity API to correlate suggestion timestamps with actor events, but that is out of scope here — same treatment as the PDF-page-mapping limitation in §12.1.
