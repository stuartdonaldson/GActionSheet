# Verified Team Action Portal — Working Plan (spike-gated)

**Status:** Draft / assumptions unproven — **do not propagate to CONTEXT.md, ADRs,
security-architecture.md, or bd epics until Spikes S1 + S2 pass.**
**Date:** 2026-07-21 (terminology + scope correction 2026-07-26 — see §0)
**Owner:** Stuart Donaldson
**Relates to:** ADR-0017 (verified identity for chip-link action editing — *Proposed*),
ADR-0014 (team-scope folder-walk), `docs/security-architecture.md` §1–3,
`../F3Go30/docs/StaticHTMLonGas.md` (static-first-party + GIS pattern this plan adopts).

> **Why this document is standalone.** The architecture here (static first-party page +
> GIS) reverses a decision ADR-0017 currently records (auth-code redirect on `/exec`,
> external host rejected). That reversal rests on assumptions (A1–A8 below) that are
> *plausible but unproven*. We prove them with two throwaway spikes first; only then do we
> revise ADR-0017 / write ADR-0021, update CONTEXT.md, security-architecture.md,
> OPERATIONS.md, and file the milestone bd epic. Editing those now would bake in
> assumptions we might have to unwind.

---

## 0. Terminology and scope correction (2026-07-26)

This plan was originally written around a "board group" and a **board folder id**. That was
wrong on both counts, and the error propagated into route params, filenames, log tags, and
bd descriptions. Corrected here; the rest of this document uses the corrected terms.

**The unit of scope is a TEAM, not a board.** Per ADR-0014, `TeamData` is the authority for
team identity: `Team Id` (e.g. `Board`, `Membership`) → `Folder Id` → `Contact`. **`Board`
is one example value of `Team Id`** — a team, not a distinct concept. There is no "board
group" in the data model. Every occurrence of "board group" in this plan means *team*.

**A team may own more than one folder** (ADR-0014 §1: multiple `TeamData` rows sharing a
`Team Id`). A folder id therefore does **not** identify a team — it identifies a *fraction*
of one. Keying the portal on `boardFolderId` addresses only the documents under one of a
team's folders. **The portal is keyed on `teamId`.**

**No Drive-ancestry walk is needed to resolve the portal's scope.** The sheet model already
answers it directly:

```
docId ──DocData.teamId──►  teamId  ──TeamData rows (1..n)──►  folderId[]   (for ACL checks)
                              └─────DocData.teamId───────────►  docId[]     (for listing)
```

The folder walk (`_walkFolderForTeam`, `src/SyncManager.js`) remains correct and stays —
but only in its ADR-0014 role: **assigning** `teamScope` to a document that does not yet
have one, at sync/register time. It is not a lookup path for an already-tracked document,
and the portal must not call it.

**Access tier resolves across all of a team's folders** (decision 2026-07-26): tier is the
*highest* tier the caller holds on any `TeamData` folder for that team — you see the team's
list if you can see any part of it. **Write is re-checked per document** against the folder
the target document actually lives under, so edit rights on one sub-folder do not confer
write on documents in another. See §4.

**Milestone 1 scope, corrected.** The UI is built as the *complete* team-portal mockup —
including the status/assignee filters and the edit and status-change affordances — with
only the read paths wired (§9). R13 ("read-only") is now a statement about which paths are
*wired* in Milestone 1, not about what the UI shows.

---

## 1. Goal

Two surfaces, one verified-identity gate. A person outside `northlakeuu.org`, on a personal
`@gmail` or external account, gets a web equivalent of what a domain user gets from the
add-on sidebar — without an add-on and without a domain account.

**View A — team action list (primary).** All action items for a team, in one list, with:

- a **status filter**: Open (default) / Closed / All,
- a **scope filter**: mine / all — extensible to *a named person* (future),
- **edit** of an action item, for callers holding EDIT tier,
- **status change** (icon click or typed status), for the person the action is assigned to.

**View B — document view.** The sidebar's per-document action view, delivered over the web,
so an out-of-domain user has the options a sidebar user has. Reached from an `AI-N:` chip.

Both are gated on verified Google identity plus Drive access to the team's folder(s),
directly or via a domain-managed group. A user with write access can also trigger a sync.

Milestone 1 wires **listing + filters + sync**; the edit and status-change paths are built
against an AC frozen at the same review (§9).

---

## 1a. What we already know (references for a cold start)

A fresh context should read these before touching a spike — they are the ground truth this
plan builds on.

- **ADR-0017** (`knowledge-base/adr/0017-chip-link-anonymous-identity.md`) — the decision
  this plan revises. Phase 1 (anonymous notice) is **shipped**; Phase 2 (verified edit) is
  deferred. Records the two-gate rule (authenticate *then* authorize) and the confidential-
  content driver. Validation notes: `knowledge-base/adr/probes/0017-validation.md`.
- **StaticHTMLonGas.md** (`../F3Go30/docs/StaticHTMLonGas.md`) — the transferable playbook
  for the static-first-party + GIS pattern we adopt. Read its last section ("your own
  identity & access control") and the CORS spike (Step 1) + iOS/ITP storage section.
- **docs/security-architecture.md** §1–3 — execution-identity model (add-on runs as user;
  WebApp `doPost`/sync runs as **deployer**, `executeAs: USER_DEPLOYING`), trust
  boundaries, `_getIdentity()` (`eu`=deployer, `au`=caller), and finding **F3** (globalId-
  keyed unauthenticated reads — the same exposure class the chip link has).
- **Existing WebApp surfaces** (`src/WebApp.js`): `doGet`/`doPost` dispatch;
  `_handlePreviewNotice`/`_renderPreviewNotice` (Phase-1 notice, `?cmd=preview`);
  `_renderBrandedPage` (shared branded shell to reuse for spike/portal pages);
  `_handleRegister`/`_handleTeamView` (existing anonymous `doGet` pages — patterns to copy);
  the `WEBAPP_SECRET` gate and the `TEST_TOKEN` test-support gate order.
- **Probe pattern** (`src/PROBE.js`, `PROBE_ENABLED=false`) — the model for the
  `SPIKE_ENABLED` flag that keeps spike routes inert in real deployments.
- **Two-GCP-project split (2026-07-22).** Spike S1 does **not** reuse GActionSheet's existing
  GCP project (`cloud-logging-test-494622`). Two independent constraints force a separate
  project, both documented in `knowledge-base/references/workspace-addon-setup.md`: (1) the
  OAuth consent-screen User Type is project-wide — Internal (Workspace-org-only) and External
  (any Google account) can't coexist, and GActionSheet's add-on install depends on staying
  Internal/private while S1 needs External+Published; (2) the Workspace Marketplace SDK is
  one-per-GCP-project, so a second published surface can't share GActionSheet's project. The
  new project hosts **NUUC-Dispatch** (sibling repo to GActionSheet), a standalone Apps Script
  Web App scoped for now to the S1 identity-verification harness only — not the full
  dispatch-to-other-NUUC-apps design, which stays a future direction, not built. Provisioning
  tracked as `gts-79dw.3` (see §8), separate from `hc6v` (which stays scoped to
  ADR-0017 Phase 2 on the existing project).
- **Team/folder model** — ADR-0014 (folder-walk team scope) and `assertTeamAccess(teamId,
  ss)` (`src/SyncManager.js`) — but note that check probes access **as the deployer**,
  whereas the new spike must test an **arbitrary email's** access (`getAccess(email)`), a
  different mechanism.
- **Deployment** — `pnpm run deploy:test` (never `clasp` directly); manual WebApp calls via
  `python scripts/call_webapp.py`; logs via `python scripts/query_axiom.py` or
  `clasp logs`. (The spike's whole point is the *browser* cross-origin path, so its client
  is the static page, not `call_webapp.py`.)

---

## 2. Assumptions under test

Each spike exists to confirm or refute these. A refuted assumption re-opens the design.

| # | Assumption | Proven by |
|---|-----------|-----------|
| **A1** | GAS `/exec` `doGet`/`doPost` return `Access-Control-Allow-Origin: *` on **both** hops (`/exec` → `script.googleusercontent.com`), so a cross-origin static page can call them with `fetch()`. | S1 |
| **A2** | A static first-party page can run GIS "Sign in with Google" / One Tap and obtain an **ID token** for a personal `@gmail` **and** an external account, using only non-sensitive scopes (`openid email`) — no consent screen, no app-verification wall. | S1 |
| **A3** | The GAS backend (deployer context) can **verify** that ID token server-side (`tokeninfo` endpoint via `UrlFetchApp`, or JWKS/RS256), checking `aud`/`iss`/`exp`, and extract a stable `sub` + verified `email`. | S1 |
| **A4** | `DriveApp.getFolderById(folderId).getAccess(email)` (and `.getFileById(docId)`) run in deployer context returns **effective** access that reflects **group-conferred** access — specifically for an **external member of a domain-managed Google Group** that holds folder access. *(Load-bearing.)* | S2 |
| **A5** | If A4 under-resolves, `AdminDirectory.Members.hasMember(groupKey, externalEmail)` + `Drive.Permissions.list(folderId)` is a reliable fallback for **domain-managed** groups, including their external members. | S2 |
| **A6** | The VIEW/COMMENT vs EDIT/OWNER distinction from `getAccess` is trustworthy enough to gate *view* vs *sync*. | S2 |
| **A7** | `text/plain` POST bodies keep the calls "CORS simple requests" (no `OPTIONS` preflight GAS can't handle). | S1 |
| **A8** | The existing sync path can be invoked from a verified-identity, write-authorized static-origin request without weakening the `WEBAPP_SECRET` production-route model. | Downstream (not S1/S2) |

---

## 3. Requirements (atomic, testable)

**Identity**
- **R1** The portal SHALL require a verified Google identity via GIS (scopes `openid email`; `profile` optional).
- **R2** The backend SHALL verify the ID token server-side (`aud` = our client id, `iss`, `exp`, signature) before returning any team data, keying on `sub`. Fail closed.
- **R8** Action text is confidential and SHALL NOT be exposed to any identity lacking ≥ read access.

**Authorization (team-scoped — evaluated on the team's folders, not the individual document)**
- **R3** Access SHALL be evaluated against the **team's Drive folder(s)** (every `TeamData` row for the `Team Id`), not the individual document.
- **R3a** Read tier SHALL be the **highest** tier the caller holds on **any** of the team's folders.
- **R3b** A write operation on a specific document SHALL be re-authorized against the folder that document resides under, not against the team-wide tier (§4).
- **R4** VIEW/COMMENT access (direct or via a domain-managed group) → read access to the listing.
- **R5** EDIT/OWNER access → additionally authorized to trigger sync and to edit.
- **R6** No resolvable access → deny all team data + non-leaking notice. Default-deny when access cannot be positively confirmed.
- **R7** Group-conferred access SHALL resolve for **external members of a domain-managed Google Group** *(gated by A4/A5)*.

**Listing & filter (View A)**
- **R9** List all tracked actions across every document belonging to the team (`DocData.teamId == teamId`).
- **R10** Default status filter = **Open** actions only. Closed and All SHALL also be selectable.
- **R11** **All** / **Closed** SHALL include resolved actions whose last-update timestamp is within the last **60 days**.
- **R12** The 60-day window SHALL be user-extendable on the page.
- **R13** Milestone 1 **wires** the read paths (listing, filters, sync). Edit and status change are built to the AC frozen at the same review and wired immediately after (R16–R18); the UI renders their affordances from the start.
- **R13a** A **scope filter** SHALL offer *mine* (actions assigned to the verified caller) and *all*. Filtering by an arbitrary named person is a recorded open seam, not Milestone 1.
- **R13b** Rows whose source is gone SHALL be excluded: action `sync_status` of `Deleted`/`Doc Not Found`, **and** actions whose document's `DocData.syncStatus` is `Deleted`/`Doc Not Found`.

**Document view (View B)**
- **R19** A verified caller with ≥ VIEW tier on the document's team SHALL be able to view that single document's actions over the web, presenting the same information and the same available operations as the add-on sidebar's document view.
- **R20** View B SHALL be reachable from an `AI-N:` chip, and SHALL offer navigation to View A for the same team.

**Sync**
- **R14** The page SHALL offer a "Sync this document" action, **write-gated** (R5 + R3b).
- **R15** Sync SHALL reuse the existing deployer-context sync path and log `{eu, au = verified sub/email, docId, outcome}` via GasLogger.

**Edit & status (built in Milestone 1, wired against the frozen AC)**
- **R16** A caller holding EDIT tier on the target document's folder SHALL be able to edit an action item's editable fields, reusing the existing `edit_action_row` core path.
- **R17** The caller **the action is assigned to** SHALL be able to change that action's status, reusing the existing `patch_action_status` core path, whether or not they hold EDIT tier on the folder.
- **R18** Every verified-identity write SHALL log `{eu, au = verified sub/email, global_id, outcome}` and SHALL be rejected before any mutation when unauthorized (no partial execution).

---

## 4. Access-control model (target)

```
Static page (github.io)  ── GIS sign-in ──►  ID token (openid email)
        │
        │  fetch() text/plain POST  (A1, A7)
        ▼
GAS WebApp doPost (executeAs DEPLOYER, ANYONE_ANONYMOUS)
        │  1. verify ID token → sub + verified email             (R2, A3)
        │  2. teamId → TeamData rows → folderId[]                (R3, ADR-0014)
        │  3. tier = MAX over folderId[] of getAccess(email, f)  (R3a, A4)
        │         └─ fallback: Admin SDK group expansion         (A5)
        │  4. read  → VIEW/COMMENT+                              (R4/R6)
        │     write → EDIT/OWNER on THAT DOC's folder            (R3b/R5)
        │              or assignee-identity match for status     (R17)
        ▼
   View A team listing JSON  |  View B doc JSON  |  sync / edit / status
```

- The verified-identity ACL becomes the **entire security boundary** for this surface
  (the backend already runs with the deployer's full authority for every anonymous
  request). Per StaticHTMLonGas.md: default-deny, fail closed, gate on `sub` not `email`,
  concentrate tests here.
- This is **additive** — the existing `WEBAPP_SECRET`/`TEST_TOKEN` routes and the Phase-1
  anonymous notice are untouched.

### 4a. Three auth gates, one set of core functions

The portal is **a third auth gate plus a new UI over existing core functions** — not a new
subsystem. `doPost` already discriminates three caller classes (`src/WebApp.js` dispatch
order, ADR-0012):

| Gate | Credential | Callers |
|------|-----------|---------|
| `WEBAPP_SECRET` | shared secret in payload | the add-on, `SyncManager`'s own sync calls |
| `TEST_TOKEN` | per-deployment test token | the ATDD harness |
| **GIS tier** *(new)* | verified ID token → `_resolveIdentityAndAccessTier` | external verified identities (this portal) |

Below the gate, the operations the portal needs **already exist** as core functions with a
different gate in front of them. The portal MUST reuse them rather than add parallel
implementations (see §11 reuse inventory). New route wrappers are thin: resolve tier, then
delegate.

---

## 5. Spike S1 — Verifiable identity from a static GitHub Pages page

**Question:** Can a static page on a genuinely different origin obtain a verifiable Google
identity for a personal/external account and have GAS verify it? (A1, A2, A3, A7)

**Harness**
- A single static `index.html` published via **GitHub Pages** (`*.github.io` — genuinely
  cross-origin from `script.google.com`; a spike repo or a `gh-pages` branch is fine — a
  dedicated static-only repo is a *later* concern, not needed to prove identity).
- Page renders a GIS "Sign in with Google" button, obtains an **ID token**.
- Page `fetch()`es our WebApp with a `text/plain` body:
  - `doPost` route `spike_verify_identity` → `{ idToken }` → backend verifies via
    `https://oauth2.googleapis.com/tokeninfo?id_token=…` (`UrlFetchApp`), checks
    `aud`/`iss`/`exp`, returns `{ verified, sub, email, email_verified }`.
  - Repeat once via `doGet ?cmd=spike_verify_identity&idToken=…` to confirm **both**
    interfaces work cross-origin (the user asked the spike exercise `doGet` and `doPost`).
- Page displays the returned verified `email`/`sub`.

**Blocking deps (operator, GCP console)**
- A **separate GCP project** from GActionSheet's (`cloud-logging-test-494622`) — see the
  two-GCP-project split note in §1a. This new project hosts the **NUUC-Dispatch** Apps Script
  Web App (sibling repo to GActionSheet).
- OAuth consent screen on the NUUC-Dispatch project: User type **External**, publishing **In
  production**, scopes `openid email` (non-sensitive → no verification/review).
- OAuth 2.0 **Web application** client id in the NUUC-Dispatch GCP project; the
  `nuuc-it.github.io` origin as an Authorized JavaScript origin; client id embedded in
  the static page (`Static/pub/AS/index.html`).
- Spike GAS routes (in NUUC-Dispatch's `src/WebApp.js`) live behind a `SPIKE_ENABLED` flag
  (default `false`, like `PROBE`) so they never expose in a real deployment. Deploy with
  NUUC-Dispatch's own `pnpm run deploy:test`.
- Tracked as `gts-79dw.3` (not `hc6v`, which stays scoped to ADR-0017 Phase 2 on the
  existing GActionSheet project).

**Pass criteria**
- Backend logs and returns a **verified `email` + `sub`** for (a) a personal `@gmail`
  account and (b) an external account, with `aud`/`iss`/`exp` validated.
- Both `doGet` and `doPost` succeed cross-origin (confirms A1/A7).

**Revises if it fails:** if consent/verification friction appears, or CORS blocks one hop,
re-evaluate static-host vs. ADR-0017's auth-code-on-`/exec` redirect (which keeps the whole
flow inside the GAS origin and needs no CORS).

**RESULT (2026-07-22): PASS — all four assumptions confirmed.**

| Assumption | Result | Evidence |
|-----------|--------|----------|
| **A1** (CORS both hops) | ✅ PASS | Browser `fetch()` from `https://nuuc-it.github.io/Static/pub/AS/` received and rendered JSON from both `doGet` and `doPost` — both hops (`/exec` → `script.googleusercontent.com`) served usable `Access-Control-Allow-Origin` |
| **A2** (GIS ID token, external accounts, no consent wall) | ✅ PASS | `stuart.donaldson@gmail.com` and `f3go30@gmail.com` (both personal @gmail, both external to northlakeuu.org) obtained ID tokens via the GIS button with only `openid email`; no verification wall, no consent-screen friction. (GIS re-prompts on each visit — expected without `data-auto_select`; a Milestone-1 UX choice, not friction.) |
| **A3** (server-side verify in deployer context) | ✅ PASS | Backend `tokeninfo` verification returned `verified:true` with `aud`/`iss`/`exp` all validated, stable `sub`, `email_verified:true` for both accounts (log tag `webapp.spike.identity`, 6 verified entries). Negative case: tampered/garbage token → `tokeninfo_400`, `verified:false` (fail closed) |
| **A7** (`text/plain` = CORS simple request) | ✅ PASS | `doPost` with `text/plain` body succeeded cross-origin with no preflight failure |

**Operational caveat discovered (cost ~1hr):** with the script bound to a standard GCP
project, the deployer's sensitive-scope grant (`script.external_request`, needed for
`UrlFetchApp`) is silently dropped unless (a) the scope is registered on the OAuth
consent screen and (b) an editor run actually *calls* `UrlFetchApp` to trigger the
consent prompt (entry points that return early authorize "successfully" with an
incomplete token). Documented in NUUC-Dispatch `docs/OPERATIONS.md` provisioning
steps 3/11 + §Failure Modes; diagnosis/repair tooling: `pnpm run admin -- getAuthInfo`
and `SPIKE_authProbe`.

**Gate outcome:** S1 passes → the committed dispatcher build (ADR-0002 signing) and
Spike S2 (`gts-79dw.2`) are unblocked.

---

## 6. Spike S2 — Access verification for an external email against a folder/doc

**Question:** Can the deployer-context backend determine, for a verified external `@gmail`,
whether it has read/write access to the board **folder** — *including access conferred only
through a domain-managed group*? (A4, A5, A6)

**Harness**
- Reuses S1's verified email. Page calls `doPost spike_check_access` → `{ email, folderId,
  docId }`.
- Backend, in deployer context, computes:
  - `folderAccess = DriveApp.getFolderById(folderId).getAccess(email)`
  - `docAccess = DriveApp.getFileById(docId).getAccess(email)`
  - returns `{ folderAccess, docAccess, method: 'getAccess' }`.

**Test matrix** (seed each state on the real board folder before running)

| Case | Setup | Expected |
|------|-------|----------|
| (a) direct read | external email granted VIEW on folder | `VIEW` |
| (b) direct write | external email granted EDIT on folder | `EDIT` |
| **(c) group read/write** | external email has **no** direct grant, but is a **member of a domain-managed Google Group** that holds VIEW/EDIT on the folder | `VIEW`/`EDIT` — **the load-bearing case** |
| (d) no access | external email with nothing | `NONE` |
| (e) link-share | folder shared "anyone with link" | observe whether `getAccess` over-grants |

**Fallback path (only if (c) returns `NONE`/`UNKNOWN`)**
- `Drive.Permissions.list(folderId, {supportsAllDrives:true})` (Drive v2) → find
  `type: 'group'` grants and their roles.
- `AdminDirectory.Members.get(groupKey, externalEmail)` per matching group (catch the
  thrown 404 as "not a member") — **not** `Members.hasMember()`, which throws `Invalid
  Input: memberKey` for external/non-domain memberKeys even on confirmed members
  (discovered running this spike; see
  `knowledge-base/references/gas-admin-directory-external-groups.md` for the full gotcha
  list, including OAuth-consent-screen scope registration and Shared Drive sharing).
- Combine: effective role = highest role of any group the email is a confirmed member of,
  plus any direct permission.

**Pass criteria**
- A **definitive, reproducible** read vs write vs none verdict for an external `@gmail`
  whose only access is via a domain-managed group (case c).
- (e) does not silently grant access to a non-member.

**Revises if it fails:** if neither `getAccess` nor the Admin-SDK fallback resolves case
(c), the folder-scoped group model (R3/R7) is not achievable as specified — fall back to
per-document `getAccess`, an explicit allowlist, or require direct (non-group) sharing.

**RESULT (2026-07-23): PASS — all three assumptions confirmed against real production
data (Communications team Shared Drive `0AOp6vlyPY_E6Uk9PVA`).**

| Case | Result | Evidence |
|------|--------|----------|
| (a) direct VIEW | ✅ PASS | `f3go30@gmail.com` granted direct viewer on the folder → `getAccess` returned `VIEW`, `method: getAccess` |
| (b) direct EDIT | ✅ PASS | Same email upgraded to direct editor → `getAccess` returned `EDIT` (Drive correctly upgrades viewer→editor in place) |
| **(c) group read/write** | ✅ **PASS — the load-bearing case** | `stuart.donaldson@gmail.com` (external, no direct grant) resolved to `EDIT` via the Admin SDK fallback (`method: adminSdk, groupExpandUsed: true`) — confirmed member of one of the folder's domain-managed groups |
| (d) no access | ✅ PASS | An unrelated external email with no direct grant and no group membership returned `NONE` on both the direct folder and the same real folder used for case (c) — no false positive |
| (e) link-share over-grant | ⚠️ **Not independently exercised** | `0AOp6vlyPY_E6Uk9PVA` is the Shared Drive **root**; Google's Drive API rejects `Permissions.insert({type:'anyone'})` on a top-level Shared Drive folder outright (`Cannot share top level folders of shared drives to domains or anyone`) — no mutation occurred. This is itself a reassuring negative finding: the over-share risk case (e) worries about is blocked by Drive/Workspace policy at the Shared Drive root. Testing on an actual team subfolder (the more representative "board folder" shape) is deferred — not blocking, since (c)/(d) already establish default-deny + correct group resolution. |

**Assumption verdicts:**
- **A4** (getAccess reflects group-conferred access) — **REFUTED as literally stated**:
  `getAccess()` alone does NOT expand group membership; it returns `NONE` for
  group-only access. The fallback (A5) is required, not optional, for case (c).
- **A5** (Admin SDK fallback reliable for domain-managed groups incl. external members)
  — ✅ **CONFIRMED**, with a correction: use `AdminDirectory.Members.get(groupKey,
  memberKey)`, not `.hasMember()` — the latter throws `Invalid Input: memberKey` for
  external memberKeys even on confirmed members (see
  `knowledge-base/references/gas-admin-directory-external-groups.md`).
- **A6** (VIEW/COMMENT vs EDIT/OWNER trustworthy for view/sync gating) — ✅ **CONFIRMED**
  for both the direct (`getAccess`) and group-conferred (Admin SDK role mapping) paths.

**Operational gotchas discovered (full detail in
`knowledge-base/references/gas-admin-directory-external-groups.md`):** a newly-added
OAuth scope must be registered on the consent screen (manifest scope alone is silently
dropped); the underlying API (Admin SDK) must be separately enabled in GCP Console, or
the consent prompt never appears at all; forcing re-authorization requires revoking the
app's grant at `myaccount.google.com/permissions` then re-running an editor function
that actually calls the new service; `DriveApp.setSharing()` doesn't support Shared
Drive items (use `Drive.Permissions.insert`/`.remove` instead).

**Gate outcome:** S2 passes on the load-bearing case (c) plus (a)/(b)/(d) — the
folder-scoped domain-group ACL model (R3/R4/R5/R7) is achievable as specified, via
`getAccess()` + the corrected Admin SDK fallback (not `getAccess()` alone, contra A4's
literal wording). §7 gate (both spikes green) is cleared; `gts-1hyh` is
unblocked. Case (e) remains an open, non-blocking follow-up.

---

## 6a. Fixture: multi-folder team ACL (`gts-79dw.4.16`) — provisioned 2026-07-28

R3a/R3b (multi-folder tier resolution + per-document write re-authorization) cannot be
exercised without a team owning ≥2 folders where a test identity's access **differs**
between them. Standing fixture, reuse rather than reprovision:

| | Value |
|---|---|
| Team Id | `TestTeamA` |
| Folder 1 (`stuart.donaldson@gmail.com` **has** access) | `1SCPPZfUeSWqaE3WvWYl6go13lzEZQUbs` |
| Folder 2 (`stuart.donaldson@gmail.com` **does not** have access) | `1plip6j718V77_y2y_X6oritx8Th-8VqX` |
| Tracked doc under folder 1 | `12PdYg3WMbvyYtzcMeetkl8IrZE7OSSm6FfA45Cl7Sk8` — seeded `AI: stuart.donaldson@gmail.com Draft the annual report`, synced, `DocData.teamId` auto-resolved to `TestTeamA` via the folder walk (confirms `_walkFolderForTeam` fires correctly for both of a multi-folder team's rows) |
| Tracked doc under folder 2 | `1Hc_ETgOc987uUJvs2pBuxUw-9Lx4-8NajX9cLMJYEy0` — seeded `AI: board@northlakeuu.org Reconcile the budget`, synced, same auto-resolution |

Both `TeamData` rows (`teamId=TestTeamA`, one per folder) already existed; the two
tracked documents were created for this fixture via a new composable script,
`scripts/create_team_fixture_doc.py` (new: `ScenarioSession.new_doc()` →
`move_doc_to_folder` fixture → `append_paragraph` → `sync()` → `get_docdata_row` to
confirm). Re-run it against any folder id to add another seeded doc without manual
Drive clicks:

```bash
python scripts/create_team_fixture_doc.py --folder-id <folderId> \
  --action "AI: assignee@example.org Some action text"
```

**Not yet exercised by this fixture:** the domain-managed-group fallback path (A5) on
either of these two folders specifically — Spike S2's Communications Shared Drive
(`0AOp6vlyPY_E6Uk9PVA`, §6) remains the reference case for that path; `TestTeamA` is
direct-sharing only. Revisit if `gts-79dw.4.12`/`.4.8` need the group path exercised on
a multi-folder team specifically, not just on any team.

---

## 7. Gate

Both spikes green → the static+GIS architecture and the folder-scoped group ACL are
confirmed; proceed to propagate (§8) and build Milestone 1. Either red → record which
assumption failed, revise this plan, and re-decide before any propagation.

**GATE CLEARED (2026-07-23): both S1 and S2 PASS.** Propagation (§8a) is now unblocked —
not yet executed as of this writing; still a deliberate separate step per §8a's own
framing ("nothing below happens until the gate clears"). Note the mid-course
architecture split discovered while executing S2 (ADR-0002, accepted in NUUC-Dispatch):
NUUC-Dispatch verifies+signs identity only; GActionSheet (this repo) owns the folder-ACL
authorization check, since it already holds the expanded Drive/Admin-SDK scopes and
stays Internal-only (see NUUC-Dispatch ADR-0002 §Context for why the split exists —
external-facing identity verification needs minimal scope to avoid OAuth
review/friction; ACL evaluation needs expanded scope and stays domain-internal). §4's
architecture diagram and §8a's propagation list should be revised to reflect this split
before Milestone 1 build begins.

---

## 8. bd tracking (the executable spikes)

The spikes are **beads** — execute from them cold; this doc is their shared context.

| Bead | Role |
|------|------|
| `gts-79dw` [EPIC] | Authorized web app AI editing (parent). Description still names the *old* auth-code-on-`/exec` target — to be revised after the gate. |
| `gts-hc6v` [INF] | **Operator prerequisite (ADR-0017 Phase 2 only)** — provision the OAuth Web client on the *existing* GActionSheet GCP project (consent screen External/Published, `openid email`). No longer blocks S1. |
| `gts-79dw.3` [INF] | **Operator prerequisite (S1)** — provision a *separate* GCP project + OAuth Web client for **NUUC-Dispatch** (consent screen External/Published, `openid email`; **github.io as Authorized JavaScript origin**). **Blocks S1.** |
| **`gts-79dw.1`** [INF] | **Spike S1** — verifiable identity from a static GitHub Pages page via `doGet`/`doPost`. Blocked by `79dw.3`; **blocks S2 and `6dlp`.** |
| **`gts-79dw.2`** [INF] | **Spike S2** — verify a gmail/external email's read/write access to the board folder/doc incl. domain-managed group. Blocked by S1; **blocks `1hyh`.** |
| `gts-1hyh` [IMP] | Old per-document authz gate — superseded in framing by S2; kept as the eventual *build* of the authz gate, now blocked by S2. |
| `gts-6dlp` [IMP] | Deferred editing build — blocked by S1. |

## 8a. Propagation (deferred — only after §7 passes)

Nothing below happens until the gate clears:
- **ADR** — revise ADR-0017 (still *Proposed*) or write **ADR-0021**: static-first-party +
  GIS flip; folder-scoped domain-group authz. → `adr-quality-check`. *(not yet done)*
- **CONTEXT.md** — new Core Capability + UC (external team member reviews/syncs team
  actions via verified link). → `use-case-quality-check`. *(not yet done)*
- **docs/security-architecture.md** — Boundary 1 gains a verified-identity gate beyond
  `WEBAPP_SECRET`; add static origin as a trust boundary + a finding for the new surface.
  *(not yet done)*
- **OPERATIONS.md** — OAuth client / GIS setup, team folder id config, Admin SDK
  enablement, static-pages repo + publish pipeline (StaticHTMLonGas Steps 5–6). *(not yet
  done)*
- **bd** — ✅ done 2026-07-23: epic `gts-79dw` description revised to the
  static+GIS/split-repo target; Milestone-1 twin-tickets filed under new child epic
  `gts-79dw.4` — see table below.

| Bead | Role |
|------|------|
| `gts-79dw.4` [EPIC] | Milestone 1 parent: verified team action portal (listing + filters + sync). |
| `gts-79dw.4.1`/`.4.2` [IMP]/[TST] | Verify ID token + resolve folder-access tier (R1,R2,R3–R8). Test-first (specifiable, not user-visible). |
| `gts-79dw.4.3` [IMP] | Team action listing endpoint, status + scope filters (R9–R13b). Slice; depends on `.4.1`; implemented alongside `.4.5`/`.4.7`, no separate pre-implementation test. |
| `gts-79dw.4.5` [IMP] | Sync entry point gated on write tier (R14,R15). Slice; depends on `.4.1`; implemented alongside `.4.3`/`.4.7`. |
| `gts-79dw.4.7` [IMP] | Team portal UI — complete View A mockup, read paths wired (§9). Slice; depends on `.4.3`/`.4.5`. |
| `gts-79dw.4.8` [TST] | Single e2e hardening test for `.4.3`+`.4.5`+`.4.7` together, authored against the frozen slice-review AC. Blocks `.4.7`. |
| ~~`.4.4`/`.4.6`~~ | Closed 2026-07-23 — superseded, consolidated into `.4.8` (implement-first ordering revision). |

---

## 9. Milestone 1 build (post-gate, for reference — not committed yet)

Oracle-driven ordering (CLAUDE.md), **revised 2026-07-23**:
- **Test-first** (specifiable): token verify + folder-access→tier resolution (R2–R7) only
  — `gts-79dw.4.1`/`.4.2`. This is a precise security contract with no user-visible
  surface.
- **Slice** (perceptual) — everything the user actually sees or interacts with: listing +
  filter semantics (R9–R13), sync entry-point (R14–R15), and the list/filter/sync-button UI
  are implemented together first (`gts-79dw.4.3`/`.4.5`/`.4.7`), reviewed as one
  working experience, AC frozen at that review, then hardened by a single e2e test
  (`gts-79dw.4.8`) covering all three entry points + UI regression. Rationale: filter
  and sync-gating behavior are cheap to state as rules but the actual experience (is the
  list readable, does the filter control feel right, does sync-button gating read as
  expected) is what needs iterating on — pre-writing narrow endpoint tests before that
  review would lock in assumptions the review is meant to challenge.
- **Pipeline**: static-pages repo + build/publish chained into deploy; cross-origin
  regression test + a "Phase-1 GAS notice still works" guard.

**Revised 2026-07-26 — UI fidelity.** The slice builds the **complete** View A mockup
(status filter Open/Closed/All, scope filter mine/all, per-row edit affordance, assignee
status-change control) with only the read paths wired. Rationale: the filters and the edit
affordances are the part of the design most likely to be wrong on sight, and reviewing them
costs nothing extra once the list renders — whereas discovering the layout is wrong *after*
the edit backend is wired means rework on both. Edit controls render tier-correctly and are
inert until R16–R18 land against the AC frozen at that same review.

---

## 10. Decisions and open questions

**Resolved 2026-07-26** (were open questions; recorded here so they are not re-litigated):

- **Team identity.** ~~Chip `docId` → folder walk, `?group=` param, or baked-in folder id?~~
  → **`teamId`, resolved from `DocData.teamId` for a chip's `docId`.** No folder walk. See §0.
- **Scope key.** ~~`boardFolderId`~~ → **`teamId`**; a team may own several folders, so a
  folder id cannot address a team (§0, ADR-0014 §1).
- **Multi-folder tier.** Read tier = highest across the team's folders (R3a); writes
  re-authorized per-document against that document's folder (R3b).
- **Sync control placement.** ~~Per-row vs single doc-in-context button?~~ → **per document
  row** in View A (the list spans documents, so a single button has no unambiguous target),
  and a single button in View B (which has exactly one document in context).
- **Milestone 1 UI fidelity.** Complete mockup, read paths wired (§9 revision above).

**Still open:**

- **Session vs per-call verify.** Verify the ID token on every call, or verify once and
  bind to a short-lived server session (cf. F3Go30's GUID sessions)? Per-call is what
  `.4.1`/`.4.3`/`.4.5` implement today (R8, no trust-on-first-use); revisit only if the
  tokeninfo round-trip per call proves too slow with the multi-folder tier resolution (R3a
  multiplies the `getAccess` calls). Defer to build.
- **iOS/Safari storage** (StaticHTMLonGas §ITP) — only relevant once we persist a
  bookmark/token; note for build, not spike.
- **Filter by a named person** (R13a) — recorded open seam. The hardening `[TST]` should
  parameterize the scope filter so *mine* and *a named person* share one assertion shape.

---

## 11. Reuse inventory — extend, do not proliferate

Audited 2026-07-26. The portal's data and mutation needs are **already implemented**; what
is missing is the GIS gate in front of them and the UI on top. Two near-duplicate
team-scoped readers already exist and must be consolidated before a third appears.

| Portal need | Existing implementation | Action |
|---|---|---|
| Team-scoped action list | `_listImportableActionsData(docId)` (`src/WebApp.js:1458`) — docId→team via DocData, open-only, excludes current doc, rich row schema, **excludes docs whose `DocData.syncStatus` is Deleted/Doc Not Found** | **Consolidate** |
| Team-scoped action list | `_listBoardActionsData(boardFolderId, …)` (`src/BoardListing.js:61`) — folderId→team via TeamData, open/all + window, lean row schema, **does not** exclude dead docs (R13b gap) | **Consolidate** |
| Team summary (doc counts) | `_handleTeamView` (`src/WebApp.js:200`, `?cmd=teamview`) — a third teamId-scoped reader, anonymous | Fold onto the shared reader |
| Document-scoped action list (View B) | `find_sheet_actions` / `_handleFindSheetActions` — docId-scoped rows, TEST_TOKEN-gated | Reuse core; add GIS-gated route |
| Edit an action (R16) | `edit_action_row` / `_handleEditActionRow` — replicates `onActionSheetEdit`'s Dirty + Date-Modified stamp | Reuse core; add GIS-gated route |
| Change status (R17) | `patch_action_status` — sidebar status fast path; also `_setStatusFromPreview` (`src/EditorAddonCard.js:452`) as the add-on's equivalent affordance | Reuse core; add GIS-gated route |
| Sync a document | `syncDocument()` via `_handleBoardSyncDocument` (`src/BoardSync.js`) | Already reuses; rename only |
| Tier resolution | `_resolveIdentityAndAccessTier` (`src/AccessControl.js:56`) | Extend to multi-folder (R3a) + per-doc write check (R3b) |
| Branded page shell | `_renderBrandedPage` (`src/WebApp.js`) | Reuse for any GAS-served portal page |

**Target shape.** One core reader, `_readTeamActions(teamId, opts)`, where `opts` covers
`{ statusFilter, windowDays, excludeDocId, assigneeEmail, fields }`, with the existing
route handlers becoming thin gate-plus-delegate wrappers. `_listImportableActionsData` is
then `_readTeamActions(teamId, { statusFilter:'open', excludeDocId:docId })` behind
`assertTeamAccess`; the portal listing is the same call behind the GIS tier gate.

**Known defect surfaced by the audit:** `assertTeamAccess` (`src/SyncManager.js:1311`)
`break`s at the first `TeamData` row matching a `teamId`, so for a multi-folder team it
authorizes against an arbitrary one of that team's folders. Same single-folder assumption
as the portal's original `boardFolderId` keying. Both fixed together (R3a/R3b).

**Rename map** (applies with the consolidation, not before):

| From | To |
|---|---|
| `src/BoardListing.js`, `src/BoardSync.js` | `src/TeamPortal.js` (or `TeamListing.js`/`TeamSync.js` if they stay split) |
| `boardFolderId` param | `teamId` |
| `list_board_actions` | `list_team_actions` |
| `board_sync_document` | `team_sync_document` |
| `webapp.board.*` log tags | `webapp.team.*` (ADR-0019/0020) |

`webapp.teamview` already uses the corrected namespace.

---

## 12. Frozen slice AC — 2026-07-27 review gate (ADR-0013)

**Verdict: approve → harden.** `docs/team-portal-mockup.html` over
`docs/team-portal-fixture.json` (real captured rows, real status vocabulary, real
assignees) was reviewed as one working experience. The AC below is **frozen**: it is the
only shared artifact between the slice implementation and the hardening `[TST]`
(`gts-79dw.4.8`), which is authored against this section and must not read the slice code.

### 12.1 Read contract — `list_team_actions`

Request `{ teamId, statusFilter, windowDays?, scope, idToken }`:

| Field | Values | Semantics |
|---|---|---|
| `statusFilter` | `open` (default) \| `closed` \| `all` | Bucketing is by `isResolved()`, **not** by literal string match (R10). |
| `windowDays` | integer, default 60 | Applies **inside the resolved branch only** (R11/R12). |
| `scope` | `all` (default) \| `mine` | `mine` = `assignee_email` == the **verified** caller email, never a client-supplied field (R13a). |

Response rows carry exactly these fields; the page re-derives none of them:

```
global_id, action_id, action_text, assignee_email, assignee_name,
status, status_bucket, status_resolved, status_icon,
doc_id, doc_name, doc_url, created_date, modified_date
```

`status_bucket` / `status_resolved` / `status_icon` are the server's `getStatusDisplay()`
answer for that row's literal status (`SyncManager.js` `getStatusIconUrl` is the existing
display authority — inherit it, do not invent a second). The canonical picker vocabulary is
served alongside as `statusOptions[] = { status, icon, alt }` from `getStatusVocabulary()`.

**Frozen invariants (the hardening `[TST]` asserts these, not the visual surface):**

1. **A stale open action never ages out.** `windowDays` has no effect on unresolved rows at
   any setting — decided at this gate, not merely inherited. An open row last modified two
   years ago appears under `open` and under `all` with `windowDays=1`.
2. `closed`/`all` age out resolved rows outside `windowDays`; boundary is tested at the
   exact cutoff.
3. Status is bucketed by `isResolved()`, so a free-text status (`Escalated`, `Backlog`)
   lands in a bucket without appearing in `statusOptions`.
4. `scope=mine` composes with every `statusFilter` in one server query (the mockup composes
   two results client-side; the real route must not).
5. R13b: rows are excluded when the action's `sync_status` **or** its document's
   `DocData.syncStatus` is `Deleted`/`Doc Not Found`.
6. Fail closed: no row data for a caller who does not positively resolve ≥ VIEW (R6/R8).

### 12.2 Presentation rules frozen at this gate

- **Status renders the literal typed value.** When that literal is off `statusOptions`, it
  is annotated `(counts as open/closed)` — the one thing a reader of `Escalated` cannot
  infer. No canonicalization of the displayed text.
- **Rows are grouped by document**, and the sync control lives on the **document header**
  — document-scoped, one per document, not one per row. (This supersedes the earlier §10
  "per document row" wording, which the grouped layout makes precise.)
- The resolved-age control is labelled **"Include resolved from the last N days"**, never
  "Resolved within" or "Updated within" — the asymmetry in 12.1(1) makes an age-filter
  label a false promise on open rows. The control is hidden when `statusFilter=open`.
- Assignee status control = canonical picker **plus** free-text entry, offered only on rows
  whose `assignee_email` matches the verified caller (R17).
- The Edit affordance renders only at EDIT tier; the sync control renders always and is
  disabled below EDIT tier with a reason in its title (R5/R14).
- "Person…" is rendered as a disabled extension point (R13a seam) — not removed.

### 12.3 Team navigation — decided at this gate

**In-page team switcher.** A verified caller who belongs to several teams switches between
them inside one page; `teamId` is not baked into the URL. This makes the mockup's `Team`
control real and adds one route:

- **R21** The portal SHALL offer `list_my_teams` — for the verified caller, every `teamId`
  with the caller's resolved tier on it (R3a across each team's folders) — and SHALL render
  a switcher when more than one team resolves. A caller with one team sees no switcher; a
  caller with none gets the R6 non-leaking notice.

`Signed in as` and `Access` in the mockup remain **simulation-only** — the real page takes
identity from the verified GIS token and resolves tier from Drive folder access.

### 12.4 Gate outputs

- **Verdict:** approve → harden. `gts-79dw.4.8` is authored against §12 only.
- **Funnel deltas** (non-committal, ROADMAP §Funnel): filter state in the URL for
  shareable/bookmarkable views; "last synced" timestamp on the document header; sync-all
  for a team from View A; surfacing off-vocabulary statuses to a team lead.
- **Open seams** (registered into `gts-79dw.4.8` / `.4.15` design fields): named-person
  scope filter (R13a); session-vs-per-call token verify; delegated-bucket status rendering,
  which no live row currently exercises; `teamId` parameterized rather than fixed.
