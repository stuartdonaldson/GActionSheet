#!/usr/bin/env python3
"""
archive-test-results.py — Archive completed test run XML files to test-results/junit/archive/.

Reads the run timestamp from the testsuite element in each XML file and copies
it to test-results/junit/archive/ with the timestamp embedded in the filename:
  junit/pytest.xml      → junit/archive/pytest-20260604-143045.xml
  junit/playwright.xml  → junit/archive/playwright-20260604-143045.xml

Both files from the same run share the same timestamp slug (derived from pytest.xml
if both are present) so they are trivially paired.

Run this once after a test suite completes. Safe to run multiple times — existing
archives are never overwritten (exits with a warning instead).

Usage:
  python3 archive-test-results.py [--root DIR] [--dry-run]
"""

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET


def ts_from_xml(path: Path) -> datetime | None:
    """Extract the run timestamp from testsuite/@timestamp."""
    try:
        root = ET.parse(path).getroot()
        suite = root.find("testsuite")
        suite = suite if suite is not None else root
        ts_str = suite.get("timestamp")
        if ts_str:
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ET.ParseError, OSError, ValueError):
        pass
    return None


def slug_from_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")


def archive_file(src: Path, runs_dir: Path, prefix: str, slug: str, dry_run: bool) -> Path | None:
    dest = runs_dir / f"{prefix}-{slug}.xml"
    if dest.exists():
        print(f"  SKIP  {dest.name} (already archived)")
        return None
    if dry_run:
        print(f"  DRY   {src.name} → runs/{dest.name}")
        return dest
    shutil.copy2(src, dest)
    print(f"  OK    {src.name} → runs/{dest.name}")
    return dest


def main():
    parser = argparse.ArgumentParser(description="Archive test run XML files to test-results/runs/")
    parser.add_argument("--root", default=".", help="Project root directory (default: .)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be archived without copying")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    test_results = root / "test-results"
    junit_dir = test_results / "junit"
    runs_dir = junit_dir / "archive"

    pytest_xml = junit_dir / "pytest.xml"
    playwright_xml = junit_dir / "playwright.xml"

    present = [p for p in (pytest_xml, playwright_xml) if p.exists()]
    if not present:
        print("Nothing to archive — neither pytest.xml nor playwright.xml found.", file=sys.stderr)
        sys.exit(1)

    # Derive the shared slug from pytest.xml timestamp, falling back to playwright.xml, then now
    slug = None
    for candidate in (pytest_xml, playwright_xml):
        if candidate.exists():
            dt = ts_from_xml(candidate)
            if dt:
                slug = slug_from_dt(dt)
                break
    if slug is None:
        slug = slug_from_dt(datetime.now(timezone.utc))
        print(f"  WARN  Could not read timestamp from XML — using current time: {slug}")

    if not args.dry_run:
        runs_dir.mkdir(parents=True, exist_ok=True)

    archived = []
    for src, prefix in ((pytest_xml, "pytest"), (playwright_xml, "playwright")):
        if src.exists():
            dest = archive_file(src, runs_dir, prefix, slug, args.dry_run)
            if dest:
                archived.append(dest)

    if not archived and not args.dry_run:
        print("No new archives written.")
    elif not args.dry_run:
        print(f"\nArchived {len(archived)} file(s) with slug {slug}.")


if __name__ == "__main__":
    main()
