#!/usr/bin/env python3
"""
check_entry_point_extraction.py — Fail the harness when an entry point wired
in src/ is absent from scn.contract.ENTRY_POINT_REGISTRY (H12, gts-u6ew.11).

Stage 7 (gts-u6ew.10, scripts/check_entry_point_registry_view.py) made the
*views* of the registry honest against the registry. This makes the
*registry* honest against the source. They are different failures: a doc can
drift while the registry is right, and the registry can be complete-looking
while src/ has grown a handler nobody enumerated — the silent uncoverage H12
exists to prevent, and the remaining hole harness-design.md §9b named.

WHAT IS EXTRACTED (the UI-handler entry-point classes, which are wired by
name in exactly four mechanical places and so are cheap to extract without
parsing JavaScript):

  menu       onOpen()'s .addItem('Label', 'handlerName')      — src/*.js
  addon      appsscript.json addOns.* "runFunction" values    — src/appsscript.json
  card       CardService .setFunctionName('h') and this
             project's _buildCardAction('h') wrapper          — src/*.js
  trigger    ScriptApp.newTrigger('h')                        — src/*.js
  simple     the GAS simple triggers, when defined at all     — src/*.js

WHAT IS NOT EXTRACTED, deliberately: the doPost route class
(`payload.action === 'x'` in src/WebApp.js). Routes are ~60 names of which
the registry holds a deliberately chosen state-modifying subset, so an
extractor there would need a read-only exemption list roughly as large as
the registry itself — judgement, not extraction. Stage 8's deliverable is
scoped to "a new menu*/on* handler in src/ that nobody registered"; the
route class is tracked separately. Routes are therefore still hand-authored
into the registry, and this script says nothing about them.

ACCOUNTING RULE — every extracted handler must appear in exactly one of:
  * scn.contract.ENTRY_POINT_REGISTRY          (directly, or via
    ENTRY_POINT_SOURCE_ALIASES when the registry key is not the function
    name — e.g. onSyncNow -> "syncDocument.onSyncNow")
  * scn.contract.ENTRY_POINT_SOURCE_EXEMPT     (read-only / navigation, with
    a stated reason)
Anything else is UNREGISTERED and fails (exit 1).

Extraction going quiet is its own failure (exit 2), not a silent pass: if a
class yields nothing at all — a refactor, a renamed helper, a moved
appsscript.json — the check reports EXTRACTION ERROR rather than passing on
an empty set, the same rule stage 7's script applies to its doc regexes.

Usage:
    python scripts/check_entry_point_extraction.py
    python scripts/check_entry_point_extraction.py --src <dir> [--verbose]
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scn.contract import (  # noqa: E402
    ENTRY_POINT_REGISTRY,
    ENTRY_POINT_SOURCE_EXEMPT,
    ENTRY_POINT_SOURCE_ALIASES,
)

DEFAULT_SRC = "src"

# onOpen(): .addItem('Spreadsheet Sync All', 'menuSync')
MENU_ITEM_RE = re.compile(r"\.addItem\(\s*'[^']*'\s*,\s*'([A-Za-z0-9_]+)'\s*\)")
# CardService.newAction().setFunctionName('onSetActionStatus')
# and this project's wrapper _buildCardAction('onSyncNow')
CARD_ACTION_RE = re.compile(
    r"(?:setFunctionName|_buildCardAction)\(\s*'([A-Za-z0-9_]+)'\s*\)"
)
# ScriptApp.newTrigger('syncAll')
TRIGGER_RE = re.compile(r"newTrigger\(\s*'([A-Za-z0-9_]+)'\s*\)")
# GAS simple triggers, extracted only when the project actually defines one.
SIMPLE_TRIGGERS = ("onOpen", "onEdit", "onInstall", "onFormSubmit")

# Each extraction class and the minimum number of names a healthy repo yields.
# A class dropping to zero means the pattern stopped matching, not that the
# project stopped having menus — that is EXTRACTION ERROR, not a pass.
MIN_EXPECTED = {"menu": 1, "addon": 1, "card": 1, "trigger": 1, "simple": 1}


class ExtractionError(RuntimeError):
    """An extraction class yielded nothing — src/ was restructured under the
    check and it must fail loudly rather than pass on an empty set."""


def _defined_functions(js_text):
    return set(re.findall(r"^function\s+([A-Za-z0-9_]+)\s*\(", js_text, re.M))


def extract_from_js(js_sources):
    """Extract handler names from JavaScript sources.

    js_sources: {filename: text}. Returns {class: {handler: {filename, ...}}}.
    Pure — no filesystem access, so it is testable against synthetic sources.
    """
    found = {"menu": {}, "card": {}, "trigger": {}, "simple": {}}
    for name, text in sorted(js_sources.items()):
        defined = _defined_functions(text)
        for cls, pattern in (
            ("menu", MENU_ITEM_RE),
            ("card", CARD_ACTION_RE),
            ("trigger", TRIGGER_RE),
        ):
            for handler in pattern.findall(text):
                found[cls].setdefault(handler, set()).add(name)
        for handler in SIMPLE_TRIGGERS:
            if handler in defined:
                found["simple"].setdefault(handler, set()).add(name)
    return found


def extract_from_appsscript(manifest):
    """Extract every addOns.* "runFunction" value from a parsed
    appsscript.json. Returns {handler: {"appsscript.json"}}."""
    found = {}

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "runFunction" and isinstance(value, str):
                    found.setdefault(value, set()).add("appsscript.json")
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(manifest.get("addOns", {}))
    return found


def extract_entry_points(js_sources, manifest):
    """The full extraction: the four JS classes plus the manifest class."""
    found = extract_from_js(js_sources)
    found["addon"] = extract_from_appsscript(manifest)
    empty = sorted(cls for cls, minimum in MIN_EXPECTED.items() if len(found.get(cls, {})) < minimum)
    if empty:
        raise ExtractionError(
            "extraction classes yielded nothing: " + ", ".join(empty) +
            " — src/ was restructured; update this script's patterns rather than ignoring it"
        )
    return found


def load_sources(src_dir):
    src = Path(src_dir)
    js_sources = {p.name: p.read_text(encoding="utf-8") for p in sorted(src.glob("*.js"))}
    manifest_path = src / "appsscript.json"
    if not manifest_path.exists():
        raise ExtractionError(f"{manifest_path} not found")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return js_sources, manifest


def unregistered(found, registry=None, exempt=None, aliases=None):
    """Every extracted handler accounted for by neither the registry (directly
    or via an alias) nor the read-only exemption map. Returns a sorted list of
    (handler, class, sorted-source-files) tuples."""
    registry = ENTRY_POINT_REGISTRY if registry is None else registry
    exempt = ENTRY_POINT_SOURCE_EXEMPT if exempt is None else exempt
    aliases = ENTRY_POINT_SOURCE_ALIASES if aliases is None else aliases
    gaps = []
    for cls, handlers in sorted(found.items()):
        for handler, files in sorted(handlers.items()):
            key = aliases.get(handler, handler)
            if key in registry or handler in exempt:
                continue
            gaps.append((handler, cls, sorted(files)))
    return sorted(gaps)


def stale_declarations(found, exempt=None, aliases=None):
    """Exemption/alias entries naming a handler no longer wired anywhere in
    src/. Report-only: a stale exemption is drift, but it cannot hide a new
    entry point the way a missing registration can."""
    exempt = ENTRY_POINT_SOURCE_EXEMPT if exempt is None else exempt
    aliases = ENTRY_POINT_SOURCE_ALIASES if aliases is None else aliases
    seen = {h for handlers in found.values() for h in handlers}
    return sorted([n for n in exempt if n not in seen] + [n for n in aliases if n not in seen])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--src", default=DEFAULT_SRC, help="GAS source directory (default: src)")
    parser.add_argument("--verbose", action="store_true", help="list every accounted-for handler")
    args = parser.parse_args(argv)

    try:
        js_sources, manifest = load_sources(args.src)
        found = extract_entry_points(js_sources, manifest)
    except (ExtractionError, json.JSONDecodeError, OSError) as exc:
        print(f"EXTRACTION ERROR: {exc}")
        return 2

    total = len({h for handlers in found.values() for h in handlers})
    print("Entry-Point Source Extraction (H12, gts-u6ew.11)")
    print(f"  extracted {total} handler(s) from {args.src}: " +
          ", ".join(f"{cls}={len(handlers)}" for cls, handlers in sorted(found.items())))

    if args.verbose:
        for cls, handlers in sorted(found.items()):
            for handler, files in sorted(handlers.items()):
                key = ENTRY_POINT_SOURCE_ALIASES.get(handler, handler)
                where = ("registry" if key in ENTRY_POINT_REGISTRY
                         else "exempt" if handler in ENTRY_POINT_SOURCE_EXEMPT
                         else "UNREGISTERED")
                print(f"    [{cls}] {handler} ({', '.join(sorted(files))}) -> {where}")

    stale = stale_declarations(found)
    if stale:
        print("  WARNING: declared but no longer wired in src/: " + ", ".join(stale))

    gaps = unregistered(found)
    if not gaps:
        print("  OK — every extracted entry point is registered or explicitly exempt.")
        return 0

    print(f"  FAIL — {len(gaps)} entry point(s) wired in src/ but absent from the registry:")
    for handler, cls, files in gaps:
        print(f"    [{cls}] {handler} ({', '.join(files)})")
    print("  Add each to scn.contract.ENTRY_POINT_REGISTRY (plus ENTRY_POINT_DEFERRED with a")
    print("  reason if it has no tagged call-site yet), or to ENTRY_POINT_SOURCE_EXEMPT if it")
    print("  modifies no durable state.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
