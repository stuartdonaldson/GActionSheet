"""
test_force_refresh_route.py — gts-gssn (stage `act-force-refresh`,
knowledge-base/staging/apt-oracle.md).

Entry-point coverage for the WEBAPP_SECRET-gated `sync_document` doPost route —
the only way to reach syncDocument(docId, {force:true}) without a browser.

Authored against the frozen pre-code contract on the twin [IMP] bead gts-366c,
not against src/WebApp.js (no-shared-context, project CLAUDE.md §Twin-ticket):

    request : { secret, action: 'sync_document', docId, force }
    call    : syncDocument(docId, {force: force === true})
    logs    : sync.forceFlush {docId, count}  (only when force flushed >=1)
              sync.complete   {docId, upserted, updated, forced}  (always)
    response: { ok, docId, forced, result }
    force is strictly === true; absent / false / non-boolean -> forced:false
    missing docId -> { ok:false, error:'docId required' }, no sync

The oracle is specifiable (a log tag plus a JSON field), so this stage is
test-first per the project's oracle-ordering rule.

Why the log line and not just the response: on an already-converged doc a plain
sync is a no-op for every item, so `ok:true` proves nothing. sync.forceFlush
{count>=1} is the only observable evidence that force bypassed the diff — the
same argument test_menu_entry_points.py makes for the Docs-menu call-site
(gts-t78c AC-5), applied to the route.
"""
import pytest

from scn.ai import ai
from scn.engine import CheckpointKind
from scn.session import FixtureError, ScenarioSession
from tests.helpers.gas_log import assert_log, assert_no_log, clear_logs

STEP = CheckpointKind.STEP

_ROUTE = "sync_document"


@pytest.fixture
def scn(settings, request):
    # request=request wires JUnit ac.*/ep.* emission to this test node (T24).
    s = ScenarioSession.new_doc(settings, request=request)
    yield s
    s.close()


def _post_sync_document(scn, settings, **extra) -> dict:
    """POST the secret-gated sync_document route.

    scn._post_route sends testToken; this is a production route behind the
    WEBAPP_SECRET gate, so the payload is built here (same shape as
    tests/test_b7_write_routes.py's direct secret-gated calls).
    """
    payload = {"secret": settings["webappSecret"], "action": _ROUTE}
    payload.update(extra)
    return scn._post(payload)


def _converged_doc(scn):
    """Seed one floating action and sync until doc and sheet agree.

    After this, a second plain sync has nothing to flush for the item — which
    is precisely the state in which force must still re-render it.
    """
    seed = ai(action="sync_document route converged floating action")
    scn.append_paragraph(seed.as_text())
    scn.sync()
    return seed


# ---------------------------------------------------------------------------
# AC (1): the route reaches the force-flush path.
# ---------------------------------------------------------------------------

def test_sync_document_route_force_flushes_converged_action(scn, settings, gas_log_dir):
    """{secret, action:'sync_document', docId, force:true} must re-render a
    converged action paragraph, proving the WebApp route reaches
    syncDocument(docId, {force:true}) (gts-366c AC-1/AC-2/AC-3)."""
    if not gas_log_dir:
        pytest.skip("gas_log_dir not configured — force-flush proof requires GAS log access")
    if not settings.get("webappSecret"):
        pytest.skip("local.settings.json missing webappSecret — cannot drive the secret gate")

    _converged_doc(scn)

    fence = clear_logs(gas_log_dir)
    resp = _post_sync_document(scn, settings, docId=scn.doc_id, force=True)

    assert resp.get("ok") is True, f"[gssn] sync_document force:true expected ok:true, got {resp!r}"
    assert resp.get("forced") is True, (
        f"[gssn] response must echo forced:true (gts-366c AC-3), got {resp!r}"
    )
    assert resp.get("docId") == scn.doc_id, (
        f"[gssn] response must echo the docId it synced, got {resp!r}"
    )
    assert resp.get("result") != "locked-skip", (
        f"[gssn] sync_document lost the per-doc lock — no force flush actually ran: {resp!r}"
    )

    assert_log(
        gas_log_dir, fence,
        lambda e: e.get("tag") == "sync.forceFlush"
        and e.get("data", {}).get("docId") == scn.doc_id
        and (e.get("data", {}).get("count") or 0) >= 1,
        "[gssn sync_document] expected sync.forceFlush with count>=1 for a converged doc "
        "(proves the route bypassed the diff, not just re-ran a no-op sync)",
    )
    assert_log(
        gas_log_dir, fence,
        lambda e: e.get("tag") == "sync.complete"
        and e.get("data", {}).get("docId") == scn.doc_id
        and e.get("data", {}).get("forced") is True,
        "[gssn sync_document] sync.complete must report forced:true for this execution",
    )
    scn.checkpoint(STEP)


# ---------------------------------------------------------------------------
# AC (2): force is opt-in — the default route call must not force-flush.
# ---------------------------------------------------------------------------

def test_sync_document_route_without_force_does_not_force_flush(scn, settings, gas_log_dir):
    """force absent must leave the route on the plain diff-only sync path, so a
    converged doc produces no sync.forceFlush at all (gts-366c AC-4). This is the
    non-regression half: without it, a route that always forced would still pass
    the test above."""
    if not gas_log_dir:
        pytest.skip("gas_log_dir not configured — force-flush proof requires GAS log access")
    if not settings.get("webappSecret"):
        pytest.skip("local.settings.json missing webappSecret — cannot drive the secret gate")

    _converged_doc(scn)

    fence = clear_logs(gas_log_dir)
    resp = _post_sync_document(scn, settings, docId=scn.doc_id)  # no force key at all

    assert resp.get("ok") is True, f"[gssn] sync_document without force expected ok:true, got {resp!r}"
    assert resp.get("forced") is False, (
        f"[gssn] force absent must yield forced:false, got {resp!r}"
    )
    assert_no_log(
        gas_log_dir, fence,
        lambda e: e.get("tag") == "sync.forceFlush"
        and e.get("data", {}).get("docId") == scn.doc_id,
        "[gssn sync_document] a non-forced sync of a converged doc must not emit sync.forceFlush",
    )
    scn.checkpoint(STEP)


def test_sync_document_route_non_boolean_force_is_not_forced(scn, settings, gas_log_dir):
    """force must be strictly === true (gts-366c AC-4, mirroring
    _handleSyncActionRows' `scanned === true` gate). A JSON string 'true' — the
    shape a hand-rolled shell caller most easily produces — must NOT force."""
    if not gas_log_dir:
        pytest.skip("gas_log_dir not configured — force-flush proof requires GAS log access")
    if not settings.get("webappSecret"):
        pytest.skip("local.settings.json missing webappSecret — cannot drive the secret gate")

    _converged_doc(scn)

    fence = clear_logs(gas_log_dir)
    resp = _post_sync_document(scn, settings, docId=scn.doc_id, force="true")

    assert resp.get("forced") is False, (
        f"[gssn] force:'true' (string) must not be treated as forced, got {resp!r}"
    )
    assert_no_log(
        gas_log_dir, fence,
        lambda e: e.get("tag") == "sync.forceFlush"
        and e.get("data", {}).get("docId") == scn.doc_id,
        "[gssn sync_document] a non-boolean force value must not reach the force-flush path",
    )
    scn.checkpoint(STEP)


# ---------------------------------------------------------------------------
# Negatives (T-series): the route must refuse rather than mis-sync.
# ---------------------------------------------------------------------------

def test_sync_document_route_requires_doc_id(scn, settings):
    """An omitted docId must be refused with a named error, never silently
    dispatched into syncDocument('') (gts-366c AC-5).

    ScenarioSession._post raises FixtureError for any response carrying an
    `error` key, so the refusal surfaces as that exception rather than a dict —
    asserting on its message is the honest shape of the harness contract.
    """
    if not settings.get("webappSecret"):
        pytest.skip("local.settings.json missing webappSecret — cannot drive the secret gate")

    with pytest.raises(FixtureError, match="docId required"):
        _post_sync_document(scn, settings, force=True)


def test_sync_document_route_rejects_a_bad_secret(scn):
    """The route sits below the WEBAPP_SECRET gate: a wrong secret must be
    rejected before any sync runs (gts-366c AC-6).

    doPost's gate answers with a structured JSON body {ok:false, error:'unauthorized'}
    (src/WebApp.js, gts-pl2k), so it fails on the FIRST attempt instead of being
    misdiagnosed as GAS deployment-propagation lag (a non-JSON/echo-page response,
    which is what the plain-text 'unauthorized' body used to look like to every
    sanctioned caller). ScenarioSession._post surfaces the JSON 'error' field as a
    FixtureError, so assert on the response shape, not an exception raised while
    parsing a non-JSON body.
    """
    with pytest.raises(FixtureError, match="unauthorized"):
        scn._post({
            "secret": "not-the-webapp-secret",
            "action": _ROUTE,
            "docId": scn.doc_id,
            "force": True,
        })
