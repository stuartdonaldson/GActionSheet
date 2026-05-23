# OPERATIONS.md — GActionSheet

## Clasp Projects

This repo contains two Apps Script projects pushed via clasp.

| Project | Directory | Script ID | Bound to |
|---------|-----------|-----------|----------|
| Workspace Add-on | `src/addon/` | `1rQP0qFPh4HrkD2YfVou6bMEXr_beRySLxwW8no5TFtbQyiUldx3XX1fW` | Standalone (add-on) |
| Automation (container-bound) | `src/automation/` | `12EKX7dQiO1Wf7rvv94Adgpbh3nac0OetsZMTD_1lme3y2o1KLYdKcTXi` | ActionSheet spreadsheet (`10UCsEHPL2RjA1IduUSFDSaA2lpkoCuZY79sIjratH_s`) |

### Pushing

```bash
npm run push:addon        # push src/addon/ → add-on script project
npm run push:automation   # push src/automation/ → container-bound script project
```

Each push replaces the full project content. Do not push from the repo root
`.clasp.json` — that config is retained for reference only.

If you see `Skipping push.` (clasp 3.x hash cache), add `--force`:

```bash
cd src/automation && clasp push --force
```

### First-time setup (new machine)

1. `clasp login` (or restore `.auth/user.json` to `~/.clasprc.json`)
2. Run `npm run push:automation` to verify the automation project is reachable.
3. Open the Apps Script editor for the automation project and run `bootstrap()`
   from `TestFixtures.js` to set script properties (`TEST_DOC_ID`,
   `TEST_SHEET_ID`, `GAS_LOGGER_FOLDER_ID`).
4. Run `smokeAutomation()` once to confirm GasLogger output appears in Drive.

### Running Tests

See the TDD lifecycle in `/knowledge-base/adr/` for phase conventions.

```bash
npm run test:smoke        # Playwright smoke test (requires running sheet URL)
```

GAS test invocation: open the ActionSheet in Sheets, use the **Action Sync** custom
menu. See the `gas-test-invocation` bd memory for selector details.
