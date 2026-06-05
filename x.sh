#!/bin/bash

claude --model=sonnet 'ATDD documentation belongs in docs/atdd/ 
<ID> = GTaskSheet-5vwu.13 and <EPIC> = GTTaskSheet-5vwu

You are working bead <ID> in the GActionSheet repo (branch poc/editor-addon-action-chip). Assume a
CLEAN context.

1. `bd show <ID>` — read description, acceptance, design notes, dependencies, and the model:* label
(work at that altitude).
2. `bd show <EPIC>` — read the Coordination Log for cross-cutting facts from sibling tasks.
3. Read ONLY the sources the bead names (e.g. docs/proposed-atdd-lifecycle.md §16.x,
src/ContractSchema.js, docs/DESIGN.md). Do NOT read the paired [IMP]/[TST] siblings code — the
contract is the only shared artifact.
4. State in one line each, before coding: (a) the interface/entry-point you produce, (b) the
completion signal, (c) the output you will be verified against. If any is unclear it is a CONTRACT
GAP — stop and append the question to the epic Coordination Log instead of guessing.
5. Run the implementation-gate skill, then do the work. Honor the §16 vocabulary and §16.11
decisions verbatim.
6. Quality gates (tests/lint/deploy as applicable). For GAS use the package.json npm scripts, never
raw clasp.
7. If you discovered anything a sibling needs: durable -> update the planning doc/ContractSchema and
say where; transient -> `bd update <EPIC> --append-notes "..."`.
8. Close per session protocol: update bead status, commit, push.'
