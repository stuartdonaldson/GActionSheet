# ADR-0031: Sync entry points and what each one promises

**Status:** Accepted — decided by Stuart Donaldson 2026-08-31. Amended 2026-09-01 (see
§Amendment 2026-09-01 below) — vocabulary completed, a conform gap found, DocData-as-walk-source
decided.
**Date:** 2026-08-31
**Supersedes:** ADR-0027 rule 8's "Amended 2026-08-31 (gts-tne6)" block, which specified a
different scope (it applied indent conformance to `syncAll`, including the unattended 30-minute
trigger). Rule 8 now states rendering only and points here for when a flush is triggered.
**Relates to:** gts-tne6 (the design bead this answers), gts-ttns/gts-guux (the twin-ticket pair
it scopes), ADR-0022 (inline runs own bold/italic — load-bearing for the comparison rule below),
ADR-0027 rules 5/8 (continuation-line strip and indent rendering), ADR-0009 (Dirty-flag conflict
resolution), gts-9a4j (`SR Indent`/`Field SR Indent`), gts-t78c (Force Refresh), gts-d99c
(`configFormat` sampling), gts-w9kx (menu-label disambiguation, scope widened by the 2026-09-01
amendment below)

## Context

Three separate entry points can write to a document, and until now the question *"what does a
sync promise to make true about the document?"* had no single answer. It was distributed across
four locations, none of which is where a reader would look for it:

| Where | What it decided |
|---|---|
| ADR-0027 rule 8, amendment at line ~280 | that indent participates in the ordinary diff, and in which entry points |
| ADR-0022 | that inline runs own bold/italic and Config owns font/size/colour/underline |
| `ContractSchema.js:193-203` | that `runs`/`customFields` never participate in row identity |
| `MenuHandler.js`, `menuForceRefreshActiveDoc` docstring | what Force Refresh is *for* |

**This fragmentation caused a real misreading**, which is why this ADR exists as its own document
rather than as a fifth amendment. `ContractSchema.js`'s note — *"a formatting-only change does not
orphan a row, mark it Dirty, or force a tracker re-render"* — is a statement about **inline `runs`
participating in row identity**, i.e. the document→sheet direction: a user bolding a word must not
make their row look content-changed and get orphaned. It was subsequently read as a general
"formatting never triggers a flush" invariant, which it never was. On that misreading, ADR-0027
rule 8's amendment concluded it had to *carve indent out of a standing invariant* and said so in
its section (c). There was no invariant to carve: config-driven rendering conformance and inline-run
identity are different axes and do not intersect.

The user-visible symptom that prompted the review: change `SR Indent` in the Config sheet, run a
Sync, and nothing happens — but change one word of an action and it flushes. Same for `ai_token`
and `action_text` font, size and colour: all four Config keys are read **only at flush time** and
are never compared against what the document actually shows, so a plain Sync treats a
content-matching action as fully converged no matter how far its rendering has drifted. Correcting
it required Force Refresh, which rewrites *every* action in the document rather than the wrong
ones. That is the "confusing to a user" case this ADR resolves.

## Terminology — two different things are both called "Sync"

This must be read first, because the codebase and the UI both overload the word and the two
overloaded things land on **opposite sides of this ADR's decision**.

| This ADR says | UI path | Handler | Document context? |
|---|---|---|---|
| **Document Sync** | *Extensions ▸ Action Sync ▸ Sync*, while in a Google Doc; the add-on sidebar's *Sync Now*; the web UI / team portal *Sync* button | `menuSyncActiveDoc`, `onSyncNow`, `_handleSyncDocument`/`_handleTeamSyncDocument` — all one docId | **yes** — the active document |
| **Spreadsheet Sync All** | *Action Sync ▸ Sync*, in the tracker spreadsheet | `menuSync` → `syncAll` | **no** — sweeps every tracked doc |
| **Background Sync** *(named 2026-09-01)* | none — no menu, unattended | 30-minute time trigger → `syncAll` | **no** — sweeps every tracked doc |
| **Force Refresh** | *Extensions ▸ Action Sync ▸ Force Refresh* | `menuForceRefreshActiveDoc` | **yes** — the active document |
| **Row Sync** *(named 2026-09-01)* | none — fires on an Actions-tab cell edit | `onActionSheetEdit` → `_syncSheetRowToDoc` | n/a — scoped to the edited **row**, not a document; sheet→doc only |
| **Sync Verify** *(not a sync — a read-only check)* | sidebar / web UI *Verify* | `verifyDocumentSync` | yes, but never writes | 

**Both spreadsheet-application menus are named `Action Sync` and both items are labelled `Sync`**
— see `onOpen()`'s two menu builders in `MenuHandler.js`, which now carry a label-collision note
at the site. Identical text, different handlers, and after this ADR, different behaviour. Never
write "the Sync menu item" unqualified in this codebase; say Document Sync, Spreadsheet Sync All,
Background Sync, Force Refresh, or Row Sync — whichever applies. See §Consequences for the UI
follow-up this collision needs, and the 2026-09-01 amendment below for the full six-name
vocabulary and two further findings it records.

## Decision

**Each sync entry point makes a different, stated promise. Rendering conformance belongs to
invocations that have a document context.**

| Entry point | Document context | Converges sheet⇄doc data | Conforms rendering to Config | Rewrites unconditionally |
|---|---|---|---|---|
| 30-minute time trigger → `syncAll` | no | ✓ | — | — |
| **Spreadsheet Sync All** (`menuSync` → `syncAll`) | no | ✓ | — | — |
| **Document Sync** (`menuSyncActiveDoc`) | yes | ✓ | **✓** | — |
| Sidebar sync | yes | ✓ | **✓** | — |
| Team portal / web UI doc sync | yes | ✓ | **✓** *(not yet true — see 2026-09-01 amendment, gts-gvs8)* | — |
| Force Refresh (`menuForceRefreshActiveDoc`, `force: true`) | yes | ✓ | ✓ | **✓** |
| `onActionSheetEdit` immediate flush | n/a | partial (gts-t6xs) | — | — |

**Document context is the discriminator, not user-initiation.** Spreadsheet Sync All is every bit
as user-initiated as Document Sync — a person clicks it deliberately. What it lacks is a *subject*:
it sweeps every tracked document, and the operator is not looking at any of them. That is the
structural property that decides the row, and it is why the spreadsheet item groups with the
unattended trigger without needing a special case.

The three document-context rows share one seam already — they all route through
`_menuProxyAction('sync_document', {docId, force})` → the WebApp `sync_document` route →
`syncDocument(docId, opts)` (ADR-0030). Conformance is carried as an option on that call, beside
`force`.

### The two principles this encodes

1. **A sync with no document context never changes what a reader last saw.** An unattended sweep —
   or a spreadsheet-wide one — that restyles paragraphs is indistinguishable, from the reader's
   side, from someone else having edited the document. These syncs still propagate **data**: an
   admin's edit to action text, status or assignee in the sheet reaches the document on the next
   sweep exactly as today (`sheetWins`, ADR-0009). What they do not do is re-render for a
   *presentation* change nobody asked for, in a document nobody was looking at.
2. **A sync with a document context leaves that document idempotently correct.** After it, every
   action's rendering matches the current Config. An action already matching is **not** flushed —
   conformance is a convergence check, not an unconditional rewrite.

### What "conforms rendering to Config" compares

Exactly the dimensions Config actually owns. **ADR-0022 is load-bearing here and gets this wrong
easily:**

| Config key | Compared |
|---|---|
| `SR Indent` | leading-space count on `actionText`/block-0 continuation lines |
| `Field SR Indent` | leading-space count on field-block continuation lines, label line included |
| `ai_token` | `fontFamily`, `fontSize`, `color`, `bold`, `italic`, `underline` — all six |
| `action_text` | `fontFamily`, `fontSize`, `color`, `underline` — **four only** |

**`action_text` bold and italic are never compared and never asserted.** ADR-0022 gave those two
attributes exclusively to author-typed inline runs, and `_actionTextStyleRequest`'s `fields` mask
(`SyncManager.js:3437`) already omits them for exactly that reason. A conformance check that
compared them would re-flatten per-word author formatting on every user sync — reintroducing the
precise defect ADR-0022 exists to prevent. The `ai_token` range has no such exemption: the token is
machine-rendered, never author-typed, so Config owns all six there
(`SyncManager.js:3391`).

Comparison is **document-rendered state vs. current Config**, never document vs. sheet — the
Actions sheet has no indent or style column at all, these being flush-time rendering parameters
that are never persisted as sheet data. It is therefore structurally independent of
`_rowIdentityKey`, `sheetWins`, orphan detection and `_trackerRowsMatch`, and folds into none of
them.

Granularity is per-`globalId`, matching every other `toFlush` path: one non-conforming
continuation line marks the whole action for reflush.

### Why Spreadsheet Sync All does not conform

Restyling fifty documents from a spreadsheet menu click is the same surprise principle 1 exists to
prevent, with a larger blast radius than the trigger has: the operator gets no indication of which
documents were touched. Per-document conformance stays available exactly where someone is looking
at the document and can see the result — which is also where they would notice it being wrong.

This also keeps conformance clear of `syncAll`'s skip optimisation
(`SyncManager.js:609-614`), which returns early on `lastModified <= lastSynced`. A Config change
touches no document's `modifiedTime`, so a converged document is skipped before `syncDocument()`
is ever called — conformance placed inside `syncAll` would not fire for the documents that need it
without additionally defeating that optimisation. Confining it to the single-document path avoids
the problem rather than working around it.

## Rationale

- **It matches how people actually use the tool.** Syncing the document you are reading is a
  request to make *that document* right. A sweep with no subject is a request to reconcile data,
  not a request to restyle anything.
- **It puts the expensive check where it is affordable.** The document scan does not sample
  character style today — `_runsFromRichTextRuns` reads `isBold`/`isItalic`/`getLinkUrl` on the
  *sheet-side* RichTextValue, and nothing reads `weightedFontFamily`/`fontSize`/`foregroundColor`
  off the document. Style conformance therefore needs new per-paragraph sampling on the scan path.
  Universal conformance would pay that for every action in every document on every sweep;
  confined to a Document Sync, it is one document with the user waiting on it.
- **Force Refresh gets a coherent purpose.** It stops being "the thing you have to remember to
  run" — the role a plain Sync now fills — and becomes the unconditional repair tool for when
  detection is wrong or a document is corrupt. Three entry points, three distinct promises, no
  overlap requiring a user to know which one to reach for.
- **The alternative was considered and rejected.** Flushing every action on every sync is simpler,
  and the objections usually raised against it (REST cost, revision churn) are weak: the flush is
  already batched one GET + one `batchUpdate` per document (gts-kkm7.3), and `_updateSyncState`
  stamps `lastSynced` after the flush so the skip optimisation still absorbs the steady state. It
  was rejected because it is simultaneously too broad — rewriting untouched paragraphs under a
  reader, on an unattended schedule — and too narrow: `syncAll`'s skip gate means it would never
  reach the swept documents whose Config drifted, which is the case that prompted this.

## Consequences

- **A Config style change does not propagate on its own.** After an admin edits `SR Indent`,
  `ai_token` or `action_text`, each affected document conforms on its next Document Sync, or
  immediately via Force Refresh. Accepted deliberately: explicit and visible beats a silent mass
  restyle of every tracked document on the next half-hour boundary.
- **The two `Sync` menu items now need distinguishable labels.** Before this ADR they differed only
  in scope, and identical labels in two different applications were merely unhelpful. After it they
  make different promises about the document, so identical labels are actively misleading — a user
  who learns "Sync fixes the formatting" from the Docs menu will reasonably expect the spreadsheet's
  `Sync` to do the same across their documents, and it will not — silently, with no indication
  anything was skipped. Renaming is out of scope for this ADR (it decides behaviour, not UI copy)
  and is tracked as **gts-w9kx**. Whatever the labels become, the two names in §Terminology are what
  this codebase's prose, comments and beads should use; if the chosen labels diverge from them,
  gts-w9kx updates this ADR so the two vocabularies stay reconciled.
- **`syncAll` must remain zero-argument.** A GAS time-based trigger passes an event object as the
  first argument to its handler, and `TriggerManager.js:53` registers `syncAll` by name. Adding an
  options parameter would silently bind the trigger event to it every 30 minutes. If `syncAll` ever
  needs a mode, it takes a separate named wrapper for the menu, never an optional parameter.
- **The scan needs a mode.** Style sampling is only performed when conformance is requested,
  threaded from the same option that carries the entry-point distinction. The indent half needs no
  such gate — `_parseFieldContinuationBlocksTracked` already computes each continuation line's
  leading-space count (`stripLen`) during the rule 5 strip and currently discards it.
- **Indent and style are different-sized pieces.** Indent is a comparison against a count the
  scanner already has. Style requires new character-attribute sampling. They are tracked as
  separate work even though this ADR decides them together.
- **`ContractSchema.js:193-203`'s note is unchanged in substance** but is clarified in place to say
  what it governs (row identity, document→sheet) and what it does not (config→document rendering
  conformance), so the misreading recorded in Context cannot recur.
- **Two prerequisites, both open.** Conformance necessarily causes more flushes, so the flush must
  first be correct and idempotent:
  - **gts-1h5g** — `_renderCustomFieldLines` writes `customFields[name].text` as plain text and
    never reapplies `.runs`, so every flush strips links and formatting out of field values. This
    is a defect in its own right; conformance would simply expose it more often.
  - **gts-5ktl** — nothing in the suite asserts sync-twice-no-edit produces no change
    (`apt_lane_runner.run_lane` captures once per lane run). Principle 2 promises *idempotently*
    correct; that promise needs an executable assertion behind it.
- **`onActionSheetEdit` stays out of scope.** It already flushes with no `customFields`/indent
  awareness (gts-t6xs); this ADR does not change that, and says so rather than leaving it ambiguous.

## Amendment 2026-09-01: full sync-entry-point vocabulary, a conform gap, and DocData as the walk source

Prompted by a request to name and scope *every* sync entry point in the codebase, not just the
two this ADR originally distinguished. Two findings and two design decisions came out of that
audit; none of them change §Decision's table above, which still holds.

**Vocabulary completed.** §Terminology now names all six: **Document Sync** (now explicitly
covering the Docs menu, the add-on sidebar, and the web UI/team portal — one promise, three
surfaces, all routing through the `sync_document` seam per ADR-0030), **Spreadsheet Sync All**,
**Background Sync** (the 30-minute trigger — previously unnamed in prose even though it shares
`syncAll` with Spreadsheet Sync All and is called out on its own row in §Decision), **Force
Refresh**, **Row Sync** (`onActionSheetEdit` — row-scoped and sheet→doc-only, structurally
different from every document-scoped entry above it: no document is ever "converged," one edited
row is pushed), and **Sync Verify** (`verifyDocumentSync` — not a sync at all, kept in the
vocabulary only so nobody reaches for the word "sync" to describe it). gts-w9kx (menu-label
disambiguation) is updated to track this six-name vocabulary; its own deliverable is unchanged —
UI copy for the two menu-visible labels only, since the other four names have no menu label of
their own to fix.

**Finding: the web UI does not actually conform.** §Decision's table lists "Team portal / web UI
doc sync" as document-context and rendering-conforming, on the strength of `_handleSyncDocument`
passing `conform: true` unconditionally. But the deployed web UI (`static-portal/src/index.html`)
does not call that route — it posts `team_sync_document`, handled by `_handleTeamSyncDocument`
(`TeamSync.js`), which calls `syncDocument(docId)` with **no options**, so `conform` defaults
false. The promise this ADR states for that row has never actually been kept by the real caller.
Tracked as **gts-gvs8** (fix) / **gts-ccve** (twin-ticket regression coverage, Path B). Once
landed, `_handleTeamSyncDocument` becomes an ordinary caller of the same seam the Docs menu and
sidebar already use, and the "(not yet true)" qualifier on that table row is removed.

**Decision: context-free syncs (Background Sync, Spreadsheet Sync All) walk `DocData`, not
docIds regexed out of Actions.** `syncAll()` currently derives its doc list by pattern-matching
the Actions sheet's `document_formula` column, and only consults `DocData` afterward, inside the
existing DocData-integrity pass (gts-6ipb). `DocData` is already the canonical per-doc registry
(`FileId`, `teamId`, `action_count`, `resolved_count`); it should be the *source* of the sweep,
not a side-effect target reconciled after the fact. This also turns "does every Actions reference
resolve to a DocData row" into an explicit, reportable check that falls out of the same pass,
rather than a silent repair with no operator-visible signal. The reverse is explicitly **not**
required: a `DocData` row with no live Actions rows is a normal state (a tracked document with no
open actions), not an integrity problem. Tracked as **gts-qkev** (implementation) / **gts-lk8w**
(twin-ticket).

**Decision: a repair performed during that pass must be Axiom-logged (already true — extended,
not newly required) and, when the operator is actually looking (Spreadsheet Sync All only, never
Background Sync), surfaced as a UI notice.** Per-row Axiom logging already exists
(`sync.docData.created` per repaired row, `sync.integrity.complete` aggregate, both via
`GasLogger`, both shipped on `GasLogger.flush()`) and gts-qkev's return-value change carries it
forward rather than reintroducing it. What was missing is the UI half: `menuSync()` currently
gives the operator no feedback at all, success or failure. Because `syncAll()` must stay
zero-argument (this ADR's own hard constraint, below) and is shared with the unattended trigger —
which has no UI session and must never call `SpreadsheetApp.getUi()` — the notice is added at the
`menuSync()` call site only, gated on the repair-count fields in `syncAll()`'s new return value,
using the same "extract the decision into a UI-session-free helper" pattern `configFormat`
already establishes for testability. Tracked as **gts-xqce** (implementation) / **gts-05rj**
(twin-ticket).

## What this ADR does not decide

Whether the document or the sheet is *the* authority for action data. The current model is
bidirectional — `sheetWins` pushes sheet edits to the document under ADR-0009's Dirty-flag/
timestamp resolution, while the document remains sole source of truth for `customFields` and
`runs` (gts-t6xs). This ADR is only about **rendering** conformance, which is neither direction: it
compares the document against Config, which no sheet row carries.
