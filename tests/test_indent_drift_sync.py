"""
test_indent_drift_sync.py — [TST] for gts-guux (twin: gts-ttns [IMP]).

Regression coverage for ADR-0031 (knowledge-base/adr/0031-sync-entry-points-
and-rendering-conformance.md), which superseded gts-tne6's original (wider)
design: a continuation-line indent that no longer matches the currently
configured 'SR Indent'/'Field SR Indent' (Config sheet, gts-9a4j) must be
treated as a real difference and reflushed on the next Document Sync -- not
left invisible until someone runs Force Refresh.

No shared context with gts-ttns's implementation: authored against ADR-0031's
recorded decision only (project CLAUDE.md Twin-ticket rule) -- GAS
implementation of the toFlush indentDrift loop was not read while writing
these tests.

Frozen contract this file asserts against (ADR-0031 §Decision/§Consequences):
  - GAS log tag `sync.indentDrift {docId, count}` fires from syncDocument()'s
    toFlush construction when >=1 globalId was added for indent mismatch.
  - Comparison is doc-rendered indent vs. CURRENTLY CONFIGURED Config value,
    independent of _rowIdentityKey -- so an action whose content already
    matches the sheet is still reflushed on indent-only drift.
  - Scope is DOCUMENT CONTEXT ONLY (ADR-0031 §Terminology/§Decision): the
    conforming seam is Document Sync -- menuSyncActiveDoc / the sidebar's
    onSyncNow / the web UI doc sync, all sharing the sync_document route
    that sets `conform: true` (WebApp.js's _handleSyncDocument). It is
    driven here via the `menu_sync_active_doc` TestFixtures.js case, NOT
    the bare `sync_document` fixture (scn.sync()), which calls
    syncDocument() in-process with no opts and therefore never conforms.
  - Spreadsheet Sync All (menuSync -> syncAll) and the unattended 30-minute
    trigger (also syncAll) have NO document context and MUST NOT conform --
    see test_background_sync_never_reflushes_indent_drift below, the
    negative case ADR-0031 requires.
  - onActionSheetEdit stays out of scope (gts-t6xs), unchanged by this ADR.

Config sheet rows are cleared in a `finally` block per gts-9a4j's
test_continuation_indent_config.py pattern (clear_config_rows) -- reusing
that pattern rather than reintroducing the shared-live-sheet leak it fixed.
"""
import pytest

from scn.session import ScenarioSession

from tests.helpers.doc_inspect import load_doc, paragraph_texts_with_breaks
from tests.helpers.download import download_docx


@pytest.fixture
def scn_indent(settings, request):
    """Same clear_config_rows-in-finally pattern as gts-9a4j's
    test_continuation_indent_config.py -- 'SR Indent'/'Field SR Indent' live on
    the Config sheet of the one shared tracker spreadsheet
    (_openActionSheetSpreadsheet has no per-test-doc scoping), so leaving them
    set here leaks a non-default indent into every other test's flush."""
    s = ScenarioSession.new_doc(settings, request=request)
    try:
        yield s
    finally:
        s._post_fixture("clear_config_rows", {})
        s.close()


def _paras_containing(scn, needle):
    return [
        p for p in paragraph_texts_with_breaks(load_doc(download_docx(scn.doc_id)))
        if needle in p
    ]


def _set_indent(scn, sr_indent: int, field_sr_indent: int) -> None:
    set_sr = scn._post_fixture("set_config_row", {"key": "SR Indent", "value": sr_indent})
    assert (set_sr.get("data") or {}).get("ok"), f"set_config_row(SR Indent) failed: {set_sr!r}"
    set_field_sr = scn._post_fixture(
        "set_config_row", {"key": "Field SR Indent", "value": field_sr_indent}
    )
    assert (set_field_sr.get("data") or {}).get("ok"), (
        f"set_config_row(Field SR Indent) failed: {set_field_sr!r}"
    )


def test_indent_only_drift_reflushed_by_document_sync(scn_indent, gas_log_dir):
    """AC (1)/(a) and (4)/(c): an action whose content already matches the sheet,
    but whose doc-rendered continuation-line indent no longer matches the
    CURRENTLY CONFIGURED SR Indent/Field SR Indent, gets reflushed by a
    Document Sync (menuSyncActiveDoc -- ADR-0031's conforming, document-
    context seam) -- proven via sync.indentDrift plus an artifact-truth
    re-read of the doc showing the corrected indent."""
    scn = scn_indent
    if not gas_log_dir:
        pytest.skip("gas_log_dir not configured — indentDrift proof requires GAS log access")

    from tests.helpers.gas_log import assert_log, clear_logs

    _set_indent(scn, 5, 3)
    scn._post_fixture(
        "append_doc_soft_paragraph",
        {"text": "AI: reindent me\n- keep this line\nTarget: some value"},
    )
    scn.sync()  # establishing sync: flushes at SR Indent=5 / Field SR Indent=3

    before = _paras_containing(scn, "reindent me")
    assert len(before) == 1
    assert before[0] == (
        "ACT-1: reindent me (Open)\n"
        "     - keep this line\n"
        "   Target:\tsome value"
    ), f"establishing sync did not apply configured indent: {before[0]!r}"

    # Change config only -- sheet content (assignee/action_text/status) is
    # untouched, so a diff keyed purely on _rowIdentityKey would see this
    # action as fully converged.
    _set_indent(scn, 2, 1)

    fence = clear_logs(gas_log_dir)
    scn._post_fixture("menu_sync_active_doc")  # Document Sync -- conforms, force defaults false

    assert_log(
        gas_log_dir, fence,
        lambda e: e.get("tag") == "sync.indentDrift"
        and e.get("data", {}).get("docId") == scn.doc_id
        and (e.get("data", {}).get("count") or 0) >= 1,
        "[guux] expected sync.indentDrift with count>=1 for a content-converged "
        "action whose continuation-line indent no longer matches Config",
    )

    after = _paras_containing(scn, "reindent me")
    assert len(after) == 1
    assert after[0] == (
        "ACT-1: reindent me (Open)\n"
        "  - keep this line\n"
        " Target:\tsome value"
    ), f"Document Sync did not correct continuation-line indent to new Config values: {after[0]!r}"


def test_matching_indent_and_content_emits_no_indent_drift(scn_indent, gas_log_dir):
    """Non-regression, counterpart to test_menu_entry_points.py's
    test_menuSyncActiveDoc_converged_doc_emits_no_forceFlush: an action already
    matching both content AND the current indent config produces no
    sync.indentDrift and no gratuitous sync.forceFlush on a Document Sync
    (menuSyncActiveDoc)."""
    scn = scn_indent
    if not gas_log_dir:
        pytest.skip("gas_log_dir not configured — indentDrift proof requires GAS log access")

    from tests.helpers.gas_log import assert_no_log, clear_logs

    _set_indent(scn, 4, 2)
    scn._post_fixture(
        "append_doc_soft_paragraph",
        {"text": "AI: already converged\n- steady line\nTarget: steady value"},
    )
    scn.sync()  # establishing sync at SR Indent=4 / Field SR Indent=2

    before = _paras_containing(scn, "already converged")
    assert len(before) == 1
    assert before[0] == (
        "ACT-1: already converged (Open)\n"
        "    - steady line\n"
        "  Target:\tsteady value"
    ), f"establishing sync did not apply configured indent: {before[0]!r}"

    # Same Config values still in effect -- doc indent already matches.
    fence = clear_logs(gas_log_dir)
    scn._post_fixture("menu_sync_active_doc")  # Document Sync -- force defaults false

    assert_no_log(
        gas_log_dir, fence,
        lambda e: e.get("tag") == "sync.indentDrift" and e.get("data", {}).get("docId") == scn.doc_id,
        "[guux] Document Sync of a content- and indent-converged action must not emit sync.indentDrift",
    )
    assert_no_log(
        gas_log_dir, fence,
        lambda e: e.get("tag") == "sync.forceFlush" and e.get("data", {}).get("docId") == scn.doc_id,
        "[guux] Document Sync of a content- and indent-converged action must not emit sync.forceFlush",
    )

    after = _paras_containing(scn, "already converged")
    assert len(after) == 1
    assert after[0] == before[0], "no-op Document Sync must not rewrite an already-converged action"


def test_bold_italic_formatting_does_not_trigger_indent_drift(scn_indent, gas_log_dir):
    """Non-regression (AC's explicit negative case): indent detection must not
    widen to catch arbitrary formatting -- an action carrying bold/italic runs
    (gts-zocq) but no continuation-line indent problem must not emit
    sync.indentDrift (or sync.forceFlush) on a Document Sync re-sync, and its
    runs must survive unchanged. Driven via menu_sync_active_doc (the
    conforming seam) rather than the bare sync_document fixture -- a
    non-conforming re-sync would never reach the indentConforms check at all,
    making the assertion vacuous. Uses the same seed_formatted_action fixture
    as tests/test_inline_formatting.py rather than reading gts-ttns's diff to
    guess what would trip it."""
    scn = scn_indent
    if not gas_log_dir:
        pytest.skip("gas_log_dir not configured — indentDrift proof requires GAS log access")

    from tests.helpers.gas_log import assert_no_log, clear_logs

    seed = scn._post_fixture("seed_formatted_action", {"n": 1})
    seed_data = seed.get("data") or {}
    assert seed_data.get("ok"), f"seed_formatted_action failed: {seed}"

    scn.sync()  # establishing sync: materializes status token, flushes runs

    before = scn._post_fixture("debug_action_runs", {"n": 1}).get("data") or {}
    assert before.get("ok"), f"debug_action_runs failed: {before}"

    fence = clear_logs(gas_log_dir)
    scn._post_fixture("menu_sync_active_doc")  # Document Sync -- force defaults false

    assert_no_log(
        gas_log_dir, fence,
        lambda e: e.get("tag") == "sync.indentDrift" and e.get("data", {}).get("docId") == scn.doc_id,
        "[guux] bold/italic-only content must not emit sync.indentDrift -- indent "
        "detection must not overreach into character-run formatting",
    )
    assert_no_log(
        gas_log_dir, fence,
        lambda e: e.get("tag") == "sync.forceFlush" and e.get("data", {}).get("docId") == scn.doc_id,
        "[guux] bold/italic-only content must not emit sync.forceFlush on a Document Sync",
    )

    after = scn._post_fixture("debug_action_runs", {"n": 1}).get("data") or {}
    assert after.get("scanRuns") == before.get("scanRuns"), (
        "runs changed across a no-op Document Sync -- indent-drift detection must "
        "not disturb bold/italic run formatting"
    )


def test_background_sync_never_reflushes_indent_drift(scn_indent, gas_log_dir):
    """ADR-0031 principle 1 (REQUIRED new case, added 2026-08-31 rescope): a
    sync with NO document context never restyles a document, even one it
    knows is drifted. Seeds an action, converges it via a Document Sync at
    one SR Indent/Field SR Indent, then changes Config so the doc is now
    known-drifted (mirrors test_indent_only_drift_reflushed_by_document_sync's
    setup) -- but instead of a Document Sync, drives BOTH no-document-context
    entry points ADR-0031 classifies as background (the 30-minute trigger's
    own function, via the `sync_all` fixture, and Spreadsheet Sync All, via
    the `menu_sync` fixture -> menuSync() -> syncAll()) and asserts neither
    emits sync.indentDrift nor changes a single byte of the doc's rendering.

    Proven to fail against an implementation that runs conformance inside
    syncAll() -- exactly gts-guux's original (pre-ADR-0031) contract, which
    is why this is the case that keeps the entry-point split honest, not a
    resemblance check."""
    scn = scn_indent
    if not gas_log_dir:
        pytest.skip("gas_log_dir not configured — indentDrift proof requires GAS log access")

    from tests.helpers.gas_log import assert_no_log, clear_logs

    _set_indent(scn, 5, 3)
    scn._post_fixture(
        "append_doc_soft_paragraph",
        {"text": "AI: stay drifted\n- keep this line\nTarget: some value"},
    )
    scn.sync()  # establishing sync: flushes at SR Indent=5 / Field SR Indent=3

    before_establish = _paras_containing(scn, "stay drifted")
    assert len(before_establish) == 1
    assert before_establish[0] == (
        "ACT-1: stay drifted (Open)\n"
        "     - keep this line\n"
        "   Target:\tsome value"
    ), f"establishing sync did not apply configured indent: {before_establish[0]!r}"

    # Drift the doc against the NEW config, exactly like the positive-case
    # test -- but the doc is deliberately never given a Document Sync again,
    # so it stays drifted for the rest of this test.
    _set_indent(scn, 2, 1)
    drifted = _paras_containing(scn, "stay drifted")
    assert drifted == before_establish, "changing Config alone must not touch the doc"

    # No-document-context entry point 1: the 30-minute trigger's own handler.
    fence = clear_logs(gas_log_dir)
    scn._post_fixture("sync_all")

    assert_no_log(
        gas_log_dir, fence,
        lambda e: e.get("tag") == "sync.indentDrift" and e.get("data", {}).get("docId") == scn.doc_id,
        "[guux] syncAll() (trigger path) must never emit sync.indentDrift -- it has "
        "no document context and must not conform rendering (ADR-0031 principle 1)",
    )
    after_trigger = _paras_containing(scn, "stay drifted")
    assert after_trigger == before_establish, (
        "syncAll() (trigger path) rewrote a known-drifted doc's rendering -- "
        "background syncs must leave what a reader last saw untouched"
    )

    # No-document-context entry point 2: Spreadsheet Sync All (menuSync ->
    # syncAll()) -- ADR-0031 groups this with the trigger despite being
    # deliberately clicked by a human, because it has no subject document.
    fence = clear_logs(gas_log_dir)
    scn._post_fixture("menu_sync")

    assert_no_log(
        gas_log_dir, fence,
        lambda e: e.get("tag") == "sync.indentDrift" and e.get("data", {}).get("docId") == scn.doc_id,
        "[guux] Spreadsheet Sync All (menuSync) must never emit sync.indentDrift -- "
        "it sweeps every tracked doc with no subject and must not conform "
        "rendering (ADR-0031 principle 1)",
    )
    after_menu_sync = _paras_containing(scn, "stay drifted")
    assert after_menu_sync == before_establish, (
        "Spreadsheet Sync All (menuSync) rewrote a known-drifted doc's rendering -- "
        "background syncs must leave what a reader last saw untouched"
    )
