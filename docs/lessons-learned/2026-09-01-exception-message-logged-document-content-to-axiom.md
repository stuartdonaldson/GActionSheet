# LL: exception message logged real document content to Axiom

Date: 2026-09-01
Domain: logging
Session: 9a56db38-a3e7-411b-b4fa-94cdb3e12e05 (gts-gwyg)

## Observation
During implementation of `gts-gwyg`, `_quickMatchActionDoc` in `src/AdminDocScan.js` called
`Drive.Files.export(fileId, 'text/plain', {alt:'media'})` inside a try/catch whose handler was
`GasLogger.log('admin.scanTeamDocs.exportError', { ..., msg: String(e) })`.

In this GAS API version that call throws even on an otherwise successful fetch, and the thrown
exception's `.message` embeds the full fetched document body. `GasLogger` ships to Axiom.

While the automated test was running against the synthetic `TestTeamScopeA`, the operator manually
exercised the new scan button against their real "Communications" team folder. Result:
**86 `admin.scanTeamDocs.exportError` events in Axiom dataset `nuuts`**, window
2026-09-01T15:55:24Z–15:58:31Z, each carrying up to ~1050 characters of real document text —
meeting notes containing real personal names, and a second unrelated document. The session's own
fixture docs contained only placeholder text, so no automated test could have surfaced this.

The first report of the incident to the operator stated **44 events**, derived from a query window
narrower than the actual exposure. It was corrected to 86 about 10 minutes later after a fuller query.

Axiom is the only sink that received the content (the Drive-NDJSON fallback did not fire). Purging
the events requires Axiom dashboard access the session did not have; **still outstanding as of
session end**.

## Why Chain

Branch A — content reached the log
Why 1 — Real document text was written to Axiom.
Why 2 — A catch handler logged `String(e)` from an API call whose exception message can contain the fetched payload.
Why 3 — `String(e)` / `e.message` logging is a general-purpose idiom in this codebase and was applied to a doc-content-adjacent path without asking what the message can contain.
Why 4 — `GasLogger.log` accepts an arbitrary data object, so nothing structurally distinguishes a safe classification field from a field that may carry payload; safety depends entirely on the caller's judgement at each call site.
Root cause A: `GasLogger` exposes no error-logging entry point that is safe by construction, so every catch block is an independent opportunity to ship an untrusted exception message to an external sink, and the convention "don't log `e.message` near document content" cannot survive copy-paste.

Branch B — incident scope was under-reported on first pass
Why 1 — The operator was told 44 events when the true count was 86.
Why 2 — The first Axiom query used a time window narrower than the actual exposure period.
Why 3 — The window was chosen from when the failure was *noticed*, not from when the offending build was first served.
Why 4 — No procedure exists for scoping a data-exposure incident; the query was composed ad hoc under time pressure.
Root cause B: no procedure requires bounding a data-exposure query by the deployment window of the offending build before reporting scope, so a first report can understate exposure and be corrected in front of the operator.

## Initial Candidates
- f: bd issue — add `GasLogger.logError(tag, e, extra)` emitting only `e.name` plus a fixed-vocabulary keyword classification; make raw `e.message`/`String(e)` structurally unavailable in log payloads (Branch A)
- b: project CLAUDE.md — hard rule: never log `String(e)` / `e.message` from any code path that reads document content (Branch A, interim until the API change lands)
- c: `lessons-learned` or a new incident-scoping step — bound a data-exposure query by the offending build's full deployment window before reporting a count (Branch B)
- f: bd issue — purge the 86 events from Axiom dataset `nuuts` (operator action; requires dashboard access)
[Developed fully at resolve phase]

## Outstanding
The 86 leaked events have not been purged. This LL cannot be resolved while the exposure stands.
