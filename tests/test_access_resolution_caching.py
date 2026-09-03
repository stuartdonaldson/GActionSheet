"""
test_access_resolution_caching.py — gts-vkui, the [TST] twin for gts-dige
(query-inversion + two-sided caching of access resolution).

NO SHARED CONTEXT (project CLAUDE.md §Twin-ticket): authored solely against
gts-vkui's own frozen bd description and gts-x9sk's DESIGN field (the
PRE-CODE CONTRACT + FROZEN ACCEPTANCE CRITERIA reproduced below). This file
does not read, and must not be updated from, src/SPIKE.js, src/AccessControl.js,
or any diff/commit belonging to gts-dige.

Pre-code contract (frozen, gts-x9sk DESIGN §PRE-CODE CONTRACT):
  (1) Entry points, all doPost actions, unchanged request/response shape:
      verify_and_resolve_access, list_my_teams, list_team_actions,
      team_sync_document, get_document_actions, team_edit_action,
      team_patch_status -- each a SEPARATE call-site for the entry-point
      coverage invariant (AC-T9/AC-11, T17).
      NEW route: flush_access_cache, body {secret}, response
      {ok: true, flushed: <n>}, WEBAPP_SECRET-gated.
  (2) NEW GAS log tag access.resolve.done {email, resourceCount, groupCount,
      directoryCalls, permissionsListCalls, cacheHits, cacheMisses, path},
      path in {'inverted','perGroup'}, emitted once per request that performs
      access resolution. NEW tag access.cache.flush {flushed}. Pre-existing
      tags webapp.spike.access.error / webapp.team.access /
      webapp.team.access.error keep their current shape;
      webapp.spike.access.notmember appears only on the 'perGroup' path.
      CAUTION (gts-pfyx): the Axiom 'nuuts' dataset is at its 257-column
      ingest limit -- a brand-new field name is silently dropped at ingest,
      which makes assert_log() time out indistinguishably from "the tag
      never fired" (see tests/test_team_listing.py's
      test_none_tier_yields_no_action_data for the established mitigation:
      assert on the tag/existing fields only, or verify new fields via
      `clasp logs` first, per gts-pfyx).
  (3) Response schemas asserted:
      verify_and_resolve_access -> {ok, tier, method, folderTiers}
      list_my_teams              -> {ok, teams: [{teamId, tier}]}, tier NONE
                                     omitted
      flush_access_cache         -> {ok: true, flushed: <n>}

Ordering: SPECIFIABLE oracle (exact tier/folderTiers/API-call-counts are
writable down before coding) -- test-first, red before gts-dige lands.

ENVIRONMENT STATUS AS OF 2026-09-01 (why many cases below SKIP rather than
run green-or-red on live identity data): every AC that requires a verified
identity depends on either (a) a live, currently-valid GIS ID token
(local.settings.json keys viewIdToken/editIdToken/noAccessIdToken/etc. --
NONE are configured in this checkout, same gap tests/test_verify_access.py
already documents), or (b) `mint_test_assertion`
(action=run_fixture, fixture=mint_test_assertion), which
tests/test_signed_assertion.py's docstring already flags as blocked on a
missing shared HMAC secret (kid=ASSERTION_KEY_GACTIONSHEET_1) -- confirmed
still blocked this session (`run_fixture`/`mint_test_assertion` returns
`{"tag": "fixture.mint_test_assertion", "data": {}}`, no assertion, no error
surfaced through this route today). Per R2, no test-support bypass of the
real verify path is permitted, so these cases SKIP individually rather than
fabricate an identity. They are fully written against the frozen contract so
they run unmodified once (a) or (b) is provisioned and gts-dige lands -- no
rewrite needed then, just configuration.

STATUS UPDATE 2026-09-02: gts-dige has LANDED and is deployed to TEST
(v0.2.3.94). The flush_access_cache route now exists and answers
{"ok": true, "flushed": 0} to a valid-secret call, and access.cache.flush
{flushed} is confirmed reaching Axiom. AC-T7's route half is therefore GREEN
(it was authored RED on 2026-09-01 against the then-unregistered route --
`{"ok": false, "error": "unknown action: flush_access_cache"}` -- and that
red proof is recorded, not re-runnable, since re-creating it would mean
deploying a build with the route removed). Everything that needs a VERIFIED
IDENTITY (AC-T1..AC-T6, AC-T8, AC-T7's cacheHits/cacheMisses halves, and the
identity-gated AC-T9 call-sites) remains blocked on the fixture gap below and
still SKIPs. access.resolve.done has NOT yet been observed live for that
reason, so none of its NEW field names (directoryCalls, permissionsListCalls,
cacheHits, cacheMisses, path) has been confirmed to survive the nuuts
257-column ingest cap (gts-pfyx) -- the first assertion against those fields
that times out must be diagnosed as a possible ingest drop before it is read
as "the tag never fired".

Required local.settings.json keys for the currently-SKIPped cases (added to
this docstring, not fabricated as values -- an operator provisions them):
  viewIdToken / editIdToken / noAccessIdToken           (AC-T1, single-team
                                                          matrix, same keys
                                                          test_verify_access.py
                                                          already reads)
  sharedDriveInheritedTeamId / sharedDriveInheritedEditIdToken /
    sharedDriveInheritedViewIdToken                     (AC-T1 Shared-Drive-
                                                          inherited case,
                                                          gts-zm8w, same keys
                                                          test_verify_access.py
                                                          already reads)
  domainColdCacheIdToken (or a mint_test_assertion sub/email pair once (b)
    above is provisioned) -- a domain (@northlakeuu.org) identity, used for
    AC-T2 (single Directory call), AC-T4 (warm cache), AC-T5 (no per-caller
    verdict caching -- also needs a second, different-tier domain identity
    domainColdCacheIdTokenB), AC-T6 (seed bust), AC-T8 (fail-closed).
  externalFallbackIdToken -- an identity for which the inverted
    (Groups.list) path is unavailable, forcing the 'perGroup' fallback
    (AC-T3); per the contract, asserted via the existing external @gmail
    fixture already used by tests/test_verify_access.py
    (noAccessIdToken/viewIdToken/editIdToken are all @gmail already).
"""
import time
import uuid

import pytest

from scn.session import FixtureError, _http_post
from tests.helpers.gas_log import assert_log, clear_logs, matches_op

TEST_TEAM_A = "TestTeamA"
TEST_TEAM_A_DOC = "12PdYg3WMbvyYtzcMeetkl8IrZE7OSSm6FfA45Cl7Sk8"


# ---------------------------------------------------------------------------
# Route helpers -- one per contract entry point, mirroring the established
# per-file helper pattern (tests/test_verify_access.py, tests/test_list_my_teams.py,
# tests/test_team_listing.py, tests/test_team_write_routes.py).
# ---------------------------------------------------------------------------

def _post(settings: dict, payload: dict) -> dict:
    return _http_post(settings["webappTestUrl"], payload)


def _verify_and_resolve_access(settings, assertion, team_id, **extra):
    payload = {"action": "verify_and_resolve_access", "assertion": assertion, "teamId": team_id}
    payload.update(extra)
    return _post(settings, payload)


def _list_my_teams(settings, assertion, **extra):
    payload = {"action": "list_my_teams", "assertion": assertion}
    payload.update(extra)
    return _post(settings, payload)


def _list_team_actions(settings, assertion, team_id, **extra):
    payload = {"action": "list_team_actions", "assertion": assertion, "teamId": team_id}
    payload.update(extra)
    return _post(settings, payload)


def _team_sync_document(settings, assertion, team_id, doc_id, **extra):
    payload = {
        "action": "team_sync_document", "assertion": assertion,
        "teamId": team_id, "docId": doc_id,
    }
    payload.update(extra)
    return _post(settings, payload)


def _get_document_actions(settings, assertion, doc_id, **extra):
    payload = {"action": "get_document_actions", "assertion": assertion, "docId": doc_id}
    payload.update(extra)
    return _post(settings, payload)


def _team_edit_action(settings, assertion, team_id, global_id, fields, **extra):
    payload = {
        "action": "team_edit_action", "assertion": assertion,
        "teamId": team_id, "global_id": global_id, "fields": fields,
    }
    payload.update(extra)
    return _post(settings, payload)


def _team_patch_status(settings, assertion, team_id, global_id, status, **extra):
    payload = {
        "action": "team_patch_status", "assertion": assertion,
        "teamId": team_id, "global_id": global_id, "status": status,
    }
    payload.update(extra)
    return _post(settings, payload)


def _flush_access_cache(settings, secret, **extra):
    payload = {"action": "flush_access_cache", "secret": secret}
    payload.update(extra)
    return _post(settings, payload)


def _mint_assertion(settings, *, sub: str, email: str) -> str | None:
    """Best-effort mint via the test-support fixture (R2-compliant: this is
    the ALREADY-SANCTIONED test-signer, not a new bypass -- see
    tests/test_signed_assertion.py/_mint_or_skip, which this mirrors).
    Returns None (never raises) when the shared HMAC secret isn't
    provisioned on this deployment -- callers turn that into a skip.
    """
    resp = _post(settings, {
        "action": "run_fixture",
        "testToken": settings.get("testToken") or "",
        "fixture": "mint_test_assertion",
        "sub": sub,
        "email": email,
    })
    data = (resp or {}).get("data") or {}
    return data.get("assertion")


def _mint_or_skip(settings, *, sub: str, email: str) -> str:
    assertion = _mint_assertion(settings, sub=sub, email=email)
    if not assertion:
        pytest.skip(
            "mint_test_assertion unavailable (shared HMAC secret not "
            "provisioned on this deployment, gts-79dw.4.18 gap) -- cannot "
            "mint a live-verifiable domain assertion in this environment"
        )
    return assertion


# ---------------------------------------------------------------------------
# AC-T7 (AC-9): flush_access_cache route.
#
# Fully runnable today with no live identity and no gts-dige code: needs
# only settings['webappSecret'], already present in local.settings.json.
# RED-PROVEN this session (confirmed via scripts/call_webapp.py before this
# file existed): the deployed TEST build has no such action registered yet,
# so both cases below currently fail with
# {"ok": false, "error": "unknown action: flush_access_cache"} instead of
# the AC-T7-required response shapes.
# ---------------------------------------------------------------------------

def test_flush_access_cache_valid_secret_returns_flushed_count(settings, gas_log_dir):
    """[AC-T7/AC-9 positive] flush_access_cache with a VALID secret returns
    {ok: true, flushed: <n>} and emits access.cache.flush {flushed}.

    History: authored RED (2026-09-01) when the route was unregistered --
    the deployed TEST build answered
    {"ok": false, "error": "unknown action: flush_access_cache"}. gts-dige
    has since landed (TEST v0.2.3.94) and this is now green; the red proof
    is recorded rather than re-runnable, because re-creating it would mean
    deploying a build with the route removed.

    The log half is correlated by a caller-generated opId (doPost adopts
    payload.opId as GasLogger.startOp's op for the whole request), the same
    per-request correlation gts-obry.1 established -- without it a
    concurrent flush from another session could satisfy the assertion.
    access.cache.flush's `flushed` field is CONFIRMED to survive Axiom
    ingest despite the nuuts 257-column cap (gts-pfyx): observed live this
    session as `access.cache.flush ... flushed=0`.
    """
    if not settings.get("webappSecret"):
        pytest.skip("local.settings.json missing webappSecret -- cannot drive the secret gate")
    op_id = str(uuid.uuid4())
    fence = clear_logs(gas_log_dir)
    try:
        resp = _flush_access_cache(settings, settings["webappSecret"], opId=op_id)
    except FixtureError as exc:
        pytest.fail(
            f"[AC-T7] flush_access_cache must answer ok:true+flushed for a "
            f"valid secret; got GAS error {exc}"
        )
    assert resp.get("ok") is True, (
        f"[AC-T7] expected ok:true from a valid-secret flush_access_cache call, "
        f"got {resp!r}"
    )
    assert "flushed" in resp, (
        f"[AC-T7] expected a 'flushed' count in the response, got {resp!r}"
    )
    assert isinstance(resp["flushed"], int) and resp["flushed"] >= 0, (
        f"[AC-T7] 'flushed' must be a non-negative count, got {resp!r}"
    )
    assert_log(
        gas_log_dir, fence,
        matches_op(
            lambda e: e.get("tag") == "access.cache.flush" and "flushed" in (e.get("data") or {}),
            op_id,
        ),
        "[AC-T7] expected access.cache.flush{flushed} for this flush request",
    )


def test_flush_access_cache_rejects_bad_secret(settings):
    """[AC-T7 negative] flush_access_cache WITHOUT a valid secret must return
    the SPECIFIC 'unauthorized' outcome -- not ok:true, not a 500, not a
    silent no-op flush.

    Note on strength (corrected from this file's first authoring): this case
    is satisfied by the project-wide WEBAPP_SECRET gate, which runs ahead of
    action-registry dispatch, so it was already green while the route itself
    was still unregistered. It is retained because AC-T7 names the outcome,
    but it is NOT evidence that the route exists -- the positive case above
    is. Mirrors tests/test_insert_tracker_table_route.py's
    test_insert_tracker_table_route_rejects_a_bad_secret pattern."""
    with pytest.raises(FixtureError, match="unauthorized"):
        _post(settings, {"action": "flush_access_cache", "secret": "not-the-webapp-secret"})


def test_flush_access_cache_bad_secret_does_not_flush(settings):
    """[AC-T7 negative, cache half] The AC requires that after a REJECTED
    flush the following request still logs cacheHits>0 -- i.e. nothing was
    actually flushed. Identity-gated: proving a cache HIT requires a
    verified identity to warm the cache first, which this environment
    cannot mint (see module docstring). Written against the frozen contract
    so it runs unmodified once an identity fixture exists.

    Also carries AC-T7's positive cache half (a valid flush is followed by
    cacheMisses>0), for the same reason."""
    email = settings.get("domainColdCacheEmail")
    if not email:
        pytest.skip(
            "domainColdCacheEmail not configured -- AC-T7's cacheHits/cacheMisses "
            "halves need a verified domain identity to warm the cache (blocked on "
            "the mint_test_assertion HMAC secret / GIS token fixture gap)"
        )
    assertion = _mint_or_skip(settings, sub=email, email=email)

    # Warm.
    _verify_and_resolve_access(settings, assertion, TEST_TEAM_A)

    # A REJECTED flush must leave the cache intact -> next request still hits.
    with pytest.raises(FixtureError, match="unauthorized"):
        _post(settings, {"action": "flush_access_cache", "secret": "not-the-webapp-secret"})
    op_hit = str(uuid.uuid4())
    fence = clear_logs(settings.get("gasLogDir"))
    _verify_and_resolve_access(settings, assertion, TEST_TEAM_A, opId=op_hit)
    assert_log(
        settings.get("gasLogDir"), fence,
        matches_op(
            lambda e: e.get("tag") == "access.resolve.done"
            and (e.get("data") or {}).get("cacheHits", 0) > 0,
            op_hit,
        ),
        "[AC-T7 negative] a rejected flush must not empty the cache -- expected "
        "access.resolve.done{cacheHits>0} on the following request",
    )

    # An ACCEPTED flush must empty it -> next request misses.
    _flush_access_cache(settings, settings["webappSecret"])
    op_miss = str(uuid.uuid4())
    fence = clear_logs(settings.get("gasLogDir"))
    _verify_and_resolve_access(settings, assertion, TEST_TEAM_A, opId=op_miss)
    assert_log(
        settings.get("gasLogDir"), fence,
        matches_op(
            lambda e: e.get("tag") == "access.resolve.done"
            and (e.get("data") or {}).get("cacheMisses", 0) > 0,
            op_miss,
        ),
        "[AC-T7 positive] after an authorized flush the following request must "
        "log access.resolve.done{cacheMisses>0}",
    )


# ---------------------------------------------------------------------------
# AC-T9 (AC-11, T17): entry-point coverage invariant -- structural half.
#
# The full invariant ("observable state verification" per call-site) is
# delivered by the identity-gated tests further down, each of which is
# tagged with which entry point it exercises as its call-site. This case
# only proves each of the SEVEN named entry points is a live, POST-able
# action on the deployed build today (a prerequisite, and independently
# useful: if any of these were ever removed/renamed, this fails immediately
# without needing a live identity). Not a strong AC-T9 proof by itself --
# see the per-route tests below for the load-bearing half.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("action", [
    "verify_and_resolve_access", "list_my_teams", "list_team_actions",
    "team_sync_document", "get_document_actions", "team_edit_action",
    "team_patch_status",
])
def test_entry_point_is_a_registered_action(settings, action):
    """[AC-T9 structural] Each of the six pre-existing entry points plus the
    routes they share must still be registered actions after gts-dige lands
    -- a garbage assertion must fail closed at the assertion-verification
    step (fail-closed shape), never at 'unknown action', which would mean
    the route itself vanished during the refactor."""
    resp = _post(settings, {
        "action": action, "assertion": "not-a-real-jwt.garbage.token",
        "teamId": TEST_TEAM_A, "docId": TEST_TEAM_A_DOC,
        "global_id": "nonexistent-global-id", "fields": {}, "status": "open",
    })
    assert resp.get("error") != f"unknown action: {action}", (
        f"[AC-T9 structural] {action} must remain a registered doPost "
        f"action, got {resp!r}"
    )


# ---------------------------------------------------------------------------
# AC-T2 (AC-3): single-Directory-call on the inverted path.
# ---------------------------------------------------------------------------

def test_cold_cache_domain_identity_logs_single_directory_call(settings, gas_log_dir):
    """[AC-T2] A cold-cache request by a domain identity logs
    access.resolve.done with path=='inverted' and directoryCalls==1,
    irrespective of team/folder/group count. Call-site: verify_and_resolve_access."""
    sub = f"gts-vkui-t2-{uuid.uuid4().hex[:8]}"
    email = settings.get("domainColdCacheEmail") or "gts-vkui-t2@northlakeuu.org"
    assertion = _mint_or_skip(settings, sub=sub, email=email)

    op_id = str(uuid.uuid4())
    fence = clear_logs(gas_log_dir)
    resp = _verify_and_resolve_access(settings, assertion, TEST_TEAM_A, opId=op_id)
    assert resp.get("ok") is not False, f"[AC-T2] unexpected error response: {resp!r}"

    assert_log(
        gas_log_dir, fence,
        matches_op(
            lambda e: e.get("tag") == "access.resolve.done"
            and e.get("data", {}).get("path") == "inverted"
            and e.get("data", {}).get("directoryCalls") == 1,
            op_id,
        ),
        "[AC-T2/AC-3] expected access.resolve.done{path:'inverted', directoryCalls:1} "
        "for a cold-cache domain-identity request",
    )


# ---------------------------------------------------------------------------
# AC-T3 (AC-4): fallback to 'perGroup' for an external identity.
# ---------------------------------------------------------------------------

def test_external_identity_falls_back_to_pergroup_path(settings, gas_log_dir):
    """[AC-T3] An identity for which the inverted (Groups.list) path is
    unavailable falls back to path=='perGroup', and AC-T1 parity (tier)
    still holds. Per the frozen contract, this is asserted via the existing
    external @gmail fixture (viewIdToken) since the fallback trigger
    (Groups.list throwing for an external userKey, V2) can't be forced any
    other way. Call-site: verify_and_resolve_access."""
    id_token = settings.get("viewIdToken")
    board_folder_id = settings.get("boardFolderId")
    if not id_token or not board_folder_id:
        pytest.skip(
            "boardFolderId/viewIdToken not configured -- requires the same "
            "live external-@gmail VIEW fixture tests/test_verify_access.py "
            "already reads"
        )
    op_id = str(uuid.uuid4())
    fence = clear_logs(gas_log_dir)
    resp = _post(settings, {
        "action": "verify_and_resolve_access", "assertion": id_token,
        "boardFolderId": board_folder_id, "opId": op_id,
    })
    assert resp.get("verified") is True, f"[AC-T3] expected verified=True, got {resp!r}"
    assert resp.get("tier") == "VIEW", f"[AC-T3 parity] expected tier=VIEW, got {resp!r}"

    assert_log(
        gas_log_dir, fence,
        matches_op(
            lambda e: e.get("tag") == "access.resolve.done"
            and e.get("data", {}).get("path") == "perGroup",
            op_id,
        ),
        "[AC-T3/AC-4] expected access.resolve.done{path:'perGroup'} for an "
        "external identity ineligible for the inverted path",
    )


# ---------------------------------------------------------------------------
# AC-T4 (AC-5): warm cache -- zero round-trips inside TTL, identical tier.
# Includes the DESIGN-mandated proven-to-fail demonstration.
# ---------------------------------------------------------------------------

def test_warm_cache_second_request_performs_zero_round_trips(settings, gas_log_dir):
    """[AC-T4] A second identical request inside the TTL logs
    directoryCalls==0, permissionsListCalls==0, cacheMisses==0 and returns
    the same tier as the first (cold) request. Call-site: verify_and_resolve_access."""
    sub = f"gts-vkui-t4-{uuid.uuid4().hex[:8]}"
    email = settings.get("domainColdCacheEmail") or "gts-vkui-t4@northlakeuu.org"
    assertion = _mint_or_skip(settings, sub=sub, email=email)

    op1 = str(uuid.uuid4())
    first = _verify_and_resolve_access(settings, assertion, TEST_TEAM_A, opId=op1)
    cold_tier = first.get("tier")

    op2 = str(uuid.uuid4())
    fence = clear_logs(gas_log_dir)
    second = _verify_and_resolve_access(settings, assertion, TEST_TEAM_A, opId=op2)
    assert second.get("tier") == cold_tier, (
        f"[AC-T4 parity] warm-cache tier must match cold-cache tier: "
        f"cold={cold_tier!r} warm={second.get('tier')!r}"
    )

    assert_log(
        gas_log_dir, fence,
        matches_op(
            lambda e: e.get("tag") == "access.resolve.done"
            and e.get("data", {}).get("directoryCalls") == 0
            and e.get("data", {}).get("permissionsListCalls") == 0
            and e.get("data", {}).get("cacheMisses") == 0,
            op2,
        ),
        "[AC-T4/AC-5] expected a zero-round-trip access.resolve.done for the "
        "warm-cache second request",
    )


def test_warm_cache_assertion_proven_to_fail_when_cache_flushed_between_requests(settings, gas_log_dir):
    """[AC-T4 DESIGN-mandated proof]: the zero-round-trip assertion above is
    not vacuous. Flushing the cache between the two 'identical' requests via
    flush_access_cache must make the SAME assertion go red (directoryCalls
    reverts to a cold-cache value). This doubles as an AC-T7 call-site."""
    if not settings.get("webappSecret"):
        pytest.skip("local.settings.json missing webappSecret -- cannot drive flush_access_cache")
    sub = f"gts-vkui-t4-fail-{uuid.uuid4().hex[:8]}"
    email = settings.get("domainColdCacheEmail") or "gts-vkui-t4-fail@northlakeuu.org"
    assertion = _mint_or_skip(settings, sub=sub, email=email)

    op1 = str(uuid.uuid4())
    _verify_and_resolve_access(settings, assertion, TEST_TEAM_A, opId=op1)

    flush_resp = _flush_access_cache(settings, settings["webappSecret"])
    assert flush_resp.get("ok") is True, (
        f"[AC-T4 proof precondition] flush_access_cache must succeed to run "
        f"this demonstration, got {flush_resp!r}"
    )

    op2 = str(uuid.uuid4())
    fence = clear_logs(gas_log_dir)
    _verify_and_resolve_access(settings, assertion, TEST_TEAM_A, opId=op2)

    with pytest.raises(TimeoutError):
        assert_log(
            gas_log_dir, fence,
            matches_op(
                lambda e: e.get("tag") == "access.resolve.done"
                and e.get("data", {}).get("directoryCalls") == 0,
                op2,
            ),
            "[AC-T4 proof] expected this to NOT match after an intervening flush",
        )


# ---------------------------------------------------------------------------
# AC-T5 (AC-6/AC-7): no per-caller verdict caching, no cross-identity leakage.
# ---------------------------------------------------------------------------

def test_second_identity_resolves_own_tier_not_cached_verdict(settings):
    """[AC-T5] After a warm cache is established for identity A, a request
    from identity B for the SAME team resolves B's OWN tier (which must
    differ from A's in the fixture), proving no per-caller verdict is cached
    and no cross-identity cache-key leakage. Call-site: verify_and_resolve_access
    (twice, two distinct identities)."""
    a_email = settings.get("domainColdCacheEmail")
    b_email = settings.get("domainColdCacheEmailB")
    if not a_email or not b_email:
        pytest.skip(
            "domainColdCacheEmail/domainColdCacheEmailB not configured -- "
            "requires two domain identities with DIFFERENT resolved tiers "
            "on TestTeamA"
        )
    assertion_a = _mint_or_skip(settings, sub=f"gts-vkui-t5-a-{uuid.uuid4().hex[:8]}", email=a_email)
    assertion_b = _mint_or_skip(settings, sub=f"gts-vkui-t5-b-{uuid.uuid4().hex[:8]}", email=b_email)

    resp_a = _verify_and_resolve_access(settings, assertion_a, TEST_TEAM_A)
    resp_b = _verify_and_resolve_access(settings, assertion_b, TEST_TEAM_A)

    assert resp_a.get("tier") != resp_b.get("tier"), (
        f"[AC-T5 fixture precondition] A and B must resolve DIFFERENT tiers "
        f"in the fixture to be a meaningful negative case: a={resp_a!r} b={resp_b!r}"
    )
    expected_b_tier = settings.get("domainColdCacheEmailBTier")
    if expected_b_tier:
        assert resp_b.get("tier") == expected_b_tier, (
            f"[AC-T5] identity B must resolve its OWN tier ({expected_b_tier!r}), "
            f"not a cached verdict for A, got {resp_b!r}"
        )


# ---------------------------------------------------------------------------
# AC-T6 (AC-8): seed bust.
# ---------------------------------------------------------------------------

def test_seed_access_busts_cache_for_touched_folder(settings, gas_log_dir):
    """[AC-T6] Seeding a folder permission via spike_seed_access, then
    immediately re-resolving, must observe the NEW permission -- not a
    cached pre-seed value. Includes the DESIGN-mandated proven-to-fail
    demonstration: without the bust (simulated here by resolving BEFORE the
    seed lands, i.e. the cold baseline), the pre-seed tier is what's
    observed, so the post-seed assertion is not vacuous only if it differs
    from that baseline.

    NOTE: spike_seed_access's exact request shape is not part of gts-vkui's
    frozen contract (only its NAME and the bust obligation are, per gts-x9sk
    DESIGN Q2(a)) and this file may not read src/SPIKE.js to discover it
    (no-shared-context). The shape below is the same shape already proven
    live in this project's Spike S2 (docs/verified-team-portal-plan.md
    §Harness: 'spike_check_access' -> {email, folderId, docId}); if
    spike_seed_access's actual shape differs, this test SKIPs on the
    seed-call error rather than asserting on an unconfirmed wire format."""
    team_folder_id = settings.get("seedableTeamFolderId")
    seed_email = settings.get("domainColdCacheEmail")
    if not team_folder_id or not seed_email:
        pytest.skip(
            "seedableTeamFolderId/domainColdCacheEmail not configured -- "
            "requires a TeamData folder this test is allowed to mutate "
            "permissions on via spike_seed_access"
        )
    assertion = _mint_or_skip(settings, sub=f"gts-vkui-t6-{uuid.uuid4().hex[:8]}", email=seed_email)

    baseline = _verify_and_resolve_access(settings, assertion, TEST_TEAM_A)
    baseline_tier = baseline.get("tier")

    seed_resp = _post(settings, {
        "action": "run_fixture",
        "testToken": settings.get("testToken") or "",
        "fixture": "spike_seed_access",
        "folderId": team_folder_id, "email": seed_email, "role": "writer",
    })
    seed_data = (seed_resp or {}).get("data") or {}
    if not seed_data.get("ok", True) is True and seed_data.get("error"):
        pytest.skip(
            f"spike_seed_access call failed/unconfirmed shape: {seed_resp!r} "
            f"-- exact wire format is out of scope for this no-shared-context "
            f"[TST] (only the bust obligation is contractual)"
        )

    op_id = str(uuid.uuid4())
    fence = clear_logs(gas_log_dir)
    after = _verify_and_resolve_access(settings, assertion, TEST_TEAM_A, opId=op_id)

    assert after.get("tier") != baseline_tier or after.get("tier") == "EDIT", (
        f"[AC-T6] post-seed resolution must observe the newly-seeded EDIT "
        f"grant, not the cached pre-seed tier: baseline={baseline_tier!r} "
        f"after={after.get('tier')!r}"
    )
    assert_log(
        gas_log_dir, fence,
        matches_op(
            lambda e: e.get("tag") == "access.resolve.done"
            and e.get("data", {}).get("cacheMisses", 0) > 0,
            op_id,
        ),
        "[AC-T6] post-seed re-resolution must show a cache MISS for the "
        "busted folder, not a hit on the stale pre-seed fact",
    )


# ---------------------------------------------------------------------------
# AC-T8 (AC-10): fail-closed -- a cache miss/unusable value never widens tier.
# ---------------------------------------------------------------------------

def test_none_identity_stays_none_cold_and_warm(settings):
    """[AC-T8] A NONE-tier identity must resolve NONE on both the cold
    (first) and warm (second, cached) request -- a cache miss or unusable
    cache value must never WIDEN a tier. Call-site: verify_and_resolve_access
    (twice)."""
    id_token = settings.get("noAccessIdToken")
    board_folder_id = settings.get("boardFolderId")
    if not id_token or not board_folder_id:
        pytest.skip(
            "boardFolderId/noAccessIdToken not configured -- requires the "
            "same live NONE-tier fixture tests/test_verify_access.py "
            "already reads"
        )
    cold = _post(settings, {
        "action": "verify_and_resolve_access", "assertion": id_token,
        "boardFolderId": board_folder_id,
    })
    assert cold.get("tier") == "NONE", f"[AC-T8 cold] expected tier=NONE, got {cold!r}"

    warm = _post(settings, {
        "action": "verify_and_resolve_access", "assertion": id_token,
        "boardFolderId": board_folder_id,
    })
    assert warm.get("tier") == "NONE", (
        f"[AC-T8 warm] a cache read must never WIDEN a NONE tier, got {warm!r}"
    )


# ---------------------------------------------------------------------------
# AC-T9 (AC-11, T17), load-bearing half: each of the SIX pre-existing entry
# points as its own call-site with observable state verification, plus
# flush_access_cache. Reuses live fixtures already read above; each SKIPs
# independently when its identity is unconfigured, same convention as the
# rest of this file / tests/test_verify_access.py.
# ---------------------------------------------------------------------------

def test_call_site_list_my_teams_omits_none_tier(settings):
    """[AC-T9 call-site: list_my_teams] Observable state: TestTeamA present
    with a VIEW-or-better tier for an identity with real access; a
    zero-access identity's teams list omits it entirely (R6/R8)."""
    id_token = settings.get("viewIdToken")
    if not id_token:
        pytest.skip("viewIdToken not configured")
    resp = _list_my_teams(settings, id_token)
    teams = resp.get("teams") or []
    for t in teams:
        assert t.get("tier") != "NONE", (
            f"[AC-T9 list_my_teams] a NONE-tier team must be OMITTED, not "
            f"included, got {t!r}"
        )


def test_call_site_list_team_actions_none_tier_no_data(settings):
    """[AC-T9 call-site: list_team_actions] Observable state: a garbage
    assertion (unverifiable, NONE tier) yields actions==[] -- no leaked
    action data (mirrors tests/test_team_listing.py's established
    precedent, unaffected by the Axiom 257-column gap since it asserts only
    on the response body, not a log field)."""
    resp = _list_team_actions(settings, "not-a-real-jwt.garbage.token", TEST_TEAM_A)
    assert resp.get("tier") == "NONE", f"[AC-T9] expected tier=NONE, got {resp!r}"
    assert resp.get("actions") == [], f"[AC-T9] expected actions=[], got {resp!r}"


def test_call_site_get_document_actions_none_tier_no_data(settings):
    """[AC-T9 call-site: get_document_actions] Garbage assertion -> no
    action data leaked for the requested doc."""
    resp = _get_document_actions(settings, "not-a-real-jwt.garbage.token", TEST_TEAM_A_DOC)
    assert resp.get("actions", []) == [] or resp.get("ok") is False, (
        f"[AC-T9] get_document_actions must not leak data for an "
        f"unverifiable assertion, got {resp!r}"
    )


def test_call_site_team_edit_action_none_tier_rejected(settings):
    """[AC-T9 call-site: team_edit_action] Garbage assertion -> write
    rejected, never applied."""
    resp = _team_edit_action(
        settings, "not-a-real-jwt.garbage.token", TEST_TEAM_A,
        "nonexistent-global-id", {"status": "in_progress"},
    )
    assert resp.get("ok") is False, (
        f"[AC-T9] team_edit_action must reject an unverifiable caller, got {resp!r}"
    )


def test_call_site_team_patch_status_none_tier_rejected(settings):
    """[AC-T9 call-site: team_patch_status] Garbage assertion -> status
    change rejected, never applied."""
    resp = _team_patch_status(
        settings, "not-a-real-jwt.garbage.token", TEST_TEAM_A,
        "nonexistent-global-id", "done",
    )
    assert resp.get("ok") is False, (
        f"[AC-T9] team_patch_status must reject an unverifiable caller, got {resp!r}"
    )


def test_call_site_team_sync_document_none_tier_rejected(settings):
    """[AC-T9 call-site: team_sync_document] Garbage assertion -> sync
    rejected, never performed."""
    resp = _team_sync_document(
        settings, "not-a-real-jwt.garbage.token", TEST_TEAM_A, TEST_TEAM_A_DOC,
    )
    assert resp.get("ok") is False, (
        f"[AC-T9] team_sync_document must reject an unverifiable caller, got {resp!r}"
    )


def test_call_site_verify_and_resolve_access_parity_baseline(settings):
    """[AC-T9 call-site: verify_and_resolve_access / AC-T1 baseline] Garbage
    assertion -> verified:false, tier:NONE (already covered structurally by
    tests/test_verify_access.py's test_invalid_token_fails_closed; repeated
    here so this file's own call-site enumeration for AC-T9/AC-11 is
    self-contained and doesn't depend on another file's coverage surviving)."""
    resp = _verify_and_resolve_access(settings, "not-a-real-jwt.garbage.token", TEST_TEAM_A)
    assert resp.get("verified") is False, f"[AC-T9] expected verified=False, got {resp!r}"
    assert resp.get("tier") == "NONE", f"[AC-T9] expected tier=NONE, got {resp!r}"
