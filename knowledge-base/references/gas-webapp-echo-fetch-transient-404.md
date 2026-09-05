# GAS WebApp Response Delivery: Transient 404 on the `script.googleusercontent.com/macros/echo` Hop

Reusable reference: a single observed case where a GAS Web App call appeared to the client as
"Non-JSON response" even though the server-side script executed successfully — the failure was
in Google's own two-hop response-delivery mechanism, not in application code. Captured against
GActionSheet's TEST deployment (portal at `nuuc-it.github.io/Static/pub/AS-sit/`), 2026-09-02.

**Candidate for elevation to `GAS-Core/best-practices/`** once a second project needs this
(see `GAS-Core/best-practices/gas-webapp-admin/README.md` for the "provenance / second use
elevates it" convention this repo follows). Until then, this file is the source of truth.

---

## The mechanism (background)

A GAS Web App call is not a single request/response — it's two hops:

1. Client `POST`/`GET`s `https://script.google.com/macros/s/<deploymentId>/exec`. GAS executes
   `doGet`/`doPost` and, on completion, responds with an HTTP **302 redirect** to
   `https://script.googleusercontent.com/macros/echo?user_content_key=<ephemeral>&lib=<id>`.
2. The client's HTTP stack (browser `fetch`, or any client that follows redirects — see
   `scripts/call_webapp.py` and `scn.session.ScenarioSession._http_post` for the reasons this
   project's sanctioned callers already handle it) follows that redirect and fetches the actual
   response body — the JSON payload — from the `echo` URL. The `user_content_key` is short-lived.

Under normal conditions both hops complete in well under a second combined for the second hop.
"Non-JSON response from .../exec" (the error text this project's client-side error handler emits,
see `WebApp.js` `?cmd=version` verification and `docs/atdd/` mentions of deployment-propagation
lag) is usually attributed to a deploy landing mid-propagation — but that is not the only cause.

---

## The observed failure

One captured HAR (`list_my_teams` call, GActionSheet TEST, 2026-09-02 01:30:59 UTC):

| Hop | Duration | Result |
|---|---|---|
| `POST /exec` | 11.3s | **302** redirect to `.../macros/echo?user_content_key=...` (normal) |
| `GET .../macros/echo?...` | **26.8s** | **404**, `content-type: text/html`, generic Google error-interstitial page (`window['ppConfig'] = {...}` boilerplate — not app content) |

Cross-referencing the server-side structured log (Axiom/Stackdriver, shared `op` correlation id
`c071258c-284c-4558-be12-fe75dceb9f94`) for the same call:

```
01:30:58.856  webapp.request        action=list_my_teams
01:31:07.423  access.resolve.done
01:31:07.638  webapp.team.myTeams   teamCount=9   <- script completed successfully
```

**The script ran and completed correctly** (~8.8s server-side, consistent with the POST's 11.3s
wall time). The failure was entirely in the client's follow-up fetch of the `echo` URL — hop 2 —
which stalled for 26.8s and then 404'd, well past whatever TTL Google holds the ephemeral content
key for. This is invisible to server-side logging by construction: `doGet`/`doPost` already
returned before hop 2 even starts, so there is nothing to log for a hop-2 failure — a project's
Axiom/Stackdriver logs will always look clean for this failure mode.

## What was ruled out

Three follow-up HAR captures on the same portal/deployment, spanning Brave Shields on and off and
`/exec` durations from 1.5s to **14.9s**, all completed cleanly (hop-2 fetch times 124ms–2.9s,
all 200 with valid JSON). Specifically:
- **Brave Shields on/off is not a reliable predictor.** Tested both states multiple times after
  the failure; both produced clean captures. One shields-on capture had a 14.9s `doPost` (longer
  than the failing capture's 11.3s) and still had a fast, successful hop-2 fetch.
- **Backend execution time is not correlated.** The failing capture's `doPost` (11.3s) was
  shorter than a later successful capture's `doPost` (14.9s).

This leaves the cause most likely a transient stall specific to that one `echo` fetch — either on
Google's CDN side or the client's network path — rather than anything toggled by browser privacy
settings or by backend load. Single occurrence; not reproduced on demand.

## Diagnostic technique (for the next occurrence, in this or another project)

1. Capture a HAR at the moment of failure (browser DevTools → Network → "Export HAR").
2. Find the `POST .../exec` entry — confirm it resolved with a **302** and a `redirectURL` to
   `script.googleusercontent.com/macros/echo?...` (if not, the failure is upstream of this
   pattern — e.g. an actual redeploy-propagation miss, auth failure, or GAS 500).
3. Find the matching `GET .../macros/echo?user_content_key=...` entry. If its `time` is
   anomalously long (multi-second) and status is **404** with `content-type: text/html`
   containing `window['ppConfig']`, this is the same failure mode.
4. Pull the server-side structured log for the same time window and correlate by the request's
   `op` id (present in every log line this project's `WebApp.js`/`Logger` emit) — confirm whether
   the script itself completed successfully. If it did (as in this case), the fix search space is
   entirely client-side/network — do not spend time auditing the GAS handler code.
5. `python scripts/query_axiom.py --side gas --since <window>` and/or `clasp logs` (Stackdriver;
   no time-range flag, "most recent ~100 entries" only) are the two log sources; they carry the
   same underlying data, so checking one is normally sufficient.

## Possible future mitigation (not yet implemented)

Since the backend already completed successfully in the observed case, a client-side bounded
retry **on the `echo` URL specifically** (not a full re-submission of the original action) could
recover from this failure mode without duplicating a non-idempotent server-side action — worth
considering if this recurs with enough frequency to justify the added client complexity. No
project currently implements this.
