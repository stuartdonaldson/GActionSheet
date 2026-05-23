"""Helpers for invoking the Workspace Add-on sidebar via Playwright (Node.js)."""
import json
import pathlib
import subprocess

_SCRIPT      = pathlib.Path(__file__).parent.parent / "playwright" / "addon_helpers.js"
_SEED_SCRIPT = pathlib.Path(__file__).parent.parent / "playwright" / "seed_doc.js"


def sync_via_sidebar(doc_id: str | None = None, timeout: int = 120) -> dict:
    """Open the test doc, click Sync now in the sidebar, wait for sync.complete.

    Returns the sync.complete log entry as a dict.
    Raises RuntimeError if the sync fails or times out.
    """
    cmd = ["node", str(_SCRIPT), "sync"]
    if doc_id:
        cmd.append(doc_id)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(
            f"sync_via_sidebar failed:\n{result.stderr}"
        )
    return json.loads(result.stdout.strip())


def seed_chip_action(doc_id: str, assignee_email: str, action_text: str = "Review the budget report", timeout: int = 90) -> dict:
    """Insert a chip-led list item into the test doc via Playwright.

    Uses @ mention to create a real PERSON chip as the first element of a
    bulleted-list paragraph. Must be called AFTER the GAS fixture has cleared
    the doc body so the cursor lands at the start of an empty document.

    Returns the JSON result written to stdout by seed_doc.js.
    Raises RuntimeError on failure.
    """
    cmd = ["node", str(_SEED_SCRIPT), "seed", doc_id, assignee_email, action_text]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(
            f"seed_chip_action failed:\n{result.stderr}"
        )
    return json.loads(result.stdout.strip())
