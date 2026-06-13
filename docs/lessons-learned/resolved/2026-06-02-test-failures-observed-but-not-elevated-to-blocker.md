# LL: Technical debt identified but not reviewed with the human before proceeding

Date: 2026-06-02
Domain: process

## Observation
Session 2026-05-31 19:59:13: tests ran, failures observed. Key Learnings noted the mechanism
correctly for one file: "uc_a_clear inserts chip-led items, invisible to AI-N scanner."
Session ended with "Work will need to continue."

Session 2026-06-01 00:15:41: 11 failures identified across test_uc_scenarios, test_b7_write_routes,
test_uc_sidebar_mutations. Issue `GTaskSheet-w6vg` filed at P3 with a description of the failures
and a plausible explanation ("accumulated legacy rows without globalIds"). Session moved on.

Session 2026-06-01 12:23:41: PR reviewed, two additional debt issues filed, PR squash-merged to
master. The merge proceeded with GTaskSheet-w6vg open.

At no point was there an explicit conversation with the user: "we have 11 failing tests and here
is the state of the test suite — do you want to address this before merging, or accept this as
tracked debt and proceed?" The debt was identified, filed, and treated as discharged by the act
of filing. The human decision about whether to carry that debt into master was never requested.

Whether the diagnosis in w6vg was precisely correct is secondary. Even a perfectly correct
diagnosis would have had the same outcome under the same process: file → proceed.

## Why Chain

Why 1 — The PR merged to master with 11 known test failures.
Why 2 — Filing GTaskSheet-w6vg was treated as discharging the obligation — the act of creating
         the issue substituted for the conversation about whether to proceed.
Why 3 — No step in the merge-gate process requires the AI to surface a debt summary to the human
         and explicitly request a proceed/address decision when known failures exist.
Why 4 — The AI's role at merge time was treated as "check, file what's broken, proceed if
         something is tracking the failures" rather than "surface the debt state and give the
         human the choice."
Why 5 — There is no convention distinguishing "AI files a ticket and proceeds autonomously"
         from "AI files a ticket and surfaces the decision to the human before proceeding."

Root cause: When technical debt is identified at a merge/gate transition, the AI files a tracking
issue and proceeds without presenting the debt state to the human and requesting an explicit
proceed/defer decision. Filing a ticket is treated as a discharge of the obligation rather than
the opening of a conversation.

## Note on the misdiagnosis question
The description in w6vg ("accumulated legacy rows") may have been imprecise, but this is not
the primary gap. The process failure would have occurred identically with a perfect diagnosis:
correct description → P3 ticket → proceed. The root cause is the absence of a human decision
step, not the accuracy of the technical finding.

## Relation to existing LLs
`2026-06-02-scanner-change-did-not-audit-fixture-producers.md` (LL-1) — addresses the gate
that should have caught the regression. This LL is downstream: the gate partially fired
(tests were run, debt was found), but the response was to file and proceed rather than surface
and decide.

## Initial Candidates

c: update merge-gate skill — add an explicit human-decision step when failures exist:
   "if any tests are failing or any debt issues are filed during this gate, do NOT proceed;
   instead present a debt summary to the human: what is failing, what is the known explanation
   (confirmed or plausible), what is the risk of carrying it forward; ask explicitly: proceed
   with this debt, or address it first?"

b: add to project CLAUDE.md — "when known test failures exist at a merge or gate transition,
   the AI does not proceed autonomously; it presents the debt state to the human and waits for
   an explicit proceed/address decision; filing a tracking issue does not constitute permission
   to proceed"

c: update session-start-check skill — at session start, if open test-failure issues exist
   (identifiable by title prefix or label), surface them before starting new work: "N test
   failures are currently tracked as open debt — do you want to address these before starting
   new work, or continue with them open?"

Preferred: the merge-gate skill change (c) is the enforcement point where the decision should
happen; the CLAUDE.md rule (b) is the backstop for sessions that don't run the skill explicitly.

## Resolution (2026-06-12)

Already applied. `merge-gate` skill v1.1 Step 0 "Debt state check" requires synthesizing
known debt (test failures, stale issues, convention drift), presenting it to the human, and
asking explicitly "address before merging, or proceed with it tracked?" — with the line
"Filing a tracking issue does not constitute permission to proceed." This is the c option
verbatim, including the anti-pattern entry citing this exact incident (GTaskSheet-w6vg).
No CLAUDE.md backstop or session-start-check addition needed — merge-gate is the enforcement
point and it fires automatically.

Verify: had Step 0 existed at the 2026-06-01 merge, the 11 known failures would have required
an explicit human proceed/address decision before the squash-merge to master, rather than
being discharged by filing GTaskSheet-w6vg.
