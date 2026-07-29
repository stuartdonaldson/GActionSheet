#!/usr/bin/env python3
"""repro_tracker_stale.py — gts-m2gf repro.

Builds a throwaway journey document with the structure the defect needs — nested
bulleted list items carrying AI-N floating actions, plus an Action Item Summary
tracker table — then edits an action's text in the SPREADSHEET, syncs, and
compares the floating action against its tracker cell.

Defect: the sheet edit reaches the floating action but the tracker row stays stale.

    python scripts/repro_tracker_stale.py            # build, prove, trash the doc
    python scripts/repro_tracker_stale.py --keep     # leave the doc for inspection
"""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from call_webapp import call_action  # noqa: E402

NEW_TEXT = "REWRITTEN FROM SHEET — tracker must show this"


def fixture(name, doc_id, **data):
    return call_action("run_fixture", {"fixture": name, "testDocId": doc_id, **data})


def dump(doc_id):
    return call_action("dump_doc_paragraphs", {"docId": doc_id}).get("elements", [])


def show(elements, label):
    print(f"\n--- {label}")
    for e in elements:
        text = e["text"].replace("\n", "\\n").replace("\v", "\\v")
        if not text.strip():
            continue
        kind = "LIST" if e["isListItem"] else "PARA"
        print(f"  {str(e['i']):>12} {kind} [{e['start']:5},{e['end']:5}) {text[:88]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="do not trash the doc at the end")
    ap.add_argument("--also-sync", action="store_true",
                    help="run a sync_document after the cell edit, to test whether a later sync repairs it")
    args = ap.parse_args()

    session = call_action("begin_journey_session", {})
    doc_id = session["docId"]
    print(f"Repro doc: {session['docName']}\n  {session['docUrl']}")

    try:
        # Structure mirroring the reported document: a parent bullet, an AI action
        # nested under it, a sibling bullet, and a second AI action — so the tracker
        # has more than one row and the edited row is not the only candidate.
        fixture("append_doc_list_item", doc_id, text="Board retreat planning")
        fixture("append_doc_list_item", doc_id, text="AI: Finalize board retreat date")
        fixture("append_doc_list_item", doc_id, text="Town hall meetings - reserved for Transition Team")
        fixture("append_doc_list_item", doc_id, text="AI: Put board meeting on calendar")

        # First sync assigns AI-N tokens and creates the sheet rows.
        fixture("sync_document", doc_id)
        # Tracker must already exist: syncDocument refreshes with onlyIfExists=true.
        fixture("insert_tracker_table", doc_id)

        rows = call_action("find_sheet_actions", {"docId": doc_id}).get("rows", [])
        if not rows:
            print("ABORT: no sheet rows were created", file=sys.stderr)
            return 1
        target = rows[0]
        gid = target["global_id"]
        print(f"\nEditing {gid}\n  from: {target['action_text']!r}\n  to:   {NEW_TEXT!r}")

        show(dump(doc_id), "BEFORE the sheet edit")

        # The act under test: a real spreadsheet cell edit. This drives
        # onActionSheetEdit -> _syncSheetRowToDoc, the path an actual user edit
        # takes — NOT edit_action_row + sync_document, which reaches the tracker
        # refresh through a different route and masks the defect.
        print(fixture("edit_cell_via_trigger", doc_id,
                      globalId=gid, field="action_text", value=NEW_TEXT))
        if args.also_sync:
            fixture("sync_document", doc_id)

        after = dump(doc_id)
        show(after, "AFTER sheet edit + sync")

        ai_n = gid.split("/")[-1]
        floating = [e for e in after if e["text"].startswith(f"{ai_n}:")]
        # Tracker cells live inside the summary table; the action cell is the one
        # holding the action text, keyed by the row whose first cell is the AI-N id.
        tracker = [e for e in after if NEW_TEXT in e["text"] and not e["text"].startswith(f"{ai_n}:")]
        stale = [e for e in after
                 if e["text"].strip() == target["action_text"].strip()
                 and not e["text"].startswith(f"{ai_n}:")]

        print("\n=== VERDICT")
        got_floating = any(NEW_TEXT in e["text"] for e in floating)
        print(f"  floating action updated : {got_floating}")
        print(f"  tracker cell updated    : {bool(tracker)}")
        if stale:
            print(f"  STALE tracker cell(s)   : {[e['i'] for e in stale]} -> {stale[0]['text']!r}")
        if got_floating and not tracker:
            print("\n  REPRODUCED (gts-m2gf): floating action carries the new text, "
                  "tracker table does not.")
            return 0
        if got_floating and tracker:
            print("\n  NOT reproduced: both surfaces updated.")
            return 2
        print("\n  INCONCLUSIVE: the floating action itself did not update.")
        return 3
    finally:
        if args.keep:
            print(f"\nLeaving doc in place: {doc_id}")
        else:
            call_action("end_journey_session", {"docId": doc_id})
            print(f"\nTrashed repro doc {doc_id}")


if __name__ == "__main__":
    sys.exit(main())
