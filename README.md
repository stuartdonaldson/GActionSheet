# GActionSheet

Workspace Add-on that tracks action items inside Google Docs and aggregates them in a central spreadsheet (the **ActionSheet**) for cross-doc roll-up. Actions are recognized natively as checklist items led by a person chip — no typed prefix syntax — and anchored with named ranges so identity survives edits.

**Status:** Active prototype

---

## How It Works

1. In any Google Doc, type a checklist item that begins with a person chip (`@name`). The chip's email is the assignee.
2. Open the GActionSheet sidebar (Extensions → GActionSheet).
3. Click **Sync now**. The sidebar lists every action in the doc; the ActionSheet receives a row for each, anchored by a named range.
4. Later edits on either authoritative side converge on the next Sync: ActionSheet edits to `Status`, `Action`, or `Assignee` update the floating action paragraph, and doc-side edits update the matching ActionSheet row without leaving duplicate rows behind.
5. Status lives at the end of the line in parentheses, e.g. `(Open)`, `(Closed)`, or any free-form value you prefer. `(Open)` is the default.
6. Click **VerifySync** to compare the doc's floating actions, the in-doc tracker table when present, and the ActionSheet rows for this document. The sidebar shows the verification steps and any mismatches it finds.
7. Click **Insert / refresh tracker** to write a summary table into the doc, prefixed with the sync rules.

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
