"""
access_filter.py — shared J-ACCESS-FILTER helper (GTaskSheet-1dxz).

Single home for the access-filter assertion shared by Import (1dxz) and Notify
(ay5w), per knowledge-base/staging/j-access-filter-journey.md §2. Signatures are
account-parameterized so the Notify binding bead can extend this module with
the test.u2/test.u3 (non-Primary) branches later without reshaping it.

GTaskSheet-1dxz's reduced scope (Primary only, no new accounts/teams — see
docs/security-architecture.md §1 for why account-differentiated TeamAccessDenied
is not producible today) supplies only the Primary branch; `visible_doc_set`
takes the caller-seeded doc_id set directly for that branch.
"""
from __future__ import annotations

import re

_DOC_URL_RE = re.compile(r"/document/d/([^/]+)")


def visible_doc_set(scn, account: str = "Primary", *, seeded: set[str] | None = None) -> set[str]:
    """Expected visible doc_id set for `account`.

    Primary (this bead's scope): the caller has already seeded the set of
    source doc_ids that should be visible to Primary (everything readable —
    Primary is the deployer-equivalent full-access account); return it as-is.

    Non-Primary accounts (`TeamA-only`, `Restricted`) are deferred to the
    Notify binding bead (ay5w) per j-access-filter-journey.md §7 — the
    caller-token assertTeamAccess seam (tracked on GTaskSheet-wdh0) is
    required to differentiate accounts.
    """
    if account != "Primary":
        raise NotImplementedError(
            f"visible_doc_set(account={account!r}): non-Primary accounts require "
            "the caller-token assertTeamAccess seam (j-access-filter-journey.md "
            "§7, GTaskSheet-wdh0) — not built yet."
        )
    return set(seeded or set())


def assert_visible_set(actual: set[str], expected: set[str], *, account: str, phase: str) -> None:
    """Single assertion point for the J-ACCESS-FILTER journey's visibleDocSet check."""
    assert actual == expected, (
        f"{phase} ({account}): visible doc set mismatch\n"
        f"  expected: {sorted(expected)}\n"
        f"  actual:   {sorted(actual)}"
    )


def import_adapter(groups: list[dict]) -> set[str]:
    """Projection: scn.ui.read_import_list() groups -> set of doc_id (from doc_url)."""
    doc_ids: set[str] = set()
    for group in groups:
        m = _DOC_URL_RE.search(group.get("doc_url") or "")
        if m:
            doc_ids.add(m.group(1))
    return doc_ids
