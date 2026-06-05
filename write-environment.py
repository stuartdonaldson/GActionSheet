#!/usr/bin/env python3
"""
write-environment.py — Prepare allure-results for a new test run.

1. Cleans test-results/allure-results/ (removes stale result JSON files so
   each run's report shows only that run's tests).
2. Copies allure-report/history/ back in so history trends survive the clean.
3. Copies categories.json from the archive into the fresh results dir.
4. Writes environment.properties from the latest deployment-ledger entry so
   the report is stamped with the deployment version it tested.

Usage:
  python3 write-environment.py [--root DIR] [--target test|prod]
"""

import argparse
import json
import shutil
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Project root (default: .)")
    parser.add_argument("--target", default="test", help="Deployment target (default: test)")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    ledger = root / "deployment-ledger" / f"{args.target}.jsonl"
    results_dir = root / "test-results" / "allure-results"
    report_dir = root / "allure-report"
    categories_src = results_dir / "categories.json"

    # ── 1. Clean stale results, preserve categories.json ─────────────────────
    categories_backup = None
    if results_dir.exists():
        if categories_src.exists():
            categories_backup = categories_src.read_bytes()
        # Remove everything except the categories.json we just backed up
        for item in results_dir.iterdir():
            if item.name == "categories.json":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

    results_dir.mkdir(parents=True, exist_ok=True)

    # Restore categories.json
    if categories_backup is not None:
        (results_dir / "categories.json").write_bytes(categories_backup)

    # ── 2. Copy history from last report for trend continuity ─────────────────
    report_history = report_dir / "history"
    if report_history.exists():
        shutil.copytree(report_history, results_dir / "history")
        print(f"OK    history copied from {report_history}")
    else:
        print("INFO  no prior history — first run will have no trend data")

    # ── 3. Write environment.properties ───────────────────────────────────────
    if not ledger.exists():
        print(f"WARN: ledger not found: {ledger}", file=sys.stderr)
        return

    last_entry = None
    for line in ledger.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                last_entry = json.loads(line)
            except json.JSONDecodeError:
                pass

    if not last_entry:
        print("WARN: no entries in ledger", file=sys.stderr)
        return

    version = last_entry.get("version", "unknown")
    props = [
        f"deployment.version={version}",
        f"deployment.timestamp={last_entry.get('timestamp', '')}",
        f"deployment.target={last_entry.get('target', args.target)}",
        f"deployment.description={last_entry.get('description', '')}",
    ]
    (results_dir / "environment.properties").write_text("\n".join(props) + "\n")
    print(f"OK    environment.properties ({version})")


if __name__ == "__main__":
    main()
