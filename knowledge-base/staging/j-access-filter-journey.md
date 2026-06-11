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
| Two-account auth (`.auth/user.json`, `.auth/user2.json`, `PROBE_AUTH_STATE`) | `tests/playwright/auth.setup.js --output`, `playwright.config.js` (**existing, from Probe work**) | Probe | P2 + P3 |

`access_filter.py` is created **once** by whichever binding bead runs first (Import,
`GTaskSheet-1dxz`); the second binding bead (Notify, `GTaskSheet-ay5w`) imports it
unchanged and supplies only its projection adapter. The no-shared-context rule (CLAUDE.md
§Testing) is preserved: both binding beads work from *this contract*, not from each other's
test code; the helper's behaviour is fully specified here in §4.

## 3. Two-account fixture matrix

Reuses the EPIC-B folder hierarchy verbatim — **no new folders, no new TeamData rows**. The
only new fixture state is (a) one Drive ACL grant and (b) one seeded source document per team
folder.

### Accounts

| Account | Identity | Auth artifact | Drive access granted | Role |
|---------|----------|---------------|----------------------|------|
| Primary | the existing test Google account | `.auth/user.json` | reader/owner on **all** team folders (`testTeamA`, `testTeamAChild`) | full-access baseline |
| Restricted | the second account used in prior Probe tests (`probe:user2`) | `.auth/user2.json` (`PROBE_AUTH_STATE`) | reader on **`testTeamAChild` only**; **no** access to `testTeamA` | least-privilege subset |

### Seeded source documents (idempotent — check-exists-or-create, no cleanup)

| Doc | Lives in folder | Team (via folder-walk) | Primary can read | Restricted can read |
|-----|-----------------|------------------------|------------------|---------------------|
| `docTeamA`     | `testTeamA`      | `TestTeamA`      | ✓ | ✗ |
| `docTeamAChild`| `testTeamAChild` | `TestTeamAChild` | ✓ | ✓ |

Each seeded doc must carry ≥1 team-scoped action with a known assignee (so Notify
aggregation is non-empty and parity is meaningful — guards against the vacuous-empty-set
pass, `docs/lessons-learned/2026-06-02-new-assertion-vacuously-passes-on-empty-result-set.md`).

### Expected visible sets (the journey's single source of truth)

| Account | `visibleDocSet` |
|---------|-----------------|
| Primary    | `{ docTeamA, docTeamAChild }` |
| Restricted | `{ docTeamAChild }` |

## 4. Journey phases (P1–P4)

Each phase is account-parameterised and adapter-parameterised. The `entry_point` tag is the
feature's access-filtered read (the binding bead names the concrete GAS function in its
pre-code contract); the call-site is that read itself, never the `assertTeamAccess`
mechanism in isolation (entry-point coverage invariant, CLAUDE.md).

| Phase | Account | Action | Durable assertion | Reuses |
|-------|---------|--------|-------------------|--------|
| **P1-PrimaryFullAccess** | Primary | run feature's filtered read | `assert_visible_set(adapter(result), { docTeamA, docTeamAChild })` | `visible_doc_set`, join |
| **P2-SecondaryRestrictedAccess** | Restricted | run feature's filtered read | `assert_visible_set(adapter(result), { docTeamAChild })` — `docTeamA` absent (never listed) | `visible_doc_set`, join, user2 auth |
| **P3-NoTeamFolderAccess** | Restricted | request a read scoped to `TestTeamA` (a team the account cannot read) | zero rows returned **and** `TeamAccessDenied` surfaced to caller; **no partial data** | `assert_team_access`/`_team_access_check`, `assertTeamAccess` |
| **P4-FeatureParity** | Primary, then Restricted | run **both** features' reads for the same account | `adapter_import(result) == adapter_notify(result) == visibleDocSet(account)` | both adapters; `GTaskSheet-7fng` |

Notes:
- **P3 is the phase that justifies the second account.** The existing single-account suite
  covers `assertTeamAccess` *allow* (S5) and folder *no-match → blank* (S2/S6); it cannot
  produce a genuine `getFolderById`-denied path. The restricted account, denied on
  `testTeamA`, produces it. P3 asserts the deny path drops rows *and* surfaces the error —
  it must never leak `docTeamA` to the restricted account.
- **P4 reuses, never rebuilds.** Parity (`GTaskSheet-7fng`) is `import_set == notify_set`,
  both compared to the same `visibleDocSet` already computed for P1/P2. No third expected
  set, no third fixture.
- **Filtering vs. erroring.** For an *unscoped list* (P1/P2), teams the account cannot read
  are silently excluded (their docs never appear) — no error, no leak. For an *explicitly
  requested inaccessible team* (P3), surface `TeamAccessDenied`. Both behaviours route
  through `assertTeamAccess`'s existing throw; neither adds new access logic.

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
