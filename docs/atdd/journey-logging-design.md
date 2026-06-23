# Journey Logging Design — closing the gap between "something is slow" and "here's the report"

**Status:** Draft — proposal, not yet implemented.
**Related:** `docs/atdd/harness-design.md` §3 (`scn/reporter.py` row), `scn/reporter.py`, `scn/session.py`, `scn/ui.py`.
**Motivating case:** GTaskSheet-y8a0 / GTaskSheet-3sgr follow-up — diagnosing `test_import_access_filter`'s intermittent `show_tab("Import")` timeout required ~40 minutes of manual reconstruction (cross-referencing 4 separate trace files, reading test/helper source to label generic `run_fixture` events, inferring an un-logged step's duration from gaps between files). That reconstruction should be a single command.

## 1. Problem

The scenario harness (`scn/`) already has a real timing infrastructure (`Reporter`, `scn/reporter.py`): every `ScenarioSession` writes a timestamped, per-step JSONL + human-readable log under `test-results/runs/`, with duration (`dur_s`) on every `HTTP`/`ACT`/`UIACT`/`QUERY` event. This is more than most test harnesses have. But three gaps meant it couldn't answer "what was slow, and by how much" without manual effort:

1. **The slowest step is invisible.** `ScenarioSession.new_doc()` (`scn/session.py:365-385`) POSTs `begin_journey_session` directly via `_http_post`, *before* the `Reporter` exists (you need the response's `docId` to construct the session that owns the reporter). Doc creation — plausibly the single most expensive operation per session — never gets a trace event. Its duration can only be inferred after the fact from the gap between two other sessions' file-creation timestamps.

2. **Every fixture call looks identical.** `ScenarioSession._post_fixture()` wraps the payload as `{"action": "run_fixture", "fixture": fixture_name, ...}`. `_post()`'s event-naming (`scn/session.py:248`) does `payload.get("action") or payload.get("fixture")` — `"action"` wins, so every one of `move_doc_to_folder`, `setup_team_scope_fixture`, `set_docdata_row`, `get_docdata_row`, etc. is logged as the same bare string `"run_fixture"`. Reconstructing "which call was this" requires reading the test's source and counting call order by hand.

3. **One test, many trace files, no merge.** A test that creates N `ScenarioSession`s (e.g. `test_import_access_filter` creates 6) gets N separate `Reporter` instances, each writing its own `test-results/runs/<node_name>_<utc>.trace.{jsonl,log}` — and since `node_name` defaults to the *same* `request.node.name` for every session in one test, the only thing distinguishing the files is a few-second-apart timestamp suffix. There is no single view of "everything that happened in this test, in order." Producing one requires `cat`-ing the files, sorting by `t_wall`, and manually attributing each row to a session by reading its call pattern.

A fourth, smaller gap surfaced during the same investigation: **GAS-side corroboration isn't available after the fact.** `GasLogger`'s file output only captures whatever the GAS code explicitly logs (in practice: the 30-minute sync trigger, not test-route fixture calls), and `clasp logs` is a live tail with no historical range query — so once a run has finished, there's no way to retroactively confirm whether slowness was server-execution time or something else. This is flagged here for completeness but the fix (live-capture discipline, §5) is process, not code.

## 2. Goals

- Every scenario-test step (HTTP round-trip, sync, UI action) is logged with **what it's doing** (a real name, not `"run_fixture"`) and **duration**, with no step invisible.
- One command produces a single, chronological, human-readable report for a given test run — no manual `cat`/`sort`/`jq` reconstruction, no reading test source to attribute events to sessions.
- The report is generatable from a **passing** run too, not just on failure — so "what's typical" and "how much does it vary" can be answered from historical data, not just incident postmortems.

## 3. Non-goals

- Replacing or restructuring the existing `Reporter`/Allure/JUnit reporting (AC drain, `elapsed.*` properties) — that mechanism is unrelated and works; this proposal is additive.
- Real-time alerting or CI gating on duration thresholds — out of scope; this is a diagnostics/reporting improvement, not a perf-regression gate (could be a later follow-up once a baseline exists).
- Fixing the underlying slowness observed in the motivating case — that's a separate, environmental question this tooling is meant to help answer, not the thing being designed here.

## 4. Design

### 4.1 Name every event by what it actually did

`ScenarioSession._post()` (`scn/session.py:240-259`) picks the event name. Change the precedence so the more specific name wins:

```python
action = payload.get("fixture") or payload.get("action") or "post"
```

`_post_route()` calls have no `"fixture"` key, so their behavior is unchanged (still named by `"action"`). `_post_fixture()` calls gain their real name (`move_doc_to_folder`, `setup_team_scope_fixture`, ...) for free. One-line change, no new fields, no schema migration (the `event()` schema's `name` field already exists).

### 4.2 Make doc creation a logged step

`new_doc()` can't use `self._reporter` because the reporter doesn't exist until the session does. Two options:

- **(a) Time it in the classmethod, inject a synthetic first event after construction.** `new_doc()` already measures nothing today; wrap the `_http_post` call in `time.monotonic()`, then immediately after constructing `cls(...)`, call `instance._reporter.event("HTTP", "begin_journey_session", dur_s=<measured>, _t_elapsed=0.0)` so it's the first row in that session's own trace, instead of inferred from cross-file gaps.
- **(b) Module-level pre-session Reporter.** Heavier — would need a process-wide or fixture-scoped Reporter that outlives any one session, contradicting the current "one Reporter per ScenarioSession" ownership model documented in `harness-design.md` §3.

**Recommendation: (a).** It's a 3-line change, keeps the existing one-Reporter-per-session ownership rule intact, and the data lands in the right file (the session's own trace) instead of needing cross-file inference.

### 4.3 A standalone logging service, decoupled from the execution it's measuring

The deeper fix for "one test, many trace files, no merge" (and for §1's fourth gap — no GAS-side corroboration) is to stop treating client-side (`Reporter`) and server-side (`GasLogger`) logging as two separate systems and have **everything write through one sink**, so events naturally share one clock with nothing to reconcile after the fact.

**Why not just reuse `GasLogger` inside the main webapp (the first draft of this section).** `GasLogger`'s buffer lives in the *same* GAS execution that's doing the work being measured — entries sit in memory until that execution calls `flush()`. If that execution is the slow/hanging/crashing one (exactly the failure mode this tooling exists to diagnose), the buffered entries can be lost before they're ever written. Routing Python's log calls through a new route on the *same* webapp inherits that risk and adds no independence — it's still subject to the main app's GAS execution quota, which may itself be what's exhausted.

**Design: a separate, minimal Apps Script webapp, its own deployment.** A small standalone script (own `clasp` project/deployment, own quota, no business logic) with one `doPost(e)` handler. Two layers, not one:

- **Fast path (what the caller waits on):** the handler does the minimum work needed to durably accept the entry, then returns. A single `sheet.appendRow()` per call is a reasonable starting point (it's already a single atomic write), but if call volume makes even that too slow to do synchronously, the handler can instead append to a lightweight "incoming" queue (the same `appendRow()`, just to a smaller/narrower tab, or `PropertiesService`/`CacheService` for short bursts) and return immediately — the point is the caller's doPost round-trip shouldn't be coupled to however expensive the *final* compacted write turns out to be.
- **Durable compaction (decoupled from any caller):** a time-driven trigger (e.g. every 1-5 minutes, the same pattern this project already uses for the 30-minute sync trigger) drains the queue and writes it to the final append-only log sheet/file in bulk. This is the actual "buffer, then flush" the GasLogger critique above was about — the difference is *where* the buffer lives: a durable queue that survives between separate executions (a sheet tab, not an in-memory JS variable, since GAS doesn't guarantee in-memory state persists across separate requests), drained by a trigger that's independent of whichever caller's execution is slow or crashing.

Whether the fast path needs the queue/trigger split or a direct `appendRow()` is good enough is a tuning question that depends on actual call volume — worth deciding empirically (start with direct `appendRow()`, add the queue only if doPost latency under real load proves it's needed) rather than building the more complex version up front. Three independent callers write to this service:

- the Python `Reporter` (replacing/supplementing its local trace files),
- the main GTaskSheet webapp's own server-side events (replacing `GasLogger` calls at the same call sites, or running alongside it during a transition period),
- any other GAS-side code that wants to log (e.g. the 30-minute sync trigger), without needing `gasLogDir`'s Drive-mount convention at all.

A spreadsheet sink (vs. a flat NDJSON file) also directly serves §4.4's variance-tracking goal: filtering/pivoting "what's the p95 duration of `move_doc_to_folder` over the last 50 runs" is a Sheets formula away, not a script that has to parse and aggregate many small files.

**Retrieval.** Two options, not mutually exclusive: (a) a `doGet(e)` on the same standalone webapp that returns rows since a given timestamp/runId as JSON — the curl-able approach originally proposed; (b) since the harness already downloads sheet exports elsewhere (`download_xlsx()`), read the log sheet the same way, no curl needed. (a) is more useful for ad-hoc live tailing during a diagnostic session; (b) is simpler and consistent with existing harness conventions for routine report generation.

**Cost of the round-trip itself.** A POST to this service is still a network call, and an HTTP call to *any* Google-hosted endpoint shares the same general network path as the main webapp — it won't be immune to broad Google-side latency (only to *this project's* GAS execution-quota exhaustion specifically, since the standalone deployment has its own separate quota bucket). The batching guidance from the original draft still applies: log natural checkpoints (`session.close()`, `checkpoint()`), not every micro-step, so the logger doesn't add as much round-trip overhead as the thing it's trying to measure.

**`journey_report.py` is still useful, but simpler.** A merge/report tool remains worth building, but now it only reads **one schema**, from **one source** (the log sheet), with **one clock** — Python steps and GAS-side events interleave automatically because they were always written to the same place. This closes §1's fourth gap (no GAS-side corroboration) as a side effect, with no separate `clasp logs --watch` capture needed for routine diagnosis.

### 4.4 Baseline / variance tracking

With 4.1-4.3 in place, every run's events land as rows in the log sheet, pass or fail — a `QUERY`/pivot over "all `move_doc_to_folder` rows in the last N runs" answers "what's typical and how much does it vary" directly in Sheets, no separate aggregation script needed for a first cut. A dedicated report script (min/median/p95 per event `name`, trended over time) remains a reasonable follow-up once enough history accumulates, but isn't required to get *some* answer to the variance question — **the spreadsheet sink makes this materially easier than the file-based design's first draft**, where aggregation would have needed a script to parse and merge many small NDJSON files first.

## 5. Process note: when even the logging service might be the problem

Not a code change. If the standalone logging webapp's own deployment is itself suspect (e.g. its quota is *also* exhausted, or it's not receiving requests at all), fall back to `npx clasp logs --watch > /tmp/clasp-live.log &`, started *before* the test run — `clasp logs` has no historical range query, so it only confirms activity that happens while it's actively tailing. With the standalone service in place this should rarely be needed; kept here as the fallback of last resort.

## 6. Open decisions (need a human call before implementation)

- §4.2's synthetic first-event approach (option a) versus accepting the inferred-from-gap status quo for `begin_journey_session` specifically — (a) is recommended but changes `new_doc()`'s contract slightly (it now does reporter-shaped work without a `self` to call it on yet, until after construction).
- §4.3's batch boundary for the Python side: flush to the logging service at every `checkpoint()` (finer-grained, more requests) vs. only at `session.close()` (coarser, fewer requests, but a hung/crashed test loses its unflushed batch unless flushed from a `finally` block).
- Whether the main GTaskSheet webapp's server-side events should *migrate* from `GasLogger` to the new standalone service, run *alongside* it during a transition period, or stay on `GasLogger` entirely (only the Python/test side uses the new service). Full migration gets the cleanest single-source-of-truth log but touches every existing `GasLogger.log()` call site in the main app; running alongside is lower-risk but keeps two systems alive longer. Recommendation: start test-side-only (Python + test routes), evaluate before touching production logging call sites.
- Whether `Reporter` should keep writing its existing local `trace.jsonl`/`.log` files *in addition to* posting to the standalone service (redundant but resilient if the service itself is unreachable — exactly the kind of failure this tooling needs to diagnose) or be replaced by it. Recommendation: keep both, at least initially.
- New deployment to stand up and maintain (its own `clasp` project, its own auth/token scheme) — this is real ongoing overhead, not a one-time cost, and should be weighed against how often journey-timing diagnosis actually comes up versus a lighter-weight fallback (e.g. accepting `clasp logs --watch`, captured live, as "good enough" for the rare cases).
- Whether `doGet` (live curl-able tail) is worth building alongside `doPost`, or whether reading the sheet via the harness's existing `download_xlsx()`-style convention covers the need.

## 7. Acceptance criteria (for whichever slice gets implemented)

- `_post()` names HTTP events by fixture name when present; existing `_post_route` callers' event names are unchanged (regression check: any test asserting on a specific event `name` string still passes).
- A `ScenarioSession` created via `new_doc()` has a `begin_journey_session` event logged with a real measured duration, not inferred after the fact from gaps between files.
- A new, independently-deployed Apps Script webapp accepts a log entry via `doPost` and durably accepts it fast (direct `Sheet.appendRow()`, or a queue-tab + time-driven-trigger compaction if call volume requires it) — its quota and execution are decoupled from the main GTaskSheet webapp's.
- The Python `Reporter` posts to this service (batched at natural checkpoints, not per-event) in addition to its existing local trace files.
- A merge/report tool reading the log sheet produces one chronologically-sorted, human-readable table — Python steps and GAS-side events interleaved by real timestamp — without requiring the operator to read test source to label any event, written to `test-results/JOURNEY-<slug>-<utc>.log`.
- No existing AC-drain / JUnit / Allure reporting behavior changes (this is additive to `Reporter`, not a replacement).

## 8. Current state: GAS-side vs Python-side event naming (GTaskSheet-ecs1)

Until §4.3's unified sink ships (still an open decision, §6), GAS-side and Python-side
events are logged through two separate systems with two different naming schemes, and
nobody building a single Axiom view that spans one request end-to-end can facet across
both without already knowing the two vocabularies map to the same operation. This
section is that mapping — read it before trying to correlate a Python test step with
the GAS-side events it triggered.

**GAS side** (`GasLogger`, `side:"gas"` in Axiom) uses the `domain.event` taxonomy —
`knowledge-base/adr/0019-gaslogger-naming-standard.md`.

**Python side** (`scn/reporter.py` / `scn/session.py`'s `ScenarioSession._post()`,
`side:"python"` in Axiom) names events by the raw action/fixture name straight off the
wire — `payload.get("fixture") or payload.get("action")` (§4.1) — deliberately, so the
event reads as "what was actually called," not a derived taxonomy.

Re-pulled live (`python scripts/query_axiom.py --limit 200 --since 24h`, 2026-06-19):
182 `side:"gas"` events across 18 distinct names, 18 `side:"python"` events across 9
distinct names — the split still holds.

| Python action/fixture name | Caller | Corresponding GAS-side event(s) |
|---|---|---|
| `begin_journey_session` | `ScenarioSession.new_doc()` — direct `_http_post`, not via `run_fixture` | `journey.begin` (`WebApp.js` `_handleJourneySession`) |
| `end_journey_session` | `ScenarioSession.close()` — `_post_route`, not via `run_fixture` | `journey.end` (same handler) |
| `append_doc_paragraph` | `ScenarioSession.append_paragraph()` — `_post_route` | `test.append_doc_paragraph` (`WebApp.js`) |
| `sync_all` | `_post_fixture("sync_all")` → `TestFixtures.js` `case 'sync_all'` → calls `syncAll()` | the full `sync.*`/`archive.*`/`tracker.*` cascade: `sync.all.start(.identity)`, per-doc `sync.scanned`/`sync.complete`/`sync.docNotFound.{invalid,trashed,confirmed}`/`sync.skip`, `sync.teamScope.*`, `sync.archive.doc_not_found`, `archive.complete`, `sync.integrity.complete`, `sync.all.complete` — plus the generic `fixture.setup` every `run_fixture` call produces (below) |
| `sync_document` | `ScenarioSession.sync()` — `_post_fixture("sync_document")`, reported as Reporter `ACT` step `"sync"` (a different event from the HTTP-level `"sync_document"` name) | `syncDocument(docId)`'s per-doc subset of the same `sync.*` family (no `sync.all.*`) — plus `fixture.setup` |
| `get_docdata_row`, `set_docdata_row` | `_post_fixture(...)` | **no domain-specific GAS tag** — these fixtures only produce the generic `fixture.setup` wrapper (`data.scenario` carries the fixture name); read/write DocData directly with no other logged side effect |
| any other `_post_fixture(name)` call (`uc_a_clear`, `sidebar_set_status`, `sync_status_doc_not_found`, ...) | `TestFixtures.js`'s `setupTestFixtures()` switch | `fixture.setup` (always) **+** that case's own `fixture.<name>` tag, if the case logs one explicitly — not all cases do (see `get_docdata_row`/`set_docdata_row` above) |

**Why `fixture.setup` is the GAS-side anchor for most fixture calls, not a per-fixture
tag:** `setupTestFixtures()` logs one generic `GasLogger.log('fixture.setup', {
scenario: resolvedScenario })` after every successful run, regardless of which `case`
ran (`TestFixtures.js`, end of function) — that's the event to correlate against a
Python `_post_fixture()` call when the specific fixture case has no GasLogger call of
its own. A fixture's own `fixture.<name>` tag, when present, is additional detail from
inside that case, not a replacement for the generic wrapper.

**This is documentation, not a fix.** No code changed to produce this table; it
re-derives and records the mapping so a human or dashboard query can bridge the two
vocabularies manually. §4.3's unified-sink design remains the architectural fix for
needing this table at all, and remains an explicit open decision (§6) — not implemented
as a side effect of writing this section.

## 9. GAS-side call-tree correlation: `op`/`parentOp` (GTaskSheet-65g1, GTaskSheet-j8cn)

Before this, a multi-step GAS execution's own sub-events (e.g. `syncAll()`'s
`sync.all.start` then per-doc `sync.scanned`/`sync.complete` ×N then
`sync.all.complete`) had nothing tying them together except time proximity — fragile,
and exactly the kind of manual reconstruction this whole doc exists to eliminate (§1).

**Mechanism** (`GasLogger.startOp()` / `endOp()` / `getCurrentOp()`,
`src/GasLogger.js`): module-level state (`_currentOp`, `_parentOp`) holds a
`Utilities.getUuid()` minted at `startOp()`, stamped as `entry.op` on every
`GasLogger.log()` call until `endOp()` clears it. `_postToAxiom`'s row mapping
includes `op`/`parentOp` when present, so a single invocation's sub-events become
queryable by exact id, not time-window guessing.

**Why module-level state is safe:** each GAS execution (each `doPost`/`doGet`/trigger
invocation) gets its own isolated global scope — there is no shared memory across
concurrent invocations. A module-level "current op" variable can't leak between two
simultaneous `syncAll()` runs the way it would in a long-lived server process; it only
ever needs to survive within one execution's own call stack, between that execution's
`startOp()` and `endOp()`.

**Cross-execution correlation (`parentOp`):** `startOp(receivedOpId)` never adopts a
caller's id as its own (that would collapse concurrent/replayed invocations under one
id, breaking "op is unique per execution"). Instead the callee still mints its own
fresh `op`, and if a `receivedOpId` was passed in, stamps it onto every entry as a
separate `parentOp` field — the trace-id/span-id shape from distributed tracing (`op`
= this execution's own span, `parentOp` = the caller's span). `getCurrentOp()` lets a
caller read its own op id before issuing a `UrlFetchApp` call so it can pass it along
as `opId` in the request payload. This is what GTaskSheet-j8cn wired across the
addon→WebApp HTTP boundary: `WebApp.js`'s `doPost` reads `payload.opId` and passes it
into `startOp()`; `WorkspaceAddonCard.js`/`EditorAddonCard.js`/`SyncManager.js` outbound
calls read `GasLogger.getCurrentOp()` and set it as `opId` on the way out.

**Current scope: `syncAll()` only.** `journey-session` begin/end
(`WebApp.js`'s `_handleJourneySession`) and other multi-step-looking entry points
(import flows) were evaluated and found *not* to need `op` — each handler invocation
(`begin_journey_session`, `end_journey_session`) emits exactly **one** `log()` call, so
there are no within-invocation sub-events to correlate. `docId` already links the begin
and end events across their two separate `doPost` executions. **Before re-proposing
wiring `op` into journey-session (or any other entry point), re-check that this is
still true** — it was an empirical finding (count the `GasLogger.log()` call sites
inside the handler), not a general exclusion rule.

**Verification it's non-vacuous:** `tests/test_sync_all.py::test_sync_all_op_correlation`
asserts two back-to-back `syncAll()` sweeps each have their own sub-events sharing
exactly one `op` id, and the two sweeps get different ids — proved to actually fail
(not a fence artifact) by reverting the `GasLogger.js`/`SyncManager.js` changes and
redeploying TEST before restoring.

**Related follow-ups (both closed, kept here as the historical pointer):**
GTaskSheet-j8cn (cross-invocation `parentOp` propagation, addon→WebApp — described
above) and GTaskSheet-x94a (`GasLogger` tag-naming taxonomy cleanup, unrelated to
correlation but touched the same call sites around the same time;
`knowledge-base/adr/0019-gaslogger-naming-standard.md`).
