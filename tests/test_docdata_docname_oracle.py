"""
test_docdata_docname_oracle.py — gts-axll (stage `docdata-oracle`,
knowledge-base/staging/docdata-litter-apt-speed.md).

A 2026-08-29 read-only pull of the live TEST spreadsheet found DocData's Doc
Name column silently degrading from a live `=HYPERLINK(...)` formula to
flattened plain text (`ArchiveManager._evictStaleDocData`, src/ArchiveManager.js,
reads with getValues() and writes back with setValues() -- unlike
`_archiveActionsRows` 80 lines above, which merges getFormulas()/getValues()
correctly), plus rows whose Doc Name is permanently blank (a sticky default
from `seed_row`-manufactured Actions rows with an empty Document column,
propagated with no fallback by WebApp.js).

No existing assertion can see either defect: tests/test_sync_all.py:690 reads
through get_docdata_row -> _readDocDataRow (src/SyncManager.js), which only
ever calls getValues() on the Doc Name cell -- structurally identical output
for a formula and its display string. This test adds the read path that can
tell them apart (get_all_docdata_rows -> getFormulas(), gts-axll) and the
assertion neither existing test makes.

Expected to fail red against the live TEST sheet until gts-t9f9 (eviction
flattens the HYPERLINK) and gts-pz8o (blank Doc Name never backfilled) land --
that failure is this bead's acceptance criterion, not a bug in the test.

gts-u947 (stage `regression-verify`, 2026-09-01): the first live full-sweep
run of this test caught 4 blank-Doc-Name rows. Diagnosis split them into two
distinct classes that this test now treats differently:

  - 3/4 had a live Actions row (real docName text, written moments earlier)
    -- re-reading the sheet a few minutes later, with no code/deploy change,
    showed the correct name. That is a Sheets write->read propagation lag
    across separate GAS executions (same failure family as gas_log.py's
    wait_for_log Axiom-ingestion-lag handling), unrelated to the sync
    operation under test. A single-read assertion can't distinguish this
    from a real defect, so it now gets a bounded, fast-when-clean poll
    instead of a hard single-read assertion.
  - 1/4 had NO Actions row at all (docNameFormula's own display-text arg was
    literally `""`) -- an unrepairable orphan gts-pz8o's fix cannot reach
    (nothing to backfill a name from). That case fails immediately, with no
    retry, since waiting cannot help it; the fix is eviction
    (ArchiveManager.archive() / the purge_stale_test_docs fixture), not a
    later read.
"""
import re
import time

import pytest

from scn.session import ScenarioSession

_HYPERLINK_RE = re.compile(r"^=HYPERLINK\(", re.IGNORECASE)

# Bounded poll for the transient (Actions-row-backed) blank-name case only.
# Fast when the sheet is already consistent (loop body never runs); bounded
# so a real, persistent defect still fails within a reasonable window.
_BLANK_RETRY_TIMEOUT_S = 60
_BLANK_RETRY_POLL_S = 3


@pytest.fixture
def scn(settings, request):
    # request=request wires JUnit ac.*/ep.* emission to this test node (T24).
    # TestFixtures.js's dispatcher opens testDocId unconditionally before the
    # fixture switch, so a doc is required even though get_all_docdata_rows
    # itself ignores testDocId and reads the whole DocData sheet.
    s = ScenarioSession.new_doc(settings, request=request)
    yield s
    s.close()


def _read_docdata(scn):
    """One read of DocData, split into (flattened, blank) fileId lists."""
    resp = scn._post_fixture("get_all_docdata_rows")
    rows = (resp.get("data") or {}).get("rows") or []

    flattened = []
    blank = []
    for row in rows:
        file_id = row.get("fileId")
        doc_name = row.get("docName") or ""
        formula = row.get("docNameFormula") or ""
        if not doc_name.strip():
            blank.append(file_id)
        elif not _HYPERLINK_RE.match(formula):
            flattened.append(file_id)
    return rows, flattened, blank


def test_docdata_docname_is_live_hyperlink_and_nonblank(scn):
    """Every DocData row's Doc Name must be a live HYPERLINK formula, and non-blank.

    Distinguishes a live HYPERLINK from its flattened display text (both read
    from the same row via get_all_docdata_rows) and flags any row whose Doc
    Name is blank -- the two defects docdata-litter-apt-speed.md's Evidence
    table documents as 147 flattened rows and 17 (13 unrepairable) blank rows
    in the 2026-08-29 snapshot.
    """
    rows, flattened, blank = _read_docdata(scn)
    assert rows, "expected the live TEST DocData sheet to have at least one row"

    assert not flattened, (
        f"{len(flattened)} DocData row(s) have a non-blank Doc Name that is NOT "
        f"a live HYPERLINK formula (flattened to display text by "
        f"ArchiveManager._evictStaleDocData, gts-t9f9): {flattened[:10]}"
        f"{' ...' if len(flattened) > 10 else ''}"
    )

    if not blank:
        return

    # Split blanks: a row backed by no *active* Actions row -- either none
    # at all, or every one already Doc Not Found/Deleted -- has nothing for
    # gts-pz8o's fix to ever backfill from. gts-pz8o's backfill
    # (docTitleByDocId in SyncManager.js) lives only inside syncAll()'s
    # whole-sheet integrity pass, not per-doc syncDocument() -- a doc whose
    # only Actions rows are already Doc Not Found is excluded from that
    # pass's integrityCounts and, on a session where no syncAll() sweep has
    # run yet (this suite's own collection order can reach this oracle
    # before tests/test_sync_all.py), simply never gets visited. Such a row
    # cannot self heal via backfill -- its actionCount is 0, so it is
    # ordinary 24h-gated litter (gts-30cq) headed for eviction, not a doc
    # that needs a name. Fail immediately rather than burning the retry
    # budget on something no amount of waiting can fix.
    #
    # gts-u947 (stage regression-verify): this used to pull the WHOLE Actions
    # sheet via dump_all_action_rows -- overkill for checking a handful of
    # specific fileIds, and it surfaced a real dispatcher-level bug
    # (_handleRunFixture's opId dedupe cache hitting CacheService's ~100KB
    # value cap on a large live corpus, "Argument too large: value" at
    # TestWebApp.js:133 -- fixed separately by guarding that cache write).
    # Scoped per-fileId lookups via the find_sheet_actions webapp route (not
    # run_fixture, so not subject to that cache path at all) avoid both the
    # oversized-payload risk and the unnecessary whole-sheet cost.
    _INACTIVE_STATUSES = ("Doc Not Found", "Deleted")
    active_file_ids = set()
    for f in blank:
        resp = scn._post_route("find_sheet_actions", {"docId": f}) or {}
        rows = resp.get("rows") or []
        if any(r.get("sync_status") not in _INACTIVE_STATUSES for r in rows):
            active_file_ids.add(f)

    orphaned_blank = [f for f in blank if f not in active_file_ids]
    assert not orphaned_blank, (
        f"{len(orphaned_blank)} DocData row(s) have a blank Doc Name and no "
        f"ACTIVE referencing Actions row (either none at all, or every one "
        f"already Doc Not Found/Deleted) -- an unrepairable orphan (nothing "
        f"for gts-pz8o's fix to backfill a name from; syncAll()'s integrity "
        f"pass excludes Doc Not Found/Deleted rows from its backfill scan). "
        f"Evict via ArchiveManager.archive() / the purge_stale_test_docs "
        f"fixture: {orphaned_blank[:10]}{' ...' if len(orphaned_blank) > 10 else ''}"
    )

    # Every remaining blank has a live Actions row -- give normal Sheets
    # write->read propagation a bounded window to catch up before treating
    # it as the sticky-default defect.
    deadline = time.time() + _BLANK_RETRY_TIMEOUT_S
    while blank and time.time() < deadline:
        time.sleep(_BLANK_RETRY_POLL_S)
        rows, flattened, blank = _read_docdata(scn)
        assert not flattened, (
            f"{len(flattened)} DocData row(s) have a non-blank Doc Name that is "
            f"NOT a live HYPERLINK formula (flattened to display text by "
            f"ArchiveManager._evictStaleDocData, gts-t9f9), surfaced during the "
            f"blank-name retry poll: {flattened[:10]}"
            f"{' ...' if len(flattened) > 10 else ''}"
        )

    assert not blank, (
        f"{len(blank)} DocData row(s) still have a blank Doc Name after "
        f"{_BLANK_RETRY_TIMEOUT_S}s of polling (each has a live Actions row, "
        f"so this is not the orphan case) -- either a persistent write->read "
        f"lag beyond the retry budget or a genuine regression of the "
        f"sticky-default defect (gts-pz8o): {blank[:10]}"
        f"{' ...' if len(blank) > 10 else ''}"
    )
