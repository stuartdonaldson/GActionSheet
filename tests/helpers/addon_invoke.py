"""Helpers for invoking the Workspace Add-on sidebar via Playwright (Node.js)."""
import json
import pathlib
import subprocess

_SCRIPT = pathlib.Path(__file__).parent.parent / "playwright" / "addon_helpers.js"


def sync_via_sidebar(doc_id: str | None = None, timeout: int = 90) -> dict:
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
