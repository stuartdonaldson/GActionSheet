# Design & Code Review — GActionSheet

**Date:** 2026-05-29
**Scope:** `docs/DESIGN.md` and all `src/*.js` (15 files), plus `src/appsscript.json` / `.clasp.json` for cross-checks.
**Branch / build:** `poc/editor-addon-action-chip`, `v0.1.0 (Rev. May 28, 2026 23:56) (DEV)`.
**Method:** Manual full read of DESIGN.md and every source file, **cross-referenced against** the
other `docs/` files (CONTEXT.md, OPERATIONS.md, `poc-editor-addon-migration.md`, lessons-learned),
the `knowledge-base/adr/` records, `knowledge-base/references/`, `work-log.md`, and the 21 `bd`
memories. The supporting material substantially changes the *framing* of the top findings (see
§Supporting context) — most are not accidental drift but documented decisions that were never
reconciled across ADRs, DESIGN, and code.

## Summary

The code is internally consistent, well-logged, and defensively written. The dominant problem is a
**three-way divergence between the ADRs, DESIGN.md, and the code** that is not recorded anywhere as
a deliberate change:

- DESIGN and **ADR-0005** describe action identity as a Docs REST **named range** (`namedRangeId`)
  and a **two-project** architecture ("share no code"). The code uses an **`AI-N:` text-token**
  identity in a **single** project whose add-on and automation halves call each other directly.
- The text-token model is a *real, documented engineering decision* (smart-chip pills and rich
  links don't appear in `getText()`, so a text-based scanner was required — `work-log.md`
  2026-05-28 §Decisions/Research). But it was never promoted to an ADR or into DESIGN, and it is
  precisely the "hidden text tag" approach that ADR-0005 and the `google-tasks-api-ruled-out`
  memory had *deprioritized* in favour of named ranges. The carrier field is still named
  `namedRangeId` everywhere — a fossil of the abandoned design.
- The ADR set itself was contradictory: **ADR-001** (single-script dual-deployment, Accepted
  2026-05-22) and **ADR-0005** (two-project sidecar, Accepted 2026-05-23) described incompatible
  architectures, with a numbering collision (`001` vs `0001`) and no superseding record. The code
  follows ADR-001; DESIGN's diagram follows ADR-0005. **(✓ Reconciled 2026-05-29 — see H4: the ADRs
  now match the code via ADR-0007/0008/0009. The remaining DESIGN.md edits are pending.)**

Beyond the divergence there are genuine correctness gaps (assignee email never updated on the
upsert path; conflict resolution that ignores the timestamp it loads; the stated idempotence
invariant violated; optimistic-concurrency protection removed with no replacement) and some
maintainability debt (orphaned HtmlService sidebar from an abandoned pivot; a chip-style block
duplicated in three files; `globalId` parsing duplicated in five).

Findings are ordered highest-priority first. The **Source** column cites the project record that
corroborates or explains each item, in addition to the code evidence in the Finding/Recommendation.

## Findings

| # | Priority | Area | Finding | Code evidence | Source / provenance | Recommendation |
|---|----------|------|---------|---------------|---------------------|----------------|
| C1 | **Critical** — ✓ **RESOLVED 2026-05-29** (DESIGN + code rename) | Identity model | DESIGN's named-range identity is abandoned in code: identity is an `AI-N:` text token, `globalId = {docId}/AI-{N}`; no `addNamedRange` exists for actions (only the tracker heading). The carrier field is still *named* `namedRangeId` across 5 files. | `SyncManager.js:1-10,330-456`; `WebApp.js:230` | DESIGN faithfully reflects **ADR-0005 §Consequences** ("Identity is `namedRangeId`"). Code diverged *deliberately*: `insertRichLink`/smart-chip pills are absent from `getText()`, so a text scanner was required (`work-log.md` 2026-05-28). The token is the "hidden text tag" that `google-tasks-api-ruled-out` memory deprioritized. | Write a **superseding ADR** for the text-token identity (cite the `getText()` constraint), then rewrite DESIGN §Solution Strategy / §Identity / §Data Model / §Building Block View. Rename `namedRangeId`→`globalId`. The most accurate as-built description today is `poc-editor-addon-migration.md` §paragraph-form — use it as the source. |
| H1 | **High** — ✓ RESOLVED (DESIGN + bd memory) | Detection rule | DESIGN says actions are detected by a leading PERSON chip or email. Code requires a leading `AI-N:` token; chip/email is optional and parsed *after* it. | `SyncManager.js:347-381` | `bd` memory `action-identification-strategy` ("checklist item with a person chip, **not** AI-delimited") also contradicts the code — the memory is stale too. | Update DESIGN §Action Scanner and the `bd` memory to the token-led rule (`bd remember --key action-identification-strategy …`). |
| H2 | **High** — ✓ RESOLVED (DESIGN) | Write suppression | WriteGuard cross-execution layer is **disabled** in code; `wrapPersistent` is a plain alias of `wrap` and `SYNC_IN_PROGRESS_UNTIL_MS` is never written. DESIGN §Programmatic Write Suppression and the Scenario A/B mermaid notes still describe it active with a 20 s window. | `WriteGuard.js:1-73`; DESIGN.md:274-280,431,464 | Timeline: the cross-execution layer was added to fix "Dirty re-set after sync" (`work-log.md` 2026-05-28 23:30 §Open Issues), then **disabled 2026-05-29** after testing showed doPost writes don't fire the installable `onEdit` trigger (WriteGuard.js header). DESIGN never updated. | Update DESIGN to the in-process-only model; record the empirical basis and residual risk as an accepted POC tradeoff. |
| H3 | **High** — ✓ RESOLVED (DESIGN diagram) | Architecture | DESIGN §Runtime Architecture (two subgraphs) and §Dependency Rules ("no cross-project calls", "share no code") describe two projects. Code is one project where `onActionSheetEdit`→`syncDocument`→`insertTrackerTable` call each other. | `.clasp.json`, `appsscript.json`; `SyncManager.js:229-314` | The diagram is traceable to **ADR-0005** ("Deploy two GAS projects … share no code"). Single-project reality is confirmed by **ADR-001**, and memories `editor-addon-coexistence` ("co-exist in the same appsscript.json") and `gcp-project-topology` ("A=POC uses single project"). | Collapse to a single-project diagram in DESIGN — but do it as part of resolving H4 (the ADR conflict), not as a standalone edit. |
| H4 | **High** — ✓ **RESOLVED 2026-05-29** | ADR integrity | The ADR set was self-contradictory and is the governance root cause of C1 and H3. **ADR-001** (3-digit, single-script dual-deployment, Accepted 05-22) and **ADR-0005** (4-digit, two-project sidecar + named-range identity, Accepted 05-23) decided incompatible architectures; both were "Accepted" with no supersede link. There was also a filename/numbering collision: `001-…` vs `0001-…`. | n/a (docs) | `knowledge-base/adr/0001-…`, `0005-…`, `0007-…`, `0008-…`, `0009-…` | **Done (code-first reconciliation).** Renamed `001-…`→`0007-…` (collision fixed). Marked **ADR-0005 → Superseded by ADR-0008** and **ADR-0002 → Superseded by ADR-0009** (status-line + note only; bodies preserved per immutability). New **ADR-0008** records the in-text `AI-N:` token identity + single-project model + in-process-only guard; new **ADR-0009** records Dirty-flag conflict resolution. ADRs now match the code; C1/H1/H2/H3/M9 DESIGN edits can follow. |
| M1 | Medium — ✓ **RESOLVED 2026-05-29** | Bug | `_handleUpsertActionRows` update branch updates cols 2,4,5,6,9 but **never col 3 (Assignee Email)**; the insert branch does. An email change via the upsert path (chip create / async drain) never reaches an existing row. | `WebApp.js:162-169` | The update path has been patched column-by-column — `work-log.md` 2026-05-28 23:30 added "col 2 (ID) refresh … ID was never written on updates". Col 3 is the next unpatched gap in the same pattern. Related documented gap: "Assignee Name not written back on sheetWins path" (same work-log §Open Issues). | ✓ Col 3 added; entire update branch now guarded by a `changed` flag (M2 fix bundled); idempotent write added. [TST] GTaskSheet-45k tracks Python test coverage. |
| M2 | Medium — ✓ **RESOLVED 2026-05-29** | Invariant | §Idempotence ("a Sync that finds no differences makes no writes") is violated: upsert update branch stamps `col9 = now` unconditionally; sync doc-wins branch always rewrites the col 7 formula and clears col 10 every run. | `WebApp.js:168,345-347` | DESIGN.md:402-403 | ✓ Upsert update: all writes guarded by `changed` flag (col9 only stamps on real change). Doc-wins: col7 formula compared before write; col10 only cleared when `syncStatus !== ''`. [TST] GTaskSheet-ckj tracks Python test coverage. |
| M3 | Medium — ✓ **RESOLVED 2026-05-29** | Bug / UX | Doc-wins path never writes a missing `(Open)` token back to the doc (only sheetWins/new/duplicate globalIds are flushed), yet VerifySync flags "missing explicit status token" as an issue → a permanent verification failure with no auto-fix. DESIGN claims Sync rewrites the token. | `SyncManager.js:87-147`; `VerifySync.js:251-256`; DESIGN.md:272 | — | ✓ Added fourth flush loop in `syncDocument`: iterates `canonicalByGlobalId`, adds any action where `!hasExplicitStatus` to `toFlush`. Next sync materializes `(Open)`. [TST] GTaskSheet-dm7 tracks Python test coverage. |
| M4 | Medium — ✓ **RESOLVED 2026-05-29** | Robustness | Inconsistent doc-matching: `_loadRowsForDocUrl` matches by `docUrl` substring; orphan detection matches by `docId` substring. docUrl substring is fragile (prefix collisions, format differences). | `WebApp.js:418` vs `:358` | `work-log.md` 2026-05-28 23:30 already fixed a related URL-format bug (`open?id=` vs `/d/`) in `syncAll`/`_syncSheetRowToDoc` — the same format fragility applies here. | ✓ Added `_extractDocIdFromString(s)` helper; `_loadRowsForDocUrl` now extracts docId from both the input URL and each formula and compares extracted docIds. [TST] GTaskSheet-wpe1 tracks Python test coverage. |
| M5 | Medium — ✓ **RESOLVED 2026-05-29** (set 4) | Performance | A single sheet edit does redundant work: `_syncSheetRowToDoc` flushes, then calls `syncDocument` (re-open + rescan + sheet sync + tracker refresh), then calls `insertTrackerTable` again — tracker rebuilt up to twice per edit. | `SyncManager.js:284-305` | — | ✓ Removed trailing `insertTrackerTable` call; `syncDocument` already refreshes the tracker via its own `insertTrackerTable(docId, { onlyIfExists: true })` call at line 174. |
| M6 | Medium — ✓ **RESOLVED 2026-05-29** (Opus) | DRY / styling | The chip-badge style block (~10 lines) is duplicated verbatim in three files; the "GET body → locate tracker table" loop is duplicated within TrackerTable. The badge colours are also **inverted** vs the documented intent. | `SyncManager.js:689-698`, `EditorChipPoc.js:787-798`, `TrackerTable.js:486-494,367-378/437-447` | `work-log.md` 2026-05-28 documents the badge as "Comic Sans MS bold, **white text, dark purple (#4C1D95) background**"; code applies dark-purple as *foreground* on a *white* background — inverted. | ✓ **Field semantics confirmed:** in `updateTextStyle`, `foregroundColor` = glyph colour, `backgroundColor` = highlight. The work-log *prose* was the inaccurate record; the code's purple foreground is correct. **Resolution (user, 2026-05-29):** badge = bold Comic Sans, purple text (#4C1D95), **no background** — so the white `backgroundColor` was dropped (not flipped) at all 3 sites. Extracted `_chipBadgeStyleRequest(start,end)` → SyncManager.js (1 def, 3 call sites). Extracted `_findTrackerTable(content)` → TrackerTable.js returns `{table,startIndex}` (1 def, 2 call sites). Done atomically with M7. |
| M7 | **High** — ✓ **RESOLVED 2026-05-29** (Opus, merge-blocker) | Process | **Promotion is decided** (team, 2026-05-29) — the POC is becoming the product and is being cleaned up before merge. The `EditorChipPoc.js` header is now actively wrong: "No existing src/ file is modified … Remove this file before merging to master." Its isolation contract is already void (the core `_poc_*` functions live in `SyncManager.js` as the production sync mechanism), and the "remove before merge" instruction directly contradicts the promotion. | `EditorChipPoc.js:1-20`; `SyncManager.js:614` (`_poc_flushActionParagraph`) | `poc-editor-addon-migration.md` §POC Findings ("confirmed"); promotion confirmed by user 2026-05-29. | ✓ **File layout (user decision):** split by Google add-on type — `EditorChipPoc.js`→`EditorAddon.js` (Docs editor add-on, ②), `Addon.js`→`WorkspaceAddon.js` (Workspace add-on, ①); no CommonAddon.js yet (only `_buildCardAction` qualifies, currently Workspace-only — YAGNI). Isolation banner replaced with production header. All 15 surviving `_poc_*` functions de-namespaced (`_poc_X`→`_X`), incl. `setFunctionName`/trigger-handler string refs; `_POC_*` constants, `poc_*` form fields, and the `POC_QUEUE`→`ACTION_SHEET_QUEUE` property key. `_buildSidebarAction`→`_buildCardAction`. **Dead code deleted:** `_poc_lookupAction` + `_poc_lookupActionFromDoc` (defined, never called). DESIGN §Module Map + diagrams updated. **Scope boundary:** `GasLogger` log-tag string literals (`POC_*`, `poc.*`) left unchanged — observability surface in work-log history, no test depends on them; trivial follow-up if desired. `node --check` passes on all 4 touched files; full call graph verified intact. |
| M8 | Medium — ✓ **RESOLVED 2026-05-29** (set 4) | Security | Test routes (`run_fixture`, `set_test_token`) ship in the production webapp (`access: ANYONE_ANONYMOUS`); `_handleRunFixture` treated an **empty** `TEST_TOKEN_EXPIRES` as "no expiry enforced". | `WebApp.js:52`; `TestWebApp.js:53-58` | OPERATIONS.md / deploy pipeline registers the token each `deploy:test`. | ✓ Empty `expiresAt` now fails (returns `test-token-expired`) — `deploy:test` always writes a future timestamp so the pipeline is unaffected. Comment updated. |
| M9 | Medium — ✓ RESOLVED (ADR-0009 + DESIGN) | Conflict model | Conflict resolution is **Dirty-flag-based, not timestamp-based**. `_handleSyncActionRows` loads `dateModified` but resolves purely on `syncStatus === 'Dirty'` (sheet wins) vs else (doc wins); the loaded timestamp is never compared. **ADR-0002** (Accepted) and DESIGN Scenario C / §Building Block View both state `Last Modified` determines the winner, with tie-break rules (timestamp-vs-none, tracker-row-wins) that are entirely unimplemented. | `WebApp.js:217,314-348`; DESIGN.md:168,501 | **ADR-0002** "Timestamp-Based Conflict Resolution" | Either implement timestamp comparison per ADR-0002, or supersede ADR-0002 and rewrite DESIGN to describe the Dirty-flag model the code actually uses. Pick one and make all three agree. |
| M10 | Medium — **Deferred to Opus** | Concurrency | `_poc_flushActionParagraph` does an unguarded GET→batchUpdate. Optimistic concurrency (`requiredRevisionId`) was **removed** because the API rejects it (HTTP 400). The async tracker rewrite and the flush can interleave and shift character offsets between GET and batchUpdate — the exact "silent document corruption" the removed guard targeted — with no replacement strategy. | `SyncManager.js:625-705` | `work-log.md` 2026-05-28 21:45 & 23:30 (removed `requiredRevisionId`; "Key Learning: revision conflict detection must use a different strategy if needed") | **For Opus:** Evaluate two mitigation paths: (A) per-doc `LockService.getDocumentLock()` wrapping the entire GET→batchUpdate block in `_poc_flushActionParagraph` — prevents interleave between the flush and the async tracker rewrite that also batchUpdates the same doc; (B) re-fetch the paragraph's start index immediately before building the batchUpdate requests (re-validate offsets after GET rather than using the cached offsets). Path A is simpler but LockService has a 10s acquisition window which may cause `onActionSheetEdit` to time out under concurrent edits. Path B is safer but requires restructuring `_poc_flushActionParagraph` to separate the index-location step from the mutation step. The current risk at POC scale is low (single-user doc, low concurrency) — may be acceptable to document and defer. |
| L1 | Low — ✓ **RESOLVED 2026-05-29** (set 4) | DRY | `globalId` parsing (`split('/AI-')`) is duplicated across 5 files. | `SyncManager.js:278`, `WebApp.js:231`, `Addon.js:510`, `EditorChipPoc.js:607`, `TrackerTable.js:149` | — | ✓ Added `parseGlobalId(globalId) → {docId, N, actionId}` to `WebApp.js`; `_extractActionId` now delegates to it. All 8 inline `split('/AI-')` call sites replaced across SyncManager, Addon, EditorChipPoc, TrackerTable. |
| L2 | Low — ✓ **RESOLVED 2026-05-29** (set 4) | Stale comment | `SheetSetup.js:5` says "8-column header row"; `SHEET_HEADERS` has 10. `ArchiveManager` cites superseded "requirements §13/§16". | `SheetSetup.js:5,12-23`; `ArchiveManager.js:8-15` | The original requirements are archived/superseded (`knowledge-base/references/requirements-original-2026.md`). | ✓ SheetSetup comment updated to "10-column"; ArchiveManager superseded-requirements references replaced with `DESIGN.md §Archive Manager` anchor. |
| L3 | Low — ✓ **RESOLVED 2026-05-29** (set 4) | Dead code | Every proxy call sends `Authorization: Bearer <oauthToken>`, but `doPost` authenticates on the shared `secret` only and never reads the header. | `SyncManager.js:511`, `WebApp.js:56-59` | **ADR-001 §Tradeoffs** ("Bearer tokens not propagated by Apps Script runtime") explains *why* the header is useless. | ✓ Removed the `Authorization: Bearer` header from the two WebApp proxy calls (`_syncActionRows`, `_markDocNotFound`). The Docs REST API calls in `_poc_flushActionParagraph` and `_poc_insertActionChip` that call `docs.googleapis.com` directly retain their Bearer headers — those are legitimate. |
| L4 | Low — ✓ RESOLVED (set 2) | Doc placement | DESIGN §"Proposed Tracker Sheet Resolution Architecture" (~115 lines, second-person) is an unimplemented proposal embedded mid-document. | DESIGN.md:284-400 | It *is* live forward intent: `chip-url-must-encode-sheet-id-for-multi-tenant` memory + `poc-editor-addon-migration.md` describe the multi-tenant chip URL `gactionsheet.app/action/{sheetId}/{namedRangeId}` (current chip URL is single-tenant `northlakeuu.org/…`). | ✓ Moved to `knowledge-base/ROADMAP.md`; one-line pointer left in DESIGN (set 2). |
| L5 | Low — ✓ RESOLVED (set 2) | Doc gap | Script properties `ACTION_SHEET_ID` and `DOC_FOLDER_ID` are read by code but absent from DESIGN §Script Properties. | `TrackerTable.js:92`, `SheetSetup.js:81-92`; DESIGN.md:76-83 | — | ✓ Added both rows to DESIGN §Script Properties table (set 2). |
| L6 | Low — ✓ **RESOLVED 2026-05-29** (set 4) | Edge case | `_poc_insertActionChip` computes the cursor offset by matching a sibling text run via `.getText()` equality; two runs with identical text resolve the wrong offset. | `EditorChipPoc.js:711-722` | — | ✓ Replaced text-equality loop with `cursorPara.getChildIndex(cursorElement)` — iterates only up to the target child index, eliminating the false-match risk entirely. |
| L7 | Low — ✓ **RESOLVED 2026-05-29** (set 4) | Dead code | `onOpenSidebar()` and `src/Sidebar.html` use the **HtmlService** sidebar; `onOpenSidebar` is not wired in `appsscript.json` (homepageTrigger is `buildHomepageCard`). The HtmlService sidebar was abandoned. | `Addon.js:90-120`; `src/Sidebar.html` | `html-sidebar-card-pivot` memory (2026-05-27): "Abandoned … deliver the sidebar functionality using the card architecture directly (CardService), not HtmlService." | ✓ Deleted `onOpenSidebar()` from Addon.js and removed `src/Sidebar.html`. Note: `_buildSidebarAction` is retained — it builds CardService actions for card buttons and is actively used; M7 should rename it to `_buildCardAction` as part of the de-namespace pass. |

## Supporting context from project records

The records explain *why* the code looks the way it does and reframe the top findings from "drift"
to "undocumented decisions." These notes belong in the eventual ADR/DESIGN reconciliation.

- **Identity-model history (C1, H1, H4).** ADR-0001 (container-bound on the Sheet) → superseded by
  ADR-0005 (two-project sidecar, named-range identity). ADR-0005 explicitly *rejected* "named
  ranges via DocumentApp" in favour of "named ranges via REST," and the `google-tasks-api-ruled-out`
  memory records named ranges as "preferred over hidden text tags." The POC then discovered that
  smart-chip pills / `insertRichLink` elements do **not** appear in `para.getText()`
  (`work-log.md` 2026-05-28 §Decisions/Research), forcing a text-based `^AI-(\d+):` scanner — i.e.
  the team adopted the very hidden-text-tag approach the ADR had set aside. This is a legitimate
  reversal that simply never got an ADR. `poc-editor-addon-migration.md` documents the resulting
  paragraph form and is the most accurate as-built description available.

- **Architecture (H3, H4).** ADR-001 (single-script dual-deployment) and ADR-0005 (two projects)
  are both "Accepted" and incompatible. Memories `editor-addon-coexistence` and
  `gcp-project-topology` ("A=POC uses single project") confirm the single-project reality the code
  implements. DESIGN's two-subgraph diagram is an honest rendering of ADR-0005 — fixing it requires
  fixing the ADR first.

- **WriteGuard timeline (H2).** "Dirty re-set after sync" was an open issue on 2026-05-28; a
  cross-execution property guard was added, then disabled on 2026-05-29 once testing showed doPost
  writes never trigger the installable `onEdit`. The disable is well-commented in code but DESIGN
  still documents the guard as active.

- **Conflict resolution (M9).** ADR-0002 mandates timestamp precedence with specific tie-breaks.
  The implemented model is a one-bit Dirty flag set by `onActionSheetEdit`. These are different
  systems; the timestamp the code loads is dead weight under the current logic.

- **POC promotion status (M7) — DECIDED.** The team confirmed (2026-05-29) the POC will be
  **promoted**, and this review is part of the pre-merge cleanup. The `poc-editor-addon-migration.md`
  plan originally said "keep the existing sync flow unchanged, put experimental code behind a
  separate namespace, remove before merge"; that removal clause is now obsolete because the
  `_poc_*` functions already became the production path in `SyncManager.js`. Consequence for this
  review: the divergence findings (C1, H1, H2, H3, H4, M9) are no longer "future doc hygiene" — they
  are the documentation half of promoting the code and should land **before** the merge so the
  merged `master` ships with ADRs and DESIGN that match the code.

- **Entry-point coverage (context for M5/M3).** The `stub-functions-mask-dead-end-tests` lesson
  (`syncAll()` shipped as a stub wired to a live menu + trigger) is why CLAUDE.md now requires every
  state-modifying entry point to be exercised end-to-end. `syncAll()` is now implemented; the M-tier
  sync-path findings should each gain a `[TST]` that exercises the *entry point*, not just the
  mechanism, per that invariant.

## Strengths

- **Consistent error/logging discipline** — every entry point wraps work in `try/finally` with
  `GasLogger.flush()`; structured, greppable log tags (the work-log shows these were repeatedly the
  thing that made live debugging tractable).
- **Idempotent trigger installation** — `initializeTriggers` deletes matching triggers before
  recreating.
- **WriteGuard pattern** — a clean abstraction; the disable decision is documented with a re-enable
  recipe and the empirical basis.
- **Hard-won runtime knowledge is captured** — `bd` memories and the work-log record real GAS
  gotchas (insertPerson email-only, linkPreview pathPrefix slashes, `getText()` vs rich links,
  trigger fire-delay, `requiredRevisionId` unsupported) that would otherwise be re-learned painfully.
- **Thorough JSDoc** and a readable `doPost` dispatch table.

## Suggested remediation order

> **Promotion is confirmed; this is pre-merge cleanup.** Steps 1–3 plus M7 are **merge-blockers** —
> they are what makes the merged `master` an honest representation of the promoted product (code,
> ADRs, and DESIGN agreeing). Steps 4–5 can be fast-followed but M8 must precede any public exposure.

1. ~~**Reconcile the ADRs first (H4).**~~ ✓ **Done 2026-05-29** (code-first): collision fixed
   (`001-…`→`0007-…`); ADR-0005 superseded by **ADR-0008** (in-text token identity + single
   project + in-process guard); ADR-0002 superseded by **ADR-0009** (Dirty-flag conflict
   resolution). The ADRs now match the code; this unblocks the C1, H1, H2, H3, M9 DESIGN edits.
   (Pre-existing, out of scope: ADR-0003 still reads `Proposed` though ADR-0006 retired its model.)
2. ~~**One DESIGN.md pass**~~ ✓ **Done 2026-05-29** (code-first): rewrote §Solution Strategy /
   §Identity / §Data Model / §Building Block View to the `AI-N:` token model (C1), the scanner
   detection rule (H1), and in-process-only WriteGuard (H2); **replaced the two-project runtime
   diagram with an Execution-contexts diagram + a Data-flow diagram** (H3) and added a **Conflict
   Resolution flowchart** (M9, Dirty-flag); corrected the Scenario A/B/C notes; expanded the Module
   Map and Script Properties (L5); relocated the tracker-resolution proposal to
   `knowledge-base/ROADMAP.md` (L4); switched the sidebar description to CardService (L7, doc side);
   removed the non-existent `LAST_RECONCILED_AT` claim; and updated the `action-identification-strategy`
   `bd` memory. **Remaining doc nit:** the `Action`/`ActionSheetRow` erDiagram fields are still named
   `namedRangeId` (alias note added) — renamed to `globalId` in code and DESIGN erDiagram 2026-05-29 (set 3). ActionSheet column heading still reads `NamedRangeId` as a legacy label.
3. ~~**Correctness fixes**~~ ✓ **Done 2026-05-29** (set 3): C1 rename (`namedRangeId`→`globalId`
   in all 6 product files + TestFixtures.js + DESIGN erDiagram); M1 (col 3 + changed-guard);
   M2 (idempotence: upsert changed-flag, doc-wins formula/col10 guards); M3 (flush loop for
   `!hasExplicitStatus`); M4 (`_extractDocIdFromString` helper + docId-based matching).
   Twin `[TST]` tickets created: GTaskSheet-45k (M1), GTaskSheet-ckj (M2), GTaskSheet-dm7 (M3),
   GTaskSheet-wpe1 (M4). TestFixtures.js `_TF_RESULT` now returns `globalId` field — Python
   test assertions referencing `namedRangeId` in fixture results need updating per those tickets.
4. ~~**Risk/maintainability**~~ ✓ **Partially done 2026-05-29** (set 4): M5 (trailing
   `insertTrackerTable` removed); L1 (`parseGlobalId` utility + all 8 call sites); L2 (stale
   column count + superseded-requirement refs); L3 (dead Bearer headers removed from proxy calls);
   L6 (cursor offset uses `getChildIndex`); L7 (`onOpenSidebar` + `Sidebar.html` deleted); M8
   (empty `TEST_TOKEN_EXPIRES` now fails).
   **Remaining (deferred to Opus):** M10 (concurrency — LockService vs re-fetch analysis); M6
   (chip-badge DRY + colour inversion — best done atomically with M7).
5. ~~**Pre-merge (Opus session)**: M7 + M6~~ ✓ **Done 2026-05-29** (Opus, one pass): M7
   (de-namespace `_poc_*`; files split by add-on type → `EditorAddon.js` / `WorkspaceAddon.js`;
   `_buildSidebarAction`→`_buildCardAction`; dead lookups deleted; DESIGN §Module Map + diagrams
   updated) + M6 (`_chipBadgeStyleRequest` + `_findTrackerTable` helpers; badge background dropped
   per confirmed field semantics + user intent). `node --check` clean; call graph verified. M8 is
   closed. **Remaining deferred:** M10 (concurrency — LockService vs re-fetch analysis) is the only
   open Opus item.
