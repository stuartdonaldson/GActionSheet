"""Download Google Sheet (.xlsx) and Google Doc (.docx) for local inspection."""
import json
import os
import pathlib
import re
import sys
import time
import requests

from scn.session import resolve_auth_file
from tests.helpers.auth_probe import AuthSessionDeadError

_OOXML_MAGIC = b"PK\x03\x04"
_DOC_TITLE_RE = re.compile(r"<title>(.*?)\s*-\s*Google Docs</title>", re.IGNORECASE | re.DOTALL)

# gts-f3me.4: proactive-refresh window. A requests.Session built from a
# storage_state.json snapshot older than this is refreshed (see
# _refresh_auth_state) before use, even if no failure has been observed yet.
# Override via env for tests / tighter tuning.
_STALE_THRESHOLD_S = float(os.environ.get("GACTIONSHEET_AUTH_STALE_S", 45 * 60))


class DownloadError(Exception):
    pass


def _session_from_auth_file(auth_path: pathlib.Path) -> requests.Session:
    s = requests.Session()
    if not auth_path.exists():
        return s
    data = json.loads(auth_path.read_text())
    for c in data.get("cookies", []):
        s.cookies.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))
    return s


def _refresh_auth_state(role: str = "primary") -> bool:
    """Re-derive fresh cookies for `role` and overwrite its storage_state.json.

    gts-f3me.4 root cause: Google periodically rotates session-cookie *values*
    (accounts.google.com/RotateCookiesPage) while leaving the cookie's on-disk
    expiry timestamp untouched. A live Playwright browser context follows the
    rotation automatically (it runs the page's JS); a requests.Session built
    once from a static storage_state.json snapshot never does, so the
    snapshot silently goes stale mid-run even though nothing on disk looks
    expired.

    Loads the *existing* on-disk cookies into a short-lived headless browser,
    lets it navigate a live Google page (which completes any pending
    rotation the same way an interactive browser would), then saves the
    context's storage_state back over the auth file so subsequent
    requests.Session builds (via _session_from_auth_file) pick up the
    refreshed values. This does not perform an interactive login -- it only
    catches an already-authenticated-but-rotating session back up; a fully
    expired/signed-out session still requires re-running
    tests/playwright/auth.setup.js by hand.

    Returns True if a refresh was attempted and completed, False if it could
    not be attempted (no auth file, playwright not installed) or failed --
    either way, callers should fall back to retrying with whatever is on
    disk, since False just means "no better than before."
    """
    auth_path = resolve_auth_file(role)
    if not auth_path.exists():
        return False
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(storage_state=str(auth_path))
                page = ctx.new_page()
                page.goto(
                    "https://docs.google.com/",
                    wait_until="domcontentloaded",
                    timeout=30_000,
                )
                state = ctx.storage_state()
                ctx.close()
            finally:
                browser.close()
        auth_path.write_text(json.dumps(state))
        return True
    except Exception as exc:
        print(f"⚠️  _refresh_auth_state({role!r}) failed: {exc}", file=sys.stderr)
        return False


def _authed_session(role: str = "primary", *, allow_proactive_refresh: bool = True) -> requests.Session:
    """Build a requests.Session using cookies from the Playwright storage state.

    Resolves the "primary" role via scn.session.resolve_auth_file (shared
    $PLAYWRIGHT_AUTH_DIR location, falling back to the project-local
    .auth/user.json) rather than a hardcoded path -- see .auth/README.md.

    gts-f3me.4: if the on-disk snapshot is older than _STALE_THRESHOLD_S,
    proactively refreshes it (see _refresh_auth_state) before building the
    session, rather than waiting to discover staleness via a failed
    download.
    """
    auth_path = resolve_auth_file(role)
    if allow_proactive_refresh and auth_path.exists() and _STALE_THRESHOLD_S > 0:
        age_s = time.time() - auth_path.stat().st_mtime
        if age_s > _STALE_THRESHOLD_S:
            _refresh_auth_state(role)
    return _session_from_auth_file(auth_path)


def _get_with_refresh(url: str, *, timeout: int, is_stale) -> requests.Response:
    """GET url; if the response looks stale per is_stale(resp), refresh the
    auth state once and retry (gts-f3me.4 reactive path -- covers rotation
    that happens between the proactive check and the request landing).
    """
    session = _authed_session()
    resp = session.get(url, timeout=timeout, allow_redirects=True)
    if is_stale(resp) and _refresh_auth_state():
        session = _authed_session(allow_proactive_refresh=False)
        resp = session.get(url, timeout=timeout, allow_redirects=True)
        if is_stale(resp):
            # gts-85x3.1: the refresh completed but the retry is STILL stale
            # -- per _refresh_auth_state's own docstring, that mechanism only
            # catches an already-authenticated-but-rotating session back up.
            # A response that's still stale after a refresh means the
            # session is fully signed out, which no amount of automated
            # retrying will fix (confirmed live 2026-08-21, gas-test4.log:
            # the account stayed signed out for a full 2h21m run). Fail
            # loud here instead of returning the bad response for a
            # generic caller-side check (e.g. the xlsx/docx magic-bytes
            # check) to fail on less clearly, once per call, for the rest
            # of the run.
            raise AuthSessionDeadError(
                f"Auth session for this role is fully signed out (still stale "
                f"after refresh-and-retry against {url!r}). Re-run "
                f"'node tests/playwright/auth.setup.js' by hand before "
                f"continuing."
            )
    return resp


def _looks_stale(resp: requests.Response) -> bool:
    """True if a response looks like a login/error HTML page rather than the
    requested binary export (gts-f3me.4 staleness signal). Excludes 429 --
    that's a rate limit, handled by download_xlsx's own retry loop, not an
    auth problem."""
    if resp.status_code == 429:
        return False
    if "accounts.google.com" in resp.url:
        return True
    return "text/html" in resp.headers.get("Content-Type", "")


def download_xlsx(spreadsheet_id: str, timeout: int = 60, retries: int = 3) -> bytes:
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=xlsx"
    for attempt in range(retries):
        resp = _get_with_refresh(url, timeout=timeout, is_stale=_looks_stale)
        if resp.status_code == 429 and attempt < retries - 1:
            time.sleep(5 * (attempt + 1))
            continue
        resp.raise_for_status()
        if not resp.content.startswith(_OOXML_MAGIC):
            raise DownloadError(f"Response is not xlsx (got {resp.content[:20]!r})")
        return resp.content


def download_docx(doc_id: str, timeout: int = 60) -> bytes:
    url = f"https://docs.google.com/document/d/{doc_id}/export?format=docx"
    resp = _get_with_refresh(url, timeout=timeout, is_stale=_looks_stale)
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

    def _title_missing(resp: requests.Response) -> bool:
        return not _DOC_TITLE_RE.search(resp.text)

    resp = _get_with_refresh(url, timeout=timeout, is_stale=_title_missing)
    resp.raise_for_status()
    m = _DOC_TITLE_RE.search(resp.text)
    if not m:
        raise DownloadError(f"Could not find doc title in edit-page response for {doc_id!r}")
    return m.group(1)
