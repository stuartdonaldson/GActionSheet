# GActionSheet

Workspace Add-on that tracks action items inside Google Docs and aggregates them in a central spreadsheet (the **ActionSheet**) for cross-doc roll-up. Actions are identified by an in-text `AI-N:` token at the start of each checklist item, followed by a person chip (assignee) and the action text; status is a trailing parenthesized token, e.g., `(Open)`, `(Closed)`. Identity survives edits because the token embeds the durable `AI-N` prefix unique per document.

**Status:** Active prototype

---

## How It Works

1. In any Google Doc, create a checklist item with the pattern: `AI: @name action text (Status)`. The scanner auto-assigns `N` on the next Sync (e.g., `AI-1: @name …`). You may also type just `AI: text` and add the person chip and status later.
2. Open the GActionSheet sidebar (Extensions → GActionSheet) and click **Sync now**. The sidebar lists every action in the doc; the ActionSheet receives a row for each, identified by the `AI-N` token.
3. Edit either the floating action (doc-side) or the ActionSheet row (sheet-side). On the next Sync, changes converge: if the ActionSheet row was edited after the last sync, it wins and updates the doc paragraph; otherwise the doc's state overwrites the sheet row. The `Sync Status` (Dirty) flag decides the winner per row.
4. Status is the trailing parenthesized token, e.g., `(Open)`, `(Closed)`, or any free-form value. If omitted, Sync adds an explicit `(Open)` token.
5. Click **VerifySync** to compare the doc's floating actions, the in-doc tracker table when present, and the ActionSheet rows for this document. The sidebar shows the verification steps and any mismatches it finds.
6. Click **Insert / refresh tracker** to write a summary table into the doc, prefixed with the sync rules. The tracker is a rendered view and is overwritten on each refresh.

A timed sweep on the ActionSheet (every 30 minutes) picks up changes in docs no one opened recently. Closed actions older than 30 days are moved to an archive sheet.

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

Use the repo scripts instead of calling `clasp` directly:

```bash
npm install
npm run push
npm run deploy:test
```

`npm run deploy:test` pushes the Apps Script sources and repoints the TEST web-app deployment to the new revision. `npm run deploy:prod` does the same for production.

### Manual test report
Use this prompt - update for current folder structure:
Report → write pipeline-report.md ONLY (bdreport style):
  1. Headline JOIN: match the run's deployment (target + deploymentId + build) to the latest
     ledger entry; state green/red for the CURRENT deployment and flag if it is still untested.
  2. Run summary: passed/total (%), failures, errors, skipped, wall time.
  3. Per-suite table: tests / pass / fail / err / time.
  4. Failure triage by ROOT-CAUSE bucket (not raw count): Env (add-on/side-panel not installed),
     Harness/config (token/fixture rejected), Perf/timeout (≥ GAS 6-min ceiling), Product
     (logic regression). Classify each failing test.
  5. Deployment ledger: list each deploy as target + deploymentId + version; cadence; current
     deployment; time-since-last-green.
  6. Health flags + recommended next action.
  Parse from: test-results/playwright.xml + test-results/pytest.xml + deployment-ledger/test.jsonl.
  Note if only one run exists (no trend/flaky analysis yet).

### Allure test reporting
Project is defining best practices captured in GAS-Practices for test reporting.
```
npm run test:report
npm run test:server
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
