#!/usr/bin/env python3
"""
check_auth.py — one-shot liveness check for the shared Playwright auth
session (gts-85x3.1).

Navigates a real browser to https://docs.google.com/ using the given role's
on-disk storage_state (same file tests/helpers/download.py and every
browser_page-based UI test use) and reports whether it actually landed
signed in, or was bounced to Google's sign-in page. This is the manual,
visual-debug counterpart to the automated pytest session-start check
(tests/conftest.py) and download.py's own reactive-refresh path -- run it
by hand whenever you suspect the shared credential has expired, before
kicking off a long live-suite run.

Usage:
    python scripts/check_auth.py                  # headless, role "primary"
    python scripts/check_auth.py --headed          # watch it happen
    python scripts/check_auth.py --role primary --timeout 45

Exit code 0 = session alive, 1 = signed out (or probe couldn't run at all).
If it fails: re-run `node tests/playwright/auth.setup.js` by hand for that
role, then re-check.
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from tests.helpers.auth_probe import AuthSessionDeadError, probe_auth_session


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--role", default="primary", help="playwrightAccounts role to check (default: primary)")
    parser.add_argument("--headed", action="store_true", help="show the browser window instead of running headless")
    parser.add_argument("--timeout", type=int, default=30, help="navigation timeout in seconds (default: 30)")
    args = parser.parse_args()

    print(f"Checking auth session for role {args.role!r} ({'headed' if args.headed else 'headless'})...")

    def _hold_open() -> None:
        # Headed debugging is useless if the window vanishes the instant the
        # probe finishes -- hold it open until the operator is done looking.
        input("Browser is up -- press Enter here to close it...")

    try:
        result = probe_auth_session(
            args.role,
            headless=not args.headed,
            timeout_ms=args.timeout * 1000,
            before_close=_hold_open if args.headed else None,
        )
    except AuthSessionDeadError as exc:
        print(f"FAIL: {exc}")
        return 1

    if result.ok:
        print(f"PASS: {result.message}")
        return 0

    print(f"FAIL: {result.message}")
    print(f"      Re-run 'node tests/playwright/auth.setup.js' by hand for role {args.role!r}, then re-check.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
