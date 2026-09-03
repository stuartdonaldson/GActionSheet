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


# gts-athl: syncDocument() (src/SyncManager.js) has exactly two early-return
# branches that legitimately never reach the sync.scanned log call -- audited
# 2026-09-01: the doc-not-found-on-open branch (logs sync.docNotFound.invalid)
# and the trashed-doc branch (logs sync.docNotFound.trashed). Both return
# before _scanFloatingActions runs. Every other return in syncDocument()
# (empty-scan sync.complete, the populated-scan path) happens AFTER
# sync.scanned is already logged, so this is the complete set -- a sync that
# hits either of these two tags is not a missing-coverage failure, it is a
# doc that could not be scanned at all this call.
NO_SCAN_TAGS = frozenset({"sync.docNotFound.invalid", "sync.docNotFound.trashed"})


def scan_coverage_problems(
    scanned_count: int | None,
    expected_min: int,
    *,
    no_scan_reason: str | None = None,
) -> list[str]:
    """``scanned_count`` is ``sync.scanned``'s logged ``count``, or ``None``
    when no matching log entry was found for this sync's op id -- itself
    worth surfacing rather than silently passing, UNLESS ``no_scan_reason``
    names one of ``NO_SCAN_TAGS`` (gts-athl): a sync that legitimately took a
    non-scanning branch of syncDocument() (e.g. the doc was already trashed)
    can never produce a sync.scanned entry, so a missing one is not itself a
    coverage gap for that call.

    ``expected_min`` <= 0 means this session has appended nothing verifiable
    yet (mirrors the existing ``_appended_actions > 0`` gate on
    ``verify_chip_integrity``, ``scn/session.py``) -- no claim to check.
    """
    if expected_min <= 0:
        return []
    if scanned_count is None:
        if no_scan_reason in NO_SCAN_TAGS:
            return []
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
    from tests.helpers.gas_log import matches_op, wait_for_log

    problems: list[str] = []

    log_dir = session.settings.get("gasLogDir")
    if log_dir:
        # gts-6pws: a single-shot collect_logs query right after scn.sync()
        # returns races Axiom ingestion lag -- the entry can exist but not
        # yet be queryable. Poll with a short timeout instead (wait_for_log),
        # same fix shape as site 2 below.
        #
        # gts-athl: match sync.scanned OR either NO_SCAN_TAGS entry in the
        # SAME bounded wait -- syncDocument()'s trashed/not-found branches
        # log one of those instead of sync.scanned, and never will (see
        # scan_coverage_problems' docstring), so waiting out the full 15s
        # for a sync.scanned that a legitimate no-scan sync can never
        # produce would just be a slow, pointless timeout on that path.
        try:
            entry = wait_for_log(
                log_dir,
                matches_op(
                    lambda e: e.get("tag") == "sync.scanned" or e.get("tag") in NO_SCAN_TAGS,
                    op_id,
                ),
                timeout_s=15,
                after=fence,
            )
        except TimeoutError:
            entry = None

        if entry is not None and entry.get("tag") in NO_SCAN_TAGS:
            scanned_count = None
            no_scan_reason = entry["tag"]
        else:
            scanned_count = entry["data"].get("count") if entry is not None else None
            no_scan_reason = None
        problems += scan_coverage_problems(scanned_count, expected_min, no_scan_reason=no_scan_reason)

    resp = session._post_route("find_sheet_actions", {"docId": session.doc_id})
    rows = resp.get("rows") or []
    problems += deleted_row_problems(rows, session.doc_id)

    if problems:
        raise AssertionError(
            f"sync coverage guard failed for {session.doc_id}:\n  " + "\n  ".join(problems)
        )
