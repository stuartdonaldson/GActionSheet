"""
test_uuse_scoped_listing.py — gts-uuse

Regression coverage for gts-uuse: syncAll's Drive metadata listing is now
scoped to known TeamData folders (direct children only) instead of every
Google Doc the executing identity can see account-wide, with a per-doc
fallback (reusing _fetchSingleDocMetadata's three-state contract) for any
tracked doc absent from the scoped listing, and — the piece with no prior
coverage at all — that fallback is BATCHED via Drive API's batch endpoint
(https://www.googleapis.com/batch/drive/v3) when more than one doc needs it
in the same sweep, rather than firing one files.get per doc in a loop.

This environment has no test Shared Drive folder id provisioned (see
test_sync_all.py's gts-rskf comment, same constraint), so the "does a
Shared-Drive-hosted doc under a scoped team folder still list correctly"
half of gts-uuse's AC1 can't be exercised end-to-end live here either. What
IS provable without a real Shared Drive: the scoped listing's own fallback
path — the exact mechanism gts-rskf already depends on to never mark a live
doc Doc Not Found on a mere listing absence — behaves identically whether a
doc is absent from the listing because it's on a Shared Drive the query
didn't reach, or (as the new 'sync_all_force_listing_miss_multi' fixture
simulates) because it isn't a direct child of any configured TeamData folder.
Both funnel through the same "confirm before condemning" per-doc lookup, now
batched.

Backstop: 'sync.driveMetadata.batchFallback.fetched' and the batched-vs-
sequential behavior did not exist before gts-uuse — pre-fix, syncAll's
per-doc fallback (line ~491, _fetchSingleDocMetadata) fired once per missing
doc with no batching at all, so a build predating this change would show ZERO
'sync.driveMetadata.batchFallback.fetched' events (the tag itself is new) for
this same scenario, not one.
"""
import uuid

import pytest

from scn.engine import CheckpointKind, Surface
from scn.session import ScenarioSession

SHEET = Surface.SHEET
STEP = CheckpointKind.STEP


def _post_fixture_patient(scn, fixture_name: str, extra: dict | None = None, timeout: int = 600) -> dict:
    """Same convention as test_sync_all.py's helper of the same name — this
    fixture re-runs the real syncAll() over the whole production backlog, not
    just this test's own docs, so it inherits the same longer client timeout."""
    payload = {
        "action": "run_fixture",
        "testToken": scn.settings.get("testToken") or "",
        "fixture": fixture_name,
        "testDocId": scn.doc_id,
    }
    if extra:
        payload.update(extra)
    return scn._post(payload, timeout=timeout)


def test_syncall_batches_multi_doc_listing_miss_fallback(settings, gas_log_dir, request):
    """[gts-uuse] Two docs simultaneously absent from the (now-scoped) Drive
    metadata listing in the same syncAll() sweep are resolved by ONE batched
    fallback call (_fetchDriveDocMetadataBatch), not two sequential
    _fetchSingleDocMetadata calls — and both docs' rows survive the sweep
    exactly as gts-rskf's single-doc listing-miss case already guarantees."""
    if not gas_log_dir:
        pytest.skip("gas_log_dir not configured — call-count assertions require GAS log access")

    from tests.helpers.gas_log import clear_logs, collect_logs, matches_op, wait_for_log

    scn_a = ScenarioSession.new_doc(settings, request=request)
    scn_b = ScenarioSession.new_doc(settings, request=request)
    try:
        scn_a.append_paragraph("AI-1: uuse multi-listing-miss doc A")
        scn_a.sync()
        scn_b.append_paragraph("AI-1: uuse multi-listing-miss doc B")
        scn_b.sync()

        pre_rows_a = scn_a.find_sheet_actions()
        pre_rows_b = scn_b.find_sheet_actions()
        assert pre_rows_a, "[uuse] expected ≥1 Actions row for doc A before the forced-miss sweep"
        assert pre_rows_b, "[uuse] expected ≥1 Actions row for doc B before the forced-miss sweep"
        pre_statuses_a = {r.global_id: r.sync_status for r in pre_rows_a}
        pre_statuses_b = {r.global_id: r.sync_status for r in pre_rows_b}

        # op-correlation (gts-obry.1): scope this sweep's own opId so the
        # exactly-ONE batch assertion below can't be inflated by an unrelated
        # concurrent syncAll (the account's 30-min trigger, or another
        # session) landing in the same fence window — see matches_op's
        # docstring.
        sweep_op_id = str(uuid.uuid4())
        fence = clear_logs(gas_log_dir)
        _post_fixture_patient(
            scn_a, "sync_all_force_listing_miss_multi",
            extra={"docIds": [scn_a.doc_id, scn_b.doc_id], "opId": sweep_op_id},
        )
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.all.complete", timeout_s=90, after=fence)

        batch_events = collect_logs(
            gas_log_dir,
            matches_op(lambda e: e.get("tag") == "sync.driveMetadata.batchFallback.fetched", sweep_op_id),
            after=fence,
        )
        assert len(batch_events) == 1, (
            f"[uuse] expected exactly ONE batched fallback call for 2 simultaneously-missing "
            f"docs, got {len(batch_events)}: {batch_events!r}"
        )
        assert (batch_events[0].get("data") or {}).get("count") == 2, (
            f"[uuse] batched fallback call should report count=2, got {batch_events[0]!r}"
        )

        error_events = collect_logs(
            gas_log_dir,
            matches_op(lambda e: e.get("tag") == "sync.driveMetadata.batchFallback.error", sweep_op_id),
            after=fence,
        )
        assert not error_events, (
            f"[uuse] batch/drive/v3 request degraded to the sequential fallback path "
            f"(should have succeeded): {error_events!r}"
        )

        # Both docs must survive exactly like gts-rskf's single-doc listing-miss
        # case: absence from the (now-scoped) bulk listing is never, by itself,
        # proof of deletion.
        for scn, pre_rows, pre_statuses, label in (
            (scn_a, pre_rows_a, pre_statuses_a, "A"),
            (scn_b, pre_rows_b, pre_statuses_b, "B"),
        ):
            post_rows = scn.find_sheet_actions()
            assert len(post_rows) == len(pre_rows), (
                f"[uuse] doc {label} Actions row count changed after a forced multi-listing-miss "
                f"sweep: before={len(pre_rows)} after={len(post_rows)}"
            )
            for row in post_rows:
                assert row.sync_status != "Doc Not Found", (
                    f"[uuse] doc {label} row {row.global_id!r} marked 'Doc Not Found' after a "
                    f"forced multi-listing-miss sweep — batched fallback did not save it"
                )
                prior = pre_statuses.get(row.global_id)
                assert row.sync_status == (prior or ""), (
                    f"[uuse] doc {label} row {row.global_id!r} sync_status changed: "
                    f"{prior!r} -> {row.sync_status!r}"
                )

        def _durable(scn):
            def _check() -> str | None:
                rows = scn.find_sheet_actions()
                if not rows:
                    return "[uuse] Actions rows disappeared after forced multi-listing-miss sweep"
                for row in rows:
                    if row.sync_status == "Doc Not Found":
                        return f"[uuse] row {row.global_id!r} marked Doc Not Found"
                return None
            return _check

        scn_a.expect_callable(_durable(scn_a), on=SHEET, tag="[uuse batched fallback A]", entry_point="syncAll")
        scn_a.checkpoint(STEP)
        scn_b.expect_callable(_durable(scn_b), on=SHEET, tag="[uuse batched fallback B]", entry_point="syncAll")
        scn_b.checkpoint(STEP)

        settled_a = next(r for r in scn_a.find_sheet_actions() if r.global_id == pre_rows_a[0].global_id)
        scn_a.verify_all_expectations(settled_a, tag="[uuse batched fallback]", entry_point="syncAll")
        scn_a.checkpoint(CheckpointKind.INTEGRITY)
        scn_a.verify_consistency(scope=SHEET)
    finally:
        for scn in (scn_a, scn_b):
            scn.engine.close()


def test_syncall_survives_garbage_teamdata_folder_id(settings, gas_log_dir, request):
    """[gts-moy1.2] A TeamData row with a placeholder Folder Id ('-NA-', the
    literal value the live sheet used to mean "no dedicated folder for this
    team") must not poison syncAll()'s scoped Drive listing query for the
    rest of the account.

    Root cause: _fetchDriveDocMetadata built ONE combined files.list query
    ORing every TeamData folderId's `'<id>' in parents` clause together with
    zero validation. An implausible id (like '-NA-') made Drive reject the
    WHOLE query with HTTP 404 — which threw, and (compounding bug) the
    per-doc fallback safety net was gated behind `if (driveMetadata)`, so a
    thrown listing call silently skipped BOTH the scoped listing AND its own
    fallback for every tracked doc account-wide, not just the doc(s)
    associated with the bad TeamData row.

    Backstop: this assertion is proven to fail against the pre-fix build —
    the bad row alone produces a 404 that throws inside _fetchDriveDocMetadata
    (confirmed live during gts-moy1.1 Stage 1 triage with a temporary
    diagnostic log), so `sync.driveMetadata.error` fires and the doc below
    would surface either as an error or (via the compounding bug) skip
    metadata-driven detection entirely for the sweep."""
    if not gas_log_dir:
        pytest.skip("gas_log_dir not configured — log-based assertions require GAS log access")

    from tests.helpers.gas_log import clear_logs, collect_logs, wait_for_log

    scn = ScenarioSession.new_doc(settings, request=request)
    garbage_team_id = "_TEST_GTMOY12_GARBAGE"
    try:
        scn.append_paragraph("AI-1: moy1.2 garbage-folder-id survival action")
        scn.sync()
        pre_rows = scn.find_sheet_actions()
        assert pre_rows, "[moy1.2] expected ≥1 Actions row before the garbage-row sweep"
        pre_statuses = {r.global_id: r.sync_status for r in pre_rows}

        seed_result = scn._post_fixture("seed_garbage_teamdata_row", {
            "teamId": garbage_team_id, "folderId": "-NA-",
        })
        assert (seed_result.get("data") or {}).get("folderId") == "-NA-", (
            f"[moy1.2] seed_garbage_teamdata_row did not write the expected placeholder: "
            f"{seed_result!r}"
        )

        fence = clear_logs(gas_log_dir)
        _post_fixture_patient(scn, "sync_all")
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.all.complete", timeout_s=600, after=fence)

        rejected_events = collect_logs(
            gas_log_dir, lambda e: e.get("tag") == "sync.driveMetadata.folderIdRejected", after=fence,
        )
        assert rejected_events, (
            "[moy1.2] expected the '-NA-' folder id to be logged as rejected/excluded from "
            "the scoped listing query, found no sync.driveMetadata.folderIdRejected event"
        )

        error_events = collect_logs(
            gas_log_dir, lambda e: e.get("tag") == "sync.driveMetadata.error", after=fence,
        )
        assert not error_events, (
            f"[moy1.2] scoped Drive listing threw despite the garbage TeamData folder id — "
            f"filtering did not prevent the poisoned query: {error_events!r}"
        )

        post_rows = scn.find_sheet_actions()
        assert len(post_rows) == len(pre_rows), (
            f"[moy1.2] Actions row count changed after a syncAll sweep with a garbage "
            f"TeamData folder id present: before={len(pre_rows)} after={len(post_rows)}"
        )
        for row in post_rows:
            assert row.sync_status != "Doc Not Found", (
                f"[moy1.2] row {row.global_id!r} marked 'Doc Not Found' after a syncAll sweep "
                f"with a garbage TeamData folder id present — the fallback safety net was "
                f"suppressed for the whole account, not just the bad row's own team"
            )
            prior = pre_statuses.get(row.global_id)
            assert row.sync_status == (prior or ""), (
                f"[moy1.2] row {row.global_id!r} sync_status changed: "
                f"{prior!r} -> {row.sync_status!r}"
            )
    finally:
        scn._post_fixture("remove_teamdata_row_by_team_id", {"teamId": garbage_team_id})
        scn.engine.close()
