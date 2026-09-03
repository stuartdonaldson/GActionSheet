# Fixture corpus (stage `docx-harness`, `gts-28hx`)

Checked-in `.docx` files so stages `docx-structure`/`docx-comments`/`docx-revisions`/`docx-images`
(3-6) and `gts-0rho` (stage `docx-verify`) are testable offline, with no live Google auth. Generated
by `build_fixtures.py` (stdlib-only: `zipfile` + hand-built OOXML strings) — not via `python-docx`,
for the same reason ADR-0026 Decision 3 rules it out for the pipeline itself: no support for
`w:commentRangeStart`/`End` or `w:ins`/`w:del` authorship.

Regenerate with:

```
python document_export/fixtures/build_fixtures.py
```

## `golden.docx`

| Feature | What it exercises | Where |
|---|---|---|
| TOC | A `w:fldSimple` TOC field with cached result text, and a bookmarked `Heading1`. Simplified relative to Word's native complex-field (nested-hyperlink) TOC — sufficient for structure/traversal, not for round-tripping a live edit. | Paragraphs 1-3 |
| Tracked changes — proposed insertion | `w:ins` wrapping a run | "The system shall **[ins]always** process requests" paragraph |
| Tracked changes — suggested deletion | `w:del` wrapping a run (`w:delText`) | same paragraph, trailing clause |
| Tracked changes — inserted-then-deleted | `w:del` nested inside `w:ins` (contract §3.2) | "Draft note removed before acceptance." paragraph |
| Comments — range + reply + resolution | `w:commentRangeStart`/`End`/`commentReference` around one sentence; `word/comments.xml` carries the original + a reply; `word/commentsExtended.xml` threads the reply (`w15:paraIdParent`) and marks it resolved (`w15:done="1"`), the original unresolved (`w15:done="0"`) | "2. Review Comments" section |
| Numbered list | `numPr`/`numId` against `word/numbering.xml`'s single decimal abstract numbering | "3. Numbered Steps" section, 3 items |
| Table + mid-cell unit switch | A 2x2 table whose second data cell contains a `Heading3` paragraph followed by body text — a new unit opening partway through a cell, the invariant carried forward from `gts-qjkj` | "4. Reference Table" section |
| Image (inline) | One inline `w:drawing` / `wp:inline` referencing `word/media/image1.png` (a hand-encoded 1x1 red PNG) via `a:blip/@r:embed`, with `wp:docPr/@title` and `@descr` set | "5. Figure" section |
| Image (anchored) | One positioned/floating `w:drawing` / `wp:anchor` referencing `word/media/image2.png` (a hand-encoded 1x1 blue PNG), own `wp:docPr` and `a:blip/@r:embed` — `gts-8uo6` AC #1's "inline AND positioned/anchored" case | "5. Figure" section, second paragraph |

## `golden-no-images.docx`

Identical to `golden.docx` with the image paragraph, media part, and its relationship omitted
entirely. Exists for `gts-0rho` AC #6(d): asserts `document.images` is **omitted from the artifact
entirely** (key absent, not `[]`) for a document with no images — that negative case cannot run
against `golden.docx`, which always has one.

## Deliberately not included

- **A drawing with no resolvable `word/media/` part** (unresolved `a:blip/@r:embed`, or a target
  missing from the zip) — `gts-8uo6`'s fail-closed/skip-with-warning path is covered by a synthetic
  fixture instead (`TestImageExtraction`), same tier as the comment/structure synthetic-only cases
  above.
- **Multi-tab content** — contract §1.1: there is no OOXML analogue of a Google Docs tab, and
  `gts-11rq` (deferred) is what would establish converter behavior for one. Not fabricable in a
  hand-built fixture without evidence of what the real converter does.
- **`no_range`/`range_unterminated` comment states** (contract §2.3) — both are fail-closed, expected
  to be rare, and not deliberately authored into the golden path. Add a dedicated malformed-comment
  fixture if `gts-nxx3` (stage `docx-comments`) needs to assert them directly.
