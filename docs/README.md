# Documentation — GActionSheet

<!-- Planning and Documentation Framework section — managed by the framework.
     On framework upgrade, replace this entire section (from the h2 heading to the
     closing horizontal rule) with the updated version. All other content in this
     file is project-specific and must not be modified during upgrade. -->

## Planning and Documentation Framework

**Framework Version:** `2.3.0` | **Tier:** `Standard` | **Applied:** `2026-05-19`

This project follows the [DevStandard documentation framework](../doc-framework/README.md).
Framework files are in `/doc-framework/` — read-only reference copies updated from the
central tooling location.

---

### Document Structure

**Standard tier** — separate documents in `/docs/`:

| Document | Purpose | Tier |
|----------|---------|------|
| `docs/CONTEXT.md` | Goals, constraints, use cases, glossary | Standard + Extended |
| `docs/DESIGN.md` | Architecture, building blocks, runtime view | Standard + Extended |
| `docs/OPERATIONS.md` | Deployment, configuration, failure modes | Standard + Extended |
| `knowledge-base/adr/` | Architecture decision records | All tiers |

Architecture decision records are immutable once Accepted. See `doc-framework/doc-standard.md §ADR Format`.

---

### Issue Tracking

This project uses **bd (beads)** for issue tracking.

```bash
bd prime    # session context and ready work
bd ready    # available work (unblocked, prioritized)
bd show <id>          # issue detail
bd update <id> --claim  # claim work
bd close <id>         # mark complete
```

---

### Session Start

```
review project state before we start
```

This triggers a check of document sizes, open decisions, and graduation candidates before
beginning work.

---

### Document Templates

Templates for creating new framework documents are in `/doc-framework/templates/`. Use the
corresponding template when adding a new document type to this project.

---

### Framework Updates

To update the framework in this project:

1. Copy updated framework files from the central tooling location into `/doc-framework/`
2. Replace the "Planning and Documentation Framework" section in this file with the updated
   `templates/planning-docs-README.md`, filled in with this project's tier and applied date
3. Review the reconciliation report for any new or changed sections in project documents
4. Do not remove project-specific content during the update

---
