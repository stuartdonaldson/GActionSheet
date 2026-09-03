"""Pristine-restore materialisation of the ADR-0027 reference corpus (gts-p150).

Every APT lane before this bead either called `ScenarioSession.new_doc()`
(a blank doc, no reference-corpus content at all) or read the shared
canonical reference Doc (`settings['referenceDocId']`) directly — the one
Doc every other stage of `knowledge-base/staging/apt-oracle.md` repairs and
guards by hand, and which stage `apt-repair` found drifts a little more with
every flush. A lane that wants to *start* from the reference corpus (rather
than read the live shared Doc, or build its own paragraphs by hand) needs a
disposable copy, not the canonical one.

`materialize_reference_corpus()` decodes the checked-in golden
(`tests/fixtures/action-reference.apt.txt`, the same file `apt.py bless`
writes) into a fresh doc via `new_doc()` + `decode_reference_document`, then
verifies — independently of the sheet, via the same `doc_inspect` grammar
parse the oracle uses — that every token the golden declares actually landed
before handing the doc back. A decode that silently drops or truncates
content raises `IncompleteMaterialization` instead of returning a
partially-seeded doc for a lane to unknowingly build assertions on top of.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "scripts"))
import apt_lib  # noqa: E402 -- path insert must run first

from scn.session import ScenarioSession
from tests.helpers.doc_inspect import floating_actions, load_doc
from tests.helpers.download import download_docx

_APT_PATH = pathlib.Path(__file__).parent.parent / "fixtures" / "action-reference.apt.txt"


class IncompleteMaterialization(RuntimeError):
    """The decoded doc does not hold every token the golden corpus declares."""


def golden_token_count(apt_text: str | None = None) -> int:
    """Number of distinct `ACT-N`/`AI-N` tokens the golden corpus declares.

    Delegates to `apt_lib.split_records`/`record_token` (the same record
    grammar `apt.py bless`/`diff` use) rather than re-deriving it, so a
    future re-bless that adds, removes, or renumbers a record cannot desync
    this guard from the corpus it is checking. The deliberate rule-6
    paragraph (`ACT-77 | someone | do the thing`) carries no such token and
    is correctly excluded.
    """
    text = apt_text if apt_text is not None else _APT_PATH.read_text(encoding="utf-8")
    tokens = [apt_lib.record_token(r) for r in apt_lib.split_records(text)]
    return len([t for t in tokens if t])


def materialize_reference_corpus(settings: dict, *, request=None, sync: bool = True) -> ScenarioSession:
    """Decode the golden reference corpus into a fresh, disposable doc.

    Returns the live `ScenarioSession` (caller owns `.close()`, or passes
    `request=` to a pytest fixture so `new_doc()`'s own finalizer trashes it).
    Raises `IncompleteMaterialization` — and trashes the partial doc itself,
    since no caller received it to clean up — if the decode did not produce
    every token the golden declares.
    """
    apt_text = _APT_PATH.read_text(encoding="utf-8")
    expected = golden_token_count(apt_text)

    scn = ScenarioSession.new_doc(settings, request=request)
    resp = scn._post_fixture("decode_reference_document", {"apt": apt_text})
    if not (resp.get("data") or {}).get("ok"):
        scn._deferred_trash()
        raise IncompleteMaterialization(
            f"decode_reference_document failed against fresh doc {scn.doc_id}: {resp}"
        )

    actions = floating_actions(load_doc(download_docx(scn.doc_id)))
    tokens = [a.token for a in actions if a.token]
    if len(tokens) != expected or len(set(tokens)) != expected:
        scn._deferred_trash()
        raise IncompleteMaterialization(
            f"materialized doc {scn.doc_id} holds {len(tokens)} tokened action(s) "
            f"(want {expected}, from {_APT_PATH.name}): {sorted(tokens)}"
        )

    if sync:
        scn.sync()
    return scn
