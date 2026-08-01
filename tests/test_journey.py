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

Act 6 (configFormat, gts-d99c/gts-1pk): a journey-embedded step group, not a
dedicated file -- test-organization decision recorded in gts-1pk/gts-28p.
Authored from gts-1pk's frozen contract text (Description/AC/Design), not by
reading _configFormatForDoc's implementation diff, per CLAUDE.md's
no-shared-context twin-ticket rule.
"""
import pathlib
import time

import pytest

from scn.ai import ai
from scn.engine import CheckpointKind, Severity, Surface
from scn.reporter import emit_standalone_event
from scn.session import ScenarioSession, resolve_auth_file
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

    auth = resolve_auth_file()
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

def test_journey(scn, expected_version, gas_log_dir, settings):
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
    _fence = clear_logs(gas_log_dir)
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

    # GTaskSheet-5ab2c9c-regression: _submitCreateAction no longer upserts the
    # sheet row itself (doc is source of truth; "the sheet row will be created
    # by the next sync" — EditorAddonCard.js comment). The deferred SHEET
    # expectation above needs that sync to actually happen before the
    # checkpoint reads the sheet, or it observes a row that was never written.
    scn.sync()

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

    # ── Act 6 — configFormat: sample a styled reference doc's action-item ────
    # style, apply it to a chip write in a DIFFERENT document, then verify a
    # Config-clear restores the exact prior hardcoded default (gts-d99c/
    # gts-1pk twin ticket). See module docstring for the test-placement note.
    #
    # The two style dicts below are fixed fixture constants mirrored in
    # TestFixtures.js's 'seed_styled_action' case (_TF_STYLED_AI_TOKEN /
    # _TF_STYLED_ACTION_TEXT) -- hardcoded here rather than re-derived from
    # that file, so a fixture/assertion drift surfaces as a failure instead
    # of a vacuous pass. `default_ai_token` mirrors SyncManager.js's
    # _DEFAULT_AI_TOKEN_STYLE (Comic Sans MS bold purple #4C1D95) per
    # gts-1pk's frozen AC text, not by reading that file.
    styled_ai_token = {
        "fontFamily": "Georgia", "bold": True, "italic": False, "underline": True,
        "color": "#1b5e20",
    }
    styled_action_text = {
        "fontFamily": "Courier New", "bold": False, "italic": True, "underline": False,
        "color": "#b71c1c",
    }
    default_ai_token = {"fontFamily": "Comic Sans MS", "bold": True, "color": "#4c1d95"}

    ref_scn = ScenarioSession.new_doc(settings)
    try:
        # Step 1 — seed a reference doc, distinct from the journey's own doc,
        # with a styled first AI-1: action.
        ref_scn._post_fixture("seed_styled_action")

        # Step 2 — sample its style into the Config sheet.
        cfg_data = ref_scn._post_fixture(
            "config_format", {"docId": ref_scn.doc_id}
        ).get("data") or {}
        assert cfg_data.get("ok") is True, (
            f"[gts-d99c] config_format fixture did not report success: {cfg_data!r}"
        )

        # Step 3 — Config sheet has exactly one 'ai_token' + one 'action_text'
        # row, matching the sampled style (durable-state assertion).
        def _config_sampled_correctly():
            rows = (scn._post_fixture("get_config_rows").get("data") or {}).get("rows") or []
            by_key = {r["key"]: r["value"] for r in rows}
            if set(by_key.keys()) != {"ai_token", "action_text"}:
                return (
                    f"expected exactly one 'ai_token' + one 'action_text' Config row "
                    f"after sampling, got keys {list(by_key.keys())}: {rows!r}"
                )
            for field in ("fontFamily", "bold", "italic", "underline"):
                if by_key["ai_token"].get(field) != styled_ai_token[field]:
                    return f"Config 'ai_token'.{field}={by_key['ai_token'].get(field)!r} != sampled {styled_ai_token[field]!r}"
                if by_key["action_text"].get(field) != styled_action_text[field]:
                    return f"Config 'action_text'.{field}={by_key['action_text'].get(field)!r} != sampled {styled_action_text[field]!r}"
            if (by_key["ai_token"].get("color") or "").lower() != styled_ai_token["color"]:
                return f"Config 'ai_token'.color={by_key['ai_token'].get('color')!r} != sampled {styled_ai_token['color']!r}"
            if (by_key["action_text"].get("color") or "").lower() != styled_action_text["color"]:
                return f"Config 'action_text'.color={by_key['action_text'].get('color')!r} != sampled {styled_action_text['color']!r}"
            return None

        scn.expect_callable(
            _config_sampled_correctly, on=SHEET,
            tag="[journey configFormat-sample]", entry_point="configFormat",
        )
        scn.checkpoint(STEP)

        # Step 4 — a DIFFERENT document's (the journey's own doc) subsequent
        # chip write reflects the sampled style, verified via the Docs REST
        # GET the flush itself uses (not visually).
        marker_styled = "configFormat sampled-style smoke check"
        scn.append_paragraph(f"AI: {marker_styled}")
        scn.sync()

        def _different_doc_picks_up_sampled_style():
            rows = [r for r in scn.find_sheet_actions() if marker_styled in (r.action or "")]
            if not rows:
                return f"marker action {marker_styled!r} not found on sheet after sync"
            try:
                n = int(rows[0].action_id.split("-")[1])
            except Exception as exc:
                return f"could not parse action_id {rows[0].action_id!r}: {exc}"
            style = scn._post_fixture("debug_action_text_style", {"n": n}).get("data") or {}
            if not style.get("ok"):
                return f"debug_action_text_style failed: {style!r}"
            tok, act = style.get("aiToken") or {}, style.get("actionText") or {}
            for field in ("fontFamily", "bold", "italic", "underline"):
                if tok.get(field) != styled_ai_token[field]:
                    return f"chip aiToken.{field}={tok.get(field)!r} != sampled {styled_ai_token[field]!r}"
                if act.get(field) != styled_action_text[field]:
                    return f"chip actionText.{field}={act.get(field)!r} != sampled {styled_action_text[field]!r}"
            if (tok.get("color") or "").lower() != styled_ai_token["color"]:
                return f"chip aiToken.color={tok.get('color')!r} != sampled {styled_ai_token['color']!r}"
            if (act.get("color") or "").lower() != styled_action_text["color"]:
                return f"chip actionText.color={act.get('color')!r} != sampled {styled_action_text['color']!r}"
            return None

        scn.expect_callable(
            _different_doc_picks_up_sampled_style, on=DOC,
            tag="[journey configFormat-cross-doc]", entry_point="configFormat",
        )
        scn.checkpoint(STEP)

        # Step 5 — clear Config rows. Explicitly a reset, NOT an undo to a
        # prior style (_configFormatForDoc has no stack/undo semantics).
        scn._post_fixture("clear_config_rows")
        cleared_rows = (scn._post_fixture("get_config_rows").get("data") or {}).get("rows") or []
        assert cleared_rows == [], f"[gts-1pk] Config rows not cleared: {cleared_rows!r}"

        # Step 6 — sync again (a new chip write): the exact pre-existing
        # hardcoded default (Comic Sans MS bold purple token, inherited-
        # default action text) is restored -- the fallback-path regression
        # guard.
        #
        # Uses a THIRD, pristine doc (not scn's own journey doc, which
        # already carries the Step 4 custom-styled chip) -- confirmed via
        # manual probe during this session that Google Docs' insertText
        # inherits the AMBIENT style of nearby text when no explicit
        # updateTextStyle request is pushed (exactly what happens once
        # Config's 'action_text' row is cleared): reusing scn's own doc made
        # the new action text inherit the still-present Step-4 custom style
        # from the adjacent paragraph, which would make a "does NOT carry the
        # custom style" assertion pass or fail by accident of doc layout
        # rather than by what _actionTextStyleRequest actually did. A fresh
        # doc has no such neighbor to inherit from, so its action-text style
        # is the genuine Google Docs blank-paragraph default.
        reset_scn = ScenarioSession.new_doc(settings)
        try:
            marker_reset = "configFormat reset-to-default smoke check"
            reset_scn.append_paragraph(f"AI: {marker_reset}")
            reset_scn.sync()

            def _reset_to_hardcoded_default():
                rows = [r for r in reset_scn.find_sheet_actions() if marker_reset in (r.action or "")]
                if not rows:
                    return f"marker action {marker_reset!r} not found on sheet after sync"
                try:
                    n2 = int(rows[0].action_id.split("-")[1])
                except Exception as exc:
                    return f"could not parse action_id {rows[0].action_id!r}: {exc}"
                style = reset_scn._post_fixture("debug_action_text_style", {"n": n2}).get("data") or {}
                if not style.get("ok"):
                    return f"debug_action_text_style failed: {style!r}"
                tok = style.get("aiToken") or {}
                if tok.get("fontFamily") != default_ai_token["fontFamily"]:
                    return f"AI-N token font not reset to hardcoded default: {tok!r}"
                if tok.get("bold") != default_ai_token["bold"]:
                    return f"AI-N token bold not reset to hardcoded default: {tok!r}"
                if (tok.get("color") or "").lower() != default_ai_token["color"]:
                    return f"AI-N token color not reset to hardcoded default: {tok!r}"
                act = style.get("actionText") or {}
                if act.get("fontFamily") == styled_action_text["fontFamily"] and act.get("italic") == styled_action_text["italic"]:
                    return (
                        f"action text on a pristine doc still carries the custom sampled "
                        f"style (fontFamily+italic) after Config clear: {act!r}"
                    )
                return None

            scn.expect_callable(
                _reset_to_hardcoded_default, on=DOC,
                tag="[journey configFormat-reset-default]", entry_point="configFormat",
            )
            scn.checkpoint(STEP)
        finally:
            try:
                reset_scn._post_route("end_journey_session", {"docId": reset_scn.doc_id})
            except Exception:
                pass
    finally:
        try:
            ref_scn._post_route("end_journey_session", {"docId": ref_scn.doc_id})
        except Exception:
            pass
