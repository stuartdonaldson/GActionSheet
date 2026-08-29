"""The independent parser run against the canonical ADR-0027 reference Doc (gts-e5cl).

Read-only: downloads the reference Doc's .docx export and reports what the
grammar says is in it.  It calls no GAS route and mutates nothing, so it is
safe to run against the canonical Doc at any time — which matters, because
before 2026-08-29 no test in the suite touched this Doc at all.

The count assertion is the oracle's headline claim: the reference Doc holds 21
established floating actions, independently of whether a sync ever saw them.
"""
import pytest

from tests.helpers.doc_inspect import floating_actions, load_doc
from tests.helpers.download import download_docx

REFERENCE_ACTION_COUNT = 21


@pytest.fixture(scope="module")
def reference_actions(settings):
    doc_id = settings.get("referenceDocId")
    if not doc_id:
        pytest.skip("referenceDocId not set in local.settings.json")
    return floating_actions(load_doc(download_docx(doc_id)))


def test_reference_doc_holds_21_floating_actions(reference_actions):
    tokens = [a.token for a in reference_actions if a.token]
    assert len(tokens) == REFERENCE_ACTION_COUNT, f"tokens={tokens}"
    assert len(set(tokens)) == REFERENCE_ACTION_COUNT, f"duplicate tokens: {tokens}"


def test_every_established_token_carries_its_link_header(reference_actions):
    """A token whose chip-badge link is missing is reported, not dropped.

    Red on the state the plan describes (13 records with no link header), which
    stage `apt-repair` repairs and stage `apt-lane-guards` guards against.
    """
    unlinked = [a.token for a in reference_actions if a.token and not a.token_linked]
    assert unlinked == [], f"present-but-unlinked tokens: {unlinked}"


def test_no_action_is_left_pending(reference_actions):
    """Every trigger in the reference Doc has been assigned a token."""
    pending = [a.raw_text[:60] for a in reference_actions if a.pending]
    assert pending == [], f"unassigned triggers: {pending}"


def test_unparseable_paragraphs_are_reported_with_a_usable_diagnostic(reference_actions):
    """ADR-0027 rule 6.

    The corpus deliberately carries the pipe-form paragraph
    (`unparseable-reporting`, gts-thwh), so the assertion is that each such
    paragraph is *reported* with its body-child index and leading text — not
    that none exists.
    """
    reported = [a for a in reference_actions if a.error]
    assert reported, "expected the corpus's deliberate rule-6 paragraph to be reported"
    for a in reported:
        assert a.body_index >= 0
        assert a.raw_text.strip()
        assert a.token is None
