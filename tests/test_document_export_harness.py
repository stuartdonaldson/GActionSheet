"""test_document_export_harness.py -- gts-28hx (docx-harness) and gts-pmga
(docx-structure).

Targeted, offline-only test (no live Google auth): run the CLI end-to-end
against the checked-in golden fixture and assert the result is well-formed
and structurally valid per docs/interfaces/document-export-contract.md.
`TestStructurePass` covers gts-pmga AC #1-#5 (units/blocks/runs/tables/
numbering). `TestCommentAnchoring` covers gts-nxx3 (stage docx-comments)
AC #1-#5. `TestRevisionModel` covers gts-9c8k (stage docx-revisions)
AC #1-#4 (AC #5 is the targeted-gate-only close condition itself).
`TestImageExtraction` covers gts-8uo6 (stage docx-images) AC #1-#5.
`TestEndToEndAcceptance` covers gts-0rho (stage docx-verify) AC #1-#9 --
ONE acceptance pass over the CLI's own artifact + on-disk output, per this
project's testing-emphasis (the CLI is the call-site, the JSON/image files
are the durable state; T17). It deliberately does not re-derive the
per-pass unit coverage above.

Not part of pytest's full-suite live-backend sweep in spirit -- it makes no
network call and needs no fixture doc -- but it lives under tests/ per the
project's `pytest -x` convention (targeted subset gate; Backstop rules,
project CLAUDE.md).
"""
import json
import pathlib
import subprocess
import sys

import pytest

pytestmark = pytest.mark.no_live_session

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "document_export" / "fixtures"
GOLDEN = FIXTURES_DIR / "golden.docx"
GOLDEN_NO_IMAGES = FIXTURES_DIR / "golden-no-images.docx"

sys.path.insert(0, str(REPO_ROOT))

from document_export.build import build_export  # noqa: E402
from document_export.comments import resolve_comments  # noqa: E402
from document_export.package import DocxPackage, PackageError  # noqa: E402
from document_export.images import write_image_files  # noqa: E402
from document_export.schema import (  # noqa: E402
    make_block_id,
    make_image_id,
    make_image_ref,
    make_unit_id,
    sanitize_filename,
    slugify,
)
from document_export.structure import walk_structure  # noqa: E402


def _run_cli(*args: str, cwd: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "export_document.py"), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestCliEndToEndOffline:
    """gts-28hx AC #1 (--from-docx offline path) + AC #6 (targeted,
    fixture-driven, parseable JSON)."""

    def test_cli_runs_against_golden_fixture_and_writes_parseable_json(self, tmp_path):
        result = _run_cli("--docx", str(GOLDEN), "--out-dir", str(tmp_path), cwd=REPO_ROOT)
        assert result.returncode == 0, result.stderr

        json_files = list(tmp_path.glob("*-docx.json"))
        assert len(json_files) == 1, f"expected exactly one *-docx.json, got {json_files}"
        artifact = json.loads(json_files[0].read_text(encoding="utf-8"))

        assert artifact["schema_version"] == "3.0"
        assert artifact["producer"] == "python-document-export"
        assert artifact["document"]["title"] == "golden"

    def test_cli_makes_no_network_call_with_docx_flag(self, tmp_path, monkeypatch):
        """--docx must never reach acquire_docx_by_id (contract §7.3: 'makes
        no network call at all'). Called in-process (not via subprocess) so
        the monkeypatch actually intercepts the call."""
        import document_export.cli as cli_module

        def _fail(*a, **kw):
            raise AssertionError("acquire_docx_by_id must not be called when --docx is given")

        monkeypatch.setattr(cli_module, "acquire_docx_by_id", _fail)
        exit_code = cli_module.main(["--docx", str(GOLDEN), "--out-dir", str(tmp_path)])
        assert exit_code == 0
        assert list(tmp_path.glob("*-docx.json"))

    def test_cli_json_only_suppresses_cached_docx(self, tmp_path):
        result = _run_cli("--docx", str(GOLDEN), "--out-dir", str(tmp_path), "--json-only", cwd=REPO_ROOT)
        assert result.returncode == 0, result.stderr
        assert not list(tmp_path.glob("*.docx"))
        assert list(tmp_path.glob("*-docx.json"))

    def test_cli_rejects_doc_id_and_docx_together(self, tmp_path):
        result = _run_cli("someDocId", "--docx", str(GOLDEN), "--out-dir", str(tmp_path), cwd=REPO_ROOT)
        assert result.returncode != 0

    def test_cli_exits_nonzero_on_malformed_docx(self, tmp_path):
        bad = tmp_path / "not-really.docx"
        bad.write_bytes(b"PK\x03\x04not a real docx")
        result = _run_cli("--docx", str(bad), "--out-dir", str(tmp_path), cwd=REPO_ROOT)
        assert result.returncode == 1
        assert not list(tmp_path.glob("*-docx.json"))


class TestBuildExportPure:
    """build_export is the offline seam (contract §7.2) -- exercised directly,
    not just through the CLI, since stages 3-6 call it the same way."""

    def test_artifact_shape(self):
        artifact = build_export(GOLDEN.read_bytes(), doc_id="abc123", title="Golden Doc")
        assert artifact["schema_version"] == "3.0"
        assert artifact["document"]["id"] == "abc123"
        assert artifact["document"]["title"] == "Golden Doc"
        assert artifact["document"]["source_url"] == "https://docs.google.com/document/d/abc123/edit"
        # stage docx-comments (gts-nxx3): comments -- see TestCommentAnchoring
        # for the anchoring assertions themselves.
        assert len(artifact["comments"]) == 2
        # stage docx-images (gts-8uo6): one inline + one anchored image in
        # the golden fixture -- see TestImageExtraction for the extraction
        # assertions themselves.
        assert len(artifact["document"]["images"]) == 2
        # contract §7.5: omitted entirely (not []) when empty -- this stage
        # does not populate document.toc (TOC diversion is out of scope).
        assert "toc" not in artifact["document"]

    def test_tabs_detected_null_with_warning(self):
        artifact = build_export(GOLDEN.read_bytes())
        assert artifact["diagnostics"]["tabs_detected"] is None
        assert artifact["diagnostics"]["warnings"], "expected a tabs-unknown warning"
        assert "verify what was actually downloaded" in artifact["diagnostics"]["warnings"][0]

    def test_offline_no_docid_falls_back_to_title_or_document(self):
        artifact = build_export(GOLDEN.read_bytes())
        assert artifact["document"]["id"] is None
        assert artifact["document"]["source_url"] is None
        assert artifact["document"]["title"] == "document"

    def test_raises_package_error_on_missing_document_xml(self):
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("not-document.xml", "<root/>")
        with pytest.raises(PackageError):
            build_export(buf.getvalue())

    def test_runs_against_image_free_variant(self):
        artifact = build_export(GOLDEN_NO_IMAGES.read_bytes())
        assert "images" not in artifact["document"]


class TestDocxPackage:
    def test_optional_parts_present_on_golden_fixture(self):
        pkg = DocxPackage(GOLDEN.read_bytes())
        assert pkg.xml("document") is not None
        assert pkg.xml("comments") is not None
        assert pkg.xml("comments_extended") is not None
        assert pkg.xml("numbering") is not None
        assert pkg.xml("styles") is not None
        assert pkg.media_names() == ["word/media/image1.png", "word/media/image2.png"]

    def test_media_absent_on_image_free_variant(self):
        pkg = DocxPackage(GOLDEN_NO_IMAGES.read_bytes())
        assert pkg.media_names() == []

    def test_tabs_detected_always_none(self):
        pkg = DocxPackage(GOLDEN.read_bytes())
        assert pkg.tabs_detected() is None


class TestSchemaHelpers:
    """Contract §1.3 id shapes and §1.2 zero-padded ordinals."""

    def test_block_id_shape(self):
        assert make_block_id("main", 0) == "block__main__000000"
        assert make_block_id("main", 42) == "block__main__000042"

    def test_unit_id_agrees_with_opening_block_ordinal(self):
        unit_id = make_unit_id("main", "heading", "1. Introduction", 3)
        assert unit_id == "main__heading__1-introduction__000003"
        # unit id and its opening block id share the same zero-padded tail.
        assert unit_id.endswith(make_block_id("main", 3).split("__")[-1])

    def test_image_ref_shape(self):
        assert make_image_ref("main", 7, "png") == "img-main-000007.png"

    def test_slugify_matches_gas_normalisation_examples(self):
        assert slugify("1. Introduction") == "1-introduction"
        assert slugify("") == ""
        assert slugify(None) == ""

    def test_sanitize_filename(self):
        assert sanitize_filename('a/b:c*d?e"f<g>h|i') == "a-b-c-d-e-f-g-h-i"
        assert sanitize_filename("") == "document"


def _minimal_docx_with_body_xml(body_xml: str) -> bytes:
    """A .docx with only word/document.xml (no styles/numbering/rels) --
    DocxPackage requires nothing else, and every optional part degrades to
    None. Used for structure-pass cases the golden fixture doesn't carry
    (fixtures/README.md's "Deliberately not included" list)."""
    import io
    import zipfile

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body_xml}<w:sectPr/></w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
    return buf.getvalue()


class TestStructurePass:
    """gts-pmga, stage docx-structure -- AC #1-#5 against the golden fixture
    (real units/blocks/tables/lists) plus two synthetic cases the golden
    fixture doesn't carry (AC #5's soft return, and the no-numbering-part
    fallback for AC #2's "real answer, including null" requirement)."""

    @pytest.fixture(scope="class")
    def artifact(self):
        return build_export(GOLDEN.read_bytes())

    # -- AC #1: units with parent_unit_id hierarchy, blocks with location.

    def test_units_form_expected_parent_hierarchy(self, artifact):
        by_title = {u["title"]: u for u in artifact["units"]}
        assert by_title["Table of Contents"]["parent_unit_id"] is None
        assert by_title["1. Introduction"]["parent_unit_id"] is None
        # "2. Review Comments"/"3. Numbered Steps"/"4. Reference Table"/
        # "5. Figure" are all Heading2 siblings nested under "1. Introduction".
        for title in ("2. Review Comments", "3. Numbered Steps", "4. Reference Table", "5. Figure"):
            assert by_title[title]["parent_unit_id"] == by_title["1. Introduction"]["id"]
        # The Heading3 opened mid-cell in the table is a child of the table's
        # own unit, not a sibling of it.
        assert by_title["Sub-Unit In Cell"]["parent_unit_id"] == by_title["4. Reference Table"]["id"]

    def test_units_ordinal_agrees_with_opening_block(self, artifact):
        intro = next(u for u in artifact["units"] if u["title"] == "1. Introduction")
        assert intro["id"].endswith(intro["blocks"][0]["id"].split("__")[-1])

    def test_blocks_carry_location_with_ordinal_and_segment(self, artifact):
        all_blocks = [b for u in artifact["units"] for b in u["blocks"]]
        assert len(all_blocks) == artifact["diagnostics"]["blocks"] > 0
        ordinals = [b["location"]["ordinal"] for b in all_blocks]
        # AC #1 / contract §1.2: dense, zero-based, document-order.
        assert ordinals == list(range(len(all_blocks)))
        for b in all_blocks:
            assert b["location"]["segment"] == "main"
            assert b["location"]["tab_id"] is None
            assert b["id"] == f"block__main__{b['location']['ordinal']:06d}"

    # -- AC #2: real list numbering, not null.

    def test_ordered_list_numbering_read_from_numbering_xml(self, artifact):
        steps = next(u for u in artifact["units"] if u["title"] == "3. Numbered Steps")
        items = [b for b in steps["blocks"] if b["kind"] == "list_item"]
        assert len(items) == 3
        for item in items:
            assert item["list"] == {"list_id": "1", "nesting_level": 0, "ordered": True}

    def test_list_ordered_is_none_without_numbering_part(self):
        """No word/numbering.xml at all -> "could not be determined", not an
        invented answer -- inferOrderedList_'s retired `return null` becomes
        a real None only when numbering.xml actually resolves it."""
        docx = _minimal_docx_with_body_xml(
            '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
            '<w:r><w:t>Item one</w:t></w:r></w:p>'
        )
        diagnostics = {"blocks": 0, "units": 0, "runs": 0, "explicit_page_breaks": 0}
        pkg = DocxPackage(docx)
        units, _ = walk_structure(pkg, diagnostics)
        block = units[0]["blocks"][0]
        assert block["list"]["ordered"] is None

    # -- AC #3: table blocks carry {row, column}, including after a mid-cell
    # unit switch.

    def test_table_blocks_tagged_row_column(self, artifact):
        table_unit = next(u for u in artifact["units"] if u["title"] == "4. Reference Table")
        by_text = {b["text"]: b["table"] for b in table_unit["blocks"] if b.get("table")}
        assert by_text["Column A"] == {"row": 0, "column": 0}
        assert by_text["Column B"] == {"row": 0, "column": 1}
        assert by_text["Value 1"] == {"row": 1, "column": 0}

    def test_table_tagging_survives_mid_cell_unit_switch(self, artifact):
        # gts-qjkj invariant: the Heading3 "Sub-Unit In Cell" opens a new
        # unit partway through cell (1, 1) -- both it and the body text that
        # follows must still carry {row: 1, column: 1}, not the enclosing
        # table unit's own position.
        sub_unit = next(u for u in artifact["units"] if u["title"] == "Sub-Unit In Cell")
        assert len(sub_unit["blocks"]) == 2
        for block in sub_unit["blocks"]:
            assert block["table"] == {"row": 1, "column": 1}

    # -- AC #4: empty structural arrays omitted, not [].

    def test_empty_structural_arrays_omitted(self, artifact):
        # comment_ids is populated for the two units/blocks stage docx-comments
        # actually anchors a comment to -- see TestCommentAnchoring for that
        # positive case. Every other unit/block here has no comment, so the
        # omission still holds for all of them.
        commented_titles = {"2. Review Comments", "2b. Multi-block Comment"}
        for unit in artifact["units"]:
            assert "color_signals" not in unit
            if unit["title"] not in commented_titles:
                assert "comment_ids" not in unit
            for block in unit["blocks"]:
                if unit["title"] not in commented_titles:
                    assert "comment_ids" not in block
                for run in block["runs"]:
                    assert "evidence" not in run["revision"]
        # A heading-fallback unit's kind_evidence is real (non-empty) on this
        # fixture -- the omission only ever fires on an actually-empty array,
        # never unconditionally strips the key (would defeat AC #4's own
        # "when they would be empty" qualifier).
        toc_unit = next(u for u in artifact["units"] if u["title"] == "Table of Contents")
        assert toc_unit["kind_evidence"] == [
            {"type": "style_pattern", "rule": "heading_style", "named_style": "HEADING_1"}
        ]

    # -- AC #5: soft returns (w:br) survive.

    def test_soft_return_survives_as_newline(self):
        docx = _minimal_docx_with_body_xml(
            "<w:p><w:r><w:t>First line</w:t><w:br/><w:t>Second line</w:t></w:r></w:p>"
        )
        diagnostics = {"blocks": 0, "units": 0, "runs": 0, "explicit_page_breaks": 0}
        pkg = DocxPackage(docx)
        units, _ = walk_structure(pkg, diagnostics)
        block = units[0]["blocks"][0]
        assert block["text"] == "First line\nSecond line"
        # A soft (textWrapping) break must not be counted as an explicit page
        # break (contract §5 -- only w:br w:type="page" counts).
        assert diagnostics["explicit_page_breaks"] == 0

    def test_explicit_page_break_counted_and_excluded_from_text(self):
        docx = _minimal_docx_with_body_xml(
            '<w:p><w:r><w:t>Before</w:t><w:br w:type="page"/><w:t>After</w:t></w:r></w:p>'
        )
        diagnostics = {"blocks": 0, "units": 0, "runs": 0, "explicit_page_breaks": 0}
        pkg = DocxPackage(docx)
        units, _ = walk_structure(pkg, diagnostics)
        block = units[0]["blocks"][0]
        assert block["text"] == "BeforeAfter"
        assert diagnostics["explicit_page_breaks"] == 1

    # -- Diagnostics wiring (walk_structure mutates the shared dict).

    def test_diagnostics_units_blocks_runs_counted(self, artifact):
        assert artifact["diagnostics"]["units"] == len(artifact["units"])
        assert artifact["diagnostics"]["blocks"] == sum(len(u["blocks"]) for u in artifact["units"])
        assert artifact["diagnostics"]["runs"] == sum(
            len(b["runs"]) for u in artifact["units"] for b in u["blocks"]
        )
        assert sanitize_filename(None) == "document"


def _minimal_docx_with_headings(body_xml: str, *, with_drawing_rels: bool = False) -> bytes:
    """A .docx like `_minimal_docx_with_body_xml` but with a real
    word/styles.xml giving "Heading1"/"Heading2" style ids resolvable heading
    levels (via the name-based "heading N" fallback `_load_heading_levels`
    reads when no `w:outlineLvl` is present) -- gts-pczo.2's hierarchy/
    unit-boundary cases need real `heading_level` resolution, which the
    styles-free `_minimal_docx_with_body_xml` can't provide.
    `with_drawing_rels=True` additionally wires a rels part + a fake
    word/media/image1.png so a heading paragraph's `w:drawing` can resolve
    (the "image-only heading still opens its own unit" case
    `_detect_document_unit`'s docstring names)."""
    import io
    import zipfile

    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/></w:style>'
        "</w:styles>"
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<w:body>{body_xml}<w:sectPr/></w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/styles.xml", styles_xml)
        if with_drawing_rels:
            rels_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId9" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                'Target="media/image1.png"/></Relationships>'
            )
            zf.writestr("word/_rels/document.xml.rels", rels_xml)
            zf.writestr("word/media/image1.png", b"\x89PNG\r\n\x1a\nfake-but-present-bytes")
    return buf.getvalue()


_ARTICLE_ONE_P = (
    '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
    "<w:r><w:t>ARTICLE ONE - INTRODUCTION</w:t></w:r></w:p>"
)
# Two consecutive blank heading-styled paragraphs -- no text, no image -- the
# real-world authoring noise gts-pczo.1's "73 empty structural units"
# baseline came from (a stray Enter-after-heading leaving an empty
# Heading-styled line). Two in a row, sharing the same kind+slug fallback
# ("section"), is what reproduces the reported duplicate-id collision:
# each one's unclaimed ordinal is reused by the next thing that asks for
# one -- including the very next blank heading.
_BLANK_HEADING_P = (
    '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr></w:p>'
    '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr></w:p>'
)
# ARTICLE TWO wrapped in a Google-Docs-export `w:sdt` (`goog_rdk_*` tag) --
# the exact shape found in the reviewed document's ARTICLE FOUR paragraph
# (/tmp/export-test, gts-pczo.1) that made the whole paragraph vanish
# because the body-level walk only recursed into "p"/"tbl" tags.
_ARTICLE_TWO_SDT_P = (
    '<w:sdt><w:sdtPr><w:id w:val="1"/><w:tag w:val="goog_rdk_1"/></w:sdtPr><w:sdtContent>'
    '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
    "<w:r><w:t>ARTICLE TWO - MEMBERSHIP</w:t></w:r></w:p>"
    "</w:sdtContent></w:sdt>"
)
_SECTION_ONE_P = (
    '<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr>'
    "<w:r><w:t>Section 1. Eligibility</w:t></w:r></w:p>"
    "<w:p><w:r><w:t>Membership is open to all.</w:t></w:r></w:p>"
)


class TestHierarchyAndUnitBoundaries:
    """gts-pczo.1/gts-pczo.2 -- ARTICLE detection across a Google-Docs-export
    `w:sdt`-wrapped heading paragraph, and the ordinal/duplicate-id and
    empty-unit fallout from a blank heading-styled paragraph, reproduced
    from the shape found in the reviewed document at /tmp/export-test."""

    @pytest.fixture(scope="class")
    def artifact(self):
        docx = _minimal_docx_with_headings(
            _ARTICLE_ONE_P + _BLANK_HEADING_P + _ARTICLE_TWO_SDT_P + _SECTION_ONE_P
        )
        diagnostics = {"blocks": 0, "units": 0, "runs": 0, "explicit_page_breaks": 0}
        pkg = DocxPackage(docx)
        units, _ = walk_structure(pkg, diagnostics)
        return units

    # AC #1: every top-level ARTICLE-style heading is its own unit, with
    # correct child nesting -- no section mis-nested under the wrong ARTICLE.

    def test_sdt_wrapped_article_is_not_dropped(self, artifact):
        titles = [u["title"] for u in artifact]
        assert "ARTICLE TWO - MEMBERSHIP" in titles, (
            "a w:sdt-wrapped heading paragraph (Google Docs export's "
            "goog_rdk_* artifact) must still be walked, not silently skipped"
        )

    def test_sdt_wrapped_article_is_its_own_top_level_unit(self, artifact):
        by_title = {u["title"]: u for u in artifact}
        article_two = by_title["ARTICLE TWO - MEMBERSHIP"]
        assert article_two["kind"] == "article"
        assert article_two["parent_unit_id"] is None

    def test_section_nests_under_the_sdt_wrapped_article_not_the_prior_one(self, artifact):
        by_title = {u["title"]: u for u in artifact}
        article_one = by_title["ARTICLE ONE - INTRODUCTION"]
        article_two = by_title["ARTICLE TWO - MEMBERSHIP"]
        section = by_title["Section 1. Eligibility"]
        assert section["parent_unit_id"] == article_two["id"]
        assert section["parent_unit_id"] != article_one["id"]

    # AC #2: zero duplicate unit IDs.

    def test_no_duplicate_unit_ids(self, artifact):
        ids = [u["id"] for u in artifact]
        assert len(ids) == len(set(ids)), f"duplicate unit ids: {sorted(ids)}"

    # AC #3: the blank heading-styled paragraph does not open its own
    # (empty) unit at all -- root-caused and eliminated, not merely reduced.

    def test_blank_heading_paragraph_opens_no_unit(self, artifact):
        assert all(u["title"] != "" for u in artifact)
        assert not any(not u["blocks"] for u in artifact), (
            "a heading-styled paragraph with no text and no image must not "
            "open a structural unit"
        )

    # Companion positive case: an image-only heading (no text, but a real
    # w:drawing) is the documented, intentional exception -- _detect_
    # document_unit's docstring names it explicitly -- so it must still
    # open its own unit even after AC #3's blank-heading suppression.

    def test_image_only_heading_still_opens_its_own_unit(self):
        docx = _minimal_docx_with_headings(
            '<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:drawing>'
            '<wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
            '<wp:extent cx="914400" cy="457200"/><wp:docPr id="1" name="Test Picture"/>'
            '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:blipFill><a:blip r:embed="rId9"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            "</pic:pic></a:graphicData></a:graphic></wp:inline>"
            "</w:drawing></w:r></w:p>",
            with_drawing_rels=True,
        )
        diagnostics = {
            "blocks": 0, "units": 0, "runs": 0, "explicit_page_breaks": 0,
            "images": 0, "warnings": [],
        }
        pkg = DocxPackage(docx)
        units, _ = walk_structure(pkg, diagnostics)
        assert len(units) == 1
        assert units[0]["kind"] == "section"


def _minimal_docx_with_comments(body_xml: str, comments_xml: str, comments_extended_xml: str | None = None) -> bytes:
    """A .docx with word/document.xml + word/comments.xml (+ optionally
    commentsExtended.xml) and nothing else -- DocxPackage degrades every
    other optional part to None. Used for anchor_basis cases the golden
    fixture doesn't carry (no_range, range_unterminated on a non-reply
    comment)."""
    import io
    import zipfile

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body_xml}<w:sectPr/></w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/comments.xml", comments_xml)
        if comments_extended_xml is not None:
            zf.writestr("word/commentsExtended.xml", comments_extended_xml)
    return buf.getvalue()


class TestCommentAnchoring:
    """gts-nxx3, stage docx-comments -- AC #1-#5 against the golden fixture's
    two comments (a same-paragraph range with a threaded, resolved reply;
    and a range spanning two paragraphs) plus two synthetic cases the golden
    fixture doesn't carry (no_range, range_unterminated on a non-reply
    comment)."""

    @pytest.fixture(scope="class")
    def artifact(self):
        return build_export(GOLDEN.read_bytes())

    # -- AC #1: every comment anchors to at least one block id; no unmatched
    # bucket (the value itself must not appear anywhere in the pipeline).

    def test_comments_have_no_unmatched_bucket(self, artifact):
        for comment in artifact["comments"]:
            assert comment["anchor_basis"] != "unmatched"
            assert "association_basis" not in comment
        assert "unmatched_comments" not in artifact["diagnostics"]

    def test_same_paragraph_range_anchors_exactly(self, artifact):
        comment = next(c for c in artifact["comments"] if c["id"] == "0")
        assert comment["anchor_basis"] == "range_exact"
        assert comment["associated_block_ids"] == ["block__main__000006"]
        review_unit = next(u for u in artifact["units"] if u["title"] == "2. Review Comments")
        assert comment["associated_unit_ids"] == [review_unit["id"]]
        assert review_unit["comment_ids"] == ["0"]
        commented_block = next(b for b in review_unit["blocks"] if b["id"] == "block__main__000006")
        assert commented_block["comment_ids"] == ["0"]

    # -- AC #2: author/timestamp are the XML facts, not inferred.

    def test_author_and_timestamp_are_xml_facts(self, artifact):
        comment = next(c for c in artifact["comments"] if c["id"] == "0")
        assert comment["author"] == "Alex Reviewer"
        assert comment["created_at"] == "2026-08-20T10:00:00Z"

    # -- AC #3: threading/reply structure from commentsExtended.xml.

    def test_reply_is_threaded_under_parent_not_a_top_level_comment(self, artifact):
        top_level_ids = {c["id"] for c in artifact["comments"]}
        assert "1" not in top_level_ids  # the reply is nested, not a sibling.
        parent = next(c for c in artifact["comments"] if c["id"] == "0")
        assert len(parent["replies"]) == 1
        reply = parent["replies"][0]
        assert reply["id"] == "1"
        assert reply["author"] == "Sam Author"
        assert reply["content"] == "Confirmed with legal, thanks -- resolving."

    # -- AC #4: a range spanning more than one paragraph -> ONE comment
    # record, N block ids, in traversal order.

    def test_multiblock_range_yields_one_record_n_block_ids(self, artifact):
        comment = next(c for c in artifact["comments"] if c["id"] == "2")
        assert comment["anchor_basis"] == "range_multiblock"
        assert len(comment["associated_block_ids"]) == 2
        # traversal order: the first-paragraph block precedes the second.
        block_by_id = {b["id"]: b for u in artifact["units"] for b in u["blocks"]}
        first, second = (block_by_id[bid] for bid in comment["associated_block_ids"])
        assert first["location"]["ordinal"] < second["location"]["ordinal"]
        # exactly one comment record -- splitting into two is prohibited
        # (contract §2.2).
        assert sum(1 for c in artifact["comments"] if c["id"] == "2") == 1

    # -- AC #5: resolved-comment behavior established: a resolved comment
    # (the reply, w15:done="1") is present with resolved information, not
    # silently omitted; an unresolved root reports resolved: false, not null.

    def test_resolved_state_present_when_commentsextended_present(self, artifact):
        parent = next(c for c in artifact["comments"] if c["id"] == "0")
        assert parent["resolved"] is False  # w15:done="0" on its own paraId.

    def test_resolved_null_when_commentsextended_absent(self):
        docx = _minimal_docx_with_comments(
            '<w:p><w:commentRangeStart w:id="0"/><w:r><w:t>Text</w:t></w:r>'
            '<w:commentRangeEnd w:id="0"/><w:r><w:commentReference w:id="0"/></w:r></w:p>',
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">'
            '<w:comment w:id="0" w:author="A" w:date="2026-08-20T10:00:00Z">'
            '<w:p w14:paraId="00000001"><w:r><w:t>c</w:t></w:r></w:p></w:comment></w:comments>',
        )
        pkg = DocxPackage(docx)
        diagnostics = {"comments": 0, "unresolved_comments": 0, "unanchored_comments": 0, "warnings": []}
        units, _ = walk_structure(pkg, {"blocks": 0, "units": 0, "runs": 0, "explicit_page_breaks": 0})
        comments = resolve_comments(pkg, units, diagnostics)
        assert comments[0]["resolved"] is None  # unknown, never coerced to False.

    # -- anchor_basis fail-closed states not exercised by the golden fixture.

    def test_no_range_when_comment_has_no_range_markers(self):
        docx = _minimal_docx_with_comments(
            "<w:p><w:r><w:t>No markers here.</w:t></w:r></w:p>",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">'
            '<w:comment w:id="5" w:author="A" w:date="2026-08-20T10:00:00Z">'
            '<w:p w14:paraId="00000009"><w:r><w:t>orphaned</w:t></w:r></w:p></w:comment></w:comments>',
        )
        pkg = DocxPackage(docx)
        diagnostics = {"comments": 0, "unresolved_comments": 0, "unanchored_comments": 0, "warnings": []}
        units, _ = walk_structure(pkg, {"blocks": 0, "units": 0, "runs": 0, "explicit_page_breaks": 0})
        comments = resolve_comments(pkg, units, diagnostics)
        assert comments[0]["anchor_basis"] == "no_range"
        assert comments[0]["associated_block_ids"] == []
        assert comments[0]["quoted_text"] is None
        assert diagnostics["unanchored_comments"] == 1
        assert diagnostics["warnings"], "expected a no_range/unterminated warning"

    def test_range_unterminated_when_end_marker_missing(self):
        docx = _minimal_docx_with_comments(
            '<w:p><w:commentRangeStart w:id="7"/><w:r><w:t>Never closed</w:t></w:r>'
            '<w:r><w:commentReference w:id="7"/></w:r></w:p>',
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">'
            '<w:comment w:id="7" w:author="A" w:date="2026-08-20T10:00:00Z">'
            '<w:p w14:paraId="00000009"><w:r><w:t>c</w:t></w:r></w:p></w:comment></w:comments>',
        )
        pkg = DocxPackage(docx)
        diagnostics = {"comments": 0, "unresolved_comments": 0, "unanchored_comments": 0, "warnings": []}
        units, _ = walk_structure(pkg, {"blocks": 0, "units": 0, "runs": 0, "explicit_page_breaks": 0})
        comments = resolve_comments(pkg, units, diagnostics)
        assert comments[0]["anchor_basis"] == "range_unterminated"
        assert len(comments[0]["associated_block_ids"]) == 1
        assert diagnostics["unanchored_comments"] == 1

    # -- gts-ipot regression: a comment range anchored on a revision-bearing
    # block (all_text/baseline_text/proposed_text trio, no `text` key --
    # contract §13.3) must resolve, not crash. Neither TestCommentAnchoring
    # nor TestRevisionModel exercised the two passes' intersection before
    # this, and the golden fixture's comments never overlap its revision
    # paragraphs -- found live against a real corpus document.

    def test_comment_range_on_revision_bearing_block_does_not_crash(self):
        docx = _minimal_docx_with_comments(
            '<w:p><w:commentRangeStart w:id="9"/>'
            '<w:ins w:id="1" w:author="Ada" w:date="2026-01-01T00:00:00Z">'
            "<w:r><w:t>Inserted text</w:t></w:r></w:ins>"
            '<w:commentRangeEnd w:id="9"/><w:r><w:commentReference w:id="9"/></w:r></w:p>',
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">'
            '<w:comment w:id="9" w:author="A" w:date="2026-08-20T10:00:00Z">'
            '<w:p w14:paraId="00000009"><w:r><w:t>c</w:t></w:r></w:p></w:comment></w:comments>',
        )
        pkg = DocxPackage(docx)
        diagnostics = {
            "comments": 0, "unresolved_comments": 0, "unanchored_comments": 0, "warnings": [],
            "proposed_insertions": 0, "suggested_deletions": 0,
        }
        units, _ = walk_structure(pkg, {
            "blocks": 0, "units": 0, "runs": 0, "explicit_page_breaks": 0,
            "proposed_insertions": 0, "suggested_deletions": 0,
        })
        block = units[0]["blocks"][0]
        assert "text" not in block  # precondition for this regression -- see structure.py §13.3.
        comments = resolve_comments(pkg, units, diagnostics)  # pre-fix: KeyError: 'text'
        assert comments[0]["anchor_basis"] == "range_exact"
        assert comments[0]["associated_block_ids"] == [block["id"]]
        assert comments[0]["quoted_text"] == "Inserted text"

    # -- diagnostics wiring.

    def test_diagnostics_comment_counts(self, artifact):
        assert artifact["diagnostics"]["comments"] == 2  # roots only, replies nest.
        assert artifact["diagnostics"]["unresolved_comments"] == 2  # both roots done="0".
        assert artifact["diagnostics"]["unanchored_comments"] == 0
        assert "unmatched_comments" not in artifact["diagnostics"]


class TestRevisionModel:
    """gts-9c8k, stage docx-revisions -- AC #1-#4 against the golden
    fixture's two revision paragraphs (a mixed insertion+deletion paragraph,
    and a paragraph that is entirely inserted-then-deleted) plus two
    synthetic cases the golden fixture doesn't carry on their own
    (insertions-only, deletions-only -- the golden fixture's only plain
    insertion/deletion runs share a paragraph, so it never exercises either
    in isolation). AC #5 (targeted gate, regression=pending on close) is the
    stage's own close condition, not a test."""

    @pytest.fixture(scope="class")
    def artifact(self):
        return build_export(GOLDEN.read_bytes())

    @pytest.fixture(scope="class")
    def artifact_with_views(self):
        return build_export(GOLDEN.read_bytes(), options={"includeWholeDocumentViews": True})

    def _blocks(self, artifact):
        return [b for u in artifact["units"] for b in u["blocks"]]

    # -- AC #1: insertions-only, deletions-only, mixed -> correct
    # revision_summary + all_text/baseline_text/proposed_text trio, `text`
    # absent. Unchanged blocks are the mirror image (`text` present, trio
    # absent) -- already covered by TestStructurePass but reasserted here as
    # this stage's own baseline.

    def test_insertions_only_block(self):
        docx = _minimal_docx_with_body_xml(
            '<w:p><w:ins w:id="1" w:author="Ada" w:date="2026-01-01T00:00:00Z">'
            "<w:r><w:t>New text</w:t></w:r></w:ins></w:p>"
        )
        diagnostics = {
            "blocks": 0, "units": 0, "runs": 0, "explicit_page_breaks": 0,
            "proposed_insertions": 0, "suggested_deletions": 0,
        }
        block = walk_structure(DocxPackage(docx), diagnostics)[0][0]["blocks"][0]
        assert block["revision_summary"] == "insertions"
        assert "text" not in block
        assert block["all_text"] == "New text"
        assert block["baseline_text"] == ""
        assert block["proposed_text"] == "New text"
        assert diagnostics["proposed_insertions"] == 1
        assert diagnostics["suggested_deletions"] == 0

    def test_deletions_only_block(self):
        docx = _minimal_docx_with_body_xml(
            '<w:p><w:del w:id="2" w:author="Bea" w:date="2026-01-02T00:00:00Z">'
            "<w:r><w:delText>Old text</w:delText></w:r></w:del></w:p>"
        )
        diagnostics = {
            "blocks": 0, "units": 0, "runs": 0, "explicit_page_breaks": 0,
            "proposed_insertions": 0, "suggested_deletions": 0,
        }
        block = walk_structure(DocxPackage(docx), diagnostics)[0][0]["blocks"][0]
        assert block["revision_summary"] == "deletions"
        assert "text" not in block
        assert block["all_text"] == "Old text"
        assert block["baseline_text"] == "Old text"
        assert block["proposed_text"] == ""
        assert diagnostics["proposed_insertions"] == 0
        assert diagnostics["suggested_deletions"] == 1

    def test_mixed_insertion_and_deletion_block(self, artifact):
        block = next(
            b for b in self._blocks(artifact)
            if b.get("all_text", "").startswith("The system shall")
        )
        assert block["revision_summary"] == "mixed"
        assert "text" not in block
        assert block["all_text"] == "The system shall always process requests within one business day."
        # baseline keeps the suggested deletion (still in the baseline until
        # accepted) and drops the proposed insertion; proposed is the mirror.
        assert block["baseline_text"] == "The system shall process requests within one business day."
        assert block["proposed_text"] == "The system shall always process requests."

    def test_inserted_then_deleted_block_is_mixed_and_excluded_from_both_views(self, artifact):
        # Contract §3.2: a block containing an inserted_then_deleted run is
        # always "mixed", and that run contributes to neither baseline_text
        # nor proposed_text -- "never in the baseline and is not proposed".
        block = next(
            b for b in self._blocks(artifact)
            if b.get("all_text") == "Draft note removed before acceptance."
        )
        assert block["revision_summary"] == "mixed"
        assert "text" not in block
        assert block["baseline_text"] == ""
        assert block["proposed_text"] == ""
        run = block["runs"][0]
        assert run["revision"]["change"] == "inserted_then_deleted"

    def test_unchanged_block_carries_text_not_the_trio(self, artifact):
        block = next(b for b in self._blocks(artifact) if b["kind"] == "heading" and b.get("text") == "1. Introduction")
        assert block["revision_summary"] == "unchanged"
        assert "all_text" not in block
        assert "baseline_text" not in block
        assert "proposed_text" not in block

    # -- AC #2: every revision-bearing run carries a real author/date;
    # possible_authors is retired, not ported.

    def test_revision_bearing_runs_carry_real_author_and_date(self, artifact):
        block = next(
            b for b in self._blocks(artifact)
            if b.get("all_text", "").startswith("The system shall")
        )
        by_text = {r["text"]: r["revision"] for r in block["runs"]}
        assert by_text["always "]["author"] == "Diane Slota"
        assert by_text["always "]["date"] == "2026-08-18T09:00:00Z"
        assert by_text[" within one business day"]["author"] == "Diane Slota"
        assert by_text[" within one business day"]["date"] == "2026-08-18T09:05:00Z"
        # Unchanged runs carry no author/date at all -- only revision-bearing
        # runs do (contract §3.3's literal "each REVISION-BEARING run...").
        assert "author" not in by_text["process requests"]
        assert "date" not in by_text["process requests"]

    def test_possible_authors_does_not_appear_anywhere(self, artifact):
        assert "possible_authors" not in json.dumps(artifact)

    def test_suggestion_authorship_is_a_fact(self, artifact):
        assert artifact["suggestion_authorship"] == {
            "resolvable": True,
            "basis": "ooxml_w_ins_w_del_author",
        }

    # -- AC #3: document.revision_groups groups revisions by (author, date)
    # identity, with real authorship attached. ADR-0029 renamed the field
    # from document.suggestion_groups; regenerated here per the ADR's own
    # Consequences section rather than patched field-by-field.

    def test_revision_groups_grouped_by_author_and_date(self, artifact):
        groups = artifact["document"]["revision_groups"]
        assert len(groups) == 3  # insertion, deletion, inserted-then-deleted -- three distinct dates.
        for g in groups:
            assert g["author"] == "Diane Slota"
            assert "possible_authors" not in g
            assert g["run_count"] == 1
        by_date = {g["date"]: g for g in groups}
        assert by_date["2026-08-18T09:00:00Z"]["block_ids"][0].endswith("000003")  # the insertion's block.
        assert by_date["2026-08-18T09:05:00Z"]["block_ids"][0].endswith("000003")  # the deletion's block.
        assert by_date["2026-08-18T09:12:00Z"]["block_ids"][0].endswith("000004")  # inserted-then-deleted's block.
        assert artifact["diagnostics"]["distinct_revision_group_ids"] == 3

    # -- AC #4: top-level views.baseline_text/proposed_text reconstruct
    # correctly across a document mixing changed and unchanged blocks,
    # proving the fallback to block.text works (§13.1/§13.2).

    def test_whole_document_views_opt_in_and_reconstruct_correctly(self, artifact, artifact_with_views):
        # Default (includeWholeDocumentViews unset) -- deleted_text/
        # proposed_additions always present, baseline_text/proposed_text
        # absent.
        assert artifact["views"]["deleted_text"] == " within one business day"
        assert artifact["views"]["proposed_additions"] == "always "
        assert "baseline_text" not in artifact["views"]
        assert "proposed_text" not in artifact["views"]

        # Opt-in -- whole-document reconstructions, one line per block,
        # falling back to the canonical `text` field for every unchanged
        # block (most of the document) and using the revision-filtered trio
        # only for the two revision-bearing blocks.
        views = artifact_with_views["views"]
        baseline_lines = views["baseline_text"].split("\n")
        proposed_lines = views["proposed_text"].split("\n")
        assert "The system shall process requests within one business day." in baseline_lines
        assert "The system shall always process requests." in proposed_lines
        # The inserted-then-deleted-only paragraph contributes nothing to
        # either reconstruction (its baseline_text/proposed_text are "",
        # filtered out by the join's blank-line skip) -- unlike unchanged
        # blocks elsewhere in the document, which appear in both.
        assert "1. Introduction" in baseline_lines
        assert "1. Introduction" in proposed_lines
        assert "Draft note removed before acceptance." not in baseline_lines
        assert "Draft note removed before acceptance." not in proposed_lines


class TestADR0029FactualRevisions:
    """gts-pczo.4 -- twin [TST] for gts-pczo.3 (ADR-0029: revisions and
    unit/block classification are OOXML facts only, no semantic-
    interpretation layer). Authored against docs/interfaces/document-
    export-contract.md §3.2/§3.3/§6 and ADR-0029 only, no shared context
    with the [IMP] bead.

    AC #5 note: as of this bead, every assertion below is proven to fail
    against the pre-ADR-0029 export -- confirmed by running this class
    (`pytest tests/test_document_export_harness.py -k ADR0029Factual`)
    before gts-pczo.3 lands. `TestRevisionModel.test_suggestion_groups_
    grouped_by_author_and_date` (this file) and any golden-fixture JSON
    under document_export/fixtures/ asserting the pre-3.1 shape are exactly
    the fixtures ADR-0029's Consequences section calls out as needing
    regeneration, not field-by-field patching -- gts-pczo.3's job, not
    this bead's."""

    @pytest.fixture(scope="class")
    def artifact(self):
        return build_export(GOLDEN.read_bytes())

    def _blocks(self, artifact):
        return [b for u in artifact["units"] for b in u["blocks"]]

    def _runs(self, artifact):
        return [r for b in self._blocks(artifact) for r in b["runs"]]

    # -- AC #1: document.revision_groups present, document.suggestion_groups
    # absent, on a fixture with tracked-change activity (the golden fixture
    # carries insertion/deletion/inserted-then-deleted runs -- TestRevisionModel).

    def test_revision_groups_present_suggestion_groups_absent(self, artifact):
        document = artifact["document"]
        assert "revision_groups" in document, (
            "contract §3.3 (ADR-0029): document.suggestion_groups is "
            "renamed document.revision_groups"
        )
        assert "suggestion_groups" not in document, (
            "ADR-0029 Decision 1: suggestion_groups is retired, not kept "
            "alongside the rename"
        )
        # Grouping key/membership are unchanged by the rename (author, date).
        groups = document["revision_groups"]
        assert len(groups) == 3
        for g in groups:
            assert g["author"] == "Diane Slota"
            assert "possible_authors" not in g

    # -- AC #2: no run object in the export carries a `state` key.

    def test_no_run_carries_a_state_key(self, artifact):
        revision_bearing = [r for r in self._runs(artifact) if "revision" in r]
        assert revision_bearing, "fixture must exercise at least one revision-bearing run"
        for run in revision_bearing:
            assert "state" not in run["revision"], (
                "ADR-0029 Decision 3: revision.state is removed; "
                f"revision.change ({run['revision'].get('change')!r}) is the single fact"
            )

    # -- AC #3: no unit/block carries semantic_state/semantic_state_evidence,
    # and top-level `semantics` is absent, on a fixture containing the
    # (OLD)/TBD/FYI-style markers ADR-0029 Context names as the classifier's
    # trigger surface (`_detect_semantic_state`, document_export/structure.py).

    def test_no_semantic_state_anywhere_on_marker_bearing_fixture(self):
        docx = _minimal_docx_with_body_xml(
            "<w:p><w:r><w:t>(OLD) This clause is superseded.</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>TBD -- pending legal review.</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>FYI: informational only, ???</w:t></w:r></w:p>"
        )
        diagnostics = {"blocks": 0, "units": 0, "runs": 0, "explicit_page_breaks": 0}
        pkg = DocxPackage(docx)
        units, _ = walk_structure(pkg, diagnostics)
        dumped = json.dumps(units)
        assert "semantic_state" not in dumped, (
            "ADR-0029 Decision 2: semantic_state/semantic_state_evidence "
            "removed document-wide, including semantic_state_evidence "
            "(substring-covered by the same check)"
        )
        for unit in units:
            assert "semantic_state" not in unit
            assert "semantic_state_evidence" not in unit
            assert unit["kind"] not in ("historical_note", "editorial_note"), (
                "ADR-0029 Decision 2: historical_note/editorial_note block "
                "kinds are retired on this path"
            )
            for block in unit["blocks"]:
                assert "semantic_state" not in block
                assert "semantic_state_evidence" not in block
                assert block["kind"] not in ("historical_note", "editorial_note")

    def test_top_level_semantics_absent(self, artifact):
        assert "semantics" not in artifact, (
            "ADR-0029 Decision 2: the top-level semantics object "
            "(baseline/proposed/historical/editorial) is removed"
        )

    # -- AC #4: schema_version reports 3.1.

    def test_schema_version_is_3_1(self, artifact):
        assert artifact["schema_version"] == "3.1", (
            "contract §6 (ADR-0029): schema version bumps 3.0 -> 3.1 for "
            "the revision_groups rename + state/semantic_state/semantics removal"
        )


def _minimal_docx_with_drawing(
    *, embed_rid: str | None, content_types_override: str | None = None, with_alt: bool = True
) -> bytes:
    """A .docx with one inline w:drawing and, unless `embed_rid` is None, a
    matching word/media/ part + relationship. Passing an `embed_rid` that
    doesn't match the relationship's own id (or None, meaning "no
    a:blip/@r:embed at all") produces an unresolvable drawing -- the
    fail-closed/skip-with-warning path (fixtures README's "Deliberately not
    included"). `content_types_override`, if given, replaces the Default
    png->image/png mapping with an Override on word/media/image1.png so AC #2
    (content-type-derived, not filename-guessed, extension) can be exercised
    against a part whose declared type disagrees with its own filename.
    `with_alt=False` omits docPr's title/descr entirely (gts-0rho AC #6(c):
    alt_title/alt_description must be null, not fabricated, when the source
    carries no alt text)."""
    import io
    import zipfile

    blip = f'<a:blip r:embed="{embed_rid}"/>' if embed_rid else "<a:blip/>"
    doc_pr = (
        '<wp:docPr id="1" name="Test Picture" title="A title" descr="A description"/>'
        if with_alt else '<wp:docPr id="1" name="Test Picture"/>'
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<w:body><w:p><w:r><w:drawing>"
        '<wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
        '<wp:extent cx="914400" cy="457200"/>'
        f"{doc_pr}"
        '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f"<pic:blipFill>{blip}<a:stretch><a:fillRect/></a:stretch></pic:blipFill>"
        "</pic:pic></a:graphicData></a:graphic></wp:inline>"
        "</w:drawing></w:r></w:p><w:sectPr/></w:body></w:document>"
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId9" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        'Target="media/image1.png"/></Relationships>'
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        + (content_types_override or '<Default Extension="png" ContentType="image/png"/>')
        + "</Types>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/_rels/document.xml.rels", rels_xml)
        zf.writestr("word/media/image1.png", b"\x89PNG\r\n\x1a\nfake-but-present-bytes")
    return buf.getvalue()


class TestImageExtraction:
    """gts-8uo6, stage docx-images -- AC #1-#5 against the golden fixture
    (one inline + one anchored drawing) plus synthetic-fixture cases for
    AC #2's content-type-vs-filename distinction and the unresolvable-
    drawing skip path (fixtures README's "Deliberately not included"). AC #6
    (targeted gate, regression=pending on close) is the stage's own close
    condition, not a test."""

    @pytest.fixture(scope="class")
    def artifact(self):
        return build_export(GOLDEN.read_bytes(), doc_id="golden-doc")

    def _image_blocks(self, artifact):
        return [b for u in artifact["units"] for b in u["blocks"] if b["kind"] == "image"]

    # -- AC #1: every w:drawing (inline AND anchored) produces an image
    # block with a stable image_ref and a matching document.images[] entry.

    def test_inline_and_anchored_drawings_both_produce_image_blocks(self, artifact):
        blocks = self._image_blocks(artifact)
        assert len(blocks) == 2
        assert [b["anchored"] for b in blocks] == [False, True]
        assert artifact["diagnostics"]["images"] == 2

    def test_image_block_matches_document_images_entry(self, artifact):
        blocks = {b["image_ref"]: b for b in self._image_blocks(artifact)}
        entries = {e["image_ref"]: e for e in artifact["document"]["images"]}
        assert set(blocks) == set(entries)
        for image_ref, block in blocks.items():
            entry = entries[image_ref]
            assert entry["source_part"] == block["source_part"]
            assert entry["anchored"] == block["anchored"]
            assert entry["location"] == block["location"]
            assert entry["id"] == make_image_id("main", block["location"]["ordinal"])
            assert block["id"] == make_block_id("main", block["location"]["ordinal"])

    def test_two_drawings_referencing_distinct_media_parts_get_distinct_refs(self, artifact):
        blocks = self._image_blocks(artifact)
        assert blocks[0]["source_part"] == "word/media/image1.png"
        assert blocks[1]["source_part"] == "word/media/image2.png"
        assert blocks[0]["image_ref"] != blocks[1]["image_ref"]

    # -- AC #2: extension is derived from the media part's declared content
    # type ([Content_Types].xml), never guessed from its own filename.

    def test_extension_derived_from_content_type_default_entry(self):
        docx = _minimal_docx_with_drawing(embed_rid="rId9")
        artifact = build_export(docx)
        assert artifact["document"]["images"][0]["image_ref"].endswith(".png")

    def test_extension_follows_override_even_when_filename_disagrees(self):
        # word/media/image1.png declared image/jpeg via an Override -- the
        # part's own ".png" filename must not win.
        docx = _minimal_docx_with_drawing(
            embed_rid="rId9",
            content_types_override='<Override PartName="/word/media/image1.png" ContentType="image/jpeg"/>',
        )
        artifact = build_export(docx)
        assert artifact["document"]["images"][0]["image_ref"].endswith(".jpg")

    # -- AC #3: description is null on every entry.

    def test_description_always_null(self, artifact):
        for block in self._image_blocks(artifact):
            assert block["description"] is None

    # -- AC #4: negative -- a document with no images omits document.images
    # entirely (key absent), not [].

    def test_no_images_document_omits_document_images_key(self):
        artifact = build_export(GOLDEN_NO_IMAGES.read_bytes())
        assert "images" not in artifact["document"]
        assert artifact["diagnostics"]["images"] == 0

    def test_include_images_false_suppresses_extraction_even_with_images_present(self, artifact):
        suppressed = build_export(GOLDEN.read_bytes(), options={"includeImages": False})
        assert "images" not in suppressed["document"]
        assert suppressed["diagnostics"]["images"] == 0
        # No ordinals consumed for the two drawings -- every other block's
        # count is unaffected, as if the drawings were never there at all.
        assert (
            suppressed["diagnostics"]["blocks"]
            == artifact["diagnostics"]["blocks"] - len(self._image_blocks(artifact))
        )

    # -- AC #5: idempotency -- re-running against the same .docx bytes
    # produces identical image_ref names (stable, ordinal-derived).

    def test_rerun_produces_identical_image_refs(self):
        first = build_export(GOLDEN.read_bytes())["document"]["images"]
        second = build_export(GOLDEN.read_bytes())["document"]["images"]
        assert [e["image_ref"] for e in first] == [e["image_ref"] for e in second]
        assert [e["id"] for e in first] == [e["id"] for e in second]

    # -- Fail-closed: a drawing whose blip cannot be resolved to a present
    # word/media/ part is skipped entirely -- never a block/entry with an
    # image_ref that doesn't correspond to an actual extracted image.

    def test_unresolvable_drawing_skipped_with_warning_not_partially_recorded(self):
        docx = _minimal_docx_with_drawing(embed_rid="rIdDoesNotExist")
        artifact = build_export(docx)
        assert "images" not in artifact["document"]
        assert artifact["diagnostics"]["images"] == 0
        assert any("Test Picture" in w for w in artifact["diagnostics"]["warnings"])

    def test_drawing_with_no_blip_at_all_skipped_with_warning(self):
        docx = _minimal_docx_with_drawing(embed_rid=None)
        artifact = build_export(docx)
        assert "images" not in artifact["document"]
        assert any("Test Picture" in w for w in artifact["diagnostics"]["warnings"])

    # -- write_image_files (cli.py's post-build_export step, contract §4):
    # bytes on disk match the source media part exactly, named by image_ref.

    def test_write_image_files_writes_exact_media_bytes_named_by_ref(self, artifact, tmp_path):
        pkg = DocxPackage(GOLDEN.read_bytes())
        written = write_image_files(pkg, artifact["document"]["images"], tmp_path)
        assert len(written) == 2
        for path, entry in zip(written, artifact["document"]["images"]):
            assert path.name == entry["image_ref"]
            assert path.read_bytes() == pkg.media_bytes(entry["source_part"])

    # -- Regression: an image-only paragraph (no text) must not desync
    # comments.py's paragraph<->block alignment for every text paragraph
    # that follows it. Before this stage's fix, _flatten_blocks_in_order
    # included image blocks, so the image block "meant for" the image-only
    # paragraph (which _paragraph_block_pairs never pulls a block for, since
    # it has no text) was instead handed to the *next* text paragraph's
    # comment-range resolution -- silently wrong association_block_ids.
    def test_comment_after_image_only_paragraph_associates_with_correct_block(self):
        import io
        import zipfile

        document_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<w:body>"
            # Image-only paragraph: produces one image block, no text block.
            "<w:p><w:r><w:drawing>"
            '<wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
            '<wp:extent cx="914400" cy="914400"/><wp:docPr id="1" name="Diagram"/>'
            '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:blipFill><a:blip r:embed="rId9"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            "</pic:pic></a:graphicData></a:graphic></wp:inline>"
            "</w:drawing></w:r></w:p>"
            # Text paragraph immediately after, carrying a comment range.
            "<w:p><w:commentRangeStart w:id=\"0\"/>"
            '<w:r><w:t>Text right after the image</w:t></w:r>'
            '<w:commentRangeEnd w:id="0"/><w:r><w:commentReference w:id="0"/></w:r></w:p>'
            "<w:sectPr/></w:body></w:document>"
        )
        rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId9" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            'Target="media/image1.png"/></Relationships>'
        )
        content_types_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="png" ContentType="image/png"/>'
            "</Types>"
        )
        comments_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">'
            '<w:comment w:id="0" w:author="A" w:date="2026-08-20T10:00:00Z">'
            '<w:p w14:paraId="00000001"><w:r><w:t>c</w:t></w:r></w:p></w:comment></w:comments>'
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("[Content_Types].xml", content_types_xml)
            zf.writestr("word/document.xml", document_xml)
            zf.writestr("word/_rels/document.xml.rels", rels_xml)
            zf.writestr("word/comments.xml", comments_xml)
            zf.writestr("word/media/image1.png", b"\x89PNG\r\n\x1a\nfake")
        docx = buf.getvalue()

        artifact = build_export(docx)
        text_block = next(
            b for u in artifact["units"] for b in u["blocks"] if b["kind"] != "image"
        )
        assert text_block.get("all_text", text_block.get("text")) == "Text right after the image"
        comment = artifact["comments"][0]
        assert comment["associated_block_ids"] == [text_block["id"]]

    # -- Regression: image blocks carry no `text`/`runs` content -- revisions.py's
    # whole-document view reconstruction (opt-in, contract §13.1/§13.2) and
    # suggestion grouping must not choke on that (empty `runs`, no `text` key).
    def test_whole_document_views_and_suggestion_groups_tolerate_image_blocks(self, artifact):
        artifact_with_views = build_export(
            GOLDEN.read_bytes(), options={"includeWholeDocumentViews": True}
        )
        assert isinstance(artifact_with_views["views"]["baseline_text"], str)
        assert isinstance(artifact_with_views["views"]["proposed_text"], str)
        # image blocks contribute nothing (no text) -- not a crash, not a
        # stray "None"/"null" line.
        for block in self._image_blocks(artifact):
            assert block["id"] not in artifact_with_views["views"]["baseline_text"]


# -- gts-0rho AC #2/#3: extracted so AC #9's proven-to-fail requirement can
# call the same assertion logic against both the real artifact (must pass)
# and a deliberately mutated copy (must raise AssertionError) without
# duplicating the assertion body.

def _assert_mid_cell_tagging(artifact):
    sub_unit = next(u for u in artifact["units"] if u["title"] == "Sub-Unit In Cell")
    table_unit = next(u for u in artifact["units"] if u["title"] == "4. Reference Table")
    assert sub_unit["id"] != table_unit["id"]  # AC #2.3: two different units.
    assert len(sub_unit["blocks"]) == 2
    for block in sub_unit["blocks"]:
        assert block["table"] == {"row": 1, "column": 1}  # AC #2.2.


def _assert_block_shape(block):
    # AC #3: schema-3.0 block-level always-present keys -- id/kind/label/
    # named_style/heading_level/list/location/unit_id. gts-e7ca's AC text
    # (inherited verbatim from the GAS-side, schema-2.2 contract) also names
    # title/parent_unit_id; those live on the *unit* in schema 3.0's
    # units/blocks split, not the block -- see this test class's docstring
    # note below.
    for key in ("id", "kind", "label", "named_style", "heading_level", "list", "location", "unit_id"):
        assert key in block
    if block["kind"] == "image":
        # Image blocks carry no text content at all (contract §4) -- the
        # text/trio conditional-emission rule applies only to text-bearing
        # block kinds.
        assert "text" not in block
        assert "all_text" not in block
        return
    if block["revision_summary"] == "unchanged":
        assert "text" in block
        assert "all_text" not in block
        assert "baseline_text" not in block
        assert "proposed_text" not in block
    else:
        assert "text" not in block
        assert "all_text" in block
        assert "baseline_text" in block
        assert "proposed_text" in block


class TestEndToEndAcceptance:
    """gts-0rho, stage docx-verify -- ONE end-to-end acceptance test over the
    CLI's own artifact and on-disk output (contract T17: the CLI is the
    call-site, the JSON + image files are the durable state under test).
    Absorbs gts-qjkj (AC #2, table mid-cell unit-switch tagging) and
    gts-e7ca (AC #3, conditional block-text emission + empty-array omission)
    as assertions here rather than as separate test beads, per this
    project's Testing posture (staging doc, docx-verify stage).

    AC #3 wording note: gts-0rho's AC text names `title`/`parent_unit_id`
    among a block's always-present keys, inherited verbatim from the frozen
    GAS exporter's schema-2.2 contract (gts-e7ca's own pre-code contract).
    Schema 3.0 (docs/interfaces/document-export-contract.md) splits units
    from blocks -- `title`/`parent_unit_id` are unit-level fields, asserted
    separately in `test_ac1_structure_hierarchy_and_real_numbering` below.
    `_assert_block_shape` asserts the schema-3.0 block-level key set that
    actually exists; this is a documentation-inheritance wording gap, not an
    implementation gap -- flagged here for `gts-284o`/`gts-fadg` (stage
    document-rename) rather than filed as its own bead.
    """

    @pytest.fixture(scope="class")
    def export_dir(self, tmp_path_factory):
        out_dir = tmp_path_factory.mktemp("gts-0rho-export")
        result = _run_cli("--docx", str(GOLDEN), "--out-dir", str(out_dir), cwd=REPO_ROOT)
        assert result.returncode == 0, result.stderr
        return out_dir

    @pytest.fixture(scope="class")
    def artifact(self, export_dir):
        json_files = list(export_dir.glob("*-docx.json"))
        assert len(json_files) == 1, f"expected exactly one *-docx.json, got {json_files}"
        return json.loads(json_files[0].read_text(encoding="utf-8"))

    def _all_blocks(self, artifact):
        return [b for u in artifact["units"] for b in u["blocks"]]

    # -- AC #1: structure -- parent_unit_id hierarchy, real (non-null) list
    # numbering.

    def test_ac1_structure_hierarchy_and_real_numbering(self, artifact):
        by_title = {u["title"]: u for u in artifact["units"]}
        assert by_title["1. Introduction"]["parent_unit_id"] is None
        assert by_title["4. Reference Table"]["parent_unit_id"] == by_title["1. Introduction"]["id"]
        assert by_title["Sub-Unit In Cell"]["parent_unit_id"] == by_title["4. Reference Table"]["id"]
        steps = by_title["3. Numbered Steps"]
        list_items = [b for b in steps["blocks"] if b["kind"] == "list_item"]
        assert list_items, "expected at least one list_item block"
        for item in list_items:
            assert item["list"]["ordered"] is True
            assert item["list"]["list_id"] is not None  # real numbering, not null.

    # -- AC #2 (gts-qjkj): mid-cell unit-switch tagging, proven non-vacuous
    # by asserting the switch happened (see AC #9 below for the fail-proof).

    def test_ac2_table_mid_cell_unit_switch_tagging(self, artifact):
        _assert_mid_cell_tagging(artifact)

    # -- AC #3 (gts-e7ca): conditional block-text emission + always-present
    # keys, across every block in the document (not just one hand-picked
    # example) -- and empty structural arrays are absent, not [].

    def test_ac3_block_text_shape_across_every_block(self, artifact):
        blocks = self._all_blocks(artifact)
        assert any(b["revision_summary"] == "unchanged" for b in blocks)
        assert any(b["revision_summary"] != "unchanged" for b in blocks)
        for block in blocks:
            _assert_block_shape(block)

    def test_ac3_empty_structural_arrays_omitted(self, artifact):
        commented_titles = {"2. Review Comments", "2b. Multi-block Comment"}
        for unit in artifact["units"]:
            assert "color_signals" not in unit
            if unit["title"] not in commented_titles:
                assert "comment_ids" not in unit
            for block in unit["blocks"]:
                if unit["title"] not in commented_titles:
                    assert "comment_ids" not in block
                for run in block.get("runs", []):
                    assert "evidence" not in run["revision"]

    # -- AC #4: every comment anchors to a block id with a real author and
    # timestamp; no unmatched bucket exists anywhere in the pipeline.

    def test_ac4_comments_anchor_with_real_author_no_unmatched(self, artifact):
        assert artifact["comments"], "golden fixture must carry at least one comment"
        block_ids = {b["id"] for b in self._all_blocks(artifact)}
        for comment in artifact["comments"]:
            assert comment["anchor_basis"] != "unmatched"
            assert comment["author"]
            assert comment["created_at"]
            for bid in comment["associated_block_ids"]:
                assert bid in block_ids
        assert "unmatched_comments" not in artifact["diagnostics"]

    # -- AC #5: every revision carries a real author; possible_authors is
    # absent from the artifact entirely.

    def test_ac5_revisions_have_real_authors_no_possible_authors(self, artifact):
        revision_runs = [
            r for b in self._all_blocks(artifact) for r in b.get("runs", [])
            if r["revision"]["change"] != "unchanged"
        ]
        assert revision_runs, "golden fixture must carry at least one revision-bearing run"
        for run in revision_runs:
            assert run["revision"]["author"]
            assert run["revision"]["date"]
        assert "possible_authors" not in json.dumps(artifact)

    # -- AC #6: images -- stable image_ref, matching document.images entry,
    # description/alt_description never fabricated; plus (a)-(d) below.

    def test_ac6_images_have_stable_refs_and_matching_document_entries(self, artifact):
        image_blocks = [b for b in self._all_blocks(artifact) if b["kind"] == "image"]
        assert image_blocks, "golden fixture must carry at least one image"
        entries = {e["image_ref"]: e for e in artifact["document"]["images"]}
        for block in image_blocks:
            assert block["image_ref"] in entries
            assert entries[block["image_ref"]]["source_part"] == block["source_part"]

    def test_ac6a_image_files_exist_on_disk_with_image_content_type(self, artifact, export_dir):
        images_dir = export_dir / "golden-images"
        assert images_dir.is_dir(), f"expected {images_dir} to exist"
        for entry in artifact["document"]["images"]:
            path = images_dir / entry["image_ref"]
            assert path.is_file(), f"expected {path} to exist"
            assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"  # real PNG magic bytes.

    def test_ac6b_rerun_produces_identical_image_refs(self, tmp_path_factory):
        out_dir_1 = tmp_path_factory.mktemp("gts-0rho-rerun-1")
        out_dir_2 = tmp_path_factory.mktemp("gts-0rho-rerun-2")
        for out_dir in (out_dir_1, out_dir_2):
            result = _run_cli("--docx", str(GOLDEN), "--out-dir", str(out_dir), cwd=REPO_ROOT)
            assert result.returncode == 0, result.stderr
        refs = []
        for out_dir in (out_dir_1, out_dir_2):
            artifact = json.loads(next(out_dir.glob("*-docx.json")).read_text(encoding="utf-8"))
            refs.append([e["image_ref"] for e in artifact["document"]["images"]])
        assert refs[0] == refs[1]

    def test_ac6c_alt_description_never_fabricated(self, artifact):
        image_blocks = [b for b in self._all_blocks(artifact) if b["kind"] == "image"]
        for block in image_blocks:
            assert block["description"] is None  # never fabricated, per AC #6.
        # Golden fixture's own two images both carry real alt text -- the
        # null-when-absent case (AC #6(c)'s non-vacuous requirement) needs a
        # source with none, so it's exercised against a synthetic fixture
        # instead (same pattern as TestImageExtraction's other synthetic
        # cases).
        no_alt_artifact = build_export(_minimal_docx_with_drawing(embed_rid="rId9", with_alt=False))
        no_alt_block = next(
            b for u in no_alt_artifact["units"] for b in u["blocks"] if b["kind"] == "image"
        )
        assert no_alt_block["alt_title"] is None
        assert no_alt_block["alt_description"] is None
        assert no_alt_block["description"] is None

    def test_ac6d_image_free_document_omits_document_images_key(self, tmp_path_factory):
        out_dir = tmp_path_factory.mktemp("gts-0rho-no-images")
        result = _run_cli("--docx", str(GOLDEN_NO_IMAGES), "--out-dir", str(out_dir), cwd=REPO_ROOT)
        assert result.returncode == 0, result.stderr
        artifact = json.loads(next(out_dir.glob("*-docx.json")).read_text(encoding="utf-8"))
        assert "images" not in artifact["document"]  # key absent, not [].
        assert not list(out_dir.glob("*-images"))  # no images dir written at all.

    # -- AC #7: views.baseline_text / views.proposed_text reconstruct across
    # a mix of changed and unchanged blocks.

    def test_ac7_views_reconstruct_baseline_and_proposed(self, tmp_path_factory):
        out_dir = tmp_path_factory.mktemp("gts-0rho-views")
        result = _run_cli(
            "--docx", str(GOLDEN), "--out-dir", str(out_dir), "--whole-document-views", "--json-only",
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stderr
        artifact = json.loads(next(out_dir.glob("*-docx.json")).read_text(encoding="utf-8"))
        views = artifact["views"]
        baseline_lines = views["baseline_text"].split("\n")
        proposed_lines = views["proposed_text"].split("\n")
        # An unchanged block (falls back to block.text) appears in both.
        assert "1. Introduction" in baseline_lines
        assert "1. Introduction" in proposed_lines
        # A revision-bearing block's baseline/proposed differ from each
        # other -- proving the trio, not block.text, drove the
        # reconstruction for that block.
        assert baseline_lines != proposed_lines

    # -- AC #8: warnings[] present; the tabs warning behaves per gts-28hx.

    def test_ac8_diagnostics_warnings_present_and_tabs_null(self, artifact):
        assert artifact["diagnostics"]["tabs_detected"] is None
        assert artifact["diagnostics"]["warnings"]
        assert any("tab" in w.lower() for w in artifact["diagnostics"]["warnings"])

    # -- AC #9: proven-to-fail -- the mid-cell tagging assertion and a
    # block-shape assertion are demonstrated to raise when their condition is
    # violated, not just to pass as-built (project backstop rule).

    def test_ac9_mid_cell_tagging_assertion_fails_when_violated(self, artifact):
        import copy

        _assert_mid_cell_tagging(artifact)  # passes on the real artifact.
        corrupted = copy.deepcopy(artifact)
        sub_unit = next(u for u in corrupted["units"] if u["title"] == "Sub-Unit In Cell")
        sub_unit["blocks"][0]["table"] = {"row": 0, "column": 0}
        with pytest.raises(AssertionError):
            _assert_mid_cell_tagging(corrupted)

    def test_ac9_block_shape_assertion_fails_when_violated(self, artifact):
        block = next(
            b for b in self._all_blocks(artifact)
            if b["kind"] != "image" and b["revision_summary"] == "unchanged"
        )
        _assert_block_shape(block)  # passes on the real block.
        violated_missing_text = {k: v for k, v in block.items() if k != "text"}
        with pytest.raises(AssertionError):
            _assert_block_shape(violated_missing_text)
        violated_wrong_key_set = dict(block)
        del violated_wrong_key_set["id"]
        with pytest.raises(AssertionError):
            _assert_block_shape(violated_wrong_key_set)
