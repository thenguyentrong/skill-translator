// node site/tools/shot.mjs <url> <out-prefix> : headless click-through + screenshots (run from the playwright folder via NODE_PATH)
import { chromium } from 'playwright';
const [url, out] = process.argv.slice(2);
const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const p = await b.newPage({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark' });
const logs = [];
p.on('console', (m) => { if (['error', 'warning'].includes(m.type())) logs.push(m.type() + ': ' + m.text()); });
p.on('pageerror', (e) => logs.push('pageerror: ' + e.message));
await p.goto(url); await p.waitForFunction(() => window.__live, null, { timeout: 60000 });
await p.waitForTimeout(6000);
const s = await p.evaluate(() => window.__live);
console.log('step', s.step, 't', s.time, 'tries', s.tries);
await p.screenshot({ path: out + '_dark.png' });
console.log(logs.slice(0, 10).join('\n'));
await b.close();
