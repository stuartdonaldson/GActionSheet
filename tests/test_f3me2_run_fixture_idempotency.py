"""
test_f3me2_run_fixture_idempotency.py — gts-f3me.2 [TST]

Regression test for the double-batchFallback-event bug diagnosed against
gas-test3.log (02:07-02:13): test_uuse_scoped_listing.py's
test_syncall_batches_multi_doc_listing_miss_fallback saw TWO
sync.driveMetadata.batchFallback.fetched events (both count=3, real data)
sharing the SAME parentOp, ~3 minutes apart. Same bug class as gts-f3me.1's
append_doc_paragraph duplicate row: scn/session.py's _http_post retries a
run_fixture call on HTTP 404 / a non-JSON echo-page response, assuming the
first attempt never reached the GAS handler — but when the fixture (here, a
full syncAll() sweep) actually ran to completion and only the *response* was
lost to the /exec -> script.googleusercontent.com routing glitch, the retry
re-ran the whole fixture a second time under the same client-supplied opId
(parentOp), producing a real second execution rather than a false
correlation-filter positive.

Fix: TestWebApp.js's _handleRunFixture now dedupes on the client-supplied
opId (reused across all retry attempts of one logical call by _http_post)
via CacheService, mirroring gts-f3me.1's _handleAppendDocParagraph guard.

This test drives run_fixture directly with a fixed opId (rather than through
_post_fixture, which mints a fresh one per call) to simulate exactly the
retry-after-lost-response scenario. NOTE: 'sync_all' is NOT a cheap
single-doc fixture — src/TestFixtures.js's 'sync_all' case calls the
full-corpus syncAll() sweep; testDocId is passed through as a real parameter
but does not scope the sweep to one doc. This call legitimately takes
longer than the default 360s client timeout (scn/session.py's
_CORPUS_SCALED_FIXTURE_TIMEOUTS["sync_all"] = 600) and must use that
timeout explicitly here since it bypasses _post_fixture. Asserts exactly one
sync.all.start log entry results from two same-opId calls, and two from two
distinct-opId calls.
"""
import uuid

import pytest


def test_run_fixture_same_opid_is_not_duplicated(settings, gas_log_dir, request):
    if not gas_log_dir:
        pytest.skip("gas_log_dir not configured — call-count assertions require GAS log access")

    from scn.session import ScenarioSession
    from tests.helpers.gas_log import clear_logs, collect_logs, matches_op

    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn.append_paragraph("AI-1: f3me.2 idempotency-check action")
        scn.sync()

        sweep_op_id = str(uuid.uuid4())
        fence = clear_logs(gas_log_dir)

        payload = {
            "action": "run_fixture",
            "testToken": scn.settings.get("testToken") or "",
            "fixture": "sync_all",
            "testDocId": scn.doc_id,
            "opId": sweep_op_id,
        }
        resp1 = scn._post(payload, timeout=600)
        assert resp1.get("tag") == "fixture.sync_all", resp1

        # Simulated retry: same opId, same call — what _http_post does when
        # the first response never reaches the client despite the server
        # having already applied (and finished) the run.
        resp2 = scn._post(payload, timeout=600)
        assert resp2 == resp1, (
            f"[f3me.2] retried run_fixture call with the same opId should return the "
            f"cached response verbatim, got a different one: {resp1!r} vs {resp2!r}"
        )

        start_events = collect_logs(
            gas_log_dir,
            matches_op(lambda e: e.get("tag") == "sync.all.start", sweep_op_id),
            after=fence,
        )
        assert len(start_events) == 1, (
            f"[f3me.2] expected exactly ONE sync.all.start for two same-opId run_fixture "
            f"calls, got {len(start_events)}: {start_events!r}"
        )
    finally:
        scn.engine.close()


def test_run_fixture_different_opid_is_not_deduped(settings, gas_log_dir, request):
    """Sanity check the guard is opId-scoped, not fixture-scoped: two
    genuinely distinct calls (different opId) must both execute."""
    if not gas_log_dir:
        pytest.skip("gas_log_dir not configured — call-count assertions require GAS log access")

    from scn.session import ScenarioSession
    from tests.helpers.gas_log import clear_logs, collect_logs

    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn.append_paragraph("AI-1: f3me.2 distinct-calls-check action")
        scn.sync()

        fence = clear_logs(gas_log_dir)
        op_a = str(uuid.uuid4())
        op_b = str(uuid.uuid4())

        for op_id in (op_a, op_b):
            resp = scn._post({
                "action": "run_fixture",
                "testToken": scn.settings.get("testToken") or "",
                "fixture": "sync_all",
                "testDocId": scn.doc_id,
                "opId": op_id,
            }, timeout=600)
            assert resp.get("tag") == "fixture.sync_all", resp

        start_events = collect_logs(
            gas_log_dir,
            lambda e: e.get("tag") == "sync.all.start" and e.get("parentOp") in (op_a, op_b),
            after=fence,
        )
        assert len(start_events) == 2, (
            f"[f3me.2] expected 2 sync.all.start events from two distinct-opId run_fixture "
            f"calls, got {len(start_events)}: {start_events!r}"
        )
    finally:
        scn.engine.close()
