# LL: [INF] design bead created without its deliverable defined

Date: 2026-06-09
Domain: process

## Observation

During EPIC-B plan execution, two `[INF]` design beads (`me6w.1` and `me6w.2`) were created
with correct structural metadata (title, model label, parent, dependency chain) but zero
content — no description, no design field, no acceptance criteria. The beads blocked the
downstream `[IMP]` and `[TST]` beads as intended, but were themselves unworkable: no one
looking at the bead could determine what to write or what "done" meant.

Caught by the user after bead creation, when they asked "how do we fill in the beads?"
and noted it was not clear from the staging contract. The design work (reading the codebase,
resolving the cross-context property storage issue, writing 7 test scenarios with fixtures)
was done in the subsequent turn — work that could have been done at creation time had the
convention required it.

## Why Chain

Why 1 — the `bd create` commands during plan execution omitted `--description`, `--design`,
and `--acceptance` flags for the `[INF]` beads.

Why 2 — the plan file presented bead creation as structural scaffolding (title + labels +
deps). No distinction was made between beads that are immediately executable versus beads
that themselves require authoring work before they can be claimed.

Why 3 — no convention exists in CLAUDE.md, the ROADMAP §Planning bead template, or any
skill specifying that `[INF]` design beads require their deliverable to be scoped at creation
time (description = what artifact; acceptance = done criteria; design = questions the
artifact must answer).

Why 4 — `[INF]` is used for both mechanical work ("author ADR") and design-class work
("produce implementation contract the downstream beads work from"). The project convention
does not distinguish between these, so design-class `[INF]` bead creation is treated the
same as any other: title + labels + deps is sufficient.

Root cause: The bead authoring convention makes no distinction between `[INF]` beads whose
deliverable is an artifact blocking downstream beads versus `[INF]` beads that are
self-contained operational tasks. Design-class `[INF]` beads are therefore created
structurally valid but operationally unworkable — the bead gives no signal of what to
produce or what "done" looks like.

## Initial Candidates

b: CLAUDE.md §Issue Conventions — add a rule: "When a `[INF]` bead's deliverable is an
artifact consumed by downstream beads, `--description` (scope of artifact),
`--acceptance` (done criteria), and `--design` (questions the artifact must answer) are
required at creation time. A `[INF]` bead with empty fields is considered incomplete."

c: Update the `implementation-gate` skill or create a `bead-authoring` check — when plan
execution creates `[INF]` design beads, verify content fields before proceeding to
downstream bead creation.

d: Add to the EPIC planning bead template in ROADMAP §Planning — after the bead table,
add: "Before closing the planning step, each `[INF]` design bead must have its description,
acceptance criteria, and design stub populated. Downstream `[IMP]`/`[TST]` beads are not
created until the `[INF]` bead is workable."
