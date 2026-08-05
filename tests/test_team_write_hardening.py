"""
test_team_write_hardening.py — gts-79dw.4.15, the blocking hardening [TST] for
the verified-identity write routes built in gts-79dw.4.14 (ADR-0013 twin-ticket
rule, entry-point coverage invariant T17).

AUTHORING CONSTRAINT (per the bead's own design field): authored ONLY against
docs/verified-team-portal-plan.md §12 ("Frozen slice AC — 2026-07-27 review
gate") plus gts-79dw.4.15's own bd description (which spells out the write
routes' wire shape, since §12 itself only froze the read contract). This file
does NOT read src/TeamActionWrite.js or the diff to src/WebApp.js for the
write routes, and does not read tests/test_team_write_routes.py (gts-79dw.4.14's
own targeted test — a sibling deliverable, not a reference; no-shared-context
twin-ticket rule). tests/test_team_portal_hardening.py (gts-79dw.4.8, the
sibling *read*-path hardening test) IS used for fixture/assertion pattern
reference, as explicitly sanctioned by the bead.

The exact wire shapes below (response field names, outcome strings like
'rejected-doc-scope'/'ok', and which of the two routes is tier-gated vs.
assignee-gated) were learned the sanctioned black-box way -- live HTTP probes
against the deployed test WebApp via scn/session._http_post conventions --
never by reading implementation source. In particular:

  - team_patch_status is ASSIGNEE-gated: a VIEW-tier caller who IS the row's
    verified assignee can change its status; a VIEW-tier caller who is NOT
    the assignee is rejected. This matches §12.2's presentation rule ("the
    assignee status control ... offered only on rows whose assignee_email
    matches the verified caller").
  - team_edit_action is EDIT-TIER-gated: a VIEW-tier caller is rejected even
    on their own assigned row. This matches §12.2's presentation rule ("the
    Edit affordance renders only at EDIT tier").

Both were confirmed live before this file was finalized, then reverted to a
clean state (each probe used a disposable journey doc, closed after).

Routes under test (gts-79dw.4.15 bd description):
  team_edit_action    -- body {assertion, teamId, global_id, fields}
  team_patch_status   -- body {assertion, teamId, global_id, status}
  both respond {ok, global_id, outcome}

Identity: verified-caller auth uses a NUUC-Dispatch signed assertion (the
'assertion' field, gts-79dw.4.18), minted via the 'mint_test_assertion'
run_fixture for arbitrary sub/email pairs -- Drive-side access tier still
resolves for real against the real fixture folders (gts-79dw.4.16, TestTeamA).

Fixture identity: stuart.donaldson@gmail.com resolves VIEW tier (never EDIT)
on TestTeamA's folders as of this writing -- the same documented gap
tests/test_team_portal_hardening.py already records (local.settings.json key
'teamAEditEmail', unset). This file's assignee-gated team_patch_status
positive/idempotency/off-vocab coverage does NOT need EDIT tier (assignee
match at VIEW tier is sufficient and is itself the invariant under test), so
those run unconditionally. team_edit_action's true "write succeeds" positive
path and the R3b cross-folder negative (which requires an EDIT-tier identity
on TestTeamA folder 1) SKIP for the same documented gap -- see
test_edit_action_succeeds_at_edit_tier and test_r3b_cross_folder_edit_rejected
for how to unskip.
"""
import uuid

import pytest

from scn.session import ScenarioSession, _http_post

TEAM_A = "TestTeamA"
TEAM_A_FOLDER_1 = "1SCPPZfUeSWqaE3WvWYl6go13lzEZQUbs"
TEAM_A_FOLDER_2 = "1plip6j718V77_y2y_X6oritx8Th-8VqX"
TEAM_A_FOLDER_2_DOC = "1Hc_ETgOc987uUJvs2pBuxUw-9Lx4-8NajX9cLMJYEy0"  # plan §6a

CALLER_EMAIL = "stuart.donaldson@gmail.com"  # real VIEW-tier grant on TestTeamA
OTHER_EMAIL = "teammate@example.com"  # never a real caller identity in this file
NO_ACCESS_EMAIL = "gts-79dw-4-15-hardening-noaccess@example.com"

_RUN_TAG = uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Wire helpers
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


def _team_edit_action(settings, assertion, team_id, global_id, fields, extra: dict | None = None) -> dict:
    payload = {
        "action": "team_edit_action",
        "assertion": assertion,
        "teamId": team_id,
        "global_id": global_id,
        "fields": fields,
    }
    if extra:
        payload.update(extra)
    return _http_post(settings["webappTestUrl"], payload)


def _team_patch_status(settings, assertion, team_id, global_id, status, extra: dict | None = None) -> dict:
    payload = {
        "action": "team_patch_status",
        "assertion": assertion,
        "teamId": team_id,
        "global_id": global_id,
        "status": status,
    }
    if extra:
        payload.update(extra)
    return _http_post(settings["webappTestUrl"], payload)


def _list_team_actions(settings, assertion, team_id, *, status_filter="all", scope="all") -> dict:
    return _http_post(settings["webappTestUrl"], {
        "action": "list_team_actions",
        "assertion": assertion,
        "teamId": team_id,
        "statusFilter": status_filter,
        "scope": scope,
    })


def _row_by_text(rows, text):
    return next((r for r in rows if r.action == text), None)


def _list_row_by_global_id(settings, assertion, team_id, global_id):
    resp = _list_team_actions(settings, assertion, team_id)
    return next((r for r in resp.get("actions", []) if r.get("global_id") == global_id), None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def caller_assertion(settings):
    return _mint(settings, sub=f"gts-79dw-4-15-{_RUN_TAG}-caller", email=CALLER_EMAIL)


@pytest.fixture(scope="module")
def no_access_assertion(settings):
    return _mint(settings, sub=f"gts-79dw-4-15-{_RUN_TAG}-noaccess", email=NO_ACCESS_EMAIL)


@pytest.fixture(scope="module")
def seeded_doc(settings):
    """One doc under TestTeamA/folder1 with two rows: one assigned to the
    verified caller (mine), one assigned to someone else (other) -- covers
    every negative/positive pairing team_edit_action/team_patch_status need
    without requiring an EDIT-tier identity."""
    scn = ScenarioSession.new_doc(settings)
    mine_text = f"gts79dw415 {_RUN_TAG} mine action"
    other_text = f"gts79dw415 {_RUN_TAG} other action"
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

        scn.append_paragraph(f"AI: {CALLER_EMAIL} {mine_text}")
        scn.append_paragraph(f"AI: {OTHER_EMAIL} {other_text}")
        scn.sync()

        rows = scn.find_sheet_actions()
        mine = _row_by_text(rows, mine_text)
        other = _row_by_text(rows, other_text)
        assert mine is not None and other is not None, (
            f"expected both seeded rows, got {[r.action for r in rows]!r}"
        )

        yield {
            "session": scn,
            "doc_id": scn.doc_id,
            "mine_text": mine_text,
            "mine_global_id": mine.global_id,
            "other_text": other_text,
            "other_global_id": other.global_id,
        }
    finally:
        try:
            scn.close()
        except Exception:
            pass


def _fresh_row(state, *, which):
    """Re-fetch the current durable state of a seeded row via find_sheet_actions."""
    rows = state["session"].find_sheet_actions()
    text = state["mine_text"] if which == "mine" else state["other_text"]
    row = _row_by_text(rows, text)
    assert row is not None, f"expected seeded row {text!r} still present, got {[r.action for r in rows]!r}"
    return row


# ---------------------------------------------------------------------------
# team_patch_status -- assignee-gated positive path (call-site + durable
# state), idempotency, and the off-vocabulary-status open seam.
# ---------------------------------------------------------------------------

def test_patch_status_assignee_at_view_tier_succeeds_durable(settings, caller_assertion, seeded_doc):
    """[call-site, durable state] The verified caller, who IS the assignee of
    'mine', changes its status via team_patch_status. VIEW tier is sufficient
    because authorization here is assignee-match, not team tier (§12.2:
    assignee status control offered only on rows whose assignee_email matches
    the verified caller)."""
    before = _fresh_row(seeded_doc, which="mine")
    assert before.status != "Closed"

    resp = _team_patch_status(settings, caller_assertion, TEAM_A,
                               seeded_doc["mine_global_id"], "Closed")
    assert resp.get("ok") is True, f"assignee at VIEW tier must be able to change their own row's status, got {resp!r}"
    assert resp.get("global_id") == seeded_doc["mine_global_id"]

    after = _fresh_row(seeded_doc, which="mine")
    assert after.status == "Closed", (
        f"durable sheet state must reflect the status change -- got status={after.status!r}"
    )


def test_patch_status_idempotent_repeat_does_not_double_apply(settings, caller_assertion, seeded_doc):
    """[Idempotency] Repeating a status change to the SAME value converges:
    both calls succeed, and the durable row settles on exactly ONE row at
    that global_id carrying that status -- not duplicated, not reverted, not
    errored on the repeat. (Probed live: this route re-stamps modified_date
    on every accepted call regardless of whether the value actually changed,
    so modified_date is not a usable no-op proxy here -- unlike
    edit_action_row/patch_action_status's Dirty+Date-Modified behavior
    referenced in §11; convergence is asserted on the row's own state and
    identity instead.)"""
    resp1 = _team_patch_status(settings, caller_assertion, TEAM_A,
                                seeded_doc["mine_global_id"], "InProgress")
    assert resp1.get("ok") is True, f"first status change must succeed, got {resp1!r}"
    after1 = _fresh_row(seeded_doc, which="mine")
    assert after1.status == "InProgress"

    resp2 = _team_patch_status(settings, caller_assertion, TEAM_A,
                                seeded_doc["mine_global_id"], "InProgress")
    assert resp2.get("ok") is True, f"repeating the same status must converge (ok), got {resp2!r}"
    assert resp2.get("global_id") == resp1.get("global_id") == seeded_doc["mine_global_id"]

    rows_after = seeded_doc["session"].find_sheet_actions()
    matches = [r for r in rows_after if r.global_id == seeded_doc["mine_global_id"]]
    assert len(matches) == 1, (
        f"[idempotency] repeating a status change to the same value must not "
        f"create a duplicate row -- expected exactly 1 row at "
        f"global_id={seeded_doc['mine_global_id']!r}, got {len(matches)}: "
        f"{[(r.global_id, r.status) for r in rows_after]!r}"
    )
    assert matches[0].status == "InProgress", (
        f"[idempotency] the row must settle on the repeated value, got "
        f"{matches[0].status!r}"
    )


def test_patch_status_offvocab_free_text_round_trips_and_display_authority_agrees(
    settings, caller_assertion, seeded_doc
):
    """[Open seam: free-text status first-class] An off-vocabulary status
    literal ('Escalated') round-trips into a bucket via isResolved(), not
    only canonical values -- and the display fields returned by the read
    route (status_bucket/status_resolved/status_icon) after this write agree
    with what the sheet itself now holds. These display fields are read via
    list_team_actions (the established read-route helper), not a hand-rolled
    parallel implementation of getStatusDisplay()."""
    resp = _team_patch_status(settings, caller_assertion, TEAM_A,
                               seeded_doc["mine_global_id"], "Escalated")
    assert resp.get("ok") is True, f"an off-vocabulary status literal must be accepted, got {resp!r}"

    after = _fresh_row(seeded_doc, which="mine")
    assert after.status == "Escalated", (
        f"durable sheet state must carry the literal typed status, got {after.status!r}"
    )

    row = _list_row_by_global_id(settings, caller_assertion, TEAM_A, seeded_doc["mine_global_id"])
    assert row is not None, "seeded row must still be visible via list_team_actions after the write"
    assert row.get("status") == "Escalated", (
        f"[status display authority] list_team_actions must render the literal "
        f"typed status, got {row.get('status')!r}"
    )
    assert row.get("status_bucket"), (
        f"[status display authority] an off-vocab status must still resolve a "
        f"non-empty status_bucket via isResolved(), got {row!r}"
    )
    assert row.get("status_resolved") is True, (
        f"[status display authority] 'Escalated' must resolve as a closed/"
        f"resolved bucket via isResolved(), got {row!r}"
    )
    assert row.get("status_icon"), (
        f"[status display authority] status_icon must be populated (inherited "
        f"from getStatusDisplay(), not invented), got {row!r}"
    )


# ---------------------------------------------------------------------------
# Negatives -- every one asserts durable state is UNCHANGED, not merely that
# the response said no.
# ---------------------------------------------------------------------------

def test_patch_status_view_tier_non_assignee_rejected_durable_unchanged(
    settings, caller_assertion, seeded_doc
):
    """[Negative] The verified caller (VIEW tier) is NOT the assignee of
    'other' -- team_patch_status must reject, and the row's status must be
    unchanged."""
    before = _fresh_row(seeded_doc, which="other")
    resp = _team_patch_status(settings, caller_assertion, TEAM_A,
                               seeded_doc["other_global_id"], "Closed")
    assert resp.get("ok") is False, (
        f"a VIEW-tier non-assignee caller's status change must be rejected, got {resp!r}"
    )
    after = _fresh_row(seeded_doc, which="other")
    assert after.status == before.status, (
        f"[durable state] rejected status change must leave the row unchanged -- "
        f"before={before.status!r} after={after.status!r}"
    )


def test_edit_action_view_tier_rejected_durable_unchanged(settings, caller_assertion, seeded_doc):
    """[Negative] team_edit_action requires EDIT tier (§12.2: 'the Edit
    affordance renders only at EDIT tier'). The verified caller resolves only
    VIEW on TestTeamA, so even editing their OWN assigned row ('mine') must
    be rejected, and the row's text must be unchanged."""
    before = _fresh_row(seeded_doc, which="mine")
    resp = _team_edit_action(settings, caller_assertion, TEAM_A,
                              seeded_doc["mine_global_id"], {"action_text": "hacked via edit"})
    assert resp.get("ok") is False, (
        f"a VIEW-tier caller's team_edit_action call must be rejected regardless "
        f"of assignee-match, got {resp!r}"
    )
    after = _fresh_row(seeded_doc, which="mine")
    assert after.action == before.action, (
        f"[durable state] rejected edit must leave the row's action_text "
        f"unchanged -- before={before.action!r} after={after.action!r}"
    )


def test_none_tier_rejected_on_both_write_routes_durable_unchanged(
    settings, no_access_assertion, seeded_doc
):
    """[Negative] A caller with NO resolvable access to the team (NONE tier)
    must be rejected on both team_edit_action and team_patch_status, and the
    target row must be unchanged on both counts."""
    before = _fresh_row(seeded_doc, which="mine")

    resp_status = _team_patch_status(settings, no_access_assertion, TEAM_A,
                                      seeded_doc["mine_global_id"], "Closed")
    assert resp_status.get("ok") is False, (
        f"a NONE-tier caller's team_patch_status call must be rejected, got {resp_status!r}"
    )

    resp_edit = _team_edit_action(settings, no_access_assertion, TEAM_A,
                                   seeded_doc["mine_global_id"], {"action_text": "hacked via edit"})
    assert resp_edit.get("ok") is False, (
        f"a NONE-tier caller's team_edit_action call must be rejected, got {resp_edit!r}"
    )

    after = _fresh_row(seeded_doc, which="mine")
    assert after.status == before.status and after.action == before.action, (
        f"[durable state] a NONE-tier caller's rejected writes must leave the "
        f"row completely unchanged -- before=({before.status!r},{before.action!r}) "
        f"after=({after.status!r},{after.action!r})"
    )


def test_patch_status_assignee_match_ignores_client_supplied_assignee_field(
    settings, caller_assertion, seeded_doc
):
    """[Assignee-match is server-verified, not client-supplied] The verified
    caller is NOT the assignee of 'other'. Adding a spoofed assignee-shaped
    field to the request body (claiming to BE the assignee) must not widen
    authorization -- the server must derive identity solely from the signed
    assertion, never from any request body field. Durable state must stay
    unchanged."""
    before = _fresh_row(seeded_doc, which="other")
    resp = _team_patch_status(
        settings, caller_assertion, TEAM_A, seeded_doc["other_global_id"], "Closed",
        extra={"assigneeEmail": OTHER_EMAIL, "assignee": OTHER_EMAIL},
    )
    assert resp.get("ok") is False, (
        f"a spoofed assignee-shaped field must not grant authorization the "
        f"verified assertion email doesn't already have, got {resp!r}"
    )
    after = _fresh_row(seeded_doc, which="other")
    assert after.status == before.status, (
        f"[durable state] a spoofed-assignee write attempt must leave the row "
        f"unchanged -- before={before.status!r} after={after.status!r}"
    )


# ---------------------------------------------------------------------------
# R3b -- EDIT tier on folder 1 must not confer write over a doc under folder 2
# of the same multi-folder team (the single-folder assumption's old gap,
# gts-79dw.4.16's fixture). Both SKIP for the same documented reason
# tests/test_team_portal_hardening.py's R3b case does: no identity currently
# resolves EDIT (only VIEW) on TestTeamA's folders.
#
# Non-vacuousness of this assertion (required by the AC) is established by
# REASONING, not a live stub/revert cycle, per the ticket's explicit "or"
# option -- see this file's closing bd note for the full argument, summarized
# here: docs/verified-team-portal-plan.md §11 already documents that
# assertTeamAccess (pre-fix) `break`s at the FIRST TeamData row matching a
# teamId, so a multi-folder team was authorized against an arbitrary one of
# its folders. Under that exact (real, historical) defect, a caller holding
# EDIT on folder 1 would resolve team-level EDIT and this call would be
# authorized to write TEAM_A_FOLDER_2_DOC purely because doc's folder is
# never separately checked -- flipping resp.get("ok") from the asserted
# False to True and failing this test. The assertion is therefore a real
# regression catch for a documented historical bug pattern, not a tautology.
# ---------------------------------------------------------------------------

def test_r3b_cross_folder_edit_rejected(settings):
    """[R3b negative] EDIT on TestTeamA folder 1 must not confer write over a
    document under folder 2 via team_edit_action."""
    edit_email = settings.get("teamAEditEmail")
    if not edit_email:
        pytest.skip(
            "teamAEditEmail not configured in local.settings.json -- no known "
            f"identity holds EDIT (vs VIEW) on TestTeamA folder 1 ({TEAM_A_FOLDER_1}) "
            "as of this writing; same documented gap as "
            "tests/test_team_portal_hardening.py's R3b case"
        )
    assertion = _mint(settings, sub=f"gts-79dw-4-15-{_RUN_TAG}-edit-r3b", email=edit_email)
    resolved = _http_post(settings["webappTestUrl"], {
        "action": "verify_and_resolve_access", "assertion": assertion, "teamId": TEAM_A,
    })
    assert resolved.get("tier") == "EDIT", (
        f"[R3b precondition] teamAEditEmail must resolve EDIT on TestTeamA, got {resolved!r}"
    )
    resp = _team_edit_action(settings, assertion, TEAM_A,
                              f"{TEAM_A_FOLDER_2_DOC}/AI-1", {"action_text": "r3b hacked"})
    assert resp.get("ok") is False, (
        f"[R3b] EDIT on folder 1 must not confer team_edit_action write over a "
        f"doc under folder 2, got {resp!r}"
    )


def test_r3b_cross_folder_patch_status_rejected(settings):
    """[R3b negative] EDIT on TestTeamA folder 1 must not confer write over a
    document under folder 2 via team_patch_status either -- even though
    team_patch_status is normally assignee-gated (not tier-gated), the
    per-document re-authorization must still hold for any caller who is not
    also the row's verified assignee."""
    edit_email = settings.get("teamAEditEmail")
    if not edit_email:
        pytest.skip(
            "teamAEditEmail not configured -- see test_r3b_cross_folder_edit_rejected"
        )
    assertion = _mint(settings, sub=f"gts-79dw-4-15-{_RUN_TAG}-status-r3b", email=edit_email)
    resp = _team_patch_status(settings, assertion, TEAM_A,
                               f"{TEAM_A_FOLDER_2_DOC}/AI-1", "Closed")
    assert resp.get("ok") is False, (
        f"[R3b] EDIT on folder 1 must not confer team_patch_status write over "
        f"a doc under folder 2, got {resp!r}"
    )


def test_edit_action_succeeds_at_edit_tier(settings):
    """[Positive, EDIT tier, durable state] An EDIT-tier caller's
    team_edit_action call must succeed and the row's text must durably
    change. SKIPPED: no identity with EDIT (rather than VIEW) access to
    TestTeamA is currently configured -- same documented gap as
    tests/test_team_portal_hardening.py's test_write_succeeds_at_edit_tier.
    Configure local.settings.json 'teamAEditEmail' to unskip."""
    edit_email = settings.get("teamAEditEmail")
    if not edit_email:
        pytest.skip(
            "teamAEditEmail not configured in local.settings.json -- no known "
            f"identity holds EDIT (vs VIEW) on TestTeamA folder 1 ({TEAM_A_FOLDER_1}) "
            "as of this writing"
        )
    assertion = _mint(settings, sub=f"gts-79dw-4-15-{_RUN_TAG}-edit-pos", email=edit_email)
    resolved = _http_post(settings["webappTestUrl"], {
        "action": "verify_and_resolve_access", "assertion": assertion, "teamId": TEAM_A,
    })
    assert resolved.get("tier") == "EDIT", (
        f"[precondition] teamAEditEmail must resolve EDIT, got {resolved!r}"
    )

    scn = ScenarioSession.new_doc(settings)
    try:
        _http_post(settings["webappTestUrl"], {
            "action": "run_fixture", "testToken": settings.get("testToken") or "",
            "fixture": "move_doc_to_folder", "docId": scn.doc_id, "folderId": TEAM_A_FOLDER_1,
        })
        text = f"gts79dw415 {_RUN_TAG} edit-tier-positive action"
        scn.append_paragraph(f"AI: {edit_email} {text}")
        scn.sync()
        rows = scn.find_sheet_actions()
        row = _row_by_text(rows, text)
        assert row is not None, f"expected seeded row, got {[r.action for r in rows]!r}"

        new_text = f"{text} EDITED"
        resp = _team_edit_action(settings, assertion, TEAM_A, row.global_id, {"action_text": new_text})
        assert resp.get("ok") is True, (
            f"[R14-R18 positive] an EDIT-tier caller's team_edit_action must "
            f"succeed, got {resp!r}"
        )

        rows_after = scn.find_sheet_actions()
        edited = next((r for r in rows_after if r.action == new_text), None)
        assert edited is not None, (
            f"[durable state] the row's action_text must durably change to "
            f"{new_text!r}, got {[r.action for r in rows_after]!r}"
        )
    finally:
        try:
            scn.close()
        except Exception:
            pass
