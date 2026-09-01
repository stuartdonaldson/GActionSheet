# LL: bead closed green while the user-facing entry point had no test call-site

Date: 2026-09-01
Domain: testing
Session: 9a56db38-a3e7-411b-b4fa-94cdb3e12e05 (gts-gwyg / gts-s4tr)

## Observation
`gts-gwyg` and its twin `gts-s4tr` were closed with `regression=pending` on a green targeted
gate: 3/3 tests in `tests/test_admin_doc_scan.py` passing against TEST v0.2.3.82. The operator's
review after the session reported the feature still does not work.

All three tests POST to the `admin_scan_team_docs` route with `testToken` + `email`, a test-only
identity bypass added at deploy 3 because the assertion-minting secret is not provisioned in this
environment. Consequently:

- The production identity path (GIS assertion → `_verifySignedAssertion` → `_isAdminUser` →
  Config `AdminUsers`) is exercised only in its denial case (`test_scan_denies_unverified_assertion`).
- `isAdmin` — returned by `list_team_actions` (`src/TeamListing.js:117`) and the sole gate on the
  button rendering (`static-portal/src/index.html:768`, additionally hidden in the "All teams"
  view) — has **no test coverage**. `grep -rn isAdmin tests/ scn/` returns one docstring comment.
- No static-portal client code is exercised by any test.

The operator's symptom ("I do not see the option") lands exactly on the untested seam.

This is a recurrence of the class in
`docs/lessons-learned/resolved/2026-05-27-stub-entry-point-wired-to-trigger-without-end-to-end-test.md`
(`syncAll()` stub: mechanism tested directly, entry point never the call-site). **The levers from
that resolution are present and intact** — project CLAUDE.md carries the "Entry point coverage
invariant" and the retroactive Path B rule; `.claude/skills/code-review/SKILL.md` Steps 4–5 carry
an entry-point inventory and coverage check. Neither fired: `code-review` was not invoked at any
point in this session (one `Skill` call total — `implementation-gate`), and `merge-gate` was not
reached because nothing was committed.

## Why Chain

Branch A — the coverage check has no trigger at bead-close
Why 1 — The bead closed with the user-facing entry point untested.
Why 2 — The entry-point coverage check lives in `code-review` and `merge-gate`, both of which fire at the merge boundary.
Why 3 — The Backstop rules deliberately permit closing a bead on a fast targeted subset with `regression=pending`, deferring full verification to merge — a correct cost decision against a live GAS backend.
Why 4 — `regression=pending` records *that* the full suite has not run; it records nothing about *which entry points* the targeted gate left uncovered, so the gap is invisible until merge, and to the operator it looks like a green close.
Root cause A: no coverage check fires at the bead-close boundary, and the `regression=pending` marker carries no inventory of what the targeted gate did not cover — so the one boundary the operator treats as "done" is the only boundary with no entry-point enforcement.

Branch B — a test-only auth bypass silently became the coverage strategy
Why 1 — All functional coverage runs through the `testToken` + `email` bypass, so the production identity path is never exercised in its success case.
Why 2 — The bypass was introduced to obtain functional coverage when the shared assertion secret proved unprovisioned in TEST, and was then treated as sufficient.
Why 3 — Nothing marks a test-only bypass as coverage *debt* rather than coverage; once the test is green the bypass reads as satisfied coverage.
Root cause B: there is no convention that a test bypassing a production auth or identity path creates a recorded coverage gap, so a green targeted gate can certify a route while the path every real caller takes is untested.

## Initial Candidates
- c/d: emit an entry-point inventory at bead-close — `regression=pending` reason string, or a `bd set-state` field, must name the entry points the targeted gate did not cover (Branch A)
- c: `implementation-gate` Step 5 — before close, list the state-modifying entry points introduced by this bead and mark each covered / uncovered (Branch A)
- b: project CLAUDE.md Backstop rules — a test that bypasses a production identity/auth path does not count as coverage for that path; a paired `[TST]` or a recorded gap is required before close (Branch B)
- f: bd issue — close the concrete `isAdmin` / real-identity / static-portal coverage gap (Branch B, filed same day)
[Developed fully at resolve phase]

## Cross-reference
Same failure class, different structural gap, as
`resolved/2026-05-27-stub-entry-point-wired-to-trigger-without-end-to-end-test.md`. That LL's root
cause was "no rule requires entry-point coverage"; the rule now exists. This LL's root cause is
that the gates carrying it do not fire at the boundary where a bead is actually closed.
