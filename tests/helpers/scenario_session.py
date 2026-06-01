"""ScenarioSession — driver for the §14 editor journey scenario test."""
from __future__ import annotations
import dataclasses
import re
from typing import Optional

_GLOBAL_ID_RE = re.compile(r'^[A-Za-z0-9_-]{25,44}/AI-\d+$')

from tests.helpers.fixture_invoke import invoke_fixture
from tests.helpers.download import download_xlsx, download_docx
from tests.helpers.sheet_inspect import load_sheet, rows_for_doc
from tests.helpers.doc_inspect import load_doc, floating_actions


@dataclasses.dataclass
class ActionHandle:
    seed_text: str
    expected_id: Optional[int]         # None = auto-assigned by sync
    expected_email: Optional[str]
    expected_display_name: Optional[str]
    expected_action_text: str
    expected_status: str = "Open"
    resolved_id: Optional[int] = None  # filled by verify_import()


class ScenarioSession:

    def __init__(self, doc_id: str, sheet_id: str, settings: dict, _owns_doc: bool = False):
        self._doc_id   = doc_id
        self._sheet_id = sheet_id
        self._settings = settings
        self._owns_doc = _owns_doc

    # ── Factories ──────────────────────────────────────────────────────────────

    @classmethod
    def from_standard_clone(cls, master_doc_id: str, sheet_id: str, settings: dict) -> "ScenarioSession":
        """Clone the master template into a fresh, descriptively-named journey doc."""
        result = invoke_fixture("begin_journey_session", master_doc_id, settings, timeout=180)
        doc_id = result["data"]["docId"]
        return cls(doc_id, sheet_id, settings, _owns_doc=True)

    @classmethod
    def from_existing_doc(cls, doc_id: str, sheet_id: str, settings: dict) -> "ScenarioSession":
        """Use a caller-provided doc (no lifecycle management; close() is a no-op)."""
        return cls(doc_id, sheet_id, settings, _owns_doc=False)

    def close(self):
        if self._owns_doc:
            invoke_fixture("end_journey_session", self._doc_id, self._settings, timeout=60)

    # ── Seeding ────────────────────────────────────────────────────────────────

    def seed(self) -> tuple[ActionHandle, ...]:
        """Insert the four §14 AI-token items; return their ActionHandles."""
        invoke_fixture("scenario_journey_seed", self._doc_id, self._settings, timeout=300)
        return (
            ActionHandle(
                seed_text="AI: This tag and text confirms creation of an unassigned action item",
                expected_id=None,
                expected_email=None,
                expected_display_name=None,
                expected_action_text="This tag and text confirms creation of an unassigned action item",
            ),
            ActionHandle(
                seed_text="AI: aitest@example.com ...",
                expected_id=None,
                expected_email="aitest@example.com",
                expected_display_name="Aitest",
                expected_action_text="This tag and email address along with this text confirms the creation of an action item with an assignee.",
            ),
            ActionHandle(
                seed_text="AI-5: ...",
                expected_id=5,
                expected_email=None,
                expected_display_name=None,
                expected_action_text="This tag and text confirms creation of an action item with id AI-5 pre-assigning the specific ID.",
            ),
            ActionHandle(
                seed_text="AI-9: minister@northlakeuu.org ...",
                expected_id=9,
                expected_email="minister@northlakeuu.org",
                expected_display_name="Northlake Minister",
                expected_action_text=(
                    "This tag, email and text should result in the creation of the assignee as a person chip, "
                    "working within our Northlake domain this has a username of 'Northlake Minister' which "
                    "should appear in the chip."
                ),
            ),
        )

    # ── Sync ───────────────────────────────────────────────────────────────────

    def sync(self):
        invoke_fixture("sync_document", self._doc_id, self._settings, timeout=180)

    # ── Import verification ────────────────────────────────────────────────────

    def verify_import(self, *handles: ActionHandle):
        xlsx = download_xlsx(self._sheet_id)
        ws   = load_sheet(xlsx, sheet_name="Actions")
        rows = rows_for_doc(ws, self._doc_id)
        for h in handles:
            if h.expected_id is not None:
                matches = [
                    r for r in rows
                    if re.search(
                        rf"AI-{h.expected_id}\b",
                        (r.get("globalId") or ""),
                    )
                ]
            else:
                matches = [
                    r for r in rows
                    if h.expected_action_text in (r.get("Action") or "")
                    and (h.expected_email or "") == (r.get("Assignee Email") or "")
                ]
            assert len(matches) == 1, (
                f"[scenario UC-A AC1] Expected 1 sheet row for {h.seed_text!r}, "
                f"got {len(matches)}.\n  rows={rows}"
            )
            row = matches[0]
            assert row.get("globalId") not in (None, ""), (
                f"[scenario UC-A AC1] globalId not set for {h.seed_text!r}"
            )
            assert _GLOBAL_ID_RE.match(row.get("globalId") or ""), (
                f"[scenario UC-A AC1] globalId format invalid: {row.get('globalId')!r} "
                f"(expected '{{docId}}/AI-{{N}}') for {h.seed_text!r}"
            )
            assert row.get("Status") == h.expected_status, (
                f"[scenario UC-A AC1] Status: expected {h.expected_status!r}, "
                f"got {row.get('Status')!r} for {h.seed_text!r}"
            )
            if h.expected_email:
                assert row.get("Assignee Email") == h.expected_email, (
                    f"[scenario UC-A AC1] Assignee Email: expected {h.expected_email!r}, "
                    f"got {row.get('Assignee Email')!r}"
                )
            if h.expected_display_name:
                assert row.get("Assignee Name") == h.expected_display_name, (
                    f"[scenario UC-A AC1] Assignee Name: expected {h.expected_display_name!r}, "
                    f"got {row.get('Assignee Name')!r}"
                )
            gid = (row.get("globalId") or "")
            m = re.search(r"AI-(\d+)", gid)
            if m:
                h.resolved_id = int(m.group(1))

    def verify_doc_sheet_consistency(self):
        result = invoke_fixture("verify_consistency", self._doc_id, self._settings, timeout=120)
        issues = result.get("data", {}).get("issues", [])
        assert not issues, f"[scenario] Consistency check failed: {issues}"

    # ── Tracker table ──────────────────────────────────────────────────────────

    def insert_tracker_table(self):
        invoke_fixture("insert_tracker_table", self._doc_id, self._settings, timeout=120)

    def verify_tracker_rows(self, *handles: ActionHandle):
        result = invoke_fixture("verify_consistency", self._doc_id, self._settings, timeout=120)
        tracker_rows = result.get("data", {}).get("tracker", {}).get("rows", [])
        for h in handles:
            matches = [t for t in tracker_rows if h.expected_action_text in (t.get("action") or "")]
            assert len(matches) >= 1, (
                f"[scenario UC-C AC1] Tracker table missing row for {h.expected_action_text!r}"
            )

    # ── Delete ─────────────────────────────────────────────────────────────────

    def delete_unassigned(self):
        result = invoke_fixture(
            "scenario_delete_unassigned", self._doc_id, self._settings, timeout=60
        )
        assert "error" not in result.get("data", {}), (
            f"[scenario sjj AC4] Delete fixture failed: {result}"
        )

    def verify_deleted_unassigned(self, handle: ActionHandle):
        xlsx = download_xlsx(self._sheet_id)
        ws   = load_sheet(xlsx, sheet_name="Actions")
        rows = rows_for_doc(ws, self._doc_id)
        live = [
            r for r in rows
            if handle.expected_action_text in (r.get("Action") or "")
            and r.get("Status") != "Deleted"
        ]
        assert not live, f"[scenario sjj AC4] Unassigned action still live after delete: {live}"

    # ── Final integrity ────────────────────────────────────────────────────────

    def final_integrity_check(self, *surviving_handles: ActionHandle):
        result = invoke_fixture("verify_consistency", self._doc_id, self._settings, timeout=120)
        issues = result.get("data", {}).get("issues", [])
        assert not issues, f"[scenario] Final integrity check failed: {issues}"
        xlsx = download_xlsx(self._sheet_id)
        ws   = load_sheet(xlsx, sheet_name="Actions")
        rows = rows_for_doc(ws, self._doc_id)
        for h in surviving_handles:
            matches = [r for r in rows if h.expected_action_text in (r.get("Action") or "")]
            assert matches, (
                f"[scenario] Surviving action missing from sheet: {h.expected_action_text!r}"
            )
