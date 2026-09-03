"""gts-klp8 — differential oracle, live-corpus-document variant.

The seeded-fixture variant (run_differential_oracle.py) found that
DriveV3.Comments.create()-seeded comments never appear in a .docx export
(no word/comments.xml at all, even after 80s) — consistent with gts-6ls9's
finding that the Drive Comments API anchor is opaque and not a real
in-document range. Synthetic Drive-API comments are therefore not a valid
fixture for comparing comment anchoring.

This variant instead runs both exporters read-only against the real
Google-native corpus document already used by gts-6cq2/gts-1nw8 for TOC
verification (`local.settings.json`'s `exportTestDocId`), which is known to
carry real comments and a real TOC. READ-ONLY: no seed_doc_content, no
create_doc_comment, no rename, no trash — this is a live customer document.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from scn.session import ScenarioSession  # noqa: E402
from tests.helpers.download import download_docx  # noqa: E402
from document_export.build import build_export  # noqa: E402

OUT_DIR = pathlib.Path(
    "/tmp/claude-1000/-home-stuar-proj-GActionSheet/abd42669-b8b3-4257-8213-ab772295e65a/"
    "scratchpad/differential-oracle"
)


def _load_settings() -> dict:
    return json.loads((ROOT / "local.settings.json").read_text())


def main() -> None:
    settings = _load_settings()
    doc_id = settings["exportTestDocId"]
    scn = ScenarioSession(doc_id=doc_id, sheet_id=settings.get("testSheetId", ""), settings=settings)

    resp = scn._post_route("export_document_json", {
        "docId": doc_id,
        "exportPdf": False,
        "includeWholeDocumentViews": True,
    })
    assert resp.get("ok"), resp
    gas_json = resp["json"]

    docx_bytes = download_docx(doc_id)
    python_json = build_export(
        docx_bytes,
        doc_id=doc_id,
        title="differential-oracle-livedoc",
        options={"includeImages": True, "includeWholeDocumentViews": True},
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "gas-livedoc.json").write_text(json.dumps(gas_json, indent=2, ensure_ascii=False))
    (OUT_DIR / "python-livedoc.json").write_text(json.dumps(python_json, indent=2, ensure_ascii=False))
    (OUT_DIR / "livedoc_doc_id.txt").write_text(doc_id)
    print(f"wrote artifacts to {OUT_DIR}", file=sys.stderr)


if __name__ == "__main__":
    main()
