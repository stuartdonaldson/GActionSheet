"""tests/helpers/reference_corpus.py — gts-p150, stage `apt-lane-guards`.

Covers the bead's four ACs directly:
  (1) materialize_reference_corpus() decodes the golden into a fresh doc
      distinct from the shared canonical reference Doc.
  (2) calling it twice in one session produces equivalent starting state
      (idempotency, T-series).
  (3) an existing APT lane switched onto it — done in
      test_adr0027_reference_document.py's `reference` fixture, not
      re-demonstrated here.
  (4) it fails loudly (raises, and trashes the partial doc) rather than
      handing back a doc that didn't fully materialise.
"""
import pytest

from tests.helpers.doc_inspect import floating_actions, load_doc
from tests.helpers.download import download_docx
from tests.helpers.reference_corpus import (
    IncompleteMaterialization,
    golden_token_count,
    materialize_reference_corpus,
)


def test_golden_token_count_matches_the_known_corpus():
    """Sanity check on the helper itself, offline — no network."""
    assert golden_token_count() == 21


def test_materialize_yields_a_fresh_doc_distinct_from_the_canonical_one(settings, request):
    scn = materialize_reference_corpus(settings, request=request)
    reference_doc_id = settings.get("referenceDocId")
    assert scn.doc_id, "materialized session has no doc_id"
    if reference_doc_id:
        assert scn.doc_id != reference_doc_id, (
            "materialize_reference_corpus must not hand back the shared canonical "
            "reference Doc — every other stage of apt-oracle.md repairs and guards "
            "that Doc by hand; a lane writing to it defeats the point of this fixture"
        )
    actions = floating_actions(load_doc(download_docx(scn.doc_id)))
    tokens = [a.token for a in actions if a.token]
    assert len(tokens) == golden_token_count() == len(set(tokens))
    scn.close()


def test_materialize_is_idempotent_across_two_calls_in_one_session(settings, request):
    """Re-running the fixture twice in one session produces equivalent
    starting state (AC2) — same token set and the same content on a
    representative record, even though each call gets its own fresh doc."""
    first = materialize_reference_corpus(settings, request=request)
    second = materialize_reference_corpus(settings, request=request)
    try:
        assert first.doc_id != second.doc_id, "each call must materialise its own doc"

        first_actions = {
            a.token: a for a in floating_actions(load_doc(download_docx(first.doc_id))) if a.token
        }
        second_actions = {
            a.token: a for a in floating_actions(load_doc(download_docx(second.doc_id))) if a.token
        }
        assert set(first_actions) == set(second_actions)

        for token in ("ACT-1", "ACT-19"):
            a1, a2 = first_actions[token], second_actions[token]
            assert a1.assignee_email == a2.assignee_email
            assert a1.action_text == a2.action_text
            assert a1.status == a2.status
    finally:
        first.close()
        second.close()


def test_materialize_fails_loudly_on_an_incomplete_decode(settings, request, monkeypatch):
    """AC4: a decode that lands fewer tokens than the golden declares must
    raise — not hand back a partially-seeded doc for a lane to unknowingly
    build assertions on top of. Forced by inflating the expected count
    rather than corrupting the golden or the decode route, since the decode
    path itself has no known way to reproduce a real short landing on
    demand; this proves the completeness *check* fires, which is the part
    this bead owns."""
    import tests.helpers.reference_corpus as reference_corpus

    monkeypatch.setattr(reference_corpus, "golden_token_count", lambda *a, **k: 9999)

    with pytest.raises(IncompleteMaterialization, match=r"holds \d+ tokened action"):
        materialize_reference_corpus(settings, request=request)
