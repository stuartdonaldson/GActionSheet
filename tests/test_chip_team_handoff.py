"""
test_chip_team_handoff.py — gts-79dw.4.9

Targeted hardening for the chip -> verified-portal handoff added to
doGet ?cmd=preview (_handlePreviewNotice / _renderPreviewNotice, src/WebApp.js).

Implementation choice (a) from the bd pre-code contract: ?cmd=preview itself
gains a "Sign in for the full view" CTA linking to the verified per-document
view (View B, gts-79dw.4.13) on the static portal frontend, carrying the
docId and the DocData.teamId resolved via _readDocDataRow (NOT
_walkFolderForTeam). A docId with no DocData.teamId degrades to the plain
anonymous notice -- no CTA, no error.

Twin-ticket: [TST] gts-79dw.4.9.1 (paired with this [IMP] bead).
Regression guard for the existing Phase-1 anonymous preview lives in
tests/test_chip_preview.py and is not duplicated here.
"""
import pytest

from scn.ai import ai
from scn.session import ScenarioSession
from tests.helpers.gas_log import assert_log as _assert_log
from tests.helpers.gas_log import clear_logs

_VERIFIED_TEAM_PORTAL_BASE = "https://nuuc-it.github.io/Static/pub/AS/"


@pytest.fixture
def scn(settings, request):
    s = ScenarioSession.new_doc(settings, request=request)
    yield s
    s.close()


def _seed_synced_action(scn):
    seed = ai(action="chip team-handoff coverage gts-79dw.4.9")
    scn.append_paragraph(seed.as_text())
    scn.sync()
    rows = scn.find_sheet_actions()
    match = next((r for r in rows if r.action_id), None)
    assert match is not None, f"seeded action not found after sync; rows={rows}"
    return match.action_id


def test_chip_preview_offers_view_b_cta_when_team_resolved(scn, gas_log_dir):
    action_id = _seed_synced_action(scn)

    team_id = "TestChipHandoffTeam"
    scn._post_fixture("set_docdata_row", {"teamId": team_id})

    fence = clear_logs(gas_log_dir)
    html = scn.fetch_preview_html(action_id)

    expected_url = (
        f"{_VERIFIED_TEAM_PORTAL_BASE}?doc={scn.doc_id}&amp;team={team_id}"
    )
    assert expected_url in html or expected_url.replace("&amp;", "&") in html, (
        f"expected View B CTA URL for docId={scn.doc_id} teamId={team_id} "
        f"not found in preview HTML: {html!r}"
    )
    assert "Sign in for the full view" in html, f"missing CTA copy: {html!r}"

    _assert_log(
        gas_log_dir, fence,
        lambda e: e.get("tag") == "webapp.team.handoff"
        and e.get("data", {}).get("docId") == scn.doc_id
        and e.get("data", {}).get("teamId") == team_id
        and e.get("data", {}).get("route") == "docview-cta",
        "webapp.team.handoff docview-cta",
    )


def test_chip_preview_falls_back_when_no_docdata_team(scn, gas_log_dir):
    action_id = _seed_synced_action(scn)

    # Explicitly clear any teamId DocData may already carry for this doc.
    scn._post_fixture("set_docdata_row", {"teamId": ""})

    fence = clear_logs(gas_log_dir)
    html = scn.fetch_preview_html(action_id)

    assert "Sign in for the full view" not in html, (
        f"CTA should not render with no resolved teamId: {html!r}"
    )
    assert _VERIFIED_TEAM_PORTAL_BASE not in html, (
        f"portal URL leaked with no resolved teamId: {html!r}"
    )

    _assert_log(
        gas_log_dir, fence,
        lambda e: e.get("tag") == "webapp.team.handoff"
        and e.get("data", {}).get("docId") == scn.doc_id
        and e.get("data", {}).get("teamId") == ""
        and e.get("data", {}).get("route") == "anonymous-preview-fallback",
        "webapp.team.handoff anonymous-preview-fallback",
    )
