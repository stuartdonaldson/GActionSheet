# ADR-0001: Container-Bound GAS on the Spreadsheet

Status: Superseded by ADR-0005
Date: 2026-05-19

## Context
The system needs a runtime that has native access to a Google Spreadsheet (the hub) and can also open arbitrary Google Docs (the sources). Options were: (a) container-bound script on the Sheet, (b) container-bound script on each Doc, (c) standalone GAS project.

## Decision
Use a single container-bound Google Apps Script attached to the tracking Spreadsheet.

## Consequences
- Direct `SpreadsheetApp` access without OAuth round-trips; Sheet is the natural authoritative hub.
- `DocumentApp.openById()` provides Doc access under the authorizing user's identity; no separate credential management.
- Simple `onEdit` trigger cannot call external services — the sheet-update trigger must be an installable trigger installed by `initializeTriggers`.
- 6-minute GAS execution limit applies per run; syncing large document sets may require batching or continuation tokens in future.
- No Doc-side triggers needed, avoiding the complexity of managing triggers across an unbounded number of documents.
