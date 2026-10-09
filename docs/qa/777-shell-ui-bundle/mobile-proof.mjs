import assert from 'node:assert/strict';
import { writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const root = '/Users/pythagor/.codex/worktrees/resume-shell-ui/nexus';
const ui = resolve(root, 'ui');
const evidence = resolve(root, 'docs/qa/777-shell-ui-bundle');
const html = resolve(import.meta.dirname, 'trace-green/fixture.html');
const require = createRequire(resolve(ui, 'package.json'));
const { chromium } = require('playwright');
const browser = await chromium.launch({ headless: true });
const errors = [], requests = [], readings = {};
const page = await browser.newPage({ viewport: { width: 390, height: 844 },
  hasTouch: true, isMobile: true, deviceScaleFactor: 1,
  colorScheme: 'dark', reducedMotion: 'reduce' });
try {
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (/^https?:/.test(request.url())) requests.push(request.url());
  });
  await page.route(/^https?:/, route => route.abort());
  await page.routeWebSocket(/.*/, () => {});
  await page.route('**/fonts/**', route => route.fulfill({
    path: resolve(ui, 'client/public', new URL(route.request().url()).pathname.slice(1)),
  }));
  await page.goto(pathToFileURL(html).href);
  readings.viewport = await page.evaluate(() => ({ innerWidth, innerHeight,
    coarseNarrow: matchMedia('(max-width: 760px) and (pointer: coarse)').matches }));
  assert.equal(readings.viewport.innerWidth, 390);
  assert.equal(readings.viewport.coarseNarrow, true);
  for (const [name, mode] of [['map', 'map'], ['settings', 'key']]) {
    await page.evaluate(mode => window.renderSurfaces('veil', mode, 'sea', false), mode);
    await page.locator('[data-testid="nexus-layout"]').waitFor();
    await page.evaluate(() => document.fonts.ready);
    if (name === 'settings') await page.getByRole('button', { name: 'API Keys', exact: true }).click();
    await page.evaluate(async () => {
      await Promise.all(document.getAnimations().map(a => a.finished.catch(() => {})));
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    });
    readings[name] = await page.evaluate(() => {
      const nav = document.querySelector('nav[aria-label="Primary navigation"]');
      const main = document.querySelector('main.nexus-content');
      const box = nav.getBoundingClientRect();
      return { nav: { x: box.x, y: box.y, width: box.width, height: box.height, bottom: box.bottom },
        followsMain: Boolean(main.compareDocumentPosition(nav) & Node.DOCUMENT_POSITION_FOLLOWING),
        viewportBottom: innerHeight, display: getComputedStyle(nav).display };
    });
    assert.equal(readings[name].nav.bottom, readings[name].viewportBottom);
    assert.equal(readings[name].followsMain, true);
    assert.notEqual(readings[name].display, 'none');
    await page.screenshot({ path: resolve(evidence, `narrow-${name}.png`) });
    writeFileSync(resolve(evidence, `narrow-${name}-accessibility.txt`), await page.locator('body').ariaSnapshot());
  }
  const input = page.locator('.key-row input').first();
  await input.focus();
  readings.keyboardFocused = await page.locator('nav[aria-label="Primary navigation"]').evaluate(nav => getComputedStyle(nav).display);
  assert.equal(readings.keyboardFocused, 'none');
  await input.blur();
  readings.keyboardBlurred = await page.locator('nav[aria-label="Primary navigation"]').evaluate(nav => getComputedStyle(nav).display);
  assert.notEqual(readings.keyboardBlurred, 'none');
  readings.fixtureTransport = await page.evaluate(() => window.fixtureTransport);
  assert.equal(readings.fixtureTransport.some(r => r.method === 'POST'), false);
  assert.deepEqual(errors, []);
  assert.deepEqual(requests, []);
  console.log('390x844 coarse/mobile: map and settings bottom rail, DOM order, focus hiding and blur restoration passed');
} finally {
  writeFileSync(resolve(evidence, 'narrow-readback.json'), JSON.stringify({ readings, errors, requests }, null, 2) + '\n');
  await browser.close();
}
