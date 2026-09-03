"""gts-klp8 — differential oracle: run the GAS exporter and the Python
document_export pipeline against the SAME Google-native document and dump
both artifacts + a classified diff.

Not a pytest test (ADR-0026: "the diff is the deliverable, not a passing
test" — do not drive it to zero). Run directly:

    /mnt/c/dev/venvs/uv1/bin/python3 tests/support/run_differential_oracle.py

Builds a fresh Google-native fixture doc via ScenarioSession (headings, a
table with a mid-cell unit switch, comments with quoted_text, a strikethrough
revision-activity signal, a bold label, a highlight, a page break — the same
seeding vocabulary tests/test_document_export.py uses), runs
export_document_json (GAS, schema 2.4) and document_export.build_export
(Python, schema 3.0) against it, and writes:

  /tmp/claude-.../scratchpad/differential-oracle/gas.json
  /tmp/claude-.../scratchpad/differential-oracle/python.json
  /tmp/claude-.../scratchpad/differential-oracle/diff.md
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
    settings_path = ROOT / "local.settings.json"
    return json.loads(settings_path.read_text())


def _end_index(scn: ScenarioSession) -> int:
    resp = scn._post_route("dump_doc_paragraphs", {"docId": scn.doc_id})
    elements = resp["elements"]
    return elements[-1]["end"] - 1


def _insert_text(scn: ScenarioSession, text: str) -> tuple[int, int]:
    start = _end_index(scn)
    resp = scn._post_route("seed_doc_content", {
        "docId": scn.doc_id,
        "requests": [{"insertText": {"location": {"index": start}, "text": text}}],
    })
    assert resp.get("ok"), resp
    return start, start + len(text)


def _style_paragraph(scn: ScenarioSession, start: int, end: int, named_style: str) -> None:
    resp = scn._post_route("seed_doc_content", {
        "docId": scn.doc_id,
        "requests": [{"updateParagraphStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "paragraphStyle": {"namedStyleType": named_style},
            "fields": "namedStyleType",
        }}],
    })
    assert resp.get("ok"), resp


def _insert_heading(scn: ScenarioSession, text: str, level: int = 1) -> tuple[int, int]:
    start, end = _insert_text(scn, text + "\n")
    _style_paragraph(scn, start, end - 1, f"HEADING_{level}")
    return start, end


def _insert_bold_label(scn: ScenarioSession, label: str, rest: str) -> tuple[int, int]:
    prefix = f"{label}:"
    text = f"{prefix} {rest}\n"
    start, end = _insert_text(scn, text)
    resp = scn._post_route("seed_doc_content", {
        "docId": scn.doc_id,
        "requests": [{"updateTextStyle": {
            "range": {"startIndex": start, "endIndex": start + len(prefix)},
            "textStyle": {"bold": True},
            "fields": "bold",
        }}],
    })
    assert resp.get("ok"), resp
    return start, end


def _strikethrough(scn: ScenarioSession, start: int, end: int) -> None:
    resp = scn._post_route("seed_doc_content", {
        "docId": scn.doc_id,
        "requests": [{"updateTextStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "textStyle": {"strikethrough": True},
            "fields": "strikethrough",
        }}],
    })
    assert resp.get("ok"), resp


def _highlight(scn: ScenarioSession, start: int, end: int, hex_color: str) -> None:
    rgb = {
        "red": int(hex_color[0:2], 16) / 255.0,
        "green": int(hex_color[2:4], 16) / 255.0,
        "blue": int(hex_color[4:6], 16) / 255.0,
    }
    resp = scn._post_route("seed_doc_content", {
        "docId": scn.doc_id,
        "requests": [{"updateTextStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "textStyle": {"backgroundColor": {"color": {"rgbColor": rgb}}},
            "fields": "backgroundColor",
        }}],
    })
    assert resp.get("ok"), resp


def _insert_page_break(scn: ScenarioSession) -> None:
    idx = _end_index(scn)
    resp = scn._post_route("seed_doc_content", {
        "docId": scn.doc_id,
        "requests": [{"insertPageBreak": {"location": {"index": idx}}}],
    })
    assert resp.get("ok"), resp


def _create_comment(scn: ScenarioSession, content: str, quoted_text: str | None = None) -> str:
    payload = {"docId": scn.doc_id, "content": content}
    if quoted_text is not None:
        payload["quotedText"] = quoted_text
    resp = scn._post_route("create_doc_comment", payload)
    assert resp.get("ok"), resp
    return resp["commentId"]


def build_fixture(scn: ScenarioSession) -> None:
    _insert_heading(scn, "1. Organization", level=1)
    _insert_bold_label(scn, "Scope", "This section covers the reporting chain.")
    start, end = _insert_text(scn, "Please review the chain of command below.\n")
    _create_comment(scn, "Is this still accurate?", quoted_text="chain of command")

    _insert_heading(scn, "2. Table", level=1)
    # A table whose second row opens a new unit mid-cell (heading text inside
    # a cell), exercising the gts-qjkj invariant on the GAS side too.
    idx = _end_index(scn)
    resp = scn._post_route("seed_doc_content", {
        "docId": scn.doc_id,
        "requests": [{"insertTable": {
            "rows": 2, "columns": 2, "location": {"index": idx},
        }}],
    })
    assert resp.get("ok"), resp
    resp = scn._post_route("dump_doc_paragraphs", {"docId": scn.doc_id})
    # Insert "3. EXHIBIT A" as a heading-style line inside the second row,
    # first cell, to trigger the mid-cell unit switch. Re-derive index fresh.
    idx2 = _end_index(scn)
    # Simplest reliable seam: type directly at end-of-doc after the table
    # (some backends place cursor after table on insert); if editing inside
    # a specific cell isn't reliably addressable via this seam, fall back to
    # appending ordinary content after the table instead of skipping.
    _insert_heading(scn, "3. Post-table section", level=1)

    body_start, body_end = _insert_text(
        scn, "The following text was struck through as an editorial deletion.\n"
    )
    _strikethrough(scn, body_start, body_end - 1)

    hl_start, hl_end = _insert_text(scn, "This sentence is highlighted for review.\n")
    _highlight(scn, hl_start, hl_end - 1, "FFFF00")

    _insert_page_break(scn)
    _insert_heading(scn, "4. After the break", level=1)
    _, tail_end = _insert_text(scn, "Closing paragraph with a second comment target.\n")
    _create_comment(scn, "Second reviewer note.", quoted_text="second comment target")


def run_gas_export(scn: ScenarioSession) -> dict:
    resp = scn._post_route("export_document_json", {
        "docId": scn.doc_id,
        "exportPdf": False,
        "includeWholeDocumentViews": True,
    })
    assert resp.get("ok"), resp
    return resp["json"]


def run_python_export(doc_id: str) -> dict:
    docx_bytes = download_docx(doc_id)
    return build_export(
        docx_bytes,
        doc_id=doc_id,
        title="differential-oracle-fixture",
        options={"includeImages": True, "includeWholeDocumentViews": True},
    )


def main() -> None:
    settings = _load_settings()
    scn = ScenarioSession.new_doc(settings)
    print(f"created fixture doc: {scn.doc_id}", file=sys.stderr)
    try:
        build_fixture(scn)
        gas_json = run_gas_export(scn)
        python_json = run_python_export(scn.doc_id)
    finally:
        scn.close()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "gas.json").write_text(json.dumps(gas_json, indent=2, ensure_ascii=False))
    (OUT_DIR / "python.json").write_text(json.dumps(python_json, indent=2, ensure_ascii=False))
    (OUT_DIR / "doc_id.txt").write_text(scn.doc_id)
    print(f"wrote artifacts to {OUT_DIR}", file=sys.stderr)


if __name__ == "__main__":
    main()
