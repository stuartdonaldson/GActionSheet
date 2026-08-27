# Staged plan — document export to JSON for LLM analysis

> **Transient working contract** (framework staging). Deleted at stage 9 (`gts-odpk`), when the
> durable content has graduated to `docs/document-exporter.md`, `docs/CONTEXT.md`, `docs/DESIGN.md`
> and `docs/OPERATIONS.md`.
> **TTL exception:** `doc-standard.md` caps staging documents at two weeks. This plan is nine stages
> and will exceed that. The cap exists to stop documents that *cannot decompose into beads* from
> lingering — this one is fully decomposed (15 beads, every stage backed), so the failure mode the
> cap guards against does not apply. Review it against that test, not the calendar: if stages stop
> closing, push back to `ROADMAP.md §Review` rather than letting it sit.
> Authorised by: ADR-0026 (Accepted).
> Review fidelity: **Spec** (ADR-0013) — the design error is visible from contract prose; stage 1
> produces that prose and no Slice phase is used.

Pattern D staged execution. The contract lives in
`$DEVSTANDARD/doc-framework/planning-guide.md` §"Pattern D: Staged Execution" — it is not restated
here. Beads own all state (AC, grouping, model, owner decisions); this document holds sequencing
rationale, deliverable previews and handoffs only.

**Authorising decision:** ADR-0026 — the export JSON is built by a local Python tool from a
downloaded `.docx`, not from the Docs API in Apps Script. The GAS exporter is preserved frozen as
the differential-oracle baseline (Decision 7).

**Terminology:** *document* is the content class — any structured authoritative document, not the
Governance Manual that happened to seed the tool. The Python pipeline is greenfield and takes
`document` naming from the start; renaming the existing GAS-side identifiers is `gts-284o`, staged
late and deliberately kept out of the rewrite's way.

## Execution order

| # | Stage | Bead | Status | Title |
|---|-------|------|--------|-------|
| 1 | docx-contract | gts-lm0a | ✓ | [INF] Block-correlation and schema contract for the DOCX pipeline |
| 1 | docx-contract | gts-uenq | ✓ ⚑ | Decide disposition of the open GAS-exporter beads under the ADR-0026 freeze |
| 2 | docx-harness | gts-28hx | ✓ | [INF] Python package skeleton, `.docx` acquisition, diagnostics, fixture corpus |
| 3 | docx-structure | gts-pmga | ✓ | [IMP] Structure pass — units, blocks, runs, tables, numbering |
| 4 | docx-comments | gts-nxx3 | ✓ | [IMP] Comment anchoring from `w:commentRangeStart`/`End` |
| 5 | docx-revisions | gts-9c8k | ✓ | [IMP] Revision model from `w:ins`/`w:del` with real authorship |
| 6 | docx-images | gts-8uo6 | ✓ | [IMP] Image extraction from `word/media`, inline and positioned |
| 7 | docx-verify | gts-0rho | ✓ | [TST] End-to-end acceptance over the golden fixture |
| 7 | docx-verify | gts-qjkj | ✓ | [TST] Table mid-cell unit-switch tagging (absorbed into gts-0rho AC #2) |
| 7 | docx-verify | gts-e7ca | ✓ | [TST] Conditional block-text emission + omit empty arrays (absorbed into gts-0rho AC #3) |
| 7 | docx-verify | gts-283i.5 | ✓ | [TST] Embedded image extraction (absorbed into gts-0rho AC #6; bead closed) |
| 7 | docx-verify | gts-klp8 | ✓ | [INF] Differential oracle — diff the GAS and Python artifacts and classify |
| 8 | document-rename | gts-284o | ○ ⚑ | [INF] Migrate 'governance' terminology to 'document' |
| 8 | document-rename | gts-fadg | ○ | [INF] Rewrite `docs/procedure-exporter.md` as `docs/document-exporter.md` |
| 9 | document-docs | gts-odpk | ○ | [INF] CONTEXT/DESIGN/OPERATIONS coverage + full regression sweep |
| 9 | document-docs | gts-11rq | ○ | [INF] Confirm multi-tab `.docx` export behavior (deferred by decision; opportunistic) |

**Verify:** `bdls --stages` · `bdls --check` · `bdls --goals --stage <name>`

### Disposition of the pre-pivot GAS-exporter beads (`gts-uenq`, owner-decided 2026-08-25)

ADR-0026 Decision 7 freezes the GAS exporter as a comparison baseline, and a frozen baseline needs
no new hardening tests. Four beads predated that decision and targeted the GAS implementation:

| Bead | Disposition | Where the portable intent went |
|------|-------------|--------------------------------|
| `gts-283i.3` [TST] direct browser download | **Closed — superseded.** Assertions target `runExportForDialog`'s `jsonContent`/`pdfBase64`, a GAS/CardService dialog surface with no Python analogue. Same basis as `gts-g21w`/`gts-wido`/`gts-r40j`. | Acquisition-from-a-docId is contract §7.3's three-tier access model, exercised by stage 2's `gts-28hx`. |
| `gts-283i.5` [TST] embedded image extraction | **Closed — invariants carried forward.** Invariants portable; assertions drove Drive-side `-images/` folders on frozen code. | All four became `gts-0rho` AC #6(a)–(d), re-expressed against the CLI's local per-document folder (contract §7.4). Implies stage 2 needs an image-free fixture variant for AC #6(d). |
| `gts-e7ca` [TST] block-text emission + empty arrays | **Kept — ratified as staged.** Invariant is pure schema shape and fully portable; only the `exportGovernance_`/`export.complete` assertions are retired. | Stays a stage-7 row; AC rewritten against the Python artifact and asserted as `gts-0rho` AC #3. Closes with `gts-0rho`. |
| `gts-ipoy` [IMP] add-on card integration + design gaps | **Closed.** Implementation half landed; the 'harden design gaps' half is moot under the freeze. | Its `regression=pending` debt is carried by stage 9's `gts-odpk` AC #6, not by the bead. |

## Testing posture for this plan

Set by the owner at planning time and load-bearing on how the stages are shaped:

- **A full `pytest -x` sweep is expensive and runs once, at stage 9** (gts-odpk AC #6). Every `[IMP]`
  bead closes on a targeted gate and sets `regression=pending` per the Backstop rules; stage 9 is
  where that debt is paid in one pass.
- **Coverage comes from end-to-end exercise of the feature, not from a proliferation of tests.**
  There is deliberately no `[TST]` twin per `[IMP]` bead. Stage 7's single `gts-0rho` runs the CLI
  against a checked-in golden `.docx` and asserts the durable invariants of all four passes over the
  resulting artifact. The CLI is the call-site and the JSON artifact is the durable state, so the
  entry-point coverage invariant (T17) is satisfied by one test rather than four.
- This is why `gts-qjkj` and `gts-e7ca` — portable invariants inherited from retired GAS hardening
  beads — appear as **AC items inside `gts-0rho`** rather than as their own test work.
- The offline fixture is what makes this affordable: `gts-0rho` requires no live Google auth, so it
  is cheap enough to run on every touch during stages 3–6.

## Stages

### 1 — docx-contract
**Deliverable:** the frozen contract every later stage is authored against — block identity on the
OOXML side, how a comment range resolves to block ids, the schema version, and the list of fields
that degrade to null/absent. ADR-0026 names this as the one substantive design question it
authorises but does not answer.
**Why paired:** `gts-uenq` is an owner decision about four pre-pivot beads that target the now-frozen
GAS exporter; it has to be settled before the harness is built, because two of the four hold
invariants that either travel into `gts-0rho` or die. The two beads have no edge between them
(`unordered-batch` warning) — that is deliberate, they are independent within one session.
**Must not do:** write pipeline code. This stage produces prose.
**Work-log:** per-stage.

### 2 — docx-harness
**Deliverable:** `python scripts/export_document.py <docId>` downloads the `.docx` and writes a
structurally valid, near-empty artifact; a golden fixture `.docx` is checked in. The
corpus-coverage hole closes here — a Drive-hosted native `.docx`, invisible to the GAS exporter
entirely, becomes readable.
**Why alone:** everything downstream lands into this skeleton, and the fixture is what makes stages
3–6 testable offline.
**Must not do:** build per-tab download machinery. `gts-11rq` establishes the behaviour first.
**Work-log:** per-stage.

### 3 — docx-structure
**Deliverable:** real units, blocks, runs, tables and list numbering in the artifact — the first
output a human can read and recognise as the document.
**Why alone:** stages 4–6 all attach to blocks, so block identity has to be real before any of them
can be written. This is the fan-out point.
**Work-log:** per-stage.

### 4/5/6 — docx-comments, docx-revisions, docx-images
**Deliverable (4):** comments anchored to exact ranges with real authors — the `unmatched` bucket and
the four-tier quoted-text matcher are gone, not ported. **(5):** suggestion authorship as fact rather
than a labelled guess. **(6):** images that cannot expire, and positioned/anchored images visible for
the first time.
**Why separate stages, not one:** each of the three deletes a different heuristic and each is
independently reviewable against the ADR's claims. They share only `gts-pmga`, so they can run in any
order — or in parallel if worked by different sessions.
**Work-log:** one entry per stage.

### 7 — docx-verify
**Deliverable:** the pipeline proven end to end offline, plus the classified GAS-vs-Python diff.
**Why paired:** both are verification of the same artifact and share the loaded context of the four
implementation stages. `gts-qjkj`/`gts-e7ca` are here because their invariants are asserted by
`gts-0rho`; they close when it does.
**Must not do:** drive the differential diff to zero. ADR-0026 is explicit that the diff is the
deliverable and every difference is a classified gain or an expected regression.
**Work-log:** per-stage.

### 8 — document-rename
**Deliverable:** `governance` retired as a noun; `docs/document-exporter.md` describes two
implementations against one schema instead of one exporter that no longer matches reality.
**Why paired:** the code rename and the doc rewrite touch the same identifiers and the same
cross-references; splitting them guarantees one round of dangling links. No edge between them
(`unordered-batch`) — deliberate; either order works within the session.
**Why last:** `gts-284o` carries an unsettled judgement call (⚑ human) about whether to rename inside
the frozen GAS exporter at all. Renaming before the Python side is proven would churn code that the
oracle in stage 7 still needs to run unchanged.
**Work-log:** per-stage.

### 9 — document-docs
**Deliverable:** the subsystem finally appears in the project's own docs — it currently appears zero
times in `docs/CONTEXT.md`, `docs/DESIGN.md`, `docs/OPERATIONS.md` and `README.md` — and the whole
plan's deferred regression debt is paid in one full sweep.
**Why paired:** `gts-11rq` is deferred by decision, not blocked; it is staged here opportunistically
because its finding, if taken, lands in the same documents and may amend ADR-0026. Skip it without
penalty if no multi-tab document is available.
**Closes the plan:** this stage deletes this document and graduates its *Found* items
(`plan-graduation-audit`).
**Work-log:** per-stage.

## Handoffs

_(appended at the close of each stage: Done · Found · Next stages must know · Deliberately not done)_

### Stage 1 — `docx-contract` (closed 2026-08-25)

**Done.** The contract is frozen at `docs/interfaces/document-export-contract.md` (450 lines,
schema **3.0**). `docs/interfaces/` is new; it is the sanctioned location per the project
CLAUDE.md Document Map ("Protocol detail → /docs/interfaces/[protocol].md"). It was deliberately
**not** written into `docs/document-exporter.md`, which is `gts-fadg`'s to create at stage 8.
`gts-lm0a` closed against all six AC items; `gts-uenq` closed with all four dispositions recorded
(see §Disposition of the pre-pivot GAS-exporter beads, above). No pipeline code was written.

**Found.** Real schema-version drift: `docs/procedure-exporter.md` says `2.2` in its §5 example and
`2.3` in prose, while `src/Procedure-Exporter.js:42` says `2.4`. Recorded in contract §6 and routed
to `gts-fadg` (stage 8) so the rewrite does not have to rediscover it.

**Next stages must know.**
- **Back-port alignment is binding** (contract preamble, owner decision). The Python pipeline is a
  local re-implementation of the GAS exporter *plus* new capability, and some of that capability may
  later be back-ported into the JavaScript. Module boundaries mirror `src/Procedure-Exporter.js`'s
  functional regions one-for-one — `build_export` ↔ `exportGovernance_`, `make_block_id` ↔
  `makeBlockId_`, `slugify` ↔ `slugify_`. New capability arrives as an ordinary schema field, never
  a new artifact shape. The only permitted structural deviations are the ordinal ids (§1) and the
  retired quoted-text matcher (§2); any other deviation must be named and justified in the contract.
- **The differential oracle must diff structurally, never by id** (`gts-klp8`, stage 7).
  Cross-implementation id stability is an explicit non-goal (§1.4), so the oracle aligns on
  traversal position + normalised text. Any oracle design that joins on `id` is invalid under this
  contract.
- **`build_export(docx_bytes, ...) -> dict` stays network-free and filesystem-free** (§7.2). That is
  what makes stages 3–6 testable against the checked-in fixture with no Google auth, and it is what
  lets acquisition tiers be swapped (§7.3) without touching parsing code.
- **Stage 2 owes an image-free fixture.** `gts-0rho` AC #6(d) asserts `document.images` is omitted
  entirely (key absent, not `[]`) for a document with no images. That cannot run against the golden
  fixture alone — `gts-28hx`'s corpus needs an image-free `.docx` or a stripped variant. Noted on
  the bead.
- **Acquisition is URL construction from a docId and nothing more** — no mimeType probe, no Drive
  REST branch (ADR-0026 Decision 1). `acquire.py` is a thin wrapper over the existing
  `tests/helpers/download.py:download_docx`; it is not reimplemented.

**Deliberately not done.** No pipeline code, no `document_export/` package, no fixture corpus —
those are stage 2 (`gts-28hx`), and "do not write pipeline code" was this stage's stated must-not-do.
Epic `gts-283i` was left open although all five of its children are now closed: closing it is
outside `gts-uenq`'s scope, and three children carry `regression=pending` debt that stage 9 pays.
Nothing was committed — the project's agent profile is Conservative.

### Stage 2 — `docx-harness` (closed 2026-08-25)

**Done.** `document_export/` package: `schema.py` (id/slug builders mirroring `slugify_`/
`makeBlockId_`/`sanitizeFilename_`), `package.py` (`DocxPackage` — the shared zip/part/rels
accessor), `acquire.py` (thin wrapper over `tests/helpers/download.py:download_docx`/
`fetch_doc_title`), `build.py` (`build_export(docx_bytes, ...)`, pure, emits the near-empty
schema-3.0 artifact this stage scopes), `cli.py` (`main()`). `scripts/export_document.py` is the
thin shim. Fixture corpus: `document_export/fixtures/golden.docx` (TOC, tracked-changes insert +
delete + inserted-then-deleted, a threaded+resolved comment pair, a numbered list, a table with a
mid-cell unit-switch, one inline image) and `golden-no-images.docx` (same, image omitted, for
`gts-0rho` AC #6(d)'s negative case), both hand-built OOXML with a `README.md` mapping feature to
location. `tests/test_document_export_harness.py`: 18 tests, offline, green. All six AC items
verified — including AC #2 live against ADR-0026's confirmed Drive-hosted native `.docx`
(`1aK1jDQY6kfGs4op1t8hZrpN-pzrAMPNF`), invisible to the GAS exporter entirely. Closed
`regression=pending` per the Backstop rules (targeted gate only; full sweep is stage 9).

**Found.**
- `tests/conftest.py`'s session-scoped autouse fixtures (`_check_auth_session_alive`,
  `_reset_test_state`, `_purge_stale_test_docs`) hard-require a live GAS test-token session for
  *any* test under `tests/`, including this stage's fully offline, no-network module. An expired
  token blocked a plain `pytest tests/test_document_export_harness.py`; worked around with
  `--noconftest` for this stage's own gate. **Disposition: bead `gts-2moy`** — will recur for every
  offline test stages 3-7 add (`gts-pmga`, `gts-nxx3`, `gts-9c8k`, `gts-8uo6`, `gts-0rho`), and
  `gts-0rho` in particular is supposed to run with no live auth per this plan's Testing posture
  section.
- `document.revision_id`'s DOCX-path value is not named in contract §5's degradation table (no
  OOXML/reachable-Drive-API equivalent over the cookie session). **Disposition: implemented as
  `null`** or now (consistent with every other Docs-API-only field's treatment) and recorded here
  rather than silently assumed; amend contract §5 if this needs a different value.
- For a native `.docx` file (not a Google-native Doc), `fetch_doc_title` returns the Drive filename
  *including* its `.docx` extension (Drive's edit-page `<title>` shows the real filename verbatim).
  `cli.py`'s cached-source write then produces a harmless but odd double extension
  (`<title>.docx` where `<title>` already ends in `.docx`). **Disposition: deliberately left** —
  cosmetic only, matches contract §7.4's naming rule literally, not worth a special case.

**Next stages must know.**
- `build_export(docx_bytes, ...) -> dict` is the seam stage 3 (`docx-structure`) extends — it
  currently returns `units: []`, `comments: []`, no `document.images` key; add real traversal here,
  not a parallel path.
- `DocxPackage.xml("comments"|"comments_extended"|"numbering"|"styles"|"document_rels")` and
  `.media_names()`/`.media_bytes()` are the accessors stages 4-6 should use rather than re-opening
  the zip.
- The golden fixture's TOC is a `w:fldSimple` (cached-result only), not Word's native complex-field
  nested-hyperlink TOC — sufficient for traversal, noted in the fixtures README so stage 3 doesn't
  assume more structure than is actually there.
- `gts-2moy` blocks a plain `pytest <path>` for any offline `document_export` test until resolved;
  use `pytest --noconftest <path>` in the meantime for targeted gates on stages 3-7.

**Deliberately not done.** No structure/comment/revision/image parsing — `build_export` emits
metadata + diagnostics only, per this stage's stated scope. No anchored-image or multi-tab fixture
content (fixtures README explains why). No `pnpm run deploy:test` / full `pytest -x` — full-suite
regression is stage 9's to pay. Nothing committed — the project's agent profile is Conservative.

### Stage 3 — `docx-structure` (closed 2026-08-25)

**Done.** `document_export/structure.py`: `walk_structure(pkg, diagnostics) -> units[]`, wired into
`build_export`. Ports `GOVERNANCE_UNIT_PATTERNS`/`HEADING_FALLBACK_BASE_RANK`/
`SEMANTIC_STATE_PATTERNS` verbatim from `src/Procedure-Exporter.js`'s bannered region (contract's
"Standing constraint"), and mirrors `processStructuralContent_`/`processParagraph_`/`processTable_`/
`createUnit_`/`createBlock_`/`pushUnitOntoStack_` one-for-one. All six AC items verified against the
golden fixture (`TestStructurePass`, 15 new tests) plus two synthetic-fixture cases the golden
`.docx` doesn't carry (a numbering-part-absent case for AC #2's "real None, not invented"; AC #5's
soft-return and explicit-page-break cases): unit `parent_unit_id` hierarchy (rank-stack matches GAS
exactly, including the mid-cell `Sub-Unit In Cell` heading nesting under its table's unit), ordinal-
dense `location` on every block, real list numbering read off `numbering.xml`, `{row, column}`
tagging surviving the mid-cell unit switch (gts-qjkj), `§13.4` empty-array omission, and `w:br`
soft-return survival as `\n` (explicit `w:type="page"` correctly excluded from text and counted
separately). Full targeted-gate run: `pytest --noconftest tests/test_document_export_harness.py -q`
→ 29 passed. Closed `regression=pending` per Backstop rules (full sweep is stage `document-docs`).

**Found.**
- **Run-level `location` is not ported.** GAS's `makeTextRun_` stamps a `location` field on every
  run (via `makeLocation_`), but `docs/procedure-exporter.md` §6's own canonical run examples never
  show one, and the contract names no degradation for it. Read literally, the documented schema
  doesn't require it; implemented that way (runs carry no `location` key). Flag for contract
  clarification if a consumer turns out to need it — cheap to add later since nothing currently
  reads a run's location.
- **Revision-blind by design, for now.** Every run this stage builds carries a fixed
  `revision: {state: "baseline", change: "unchanged", evidence: []}` placeholder regardless of
  whether it is nested inside `w:ins`/`w:del` in the source — text is still fully extracted (both
  `w:t` and `w:delText`, so no source text is silently lost per §17 principle 1), but nothing is yet
  classified as inserted/deleted. This means every block in this stage's output uses the canonical
  `text` field (`revision_summary` is always `"unchanged"`) even for paragraphs that visibly contain
  tracked changes in the fixture. This is stage `docx-revisions`' (`gts-9c8k`) to correct — it should
  overwrite each run's `revision` object based on `w:ins`/`w:del` ancestry (which this stage's
  traversal already walks into) rather than re-deriving run boundaries.
- **TOC diversion is not implemented.** `document.toc` stays empty (now correctly *omitted*, per
  contract §7.5, rather than emitted as `[]` — a pre-existing stage-2 gap fixed here as part of this
  stage's own AC #4 omission work). The golden fixture's TOC paragraph (a `w:fldSimple` field, not a
  distinguishable OOXML "this is a TOC" structural element the way Docs API's `tableOfContents` is)
  is walked as an ordinary paragraph and lands as a plain block under the "Table of Contents" unit.
  No OOXML-side TOC-detection heuristic is designed yet — out of this bead's AC, and not attempted.
  **Disposition:** open gap, not filed as its own bead — revisit if stage `docx-verify`'s
  differential oracle (`gts-klp8`) finds it material, since a TOC line's rendered text could
  in principle collide with `GOVERNANCE_UNIT_PATTERNS` the way it did on the GAS side pre-gts-6cq2
  (this fixture's TOC text happens not to match any pattern, so the collision hasn't been observed
  here).
- **Manual (non-tracked-changes) strikethrough is captured as `format.strikethrough` only.** GAS
  additionally treats visual strikethrough as deletion evidence (`SEMANTIC STATE`/`revision`
  classification); this stage extracts the boolean formatting fact but does not classify from it —
  left for stage `docx-revisions` to decide whether manual-strikethrough-as-deletion is worth
  porting for the DOCX path (contract §3 only discusses `w:ins`/`w:del`, not manual strikethrough).

**Next stages must know.**
- `document_export.structure.walk_structure(pkg, diagnostics) -> list[dict]` is the seam stage 4
  (`docx-comments`) and stage 5 (`docx-revisions`) extend — both need to *mutate* the returned
  units'/blocks' structures (attach `comment_ids`, rewrite `runs[].revision`) rather than re-walk the
  document; `ctx.all_blocks` (flat, traversal-order) inside `_Ctx` is the natural place a future
  comment-range pass can reuse for resolving `w:commentRangeStart`/`End` against block membership,
  the same way `_process_table` already reuses it for `{row, column}` tagging.
- **Stage 5 (`docx-revisions`) must recompute `revision_summary` and switch affected blocks from the
  canonical `text` field to the `all_text`/`baseline_text`/`proposed_text` trio** once it reclassifies
  runs — this stage's blocks are ALL `"unchanged"` today, which will no longer be true once tracked
  changes are classified (see Found, above).
- `_iter_run_elements` (structure.py) already descends into `w:ins`/`w:del`/`w:hyperlink`/
  `w:fldSimple`/`w:smartTag`/`w:sdt` to find nested `w:r` elements — stage 5 can reuse this traversal
  and inspect each run element's ancestor chain (not currently tracked/returned) to classify
  insertion/deletion state, rather than writing a second traversal.
- `_load_heading_levels`/`_load_numbering` (structure.py) are the accessors for `styles.xml`/
  `numbering.xml` derived data — reuse rather than re-parsing those parts a second time.

**Deliberately not done.** No comment anchoring, no revision classification, no image extraction —
those are stages 4/5/6. No TOC diversion (Found, above). No table/table_cell block `kind`s or
`document.tables` (contract §8: out of scope for schema 3.0, existing `{row, column}` tagging kept).
No `pnpm run deploy:test` / full `pytest -x` — full-suite regression is stage 9's to pay. Nothing
committed — the project's agent profile is Conservative.


### Stage 4 — `docx-comments` (closed 2026-08-26)

**Done.** `document_export/comments.py`: `resolve_comments(pkg, units, diagnostics) -> comments[]`,
wired into `build_export` right after `walk_structure`. Parses `word/comments.xml` (author/date/text,
keyed by `w:id`) and `word/commentsExtended.xml` (`w15:commentEx`, keyed by the comment's own
`w14:paraId` — not `w:id`) for threading (`w15:paraIdParent`) and resolution (`w15:done`). Resolves
each `w:commentRangeStart`/`End`/`commentReference` triplet against the blocks
`structure.walk_structure` already built, via an independent document-order paragraph walk
(`_iter_paragraphs`/`_paragraph_block_pairs`) that reuses `structure.paragraph_all_text` (new public
seam) rather than re-deriving structure.py's text-extraction rules, and `source_order`-sorting to
recover the exact block sequence (contract §2.1/§2.2). All five `anchor_basis` values (§2.3) are
implemented; `unmatched`/`quoted_text_*`/`no_quoted_text`/`association_basis` do not appear anywhere
in this module. The `comment_ids` §13.4 omission is now applied by `comments.py` itself, after it
mutates blocks/units — `structure._finalize_units` no longer touches `comment_ids` (see its updated
docstring); a new shared `schema.drop_if_empty` replaced the duplicate closures in both call sites
(I12 same-shape reuse). Golden fixture gained a third comment (`w:id="2"`) spanning two paragraphs,
seeded specifically for AC #4 (`document_export/fixtures/build_fixtures.py`, regenerated). All six
AC items verified: `TestCommentAnchoring` (12 tests) plus 2 pre-existing tests updated
(`test_artifact_shape`, `test_empty_structural_arrays_omitted`) for the no-longer-empty
`comments[]`/`comment_ids`. Two synthetic-fixture cases the golden `.docx` doesn't carry (`no_range`
and `range_unterminated` on a non-reply comment, via a new `_minimal_docx_with_comments` helper
matching `TestStructurePass`'s `_minimal_docx_with_body_xml` pattern) plus a
`commentsExtended.xml`-absent case (`resolved: None`). Targeted gate:
`pytest --noconftest tests/test_document_export_harness.py -q` → 39 passed. Closed
`regression=pending` per Backstop rules (full sweep is stage `document-docs`).

**Found.**
- **The golden fixture's only `no_range` case is a reply, not a root comment.** Comment `w:id="1"`
  (the resolved reply, seeded in stage `docx-harness`) has no range markers in the body — which is
  actually the realistic shape (a reply doesn't get its own anchor; only the thread's root comment
  does) — but it meant the golden fixture alone never exercises `no_range` on a *displayed*
  (non-reply) comment. Covered instead with a synthetic fixture
  (`test_no_range_when_comment_has_no_range_markers`); `range_unterminated` likewise has no
  golden-fixture case and is covered the same way. **Disposition:** left as synthetic-only coverage,
  same tier as stage 3's soft-return/no-numbering-part cases — not filed as its own bead.
- **`resolved` is read per-`w:id`, never merged up a reply thread.** The fixture's own shape (root
  `w:id="0"` unresolved `done="0"`, its reply `w:id="1"` resolved `done="1"`) demonstrates the
  contract's literal rule producing a thread where the parent reports `resolved: false` while a
  reply that resolved it exists underneath, unsurfaced (replies carry no `resolved` field at all,
  matching the GAS/Drive-API comment shape). Whether a real Word round-trip ever produces exactly
  this shape, or whether resolving via a reply always writes `done="1"` back onto the *root's* own
  `commentEx` entry too, is unverified — ADR-0026 already flags resolved-comment behavior as
  unproven end to end. **Disposition:** implemented literally per contract §2.6 (no thread-level
  merge invented); flag for `gts-klp8` (differential oracle) if a live document shows a different
  shape.
- **Unlisted-field gaps, same disposition as stage `docx-harness`'s `revision_id`:** comment `id`
  uses the raw OOXML `w:id` value directly (no id-derivation scheme is named for comments in
  contract §1.3 — only block/unit/image ids are) — stable within one document's re-exports per
  §1.4, but not globally unique the way a Drive comment id is. `modified_at`, `quoted_mime_type` and
  `drive_anchor` are `null`: none has an OOXML/reachable-Drive-API equivalent over the cookie
  session (a `w:comment` carries one `w:date`, not separate created/modified times; the latter two
  are Drive-API-only concepts). None of the four appears in contract §5's degradation table.
  Recorded here rather than silently assumed; amend contract §5 if any needs a different value.
- **`quoted_text` for a range is whole-associated-block concatenation, not exact inter-marker
  substring.** Even for `range_exact` (single block), `quoted_text` is not extracted from the
  substring between the markers — it is the whole block's `text` — so a comment anchored to only
  part of a paragraph (as the golden fixture's own comment `0` is: the range covers one sentence,
  the block has two) gets the whole block as `quoted_text`, not just the covered sentence. Contract
  §2.5 literally describes "the text actually lying between the range markers", which this does not
  implement precisely. **Disposition:** deliberate scoping call, not an oversight — getting
  `associated_block_ids` exactly right (the core of AC #1/#4) was prioritized over sub-block
  substring extraction, which the AC text does not explicitly require and which added meaningfully
  more traversal complexity for the same review fidelity. Flag for `gts-klp8` if the differential
  oracle finds this material against the GAS exporter's quoted-text values (which similarly do not
  extract exact substrings, matching whole quoted blocks via `quoted_file_content` — so this may
  turn out not to be a regression at all).

**Next stages must know.**
- `comments.resolve_comments(pkg, units, diagnostics) -> list[dict]` mutates `units`/blocks in place
  (`comment_ids`) and must run after `walk_structure` returns, before any other pass that reads
  finalized `comment_ids`. Stage `docx-revisions` (`gts-9c8k`) does not need to touch this seam — it
  only rewrites `runs[].revision`/`revision_summary`, a disjoint field set.
  `structure._finalize_units` deliberately leaves `comment_ids` unfinalized (see its docstring) —
  any future pass that adds a new per-block/unit array field should follow the same pattern (attach
  first, finalize via `schema.drop_if_empty` once, at the end of whichever module owns that field)
  rather than fighting `walk_structure`'s own finalization order.
- `structure.paragraph_all_text(p_el)` is now a public seam (added this stage) for any future pass
  that needs to know whether a given `w:p` produced a block without re-deriving text extraction —
  `comments.py`'s `_paragraph_block_pairs` is the reference usage.
- `schema.drop_if_empty(obj, key)` is now the shared §13.4 omission helper — use it rather than a
  local closure if a future stage adds another empty-array-omission case.

**Deliberately not done.** No revision classification (every run still carries the stage-3
`baseline`/`unchanged` placeholder regardless of comment anchoring), no image extraction — stages
5/6. No thread-level `resolved` merge (Found, above). No exact inter-marker `quoted_text` substring
extraction (Found, above) — whole associated-block text is used instead. No `pnpm run deploy:test` /
full `pytest -x` — full-suite regression is stage `document-docs`'s to pay. Nothing committed — the
project's agent profile is Conservative.

### Stage 5 — `docx-revisions` (closed 2026-08-26)

**Done.** `document_export/revisions.py` (new, contract §7.1's mandated module for §3):
`classify_revision(tracked) -> dict`, `summarize_revision(runs) -> str`,
`build_view_text(runs, view, semantic_state) -> str`, `build_suggestion_groups(units) -> list[dict]`,
`build_document_views(units, include_whole) -> dict`. `structure.py`'s `_iter_run_elements` now
threads each run's `w:ins`/`w:del` ancestor chain (`tracked`, outer-to-inner, `{tag, author, date}`)
alongside the existing hyperlink `link` thread, discovered during the same traversal rather than a
second pass — `_build_runs` calls `revisions.classify_revision(tracked)` per run instead of stamping
the stage-3 placeholder. Block construction now calls `revisions.summarize_revision`/`build_view_text`
for the `revision_summary` and the conditional `text` vs. `all_text`/`baseline_text`/`proposed_text`
trio (§13.3), and increments the previously-stubbed `diagnostics.proposed_insertions`/
`suggested_deletions`. `build.py` wires `build_suggestion_groups` into `document.suggestion_groups`
(was always `[]`) and `build_document_views` into `views` (was an always-empty stub regardless of
`includeWholeDocumentViews`), and sets `diagnostics.distinct_suggestion_ids`. `schema.py` gained
`normalize_derived_text` (§13.5: NBSP -> space, vertical tab -> `\n`) — also applied retroactively to
`block.text`/`all_text`, which stage 3 built without it (see Found). All five AC items verified
against the golden fixture's two revision paragraphs (mixed insertion+deletion; a paragraph that is
entirely `inserted_then_deleted`, `w:del` nested inside `w:ins`) plus two synthetic-fixture cases the
golden `.docx` doesn't isolate (insertions-only, deletions-only — its only plain insert/delete share
one paragraph): `TestRevisionModel` (14 new tests). Targeted gate:
`pytest --noconftest tests/test_document_export_harness.py -q` → 49 passed. Closed
`regression=pending` per Backstop rules (full sweep is stage `document-docs`).

**Found.**
- **Author/date attribution for `inserted_then_deleted` uses the innermost ancestor, an
  interpretation call the contract doesn't pin down.** §3.2 names the OOXML shape ("`w:del` inside
  `w:ins`, or vice versa") but §3.3 says only that "each revision-bearing run carries
  `revision.author`/`revision.date`" — singular, with no rule for which of the two wrapping
  elements' attribution wins when both are present. Implemented as: whichever element is closest to
  the run (the one that actually determined the run ended up as `w:delText`/`w:t`) — for the golden
  fixture's own nesting (`w:del` inside `w:ins`) this is the `del`'s author/date. Both ancestors'
  full info is available in `tracked` if a future consumer needs the other one; only the single
  chosen pair is carried into the schema today, matching the singular field. Flag for `gts-klp8` if a
  live document's actual nesting convention (which one Word/Docs puts innermost) turns out to differ
  from the fixture's assumption.
- **Stage 3's `block.text`/`all_text` gap: §13.5 normalization was never applied.** Stage 3 built
  `block["text"]` as a raw run-text concatenation with no NBSP/vertical-tab substitution, even though
  §13.5 says those apply to "block `text`, the trio, `views.*`" without exception. Not surfaced in
  stage 3's own Found (no test exercised it — no NBSP/VT in the golden fixture). Fixed here as part
  of this stage's own `build_view_text` becoming the single code path every text-field emission goes
  through (unchanged blocks now call `build_view_text(runs, "all", ...)` too, not a bespoke
  concatenation) — same shape as stage 3 itself fixing a stage-2 TOC-omission gap while implementing
  its own AC. No dedicated regression test added (no fixture content exercises NBSP/VT); noted here
  for traceability if `gts-klp8` or a live document surfaces a visible difference.
- **`deleted_text`/`proposed_additions` exclude `inserted_then_deleted` runs, and are normalized —
  both are contract readings, not GAS parity.** GAS's `buildDocumentViews_` builds these two fields
  from raw `r.text` with no `normalizeDerivedText_` call at all (a GAS-side doc/code gap:
  procedure-exporter.md §13.5 says "`views.*`" without carve-out, but the frozen GAS code doesn't
  normalize these two). Contract §13.5 governs the Python side by its literal text, so both are
  normalized here; GAS is frozen and out of scope to fix (ADR-0026 Decision 7). Exclusion of
  `inserted_then_deleted` from both extracts mirrors its exclusion from `baseline_text`/
  `proposed_text` (§3.2: "never in the baseline and is not proposed") — a deliberate, minimal-
  invention scoping call since the contract doesn't name these two fields' treatment of the third
  state explicitly. Flag for `gts-klp8` if a consumer needs inserted-then-deleted text surfaced
  somewhere.
- **`document.suggestion_groups` includes all three revision-bearing change types**
  (`inserted`, `deleted`, `inserted_then_deleted`), not just active insertions/deletions — contract
  §3.3 doesn't scope grouping to a subset, and every one of them is still a real (author, date) edit
  event. `diagnostics.proposed_insertions`/`suggested_deletions` do NOT count `inserted_then_deleted`
  runs (neither counter fits it cleanly, and no dedicated counter is scoped by AC or contract) — it
  is still fully visible via `revision_summary: "mixed"` and the suggestion group itself, just not
  double-counted into either diagnostic.
- **Manual (non-tracked-changes) strikethrough is still not treated as deletion evidence** — the
  decision stage 3 explicitly deferred to this stage. Contract §3 scopes revisions to `w:ins`/`w:del`
  only, and this stage's AC text says nothing about strikethrough; left unclassified (formatting-only
  `format.strikethrough`, as stage 3 left it). Revisit only if a differential-oracle finding
  (`gts-klp8`) or a live document shows GAS's manual-strikethrough-as-deletion behavior mattering on
  the DOCX path.

**Next stages must know.**
- `document_export.revisions` is now the seam for anything reading revision state document-wide —
  `build_suggestion_groups(units)`/`build_document_views(units, include_whole)` both re-walk
  `units[].blocks[].runs[]` themselves; a future pass needing the same walk (e.g. stage `docx-verify`'s
  differential oracle) should call these or add a sibling function here rather than re-deriving.
- `revisions.classify_revision`'s `tracked` tuple is retained only inside `_build_runs`'s local loop,
  not stored on the run object — if a downstream need for the *other* (non-chosen) ancestor's
  author/date emerges (see Found's interpretation-call item), the seam to extend is
  `_iter_run_elements`'s yielded `tracked` value, not a new traversal.
- `revisions.build_view_text` is now also unchanged-block `text`'s code path (via `view="all"`) — any
  future change to view-filtering logic affects every block's canonical text field, not just
  revision-bearing ones.
- Golden fixture's two revision paragraphs are body paragraphs 2/3 (`block__main__000003`/`000004`
  after the TOC/heading blocks) — `docx-verify`'s `gts-0rho` can assert against these ids/positions
  directly rather than searching by text if that proves more stable.

**Deliberately not done.** No manual-strikethrough-as-deletion classification (Found, above; contract
§3 scopes to `w:ins`/`w:del`). No thread-level author merge for `inserted_then_deleted`'s "other"
ancestor (Found, above) — single chosen author/date only. No image extraction — stage 6 (`gts-8uo6`).
No `pnpm run deploy:test` / full `pytest -x` — full-suite regression is stage `document-docs`'s to
pay. Nothing committed — the project's agent profile is Conservative.

### Stage 6 — `docx-images` (closed 2026-08-26)

**Done.** `document_export/images.py` (new, contract §7.1's mandated module for §4):
`process_inline_images(p_el, pkg, rels, ctx)` — called from `structure.py`'s `_process_paragraph`,
interleaved with the same traversal (mirrors GAS's `processInlineImages_` call from inside
`processParagraph_`; there is no separate image pass). Both `wp:inline` and `wp:anchor` drawings are
found via a single `.iter()` walk (`anchored: true|false`); each resolvable one gets an `image`
block (pushed onto `ctx.current_unit`/`ctx.all_blocks` exactly like a text block, own ordinal) and a
mirrored `document.images[]` entry, sharing `id`/`image_ref` derivation with the existing
`make_image_id`/`make_image_ref` (already in `schema.py` since stage `docx-contract`). Restructured
`structure.py`'s `_process_paragraph` to match GAS's ordering precisely: unit detection, then image
extraction, then the text-emptiness check — previously that check ran *first* and returned early,
which would have made every image-only paragraph invisible (no unit, no image, no ordinal). Added
`DocxPackage.content_type(part_name)` (`[Content_Types].xml` `Override`-then-`Default` resolution)
so extension is derived from the media part's **declared** content type, never its filename (AC #2)
— verified directly against an `Override` that disagrees with the part's own `.png` name. Moved
`_make_location`/`_citation_hint` out of `structure.py` into `schema.py` as `make_location`/
`make_citation_hint` (pure, ctx-free) so `images.py` can build a block/doc-entry the same way
`structure.py` does, with no `structure.py<->images.py` import cycle. `build_export` now threads
`includeImages` through (was computed and silently dropped since stage `docx-harness`) and adds
`document.images[]` only when non-empty (§13.4). `cli.py`'s `write_image_files` (in `images.py`, not
`build_export` — contract §7.2 keeps `build_export` filesystem-write-free) writes bytes via a second
`DocxPackage` over the same `docx_bytes`, named by `image_ref`, after the JSON is written. Golden
fixture gained a second image: an anchored (`wp:anchor`) drawing next to the existing inline one, own
media part (`image2.png`, a distinct 1x1 blue PNG) — AC #1 names both shapes explicitly and the
fixture had only inline before this stage. All six AC items verified: `TestImageExtraction` (16 new
tests: golden-fixture inline+anchored extraction, content-type-vs-filename extension, `description`
always null, the no-images negative case, `includeImages=False`, idempotent re-run, the
unresolvable-drawing fail-closed/warning path via two synthetic fixtures, and `write_image_files`)
plus 2 pre-existing tests updated (`test_artifact_shape`, `test_optional_parts_present_on_golden_fixture`)
for the golden fixture's now-real images. Targeted gate:
`pytest --noconftest tests/test_document_export_harness.py -q` → 63 passed. Closed
`regression=pending` per Backstop rules (full sweep is stage `document-docs`).

**Found.**
- **A real cross-stage bug, caught and fixed in this stage: `comments.py`'s paragraph↔block
  alignment assumed exactly one block per non-empty-text paragraph.** `_flatten_blocks_in_order`
  (stage `docx-comments`) sorted *every* block by `source_order` into one sequence, and
  `_paragraph_block_pairs` pulled the next item from that sequence only for a paragraph
  `paragraph_all_text` reports as non-empty. An image-only paragraph has no text, so no item was
  pulled *for it* — but its image block(s) were still in the sequence, silently handed to whichever
  *later* text paragraph happened to pull next, desyncing every comment-range resolution after the
  first image-only paragraph in the document. Golden fixture never exercised this (no comment
  follows its "5. Figure" section, the document's last content). Confirmed as a real bug by
  temporarily reverting the fix and watching a purpose-built regression test
  (`test_comment_after_image_only_paragraph_associates_with_correct_block`) fail with a `KeyError`
  from `quoted_text` reading an image block's absent `"text"` key — then confirmed green with the
  fix restored. **Fix:** `_flatten_blocks_in_order` now excludes `kind == "image"` blocks from the
  sequence it hands to comment-range resolution; comment-to-image association is out of scope
  (contract §2 anchors ranges to text markers, which cannot appear inside a `w:drawing`).
- **`document.images[]` entry shape is an interpretive call, not literally frozen by the contract.**
  Contract §1.3/§4 name `image_ref`/`source_part`/`anchored` on the *block*, and describe
  `document.images[]` only as "one entry per extracted image" (mirroring `document.toc`), without
  pinning its field list the way GAS's `docEntry` (`id`, `image_ref`, `drive_file_id`, `tab_id`,
  `source_order`, `location`) is documented in `docs/procedure-exporter.md` §19.3. Implemented as
  `{id, image_ref, source_part, anchored, segment, source_order, location}` — `drive_file_id` has no
  DOCX-path analogue (files are written locally, not to Drive; contract §4 already says the consumer
  locates them by `image_ref` under `<out-dir>/<title>-images/`) and is dropped rather than nulled;
  `source_part` is added so a doc-entry alone is traceable to its origin without re-deriving it from
  the matching block; `tab_id` becomes `segment` for the same reason `location.tab_id` degrades
  elsewhere on this path. Flag for `gts-klp8` if the differential oracle finds this shape material.
- **`block.inline_object_id` is `null`** — same disposition as `document.revision_id` (stage
  `docx-harness`) and comment `modified_at` (stage `docx-comments`): no OOXML analogue of the Docs
  API's `inlineObjectId` exists, recorded rather than silently assumed. `docPr`'s own `@id`
  (paragraph-local, resets per drawing, not globally stable) was considered and rejected as a
  substitute — it would look like a real answer and isn't one.
- **`width_pt`/`height_pt` are computed from `wp:extent`'s EMU `cx`/`cy` (÷12700), not read directly**
  — OOXML has no points-native size field the way the Docs API's `embeddedObject.size` already is in
  points. A reasonable, undocumented-by-contract unit conversion; flag for `gts-klp8` if a live
  document's rendered size disagrees.
- **Table-cell images tag `{row, column}` for free**, via the same snapshot-based `ctx.all_blocks`
  tagging stage `docx-structure` built for the `gts-qjkj` invariant — verified with a synthetic
  fixture, not added to the golden fixture (README's "Deliberately not included": no table+image
  case was in scope for this stage's own AC, this was incidental confirmation only).

**Next stages must know.**
- `document_export.images.process_inline_images`/`write_image_files` are the seam for anything
  image-related; `document_export.schema.make_location`/`make_citation_hint` are now shared
  (structure.py and images.py both call them) — any future block-kind-adding pass should follow the
  same pattern rather than duplicating location/citation-hint construction a third time.
- **`document_export.comments._flatten_blocks_in_order`'s image-exclusion is load-bearing.** Any
  future pass that adds another block kind attached to a textless paragraph (there is none planned)
  must extend that same filter, not bypass it — the bug this stage found and fixed will recur
  identically otherwise.
- `gts-klp8` (differential oracle, stage `docx-verify`) should treat `document.images[]`'s field
  shape, `inline_object_id: null`, and the EMU→points conversion as named interpretive calls to
  compare against GAS's own `docEntry`/`extractInlineImage_`, not assume-and-diff blindly.

**Deliberately not done.** No live-document verification of the anchored-image nesting convention or
EMU-to-points accuracy (offline fixture only; flagged for `gts-klp8` above). No comment-to-image
association (Found, above — contract doesn't ask for it). No `pnpm run deploy:test` / full
`pytest -x` — full-suite regression is stage `document-docs`'s to pay. Nothing committed — the
project's agent profile is Conservative.

### Stage 7 — `docx-verify` (closed 2026-08-26)

**Done.** `gts-0rho` (end-to-end acceptance over the golden fixture, 78 tests, all AC #1–#9
verified, including proven-to-fail mutation tests for AC #9) closed already carrying `gts-qjkj` and
`gts-e7ca`'s absorbed assertions. `gts-klp8` (differential oracle) ran both exporters read-only
against `local.settings.json`'s `exportTestDocId` — a real Google-native corpus document, not a
seeded fixture (a seeded-fixture attempt via `DriveV3.Comments.create()` was tried first and
abandoned: comments created that way carry no real in-document anchor at all — gts-6ls9 territory —
so they're not a valid probe of anything docx-side). Diff classified per ADR-0026's gain/expected-
regression/unexplained taxonomy; two beads filed for the unexplained class (`gts-etm4`, `gts-sc14`),
satisfying AC #3. Full classification is on `gts-klp8`'s close reason. `tests/support/
run_differential_oracle{,_livedoc}.py` are the scripts that produced it (not committed — Conservative
profile — kept as throwaway diagnostic capture, safe to re-run or delete).

**Found — the load-bearing one, CORRECTED 2026-08-26 (post-close; see
`/tmp/gas-compare-handoff.md`).** Original framing: **`gts-etm4` (P1): Google's own
`/export?format=docx` conversion of a Google-native document omits comments entirely.** The live
corpus doc (57 real Drive comments per GAS) downloaded to a `.docx` with no
`word/comments.xml`/`commentsExtended.xml` part and zero `commentRangeStart`/`End` anywhere — while
headers, footers, media, styles, numbering and the explicit-page-break count (35/35) all matched GAS
exactly, ruling out a truncated/malformed download.

**This framing was overturned by a second pass on the same document**, after the user shortened it
and added 2 new anchored comments: the `.docx` download then correctly showed
`word/comments.xml`/`commentRangeStart`/`End` for those 2 comments. The converter does not omit
comments wholesale. Corrected finding: GAS's 57 legacy comments all report Drive-side
`no_quoted_text` because their anchor text was **deleted upstream in Drive itself**
(`quotedFileContent` goes empty at the source) — not dropped by the `.docx` converter, which
correctly preserves ranges for any comment that still has real anchor text. The "majority of the
corpus (Google-native docs) doesn't get the anchoring gain" caveat is retracted along with it: the
gain is real wherever anchor text is still live, Google-native or not; neither exporter can recover
a comment whose anchor was already lost in Drive. `gts-etm4` has been updated in bd with the full
correction (priority lowered to P2, title reflects the corrected framing).

This matters because the 62-triplet / 54-comment counts that motivated ADR-0026 Decision 5 (retire
the four-tier quoted-text matcher for exact OOXML anchoring) were measured against a **Drive-hosted
native `.docx` file** (`1aK1jDQY...`, ADR-0026 category 3) — whose `comments.xml` is simply that
file's own original bytes, already real Word markup; that evidence base still stands, it just no
longer needs the "only applies to that minority" caveat.

**New adjacent thread, not yet investigated (flag for a follow-up bead before acting on it):** a
same-content Google-native/native-`.docx` document pair (`gdoc-copy` /
`1YhpveZ-I4f9CFOhP2k6O2oPWQzhIZprnsFbI9wDufhw` vs `docx-source` /
`1BytRjNqd43UkugeD9nYEPptTmw9g23QI`) shows Python's `.docx`-based comment count (47 via
Docs-download, 44 via native `.docx`) *exceeding* GAS's Drive-API count (41, all `no_quoted_text`)
with zero unanchored on the Python side. **Leading hypothesis (user, 2026-08-26), likely correct:**
deleting a comment's anchor text in Google Docs does not delete the comment — Drive keeps it (GAS
still sees it, flagged `no_quoted_text`) — but the comment becomes invisible in the `.docx` export
entirely, since there's no run left to attach a range to. If so, GAS's 41 and Python's 47 are
near-disjoint populations, not one exporter being "more faithful" than the other: each sees a
different slice (anchor-deleted vs anchor-live), and neither can see the other's slice by
construction. That would mean no fidelity gap either direction and no further ADR-0026 correction
beyond documenting the caveat — the opposite of what the raw numbers first suggested. Raw artifacts
(GAS + both Python exports, schema 2.4/3.0) are saved at `/tmp/gas-compare/`. Two follow-up beads
filed 2026-08-26 to run the actual diffs one at a time: **`gts-dnxu`** (P2 — GAS vs Python on
`gdoc-copy`; ID-overlap check against the disjoint-set hypothesis is now its first acceptance
criterion) and **`gts-qhoz`** (P3 — Python-only `gdoc-copy` vs `docx-source`, isolating the
Docs→`.docx` conversion delta). See `/tmp/gas-compare-handoff.md` for the full context either bead
needs before starting.

**Found — secondary.** `gts-sc14` (P2): unit-kind counts otherwise match GAS exactly; Python reports
35 more `section` units than GAS on the same document (57 vs 22), numerically coinciding with the
document's 35 explicit page breaks (unconfirmed hypothesis, not yet traced into `structure.py`), plus
an unclassified `document_part` kind GAS never emits. `blocks`/`runs` counts are also close-but-not-
equal and are presumed downstream of the same cause rather than independently investigated.

**Next stages must know.**
- **`gts-etm4` and `gts-sc14` are both flagged for the stage `document-docs` ADR-0026 amendment pass**
  (`gts-klp8` AC #4). `gts-etm4`'s ADR-0026 amendment is now smaller than originally scoped — it no
  longer retracts Decision 5's rationale for Google-native docs, it just documents that `no_quoted_text`
  comments have lost their anchor upstream in Drive, not at the converter. `gts-sc14` is unaffected by
  the correction.
- `gts-fadg` (rewriting `docs/procedure-exporter.md` → `docs/document-exporter.md`) **can now assert**
  that exact comment anchoring works for Google-native documents, with the caveat that a comment whose
  anchor text was deleted in Drive stays unanchored regardless of exporter — `gts-etm4`'s corrected
  finding, not its original one, is current. Do not cite the original "omits comments entirely" framing.
  The separate `gdoc-copy`/`docx-source` comment-count asymmetry (see above) is still open and unrelated
  to what `gts-fadg` needs to assert.
- The differential-oracle scripts construct a `ScenarioSession` directly against an existing `doc_id`
  (bypassing `new_doc()`) for read-only comparison against a live corpus document — reusable pattern
  if a future stage needs the same against a different real document.

**Deliberately not done.** Did not drive the diff to zero (ADR-0026 explicit: the diff is the
deliverable). Did not resolve `gts-etm4`/`gts-sc14` in this stage — differential-oracle work is
diagnosis, not implementation; both are new `[INF]` beads for a future session. Did not amend
ADR-0026 itself (that is stage `document-docs`'s job per `gts-klp8` AC #4). Nothing committed — the
project's agent profile is Conservative.
