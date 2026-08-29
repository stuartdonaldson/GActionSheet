"""
test_export_dialog.py — gts-0002, [TST] twin of gts-s7ut (classic-menu
Export dialog: Ui.showModalDialog + google.script.run progress).

Authored against gts-s7ut's frozen pre-code contract only (entry-point
signatures, EXPORT_STATUS_ ScriptProperty schema, above in gts-s7ut's
description) — this file does not read gts-s7ut's implementation code or
ExportProgressDialog.html (no-shared-context rule).

Entry points: runExportForDialog(docId, exportPdf) and
getExportProgressForDialog(docId) in src/Procedure-Exporter.js. Both are
plain functions (not CardService/Ui-bound), so — per the pre-code contract —
they're callable headlessly the same way exportDocument_ already is
(gts-2glm's export_document_json route): this bead adds two mirroring
WebApp.js test-support routes, run_export_for_dialog_test and
get_export_progress_for_dialog_test, that call them directly rather than
via google.script.run (which has no headless client outside a live HtmlService
dialog session).

Concurrency note: runExportForDialog runs exportDocument_() synchronously
end-to-end, so observing the durable 'running' EXPORT_STATUS_ state requires
polling from a second, concurrent HTTP request while the first is still in
flight (mirroring how the real dialog polls while google.script.run's
runExportForDialog call is outstanding). A background thread drives the run;
the main thread polls get_export_progress_for_dialog_test until either a
'running' status is observed or the run completes.
"""
import threading
import time

import pytest

from scn.session import FixtureError, ScenarioSession


# ---------------------------------------------------------------------------
# Seed-content helpers (Docs API batchUpdate passthrough; test-only — mirrors
# tests/test_document_export.py's helpers so this file needs no shared
# context with gts-s7ut's implementation, only the existing seed routes).
# ---------------------------------------------------------------------------

def _end_index(scn: ScenarioSession) -> int:
    resp = scn._post_route("dump_doc_paragraphs", {"docId": scn.doc_id})
    elements = resp["elements"]
    return elements[-1]["end"] - 1


def _insert_text(scn: ScenarioSession, text: str) -> tuple[int, int]:
    start = _end_index(scn)
    resp = scn._post_route("seed_doc_content", {
        "docId": scn.doc_id,
        "requests": [{"insertText": {"location": {"index": start}, "text": text}}],
    })
    assert resp.get("ok"), resp
    return start, start + len(text)


def _style_paragraph(scn: ScenarioSession, start: int, end: int, named_style: str) -> None:
    resp = scn._post_route("seed_doc_content", {
        "docId": scn.doc_id,
        "requests": [{"updateParagraphStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "paragraphStyle": {"namedStyleType": named_style},
            "fields": "namedStyleType",
        }}],
    })
    assert resp.get("ok"), resp


def _insert_heading(scn: ScenarioSession, text: str, level: int = 1) -> tuple[int, int]:
    start, end = _insert_text(scn, text + "\n")
    _style_paragraph(scn, start, end - 1, f"HEADING_{level}")
    return start, end


def _run_export_for_dialog(scn: ScenarioSession, doc_id: str, export_pdf: bool = False) -> dict:
    return scn._post_route("run_export_for_dialog_test", {"docId": doc_id, "exportPdf": export_pdf})


def _get_export_progress(scn: ScenarioSession, doc_id: str) -> dict:
    resp = scn._post_route("get_export_progress_for_dialog_test", {"docId": doc_id})
    assert resp.get("ok"), resp
    return resp["status"]


def _pad_with_stage_latency(scn: ScenarioSession, n: int = 25) -> None:
    """Enough real content that runExportForDialog's synchronous
    exportDocument_() call spans multiple real Docs-API round trips, giving
    the concurrent poll below a realistic window to observe the 'running'
    EXPORT_STATUS_ state before it flips to 'done'."""
    for i in range(n):
        _insert_text(scn, f"Body paragraph number {i} padding export dialog timing.\n")


# ---------------------------------------------------------------------------
# Entry-point coverage: runExportForDialog / getExportProgressForDialog
# call-sites + durable EXPORT_STATUS_ state (running -> done)
# ---------------------------------------------------------------------------

def test_export_dialog_status_transitions_running_then_done(settings, request):
    """Call-site coverage for both entry points named in gts-s7ut's AC:
    getExportProgressForDialog observes state='running' while
    runExportForDialog is still in flight (concurrent poll from a background
    thread), then state='done' with the same jsonFileId once it returns —
    durable-state assertion on EXPORT_STATUS_<docId>, not just the response."""
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_heading(scn, "Board Policy 1: Dialog Export Timing", level=1)
    _pad_with_stage_latency(scn)

    result_holder: dict = {}

    def _run():
        result_holder["resp"] = _run_export_for_dialog(scn, scn.doc_id, export_pdf=False)

    thread = threading.Thread(target=_run)
    thread.start()

    observed_running = False
    deadline = time.monotonic() + 60
    while thread.is_alive() and time.monotonic() < deadline:
        status = _get_export_progress(scn, scn.doc_id)
        if status and status.get("state") == "running":
            observed_running = True
            break
        time.sleep(0.1)

    thread.join(timeout=60)
    assert not thread.is_alive(), "runExportForDialog did not complete within the test deadline"
    assert observed_running, (
        "expected getExportProgressForDialog to observe EXPORT_STATUS_ state='running' "
        "while runExportForDialog was still in flight"
    )

    resp = result_holder["resp"]
    assert resp.get("ok"), resp
    assert resp.get("jsonFileId")

    final_status = _get_export_progress(scn, scn.doc_id)
    assert final_status["state"] == "done"
    assert final_status["jsonFileId"] == resp["jsonFileId"]
    assert final_status["stageIndex"] == final_status["totalStages"]


def test_export_dialog_no_status_before_first_run(settings, request):
    """getExportProgressForDialog returns null for a docId that has never
    had runExportForDialog invoked against it — the 'no export yet' case is
    distinct from any in-progress or terminal state."""
    scn = ScenarioSession.new_doc(settings, request=request)
    status = _get_export_progress(scn, scn.doc_id)
    assert status is None


# ---------------------------------------------------------------------------
# Returned {jsonFileId, pdfFileId} shape
# ---------------------------------------------------------------------------

def test_export_dialog_run_export_json_only_omits_pdf_file_id(settings, request):
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_heading(scn, "Board Policy 2: JSON-Only Dialog Export", level=1)
    _insert_text(scn, "Body text for a JSON-only dialog export.\n")

    resp = _run_export_for_dialog(scn, scn.doc_id, export_pdf=False)
    assert resp.get("ok"), resp
    assert resp.get("jsonFileId")
    assert "pdfFileId" not in resp or resp.get("pdfFileId") is None


def test_export_dialog_run_export_with_pdf_returns_both_file_ids(settings, request):
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_heading(scn, "Board Policy 3: JSON+PDF Dialog Export", level=1)
    _insert_text(scn, "Body text for a JSON+PDF dialog export.\n")

    resp = _run_export_for_dialog(scn, scn.doc_id, export_pdf=True)
    assert resp.get("ok"), resp
    assert resp.get("jsonFileId")
    assert resp.get("pdfFileId")

    final_status = _get_export_progress(scn, scn.doc_id)
    assert final_status["state"] == "done"
    assert final_status["jsonFileId"] == resp["jsonFileId"]
    assert final_status["pdfFileId"] == resp["pdfFileId"]


# ---------------------------------------------------------------------------
# Error path
# ---------------------------------------------------------------------------

def test_export_dialog_run_export_error_path_sets_durable_error_status(settings, request):
    """A docId that cannot be exported (does not exist / not accessible)
    surfaces as {error} from the route (runExportForDialog rethrows per its
    own contract — ScenarioSession._post_route raises FixtureError on any
    {error} response) AND as a durable EXPORT_STATUS_ state='error' with a
    non-empty errorMessage — the dialog's failure path (AC 4 in gts-s7ut)
    can read either signal."""
    scn = ScenarioSession.new_doc(settings, request=request)
    bogus_doc_id = scn.doc_id[:-4] + "0000"  # well-formed-looking but invalid docId

    with pytest.raises(FixtureError, match="run_export_for_dialog_test"):
        _run_export_for_dialog(scn, bogus_doc_id, export_pdf=False)

    status = _get_export_progress(scn, bogus_doc_id)
    assert status is not None
    assert status["state"] == "error"
    assert status.get("errorMessage")
