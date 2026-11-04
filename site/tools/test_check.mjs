// Do the browser rules give the same answer as the Python translator on saved cards? node site/tools/test_check.mjs
import { readFileSync } from 'fs';
import { answer } from '../public/check.js';
const d = JSON.parse(readFileSync(new URL('../public/data/facts.json', import.meta.url)));
let same = 0, total = 0;
for (const j of d.jobs) for (const r of d.robots) {
  const a = answer(r, j, d.table), want = j.python[r.id] ?? null; total++;
  if (a.label === want) same++; else console.log('differs:', j.title, r.name, 'python', want, 'js', a.label, a.why);
}
console.log(`${same}/${total} match`);
