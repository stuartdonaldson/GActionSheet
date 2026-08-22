"""
test_f3me1_append_idempotency.py — gts-f3me.1 [TST]

Regression test for the duplicate-row bug diagnosed against gas-test3.log
(01:37-01:39): scn/session.py's _http_post retries append_doc_paragraph on
HTTP 404 / non-JSON-echo responses under the assumption the first attempt
never reached the GAS handler. When the handler actually succeeded and only
the *response* was lost to the /exec -> script.googleusercontent.com routing
glitch, a bare retry re-appended the same paragraph — producing a duplicate
Actions row once the doc was synced (test_team_portal_hardening.py's
module-scoped seeded_rows fixture hit this live).

Fix: WebApp.js's _handleAppendDocParagraph now dedupes on the client-supplied
opId (reused across all retry attempts of one logical call by _http_post, see
scn/session.py) via CacheService, within a TTL well above the retry loop's
worst case.

This test drives the real append_doc_paragraph route directly (not through
ScenarioSession.append_paragraph, which mints a fresh opId per call) so it can
simulate exactly the retry-after-lost-response scenario: two POSTs, same
opId, same text. Asserts the doc ends up with exactly one paragraph
containing the text.
"""
from scn.session import ScenarioSession


def test_append_doc_paragraph_same_opid_is_not_duplicated(settings, request):
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        text = f"gts-f3me1 idempotency-check {scn.doc_id[:8]}"
        fixed_op_id = f"gts-f3me1-retry-sim-{scn.doc_id}"

        # First attempt: as scn/session.py's _http_post would send it, carrying
        # a client-generated opId reused across retries.
        resp1 = scn._post_route(
            "append_doc_paragraph",
            {"testDocId": scn.doc_id, "text": text, "opId": fixed_op_id},
        )
        assert resp1.get("ok"), resp1

        # Simulated retry: same opId, same call — this is what _http_post does
        # when the first response never reaches the client despite the server
        # having already applied the write.
        resp2 = scn._post_route(
            "append_doc_paragraph",
            {"testDocId": scn.doc_id, "text": text, "opId": fixed_op_id},
        )
        assert resp2.get("ok"), resp2

        dump = scn._post_route("dump_doc_paragraphs", {"docId": scn.doc_id})
        matches = [el for el in dump["elements"] if text in el["text"]]
        assert len(matches) == 1, (
            f"expected exactly 1 paragraph for {text!r} after a same-opId retry, "
            f"got {len(matches)}: {[el['text'] for el in matches]}"
        )
    finally:
        scn.close()


def test_append_doc_paragraph_different_opid_is_not_deduped(settings, request):
    """Sanity check the guard is opId-scoped, not text-scoped: two genuinely
    distinct calls (different opId) for the same text must both apply."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        text = f"gts-f3me1 distinct-calls-check {scn.doc_id[:8]}"

        resp1 = scn._post_route(
            "append_doc_paragraph",
            {"testDocId": scn.doc_id, "text": text, "opId": f"gts-f3me1-a-{scn.doc_id}"},
        )
        assert resp1.get("ok"), resp1

        resp2 = scn._post_route(
            "append_doc_paragraph",
            {"testDocId": scn.doc_id, "text": text, "opId": f"gts-f3me1-b-{scn.doc_id}"},
        )
        assert resp2.get("ok"), resp2

        dump = scn._post_route("dump_doc_paragraphs", {"docId": scn.doc_id})
        matches = [el for el in dump["elements"] if text in el["text"]]
        assert len(matches) == 2, (
            f"expected 2 paragraphs for {text!r} from two distinct opIds, "
            f"got {len(matches)}: {[el['text'] for el in matches]}"
        )
    finally:
        scn.close()
