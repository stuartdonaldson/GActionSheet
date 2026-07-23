# Verified Board-Group Action Portal — Working Plan (spike-gated)

**Status:** Draft / assumptions unproven — **do not propagate to CONTEXT.md, ADRs,
security-architecture.md, or bd epics until Spikes S1 + S2 pass.**
**Date:** 2026-07-21
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

## 1. Goal

A recipient who clicks an `AI-N:` chip in a board document — **including someone outside
`northlakeuu.org`, on a personal `@gmail` or external account** — lands on a page that:

1. proves *who they are* (verified Google identity), then
2. shows them **all action items for that board group**, filterable, **only if** their
   identity has Drive access to the board folder (directly or via a domain-managed group),
   and
3. lets them **sync the document** if they have write access — enabling a
   type-`AI-N:`-and-bookmark workflow with no add-on and no domain account.

Milestone 1 is **read-only listing + sync**. Editing action status is deferred.

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
  tracked as `GTaskSheet-79dw.3` (see §8), separate from `hc6v` (which stays scoped to
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
- **R2** The backend SHALL verify the ID token server-side (`aud` = our client id, `iss`, `exp`, signature) before returning any board data, keying on `sub`. Fail closed.
- **R8** Action text is confidential and SHALL NOT be exposed to any identity lacking ≥ read access.

**Authorization (board-folder scoped — not per-document)**
- **R3** Access SHALL be evaluated against the **board group's Drive folder**, not the individual document.
- **R4** VIEW/COMMENT access (direct or via a domain-managed group) → read access to the listing.
- **R5** EDIT/OWNER access → additionally authorized to trigger sync.
- **R6** No resolvable access → deny all board data + non-leaking notice. Default-deny when access cannot be positively confirmed.
- **R7** Group-conferred access SHALL resolve for **external members of a domain-managed Google Group** *(gated by A4/A5)*.

**Listing & filter (Milestone 1 — read-only)**
- **R9** List all tracked actions across every document under the board group's folder.
- **R10** Default filter = **Open** actions only.
- **R11** **All** filter = Open + Closed whose last-update timestamp is within the last **60 days**.
- **R12** The 60-day window SHALL be user-extendable on the page.
- **R13** Milestone 1 is read-only — no status editing.

**Sync**
- **R14** The page SHALL offer a "Sync this document" action, **write-gated** (R5).
- **R15** Sync SHALL reuse the existing deployer-context sync path and log `{eu, au = verified sub/email, docId, outcome}` via GasLogger.

---

## 4. Access-control model (target)

```
Static page (github.io)  ── GIS sign-in ──►  ID token (openid email)
        │
        │  fetch() text/plain POST  (A1, A7)
        ▼
GAS WebApp doPost (executeAs DEPLOYER, ANYONE_ANONYMOUS)
        │  1. verify ID token → sub + verified email        (R2, A3)
        │  2. folder access = getAccess(email, boardFolder)  (R3, A4)
        │         └─ fallback: Admin SDK group expansion     (A5)
        │  3. tier: VIEW/COMMENT → read ; EDIT/OWNER → read+sync   (R4/R5/R6)
        ▼
   read → board listing JSON (filtered)   |   write → sync route
```

- The verified-identity ACL becomes the **entire security boundary** for this surface
  (the backend already runs with the deployer's full authority for every anonymous
  request). Per StaticHTMLonGas.md: default-deny, fail closed, gate on `sub` not `email`,
  concentrate tests here.
- This is **additive** — the existing `WEBAPP_SECRET`/`TEST_TOKEN` routes and the Phase-1
  anonymous notice are untouched.

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
- Tracked as `GTaskSheet-79dw.3` (not `hc6v`, which stays scoped to ADR-0017 Phase 2 on the
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
Spike S2 (`GTaskSheet-79dw.2`) are unblocked.

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
- `Drive.Permissions.list(folderId)` → find `type: 'group'` grants and their roles.
- `AdminDirectory.Members.hasMember(groupKey, externalEmail)` per matching group
  (works for external members **because the group is domain-managed**), enable Admin SDK
  Directory advanced service.
- Combine: effective role = highest role of any group the email is a confirmed member of,
  plus any direct permission.

**Pass criteria**
- A **definitive, reproducible** read vs write vs none verdict for an external `@gmail`
  whose only access is via a domain-managed group (case c).
- (e) does not silently grant access to a non-member.

**Revises if it fails:** if neither `getAccess` nor the Admin-SDK fallback resolves case
(c), the folder-scoped group model (R3/R7) is not achievable as specified — fall back to
per-document `getAccess`, an explicit allowlist, or require direct (non-group) sharing.

---

## 7. Gate

Both spikes green → the static+GIS architecture and the folder-scoped group ACL are
confirmed; proceed to propagate (§8) and build Milestone 1. Either red → record which
assumption failed, revise this plan, and re-decide before any propagation.

---

## 8. bd tracking (the executable spikes)

The spikes are **beads** — execute from them cold; this doc is their shared context.

| Bead | Role |
|------|------|
| `GTaskSheet-79dw` [EPIC] | Authorized web app AI editing (parent). Description still names the *old* auth-code-on-`/exec` target — to be revised after the gate. |
| `GTaskSheet-hc6v` [INF] | **Operator prerequisite (ADR-0017 Phase 2 only)** — provision the OAuth Web client on the *existing* GActionSheet GCP project (consent screen External/Published, `openid email`). No longer blocks S1. |
| `GTaskSheet-79dw.3` [INF] | **Operator prerequisite (S1)** — provision a *separate* GCP project + OAuth Web client for **NUUC-Dispatch** (consent screen External/Published, `openid email`; **github.io as Authorized JavaScript origin**). **Blocks S1.** |
| **`GTaskSheet-79dw.1`** [INF] | **Spike S1** — verifiable identity from a static GitHub Pages page via `doGet`/`doPost`. Blocked by `79dw.3`; **blocks S2 and `6dlp`.** |
| **`GTaskSheet-79dw.2`** [INF] | **Spike S2** — verify a gmail/external email's read/write access to the board folder/doc incl. domain-managed group. Blocked by S1; **blocks `1hyh`.** |
| `GTaskSheet-1hyh` [IMP] | Old per-document authz gate — superseded in framing by S2; kept as the eventual *build* of the authz gate, now blocked by S2. |
| `GTaskSheet-6dlp` [IMP] | Deferred editing build — blocked by S1. |

## 8a. Propagation (deferred — only after §7 passes)

Nothing below happens until the gate clears:
- **ADR** — revise ADR-0017 (still *Proposed*) or write **ADR-0021**: static-first-party +
  GIS flip; folder-scoped domain-group authz. → `adr-quality-check`.
- **CONTEXT.md** — new Core Capability + UC (external board member reviews/syncs board
  actions via verified link). → `use-case-quality-check`.
- **docs/security-architecture.md** — Boundary 1 gains a verified-identity gate beyond
  `WEBAPP_SECRET`; add static origin as a trust boundary + a finding for the new surface.
- **OPERATIONS.md** — OAuth client / GIS setup, board-folder id config, Admin SDK
  enablement, static-pages repo + publish pipeline (StaticHTMLonGas Steps 5–6).
- **bd** — revise epic `GTaskSheet-79dw` description to the static+GIS target; file the
  Milestone-1 board-listing + sync twin-tickets.

---

## 9. Milestone 1 build (post-gate, for reference — not committed yet)

Oracle-driven ordering (CLAUDE.md):
- **Test-first** (specifiable): token verify (R2), folder-access→tier (R3–R7), filter
  semantics (R10–R12), sync entry-point (R14–R15).
- **Slice** (perceptual): static list UI + filter control + sync button — implement-first →
  human review → freeze AC → harden `[TST]` against frozen contract.
- **Pipeline**: static-pages repo + build/publish chained into deploy; cross-origin
  regression test + a "Phase-1 GAS notice still works" guard.

---

## 10. Open questions
- **Sync control placement.** The board view spans multiple docs; is "Sync this document"
  per-document-row, or a single action for the doc the chip arrived from? Resolve at the
  slice-review gate.
- **Board-group identity.** How does the page know *which* board folder to list — from the
  chip's `docId` → folder walk (ADR-0014), a `?group=` param, or the folder id baked into
  the bookmarkable URL?
- **Session vs per-call verify.** Verify the ID token on every call, or verify once and
  bind to a short-lived server session (cf. F3Go30's GUID sessions)? Defer to build.
- **iOS/Safari storage** (StaticHTMLonGas §ITP) — only relevant once we persist a
  bookmark/token; note for build, not spike.
