# Contents — <Workspace Name>

_One-line description of the workspace._

---

## Sub-Projects

| Name | Type | Tier | bd | Status | Description |
|------|------|------|----|--------|-------------|
| `sub-project-name/` | library | Minimal | ✅ | active | One sentence |

**Type values:** `library` (shared code consumed by other sub-projects), `app` (deployed application or script), `tool` (utility, CLI, or automation), `sample` (reference code, not deployed), `archive` (inactive; retained for history)

**Tier values:** `Minimal` / `Standard` / `Extended` / `—` (not yet assessed)

**bd values:** `✅` (bd in use) / `—` (no bd)

**Status values:** `active` (deployed and maintained), `staged` (built but not deployed), `draft` (in development, not yet functional), `archived` (no longer maintained)

---

## Shared Resources

| Resource | Location | Used by |
|----------|----------|---------|
| _Canonical spec or schema_ | `path/to/file` | sub-project-a, sub-project-b |
| _Shared test assets_ | `assets/` | sub-project-a |

_Remove this section if no shared resources exist._

---

## Dependency Chain

_Document runtime and build-time dependencies between sub-projects._

```
sub-project-a  (foundational)
    ↓
    └─→ sub-project-b (imports sub-project-a at runtime)
            ↓
            └─→ sub-project-c (imports sub-project-b in tests)

sub-project-d  (standalone — no cross-project dependencies)
```

_If there are no cross-project dependencies, omit this section._

---

<!--
FORMAT NOTE
-----------
This template uses the table format (concise, one row per sub-project).

For workspaces where richer per-project detail is needed, a card format is also acceptable:
each sub-project gets a narrative block with a detail table (git status, commit count,
GitHub link, etc.). See WingTools/CONTENTS.md for a reference implementation.

Both formats are valid. Choose one and apply it consistently within the workspace.
-->
