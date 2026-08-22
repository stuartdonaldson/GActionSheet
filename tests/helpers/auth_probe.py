"""auth_probe.py — one-shot liveness check for the shared Playwright auth
session (gts-85x3.1, follow-up to gts-f3me.4).

gts-f3me.4 shipped a proactive/reactive *cookie-rotation* refresh for
tests/helpers/download.py's requests-based session (Google periodically
rotates session-cookie values while leaving the on-disk expiry untouched;
`download._refresh_auth_state` catches that back up). That mechanism is, by
its own docstring, blind to a *fully signed-out* session -- a signed-out
snapshot re-loaded into a headless browser stays signed out no matter how
many times it's refreshed, and gets silently written back to disk unchanged
in substance. On 2026-08-21 (`/tmp/gas-test4.log`) that blind spot let a
fully dead session burn a full 2h21m live-suite run, one test at a time
(39 failed / 6 errors), before anyone noticed.

This module is the fast, explicit check for that case: navigate a real
Playwright browser (headed or headless) to a known "common" page using the
role's on-disk storage_state, and confirm we actually land there signed in
-- reusing the same page (`https://docs.google.com/`) `download.py`'s own
`_refresh_auth_state` already navigates, rather than introducing a second
canonical probe target.

Three ways to use it:
  * `probe_auth_session(role)` -- returns an `AuthProbeResult`, never raises.
    Use when the caller wants to inspect the result (e.g. the CLI).
  * `assert_alive(role)` -- raises `AuthSessionDeadError` on failure. Use as
    a fail-fast guard (conftest.py's session fixture, download.py's
    reactive-refresh path).
  * `scripts/check_auth.py` -- human-run CLI wrapping `probe_auth_session`,
    with a `--headed` flag for visual debugging when a credential is
    suspected to have expired.
"""
from __future__ import annotations

import dataclasses
from typing import Callable, Optional

from scn.session import resolve_auth_file

PROBE_URL = "https://docs.google.com/"
_SIGNED_OUT_MARKERS = ("signed out",)


class AuthSessionDeadError(RuntimeError):
    """The shared Playwright auth session is fully signed out (not merely
    rotating) -- automated refresh cannot fix this. Re-run
    tests/playwright/auth.setup.js by hand for this role."""


@dataclasses.dataclass
class AuthProbeResult:
    ok: bool
    final_url: str
    message: str


def _classify(final_url: str, page_content: str) -> AuthProbeResult:
    if "accounts.google.com" in final_url:
        return AuthProbeResult(
            ok=False,
            final_url=final_url,
            message=(
                f"Landed on the Google sign-in page ({final_url!r}) instead of "
                f"{PROBE_URL!r} -- session is signed out."
            ),
        )
    lowered = page_content.lower()
    if any(marker in lowered for marker in _SIGNED_OUT_MARKERS):
        return AuthProbeResult(
            ok=False,
            final_url=final_url,
            message=(
                f"Landed on {final_url!r} but the page shows a 'Signed out' "
                f"account state -- session is signed out."
            ),
        )
    return AuthProbeResult(
        ok=True,
        final_url=final_url,
        message=f"Session is alive -- landed signed-in on {final_url!r}.",
    )


def probe_auth_session(
    role: str = "primary",
    *,
    headless: bool = True,
    timeout_ms: int = 30_000,
    before_close: Optional[Callable[[], None]] = None,
) -> AuthProbeResult:
    """Navigate a real (headed or headless) Playwright browser to PROBE_URL
    using `role`'s on-disk storage_state and classify the result.

    Never raises for a "signed out" outcome -- that's a normal result,
    reported via AuthProbeResult.ok. Raises AuthSessionDeadError only for a
    setup problem (no auth file for this role at all) that a probe can't
    meaningfully classify as "signed out" vs "never configured".

    `before_close`, if given, runs after the page has loaded and been
    classified but before the browser is torn down -- the hook a headed CLI
    caller uses to pause for visual debugging instead of the window
    vanishing the instant the probe finishes (see scripts/check_auth.py).
    """
    from playwright.sync_api import sync_playwright

    auth_path = resolve_auth_file(role)
    if not auth_path.exists():
        raise AuthSessionDeadError(
            f"probe_auth_session({role!r}): no auth file at {auth_path} -- "
            f"run tests/playwright/auth.setup.js to create one."
        )

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        try:
            ctx = browser.new_context(storage_state=str(auth_path))
            page = ctx.new_page()
            page.goto(PROBE_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            final_url = page.url
            # Visible text only -- NOT page.content() (raw HTML/JS source).
            # docs.google.com always embeds the literal string "Signed out"
            # in a JSON config blob for the account-switcher menu regardless
            # of actual sign-in state (it's a static UI-label constant), so
            # scanning full page source produces a false "signed out" on a
            # session that is actually alive. inner_text("body") only sees
            # what a human looking at the page would see.
            content = page.inner_text("body")
            if before_close is not None:
                before_close()
        finally:
            browser.close()

    return _classify(final_url, content)


def assert_alive(role: str = "primary", *, headless: bool = True, timeout_ms: int = 30_000) -> None:
    """probe_auth_session(role), raising AuthSessionDeadError on any failure
    (signed out, or the probe itself couldn't run) -- the fail-fast entry
    point for callers that should stop rather than inspect a result."""
    result = probe_auth_session(role, headless=headless, timeout_ms=timeout_ms)
    if not result.ok:
        raise AuthSessionDeadError(
            f"{result.message} Re-run 'node tests/playwright/auth.setup.js' "
            f"by hand for role {role!r} before continuing."
        )
