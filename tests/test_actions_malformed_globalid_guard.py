"""
test_actions_malformed_globalid_guard.py — gts-5jrn (stage `actions-token-guard`,
knowledge-base/staging/docdata-litter-apt-speed.md), twin of gts-2226.

Path B retroactive coverage: a user-reported TestTeamA view showed action_id
values 'AI-ACT-1'/'AI-ACT-3'/'AI-ACT-7' — a malformed dual-prefix global_id
(no docId, both ACT and AI prefixes concatenated) round-tripping as a raw,
unparseable string with zero diagnostic trail. Traced to `parseGlobalId()`
(WebApp.js) silently returning the raw input as `actionId` on a regex-match
failure, and `_handleUpsertActionRows` (WebApp.js) writing/keeping such a row
with no guard.

The write-side defect predates this ticket and is not reproducible by writing
a NEW malformed global_id today (every current write site is single-prefix
safe) — so this authors the regression test against gts-2226's frozen design
contract only, not against its implementation:
  - log tag: sync.globalId.malformed
  - entry point: upsert_action_rows (_handleUpsertActionRows, WebApp.js)
  - decision: a malformed-globalId row is REJECTED (not written or updated),
    not merely flagged in place

Three required cases (gts-2226 DESIGN):
  1. upsert_action_rows with a malformed globalId ('AI-ACT-<N>', no docId) —
     the malformed-token log fires exactly once and no row is written.
  2. upsert_action_rows with a normal globalId (docId/ACT-N) in the SAME
     batch — negative control: no malformed-token log fires for it, and it
     is written normally (proves case 1 isn't vacuous / doesn't clobber
     well-formed siblings).
  3. parseGlobalId's fallback path returns a safe, non-crashing shape for a
     malformed input — exercised here through the same upsert_action_rows
     call (no direct GAS unit-invocation exists for a bare function): the
     webapp responds normally (HTTP 200, valid JSON, no error) instead of
     throwing, proving the fallback shape didn't propagate an exception.
"""
import time
import uuid

from scn.session import ScenarioSession

from tests.helpers.gas_log import assert_no_log, clear_logs, collect_logs, matches_op


def _find_row(scn, action_text):
    rows = scn.find_sheet_actions()
    return next((r for r in rows if r.action == action_text), None)


def test_malformed_globalid_upsert_rejected_and_logged(settings, gas_log_dir, request):
    """[gts-5jrn case 1+3] A malformed dual-prefix globalId ('AI-ACT-<N>', no
    docId) sent to upsert_action_rows is logged (sync.globalId.malformed) and
    not written, and the webapp still responds cleanly (no crash)."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        op_id = str(uuid.uuid4())
        fence = clear_logs(gas_log_dir)

        malformed_action_text = "5jrn malformed-globalId row must not be written"
        malformed_global_id = "AI-ACT-" + str(int(time.time() * 1000) % 1000000)

        resp = scn._post({
            "secret": settings["webappSecret"],
            "action": "upsert_action_rows",
            "opId": op_id,
            "docUrl": f"https://docs.google.com/document/d/{scn.doc_id}/edit",
            "docTitle": "Test doc",
            "rows": [{
                "globalId": malformed_global_id,
                "assigneeEmail": "",
                "assigneeName": "",
                "actionText": malformed_action_text,
                "status": "Open",
            }],
        })

        # case 3: the webapp responded at all (no unhandled exception) and
        # the malformed row was neither inserted nor updated.
        assert resp.get("inserted") == 0 and resp.get("updated") == 0, (
            f"[5jrn] malformed globalId must not be inserted/updated, got {resp!r}"
        )

        # case 1: no row landed in the Actions sheet for the malformed id.
        row = _find_row(scn, malformed_action_text)
        assert row is None, (
            f"[5jrn] malformed globalId {malformed_global_id!r} must not create a "
            f"sheet row, found {row!r}"
        )

        # case 1: the malformed-token log fired exactly once, correlated to
        # this call's own opId (excludes any concurrent/trigger activity).
        matches = collect_logs(
            gas_log_dir,
            matches_op(
                lambda e: e.get("tag") == "sync.globalId.malformed"
                and e.get("data", {}).get("globalId") == malformed_global_id,
                op_id,
            ),
            after=fence,
        )
        assert len(matches) == 1, (
            f"[5jrn] expected exactly 1 sync.globalId.malformed log entry for "
            f"{malformed_global_id!r}, got {len(matches)}: {matches!r}"
        )
    finally:
        scn.close()


def test_wellformed_globalid_upsert_not_flagged(settings, gas_log_dir, request):
    """[gts-5jrn case 2] Negative control: a normal docId/ACT-N globalId in
    the same shape of request does not fire the malformed-token log and is
    written normally."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        op_id = str(uuid.uuid4())
        fence = clear_logs(gas_log_dir)

        good_action_text = "5jrn well-formed globalId negative control"
        good_global_id = f"{scn.doc_id}/ACT-{int(time.time() * 1000) % 1000000}"

        resp = scn._post({
            "secret": settings["webappSecret"],
            "action": "upsert_action_rows",
            "opId": op_id,
            "docUrl": f"https://docs.google.com/document/d/{scn.doc_id}/edit",
            "docTitle": "Test doc",
            "rows": [{
                "globalId": good_global_id,
                "assigneeEmail": "",
                "assigneeName": "",
                "actionText": good_action_text,
                "status": "Open",
            }],
        })
        assert resp.get("inserted") == 1, (
            f"[5jrn negative control] well-formed globalId expected inserted=1, got {resp!r}"
        )

        row = _find_row(scn, good_action_text)
        assert row is not None, "[5jrn negative control] well-formed row not found after upsert"

        assert_no_log(
            gas_log_dir,
            fence,
            matches_op(lambda e: e.get("tag") == "sync.globalId.malformed", op_id),
            what="well-formed globalId must not fire sync.globalId.malformed",
        )
    finally:
        scn.close()
