# LL: skill not invoked when user named it as a noun phrase without slash prefix

Date: 2026-05-27
Domain: process

## Observation
User message: "do a lessons-learned on this, as there should have been a test case for it…"
The word "lessons-learned" named an available skill explicitly. The assistant did not invoke the skill.
Instead it performed inline manual analysis, called `bd remember`, and returned a prose summary.
The user had to follow up: "i specifically said to do a lessons-learned, why did that not invoke the
lessons-learned skill?" before the skill was invoked.

## Why Chain
Why 1 — The assistant executed the task directly rather than routing through the named skill
Why 2 — The assistant treated "do a lessons-learned" as a task description, not a skill invocation
Why 3 — The governing rule reads "When the user types `/<skill-name>`, invoke it via Skill" — this only specifies the slash-prefix form; no rule covers a skill named as a natural-language noun phrase
Why 4 — The skill's own auto-trigger keywords ("lesson", "root cause", "post-mortem") are defined inside the skill file, which is only readable after invocation — the agent cannot see auto-trigger rules before the skill fires
Why 5 — No rule states "if the user's message contains a known skill name as a noun or verb phrase, invoke the skill even without /"
Root cause: The instruction governing skill invocation only specifies the `/<name>` prefix form; there is no rule for recognising a skill by its name in natural language, so the agent defaults to executing the task inline.

## Initial Candidates
b: add to global CLAUDE.md — "if the user's message contains a known skill name (with or without slash), invoke the skill via the Skill tool before executing the task directly; slash prefix is not required"
c: not applicable — skill auto-trigger rules are inside the skill file and unreadable before invocation; the fix must be in the governing instruction layer, not inside the skill
