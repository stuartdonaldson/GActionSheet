"""
test_poc_features.py — GTaskSheet-0n3

POC: verify edit action propagation and async sheet update.

Layer 1 (HTTP) — ONE scenario:
  seed → submit edit via set_status_from_preview wrapper → QUEUE enqueued →
  process_pending_sheet_updates → QUEUE drained → durable sheet status.

Layer 2 (Playwright) minimal/warn-level: Acts 4–5 of test_journey.py cover
preview-card visibility; not re-implemented here.

Note on set_status_from_preview fixture: the handler calls
DocumentApp.getActiveDocument() which may return null when invoked via HTTP
(doPost context, standalone script). If the fixture raises FixtureError, this
is an implementation gap in the fixture wrapper (not a feature regression).
"""
import urllib.parse
import pytest

from scn.ai import ai
from scn.session import ScenarioSession
from scn.surfaces import SheetReader
from tests.helpers.download import download_xlsx

ACTION_CHIP_URL_BASE = "https://northlakeuu.org/NUUTS"


def _chip_url(global_id: str) -> str:
    """Construct the chip URL that _setStatusFromPreview expects."""
    return f"{ACTION_CHIP_URL_BASE}?c=view&globalId={urllib.parse.quote(global_id, safe='')}"


@pytest.fixture(scope="module")
def scn(settings):
    s = ScenarioSession.new_doc(settings)
    yield s
    s.close()


def test_poc_edit_action_propagation(scn, settings):
    """GTaskSheet-0n3 Layer 1: submit edit via fixture wrapper; drain queue; assert sheet status."""
    sheet_id = settings["testSheetId"]

    # ── Step 1: seed one action and sync ─────────────────────────────────────
    action = ai(
        action="0n3 poc edit action for async sheet update verification",
        status="Open",
    )
    scn.append_paragraph(action.as_text())
    scn.sync()

    rows = scn.find_sheet_actions()
    matching = [r for r in rows if r.action == action.action]
    assert len(matching) == 1, f"[0n3] expected 1 row after sync, got {len(matching)}"
    action.action_id = matching[0].action_id
    action.status = "Open"

    global_id = f"{scn.doc_id}/{action.action_id}"
    chip_url = _chip_url(global_id)

    # ── Step 2: submit edit via set_status_from_preview fixture wrapper ───────
    # This exercises _setStatusFromPreview: scans the doc, flushes the paragraph
    # via REST API, enqueues a sheet update in ACTION_SHEET_QUEUE.
    # Expected completion signal: POC_EDIT_ACTION.complete logged.
    #
    # Implementation note: _setStatusFromPreview calls DocumentApp.getActiveDocument()
    # which returns null in HTTP context (standalone script, no active doc).
    # If FixtureError is raised here, the fixture wrapper needs refactoring to
    # accept testDocId explicitly (known gap in por0 implementation).
    new_status = "In Progress"
    scn._post_fixture("set_status_from_preview", {
        "url": chip_url,
        "newStatus": new_status,
    })

    # After set_status_from_preview: the sheet row should NOT yet have the new status
    # (update is async — queued in ACTION_SHEET_QUEUE, not written to sheet yet).
    # Note: the fixture also updates the doc paragraph via REST; this is not asserted
    # here as Layer 1 focuses on the sheet propagation path.
    xlsx_pre_drain = download_xlsx(sheet_id)
    pre_drain_rows = SheetReader().read(xlsx_pre_drain, scn.doc_id)
    pre_drain_row = next((r for r in pre_drain_rows if r.action_id == action.action_id), None)
    assert pre_drain_row is not None, "[0n3] row not found in sheet before drain"
    # Status must not be updated yet (queue has not been drained)
    assert getattr(pre_drain_row, "status", None) != new_status, (
        f"[0n3] sheet row already shows new status before drain — "
        f"expected async (queue not yet drained), got {pre_drain_row.status!r}"
    )

    # ── Step 3: drain the queue via process_pending_sheet_updates ────────────
    # This exercises _processPendingSheetUpdates: reads ACTION_SHEET_QUEUE,
    # calls upsert_action_rows for each entry, clears the queue.
    # Expected completion signal: POC_ASYNC_SHEET.complete logged.
    scn._post_fixture("process_pending_sheet_updates")

    # ── Step 4: assert durable sheet status ──────────────────────────────────
    xlsx_post_drain = download_xlsx(sheet_id)
    post_drain_rows = SheetReader().read(xlsx_post_drain, scn.doc_id)
    post_drain_row = next((r for r in post_drain_rows if r.action_id == action.action_id), None)
    assert post_drain_row is not None, "[0n3] row not found in sheet after drain"
    assert getattr(post_drain_row, "status", None) == new_status, (
        f"[0n3] expected sheet status={new_status!r} after queue drain, "
        f"got {getattr(post_drain_row, 'status', None)!r}"
    )
