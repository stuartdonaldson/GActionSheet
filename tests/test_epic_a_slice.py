"""
EPIC-A slice smoke — GTaskSheet-5r4l.2 (ADR-0013 Slice fidelity).

Two durable invariants ONLY (staging contract §Smoke spec):
  (a) round-trip: DocData rows written then read back are identical (non-date columns).
  (b) single resolved authority: Resolved Count values are produced by isResolved();
      no second status-set definition exists in the slice GAS code.

Volatile surface (column order, exact date values, full auto-assignment, UpdateDoc
write-back matrix) is NOT asserted here — frozen at the freeze gate (5r4l.3).
"""
import pathlib
import re
import pytest

from tests.helpers.fixture_invoke import invoke_fixture

_REPO_ROOT = pathlib.Path(__file__).parent.parent
_GAS_SRC   = _REPO_ROOT / "src"


@pytest.fixture(scope="module")
def slice_result(settings, test_doc_id):
    """Invoke the team_data_slice fixture once; all smoke tests share the result."""
    return invoke_fixture("team_data_slice", test_doc_id, settings, timeout=120)


class TestEpicASliceRoundTrip:
    """Smoke (a): DocData rows survive a write-then-read-back cycle intact."""

    def test_no_round_trip_diff(self, slice_result):
        data = slice_result["data"]
        diff = data.get("roundTripDiff", [])
        assert diff == [], (
            f"DocData round-trip produced {len(diff)} mismatch(es): {diff}"
        )

    def test_expected_row_counts(self, slice_result):
        data = slice_result["data"]
        assert data["teamDataRows"] == 3, "Expected 3 TeamData sample rows"
        assert data["docDataRows"]  == 3, "Expected 3 DocData sample rows"


class TestEpicASliceResolvedAuthority:
    """Smoke (b): Resolved Count uses isResolved() as the single authority."""

    def test_resolved_counts_match_expected(self, slice_result):
        # Action-status sets from the fixture (must mirror TestFixtures.js slice rows):
        #   row 1: [Done, Open]  → 1 resolved
        #   row 2: [Open]        → 0 resolved
        #   row 3: [Closed]      → 1 resolved
        expected = [1, 0, 1]
        actual = slice_result["data"]["resolvedCounts"]
        assert actual == expected, (
            f"Resolved counts via isResolved() expected {expected}, got {actual}"
        )

    def test_no_inline_status_set_in_slice_fixture(self):
        """Static: the team_data_slice case must not define its own resolved-status set.

        Allowed pattern: isResolved() calls only.
        Disallowed pattern: inline arrays/constants like ['Done','Closed'] or
        ['Done', 'Closed'] that would shadow or duplicate the shared authority.
        """
        fixture_src = (_GAS_SRC / "TestFixtures.js").read_text()

        # Locate the team_data_slice case block.
        match = re.search(
            r"case 'team_data_slice'\s*:\s*\{(.+?)(?=\n\s+case |\n\s+default\s*:)",
            fixture_src,
            re.DOTALL,
        )
        assert match, "Could not locate 'team_data_slice' case in TestFixtures.js"
        slice_block = match.group(1)

        # No inline resolved-status array (e.g. ['Done', 'Closed'] / ["Done","Closed"]).
        inline_set = re.search(
            r"""['"][Dd]one['"][,\s]+['"][Cc]losed['"]|['"][Cc]losed['"][,\s]+['"][Dd]one['"]""",
            slice_block,
        )
        assert inline_set is None, (
            "team_data_slice case contains an inline resolved-status set — "
            "use isResolved() exclusively. "
            f"Found: {inline_set.group()!r}"
        )

    def test_is_resolved_helper_exists_in_sync_manager(self):
        """isResolved() must be defined in SyncManager.js (the shared authority)."""
        sync_src = (_GAS_SRC / "SyncManager.js").read_text()
        assert "function isResolved(" in sync_src, (
            "isResolved() is not defined in SyncManager.js"
        )
