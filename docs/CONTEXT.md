# CONTEXT — GActionSheet

## Introduction & Goals

### Purpose
GActionSheet captures and tracks action items inside Google Docs and aggregates them in a central spreadsheet (the **ActionSheet**) for cross-doc roll-up. Authors create actions natively — a checklist item that begins with a Google Docs person chip is an action assigned to that person. Each action is identified by an in-text `ACT-N:` token (or its legacy `AI-N:` spelling, permanently read-compatible — ADR-0023) so its identity survives edits. The Workspace Add-on homepage card is the user-facing surface for the active document; the **verified team portal** (ADR-0021) is the user-facing surface for cross-doc, per-team action lists and edits, including for people outside the domain; the ActionSheet spreadsheet itself is the cross-doc store, edited directly only by an administrator.

### Quality Goals
| Priority | Quality Goal | Scenario |
|----------|-------------|----------|
| 1 | Idempotence | Clicking **Sync now** twice in succession with no edits produces no further writes to the doc or the ActionSheet |
| 2 | Data integrity | No action record is silently overwritten; `Last Modified` precedence determines the winner on every conflict |
| 3 | Operability | A document author can capture an action by adding a checklist item with an `AI:` token, optional person chip, and action text — no separate sheet interaction needed |
| 4 | Stable identity | An action's `ACT-N:`/`AI-N:` text token survives edits elsewhere in the doc; no duplicate ActionSheet rows are produced |

### Stakeholders
| Stakeholder | Expectation |
|-------------|-------------|
| Administrator | One-time deploy of the add-on (private or admin-deployed) and the container-bound automation; clear errors when configuration is missing |
| Document author | Capture and update actions in a Doc without leaving the document; the sidebar reflects the doc's current state |
| Action owner | Edit status, action text, or assignee for their own action via the verified team portal (ADR-0021), reached from an `ACT-N:`/`AI-N:` chip link or a team URL; changes propagate to the doc on the next Sync. An administrator with direct ActionSheet access may also edit there |
| Reviewer / manager | Filter and search all open actions across a team from the verified team portal's team list (View A); an administrator with direct ActionSheet access may also filter/search there across all teams |

---

## Constraints

### Technical Constraints
- GActionSheet is a single GAS project (`scriptId: 12EKX7dQiO1Wf7rvv94Adgpbh3nac0OetsZMTD_1lme3y2o1KLYdKcTXi`), container-bound to the ActionSheet spreadsheet. It is deployed simultaneously as a Workspace Add-on (sidebar card in Docs) and a Web App (proxy endpoint for sheet writes). `appsscript.json` declares both `addOns` and `webapp` sections
- Web App access must be **"Anyone"** (not "Anyone within org") — the org SSO policy enforces authentication on `UrlFetchApp` requests regardless of headers if set to org-restricted; `executeAs` must be `USER_DEPLOYING` for sheet-write authority
- The GCP project linked to the add-on must have the **Google Docs REST API** enabled (used for `createNamedRange`, `deleteNamedRange`, and tracker-table `batchUpdate` operations); the add-on requires the `https://www.googleapis.com/auth/script.external_request` scope to call the REST API
- DocumentApp is used for read-side traversal because it exposes PERSON chips ergonomically; the REST API is used for write-side anchoring and table mutation
- GAS execution time limit: 6 minutes per run. The timed sweep batches docs to stay within the limit
- The executing user (sidebar) must have edit access to the active doc; the automation script's owner must have access to all docs referenced by ActionSheet rows
- Simple `onEdit` triggers cannot call external services; the ActionSheet timestamp stamper is an installable trigger
- The visual checked state of a checklist item is **not** readable through any Google API; the source of truth for status is the trailing `(Status)` token

### Action Format

A **floating action** (also called an action item) is a paragraph or list item in the doc. The
grammar below is authoritative (ADR-0027); a paragraph either satisfies it or is not an action.

```
actionParagraph := [inlineImage] token [assignee] actionBody [continuation*]
token           := ("ACT" | "AI") "-" digits ":" [ \t]*
assignee        := personChip | "@"? email [ \t]*
email           := [\w.+-]+ "@" [\w-]+ ("." [a-z]{2,})+
actionBody      := text [ statusToken ]
statusToken     := "(" [^)]* ")"        ; last qualifying group on the HEADER LINE only
continuation    := "\n" ( fieldLine | prose )
fieldLine       := [ \t]* fieldName ":" ( [ \t] inlineValue? | EOL )
fieldName       := fieldWord (" " fieldWord)*   ; ≤32 chars total (gts-eezz)
fieldWord       := [A-Z] [A-Za-z0-9_-]*
```

The **header line** is everything up to the first soft return. Continuation lines are soft returns
(Shift+Enter) within the same paragraph element, not separate paragraphs.

| Element | Required | Absent-value behavior |
|---------|----------|-----------------------|
| `inlineImage` | optional | no status icon; Sync inserts one on flush |
| `token` | **required** | the paragraph is not an action |
| `assignee` | optional | `assignee_email` and `assignee_name` are empty strings |
| `actionBody` text | optional | `action_text` is an empty string (bare token, gts-jxrw) |
| `statusToken` | optional | status defaults to `Open`; Sync writes `(Open)` explicitly on flush |
| `continuation` | optional | `custom_fields` is `{}` |

Rules:

- **Token.** `ACT-N:` is canonical for new writes; `AI-N:` remains valid on read indefinitely, and
  N is one shared namespace across both spellings (ADR-0023). The durable identity is
  `globalId = {docId}/{token}`, stored in ActionSheet column 1 and embedded in chip URLs. Existing
  `AI-N` globalIds are never rewritten.
- **Assignee.** From a PERSON chip when present, otherwise from a leading email in the text, where
  an optional `@` sigil is accepted and not stored. A display name derived from an email replaces
  punctuation in the username with spaces and title-cases it: `jane.smith@example.com` →
  `Jane Smith`.
- **Status.** Extracted from the **header line only**, before continuation lines are considered.
  The last `(...)` group on that line qualifies only if what follows it, trimmed, is empty or
  begins with a non-word character; otherwise it reads as sentence continuation and no status is
  detected (gts-28q / gts-v0py / gts-1tbe). `(Closed)` is recognized for archiving; any other
  value is preserved verbatim as a free-form status. Parentheses in field values and in
  continuation prose are always literal.
- **No field delimiter.** `|` carries no meaning anywhere in an action paragraph and is literal
  text. There is no escape mechanism because none is needed. The header line is not extensible;
  `Field: value` continuation lines are the sanctioned extension point (ADR-0027 rule 9).
- **Field lines.** A continuation line is a field line only if, once leading whitespace is
  stripped, it matches `fieldLine` above — a name of at most 32 characters where every
  space-separated word starts with an uppercase letter (`Consult With`, not `then he said`), then
  a colon followed by a space, a tab, or the end of the line (a bare `Consult With:` is a field
  line with an empty inline value). Leading whitespace itself is neither required nor forbidden —
  the parser strips it before testing the shape, both to read its own flush output back (rule 8)
  and to tolerate an author's own indent. A line matching the `token` production starts a new
  action and wins over `fieldLine`.
- **Prose attaches to the open block; order is retained.** The action body opens the first block
  and each field line opens a new one. A prose continuation line belongs to whichever block is
  open when it is read — `action_text` before any field line, otherwise the value of the most
  recent field line (gts-dr8j is the first-block case). Line order within a block and field order
  across blocks are document order, preserved through parse, the `custom_fields` JSON, the sheet
  cell and re-render on flush: a soft return is a `\n` in the stored value and a soft return again
  on flush. A repeated field name appends rather than overwrites.
- **Inline formatting.** Bold, italic and hyperlinks are author-owned and survive round-trip as
  per-character runs (ADR-0022, ADR-0027 rules 10–15). Config's uniform `action_text` style owns
  font family, size, colour and underline only.
- **Continuation rendering.** On flush, every continuation line is indented by a configurable
  number of leading spaces — the Config sheet's `SR Indent` key for `actionText` continuation
  lines and `Field SR Indent` independently for field continuation lines, each defaulting to `0`
  (flush-left) when the Config sheet carries no row for that key. A field's `Name:` label is
  additionally bold with a tab (not a space) before the value. Both indent and label emphasis are
  system-applied presentation, stripped back off on read and never stored as part of the value's
  text or its `runs` (ADR-0027 rule 8).
- **Unparseable input is reported.** A paragraph beginning `(ACT|AI)-\d+` that does not complete
  the grammar is recorded by VerifySync as `unparseable-action-paragraph`. It is not synced and
  not silently skipped.
- **Dates** are stored in the ActionSheet as native sheet date values; in the in-doc tracker table
  they are written using the sheet's locale-formatted date.

Example with continuation fields (as typed by an author; on flush each continuation line below is
re-rendered with the configured `SR Indent`/`Field SR Indent` indent — none at the default of 0 —
and each `Name:` label bold with a tab after it — ADR-0027 rule 8):

```
[img] ACT-7: [Jane Smith] draft the Q4 board deck and circulate (In Progress)
- pull last year's actuals
Target: September 12 board meeting
Progress: outline done, needs the revenue section
Consult With:
- Stuart
- John
Notes: Peter wants the a|b test results folded in
```

parses to `action_text` = `draft the Q4 board deck and circulate\n- pull last year's actuals` and
`custom_fields` = `{"Target": {"text": "September 12 board meeting", "runs": []}, "Progress":
{"text": "outline done, needs the revenue section", "runs": []}, "Consult With": {"text": "\n-
Stuart\n- John", "runs": []}, "Notes": {"text": "Peter wants the a|b test results folded in",
"runs": []}}` (each value carried as `{text, runs}` per ADR-0027 rule 15) — `Stuart` and `John` are
the `Consult With` value, so a tabular view of these records shows both under that column.

### Organizational Constraints
- No external service dependencies; both projects run entirely within Google Workspace
- No server infrastructure
- **The ActionSheet spreadsheet is administrator-only** — direct read/write access to it is not
  extended to action owners, reviewers, or managers, and spreadsheet sharing is not the mechanism
  for cross-team visibility control. Team-scoped visibility for everyone else is enforced by the
  verified team portal's per-team access tier (`NONE`/`VIEW`/`EDIT`, resolved server-side by
  `src/AccessControl.js` from a signed identity assertion — ADR-0021)

---

## ActionSheet Schema

### ActionSheet Columns

| Column | Notes |
|--------|-------|
| globalId | The action's global identifier `{docId}/{token}` (`ACT-{N}` canonical, `AI-{N}` legacy-compatible — ADR-0023), derived from the token at paragraph start |
| ID | Document-scoped sequential integer for human reference (e.g. shown in the tracker table) |
| Assignee Email | Canonical email address from the person chip or email-at-start text |
| Assignee Name | Display name from the chip; or derived from email username if chip absent |
| Action | Action item text (chip/email stripped, trailing `(Status)` stripped) |
| Status | Current status; Sync writes it explicitly into the floating action, using `Open` as the default; `Closed` is recognized for archiving; otherwise free-form |
| Document | Hyperlink cell — display text is the document title, target is the document URL |
| Assigned Date | Date the action was first written to the ActionSheet |
| Last Modified | Most recent reconcile or user edit time; empty means the row has never been synced (no separate Synced column) |

Sheet filters are enabled on all columns. The Document column is always written as a hyperlink cell; plain-text document names are not accepted.

### In-Doc Action Tracker Table

The in-doc tracker is a table inserted by the **Insert / refresh tracker** button, preceded by a short instructional paragraph summarizing the sync rules:

| Column | Notes |
|--------|-------|
| ID | Document-scoped sequential integer |
| Assignee | Display name (or email if name is empty) |
| Action | Action text |
| Status | Current status |
| Assigned Date | Date first synced |
| Last Modified | Most recent reconcile or edit time |

The tracker table is located by a sentinel heading paragraph so refresh can replace its contents in place without disturbing surrounding doc content.

---

## Core Capabilities
- **Web App proxy endpoint** — the same GAS script is deployed as a Web App; the add-on uses `UrlFetchApp` to call `doPost`, which runs as the deployer identity with sheet-write authority over the ActionSheet
- **Proxy-write pattern** — bridges the cross-identity boundary: add-on runs as the active user (read-only doc access); Web App runs as the deployer (`executeAs: USER_DEPLOYING`); no service account required
- Detect actions in the **active doc** (the doc the sidebar is attached to) as checklist items beginning with a PERSON chip
- Identify each action with an in-text `ACT-N:` token (or legacy `AI-N:` — ADR-0023); the `globalId` is the stable identity recorded in the ActionSheet
- Maintain a trailing `(Status)` token on each action paragraph; default `(Open)`, recognize `(Closed)` for archiving, preserve any other value as a free-form custom status
- Administrator-configurable continuation-line indent on flush — the ActionSheet `Config` sheet's `SR Indent` (action-text continuation lines) and `Field SR Indent` (custom-field continuation lines) keys each set a leading-space count applied when an action paragraph is re-rendered; the two are independent and both default to `0` (flush-left) when unset. The indent is presentation only: the parser strips it on read, so changing either key never changes stored action text or field values (ADR-0027 rule 8)
- Refresh the homepage card without mutating data — **Scan card** re-reads the current doc, tracker, and sheet-derived summary state so the visible card catches up to edits or a recent sync
- Sync the active doc to the ActionSheet on demand from the homepage card — a single **Sync now** action that scans the doc and reconciles ActionSheet rows in one round (push/pull resolved by `Last Modified`)
- Verify the active doc from the homepage card without mutating data — scans floating actions, the in-doc tracker table when present, and ActionSheet rows for the same doc; reports progress and mismatches in the verification card
- Sort and filter the active document's action list directly in the homepage card without changing document state
- Insert or refresh the in-doc tracker table on demand, prefixed with concise instructional text summarizing the sync rules
- Periodic timed sweep (owned by the ActionSheet automation script) reconciles all docs referenced by ActionSheet rows, catching docs no one opened recently
- Archive ActionSheet rows with `Status = Closed` and `Last Modified > 30 days` to the archive sheet
- Team Scope: on first sync, auto-assign a document to a team by walking its Drive folder ancestry for a `TeamData` match; the assignment is sticky (stored as the `teamScope` Drive file property) and survives the document being moved to another team's folder, unless explicitly overridden via `DocData.SyncStatus = UpdateDoc`
- Anonymous chip-preview notice (ADR-0017 Phase 1): any recipient who clicks an action-token chip's link (`ACT-N` or legacy `AI-N`) lands on `doGet ?cmd=preview&docId&ain`, a branded page showing only non-confidential metadata (document name, team, the token, status) and a Drive-ACL-gated link to open the document — never the action text. Unknown/missing actions render a non-leaking not-found page
- Import tab: the active doc's author can pull an open action from any other doc on the same team into the active doc as a new floating action with a new `globalId`; the source row is left in place and marked `Forwarded` so it drops out of future import lists
- **Verified team portal** (ADR-0021): a statically-hosted web surface (GitHub Pages) — View A, a per-team filterable action list (`list_team_actions`), and View B, a single-document action view (`get_document_actions`) reached from an `ACT-N:`/`AI-N:` chip link — that lets a person, including one outside the domain, view and (per their resolved access tier) edit actions and trigger a sync without ActionSheet access. Identity is a GIS sign-in on the separate NUUC-Dispatch project, handed off as a signed assertion GActionSheet verifies server-side (`_verifySignedAssertion`, `src/AccessControl.js`); the anonymous chip-preview notice (above) is the fallback for a caller who is not signed in or does not resolve to team access

---

## Use Cases

### Invariants (apply to every use case)

- **Identity is the text token.** The `globalId` (`{docId}/{token}`) derived from the `ACT-N:`/`AI-N:` token is the durable key (ADR-0023: `ACT-N:` canonical on write, `AI-N:` permanently read-compatible). ActionSheet rows are keyed on `globalId`. The doc-scoped `ID` is for human reference only.
- **Status is the trailing parenthesized token.** The visual checkbox state is decorative; the parenthesized status string is the truth.
- **Modified-date precedence.** Each row carries a `Last Modified` timestamp on both sides. Later wins. On tie, the ActionSheet row wins. A blank `Last Modified` means "just edited" — it is stamped to sync-start time and propagated.
- **Sync is eventually consistent.** Per-doc Sync is on-demand from the sidebar; cross-doc consistency is provided by the timed sweep.

---

### UC-A: Capture and track a new action

Actor: Document author

Preconditions:
- The add-on is installed and the user has the doc open.
- The doc contains at least one floating action: a checklist item or paragraph beginning with `AI:`/`ACT:` (auto-ID) or `AI-N:`/`ACT-N:` (explicit ID), followed by an optional assignee email and action text.

Primary Flow:
1. Author writes a checklist item that begins with `AI:`/`ACT:` or `AI-N:`/`ACT-N:`, optionally followed by an assignee email and action text, with an optional trailing `(Status)` token.
2. Author opens the homepage card and clicks **Sync now**.
3. The add-on scans the doc, detects each floating action by its `ACT-N:`/`AI-N:` token at paragraph start (a bare `AI:`/`ACT:` trigger is promoted to the canonical `ACT-N:` on first Sync — ADR-0023), assigns a `globalId` to each one, and writes a row to the ActionSheet with the resolved assignee and `Status = Open` (or the trailing token value if present).
4. The homepage card refreshes and shows the new actions.

Postconditions:
- Every floating action in the document has exactly one corresponding ActionSheet row, and the pair agrees on `Assignee Email`, `Assignee Name`, `Action` text, `Status`, and `globalId` (non-empty, format `{docId}/ACT-{N}` or, for a pre-existing legacy token, `{docId}/AI-{N}`). The ActionSheet `Document` column display text equals the current document title. No ActionSheet rows for this document exist beyond those with a corresponding floating action.

Acceptance Criteria:
- AC1: After Sync, action-token items — bare `AI:`/`ACT:` (auto-ID, promoted to canonical `ACT-N:`) and explicit `AI-N:`/`ACT-N:`, with and without an assignee email — appear in the ActionSheet with correct `Assignee Email`, `Assignee Name`, action text, status, and a non-empty `globalId`. For email assignees, `Assignee Name` is derived from the username portion of the email.
- AC2: A second Sync with no edits produces no new rows and no lost rows. All `globalId` values are unchanged. Every floating action has exactly one ActionSheet row; the pair is consistent on `Assignee Email`, `Assignee Name`, `Action` text, `Status`, and `globalId`. The `Document` column display text equals the current document title.

---

### UC-B: Update an action from either side and converge

Actor: Action owner (ActionSheet side) **or** Document author (floating action side)

Preconditions:
- The action already exists with a row on the ActionSheet and a floating action paragraph in the doc (identified by its `ACT-N:`/`AI-N:` token), sharing a `globalId`

Authoritative edit surfaces:
- The **floating action paragraph** (chip + action text + trailing `(Status)`) is the doc-side authority.
- The **ActionSheet row** is the cross-doc authority.
- The **in-doc tracker table is view-only**. Edits made directly inside its cells are not propagated and are overwritten on the next **Insert / refresh tracker** click. (See UC-C.)

Primary Flow:
1. Either the action owner edits `Status`, `Action`, or `Assignee` in the ActionSheet row, or the author edits the floating action paragraph in the doc (changing the trailing `(Status)`, the action text, or replacing the person chip with a different person).
2. The next Sync (sidebar click or timed sweep) detects the difference and applies the later-modified side's values to the other.

Postconditions:
- After Sync, every floating action in the document has exactly one corresponding ActionSheet row. The pair is consistent on: `Assignee Email` and `Assignee Name` (match the floating action's assignee), `Action` text (exact match), `Status` (exact match), `globalId` (stable, non-empty, format `{docId}/ACT-{N}` or a pre-existing `{docId}/AI-{N}`), and `Document` column display text (equals the current document title). No ActionSheet rows exist for floating actions that have been deleted; no floating actions exist without a matching ActionSheet row.
- If an earlier re-anchor left a stale duplicate ActionSheet row for the same action, the next successful Sync removes the stale row so the doc returns to a 1:1 doc-row pairing.
- After the next tracker refresh, the in-doc tracker row for that action shows the same `Action` and `Status` values.
- `Last Modified` on both sides reflects the time of the original user edit.

Acceptance Criteria:
- A sheet edit to `Status`, `Action`, or `Assignee` reaches the floating action paragraph after Sync, regardless of which side was edited last; later `Last Modified` wins.
- A doc edit to the floating action propagates to the ActionSheet after Sync for all three mutation types: trailing `(Status)` change (free-form value preserved verbatim), action text change, and chip-replaced assignee change.
- After those values converge, the next **Insert / refresh tracker** updates the tracker-table row so its `Action` and `Status` cells match the floating action paragraph and the ActionSheet row for the same action.
- The action's `ACT-N:`/`AI-N:` text token survives every edit type above, and no duplicate ActionSheet rows are created.
- Edits typed directly into the in-doc tracker table cells are **not** reflected on the ActionSheet by any Sync; the next tracker refresh restores the rendered values from the floating actions (covered by UC-C).

---

### UC-C: Insert / refresh the in-doc tracker table

Actor: Document author

Preconditions:
- The doc contains at least one action

Primary Flow:
1. Author clicks **Insert / refresh tracker** in the sidebar.
2. The add-on inserts (or refreshes) the tracker table at its anchor, prefixed with the instructional paragraph, with one row per current action in document order.

Postconditions:
- Every floating action in the document has exactly one tracker-table row and one ActionSheet row. All three agree on `Action` text and `Status`. The ActionSheet rows also agree with their paired floating actions on `Assignee Email`, `Assignee Name`, and `globalId`. The `Document` column display text on each ActionSheet row equals the current document title.

Acceptance Criteria:
- First click on a doc with N actions produces the instructional paragraph plus a table with N rows in document order, anchored so subsequent refreshes update in place.
- A subsequent click after the user closes one action and adds another produces a table that reflects both changes, in the same location, without leaving stale rows.
- For each tracked action, the refreshed table row's `Action` and `Status` cells match the current floating action paragraph and ActionSheet row values.
- The tracker table is **view-only**: any edit a user types directly into its cells is discarded on the next refresh and replaced by the rendered values from the floating actions and ActionSheet. The instructional paragraph above the table states this explicitly.

---

### UC-D: Archive closed actions

Actor: System (timed sweep on the ActionSheet)

Postconditions:
- The ActionSheet contains no rows with `Status = Closed` and `Last Modified > 30 days`; all such rows have been moved to the archive sheet with `Last Modified` preserved.
- All remaining ActionSheet rows are unchanged in content.
- No document content has been altered.

Acceptance Criteria:
- An ActionSheet row with `Status = Closed` and `Last Modified > 30 days` is moved from the ActionSheet to the archive sheet on the next sweep, preserving `Last Modified`.
- Archiving does not alter any document content.
- If a previously archived action reappears (its `ACT-N:`/`AI-N:` token still exists in the doc), a later Sync may restore an active ActionSheet row for it.

---

### UC-E: Import an open action from a teammate's doc

Actor: Document author

Preconditions:
- The active doc has a `Team Id` assigned (Team Scope) and the requesting user has access to that team.
- At least one other doc sharing the same `Team Id` has an open (unresolved) action.

Primary Flow:
1. Author opens the **Import** tab in the sidebar; it lists open actions from other docs on the same team, grouped by document name.
2. Author selects one or more actions and clicks **Import selected**.
3. The add-on inserts a new floating action in the active doc for each selection, with a new `ACT-N` token and `globalId` (a fresh token is always canonical `ACT-N:` — ADR-0023), carrying over the source action's text, assignee, and status.
4. The source row's `Action` text is appended with a `[Forward:<active doc name> AI-<new N>]` note, its `Status` is set to `Forwarded`, and it is marked dirty so the source doc reflects the new status on its next Sync.

Postconditions:
- The active doc and its ActionSheet gain one new row per imported action, with its own `globalId` (the import is a copy, not a move — the new row has no recorded link back to the source's `globalId`).
- The imported row's `Assigned Date` (`created_date`) is copied from the source action, not set to the import time — so the ActionSheet continues to reflect when the action was originally raised, not when it was last forwarded.
- The source row's `Status` becomes `Forwarded` (a free-form status recognized as resolved, per the Status invariant) and its `Action` text carries a `[Forward:...]` note pointing at the new doc/`ACT-N`. Once forwarded, the source row no longer appears in any doc's Import tab.

Acceptance Criteria:
- AC1: The Import tab lists only open actions from other same-team docs; actions already `Forwarded`, `Closed`, or otherwise resolved are excluded, as are rows whose source doc or row is `Deleted`/`Doc Not Found`.
- AC2: After **Import selected**, each chosen action appears as a new floating action in the active doc and a new ActionSheet row, with a fresh sequential `ACT-N`/`globalId`, the source's action text/assignee/status carried over, and `Assigned Date` equal to the source row's `Assigned Date` (not the import timestamp).
- AC3: Each source row's `Status` becomes `Forwarded`, its `Action` text gains a `[Forward:<target doc name> AI-<new N>]` suffix, and it is marked dirty so the source doc's own floating action reflects `Forwarded` on its next Sync.
- AC4: Re-running Import against an already-`Forwarded` source row is a no-op — no duplicate `[Forward:...]` suffix is appended and no second clone is created. (Guarded in code by `_handleForwardActionRows`; not yet reachable from a regression test — see `gts-apcu`.)

---

## Error Handling

Errors are surfaced in the sidebar (for add-on operations) or logged to the automation script's execution transcript (for sweep/archive). The full sync run is never aborted by a single-doc failure; other docs continue.

- **Checklist item with no detectable assignee** — no PERSON chip and no email-at-start text; the item is silently skipped by the scanner and does not appear in the ActionSheet. The sidebar only shows detected floating actions.
- **Orphaned ActionSheet row** — if a row's `globalId` (from an `ACT-N:`/`AI-N:` token) is no longer found in the document, the scanner checks if the action text and assignee match a different action (indicating a copy/paste duplicate). If so, the stale row is deleted. Otherwise it is marked `Deleted` on the ActionSheet for human review or archival.
- **Doc inaccessible during sweep** — that doc is skipped with a logged error; other docs continue.
- **Docs REST API quota / scope error** — surfaced in the sidebar with the underlying message; no doc or sheet writes are made for that Sync.

---

## Non-Goals
- Real-time bidirectional sync (Sync is on-demand or on the sweep cadence)
- Reading the visual checked state of a checklist item (not exposed by any API)
- Cross-document `ID` uniqueness (`ID` is doc-scoped; the cross-doc key is `globalId`)
- Preservation of rich text formatting (bold, italic, colour) on the action paragraph when rewriting the trailing `(Status)` token
- Multi-tenant or cross-organisation support

---

## Glossary
| Term | Definition |
|------|------------|
| Action item (action) | A checklist item in a Google Doc whose first inline child is a PERSON chip. The chip is the assignee. The trailing parenthesized token is the status. |
| ActionSheet | The central Google Spreadsheet that aggregates actions across docs. The cross-doc store. |
| Add-on | The Google Workspace Add-on (Docs) that provides the sidebar UI. |
| Action token | The in-text `ACT-N:` prefix at a floating action paragraph's start (e.g. `ACT-3:`), canonical for all new writes; the legacy `AI-N:` spelling remains valid on read indefinitely and shares the same `N` namespace (ADR-0023). The durable identity is `globalId = {docId}/{token}`, stored in the `globalId` column. Bare `AI:`/`ACT:` placeholders are promoted to canonical `ACT-N:` on first Sync. |
| Automation script | The container-bound Apps Script on the ActionSheet that owns the `onEdit` timestamp stamper, the timed sweep trigger, and the archive job. |
| Last Modified | A timestamp column on each ActionSheet row and (implicitly) each anchored action. Records the most recent reconcile or user edit time. Empty means never synced. |
| Sidebar | The card-based UI shown by the add-on in the active doc, built with CardService (not HtmlService). Surfaces sync state, action buttons (Sync now, VerifySync, Insert tracker), and a per-action list with status dropdown and delete. |
| Status | The recognized values are `Open`, `In Progress`, `In Review`, `Done`, and `Closed` (eligible for archive). The sidebar status dropdown exposes all five values; any other parenthesized token found in the doc is preserved as a free-form custom status. `Forwarded` is one such free-form status, set by Import (UC-E) on a source row; it is treated as resolved (drops out of Import lists and archive-eligibility checks the same way `Closed` does). |
| Import tab | A sidebar tab (UC-E) listing open actions from other same-team docs that the active doc's author can pull in as new floating actions. Importing clones the action with a new `globalId` and `Assigned Date` copied from the source; the source row is left in place, marked `Forwarded`. |
| Sweep | The time-based reconcile run on the ActionSheet that iterates rows grouped by document and pulls updates from docs no one opened recently. |
| Sync | One on-demand round in the sidebar that scans the active doc and reconciles ActionSheet rows for that doc in one shot. |
| Team Scope (`teamScope`) | The Drive file `appProperty` holding a document's assigned `Team Id`. Set once via folder-walk auto-assignment (sticky thereafter) or overridden via `DocData.SyncStatus = UpdateDoc`. |
| TeamData | Admin-managed sheet tab mapping `Team Id` -> `Folder Id` (+ `Contact`), used for folder-walk auto-assignment and the `assertTeamAccess` security gate. |
| DocData | Per-document sync-state sheet tab (`FileId`, `Doc Name`, `Last Sync Time`, `Doc Updated`, `SyncStatus`, `Team Id`, `Action Count`, `Resolved Count`) used for DocWins reconciliation and Team Scope sync. |
| `SR Indent` / `Field SR Indent` | ActionSheet `Config` sheet keys (plain non-negative integers) giving the number of leading spaces flush applies to `actionText` continuation lines and to custom-field continuation lines respectively. Independent of each other; both default to `0` (flush-left) when absent, blank, negative or non-numeric. Presentational only — stripped on read, never stored in a value's text or `runs` (ADR-0027 rule 8). |
| Tracker table | The in-doc summary table written by **Insert / refresh tracker**, preceded by an instructional paragraph summarizing the sync rules. |
| Proxy-write | The pattern where the add-on calls the Web App to perform writes under the deployer identity, bridging the add-on's active-user identity to the deployer's sheet-write authority. |
| BUILD_INFO | Version/timestamp object stamped into `src/Version.js` by `update-revision.js` before each deployment. |
| WEBAPP_URL | Script property storing the canonical Web App URL; set automatically by `doGet` (which also normalizes org-specific URL format variants). |
| WEBAPP_SECRET | Shared secret script property used to authenticate `doPost` requests from the add-on. Bearer tokens are not propagated by the Apps Script runtime. |
| TEST-WEB-APP | Anchor string in a deployment description used by `manage-deployments.js` to discover the test Web App deployment ID. |
| PROD-WEB-APP | Anchor string in a deployment description used by `manage-deployments.js` to discover the prod Web App deployment ID. |
