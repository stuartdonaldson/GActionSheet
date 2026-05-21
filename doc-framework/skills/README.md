# Framework Skills

Global skills for managing documentation and design activities across all projects using the doc-bootstrap framework. Skills are deployed to `~/.claude/skills/` — that directory is the source of truth.

---

## Deployed Skills

| Skill | Description | Maps To |
|-------|-------------|---------|
| [session-start-check](~/.claude/skills/session-start-check/SKILL.md) | Maintenance protocol at session start | CLAUDE.md §Maintenance Protocol |
| [plan-graduation-audit](~/.claude/skills/plan-graduation-audit/SKILL.md) | Identify PLAN.md content ready to graduate | §Graduation Rules |
| [adr-quality-check](~/.claude/skills/adr-quality-check/SKILL.md) | Validate ADR format and immutability | §ADR Format |
| [doc-trigger-check](~/.claude/skills/doc-trigger-check/SKILL.md) | Identify doc updates required after changes | §Trigger Rules |
| [use-case-quality-check](~/.claude/skills/use-case-quality-check/SKILL.md) | Validate use case format compliance | §Use Case Scenario Format |
| [validate-diagram-intent](~/.claude/skills/validate-diagram-intent/SKILL.md) | Ensure diagrams answer one clear question | §Diagramming Standards |
| [layering-validation](~/.claude/skills/layering-validation/SKILL.md) | Validate abstraction layer separation | §Diagramming Standards |
| [accessibility-audit](~/.claude/skills/accessibility-audit/SKILL.md) | Check contrast and dark mode readability | §Diagramming Standards |
| [code-to-doc-consistency](~/.claude/skills/code-to-doc-consistency/SKILL.md) | Verify docs match actual code behaviour | §Trigger Rules |
| [document-structure-audit](~/.claude/skills/document-structure-audit/SKILL.md) | Find orphaned files, duplicates, broken links | §File Structure Rules |
| [ps-version-compatibility](~/.claude/skills/ps-version-compatibility/SKILL.md) | Validate PowerShell 5.1 compatibility | — |
| [bd-report](~/.claude/skills/bd-report/SKILL.md) | Generate bdreport.md — bd state snapshot with Mermaid dep graph and narrative | §Issue Tracker Integration |

---

## Adding a New Skill

1. Create `~/.claude/skills/<skill-name>/SKILL.md` directly — that file is both source and deployment
2. Add a row to the table above
3. Follow the format in `~/.claude/skills/skill-builder/SKILL.md`

*2026-03-06*
