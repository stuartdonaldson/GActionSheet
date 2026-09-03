#!/usr/bin/env python3
"""
export_gas.py — run the frozen GAS document export against a live Google Doc and
download the JSON (and optionally PDF) artifacts to local disk (gts-283i.2).

Calls the same run_export_for_dialog_test WebApp route the pytest suite uses
(tests/test_export_dialog.py) — the headless call-site into
src/Procedure-Exporter.js's runExportForDialog(), the same entry point the
classic-menu Export dialog (ExportProgressDialog.html) drives via
google.script.run. runExportForDialog's jsonContent/pdfBase64 return fields
(gts-283i.2) are what let this script download bytes locally without a
second Drive round trip — see that function's docstring in
src/Procedure-Exporter.js.

The export always also lands in Drive (getExportFolder_()'s per-document
export folder, or the source doc's parent folder as a fallback) — this
script's local copy is an additional convenience, not a replacement.

Usage:
    python scripts/export_gas.py [DOC_ID] [--pdf] [--images] [--out-dir DIR] [--env test|prod|dev]

DOC_ID is optional: if omitted, defaults to exportTestDocId in local.settings.json.

Examples:
    python scripts/export_gas.py
    python scripts/export_gas.py 1zQkRAczbRjB0iRD2OhpHsqXvHsmskE8VI7VNx8vE5yE --pdf --images --out-dir /tmp/exports
"""
import argparse
import base64
import json
import pathlib
import re
import sys
import time
import requests

from call_webapp import call_action, _load_settings  # scripts/ is the CWD-relative import root

# scn/ lives at the project root, not under scripts/ -- running this script as
# `python scripts/export_gas.py` puts scripts/ (not the project root)
# on sys.path[0], so the plain `from scn.session import ...` silently
# ModuleNotFoundErrors and (if caught broadly) masks itself as "auth not
# configured" instead of "path wrong". Add the project root explicitly.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from scn.session import resolve_auth_file


def _sanitize_filename(s: str) -> str:
    """Mirror src/Procedure-Exporter.js's sanitizeFilename_ so local filenames
    match the names Drive already gave the same bytes (jsonFile/pdfFile)."""
    s = (s or "document").strip()
    s = re.sub(r'[\\/:*?"<>|]+', "-", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-") or "document"


def _authed_session() -> requests.Session:
    """Build a requests.Session using cookies from Playwright storage state.

    Mirrors tests/helpers/download.py's _authed_session -- same "primary"
    role resolution, same reuse of captured browser auth instead of a
    separate OAuth/service-account setup. Unlike download.py this raises
    (rather than silently returning an unauthenticated session) when no auth
    file is found: image blobs are typically private to the exporting
    account, so an unauthenticated download would fail confusingly downstream
    instead of with a clear cause here.
    """
    auth_path = resolve_auth_file("primary")
    if not auth_path.exists():
        raise RuntimeError(
            f"No Playwright auth file found at {auth_path} -- run "
            "`node tests/playwright/auth.setup.js` (see .auth/README.md) "
            "before using --images."
        )
    s = requests.Session()
    data = json.loads(auth_path.read_text())
    for c in data.get("cookies", []):
        s.cookies.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))
    return s


def _download_drive_file(session: requests.Session, file_id: str, timeout: int = 30,
                          retries: int = 3) -> bytes:
    """Download a raw file's bytes from Google Drive using an authenticated
    session (cookie-based, same mechanism as tests/helpers/download.py's
    xlsx/docx export downloads -- the /uc?export=download endpoint accepts
    browser session cookies, unlike the Drive REST API which needs an OAuth
    bearer token).

    Only retries transient conditions (429 rate-limit, 5xx); a 403/404 means
    the file id is wrong or the authed account lacks access, and retrying
    that blindly just wastes time before failing the same way.
    """
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    for attempt in range(retries):
        resp = session.get(url, timeout=timeout, allow_redirects=True)
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
            time.sleep(5 * (attempt + 1))
            continue
        resp.raise_for_status()
        return resp.content

    raise RuntimeError(f"Failed to download Drive file {file_id} after {retries} retries")


def export_and_download(doc_id: str, *, export_pdf: bool, export_images: bool,
                         out_dir: pathlib.Path, env: str = "test") -> dict:
    result = call_action(
        "run_export_for_dialog_test",
        {"docId": doc_id, "exportPdf": export_pdf},
        env=env,
    )
    if "error" in result:
        raise RuntimeError(f"export failed for docId={doc_id!r}: {result['error']}")
    if not result.get("ok"):
        raise RuntimeError(f"unexpected response for docId={doc_id!r}: {result}")

    out_dir.mkdir(parents=True, exist_ok=True)

    doc_json = json.loads(result["jsonContent"])

    # Name local files after the document's own title (matching the Drive
    # file names exportDocument_ already gave the same bytes:
    # "<title>-gas.json" / "<title>-snapshot.pdf") rather than the
    # docId, so the local copy is identifiable at a glance.
    title = doc_json.get("document", {}).get("title") or doc_id
    stem = _sanitize_filename(title)

    json_path = out_dir / f"{stem}-gas.json"
    json_path.write_text(result["jsonContent"], encoding="utf-8")
    written = {"json": json_path}

    if export_pdf:
        if not result.get("pdfBase64"):
            print("WARNING: --pdf requested but no pdfBase64 in response "
                  "(PDF snapshot may have failed server-side)", file=sys.stderr)
        else:
            pdf_path = out_dir / f"{stem}-snapshot.pdf"
            pdf_path.write_bytes(base64.b64decode(result["pdfBase64"]))
            written["pdf"] = pdf_path

    if export_images:
        images = doc_json.get("document", {}).get("images", [])
        if not images:
            print("No embedded images found in document.", file=sys.stderr)
        else:
            # "<title>-images/" matches getImagesFolder_'s own naming
            # convention in src/Procedure-Exporter.js, so the local copy
            # mirrors the Drive-side subfolder the exporter already created.
            images_dir = out_dir / f"{stem}-images"
            images_dir.mkdir(parents=True, exist_ok=True)
            session = _authed_session()
            image_paths = []
            written["images_total"] = len(images)
            for img in images:
                file_id = img["drive_file_id"]
                image_ref = img["image_ref"]
                try:
                    data = _download_drive_file(session, file_id)
                except (requests.exceptions.RequestException, RuntimeError) as e:
                    print(f"WARNING: failed to download image {image_ref} "
                          f"(drive_file_id={file_id}): {e}", file=sys.stderr)
                    continue
                img_path = images_dir / image_ref
                img_path.write_bytes(data)
                image_paths.append(img_path)
            written["images"] = image_paths
            written["images_dir"] = images_dir

    written["jsonFileId"] = result.get("jsonFileId")
    written["pdfFileId"] = result.get("pdfFileId")
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("doc_id", nargs="?", default=None,
                         help="Google Doc id to export (default: exportTestDocId in "
                              "local.settings.json, if set)")
    parser.add_argument("--pdf", action="store_true", help="Also export + download a PDF snapshot")
    parser.add_argument("--images", action="store_true",
                         help="Also download embedded images (from document.images[].drive_file_id) "
                              "into a <title>-images/ subfolder of --out-dir")
    parser.add_argument("--out-dir", default="exports", help="Local directory to write files into (default: ./exports)")
    parser.add_argument("--env", choices=["test", "prod", "dev"], default="test",
                         help="Which WebApp deployment to call (default: test)")
    args = parser.parse_args()

    doc_id = args.doc_id
    if doc_id is None:
        doc_id = _load_settings().get("exportTestDocId")
        if not doc_id:
            parser.error("doc_id not given and exportTestDocId not set in local.settings.json")
        print(f"No doc_id given -- using exportTestDocId from local.settings.json: {doc_id}",
              file=sys.stderr)

    try:
        written = export_and_download(
            doc_id, export_pdf=args.pdf, export_images=args.images,
            out_dir=pathlib.Path(args.out_dir), env=args.env,
        )
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"JSON  -> {written['json']}  (Drive fileId: {written.get('jsonFileId')})")
    if "pdf" in written:
        print(f"PDF   -> {written['pdf']}  (Drive fileId: {written.get('pdfFileId')})")
    if "images" in written:
        print(f"IMAGES -> {written['images_dir']}/  ({len(written['images'])}/"
              f"{written['images_total']} downloaded)")
        for p in written["images"]:
            print(f"          {p.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
