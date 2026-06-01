"""
Scenario: AI-tag import, tracker insertion, and delete.

UC-A AC1  — unassigned action created from bare AI: tag
UC-A AC1  — email-assignee action created from AI: + email
UC-A      — explicit ID preserved when AI-N: N is specified
UC-A      — domain email resolved to display name
UC-C AC1  — tracker table inserted with correct rows
sjj AC4   — delete marks row Deleted, removes floating action from doc

Playwright phases (sidebar sync, @create, 6ov.4/6ov.6, status change)
are deferred; see Phase 3.
"""
import pytest

from tests.helpers.scenario_session import ScenarioSession


@pytest.fixture(scope="module")
def journey(settings):
    session = ScenarioSession.from_standard_clone(
        master_doc_id=settings["testDocId"],
        sheet_id=settings["testSheetId"],
        settings=settings,
    )
    yield session
    session.close()


def test_scenario_journey(journey):
    # Phase 1 — seed + sync + import verification
    unassigned, with_email, explicit_5, domain_user = journey.seed()
    journey.sync()
    journey.verify_import(unassigned, with_email, explicit_5, domain_user)
    journey.verify_doc_sheet_consistency()

    # Phase 2 — tracker table
    journey.sync()
    journey.insert_tracker_table()
    journey.sync()
    journey.verify_tracker_rows(unassigned, with_email, explicit_5, domain_user)

    # Phase 6 — delete
    journey.delete_unassigned()
    journey.verify_deleted_unassigned(unassigned)

    # Final integrity — surviving actions present and consistent
    journey.final_integrity_check(with_email, explicit_5, domain_user)
