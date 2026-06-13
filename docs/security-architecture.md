# Security Architecture & Threat Model — GActionSheet (NUUTS Action tool)

**Status:** Draft for review
**Date:** 2026-06-12
**Scope:** Identity/execution model, trust boundaries, authentication, the
service-account direction for release, account taxonomy, and a threat model with
current findings. Decision records that follow from this document are tracked
separately (see §9).

This document is **intent + analysis**. It does not change code. Concrete
remediations are listed in §8 and §9 for separate execution.

---

## 1. Execution identity model (the governing fact)

Apps Script runs the two halves of this tool under **different identities**, and
every other security decision follows from that split.

| Surface | Runs as | Mechanism | Notes |
|---------|---------|-----------|-------|
| **Add-on** — homepage card, `@`-menu create-action, link preview, sidebar acts | **The invoking end user** | Workspace Add-on triggers always execute as the active user | Cannot be forced to a service identity. `Session.getEffectiveUser()` == `getActiveUser()` here. |
| **Central sync / write-back** — `doPost` routes, `syncDocument` → WebApp proxy | **The deployer** | WebApp deployed `executeAs: USER_DEPLOYING` (appsscript.json:29) | Stable shared identity. `eu` = deployer, `au` = caller. |

The add-on (user context) hands work to the WebApp (deployer context) over
`UrlFetchApp` + a shared secret. **That handoff is a deliberate privilege
transition**: a least-privilege user action is escalated to the shared service
identity that owns the ActionSheet. The user can write to a Doc they already have;
the *sheet* write is performed by the deployer identity on their behalf.

`_getIdentity()` (WebApp.js:25) records both identities on every request, so any
write can be attributed to the human caller even though it executed as the deployer.

### Why this matters for testing fidelity

Today the **deployer and the primary full-access test account are the same person**
(`sdonaldson@`). That conflation hides a bug class: code that leans on *deployer*
privilege instead of the *caller's* own access would pass silently, because the
caller happens to be the deployer. A non-deployer full-access test account exercises
the real production property — the add-on acts with the *user's* authority, not the
service's. See §5.

---

## 2. Trust boundaries

```
   ┌─────────────────────────────────────────────────────────────┐
   │ Internet (ANYONE_ANONYMOUS)                                   │
   │                                                               │
   │   any client ──POST──► /exec doPost ──┐                       │
   └───────────────────────────────────────┼───────────────────────┘
                                            │  ◄── BOUNDARY 1: app auth
                                            ▼
   ┌─────────────────────────────────────────────────────────────┐
   │ WebApp (executeAs DEPLOYER)                                   │
   │   • WEBAPP_SECRET gate  (production routes)                   │
   │   • TEST_TOKEN gate     (test-support routes)                 │
   │   • assertTeamAccess()  ◄── BOUNDARY 2: per-team data access  │
   │                                                               │
   │   reads/writes ActionSheet (owned by deployer)                │
   │   reads team folders via DriveApp (deployer's Drive view)     │
   └─────────────────────────────────────────────────────────────┘
                    ▲
                    │  UrlFetchApp + Bearer + secret
                    │
   ┌────────────────┴────────────────────────────────────────────┐
   │ Add-on (executeAs END USER)                                   │
   │   • runs in the user's Docs context, user's OAuth grant       │
   │   • writes chips into Docs the user can already edit          │
   └─────────────────────────────────────────────────────────────┘
```

- **Boundary 1 (app authentication):** the `/exec` endpoint is
  `ANYONE_ANONYMOUS` (appsscript.json:28), so GAS performs no identity check before
  `doPost`. Authentication is entirely application-level: `WEBAPP_SECRET` for
  production routes, `TEST_TOKEN` for test-support routes. **The secret is the only
  thing standing between the internet and the sync logic.**
- **Boundary 2 (data-access authorization):** `assertTeamAccess(teamId, ss)`
  (SyncManager.js:872) probes `DriveApp.getFolderById` in the *executing* identity
  and throws `TeamNotFound` / `TeamAccessDenied` rather than returning partial data.
  This is the per-team confidentiality control for filtered reads (Import/Notify).

---

## 3. Authentication layers (as built)

Three independent mechanisms, by route class:

1. **GAS HTTP gate (Bearer token)** — Layer 1 of ADR-0012. `UrlFetchApp` callers
   attach `Authorization: Bearer ScriptApp.getOAuthToken()` unconditionally. On
   `ANYONE_ANONYMOUS` it is accepted but not required; it exists so the same call
   site works against `/dev` and `/exec ANYONE` without change.
2. **`WEBAPP_SECRET` (application secret)** — Layer 2 of ADR-0012. Checked in
   `doPost` (WebApp.js:146) before any production handler. Stored in Script
   Properties, never in source.
3. **`TEST_TOKEN` (per-deployment, expiring)** — `_checkTestToken` (TestWebApp.js).
   A UUID minted by `npm run deploy:test`, expiring after a fixed window, gating the
   test-support/fixture routes so the Python harness can drive GAS without a browser.

The **`probe` action bypasses both gates by design** (WebApp.js:100) but is inert in
production: `PROBE_ENABLED = false` (PROBE.js:14).

---

## 4. Release identity: dedicated service (robot) account

### Decision direction

GAS has **no true service-account runtime identity**. The two viable patterns:

- **(A) Dedicated Workspace *user* (robot) account** — e.g.
  `nuuts.service@northlakeuu.org` — owns the script, the ActionSheet, and the
  deployments, and is the `USER_DEPLOYING` identity. *Recommended.*
- **(B) GCP service account + domain-wide delegation** — only required to write to
  *arbitrary* users' Docs without their interactive consent. Not needed here: add-on
  writes happen in the user's own context, and central writes target one sheet the
  robot owns. DWD carries a much larger blast radius and a Workspace-admin grant.

**Recommendation: Pattern A — `nuuts.service@` for production.** It decouples the
tool from any individual (continuity / bus-factor), shrinks the blast radius of the
`executeAs` identity to only what the robot is explicitly granted, and makes
Drive/Docs audit logs attribute all automated writes to a single distinguishable
actor.

### Obligations that come with Pattern A

- Transfer ownership of the script project, the ActionSheet, and the WebApp
  deployment to the robot account **before** release.
- The robot is granted **Reader/Editor only on the team folders + the ActionSheet** —
  nothing else. Its Drive footprint *is* the blast radius of a leaked `WEBAPP_SECRET`.
- Credentials (the robot's password + recovery + any clasp login) are held as a
  managed secret, not on a personal device.

---

## 5. Account taxonomy

Three **orthogonal roles**. Dev conflates the first two onto one human; production
separates all three.

| Role | Purpose | Dev (now) | Production (target) | Auth artifact |
|------|---------|-----------|---------------------|---------------|
| **Service / deployer** | Owns project + sheet; WebApp `executeAs`; runs privileged writes; clasp/deploy | `sdonaldson@` | `nuuts.service@` | clasp creds + deployer browser session |
| **Primary end user** | Full team access; exercises happy-path add-on/UI as a *non-deployer* | *(conflated with deployer today)* | `test.u1@northlakeuu.org` | `.auth/test.u1.json` |
| **Restricted end user** | Partial access; exercises the access-denial path (`TeamAccessDenied`) | `sanctuary@` | `test.u2@northlakeuu.org` | `.auth/test.u2.json` |

Renames that follow from this taxonomy (for separate execution):

- `.auth/user.json`  → `.auth/sdonaldson.json` (dev deployer session; prod successor `nuuts.service@`)
- `.auth/user2.json` → `.auth/test.u2.json` (restricted; replaces `sanctuary@`)
- **new** `.auth/test.u1.json` (primary full-access, non-deployer)
- `.auth/user1.json` — stale; delete after confirmation.

Test selection stays via `PROBE_AUTH_STATE` (default = primary). `.auth/` is
git-ignored (.gitignore); the mapping is documented in a committed `.auth/README.md`.

---

## 6. Assets & threat model

| # | Asset | Threat | Current control | Residual risk |
|---|-------|--------|-----------------|---------------|
| A1 | ActionSheet contents (all teams' actions, assignees, emails) | Unauthorized read/write via `/exec` | `WEBAPP_SECRET` (prod routes); `executeAs` deployer owns sheet | **High if secret weak/leaked** — see F1, F2 |
| A2 | Per-team confidentiality (one team reading another's actions) | Cross-team data leak in filtered reads | `assertTeamAccess` throws, never partial | Depends on every read path calling it (F4) |
| A3 | Test-support routes operating on production data | Anonymous caller invokes fixture/seed/read routes | `TEST_TOKEN`, expiring, per-deploy | **F3: two read routes are not token-gated** |
| A4 | `WEBAPP_SECRET` itself | Disclosure (repo, logs, client payloads) | Script Properties only; not in source | Test value is `"1234"` (F1) |
| A5 | OAuth scope grant (what a consenting user authorizes) | Over-broad scope → larger consent + larger compromise surface | — | Broad scope set (F5) |
| A6 | Deployer identity continuity | Tool tied to a departing individual | — | Addressed by §4 robot account (F6) |

### Findings

- **F1 — Production `WEBAPP_SECRET` strength.** `local.settings.json` carries
  `"webappSecret": "1234"` for test. Production must use a high-entropy,
  rotatable value in Script Properties. On `ANYONE_ANONYMOUS`, this secret is the
  sole app-auth boundary (§2, Boundary 1). **Blocker for release.**
- **F2 — `ANYONE_ANONYMOUS` exposure.** Any internet client can reach `doPost`.
  Acceptable *only* because Layer 2 is strong and confidential. If the org permits
  it, an `ANYONE` (Google-account-required) `/exec` would add defense in depth — but
  it would block the Node test path, so it must be a prod-only deployment setting,
  not a code change. Re-evaluate at release.
- **F3 — Unauthenticated production reads.** `verify_action_rows` (WebApp.js:130)
  and `verify_chip_integrity` (WebApp.js:133) are dispatched **before** the
  `WEBAPP_SECRET` gate and their handlers do **not** call `_checkTestToken` (unlike
  `edit_action_row`, `find_sheet_actions`, `append_doc_paragraph`, etc.). On the
  anonymous endpoint, an arbitrary caller who supplies a `docId` can read that
  document's action rows and chip-integrity data. These are test-support routes that
  touch production data — they should be `TEST_TOKEN`-gated like their siblings, or
  removed from the production deployment. **Address before release.**
- **F4 — `assertTeamAccess` coverage.** The control is sound but only as good as its
  call-site coverage. Every team-scoped read path (Import/Notify, EPIC-D/E) must
  route through it; this should be asserted by the access-filter journey
  (`J-ACCESS-FILTER`) rather than assumed.
- **F5 — OAuth scope breadth.** The manifest requests `drive` (full),
  `documents`, `spreadsheets`, `directory.readonly`, `contacts.readonly`, plus
  identity scopes (appsscript.json:6–17). `drive` (full) is broad; if folder access
  is only ever by ID, `drive.file` or a narrower scope may suffice for some paths.
  Audit each scope against actual API calls before public listing — every scope is
  consent surface and compromise surface.
- **F6 — Identity continuity.** Covered by the §4 robot-account direction; tracked
  as a release prerequisite, not a code defect.

---

## 7. Defense-in-depth principles (retain through release)

- **Keep `assertTeamAccess` enforced even in service context.** Service privilege
  must never let a malformed request cross a team boundary. The authz check runs in
  the executing identity (the deployer/robot's Drive view) — confirm the robot's
  folder grants match exactly the intended team scope, no more.
- **Secret is a boundary, not a convenience.** Treat `WEBAPP_SECRET` rotation as an
  operational procedure; never log it, never echo it in responses, never commit it.
- **Least privilege at every layer:** narrowest OAuth scopes, narrowest robot Drive
  grants, expiring test tokens, probes disabled in prod.

---

## 8. Pre-release hardening checklist

- [ ] F1 — Generate high-entropy production `WEBAPP_SECRET`; store in Script
      Properties; document rotation in OPERATIONS.md.
- [ ] F3 — Gate `verify_action_rows` + `verify_chip_integrity` behind
      `_checkTestToken`, or exclude test-support routes from the production deployment.
- [ ] F5 — Audit OAuth scopes against actual call sites; drop or narrow unused/broad
      scopes.
- [ ] F6 — Provision `nuuts.service@`; transfer script, ActionSheet, and deployment
      ownership; grant Drive access to team folders + sheet only.
- [ ] F2 — Decide `ANYONE` vs `ANYONE_ANONYMOUS` for the production `/exec`
      deployment with the org admin.
- [ ] Confirm `PROBE_ENABLED = false` in the production build.

---

## 9. Decisions to record separately

The smaller-model follow-up session should:

1. Draft an ADR for the **identity & service-account model** (the user/service
   execution split + the `nuuts.service@` robot-account direction). Successor /
   relationship to ADR-0007 (single-script dual-deployment) and ADR-0012
   (two-layer auth) should be stated, not duplicated.
2. Execute the §5 `.auth/` renames + new `test.u1`/`test.u2` artifacts and update
   all references (Python, JS, `package.json`, OPERATIONS.md, staging journey docs).
3. Add `.auth/README.md` (committed) describing the account roles per §5.
4. Update OPERATIONS.md §Test Accounts to reflect the three-role taxonomy and the
   permission scenarios.
5. File findings F1–F5 as tracked issues (bd) with the release-blocker ones flagged.
```
