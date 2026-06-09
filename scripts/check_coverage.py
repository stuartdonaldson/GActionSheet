#!/usr/bin/env python3
"""
check_coverage.py — Compare JUnit AC properties against the AC registry (T24 Step 3).

Parses test-results/junit/pytest.xml for ac.* properties (emitted by ScenarioSession),
extracts AC tags, and diffs against scn/contract.AC_REGISTRY. Reports covered,
uncovered, and warn-only ACs. Exits 1 if gaps exist.

Usage:
    python scripts/check_coverage.py [--xml <path>] [--verbose]
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scn.contract import AC_REGISTRY


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Check AC coverage against JUnit properties")
    parser.add_argument("--xml", default="test-results/junit/pytest.xml", help="Path to JUnit XML")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all ACs and coverage")
    args = parser.parse_args()

    xml_path = Path(args.xml)
    if not xml_path.exists():
        print(f"ERROR: {xml_path} not found", file=sys.stderr)
        return 1

    tree = ET.parse(xml_path)
    root = tree.getroot()

    covered = set()
    warn_only = set()

    for testcase in root.iter("testcase"):
        for prop in testcase.iter("property"):
            name = prop.get("name", "")
            value = prop.get("value", "")
            if name.startswith("ac."):
                parts = name.split(".")
                if len(parts) >= 3:
                    tag = ".".join(parts[1:-1])
                    if value == "PASS":
                        covered.add(tag)
                    elif value == "WARN":
                        warn_only.add(tag)

    uncovered = set(AC_REGISTRY.keys()) - covered - warn_only
    covered_with_pass = covered

    print("AC Coverage Report")
    print("=" * 60)
    print(f"Registry size: {len(AC_REGISTRY)}")
    print(f"Covered (PASS): {len(covered_with_pass)}")
    print(f"Warn-only: {len(warn_only)}")
    print(f"Uncovered: {len(uncovered)}")
    print()

    if args.verbose:
        if covered_with_pass:
            print("Covered ACs:")
            for ac in sorted(covered_with_pass):
                print(f"  ✓ {ac}")
            print()

        if warn_only:
            print("Warn-only ACs:")
            for ac in sorted(warn_only):
                print(f"  ⚠ {ac}")
            print()

    if uncovered:
        print("Uncovered ACs:")
        for ac in sorted(uncovered):
            print(f"  ✗ {ac}: {AC_REGISTRY[ac]}")
        print()
        return 1

    print("All ACs covered!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
