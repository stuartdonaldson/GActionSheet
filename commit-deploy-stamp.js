#!/usr/bin/env node

/**
 * Commits src/Version.js with deployment metadata in the message.
 * Called by release:patch/minor/major after deployment completes.
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const metadataFile = path.join(__dirname, '.deploy-metadata.json');
if (!fs.existsSync(metadataFile)) {
  console.error('❌ No deployment metadata found. Did deploy:prod run successfully?');
  process.exit(1);
}

const { deploymentId, version, description, target } = JSON.parse(fs.readFileSync(metadataFile, 'utf8'));
const versionMatch = description.match(/v\d+\.\d+\.\d+/);
const revMatch = description.match(/Rev\.\s+(.+)\)/);
const deployVersion = versionMatch ? versionMatch[0] : 'unknown';
const deployTimestamp = revMatch ? revMatch[1] : 'unknown';

const msg = `chore: deploy stamp\n\nDeployed ${deployVersion} to ${target}\nDeployment ID: ${deploymentId}\nDeployment revision: ${version}\nTimestamp: ${deployTimestamp}`;
execSync('git add src/Version.js', { stdio: 'inherit' });
execSync(`git commit -m "${msg.replace(/"/g, '\\"')}"`, { stdio: 'inherit' });
fs.unlinkSync(metadataFile);
console.log('✅ Deploy stamp committed.');
