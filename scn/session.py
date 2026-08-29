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

import contextlib
import copy
import json
import os
import pathlib
import re
import sys
import time
import uuid
import urllib.error
import urllib.parse
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
from scn.reporter import NullReporter, Reporter
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


_SETTINGS_PATH = pathlib.Path(__file__).parent.parent / "local.settings.json"
_PROJECT_ROOT = pathlib.Path(__file__).parent.parent


def _devstandard_playwright_auth_dir() -> pathlib.Path:
    devstandard = os.environ.get("DEVSTANDARD")
    if not devstandard:
        raise RuntimeError(
            "$DEVSTANDARD is not set -- required to resolve the shared Playwright auth "
            "resolver (see /home/stuar/.claude/CLAUDE.md §10a: export DEVSTANDARD=/mnt/c/dev/DevStandard "
            "in your shell profile)."
        )
    d = pathlib.Path(devstandard) / "tools" / "playwright-auth"
    if not d.is_dir():
        raise RuntimeError(f"$DEVSTANDARD is set to {devstandard!r} but {d} does not exist.")
    return d


_devstandard_dir = _devstandard_playwright_auth_dir()
if str(_devstandard_dir) not in sys.path:
    sys.path.insert(0, str(_devstandard_dir))
from playwright_auth import resolve_auth_file as _ds_resolve_auth_file  # noqa: E402


def resolve_auth_file(role: str = "primary") -> pathlib.Path:
    """Resolve a Playwright storageState file for a project role.

    Delegates to DevStandard's canonical resolver
    ($DEVSTANDARD/tools/playwright-auth/playwright_auth.py) so this project
    carries no forked copy of the resolution logic to drift out of sync --
    see docs/standards/playwright-shared-auth.md. Kept as a same-signature
    wrapper (role-only, no project_root) so every existing call site in this
    project (scn.session, tests/helpers/download.py, tests/helpers/auth_probe.py,
    scripts/export_gas.py) is unaffected.
    """
    return _ds_resolve_auth_file(role, project_root=_PROJECT_ROOT)


_AUTH_FILE = resolve_auth_file()


def _load_auth_cookie_header() -> str | None:
    """Load Playwright auth cookies from the resolved auth file and return a Cookie header string.

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


_HTTP_POST_MAX_ATTEMPTS = 5
_HTTP_POST_RETRY_DELAY_S = 3  # base delay; _http_post backs off exponentially from this


def _http_post(url: str, payload: dict, timeout: int = 360) -> dict:
    """Low-level HTTP POST; returns parsed JSON; raises on token/HTTP/parse errors.

    Retries a bounded number of times on three symptoms of the same underlying
    flakiness: (1) the response is the GAS echo page instead of JSON, (2) a
    Drive "Page Not Found" error page arrives with HTTP 404, and (3) the read
    side stalls until the socket timeout fires (`TimeoutError`). None of these
    is a fixed deployment-propagation window (observed recurring 50+ minutes
    after a deploy, and intermittently mid-run with no redeploy at all) — all
    three are the /exec -> script.googleusercontent.com/echo routing
    intermittently failing to resolve (replayed as GET dropping the POST body
    for the first case, a bare 404 instead of a redirect for the second, and
    a hung read for the third). A fresh POST attempt either lands on the real
    handler or hits the same routing quirk again, so a bounded retry with
    exponential backoff is the fix, not a longer flat sleep. Every other
    failure (non-404 HTTP error, token rejection, network error) raises
    immediately — only these three routing symptoms are retried.

    gts-f3me.4 (Stage B, TD-PLAN-21-08.md): `TimeoutError` was previously
    unretried and uncaught. `urllib.request.urlopen`'s `do_open` wraps only
    `h.request()` in `except OSError: raise URLError(err)`;
    `h.getresponse()` (visible in all three original tracebacks at
    request.py:1348) propagates `TimeoutError` raw, bypassing the
    `URLError` handler and the retry/backoff loop entirely. Note `socket.
    timeout` is a `TimeoutError` alias as of CPython 3.10, so catching
    `TimeoutError` covers both spellings.

    gts-f3me.5: bumped from 3 attempts/flat 3s delay to 5 attempts/exponential
    backoff (3s, 6s, 12s, 24s) after a full sweep (gas-test3.log) hit this
    exhausted-retry path 4x in one run against zero occurrences in the two
    prior sweeps (gas-test.log, gas-test2.log) — a step change from baseline,
    plausibly inflated by that run's general slowdown (more wall time / HTTP
    call volume = more exposure to the same low-probability routing glitch;
    see gts-f3me.6, the cause-side investigation this bead deliberately does
    not conflate with). Widening the budget is a low-risk, isolated mitigation
    of the symptom either way.
    """
    if not url:
        raise RuntimeError(
            "webappTestUrl not set in local.settings.json"
        )

    # Correlation instrumentation (gts-obry.1): every call is stamped with a
    # client-generated opId (a uuid4, reused across all retry attempts of the
    # SAME logical call -- computed once, before the retry loop below) and an
    # initiatedAt epoch-ms timestamp. doPost's existing
    # GasLogger.startOp(opId) (src/WebApp.js, gts-j8cn) already stamps any
    # caller-supplied opId onto every log entry it makes as `parentOp`,
    # distinct from the fresh `op` each execution mints for itself -- this
    # was previously always null for Python-initiated calls since nothing
    # populated it. Two log groups sharing one parentOp but carrying
    # different op values means the SAME client call was dispatched twice by
    # the platform (a real duplicate-execution bug); different parentOp
    # values means two genuinely separate calls. A caller that already set
    # its own opId (chaining an existing op) is not overwritten.
    payload.setdefault("opId", str(uuid.uuid4()))
    payload.setdefault("initiatedAt", int(time.time() * 1000))

    data = json.dumps(payload).encode("utf-8")
    headers: dict = {"Content-Type": "application/json"}
    # /dev URLs require Google auth; inject saved Playwright cookies when present.
    if url.endswith("/dev"):
        cookie = _load_auth_cookie_header()
        if cookie:
            headers["Cookie"] = cookie

    for attempt in range(1, _HTTP_POST_MAX_ATTEMPTS + 1):
        req = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                final_url = resp.geturl()
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404 and attempt < _HTTP_POST_MAX_ATTEMPTS:
                time.sleep(_HTTP_POST_RETRY_DELAY_S * (2 ** (attempt - 1)))
                continue
            raise RuntimeError(
                f"HTTP {exc.code} from GAS WebApp (action={payload.get('action')!r}): {raw!r}"
                + (f" (after {attempt} attempts)" if exc.code == 404 else "")
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Network error (action={payload.get('action')!r}): {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            # gts-f3me.4: urllib.request.urlopen's do_open wraps only
            # h.request() in `except OSError: raise URLError(err)` -- a
            # read-side stall inside h.getresponse() (request.py:1348)
            # propagates TimeoutError/socket.timeout raw, past the
            # URLError handler above, so it was previously unretried and
            # uncaught (bare traceback out of _http_post). Route it
            # through the same bounded-retry/backoff path as the other two
            # routing symptoms above -- a fresh attempt either completes
            # inside the timeout or hits the same stall again.
            if attempt < _HTTP_POST_MAX_ATTEMPTS:
                time.sleep(_HTTP_POST_RETRY_DELAY_S * (2 ** (attempt - 1)))
                continue
            raise RuntimeError(
                f"Timed out waiting for response (action={payload.get('action')!r}, "
                f"timeout={timeout}s) after {_HTTP_POST_MAX_ATTEMPTS} attempts"
            ) from exc

        if raw in ("test-token-unauthorized", "test-token-expired"):
            raise FixtureTokenError(
                f"GAS rejected test token for action={payload.get('action')!r}: {raw}. "
                "Re-register with: python scripts/refresh_test_token.py (or npm run deploy:test)."
            )

        # GAS always redirects /exec → script.googleusercontent.com/macros/echo (normal).
        # When the final URL differs from the request URL AND the body is non-JSON, include
        # the redirect destination so the cause is unambiguous.
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            redir = f" (redirected to {final_url!r})" if final_url != url else ""
            if attempt < _HTTP_POST_MAX_ATTEMPTS:
                time.sleep(_HTTP_POST_RETRY_DELAY_S * (2 ** (attempt - 1)))
                continue
            raise RuntimeError(
                f"Non-JSON response (action={payload.get('action')!r}){redir}: {raw!r} "
                f"(after {_HTTP_POST_MAX_ATTEMPTS} attempts)"
            ) from exc

        if "error" in result:
            raise FixtureError(
                f"GAS returned error for action={payload.get('action')!r}: {result['error']}"
            )

        return result


def _http_get(url: str, timeout: int = 60) -> str:
    """Low-level HTTP GET; returns the raw response body as text.

    Used for doGet HTML routes (e.g. ADR-0017 ?cmd=preview), which return
    HtmlOutput rather than JSON.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error fetching {url!r}: {exc.reason}") from exc


_GOOG_SCRIPT_INIT_RE = re.compile(r'goog\.script\.init\("((?:[^"\\]|\\.)*)"')
_HEX_ESCAPE_RE = re.compile(r'\\x([0-9a-fA-F]{2})')


def extract_html_output(wrapper: str) -> str:
    """Decode the HtmlService body served via doGet.

    GAS wraps `HtmlService.createHtmlOutput(...)` in a sandboxed-iframe
    bootstrap page where the actual markup is triple-escaped (JS hex-escapes
    plus two layers of JSON-string-escaping) inside a `goog.script.init(...)`
    call. Undo all three layers so callers can assert against the rendered
    HTML directly.
    """
    m = _GOOG_SCRIPT_INIT_RE.search(wrapper)
    if not m:
        raise ValueError(f"goog.script.init(...) not found in response: {wrapper[:200]!r}")
    literal = _HEX_ESCAPE_RE.sub(r'\\u00\1', m.group(1))
    config = json.loads(json.loads('"' + literal + '"'))
    return config["userHtml"]


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
        self._appended_actions: int = 0
        self.engine = CheckpointEngine()
        self._seq: int = 0
        self._request = request  # pytest FixtureRequest; enables JUnit + trace files (T24)
        self._start_time = time.monotonic()  # reporter reports elapsed relative to this
        # Reporter = single owner of trace files + JUnit user_properties (R1, 80mo.16).
        # NullReporter when there is no run context (harness unit tests) — writes no files.
        self._reporter = (
            Reporter(
                start_time=self._start_time,
                request=request,
                axiom_dataset=settings.get("axiomDataset"),
                axiom_token=settings.get("axiomToken"),
            )
            if request is not None
            else NullReporter()
        )
        # Fail-fast fence: a GAS *.error logged after this aborts the next post-Act
        # check (default on; SCN_FAILFAST=0 disables raising). No-op without gasLogDir.
        from tests.helpers.gas_log import clear_logs
        self._gas_fence: float = clear_logs(settings.get("gasLogDir"))
        # Attach after creation: scn.ui = UiDriver(page, doc_id=scn.doc_id)
        self._ui = None
        self._trashed = False  # guards _deferred_trash() idempotency (gts-hroj)

    # ``ui`` is a property so assigning the driver auto-wires the reporter + a
    # back-reference for the post-act fail-fast check — no fixture edits needed.
    @property
    def ui(self):
        return self._ui

    @ui.setter
    def ui(self, driver) -> None:
        self._ui = driver
        if driver is not None:
            driver.reporter = self._reporter
            driver._session = self

    # ------------------------------------------------------------------
    # Private HTTP helpers
    # ------------------------------------------------------------------

    def _post(self, payload: dict, *, timeout: int | None = None) -> dict:
        """POST JSON payload to webappTestUrl; time it and emit an HTTP trace event.

        Unexpected responses (HTTP error / non-JSON / token / GAS error field) are
        raised by _http_post; we record a FAIL HTTP event first so the trace shows
        the bad response at the source (G2 fail-fast signal), then re-raise.

        When `timeout` is omitted, a `payload["fixture"]` present in
        `_CORPUS_SCALED_FIXTURE_TIMEOUTS` (e.g. "sync_all") gets that fixture's
        scaled timeout even on a hand-rolled call that bypasses _post_fixture —
        this used to be advisory-only in _post_fixture, which let a direct
        caller silently under-time a corpus-scaled fixture (gts-a8yh Stage A #3).
        """
        if timeout is None:
            timeout = self._CORPUS_SCALED_FIXTURE_TIMEOUTS.get(payload.get("fixture"), 360)
        url = self.settings.get("webappTestUrl") or ""
        action = payload.get("fixture") or payload.get("action") or "post"
        t0 = time.monotonic()
        try:
            result = _http_post(url, payload, timeout)
        except Exception as exc:
            self._reporter.event(
                "HTTP", action, detail=str(exc)[:200], result="FAIL",
                dur_s=time.monotonic() - t0,
            )
            raise
        self._reporter.event("HTTP", action, dur_s=time.monotonic() - t0)
        return result

    def _post_route(self, action: str, extra: dict | None = None) -> dict:
        """POST a named webapp route with the test token."""
        payload = {"action": action, "testToken": self.settings.get("testToken") or ""}
        if extra:
            payload.update(extra)
        return self._post(payload)

    # Fixtures whose GAS-side execution time scales with the shared TEST
    # corpus's doc count rather than this call's own payload (gts-4m7l):
    # a real syncAll() sweep over 100+ docs can legitimately run past the
    # default 360s client-side read timeout even though the GAS side itself
    # completes well inside it. Stopgap only — see gts-4m7l's durable fix
    # (purge_stale_test_docs, invoked per-session in conftest.py) for the
    # actual corpus-growth cure; this just gives the slow fixture more room
    # while that cure keeps the corpus (and so this timeout's headroom) from
    # eroding again.
    _CORPUS_SCALED_FIXTURE_TIMEOUTS = {"sync_all": 600}

    def _post_fixture(self, fixture_name: str, extra: dict | None = None, *, timeout: int | None = None) -> dict:
        """POST run_fixture with fixture_name and the current doc ID."""
        payload = {
            "action": "run_fixture",
            "testToken": self.settings.get("testToken") or "",
            "fixture": fixture_name,
            "testDocId": self.doc_id,
        }
        if extra:
            payload.update(extra)
        return self._post(payload, timeout=timeout)

    def _gid(self, target: ai) -> str:
        """Construct the globalId from doc_id + target.action_id (§16.11 #3)."""
        if not target.action_id:
            raise ValueError(
                f"Cannot address target by globalId: ai.action_id is not set. "
                "Pin action_id on the ai after a sync/read before calling write acts."
            )
        return f"{self.doc_id}/{target.action_id}"

    # ------------------------------------------------------------------
    # Fail-fast monitor (G2) — single GAS-error scan path
    # ------------------------------------------------------------------

    @staticmethod
    def _failfast_enabled() -> bool:
        """Fail-fast aborts by default; SCN_FAILFAST=0 downgrades to trace-only."""
        return os.environ.get("SCN_FAILFAST") != "0"

    def _check_gas_errors(self, fence: float | None = None, *, raise_on_error: bool | None = None):
        """Scan the GAS log dir for any `*.error` entry since the fence.

        The single GAS-error scan routine: both the always-on post-Act guard and
        assert_no_addon_error() call this (no duplicated scan logic). On a hit it
        records a MONITOR FAIL trace event and advances the running fence past the
        entry. Whether it raises:
          * raise_on_error=None  → default-on fail-fast, suppressed by SCN_FAILFAST=0
            (post-Act guard);
          * raise_on_error=True  → always raise (explicit assert_no_addon_error).
        No-op when gasLogDir is unset. Returns the matched entry (or None).
        """
        from datetime import datetime
        from tests.helpers.gas_log import collect_logs

        log_dir = self.settings.get("gasLogDir")
        if not log_dir:
            return None
        if fence is None:
            fence = self._gas_fence
        entries = collect_logs(
            log_dir,
            lambda e: str(e.get("tag", "")).endswith(".error"),
            after=fence,
        )
        entry = entries[0] if entries else None
        if not entry:
            return None

        tag = entry.get("tag", "?")
        data = entry.get("data")
        self._reporter.event(
            "MONITOR", str(tag), detail=str(data)[:200], result="FAIL",
        )
        # Advance the running fence past this entry so we don't re-detect it.
        try:
            ts = datetime.fromisoformat(
                str(entry.get("ts", "")).replace("Z", "+00:00")
            ).timestamp()
            self._gas_fence = max(self._gas_fence, ts + 0.001)
        except (ValueError, OSError):
            pass
        should_raise = self._failfast_enabled() if raise_on_error is None else raise_on_error
        if should_raise:
            raise AssertionError(f"GAS backend error: {tag} {data}")
        return entry

    def _attach_ui_failure_screenshot(self, surface: Surface, tag: str, error: str) -> None:
        """on_ui_fail hook for engine.drain() (R6, GTaskSheet-16kh).

        Attaches a screenshot of the live page to the Allure report when a
        Surface.UI FAIL-severity check misses, named "<tag> <surface> FAIL".
        No-op if scn.ui is not attached.
        """
        if self.ui is not None:
            self._reporter.attach_screenshot(self.ui._page, name=f"{tag} {surface.value} FAIL")

    @contextlib.contextmanager
    def _act(self, name: str, detail: str = ""):
        """Run an Act body as a traced step, then the post-act fail-fast check."""
        with self._reporter.step("ACT", name, detail):
            yield
        self._check_gas_errors()

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
        t0 = time.monotonic()
        result = _http_post(url, {"action": "begin_journey_session", "testToken": token})
        dur_s = time.monotonic() - t0

        doc_id = result.get("docId")
        if not doc_id:
            raise RuntimeError(f"begin_journey_session response missing docId: {result}")

        instance = cls(
            doc_id=doc_id,
            sheet_id=settings["testSheetId"],
            settings=settings,
            request=request,
        )
        # The Reporter doesn't exist until after this POST returns (it's keyed on
        # docId), so emit it as a synthetic first event now instead of leaving doc
        # creation invisible (§4.2, GTaskSheet-ishz.1).
        instance._reporter.event("HTTP", "begin_journey_session", dur_s=dur_s, _t_elapsed=0.0)
        if hasattr(request, "addfinalizer"):
            # Deferred trash, not immediate (gts-hroj): registering this as a
            # pytest finalizer — rather than leaving it to the caller's own
            # `finally:` — means it runs in the teardown phase, strictly
            # after the call-phase failure report. See _deferred_trash()'s
            # docstring for why that ordering matters. hasattr-guarded (not
            # `is not None`) because some non-pytest callers pass a bare
            # sentinel object as `request` just to opt into Reporter creation
            # (e.g. test_scn_session.py's test doubles) — those aren't real
            # FixtureRequests and have no finalizer machinery to register with.
            request.addfinalizer(instance._deferred_trash)
        return instance

    def close(self) -> None:
        """Assert the expectation queue is empty, then trash the journey doc (§4.6).

        engine.close() runs first so a caller invoking close() directly still
        observes the DrainInvariantError (a non-empty queue is a real test
        failure) at this call site, rather than it surfacing later out of a
        finalizer. Trashing itself is delegated to _deferred_trash() — see its
        docstring for why multi-doc *tests* should prefer registering that via
        new_doc(request=...) over calling close() from their own `finally:`.
        """
        self.engine.close()
        self._deferred_trash()

    def _deferred_trash(self) -> None:
        """Trash the journey doc and close the reporter (gts-hroj).

        Split out of close() so new_doc() can register it as a pytest
        fixture finalizer (request.addfinalizer) instead of a test running it
        from its own `finally:`. Fixture finalizers run in pytest's teardown
        phase, strictly after the call-phase failure report — and this
        suite's universal UI-failure-diagnostics hook
        (conftest.py::pytest_runtest_makereport, GTaskSheet-3tkf) fires
        exactly there. A test that trashes its own doc inside `finally:`
        (part of the call phase — see the test's own stack, not a hook) beats
        the diagnostics hook to it every time, so the captured screenshot
        always shows the post-trash "file is in trash" Drive chrome
        regardless of the real failure (mis-diagnosed as a product bug twice:
        gts-lirp 2026-08-05, gts-ir1f attempt #4 2026-08-06).

        Multi-doc live tests: let this run via the new_doc(request=...)
        finalizer. Do not call this (or close()) from a test's own
        `finally:` — call `scn.engine.close()` there instead if the
        drain-invariant assertion still needs to happen at that point.

        Idempotent — self._trashed guards a second invocation (e.g. close()
        called explicitly on an instance that also has the auto-registered
        finalizer) from re-trashing or double-closing the reporter.
        """
        if self._trashed:
            return
        self._trashed = True
        try:
            self._post_route("end_journey_session", {"docId": self.doc_id})
        except Exception:
            pass
        self._reporter.close()

    # ------------------------------------------------------------------
    # Acts — HTTP mutations (§16.9 / §3.4)
    # ------------------------------------------------------------------

    def append_paragraph(self, text: str) -> None:
        """Insert a paragraph into the journey doc (no action implied until sync).

        Routes through the append_doc_paragraph testToken-gated route (WebApp.js).
        Text is appended as a plain paragraph; the AI-N: token causes sync to detect it.
        """
        with self._act("append_paragraph", text[:60]):
            self._post_route("append_doc_paragraph", {"testDocId": self.doc_id, "text": text})
        self._appended_actions += 1

    def insert_tracker(self) -> None:
        """Insert/refresh the tracker table; widens surface set of subsequent verify_all_expectations.

        # TODO(.8 CONTRACT GAP): fixture name 'insert_tracker_table' is a placeholder.
        # Confirm with bead .8 before .11/.13 run. See epic Coordination Log.
        """
        with self._act("insert_tracker"):
            self._post_fixture("insert_tracker_table")
        self.tracker_present = True

    def sync(self) -> None:
        """Synchronise the journey doc via the sync_document fixture.

        Routes through run_fixture('sync_document') — the testToken-gated path that
        calls GAS syncDocument() internally, which in turn POSTs sync_action_rows with
        WEBAPP_SECRET and drains ACTION_SHEET_QUEUE before responding (§16.11 #4).
        A following sync() is how the scenario forces an async act to convergence.
        """
        with self._act("sync"):
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
        with self._act("edit_sheet", f"{target.action_id} {fields}"[:60]):
            self._post_route("edit_action_row", {"global_id": self._gid(target), "fields": fields})

    def set_status(self, target: ai, status: str) -> None:
        """Set status via the sidebar path (async; converges on next sync(), §16.11 #4)."""
        with self._act("set_status", f"{target.action_id} -> {status}"):
            self._post_route("patch_action_status", {"global_id": self._gid(target), "status": status})

    def link_preview_status_change(self, target: ai, status: str) -> None:
        """Standard-run substitute for the Act-5 link-preview card + in-card status change.

        Rendering the onLinkPreview card requires a cursor-placement + retry
        sequence (Ctrl+F -> Enter -> Escape, move away, re-place —
        GTaskSheet-39jk/cug8, UiDriver.open_link_preview) that takes ~1-2 min.
        The rendered-card fidelity checks (card header 'AI-N:', globalId
        bubble, status chip) and the in-card status click
        (_setStatusFromPreview, ENTRY_POINT_DEFERRED) are exercised by
        tests/test_link_preview.py.

        For the (fast) automated journey this drives the status change
        through the same core the card's status control invokes — the
        patch_action_status route — leaving durable-surface verification to
        the caller.
        """
        self.set_status(target, status)
        target.status = status

    def delete(self, target: ai) -> None:
        """Delete the target row (addressed by globalId, §16.11 #3); Sync Status → 'Deleted'."""
        with self._act("delete", str(target.action_id)):
            self._post_route("delete_action_row", {"global_id": self._gid(target)})

    # ------------------------------------------------------------------
    # Queries — read-only, no mutation (§16.9 / §3.5)
    # ------------------------------------------------------------------

    def doc_items(self) -> list[ai]:
        """Parse floating actions from the live journey doc (.docx download, DOC surface)."""
        from tests.helpers.download import download_docx
        with self._reporter.step("QUERY", "doc_items"):
            docx = download_docx(self.doc_id)
            return DocReader().read(docx, self.doc_id)

    def sheet_rows(self) -> list[ai]:
        """Download the ActionSheet (.xlsx), parse rows scoped to this doc (SHEET surface)."""
        from tests.helpers.download import download_xlsx
        with self._reporter.step("QUERY", "sheet_rows"):
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

    def fetch_preview_html(self, ain: str, *, doc_id: str | None = None) -> str:
        """GET the ADR-0017 Phase 1 anonymous chip-preview notice page.

        Hits doGet ?cmd=preview&docId=<doc_id>&ain=<ain> (no test token —
        this route is the anonymous, unauthenticated chip-link landing page).
        Returns the decoded HtmlOutput markup (see extract_html_output).
        """
        url = self.settings.get("webappTestUrl") or ""
        if not url:
            raise RuntimeError("webappTestUrl not set in local.settings.json")
        qs = urllib.parse.urlencode({"cmd": "preview", "docId": doc_id or self.doc_id, "ain": ain})
        with self._reporter.step("QUERY", "fetch_preview_html"):
            return extract_html_output(_http_get(f"{url}?{qs}"))

    def fetch_team_view_html(self, team_id: str) -> str:
        """GET the branded team-view page: doGet ?cmd=teamview&team=<team_id>.

        Anonymous, unauthenticated route — same disclosure model as
        fetch_preview_html. Returns the decoded HtmlOutput markup.
        """
        url = self.settings.get("webappTestUrl") or ""
        if not url:
            raise RuntimeError("webappTestUrl not set in local.settings.json")
        qs = urllib.parse.urlencode({"cmd": "teamview", "team": team_id})
        with self._reporter.step("QUERY", "fetch_team_view_html"):
            return extract_html_output(_http_get(f"{url}?{qs}"))

    def tracker_id_urls(self) -> dict:
        """Return {action_id: id_url} for tracker rows that have an ID-column hyperlink."""
        from tests.helpers.download import download_docx
        from scn.surfaces import TrackerReader
        with self._reporter.step("QUERY", "tracker_id_urls"):
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
                      col7 doc_name present, matches the doc's actual current title
                      (GTaskSheet-k1g9), and col10 sync_status not an error state.
                      Does NOT call any GAS route (verify_action_rows/verify_chip_integrity
                      untouched) -- the doc-name-correctness check reads the live Drive
                      title off the doc's edit page (fetch_doc_title, gts-jnsf) rather
                      than the .docx export's core_properties.title, which Google Docs
                      always writes as the literal placeholder "Word Document" and so
                      cannot observe a rename.  Equivalent to an artifact-side
                      verify(on=SHEET) check; placed here for caller ergonomics only.
        """
        if scope == Surface.SHEET:
            from tests.helpers.download import download_xlsx, fetch_doc_title

            xlsx = download_xlsx(self.sheet_id)
            rows = SheetReader().read(xlsx, self.doc_id)
            _SYNC_ERROR_STATES = {"Dirty", "Deleted", "Doc Not Found"}

            current_title = None
            if rows:
                # Only fetch the title (extra request) if there's a row to check the
                # name against -- no rows means nothing to compare.
                current_title = fetch_doc_title(self.doc_id)

            for row in rows:
                # M2-guarded col 7: document_formula must resolve to a doc_id and doc_name
                assert row.doc_name is not None, (
                    f"col7 document_formula missing doc_name for {row.global_id!r}"
                )
                # doc-name-correctness (GTaskSheet-k1g9): the Sheet's cached doc_name
                # must match the document's actual current title -- catches the
                # stale-name-after-rename bug the presence-only check above misses.
                if current_title is not None and row.doc_name != current_title:
                    raise AssertionError(
                        f"col7 document_formula doc_name stale for {row.global_id!r}: "
                        f"expected={current_title!r}, actual={row.doc_name!r}"
                    )
                # M2-guarded col 10: after a clean sync no row should be in an error state.
                # Blank ("") is the normal post-sync value; Dirty/Deleted/Doc Not Found are errors.
                assert row.sync_status not in _SYNC_ERROR_STATES, (
                    f"col10 sync_status {row.sync_status!r} for {row.global_id!r}"
                )
            return {"scope": "SHEET", "rows": len(rows)}
        result = self._post_route("verify_action_rows", {"docId": self.doc_id})
        result_violations = result.get("violations", [])
        if result_violations:
            lines = "\n".join(f"  {v['docId']}: {v['issue']}" for v in result_violations)
            raise AssertionError(f"Action-row violations ({len(result_violations)}):\n{lines}")
        chip = self._post_route("verify_chip_integrity", {"docId": self.doc_id})
        if self._appended_actions > 0:
            assert chip.get("checked_count", 0) > 0, (
                f"verify_chip_integrity scanned 0 AI-N:/ACT-N: paragraphs but "
                f"{self._appended_actions} action(s) were appended this session"
            )
        violations = chip.get("violations", [])
        if violations:
            lines = "\n".join(f"  {v['paragraph']}: {v['issue']}" for v in violations)
            raise AssertionError(f"Chip integrity violations ({len(violations)}):\n{lines}")
        return result

    # ------------------------------------------------------------------
    # Expectation delegation — thin enqueuers (§16.9 / §3.6)
    # ------------------------------------------------------------------

    def _enqueue(self, exp: Expectation) -> None:
        if exp.entry_point and isinstance(self._reporter, NullReporter):
            raise ValueError(
                f"entry_point={exp.entry_point!r} set on a session with no "
                f"request= (ScenarioSession.new_doc(settings, request=request)); "
                f"coverage would be silently dropped."
            )
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
        entry_point: str = "",
    ) -> None:
        """Enqueue an absence expectation (terminal; sheet Sync Status = 'Deleted').

        entry_point (T1/T17): the state-modifying entry point this expectation exercises;
        when set, emits an ep.<entry_point>.<surface> property for entry-point coverage.
        """
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
            entry_point=entry_point,
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

    @contextlib.contextmanager
    def assert_no_addon_error(self, *, timeout_s: float = 10.0):
        """Wrap a sidebar/add-on UI act; fail if it logs a `*.error` entry.

        UI acts (sidebar_sync, insert_tracker_button, sidebar_set_status,
        sidebar_delete) only wait out the busy-spinner — a GAS-side exception
        in the underlying entry point (e.g. addon.sync.error) does not always
        surface as a Playwright failure, since the sidebar may already show
        state from an earlier sync. This polls the GasLogger NDJSON output for
        timeout_s after the wrapped block returns and raises if an error was
        logged. Delegates to the single GAS-error scan (_check_gas_errors); as an
        explicit assertion it always raises, regardless of SCN_FAILFAST.

        No-op if `gasLogDir` is not configured.
        """
        from tests.helpers.gas_log import clear_logs

        log_dir = self.settings.get("gasLogDir")
        fence = clear_logs(log_dir) if log_dir else 0.0
        yield
        if not log_dir:
            return

        import time as _time
        deadline = _time.monotonic() + timeout_s
        while _time.monotonic() < deadline:
            self._check_gas_errors(fence, raise_on_error=True)
            _time.sleep(0.5)

    def mark(self, label: str) -> None:
        """Record an elapsed.{seq}.{label} milestone + a MARK trace event.

        Lightweight sibling of checkpoint()'s elapsed.* property, for timing
        sub-Act boundaries (T24) without the cost or side-effects of a drain.
        Emission routed through the reporter (single owner — R1).
        """
        self._reporter.elapsed(label, junit=True)
        self._reporter.event("MARK", label)

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

        checkpoint_name = f"{kind.value}.{label}" if label else kind.value
        t0 = time.monotonic()
        try:
            warnings, drained_records = self.engine.drain(
                kind,
                label=label,
                on=on,
                read=read,
                read_consistency=read_consistency,
                step_cm=self._reporter.allure_step,
                on_ui_fail=self._attach_ui_failure_screenshot,
            )
        except AssertionError as exc:
            # FAIL-severity miss: record what was being checked before re-raising,
            # so the trace ends on the real check rather than a bare traceback.
            self._reporter.event(
                "CHECK", checkpoint_name, detail=str(exc)[:200],
                result="FAIL", dur_s=time.monotonic() - t0,
            )
            raise

        # Per-surface CHECK events — "what was being checked" (PASS/WARN) — and the
        # JUnit ac.*/ep.* coverage properties, all via the reporter (single path, R1).
        # Format preserved for scripts/check_coverage.py.
        for tag, surface, severity, entry_point in drained_records:
            self._reporter.event(
                "CHECK", checkpoint_name, checking=f"{tag} {surface}",
                surface=surface, result=severity,
            )
            self._reporter.junit(f"ac.{tag}.{surface}", severity)
            # T1/T17 entry-point coverage: emit ep.* only when the expectation tagged
            # an entry point (GTaskSheet-me6w.2).
            if entry_point:
                self._reporter.junit(f"ep.{entry_point}.{surface}", severity)
        self._reporter.elapsed(checkpoint_name, junit=True)
        self._reporter.event(
            "CHECKPOINT", checkpoint_name,
            detail=f"drained={len(drained_records)} warnings={len(warnings)}",
            dur_s=time.monotonic() - t0,
        )
        return warnings


# ---------------------------------------------------------------------------
# Module-level row conversion helper
# ---------------------------------------------------------------------------

def _row_dict_to_ai(row: dict) -> ai:
    """Convert a find_sheet_actions response row (JSON dict) to an ai.

    ContractSchema sheetAction field names → ai field names.
    Dynamic attributes (global_id, assignee_name, sync_status, created_date,
    modified_date) attached post-init.
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
    item.created_date = row.get("created_date") or ""
    item.modified_date = row.get("modified_date") or ""
    return item
