"""
test_sync_all.py — GTaskSheet-r3d/grxl/5u2v/nv6g/cduk

One scenario: seed a mixed ActionSheet (invalid-doc, trashed-doc, unmodified-valid,
modified-valid rows), run syncAll ONCE (Sweep 1), drain per-condition expectations,
then run syncAll a SECOND time (Sweep 2) to verify Doc Not Found rows are archived.

All four beads map to expectations on the same two sweeps (§6 permutation batching).

Archive eligibility (ArchiveManager):
  - Status='Closed': Date Modified > 30 days old
  - sync_status='Doc Not Found': Date Modified > 24 hours old
    (_handleMarkDocNotFound stamps modified_date at detection time, so the timer
    starts when the doc is first detected missing — not when the action was last edited)

The invalid-doc row is backdated 2 days after Sweep 1 stamps its modified_date,
making it immediately eligible for archiving on Sweep 2.  The trashed-doc row is
stamped now during Sweep 1 and is not backdated, so it remains in Actions under
the 24-hour grace period.
"""
import secrets
import time

import pytest

from scn.ai import ai
from scn.engine import CheckpointKind, Surface
from scn.session import ScenarioSession
from scn.surfaces import SheetReader
from tests.helpers.download import download_xlsx

SHEET = Surface.SHEET
STEP = CheckpointKind.STEP


def _sheet_rows_for(settings: dict, doc_id: str) -> list:
    """Download ActionSheet and return rows scoped to doc_id (Actions tab)."""
    xlsx = download_xlsx(settings["testSheetId"])
    return SheetReader().read(xlsx, doc_id)


def _archive_rows_for(settings: dict, doc_id: str) -> list:
    """Download ActionSheet and return rows scoped to doc_id (Archive tab)."""
    xlsx = download_xlsx(settings["testSheetId"])
    return SheetReader().read(xlsx, doc_id, tab_name="Archive")


@pytest.fixture
def sync_ctx(settings, request):
    """Set up the mixed ActionSheet; yield context; teardown trashes all journey docs.

    Setup order:
      1. scn_mod: create doc, append action, sync, then append more (modified-valid)
      2. scn_unmod: create doc, append action, sync, no further mutation (unmodified-valid)
      3. scn_trash: create doc, append action, sync, then trash the doc (trashed)
      4. Seed one invalid-doc row via seed_row fixture

    The invalid docId is unique per session (secrets.token_urlsafe) to prevent
    accumulated rows from previous test runs bleeding into this session's assertions.
    """
    # Unique-per-session fake docId (44 URL-safe chars, will never resolve in Drive).
    invalid_doc_id = secrets.token_urlsafe(33)[:44]

    scn_mod = ScenarioSession.new_doc(settings, request=request)
    scn_unmod = ScenarioSession.new_doc(settings)
    scn_trash = ScenarioSession.new_doc(settings)

    # modified-valid: sync once to create sheet row, then add more content
    scn_mod.append_paragraph("AI-1: syncall modified valid action")
    scn_mod.sync()
    scn_mod.append_paragraph("AI-2: additional action added after sync — marks doc modified")

    # unmodified-valid: sync once, no further mutation
    scn_unmod.append_paragraph("AI-1: syncall unmodified valid action")
    scn_unmod.sync()

    # to-be-trashed: sync once to create sheet row, then trash the doc
    scn_trash.append_paragraph("AI-1: syncall trashed doc action")
    scn_trash.sync()
    trashed_id = scn_trash.doc_id
    scn_trash._post_fixture("trash_doc")   # trashes scn_trash.doc_id (= testDocId for this call)

    # invalid-doc: seed two raw rows sharing the same unreachable docId, so
    # Sweep 1's Doc Not Found mark and Sweep 2's archive sweep can be checked
    # for GTaskSheet-4tnr's per-docId batching (both rows converge/evict
    # together, not independently).
    # modified_date is left as now — _handleMarkDocNotFound will overwrite it anyway.
    # The globalIds are set explicitly so backdate_action_row can address these
    # rows after Sweep 1 stamps them with a fresh modified_date.
    invalid_formula = (
        f'=HYPERLINK("https://docs.google.com/document/d/{invalid_doc_id}/edit","Invalid Doc")'
    )
    invalid_global_id = f"{invalid_doc_id}/AI-1"
    invalid_global_id_2 = f"{invalid_doc_id}/AI-2"
    scn_mod._post_fixture("seed_row", {
        "globalId": invalid_global_id,
        "actionId": "INVALID-1",
        "actionText": "syncall invalid doc seeded action",
        "status": "Open",
        "documentFormula": invalid_formula,
    })
    scn_mod._post_fixture("seed_row", {
        "globalId": invalid_global_id_2,
        "actionId": "INVALID-2",
        "actionText": "syncall invalid doc seeded action (sibling row, same docId)",
        "status": "Open",
        "documentFormula": invalid_formula,
    })

    yield {
        "settings": settings,
        "scn_mod": scn_mod,
        "scn_unmod": scn_unmod,
        "modified_id": scn_mod.doc_id,
        "unmodified_id": scn_unmod.doc_id,
        "trashed_id": trashed_id,
        "invalid_id": invalid_doc_id,
        "invalid_global_id": invalid_global_id,
        "invalid_global_id_2": invalid_global_id_2,
    }

    # Teardown: end journey sessions (trashes the docs)
    for scn in (scn_mod, scn_unmod):
        try:
            scn._post_route("end_journey_session", {"docId": scn.doc_id})
        except Exception:
            pass
    # scn_trash doc is already trashed; engine has no enqueued expectations, so skip close()


def test_sync_all(sync_ctx):
    settings = sync_ctx["settings"]
    scn_mod = sync_ctx["scn_mod"]
    scn_unmod = sync_ctx["scn_unmod"]
    modified_id = sync_ctx["modified_id"]
    unmodified_id = sync_ctx["unmodified_id"]
    trashed_id = sync_ctx["trashed_id"]
    invalid_id = sync_ctx["invalid_id"]
    invalid_global_id = sync_ctx["invalid_global_id"]
    invalid_global_id_2 = sync_ctx["invalid_global_id_2"]

    # ── Pre-sweep baseline ───────────────────────────────────────────────────
    # unmodified doc: 1 row in Actions, no sync_status
    pre_unmod = _sheet_rows_for(settings, unmodified_id)
    assert len(pre_unmod) >= 1, "[5u2v pre] expected ≥1 row for unmodified doc before syncAll"

    # invalid doc row exists in Actions before sweep
    pre_invalid = _sheet_rows_for(settings, invalid_id)
    assert len(pre_invalid) >= 1, "[r3d pre] seeded invalid-doc row not found before syncAll"

    # ── Sweep 1 ──────────────────────────────────────────────────────────────
    # sync_all fixture calls syncAll() on the production sheet — all rows are processed.
    # Use scn_mod._post_fixture (testDocId = scn_mod.doc_id) but sync_all ignores testDocId.
    scn_mod._post_fixture("sync_all")

    # [r3d] invalid doc → Sync Status = 'Doc Not Found'
    invalid_s1 = _sheet_rows_for(settings, invalid_id)
    assert len(invalid_s1) >= 1, (
        "[r3d] invalid-doc row disappeared from Actions after Sweep 1 (expected Doc Not Found)"
    )
    for row in invalid_s1:
        assert getattr(row, "sync_status", None) == "Doc Not Found", (
            f"[r3d] invalid-doc row: expected 'Doc Not Found', got {row.sync_status!r}"
        )

    # entry_point: syncAll (30-min time-based sweep, ID-map P1-1) — durable-state
    # assertion at the sweep's own call-site (GTaskSheet-rz4k.1). Re-checks the
    # [r3d] invalid-doc condition above via the tagged scn mechanism.
    def _invalid_doc_not_found() -> str | None:
        rows = _sheet_rows_for(settings, invalid_id)
        if not rows:
            return "[r3d] invalid-doc row disappeared from Actions after Sweep 1"
        for row in rows:
            if getattr(row, "sync_status", None) != "Doc Not Found":
                return (
                    f"[r3d] invalid-doc row: expected 'Doc Not Found', got {row.sync_status!r}"
                )
        return None

    scn_mod.expect_callable(
        _invalid_doc_not_found, on=SHEET, tag="[r3d syncAll sweep1]", entry_point="syncAll",
    )
    scn_mod.checkpoint(STEP)

    # [grxl] trashed doc → Sync Status = 'Doc Not Found'
    # Both paths (inaccessible + trashed) produce the same durable status.
    # The trashed-path is disambiguated by err='Document is in Trash' in GAS logs,
    # not by a distinct sync_status — so we assert the durable outcome only.
    trashed_s1 = _sheet_rows_for(settings, trashed_id)
    assert len(trashed_s1) >= 1, (
        "[grxl] trashed-doc row disappeared from Actions after Sweep 1 (expected Doc Not Found)"
    )
    for row in trashed_s1:
        assert getattr(row, "sync_status", None) == "Doc Not Found", (
            f"[grxl] trashed-doc row: expected 'Doc Not Found', got {row.sync_status!r}"
        )

    # entry_point: mark_doc_not_found (GTaskSheet-rz4k.2) -- syncDocument's catch
    # path POSTs this route when the doc is inaccessible/trashed; tag the [grxl]
    # durable-stamp condition above (distinct from the [r3d]/syncAll tag, since
    # both invalid- and trashed-doc rows are stamped via the same route).
    def _trashed_doc_not_found() -> str | None:
        rows = _sheet_rows_for(settings, trashed_id)
        if not rows:
            return "[grxl] trashed-doc row disappeared from Actions after Sweep 1"
        for row in rows:
            if getattr(row, "sync_status", None) != "Doc Not Found":
                return f"[grxl] trashed-doc row: expected 'Doc Not Found', got {row.sync_status!r}"
        return None

    scn_mod.expect_callable(
        _trashed_doc_not_found, on=SHEET, tag="[grxl mark_doc_not_found]", entry_point="mark_doc_not_found",
    )
    scn_mod.checkpoint(STEP)

    # [zc21] DocData mirrors 'Doc Not Found' and keeps Team Id consistent with
    # the document's actual teamScope appProperty.
    trashed_docdata = _docdata(scn_mod, trashed_id)
    assert trashed_docdata is not None, (
        "[zc21] trashed-doc DocData row missing after Sweep 1"
    )
    assert trashed_docdata.get("syncStatus") == "Doc Not Found", (
        f"[zc21] trashed-doc DocData.sync_status: expected 'Doc Not Found', "
        f"got {trashed_docdata.get('syncStatus')!r}"
    )
    trashed_team_scope = (scn_mod._post_fixture("get_team_scope", {"docId": trashed_id})
                           .get("data") or {}).get("teamScope", "")
    assert trashed_docdata.get("teamId", "") == trashed_team_scope, (
        f"[zc21] trashed-doc DocData.team_id ({trashed_docdata.get('teamId')!r}) "
        f"!= teamScope appProperty ({trashed_team_scope!r})"
    )

    # [zc21] invalid doc never had a DocData row before sync_all — one is
    # created on first 'Doc Not Found' mark, with an empty Team Id.
    invalid_docdata = _docdata(scn_mod, invalid_id)
    assert invalid_docdata is not None, (
        "[zc21] invalid-doc DocData row not created after Sweep 1"
    )
    assert invalid_docdata.get("syncStatus") == "Doc Not Found", (
        f"[zc21] invalid-doc DocData.sync_status: expected 'Doc Not Found', "
        f"got {invalid_docdata.get('syncStatus')!r}"
    )
    assert invalid_docdata.get("teamId", "") == "", (
        f"[zc21] invalid-doc DocData.team_id: expected '', got {invalid_docdata.get('teamId')!r}"
    )

    # [5u2v] unmodified valid doc → row count unchanged; NOT marked Doc Not Found
    post_unmod_s1 = _sheet_rows_for(settings, unmodified_id)
    for row in post_unmod_s1:
        assert getattr(row, "sync_status", None) != "Doc Not Found", (
            f"[5u2v] unmodified-valid doc incorrectly marked Doc Not Found: {row.sync_status!r}"
        )

    # modified valid doc → NOT marked Doc Not Found (may have new rows from AI-2)
    mod_s1 = _sheet_rows_for(settings, modified_id)
    for row in mod_s1:
        assert getattr(row, "sync_status", None) != "Doc Not Found", (
            f"[5u2v] modified-valid doc marked Doc Not Found unexpectedly: {row.sync_status!r}"
        )

    # ── Backdate invalid-doc for Sweep 2 ─────────────────────────────────────
    # Sweep 1 stamped modified_date = now on both invalid-doc rows (same docId).
    # The 24-hour Doc Not Found threshold means they won't archive until that
    # date is > 24h ago. Backdate both rows to 2 days ago so Sweep 2 archives
    # them together — GTaskSheet-4tnr's per-docId batching means a docId's
    # sibling rows are not evicted independently of each other.
    scn_mod._post_fixture("backdate_action_row", {
        "globalId": invalid_global_id,
        "daysAgo": 2,
    })
    scn_mod._post_fixture("backdate_action_row", {
        "globalId": invalid_global_id_2,
        "daysAgo": 2,
    })

    # ── Sweep 2 (nv6g) ───────────────────────────────────────────────────────
    # Second sweep: Doc Not Found rows from Sweep 1 are now in alreadyDocNotFound set
    # → ArchiveManager.archive() moves them from Actions to Archive sheet.
    scn_mod._post_fixture("sync_all")

    # [nv6g] both invalid-doc rows → archived together (backdated 2 days, > 24h threshold)
    invalid_archived = _archive_rows_for(settings, invalid_id)
    assert len(invalid_archived) == 2, (
        f"[nv6g] expected both invalid-doc rows archived together as one docId batch, "
        f"got {len(invalid_archived)}"
    )
    invalid_actions_s2 = _sheet_rows_for(settings, invalid_id)
    assert len(invalid_actions_s2) == 0, (
        f"[nv6g] invalid-doc row still in Actions after archive sweep "
        f"(expected 0, got {len(invalid_actions_s2)})"
    )

    # [GTaskSheet-4tnr] once every Actions row for a Doc Not Found docId has
    # aged out and archived, the DocData row for that docId is evicted too —
    # DocData must not keep referencing a docId whose Actions rows are gone.
    invalid_docdata_s2 = _docdata(scn_mod, invalid_id)
    assert invalid_docdata_s2 is None, (
        f"[GTaskSheet-4tnr] invalid-doc DocData row should be evicted once its "
        f"Doc Not Found Actions rows archive past the 24h threshold, got {invalid_docdata_s2!r}"
    )

    # [GTaskSheet-4tnr] trashed-doc is still within its 24h grace period (not
    # backdated) — its DocData row must survive this sweep.
    trashed_docdata_s2 = _docdata(scn_mod, trashed_id)
    assert trashed_docdata_s2 is not None, (
        "[GTaskSheet-4tnr] trashed-doc DocData row evicted prematurely, "
        "before its 24h grace period elapsed"
    )

    # [nv6g §grace] trashed-doc row → still in Actions (modified_date stamped now by Sweep 1,
    # < 24 hours old; not backdated, so the 24-hour grace period applies).
    trashed_actions_s2 = _sheet_rows_for(settings, trashed_id)
    assert len(trashed_actions_s2) >= 1, (
        "[nv6g §grace] trashed-doc row should still be in Actions under 24-hour grace period"
    )
    for row in trashed_actions_s2:
        assert getattr(row, "sync_status", None) == "Doc Not Found", (
            f"[nv6g §grace] trashed-doc row should remain 'Doc Not Found' in Actions, "
            f"got {row.sync_status!r}"
        )

    # [nv6g §7] Valid doc rows unaffected by either sweep
    mod_s2 = _sheet_rows_for(settings, modified_id)
    for row in mod_s2:
        assert getattr(row, "sync_status", None) != "Doc Not Found", (
            f"[nv6g §7] modified-valid doc incorrectly archived or marked: {row.sync_status!r}"
        )
    unmod_s2 = _sheet_rows_for(settings, unmodified_id)
    for row in unmod_s2:
        assert getattr(row, "sync_status", None) != "Doc Not Found", (
            f"[nv6g §7] unmodified-valid doc incorrectly archived or marked: {row.sync_status!r}"
        )


def test_mark_doc_not_found_no_restamp_on_reconfirm(settings, request):
    """GTaskSheet-4tnr: re-confirming an already-Doc-Not-Found doc must not
    reset its Date Modified.

    syncAll()'s own sweep already keeps a permanently-missing docId out of the
    detection path on later sweeps (its alreadyDocNotFound skip-list,
    SyncManager.js:348-352) -- but syncDocument() is also called directly from
    doc-context entry points with no such guard (Document Sync menu item --
    MenuHandler.js; sidebar Sync button -- WorkspaceAddonCard.js:351). scn.sync() exercises that
    same direct path via the sync_document fixture. Without a guard in
    _handleMarkDocNotFound itself, a user re-clicking Sync on a doc that's still
    missing would keep resetting the 24h Doc-Not-Found aging clock forever.
    """
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn.append_paragraph(ai(action="4tnr restamp guard action").as_text())
        scn.sync()
        scn._post_fixture("trash_doc")

        scn.sync()  # first detection: transitions to Doc Not Found, stamps now
        rows_1 = scn.find_sheet_actions()
        assert rows_1, "expected at least one Actions row for this doc"
        assert rows_1[0].sync_status == "Doc Not Found"
        first_modified = rows_1[0].modified_date
        assert first_modified, "[4tnr] modified_date should be stamped on first detection"

        time.sleep(2)  # measurable timestamp delta if a re-stamp happens
        scn.sync()  # re-confirmation: doc is STILL trashed -- must be a no-op
        rows_2 = scn.find_sheet_actions()
        assert rows_2[0].sync_status == "Doc Not Found"
        assert rows_2[0].modified_date == first_modified, (
            f"[4tnr] Date Modified changed on re-confirmation of an already-Doc-Not-Found "
            f"doc: {first_modified!r} -> {rows_2[0].modified_date!r}"
        )
    finally:
        try:
            scn._post_route("end_journey_session", {"docId": scn.doc_id})
        except Exception:
            pass
        scn.engine.close()


# ---------------------------------------------------------------------------
# op-id correlation — GTaskSheet-65g1
# ---------------------------------------------------------------------------

def test_sync_all_op_correlation_and_webapp_propagation(settings, gas_log_dir, request):
    """GTaskSheet-65g1 + GTaskSheet-j8cn (merged, gts-i9xc): one syncAll()
    invocation's sub-events share one `op` id, that op crosses the
    addon->WebApp HTTP boundary as parentOp on each per-doc sync_action_rows
    call, and a second, separate sweep produces a DIFFERENT op id.

    Sweep 1 mints its own opId (kkm7/uuse convention) up front and scopes
    every assertion to entries chained from THIS sweep via matches_op —
    gts-i9xc: without this, the account's installed 30-min syncAll trigger
    (or another session) landing in the same fence window contributes its
    own unparented sync.all.start (or its own sync_action_rows calls),
    breaking an unscoped "exactly one op" or "exactly N webapp calls" check.
    Sweep 2 uses no explicit opId, to prove op ids are per-invocation, not a
    constant.
    """
    if not gas_log_dir:
        pytest.skip("gas_log_dir not configured — op correlation requires GAS log access")

    import time
    import uuid

    from tests.helpers.gas_log import clear_logs, collect_logs, matches_op, wait_for_log

    scn_a = ScenarioSession.new_doc(settings, request=request)
    scn_b = ScenarioSession.new_doc(settings)
    try:
        scn_a.append_paragraph("AI-1: 65g1/j8cn op-correlation doc A")
        scn_a.sync()
        scn_b.append_paragraph("AI-1: 65g1/j8cn op-correlation doc B")
        scn_b.sync()

        # clear_logs()'s fence has a 10s clock-skew grace window — without this
        # pause, the individual sync() calls' own sync.complete entries (no op,
        # not part of a syncAll sweep) land inside that grace window and falsely
        # appear as "after the fence" once flushed.
        time.sleep(12)

        # ── Sweep 1: explicit opId, all assertions scoped via matches_op ───────
        sweep_op = str(uuid.uuid4())
        fence1 = clear_logs(gas_log_dir)
        scn_a._post_fixture("sync_all", extra={"opId": sweep_op})
        wait_for_log(
            gas_log_dir,
            matches_op(lambda e: e.get("tag") == "sync.all.complete", sweep_op),
            timeout_s=60,
            after=fence1,
        )

        sweep1_entries = collect_logs(
            gas_log_dir,
            matches_op(
                lambda e: e.get("tag") in (
                    "sync.all.start", "sync.all.complete", "sync.scanned", "sync.complete",
                ),
                sweep_op,
            ),
            after=fence1,
        )
        assert sweep1_entries, "[65g1] no sub-events captured for sweep 1's own op"
        # matches_op already scoped these entries to parentOp == sweep_op (the
        # fixture dispatcher's own op, chained through GasLogger.startOp); the
        # sweep's OWN op is a freshly minted id distinct from sweep_op, shared
        # by every one of its sub-events.
        ops1 = {e.get("op") for e in sweep1_entries}
        assert len(ops1) == 1 and None not in ops1, (
            f"[65g1] sweep 1 sub-events do not share a single op id: {ops1!r} "
            f"(entries: {sweep1_entries})"
        )
        op1 = next(iter(ops1))

        # gts-6pws: wait_for_log(sync.all.complete) above only proves the
        # sweep's own top-level op is done -- it races Axiom ingestion lag on
        # the per-doc webapp.request entries this assertion also needs, which
        # can land slightly after sync.all.complete does. Poll collect_logs
        # (short timeout, same shape as wait_for_log's own retry loop) until
        # both expected entries are queryable instead of a single-shot query.
        webapp_deadline = time.monotonic() + 15
        webapp_entries = []
        while time.monotonic() < webapp_deadline:
            webapp_entries = collect_logs(
                gas_log_dir,
                matches_op(
                    lambda e: e.get("tag") == "webapp.request"
                    and (e.get("data") or {}).get("action") == "sync_action_rows",
                    sweep_op,
                ),
                after=fence1,
            )
            if len(webapp_entries) >= 2:
                break
            time.sleep(1.0)
        assert len(webapp_entries) >= 2, (
            f"[j8cn] expected ≥2 sync_action_rows webapp.request entries for THIS sweep "
            f"(one per doc), got {webapp_entries!r}"
        )

        webapp_ops = {e.get("op") for e in webapp_entries}
        assert len(webapp_ops) == len(webapp_entries) and None not in webapp_ops, (
            f"[j8cn] each doPost execution should mint its OWN op id, not share one: {webapp_ops!r}"
        )

        # matches_op already filtered to parentOp == sweep_op above; this
        # assertion is retained as an explicit, readable statement of the
        # invariant it's proving (defense-in-depth, not a redundant check —
        # a regression in matches_op itself would still be caught here).
        webapp_parent_ops = {e.get("parentOp") for e in webapp_entries}
        assert webapp_parent_ops == {sweep_op}, (
            f"[j8cn] all sync_action_rows calls in this sweep should carry parentOp={sweep_op!r}, "
            f"got {webapp_parent_ops!r}"
        )

        # ── Sweep 2 (separate invocation, no explicit opId) ─────────────────────
        fence2 = clear_logs(gas_log_dir)
        scn_a._post_fixture("sync_all")
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.all.complete", timeout_s=60, after=fence2)

        sweep2_entries = collect_logs(
            gas_log_dir,
            lambda e: e.get("tag") in ("sync.all.start", "sync.all.complete"),
            after=fence2,
        )
        assert sweep2_entries, "[65g1] no sub-events captured for sweep 2"
        ops2 = {e.get("op") for e in sweep2_entries}
        assert len(ops2) == 1 and None not in ops2, (
            f"[65g1] sweep 2 sub-events do not share a single op id: {ops2!r}"
        )
        op2 = next(iter(ops2))

        assert op2 != op1, (
            f"[65g1] two separate syncAll() invocations produced the SAME op id "
            f"({op1!r}) — correlation field is not per-invocation"
        )
    finally:
        # scn_a's doc-trashing is deferred to new_doc(request=request)'s
        # pytest finalizer (gts-hroj); scn_b has no `request` and keeps its
        # inline trash (this test has no browser_page, so the diagnostics
        # ordering hook is a no-op here regardless).
        scn_a.engine.close()
        try:
            scn_b._post_route("end_journey_session", {"docId": scn_b.doc_id})
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Integrity pass — GTaskSheet-cduk
# ---------------------------------------------------------------------------

def _docdata(scn, file_id: str | None = None) -> dict | None:
    """Read the DocData row for scn's doc (or an explicit file_id) as a plain dict."""
    extra = {"fileId": file_id} if file_id else {}
    resp = scn._post_fixture("get_docdata_row", extra)
    return (resp.get("data") or {}).get("row")


def _post_fixture_patient(scn, fixture_name: str, extra: dict | None = None, timeout: int = 600) -> dict:
    """Like scn._post_fixture, but with a longer client-side read timeout.

    A few of gts-m33k/gts-sl64's new fixtures re-run the REAL syncAll() over
    the whole production Actions/DocData backlog (not a small per-test doc),
    which has been independently observed (gts-b6dm comments) to take
    anywhere from ~1 to ~12+ minutes depending on how many docs need
    reconciliation/walking in that particular sweep. ScenarioSession's
    default 360s client timeout occasionally trips on this specific
    variance (a client-side socket read timeout, not a GAS-side failure —
    the execution itself completes server-side either way).
    """
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
# GTaskSheet-cduk (integrity pass) + gts-m33k (listing-miss negative + 24h
# aging-window guard) — batched (gts-ir1f, 2026-08-06)
# ---------------------------------------------------------------------------
#
# gts-rskf's AC has two parts: (1) Drive REST calls carry the all-drives
# flags so a Shared-Drive-hosted doc actually appears in the bulk files.list
# listing, and (2) even if a live, reachable doc is EVER absent from that
# listing (Shared Drive omission being the reported cause, but a paginated
# listing miss is not guaranteed to have only one cause), a direct per-doc
# lookup must confirm it is really gone before syncAll marks it Doc Not
# Found. This environment has no test Shared Drive folder id provisioned
# (local.settings.json has no such key — see plan-context.md), so part (1)
# cannot be exercised end-to-end live. Part (2) — the actual mechanism that
# stops a live doc's rows from being silently archived, regardless of why it
# was missing from the listing — is fully testable via the
# sync_all_force_listing_miss fixture, which monkey-patches
# _fetchDriveDocMetadata for exactly one syncAll() call to omit a specific,
# otherwise perfectly reachable doc from the bulk map. This is the Backstop
# case: pre-fix, syncAll marked a listing-absent doc Doc Not Found
# unconditionally (no per-doc lookup existed at all), so this assertion
# fails against that build and passes against the current one.
#
# Batching note (gts-ir1f): cduk (single sweep), m33k-listing-miss (single
# sweep, per-doc-scoped fault) and m33k-revival (inherently 2 sweeps —
# trash-detect then untrash-revive, a genuine sequencing dependency per
# plan-context.md's "when NOT to batch" list, so NOT force-fit into one
# sweep) share a SEED sweep (cduk's integrity-pass correction +
# listing-miss's survival + revival's Sweep-1 trash-detection, all in the
# ONE syncAll() call sync_all_force_listing_miss drives — that fixture only
# removes its target doc from the bulk map, so cduk's and revival's docs
# process normally in the same call) and a FINAL sweep (revival's Sweep 2
# only — untrash then re-sweep; cduk/listing-miss need nothing further).
# 4 sweeps across 3 original tests -> 2 shared sweeps.

def test_sync_all_integrity_and_listing_miss_batch(settings, gas_log_dir, request):
    """Batches GTaskSheet-cduk's integrity-pass AC1-AC4, gts-m33k's
    listing-miss survival, and gts-m33k AC4's 24h-aging-window revival guard
    behind one seed syncAll() sweep + one final syncAll() sweep."""
    sessions = []
    try:
        # --- cduk doc: 2 open actions -> sync -> corrupt DocData ---------------
        cduk = ScenarioSession.new_doc(settings, request=request)
        sessions.append(cduk)
        cduk.append_paragraph("AI-1: cduk integrity pass action one")
        cduk.append_paragraph("AI-2: cduk integrity pass action two")
        cduk.sync()

        cduk_initial = _docdata(cduk)
        assert cduk_initial is not None, "[cduk] DocData row not created by initial sync"
        assert cduk_initial.get("actionCount") == 2, (
            f"[cduk] initial actionCount: expected 2, got {cduk_initial.get('actionCount')!r}"
        )
        cduk_initial_name = cduk_initial.get("docName") or ""

        cduk._post_fixture("set_docdata_row", {
            "actionCount": 99, "resolvedCount": 7, "docName": "Stale Name cduk",
        })
        cduk_stale = _docdata(cduk)
        assert cduk_stale is not None and cduk_stale.get("actionCount") == 99, (
            "[cduk] set_docdata_row did not write stale actionCount=99"
        )

        # AC3: seed an orphan DocData row (fake fileId, no Actions rows).
        # gts-30cq briefly widened ArchiveManager._evictStaleDocData to evict
        # on "no Actions row" alone, and this became an eviction assertion.
        # gts-avvl reverted that: absence of Actions rows is not an eviction
        # signal (ADR-0031 amendment 2026-09-01 -- a DocData row with no live
        # Actions rows is a normal state), because the Team Portal
        # scan-and-track flow mints exactly this shape and the widened
        # predicate destroyed three of the operator's freshly-tracked docs.
        # Back to a SURVIVAL assertion on this sweep; see below.
        cduk_orphan_id = secrets.token_urlsafe(33)[:44]
        cduk._post_fixture("set_docdata_row", {
            "fileId": cduk_orphan_id, "actionCount": 55, "resolvedCount": 3, "docName": "Orphan",
        })

        # --- listing-miss doc: just a normal synced doc -------------------------
        lm = ScenarioSession.new_doc(settings, request=request)
        sessions.append(lm)
        lm.append_paragraph("AI-1: m33k listing-miss survival action")
        lm.sync()
        lm_pre_rows = lm.find_sheet_actions()
        assert lm_pre_rows, "[m33k] expected ≥1 Actions row before the forced-miss sweep"
        lm_pre_statuses = {r.global_id: r.sync_status for r in lm_pre_rows}

        # --- revival doc: sync then trash (Sweep 1 target: trash-detection) ----
        rev = ScenarioSession.new_doc(settings, request=request)
        sessions.append(rev)
        rev.append_paragraph("AI-1: m33k aging-window revival action")
        rev.sync()
        rev._post_fixture("trash_doc")

        # --- Shared SEED sweep ---------------------------------------------------
        # ONE syncAll() call, driven via sync_all_force_listing_miss targeting
        # `lm` only — cduk's and rev's docs process normally in the same sweep
        # (src/TestFixtures.js ~line 2707: the fault only deletes the target
        # doc's own entry from the bulk map).
        if gas_log_dir:
            from tests.helpers.gas_log import clear_logs
            fence = clear_logs(gas_log_dir)
        else:
            fence = 0.0

        _post_fixture_patient(lm, "sync_all_force_listing_miss", extra={"docId": lm.doc_id})

        # --- cduk AC1/AC2/AC3/AC4: DocData corrected by the integrity pass -----
        cduk_after = _docdata(cduk)
        assert cduk_after is not None, "[cduk AC1] DocData row missing after syncAll"
        assert cduk_after.get("actionCount") == 2, (
            f"[cduk AC1] actionCount: expected 2, got {cduk_after.get('actionCount')!r}"
        )
        assert cduk_after.get("resolvedCount") == 0, (
            f"[cduk AC1] resolvedCount: expected 0, got {cduk_after.get('resolvedCount')!r}"
        )
        assert cduk_after.get("docName") != "Stale Name cduk", (
            "[cduk AC2] docName still shows stale value after integrity pass"
        )
        if cduk_initial_name:
            assert cduk_after.get("docName") == cduk_initial_name, (
                f"[cduk AC2] docName: expected {cduk_initial_name!r}, got {cduk_after.get('docName')!r}"
            )
        # AC3 (gts-avvl): the orphan row has no Actions row referencing it and a
        # blank syncStatus, so ArchiveManager.archive() must NOT evict it on
        # this sweep. Its fake fileId is unreachable in Drive, so syncAll's own
        # walk marks it 'Doc Not Found' during this same sweep -- but archive()
        # runs BEFORE that marking, which is the grace period. It becomes
        # evictable on the NEXT sweep, asserted separately in
        # tests/test_docdata_orphan_eviction.py.
        cduk_orphan_after = _docdata(cduk, file_id=cduk_orphan_id)
        assert cduk_orphan_after is not None, (
            f"[cduk AC3] orphan DocData row (blank syncStatus, no Actions rows) was "
            f"EVICTED on the sweep that first observed it. Absence of Actions rows is "
            f"not an eviction signal (gts-avvl / ADR-0031 amendment 2026-09-01)."
        )
        if gas_log_dir:
            from tests.helpers.gas_log import wait_for_log
            wait_for_log(
                gas_log_dir,
                lambda e: e.get("tag") == "sync.integrity.complete",
                timeout_s=60,
                after=fence,
            )

        # --- listing-miss: survives the sweep it was forced absent from --------
        lm_post_rows = lm.find_sheet_actions()
        assert len(lm_post_rows) == len(lm_pre_rows), (
            f"[m33k] Actions row count changed after a forced listing-miss sweep: "
            f"before={len(lm_pre_rows)} after={len(lm_post_rows)}"
        )
        for row in lm_post_rows:
            assert row.sync_status != "Doc Not Found", (
                f"[m33k] row {row.global_id!r} marked 'Doc Not Found' after a forced "
                f"listing-miss sweep — per-doc lookup fallback did not save it"
            )
            prior = lm_pre_statuses.get(row.global_id)
            assert row.sync_status == (prior or ""), (
                f"[m33k] row {row.global_id!r} sync_status changed: "
                f"{prior!r} -> {row.sync_status!r}"
            )
        lm_archived = _archive_rows_for(settings, lm.doc_id)
        assert not lm_archived, (
            f"[m33k] doc's rows appeared in Archive after a single forced "
            f"listing-miss sweep: {lm_archived!r}"
        )

        # --- revival: Sweep 1 marked it Doc Not Found ---------------------------
        rev_marked_rows = rev.find_sheet_actions()
        assert rev_marked_rows, "[m33k] Actions row disappeared after trash+sync_all"
        for row in rev_marked_rows:
            assert row.sync_status == "Doc Not Found", (
                f"[m33k] expected 'Doc Not Found' after Sweep 1, got {row.sync_status!r}"
            )

        # --- Shared FINAL sweep ---------------------------------------------------
        # Untrash the revival doc, then ONE more syncAll() — needed only for
        # revival's own sequencing (Sweep 2 must follow Sweep 1); cduk and
        # listing-miss need nothing further from this sweep.
        rev._post_fixture("untrash_doc")
        _post_fixture_patient(rev, "sync_all")

        rev_revived_rows = rev.find_sheet_actions()
        assert rev_revived_rows, (
            "[m33k] Actions row(s) missing after revival sweep — doc was archived "
            "despite becoming reachable before the 24h aging threshold"
        )
        for row in rev_revived_rows:
            assert row.sync_status != "Doc Not Found", (
                f"[m33k] row {row.global_id!r} still 'Doc Not Found' after revival sweep"
            )
        rev_archived = _archive_rows_for(settings, rev.doc_id)
        assert not rev_archived, (
            f"[m33k] doc's rows were archived despite becoming reachable before "
            f"the 24h aging threshold: {rev_archived!r}"
        )

        # --- Durability + entry-point tagging (T1/T17/T24), one per scenario ---
        def _cduk_durable() -> str | None:
            row = _docdata(cduk)
            if row is None:
                return "[cduk] DocData row missing"
            if row.get("actionCount") != 2 or row.get("resolvedCount") != 0:
                return f"[cduk] counts drifted: {row!r}"
            return None

        def _lm_durable_survival() -> str | None:
            rows = lm.find_sheet_actions()
            if not rows:
                return "[m33k] Actions rows disappeared after forced listing-miss sweep"
            for row in rows:
                if row.sync_status == "Doc Not Found":
                    return f"[m33k] row {row.global_id!r} marked Doc Not Found"
            return None

        def _rev_durable_revival() -> str | None:
            rows = rev.find_sheet_actions()
            if not rows:
                return "[m33k] revived doc's rows missing from Actions"
            for row in rows:
                if row.sync_status == "Doc Not Found":
                    return f"[m33k] row {row.global_id!r} still marked Doc Not Found post-revival"
            return None

        cduk.expect_callable(
            _cduk_durable, on=SHEET, tag="[cduk integrity pass corrects stale DocData]", entry_point="syncAll",
        )
        cduk.checkpoint(STEP)
        lm.expect_callable(
            _lm_durable_survival, on=SHEET, tag="[m33k listing-miss survives]", entry_point="syncAll",
        )
        lm.checkpoint(STEP)
        rev.expect_callable(
            _rev_durable_revival, on=SHEET, tag="[m33k aging-window revival]", entry_point="syncAll",
        )
        rev.checkpoint(STEP)
    finally:
        # Doc-trashing deferred to each session's new_doc(request=request)
        # pytest finalizer (gts-hroj).
        for scn in sessions:
            scn.engine.close()


# ---------------------------------------------------------------------------
# gts-pm72: bounded retry on transient Drive files.list 5xx
# ---------------------------------------------------------------------------
#
# Regression run 2026-08-05: test_import_flow_forward_sync failed 4 consecutive
# attempts, the last on 'sync.driveMetadata.error: files.list failed: HTTP 500'
# -- a one-off Drive Advanced-Service 500 mid-execution, not a code defect, with
# no retry to absorb it. SyncManager.js's _fetchDriveWithRetry (gts-pm72) now
# wraps _fetchDriveDocMetadata's files.list call in a bounded retry (3 attempts,
# short backoff, mirroring scn/session.py::_http_post's convention). The
# 'sync_all_force_drive_5xx' fixture drives the real syncAll() entry point with
# PropertiesService fault-injection (_TEST_FORCE_DRIVE_5XX_COUNT, consulted by
# _driveFetchTestOverrideCode) standing in for a real transient 500, so this is
# provable without waiting for a real Google-side outage to line up with a test
# run. This is the Backstop case: pre-fix, ANY forced-5xx count -- even 1 --
# throws immediately and logs sync.driveMetadata.error, so this assertion fails
# against that build and passes against the current one.

def test_sync_all_retries_transient_drive_5xx(settings, gas_log_dir, request):
    """[gts-pm72] One doc, two sequential forced-5xx sweeps.

    Sweep 1: a single transient Drive files.list 500 (within the 3-attempt
    retry budget) is absorbed by the bounded retry: no
    sync.driveMetadata.error is logged, and syncAll completes with no
    observable disruption.

    Sweep 2: a persistent Drive files.list 500 (beyond the 3-attempt retry
    budget) still throws sync.driveMetadata.error once the bound is
    exhausted -- proving the retry is bounded, not silently infinite or
    skipped -- but the pre-existing per-doc fallback (gts-rskf) still keeps
    the sweep correct: no row is misclassified 'Doc Not Found' just because
    the bulk listing call failed outright.

    The fault counter (_TEST_FORCE_DRIVE_5XX_COUNT, ScriptProperties) is
    global, not doc-scoped, and each fixture call consumes its own count
    before the next runs -- sequencing both sweeps on one doc changes
    nothing about what's being proven.
    """
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn.append_paragraph("AI-1: pm72 transient/exhausted-500 action")
        scn.sync()

        pre_rows = scn.find_sheet_actions()
        assert pre_rows, "[pm72] expected ≥1 Actions row before the forced-5xx sweeps"
        pre_statuses = {r.global_id: r.sync_status for r in pre_rows}

        # ── Sweep 1: single transient 500, absorbed by the bounded retry ───────
        if gas_log_dir:
            from tests.helpers.gas_log import clear_logs, assert_no_log
            fence = clear_logs(gas_log_dir)
        else:
            fence = 0.0

        _post_fixture_patient(scn, "sync_all_force_drive_5xx", {"fails": 1})

        if gas_log_dir:
            assert_no_log(
                gas_log_dir, fence,
                lambda e: e.get("tag") == "sync.driveMetadata.error",
                "[pm72] sync.driveMetadata.error logged for a single forced 500 "
                "-- the bounded retry did not absorb it",
            )

        post_rows = scn.find_sheet_actions()
        assert len(post_rows) == len(pre_rows), (
            f"[pm72] Actions row count changed after a forced-500-recovery sweep: "
            f"before={len(pre_rows)} after={len(post_rows)}"
        )
        for row in post_rows:
            assert row.sync_status != "Doc Not Found", (
                f"[pm72] row {row.global_id!r} marked 'Doc Not Found' after a "
                f"single transient 500 the retry should have absorbed"
            )
            prior = pre_statuses.get(row.global_id)
            assert row.sync_status == (prior or ""), (
                f"[pm72] row {row.global_id!r} sync_status changed: "
                f"{prior!r} -> {row.sync_status!r}"
            )

        # ── Sweep 2: persistent 500, retry bound exhausted, fallback recovers ──
        if gas_log_dir:
            from tests.helpers.gas_log import clear_logs, wait_for_log
            fence2 = clear_logs(gas_log_dir)

        _post_fixture_patient(scn, "sync_all_force_drive_5xx", {"fails": 5})

        if gas_log_dir:
            wait_for_log(
                gas_log_dir,
                lambda e: e.get("tag") == "sync.driveMetadata.error",
                timeout_s=30,
                after=fence2,
            )

        post_rows2 = scn.find_sheet_actions()
        assert len(post_rows2) == len(pre_rows), (
            f"[pm72] Actions row count changed after an exhausted-retry sweep: "
            f"before={len(pre_rows)} after={len(post_rows2)}"
        )
        for row in post_rows2:
            assert row.sync_status != "Doc Not Found", (
                f"[pm72] row {row.global_id!r} marked 'Doc Not Found' after an "
                f"exhausted-retry bulk-listing failure -- per-doc fallback did not save it"
            )
    finally:
        # Doc-trashing deferred to new_doc(request=request)'s pytest
        # finalizer (gts-hroj).
        scn.engine.close()


# ---------------------------------------------------------------------------
# gts-232z: bounded retry on _syncActionRows' own self-call non-200
# ---------------------------------------------------------------------------
#
# gts-u947's regression-verify sweep (2026-09-01) hit
# 'sync_action_rows failed: HTTP 302' from _syncActionRows' UrlFetchApp.fetch
# self-call back into this same deployed WebApp -- the documented /exec ->
# script.googleusercontent.com routing glitch every OTHER caller already
# retries (scn/session.py::_http_post client-side, TestFixtures.js's opId-
# dedupe comment, _fetchDriveWithRetry for Drive REST) but this one call site
# did not. SyncManager.js's _syncActionRows now wraps its self-call fetch in
# a bounded retry (3 attempts, 1s backoff, mirroring _fetchDriveWithRetry's
# shape) via _webAppFetchTestOverrideCode. The
# 'sync_all_force_webapp_non200' fixture drives the real syncAll() entry
# point with PropertiesService fault-injection
# (_TEST_FORCE_WEBAPP_NON200_COUNT) standing in for the real routing glitch,
# so this is provable without waiting for a real 302 to line up with a test
# run. Backstop: pre-fix, ANY forced-non-200 count -- even 1 -- logs
# sync.error immediately on the first attempt with no retry, so both
# assertions below fail against that build and pass against the current one.

def test_sync_all_retries_transient_webapp_non200(settings, gas_log_dir, request):
    """[gts-232z] A single transient non-200 (within the 3-attempt retry
    budget) from _syncActionRows' self-call is absorbed by the bounded
    retry: sync.actionRows.retry is logged for the forced attempt, no
    sync.error is logged, and the row's sync_status is unaffected."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn.append_paragraph("AI-1: gts-232z transient-non200 recovery action")
        scn.sync()

        pre_rows = scn.find_sheet_actions()
        assert pre_rows, "[gts-232z] expected >=1 Actions row before the forced-non200 sweep"
        pre_statuses = {r.global_id: r.sync_status for r in pre_rows}

        if gas_log_dir:
            from tests.helpers.gas_log import clear_logs, assert_no_log, wait_for_log
            fence = clear_logs(gas_log_dir)
        else:
            fence = 0.0

        _post_fixture_patient(scn, "sync_all_force_webapp_non200", {"fails": 1})

        if gas_log_dir:
            wait_for_log(
                gas_log_dir,
                lambda e: e.get("tag") == "sync.actionRows.retry",
                timeout_s=30,
                after=fence,
            )
            assert_no_log(
                gas_log_dir, fence,
                lambda e: e.get("tag") == "sync.error"
                and "sync_action_rows failed" in (e.get("data", {}).get("msg") or ""),
                "[gts-232z] sync.error logged for a single forced non-200 "
                "-- the bounded retry did not absorb it",
            )

        post_rows = scn.find_sheet_actions()
        assert len(post_rows) == len(pre_rows), (
            f"[gts-232z] Actions row count changed after a forced-non200-recovery sweep: "
            f"before={len(pre_rows)} after={len(post_rows)}"
        )
        for row in post_rows:
            prior = pre_statuses.get(row.global_id)
            assert row.sync_status == (prior or ""), (
                f"[gts-232z] row {row.global_id!r} sync_status changed: "
                f"{prior!r} -> {row.sync_status!r}"
            )
    finally:
        # Doc-trashing deferred to new_doc(request=request)'s pytest
        # finalizer (gts-hroj).
        scn.engine.close()


def test_sync_all_exhausted_webapp_non200_retry_still_logs_error(settings, gas_log_dir, request):
    """[gts-232z] A persistent non-200 (beyond the 3-attempt retry budget)
    from _syncActionRows' self-call still logs sync.error once the bound is
    exhausted -- proving the retry is bounded, not silently infinite or
    skipped."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn.append_paragraph("AI-1: gts-232z exhausted-retry action")
        scn.sync()

        pre_rows = scn.find_sheet_actions()
        assert pre_rows, "[gts-232z] expected >=1 Actions row before the forced-non200 sweep"

        if gas_log_dir:
            from tests.helpers.gas_log import clear_logs, wait_for_log
            fence = clear_logs(gas_log_dir)

        _post_fixture_patient(scn, "sync_all_force_webapp_non200", {"fails": 5})

        if gas_log_dir:
            wait_for_log(
                gas_log_dir,
                lambda e: e.get("tag") == "sync.error"
                and "sync_action_rows failed" in (e.get("data", {}).get("msg") or ""),
                timeout_s=30,
                after=fence,
            )

        post_rows = scn.find_sheet_actions()
        assert len(post_rows) == len(pre_rows), (
            f"[gts-232z] Actions row count changed after an exhausted-retry sweep: "
            f"before={len(pre_rows)} after={len(post_rows)}"
        )
    finally:
        # Doc-trashing deferred to new_doc(request=request)'s pytest
        # finalizer (gts-hroj).
        scn.engine.close()


# ---------------------------------------------------------------------------
# gts-aiaz: missing docState/allDocGlobalIds must never mass-delete rows
# ---------------------------------------------------------------------------
#
# _handleSyncActionRows (WebApp.js) is WEBAPP_SECRET-gated, not testToken-
# gated -- a hand-made maintenance call sending only {action, docId, secret}
# is exactly the incident scenario in gts-aiaz's bug report (observed:
# one such call stamped all 7 rows of a live doc 'Deleted' while the document
# still contained all 7 actions). This posts that payload directly (no
# docState, no allDocGlobalIds, no scanned) and asserts no row's sync_status
# changes. Backstop: pre-fix, the orphan-detection loop was gated on `docId`
# alone -- docState=[] read as "the document is empty", and every existing
# row for that doc was marked Deleted unconditionally. That destructive
# branch (WebApp.js's `if (docId) { ... mark every row missing from docState
# Deleted ... }`, before the `scanned` gate existed) is exactly what this
# assertion would have failed against.

def test_sync_action_rows_missing_docstate_is_noop(settings, gas_log_dir, request):
    """[gts-aiaz] A docId-only sync_action_rows payload (no docState,
    allDocGlobalIds, or scanned flag) must not alter any row's sync_status —
    omission is a no-op for orphan detection, never a mandate to delete."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn.append_paragraph("AI-1: aiaz missing-docstate noop action")
        scn.sync()

        pre_rows = scn.find_sheet_actions()
        assert pre_rows, "[aiaz] expected >=1 Actions row before the bare maintenance call"
        pre_statuses = {r.global_id: r.sync_status for r in pre_rows}

        secret = settings.get("webappSecret") or ""
        assert secret, (
            "[aiaz] local.settings.json missing webappSecret — cannot exercise the "
            "WEBAPP_SECRET-gated sync_action_rows route directly"
        )

        fence = 0.0
        if gas_log_dir:
            from tests.helpers.gas_log import clear_logs
            fence = clear_logs(gas_log_dir)

        resp = scn._post({"action": "sync_action_rows", "secret": secret, "docId": scn.doc_id})
        assert "error" not in resp, f"[aiaz] bare maintenance call unexpectedly errored: {resp!r}"

        post_rows = scn.find_sheet_actions()
        assert len(post_rows) == len(pre_rows), (
            f"[aiaz] Actions row count changed after a docId-only sync_action_rows call: "
            f"before={len(pre_rows)} after={len(post_rows)}"
        )
        for row in post_rows:
            assert row.sync_status != "Deleted", (
                f"[aiaz] row {row.global_id!r} marked 'Deleted' by a sync_action_rows payload "
                f"that omitted docState/allDocGlobalIds/scanned — the destructive branch fired "
                f"with no explicit scan assertion"
            )
            prior = pre_statuses.get(row.global_id)
            assert row.sync_status == (prior or ""), (
                f"[aiaz] row {row.global_id!r} sync_status changed: {prior!r} -> {row.sync_status!r}"
            )

        if gas_log_dir:
            from tests.helpers.gas_log import wait_for_log
            wait_for_log(
                gas_log_dir,
                lambda e: e.get("tag") == "sync.orphanDetection.skipped"
                and (e.get("data") or {}).get("docId") == scn.doc_id,
                timeout_s=60,
                after=fence,
            )

        def _durable_noop() -> str | None:
            rows = scn.find_sheet_actions()
            if len(rows) != len(pre_rows):
                return f"[aiaz] row count drifted: expected {len(pre_rows)}, got {len(rows)}"
            for row in rows:
                if row.sync_status == "Deleted":
                    return f"[aiaz] row {row.global_id!r} marked Deleted"
            return None

        scn.expect_callable(
            _durable_noop, on=SHEET, tag="[aiaz missing-docState noop]", entry_point="sync_action_rows",
        )
        scn.checkpoint(STEP)
    finally:
        # Doc-trashing deferred to new_doc(request=request)'s pytest
        # finalizer (gts-hroj).
        scn.engine.close()


# ---------------------------------------------------------------------------
# gts-binf / gts-6hzy: duplicate-globalId Actions rows collapse on syncAll
# ---------------------------------------------------------------------------
#
# _loadExistingRowsByGlobalId (WebApp.js) resolves existingMap[globalId] to
# the LAST-scanned physical sheet row when N>1 rows share a globalId (silent
# last-write-wins) -- pre-fix, earlier duplicate rows for that globalId were
# invisible to the entire sync_action_rows upsert/orphan pass: never updated,
# never flagged, never removed. They just sat in the sheet forever, showing
# the same action twice (the user-reported symptom). This seeds a genuine
# second physical row sharing an already-synced action's globalId and drives
# the regular syncDocument()/sync_action_rows sweep -- the entry point named
# in gts-binf's own pre-code contract -- rather than a synthetic direct call.
# No-shared-context note (plan-context.md): authored against gts-binf's
# frozen Description/AC text, not its implementation diff.
#
# Backstop: pre-fix, _handleSyncActionRows had no code path that ever
# inspected more than the last-scanned row per globalId, so
# `len(collapsed_rows)` would still be 2 (not 1) and no `sync.dedup` event
# would ever fire -- both assertions below fail against that build.

def test_sync_all_collapses_duplicate_globalid_rows(settings, gas_log_dir, request):
    """[gts-binf/gts-6hzy case 1+3+2] N>1 sheet rows sharing a globalId
    collapse to one canonical row on the regular sync sweep; a sync.dedup
    log event fires on collapse; a second sync afterward is idempotent (no
    further dedup event, no row-count change); and, on the same
    now-canonical row, the pre-existing re-anchor duplicate-IDENTITY path
    (WebApp.js's docStateIdentitySet check, distinct from gts-binf's
    SAME-globalId collapse) still fires correctly."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn.append_paragraph("AI-1: binf dedup canonical action")
        scn.sync()

        canonical_rows = scn.find_sheet_actions()
        assert len(canonical_rows) == 1, (
            f"[binf] expected exactly 1 row after initial sync, got {len(canonical_rows)}"
        )
        global_id = canonical_rows[0].global_id
        assert global_id, "[binf] canonical row has no global_id"

        doc_formula = (
            f'=HYPERLINK("https://docs.google.com/document/d/{scn.doc_id}/edit","Dup Guard")'
        )
        scn._post_fixture("seed_row", {
            "globalId": global_id,
            "actionId": "AI-1",
            "actionText": "STALE pre-existing duplicate row (should be collapsed)",
            "status": "Open",
            "documentFormula": doc_formula,
        })

        duped_rows = [r for r in scn.find_sheet_actions() if r.global_id == global_id]
        assert len(duped_rows) == 2, (
            f"[binf] seed_row did not produce a duplicate-globalId row: expected 2 rows "
            f"for {global_id!r}, got {len(duped_rows)}"
        )

        fence = 0.0
        if gas_log_dir:
            from tests.helpers.gas_log import clear_logs
            fence = clear_logs(gas_log_dir)

        scn.sync()  # regular sweep entry point (syncDocument -> sync_action_rows)

        collapsed_rows = [r for r in scn.find_sheet_actions() if r.global_id == global_id]
        assert len(collapsed_rows) == 1, (
            f"[binf] duplicate-globalId rows not collapsed by the regular sync sweep: "
            f"expected 1 row for {global_id!r} after sync, got {len(collapsed_rows)}"
        )
        assert collapsed_rows[0].action == "binf dedup canonical action", (
            f"[binf] surviving row's content is not the live doc content: "
            f"{collapsed_rows[0].action!r}"
        )

        if gas_log_dir:
            from tests.helpers.gas_log import wait_for_log
            wait_for_log(
                gas_log_dir,
                lambda e: e.get("tag") == "sync.dedup"
                and (e.get("data") or {}).get("globalId") == global_id,
                timeout_s=60,
                after=fence,
            )

        def _durable_dedup() -> str | None:
            rows = [r for r in scn.find_sheet_actions() if r.global_id == global_id]
            if len(rows) != 1:
                return f"[binf] {len(rows)} rows for {global_id!r}, expected 1"
            return None

        scn.expect_callable(
            _durable_dedup, on=SHEET, tag="[binf duplicate-globalId collapse]", entry_point="syncAll",
        )
        scn.checkpoint(STEP)

        # [gts-6hzy case 3] Idempotency: a second sync after the collapse is a
        # no-op -- no further dedup event, no row-count change.
        fence2 = 0.0
        if gas_log_dir:
            from tests.helpers.gas_log import clear_logs
            fence2 = clear_logs(gas_log_dir)

        scn.sync()

        idempotent_rows = [r for r in scn.find_sheet_actions() if r.global_id == global_id]
        assert len(idempotent_rows) == 1, (
            f"[6hzy idempotency] row count for {global_id!r} changed on a second sync "
            f"after collapse: {len(idempotent_rows)}"
        )

        if gas_log_dir:
            from tests.helpers.gas_log import assert_no_log
            assert_no_log(
                gas_log_dir, fence2,
                lambda e: e.get("tag") == "sync.dedup" and (e.get("data") or {}).get("globalId") == global_id,
                what="[6hzy idempotency] unexpected repeat sync.dedup after collapse already settled",
            )

        # [gts-binf/gts-6hzy case 2] Regression guard, on the SAME now-canonical
        # live row: the pre-existing re-anchor duplicate-IDENTITY path
        # (WebApp.js's docStateIdentitySet check, distinct from gts-binf's
        # SAME-globalId collapse above) must still fire correctly. Seeds a
        # stale row under a DIFFERENT globalId but the SAME identity (assignee
        # + action text + status) as the still-live canonical action --
        # simulating the row a re-anchor (AI-N renumber / named-range reset)
        # leaves behind. This is a no-change assertion by construction (the
        # identity-duplicate code path is untouched by gts-binf's
        # same-globalId dedup pass, which only ever inspects rows sharing an
        # exact globalId) -- it is not expected to fail pre-fix; its purpose
        # is to prove the same-globalId collapse pass above does not
        # interfere with, duplicate, or suppress this older mechanism.
        live_row = collapsed_rows[0]
        live_global_id = live_row.global_id

        # A stale row under a DIFFERENT (fabricated) globalId for the same doc,
        # sharing the live row's identity (assignee/action/status) -- exactly
        # what a re-anchor leaves behind per WebApp.js's own comment ("If the
        # current doc still has the same action state under a different
        # globalId, this row is a stale duplicate left behind by a re-anchor").
        stale_global_id = f"{scn.doc_id}/AI-999"
        doc_formula = (
            f'=HYPERLINK("https://docs.google.com/document/d/{scn.doc_id}/edit","Reanchor Guard")'
        )
        scn._post_fixture("seed_row", {
            "globalId": stale_global_id,
            "actionId": "AI-999",
            "actionText": live_row.action,
            "assigneeEmail": live_row.assignee or "",
            "status": live_row.status or "Open",
            "documentFormula": doc_formula,
        })

        pre_sync_rows = scn.find_sheet_actions()
        assert any(r.global_id == stale_global_id for r in pre_sync_rows), (
            "[binf reanchor-guard] seed_row did not create the stale identity-duplicate row"
        )
        assert len(pre_sync_rows) == 2, (
            f"[binf reanchor-guard] expected 2 rows (live + stale identity-duplicate) "
            f"before sync, got {len(pre_sync_rows)}"
        )

        scn.sync()  # regular sweep entry point

        post_sync_rows = scn.find_sheet_actions()
        stale_still_present = [r for r in post_sync_rows if r.global_id == stale_global_id]
        live_still_present = [r for r in post_sync_rows if r.global_id == live_global_id]

        assert not stale_still_present, (
            f"[binf reanchor-guard] stale identity-duplicate row {stale_global_id!r} "
            f"survived a sync sweep — the pre-existing re-anchor duplicate-identity path "
            f"(WebApp.js docStateIdentitySet check) regressed"
        )
        assert len(live_still_present) == 1, (
            f"[binf reanchor-guard] the live action's own row {live_global_id!r} was "
            f"affected by the identity-duplicate cleanup: {live_still_present!r}"
        )

        def _durable_reanchor_guard() -> str | None:
            rows = scn.find_sheet_actions()
            if any(r.global_id == stale_global_id for r in rows):
                return f"[binf reanchor-guard] stale row {stale_global_id!r} reappeared"
            if not any(r.global_id == live_global_id for r in rows):
                return f"[binf reanchor-guard] live row {live_global_id!r} missing"
            return None

        scn.expect_callable(
            _durable_reanchor_guard, on=SHEET,
            tag="[binf reanchor duplicate-identity regression guard]", entry_point="syncAll",
        )
        scn.checkpoint(STEP)
    finally:
        # Doc-trashing deferred to new_doc(request=request)'s pytest
        # finalizer (gts-hroj).
        scn.engine.close()
