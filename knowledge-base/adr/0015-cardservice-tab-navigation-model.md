# ADR-0015: CardService tab-navigation model for the homepage card

Status: Accepted
Date: 2026-06-11
Relates to: ADR-0010 (add-on surface files by UI technology). Resolves the conflict between
`knowledge-base/ROADMAP.md`'s "tabbed sidebar" (DocStatus/Import/Notify) and the
`html-sidebar-card-pivot` decision (2026-05-27, `GTaskSheet-cw5`) that committed the project to a
CardService-only UI.

## Context

ROADMAP EPIC-D/E specify a **tabbed sidebar** with DocStatus, Import, and Notify tabs. That wording
predates the `html-sidebar-card-pivot` decision (`GTaskSheet-cw5`), which removed HtmlService and
committed the add-on to a **CardService-only** UI (ADR-0010). CardService has **no native tab
widget**: a "tab" is simulated by swapping the rendered card. So "tabbed sidebar" must be realised
as card navigation, not as an HtmlService tab control.

The navigation refactor touches `buildHomepageCard()` in `src/WorkspaceAddonCard.js` — the
`homepageTrigger` entry point rendered for **every user on every document**. Five handlers rebuild
the card through it (`onSyncNow`, `onVerifySync`, `onInsertTrackerTable`, `onSetActionStatus`,
`onDeleteAction`), and the DocStatus body performs an HTTP sheet fetch (`_buildHomepageState`). A
naive second "tabbed" card builder beside the existing one would fork the production entry point and
duplicate the DocStatus rendering — the exact maintenance hazard this design must avoid. EPIC-D-PRE
also requires the model to stay extensible for a future Settings tab (Phase 2) without
re-architecting.

This ADR fixes the navigation model so the slice (`GTaskSheet-0r0s`) implements one agreed design;
it specifies no business logic for the Import/Notify tabs (those land in EPIC-D/E).

## Decision

Introduce a single navigation helper that `buildHomepageCard()` **delegates to**, with the
DocStatus tab reusing the existing card-building functions unchanged. There is **no parallel
card-building path**.

### Navigation mechanism

A **tab-bar section** at the top of the card: a `ButtonSet` of `TextButton`s, one per tab. The
active tab renders `FILLED` and inert; each inactive tab carries an `onClickAction` that switches
the card via `CardService.newNavigation().updateCard(...)`. This reuses the existing button +
`_buildCardAction` + parameterised-handler idiom already used by `onSetActionStatus` /
`onDeleteAction` (which read `e.parameters`).

Rejected alternatives: the card-header `addCardAction` overflow menu (a 3-dot menu, not a visible
tab UX); `setFixedFooter` (caps at ~two buttons, cannot hold a growing tab set).

### Navigation helper

```
_buildTabbedHomepageCard(activeTab, eventOrVerificationResult, opts)
  activeTab ∈ {'docStatus','import','notify'}, default 'docStatus'
```

It builds, in order: the shared header (`_buildHomepageHeader`) → the tab-bar section
(`_buildTabBarSection(activeTab)`) → **the active tab's body only** → the version footer. The
existing DocStatus error-fallback card is retained.

### Reuse of existing card actions (no parallel path)

- `buildHomepageCard(eventOrVerificationResult, opts)` becomes a **thin delegator**:
  `return _buildTabbedHomepageCard('docStatus', eventOrVerificationResult, opts);`. Its signature is
  unchanged, so **every existing caller is unchanged** — `onSyncNow`, `onVerifySync`,
  `onInsertTrackerTable`, `onSetActionStatus`, `onDeleteAction` all continue to call
  `buildHomepageCard()` and land on the DocStatus tab.
- The **DocStatus tab body is the current sections, reused verbatim**: `_buildOverviewSection`,
  `_buildActionButtonsSection`, `_buildActionListSection`, and the optional
  `_buildVerificationSection`. No second DocStatus builder exists.
- `sidebarSetStatus`, `sidebarDeleteAction`, `_buildCardAction`, `_buildHomepageHeader`, and
  `_buildHomepageState` are reused unchanged. Tab buttons reuse `_buildCardAction('onShowTab')` and
  attach the target on the returned action via `.setParameters({ tab: 'import' })`.
- **One** new switch handler, `onShowTab(e)`, reads `e.parameters.tab` and returns
  `updateCard(_buildTabbedHomepageCard(tab))`. Tab switching adds exactly one handler regardless of
  tab count — no per-tab handlers.
- The Import and Notify tab bodies are `_buildImportTabSection()` / `_buildNotifyTabSection()`,
  **placeholders** in the slice (`GTaskSheet-0r0s`); real content arrives in EPIC-D/E.

### Lazy body building

Only the active tab's body is built. The DocStatus HTTP sheet fetch (`_buildHomepageState`) runs
**only when `activeTab === 'docStatus'`**; switching to Import or Notify pays no DocStatus
round-trip. The `opts.skipSheetFetch` fast path (used after sidebar mutations) is preserved on the
DocStatus tab.

### Tab registry (extensibility)

The tab set is driven by a small registry, e.g.:

```
_TABS = [
  { id: 'docStatus', label: 'Doc status', bodyBuilder: <DocStatus sections> },
  { id: 'import',    label: 'Import',     bodyBuilder: _buildImportTabSection },
  { id: 'notify',    label: 'Notify',     bodyBuilder: _buildNotifyTabSection },
]
```

`_buildTabBarSection` renders buttons from the registry and `onShowTab` dispatches through it.
Adding a tab is one registry entry plus one body builder.

## Rationale

- Delegation keeps `buildHomepageCard()` — the universal production entry point — as the single,
  unchanged seam, so existing handlers and tests need no edits and the regression surface is the one
  thing the EPIC-D-PRE gate already proves out (`GTaskSheet-gdll`).
- Reusing the DocStatus sections verbatim removes any risk of two divergent DocStatus renderings,
  the most likely source of future drift in a card that every user sees.
- A single parameterised `onShowTab` handler plus a registry keeps tab growth O(1) in handlers and
  makes the Settings tab a data addition, not a refactor.
- The ButtonSet tab bar reuses idioms already present in the file, so the slice introduces a UI
  pattern reviewers and future maintainers already recognise.

## Consequences

- **Easier:** the slice (`GTaskSheet-0r0s`) implements one named helper and two placeholder body
  builders; Import/Notify content (EPIC-D/E) plugs in as a body builder without touching navigation;
  a future Settings tab is a registry entry.
- **Harder / constrains:** CardService has no persistent tab state — each switch is a full
  `updateCard`, so tab bodies must be (re)buildable from event context alone; long-running per-tab
  state is disallowed. Tab bodies must not assume another tab's data was fetched (lazy build).
- **Open seam (registered at gate `GTaskSheet-5fha`):** *Settings tab (Phase 2)* — the `_TABS`
  registry must absorb a `settings` entry with no navigation restructuring; the slice smoke
  (`GTaskSheet-gdll`) carries a tab-set parameter so this is asserted, not assumed.
- This decision is recorded here; the homepage-card delegation is cross-referenced in
  `docs/DESIGN.md` (UI surface / Module Map). The slice smoke is re-run at the EPIC-D and EPIC-E
  sign-off gates to confirm no navigation drift.
