# GActionSheet

Workspace Add-on that tracks action items inside Google Docs and aggregates them in a central spreadsheet (the **ActionSheet**) for cross-doc roll-up. Actions are recognized natively as checklist items led by a person chip — no typed prefix syntax — and anchored with named ranges so identity survives edits.

**Status:** Design

---

## How It Works

1. In any Google Doc, type a checklist item that begins with a person chip (`@name`). The chip's email is the assignee.
2. Open the GActionSheet sidebar (Extensions → GActionSheet).
3. Click **Sync now**. The sidebar lists every action in the doc; the ActionSheet receives a row for each, anchored by a named range.
4. Status lives at the end of the line in parentheses, e.g. `(Open)`, `(Closed)`, or any free-form value you prefer. `(Open)` is the default.
5. Click **Insert / refresh tracker** to write a summary table into the doc, prefixed with the sync rules.

A timed sweep on the ActionSheet picks up changes in docs no one opened recently. Closed actions older than 30 days are moved to an archive sheet.

---

## Getting Started

### Prerequisites

- Google account with edit access to the ActionSheet and the source Docs
- [clasp](https://github.com/google/clasp) CLI (`npm install -g @google/clasp`)
- A GCP project with the **Google Docs API** enabled (required for named ranges and tracker-table writes via REST `batchUpdate`)

### Setup

Two Apps Script projects are deployed independently:

| Project | Type | Purpose |
|---|---|---|
| **GActionSheet Add-on** | Standalone script with Workspace Add-on manifest (Docs) | Sidebar UI, per-doc Sync, named ranges, tracker-table render |
| **ActionSheet Automation** | Container-bound script on the ActionSheet spreadsheet | `onEdit` timestamp stamping, timed sweep, archiving |

```bash
clasp login
# Add-on project
cd src/addon && clasp clone <addonScriptId> && clasp push
# Automation project
cd ../automation && clasp clone <automationScriptId> && clasp push
```

### First run

1. From the Apps Script editor for the add-on, deploy as a **test deployment** (Deploy → Test deployments → Install). Open any Doc; the sidebar appears under Extensions → GActionSheet.
2. From the Apps Script editor for the automation script, run `initializeTriggers` once to install the `onEdit` and time-based triggers on the ActionSheet.

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for configuration details.

---

## Documentation

| Document | Purpose |
|----------|---------|
| [CONTEXT.md](docs/CONTEXT.md) | Purpose, capabilities, use cases, glossary |
| [DESIGN.md](docs/DESIGN.md) | Architecture, modules, data model |
| [OPERATIONS.md](docs/OPERATIONS.md) | Configuration, deployment, failure modes |
| [ADRs](knowledge-base/adr/) | Architecture decision records |
| [Worpspace-Setup](knowledge-base/references/workspace-addon-setup.md) | Research results on Google Workspace AddOn setup, configuration and testing |

---

## License

MIT — see [LICENSE](LICENSE) for details.
