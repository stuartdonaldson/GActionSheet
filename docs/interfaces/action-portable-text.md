# Action Portable Text (APT) — format spec

**Status:** v2 (gts-83s5 added list-item and table-cell containers; v1 drafted for gts-colw,
ADR-0027 rule 16).
**Purpose:** a round-trippable, git-diffable text serialization of a Google Doc's body
paragraphs, so a human-authored canonical reference Doc can be checked into git as plain text
and regenerated if lost. Not a general Docs serialization — scoped to what ADR-0027's grammar
cares about (floating-action paragraphs and the plain prose paragraphs that appear alongside
them, now also inside a bulleted list item or a table cell — see "List items and table cells
(v2)" below). Headings, images other than the flush-inserted status icon, and other Docs
structure remain out of scope.

Encode/decode functions: `src/PortableText.js` (`encodeDocToApt`, `decodeAptToRequests`).

## Why not plain Markdown

Two of ADR-0027's own grammar distinctions have no Markdown equivalent:

- A **soft return** (Shift+Enter, ADR-0027's `SR` terminal) stays inside the same paragraph — it
  is not the same thing as a **hard paragraph break** (Enter). Markdown has exactly one line-break
  concept and collapses the distinction.
- Markdown renderers collapse runs of whitespace. ADR-0027's grammar cares about leading
  whitespace on a continuation line (rule 5) and about literal characters inside action text (rule
  2 — no field delimiter, parens and pipes are literal). APT is never fed through a Markdown
  renderer — it is only ever read back by its own decoder — so nothing is collapsed; every space
  and tab in a line's text round-trips exactly.

APT reuses two notations ADR-0027's own prose already established (`<SR>`, `**bold**`) rather than
inventing new ones.

## File structure

```
<!-- kind: golden -->
<!-- name: action-reference -->
<!-- doc: 1PYIU022o5dWNhIkyErjUzF6TRg--r4QrH-h-JbPNO-E -->
<!-- serves: gts-colw, gts-ucdz, gts-thwh, gts-tz5x, gts-82s2, gts-nrxn -->
<!-- generated: 2026-08-27T21:51:31.347Z -->

record 1 (one or more physical lines)

record 2 (one or more physical lines)

...
```

- Everything before the first blank line is a **preamble** — comment lines only, never
  interpreted by decode. Optional; decode does not require it.
- Records are separated by exactly one blank physical line. A record is one Doc body paragraph.
- **A record's own content never contains a genuinely blank physical line** — see `<BLANK>` below.
  This is what makes blank-line-separated records unambiguous to split on.

### Structured preamble (gts-x9un)

One `<!-- key: value -->` comment line per field, parsed (but never required) by the tooling in
`scripts/apt_lib.py`:

| Field | Meaning |
|-------|---------|
| `kind` | `golden` (a reviewed, checked-in corpus) or `capture` (a raw encode of a live Doc). Only `bless` (`scripts/apt.py`, stage `apt-cli`) may promote a `capture` to a `golden` — a lint asserts no `kind: capture` file ever lands under `tests/fixtures/`. |
| `name` | the corpus's name, e.g. `action-reference`. |
| `doc` | source Doc ID. Optional (decision 7) — a scenario corpus checked into `tests/fixtures/` typically carries none, since it materialises into a fresh `ScenarioSession.new_doc()` rather than naming a shared mutable Doc. |
| `serves` | comma-separated bead IDs this corpus's records exercise (decision 9's per-record prose annotations name the *specific* case within the corpus; `serves` names the corpus's beads as a whole). |
| `generated` | ISO-8601 timestamp, written by `encodeDocToApt`. |

`encodeDocToApt(doc, opts)` writes `kind: capture` by default (a raw encode of a live Doc is a
capture by definition) plus `doc` and `generated`; `opts.kind`/`opts.name`/`opts.serves` let a
caller (eventually `apt.py pull`/`bless`) override. Unrecognised or legacy free-text preamble
lines are ignored, not errors.

## One record = one paragraph

A record is one or more physical lines. Each physical line but the last ends with the literal
token `<SR>` immediately before the line break — that break is a soft return (Shift+Enter) in the
document, not a new paragraph. The record's last physical line has no `<SR>` suffix; the paragraph
ends there (a real Enter), which is exactly what the following blank line in the file represents.

```
ACT-9: jane@example.com Draft the Q3 budget memo (In Progress)<SR>
- pull last year's actuals<SR>
- circulate before Friday<SR>
Consult With:<SR>
- Stuart<SR>
- John<SR>
Due: Tuesday
```
is one record (one paragraph, six soft returns, seven physical lines) — the same paragraph
ADR-0027 rule 5a's worked example already shows in this exact notation.

### Empty paragraph

A paragraph with no text at all is encoded as a record containing the single token `<EMPTY>`.

### Blank line inside a paragraph

A genuinely empty physical line inside a multi-line paragraph (an author-typed blank continuation
line — legal under the grammar, if unusual) is encoded as the literal token `<BLANK>` alone on
that line (still `<SR>`-suffixed unless it is the record's last line).

## Inline formatting

- **Bold:** `**text**`
- **Italic:** `_text_`
- **Bold + italic together:** `**_text_**`
- **Link:** `[text](url)` — `text` is exactly the linked range (ADR-0027 rule 10: the link's text
  *is* the range, no separate link-text field). May nest bold/italic markers inside:
  `[**text**](url)`.

Coalescing follows ADR-0027 rule 11/`_extractInlineRuns`: adjacent characters with the same
bold/italic/link all merge into one marked span; unformatted text carries no markup at all.

**v1 limitation:** a link range that is bold/italic over its ENTIRE width round-trips
(`[**text**](url)`, matching how a sync's own chip-badge link+bold on a token comes out).
Bold/italic covering only PART of a link's width is not representable — decode has no way to tell
"this link happens to start with two literal asterisk characters" from "this link's first word is
meant to be bold," so it is left as opaque literal text (a documented gap; no case in ADR-0027 or
the current `[TST]` beads needs partial-width nesting).

## PERSON chip assignee

A PERSON chip (only ever legal immediately after the token, per the `assignee` production) is
encoded inline, in place, as:

```
{{chip:jane@example.com}}
```

No display name is encoded — a chip's display name is resolved from the account by Docs itself,
not an independently stored fact.

## Status icon

The small inline status image Sync inserts at the start of a flushed action paragraph is **not**
encoded. It is system-derived from the status token, exactly like a live flush (ADR-0027 rule 8's
principle: system-applied presentation is never part of stored author intent). Decode reconstructs
it from the status token the same way `_buildFlushRequests` does.

## Escaping

A literal occurrence, in real paragraph text, of any character APT's own syntax uses —
`\ * _ [ ] < > { }` — is backslash-escaped on encode (`\*`, `\_`, `\[`, `\]`, `\<`, `\>`, `\{`,
`\}`, `\\`) and unescaped on decode. Parentheses and `|` are never escaped — ADR-0027 rule 2
already makes them literal-only in the grammar, and they carry no meaning in APT either, so a
status token `(In Progress)` or a literal pipe in action text round-trips unescaped, matching how
it looks in the document.

This escaping is total (every syntax character has an escape, applied unconditionally to literal
occurrences), which is what makes `encode(decode(x)) == x` a property of the format rather than
something asserted case by case.

**v1 limitation:** a link URL containing a literal, unescaped `)` cannot be represented — the
`[text](url)` closing parenthesis is found by scanning for the first unescaped `)`, the same wart
standard Markdown link syntax has. None of ADR-0027's or the current `[TST]` beads' URLs need one;
flagged here rather than silently mis-parsed if it ever comes up.

## List items and table cells (v2, gts-83s5)

A **list item** (a bulleted paragraph, `DocumentApp.ElementType.LIST_ITEM`) is encoded exactly
like an ordinary paragraph, except its first physical line is prefixed with the marker `<LI> `:

```
<LI> ACT-60: jane@example.com body-level list item action (Open)
```

Decode strips the marker and, after inserting the paragraph's text like any other, issues a
`createParagraphBullets` request over it (`BULLET_DISC_CIRCLE_SQUARE`). **v2 limitation:**
nesting level is not encoded — every list item round-trips as a flat, single-level bullet. No
current case (including a list item inside a table cell) needs multi-level nesting.

A **table** is encoded as a flat run of structural-marker records around ordinary paragraph
records, so "one record = one paragraph" still holds for every record that carries actual
content:

```
<TABLE rows=2 cols=2>

<CELL 0,0>

ACT-61: jane@example.com table cell plain action (Open)

<CELL 0,1>

<EMPTY>

<CELL 1,0>

<EMPTY>

<CELL 1,1>

<LI> ACT-62: jane@example.com table cell list item action (Open)

</TABLE>
```

`<TABLE rows=R cols=C>` opens, one `<CELL r,c>` marker precedes each cell's own records (in
row-major order — every cell must appear, even an empty one, as `<EMPTY>`), and `</TABLE>`
closes. A cell's content is ordinary paragraph/list-item records — the same escaping, inline
formatting and `<LI>` marker apply inside a cell as at body level. No nested tables (a cell
containing a table is not representable — the "not a general Docs serialization" non-goal still
holds).

**v2 restriction — table position:** a body-level table must be the LAST top-level content in
the doc (aside from one further restriction below). Building a table needs a second Docs REST
round trip after the flat paragraph text is already in place (`insertTable`'s cell indices are
read back via `documents.get`, not computed — a Table's internal index footprint is not reliably
predictable from row/column counts alone), so decode always appends table content after every
top-level paragraph record; a corpus with paragraph content authored AFTER a table would not
round-trip and is rejected. Every real use case (including `test_floating_action_scanner.py`'s
AC-3 through AC-6) already appends its table last.

**v2 restriction — trailing `<EMPTY>`:** Google Docs itself never allows a table to be the body's
final element — it silently appends an empty paragraph after one that would otherwise be last. A
golden corpus whose table is the doc's last content must therefore end with one explicit
`<EMPTY>` record after `</TABLE>`, documenting that unavoidable outcome; decode recognises and
skips exactly this one trailing record (Docs creates it as a side effect of `insertTable`, so
decode does nothing further for it) and rejects anything else appearing after a table.

Tracker-table exclusion (the scanner ignoring `AI:`/`ACT:` tokens inside the Action Item Tracker
table, `test_floating_action_scanner.py` AC-6) is scanner behaviour, not an APT concern — APT
v2 encodes any table generically; which tables the scanner chooses to scan is orthogonal.

## Round-trip contract

`encode(decode(x)) == x` for every construct in this spec. `decodeAptIntoDoc` itself is
append-only against an **empty** doc body — it does not delete/patch existing content, unlike
`_buildFlushRequests`' in-place occurrence tracking — so regenerating an already-populated doc
(the canonical Doc after a hand edit or a live sync) is a **clear-then-decode**, not decode alone;
the `decode_reference_document` test-support fixture (`src/TestFixtures.js`) clears the target
doc's body before decoding for exactly this reason. Content is built via raw Docs REST API
`batchUpdate` requests (`insertText`/`insertPerson`/`updateTextStyle`), not `DocumentApp`'s
high-level per-paragraph API — `DocumentApp#appendText` was found empirically to silently mangle a
literal soft-return character, and `DocumentApp` has no API to insert a PERSON chip at all.

## Canonical reference doc

- Drive doc ID: `1PYIU022o5dWNhIkyErjUzF6TRg--r4QrH-h-JbPNO-E` (also recorded as
  `referenceDocId` in `local.settings.json`, and in the checked-in file's own preamble comment).
- Checked-in portable text: `tests/fixtures/action-reference.apt.txt` — regenerate with the
  `encode_reference_document` test-support fixture (see `tests/test_adr0027_reference_document.py`)
  after editing the Doc by hand; regenerate the Doc from the file with `decode_reference_document`
  if it is ever lost.
- Covers every case in ADR-0027's `[TST]` beads (gts-ucdz, gts-thwh, gts-tz5x, gts-82s2, gts-nrxn)
  that is expressible as document content — see that test file's per-bead sections for the mapping.
- **Kept, deliberately, past the split corpora below** (gts-ndb8, stage `apt-scenarios`) —
  `act-retire`/gts-45fg decided its fate: `tests/test_adr0027_reference_document.py` asserts
  field-by-field semantics (assignee_name resolution, `scanCustomFields` values, link-run detection
  via `debug_action_runs`) that `test_apt_corpus_check.py`'s text-diff invariant does not
  independently verify, so it is genuinely distinct coverage, not a duplicate. It stays checked in
  as the human-reviewable, Doc-backed grammar reference; `apt.py pull/push/bless action-reference`
  still targets the real Drive doc above.

## Split per-boundary corpora (gts-ndb8, stage `apt-scenarios`)

`tests/fixtures/<boundary>.apt.txt` — one corpus per `[TST]` bead's grammar boundary
(`grammar-matrix.apt.txt` → gts-ucdz, `unparseable-reporting.apt.txt` → gts-thwh,
`hyperlink-roundtrip.apt.txt` → gts-tz5x, `field-continuation.apt.txt` → gts-82s2,
`dual-prefix.apt.txt` → gts-nrxn) — records copied verbatim from the canonical reference (N
tokens are literal text, never renumbered on decode, so moving a record between files does not
change its token). Each is **doc-less** (decision 7: a scenario corpus materialises into a fresh
`ScenarioSession.new_doc()` rather than naming a shared mutable Doc) and its own
`<!-- serves: ... -->` names exactly the one bead it exercises.

**Decision-9 annotation convention, concretely:** every action-token record is preceded, as its
own separate prose paragraph/record, by a one-line annotation naming the case and bead it
demonstrates, e.g.:

```
Case 1 (gts-ucdz): @-sigil email assignee.

ACT-3: @jane@example.com finish the report (Open)
```

No new syntax — the annotation is ordinary prose content the differ and the grammar already
preserve (ADR-0027: a plain paragraph carrying no token is not an action). `scripts/apt_lib.py`'s
`unannotated_records()` lints this: an action-token record whose immediately preceding record does
not read as plain prose is flagged. **Escaping still applies inside an annotation** — a literal
`<`, `>`, `*`, `_`, `[`, `]`, `{`, `}` or `\` in annotation prose needs the same backslash escape
as any other APT text (see Escaping above); an unescaped one round-trips escaped on the next
capture and reads as a spurious presentational diff.

## Scenario triples (gts-ndb8, stage `apt-scenarios`)

A **scenario** (staging doc Terminology) is `(input corpus, mutation, expected corpus)` — the
read-only reference is the degenerate case: `mutation: {"kind": "sync"}` ("sync once"), input and
expected are the same corpus, and the assertion is that a golden corpus survives a decode + sync +
re-encode unchanged. A non-degenerate `"sync"` scenario (different input/expected corpora) needs no
extra machinery either — the input corpus's own content (a bare `AI:` trigger, a duplicate
occurrence, a missing status token, an insertion position) is what triggers the flush; the single
establishing sync resolves it. Two further mutation kinds (stage `apt-lanes`, gts-iz9i) need a
live per-item action between the establishing sync and capture:

```json
{ "kind": "sheetEdit", "token": "AI-101", "fields": { "status": "In Progress" } }
{ "kind": "trigger", "token": "AI-107", "field": "status", "value": "Done" }
```

`sheetEdit` addresses an already-established record by its literal (never-renumbered) N token and
edits sheet field(s) — the sheetWin path; its flush lands on the runner's second sync, not the
first (Dirty-flag path). `trigger` drives the onEdit-trigger entry point
(`_syncSheetRowToDoc`) via the `edit_cell_via_trigger` test fixture and applies its own flush
immediately.

On disk, a scenario is `tests/fixtures/<name>.scenario.json`:

```json
{
  "name": "grammar-matrix",
  "input": "grammar-matrix",
  "mutation": { "kind": "sync" },
  "expected": "grammar-matrix",
  "serves": ["gts-ucdz"]
}
```

`input`/`expected` are corpus **names** (resolved to `tests/fixtures/<name>.apt.txt`, same
resolution `scripts/apt.py` uses), not paths. An optional `"batch"` field (e.g.
`"apt-lanes-flush"`, `"apt-lanes-create"`) names the batched runner that owns executing a scenario
(`tests/support/apt_lane_runner.py`, stage `apt-lanes`) — when set,
`tests/test_apt_corpus_check.py` skips it rather than re-running it under the one-doc-per-scenario
shape that runner exists to avoid (that lane measured 7 scenarios at 5.1 min — decision-load-bearing
enough that a batched scenario is never silently re-executed there). `scripts/apt_lib.py::load_scenario`
is the one shared parser (decision 8); `tests/test_apt_corpus_check.py` executes every
un-batched `"sync"` scenario against its own live Doc and asserts
`apt_lib.diff_apt(expected, captured).clean` — "apt check" as a pytest lane, sharing the same
differ a human's `apt.py diff` invokes.

### Batched lanes (gts-iz9i/gts-pi1s, stage `apt-lanes`)

`tests/support/apt_lane_runner.py::run_lane(scn, scenarios)` materialises every scenario's input
corpus into ONE Doc (`apt_lib.compose_corpora`), syncs once (establishing every record and
resolving every plain `"sync"`-kind scenario in the batch in the same call), applies each
`sheetEdit`/`trigger` scenario's own mutation, syncs a second time only if a `sheetEdit` mutation
was applied, captures the whole Doc once, and slices the single capture back into per-scenario
chunks (`apt_lib.slice_records`) to diff each against its own expected corpus. A corpus containing
a body-level `<TABLE...>` must be LAST among the scenarios passed to one `run_lane` call (the v2
table-position restriction, scoped to the whole composed Doc, not per scenario).

Because every scenario shares ONE Doc, a chip-badge preview link a fresh flush produces
(`[**ACT-N: **](...docId=<doc>&ain=ACT-N)`) carries THAT run's own randomly-generated `doc_id`
(decision 7: batched-lane corpora are doc-less) — unpredictable at golden-authoring time.
`run_lane` normalises this one substitution before diffing: the captured text's literal `doc_id`
is replaced with the placeholder `DOC_ID`, and a golden whose scenario forces a re-flush spells its
own chip URL with `docId=DOC_ID` rather than a real id. Golden corpora whose token is never
re-flushed (nothing in the scenario requires it — see the `dual-prefix`/`hyperlink-roundtrip`
corpora above) need no such placeholder: their content is byte-identical whichever Doc it lives in.

`tests/test_apt_flush_lane.py` (gts-iz9i) expresses flush entry points 1–4 and 7
(`flush-lane-*.apt.txt`/`.scenario.json`, `batch: "apt-lanes-flush"`) — sheetWin, newly-assigned,
missing-explicit-status materialization, duplicate-N reconciliation, and the onEdit-trigger path
(whose golden documents a KNOWN GAP: no `customFields` source on that path, so the field line is
dropped — matching `tests/test_field_continuation_flush.py::test_ep7_onedit_flush_known_gap`).
Entry points 5 and 6 (preview-card/sidebar status taps) stay covered by their existing UI-driven
tests — a sheet edit does not reach those call sites, and the entry-point-coverage invariant
requires the call site itself.

`tests/test_apt_create_lane.py` (gts-pi1s) expresses the `@create` boundary lane
(`create-lane-*.apt.txt`/`.scenario.json`, `batch: "apt-lanes-create"`): a bare `AI:` trigger
inserted at the start/middle/end of an already-populated corpus, plus inside a body-level table
cell — all plain `"sync"`-kind scenarios, since a bare trigger's presence in the input IS the
mutation. What these exercise is `_buildFlushRequests`' general occurrence scanner
(`_collectFlushOccurrences`, including its `item.table` nested-cell search) locating and rewriting
a freshly-assigned token wherever it lands in document order — the path `decodeAptIntoDoc`
(append-only against an empty body) never reaches, since every corpus it decodes ends up
flush-appended in file order regardless of which "boundary" a scenario's own record occupies
relative to its siblings.

## Non-goals

- Not a general Google Docs serialization (no headings, doc-level styles, non-action images, or
  nested tables). Tables and list items are supported per v2 above, within the stated
  restrictions (last-in-body position, flat single-level lists only).
- Not designed to be human-*written* Markdown-from-scratch fluently for arbitrary prose — it is
  designed to be human-*reviewed* and *extended* by editing existing records or copying the shape
  of a nearby one.
