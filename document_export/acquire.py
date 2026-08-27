""".docx acquisition and on-disk cache (contract §7.3).

Acquisition is URL construction from a docId, and nothing more (ADR-0026
Decision 1) — no mimeType probe, no Drive REST branch, no endpoint
selection. This module is a thin wrapper over
tests/helpers/download.py:download_docx, which already does exactly this
(https://docs.google.com/document/d/<id>/export?format=docx over the shared
Playwright cookie session with proactive+reactive rotation refresh,
gts-f3me.4/gts-85x3.1) — it is not reimplemented here. That endpoint is
verified (ADR-0026 Decision 1) to work for both Google-native documents and
Drive-hosted native .docx files, so a single acquisition path covers tier 1
and tier 2 of the access model (contract §7.3); tier 3 (a WebApp call) is
future and not built, which is why this module keeps acquisition behind one
function rather than leaking a cookie session into the parser.
"""
from __future__ import annotations

import pathlib
import sys

# document_export/ sits at the project root, sibling to scn/ and tests/ —
# add the project root to sys.path so `from tests.helpers.download import
# download_docx` and `from scn.session import ...` resolve regardless of the
# caller's CWD (mirrors scripts/export_governance.py's same guard).
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tests.helpers.download import DownloadError, download_docx, fetch_doc_title  # noqa: E402

__all__ = ["AcquisitionError", "acquire_docx_by_id", "acquire_docx_from_file", "resolve_title"]


class AcquisitionError(Exception):
    pass


def acquire_docx_by_id(doc_id: str, *, timeout: int = 60) -> bytes:
    """Download the .docx export of `doc_id` via the shared cookie session.
    Raises AcquisitionError (not the raw DownloadError) so cli.py has one
    exception type to catch across both acquisition paths."""
    try:
        return download_docx(doc_id, timeout=timeout)
    except DownloadError as exc:
        raise AcquisitionError(str(exc)) from exc


def acquire_docx_from_file(path: str | pathlib.Path) -> bytes:
    """Read a local .docx (the --docx offline fixture path, contract §7.3).
    Makes no network call at all."""
    p = pathlib.Path(path)
    data = p.read_bytes()
    if not data.startswith(b"PK\x03\x04"):
        raise AcquisitionError(f"{p} does not look like a .docx (bad zip magic bytes)")
    return data


def resolve_title(doc_id: str | None, docx_path: str | pathlib.Path | None) -> str | None:
    """Contract §7.3: title comes from download.fetch_doc_title(doc_id), not
    the package's core_properties.title (Google Docs always writes the
    literal "Word Document" there). With --docx and no DOC_ID, title falls
    back to the input filename stem (handled by the caller, which has the
    path) — this function returns None in that case so the caller's fallback
    is visibly the only source, not a silently-overridden one."""
    if doc_id:
        try:
            return fetch_doc_title(doc_id)
        except DownloadError:
            return None
    return None
