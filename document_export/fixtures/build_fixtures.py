#!/usr/bin/env python3
"""Generator for the stage-2 (gts-28hx) checked-in fixture corpus.

Hand-builds two .docx packages directly as OOXML (not via python-docx, which
has no support for w:commentRangeStart/End or w:ins/w:del authorship — the
same reason ADR-0026 Decision 3 rules it out for the pipeline itself) so the
fixtures exercise exactly the features the contract names: comments (with a
threaded, resolved reply), tracked changes (including inserted-then-deleted),
images (inline), tables (with a mid-cell unit-switch), numbered lists, and a
TOC field.

Run to regenerate the checked-in fixtures:
    python document_export/fixtures/build_fixtures.py

Writes:
    document_export/fixtures/golden.docx           -- full feature set
    document_export/fixtures/golden-no-images.docx -- same minus the image
                                                        (gts-0rho AC #6(d):
                                                        document.images must
                                                        be omitted entirely,
                                                        key absent, for a
                                                        document with no
                                                        images)

Not part of the document_export package -- this is a one-shot content
generator, not runtime code.
"""
from __future__ import annotations

import binascii
import pathlib
import struct
import zipfile
import zlib

FIXTURES_DIR = pathlib.Path(__file__).resolve().parent

CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
  <Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>
  <Override PartName="/word/commentsExtended.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtended+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""

ROOT_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""

CORE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Word Document</dc:title>
  <dc:creator>document-export fixture generator</dc:creator>
  <dcterms:created xsi:type="dcterms:W3CDTF">2026-08-01T00:00:00Z</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">2026-08-25T00:00:00Z</dcterms:modified>
</cp:coreProperties>
"""

APP_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Application>document_export fixture generator</Application>
</Properties>
"""

STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:sz w:val="22"/></w:rPr></w:rPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:outlineLvl w:val="0"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="32"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:outlineLvl w:val="1"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="28"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading3">
    <w:name w:val="heading 3"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:outlineLvl w:val="2"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="24"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="ListParagraph">
    <w:name w:val="List Paragraph"/>
    <w:basedOn w:val="Normal"/>
  </w:style>
</w:styles>
"""

NUMBERING_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="0">
    <w:lvl w:ilvl="0">
      <w:start w:val="1"/>
      <w:numFmt w:val="decimal"/>
      <w:lvlText w:val="%1."/>
      <w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr>
    </w:lvl>
  </w:abstractNum>
  <w:num w:numId="1">
    <w:abstractNumId w:val="0"/>
  </w:num>
</w:numbering>
"""

COMMENTS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">
  <w:comment w:id="0" w:author="Alex Reviewer" w:initials="AR" w:date="2026-08-20T10:00:00Z">
    <w:p w14:paraId="00000001"><w:r><w:t>Please confirm this figure with legal before publishing.</w:t></w:r></w:p>
  </w:comment>
  <w:comment w:id="1" w:author="Sam Author" w:initials="SA" w:date="2026-08-20T11:00:00Z">
    <w:p w14:paraId="00000002"><w:r><w:t>Confirmed with legal, thanks -- resolving.</w:t></w:r></w:p>
  </w:comment>
  <w:comment w:id="2" w:author="Alex Reviewer" w:initials="AR" w:date="2026-08-20T12:00:00Z">
    <w:p w14:paraId="00000003"><w:r><w:t>This spans two paragraphs -- flag both for review.</w:t></w:r></w:p>
  </w:comment>
</w:comments>
"""

COMMENTS_EXTENDED_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w15:commentsEx xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml">
  <w15:commentEx w15:paraId="00000001" w15:done="0"/>
  <w15:commentEx w15:paraId="00000002" w15:paraIdParent="00000001" w15:done="1"/>
  <w15:commentEx w15:paraId="00000003" w15:done="0"/>
</w15:commentsEx>
"""


def _run(text: str, *, bold: bool = False) -> str:
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{text}</w:t></w:r>'


def _p(style: str | None, inner: str, *, num_id: int | None = None, ilvl: int = 0) -> str:
    ppr_parts = []
    if style:
        ppr_parts.append(f'<w:pStyle w:val="{style}"/>')
    if num_id is not None:
        ppr_parts.append(f'<w:numPr><w:ilvl w:val="{ilvl}"/><w:numId w:val="{num_id}"/></w:numPr>')
    ppr = f"<w:pPr>{''.join(ppr_parts)}</w:pPr>" if ppr_parts else ""
    return f"<w:p>{ppr}{inner}</w:p>"


def _document_xml(*, include_image: bool) -> str:
    body_parts: list[str] = []

    # -- 1. Heading + TOC (simple field; Word normally emits a complex
    # field with nested hyperlinks, simplified here -- see fixtures README).
    body_parts.append(_p("Heading1", _run("Table of Contents")))
    body_parts.append(
        _p(
            None,
            '<w:fldSimple w:instr="TOC \\o &quot;1-3&quot; \\h \\z \\u">'
            + _run("1. Introduction ... 1")
            + "</w:fldSimple>",
        )
    )
    body_parts.append(
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        '<w:bookmarkStart w:id="0" w:name="_Toc00000001"/>'
        + _run("1. Introduction")
        + '<w:bookmarkEnd w:id="0"/></w:p>'
    )

    # -- 2. Tracked changes: proposed insertion + suggested deletion.
    body_parts.append(
        "<w:p>"
        + _run("The system shall ")
        + '<w:ins w:id="1" w:author="Diane Slota" w:date="2026-08-18T09:00:00Z">'
        + _run("always ")
        + "</w:ins>"
        + _run("process requests")
        + '<w:del w:id="2" w:author="Diane Slota" w:date="2026-08-18T09:05:00Z">'
        + '<w:r><w:delText xml:space="preserve"> within one business day</w:delText></w:r>'
        + "</w:del>"
        + _run(".")
        + "</w:p>"
    )

    # -- 3. Inserted-then-deleted (w:del nested inside w:ins) -- contract §3.2.
    body_parts.append(
        "<w:p>"
        + '<w:ins w:id="3" w:author="Diane Slota" w:date="2026-08-18T09:10:00Z">'
        + '<w:del w:id="4" w:author="Diane Slota" w:date="2026-08-18T09:12:00Z">'
        + '<w:r><w:delText xml:space="preserve">Draft note removed before acceptance.</w:delText></w:r>'
        + "</w:del></w:ins>"
        + "</w:p>"
    )

    # -- 4. Comment range, threaded + resolved reply attaches via
    # commentsExtended.xml (paraId 00000001/00000002), not via this range.
    body_parts.append(_p("Heading2", _run("2. Review Comments")))
    body_parts.append(
        "<w:p>"
        + '<w:commentRangeStart w:id="0"/>'
        + _run("Revenue projections increase forty percent year over year")
        + '<w:commentRangeEnd w:id="0"/>'
        + '<w:r><w:commentReference w:id="0"/></w:r>'
        + _run(".")
        + "</w:p>"
    )

    # -- 4b. Comment range spanning two paragraphs (contract §2.2:
    # associated_block_ids gets both block ids, one comment record).
    body_parts.append(_p("Heading2", _run("2b. Multi-block Comment")))
    body_parts.append(
        "<w:p>"
        + '<w:commentRangeStart w:id="2"/>'
        + _run("First paragraph of the spanning comment")
        + "</w:p>"
    )
    body_parts.append(
        "<w:p>"
        + _run("second paragraph of the spanning comment")
        + '<w:commentRangeEnd w:id="2"/>'
        + '<w:r><w:commentReference w:id="2"/></w:r>'
        + "</w:p>"
    )

    # -- 5. Numbered list.
    body_parts.append(_p("Heading2", _run("3. Numbered Steps")))
    for i, step in enumerate(["Gather requirements.", "Draft the procedure.", "Circulate for review."]):
        body_parts.append(_p("ListParagraph", _run(step), num_id=1, ilvl=0))

    # -- 6. Table with a mid-cell unit-switch (gts-qjkj invariant): cell B2
    # contains a heading paragraph followed by body text, i.e. a new unit
    # opens partway through a table cell.
    body_parts.append(_p("Heading2", _run("4. Reference Table")))
    body_parts.append(
        "<w:tbl>"
        '<w:tblPr><w:tblW w:w="0" w:type="auto"/></w:tblPr>'
        '<w:tblGrid><w:gridCol/><w:gridCol/></w:tblGrid>'
        "<w:tr>"
        f'<w:tc><w:tcPr/>{_p(None, _run("Column A", bold=True))}</w:tc>'
        f'<w:tc><w:tcPr/>{_p(None, _run("Column B", bold=True))}</w:tc>'
        "</w:tr>"
        "<w:tr>"
        f'<w:tc><w:tcPr/>{_p(None, _run("Value 1"))}</w:tc>'
        f'<w:tc><w:tcPr/>{_p("Heading3", _run("Sub-Unit In Cell"))}{_p(None, _run("Detail text for the sub-unit."))}</w:tc>'
        "</w:tr>"
        "</w:tbl>"
    )
    # A paragraph must follow a table at the sectPr level per OOXML (a body
    # cannot end on a w:tbl).
    body_parts.append(_p(None, ""))

    # -- 7. Images: one inline (wp:inline), one positioned/anchored
    # (wp:anchor) -- gts-8uo6 AC #1 requires both shapes covered. Omitted
    # entirely in the image-free variant so gts-0rho AC #6(d) (document.images
    # key absent) has a fixture to run against.
    if include_image:
        body_parts.append(_p("Heading2", _run("5. Figure")))
        body_parts.append(
            "<w:p><w:r><w:drawing>"
            '<wp:inline distT="0" distB="0" distL="0" distR="0" '
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
            '<wp:extent cx="914400" cy="914400"/>'
            '<wp:docPr id="1" name="Picture 1" title="Sample figure" descr="A single red pixel used as a placeholder figure."/>'
            '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:blipFill><a:blip r:embed="rId4" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
            "<a:stretch><a:fillRect/></a:stretch></pic:blipFill>"
            "<pic:spPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"914400\" cy=\"914400\"/></a:xfrm>"
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
            "</pic:pic></a:graphicData></a:graphic></wp:inline>"
            "</w:drawing></w:r></w:p>"
        )
        body_parts.append(
            "<w:p><w:r><w:drawing>"
            '<wp:anchor distT="0" distB="0" distL="114300" distR="114300" simplePos="0" '
            'relativeHeight="1" behindDoc="0" locked="0" layoutInCell="1" allowOverlap="1" '
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
            '<wp:simplePos x="0" y="0"/>'
            '<wp:positionH relativeFrom="column"><wp:posOffset>0</wp:posOffset></wp:positionH>'
            '<wp:positionV relativeFrom="paragraph"><wp:posOffset>0</wp:posOffset></wp:positionV>'
            '<wp:extent cx="914400" cy="457200"/>'
            "<wp:wrapNone/>"
            '<wp:docPr id="2" name="Picture 2" title="Anchored figure" descr="A floating callout image."/>'
            '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:blipFill><a:blip r:embed="rId6" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
            "<a:stretch><a:fillRect/></a:stretch></pic:blipFill>"
            "<pic:spPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"914400\" cy=\"457200\"/></a:xfrm>"
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
            "</pic:pic></a:graphicData></a:graphic></wp:anchor>"
            "</w:drawing></w:r></w:p>"
        )

    sect_pr = "<w:sectPr/>"
    body = "".join(body_parts) + sect_pr

    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <w:body>{body}</w:body>
</w:document>
"""


def _document_rels_xml(*, include_image: bool) -> str:
    rels = [
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>',
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>',
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/>',
    ]
    if include_image:
        rels.append(
            '<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>'
        )
        rels.append(
            '<Relationship Id="rId6" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image2.png"/>'
        )
    rels.append(
        '<Relationship Id="rId5" Type="http://schemas.microsoft.com/office/2011/relationships/commentsExtended" Target="commentsExtended.xml"/>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n  '
        + "\n  ".join(rels)
        + "\n</Relationships>\n"
    )


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", binascii.crc32(tag + data))


def _one_pixel_red_png() -> bytes:
    """A minimal, valid 1x1 red PNG -- stdlib-only (struct + zlib + binascii),
    no image library dependency for the fixture generator."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1x1, 8-bit, RGB
    raw_scanline = b"\x00" + bytes([255, 0, 0])  # filter byte 0 + one RGB pixel
    idat = zlib.compress(raw_scanline)
    return (
        sig
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def _one_pixel_blue_png() -> bytes:
    """Second fixture image (the anchored one) -- a distinct color from
    _one_pixel_red_png so the two media parts are visibly different bytes,
    not just different names."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1x1, 8-bit, RGB
    raw_scanline = b"\x00" + bytes([0, 0, 255])  # filter byte 0 + one RGB pixel
    idat = zlib.compress(raw_scanline)
    return (
        sig
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def _build(out_path: pathlib.Path, *, include_image: bool) -> None:
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        zf.writestr("_rels/.rels", ROOT_RELS_XML)
        zf.writestr("docProps/core.xml", CORE_XML)
        zf.writestr("docProps/app.xml", APP_XML)
        zf.writestr("word/document.xml", _document_xml(include_image=include_image))
        zf.writestr("word/_rels/document.xml.rels", _document_rels_xml(include_image=include_image))
        zf.writestr("word/styles.xml", STYLES_XML)
        zf.writestr("word/numbering.xml", NUMBERING_XML)
        zf.writestr("word/comments.xml", COMMENTS_XML)
        zf.writestr("word/commentsExtended.xml", COMMENTS_EXTENDED_XML)
        if include_image:
            zf.writestr("word/media/image1.png", _one_pixel_red_png())
            zf.writestr("word/media/image2.png", _one_pixel_blue_png())


def main() -> None:
    _build(FIXTURES_DIR / "golden.docx", include_image=True)
    _build(FIXTURES_DIR / "golden-no-images.docx", include_image=False)
    print(f"wrote {FIXTURES_DIR / 'golden.docx'}")
    print(f"wrote {FIXTURES_DIR / 'golden-no-images.docx'}")


if __name__ == "__main__":
    main()
