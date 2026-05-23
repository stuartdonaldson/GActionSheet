# ADR-001: Single-script dual-deployment architecture

**Status:** Accepted
**Date:** 2026-05-22

## Context

GActionSheet needs to (a) display a sidebar card in Google Docs as a Workspace Add-on and (b) write to a central ActionSheet spreadsheet that end users do not have direct edit access to. These two goals create an identity boundary: add-ons run as the active user; sheet writes require deployer identity.

Options considered:
1. **Two GAS projects** — separate add-on project and automation project; add-on calls automation Web App. Simpler identity model but doubles deployment surface.
2. **Service account proxy** — add-on calls Sheets API using OAuth2 library + service account credentials stored in script properties. Eliminates Web App but adds credential management complexity.
3. **Single-script dual-deployment** — one project deployed as both Workspace Add-on and Web App; add-on calls its own Web App endpoint via `UrlFetchApp`.

## Decision

Use single-script dual-deployment (option 3).

## Rationale

- One codebase, one `.clasp.json`, one deploy pipeline
- No credential files or OAuth2 library required
- POC verified end-to-end 2026-05-22: add-on → doPost → sheet.appendRow succeeded

## Tradeoffs

- Web App access must be "Anyone" (not org-restricted) — org admin must set this; cannot be controlled in code
- Shared secret is the only viable auth mechanism (Bearer tokens not propagated by Apps Script runtime)
- Both add-on and Web App deployments must be updated in sync on each release
