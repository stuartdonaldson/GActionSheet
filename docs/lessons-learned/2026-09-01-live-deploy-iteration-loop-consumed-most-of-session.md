# LL: live-deploy iteration loop consumed 59% of a feature session

Date: 2026-09-01
Domain: process
Session: 9a56db38-a3e7-411b-b4fa-94cdb3e12e05 (gts-gwyg / gts-s4tr)

## Observation
Implementing `gts-gwyg` (admin scan for untracked action Docs) took 118 minutes wall clock and
475 API calls. Measured breakdown: research + naming + beads 11 min; implementation-gate +
user Q&A 11 min; code authoring 12 min; **deploy/test round trips 70 min (59%)**; wrap-up 14 min.
Eight `pnpm run deploy:test` runs and nine live pytest runs were executed against the TEST
backend for one feature.

Deploys 4, 6 and 8 were three successive attempts to read a Doc's plain text without
`DocumentApp.openById()`:
- deploy 4 — `Drive.Files.export(id, 'text/plain', {alt:'media'})`, threw
- deploy 6 — `Drive.Files.get(id, {fields:'exportLinks'})` + `UrlFetchApp`, threw `GoogleJsonResponseException`
- deploy 8 — reverted to `DocumentApp.openById(id).getBody().getText()`, passed first try

`DocumentApp.openById(...).getBody().getText()` was already the pattern used throughout
`src/SyncManager.js` at the time the alternative was chosen. Deploy 5 was a privacy fix caused
by deploy 4 (see `2026-09-01-exception-message-logged-document-content-to-axiom.md`).

Deploy 2 corrected a response-shape collision: the frozen contract used a top-level `error` key,
which `scn.session.ScenarioSession._http_post` treats as a fatal transport failure for any route.
Sibling route `list_team_actions` already demonstrated the convention in use (`tier:'NONE'`).

At 15:16 a research agent reported that the Team Actions UI is an external static portal
(`static-portal/src/index.html` → `nuuc-it/Static`), not a surface in this repo. The backend was
declared done at 15:44. The client-side gap surfaced at 15:47 when the operator asked "In the
Team actions ui page, I do not see the option to sync or search the folders under it."

## Why Chain

Branch A — unvalidated performance assumption drove three deploy cycles
Why 1 — `_quickMatchActionDoc` was written against Advanced Drive Service export instead of `DocumentApp`.
Why 2 — A design decision ("avoid `DocumentApp` — it opens the full object model and takes an edit lock") was made during implementation and treated as settled without evidence.
Why 3 — No step between contract-freeze and code authoring requires checking how the codebase already answers the same question; the project's I12 prior-art rule has no enforcement point in `implementation-gate`.
Why 4 — In a live-backend project every unvalidated API assumption costs a full deploy+test round trip to disprove, but nothing in the gate prices that cost in before code is written.
Root cause A: `implementation-gate` has no prior-art step — a mid-implementation API or performance decision can diverge from an established codebase pattern with no check, and in a no-local-mock project each such divergence is paid for in deploy cycles rather than at authoring time.

Branch B — contract frozen without diffing the nearest sibling
Why 1 — The frozen contract's `{ok:false, error:'forbidden'}` shape was rejected by the Python test client.
Why 2 — The `error`-key convention of `_http_post` was not consulted when the response schema was written.
Why 3 — The pre-code contract requires entry-point signature, log tag, and output schema, but does not require the schema to be checked against an existing route of the same class.
Root cause B: the pre-code contract has no sibling-route comparison step, so a route can freeze a response shape that a peer route already demonstrates is incompatible with the test harness.

Branch C — implementation surface expanded with no re-gate
Why 1 — Client-side work in `static-portal/src/index.html` was implemented ~30 min after the backend was declared done, in response to an operator question.
Why 2 — The static-portal surface was not in the frozen contract, and was not added when research revealed it.
Why 3 — `implementation-gate` ran once, at 15:03, against a backend-only reading of the bead; nothing re-triggers it when implementation reaches a file outside the surfaces the contract names.
Root cause C: the gate is entry-triggered only — there is no re-entry condition when implementation touches a surface absent from the frozen contract, so scope can expand without the AC, coverage obligations, or estimate being revisited.

## Initial Candidates
- c: `implementation-gate` — add a prior-art step (grep for how the codebase already solves this; record the finding in the bead) before any "avoid the obvious API" decision (Branch A)
- b: project CLAUDE.md — "in a live-backend project, an unproven performance optimisation is a deploy-cycle gamble; take the proven path to green first, optimise after" (Branch A)
- c/d: pre-code contract — add "name the nearest existing sibling route and diff your response shape against it" to the required fields (Branch B)
- c: `implementation-gate` — add a re-entry trigger: implementation touching a file outside the contract's named surfaces re-enters the gate (Branch C)
[Developed fully at resolve phase]
