"""
test_zc0w_probe_parity.py — gts-zc0w

Path B twin for gts-vl44 (batch fallback probe omitted supportsAllDrives,
already fixed — see SyncManager.js:2917-2920). Audits the FULL entry-point
class for Drive reachability probing, not only the one reported failure.

Two probe surfaces, both returning {status: 'found'|'gone'|'unknown', meta,
err} (SyncManager.js:661-664):
  - _fetchSingleDocMetadata(docId)   -- used when exactly 1 tracked doc is
    absent from the scoped Drive listing in a syncAll() sweep.
  - _fetchDriveDocMetadataBatch(docIds) -- used when >=2 docs are absent.

PARITY IS THE INVARIANT this file exists to assert directly: for the same
docId, both paths must return the same status. That is the assertion that
would have caught gts-vl44 (a Shared-Drive doc 404'd through the batch path
only, because its multipart request omitted supportsAllDrives, while the
single-doc path — which already carried the flag — reported it live).

AC5 audit enumeration (the cases named in gts-zc0w's frozen contract, and
where each is covered):

  (a) N=1 vs N>=2, same doc, same verdict ('found')
      -> test_probe_parity_found_single_vs_batch (THIS FILE, primary deliverable)
  (b) A live Shared Drive doc absent from the listing -> never marked
      -> NOT drivable here. This environment has no test Shared Drive folder
         id provisioned in local.settings.json (same constraint documented in
         tests/test_uuse_scoped_listing.py's module docstring and
         tests/test_sync_all.py's gts-rskf comment ~line 570). gts-vl44's own
         fix (the _DRIVE_ITEM_PARAMS / supportsAllDrives addition at
         SyncManager.js:2920) is reviewed structurally below instead (AC3).
  (c) A genuinely deleted (unreachable) doc -> marked 'Doc Not Found' through
      BOTH paths
      -> test_probe_parity_gone_single_vs_batch (THIS FILE). Practically
         drivable form: trash_doc on a real doc (files.get still returns 200
         with trashed:true, not a literal 404/'gone' -- see that test's own
         docstring for why a true 404 isn't drivable here without a new
         permanent-delete fixture, out of scope) forced absent from the
         listing, compared single-path vs batch-path.
  (d) A doc wrongly marked -> revived on the next sweep
      -> already covered: tests/test_sync_all.py::test_sync_all_integrity_and_listing_miss_batch
         (the "rev" sub-case: trash_doc -> forced-miss sweep marks it -> untrash
         -> next sweep logs sync.docNotFound.revived and the row survives).
         Not duplicated here.
  (e) A transient/indeterminate probe -> neither marked nor revived
      -> NOT drivable with existing fixtures. Structural reason (traced via
         SyncManager.js:2705-2740, _fetchDriveWithRetry / _driveFetchTestOverrideCode
         and the existing 'sync_all_force_drive_5xx' fixture): the fault-injection
         counter (_TEST_FORCE_DRIVE_5XX_COUNT) is GLOBAL across the whole retry
         chain, not scoped to one call site, and is consumed in call order by
         WHICHEVER Drive REST call happens first in a sweep. The bulk listing
         call (_fetchDriveDocMetadata) always fires before any fallback probe,
         so any fails count large enough to also exhaust the fallback probe's
         own 3 attempts first exhausts the bulk listing's 3 attempts, which
         empties driveMetadata and routes EVERY tracked doc through the
         fallback -- and by the time that fallback's own _fetchDriveWithRetry
         call runs, the counter is spent, so it succeeds on a real (non-forced)
         attempt and returns 'found', never 'unknown'. Every failure layer in
         this code recovers before a genuine 'unknown' is reached, by design
         (see gts-rskf/gts-pm72's "never assume, always confirm" layering) --
         which is exactly why case (e) has no live drive. Producing it would
         require a NEW dedicated fault-injection hook scoped to
         _fetchSingleDocMetadata/_fetchDriveDocMetadataBatch specifically
         (a TestFixtures.js change), which is out of this bead's scope per the
         task brief ("do not fabricate a Shared Drive folder id" / stick to
         existing fixtures). Recorded here per AC2 rather than silently
         omitted.

Consumers enumerated in the frozen contract (AC2):
  - syncAll's not-found detection (marks)      -- exercised by both tests below
    and by test_sync_all.py's existing coverage.
  - syncAll's alreadyDocNotFound revival branch (unmarks) -- covered by
    test_sync_all.py::test_sync_all_integrity_and_listing_miss_batch (case d
    above); not duplicated here.
  - The 30-minute Background Sync trigger -- the trigger is disabled in
    production (gts-bxa6, resolved separately), but its handler function is
    the same syncAll() every test in this file and test_sync_all.py already
    drives directly, so the entry point is covered structurally: the trigger
    is just a scheduler calling the same function under test.

Log tags exercised (SyncManager.js): sync.driveMetadata.listingMiss,
sync.driveMetadata.batchFallback.fetched / .error, sync.docNotFound.missing,
sync.driveMetadata.indeterminate.
"""
import uuid

import pytest

from scn.engine import CheckpointKind, Surface
from scn.session import ScenarioSession

SHEET = Surface.SHEET
STEP = CheckpointKind.STEP


def _post_fixture_patient(scn, fixture_name: str, extra: dict | None = None, timeout: int = 600) -> dict:
    """Same convention as test_sync_all.py / test_uuse_scoped_listing.py's
    helper of the same name -- these fixtures re-run the real syncAll() over
    the whole production backlog, not just this test's own docs, so they
    inherit the same longer client timeout."""
    payload = {
        "action": "run_fixture",
        "testToken": scn.settings.get("testToken") or "",
        "fixture": fixture_name,
        "testDocId": scn.doc_id,
    }
    if extra:
        payload.update(extra)
    return scn._post(payload, timeout=timeout)


# ---------------------------------------------------------------------------
# Case (a) -- THE primary deliverable: parity assertion, 'found' verdict
# ---------------------------------------------------------------------------

def test_probe_parity_found_single_vs_batch(settings, gas_log_dir, request):
    """[gts-zc0w AC1] The same live, reachable doc (X) is forced absent from
    the scoped Drive listing in two separate sweeps: once alone (intended to
    route through _fetchSingleDocMetadata, syncAll's N=1 branch), once paired
    with a second doc Y (guaranteed to route through
    _fetchDriveDocMetadataBatch, syncAll's N>=2 branch -- forcing 2 absent
    docs makes missingDocIds.length >= 2 regardless of any other backlog
    churn in this shared account). X's verdict ('found', not marked, not
    indeterminate) must be identical across both sweeps -- this is the
    assertion gts-vl44 would have caught, made direct rather than inferred
    from survival alone.

    Best-effort note on path selection: this is a shared, live TEST account,
    and 'missingDocIds' (SyncManager.js ~line 658) is computed over the WHOLE
    tracked backlog, not just this test's own docs (see
    tests/test_uuse_scoped_listing.py's own comment on batchFallback.fetched's
    'count' ranging 2-258 across routine sweeps). Sweep 1 below is designed to
    exercise the single-doc path and is checked for that (no batchFallback
    tag correlated to its own opId), but a concurrent sweep elsewhere in the
    account could in principle push it to the batch path too -- if that
    happens the assertion below fails loudly rather than silently mis-
    reporting parity, which is the correct behavior for an environment-
    dependent precondition.
    """
    if not gas_log_dir:
        pytest.skip("gas_log_dir not configured — call-count/tag assertions require GAS log access")

    from tests.helpers.gas_log import clear_logs, collect_logs, matches_op, wait_for_log

    scn_x = ScenarioSession.new_doc(settings, request=request)
    scn_y = ScenarioSession.new_doc(settings, request=request)
    try:
        scn_x.append_paragraph("AI-1: zc0w parity found-case doc X")
        scn_x.sync()
        scn_y.append_paragraph("AI-1: zc0w parity found-case doc Y (batch padding only)")
        scn_y.sync()

        pre_rows_x = scn_x.find_sheet_actions()
        assert pre_rows_x, "[zc0w] expected ≥1 Actions row for doc X before the forced-miss sweeps"
        pre_statuses_x = {r.global_id: r.sync_status for r in pre_rows_x}

        # ── Sweep 1: X alone forced missing -- intended single-doc path ────────
        op1 = str(uuid.uuid4())
        fence1 = clear_logs(gas_log_dir)
        _post_fixture_patient(
            scn_x, "sync_all_force_listing_miss",
            extra={"docId": scn_x.doc_id, "opId": op1},
        )
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.all.complete", timeout_s=600, after=fence1)

        listingmiss_1 = collect_logs(
            gas_log_dir,
            matches_op(
                lambda e: e.get("tag") == "sync.driveMetadata.listingMiss"
                and (e.get("data") or {}).get("docId") == scn_x.doc_id,
                op1,
            ),
            after=fence1,
        )
        assert listingmiss_1, (
            f"[zc0w] expected doc X to log sync.driveMetadata.listingMiss (verdict 'found') "
            f"in sweep 1, got none"
        )
        gone_1 = collect_logs(
            gas_log_dir,
            matches_op(
                lambda e: e.get("tag") == "sync.docNotFound.missing"
                and (e.get("data") or {}).get("docId") == scn_x.doc_id,
                op1,
            ),
            after=fence1,
        )
        assert not gone_1, f"[zc0w] doc X (live) wrongly reported 'gone' in sweep 1: {gone_1!r}"
        unknown_1 = collect_logs(
            gas_log_dir,
            matches_op(
                lambda e: e.get("tag") == "sync.driveMetadata.indeterminate"
                and (e.get("data") or {}).get("docId") == scn_x.doc_id,
                op1,
            ),
            after=fence1,
        )
        assert not unknown_1, f"[zc0w] doc X (live) wrongly reported 'unknown' in sweep 1: {unknown_1!r}"

        batch_1 = collect_logs(
            gas_log_dir,
            matches_op(lambda e: e.get("tag") == "sync.driveMetadata.batchFallback.fetched", op1),
            after=fence1,
        )
        if batch_1:
            # Environmental precondition, not a defect: this shared TEST account's
            # ambient backlog (docs already outside every scoped team folder, or
            # otherwise naturally missing from the listing -- see
            # test_uuse_scoped_listing.py's "count ranged 2-258" comment) can push
            # missingDocIds.length >= 2 regardless of this fixture, routing sweep 1
            # into the batch path too. That makes a genuine single-vs-batch
            # comparison undrivable THIS run, not wrong -- skip rather than
            # false-FAIL; re-running when the account is quieter gets the clean
            # single-path leg.
            pytest.skip(
                f"[zc0w] sweep 1 (intended single-doc path) hit the batch path instead "
                f"due to shared-account backlog churn: {batch_1!r}. Not a defect -- "
                f"re-run when the account has <2 docs naturally missing from the "
                f"scoped listing to get a clean single-vs-batch comparison."
            )

        post_rows_x_1 = scn_x.find_sheet_actions()
        assert len(post_rows_x_1) == len(pre_rows_x), (
            f"[zc0w] doc X Actions row count changed after sweep 1: "
            f"before={len(pre_rows_x)} after={len(post_rows_x_1)}"
        )
        for row in post_rows_x_1:
            assert row.sync_status != "Doc Not Found", (
                f"[zc0w] doc X row {row.global_id!r} marked 'Doc Not Found' after sweep 1"
            )

        # ── Sweep 2: X + Y forced missing -- guaranteed batch path (N>=2) ──────
        op2 = str(uuid.uuid4())
        fence2 = clear_logs(gas_log_dir)
        _post_fixture_patient(
            scn_x, "sync_all_force_listing_miss_multi",
            extra={"docIds": [scn_x.doc_id, scn_y.doc_id], "opId": op2},
        )
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.all.complete", timeout_s=600, after=fence2)

        batch_2 = collect_logs(
            gas_log_dir,
            matches_op(lambda e: e.get("tag") == "sync.driveMetadata.batchFallback.fetched", op2),
            after=fence2,
        )
        assert batch_2, (
            "[zc0w] sweep 2 (2 docs forced missing) did not exercise "
            "_fetchDriveDocMetadataBatch at all -- expected ≥1 batchFallback.fetched event"
        )
        batch_2_errors = collect_logs(
            gas_log_dir,
            matches_op(lambda e: e.get("tag") == "sync.driveMetadata.batchFallback.error", op2),
            after=fence2,
        )
        assert not batch_2_errors, (
            f"[zc0w] batch/drive/v3 request degraded to the sequential fallback in sweep 2 "
            f"(should have succeeded via the real batch endpoint): {batch_2_errors!r}"
        )

        listingmiss_2 = collect_logs(
            gas_log_dir,
            matches_op(
                lambda e: e.get("tag") == "sync.driveMetadata.listingMiss"
                and (e.get("data") or {}).get("docId") == scn_x.doc_id,
                op2,
            ),
            after=fence2,
        )
        assert listingmiss_2, (
            f"[zc0w] expected doc X to ALSO log sync.driveMetadata.listingMiss (verdict "
            f"'found') in sweep 2 (batch path), got none"
        )
        gone_2 = collect_logs(
            gas_log_dir,
            matches_op(
                lambda e: e.get("tag") == "sync.docNotFound.missing"
                and (e.get("data") or {}).get("docId") == scn_x.doc_id,
                op2,
            ),
            after=fence2,
        )
        assert not gone_2, f"[zc0w] doc X (live) wrongly reported 'gone' in sweep 2 (batch path): {gone_2!r}"
        unknown_2 = collect_logs(
            gas_log_dir,
            matches_op(
                lambda e: e.get("tag") == "sync.driveMetadata.indeterminate"
                and (e.get("data") or {}).get("docId") == scn_x.doc_id,
                op2,
            ),
            after=fence2,
        )
        assert not unknown_2, f"[zc0w] doc X (live) wrongly reported 'unknown' in sweep 2 (batch path): {unknown_2!r}"

        # ── THE PARITY ASSERTION (AC1): same docId, same verdict, different path ──
        # Sweep 1 exercised _fetchSingleDocMetadata (confirmed above: no batch
        # event correlated to op1); sweep 2 exercised _fetchDriveDocMetadataBatch
        # (confirmed above: batchFallback.fetched present). Both produced
        # sync.driveMetadata.listingMiss for the SAME docId and neither produced
        # docNotFound.missing/indeterminate for it -- i.e. status='found' via two
        # structurally different code paths. This is exactly the invariant
        # gts-vl44 broke: the batch path's multipart request omitted
        # supportsAllDrives (SyncManager.js:2920) so a Shared-Drive doc got
        # 'gone' through batch while the single path (which already carried the
        # flag) reported 'found' for the identical doc -- a parity break this
        # assertion would have caught directly.
        assert bool(listingmiss_1) and bool(listingmiss_2), (
            "[zc0w] PARITY FAILURE: doc X's verdict differed between the single-doc "
            f"path (sweep 1: listingMiss={bool(listingmiss_1)}) and the batch path "
            f"(sweep 2: listingMiss={bool(listingmiss_2)})"
        )

        post_rows_x_2 = scn_x.find_sheet_actions()
        assert len(post_rows_x_2) == len(pre_rows_x), (
            f"[zc0w] doc X Actions row count changed after sweep 2: "
            f"before={len(pre_rows_x)} after={len(post_rows_x_2)}"
        )
        for row in post_rows_x_2:
            assert row.sync_status != "Doc Not Found", (
                f"[zc0w] doc X row {row.global_id!r} marked 'Doc Not Found' after sweep 2"
            )
            prior = pre_statuses_x.get(row.global_id)
            assert row.sync_status == (prior or ""), (
                f"[zc0w] doc X row {row.global_id!r} sync_status changed: "
                f"{prior!r} -> {row.sync_status!r}"
            )

        # ── Durability + entry-point tagging (project rule: verify_consistency()
        #    requires ≥1 verify_all_expectations() call in the same scenario) ──
        def _durable_x() -> str | None:
            rows = scn_x.find_sheet_actions()
            if not rows:
                return "[zc0w] doc X Actions rows disappeared after parity sweeps"
            for row in rows:
                if row.sync_status == "Doc Not Found":
                    return f"[zc0w] doc X row {row.global_id!r} marked Doc Not Found"
            return None

        scn_x.expect_callable(_durable_x, on=SHEET, tag="[zc0w probe parity found]", entry_point="syncAll")
        scn_x.checkpoint(STEP)
        settled_x = next(r for r in scn_x.find_sheet_actions() if r.global_id == pre_rows_x[0].global_id)
        scn_x.verify_all_expectations(settled_x, tag="[zc0w probe parity found]", entry_point="syncAll")
        scn_x.checkpoint(CheckpointKind.INTEGRITY)
        scn_x.verify_consistency(scope=SHEET)
    finally:
        for scn in (scn_x, scn_y):
            scn.engine.close()


# ---------------------------------------------------------------------------
# Case (c) -- parity assertion, 'gone' verdict (genuinely unreachable doc)
# ---------------------------------------------------------------------------

def test_probe_parity_gone_single_vs_batch(settings, gas_log_dir, request):
    """[gts-zc0w AC1/case (c)] Two independent REAL docs (R1, R2), each synced
    normally then trashed (trash_doc), each forced absent from the scoped
    Drive listing in its own sweep -- R1 alone (intended single-doc path),
    R2 paired with a third live doc R3 (guaranteed batch path, N>=2). Both
    trigger the SAME probe outcome -- files.get succeeds (200, trashed:true),
    i.e. probe status='found' with meta.trashed=true, which syncAll's outer
    check then marks 'Doc Not Found' via the DISTINCT 'sync.docNotFound.trashed'
    tag -- and this must be identical through both paths. This is the
    'genuinely deleted' case's practically-drivable form in this environment.

    Not a literal probe status='gone' (404): a real trashed-but-undeleted
    Drive file still returns HTTP 200 from files.get with trashed:true, not a
    404 -- 'gone' is reserved for a file Drive positively reports doesn't
    exist at all (see docstring on _fetchSingleDocMetadata,
    SyncManager.js:3017-3030). A true 404 for an otherwise-real, team-folder-
    scoped tracked doc would require permanently deleting a live Drive file,
    which has no fixture in this project (only trash_doc/untrash_doc exist)
    and is out of this bead's scope to add. What IS provable, and is exactly
    what this test proves: the SAME probe response shape (found + trashed)
    drives the SAME outward 'marked not-found' behavior regardless of which
    of the two probe functions produced it -- which is the parity invariant
    gts-vl44 broke (there, the batch path's OWN malformed request made it
    diverge from the single path's answer for the identical doc).

    Two independent docs rather than reusing one across both sweeps: once a
    doc is marked 'Doc Not Found', a second sweep against the SAME doc enters
    syncAll's alreadyDocNotFound REVIVAL branch (a different code path,
    already covered -- see case (d) in this file's module docstring), not the
    fresh-detection branch this test targets.
    """
    if not gas_log_dir:
        pytest.skip("gas_log_dir not configured — call-count/tag assertions require GAS log access")

    from tests.helpers.gas_log import clear_logs, collect_logs, matches_op, wait_for_log

    r1 = ScenarioSession.new_doc(settings, request=request)
    r2 = ScenarioSession.new_doc(settings, request=request)
    r3 = ScenarioSession.new_doc(settings, request=request)
    try:
        r1.append_paragraph("AI-1: zc0w parity gone-case R1 (single-path leg)")
        r1.sync()
        r2.append_paragraph("AI-1: zc0w parity gone-case R2 (batch-path leg)")
        r2.sync()
        r3.append_paragraph("AI-1: zc0w parity gone-case R3 (batch padding only)")
        r3.sync()

        r1._post_fixture("trash_doc")
        r2._post_fixture("trash_doc")

        # ── Leg 1: R1 (trashed) forced absent from the listing -- intended
        #    single-doc path (docId==testDocId, same working pattern as case
        #    (a)'s sweep 1: DocumentApp.openById(R1.doc_id) opens fine even
        #    though the doc is trashed -- trashing is not deletion). ─────────
        op1 = str(uuid.uuid4())
        fence1 = clear_logs(gas_log_dir)
        _post_fixture_patient(
            r1, "sync_all_force_listing_miss",
            extra={"docId": r1.doc_id, "opId": op1},
        )
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.all.complete", timeout_s=600, after=fence1)

        batch_1 = collect_logs(
            gas_log_dir,
            matches_op(lambda e: e.get("tag") == "sync.driveMetadata.batchFallback.fetched", op1),
            after=fence1,
        )
        if batch_1:
            # Same environmental precondition as case (a)'s sweep 1 -- see that
            # test's comment. Skip rather than false-FAIL.
            pytest.skip(
                f"[zc0w] leg 1 (intended single-doc path) hit the batch path instead "
                f"due to shared-account backlog churn: {batch_1!r}. Not a defect -- "
                f"re-run when the account has <2 docs naturally missing from the "
                f"scoped listing to get a clean single-vs-batch comparison."
            )
        listingmiss_1 = collect_logs(
            gas_log_dir,
            matches_op(
                lambda e: e.get("tag") == "sync.driveMetadata.listingMiss"
                and (e.get("data") or {}).get("docId") == r1.doc_id,
                op1,
            ),
            after=fence1,
        )
        assert listingmiss_1, (
            "[zc0w] expected R1 to log sync.driveMetadata.listingMiss (probe status "
            "'found', meta.trashed=true) in leg 1"
        )
        trashed_1 = collect_logs(
            gas_log_dir,
            matches_op(
                lambda e: e.get("tag") == "sync.docNotFound.trashed"
                and (e.get("data") or {}).get("docId") == r1.doc_id,
                op1,
            ),
            after=fence1,
        )
        assert trashed_1, "[zc0w] expected R1 to log sync.docNotFound.trashed (marked) in leg 1"

        r1_rows = r1.find_sheet_actions()
        assert r1_rows, "[zc0w] R1's Actions row disappeared before leg 1 could mark it"
        for row in r1_rows:
            assert row.sync_status == "Doc Not Found", (
                f"[zc0w] R1 row {row.global_id!r} not marked 'Doc Not Found' after leg 1 "
                f"(single-path): sync_status={row.sync_status!r}"
            )

        # ── Leg 2: R2 (trashed) + R3 (live) forced absent -- guaranteed batch
        #    path (N>=2, regardless of any other backlog churn). ────────────
        op2 = str(uuid.uuid4())
        fence2 = clear_logs(gas_log_dir)
        _post_fixture_patient(
            r2, "sync_all_force_listing_miss_multi",
            extra={"docIds": [r2.doc_id, r3.doc_id], "opId": op2},
        )
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.all.complete", timeout_s=600, after=fence2)

        batch_2 = collect_logs(
            gas_log_dir,
            matches_op(lambda e: e.get("tag") == "sync.driveMetadata.batchFallback.fetched", op2),
            after=fence2,
        )
        assert batch_2, (
            "[zc0w] leg 2 (R2 + R3 forced missing) did not exercise "
            "_fetchDriveDocMetadataBatch at all -- expected ≥1 batchFallback.fetched event"
        )
        batch_2_errors = collect_logs(
            gas_log_dir,
            matches_op(lambda e: e.get("tag") == "sync.driveMetadata.batchFallback.error", op2),
            after=fence2,
        )
        assert not batch_2_errors, (
            f"[zc0w] batch/drive/v3 request degraded to the sequential fallback in leg 2 "
            f"(should have succeeded via the real batch endpoint): {batch_2_errors!r}"
        )
        listingmiss_2 = collect_logs(
            gas_log_dir,
            matches_op(
                lambda e: e.get("tag") == "sync.driveMetadata.listingMiss"
                and (e.get("data") or {}).get("docId") == r2.doc_id,
                op2,
            ),
            after=fence2,
        )
        assert listingmiss_2, (
            "[zc0w] expected R2 to ALSO log sync.driveMetadata.listingMiss (probe status "
            "'found', meta.trashed=true) in leg 2 (batch path)"
        )
        trashed_2 = collect_logs(
            gas_log_dir,
            matches_op(
                lambda e: e.get("tag") == "sync.docNotFound.trashed"
                and (e.get("data") or {}).get("docId") == r2.doc_id,
                op2,
            ),
            after=fence2,
        )
        assert trashed_2, "[zc0w] expected R2 to log sync.docNotFound.trashed (marked) in leg 2 (batch path)"

        r2_rows = r2.find_sheet_actions()
        assert r2_rows, "[zc0w] R2's Actions row disappeared before leg 2 could mark it"
        for row in r2_rows:
            assert row.sync_status == "Doc Not Found", (
                f"[zc0w] R2 row {row.global_id!r} not marked 'Doc Not Found' after leg 2 "
                f"(batch-path): sync_status={row.sync_status!r}"
            )

        # R3 (padding doc, live/not trashed) must survive unmarked -- same
        # invariant as case (a)'s doc Y.
        r3_rows = r3.find_sheet_actions()
        for row in r3_rows:
            assert row.sync_status != "Doc Not Found", (
                f"[zc0w] R3 (live padding doc) row {row.global_id!r} wrongly marked "
                f"'Doc Not Found' after leg 2"
            )

        # ── THE PARITY ASSERTION (AC1/case c): same probe response shape
        #    (found + trashed:true), same outward marking, through two
        #    structurally different code paths -- R1 (single-path leg,
        #    confirmed above: no batch event correlated to op1) and R2
        #    (batch-path leg, confirmed above: batchFallback.fetched present).
        #
        # AC3 proven-to-fail discharge (structural-review path, CLAUDE.md
        # gts-tz3j, decided 2026-09-02 -- gts-vl44's fix is already deployed
        # and not easily revertible live, so this traces the counterfactual
        # instead of attempting a live revert/redeploy):
        #   Guard code: SyncManager.js:2911-2921, inside
        #   _fetchDriveDocMetadataBatch's request-building loop, each part's
        #   GET line ends with
        #     '&' + _DRIVE_ITEM_PARAMS + ' HTTP/1.1\r\n\r\n'
        #   where _DRIVE_ITEM_PARAMS carries 'supportsAllDrives=true' (the
        #   same constant _driveUrl uses for _fetchSingleDocMetadata's own
        #   request, SyncManager.js:3032).
        #   Counterfactual: remove '&' + _DRIVE_ITEM_PARAMS from line 2920's
        #   template literal. R1 and R2 are both plain My-Drive test docs
        #   (this environment provisions no test Shared Drive folder --
        #   see module docstring, case (b)), so removing supportsAllDrives
        #   would NOT change either leg's outcome here -- that flag only
        #   affects Shared-Drive-hosted items. Only a REAL Shared-Drive-
        #   hosted doc (case (b)) would flip from 'found' (single path, flag
        #   present) to 'gone' (batch path, flag removed) -- exactly
        #   gts-vl44's reported symptom. Verdict: HOLDS WITH CAVEAT -- the
        #   counterfactual is correctly traced and the removed guard clause
        #   is exactly the line gts-vl44 fixed, but neither this test's
        #   fixtures nor case (a)'s can exercise the caveat's fork; only a
        #   live Shared Drive doc would (case (b), not drivable here).
        assert bool(trashed_1) and bool(trashed_2), (
            "[zc0w] PARITY FAILURE: a trashed doc's verdict differed between the "
            f"single-doc path (leg 1: docNotFound.trashed={bool(trashed_1)}) and the "
            f"batch path (leg 2: docNotFound.trashed={bool(trashed_2)})"
        )

        # ── Durability + entry-point tagging on R3 (the one doc in this test
        #    expected to SURVIVE) -- project rule: verify_consistency() requires
        #    ≥1 verify_all_expectations() call in the same scenario. ──────────
        def _durable_r3() -> str | None:
            rows = r3.find_sheet_actions()
            if not rows:
                return "[zc0w] R3 Actions rows disappeared"
            for row in rows:
                if row.sync_status == "Doc Not Found":
                    return f"[zc0w] R3 row {row.global_id!r} wrongly marked Doc Not Found"
            return None

        r3.expect_callable(_durable_r3, on=SHEET, tag="[zc0w probe parity gone]", entry_point="syncAll")
        r3.checkpoint(STEP)
        settled_r3 = next(r for r in r3.find_sheet_actions() if r.global_id == r3_rows[0].global_id)
        r3.verify_all_expectations(settled_r3, tag="[zc0w probe parity gone]", entry_point="syncAll")
        r3.checkpoint(CheckpointKind.INTEGRITY)
        r3.verify_consistency(scope=SHEET)
    finally:
        for scn in (r1, r2, r3):
            scn.engine.close()
