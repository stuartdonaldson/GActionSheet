"""
test_insert_tracker_table_route.py — gts-ljc9 (twin-ticket [TST] for gts-6vzm),
ADR-0030 (knowledge-base/adr/0030-addon-entry-points-proxy-through-webapp.md).

Entry-point coverage for the new WEBAPP_SECRET-gated `insert_tracker_table` doPost
route — the document-mutation half of ADR-0030 not already covered by
test_force_refresh_route.py's `sync_document` route tests.

Authored against the frozen pre-code contract on the twin [IMP] bead gts-6vzm,
not against src/WebApp.js (no-shared-context, project CLAUDE.md §Twin-ticket):

    request : { secret, action: 'insert_tracker_table', docId }
    call    : insertTrackerTable(docId)
    logs    : tracker.insert.complete {docId, rowCount}  (table rendered)
              tracker.skip           {docId, ...}         (already matched — not
                                                            exercised by this route
                                                            test; see
                                                            test_tracker_view_only.py)
    response: { ok, docId, result }   -- result is always null (no return value)
    missing docId -> { ok:false, error:'docId required' }, no scan/insert

The oracle is specifiable (an artifact-truth tracker row plus a JSON field), so
this stage is test-first per the project's oracle-ordering rule.
"""
import pytest

from scn.ai import ai
from scn.engine import CheckpointKind
from scn.session import FixtureError, ScenarioSession
from scn.surfaces import TrackerReader
from tests.helpers.download import download_docx
from tests.helpers.gas_log import assert_log, clear_logs

STEP = CheckpointKind.STEP

_ROUTE = "insert_tracker_table"


@pytest.fixture
def scn(settings, request):
    # request=request wires JUnit ac.*/ep.* emission to this test node (T24).
    s = ScenarioSession.new_doc(settings, request=request)
    yield s
    s.close()


def _post_insert_tracker_table(scn, settings, **extra) -> dict:
    """POST the secret-gated insert_tracker_table route.

    scn._post_route sends testToken; this is a production route behind the
    WEBAPP_SECRET gate, so the payload is built here (same shape as
    test_force_refresh_route.py's _post_sync_document).
    """
    payload = {"secret": settings["webappSecret"], "action": _ROUTE}
    payload.update(extra)
    return scn._post(payload)


def _anchored_action(scn):
    """Seed one floating action and sync it so it carries a globalId.

    insertTrackerTable() reads floating actions straight from the doc plus
    the ActionSheet rows — an anchored (synced) action is what the tracker
    table is built from.
    """
    seed = ai(action="insert_tracker_table route seeded floating action")
    scn.append_paragraph(seed.as_text())
    scn.sync()
    return seed


# ---------------------------------------------------------------------------
# AC (1): the route reaches insertTrackerTable() and renders a real table.
# ---------------------------------------------------------------------------

def test_insert_tracker_table_route_renders_tracker(scn, settings, gas_log_dir):
    """{secret, action:'insert_tracker_table', docId} must render the in-doc
    tracker table for an anchored action, proving the WebApp route reaches
    insertTrackerTable(docId) (gts-6vzm)."""
    if not settings.get("webappSecret"):
        pytest.skip("local.settings.json missing webappSecret — cannot drive the secret gate")

    seed = _anchored_action(scn)

    fence = clear_logs(gas_log_dir) if gas_log_dir else 0.0
    resp = _post_insert_tracker_table(scn, settings, docId=scn.doc_id)

    assert resp.get("ok") is True, f"[6vzm] insert_tracker_table expected ok:true, got {resp!r}"
    assert resp.get("docId") == scn.doc_id, (
        f"[6vzm] response must echo the docId it inserted for, got {resp!r}"
    )
    assert resp.get("result") is None, (
        f"[6vzm] insertTrackerTable() has no return value -- result must be null, got {resp!r}"
    )

    if gas_log_dir:
        assert_log(
            gas_log_dir, fence,
            lambda e: e.get("tag") == "tracker.insert.complete"
            and e.get("data", {}).get("docId") == scn.doc_id
            and (e.get("data", {}).get("rowCount") or 0) >= 1,
            "[6vzm insert_tracker_table] expected tracker.insert.complete with rowCount>=1",
        )

    # Artifact truth: the rendered tracker table must actually contain the
    # seeded action, not just an ok:true HTTP ack.
    docx = download_docx(scn.doc_id)
    tracker_rows = TrackerReader().read(docx, scn.doc_id)
    assert any(row.action == seed.action for row in tracker_rows), (
        f"[6vzm insert_tracker_table] seeded action not found in rendered tracker table; "
        f"rows: {[r.action for r in tracker_rows]!r}"
    )
    scn.checkpoint(STEP)


# ---------------------------------------------------------------------------
# Negatives (T-series): the route must refuse rather than mis-insert.
# ---------------------------------------------------------------------------

def test_insert_tracker_table_route_requires_doc_id(scn, settings):
    """An omitted docId must be refused with a named error, never silently
    dispatched into insertTrackerTable('') (mirrors gts-366c AC-5 for
    sync_document).

    ScenarioSession._post raises FixtureError for any response carrying an
    `error` key, so the refusal surfaces as that exception rather than a dict.
    """
    if not settings.get("webappSecret"):
        pytest.skip("local.settings.json missing webappSecret — cannot drive the secret gate")

    with pytest.raises(FixtureError, match="docId required"):
        _post_insert_tracker_table(scn, settings)


def test_insert_tracker_table_route_rejects_a_bad_secret(scn):
    """The route sits below the WEBAPP_SECRET gate: a wrong secret must be
    rejected before any doc scan/insert runs (mirrors gts-366c AC-6 for
    sync_document).

    doPost's gate answers with a structured JSON body {ok:false, error:'unauthorized'}
    (src/WebApp.js, gts-pl2k), so a wrong secret fails on the FIRST attempt
    instead of being misdiagnosed as GAS deployment-propagation lag.
    """
    with pytest.raises(FixtureError, match="unauthorized"):
        scn._post({
            "secret": "not-the-webapp-secret",
            "action": _ROUTE,
            "docId": scn.doc_id,
        })
