# Staging — J-ACCESS-FILTER: shared access-filter journey (EPIC-D + EPIC-E)

> **Transient working contract** (framework staging). Authored by `GTaskSheet-z1fr`.
> Sole design input for the binding beads `GTaskSheet-1dxz` (Import), `GTaskSheet-ay5w`
> (Notify), and `GTaskSheet-7fng` (parity). Deleted when EPIC-D **and** EPIC-E close and
> the durable test-account note has graduated to `docs/OPERATIONS.md`.
> Review fidelity: **Slice** (ADR-0013) — see parent epic `GTaskSheet-uz7h`.
> Reuses (no new logic): `assertTeamAccess(teamId, ss)` (`src/SyncManager.js:872`) and the
> `ActionSheet.File Id` → `DocData.FileId` join (`_readDocDataRow`, `src/SyncManager.js:905`).

## 1. Purpose and the anti-duplication thesis

Import (EPIC-D) and Notify (EPIC-E) apply the **same** visibility rule: a feature may only
present source documents that are readable by the current user. The naïve path is two
parallel access-test suites — one per feature — that drift apart over time. This journey
exists to prevent that.

**Reduction.** Both features reduce to one observable:

```
visibleDocSet(account) = { fileId : fileId ∈ ActionSheet
                                    AND join(ActionSheet.File Id → DocData.FileId) yields teamId
                                    AND assertTeamAccess(teamId, ss) does NOT throw for `account` }
```

- Import's "list source documents" projects to a set of source `fileId`s.
- Notify's "aggregate assignees from source documents" projects to a set of source `fileId`s.
- Access correctness for **either** feature is `featureSourceSet(account) == visibleDocSet(account)`.

Therefore the journey defines **one** expected set per account and **one** assertion
(`assert_visible_set`). Each feature contributes only a thin *projection adapter* — its
entry point's result mapped to a set of source `fileId`s. The access rules (P1–P4) are
asserted once, in a shared helper module, and parameterised by adapter. No feature
re-implements an access check, a join, or an expected-set computation.

This is the whole maintenance payoff: adding a third consumer later (e.g. a Settings/export
tab) costs one projection adapter, not a third access suite.

## 2. Shared test-side home (single source of truth)

| Artifact | Location | Owner | Reused by |
|----------|----------|-------|-----------|
| `visible_doc_set(scn, account)` — computes the expected set from durable state | `tests/helpers/access_filter.py` (**new, single home**) | `z1fr` design → first binding bead creates it | Import + Notify + parity |
| `assert_visible_set(actual_set, expected_set, *, account, phase)` | `tests/helpers/access_filter.py` | same | Import + Notify + parity |
| `assert_team_access` fixture route + `_team_access_check` | `src/TestFixtures.js:1698`, `tests/test_team_scope.py:98` (**existing**) | EPIC-B | P3 deny-path |
| Folder hierarchy + TeamData rows (`testTeamA`/`testTeamAChild`/`testTeamADeep`/`testTeamNoTeam`) | `setup_team_scope_fixture` (**existing**) | EPIC-B | all phases |
| `testTeamB`/`TestTeamB` folder + TeamData row (**new**, independent sibling of `testTeamA`) | `setup_team_scope_fixture` (extend with one more idempotent row/folder, same pattern) | `z1fr` → `1dxz` | all phases, §3 |
| Two-account auth (`.auth/user.json`, `.auth/test.u2.json`, `PROBE_AUTH_STATE`) | `tests/playwright/auth.setup.js --account=`, `playwright.config.js` (**existing, from Probe work**) | Probe | P2 + P3 |
| Third account `TeamA-only` (**new**, `.auth/test.u3.json`) | `npm run auth:test.u3` (same mechanism as `test.u2`) | `z1fr` → `1dxz` | P1/P2 mirror, §3 |

`access_filter.py` is created **once** by whichever binding bead runs first (Import,
`GTaskSheet-1dxz`); the second binding bead (Notify, `GTaskSheet-ay5w`) imports it
unchanged and supplies only its projection adapter. The no-shared-context rule (CLAUDE.md
§Testing) is preserved: both binding beads work from *this contract*, not from each other's
test code; the helper's behaviour is fully specified here in §4.

## 3. Account + assignee fixture matrix (three accounts, three teams)

`testTeamAChild` is a **child folder under `testTeamA`** (EPIC-B's folder-walk hierarchy
case — `testTeamAMid`/`testTeamADeep` nest further under it). It stays exactly as-is for
that purpose. It is *not* reused as "the other team" here, since "a nested folder under A"
and "an independent sibling team" are different things and conflating them would muddy both
tests.

New fixture state: (a) **one new account** (`TeamA-only`), (b) **one new, independent team**
`TeamB` — new folder `testTeamB` (sibling to `testTeamA`, not nested under it) + new
TeamData row `TestTeamB` — via the same idempotent `setup_team_scope_fixture` pattern, and
(c) **one new seeded source document** `docTeamB` in it.

### Accounts

| Account | Identity | Auth artifact | Drive access granted | Role |
|---------|----------|---------------|----------------------|------|
| Primary | the existing test Google account | `.auth/user.json` | reader/owner on **all** team folders (`testTeamA`, `testTeamB`, `testTeamAChild`) | full-access baseline |
| **TeamA-only** *(NEW)* | a new test account | `.auth/test.u3.json` | reader on **`testTeamA` only**; no access to `testTeamB` or `testTeamAChild` | least-privilege subset |
| Restricted | the second account used in prior Probe tests (`probe:test.u2`) | `.auth/test.u2.json` (`PROBE_AUTH_STATE`) | reader on **`testTeamAChild` only**; no access to `testTeamA` or `testTeamB` | least-privilege subset |

### Seeded source documents (idempotent — check-exists-or-create, no cleanup)

| Doc | Lives in folder | Team (via folder-walk) | Primary can read | TeamA-only can read | Restricted can read |
|-----|-----------------|------------------------|------------------|----------------------|---------------------|
| `docTeamA`      | `testTeamA`      | `TestTeamA`      | ✓ | ✓ | ✗ |
| `docTeamB` *(NEW)* | `testTeamB` (new, independent — not nested under `testTeamA`) | `TestTeamB` (new) | ✓ | ✗ | ✗ |
| `docTeamAChild` | `testTeamAChild` | `TestTeamAChild` | ✓ | ✗ | ✓ |

`docTeamB` is visible only to Primary — it covers the case "a document exists, in a team
neither restricted account belongs to" (both `team-scope` exclusion for Import and
`read-access` exclusion for P1–P4 collapse to the same negative here, which is fine: it's
an additional negative, not a substitute for the `docTeamAChild` read-access-denied case
P3 specifically needs).

### Assignee identity = access account

Don't invent a separate set of "assignee" identities — **seed each document's action(s)
assigned to the account that matches its team**, using the plain-email assignee format
(no `insertPerson`/contacts dependency for new accounts):

- `docTeamA` action → assigned to **TeamA-only**'s email
- `docTeamAChild` action → assigned to **Restricted**'s email
- `docTeamB` action → assigned to **Primary**'s email (already the default `testAssigneeEmail`)

**Example.** Notify aggregates by assignee, gated by the same access filter as Import:
- Run as **Primary** (full access): sees `docTeamA`, `docTeamB`, `docTeamAChild` →
  aggregation shows TeamA-only (1), Restricted (1), and Primary's own (1).
- Run as **TeamA-only**: only `docTeamA` is visible → aggregation shows only TeamA-only's
  own 1 unresolved action; neither Restricted nor Primary's assignment appears.
- Run as **Restricted**: symmetric — only its own 1 unresolved action from `docTeamAChild`.

One fixture, one set of accounts, drives both the P1–P4 access assertions *and* gives
Notify's per-assignee aggregation real, differentiated data — and incidentally sets up
(without building) the future "Assignee reminder" funnel item (`GTaskSheet-tv54`), where
the assignee is a real account whose own Drive access matches the team their action lives
in.

### Expected visible sets (the journey's single source of truth)

| Account | `visibleDocSet` |
|---------|-----------------|
| Primary    | `{ docTeamA, docTeamB, docTeamAChild }` |
| TeamA-only | `{ docTeamA }` |
| Restricted | `{ docTeamAChild }` |

### Open item — AC-1's within-team grouping fixture (not covered here)

AC-1 (`GTaskSheet-eore`) needs **≥2 source documents in the *same* team as the target/
journey doc**, so its Import list renders ≥2 groups with AI-N sub-sorting inside at least
one group. None of `docTeamA`/`docTeamB`/`docTeamAChild` are in the same team as each other
by design (§3 above), so this matrix does not provide that fixture. That's a separate,
smaller addition (one more document in whichever team the target/journey doc belongs to)
— **flag to Stuart for confirmation before `eore` builds it**, rather than folding a second
purpose into this matrix again.

## 4. Journey phases (P1–P4)

Each phase is account-parameterised and adapter-parameterised. The `entry_point` tag is the
feature's access-filtered read (the binding bead names the concrete GAS function in its
pre-code contract); the call-site is that read itself, never the `assertTeamAccess`
mechanism in isolation (entry-point coverage invariant, CLAUDE.md).

| Phase | Account | Action | Durable assertion | Reuses |
|-------|---------|--------|-------------------|--------|
| **P1-PrimaryFullAccess** | Primary | run feature's filtered read | `assert_visible_set(adapter(result), { docTeamA, docTeamB, docTeamAChild })` | `visible_doc_set`, join |
| **P2-SecondaryRestrictedAccess** | Restricted | run feature's filtered read | `assert_visible_set(adapter(result), { docTeamAChild })` — `docTeamA`/`docTeamB` absent (never listed) | `visible_doc_set`, join, test.u2 auth |
| **P3-NoTeamFolderAccess** | Restricted | request a read scoped to `TestTeamA` (a team the account cannot read) | zero rows returned **and** `TeamAccessDenied` surfaced to caller; **no partial data** | `assert_team_access`/`_team_access_check`, `assertTeamAccess` |
| **P4-FeatureParity** | Primary, then Restricted | run **both** features' reads for the same account | `adapter_import(result) == adapter_notify(result) == visibleDocSet(account)` | both adapters; `GTaskSheet-7fng` |

Notes:
- **P3 is the phase that justifies the second account.** The existing single-account suite
  covers `assertTeamAccess` *allow* (S5) and folder *no-match → blank* (S2/S6); it cannot
  produce a genuine `getFolderById`-denied path. The restricted account, denied on
  `testTeamA`, produces it. P3 asserts the deny path drops rows *and* surfaces the error —
  it must never leak `docTeamA`/`docTeamB` to the restricted account.
- **P4 reuses, never rebuilds.** Parity (`GTaskSheet-7fng`) is `import_set == notify_set`,
  both compared to the same `visibleDocSet` already computed for P1/P2. No third expected
  set, no third fixture.
- **Filtering vs. erroring.** For an *unscoped list* (P1/P2), teams the account cannot read
  are silently excluded (their docs never appear) — no error, no leak. For an *explicitly
  requested inaccessible team* (P3), surface `TeamAccessDenied`. Both behaviours route
  through `assertTeamAccess`'s existing throw; neither adds new access logic.
- **TeamA-only (third account) is P1/P2's mirror, not a new phase.** `assert_visible_set`
  is already account-parameterised — running it with `account=TeamA-only` and expected set
  `{ docTeamA }` is the *same* P2-shaped assertion with roles reversed (the team that's
  denied flips from `TestTeamA` to `TestTeamB`+`TestTeamAChild`). It's a thin reuse of the
  same helper, not a fifth phase to design.

## 5. Entry-point call-site table (for the binding beads' pre-code contracts)

The binding beads register their concrete entry points in `scn/contract.ENTRY_POINT_REGISTRY`
and tag scenarios with them. This table fixes the *shape*; the GAS function names are filled
by each feature's own pre-code contract (no-shared-context).

| `entry_point` key (to register) | Call-site (the feature read) | Projection adapter → `set[fileId]` | Bound by |
|---------------------------------|------------------------------|------------------------------------|----------|
| `importList` (name TBD by EPIC-D contract) | Import tab's team-scoped list-source-documents read | rows → distinct source `File Id` | `GTaskSheet-1dxz` |
| `notifyAggregate` (name TBD by EPIC-E contract) | Notify tab's assignee-aggregation read | aggregated entries → distinct source `File Id` | `GTaskSheet-ay5w` |

Each registered entry point **must** call `assertTeamAccess(teamId, ss)` per candidate team
before emitting rows — this is the reuse contract, asserted behaviourally by P3, not a new
check authored in the test.

## 6. Packaging (per ROADMAP §J-ACCESS-FILTER)

| Package | Phases run |
|---------|-----------|
| Integration (per feature) | full `P1`–`P4` + that feature's functional assertions |
| Regression (fast guard) | `P2` + `P3` + parity smoke (`P4`) — guards access drift cheaply |
| Weekly / full | full `P1`–`P4` for **both** Import and Notify |

## 7. Open seams (ADR-0013 register — carried to EPIC-D/E hardening beads)

- **`assertTeamAccess` caller-supplied identity.** Future service-account impersonation will
  pass an explicit user identity rather than the active user. Express in the hardening
  `[TST]` as a one-liner + a test parameter `as_account=`; `visible_doc_set` already takes an
  `account` argument, so the seam is the *signature*, not the test shape. Do not build now.
  (Carried from EPIC-B `me6w` open seams via `GTaskSheet-5fha`.)
- **Settings tab (Phase 2) as a third consumer.** It would add one projection adapter to
  `access_filter.py`, reusing P1–P4 unchanged — recorded to confirm the shared-helper design
  scales without a third access suite. Do not build now.

## 8. Exit (when EPIC-D and EPIC-E both close)

1. Graduate the two-account test-asset note (§3 Accounts) to `docs/OPERATIONS.md`
   §Running Tests → Test Accounts (drafted now by this bead; see that section).
2. Confirm `tests/helpers/access_filter.py` is the only home of the access-filter assertion
   (document-structure-audit: no parallel per-feature copy).
3. Delete this staging file.
4. Add any funnel deltas to `knowledge-base/ROADMAP.md §Funnel`.
