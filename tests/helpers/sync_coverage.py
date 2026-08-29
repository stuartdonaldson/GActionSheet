"""Per-sync coverage guard (gts-lu13).

The 2026-08-29 failure was visible in the logs (``sync.scanned count:1``
against 21 declared actions) and in the sheet (20 rows marked *Deleted*) and
no lane looked at either. This makes both conditions fail the lane that
produces them, instead of only the ``input == expected`` corpus check that a
scan-nothing sync trivially satisfies.

Pure core (``scan_coverage_problems``/``deleted_row_problems``) is
unit-testable offline, mirroring ``tests.helpers.doc_sheet_agreement``'s
split; ``assert_sync_coverage`` is the live wrapper wired into
``ScenarioSession.sync()``.
"""


def scan_coverage_problems(scanned_count: int | None, expected_min: int) -> list[str]:
    """``scanned_count`` is ``sync.scanned``'s logged ``count``, or ``None``
    when no matching log entry was found for this sync's op id -- itself
    worth surfacing rather than silently passing.

    ``expected_min`` <= 0 means this session has appended nothing verifiable
    yet (mirrors the existing ``_appended_actions > 0`` gate on
    ``verify_chip_integrity``, ``scn/session.py``) -- no claim to check.
    """
    if expected_min <= 0:
        return []
    if scanned_count is None:
        return [
            f"no sync.scanned log entry found for this sync "
            f"(expected count >= {expected_min})"
        ]
    if scanned_count < expected_min:
        return [
            f"sync.scanned count={scanned_count} fewer than {expected_min} "
            f"action(s) this session appended"
        ]
    return []


def deleted_row_problems(rows: list[dict], doc_id: str) -> list[str]:
    """``rows`` is the ``find_sheet_actions`` webapp route's ``rows`` list --
    no doc parse, no .xlsx download; the cheap per-sync guard.
    """
    problems = []
    for r in rows:
        status = str(r.get("sync_status") or r.get("status") or "").strip().lower()
        if status == "deleted":
            gid = r.get("global_id") or r.get("globalId") or "?"
            problems.append(f"{doc_id}: sheet row {gid} marked Deleted")
    return problems


def assert_sync_coverage(session, *, op_id: str, fence: float, expected_min: int) -> None:
    """Live wrapper: one Axiom/file log query (scoped by op_id, gts-obry.1's
    ``matches_op``) plus one ``find_sheet_actions`` HTTP call. No doc parse --
    ``tests.helpers.doc_sheet_agreement.assert_doc_sheet_agreement`` remains
    the heavier, doc-vs-sheet agreement check for lanes that already pull a
    .docx/.xlsx.
    """
    from tests.helpers.gas_log import collect_logs, matches_op

    problems: list[str] = []

    log_dir = session.settings.get("gasLogDir")
    if log_dir:
        entries = collect_logs(
            log_dir,
            matches_op(lambda e: e.get("tag") == "sync.scanned", op_id),
            after=fence,
        )
        scanned_count = entries[-1]["data"].get("count") if entries else None
        problems += scan_coverage_problems(scanned_count, expected_min)

    resp = session._post_route("find_sheet_actions", {"docId": session.doc_id})
    rows = resp.get("rows") or []
    problems += deleted_row_problems(rows, session.doc_id)

    if problems:
        raise AssertionError(
            f"sync coverage guard failed for {session.doc_id}:\n  " + "\n  ".join(problems)
        )
