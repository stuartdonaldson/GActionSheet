"""
test_admin_doc_scan.py — Twin TST for gts-lgpx ([IMP] Resumable admin
doc-scan: Script-Property progress + self-rescheduling trigger).

Pre-code / frozen contract, gts-lgpx design field (frozen 2026-09-01):

  Four state-modifying entry points (all must appear as CALL-SITES, per the
  CLAUDE.md entry-point coverage invariant — testing only the internal
  pass-advance helper they delegate to is not sufficient):

  1. doPost action 'admin_scan_start'  { assertion|testToken+email, teamId }
     -> clears prior state, seeds folderStack, schedules one-shot, returns
     immediately. Response: { ok:true, status:'waiting', teamId,
     scanned:0, total:null }
  2. doPost action 'admin_scan_status' { assertion|testToken+email, teamId }
     -> READ-ONLY. Response: { ok:true, teamId, phase, status, scanned,
     total, matched, candidates:[{docId,docName,url}], updatedAt,
     complete:bool, error }
  3. doPost action 'admin_scan_resume' { assertion|testToken+email, teamId }
     -> reschedules the one-shot for an existing incomplete/stale scan.
     Refuses (ok:false, reason:'no_scan_in_progress') when there is none.
  4. Trigger handler function 'resumeAdminDocScan' (global, GAS-callable)
     -> deletes its own trigger, advances one bounded pass, reschedules if
     incomplete. Must be safe to run with no scan pending (no-op).

  STATE (single Script Property 'ADMIN_DOC_SCAN_STATE', JSON):
  { teamId, phase: 'enumerate'|'match'|'done',
    status: 'running'|'waiting'|'done'|'error',
    startedAt, updatedAt, total, scanned, matched,
    folderStack: [folderId], cursor: int,
    queueChunks: int, candidateChunks: int, error: string|null }

  RUNNING vs WAITING: a trigger pass sets status:'running' and heartbeats
  updatedAt; on exit, if incomplete, sets status:'waiting' and schedules the
  next one-shot. status:'running' with updatedAt older than 7 minutes is
  STALE and must be resumable.

  AUTHORIZATION (unchanged from gts-gwyg): _resolveScanIdentity +
  _isAdminUser (Config!AdminUsers) gate EVERY route, including
  admin_scan_status. Denied responses stay { ok:false, reason:'forbidden' }
  with no partial data. Uses `reason`, never a top-level `error` key
  (scn/session.py's _http_post raises FixtureError on any top-level `error`
  key — gts-gwyg contract note, unchanged).

  Test-support fixture routes (gts-lgpx, src/TestFixtures.js), both via the
  normal run_fixture / _post_fixture path:
  - admin_scan_pass: invokes resumeAdminDocScan() directly (real trigger
    handler call-site). Returns { state: <persisted state blob or null> }.
  - admin_scan_set_state: {clear:true} wipes all scan properties.
    {patch:{...}} shallow-merges into persisted state, returns
    { state, triggers: <count of pending resumeAdminDocScan triggers> }.
    A patch containing updatedAt is written verbatim (manufactures the stale
    case without a genuinely crashed execution). Called with neither, it is
    a pure read.

  gts-vsjv (shipped in this same build): quick-match accepts AI-/AI-N: as
  well as ACT-/ACT-N:. Covered here by ai_numbered_untracked /
  ai_plain_untracked.

No-shared-context (twin-ticket rule): authored against the frozen contract
in gts-lgpx's description ONLY — src/AdminDocScan.js, the admin_scan_*
routing block in src/WebApp.js, and src/TeamListing.js were not read while
writing these assertions.

Fixture reuse (I12): setup_team_scope_fixture, set_config_row(append=True)
for the AdminUsers identity, move_doc_to_folder, set_docdata_row, the
_make_doc helper and the module-scoped session pattern using request= (so
cleanup runs through new_doc's own finalizer, gts-hroj) are all carried
forward unchanged from the retired single-shot version of this file. Every
_post_fixture call in this module (admin_scan_pass / admin_scan_set_state)
is issued through one function-scoped `driver` session per test (see the
`driver` fixture below) rather than a fresh ScenarioSession.new_doc() per
call — those routes ignore the doc entirely (docAlreadyClosed:true), so
minting a new real Google Doc for each one would only add Drive-quota cost
and, without request=..., leak untracked docs (gts-hroj).

Ordering: specifiable oracle (candidate docIds and scanned/total counts are
precomputable from fixture setup) -- test-first (red before green) per
CLAUDE.md's oracle-ordering rule.
"""
import uuid

import pytest

from scn.session import ScenarioSession, _http_post


def _admin(settings: dict, action: str, **kwargs) -> dict:
    payload = {"action": action, "testToken": settings.get("testToken") or ""}
    payload.update(kwargs)
    return _http_post(settings["webappTestUrl"], payload)


def _end_index(scn: ScenarioSession) -> int:
    resp = scn._post_route("dump_doc_paragraphs", {"docId": scn.doc_id})
    elements = resp["elements"]
    return elements[-1]["end"] - 1


def _seed_text(scn: ScenarioSession, text: str) -> None:
    start = _end_index(scn)
    resp = scn._post_route("seed_doc_content", {
        "docId": scn.doc_id,
        "requests": [{"insertText": {"location": {"index": start}, "text": text}}],
    })
    assert resp.get("ok"), resp


@pytest.fixture(scope="module")
def team_folders(settings, request):
    """Idempotent TestTeamScopeA hierarchy (setup_team_scope_fixture,
    src/TestFixtures.js) -- reused rather than inventing a new one (I12).
    Uses request=... so the journey doc is trashed via new_doc's own
    pytest-finalizer path (gts-hroj), never this fixture's own cleanup."""
    scn = ScenarioSession.new_doc(settings, request=request)
    resp = scn._post_fixture("setup_team_scope_fixture")
    return resp["data"]


@pytest.fixture(scope="module")
def admin_email(settings, request, team_folders):
    """A unique admin identity for this test module, appended onto the
    Config sheet's AdminUsers row (append:true) so it never clobbers a real
    admin email a human seeded there manually, and doesn't collide with
    other test modules' runs."""
    email = f"gts-m4cq-admin-{uuid.uuid4().hex[:8]}@example.test"
    scn = ScenarioSession.new_doc(settings, request=request)
    scn._post_fixture("set_config_row", {"key": "AdminUsers", "value": email, "append": True})
    return email


def _make_doc(settings, request, *, folder_id: str, text: str | None, tracked: bool) -> ScenarioSession:
    """Creates a fresh journey doc, optionally seeds marker text, moves it
    into folder_id, and optionally registers it in DocData (tracked).
    Trashing is deferred to new_doc's own pytest finalizer (gts-hroj)."""
    scn = ScenarioSession.new_doc(settings, request=request)
    if text:
        _seed_text(scn, text)
    scn._post_fixture("move_doc_to_folder", {"folderId": folder_id})
    if tracked:
        scn._post_fixture("set_docdata_row", {
            "fileId": scn.doc_id, "docName": "tracked-" + scn.doc_id,
            "teamId": "TestTeamScopeA", "syncStatus": "Synced",
        })
    return scn


@pytest.fixture(scope="module")
def scan_docs(settings, request, team_folders):
    """The candidate set for the positive scan case, plus negative controls:
    untracked+action (ACT and AI spellings, numbered and bare), a
    no-action doc, an already-tracked doc, and a doc outside every
    registered team folder. Each is its own ScenarioSession so cleanup
    (trash) is independent and none share Actions/DocData rows."""
    team_a = team_folders["testTeamA"]
    no_team = team_folders["testTeamNoTeam"]
    sessions = {
        "act1_untracked":        _make_doc(settings, request, folder_id=team_a, text="ACT-1: Untracked action one", tracked=False),
        "act_plain_untracked":   _make_doc(settings, request, folder_id=team_a, text="ACT: Untracked action two", tracked=False),
        "ai_numbered_untracked": _make_doc(settings, request, folder_id=team_a, text="AI-7: Legacy untracked action", tracked=False),
        "ai_plain_untracked":    _make_doc(settings, request, folder_id=team_a, text="AI: Legacy bare untracked action", tracked=False),
        "no_action_untracked":   _make_doc(settings, request, folder_id=team_a, text="Just some ordinary paragraph text.", tracked=False),
        "act_tracked":           _make_doc(settings, request, folder_id=team_a, text="ACT: Already tracked action", tracked=True),
        "act_outside_team":      _make_doc(settings, request, folder_id=no_team, text="ACT: Outside any team folder", tracked=False),
    }
    return {name: scn.doc_id for name, scn in sessions.items()}


def _expected_candidate_ids(scan_docs: dict) -> set:
    return {
        scan_docs["act1_untracked"],
        scan_docs["act_plain_untracked"],
        scan_docs["ai_numbered_untracked"],
        scan_docs["ai_plain_untracked"],
    }


def _drive_scan_to_completion(driver: ScenarioSession, team_id: str, *, max_passes: int = 20) -> dict:
    """Repeatedly invoke the real trigger-handler call-site (admin_scan_pass)
    on the given driver session until the persisted state reports
    phase:'done', or raise if it doesn't converge -- this suite must never
    sleep for the real ~60s-out trigger."""
    state = None
    for _ in range(max_passes):
        resp = driver._post_fixture("admin_scan_pass")
        state = resp["data"]["state"]
        if state and state.get("phase") == "done":
            return state
    raise AssertionError(f"scan for teamId={team_id} did not complete within {max_passes} passes: {state}")


@pytest.fixture()
def driver(settings, request):
    """One real ScenarioSession per test, trashed via new_doc's own
    pytest-finalizer (gts-hroj) -- reused across every admin_scan_pass /
    admin_scan_set_state call the test makes, since those routes ignore the
    doc entirely."""
    return ScenarioSession.new_doc(settings, request=request)


@pytest.fixture()
def fresh_scan_state(driver):
    """Wipe all scan Script Properties before a test that needs a clean
    precondition (module-scoped fixtures share the underlying properties
    across tests, so each state-sensitive test clears first)."""
    driver._post_fixture("admin_scan_set_state", {"clear": True})
    return driver


# ---------------------------------------------------------------------------
# AC 1 + AC 2: durable-state assertion, start returns fast, one bounded pass
# ---------------------------------------------------------------------------

def test_scan_start_persists_progress_read_via_status(settings, admin_email, scan_docs, fresh_scan_state):
    """[AC 1] Starting a scan, then advancing exactly one bounded pass via
    the real trigger-handler call-site, persists progress that is read back
    through admin_scan_status -- not merely inferred from admin_scan_start's
    own response body."""
    start_resp = _admin(settings, "admin_scan_start", email=admin_email, teamId="TestTeamScopeA")
    assert start_resp.get("ok") is True, start_resp
    assert start_resp.get("status") == "waiting", start_resp
    assert start_resp.get("teamId") == "TestTeamScopeA", start_resp
    assert start_resp.get("scanned") == 0, start_resp

    pass_resp = fresh_scan_state._post_fixture("admin_scan_pass")
    persisted = pass_resp["data"]["state"]
    assert persisted is not None, pass_resp
    assert persisted.get("teamId") == "TestTeamScopeA", persisted

    status_resp = _admin(settings, "admin_scan_status", email=admin_email, teamId="TestTeamScopeA")
    assert status_resp.get("ok") is True, status_resp
    assert status_resp.get("teamId") == "TestTeamScopeA", status_resp
    # Durable-state assertion: status's scanned/phase match what admin_scan_pass
    # just persisted, read back through an independent route.
    assert status_resp.get("scanned") == persisted.get("scanned"), (status_resp, persisted)
    assert status_resp.get("phase") == persisted.get("phase"), (status_resp, persisted)


# ---------------------------------------------------------------------------
# AC 2: resume-across-passes, cursor advances, union of candidates correct
# ---------------------------------------------------------------------------

def test_scan_resumes_across_passes_to_completion(settings, admin_email, scan_docs, fresh_scan_state):
    """[AC 2] A scan forced to end incomplete (by driving exactly one pass
    then reading state) resumes on subsequent passes and finishes; the
    union of candidates across all passes equals the expected untracked set,
    and scanned strictly advances between pass 1 and completion."""
    start_resp = _admin(settings, "admin_scan_start", email=admin_email, teamId="TestTeamScopeA")
    assert start_resp.get("ok") is True, start_resp

    pass1_resp = fresh_scan_state._post_fixture("admin_scan_pass")
    pass1_state = pass1_resp["data"]["state"]
    assert pass1_state is not None, pass1_resp
    scanned_after_pass1 = pass1_state.get("scanned")

    final_state = _drive_scan_to_completion(fresh_scan_state, "TestTeamScopeA")
    assert final_state.get("phase") == "done", final_state
    assert final_state.get("status") == "done", final_state
    assert final_state.get("scanned") > scanned_after_pass1, (final_state, scanned_after_pass1)

    status_resp = _admin(settings, "admin_scan_status", email=admin_email, teamId="TestTeamScopeA")
    assert status_resp.get("ok") is True, status_resp
    assert status_resp.get("complete") is True, status_resp
    candidate_ids = {c["docId"] for c in status_resp.get("candidates", [])}

    assert candidate_ids == _expected_candidate_ids(scan_docs), (candidate_ids, scan_docs)
    assert status_resp.get("matched") == len(_expected_candidate_ids(scan_docs)), status_resp


# ---------------------------------------------------------------------------
# AC 3: idempotency of admin_scan_resume
# ---------------------------------------------------------------------------

def test_scan_resume_called_twice_is_idempotent(settings, admin_email, scan_docs, fresh_scan_state):
    """[AC 3] Calling admin_scan_resume twice in a row against the same
    incomplete scan does not double-count scanned, duplicate candidates, or
    create two pending triggers."""
    start_resp = _admin(settings, "admin_scan_start", email=admin_email, teamId="TestTeamScopeA")
    assert start_resp.get("ok") is True, start_resp

    pass_resp = fresh_scan_state._post_fixture("admin_scan_pass")
    state_after_pass = pass_resp["data"]["state"]
    assert state_after_pass is not None, pass_resp

    resume1 = _admin(settings, "admin_scan_resume", email=admin_email, teamId="TestTeamScopeA")
    assert resume1.get("ok") is True, resume1
    resume2 = _admin(settings, "admin_scan_resume", email=admin_email, teamId="TestTeamScopeA")
    assert resume2.get("ok") is True, resume2

    check_resp = fresh_scan_state._post_fixture("admin_scan_set_state")
    assert check_resp["data"]["triggers"] == 1, check_resp

    status_resp = _admin(settings, "admin_scan_status", email=admin_email, teamId="TestTeamScopeA")
    assert status_resp.get("ok") is True, status_resp
    assert status_resp.get("scanned") == state_after_pass.get("scanned"), (status_resp, state_after_pass)
    candidate_ids = [c["docId"] for c in status_resp.get("candidates", [])]
    assert len(candidate_ids) == len(set(candidate_ids)), status_resp


# ---------------------------------------------------------------------------
# AC 4: stale-running recovery
# ---------------------------------------------------------------------------

def test_stale_running_scan_is_resumable(settings, admin_email, scan_docs, fresh_scan_state):
    """[AC 4] A state stamped status:'running' with an updatedAt older than
    7 minutes is treated as stale (a crashed pass) and admin_scan_resume
    succeeds against it rather than treating it as genuinely active."""
    start_resp = _admin(settings, "admin_scan_start", email=admin_email, teamId="TestTeamScopeA")
    assert start_resp.get("ok") is True, start_resp

    pass_resp = fresh_scan_state._post_fixture("admin_scan_pass")
    state = pass_resp["data"]["state"]
    assert state is not None, pass_resp

    stale_updated_at = "2020-01-01T00:00:00.000Z"
    patch_resp = fresh_scan_state._post_fixture("admin_scan_set_state", {
        "patch": {"status": "running", "updatedAt": stale_updated_at},
    })
    assert patch_resp["data"]["state"]["updatedAt"] == stale_updated_at, patch_resp

    resume_resp = _admin(settings, "admin_scan_resume", email=admin_email, teamId="TestTeamScopeA")
    assert resume_resp.get("ok") is True, resume_resp


# ---------------------------------------------------------------------------
# AC 5: no-op safety of the trigger handler
# ---------------------------------------------------------------------------

def test_trigger_handler_is_noop_with_no_scan_pending(fresh_scan_state):
    """[AC 5] resumeAdminDocScan (via admin_scan_pass) fires cleanly with no
    scan pending -- state stays empty, no exception."""
    resp = fresh_scan_state._post_fixture("admin_scan_pass")
    assert resp["data"]["state"] is None, resp


# ---------------------------------------------------------------------------
# AC 6: negative/authorization across all three doPost routes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("action", ["admin_scan_start", "admin_scan_status", "admin_scan_resume"])
def test_scan_route_denies_non_admin_identity(settings, team_folders, action):
    """[AC 6] A verified identity NOT on Config!AdminUsers gets
    ok:false/forbidden from every route, never partial data."""
    non_admin_email = f"gts-m4cq-nonadmin-{uuid.uuid4().hex[:8]}@example.test"
    resp = _admin(settings, action, email=non_admin_email, teamId="TestTeamScopeA")
    assert resp.get("ok") is False, resp
    assert resp.get("reason") == "forbidden", resp
    assert not resp.get("candidates"), resp


@pytest.mark.parametrize("action", ["admin_scan_start", "admin_scan_status", "admin_scan_resume"])
def test_scan_route_denies_unverified_assertion(settings, action):
    """[AC 6] An unverifiable assertion fails closed on every route, same as
    every other signed-assertion route (R6/R8) -- no shared secret needed
    since this is a structural-rejection case."""
    resp = _http_post(settings["webappTestUrl"], {
        "action": action, "assertion": "not-a-jwt-shape-at-all", "teamId": "TestTeamScopeA",
    })
    assert resp.get("ok") is False, resp
    assert resp.get("reason") == "forbidden", resp
    assert not resp.get("candidates"), resp


# ---------------------------------------------------------------------------
# AC 7: restart semantics
# ---------------------------------------------------------------------------

def test_scan_start_against_in_progress_scan(settings, admin_email, scan_docs, fresh_scan_state):
    """[AC 7] admin_scan_start called again while a scan for the same team
    is already in progress (status:'waiting', incomplete) still returns
    ok:true/status:'waiting' and resets progress -- restarting the walk from
    scratch rather than erroring or silently no-op'ing, per the frozen
    contract's 'clears prior state, seeds folderStack' description for this
    route. Asserted explicitly: scanned resets to 0 and a fresh pass finds
    the same expected candidate set again (state was not left corrupted by
    the restart)."""
    first_start = _admin(settings, "admin_scan_start", email=admin_email, teamId="TestTeamScopeA")
    assert first_start.get("ok") is True, first_start

    pass_resp = fresh_scan_state._post_fixture("admin_scan_pass")
    state_after_pass = pass_resp["data"]["state"]
    assert state_after_pass is not None, pass_resp
    assert state_after_pass.get("phase") in ("enumerate", "match"), state_after_pass

    second_start = _admin(settings, "admin_scan_start", email=admin_email, teamId="TestTeamScopeA")
    assert second_start.get("ok") is True, second_start
    assert second_start.get("status") == "waiting", second_start
    assert second_start.get("scanned") == 0, second_start

    final_state = _drive_scan_to_completion(fresh_scan_state, "TestTeamScopeA")
    status_resp = _admin(settings, "admin_scan_status", email=admin_email, teamId="TestTeamScopeA")
    assert status_resp.get("ok") is True, status_resp
    assert status_resp.get("complete") is True, status_resp
    candidate_ids = {c["docId"] for c in status_resp.get("candidates", [])}
    assert candidate_ids == _expected_candidate_ids(scan_docs), (candidate_ids, scan_docs, final_state)


# ---------------------------------------------------------------------------
# AC 8: proven-to-fail demonstration for the progress-persistence assertion
# ---------------------------------------------------------------------------

def test_progress_persistence_assertion_fails_when_violated(settings, admin_email, scan_docs, fresh_scan_state):
    """[AC 8 / Backstop rule] Deliberately violate the durable-state /
    monotonic-progress invariant that test_scan_resumes_across_passes_to_completion
    relies on (AC 2/4: 'scanned' strictly advances across a resume) by
    rewinding cursor/scanned via admin_scan_set_state, then show the resume
    assertion goes red. Proves the assertion is not vacuously green."""
    start_resp = _admin(settings, "admin_scan_start", email=admin_email, teamId="TestTeamScopeA")
    assert start_resp.get("ok") is True, start_resp

    pass1_resp = fresh_scan_state._post_fixture("admin_scan_pass")
    pass1_state = pass1_resp["data"]["state"]
    assert pass1_state is not None, pass1_resp
    scanned_after_pass1 = pass1_state.get("scanned")

    # Violate the invariant: rewind scanned/cursor backward as if a pass had
    # regressed instead of advanced.
    fresh_scan_state._post_fixture("admin_scan_set_state", {
        "patch": {"scanned": 0, "cursor": 0},
    })

    pass2_resp = fresh_scan_state._post_fixture("admin_scan_pass")
    pass2_state = pass2_resp["data"]["state"]
    assert pass2_state is not None, pass2_resp

    with pytest.raises(AssertionError):
        assert pass2_state.get("scanned") > scanned_after_pass1, (pass2_state, scanned_after_pass1)
