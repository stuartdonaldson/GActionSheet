"""
test_team_write_routes.py — targeted test for gts-79dw.4.14's team_edit_action
/ team_patch_status routes (verified-team-portal edit + status-change, R16-R18).

Backstop rules are relaxed for this bead per explicit session instruction: this
is a targeted, fast test (not the full pytest -x suite). Full-suite regression
and exhaustive hardening are gts-79dw.4.15's job (blocking twin [TST], frozen-
contract-only, no shared context with this implementation) -- this file only
covers a reasonable slice: positive edit-tier gating check, positive
status-change-by-assignee, and negatives for a VIEW-tier non-assignee and a
NONE-tier caller on both routes.

Modeled on tests/test_team_portal_hardening.py's and tests/test_view_b.py's
GIS-assertion fixture patterns (mint_test_assertion run_fixture,
move_doc_to_folder run_fixture, ScenarioSession + find_sheet_actions() for
durable-state assertions).

No EDIT-tier identity is currently configured on TestTeamA (see
test_team_portal_hardening.py's documented gap / local.settings.json key
'teamAEditEmail') -- the true "EDIT-tier caller successfully edits" positive
path is SKIPPED with a clear reason, same as that file's precedent, not
fabricated. The VIEW-tier and NONE-tier edit REJECTIONS are fully exercised
unconditionally with real Drive-resolved tiers, as is the R17 assignee status
positive path (assignee bypass needs only VIEW tier, which IS configured).
"""
import uuid

import pytest

from scn.session import ScenarioSession, _http_post

TEAM_A = "TestTeamA"
TEAM_A_FOLDER_1 = "1SCPPZfUeSWqaE3WvWYl6go13lzEZQUbs"

CALLER_EMAIL = "stuart.donaldson@gmail.com"  # real VIEW-tier grant on TestTeamA
NO_ACCESS_EMAIL = "gts-79dw-4-14-hardening-noaccess@example.com"
OTHER_ASSIGNEE_EMAIL = "gts-79dw-4-14-other-assignee@example.com"

_RUN_TAG = uuid.uuid4().hex[:8]


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


def _team_edit_action(settings, assertion, team_id, global_id, fields) -> dict:
    return _http_post(settings["webappTestUrl"], {
        "action": "team_edit_action",
        "assertion": assertion,
        "teamId": team_id,
        "global_id": global_id,
        "fields": fields,
    })


def _team_patch_status(settings, assertion, team_id, global_id, status) -> dict:
    return _http_post(settings["webappTestUrl"], {
        "action": "team_patch_status",
        "assertion": assertion,
        "teamId": team_id,
        "global_id": global_id,
        "status": status,
    })


@pytest.fixture(scope="module")
def caller_assertion(settings):
    return _mint(settings, sub=f"gts-79dw-4-14-{_RUN_TAG}-caller", email=CALLER_EMAIL)


@pytest.fixture(scope="module")
def no_access_assertion(settings):
    return _mint(settings, sub=f"gts-79dw-4-14-{_RUN_TAG}-noaccess", email=NO_ACCESS_EMAIL)


@pytest.fixture(scope="module")
def seeded_rows(settings):
    """One doc under TestTeamA/folder1 with two tagged rows: one assigned to
    the real VIEW-tier caller (R17 assignee-bypass target), one assigned to
    someone else (VIEW-tier-non-assignee negative target)."""
    scn = ScenarioSession.new_doc(settings)

    mine_text = f"gts79dw414 {_RUN_TAG} mine assigned action"
    other_text = f"gts79dw414 {_RUN_TAG} other assigned action"

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
        scn.append_paragraph(f"AI: {OTHER_ASSIGNEE_EMAIL} {other_text}")
        scn.sync()

        sheet_rows = scn.find_sheet_actions()
        mine_matches = [r for r in sheet_rows if r.action == mine_text]
        other_matches = [r for r in sheet_rows if r.action == other_text]
        assert len(mine_matches) == 1, f"expected 1 seeded 'mine' row, got {mine_matches!r}"
        assert len(other_matches) == 1, f"expected 1 seeded 'other' row, got {other_matches!r}"

        mine_global_id = mine_matches[0].global_id
        other_global_id = other_matches[0].global_id

        yield {
            "session": scn,
            "doc_id": scn.doc_id,
            "mine_global_id": mine_global_id,
            "mine_text": mine_text,
            "other_global_id": other_global_id,
            "other_text": other_text,
        }
    finally:
        try:
            scn.close()
        except Exception:
            pass


def _row_state(seeded_rows, global_id):
    """Fresh durable-state read (not the mutation route's own response)."""
    rows = seeded_rows["session"].find_sheet_actions()
    for r in rows:
        if r.global_id == global_id:
            return r
    return None


# ---------------------------------------------------------------------------
# team_edit_action
# ---------------------------------------------------------------------------

def test_view_tier_caller_edit_rejected_before_mutation(settings, caller_assertion, seeded_rows):
    """[AC negative] A VIEW-tier (sub-EDIT) caller's team_edit_action call must
    be rejected before any mutation runs; durable row state must be unchanged."""
    resp = _team_edit_action(
        settings, caller_assertion, TEAM_A, seeded_rows["mine_global_id"],
        {"action_text": f"{seeded_rows['mine_text']} TAMPERED"},
    )
    assert resp.get("ok") is False, f"[R16] VIEW-tier caller edit must be rejected, got {resp!r}"
    assert resp.get("global_id") == seeded_rows["mine_global_id"], f"[schema] {resp!r}"
    assert resp.get("outcome", "").startswith("rejected"), f"[schema] {resp!r}"

    row = _row_state(seeded_rows, seeded_rows["mine_global_id"])
    assert row is not None, "seeded row must still exist"
    assert row.action == seeded_rows["mine_text"], (
        f"[durable-state negative] row must be UNCHANGED after a rejected edit, got {row.action!r}"
    )


def test_none_tier_caller_edit_rejected(settings, no_access_assertion, seeded_rows):
    """[AC] A NONE-tier caller must be rejected before any mutation runs."""
    resp = _team_edit_action(
        settings, no_access_assertion, TEAM_A, seeded_rows["mine_global_id"],
        {"action_text": f"{seeded_rows['mine_text']} TAMPERED-BY-NONE"},
    )
    assert resp.get("ok") is False, f"[R16] NONE-tier caller edit must be rejected, got {resp!r}"

    row = _row_state(seeded_rows, seeded_rows["mine_global_id"])
    assert row is not None
    assert row.action == seeded_rows["mine_text"], (
        f"[durable-state negative] row must be UNCHANGED after a rejected edit, got {row.action!r}"
    )


def test_write_succeeds_at_edit_tier(settings, seeded_rows):
    """[AC positive] An EDIT-tier caller's team_edit_action call must succeed,
    stamping Dirty + Date Modified exactly as the existing edit_action_row path
    does. SKIPPED: no identity with EDIT (rather than VIEW) access to TestTeamA
    is currently configured -- see test_team_portal_hardening.py's identical,
    documented gap (local.settings.json key 'teamAEditEmail'). Not fabricated."""
    edit_email = settings.get("teamAEditEmail")
    if not edit_email:
        pytest.skip(
            "teamAEditEmail not configured in local.settings.json -- no known "
            "identity holds EDIT (vs VIEW) on TestTeamA folder 1 "
            f"({TEAM_A_FOLDER_1}) as of this writing"
        )
    assertion = _mint(settings, sub=f"gts-79dw-4-14-{_RUN_TAG}-edit", email=edit_email)
    new_text = f"{seeded_rows['mine_text']} EDITED-BY-EDIT-TIER"
    resp = _team_edit_action(
        settings, assertion, TEAM_A, seeded_rows["mine_global_id"], {"action_text": new_text},
    )
    assert resp.get("ok") is True, f"[R16 positive] EDIT-tier caller edit must succeed, got {resp!r}"
    assert resp.get("outcome") == "ok", f"[schema] {resp!r}"

    row = _row_state(seeded_rows, seeded_rows["mine_global_id"])
    assert row is not None
    assert row.action == new_text, f"[durable-state AC] row must reflect the edit, got {row.action!r}"
    assert row.sync_status == "Dirty", (
        f"[AC] edit must stamp Sync Status='Dirty' exactly as edit_action_row does, got {row.sync_status!r}"
    )


# ---------------------------------------------------------------------------
# team_patch_status
# ---------------------------------------------------------------------------

def test_assignee_can_change_status_with_view_tier_only(settings, caller_assertion, seeded_rows):
    """[AC/R17 positive] The action's ASSIGNEE (CALLER_EMAIL) changes its
    status with only VIEW tier on the folder -- must succeed."""
    resp = _team_patch_status(
        settings, caller_assertion, TEAM_A, seeded_rows["mine_global_id"], "Closed",
    )
    assert resp.get("ok") is True, f"[R17] assignee status change must succeed at VIEW tier, got {resp!r}"
    assert resp.get("outcome") == "ok", f"[schema] {resp!r}"

    row = _row_state(seeded_rows, seeded_rows["mine_global_id"])
    assert row is not None
    assert row.status == "Closed", f"[durable-state AC] status must be updated, got {row.status!r}"


def test_view_tier_non_assignee_status_rejected(settings, caller_assertion, seeded_rows):
    """[AC negative] A VIEW-tier caller who is NOT the row's assignee must be
    rejected before any mutation runs; durable row state must be unchanged."""
    resp = _team_patch_status(
        settings, caller_assertion, TEAM_A, seeded_rows["other_global_id"], "Closed",
    )
    assert resp.get("ok") is False, (
        f"[R17 negative] VIEW-tier non-assignee status change must be rejected, got {resp!r}"
    )

    row = _row_state(seeded_rows, seeded_rows["other_global_id"])
    assert row is not None
    assert row.status != "Closed", (
        f"[durable-state negative] row must be UNCHANGED after a rejected status change, got {row.status!r}"
    )


def test_none_tier_status_rejected(settings, no_access_assertion, seeded_rows):
    """[AC] A NONE-tier caller must be rejected before any mutation runs."""
    resp = _team_patch_status(
        settings, no_access_assertion, TEAM_A, seeded_rows["other_global_id"], "Closed",
    )
    assert resp.get("ok") is False, f"[R17] NONE-tier caller status change must be rejected, got {resp!r}"

    row = _row_state(seeded_rows, seeded_rows["other_global_id"])
    assert row is not None
    assert row.status != "Closed", (
        f"[durable-state negative] row must be UNCHANGED after a rejected status change, got {row.status!r}"
    )
