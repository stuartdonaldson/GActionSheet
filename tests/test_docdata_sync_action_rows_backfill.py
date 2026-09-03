"""
test_docdata_sync_action_rows_backfill.py — gts-qjnf (stage `docdata-eviction`,
knowledge-base/staging/docdata-litter-apt-speed.md).

Path B entry-point audit gap: `WebApp.js`'s `_handleSyncActionRows` (the
`sync_action_rows` webapp route, HTTP-POSTed by `SyncManager.js`'s
`_syncActionRows` on every regular `syncDocument()`/`scn.sync()` call, not
just the `syncAll()` 30-min sweep) carries its own gts-pz8o blank-docName
fallback at `WebApp.js:1421` -- independent of, and textually distinct from,
`SyncManager.js`'s integrity-pass fallback exercised by
`tests/test_sync_all.py`'s `[cduk AC2]`. Before this test, that fallback had
no durable-state assertion tagged to the `sync_action_rows` entry point
itself: `tests/test_b7_write_routes.py`'s `[rz4k.2 sync_action_rows]` checks
only the Actions-row write, and `[cduk AC2]` reaches `WebApp.js:1421` only
transitively through a `sync_all_force_listing_miss` sweep, tagged to
`syncAll` instead.

This seeds a DocData row with a blank Doc Name (the sticky-default shape
`gts-pz8o` fixed), then syncs the doc directly (`scn.sync()`, no `syncAll`
sweep involved) and asserts the row is backfilled from the request's own
`docTitle` -- proving the `sync_action_rows` call site itself, not just the
`syncAll` sweep it is usually observed through.
"""
from scn.session import ScenarioSession


def _docdata(scn):
    resp = scn._post_fixture("get_docdata_row")
    return (resp.get("data") or {}).get("row")


def test_sync_action_rows_backfills_blank_doc_name(settings, request):
    """[gts-qjnf] sync_action_rows (WebApp.js:1421) backfills a blank
    DocData.docName from the request's docTitle -- the same gts-pz8o
    contract test_sync_all.py's [cduk AC2] proves for the syncAll integrity
    pass, asserted here at its own entry point."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn.append_paragraph("AI-1: qjnf sync_action_rows backfill probe")
        scn.sync()

        before = _docdata(scn)
        assert before is not None, "[qjnf] DocData row missing after initial sync"
        assert before.get("docName"), (
            "[qjnf setup] expected a non-blank docName after the initial sync"
        )

        scn._post_fixture("set_docdata_row", {"docName": ""})
        blanked = _docdata(scn)
        assert blanked is not None and blanked.get("docName") == "", (
            f"[qjnf setup] set_docdata_row did not blank docName: {blanked!r}"
        )

        # entry_point: sync_action_rows -- scn.sync() drives syncDocument(),
        # which POSTs this route directly (SyncManager.js's _syncActionRows);
        # no syncAll() sweep is involved in this call path.
        scn.sync()

        after = _docdata(scn)
        assert after is not None, "[qjnf] DocData row missing after backfill sync"
        assert after.get("docName"), (
            f"[qjnf] sync_action_rows did not backfill a blank docName "
            f"(WebApp.js:1421 gts-pz8o fallback): {after!r}"
        )
    finally:
        scn.close()
