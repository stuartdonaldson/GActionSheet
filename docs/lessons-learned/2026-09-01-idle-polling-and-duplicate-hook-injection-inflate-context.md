# LL: idle polling turns and duplicate hook injection inflate session context

Date: 2026-09-01
Domain: process
Session: 9a56db38-a3e7-411b-b4fa-94cdb3e12e05 (gts-gwyg / gts-s4tr)

## Observation
Measured from the raw session transcript:

- 475 API calls consumed **98.7 M cache-read tokens** (mean 208 K/call).
- **45 assistant turns produced no work** — a `ScheduleWakeup` and/or a sentence of the form
  "Still waiting…", "Still running…", "I'll check back shortly." Those 45 turns account for
  **11.0 M cache-read tokens (~11% of total session spend)**.
- 20 `ScheduleWakeup` calls were issued at 90–300 s delays, every one of them polling a
  *harness-tracked* background task (`pnpm run deploy:test`, `pytest`) that re-invokes the
  session automatically on exit. 11 of the 20 were logged `noop: true`.
- Context at the **first tool call** was 61 K tokens, before any work. Of that,
  `hook_success` attachments totalled 210 KB across **2 records** — the `bd prime` SessionStart
  hook output (94.6 KB, 70 persistent memories) emitted twice, once as stdout and once as
  `additionalContext`, ≈52 K tokens of duplicated text.
- Context grew 61 K → 359 K over the session; tool results accounted for only ~70 K of that.

The duplicate `bd prime` injection is not specific to this session — it reproduces on every
session start in this project. `.claude/settings.json` runs `bd prime --hook-json` (SessionStart)
while `~/.claude/settings.json` (global) also runs a bare `bd prime` (SessionStart), so both a
JSON-shaped and a plain-text copy of the same 94.6 KB payload enter context.

## Why Chain

Branch A — idle polling turns
Why 1 — 45 turns were spent re-reading 200–350 K of context to emit a sentence reporting no progress.
Why 2 — `ScheduleWakeup` was used to poll background deploys and test runs.
Why 3 — The harness already re-invokes the session when a backgrounded Bash task exits, so the wakeup is redundant and usually fires first, producing a noop turn.
Why 4 — Nothing in project convention states that backgrounded deploy/test work is harness-tracked and must not be polled; the existing CLAUDE.md guidance ("route test output to a file rather than pipe to tail") covers output capture but is silent on how to wait.
Root cause A: no project rule distinguishes harness-tracked background work (which notifies on its own) from external state (which must be polled), so long-running deploy/test waits are filled with self-scheduled noop turns each costing a full context read.

Branch B — duplicate SessionStart hook payload
Why 1 — Every session begins ~52 K tokens heavier than necessary.
Why 2 — The `bd prime` output is injected twice.
Why 3 — A project-level SessionStart hook (`bd prime --hook-json`) and a global SessionStart hook (`bd prime`) both fire; hook configuration is additive across scopes, not overriding.
Why 4 — Neither hook was authored with knowledge of the other, and no check compares project and global hook configuration for duplicate commands.
Root cause B: SessionStart hooks compose additively across global and project settings with no duplicate-command detection, so the same context-injecting command can be registered twice and silently doubles the session's baseline context.

## Initial Candidates
- b: project CLAUDE.md — rule prohibiting `ScheduleWakeup` polling of harness-tracked background work (Branch A)
- b: settings — remove the redundant SessionStart hook so `bd prime` is injected once (Branch B)
- f: bd issue — evaluate whether `bd prime`'s 70-memory dump should be summarised at session start with `bd memories <keyword>` for on-demand retrieval (Branch B, follow-on)
[Developed fully at resolve phase]

## Interim resolution (2026-09-01, operator-directed)
The operator explicitly directed both branches be addressed immediately rather than deferred.
Applied same-day: see `## Applied` section below. Formal scoring/lever selection at the next
resolve pass; these are recorded as interim levers under observation.

## Applied (2026-09-01, interim — operator-directed, not a formal resolve)

Branch A (idle polling) — lever b, two artifacts:
- `~/.claude/CLAUDE.md` (global) — new §"Waiting on Long-Running Commands": background it then
  stop; no `ScheduleWakeup` against harness-tracked work; no "still waiting" turns; poll only
  external state the harness cannot observe; if an inline wait is unavoidable use one blocking
  `pgrep` loop rather than N wakeup turns. Placed adjacent to the existing §"Command Output
  Visibility", which covers *capturing* output but was silent on *waiting*.
- This project's `CLAUDE.md` §Testing Strategy — concrete instance naming `pnpm run deploy:test`
  and `pytest` as harness-tracked, with the measured cost.

Branch B (duplicate hook payload) — lever b, global settings:
- `~/.claude/settings.json` SessionStart hook changed from bare `bd prime` to a guard that skips
  when the project registers its own `bd prime` SessionStart hook:
  `d="${CLAUDE_PROJECT_DIR:-$PWD}"; for f in "$d/.claude/settings.json" "$d/.claude/settings.local.json"; do [ -f "$f" ] && jq -e '[.hooks.SessionStart[]?.hooks[]?.command] | any(test("bd prime"))' "$f" >/dev/null 2>&1 && exit 0; done; bd prime`
- Chosen over deleting either hook: 13 beads projects register their own SessionStart hook and
  would keep double-priming; 6 (F3Go30, PracticeMix, RepositoryReport, AIPraxis, Calendar Sync,
  GDriveUtils) rely on the global one and would silently lose priming if it were removed. One
  global edit fixes the whole class.
- First attempt used a plain `grep "bd prime"` over the project settings files; it produced a
  false positive on F3Go30, whose `settings.local.json` contains the *permission* entry
  `"Bash(bd prime:*)"` rather than a hook. Corrected to a `jq` query scoped to
  `.hooks.SessionStart[].hooks[].command`. Verified: SKIP for GActionSheet/GAS-Core/DevStandard/
  KGWiki, PRIME for F3Go30/PracticeMix/AIPraxis and for non-beads directories.
- Backups: `~/.claude/settings.json.bak-2026-09-01`, `~/.claude/CLAUDE.md.bak-2026-09-01`.

Verify (step 9): had these been in place at session start, the gts-gwyg session would have begun
at ~35K rather than 61K context, and the 45 idle turns (~11M cache-read tokens) would not have
been generated — the deploy/test round trips themselves are unaffected, so the 70 minutes of
wall clock stands. This lever addresses context cost, not elapsed time; the elapsed-time branches
are in `2026-09-01-live-deploy-iteration-loop-consumed-most-of-session.md`.

## Not addressed
- Global `PreCompact` hook still runs bare `bd prime`, re-injecting ~97KB after every compaction.
  Arguably intended (context recovery is the point of PreCompact), but unexamined — carry to resolve.
- Whether `bd prime`'s 70-memory dump should be replaced at session start by a summary plus
  on-demand `bd memories <keyword>`. Larger change, upstream in bd itself.
