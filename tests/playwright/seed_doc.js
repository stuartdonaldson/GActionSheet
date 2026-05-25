/**
 * Seed the test Google Doc with a chip-led list item.
 *
 * Usage:
 *   node seed_doc.js seed <docId> <assigneeEmail> <actionText>
 *
 * What it does:
 *   1. Opens the doc (assumes it has already been cleared by the GAS fixture)
 *   2. Applies bulleted-list format (Ctrl+Shift+8)
 *   3. Types @ + assigneeEmail to trigger the smart chip picker
 *   4. Waits for the picker dropdown and selects the first option
 *   5. Types the action text and waits for autosave
 *
 * Exit codes:
 *   0  — chip-led item was inserted
 *   1  — error (message to stderr)
 */

const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const settings = JSON.parse(
  fs.readFileSync(path.join(__dirname, '..', '..', 'local.settings.json'), 'utf8')
);
const storageState = path.join(__dirname, '..', '..', '.auth', 'user.json');

// ---------------------------------------------------------------------------

async function seedChipLedItem(page, docId, assigneeEmail, actionText) {
  const docUrl = `https://docs.google.com/document/d/${docId}/edit`;
  await page.goto(docUrl);
  await page.waitForSelector('.docs-title-outer', { timeout: 30000 });
  // Let the editor finish loading
  await page.waitForTimeout(2000);

  // Focus the document content area
  await page.keyboard.press('Control+Home');
  await page.waitForTimeout(300);

  // Apply bulleted-list format so python-docx sees w:numPr (required by floating_actions())
  await page.keyboard.press('Control+Shift+8');
  await page.waitForTimeout(300);

  // Type @ to open the smart chip picker, then the LOCAL part of the email only.
  // Typing the full email would include a second @ which triggers another picker.
  const localPart = assigneeEmail.split('@')[0];
  await page.keyboard.type('@');
  await page.waitForTimeout(400);
  await page.keyboard.type(localPart);
  await page.waitForTimeout(2500); // wait for picker to populate

  // Accept the first suggestion. Tab is the standard autocomplete-accept key in
  // Google Docs smart chip pickers. Try clicking [role="option"] first; fall back to Tab.
  const pickerOption = page.locator('[role="option"]').first();
  const pickerVisible = await pickerOption.isVisible().catch(() => false);
  if (pickerVisible) {
    await pickerOption.click();
  } else {
    await page.keyboard.press('Tab');
  }

  // Wait for the chip to be rendered before typing the action text
  await page.waitForTimeout(800);

  // Type action text after the chip
  await page.keyboard.type(' ' + actionText);

  // Wait for autosave (the "Saving..." / "All changes saved" indicator)
  await page.waitForTimeout(3000);
}

// ---------------------------------------------------------------------------

if (require.main === module) {
  const command = process.argv[2];
  if (command !== 'seed') {
    process.stderr.write(`Unknown command: ${command}\nUsage: node seed_doc.js seed <docId> <email> <actionText>\n`);
    process.exit(1);
  }

  const docId       = process.argv[3] || settings.testDocId;
  const email       = process.argv[4] || settings.testAssigneeEmail;
  const actionText  = process.argv[5] || 'Review the budget report';

  if (!email) {
    process.stderr.write('testAssigneeEmail not set in local.settings.json and no email argument provided\n');
    process.exit(1);
  }

  (async () => {
    const browser = await chromium.launch({ headless: false });
    const context = await browser.newContext({ storageState });
    const page    = await context.newPage();
    try {
      await seedChipLedItem(page, docId, email, actionText);
      process.stdout.write(JSON.stringify({ seeded: true, email, actionText }) + '\n');
      process.exit(0);
    } catch (e) {
      process.stderr.write(e.message + '\n');
      process.exit(1);
    } finally {
      await browser.close();
    }
  })();
}

module.exports = { seedChipLedItem };
