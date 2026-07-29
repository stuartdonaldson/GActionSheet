#!/usr/bin/env python3
"""capture_team_actions_fixture.py — capture the View A review fixture (gts-79dw.4.11 slice 1).

Calls the testToken-gated `read_team_actions` route once per filter state and
writes the REAL rows to docs/team-portal-fixture.json, so gts-79dw.4.7's View A
mockup can be reviewed against real data — real status vocabulary above all —
without a GIS round trip and without a redeploy per iteration.

Do NOT hand-write or hand-extend this file's output. isResolved()
(src/SyncManager.js) buckets arbitrary user-typed status strings by free-text
synonym, so a fabricated fixture would show 'Open'/'Closed' and hide exactly the
perceptual property the review exists to judge (plan-0726a.txt §G1a).

    python scripts/capture_team_actions_fixture.py --doc-id <docId>
    python scripts/capture_team_actions_fixture.py --team-id Communications --team-id Board \
        --mine sdonaldson@northlakeuu.org --mine board-secretary@northlakeuu.org

Each --team-id (or the team resolved from --doc-id's DocData row, or from
testDocId in local.settings.json) is captured into its own block, because no
single team carries every filter state: one team may have no resolved actions
at all, so the Closed/window states are only reviewable across several. Each
--mine identity is captured per team and dropped where it owns no rows there.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from call_webapp import call_action, _load_settings

_OUTPUT_PATH = pathlib.Path(__file__).parent.parent / "docs" / "team-portal-fixture.json"

# One entry per filter state the review needs to see. `window_boundary` is the
# same query as `closed` with a deliberately narrow window, so the reviewer can
# see which resolved rows the default 60-day window is hiding.
_STATES = {
    "open":            {"statusFilter": "open"},
    "closed":          {"statusFilter": "closed"},
    "all":             {"statusFilter": "all"},
    "window_boundary": {"statusFilter": "closed", "windowDays": 7},
}


def _read(scope: dict, opts: dict, env: str, label: str) -> dict:
    result = call_action("read_team_actions", {**scope, **opts}, env=env)
    if not result.get("ok"):
        raise RuntimeError(f"read_team_actions failed for state {label!r}: {result}")
    return result


def capture_team(scope: dict, identities: list[str], env: str) -> dict:
    """Capture every filter state for one team scope."""
    states = {name: {"opts": opts} for name, opts in _STATES.items()}
    for name in states:
        result = _read(scope, states[name]["opts"], env, name)
        states[name]["rows"] = result["rows"]
        team_id = result.get("teamId", "")
        status_options = result.get("statusOptions", [])

    # One 'mine' state per identity that actually owns rows in this team —
    # an empty one would only show the reviewer an empty list.
    mine: dict = {}
    for email in identities:
        opts = {"statusFilter": "all", "assigneeEmail": email}
        rows = _read(scope, opts, env, f"mine:{email}")["rows"]
        if rows:
            mine[email] = {"opts": opts, "rows": rows}

    for name, state in states.items():
        print(f"  {name:<16} {len(state['rows']):>4} rows")
    for email, state in mine.items():
        print(f"  mine:{email:<11.11} {len(state['rows']):>4} rows")

    return {"teamId": team_id, "scope": scope, "states": states, "mine": mine,
            "statusOptions": status_options}


def capture(scopes: list[dict], identities: list[str], env: str) -> dict:
    fixture: dict = {
        "_source": "scripts/capture_team_actions_fixture.py via read_team_actions "
                   f"({env} deployment) — real rows, never hand-edited",
        "teams": {},
    }

    for scope in scopes:
        print(f"Team scope {scope}:")
        team = capture_team(scope, identities, env)
        # The canonical status picker list is global, not per-team — hoist it
        # so the page has one place to read it from.
        fixture["statusOptions"] = team.pop("statusOptions")
        fixture["teams"][team["teamId"] or str(scope)] = team

    return fixture


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--team-id", action="append", default=[], metavar="TEAM",
                        help="Team Id to capture; repeatable (else resolved from --doc-id)")
    parser.add_argument("--doc-id", help="Any document in the team; its DocData row supplies the team")
    parser.add_argument("--mine", action="append", default=[], metavar="EMAIL",
                        help="Assignee email to capture the mine/all scope filter for; repeatable")
    parser.add_argument("--env", choices=["test", "prod", "dev"], default="test")
    parser.add_argument("--out", type=pathlib.Path, default=_OUTPUT_PATH)
    args = parser.parse_args()

    if args.team_id:
        scopes = [{"teamId": team} for team in args.team_id]
    else:
        doc_id = args.doc_id or _load_settings().get("testDocId")
        if not doc_id:
            print("ERROR: pass --team-id or --doc-id (testDocId is unset)", file=sys.stderr)
            return 1
        scopes = [{"docId": doc_id}]

    print(f"Capturing team-actions fixture from the {args.env} deployment")
    try:
        fixture = capture(scopes, args.mine, args.env)
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    args.out.write_text(json.dumps(fixture, indent=2) + "\n")
    print(f"Wrote {args.out} (teams={', '.join(fixture['teams'])})")

    empty = [name for name, team in fixture["teams"].items()
             if not any(state["rows"] for state in team["states"].values())]
    if empty:
        print(f"WARNING: no rows in any state for: {', '.join(empty)} — "
              "check those teams have synced actions.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
