/* vj-remote Vital-style links test.
   Drives the real page: seeds a layout via localStorage, stubs WebSocket,
   then moves controls and asserts the exact OSC messages each link produces.
   Run: NODE_PATH=~/workspace/limbo-test/node_modules node tests/test-links.mjs */
import { chromium } from 'playwright-core';
import { readFileSync } from 'fs';

const PAGE = 'file:///home/hatch/workspace/vj-remote/web/index.html';
const results = [];
const check = (name, ok, extra = '') => {
  results.push(ok);
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? '  — ' + extra : ''}`);
};

const layout = {
  name: 'link test',
  controls: [
    { id: 'ka', type: 'knob', label: 'A', binding: { kind: 'effect-param', p: { layer: 1, effect: 'goo', param: 'speed' } }, min: 0, max: 1, def: 0.5,
      links: [{ target: 'kb', amount: 1 }, { target: 'sc', amount: 0.5 }] },
    { id: 'kb', type: 'knob', label: 'B', binding: { kind: 'layer-opacity', p: { layer: 1 } }, min: 0, max: 1, def: 0.5 },
    { id: 'sc', type: 'slider', label: 'C', binding: { kind: 'master-opacity', p: {} }, orientation: 'v', min: 0, max: 1 },
    { id: 'xd', type: 'xy', label: 'D pad', binding: { x: { kind: 'effect-param', p: { layer: 1, effect: 'goo', param: 'speed' } }, y: { kind: 'layer-opacity', p: { layer: 2 } } }, spring: false },
    { id: 'eb', type: 'button', label: 'E', binding: { kind: 'layer-bypass', p: { layer: 1 } }, behavior: 'toggle' },
  ],
};

const browser = await chromium.launch({ executablePath: '/opt/meta-chromium/chrome',
  args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const page = await browser.newPage();
const errors = [];
page.on('pageerror', e => errors.push('pageerror: ' + e.message));
page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });

await page.addInitScript((ls) => {
  if (!localStorage.getItem('vjremote.layout.v1'))
    localStorage.setItem('vjremote.layout.v1', JSON.stringify(ls));
  localStorage.removeItem('vjremote.bridge');
  window.__msgs = [];
  window.WebSocket = function (url) {
    const s = { url, readyState: 1 };
    s.send = (data) => { window.__msgs.push(JSON.parse(data)); };
    s.close = () => {};
    setTimeout(() => { if (s.onopen) s.onopen(); }, 0);
    return s;
  };
}, layout);

await page.goto(PAGE, { waitUntil: 'load' });
await page.waitForTimeout(600);

const msgs = () => page.evaluate(() => window.__msgs);
const clear = () => page.evaluate(() => { window.__msgs = []; });
const card = (id) => page.evaluate((cid) => {
  const el = document.querySelector('.ctl[data-id="' + cid + '"]');
  return !!el;
}, id);
const move = (id, v, axis) => page.evaluate(([cid, val, ax]) => {
  document.querySelector('.ctl[data-id="' + cid + '"]')._setLinked(val, ax);
}, [id, v, axis]);
const setLinks = (id, links) => page.evaluate(([cid, ls]) => {
  const cur = JSON.parse(localStorage.getItem('vjremote.layout.v1'));
  cur.controls = cur.controls.map(c =>
    c.id === cid ? Object.assign({}, c, { links: ls }) : c);
  localStorage.setItem('vjremote.layout.v1', JSON.stringify(cur));
}, [id, links]).then(() => page.reload({ waitUntil: 'load' }))
  .then(() => page.waitForTimeout(500));

check('all 5 cards rendered', await card('ka') && await card('kb') && await card('sc') && await card('xd') && await card('eb'));
check('link badge on source card', await page.evaluate(() =>
  document.querySelector('.ctl[data-id="ka"] .linkbadge')?.textContent === '🔗2'));

// 1. one source -> two targets, with amount scaling
await clear();
await move('ka', 0.8);
let m = await msgs();
const addr = (a) => m.filter(x => x.address === a).map(x => x.args[0].value);
check('A sends own OSC @0.8',
  addr('/composition/layers/1/video/effects/goo/speed').join() === '0.8', JSON.stringify(m));
check('B follows @100%',
  addr('/composition/layers/1/video/opacity').join() === '0.8');
check('C follows @50% -> 0.4',
  addr('/composition/video/opacity').join() === '0.4');

// 2. negative amount inverts
await setLinks('ka', [{ target: 'kb', amount: -1 }]);
await page.waitForTimeout(600);
await clear();
await move('ka', 0.75);
m = await msgs();
check('invert: A=0.75 -> B=0.25',
  m.filter(x => x.address === '/composition/layers/1/video/opacity').map(x => x.args[0].value).join() === '0.25',
  JSON.stringify(m.map(x => x.address + '=' + x.args[0].value)));

// 3. cycle guard: A<->B terminates
await setLinks('ka', [{ target: 'kb', amount: 1 }]);
await setLinks('kb', [{ target: 'ka', amount: 1 }]);
await page.waitForTimeout(900);
await clear();
await move('ka', 0.5);
m = await msgs();
check('A<->B cycle terminates at 2 sends', m.length === 2, 'got ' + m.length);

// 4. chaining: A->B->C propagates
await setLinks('kb', [{ target: 'sc', amount: 1 }]);
await page.waitForTimeout(900);
await clear();
await move('ka', 0.6);
m = await msgs();
check('chain A->B->C = 3 sends', m.length === 3, 'got ' + m.length);
check('C got chained value 0.6',
  m.filter(x => x.address === '/composition/video/opacity').map(x => x.args[0].value).join() === '0.6');

// 5. XY source axis select: X moves, Y-link stays quiet
await setLinks('xd', [{ target: 'kb', amount: 1, src: 'y' }]);
await page.waitForTimeout(900);
await clear();
await move('xd', 0.9, 'x');
m = await msgs();
check('X move does not drive Y-link',
  !m.some(x => x.address === '/composition/layers/1/video/opacity'),
  JSON.stringify(m.map(x => x.address)));
await clear();
await move('xd', 0.3, 'y');
m = await msgs();
check('Y move drives Y-link @0.3',
  m.filter(x => x.address === '/composition/layers/1/video/opacity').map(x => x.args[0].value).join() === '0.3');

// 6. XY as target: taxis picks the axis
await setLinks('ka', [{ target: 'xd', amount: 1, taxis: 'y' }]);
await page.waitForTimeout(900);
await clear();
await move('ka', 0.65);
m = await msgs();
check('pad Y axis driven @0.65',
  m.filter(x => x.address === '/composition/layers/2/video/opacity').map(x => x.args[0].value).join() === '0.65');
check('pad X axis untouched (exactly 1 send to that address: A\'s own)',
  m.filter(x => x.address === '/composition/layers/1/video/effects/goo/speed').length === 1,
  JSON.stringify(m.map(x => x.address + '=' + x.args[0].value)));

// 7. button as target: threshold -> int 0/1
await setLinks('ka', [{ target: 'eb', amount: 1 }]);
await page.waitForTimeout(900);
await clear();
await move('ka', 0.6);
m = await msgs();
check('button target ON @0.6',
  m.filter(x => x.address === '/composition/layers/1/bypassed').map(x => x.args[0].value).join() === '1');
await clear();
await move('ka', 0.4);
m = await msgs();
check('button target OFF @0.4',
  m.filter(x => x.address === '/composition/layers/1/bypassed').map(x => x.args[0].value).join() === '0');

// 8. config sheet links editor renders
await setLinks('ka', [{ target: 'kb', amount: 0.5 }, { target: 'sc', amount: -1 }]);
await page.waitForTimeout(900);
const cfg = await page.evaluate(() => {
  openCfg('ka');
  const rows = document.querySelectorAll('#cfgLinks .lrow').length;
  const opts = document.querySelectorAll('#linkTarget option').length;
  const pct = document.querySelector('#cfgLinks .lrow .lval')?.textContent;
  document.getElementById('cfgDone').click();
  return { rows, opts, pct };
});
check('cfg shows 2 link rows', cfg.rows === 2, JSON.stringify(cfg));
check('cfg target picker lists other controls', cfg.opts === 4, 'opts=' + cfg.opts);
check('cfg shows 50% amount', cfg.pct === '50%');

check('zero page errors', errors.length === 0, errors.join(' | ').slice(0, 300));

const failed = results.filter(r => !r).length;
console.log(`\n${results.length - failed}/${results.length} passed`);
await browser.close();
process.exit(failed ? 1 : 0);
