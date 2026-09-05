#!/usr/bin/env python3
"""
audit_disposition.py — Mechanical audit for ADR-0011 disposition compliance (gts-u6ew.9).

Mechanizes the two ad hoc `bd`/`jq` commands documented in
`~/.claude/skills/bd/SKILL.md` §"Disposition on `[TST]` Issues" into one reusable,
scriptable check: every `[TST]` bead in scope must carry exactly one `disp:<n>`
label (n in 0-4) and a `## Disposition` section in its description. Prints
nothing and exits 0 on a clean scope; prints each violation and exits 1
otherwise.

Scope, not the whole tracker, is what merge-gate's Step 2.5 ("For every [TST]
bead in scope...") actually needs audited. Two ways to select it:

  --ids ID,ID,...   Explicit bead ids — this is the merge-gate wiring: the
                    reviewer (or a hook) passes the [TST] beads closed/touched
                    by the diff under review, and only those are checked.
  --since DATE      Whole-tracker forward-binding audit (default: this
                    project's ADR-0011 effective date, DISPOSITION_EFFECTIVE_DATE
                    below) — `created_at >= DATE`. This is the periodic health
                    check; it deliberately does not flag the ~213 pre-adoption
                    [TST] beads, per project-testing-guide.md §9's "dispositions
                    bind forward from 2026-09-05; closed [TST] items are not
                    re-litigated" rule.

--ids and --since are mutually exclusive; --ids wins if both are given. With
neither, --since defaults to DISPOSITION_EFFECTIVE_DATE.

Usage:
    python scripts/audit_disposition.py                       # whole-tracker, forward-binding
    python scripts/audit_disposition.py --since 2026-09-05
    python scripts/audit_disposition.py --ids gts-u6ew.12,gts-u6ew.13
"""
import json
import subprocess
import sys

DISPOSITION_EFFECTIVE_DATE = "2026-09-05"
DISP_LABELS = ["disp:0", "disp:1", "disp:2", "disp:3", "disp:4"]
TST_TITLE_PREFIX = "[TST]"


def _is_tst(issue):
    return issue.get("title", "").startswith(TST_TITLE_PREFIX)


def _disp_labels(issue):
    return [l for l in issue.get("labels", []) if l.startswith("disp:")]


def filter_since(issues, since_date):
    """[TST] issues created on or after since_date (ISO date, compared as string prefix)."""
    return [i for i in issues if _is_tst(i) and i.get("created_at", "") >= since_date]


def filter_ids(issues, ids):
    """[TST] issues whose id is in the given set."""
    idset = set(ids)
    return [i for i in issues if _is_tst(i) and i.get("id") in idset]


def find_missing_disposition(scoped_tst_issues):
    """[TST] issues in scope carrying no disp:<n> label at all."""
    return [i for i in scoped_tst_issues if not _disp_labels(i)]


def find_malformed_disposition(scoped_tst_issues):
    """[TST] issues in scope carrying more than one disp:<n> label, or missing the
    '## Disposition' description section (checked only for issues that have at
    least one disp label — a fully missing disposition is find_missing_disposition's
    finding, not this one's, to avoid double-reporting the same bead twice)."""
    out = []
    for i in scoped_tst_issues:
        labels = _disp_labels(i)
        if not labels:
            continue
        no_section = "## Disposition" not in (i.get("description") or "")
        if len(labels) > 1 or no_section:
            out.append(i)
    return out


def _bd_list_json(extra_args):
    result = subprocess.run(
        ["bd", "list", "--status", "all", "--limit", "1000", "--json", *extra_args],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def load_all_tst_issues():
    """Every issue bd knows about, [TST]-titled or not — callers filter."""
    return _bd_list_json([])


def audit(scoped_tst_issues):
    """Run both checks over an already-scoped [TST] issue list. Returns
    (missing, malformed) — both empty on a clean scope."""
    missing = find_missing_disposition(scoped_tst_issues)
    malformed = find_malformed_disposition(scoped_tst_issues)
    return missing, malformed


def _print_violations(missing, malformed):
    for i in missing:
        print(f"MISSING\t{i['id']}\t{i['title']}")
    for i in malformed:
        labels = _disp_labels(i)
        reason = "multiple disp labels" if len(labels) > 1 else "no ## Disposition section"
        print(f"MALFORMED ({reason})\t{i['id']}\t{i['title']}")


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Audit [TST] beads for ADR-0011 disposition compliance (gts-u6ew.9)")
    parser.add_argument("--ids", default=None,
                         help="Comma-separated bead ids to audit (merge-gate scope). "
                              "Wins over --since if both given.")
    parser.add_argument("--since", default=None,
                         help=f"Audit every [TST] bead created on/after this ISO date "
                              f"(default: {DISPOSITION_EFFECTIVE_DATE})")
    args = parser.parse_args()

    all_issues = load_all_tst_issues()

    if args.ids:
        ids = [x.strip() for x in args.ids.split(",") if x.strip()]
        scoped = filter_ids(all_issues, ids)
        # Any explicitly requested id that bd doesn't know, or that isn't a [TST]
        # issue, is a caller error worth surfacing rather than silently dropping.
        found_ids = {i["id"] for i in scoped}
        unresolved = [x for x in ids if x not in found_ids]
        if unresolved:
            print(f"WARNING: not found or not [TST]-titled: {', '.join(unresolved)}",
                  file=sys.stderr)
    else:
        since = args.since or DISPOSITION_EFFECTIVE_DATE
        scoped = filter_since(all_issues, since)

    missing, malformed = audit(scoped)
    _print_violations(missing, malformed)
    return 1 if (missing or malformed) else 0


if __name__ == "__main__":
    sys.exit(main())
