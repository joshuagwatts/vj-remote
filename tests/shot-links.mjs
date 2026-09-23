/* Eyeball check: links editor + app connect overlay. */
import { chromium } from 'playwright-core';

const PAGE = 'file:///home/hatch/workspace/vj-remote/web/index.html';
const layout = { name: 't', controls: [
  { id: 'ka', type: 'knob', label: 'Goo speed', binding: { kind: 'effect-param', p: { layer: 1, effect: 'goo', param: 'speed' } }, min: 0, max: 1, def: 0.5,
    links: [{ target: 'kb', amount: 1 }, { target: 'sc', amount: -0.5 }] },
  { id: 'kb', type: 'knob', label: 'Trails', binding: { kind: 'effect-param', p: { layer: 1, effect: 'trails', param: 'decay' } }, min: 0, max: 1, def: 0 },
  { id: 'sc', type: 'slider', label: 'Master', binding: { kind: 'master-opacity', p: {} }, orientation: 'v', min: 0, max: 1 },
]};

const browser = await chromium.launch({ executablePath: '/opt/meta-chromium/chrome',
  args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
await page.addInitScript((ls) => {
  localStorage.setItem('vjremote.layout.v1', JSON.stringify(ls));
  window.WebSocket = function () { return { readyState: 1, send() {}, close() {} }; };
  // pretend we're the installed app with no bridge yet
  window.Capacitor = { isNativePlatform: () => true };
}, layout);
await page.goto(PAGE, { waitUntil: 'load' });
await page.waitForTimeout(500);

// connect overlay (app mode, no bridge saved)
await page.screenshot({ path: '/tmp/vj-connect.png' });
// dismiss overlay, open config sheet on the linked knob
await page.evaluate(() => document.getElementById('connectOv').classList.remove('show'));
await page.evaluate(() => openCfg('ka'));
await page.waitForTimeout(400);
await page.screenshot({ path: '/tmp/vj-links.png' });
await browser.close();
console.log('shots saved');
