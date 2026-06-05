# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: sidebar_tracker_insert.test.js >> sidebar Insert tracker button inserts table and consistency passes
- Location: tests/playwright/sidebar_tracker_insert.test.js:103:1

# Error details

```
Error: expect(received).toBe(expected) // Object.is equality

Expected: 1
Received: 3
```

# Page snapshot

```yaml
- application [ref=e1]:
  - iframe [ref=e2]:
    
  - iframe [ref=e3]:
    
  - banner "Menu bar" [ref=e4]:
    - generic [ref=e7]:
      - link "Docs home" [ref=e9] [cursor=pointer]:
        - /url: https://docs.google.com/document/u/0/?pli=1&authuser=0&usp=docs_web
      - generic [ref=e16]:
        - generic "Untitled document" [ref=e18]:
          - generic [ref=e19]:
            - generic: Untitled document
            - textbox "Rename" [ref=e21]: Untitled document
          - generic [ref=e22]:
            - checkbox "Star" [ref=e24] [cursor=pointer]
            - button "Move" [ref=e28] [cursor=pointer]
            - 'button "Document status: Saved to Drive." [ref=e32]'
        - generic [ref=e39]:
          - button "Last edit was made seconds ago by Stuart Donaldson" [ref=e41] [cursor=pointer]
          - button "Show all comments 0 new comments" [ref=e45] [cursor=pointer]
          - button "Join a call here or present this tab to the call" [ref=e49] [cursor=pointer]
          - generic [ref=e54]:
            - button "Share. Northlake Unitarian Universalist Church. Anyone in this group with the link can open" [ref=e55] [cursor=pointer]: Share
            - button "Quick sharing actions" [ref=e57] [cursor=pointer]
          - 'button "Google Account: Stuart Donaldson (sdonaldson@northlakeuu.org)" [ref=e61] [cursor=pointer]':
            - img [ref=e62]
    - generic [ref=e63]:
      - menubar [ref=e65]:
        - menuitem "File" [ref=e66] [cursor=pointer]
        - menuitem "Edit" [ref=e67] [cursor=pointer]
        - menuitem "View" [ref=e68] [cursor=pointer]
        - menuitem "Insert" [ref=e69] [cursor=pointer]
        - menuitem "Format" [ref=e70] [cursor=pointer]
        - menuitem "Tools" [ref=e71] [cursor=pointer]
        - menuitem "Extensions" [ref=e72] [cursor=pointer]
        - menuitem "Help" [ref=e73] [cursor=pointer]
        - menuitem "Accessibility" [ref=e74] [cursor=pointer]
      - generic [ref=e75]:
        - generic [ref=e76]:
          - toolbar "Search the menus (Alt+/)" [ref=e77]:
            - combobox "Menus" [ref=e79]
          - toolbar "Main" [ref=e80]:
            - button "Undo (Ctrl+Z)" [ref=e81] [cursor=pointer]
            - button "Redo (Ctrl+Y)" [ref=e86] [cursor=pointer]
            - button "Print (Ctrl+P)" [ref=e91] [cursor=pointer]
            - button "Spelling and grammar check (Ctrl+Alt+X)" [ref=e96] [cursor=pointer]
            - button "Paint format" [ref=e101] [cursor=pointer]
            - combobox "Zoom" [ref=e106] [cursor=pointer]:
              - option "Zoom list. 100% selected." [selected] [ref=e109]:
                - textbox "Zoom" [ref=e110]: 100%
            - separator [disabled] [ref=e114]
            - listbox "Styles" [ref=e115] [cursor=pointer]:
              - option "Styles list. Normal text selected." [selected] [ref=e118]: Normal text
            - separator [disabled] [ref=e122]
            - listbox "Font" [ref=e123] [cursor=pointer]:
              - option "Arial" [selected] [ref=e126]
            - separator [disabled] [ref=e130]
            - button "Decrease font size (Ctrl+Shift+comma)" [ref=e131] [cursor=pointer]
            - combobox "Font size" [ref=e136] [cursor=pointer]:
              - option "Font size list. 11 selected." [selected] [ref=e139]:
                - textbox "Font size" [ref=e140]: "11"
            - button "Increase font size (Ctrl+Shift+period)" [ref=e141] [cursor=pointer]
            - separator [disabled] [ref=e146]
            - button "More" [disabled] [ref=e147] [cursor=pointer]
        - toolbar "Mode and view" [ref=e154]:
          - button "Editing mode" [ref=e155] [cursor=pointer]:
            - generic [ref=e158]: Editing
          - separator [disabled] [ref=e162]
          - button "Hide the menus (Ctrl+Shift+F)" [ref=e163] [cursor=pointer]
    - complementary "Side panel" [ref=e169]:
      - tablist [ref=e171]:
        - tab "Calendar"
        - tab "Keep"
        - tab "Tasks"
        - tab "Contacts"
        - tab "Maps"
        - separator [disabled] [ref=e177]
        - tab "Northlake Doc Tools" [selected]
        - tab "Get Add-ons"
  - generic [ref=e182]:
    - generic [ref=e187]:
      - generic [ref=e188]: "9"
      - generic [ref=e197]: "8"
      - generic [ref=e206]: "7"
      - generic [ref=e215]: "6"
      - generic [ref=e224]: "5"
      - generic [ref=e233]: "4"
      - generic [ref=e242]: "3"
      - generic [ref=e251]: "2"
      - generic [ref=e260]: "1"
      - generic [ref=e277]: "1"
      - generic [ref=e286]: "2"
      - generic [ref=e295]: "3"
      - generic [ref=e304]: "4"
      - generic [ref=e313]: "5"
      - generic [ref=e322]: "6"
      - generic [ref=e331]: "7"
      - generic [ref=e340]: "8"
    - generic [ref=e359]:
      - generic:
        - generic [ref=e362]:
          - button
        - generic:
          - list
    - generic [ref=e366]:
      - generic [ref=e367]: "11"
      - generic [ref=e376]: "10"
      - generic [ref=e385]: "9"
      - generic [ref=e394]: "8"
      - generic [ref=e403]: "7"
      - generic [ref=e412]: "6"
      - generic [ref=e421]: "5"
      - generic [ref=e430]: "4"
      - generic [ref=e439]: "3"
      - generic [ref=e448]: "2"
      - generic [ref=e457]: "1"
      - generic [ref=e474]: "1"
      - generic [ref=e483]: "2"
      - generic [ref=e492]: "3"
      - generic [ref=e501]: "4"
      - generic [ref=e510]: "5"
      - generic [ref=e519]: "6"
      - generic [ref=e528]: "7"
      - generic [ref=e537]: "8"
      - generic [ref=e546]: "9"
      - generic [ref=e555]: "10"
    - img [ref=e567]
    - generic "Document tabs" [ref=e570]:
      - button "Hide tabs & outlines" [ref=e572] [cursor=pointer]:
        - button "Back" [disabled] [ref=e573]:
          - button "Back" [disabled] [ref=e577]
      - generic [ref=e583]:
        - generic [ref=e585]:
          - heading "Document tabs" [ref=e586]
          - button "Add tab" [ref=e589]
        - tree "Document tabs" [ref=e593]:
          - generic [ref=e595] [cursor=pointer]:
            - treeitem "Tab 1" [selected] [ref=e596]:
              - generic [ref=e603]: Tab 1
              - button "Tab options" [ref=e606]
            - menuitem "Action Item Summary level 1" [ref=e611]:
              - generic "Action Item Summary level 1" [ref=e616]:
                - generic [ref=e617]: Action Item Summary
  - iframe [ref=e618]:
    - textbox "Document content" [ref=f1e1]:
      - group
  - generic [ref=e619]: Banner hidden
  - region
  - region [ref=e620]:
    - generic [ref=e621]: Screen reader support enabled.
    - generic [ref=e622]: 1 visible tab named Tab 1
    - generic [ref=e623]: On page 1.
  - complementary [ref=e624]:
    - generic "Add-on content shows." [ref=e628]:
      - iframe [active] [ref=e630]:
        - generic [ref=f10e1]:
          - generic [ref=f10e9]:
            - generic [ref=f10e10]:
              - generic [ref=f10e12]: Northlake Doc Tools
              - button "More actions" [ref=f10e17] [cursor=pointer]:
                - img [ref=f10e19]
              - button "Close" [ref=f10e23] [cursor=pointer]:
                - img [ref=f10e25]
            - generic "Add-on Card" [active] [ref=f10e28]:
              - generic [ref=f10e31]:
                - generic [ref=f10e33]:
                  - img "Action Sync logo" [ref=f10e34]
                  - generic [ref=f10e35]:
                    - generic [ref=f10e36]: Action Sync
                    - generic [ref=f10e37]: Untitled document
                - generic [ref=f10e42]:
                  - generic [ref=f10e43]: "Sync status: Tracked"
                  - generic [ref=f10e44]: 3 action(s) recorded for this document.
                - generic [ref=f10e45]:
                  - generic [ref=f10e47]:
                    - button "Sync now" [ref=f10e49] [cursor=pointer]:
                      - generic [ref=f10e50]: Sync now
                    - button "VerifySync" [ref=f10e52] [cursor=pointer]:
                      - generic [ref=f10e53]: VerifySync
                  - generic [ref=f10e56]: Tracker already present in this document.
                - generic [ref=f10e57]:
                  - generic [ref=f10e59]: Actions for this document (3)
                  - generic [ref=f10e63]:
                    - generic [ref=f10e64]: AI-1 • Stuart Donaldson • Done
                    - generic [ref=f10e65]: "Perm: Schedule the kickoff"
                  - generic [ref=f10e67]:
                    - generic [ref=f10e69]:
                      - button "Set Open" [ref=f10e70] [cursor=pointer]:
                        - img [ref=f10e72]
                      - tooltip [ref=f10e74]: Set Open
                    - generic [ref=f10e76]:
                      - button "Set In Progress" [ref=f10e77] [cursor=pointer]:
                        - img [ref=f10e79]
                      - tooltip [ref=f10e81]: Set In Progress
                    - generic [ref=f10e83]:
                      - button "Set In Review" [ref=f10e84] [cursor=pointer]:
                        - img [ref=f10e86]
                      - tooltip [ref=f10e88]: Set In Review
                    - generic [ref=f10e90]:
                      - button "Set Done" [ref=f10e91] [cursor=pointer]:
                        - img [ref=f10e93]
                      - tooltip [ref=f10e95]: Set Done
                    - generic [ref=f10e97]:
                      - button "Set Closed" [ref=f10e98] [cursor=pointer]:
                        - img [ref=f10e100]
                      - tooltip [ref=f10e102]: Set Closed
                    - generic [ref=f10e104]:
                      - button "Delete action" [ref=f10e105] [cursor=pointer]:
                        - img [ref=f10e107]
                      - tooltip [ref=f10e109]: Delete action
                  - generic [ref=f10e113]:
                    - generic [ref=f10e114]: AI-2 • jane.smith@example.com • Open
                    - generic [ref=f10e115]: "Perm: Draft the committee agenda"
                  - generic [ref=f10e117]:
                    - generic [ref=f10e119]:
                      - button "Set Open" [ref=f10e120] [cursor=pointer]:
                        - img [ref=f10e122]
                      - tooltip [ref=f10e124]: Set Open
                    - generic [ref=f10e126]:
                      - button "Set In Progress" [ref=f10e127] [cursor=pointer]:
                        - img [ref=f10e129]
                      - tooltip [ref=f10e131]: Set In Progress
                    - generic [ref=f10e133]:
                      - button "Set In Review" [ref=f10e134] [cursor=pointer]:
                        - img [ref=f10e136]
                      - tooltip [ref=f10e138]: Set In Review
                    - generic [ref=f10e140]:
                      - button "Set Done" [ref=f10e141] [cursor=pointer]:
                        - img [ref=f10e143]
                      - tooltip [ref=f10e145]: Set Done
                    - generic [ref=f10e147]:
                      - button "Set Closed" [ref=f10e148] [cursor=pointer]:
                        - img [ref=f10e150]
                      - tooltip [ref=f10e152]: Set Closed
                    - generic [ref=f10e154]:
                      - button "Delete action" [ref=f10e155] [cursor=pointer]:
                        - img [ref=f10e157]
                      - tooltip [ref=f10e159]: Delete action
                  - generic [ref=f10e163]:
                    - generic [ref=f10e164]: AI-3 • bob_jones@example.com • Open
                    - generic [ref=f10e165]: "Perm: Review the meeting minutes"
                  - generic [ref=f10e167]:
                    - generic [ref=f10e169]:
                      - button "Set Open" [ref=f10e170] [cursor=pointer]:
                        - img [ref=f10e172]
                      - tooltip [ref=f10e174]: Set Open
                    - generic [ref=f10e176]:
                      - button "Set In Progress" [ref=f10e177] [cursor=pointer]:
                        - img [ref=f10e179]
                      - tooltip [ref=f10e181]: Set In Progress
                    - generic [ref=f10e183]:
                      - button "Set In Review" [ref=f10e184] [cursor=pointer]:
                        - img [ref=f10e186]
                      - tooltip [ref=f10e188]: Set In Review
                    - generic [ref=f10e190]:
                      - button "Set Done" [ref=f10e191] [cursor=pointer]:
                        - img [ref=f10e193]
                      - tooltip [ref=f10e195]: Set Done
                    - generic [ref=f10e197]:
                      - button "Set Closed" [ref=f10e198] [cursor=pointer]:
                        - img [ref=f10e200]
                      - tooltip [ref=f10e202]: Set Closed
                    - generic [ref=f10e204]:
                      - button "Delete action" [ref=f10e205] [cursor=pointer]:
                        - img [ref=f10e207]
                      - tooltip [ref=f10e209]: Delete action
                - generic [ref=f10e213]: v0.2.0 (Rev. Jun 5, 2026 05:08) (TEST)
          - generic [ref=f10e214]: Tracker refreshed
          - generic [ref=f10e217]: Tracker refreshed
```

# Test source

```ts
  42  | 
  43  | async function invokeRoute(action, body, settings) {
  44  |   const response = await fetch(settings.webappTestUrl, {
  45  |     method: 'POST',
  46  |     headers: { 'Content-Type': 'application/json' },
  47  |     body: JSON.stringify({ action, testToken: settings.testToken, ...body }),
  48  |   });
  49  |   const raw = await response.text();
  50  |   if (raw === 'test-token-unauthorized' || raw === 'test-token-expired') {
  51  |     throw new Error(`Route ${action} rejected token: ${raw}`);
  52  |   }
  53  |   const result = JSON.parse(raw);
  54  |   if (result.error) throw new Error(`Route ${action} failed: ${result.error}`);
  55  |   return result;
  56  | }
  57  | 
  58  | async function findAddonFrame(page, timeoutMs = 30000) {
  59  |   const deadline = Date.now() + timeoutMs;
  60  |   let refreshAttempted = false;
  61  | 
  62  |   while (Date.now() < deadline) {
  63  |     for (const frame of page.frames()) {
  64  |       const syncNow = frame.getByRole('button', { name: /sync now/i });
  65  |       if (await syncNow.count().catch(() => 0)) {
  66  |         return frame;
  67  |       }
  68  |     }
  69  | 
  70  |     if (!refreshAttempted) {
  71  |       const refreshButton = page.getByRole('button', { name: /^Refresh$/i });
  72  |       if (await refreshButton.count().catch(() => 0)) {
  73  |         refreshAttempted = true;
  74  |         await refreshButton.click();
  75  |         await page.waitForTimeout(4000);
  76  |         continue;
  77  |       }
  78  |     }
  79  | 
  80  |     await page.waitForTimeout(500);
  81  |   }
  82  | 
  83  |   throw new Error('Timed out locating add-on frame with Sync now control');
  84  | }
  85  | 
  86  | async function createBlankDoc(page) {
  87  |   await page.goto('https://docs.google.com/document/create');
  88  |   await page.waitForURL(/\/document\/d\/[a-zA-Z0-9_-]+\/edit/, { timeout: 30000 });
  89  |   await page.waitForSelector('.docs-title-outer', { timeout: 30000 });
  90  | 
  91  |   const match = page.url().match(/\/document\/d\/([a-zA-Z0-9_-]+)\/edit/);
  92  |   if (!match) {
  93  |     throw new Error(`Could not determine doc ID from URL: ${page.url()}`);
  94  |   }
  95  | 
  96  |   return match[1];
  97  | }
  98  | 
  99  | // ─────────────────────────────────────────────────────────────────────────────
  100 | // AC1: sidebar "Insert tracker" button inserts table; full consistency passes
  101 | // ─────────────────────────────────────────────────────────────────────────────
  102 | 
  103 | test('sidebar Insert tracker button inserts table and consistency passes', async ({ page }) => {
  104 |   test.setTimeout(180000);
  105 |   const settings = loadSettings();
  106 |   const docId = await createBlankDoc(page);
  107 | 
  108 |   // uc_a_permutations seeds 3 floating actions but does NOT insert a tracker table.
  109 |   await invokeFixture('uc_a_permutations', docId, settings);
  110 | 
  111 |   await openDocSidebar(page, docId);
  112 |   let addonFrame = await findAddonFrame(page);
  113 | 
  114 |   // Sync floating actions so they become Anchored (required for Insert tracker to appear).
  115 |   clearLogs();
  116 |   await addonFrame.getByRole('button', { name: /sync now/i }).click();
  117 |   await waitForLogEntry(
  118 |     e => e.tag === 'sync.complete' && (!e.data?.docId || e.data.docId === docId),
  119 |     60000
  120 |   );
  121 | 
  122 |   addonFrame = await findAddonFrame(page);
  123 | 
  124 |   // Insert tracker button must be visible — asserts the user-facing entry point (AC1).
  125 |   await expect(addonFrame.getByRole('button', { name: /^Insert tracker$/i }))
  126 |     .toBeVisible({ timeout: 10000 });
  127 | 
  128 |   // Click the sidebar "Insert tracker" button — this is the entry point under test.
  129 |   await addonFrame.getByRole('button', { name: /^Insert tracker$/i }).click();
  130 | 
  131 |   // After insert the card refreshes; "tracker already present" confirms the table was written.
  132 |   addonFrame = await findAddonFrame(page);
  133 |   await expect(addonFrame.getByText(/tracker already present in this document/i))
  134 |     .toBeVisible({ timeout: 30000 });
  135 | 
  136 |   // Full consistency: ok=true, no issues.
  137 |   // uc_a_permutations seeds 1 chip-led floating action (AI: placeholder → AI-N: after sync).
  138 |   // The 2 email-only text items have no AI-N: prefix so are not detected by the scanner.
  139 |   const consistency = await invokeFixture('verify_consistency', docId, settings);
  140 |   expect(consistency.data.ok, consistency.data.issues?.join('\n')).toBe(true);
  141 |   expect(consistency.data.issues).toHaveLength(0);
> 142 |   expect(consistency.data.counts.floating).toBe(1);
      |                                            ^ Error: expect(received).toBe(expected) // Object.is equality
  143 |   expect(consistency.data.counts.tracker).toBe(1);
  144 |   expect(consistency.data.counts.matched).toBe(1);
  145 | 
  146 |   // Per-row field check — tracker.rows must have non-empty id, action, status.
  147 |   expect(consistency.data.tracker.rows).toHaveLength(1);
  148 |   for (const row of consistency.data.tracker.rows) {
  149 |     expect(row.id).toBeTruthy();
  150 |     expect(row.action).toBeTruthy();
  151 |     expect(row.status).toBeTruthy();
  152 |   }
  153 | });
  154 | 
  155 | // ─────────────────────────────────────────────────────────────────────────────
  156 | // AC2: after a status mutation and sync, tracker reflects only the changed row
  157 | // ─────────────────────────────────────────────────────────────────────────────
  158 | 
  159 | test('sync refreshes tracker after status mutation and only mutated row differs', async ({ page }) => {
  160 |   test.setTimeout(180000);
  161 |   const settings = loadSettings();
  162 |   const docId = await createBlankDoc(page);
  163 | 
  164 |   // uc_c_pending_sync_refresh seeds 3 anchored actions with a tracker already present.
  165 |   await invokeFixture('uc_c_pending_sync_refresh', docId, settings);
  166 | 
  167 |   await openDocSidebar(page, docId);
  168 |   let addonFrame = await findAddonFrame(page);
  169 | 
  170 |   // Sync the 3rd pending floating action; insertTrackerTable runs as part of
  171 |   // sync, so the tracker grows from 2 → 3 rows before we take the baseline.
  172 |   clearLogs();
  173 |   await addonFrame.getByRole('button', { name: /sync now/i }).click();
  174 |   await waitForLogEntry(
  175 |     e => e.tag === 'sync.complete' && (!e.data?.docId || e.data.docId === docId),
  176 |     60000
  177 |   );
  178 | 
  179 |   addonFrame = await findAddonFrame(page);
  180 |   await expect(addonFrame.getByText(/tracker already present in this document/i))
  181 |     .toBeVisible({ timeout: 10000 });
  182 | 
  183 |   // Baseline: capture tracker rows and confirm consistency before mutation.
  184 |   const baseline = await invokeFixture('verify_consistency', docId, settings);
  185 |   expect(baseline.data.ok, baseline.data.issues?.join('\n')).toBe(true);
  186 |   const baselineRows = baseline.data.tracker.rows;
  187 |   expect(baselineRows).toHaveLength(3);
  188 | 
  189 |   // Pick the first tracker row and mutate its status.
  190 |   const targetRow = baselineRows[0];
  191 |   const targetActionId = targetRow.id;           // e.g. "AI-5"
  192 |   const targetGlobalId = `${docId}/${targetActionId}`;
  193 |   const originalStatus = targetRow.status || 'Open';
  194 |   const newStatus = originalStatus === 'Open' ? 'In Progress' : 'Open';
  195 | 
  196 |   await invokeRoute('edit_action_row', {
  197 |     global_id: targetGlobalId,
  198 |     fields: { status: newStatus },
  199 |   }, settings);
  200 | 
  201 |   // Re-sync: propagates the sheet mutation to the doc and refreshes the tracker.
  202 |   clearLogs();
  203 |   addonFrame = await findAddonFrame(page);
  204 |   await addonFrame.getByRole('button', { name: /sync now/i }).click();
  205 |   await waitForLogEntry(
  206 |     e => e.tag === 'sync.complete' && (!e.data?.docId || e.data.docId === docId),
  207 |     60000
  208 |   );
  209 | 
  210 |   // Post-mutation consistency: ok=true, no issues, same row count.
  211 |   const postMutation = await invokeFixture('verify_consistency', docId, settings);
  212 |   expect(postMutation.data.ok, postMutation.data.issues?.join('\n')).toBe(true);
  213 |   expect(postMutation.data.issues).toHaveLength(0);
  214 |   expect(postMutation.data.counts.tracker).toBe(3);
  215 |   expect(postMutation.data.counts.matched).toBe(3);
  216 | 
  217 |   // Exactly one row has the new status; all other rows are field-identical to baseline.
  218 |   let mutatedCount = 0;
  219 |   for (const postRow of postMutation.data.tracker.rows) {
  220 |     if (String(postRow.id) === String(targetActionId)) {
  221 |       expect(postRow.status).toBe(newStatus);
  222 |       mutatedCount++;
  223 |     } else {
  224 |       const baseRow = baselineRows.find(b => b.id === postRow.id);
  225 |       if (baseRow) {
  226 |         expect(postRow.action).toBe(baseRow.action);
  227 |         expect(postRow.status).toBe(baseRow.status);
  228 |         expect(postRow.assignee).toBe(baseRow.assignee);
  229 |       }
  230 |     }
  231 |   }
  232 |   expect(mutatedCount).toBe(1);
  233 | });
  234 | 
  235 | // ─────────────────────────────────────────────────────────────────────────────
  236 | // AC3: direct tracker cell edit is overwritten on re-insert (view-only enforcement)
  237 | // ─────────────────────────────────────────────────────────────────────────────
  238 | 
  239 | test('direct tracker cell edit is overwritten on re-insert', async ({ page }) => {
  240 |   test.setTimeout(120000);
  241 |   const settings = loadSettings();
  242 |   const docId = await createBlankDoc(page);
```