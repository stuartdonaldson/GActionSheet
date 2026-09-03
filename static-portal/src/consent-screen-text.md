# NUUC-Dispatch — OAuth Consent Screen Text

Fields for the GCP Console OAuth consent screen configuration (see
`../../GActionSheet/../NUUC-Dispatch/SETUP.md` for the full provisioning checklist this
belongs to).

## User type
- **External** — required even though the GCP account/project is a
  `northlakeuu.org` Workspace member (which also offers an "Internal" option).
  Internal restricts sign-in to `@northlakeuu.org` accounts only, which breaks the
  "Visitor (any Google account)" requirement in `NUUC-Dispatch/docs/CONTEXT.md`
  §Stakeholders/§Constraints. Do not switch to Internal to dodge verification.

## App information
- **App name:** NUUC-Dispatch
- **User support email:** stuart.donaldson@gmail.com
- **App logo:** none — omitted deliberately. Adding a logo (or exceeding 10 authorized
  domains) voids the non-sensitive-scope verification exemption and forces Google's
  brand-verification review before Publish. `icon-128.png` (this folder) exists for the
  consent screen but must **not** be uploaded while this app stays unverified.

## App domain
- **Application home page:** https://nuuc-it.github.io/Static/pub/AS/
- **Application privacy policy link:** https://nuuc-it.github.io/Static/pub/AS/privacy/
- **Application terms of service link:** https://nuuc-it.github.io/Static/pub/AS/terms/

## Authorized domains
- `nuuc-it.github.io` (not bare `github.io` — it's on the public suffix list, so Google
  requires the specific subdomain)

## Developer contact information
- sdonaldson@northlakeuu.org (same person as the GCP account owner, but this field
  scopes to the org domain the app will actually be used within)

## Scopes
- `openid`
- `.../auth/userinfo.email`

Both non-sensitive — no Google verification/security review required, even with
publishing status **In production**.

## OAuth 2.0 Client (Web application)
- **Name:** NUUC-Dispatch Web (Spike S1)
- **Authorized JavaScript origins:** `https://nuuc-it.github.io`
- **Authorized redirect URIs:** none (GIS ID-token sign-in, not an auth-code redirect)
