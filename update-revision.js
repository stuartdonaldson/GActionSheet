/**
 * Stamps version and build date into src/Version.js.
 * Reads version from package.json. Called by deploy:test and deploy:prod
 * before clasp push — do not call directly.
 */

const fs = require('fs');
const path = require('path');

const packageJson = JSON.parse(fs.readFileSync(path.join(__dirname, 'package.json'), 'utf8'));
const appVersion = `v${packageJson.version}`;

const now = new Date();
const dateStr = now.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
const timeStr = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
const currentDateTime = `${dateStr} ${timeStr}`;

const versionPath = path.join(__dirname, 'src', 'Version.js');

let data = fs.readFileSync(versionPath, 'utf8');
data = data.replace(/version: "[^"]*"/, `version: "${appVersion} (Rev. ${currentDateTime})"`);
data = data.replace(/buildDate: "[^"]*"/, `buildDate: "${now.toISOString()}"`);
fs.writeFileSync(versionPath, data, 'utf8');

console.log(`Revision stamped: ${appVersion} — ${currentDateTime}`);
