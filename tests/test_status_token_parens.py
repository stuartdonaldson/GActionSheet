"""
test_status_token_parens.py — parentheses-in-action-text status-token hardening.

_parseParagraphAsFloatingAction (SyncManager.js) extracts a trailing status
token via /\\(([^)]*)\\)\\s*$/ — only a parenthesised phrase anchored at the
very end of the paragraph qualifies; parentheses earlier in the action text
are left untouched. Covers the three corner cases from the bd filing:
  1. parens mid-text, no trailing status      -> no false status detected
  2. parens mid-text, with a trailing status   -> only the trailing one parsed
  3. parens only at the end (ambiguous)        -> treated as a status (defined
     rule: position, not content, decides — the regex always prefers the
     trailing parenthesised phrase as the status)

Bead: GTaskSheet-28q
"""
from scn.ai import ai
from scn.engine import CheckpointKind, Surface
from scn.session import ScenarioSession

SHEET = Surface.SHEET
INTEGRITY = CheckpointKind.INTEGRITY


def test_status_token_parens_hardening(settings):
    scn = ScenarioSession.new_doc(settings)
    try:
        # 1. mid-text parens, no trailing status token
        mid_no_status = ai(action="Review the (draft) proposal", action_id="AI-1")
        # 2. mid-text parens, with a trailing status token
        mid_with_status = ai(
            action="Review the (draft) proposal", status="In Progress", action_id="AI-2"
        )
        # 3. parens only at the end — ambiguous; current rule treats it as status
        trailing_only = ai(action="Review", status="draft", action_id="AI-3")

        scn.append_paragraph(mid_no_status.as_text())
        scn.append_paragraph(mid_with_status.as_text())
        scn.append_paragraph(trailing_only.as_text())

        scn.sync()

        mid_no_status.status = "Open"  # no explicit status -> defaults to Open

        for a in (mid_no_status, mid_with_status, trailing_only):
            scn.verify(a, on=SHEET, tag="[28q status-parens]")
        scn.checkpoint(INTEGRITY)
    finally:
        scn.close()
