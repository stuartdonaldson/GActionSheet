"""argument parsing, stderr diagnostics, exit code (contract §7.1, §7.3, §7.5).

`scripts/export_document.py` is a thin shim over `main()` (contract §7.3).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from document_export.acquire import AcquisitionError, acquire_docx_by_id, acquire_docx_from_file, resolve_title
from document_export.build import build_export
from document_export.images import write_image_files
from document_export.package import DocxPackage, PackageError
from document_export.schema import sanitize_filename


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="export_document.py",
        description="Build the LLM-ingestion export JSON from a Google Doc or "
        "Drive-hosted .docx (ADR-0026, schema 3.0).",
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("doc_id", nargs="?", default=None, metavar="DOC_ID",
                      help="Google Drive file id — downloaded via the shared cookie session.")
    src.add_argument("--docx", metavar="PATH",
                      help="Local .docx file. Makes no network call (offline fixture path).")
    p.add_argument("--out-dir", default=None,
                    help="Output directory (default ./exports/<doc_id-or-filename-stem>/).")
    p.add_argument("--no-images", action="store_true",
                    help="Set includeImages=False (default: images included).")
    p.add_argument("--whole-document-views", action="store_true",
                    help="Set includeWholeDocumentViews=True (default: False).")
    p.add_argument("--json-only", action="store_true",
                    help="Suppress writing the cached .docx source alongside the JSON.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    doc_id = args.doc_id
    docx_path = pathlib.Path(args.docx) if args.docx else None

    try:
        if docx_path is not None:
            docx_bytes = acquire_docx_from_file(docx_path)
            title = resolve_title(None, docx_path) or docx_path.stem
        else:
            docx_bytes = acquire_docx_by_id(doc_id)
            title = resolve_title(doc_id, None) or doc_id
    except AcquisitionError as exc:
        print(f"error: acquisition failed: {exc}", file=sys.stderr)
        return 1

    options = {
        "includeImages": not args.no_images,
        "includeWholeDocumentViews": args.whole_document_views,
    }
    try:
        artifact = build_export(docx_bytes, doc_id=doc_id, title=title, options=options)
    except PackageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # contract §7.5 — every warning travels on both channels: it is already
    # in diagnostics.warnings[] (so it reaches the LLM consumer with the
    # artifact); mirror it to stderr here for the operator.
    for warning in artifact.get("diagnostics", {}).get("warnings", []):
        print(f"warning: {warning}", file=sys.stderr)

    stem = sanitize_filename(title)
    default_dir_name = doc_id or docx_path.stem
    out_dir = pathlib.Path(args.out_dir) if args.out_dir else pathlib.Path("exports") / default_dir_name
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"{stem}-document.json"
    json_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    # contract §4: images are written alongside the JSON, named by
    # image_ref. build_export is filesystem-write-free (§7.2), so this reads
    # word/media/ a second time through a fresh DocxPackage over the same
    # bytes rather than threading one out of the pure build.
    document_images = artifact.get("document", {}).get("images")
    if document_images:
        images_dir = out_dir / f"{stem}-images"
        write_image_files(DocxPackage(docx_bytes), document_images, images_dir)

    if not args.json_only:
        cache_path = out_dir / f"{stem}.docx"
        cache_path.write_bytes(docx_bytes)

    print(f"wrote {json_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
