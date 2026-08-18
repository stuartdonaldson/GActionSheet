# Handoff — gts-2glm (governance exporter hardening tests) — 2026-08-13

## Where this session started

Resumed governance-exporter work (gts-ipoy) after a prior-session revert to
an older commit "to verify some work." Session opened with a status review:

- Current branch `tmp/pr3-pr4-combined` already contained the
  governance-exporter comment-traceability merge (`361bf04`) — nothing was
  lost in the earlier revert.
- Cleaned up 3 stale git worktrees + their branches (two `worktree-agent-*`
  copies referencing already-deleted `DocumentNormalizer.js`/
  `FloatingActionParser.js`; `spike/menu-regression-3wk-ago`, already merged
  and superseded).
- Found 44 uncommitted files that turned out to be a *separate*,
  already-bd-closed thread (`gts-pm72` GAS retry backstop, `gts-hroj`
  diagnostics-hook-ordering fix, `gts-ir1f` in-progress syncAll batching
  retrofit) that had never actually been committed to git. Logged a
  work-log.md entry and committed it as `b77b63b` to clear the bd/git
  inconsistency before touching the exporter.

## gts-2glm work this session

Claimed `gts-2glm` (`bd update gts-2glm --status in_progress`), the `[TST]`
twin blocking `gts-ipoy`'s close. Per the twin-ticket "no shared context"
rule, explicitly asked and got permission to relax it (single-operator
context) — read `src/Procedure-Exporter.js` in full before writing tests.

### 1. Testability seam (src/Procedure-Exporter.js)

`exportGovernance_()` hardcoded `DocumentApp.getActiveDocument()`
(add-on-UI-session-only) — no headless call-site existed. Added an optional
`options.docId` param: falls back to `getActiveDocument()` when omitted, so
production entry points (`onGovernanceExportMenu`,
`onGovernanceExportAndPdfMenu`, `onExportGovernanceJson`,
`onExportGovernanceJsonAndPdf`) are byte-for-byte unchanged — they never
pass `docId`. Also fixed the doc-title fallback (`apiDoc.title ||
appDoc.getName()` → `apiDoc.title || documentId`) since `appDoc` no longer
exists when the seam path is used. `node --check` clean.

### 2. Test-support routes (src/WebApp.js)

Three new `testToken`-gated routes, all construct-fixtures-or-call-entry-
point only, never touched by production code:

- **`export_governance_json`** (`_handleExportGovernanceJson`) — the seam's
  only caller. `{docId, exportPdf?}` → `{ok, json, jsonFileId, pdfFileId?}`.
  This *is* the call-site gts-2glm's description asked for.
- **`seed_doc_content`** (`_handleSeedDocContent`) — generic
  `Docs.Documents.batchUpdate()` passthrough. `{docId, requests:[...]}` →
  `{ok, replies}`. Lets tests build arbitrary formatted content (headings,
  page breaks, bold runs, highlight colors) using the standard Docs API
  request shape instead of a bespoke GAS builder per scenario.
- **`create_doc_comment`** (`_handleCreateDocComment`) — `DriveV3.Comments.
  create()` passthrough. `{docId, content, quotedText?}` → `{ok,
  commentId}`. Real Drive comments are creatable via API (unlike Docs
  Suggested-edits — see gap below), so this drives
  `associateCommentsToBlocks_` with real data rather than a mock.

Deployed to TEST twice (`v0.2.2 Rev. Aug 13, 2026 09:07 (TEST)` is current).
Hit one transient `HTTP 404` on the second deploy's health check —
resolved itself after ~15s (known GAS deployment-propagation lag, not a
code issue) — confirmed via `python scripts/call_webapp.py get_test_config`.

**Smoke-verified all three routes live** against `TEST_DOC_ID`:
`export_governance_json` returned a full, correctly-shaped JSON export;
`seed_doc_content` successfully inserted text via `insertText`;
`dump_doc_paragraphs` (pre-existing route) confirmed the insert landed at
the expected index.

### 3. `tests/test_governance_export.py` — written, **NOT YET RUN**

New file, untracked. Session was interrupted (tool-use rejected) right
before the first live pytest run — **this is the actual next action**.

Structure:
- Seed-content helpers (`_insert_text`, `_insert_heading`,
  `_insert_bold_label`, `_highlight`, `_insert_page_break`,
  `_create_comment`, `_export`) built on `scn._post_route()` and the three
  new WebApp.js routes above. `_end_index()` uses the existing
  `dump_doc_paragraphs` route to find the current insertion point before
  each `seed_doc_content` call (one round trip per logical insert — simple
  and robust, avoids hand-rolling Docs API batch-relative index math).
- 8 tests, each `ScenarioSession.new_doc()`-isolated (own throwaway journey
  doc, auto-trashed via the existing `gts-hroj` fixture-finalizer pattern):
  1. `test_export_governance_entry_point_basic_shape` — call-site + schema_version/document.id/diagnostics counts + a `policy_numbered` kind_evidence match.
  2. `test_export_governance_parent_unit_id_hierarchy` — procedure (rank 3) nested under policy (rank 2); a following paragraph's `block.unit_id`.
  3. `test_export_governance_page_approximate_transitions_on_explicit_break` — `page_approximate` true→false across an inserted page break; `diagnostics.explicit_page_breaks`.
  4. `test_export_governance_semantic_state_text_pattern_evidence` — `(OLD)` prefix on both a unit heading and a block; `old_paren_prefix` vs `old_dash_prefix` rule names; `historical_blocks` diagnostic.
  5. `test_export_governance_bold_colon_label_style_pattern` — bold `Intent:` prefix → `block.label`/`kind: labeled_paragraph`.
  6. `test_export_governance_color_signals_scoped_per_unit` — highlight in unit A does not leak into unit B's `color_signals`; highlight-color diagnostics warning present.
  7. `test_export_governance_comment_association_exact_match` — real Drive comment with matching `quoted_text` → `association_basis: quoted_text_exact`, `associated_unit_ids`, `section_path`, reverse `block.comment_ids`/`unit.comment_ids`.
  8. `test_export_governance_comment_association_unmatched` — comment whose quote isn't in the doc → first-class `unmatched` terminal state (not an empty/ambiguous array), `diagnostics.unmatched_comments`, warning text.

### Explicitly scoped OUT this session (flagged, not silently dropped)

Recorded in `gts-2glm`'s bd notes (2026-08-13 note already added):

- **`document.suggestion_groups`/`possible_authors` and `autoText` run
  preservation** — cannot be seeded live. The Docs API has no public way to
  create a Suggested-edit or an autoText page-number field via
  `batchUpdate` (both are read-only via the API). Recommended track:
  pure-function tests (Node, no GAS runtime) feeding hand-built
  Docs-API-shaped fixture objects directly into `buildSuggestionGroups_`
  and `mergeAdjacentRuns_`/`makeAutoTextRun_` — mirrors the `vm`-sandbox
  harness gts-ipoy's implementer already used for pre-commit verification.
  **Not started this session.**
- **Table mid-cell unit-switch tagging** (`processTable_`'s
  `ctx.allBlocks` before/after slice) — not covered; would need
  `insertTable` + a second seed pass to find cell-content start indices.
- **Comment-match tiers beyond exact/unmatched** — `quoted_text_prefix`
  (Tier 2), `quoted_text_multiblock` (Tier 3, `findMultiBlockMatch_`), and
  `quoted_text_fuzzy` (Tier 4, `findFuzzyBlockMatch_`) are untested. Each
  needs a deliberately-crafted quote (truncated/cross-paragraph/reflowed)
  to land in that specific tier rather than Tier 1.

## Immediate next action

```bash
mkdir -p /tmp/jobs
/mnt/c/dev/venvs/uv1/bin/python3 -m pytest tests/test_governance_export.py -v > /tmp/jobs/gts2glm-run1.log 2>&1
tail -150 /tmp/jobs/gts2glm-run1.log
```

Then triage failures (first live run of hand-written index-math seed
helpers — expect some off-by-one/index bugs before green), fix, re-run.

## After that (still open for gts-2glm to close)

1. Get all 8 tests green live.
2. Build the Node pure-function track for suggestion_groups/autoText.
3. Decide (with user) whether table-mid-cell + comment-tier-2/3/4 coverage
   is required before `gts-2glm` can close, or tracked as a follow-up bead
   per this project's "open seams register" convention (ADR-0013) — has
   not been discussed yet.
4. `regression=pending` until the full-suite `pytest -x` merge-gate runs
   clean (also still outstanding from the separate `gts-ir1f` thread,
   unrelated to this bead).
5. Once `gts-2glm` is green, `gts-ipoy` itself is still open for its own
   card-action integration + design-gap hardening review — confirm nothing
   else blocks its close.

## Uncommitted files at handoff time

```
 M src/Procedure-Exporter.js        (docId seam)
 M src/WebApp.js                    (3 new test-support routes)
?? tests/test_governance_export.py  (written, not yet run)
```
(Other uncommitted files — `.beads/*`, `.gitignore`, `CLAUDE.md`,
`deployment-ledger/test.jsonl`, `pyproject.toml`, `knowledge-base/adr/002{3,4}-*.md`,
`plan-*.txt`, `test-full-run.txt` — predate this session's exporter work and
were left untouched, as noted in the 2026-08-13 work-log entry.)

## bd state

- `gts-2glm`: `IN_PROGRESS`, note added summarizing the seam + scope gap.
- `gts-ipoy`: unchanged, still `OPEN`, blocked on `gts-2glm`.
