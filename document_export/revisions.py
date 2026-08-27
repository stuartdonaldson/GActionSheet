"""Revision model: w:ins/w:del -> run.revision, block revision_summary, the
all_text/baseline_text/proposed_text trio, document.suggestion_groups and
document-wide views (contract §3, §13.1-13.3; stage docx-revisions, gts-9c8k).

Mirrors src/Procedure-Exporter.js's revision-summarisation functional region
one-for-one per the contract's "Standing constraint: architectural alignment
for back-port" -- makeTextRun_'s revision-object construction,
summarizeRevision_, buildViewText_, buildSuggestionGroups_ and
buildDocumentViews_'s deleted_text/proposed_additions/baseline_text/
proposed_text logic all have a same-shape counterpart below. The one
structural difference: w:ins/w:del wrap whole w:r elements (contract §3.1),
so there is no offset reconciliation to do and no suggestion_id to key on --
grouping is by (author, date) instead (contract §3.3), and possible_authors
is retired rather than ported (nothing left to guess once authorship is a
fact read directly off the markup).

structure.py owns the OOXML traversal that discovers a run's w:ins/w:del
ancestor chain (contract §3.1's "parser emits runs in OOXML document order
and each carries its own state") and calls into this module to turn that
chain into a revision object -- the traversal mechanics stay in
structure.py (which already owns "runs" per contract §7.1's module table),
the §3 classification rules live here.
"""
from __future__ import annotations

from document_export.schema import normalize_derived_text

_EXCLUDED_VIEW_SEMANTIC_STATES = ("historical", "editorial")


def classify_revision(tracked: tuple[dict, ...]) -> dict:
    """`tracked` is a run's w:ins/w:del ancestor chain, outer-to-inner, each
    entry `{"tag": "ins"|"del", "author": str|None, "date": str|None}`.

    Empty -> unchanged; per contract §3.3 ("each REVISION-BEARING run
    carries revision.author/date"), an unchanged run carries neither key.

    A single ins or del ancestor -> that state, author/date read off it.

    Both present ("w:del inside w:ins, or vice versa", contract §3.2) ->
    inserted_then_deleted. Author/date come from the innermost ancestor --
    the element that directly wraps the run's w:t/w:delText, i.e. the
    action that actually produced the run's current text representation
    (the golden fixture's own case nests w:del inside w:ins, so the
    innermost element is the del that determined the run ended up as
    deleted text)."""
    if not tracked:
        return {"state": "baseline", "change": "unchanged", "evidence": []}

    has_ins = any(a["tag"] == "ins" for a in tracked)
    has_del = any(a["tag"] == "del" for a in tracked)
    innermost = tracked[-1]

    if has_ins and has_del:
        change = "inserted_then_deleted"
        state = "proposed"
    elif has_ins:
        change = "inserted"
        state = "proposed"
    else:
        change = "deleted"
        state = "baseline"

    return {
        "state": state,
        "change": change,
        "author": innermost["author"],
        "date": innermost["date"],
        "evidence": [],
    }


def summarize_revision(runs: list[dict]) -> str:
    """Contract §3.2: a block containing any inserted_then_deleted run is
    always "mixed", regardless of what else the block contains."""
    changes = {r["revision"]["change"] for r in runs if r.get("kind") == "text"}
    if "inserted_then_deleted" in changes:
        return "mixed"
    has_ins = "inserted" in changes
    has_del = "deleted" in changes
    if has_ins and has_del:
        return "mixed"
    if has_ins:
        return "insertions"
    if has_del:
        return "deletions"
    return "unchanged"


def build_view_text(runs: list[dict], view: str, semantic_state: str) -> str:
    """Contract §3.2's table, `view` in {"all", "baseline", "proposed"}.
    Historical/editorial content is excluded from baseline/proposed (kept in
    all_text only) -- unchanged from the GAS exporter's buildViewText_.
    inserted_then_deleted is excluded from both baseline and proposed
    (contract §3.2: "never in the baseline and is not proposed"), kept only
    in all_text. Result is §13.5-normalized (NBSP -> space, vertical tab ->
    '\\n') since this always builds a derived/concatenated field, never
    runs[].text itself."""
    if view != "all" and semantic_state in _EXCLUDED_VIEW_SEMANTIC_STATES:
        return ""

    if view == "all":
        def keep(change: str) -> bool:
            return True
    elif view == "baseline":
        def keep(change: str) -> bool:
            return change in ("unchanged", "deleted")
    elif view == "proposed":
        def keep(change: str) -> bool:
            return change in ("unchanged", "inserted")
    else:
        raise ValueError(f"unknown view: {view!r}")

    joined = "".join(
        r["text"] for r in runs
        if r.get("kind") == "text" and keep(r["revision"]["change"])
    )
    return normalize_derived_text(joined)


def build_suggestion_groups(units: list[dict]) -> list[dict]:
    """Contract §3.3: grouped by (author, date) rather than the Docs
    suggestion_id, which has no OOXML equivalent. `possible_authors` is
    retired -- nothing left to guess. Every revision-bearing run
    (inserted, deleted, or inserted_then_deleted) contributes, mirroring
    buildSuggestionGroups_'s walk over every run carrying suggestion
    evidence. Runs carry no `location` (stage docx-structure, gts-pmga's
    Found note); the group's first/last location is its blocks' instead --
    the closest available granularity."""
    groups: dict[tuple[str | None, str | None], dict] = {}

    for unit in units:
        for block in unit["blocks"]:
            for run in block.get("runs", []):
                if run.get("kind") != "text":
                    continue
                rev = run["revision"]
                if rev["change"] == "unchanged":
                    continue
                key = (rev.get("author"), rev.get("date"))
                g = groups.setdefault(key, {
                    "run_count": 0,
                    "block_ids": {},
                    "first_location": block["location"],
                    "last_location": block["location"],
                })
                g["run_count"] += 1
                g["block_ids"][block["id"]] = True
                g["last_location"] = block["location"]

    return [
        {
            "author": author,
            "date": date,
            "run_count": g["run_count"],
            "block_ids": list(g["block_ids"].keys()),
            "first_location": g["first_location"],
            "last_location": g["last_location"],
        }
        for (author, date), g in groups.items()
    ]


def build_document_views(units: list[dict], include_whole_document_views: bool) -> dict:
    """Contract §13.1/§13.2 top-level views. `deleted_text`/
    `proposed_additions` are always included (small extracts, no dedup
    concern); `baseline_text`/`proposed_text` are opt-in whole-document
    reconstructions. inserted_then_deleted runs contribute to neither
    extract, for the same reason they contribute to neither reconstruction
    (contract §3.2: "never in the baseline and is not proposed") -- a
    deliberate scoping call, not an oversight; flag for gts-klp8 if the
    differential oracle finds a consumer needs them surfaced some other
    way."""
    blocks = [b for u in units for b in u["blocks"]]

    deleted_text = normalize_derived_text("".join(
        r["text"]
        for b in blocks
        for r in b.get("runs", [])
        if r.get("kind") == "text" and r["revision"]["change"] == "deleted"
    ))
    proposed_additions = normalize_derived_text("".join(
        r["text"]
        for b in blocks
        for r in b.get("runs", [])
        if r.get("kind") == "text" and r["revision"]["change"] == "inserted"
    ))

    views = {"deleted_text": deleted_text, "proposed_additions": proposed_additions}

    if include_whole_document_views:
        views["baseline_text"] = "\n".join(
            t for t in (block_text(b, "baseline") for b in blocks) if t
        )
        views["proposed_text"] = "\n".join(
            t for t in (block_text(b, "proposed") for b in blocks) if t
        )

    return views


def block_text(block: dict, which: str = "all") -> str:
    """§13.3 fallback accessor mirrored from blockBaselineText_/
    blockProposedText_: read the named view field when present (revision
    activity), else the canonical `text` field (unchanged block). Public --
    also used by comments.py (gts-ipot) to read a block's display text
    without assuming `text` is always present."""
    key = f"{which}_text"
    if key in block:
        return block[key]
    return block.get("text", "")
