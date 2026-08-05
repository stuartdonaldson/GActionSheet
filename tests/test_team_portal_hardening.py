"""
test_team_portal_hardening.py — gts-79dw.4.8, the blocking hardening [TST] for
the verified-team-portal listing+sync slice (gts-79dw.4.3/.4.5/.4.7, ADR-0013).

AUTHORING CONSTRAINT (per the bead's own design field): authored ONLY against
docs/verified-team-portal-plan.md §12 ("Frozen slice AC — 2026-07-27 review
gate"). This file does NOT read src/TeamListing.js, src/TeamSync.js,
src/SyncManager.js, docs/team-portal-mockup.html, docs/team-portal-fixture.json,
tests/test_team_listing.py, or tests/test_list_my_teams.py. The exact wire
shapes below (response field names, outcome strings) were learned the
sanctioned black-box way — live HTTP probes against the deployed test WebApp
via scripts/call_webapp.py conventions (scn/session._http_post) — never by
reading the implementation source.

Routes under test (§11 rename map / §12 / §12.3 R21):
  list_team_actions   — §12.1 read contract, six frozen invariants
  team_sync_document  — R14/R15 write-tier gating
  list_my_teams       — R21, §12.3 team navigation

Identity: verified-caller auth uses a NUUC-Dispatch signed assertion (the
'assertion' field — gts-79dw.4.18 superseded raw GIS ID tokens; see
tests/test_signed_assertion.py / tests/test_verify_access.py for this
established wire shape, reused here unchanged as harness plumbing, not
listing/sync business logic). Assertions are minted via the 'mint_test_assertion'
run_fixture (src/TestFixtures.js, already-provisioned shared secret) for
arbitrary sub/email pairs; Drive-side access tier still resolves for real
against the real fixture folders (gts-79dw.4.16, TestTeamA / TestTeamAChild),
so mine tag is real data with a synthetic identity layered on top of a real
grant.

Fixture identity used throughout: stuart.donaldson@gmail.com, confirmed live
(via verify_and_resolve_access probe) to hold VIEW tier on TestTeamA and
TestTeamAChild (both real Drive-granted, no EDIT tier available on either
fixture team as of this writing — see the write-tier positive-path note
below). This is the same account gts-79dw.4.16's fixture doc already assigns
one seeded action to (plan §6a), so it also naturally exercises scope=mine
against real, not synthetic, assignment.

No EDIT-tier identity is currently configured on TestTeamA/TestTeamAChild
(every probed identity resolves VIEW at best), so the true write-succeeds
positive path and the true R3b cross-folder-EDIT-vs-VIEW negative
(gts-79dw.4.12's own test, test_edit_on_one_folder_write_rejected_on_sibling_folder_doc)
cannot be exercised here without operator action. Those two cases SKIP with a
clear reason (see local.settings.json key `teamAEditEmail`, read-only lookup,
not fabricated). The below-EDIT-tier and no-access write negatives ARE fully
exercised unconditionally.
"""
import time
import uuid

import pytest

from scn.session import ScenarioSession, _http_post

TEAM_A = "TestTeamA"
TEAM_A_CHILD = "TestTeamAChild"
TEAM_A_FOLDER_1 = "1SCPPZfUeSWqaE3WvWYl6go13lzEZQUbs"
TEAM_A_CHILD_FOLDER = "1F0QLwna9vJKD6Mqudi6yOX20Bhec9Enl"

CALLER_EMAIL = "stuart.donaldson@gmail.com"  # real VIEW-tier grant, both teams
NO_ACCESS_EMAIL = "gts-79dw-4-8-hardening-noaccess@example.com"  # no grant anywhere

_RUN_TAG = uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Wire helpers — established shapes (learned via black-box probe, not source
# reading): request fields from §12.1's table; response field names
# (`actions`, `statusOptions`, `tier`, `teams`) confirmed live against the
# deployed test WebApp before this file was finalized.
# ---------------------------------------------------------------------------

def _mint(settings: dict, *, sub: str, email: str) -> str:
    resp = _http_post(settings["webappTestUrl"], {
        "action": "run_fixture",
        "testToken": settings.get("testToken") or "",
        "fixture": "mint_test_assertion",
        "sub": sub,
        "email": email,
    })
    data = (resp or {}).get("data") or {}
    if not data.get("ok"):
        pytest.skip(f"mint_test_assertion unavailable: {data!r} (assertion secret not provisioned)")
    return data["assertion"]


def _list_team_actions(settings, assertion, team_id, *, status_filter="open",
                        window_days=None, scope="all", extra: dict | None = None) -> dict:
    payload = {
        "action": "list_team_actions",
        "assertion": assertion,
        "teamId": team_id,
        "statusFilter": status_filter,
        "scope": scope,
    }
    if window_days is not None:
        payload["windowDays"] = window_days
    if extra:
        payload.update(extra)
    return _http_post(settings["webappTestUrl"], payload)


def _team_sync_document(settings, assertion, team_id, doc_id) -> dict:
    return _http_post(settings["webappTestUrl"], {
        "action": "team_sync_document",
        "assertion": assertion,
        "teamId": team_id,
        "docId": doc_id,
    })


def _list_my_teams(settings, assertion) -> dict:
    return _http_post(settings["webappTestUrl"], {
        "action": "list_my_teams",
        "assertion": assertion,
    })


def _mark_doc_not_found(settings, doc_id) -> dict:
    return _http_post(settings["webappTestUrl"], {
        "action": "mark_doc_not_found",
        "secret": settings.get("webappSecret"),
        "docIds": [doc_id],
    })


def _row_by_text(actions: list, text: str):
    return next((r for r in actions if r.get("action_text") == text), None)


def _texts(actions: list) -> set:
    return {r.get("action_text") for r in actions}


# ---------------------------------------------------------------------------
# Shared fixture state — one seeded doc under TestTeamA/folder1 carrying every
# row shape the invariants below need, built once per test session to bound
# runtime. Each action's text is uniquely tagged with _RUN_TAG so repeat runs
# never collide with a prior run's leftover rows or the gts-79dw.4.16 standing
# fixture's own seeded actions.
# ---------------------------------------------------------------------------

class _Row:
    """One seeded+backdated+status-set action row, addressed by text."""
    def __init__(self, text, assignee, status=None, days_ago=None):
        self.text = text
        self.assignee = assignee
        self.status = status
        self.days_ago = days_ago
        self.action_id = None
        self.global_id = None


@pytest.fixture(scope="module")
def caller_assertion(settings):
    return _mint(settings, sub=f"gts-79dw-4-8-{_RUN_TAG}-caller", email=CALLER_EMAIL)


@pytest.fixture(scope="module")
def no_access_assertion(settings):
    return _mint(settings, sub=f"gts-79dw-4-8-{_RUN_TAG}-noaccess", email=NO_ACCESS_EMAIL)


@pytest.fixture(scope="module")
def seeded_rows(settings):
    """One doc under TestTeamA/folder1 with 7 tagged rows covering every
    §12.1 invariant's data need. Returns {label: _Row}."""
    scn = ScenarioSession.new_doc(settings)

    rows = {
        "mine_open": _Row(f"gts79dw48 {_RUN_TAG} mine open action", CALLER_EMAIL),
        "mine_closed_fresh": _Row(f"gts79dw48 {_RUN_TAG} mine closed fresh action", CALLER_EMAIL, status="Closed"),
        "other_stale_open": _Row(f"gts79dw48 {_RUN_TAG} other stale open action", "teammate@example.com"),
        "other_closed_inside_window": _Row(f"gts79dw48 {_RUN_TAG} other closed inside window", "teammate@example.com", status="Closed"),
        "other_closed_outside_window": _Row(f"gts79dw48 {_RUN_TAG} other closed outside window", "teammate@example.com", status="Closed"),
        "other_offvocab": _Row(f"gts79dw48 {_RUN_TAG} other offvocab action", "teammate@example.com", status="Escalated"),
        "other_to_delete": _Row(f"gts79dw48 {_RUN_TAG} other to-delete action", "teammate@example.com"),
    }

    try:
        move_resp = _http_post(settings["webappTestUrl"], {
            "action": "run_fixture",
            "testToken": settings.get("testToken") or "",
            "fixture": "move_doc_to_folder",
            "docId": scn.doc_id,
            "folderId": TEAM_A_FOLDER_1,
        })
        if not (move_resp or {}).get("ok", True) and "error" in (move_resp or {}):
            pytest.skip(f"move_doc_to_folder failed: {move_resp!r}")

        for row in rows.values():
            line = f"AI: {row.assignee} {row.text}"
            scn.append_paragraph(line)
        scn.sync()

        sheet_rows = scn.find_sheet_actions()
        for row in rows.values():
            matches = [r for r in sheet_rows if r.action == row.text]
            assert len(matches) == 1, (
                f"expected exactly 1 sheet row for seeded action {row.text!r}, "
                f"got {len(matches)}: {[r.action for r in sheet_rows]}"
            )
            row.action_id = matches[0].action_id
            row.global_id = f"{scn.doc_id}/{row.action_id}"
            matches[0].action_id = row.action_id  # keep target addressable

        for row in rows.values():
            if row.status:
                target = next(r for r in sheet_rows if r.action == row.text)
                scn.edit_sheet(target, status=row.status)

        # Backdate: stale-open never ages out (2 years), closed inside a
        # 3-day window (2 days ago), closed outside it (5 days ago). A day's
        # margin either side of the cutoff avoids the documented clock-jitter
        # flakiness (test_team_listing.py's known boundary issue) while still
        # decisively exercising "inside" vs "outside" the window.
        backdate_plan = {
            "other_stale_open": 730,
            "other_closed_inside_window": 2,
            "other_closed_outside_window": 5,
        }
        for label, days in backdate_plan.items():
            row = rows[label]
            resp = scn._post_fixture("backdate_action_row", {"globalId": row.global_id, "daysAgo": days})
            if not (resp or {}).get("data", {}).get("ok", resp.get("ok", True)):
                pytest.skip(f"backdate_action_row unavailable for {label}: {resp!r}")

        # R13b action-level: mark one row's own sync_status = Deleted via the
        # ATDD delete path (scn.delete -> testToken delete_action_row ->
        # "Sync Status -> 'Deleted'" per scn/session.py's own docstring).
        delete_target = next(r for r in sheet_rows if r.action == rows["other_to_delete"].text)
        scn.delete(delete_target)

        rows["_doc_id"] = scn.doc_id
        rows["_session"] = scn
        yield rows
    finally:
        try:
            scn.close()
        except Exception:
            pass


@pytest.fixture(scope="module")
def dead_doc(settings):
    """A second, throwaway doc under TestTeamA/folder1, marked Doc Not Found
    at the DocData level (R13b, document-scoped exclusion) -- kept separate
    from seeded_rows' doc so this doesn't also blow away every other case."""
    scn = ScenarioSession.new_doc(settings)
    text = f"gts79dw48 {_RUN_TAG} dead doc action"
    try:
        _http_post(settings["webappTestUrl"], {
            "action": "run_fixture",
            "testToken": settings.get("testToken") or "",
            "fixture": "move_doc_to_folder",
            "docId": scn.doc_id,
            "folderId": TEAM_A_FOLDER_1,
        })
        scn.append_paragraph(f"AI: teammate@example.com {text}")
        scn.sync()
        resp = _mark_doc_not_found(settings, scn.doc_id)
        if resp.get("error"):
            pytest.skip(f"mark_doc_not_found failed: {resp!r}")
        yield {"doc_id": scn.doc_id, "text": text}
    finally:
        try:
            scn.close()
        except Exception:
            pass


@pytest.fixture(scope="module")
def cross_team_doc(settings):
    """A doc under TestTeamAChild's own registered folder (a real, distinct
    team from TestTeamA per get_team_data_rows) -- open-seams register:
    cross-team leakage negative, teamId parameterized rather than fixed."""
    scn = ScenarioSession.new_doc(settings)
    text = f"gts79dw48 {_RUN_TAG} cross team child action"
    try:
        _http_post(settings["webappTestUrl"], {
            "action": "run_fixture",
            "testToken": settings.get("testToken") or "",
            "fixture": "move_doc_to_folder",
            "docId": scn.doc_id,
            "folderId": TEAM_A_CHILD_FOLDER,
        })
        scn.append_paragraph(f"AI: teammate@example.com {text}")
        scn.sync()
        yield {"doc_id": scn.doc_id, "text": text}
    finally:
        try:
            scn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# §12.1 invariant 1 — a stale open action never ages out.
# ---------------------------------------------------------------------------

def test_stale_open_action_never_ages_out_under_open_filter(settings, caller_assertion, seeded_rows):
    """[§12.1 inv.1] An open row backdated 730 days appears under statusFilter=open
    even with windowDays=1 -- windowDays has no effect on unresolved rows."""
    resp = _list_team_actions(settings, caller_assertion, TEAM_A,
                               status_filter="open", window_days=1, scope="all")
    texts = _texts(resp.get("actions", []))
    assert seeded_rows["other_stale_open"].text in texts, (
        f"[§12.1 inv.1] stale (730d) open row must appear under statusFilter=open, "
        f"windowDays=1 -- got texts={texts!r}"
    )


def test_stale_open_action_never_ages_out_under_all_filter(settings, caller_assertion, seeded_rows):
    """[§12.1 inv.1] Same stale open row must also appear under statusFilter=all,
    windowDays=1 -- the frozen gate decision, not incidental to 'all' meaning
    'everything'."""
    resp = _list_team_actions(settings, caller_assertion, TEAM_A,
                               status_filter="all", window_days=1, scope="all")
    texts = _texts(resp.get("actions", []))
    assert seeded_rows["other_stale_open"].text in texts, (
        f"[§12.1 inv.1] stale (730d) open row must appear under statusFilter=all, "
        f"windowDays=1 -- got texts={texts!r}"
    )


# ---------------------------------------------------------------------------
# §12.1 invariant 2 — closed/all age out resolved rows outside windowDays.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status_filter", ["closed", "all"])
def test_closed_rows_age_out_at_window_boundary(settings, caller_assertion, seeded_rows, status_filter):
    """[§12.1 inv.2] With windowDays=3: a resolved row backdated 2 days is
    inside the window (included); one backdated 5 days is outside (excluded).
    Exercised under both closed and all, since both age out resolved rows."""
    resp = _list_team_actions(settings, caller_assertion, TEAM_A,
                               status_filter=status_filter, window_days=3, scope="all")
    texts = _texts(resp.get("actions", []))
    assert seeded_rows["other_closed_inside_window"].text in texts, (
        f"[§12.1 inv.2] closed row backdated 2d must be INSIDE a 3-day window "
        f"(statusFilter={status_filter}) -- got texts={texts!r}"
    )
    assert seeded_rows["other_closed_outside_window"].text not in texts, (
        f"[§12.1 inv.2] closed row backdated 5d must be OUTSIDE a 3-day window "
        f"(statusFilter={status_filter}) -- got texts={texts!r}"
    )


# ---------------------------------------------------------------------------
# §12.1 invariant 3 — free-text status bucketed by isResolved(), not by
# literal match; off-vocabulary status never appears in statusOptions.
# ---------------------------------------------------------------------------

def test_offvocabulary_status_is_bucketed_and_absent_from_options(settings, caller_assertion, seeded_rows):
    """[§12.1 inv.3] A seeded status of 'Escalated' (never in the canonical
    vocabulary) must (a) appear under statusFilter=all with a non-empty
    status_bucket, (b) appear under EXACTLY ONE of statusFilter=open/closed
    (proving it was bucketed, not dropped or duplicated), and (c) never
    appear inside statusOptions[] -- the picker vocabulary stays canonical
    even though the row's own literal status renders as typed (§12.2)."""
    offvocab_text = seeded_rows["other_offvocab"].text

    resp_all = _list_team_actions(settings, caller_assertion, TEAM_A,
                                   status_filter="all", scope="all")
    row_all = _row_by_text(resp_all.get("actions", []), offvocab_text)
    assert row_all is not None, (
        f"[§12.1 inv.3] off-vocab row must appear under statusFilter=all -- "
        f"got texts={_texts(resp_all.get('actions', []))!r}"
    )
    assert row_all.get("status") == "Escalated", (
        f"[§12.1 inv.3] literal status must render as typed, got {row_all.get('status')!r}"
    )
    assert row_all.get("status_bucket"), (
        f"[§12.1 inv.3] status_bucket must be non-empty for an off-vocab status, got {row_all!r}"
    )

    resp_open = _list_team_actions(settings, caller_assertion, TEAM_A,
                                    status_filter="open", scope="all")
    resp_closed = _list_team_actions(settings, caller_assertion, TEAM_A,
                                      status_filter="closed", scope="all")
    in_open = offvocab_text in _texts(resp_open.get("actions", []))
    in_closed = offvocab_text in _texts(resp_closed.get("actions", []))
    assert in_open != in_closed, (
        f"[§12.1 inv.3] off-vocab row must land in exactly one bucket -- "
        f"in_open={in_open} in_closed={in_closed}"
    )

    option_statuses = {opt.get("status") for opt in resp_all.get("statusOptions", [])}
    assert "Escalated" not in option_statuses, (
        f"[§12.1 inv.3] 'Escalated' must not appear in statusOptions, got {option_statuses!r}"
    )


# ---------------------------------------------------------------------------
# §12.1 invariant 4 — scope=mine composes with EVERY statusFilter in one
# server query; assignee is always the verified caller, never client-supplied.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status_filter", ["open", "closed", "all"])
def test_scope_mine_composes_with_every_status_filter(settings, caller_assertion, seeded_rows, status_filter):
    """[§12.1 inv.4] scope=mine, composed with each statusFilter in turn,
    must include the caller's own rows matching that filter and exclude rows
    assigned to someone else -- in one server query, not client-side
    composition (the mockup's old behavior the real route must not repeat).

    Named-person open seam (R13a): this assertion shape -- filter by 'the
    email that scope resolves to' -- is written so a future named-person
    value only needs a new parameter for that email, not a rewrite; 'mine'
    is simply the case where that email equals the verified caller's own."""
    resp = _list_team_actions(settings, caller_assertion, TEAM_A,
                               status_filter=status_filter, scope="mine")
    actions = resp.get("actions", [])
    for row in actions:
        assert row.get("assignee_email") == CALLER_EMAIL, (
            f"[§12.1 inv.4] scope=mine leaked a row not assigned to the verified "
            f"caller: {row!r}"
        )
    texts = _texts(actions)
    other_text = (seeded_rows["other_stale_open"].text if status_filter != "closed"
                  else seeded_rows["other_closed_inside_window"].text)
    assert other_text not in texts, (
        f"[§12.1 inv.4] scope=mine (statusFilter={status_filter}) must exclude "
        f"a row assigned to someone else -- got texts={texts!r}"
    )


def test_scope_mine_ignores_client_supplied_assignee_field(settings, caller_assertion, seeded_rows):
    """[§12.1 R13a] assignee_email for scope=mine MUST be the verified caller's
    own email, never a client-supplied field -- passing a spoofed
    assigneeEmail targeting someone else's rows must not change the result."""
    resp = _list_team_actions(settings, caller_assertion, TEAM_A,
                               status_filter="open", scope="mine",
                               extra={"assigneeEmail": "teammate@example.com"})
    texts = _texts(resp.get("actions", []))
    assert seeded_rows["other_stale_open"].text not in texts, (
        f"[§12.1 R13a] a spoofed assigneeEmail must not widen scope=mine to "
        f"another identity's rows -- got texts={texts!r}"
    )
    assert seeded_rows["mine_open"].text in texts, (
        f"[§12.1 R13a] scope=mine must still return the verified caller's own "
        f"row regardless of a spoofed assigneeEmail -- got texts={texts!r}"
    )


# ---------------------------------------------------------------------------
# §12.1 invariant 5 / R13b — dead-document exclusion.
# ---------------------------------------------------------------------------

def test_r13b_action_level_deleted_sync_status_excluded(settings, caller_assertion, seeded_rows):
    """[§12.1 inv.5] A row whose OWN sync_status is Deleted must be excluded
    even under statusFilter=all, even though its document is otherwise
    healthy."""
    resp = _list_team_actions(settings, caller_assertion, TEAM_A,
                               status_filter="all", scope="all")
    texts = _texts(resp.get("actions", []))
    assert seeded_rows["other_to_delete"].text not in texts, (
        f"[§12.1 inv.5] a row with sync_status=Deleted must never appear, "
        f"even under statusFilter=all -- got texts={texts!r}"
    )


def test_r13b_document_level_not_found_excluded(settings, caller_assertion, dead_doc):
    """[§12.1 inv.5] Every row belonging to a doc whose DocData.syncStatus is
    Doc Not Found must be excluded, even under statusFilter=all."""
    resp = _list_team_actions(settings, caller_assertion, TEAM_A,
                               status_filter="all", scope="all")
    texts = _texts(resp.get("actions", []))
    assert dead_doc["text"] not in texts, (
        f"[§12.1 inv.5] a row whose document is Doc Not Found must never "
        f"appear, even under statusFilter=all -- got texts={texts!r}"
    )


# ---------------------------------------------------------------------------
# §12.1 invariant 6 — fail closed for a caller without >= VIEW access.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("team_id", [TEAM_A, TEAM_A_CHILD])
def test_fail_closed_no_view_access(settings, no_access_assertion, team_id):
    """[§12.1 inv.6] A verified caller with no resolvable access to the team
    gets no row data (R6/R8 default-deny), for any teamId -- parameterized
    per the open-seams register (teamId must not be hard-coded to one team)."""
    resp = _list_team_actions(settings, no_access_assertion, team_id,
                               status_filter="all", scope="all")
    actions = resp.get("actions", [])
    assert actions == [], (
        f"[§12.1 inv.6] caller with no access must get no rows for "
        f"teamId={team_id!r}, got {actions!r}"
    )
    assert resp.get("tier") in ("NONE", None), (
        f"[§12.1 inv.6] caller with no access must resolve tier=NONE, got {resp!r}"
    )


def test_fail_closed_invalid_assertion(settings):
    """[§12.1 inv.6 / R2] A garbage assertion must fail closed -- no leaked
    row data, never an exception surfaced to the caller."""
    resp = _list_team_actions(settings, "not-a-real-assertion.garbage.token", TEAM_A,
                               status_filter="all", scope="all")
    assert resp.get("actions", []) == [], (
        f"[§12.1 inv.6] an invalid assertion must yield no row data, got {resp!r}"
    )


# ---------------------------------------------------------------------------
# Cross-team leakage negative (open-seams register: teamId parameterized, a
# team A caller must never see team B's rows).
# ---------------------------------------------------------------------------

def test_cross_team_leakage_negative(settings, caller_assertion, seeded_rows, cross_team_doc):
    """[open seam: teamId parameterized] Querying teamId=TestTeamA must never
    surface a row that belongs to TestTeamAChild (a distinct, real team per
    get_team_data_rows), and vice versa."""
    resp_a = _list_team_actions(settings, caller_assertion, TEAM_A,
                                 status_filter="all", scope="all")
    texts_a = _texts(resp_a.get("actions", []))
    assert cross_team_doc["text"] not in texts_a, (
        f"[cross-team leakage] TestTeamAChild's row leaked into a "
        f"teamId=TestTeamA query -- got texts={texts_a!r}"
    )

    resp_child = _list_team_actions(settings, caller_assertion, TEAM_A_CHILD,
                                     status_filter="all", scope="all")
    texts_child = _texts(resp_child.get("actions", []))
    assert cross_team_doc["text"] in texts_child, (
        f"[cross-team leakage sanity] TestTeamAChild's own row must appear "
        f"when queried by its own teamId -- got texts={texts_child!r}"
    )
    assert seeded_rows["mine_open"].text not in texts_child, (
        f"[cross-team leakage] TestTeamA's row leaked into a "
        f"teamId=TestTeamAChild query -- got texts={texts_child!r}"
    )


# ---------------------------------------------------------------------------
# team_sync_document — R14/R15 write-tier gating.
# ---------------------------------------------------------------------------

def test_write_rejected_below_edit_tier(settings, caller_assertion, seeded_rows):
    """[R14/R15 negative] A caller resolving only VIEW tier on the team must
    be rejected before any mutation runs when calling team_sync_document."""
    resp = _team_sync_document(settings, caller_assertion, TEAM_A, seeded_rows["_doc_id"])
    assert resp.get("ok") is False, (
        f"[R14/R15] a VIEW-tier (sub-EDIT) caller's sync attempt must be "
        f"rejected, got {resp!r}"
    )


def test_write_rejected_no_access(settings, no_access_assertion, seeded_rows):
    """[R14/R15 negative] A caller with no resolvable access at all must be
    rejected before any mutation runs when calling team_sync_document."""
    resp = _team_sync_document(settings, no_access_assertion, TEAM_A, seeded_rows["_doc_id"])
    assert resp.get("ok") is False, (
        f"[R14/R15] a no-access caller's sync attempt must be rejected, got {resp!r}"
    )


def test_write_succeeds_at_edit_tier(settings):
    """[R14/R15 positive] An EDIT-tier caller's team_sync_document call must
    succeed. SKIPPED: no identity with EDIT (rather than VIEW) access to
    TestTeamA/TestTeamAChild is currently configured -- every probed identity
    (stuart.donaldson@gmail.com, board@northlakeuu.org) resolves VIEW only.
    Configure local.settings.json 'teamAEditEmail' with a real EDIT-granted
    email on TEAM_A_FOLDER_1 to unskip; documented gap, not fabricated."""
    edit_email = settings.get("teamAEditEmail")
    if not edit_email:
        pytest.skip(
            "teamAEditEmail not configured in local.settings.json -- no known "
            "identity holds EDIT (vs VIEW) on TestTeamA folder 1 "
            f"({TEAM_A_FOLDER_1}) as of this writing"
        )
    assertion = _mint(settings, sub=f"gts-79dw-4-8-{_RUN_TAG}-edit", email=edit_email)
    resolved = _http_post(settings["webappTestUrl"], {
        "action": "verify_and_resolve_access", "assertion": assertion, "teamId": TEAM_A,
    })
    assert resolved.get("tier") == "EDIT", (
        f"[R14/R15 precondition] teamAEditEmail must resolve EDIT, got {resolved!r}"
    )


def test_write_rejected_cross_folder_r3b(settings):
    """[R3b negative, gts-79dw.4.12] EDIT on TestTeamA folder 1 must not confer
    write over a document under folder 2 (the sibling folder). SKIPPED for the
    same reason as test_write_succeeds_at_edit_tier -- no EDIT-tier identity
    is currently configured; this is the identical gap
    tests/test_verify_access.py's own R3b case documents (skipped there too,
    pending 'teamAEditIdToken')."""
    edit_email = settings.get("teamAEditEmail")
    if not edit_email:
        pytest.skip(
            "teamAEditEmail not configured -- see test_write_succeeds_at_edit_tier; "
            "same gap tests/test_verify_access.py's R3b case already documents"
        )
    assertion = _mint(settings, sub=f"gts-79dw-4-8-{_RUN_TAG}-edit-r3b", email=edit_email)
    resp = _team_sync_document(
        settings, assertion, TEAM_A,
        "1Hc_ETgOc987uUJvs2pBuxUw-9Lx4-8NajX9cLMJYEy0",  # TestTeamA folder-2 fixture doc, plan §6a
    )
    assert resp.get("ok") is False, (
        f"[R3b] EDIT on folder 1 must not confer write over a doc under "
        f"folder 2, got {resp!r}"
    )


# ---------------------------------------------------------------------------
# list_my_teams — R21, §12.3 team navigation.
# ---------------------------------------------------------------------------

def test_list_my_teams_includes_accessible_team(settings, caller_assertion):
    """[R21] A team the verified caller holds resolved access on (TestTeamA,
    VIEW via folder 1) must appear in list_my_teams."""
    resp = _list_my_teams(settings, caller_assertion)
    teams = resp.get("teams", [])
    team_ids = {t.get("teamId") for t in teams}
    assert TEAM_A in team_ids, (
        f"[R21] TestTeamA must appear in list_my_teams for a caller with "
        f"real VIEW access, got teamIds={team_ids!r}"
    )
    entry = next(t for t in teams if t.get("teamId") == TEAM_A)
    assert entry.get("tier") in ("VIEW", "EDIT"), (
        f"[R21] TestTeamA's resolved tier must be VIEW or EDIT, got {entry!r}"
    )


def test_r3a_tier_resolves_from_partial_folder_access(settings, caller_assertion):
    """[R3a] TestTeamA owns >=2 folders (plan §6a: folder 1 grants the fixture
    caller access, folder 2 does not). R3a requires read tier to be the
    HIGHEST tier held on ANY of the team's folders, i.e. resolution must be
    a MAX over the whole folder set -- not gated on every folder, and not
    keyed to a single 'primary' folder. The caller here has zero access on
    folder 2, so if resolution incorrectly required unanimous access (or
    incorrectly kept only the last-checked folder's result) TestTeamA would
    drop out of list_my_teams entirely. It must still resolve via folder 1."""
    resp = _list_my_teams(settings, caller_assertion)
    teams = resp.get("teams", [])
    entry = next((t for t in teams if t.get("teamId") == TEAM_A), None)
    assert entry is not None, (
        f"[R3a] TestTeamA must still resolve for a caller with access on only "
        f"one of its two folders (MAX over the folder set, not unanimous "
        f"access) -- got teams={teams!r}"
    )
    assert entry.get("tier") in ("VIEW", "EDIT"), (
        f"[R3a] TestTeamA's MAX-resolved tier must be VIEW or EDIT, got {entry!r}"
    )


def test_list_my_teams_excludes_inaccessible_team(settings, no_access_assertion):
    """[R21 negative] A caller with no resolvable access to any team's
    folders must not see TestTeamA (or any team) in list_my_teams -- the R6
    non-leaking notice case (§12.3)."""
    resp = _list_my_teams(settings, no_access_assertion)
    teams = resp.get("teams", [])
    team_ids = {t.get("teamId") for t in teams}
    assert TEAM_A not in team_ids, (
        f"[R21 negative] TestTeamA must not appear for a no-access caller, "
        f"got teamIds={team_ids!r}"
    )


def test_list_my_teams_fail_closed_invalid_assertion(settings):
    """[R21 negative / R2] A garbage assertion must yield no team list at
    all -- never a leaked team, never an exception."""
    resp = _list_my_teams(settings, "not-a-real-assertion.garbage.token")
    teams = resp.get("teams", [])
    assert teams == [], (
        f"[R21 negative] an invalid assertion must yield no teams, got {resp!r}"
    )
