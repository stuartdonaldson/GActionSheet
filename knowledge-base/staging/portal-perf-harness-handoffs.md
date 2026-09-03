# Handoff log — portal-perf-harness

Companion to `knowledge-base/staging/portal-perf-harness.md`. Split out 2026-09-02: nine stages
each carrying the guide's four-part handoff cannot fit `plan-lint.py`'s 300-line cap on the plan
itself, and the handoff content is required by `$DEVSTANDARD/doc-framework/planning-guide.md`
§"Handoff notes". The plan keeps sequencing and deliverables; this file keeps the record.

Four parts per stage: **Done** (real output pasted) · **Found** (disposition inline on every
finding) · **Next stages must know** · **Deliberately not done**. The beads carry the same notes —
`bd show <id>` — and are the authority where the two differ.

### Stage 1 — `access-resolution` (2026-09-02) — **NOT CLOSED, blocked**

Beads `gts-vkui`, `gts-s1j5` (both in progress). New: `gts-a37j` (`human`, P1) blocks both.
Full notes on the beads — `bd show gts-vkui gts-s1j5 gts-a37j`.

**Done** — `gts-dige` landed mid-stage; TEST is `v0.2.3.94` and the contracted route exists
(`call_webapp.py flush_access_cache` → `{"ok":true,"flushed":0}`). `gts-vkui`: the two AC-T7 tests
were still named `*_does_not_exist_yet`, now false — renamed, red proof moved to the docstring;
added AC-T7's missing halves (`assert_log` on `access.cache.flush{flushed}` by caller-generated
`opId`, and an identity-gated cacheHits/cacheMisses case). `gts-s1j5`: added `team_sync_document`
under the drive-inherited folder, `list_my_teams` + `list_team_actions` as own call-sites, AC2 on
`list_team_actions`, and the four `sharedDriveInherited*` keys into the module docstring per AC4.

Red-first proof for the new AC-T7 assertion (condition violated, then restored):

```
E           Failed: [AC-T7] flush_access_cache must answer ok:true+flushed for a valid secret;
                    got GAS error GAS returned error for action='flush_access_cache': unauthorized
1 failed in 20.33s
```

```
$ pytest tests/test_access_resolution_caching.py tests/test_verify_access.py -q
18 passed, 21 skipped in 73.05s
```

**Operator check — run, and *not executable*.** Not a green-only result; a cannot-run result.
Scratch worktree with `AccessControl.js`/`SPIKE.js` reverted to `76d1b98^`:

```
! Deployed build mismatch: expected version='0.2.3.38' target='TEST', got '0.2.3.94' 'TEST'.
  Re-run 'pnpm run deploy:test' and re-run the suite. !
```

Generalised into §GAS-side red-first proofs. Even with the guard bypassed every detecting test
**SKIPs** — skip-only, never red. Restated in `gts-a37j`'s design field.

**Found**

| Finding | Disposition |
|---|---|
| `access.cache.flush`'s `flushed` field **does** survive Axiom ingest despite the 257-column cap (`gts-pfyx`) — observed live | Fixed now; in the test docstring |
| ~~`access.resolve.done` has never been observed live~~ **— WRONG, retracted 2026-09-02.** Stage 2 found 10 emissions in 48h; independently re-verified from the orchestrator (`query_axiom.py --name access.resolve.done --since 48h` → 10 events, all of `directoryCalls`/`permissionsListCalls`/`cacheHits`/`cacheMisses`/`path`/`resourceCount`/`groupCount` intact through the 257-column cap). Stage 1 generalised from an unverified-identity request. | Retracted here; correction on `gts-vkui`. The column-cap worry it raised is **closed**, not deferred |
| `mint_test_assertion` still dead — `run_fixture` returns an empty `data` (`gts-79dw.4.18` HMAC gap) | Bead `gts-a37j` |
| **No TeamData folder inside a Shared Drive exists in this environment**, so `76d1b98`'s fix has never executed under test | Bead `gts-a37j` |
| `tests/test_access_resolve_dedupe.py` (untracked, 570 lines) belongs to `gts-29zs`, already closed | Dropped — another bead's deliverable; left untouched |
| AC-T7's bad-secret negative is satisfied by the `WEBAPP_SECRET` gate running *ahead* of dispatch, so it was green while the route was unregistered — not evidence the route exists | Fixed now; claim corrected in docstring |

**Next stages must know**

- **Stages 2 and 3 inherit the same wall** — both need a verified identity. Do not open stage 3
  expecting a red-first demonstration before `gts-a37j`.
- "Revert locally and run" is dead for every GAS-side Operator check — generalised into
  §GAS-side red-first proofs; stages 1, 3 and 5's checks were rewritten 2026-09-02. Stage 9's is
  an observation and survives unchanged.
- `regression=pending` on both beads; neither has had `pytest -x`.

**Deliberately not done**

- **Full `pytest -x`** — CLAUDE.md's Backstop default forbids it on an agent's own initiative
  against the live backend. `gts-vkui` AC-T10 stays unmet by design.
- **No deploy** (would have pushed 132 uncommitted unrelated files to TEST); **no commit or push**
  (rule 7 deferred to the human by instruction).
- **Did not read `src/AccessControl.js` / `src/SPIKE.js`** while authoring (`gts-vkui`
  no-shared-context); the scratch revert ran last, via `git checkout`, without reading them.

### Stage 2 — `all-teams-view` (2026-09-02) — **NOT CLOSED, gate pending**

Bead `gts-zxes` (in progress). New: `gts-m8ll`. Full notes on the beads — `bd show gts-zxes gts-m8ll`.

**No code changed this session. None needed changing.**

**Done**

The stage opened on a false premise — that a prior session had left this bead half-built in the
working tree. It had not. `gts-zxes` landed **complete** in `76d1b98` (2026-08-30), and its UI
follow-on `gts-zeti` is closed. The uncommitted diffs in the stage's four artifacts belong to
other beads entirely:

| Artifact | Uncommitted diff actually belongs to |
|---|---|
| `src/AccessControl.js` | `gts-49u1`, `gts-dige`, `gts-pulj` |
| `src/TeamListing.js` | `gts-gwyg` (`isAdmin` field only) |
| `src/WebApp.js` | `gts-5kyu`, `gts-c7fp`, `gts-pl2k`, `gts-pz8o`, `gts-ttns`, `gts-6vzm`, `gts-gwyg`/`lgpx`/`qkev` |
| `static-portal/src/index.html` | `gts-zeti`, `gts-gwyg`/`lgpx` |

Not one line of that diff is this bead's. So the stage became: prove what shipped actually works,
and set up the gate that freezes the AC.

TEST serves `{"ok":true,"version":"0.2.3.94","target":"TEST","env":"test"}` (`?cmd=version`). The
`ALL` sentinel branch is live and fails closed — the `teams` key appears **only** on the ALL
branch, which is what makes this a proof that the branch was *taken*, not merely that the route
exists:

```
$ python scripts/call_webapp.py list_team_actions --data '{"assertion":"not-a-real-token","teamId":"ALL"}'
{"tier": "NONE", "teamId": "ALL", "isAdmin": false, "serverVersion": "0.2.3.94",
 "teams": [], "actions_len": 0, "has_teams_key": true}

$ ... --data '{"assertion":"not-a-real-token","teamId":"TestTeamA"}'
{"tier": "NONE", "teamId": "TestTeamA", "isAdmin": false, "serverVersion": "0.2.3.94",
 "actions_len": 0, "has_teams_key": false}
```

The published SIT portal (`http=200`, 59141 bytes) is byte-current with
`static-portal/src/index.html` — normalised diff is 15 lines, every one a build-time stamp
(`STATIC_BV`, `STATIC_WEBAPP_URL_`, `STATIC_ENV_LABEL_`) — and its badge reads
`BUILD_VERSION_ = "0.2.3.94"`, matching the backend. Both halves are deployed and in agreement.

**AC-3 is evidenced live**, which nobody expected going in (`python scripts/query_axiom.py --since 48h --name access.resolve.done`):

```
op=60891306  email=sdonaldson@northlakeuu.org   resourceCount=4   permissionsListCalls=4   directoryCalls=1  cacheHits=0  cacheMisses=5    (paired myTeams: teamCount=9)
op=f1a19d1d  email=sdonaldson@northlakeuu.org   resourceCount=4   permissionsListCalls=0   directoryCalls=1  cacheHits=4  cacheMisses=1    (paired myTeams: teamCount=9)
op=cb0e49fe  email=stuart.donaldson@gmail.com   resourceCount=11  permissionsListCalls=11  directoryCalls=1  cacheHits=0  cacheMisses=12   (paired myTeams: teamCount=4)
```

Nine visible teams resolved over four distinct resource scans; one `Permissions.list` per distinct
resource; one Directory call for the whole request. Stated rather than glossed: `resourceCount`
counts *distinct* resources, so this demonstrates one-scan-per-resource. It does not by itself
prove the nine teams reference fewer than nine folders — TeamData is not readable without an admin
credential. The `permissionsListCalls == resourceCount` equality is the load-bearing part.

AC-2 and AC-4 traced statically (line-level trace on the bead): all three portal write call sites
send `teamIdForWrite(row)` → `row.team_id`, and `src/TeamActionWrite.js` resolves against
`payload.teamId`, so the ALL sentinel never reaches a write path; `_handleListTeamActions` opens
the spreadsheet and reads TeamData exactly once each. `node --check` clean on all three GAS files.

**Found**

| Finding | Disposition |
|---|---|
| The stage's four artifacts were **not** half-finished work on this bead; the diff belongs to nine other beads (table above). The bead's own code shipped in `76d1b98` two days before the stage opened | Fixed now — Deliverable line corrected; recorded on `gts-zxes` so it is not re-opened expecting unfinished code |
| **`access.resolve.done` HAS been observed live**, contradicting stage 1's handoff. Ten emissions in 48h from two real browser identities, all seven fields intact through Axiom's 257-column cap | Fixed now — `bd remember`; correction noted on `gts-vkui`, whose test docstring carries the false claim; `gts-a37j` AC-4 re-scoped in a note |
| **`gts-a37j` blocks the test harness, not a human.** A human's own browser supplies a verified identity through GIS, and already has on this build (9 and 4 visible teams). Stage 1 generalised its wall one step too far, and stages 2 and 3 inherited the over-generalisation | Fixed now — stage 2's Operator check re-scoped as executable; noted on `gts-a37j` |
| **A real Google session cannot be driven through GIS by Playwright.** With `~/.playwright/sdonaldson.json` the portal *does* recognise the account and renders GIS's "Sign in as Stuart" button, but the click dies inside FedCM, which needs a native account-chooser dialog automation cannot reach: `FedCM get() rejects with NetworkError` headless, `AbortError: signal is aborted without reason` headed under `xvfb`. Tried both, with and without an explicit click on the GIS iframe | Bead `gts-l632` (noted there, so the route is not re-derived) and `gts-a37j` (third option ruled out before provisioning work starts) |
| **AC-4 has no black-box oracle.** `_readTeamDataRows` (`src/SyncManager.js`:2897) and `_openActionSheetSpreadsheet` are uninstrumented; `access.resolve.done` counts Drive/Directory round-trips only; `webapp.team.list` carries no read count. So stage 3's `gts-lkaa` cannot assert AC-4 without reading the implementation, which the twin-ticket rule forbids | Bead `gts-m8ll` (filed, `stage:all-teams-coverage`) |
| **This document now fails `plan-lint.py`'s 300-line size cap** (426 lines after trimming, ~300 of which predates this stage). Nine stages each carrying a four-part handoff cannot fit the cap; the handoff content is required by the guide, so the cap and the plan's span are in genuine conflict | Not fixed — trimmed this stage's handoff to the minimum the guide requires and left the breach visible rather than deleting required content. Discharge at plan retirement by graduating handoffs per `doc-standard.md` §Graduation Rules, or split the plan |
| The ALL-teams page badge reads `MULTIPLE — permissions vary by team` rather than a blended tier (`index.html`:927–935), and per-doc gating reads `state.teamTiers[team_id]` at :1031 and :1145. The blended-tier trap AC-1 warns about is structurally absent | Deliberately dropped — nothing to do; recorded so the reviewer knows it was checked and need not re-derive it |

**Next stages must know**

- **Stage 3 is not one wall, it is two.** `gts-lkaa` (server-side) is blocked by `gts-a37j` and now
  also wants `gts-m8ll` for AC-4. `gts-l632` (Playwright) is blocked by `gts-a37j` via
  `mint_test_assertion` and **cannot** be rescued by a captured browser session — see the FedCM
  finding. Plan it on `mint_test_assertion`, not on storageState.
- **Do not author stage 3 until `gts-zxes`'s Operator check passes.** ADR-0013: this is the AC-freeze
  gate. Authoring hardening tests against an unfrozen perceptual AC is the failure the phasing exists
  to prevent.
- `regression=pending` on `gts-zxes`; no `pytest -x` was run.
- The TEST deployment at `v0.2.3.94` was stamped from the **working tree**, uncommitted files
  included. So "deployed" here does not mean "committed". Anyone reasoning about what TEST is
  serving should read `src/Version.js` plus `git status`, not the git log.

**Deliberately not done**

- **Did not close the bead.** AC-1 has not been looked at by a human and AC-5 has not been run.
  Closing on the strength of a live probe and a static trace would be exactly the self-certification
  ADR-0013's review gate exists to prevent.
- **Did not write any test** — stage 3 is the twin `[TST]` half and must be authored by a session
  that has not read this implementation.
- **Did not commit, push or deploy.** 132 unrelated uncommitted files in the tree; rule 7 deferred to
  the human by instruction.
- **Did not add the AC-4 counter myself.** It is one small edit and the temptation to bundle it into
  "the resolver perf fix" was real — but it is outside this bead's AC, so rule 4 applies. It is
  `gts-m8ll`.
- **Did not chase FedCM further.** Two bounded attempts (headless, then headed under `xvfb`), then
  stopped: the human Operator check is five minutes and does not need it.

**The Operator check — for the human, executable now**

Open <https://nuuc-it.github.io/Static/pub/AS-sit/> and sign in as `sdonaldson@northlakeuu.org`
(9 visible teams) or `stuart.donaldson@gmail.com` (4). Confirm the footer badge says
`SIT · v0.2.3.94`; if it does not, you are not looking at this build and nothing below is valid.

1. The team dropdown carries an **All teams** entry above the individual teams. Pick it.
2. The title-line tag reads `MULTIPLE — permissions vary by team`, and **Expand all** /
   **Collapse all** appear.
3. Actions are grouped by team, each team group holding its own document groups.
4. **Every action appears exactly once.** A duplicate is the resolver de-dupe defect this bead
   exists to fix, and is the single most important thing to look for.
5. Sync/Edit controls are enabled per team, by *that* team's own tier — a team you only have VIEW
   on must show them disabled even while an EDIT team on the same page shows them enabled. A page
   where every group is gated identically means the per-team tier is not reaching the renderer.
6. Collapse all, expand all, then collapse one team and change the status filter — the collapse
   state must survive the re-render.
7. Edit or re-status one action in an EDIT team from this view. It must succeed. A rejection here
   is the ALL sentinel leaking onto a write path.

**What would make it wrong:** a duplicated action (4); uniform gating across teams of different
tiers (5); a write rejected from the All-teams view that succeeds from that team's own view (7).
Any of those means the AC is not met and the bead does not close.


### Stage 2 review gate — run 2026-09-02 by the operator — **INCONCLUSIVE, P0 found**

Not a pass and not a fail: the gate could not reach its question. Build confirmed correct
(`SIT · v0.2.3.94`). The operator tracked three docs from the folder-scan flow, saw no actions in
**All teams**, and found the Actions sheet held only rows for deleted test docs. Running
`Action Sync > Sync` deleted the three new DocData registrations outright.

**Cause — `gts-avvl` (P0), proven from Axiom op `1ed56163-83a7-4e7b-b686-919fb9274dea`:**

```
08:24:44.653  sync.all.start           docCount=23 integrityOrphaned=3
08:24:45.420  archive.docdata_evicted  fileId=13gubgybQCVIZ8HaZvHnzcdtcmNFZqGF1zZ46yBiumgw
08:24:45.422  archive.docdata_evicted  fileId=1QS2TjyU-XpT-VhVSupRwo0r4DLVpQcCon8KzokI24bQ
08:24:45.423  archive.docdata_evicted  fileId=1hADPOeHmw3iPoLGB1Vh-wVfNveHl89RVEGYUT3nk240
08:24:59.990  sync.all.start           docCount=20 integrityOrphaned=0
```

`ArchiveManager._evictStaleDocData` treats "no Actions rows" as proof of having aged out. A
scan-and-track registration has never had Actions rows, so it is deleted as an orphan. This
directly contradicts `gts-qkev`'s own comment at `SyncManager.js:500-505`, in the same uncommitted
change set — `gts-qkev` fixed the sweep to preserve these rows (`integrityOrphaned=3` proves the
walk saw them) and `ArchiveManager` deletes them one second later.

| Finding | Disposition |
|---|---|
| Never-actioned DocData registrations destroyed by any sync that also has a stale `Doc Not Found` row | **Bead `gts-avvl`** (P0, `stage:sync-docdata-walk`) |
| Full entry-point class for DocData eviction is unaudited (`syncAll`, menu Archive, 30-min trigger, Spreadsheet Sync All) | **Bead `gts-x1ka`** (P0, `stage:sync-coverage`, Path B retroactive audit), blocked by `gts-avvl` |
| The operator reached this through `Action Sync > Sync` — one of the two identically-labelled menu items `gts-w9kx` exists to disambiguate. Which one was used is not recoverable from the log | Recorded on `gts-w9kx` as live evidence the ambiguity has operational cost |
| Stage 2's AC-1 remains unobserved — the gate is inconclusive, not failed | AC of stage 2: re-run the gate after `gts-avvl` |

### Stage 2 review gate — re-run precondition cleared 2026-09-02 (`gts-avvl` closed)

`gts-avvl` is fixed and deployed to TEST as **v0.2.3.95**. The eviction predicate is back to
(`syncStatus === 'Doc Not Found'` **and** no Actions row) — absence of Actions rows is no longer an
eviction signal, per ADR-0031's 2026-09-01 amendment. A companion fix in
`WebApp.js::_handleMarkDocNotFound` closes the mirror gap that would otherwise have made a deleted
zero-Actions-row registration immortal under the restored predicate.

**The stage-2 gate can be re-run.** Three corrections to the script recorded in the stage-2 block
above, all discovered while fixing `gts-avvl`:

1. **The three destroyed registrations are gone and must be re-tracked.** They were deleted from
   DocData, not merely hidden. The gate starts from the folder-scan flow again, not from the
   assumption that last run's registrations survived.
2. **`Action Sync > Sync` must be run manually — there is no background sweep.** The operator
   disabled the 30-minute Background Sync trigger on 2026-09-02 so it could not fire mid-diagnosis
   (**`gts-bxa6`**, `human`, P1 — re-enable it or record that it stays off). Any step reading
   "wait for the next sweep" is not executable until that bead is discharged. Stage 6's operator
   check depends on that trigger outright.
3. **`sync.all.start`'s absence from Axiom is expected while the trigger is off**, not a symptom.
   Do not read it as a regression.

**What the gate is still for:** stage 2's AC-1 — every action appears exactly once in the
**All teams** view — which has never been observed. `gts-avvl` only removed the thing that stopped
it being observable; it is not evidence that AC-1 holds. The verdict is still open.

**Verification note.** The re-run is a *perceptual-oracle* look (ADR-0013) and stays one. The
`gts-avvl` fix carries `regression=pending` and one deliberately uncovered branch
(`_handleMarkDocNotFound`'s zero-Actions-row mirror, owned by `gts-x1ka`, now P0 and ready). A
green gate does not discharge that; `gts-x1ka` does.
