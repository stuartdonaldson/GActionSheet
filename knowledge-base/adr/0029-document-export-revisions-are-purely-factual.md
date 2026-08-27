# ADR-0029: Document export represents revisions and unit/block classification as OOXML facts only, with no semantic-interpretation layer

**Status:** Accepted
**Date:** 2026-08-26
**Supersedes:** ADR-0026 Decision 4 ("Schema shape is preserved") for the three fields named below.
Decision 4's other content — schema-shape preservation as the default, the differential-oracle
rationale — stands.
**Amends:** `docs/interfaces/document-export-contract.md` §3.2, §3.3 (table row
`document.suggestion_groups[].possible_authors` retained → group container renamed), and the
"Standing constraint" paragraph, to the extent they lock the three fields below to the GAS 2.4
shape.
**Relates to:** ADR-0026 (DOCX source decision this amends), gts-284o ('governance' → 'document'
terminology migration — same rename mechanics, different field), docs/interfaces/document-export-
contract.md (contract this supersedes in part), first governance-consumer review of the schema
3.0 JSON export (2026-08-26, review response transcribed in this ADR's originating conversation)

## Context

ADR-0026 froze the DOCX-export schema to match the GAS 2.4 shape field-for-field, deliberately, so
the GAS exporter could serve as a differential oracle. That default was correct for the fields it
was protecting (block/unit structure, comment anchoring, image handling) — those are unaffected
here.

Three fields were carried forward under that default without independent justification: they exist
because the GAS 2.4 exporter had them, not because a downstream consumer asked for them in that
shape. The first real consumer review of the schema 3.0 JSON (governance-document review workflow)
flagged all three as actively working against the extractor's now-stated purpose — "primarily
factual" evidence for downstream governance judgment, not a second, competing classification layer:

1. **`document.suggestion_groups`.** The name is a GAS-era holdover from Google Docs' `suggestionId`
   concept. On the DOCX path these are native Word `w:ins`/`w:del` tracked-changes events grouped by
   `(author, date)` — there is no "suggestion" being made; it is a revision that already happened in
   the document's edit history. The name misleads a consumer into treating grouped revisions as
   proposals awaiting a decision.
2. **`semantic_state` / `semantic_state_evidence`** on units and blocks, and the top-level
   `semantics` object defining `baseline`/`proposed`/`historical`/`editorial`. This is a regex-based
   classifier (`_detect_semantic_state`, `document_export/structure.py`) guessing document *intent*
   from surface markers (`(OLD)`, `TBD`, `???`, `FYI`) — a heuristic exactly like the ones ADR-0026's
   Rationale already celebrated retiring ("deleting a heuristic is worth more than optimizing one,
   because every one of them is a place the artifact can be quietly wrong in a way an LLM consumer
   cannot detect"). It was never retired because it predates the DOCX rewrite and nothing in ADR-0026
   named it as in scope. Carrying it forward, undisturbed, contradicts the rewrite's own rationale.
3. **`revision.state`** (`baseline`/`proposed`) alongside `revision.change`
   (`inserted`/`deleted`/`unchanged`) on runs. `state` is a derived label computed from `change`
   (§3.2's table is exactly a `change → state` mapping); it adds a second name for one fact rather
   than a second fact. `change` plus `author`/`date` is everything a consumer needs; `state` invites
   a reader to treat it as an independent signal.

None of the three is required by the coordinate-system change (§1) or the comment-anchoring change
(§2) that ADR-0026 justified on the merits. They are schema-shape preservation applied past the
point it earns its keep.

## Decision

**On the DOCX export path (schema ≥3.1), revision and classification data is represented as OOXML
facts only. No field states or implies a semantic/governance judgment.**

1. **`document.suggestion_groups` is renamed `document.revision_groups`.** Grouping key, membership,
   and all other structure are unchanged (§3.3: `(author, date)`, member run/block ids). Contract
   §3.3's retained-field language is amended to read `revision_groups` throughout.
2. **`semantic_state`, `semantic_state_evidence`, and the top-level `semantics` object are removed
   from the DOCX export path.** The regex classifier (`_detect_semantic_state` and its marker table
   in `document_export/structure.py`) is deleted, not merely hidden — it is dead code once nothing
   reads its output. `_classify_block`'s branches on `semantic_state == "historical"/"editorial"`
   (producing `historical_note`/`editorial_note` block kinds) lose their trigger condition; `kind`
   classification for those two block types is retired on this path along with it. Blocks that
   relied on `historical`/`editorial` exclusion from `baseline_text`/`proposed_text` (§3.2's
   `_EXCLUDED_VIEW_SEMANTIC_STATES`) now follow §3.2's `change`-only rule uniformly — every run is
   in `baseline_text`/`proposed_text` per its own `change` value, with no unit-level override.
3. **Run-level `revision.state` is removed; `revision.change` remains the single fact, alongside
   `author` and `date`.** §3.2's table collapses to a `change`-only column
   (`unchanged`/`inserted`/`deleted`/`inserted_then_deleted`); `baseline_text`/`proposed_text`
   membership is computed directly off `change` (the same map §3.2 already encoded, now with one
   fewer name for it).

**Schema version bumps to 3.1** (additive-shape rename + field removal on the DOCX path only; GAS
2.4 is untouched, consistent with ADR-0026 Decision 7).

**Out of scope for this decision**, per the same review, ranked by the reviewer as higher priority
than any of the above: unit/block hierarchy correctness (heading-boundary detection dropping
ARTICLE FOUR, causing membership Sections 1–5 to nest under ARTICLE THREE) and duplicate/empty
structural units. Those are implementation bugs against the existing structural contract, not a
schema decision — tracked separately (gts-<hierarchy-bug>, gts-<toc-spike>). Comment anchoring
(§2) is explicitly *not* touched by this decision — the same review called it "excellent" and
recommended no change.

## Rationale

- **The reviewer is the schema's actual downstream consumer**, not a hypothetical one; ADR-0026's
  contract was frozen before any consumer had exercised it against a real document. This is new
  information ADR-0026 did not have, not a taste preference.
- **Consistency with ADR-0026's own stated rationale.** ADR-0026 already argued for turning
  heuristics into facts (comment anchoring, suggestion authorship, list numbering). `semantic_state`
  is the one heuristic that rationale should have reached and didn't, because it wasn't touched by
  the DOCX rewrite. This decision closes that gap rather than opening a new direction.
- **`suggestion_groups`→`revision_groups` and `state`-removal are both pure renames/simplifications
  of already-correct underlying data** (the reviewer confirmed group membership, author, and date
  are all correct) — no re-derivation risk, unlike a change to comment anchoring or structure
  extraction would carry.
- **Scoped to the DOCX path only**, consistent with ADR-0026 Decision 7: the frozen GAS 2.4 exporter
  is not touched, so the differential-oracle comparison for the fields ADR-0026 was actually
  protecting (structure, comments, images) is unaffected — only the three named fields diverge, and
  the oracle already has to special-case the `schema_version`-conditional fields in §5 for exactly
  this kind of enumerated, versioned divergence.

## Consequences

**Easier:**
- The export schema now has one representation of "what changed," not two (`semantic_state` vs.
  `revision.change`) plus a third derived one (`revision.state`). A downstream governance-review
  consumer no longer has to decide which of three fields is authoritative.
- `document_export/structure.py` loses a full classifier (marker table, `_detect_semantic_state`,
  the `historical_note`/`editorial_note` block-kind branch) — less code, one fewer place the
  artifact can be "quietly wrong" per ADR-0026's own standard.

**Harder:**
- `document_export/revisions.py`'s `_EXCLUDED_VIEW_SEMANTIC_STATES` mechanism and `build_view_text`'s
  `semantic_state` parameter are removed; every call site that threaded `semantic_state` through
  (`structure.py` lines around `block["baseline_text"] = revisions.build_view_text(runs, "baseline",
  semantic["state"])`) must be updated in the same change, not left calling a signature that no
  longer exists.
- Any existing fixture/golden-file JSON asserting on `semantic_state`, `semantics`, `suggestion_groups`,
  or `revision.state` (`tests/test_document_export_harness.py`, `tests/test_governance_export.py`,
  golden fixtures under `document_export/fixtures/`) breaks and must be regenerated against 3.1, not
  patched field-by-field.
- The differential oracle (gts-klp8) must be told these three fields are expected, versioned
  divergences from the GAS 2.4 baseline (same treatment as the existing §5 table), or every DOCX run
  will report false-positive diffs against the frozen GAS output.
- `historical_note`/`editorial_note` `block.kind` values disappear from the DOCX path; any consumer
  branching on those kind values (none identified at decision time — governance review reads
  `semantic_state`, not `kind`, for this) needs the fallback `kind` behavior confirmed before this
  ships.

## Open questions this ADR does not resolve

- Whether `historical`/`editorial`-style classification has *any* future home (e.g. as an opt-in,
  clearly-labeled `exporter_classification` field, distinct from governance status, as the reviewer
  suggested as a fallback if outright removal proved too costly). This ADR takes the stronger of the
  reviewer's two options (remove, not merely relabel) because the reviewer stated a preference for
  it and no consumer dependency on the softer option was identified. Revisit if one surfaces.
- Whether `revision_groups` or `tracked_change_groups` is the better name — the reviewer offered
  both. `revision_groups` is chosen here as the shorter, `revision.change`-consistent option; no
  material tradeoff between them.
