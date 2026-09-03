"""apt_lib.py — shared pure-Python core for Action Portable Text (APT) tooling
(gts-snub, gts-x9un, gts-ndb8; designed across stages `apt-differ` and
`apt-scenarios` of the staged plan that built this tooling — deleted on close,
per Pattern D; its numbered "decision N" design calls cited throughout this
module are reconstructed at docs/interfaces/action-portable-text.md
§Tooling design decisions, the durable home its own header promised).

Three responsibilities, kept in one module per decision 8 (the differ must
have exactly one implementation shared by the CLI and by pytest — this module
IS that shared implementation; `scripts/apt.py`, stage `apt-cli`/gts-4bop,
imports it rather than reimplementing):

  parse_header(text)        -- read the structured preamble (gts-x9un)
  diff_apt(golden, capture) -- classify differences (gts-snub)
  load_scenario(path)       -- read a (input, mutation, expected) triple (gts-ndb8)

Pure Python, no network, no GAS dependency (decision 3) — this is what makes
both offline-unit-testable and gives an `apt diff a b` CLI for free later.
`load_scenario` is data marshaling only — it does not execute a mutation
(that needs a live Doc and stays in the pytest lane / stage `apt-lanes`).

Format reference: docs/interfaces/action-portable-text.md. This module does
not re-derive the grammar (soft returns, escaping, chip syntax) — it treats
each record as opaque text plus the light structural cues (leading N token,
`Field: value` lines, `[text](url)` links) needed to classify a difference,
matching the encode/decode contract in src/PortableText.js.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
import re

# ---------------------------------------------------------------------------
# Structured preamble (gts-x9un)
# ---------------------------------------------------------------------------
#
# One `<!-- key: value -->` comment line per field, e.g.:
#
#   <!-- kind: golden -->
#   <!-- name: action-reference -->
#   <!-- doc: 1PYIU022o5dWNhIkyErjUzF6TRg--r4QrH-h-JbPNO-E -->
#   <!-- serves: gts-colw, gts-ucdz, gts-thwh, gts-tz5x, gts-82s2, gts-nrxn -->
#   <!-- generated: 2026-08-27T21:51:31.347Z -->
#
# `kind` is `golden` (a reviewed, blessed corpus checked into tests/fixtures/)
# or `capture` (a raw encode of a live Doc — decision 1: only `bless` may
# promote a capture to a golden; a capture is never itself a golden). `name`,
# `doc` (decision 7: optional) and `serves` are free text; `generated` is an
# ISO-8601 timestamp. Unrecognised or legacy free-text preamble comment lines
# (the pre-gts-x9un single-line format) are ignored, not errors — decode has
# never interpreted the preamble and still doesn't.

_HEADER_LINE_RE = re.compile(r"^<!--\s*([A-Za-z_]+):\s*(.*?)\s*-->\s*$")
_N_TOKEN_RE = re.compile(r"^(ACT|AI)-(\d+):")
# Sees through the SAME leading markup _looks_like_plain_prose/record_token
# already lstrip("[*") past: a token that has been flushed at least once is
# rendered as a bold link-badge, `[**ACT-9: **](url)` -- the raw N-token
# regex above, anchored at position 0, never matches THAT shape (gts-iz9i,
# stage `apt-lanes`, first surfaced this: every pre-existing corpus whose
# token round-trips this way happens to never re-flush, so its digits never
# actually differ between golden and capture -- a batch that forces a
# re-flush is what exposes the gap). Captures the markup prefix in group 1
# so _normalize_n can put it back unchanged.
_N_TOKEN_MARKUP_RE = re.compile(r"^(\[\*\*)?(ACT|AI)-(\d+):")
# The SAME flushed badge also repeats its N inside the chip-preview URL's
# `ain=` query param (`...&ain=ACT-9)`), not just the leading label matched
# above. That second occurrence sits after the record's start, so the
# start-anchored regex above never reaches it -- left unmatched, a re-flushed
# record's `ain=ACT-<N>` digits differ golden vs capture even after the label
# itself normalises, which is exactly gts-iz9i's flush-lane-new-assign
# surfacing the same latent gap a second place (decision 5: N is positional
# everywhere it appears, not just at the label).
_N_AIN_PARAM_RE = re.compile(r"(ain=)(ACT|AI)-(\d+)")
# gts-py21: a not-yet-assigned BARE trigger ("ACT: .../AI: ..." — no digits)
# normalises to the SAME placeholder as an already-numbered token
# (decision 5's positional-N rule extended one step: the bare-to-assigned
# transition IS the N assignment itself, just caught one edge earlier than
# _N_TOKEN_MARKUP_RE above can see, which requires digits to already exist).
# Without this, a copy-fidelity check that pulls a doc BEFORE a first sync
# (bare trigger) and compares it against the SAME doc's own copy AFTER that
# sync (now digit-assigned) reports every such record as a false structural
# "content changed" — the doc's worked-example content legitimately mixes
# bare and pre-assigned demonstration paragraphs by design
# (tests/test_floating_action_copy_fidelity.py), so this transition is
# positional, not structural, the same way renumbering N itself already is.
# Only applied when the digit form above didn't already match (count=1
# below is enough since a record's leading token line is normalised once).
_BARE_TRIGGER_MARKUP_RE = re.compile(r"^(\[\*\*)?(ACT|AI):")

VALID_KINDS = ("golden", "capture")

# APT v2 (gts-83s5) — a list-item record's first physical line carries a
# leading `<LI> ` marker (src/PortableText.js's _APT_LI_PREFIX) ahead of its
# content. Every N-token/prose heuristic below inspects a record's first
# line, so they need to see through this marker the same way they already
# see through nothing for a plain paragraph — otherwise a bulleted-list
# action would silently stop getting decision-5 N normalisation and
# decision-9 annotation-lint coverage the moment it moves into a list item.
_LI_PREFIX = "<LI> "


def _strip_li_prefix(line: str) -> str:
    return line[len(_LI_PREFIX):] if line.startswith(_LI_PREFIX) else line


def split_preamble_and_body(text: str) -> tuple[str, str]:
    """Splits `text` into (preamble_chunk, rest) on the first blank line,
    matching src/PortableText.js's `_aptSplitRecords`: the preamble is
    everything before the first blank physical line, and only counts as a
    preamble at all if it starts with `<!--`. Returns ("", text) when there
    is no comment preamble.
    """
    normalized = text.replace("\r\n", "\n")
    parts = re.split(r"\n\n+", normalized, maxsplit=1)
    first = parts[0]
    if first.lstrip().startswith("<!--"):
        rest = parts[1] if len(parts) > 1 else ""
        return first, rest
    return "", normalized


def parse_header(text: str) -> dict:
    """Parses every `<!-- key: value -->` line in `text`'s preamble into a
    dict. Missing fields are simply absent — callers decide what's required
    (e.g. the fixtures-lint requires `kind`; the differ requires nothing).
    """
    preamble, _ = split_preamble_and_body(text)
    header = {}
    for line in preamble.splitlines():
        m = _HEADER_LINE_RE.match(line.strip())
        if m:
            header[m.group(1)] = m.group(2)
    return header


def format_header(fields: dict) -> str:
    """Inverse of parse_header's line format, in a stable field order —
    written by a future `bless`/`pull` (gts-4bop) and by tests constructing
    fixtures in-memory."""
    order = ["kind", "name", "doc", "serves", "generated"]
    lines = []
    for key in order:
        if key in fields and fields[key] not in (None, ""):
            lines.append(f"<!-- {key}: {fields[key]} -->")
    for key, value in fields.items():
        if key not in order and value not in (None, ""):
            lines.append(f"<!-- {key}: {value} -->")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


def split_records(text: str) -> list[str]:
    """Returns the record bodies (blank-line-separated chunks after the
    preamble), each still containing its own `<SR>`-suffixed physical lines
    — mirrors src/PortableText.js's `_aptSplitRecords`."""
    _, body = split_preamble_and_body(text)
    body = body.strip("\n")
    if not body:
        return []
    return [c for c in re.split(r"\n\n+", body) if c]


def _normalize_n(record: str) -> str:
    """Replaces a leading `ACT-<digits>:` / `AI-<digits>:` token's digits
    with a placeholder so two records that differ ONLY in N compare equal
    (decision 5: N is normalised positionally in the diff; N-assignment
    invariants get their own assertions outside the diff lane). Sees through
    a leading APT v2 `<LI> ` list-item marker (_strip_li_prefix) so a
    bulleted-list action gets the same normalisation as a plain paragraph
    one."""
    prefix = _LI_PREFIX if record.startswith(_LI_PREFIX) else ""
    body = _strip_li_prefix(record)
    # gts-py21: normalise the token on EVERY line that carries one, not just
    # the record's first. src/SyncManager.js's _collectTokenParagraphs scans
    # every line of a paragraph for a token, so a record whose token sits on
    # a continuation line (the "<LI> intro text:<SR>\nACT: ..." shape) is
    # just as much an action record as one whose token leads — and its N is
    # just as positional. Anchoring at the record's first line only left
    # those records' labels un-normalised, so their N showed up as a
    # structural content change.
    lines = []
    for line in body.split("\n"):
        digit_normalized = _N_TOKEN_MARKUP_RE.sub(
            lambda m: f"{m.group(1) or ''}{m.group(2)}-#:", line, count=1
        )
        if digit_normalized != line:
            lines.append(digit_normalized)
        else:
            lines.append(
                _BARE_TRIGGER_MARKUP_RE.sub(
                    lambda m: f"{m.group(1) or ''}{m.group(2)}-#:", line, count=1
                )
            )
    body = "\n".join(lines)
    body = _N_AIN_PARAM_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}-#", body)
    return prefix + body


_MARKUP_RE = re.compile(r"\*\*|\*|_|\\(.)")
_LINK_RE = re.compile(r"\[((?:[^\[\]\\]|\\.)*)\]\(((?:[^()\\]|\\.)*)\)")
_FIELD_LINE_RE = re.compile(r"^([A-Z][A-Za-z ]*):\s?(.*)$")
# gts-py21: a not-yet-assigned bare trigger line ("ACT: ..."/"AI: ...", no
# digits) matches _FIELD_LINE_RE too -- "ACT"/"AI" is itself a bare,
# capitalised, colon-terminated word, indistinguishable from a real custom
# field label by that regex alone. Once the record is synced/flushed, the
# SAME line becomes an established, markup-wrapped "[**ACT-9: **](url)..."
# header, which _FIELD_LINE_RE correctly does NOT match (mirrors
# _N_TOKEN_MARKUP_RE's own markup-aware anchoring above) -- so a diff across
# that transition sees a "field" silently vanish and misreports a real,
# expected token-assignment as a structural field removal. Exclude both
# trigger shapes explicitly rather than letting the generic field-label
# pattern guess.
_BARE_TRIGGER_LINE_RE = re.compile(r"^(?:\[\*\*)?(ACT|AI):")


def _strip_markup(text: str) -> str:
    """Plain-text content of a record: links reduced to their text (URL
    dropped), bold/italic markers removed, escapes resolved, `<SR>` markers
    and the `<BLANK>`/`<EMPTY>` sentinels normalised to nothing/blank so pure
    reflow (indent, tab-vs-space, marker placement) never shows up here —
    that's what makes this the presentational/structural boundary."""
    text = _LINK_RE.sub(lambda m: m.group(1), text)
    text = text.replace("<SR>", "")
    text = re.sub(r"<BLANK>", "", text)
    text = re.sub(r"<EMPTY>", "", text)
    text = re.sub(r"\*\*|\*|_", "", text)
    text = re.sub(r"\\(.)", r"\1", text)
    # Whitespace is presentational (indent, tab-vs-space) — collapse it.
    text = re.sub(r"[ \t]+", " ", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def _extract_links(record: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2)) for m in _LINK_RE.finditer(record)]


def _field_labels(record: str) -> list[str]:
    labels = []
    for line in record.split("\n"):
        stripped = line[: -len("<SR>")] if line.endswith("<SR>") else line
        if _BARE_TRIGGER_LINE_RE.match(stripped):
            continue
        m = _FIELD_LINE_RE.match(stripped)
        if m:
            labels.append(m.group(1))
    return labels


def _line_count(record: str) -> int:
    return record.count("\n") + 1


# ---------------------------------------------------------------------------
# Classification (gts-snub, decision 4)
# ---------------------------------------------------------------------------

POSITIONAL = "positional"
PRESENTATIONAL = "presentational"
STRUCTURAL = "structural"
PRESERVATION = "preservation"

_STRICTNESS = {POSITIONAL: 0, PRESENTATIONAL: 1, STRUCTURAL: 2, PRESERVATION: 3}


def _stricter(a: str, b: str) -> str:
    return a if _STRICTNESS[a] >= _STRICTNESS[b] else b


@dataclasses.dataclass
class DiffEntry:
    klass: str
    record_index: int
    summary: str
    golden: str | None
    capture: str | None


@dataclasses.dataclass
class AptDiffResult:
    entries: list

    @property
    def classes_present(self) -> set:
        return {e.klass for e in self.entries}

    @property
    def clean(self) -> bool:
        return not self.entries

    def exit_code(self) -> int:
        """Highest class present, per gts-4bop's planned exit-code contract
        (0 clean, then rising by strictness): 0 none, 1 presentational,
        2 structural, 3 preservation. Positional never appears (normalised
        away, decision 4), so it never raises the exit code."""
        if not self.entries:
            return 0
        return max(_STRICTNESS[k] for k in self.classes_present if k != POSITIONAL) \
            if self.classes_present - {POSITIONAL} else 0


# gts-py21: ADR-0027 rule 4 bundles N-assignment together with a status
# suffix (" (Open)" etc.) on the SAME transition -- a bare trigger becoming
# an assigned token also gains a status suffix it never had before, in one
# atomic write. _normalize_n above already neutralises the N half; this
# neutralises the status half, but ONLY when the record just crossed the
# bare-to-assigned boundary (never on an already-assigned record, where a
# status change like Open->Done must stay visible as a real diff).
_ASSIGNED_STATUS_SUFFIX_RE = re.compile(r"\s\([A-Za-z][A-Za-z ]*\)(?=(<SR>)?$)")

# The token header a flush WRITES, as it looks after _normalize_n has already
# replaced the digits with the '#' placeholder: a bold, preview-linked label
# ("[**ACT-#: **](https://.../NUUTS?cmd=preview&docId=...&ain=ACT-#)"). The
# bare trigger it replaced carried no markup at all, so reducing this back to
# the bare "ACT-#: " spelling is what makes the two sides of the transition
# comparable at all (docs/interfaces/action-portable-text.md).
_ASSIGNED_TOKEN_HEADER_RE = re.compile(r"^\[\*\*(ACT|AI)-#:\s*\*\*\]\([^)]*\)")

# ADR-0027 rule 5/5a continuation fields render, once flushed, as a BOLD
# label followed by a tab ("**Field-1:**\tvalue") -- the canonical spelling
# src/SyncManager.js's _renderCustomFieldLines emits. A hand-authored doc
# spells the same field plainly ("Field-1: value"), so first flush
# canonicalises it. Reduce the flushed spelling back to the plain one.
_FLUSHED_FIELD_LINE_RE = re.compile(r"^\*\*([^*\n]+?):\*\*\t")


def _bare_to_assigned_lines(golden: str, capture: str) -> list[int]:
    """Line indices (into the record, `<LI> ` marker already stripped) where
    the golden still carries a bare trigger and the capture carries an
    assigned token — i.e. the lines this capture's first flush minted an N
    on. Checked per line, not just line 0: a token may legitimately sit on a
    continuation line ("<LI> intro text:<SR>\\nACT: ..."), which is exactly
    the record shape src/SyncManager.js's soft-return parser owns."""
    g_lines = _strip_li_prefix(golden).split("\n")
    c_lines = _strip_li_prefix(capture).split("\n")
    return [
        i
        for i in range(min(len(g_lines), len(c_lines)))
        if _BARE_TRIGGER_MARKUP_RE.match(g_lines[i])
        and _N_TOKEN_MARKUP_RE.match(c_lines[i])
    ]


def _undo_first_flush_canonicalisation(
    capture: str, golden: str, transition_lines: list[int]
) -> str:
    """gts-py21: reduce a just-flushed record's canonical spellings back to
    the plain, hand-authored spellings the SAME record carried before its
    first sync — each newly-assigned token line's bold preview link back to a
    bare `ACT-#: `, the ` (Status)` suffix that assignment bundled with it
    away, and each continuation field's `**Label:**\\t` back to `Label: `.

    `capture` is the already-`_normalize_n`'d capture; `golden` the raw
    golden (read only, to tell a minted status from one the original already
    carried). Applied ONLY where `_bare_to_assigned_lines` confirmed a
    transition, i.e. exactly the one write in a record's life where these
    three changes are the system doing its job rather than content drifting.
    Everything else in the record — its prose, its chips, its links, its line
    count — is left untouched and still diffs normally, so a real edit
    smuggled into the same flush (a dropped PERSON chip, a lost trailing
    blank line) stays visible.
    """
    prefix = _LI_PREFIX if capture.startswith(_LI_PREFIX) else ""
    lines = _strip_li_prefix(capture).split("\n")
    g_lines = _strip_li_prefix(golden).split("\n")
    for i in transition_lines:
        lines[i] = _ASSIGNED_TOKEN_HEADER_RE.sub(
            lambda m: f"{m.group(1)}-#: ", lines[i], count=1
        )
        # Only the status the flush MINTED is normalised away. A status the
        # hand-authored original already carried is an input to the flush,
        # not an output of it -- leave it so an Open->Done (or a dropped
        # status) still diffs as the real change it would be.
        if not _ASSIGNED_STATUS_SUFFIX_RE.search(g_lines[i]):
            lines[i] = _ASSIGNED_STATUS_SUFFIX_RE.sub("", lines[i], count=1)
    transitioned = set(transition_lines)
    for i in range(len(lines)):
        if i in transitioned:
            continue
        lines[i] = _FLUSHED_FIELD_LINE_RE.sub(lambda m: f"{m.group(1)}: ", lines[i], count=1)
    return prefix + "\n".join(lines)


def _classify_record_pair(index: int, golden: str, capture: str) -> DiffEntry | None:
    norm_g, norm_c = _normalize_n(golden), _normalize_n(capture)
    transition_lines = _bare_to_assigned_lines(golden, capture)
    if transition_lines:
        norm_c = _undo_first_flush_canonicalisation(norm_c, golden, transition_lines)
    if norm_g == norm_c:
        return None  # identical, or differs only in N (positional — not shown)

    plain_g, plain_c = _strip_markup(norm_g), _strip_markup(norm_c)

    # A link's text surviving as plain content while its URL vanished is a
    # preservation case regardless of what else in the record also changed
    # — checked BEFORE the plain-text-equality shortcut below (a dropped
    # link's visible text is often unchanged, which would otherwise read as
    # merely presentational). Ambiguity resolves to the strictest tier
    # (decision 4), never the loosest.
    links_g = _extract_links(golden)
    urls_g = {u for _, u in links_g}
    urls_c = {u for _, u in _extract_links(capture)}
    dropped_urls = urls_g - urls_c
    if dropped_urls and any(text in plain_c for text, url in links_g if url in dropped_urls):
        return DiffEntry(PRESERVATION, index, "link dropped", golden, capture)

    if plain_g == plain_c:
        return DiffEntry(PRESENTATIONAL, index, "formatting/whitespace only", golden, capture)

    if _line_count(capture) < _line_count(golden):
        return DiffEntry(PRESERVATION, index, "line count reduced", golden, capture)

    if plain_c and plain_g and plain_c != plain_g and plain_c in plain_g and len(plain_c) < len(plain_g):
        return DiffEntry(PRESERVATION, index, "value shortened", golden, capture)

    fields_g, fields_c = set(_field_labels(golden)), set(_field_labels(capture))
    if fields_g != fields_c:
        added = fields_c - fields_g
        removed = fields_g - fields_c
        bits = []
        if added:
            bits.append(f"field(s) added: {', '.join(sorted(added))}")
        if removed:
            bits.append(f"field(s) removed: {', '.join(sorted(removed))}")
        return DiffEntry(STRUCTURAL, index, "; ".join(bits), golden, capture)

    return DiffEntry(STRUCTURAL, index, "content changed (prose/field reclassification or edit)", golden, capture)


def diff_apt(golden_text: str, capture_text: str) -> AptDiffResult:
    """Pure file x file comparator (decision 3). N is normalised
    positionally (decision 5): records are paired by position, not by their
    N label. A record present in one side and absent in the other (record
    count differs) is `structural` per decision 4 ("record ... added or
    removed"); ambiguous single-record differences resolve to the strictest
    applicable tier, never the loosest."""
    golden_records = split_records(golden_text)
    capture_records = split_records(capture_text)

    entries: list[DiffEntry] = []
    common = min(len(golden_records), len(capture_records))
    for i in range(common):
        entry = _classify_record_pair(i, golden_records[i], capture_records[i])
        if entry is not None:
            entries.append(entry)

    for i in range(common, len(golden_records)):
        entries.append(DiffEntry(STRUCTURAL, i, "record removed", golden_records[i], None))
    for i in range(common, len(capture_records)):
        entries.append(DiffEntry(STRUCTURAL, i, "record added", None, capture_records[i]))

    return AptDiffResult(entries)


# ---------------------------------------------------------------------------
# Capture store (gts-x9un) — retention helper.
#
# The store itself (.apt-captures/, gitignored) is written to by `pull`
# (stage apt-cli, gts-4bop, not yet built). This is the pure retention
# policy that command will call — kept here so it is offline-unit-testable
# now rather than invented ad hoc alongside the transport code later.
# ---------------------------------------------------------------------------


def captures_to_evict(existing_names: list, keep_last_n: int) -> list:
    """Given capture filenames for ONE corpus name (already sorted oldest ->
    newest by the caller, e.g. by embedded timestamp or mtime), returns the
    prefix to delete so at most `keep_last_n` remain. Pure and file-I/O-free
    so the CLI's retention behaviour is unit-testable without a real
    filesystem."""
    if keep_last_n < 0:
        raise ValueError("keep_last_n must be >= 0")
    overflow = len(existing_names) - keep_last_n
    if overflow <= 0:
        return []
    return list(existing_names[:overflow])


# ---------------------------------------------------------------------------
# Scenario triples (gts-ndb8, stage `apt-scenarios`)
#
# Terminology (staging doc): a scenario is (input corpus, mutation, expected
# corpus) -- a read-only reference is the degenerate case, mutation
# {"kind": "sync"} ("sync once"). Non-degenerate mutation kinds (a sheet
# edit, an @create insertion) are stage `apt-lanes`' job -- this loader
# accepts any `kind` string but does not know how to EXECUTE one; that stays
# in the pytest lane that owns a live Doc (decision 3: no network here).
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Scenario:
    name: str
    input_corpus: str
    mutation: dict
    expected_corpus: str
    serves: list
    batch: str | None = None
    #: gts-5ktl (stage `lane-idempotency`): whether the batched runner's
    #: second, no-op sync must reproduce this scenario's own slice byte for
    #: byte. Default ON -- a scenario whose mutation is inherently multi-sweep
    #: (or whose expected corpus deliberately encodes a still-converging
    #: state) opts out with `"idempotent": false` in its scenario.json plus a
    #: recorded reason, so the exclusion is a decision on record rather than a
    #: silent skip.
    idempotent: bool = True

    @property
    def is_degenerate(self) -> bool:
        """The read-only-reference case (Terminology): mutation is 'sync
        once' and input == expected -- captured state must already equal the
        golden it was decoded from."""
        return self.mutation.get("kind") == "sync" and self.input_corpus == self.expected_corpus


def load_scenario(path) -> Scenario:
    """Reads one `<name>.scenario.json` triple. Required keys: `input`,
    `mutation` (an object with at least a `kind`), `expected`. `name`
    defaults to the file's own stem; `serves` defaults to `[]` (a scenario
    that names no bead is legal here -- gts-ndb8's `serves:`-per-corpus rule
    is about the *corpus* header, not this manifest). `batch` (stage
    `apt-lanes`, gts-iz9i/gts-pi1s) is optional and names the batched runner
    that owns executing this scenario (tests/support/apt_lane_runner.py) --
    when set, the generic single-scenario lane (tests/test_apt_corpus_check.py)
    skips it rather than executing it a second time under the one-doc-per-
    scenario shape the batched runner exists to avoid. `idempotent`
    (gts-5ktl, stage `lane-idempotency`) is optional and defaults to True --
    set it to `false` (with the reason recorded in the file) to exclude this
    scenario from the batched runner's second-capture diff."""
    path = pathlib.Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    for key in ("input", "mutation", "expected"):
        if key not in raw:
            raise ValueError(f"{path}: scenario triple missing required key {key!r}")
    if not isinstance(raw["mutation"], dict) or "kind" not in raw["mutation"]:
        raise ValueError(f"{path}: 'mutation' must be an object with a 'kind'")
    idempotent = raw.get("idempotent", True)
    if not isinstance(idempotent, bool):
        raise ValueError(
            f"{path}: 'idempotent' must be a boolean when present "
            "(gts-5ktl -- opting out of the lane's second-capture diff is a "
            "recorded decision, not a truthy value)"
        )
    return Scenario(
        name=raw.get("name") or path.stem.removesuffix(".scenario"),
        input_corpus=raw["input"],
        mutation=raw["mutation"],
        expected_corpus=raw["expected"],
        serves=list(raw.get("serves") or []),
        batch=raw.get("batch"),
        idempotent=idempotent,
    )


# ---------------------------------------------------------------------------
# Degenerate-scenario lint (gts-5st5, stage `apt-corpora-rebuild`)
#
# The failure this exists to make impossible: all 15 scenario triples once had
# `input == expected` under `mutation: sync`, so every assertion reduced to
# `encode(sync(decode(X))) == X` -- which a sync that scans NOTHING satisfies.
# On 2026-08-29 a sync that scanned 1 of 21 actions went undetected for exactly
# that reason (knowledge-base/staging/apt-oracle.md, "Why this plan exists").
#
# Identity is compared on the corpora's RECORDS, after `_normalize_n`, not on
# raw file bytes. Two reasons, both about matching the check to the assertion
# it protects:
#
#   * Raw bytes would be trivially defeated by the preamble. A `<name>` and a
#     `<name>-expected` corpus always differ in their own `<!-- name: ... -->`
#     line, so a byte comparison of whole files reports "different" even for a
#     verbatim copy -- the exact case this lint has to catch.
#   * `diff_apt` normalises N positionally (decision 5), so a pair differing
#     ONLY in its N digits is indistinguishable, to the assertion, from a pair
#     that is identical. Comparing raw N here would pass a scenario the lane
#     still cannot fail. Normalising is therefore strictly the stronger test,
#     and it is the same normalisation the differ itself applies.
# ---------------------------------------------------------------------------

#: Scenarios whose post-mutation state genuinely equals their input, each with
#: the reason that makes it so (gts-5st5 AC3: an exemption without a stated
#: reason is how the vacuous shape returns). Re-verified live per entry by
#: gts-ru4c -- an entry here is a claim about the SPEC, not a record of what
#: the implementation happens to do today.
DEGENERATE_SCENARIO_ALLOWLIST = {
    "unparseable-reporting": (
        "ADR-0027 rule 6: a paragraph opening with a token but failing the "
        "grammar is REPORTED as unparseable-action-paragraph and is neither "
        "synced nor rewritten, so its post-sync document state is its input by "
        "definition. The corpus's non-vacuous assertion is the report itself "
        "(tests/test_doc_oracle_reference.py), not this text diff, which can "
        "only ever assert that the paragraph was left alone."
    ),
    "unparseable-reporting-verify": (
        "Same corpus, same rule-6 reasoning as 'unparseable-reporting' above -- "
        "reused under stage `apt-scanner-migration`'s own batch tag "
        "(gts-oaw1/gts-xvlu) so a live verify_consistency call can be asserted "
        "on the same open ScenarioSession this scenario's establishing sync "
        "leaves behind. The corpus's non-vacuous assertion is that "
        "verify_consistency call (tests/test_apt_scanner_lane.py), not this "
        "text diff."
    ),
}


def normalized_records(text: str) -> list[str]:
    """A corpus's records with N normalised — the unit the degenerate-scenario
    lint compares, and the same normalisation `diff_apt` applies before it
    decides two records are equal."""
    return [_normalize_n(r) for r in split_records(text)]


def corpora_are_equivalent(input_text: str, expected_text: str) -> bool:
    """True when the two corpora carry the same records modulo N — i.e. when
    `diff_apt(expected, capture)` could not tell a real mutation from a no-op
    for this pair."""
    return normalized_records(input_text) == normalized_records(expected_text)


def degenerate_scenario_problems(
    scenario: "Scenario",
    input_text: str,
    expected_text: str,
    allowlist: dict | None = None,
) -> list[str]:
    """Returns the lint problems for ONE scenario triple, empty when clean.

    Three problems are reported, not one — an allowlist that rots silently is
    the same defect in a new place:

      * a non-allowlisted scenario whose input and expected are equivalent;
      * an allowlist entry with no (or blank) stated reason;
      * an allowlist entry for a scenario that is no longer degenerate, which
        would otherwise keep a real mutation exempt forever.
    """
    allowlist = DEGENERATE_SCENARIO_ALLOWLIST if allowlist is None else allowlist
    equivalent = corpora_are_equivalent(input_text, expected_text)
    exempt = scenario.name in allowlist
    problems = []
    if exempt:
        reason = (allowlist.get(scenario.name) or "").strip()
        if not reason:
            problems.append(
                f"{scenario.name}: allowlisted as degenerate with no stated "
                "reason (gts-5st5 AC3 — every exemption states why)."
            )
        if not equivalent:
            problems.append(
                f"{scenario.name}: allowlisted as degenerate, but its input "
                f"({scenario.input_corpus}) and expected "
                f"({scenario.expected_corpus}) corpora now differ — remove the "
                "DEGENERATE_SCENARIO_ALLOWLIST entry rather than leaving a real "
                "mutation exempt."
            )
    elif equivalent:
        problems.append(
            f"{scenario.name}: mutation {scenario.mutation.get('kind')!r} is "
            f"state-changing, but input ({scenario.input_corpus}) and expected "
            f"({scenario.expected_corpus}) carry identical records (modulo N), "
            "so the lane asserts encode(sync(decode(X))) == X — a sync that "
            "scans nothing passes it. Re-author the expected corpus as the "
            "real post-mutation state, or add a reasoned "
            "DEGENERATE_SCENARIO_ALLOWLIST entry."
        )
    return problems


def lint_scenarios(fixtures_dir, allowlist: dict | None = None) -> list[str]:
    """Runs `degenerate_scenario_problems` over every `*.scenario.json` under
    `fixtures_dir`, plus one whole-directory check: an allowlist entry naming a
    scenario that does not exist. Shared by `scripts/apt.py lint` and the
    pytest lane (gts-5st5 AC1) so there is one implementation, not two —
    decision 8's rule for the differ, applied to the lint."""
    allowlist = DEGENERATE_SCENARIO_ALLOWLIST if allowlist is None else allowlist
    fixtures_dir = pathlib.Path(fixtures_dir)
    problems: list[str] = []
    seen = set()
    for path in sorted(fixtures_dir.glob("*.scenario.json")):
        scenario = load_scenario(path)
        seen.add(scenario.name)
        input_path = fixtures_dir / f"{scenario.input_corpus}.apt.txt"
        expected_path = fixtures_dir / f"{scenario.expected_corpus}.apt.txt"
        if not input_path.exists() or not expected_path.exists():
            continue  # corpus existence is test_apt_scenario_format's lint
        problems.extend(degenerate_scenario_problems(
            scenario,
            input_path.read_text(encoding="utf-8"),
            expected_path.read_text(encoding="utf-8"),
            allowlist=allowlist,
        ))
    for name in sorted(set(allowlist) - seen):
        problems.append(
            f"{name}: DEGENERATE_SCENARIO_ALLOWLIST names a scenario with no "
            f"{name}.scenario.json under {fixtures_dir} — a stale exemption."
        )
    return problems


# ---------------------------------------------------------------------------
# Decision-9 annotation lint
#
# "Every corpus record added for test purposes carries a prose annotation
# naming what it demonstrates." Heuristic, not a grammar check: a record
# counts as annotated when the record immediately before it (in document
# order) carries no leading N token and no `Field:`-shaped line of its own --
# i.e. it reads as plain prose, not another action.
# ---------------------------------------------------------------------------


def record_token(record: str) -> str | None:
    """Returns a record's leading N token (e.g. "ACT-3", "AI-10"), or None if
    the record carries no such token -- sees through the APT v2 `<LI> `
    list-item marker like every other N-token heuristic in this module.
    Used by stage `apt-lanes`' batched runner to address a specific record's
    action by its literal (never-renumbered, decision 5) token spelling when
    applying a declarative sheetEdit/trigger mutation."""
    first_line = record.split("\n", 1)[0]
    stripped = first_line[: -len("<SR>")] if first_line.endswith("<SR>") else first_line
    stripped = _strip_li_prefix(stripped)
    m = _N_TOKEN_RE.match(stripped) or _N_TOKEN_RE.match(stripped.lstrip("[*"))
    return f"{m.group(1)}-{m.group(2)}" if m else None


# ---------------------------------------------------------------------------
# Batched-lane composition (gts-iz9i/gts-pi1s, stage `apt-lanes`)
#
# Pure text operations (decision 3: no network here) supporting the stage's
# own "Must not" clause -- materialise once, sync once, assert every scenario
# against that one convergence, rather than one Doc per scenario
# (tests/test_apt_corpus_check.py's own shape today, called out by name in
# the staged plan as the anti-pattern this stage's runner replaces). The
# runner that actually talks to a live Doc is tests/support/apt_lane_runner.py
# -- these two functions are its offline-testable halves.
# ---------------------------------------------------------------------------


def compose_corpora(named_texts: list[tuple[str, str]]) -> tuple[str, dict[str, tuple[int, int]]]:
    """Concatenates several corpora's own records (preamble dropped -- the
    composed text is decode-only scratch, never itself a golden) into ONE
    doc-less apt text. Returns (composed_text, ranges) where
    ranges[name] = (start, end) is that corpus's own records' 0-based,
    end-exclusive position in the composed record list -- what the batched
    runner uses to slice the ONE captured doc's records back into
    per-scenario chunks after one shared sync.

    A corpus containing a body-level `<TABLE...>` (APT v2 restriction: a
    table must be the doc's LAST content) must be last in `named_texts`, or
    this raises -- composing a table corpus ahead of a later one, or two
    table corpora, cannot round-trip (docs/interfaces/action-portable-text.md
    "v2 restriction -- table position")."""
    ranges: dict[str, tuple[int, int]] = {}
    all_records: list[str] = []
    for i, (name, text) in enumerate(named_texts):
        records = split_records(text)
        has_table = any(r.startswith("<TABLE") for r in records)
        if has_table and i != len(named_texts) - 1:
            raise ValueError(
                f"compose_corpora: {name!r} contains a body-level table but is "
                "not last in the list -- APT v2 requires a table to be the "
                "doc's last content."
            )
        start = len(all_records)
        all_records.extend(records)
        ranges[name] = (start, len(all_records))
    return "\n\n".join(all_records), ranges


def slice_records(text: str, start: int, end: int) -> str:
    """Inverse half of compose_corpora: re-joins captured records[start:end]
    (one of compose_corpora's own ranges) back into one corpus-shaped text
    the differ can compare against a single scenario's own golden."""
    return "\n\n".join(split_records(text)[start:end])


def _looks_like_plain_prose(record: str) -> bool:
    first_line = record.split("\n", 1)[0]
    stripped = first_line[: -len("<SR>")] if first_line.endswith("<SR>") else first_line
    stripped = _strip_li_prefix(stripped)
    if _N_TOKEN_RE.match(stripped) or _N_TOKEN_RE.match(stripped.lstrip("[*")):
        return False
    if _FIELD_LINE_RE.match(stripped):
        return False
    return True


def unannotated_records(text: str) -> list:
    """Returns the 0-based indices of records that carry a leading N token
    (i.e. are action paragraphs, not the annotations themselves) but whose
    immediately preceding record does not read as plain prose -- decision 9
    candidates missing their annotation. A corpus's first record has no
    preceding record at all, so it is always flagged if it is an action
    paragraph -- the annotation must come before it, i.e. it cannot BE the
    first record."""
    records = split_records(text)
    offenders = []
    for i, record in enumerate(records):
        first_line = record.split("\n", 1)[0]
        stripped = first_line[: -len("<SR>")] if first_line.endswith("<SR>") else first_line
        stripped = _strip_li_prefix(stripped)
        is_action = bool(_N_TOKEN_RE.match(stripped) or _N_TOKEN_RE.match(stripped.lstrip("[*")))
        if not is_action:
            continue
        if i == 0 or not _looks_like_plain_prose(records[i - 1]):
            offenders.append(i)
    return offenders
