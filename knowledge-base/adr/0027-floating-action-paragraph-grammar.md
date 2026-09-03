# ADR-0027: Floating-action item structure — grammar, storage, and flush rendering

**Status:** Proposed
**Date:** 2026-08-26
**Merged:** 2026-08-27 — folds in ADR-0024 (`custom_fields` column, Accepted 2026-08-26, gts-4l1a)
and ADR-0028 (link/run model, Proposed) so a single document defines the full structure of a
floating-action item — parse grammar, sheet storage, and flush rendering — instead of three cross
-referencing ones. Nothing either ADR covers has shipped to a real release. ADR-0024 and ADR-0028
are now pointer stubs; their content lives here (rules 9 and 10–15 respectively). Their acceptance
history (ADR-0024 Accepted 2026-08-26; the "Resolved" notes below) carries forward unchanged
(Stuart Donaldson).
**Restructured:** 2026-08-27 (same day, later pass) — decision-first ordering (rules now precede
the forensic evidence that motivated them), the paragraph-continuation terminal corrected from a
literal `\n` to an explicit soft-return terminal `SR` (the grammar was conflating "end of
paragraph" notation with a same-paragraph Shift+Enter), and "formatting is uniform across the
action body and every field value" surfaced as a stated property instead of arriving unannounced
at rule 10. No rule's substance changed; rule numbers are unchanged. The pipe-separator commit
archaeology moved to Appendix A. (Stuart Donaldson)
**Relates to:** gts-qi1j (the design bead this answers), gts-tis (closed obsolete by this ADR),
ADR-0022 (inline bold/italic runs own character formatting — rules 10–15 extend its run model),
ADR-0023 (token spelling — `ACT-N:` canonical, `AI-N:` read-compatible), gts-zocq (the run
mechanism), gts-jxrw (bare-token truncation), gts-dr8j (soft-return continuation),
gts-v0py/gts-28q/gts-1tbe (status-token position rule), gts-eezz (field-name production),
gts-po8t (flush indentation correction, revisited by rule 8),
ADR-0031 (sync entry points and rendering conformance — owns *when* a flush is triggered; rule 8
owns only what it writes), docs/CONTEXT.md §Action Format

## Context

The floating-action paragraph format has never been written down as a grammar. It exists as
behavior distributed across two parsers in `SyncManager.js` — `_parseParagraphAsFloatingAction`
(single-token fast path, handles PERSON chips) and `_parseSoftReturnParagraphActions`
(soft-return path, text-email only) — plus a shared status extractor,
`_extractStatusTokenTracked`. `docs/CONTEXT.md` §Action Format describes the detection rules in
prose but does not state a grammar precise enough to classify a given paragraph accept/reject
without reading parser source.

One adjacent decision is already on file and is **not reopened here**: **ADR-0023** decided the
token spelling (`ACT-N:` canonical for writes, `AI-N:` read-valid indefinitely, one shared N
namespace, token literal centralized, `globalId` shape unchanged).

Four further questions needed resolving together, because they interact: whether `|` is a field
delimiter (an accidental precedent from a since-deleted parser — rule 2, investigated in
Appendix A); how the trailing `(Status)` token behaves once a paragraph can carry more than one
line (rule 4); where team-defined `Field: value` continuation data lives once synced to the sheet,
given `action_text` is read elsewhere as a plain atomic string (rule 9, options considered in
Appendix B); and how a hyperlink or bold/italic span typed into an action survives a flush, since
the existing read path (`_extractInlineRuns`) only ever sampled bold/italic and a link was silently
destroyed on every round-trip (rules 10–15, background in Appendix C).

## Decision

### 1. The grammar

```
actionParagraph := [inlineImage] token [assignee] actionBody [continuation*]
token           := ("ACT" | "AI") "-" digits ":" [ \t]*
assignee        := personChip | "@"? email [ \t]*
email           := [\w.+-]+ "@" [\w-]+ ("." [a-z]{2,})+
actionBody      := text [ statusToken ]
statusToken     := "(" [^)]* ")"        ; last such group on the HEADER LINE, per rule 4
continuation    := SR ( fieldLine | prose )
fieldLine       := [ \t]* fieldName ":" ( [ \t] inlineValue? | EOL )
fieldName       := fieldWord (" " fieldWord)*   ; ≤32 chars total (gts-eezz)
fieldWord       := [A-Z] [A-Za-z0-9_-]*
SR              := soft return — Shift+Enter, staying inside the same paragraph element;
                    U+000B in tracked document text (`_toSoftReturnText`). Not a paragraph
                    break: a real `\n`/`\r` ends the paragraph and the action with it. The
                    "header line" is everything before the first `SR`.
```

Whitespace between the token, the assignee and the action body is the only separator on the header
line. There is **no field delimiter**. Leading whitespace on a continuation line is not part of the
delimiter grammar either — rule 5 governs it.

**Formatting is a property of the grammar, not of any one part of it.** The action body and every
field's inline value are both text values that may carry bold, italic and link runs, coalesced
into the same `{text, runs}` shape (rules 10–15) — the header line is not a "plain" special case
and a field value is not a "richer" one. This is stated here, ahead of the rules that implement it,
because it governs how rules 5a, 8, 9 and 15 all read.

### 2. `|` carries no meaning

A pipe character anywhere in an action paragraph is literal text. There is no escape mechanism
because none is needed. gts-tis is **superseded**, not ratified, and is closed as obsolete —
Appendix A has the investigation that established the pipe form was accidental residue, not a
requirement.

The header line is deliberately not extensible by adding positional or keyed fields to it. Rule 9's
`Field: value` continuation lines are the sanctioned extension point; a second extension mechanism
on the header line would give two ways to express the same thing and force an escaping rule onto
prose that currently needs none.

### 2a. The header-line field set is unchanged

No field is added to or removed from the parsed action record by this ADR. It remains
`globalId`, `N`, `assigneeEmail`, `assigneeName`, `actionText`, `status`, `hasExplicitStatus`,
`isDuplicate`, `runs`. `src/ContractSchema.js` needs no change on the grammar's account; the
`custom_fields` column (rule 9) is additive schema surface and lands outside the header line.

### 3. The assignee may carry a leading `@` sigil

`@jane@example.com` parses identically to `jane@example.com`. Unlike the pipe, this is a plausible
thing for a person to type — it mirrors the chip-insertion gesture — and admitting it costs one
optional character in the assignee production. The sigil is not stored; `assignee_email` holds the
bare address.

### 4. The status token is scoped to the header line

`_extractStatusTokenTracked` currently scans for the last `(...)` group anywhere in the action
text, which today means anywhere in the paragraph. Once continuation lines (rule 9) exist, that
is wrong in two ways: a status token on the header line stops being the last group in the
paragraph and is silently missed (the action defaults to `Open`), and a field value that happens
to end in parentheses — `Progress: revenue section (blocked)` — is misread as the status.

**Status is extracted from the header line only, before continuation lines are considered.**
Parentheses in field values and in continuation prose are always literal. The position rule within
the header line (gts-28q as refined by gts-v0py and gts-1tbe — the last group qualifies only if
what follows it is empty or begins with a non-word character) is unchanged.

### 5. Field line versus continuation prose

A continuation line is a `fieldLine` if and only if, once leading whitespace is stripped, it
matches the bounded production above: a name of at most 32 characters drawn from
`[A-Za-z0-9 _-]` where **every space-separated word starts with an uppercase letter**, then a
colon followed by a space, a tab, or the end of the line. A bare `Consult With:` with nothing
after the colon is a field line with an empty inline value, not prose. Every other continuation
line is prose.

**Leading whitespace is ignored, not required or forbidden.** The parser strips any run of spaces
or tabs at the start of a continuation line before testing the `fieldLine` shape and before
absorbing a line as prose. This is not a preference — rule 8 renders every continuation line with
a Config-driven indent on flush (`SR Indent`/`Field SR Indent`, default 0 — amended 2026-08-29,
gts-9a4j), and the parser must read its own rendered output back unchanged (idempotent round-trip,
rule 7) regardless of the configured width, as well as a line an author indented by hand for
readability while typing. The stripped whitespace is not part of the stored value in either case: a
field's inline value and every prose line are stored without their leading indent, and rule 8
reapplies the indent uniformly on the next flush.

**Resolved (gts-eezz, 2026-08-26):** the per-word-uppercase constraint narrows the production as
first drafted here (`[A-Za-z] [A-Za-z0-9 _-]{0,31}`, no case requirement). That looser form cannot
actually distinguish a field name from ordinary prose containing a colon: `then he said` (12
chars, all letters/spaces) satisfies it exactly as `Consult With` does, so a sentence like `then
he said: we should ship it` would parse as a field line, which is wrong. The per-word-uppercase
form matches every field-name example on record (`Target`, `Progress`, `Notes`, `Consult With`,
`Due` — all Title Case) and correctly excludes lowercase sentence continuations. The 32-character
length bound is unchanged and still independently enforced.

This answers what were originally three open parser questions from the storage decision (rule 9):

1. *Field-name line versus a continuation line containing a colon* — the bounded production. A
   prose line such as `then he said: we should ship it` fails it (`then`/`he`/`said` do not start
   with uppercase letters), so it stays prose. No per-team allowlist is required.
2. *Field-name line versus the next record's token* — the token production is attempted first and
   wins. A line beginning `ACT-4:` starts a new record even though it would also satisfy
   `fieldLine`.
3. *Continuation prose before any `Field:` line* — absorbed into `actionText`, per rule 5a.

### 5a. Prose attaches to the open block; soft-return order is retained

A paragraph is an ordered sequence of **blocks**. The action body opens the first block; each
`fieldLine` closes the block before it and opens a new one named by its field. **A prose
continuation line belongs to whichever block is open when it is read** — `actionText` if no field
line has been seen yet, otherwise the value of the most recent field line. Prose does not jump
back to `actionText` once a field has been opened.

A block's value is an ordered list of lines, joined with `\n` (this is the parsed JS string's own
line separator — the internal representation a stored value uses once extracted, distinct from the
grammar's `SR` terminal above, which is a document-level character, not a stored one):

- the action body's first line is the header line's text (chip/email and status token stripped);
- a field's first line is its inline value — the text after the colon, or the empty string when
  the field line is bare;
- each subsequent prose line is appended in document order.

Line order within a block, and field order across blocks, are both document order and are
preserved end to end: parse, `custom_fields` JSON (object keys in insertion order), sheet cell,
and re-render on flush. The joined string is the value's `text` under rule 15. A soft return in
the document is a `\n` in the stored value and a soft return again on flush — never a space, never
a reordering, never a dropped line. Stored line text never carries the leading indent rule 8 adds
on flush — see rule 5.

Worked example:

```
ACT-9: jane@example.com Draft the Q3 budget memo (In Progress)<SR>
- pull last year's actuals<SR>
- circulate before Friday<SR>
Consult With:<SR>
- Stuart<SR>
- John<SR>
Due: Tuesday
```

```
actionText    = "Draft the Q3 budget memo\n- pull last year's actuals\n- circulate before Friday"
custom_fields = {"Consult With": {"text": "\n- Stuart\n- John", "runs": []},
                 "Due":          {"text": "Tuesday",             "runs": []}}
```

(field values carry `{text, runs}` per rule 15; the joined line text is the `text`, and run
offsets are indices into it, so a `\n` is an ordinary character as far as runs are concerned)

`- Stuart` and `- John` are the `Consult With` value, not action prose and not their own fields —
so a later tabular view of these records puts both names in the `Consult With` column. The leading
`\n` in that value is the bare field line's empty inline value, and is what lets flush re-render
`Consult With:` on its own line exactly as the author typed it.

**Repeated field name.** A field name that appears twice does not overwrite: the later block's
lines are appended to the existing value, in document order, separated by `\n`. Nothing an author
typed is dropped (the gts-dr8j / gts-zocq precedent), at the cost of the two occurrences reading
as one value on flush.

**Round-trip.** Flush renders block *n* as a bold `Name:` label, a tab, then the value's first
line, followed by one indented soft return per remaining line, in order — see rule 8 for the
exact rendering. Parsing that output strips the label's bold run, the tab, and each line's leading
indent before re-deriving the same blocks (rule 5), so the rendering is exact for input already in
this shape and idempotent thereafter.

### 6. A paragraph that starts with a token but fails to parse is reported, not skipped

Today `_parseParagraphAsFloatingAction` returns `null` when its token regex does not match, and
the paragraph is dropped without a signal. That is how the input behind gts-tis disappeared
silently rather than being surfaced.

A paragraph whose text begins with `(ACT|AI)-\d+` but does not complete the grammar is recorded by
VerifySync as `unparseable-action-paragraph`, carrying the paragraph's body-child index and its
leading text. It is not synced and it is not silently discarded.

### 7. Nothing valid today becomes invalid

The grammar above is a strict superset of what the current parsers accept: it adds the optional
`@` sigil and the continuation-line productions, and it narrows nothing. No document requires
migration, and rule 6 introduces reporting only for input that is already being lost.

Rule 4 is the sole change to behavior observable today; rules 5/5a specify behavior that only
exists once continuation field lines do, which they do not yet. Today's rule — prose is absorbed
into `actionText` (gts-dr8j) — is rule 5a's first-block case, unchanged.

### 8. Continuation-line rendering: indent and field-label emphasis

Every continuation line — the value's first line and every subsequent line, whether the block is
`actionText` or a field — is rendered on flush with a leading-space indent at the start of the
line. **Amended 2026-08-29 (gts-9a4j):** the indent width is **Config-driven, not a fixed 5** —
the Config sheet's `SR Indent` key sets it for `actionText` continuation lines and `Field SR
Indent` independently sets it for field continuation lines, each defaulting to **0** (flush-left)
when the Config sheet has no row for that key. gts-po8t's 2026-08-27 flush-left correction was
this default's zero-value case all along, not a separate decision contradicting this rule — the
live flush had simply never read either key before gts-9a4j added the accessor
(`_getContinuationIndentConfig`, `src/SyncManager.js`). This is presentational only: it exists so
a continuation reads visually as subordinate to the header line when a positive value is
configured, and it is stripped back off by the parser (rule 5) rather than stored as part of the
value's text, regardless of which width was in effect when it was written.

A field's `Name:` label is additionally rendered **bold**, and is followed by a **tab character**
rather than a plain space before the value's first line. The label's bold run and the tab are
system-applied formatting, not author-typed intent: they are produced fresh on every flush from
the field name string and are never read back as part of `actionText`'s or a field value's `runs`
(rule 15) — a link or bold/italic run inside the value's own text is unaffected and continues to
round-trip under rules 10–15. The action body's first line (the header line) is not a field and
gets no label; only `SR Indent` applies to it and to `actionText` prose continuation lines.

Worked example, rendering the paragraph from the rule 5a example on flush with `SR Indent`=5 and
`Field SR Indent`=5 configured (`␣` marks a literal space, **bold** marks the field-label run, `→`
marks the tab — with both keys absent/0, every `␣␣␣␣␣` below is simply empty):

```
ACT-9: jane@example.com Draft the Q3 budget memo (In Progress)
␣␣␣␣␣- pull last year's actuals
␣␣␣␣␣- circulate before Friday
␣␣␣␣␣**Consult With:**→
␣␣␣␣␣- Stuart
␣␣␣␣␣- John
␣␣␣␣␣**Due:**→Tuesday
```

The bare `Consult With:` line still renders its label, tab, and indent even though its inline
value is empty — the next line (`- Stuart`) carries the indent as an ordinary continuation of that
same block, not as the label's inline value.

**Amended 2026-08-31 — superseded same day; see ADR-0031.** An earlier revision of this rule
carried a four-part design (`(a)`–`(d)`) for making indent participate in `syncDocument()`'s
ordinary diff, scoped to *every* non-force caller including `syncAll` and therefore the unattended
30-minute trigger. **That scope was not adopted.** It has been replaced in full by
**ADR-0031: Sync entry points and what each one promises**, which decides that rendering
conformance — indent *and* the `ai_token`/`action_text` character styles, which have exactly the
same gap — belongs to **user-initiated single-document syncs only**, never to a background sweep.

Two corrections that revision contained are worth recording, since both are easy to re-derive
wrongly:

- It claimed a **carve-out from the "formatting-only changes never mark Dirty / never force a
  tracker re-render" invariant** (`ContractSchema.js:193-203`). There is no carve-out, because
  there is no conflict: that note governs whether inline **`runs` participate in row identity**
  (the document→sheet direction — a user bolding a word must not orphan their row). Rendering
  conformance compares the document against **Config** and never touches `_rowIdentityKey`,
  `sheetWins`, orphan detection, or `_trackerRowsMatch`. The two are different axes. No amendment
  to that invariant is required, and none was made.
- It described the comparison as *"structurally different from the existing doc-vs-sheet diff."*
  The precedent already exists four lines away in the same loop: the **missing-explicit-status
  materialize** pass (`SyncManager.js:311-318`) flushes an action whose content already matches the
  sheet, purely because its *rendered* form lacks a status token. That is a
  document-vs-expected-rendering predicate, and rendering conformance is the same shape with a
  different condition.

**Rule 8 states rendering only** — what a flush *writes*. When a flush is triggered, and by which
entry point, is ADR-0031's subject, not this rule's. The split is deliberate: mixing "what the
output looks like" with "when we produce it" inside a grammar document is what made the policy
hard to find in the first place.

### 9. `custom_fields`: a new, additive sheet column

Team-defined fields land in a new `sheetAction` column, `custom_fields`, holding a single
JSON-encoded object keyed by field name, each value shaped `{text, runs}` per rule 15
(`{"Target": {"text": "September meeting", "runs": []}}`) — not a bare string, so links and
bold/italic typed into a field value round-trip the same way they do in `action_text`. The
existing canonical columns (`assignee_email`/`assignee_name`, `action_text`, `status`,
`modified_date`, etc.) are unchanged in meaning and continue to hold only what they hold today —
the header line's owner, description, and status, and sheet-tracked timestamps. `action_text`
never carries JSON. (Appendix B has the storage options considered.)

The column is additive and optional, following the precedent set by the `runs` field
(`gts-zocq`, `SyncManager.js:157-162`): a row with no custom fields either omits the column value
or stores `{}`/empty, and every code path that predates this ADR keeps working unchanged.

**No per-team allowlist.** Rule 5's bounded `fieldLine` production (leading letter, ≤32 chars from
`[A-Za-z0-9 _-]`, every word Title Case, then `: `) is used instead of a per-team enforced list —
any team-typed field name matching that shape is accepted verbatim.

**Examples.** `<SR>` denotes a soft return (Shift+Enter) inside a single paragraph — the
continuation-line boundary rules 5/8/9 all key off. All three paragraphs below are otherwise
identical (same token, assignee, status).

*Without fields — header line only, no continuation:*
```
ACT-3: jane@example.com Draft the Q3 budget memo (In Progress)
```
`custom_fields` is omitted (or stored as `{}`); `action_text` is `Draft the Q3 budget memo`.

*Soft return, no fields — continuation is prose, not a field:*
```
ACT-4: jane@example.com Draft the Q3 budget memo (In Progress)<SR>
Still waiting on finance numbers before this can close.
```
The continuation line doesn't match the `fieldLine` production (rule 5 — no field-name shape), so
it's absorbed as prose into `action_text` rather than parsed as a field: `action_text` becomes
`Draft the Q3 budget memo\nStill waiting on finance numbers before this can close.`
`custom_fields` is still omitted/`{}` — this column only ever holds recognized `Field: value`
lines, never absorbed continuation prose.

*Soft return with fields:*
```
ACT-5: jane@example.com Draft the Q3 budget memo (In Progress)<SR>
Target: September board meeting<SR>
Progress: revenue section drafted, expenses pending
```
Each continuation line matches the `fieldLine` production. `action_text` remains
`Draft the Q3 budget memo` (unchanged by the fields); `custom_fields` becomes:
```json
{"Target": {"text": "September board meeting", "runs": []},
 "Progress": {"text": "revenue section drafted, expenses pending", "runs": []}}
```
(`runs: []` here — neither value has a link or bold/italic span; see rule 15 for a formatted
example and rule 8 for how `Target:`/`Progress:` are rendered — bold label, a tab, then the value
— on flush.)

### 10. `link` becomes a third inline-run attribute

The inline-run record grows one field:

```js
{ start, end, bold, italic, link: 'https://…' | null }
```

`link` is `null` for unlinked ranges. The link's **text is the range itself** —
`actionText.slice(start, end)`. No separate link-text field is stored: a parallel copy of text
already present in `actionText` would be two things that can disagree, and the range is the
authoritative answer to "what is linked". (Appendix C has the defect this closes.)

### 11. Every seam extends rather than changes shape

| Seam | Today | Change |
|------|-------|--------|
| Doc read (`_extractInlineRuns`) | `isBold(off)`, `isItalic(off)` | add `getLinkUrl(off)` — the same offset-sampling API shape |
| Run coalescing | neighbours merge when `bold` and `italic` match | `link` joins the equality test |
| Sheet store | `RichTextValue` runs | `RichTextValue` carries `getLinkUrl()` natively — **no new column, no schema change** |
| Sheet read (`_runsFromRichTextRuns`) | reads `TextStyle` bold/italic | add the run's link URL |
| Doc write | per-run `updateTextStyle` | add `link` to the `fields` mask — the request shape the token's own chip-link request already uses |

### 12. `hasFormatting` gates on `link` too

`_extractInlineRuns` returns `[]` unless some run is bold or italic. Without adding `link` to that
test, an action whose only formatting is a hyperlink still returns `[]` and the link is lost —
the exact bug rules 10–15 exist to fix, reintroduced one line below the fix.

### 13. Config's uniform style does not assert `link`

ADR-0022 set `_actionTextStyleRequest`'s mask to `underline,foregroundColor,weightedFontFamily
[,fontSize]`. `link` is absent from it and stays absent. Runs own `bold`, `italic` and `link`
exclusively; Config owns font family, size, colour and underline. No ordering guarantee between
the two requests is required, which is the property ADR-0022 chose option (b) to obtain.

### 14. The token and status-image links are out of scope of runs

Runs are extracted from `actionText`, which exists only after the token strip and the assignee
strip. The chip URL on the `ACT-N:`/`AI-N:` text and the status image's link sit outside that
range and are applied by their own requests. A run link therefore cannot overwrite the chip link,
and the flush must not widen a run's range past the action-text boundary.

### 15. `custom_fields` values carry `{text, runs}` from day one

A `custom_fields` field value (rule 9) is not a bare string:

```json
{"Notes": {"text": "see the Q3 deck for context",
           "runs": [{"start": 8, "end": 16, "bold": false, "italic": false,
                     "link": "https://docs.google.com/…"}]}}
```

`runs` is `[]` for an unformatted value, matching the "empty means plain" convention
`_extractInlineRuns` already uses. Since `custom_fields` is unimplemented, this costs a wordier
JSON shape now and avoids migrating stored cells later.

A field value's `runs` cover only the value's own text — the range `Progress: revenue section
(blocked)`'s bold/italic/link runs would sample within `"revenue section (blocked)"`, offset from
the field's inline value, never from the `Name:` label. The label's bold emphasis and the tab that
follows it (rule 8) are system-applied on every flush and are never sampled into `runs` —
conflating the two would make a value compare unequal to itself across flushes with no author edit
involved.

### 16. Reference example — a generated, canonical source (gts-colw)

The examples elsewhere in this ADR (rules 5a, 8, 9, 15) illustrate one rule each, by hand-typed
prose, and are free to drift from actual behavior. Instead they are backed by a single worked
example that cannot silently drift: a permanent canonical Google Doc
(`1PYIU022o5dWNhIkyErjUzF6TRg--r4QrH-h-JbPNO-E`, also recorded as `referenceDocId` in
`local.settings.json`) built from a checked-in, git-diffable text serialization —
`tests/fixtures/action-reference.apt.txt`, in **Action Portable Text (APT)**, spec'd at
`docs/interfaces/action-portable-text.md`. APT preserves whitespace exactly and spells a soft
return `<SR>`, distinct from a real paragraph break — the same notation this ADR's own worked
examples already use. `src/PortableText.js` provides `encodeDocToApt` (Doc → APT, used to
regenerate the checked-in file after the canonical Doc is hand-edited) and `decodeAptIntoDoc`
(APT → Doc, used both to seed a test doc and to regenerate the canonical Doc if it is ever lost);
`encode(decode(x)) == x` is verified for every construct the reference doc uses.

`tests/test_adr0027_reference_document.py` seeds itself by decoding the checked-in APT file into a
fresh doc once per test session and asserts against the resulting sheet rows — it is the closing
artifact for five open `[TST]` beads' doc-content-representable cases (gts-ucdz, gts-thwh,
gts-tz5x, gts-82s2, gts-nrxn); each bead's behavioral-only cases (idempotency, entry-point audits,
live create-flow) remain that bead's own scope.

Delivered by **gts-colw** (`[INF]`, format spec + encode/decode functions + canonical doc location
+ the consolidated test file).

## Consequences

**Positive:**

- The grammar is stated precisely enough to classify a paragraph accept/reject without reading
  parser source, which is gts-qi1j's acceptance criterion.
- Declining the delimiter removes an escaping problem rather than solving one; prose pipes and
  parenthesized field values stay literal with no user-visible rule to learn.
- Rule 4 catches a real defect in rule 9's implementation path before it ships, at the cost of
  one scoping change in a function that already exists.
- Rule 6 converts a silent data-loss path into a reported one, consistent with this project's
  repeated precedent (gts-dr8j, gts-zocq, gts-v0py) that author-typed intent is never discarded
  quietly.
- Rule 8's bold-label-plus-tab rendering makes a flushed action visually self-documenting —
  which line is a field, and what it's named, is legible at a glance without opening the sheet.
- Stripping leading whitespace before the `fieldLine` test (rule 5) makes parsing agnostic to
  exactly how a continuation line's indent got there — rule 8's flush, an author's own typed
  indent, or a paste from elsewhere — with one rule instead of three.
- `action_text`'s existing role as a comparable atomic value for row-identity/diff logic is
  preserved — no risk of spurious sync noise from JSON key-order or formatting differences.
  Every consumer that reads `action_text` expecting a plain description (sorting, chip preview,
  compact card labels) needs no change. `custom_fields` is additive/optional, matching an
  established pattern in this schema; low blast radius for callers that don't touch it.
- Closes a live data-loss path affecting every user who has ever pasted a link into an action, and
  fixes `custom_fields`' value shape (rule 15) while it is still free to fix, before it ships.
- No sheet schema change for links: `RichTextValue` already models per-run link URLs, so the
  storage question that motivated rule 9's new column does not arise for rules 10–15.
- Rules 10–15 extend an accepted, already-implemented mechanism (gts-zocq's offsets-tracking) 
  rather than introducing a parallel one.
- One document instead of three: a reader learns the full shape of a floating-action item — parse
  grammar, storage, and rendering — without following cross-references across separate ADRs, and
  the decision-first ordering means the rules that govern implementation come before the forensic
  evidence that motivated them.

**Negative / tradeoffs:**

- The 32-character field-name bound in rule 5 is a judgment call, not a derived constant. A team
  wanting a longer field name gets prose instead, with no diagnostic. Rule 6's reporting does not
  cover this case because the paragraph itself parses fine. Under rule 5a that misclassified line
  is now absorbed into the preceding field's value rather than into `actionText`, which is a
  quieter failure than it was — the text survives, but under a neighbouring label.
- Rule 5a makes a `custom_fields` value's `text` (rule 15) multi-line, where the original examples
  showed only single-line ones. The column's shape is otherwise unchanged (JSON object keyed by
  field name); a value's `text` can now contain embedded newlines, which is opaque to
  Sheets-native filtering — accepted for this admin-only sheet.
- Appending on a repeated field name is the lossless choice, not the intuitive one: an author who
  retypes `Due:` to correct it gets both values concatenated rather than the later one winning.
  Making the correction case work would require discarding author-typed text, which this project
  does not do silently.
- The 5-space indent and the bold-label-plus-tab shape (rule 8) are judgment calls, like the
  32-character bound, not derived constants — a future design pass could revisit either without
  touching the parsing grammar, since rule 5 only requires *some* leading whitespace to exist, not
  a specific width.
- Rule 8's label bold run must not be confused with a value's own `runs` (rule 15): the flush
  path has to apply and then discard the label's formatting on a range that is deliberately
  outside `actionText`/field-value offsets, or a naive implementation will leak it into the stored
  `runs` array and produce spurious doc-vs-sheet diffs on every field.
- The header line cannot grow new fields without a further ADR. This is intended, but it means a
  future due-date or priority field must arrive as a continuation field rather than as a
  first-class column, or reopen this decision. (A brace-prefixed structured-object escape hatch
  for the action body was raised as an alternative during review and intentionally deferred — see
  the design bead this ADR's "Related" section points to.)
- Rule 4 requires the two parsers to agree on where the header line ends. They already diverge on
  assignee handling (`_parseParagraphAsFloatingAction` reads PERSON chips;
  `_parseSoftReturnParagraphActions` is text-email only), so the header-line split must be factored
  into one shared helper or the status rule will drift between the two paths — the same class of
  drift `_extractStatusTokenTracked` was extracted to prevent (gts-v0py).
- A new column (`custom_fields`) is schema surface that has to be carried through the sheet-write
  path (`TeamActionWrite.js`), the Web App contract (`ContractSchema.js` messages), and any place
  that enumerates `sheetAction.fields`/`headers`/`columnsByField` in lockstep — three parallel
  arrays today (`ContractSchema.js:60-88`), each needing the new entry kept in sync.
- Run fragmentation increases (rules 10–15). Every link boundary now splits a run even when
  bold/italic are uniform, so a link-heavy action produces more `updateTextStyle` requests per
  flush. Bounded by the number of distinct linked ranges, which is small in practice, but it is a
  real cost on the 6-minute execution budget for a sweep over many documents.
- `link: null` and an absent `link` key must be treated identically on read, or runs written
  before rule 10 compare unequal to runs written after and produce spurious doc-vs-sheet diffs.
- Sheets' `RichTextValue` link support is not perfectly symmetric with Docs' — a URL Sheets
  normalizes on write (trailing slash, percent-encoding) round-trips back as a different string
  and reads as a change. The `[TST]` twin must assert round-trip stability on a URL with
  encodable characters, not only on a plain `https://host/path`.
- A link whose range spans a status token or the assignee is not representable, since runs cover
  `actionText` only. Such a link is truncated to the surviving range rather than preserved whole.

**Resolved (2026-08-26, gts-4l1a):**
- The shared header-line helper (rule 4's status-scoping) folds into this ADR's `[IMP]` twin —
  both parsers must agree on where the header line ends for rule 4 to hold at all. Full
  PERSON-chip/text-email parity in the soft-return path is tracked separately as its own bead, not
  folded into this ADR's implementation.
- Should an existing action be re-read to recover links that were already destroyed by a previous
  flush? It cannot be — the URL is gone from both doc and sheet. Rules 10–15 are forward-only;
  there is no recovery path, and that should be stated to users rather than discovered.

## Appendix A: the pipe separator was residue, not a requirement

gts-qi1j was scoped on the premise that gts-tis ("accept `AI-2 | @stu@asyn.com | action`")
established `|` as a field delimiter as a side effect of a bug fix, and that the broader format
question therefore needed deciding before that accident hardened.

The premise does not hold. The pipe form was introduced on 2026-05-21 in commit `7d9c162`, whose
own message describes the parser it served: *"Remove trailing `\s*` from BARE_EMAIL_RE and
DISPLAY_NAME_RE so rest starts with ' | ' and field parser can extract action text."* That parser
— `FloatingActionParser.js`, together with `DocumentNormalizer.js`, `SheetReconciler.js`,
`SyncOrchestrator.js`, `DocumentDiscovery.js` and `test_floating_action_parser.py` — was deleted
the following day by `fd3249b` (GTaskSheet-ii7, 1,877 lines removed), which stubbed
`floating_actions()` "for future checkbox+person-chip parser". The current parser was written
against the chip/email-at-start model instead.

`grep -rn "AI-[0-9#]* *|" src/ tests/` returns zero hits. The pipe form survives in no fixture, no
test and no source file. What survived is gts-tis and one sentence in `docs/OPERATIONS.md`
recording two xfails that vanished with the deleted test file. Confirmed with the product owner
2026-08-26: **no live document uses the pipe form.** This is the evidence behind rule 2.

## Appendix B: `custom_fields` storage options considered

A markup-spec review proposed letting an action record carry team-defined `FieldName: value`
lines in the document (soft-return-separated, following the header line) — e.g. `Target:`,
`Progress:` — so teams can attach whatever contextual fields matter to them without a schema
change per team. The document remains the source of truth: a user types plain `Field: value`
lines directly in the paragraph, same as they type the header line today.

`sheetAction` (`ContractSchema.js:60-74`) is a fixed, positional column list —
`assignee_email`, `action_text`, `status`, `modified_date`, etc. — with no slot for arbitrary
key/value data. Two storage options were considered for where the parsed fields land once synced
to the sheet:

- Overload `action_text` with a JSON representation of the whole record (description + fields).
- Add a new column holding only the flexible fields, JSON-encoded, alongside the unchanged
  canonical columns (**chosen** — rule 9).

`action_text` is read as a plain atomic string by existing comparison logic — row-identity/diff
checks (`TrackerTable.js`'s row-match logic, `VerifySync.js:88`) and display surfaces
(`WorkspaceAddonCard.js`, chip preview text) all assume it is a short human description, not a
serialized object. The sheet itself is admin-only, not a user-facing surface, but `action_text`
also round-trips into the document paragraph on flush — though on that path the value is always
re-parsed/re-rendered into `Field: value` lines rather than copied verbatim, so document
readability does not by itself decide between the two options. The overload option was raised
again during the 2026-08-27 restructuring pass, reframed as an opt-in escape hatch (the action
body beginning `{` parses as a structured object, folding field data into `action_text` only when
an author or a machine writer chooses that syntax) — deferred rather than adopted: it still
requires every `action_text` consumer above to special-case "plain string or object" rather than
eliminating a case, it does not by itself remove the need for sheet-side field storage unless the
sheet also stops needing to query fields, and hand-typed JSON is a materially worse failure mode
than the bounded `fieldLine` grammar (rule 5) for the same audience ADR-0024 designed for. Tracked
separately for further exploration rather than folded into this ADR's decision.

## Appendix C: hyperlinks were destroyed on flush

The read path samples exactly two character attributes. `_extractInlineRuns`
(`SyncManager.js:1302`) walks `actionText`, reads `textEl.isBold(off)` and `textEl.isItalic(off)`
at each character's tracked document offset, coalesces equal-styled neighbours into
`{start, end, bold, italic}` runs, and returns `[]` when nothing in range is formatted. `getLinkUrl`
appears nowhere in the read path. The only link write in `SyncManager.js` is the chip URL applied
to the token itself.

So the link is never read, never stored, and never reapplied. On the next flush the action text is
rewritten from the stored value and the link is gone.

This is the same defect class this project has repeatedly decided against: gts-dr8j (soft returns
flattened), gts-zocq (inline bold/italic flattened by Config's uniform style), gts-v0py (trailing
text after a status token dropped). Each was resolved on the principle that author-typed intent
beats a mechanical flatten. ADR-0022 states it directly: *"when a mechanical uniform transform
collides with author-typed intent, author intent wins rather than being silently discarded."*
`custom_fields` (rule 9) has the same exposure and had not shipped yet at decision time — if field
values were stored as plain strings, a link in `Notes:` would be lost the same way, and fixing it
afterwards would mean migrating every stored cell. Rules 10–15 resolve this for both `actionText`
and `custom_fields` together, before either ships.

## Related

Depends on ADR-0023 for the token production. Extends ADR-0022's run model with a third attribute
(`link`) under the same ownership split. Formerly split across ADR-0024 (`custom_fields` schema)
and ADR-0028 (link/run model), both now superseded by and folded into this ADR. The brace-prefixed
structured-action-body idea raised during the 2026-08-27 restructuring (Appendix B) is tracked as
a separate design exploration, not part of this ADR's decision.
