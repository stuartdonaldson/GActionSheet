# LL: Smart-chip pill rendering and hover preview are gated on Marketplace publish

Date: 2026-06-02
Domain: platform | editor-addon

## Observation
During the 6ov POC (branch `poc/editor-addon-action-chip`), `createActionTriggers` and
`linkPreviewTriggers` were confirmed functional in developer test mode. However, the rounded
chip pill appearance and hover preview card did not appear for URLs inserted programmatically.
Investigation confirmed two independent gating mechanisms:

**Gate 1 — Chip pill rendering requires user-initiated conversion.**
Programmatic URL insertion via `DocumentApp.getCursor().insertText()` + `Text.setLinkUrl()`
creates a plain hyperlink. It does NOT trigger the "replace with chip" prompt. That prompt
fires only when a user types or pastes the URL directly into the document. The chip pill
shape requires either user-initiated conversion or a right-click "convert to chip" option.
After `createActionTrigger` inserts the link, the user sees a styled hyperlink — not a pill.

**Gate 2 — linkPreviewTriggers pattern matching uses the Marketplace SDK deployment version.**
Docs checks URL patterns from the manifest of the deployment pinned in the GCP Marketplace
SDK App Configuration page. If that version is stale (e.g. the SDK still points to version
124 but version 128 has been deployed), Docs does not recognise the URL and never calls
`onLinkPreview`. No log activity appears — the trigger simply doesn't fire. The function
execution itself uses the deployment the individual user has installed, so these two halves
of the dispatch are decoupled.

**Gate 3 — Full chip pill rendering appears to require a published Marketplace listing.**
Both rounded pill shape and logo rendering were not confirmed in developer test mode. This
is consistent with Google's documentation that the smart-chip rendering is a Docs client-side
feature gated on the add-on being installed through the Workspace Marketplace.

Additionally: `CardService.newSmartChipConfig()` and `CardService.newRenderAction()` are not
present in the GAS runtime. These appear in AI-generated code (confirmed Gemini hallucination)
but are not in the CardService reference documentation. Calling them throws
`TypeError: CardService.newSmartChipConfig is not a function`.

## Why Chain

Why 1 — POC appeared to not work; debugging consumed significant time.
Why 2 — Developer test mode looks like a complete environment; platform limitations aren't
         documented prominently.
Why 3 — No prior guide captured the distinction between the mechanism (URL pattern, handler,
         manifest) being correct and the visual rendering requiring a published listing.
Why 4 — AI-generated code for GAS add-ons references non-existent CardService APIs (hallucination
         risk is high in this domain); no guard prevents their use.

Root cause: The visual smart-chip experience has platform gates invisible at development time.
Developers confirm the mechanism works (URL inserted, handler fires, card renders) but cannot
confirm the final visual appearance without a Marketplace-published listing.

## Guidance (gas-addon-guide.md target)

- The chip mechanism (URL insertion, pattern matching, preview card handler) can be tested
  in developer mode. The visual pill appearance requires a published or domain-installed add-on.
- After every `npm run deploy:test` or `npm run deploy:prod`, update the GCP Marketplace SDK
  App Configuration to point to the new version number. Failing to do so silently breaks
  `linkPreviewTriggers` with zero log activity.
- `createActionTriggers` and `linkPreviewTriggers` dispatch differently: pattern matching uses
  the SDK-configured deployment; function execution uses the user's installed deployment.
  Develop against `/dev` HEAD once any valid version is set in the SDK config.
- Do not use `CardService.newSmartChipConfig()` or `CardService.newRenderAction()` — they do
  not exist in the GAS runtime. Any AI-generated code referencing them is a hallucination.
- Programmatic `insertText` + `setLinkUrl` never triggers the chip conversion prompt.
  The user must paste the URL or manually convert it. Design the UX around this constraint.

## Initial Candidates

b: add a "Smart chip constraints" section to `gas-addon-guide.md` covering the three gates,
   the SDK version update requirement, and the hallucinated CardService APIs

b: add a developer checklist note to `docs/poc-editor-addon-migration.md` success criteria:
   "visual chip pill rendering is confirmed only after domain-install or Marketplace publish;
   mechanism confirmation (pattern match + preview card fires) is the POC bar"
