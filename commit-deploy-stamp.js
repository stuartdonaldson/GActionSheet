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

const meta = JSON.parse(fs.readFileSync(metadataFile, 'utf8'));
const { deploymentId, version, description, target } = meta;
// productVersion/at are written explicitly by manage-deployments.js's deployMetadata shaper
// (gas-deploy, RECOMMENDATION.md Stage 3). The regexes are the pre-package fallback: metadata
// written by the old script only carried the product version and timestamp inside `description`.
const deployVersion = meta.productVersion || (description.match(/v\d+\.\d+\.\d+/) || ['unknown'])[0];
const deployTimestamp = meta.at || (description.match(/Rev\.\s+(.+)\)/) || [null, 'unknown'])[1];

const msg = `chore: deploy stamp\n\nDeployed ${deployVersion} to ${target}\nDeployment ID: ${deploymentId}\nDeployment revision: ${version}\nTimestamp: ${deployTimestamp}`;
execSync('git add src/Version.js', { stdio: 'inherit' });
execSync(`git commit -m "${msg.replace(/"/g, '\\"')}"`, { stdio: 'inherit' });
fs.unlinkSync(metadataFile);
console.log('✅ Deploy stamp committed.');
