"""Image extraction (contract §4; stage docx-images, gts-8uo6).

Mirrors src/Procedure-Exporter.js's EMBEDDED IMAGES region
(processInlineImages_/extractInlineImage_) per the contract's "Standing
constraint: architectural alignment for back-port" — one `image` block per
`w:drawing`, pushed onto the paragraph's current unit the same way a text
block is, plus a mirrored `document.images[]` entry (contract §4's "diverted
metadata" convention, matching `document.toc`). `process_inline_images` is
called from structure.py's `_process_paragraph`, before the paragraph's
text-block emptiness check — mirroring GAS's own `processInlineImages_` ->
`allText.trim()` ordering, so an image-only paragraph produces no text block,
only the image block(s) below.

Both **inline** (`wp:inline`) and **positioned/anchored** (`wp:anchor`)
drawings are in scope on this path (contract §4). `extractInlineImage_` only
ever saw `inlineObjectElement` — positioned objects are a Docs-API concept
(`paragraph.positionedObjectIds`) that GAS's structural walk never reaches.
In OOXML both shapes are ordinary `w:drawing` children with the same
`a:blip/@r:embed` -> media-part resolution, so anchored images come along for
free (ADR-0026 Rationale) — `anchored: true|false` on the block is the only
new thing this path has to track.

Bytes are never read here — `word/media/` bytes are needed only to write the
output image files, and `build_export` is network- and filesystem-write-free
(contract §7.2). `write_image_files`, below, is `cli.py`'s post-`build_export`
step, run against its own `DocxPackage` over the same `docx_bytes`.
"""
from __future__ import annotations

import pathlib

from document_export.package import NS
from document_export.schema import (
    SEGMENT_MAIN,
    make_block_id,
    make_citation_hint,
    make_image_id,
    make_image_ref,
    make_location,
)

_R = NS["r"]
_A = NS["a"]
_WP = NS["wp"]

EMU_PER_POINT = 12700

# Mirrors IMAGE_CONTENT_TYPE_EXTENSIONS_ (src/Procedure-Exporter.js:963) —
# content type comes from DocxPackage.content_type() ([Content_Types].xml),
# not the media part's own filename extension (AC #2).
_CONTENT_TYPE_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/bmp": "bmp",
    "image/svg+xml": "svg",
    "image/tiff": "tiff",
    "image/x-emf": "emf",
    "image/x-wmf": "wmf",
}
_DEFAULT_EXTENSION = "png"


def _find_drawings(p_el):
    """Yields (anchored, wp_el) for every wp:inline/wp:anchor anywhere under
    this paragraph, in document order — .iter() descends into w:ins/w:del/
    w:hyperlink/w:smartTag/w:sdt wrappers the same way structure.py's
    _iter_run_elements does for text runs, so a tracked-change- or
    hyperlink-wrapped drawing is not missed."""
    for el in p_el.iter():
        if el.tag == f"{{{_WP}}}inline":
            yield False, el
        elif el.tag == f"{{{_WP}}}anchor":
            yield True, el


def _resolve_source_part(wp_el, rels: dict) -> str | None:
    blip = wp_el.find(f".//{{{_A}}}blip")
    rid = blip.get(f"{{{_R}}}embed") if blip is not None else None
    if not rid:
        return None
    rel = rels.get(rid)
    if not rel:
        return None
    target = rel["target"]
    # document.xml.rels targets are relative to word/ — media/imageN.ext.
    return target if target.startswith("word/") else f"word/{target}"


def _extent_pt(wp_el) -> tuple[float | None, float | None]:
    extent = wp_el.find(f"{{{_WP}}}extent")
    if extent is None:
        return None, None
    cx, cy = extent.get("cx"), extent.get("cy")
    width = round(int(cx) / EMU_PER_POINT, 2) if cx is not None else None
    height = round(int(cy) / EMU_PER_POINT, 2) if cy is not None else None
    return width, height


def _extension_for(pkg, source_part: str) -> str:
    return _CONTENT_TYPE_EXTENSIONS.get(pkg.content_type(source_part) or "", _DEFAULT_EXTENSION)


def has_drawing(p_el) -> bool:
    """Public seam for structure.py (gts-pczo.1): a cheap presence check --
    "does this paragraph carry a drawing at all" -- with no ordinal
    consumption or extraction, so unit detection can tell an image-only
    heading (still opens its own unit) from a truly blank one (does not)
    before process_inline_images does the real, ordinal-consuming walk."""
    return next(_find_drawings(p_el), None) is not None


def process_inline_images(p_el, pkg, rels: dict, ctx) -> None:
    """Mutates `ctx` exactly the way structure.py's own paragraph/table walk
    does: pushes each resolvable drawing's `image` block onto
    `ctx.current_unit["blocks"]`/`ctx.all_blocks`, appends its mirrored
    `document.images[]` entry to `ctx.document_images`, and increments
    `ctx.diagnostics["blocks"]`/`["images"]` — mirroring
    `processInlineImages_` pushing onto `ctx.out.document.images`/
    `ctx.out.diagnostics.images` directly. Each drawing consumes one ordinal
    via `ctx.next_ordinal`, exactly like a text block. A drawing whose blip
    cannot be resolved to a present `word/media/` part is skipped entirely —
    logged as a diagnostics warning, never partially recorded (mirrors
    `extractInlineImage_`'s own fail-closed rule: no block whose `image_ref`
    doesn't correspond to an actual extractable image)."""
    for anchored, wp_el in _find_drawings(p_el):
        doc_pr = wp_el.find(f"{{{_WP}}}docPr")
        name = doc_pr.get("name") if doc_pr is not None else None
        source_part = _resolve_source_part(wp_el, rels)
        if not source_part or not pkg.has_part(source_part):
            ctx.diagnostics["warnings"].append(
                f"Drawing '{name or '?'}' near ordinal {ctx.next_ordinal} has no "
                "resolvable word/media/ part -- skipped, not exported."
            )
            continue

        ordinal = ctx.next_ordinal
        ctx.next_ordinal += 1

        image_ref = make_image_ref(SEGMENT_MAIN, ordinal, _extension_for(pkg, source_part))
        width_pt, height_pt = _extent_pt(wp_el)
        location = make_location(ordinal, ctx.current_page, ctx.explicit_breaks_so_far == 0)

        block = {
            "id": make_block_id(SEGMENT_MAIN, ordinal),
            "unit_id": ctx.current_unit["id"],
            "kind": "image",
            "semantic_state": "baseline",
            "label": None,
            "named_style": None,
            "heading_level": None,
            "source_order": ordinal,
            "location": location,
            "list": None,
            "runs": [],
            "revision_summary": "unchanged",
            "comment_ids": [],
            "image_ref": image_ref,
            "source_part": source_part,
            "anchored": anchored,
            # No OOXML analogue of the Docs API's inlineObjectId -- same
            # disposition as document.revision_id (stage docx-harness) and
            # comment `modified_at` (stage docx-comments): null, recorded
            # here rather than silently assumed. Amend contract §5 if a
            # consumer needs a different value.
            "inline_object_id": None,
            "alt_title": (doc_pr.get("title") if doc_pr is not None else None) or None,
            "alt_description": (doc_pr.get("descr") if doc_pr is not None else None) or None,
            "width_pt": width_pt,
            "height_pt": height_pt,
            # §17 principle 2 -- never fabricated by the exporter. ADR-0025's
            # sidecar writeback is the out-of-band tool that fills this.
            "description": None,
        }
        block["citation_hint"] = make_citation_hint(ctx.current_unit, block)

        ctx.current_unit["blocks"].append(block)
        ctx.all_blocks.append(block)
        ctx.diagnostics["blocks"] += 1
        ctx.diagnostics["images"] += 1

        ctx.document_images.append({
            "id": make_image_id(SEGMENT_MAIN, ordinal),
            "image_ref": image_ref,
            "source_part": source_part,
            "anchored": anchored,
            "segment": SEGMENT_MAIN,
            "source_order": ordinal,
            "location": location,
        })


def write_image_files(pkg, document_images: list[dict], images_dir: pathlib.Path) -> list[pathlib.Path]:
    """cli.py's post-`build_export` step (contract §4: "Files are written to
    <out-dir>/<sanitized-title>-images/, named by image_ref"). Deliberately
    outside `build_export` — which is filesystem-write-free (contract §7.2)
    — so it takes its own `DocxPackage` over the same `docx_bytes` rather
    than one threaded out of the pure build. Same names on re-export of an
    unchanged document (ordinal-derived `image_ref`, AC #5)."""
    images_dir.mkdir(parents=True, exist_ok=True)
    written: list[pathlib.Path] = []
    for entry in document_images:
        path = images_dir / entry["image_ref"]
        path.write_bytes(pkg.media_bytes(entry["source_part"]))
        written.append(path)
    return written
