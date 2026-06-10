"""
session.py — ScenarioSession thin driver (GTaskSheet-5vwu.7).

Spec: docs/atdd/atdd-lifecycle.md §16.9, §16.11
Design: docs/atdd/scenario-harness-design.md §3, §4

Public API (§16.9 catalog):
  Lifecycle:   new_doc, close
  Acts:        append_paragraph, insert_tracker, sync, edit_sheet, set_status, delete
  Queries:     doc_items, sheet_rows, find_sheet_actions, verify_consistency
  Expectations: verify, verify_all_expectations, expect_absent, checkpoint

Ownership: session owns lifecycle, HTTP acts, surface captures, and ai-state accumulation.
It does NOT own assertion logic — evaluation lives in engine.py + assertions.py.
"""
from __future__ import annotations

import copy
import json
import os
import pathlib
import urllib.error
import urllib.request

from scn.ai import ai
from scn.engine import (
    AUTO,
    CheckpointEngine,
    CheckpointKind,
    Expectation,
    Severity,
    Surface,
)
from scn.surfaces import DocReader, SheetReader, TrackerReader


# ---------------------------------------------------------------------------
# Module-level helpers (pure functions — no session state)
# ---------------------------------------------------------------------------

def _snapshot(target: ai) -> dict:
    """Deep-copy the ai's primitive fields at enqueue time (§4.2 snapshot rule)."""
    return copy.copy({k: v for k, v in vars(target).items() if v is not None})


def _current_test_tag() -> str:
    """Derive a triage tag from pytest's running test id (§3.6 tag source)."""
    raw = os.environ.get("PYTEST_CURRENT_TEST", "unknown")
    return raw.split("::")[-1]


class FixtureTokenError(RuntimeError):
    """GAS WebApp rejected the test token (missing, mismatched, or expired)."""


class FixtureError(RuntimeError):
    """GAS fixture returned an application-level error."""


_AUTH_COOKIE_DOMAINS = {"script.google.com", ".google.com", "accounts.google.com"}

_AUTH_FILE = pathlib.Path(__file__).parent.parent / ".auth" / "user.json"


def _load_auth_cookie_header() -> str | None:
    """Load Playwright auth cookies from .auth/user.json and return a Cookie header string.

    Only cookies whose domain matches Google's auth domains are included.
    Returns None if the auth file is absent (falls through to unauthenticated request).
    """
    if not _AUTH_FILE.exists():
        return None
    try:
        state = json.loads(_AUTH_FILE.read_text())
    except Exception:
        return None
    parts = []
    for c in state.get("cookies", []):
        domain = c.get("domain", "")
        if any(domain == d or domain.endswith(d) for d in _AUTH_COOKIE_DOMAINS):
            parts.append(f"{c['name']}={c['value']}")
    return "; ".join(parts) if parts else None


def _http_post(url: str, payload: dict, timeout: int = 360) -> dict:
    """Low-level HTTP POST; returns parsed JSON; raises on token/HTTP/parse errors."""
    if not url:
        raise RuntimeError(
            "webappTestUrl not set in local.settings.json"
        )

    data = json.dumps(payload).encode("utf-8")
    headers: dict = {"Content-Type": "application/json"}
    # /dev URLs require Google auth; inject saved Playwright cookies when present.
    if url.endswith("/dev"):
        cookie = _load_auth_cookie_header()
        if cookie:
            headers["Cookie"] = cookie
    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"HTTP {exc.code} from GAS WebApp (action={payload.get('action')!r}): {raw!r}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Network error (action={payload.get('action')!r}): {exc.reason}"
        ) from exc

    if raw in ("test-token-unauthorized", "test-token-expired"):
        raise FixtureTokenError(
            f"GAS rejected test token for action={payload.get('action')!r}: {raw}. "
            "Re-register with: python scripts/refresh_test_token.py (or npm run deploy:test)."
        )

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Non-JSON response (action={payload.get('action')!r}): {raw!r}"
        ) from exc

    if "error" in result:
        raise FixtureError(
            f"GAS returned error for action={payload.get('action')!r}: {result['error']}"
        )

    return result


# ---------------------------------------------------------------------------
# ScenarioSession
# ---------------------------------------------------------------------------

class ScenarioSession:
    """Thin driver for §16.10 scenario journeys.

    Created via new_doc(); torn down via close().
    The author writes acts + expectations + checkpoints against `scn` (an instance).
    """

    def __init__(
        self,
        *,
        doc_id: str,
        sheet_id: str,
        settings: dict,
        request=None,
    ) -> None:
        self.doc_id = doc_id
        self.sheet_id = sheet_id
        self.settings = settings
        self.tracker_present: bool = False
        self.engine = CheckpointEngine()
        self._seq: int = 0
        self._request = request  # pytest FixtureRequest; used by checkpoint() for JUnit properties (T24)
        # Attach after creation: scn.ui = UiDriver(page, doc_id=scn.doc_id)
        self.ui: UiDriver | None = None

    # ------------------------------------------------------------------
    # Private HTTP helpers
    # ------------------------------------------------------------------

    def _post(self, payload: dict, *, timeout: int = 360) -> dict:
        """POST JSON payload to webappTestUrl; delegates to module-level _http_post."""
        url = self.settings.get("webappTestUrl") or ""
        return _http_post(url, payload, timeout)

    def _post_route(self, action: str, extra: dict | None = None) -> dict:
        """POST a named webapp route with the test token."""
        payload = {"action": action, "testToken": self.settings.get("testToken") or ""}
        if extra:
            payload.update(extra)
        return self._post(payload)

    def _post_fixture(self, fixture_name: str, extra: dict | None = None) -> dict:
        """POST run_fixture with fixture_name and the current doc ID."""
        payload = {
            "action": "run_fixture",
            "testToken": self.settings.get("testToken") or "",
            "fixture": fixture_name,
            "testDocId": self.doc_id,
        }
        if extra:
            payload.update(extra)
        return self._post(payload)

    def _gid(self, target: ai) -> str:
        """Construct the globalId from doc_id + target.action_id (§16.11 #3)."""
        if not target.action_id:
            raise ValueError(
                f"Cannot address target by globalId: ai.action_id is not set. "
                "Pin action_id on the ai after a sync/read before calling write acts."
            )
        return f"{self.doc_id}/{target.action_id}"

    # ------------------------------------------------------------------
    # Lifecycle (§16.9 / §3.3)
    # ------------------------------------------------------------------

    @classmethod
    def new_doc(cls, settings: dict, *, request=None) -> "ScenarioSession":
        """Create a guaranteed-clean empty journey doc (§16.11 #1).

        Calls begin_journey_session (AtddContracts.js); synchronous response carries docId.
        Pass request=<pytest FixtureRequest> to enable JUnit property emission (T24).
        """
        url = settings.get("webappTestUrl") or ""
        token = settings.get("testToken") or ""
        result = _http_post(url, {"action": "begin_journey_session", "testToken": token})

        doc_id = result.get("docId")
        if not doc_id:
            raise RuntimeError(f"begin_journey_session response missing docId: {result}")

        return cls(
            doc_id=doc_id,
            sheet_id=settings["testSheetId"],
            settings=settings,
            request=request,
        )

    def close(self) -> None:
        """Trash the journey doc and assert the expectation queue is empty (§4.6).

        Calls end_journey_session (AtddContracts.js); then engine.close() enforces
        the drain invariant — a non-empty queue is a DrainInvariantError (test failure).
        """
        self._post_route("end_journey_session", {"docId": self.doc_id})
        self.engine.close()

    # ------------------------------------------------------------------
    # Acts — HTTP mutations (§16.9 / §3.4)
    # ------------------------------------------------------------------

    def append_paragraph(self, text: str) -> None:
        """Insert a paragraph into the journey doc (no action implied until sync).

        Routes through the append_doc_paragraph testToken-gated route (WebApp.js).
        Text is appended as a plain paragraph; the AI-N: token causes sync to detect it.
        """
        self._post_route("append_doc_paragraph", {"testDocId": self.doc_id, "text": text})

    def insert_tracker(self) -> None:
        """Insert/refresh the tracker table; widens surface set of subsequent verify_all_expectations.

        # TODO(.8 CONTRACT GAP): fixture name 'insert_tracker_table' is a placeholder.
        # Confirm with bead .8 before .11/.13 run. See epic Coordination Log.
        """
        self._post_fixture("insert_tracker_table")
        self.tracker_present = True

    def sync(self) -> None:
        """Synchronise the journey doc via the sync_document fixture.

        Routes through run_fixture('sync_document') — the testToken-gated path that
        calls GAS syncDocument() internally, which in turn POSTs sync_action_rows with
        WEBAPP_SECRET and drains ACTION_SHEET_QUEUE before responding (§16.11 #4).
        A following sync() is how the scenario forces an async act to convergence.
        """
        resp = self._post_fixture("sync_document")
        data = resp.get("data") or {}
        if not data.get("synced"):
            raise RuntimeError(
                f"sync_document fixture returned unexpected response: {resp}"
            )

    def edit_sheet(self, target: ai, **fields) -> None:
        """Edit one or more sheet fields for target (addressed by globalId, §16.11 #3).

        Replicates onActionSheetEdit's Dirty + Date-Modified stamp on the API path (§16.11 #2).
        """
        self._post_route("edit_action_row", {"global_id": self._gid(target), "fields": fields})

    def set_status(self, target: ai, status: str) -> None:
        """Set status via the sidebar path (async; converges on next sync(), §16.11 #4)."""
        self._post_route("patch_action_status", {"global_id": self._gid(target), "status": status})

    def delete(self, target: ai) -> None:
        """Delete the target row (addressed by globalId, §16.11 #3); Sync Status → 'Deleted'."""
        self._post_route("delete_action_row", {"global_id": self._gid(target)})

    # ------------------------------------------------------------------
    # Queries — read-only, no mutation (§16.9 / §3.5)
    # ------------------------------------------------------------------

    def doc_items(self) -> list[ai]:
        """Parse floating actions from the live journey doc (.docx download, DOC surface)."""
        from tests.helpers.download import download_docx
        docx = download_docx(self.doc_id)
        return DocReader().read(docx, self.doc_id)

    def sheet_rows(self) -> list[ai]:
        """Download the ActionSheet (.xlsx), parse rows scoped to this doc (SHEET surface)."""
        from tests.helpers.download import download_xlsx
        xlsx = download_xlsx(self.sheet_id)
        return SheetReader().read(xlsx, self.doc_id)

    def archive_rows(self, doc_id: str) -> list[ai]:
        """Download the ActionSheet (.xlsx), parse Archive-tab rows scoped to doc_id."""
        from tests.helpers.download import download_xlsx
        xlsx = download_xlsx(self.sheet_id)
        return SheetReader().read(xlsx, doc_id, tab_name="Archive")

    def find_sheet_actions(self) -> list[ai]:
        """Fetch current-doc sheet rows via the find_sheet_actions webapp route."""
        resp = self._post_route("find_sheet_actions", {"docId": self.doc_id})
        rows = resp.get("rows") or []
        return [_row_dict_to_ai(r) for r in rows]

    def tracker_id_urls(self) -> dict:
        """Return {action_id: id_url} for tracker rows that have an ID-column hyperlink."""
        from tests.helpers.download import download_docx
        from scn.surfaces import TrackerReader
        docx = download_docx(self.doc_id)
        rows = TrackerReader().read(docx, self.doc_id)
        return {r.action_id: r.id_url for r in rows if getattr(r, "id_url", None)}

    def verify_consistency(self, scope: Surface = Surface.DOC) -> dict:
        """Single server authority for consistency verification (§16.7 + 6ov.8).

        This is the ONLY code path permitted to call the GAS routes verify_action_rows
        and verify_chip_integrity.  No other helper, test, or module may POST those
        routes directly.

        scope=DOC  — SERVER authority.  Posts verify_action_rows + verify_chip_integrity
                     to the live GAS WebApp.  Sees real-time doc state that a downloaded
                     artifact cannot capture (globalId linkage, rendered chip icons).
                     Raises AssertionError on any violation.  Called standalone or
                     internally by every INTEGRITY checkpoint via the read_consistency
                     closure (session.py:511-519).

        scope=SHEET — ARTIFACT-convenience authority.  Downloads the xlsx and asserts
                      col7 doc_name present and col10 sync_status not an error state.
                      Does NOT call any GAS route.  Equivalent to an artifact-side
                      verify(on=SHEET) check; placed here for caller ergonomics only.
        """
        if scope == Surface.SHEET:
            from tests.helpers.download import download_xlsx
            xlsx = download_xlsx(self.sheet_id)
            rows = SheetReader().read(xlsx, self.doc_id)
            _SYNC_ERROR_STATES = {"Dirty", "Deleted", "Doc Not Found"}
            for row in rows:
                # M2-guarded col 7: document_formula must resolve to a doc_id and doc_name
                assert row.doc_name is not None, (
                    f"col7 document_formula missing doc_name for {row.global_id!r}"
                )
                # M2-guarded col 10: after a clean sync no row should be in an error state.
                # Blank ("") is the normal post-sync value; Dirty/Deleted/Doc Not Found are errors.
                assert row.sync_status not in _SYNC_ERROR_STATES, (
                    f"col10 sync_status {row.sync_status!r} for {row.global_id!r}"
                )
            return {"scope": "SHEET", "rows": len(rows)}
        result = self._post_route("verify_action_rows", {"docId": self.doc_id})
        chip = self._post_route("verify_chip_integrity", {"docId": self.doc_id})
        violations = chip.get("violations", [])
        if violations:
            lines = "\n".join(f"  {v['paragraph']}: {v['issue']}" for v in violations)
            raise AssertionError(f"Chip integrity violations ({len(violations)}):\n{lines}")
        return result

    # ------------------------------------------------------------------
    # Expectation delegation — thin enqueuers (§16.9 / §3.6)
    # ------------------------------------------------------------------

    def _enqueue(self, exp: Expectation) -> None:
        self.engine.enqueue(exp)
        self._seq += 1

    def verify_all_expectations(
        self,
        target: ai,
        *,
        at=AUTO,
        severity: Severity = Severity.FAIL,
        tag: str = "",
        entry_point: str = "",
    ) -> None:
        """Enqueue a present-and-consistent expectation across DOC + SHEET (+ TRACKER if present).

        Snapshot the ai NOW (§4.2) — pin action_id/status before calling this.
        needs_consistency=True: the CONSISTENCY obligation runs at the next INTEGRITY.
        entry_point (T1/T17): the state-modifying entry point this expectation exercises;
        when set, emits an ep.<entry_point>.<surface> property for entry-point coverage.
        """
        surfaces = frozenset(
            {Surface.DOC, Surface.SHEET}
            | ({Surface.TRACKER} if self.tracker_present else set())
        )
        exp = Expectation(
            seq=self._seq,
            expected=_snapshot(target),
            surfaces=surfaces,
            remaining=set(surfaces),
            target=at,
            kind="PRESENT_CONSISTENT",
            within=None,
            severity=severity,
            needs_consistency=True,
            tag=tag or _current_test_tag(),
            entry_point=entry_point,
        )
        self._enqueue(exp)

    def verify(
        self,
        target: ai,
        *,
        on: Surface,
        at=AUTO,
        within: str | None = None,
        severity: Severity = Severity.FAIL,
        tag: str = "",
        entry_point: str = "",
        **field_overrides,
    ) -> None:
        """Enqueue a single-surface present-and-consistent expectation.

        field_overrides (e.g. status="Open") override the snapshot for this surface only (§16.10 Act 4).
        entry_point (T1/T17): the state-modifying entry point this expectation exercises;
        when set, emits an ep.<entry_point>.<surface> property for entry-point coverage.
        """
        snap = _snapshot(target)
        snap.update(field_overrides)
        exp = Expectation(
            seq=self._seq,
            expected=snap,
            surfaces=frozenset({on}),
            remaining={on},
            target=at,
            kind="PRESENT_CONSISTENT",
            within=within,
            severity=severity,
            needs_consistency=False,
            tag=tag or _current_test_tag(),
            entry_point=entry_point,
        )
        self._enqueue(exp)

    def expect_absent(
        self,
        target: ai,
        *,
        on: Surface,
        at=AUTO,
        tag: str = "",
    ) -> None:
        """Enqueue an absence expectation (terminal; sheet Sync Status = 'Deleted')."""
        exp = Expectation(
            seq=self._seq,
            expected=_snapshot(target),
            surfaces=frozenset({on}),
            remaining={on},
            target=at,
            kind="ABSENT",
            within=None,
            severity=Severity.FAIL,
            needs_consistency=False,
            tag=tag or _current_test_tag(),
        )
        self._enqueue(exp)

    def expect_callable(
        self,
        check: "Callable[[], str | None]",
        *,
        on: Surface,
        at=AUTO,
        severity: Severity = Severity.FAIL,
        tag: str = "",
        entry_point: str = "",
    ) -> None:
        """Enqueue a generic drained expectation backed by a zero-arg check callable.

        `check()` is called at drain time; return None for pass, or an error string
        for failure. Reuses the standard checkpoint/drain mechanism (and its
        ac.<tag>.<surface> / ep.<entry_point>.<surface> emission) for expectations
        that aren't ai-shaped — e.g. Team Scope / DocData state (GTaskSheet-me6w.6,
        T24 resolution: no parallel emission path).
        """
        exp = Expectation(
            seq=self._seq,
            expected={"check": check},
            surfaces=frozenset({on}),
            remaining={on},
            target=at,
            kind="CALLABLE",
            within=None,
            severity=severity,
            needs_consistency=False,
            tag=tag or _current_test_tag(),
            entry_point=entry_point,
        )
        self._enqueue(exp)

    # ------------------------------------------------------------------
    # UI expectations — convenience wrappers that delegate to scn.ui (§16.8)
    # ------------------------------------------------------------------

    def expect_visible(self, card, *, timeout: str = "5s") -> None:
        """Assert the preview card is visible; delegates to scn.ui (§16.8).

        Convenience wrapper so scenarios write `scn.expect_visible(card)` per
        the §16.8 usage pattern.
        """
        if self.ui is None:
            raise RuntimeError(
                "scn.expect_visible requires scn.ui — "
                "set scn.ui = UiDriver(page, doc_id=scn.doc_id)"
            )
        self.ui.expect_visible(card, timeout=timeout)

    def expect_alt(
        self,
        locator,
        text: str,
        *,
        severity: Severity = Severity.FAIL,
    ) -> None:
        """Assert aria-label / alt / title of element equals text; delegates to scn.ui."""
        if self.ui is None:
            raise RuntimeError(
                "scn.expect_alt requires scn.ui — "
                "set scn.ui = UiDriver(page, doc_id=scn.doc_id)"
            )
        self.ui.expect_alt(locator, text, severity=severity)

    def checkpoint(
        self,
        kind: CheckpointKind,
        *,
        on: frozenset | None = None,
        label: str | None = None,
    ) -> list[str]:
        """Drain queued expectations at this checkpoint; return any warnings.

        Builds a lazy-download read closure: each surface is downloaded at most once
        per checkpoint call. DOC and TRACKER share the same .docx download.
        """
        from tests.helpers.download import download_docx, download_xlsx

        _bytes_cache: dict = {}

        def read(surface: Surface) -> list[ai]:
            if surface in (Surface.DOC, Surface.TRACKER):
                if "docx" not in _bytes_cache:
                    _bytes_cache["docx"] = download_docx(self.doc_id)
                docx = _bytes_cache["docx"]
                if surface == Surface.DOC:
                    return DocReader().read(docx, self.doc_id)
                return TrackerReader().read(docx, self.doc_id)
            if surface == Surface.SHEET:
                if "xlsx" not in _bytes_cache:
                    _bytes_cache["xlsx"] = download_xlsx(self.sheet_id)
                return SheetReader().read(_bytes_cache["xlsx"], self.doc_id)
            if surface == Surface.UI:
                return self.ui.read_current() if self.ui is not None else []
            return []

        def read_consistency() -> dict:
            return self.verify_consistency()

        warnings, drained_records = self.engine.drain(
            kind,
            label=label,
            on=on,
            read=read,
            read_consistency=read_consistency,
        )
        if self._request is not None:
            for tag, surface, severity, entry_point in drained_records:
                self._request.node.user_properties.append((f"ac.{tag}.{surface}", severity))
                # T1/T17 entry-point coverage: emit ep.* only when the expectation tagged
                # an entry point, so scripts/check_coverage.py can diff against
                # ENTRY_POINT_REGISTRY (GTaskSheet-me6w.2).
                if entry_point:
                    self._request.node.user_properties.append(
                        (f"ep.{entry_point}.{surface}", severity)
                    )
        return warnings


# ---------------------------------------------------------------------------
# Module-level row conversion helper
# ---------------------------------------------------------------------------

def _row_dict_to_ai(row: dict) -> ai:
    """Convert a find_sheet_actions response row (JSON dict) to an ai.

    ContractSchema sheetAction field names → ai field names.
    Dynamic attributes (global_id, assignee_name, sync_status) attached post-init.
    """
    item = ai(
        action=row.get("action_text") or "",
        assignee=row.get("assignee_email") or None,
        action_id=row.get("action_id") or None,
        status=row.get("status") or None,
    )
    item.global_id = row.get("global_id") or ""
    item.assignee_name = row.get("assignee_name") or ""
    item.sync_status = row.get("sync_status") or ""
    item.doc_id = row.get("doc_id") or ""
    item.doc_name = row.get("doc_name") or ""
    return item
