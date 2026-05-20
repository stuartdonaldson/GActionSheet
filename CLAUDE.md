# CLAUDE.md — GTaskSheet

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


<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:7510c1e2 -->
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

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->
