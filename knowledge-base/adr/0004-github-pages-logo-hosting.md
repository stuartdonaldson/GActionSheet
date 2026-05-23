# ADR-0004: GitHub Pages for Static Asset Hosting

Status: Accepted
Date: 2026-05-22

## Context
The Workspace Add-on manifest requires a publicly accessible `logoUrl`. Logo assets exist in
`assets/` (logo-128.png, logo-32.png). Options for hosting:

(a) Google Drive direct URL — requires file sharing set to "Anyone with link", file ID extracted
    from sharing link; ID is opaque and not version-controlled.
(b) GitHub Pages on the public repo — assets served directly from the repo tree; URL is stable,
    version-controlled, and requires no separate sharing management.
(c) Cloudflare Pages — full static site CDN; unnecessary complexity for a single image.

## Decision
Make the GitHub repository public and enable GitHub Pages (source: master branch, root folder).
Use the GitHub Pages asset URL as the `logoUrl` in the add-on manifest.

## Consequences
- Repository becomes publicly readable; no private credentials or secrets may be committed.
- Logo URL is stable and version-controlled: changing the asset updates it at the same URL on
  next push + Pages rebuild (typically < 1 min).
- One-time manual setup: enable Pages in GitHub Settings (Settings → Pages → Deploy from branch
  → master → / (root)).
- Any future static assets (icons, doc images) can be served from the same host at no cost.
- Google Drive hosting approach (documented in knowledge-base/references/workspace-addon-setup.md)
  remains valid as a fallback if the repo visibility must be made private in future.
