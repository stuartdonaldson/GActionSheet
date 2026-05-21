---
framework-version: "2.3.0"
tier: standard
---
# ROADMAP — GActionSheet

## Funnel
Ideas not yet evaluated. One-liners only. To advance: evaluate at planning review; add lean business case to §Review.

- Assignee token normalization — canonicalize person tiles and bare emails to `Display Name <email>` on rewrite (deferred per requirements §7.10)
- Email notification to assignee when a new action is assigned
- Overdue indicator — mark actions whose created date is past a configurable threshold
- Status preset view — sheet view hiding Closed actions for daily triage
- Document health indicator — warn when a document in scope is missing `=== Tracked Actions ===`
- Bulk re-sync — on-demand full scan ignoring the 7-day discovery window (for initial migration of older documents)

## Review
Initiatives with a lean business case under value/risk evaluation.

*(none — v1 execution is active in beads)*

---

## Execution

v1 work is managed in beads. Run `bd ready` for actionable items.

### Delivering a future feature (v2+)

When an initiative exits §Review and is selected for delivery, create a staging document in
`knowledge-base/staging/`, decompose it into spikes, then pour the feature-delivery molecule:

```bash
bd cook /mnt/c/dev/DevStandard/dot-beads/formulas/mol-feature-delivery.formula.yaml \
  --var feature="<feature name>" \
  --var use_case_id="UC-N" \
  --var target_docs="docs/CONTEXT.md, docs/DESIGN.md"
```

The resulting molecule appears in `bd ready` step by step as dependencies resolve.
Human gate issues pause execution until closed with `bd gate resolve <id>`.
Verify the full DAG with `bd graph <epic-id> --compact`.
