# Staged plan — suite composition

**Pattern:** `$DEVSTANDARD/doc-framework/planning-guide.md` §"Pattern D: Staged Execution".
Rules are cited, not restated. Beads own all state.
**Alignment artifact:** `docs/suite-composition-deployment.md` (DRAFT) — the target deployment
architecture after stages 1–3, and the three module models stage 7 chooses between. Written
before the plan runs; reconciled against reality at the checkpoints below.

## Why this plan exists

The Northlake UU Tool Suite is one Apps Script project that will host more than one sub-app.
Today the governance exporter is a de-facto sub-app entangled with the core: its menu item is
hardcoded in `MenuHandler.js:62`, its five routes are hand-placed in `WebApp.js`'s 3161-line
`doPost`, its two `universalActions` sit in the core `appsscript.json`, and its
`registerExportConfig` deploy hook is a line in `manage-deployments.js`'s ordered list.

**The repository question is deliberately not in scope of stages 1–6.** Whether the exporter
ends up as a separate repo composed at deploy time, a pinned library dependency, or stays in
this tree as a registered plugin, *all three outcomes need the same seams*: a registry, a
composed manifest, a composed source folder, declared routes, and a sub-app test surface that
does not reach into `scn/`. Every stage before `module-decision` is therefore valuable under
all three, and none of them moves a file across a repo boundary.

`module-decision` is the gate where the owner picks the model, informed by seams that exist
rather than by an estimate.

## Measurements this plan rests on

Taken 2026-08-27 against this tree, so later stages do not re-derive them:

- `src/Procedure-Exporter.js` (1969) + `src/ExportFolderMap.js` (212): **zero** references to
  `ACT-`, `AI-N`, `TrackerTable`, `actionRow`. Only inbound core dependency is `GasLogger`
  (7 call sites).
- Exporter requires **no** OAuth scope and **no** advanced service that core does not already
  request. Its entire manifest fragment is the two `addOns.common.universalActions` entries.
- `test_governance_export.py` + `test_export_dialog.py` use exactly three members of
  `ScenarioSession`: `.doc_id` (26), `._post_route` (17), `.sheet_id` (1) — not the
  ~6000-LOC harness.
- `gas-deploy`'s `deploy()` already has a **`prePush` hook phase** documented for regenerating
  source that must be in the push (precedent: F3Go30). Composition is a hook slot, not new
  machinery.
- `document_export/` (Python, 2519 LOC) already declares itself independent of `scn/`; its
  only coupling is `tests/helpers/download.py`.

## Stage 0 — beads to file

**Closed 2026-08-27.** All 15 beads created; see the execution-order table below.
Written ahead of them: `docs/suite-composition-deployment.md` (DRAFT), the alignment
artifact. It is a draft precisely because stages 2, 3 and 4 change what it describes;
its drift checkpoints are AC lines on the beads, not notes in a document.

## Execution-order table

| # | Stage | Bead | Status | Title |
|---|---|---|---|---|
| 1 | `plugin-contract` | `gts-an8x` | ○ | [INF] Sub-app plugin contract for the Northlake UU Tool Suite |
| 1 | `plugin-contract` | `gts-3gw1` | ○ | [INF] ADR-0030: sub-apps compose into one script project via source composition and a registry |
| 2 | `deploy-compose` | `gts-qeis` | ○ | [INF] build/ source composer as a gas-deploy prePush hook |
| 2 | `deploy-compose` | `gts-unhl` | ○ | [TST] Composition assertions: collisions, contributions, and all four name-binding kinds |
| 3 | `gdx-namespace` | `gts-9omu` | ○ | [TST] Name-binding resolution coverage for all four binding kinds |
| 3 | `gdx-namespace` | `gts-hcic` | ○ | [IMP] GDX_ namespace over the document exporter |
| 4 | `route-registry` | `gts-68vz` | ○ | [TST] Auth-gate class rejection coverage |
| 4 | `route-registry` | `gts-8v8w` | ○ | [IMP] WebApp route table with declared auth gates |
| 5 | `menu-registry` | `gts-oddb` | ○ | [IMP] Extensions menu and universalActions built from the registry |
| 5 | `menu-registry` | `gts-sa9w` | ○ | [TST] Registry-driven menu entry-point coverage |
| 6 | `plugin-register` | `gts-6zed` | ○ | [IMP] Register the document exporter as sub-app #1 |
| 6 | `plugin-register` | `gts-lxfg` | ○ | [IMP] Sub-app-declared deploy hook and provenance in the deploy summary |
| 7 | `test-surface` | `gts-8xef` | ○ | [TST] Thin webapp test client, and port the exporter tests off ScenarioSession |
| 7 | `test-surface` | `gts-tygg` | ○ | [INF] Sub-app test surface contract |
| 8 | `module-decision` | `gts-ddhb` | ○ | [INF] `human` — pick the module model for suite sub-apps |

**External prerequisites** (outside these stages, must close first):
`gts-284o` (stage `document-rename`, `human`) → `gts-9omu` · `gts-2moy` (stage `docx-harness`) → `gts-8xef`

**Verify:** `bdls --stages` · `bdls --check` · `bdls --goals --stage <name>`
Status above mirrors the tracker, which stays the authority. Audit at authoring
(2026-08-27): **0 errors**, 3 warnings — all three on pre-existing stages
(`docx-verify`, `document-docs`, `document-rename`), none on these eight.

**Twin ordering is oracle-driven** (project CLAUDE.md): `gdx-namespace` and
`route-registry` are wired `[TST]` → `[IMP]` because both have a specifiable
oracle — for the rename, "every string-bound name resolves" is a precise state
writable before the change; for the routes, the gate a credential class receives
is a precise response. The remaining stages are wired artifact-first because the
thing under test must exist to be asserted against.

## Stages

### 1 · `plugin-contract`
**Drift AC:** reconcile `docs/suite-composition-deployment.md`'s registry shape and manifest-fragment schema against what this stage actually built; correct the document as part of closing the stage.
**Deliverable:** the written contract every later stage and every future sub-app is built
against, plus the ADR that fixes "one script project, one manifest" so the question is not
reopened per sub-app.
**Why paired:** the ADR is the one-paragraph decision; the interface doc is its detail. Splitting
them across sessions means the ADR is written without the detail that tests it.
**Must not:** choose the repository model. That is `module-decision`.
**Work-log:** per-stage.

### 2 · `deploy-compose`
**Drift AC:** reconcile `docs/suite-composition-deployment.md`'s deploy sequence (§A.3) and the compose/assert steps against what this stage actually built; correct the document as part of closing the stage.
**Deliverable:** `pnpm run deploy:test` pushes from a composed `build/` instead of `src/`, with
zero plugins registered and a byte-identical result — the foundation both the split model and
the library model need, proven before any source moves.
**Why paired:** the assertions are what make the composer safe to trust; a composer landing
without them is a silent-failure surface in the deploy path.
**Must not:** move or rename any exporter source. A composition regression must be unambiguous.
**Anti-pairing:** never batched with a stage that moves source (contract §Batching — never batch
across a deletion; `build/` wipe-and-rebuild is one).
**Work-log:** per-stage.

### 3 · `gdx-namespace`
**Drift AC:** reconcile `docs/suite-composition-deployment.md`'s namespace rule against the prefix actually applied; correct the document as part of closing the stage.
**Deliverable:** every exporter symbol is unambiguously the exporter's, in one mechanical diff
with no semantic change in it — clarity that pays off under every outcome, including staying
in-tree forever.
**Why paired:** the rename's real risk is six *string-bound* name sites across four binding
kinds (manifest `runFunction`, `addItem` callback, `setFunctionName`, `google.script.run.<name>`
in HTML) that fail at runtime for a user rather than at push. The coverage bead is what makes
the rename safe, not an optional follow-up.
**Why here and not first:** the prefix is an output of stage 1, and stage 2's composition assert
is the automated net for the manifest half of the failure class. Renaming before either means
doing 81 renames with no name-resolution check at all.
**Ordering note:** `gts-284o` (`human`, governance→document terminology) renames the same
symbols. Resolve it before this stage so this is one rename pass, not two — it is now a
stage-1-timeframe decision.
**Must not:** change WebApp `action` strings, GasLogger tags, or any behaviour. A semantic change
inside an 81-function mechanical diff is unreviewable.
**Work-log:** per-stage.

### 4 · `route-registry`
**Drift AC:** reconcile `docs/suite-composition-deployment.md`'s dispatch model (§A.5) against what this stage actually built; correct the document as part of closing the stage.
**Deliverable:** `WebApp.js`'s auth-gate ordering becomes declared data instead of `doPost`
statement order — worth doing on its own merits regardless of any sub-app.
**Why paired:** the gate ordering is currently untested; converting it without proving the
rejection cases is how an auth gap gets refactored in.
**Must not:** change any `action` string. Those are wire contract.
**Work-log:** per-stage.

### 5 · `menu-registry`
**Deliverable:** a sub-app can add an Extensions-menu item and a universal action without
editing a core file.
**Why paired:** entry-point coverage (project CLAUDE.md invariant) must move with the mechanism
that creates the entry points.
**Must not:** be batched with `route-registry` — the two are the same conversion applied to a
second surface, and the second session must re-derive rather than inherit (contract §Batching).
**Work-log:** per-stage.

### 6 · `plugin-register`
**Deliverable:** the exporter is a registered sub-app end-to-end while still in this tree — the
proof the contract holds, and the point after which a repo split is a file move rather than a
redesign.
**Why paired:** the source-side declaration and the deploy-hook declaration are two halves of
"core no longer names this sub-app"; either alone leaves the coupling in place.
**Why separate from `gdx-namespace`:** this stage's diff is entirely semantic. Sharing it with
an 81-function rename is how a real bug hides in mechanical noise.
**Must not:** move any file out of this repository.
**Work-log:** per-stage.

### 7 · `test-surface`
**Deliverable:** a sub-app's tests depend on the deployed wire contract, not on `scn/` — which
is what makes a separate tracker and a separate test suite viable under any of the three models.
**Why paired:** the client and the statement of what it may depend on are one decision.
**Prerequisite (ext):** `gts-2moy` (stage `docx-harness`) — offline tests blocked by
`tests/conftest.py`'s live-session autouse fixtures.
**Must not:** move Python packages between repos.
**Work-log:** per-stage.

### 8 · `module-decision`
**Drift AC:** reconcile `docs/suite-composition-deployment.md`'s three-model comparison (Part B) against what the preceding stages actually built; correct the document as part of closing the stage.
**Deliverable:** the owner's recorded choice of module model, and the beads that follow from it.
**Why single-bead:** it is a decision, not work. Carries the `human` label so it appears in
`bd human list` rather than sitting in prose.
**Work-log:** folded into the next stage's entry.

## Sequencing rationale

- **Contract before mechanism.** Stages 2, 4 and 5 each implement one face of the contract;
  writing them against a contract that does not exist yet means three sessions inventing three
  shapes.
- **Composer before everything it protects.** The composer is the only stage that changes what
  gets pushed to Google, so isolating it means a deploy regression has exactly one candidate
  cause — and its assert is the automated net the rename in stage 3 then leans on.
- **Rename before the registry, not after.** The naming shift is decision-independent and helps
  clarity under every outcome, so it should not wait behind work that might not happen. Landing
  it before stages 4-6 also means the registry is built once, against final names.
- **Mechanical and semantic diffs never share a stage.** `gdx-namespace` (81 renames, zero
  behaviour change) and `plugin-register` (all behaviour change, no renames) are deliberately
  split for reviewability.
- **Routes before menu.** Routes are the larger surface and the one with a security-relevant
  ordering property; doing it first means the menu conversion inherits a proven pattern.
- **Decision after seams.** The whole point: stages 1-7 are the work that is worth doing whether
  the answer is split, library, or stay.
