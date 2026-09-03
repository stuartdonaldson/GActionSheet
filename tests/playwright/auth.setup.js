/**
 * Capture a Google auth session as a shared, cross-project Playwright
 * storageState, identified by account slug (not project role):
 *
 *   node tests/playwright/auth.setup.js                        # slug auto-derived from detected email
 *   node tests/playwright/auth.setup.js --account=sdonaldson   # explicit slug (overrides auto-derive)
 *   node tests/playwright/auth.setup.js --output=.auth/custom.json   # one-off, bypasses shared dir/registry
 *
 * If the email can't be auto-detected, this prompts for a slug on the spot
 * rather than discarding the captured session — the interactive Google login
 * is the expensive part; naming a file afterward is not, and forcing a
 * re-login just because scraping failed would waste it. If stdin isn't
 * interactive (or the prompt is left blank), the session is staged instead
 * of lost, with the command to finish naming it printed:
 *   node tests/playwright/auth.setup.js --apply=<staged-path> --account=<slug>
 *
 * Writes $PLAYWRIGHT_AUTH_DIR/<slug>.json (.envrc; default ~/.playwright)
 * and records the logged-in email + capture timestamp in
 * $PLAYWRIGHT_AUTH_DIR/accounts.json — the identity registry other tools
 * read to show which real Google account a given file belongs to.
 *
 * If --account is given and the detected email doesn't match what's already
 * on file for that slug, this warns rather than silently overwriting —
 * catches "signed into the wrong account" before it produces a confusing
 * test failure days later.
 *
 * This project assigns accounts to its own roles via local.settings.json's
 * "playwrightAccounts" map (see .auth/README.md and docs/security-architecture.md
 * §5 for the role taxonomy — primary / test.u1 / test.u2 / test.u3 / nuuts.service):
 *   { "primary": "sdonaldson.json", "test.u2": "sanctuary.json", ... }
 * auth.setup.js has no notion of roles at all — that mapping lives only in
 * local.settings.json, hand-edited by the developer after capture.
 *
 * Re-run only when a session expires.
 */
const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const readline = require('readline');
const { authDir, loadRegistry, saveRegistry } = require('../../scripts/playwright-auth');

function slugFromEmail(email) {
  return email.split('@')[0].replace(/[^a-zA-Z0-9._-]/g, '-');
}

function ask(rl, question) {
  return new Promise((resolve) => rl.question(question, resolve));
}

function updateRegistry(account, email) {
  const registry = loadRegistry();
  const existing = registry[account];
  if (existing && existing.email && email && existing.email !== email) {
    console.warn(
      `⚠️  "${account}" was previously registered as ${existing.email}, but this login detected `
      + `${email}. Wrong account? File written anyway — check before relying on it.`
    );
  }
  registry[account] = {
    email: email || (existing && existing.email) || null,
    capturedAt: new Date().toISOString(),
    capturedBy: path.basename(process.cwd()),
  };
  saveRegistry(registry);
  console.log(registry[account].email
    ? `Registry updated: ${account} → ${registry[account].email}`
    : `Registry updated: ${account} (email unknown — edit ${path.join(authDir(), 'accounts.json')} to fill it in)`);
}

(async () => {
  const outputArg = process.argv.find(a => a.startsWith('--output='));
  const accountArg = process.argv.find(a => a.startsWith('--account='));
  const applyArg = process.argv.find(a => a.startsWith('--apply='));
  const explicitAccount = accountArg ? accountArg.slice('--account='.length) : null;

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });

  // --apply: finish naming a session that was staged because detection
  // failed and nobody was there (or willing) to type a slug at the time.
  if (applyArg) {
    if (!explicitAccount) {
      console.error('--apply requires --account=<slug> to name the staged session.');
      rl.close();
      process.exit(1);
    }
    const stagedPath = path.resolve(process.cwd(), applyArg.slice('--apply='.length));
    const state = JSON.parse(fs.readFileSync(stagedPath, 'utf8'));
    const authPath = path.join(authDir(), `${explicitAccount}.json`);
    fs.mkdirSync(path.dirname(authPath), { recursive: true });
    fs.writeFileSync(authPath, JSON.stringify(state, null, 2));
    fs.unlinkSync(stagedPath);
    console.log(`Applied staged session to ${authPath}`);
    updateRegistry(explicitAccount, null);
    rl.close();
    process.exit(0);
  }

  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  await page.goto('https://accounts.google.com');
  await ask(rl, 'Log in to Google in the browser window, then press Enter here...\n');

  // Capture to memory first — the destination filename may depend on the
  // detected email, so it isn't known yet.
  const state = await context.storageState();

  let email = null;
  try {
    await page.goto('https://myaccount.google.com/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    const bodyText = await page.evaluate(() => document.body.innerText);
    const match = bodyText.match(/[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}/);
    email = match ? match[0] : null;
  } catch (err) {
    console.warn(`⚠️  Could not auto-detect account email: ${err.message}`);
  }

  let account = explicitAccount || (email ? slugFromEmail(email) : null);

  if (!outputArg && !account) {
    console.log('Could not auto-detect the account email.');
    if (process.stdin.isTTY) {
      const typed = (await ask(rl, 'Enter an account slug to save this session as (blank to decide later): ')).trim();
      account = typed || null;
    }
    if (!account) {
      const stagingPath = path.join(authDir(), `.unnamed-${Date.now()}.json`);
      fs.mkdirSync(path.dirname(stagingPath), { recursive: true });
      fs.writeFileSync(stagingPath, JSON.stringify(state, null, 2));
      console.log('Session captured but not named — no need to log in again. Finish with:');
      console.log(`  node tests/playwright/auth.setup.js --apply=${stagingPath} --account=<slug>`);
      rl.close();
      await browser.close();
      process.exit(0);
    }
  }

  const authPath = outputArg
    ? path.resolve(process.cwd(), outputArg.slice('--output='.length))
    : path.join(authDir(), `${account}.json`);
  fs.mkdirSync(path.dirname(authPath), { recursive: true });
  fs.writeFileSync(authPath, JSON.stringify(state, null, 2));
  console.log(`Auth saved to ${authPath}`);

  if (account && !outputArg) {
    updateRegistry(account, email);
  }

  rl.close();
  await browser.close();
  process.exit(0);
})();
