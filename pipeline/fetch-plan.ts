// Fetch/generate all assets of an existing plan and write <plan>.resolved.json next to it:
//   npm run fetch -- work/<job>/plan.json <job> [--fresh]
import fs from 'node:fs';
import {fetchAssets} from './assets';
import {loadSettings} from './settings';

const [planFile, job] = process.argv.slice(2);
if (!planFile || !job) {
  console.error('usage: npm run fetch -- <plan.json> <job> [--fresh]');
  process.exit(1);
}
const plan = JSON.parse(fs.readFileSync(planFile, 'utf8'));
await fetchAssets(plan, job, loadSettings(), process.argv.includes('--fresh'));
const out = planFile.replace(/\.json$/, '.resolved.json');
fs.writeFileSync(out, JSON.stringify(plan, null, 1));
console.log(`-> ${out}`);
