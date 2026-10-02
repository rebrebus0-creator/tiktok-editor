// Render an existing (hand-written or resolved) plan file directly:
//   npm run render -- work/<job>/plan.resolved.json out/<job>.mp4
import fs from 'node:fs';
import {renderPlan} from './render';
import {loadSettings} from './settings';

const [planFile, outFile] = process.argv.slice(2);
if (!planFile || !outFile) {
  console.error('usage: npm run render -- <plan.json> <out.mp4>');
  process.exit(1);
}
await renderPlan(JSON.parse(fs.readFileSync(planFile, 'utf8')), outFile, loadSettings());
