# ADR-0021: Verified team portal as the single verified-identity surface

Status: Accepted
Date: 2026-07-31
Supersedes: ADR-0017 (Verified identity for chip-link action editing) — Phase 2 only;
Phase 1 (anonymous chip-preview notice) is retained, see Decision.
Relates to: `../../NUUC-Dispatch/knowledge-base/adr/0002-signed-identity-assertion.md`
(signed-assertion identity handoff), ADR-0012 (web app two-layer auth),
`docs/security-architecture.md` §1-3, gts-79dw (epic), gts-79dw.4.7/.4.9/.4.13/.4.14/
.4.18/.4.21-.4.25 (portal build-out), gts-6dlp (superseded in-place edit), gts-hc6v
(disposition recorded below)

## Context

ADR-0017 recorded two phases for verified, editable access to a chip-linked action:
Phase 1, an anonymous notice page (shipped, still correct), and Phase 2, a verified
edit obtained via an **OAuth 2.0 authorization-code redirect anchored on the stable
GAS `/exec` URL**, explicitly choosing that flow over a GIS JS widget (blocked — GAS's
rotating `googleusercontent.com` iframe origin cannot be a registered Authorized JS
origin) and over a **stable external host**, which ADR-0017 rejected as unnecessary
("the stable GAS `/exec` URL itself serves as the OAuth `redirect_uri`").

Every part of that Phase 2 design has since been superseded by what actually shipped
(gts-79dw Units A-D, `plan-context.md`):

- **Identity source.** Verified identity now comes from GIS running on the separate
  **NUUC-Dispatch** project, which signs the verified identity into a per-target HMAC
  assertion (`NUUC-Dispatch` ADR-0002) that GActionSheet verifies server-side
  (`_verifySignedAssertion`, `src/AccessControl.js:321`, checking `iss ===
  'nuuc-dispatch'`, `aud === 'gactionsheet'`, signature, expiry). There is no
  OAuth-authorization-code redirect anywhere in the shipped flow, and no `/exec`
  redirect URI is registered for this purpose. `src/AccessControl.js`'s own
  `_verifyGisIdToken` — the raw-tokeninfo verifier ADR-0017 Phase 2 would have used —
  is retained only as dead code (superseded by gts-79dw.4.18) with a comment
  explaining it can never work for a genuinely external caller: any GIS ID token
  audience-matching a client on GActionSheet's *own* GCP project requires that
  project's consent screen to go External, which conflicts with keeping it
  Internal-only for the Workspace add-on (ADR-0002 in *this* repo — timestamp-based
  conflict resolution — is unrelated; the premise referenced here is GActionSheet's
  Internal-consent-screen requirement documented in `docs/verified-board-portal-plan.md`).
- **External static host.** The team portal frontend (`static-portal/src/index.html`,
  `doc.html`) is served from **GitHub Pages** (`https://nuuc-it.github.io/Static/pub/AS/`
  and `AS-sit/`) — precisely the "stable external host" ADR-0017 rejected. It is now
  correct: the portal is a static page that authenticates via GIS and calls the GAS
  WebApp's verified-portal routes over HTTPS; no OAuth redirect URI needs to live on
  the GAS `/exec` URL at all, so the constraint that motivated the rejection no longer
  applies.
- **Editing surface.** Editing does not happen in place on the chip-preview/notice
  page. It happens in the team portal (`team_edit_action`, `team_patch_status`,
  `src/TeamActionWrite.js`) — an operator decision recorded 2026-07-26 when gts-6dlp
  (ADR-0017's Phase 2 in-place edit) was closed as superseded.
- **Read/write split.** ADR-0017's Phase 1/Phase 2 split described an anonymous-read →
  verified-edit progression on the *same* notice page. The portal instead owns both
  read (`get_document_actions`, View B) and write (`team_edit_action`,
  `team_patch_status`) as one verified surface; the notice page is no longer a step
  toward editing, it is a permanent, separate, lower-capability fallback (see Decision).

## Decision

The **verified team portal** — `static-portal/src/index.html` (View A, team list) and
`static-portal/src/doc.html` (View B, single document), served from GitHub Pages, GIS
sign-in on the NUUC-Dispatch project, identity handed off as a signed HMAC assertion
verified server-side by `src/AccessControl.js` — is the single verified-identity
surface for reading and editing team action items. It replaces ADR-0017 Phase 2 in
full:

1. **Identity path:** GIS (NUUC-Dispatch project) → signed assertion (`NUUC-Dispatch`
   ADR-0002, HMAC-SHA256, `aud: 'gactionsheet'`) → `_verifySignedAssertion` →
   `_resolveIdentityAndAccessTier` (`src/AccessControl.js:94`) resolves a per-team
   `NONE`/`VIEW`/`EDIT` tier from Drive ACL / Admin SDK group membership. No OAuth
   authorization-code redirect exists in this repo; no GCP-console OAuth Web client is
   provisioned or required on GActionSheet's own project for this path.
2. **Hosting:** the portal frontend is deliberately hosted externally (GitHub Pages),
   not on the GAS `/exec` URL. This directly reverses ADR-0017's rejection of an
   external host — the OAuth-redirect constraint that motivated that rejection does
   not exist in the assertion-handoff design.
3. **Read and write both live in the portal**, not on the chip-preview notice page:
   `get_document_actions` (read, View B), `team_edit_action` / `team_patch_status`
   (write), each re-authorizing per document (`_authorizeDocWrite`, R3b) rather than
   trusting team-wide tier.
4. **Phase 1 is retained as the unauthenticated fallback.** The anonymous
   `doGet ?cmd=preview&docId=<docId>&ain=AI-N` notice page (`_handlePreviewNotice`,
   `src/WebApp.js:123`) is unchanged in spirit and still shipped: non-confidential
   metadata only, a Drive-ACL-gated document link, and — new since ADR-0017 — a
   "sign in for the full view" CTA that hands off to View B
   (`?doc=<docId>&team=<teamId>` on the portal origin) when the doc resolves to a
   team. It remains the correct landing page for a recipient who is not signed in, or
   whose identity does not resolve to any team access; the portal does not replace it,
   it is what the notice page's sign-in CTA now leads to.

## Rejected alternatives

Carried forward from ADR-0017 (still correct, restated for completeness):

| Alternative | Why rejected |
|---|---|
| GIS Sign-In JS widget inside the GAS HtmlService page | Still blocked — GAS's rotating `googleusercontent.com` iframe origin cannot be a registered Authorized JS origin. This is why GIS instead runs on the separate NUUC-Dispatch origin, not inside GAS's own served page. |
| Anonymous edit (no identity) | Still rejected — a `globalId` is forwardable/guessable (F3-class); insufficient to expose action text or authorize edits. |

Newly rejected, reversing ADR-0017:

| Alternative | Why rejected now |
|---|---|
| OAuth authorization-code redirect anchored on the stable GAS `/exec` URL (ADR-0017 Phase 2's design) | Requires an OAuth Web client + Authorized redirect URI provisioned on GActionSheet's own GCP project, which must stay Internal-only to keep the Workspace add-on installable — so no true external (non-domain) visitor could ever complete it. The NUUC-Dispatch signed-assertion handoff achieves the same verified-identity goal without this conflict. |

## Consequences

- **Simpler trust boundary:** GActionSheet never runs its own OAuth flow or holds a
  GIS client secret; it only verifies a signed assertion against a shared HMAC secret
  scoped to itself (`aud: 'gactionsheet'`), one per target, per NUUC-Dispatch ADR-0002.
- **No GCP-console provisioning required on GActionSheet's own project** for verified
  identity — gts-hc6v's OAuth-Web-client provisioning work is obsolete (see below).
- **External hosting is now load-bearing, not just tolerated:** the portal's ability to
  serve GIS sign-in depends on GitHub Pages being a stable, registerable JS origin —
  changing that hosting choice later is an architecture-level decision, not a deploy
  detail.
- **Phase 1 / Phase 2 language retired.** Future work should refer to "the anonymous
  notice" and "the verified portal" rather than "Phase 1" / "Phase 2" — the phased
  same-page progression ADR-0017 described no longer describes the shipped shape.
- **Open seam carried forward unchanged:** email-code verification for recipients
  without a Google account, noted in ADR-0017 as deferred to ROADMAP §Funnel, is still
  unaddressed and still out of scope here.

## Disposition of gts-hc6v

gts-hc6v ("Provision OAuth Web client for chip-link verified identity (Phase 2)") was
scoped entirely to ADR-0017 Phase 2's auth-code-redirect design: an OAuth 2.0 Web
client on GActionSheet's own GCP project, its `/exec` URL as an Authorized redirect
URI, and `GIS_CLIENT_ID`/`GIS_CLIENT_SECRET` in Script Properties. That design is
superseded per this ADR. gts-hc6v's own 2026-07-22/07-26 notes already anticipated
this and asked to confirm before closing: is `GIS_CLIENT_ID` (as read by the now-dead
`_verifyGisIdToken`) pointing at the NUUC-Dispatch client the intended/sufficient
configuration, i.e. does any portal path still need an OAuth Web client on
GActionSheet's own project?

Confirmed no: the live verification path (`_verifySignedAssertion`,
`src/AccessControl.js:321`) checks an HMAC signature against a Script-Property secret
named by the assertion's `kid`, plus `iss`/`aud`/`exp` — it never reads
`GIS_CLIENT_ID` at all. `_verifyGisIdToken`, the only function that *does* read
`GIS_CLIENT_ID`, is explicitly marked dead code in-source (superseded by gts-79dw.4.18)
with a comment stating it can never succeed for a true external caller regardless of
which client `GIS_CLIENT_ID` names, because GActionSheet's own consent screen must
stay Internal to keep the Workspace add-on installable. No portal route — read or
write — depends on an OAuth Web client on GActionSheet's own GCP project. gts-hc6v is
closed as superseded by this ADR.
