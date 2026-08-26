# ADR-0028: Hyperlinks survive round-trip as a third inline-run attribute

**Status:** Proposed
**Date:** 2026-08-26
**Relates to:** ADR-0022 (inline bold/italic runs own character formatting — this extends its run
model), gts-zocq (the run mechanism), ADR-0024 (`custom_fields` — this fixes its value shape before
it ships), ADR-0027 (paragraph grammar), gts-dr8j / gts-v0py (the author-intent-wins precedent),
docs/CONTEXT.md §Action Format

## Context

A hyperlink typed into action text is destroyed on flush today.

The read path samples exactly two character attributes. `_extractInlineRuns`
(`SyncManager.js:1302`) walks `actionText`, reads `textEl.isBold(off)` and `textEl.isItalic(off)`
at each character's tracked document offset, coalesces equal-styled neighbours into
`{start, end, bold, italic}` runs, and returns `[]` when nothing in range is formatted. `getLinkUrl`
appears nowhere in the read path. The only link write in `SyncManager.js` is line 3281, the chip URL
applied to the token itself.

So the link is never read, never stored, and never reapplied. On the next flush the action text is
rewritten from the stored value and the link is gone.

This is the same defect class this project has repeatedly decided against: gts-dr8j (soft returns
flattened), gts-zocq (inline bold/italic flattened by Config's uniform style), gts-v0py (trailing
text after a status token dropped). Each was resolved on the principle that author-typed intent
beats a mechanical flatten. ADR-0022 states it directly: *"when a mechanical uniform transform
collides with author-typed intent, author intent wins rather than being silently discarded."*

ADR-0024's `custom_fields` has the same exposure and has not shipped yet. If field values are
stored as plain JSON strings, a link in `Notes:` is lost the same way — and fixing it afterwards
means migrating every stored cell.

## Decision

### 1. `link` becomes a third run attribute

The inline-run record grows one field:

```js
{ start, end, bold, italic, link: 'https://…' | null }
```

`link` is `null` for unlinked ranges. The link's **text is the range itself** —
`actionText.slice(start, end)`. No separate link-text field is stored: a parallel copy of text
already present in `actionText` would be two things that can disagree, and the range is the
authoritative answer to "what is linked".

### 2. Every seam extends rather than changes shape

| Seam | Today | Change |
|------|-------|--------|
| Doc read (`_extractInlineRuns`) | `isBold(off)`, `isItalic(off)` | add `getLinkUrl(off)` — the same offset-sampling API shape |
| Run coalescing | neighbours merge when `bold` and `italic` match | `link` joins the equality test |
| Sheet store | `RichTextValue` runs | `RichTextValue` carries `getLinkUrl()` natively — **no new column, no schema change** |
| Sheet read (`_runsFromRichTextRuns`) | reads `TextStyle` bold/italic | add the run's link URL |
| Doc write | per-run `updateTextStyle` | add `link` to the `fields` mask — the request shape already at `SyncManager.js:3281` |

### 3. `hasFormatting` gates on `link` too

`_extractInlineRuns` returns `[]` unless some run is bold or italic. Without adding `link` to that
test, an action whose only formatting is a hyperlink still returns `[]` and the link is lost —
the exact bug this ADR exists to fix, reintroduced one line below the fix.

### 4. Config's uniform style does not assert `link`

ADR-0022 set `_actionTextStyleRequest`'s mask to `underline,foregroundColor,weightedFontFamily
[,fontSize]`. `link` is absent from it and stays absent. Runs own `bold`, `italic` and `link`
exclusively; Config owns font family, size, colour and underline. No ordering guarantee between
the two requests is required, which is the property ADR-0022 chose option (b) to obtain.

### 5. The token and status-image links are out of scope of runs

Runs are extracted from `actionText`, which exists only after the token strip and the assignee
strip. The chip URL on the `ACT-N:`/`AI-N:` text and the status image's link sit outside that
range and are applied by their own requests. A run link therefore cannot overwrite the chip link,
and the flush must not widen a run's range past the action-text boundary.

### 6. `custom_fields` values carry runs from day one

An ADR-0024 field value is not a bare string:

```json
{"Notes": {"text": "see the Q3 deck for context",
           "runs": [{"start": 8, "end": 16, "bold": false, "italic": false,
                     "link": "https://docs.google.com/…"}]}}
```

`runs` is `[]` for an unformatted value, matching the "empty means plain" convention
`_extractInlineRuns` already uses. Since `custom_fields` is unimplemented, this costs a wordier
JSON shape now and avoids migrating stored cells later.

## Consequences

**Positive:**

- Closes a live data-loss path affecting every user who has ever pasted a link into an action.
- No sheet schema change: `RichTextValue` already models per-run link URLs, so the storage
  question that made ADR-0024 need a new column does not arise here.
- Extends an accepted, already-implemented mechanism rather than introducing a parallel one —
  the offsets-tracking machinery gts-zocq built is exactly what a third attribute needs.
- Fixes ADR-0024's value shape while it is still free to fix.

**Negative / tradeoffs:**

- Run fragmentation increases. Every link boundary now splits a run even when bold/italic are
  uniform, so a link-heavy action produces more `updateTextStyle` requests per flush. Bounded by
  the number of distinct linked ranges, which is small in practice, but it is a real cost on the
  6-minute execution budget for a sweep over many documents.
- `link: null` and an absent `link` key must be treated identically on read, or runs written
  before this change compare unequal to runs written after and produce spurious doc-vs-sheet
  diffs.
- Sheets' `RichTextValue` link support is not perfectly symmetric with Docs' — a URL Sheets
  normalizes on write (trailing slash, percent-encoding) round-trips back as a different string
  and reads as a change. The `[TST]` twin must assert round-trip stability on a URL with
  encodable characters, not only on a plain `https://host/path`.
- A link whose range spans a status token or the assignee is not representable, since runs cover
  `actionText` only. Such a link is truncated to the surviving range rather than preserved whole.

**Open question (resolve at Accept):** should an existing action be re-read to recover links that
were already destroyed by a previous flush? It cannot be — the URL is gone from both doc and
sheet. This ADR is forward-only; there is no recovery path, and that should be stated to users
rather than discovered.

## Related

Extends ADR-0022's run model with a third attribute under the same ownership split. Independently
adoptable: the action-text half fixes a defect that exists today regardless of ADR-0024 or
ADR-0027, and the `custom_fields` half (rule 6) applies only when ADR-0024 is implemented.
