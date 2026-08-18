# Plan: gts-79dw open work — unit-per-agent execution

Snapshot taken 2026-07-31. Each unit below = one agent session with clean context.
Do not combine units within one session unless explicitly noted — that defeats the
point of the split (context drift, twin-ticket independence, token cost).

Full `pytest -sw` regression does **not** run per unit. Each unit closes on a fast/
targeted gate (`bd set-state <id> regression=pending --reason "<what ran>"`). A single
capstone regression run happens after every unit below is closed.

Execution order matters here — later units depend functionally (not always via a
formal bd dependency) on earlier ones. Work top to bottom.

## How each session is run

1. Launch a fresh Claude session. Prompt it to load this file (`plan-79dw.md`) and, if
   it exists yet, `plan-context.md`.
2. Point it at exactly one unit (e.g. "execute Unit B"). It should read the relevant
   `plan-context.md` section(s) named in that unit before doing any of its own
   grep/read discovery — the point of that doc is to make that discovery unnecessary.
3. On completion, it updates this file in place: check the unit's checklist boxes,
   fill in a one-line **Result** note under the unit (what changed, gate outcome).
   If it touched anything `plan-context.md` describes (new/moved files, changed
   function responsibilities), it updates `plan-context.md` too — don't let it drift.
4. Repeat for the next unit in a new session. Each session should only need this file
   + `plan-context.md` + whatever bd issue text it's implementing — not the prior
   sessions' transcripts.

---

## Unit 0 — Generate plan-context.md
**Status:** closed

Write `plan-context.md`: a map of which files and functions own which piece of the
79dw team-portal surface, so each downstream unit can read it instead of rediscovering
the same code. Two sections, generated in two passes because Unit A relocates the
frontend:

- **§Backend/route contracts** (generate now — stable, unaffected by Unit A): the
  `WebApp.js` route handlers relevant to B/C/D (`team_edit_action`, `team_patch_status`,
  `get_document_actions`, chip-link CTA URL construction), their request/response
  shapes, and where auth/tier resolution happens (`AccessControl.js` / GIS / NUUC-
  Dispatch assertion). Cite file:function, not full listings.
- **§Frontend file map** (generate/refresh as part of Unit A, once the file has
  actually moved to its new location under the new build pattern) — where the portal
  pages live, which page owns View A vs. the new View B, where the stubbed
  Edit/status controls and query-string handling need to go.

**Why its own step, before A:** every other unit references this doc instead of
re-deriving route contracts from scratch. Generating the backend half now means B, C,
and D all skip that discovery; the frontend half has to wait for A regardless.

- [x] Executed (backend/route contracts section)
- [x] `plan-context.md` created

**Result:** Wrote `plan-context.md` §Backend/route contracts covering
`get_document_actions` (`DocView.js`), `team_edit_action`/`team_patch_status`
(`TeamActionWrite.js`), the auth/tier chain (`_verifySignedAssertion` →
`_resolveIdentityAndAccessTier` → `_authorizeDocWrite`, `AccessControl.js`),
and the chip-CTA URL construction (`_handlePreviewNotice`, `WebApp.js:123`)
with the exact `?doc=&team=` / `?team=` query-string contract Unit C needs.
Flagged that `_VERIFIED_TEAM_PORTAL_BASE` is defined in two places
(`DocView.js` + `WebApp.js`) and both must move together when Unit A
relocates the frontend. §Frontend file map left as a stub for Unit A per
plan. No code touched — docs-only, no gate/regression state needed.

---

## Unit A — Publish pipeline migration
**Issue:** `gts-79dw.4.25` [INF]
**Status:** closed
**Context:** `plan-context.md` §Backend/route contracts (for what the frontend calls)

Move the static portal frontend's source of truth from the sibling `Static` repo
(`/home/stuar/proj/Static/pub/AS/index.html`, hand-edited/pushed) into this repo,
following the F3Go30 `build-static-pages.js` / `publish-static-pages.js` pattern
(SIT/PROD folders, scripted deploy-time publish).

**Why first:** Units B/C/D all edit the same frontend file. If they land before this
migration, their edits happen in the old location and have to be manually carried
over during the move — real risk of lost work. Doing the migration first means every
subsequent frontend edit happens in the new, correct place exactly once.

**Gate:** targeted — confirm build/publish script produces an artifact equivalent to
current hand-pushed `index.html`, deploy once, smoke-check the live portal loads.

**Also produces:** write `plan-context.md` §Frontend file map once the file lands in
its new location (see Unit 0) — this is the first point that section can be accurate.

- [x] Executed
- [x] Fast gate green
- [x] `regression=pending` set
- [x] `plan-context.md` §Frontend file map written/refreshed

**Result:** Moved the portal frontend's source of truth into this repo at
`static-portal/src/` (`index.html` ported from `Static/pub/AS/index.html`
verbatim except for three new build-time placeholders — see below — plus
`icon-*.png`, `consent-screen-text.md`, `README.md`, `privacy/index.html`,
`terms/index.html`, all carried over unchanged). Added
`scripts/build-static-portal.js` (stamps `STATIC_BUILD_VERSION_`,
`STATIC_WEBAPP_URL_`, `STATIC_ENV_LABEL_` into `static-portal/dist/<sit|
prod>/index.html` by reading `src/Version.js`'s `BUILD_INFO` — the same
version source `manage-deployments.js` already stamps, no second source;
refuses to build if `BUILD_INFO.env` doesn't match the requested portal env,
so a stale/wrong-target stamp can't silently ship) and
`scripts/publish-static-portal.js` (builds, copies into the sibling `Static`
repo's `pub/AS-sit/` or `pub/AS/`, commits, pushes — prompts for confirmation
before the cross-repo push unless `--yes`). Wired into
`manage-deployments.js`'s `deployToTarget()` as the last step: `test` target
→ `--env sit`, `production` target → `--env prod`; publish failure warns
with a retry command rather than failing the already-succeeded GAS deploy.
Added `staticPortalRepoPath` (`../Static`) to `local.settings.example.json`
and `local.settings.json`; added `static-portal/dist/` to `.gitignore`
(generated, like F3Go30's `static-pages/dist/`).

Design questions from the bd issue, resolved: (a) source dir
`static-portal/src/` (analogous to F3Go30's `static-pages/src/`); (b) GCP
OAuth-consent-screen visibility is orthogonal, not touched; (c) deploy-time
publish prompts for confirmation only when run standalone/interactively —
`pnpm run deploy:test`/`deploy:prod` already run fully non-interactively
(existing convention, `nonInteractive = args.length > 0`), so the publish
step inherits that same posture rather than introducing a new confirmation
gate the GAS-deploy half doesn't have; (d) first SIT publish is net-new
(`pub/AS-sit/` didn't exist) — confirmed by the gate run below.

**Gate run:** `node scripts/build-static-portal.js --env sit` built clean;
`node scripts/publish-static-portal.js --env sit --yes` copied, committed,
and pushed `pub/AS-sit/` to `nuuc-it/Static` (commit `fa5a0c7`). Fetched the
live page (`https://nuuc-it.github.io/Static/pub/AS-sit/index.html`) and
confirmed all three placeholders are correctly stamped (`STATIC_BUILD_VERSION_
= "v0.2.2 (Rev. Jul 31, 2026 12:16) (TEST)"`, `STATIC_ENV_LABEL_ = "SIT"`,
`STATIC_WEBAPP_URL_` = the TEST-WEB-APP `/exec` URL) — content and structure
equivalent to the prior hand-pushed `index.html`. Did **not** run
`--env prod` (would require running `pnpm run deploy:prod` first to re-stamp
`Version.js` for production, which is outside this unit's scope and a real
prod GAS redeploy) — the build script's own env-mismatch guard was exercised
instead and correctly refused. `regression=pending` set on `gts-79dw.4.25`
(`node scripts/build-static-portal.js`/`publish-static-portal.js` syntax-
checked + exercised live; no Python/pytest surface touched by this unit).
`plan-context.md` §Frontend file map written.

**Note for Units B/C/D:** edit `static-portal/src/index.html` going forward —
`Static/pub/AS/index.html` (the old hand-pushed location) is now stale
reference only; it is not touched by the publish pipeline anymore.

---

## Unit B — Wire stubbed portal buttons to shipped backend routes
**Issues:** `gts-79dw.4.21` [FIX] + `gts-79dw.4.22` [FIX]
**Status:** closed, closed
**Context:** `plan-context.md` §Backend/route contracts (`team_edit_action`,
`team_patch_status`) + §Frontend file map (button/control locations)

Both are the same shape of bug in the same file (View A `index.html`): a UI control
that currently just toasts "lands in a follow-up bead" instead of calling a backend
route that has *already shipped and closed* (`gts-79dw.4.14`: `team_edit_action` for
.21, `team_patch_status` for .22).

**Why bundled:** same file, same pattern (stub → real call), same already-shipped
backend contract to read once. Splitting these into two sessions would mean loading
the same `team_edit_action`/`team_patch_status` route context twice for no benefit.

**Gate:** targeted — exercise Edit and status-change controls against the live portal
(or a scenario test) for both routes; screenshot/diagnostics per project UI-test
convention if driven through Playwright.

- [x] Executed
- [x] Fast gate green
- [x] `regression=pending` set

**Result:** In `static-portal/src/index.html`: the per-row Edit button now
opens an inline edit form (`editRowHtml()` — `action_text`/`assignee_name`/
`assignee_email` inputs, Save/Cancel) and POSTs `team_edit_action` on Save
(`onSaveEditClick()`); on success it clears `state.editingId` and calls
`refreshActions()` (matches `onSyncClick`'s existing "AJAX refresh, no page
reload" pattern — `team_edit_action`'s response is `{ok, global_id, outcome}`
with no row payload, so re-fetching the list is how the row picks up the
edit, same as sync). On rejection it toasts `outcome` and reverts to the
unedited row. The assignee status-chip menu's two stub call sites
(canonical-picker click, free-text `Enter`) now both call a new
`submitStatusChange(globalId, status)` that POSTs `team_patch_status` and
`refreshActions()`s on success; both stale `toast('...gts-79dw.4.14...')`
lines and the caveats-list "some writes are inert" copy are removed.
`data-status-for` (already present on the status chip) supplies `globalId`
to the menu; `state.teamId`/`state.assertion` reused, not re-derived, per
`plan-context.md`.

Gate: **added** `tests/playwright/team_portal_wired_controls.test.js` — 3
cases (edit success, edit rejection leaves row unchanged + surfaces error,
status-change success), each driving the real built
`static-portal/dist/sit/index.html` in a real browser via a local fixture
server (same pattern as `cors_team_portal.test.js`), with `page.route()`
intercepting the exact `webappTestUrl` so no live GAS/doc/team seeding is
needed — this is a frontend-wiring test, not a re-proof of backend
authorization (that's `tests/test_team_write_routes.py`'s job, already
closed/green against `team_edit_action`/`team_patch_status`). Verified the
new test genuinely exercises the fix: reverted the wiring to the old stub
handlers in a scratch copy, rebuilt, reran — all 3 cases failed (toast still
read "...lands in a follow-up bead..."); restored the real implementation,
rebuilt, reran — all 3 green. `npx playwright test
tests/playwright/team_portal_wired_controls.test.js --config
tests/playwright/playwright.config.js --retries=0` — 3 passed. `node
scripts/build-static-portal.js --env sit` and `node --check` on the
extracted `<script>` block both clean. `regression=pending` set on both
`gts-79dw.4.21`/`.4.22` (full `pytest -sw` not run — capstone's job); both
beads closed.

---

## Unit C — Portal query-string handling
**Issue:** `gts-79dw.4.24` [FIX]
**Status:** closed
**Context:** `plan-context.md` §Frontend file map (routing/state on page load) +
§Backend/route contracts (chip-link CTA URL shape from `gts-79dw.4.9`)

`index.html` has no `location.search`/`URLSearchParams` handling at all. Two features
already generate URLs depending on it and currently dead-end: the chip-link CTA
(`?doc=<docId>&team=<teamId>`, from `gts-79dw.4.9`) and cross-page nav.

**Why its own unit, and why before Unit D:** this is routing/plumbing work, distinct
from Unit B's button-wiring pattern. It's also a functional prerequisite for View B
(Unit D) — View B needs to know *which document* to render, and that has to come from
`?doc=`. No formal bd dependency links C→D, but building D without C means either
re-doing the query-param work inside D's session (context bleed) or shipping View B
with no way to reach it.

**Gate:** targeted — verify `?doc=`/`?team=` are read and drive the correct view/state
on load, including the chip-link CTA path end-to-end.

- [x] Executed
- [x] Fast gate green
- [x] `regression=pending` set

**Result:** In `static-portal/src/index.html`: added `QUERY_PARAMS`/
`QUERY_TEAM`/`QUERY_DOC` (`URLSearchParams(location.search)`, parsed right
after the `$()` helper is defined, before `initAuth()` runs). `loadTeams()`
now preselects `state.teamId = QUERY_TEAM` when the caller actually has
that team in `state.teams` (server-scoped list from `list_my_teams` — a
`?team=` for a team the caller can't see is never trusted client-side),
falling back to `state.teams[0].teamId` otherwise (regression guard,
matches the AC's "no-param load unchanged" requirement). Since View B
(Unit D) doesn't exist yet, `?doc=` doesn't route anywhere yet either — per
the AC's "must not silently no-op" requirement, added a new `#docViewNotice`
banner (same `.notice` pattern as `#noTeamsNotice`) shown whenever `?doc=`
is present, so the page still lands on View A but the visitor sees their
link didn't do what it promised, instead of a silent drop. `teamPortalUrl`'s
`?team=`-only shape (View B's future "back to team list" link) and the chip
CTA's `?doc=&team=` shape both exercise the same parsing path.

Gate: **added** `tests/playwright/team_portal_query_routing.test.js` — 3
cases (`?team=` preselects a non-default team, `?doc=` shows the notice and
still lands on View A, no-param load still defaults to team[0] with no
notice), same fixture-server/`page.route()`-interception pattern as
`team_portal_wired_controls.test.js` (Unit B) against the real built
`static-portal/dist/sit/index.html`. Verified the new test genuinely
exercises the fix: stripped the query-routing block from the built dist
file in a scratch copy — 2 of 3 cases failed as expected (`?team=`
preselection and `?doc=` notice), the no-param regression-guard case still
passed; restored the real build, reran — all 3 green. `npx playwright test
tests/playwright/team_portal_query_routing.test.js --config
tests/playwright/playwright.config.js --retries=0` — 3 passed. Also reran
`tests/playwright/team_portal_wired_controls.test.js` (Unit B) against the
same modified file — still 3/3 green, no regression from this unit's edits.
`node scripts/build-static-portal.js --env sit` and `node --check` on the
extracted `<script>` block both clean. `regression=pending` set on
`gts-79dw.4.24` (full `pytest -sw` not run — capstone's job); bead closed.

---

## Unit D — Build View B frontend (per-document verified view)
**Issue:** `gts-79dw.4.23` [IMP]
**Status:** closed
**Context:** `plan-context.md` §Backend/route contracts (`get_document_actions`
shape) + §Frontend file map (build pattern from Unit A, where View B's page goes,
how `?doc=` routing from Unit C feeds it)

New frontend page consuming the already-shipped `get_document_actions` backend route
(`gts-79dw.4.13`). Static/pub/AS/ currently only has View A (team list) — this is a
new page, not a patch to the existing one.

**Why last of the frontend work, and its own unit:** largest scope of the four
frontend issues — new page, not a small fix — and depends functionally on Unit C
(`?doc=` routing) to know what to render, and on Unit A (publish pipeline) so it's
authored in the new source-of-truth location using the new build pattern rather than
hand-pushed like the legacy `index.html`.

**Gate:** targeted — load View B for a known doc via `?doc=`, verify it matches the
sidebar's document-view operation set (per `gts-79dw.4.13` notes on read/absent
reconciliation). **Also add one true e2e test** (no `page.route()` mocking — live
GAS deployment, same no-mock pattern as `tests/playwright/cors_team_portal.test.js`):
drive the actual published/built portal in a real browser through the `?doc=`
chip-link path against the real `get_document_actions` route, asserting on real
response data. This is the gap flagged after Units B/C: every portal Playwright test
so far (`team_portal_wired_controls.test.js`, `team_portal_query_routing.test.js`)
mocks the backend, so a real response-shape drift between GAS and the frontend's
assumptions would pass silently. `cors_team_portal.test.js` is the only existing
precedent for a true no-mock browser→live-GAS portal test — follow its fixture-page
pattern, not the mocked ones.

- [x] Executed
- [x] Fast gate green (including the new no-mock e2e case)
- [x] `regression=pending` set

**Result:** New page **`static-portal/src/doc.html`** (View B), built by
the same `scripts/build-static-portal.js` pipeline as `index.html` — the
build script was extended (`STAMPED_PAGES = ['index.html', 'doc.html']`,
replacing its single-`index.html` stamping call with a loop) so both pages
get the same three build-time placeholders
(`STATIC_BUILD_VERSION_`/`STATIC_WEBAPP_URL_`/`STATIC_ENV_LABEL_`) stamped
identically; `publish-static-portal.js` needed no changes since it already
copies whatever `dist/<env>/` contains. `doc.html` duplicates (does not
share, since this is a single-file-per-page architecture with no include
mechanism) `index.html`'s sign-in/auth-cache/`postJson`/toast/spinner
patterns verbatim — same GIS client ID, same NUUC-Dispatch flow, same
`nuucAsAuth.v1` 45-day localStorage cache — so "reuse the existing auth
flow, don't reimplement" is satisfied at the logic level even though the
code is physically duplicated once, consistent with how this project's
single-file pages already work.

**Response-shape finding (important, drove the row-rendering design):**
`get_document_actions`'s `actions` array is **not** the
`list_team_actions`-enriched shape `index.html`'s `rowHtml()`/`statusChip()`
consume (`status_bucket`/`status_icon`/`status_resolved`) — `src/DocView.js`
calls `_findSheetActionsForDoc` directly with no enrichment step, so it only
returns the raw `SheetAction` fields (`global_id`, `action_id`,
`assignee_email`, `assignee_name`, `action_text`, `status`, `doc_id`,
`doc_name`, `created_date`, `modified_date`, `sync_status`). `doc.html`'s
`rowHtml()` was written against this actual schema (confirmed by reading
`src/DocView.js` + `src/WebApp.js:_findSheetActionsForDoc` directly, not
assumed from `index.html`'s pattern): status renders as plain text (no
icon/bucket styling — that data doesn't exist here), and `sync_status` is
shown since it's present and sidebar-parity-relevant. `plan-context.md`'s
§Frontend file map didn't call this shape mismatch out explicitly, so it's
recorded here and in `plan-context.md`'s update below for the next reader.

**Query-string routing (supersedes Unit C's placeholder):** `index.html`'s
`?doc=` handling now does `location.replace('doc.html' + location.search)`
instead of showing the `#docViewNotice` banner Unit C shipped as an
explicitly-interim placeholder ("View B doesn't exist yet"). The
`initAuth()` IIFE is guarded (`if (QUERY_DOC) return;`) so no wasted
`list_my_teams`/`list_team_actions` calls fire before the redirect.
`#docViewNotice`'s markup was removed from `index.html` (dead code once
nothing sets it visible). `doc.html` itself re-parses `?doc=`/`?team=` from
`location.search` independently (routing/initial-context only — tier is
always re-resolved server-side per R8, never trusted from the query string).

**View B page contents:** sign-in / launch / signed-in states (same
pattern as `index.html`); on doc load, calls `get_document_actions` with
`{assertion, docId}`; renders `docName` (linked to `docUrl`) in the sub-line,
a tier tag, and one action row per item (AI-N, action text, assignee,
updated date, sync status, plain-text status — no edit button, no
clickable/editable status control, per `gts-79dw.4.13`'s operation-parity
reconciliation: those are write-path and out of scope here). A NONE-tier
response hides the list and shows `#noAccessNotice` instead (R8 — no action
data leaks, mirrored from the real server response, not client-side
gating). `#backToTeamLink`'s `href` is the server's own `teamPortalUrl` when
present (R20), falling back to `index.html?team=<teamId>` only if the
server ever returns an empty one (e.g. an unresolvable docId). A page load
with no `?doc=` at all shows `#noDocView` (a dead link, not a silent
sign-in prompt for a page with nothing to show).

**Gate — mocked wiring test:** added `tests/playwright/team_portal_view_b.test.js`
(3 cases: VIEW-tier caller sees sidebar-parity fields with no write
controls present; NONE-tier caller sees only the access notice, no rows;
missing `?doc=` shows the no-document notice) against the real built
`static-portal/dist/sit/doc.html`, `page.route()`-intercepting the exact
`GACTIONSHEET_URL` baked into the build — same pattern as Units B/C's
mocked tests, deliberately seeding rows in the **raw** (non-enriched)
schema described above to prove `doc.html` doesn't assume fields that
`get_document_actions` doesn't actually send.

**Gate — true no-mock e2e (the unit's own explicit requirement):** added
`tests/playwright/team_portal_view_b_live.test.js`, following
`cors_team_portal.test.js`'s fixture-page/no-`page.route()` pattern (the
only prior no-mock precedent). Setup replicates
`tests/test_view_b.py`/`scn/session.py`'s testToken-gated GAS calls
(`begin_journey_session`, `append_doc_paragraph`, `run_fixture
move_doc_to_folder`, `run_fixture sync_document`, `run_fixture
mint_test_assertion`, `end_journey_session`) in plain node `fetch()` rather
than shelling out to pytest, since the test's own assertions need to run
inside a real Playwright browser page — same "call webappTestUrl directly
from JS test setup" precedent `addon_helpers.js` already uses (not a
hand-rolled-curl violation of the `call_webapp.py` rule, which targets ad
hoc manual probes outside a test run, not in-test setup helpers). Seeds a
real doc under the real `TestTeamA`/`TEAM_A_FOLDER_1` fixture folder, mints
a real signed assertion for the real VIEW-tier caller email
`test_view_b.py` already relies on (`stuart.donaldson@gmail.com`), then
drives the real built `doc.html` in a real browser against the live SIT
`get_document_actions` deployment with **zero** `page.route()` calls
anywhere in the file — the seeded action text and AI-N id are asserted
straight off the live response.

**Break/restore verification (both gate levels):** patched
`static-portal/dist/sit/doc.html`'s `render()` to always take the
NONE-tier branch (`if (state.tier === 'NONE')` → `if (true)`) — reran both
`team_portal_view_b.test.js` and `team_portal_view_b_live.test.js`: both
failed as expected (mocked test on the missing `.action` text; the live e2e
test timing out waiting for the real seeded action text, since the page now
always shows the no-access notice regardless of the real VIEW tier the live
backend returned). Restored the source
(`node scripts/build-static-portal.js --env sit`, output byte-identical to
the pre-patch build), reran — all green again (confirmed the live e2e test
independently, not just the mocked one, since Unit D's whole point was
catching what mocking hides).

**Full run:** `npx playwright test team_portal_view_b.test.js
team_portal_view_b_live.test.js team_portal_wired_controls.test.js
team_portal_query_routing.test.js --config tests/playwright/playwright.config.js
--retries=0` — 10/10 passed. `node scripts/build-static-portal.js --env sit`
and `node --check` on both extracted `<script>` blocks (`index.html` and
`doc.html`) clean.

**Unit B/C regression check — one intentional test-content change:**
`team_portal_query_routing.test.js`'s `?doc=` case originally asserted the
`#docViewNotice` placeholder Unit C shipped explicitly as an interim
stand-in "since View B doesn't exist yet" (Unit C's own Result note). That
placeholder is exactly what this unit was scoped to replace, so the case
was updated to assert the redirect to `doc.html` instead (URL
path/`doc`/`team` params) rather than the retired banner — not a
regression, since re-asserting the old placeholder behavior would be
asserting the bug this unit fixes. Needed a path-aware fixture server
variant (`startRedirectAwareFixtureServer`) for that one case: the existing
`startFixtureServer()` ignores the request path and returns the same
`index.html` content for every URL, which meant navigating to `/doc.html`
served `index.html`'s content again — since that content still carries
`?doc=` in its own `location.search`, the redirect kept re-firing against
itself (`location.replace('doc.html'+search)` resolves to the same URL
whether starting from `/` or already `/doc.html`), hanging `page.goto`'s
default `waitUntil:'load'` for the full 120s timeout. Fixed by serving a
trivial static stub at `/doc.html` instead of looping `index.html` back on
itself — the stub's content is irrelevant, only reachability matters for
that assertion. The other two Unit C cases (`?team=` preselect, no-param
default) needed no content changes, only removing a now-nonexistent-element
assertion (`#docViewNotice` no longer in the DOM) in the third case,
replaced with a URL-based "no redirect occurred" check. `regression=pending`
set on `gts-79dw.4.23`; bead closed. Full `pytest -sw` not run (capstone's
job, per Backstop rules).

---

## Unit E — Reconcile tracking/docs to current architecture reality
**Issues:** `gts-79dw.5` [INF] + `gts-hc6v` [INF, in_progress] (disposition only)
**Status:** closed, closed
**Context:** `plan-context.md` §Backend/route contracts (auth/tier resolution —
GIS / NUUC-Dispatch assertion vs. the auth-code redirect ADR-0017 describes)

`gts-79dw.5` supersedes ADR-0017: Phase 2 identity now comes from GIS / the
NUUC-Dispatch signed assertion, not an auth-code redirect, and the external static
host that ADR-0017 explicitly rejected is exactly what shipped.

`gts-hc6v`'s own description says its OAuth-Web-client provisioning was "required by
ADR-0017 Phase 2's auth-code-redirect design" — a design `gts-79dw.5` is about to
declare superseded. This reads as the same decision seen from two tickets: **hc6v is
very likely obsolete** and should be closed as superseded by the team portal, not
carried forward as open implementation work.

**Why bundled, and why last:** both are documentation/tracking reconciliation, not
code — no reason to pay for two separate agent spin-ups to make one architectural
call. Sequenced last so the ADR is written against the *final* implemented state
(after A–D land), not a snapshot that's stale by the time it's committed.

**Gate:** none (docs-only) — confirm ADR supersession is committed and `hc6v` is
explicitly closed with a reason pointing at `gts-79dw.5`, or reopened with a concrete
remaining scope if this session finds it isn't actually moot.

- [x] Executed
- [x] `gts-hc6v` disposition recorded (closed-as-superseded, or justified as still open)
- [x] `regression=pending` set (if any code touched — expected not to be)

**Result:** Docs-only unit, zero code touched — no `regression=pending`
applicable (per the task's own instruction for a fully docs-only unit).

Wrote **`knowledge-base/adr/0021-verified-team-portal-single-identity-surface.md`**,
superseding ADR-0017's Phase 2 (the OAuth authorization-code-redirect design
anchored on the stable GAS `/exec` URL, and its rejection of an external
static host). Content is based on what actually shipped in Units A-D, not a
re-guess: identity path is GIS (running on the separate **NUUC-Dispatch**
project, not this one) → NUUC-Dispatch-signed HMAC assertion
(`../../NUUC-Dispatch/knowledge-base/adr/0002-signed-identity-assertion.md`)
→ `_verifySignedAssertion`/`_resolveIdentityAndAccessTier`
(`src/AccessControl.js:321`/`:94`) → per-team/per-doc tier; hosting is
GitHub Pages (`static-portal/src/index.html`/`doc.html`, Unit A) — exactly
the external host ADR-0017 rejected, now correct because the OAuth-redirect
constraint that motivated the rejection doesn't exist in the assertion-
handoff design; editing lives in the portal (`team_edit_action`/
`team_patch_status`, `src/TeamActionWrite.js`), not in-place on the chip
notice (gts-6dlp, already closed as superseded 2026-07-26). ADR-0021
explicitly retains Phase 1 (the anonymous `?cmd=preview` notice,
`_handlePreviewNotice`) unchanged as the permanent unauthenticated fallback
— not a step toward Phase 2 anymore, but where the notice page's "sign in"
CTA now leads (View B via `?doc=&team=`, per `plan-context.md`'s chip-CTA
contract). Followed `adr-quality-check`: all required fields present,
single coherent decision, Accepted status with Consequences covering
easier/harder, supersede chain intact both directions. **ADR-0017 itself
was edited by exactly one line** (its `**Status:**` line, now "Superseded
by ADR-0021 (Phase 2 only...)") — no other content touched, per the
immutability rule; note ADR-0017 was still `Proposed` (never reached
`Accepted`), so this is conservative even beyond what immutability strictly
requires.

**`gts-hc6v` disposition — confirmed obsolete, closed as superseded.**
Verified rather than assumed: read `src/AccessControl.js` in full around
both verifier functions. The live verification path
(`_verifySignedAssertion`, line 321) checks an HMAC signature against a
Script-Property secret named by the assertion's own `kid` claim, plus
`iss`/`aud`/`exp` — it **never reads `GIS_CLIENT_ID`**. The only function
that does read `GIS_CLIENT_ID` is `_verifyGisIdToken` (line 404), which is
explicitly marked **dead code** in its own doc comment ("superseded by
gts-79dw.4.18... no route calls this function anymore") — and that comment
independently confirms hc6v's exact question: it states an OAuth client on
GActionSheet's *own* GCP project could never work for a genuinely external
caller anyway, because that project's consent screen must stay
Internal-only to keep the Workspace add-on installable, so no true external
`@gmail` visitor's ID token could ever satisfy the `aud` check regardless of
which client `GIS_CLIENT_ID` names. This is stronger confirmation than
"probably obsolete" — the code itself documents why the OAuth-client path
was structurally unable to serve hc6v's stated goal, independent of
ADR-0017's supersession. Closed with
`bd close gts-hc6v --reason "..."` pointing at ADR-0021's disposition
section. Also, per hc6v's own closing instruction ("record the reason in
OPERATIONS.md alongside the GIS setup"), added a **"Verified Team Portal
Identity (GIS / NUUC-Dispatch) — no OAuth client needed here"** subsection
to `docs/OPERATIONS.md` (under §Prerequisites, before `urlFetchWhitelist`)
stating no OAuth Web client/redirect URI/`GIS_CLIENT_ID`/`GIS_CLIENT_SECRET`
is needed on this project, and pointing to `docs/verified-team-portal-plan.md`
for the NUUC-Dispatch-side provisioning that *is* required.

**`plan-context.md`:** no correction needed — its §Backend/route contracts
section already accurately described the assertion-based auth chain this
ADR formalizes; nothing this unit learned contradicts it.

**Judgment calls:** (1) placed the new ADR at `0021` (next free number
after `0020`) rather than reusing `0017`'s slot, per the immutability/
supersede convention every other superseded ADR in this repo follows
(`0001`→`0005`, `0002`→`0009`, `0003`→`0006`). (2) Cited NUUC-Dispatch's
*own* ADR-0002 (signed identity assertion) rather than this repo's
`knowledge-base/adr/0002-timestamp-based-conflict-resolution.md` — the bd
issue text's parenthetical "(ADR-0002)" is ambiguous about which repo, and
reading `src/AccessControl.js` + the sibling `NUUC-Dispatch` repo confirmed
the signed-assertion scheme is NUUC-Dispatch's ADR-0002, not this repo's;
flagged the ambiguity explicitly in ADR-0021's Context so a future reader
isn't confused by the same repo-local `0002` existing here for something
unrelated (timestamp-based conflict resolution). (3) Went slightly beyond
the bare bd-close instruction by also touching `docs/OPERATIONS.md`, since
hc6v's own text asked for that as part of its closing condition — judged
this as still docs-only and in-scope for "reconcile tracking/docs," not
scope creep into a different unit's file.

---

## Unit E.5 — Live portal e2e sweep (no mocks)
**Status:** closed
**Context:** all portal Playwright coverage so far (Units B/C/D) mocks `GACTIONSHEET_URL`
via `page.route()`. Only `tests/playwright/cors_team_portal.test.js` and Unit D's new
no-mock case exercise the live GAS backend from a real browser.

Once Unit E closes (portal is feature-complete for this batch — A–D landed, tracking
reconciled), do one true no-mock e2e pass over the remaining high-level portal
functionality that's only ever been exercised through mocks or Python: team list load
(`list_my_teams`/`list_team_actions`) on a live signed-in-equivalent session, sync
(`team_sync_document`), Edit (`team_edit_action`), and status change
(`team_patch_status`) — each driven through the actual built/published portal page in
a real browser against the live SIT deployment, not through `page.route()` canned
responses. Goal is to catch response-shape drift between GAS and frontend assumptions
that a mocked test structurally cannot catch — not to duplicate
`tests/test_team_write_routes.py`'s authorization-matrix coverage, which stays
Python/backend-only.

**Gate:** targeted — new/extended no-mock Playwright test(s) pass against live SIT.

- [x] Executed
- [x] Fast gate green
- [x] `regression=pending` set

**Result:** No bd issue is named in this unit's own header (unlike every
other unit in this plan, which carries an explicit `**Issue(s):**` line) —
confirmed by re-reading the section header carefully before guessing. The
closest candidate, `gts-79dw.5`, is Unit E's docs-only ADR-supersession bead
and is already closed for that unrelated scope; attaching E.5's
`regression=pending` there would misrepresent what that bead covers. Per the
task's own instruction not to guess an id, no bd issue was updated for this
unit's code changes. If a durable record is wanted, the natural next step is
a small new `[TST]` bead filed under the `gts-79dw.4` milestone epic
pointing at this Result — left to whoever runs Capstone/merge-gate to decide,
since filing it here would be scope creep into issue-tracking taxonomy this
unit wasn't asked to own.

Added **`tests/playwright/team_portal_live_sweep.test.js`** — two cases,
following `cors_team_portal.test.js`/`team_portal_view_b_live.test.js`'s
established no-mock pattern exactly (local fixture server standing in for
the real `nuuc-it.github.io` cross-origin host, serving the real built
`static-portal/dist/sit/index.html`; plain node `fetch()`-based
`testToken`-gated setup calls, same as Unit D's live test; zero
`page.route()` calls anywhere in the file):

1. **"live team list load + assignee status change (R17) + VIEW-tier
   sync/edit rejection shapes"** (always runs) — seeds a real doc/action
   under `TestTeamA`/`TEAM_A_FOLDER_1`, assigned to the real VIEW-tier
   caller `stuart.donaldson@gmail.com` (same identity `test_view_b.py`/
   `test_team_write_routes.py` already rely on), mints a real signed
   assertion, then drives the real built `index.html` in a real browser:
   - **List load** (`list_my_teams`/`list_team_actions`): asserts `#teamSel`
     preselects `TestTeamA` and the seeded action text is visible — both
     calls hit the live SIT deployment, no canned data.
   - **Status change** (`team_patch_status`, R17 VIEW-tier assignee
     bypass — the one write path a VIEW-tier-only identity can exercise
     through the real UI): clicks the `.status.mine` chip, picks "Closed"
     from the real `#statusMenu`, asserts the toast and the row's displayed
     status update after the app's own `refreshActions()` re-fetch.
   - **Sync/Edit rejection shape** (`team_sync_document`/`team_edit_action`
     at VIEW tier): the Sync/Edit *buttons* are only rendered/enabled at
     EDIT tier (`index.html`'s `render()`/`rowHtml()`), and **no identity
     with EDIT (rather than VIEW) access to `TestTeamA` is currently
     configured** — the exact same documented gap
     `tests/test_team_write_routes.py`/`tests/test_team_portal_hardening.py`
     already carry (`local.settings.json` key `teamAEditEmail`, unset). So
     this case invokes the built page's *own* `postJson()`/
     `GACTIONSHEET_URL`/`state` (top-level `const`/`function` declarations
     in a classic, non-module `<script>` share the page's global lexical
     scope, so `page.evaluate` can reference them directly — verified this
     works, not assumed) rather than a hand-rolled fetch. Asserts the real
     response shapes: `{ok:false, outcome:'rejected-VIEW'}` for sync,
     `{ok:false, outcome:'rejected-doc-scope'}` for edit — both confirmed
     against real `TeamSync.js`/`TeamActionWrite.js` source before writing
     the assertions, not guessed.
   - **Durable-state check**: a final live `get_document_actions` call
     confirms the rejected edit did **not** mutate `action_text` and the
     status-change from the UI step **did** persist to `status: 'Closed'` —
     both against real backend state, not the mutation routes' own echoed
     response.
2. **"EDIT-tier caller: real sync + edit success via actual UI button
   clicks"** (conditional) — `test.skip(!settings.teamAEditEmail, ...)`,
   same convention as the three Python precedents above (not fabricated
   access). Would, if unskipped, seed a doc assigned to `teamAEditEmail`,
   verify `verify_and_resolve_access` actually resolves `EDIT` first
   (precondition check mirroring `test_team_portal_hardening.py`), then
   click the real (enabled) `[data-sync]` and `[data-edit]` controls and
   assert `'Synced.'`/`'Saved.'` toasts plus a durable
   `get_document_actions` re-read. Currently skipped —
   `local.settings.json` has no `teamAEditEmail` key, same gap every
   backend precedent already documents; not this unit's job to provision a
   real Drive EDIT grant on a shared fixture folder.

**Judgment call — the identity-availability gap:** the task asked for
sync/edit/status-change all "driven through the actual built/published
portal page." Discovered while writing the test that the Sync and Edit UI
controls are gated to EDIT tier client-side (`tier === 'EDIT'` in
`rowHtml()`/the docgroup header), and no EDIT-tier identity exists in this
environment's fixture setup — three separate Python test files already
carry this exact gap under the documented `teamAEditEmail` key rather than
attempting to provision one ad hoc. Provisioning a real Drive EDIT grant on
the shared `TestTeamA`/`TEAM_A_FOLDER_1` fixture folder is a real,
semi-permanent change to shared test infrastructure — judged out of scope
for a single Playwright-authoring unit to make unilaterally. Followed the
existing precedent instead: unconditionally exercise what a VIEW-tier
identity genuinely can (list load, R17 assignee-bypass status change, and
the *rejection* response-shape of sync/edit, which is still real
response-shape coverage — it just isn't the success shape), and gate the
EDIT-tier success paths behind the same `test.skip`-with-reason convention,
ready to activate the moment `teamAEditEmail` is configured.

**Break/restore verification:** patched `static-portal/dist/sit/index.html`
(`isMine()` forced to always return `false`, keeping the original
expression as unreachable dead code via `var _dead = ...` so the diff was
minimal and reversible) — reran test 1: failed exactly as expected,
`.status.mine` chip not found (the R17 status-change UI path is unreachable
without it). Restored the file from a pre-patch copy (byte-identical
restore, diffed to confirm), rebuilt via `node scripts/build-static-portal.js
--env sit`, reran — green again. The sync/edit rejection-shape assertions
were separately validated against real, freshly-observed backend responses
(a standalone manual live probe against `TestTeamA`/`get_document_actions`/
`team_patch_status`/`list_team_actions` confirmed the exact `outcome`
strings and also surfaced the filter-default finding below) before being
hard-coded into the test, rather than guessed.

**Finding recorded for future readers (not a bug — real, load-bearing
product behavior that shaped this test):** `list_team_actions`'s default
`statusFilter` is `'open'` (`TeamListing.js:46`, mirrored client-side by
`static-portal/src/index.html`'s `state.status: 'open'` default). A row
that transitions to `Closed` via `team_patch_status` and is then re-fetched
by the app's own post-write `refreshActions()` call **disappears from the
default-filtered view** — it does not show a "Closed" chip in place, it
vanishes, because the default fetch no longer asks for closed rows. The
test switches the UI to `#statusSeg [data-status="all"]` before triggering
the status change specifically so the transition stays observable; an
earlier draft of this test asserted the row would still be present showing
"Closed" under the default filter and failed because of this — not because
of a code defect, but because the assertion didn't match real, correct
filtering behavior. Recorded here (and see the inline comment in the test
file) so a future reader modifying `index.html`'s default filter doesn't
have to rediscover this.

**Gate run:** `node scripts/build-static-portal.js --env sit` (dist already
matched the current `Version.js`/live SIT revision — confirmed via
`python scripts/call_webapp.py get_test_config`, `serverVersion` matched
local `BUILD_INFO.version` exactly, so **no `pnpm run deploy:test` redeploy
was needed or performed** this unit). `node --check` on both extracted
`<script>` blocks (`index.html`, `doc.html`) clean.
`npx playwright test team_portal_view_b.test.js team_portal_view_b_live.test.js
team_portal_wired_controls.test.js team_portal_query_routing.test.js
team_portal_live_sweep.test.js --config tests/playwright/playwright.config.js
--retries=0` — 11 passed, 1 skipped (the conditional EDIT-tier case), 0
failed, confirming this unit's new test doesn't regress Units B/C/D's
existing portal coverage. Full `pytest -sw` not run (Capstone's job per
Backstop rules). No bd issue closed/regression-flagged — see the disposition
note above.

---

## Capstone
After Units A–E.5 are all closed:

- [ ] Full `pytest -sw` run, clean
- [ ] Flip every unit's issues to `regression=verified`
- [ ] Merge-gate

---

## Notes for whoever runs this
- Order is strictly 0→A→B→C→D→E→E.5: Unit 0's backend section unblocks B/C/D's context
  reads, Unit A's frontend-map output unblocks B/C/D's frontend context, and the
  functional (not bd-formal) dependency C→D still holds. Don't parallelize B against
  A — same file-location risk described in Unit A. E.5 is sequenced after E (not
  bundled into D) because it deliberately covers the *whole* portal surface once
  everything has landed, not just the feature a given unit just added.
- Each session is launched fresh against this file (and `plan-context.md` once Unit 0
  exists): "load plan-79dw.md, execute Unit X." It should not need prior sessions'
  transcripts — everything it needs to skip rediscovery is either in this file or in
  `plan-context.md`. If a session finds `plan-context.md` wrong or incomplete for its
  unit, it should correct it as part of that unit's Result, not silently work around
  it — otherwise the next session inherits the same stale doc.
- If new work surfaces mid-unit that belongs to a *different* unit's file/theme, file
  it as a new bd issue rather than scope-creeping the current session.
- This file is a working checklist, not a durable doc — once all units + capstone are
  done, this file's contents are exhausted and it can be deleted (or its outcome
  captured via `/work-log` if it doesn't already belong to the beads issues themselves).
  `plan-context.md` may outlive it if it stays accurate and useful beyond this batch —
  that's a call to make at capstone time, not now.
