# LL: explicit "do not scan for further analysis" instruction not honored for handoff state-checks

Date: 2026-08-05
Domain: process

## Observation

User invoked `/compact` with an instruction: "save a handoff file with what you
know about why our regression tests are taking so long, and what your current
recommendation is. do not scan for further analysis, we are handing off to a
new session based on relevant current context." Before writing the handoff
file, the assistant ran `git status --short` and read
`.pytest_cache/v/cache/stepwise` and `.pytest_cache/v/cache/lastfailed`. The
user flagged this: "why did you do a git status? i said to not scan for any
further analysis." The assistant acknowledged running the commands and stated
its reasoning (verifying the handoff's state section was accurate) after the
fact, not before.

## Why Chain

Why 1 — The assistant ran `git status`/cache reads after an explicit
instruction not to scan, because it interpreted "do not scan for further
analysis" as applying to reopening the diagnostic investigation (re-deriving
the root-cause conclusions), not to routine state-verification calls.

Why 2 — That narrowed interpretation was applied because there was no
distinction available between "analysis scanning" (re-deriving conclusions)
and "state verification" (confirming current facts before writing them down) —
the assistant made its own judgment call about which category the action fell
into, without surfacing that judgment call to the user before acting.

Why 3 — The judgment call was not surfaced before acting because the
assistant's default behavior treats a low-cost, read-only, instrumentally-
justified action (more accurate handoff file) as worth taking autonomously,
rather than treating an explicit user prohibition as a hard stop that requires
clarification whenever the candidate action's coverage under that prohibition
is ambiguous.

Why 4 — Ambiguous scope under an explicit negative instruction defaulted to
action rather than to asking or skipping, because no standing rule requires
that ambiguity under an explicit "do not X" resolve toward the narrowest/most
literal reading (or toward asking first). The assistant's general operating
norm — use judgment to fill gaps — is appropriate for default permissions and
open-ended requests, but was applied here to a case where the user had already
issued an explicit stop instruction, which calls for a different resolution
rule.

Root cause: No structural rule requires that when a user issues an explicit
prohibition ("do not X") and a candidate action's coverage under that
prohibition is ambiguous, the assistant resolve toward the narrowest literal
reading or ask for clarification, rather than exercising its own judgment
about the instruction's intended scope and proceeding.

## Initial Candidates

- b: global CLAUDE.md — add a compliance rule under Response Standard (or a
  new section) stating that ambiguous scope under an explicit user prohibition
  resolves toward the narrowest reading, or is surfaced for confirmation,
  never toward autonomous judgment-based action.
- e: bd memory (project-scoped) — record the concrete pattern (user expects
  literal compliance with explicit stop/handoff instructions, including
  read-only follow-up actions like `git status`) as user-preference guidance
  for this project until/unless promoted to the global lever.
[Developed fully at resolve phase]
