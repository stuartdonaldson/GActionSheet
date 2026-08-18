"""
test_team_listing.py — Twin TST for gts-79dw.4.3 ([IMP] Team action listing
endpoint (status + scope filters)).

Pre-code / frozen contract, docs/verified-team-portal-plan.md §12.1 (frozen
2026-07-27, supersedes this bead's own earlier `design` field where they
disagree):

  Entry point: doPost action 'list_team_actions', body
    { assertion, teamId, statusFilter, windowDays?, scope } (assertion field
    renamed from idToken by gts-79dw.4.18 -- see tests/test_signed_assertion.py).
  Log tag: GasLogger 'webapp.team.list' with
    { sub, tier, statusFilter, scope, count }.
  Response: { tier, teamId, actions: [<row>...], statusOptions }, rows
    carrying exactly:
      global_id, action_id, action_text, assignee_email, assignee_name,
      status, status_bucket, status_resolved, status_icon,
      doc_id, doc_name, doc_url, created_date, modified_date

Frozen invariants under test (the ones the eventual gts-79dw.4.8 hardening
pass will also assert):
  1. A stale OPEN action never ages out regardless of windowDays.
  2. closed/all age out resolved rows outside windowDays; exact boundary.
  3. Status bucketing is via isResolved()/getStatusDisplay(), not literal
     string match -- an off-vocabulary status still lands in a bucket and is
     excluded from statusOptions.
  4. scope=mine composes with statusFilter in ONE server query.
  5. R13b: rows are excluded when the action's own sync_status OR its source
     document's DocData.syncStatus is Deleted/Doc Not Found.
  6. Fail-closed: NONE tier returns no action data.

No live GIS ID token is available non-interactively (Spike S2; same
constraint documented in tests/test_verify_access.py) -- there is no way to
drive `list_team_actions` end-to-end with a VIEW/EDIT-resolving identity in
this environment. This file therefore proves invariants 1/2/3/4/5 against
`_readTeamActions` directly via the testToken-gated `read_team_actions`
route (src/WebApp.js, gts-79dw.4.11) -- the exact function `list_team_actions`
delegates to, with the exact same field projection (TEAM_ACTION_FIELDS) --
and proves invariant 6 (fail-closed) plus the wire-level param names/response
shape against the real `list_team_actions` route using the same
always-runnable garbage-token path test_verify_access.py already establishes
for the tier resolver (no real GIS access is needed to prove a token that
cannot verify yields tier=NONE and empty actions). `scope=mine`'s specific
wiring (resolved.email -> assigneeEmail, never a client-supplied field) is
verified by code inspection (src/TeamListing.js) plus the equivalent
assigneeEmail-composition behavior at the reader level (test 4 below) --
recorded here rather than silently assumed.

Ordering: regression coverage for an already-implemented route
(oracle-ordering-lever, gts-m65t) -- retroactive path, not red-green.
"""
import time

import pytest

from scn.session import ScenarioSession, _http_post

TEAM_ACTION_FIELDS = [
    "global_id", "action_id", "action_text", "assignee_email", "assignee_name",
    "status", "status_bucket", "status_resolved", "status_icon",
    "doc_id", "doc_name", "doc_url", "created_date", "modified_date",
]


def _read_team_actions(settings: dict, **kwargs) -> dict:
    payload = {"action": "read_team_actions", "testToken": settings.get("testToken") or ""}
    payload.update(kwargs)
    return _http_post(settings["webappTestUrl"], payload)


def _list_team_actions(settings: dict, **kwargs) -> dict:
    payload = {"action": "list_team_actions"}
    payload.update(kwargs)
    return _http_post(settings["webappTestUrl"], payload)


def _set_docdata(scn, **fields):
    return scn._post_fixture("set_docdata_row", fields)


def _seed_row(scn, **fields):
    return scn._post_fixture("seed_row", fields)


@pytest.fixture
def team_doc(settings, request):
    """A fresh, isolated journey doc (run-isolated clone, I8) with a unique
    teamId so this file's rows never collide with other tests' fixture data
    sharing the same Actions/DocData tabs."""
    scn = ScenarioSession.new_doc(settings, request=request)
    team_id = "TestListing-" + scn.doc_id[:12]
    _set_docdata(scn, fileId=scn.doc_id, teamId=team_id, docName="Team Listing Test Doc")
    try:
        yield scn, team_id
    finally:
        scn.close()


# ---------------------------------------------------------------------------
# Invariant 1 -- a stale OPEN action never ages out
# ---------------------------------------------------------------------------

def test_stale_open_action_never_ages_out(settings, team_doc):
    scn, team_id = team_doc
    global_id = f"{scn.doc_id}/AI-1"
    two_years_ago = "2024-01-01T00:00:00.000Z"
    _seed_row(scn, globalId=global_id, actionId=1, status="Open",
              actionText="Ancient open action", dateModified=two_years_ago)

    open_resp = _read_team_actions(settings, teamId=team_id, statusFilter="open", windowDays=1)
    open_ids = {r["global_id"] for r in open_resp["rows"]}
    assert global_id in open_ids, (
        f"[12.1 invariant 1] stale Open row must appear under statusFilter=open "
        f"regardless of windowDays, got rows={open_resp['rows']!r}"
    )

    all_resp = _read_team_actions(settings, teamId=team_id, statusFilter="all", windowDays=1)
    all_ids = {r["global_id"] for r in all_resp["rows"]}
    assert global_id in all_ids, (
        f"[12.1 invariant 1] stale Open row must appear under statusFilter=all with "
        f"windowDays=1 -- windowDays must have NO effect on unresolved rows, "
        f"got rows={all_resp['rows']!r}"
    )


# ---------------------------------------------------------------------------
# Invariant 2 -- closed/all age out resolved rows outside windowDays,
# boundary tested at the exact cutoff.
# ---------------------------------------------------------------------------

def test_closed_rows_age_out_at_the_window_boundary(settings, team_doc):
    scn, team_id = team_doc
    window_days = 5
    now = time.time()
    cutoff = now - window_days * 86400
    # Margin covers HTTP/client-vs-server clock jitter while still exercising
    # the boundary itself, not "some old date" -- see module docstring.
    # gts-ppfg: 8s was not enough -- this test issues 4 sequential HTTP round
    # trips (2 seeds + 2 reads) against a live GAS backend, and each
    # _readTeamActions call recomputes its cutoff from the *server's* Date.now()
    # at call time, not a value frozen at seed time. Real elapsed wall-clock
    # time between this test's client-side cutoff calculation and its second
    # (statusFilter='all') read call was observed eating the entire 8s margin
    # on its own (confirmed via GAS-side cutoffMs/modifiedMs logging), with no
    # actual off-by-something defect in the server's cutoff computation --
    # same documented clock-jitter hazard test_team_portal_hardening.py:214
    # already works around with a day-scale margin. 3600s (1h) stays
    # decisively inside the 5-day window on both sides while easily
    # outlasting observed multi-second round-trip jitter.
    margin = 3600
    inside_iso = _iso(cutoff + margin)   # just newer than the cutoff -> kept
    outside_iso = _iso(cutoff - margin)  # just older than the cutoff -> dropped

    inside_id = f"{scn.doc_id}/AI-1"
    outside_id = f"{scn.doc_id}/AI-2"
    _seed_row(scn, globalId=inside_id, actionId=1, status="Done",
              actionText="Just inside window", dateModified=inside_iso)
    _seed_row(scn, globalId=outside_id, actionId=2, status="Done",
              actionText="Just outside window", dateModified=outside_iso)

    for status_filter in ("closed", "all"):
        resp = _read_team_actions(settings, teamId=team_id, statusFilter=status_filter,
                                   windowDays=window_days)
        ids = {r["global_id"] for r in resp["rows"]}
        assert inside_id in ids, (
            f"[12.1 invariant 2] resolved row modified {margin}s inside the "
            f"windowDays={window_days} cutoff must be kept under statusFilter="
            f"{status_filter!r}, got rows={resp['rows']!r}"
        )
        assert outside_id not in ids, (
            f"[12.1 invariant 2] resolved row modified {margin}s outside the "
            f"windowDays={window_days} cutoff must be dropped under statusFilter="
            f"{status_filter!r}, got rows={resp['rows']!r}"
        )


def _iso(epoch_seconds: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# ---------------------------------------------------------------------------
# Invariant 3 -- off-vocabulary status still buckets via isResolved(), and is
# excluded from statusOptions.
# ---------------------------------------------------------------------------

def test_off_vocabulary_status_buckets_without_appearing_in_options(settings, team_doc):
    scn, team_id = team_doc
    global_id = f"{scn.doc_id}/AI-1"
    # 'Backlog' matches no _STATUS_SYNONYMS entry (SyncManager.js) -- a
    # genuinely off-vocabulary literal, unlike e.g. 'Escalated' which is
    # itself a Delegated synonym.
    _seed_row(scn, globalId=global_id, actionId=1, status="Backlog",
              actionText="Off-vocabulary status")

    resp = _read_team_actions(settings, teamId=team_id, statusFilter="all", windowDays=60)
    row = next((r for r in resp["rows"] if r["global_id"] == global_id), None)
    assert row is not None, f"[12.1 invariant 3] expected row present, got {resp['rows']!r}"
    assert row["status"] == "Backlog", f"row must carry the literal typed status, got {row!r}"
    assert row["status_bucket"] == "Other", (
        f"[12.1 invariant 3] off-vocabulary status must bucket to 'Other' via "
        f"getStatusDisplay(), got {row!r}"
    )
    assert row["status_resolved"] is False, (
        f"[12.1 invariant 3] 'Backlog' is not in isResolved()'s word list, must "
        f"resolve to status_resolved=False, got {row!r}"
    )

    option_statuses = {o["status"] for o in resp["statusOptions"]}
    assert "Backlog" not in option_statuses, (
        f"[12.1 invariant 3] an off-vocabulary status must not appear in the "
        f"canonical statusOptions picker list, got {resp['statusOptions']!r}"
    )

    # Also confirmed present (not silently dropped) under statusFilter=open,
    # since it is not resolved.
    open_resp = _read_team_actions(settings, teamId=team_id, statusFilter="open", windowDays=60)
    assert global_id in {r["global_id"] for r in open_resp["rows"]}, (
        "[12.1 invariant 3] unresolved off-vocabulary status must appear under "
        "statusFilter=open"
    )


# ---------------------------------------------------------------------------
# Invariant 4 -- scope=mine composes with statusFilter in ONE server query
# (proven at the shared reader _readTeamActions, which list_team_actions
# delegates to via a single call with assigneeEmail set from the verified
# caller's email -- src/TeamListing.js).
# ---------------------------------------------------------------------------

def test_assignee_scope_composes_with_status_filter_in_one_call(settings, team_doc):
    scn, team_id = team_doc
    mine_open_id = f"{scn.doc_id}/AI-1"
    mine_closed_id = f"{scn.doc_id}/AI-2"
    other_open_id = f"{scn.doc_id}/AI-3"

    _seed_row(scn, globalId=mine_open_id, actionId=1, status="Open",
              assigneeEmail="alice@example.org", actionText="Mine, open")
    _seed_row(scn, globalId=mine_closed_id, actionId=2, status="Done",
              assigneeEmail="alice@example.org", actionText="Mine, closed")
    _seed_row(scn, globalId=other_open_id, actionId=3, status="Open",
              assigneeEmail="bob@example.org", actionText="Not mine, open")

    resp = _read_team_actions(settings, teamId=team_id, statusFilter="open",
                               assigneeEmail="alice@example.org", windowDays=60)
    ids = {r["global_id"] for r in resp["rows"]}
    assert ids == {mine_open_id}, (
        f"[12.1 invariant 4] scope=mine (assigneeEmail) composed with "
        f"statusFilter=open in a single reader call must return exactly "
        f"alice's open row, got {resp['rows']!r}"
    )

    resp_all = _read_team_actions(settings, teamId=team_id, statusFilter="all",
                                   assigneeEmail="alice@example.org", windowDays=60)
    ids_all = {r["global_id"] for r in resp_all["rows"]}
    assert ids_all == {mine_open_id, mine_closed_id}, (
        f"[12.1 invariant 4] scope=mine composed with statusFilter=all must "
        f"return both of alice's rows and none of bob's, got {resp_all['rows']!r}"
    )


# ---------------------------------------------------------------------------
# Invariant 5 (R13b) -- dead source document excludes its rows under every
# filter.
# ---------------------------------------------------------------------------

def test_dead_source_document_excludes_its_rows(settings, team_doc):
    scn, team_id = team_doc
    global_id = f"{scn.doc_id}/AI-1"
    _seed_row(scn, globalId=global_id, actionId=1, status="Open",
              actionText="Row on a doc that is about to die")

    resp_alive = _read_team_actions(settings, teamId=team_id, statusFilter="all", windowDays=60)
    assert global_id in {r["global_id"] for r in resp_alive["rows"]}, (
        "sanity precondition: row must be visible before the source doc dies"
    )

    _set_docdata(scn, fileId=scn.doc_id, teamId=team_id, syncStatus="Deleted")

    for status_filter in ("open", "closed", "all"):
        resp = _read_team_actions(settings, teamId=team_id, statusFilter=status_filter, windowDays=60)
        assert global_id not in {r["global_id"] for r in resp["rows"]}, (
            f"[12.1 invariant 5 / R13b] a row whose source DocData.syncStatus is "
            f"'Deleted' must be excluded under statusFilter={status_filter!r}, "
            f"got rows={resp['rows']!r}"
        )


# ---------------------------------------------------------------------------
# Invariant 6 -- fail-closed: NONE tier (garbage/unverifiable token) returns
# no action data. Also exercises the real list_team_actions wire shape:
# param names (teamId, statusFilter, scope, windowDays) and response keys
# (tier, teamId, actions, statusOptions).
# ---------------------------------------------------------------------------

def test_none_tier_yields_no_action_data(settings):
    """No GasLogger content assertion here (see gts-pfyx): the shared Axiom
    dataset ('nuuts') is at its 257-column schema limit, so any log field not
    already in its schema -- including this route's own 'statusFilter'/'scope'
    -- is silently rejected by Axiom's ingest endpoint (HTTP 400, confirmed via
    `clasp logs`: GasLogger.log('webapp.team.list', {...}) fires correctly
    server-side every time, but the row never reaches Axiom). That makes
    tests/helpers/gas_log.py's assert_log() time out regardless of whether the
    tag/field logging is correct -- indistinguishable from a real regression.
    Manually confirmed via `clasp logs` immediately after a call with this
    exact payload: `{"tag":"webapp.team.list","data":{"sub":"","tier":"NONE",
    "statusFilter":"all","scope":"mine","count":0}}` -- log tag and field
    names match the pre-code contract exactly. gts-pfyx tracks fixing the
    Axiom pipe; once fixed, add the assert_log check back here."""
    resp = _list_team_actions(
        settings,
        assertion="not-a-real-jwt.garbage.token",
        teamId="TestTeamA",
        statusFilter="all",
        scope="mine",
        windowDays=9999,
    )
    assert resp.get("tier") == "NONE", f"[R6/R8] expected tier=NONE for an unverifiable token, got {resp!r}"
    assert resp.get("actions") == [], f"[12.1 invariant 6] NONE tier must yield no action data, got {resp!r}"
    assert resp.get("teamId") == "TestTeamA", f"response must echo the requested teamId, got {resp!r}"
    assert isinstance(resp.get("statusOptions"), list) and len(resp["statusOptions"]) > 0, (
        f"statusOptions must still be served (picker vocabulary is not itself "
        f"row data), got {resp!r}"
    )


def test_list_team_actions_response_shape_and_row_projection(settings, team_doc):
    """Confirms list_team_actions' row projection matches §12.1's frozen field
    list exactly -- proven via read_team_actions (identical TEAM_ACTION_FIELDS
    projection, no `fields` narrowing passed by either caller) since driving
    list_team_actions itself to a non-NONE tier requires a live GIS token
    unavailable in this environment (see module docstring)."""
    scn, team_id = team_doc
    global_id = f"{scn.doc_id}/AI-1"
    _seed_row(scn, globalId=global_id, actionId=1, status="Open", actionText="Shape check")

    resp = _read_team_actions(settings, teamId=team_id, statusFilter="all", windowDays=60)
    row = next(r for r in resp["rows"] if r["global_id"] == global_id)
    assert set(row.keys()) == set(TEAM_ACTION_FIELDS), (
        f"[12.1] row must carry exactly the frozen field list, got keys={sorted(row.keys())!r}"
    )
    for opt in resp["statusOptions"]:
        assert set(opt.keys()) == {"status", "icon", "alt"}, (
            f"statusOptions entries must be {{status, icon, alt}} (getStatusIconButtons()), got {opt!r}"
        )
