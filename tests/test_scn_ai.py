"""
Unit tests for scn/ai.py and scn/contacts.py (GTaskSheet-5vwu.4).

Pure unit — no network, no GAS, no local.settings.json required.
Covers every row of the §16.2 as_text() table (×2 for status on/off)
and both name-resolution paths from §16.4.
"""
import pytest

from scn.ai import ai
from scn.contacts import (
    TEST_CONTACTS,
    autocomplete_expected,
    expected_name,
    name_from_email,
)


# ---------------------------------------------------------------------------
# ai.as_text() — §16.2 rendering table
# ---------------------------------------------------------------------------

class TestAiAsText:
    def test_action_only(self):
        assert ai("Do the thing").as_text() == "AI: Do the thing"

    def test_action_with_assignee(self):
        assert ai("Do the thing", assignee="a@b.com").as_text() == "AI: a@b.com Do the thing"

    def test_action_with_action_id(self):
        assert ai("Do the thing", action_id="AI-3").as_text() == "AI-3: Do the thing"

    def test_action_with_assignee_and_action_id(self):
        a = ai("Do the thing", assignee="a@b.com", action_id="AI-3")
        assert a.as_text() == "AI-3: a@b.com Do the thing"

    # status token appended iff status is set
    def test_status_appended_action_only(self):
        assert ai("Do the thing", status="Open").as_text() == "AI: Do the thing (Open)"

    def test_status_appended_with_assignee(self):
        a = ai("Do the thing", assignee="a@b.com", status="Open")
        assert a.as_text() == "AI: a@b.com Do the thing (Open)"

    def test_status_appended_with_action_id(self):
        a = ai("Do the thing", action_id="AI-3", status="Open")
        assert a.as_text() == "AI-3: Do the thing (Open)"

    def test_status_appended_all_fields(self):
        a = ai("Do the thing", assignee="a@b.com", action_id="AI-3", status="Open")
        assert a.as_text() == "AI-3: a@b.com Do the thing (Open)"

    def test_status_none_no_token(self):
        # explicit None → no token
        assert ai("Do the thing", status=None).as_text() == "AI: Do the thing"

    def test_non_default_status(self):
        a = ai("Do the thing", status="In Progress")
        assert a.as_text() == "AI: Do the thing (In Progress)"


# ---------------------------------------------------------------------------
# ai fields and mutability — §16.2
# ---------------------------------------------------------------------------

class TestAiFields:
    def test_assignee_source_defaults_none_on_authored_ai(self):
        a = ai("Some action")
        assert a.assignee_source is None

    def test_assignee_source_settable_chip(self):
        a = ai("action", assignee="x@y.com")
        a.assignee_source = "chip"
        assert a.assignee_source == "chip"

    def test_assignee_source_settable_parsed(self):
        a = ai("action", assignee="x@y.com")
        a.assignee_source = "parsed"
        assert a.assignee_source == "parsed"

    def test_mutable_pin_action_id_updates_as_text(self):
        a = ai("Do the thing")
        assert a.as_text() == "AI: Do the thing"
        a.action_id = "AI-7"
        assert a.as_text() == "AI-7: Do the thing"

    def test_mutable_pin_status_updates_as_text(self):
        a = ai("Do the thing")
        assert a.as_text() == "AI: Do the thing"
        a.status = "Open"
        assert a.as_text() == "AI: Do the thing (Open)"

    def test_all_fields_optional_except_action(self):
        a = ai("Bare action")
        assert a.assignee is None
        assert a.action_id is None
        assert a.status is None
        assert a.assignee_source is None


# ---------------------------------------------------------------------------
# contacts — §16.4
# ---------------------------------------------------------------------------

class TestContacts:
    def test_expected_name_contacts_path_minister(self):
        assert expected_name("minister@northlakeuu.org") == "Northlake Minister"

    def test_expected_name_contacts_path_sdonaldson(self):
        assert expected_name("sdonaldson@northlakeuu.org") == "Stuart Donaldson"

    def test_expected_name_derivation_path_aitest(self):
        # aitest@example.com absent from TEST_CONTACTS → derives "Aitest"
        assert expected_name("aitest@example.com") == "Aitest"

    def test_name_from_email_dot_separated(self):
        assert name_from_email("jane.smith@example.com") == "Jane Smith"

    def test_name_from_email_single_part(self):
        assert name_from_email("aitest@example.com") == "Aitest"

    def test_name_from_email_multiple_dots(self):
        assert name_from_email("john.michael.doe@x.com") == "John Michael Doe"

    def test_autocomplete_expected_known_contact(self):
        assert autocomplete_expected("minister@northlakeuu.org") is True

    def test_autocomplete_expected_unknown_contact(self):
        assert autocomplete_expected("aitest@example.com") is False

    def test_test_contacts_has_expected_keys(self):
        assert "minister@northlakeuu.org" in TEST_CONTACTS
        assert "sdonaldson@northlakeuu.org" in TEST_CONTACTS
        assert "aitest@example.com" not in TEST_CONTACTS
