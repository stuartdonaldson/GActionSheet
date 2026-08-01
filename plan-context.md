# plan-context.md — gts-79dw team-portal surface map

Generated for `plan-79dw.md` Unit 0. Backend section is stable; frontend
section is written/refreshed by Unit A once the frontend source of truth
moves. If a downstream unit finds this doc wrong or incomplete for its
unit, correct it as part of that unit's Result — don't silently work around it.

---

## §Backend/route contracts

All routes below are `doPost` actions dispatched from `WebApp.js`'s main
handler (~`src/WebApp.js:520-580`, the `if (payload.action === '...')` chain).
The four routes relevant to Units B/C/D are **verified-portal** routes: they
bypass `WEBAPP_SECRET` intentionally because the caller's identity proof
*is* the NUUC-Dispatch signed `assertion` in the body (re-verified on every
call, R8) — not `testToken`/`secret`. Contract text historically said
`idToken`; every verified route now actually reads `payload.assertion`
(moved by gts-79dw.4.18 when identity verification moved from raw GIS
tokeninfo to NUUC-Dispatch signed assertions — see `AccessControl.js:1-36`
file header). Follow `assertion`, not the frozen contract's `idToken`.

### Auth / tier resolution (`src/AccessControl.js`)

- **`_verifySignedAssertion(assertion)`** (`AccessControl.js:321`) — HMAC-SHA256
  verify against the Script Property named by the assertion's own `kid`
  claim, then iss (`nuuc-dispatch`) / aud (`gactionsheet`) / exp checked.
  Returns `{ verified, sub, email }`. Fails closed (R6).
- **`_resolveIdentityAndAccessTier(assertion, teamId)`** (`AccessControl.js:94`)
  — the shared resolver every route below calls. Verifies the assertion,
  then resolves `teamId` → every matching `TeamData` row → folder id →
  `DriveApp.getAccess()` (falls back to Admin SDK group-membership walk,
  `SPIKE.js`). Returns
  `{ verified, sub, email, tier: 'NONE'|'VIEW'|'EDIT', method, folderTiers }`.
  `tier` is the **MAX across all of the team's folders** (R3a) — team-wide
  READ visibility only; NOT sufficient authorization for a write (see next).
- **`_authorizeDocWrite(resolved, docId)`** (`AccessControl.js:263`) — the
  write-side check. Re-authorizes EDIT against the **specific folder the
  target document actually resides under** (R3b) using `resolved.folderTiers`
  — team-wide EDIT tier from one sub-folder never confers write over a
  document under a sibling folder. Always call this per-document; never
  trust the team-wide `tier` alone for a mutation.
- **`_handleListMyTeams`** (`AccessControl.js:204`, action `list_my_teams`) —
  verifies the assertion once, resolves tier across every team the caller
  has any access to. No `teamId` in the request (that's the point).

### Read routes

- **`_handleGetDocumentActions(payload)`** — `src/DocView.js:63`, action
  `get_document_actions`. Body `{ assertion, docId }`.
  1. `_readDocDataRow(ss, docId)` (`SyncManager.js`) → `teamId` (DocData
     lookup — explicitly NOT `_walkFolderForTeam`, which is only for
     assigning teamScope at sync time / re-auth on write).
  2. `_resolveIdentityAndAccessTier(assertion, teamId)`.
  3. NONE tier → `actions: []` (R8: no action data ever leaks below tier).
     Otherwise `_findSheetActionsForDoc(ss, docId)` (factored out of
     `_handleFindSheetActions` in `WebApp.js`) is the data source — reuse,
     not a second reader.
  Response: `{ tier, teamId, docName, docUrl, actions: [...], teamPortalUrl }`.
  `docName`/`docUrl`/`teamPortalUrl` are populated regardless of tier (echo
  of caller-supplied `docId`, not privileged data). `teamPortalUrl` =
  `_VERIFIED_TEAM_PORTAL_BASE + '?team=' + teamId` — this is the "back to
  View A" link (R20), wired but not yet clickable end-to-end until View A
  actually lives at that origin (Unit A).
  Log: `webapp.team.docview` `{ sub, tier, docId, count }`.

### Write routes (`src/TeamActionWrite.js`)

Both share `_resolveIdentityAndAccessTier` + reuse the existing mutation
cores (`_editActionRowCore` / `_patchActionStatusCore`, factored out of the
legacy `edit_action_row` / `patch_action_status` test-token routes in
`WebApp.js`) — never re-implement Dirty/Date-Modified stamping or the
status write.

- **`_handleTeamEditAction(payload)`** — `TeamActionWrite.js:57`, action
  `team_edit_action`. Body `{ assertion, teamId, global_id, fields }`.
  `docId = parseGlobalId(globalId).docId` (format `{docId}/AI-{N}`,
  `WebApp.js:936`). Requires `_authorizeDocWrite(resolved, docId)` —
  EDIT-tier-on-folder ONLY, no assignee bypass. Rejects before any mutation
  (no partial execution): `outcome` is `'rejected-unverified'` (bad
  assertion) or `'rejected-doc-scope'` (verified but not authorized for
  this doc's folder). On success: `_editActionRowCore(globalId, fields)`.
  Response: `{ ok, global_id, outcome }`. Log: `webapp.team.edit`
  `{ eu, au, global_id, outcome }` (`eu` = this execution's own identity,
  `au` = verified caller's `resolved.email`).
- **`_handleTeamPatchStatus(payload)`** — `TeamActionWrite.js:91`, action
  `team_patch_status`. Body `{ assertion, teamId, global_id, status }`.
  Same docId/tier resolution as above, but authorization is
  `_authorizeDocWrite(...) OR isAssignee` (R17) — `isAssignee` is decided
  off the row's **durable** `assigneeEmail` (looked up from the sheet,
  `_loadExistingRowsByGlobalId`) matching `resolved.email`, never anything
  client-supplied. Lets an external assignee with only VIEW tier change
  their own action's status. On success: `_patchActionStatusCore(globalId,
  newStatus)`. Response: `{ ok, global_id, outcome }`. Log:
  `webapp.team.status` `{ eu, au, global_id, outcome }`.

### Chip-link CTA URL construction (anonymous → verified handoff)

`_handlePreviewNotice(e)` — `src/WebApp.js:123` (doGet `?cmd=preview&docId=
<docId>&ain=AI-N`, ADR-0017 Phase 1 anonymous chip notice, ties into
gts-79dw.4.9). When the chip's `docId` resolves to a `DocData.teamId`
(again `_readDocDataRow`, not `_walkFolderForTeam`), the rendered page
gets a "Sign in for the full view" CTA:

```
docViewUrl = _VERIFIED_TEAM_PORTAL_BASE + '?doc=' + encodeURIComponent(docId)
                                         + '&team=' + encodeURIComponent(teamId)
```

(`WebApp.js:141-143`). No `DocData.teamId` → `docViewUrl` is `''` and the
CTA row is omitted — falls back to the plain Phase-1 anonymous notice, no
error. Completion log `webapp.team.handoff` `{ docId, teamId, route }` where
`route` is `'docview-cta'` or `'anonymous-preview-fallback'`.

Compare to View B's own outbound link back to View A, which uses only
`?team=` (`DocView.js:92`, no `doc` param — that's the team-list view, not
a specific document).

**`_VERIFIED_TEAM_PORTAL_BASE`** is defined **twice** — once in
`DocView.js:57` and again implicitly reused via the same string literal at
`WebApp.js` (search both files for `nuuc-it.github.io/Static/pub/AS/`) —
currently `'https://nuuc-it.github.io/Static/pub/AS/'`. **Unit A will
change this value** when the frontend source of truth moves out of the
sibling `Static` repo; both definitions must be updated together (or
consolidated into one shared constant — flagged as a candidate cleanup for
whichever unit touches this next, not decided here).

### Query-string contract the frontend must implement (relevant to Unit C)

Two distinct query-string shapes are already generated server-side and
currently dead-end client-side:

| Origin | URL shape | Meaning |
|---|---|---|
| Chip CTA (`_handlePreviewNotice`) | `?doc=<docId>&team=<teamId>` | jump straight to View B for one document |
| View B's own "back to team" link (`get_document_actions` → `teamPortalUrl`) | `?team=<teamId>` | View A, team list, no specific doc |

A page load with `doc` present should route to View B (Unit D) scoped to
that `docId`, using `teamId` only for initial context (View B re-resolves
tier itself server-side via `get_document_actions`, R8 — the query param is
routing only, not a trust boundary). A page load with only `team` present
is View A.

### Related read/sync routes (context, not directly touched by B/C/D)

- `list_team_actions` (`WebApp.js:531`, renamed from `list_board_actions`,
  gts-79dw.4.11) — View A's list data.
- `team_sync_document` (`WebApp.js:550`) — requires EDIT tier, rejected
  before sync runs otherwise.
- `verify_and_resolve_access` (`AccessControl.js:50`) — generic tier probe,
  `{ verified, sub, email, tier }`.

---

## §Frontend file map

Written by Unit A (`gts-79dw.4.25`). The frontend source of truth is now
**`static-portal/src/index.html`** in this repo — edit that file, not
`/home/stuar/proj/Static/pub/AS/index.html` (stale reference/pre-migration
copy; the publish pipeline no longer touches it).

- **`static-portal/src/index.html`** — the entire portal page: markup,
  styles, and JS all inline in one file (no separate CSS/JS assets, same
  structure the migrated content already had). Everything B/C/D touch lives
  here:
  - **View A (team list)** — the only view that exists today. `#signinView`
    / `#launchView` / `#appView` are the three top-level states
    (signed-out / transitional / signed-in); `#appView` renders the
    team-list UI: `#teamSel` (team switcher), `#statusSeg`/`#scopeSeg`/
    `#windowSel` (filters), `#list` (document-grouped action rows via
    `render()`/`rowHtml()`).
  - **Stubbed controls Unit B wires up:** the per-row `data-edit` button
    (currently just `toast('Editing lands in a follow-up bead...')` in
    `render()`'s `listEl.querySelectorAll('[data-edit]')` handler — call
    `team_edit_action` instead) and the assignee status-chip menu
    (`openStatusMenu()` / the `data-set` button handler inside it —
    currently also just a toast; call `team_patch_status` instead). Both
    already read `state.assertion`/`state.teamId` — reuse those, don't
    re-derive.
  - **Query-string handling Unit C adds:** none exists yet — no
    `location.search`/`URLSearchParams` read anywhere in the file. The
    natural entry point is right after the `<script>` block's top
    (alongside the `STATIC_BUILD_VERSION_`/`STATIC_WEBAPP_URL_`/
    `STATIC_ENV_LABEL_` build-stamp constants, before `initAuth()` runs) —
    parse `doc`/`team` before deciding whether to render View A or
    (post-Unit-D) View B.
  - **Where View B lives (Unit D, closed):** `static-portal/src/doc.html` —
    a second HTML file alongside `index.html`, per the placement this
    section originally proposed. `scripts/build-static-portal.js` was
    extended with a `STAMPED_PAGES = ['index.html', 'doc.html']` list (its
    single-file stamping call became a loop over that list; the
    copy-everything-else loop excludes both names instead of just
    `index.html`) — both pages get the same three build-time placeholders
    stamped identically. `doc.html` duplicates (not shares — no include
    mechanism exists in this single-file-per-page architecture)
    `index.html`'s sign-in/auth-cache/`postJson` logic verbatim.
    **`index.html`'s `?doc=` handling now redirects here**
    (`location.replace('doc.html' + location.search)`) instead of showing
    the interim `#docViewNotice` banner Unit C shipped (that element was
    removed from `index.html`'s markup once nothing sets it visible
    anymore); `initAuth()` is guarded (`if (QUERY_DOC) return;`) so no
    wasted team-list calls fire before the redirect. `doc.html` re-parses
    `?doc=`/`?team=` independently — `teamId` is initial-context only, tier
    is always re-resolved server-side (R8).
  - **`get_document_actions`'s actual response shape (confirmed while
    building View B — this was NOT documented above and is easy to get
    wrong by pattern-matching `index.html`'s `list_team_actions` rows):**
    `actions` is the **raw** `_findSheetActionsForDoc` `SheetAction` shape
    (`global_id`, `file_id`, `action_id`, `assignee_email`,
    `assignee_name`, `action_text`, `status`, `document_formula`, `doc_id`,
    `doc_name`, `created_date`, `modified_date`, `sync_status`) — `src/DocView.js`
    calls that reader directly with **no** enrichment step. It does
    **NOT** carry `status_bucket`/`status_icon`/`status_resolved`, which
    only exist on `list_team_actions`' enriched rows (a `getStatusDisplay()`
    step that route runs but `get_document_actions` doesn't). Any future
    View-B-adjacent work rendering a status pill must use plain text, not
    `index.html`'s icon/bucket-styled `statusChip()` — that function assumes
    fields this route never sends.
  - **Backend call sites already in the file:** `NUUC_DISPATCH_URL` (sign-in
    only, external project, not stamped), `GACTIONSHEET_URL` (this repo's
    WebApp — now `STATIC_WEBAPP_URL_`, baked at build time, no manual URL
    edits needed for B/C/D). `postJson()` is the shared POST helper — reuse
    it for any new route call, don't hand-roll `fetch`.
  - **Build-time placeholders (do not hardcode a URL/version here):**
    `STATIC_BUILD_VERSION_`, `STATIC_WEBAPP_URL_`, `STATIC_ENV_LABEL_` —
    declared `= null` in source, stamped by
    `scripts/build-static-portal.js` from `src/Version.js`'s `BUILD_INFO`.
    Editing `static-portal/src/index.html` directly and opening it in a
    browser (not via `static-portal/dist/`) leaves these `null` — the page
    still loads (build badge shows "unbuilt source") but
    `GACTIONSHEET_URL` is `null`, so no backend calls will work; build first
    (`node scripts/build-static-portal.js --env sit`) to test against a
    real backend.

- **Learned while writing Unit E.5's live e2e sweep (not previously
  documented here):**
  - `refreshActions()`'s request always carries `statusFilter: state.status`
    (default `'open'`, `TeamListing.js:46` mirrors the same default
    server-side). A row that transitions to a resolved/closed status and is
    then re-fetched by the app's own post-write `refreshActions()` call
    **disappears from the default-filtered view** rather than showing its
    new status in place — switch to `#statusSeg [data-status="all"]` first
    if a test needs to observe a status transition without the row
    vanishing.
  - The assignee status chip's `mine`/editable class (`rowHtml()`'s
    `statusChip(r, isMine(r))`) is gated purely on `isMine(r)` — i.e.
    `row.assignee_email === state.email` — **not** on tier. An EDIT-tier
    caller who isn't the assignee gets a *non*-editable chip in the current
    UI even though `team_patch_status`'s backend authorization would allow
    them via `_authorizeDocWrite`; only the R17 assignee-bypass path is
    reachable through today's UI. Not treated as a bug by this unit (out of
    scope to change), just recorded since it constrains what a UI-driven
    status-change test can exercise.
  - The Sync (`[data-sync]`) and Edit (`[data-edit]`) buttons are rendered/
    enabled only at `tier === 'EDIT'`. No identity with EDIT (rather than
    VIEW) access to `TestTeamA`/`TEAM_A_FOLDER_1` is currently configured in
    this environment (`local.settings.json` key `teamAEditEmail`, unset) —
    the same gap `tests/test_team_write_routes.py` and
    `tests/test_team_portal_hardening.py` already document. Any future live
    e2e test wanting to click-drive Sync/Edit needs that key configured
    first; until then, those success paths can only be tested via
    `page.route()` mocks (Unit B's `team_portal_wired_controls.test.js`) or
    via direct in-page `postJson(GACTIONSHEET_URL, ...)` calls that bypass
    the button (still hits the live route, just not through a real click —
    see `tests/playwright/team_portal_live_sweep.test.js`).

- **Build/publish pipeline:** `scripts/build-static-portal.js` (stamps +
  writes `static-portal/dist/<sit|prod>/`) and
  `scripts/publish-static-portal.js` (builds, then copies/commits/pushes to
  the sibling `Static` repo's `pub/AS-sit/` or `pub/AS/` —
  `local.settings.json`'s `staticPortalRepoPath`). Chained automatically as
  the last step of `pnpm run deploy:test` (→ SIT) / `pnpm run deploy:prod`
  (→ PROD) inside `manage-deployments.js`'s `deployToTarget()`. B/C/D
  sessions don't need to touch these scripts unless adding a second HTML
  page (Unit D, see above).

- **Live URLs:** SIT `https://nuuc-it.github.io/Static/pub/AS-sit/index.html`
  (confirmed live as of Unit A's gate run), PROD
  `https://nuuc-it.github.io/Static/pub/AS/index.html` (not yet published —
  first PROD publish requires `pnpm run deploy:prod` to run once, which no
  unit in this batch has done).

---

## §FIX/IMP/INF/TST cleanup — reusable context (for `plan-fix.md`)

Generated 2026-07-31 from a full read of the 40 open `[FIX]`/`[IMP]`/`[INF]`/
`[TST]` bd issues (separate from the gts-79dw team-portal work above). Re-read
the relevant `bd show <id>` before coding — this is a map, not a spec; issue
descriptions are the authoritative contract.

### Subsystem file map

| File | Role |
|------|------|
| `src/SyncManager.js` | Core scan/sync/flush engine: doc scanning, floating-action parsing, Drive metadata fetch, team-scope resolution, flush-to-doc requests, tracker refresh, configFormat. |
| `src/WebApp.js` | HTTP entry points (`doPost` route table): `sync_action_rows`, `upsert_action_rows`, `mark_doc_not_found`, team-portal routes, ATDD test-support routes. |
| `src/TriggerManager.js` | `initializeTriggers()` — installs onEdit + 30-min syncAll time-based triggers. **Do not remove the time-based trigger to dodge test races** — see Gotchas. |
| `src/EditorAddonCard.js` | Docs editor add-on sidebar/card UI: create-action flow, assignee suggestions, single-item chip flush call site. |
| `src/WorkspaceAddonCard.js` | Workspace add-on homepage/sidebar card: action list rendering, Import tab, single-item chip flush call site. |
| `src/TrackerTable.js` | "Action Item Summary" tracker table insert/refresh, `_trackerRowsMatch`. |
| `src/ArchiveManager.js` | Archives Doc-Not-Found rows after the 24h aging threshold. |
| `src/AccessControl.js` | Identity/access-tier resolution (`_resolveIdentityAndAccessTier`), calls into `SPIKE.js` folder-access fallback. |
| `src/SPIKE.js` | Spike/experimental helpers — some (like `_spikeAdminSdkFolderAccess`) are on the live fallback path despite the name. |
| `src/TeamActionWrite.js` | Team-portal write routes (`team_edit_action`, `team_patch_status`). |
| `src/ContractSchema.js` | Wire-contract/sheet-schema definitions (`CONTRACT_SCHEMA`). |
| `src/GasLogger.js` | GAS-side structured logger, flushes to Axiom. `_HOISTED_KEYS` (env/docId/docIds/eu) go top-level; everything else nests under `data`. |
| `scn/session.py`, `scn/engine.py`, `scn/assertions.py` | Python scenario-test harness (`ScenarioSession`, `CheckpointEngine`, assertion helpers). `_check_gas_errors()` in `session.py` is the always-on fail-fast GAS-log scanner. |
| `tests/helpers/gas_log.py` | Python-side Axiom query/read-back helper for tests. |
| `scripts/query_axiom.py` / `scripts/call_webapp.py` | Sanctioned Axiom-query / manual-WebApp-POST tools — see project CLAUDE.md. |
| `scripts/playwright-auth.js` | `resolveAuthFile()` — shared multi-account Playwright auth taxonomy. |

### Key functions / line anchors (as of 2026-07-31 — confirm with `grep -n` before editing, they drift)

- `_fetchDriveDocMetadata` — `SyncManager.js:1118` — Drive `files.list` bulk metadata fetch feeding syncAll's skip/sync/not-found branching. Missing all-drives flags is the gts-rskf root cause.
- `syncAll()` — `SyncManager.js:287`; DocData integrity pass ~`:469`; per-doc trash/modified check loop ~`:357-360`; `_markDocNotFound` call ~`:371`.
- `_getDocAppProperty` / `_setDocAppProperty` — `SyncManager.js:1171` / `:1200` — also need `supportsAllDrives`.
- `_walkFolderForTeam` — `SyncManager.js:1398` — folder-ancestry team resolution; gts-b6dm extended it with an optional per-run `folderTeamCache` (folderId → `{teamId,teamLink,folderId}`\|null, with a separate error sentinel so Drive errors never clobber existing data).
- `_syncTeamScope` — `SyncManager.js:1647` — treats teamScope as sticky-once-resolved by design; this is the gts-b6dm bug surface.
- `_parseParagraphAsFloatingAction` — `SyncManager.js:644-650` (text extraction) and `:689` (status-token regex `/(([^)]*))\s*$/`, anchored to end-of-text — root of gts-v0py). `_collectActionsFromParagraph` (`:843-851`) routes single-token paragraphs down this path, so soft-return continuation lines are absorbed whole (gts-jxrw).
- `_buildFlushRequests` / `_actionTextStyleRequest` — `SyncManager.js:1761` — uniform `updateTextStyle` request applied on every flush; flattens any inline (per-run) formatting (gts-zocq crux).
- `_readActionFormatConfig` — `SyncManager.js:1671` — Config-sheet-driven style; returns `{aiToken, actionText: null}` by default, so the uniform-style flattening in `_actionTextStyleRequest` is a no-op until a user runs `configFormat` (gts-d99c) and populates an `action_text` Config row.
- `_flushActionParagraph`, syncDocument's `flushIds` loop — `SyncManager.js` ~`233-238` — currently one GET + one `:batchUpdate` per changed action item; gts-kkm7.3 batches this per-doc.
- `_getOrUpsertDocDataRow` — `SyncManager.js:1408` — single write chokepoint for the DocData sheet's Doc Name column (gts-46qv target).
- `_handleSyncActionRows` — `WebApp.js:894-904` (payload read, no doc scan of its own — gts-aiaz surface), `:989` (main handler), orphan/dedup loop `:991-1012` / `:1132-1146`, sheetWins branch `:1020-1029`, existing-row update branch `:1080-1119`.
- `_loadExistingRowsByGlobalId` — `WebApp.js:904` — builds `existingMap` keyed by globalId with a silent last-write-wins overwrite on duplicates (gts-binf root cause). Other call sites: `WebApp.js:130,838,1037,1505,1572,1938,2036,2064,2339,2386,2447`, plus `TeamActionWrite.js:106`.
- `_handleMarkDocNotFound` — payload currently `{docId}` singular; gts-kkm7.1 batches to `{docIds:[...]}`.
- `_handleVerifyActionRows` — `WebApp.js:1150` — existing (insufficient) teamScope-vs-DocData.teamId reconciliation; both sides go stale together on a folder move, which is why it can't catch gts-b6dm's bug.
- `_spikeAdminSdkFolderAccess` — `SPIKE.js:274` — called from `AccessControl.js:162` on the **live** `_resolveIdentityAndAccessTier` fallback path (not gated by `SPIKE_ENABLED` despite the filename). Logs routine group-non-membership 404s under a `.error`-suffixed tag (gts-q2sq).
- Python harness: `CheckpointEngine.drain()` (`scn/engine.py`), `check_present_consistent()` (`scn/assertions.py`), `ScenarioSession.verify_consistency(scope=Surface.SHEET)` (`scn/session.py`) — targets of gts-dxz3.
- `tests/helpers/gas_log.py`'s `_axiom_query()` — fixed 2026-07-31 to pop the nested `data` sub-object rather than treating the whole raw Axiom row (incl. stale legacy top-level columns) as the payload.

### Known gotchas / traps surfaced during this review

- **Don't disable the 30-min syncAll trigger to dodge test races.** Explicitly tried and reverted (2026-07-31, see gts-iwa0 comment log) — a test run that dies before re-enabling it leaves scheduled sync off in that environment permanently (fails open, worse than the race). The real fix for the race is a per-docId lock (gts-li3g).
- **`.error`-suffixed GAS log tags trip a shared fail-fast scanner across unrelated tests.** `scn/session.py`'s `_check_gas_errors()` scans the whole shared `gasLogDir` since a running fence, not scoped to the current scenario. A routine/expected condition logged as `*.error` (gts-q2sq) can fail tests that never touch that code path at all.
- **Axiom read-back in the test harness has a recurring ~60s false-timeout pattern** (gts-9a1m) across at least 3 different log-tag waits (`sync.teamScope.resolved`, `importList.done`, `importSelected.done`). In every observed case the event WAS in Axiom when queried after the fact — the harness's read-back path is the fault, not the product. Before concluding a regression from a single log-wait timeout, re-query with `scripts/query_axiom.py` to check whether the event actually landed.
- **xlsx export loses sub-second datetime precision.** `created_date`/`modified_date` comparisons in `scn/assertions.py` now tolerate a 2s delta (was bit-exact) — this is a real Google xlsx-export artifact, not a bug in the sync logic (gts-930o).
- **Shared Drive vs My Drive folder-id heuristic:** a 19-character folder id is a Shared Drive root; a 33-character id is a My Drive folder. Useful for quickly eyeballing which TeamData rows are Shared-Drive-hosted (the class gts-rskf silently broke).
- **`data`-nesting Axiom migration is mid-flight** (gts-iwa0): GAS log payloads now nest under `data` except for a small `_HOISTED_KEYS` allowlist (env/docId/docIds/eu). The Axiom console still needs an explicit map-field creation for `data` (console-only — current tokens lack `datasets:update` scope) — code-side work is done and deployed to TEST.
- **Twin-ticket "no shared context" rule vs. session batching:** CLAUDE.md requires a `[TST]` issue's author not read the paired `[FIX]`/`[IMP]`'s implementation, working only from the frozen contract in the issue description. `plan-fix.md` batches several FIX+TST twins into the same session for cost reasons, which is in tension with strict no-shared-context. Where a session contains both halves of a twin, author the test against the **issue's Design/AC text**, not by reading the freshly-written implementation diff, to preserve the spirit of the rule.
- **Backstop rule applies to every new/extended assertion in this batch:** each must be shown to fail against the pre-fix build before it's trusted (not just pass post-fix). Several issue descriptions state this explicitly — don't skip it under time pressure.
- **Full `pytest -x`/`-sw` is being deliberately deferred** until all sessions in `plan-fix.md` are done, per the user's explicit ask (expensive full regression). Within a session, use the fast/targeted-subset gate (`regression=pending` per CLAUDE.md's narrowed Backstop scope) to iterate; don't run the full suite per-session.

### Test execution convention — batch scenario setups per live `syncAll()` sweep (decided 2026-08-01)

**For any `[TST]` work in Session 3 onward, new live-backend test files/cases should
default to this shape unless there's a specific reason not to** (documented below).
This is the project's own "permutation batching" testing principle
(CLAUDE.md → DevStandard `sdlc-testing-principles.md`, `T1`-`T24`/`I1`-`I11`)
applied to `syncAll()` specifically, and `scn/engine.py`'s `CheckpointEngine` +
expectation-queue design already supports it.

**Why:** the dominant cost of a live `syncAll()`-driven test is the sweep itself
(crawling Drive/Sheets/Docs), not assertion logic. Sessions 1/2 added new tests
following the file's existing one-scenario-per-test-with-its-own-`syncAll()`
convention — each new test costs ~1-2 min. Batching N independent scenarios'
setup, running **one** `syncAll()`, then asserting each scenario's expected
outcome from that single sweep turns N sync round-trips into 1.

**Shape:**
1. Build up all N scenario docs/folders/rows first (each still gets its own
   isolated doc/folder per the project's run-isolated-clones principle — only
   the *sync sweep* is shared, not scenario state).
2. Run exactly one `syncAll()` (or `sync_all` fixture call).
3. Assert each scenario's expected post-sync state independently — keep
   per-scenario assertions fully separated (already how expectation-queues/
   checkpoints work) so a failure names which scenario broke, not just "the
   batch failed."

**When NOT to batch (do one-scenario-per-sync instead, as Sessions 1/2 did):**
- Scenarios need `syncAll()` fired at *different points* relative to their own
  setup (e.g. "before 24h threshold" vs "after 24h threshold", or a
  multi-sweep sequencing scenario like Session 1's UpdateDoc-override
  confound — two sweeps at different times, not independent state ready for
  one shared sweep).
- The scenario under test is specifically about `syncAll()`'s own
  idempotency/race behavior across *multiple* sweeps (Session 4's gts-li3g
  concurrency-lock test is inherently multi-sweep by design, not a batching
  candidate).
- Fewer than ~3 scenarios in the batch — the setup/assertion bookkeeping
  overhead isn't worth it below that.

**Not retrofitted onto Sessions 1/2's already-written tests** — that would
waste completed work for marginal gain on a handful of tests. Tracked instead
as a standalone follow-up: gts-ir1f.

### Cross-cutting themes across the 40 issues

- **Live data-loss cluster** (P0/P1, 2026-07-26/27 user reports): Shared Drive doc-not-found (gts-rskf), team-folder-move staleness (gts-b6dm), soft-return absorption (gts-jxrw), status-token trailing text (gts-v0py), missing-docState false-deletion (gts-aiaz), duplicate globalId rows (gts-binf). All trace to the same syncAll/sync_action_rows/floating-action-parser machinery — recently very active, high blast radius, most urgent.
- **kkm7 epic**: pure performance refactor (batch Drive/webapp calls), 4 tightly-coupled sub-issues (3 IMP + 1 TST), independent of the data-loss cluster but touches the same `syncAll`/`syncDocument` code paths — sequencing after the data-loss fixes land avoids rebasing batched code on top of correctness fixes mid-flight.
- **Test/harness reliability cluster**: several P2/P3 issues are about the test harness lying (false timeouts, noisy `.error` tags, stale mocks) rather than the product being broken — worth a dedicated pass so future debugging sessions don't re-chase these ghosts.
- **Feature backlog** (inline formatting, configFormat sampling, assignee autocomplete, tracker perf, add-on naming): lower urgency, no user-reported breakage, can trail the bug-fix sessions.
