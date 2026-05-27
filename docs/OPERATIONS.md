# OPERATIONS — GActionSheet

## Deployment

### Model
Container-bound Google Apps Script attached to the tracking Google Spreadsheet. No server infrastructure. The script runs within the Google Workspace execution environment under the authorizing user's identity.

### Development Environment

**Setup:**
```bash
npm install -g @google/clasp
clasp login
```

**Clone existing script:**
```bash
clasp clone <scriptId>
```

**Create new bound script (if starting from scratch):**
1. Open the target Spreadsheet in Google Sheets
2. Extensions → Apps Script — this creates a bound script
3. Note the script ID from the URL
4. `clasp clone <scriptId>`

**Verify:**
```bash
clasp status
```

### Static Assets (GitHub Pages)

Logo and other static assets are served from GitHub Pages. The repository must be public and
Pages must be enabled once:

1. GitHub repo → Settings → Pages
2. Source: Deploy from a branch
3. Branch: master, folder: / (root)
4. Save — the site publishes at `https://stuartdonaldson.github.io/GActionSheet/`

Asset URL pattern: `https://stuartdonaldson.github.io/GActionSheet/assets/<filename>`

The `.nojekyll` file at the repo root suppresses Jekyll processing so PNG files are served
without path rewriting.

### Installation
```bash
clasp push          # push source to Apps Script
```

Then, in the Apps Script editor or via the Sheet menu after first push, run `initializeTriggers` once to install the time-based and `onEdit` triggers.

### Environment Variables

Script properties (set via Apps Script editor → Project Settings → Script Properties, or set programmatically by `initializeTriggers`):

| Property | Required | Default | Description |
|----------|----------|---------|-------------|
| `DOC_FOLDER_ID` | Yes | Auto-set on first `initializeTriggers` call | Drive folder ID or URL that roots document discovery. Defaults to the parent folder of the Spreadsheet. |
| `SYNC_IN_PROGRESS` | Internal | `false` | Guard flag set during programmatic sheet writes to suppress the `onEdit` trigger. Do not set manually. |

---

## Configuration

### Key Options
| Option | Values | Default | Effect |
|--------|--------|---------|--------|
| `DOC_FOLDER_ID` | Drive folder ID or full URL | Parent folder of the Spreadsheet | Roots the document discovery search |
| Scan interval | Set in trigger definition | 30 minutes | How often the timed sync runs |
| Archive threshold | Hardcoded | 30 days | Days since last modification before a `Closed` record is archived |
| Discovery window | Hardcoded | 7 days | Documents not modified in the last 7 days are excluded from each sync run |

---

## Running

The script runs automatically via installed triggers. Manual execution:

1. Open the tracking Spreadsheet
2. `Action Sync` menu → `Sync` — runs a full sync across all discovered documents immediately

In the Google Docs homepage card for an active document:
- **Scan card** — refreshes the card from current doc, tracker, and sheet summary state without writing changes
- **Sync now** — reconciles the doc's floating actions with the ActionSheet
- **VerifySync** — performs a read-only comparison of floating actions, tracker rows when present, and ActionSheet rows for the same doc; the verification card lists progress and mismatches
- **Insert / refresh tracker** — inserts or refreshes the in-doc tracker table
- **Sort** / **Filter** — reorder or narrow the rendered action list without changing the underlying document or sheet data

To re-initialize triggers after a project clone or script re-creation:

```
Apps Script editor → Run → initializeTriggers
```

---

## Monitoring

### Log Location
Apps Script execution logs: Apps Script editor → Executions (left sidebar). Each sync run logs start/end, documents processed, rows created/updated, and any errors.

### Health Indicators
- No ERROR entries in the execution log = healthy
- `Action Sync` menu present in the Spreadsheet = triggers initialized
- Archive sheet tab exists = archiving has run at least once

---

## Failure Modes

| Failure | Symptom | Recovery |
|---------|---------|---------|
| `DOC_FOLDER_ID` not set | `initializeTriggers` logs "DOC_FOLDER_ID not set, defaulting to spreadsheet parent folder" | Verify the script property after first run; override if needed |
| Tracked-actions section missing in a Doc | Sync skips that document with a logged error | Add `=== Tracked Actions ===` heading and a table to the document |
| Duplicate tracked-actions section in a Doc | Sync fails for that document with a logged error | Remove the duplicate section from the document |
| Duplicate `ID` in tracked-actions table | Sync fails for that document with a logged error | Manually deduplicate rows in the document table |
| GAS execution timeout (> 6 min) | Execution log shows `Exceeded maximum execution time` | Reduce folder scope via `DOC_FOLDER_ID`, or run sync manually on smaller document sets |
| Missing required sheet header | Sync fails with a logged error listing the missing column | Add the missing header to the tracking sheet or archive sheet |
| Permission denied on a Doc | Sync skips that document with a logged error | Grant the executing user edit access to the document |
| Floating actions not discovered | Sync logs `count: 0`; sheet gets no new rows | Ensure items begin with a PERSON chip or a valid email address (`word@word.tld`) as the very first content of the paragraph/list item |

---

## Running Tests

```bash
# Always use -x (fail-fast): stop after the first test that fails.
# Within a test, all assertions run to completion — multiple defects within one
# test accumulate. The -x flag only prevents starting the *next* test while a
# blocking failure exists.
/mnt/c/dev/venvs/uv1/bin/python -m pytest tests/ -x -v

# Parser unit tests only (fast, no GAS/network):
/mnt/c/dev/venvs/uv1/bin/python -m pytest tests/test_floating_action_parser.py -x -v

# UC-A acceptance tests (requires live GAS — clasp push first):
/mnt/c/dev/venvs/uv1/bin/python -m pytest tests/test_uc_a.py -x -v
```

Each UC scenario test has significant setup/teardown cost (GAS invocation, log polling up to 60 s).
A root-cause failure in an early scenario cascades to all later ones — running to completion wastes
minutes and obscures the real defect. Fix the first failure before proceeding.

### UC-A Tests

**Prerequisites:** `npm run deploy:test` (pushes `src/`, stamps the revision, and repoints the TEST deployment).

Prefer the Web App HTTP fixtures for setup and state mutation whenever the UI itself is not the subject of the test. Reserve Playwright for assertions about the Docs homepage card and other user-visible add-on behavior.

The `uc_a_clear` GAS fixture sets up the test doc automatically:
1. Clears the ActionSheet and removes all named ranges from the test doc.
2. Clears the doc body and inserts a chip-led bullet list item via the Docs REST API (`insertPerson` + `createParagraphBullets`).
3. Appends an email-led bullet list item via a second REST API call (`_tfAppendTextListItem`).

No manual doc preparation is required. The test doc needs no pre-existing chip items.

**Tests:**
- `test_uc_a_ac1_multi_format_detection` — one Sync; verifies chip-led and email-led items both appear in the ActionSheet with correct email, name, action text, and status.
- `test_uc_a_ac2_idempotent_second_sync` — second Sync; verifies no duplicate rows, named range IDs unchanged, sheet rows and doc floating actions identical.

---

## Recovery Procedures

### Sync wrote stale values to the sheet (timestamp conflict resolved incorrectly)
1. Identify the affected row using the `Date Modified` column
2. Edit the correct field values directly in the sheet
3. The `onEdit` trigger will update `Date Modified` to now
4. On the next sync, the sheet row's newer timestamp will win and propagate to the document

### Triggers missing after script re-creation
1. Open the Spreadsheet
2. Open Apps Script editor
3. Run `initializeTriggers` manually
4. Confirm `Action Sync` menu reappears and the Executions log shows the next timed run scheduled
