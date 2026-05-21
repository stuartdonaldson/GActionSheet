const { chromium } = require('@playwright/test');
const fs = require('fs');

(async () => {
  const settings = JSON.parse(fs.readFileSync('/mnt/c/dev/GActionSheet/local.settings.json', 'utf8'));
  const editorUrl = `https://script.google.com/d/${settings.scriptId}/edit`;

  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ storageState: '/mnt/c/dev/GActionSheet/.auth/user.json' });
  const page = await context.newPage();

  await page.goto(editorUrl);
  await page.waitForTimeout(5000);

  // Dump everything in the toolbar area
  const elements = await page.evaluate(() => {
    const results = [];
    document.querySelectorAll('*').forEach(el => {
      const text = (el.getAttribute('aria-label') || el.getAttribute('title') || el.textContent || '').trim().slice(0, 80);
      if (text.toLowerCase().includes('function') || text === 'No functions') {
        results.push({
          tag: el.tagName,
          role: el.getAttribute('role'),
          ariaLabel: el.getAttribute('aria-label'),
          title: el.getAttribute('title'),
          text: el.textContent?.trim().slice(0, 80),
          class: el.className?.slice(0, 60),
        });
      }
    });
    return results.slice(0, 20);
  });

  console.log(JSON.stringify(elements, null, 2));
  await browser.close();
})();
