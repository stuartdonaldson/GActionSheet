"""
test_kkm7_batching.py — gts-kkm7.4

Twin regression coverage for gts-kkm7.1 (batch mark_doc_not_found),
gts-kkm7.2 (single files.list Drive metadata pass), and gts-kkm7.3 (batch
chip-flush GET+batchUpdate per doc). All three IMPs were already implemented
and committed (visible in `git log` before this session; see plan-fix.md
Session 4 Result) but had no dedicated regression coverage — this file is
that twin, authored against the three beads' frozen pre-code contracts
(Description/AC text in `bd show gts-kkm7.{1,2,3}`), per the no-shared-context
convention noted in plan-context.md.

Call-count assertions use GAS-side Axiom log tags already emitted by the
implementation:
  - sync.docNotFound.confirmed  — fires once per _markDocNotFound() call
    (WebApp.js _handleMarkDocNotFound), and _markDocNotFound() is itself
    called at most once per syncAll() sweep regardless of trashed-doc count.
  - sync.driveMetadata.fetched  — fires once per _fetchDriveDocMetadata()
    call, itself called at most once per syncAll() sweep.
  - flush.done                  — fires once per _flushActionParagraphs()
    call (one GET + one batchUpdate), extended with `batchSize` reporting
    how many action items were included in that one call.

Backstop: these are dedicated tests for pre-existing, already-deployed
behavior (not authored test-first against a red build). Per Session 1's
precedent for the same situation (rskf/m33k), backstop confidence here rests
on the implementation's own commit history/comments rather than a live
revert-and-fail cycle: gts-kkm7.1/.2/.3's doc-comments explicitly name what
they replaced (one-call-per-doc loops), and the log tags these assertions
check (sync.docNotFound.confirmed count==1, sync.driveMetadata.fetched
count==1, flush.done batchSize==N) did not exist in any form before the
batching change — a pre-batching build would have produced N separate
`sync.docNotFound.confirmed`-equivalent single-docId calls (old tag/shape)
and no `flush.done.batchSize` field at all, so these exact assertions could
not have passed against it.
"""
import time
import uuid

import pytest

from scn.engine import CheckpointKind, Surface
from scn.session import ScenarioSession

SHEET = Surface.SHEET
STEP = CheckpointKind.STEP


def _docdata(scn, file_id: str | None = None) -> dict | None:
    """Read the DocData row for scn's doc (or an explicit file_id) as a plain dict."""
    extra = {"fileId": file_id} if file_id else {}
    resp = scn._post_fixture("get_docdata_row", extra)
    return (resp.get("data") or {}).get("row")


def test_syncall_batches_mark_doc_not_found_and_drive_metadata(settings, gas_log_dir, request):
    """[gts-kkm7.1 / gts-kkm7.2] A syncAll() sweep with N>1 newly-trashed docs
    fires exactly one mark_doc_not_found webapp call (not N) and exactly one
    Drive files.list metadata fetch (not one DriveApp.getFileById per doc),
    stamps every affected row with the SAME modified_date (gts-4tnr), and
    mirrors 'Doc Not Found' to DocData for each trashed doc — while a live
    control doc's row is left untouched."""
    if not gas_log_dir:
        pytest.skip("gas_log_dir not configured — call-count assertions require GAS log access")

    from tests.helpers.gas_log import clear_logs, collect_logs, matches_op, wait_for_log

    scn_a = ScenarioSession.new_doc(settings, request=request)
    scn_b = ScenarioSession.new_doc(settings)
    scn_control = ScenarioSession.new_doc(settings)
    try:
        scn_a.append_paragraph("AI-1: kkm7.1/.2 batch-notfound doc A")
        scn_a.sync()
        scn_b.append_paragraph("AI-1: kkm7.1/.2 batch-notfound doc B")
        scn_b.sync()
        scn_control.append_paragraph("AI-1: kkm7.1/.2 batch-notfound control doc")
        scn_control.sync()

        control_rows = scn_control.find_sheet_actions()
        assert control_rows, "[kkm7.1] expected a control row before the sweep"
        control_before = {r.global_id: r.modified_date for r in control_rows}

        scn_a._post_fixture("trash_doc")
        scn_b._post_fixture("trash_doc")

        # clear_logs()'s fence has a 10s clock-skew grace window (see 65g1's
        # op-correlation test) — settle before fencing so the trash_doc calls'
        # own log entries don't leak into the sweep's collected window.
        time.sleep(12)

        # op-correlation (gts-obry.1): scope this sweep's own opId so the
        # exactly-ONE assertions below can't be inflated by an unrelated
        # concurrent syncAll (the account's 30-min trigger, or another
        # session) landing in the same fence window — see matches_op's
        # docstring.
        sweep_op_id = str(uuid.uuid4())
        fence = clear_logs(gas_log_dir)
        scn_control._post_fixture("sync_all", extra={"opId": sweep_op_id})
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.all.complete", timeout_s=90, after=fence)

        notfound_events = collect_logs(
            gas_log_dir,
            matches_op(lambda e: e.get("tag") == "sync.docNotFound.confirmed", sweep_op_id),
            after=fence,
        )
        assert len(notfound_events) == 1, (
            f"[kkm7.1] expected exactly ONE mark_doc_not_found webapp call for this sweep "
            f"(N>1 trashed docs batched into one), got {len(notfound_events)}: {notfound_events!r}"
        )

        drivemeta_events = collect_logs(
            gas_log_dir,
            matches_op(lambda e: e.get("tag") == "sync.driveMetadata.fetched", sweep_op_id),
            after=fence,
        )
        assert len(drivemeta_events) == 1, (
            f"[kkm7.2] expected exactly ONE Drive files.list metadata fetch for this sweep "
            f"(single batched pass replacing per-doc DriveApp calls), got {len(drivemeta_events)}: "
            f"{drivemeta_events!r}"
        )

        rows_a = scn_a.find_sheet_actions()
        rows_b = scn_b.find_sheet_actions()
        assert rows_a and rows_a[0].sync_status == "Doc Not Found", (
            f"[kkm7.1] doc A row not stamped 'Doc Not Found': {rows_a!r}"
        )
        assert rows_b and rows_b[0].sync_status == "Doc Not Found", (
            f"[kkm7.1] doc B row not stamped 'Doc Not Found': {rows_b!r}"
        )
        assert rows_a[0].modified_date == rows_b[0].modified_date, (
            f"[kkm7.1/gts-4tnr] doc A and doc B were marked Doc Not Found with DIFFERENT "
            f"modified_date timestamps in the same batched call: "
            f"{rows_a[0].modified_date!r} vs {rows_b[0].modified_date!r}"
        )

        docdata_a = _docdata(scn_a)
        docdata_b = _docdata(scn_b)
        assert docdata_a and docdata_a.get("syncStatus") == "Doc Not Found", (
            f"[kkm7.1] DocData not mirrored to 'Doc Not Found' for doc A: {docdata_a!r}"
        )
        assert docdata_b and docdata_b.get("syncStatus") == "Doc Not Found", (
            f"[kkm7.1] DocData not mirrored to 'Doc Not Found' for doc B: {docdata_b!r}"
        )

        # The live control doc's row must be completely untouched by the
        # batched call — proves the batching change didn't widen scope to
        # docs that were never in notFoundDocIds.
        control_after = {r.global_id: r.modified_date for r in scn_control.find_sheet_actions()}
        assert control_after == control_before, (
            f"[kkm7.1] control doc's row was touched by the batched mark_doc_not_found call: "
            f"before={control_before!r} after={control_after!r}"
        )
        control_rows_after = scn_control.find_sheet_actions()
        assert control_rows_after[0].sync_status != "Doc Not Found", (
            "[kkm7.1] control doc (never trashed) was incorrectly marked Doc Not Found"
        )

        scn_control.verify_consistency(scope=SHEET)
        control_rows_after[0].status = control_rows_after[0].status or "Open"
        scn_control.verify_all_expectations(control_rows_after[0], tag="[kkm7.1 control]")
        scn_control.checkpoint(CheckpointKind.INTEGRITY)
    finally:
        # scn_a's doc-trashing is deferred to new_doc(request=request)'s
        # pytest finalizer (gts-hroj); scn_b/scn_control have no `request`
        # and keep their inline trash (this test has no browser_page, so the
        # diagnostics ordering hook is a no-op here regardless).
        scn_a.engine.close()
        for s in (scn_b, scn_control):
            try:
                s._post_route("end_journey_session", {"docId": s.doc_id})
            except Exception:
                pass


def test_syncdocument_batches_flush_for_multiple_actions_single_doc(settings, gas_log_dir, request):
    """[gts-kkm7.3] A syncDocument() call with N>1 action items needing a
    flush in the SAME doc fires exactly one flush.done event reporting
    batchSize==N (one shared GET + one shared batchUpdate), and every
    action's doc paragraph (status token) is updated correctly."""
    if not gas_log_dir:
        pytest.skip("gas_log_dir not configured — call-count assertions require GAS log access")

    from tests.helpers.gas_log import clear_logs, collect_logs, wait_for_log

    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn.append_paragraph("AI-1: kkm7.3 batch-flush action one")
        scn.append_paragraph("AI-2: kkm7.3 batch-flush action two")
        scn.append_paragraph("AI-3: kkm7.3 batch-flush action three")
        scn.sync()

        rows = scn.find_sheet_actions()
        assert len(rows) == 3, f"[kkm7.3] expected 3 seeded rows, got {len(rows)}: {rows!r}"

        # Dirty all three via patch_action_status (sidebar path) so the next
        # sync() must flush all three paragraphs together — the batched
        # entry point under test.
        for r in rows:
            scn.set_status(r, "In Progress")

        fence = clear_logs(gas_log_dir)
        scn.sync()
        wait_for_log(
            gas_log_dir,
            lambda e: e.get("tag") == "flush.done" and (e.get("data") or {}).get("docId") == scn.doc_id,
            timeout_s=60,
            after=fence,
        )

        flush_events = collect_logs(
            gas_log_dir,
            lambda e: e.get("tag") == "flush.done" and (e.get("data") or {}).get("docId") == scn.doc_id,
            after=fence,
        )
        assert len(flush_events) == 1, (
            f"[kkm7.3] expected exactly ONE flush.done event (single GET+batchUpdate) for "
            f"3 changed action items in one doc, got {len(flush_events)}: {flush_events!r}"
        )
        batch_size = (flush_events[0].get("data") or {}).get("batchSize")
        assert batch_size == 3, (
            f"[kkm7.3] flush.done batchSize should report 3 (all changed items in one call), "
            f"got {batch_size!r}: {flush_events[0]!r}"
        )

        for item in scn.doc_items():
            assert item.status == "In Progress", (
                f"[kkm7.3] action {item.action_id!r} paragraph not flushed to 'In Progress': "
                f"{item.status!r}"
            )

        # Re-snapshot from the current sheet — created_date/modified_date
        # advanced when the batched flush's sync ran, and verify_all_expectations
        # pins whatever the ai carries at call time.
        settled = next(r for r in scn.find_sheet_actions() if r.global_id == rows[0].global_id)
        scn.verify_all_expectations(settled, tag="[kkm7.3 batch-flush]", entry_point="syncDocument")
        scn.checkpoint(CheckpointKind.INTEGRITY)
        scn.verify_consistency(scope=SHEET)
    finally:
        # Doc-trashing deferred to new_doc(request=request)'s pytest
        # finalizer (gts-hroj).
        scn.engine.close()
