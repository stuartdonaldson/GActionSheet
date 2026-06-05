"""
Infrastructure tests for dd5: TriggerManager, MenuHandler, SheetSetup.
"""
import pathlib
import subprocess
import pytest

from tests.helpers.download import download_xlsx
from tests.helpers.sheet_inspect import load_sheet, headers
from tests.helpers.gas_log import clear_logs, wait_for_log
from tests.helpers import gas_invoke

_REPO_ROOT = pathlib.Path(__file__).parent.parent
_OPEN_SHEET_JS = _REPO_ROOT / "tests" / "playwright" / "open_sheet.js"

# Expected column orders (1-based positions must match this exact left-to-right sequence)
ACTIONS_HEADERS = [
    "globalId",
    "ID",
    "Assignee Email",
    "Assignee Name",
    "Action",
    "Status",
    "Document",
    "Date Created",
    "Date Modified",
]

ARCHIVE_HEADERS = [
    "globalId",
    "ID",
    "Assignee Email",
    "Assignee Name",
    "Action",
    "Status",
    "Document",
    "Date Created",
    "Date Modified",
]


# ---------------------------------------------------------------------------
# TriggerManager
# ---------------------------------------------------------------------------

class TestInitializeTriggers:
    """dd5 / TriggerManager: idempotency guarantee."""

    def test_initialize_triggers_is_idempotent(self, test_sheet_id, gas_log_dir):
        """Calling initializeTriggers() twice must result in exactly 1 onEdit trigger
        and exactly 1 time-based trigger — not 2 of each."""
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        # First call
        fence1 = clear_logs(gas_log_dir)
        gas_invoke.initialize_triggers()
        entry1 = wait_for_log(
            gas_log_dir,
            lambda e: e.get("tag") == "triggers.initialized",
            timeout_s=30,
            after=fence1,
        )

        # Second call — idempotency check
        fence2 = clear_logs(gas_log_dir)
        gas_invoke.initialize_triggers()
        entry2 = wait_for_log(
            gas_log_dir,
            lambda e: e.get("tag") == "triggers.initialized",
            timeout_s=30,
            after=fence2,
        )

        # The log entry on the second call must report exactly 1 onEdit + 1 time-based
        assert entry2["data"]["onEditCount"] == 1, (
            f"Expected 1 onEdit trigger after idempotent init, got {entry2['data']['onEditCount']}"
        )
        assert entry2["data"]["timeBasedCount"] == 1, (
            f"Expected 1 time-based trigger after idempotent init, "
            f"got {entry2['data']['timeBasedCount']}"
        )


# ---------------------------------------------------------------------------
# SheetSetup — header layout
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def sheet_structure_ready(settings):
    """Ensure the ActionSheet has the correct layout before header tests.

    Uses HTTP fixture invocation — no browser required.
    """
    from tests.helpers.fixture_invoke import invoke_fixture
    invoke_fixture("ensure_sheet_structure", settings["testDocId"], settings, timeout=60)


class TestSheetHeaders:
    """dd5 / SheetSetup: sheet tabs and header columns are created correctly."""

    def test_actions_sheet_headers(self, test_sheet_id):
        """'Actions' tab must exist with the required headers in exact left-to-right order."""
        xlsx = download_xlsx(test_sheet_id)
        ws = load_sheet(xlsx, sheet_name="Actions")
        actual = headers(ws)  # {header_name: col_index}

        # All required headers must be present
        missing = [h for h in ACTIONS_HEADERS if h not in actual]
        assert not missing, f"Actions tab missing headers: {missing}"

        # Headers must appear in the declared order (col indices must be strictly ascending)
        col_positions = [actual[h] for h in ACTIONS_HEADERS]
        assert col_positions == sorted(col_positions), (
            f"Actions headers are not in the expected order. "
            f"Got positions: {list(zip(ACTIONS_HEADERS, col_positions))}"
        )

    def test_archive_sheet_headers(self, test_sheet_id):
        """'Archive' tab must exist with the required headers in exact left-to-right order."""
        xlsx = download_xlsx(test_sheet_id)
        ws = load_sheet(xlsx, sheet_name="Archive")
        actual = headers(ws)

        missing = [h for h in ARCHIVE_HEADERS if h not in actual]
        assert not missing, f"Archive tab missing headers: {missing}"

        col_positions = [actual[h] for h in ARCHIVE_HEADERS]
        assert col_positions == sorted(col_positions), (
            f"Archive headers are not in the expected order. "
            f"Got positions: {list(zip(ARCHIVE_HEADERS, col_positions))}"
        )


# ---------------------------------------------------------------------------
# MenuHandler
# ---------------------------------------------------------------------------

class TestMenuHandler:
    """dd5 / MenuHandler: custom menu is registered on open."""

    def test_menu_item_exists(self):
        """onOpen() must register the Action Sync custom menu — verified by UI presence.
        Note: simple triggers cannot write to Drive, so log-based verification is not possible."""
        result = subprocess.run(["node", str(_OPEN_SHEET_JS)], cwd=str(_REPO_ROOT))
        assert result.returncode == 0, (
            "Action Sync menu not found after sheet opened — onOpen() did not run or failed"
        )
