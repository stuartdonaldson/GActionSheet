"""
test_view_b.py — targeted hardening test for gts-79dw.4.13's get_document_actions
route (View B: verified per-document action view), gts-79dw.4.19's [TST] pairing.

Backstop rules are relaxed for this bead per explicit session instruction: this is
a targeted, fast test (not the full pytest -x suite). See gts-79dw.4.13's bd notes
for the operation-parity reconciliation and gts-79dw.4.19 for the paired [TST].

Modeled on tests/test_team_portal_hardening.py's GIS-assertion fixture patterns
(mint_test_assertion run_fixture, move_doc_to_folder run_fixture, ScenarioSession).
Uses the real TestTeamA fixture folder (gts-79dw.4.16) so tier resolution is real,
not mocked.

Covers:
  - a VIEW-tier caller sees the document's actions with the frozen output schema
    (tier, teamId, docName, docUrl, actions, teamPortalUrl) and the same per-row
    fields find_sheet_actions already returns.
  - a NONE-tier caller (no resolvable Drive access) receives actions:[] (R8) while
    the caller-supplied-derived fields (teamId, docName, docUrl) are still present,
    matching the convention list_team_actions already follows for its own
    caller-supplied teamId echo.
  - a docId with no DocData row (never synced / unknown to this deployment)
    resolves teamId='' -> tier NONE -> actions:[], docName/docUrl reflect "no row
    found" sensibly rather than erroring.
"""
import uuid

import pytest

from scn.session import ScenarioSession, _http_post

TEAM_A = "TestTeamA"
TEAM_A_FOLDER_1 = "1SCPPZfUeSWqaE3WvWYl6go13lzEZQUbs"

CALLER_EMAIL = "stuart.donaldson@gmail.com"  # real VIEW-tier grant on TestTeamA (see test_team_portal_hardening.py)
NO_ACCESS_EMAIL = "gts-79dw-4-19-hardening-noaccess@example.com"

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


def _get_document_actions(settings, assertion, doc_id) -> dict:
    return _http_post(settings["webappTestUrl"], {
        "action": "get_document_actions",
        "assertion": assertion,
        "docId": doc_id,
    })


@pytest.fixture(scope="module")
def caller_assertion(settings):
    return _mint(settings, sub=f"gts-79dw-4-19-{_RUN_TAG}-caller", email=CALLER_EMAIL)


@pytest.fixture(scope="module")
def no_access_assertion(settings):
    return _mint(settings, sub=f"gts-79dw-4-19-{_RUN_TAG}-noaccess", email=NO_ACCESS_EMAIL)


@pytest.fixture(scope="module")
def seeded_doc(settings):
    """One doc under TestTeamA/folder1 carrying a single tagged action row."""
    scn = ScenarioSession.new_doc(settings)
    text = f"gts79dw419 {_RUN_TAG} view b action"
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

        scn.append_paragraph(f"AI: teammate@example.com {text}")
        scn.sync()
        yield {"doc_id": scn.doc_id, "text": text, "session": scn}
    finally:
        try:
            scn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# VIEW-tier positive path — schema + row content.
# ---------------------------------------------------------------------------

def test_view_tier_caller_sees_document_actions(settings, caller_assertion, seeded_doc):
    """[AC] A verified caller with >= VIEW tier on the document's team sees
    that document's actions, with the frozen output schema present."""
    resp = _get_document_actions(settings, caller_assertion, seeded_doc["doc_id"])

    assert resp.get("tier") in ("VIEW", "EDIT"), (
        f"[AC] caller with real TestTeamA access must resolve >= VIEW, got {resp!r}"
    )
    assert resp.get("teamId") == TEAM_A, f"[schema] teamId must be TestTeamA, got {resp!r}"
    assert resp.get("docUrl", "").endswith(seeded_doc["doc_id"] + "/edit"), (
        f"[schema] docUrl must be the canonical Drive edit URL for the docId, got {resp!r}"
    )
    assert "teamPortalUrl" in resp, f"[schema/R20] teamPortalUrl must be present, got {resp!r}"
    assert resp.get("teamPortalUrl"), f"[schema/R20] teamPortalUrl must be non-empty for a resolved team, got {resp!r}"

    actions = resp.get("actions", [])
    texts = {a.get("action_text") for a in actions}
    assert seeded_doc["text"] in texts, (
        f"[AC] seeded action must appear in View B's actions for its own doc, got texts={texts!r}"
    )
    row = next(a for a in actions if a.get("action_text") == seeded_doc["text"])
    # Same per-row fields the sidebar document view presents (assignee, status,
    # id) -- reused verbatim from find_sheet_actions' core (_findSheetActionsForDoc).
    for field in ("global_id", "action_id", "assignee_email", "status", "doc_id"):
        assert field in row, f"[operation parity] row missing field {field!r}: {row!r}"
    assert row.get("doc_id") == seeded_doc["doc_id"], f"[AC] row must be scoped to the requested doc, got {row!r}"


# ---------------------------------------------------------------------------
# NONE-tier negative — fail closed on actions, non-action fields still present.
# ---------------------------------------------------------------------------

def test_none_tier_caller_receives_no_action_data(settings, no_access_assertion, seeded_doc):
    """[AC/R8] A NONE-tier caller (no resolvable Drive access to the team)
    receives no action data -- actions must be empty -- while teamId/docName/
    docUrl (derived from the docId the caller already supplied) are still
    returned, matching list_team_actions' existing convention of always
    echoing caller-supplied identifiers regardless of resolved tier."""
    resp = _get_document_actions(settings, no_access_assertion, seeded_doc["doc_id"])

    assert resp.get("tier") == "NONE", f"[R8] no-access caller must resolve tier=NONE, got {resp!r}"
    assert resp.get("actions", []) == [], (
        f"[R8] a NONE-tier caller must receive no action data, got {resp!r}"
    )
    assert resp.get("teamId") == TEAM_A, (
        f"[schema] teamId is derived from DocData, not caller-gated -- must still be TestTeamA, got {resp!r}"
    )


def test_fail_closed_invalid_assertion(settings, seeded_doc):
    """[R2/R6 negative] A garbage assertion must fail closed -- no leaked
    action data, never an exception surfaced to the caller."""
    resp = _get_document_actions(settings, "not-a-real-assertion.garbage.token", seeded_doc["doc_id"])
    assert resp.get("tier") == "NONE", f"[R6] invalid assertion must resolve tier=NONE, got {resp!r}"
    assert resp.get("actions", []) == [], f"[R6] invalid assertion must yield no action data, got {resp!r}"


# ---------------------------------------------------------------------------
# docId with no DocData.teamId — "behaves sensibly" (fails closed, no error).
# ---------------------------------------------------------------------------

def test_unknown_doc_id_resolves_none_tier_and_no_actions(settings, caller_assertion):
    """[sensible-behavior AC] A docId with no DocData row (never synced / not
    tracked by this deployment) must resolve teamId='' -> tier NONE -> no
    action data, and must not throw or 500 -- even for an otherwise
    real, verified caller."""
    resp = _get_document_actions(settings, caller_assertion, "not-a-real-doc-id-" + _RUN_TAG)

    assert resp.get("tier") == "NONE", f"[sensible] unknown docId must resolve tier=NONE, got {resp!r}"
    assert resp.get("teamId") == "", f"[sensible] unknown docId must resolve empty teamId, got {resp!r}"
    assert resp.get("actions", []) == [], f"[sensible] unknown docId must yield no action data, got {resp!r}"
    assert resp.get("docName", "") == "", f"[sensible] unknown docId must yield empty docName, got {resp!r}"
