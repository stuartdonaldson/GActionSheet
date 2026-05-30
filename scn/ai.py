"""
ai.py — the noun a scenario manipulates (GTaskSheet-5vwu.4).

Spec: docs/proposed-atdd-lifecycle.md §16.2
Design: docs/atdd/scenario-harness-design.md §3.1
"""
from dataclasses import dataclass


@dataclass
class ai:
    action: str
    assignee: str | None = None         # email
    action_id: str | None = None        # "AI-N"
    status: str | None = None           # free text; token rendered only if set (§16.2 status rule)
    assignee_source: str | None = None  # "chip"|"parsed"; set by readers on read-back; unset when authored

    def as_text(self) -> str:
        """Render as the exact paragraph text the document contains (§16.2 table).

        prefix  | no action_id  | action_id set
        --------|---------------|---------------
        no asgn | AI: {action}  | AI-N: {action}
        asgn    | AI: {a} {act} | AI-N: {a} {act}

        Trailing ' ({status})' appended iff status is set.
        """
        prefix = f"{self.action_id}:" if self.action_id else "AI:"
        core = (
            f"{prefix} {self.assignee} {self.action}"
            if self.assignee
            else f"{prefix} {self.action}"
        )
        return f"{core} ({self.status})" if self.status else core
