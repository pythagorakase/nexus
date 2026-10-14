// Key-row hover microverification for the resolver's committed hoverKeyRow helper.
//
// Usage, from any checkout root:
//   STATE_SURFACES_SCRATCH=<scratch>/hover-micro \
//   nice -n 15 node docs/qa/777-shell-ui-bundle/capture-at-b6a704ca/key-hover-micro-v2.mjs [<repo-root>]
//
// <repo-root> defaults to the checkout that holds this script. The fixture is built
// with fixtureBuild and the production Vite CSS, exactly as
// ui/scripts/state-surfaces/tooltip-focus-trace.mjs builds it, into
// STATE_SURFACES_SCRATCH. All HTTP(S) is aborted; fonts come from disk.
// It writes hover-micro.json to STATE_SURFACES_SCRATCH and exits non-zero unless
// all 72 passing cases pass and both planted refusal cases refuse.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const root = resolve(process.argv[2] ?? resolve(import.meta.dirname, '../../../..'));
const ui = resolve(root, 'ui');
if (!process.env.STATE_SURFACES_SCRATCH)
  throw new Error('Set STATE_SURFACES_SCRATCH to the microverification output directory');
const scratch = resolve(process.env.STATE_SURFACES_SCRATCH);
mkdirSync(scratch, { recursive: true });

const source = readFileSync(resolve(ui, 'scripts/resolve-state-surfaces.mjs'), 'utf8');
const start = source.indexOf('    async function hoverKeyRow(selector) {');
const end = source.indexOf('    async function keyboardFocus(selector) {', start);
assert(start >= 0 && end > start, 'hoverKeyRow helper not found in the resolver');
const helper = source.slice(start, end);
// Execute the exact committed helper with the real page closure, not a reimplementation.
const bindHelper = new Function('page', `${helper}\nreturn hoverKeyRow;`);

const require = createRequire(resolve(ui, 'package.json'));
const { build: viteBuild } = require('vite');
const { chromium } = require('playwright');
const { fixtureBuild } = await import(pathToFileURL(resolve(ui, 'scripts/state-surfaces/inputs.mjs')).href);
const bundle = await fixtureBuild(ui);
writeFileSync(resolve(scratch, 'fixture.js'), bundle.outputFiles[0].contents);
const cwd = process.cwd();
process.chdir(ui);
const built = await viteBuild({ configFile: resolve(ui, 'vite.config.ts'), logLevel: 'error',
  build: { outDir: resolve(scratch, 'production-build'), emptyOutDir: true } });
process.chdir(cwd);
const css = built.output.filter(o => o.type === 'asset' && o.fileName.endsWith('.css')).map(o => o.source).join('\n');
if (!css) throw new Error('Production Vite build emitted no CSS');
const html = resolve(scratch, 'fixture.html');
writeFileSync(html, `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>${css}</style><div id="root"></div><script src="fixture.js"></script>`);

const browser = await chromium.launch({ headless: true });
const readings = [], plants = [], errors = [], requests = [];
const deadline = setTimeout(() => { throw new Error('Hover microverification exceeded 300 seconds'); }, 300000);

async function openPage(width, coarse) {
  const page = await browser.newPage({ viewport: { width, height: 900 }, hasTouch: coarse, isMobile: coarse,
    deviceScaleFactor: 4, colorScheme: 'dark', reducedMotion: 'reduce' });
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()); });
  await page.route(/^https?:/, route => route.abort());
  await page.routeWebSocket(/.*/, () => {});
  await page.route('**/fonts/**', route => route.fulfill({
    path: resolve(ui, 'client/public', new URL(route.request().url()).pathname.slice(1)) }));
  await page.goto(pathToFileURL(html).href);
  return page;
}

async function renderKey(page, theme, need) {
  await page.evaluate(({ theme, need }) => window.renderSurfaces(theme, 'key', 'sea', false, need), { theme, need });
  await page.locator('[data-testid="nexus-layout"]').waitFor();
  await page.evaluate(() => document.fonts.ready);
  await page.locator('[data-testid="key-verify-verified"]').click();
  await page.locator('.key-glyph-verified').waitFor();
}

async function reset(page) {
  await page.mouse.move(0, 0);
  await page.locator('body').click({ position: { x: 1, y: 1 } });
}

/** Run one planted case and require the helper to refuse with the named message. */
async function plant(page, label, expected, run) {
  let refusal = null;
  try { await run(); } catch (error) { refusal = error.message; }
  plants.push({ label, expected, refusal });
  assert(refusal !== null, `${label}: helper accepted a planted failure`);
  assert(refusal.includes(expected), `${label}: unexpected refusal ${refusal}`);
}

try {
  for (const [width, coarse] of [[639, false], [639, true], [760, false], [1200, false]]) {
    const page = await openPage(width, coarse);
    const hoverKeyRow = bindHelper(page);
    try {
      for (const theme of ['veil', 'gilded', 'vector']) for (const need of ['required', 'optional']) {
        await renderKey(page, theme, need);
        for (const state of [need === 'required' ? 'required-missing' : 'optional-absent', 'present', 'verified']) {
          await reset(page);
          const selector = `[data-testid="key-row-${state}"]`, row = page.locator(selector);
          await row.hover();
          const centerGlyphHover = await row.locator('.key-status svg').evaluate(n => n.matches(':hover'));
          const point = await hoverKeyRow(selector);
          await page.evaluate(async () => {
            await Promise.all(document.getAnimations().map(a => a.finished.catch(() => {})));
            await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
          });
          const actual = await row.evaluate((n, point) => ({
            point, hitIsRow: document.elementFromPoint(point.x, point.y) === n,
            rowHover: n.matches(':hover'), rowFocusVisible: n.matches(':focus-visible'),
            glyphHover: n.querySelector('.key-status svg').matches(':hover'),
            glyphFocusVisible: n.querySelector('.key-status svg').matches(':focus-visible'),
            controls: [...n.querySelectorAll('button,input,[tabindex]')].map(c => ({ hover: c.matches(':hover'), focusVisible: c.matches(':focus-visible') })),
            opacity: getComputedStyle(n).opacity,
          }), point);
          const label = `${width}/${coarse ? 'coarse' : 'fine'}/${theme}/${need}/${state}`;
          assert.equal(actual.hitIsRow, true, label); assert.equal(actual.rowHover, true, label);
          assert.equal(actual.glyphHover, false, label); assert.equal(actual.glyphFocusVisible, false, label);
          assert.equal(actual.rowFocusVisible, false, label);
          assert(actual.controls.every(c => !c.hover && !c.focusVisible), label);
          assert.equal(actual.opacity, '1', label);
          readings.push({ label, centerGlyphHover, ...actual });
        }
      }
      if ((width === 639 && coarse) || width === 1200) {
        // Planted refusals drive both throw branches of the committed helper.
        await renderKey(page, 'veil', 'required');
        const selector = '[data-testid="key-row-present"]';
        await reset(page);
        await page.evaluate(() => {
          const cover = document.createElement('div');
          cover.id = 'planted-full-cover';
          cover.style.cssText = 'position:fixed;inset:0;z-index:2147483647;background:transparent';
          document.body.append(cover);
        });
        await plant(page, `${width}/${coarse ? 'coarse' : 'fine'}/full-cover-overlay`,
          'no visible empty row background', () => hoverKeyRow(selector));
        await page.evaluate(() => document.getElementById('planted-full-cover').remove());
        await reset(page);
        // A page whose mouse lands on the sampled glyph instead of the chosen background point.
        const glyphPage = {
          locator: (...args) => page.locator(...args),
          mouse: { move: async () => {
            const box = await page.locator(`${selector} .key-status svg`).boundingBox();
            await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
          } },
        };
        await plant(page, `${width}/${coarse ? 'coarse' : 'fine'}/hovered-glyph-readback`,
          'row background hover mismatch', () => bindHelper(glyphPage)(selector));
      }
    } finally { await page.close(); }
  }
  assert.equal(readings.length, 72);
  assert.equal(plants.length, 4);
  assert.deepEqual(errors, []); assert.deepEqual(requests, []);
} finally {
  clearTimeout(deadline); await browser.close();
  writeFileSync(resolve(scratch, 'hover-micro.json'), JSON.stringify({
    scope: '72 reduced-motion key-row cases plus 4 planted refusals, not full painted/color acceptance',
    root, helperSha256: createHash('sha256').update(helper).digest('hex'),
    centerGlyphHover: readings.filter(r => r.centerGlyphHover).length,
    readings, plants, errors, requests }, null, 2) + '\n');
}
console.log(`${readings.length}/72 production-helper row hover cases passed: 639 fine/coarse, 760 fine, 1200 fine; 3 themes; 2 needs; 3 states.`);
console.log(`Old center hit hovered the SVG in ${readings.filter(r => r.centerGlyphHover).length}/72 cases; corrected point in 0/72. Network ${requests.length}; page errors ${errors.length}.`);
for (const p of plants) console.log(`Planted ${p.label}: refused: ${p.refusal}`);
