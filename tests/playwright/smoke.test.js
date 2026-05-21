/**
 * Smoke test: trigger syncAll via the Sheet "Action Sync > Sync" menu and confirm
 * a sync.complete log entry appears in the Drive-mapped log directory within 30 seconds.
 *
 * Prerequisites:
 *   - .auth/user.json present (run auth.setup.js once)
 *   - GAS deployed (clasp push)
 *   - gasLogDir in local.settings.json points to a Drive-for-Desktop folder
 *   - testSheetId in local.settings.json is the bound spreadsheet ID
 */

const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');
const { runViaSheetMenu } = require('./editor_helpers');

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------
const settingsPath = path.join(__dirname, '..', '..', 'local.settings.json');
if (!fs.existsSync(settingsPath)) {
  throw new Error(`local.settings.json not found at ${settingsPath}`);
}
const settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
const gasLogDir = settings.gasLogDir;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Delete every *.log file in gasLogDir so polling starts from a clean state.
 */
function clearLogs() {
  if (!gasLogDir || !fs.existsSync(gasLogDir)) return;
  for (const name of fs.readdirSync(gasLogDir)) {
    if (name.endsWith('.log')) {
      fs.rmSync(path.join(gasLogDir, name), { force: true });
    }
  }
}

/**
 * Poll gasLogDir for an NDJSON entry where entry.tag === targetTag.
 * Resolves with the matching entry or rejects after timeoutMs.
 *
 * @param {string} targetTag
 * @param {number} timeoutMs
 * @param {number} intervalMs
 * @returns {Promise<object>}
 */
function waitForLogEntry(targetTag, timeoutMs = 30000, intervalMs = 500) {
  return new Promise((resolve, reject) => {
    if (!gasLogDir || !fs.existsSync(gasLogDir)) {
      return reject(new Error(`gasLogDir not set or does not exist: ${gasLogDir}`));
    }

    const deadline = Date.now() + timeoutMs;

    function poll() {
      if (Date.now() >= deadline) {
        return reject(
          new Error(`Timed out after ${timeoutMs}ms waiting for log entry with tag='${targetTag}'`)
        );
      }

      let found = null;
      try {
        const files = fs.readdirSync(gasLogDir).filter(f => f.endsWith('.log')).sort();
        outer: for (const name of files) {
          const text = fs.readFileSync(path.join(gasLogDir, name), 'utf8');
          for (const line of text.split('\n')) {
            const trimmed = line.trim();
            if (!trimmed) continue;
            let entry;
            try {
              entry = JSON.parse(trimmed);
            } catch {
              continue;
            }
            if (entry.tag === targetTag) {
              found = entry;
              break outer;
            }
          }
        }
      } catch (err) {
        // Transient I/O error — keep polling
      }

      if (found) {
        resolve(found);
      } else {
        setTimeout(poll, intervalMs);
      }
    }

    poll();
  });
}

// ---------------------------------------------------------------------------
// Test
// ---------------------------------------------------------------------------

test('syncDocument emits sync.complete log entry', async ({ page }) => {
  // 1. Clear any stale log files so polling starts fresh
  clearLogs();

  // 2. Invoke syncAll via the Sheet menu: Action Sync → Sync
  await runViaSheetMenu(page, 'Action Sync', 'Sync');

  // 3. Poll Drive-mapped log directory for sync.complete entry (30 s timeout)
  const entry = await waitForLogEntry('sync.complete', 30000, 500);

  // 4. Assert the entry was found and is well-formed
  expect(entry).toBeTruthy();
  expect(entry.tag).toBe('sync.complete');
  expect(typeof entry.ts).toBe('string');
});
