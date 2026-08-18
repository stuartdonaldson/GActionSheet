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
  "schema_version": "2.3",
  "generated_at": "...",
  "document": {
    "suggestion_groups": [],
    "toc": []
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

**Current implementation gap.** `table`/`table_cell` are not emitted as block
`kind`s today. A table cell's content is walked like any other structural
content, and each resulting block (of its own natural kind — `paragraph`,
`heading`, `list_item`, etc.) is tagged with an ad hoc `block.table = {row,
column}` field (`processTable_`, `src/Procedure-Exporter.js`). This preserves
row/column position within a single table but has no table identity, no
row/column count, and no merged-cell (rowSpan/colSpan) support — see §19.1
for the proposed replacement.

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

### 7.5 Table of contents (`document.toc`, gts-6cq2 follow-up)

A Google Docs `tableOfContents` structural element's lines must **not** be run through §7.1's governance-unit recognition — a TOC line's rendered text (`"Board Policy 1: X<TAB>9"`) matches the same `GOVERNANCE_UNIT_PATTERNS` as the real heading it points to, and would otherwise be emitted as a second, fake `policy`/`procedure` unit at the TOC's location in the document (confirmed live: a real 9.27MB sample export had 8 duplicate unit titles from exactly this cause before the fix). TOC lines are diverted entirely to a separate `document.toc` array and never enter `units`/`blocks`.

Each entry:

```json
{
  "title": "Article Two – Purpose and Values",
  "displayed_page": "9",
  "target_tab_id": "t.0",
  "target_heading_id": "h.ce05jcblmxdp",
  "url": "https://docs.google.com/document/d/<docId>/edit?tab=t.0#heading=h.ce05jcblmxdp"
}
```

- `title` / `displayed_page` — split from the TOC line's rendered text on its last tab character (Docs renders `"Title<TAB>PageNumber"`; the last-tab split guards against a title that itself contains a tab).
- `target_heading_id` / `target_tab_id` — a Google Docs TOC entry's link-bearing run carries `textStyle.link.heading.{id, tabId}` pointing directly at the target heading. This is a **direct API-provided link**, not a text/position match — confirmed live via `src/SPIKE-CommentPosition.js`'s `toc_probe` op (gated, disabled by default, same inert-until-enabled pattern as the other spike routes) against a real document. `null` if the TOC line carried no link (has not been observed, but not assumed impossible).
- `url` — a ready-to-use deep link into the source document at the target heading. Omitted (`null`) when `target_heading_id` is null.

`document.toc` is omitted entirely (not `[]`) when the document has no TOC — same "absence means none found" convention as §13.4's array fields. `diagnostics.toc_entries` counts entries found.

An LLM consumer may use `document.toc` to answer "what page is X on" or "link me to section Y", but must not treat it as operative governance content — it carries no `revision`/`semantic_state` and is not a substitute for the real unit at its target.

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

### 10.2 Feasibility spike: position resolution beyond quoted text (gts-6ls9)

Prompted by a real export where 100% of comments (57/57) had `quoted_text: null`, this spike re-examined the two scope exclusions in §4/§18 and the `anchor` field's assumed opacity, live against the account and sample document that produced that export (`docId 1zQkR...`, via a temporary, gated `doPost` spike route — `src/SPIKE-CommentPosition.js`, disabled by default, same inert-until-enabled pattern as `src/SPIKE.js`). **Verdict: no viable mechanism found. Stay with quoted-text-only + honest `no_quoted_text` diagnostics (gts-rdi3).**

1. **Docs API Developer Preview comment/suggestion-range endpoints — no-go, confirmed exists-or-not.** A full-tree scan of a live `documents.get` response (`suggestionsViewMode=SUGGESTIONS_INLINE`, `includeTabsContent=true`) for any key containing `comment` or `anchor` returned zero hits across all 5 top-level keys (`title`, `documentId`, `revisionId`, `suggestionsViewMode`, `tabs`). The Docs API v1 surface — Developer Preview or GA — carries no comment representation at all; there is nothing to opt into. Cost: N/A, nothing to bring into scope. §4/§18's exclusion stands, now on a confirmed rather than assumed basis.
2. **Drive Activity API — not live-tested; reasoned no-go.** Enabling it requires a new OAuth scope + advanced service on the production Apps Script project, which needs GCP Console access this session doesn't have; the user declined to pursue live verification given the added-scope cost. Reasoning from documentation: Drive Activity API v2 reports actor/timestamp/target events at the *file* level (edits, comments, moves) with a `SingleEventType` timeline, not a text-range payload — there is no field that would put a comment at a paragraph or block position, only "some edit event occurred near this time." At best it would replicate `document.suggestion_groups.possible_authors` (§6.4) — an unverified, low-confidence proximity hint, same trust tier as what already exists — for a new scope-creep and quota cost. Not worth building even if it works as documented. **No-go, without live confirmation the AC would otherwise require** — flagged here rather than silently assumed.
3. **`anchor` field structure — confirmed opaque, no decodable structure.** All 57 anchors in the sample document are `kix.<token>` (one exception, `kix.cmt0`, a short generic-looking value with no correlation to position or content — further evidence these are internal object-reference IDs, not encoded offsets). Sorting all 57 by `createdTime` shows no correlation between token value and creation order, let alone document position — tokens are opaque per-comment object IDs assigned at creation time, not a position/range encoding. Drive API v2's legacy `Comments.list` (a different resource shape, `context` instead of `quotedFileContent`) was also checked in case it decoded or exposed anchors differently: identical `kix.<token>` values, `context: null` for all 57 — same underlying anchor, no additional structure. A live stability-under-edit test (insert a throwaway comment, edit the doc, refetch, confirm the anchor is unchanged) was in scope but not run — the user declined write access to the sample doc for this spike, so it stays reasoned-not-confirmed: an opaque object-reference ID has no positional information to invalidate on edit, consistent with the token-randomness result above, but this specific claim is not itself live-verified.
4. **Different `Comments.list` params/API version — ruled out, confirmed live.** Drive API v2 (`context.value`, the legacy pre-v3 quoted-text field) was queried side by side with v3 (`quotedFileContent.value`) for the same 57 comments: both return null for all 57. The null result is not a v3-specific artifact or a parameter/fields-mask omission — Drive itself has no quoted text for this document's comments, confirming the root-cause hypothesis in gts-rdi3 (long-lived, heavily-edited document; Drive's own anchor resolution has fallen too far behind the edit history to still produce a quote).

No candidate produces an exact position; the one candidate with any signal at all (Drive Activity API) would only ever reach the same "unverified, low-confidence, co-location hint" tier §6.4 already assigns to `possible_authors` — not a new anchoring tier. This confirms §10.1 as still the complete answer for this schema version: quoted-text matching (tiers 1–4) is the only mechanism, `unmatched`/`no_quoted_text` (tiers 5–6, with gts-rdi3's now-visible diagnostics) is the correct fail-closed behavior, and no further association work is scoped here.

**Re-check (2026-08-14):** an external review raised two specific mechanisms candidates 3/4 above hadn't exercised at that exact grain — re-tested live against the same sample document via a new spike op (`gemini_recheck`), both no-go:

- **`includeDeleted: true` on `Comments.list`.** The original candidate-4 pass (v2 vs. v3) had `includeDeleted` hardcoded `false` throughout — never actually varied. Re-run with `includeDeleted: true` alongside `false`: identical result, 57/57 `quotedFileContent` still null, `deleted_count: 0` (no deleted/resolved comments were the hidden cause). Confirms candidate 4's conclusion on the one param that hadn't been literally toggled.
- **Decoding `anchor` as `JSON.parse(anchor).m` → `JSON.parse(m).q`.** This targets the `json_revision_anchor` form (anchors starting `{`) that candidate 3 had already classified but not JSON-decoded. On this document the form doesn't occur at all: all 57 anchors re-checked are `kix.<token>` (`anchor_json_revision_form_count: 0`) — the decode path candidate 3 flagged as worth checking has no anchors to apply to here. Not a disproof of the technique in general (a document with legacy-anchor-form comments might decode differently), but there is nothing on this account/document for it to recover.

Verdict unchanged: quoted-text-only, §10.1, stands.

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

Generate, at minimum, at the top level:

- `views.deleted_text`
- `views.proposed_additions`

and, when `options.includeWholeDocumentViews === true` (default `false` — opt-in; ~7% of a representative export's bytes on top of §13.3's per-block dedup, and most consumers work a section at a time, not the whole document):

- `views.baseline_text`
- `views.proposed_text`

The baseline/proposed pair are whole-document reconstructions in reading order and are exempt from the per-block conditional-emission rule in §13.3 — they exist specifically to answer "show the baseline/proposed version of the document" (§2) without the consumer reassembling one from per-block fields, and their overlap with each other on unchanged text is intentional (§3.2/§3.3 both include unchanged baseline). `deleted_text`/`proposed_additions` are much smaller extracts (not whole-document reconstructions, no equivalent duplication concern) and are always included regardless of the option.

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

### 13.3 Per-block text (canonical vs. derived views)

Every block carries `runs[].text` unconditionally (§17.1) — that is always the exact source text and never omitted. The block-level convenience fields are conditional:

- If the block has no revision activity (`revision_summary === "unchanged"`): emit a single canonical field, **`text`** — the concatenation of its runs' text. Do not also emit `all_text`, `baseline_text`, or `proposed_text`; they would be byte-identical to `text` and to each other.
- If the block has any revision activity (`revision_summary` is `"insertions"`, `"deletions"`, or `"mixed"`): emit **all three** of `all_text`, `baseline_text`, `proposed_text`, unconditionally, and omit `text`. Do not attempt finer per-field suppression (e.g. omitting `all_text` when it happens to equal `baseline_text` for a deletion-only block) — the byte savings are marginal (~4 points on a representative export) and it forces the consumer to infer, from `revision_summary`, which of the three fields is safe to skip. A block either needs the single canonical string or all three views; there is no third case.

A consumer reading a block's text should therefore branch once on presence of `text` vs. the `all_text`/`baseline_text`/`proposed_text` trio, not assume all four keys are always present. `revision_summary` (§6, unchanged/insertions/deletions/mixed) tells the consumer which shape to expect before it looks.

**Downstream implementation note:** anything that currently reads `block.all_text` unconditionally (comment quoted-text matching, §10.1; the top-level `views.*` builders, §13) must fall back to `block.text` when `all_text` is absent.

### 13.4 Omitting empty structural arrays

The following fields are omitted from a unit/block entirely when they would be empty, rather than emitted as `[]`; absence has the same meaning as an empty array (no evidence, no comments, no color signals found):

- `kind_evidence`
- `semantic_state_evidence`
- `color_signals`
- `comment_ids`
- `runs[].revision.evidence`

Scalar and nullable structural fields — `id`, `kind`, `title`, `parent_unit_id`, `label`, `named_style`, `heading_level`, `list`, `location`, `unit_id` — are **always present**, including when their value is `null`. These define the fixed shape of a unit/block object; `null` here is a meaningful value (e.g. "no parent unit"), not a stand-in for "nothing to report," and omitting the key would make the object shape vary per instance for negligible byte savings. Do not extend the omission rule to these fields.

### 13.5 Text normalization (derived text only)

`runs[].text` is the exact source text, byte-for-byte, always (§17.1) — never normalized. The derived/concatenated fields built from it (block `text`, `all_text`/`baseline_text`/`proposed_text`, `views.*`) apply two cosmetic substitutions, since both look like unrecognizable noise to a downstream LLM reader while carrying no operative meaning of their own:

- Non-breaking space (`U+00A0`, common in pasted content) → plain space (`U+0020`).
- Vertical tab (`U+000B`, Google Docs' internal encoding for a Shift+Enter soft line break within a paragraph — a real, meaningful break, not noise) → `\n`.

If exact source bytes are required (e.g. reproducing formatting precisely), read `runs[].text` — do not assume the derived fields are unmodified copies of it.

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
3. Export one JSON file to the document's **isolated export folder** (§15.1), not the source Google Doc's own folder.
4. Present a Drive file link for the exported JSON via a CardService result card (universal actions cannot show an `HtmlService` modal dialog).
5. Optionally export a PDF snapshot into the same export folder, linked from the same result card.
6. Never modify the source document.

Suggested output names:

- `<document-name>-governance.json`
- `<document-name>-snapshot.pdf`

### 15.1 Export folder isolation (gts-z6j0)

Export output (JSON, PDF snapshot, and any future image-extraction/docx-cache
artifacts, §19.3/§19.4) is written into a per-document folder isolated from
the source document, not into the source document's own parent folder —
users with access to the source folder should not see export byproducts.

- A single well-known Script Property, `EXPORT_ROOT_FOLDER_ID`, names a Drive
  folder configured once per deployment (`local.settings.json`'s
  `exportRootFolderId`, pushed at `deploy:test` via `set_export_config` —
  `manage-deployments.js`'s `registerExportConfig()`, mirroring
  `registerAxiomConfig()`).
- `getExportFolder_(documentId, title)` (`src/ExportFolderMap.js`) resolves,
  creating if necessary, a subfolder under that root named
  `<title> - <docId>` for the given document.
- Because document titles collide, the docId → folder mapping is **never**
  derived by name lookup. It is tracked in an index spreadsheet (`GActionSheet
  Export Index`, created inside the root folder; schema:
  `CONTRACT_SCHEMA.sheetExportIndex` in `src/ContractSchema.js` — Doc Id, Doc
  Title, Folder Id, Created At, Last Exported At, Meta Json). `Meta Json` is
  deliberately open-ended for other small per-export metadata (e.g. a future
  image-description cache index, §19.3), mirroring the `Config` sheet's
  Key/Value JSON-value convention.
- If `EXPORT_ROOT_FOLDER_ID` is unset, export falls back to writing into the
  source document's own parent folder (the pre-gts-z6j0 behavior) rather than
  failing — isolation is best-effort, not a hard requirement of the export
  path.
- `export_governance_json`'s WebApp response carries `exportFolderId` so a
  caller (including a test) can confirm which folder — isolated or fallback —
  received the output, without a direct Drive API call.

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
- number of TOC entries found (§7.5),
- warnings about approximate page mapping.

## 17. Safety and Fidelity Principles

1. Preserve source text exactly in `runs[].text`.
2. Do not silently correct spelling, punctuation, grammar, numbering, or duplicated text.
3. Do not infer governance approval status from revision formatting. `baseline` (in both `semantic_state` and `revision.state`) means only "pre-revision text used for comparison" — never "board-approved" or "current policy" (§3.1). Note the two fields use the word for different axes: `unit`/`block.semantic_state` classifies *content type* (baseline vs. historical vs. editorial material — never takes the value `proposed`), while `run.revision.state` classifies *revision-workflow state* (baseline vs. proposed, i.e. which side of a pending edit a run is on). A consumer must not conflate the two just because both can read `"baseline"`.
4. Do not treat comments as governance text.
5. Do not discard deleted, historical, or editorial material.
6. Prefer explicit evidence over heuristic classification. In particular, color (foreground/background) must never by itself determine `revision.state`/`revision.change` or `semantic_state` — classification comes from Google Docs suggestion metadata, strikethrough formatting, and text-pattern rules only (§6.3, §9). Color is captured as evidence (`revision.evidence` style_pattern entries, `unit.color_signals`) for human/LLM review, never as a classification input. Colored text may be ordinary formatting, a proposed alternative, or unrelated emphasis — the exporter does not assume which.
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

## 19. Proposed Enhancements (Not Yet Implemented)

Requirements staged here are not built. They are recorded so a future
implementer has a frozen contract to work against, and so this document
doesn't silently drift from what `src/Procedure-Exporter.js` actually does.
Move a subsection out of §19 and into its natural home (§7, §15, etc.) only
once the corresponding code ships.

### 19.1 Table structure and row/column relationships

**Current state (§7.2).** A table cell's content is walked like any other
structural content, and each resulting block is stamped with `block.table =
{row, column}`. This preserves position *within a single table* well enough
for a consumer that already knows it's looking at one table, but breaks down
as soon as a document has more than one table, or a table nested inside a
table cell — see the gaps below. There is also no `table`/`table_cell` block
`kind` despite §7.2 listing both.

**Gaps this proposal closes:**

1. **No table identity.** Two separate tables in the same document each
   produce blocks tagged `{row: 0, column: 0}` for their first cell, with
   nothing to disambiguate which table a given block's `.table` field refers
   to.
2. **No table dimensions.** Row count and column count are not captured
   anywhere in the output; a consumer must infer them by scanning every block
   for the highest `row`/`column` value seen, which is unreliable when a
   trailing row or column is entirely empty (produces no blocks at all).
3. **No merged-cell support.** Google Docs' `tableCellStyle.rowSpan` /
   `columnSpan` are never read. A merged cell is currently indistinguishable
   from an ordinary single cell that happens to be empty at the columns it
   visually spans.
4. **Nested tables lose their own row/column tagging.** `processTable_`
   tags every block produced while walking a cell's content — via a
   before/after slice of `ctx.allBlocks` — with that cell's `{row, column}`.
   If the cell's content includes a nested table, the nested table's own
   `processTable_` call runs first (correctly tagging its own blocks with
   its own row/column), but the *outer* table's tagging loop then runs over
   the same before/after range and overwrites those blocks with the outer
   cell's `{row, column}`, discarding the nested table's real position.

**Proposed shape.**

Add a top-level `document.tables` array, following the same "diverted
metadata, not part of `units`/`blocks`" convention `document.toc` already
established in §7.5:

```json
{
  "id": "table__t.0__142",
  "tab_id": "t.0",
  "row_count": 4,
  "column_count": 3,
  "header_row": true,
  "source_order": 12,
  "location": { "tab_id": "t.0", "start_index": 140, "end_index": 512 }
}
```

- `id` — stable, derived the same way as `makeUnitId_`/`makeBlockId_`
  (tab + structural start index), so it survives round-trips and can be
  cited from a block's `table.table_id` (below) without ambiguity even when
  a document has several tables.
- `row_count` / `column_count` — read directly from `table.tableRows.length`
  and `table.tableRows[0].tableCells.length` (Google Docs tables are
  rectangular; a row's cell count can differ from row 0 only via merged
  cells, which `column_span`/`row_span` below account for instead of a
  per-row count).
- `header_row` — best-effort: `true` when every cell in row 0 carries bold
  text and no other row does, `false` otherwise. Heuristic, not authoritative
  — expose the evidence (which cells triggered the guess) if consumers turn
  out to need to audit it, mirroring §6.3's evidence-typing convention rather
  than a bare boolean.

Extend each affected block's existing `table` field with a table reference
and span, instead of replacing it:

```json
{
  "table": {
    "table_id": "table__t.0__142",
    "row": 1,
    "column": 0,
    "row_span": 1,
    "column_span": 2
  }
}
```

- `table_id` — resolves the identity gap (#1); joins back to the
  `document.tables` entry above.
- `row_span` / `column_span` — from `tableCellStyle.rowSpan` /
  `tableCellStyle.columnSpan` (default `1` when absent, matching the Docs
  API's own default-if-unset convention elsewhere in this spec, e.g. list
  `nestingLevel`). Resolves the merged-cell gap (#3).

**Nested tables (#4).** `processTable_`'s post-order tagging loop must skip
blocks that already carry a `table.table_id` from a nested table processed
during the same before/after slice, rather than unconditionally overwriting
`block.table`. A nested table's cell also has its own outer `{row, column}`
position — capture that as `table.parent_cell` (`{table_id, row, column}`)
on the nested table's `document.tables` entry, rather than on every block
inside it, so nested-table blocks keep exactly one `table` reference (their
own innermost table) instead of an ambiguous outer/inner pair.

**Diagnostics.** Add `diagnostics.tables` (count of `document.tables`
entries) alongside the existing `diagnostics.blocks`/`diagnostics.units`
counters (§16).

**Out of scope for this proposal:** column width/border styling
(`tableStyle.tableColumnProperties`, cell borders) — no identified consumer
need yet; revisit only if one emerges, per this spec's general bias toward
not capturing metadata nothing downstream reads (§17 principle 7 notwithstanding — that principle covers *audit* metadata for classifications already made, not speculative styling capture).

### 19.2 Direct browser download (replace Drive-link delivery)

**Current state (§15).** `exportGovernance_` always writes the JSON (and,
optionally, the PDF snapshot) to a Drive folder. Every entry point then hands
the user a *link to the Drive file* — the CardService result card's "Open
JSON in Drive" button (`_buildExportResultSection_`) and the classic-menu
dialog's `jsonLink`/`pdfLink` anchors (`ExportProgressDialog.html`) both open
`https://drive.google.com/file/d/<id>/view`. Getting the actual bytes onto
the user's machine requires a second, manual step inside Drive's own viewer
(File → Download). There is no path that hands the file to the browser
directly.

**Gap this proposal closes.** The classic-menu dialog path
(`showGovernanceExportDialog_` / `runExportForDialog`, §15's
`HtmlService.showModalDialog`) is not sandboxed the way CardService
universal-action cards are and can serve a real client-side download: the
server function returns the file's bytes to the page, and the page's own JS
triggers the save — no Drive detour.

**Proposed shape.** `runExportForDialog` additionally returns the JSON file's
content (and, when `exportPdf` is true, the PDF's bytes) alongside the
existing `jsonFileId`/`pdfFileId`:

```json
{
  "jsonFileId": "...",
  "jsonContent": "{ ...the governance JSON, verbatim... }",
  "pdfFileId": "...",
  "pdfBase64": "JVBERi0xLjQK..."
}
```

- `jsonContent` — the same string already written to `jsonFile` via
  `JSON.stringify(out, null, 2)`; returned as-is rather than re-encoded, since
  `google.script.run` marshals strings natively.
- `pdfBase64` — `Utilities.base64Encode(pdfFile.getBlob().getBytes())`, since
  a PDF is binary and `google.script.run` payloads are JSON.
- `ExportProgressDialog.html`'s success handler builds a `Blob`
  (`new Blob([jsonContent], {type: 'application/json'})` /
  `Uint8Array` decode of `pdfBase64` for the PDF) and triggers a save via a
  temporary `URL.createObjectURL(...)` + `<a download="...">.click()`,
  instead of only setting `jsonLink.href`/`pdfLink.href` to the Drive view
  URL as today. The Drive file (and its "Open in Drive" link) are **kept**,
  not replaced — the local post-processing tool (§19.3) and any later manual
  reference both still want the artifact to persist in the source folder;
  this proposal only adds a second, more direct delivery path alongside it.
- The CardService universal-actions path (`onGovernanceExportMenu` /
  `_buildExportResultSection_`) is **out of scope** — CardService action
  handlers cannot serve a client-side Blob download, so that path keeps the
  Drive-link-only behavior it has today (§15 point 4 is unchanged for that
  entry point specifically).

**Open question for the implementing bead.** `google.script.run` response
size is generously bounded but not unbounded, and base64 inflates the PDF by
~33%; validate against the largest real document (the full Governance
Manual, with `includeWholeDocumentViews` on) before assuming this scales to
every export rather than only the common case.

### 19.3 Embedded image extraction for LLM analysis

**Current state.** `processParagraph_`'s per-element loop (implementation
pointer, §7.4) only handles text runs and AutoText. A paragraph element that
is an inline image (`paragraph.elements[].inlineObjectElement`) produces no
block and is silently invisible in the export today — including images
inside table cells (§7.2/§19.1) and inside the shaded "box" callouts
described alongside this document's other governance content. **Correction
(gts-283i.1 raw capture, confirmed live):** a box callout is *not*,
structurally, a table cell — the source corpus's box pattern (e.g. Church
Policy 05's "Policy Statement" box) is a run of ordinary consecutive body
paragraphs that each individually carry
`paragraphStyle.{borderTop,borderBottom,borderLeft,borderRight}` plus
`paragraphStyle.shading.backgroundColor` (observed
`{red:0.812, green:0.886, blue:0.953}`, a light blue). The captured document
(`knowledge-base/references/gts-283i-raw-capture/`) contains **zero** `table`
structural elements anywhere — `processTable_` is never invoked for this
pattern at all. The "no separate box-specific handling is needed" conclusion
still holds, but for a simpler reason than originally assumed: a box
paragraph is walked by the same top-level `processParagraph_` call as every
other body paragraph (no table detour), so fixing paragraph-level image
handling covers it automatically with no additional code path — there is no
table-cell walk to piggyback on because there is no table here at all. (This
does not change §7.2/§19.1's separate, general table-support gap — tables can
still appear elsewhere in a document and still need `processTable_`'s own
image handling once §19.3 lands; it only corrects the assumption that *this
specific* box pattern is an instance of that case.) Diagrams and flowcharts
embedded as inline images are the primary motivating case: their content
(entities and the relationships between them) is currently unrecoverable
from the JSON at all.

**Gap this proposal closes.** Embedded images carry meaning (most often a
flowchart or diagram with labeled boxes and connecting relationships) that
matters to an LLM consuming the export, but image content cannot be
extracted synchronously inside the GAS export the way text can — it requires
sending the image to a vision-capable LLM, which is out of scope for an Apps
Script execution. This proposal covers only the exporter's half: extracting
each embedded image as its own file and leaving a stable, uniquely-named
reference in the JSON for a separate, out-of-band local tool to analyze
later.

**Proposed shape.** A new block `kind`, `image`:

```json
{
  "kind": "image",
  "image_ref": "img-t.0-1482.png",
  "inline_object_id": "kix.abc123xyz",
  "alt_title": null,
  "alt_description": null,
  "width_pt": 468.0,
  "height_pt": 210.5,
  "description": null
}
```

- `image_ref` — the saved image's filename. Derived the same way as
  `makeBlockId_` (`tab_id` + structural start index), so it is unique within
  the export by construction and stable across re-exports of an unchanged
  document.
- `inline_object_id` — the Docs API's own `inlineObjectId`, kept for
  traceability back to `document.inlineObjects` in a raw API dump if one is
  ever needed for debugging.
- `alt_title` / `alt_description` — Docs' own image accessibility fields
  (`inlineObjectProperties.embeddedObject.title` / `.description`), passed
  through when the source document's author set them. Frequently absent;
  `null` is expected, not an error.
- `width_pt` / `height_pt` — from `embeddedObject.size`, in points.
- `description` — **always `null` as written by the exporter.** Per §17
  principle 2 (do not silently infer or fabricate content), the exporter
  never generates this field itself. It exists as the reserved slot a
  separate local tool fills in after the fact: that tool reads the extracted
  image file, sends it to a vision-capable LLM, and writes a description
  back — for a flowchart/diagram, that description must capture the
  depicted entities *and the relationships between them* (the whole reason
  this proposal exists), not a one-line caption. **Write-back mechanism
  decided:** the local tool writes a separate sidecar file
  (`<document-name>-image-descriptions.json`, keyed by `image_ref` with
  `inline_object_id` as a verification key) into the same per-export images
  subfolder, rather than editing this governance JSON in place — see
  `knowledge-base/adr/0025-image-description-sidecar-writeback.md` for the
  rationale (deterministic exporter output, avoids re-paying vision-LLM cost
  on re-export). A downstream RAG ingestion step merges the two files at read
  time.

**Extraction mechanics.** `inlineObjectProperties.embeddedObject
.imageProperties.contentUri` is a short-lived, signed URL — it must be
fetched via `UrlFetchApp.fetch` during the same export execution that reads
it, never persisted or deferred, or the fetch will fail once it expires.
Save the fetched bytes as a Drive file inside a per-export images subfolder
(`<document-name>-images/`) alongside the JSON/PDF, named to match
`image_ref`.

Mirror §19.1's `document.tables` and §7.5's `document.toc` "diverted
metadata" convention with a `document.images` array — one entry per
extracted image, so a consumer (or the local analysis tool) can enumerate
every image in the export without walking every block:

```json
{
  "id": "image__t.0__1482",
  "image_ref": "img-t.0-1482.png",
  "drive_file_id": "1AbC...",
  "tab_id": "t.0",
  "source_order": 37,
  "location": { "tab_id": "t.0", "start_index": 1482, "end_index": 1483 }
}
```

**Diagnostics.** Add `diagnostics.images` (count of `document.images`
entries) alongside the existing counters (§16).

**Out of scope for this proposal:** positioned/floating images
(`paragraph.positionedObjectIds` → `document.positionedObjects`, anchored
rather than inline) — no identified example in the source documents yet, but
flag as a known gap since a diagram is occasionally inserted as a floating
image rather than inline; revisit if one is found. Also out of scope: the
local analysis tool itself (the LLM call, prompt design, and write-back
mechanism) — this section defines only the exporter-side contract it
consumes.
