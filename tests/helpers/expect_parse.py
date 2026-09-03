"""Sparse expected-parse annotation (gts-gkcy, stage `apt-presentation`).

A troubleshooting aid, not a grammar or coverage requirement: a small JSON
map from a hard-to-reason-about record's token to the *subset* of
``doc_inspect.ParsedAction`` fields the parser is expected to produce for
it. Deliberately sparse and optional (AC1/AC4) -- a record with no entry is
not itself evidence of anything, and an entry names only the fields worth
pinning down, not every field on the dataclass.

MUST NOT be promoted into a per-item convention or a user-facing feature
(stage `apt-presentation`'s own constraint, shared with gts-dxgo) -- this
stays a debugging aid a human reads when a lane goes red, not a new corpus
grammar. It is intentionally a sidecar file, not new syntax inside the APT
corpus format itself: action-portable-text.md's own record grammar (blank
line separated paragraphs) has no room for a per-record comment without
breaking round-trip, so the annotation lives beside the corpus, not in it.
"""
import json
from pathlib import Path


def load_expect_parse(path) -> dict:
    """Returns ``{}`` if the sidecar file does not exist -- absence is never
    an error (AC4): a corpus with no annotation file, or a record missing
    from one that exists, is simply unchecked, not flagged."""
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def diff_expect_parse(action, expected: dict) -> list[str]:
    """Compares only the keys named in ``expected`` against ``action``
    (sparse, AC1) -- any ``ParsedAction`` field not mentioned is left alone.
    Returns human-readable "expected vs actual" mismatches (AC3), empty if
    every named field matched."""
    problems = []
    for field_name, want in expected.items():
        got = getattr(action, field_name, "<no such ParsedAction field>")
        if got != want:
            problems.append(f"{field_name}: expected {want!r}, got {got!r}")
    return problems
