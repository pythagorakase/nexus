// 821-S2 rendered-browser proof: a needed key's seat list opens on a tap at
// phone width (390x844, touch, mobile), driven in headless Chromium against
// the production CSS from `npm --prefix ui run build` and the real shell
// (seat-fixture.tsx, a copy of the 777 keyboard fixture whose key rows name
// their seats). file:// origin, every HTTP request aborted, no gateway.
// Run (after npm --prefix ui run build):
//   SEAT_SCRATCH=<scratch dir> node docs/qa/821-touch-seat-list/seat-proof.mjs
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
if (!process.env.SEAT_SCRATCH) throw new Error('Set SEAT_SCRATCH to a scratch directory');
const work = resolve(process.env.SEAT_SCRATCH);
mkdirSync(work, { recursive: true });
const bundle = await build({ absWorkingDir: ui, entryPoints: [resolve(evidence, 'seat-fixture.tsx')],
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

const errors = [], requests = [], readings = {};
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 390, height: 844 },
  hasTouch: true, isMobile: true, deviceScaleFactor: 1,
  colorScheme: 'dark', reducedMotion: 'reduce' });

async function settle() {
  await page.evaluate(async () => {
    await Promise.all(document.getAnimations().map(a => a.finished.catch(() => {})));
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  });
}
const box = b => b && { x: b.x, y: b.y, width: b.width, height: b.height, right: b.x + b.width, bottom: b.y + b.height };

try {
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()); });
  await page.route(/^https?:/, route => route.abort());
  await page.routeWebSocket(/.*/, () => {});
  await page.route('**/fonts/**', route => route.fulfill({
    path: resolve(ui, 'client/public', new URL(route.request().url()).pathname.slice(1)) }));
  await page.goto(pathToFileURL(html).href);
  readings.viewport = await page.evaluate(() => ({ innerWidth, innerHeight,
    coarseNarrow: matchMedia('(max-width: 760px) and (pointer: coarse)').matches }));
  assert.equal(readings.viewport.innerWidth, 390);
  assert.equal(readings.viewport.coarseNarrow, true);

  await page.evaluate(() => window.renderSurfaces('veil', 'key', 'sea', false));
  await page.locator('[data-testid="nexus-layout"]').waitFor();
  await page.evaluate(() => document.fonts.ready);
  await page.getByRole('button', { name: 'API Keys', exact: true }).tap();
  await settle();

  const trigger = page.getByTestId('key-seats-trigger-required-missing');
  await trigger.scrollIntoViewIfNeeded();
  await settle();
  readings.before = {
    dialogs: await page.getByRole('dialog').count(),
    trigger: box(await trigger.boundingBox()),
    triggerRole: await trigger.evaluate(el => ({ tag: el.tagName, type: el.getAttribute('type'),
      ariaExpanded: el.getAttribute('aria-expanded'), title: el.getAttribute('title'), text: el.textContent })),
    scrollWidth: await page.evaluate(() => document.documentElement.scrollWidth),
    cardText: await page.locator('#set-keys').textContent(),
  };
  assert.equal(readings.before.dialogs, 0);
  assert.ok(readings.before.trigger.x >= 0 && readings.before.trigger.right <= 390, 'trigger inside 0..390');
  assert.deepEqual([readings.before.triggerRole.tag, readings.before.triggerRole.ariaExpanded,
    readings.before.triggerRole.title], ['BUTTON', 'false', null]);
  assert.doesNotMatch(readings.before.cardText, /Skald|Summaries|World State|Wizard/);

  await trigger.tap();
  const dialog = page.getByRole('dialog');
  await dialog.waitFor();
  await settle();
  readings.open = {
    dialogs: await dialog.count(),
    text: await dialog.textContent(),
    // The browser's computed accessible name, resolved by Playwright's
    // accessibility engine rather than read off aria-labelledby by hand.
    namedDialogs: await page.getByRole('dialog', { name: 'required-missing', exact: true }).count(),
    ariaSnapshot: await dialog.ariaSnapshot(),
    insideCard: await dialog.evaluate(el => document.getElementById('set-keys').contains(el)),
    dialog: box(await dialog.boundingBox()),
    triggerExpanded: await trigger.getAttribute('aria-expanded'),
    scrollWidth: await page.evaluate(() => document.documentElement.scrollWidth),
    style: await dialog.evaluate(el => { const s = getComputedStyle(el);
      return { width: s.width, maxWidth: s.maxWidth, background: s.backgroundColor, color: s.color,
        border: `${s.borderTopStyle} ${s.borderTopWidth} ${s.borderTopColor}`, font: `${s.fontSize} ${s.fontFamily}`,
        letterSpacing: s.letterSpacing, padding: s.padding }; }),
  };
  assert.equal(readings.open.dialogs, 1);
  assert.equal(readings.open.text, 'Skald · Summaries');
  assert.equal(readings.open.namedDialogs, 1);
  assert.match(readings.open.ariaSnapshot, /^- dialog "required-missing"/);
  assert.equal(readings.open.insideCard, false);
  assert.equal(readings.open.triggerExpanded, 'true');
  assert.ok(readings.open.dialog.x >= 0 && readings.open.dialog.right <= 390, 'dialog inside 0..390');
  assert.ok(readings.open.scrollWidth <= 390, 'no horizontal page scroll');
  await page.screenshot({ path: resolve(evidence, 'seat-popover-390.png') });

  // Tap outside the dialog on a non-interactive point of the page.
  const outside = { x: 195, y: Math.min(readings.open.dialog.bottom + 120, 700) };
  readings.outsideTarget = await page.evaluate(({ x, y }) => {
    const el = document.elementFromPoint(x, y);
    return { x, y, tag: el?.tagName, className: el?.className?.toString() ?? null,
      interactive: Boolean(el?.closest('button, a, input, select, textarea, [role="button"], [tabindex]')) };
  }, outside);
  assert.equal(readings.outsideTarget.interactive, false);
  await page.touchscreen.tap(outside.x, outside.y);
  await dialog.waitFor({ state: 'detached' });
  readings.closed = { dialogs: await page.getByRole('dialog').count(),
    triggerExpanded: await trigger.getAttribute('aria-expanded') };
  assert.deepEqual(readings.closed, { dialogs: 0, triggerExpanded: 'false' });

  // A key no seat needs gets no trigger and no disclosure.
  const optional = page.getByTestId('key-row-optional-absent');
  readings.optional = {
    triggers: await page.getByTestId('key-seats-trigger-optional-absent').count(),
    namedButtons: await optional.getByRole('button', { name: 'optional-absent', exact: true }).count(),
    nameTitle: await optional.locator('.key-provider-name').getAttribute('title'),
    nameTag: await optional.locator('.key-provider-name').evaluate(el => el.tagName),
  };
  assert.deepEqual(readings.optional, { triggers: 0, namedButtons: 0, nameTitle: null, nameTag: 'SPAN' });

  readings.fixtureTransport = await page.evaluate(() => window.fixtureTransport);
  assert.equal(readings.fixtureTransport.some(t => t.method !== 'GET' && t.method !== 'HEAD'), false);
  assert.deepEqual(errors, []);
  assert.deepEqual(requests, []);
  console.log(`390x844 touch: seat popover opened on a tap (${readings.open.text}), stayed inside the viewport, closed on an outside tap; optional row has no trigger; ${errors.length} page errors, ${requests.length} HTTP requests`);
} finally {
  writeFileSync(resolve(evidence, 'seat-readback.json'),
    JSON.stringify({ productionCss: cssName, readings, errors, requests }, null, 2) + '\n');
  await browser.close();
}
