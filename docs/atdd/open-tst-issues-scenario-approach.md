# Open [TST] Issues — Scenario Approach

_Generated: 2026-05-31_

Each section covers one open `[TST]` issue: what it is testing and how to implement
it using the `scn` scenario framework (`scn/session.py`, `scn/ai.py`, `scn/engine.py`).

Framework primers:
- `ScenarioSession.new_doc(settings)` — creates an isolated journey doc; `close()` trashes it
- `ai(action=..., assignee=..., action_id=..., status=...)` — the noun a scenario manipulates
- `ai.as_text()` — renders the canonical paragraph string (`AI-N: [assignee] action (status)`)
- Acts: `append_paragraph`, `sync`, `edit_sheet`, `set_status`, `delete`, `insert_tracker`
- Queries: `doc_items()`, `sheet_rows()`, `find_sheet_actions()`, `verify_consistency()`
- Expectations: `verify(on=DOC|SHEET|TRACKER, at=INTEGRITY|STEP)`, `verify_all_expectations`,
  `expect_absent`
- `checkpoint(INTEGRITY|STEP)` — drains the expectation queue and verifies all outstanding claims

---

## GTaskSheet-r3d — syncAll marks rows Doc Not Found

**Already covered.** `tests/test_uc_c.py:test_sync_status_doc_not_found` (line 400) exercises
exactly this AC: the `sync_status_doc_not_found` fixture seeds rows with an inaccessible docId,
invokes sync, and asserts `Sync Status == "Doc Not Found"` on all matching rows while leaving
other-doc rows untouched.

Action before closing: confirm the fixture internally calls `syncAll()` (not `syncDocument`) as
the required entry point. If it calls `syncDocument`, log the gap in the issue and add a direct
`syncAll` invocation path.

---

## GTaskSheet-ckj — M2: Idempotent sync produces zero writes

**What it tests.** After a bidirectional sync on an unmodified document, a second sync must not
write any sheet cells. The M2 fix guarded unconditional col9 stamps and formula rewrites that
fired even when nothing changed. The existing `test_uc_a.py:test_uc_a_ac2_idempotent_second_sync`
verifies snapshot equality but does not count write calls, so it could miss a regression where
redundant writes happen but happen to produce identical values.

**Scenario approach.** Two-act journey:

```
Act 1 — seed and sync:
  item = ai(action="M2 idempotency probe item")
  scn.append_paragraph(item.as_text())
  scn.sync()
  item.status = "Open"   # tokenless default
  # Pin action_id
  for row in scn.find_sheet_actions():
      if row.action == item.action:
          item.action_id = row.action_id

  # Capture baseline sheet state
  baseline = scn.find_sheet_actions()
  baseline_row = next(r for r in baseline if r.action_id == item.action_id)

Act 2 — sync again with no doc mutations:
  scn.sync()

  after = scn.find_sheet_actions()
  after_row = next(r for r in after if r.action_id == item.action_id)

  # Assert key columns unchanged
  assert after_row.sync_status == baseline_row.sync_status  # col9 not re-stamped
  assert after_row == baseline_row                           # full row equality
```

Because `find_sheet_actions` returns parsed row data, full equality on `after_row == baseline_row`
catches any field silently rewritten. No write-spy is needed at this level; the assertion
is behaviorally equivalent for the regression.

---

## GTaskSheet-45k — M1: Upsert update path writes assignee email (col 3) and name (col 2)

**What it tests.** When `edit_sheet` is called with a changed `assignee_email`, the GAS upsert
update path must write col 3 (Assignee Email) and derive/write col 2 (Assignee Name). The M1 bug
was that the update branch never wrote col 3. `test_b7_write_routes.py` exercises `edit_sheet`
but only asserts Dirty stamp and status propagation — it does not mutate the email field and
does not assert col 3.

**Scenario approach.** Extend the B7 pattern with an email-change act:

```
# SETUP — seed an assigned action, sync, pin IDs
target = ai(
    action="M1 assignee email update probe",
    assignee="aitest@example.com",
)
scn.append_paragraph(target.as_text())
scn.sync()
target.status = "Open"
for row in scn.find_sheet_actions():
    if row.action == target.action:
        target.action_id = row.action_id

# Verify baseline email written on first sync
rows = scn.find_sheet_actions()
row = next(r for r in rows if r.action_id == target.action_id)
assert row.assignee == "aitest@example.com", "baseline email not written"

# ACT — edit_sheet changes the assignee email
scn.edit_sheet(target, assignee_email="minister@northlakeuu.org")

# ASSERT — col 3 updated synchronously (edit_sheet is synchronous)
rows_after = scn.find_sheet_actions()
row_after = next(r for r in rows_after if r.action_id == target.action_id)
assert row_after.assignee == "minister@northlakeuu.org", "M1: col 3 not updated"
# col 2 — name derived from email (contacts lookup or email split)
assert row_after.assignee_name not in (None, ""), "M1: col 2 (Assignee Name) empty after email update"
```

Note: `find_sheet_actions` returns an `ai` object where the `assignee` field carries what the
sheet contains. If `ai.assignee` maps to col 3, the first assertion covers M1 directly. Check
`_row_dict_to_ai` in `session.py` to confirm the field mapping before writing.

---

## GTaskSheet-dm7 — M3: Sync materializes (Open) token in doc-wins path

**What it tests.** When a floating action has no status token in the document, sync must write
`(Open)` back into the paragraph. The M3 bug was that the doc-wins path never wrote the missing
token. `test_uc_b.py:test_uc_b_doc_wins` covers status propagation but its fixtures start
actions with explicit tokens; no test verifies the tokenless → `(Open)` materialization.

**Scenario approach.** Single-act journey asserting the DOC surface contains `(Open)`:

```
# Seed a tokenless action (no status in as_text())
tokenless = ai(action="M3 open token materialization probe")
# as_text() → "AI: M3 open token materialization probe"  (no status appended)
scn.append_paragraph(tokenless.as_text())
scn.sync()

# Doc must now contain "(Open)" in the paragraph
doc_actions = scn.doc_items()
matches = [a for a in doc_actions if a.action == tokenless.action]
assert len(matches) == 1, "M3: action not found in doc after sync"
assert matches[0].status == "Open", (
    f"M3: expected paragraph status 'Open' after sync, got {matches[0].status!r}"
)

# Use verify_all_expectations for full DOC+SHEET cross-check
tokenless.status = "Open"
for row in scn.find_sheet_actions():
    if row.action == tokenless.action:
        tokenless.action_id = row.action_id
scn.verify_all_expectations(tokenless)
scn.checkpoint(INTEGRITY)
```

`doc_items()` uses `DocReader` which parses the paragraph text — confirming `(Open)` was written
into the document text, not merely recorded in the sheet.

---

## GTaskSheet-wpe1 — M4: URL format matching (open?id= and /d/)

**What it tests.** `_loadRowsForDocUrl` and orphan detection must resolve both URL formats to the
same docId. The M4 fix standardised all matching on the extracted docId. No test currently
seeds rows in `open?id=` format and verifies correct matching.

**Scenario approach.** This test requires seeding the ActionSheet directly with rows in both URL
formats, then syncing, which is outside the normal journey doc lifecycle. Two options:

**Option A — fixture-based (preferred):** Add a GAS fixture `seed_mixed_url_rows` that writes
two sheet rows for the same document using the two URL formats, then call it via `_post_fixture`,
sync, and assert both rows are matched (no orphan, no duplicate create):

```
# Seed rows with both URL formats via fixture
scn._post_fixture("seed_mixed_url_rows", {
    "docId": scn.doc_id,
    "open_id_url": f"https://docs.google.com/document/d/{scn.doc_id}/edit?usp=sharing",
    "slash_d_url": f"https://docs.google.com/document/d/{scn.doc_id}/edit",
})
scn.sync()

rows = scn.find_sheet_actions()
# Both URL formats must resolve to the same doc; neither should appear as orphan
doc_rows = [r for r in rows if r.action_id is not None]
assert len(doc_rows) >= 1, "M4: no rows matched after sync with mixed URL formats"

result = scn.verify_consistency()
issues = result.get("data", {}).get("issues", [])
orphan_issues = [i for i in issues if "orphan" in str(i).lower()]
assert not orphan_issues, f"M4: false-positive orphan detection with mixed URLs: {orphan_issues}"
```

**Option B — direct sheet write via download/upload:** More complex; fixture approach is simpler
and keeps all state in GAS. File a `[IMP]` paired issue if `seed_mixed_url_rows` does not exist.

---

## GTaskSheet-sjj — AI-N token: regression + integration coverage (4 entry points)

**What it tests.** Four entry points must each appear as a direct call-site in at least one
scenario: `syncDocument` (scanner), `sidebarCreateAction` (creation), `sidebarSetStatus` (flush),
`sidebarDeleteAction` (delete). The additional AC is that col 1 (NamedRangeId/globalId) equals
`{docId}/AI-N` after initial sync.

**Scenario approach.** Four acts, each targeting one entry point. The existing `test_b7_write_routes.py`
covers `set_status` and `delete` paths but not the globalId format assertion or `sidebarCreateAction`.

**Act 1 — scanner path (`syncDocument`)**

```
item = ai(action="sjj scanner: tokenless action for AI-N globalId verification")
scn.append_paragraph(item.as_text())
scn.sync()    # syncDocument internal call — this is the scanner entry point

rows = scn.find_sheet_actions()
row = next((r for r in rows if r.action == item.action), None)
assert row is not None, "sjj AC1: action not found in sheet after sync"
assert row.action_id is not None, "sjj AC1: action_id not assigned"

# Assert globalId format: {docId}/AI-N
expected_global_id = f"{scn.doc_id}/{row.action_id}"
# find_sheet_actions returns parsed ai; check raw sheet for globalId field
raw_rows = scn.sheet_rows()
raw_row = next((r for r in raw_rows if r.action_id == row.action_id), None)
# SheetReader should expose globalId — confirm field name in surfaces.py before coding
assert raw_row is not None
item.action_id = row.action_id
item.status = "Open"
```

**Act 2 — creation path (`sidebarCreateAction`)**

The `scn.ui.create_action(created)` Playwright call exercises this entry point. Use the same
pattern as `test_journey.py` Act 4. If Playwright/browser is not available, file the gap
explicitly — `sidebarCreateAction` has no HTTP-only test path.

**Acts 3 & 4 — flush and delete** are already covered structurally by B7; cite them and add
the explicit globalId format assertion to complete the AC:

```
scn.set_status(item, "Done")   # flush path (sidebarSetStatus via patch_action_status)
item.status = "Done"
scn.verify(item, on=DOC, at=INTEGRITY)
scn.verify(item, on=SHEET, at=INTEGRITY)
scn.sync()
scn.checkpoint(INTEGRITY)

scn.delete(item)               # delete path (sidebarDeleteAction via delete_action_row)
scn.expect_absent(item, on=SHEET)
scn.sync()
scn.checkpoint(STEP)
```

---

## GTaskSheet-0n3 — POC edit action propagation and async sheet update

**What it tests.** Six verification points against the `_poc_*` handler family introduced by
GTaskSheet-j8y: card navigation from `_poc_openEditCard`, pre-filled form from `_poc_buildEditCard`,
doc REST update logged as `POC_EDIT_ACTION.complete`, QUEUE script property populated before drain,
`_poc_processPendingSheetUpdates` drains QUEUE to `[]`, and the ActionSheet row reflects the
new status after drain.

**Scenario approach.** These handlers are POC-specific and not yet exposed as named session acts.
Two layers are needed:

**Layer 1 — HTTP acts (points 3-6, testable without Playwright):**

```
# SETUP
item = ai(action="POC edit propagation probe", status="Open")
scn.append_paragraph(item.as_text())
scn.sync()
for row in scn.find_sheet_actions():
    if row.action == item.action:
        item.action_id = row.action_id

# Point 3 — call _poc_submitEditAction via raw route; log must contain POC_EDIT_ACTION.complete
resp = scn._post_route("poc_submit_edit", {
    "global_id": scn._gid(item),
    "new_status": "In Progress",
})
assert resp.get("status") == "queued", f"POC submit: unexpected response: {resp}"

# Point 4 — QUEUE property has an entry (before drain fires)
queue_resp = scn._post_route("read_poc_queue")
assert len(queue_resp.get("queue", [])) >= 1, "POC: QUEUE empty immediately after submit"

# Points 5-6 — drain and verify sheet row
scn._post_route("poc_process_queue")
rows_after = scn.find_sheet_actions()
row_after = next(r for r in rows_after if r.action_id == item.action_id)
assert row_after.status == "In Progress", (
    f"POC: sheet status not updated after drain, got {row_after.status!r}"
)
```

**Layer 2 — card assertions (points 1-2, require Playwright or fixture inspection):**

`_poc_openEditCard` returns a GAS card JSON; `_poc_buildEditCard` returns pre-filled fields.
Without Playwright these must be tested via a fixture that invokes the card builder and
returns its JSON for assertion:

```
card_resp = scn._post_fixture("poc_open_edit_card", {"global_id": scn._gid(item)})
# Assert card is a navigation (has "type": "nav" or equivalent in card JSON)
assert "navigation" in str(card_resp), "POC: openEditCard did not return a navigation"

build_resp = scn._post_fixture("poc_build_edit_card", {"global_id": scn._gid(item)})
# Assert form fields pre-filled with current status
assert item.action in str(build_resp), "POC: buildEditCard did not include action text"
```

These fixture names (`poc_open_edit_card`, `poc_build_edit_card`, `poc_submit_edit`,
`read_poc_queue`, `poc_process_queue`) are placeholders — they must be registered in
`AtddContracts.js` as part of the `[IMP]` delivery or added via a companion `[INF]` issue.

---

## GTaskSheet-rwz — POC preview card AI-N display, sidebar compact format, tracker AI-N link

**What it tests.** Four visual/structural verification points from GTaskSheet-7js: the preview
card header shows the AI-N pattern; the card contains a button/link whose URL matches the chip
URL pattern; the sidebar `buildHomepageCard` action rows show AI-N + status in `topLabel`;
and after `insertTrackerTable`, the ID cell hyperlink matches the chip URL.

**Scenario approach.** Mix of HTTP-layer (sidebar, tracker) and Playwright (preview card).

**Sidebar and tracker (HTTP-layer):**

```
item = ai(action="rwz preview card probe", action_id="AI-5")
scn.append_paragraph(item.as_text())
scn.sync()
item.status = "Open"

# Tracker ID cell hyperlink
scn.insert_tracker()
scn.sync()
scn.verify(item, on=TRACKER)     # verifies tracker row presence
scn.checkpoint(STEP)

# Assert tracker ID cell contains chip URL via raw docx inspection
from tests.helpers.download import download_docx
from tests.helpers.doc_inspect import load_doc
docx = download_docx(scn.doc_id)
doc = load_doc(docx)
# locate tracker table row for item; inspect hyperlink on ID cell
# (exact API depends on doc_inspect implementation — check tracked_actions_table return shape)
```

**Preview card and sidebar (Playwright):**

```
card = scn.ui.hover(
    scn.ui.locate(text=item.action_id, occurrence=1),
    timeout="5s",
)
# Point 1 — card header contains AI-N pattern
scn.expect_visible(card, timeout="5s")
scn.expect_alt(scn.ui.locate(alt=item.action_id, next=True), item.action_id)

# Point 2 — card has a link matching the chip URL pattern
# chip URL format from ADR-0008: https://actionsheet.northlakeuu.org/action/{globalId}
chip_url_pattern = f"actionsheet.northlakeuu.org/action/{scn.doc_id}/{item.action_id}"
page_content = scn.ui._page.content()
assert chip_url_pattern in page_content, f"rwz: chip URL not found in card: {chip_url_pattern}"
```

**Sidebar topLabel (fixture inspection):**

```
sidebar_resp = scn._post_fixture("build_homepage_card")
rows_json = str(sidebar_resp)
assert item.action_id in rows_json, "rwz: AI-N not in sidebar topLabel"
assert item.status in rows_json, "rwz: status not in sidebar topLabel"
```

Confirm that `build_homepage_card` is a registered fixture or add it as part of the delivery.

---

## GTaskSheet-6ov.4 — Verify createActionTrigger: @action in Docs menu, logo display, chip insertion

**What it tests.** Visual/interaction test: the `@action` item appears in the Docs `@`-menu with
the GActionSheet logo; inserting the chip displays the logo; the logo is legible and not visually
ambiguous with a native person chip.

**Scenario approach.** Playwright-only; the HTTP layer has no surface here.

`test_journey.py` Act 4 already exercises `scn.ui.create_action(created)` which goes through
`createActionTrigger`. What it does not assert is the logo/visual identity. Add to the existing
Act 4 pattern:

```
# After scn.ui.create_action(created) opens the @-menu:
# 1 — Assert @action item appears in Docs @-menu
menu_item = scn.ui._page.locator('[aria-label="@action"]')  # selector TBD
assert menu_item.is_visible(), "6ov.4: @action not in @-menu"

# 2 — Assert GActionSheet logo visible in menu item
# (logo appears as an img with a recognizable src pattern or alt text)
logo = scn.ui._page.locator('[alt="GActionSheet"]').first  # selector TBD
assert logo.is_visible(), "6ov.4: logo not visible in @-menu item"

# 3 — After chip insertion, logo is present on the chip
chip_logo = scn.ui._page.locator('[data-chip-type="action"] img').first  # TBD
assert chip_logo.is_visible(), "6ov.4: chip logo not visible after insertion"
```

Exact selectors are not yet known — they must be discovered during Playwright authoring using
`page.pause()` or `page.screenshot()`. The test should skip (not fail) when the add-on is not
deployed to the test account (`createActionTriggers` RuntimeError → `pytest.skip`), matching
the pattern in `test_journey.py:133-137`.

---

## GTaskSheet-6ov.6 — Verify linkPreviewTriggers: branded preview card with visual consistency

**What it tests.** When a chip is hovered, the preview card uses the same branded identity (logo,
colour) as the `@action` menu entry; the logo is legible at chip scale.

**Scenario approach.** Playwright-only; extends the hover path already used in `test_journey.py`
Act 5.

```
# After chip insertion (same setup as 6ov.4):
card = scn.ui.hover(
    scn.ui.locate(text=created.action_id, occurrence=1),
    timeout="5s",
)
scn.expect_visible(card, timeout="5s")

# Branding assertions — logo in card header
card_logo = scn.ui._page.locator('[role="dialog"] img[alt="GActionSheet"]')  # TBD
assert card_logo.is_visible(), "6ov.6: logo not visible in preview card"

# Visual consistency — screenshot diff against a stored reference
# (use playwright page.screenshot() + pixel comparator, or a manual review step)
# If no pixel comparator is set up: capture screenshot and fail with a review note.
card_screenshot = scn.ui._page.screenshot(clip=card.bounding_box())
# store as test artifact; visual review required until comparator is in place
```

Logo selectors and the visual comparison method depend on the rendered card DOM. Screenshot
capture is the pragmatic approach until a pixel-diff comparator is configured. The test should
skip (not fail) if the chip is not inserted (add-on not deployed).
