# ADR-0016: Email-sending standard — adopt the GAS HTML email-templating pattern

Status: Accepted
Date: 2026-06-12
Relates to: ADR-0010 (add-on surface files by UI technology — module placement),
ADR-0014 (team-scope model — sender-identity rationale)

## Context

EPIC-E (`GTaskSheet-gc43`, Notify tab) and the deferred **Assignee reminder** Funnel entry
(`knowledge-base/ROADMAP.md` §Funnel) both send HTML reminder emails listing an assignee's
open actions. No canonical email-sending standard existed in this project, so the two features
risked two parallel, divergent email-template implementations. This [INF] decision
(`GTaskSheet-tv54`) records one standard before any email-send IMP work (`GTaskSheet-f3v9`)
begins.

A reusable, externally maintained pattern already exists:
`../GAS-Practices/best-practices/gas-email-templating/README.md` (renderer + builder + sender +
delivery policy + `escapeHtml_()`; provenance: project F3Go30). This ADR **binds** that practice
to GActionSheet rather than restating it.

## Decision

Adopt the GAS-Practices `gas-email-templating` pattern as the single email-sending standard for
all features in this project. Both EPIC-E's Notify send and the future Assignee Reminder funnel
item use the same template, renderer, builder, escaping helper, and delivery policy — one
implementation, parameterised, never duplicated.

Project-specific bindings:

1. **Reference, don't fork.** The authoritative mechanics live in the GAS-Practices doc above.
   This project follows it as written: `render…Html_()` → `build…Template_()` returning
   `{ subject, body, htmlBody }` → `sendConfiguredEmail_()` policy wrapper.

2. **Sender: `GmailApp`** (sends as the active OAuth user), **not `MailApp`** (sends as the
   script deployer). A reminder must visibly come from the teammate who triggered it, and
   per-user identity is consistent with the team-scope per-user access model (J-ACCESS-FILTER,
   ADR-0014) — the user only reminds on actions in documents they can read, under their own
   authorization. `MailApp`'s deployer-identity send is the wrong sender for a peer reminder.

3. **Required scope.** `https://www.googleapis.com/auth/gmail.send` must be added to
   `src/appsscript.json` `oauthScopes` (the IMP slice `GTaskSheet-f3v9` carries the manifest
   change; it is not yet present).

4. **Template location and naming.** The `.html` template lives in the Apps Script project root
   (clasp `src/`); `createTemplateFromFile` takes the bare name with no path or `.html` suffix.
   Name it by purpose: `ReminderEmailTemplate.html`. One template serves both the Notify send and
   the promoted Assignee Reminder funnel item — the email content is the same (assignee name,
   per-action text/status/source-doc link, counts).

5. **Module placement (per ADR-0010).** Email rendering and sending are host-agnostic shared
   core, so the code is **unsuffixed** (not `…Card.js` / `…Html.js`). Shared helpers
   (`escapeHtml_()`, `sendConfiguredEmail_()`, delivery-policy readers) and the reminder
   renderer/builder go in a single unsuffixed file (e.g. `EmailSender.js`). Do not split into a
   helper-vs-renderer abstraction until a second, distinct email type exists.

6. **XSS contract.** `<?= val ?>` does **not** auto-escape. Every interpolated user-controlled
   value — assignee name, action text, status, source-document title — passes through the shared
   `escapeHtml_()`. Always supply both plain-text `body` and `htmlBody`.

7. **Delivery policy (test isolation).** All sends route through `sendConfiguredEmail_()`, which
   honours an `Email Test Mode` Config-sheet flag and redirects to a safe test recipient with a
   TEST MODE banner. This keeps the EPIC-E acceptance and template `[TST]` runs
   (`GTaskSheet-twwo`, `GTaskSheet-ay5w`) from emailing real assignees. Direct `GmailApp`/`MailApp`
   calls that bypass the wrapper are disallowed.

## Consequences

- **Easier:** `GTaskSheet-f3v9` implements against a fixed contract; `GTaskSheet-twwo` asserts
  rendering/escaping against a known renderer/builder boundary (Node-unit-testable without
  mocking, per the practice's `HtmlService` guard); the Assignee Reminder funnel item, when
  promoted, reuses the same template/renderer with no second design pass.
- **Constrains:** a `gmail.send` scope must be added before send works; every send path must go
  through `sendConfiguredEmail_()`; email code stays unsuffixed shared-core, never a surface file.
- **Open seam (held, not built):** the Assignee Reminder funnel item is menu/card-triggered from
  any document with team-wide scope, whereas Notify is selection-driven from the tab. Both share
  the template/renderer/sender; only the action-set assembly differs. That shared boundary is the
  invariant this standard fixes.
