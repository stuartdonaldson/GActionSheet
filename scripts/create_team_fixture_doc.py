#!/usr/bin/env python3
"""Create a tracked test document, seeded with action rows, inside a given
Drive folder — for standing up multi-folder team fixtures (e.g. gts-79dw.4.16)
without manual Drive clicks.

Composes existing pieces (scn.session.ScenarioSession + the move_doc_to_folder
and sync_document fixtures) rather than adding a new GAS route:
  1. begin_journey_session -> a guaranteed-clean empty doc (default parent).
  2. move_doc_to_folder    -> relocate it under the target folder.
  3. append_doc_paragraph  -> seed one or more `AI-N:` action rows.
  4. sync_document         -> sync so the row lands in Actions + DocData
                              picks up teamId via the folder-walk auto-assign
                              (SyncManager._walkFolderForTeam) since the doc
                              has no teamScope yet.

Usage:
  python scripts/create_team_fixture_doc.py --folder-id <folderId> \\
      --action "AI-N: Do the thing -- assignee@example.org" \\
      [--action "AI-N: Do another thing"] [--name "TestTeamA fixture doc 1"]

Prints the resulting docId and (after sync) the DocData.teamId it resolved to,
so the caller can confirm the folder-walk assignment worked as expected.
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from scn.session import ScenarioSession, _http_post

_SETTINGS_PATH = pathlib.Path(__file__).parent.parent / "local.settings.json"


def _load_settings() -> dict:
    if not _SETTINGS_PATH.exists():
        raise FileNotFoundError(
            "local.settings.json not found. Copy local.settings.example.json and fill in IDs."
        )
    return json.loads(_SETTINGS_PATH.read_text())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--folder-id", required=True, help="Target Drive folder id")
    parser.add_argument("--action", action="append", dest="actions", default=[],
                         help="AI-N: seed line to append (repeatable)")
    args = parser.parse_args()

    if not args.actions:
        args.actions = ["AI-N: Fixture seeded action -- placeholder@example.org"]

    settings = _load_settings()

    session = ScenarioSession.new_doc(settings)
    doc_id = session.doc_id
    print(f"Created doc: {doc_id}")

    move_resp = _http_post(settings["webappTestUrl"], {
        "action": "run_fixture",
        "testToken": settings.get("testToken") or "",
        "fixture": "move_doc_to_folder",
        "docId": doc_id,
        "folderId": args.folder_id,
    })
    print(f"Moved to folder {args.folder_id}: {move_resp}")

    for text in args.actions:
        session.append_paragraph(text)
        print(f"Appended: {text}")

    session.sync()
    print("Synced.")

    rows_resp = _http_post(settings["webappTestUrl"], {
        "action": "run_fixture",
        "testToken": settings.get("testToken") or "",
        "fixture": "get_docdata_row",
        "fileId": doc_id,
    })
    print(f"DocData row after sync: {json.dumps(rows_resp, indent=2)}")

    print(f"\ndocId={doc_id} folderId={args.folder_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
