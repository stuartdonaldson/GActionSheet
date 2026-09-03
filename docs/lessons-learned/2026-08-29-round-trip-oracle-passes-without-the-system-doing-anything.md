# LL: Round-trip oracle passes without the system under test doing anything

Date: 2026-08-29
Domain: testing

## Observation

The ADR-0027 canonical reference Doc (`referenceDocId`, 21 actions) was found by the operator to
be missing status icons, person chips, and `ACT-N:` link headers. Axiom for the operator's re-scan
at 04:42:51Z shows `sync.scanned {count: 1}` under build `v0.2.2 (Rev. Aug 14, 2026)`, followed by
20 `sync.info "Sync Status — Deleted"` events (ACT-1…ACT-21, excluding ACT-10) and
`sync.complete {upserted: 0, updated: 0}`. The single action found was ACT-10, spelled `AI-10:`;
the build predates ADR-0023 (2026-08-26) dual-prefix `ACT-` read support. After the operator
updated the add-on to deployment @508, and on a WebApp-initiated scan at 05:03:02Z under build
0.2.3.37, `sync.scanned {count: 21}` with `sync.complete {upserted: 0, updated: 0, forced: false}`.

The APT test suite committed at 3d30a67 was green throughout. State at time of discovery:

- All 15 `tests/fixtures/*.scenario.json` declare `input == expected` under `mutation: {kind: sync}`.
  The assertion in `tests/test_apt_corpus_check.py` is `diff_apt(expected, encode(sync(decode(input))))`,
  which holds when the sync performs no work.
- No test references `referenceDocId`. `tests/test_adr0027_reference_document.py:45` and
  `tests/test_apt_corpus_check.py:83` both call `ScenarioSession.new_doc()`.
- `tests/fixtures/action-reference.apt.txt` carries `ACT-N:` link headers on 8 of 21 records and
  bare tokens on 13. The file was produced by `bless` from a live capture.
- `tests/helpers/doc_inspect.py:16` `floating_actions()` detects an action as a paragraph with
  `w:numPr` whose first content resolves to an assignee, and does not extract the `ACT-N:` token.
- `src/PortableText.js:145` skips `INLINE_IMAGE` on encode (rule 8), so status icons are absent
  from every golden.
- `src/WebApp.js` contains no `force` parameter; `syncDocument(docId, {force:true})` is reachable
  only from `src/MenuHandler.js:127`.
- `knowledge-base/staging/apt-testing.md` was deleted at dff61ca, recorded in that commit message
  as "was untracked -- no prior commit". `scripts/apt.py`, `scripts/apt_lib.py` and
  `docs/interfaces/action-portable-text.md` cite decisions 1–9 of that document.
- `docs/CONTEXT.md:21-22` lists "Action owner — edit status, action text, or assignee in the
  ActionSheet" and "Reviewer / manager — filter and search all open actions across all docs from
  the ActionSheet" as stakeholder expectations. The operator states the ActionSheet is admin-only
  because it aggregates all teams with no per-row visibility enforcement.

Caught by the operator reading the document, not by any gate.

## Prior incident — same root cause

`docs/lessons-learned/resolved/2026-06-02-new-assertion-vacuously-passes-on-empty-result-set.md`
records the same failure mode at `sync.scanned count:0`. Its resolution added two CLAUDE.md
Backstop rules: that a test calling `verify_consistency()` must also call
`verify_all_expectations(a)`, and that a new assertion must be proven to fail before acceptance.
`tests/test_apt_corpus_check.py` cites that LL by filename in its own docstring and guards the
scenario *glob* against being empty — while leaving the scan itself unguarded.

## Why Chain

### Branch A — The recurrence: a rule written about a function, not a property

Why 1 — `test_apt_corpus_check.py` passes when the scan finds nothing.
Why 2 — Its oracle compares the system's output against the system's own input; a no-op satisfies it.
Why 3 — The Backstop rule that addresses this names `verify_consistency()` and
        `verify_all_expectations(a)` — two specific functions in `scn/`.
Why 4 — A new lane in a different module with a different vacuous shape is outside the rule's
        literal scope, so citing the LL and complying with the rule as written are compatible with
        reproducing the defect.
Why 5 — No rule states the general property: an assertion must be able to fail when the
        system under test does nothing.

**Root cause A:** the 2026-06-02 corrective action was expressed as a rule about two named
functions rather than about the class of oracle, so it does not reach any new test that has the
same shape under different names.

### Branch B — A blessed golden cannot contradict the implementation

Why 1 — `action-reference.apt.txt` records 13 records with no link header as expected output.
Why 2 — It was produced by `apt.py bless`, which promotes a capture of live system output.
Why 3 — The expected value and the actual value therefore have a common origin.
Why 4 — Nothing in the corpus workflow requires any expected value to be authored independently
        of the implementation.
Why 5 — No convention distinguishes a *recorded* baseline (detects change) from a *specified*
        expectation (detects incorrectness), or requires that a suite contain at least one of the latter.

**Root cause B:** the corpus workflow has no independently-authored expected value, so the suite
can detect drift but cannot detect that the current behaviour is wrong.

### Branch C — The named canonical artifact was never exercised

Why 1 — The reference Doc accumulated 20 unscanned actions with no test failing.
Why 2 — No test opens it; every lane materialises a fresh doc.
Why 3 — `referenceDocId` is consumed only by `scripts/apt.py`'s CLI resolution path.
Why 4 — The one independent Python parse (`doc_inspect.floating_actions`) still implements the
        pre-ADR-0027 checklist grammar and would find almost nothing in an ADR-0027 document.
Why 5 — No convention requires that an artifact designated canonical be exercised by the suite, or
        that a grammar change audit the parsers that read that grammar.

**Root cause C:** designating an artifact canonical creates no obligation that any test read it,
so it can drift arbitrarily far from the behaviour it is said to define.

### Branch D — The build under test was not established

Why 1 — The operator's 04:42 scan ran build v0.2.2 while the deployment ledger's head was 0.2.3.37.
Why 2 — Add-on surfaces resolve to a pinned deployment version independent of the WebApp deployment.
Why 3 — Nothing in the lane asserts which build answered.
Why 4 — `?cmd=version` exists and the deploy pipeline polls it, but only at deploy time.
Why 5 — No convention requires a live test to record or assert the identity of the build it exercised.

**Root cause D:** live lanes do not establish which build responded, so a result cannot be
attributed to a known revision.

### Branch E — Decisions were lost with their carrier

Why 1 — Decisions 1–9 cited across `apt.py`, `apt_lib.py` and the APT spec resolve to nothing.
Why 2 — `knowledge-base/staging/apt-testing.md` was deleted while untracked.
Why 3 — The staged-plan skill's Mode C instructs deletion once *Found* items are graduated, and
        graduation covered three named targets, not the numbered decision list the code cites.
Why 4 — Nothing verifies that no surviving artifact references a document being retired.
Why 5 — No step in the retirement path preserves the document at the revision its work landed on.

**Root cause E:** the staged-plan retirement path destroys the document without checking for
inbound references or preserving it in history, so citations into it become unresolvable.

## Initial Candidates

- **a / c — generalise the vacuous-oracle rule (Branch A):** state the property, not the function
  names, in `sdlc-testing-principles.md` and/or the `test-functional` skill — an oracle must be
  able to fail when the system does nothing; a suite whose expected values all derive from system
  output has no correctness oracle.
- **b — CLAUDE.md Backstop (Branch A/B):** `input == expected` is not an acceptable scenario shape
  for a non-degenerate mutation; at least one independently-authored expected value per lane.
- **c — `staged-plan` skill Mode C (Branch E):** commit the retiring doc on the version its work
  landed on, then remove; grep for inbound references before retiring.
- **c / d — live-lane build assertion (Branch D):** deployed-build guard as a lane precondition.
- **f — beads (Branches B/C/D):** the remediation work is staged in
  `knowledge-base/staging/apt-oracle.md` Stage 0.
- **b — CONTEXT.md surface model (adjacent):** the incorrect stakeholder rows are a documentation
  defect surfaced by this incident; tracked as a bead, not a lever.

[Developed fully at resolve phase]
