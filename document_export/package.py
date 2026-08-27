"""OOXML zip/part/relationship access (contract §7.1).

One accessor over a .docx's zip parts so later passes (structure, comments,
revisions, images — stages 3-6) do not each re-open the archive. stdlib
zipfile + xml.etree.ElementTree only, per ADR-0026 Decision 3: python-docx is
available but is not used for comment ranges (its native support is weak and
w:commentRangeStart/End handling is the whole point of this pipeline).
"""
from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree as ET

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}

# Parts this pipeline reads (contract §7.1 item 3). Not every part is present
# in every .docx — comments.xml/commentsExtended.xml/numbering.xml are all
# optional per OOXML and are treated as absent (None), not an error.
_OPTIONAL_XML_PARTS = {
    "document": "word/document.xml",
    "comments": "word/comments.xml",
    "comments_extended": "word/commentsExtended.xml",
    "numbering": "word/numbering.xml",
    "styles": "word/styles.xml",
    "document_rels": "word/_rels/document.xml.rels",
}


class PackageError(Exception):
    """Raised when word/document.xml — the one required part — is missing or
    the archive is not a valid zip. Every other tracked part degrades to None
    rather than raising; a .docx with no comments.xml is not malformed, it
    simply has no comments."""


class DocxPackage:
    """Lazy, cached access to a .docx's XML parts and media bytes.

    Constructed once per document and threaded through the structure/
    comments/revisions/images passes (stages 3-6) so the zip is opened once.
    """

    def __init__(self, docx_bytes: bytes):
        self._bytes = docx_bytes
        try:
            self._zip = zipfile.ZipFile(io.BytesIO(docx_bytes))
        except zipfile.BadZipFile as exc:
            raise PackageError(f"Not a valid .docx (bad zip): {exc}") from exc
        self._xml_cache: dict[str, ET.Element | None] = {}
        self._content_types: tuple[dict[str, str], dict[str, str]] | None = None
        if "word/document.xml" not in self._zip.namelist():
            raise PackageError(
                "word/document.xml is missing — not a valid .docx package "
                "(acquisition may have returned an HTML error page; see "
                "acquire.py's OOXML-magic-bytes check)."
            )

    def has_part(self, part_name: str) -> bool:
        return part_name in self._zip.namelist()

    def read_part(self, part_name: str) -> bytes | None:
        if part_name not in self._zip.namelist():
            return None
        return self._zip.read(part_name)

    def xml(self, key: str) -> ET.Element | None:
        """Parsed root element for one of the named optional parts (see
        _OPTIONAL_XML_PARTS), or None if the part is absent from the package."""
        if key not in _OPTIONAL_XML_PARTS:
            raise KeyError(f"Unknown XML part key {key!r}; add it to _OPTIONAL_XML_PARTS")
        if key not in self._xml_cache:
            data = self.read_part(_OPTIONAL_XML_PARTS[key])
            self._xml_cache[key] = ET.fromstring(data) if data is not None else None
        return self._xml_cache[key]

    def media_names(self) -> list[str]:
        """All part names under word/media/, sorted for deterministic
        iteration (contract §4)."""
        return sorted(n for n in self._zip.namelist() if n.startswith("word/media/"))

    def media_bytes(self, part_name: str) -> bytes:
        return self._zip.read(part_name)

    def document_rels(self) -> dict[str, dict[str, str]]:
        """r:id -> {Type, Target} from word/_rels/document.xml.rels, used to
        resolve a:blip/@r:embed to a word/media/ part name (contract §4)."""
        root = self.xml("document_rels")
        if root is None:
            return {}
        out: dict[str, dict[str, str]] = {}
        for rel in root.findall("pr:Relationship", NS):
            rid = rel.get("Id")
            if rid:
                out[rid] = {
                    "type": rel.get("Type", ""),
                    "target": rel.get("Target", ""),
                }
        return out

    def content_type(self, part_name: str) -> str | None:
        """Declared content type for one zip part, resolved from
        `[Content_Types].xml` -- an `Override` keyed by exact part name takes
        precedence over a `Default` keyed by extension, per OOXML. `None` if
        neither entry exists. Stage docx-images (gts-8uo6) AC #2: an image's
        extension is derived from this, never guessed from the media part's
        own filename alone."""
        if self._content_types is None:
            self._content_types = self._load_content_types()
        overrides, defaults = self._content_types
        part_path = part_name if part_name.startswith("/") else f"/{part_name}"
        if part_path in overrides:
            return overrides[part_path]
        ext = part_name.rsplit(".", 1)[-1].lower() if "." in part_name else ""
        return defaults.get(ext)

    def _load_content_types(self) -> tuple[dict[str, str], dict[str, str]]:
        data = self.read_part("[Content_Types].xml")
        overrides: dict[str, str] = {}
        defaults: dict[str, str] = {}
        if data is None:
            return overrides, defaults
        root = ET.fromstring(data)
        for el in root.findall("ct:Override", NS):
            part_name, ctype = el.get("PartName"), el.get("ContentType")
            if part_name and ctype:
                overrides[part_name] = ctype
        for el in root.findall("ct:Default", NS):
            ext, ctype = el.get("Extension"), el.get("ContentType")
            if ext and ctype:
                defaults[ext.lower()] = ctype
        return overrides, defaults

    def tabs_detected(self):
        """Contract §5: cookie auth cannot reach the Docs API, so this
        pipeline cannot count tabs. Always None ("could not determine"),
        never 0 ("counted zero"). Kept as a method (rather than a bare
        constant import) so a future acquisition tier (contract §7.3 tier 3)
        has one place to override it."""
        return None
