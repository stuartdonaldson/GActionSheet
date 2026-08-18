"""
test_gas_log_reliability.py — gts-7389

Regression coverage for the Axiom log-wait false-negative investigated in
gts-7389: a full-suite run observed test_sync_concurrency.py's
sync.locked.skip wait time out at 60s even though the event was later
confirmed present in Axiom (python scripts/query_axiom.py --name
sync.locked.skip --since 12h), with a `_time` squarely inside the failing
test's own window.

Root cause found: TestWebApp.js's `_handleRunFixture` (the run_fixture HTTP
dispatcher every fixture-driven test call goes through) never called
GasLogger.flush(). GasLogger's entry buffer is per-execution, in-memory
state (see GasLogger.js's own doc comment) with no durable backing —
flush() is the only thing that POSTs it to Axiom. Without a flush() call in
_handleRunFixture's `finally` block, any log() entries produced while
handling a run_fixture request (including syncDocument()'s own
'sync.locked.skip' locked-skip early return, which itself never flushes)
just sat in that buffer. They became durable only by accident: either a
LATER, unrelated request warmed the same GAS instance and pushed the
buffer over FLUSH_THRESHOLD (25 entries), or the instance was torn down
and the entry was lost outright. Either way, the entry's `ts` is stamped
at log() time — so a flush minutes later still lands in Axiom with a
timestamp inside the *original* request's window, looking to a human
cross-referencing timestamps after the fact like it "was there all
along," while the live wait_for_log poll that actually mattered had
already timed out.

Fix: _handleRunFixture now unconditionally calls GasLogger.flush() in its
`finally` block (matching every other WebApp.js route), so every
run_fixture response is synchronously durable before the HTTP response
returns.

This test drives the exact fixture (`sync_lock_race`) from the original
false-negative and asserts the resulting log entry is queryable well
inside a tight bound — proving flush is now deterministic rather than
luck-of-warm-instance-reuse. It is deliberately independent of (and
lighter than) test_sync_concurrency.py's own full lock-serialization
regression test — this one only exercises the log-delivery path.
"""
from scn.session import ScenarioSession


def test_run_fixture_flushes_gas_logger_before_response(settings, gas_log_dir, request):
    """[gts-7389] A run_fixture-driven log entry must be queryable well
    within a tight bound, not merely "eventually, if a later request
    happens to flush the buffer." Confirms _handleRunFixture's flush()
    fix closes the gap deterministically."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        fence = 0.0
        if gas_log_dir:
            from tests.helpers.gas_log import clear_logs
            fence = clear_logs(gas_log_dir)

        # sync_lock_race (TestFixtures.js, gts-li3g) acquires the per-docId
        # lock itself, then drives the real syncDocument() entry point a
        # second time — which hits the locked-skip early return and logs
        # 'sync.locked.skip' without flushing on its own. Whether that entry
        # ever reaches Axiom promptly depends entirely on _handleRunFixture's
        # own flush() call.
        resp = scn._post_fixture("sync_lock_race")
        race_data = resp.get("data") or {}
        assert race_data.get("lockHeldByFirst") is True, (
            f"[gts-7389] fixture failed to acquire the simulated first-execution "
            f"lock: {resp!r}"
        )

        if gas_log_dir:
            from tests.helpers.gas_log import wait_for_log
            # Tight bound (well under the 60s used elsewhere in this suite) —
            # this IS the regression assertion. axiom_probe_latency's own
            # calibration (tests/helpers/gas_log.py) puts a synchronously-
            # flushed round trip in the low single-digit seconds; 20s leaves
            # generous headroom for Axiom ingest jitter without disguising a
            # reintroduced missing-flush bug as a slow-but-passing test.
            wait_for_log(
                gas_log_dir,
                lambda e: e.get("tag") == "sync.locked.skip"
                and (e.get("data") or {}).get("docId") == scn.doc_id,
                timeout_s=20,
                after=fence,
            )
    finally:
        scn.close()
