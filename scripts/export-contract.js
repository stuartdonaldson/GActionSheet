#!/usr/bin/env node
/**
 * export-contract.js
 *
 * Exports CONTRACT_SCHEMA from src/ContractSchema.js as JSON.
 * Called by `npm run export-contract` (defined in package.json).
 *
 * Loads the entire ContractSchema.js file in a VM context and writes
 * the JSON-serialized CONTRACT_SCHEMA to ContractSchema.json at the project root.
 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const contractPath = path.join(__dirname, '../src/ContractSchema.js');
const outputPath = path.join(__dirname, '../ContractSchema.json');

try {
  const src = fs.readFileSync(contractPath, 'utf8');
  const ctx = vm.createContext({});
  vm.runInContext(src, ctx);

  if (!ctx.CONTRACT_SCHEMA) {
    console.error('ERROR: CONTRACT_SCHEMA not defined in src/ContractSchema.js');
    process.exit(1);
  }

  const json = JSON.stringify(ctx.CONTRACT_SCHEMA, null, 2);
  fs.writeFileSync(outputPath, json);
  console.log(`Exported ContractSchema.json (${json.length} bytes)`);
} catch (err) {
  console.error('ERROR exporting contract:', err.message);
  process.exit(1);
}
