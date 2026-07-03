# Runbook: lessons-learned staging cleanup (2026-07-01)

**For:** clear-context executor (Haiku). Everything needed is in this file.
**Principle being applied:** `docs/lessons-learned/` (the staging dir, i.e. files *not* under
`resolved/`) is a capture surface, not a backlog. An LL's job ends when (a) its root cause is
captured and (b) its lever is either applied or handed to a bd issue — then it moves to
`resolved/`. Reference material is not an LL and goes to `knowledge-base/references/`.

**Goal state:** `docs/lessons-learned/*.md` (top level) contains **zero** files; all 7 current
staged files are either under `resolved/` or relocated; 2 carrier bd issues created; 1 CLAUDE.md
rule added.

All paths below are relative to repo root `/mnt/c/dev/GActionSheet`.

---

## Step 1 — Create the two carrier bd issues FIRST (capture their IDs for Steps 3 & 7)

```bash
bd create "[TST] Unit-test _parseAssigneeFromText rest output (LL 2026-05-20 Branch B)" \
  --type task -p 3 \
  --description "Branch B of LL 2026-05-20 (uc-scenario-suite-exhausts). Add a focused, deterministic parser unit test (T12) asserting the 'rest' return value of _parseAssigneeFromText after token extraction. Root cause was BARE_EMAIL_RE '\\s*' eating the field separator so action=='' — only caught at the 6-minute UC-scenario level. A parser-level test surfaces it in seconds. Add to test_floating_action_parser.py." \
  --acceptance "Test asserts the exact 'rest' string for at least: (a) a bare-email assignee followed by action text, (b) the field-separator-adjacent case that triggered the bug. Test fails if BARE_EMAIL_RE over-consumes the separator."
# → record the ID printed, e.g. GTaskSheet-XXXX  (call it BRANCH_B_ID)

bd create "[INF] /technical-debt v1.1 refinements (LL 2026-06-12 residuals)" \
  --type task -p 3 \
  --description "Residuals from LL 2026-06-12 (molecule-placeholder issues stayed open). The immediate mol-66r/mol-dhd child closures were done 2026-06-12; these are the carried-forward tool refinements. Branch A: /technical-debt implicit-resolve check should also match recently-closed bead titles/close-reasons against the TITLES of open molecule-formula step children sharing a parent epic (empty descriptions defeat the current commit-vs-description match). Branch B: tune 'bd stale' threshold against this project's epic/molecule cadence (21-day-dormant placeholder children were not flagged). Branch D: add a '100%-children-closed but parent still open' check (bd's own 'eligible for close' signal has no aggregate surface)." \
  --design "Where each refinement lands: Branch A/D → /technical-debt SKILL.md checks; Branch B → bd stale config or a session-start-check step. Open question: is title-matching precise enough to avoid false 'superseded' calls, or does it need human confirm (as the existing implicit-resolve check already requires)?" \
  --acceptance "Each of Branch A, B, D is either implemented in the named artifact or explicitly deferred with rationale recorded on this issue."
# → record the ID printed, e.g. GTaskSheet-YYYY  (call it TECHDEBT_V11_ID)
```

## Step 2 — Add the `[INF]`-authoring rule to project CLAUDE.md (resolves LL 2026-06-09)

In `CLAUDE.md`, find the paragraph beginning **"**Pre-code contract:**"** in the Testing
Strategy section. Insert immediately **after** that paragraph (as its own paragraph):

```
**`[INF]` design-bead authoring:** when an `[INF]` bead's deliverable is an artifact consumed by
downstream beads, `--description` (scope of the artifact), `--acceptance` (done criteria), and
`--design` (questions the artifact must answer) are required at creation time. An `[INF]` bead
with empty content fields is incomplete — downstream `[IMP]`/`[TST]` beads are not created until
it is workable.
```

## Step 3 — Append Resolution sections, then move each file to `resolved/`

For each file below: append the given `## Resolution (2026-07-01)` block to the end of the file,
then `git mv docs/lessons-learned/<file> docs/lessons-learned/resolved/<file>`.
Substitute BRANCH_B_ID / TECHDEBT_V11_ID captured in Step 1. SONNET_BEAD_ID is **GTaskSheet-g7ep**.

**2026-05-20-uc-scenario-suite-exhausts-on-root-cause-failure.md**
```
## Resolution (2026-07-01)
Branch A applied and confirmed: `pytest -x` is the documented default (CLAUDE.md Testing Strategy
"Backstop rules" + implementation-gate Step 6 [IMP]-close full-suite gate). Branch B (focused unit
test for `_parseAssigneeFromText` `rest` output) handed to BRANCH_B_ID. Moved to resolved/.
```

**2026-05-27-skill-not-invoked-on-natural-language-skill-name.md**
```
## Resolution (2026-07-01)
Out of project scope. The only lever is a global-instruction change (recognise a skill named as a
natural-language noun phrase, not only the `/name` form) in the user-scoped global CLAUDE.md —
cross-project, not a GActionSheet artifact. Recorded here for global-instruction follow-up; no
project change owed. Moved to resolved/.
```

**2026-06-02-smart-chip-rendering-is-publish-gated.md**
```
## Resolution (2026-07-01)
Guidance already integrated into DevStandard `knowledge-base/gas-addon-guide.md` §"Three platform
gates invisible at development time (LL 2026-06-02)" (incl. the hallucinated-CardService warning).
Lever applied. Moved to resolved/.
```

**2026-06-02-webapp-url-deployment-stamping-and-reuse-boundaries.md**
```
## Resolution (2026-07-01)
Documentation lever applied: guidance integrated into DevStandard `knowledge-base/gas-addon-guide.md`
§"WebApp URL must be deployment-stamped at build time, not self-registered (LL 2026-06-02)". The
code-fix verification (WEBAPP_URL stamped at deploy time vs. self-registered on first visit) is
tracked separately in GTaskSheet-g7ep. Moved to resolved/.
```

**2026-06-09-inf-design-bead-created-without-deliverable-defined.md**
```
## Resolution (2026-07-01)
Lever applied: `[INF]` design-bead authoring rule added to project CLAUDE.md Testing Strategy
(description/acceptance/design required at creation when the deliverable blocks downstream beads).
Dogfooded on GTaskSheet-m65t. Moved to resolved/.
```

**2026-06-12-molecule-placeholder-issues-stayed-open-after-scope-delivered-elsewhere.md**
```
## Resolution (2026-07-01)
Immediate actions (mol-66r/mol-dhd child closures) taken 2026-06-12. Residual tool refinements
(Branch A title-matching, Branch B `bd stale` tuning, Branch D "100%-children-closed-parent-open"
check) handed to TECHDEBT_V11_ID. Moved to resolved/.
```

## Step 4 — Reclassify the reference note (NOT a resolution)

`2026-05-27-docs-addon-sidebar-testing-notes.md` is self-declared reference material
("This is a reference note for future similar projects, not a formal lessons-learned action item").
It is not an incident LL. Relocate it:

```bash
mkdir -p knowledge-base/references
git mv docs/lessons-learned/2026-05-27-docs-addon-sidebar-testing-notes.md \
       knowledge-base/references/docs-addon-sidebar-testing-notes.md
```

## Step 5 — Verify goal state

```bash
ls docs/lessons-learned/*.md 2>/dev/null | wc -l   # MUST print 0
ls docs/lessons-learned/resolved/ | grep -c 2026    # increased by 6
grep -c "\[INF\] design-bead authoring" CLAUDE.md   # MUST print 1
```

## Step 6 — Do NOT commit

Leave changes staged/unstaged for human review. Report the two created bd IDs and the final
`ls docs/lessons-learned/` output.
```
