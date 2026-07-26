"""Download Google Sheet (.xlsx) and Google Doc (.docx) for local inspection."""
import json
import pathlib
import re
import time
import requests

_OOXML_MAGIC = b"PK\x03\x04"
_AUTH_PATH = pathlib.Path(__file__).parent.parent.parent / ".auth" / "user.json"
_DOC_TITLE_RE = re.compile(r"<title>(.*?)\s*-\s*Google Docs</title>", re.IGNORECASE | re.DOTALL)


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


def download_xlsx(spreadsheet_id: str, timeout: int = 60, retries: int = 3) -> bytes:
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=xlsx"
    session = _authed_session()
    for attempt in range(retries):
        resp = session.get(url, timeout=timeout, allow_redirects=True)
        if resp.status_code == 429 and attempt < retries - 1:
            time.sleep(5 * (attempt + 1))
            continue
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


def fetch_doc_title(doc_id: str, timeout: int = 30) -> str:
    """Return the document's real, current Drive title (gts-jnsf).

    Reads the <title> tag off the doc's edit page ("<Name> - Google Docs") via
    the same cookie-authed session used for xlsx/docx downloads -- unlike the
    .docx export's core_properties.title, which Google Docs always writes as
    the literal placeholder "Word Document", this reflects the live Drive
    filename and observes renames.
    """
    url = f"https://docs.google.com/document/d/{doc_id}/edit"
    resp = _authed_session().get(url, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    m = _DOC_TITLE_RE.search(resp.text)
    if not m:
        raise DownloadError(f"Could not find doc title in edit-page response for {doc_id!r}")
    return m.group(1)
