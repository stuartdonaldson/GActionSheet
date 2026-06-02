# PROBE — Deployment & Identity Instrumentation Spec

**Status:** Draft  
**Purpose:** One-time (repeatable) instrumentation to characterise how effective user identity,
execution context, and code version vary across deployment configurations, add-on installation
sources, document states, and WebApp endpoints.  
**Cleanup:** Remove `PROBE.js` from `src/` and delete all `PROBE_log()` call sites. Every
insertion point is marked with the comment `// PROBE`.

---

## 1. Test Matrix

### 1.1 Fixed dimensions (vary between runs, not within a run)

| Dimension | Run A | Run B | Run C |
|-----------|-------|-------|-------|
| Installed add-on source | Direct test deployment (`/dev` installed) | Direct test deployment | Marketplace SDK draft |
| Deployment state | `npm run push` only | After `npm run deploy:test` | After Marketplace SDK version updated to current TEST |

Runs are sequential and irreversible — A → B → C.

### 1.2 Variable dimensions (exercised within every run)

| Dimension | Values |
|-----------|--------|
| WebApp endpoint | DEV (`…/dev`), TEST (`…/exec`) |
| Doc state | New doc (no prior sync), Existing doc (has AI-N tokens + tracker table) |

### 1.3 Instrumented surfaces

| Surface ID | Code location | Entry point |
|------------|---------------|-------------|
| `doGet.dev` | `WebApp.js` | `doGet(e)` hit on `/dev` URL |
| `doGet.test` | `WebApp.js` | `doGet(e)` hit on `/exec` URL |
| `doPost.dev` | `WebApp.js` | `doPost(e)` hit on `/dev` URL |
| `doPost.test` | `WebApp.js` | `doPost(e)` hit on `/exec` URL |
| `sidebar.new` | `WorkspaceAddonCard.js` | `buildHomepageCard()` — new doc |
| `sidebar.existing` | `WorkspaceAddonCard.js` | `buildHomepageCard()` — existing doc |
| `chipHover.new` | `EditorAddonCard.js` | `onLinkPreview(e)` — new doc |
| `chipHover.existing` | `EditorAddonCard.js` | `onLinkPreview(e)` — existing doc |
| `onOpen` | `MenuHandler.js` | `onOpen()` simple trigger |
| `menu` | `MenuHandler.js` | `menuSync()` (or any menu handler) |

---

## 2. PROBE.js Design

### 2.1 Principles

- Single file `src/PROBE.js` — all probe logic lives here.
- One public API: `PROBE_log(surface, extraData)`.
- `PROBE_ENABLED` flag at top of file — set to `false` to make all calls no-ops without removing them.
- All GasLogger tags prefixed `PROBE.` — one grep finds everything across all log files.
- RunId is the primary correlation key across surfaces and runs.

### 2.2 RunId protocol

Playwright generates a UUID at test-session start and passes it inbound to the first
WebApp hit. `PROBE_log` then reads it from Script Properties on every subsequent call.

```
Playwright ──► doGet(?probe_run=<uuid>)
                  └─► PROBE_setRunId(uuid) → ScriptProperties['PROBE_RUN_ID']
               doPost({probe_run: <uuid>, ...})
                  └─► PROBE_setRunId(uuid)   (same key, idempotent)

sidebar / chipHover / onOpen / menu
   └─► PROBE_log reads ScriptProperties['PROBE_RUN_ID']
```

The WebApp endpoints must be hit **before** the UI surfaces are exercised in each Playwright run.

### 2.3 Identity fields captured at every surface

| Field | Source |
|-------|--------|
| `effectiveUser` | `Session.getEffectiveUser().getEmail()` |
| `activeUser` | `Session.getActiveUser().getEmail()` |
| `version` | `BUILD_INFO.version` |
| `buildDate` | `BUILD_INFO.buildDate` |
| `webappUrl` | `BUILD_INFO.webappUrl` (stamped at deploy time) |
| `serviceUrl` | `ScriptApp.getService().getUrl()` (runtime, where available) |
| `timestamp` | `new Date().toISOString()` |
| `runId` | from ScriptProperties |
| `surface` | passed by call site |

`serviceUrl` is available in `doGet`/`doPost` contexts. In card/add-on contexts
`ScriptApp.getService()` may not be callable — catch and omit if it throws.

### 2.4 Additional per-surface fields

| Surface | Extra fields |
|---------|-------------|
| `doGet.*` | `queryString`, `parameter` (full `e.parameter`), `pathInfo` |
| `doPost.*` | `action` field from payload, `senderVersion` (if payload includes it) |
| `sidebar.*` | `docId`, `docState` (`new`\|`existing`) |
| `chipHover.*` | `matchedUrl`, `globalId` extracted from URL, `docState` |
| `onOpen` | `authMode` (value of `e.authMode` if present) |
| `menu` | `menuItem` label |

### 2.5 PROBE.js implementation spec

```javascript
// PROBE.js — Deployment & identity instrumentation.
// Set PROBE_ENABLED = false to silence all probes without removing call sites.
// Delete this file + all // PROBE call sites to strip instrumentation permanently.

var PROBE_ENABLED = true;
var PROBE_RUN_ID_KEY = 'PROBE_RUN_ID';

/** Store runId received from Playwright. Idempotent — last write wins. */
function PROBE_setRunId(runId) {
  if (!PROBE_ENABLED || !runId) return;
  PropertiesService.getScriptProperties().setProperty(PROBE_RUN_ID_KEY, runId);
}

/** Read back the stored runId (empty string if not set). */
function PROBE_getRunId() {
  if (!PROBE_ENABLED) return '';
  return PropertiesService.getScriptProperties().getProperty(PROBE_RUN_ID_KEY) || '';
}

/**
 * Log a probe entry. surface: a Surface ID string from §1.3.
 * extraData: object merged into the log entry.
 */
function PROBE_log(surface, extraData) {
  if (!PROBE_ENABLED) return;

  var serviceUrl = '';
  try { serviceUrl = ScriptApp.getService().getUrl(); } catch (_) {}

  var entry = {
    runId:         PROBE_getRunId(),
    surface:       surface,
    timestamp:     new Date().toISOString(),
    effectiveUser: Session.getEffectiveUser().getEmail(),
    activeUser:    Session.getActiveUser().getEmail(),
    version:       BUILD_INFO.version,
    buildDate:     BUILD_INFO.buildDate,
    webappUrl:     BUILD_INFO.webappUrl || '',
    serviceUrl:    serviceUrl
  };

  // Merge caller-supplied fields (caller wins on collision).
  var keys = Object.keys(extraData || {});
  for (var i = 0; i < keys.length; i++) entry[keys[i]] = extraData[keys[i]];

  GasLogger.log('PROBE.' + surface, entry);
  GasLogger.flush();
}
```

---

## 3. Call-Site Insertions

### 3.1 `WebApp.js — doGet()`

After the URL registration block, before the `return`:

```javascript
// PROBE
var _probeRunId = (e && e.parameter && e.parameter.probe_run) || '';
PROBE_setRunId(_probeRunId);
PROBE_log('doGet.' + (_probeRunId ? 'dev' : 'unknown'), {
  queryString:   (e && e.queryString)  || '',
  parameter:     JSON.stringify((e && e.parameter) || {}),
  pathInfo:      (e && e.pathInfo)     || ''
});
```

> Note: surface tag (`dev` vs `test`) can't be auto-detected from within GAS — the Playwright
> caller distinguishes by which URL it hit. Pass `probe_surface=doGet.dev` or `doGet.test`
> as an additional query param and read it here.

Revised:

```javascript
// PROBE
var _probeRunId     = (e && e.parameter && e.parameter.probe_run)     || '';
var _probeSurface   = (e && e.parameter && e.parameter.probe_surface) || 'doGet';
PROBE_setRunId(_probeRunId);
PROBE_log(_probeSurface, {
  queryString: (e && e.queryString)  || '',
  parameter:   JSON.stringify((e && e.parameter) || {}),
  pathInfo:    (e && e.pathInfo)     || ''
});
```

### 3.2 `WebApp.js — doPost()`

At the top of `doPost()`, after `payload` is parsed:

```javascript
// PROBE
PROBE_setRunId(payload.probe_run || '');
PROBE_log(payload.probe_surface || 'doPost', {
  action:        payload.action || '',
  senderVersion: payload.probe_version || ''
});
```

Playwright injects `probe_run`, `probe_surface`, and `probe_version` into every POST body.

### 3.3 `WorkspaceAddonCard.js — buildHomepageCard()`

At entry, before any doc resolution:

```javascript
// PROBE
PROBE_log('sidebar.' + PROBE_docState(null), {});
```

After `doc` is resolved (and doc state is knowable):

```javascript
// PROBE
var _probeDocState = PROBE_docState(doc);
PROBE_log('sidebar.' + _probeDocState, { docId: doc ? doc.getId() : '' });
```

Add helper to `PROBE.js`:

```javascript
/**
 * Returns 'new' if the doc has no AI-N tokens or tracker table, 'existing' otherwise.
 * Pass null if doc is not yet resolved — returns 'unknown'.
 */
function PROBE_docState(doc) {
  if (!doc) return 'unknown';
  try {
    var body = doc.getBody().getText();
    return /AI-\d+:/.test(body) ? 'existing' : 'new';
  } catch (_) { return 'unknown'; }
}
```

### 3.4 `EditorAddonCard.js — onLinkPreview()`

At entry:

```javascript
// PROBE
var _probeUrl = (e && e.docs && e.docs.matchedUrl && e.docs.matchedUrl.url) || '';
PROBE_log('chipHover.' + PROBE_docState(DocumentApp.getActiveDocument()), {
  matchedUrl: _probeUrl,
  globalId:   _globalIdFromChipUrl(_probeUrl)
});
```

### 3.5 `MenuHandler.js — onOpen()`

`onOpen` is a simple trigger and **cannot call `PropertiesService`** (authorized service
restriction). Log only what is safe — use `Logger.log` directly, not GasLogger:

```javascript
// PROBE — simple trigger: authorized services not available; use Logger only
if (PROBE_ENABLED) {
  Logger.log(JSON.stringify({
    tag:       'PROBE.onOpen',
    version:   BUILD_INFO.version,
    timestamp: new Date().toISOString()
  }));
}
```

> `Session.getActiveUser()` and `Session.getEffectiveUser()` are also off-limits in simple
> triggers. The Logger output is visible in the Apps Script editor execution log, not GasLogger
> Drive files — note this in log collection.

### 3.6 `MenuHandler.js — menuSync()` (representative menu handler)

At entry, before delegating:

```javascript
// PROBE
PROBE_log('menu', { menuItem: 'menuSync' });
```

Apply the same pattern to any other menu items exercised by the Playwright test.

---

## 4. Playwright Test Sequence

One reusable test function `runProbeSession(runId, opts)` where opts carries:
- `devUrl` — the `/dev` WebApp URL
- `testUrl` — the `/exec` WebApp URL  
- `newDocUrl` — URL of a freshly created Google Doc
- `existingDocUrl` — URL of a doc with existing AI-N tokens
- `sheetUrl` — URL of the ActionSheet spreadsheet

### 4.1 Step sequence

```
1.  Generate runId = UUID
1a. Print runId to stdout immediately — copy into probe-runs.md before any other step
2.  Hit devUrl?probe_run=<runId>&probe_surface=doGet.dev   (GET, no auth)
3.  Hit devUrl?probe_run=<runId>&probe_surface=doGet.dev   (GET, with Playwright auth)
4.  Hit testUrl?probe_run=<runId>&probe_surface=doGet.test (GET, no auth)
5.  Hit testUrl?probe_run=<runId>&probe_surface=doGet.test (GET, with Playwright auth)
6.  POST devUrl  { probe_run, probe_surface:'doPost.dev',  probe_version: BUILD_INFO_VERSION, action:'probe' }
7.  POST testUrl { probe_run, probe_surface:'doPost.test', probe_version: BUILD_INFO_VERSION, action:'probe' }

-- NEW DOC --
8.  Open newDocUrl in browser (authenticated)
9.  Open sidebar → wait for buildHomepageCard to fire  → PROBE.sidebar.new logged
10. Insert AI-1: floating action via @-mention or typed token
11. Click Sync Now in sidebar
12. Hover over generated AI-1: chip → wait for preview card → PROBE.chipHover.new logged

-- EXISTING DOC --
13. Open existingDocUrl in browser (authenticated)
14. Open sidebar → PROBE.sidebar.existing logged
15. Hover over an existing chip → PROBE.chipHover.existing logged

-- SPREADSHEET --
16. Open sheetUrl in browser (authenticated)
17. Wait for onOpen to fire (Apps Script editor log captures PROBE.onOpen)
18. Click Action Sync → Sync → PROBE.menu logged
```

### 4.2 Unauthenticated GET variants (steps 2 & 4)

Use a separate Playwright `browser.newContext()` with no stored auth to simulate an
anonymous caller. The response body and GAS identity data will differ — that difference
is the finding.

### 4.3 Probe POST action

`doPost` currently requires `WEBAPP_SECRET` or `TEST_TOKEN`. Add a probe-specific route
gated only by a `probe_run` being present and non-empty, returning a minimal JSON
response. This avoids entangling probe with secret management:

```javascript
// PROBE — in doPost(), before secret gate
if (payload.action === 'probe' && payload.probe_run) {
  PROBE_setRunId(payload.probe_run);
  PROBE_log(payload.probe_surface || 'doPost', {
    action: 'probe',
    senderVersion: payload.probe_version || ''
  });
  return _jsonResponse({ probe: 'ok', version: BUILD_INFO.version }, 200);
}
```

---

## 5. Log Retention & Collection

### 5.1 Retention policy

**GasLogger Drive files are never deleted.** The logger folder is append-only — probe run
files coexist permanently with normal operational logs. The `runId` is the only scope
boundary needed; filenames are timestamps and are not meaningful.

**Do not clean up probe log files after analysis.** Raw logs must be available for:
- Re-analysis with different questions
- Comparison against future probe runs (e.g. after a GCP config change, a new Marketplace
  version, or a GAS platform update)
- Audit of what the identity context was at a specific point in time

### 5.2 Run registry

Every probe session must be registered in `staging/probe-runs.md` **before** exercising
any surfaces. Playwright prints the `runId` at step 1a; copy it immediately.

`staging/probe-runs.md` format:

```markdown
| runId | Date | Run | Deployment state | Installed add-on | Notes |
|-------|------|-----|-----------------|-----------------|-------|
| abc-123... | 2026-06-01 | A | push-only | direct /dev | baseline |
| def-456... | 2026-06-01 | B | deploy:test | direct /dev | |
| ghi-789... | 2026-06-01 | C | deploy:test + SDK updated | Marketplace draft | |
```

Add a row for every run, including partial or failed runs — note what failed in the Notes
column. A failed run's `runId` may still have partial log data worth keeping.

### 5.3 Sources

| Source | How to collect |
|--------|---------------|
| GasLogger Drive files | `GasLogger.flush()` after every PROBE_log; files accumulate in the logger Drive folder — do not delete |
| Apps Script `Logger.log` | Manually copy from Script Editor execution log (onOpen only) — paste into `staging/probe-runs.md` notes for that runId |
| Playwright response bodies | Captured inline — doGet response text, doPost JSON; save to `staging/probe-responses-<runId>.txt` |

### 5.4 Grep recipe

```bash
# All probe entries from all log files for a given run
grep '"PROBE\.' *.log | grep '"runId":"<uuid>"'

# By surface
grep 'PROBE\.sidebar' *.log
grep 'PROBE\.chipHover' *.log
grep 'PROBE\.doGet' *.log
```

### 5.5 Report structure

For each run (A / B / C), produce a table:

| Surface | effectiveUser | activeUser | version | serviceUrl | notes |
|---------|--------------|------------|---------|------------|-------|
| doGet.dev (no auth) | | | | | |
| doGet.dev (authed) | | | | | |
| doGet.test (no auth) | | | | | |
| doGet.test (authed) | | | | | |
| doPost.dev | | | | | |
| doPost.test | | | | | |
| sidebar.new | | | | | |
| sidebar.existing | | | | | |
| chipHover.new | | | | | |
| chipHover.existing | | | | | |
| onOpen | — | — | version only | — | Logger only |
| menu | | | | | |

Diff Run A vs B vs C column-by-column. Cells that differ across runs are the findings.

---

## 6. Cleanup

**Cleanup requires explicit human approval. Do not initiate cleanup autonomously.**

The analysis document is a snapshot of one set of questions. Additional questions may arise
after review, or a future configuration change may warrant a comparison run against the
existing log data. The instrumentation and raw logs must remain intact until the user
explicitly signs off.

### 6.1 Approval gate

Before any cleanup step is taken, the user must explicitly confirm:
- All questions from the current analysis are resolved
- No further re-analysis against existing run data is anticipated
- No future comparison run is planned that would need the current baseline

A statement like "ok let's clean up" or "we're done with the probe" constitutes approval.
Completing the analysis write-up does NOT.

### 6.2 Cleanup steps (after explicit approval only)

1. Confirm all raw log files are still in the GasLogger Drive folder — do not delete them
2. Confirm `staging/probe-runs.md` has a complete row for every run
3. Delete `src/PROBE.js`
4. Remove all lines marked `// PROBE` from call sites
5. Remove the `probe` action branch from `doPost()`
6. `npm run push` to restore clean state
7. Move this spec and `probe-runs.md` to `knowledge-base/references/` for long-term reference

**GasLogger Drive files are never deleted** — even after cleanup. They remain as the
permanent ground truth for all past runs.

---

## 7. Open Questions

- Does `ScriptApp.getService().getUrl()` work in card/add-on trigger contexts, or does it
  throw? (Confirmed safe in `doGet`/`doPost`; unknown for homepage/linkPreview triggers.)
- Can `Session.getActiveUser()` ever return a value in a doGet with `access=ANYONE` and
  an unauthenticated caller? (Expected: empty string — probe will confirm.)
- Does the Marketplace SDK draft install change which script project's code runs, or only
  the OAuth consent/scope surface?
