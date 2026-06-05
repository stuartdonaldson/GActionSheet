"""
assertions.py — standalone per-surface assertion helpers (GTaskSheet-5vwu.5).

Spec: docs/atdd/atdd-lifecycle.md §16.5, §16.6
Design: docs/atdd/scenario-harness-design.md §3.7, §5

Returns None on pass, an error string on failure.
Consumed by engine.py's drain procedure and importable standalone by session.py (.7).
"""
import re

from scn.contacts import TEST_CONTACTS, expected_name
from scn.engine import Surface

_AI_N_RE = re.compile(r"^AI-\d+$")


def _find_matches(expected: dict, actuals: list) -> list:
    """Locate actuals whose identity key matches expected (action_id preferred, else action text)."""
    if "action_id" in expected:
        key = expected["action_id"]
        return [a for a in actuals if a.action_id == key]
    text = expected["action"]
    return [a for a in actuals if a.action == text]


def check_present_consistent(
    expected: dict,
    actuals: list,
    surface: Surface,
    tag: str,
) -> str | None:
    """Check that a matching action exists on `surface` and its fields are correct (§16.6).

    Matching key: expected['action_id'] if set, else expected['action'] text.
    Checks: action text; action_id (exact if set, else valid AI-N); status (if set);
    assignee email (if set); assignee_name (if reader set it, via expected_name()).
    DOC surface: all matching occurrences must be identical to each other (§16.5).

    Returns None on pass, error string on failure.
    """
    matches = _find_matches(expected, actuals)

    if not matches:
        key = expected.get("action_id") or expected.get("action", "?")
        return f"[{tag}] {surface.value}: action not found: {key!r}"

    # DOC: all occurrences must carry identical field values (§16.5)
    if surface == Surface.DOC and len(matches) > 1:
        first = matches[0]
        for m in matches[1:]:
            if (
                m.action != first.action
                or m.action_id != first.action_id
                or m.status != first.status
                or m.assignee != first.assignee
            ):
                return (
                    f"[{tag}] DOC: occurrences of {first.action_id!r} are not identical"
                )

    actual = matches[0]

    # UI surface carve-out: enforce identity + status only; skip text, assignee, name (R1-impl §2)
    if surface == Surface.UI:
        if "action_id" in expected:
            if actual.action_id != expected["action_id"]:
                return (
                    f"[{tag}] UI: action_id mismatch: "
                    f"expected={expected['action_id']!r}, actual={actual.action_id!r}"
                )
        else:
            if not actual.action_id or not _AI_N_RE.match(actual.action_id):
                return (
                    f"[{tag}] UI: expected a valid AI-N, got: {actual.action_id!r}"
                )
        if "status" in expected:
            if actual.status != expected["status"]:
                return (
                    f"[{tag}] UI: status mismatch: "
                    f"expected={expected['status']!r}, actual={actual.status!r}"
                )
        return None

    # action text
    if actual.action != expected["action"]:
        return (
            f"[{tag}] {surface.value}: action mismatch: "
            f"expected={expected['action']!r}, actual={actual.action!r}"
        )

    # action_id: exact match if pinned, else any valid AI-N
    if "action_id" in expected:
        if actual.action_id != expected["action_id"]:
            return (
                f"[{tag}] {surface.value}: action_id mismatch: "
                f"expected={expected['action_id']!r}, actual={actual.action_id!r}"
            )
    else:
        if not actual.action_id or not _AI_N_RE.match(actual.action_id):
            return (
                f"[{tag}] {surface.value}: expected a valid AI-N, got: {actual.action_id!r}"
            )

    # status (checked only when set in expected)
    if "status" in expected:
        if actual.status != expected["status"]:
            return (
                f"[{tag}] {surface.value}: status mismatch: "
                f"expected={expected['status']!r}, actual={actual.status!r}"
            )

    # assignee email + derived name
    if "assignee" in expected:
        if actual.assignee != expected["assignee"]:
            return (
                f"[{tag}] {surface.value}: assignee mismatch: "
                f"expected={expected['assignee']!r}, actual={actual.assignee!r}"
            )
        # Only verify assignee_name on TRACKER (chip-rendered, directory-resolved name).
        # DOC and SHEET store GAS email-derived names which differ from directory names.
        if hasattr(actual, "assignee_name") and surface == Surface.TRACKER:
            email = expected["assignee"]
            if email in TEST_CONTACTS:
                exp_name = TEST_CONTACTS[email]
                if actual.assignee_name != exp_name:
                    return (
                        f"[{tag}] {surface.value}: assignee_name mismatch: "
                        f"expected={exp_name!r}, actual={actual.assignee_name!r}"
                    )

    return None


def check_absent(
    expected: dict,
    actuals: list,
    surface: Surface,
    tag: str,
) -> str | None:
    """Check that no matching action exists on `surface` (absence/terminal expectation).

    Returns None when the action is absent (pass), error string when found (failure).
    """
    matches = _find_matches(expected, actuals)
    if matches:
        key = expected.get("action_id") or expected.get("action", "?")
        return f"[{tag}] {surface.value}: expected absent but found: {key!r}"
    return None
