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

## Not yet done (remaining gts-283i.1 AC items)

1. Box/table-cell structural confirmation (Church Policy 05 Policy Statement
   pattern) — needs a capture against a doc containing that pattern; this
   doc's content wasn't inspected for a table match yet.
2. `contentUri` expiry/TTL behavior — needs a second delayed fetch.
3. ADR for the description write-back mechanism decision.
4. `docs/procedure-exporter.md` §19.3 update if the positioned-object finding
   above (or the box/table finding) contradicts current draft assumptions.
