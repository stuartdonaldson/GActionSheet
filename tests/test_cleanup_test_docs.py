"""
test_cleanup_test_docs.py — [TST] gts-ve6z, twin of [IMP] gts-97ol.

Entry-point coverage for menuCleanupTestDocs() (MenuHandler.js), driven
through its own 'menu_cleanup_test_docs' run_fixture wrapper (mirrors
test_menu_entry_points.py's menu_run_archive pattern) — the entry point
itself is the call-site, not ArchiveManager.purgeByPrefix directly.

Uses a session-unique 'Test Doc Prefix' Config value (never the shared
default 'GActionSheet-Test-') so this test can never delete another
concurrent test run's rows in the shared TEST spreadsheet, and restores the
Config key's ORIGINAL value on exit via set_config_row rather than
clear_config_rows — this repo's shared TEST Config sheet carries real,
human-authored style/indent settings (ai_token, SR Indent, ...) that a blanket
clear_config_rows would destroy; only the single 'Test Doc Prefix' row is
ever touched here.

Coverage-inventory note (implementation-gate Step 7(a)): this suite drives
menuCleanupTestDocs() only via run_fixture, which has no interactive Sheets
UI — SpreadsheetApp.getUi() throws inside the handler and it takes the
documented no-confirm branch (see that function's own doc comment). The
interactive YES/NO confirm-dialog branch has no headless equivalent and is
NOT covered by this suite — recorded here as deferred/manual-verification-only,
not silently bypassed.
"""
import secrets

from scn.session import ScenarioSession
from scn.ai import ai
from tests.helpers.download import download_xlsx, fetch_doc_title
from tests.helpers.sheet_inspect import load_sheet, rows_for_doc


def _docdata_row(scn, doc_id: str):
    resp = scn._post_fixture("get_docdata_row", {"fileId": doc_id})
    return (resp.get("data") or {}).get("row")


def _current_prefix_row(scn):
    resp = scn._post_fixture("get_config_rows", {})
    rows = (resp.get("data") or {}).get("rows") or []
    for row in rows:
        if row.get("key") == "Test Doc Prefix":
            return row.get("raw")
    return None


def _set_prefix(scn, prefix: str) -> None:
    resp = scn._post_fixture("set_config_row", {"key": "Test Doc Prefix", "value": prefix})
    assert (resp.get("data") or {}).get("ok"), f"[gts-ve6z] set_config_row(Test Doc Prefix) failed: {resp!r}"


def test_menuCleanupTestDocs_deletes_matching_and_spares_other_prefix(settings, request):
    """Two journey docs are created under two DISTINCT session-unique prefixes
    (each via ScenarioSession.new_doc(), which names the doc through
    _testDocName() — itself now reading the same Config key, gts-97ol). Both
    are synced (registers one Actions row + one DocData row each). Running
    menuCleanupTestDocs() configured to prefix1 only must delete prefix1's
    Actions+DocData rows and leave prefix2's untouched — proving the prefix
    match is selective on doc_name, not a blanket sweep."""
    unique = secrets.token_hex(4)
    prefix1 = f"GActionSheet-Test-cleanup1-{unique}-"
    prefix2 = f"GActionSheet-Test-cleanup2-{unique}-"

    probe = ScenarioSession.new_doc(settings, request=request)
    original_prefix_raw = _current_prefix_row(probe)
    probe.close()

    scn1 = None
    scn2 = None
    try:
        _set_prefix_via_scratch(settings, request, prefix1)
        scn1 = ScenarioSession.new_doc(settings, request=request)
        title1 = fetch_doc_title(scn1.doc_id)
        assert title1.startswith(prefix1), (
            f"[gts-ve6z] scn1 doc title {title1!r} does not start with configured prefix1 "
            f"{prefix1!r} -- _testDocName() not reading the configured 'Test Doc Prefix' key"
        )
        act1 = ai(action="menuCleanupTestDocs prefix1 seeded action (must be deleted)")
        scn1.append_paragraph(act1.as_text())
        scn1.sync()

        _set_prefix_via_scratch(settings, request, prefix2)
        scn2 = ScenarioSession.new_doc(settings, request=request)
        title2 = fetch_doc_title(scn2.doc_id)
        assert title2.startswith(prefix2), (
            f"[gts-ve6z] scn2 doc title {title2!r} does not start with configured prefix2 {prefix2!r}"
        )
        act2 = ai(action="menuCleanupTestDocs prefix2 seeded action (must survive)")
        scn2.append_paragraph(act2.as_text())
        scn2.sync()

        sheet_id = settings["testSheetId"]
        pre_actions1 = rows_for_doc(load_sheet(download_xlsx(sheet_id), sheet_name="Actions"), scn1.doc_id)
        assert len(pre_actions1) >= 1, "[gts-ve6z] precondition: scn1 Actions row missing before cleanup"
        assert _docdata_row(scn1, scn1.doc_id) is not None, (
            "[gts-ve6z] precondition: scn1 DocData row missing before cleanup"
        )
        pre_actions2 = rows_for_doc(load_sheet(download_xlsx(sheet_id), sheet_name="Actions"), scn2.doc_id)
        assert len(pre_actions2) >= 1, "[gts-ve6z] precondition: scn2 Actions row missing before cleanup"
        assert _docdata_row(scn2, scn2.doc_id) is not None, (
            "[gts-ve6z] precondition: scn2 DocData row missing before cleanup"
        )

        # Point Config back at prefix1 and run the real entry point.
        _set_prefix(scn1, prefix1)
        result = scn1._post_fixture("menu_cleanup_test_docs")
        data = result.get("data") or {}
        assert data.get("prefix") == prefix1, f"[gts-ve6z] unexpected resolved prefix: {data!r}"
        assert data.get("actionsDeleted", 0) >= 1, f"[gts-ve6z] expected >=1 Actions row deleted: {data!r}"
        assert data.get("docDataDeleted", 0) >= 1, f"[gts-ve6z] expected >=1 DocData row deleted: {data!r}"

        xlsx = download_xlsx(sheet_id)
        post_actions1 = rows_for_doc(load_sheet(xlsx, sheet_name="Actions"), scn1.doc_id)
        assert post_actions1 == [], (
            f"[gts-ve6z] prefix1 Actions row(s) survived menuCleanupTestDocs: {post_actions1!r}"
        )
        assert _docdata_row(scn1, scn1.doc_id) is None, (
            "[gts-ve6z] prefix1 DocData row survived menuCleanupTestDocs"
        )

        post_actions2 = rows_for_doc(load_sheet(xlsx, sheet_name="Actions"), scn2.doc_id)
        assert len(post_actions2) >= 1, (
            "[gts-ve6z] prefix2 (non-matching) Actions row was deleted -- cleanup was not selective"
        )
        assert _docdata_row(scn2, scn2.doc_id) is not None, (
            "[gts-ve6z] prefix2 (non-matching) DocData row was deleted -- cleanup was not selective"
        )
    finally:
        _restore_prefix(settings, request, original_prefix_raw)
        if scn1 is not None:
            scn1.close()
        if scn2 is not None:
            scn2.close()


def _set_prefix_via_scratch(settings, request, prefix: str) -> None:
    scratch = ScenarioSession.new_doc(settings, request=request)
    try:
        _set_prefix(scratch, prefix)
    finally:
        scratch.close()


def _restore_prefix(settings, request, original_raw) -> None:
    """Restores 'Test Doc Prefix' to whatever it held before this test ran
    (or the documented default, when it had no row at all) — via
    set_config_row on that single key only, NEVER clear_config_rows, which
    would wipe every other human-authored Config row on the shared sheet."""
    restore_value = original_raw if original_raw is not None else "GActionSheet-Test-"
    _set_prefix_via_scratch(settings, request, restore_value)
