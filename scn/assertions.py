"""
assertions.py — standalone per-surface assertion helpers (GTaskSheet-5vwu.5).

Spec: docs/atdd/atdd-lifecycle.md §16.5, §16.6
Design: docs/atdd/scenario-harness-design.md §3.7, §5

Returns None on pass, an error string on failure.
Consumed by engine.py's drain procedure and importable standalone by session.py (.7).
"""
import datetime
import re
import zoneinfo

from scn.contacts import TEST_CONTACTS, expected_name
from scn.engine import Surface

_AI_N_RE = re.compile(r"^AI-\d+$")

# Test ActionSheet's spreadsheet timezone (confirmed empirically: xlsx-exported
# created_date/modified_date cells run exactly 7h behind the webapp's ISO-8601
# UTC value for every row checked, matching PDT). Sheets/xlsx datetime cells
# carry no zone info of their own -- this is the one fact needed to interpret
# them (gts-cges).
_SHEET_TZ = zoneinfo.ZoneInfo("America/Los_Angeles")


def _normalize_date(value):
    """Coerce a date/datetime value (str or datetime, tz-aware or naive) to UTC.

    - Naive datetime (e.g. from SheetReader's xlsx cell): assumed to be in the
      ActionSheet's spreadsheet timezone (_SHEET_TZ).
    - ISO-8601 string (e.g. webapp JSON, trailing 'Z'): parsed directly.
    - Anything else (already tz-aware datetime, unparseable string): returned
      as-is so the caller falls back to plain equality.
    """
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=_SHEET_TZ)
        return value.astimezone(datetime.timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.datetime.fromisoformat(
                value.replace("Z", "+00:00")
            ).astimezone(datetime.timezone.utc)
        except ValueError:
            return value
    return value


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
    assignee email (if set); assignee_name (if reader set it, via expected_name());
    global_id, created_date, modified_date (GTaskSheet-k1g9) -- compared only when
    present in `expected` AND the reader populated the same attribute on `actual`
    (mirrors the assignee_name hasattr() guard below). Currently only SHEET actuals
    (scn/surfaces.py SheetReader) carry global_id/created_date/modified_date; DOC and
    TRACKER readers do not set them, so these checks are a no-op on those surfaces
    even if the caller's expected dict happens to carry the fields.
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

    # global_id / created_date / modified_date (GTaskSheet-k1g9): compared only when
    # the caller pinned the field in `expected` AND the reader populated it on `actual`.
    for field_name in ("global_id", "created_date", "modified_date"):
        if field_name in expected and hasattr(actual, field_name):
            exp_val = expected[field_name]
            act_val = getattr(actual, field_name)
            if field_name in ("created_date", "modified_date"):
                mismatch = _normalize_date(act_val) != _normalize_date(exp_val)
            else:
                mismatch = act_val != exp_val
            if mismatch:
                return (
                    f"[{tag}] {surface.value}: {field_name} mismatch: "
                    f"expected={exp_val!r}, actual={act_val!r}"
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
