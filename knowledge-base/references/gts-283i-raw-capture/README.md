# gts-283i.1 raw capture — Docs.Documents.get() dump

**Source doc:** `1zQkRAczbRjB0iRD2OhpHsqXvHsmskE8VI7VNx8vE5yE`
**Captured:** 2026-08-14, via new testToken-gated WebApp route `dump_raw_docs_api`
(`src/WebApp.js` `_handleDumpRawDocsApi`), unfiltered
`Docs.Documents.get(docId, { suggestionsViewMode: 'SUGGESTIONS_INLINE',
includeTabsContent: true })` — no `fields` mask, so this is the full response
shape.

**File:** `docs-api-get-1zQkRAczbRjB0iRD2OhpHsqXvHsmskE8VI7VNx8vE5yE.json`
(~6.4MB; response envelope is `{ ok, docId, document, serverVersion }`).

## What this doc's capture shows (first-pass read)

- Single tab (`includeTabsContent: true` → `document.tabs[0].documentTab`).
  `inlineObjects`/`positionedObjects`/`lists` all live under `documentTab`,
  not at the top level of `document` (those keys are empty at top level).
- `documentTab.inlineObjects`: 6 entries. Shape confirmed:
  `inlineObjectProperties.embeddedObject.imageProperties.contentUri` +
  `.cropProperties` (often `{}`), plus `size.{height,width}` (magnitude/unit
  PT) and `embeddedObjectBorder`. `description` field present per object
  (currently auto-generated Docs placeholder text like
  `"page1image38953456"`, not human-authored) — this is the field §19.3's
  write-back proposal would target.
- `documentTab.positionedObjects`: 1 entry — a genuine floating/positioned
  image (`positioning.layout: WRAP_TEXT`, `leftOffset`/`topOffset` present).
  **This contradicts a "positioned images don't appear in the real corpus"
  assumption** — §19.3's "out of scope" deferral for positioned objects is
  NOT safe to treat as a non-issue; at least one real document exercises it.
- `contentUri` values are signed `lh7-rt.googleusercontent.com` URLs with a
  `key=` query param — expiry behavior not yet tested (would need a delayed
  re-fetch of the same URI to confirm TTL; not done in this pass).

## Box/table-cell structural confirmation (AC item 2 — resolved)

This same capture also contains the "box" callout pattern (Church Policy 05's
"Policy Statement" box: 6 occurrences at body startIndex 40699, 45042, 48759,
51945, 55387, 58284, all identical shape). Confirmed via direct inspection of
the saved JSON (`/tmp/inspect_policy_statement2.py`-style walk, not a new live
call):

- **The document contains zero `table` structural elements anywhere** — a
  plain scan for `"table"` keys under every tab's `body.content` (recursing
  into any cell content, of which there is none) found 0.
- Each "Policy Statement" box is a run of ordinary consecutive body
  paragraphs (heading paragraph + following body paragraphs) that each
  individually carry `paragraphStyle.shading.backgroundColor` (observed
  `{red:0.8117647, green:0.8862745, blue:0.9529412}`, a light blue) plus
  `paragraphStyle.{borderTop,borderBottom,borderLeft,borderRight}` (1pt solid,
  5pt padding). There is no `tableCellStyle.backgroundColor` anywhere in this
  document — the box is paragraph-level shading, not a table cell.
- **This corrects §19.3's original assumption** ("a box is, structurally, a
  table cell") — see `docs/procedure-exporter.md` §19.3, updated in this
  pass. The practical conclusion ("no separate box-specific handling needed")
  still holds, but because a box paragraph is walked by the same top-level
  `processParagraph_` as any other body paragraph — there is no
  `processTable_` detour to piggyback on, because there is no table.
- No inline image was found inside any of the 6 observed box instances in
  this document (checked the paragraphs immediately surrounding each match
  for `inlineObjectElement`) — the box+image combination remains unconfirmed
  live, though nothing in the structural finding above suggests it would
  behave differently from an image in any other body paragraph.

## Remaining gts-283i.1 AC items (not blocking; not pursued this pass)

- `contentUri` expiry/TTL behavior — would need a second, time-delayed fetch
  of the same signed URL; not exercised in this design-spike pass (out of
  scope for the bare structural-confirmation ACs; flagged for the gts-283i.4
  implementer to hit before assuming "fetch during the same execution" is
  sufficient — see docs/procedure-exporter.md §19.3 "Extraction mechanics").
