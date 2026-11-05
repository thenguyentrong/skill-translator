// Each saved card's objects in the browser controller: node site/tools/test_job.mjs [trials]
import { readFileSync, readdirSync } from 'fs';
import loadMujoco from '../public/vendor/mujoco.js';
import { LiveRobot, loadRobot } from '../public/sim.js';
const base = new URL('../public/', import.meta.url), cards = new URL('../../cards/', import.meta.url);
const n = +(process.argv[2] || 5);
const mj = await loadMujoco();
const jobs = readdirSync(cards).map((f) => JSON.parse(readFileSync(new URL(f, cards)))).filter((c) => (c.kind ?? 'pick_place') === 'pick_place');
for (const name of ['ur5e', 'panda', 'xarm7']) {
  const { model, meta } = await loadRobot(mj, name, (p) => readFileSync(new URL(p, base)), (p) => JSON.parse(readFileSync(new URL(p, base))));
  const r = new LiveRobot(mj, model, meta);
  let seed = 7; const rng = () => (seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296;
  const row = [];
  for (const card of jobs) {
    r.setJob(card);
    let ok = 0;
    const why = [];
    for (let i = 0; i < n; i++) {
      r.reset(r.layout(rng));
      const t0 = r.d.time;
      while (r.d.time - t0 < 40) { r.advance(0.04); if (r.step === 'done' && r.state().inBowl) break; }
      if (r.step === 'done' && r.state().inBowl) ok++; else why.push(r.step + (r.note ? `:${r.note.slice(0, 24)}` : ''));
    }
    row.push(`${card.name} ${ok}/${n}${why.length ? ` (${why[0]})` : ''}`);
  }
  console.log(name.padEnd(6), row.join(' | '));
}
