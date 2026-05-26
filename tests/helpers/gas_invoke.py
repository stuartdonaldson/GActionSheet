"""Helpers for invoking GAS functions via the Google Sheet custom menu (Playwright)."""
import json
import pathlib
import subprocess

_SCRIPT       = pathlib.Path(__file__).parent.parent / "playwright" / "invoke_gas.js"
_BATCH_SCRIPT = pathlib.Path(__file__).parent.parent / "playwright" / "invoke_gas_batch.js"


def _invoke(menu_item: str, arg: str | None = None, timeout: int = 60,
            parent: str | None = None) -> None:
    cmd = ["node", str(_SCRIPT), menu_item]
    if arg is not None:
        cmd.append(arg)
    if parent is not None:
        cmd.append(f"--parent={parent}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(
            f"invoke_gas failed for menu item {menu_item!r}:\n{result.stderr}"
        )


def bootstrap() -> None:
    _invoke("Bootstrap Test Properties", parent="Setup")


def ensure_sheet_structure() -> None:
    _invoke("Ensure Sheet Structure", parent="Setup")


def initialize_triggers() -> None:
    _invoke("Initialize Triggers", parent="Setup")


def setup_fixture(scenario: str) -> None:
    _invoke("Test: Setup Fixture", scenario)


def sync_document(doc_id: str) -> None:
    _invoke("Test: Sync Document", doc_id)


def sync_all() -> None:
    _invoke("Sync")


def insert_tracker_table(doc_id: str) -> None:
    """Invoke the Insert / refresh tracker action for the given doc.

    GAS runs the tracker renderer and logs tracker.refresh.complete with data.docId.
    """
    _invoke("Test: Insert Tracker Table", doc_id, timeout=120)


def run_archive() -> None:
    """Invoke the archive sweep (moves Closed rows older than 30 days to Archive sheet).

    GAS logs archive.complete when done.
    """
    _invoke("Test: Run Archive", timeout=120)


def debug_doc_body() -> None:
    _invoke("Test: Debug Doc Body")


def setup_and_sync(scenario: str, doc_id: str | None = None) -> None:
    """Set up a fixture and sync in a single GAS invocation.

    Args:
        scenario: Name of the fixture scenario to set up.
        doc_id: Unused at helper level (GAS reads from TEST_DOC_ID script property).
                Provided for explicitness when calling code.
    """
    _invoke("Test: Setup And Sync", scenario)


def begin_test_session(master_doc_id: str) -> None:
    """Clone the master template doc and set TEST_DOC_ID to the clone.

    GAS writes the clone ID to TestControl!B1 and logs session.begin.
    """
    _invoke("Test: Begin Session", master_doc_id, timeout=120)


def end_test_session() -> None:
    """Trash the clone and restore TEST_DOC_ID to the master template."""
    _invoke("Test: End Session", timeout=60)


def batch_invoke(commands: list[dict], timeout: int = 1800) -> dict:
    """Execute multiple GAS menu items in a single Playwright session.

    Each command dict keys:
      menuItem  (required) — menu item label
      arg       (optional) — value written to TestControl!A1 before the click
      parent    (optional) — submenu label to hover into first
      awaitTag  (optional) — NDJSON log tag to wait for before the next command
      timeoutMs (optional) — per-awaitTag timeout in ms (default 240000)

    Returns a dict mapping awaitTag → log entry for every command that had an
    awaitTag.  Commands without awaitTag are not represented.

    Opens exactly one Playwright browser session for the entire command list.
    """
    result = subprocess.run(
        ["node", str(_BATCH_SCRIPT)],
        input=json.dumps(commands),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"batch_invoke failed:\n{result.stderr}"
        )
    stdout = result.stdout.strip()
    return json.loads(stdout) if stdout else {}
