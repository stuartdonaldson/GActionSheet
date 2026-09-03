"""test_webapp_unrecognized_action.py — regression coverage for gts-c7fp
(doPost's terminal else-branch used to write junk rows for any unrecognised
secret-gated action).

Restored under gts-e34d after the original content was left as a
`# placeholder — see below; will be overwritten` stub (never committed —
`git log` shows no history for this file) and consequently collected zero
tests. gts-c7fp's own close reason names this file and this test name as
having "proved the fix live against TEST", so the coverage this bead
restores is not new — it is what should already have been here.

Scope note: gts-c7fp AC (1) asks for two things — a named JSON error, and
"writes nothing". This test asserts the first directly. It does NOT
re-assert "writes nothing" via a live sheet-row-count diff: doing that
would require a new GAS-side read route (out of scope for a test-only
bead — the fallthrough writes to `SpreadsheetApp.getActiveSpreadsheet()
.getActiveSheet()`, an arbitrary tab with no existing route that reports
its row count), and would couple this test to the shared, mutable TEST
spreadsheet exactly the way the original incident describes (SyncState!
A912:A932 junk rows). The response-shape assertion below is still a
faithful regression guard: the legacy buggy branch returned a bare
plain-text 'ok' body, never JSON, so any regression back to it fails
here on the JSON-decode / shape check alone, without needing a doc or
sheet-state fixture at all.

No live doc/session needed -- this hits doPost's routing dispatch, which
runs before any per-document logic, so `scn.session._http_post` is called
directly against `webappTestUrl` (module-level, no ScenarioSession /
new_doc overhead). Not marked `no_live_session`: it is a real network call
against the deployed TEST WebApp.
"""
import pytest

from scn.session import FixtureError, _http_post


def test_unrecognized_secret_gated_action_writes_nothing(settings):
    if not settings.get("webappSecret"):
        pytest.skip("local.settings.json missing webappSecret — cannot drive the secret gate")

    action = "definitely_not_a_real_action_gts_c7fp"
    payload = {"secret": settings["webappSecret"], "action": action}

    # _http_post raises FixtureError itself when the response carries an
    # "error" key (scn/session.py) -- the JSON-shape check IS the assertion
    # that the legacy plain-text 'ok' fallthrough is gone: that body was
    # never JSON, so this would fail as an unparseable response instead of a
    # clean FixtureError if the regression ever came back.
    with pytest.raises(FixtureError, match=f"unknown action: {action}"):
        _http_post(settings["webappTestUrl"], payload)
