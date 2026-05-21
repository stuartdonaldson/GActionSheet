"""Download Google Sheet (.xlsx) and Google Doc (.docx) for local inspection."""
import json
import pathlib
import requests

_OOXML_MAGIC = b"PK\x03\x04"
_AUTH_PATH = pathlib.Path(__file__).parent.parent.parent / ".auth" / "user.json"


class DownloadError(Exception):
    pass


def _authed_session() -> requests.Session:
    """Build a requests.Session using cookies from the Playwright storage state."""
    s = requests.Session()
    if not _AUTH_PATH.exists():
        return s
    data = json.loads(_AUTH_PATH.read_text())
    for c in data.get("cookies", []):
        s.cookies.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))
    return s


def download_xlsx(spreadsheet_id: str, timeout: int = 60) -> bytes:
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=xlsx"
    resp = _authed_session().get(url, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    if not resp.content.startswith(_OOXML_MAGIC):
        raise DownloadError(f"Response is not xlsx (got {resp.content[:20]!r})")
    return resp.content


def download_docx(doc_id: str, timeout: int = 60) -> bytes:
    url = f"https://docs.google.com/document/d/{doc_id}/export?format=docx"
    resp = _authed_session().get(url, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    if not resp.content.startswith(_OOXML_MAGIC):
        raise DownloadError(f"Response is not docx (got {resp.content[:20]!r})")
    return resp.content
