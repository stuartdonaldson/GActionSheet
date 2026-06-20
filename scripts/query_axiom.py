#!/usr/bin/env python3
"""
query_axiom.py — Query the Axiom dataset (GTaskSheet-x94a/9dss/aa7j/ecs1 logging-taxonomy work)
without re-deriving the APL request shape and auth every time.

Reads axiomQueryToken + axiomDataset from local.settings.json (same settings file every other
test/script in this repo uses — see tests/conftest.py:_load_settings()). Never prints the token.

Usage:
    python scripts/query_axiom.py [--limit N] [--since DURATION] [--side gas|python]
                                   [--name SUBSTRING] [--where APL_EXPR] [--raw [PATH]]

Examples:
    python scripts/query_axiom.py                          # last 200 events, last 24h
    python scripts/query_axiom.py --limit 50 --since 2h
    python scripts/query_axiom.py --side python
    python scripts/query_axiom.py --name sync.warn
    python scripts/query_axiom.py --where "data.docId == '1AAE...'"
    python scripts/query_axiom.py --raw /tmp/axiom_dump.json   # also dump full JSON for offline analysis

DURATION accepts <N>s / <N>m / <N>h / <N>d (e.g. 30m, 2h, 1d). Default: 24h.
"""
import argparse
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

_SETTINGS_PATH = pathlib.Path(__file__).parent.parent / "local.settings.json"
_DURATION_RE = re.compile(r"^(\d+)([smhd])$")


def _load_settings() -> dict:
    if not _SETTINGS_PATH.exists():
        raise FileNotFoundError(
            "local.settings.json not found. Copy local.settings.example.json and fill in IDs."
        )
    return json.loads(_SETTINGS_PATH.read_text())


def _parse_duration(spec: str) -> timedelta:
    m = _DURATION_RE.match(spec.strip())
    if not m:
        raise ValueError(f"Bad --since value '{spec}', expected e.g. 30m, 2h, 1d")
    n, unit = int(m.group(1)), m.group(2)
    return {"s": timedelta(seconds=n), "m": timedelta(minutes=n),
            "h": timedelta(hours=n), "d": timedelta(days=n)}[unit]


def query(dataset: str, token: str, *, limit: int, since: timedelta,
          side: str | None, name: str | None, where: str | None) -> dict:
    now = datetime.now(timezone.utc)
    start = now - since
    filters = []
    if side:
        filters.append(f"side == '{side}'")
    if name:
        filters.append(f"name contains '{name}'")
    if where:
        filters.append(where)
    # `where` must precede `order by`/`limit` in the pipeline, otherwise filtering
    # would apply after the top-N cut and could return fewer than `limit` rows.
    apl = f"['{dataset}']"
    for f in filters:
        apl += f" | where {f}"
    apl += f" | order by _time desc | limit {limit}"

    body = {
        "apl": apl,
        "startTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endTime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    req = urllib.request.Request(
        "https://api.axiom.co/v1/datasets/_apl?format=legacy",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Axiom query failed ({e.code}): {e.read().decode()[:500]}") from e


def _print_table(matches: list[dict]) -> None:
    for m in matches:
        data = m.get("data", {})
        nonnull = {k: v for k, v in data.items() if v not in (None, "", {})}
        side = nonnull.pop("side", "?")
        name = nonnull.pop("name", "?")
        nonnull.pop("version", None)
        nonnull.pop("caller", None)
        detail = " ".join(f"{k}={v}" for k, v in nonnull.items())
        print(f"{m['_time']}  {side:<6} {name:<32} {detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", "-n", type=int, default=200, help="Max events to return (default: 200)")
    parser.add_argument("--since", default="24h", help="How far back to look, e.g. 30m, 2h, 1d (default: 24h)")
    parser.add_argument("--side", choices=["gas", "python"], help="Filter to one side")
    parser.add_argument("--name", help="Filter to event names containing this substring")
    parser.add_argument("--where", help="Raw APL `where` expression, e.g. \"data.docId == 'xyz'\"")
    parser.add_argument("--raw", nargs="?", const="-", metavar="PATH",
                         help="Dump full JSON response (to PATH, or stdout if no PATH given)")
    args = parser.parse_args()

    settings = _load_settings()
    dataset = settings.get("axiomDataset")
    token = settings.get("axiomQueryToken")
    if not dataset or not token:
        print("ERROR: axiomDataset / axiomQueryToken not set in local.settings.json", file=sys.stderr)
        return 1

    result = query(
        dataset, token,
        limit=args.limit, since=_parse_duration(args.since),
        side=args.side, name=args.name, where=args.where,
    )
    matches = result.get("matches", [])

    if args.raw is not None:
        text = json.dumps(result, indent=2)
        if args.raw == "-":
            print(text)
        else:
            pathlib.Path(args.raw).write_text(text)
            print(f"Wrote {len(matches)} events to {args.raw}", file=sys.stderr)
        return 0

    print(f"{len(matches)} events, {args.since} lookback, dataset={dataset}")
    _print_table(matches)
    return 0


if __name__ == "__main__":
    sys.exit(main())
