# Agent Routing — <Workspace Name>

Use this guide when starting an agent session at the workspace root.

---

## Workspace-Level Work

For cross-cutting concerns — dependency chain changes, workspace documentation, new
sub-project onboarding, cross-project ADRs, shared resource changes — work at the root.
Read `CLAUDE.md` and `CONTENTS.md` before beginning.

---

## Sub-Project Sessions

For work scoped to a single sub-project, navigate to that directory and read its `CLAUDE.md`
first. The workspace root `CLAUDE.md` is supplementary context only.

| Sub-project | Start here | When |
|-------------|------------|------|
| `sub-project-name/` | `sub-project-name/CLAUDE.md` | All work scoped to this project |

---

## Shared Resources

When a task requires reading or modifying a shared canonical resource (spec, schema, shared
test fixture), treat it as workspace-level work regardless of which sub-project triggered
the need.

---

<!--
NAMING NOTE
-----------
This template is named ROUTING.md to avoid ambiguity with AGENTS.md files that exist in
some repositories for other purposes (shell guides, bd onboarding, etc.).

If your workspace has no existing AGENTS.md, you may name this file AGENTS.md instead.
Reference the chosen name in your workspace CLAUDE.md navigation index.
-->
