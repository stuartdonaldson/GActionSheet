# DOCX Document-Export Contract (schema 3.1)

**Status:** Frozen — stage 1 deliverable of `knowledge-base/staging/document-export.md` (`gts-lm0a`).
**Authorised by:** ADR-0026 (Accepted). This document answers the one open question ADR-0026
records under "Open questions this ADR does not resolve" — the block-correlation contract — and
freezes the surface every downstream `[IMP]`/`[TST]` bead is authored against.
**Amended by:** ADR-0029 (Accepted, 2026-08-26) — §3.2/§3.3 revised: `revision.state` removed,
`document.suggestion_groups` renamed `document.revision_groups`; `semantic_state`/
`semantic_state_evidence`/top-level `semantics` removed document-wide (no section here previously
named them as contract — see ADR-0029 for the full removal). Schema version bumped 3.0 → 3.1.
**Applies to:** the Python `.docx` pipeline only. The frozen GAS exporter
(`src/Procedure-Exporter.js`, schema 2.4) is unchanged by this document and is not to be edited to
conform to it.
**Reading order:** ADR-0026 first (why), then this (what), then `docs/procedure-exporter.md` (the
schema's semantics, which this document amends rather than restates).

This is a contract, not a design note. Where it says *must*, an implementation that does otherwise
is wrong. Where a field's DOCX-path value is given as `null`, `absent` or `retired`, that is the
required value, not a suggestion.

**Terminology:** *document* throughout, per ADR-0026 §Terminology. The Python package uses
`document` in every identifier from the start; `gts-284o` (stage 8) is about the GAS side only and
does not apply here.

---

## Standing constraint: architectural alignment for back-port

**Owner decision (2026-08-25, `gts-uenq`).** The Python pipeline is a local re-implementation of the
GAS exporter *plus* new capability, not an unrelated tool. Some of the new capability may later be
back-ported into the GAS JavaScript. **Every structural choice below must therefore stay as close to
`src/Procedure-Exporter.js`'s decomposition as the OOXML source allows**, and a deviation must be
one this document names and justifies.

Concretely, this is binding on:

- **Module boundaries (§7.1)** mirror the GAS exporter's functional regions one-for-one — structure
  walk, comment association, revision summarisation, image extraction, id derivation — so a
  back-port is a translation of one module, not an untangling.
- **Function names and shapes** keep their GAS counterparts' meaning: `build_export` ↔
  `exportGovernance_`, `make_block_id` ↔ `makeBlockId_`, `slugify` ↔ `slugify_`. Names lose the
  trailing-underscore GAS privacy convention and gain `document` for `governance` (ADR-0026
  §Terminology); nothing else about them changes.
- **Schema shape** stays the contract (ADR-0026 Decision 4). Everything in §5 is a *value*
  degradation or a strictly additive field; no field is restructured for the Python side's
  convenience. **Exception (ADR-0029):** three fields inherited from GAS 2.4 without independent
  justification — `suggestion_groups` naming, `revision.state`, `semantic_state`/`semantics` — are
  restructured/removed based on first-consumer review, not Python-side convenience. See ADR-0029.
- **Deviations are enumerated, not incidental.** The only structural deviations this contract
  permits are the ordinal id derivation (§1, forced by the coordinate system) and the retirement of
  the quoted-text matcher (§2, mandated by ADR-0026 Decision 5). Both are back-portable in principle:
  a GAS exporter that later wanted ordinal ids could adopt §1.2 unchanged.

A consequence worth stating plainly: where the Python side gains a capability the GAS side lacks
(exact comment anchoring, real revision authorship, anchored images, `.docx` corpus coverage), the
capability is expressed as an ordinary schema field so that a future GAS implementation can populate
the same field if it ever finds a source for it. New capability must not arrive as a new artifact
shape.

---

## 1. Coordinate systems, and why the ID scheme changes

The Docs API addresses content by `startIndex`/`endIndex` — integer offsets into a tab's flattened
content stream. `makeBlockId_` (`src/Procedure-Exporter.js:1901`) builds
`block__<tabId>__<startIndex>__<endIndex>` directly from them.

OOXML has no such coordinate. A `.docx` body is a tree of `w:p` / `w:tbl` elements; position is
expressed by tree order alone. A character offset *can* be synthesised by counting text as the
parser walks, but it would not equal the Docs index for the same document — Docs counts paragraph
marks, section breaks and structural elements that OOXML represents differently. Synthesising one
would produce a number that *looks* like a Docs index, invites comparison with one, and is wrong.

**Decision: the DOCX path does not synthesise offsets. Identity is ordinal-based.**

### 1.1 Segment

`<segment>` replaces `<tabId>`. Its value is:

| Source | `segment` |
|---|---|
| `word/document.xml` body | `main` |
| anything else | not processed in schema 3.0 |

There is **no OOXML analogue of a Google Docs tab.** A multi-tab document exports to a single
`word/document.xml` whose contents are whatever Google's converter chose to emit; the pipeline
cannot see the boundary and must not invent one. `segment` is therefore the constant `main` for
every block in every document produced by this pipeline. It exists as a named field rather than
being dropped so that the id shape stays parseable and so a future header/footer or multi-part pass
has somewhere to go.

### 1.2 Ordinal

`<ordinal>` is a zero-based counter over **content blocks in traversal order**, incremented once per
emitted block, zero-padded to 6 digits (`000000`, `000001`, …). Traversal is document order,
depth-first, and includes paragraphs nested inside table cells at the point where the table occurs.
Zero-padding is required so that lexicographic sort of ids equals document order.

The counter must be incremented **only** when a block is emitted. A paragraph that is diverted (a
TOC line, §5) or produces no block does not consume an ordinal. This makes the ordinal a dense index
into the emitted `units[].blocks[]` sequence, which the differential oracle and the acceptance test
both rely on.

### 1.3 The identifiers

| Identifier | GAS (schema 2.4) | Python DOCX (schema 3.0) |
|---|---|---|
| block id | `block__<tabId>__<start>__<end>` | `block__<segment>__<ordinal>` |
| unit id | `<tabId>__<kind>__<slug>__<start>` | `<segment>__<kind>__<slug>__<ordinal>` |
| image id | `image__<tabId>__<start>` | `image__<segment>__<ordinal>` |
| image ref (filename) | `img-<tabId>-<start>.<ext>` | `img-<segment>-<ordinal>.<ext>` |

- The `block__` prefix is **retained**. Its meaning is unchanged (this string identifies a block);
  only the derivation of its tail changes.
- A unit's `<ordinal>` is the ordinal of the block that opened it (its heading), so a unit id and
  its first block id agree on their tail number.
- `slug` uses the same normalisation as `slugify_` (`src/Procedure-Exporter.js:1905`): NFKD, lower,
  non-alphanumerics collapsed to `-`, trimmed, truncated to 90 chars, falling back to `kind` when
  empty. This is deliberately identical so that unit ids remain visually comparable across the two
  implementations even though their tails differ.
- An image ref must additionally be traceable to its source part: the image block carries
  `source_part` (e.g. `word/media/image3.png`). Two drawings referencing the same media part get
  two distinct `image_ref` names (their own ordinals) and the same `source_part`, making
  deduplication visible to the consumer rather than silently applied.

### 1.4 Cross-implementation ID stability is an explicit non-goal

A GAS export and a Python export of the same document **will not** share block, unit or image ids.
This is stated as a decision, not conceded as a limitation: the two ids encode different coordinate
systems, and forcing agreement would require one side to fake the other's coordinates.

**Consequence for the differential oracle (`gts-klp8`):** it must align the two artifacts
**structurally** — by traversal position and normalised block text — and must not diff by id. Any
oracle design that joins on `id` is invalid under this contract.

**Within** an implementation, ids are stable across re-exports of an unchanged document, which is
the property `gts-283i.5`'s idempotency invariant actually needs and which ordinals satisfy.

---

## 2. Comment anchoring

### 2.1 Mechanism

For each `w:comment/@w:id` in `word/comments.xml`, the body is scanned for the matching
`w:commentRangeStart/@w:id` and `w:commentRangeEnd/@w:id` markers. The set of blocks the range
covers is the set of emitted blocks between (and including) the block containing the start marker
and the block containing the end marker, in traversal order.

The four-tier quoted-text matcher, its tuning constants (`COMMENT_MATCH_WINDOW_BLOCKS`,
`COMMENT_FUZZY_MIN_SCORE`, `COMMENT_FUZZY_MIN_MARGIN`) and the `unmatched` bucket are **retired, not
ported** (ADR-0026 Decision 5). No fuzzy or text-similarity matching may appear in the Python
pipeline.

### 2.2 A range that spans blocks yields ONE comment record with N block ids

`associated_block_ids` is already an array in schema 2.x (the `quoted_text_multiblock` tier
populated it with several). That shape is retained and now carries an exact answer instead of a
window guess. The **primary** block — the one `citation_hint` and `section_path` are derived from —
is the first in traversal order. `associated_unit_ids` is the ordered, de-duplicated set of
`unit_id`s of the associated blocks.

Splitting a spanning comment into N records is prohibited: one comment is one authored artifact, and
duplicating it would inflate `diagnostics.comments` and make `comment_ids` on a block ambiguous
about identity.

### 2.3 `anchor_basis` replaces `association_basis`

Every comment carries exactly one `anchor_basis`:

| `anchor_basis` | Condition | `associated_block_ids` |
|---|---|---|
| `range_exact` | start and end resolve within one block | one id |
| `range_multiblock` | start and end resolve in different blocks | N ids, traversal order |
| `range_empty` | start immediately followed by end; no text between | the containing block |
| `range_unterminated` | start found, no matching end in the body | start's block only; warning |
| `no_range` | comment id in `comments.xml` with no range markers in the body | `[]`; warning |

`unmatched`, `quoted_text_exact`, `quoted_text_prefix`, `quoted_text_multiblock`,
`quoted_text_fuzzy`, `quoted_text_multiple` and `no_quoted_text` are all retired values and must not
be emitted by this pipeline.

`range_unterminated` and `no_range` are the only fail-closed states. Each contributes to
`diagnostics.unanchored_comments` (replacing `diagnostics.unmatched_comments`) and, when the count
is nonzero, a `diagnostics.warnings` entry. Both are expected to be rare; if either becomes common
in the corpus that is a finding about Google's converter, and belongs in a bead, not in a new
matching tier.

### 2.4 Nesting and overlap

Comment ranges may overlap or nest. No resolution is performed: each `w:id` resolves its own range
independently, and a block simply appears in the `associated_block_ids` of every comment whose range
covers it (and, conversely, lists all of their ids in its own `comment_ids`). There is no
"innermost wins" rule and no containment hierarchy between comments.

### 2.5 `quoted_text` becomes a fact

On the DOCX path, `quoted_text` is the concatenated text actually lying between the range markers,
normalised per `docs/procedure-exporter.md` §13.5. It is no longer Drive's `quoted_file_content`,
and therefore no longer goes stale or arrives `null` on a heavily-edited document (the failure that
produced 57/57 nulls in gts-rdi3). It is `null` only for `no_range`, and `""` for `range_empty`.

### 2.6 Threading and resolution

From `word/commentsExtended.xml`:

- `w15:paraIdParent` present → the comment is a reply; its parent is the comment whose
  `w15:paraId` matches. Replies are nested under the parent comment's `replies[]`, preserving the
  existing schema shape.
- `resolved` is `true` when `w15:done="1"`, `false` when `w15:done="0"`, and **`null` when
  `word/commentsExtended.xml` is absent from the package**. `null` means "unknown", never "not
  resolved" — ADR-0026 records the resolved-comment round trip as unproven, and a `null` is how that
  uncertainty reaches the consumer instead of being flattened into a false.

---

## 3. Revisions: `w:ins` / `w:del`

### 3.1 No offset reconciliation is required, by construction

`w:ins` and `w:del` wrap **whole `w:r` elements**. Revision state is therefore a property of a run,
not a range over block text, and there is nothing to reconcile against block offsets: the parser
emits runs in OOXML document order and each carries its own state. This is the answer to the design
question `gts-lm0a` posed about run splits — the question does not arise on this path, because the
DOCX path never needs a character offset to attribute a revision.

Deleted runs carry their text in `w:delText` rather than `w:t`; both are read as run text.

### 3.2 Run states and derived text

**Amended by ADR-0029 (schema 3.1).** `revision.state` is removed. `revision.change` is the single
fact; `baseline_text`/`proposed_text`/`all_text` membership is computed directly from it:

| `revision.change` | OOXML | in `baseline_text` | in `proposed_text` | in `all_text` |
|---|---|---|---|---|
| unchanged | bare `w:r` | yes | yes | yes |
| inserted | `w:ins` | no | yes | yes |
| deleted | `w:del` | yes | no | yes |
| inserted_then_deleted | `w:del` inside `w:ins` (or vice versa) | no | no | yes |

`inserted_then_deleted` is a real OOXML state (an edit made and then withdrawn within the same
tracked-changes session) with no Docs-API analogue. It is preserved rather than dropped — §17
principle 5 forbids discarding deleted material — and excluded from both reconstructions, since it
was never in the baseline and is not proposed. A block containing one has
`revision_summary: "mixed"`.

Because each run's membership in the three derived strings is a pure function of its own `change`
value, the reconstructions are deterministic by construction and independent of traversal
bookkeeping and independent of any unit/block-level classification (ADR-0029 also removes
`semantic_state`, which this table used to be conditioned on via
`_EXCLUDED_VIEW_SEMANTIC_STATES` — that exclusion mechanism is gone; every run follows this table
uniformly). §13.3's conditional emission rule (single `text` for unchanged blocks; the
`all_text`/`baseline_text`/`proposed_text` trio otherwise) is unchanged and applies verbatim — this
is the invariant carried forward from `gts-e7ca`.

Adjacent runs are merged only when **all** of `change`, `author`, `date` and the §9 formatting
attributes are equal.

### 3.3 Authorship is a fact

`w:ins`/`w:del` carry `w:author` and `w:date`. Each revision-bearing run carries
`revision.author` (string) and `revision.date` (ISO 8601 string), read directly off the markup.

- `document.suggestion_groups[].possible_authors` — **retired** (field absent). It existed to carry
  a labelled guess; there is nothing left to guess.
- `suggestion_authorship` becomes
  `{"resolvable": true, "basis": "ooxml_w_ins_w_del_author"}`, replacing
  `{"resolvable_via_documents_get": false, …}`.
- **Amended by ADR-0029 (schema 3.1):** the group container is renamed `document.revision_groups`
  (was `document.suggestion_groups` — "suggestion" is a Docs-era term for something that, on this
  path, is a native Word tracked-changes event, not a pending suggestion). Grouping key and member
  structure are unchanged: grouped by `(author, date)` rather than by the Docs `suggestion_id`,
  which has no OOXML equivalent; each group carries `author`, `date`, and the member run/block ids.

---

## 4. Images

Bytes come from `word/media/` via `zipfile`, resolved through the `w:drawing`'s
`a:blip/@r:embed` relationship id against `word/_rels/document.xml.rels`. There is no signed URL and
no expiry path — `extractInlineImage_`'s `contentUri` expiry warning has no analogue and is retired.

- Both **inline** (`wp:inline`) and **positioned/anchored** (`wp:anchor`) drawings produce an
  `image` block. `anchored: true|false` distinguishes them. Anchored images are new capability, not
  a schema hazard: they occupy an ordinal at the position of their anchoring paragraph.
- `alt_title` / `alt_description` are read from `wp:docPr/@title` and `wp:docPr/@descr`.
  `alt_description` is `null` when absent and is **never fabricated** — ADR-0025's sidecar
  writeback is the only mechanism that fills it, and it does not edit this JSON in place.
- `document.images[]` is omitted entirely when the document has no images, per §13.4.
- Files are written to `<out-dir>/<sanitized-title>-images/`, named by `image_ref`. Same names on
  re-export of an unchanged document.

---

## 5. Fields that degrade, in full

ADR-0026 §Consequences names four degradations. This is the complete list with required values.
Nothing else in the schema changes value on the DOCX path.

| Field | Schema 2.4 (GAS) | Schema 3.0 (DOCX) | Why |
|---|---|---|---|
| `document.toc[].title` | from TOC line text | unchanged | The TOC field's rendered text survives conversion |
| `document.toc[].displayed_page` | last-tab split | unchanged | same |
| `document.toc[].target_heading_id` | `h.<id>` from `textStyle.link.heading.id` | **`null`** | Word emits `_Toc…` bookmarks; they do not map to Google heading ids |
| `document.toc[].target_tab_id` | `t.0` | **`null`** | no tabs |
| `document.toc[].url` | deep link | **`null`** | derived from the two above |
| `location.tab_id` | `t.0` | **`null`** (key present) | no OOXML analogue |
| `location.tab_title` | tab title | **`null`** (key present) | no OOXML analogue |
| `location.start_index` | Docs offset | **`null`** (key present) | §1 — different coordinate system |
| `location.end_index` | Docs offset | **`null`** (key present) | §1 |
| `location.ordinal` | — | **new**, integer | the authoritative order key on this path |
| `location.segment` | — | **new**, `"main"` | §1.1 |
| `location.page` / `page_basis` / `page_approximate` | explicit-break count | unchanged semantics | counted from `w:br w:type="page"` only; `w:lastRenderedPageBreak` is Word's cached pagination and is **ignored** |
| `document.suggestion_groups[].possible_authors` | low-confidence guess | **retired** (absent) | §3.3 — replaced by fact |
| `suggestion_authorship` | `{resolvable_via_documents_get: false, …}` | `{resolvable: true, basis: "ooxml_w_ins_w_del_author"}` | §3.3 |
| `comments[].association_basis` | tier name | **retired**, replaced by `anchor_basis` | §2.3 |
| `diagnostics.unmatched_comments` | count | **retired**, replaced by `diagnostics.unanchored_comments` | §2.3 |
| `diagnostics.tabs_detected` | tab count | **`null`** | cookie auth cannot reach the Docs API to count tabs (ADR-0026 §Consequences); `null` means "could not determine", not zero |
| `block.image_ref` | `img-<tab>-<start>.<ext>` | `img-<segment>-<ordinal>.<ext>` | §1.3 |
| `block.source_part` | — | **new**, `word/media/imageN.ext` | §1.3 |
| `block.anchored` | — | **new**, boolean | §4 |

`location.tab_id`, `tab_title`, `start_index` and `end_index` keep their keys with `null` values
rather than being removed. §13.4 already requires scalar structural fields to be present-when-null,
and a present `null` is a single, classifiable regression for the differential oracle, where a
missing key would be noise on every `location` object in the artifact.

---

## 6. Schema version

**Bumped again to `3.1` by ADR-0029** (2026-08-26): `revision.state` removed,
`document.suggestion_groups` → `document.revision_groups`, and `semantic_state`/
`semantic_state_evidence`/`semantics` removed document-wide. Field removals plus a rename, not a
patch. See ADR-0029 for full rationale. The `3.0` bump below is otherwise unchanged history.

**Bumped to `3.0`.** Not a patch, not `2.5`:

- Block, unit and image ids change derivation. Any consumer that parsed an id — or joined two
  artifacts on one — breaks. That alone is a major bump.
- `association_basis` and `possible_authors` are removed, not deprecated.
- `location` gains two required fields and loses the meaning of two others.

The GAS exporter stays at `2.4` and is not touched (ADR-0026 Decision 7). A consumer therefore
distinguishes the two implementations by `schema_version` alone; no field is added to the frozen GAS
side to announce provenance. For symmetry the Python artifact carries
`producer: "python-document-export"`, and the differential oracle treats its **absence** as
"produced by the GAS exporter" — which is what lets the oracle run without editing frozen code.

`docs/procedure-exporter.md` currently carries `2.2` in its §5 example and `2.3` in prose while the
code says `2.4`. That drift is real and is `gts-fadg`'s to fix during the rewrite (stage 8); it is
recorded here so the rewrite does not have to rediscover it.

**No separate ADR for the bump** (owner decision, 2026-08-25). The `3.0` bump is a resolution of the
questions ADR-0026 explicitly deferred, not an independent decision, so it is recorded here rather
than as ADR-0027. This section is the citable source for the version and its rationale.

---

## 7. Python CLI: the public surface

### 7.1 Package layout

Root-level package `document_export/`, sibling to `scn/`:

| Module | Responsibility |
|---|---|
| `document_export/cli.py` | argument parsing, stderr diagnostics, exit code |
| `document_export/acquire.py` | `.docx` acquisition and on-disk cache |
| `document_export/package.py` | OOXML zip/part/relationship access |
| `document_export/structure.py` | units, blocks, runs, tables, numbering (stage 3) |
| `document_export/comments.py` | §2 (stage 4) |
| `document_export/revisions.py` | §3 (stage 5) |
| `document_export/images.py` | §4 (stage 6) |
| `document_export/schema.py` | `SCHEMA_VERSION`, id builders, slugify, normalisation |
| `document_export/build.py` | `build_export(...)` — the offline seam |

Every identifier uses `document`. `governance` must not appear in this package.

### 7.2 Entry points

```python
# document_export/build.py — pure, no network, no filesystem writes
def build_export(
    docx_bytes: bytes,
    *,
    doc_id: str | None = None,
    title: str | None = None,
    options: dict | None = None,
) -> dict: ...
```

```python
# document_export/cli.py
def main(argv: list[str] | None = None) -> int: ...
```

`build_export` taking **bytes and returning a dict** is the load-bearing part of this section. It is
what makes stages 3–6 testable against a checked-in fixture with no Google auth, and it is the seam
`gts-0rho` asserts against. An implementation that reaches the network or writes files from inside
`build_export` violates this contract.

`options` accepts `includeWholeDocumentViews` (default `False`) and `includeImages` (default
`True`), matching §13's existing option semantics.

### 7.3 Command line

```
python scripts/export_document.py [DOC_ID] [--docx PATH] [--out-dir DIR]
                                  [--no-images] [--whole-document-views] [--json-only]
```

- `scripts/export_document.py` is a thin shim over `document_export.cli:main`, matching the existing
  `scripts/` convention.
- `DOC_ID` and `--docx` are mutually exclusive and one is required. `--docx` reads a local file and
  makes **no network call at all** — this is the offline fixture path.
- **Acquisition is URL construction from a docId, and nothing more.** The URL is
  `https://docs.google.com/document/d/<DOC_ID>/export?format=docx` — no mimeType probe, no Drive
  REST branch, no endpoint selection (ADR-0026 Decision 1). `acquire.py` is a thin wrapper over
  `tests/helpers/download.py`'s existing `download_docx(doc_id)`; it is not reimplemented.
- **Access model, in the order the pipeline will grow into it** (owner decision, `gts-uenq`):

  | Tier | Mechanism | Status |
  |---|---|---|
  | 1 | Link-only — the constructed URL fetched with no credential | Works today for any document shared "anyone with the link". The assumed baseline. |
  | 2 | Saved Playwright cookies (`scn.session.resolve_auth_file`, `~/.playwright/sdonaldson.json`, with `download.py`'s proactive + reactive rotation refresh) | **What `download_docx` already does**, and the default path. ADR-0026 Decision 2. |
  | 3 | A WebApp call into the GActionSheet Apps Script deployment | Future, not built. Recorded so `acquire.py` keeps acquisition behind one function and does not leak a cookie session into the parser. |

  Tier 3 is why `build_export` takes bytes (§7.2): swapping the acquisition tier must not touch a
  single line of parsing code.
- Title comes from `download.fetch_doc_title(doc_id)`, not from the package's
  `core_properties.title` — Google Docs always writes the literal `"Word Document"` there.
  With `--docx` and no `DOC_ID`, title falls back to the input filename stem.

### 7.4 Output

Default `--out-dir` is `./exports/<doc_id>/` (or `./exports/<filename-stem>/` under `--docx`).

| Artifact | Name |
|---|---|
| JSON | `<sanitized-title>-document.json` |
| images | `<sanitized-title>-images/img-main-<ordinal>.<ext>` |
| cached source | `<sanitized-title>.docx` (suppressed by `--json-only`) |

`-document.json` deliberately parallels the GAS side's `-governance.json` so both artifacts can sit
in one directory for the differential oracle without colliding.

### 7.5 Exit codes and warnings

- `0` — artifact written. **Including when warnings were emitted**: ADR-0026 requires warn-and-
  continue, so a nonzero exit for a degraded-but-written artifact is prohibited.
- `1` — no artifact written (acquisition failed, package unreadable, unhandled parse error).

Every warning is emitted on **both** channels, per ADR-0026: appended to `diagnostics.warnings[]`
so it travels with the artifact to the LLM consumer, and written to stderr so the operator sees it.
A warning about content the pipeline could not see must tell the reader to verify what was actually
downloaded, not merely note the condition.

---

## 8. What this contract does not settle

- **Multi-tab converter behaviour** — `gts-11rq`, deferred by decision. §1.1 fixes `segment` to
  `main` and §5 fixes `diagnostics.tabs_detected` to `null` so that the pipeline is well-defined
  today; if `gts-11rq` establishes that the converter drops tabs silently, that is an amendment to
  ADR-0026 and to this section, not a redesign of the id scheme.
- **The two download endpoints' comment-count discrepancy** (54 vs 55, 62 vs 57) — unexplained per
  ADR-0026. `/export?format=docx` is what §7.3 uses. Until reconciled, `diagnostics.comments` is the
  count of `w:comment` elements in the package and is not to be described as the document's
  authoritative comment count.
- **Table structure** (`docs/procedure-exporter.md` §19.1's proposed replacement for the ad hoc
  `block.table = {row, column}` tagging). Schema 3.0 keeps the existing tagging; the mid-cell
  unit-switch invariant carried forward from `gts-qjkj` is asserted against it by `gts-0rho`.
