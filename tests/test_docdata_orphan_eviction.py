"""
test_docdata_orphan_eviction.py — gts-avvl (was gts-30cq; stage
`sync-docdata-walk`, knowledge-base/staging/portal-perf-harness.md).

**This file's assertions were inverted on 2026-09-02.** gts-30cq widened
`ArchiveManager._evictStaleDocData` (src/ArchiveManager.js) from
(`syncStatus === 'Doc Not Found'` AND no Actions row) to (no Actions row), on
the premise that a DocData row with no Actions row is unreachable litter. That
premise was falsified twice over:

  1. gts-qkev made `syncAll` walk DocData directly, so such a row is no longer
     unreachable -- it is visited every sweep, its counts reconciled, and it is
     marked "Doc Not Found" if the document is actually gone.
  2. ADR-0031's 2026-09-01 amendment states the invariant outright: *a DocData
     row with no live Actions rows is a normal state (a tracked document with
     no open actions), not an integrity problem.* The Team Portal
     scan-and-track flow then began minting exactly such rows.

The widened predicate destroyed three of the operator's freshly-tracked
documents on the next sync (gts-avvl, live incident 2026-09-02, Axiom op
1ed56163-83a7-4e7b-b686-919fb9274dea). The two tests below pin both halves of
the corrected predicate so it cannot widen again:

  - AC-1 (survival): absence of Actions rows is NOT an eviction signal.
  - AC-2 (no regression): "Doc Not Found" + no Actions rows still IS one.

`_getOrUpsertDocDataRow` performs no Drive lookup, so a synthetic fileId is a
legitimate no-Actions-row DocData row the instant it is written.
"""
import uuid

import pytest

from scn.session import ScenarioSession


@pytest.fixture
def scn(settings, request):
    s = ScenarioSession.new_doc(settings, request=request)
    yield s
    s.close()


def _docdata_file_ids(scn):
    resp = scn._post_fixture("get_all_docdata_rows")
    return {r.get("fileId") for r in ((resp.get("data") or {}).get("rows") or [])}


def test_never_actioned_docdata_row_survives_archive_sweep(scn):
    """[gts-avvl AC-1] A DocData row with no Actions rows and a blank
    syncStatus -- the shape a Team Portal scan-and-track registration has
    before its first sweep -- must survive an archive sweep untouched."""
    newborn_file_id = f"GTS-newborn-{uuid.uuid4().hex[:12]}"

    scn._post_fixture(
        "set_docdata_row",
        {
            "fileId": newborn_file_id,
            "docName": "newborn registration probe",
            "syncStatus": "",
            "actionCount": 0,
            "resolvedCount": 0,
        },
    )
    assert newborn_file_id in _docdata_file_ids(scn), (
        f"[gts-avvl AC-1] seed row {newborn_file_id!r} not found after set_docdata_row"
    )

    # gts-avvl AC-4: drive the MENU entry point (MenuHandler.js:285
    # menuRunArchive), not ArchiveManager.archive() directly. That call site is
    # ungated -- unlike SyncManager.js:575, which only reaches archive() when
    # alreadyDocNotFound is non-empty -- so under the widened predicate it
    # destroyed registrations unconditionally on every menu Archive. The entry
    # point itself is the call-site here, per CLAUDE.md's entry-point invariant.
    scn._post_fixture("menu_run_archive")

    assert newborn_file_id in _docdata_file_ids(scn), (
        f"[gts-avvl AC-1] DocData row {newborn_file_id!r} (blank syncStatus, no "
        f"Actions rows -- a never-scanned registration) was EVICTED by the "
        f"archive sweep. Absence of Actions rows is not an eviction signal "
        f"(ADR-0031 amendment 2026-09-01); the predicate has widened again."
    )


def test_doc_not_found_docdata_row_is_still_evicted(scn):
    """[gts-avvl AC-2] The behaviour the predicate exists for does not regress:
    a DocData row marked 'Doc Not Found' with no Actions rows referencing it is
    still evicted by the archive sweep. Drives ArchiveManager.archive() via
    `archive_journey` -- the mechanism -- so the two tests together cover the
    menu call site and the predicate itself."""
    gone_file_id = f"GTS-gone-{uuid.uuid4().hex[:12]}"

    scn._post_fixture(
        "set_docdata_row",
        {
            "fileId": gone_file_id,
            "docName": "doc-not-found eviction probe",
            "syncStatus": "Doc Not Found",
            "actionCount": 0,
            "resolvedCount": 0,
        },
    )
    assert gone_file_id in _docdata_file_ids(scn), (
        f"[gts-avvl AC-2] seed row {gone_file_id!r} not found after set_docdata_row"
    )

    scn._post_fixture("archive_journey")

    assert gone_file_id not in _docdata_file_ids(scn), (
        f"[gts-avvl AC-2] DocData row {gone_file_id!r} (syncStatus='Doc Not "
        f"Found', no Actions rows) survived the archive sweep -- the eviction "
        f"path this predicate exists for has regressed."
    )
