"""
test_status_icon_size_config.py — [TST] for gts-bxrt.

Regression coverage for the new 'Status Icon Size' Config sheet key
(SyncManager.js's `_resolveStatusIconSize`): the flush-inserted status inline
image's rendered PT size, previously a hardcoded 16 unrelated to any Config
row, is now driven by a fallback chain: Config 'Status Icon Size' ->
ai_token's own configured fontSize -> 11 (Docs' own default), human decision
2026-09-02.

Prior coverage (test_decode_status_icon.py, test_doc_presentation.py) only
asserts `has_status_icon` -- image *presence*, not size -- so none of it
covers this AC; test-functional Step 1 coverage inventory finding: no
coverage of rendered icon dimensions existed before this file.
"""
import json

from scn.session import ScenarioSession

from tests.helpers.doc_inspect import load_doc, status_icon_sizes_pt
from tests.helpers.download import download_docx


def _first_icon_size_pt(scn) -> float:
    doc = load_doc(download_docx(scn.doc_id))
    sizes = status_icon_sizes_pt(doc)
    assert sizes, f"expected at least one inline image in the doc, got none (doc={scn.doc_id})"
    width_pt, height_pt = sizes[0]
    assert abs(width_pt - height_pt) < 0.5, f"status icon not square: {sizes[0]!r}"
    return width_pt


def test_configured_status_icon_size_applies(settings, request):
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        set_size = scn._post_fixture("set_config_row", {"key": "Status Icon Size", "value": 24})
        assert (set_size.get("data") or {}).get("ok"), f"set_config_row(Status Icon Size) failed: {set_size!r}"

        scn._post_fixture("append_doc_soft_paragraph", {"text": "AI: draft the memo"})
        scn.sync()

        size = _first_icon_size_pt(scn)
        assert abs(size - 24) < 0.5, f"expected ~24pt status icon per configured 'Status Icon Size', got {size!r}"
    finally:
        # 'Status Icon Size' lives on the Config sheet of the one shared
        # tracker spreadsheet (same non-per-doc scoping as 'SR Indent' /
        # 'Field SR Indent', see test_continuation_indent_config.py) --
        # leaving it set here leaks a non-default icon size into every other
        # test's flush, and into production, until someone notices. Clear
        # unconditionally, including on assertion failure above.
        scn._post_fixture("clear_config_rows", {})
        scn.close()


def test_status_icon_size_falls_back_to_ai_token_fontsize(settings, request):
    """No 'Status Icon Size' row, but 'ai_token' has a configured fontSize:
    the icon inherits that fontSize rather than any fixed literal."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        ai_token = {
            "fontFamily": "Arial", "fontSize": 20, "color": "#000000",
            "bold": True, "italic": False, "underline": False,
        }
        set_token = scn._post_fixture("set_config_row", {"key": "ai_token", "value": json.dumps(ai_token)})
        assert (set_token.get("data") or {}).get("ok"), f"set_config_row(ai_token) failed: {set_token!r}"

        scn._post_fixture("append_doc_soft_paragraph", {"text": "AI: draft the memo"})
        scn.sync()

        size = _first_icon_size_pt(scn)
        assert abs(size - 20) < 0.5, (
            f"expected status icon to fall back to ai_token.fontSize=20 when 'Status Icon Size' is unset, got {size!r}"
        )
    finally:
        scn._post_fixture("clear_config_rows", {})
        scn.close()


def test_status_icon_size_default_is_11pt(settings, request):
    """Neither Config row set (the untouched default for every other test in
    the suite): the icon falls all the way through to 11pt (Docs' own
    default, matching SyncManager.js's existing `fontSize || 11` fallback
    constant) -- not the previous hardcoded 16, which was never a considered
    default. Restates this bead's own frozen AC #3 as the proof the default
    landed where decided."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture("append_doc_soft_paragraph", {"text": "AI: default icon size base"})
        scn.sync()

        size = _first_icon_size_pt(scn)
        assert abs(size - 11) < 0.5, f"expected 11pt default status icon size with no Config rows set, got {size!r}"
    finally:
        scn.close()
