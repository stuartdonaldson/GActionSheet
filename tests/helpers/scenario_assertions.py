"""Assertions for parametrized UC scenario matrix tests."""
from tests.helpers.sheet_inspect import load_sheet, find_row, rows_as_dicts
from tests.helpers.doc_inspect import load_doc, find_table_row, floating_actions


def assert_scenario(name: str, expectations: dict, xlsx_bytes: bytes, docx_bytes: bytes) -> None:
    """Assert all expectations for a scenario against downloaded xlsx and docx bytes.

    All assertion failure messages are prefixed with f"[{name}] " for traceability.
    """
    ws = load_sheet(xlsx_bytes, sheet_name="Actions")
    doc = load_doc(docx_bytes)

    if "expected_floating_actions" in expectations:
        actions = floating_actions(doc)
        for expected in expectations["expected_floating_actions"]:
            matching = [a for a in actions if a["id"] == expected["id"]]
            assert matching, (
                f"[{name}] floating action AI-{expected['id']} not found. Got: {actions}"
            )
            a = matching[0]
            if "action" in expected:
                assert a["action"] == expected["action"], (
                    f"[{name}] floating action AI-{expected['id']} action mismatch: "
                    f"expected {expected['action']!r}, got {a['action']!r}"
                )
            if "status" in expected:
                assert a["status"] == expected["status"], (
                    f"[{name}] floating action AI-{expected['id']} status mismatch: "
                    f"expected {expected['status']!r}, got {a['status']!r}"
                )

    if "expected_table_rows" in expectations:
        for expected in expectations["expected_table_rows"]:
            row = find_table_row(doc, action_id=expected["id"])
            assert row is not None, (
                f"[{name}] tracked-actions table row with ID={expected['id']} not found"
            )
            if "action" in expected:
                assert row["Action"] == expected["action"], (
                    f"[{name}] table row ID={expected['id']} action mismatch: "
                    f"expected {expected['action']!r}, got {row['Action']!r}"
                )
            if "status" in expected:
                assert row["Status"] == expected["status"], (
                    f"[{name}] table row ID={expected['id']} status mismatch: "
                    f"expected {expected['status']!r}, got {row['Status']!r}"
                )

    if "expected_sheet_rows" in expectations:
        for expected in expectations["expected_sheet_rows"]:
            doc_url_contains = expected.get("doc_url_contains", "docs.google.com")
            row = find_row(ws, doc_url=doc_url_contains, action_id=expected["id"])
            assert row is not None, (
                f"[{name}] sheet row with ID={expected['id']} and URL containing "
                f"{doc_url_contains!r} not found"
            )
            if "action" in expected:
                assert row["Action"] == expected["action"], (
                    f"[{name}] sheet row ID={expected['id']} action mismatch: "
                    f"expected {expected['action']!r}, got {row['Action']!r}"
                )
            if "status" in expected:
                assert row["Status"] == expected["status"], (
                    f"[{name}] sheet row ID={expected['id']} status mismatch: "
                    f"expected {expected['status']!r}, got {row['Status']!r}"
                )

    if "expected_xlsx_active_rows" in expectations:
        active_rows = rows_as_dicts(ws)
        expected_count = len(expectations["expected_xlsx_active_rows"])
        assert len(active_rows) == expected_count, (
            f"[{name}] active sheet row count mismatch: "
            f"expected {expected_count}, got {len(active_rows)}"
        )

    if "expected_xlsx_archive_rows" in expectations:
        ws_archive = load_sheet(xlsx_bytes, sheet_name="Archive")
        archive_rows = rows_as_dicts(ws_archive)
        expected_count = len(expectations["expected_xlsx_archive_rows"])
        assert len(archive_rows) == expected_count, (
            f"[{name}] archive sheet row count mismatch: "
            f"expected {expected_count}, got {len(archive_rows)}"
        )
