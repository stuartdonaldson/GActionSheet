"""apt_lib.py — shared pure-Python core for Action Portable Text (APT) tooling
(gts-snub, gts-x9un, gts-ndb8; staged plan knowledge-base/staging/apt-testing.md,
stages `apt-differ` and `apt-scenarios`).

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
    body = _N_TOKEN_MARKUP_RE.sub(
        lambda m: f"{m.group(1) or ''}{m.group(2)}-#:", body, count=1
    )
    body = _N_AIN_PARAM_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}-#", body)
    return prefix + body


_MARKUP_RE = re.compile(r"\*\*|\*|_|\\(.)")
_LINK_RE = re.compile(r"\[((?:[^\[\]\\]|\\.)*)\]\(((?:[^()\\]|\\.)*)\)")
_FIELD_LINE_RE = re.compile(r"^([A-Z][A-Za-z ]*):\s?(.*)$")


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


def _classify_record_pair(index: int, golden: str, capture: str) -> DiffEntry | None:
    norm_g, norm_c = _normalize_n(golden), _normalize_n(capture)
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
    scenario shape the batched runner exists to avoid."""
    path = pathlib.Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    for key in ("input", "mutation", "expected"):
        if key not in raw:
            raise ValueError(f"{path}: scenario triple missing required key {key!r}")
    if not isinstance(raw["mutation"], dict) or "kind" not in raw["mutation"]:
        raise ValueError(f"{path}: 'mutation' must be an object with a 'kind'")
    return Scenario(
        name=raw.get("name") or path.stem.removesuffix(".scenario"),
        input_corpus=raw["input"],
        mutation=raw["mutation"],
        expected_corpus=raw["expected"],
        serves=list(raw.get("serves") or []),
        batch=raw.get("batch"),
    )


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
