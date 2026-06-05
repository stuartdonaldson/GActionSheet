# Pipeline Report

_Generated: 2026-06-04T19:18:51 UTC_

---

## 1. Headline Join

| Field | Value |
|-------|-------|
| Run timestamp | 2026-06-04T14:30:45 UTC |
| Deployment matched | `@179` — TEST-WEB-APP v0.2.0 (Rev. Jun 4, 2026 07:28) (TEST) |
| DeploymentId | `AKfycbzVloY3corgO5F9AV7XvAbkL1oaTaehcE1kXwmFdJsXZPBBCm3xJ4ONJsZADHH9Hm4` |
| Deployed at | 2026-06-04T14:28:51 UTC (1 min before run) |
| Current deployment status | **RED** |
| Current version | `@179` (deployed 2026-06-04T14:28:51 UTC) |

---

## 2. Run Summary

### Pytest
| Metric | Value |
|--------|-------|
| Total | 177 |
| Passed | 175 |
| Failed | 1 |
| Errors | 0 |
| Skipped | 1 |
| Pass rate (of runnable) | 175 / 176 = **99.4%** |
| Wall time | 1146.2 s (19m 6s) |

### Playwright
_No `playwright.xml` found — reporting from failure artifact directories._

| Metric | Value |
|--------|-------|
| Failed (confirmed from artifacts) | 2 |
| Passed | unknown |

---

## 3. Per-Suite Table

### Pytest

| Suite | Tests | Pass | Fail | Err | Skip | Time (s) |
|-------|------:|-----:|-----:|----:|-----:|---------:|
| test_ai_n_token | 3 | **3** | 0 | 0 | 0 | 33.6 |
| test_archive | 1 | 0 | **1** | 0 | 0 | 23.6 |
| test_b7_write_routes | 3 | **3** | 0 | 0 | 0 | 184.4 |
| test_contract | 4 | **4** | 0 | 0 | 0 | 0.0 |
| test_infrastructure | 4 | **3** | 0 | 0 | 1 | 56.8 |
| test_journey | 1 | **1** | 0 | 0 | 0 | 240.0 |
| test_journey_acts_1_3 | 1 | **1** | 0 | 0 | 0 | 99.1 |
| test_poc_features | 1 | **1** | 0 | 0 | 0 | 63.5 |
| test_scn_ai | 25 | **25** | 0 | 0 | 0 | 0.0 |
| test_scn_engine | 38 | **38** | 0 | 0 | 0 | 0.0 |
| test_scn_session | 25 | **25** | 0 | 0 | 0 | 0.0 |
| test_scn_surfaces | 26 | **26** | 0 | 0 | 0 | 0.8 |
| test_scn_ui | 44 | **44** | 0 | 0 | 0 | 0.1 |
| test_sync_all | 1 | **1** | 0 | 0 | 0 | 433.1 |
| **Total** | **177** | **175** | **1** | **0** | **1** | **1146.2** |

**Skipped / xfail:**
- `test_infrastructure::test_initialize_triggers_is_idempotent` — initializeTriggers() requires GAS editor invocation — not automatable via sheet menu

### Playwright

| Suite | Tests | Pass | Fail | Err | Skip | Time (s) |
|-------|------:|-----:|-----:|----:|-----:|---------:|
| sidebar_action_list.test | 1 | 0 | **1** | 0 | 0 | — |
| smoke.test | 1 | 0 | **1** | 0 | 0 | — |

---

## 4. Failure Triage by Root-Cause Bucket

### 🟠 Env
_None._

### 🟠 Harness/Config
_None._

### 🟡 Perf/Timeout

| Test | Location | Error |
|------|----------|-------|
| `smoke.test.js >> syncDocument emits sync.complete log entry` | tests/playwright/smoke.test.js:106:1 | Error: Timed out after 30000ms waiting for log entry with tag='sync.complete' |

### 🔴 Product

| Test | Location | Error |
|------|----------|-------|
| `test_archive_lifecycle` | tests.test_archive | requests.exceptions.HTTPError: 429 Client Error: Too Many Requests for url: https://doc-14-7s-sheets.googleuserconten... |
| `sidebar_action_list.test.js >> homepage card renders action rows and refreshes after sync` | tests/playwright/sidebar_action_list.test.js:77:1 | Error: expect(locator).toBeVisible() failed |

---

## 5. Deployment Ledger

| # | Version | Target | Deployed (UTC) | Notes |
|---|---------|--------|---------------|-------|
| 1 | `@173` | test | 2026-06-04T05:52:30 UTC |  |
| 2 | `@174` | test | 2026-06-04T13:44:52 UTC |  |
| 3 | `@175` | test | 2026-06-04T14:13:16 UTC |  |
| 4 | `@176` | test | 2026-06-04T14:18:52 UTC |  |
| 5 | `@177` | test | 2026-06-04T14:22:51 UTC |  |
| 6 | `@178` | test | 2026-06-04T14:23:23 UTC |  |
| 7 | `@179` | test | 2026-06-04T14:28:51 UTC |  ← **current** |

**Cadence:** 7 deploy(s) over 8.6 h.



---

## 6. Health Flags & Recommended Next Action

| Flag | Severity | Detail |
|------|----------|--------|
| `test_archive_lifecycle` | 🔴 RED | Product failure — see triage above |
| `sidebar_action_list.test.js >> homepage card renders action rows and refreshes after sync` | 🔴 RED | Product failure — see triage above |
| `smoke.test.js >> syncDocument emits sync.complete log entry` | 🟡 YELLOW | Perf/Timeout — environment or latency, not confirmed product failure |
| No `playwright.xml` | 🟠 INFO | Playwright JUnit reporter not producing output — total count unknown |
