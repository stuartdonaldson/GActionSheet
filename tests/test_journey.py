"""
test_journey.py — §16.10 canonical scenario journey: Acts 1-5 + final reconcile.

Exercises Sync Scenarios C, B/A, and the editor UI against a live GAS deployment.
Each act maps to one entry point; every expectation declares intent on an ai.

Bead: GTaskSheet-5vwu.13
Canonical source: docs/atdd/atdd-lifecycle.md §16.10

Deviations from §16.10 (mechanical, not design):
  D1 — Coordination Log (bead .1): Act 4 "Open" SHEET probe and Act 5 "In Progress"
       SHEET probe cannot share the same final INTEGRITY.  An intermediate INTEGRITY
       after Act 4 drains the Open expectation before set_status changes it.
  D3 — created.action_id is ambiguous until post-sync (§16.10 note: "next id is
       ambiguous after AI-1,2,5,9"). Resolved from scn.doc_items() after Act 4
       INTEGRITY before the Act 5 hover.
  D4 — Acts 3, 3b, 4, and 5 require add-on triggers (homepage card,
       createActionTriggers) installed as a test deployment in the test
       Google account (one-time setup, see docs/OPERATIONS.md). Act 0
       (below) is a pre-flight that opens the sidebar and reads its
       BUILD_INFO.version footer (live, via the UI -- not a settings flag):
       if the sidebar doesn't load, or shows a version other than the one
       just stamped by npm run deploy:test, the journey fails immediately
       with a message naming the install/redeploy step -- instead of Acts
       3/3b/4/5 silently warning and continuing against a missing or stale
       add-on.
"""
import pathlib
import time

import pytest

from scn.ai import ai
from scn.engine import CheckpointKind, Severity, Surface
from scn.reporter import emit_standalone_event
from scn.session import ScenarioSession
from scn.ui import UiDriver
from tests.helpers.gas_log import assert_log, clear_logs

DOC = Surface.DOC
SHEET = Surface.SHEET
TRACKER = Surface.TRACKER
INTEGRITY = CheckpointKind.INTEGRITY
STEP = CheckpointKind.STEP
WARN = Severity.WARN


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def browser_page(settings):
    """Launch Chromium with saved auth state; yield the page for Acts 4-5.

    Module-scoped, so this launch/teardown happens outside any single test's
    ScenarioSession/Reporter lifetime — timed and emitted directly via
    emit_standalone_event (GTaskSheet-j8cn gap-instrumentation) rather than
    being an invisible gap between tests.
    """
    from playwright.sync_api import sync_playwright

    auth = pathlib.Path(__file__).parent.parent / ".auth" / "user.json"
    run_id = pathlib.Path(__file__).stem  # module-scoped: no per-test request.node here
    t0 = time.monotonic()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            storage_state=str(auth),
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        emit_standalone_event(settings, run_id=run_id, name="browser_launch", dur_s=time.monotonic() - t0)
        yield page
        t1 = time.monotonic()
        ctx.close()
        browser.close()
        emit_standalone_event(settings, run_id=run_id, name="browser_teardown", dur_s=time.monotonic() - t1)


@pytest.fixture
def scn(settings, browser_page, request):
    """Create the isolated journey doc; attach UiDriver; teardown trashes the doc.

    Function-scoped (not module) so request.node is the test item — required for
    record_property/JUnit <property> emission (T24). Single test_journey in this
    module, so this is behaviorally equivalent to the prior module scope.
    """
    s = ScenarioSession.new_doc(settings, request=request)
    s.ui = UiDriver(browser_page, doc_id=s.doc_id)
    yield s
    s.close()                              # trash; assert expectation queue empty


# ---------------------------------------------------------------------------
# Journey
# ---------------------------------------------------------------------------

def test_journey(scn, expected_version, gas_log_dir):
    # ── Act 0 — pre-flight: confirm the add-on test deployment is installed
    # and serving the build just deployed ────────────────────────────────────
    try:
        sidebar = scn.ui.open_sidebar()
    except TimeoutError as e:
        pytest.fail(
            "Add-on test deployment not installed (or not loading) in this "
            f"Google account: sidebar did not load ({e}). One-time setup: "
            "Apps Script editor -> Deploy -> Test deployments -> Install as "
            "Add-on. See docs/OPERATIONS.md, Running Tests section."
        )

    version_text = scn.ui.read_version(sidebar)
    assert version_text == expected_version, (
        f"Add-on sidebar reports version {version_text!r}, expected "
        f"{expected_version!r} (src/Version.js BUILD_INFO.version, just "
        "stamped by npm run deploy:test). The installed add-on test "
        "deployment is stale -- reinstall it: Apps Script editor -> Deploy "
        "-> Test deployments -> Install as Add-on."
    )

    # ── Act 1 — author types five AI lines into a blank doc ───────────────────
    #   status left UNSET on plain items (non-default status requires explicit token)
    unassigned = ai(action="This tag and text confirms creation of an unassigned action item")
    with_email = ai(
        action="This tag and email address along with this text confirms email-assignee creation",
        assignee="aitest@example.com",
    )
    explicit_5 = ai(
        action="This tag and text confirms pre-assigning a specific action ID",
        action_id="AI-5",
    )
    domain_usr = ai(
        action="This tag email and text confirms domain-user name resolution",
        assignee="minister@northlakeuu.org",
        action_id="AI-9",
    )
    started_ip = ai(action="An action the author starts in progress", status="In Progress")
    backlogged = ai(action="An action with a non-standard status", status="Backlog")

    for a in (unassigned, with_email, explicit_5, domain_usr, started_ip, backlogged):
        scn.append_paragraph(a.as_text())  # pure doc mutation; no action implied yet

    # ── Act 2 — sync converts the lines into actions (Scenario C) ─────────────
    scn.sync()

    # pin what we expect the conversion to produce, then verify across surfaces
    unassigned.status = "Open"
    with_email.status = "Open"             # tokenless → detected Open
    explicit_5.status = "Open"
    domain_usr.status = "Open"
    # explicit_5 / domain_usr already carry AI-5 / AI-9; started_ip keeps In Progress
    # backlogged keeps "Backlog" — non-standard status, exercises status-other.png chip path

    # Resolve auto-assigned action_ids from the sheet — §16.10 shows "AI-1" / "AI-2" but
    # those assume a clean sheet; the live sheet accumulates IDs across runs.
    _action_map = {
        unassigned.action: unassigned,
        with_email.action: with_email,
        started_ip.action: started_ip,
        backlogged.action: backlogged,
    }
    for row in scn.find_sheet_actions():
        target = _action_map.get(row.action)
        if target is not None:
            target.action_id = row.action_id
    assert unassigned.action_id is not None, "unassigned action not found in sheet after sync"
    assert with_email.action_id is not None, "with_email action not found in sheet after sync"
    assert started_ip.action_id is not None, "started_ip action not found in sheet after sync"
    assert backlogged.action_id is not None, "backlogged action not found in sheet after sync"

    for a in (unassigned, with_email, explicit_5, domain_usr, started_ip, backlogged):
        scn.verify_all_expectations(a, tag="[journey sync-create]")     # doc+sheet (+tracker when present); all fields
    scn.verify_consistency(scope=DOC)      # §16.7 checklist + chip integrity (6ov.8)

    # [zc21] DocData consistency: action_count/resolved_count match both the
    # document's floating actions and the ActionSheet, and Team Id matches the
    # document's teamScope appProperty. Filtered to DocData.* issues — other
    # _runConsistencyChecks findings (e.g. assigneeName) are out of scope for
    # zc21 and tracked separately (GTaskSheet-mpe1).
    _vc = (scn._post_fixture("verify_consistency").get("data") or {})
    _vc_docdata_issues = [i for i in _vc.get("issues", []) if i.startswith("DocData.")]
    assert not _vc_docdata_issues, f"[zc21] verify_consistency failed: {_vc_docdata_issues}"

    scn.checkpoint(INTEGRITY)             # capture docx+xlsx; drain the above

    # ── Act 3 — insert the tracker table and re-sync ──────────────────────────
    # Real call-site: the sidebar Insert tracker button (R2-impl).
    scn.mark("act3.pre-insert-tracker")
    with scn.assert_no_addon_error():
        scn.ui.insert_tracker_button(timeout="30s")
    scn.mark("act3.post-insert-tracker")
    scn.sync()
    scn.mark("act3.post-sync")
    for a in (unassigned, with_email, explicit_5, domain_usr, started_ip):
        # entry_point: card call-site for the sidebar "Insert tracker" button
        # (onInsertTrackerTable -> insertTrackerTable) — GTaskSheet-rz4k.3
        scn.verify(a, on=TRACKER, tag="[journey tracker-present]", entry_point="onInsertTrackerTable")  # column form; assignee as chip
    scn.checkpoint(STEP)

    # rwz AC4: tracker ID cells are hyperlinked to chip URLs
    id_urls = scn.tracker_id_urls()
    scn.mark("act3.post-tracker-id-urls")
    for a in (unassigned, with_email, explicit_5, domain_usr, started_ip):
        url = id_urls.get(a.action_id, "")
        assert url and "docId=" in url and "ain=" in url, (
            f"Tracker ID cell for {a.action_id!r} missing chip URL hyperlink; got {url!r}"
        )

    # ── Act 3b — open the homepage sidebar, sync, verify action list ────────
    # R3-impl: sidebar_sync() added here so the Sync Now entry point appears as a
    # scn call-site in the canonical journey matrix (entry-point coverage invariant).
    sidebar = scn.ui.open_sidebar()
    scn.expect_visible(sidebar, timeout="15s")
    scn.mark("act3b.pre-sidebar-sync")
    with scn.assert_no_addon_error():
        scn.ui.sidebar_sync(timeout="60s")  # entry-point call-site: Sync Now button
    scn.mark("act3b.post-sidebar-sync")
    # rwz AC3a: action row shows AI-N • topLabel pattern (explicit_5 is always anchored)
    sidebar.frame.get_by_text(explicit_5.action_id + " •", exact=False).wait_for(
        state="visible", timeout=5000
    )
    # rwz AC3b: delete button present for anchored actions
    sidebar.frame.locator('[aria-label="Delete action"]').first.wait_for(
        state="visible", timeout=5000
    )
    scn.mark("act3b.done")

    # GTaskSheet-yuvq: durable-state assertion that the sidebar "Sync now" click
    # (onSyncNow, doc-context) ran _syncTeamScope to completion and upserted the
    # DocData row for this doc — the exact call-site that crashed before
    # SyncManager.js:70's _openActionSheetSpreadsheet() fix (getActiveSpreadsheet()
    # is null in doc-context).
    def _docdata_row_written() -> str | None:
        row = (scn._post_fixture("get_docdata_row").get("data") or {}).get("row")
        if row is None:
            return f"DocData row missing for {scn.doc_id} after onSyncNow sidebar sync"
        return None

    scn.expect_callable(
        _docdata_row_written, on=SHEET, tag="[journey onSyncNow]",
        entry_point="syncDocument.onSyncNow",
    )

    # ── Act 4 — @create through the editor UI (Playwright phase begins) ───────
    created = ai(
        action="Creating an action via the @-menu trigger",
        assignee="sdonaldson@northlakeuu.org",
    )
    scn.mark("act4.pre-create-action")
    _fence = clear_logs(gas_log_dir) if gas_log_dir else 0.0
    scn.ui.create_action(created)      # fills @-menu form; autocomplete (in TEST_CONTACTS)
    # GTaskSheet-5vr6: cursor lands on an empty paragraph (Ctrl+End+Enter before
    # @create) — the chip-insertion path that used to throw on an empty
    # paragraph/list-item. actionTrigger.done confirms _submitCreateAction
    # ran to completion without the uncaught _insertActionChip exception.
    assert_log(
        gas_log_dir, _fence,
        lambda e: e.get("tag") == "actionTrigger.done",
        "[5vr6] create_action done",
    )

    # action_id left UNSET — next id is ambiguous after AI-1,2,5,9; resolved at D3 below
    # entry_point: editor add-on @-menu create-action submit (_submitCreateAction) —
    # this DOC-surface check is the durable result of the chip insertion it performs
    # (GTaskSheet-rz4k.3)
    scn.verify(created, on=DOC, status="Open", tag="[journey ui-create]", entry_point="_submitCreateAction")  # cheap doc probe, now
    scn.verify(created, on=SHEET, status="Open", at=INTEGRITY, tag="[journey ui-create]")  # async sheet write → defer

    # D1: drain the Open SHEET expectation before set_status changes it (Coordination Log)
    scn.checkpoint(INTEGRITY)

    # D3: resolve created.action_id from live doc (ambiguous until post-sync)
    for item in scn.doc_items():
        if item.action == created.action:
            created.action_id = item.action_id
            break
    assert created.action_id is not None, (
        f"created action not found in doc after Act 4 INTEGRITY; "
        f"expected action text: {created.action!r}"
    )

    # ── Act 5 — change status via the link-preview path (standard run) ────
    # The rendered onLinkPreview card is NOT exercised here: rendering it
    # requires a cursor-placement + retry sequence (Ctrl+F -> Enter -> Escape,
    # move away, re-place — GTaskSheet-39jk/cug8) that takes ~1-2 min and is
    # covered separately by tests/test_link_preview.py (rwz AC1/AC2 header +
    # globalId bubble + in-card status click, ENTRY_POINT_DEFERRED). The
    # standard journey drives the status change through the same core the
    # card's status control invokes (patch_action_status) and asserts the
    # durable result, keeping this journey fast.
    scn.link_preview_status_change(created, "In Progress")  # patch_action_status core
    scn.verify(created, on=SHEET, at=INTEGRITY, tag="[journey status-change]")                 # durable, async (13–60s) → defer

    # ── Final reconcile (HTTP phase) — settle every deferred expectation ──
    scn.checkpoint(INTEGRITY)         # docx+xlsx+tracker+consistency; queue empty at close

    # ── Idempotency pass (bjx7): second sync must leave all surfaces unchanged ─
    scn.sync()
    _idempotency_set = (unassigned, with_email, explicit_5, domain_usr, started_ip, backlogged, created)
    for a in _idempotency_set:
        scn.verify_all_expectations(a, tag="[journey idempotent]")
    scn.checkpoint(INTEGRITY)

    # ── ckj: M2 sheet consistency after idempotency pass ─────────────────────
    # doc_formula (col7) and sync_status (col10) must be set on every row;
    # verify_consistency(scope=SHEET) raises AssertionError if either is missing.
    scn.verify_consistency(scope=SHEET)
