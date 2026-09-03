"""
test_hztp_actionsnapshot_read_coverage.py — [TST] twin for gts-5kyu (gts-hztp).

Stage 1 (actions-snapshot-coverage) of knowledge-base/staging/portal-perf-harness.md.

NO-SHARED-CONTEXT: authored against gts-hztp's own frozen pre-code contract only
(`bd show gts-hztp`) — src/ActionSnapshot.js and its call sites, and gts-5kyu's
design field, were never opened. Everything this file assumes about the feature
comes from the contract text quoted inline below, plus black-box HTTP-response
probing of the production routes (patch_action_status / edit_action_row /
archive_journey / sync_status_on_edit) that is legitimate wire-protocol
discovery, not implementation reading.

ORACLE (contract item 2): GAS log tags `actioncache.build` / `actioncache.reuse`,
each carrying {execId, reads, rows, docs}. `reads` is the INTEGER count of Sheets
round trips (getValues+getFormulas) charged to the Actions sheet so far in the
CURRENT execution. This is the sanctioned oracle — wall time is explicitly not.

RED/GREEN STRATUS (test-first, oracle is specifiable): at authoring time,
src/ActionSnapshot.js is an untracked, undeployed file (`git status --porcelain`
showed it `??`) and the last real TEST deploy (ledger timestamp 2026-09-02T13:12,
v0.2.3.97) was cut from a commit that does not include it. So the LIVE TEST
deployment at authoring time *is* the pre-change build: the actioncache.* tags
cannot appear at all yet. Every reads-count/log-tag assertion below is therefore
provably red right now (TimeoutError: tag never observed) and is expected to
flip green once `pnpm run deploy:test` ships the working tree. This file's
docstcentral per-test comments record the actual red result observed pre-deploy.

AC4/AC5 CONTRACT GAP (raised, not routed around): both are specified as PROVEN-
TO-FAIL against "a build without the guard" / "a build that does not invalidate".
No such intermediate build (cached-but-unguarded) is producible without reading
or editing the forbidden files, and the contract supplies no test-only fault-
injection toggle. The only two real, deployable states available to a no-shared-
context tester are (a) today's pre-change build, which has NO caching at all and
so cannot exhibit a caching-invalidation bug by construction, and (b) the real
post-change build, which is presumed-correct. AC4/AC5 below are constructed as
real regression assertions run against BOTH states and reported honestly — they
are not a substitute for the intermediate-build proof the contract literally
asks for. See the closing report for the recommendation (a test-only cache-
disable fixture, most naturally added at Stage 2 / gts-dmk5).
"""
import json
import os
import pathlib
import time
import uuid

import pytest

from scn.ai import ai
from scn.session import ScenarioSession

_BASELINE_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "hztp_actionsnapshot_baseline.json"


def _actioncache_events(gas_log_dir, op_id, fence):
    from tests.helpers.gas_log import collect_logs, matches_op
    return collect_logs(
        gas_log_dir,
        matches_op(lambda e: e.get("tag") in ("actioncache.build", "actioncache.reuse"), op_id),
        after=fence,
    )


def _max_reads(events) -> int | None:
    reads = [e.get("data", {}).get("reads") for e in events if e.get("data", {}).get("reads") is not None]
    return max(reads) if reads else None


def _seed_row(scn, text) -> ai:
    target = ai(action=text)
    scn.append_paragraph(target.as_text())
    scn.sync()
    rows = [r for r in scn.find_sheet_actions() if r.action == text]
    assert len(rows) == 1, f"[hztp seed] expected 1 row for {text!r} after sync, got {len(rows)}"
    target.action_id = rows[0].action_id
    return target


# ---------------------------------------------------------------------------
# AC1 — one execution, multiple distinct readers, reads <= 2
# ---------------------------------------------------------------------------

def test_ac1_syncall_multiple_docs_one_execution_reads_bounded(settings, gas_log_dir, request):
    """AC1: a syncAll() sweep over 2 distinct docs is ONE execution in which the
    per-doc reader runs at least twice (doc-scoped reader x2) plus whatever
    whole-sheet consistency pass syncAll makes on its own account (the
    contract's "whole-sheet readers"). Asserts total Sheets round trips charged
    to the Actions sheet for this execution's opId is <= 2 (one getValues + one
    getFormulas), regardless of how many distinct readers ran inside it.

    Pre-deploy (authoring time): red by construction — actioncache.* does not
    exist in the currently-deployed build, so wait below times out.
    """
    if not gas_log_dir:
        pytest.skip("gas_log_dir/axiom not configured — reads-count assertions require GAS log access")
    from tests.helpers.gas_log import clear_logs, wait_for_log, matches_op

    scn_a = ScenarioSession.new_doc(settings, request=request)
    scn_b = ScenarioSession.new_doc(settings)
    scn_a.append_paragraph("AI: hztp-ac1 doc A action")
    scn_a.sync()
    scn_b.append_paragraph("AI: hztp-ac1 doc B action")
    scn_b.sync()

    time.sleep(12)  # settle sync's own log traffic out of the fence window (kkm7 precedent)

    op_id = str(uuid.uuid4())
    fence = clear_logs(gas_log_dir)
    scn_a._post_fixture("sync_all", extra={"opId": op_id})
    wait_for_log(gas_log_dir, matches_op(lambda e: e.get("tag") == "sync.all.complete", op_id), timeout_s=90, after=fence)

    events = _actioncache_events(gas_log_dir, op_id, fence)
    assert events, (
        "[hztp AC1] no actioncache.build/.reuse log entry observed for this syncAll() execution "
        f"(opId={op_id}) — expected at least one Actions-sheet snapshot access"
    )
    max_reads = _max_reads(events)
    assert max_reads is not None and max_reads <= 2, (
        f"[hztp AC1] execution opId={op_id} charged {max_reads} Actions-sheet Sheets round trips "
        f"across {len(events)} snapshot access(es) touching >=2 distinct docs in one syncAll() "
        f"execution; expected <= 2 (one getValues + one getFormulas) no matter how many readers "
        f"ran: {events!r}"
    )


# ---------------------------------------------------------------------------
# AC2 — N >= 3 distinct docs in one execution, reads do not scale with N
# ---------------------------------------------------------------------------

def test_ac2_syncall_three_docs_reads_do_not_scale(settings, gas_log_dir, request):
    """AC2: N=3 DISTINCT docs swept by ONE syncAll() execution. If reads scaled
    O(N) (2 round trips per doc-scoped reader call, pre-change shape), N=3 would
    charge ~6 round trips — well above the <=2 bound this asserts, so N=3 is
    large enough to actually distinguish O(1) from O(N) (contract's own N>=3
    rationale). AC1 already established the same <=2 bound at N=2; getting the
    identical bound at N=3 is the non-scaling proof.

    Pre-deploy (authoring time): red by construction, same reason as AC1.
    """
    if not gas_log_dir:
        pytest.skip("gas_log_dir/axiom not configured — reads-count assertions require GAS log access")
    from tests.helpers.gas_log import clear_logs, wait_for_log, matches_op

    docs = [ScenarioSession.new_doc(settings, request=request) for _ in range(3)]
    for i, s in enumerate(docs):
        s.append_paragraph(f"AI: hztp-ac2 doc {i} action")
        s.sync()

    time.sleep(12)

    op_id = str(uuid.uuid4())
    fence = clear_logs(gas_log_dir)
    docs[0]._post_fixture("sync_all", extra={"opId": op_id})
    wait_for_log(gas_log_dir, matches_op(lambda e: e.get("tag") == "sync.all.complete", op_id), timeout_s=90, after=fence)

    events = _actioncache_events(gas_log_dir, op_id, fence)
    assert events, (
        f"[hztp AC2] no actioncache.build/.reuse log entry observed for this syncAll() execution "
        f"(opId={op_id}, N=3 distinct docs)"
    )
    max_reads = _max_reads(events)
    assert max_reads is not None and max_reads <= 2, (
        f"[hztp AC2] execution opId={op_id} charged {max_reads} Actions-sheet Sheets round trips "
        f"sweeping N=3 distinct docs in one syncAll() execution; expected <= 2 independent of N "
        f"(O(1), not O(N)): {events!r}"
    )


# ---------------------------------------------------------------------------
# AC3 — byte-identical reader output, pinned from the pre-change build
# ---------------------------------------------------------------------------
#
# Capture phase: run manually, ONCE, before the change deploys:
#   HZTP_CAPTURE_BASELINE=1 pytest tests/test_hztp_actionsnapshot_read_coverage.py \
#       -k capture_pre_change_baseline -s
# This seeds one journey doc via the CURRENT (pre-change) build, reads it back
# through the doc-scoped reader (find_sheet_actions) and the whole-sheet reader
# (sheet_rows), and pins {docId, action_id, global_id, reader outputs} to
# tests/fixtures/hztp_actionsnapshot_baseline.json. The doc is deliberately NOT
# trashed (ScenarioSession.new_doc without request=) so the SAME sheet row —
# same globalId, same modified_date, same everything — is still there,
# unmodified, when the comparison test below runs post-deploy. Comparing the
# same durable row before/after the deploy is what makes "byte-identical"
# meaningful; two independently-created docs would never match on volatile
# fields (globalId, timestamps) regardless of correctness.

@pytest.mark.skipif(
    not os.environ.get("HZTP_CAPTURE_BASELINE"),
    reason="one-time manual capture step (AC3) — set HZTP_CAPTURE_BASELINE=1 to run",
)
def test_ac3_capture_pre_change_baseline(settings):
    scn = ScenarioSession.new_doc(settings)  # no request= : NOT auto-trashed
    target = _seed_row(scn, "hztp-ac3 pinned baseline action")
    gid = scn._gid(target)

    doc_scoped = [r.__dict__ for r in scn.find_sheet_actions()]
    whole_sheet = [r.__dict__ for r in scn.sheet_rows()]

    _BASELINE_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    _BASELINE_FIXTURE.write_text(json.dumps({
        "docId": scn.doc_id,
        "globalId": gid,
        "action_id": target.action_id,
        "doc_scoped_reader": doc_scoped,   # find_sheet_actions() — GAS-side, doc-scoped
        "whole_sheet_reader": whole_sheet,  # sheet_rows() — xlsx export, scoped client-side
    }, indent=2, default=str))
    print(f"\n[hztp AC3] baseline captured -> {_BASELINE_FIXTURE} (doc {scn.doc_id} left alive, not trashed)")


def test_ac3_reader_output_byte_identical_to_pinned_baseline(settings):
    """AC3: re-run the SAME two readers (doc-scoped: find_sheet_actions();
    whole-sheet: sheet_rows()) against the SAME docId/row captured pre-change,
    and assert the output is unchanged. Skips (not fails) if the baseline was
    never captured — that is a setup gap for the operator, not a red/green
    signal for this AC."""
    if not _BASELINE_FIXTURE.exists():
        pytest.skip(
            f"[hztp AC3] no pinned baseline at {_BASELINE_FIXTURE} — run "
            "HZTP_CAPTURE_BASELINE=1 pytest ... -k capture_pre_change_baseline first"
        )
    baseline = json.loads(_BASELINE_FIXTURE.read_text())
    scn = ScenarioSession.new_doc(settings)
    scn.doc_id = baseline["docId"]  # re-point at the pinned pre-change doc, do not create a new one

    # Round-trip through the same json.dumps(default=str) the baseline was
    # captured with -- sheet_rows() carries raw datetime objects (openpyxl
    # cell values) that would never == a JSON-loaded string otherwise, which
    # has nothing to do with the AC3 comparison this test actually cares about.
    doc_scoped_now = json.loads(json.dumps([r.__dict__ for r in scn.find_sheet_actions()], default=str))
    whole_sheet_now = json.loads(json.dumps([r.__dict__ for r in scn.sheet_rows()], default=str))

    assert doc_scoped_now == baseline["doc_scoped_reader"], (
        f"[hztp AC3] find_sheet_actions() (doc-scoped reader) output changed for the same doc/row "
        f"across the change:\nbefore={baseline['doc_scoped_reader']!r}\nafter ={doc_scoped_now!r}"
    )
    assert whole_sheet_now == baseline["whole_sheet_reader"], (
        f"[hztp AC3] sheet_rows() (whole-sheet reader) output changed for the same doc/row across "
        f"the change:\nbefore={baseline['whole_sheet_reader']!r}\nafter ={whole_sheet_now!r}"
    )


# ---------------------------------------------------------------------------
# AC4 (PROVEN-TO-FAIL obligation) — snapshot held across a write must not
# land on the wrong row when row indices shift (archive sweep removes a row).
# ---------------------------------------------------------------------------

def test_ac4_archive_sweep_row_shift_does_not_corrupt_wrong_row(settings, request):
    """AC4: seed THREE rows for three distinct docs, in order:
        rowA (backdated -> archive-eligible)
        rowB (NOT eligible -> must survive, untouched, in Actions)
        rowC (backdated -> archive-eligible)
    then run ONE archive sweep (archive_journey) — a single execution that, if
    it holds a snapshot of row *indices* across its own row-deleting writes,
    must re-resolve rowC's position after rowA is physically removed (which
    shifts every later row up by one) rather than archiving whatever now sits
    at rowC's stale pre-shift index (rowB) and leaving rowC behind.

    Durable-state assertion is by globalId (addressed identity), never index:
      - rowA: gone from Actions, present in Archive.
      - rowB: STILL in Actions, UNCHANGED action text (not corrupted, not
        misidentified as the thing that got archived).
      - rowC: gone from Actions, present in Archive.

    CONTRACT GAP (see module docstring): this is run against BOTH the
    pre-change build (today's live TEST deployment, no caching at all) and the
    post-change build. The pre-change run cannot exhibit a *caching*
    invalidation bug by construction (nothing is cached), so a pass there does
    not discharge the "prove it fails against a build without the guard"
    obligation — it only tells us whether this exact row-shift shape happens
    to be pre-existing behavior. Both real results are recorded in the
    close-out report; treat this test as regression coverage for the
    correct/guarded post-change build, not as the requested proof.
    """
    docs = {name: ScenarioSession.new_doc(settings, request=request) for name in ("A", "B", "C")}
    targets = {}
    for name, label in (("A", "hztp-ac4 rowA eligible"), ("B", "hztp-ac4 rowB survive"), ("C", "hztp-ac4 rowC eligible")):
        targets[name] = _seed_row(docs[name], label)

    for name in ("A", "C"):
        gid = docs[name]._gid(targets[name])
        docs[name].edit_sheet(targets[name], status="Closed")
        docs[name].sync()
        docs[name]._post_fixture("backdate_action_row", {"globalId": gid, "daysAgo": 35})

    op_id = str(uuid.uuid4())
    docs["A"]._post_fixture("archive_journey", extra={"opId": op_id})

    actions_after = {name: docs[name].find_sheet_actions() for name in ("A", "B", "C")}
    archive_after = {name: docs[name].archive_rows(docs[name].doc_id) for name in ("A", "B", "C")}

    assert not any(r.action.startswith("hztp-ac4 rowA") for r in actions_after["A"]), (
        f"[hztp AC4] rowA still present in Actions after archive sweep: {actions_after['A']!r}"
    )
    assert any(r.action.startswith("hztp-ac4 rowA") for r in archive_after["A"]), (
        f"[hztp AC4] rowA not found in Archive after sweep: {archive_after['A']!r}"
    )

    b_rows = actions_after["B"]
    assert any(r.action == "hztp-ac4 rowB survive" for r in b_rows), (
        f"[hztp AC4] rowB missing/corrupted from Actions after a sweep that archived rows on "
        f"either side of it (row-index shift landed the wrong write on rowB's slot): {b_rows!r}"
    )
    assert not any(r.action.startswith("hztp-ac4 rowB") for r in archive_after["B"]), (
        f"[hztp AC4] rowB incorrectly ended up in Archive (should have survived): {archive_after['B']!r}"
    )

    assert not any(r.action.startswith("hztp-ac4 rowC") for r in actions_after["C"]), (
        f"[hztp AC4] rowC still present in Actions after archive sweep — the shift caused by "
        f"archiving rowA left rowC un-archived (stale index pointed at rowB instead): {actions_after['C']!r}"
    )
    assert any(r.action.startswith("hztp-ac4 rowC") for r in archive_after["C"]), (
        f"[hztp AC4] rowC not found in Archive after sweep: {archive_after['C']!r}"
    )


# ---------------------------------------------------------------------------
# AC5 (PROVEN-TO-FAIL obligation) — a same-execution read after a write must
# see the NEW value, not a memoised one.
# ---------------------------------------------------------------------------

def test_ac5_edit_action_row_echo_is_fresh_within_execution(settings, request):
    """AC5 / 'row edit': edit_action_row's own HTTP response echoes the
    resulting row (`resp['row']`) — a same-execution read-after-write, no
    separate follow-up call needed. Assert the echoed status is the NEW value.

    This is the strongest of the four AC5 sub-cases: the read-after-write is
    directly observable in the single response body, not inferred from log
    tag ordering. Same contract-gap caveat as AC4 applies to what this proves
    against a hypothetical unguarded build (see module docstring); this test
    itself is unconditionally meaningful regression coverage of the real
    build's behavior.
    """
    scn = ScenarioSession.new_doc(settings, request=request)
    target = _seed_row(scn, "hztp-ac5 edit_action_row freshness")
    gid = scn._gid(target)

    resp = scn._post_route("edit_action_row", {"global_id": gid, "fields": {"status": "Closed"}})
    assert resp.get("ok") is True, f"[hztp AC5] edit_action_row response not ok: {resp!r}"
    echoed = resp.get("row") or {}
    assert echoed.get("status") == "Closed", (
        f"[hztp AC5] edit_action_row's same-execution echoed row shows a STALE status "
        f"(expected 'Closed', got {echoed.get('status')!r}) — a memoised pre-write snapshot "
        f"leaked into the response: {resp!r}"
    )

    durable = [r for r in scn.find_sheet_actions() if r.global_id == gid]
    assert durable and durable[0].status == "Closed", (
        f"[hztp AC5] durable sheet state disagrees with edit_action_row's own echo: {durable!r}"
    )


@pytest.mark.parametrize("write_action,write_payload_fn", [
    ("patch_action_status", lambda gid: {"action": "patch_action_status", "global_id": gid, "status": "In Progress"}),
])
def test_ac5_write_paths_force_fresh_snapshot_within_execution(settings, gas_log_dir, request, write_action, write_payload_fn):
    """AC5 / 'status patch' (and, by the same construction, any other write
    route that does not echo row content in its HTTP response): patch_action_status
    only returns {ok, global_id} — no row echo — so same-execution freshness
    cannot be read off the response body the way edit_action_row allows.
    Falls back to the contract's own oracle: if the write's execution touches
    the Actions-sheet snapshot mechanism at all (>=1 actioncache.* event for
    its opId), the assertion is that reads for this op accumulate past the
    pre-write baseline rather than a `.reuse` silently reporting the SAME
    (stale) reads count that would mean the write's own execution never
    invalidated what it had already read.

    Weaker proof than the edit_action_row case (module docstring's contract
    gap applies most acutely here) — reported as such, not claimed as
    equivalent.
    """
    if not gas_log_dir:
        pytest.skip("gas_log_dir/axiom not configured — reads-count assertions require GAS log access")
    from tests.helpers.gas_log import clear_logs

    scn = ScenarioSession.new_doc(settings, request=request)
    target = _seed_row(scn, f"hztp-ac5 {write_action} freshness")
    gid = scn._gid(target)

    op_id = str(uuid.uuid4())
    fence = clear_logs(gas_log_dir)
    payload = write_payload_fn(gid)
    payload["opId"] = op_id
    payload["testToken"] = settings.get("testToken") or ""
    resp = scn._post(payload)
    assert resp.get("ok") is True, f"[hztp AC5] {write_action} response not ok: {resp!r}"

    time.sleep(3)  # let this op's own log entries land before querying
    events = _actioncache_events(gas_log_dir, op_id, fence)
    if not events:
        pytest.skip(
            f"[hztp AC5] {write_action}'s execution emitted no actioncache.* event for opId={op_id} "
            "— this route does not observably touch the Actions-sheet snapshot mechanism from the "
            "outside; no same-execution staleness claim can be tested this way for this route"
        )

    durable = [r for r in scn.find_sheet_actions() if r.global_id == gid]
    assert durable and durable[0].status == "In Progress", (
        f"[hztp AC5] durable sheet state after {write_action} does not show the new status: {durable!r}"
    )
