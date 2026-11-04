// Headless check of the browser controller: node site/tools/test_sim.mjs [robot] [trials]
import { existsSync, readFileSync, writeFileSync } from 'fs';
import loadMujoco from '../public/vendor/mujoco.js';
import { LiveRobot, loadRobot } from '../public/sim.js';
const base = new URL('../public/', import.meta.url);
const name = process.argv[2] || 'ur5e', n = +(process.argv[3] || 10);
const mj = await loadMujoco();
const { model, meta } = await loadRobot(mj, name, (p) => readFileSync(new URL(p, base)), (p) => JSON.parse(readFileSync(new URL(p, base))));
let seed = 12345; const rng = () => (seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296;
const r = new LiveRobot(mj, model, meta);
function run(limit, event) {
  const t0 = r.d.time; let fired = false;
  while (r.d.time - t0 < limit) {
    r.advance(0.04);
    if (event && !fired && event(r, r.d.time - t0)) fired = true;
    if (r.step === 'done' && r.state().inBowl && r.d.time - t0 > 0.5 && (!event || fired)) return { ok: true, t: r.d.time - t0, fired };
  }
  return { ok: false, t: limit, step: r.step, fired, cube: r.state().cube.map((v) => +v.toFixed(3)), note: r.note };
}
const report = (label, res) => {
  const ok = res.filter((x) => x.ok);
  console.log(label.padEnd(22), `${ok.length}/${res.length}`, 'mean', (ok.reduce((a, x) => a + x.t, 0) / (ok.length || 1)).toFixed(1), 's', res.filter((x) => !x.ok).slice(0, 3).map((x) => JSON.stringify(x)).join(' '));
};
const start = performance.now();
const plain = []; const cases = { 'move while reaching': [], 'take while descending': [], 'knock while carrying': [], 'take out of bowl': [] };
for (let i = 0; i < n; i++) { r.reset(r.layout(rng)); plain.push(run(30)); }
report('no disturbance', plain);
for (let i = 0; i < n; i++) {
  r.reset(r.layout(rng));
  cases['move while reaching'].push(run(35, (b, t) => { if (b.step !== 'reach' || t < 0.8) return false; const l = b.layout(rng); b.placeCube(l.cube, l.yaw); return true; }));
  r.reset(r.layout(rng));
  cases['take while descending'].push(run(35, (b) => { if (b.step !== 'descend') return false; const l = b.layout(rng); b.placeCube(l.cube, l.yaw); return true; }));
  r.reset(r.layout(rng));
  cases['knock while carrying'].push(run(35, (b) => { if (b.step !== 'carry') return false; b.knock(); return true; }));
  r.reset(r.layout(rng));
  cases['take out of bowl'].push(run(40, (b) => { if (b.step !== 'done') return false; const l = b.layout(rng); b.placeCube(l.cube, l.yaw); return true; }));
}
for (const [k, v] of Object.entries(cases)) report(k, v);
const file = new URL('../public/data/live_test.json', import.meta.url);
const old = existsSync(file) ? JSON.parse(readFileSync(file)) : {};
old[name] = { undisturbed: [plain.filter((x) => x.ok).length, plain.length], ...Object.fromEntries(Object.entries(cases).map(([k, v]) => [k, [v.filter((x) => x.ok).length, v.length]])) };
writeFileSync(file, JSON.stringify(old, null, 1));
console.log('recoveries', r.recoveries, 'wall s', ((performance.now() - start) / 1000).toFixed(1), 'sim s', r.d.time.toFixed(0));
