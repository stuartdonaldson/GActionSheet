"""
test_chip_preview.py — ADR-0017 Phase 1 anonymous chip-preview notice page.

Twin of GTaskSheet-mus0 (doGet ?cmd=preview&docId&ain). Validates the
disclosure boundary: the rendered HTML must show only non-confidential
metadata (doc name, AI-N, status, doc-edit link) and must NEVER include the
action text. Also covers the non-leaking not-found variant for an unknown
globalId.

No-shared-context: assertions are written against ADR-0017
(knowledge-base/adr/0017-chip-link-anonymous-identity.md) and the pre-code
contract on GTaskSheet-mus0, not the GAS implementation.
"""
import pytest

from scn.ai import ai
from scn.session import ScenarioSession


@pytest.fixture
def scn(settings, request):
    s = ScenarioSession.new_doc(settings, request=request)
    yield s
    s.close()


def test_chip_preview_notice_discloses_only_metadata(scn):
    secret_text = "CONFIDENTIAL chip-preview disclosure check rz5b"
    seed = ai(action=secret_text)
    scn.append_paragraph(seed.as_text())
    scn.sync()

    rows = scn.find_sheet_actions()
    match = next((r for r in rows if secret_text in (r.action or "")), None)
    assert match is not None, f"seeded action not found after sync; rows={rows}"
    action_id = match.action_id
    assert action_id, f"synced action has no AI-N id: {match}"

    docdata = (scn._post_fixture("get_docdata_row").get("data") or {}).get("row") or {}
    doc_name = docdata.get("docName") or ""

    html = scn.fetch_preview_html(action_id)

    # Core security invariant (T-negative): action text never disclosed.
    assert secret_text not in html, f"preview leaked action text: {html!r}"

    # Safe fields present.
    assert action_id in html, f"preview missing action id {action_id!r}: {html!r}"
    assert (match.status or "Open") in html, f"preview missing status: {html!r}"
    assert f"/document/d/{scn.doc_id}/edit" in html, f"preview missing doc link: {html!r}"
    if doc_name:
        assert doc_name in html, f"preview missing doc name {doc_name!r}: {html!r}"


def test_chip_preview_notice_unknown_action_is_non_leaking(scn):
    html = scn.fetch_preview_html("AI-999999")

    assert "not found" in html.lower(), f"expected non-leaking not-found page: {html!r}"
    assert scn.doc_id not in html, f"unknown-action preview should not echo docId: {html!r}"
