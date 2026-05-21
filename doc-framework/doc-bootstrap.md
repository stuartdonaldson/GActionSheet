# Repository Documentation Bootstrap Prompt

**Use this prompt for:** all project tiers — Minimal, Standard, and Extended.
Tier is determined during DocPhase 1 Discovery. If the tier is already known,
the tier-specific rows are marked throughout.

**Standards reference:** All use case formats, ADR formats, diagramming standards, writing
standards, graduation rules, trigger rules, and story rules are defined in
`doc-standard.md`. Apply them here without modification.

**Do not generate document content until explicitly instructed. Follow phases in order.
Stop at each confirmation gate.**

---

## Objectives

| Objective | Minimal | Standard | Extended |
|-----------|---------|----------|----------|
| Developer context reload in ≤10 minutes | ✓ | ✓ | ✓ |
| Optimized for Claude Code and GitHub Copilot | ✓ | ✓ | ✓ |
| Concise, technical writing — no marketing tone | ✓ | ✓ | ✓ |
| Single-file documentation for fast navigation | ✓ | — | — |
| Strict separation of concerns across document types | — | ✓ | ✓ |
| No duplicated definitions across documents | — | ✓ | ✓ |
| External reference material summarized for AI access | — | ✓ | ✓ |
| Full arc42-aligned coverage | — | — | ✓ |

---

## Target Structure

**See doc-standard.md §File Structure and Placement Rules for universal file placement.**

**Minimal:**
```
README.md       — CONTEXT, DESIGN, OPERATIONS combined in single file
PLAN.md
CLAUDE.md
adr/
docs/           — optional, for assets and references
```
CONTEXT, DESIGN, and OPERATIONS content lives in README.md under named sections that
mirror the full-scale document names exactly. This preserves terminology and makes
graduation to Standard tier straightforward.

**Standard:**
```
/docs/
    CONTEXT.md
    DESIGN.md
    OPERATIONS.md
    adr/
    assets/         [if applicable]
    interfaces/     [if applicable]
    references/     [if applicable]
```

**Extended:**
```
/docs/
    CONTEXT.md
    DESIGN.md
    OPERATIONS.md
    QUALITY.md
    adr/
    assets/         [if applicable]
    interfaces/     [if applicable]
    references/     [if applicable]
```

Subfolders under `/docs/` only when: a section exceeds ~400 lines, the area has a
distinct maintainer team, or it represents a runtime or protocol boundary requiring
independent reference depth. DESIGN.md is always the technical index.

---

## Templates

Document scaffolding for DocPhase 2 is in `doc-framework/templates/`. Copy the relevant
files when creating the scaffold — do not transcribe content from this prompt.

| Template File | Minimal | Standard | Extended | Workspace |
|--------------|---------|----------|----------|-----------|
| `framework-README.md` | ✓ | ✓ | ✓ | ✓ |
| `README-minimal.md` | ✓ | — | — | — |
| `CONTEXT.md` | — | ✓ | ✓ | Optional |
| `DESIGN.md` | — | ✓ | ✓ | Optional |
| `OPERATIONS.md` | — | ✓ | ✓ | — |
| `QUALITY.md` | — | — | ✓ | — |
| `PLAN.md` | ✓ | ✓ | ✓ | — |
| `PLAN-bd.md` | ✓ | ✓ | ✓ | — |
| `BACKLOG.md` | — | ✓ | ✓ | — |
| `CLAUDE.md` | ✓ | ✓ | ✓ | ✓ |
| `CONTENTS.md` | — | — | — | ✓ |
| `ROUTING.md` | — | — | — | Optional |

---

## Phase Overview

All tiers follow the same discovery, planning, scaffold, and migration process. Follow phases in order; stop at each confirmation gate.

**DocPhase 1 — Discovery**
Inventory existing documentation, identify gaps, analyze current state. Produces repository summary, inventory table, orphan list, gap analysis, redundancies, likely ADR candidates, external document inventory, structural risks. Tier selection occurs here.

**DocPhase 1.5 — Disposition Planning**
Convert every gap, orphan, and structural risk into an explicit recommendation. Operator reviews and decides. No files created; planning only.

**DocPhase 2 — Scaffold Creation**
Install framework files into `/doc-framework/`. Create document structure with section headers and `[If applicable]` stubs per tier templates. Create CLAUDE.md. Create PLAN.md and BACKLOG.md only if bd is not in use. No generated content at this stage.

**DocPhase 3 — Migration Plan**
Produce detailed, reviewable migration plan covering file operations, content gaps, diagrams, references, and execution order. Record Migration Losses and Orphaned Content in `/knowledge-base/ORPHANED-CONTENT.md`. Operator approves before any existing file is modified.

---

## DocPhase 1 — Discovery

Read before doing anything else:
- All files in the repository root
- All files under `/docs/` (recursive) [Standard and Extended]
- README, CHANGELOG, CONTRIBUTING files
- Any existing architecture, design, or decision documents regardless of name or location
- Any reference PDFs or external documents stored in the repository

Produce:

**1. Repository Summary**
Two to three sentences: purpose, primary language and framework, deployment model.

**2. Inventory Table**

| File | Inferred Purpose | Target Location | Action |
|------|-----------------|-----------------|--------|

**3. Orphan List**
Content with no clean target location. Standard and Extended: also check for inline
rationale in READMEs, decisions recorded only in PRs, tribal knowledge, and protocol
knowledge embedded in code. Extended: also check for risk/debt items and informally
stated quality requirements.

**4. Gap Analysis**

*Minimal tier:*
| Target Section | Status |
|---------------|--------|
| README.md §CONTEXT — Introduction & Goals | Ready / Needs rewrite / Must be authored |
| README.md §CONTEXT — Constraints | Ready / Needs rewrite / Must be authored / Not applicable |
| README.md §CONTEXT — Capabilities | ... |
| README.md §CONTEXT — Use Cases | ... |
| README.md §CONTEXT — Non-Goals | ... |
| README.md §CONTEXT — Glossary | ... |
| README.md §DESIGN — Solution Strategy | ... |
| README.md §DESIGN — Runtime Architecture | ... |
| README.md §DESIGN — Building Block View | ... |
| README.md §DESIGN — Runtime View | ... |
| README.md §DESIGN — Data Model | ... |
| README.md §OPERATIONS — Deployment | ... |
| README.md §OPERATIONS — Configuration | ... |
| README.md §OPERATIONS — Failure Modes | ... |

*Standard tier:*
| Target Section | Status |
|---------------|--------|
| CONTEXT.md — Introduction & Goals | Ready / Needs rewrite / Must be authored |
| CONTEXT.md — Quality Goals | ... |
| CONTEXT.md — Stakeholders | ... |
| CONTEXT.md — Constraints | ... |
| CONTEXT.md — Core Capabilities | ... |
| CONTEXT.md — Use Cases | ... |
| CONTEXT.md — Non-Goals | ... |
| CONTEXT.md — Glossary | ... |
| DESIGN.md — Solution Strategy | ... |
| DESIGN.md — Runtime Architecture | ... |
| DESIGN.md — Building Block View | ... |
| DESIGN.md — Runtime View | ... |
| DESIGN.md — Deployment View | ... |
| DESIGN.md — Data Model | ... |
| DESIGN.md — Crosscutting Concepts | ... |
| DESIGN.md — Dependency Rules | ... |
| OPERATIONS.md — Deployment | ... |
| OPERATIONS.md — Configuration | ... |
| OPERATIONS.md — Monitoring | ... |
| OPERATIONS.md — Failure Modes | ... |
| OPERATIONS.md — Recovery Procedures | ... |

*Extended tier (use Standard table and add):*
| Target Section | Status |
|---------------|--------|
| CONTEXT.md — Constraints (Technical) | ... |
| CONTEXT.md — Constraints (Organizational) | ... |
| CONTEXT.md — Constraints (Regulatory) | ... |
| DESIGN.md — Building Block View (L1) | ... |
| DESIGN.md — Building Block View (L2) | ... |
| QUALITY.md — Quality Tree | ... |
| QUALITY.md — Quality Scenarios | ... |
| QUALITY.md — Risks | ... |
| QUALITY.md — Technical Debt | ... |
| OPERATIONS.md — Audit and Compliance | ... |

**5. Redundancies** [Standard and Extended]
Duplicate definitions and where the canonical version will live. For each redundancy,
note whether both sources are available in the same deployment context — apparent
redundancy may be compensating for a dependency that is absent in some contexts.

**6. Likely ADR Candidates**

| Decision | Current Location | Suggested Status |
|----------|-----------------|-----------------|

**7. External Document Inventory**
[If applicable]

| Document | Location | Format | Relevance | Action |
|----------|----------|--------|-----------|--------|

**8. Scaling / Tier Assessment**
- [Minimal] Does this project already exceed Minimal tier threshold? If yes, recommend
  running against Standard tier.
- [Standard] Does this project already exhibit Extended tier signals? If yes, recommend
  running against Extended tier.

**9. Structural Risks**

| Risk | Detail |
|------|--------|

> **Stop. Confirm inventory, repository summary, and tier assessment with operator
> before proceeding.**

---

## DocPhase 1.5 — Disposition Planning

Convert every gap, orphan, and structural risk into an explicit recommendation.
Do not create files or modify content in this phase.

Classify each item using the following action types:

| Action | When to Use |
|--------|-------------|
| `Extract` | Content exists and belongs in a target document as-is or with minor rewrite |
| `Reconstruct` | Content existed previously but was removed; must be rebuilt from known source before that source is deleted |
| `Author` | No source exists; must be written from scratch |
| `Summarize` | External document exists; create AI-readable summary in /knowledge-base/references/ |
| `ADR — Accepted` | Decision is resolved; rationale exists; ready to write as accepted ADR |
| `ADR — Proposed` | Decision is real but unresolved; create stub ADR with open question in consequences field |
| `Stub` | Content is future-facing; create placeholder section in target document |
| `Hold in PLAN.md` | Current-state content; belongs in living tracker not a structured doc |
| `Hold in BACKLOG.md` | Identified but unscheduled work; not ready for PLAN.md |
| `Discard` | No durable value; safe to delete — verify the content is not compensating for an absent dependency before discarding |
| `Escalate` | Insufficient information to decide, OR two or more valid approaches exist with genuine trade-offs — flag for operator with the specific question or options |

**Orphaned operational knowledge** [Standard and Extended]
- `Extract to OPERATIONS.md §Failure Modes` if observed system behavior
- `Extract to DESIGN.md §Runtime View` if runtime scenario
- `Extract to /docs/interfaces/` if implementation-scoped protocol detail
- `ADR — Accepted` if resolved technical decision
- `Extract to CONTEXT.md §Glossary` if term definition
- `Hold in PLAN.md` if current-state finding not yet resolved
- `Discard` if no durable value

**External documents** [Standard and Extended]
- Create `/knowledge-base/references/[name]-summary.md`
- Add to `/docs/assets/` if not already in repo
- Add entry to DESIGN.md §References and CLAUDE.md Reference Summaries

**Use case reconstruction** [Standard and Extended]
Mandatory prerequisite — produce candidate UC list for operator approval before Phase 2.

**Glossary** [Standard and Extended]
Scan docs and source for undefined terms used more than once. Produce candidate list.

**Extended tier adds:**
- Informal quality statements → `Author as quality scenario in QUALITY.md`
- Quality goals without scenarios → `Author scenario per QS format`
- Implied quality behaviors → `Escalate — confirm with stakeholders before authoring`
- Risks with no permanent home → `Extract to QUALITY.md §Risks`
- Technical debt items → `Extract to QUALITY.md §Technical Debt`
- Compliance requirements stated informally → `Extract to CONTEXT.md §Constraints
  §Regulatory + OPERATIONS.md §Audit and Compliance`

Create `/docs/disposition-plan.md` containing:

**Section 1 — Disposition Table**

| # | Item | Source | Recommended Action | Target | Prerequisite | Operator Decision |
|---|------|--------|--------------------|--------|--------------|-------------------|

Leave `Operator Decision` empty. Valid entries: `Approve` / `Modify: [instruction]` /
`Escalate` / `Discard`

**Section 2 — Escalation Block** [If applicable]
```
Item #:    <Row number>
Item:      <Name>
Question:  <Specific question that must be answered before action is possible>
```

**Section 3 — Processing Instructions**

Include this verbatim at the bottom of `/docs/disposition-plan.md`:

```markdown
## How to Complete This File

1. Review each row in the Disposition Table
2. Add your decision to the `Operator Decision` column:
   - `Approve` — proceed as recommended
   - `Modify: [your instruction]` — proceed with changes you specify
   - `Escalate` — needs discussion before action
   - `Discard` — drop this item entirely
3. Answer each question in the Escalation Block or write `Defer`
4. Save the file then paste the following prompt into Claude Code:

---

### Resume Prompt

I have updated /docs/disposition-plan.md with my decisions.
Please:
1. Read /docs/disposition-plan.md
2. Confirm your understanding of each operator decision
3. Flag any decisions that conflict or create downstream problems
4. Produce a revised disposition table reflecting all modifications
5. Confirm readiness to proceed to DocPhase 2 — Scaffold Creation
6. Do not begin DocPhase 2 until I confirm
```

> **Stop. Do not proceed until the operator pastes the Resume Prompt.**

---

## DocPhase 2 — Scaffold Creation

### Step 1 — Install Framework Files

Copy into `/doc-framework/`:

Copy the entire `/doc-framework/` folder into the target project's `/doc-framework/`,
with the following exceptions:

| File | Action |
|------|--------|
| `doc-standard.md` | Always copy |
| `doc-bootstrap.md` | Never copy — run from central tooling location only |
| `templates/` | Always copy |
| `planning-guide.md` | Copy only if the planning funnel is adopted for this project |
| `README.md` | Always copy |

**Rules:**
- Framework files in `/doc-framework/` are read-only — not edited per-project
- Framework updates come from the central tooling location and replace files explicitly
- CLAUDE.md must reference the framework location so AI agents can locate it
- After CLAUDE.md is created, configure Claude Code project-scoped permissions using
  the `update-config` skill — new projects default to prompt-on-everything until
  permissions are set

### Step 2 — Create Document Scaffold

**All tiers — merge planning-docs section into `/docs/README.md`:**
Merge `templates/planning-docs-README.md` into the target project's `/docs/README.md` as
the "Planning and Documentation Framework" section. Fill in framework-version, Tier, and
Applied date. If `/docs/README.md` does not exist, create it with this section as the
starting content.

**Minimal:**
- README.md from `templates/README-minimal.md`
- PLAN.md (or PLAN-bd.md if bd in use) from `templates/`
- CLAUDE.md from `templates/CLAUDE.md` — set **Tier** to Minimal, delete inapplicable tier annotations
- `/adr/` directory with stub

**Standard:**
- PLAN.md (or PLAN-bd.md), BACKLOG.md from `templates/`
- CLAUDE.md from `templates/CLAUDE.md` — set **Tier** to Standard, delete inapplicable tier annotations
- In `/docs/`: CONTEXT.md, DESIGN.md, OPERATIONS.md from `templates/`
- `/knowledge-base/adr/`, `/docs/{assets,interfaces,references}/` as applicable

**Extended:**
- PLAN.md (or PLAN-bd.md), BACKLOG.md from `templates/`
- CLAUDE.md from `templates/CLAUDE.md` — set **Tier** to Extended, delete inapplicable tier annotations
- In `/docs/`: CONTEXT.md, DESIGN.md, OPERATIONS.md, QUALITY.md from `templates/`
- `/knowledge-base/adr/`, `/docs/{assets,interfaces,references}/` as applicable
- Reference summaries get stub files in `/knowledge-base/references/`

**If planning funnel is adopted** (bd in use + planning-guide.md in scope) — all tiers:
- Create `knowledge-base/VISION.md` stub with §Strategic Themes placeholder
- Create `knowledge-base/ROADMAP.md` stub with §Funnel and §Review placeholders
- Create `knowledge-base/lessons-learned/` directory
- Do **not** create PLAN.md or BACKLOG.md — both superseded when bd + planning funnel
  are both in use

> **Stop. Confirm scaffold with operator before proceeding.**

---

## DocPhase 3 — Migration Plan

Produce a reviewable migration plan. Do not modify any existing files.

**Section 1 — File Operations**

| # | Action | Source | Destination | Notes |
|---|--------|--------|-------------|-------|

Actions: `Rename` / `Migrate` / `Split` / `Summarize` / `Archive` / `Delete`

All replaced documents must be renamed with `-OLD` before content is extracted.

**Section 2 — Content Gap Analysis**
For each target document section: source and status
(`Ready` / `Needs rewrite` / `Must be authored` / `Orphaned — needs decision`).

**Section 3 — Diagram Inventory** [Standard and Extended]

| Diagram | Current Location | Format | Target Location | Action |
|---------|-----------------|--------|-----------------|--------|

**Section 4 — Reference Document Plan** [Standard and Extended, if applicable]

| Document | Asset Location | Summary File | Sections to Cover |
|----------|---------------|--------------|-------------------|

**Section 5 — Execution Order** [Standard and Extended]
Ordered sequence. Reference summaries before interface documents that depend on them.

**Section 6 — Quality and Risk Migration** [Extended only]

| # | Item | Source | Target | Notes |
|---|------|--------|--------|-------|
| 1 | <Informal quality requirement> | <Source> | QUALITY.md §Quality Scenarios | Author as QS-N |
| 2 | <Risk> | <Source> | QUALITY.md §Risks | Extract and format |

**Section 7 — Migration Losses and Orphaned Content** [all tiers — numbered per tier above]

Capture information with no permanent home in the framework. Record in `/knowledge-base/ORPHANED-CONTENT.md`.

For each item:
1. Brief summary (2–3 sentences)
2. Reference the original source document or location
3. Explain why it doesn't map to the framework
4. Record a plan for review (typically after DocPhase 3 completion)

> **Stop. Do not execute. Operator approves before any file is modified.**

---

## Use Case 3: Bootstrap a New Workspace

**When to use:** The target repository contains two or more sub-projects — directories each
with their own `.clasp.json`, `pyproject.toml`, `package.json`, or registered git submodules.
Running Use Case 1 at the workspace root would treat all sub-projects as a single project —
do not do this.

**Do not generate document content until explicitly instructed. Follow phases in order.
Stop at each confirmation gate.**

---

### Phase 0 — Identify Workspace vs. Single Project

Check whether the repository has multiple directories each with their own deployment config
(`.clasp.json`, `pyproject.toml`, `package.json`) or registered git submodules. If yes, use
this use case. If no, use Use Case 1.

---

### Phase 1 — Workspace Discovery

Inventory all sub-projects. For each, record:

| Sub-project | Type | Current docs state | CLAUDE.md | Tier (if declared) | bd | Deployment status |
|-------------|------|--------------------|-----------|-------------------|-----|------------------|

**Type values:** `library`, `app`, `tool`, `sample`, `archive`

Also identify:
- Shared resources at root (canonical specs, schemas, test fixtures, shared venv)
- Cross-project dependencies (which sub-projects import or depend on others at runtime or test time)
- Which sub-projects are most active and highest priority for bootstrap

Present the inventory table to the operator. Confirm which sub-projects to bootstrap
immediately vs. defer.

> **Stop. Confirm inventory with operator before proceeding.**

---

### Phase 1.5 — Tier Assignment

For each sub-project selected for bootstrap, recommend a tier based on scale (see
doc-standard.md §Tier Overview). Confirm with operator before proceeding.

Sub-projects not selected for immediate bootstrap still get a tier *declared in CONTENTS.md* —
assign based on current state, note as deferred.

> **Stop. Confirm tier assignments with operator before proceeding.**

---

### Phase 2 — Workspace Scaffold

Create workspace-level documents at root:

1. `CLAUDE.md` — workspace navigation, sub-project table, dependency chain, shared resources. Use `templates/CLAUDE.md` as base; adapt for workspace context.
2. `CONTENTS.md` — from `templates/CONTENTS.md`. Include all sub-projects (bootstrapped and deferred). Populate Dependency Chain section if cross-project dependencies exist.
3. `README.md` — user-facing overview with links to sub-projects. Use `templates/README-standard.md` as base.
4. `docs/` and `knowledge-base/adr/` — create only if cross-cutting content (shared architecture, workspace-spanning decisions) warrants it.
5. `ROUTING.md` — optional. Create from `templates/ROUTING.md` if agent session routing is needed.

> **Stop. Confirm scaffold with operator before continuing.**

---

### Phase 3 — Per-Sub-Project Bootstrap

For each prioritized sub-project, run the single-project bootstrap process (Use Case 1,
Phases 1–3) with that sub-project's directory as the target. Execute in priority order.

Each sub-project's CLAUDE.md should note its tier and reference the workspace root CLAUDE.md
as supplementary context.

Sub-projects not selected for immediate bootstrap: list in CONTENTS.md with status `draft` or
`archived` as applicable. No documents created for them at this stage.

**Output:** CONTENTS.md present at root; workspace CLAUDE.md and README.md present; each
prioritized sub-project bootstrapped to its declared tier; remaining sub-projects listed in
CONTENTS.md with deferred status.

---

## Use Case 3b: Upgrade an Existing Workspace

**When to use:** The target repository is an existing workspace that was structured ad-hoc
(without the framework workspace standard). At least one of CLAUDE.md, CONTENTS.md, or
sub-project docs exists but does not conform to the framework standard. Running Use Case 3
would overwrite ad-hoc work — use this use case instead.

**Do not generate document content until explicitly instructed. Follow phases in order.
Stop at each confirmation gate.**

---

### Phase 1 — Discovery

Read the workspace root. Inventory:

| Item | Expected (framework) | Actual | Gap |
|------|---------------------|--------|-----|
| CLAUDE.md | Required — workspace nav format | Present / Absent / Different format | — |
| CONTENTS.md | Required — from template | Present / Absent / Different format | — |
| README.md | Required — user-facing | Present / Absent | — |
| docs/CONTEXT.md | Optional | Present / Absent | — |
| docs/DESIGN.md | Optional | Present / Absent | — |
| knowledge-base/adr/ | Optional | Present / Absent | — |
| ROUTING.md | Optional | Present / Absent / Named differently | — |

For each sub-project, record actual state against framework standard (same columns as
Use Case 3 Phase 1 inventory).

Identify shared resources, cross-project dependencies, and any documents that serve a
workspace-level purpose but are not in the standard locations.

> **Stop. Confirm inventory and gap table with operator before proceeding.**

---

### Phase 1.5 — Disposition

Classify each gap item:

| Action | When |
|--------|------|
| `Conform` | Existing content can be reformatted or moved to match the standard |
| `Accept` | Existing content is structurally different but serves the same purpose — note the deviation in CLAUDE.md |
| `Author` | No existing content; must be written from scratch |
| `Escalate` | Ambiguous; flag for operator decision |

Present the disposition table to the operator.

> **Stop. Confirm dispositions with operator before proceeding.**

---

### Phase 2 — Workspace Alignment

Execute approved dispositions:

- **CLAUDE.md**: if present but not in workspace nav format, add workspace-level sections (sub-project table, dependency chain, shared resources, navigation index). Preserve existing project-specific content.
- **CONTENTS.md**: if absent, create from `templates/CONTENTS.md`. If present in card format (per-project narrative blocks), that format is acceptable — note it in CLAUDE.md and do not reformat.
- **README.md**: if absent or minimal, expand to user-facing workspace overview with sub-project links.
- **ROUTING.md**: create from `templates/ROUTING.md` only if operator confirms agent routing is needed and ROUTING.md is absent. Do not rename existing AGENTS.md or similar files without explicit operator confirmation.
- **docs/** at root: create only if cross-cutting content exists or is being authored.

For sub-projects not yet bootstrapped to the framework standard, apply Use Case 1 (single-project bootstrap) with that sub-project's directory as the target, per the prioritization agreed in Phase 1.

> **Stop. Confirm alignment plan with operator before writing any files.**

---

## Success Criteria

See doc-standard.md §Universal Success Criteria for foundational criteria.

**Minimal adds:**
- Consistent terminology: README.md section headers match tier nomenclature exactly
- Scaling path clear: CLAUDE.md §Scaling Threshold documents upgrade path

**Standard adds:**
- Document separation: CONTEXT.md, DESIGN.md, and OPERATIONS.md contain no overlapping content
- Graduation path: CLAUDE.md §Scaling Threshold documents the path to Extended tier
- Work tracking active: either BACKLOG.md is populated or bd is in use (not neither)

**Extended adds:**
- Stakeholder coverage: All stakeholder groups represented in CONTEXT.md
- Quality traceability: Each Quality Goal has at least one testable scenario in QUALITY.md
- Risk visibility: All known risks documented with probability, impact, and mitigation
- Compliance coverage: All regulatory constraints documented and traceable to OPERATIONS.md

---

*Begin with DocPhase 1. Do not skip phases. Do not generate content before migration plan
is approved.*

---

*framework-version: 2.3.0 — Monday, April 21, 2026*
