# ADR-0027: Floating-action paragraph grammar — no field delimiter; status is header-line-scoped

**Status:** Proposed
**Date:** 2026-08-26
**Relates to:** gts-qi1j (the design bead this answers), gts-tis (closed obsolete by this ADR),
ADR-0023 (token spelling — `ACT-N:` canonical, `AI-N:` read-compatible), ADR-0024 (`custom_fields`
column; this ADR resolves the three parser questions ADR-0024 left open), ADR-0028 (link
preservation), gts-jxrw (bare-token truncation), gts-dr8j (soft-return continuation),
gts-v0py/gts-28q/gts-1tbe (status-token position rule), docs/CONTEXT.md §Action Format

## Context

The floating-action paragraph format has never been written down as a grammar. It exists as
behavior distributed across two parsers in `SyncManager.js` — `_parseParagraphAsFloatingAction`
(single-token fast path, handles PERSON chips) and `_parseSoftReturnParagraphActions`
(soft-return path, text-email only) — plus a shared status extractor,
`_extractStatusTokenTracked`. `docs/CONTEXT.md` §Action Format describes the detection rules in
prose but does not state a grammar precise enough to classify a given paragraph accept/reject
without reading parser source.

Two adjacent decisions are already on file and are **not reopened here**:

- **ADR-0023** decided the token spelling (`ACT-N:` canonical for writes, `AI-N:` read-valid
  indefinitely, one shared N namespace, token literal centralized, `globalId` shape unchanged).
  Questions Q1 (does the prefix change) and Q2 (is `globalId` coupled to the visible prefix) from
  gts-qi1j are answered there.
- **ADR-0024** decided that team-defined data rides on soft-return `Field: value` continuation
  lines into a `custom_fields` JSON sheet column, leaving the header line's field set unchanged.
  Questions Q3 (field set) and Q7 (does the change reach the sheet columns) are answered there.

Both were Accepted 2026-08-26 (gts-4l1a). This ADR presumes them.

What remained genuinely open was the delimiter grammar, its interaction with the trailing
`(Status)` token, and what happens to a paragraph that fails to parse.

### The pipe separator was residue, not a requirement

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
2026-08-26: **no live document uses the pipe form.**

## Decision

### 1. The grammar

```
actionParagraph := [inlineImage] token [assignee] actionBody [continuation*]
token           := ("ACT" | "AI") "-" digits ":" [ \t]*
assignee        := personChip | "@"? email [ \t]*
email           := [\w.+-]+ "@" [\w-]+ ("." [a-z]{2,})+
actionBody      := text [ statusToken ]
statusToken     := "(" [^)]* ")"        ; last such group on the HEADER LINE, per rule 4
continuation    := "\n" ( fieldLine | prose )
fieldLine       := fieldName ":" ( [ \t] inlineValue? | EOL )
fieldName       := fieldWord (" " fieldWord)*   ; ≤32 chars total (gts-eezz)
fieldWord       := [A-Z] [A-Za-z0-9_-]*
```

Whitespace between the token, the assignee and the action body is the only separator. There is
**no field delimiter**.

### 2. `|` carries no meaning

A pipe character anywhere in an action paragraph is literal text. There is no escape mechanism
because none is needed. gts-tis is **superseded**, not ratified, and is closed as obsolete.

The header line is deliberately not extensible by adding positional or keyed fields to it.
ADR-0024's `Field: value` continuation lines are the sanctioned extension point; a second
extension mechanism on the header line would give two ways to express the same thing and force an
escaping rule onto prose that currently needs none.

### 2a. The header-line field set is unchanged

No field is added to or removed from the parsed action record by this ADR. It remains
`globalId`, `N`, `assigneeEmail`, `assigneeName`, `actionText`, `status`, `hasExplicitStatus`,
`isDuplicate`, `runs`. `src/ContractSchema.js` needs no change on this ADR's account; the
`custom_fields` column ADR-0024 introduces is that ADR's change, not this one's, and it lands
outside the header line.

### 3. The assignee may carry a leading `@` sigil

`@jane@example.com` parses identically to `jane@example.com`. Unlike the pipe, this is a plausible
thing for a person to type — it mirrors the chip-insertion gesture — and admitting it costs one
optional character in the assignee production. The sigil is not stored; `assignee_email` holds the
bare address.

### 4. The status token is scoped to the header line

`_extractStatusTokenTracked` currently scans for the last `(...)` group anywhere in the action
text, which today means anywhere in the paragraph. Once ADR-0024's continuation lines exist, that
is wrong in two ways: a status token on the header line stops being the last group in the
paragraph and is silently missed (the action defaults to `Open`), and a field value that happens
to end in parentheses — `Progress: revenue section (blocked)` — is misread as the status.

**Status is extracted from the header line only, before continuation lines are considered.**
Parentheses in field values and in continuation prose are always literal. The position rule within
the header line (gts-28q as refined by gts-v0py and gts-1tbe — the last group qualifies only if
what follows it is empty or begins with a non-word character) is unchanged.

### 5. Field line versus continuation prose

A continuation line is a `fieldLine` if and only if it matches the bounded production above: no
leading whitespace, a name of at most 32 characters drawn from `[A-Za-z0-9 _-]` where **every
space-separated word starts with an uppercase letter**, then a colon followed by a space, a tab,
or the end of the line. A bare `Consult With:` with nothing after the colon is a field line with
an empty inline value, not prose. Every other continuation line is prose.

**Resolved (gts-eezz, 2026-08-26):** the per-word-uppercase constraint narrows the production as
first drafted here (`[A-Za-z] [A-Za-z0-9 _-]{0,31}`, no case requirement). That looser form cannot
actually distinguish a field name from ordinary prose containing a colon: `then he said` (12
chars, all letters/spaces) satisfies it exactly as `Consult With` does, so a sentence like `then
he said: we should ship it` would parse as a field line, which is wrong. The per-word-uppercase
form matches every field-name example on record (`Target`, `Progress`, `Notes`, `Consult With`,
`Due` — all Title Case) and correctly excludes lowercase sentence continuations. The 32-character
length bound is unchanged and still independently enforced.

This resolves ADR-0024's three open parser questions:

1. *Field-name line versus a continuation line containing a colon* — the bounded production. A
   prose line such as `then he said: we should ship it` fails it (`then`/`he`/`said` do not start
   with uppercase letters), so it stays prose. No per-team allowlist is required, and ADR-0024's
   open question about one is answered **no**.
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

A block's value is an ordered list of lines, joined with `\n`:

- the action body's first line is the header line's text (chip/email and status token stripped);
- a field's first line is its inline value — the text after the colon, or the empty string when
  the field line is bare;
- each subsequent prose line is appended in document order.

Line order within a block, and field order across blocks, are both document order and are
preserved end to end: parse, `custom_fields` JSON (object keys in insertion order), sheet cell,
and re-render on flush. The joined string is the value's `text` under ADR-0028 rule 6. A soft return in the document is a `\n` in the stored value and a soft
return again on flush — never a space, never a reordering, never a dropped line.

Worked example:

```
ACT-9: jane@example.com Draft the Q3 budget memo (In Progress)<BR>
- pull last year's actuals<BR>
- circulate before Friday<BR>
Consult With:<BR>
- Stuart<BR>
- John<BR>
Due: Tuesday
```

```
actionText    = "Draft the Q3 budget memo\n- pull last year's actuals\n- circulate before Friday"
custom_fields = {"Consult With": {"text": "\n- Stuart\n- John", "runs": []},
                 "Due":          {"text": "Tuesday",             "runs": []}}
```

(field values carry `{text, runs}` per ADR-0028 rule 6; the joined line text is the `text`, and
run offsets are indices into it, so a `\n` is an ordinary character as far as runs are concerned)

`- Stuart` and `- John` are the `Consult With` value, not action prose and not their own fields —
so a later tabular view of these records puts both names in the `Consult With` column. The leading
`\n` in that value is the bare field line's empty inline value, and is what lets flush re-render
`Consult With:` on its own line exactly as the author typed it.

**Repeated field name.** A field name that appears twice does not overwrite: the later block's
lines are appended to the existing value, in document order, separated by `\n`. Nothing an author
typed is dropped (the gts-dr8j / gts-zocq precedent), at the cost of the two occurrences reading
as one value on flush.

**Round-trip.** Flush renders block *n* as `Name:` + the value's first line + one soft return per
remaining line, in order. Parsing that output reproduces the same blocks, so the rendering is
exact for input already in this shape and idempotent thereafter.

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

## Consequences

**Positive:**

- The grammar is stated precisely enough to classify a paragraph accept/reject without reading
  parser source, which is gts-qi1j's acceptance criterion.
- Declining the delimiter removes an escaping problem rather than solving one; prose pipes and
  parenthesized field values stay literal with no user-visible rule to learn.
- Rule 4 catches a real defect in ADR-0024's implementation path before it ships, at the cost of
  one scoping change in a function that already exists.
- Rule 6 converts a silent data-loss path into a reported one, consistent with this project's
  repeated precedent (gts-dr8j, gts-zocq, gts-v0py) that author-typed intent is never discarded
  quietly.

**Negative / tradeoffs:**

- The 32-character field-name bound in rule 5 is a judgment call, not a derived constant. A team
  wanting a longer field name gets prose instead, with no diagnostic. Rule 6's reporting does not
  cover this case because the paragraph itself parses fine. Under rule 5a that misclassified line
  is now absorbed into the preceding field's value rather than into `actionText`, which is a
  quieter failure than it was — the text survives, but under a neighbouring label.
- Rule 5a makes `custom_fields` values multi-line strings, where ADR-0024's examples show only
  single-line ones. The column's shape is unchanged (JSON object, string values); a sheet cell can
  now contain embedded newlines, which is opaque to Sheets-native filtering — already accepted in
  ADR-0024 for this admin-only sheet.
- Appending on a repeated field name is the lossless choice, not the intuitive one: an author who
  retypes `Due:` to correct it gets both values concatenated rather than the later one winning.
  Making the correction case work would require discarding author-typed text, which this project
  does not do silently.
- The header line cannot grow new fields without a further ADR. This is intended, but it means a
  future due-date or priority field must arrive as a continuation field rather than as a
  first-class column, or reopen this decision.
- Rule 4 requires the two parsers to agree on where the header line ends. They already diverge on
  assignee handling (`_parseParagraphAsFloatingAction` reads PERSON chips;
  `_parseSoftReturnParagraphActions` is text-email only), so the header-line split must be factored
  into one shared helper or the status rule will drift between the two paths — the same class of
  drift `_extractStatusTokenTracked` was extracted to prevent (gts-v0py).

**Resolved (2026-08-26, gts-4l1a):** the shared header-line helper (rule 4's status-scoping) folds
into this ADR's `[IMP]` twin — both parsers must agree on where the header line ends for rule 4 to
hold at all. Full PERSON-chip/text-email parity in the soft-return path is tracked separately as
its own bead, not folded into this ADR's implementation.

## Related

Depends on ADR-0023 for the token production and on ADR-0024 for the existence of continuation
lines; resolves ADR-0024's three deferred parser questions. ADR-0028 governs what inline
formatting and links survive inside `actionText` and inside field values, and is independently
adoptable.
