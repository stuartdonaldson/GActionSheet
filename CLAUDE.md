# CLAUDE.md — GActionSheet

**Tier:** Standard
**Standards:** /doc-framework/doc-standard.md _(read-only — do not edit)_

<!-- Framework sections — managed by the framework.
     On framework upgrade, replace from ## Reading Order through ## Memory System
     with the updated content from the CLAUDE.md template. Preserve all sections
     above this comment and any project-specific sections added below. -->
## Reading Order
1. Current state — `bd prime` _(bd in use)_
2. CONTEXT.md — purpose, capabilities, use cases
3. DESIGN.md — architecture, modules
4. OPERATIONS.md — how to run it
5. /knowledge-base/adr/ — why key decisions were made
6. /knowledge-base/references/ _(optional)_ — external document summaries

## Document Map
| Content | Default Location |
|---------|---------|
| Purpose, capabilities | CONTEXT.md |
| Quality goals, stakeholders | CONTEXT.md |
| Glossary | CONTEXT.md §Glossary |
| Architecture, modules, data model | DESIGN.md |
| Deployment, configuration, failure modes | OPERATIONS.md |
| Current state | `bd ready` |
| Identified work | bd |
| Technical decisions | /knowledge-base/adr/ |
| Protocol details | /docs/interfaces/ _(optional)_ |
| External doc summaries | /knowledge-base/references/ _(optional)_ |
| Security model | docs/security-architecture.md |

## Placement Rules
- New capabilities → CONTEXT.md §Core Capabilities + use case if actor-driven
- Architecture changes → DESIGN.md + affected diagrams
- New risk identified → `bd remember`
- Operational changes → OPERATIONS.md
- Resolved decisions → /knowledge-base/adr/
- New terms → CONTEXT.md §Glossary
- Protocol detail → /docs/interfaces/[protocol].md _(optional)_
- Do not create new top-level document types — consult doc-standard.md §Tier Overview for tier guidance

## Maintenance Protocol

Claude does not monitor documents between sessions, detect drift, or update documents
without explicit instruction.

- At session start or phase transition: run `/session-start-check`
- After any code or architecture change: run `/doc-trigger-check`
- To trigger a state review: "review project state before we start"

## Memory System
| System | Scope | Use for |
|--------|-------|---------|
| `bd remember` / `bd memories` | Project-scoped | Project rationale, design decisions, process insights — travels with the repo |
| MEMORY.md (auto-memory) | User-scoped | User preferences, cross-project style conventions |

Do not use MEMORY.md for project rationale. Do not use `bd remember` for user preferences. When in doubt: if the insight is about a specific codebase or project decision, use `bd remember`; if it applies regardless of repo, use MEMORY.md.


<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:970c3bf2 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   bd dolt push
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->

## python
`/mnt/c/dev/venvs/uv1/bin/python3` is the best python interpreter to use with it's virtual environment

## Querying Axiom Logs

Use `python scripts/query_axiom.py` — don't hand-roll the Axiom APL query/auth again.
Reads `axiomDataset`/`axiomQueryToken` from `local.settings.json`. Examples:

```bash
python scripts/query_axiom.py                          # last 200 events, last 24h
python scripts/query_axiom.py --limit 50 --since 2h
python scripts/query_axiom.py --side python             # or --side gas
python scripts/query_axiom.py --name sync.warn
python scripts/query_axiom.py --where "data.docId == '1AAE...'"
python scripts/query_axiom.py --raw /tmp/dump.json       # full JSON for offline analysis
```

## Calling the WebApp Manually

`python scripts/call_webapp.py` is the **only** sanctioned way to call the GAS WebApp
outside of a pytest run — never hand-roll `curl`/`urllib` against `webappTestUrl` directly.
It reads `webappTestUrl`/`webappProdUrl`/`webappDevUrl`, `testToken`, and `webappSecret`
from `local.settings.json` and picks the correct auth field automatically (`secret` for
production-gated routes, `testToken` for test-support routes — see `WebApp.js`'s `doPost`
gate order). The WebApp deployment is `access:ANYONE_ANONYMOUS`, so no OAuth/Authorization
header is needed or supported for external callers — auth lives entirely in the JSON body.

Manual `curl`/`urllib` calls are exactly how mistakes happen: missing the `secret` field
(silently returns `unauthorized`), mishandling the `/exec` → `script.googleusercontent.com`
redirect, or hitting the wrong environment. `call_webapp.py` encodes the same error handling
as `scn.session.ScenarioSession._http_post` (the pytest harness's own POST helper) so a
manual probe fails with the same diagnosable message a test run would produce — including
flagging GAS deployment-propagation lag (non-JSON/echo-page response right after a redeploy)
instead of a bare traceback.

```bash
python scripts/call_webapp.py get_test_config
python scripts/call_webapp.py begin_journey_session
python scripts/call_webapp.py run_fixture --data '{"fixture": "sync_all"}'
python scripts/call_webapp.py mark_doc_not_found --data '{"docIds": ["abc123"]}'
python scripts/call_webapp.py end_journey_session --data '{"docId": "abc123"}'
python scripts/call_webapp.py sync_action_rows --env prod --data '{"docId": "abc123"}'
```

## Testing Strategy & Issue Conventions

This project follows the ATDD lifecycle. Authoritative sources (all legacy
references are mapped in `docs/atdd/ID-map.md` — start there):
- **Universal testing & lifecycle principles** (`T1`–`T24`, `I1`–`I11`: entry-point coverage + call-site, durable-state assertion, negatives, idempotency, run-isolated clones, expectation-queue/checkpoints, permutation batching, twin-track independence) → DevStandard `knowledge-base/methodology/testing/bdd/sdlc-testing-principles.md` and `sdlc-implementation-principles.md`. Cite the ID, don't restate.
- **GAS+Python acceptance-testing mechanics** → GAS-Practices `best-practices/gas-acceptance-testing/`.
- **Project realization** (the `scn/` scenario model, canonical journey, contract) → `docs/atdd/ID-map.md` (§`scn/` module map) and archived source `docs/atdd/archive/atdd-lifecycle.md` §15–§16.

For long running tests, always route test output to a fail rather than pipe to tail so we have the file for later analysis and to use to monitor progress of the test.

Every Playwright/UI test failure must, as a matter of course, capture a screenshot + diagnostics (screenshot path, frame URLs, and for locator waits the per-frame match-count / is_visible / bbox). This is automated (gts-3tkf): bounded driver waits call `UiDriver.capture_failure(...)` before raising, and a `pytest_runtest_makereport` hook in `tests/conftest.py` screenshots the active page on any UI-test failure. Add a new bounded wait? Route its failure through `capture_failure` — never copy-paste a capture block. For interactions Playwright cannot drive with a direct mouse gesture (e.g. the `onLinkPreview` link-preview card), try the `Ctrl+F` -> type -> `Enter` -> `Escape` cursor-placement technique (gts-39jk/cug8, `UiDriver.open_link_preview`, `tests/test_link_preview.py`) before falling back to a non-UI route-fallback method — see epic gts-pw5x.

Methodology declaration — Testing: `atdd-bdd` — DevStandard `knowledge-base/methodology/testing/bdd/README.md`. Key rules for every session:

**Issue title prefixes (required on all new issues):**
- `[IMP]` — GAS implementation work
- `[TST]` — Python test/fixture work
- `[FIX]` — bug or regression fix
- `[INF]` — infrastructure, deployment, CI

**Twin-ticket rule:** every new feature AC, once frozen, gets a paired `[IMP]` + `[TST]` issue created at the same time. Neither merges until both are green. Test-first is preserved: "first" is relative to the frozen AC. If an AC-validation slice phase was used (see below), the hardening `[TST]` is created at the freeze gate, not at slice start.

**Pre-code contract:** before either ticket starts coding, document in the issue description: (1) GAS entry-point signature, (2) GAS log tag that signals completion, (3) output schema (XLSX columns / DOCX structure) the test will assert against.

**`[INF]` design-bead authoring:** when an `[INF]` bead's deliverable is an artifact consumed by downstream beads, `--description` (scope of the artifact), `--acceptance` (done criteria), and `--design` (questions the artifact must answer) are required at creation time. An `[INF]` bead with empty content fields is incomplete — downstream `[IMP]`/`[TST]` beads are not created until it is workable.

**No shared context:** the `[TST]` owner must not read GAS implementation; the `[IMP]` owner must not read test assertions. The contract is the only shared artifact.

**Review-fidelity phasing (ADR-0013):** an optional AC-validation phase may be inserted *upstream* of the twin-ticket cycle. Use the lowest fidelity that can surface design error:

| Fidelity | Review artifact | Default? |
|----------|-----------------|----------|
| Spec | written design / contract prose | ✓ default |
| Slice | thin concrete instance (sample schema, stub interface, happy-path journey) + smoke on durable invariants | justify |
| Hardened | full test matrix + industrialised build | twin-ticket phase |

Rules when choosing Slice:
- **Justification required:** state explicitly why Spec review is insufficient — that the design error is only visible in a concrete artifact.
- **Smoke asserts durable invariants only.** Volatile surface (field list, column set, UI copy, journey edge cases) stays untested until the gate freezes the AC.
- **The gate has three outputs:** (a) verdict (approve → harden, or redesign); (b) funnel deltas — newly-seen opportunities captured as one-liners in ROADMAP §Funnel, non-committal; (c) open-seams register — recorded in the hardening bead's `design` field so hardening tests assert the invariant a known future direction will share.
- **"Keep open" ≠ "build now."** An open seam must be expressible as a one-liner + a test parameter. Anything larger goes to ROADMAP §Funnel for value/risk evaluation — not pulled into the current slice.
- **No-shared-context preserved at hardening.** The slice implementation is throwaway, or the hardening `[TST]` is authored by a fresh-context agent against the frozen contract only — never reading slice code.
- **Blocking hardening bead required.** The gate produces a *created, blocking* hardening bead. Slice is not done until its hardening `[TST]` is green; the entry-point coverage invariant still holds.

**Ordering is oracle-driven; coverage-before-merge is the invariant _(lever under test — gts-m65t; candidate for DevStandard T23 promotion, see `docs/methodology/oracle-ordering-lever.md`)_.**
"Test-first" bundles two claims; only one is load-bearing. **Coverage-before-merge** — durable invariants and every state-modifying entry point (T17) are tested before merge — is non-negotiable. **Ordering** — whether the test is written before the implementation — is chosen by the *oracle*:
- **Specifiable oracle** (correct answer is a precise value/state you can write down before coding — parsed value, row status, contract shape): **test-first** (red → green). Debugging the test *is* debugging the contract.
- **Perceptual oracle** (you recognize "correct" on sight but cannot cheaply pre-specify it — most UI/UX, rendered output, layout/feel): **Slice** (implement-first → human review → freeze AC → author hardening `[TST]` against the frozen contract). A pre-written assertion here is both expensive *and* blind to the emergent anomaly the human eye catches. State why an assertion cannot cheaply pre-specify "correct."

When implement-first is chosen, three guardrails keep the coverage invariant honest (all already in force above): (1) harden the durable invariant, not the volatile surface still under review; (2) blocking hardening `[TST]` bead — slice not done until green; (3) the hardening assertion is proven to fail against the frozen contract (Backstop rules, below). *Diagnostic:* if the test is dramatically harder to write than the implementation, that asymmetry names the regime — immature harness (invest and amortize), perceptual oracle (use review, harden only the invariant), or a churning contract (slice first).

**Existing open issues** are not retroactively renamed — apply the prefix convention to all issues created from this point forward.

**Regression coverage — retroactive path (Path B):** when a bug or user-reported failure identifies
a missing test, the fix must be accompanied by a `[TST]` issue that closes the coverage gap. The
`[TST]` issue must audit the full entry-point class for the affected subsystem — not only the
specific failure. Enumerate all state-modifying entry points (menu items, time-based triggers,
sidebar buttons, HTTP routes) in the same functional area and verify each appears as a call-site
in ≥1 test scenario. This applies regardless of whether ATDD was followed at development time.

**Entry point coverage invariant:** the regression suite must exercise every state-modifying entry
point at least once with observable state verification. The entry point itself must be the
call-site — testing only the mechanism it delegates to is not sufficient. Standalone or sequential
test structure is not required; the entry point may be exercised as part of any scenario.

**Backstop rules (LL resolve, gts-mpi9; scope narrowed 2026-07-24 — see below):**
- `pytest -x` (full suite, not just the touched files) is required at **merge-gate**, and always
  before a hardening `[TST]` (gts-79dw.4.8-style) is itself closed. This is the enforcement point
  both source incidents actually pointed at (`2026-06-02-scanner-change-did-not-audit-fixture-
  producers.md`, `2026-06-02-test-failures-observed-but-not-elevated-to-blocker.md` — both
  resolutions say the fix belongs in `merge-gate`, not at `[IMP]`-close).
- An `[IMP]` bead may **close** on a fast, targeted-subset gate (touched-file/related tests —
  practically, whatever runs in well under a couple minutes) instead of the full suite. This is
  the normal path for a Slice-phase bead (Review-fidelity phasing, ADR-0013 above): implement,
  get the fast gate green, close, and get to a reviewable working experience without paying full
  regression cost before the AC is even frozen. Track the gap explicitly rather than silently: on
  close, set `bd set-state <id> regression=pending --reason "<what actually ran>"`; flip it to
  `regression=verified` once `pytest -x` is run clean against that bead's changes. `bd-run-beads.py`
  does this automatically (`--partial-gate` marks `regression=pending`; a full unrestricted
  `test_cmd` marks `regression=verified`; `-t ''` always implies `pending`).
- Merge-gate (or manual merge to master) still requires every bead in scope to be
  `regression=verified` — i.e. full `pytest -x` clean — before it passes. A bead closed with
  `regression=pending` is not itself blocking further implementation work in the same tree; it
  blocks that tree's merge.
- Known test failures are not a basis for proceeding autonomously: present the debt state (which
  tests fail, why) and wait for an explicit human decision rather than working around or ignoring
  the failure.
- Any scenario test that calls `verify_consistency()` must also call `verify_all_expectations(a)`
  for at least one action. This prevents `verify_consistency()` from passing vacuously when the
  preceding sync produced no detected items (`docs/lessons-learned/resolved/2026-06-02-new-assertion-vacuously-passes-on-empty-result-set.md`).
- A new integrity/quality assertion must be proven to fail before acceptance: demonstrate that it
  fails when the condition it checks is violated, not only that it passes on the current suite.
  A new assertion that only shows green is unverified.

## GAS Deployment

Use the pnpm scripts in `package.json` — never invoke `clasp` directly.

| Goal | Command |
|------|---------|
| Deploy for test cycle | `pnpm run deploy:test` |
| Deploy to production | `pnpm run deploy:prod` |
| Push only (no redeploy) | `pnpm run push` |

`clasp logs | tail -50` to look at the last 50 lines of the logs in the cloud google apps server environment
`pnpm run deploy:test` runs `update-revision.js` + `manage-deployments.js --deploy-prod`
in one step. Running `clasp push` (or `pnpm run push`) alone leaves the versioned
WebApp deployment stale — the test suite will call the old revision and produce
`sync.warn: Non-JSON response` failures.
