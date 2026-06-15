const { defineConfig } = require('@playwright/test');

// Probe-only config: identical to playwright.config.js but does NOT ignore probe.test.js.
// The base config sets testIgnore: ['**/probe.test.js'] to keep the probe out of the default
// test:smoke/test:full sweeps. In Playwright 1.59.1 testIgnore also excludes a file passed as an
// explicit positional path, so `npm run probe` against the base config returned "No tests found".
// Re-export the base config with testIgnore dropped and the probe file matched. See GTaskSheet-p8w0.
const { testIgnore, ...base } = require('./playwright.config.js');

module.exports = defineConfig({
  ...base,
  testMatch: ['**/probe.test.js'],
});
