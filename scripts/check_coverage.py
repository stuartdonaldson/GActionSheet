#!/usr/bin/env python3
"""
check_coverage.py — Compare JUnit coverage properties against the registries (T24 Step 3).

Parses test-results/junit/pytest.xml for ac.* and ep.* properties (emitted by
ScenarioSession), extracts AC tags and entry-point keys, and diffs them against
scn/contract.AC_REGISTRY and scn/contract.ENTRY_POINT_REGISTRY respectively. Reports
covered, uncovered, and warn-only items for each. Exits 1 if either diff has gaps.

Usage:
    python scripts/check_coverage.py [--xml <path>] [--verbose]
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scn.contract import AC_REGISTRY, ENTRY_POINT_REGISTRY


def _collect(root, prefix):
    """Collect covered (PASS) and warn-only keys from <prefix>.<key>.<surface> properties."""
    covered = set()
    warn_only = set()
    for testcase in root.iter("testcase"):
        for prop in testcase.iter("property"):
            name = prop.get("name", "")
            value = prop.get("value", "")
            if name.startswith(prefix):
                parts = name.split(".")
                if len(parts) >= 3:
                    key = ".".join(parts[1:-1])
                    if value == "PASS":
                        covered.add(key)
                    elif value == "WARN":
                        warn_only.add(key)
    return covered, warn_only


def _report(label, noun, registry, covered, warn_only, verbose):
    """Print a coverage section; return 1 if any registry key is uncovered, else 0."""
    uncovered = set(registry.keys()) - covered - warn_only

    print(label)
    print("=" * 60)
    print(f"Registry size: {len(registry)}")
    print(f"Covered (PASS): {len(covered)}")
    print(f"Warn-only: {len(warn_only)}")
    print(f"Uncovered: {len(uncovered)}")
    print()

    if verbose:
        if covered:
            print(f"Covered {noun}:")
            for key in sorted(covered):
                print(f"  ✓ {key}")
            print()
        if warn_only:
            print(f"Warn-only {noun}:")
            for key in sorted(warn_only):
                print(f"  ⚠ {key}")
            print()

    if uncovered:
        print(f"Uncovered {noun}:")
        for key in sorted(uncovered):
            print(f"  ✗ {key}: {registry[key]}")
        print()
        return 1

    print(f"All {noun} covered!")
    print()
    return 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Check AC and entry-point coverage against JUnit properties")
    parser.add_argument("--xml", default="test-results/junit/pytest.xml", help="Path to JUnit XML")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all items and coverage")
    args = parser.parse_args()

    xml_path = Path(args.xml)
    if not xml_path.exists():
        print(f"ERROR: {xml_path} not found", file=sys.stderr)
        return 1

    tree = ET.parse(xml_path)
    root = tree.getroot()

    ac_covered, ac_warn = _collect(root, "ac.")
    ep_covered, ep_warn = _collect(root, "ep.")

    rc = 0
    rc |= _report("AC Coverage Report", "ACs", AC_REGISTRY, ac_covered, ac_warn, args.verbose)
    rc |= _report("Entry-Point Coverage Report", "entry points",
                  ENTRY_POINT_REGISTRY, ep_covered, ep_warn, args.verbose)
    return rc


if __name__ == "__main__":
    sys.exit(main())
