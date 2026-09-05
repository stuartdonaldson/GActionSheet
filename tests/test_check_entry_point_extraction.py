"""test_check_entry_point_extraction.py — gts-u6ew.11 (H12).

Focused tests for scripts/check_entry_point_extraction.py's pure logic:
extracting handler names from JavaScript sources and an appsscript.json
manifest, and accounting for each against ENTRY_POINT_REGISTRY /
ENTRY_POINT_SOURCE_EXEMPT / ENTRY_POINT_SOURCE_ALIASES. Every function under
test takes already-loaded strings/dicts, same shape as
tests/test_check_entry_point_registry_view.py, tests/test_check_coverage.py
and tests/test_audit_disposition.py.

Coverage inventory (test-functional Step 1, run before authoring):
scripts/check_entry_point_extraction.py is net-new this bead and had no test
file. Its sibling tests/test_check_entry_point_registry_view.py covers the
*view*-vs-registry check (gts-u6ew.10), a different script and a different
failure — nothing to extend; net-new.

Includes the backstop rule's proven-to-fail cases (CLAUDE.md "a new assertion
must be proven to fail before acceptance"), both against the real project
sources rather than only synthetic ones:
  * test_real_src_with_one_registration_removed_fails — take the real src/,
    drop one real handler out of the registry copy, and assert the check
    reports it. This is the AC's exact shape.
  * test_a_new_unregistered_handler_in_real_src_fails — inject a synthetic
    new menu item into the real MenuHandler.js text and assert it is caught.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from scn.contract import (
    ENTRY_POINT_REGISTRY,
    ENTRY_POINT_SOURCE_EXEMPT,
    ENTRY_POINT_SOURCE_ALIASES,
)

# gts-aqpk: fast/local tier -- pure logic, no live GAS/Google round trip.
pytestmark = pytest.mark.no_live_session

# scripts/ is not a package (no __init__.py), so load the module by path
# rather than putting scripts/ on sys.path for the whole test session.
_SPEC = importlib.util.spec_from_file_location(
    "check_entry_point_extraction",
    Path(__file__).parent.parent / "scripts" / "check_entry_point_extraction.py",
)
cepe = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("check_entry_point_extraction", cepe)
_SPEC.loader.exec_module(cepe)

REPO_ROOT = Path(__file__).parent.parent
SRC_DIR = REPO_ROOT / "src"

# A synthetic project exercising all five extraction classes at once.
FAKE_JS = {
    "MenuHandler.js": (
        "function onOpen() {\n"
        "  SpreadsheetApp.getUi().createMenu('X')\n"
        "    .addItem('Do It', 'menuDoIt')\n"
        "    .addItem('Look', 'menuLook')\n"
        "    .addToUi();\n"
        "}\n"
        "function menuDoIt() { mutate(); }\n"
    ),
    "Card.js": (
        "function build() {\n"
        "  CardService.newAction().setFunctionName('onPressed');\n"
        "  _buildCardAction('onBack');\n"
        "}\n"
    ),
    "Triggers.js": "function install() { ScriptApp.newTrigger('sweepAll').timeBased(); }\n",
}
FAKE_MANIFEST = {
    "addOns": {
        "common": {
            "homepageTrigger": {"runFunction": "buildHome"},
            "universalActions": [{"label": "Go", "runFunction": "onUniversal"}],
        }
    }
}


def _found(js=None, manifest=None):
    return cepe.extract_entry_points(js or FAKE_JS, manifest or FAKE_MANIFEST)


# ── extraction ──────────────────────────────────────────────────────────────

def test_extract_from_js_finds_every_class():
    found = cepe.extract_from_js(FAKE_JS)
    assert set(found["menu"]) == {"menuDoIt", "menuLook"}
    assert set(found["card"]) == {"onPressed", "onBack"}
    assert set(found["trigger"]) == {"sweepAll"}
    assert set(found["simple"]) == {"onOpen"}


def test_extract_records_the_defining_file_for_each_handler():
    found = cepe.extract_from_js(FAKE_JS)
    assert found["menu"]["menuDoIt"] == {"MenuHandler.js"}
    assert found["trigger"]["sweepAll"] == {"Triggers.js"}


def test_simple_trigger_only_counts_when_actually_defined():
    # onEdit is referenced but never defined -> not an entry point here.
    found = cepe.extract_from_js({"A.js": "// onEdit is mentioned only in a comment\n"})
    assert found["simple"] == {}


def test_extract_from_appsscript_walks_nested_run_functions():
    found = cepe.extract_from_appsscript(FAKE_MANIFEST)
    assert set(found) == {"buildHome", "onUniversal"}
    assert found["buildHome"] == {"appsscript.json"}


def test_extraction_error_when_a_class_goes_empty():
    # A restructure that breaks the menu pattern must fail loudly, not pass
    # on an empty set -- same rule the stage-7 view check applies to its regexes.
    js = dict(FAKE_JS)
    js["MenuHandler.js"] = "function onOpen() { /* menu built elsewhere now */ }\n"
    with pytest.raises(cepe.ExtractionError) as exc:
        cepe.extract_entry_points(js, FAKE_MANIFEST)
    assert "menu" in str(exc.value)


# ── accounting ──────────────────────────────────────────────────────────────

def test_unregistered_is_empty_when_everything_is_accounted_for():
    registry = {"menuDoIt": "", "sweepAll": "", "onUniversal": "", "onPressed": ""}
    exempt = {"menuLook": "read-only", "onBack": "navigation", "onOpen": "menu builder",
              "buildHome": "render-only"}
    assert cepe.unregistered(_found(), registry, exempt, {}) == []


def test_unregistered_reports_handler_class_and_file():
    registry = {"sweepAll": "", "onUniversal": "", "onPressed": ""}
    exempt = {"menuLook": "read-only", "onBack": "nav", "onOpen": "builder", "buildHome": "render"}
    gaps = cepe.unregistered(_found(), registry, exempt, {})
    assert gaps == [("menuDoIt", "menu", ["MenuHandler.js"])]


def test_alias_satisfies_registration_under_a_different_key():
    registry = {"mutate.onPressed": "", "menuDoIt": "", "sweepAll": "", "onUniversal": ""}
    exempt = {"menuLook": "", "onBack": "", "onOpen": "", "buildHome": ""}
    assert cepe.unregistered(_found(), registry, exempt, {"onPressed": "mutate.onPressed"}) == []
    # ...and without the alias the same handler is a gap.
    assert ("onPressed", "card", ["Card.js"]) in cepe.unregistered(_found(), registry, exempt, {})


def test_stale_declarations_flags_names_no_longer_wired_in_src():
    stale = cepe.stale_declarations(_found(), {"menuGone": "was read-only"}, {"cardGone": "k"})
    assert stale == ["cardGone", "menuGone"]


# ── against the real project ────────────────────────────────────────────────

def test_real_src_is_fully_accounted_for():
    """The live invariant: every entry point wired in src/ is registered or
    explicitly exempt. This is what makes the check run on every test:local
    pass rather than only on manual invocation."""
    js_sources, manifest = cepe.load_sources(SRC_DIR)
    gaps = cepe.unregistered(cepe.extract_entry_points(js_sources, manifest))
    assert gaps == [], f"unregistered entry points in src/: {gaps}"


def test_real_src_has_no_stale_exemptions_or_aliases():
    js_sources, manifest = cepe.load_sources(SRC_DIR)
    found = cepe.extract_entry_points(js_sources, manifest)
    assert cepe.stale_declarations(found) == []


def test_real_src_with_one_registration_removed_fails():
    """PROVEN-TO-FAIL, real shape: drop a real handler from a copy of the
    registry and the check must report exactly it."""
    js_sources, manifest = cepe.load_sources(SRC_DIR)
    found = cepe.extract_entry_points(js_sources, manifest)
    registry = dict(ENTRY_POINT_REGISTRY)
    del registry["menuRunArchive"]
    gaps = cepe.unregistered(found, registry, ENTRY_POINT_SOURCE_EXEMPT, ENTRY_POINT_SOURCE_ALIASES)
    assert [g[0] for g in gaps] == ["menuRunArchive"]


def test_a_new_unregistered_handler_in_real_src_fails():
    """PROVEN-TO-FAIL, the AC's literal wording: a new menu*/on* handler
    added to src/ that nobody registered fails instead of being undiffed."""
    js_sources, manifest = cepe.load_sources(SRC_DIR)
    js_sources["MenuHandler.js"] += (
        "\nfunction onOpen_probe() {\n"
        "  SpreadsheetApp.getUi().createMenu('P').addItem('Wipe', 'menuWipeEverything');\n"
        "}\n"
    )
    found = cepe.extract_entry_points(js_sources, manifest)
    gaps = cepe.unregistered(found)
    assert [g[0] for g in gaps] == ["menuWipeEverything"]


def test_exempt_and_registry_never_claim_the_same_handler():
    """A handler in both maps would make its accounting ambiguous -- exempt
    means 'not an entry point', registered means 'is one'."""
    overlap = sorted(set(ENTRY_POINT_SOURCE_EXEMPT) & set(ENTRY_POINT_REGISTRY))
    assert overlap == []


# ── CLI ─────────────────────────────────────────────────────────────────────

def test_main_exits_zero_against_the_real_src(capsys):
    assert cepe.main(["--src", str(SRC_DIR)]) == 0
    assert "OK" in capsys.readouterr().out


def test_main_exits_two_on_extraction_error(tmp_path, capsys):
    (tmp_path / "Empty.js").write_text("function nothing() {}\n", encoding="utf-8")
    (tmp_path / "appsscript.json").write_text(json.dumps({"addOns": {}}), encoding="utf-8")
    assert cepe.main(["--src", str(tmp_path)]) == 2
    assert "EXTRACTION ERROR" in capsys.readouterr().out


def test_main_exits_two_when_the_manifest_is_missing(tmp_path, capsys):
    (tmp_path / "A.js").write_text("function onOpen() {}\n", encoding="utf-8")
    assert cepe.main(["--src", str(tmp_path)]) == 2
    assert "EXTRACTION ERROR" in capsys.readouterr().out
