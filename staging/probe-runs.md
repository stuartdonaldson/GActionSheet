# Probe Run Registry

One row per probe session. Add a row **before** exercising any surfaces (Playwright prints
the runId at startup — copy it immediately). Include partial and failed runs.

Log files in the GasLogger Drive folder are **never deleted** — this registry is the index
that makes them findable later.

| runId | Date | Run | Deployment state | Installed add-on | Notes |
|-------|------|-----|-----------------|-----------------|-------|
| 5ae4eb6c-38ae-4440-bd25-e380df40f465 | 2026-06-02 | A | push-only (DEV @HEAD has PROBE, TEST does not) | direct /dev | 9/11 surfaces captured; sidebar+chipHover need reinstall/manual |
| 7fb4a13c-4a5a-450f-8d02-cd3e4a783aed | 2026-06-02 | B | after deploy:test (both DEV and TEST have PROBE) | direct /dev | 10/11 surfaces; doPost.test.unauthed crashed on 302 redirect |
| 9eac3dac-4c38-4be1-bf07-062d22a7e679 | 2026-06-02 | C | after deploy:test + Marketplace SDK @152 installed | Marketplace SDK draft | 11/11 pass; sidebar panel opened but no PROBE.sidebar logged (card cache?) |
