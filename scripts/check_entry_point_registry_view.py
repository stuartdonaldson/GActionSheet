#!/usr/bin/env python3
"""
check_entry_point_registry_view.py — Stop testing-guide §7 drifting from
scn.contract.ENTRY_POINT_REGISTRY (H12/I6, gts-u6ew.10).

Testing guide §7 and harness-design.md §9b's H12 row are both *views* of
scn.contract.ENTRY_POINT_REGISTRY / ENTRY_POINT_DEFERRED — prose stating the
total entry-point count and the deferred count as bold numbers, not a second
full enumeration. That prose has already drifted once: guide §7 read "32
entry points / 22 deferred" against an actual 37/13 until corrected
2026-09-05 (see the guide's own §7 callout and harness-design.md §9b).

This script is the mechanical check named in gts-u6ew.10's acceptance
criteria ("Guide 7 is generated from the registry, or a check fails when
they disagree"): it extracts the bold total/deferred/covered numbers each
doc states via regex and compares them against the registry's actual counts
(len(ENTRY_POINT_REGISTRY), len(ENTRY_POINT_DEFERRED)). A textual mismatch
fails loudly (exit 1) instead of silently going stale again. If a doc's
prose is reworded such that the expected pattern no longer matches at all,
that is treated as its own failure (exit 2) rather than a silent pass --
the whole point is that this check cannot go quiet while the doc drifts
under it.

Usage:
    python scripts/check_entry_point_registry_view.py
    python scripts/check_entry_point_registry_view.py --guide <path> --harness-design <path>
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scn.contract import ENTRY_POINT_REGISTRY, ENTRY_POINT_DEFERRED

DEFAULT_GUIDE = "docs/atdd/project-testing-guide.md"
DEFAULT_HARNESS_DESIGN = "docs/atdd/harness-design.md"

# Guide §7: "...all **37** state-modifying entry points..."
GUIDE_TOTAL_RE = re.compile(
    r"all \*\*(\d+)\*\* state-modifying entry points"
)
# Guide §7: "24 of the 37 entries are expected to carry a real tagged
# scenario call-site; the remaining **13** are explicitly enumerated as
# **deferred**"
GUIDE_COVERED_RE = re.compile(
    r"(\d+) of the (\d+) entries are expected to carry a real tagged scenario call-site"
)
GUIDE_DEFERRED_RE = re.compile(
    r"remaining \*\*(\d+)\*\* are explicitly enumerated as \*\*deferred\*\*"
)

# harness-design.md §9a H12 row: "A single machine-readable registry of 37
# state-modifying entry points, with 13 explicitly deferred"
HARNESS_DESIGN_RE = re.compile(
    r"registry of (\d+) state-modifying entry points, with (\d+) explicitly deferred"
)


class ExtractionError(RuntimeError):
    """Raised when an expected count pattern is no longer found in a doc's
    prose -- the doc was reworded and the check must not silently pass."""


def registry_counts(registry=None, deferred=None):
    """Actual counts from the registry itself. Pure function over the two
    dicts so it is testable without importing scn.contract's live state."""
    registry = ENTRY_POINT_REGISTRY if registry is None else registry
    deferred = ENTRY_POINT_DEFERRED if deferred is None else deferred
    total = len(registry)
    n_deferred = len(deferred)
    return {"total": total, "deferred": n_deferred, "covered": total - n_deferred}


def extract_guide_counts(text):
    """Parse guide §7's stated total/covered/deferred numbers out of its
    prose. Raises ExtractionError if any of the three patterns is absent --
    a reworded doc must fail the check, not pass it vacuously."""
    total_m = GUIDE_TOTAL_RE.search(text)
    covered_m = GUIDE_COVERED_RE.search(text)
    deferred_m = GUIDE_DEFERRED_RE.search(text)
    missing = [
        name
        for name, m in (
            ("total (§7 'all **N** state-modifying entry points')", total_m),
            ("covered/of-total (§7 'N of the M entries...')", covered_m),
            ("deferred (§7 'remaining **N** are explicitly enumerated as deferred')", deferred_m),
        )
        if m is None
    ]
    if missing:
        raise ExtractionError(
            "project-testing-guide.md §7: could not find expected count pattern(s): "
            + "; ".join(missing)
        )
    covered_stated, total_from_covered = int(covered_m.group(1)), int(covered_m.group(2))
    return {
        "total": int(total_m.group(1)),
        "total_from_covered_line": total_from_covered,
        "covered": covered_stated,
        "deferred": int(deferred_m.group(1)),
    }


def extract_harness_design_counts(text):
    """Parse harness-design.md §9a's H12 row total/deferred numbers."""
    m = HARNESS_DESIGN_RE.search(text)
    if m is None:
        raise ExtractionError(
            "harness-design.md: could not find expected H12 row pattern "
            "('registry of N state-modifying entry points, with M explicitly deferred')"
        )
    total, n_deferred = int(m.group(1)), int(m.group(2))
    return {"total": total, "deferred": n_deferred, "covered": total - n_deferred}


def diff_guide(actual, claimed):
    """Compare the guide's three independently-stated numbers (total,
    covered, deferred, plus the redundant total-from-the-covered-line)
    against the registry's actual counts. Returns a list of mismatch
    messages; empty means agreement."""
    problems = []
    if claimed["total"] != actual["total"]:
        problems.append(
            f"guide §7 states {claimed['total']} total entry points; "
            f"registry actually has {actual['total']}"
        )
    if claimed["total_from_covered_line"] != actual["total"]:
        problems.append(
            f"guide §7's 'N of the M entries' line states M={claimed['total_from_covered_line']}; "
            f"registry actually has {actual['total']}"
        )
    if claimed["deferred"] != actual["deferred"]:
        problems.append(
            f"guide §7 states {claimed['deferred']} deferred entries; "
            f"ENTRY_POINT_DEFERRED actually has {actual['deferred']}"
        )
    if claimed["covered"] != actual["covered"]:
        problems.append(
            f"guide §7 states {claimed['covered']} covered entries; "
            f"registry minus deferred is actually {actual['covered']}"
        )
    return problems


def diff_harness_design(actual, claimed):
    problems = []
    if claimed["total"] != actual["total"]:
        problems.append(
            f"harness-design.md §9a H12 row states {claimed['total']} entry points; "
            f"registry actually has {actual['total']}"
        )
    if claimed["deferred"] != actual["deferred"]:
        problems.append(
            f"harness-design.md §9a H12 row states {claimed['deferred']} deferred entries; "
            f"ENTRY_POINT_DEFERRED actually has {actual['deferred']}"
        )
    return problems


def check(guide_path=DEFAULT_GUIDE, harness_design_path=DEFAULT_HARNESS_DESIGN):
    """Run both doc checks against the live registry. Returns (problems,
    extraction_errors) -- two lists of strings, either of which being
    non-empty means the check failed."""
    actual = registry_counts()
    problems = []
    extraction_errors = []

    guide_text = Path(guide_path).read_text()
    try:
        guide_claimed = extract_guide_counts(guide_text)
        problems.extend(diff_guide(actual, guide_claimed))
    except ExtractionError as e:
        extraction_errors.append(str(e))

    hd_text = Path(harness_design_path).read_text()
    try:
        hd_claimed = extract_harness_design_counts(hd_text)
        problems.extend(diff_harness_design(actual, hd_claimed))
    except ExtractionError as e:
        extraction_errors.append(str(e))

    return problems, extraction_errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guide", default=DEFAULT_GUIDE)
    parser.add_argument("--harness-design", default=DEFAULT_HARNESS_DESIGN)
    args = parser.parse_args(argv)

    problems, extraction_errors = check(args.guide, args.harness_design)

    if extraction_errors:
        for e in extraction_errors:
            print(f"EXTRACTION ERROR: {e}", file=sys.stderr)
        return 2

    if problems:
        for p in problems:
            print(f"MISMATCH: {p}", file=sys.stderr)
        return 1

    actual = registry_counts()
    print(
        f"OK: scn.contract.ENTRY_POINT_REGISTRY ({actual['total']} total, "
        f"{actual['deferred']} deferred, {actual['covered']} covered) agrees "
        f"with {args.guide} and {args.harness_design}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
