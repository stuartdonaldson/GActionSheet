# GActionSheet Activity, 2026-08-01 to 2026-08-13

_Mined from Claude Code session transcripts via session_miner.py. Organized by feature/functionality pursued, not strictly by calendar day; objectives inferred from narrative, outcomes not explicitly confirmed are marked (inferred)._

## Team Action Portal — cross-team action visibility
**2026-08-01 – 2026-08-02**

What was wanted: a way for a team member to see and act on open actions belonging to *other* teams' documents — a shared web portal (read view + write-back view) sitting alongside the per-doc sidebar add-on, with its own auth model so different account types could exercise it.

What shipped: the portal itself (View A read-only + View B write-enabled, static-site published to a sibling repo, a multi-account Playwright auth taxonomy for testing it) was already built going into this window. This period's work was getting it landed: publishing the live SIT site, merging the portal branch alongside a parallel batch-fix branch, and closing out reviewer findings.

Refinement: addressed reviewer (Copilot) findings on both merge PRs — a fixture case that was silently corrupting test state via a default-case fallback, unguarded `None`-handling in log cleanup, stale terminology in test docstrings, and a missing auth helper module on one branch. Flagged (rather than silently changed) a bootstrap-secret race condition as a design question needing the developer's call.

## Inline text formatting survives sync (bold/italic round-trip)
**2026-08-01**

What was wanted: if someone manually bolds or italicizes part of an action's text in the Google Doc, that formatting should still be there after GActionSheet syncs the action — not flattened back to plain uniform styling.

What shipped: scan → sheet (as rich text) → flush → rescan round-trip for inline bold/italic, implemented with offset-tracking so formatting survives the scanner's existing text transforms. Required a real product decision (ADR-0022): configFormat's uniform action-text styling no longer forces bold/italic, so per-word formatting can win — approved by the developer and shipped as the default.

## Sync integrity & performance — no duplicate rows, no concurrent corruption, faster multi-doc sync
**2026-08-01**

What was wanted: the developer reported the same action item showing up multiple times in the Action sheet after a sync, and separately wanted assurance that syncing wouldn't corrupt data if two sync operations overlapped, plus a standing ask that the (pre-existing) batched-sync performance epic get finished.

What shipped: a dedup pass that collapses rows sharing a globalId back to one canonical row on every sync sweep; an advisory per-document sync lock (`syncDocument` now skips rather than corrupts state if another execution already holds the lock for that doc); and completion of the multi-part batched-sync performance epic (already in flight), each proven live with a genuine revert/fail/restore Backstop cycle before being accepted.

## Test-run visibility (progress + duration-regression flagging)
**2026-08-06**

What was wanted: while iterating on the test suite, the developer asked for automated, always-on visibility into how far a long test run had progressed and whether any individual test had gotten unexpectedly slower than its own history — surfaced automatically (stderr + an append-only trend log), not something requiring an LLM to read and summarize.

What shipped: a report-only instrumentation layer — `[n/total]` progress on every test, per-phase (setup/call/teardown) durations, a self-calibrating local baseline, and an automatic `⚠ SLOW` flag when a test exceeds its own baseline by both a percentage and an absolute-time threshold. Deliberately never affects pass/fail — proven with a standalone scratch harness before being wired into the real suite.

## Flexible, team-defined fields on action items (proposed, not shipped)
**2026-08-06**

What was wanted: the developer wanted teams to be able to attach their own free-form fields (e.g. `Target:`, `Progress:`) to an action item in the doc's own text, without losing the doc as the readable source of truth, and floated renaming the in-text token from `AI-N:` to `ACT-N:` as part of that.

What shipped: design only. After several rounds of scoping (rejecting a JSON-in-`action_text` approach and a global color→author legend, in favor of a separate `custom_fields` column and per-unit-scoped signals), two ADRs were drafted — dual-prefix `ACT-N`/`AI-N` token support (superseding ADR-0008) and a `custom_fields` JSON column — both left `Status: Proposed`. No implementation work was done against them in this window.

## Governance/Procedure Exporter — Doc-to-structured-JSON export for LLM consumption
**2026-08-11 – 2026-08-13**

What was wanted: take a governance-style Google Doc (policies, procedures, articles) and export it as structured JSON an LLM could reliably query — locating comments against the section/paragraph they apply to and back again, distinguishing historical/superseded text from current text, and (optionally) a PDF snapshot — reachable as an action from inside the document, not just via manual script runs.

What shipped: a full exporter (`Procedure-Exporter.js`) producing a versioned JSON schema with unit hierarchy (`parent_unit_id`), tiered exact/cross-paragraph/fuzzy comment-to-block matching with an explicit reliability ranking (`suggestion_groups` as the trustworthy signal, comment-anchored/bare highlight-color as lower-confidence hints), and a PDF-snapshot option. Entry points moved from a menu that collided with the sheet add-on's own `onOpen()` into the modern add-on framework (`universalActions` + a sidebar card section), plus 3 real bugs fixed along the way (autoText runs silently dropped, a hardcoded confidence flag, mistagged table-cell metadata).

Refinement: after the developer found the Extensions-menu entry wasn't appearing, added a sidebar "Export JSON" / "Export JSON + PDF" button as a reliable fallback entry point once the menu issue turned out to be environment configuration, not code (see lessons below). Renamed the user-visible "Governance Export" labeling to generic "Export" once the developer pointed out the exporter isn't governance-specific. Built the first CardService-driving test harness in the repo and used it to close out the hardening-test twin ticket, which in the process surfaced and fixed two more real bugs (a regex whose word-boundary assertion could never match realistic input; unit-kind classification not stripping a leading state marker).

---

## Notable defects / prompting lessons

- **Multi-day Google Apps Script `/exec` routing flakiness (2026-08-02 → 2026-08-07).** Full-suite regression runs kept dying on transient Google-frontend routing failures (echo pages, stray 404/302s, self-call timeouts) that are undetectable in GAS's own execution logs — a known, externally-documented, still-unresolved class of Google infrastructure flakiness, not a code defect. Cost roughly a week of elapsed time across several sessions, including one night where 15 hours produced only ~10% suite progress partly because of an unrelated monitoring bug (a `nohup`+`tail -f` watcher that silently stopped following). Ultimately resolved by abandoning `--sw` for full-suite runs, adding a generalized retry-wrapper utility with call-site logging, and accepting that isolated live-backend attempts will occasionally need a human triage call rather than automatic retry. **Lesson:** for a live-Google-backend test suite, a "run the full regression" request should specify a non-stop-on-first-failure mode up front, since the default stepwise behavior turns ordinary infra noise into repeated full-context stop/diagnose/resume cycles.
- **Governance exporter's Extensions-menu entry appeared to be a code regression but wasn't (2026-08-11 → 2026-08-12).** After adding the exporter's menu entries, the Extensions-menu stopped showing the add-on at all — chased for the better part of a day (manifest schema checks, a same-code-three-weeks-ago worktree test, sidebar-vs-menu registration theories) before the developer identified the actual cause: a stale Workspace Add-ons API version pointer in the Marketplace SDK's Application Configuration, unrelated to any code in this window. **Lesson:** when a Workspace add-on's menu/UI registration breaks right after a manifest or deploy change, checking the Marketplace SDK / Cloud project's linked deployment-version config is a cheaper first step than treating it as a code bug.
- **PDF export worked from the Apps Script editor's Run button but failed for the real user through the installed add-on (2026-08-13).** `urlFetchWhitelist` didn't cover the Docs UI host used for PDF export, but that restriction is only enforced when code runs through the actual installed deployment — not a manual editor Run. **Lesson:** for Apps Script add-ons, "it worked when I ran it" isn't sufficient proof if it wasn't run through the actual add-on entry point being shipped.
