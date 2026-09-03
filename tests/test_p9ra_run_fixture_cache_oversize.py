"""
test_p9ra_run_fixture_cache_oversize.py — gts-p9ra [TST]

Regression coverage for gts-p9ra: TestWebApp.js:133's _handleRunFixture caches
every fixture response for opId-based retry dedupe (gts-f3me.2) via
CacheService.put(), which has a hard ~100KB per-value cap in Apps Script. A
whole-sheet-audit fixture can legitimately exceed that once the live TEST
corpus grows large enough (discovered live during gts-u947's regression-verify
sweep, 2026-09-01, via dump_all_action_rows) -- previously unguarded, so the
entire request 500'd to an HTML Apps Script error page instead of returning
the already-computed JSON response.

Fix (already landed at TestWebApp.js:133): rfCache.put is wrapped in
try/catch; a failure logs fixture.cachePutSkipped and falls through to
returning the computed response, rather than throwing.

This is a harness-resilience fix, not product behavior -- these fixtures are
read-only whole-sheet/Drive audits with no side effects, so a same-opId retry
re-executing (cache miss) instead of returning the cached response is
harmless by construction; this test does not assert cache-hit vs re-execute,
only that the call-site survives regardless of response size or whether the
CacheService.put() write actually succeeded.

Covers the three fixtures gts-p9ra's design names as plausibly able to
exceed CacheService's 100KB cap on the live TEST corpus:
dump_all_action_rows, get_all_docdata_rows, list_test_drive_docs. Each is
driven twice with the same client-supplied opId (simulating exactly the
retry-after-lost-response scenario _http_post produces) to exercise
_handleRunFixture's cache-read AND cache-write paths at the real entry point
-- not just the write guard in isolation.
"""
import uuid

import pytest

from scn.session import ScenarioSession

_FIXTURES = ["dump_all_action_rows", "get_all_docdata_rows", "list_test_drive_docs"]


@pytest.mark.parametrize("fixture_name", _FIXTURES)
def test_run_fixture_same_opid_survives_regardless_of_response_size(fixture_name, settings, request):
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        op_id = str(uuid.uuid4())
        payload = {
            "action": "run_fixture",
            "testToken": scn.settings.get("testToken") or "",
            "fixture": fixture_name,
            "testDocId": scn.doc_id,
            "opId": op_id,
        }

        # First call: computes the response and attempts (best-effort) to
        # cache it under op_id. Must never 500 regardless of response size.
        resp1 = scn._post(payload)
        assert resp1.get("tag") == f"fixture.{fixture_name}", (
            f"[p9ra] {fixture_name} first call did not return the expected "
            f"tag -- got {resp1!r}"
        )

        # Simulated retry: same opId, same call -- what _http_post does when
        # the first response never reaches the client. Whether this hits the
        # opId cache or (post-fix, on an oversized first response) re-executes
        # the fixture from scratch, both outcomes are valid JSON for these
        # read-only whole-sheet/Drive audits -- the AC is "never throws an
        # uncaught exception", not "always cache-hits".
        resp2 = scn._post(payload)
        assert resp2.get("tag") == f"fixture.{fixture_name}", (
            f"[p9ra] {fixture_name} same-opId retry did not return the "
            f"expected tag -- got {resp2!r}"
        )
    finally:
        scn.engine.close()
