"""Helpers for invoking GAS functions via the Google Sheet custom menu (Playwright)."""
import pathlib
import subprocess

_SCRIPT = pathlib.Path(__file__).parent.parent / "playwright" / "invoke_gas.js"


def _invoke(menu_item: str, arg: str | None = None, timeout: int = 60) -> None:
    cmd = ["node", str(_SCRIPT), menu_item]
    if arg is not None:
        cmd.append(arg)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(
            f"invoke_gas failed for menu item {menu_item!r}:\n{result.stderr}"
        )


def setup_fixture(scenario: str) -> None:
    _invoke("Test: Setup Fixture", scenario)


def sync_document(doc_id: str) -> None:
    _invoke("Test: Sync Document", doc_id)


def sync_all() -> None:
    _invoke("Sync")
