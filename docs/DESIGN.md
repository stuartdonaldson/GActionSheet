# DESIGN — GActionSheet

## Solution Strategy
GActionSheet is a single GAS project, container-bound to the ActionSheet spreadsheet, deployed simultaneously as a Workspace Add-on and a Web App. All action-sync logic lives in one codebase; the two deployment modes serve different runtime roles.

- The **Workspace Add-on deployment** provides the sidebar UI in the active document. It scans the doc for chip-led checklist items, anchors each action with a named range (via the Docs REST API `batchUpdate`), and reconciles the doc's actions with rows in the ActionSheet via a `doPost` proxy call to the Web App deployment.
- The **Web App deployment** acts as a proxy endpoint. Because the add-on runs as the active user (who may not have edit access to the ActionSheet), all sheet writes are routed through `doPost`, which runs as the deployer (`executeAs: USER_DEPLOYING`) and has sheet-write authority.
- The **Automation feature set** (timed sweep trigger, `onEdit` timestamp stamper, archive job) is implemented within the same script and activated by installable triggers on the ActionSheet container.

Stable action identity comes from a named range whose `namedRangeId` is recorded on the ActionSheet row. DocumentApp is used for read-side traversal because it exposes PERSON chips ergonomically; the Docs REST API is used for write-side anchoring and tracker-table mutation because it supports named ranges and atomic batch updates.

---

## Deployment Architecture

### Single-script dual-deployment

One GAS project (`scriptId: 12EKX7dQiO1Wf7rvv94Adgpbh3nac0OetsZMTD_1lme3y2o1KLYdKcTXi`) is container-bound to the ActionSheet spreadsheet. It is deployed simultaneously as:

- A **Workspace Add-on** (sidebar card in Docs/Sheets)
- A **Web App** (HTTP endpoint for proxy writes)

Both modes share the same source files. The `rootDir` in `.clasp.json` is `src/`; `appsscript.json` declares both `addOns` and `webapp` sections. Stable deployment IDs are maintained via `clasp deploy -i <id>` so URLs never change across pushes.

### Identity boundary and proxy-write pattern

Workspace Add-ons run as the active user. The ActionSheet is a restricted resource — end users should not have direct edit access. The Web App runs as the deployer (`executeAs: USER_DEPLOYING`), which has sheet-write authority.

```
[Add-on sidebar]
      |
      | UrlFetchApp.fetch(WEBAPP_URL, { method: 'post', payload: JSON })
      v
[doPost — runs as deployer]
      |
      | sheet.appendRow(...)
      v
[ActionSheet]
```

Authentication between add-on and Web App uses a shared secret (`WEBAPP_SECRET` script property). Apps Script Web Apps do not propagate Google identity via Bearer tokens.

### URL stability and org normalization

On northlakeuu.org, `ScriptApp.getService().getUrl()` returns:
`https://script.google.com/a/northlakeuu.org/macros/s/<id>/exec`

This is normalized in `doGet` to the canonical form:
`https://script.google.com/macros/s/<id>/exec`

and stored in the `WEBAPP_URL` script property so a single `urlFetchWhitelist` entry matches. `WEBAPP_URL` is updated automatically on each Web App visit; no manual copy-paste after redeployment.

### Module Map

| File | Role |
|------|------|
| `src/Addon.js` | Card builder, button handlers, UrlFetchApp proxy call |
| `src/WebApp.js` | `doGet` (self-register URL), `doPost` (verify secret, write to sheet) |
| `src/Version.js` | `BUILD_INFO` — stamped by `update-revision.js` before each deploy |
| `src/appsscript.json` | Manifest — addOns, webapp, oauthScopes, urlFetchWhitelist |

### Deployment Pipeline

```
npm run deploy:test
  └─ update-revision.js        → stamps src/Version.js with version + timestamp
  └─ manage-deployments.js     → finds TEST-WEB-APP deployment by anchor string
                                  clasp push (--force if needed)
                                  clasp deploy -i <id> -d "<description>"
                                  writes .deploy-metadata.json
```

Release pipeline (`npm run release:patch`) additionally runs `commit-deploy-stamp.js`, which reads `.deploy-metadata.json` and commits `src/Version.js` with deployment metadata.

### Script Properties

| Property | Set by | Purpose |
|----------|--------|---------|
| `WEBAPP_URL` | `doGet` (auto) | Normalized Web App URL for UrlFetchApp calls |
| `WEBAPP_SECRET` | Manual (script editor) | Shared secret for doPost authentication |
| `GAS_LOGGER_FOLDER_ID` | Manual | Drive folder for GasLogger output (TDD phase) |
| `TEST_DOC_ID` | Manual / `bootstrap()` | Test Google Doc ID for smoke tests |
| `TEST_SHEET_ID` | Manual / `bootstrap()` | Test Sheet ID for smoke tests |

### urlFetchWhitelist

Required in `appsscript.json` for any Workspace Add-on that calls `UrlFetchApp`. Three entries cover all URL format variants produced by northlakeuu.org:

```json
"urlFetchWhitelist": [
  "https://script.google.com/a/macros/northlakeuu.org/s/",
  "https://script.google.com/a/northlakeuu.org/macros/s/",
  "https://script.google.com/macros/s/"
]
```

Omitting `urlFetchWhitelist` produces a hard error at call time, not a manifest validation error.

### Deployment Constraints

- Web App access must be **"Anyone"** (not "Anyone within org") — org SSO enforces authentication on `UrlFetchApp` requests regardless of headers when set to org-restricted
- Web App `executeAs` must be **"USER_DEPLOYING"** to have sheet-write authority
- `urlFetchWhitelist` is mandatory for any UrlFetchApp call from a Workspace Add-on

---

## Runtime Architecture

```mermaid
graph LR
    subgraph AddOn["Add-on project (standalone, Workspace Add-on for Docs)"]
        Sidebar["Sidebar UI<br/>(HTML service)"]
        Scanner["Action Scanner<br/>(DocumentApp + REST namedRanges)"]
        NRM["Named Range Manager<br/>(REST batchUpdate)"]
        Tracker["Tracker Table Renderer<br/>(REST batchUpdate)"]
        DocSync["ActionSheet Sync<br/>(per-doc push/pull)"]
        WebApp["Web App<br/>(doPost proxy — runs as deployer)"]

        Sidebar --> Scanner
        Sidebar --> Tracker
        Sidebar --> DocSync
        Scanner --> NRM
        DocSync --> Scanner
        DocSync --> WebApp
    end

    subgraph Automation["Automation project (container-bound to ActionSheet)"]
        OnEdit["onEdit Handler<br/>(stamp Last Modified)"]
        Sweep["Sweep Trigger<br/>(time-based reconcile)"]
        Archive["Archive Manager<br/>(Closed + 30d)"]
        Guard["Write Guard<br/>(SYNC_IN_PROGRESS flag)"]

        Sweep --> Guard
        Archive --> Guard
        OnEdit -. reads .-> Guard
    end

    Doc[(Active Google Doc)]
    ActionSheet[(ActionSheet)]
    ArchiveSheet[(Archive Sheet)]
    OtherDocs[(Other Google Docs<br/>referenced by ActionSheet rows)]

    Scanner --> Doc
    NRM --> Doc
    Tracker --> Doc
    WebApp --> ActionSheet
    Sweep --> ActionSheet
    Sweep --> OtherDocs
    Archive --> ActionSheet
    Archive --> ArchiveSheet
    OnEdit --> ActionSheet
```

The two subgraphs share no arrow; communication is solely through `ActionSheet` rows.

---

## Building Block View

### Add-on project

| Component | Responsibility |
|-----------|---------------|
| Sidebar UI | Renders the action list for the active doc; surfaces **Sync now**, **VerifySync**, **Insert / refresh tracker**, warning rows, and orphan-anchor prompts |
| Action Scanner | Reads the active doc via DocumentApp: walks paragraphs and list items, identifies floating actions by two rules — (1) first inline child is a PERSON chip, or (2) first text content begins with a valid email address (`word@word.tld`); extracts assignee email/name, action text, and trailing `(Status)` token; reads existing named ranges via the REST API to resolve identity |
| Named Range Manager | Creates a named range over a newly seen action paragraph; deletes a range when its action is no longer present; re-anchors when an existing row's range is missing but its action+assignee still match a paragraph |
| Tracker Table Renderer | Inserts or refreshes the in-doc tracker table at its own named-range anchor, preceded by the instructional paragraph summarizing the sync rules; uses REST `batchUpdate` for atomic in-place replacement |
| ActionSheet Sync | Reads ActionSheet rows for the active doc, compares with scanner output by `namedRangeId`, applies `Last Modified` precedence, writes diffs to either side; sets the automation project's `SYNC_IN_PROGRESS` script property on the ActionSheet before sheet writes |
| VerifySync | Reads floating actions from the doc, reads ActionSheet rows for the same doc through a non-mutating Web App call, parses the in-doc tracker table when present, and reports progress plus mismatches in the sidebar result card; a floating action without an explicit trailing status token is itself a verification failure |

### Automation project

| Component | Responsibility |
|-----------|---------------|
| onEdit Handler | Installable trigger on the ActionSheet; stamps `Last Modified` on the edited row unless `SYNC_IN_PROGRESS` is set |
| Sweep Trigger | Time-based; groups ActionSheet rows by document URL, opens each doc, performs the same reconcile the sidebar's **Sync now** would have done; bounded by GAS execution-time budget; subsequent runs resume where the previous left off |
| Archive Manager | Identifies ActionSheet rows with `Status = Closed` and `Last Modified > 30 days`; moves them to the archive sheet without altering timestamps |
| Write Guard | Manages the `SYNC_IN_PROGRESS` flag (a script property on the ActionSheet's container script); set before any programmatic sheet write, cleared in `finally`; read by `onEdit Handler` to skip stamp updates during automated writes |

---

## Data Model

```mermaid
erDiagram
    Action {
        string  namedRangeId
        int     id
        string  assigneeEmail
        string  assigneeName
        string  actionText
        string  status
        string  assignedDate
        string  lastModified
        string  documentUrl
        string  documentTitle
    }
    ActionSheetRow {
        string  namedRangeId
        int     id
        string  assigneeEmail
        string  assigneeName
        string  actionText
        string  status
        string  documentTitle
        string  documentUrl
        string  assignedDate
        string  lastModified
    }
    DocChecklistItem {
        string  namedRangeId
        int     paragraphIndex
        string  assigneeChip
        string  actionText
        string  status
    }
    TrackerTableRow {
        int     id
        string  assigneeChip
        string  actionText
        string  status
        string  assignedDate
        string  lastModified
    }

    Action ||--|| ActionSheetRow : "stored as"
    Action ||--|| DocChecklistItem : "anchored in"
    Action ||--o| TrackerTableRow : "summarised by"
```

The cross-doc key is `namedRangeId`. The doc-scoped `id` is a human-facing integer recomputed at sync time from document order; it is not a stable identifier.

**Field notes:**
- `assigneeChip` — compound value extracted from the PERSON chip, canonical form `name <email>`. The ActionSheet stores this in two separate columns (`Assignee Name`, `Assignee Email`); `DocChecklistItem` and `TrackerTableRow` hold it as a single parsed unit.
- `documentTitle` / `documentUrl` — the ActionSheet renders these as a single hyperlink cell (display text = `documentTitle`, URL = `documentUrl`). Modelled separately here to mirror `Action` and make the hyperlink structure explicit.

---

## Dependency Rules
- Add-on Scanner reads docs only; it never touches the ActionSheet directly — the Sync component owns sheet I/O
- Sidebar UI never imports another component's internals; it calls a thin façade in the add-on script that fans out to Scanner / NRM / Tracker / Sync
- Automation Sweep performs the same reconciliation as Sidebar Sync but uses its own script identity; the two share no code (the schema is the contract)
- Archive Manager reads from and writes to the ActionSheet only; it does not open documents
- No cross-project calls between add-on and automation

---

## Crosscutting Concepts

### Authoritative surfaces
An action exists on **three** surfaces, but only **two** are authoritative:

| Surface | Role | Edits propagate? |
|---|---|---|
| Floating action paragraph (chip + text + trailing `(Status)`) in the doc | Doc-side authority | Yes — propagated to ActionSheet on Sync |
| ActionSheet row | Cross-doc authority | Yes — propagated to floating action on Sync |
| In-doc tracker table row | Rendered view of the doc's actions | **No** — overwritten on next **Insert / refresh tracker** |

Conflict resolution applies only between the two authoritative surfaces using `Last Modified`. The renderer does not read tracker-table cell contents to decide anything; it always re-renders from the floating actions and ActionSheet row pair.

### Identity
`namedRangeId` is the durable identity. The ActionSheet stores it on every row. During scan, the add-on resolves each chip-led checklist paragraph to a `namedRangeId` by intersecting paragraph indices with the doc's existing named ranges. A paragraph with no covering named range becomes a new action; a named range whose covered paragraph is no longer chip-led becomes a candidate orphan and is offered for re-anchoring (if a paragraph with matching action text and assignee still exists) or surfaced in the sidebar for human resolution.

### Checked state is unreadable
DocumentApp returns `null` for `isChecked()` on every task / checklist item, and the REST API exposes no equivalent field. The visual checkbox is **decorative only**. The truthful status is the trailing `(Status)` parenthesized token on the action paragraph. Components must never branch on visual checked state.

### Status token grammar
A trailing parenthesized token at the end of the action paragraph. If the paragraph omits the token, Sync rewrites the floating action with an explicit `(Open)` token. `Closed` is recognized for archiving. Any other value (e.g. `(In Review)`, `(Blocked)`) is preserved verbatim and round-trips to the ActionSheet `Status` column. Whitespace inside the parens is trimmed on read; the canonical written form has no leading/trailing whitespace.

### Programmatic Write Suppression
Both the add-on's per-doc Sync and the automation's Sweep / Archive set the automation project's `SYNC_IN_PROGRESS` script property on the ActionSheet before any programmatic sheet write, and clear it in a `finally` block. The `onEdit Handler` reads this flag and returns immediately when set, preventing false `Last Modified` updates from automated writes.

### Idempotence
A Sync or Sweep that finds no differences shall make no writes to any doc or sheet. Enforced by comparing normalized values before writing.

---

## Test Model

### Framework

| Item | Value |
|---|---|
| Framework | `pytest` + `python-docx` + `openpyxl` + Playwright (Node.js) |
| Run command | `uv run pytest tests/ -x -v` |
| Trigger mechanism for end-to-end tests | Playwright drives the sidebar in a live Doc (sidebar UI clicks **Sync now** / **Insert / refresh tracker**); for sweep / archive tests, Playwright runs the automation script's functions from the Apps Script editor |
| Declared methodology | `atdd-bdd` (end-to-end first; atomic tests support root-cause isolation) |

### Fixture Scope Architecture

| Scope | Established once per | What it provides |
|---|---|---|
| **Session** | Test run | Authenticated Playwright browser session (`.auth/user.json`); `local.settings.json` loaded (test doc ID, test ActionSheet ID, add-on script ID, automation script ID, log dir) |
| **Suite** | Use-case group | Known doc and ActionSheet state reset via a `setupTestFixtures()` function in the add-on project |
| **Workflow** | Individual UC scenario | Specific chip-led checklist items inserted and/or ActionSheet rows seeded to the exact precondition state |
| **Function** | Individual assertion | Fresh `.xlsx` snapshot of the ActionSheet and `.docx` snapshot of the doc after the user action completes |

### End-to-End Scenarios

Each Use Case has **one** end-to-end test that asserts the user-visible outcome only (sidebar contents + downloaded `.docx` + downloaded `.xlsx`):

| UC | What the test does | What it asserts |
|---|---|---|
| **UC-A** | Insert a chip-led list item AND an email-led list item in the same doc, click Sync, then click Sync again with no changes | Both items appear in ActionSheet with correct email, name, action text, and status (AC1); second Sync produces no new rows, all `NamedRangeId` values unchanged, sheet and doc content byte-for-byte identical (AC2) |
| **UC-B** | Four flows: (1) edit the sheet row's Status/Action/Assignee, then Sync; (2) edit the floating action's trailing `(Status)`, then Sync; (3) edit the floating action's text after the chip, then Sync; (4) replace the chip with a different person, then Sync. Plus a negative case (5): type into the tracker table cell, then Sync | (1)–(4) the *other* authoritative side reflects the edit, no duplicate ActionSheet row, named-range anchor preserved across all four; (5) the ActionSheet is unchanged and the next tracker refresh restores the rendered values |
| **UC-C** | Click **Insert / refresh tracker** twice, with intervening action changes; include a refresh after a tracker-cell edit | First click produces instructional paragraph + N-row table; second click reflects added/removed/closed actions in place; no stale rows remain; tracker-cell edits are overwritten on refresh |
| **UC-D** | Seed a Closed row with `Last Modified > 30d`, invoke the sweep | The row appears in the archive sheet with `Last Modified` preserved; no doc content changed |

### Atomic Tests

Atomic tests run with `-x` fail-fast and are owned per concern. They isolate root causes that would otherwise cascade through the slow end-to-end suite:

| Category | Example |
|---|---|
| Chip extraction | A PERSON chip as the first inline child resolves to `(email, name)`; a paragraph without a chip is correctly rejected |
| Status token parsing | `... (Open)`, `... (In Review)`, `...   (  Closed  )`, missing token, multiple parens — all parse to the right `(status, actionText)` pair |
| Named range survival | After an edit inserts text above an anchored action, the named range still covers the same paragraph and resolves to the same `namedRangeId` |
| Free-form status preservation | `(In Review)` round-trips through Sync without normalization to `Open` or `Closed` |
| Re-anchor logic | An orphan ActionSheet row matches an unanchored chip-led paragraph by `(assigneeEmail, actionText)` and re-anchors instead of duplicating |
| Write Guard | A programmatic ActionSheet write performed with `SYNC_IN_PROGRESS` set does not bump `Last Modified` |

### Anti-Patterns

- **Branch on visual checked state.** It is not readable; tests must never assert on `isChecked()` and code must never call it as a source of truth.
- **Assert on execution log alone.** The log proves the script ran; the `.docx` / `.xlsx` / sidebar contents prove the output is correct. Both are required for UC verification.
- **Hard-code IDs in tests.** All IDs come from `local.settings.json`; no IDs in committed test code.
- **Re-authenticate per test.** Auth state is expensive; establish once per session via `.auth/user.json`.
- **Skip the atomic tier before running E2E.** A root-cause failure in chip extraction will fail every UC; fix atomic tests first, then run E2E.

---

## References
| Document | Location | Covers |
|----------|----------|--------|
| Original requirements (archived) | /knowledge-base/references/requirements-original-2026.md | Full functional specification for the prior `AI-` prefix / container-bound-on-Sheet design (superseded) |
| Google Docs / Tasks API findings | /home/stuar/roots/g-Proj/GDocTools/DocsAPI/DOCS_API_FINDINGS.md | API capability matrix and architectural options that drove this design |
| GAS best practices | /mnt/c/dev/GAS-Practices/best-practices/ | Deployment, xlsx download, server logging, editor-testing patterns |
