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

---

## Future design: per-document tracker-sheet resolution

> Relocated from `docs/DESIGN.md` on 2026-05-29 — this is an **unimplemented proposal**, not
> as-built behaviour. Today every document syncs to the single container-bound ActionSheet.
> Related: the multi-tenant chip URL (`…/action/{sheetId}/{globalId}`) is also future work.

A locator model that lets each document resolve its own action-tracking spreadsheet — supporting
multiple teams and folder-local trackers — without splitting the single GAS project.

### Resolution order (strict precedence)

1. **Document custom property** — if the document stores a tracker spreadsheet ID and that
   spreadsheet is reachable, use it.
2. **Document folder discovery** — if no property is set, inspect the active document's parent
   folder for a spreadsheet with a reserved identity such as `ActionTrackingSheet`.
3. **Bound fallback sheet** — if no folder-local tracker exists, use the container-bound
   ActionSheet spreadsheet.
4. **Persist the result** — whenever steps 2 or 3 succeed, write the chosen spreadsheet ID back to
   the document custom property so subsequent syncs do not rediscover it.

The document property is the authoritative locator; folder discovery and the bound sheet are
bootstrap and recovery paths.

### Why this shape is sound

- Avoids a single shared spreadsheet becoming a cross-team bottleneck.
- Keeps routing document-local, so a doc keeps pointing at its intended tracker even if moved.
- Preserves a safe fallback for documents not yet initialized.
- Keeps UX simple: users inspect/change the resolved location in Settings, not on every sync.

### Recommended metadata model

| Field | Purpose |
|-------|---------|
| `trackerSpreadsheetId` | Authoritative target sheet for this document |
| `trackerResolutionSource` | `property`, `folder-discovery`, or `bound-fallback` for diagnostics |
| `trackerResolvedAt` | Last time the locator was written or confirmed |

If the implementation surface only supports string values, store simple scalar properties rather
than a composite JSON blob.

### Folder discovery contract

- Spreadsheet name begins as `ActionTrackingSheet`.
- The spreadsheet carries a marker (document or script property) indicating it is a valid team tracker.
- If multiple matching spreadsheets exist in the folder, resolution must **fail as ambiguous**
  rather than choosing one arbitrarily.

Name-only discovery is acceptable for bootstrap but provisional (duplicate names are likely).

### Settings surface

A document **Settings** menu item exposing: the resolved tracker; how it was resolved; whether it
is folder-local or the bound fallback; an action to initialize a local tracker in the document
folder; and an action to rebind the document to a different tracker intentionally.

### Local-folder initialization flow

1. Resolve the active document's parent folder.
2. Create or validate one folder-local tracking spreadsheet for that folder.
3. Enumerate only supported documents in that same folder.
4. For each eligible document, set its tracker document property to the folder-local spreadsheet ID.
5. Run a per-document sync into that tracker.

Guardrails: do not rewrite properties for documents already pointing at a different valid tracker
without explicit confirmation; treat initialization as an administrative action that produces a
summary report.

### Bound-sheet registry (troubleshooting index, not a routing authority)

| Column | Purpose |
|--------|---------|
| Document ID | Document being tracked |
| Document Title | Human-readable reference |
| Tracker Spreadsheet ID | Current resolved destination |
| Tracker Spreadsheet Name | Human-readable tracker reference |
| Resolution Source | Property / folder discovery / bound fallback |
| Last Sync | Latest successful sync time |
| Last Verification | Latest successful verification time |
| Last Error | Most recent routing or sync error |

The source of truth remains the document property.

### Failure handling

- **Property points to a missing/inaccessible spreadsheet** — surface an error and offer repair;
  do not silently choose a different tracker unless the user requests fallback repair.
- **Multiple candidate spreadsheets in folder** — mark as ambiguous and require user choice.
- **No folder-local spreadsheet found** — use the bound fallback only if policy allows, then persist.
- **Document has no parent folder or multiple parents** — handle deterministically and record why.

Main rule: never silently move a document's authority from one tracker to another once it has been
explicitly bound.

### Framing

- **Primary authority:** document property
- **Bootstrap discovery:** folder-local tracker lookup
- **Operational safety net:** bound spreadsheet fallback
- **Troubleshooting index:** registry worksheet on the bound spreadsheet

When promoted to delivery, this should be captured as a new ADR (it changes the identity/locator
model) before implementation.
