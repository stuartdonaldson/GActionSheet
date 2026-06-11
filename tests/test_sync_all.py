"""
test_sync_all.py — GTaskSheet-r3d/grxl/5u2v/nv6g

One scenario: seed a mixed ActionSheet (invalid-doc, trashed-doc, unmodified-valid,
modified-valid rows), run syncAll ONCE (Sweep 1), drain per-condition expectations,
then run syncAll a SECOND time (Sweep 2) to verify Doc Not Found rows are archived.

All four beads map to expectations on the same two sweeps (§6 permutation batching).

Archive eligibility (ArchiveManager): (Status='Closed' OR Sync Status='Doc Not Found')
AND Date Modified > 30 days old. The invalid-doc row is seeded with a 35-day-old
dateModified so it is immediately eligible for archiving on Sweep 2. The trashed-doc
row is created today via sync, so it remains in Actions under the 30-day grace period —
this is correct behaviour (a recently trashed doc should not be immediately archived).
"""
import datetime
import secrets
import pytest

from scn.session import ScenarioSession
from scn.surfaces import SheetReader
from tests.helpers.download import download_xlsx

_35_DAYS_AGO = (
    datetime.datetime.utcnow() - datetime.timedelta(days=35)
).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sheet_rows_for(settings: dict, doc_id: str) -> list:
    """Download ActionSheet and return rows scoped to doc_id (Actions tab)."""
    xlsx = download_xlsx(settings["testSheetId"])
    return SheetReader().read(xlsx, doc_id)


def _archive_rows_for(settings: dict, doc_id: str) -> list:
    """Download ActionSheet and return rows scoped to doc_id (Archive tab)."""
    xlsx = download_xlsx(settings["testSheetId"])
    return SheetReader().read(xlsx, doc_id, tab_name="Archive")


@pytest.fixture(scope="module")
def sync_ctx(settings):
    """Set up the mixed ActionSheet; yield context; teardown trashes all journey docs.

    Setup order:
      1. scn_mod: create doc, append action, sync, then append more (modified-valid)
      2. scn_unmod: create doc, append action, sync, no further mutation (unmodified-valid)
      3. scn_trash: create doc, append action, sync, then trash the doc (trashed)
      4. Seed one invalid-doc row via seed_row fixture

    The invalid docId is unique per session (secrets.token_urlsafe) to prevent
    accumulated rows from previous test runs bleeding into this session's assertions.
    """
    # Unique-per-session fake docId (44 URL-safe chars, will never resolve in Drive).
    invalid_doc_id = secrets.token_urlsafe(33)[:44]

    scn_mod = ScenarioSession.new_doc(settings)
    scn_unmod = ScenarioSession.new_doc(settings)
    scn_trash = ScenarioSession.new_doc(settings)

    # modified-valid: sync once to create sheet row, then add more content
    scn_mod.append_paragraph("AI-1: syncall modified valid action")
    scn_mod.sync()
    scn_mod.append_paragraph("AI-2: additional action added after sync — marks doc modified")

    # unmodified-valid: sync once, no further mutation
    scn_unmod.append_paragraph("AI-1: syncall unmodified valid action")
    scn_unmod.sync()

    # to-be-trashed: sync once to create sheet row, then trash the doc
    scn_trash.append_paragraph("AI-1: syncall trashed doc action")
    scn_trash.sync()
    trashed_id = scn_trash.doc_id
    scn_trash._post_fixture("trash_doc")   # trashes scn_trash.doc_id (= testDocId for this call)

    # invalid-doc: seed a raw row with an unreachable docId and 35-day-old dateModified
    # so it is immediately eligible for archiving on Sweep 2 (ArchiveManager threshold = 30 days).
    invalid_formula = (
        f'=HYPERLINK("https://docs.google.com/document/d/{invalid_doc_id}/edit","Invalid Doc")'
    )
    scn_mod._post_fixture("seed_row", {
        "actionId": "INVALID-1",
        "actionText": "syncall invalid doc seeded action",
        "status": "Open",
        "documentFormula": invalid_formula,
        "dateModified": _35_DAYS_AGO,
    })

    yield {
        "settings": settings,
        "scn_mod": scn_mod,
        "scn_unmod": scn_unmod,
        "modified_id": scn_mod.doc_id,
        "unmodified_id": scn_unmod.doc_id,
        "trashed_id": trashed_id,
        "invalid_id": invalid_doc_id,
    }

    # Teardown: end journey sessions (trashes the docs)
    for scn in (scn_mod, scn_unmod):
        try:
            scn._post_route("end_journey_session", {"docId": scn.doc_id})
        except Exception:
            pass
    # scn_trash doc is already trashed; engine has no enqueued expectations, so skip close()


def test_sync_all(sync_ctx):
    settings = sync_ctx["settings"]
    scn_mod = sync_ctx["scn_mod"]
    scn_unmod = sync_ctx["scn_unmod"]
    modified_id = sync_ctx["modified_id"]
    unmodified_id = sync_ctx["unmodified_id"]
    trashed_id = sync_ctx["trashed_id"]
    invalid_id = sync_ctx["invalid_id"]

    # ── Pre-sweep baseline ───────────────────────────────────────────────────
    # unmodified doc: 1 row in Actions, no sync_status
    pre_unmod = _sheet_rows_for(settings, unmodified_id)
    assert len(pre_unmod) >= 1, "[5u2v pre] expected ≥1 row for unmodified doc before syncAll"

    # invalid doc row exists in Actions before sweep
    pre_invalid = _sheet_rows_for(settings, invalid_id)
    assert len(pre_invalid) >= 1, "[r3d pre] seeded invalid-doc row not found before syncAll"

    # ── Sweep 1 ──────────────────────────────────────────────────────────────
    # sync_all fixture calls syncAll() on the production sheet — all rows are processed.
    # Use scn_mod._post_fixture (testDocId = scn_mod.doc_id) but sync_all ignores testDocId.
    scn_mod._post_fixture("sync_all")

    # [r3d] invalid doc → Sync Status = 'Doc Not Found'
    invalid_s1 = _sheet_rows_for(settings, invalid_id)
    assert len(invalid_s1) >= 1, (
        "[r3d] invalid-doc row disappeared from Actions after Sweep 1 (expected Doc Not Found)"
    )
    for row in invalid_s1:
        assert getattr(row, "sync_status", None) == "Doc Not Found", (
            f"[r3d] invalid-doc row: expected 'Doc Not Found', got {row.sync_status!r}"
        )

    # [grxl] trashed doc → Sync Status = 'Doc Not Found'
    # Both paths (inaccessible + trashed) produce the same durable status.
    # The trashed-path is disambiguated by err='Document is in Trash' in GAS logs,
    # not by a distinct sync_status — so we assert the durable outcome only.
    trashed_s1 = _sheet_rows_for(settings, trashed_id)
    assert len(trashed_s1) >= 1, (
        "[grxl] trashed-doc row disappeared from Actions after Sweep 1 (expected Doc Not Found)"
    )
    for row in trashed_s1:
        assert getattr(row, "sync_status", None) == "Doc Not Found", (
            f"[grxl] trashed-doc row: expected 'Doc Not Found', got {row.sync_status!r}"
        )

    # [zc21] DocData mirrors 'Doc Not Found' and keeps Team Id consistent with
    # the document's actual teamScope appProperty.
    trashed_docdata = (scn_mod._post_fixture("get_docdata_row", {"fileId": trashed_id})
                        .get("data") or {}).get("row")
    assert trashed_docdata is not None, (
        "[zc21] trashed-doc DocData row missing after Sweep 1"
    )
    assert trashed_docdata.get("syncStatus") == "Doc Not Found", (
        f"[zc21] trashed-doc DocData.sync_status: expected 'Doc Not Found', "
        f"got {trashed_docdata.get('syncStatus')!r}"
    )
    trashed_team_scope = (scn_mod._post_fixture("get_team_scope", {"docId": trashed_id})
                           .get("data") or {}).get("teamScope", "")
    assert trashed_docdata.get("teamId", "") == trashed_team_scope, (
        f"[zc21] trashed-doc DocData.team_id ({trashed_docdata.get('teamId')!r}) "
        f"!= teamScope appProperty ({trashed_team_scope!r})"
    )

    # [zc21] invalid doc never had a DocData row before sync_all — one is
    # created on first 'Doc Not Found' mark, with an empty Team Id.
    invalid_docdata = (scn_mod._post_fixture("get_docdata_row", {"fileId": invalid_id})
                        .get("data") or {}).get("row")
    assert invalid_docdata is not None, (
        "[zc21] invalid-doc DocData row not created after Sweep 1"
    )
    assert invalid_docdata.get("syncStatus") == "Doc Not Found", (
        f"[zc21] invalid-doc DocData.sync_status: expected 'Doc Not Found', "
        f"got {invalid_docdata.get('syncStatus')!r}"
    )
    assert invalid_docdata.get("teamId", "") == "", (
        f"[zc21] invalid-doc DocData.team_id: expected '', got {invalid_docdata.get('teamId')!r}"
    )

    # [5u2v] unmodified valid doc → row count unchanged; NOT marked Doc Not Found
    post_unmod_s1 = _sheet_rows_for(settings, unmodified_id)
    for row in post_unmod_s1:
        assert getattr(row, "sync_status", None) != "Doc Not Found", (
            f"[5u2v] unmodified-valid doc incorrectly marked Doc Not Found: {row.sync_status!r}"
        )

    # modified valid doc → NOT marked Doc Not Found (may have new rows from AI-2)
    mod_s1 = _sheet_rows_for(settings, modified_id)
    for row in mod_s1:
        assert getattr(row, "sync_status", None) != "Doc Not Found", (
            f"[5u2v] modified-valid doc marked Doc Not Found unexpectedly: {row.sync_status!r}"
        )

    # ── Sweep 2 (nv6g) ───────────────────────────────────────────────────────
    # Second sweep: Doc Not Found rows from Sweep 1 are now in alreadyDocNotFound set
    # → ArchiveManager.archive() moves them from Actions to Archive sheet.
    scn_mod._post_fixture("sync_all")

    # [nv6g] invalid-doc row → archived (dateModified 35 days ago, eligible immediately)
    invalid_archived = _archive_rows_for(settings, invalid_id)
    assert len(invalid_archived) >= 1, (
        "[nv6g] invalid-doc row not found in Archive after Sweep 2 "
        "(expected: Doc Not Found + dateModified > 30 days → archived)"
    )
    invalid_actions_s2 = _sheet_rows_for(settings, invalid_id)
    assert len(invalid_actions_s2) == 0, (
        f"[nv6g] invalid-doc row still in Actions after archive sweep "
        f"(expected 0, got {len(invalid_actions_s2)})"
    )

    # [nv6g §grace] trashed-doc row → still in Actions (dateModified = today, < 30 days)
    # The 30-day grace period prevents immediate archiving of a recently trashed doc.
    trashed_actions_s2 = _sheet_rows_for(settings, trashed_id)
    assert len(trashed_actions_s2) >= 1, (
        "[nv6g §grace] trashed-doc row should still be in Actions under 30-day grace period"
    )
    for row in trashed_actions_s2:
        assert getattr(row, "sync_status", None) == "Doc Not Found", (
            f"[nv6g §grace] trashed-doc row should remain 'Doc Not Found' in Actions, "
            f"got {row.sync_status!r}"
        )

    # [nv6g §7] Valid doc rows unaffected by either sweep
    mod_s2 = _sheet_rows_for(settings, modified_id)
    for row in mod_s2:
        assert getattr(row, "sync_status", None) != "Doc Not Found", (
            f"[nv6g §7] modified-valid doc incorrectly archived or marked: {row.sync_status!r}"
        )
    unmod_s2 = _sheet_rows_for(settings, unmodified_id)
    for row in unmod_s2:
        assert getattr(row, "sync_status", None) != "Doc Not Found", (
            f"[nv6g §7] unmodified-valid doc incorrectly archived or marked: {row.sync_status!r}"
        )
