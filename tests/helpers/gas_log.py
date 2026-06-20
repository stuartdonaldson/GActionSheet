"""Poll for GAS-side structured log entries (NDJSON), backend-agnostically.

Two backends, selected once per process based on local.settings.json:
  - "file":  poll the Drive-mapped GAS log directory (legacy; used when Axiom
             isn't configured).
  - "axiom": query the Axiom dataset GasLogger.js POSTs to (GTaskSheet-ishz.7).
             Selected when axiomDataset+axiomQueryToken are both set.

Every public function below (clear_logs/wait_for_log/assert_log/assert_no_log/
collect_logs) keeps its existing signature regardless of backend -- callers never
need to know or care which one is active. Backend choice is resolved once
(_backend(), cached) rather than re-derived inside each call.
"""
import json
import os
import pathlib
import shutil
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

_SETTINGS_PATH = pathlib.Path(__file__).parent.parent.parent / "local.settings.json"
_settings_cache: dict | None = None
_backend_cache: str | None = None


def _settings() -> dict:
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = json.loads(_SETTINGS_PATH.read_text()) if _SETTINGS_PATH.exists() else {}
    return _settings_cache


def _backend() -> str:
    """Resolved once per process. 'axiom' iff axiomDataset+axiomQueryToken are both set."""
    global _backend_cache
    if _backend_cache is None:
        s = _settings()
        _backend_cache = "axiom" if (s.get("axiomDataset") and s.get("axiomQueryToken")) else "file"
    return _backend_cache


# ---------------------------------------------------------------------------
# Axiom backend
# ---------------------------------------------------------------------------

def _axiom_query(after: float, limit: int = 500) -> list[dict]:
    """Query the configured Axiom dataset for GAS-side entries since `after`
    (epoch seconds). Returns entries reshaped to {ts, tag, version, op,
    parentOp, data} -- the same shape NDJSON entries always had -- so
    match_fn predicates written against file-backend entries work unchanged.
    """
    s = _settings()
    dataset = s["axiomDataset"]
    token = s["axiomQueryToken"]
    start = datetime.fromtimestamp(after, tz=timezone.utc)
    now = datetime.now(timezone.utc)
    apl = f"['{dataset}'] | where side == 'gas' | order by _time asc | limit {limit}"
    body = {
        "apl": apl,
        "startTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endTime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    req = urllib.request.Request(
        "https://api.axiom.co/v1/datasets/_apl?format=legacy",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Axiom query failed ({exc.code}): {exc.read().decode()[:500]}") from exc

    entries = []
    for m in result.get("matches", []):
        data = dict(m.get("data", {}))
        tag = data.pop("name", None)
        entries.append({
            "ts": m.get("_time"),
            "tag": tag,
            "version": data.pop("version", None),
            "op": data.pop("op", None),
            "parentOp": data.pop("parentOp", None),
            "data": {k: v for k, v in data.items() if k != "side"},
        })
    return entries


def _post_axiom_probe(sentinel: str, timeout: int = 30) -> None:
    """POST a sentinel through the real WebApp -> GAS -> GasLogger.flush() ->
    Axiom path (GTaskSheet-ishz.5's axiom_probe route) -- not a Python-direct-
    to-Axiom shortcut, which would skip the GAS/WebApp hop entirely.
    """
    s = _settings()
    url = s.get("webappTestUrl") or ""
    secret = s.get("webappSecret") or ""
    if not url or not secret:
        raise RuntimeError("webappTestUrl/webappSecret required for the Axiom sentinel probe")
    payload = json.dumps({"action": "axiom_probe", "secret": secret, "sentinel": sentinel}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        resp.read()


def _scan_logs_axiom(match_fn, after: float = 0.0):
    for entry in _axiom_query(after):
        if match_fn(entry):
            return entry
    return None


def _wait_for_log_axiom(match_fn, timeout_s: float = 60.0, poll_s: float = 1.0, after: float = 0.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        entry = _scan_logs_axiom(match_fn, after=after)
        if entry:
            return entry
        time.sleep(poll_s)
    raise TimeoutError(f"No matching log entry within {timeout_s}s (axiom backend)")


def _assert_no_log_axiom(fence: float, match_fn, what: str) -> None:
    """Sentinel-watermark absence check: a bare N-second timeout is unsound
    against Axiom's ingest-to-queryable latency (a real, delayed entry could
    be invisible at the timeout and produce a false pass). Instead, POST a
    fresh sentinel right now, wait until IT is observably queryable -- proving
    ingest has caught up to "now" -- then check the suspect tag is absent from
    everything observed up to that point.
    """
    sentinel = str(uuid.uuid4())
    _post_axiom_probe(sentinel)
    is_sentinel = lambda e: e.get("tag") == "test.axiom_probe" and e.get("data", {}).get("sentinel") == sentinel
    try:
        _wait_for_log_axiom(is_sentinel, timeout_s=30.0, poll_s=0.5, after=fence)
    except TimeoutError:
        raise AssertionError(
            f"sentinel-watermark probe never landed in Axiom within 30s -- "
            f"cannot soundly assert absence ({what})"
        )
    bad = [e for e in _axiom_query(fence) if match_fn(e)]
    if bad:
        raise AssertionError(f"unexpected log entry ({what}): {bad[0]}")


def axiom_probe_latency(timeout_s: float = 30.0, poll_s: float = 0.5) -> float:
    """Round-trip seconds from a WebApp axiom_probe POST to the entry being
    queryable in Axiom. Health-check (raises if Axiom is configured but the
    pipe is broken) + calibration number for sizing wait windows elsewhere.
    Call once per test session, not per-assertion.
    """
    if _backend() != "axiom":
        raise RuntimeError("axiom_probe_latency requires axiomDataset/axiomQueryToken in local.settings.json")
    sentinel = str(uuid.uuid4())
    fence = time.time() - 2.0
    t0 = time.monotonic()
    _post_axiom_probe(sentinel)
    is_sentinel = lambda e: e.get("tag") == "test.axiom_probe" and e.get("data", {}).get("sentinel") == sentinel
    _wait_for_log_axiom(is_sentinel, timeout_s=timeout_s, poll_s=poll_s, after=fence)
    return time.monotonic() - t0


# ---------------------------------------------------------------------------
# File backend (legacy -- used when Axiom isn't configured)
# ---------------------------------------------------------------------------

def _clear_logs_file(log_dir: str) -> float:
    fence = time.time() - 10.0
    if not (log_dir and os.path.isdir(log_dir)):
        return fence
    logs = list(pathlib.Path(log_dir).glob("*.log"))
    if not logs:
        return fence
    ts = time.strftime("%Y-%m-%dT%H-%M-%S")
    repo_root = pathlib.Path(__file__).parent.parent.parent
    gas_log_base = os.environ.get("SCN_GAS_LOG_DIR")
    base_dir = pathlib.Path(gas_log_base) if gas_log_base else (repo_root / "test-results" / "gas-logs")
    archive_dir = base_dir / ts
    archive_dir.mkdir(parents=True, exist_ok=True)
    for f in logs:
        shutil.copy2(f, archive_dir / f.name)
        f.unlink()
    return fence


def _scan_logs_file(log_dir: str, match_fn, after: float = 0.0):
    for f in sorted(pathlib.Path(log_dir).glob("*.log")):
        try:
            for line in f.read_text().splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                if after and entry.get("ts"):
                    try:
                        ts_s = datetime.fromisoformat(entry["ts"].replace("Z", "+00:00")).timestamp()
                        if ts_s < after:
                            continue
                    except (ValueError, OSError):
                        pass
                if match_fn(entry):
                    return entry
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _wait_for_log_file(log_dir: str, match_fn, timeout_s: float = 60.0, poll_s: float = 0.5, after: float = 0.0):
    interactive = sys.stdin.isatty()
    while True:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            entry = _scan_logs_file(log_dir, match_fn, after=after)
            if entry:
                return entry
            time.sleep(poll_s)
        if not interactive:
            raise TimeoutError(f"No matching log entry within {timeout_s}s")
        print(f"\n[wait_for_log] No log entry after {timeout_s:.0f}s. "
              "Press Enter to keep waiting, or Ctrl-C to abort.")
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            raise TimeoutError(f"Aborted by user after {timeout_s}s")


def _collect_logs_file(log_dir: str, match_fn, after: float = 0.0) -> list:
    matches = []
    for f in sorted(pathlib.Path(log_dir).glob("*.log")):
        try:
            for line in f.read_text().splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                if after and entry.get("ts"):
                    try:
                        ts_s = datetime.fromisoformat(entry["ts"].replace("Z", "+00:00")).timestamp()
                        if ts_s < after:
                            continue
                    except (ValueError, OSError):
                        pass
                if match_fn(entry):
                    matches.append(entry)
        except (json.JSONDecodeError, OSError):
            pass
    return matches


# ---------------------------------------------------------------------------
# Public API -- backend-agnostic; every call site uses these unchanged.
# ---------------------------------------------------------------------------

def clear_logs(log_dir: str) -> float:
    """Fence epoch-seconds value. Pass to wait_for_log/assert_log/collect_logs
    as `after` to ignore stale entries from a previous or concurrent GAS run.
    """
    if _backend() == "axiom":
        return time.time() - 2.0
    return _clear_logs_file(log_dir)


def wait_for_log(
    log_dir: str,
    match_fn,
    timeout_s: float = 60.0,
    poll_s: float = 0.5,
    after: float = 0.0,
):
    """Block until a log entry matching match_fn is found, or raise TimeoutError."""
    if _backend() == "axiom":
        return _wait_for_log_axiom(match_fn, timeout_s=timeout_s, poll_s=max(poll_s, 1.0), after=after)
    return _wait_for_log_file(log_dir, match_fn, timeout_s=timeout_s, poll_s=poll_s, after=after)


def collect_logs(log_dir: str, match_fn, after: float = 0.0) -> list:
    """Return every log entry matching match_fn (not just the first)."""
    if _backend() == "axiom":
        return [e for e in _axiom_query(after) if match_fn(e)]
    return _collect_logs_file(log_dir, match_fn, after=after)


def assert_log(log_dir: str | None, fence: float, match_fn, what: str) -> None:
    """Assert a matching log entry appears within 60s of `fence`. No-op if
    log_dir is unset (file backend only -- axiom backend ignores log_dir).
    """
    if _backend() == "file" and log_dir is None:
        return
    wait_for_log(log_dir, match_fn, timeout_s=60, after=fence)


def assert_no_log(log_dir: str | None, fence: float, match_fn, what: str) -> None:
    """Assert no matching log entry appears. Axiom backend uses a sentinel-
    watermark (sound against ingest latency); file backend uses an 8s bare
    timeout (sound against the Drive write itself, which is effectively
    synchronous from this process's perspective).
    """
    if _backend() == "axiom":
        _assert_no_log_axiom(fence, match_fn, what)
        return
    if log_dir is None:
        return
    try:
        entry = wait_for_log(log_dir, match_fn, timeout_s=8, after=fence)
    except TimeoutError:
        return
    raise AssertionError(f"unexpected log entry ({what}): {entry}")
