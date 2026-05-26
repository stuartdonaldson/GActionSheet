"""Assertions for parametrized UC scenario matrix tests."""
from tests.helpers.sheet_inspect import load_sheet, find_row, rows_as_dicts, rows_for_doc
from tests.helpers.doc_inspect import load_doc, find_table_row, floating_actions, tracked_actions_table


def assert_scenario(name: str, expectations: dict, xlsx_bytes: bytes, docx_bytes: bytes,
                    test_doc_id: str = "") -> None:
    """Assert all expectations for a scenario against downloaded xlsx and docx bytes.

    All assertion failure messages are prefixed with f"[{name}] " for traceability.
    test_doc_id is used to filter sheet rows to only those belonging to the test doc.
    """
    ws = load_sheet(xlsx_bytes, sheet_name="Actions")
    doc = load_doc(docx_bytes)

    if "expected_floating_actions" in expectations:
        actions = floating_actions(doc)
        for expected in expectations["expected_floating_actions"]:
            matching = [a for a in actions if a["id"] == expected["id"]]
            assert matching, (
                f"[{name}] floating action id={expected['id']} not found. Got: {actions}"
            )
            a = matching[0]
            if "action" in expected:
                assert a["action"] == expected["action"], (
                    f"[{name}] floating action id={expected['id']} action mismatch: "
                    f"expected {expected['action']!r}, got {a['action']!r}"
                )
            if "status" in expected:
                assert a["status"] == expected["status"], (
                    f"[{name}] floating action id={expected['id']} status mismatch: "
                    f"expected {expected['status']!r}, got {a['status']!r}"
                )
            if "assignee_email" in expected:
                assert a["assignee_token"] == expected["assignee_email"], (
                    f"[{name}] floating action id={expected['id']} assignee_email mismatch: "
                    f"expected {expected['assignee_email']!r}, got {a['assignee_token']!r}"
                )
            if "date_created" in expected:
                assert a["date_created"] == expected["date_created"], (
                    f"[{name}] floating action id={expected['id']} date_created mismatch: "
                    f"expected {expected['date_created']!r}, got {a['date_created']!r}"
                )
            if "date_modified" in expected:
                assert a["date_modified"] == expected["date_modified"], (
                    f"[{name}] floating action id={expected['id']} date_modified mismatch: "
                    f"expected {expected['date_modified']!r}, got {a['date_modified']!r}"
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
            if "id_str" in expected:
                assert row["ID"] == expected["id_str"], (
                    f"[{name}] table row ID cell mismatch: "
                    f"expected {expected['id_str']!r}, got {row['ID']!r}"
                )
            if "date_created" in expected:
                assert row["Date Created"] == expected["date_created"], (
                    f"[{name}] table row ID={expected['id']} date_created mismatch: "
                    f"expected {expected['date_created']!r}, got {row['Date Created']!r}"
                )
            if "date_modified" in expected:
                assert row["Date Modified"] == expected["date_modified"], (
                    f"[{name}] table row ID={expected['id']} date_modified mismatch: "
                    f"expected {expected['date_modified']!r}, got {row['Date Modified']!r}"
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

    if "expected_table_row_count" in expectations:
        table_rows = tracked_actions_table(doc) or []
        assert len(table_rows) == expectations["expected_table_row_count"], (
            f"[{name}] tracked-actions table row count mismatch: "
            f"expected {expectations['expected_table_row_count']}, got {len(table_rows)}"
        )

    if "expected_xlsx_active_rows" in expectations:
        active_rows = rows_for_doc(ws, test_doc_id) if test_doc_id else rows_as_dicts(ws)
        active_prefix = expectations.get("active_rows_prefix")
        if active_prefix:
            active_rows = [r for r in active_rows if (r.get("Action") or "").startswith(active_prefix)]
        expected_count = len(expectations["expected_xlsx_active_rows"])
        assert len(active_rows) == expected_count, (
            f"[{name}] active sheet row count mismatch: "
            f"expected {expected_count}, got {len(active_rows)}"
        )

    if "expected_xlsx_archive_rows" in expectations:
        ws_archive = load_sheet(xlsx_bytes, sheet_name="Archive")
        archive_rows = rows_for_doc(ws_archive, test_doc_id) if test_doc_id else rows_as_dicts(ws_archive)
        expected_count = len(expectations["expected_xlsx_archive_rows"])
        assert len(archive_rows) == expected_count, (
            f"[{name}] archive sheet row count mismatch: "
            f"expected {expected_count}, got {len(archive_rows)}"
        )
