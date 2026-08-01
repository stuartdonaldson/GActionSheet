"""
test_sync_concurrency.py — gts-li3g

Regression coverage for syncDocument()'s per-docId lock: two overlapping
syncDocument() executions for the SAME docId (e.g. the 30-min time-based
trigger firing mid-manual-sync) must not let the second one revert a Dirty
(sheet-authoritative) row back to the doc's stale value — the failure
signature originally observed in tests/test_journey.py's Act 5 idempotency
pass (two independent sync.complete events 117ms apart, different op IDs).

Per plan-context.md's "when NOT to batch" note, this scenario is inherently
multi-sweep by design (a deliberate two-sync sequence) and is NOT a
permutation-batching candidate — kept as its own single-scenario test.

True OS-level concurrency between two separate script executions cannot be
reliably timed from a Python test harness (HTTP/network jitter dwarfs GAS's
own scheduling), so this test drives the AC's explicitly-sanctioned
alternative: prove the lock serializes two overlapping syncDocument() calls
for the same docId. The `sync_lock_race` fixture (TestFixtures.js)
artificially holds the per-docId lock — simulating a first, still in-flight
execution — then calls the REAL syncDocument(docId) entry point a second
time while that lock is held. This is a genuine call to the production
entry point (T1/T17 entry-point-coverage), not a mock of it.

Backstop: pre-fix, `_acquireDocSyncLock`/`_releaseDocSyncLock` do not exist
in SyncManager.js, so the `sync_lock_race` fixture itself cannot run
(ReferenceError) — this test fails outright without the fix. Confirmed live
this session: `_acquireDocSyncLock`/the lock-skip guard in syncDocument()
were temporarily reverted, TEST redeployed, and this test rerun to observe
the predicted failure (second syncDocument() call proceeded and reconciled
immediately rather than skipping) before restoring and redeploying the fix.
"""
from scn.engine import CheckpointKind, Surface
from scn.session import ScenarioSession

SHEET = Surface.SHEET
STEP = CheckpointKind.STEP


def test_sync_lock_serializes_concurrent_syncdocument_for_same_doc(settings, gas_log_dir, request):
    """[gts-li3g] A second, overlapping syncDocument(docId) execution for a
    doc that's already mid-sync must skip outright — not read, reconcile, or
    flush anything — so a Dirty (sheet-authoritative) row is never reverted
    by the race. Once the first execution's lock clears, a normal sync
    reconciles the row correctly (the lock does not permanently wedge the doc)."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn.append_paragraph("AI-1: li3g concurrency-lock target action")
        scn.sync()

        rows = scn.find_sheet_actions()
        assert rows, "[li3g] expected exactly one Actions row after initial sync"
        target = rows[0]
        assert target.global_id and target.action_id, (
            f"[li3g] seeded row missing global_id/action_id: {target!r}"
        )

        # Set status via the patch_action_status core (sidebar/link-preview
        # path) — sheet becomes Dirty (sheet-authoritative) while the doc
        # paragraph still shows the stale status text. This is the exact
        # race precondition test_journey.py's Act 5 hits when the 30-min
        # trigger overlaps a manual sync.
        scn.link_preview_status_change(target, "In Progress")

        pre_rows = {r.global_id: (r.status, r.sync_status) for r in scn.find_sheet_actions()}
        pre_status, pre_sync_status = pre_rows[target.global_id]
        assert pre_status == "In Progress" and pre_sync_status == "Dirty", (
            f"[li3g] setup precondition failed: expected ('In Progress','Dirty'), "
            f"got ({pre_status!r},{pre_sync_status!r})"
        )

        fence = 0.0
        if gas_log_dir:
            from tests.helpers.gas_log import clear_logs
            fence = clear_logs(gas_log_dir)

        # Drive the race: the fixture holds the per-docId lock itself
        # (simulating a first, still in-flight execution), then calls the
        # REAL syncDocument(docId) entry point a second time while that
        # lock is held.
        resp = scn._post_fixture("sync_lock_race")
        race_data = resp.get("data") or {}
        assert race_data.get("lockHeldByFirst") is True, (
            f"[li3g] fixture failed to acquire the simulated first-execution lock: {resp!r}"
        )

        if gas_log_dir:
            from tests.helpers.gas_log import wait_for_log
            wait_for_log(
                gas_log_dir,
                lambda e: e.get("tag") == "sync.locked.skip"
                and (e.get("data") or {}).get("docId") == scn.doc_id,
                timeout_s=60,
                after=fence,
            )

        # Durable invariant: the second (racing) syncDocument() call must
        # not have touched the row at all — sheet is exactly as
        # patch_action_status left it, not reverted to the doc's stale
        # 'Open' text and not yet re-reconciled either (it never ran).
        raced_rows = {r.global_id: (r.status, r.sync_status) for r in scn.find_sheet_actions()}
        raced_status, raced_sync_status = raced_rows[target.global_id]
        assert raced_status == "In Progress" and raced_sync_status == "Dirty", (
            f"[li3g] second syncDocument() call proceeded against a stale pre-lock read "
            f"instead of skipping: expected unchanged ('In Progress','Dirty'), "
            f"got ({raced_status!r},{raced_sync_status!r})"
        )

        # Once the simulated first execution's lock clears (the fixture
        # releases it before returning), a normal sync must still reconcile
        # the Dirty row correctly — the lock must not permanently wedge the
        # doc out of sync.
        scn.sync()
        settled_rows = {r.global_id: (r.status, r.sync_status) for r in scn.find_sheet_actions()}
        settled_status, settled_sync_status = settled_rows[target.global_id]
        assert settled_status == "In Progress", (
            f"[li3g] post-contention sync did not reconcile the Dirty row: got {settled_status!r}"
        )
        assert settled_sync_status != "Dirty", (
            f"[li3g] post-contention sync left sync_status Dirty: {settled_sync_status!r}"
        )

        doc_match = None
        for item in scn.doc_items():
            if item.action_id == target.action_id:
                doc_match = item
                break
        assert doc_match is not None, (
            f"[li3g] target action {target.action_id!r} not found in doc after settle sync"
        )
        assert doc_match.status == "In Progress", (
            f"[li3g] doc paragraph not flushed to 'In Progress' after contention cleared: "
            f"{doc_match.status!r}"
        )

        # Re-snapshot from the current sheet (not the pre-race `target`) —
        # created_date/modified_date advanced when the settle sync ran, and
        # verify_all_expectations pins whatever the ai carries at call time.
        settled_target = next(
            r for r in scn.find_sheet_actions() if r.global_id == target.global_id
        )
        scn.verify_all_expectations(settled_target, tag="[li3g settle]", entry_point="syncDocument")
        scn.checkpoint(CheckpointKind.INTEGRITY)
        scn.verify_consistency(scope=SHEET)
    finally:
        scn.close()
