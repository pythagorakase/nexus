import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { fixtureBuild } from './inputs.mjs';

const ui = resolve(import.meta.dirname, '../..');
const root = resolve(ui, '..');
if (!process.env.STATE_SURFACES_SCRATCH)
  throw new Error('Set STATE_SURFACES_SCRATCH to the trace output directory');
const scratch = resolve(process.env.STATE_SURFACES_SCRATCH);
mkdirSync(scratch, { recursive: true });
const require = createRequire(resolve(ui, 'package.json'));
const { build: viteBuild } = require('vite');
const { chromium } = require('playwright');
const bundle = await fixtureBuild(ui);
writeFileSync(resolve(scratch, 'fixture.js'), bundle.outputFiles[0].contents);
process.chdir(ui);
const built = await viteBuild({ configFile: resolve(ui, 'vite.config.ts'), logLevel: 'error',
  build: { outDir: resolve(scratch, 'production-build'), emptyOutDir: true } });
process.chdir(root);
const css = built.output.filter(o => o.type === 'asset' && o.fileName.endsWith('.css')).map(o => o.source).join('\n');
if (!css) throw new Error('Production Vite build emitted no CSS');
writeFileSync(resolve(scratch, 'production.css'), css);
const html = resolve(scratch, 'fixture.html');
writeFileSync(html, `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>${css}</style><div id="root"></div><script src="fixture.js"></script>`);

const condition = {
  viewport: { width: 1200, height: 900 }, deviceScaleFactor: 4,
  colorScheme: 'dark', reducedMotion: 'reduce', hasTouch: false, isMobile: false,
};
const counts = { rowOpen: 0, trashOpen: 0, outsideClosed: 0 };
const runs = [], pageErrors = [], requests = [];
const browser = await chromium.launch({ headless: true });

/** Finish actual animations and read once; never poll for tooltip state. */
async function readOnce(page) {
  return page.evaluate(async () => {
    const animations = document.getAnimations();
    if (animations.some(a => a.effect?.getTiming().iterations === Infinity))
      throw new Error('Reduced-motion trace still has an infinite animation');
    await Promise.all(animations.map(a => a.finished.catch(() => {})));
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const row = document.querySelector('.lm-quant.exceeds');
    if (!row) throw new Error('Trace lost the exceeds-RAM quant row');
    const state = row.getAttribute('data-state');
    const tooltip = document.querySelector('[role="tooltip"]') !== null;
    const openState = ['delayed-open', 'instant-open'].includes(state);
    return {
      focused: document.activeElement?.getAttribute('data-testid') ?? null,
      focusWithin: row.contains(document.activeElement),
      scrollTop: row.closest('.set-scroller')?.scrollTop ?? null,
      state, tooltip,
      open: tooltip && openState,
      closed: !tooltip && !openState,
    };
  });
}

try {
  for (let run = 1; run <= 50; run++) {
    const page = await browser.newPage(condition);
    try {
      page.on('pageerror', error => pageErrors.push({ run, message: error.message }));
      page.on('request', request => {
        if (/^https?:/.test(request.url())) requests.push({ run, url: request.url() });
      });
      await page.route(/^https?:/, route => route.abort());
      await page.routeWebSocket(/.*/, () => {});
      await page.route('**/fonts/**', route => route.fulfill({
        path: resolve(ui, 'client/public', new URL(route.request().url()).pathname.slice(1)),
      }));
      await page.goto(pathToFileURL(html).href);
      await page.evaluate(() => window.renderSurfaces('veil', 'delete', 'sea', true));
      await page.locator('[data-testid="nexus-layout"]').waitFor();
      await page.evaluate(() => document.fonts.ready);
      await page.getByRole('button', { name: 'Model', exact: true }).click();
      await page.locator('[data-testid="lm-toggle-fixture"]').click();
      const row = page.locator('.lm-quant.exceeds');
      const trash = row.locator('.lm-trash');
      const toggle = page.locator('[data-testid="lm-toggle-fixture"]');
      await trash.waitFor();
      await page.locator('body').click({ position: { x: 1, y: 1 } });
      let tabs = 0;
      let stationaryPrecondition = null;
      while (tabs < 100 && !await row.evaluate(node => node === document.activeElement)) {
        if (await toggle.evaluate(node => node === document.activeElement)) {
          // This trace isolates focus transitions from Radix's scroll dismissal.
          // Make the row visible before Tab, while its preceding toggle has focus.
          await row.evaluate(node => node.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'nearest' }));
          stationaryPrecondition = await row.evaluate(async node => {
            const scroller = node.closest('.set-scroller');
            if (!scroller) throw new Error('Trace lost the settings scroller');
            let previous = scroller.scrollTop, stableFrames = 0;
            for (let frame = 0; frame < 60 && stableFrames < 2; frame++) {
              await new Promise(resolve => requestAnimationFrame(resolve));
              const current = scroller.scrollTop;
              stableFrames = current === previous ? stableFrames + 1 : 0;
              previous = current;
            }
            if (stableFrames < 2) throw new Error('Trace scrolling did not settle');
            const rowBox = node.getBoundingClientRect(), scrollBox = scroller.getBoundingClientRect();
            return { focused: document.activeElement?.getAttribute('data-testid'),
              scrollTop: scroller.scrollTop, stableFrames,
              rowTop: rowBox.top, rowBottom: rowBox.bottom,
              visibleTop: Math.max(0, scrollBox.top), visibleBottom: Math.min(innerHeight, scrollBox.bottom) };
          });
          assert.equal(stationaryPrecondition.focused, 'lm-toggle-fixture');
          assert(stationaryPrecondition.rowTop >= stationaryPrecondition.visibleTop, JSON.stringify(stationaryPrecondition));
          assert(stationaryPrecondition.rowBottom <= stationaryPrecondition.visibleBottom, JSON.stringify(stationaryPrecondition));
        }
        await page.keyboard.press('Tab');
        tabs++;
      }
      assert(await row.evaluate(node => node === document.activeElement), `run ${run}: Tab missed row`);
      assert(stationaryPrecondition, `run ${run}: Tab missed the stationary precondition`);
      const atRow = await readOnce(page);
      assert.equal(atRow.scrollTop, stationaryPrecondition.scrollTop, `run ${run}: row Tab scrolled`);
      await page.keyboard.press('Tab');
      assert(await trash.evaluate(node => node === document.activeElement), `run ${run}: Tab missed trash`);
      const atTrash = await readOnce(page);
      assert.equal(atTrash.scrollTop, stationaryPrecondition.scrollTop, `run ${run}: trash Tab scrolled`);
      await page.keyboard.press('Tab');
      assert(!await row.evaluate(node => node.contains(document.activeElement)), `run ${run}: focus stayed inside row`);
      const outside = await readOnce(page);
      runs.push({ run, tabs, stationaryPrecondition, atRow, atTrash, outside });
      counts.rowOpen += Number(atRow.open);
      counts.trashOpen += Number(atTrash.open);
      counts.outsideClosed += Number(outside.closed);
    } finally {
      await page.close();
    }
  }
} finally {
  await browser.close();
  writeFileSync(resolve(scratch, 'tooltip-focus-trace.json'),
    JSON.stringify({ condition, counts, runs, pageErrors, requests }, null, 2) + '\n');
  console.log(`Tooltip focus trace: ${counts.rowOpen}/50 row open; ${counts.trashOpen}/50 trash open; ${counts.outsideClosed}/50 outside closed`);
}
assert.deepEqual(counts, { rowOpen: 50, trashOpen: 50, outsideClosed: 50 });
assert.deepEqual(pageErrors, []);
assert.deepEqual(requests, []);
