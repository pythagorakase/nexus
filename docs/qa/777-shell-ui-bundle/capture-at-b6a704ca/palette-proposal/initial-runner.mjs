import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const root = '/Users/pythagor/.codex/worktrees/resume-shell-ui/nexus';
const ui = resolve(root, 'ui');
const scratch = '/tmp/nexus-777-shell-ui-4ae8b8d2';
const out = resolve(scratch, 'capture-v2/palette-proposal');
mkdirSync(out, { recursive: true });
const fixture = resolve(scratch, 'capture-v2/batch-9/fixture.html');
const require = createRequire(resolve(ui, 'package.json'));
const { chromium } = require('playwright');
const browser = await chromium.launch({ headless: true });
const requests = [], errors = [], readings = [];
const deadline = setTimeout(() => { throw new Error('Palette proposal exceeded 180 seconds'); }, 180000);
try {
  for (const theme of ['gilded', 'vector']) {
    const property = theme === 'gilded' ? '--state-map-rest' : '--state-map-hovered';
    const values = theme === 'gilded'
      ? ['hsl(30 60% 60%)', 'hsl(30 70% 50%)']
      : ['hsl(190 90% 40%)', 'hsl(190 80% 40%)'];
    for (const scene of [
      { id: '1023-motion-start', width: 1023, reducedMotion: 'no-preference', phase: 0 },
      { id: '1200-normal', width: 1200, reducedMotion: 'reduce', phase: 0 },
    ]) {
      const page = await browser.newPage({ viewport: { width: scene.width, height: 900 },
        deviceScaleFactor: 4, colorScheme: 'dark', reducedMotion: scene.reducedMotion,
        hasTouch: false, isMobile: false });
      try {
        page.on('pageerror', error => errors.push(error.message));
        page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()); });
        await page.route(/^https?:/, route => route.abort());
        await page.routeWebSocket(/.*/, () => {});
        await page.route('**/fonts/**', route => route.fulfill({ path: resolve(ui, 'client/public', new URL(route.request().url()).pathname.slice(1)) }));
        await page.goto(pathToFileURL(fixture).href);
        await page.evaluate(theme => window.renderSurfaces(theme, 'map', 'sea'), theme);
        await page.locator('[data-testid="nexus-layout"]').waitFor();
        await page.evaluate(() => document.fonts.ready);
        await page.getByTestId('map-place-row-1').click();
        const dialog = page.getByTestId('map-place-dialog');
        await dialog.waitFor();
        await dialog.getByRole('button', { name: 'Close', exact: true }).click();
        await dialog.waitFor({ state: 'hidden' });
        await page.mouse.move(0, 0);
        if (theme === 'vector') await page.locator('[data-testid="map-pin-3"] .map-state-glyph > path[fill="transparent"]').hover();
        let priorGeometry;
        for (const [index, value] of values.entries()) {
          await page.evaluate(({ property, value }) => document.documentElement.style.setProperty(property, value), { property, value });
          await page.evaluate(async phase => {
            for (const animation of document.getAnimations()) {
              if (animation.effect?.getTiming().iterations === Infinity) {
                animation.pause(); animation.currentTime = Number(animation.effect.getTiming().duration) * phase;
              }
            }
            await Promise.all(document.getAnimations().filter(a => a.playState === 'running').map(a => a.finished));
            await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
          }, scene.phase);
          const actual = await page.evaluate(({ property }) => ({
            innerWidth, fine: matchMedia('(pointer: fine)').matches,
            reduced: matchMedia('(prefers-reduced-motion: reduce)').matches,
            property: getComputedStyle(document.documentElement).getPropertyValue(property).trim(),
            pins: [1, 2, 3, 4].map(id => {
              const pin = document.querySelector(`[data-testid="map-pin-${id}"]`);
              const rect = pin.getBoundingClientRect();
              return { id, state: pin.getAttribute('data-map-state'), hover: pin.matches(':hover'),
                box: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
                parts: [...pin.querySelectorAll('[data-map-part]')].map(n => ({ part: n.getAttribute('data-map-part'), fill: getComputedStyle(n).fill, stroke: getComputedStyle(n).stroke })) };
            }),
            animationsRunning: document.getAnimations().filter(a => a.playState === 'running').length,
          }), { property });
          assert.equal(actual.innerWidth, scene.width); assert.equal(actual.fine, true);
          assert.equal(actual.reduced, scene.reducedMotion === 'reduce');
          assert.equal(actual.property, value); assert.equal(actual.animationsRunning, 0);
          assert.equal(actual.pins.find(p => p.id === 2).state, 'rest');
          assert.equal(actual.pins.find(p => p.id === 4).state, 'current');
          assert.equal(actual.pins.find(p => p.id === 1).state, 'selected');
          assert.equal(actual.pins.find(p => p.id === 3).state, theme === 'vector' ? 'hovered' : 'rest');
          const geometry = actual.pins.map(({ parts, ...pin }) => pin);
          if (index === 1) assert.deepEqual(geometry, priorGeometry);
          priorGeometry = geometry;
          const name = `${theme}-${scene.id}-${index === 0 ? 'before' : 'proposed'}.png`;
          await page.screenshot({ path: resolve(out, name) });
          readings.push({ theme, scene, property, value, file: name, ...actual });
        }
      } finally { await page.close(); }
    }
  }
  assert.deepEqual(requests, []); assert.deepEqual(errors, []); assert.equal(readings.length, 8);
} finally {
  clearTimeout(deadline); await browser.close();
  writeFileSync(resolve(out, 'readings.json'), JSON.stringify({
    scope: 'Visual proposal only; scratch document CSS override, no product change or final capture acceptance',
    inputFingerprint: '4b8a9bbd8b880dc12ff8a534e7ef819eaa72fe376f0e28a8a295f9754d976fe7',
    fixtureSha256: createHash('sha256').update(readFileSync(fixture)).digest('hex'),
    readings, requests, errors,
  }, null, 2) + '\n');
}
console.log('Eight matched proposal screenshots captured; same geometry/state before and after; requests0/errors0. No product edit.');
