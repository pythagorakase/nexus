// 777-KBD rendered-browser proof: keyboard roster access and map dialog
// focus return, driven in headless Chromium against the production CSS from
// `npm --prefix ui run build` and the real shell (keyboard-fixture.tsx, a
// copy of ui/scripts/state-surfaces/fixture.tsx with a seeded cast).
// file:// origin, every HTTP request aborted, no gateway.
// Run (after npm --prefix ui run build):
//   KBD_SCRATCH=<scratch dir> node docs/qa/777-keyboard-roster-and-map/keyboard-proof.mjs
import assert from 'node:assert/strict';
import { readdirSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const evidence = import.meta.dirname;
const root = resolve(evidence, '../../..');
const ui = resolve(root, 'ui');
const require = createRequire(resolve(ui, 'package.json'));
const { chromium } = require('playwright');
const { build } = createRequire(require.resolve('vite'))('esbuild');

// The bundled fixture and its HTML are build intermediates: keep them out of
// the evidence directory.
if (!process.env.KBD_SCRATCH) throw new Error('Set KBD_SCRATCH to a scratch directory');
const work = resolve(process.env.KBD_SCRATCH);
mkdirSync(work, { recursive: true });
const bundle = await build({ absWorkingDir: ui, entryPoints: [resolve(evidence, 'keyboard-fixture.tsx')],
  bundle: true, write: false, platform: 'browser', format: 'iife', jsx: 'automatic',
  nodePaths: [resolve(ui, 'node_modules')],
  alias: { '@': resolve(ui, 'client/src'), '@shared': resolve(ui, 'shared') },
  loader: { '.css': 'empty' } });
writeFileSync(resolve(work, 'fixture.js'), bundle.outputFiles[0].contents);
const assets = resolve(ui, 'dist/public/assets');
const cssName = readdirSync(assets).find(name => /^index-.*\.css$/.test(name));
if (!cssName) throw new Error('Run npm --prefix ui run build first: no production CSS');
const css = readFileSync(resolve(assets, cssName), 'utf8');
const html = resolve(work, 'fixture.html');
writeFileSync(html, `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>${css}</style><div id="root"></div><script src="fixture.js"></script>`);

const errors = [], requests = [], steps = [];
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1200, height: 900 }, deviceScaleFactor: 1,
  colorScheme: 'dark', reducedMotion: 'reduce', hasTouch: false, isMobile: false });

async function settle() {
  await page.evaluate(async () => {
    await Promise.all(document.getAnimations().map(a => a.finished.catch(() => {})));
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  });
}

/** document.activeElement as tag, role, accessible name and focus styling. */
async function active(label) {
  await settle();
  const reading = await page.evaluate(() => {
    const el = document.activeElement;
    const style = getComputedStyle(el);
    const name = el.getAttribute('aria-label')
      ?? (el.getAttribute('aria-labelledby') ? document.getElementById(el.getAttribute('aria-labelledby'))?.textContent : null)
      ?? el.textContent?.trim().replace(/\s+/g, ' ') ?? '';
    return { tag: el.tagName, role: el.getAttribute('role') ?? (el.tagName === 'BUTTON' ? 'button' : null),
      name, testid: el.getAttribute('data-testid'), ariaSelected: el.getAttribute('aria-selected'),
      tabindex: el.getAttribute('tabindex'), focusVisible: el.matches(':focus-visible'),
      outline: `${style.outlineStyle} ${style.outlineWidth} ${style.outlineColor}`, boxShadow: style.boxShadow,
      dossier: document.querySelector('[data-testid="text-dossier-name"]')?.textContent ?? null,
      dialogOpen: document.querySelector('[role="dialog"]') !== null };
  });
  steps.push({ step: label, ...reading });
  return reading;
}

async function mount(mode) {
  await page.evaluate(mode => window.renderSurfaces('veil', mode, 'sea', false), mode);
  await page.locator('[data-testid="nexus-layout"]').waitFor();
  await page.evaluate(() => document.fonts.ready);
}

async function load() {
  await page.goto(pathToFileURL(html).href);
}

page.on('pageerror', error => errors.push(error.message));
page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()); });
await page.route(/^https?:/, route => route.abort());
await page.routeWebSocket(/.*/, () => {});
await page.route('**/fonts/**', route => route.fulfill({
  path: resolve(ui, 'client/public', new URL(route.request().url()).pathname.slice(1)) }));

const readings = {};
try {
  // ── Defect 1: the roster (twice: first load, then after a full reload) ──
  for (const pass of ['first', 'reload']) {
    if (pass === 'reload') await page.reload(); else await load();
    await mount('characters');
    await page.locator('[data-testid="characters-pane"]').waitFor();
    await page.locator('[data-testid="rail-characters"]').focus();
    let r = await active(`${pass}: focus Characters rail button`);
    assert.equal(r.name, 'Characters');
    await page.keyboard.press('Tab');
    r = await active(`${pass}: Tab`);
    assert.equal(r.name, 'Settings');
    await page.keyboard.press('Tab');
    r = await active(`${pass}: Tab`);
    assert.deepEqual([r.role, r.name, r.ariaSelected, r.tabindex, r.focusVisible], ['option', 'Ivo Sato', 'true', '0', true]);
    await page.keyboard.press('Shift+Tab');
    r = await active(`${pass}: Shift+Tab`);
    assert.equal(r.name, 'Settings');
    await page.keyboard.press('Tab');
    r = await active(`${pass}: Tab`);
    assert.equal(r.name, 'Ivo Sato');
    await page.keyboard.press('ArrowDown');
    r = await active(`${pass}: ArrowDown`);
    assert.deepEqual([r.role, r.name, r.ariaSelected, r.dossier, r.focusVisible], ['option', 'Pela', 'false', 'Ivo Sato', true]);
    assert.notEqual(r.boxShadow, 'none');
    if (pass === 'first') {
      await page.screenshot({ path: resolve(evidence, 'roster-keyboard-focus.png') });
      writeFileSync(resolve(evidence, 'roster-accessibility.txt'),
        await page.locator('.charspane-list').ariaSnapshot() + '\n');
      readings.ringToken = await page.evaluate(() =>
        getComputedStyle(document.documentElement).getPropertyValue('--ring').trim());
    }
    await page.keyboard.press('Enter');
    r = await active(`${pass}: Enter`);
    assert.deepEqual([r.name, r.ariaSelected, r.dossier], ['Pela', 'true', 'Pela']);
    await page.keyboard.press('ArrowDown');
    const scrollBefore = await page.evaluate(() => document.querySelector('.charspane-list').scrollTop);
    await page.keyboard.press('Space');
    r = await active(`${pass}: ArrowDown, Space`);
    assert.deepEqual([r.name, r.ariaSelected, r.dossier], ['Mara Quill', 'true', 'Mara Quill']);
    assert.equal(await page.evaluate(() => document.querySelector('.charspane-list').scrollTop), scrollBefore);
    await page.keyboard.press('End');
    r = await active(`${pass}: End`);
    assert.equal(r.name, 'Juno Halloran');
    await page.keyboard.press('Home');
    r = await active(`${pass}: Home`);
    assert.equal(r.name, 'Ivo Sato');
    await page.keyboard.press('Tab');
    r = await active(`${pass}: Tab`);
    assert.equal(r.name, 'Upload portrait');
    await page.keyboard.press('Shift+Tab');
    r = await active(`${pass}: Shift+Tab`);
    assert.deepEqual([r.role, r.name, r.ariaSelected], ['option', 'Ivo Sato', 'false']);
    await page.locator('[data-testid="cast-member-5"]').click();
    r = await active(`${pass}: mouse click Rhea Lind`);
    assert.deepEqual([r.name, r.ariaSelected, r.dossier], ['Rhea Lind', 'true', 'Rhea Lind']);
  }

  // ── Defect 2: the map place dialog ─────────────────────────────────────
  await load();
  await mount('map');
  await page.locator('[data-testid="map-pane"]').waitFor();
  await page.locator('[data-testid="map-zone-1"]').focus();
  await page.keyboard.press('Enter');
  const place = page.getByRole('button', { name: 'Ring Three Public Kitchen' });
  await place.focus();
  let r = await active('map: focus Ring Three Public Kitchen');
  assert.equal(r.name, 'Ring Three Public Kitchen');
  for (const [pass, close] of [['first pass', 'Escape'], ['second pass', 'Close (Enter)'], ['third pass', 'Close (mouse)']]) {
    await page.keyboard.press('Enter');
    await page.getByRole('dialog').waitFor();
    r = await active(`map ${pass}: Enter`);
    assert.deepEqual([r.name, r.dialogOpen], ['Close', true]);
    if (close === 'Escape') await page.keyboard.press('Escape');
    else if (close === 'Close (Enter)') await page.keyboard.press('Enter');
    else await page.getByRole('button', { name: 'Close' }).click();
    await page.getByRole('dialog').waitFor({ state: 'detached' });
    r = await active(`map ${pass}: ${close}`);
    assert.deepEqual([r.tag, r.name, r.dialogOpen], ['BUTTON', 'Ring Three Public Kitchen', false]);
    if (close !== 'Close (mouse)') assert.equal(r.focusVisible, true);
    if (pass === 'first pass')
      await page.screenshot({ path: resolve(evidence, 'map-focus-return.png') });
  }
  assert.deepEqual(errors, []);
  assert.deepEqual(requests, []);
  readings.fixtureTransport = await page.evaluate(() => window.fixtureTransport);
  assert.equal(readings.fixtureTransport.some(t => t.method !== 'GET' && t.method !== 'HEAD'), false);
  console.log(`roster (first load + reload) and map focus return passed: ${steps.length} readbacks, ${errors.length} page errors, ${requests.length} HTTP requests`);
} finally {
  writeFileSync(resolve(evidence, 'keyboard-readback.json'),
    JSON.stringify({ productionCss: cssName, readings, steps, errors, requests }, null, 2) + '\n');
  await browser.close();
}
