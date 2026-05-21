# GActionSheet

Bidirectional sync of action items between a Google Sheet hub and multiple Google Docs, driven by a lightweight inline text syntax and a container-bound Google Apps Script.

**Status:** Design

---

## Getting Started

### Prerequisites

- Google account with edit access to the target Spreadsheet and all source Docs
- [clasp](https://github.com/google/clasp) CLI (`npm install -g @google/clasp`)
- Node.js (for clasp)

### Setup

```bash
clasp login
clasp clone <scriptId>        # or clasp create if starting fresh
```

### First run

1. Open the bound Spreadsheet in Google Sheets.
2. Run `initializeTriggers` from the Apps Script editor (one-time setup).
3. Confirm the `Action Sync` menu appears in the sheet.

See [OPERATIONS.md](docs/OPERATIONS.md) for configuration options and the `DOC_FOLDER_ID` property.

---

## Documentation

| Document | Purpose |
|----------|---------|
| [CONTEXT.md](docs/CONTEXT.md) | Purpose, capabilities, use cases, glossary |
| [DESIGN.md](docs/DESIGN.md) | Architecture, modules, data model |
| [OPERATIONS.md](docs/OPERATIONS.md) | Configuration, deployment, failure modes |
| [ADRs](knowledge-base/adr/) | Architecture decision records |

---

## License

MIT — see [LICENSE](LICENSE) for details.
