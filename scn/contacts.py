"""
contacts.py — TEST_CONTACTS directory + name-resolution (GTaskSheet-5vwu.4).

Spec: docs/atdd/atdd-lifecycle.md §16.4
Design: docs/atdd/scenario-harness-design.md §3.2
"""

TEST_CONTACTS: dict[str, str] = {
    "minister@northlakeuu.org":   "Northlake Minister",
    "sdonaldson@northlakeuu.org": "Stuart Donaldson",
    # aitest@example.com deliberately absent → exercises the username-derivation path
}


def name_from_email(email: str) -> str:
    """Derive a display name from an email address when the contact is not in TEST_CONTACTS.

    Local part before @, dot-separated tokens each capitalized, joined with spaces.
    "jane.smith@x" → "Jane Smith"; "aitest@example.com" → "Aitest".
    """
    local = email.split("@")[0]
    return " ".join(part.capitalize() for part in local.split("."))


def expected_name(email: str) -> str:
    """The name the system is expected to display for this assignee (§16.4).

    Uses TEST_CONTACTS lookup (chip/directory path) if present,
    else falls back to name_from_email (username-derivation path).
    """
    return TEST_CONTACTS.get(email) or name_from_email(email)


def autocomplete_expected(email: str) -> bool:
    """True iff an @create assignee with this email is expected to autocomplete (§16.4).

    Absence of autocomplete for an unknown email is warning-only, not a failure.
    """
    return email in TEST_CONTACTS
