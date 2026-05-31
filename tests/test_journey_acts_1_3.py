"""
test_journey_acts_1_3.py — Twin verify B6: empty-create + sync queue-drain convergence.

Drives §16.10 Acts 1-3 of the canonical journey against a live GAS deployment:
  Act 1 — author types 5 AI lines into a blank doc (status UNSET on plain items)
  Act 2 — sync() converts lines to actions; verify_all_expectations across DOC+SHEET;
           verify_consistency(scope=DOC); INTEGRITY checkpoint drains queue
  Act 3 — insert_tracker + re-sync; verify on=TRACKER; STEP checkpoint drains queue

Bead: GTaskSheet-5vwu.11
"""
import pytest

from scn.ai import ai
from scn.engine import CheckpointKind, Severity, Surface
from scn.session import ScenarioSession

DOC = Surface.DOC
SHEET = Surface.SHEET
TRACKER = Surface.TRACKER
INTEGRITY = CheckpointKind.INTEGRITY
STEP = CheckpointKind.STEP
WARN = Severity.WARN


@pytest.fixture(scope="module")
def scn(settings):
    s = ScenarioSession.new_doc(settings)
    yield s
    s.close()                               # trash; assert queue empty


def test_journey_acts_1_3(scn):
    # ── Act 1 — author types 5 AI lines into a blank doc ─────────────────────
    #   status left UNSET on plain items (a user types no status unless non-default)
    unassigned = ai(action="This tag and text confirms creation of an unassigned action item")
    with_email = ai(
        action="This tag and email address along with this text confirms email-assignee path",
        assignee="aitest@example.com",
    )
    explicit_5 = ai(
        action="This tag and text confirms pre-assigning the specific ID",
        action_id="AI-5",
    )
    domain_usr = ai(
        action="This tag email and text confirms domain-user name resolution",
        assignee="minister@northlakeuu.org",
        action_id="AI-9",
    )
    started_ip = ai(
        action="An action the author starts in progress",
        status="In Progress",
    )

    for a in (unassigned, with_email, explicit_5, domain_usr, started_ip):
        scn.append_paragraph(a.as_text())   # pure doc mutation; no action implied yet

    # ── Act 2 — sync converts the lines into actions (Scenario C) ─────────────
    scn.sync()

    # pin what we expect the conversion to produce, then verify across surfaces
    unassigned.status = "Open"
    with_email.status = "Open"              # tokenless → detected Open
    explicit_5.status = "Open"
    domain_usr.status = "Open"
    unassigned.action_id = "AI-1"
    with_email.action_id = "AI-2"           # expected auto-assignment
    # explicit_5 / domain_usr already carry AI-5 / AI-9; started_ip keeps In Progress

    for a in (unassigned, with_email, explicit_5, domain_usr, started_ip):
        scn.verify_all_expectations(a)      # doc+sheet; text/email/name/id/status
    scn.verify_consistency(scope=DOC)       # §16.7 checklist, this doc only
    scn.checkpoint(INTEGRITY)              # capture docx+xlsx; drain the above

    # ── Act 3 — insert the tracker table and re-sync ──────────────────────────
    scn.insert_tracker()
    scn.sync()
    for a in (unassigned, with_email, explicit_5, domain_usr, started_ip):
        scn.verify(a, on=TRACKER)           # column form; assignee as chip
    scn.checkpoint(STEP)                    # drains TRACKER expectations; queue empty at close
