# ADR-0017 validation probe — chip-link landing page

**Date:** 2026-06-14
**Validates:** ADR-0017 (anonymous-identity confirmation for chip-link status pages)
**Objective (clarified):** click action-item link → low-friction web page → view, edit,
**save** the action; **must not require org-domain membership**.

## Outcome (one line)

The **view/edit/save** objective is fully achievable with a plain GAS HtmlService web app and
needs **no** Google sign-in. The ADR's **GIS Sign-In-inside-the-page** layer (verified *who*
for the audit log) is **blocked in the GAS iframe** by two independent, documented constraints
and is **not required** by the clarified objective — it is a separable enhancement.

## What was tested

### Test 1 — server-side ID-token verification (the `doPost` half) ✅ VIABLE

`curl` against the same endpoint `UrlFetchApp` would call (the codebase already uses this exact
`UrlFetchApp + muteHttpExceptions` pattern in `_handleVerifyChipIntegrity`, `WebApp.js:627`):

```
GET https://oauth2.googleapis.com/tokeninfo?id_token=<bad>
  → HTTP 400  {"error":"invalid_token","error_description":"Invalid Value"}
connect 0.03s / total 0.12s
```

Endpoint reachable, clean JSON, rejects bad tokens. A valid token returns `200` with
`iss/aud/email/email_verified/exp`. **If** verified identity is ever needed, the server side is
trivial — the problem is entirely on the client (button) side.

### Test 2a — OAuth auth-code *redirect* flow on the stable GAS URL ✅ VIABLE (no external host)

Distinct from the GIS JS widget (Test 2). The classic OAuth 2.0 authorization-code flow uses a
**top-level redirect** (link `target="_top"`) to `accounts.google.com`, then Google redirects
back to a **stable `script.google.com` URL** (`/exec` or the `apps-script-oauth2`-style
`/usercallback`), where `doGet` exchanges `?code=` server-side for the verified email. No
iframe sign-in, no `googleusercontent` origin, no external hosting — the entire identity flow
lives in the existing GAS deployment + one OAuth Web client (redirect URI = the stable GAS URL).
This supersedes the earlier "needs a stable external host" conclusion: the stable host is the
GAS `/exec` URL itself. Proven by the official `apps-script-oauth2` library.

### Test 2 — GIS Sign-In *widget* (One-Tap/button) *inside* the GAS page ❌ BLOCKED

Two independent, documented blockers — neither is worth a deploy cycle to re-confirm:

1. **Rotating `googleusercontent.com` content origin.** GAS serves HtmlService content from a
   sandboxed cross-origin iframe on a volatile `https://<hash>-script.googleusercontent.com`
   origin that changes on each publish. GIS requires the page origin to be a registered
   *Authorized JavaScript Origin* on the OAuth Client ID, and Google **rejects
   `googleusercontent.com`** as an authorized JS origin
   ([issuetracker 170740549](https://issuetracker.google.com/issues/170740549)). You cannot
   register the origin GIS runs on.
2. **No new Google session inside an iframe.** GIS/One-Tap will not create a new sign-in
   session inside a cross-origin iframe. FedCM cross-origin-iframe support (stable M139, Aug
   2025) requires `allow="identity-credentials-get"` on **all** ancestor iframes — but GAS owns
   the outer wrapper iframe and does not set it; we cannot add attributes to GAS's own frame.

### Test 3 — anonymous view/edit/save in a GAS web app ✅ VIABLE (standard pattern)

A web app deployed *execute-as DEPLOYER / access = Anyone (anonymous)* serves an HtmlService
page to any browser regardless of domain, and `google.script.run` (or a form `doPost`) calls
back into deployer-privileged functions to write the deployer-owned `ActionSheet`. This is the
standard public-GAS-web-app pattern; the write capability is "knowledge of the `globalId`"
(magic-link class), exactly the authorization model ADR-0017 §Tradeoffs already names.

## Forward design (matches clarified objective, no blockers)

```
chip URL (?cmd=preview&docId=..&ain=AI-N)
  → doGet renders HtmlService page: action text/status/assignee + status <select> + Save
  → Save → google.script.run.confirmStatus(globalId, newStatus)   [no secret, single row]
       → patch status (reuse _handlePatchActionStatus core), log {eu, au:'anonymous', ...}
  → page shows confirmation
```

No domain membership, no sign-in, low friction. `au` degrades to `anonymous` — which the ADR
already specified as the required degraded behaviour.

## Verified-identity requirement (clarified 2026-06-14)

Verified *who* is the ultimate requirement ("if we cannot, re-evaluate the approach");
anonymous is acceptable only as an interim best-effort. GIS-in-the-GAS-iframe is dead
(Test 2), so the identity *mechanism* is the open decision. Three candidates:

| Mechanism | Verifies whom | Friction | Runs | New infra |
|---|---|---|---|---|
| GIS, stable-origin page | Google-account users only | 1 click | external host → POST token → GAS verify (Test 1) | static host + OAuth Client ID |
| **Email-code verification** | **any** email (incl. non-Google) | email round-trip | **entirely in GAS** (MailApp + google.script.run) | **none** |
| Anonymous (interim) | nobody | zero | GAS | none |

**Requirement tension:** "verify who" + "no domain" + "any recipient" cannot be met by GIS
alone — a recipient with no Google account is unverifiable, which trips the re-evaluate clause.
Email-code verification verifies any email with no GIS blocker and no new hosting, at the cost
of one email round-trip; it is the strongest fit for the stated requirements and is the
recommended re-evaluation. DocsAPI (`/home/stuar/roots/g-Proj/GDocTools/DocsAPI`) is
docs-only (markdown) — **not** a deployable host, so the GIS route needs new infra.

**Decision (operator, 2026-06-14): GIS on a stable-origin page.** Recipients with no Google
account are a **nice-to-have**, deferred to a **future email-code enhancement** — not in the
first build. ADR-0017's Decision must be revised: keep GIS + server-side verify, but move the
GIS button OUT of the GAS iframe onto a stable-origin landing page that POSTs the token to
`doPost`. The in-iframe rendering (current ADR §Decision step 2) is a rejected alternative.

## Quick-test artifact & run procedure

Artifact: `0017-gis-landing-probe.html` (this dir) — the deployable landing page.

Operator prerequisites (the only blockers to running the empirical end-to-end test):

1. **Host** `0017-gis-landing-probe.html` on a fixed origin you control (GitHub Pages /
   Firebase Hosting / any static host). Record the exact origin.
2. **OAuth Client ID** (type "Web application") in the **same GCP project** as the Apps Script
   project; add the host origin from (1) as an Authorized JavaScript Origin. Paste the
   `client_id` into the probe's `data-client_id`, and the GAS `/exec` URL into `GAS_EXEC_URL`.
3. Add a throwaway `confirm_identity_and_act` branch to `doPost` (recipe below — **probe only,
   do not ship without the twin-ticket cycle**).

Then open `https://<host>/0017-gis-landing-probe.html?docId=<DOC>&ain=AI-1` in a browser
signed into a **non-domain** Google account and confirm: account chooser (no consent screen) →
token → Save → GAS verifies and returns ok.

### GAS `doPost` verify recipe (probe only — not production)

```js
// in doPost(), before the WEBAPP_SECRET gate (this route is intentionally secret-less):
if (payload.action === 'confirm_identity_and_act') {
  var info = _verifyIdToken_(payload.id_token);          // null on any failure
  var au = (info && info.email_verified === 'true') ? info.email : 'anonymous';
  // capability = knowledge of globalId (magic-link class); reuse patch core:
  var res = _handlePatchActionStatus({ globalId: payload.globalId, newStatus: payload.newStatus });
  GasLogger.log('chip.confirm', { au: au, globalId: payload.globalId, newStatus: payload.newStatus });
  GasLogger.flush();
  return res;
}

function _verifyIdToken_(idToken) {
  if (!idToken) return null;
  var r = UrlFetchApp.fetch(
    'https://oauth2.googleapis.com/tokeninfo?id_token=' + encodeURIComponent(idToken),
    { muteHttpExceptions: true });                         // same pattern as WebApp.js:627
  if (r.getResponseCode() !== 200) return null;
  var p = JSON.parse(r.getContentText());
  var CLIENT_ID = PropertiesService.getScriptProperties().getProperty('GIS_CLIENT_ID');
  if (p.aud !== CLIENT_ID) return null;                   // token was minted for THIS app
  if (p.iss !== 'https://accounts.google.com' && p.iss !== 'accounts.google.com') return null;
  if (Number(p.exp) * 1000 < Date.now()) return null;     // not expired
  return p;                                                // { email, email_verified, ... }
}
```

## Future enhancement (deferred)

Email-code verification for non-Google recipients: anonymous GAS page → type email →
`MailApp` sends a code → confirm → `au` = that email. No GIS, no hosting, works for any
recipient. Held in ROADMAP §Funnel, not built now.

## Sources

- https://issuetracker.google.com/issues/170740549 (googleusercontent.com rejected as JS origin)
- https://developers.google.com/identity/gsi/web/guides/fedcm-migration (cross-origin iframe, M139)
- https://developers.google.com/identity/sign-in/web/gsi-with-fedcm
- https://joshuatz.com/posts/2019/google-apps-script-authorization-in-a-cross-origin-iframe/
- https://zenn.dev/freddiefujiwara/articles/6073d89c0c1924 (GitHub Pages + Apps Script GIS pattern)
- https://www.labnol.org/code/20674-verify-google-api-oauth-token (UrlFetchApp tokeninfo verify)
