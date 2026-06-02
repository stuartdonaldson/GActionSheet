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
| ee395a03-a194-492c-82dd-3bbd33b0c223 | 2026-06-02 | D | same code @152; switched back from Marketplace to direct /dev install | direct /dev | 11/11 pass; sidebar panel icon gone again; doGet.dev ran twice (auth redirect); identity unchanged |
| 567467e2-b092-4b1f-abee-846635708357 | 2026-06-02 | E1 | user2 (sanctuary@northlakeuu.org); playwright.config.js storageState bug — page fixture used user1 auth | direct /dev; user2 no add-on | STALE: page tests ran as sdonaldson; doPost.authed correctly shows sanctuary au |
| 441f85ad-90c7-4c79-bb3f-e9e9575338b8 | 2026-06-02 | E2 | user2 (sanctuary@northlakeuu.org); clean run — all fixtures use user2 auth | direct /dev; user2 no add-on | 12/12; PROBE.menu missing (OAuth auth dialog appeared mid-run; user approved but 60s poll expired); menu.identity clean |
| 77a4b35d-ff24-457b-a07e-1e60c22996e1 | 2026-06-02 | E3 | user2, post-authorization clean run | direct /dev; user2 no add-on | 12/12 clean; menu eu=au=sanctuary confirmed; WebApp eu=deployer au=sanctuary confirmed |
