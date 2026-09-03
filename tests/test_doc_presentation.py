"""Doc-side presentation assertions (gts-dxgo, stage `apt-presentation`).

Rule 8's grammar spec cannot express what a flush actually *renders* -- the
assignee's PERSON chip, the ACT-N: header's own chip-badge link, and the
status icon are all system-applied presentation (ADR-0027 rule 8's
principle, restated by docs/interfaces/action-portable-text.md's "Status
icon" section), not stored author intent a text grammar can capture. This
file asserts their presence directly, per record, read independently via
the stage-1 parser (tests/helpers/doc_inspect) -- never via GAS scan output,
so it stays on the oracle's own track (twin-track independence).

Runs against a disposable, force-flushed copy of the reference corpus
(gts-p150's materialize_reference_corpus), never the shared canonical
referenceDocId. A force flush is required to observe the status icon at
all -- see gts-3koi (found while authoring this file): decodeAptToRequests
(the decode/repair path) never inserts the status-icon image, only a real
_buildFlushRequests call does, so the canonical Doc -- repaired via decode
only, never re-flushed since -- currently carries none. That gap is
decodeAptToRequests's, not this test's; gts-3koi tracks it separately.
"""
import pytest

from tests.helpers import docx_build
from tests.helpers.doc_inspect import floating_actions, load_doc
from tests.helpers.download import download_docx
from tests.helpers.reference_corpus import materialize_reference_corpus

# ACT-9 (gts-jxrw): a bare token, no assignee, no body -- by design it gets
# no PERSON chip, since none was ever typed. Every other established token
# in the reference corpus carries one.
NO_CHIP_BY_DESIGN = {"ACT-9"}


def _label(a):
    return a.token or f"body_index={a.body_index}"


def missing_presentation_elements(a) -> list[str]:
    """The three presentation elements a flush renders on an established
    action, and what's missing from ``a`` -- named, not just counted, so a
    failure says exactly what to look at (AC2)."""
    missing = []
    if a.token not in NO_CHIP_BY_DESIGN and a.assignee_source != "chip":
        missing.append("person chip")
    if not a.token_linked:
        missing.append("ACT-N: link run")
    if not a.has_status_icon:
        missing.append("status icon")
    return missing


@pytest.fixture(scope="module")
def reference_actions(settings, request):
    scn = materialize_reference_corpus(settings, request=request)
    resp = scn._post({
        "secret": settings["webappSecret"], "action": "sync_document",
        "docId": scn.doc_id, "force": True,
    })
    assert resp.get("ok") is True, f"force flush of the materialized corpus failed: {resp!r}"
    return floating_actions(load_doc(download_docx(scn.doc_id)))


@pytest.fixture
def established(reference_actions):
    """Fully-established actions -- tokened and link-headed. A pending
    trigger or a rule-6 unparseable paragraph carries none of these three
    elements by construction and is out of this file's scope."""
    return [a for a in reference_actions if a.token and a.token_linked]


def test_every_established_action_carries_its_presentation_elements(established):
    assert established, "expected at least one established action in the reference doc"
    problems = [
        f"{_label(a)}: missing {', '.join(missing)}"
        for a in established
        for missing in [missing_presentation_elements(a)]
        if missing
    ]
    assert not problems, "\n" + "\n".join(problems)


def test_act9_is_the_documented_no_chip_exception(established):
    r = next((a for a in established if a.token == "ACT-9"), None)
    assert r is not None, "ACT-9 (gts-jxrw bare-token case) not found among established actions"
    assert not r.assignee_email, "ACT-9 must carry no assignee -- none was ever typed"
    assert r.token_linked and r.has_status_icon, (
        "ACT-9 is only exempt from the PERSON chip, not from the other two elements"
    )


# ---------------------------------------------------------------------------
# AC3 -- proven to fail. Each case reproduces one specific missing-element
# shape offline (docx_build), independent of the live doc, and shows
# missing_presentation_elements names exactly the element that's absent.
# ---------------------------------------------------------------------------

def _parse_one(blocks):
    (action,) = floating_actions(docx_build.load(docx_build.build_docx(blocks)))
    return action


def test_proven_to_fail_on_an_unlinked_header():
    """The 2026-08-29 shape itself: a scanned-but-never-flushed ACT-N: whose
    header carries no chip-badge link."""
    a = _parse_one([
        docx_build.para(
            docx_build.image(),
            docx_build.text("ACT-1: "),
            docx_build.chip("jane@example.com", "Jane"),
            docx_build.text(" do the thing (Open)"),
        ),
    ])
    assert a.token == "ACT-1" and a.assignee_email and a.has_status_icon
    assert missing_presentation_elements(a) == ["ACT-N: link run"]


def test_proven_to_fail_on_a_missing_person_chip():
    a = _parse_one([
        docx_build.para(
            docx_build.image(),
            docx_build.link("ACT-1: ", "https://example.com/preview"),
            docx_build.text("jane@example.com do the thing (Open)"),
        ),
    ])
    assert a.token == "ACT-1" and a.token_linked and a.has_status_icon
    assert a.assignee_source == "text", "fixture must reproduce a text-only, non-chip assignee"
    assert missing_presentation_elements(a) == ["person chip"]


def test_proven_to_fail_on_a_missing_status_icon():
    a = _parse_one([
        docx_build.para(
            docx_build.link("ACT-1: ", "https://example.com/preview"),
            docx_build.chip("jane@example.com", "Jane"),
            docx_build.text(" do the thing (Open)"),
        ),
    ])
    assert a.token == "ACT-1" and a.token_linked and a.assignee_email
    assert missing_presentation_elements(a) == ["status icon"]
