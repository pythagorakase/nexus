/** Repeat the exact fourth-clarification control, never an acceptance bypass. */
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const root = process.cwd(), scratch = process.env.STATE_SURFACES_SCRATCH;
if (!scratch?.includes('/scratchpad/777-S2/after-review-r4/')) throw new Error('Order scratch required');
mkdirSync(scratch, { recursive: true });
const require = createRequire(resolve(root, 'ui/package.json'));
const { chromium } = require('playwright');
const { decodePng, foreground } = await import(pathToFileURL(resolve(root, 'ui/scripts/state-surfaces/png.mjs')));
const browser = await chromium.launch({ headless: true });
const errors = [], requests = [], comparisons = [];
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const fixture = resolve(scratch, '../probe/fixture.html');
try {
  const page = await browser.newPage({ viewport: { width: 1200, height: 900 }, deviceScaleFactor: 4, colorScheme: 'dark', reducedMotion: 'reduce' });
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (/^https?:/.test(r.url())) requests.push(r.url()); });
  await page.route(/^https?:/, r => r.abort());
  await page.goto(pathToFileURL(fixture).href);
  const settled = () => page.evaluate(async () => {
    await new Promise(requestAnimationFrame);
    for (;;) {
      const running = document.getAnimations().filter(a => a.playState === 'running');
      if (!running.length) return;
      await Promise.all(running.map(a => a.finished.catch(() => {})));
    }
  });
  const props = el => el.evaluate(n => {
    const s = getComputedStyle(n), row = n.closest('.key-row'), status = n.closest('.key-status');
    return { visibility: s.visibility, display: s.display, opacity: s.opacity, fill: s.fill, stroke: s.stroke,
      color: s.color, backgroundColor: s.backgroundColor, boxShadow: s.boxShadow, filter: s.filter, textShadow: s.textShadow,
      descendants: [...n.children].map(c => ({ visibility: getComputedStyle(c).visibility, fill: getComputedStyle(c).fill, stroke: getComputedStyle(c).stroke })),
      rowOpacity: getComputedStyle(row).opacity, rowHover: row.matches(':hover'), focusWithin: row.matches(':focus-within'),
      statusFilter: getComputedStyle(status).filter, running: document.getAnimations().filter(a => a.playState === 'running').length,
      dpr: devicePixelRatio, box: JSON.stringify(n.getBoundingClientRect().toJSON()) };
  });
  for (const theme of ['veil', 'gilded', 'vector']) {
    await page.evaluate(t => window.renderSurfaces(t, 'key', 'sea', false, 'required'), theme);
    await page.getByTestId('key-verify-verified').click();
    await page.locator('.key-glyph-verified').waitFor();
    await page.mouse.move(0, 0); await page.locator('body').click({ position: { x: 1, y: 1 } });
    const el = page.locator('[data-testid="key-row-verified"] .key-status svg');
    await el.scrollIntoViewIfNeeded(); await settled();
    for (const variant of ['neutral', 'prescribed', 'tag-status-same-clip', 'diagnostic-ancestor-filter-none']) {
      let causal;
      if (variant === 'diagnostic-ancestor-filter-none') {
        // Causal probe only: never written to product CSS or used for acceptance.
        causal = await page.addStyleTag({ content: '.key-status.verified { filter: none !important; }' });
      }
      for (let repeat = 1; repeat <= (variant === 'prescribed' ? 3 : 1); repeat++) {
        await settled(); const before = await props(el), box = await el.boundingBox();
        const painted = await page.screenshot({ clip: box });
        const id = `${theme}-${variant}-${repeat}`;
        const tagged = variant === 'tag-status-same-clip' ? page.locator('[data-testid="key-row-verified"] .key-status') : el;
        await tagged.evaluate((n, id) => n.setAttribute('data-control-capture', id), id);
        const selector = `[data-control-capture="${id}"]`;
        const rule = variant === 'neutral' ? `${selector} { --control-diagnostic: 1; }` :
          `${selector}, ${selector} * { fill: transparent !important; stroke: transparent !important; background-color: transparent !important; color: transparent !important; box-shadow: none !important; filter: none !important; text-shadow: none !important; }`;
        const style = await page.addStyleTag({ content: rule });
        const during = await props(el), control = await page.screenshot({ clip: box });
        await style.evaluate(n => n.remove()); await tagged.evaluate(n => n.removeAttribute('data-control-capture'));
        const a = decodePng(painted), b = decodePng(control), counts = new Map(); let maskSize = 0;
        for (let i = 0; i < a.pixels.length; i += a.channels) {
          if (a.pixels.subarray(i, i + a.channels).equals(b.pixels.subarray(i, i + b.channels))) continue;
          maskSize++; const rgb = Array.from(a.pixels.subarray(i, i + 3)).join(','); counts.set(rgb, (counts.get(rgb) ?? 0) + 1);
        }
        const histogram = [...counts].map(([rgb, count]) => ({ rgb: rgb.split(',').map(Number), count }))
          .sort((a, b) => b.count - a.count || a.rgb[0] - b.rgb[0] || a.rgb[1] - b.rgb[1] || a.rgb[2] - b.rgb[2]);
        let measured; try { measured = foreground(painted, control, `${theme}/${variant}/${repeat}`); }
        catch (e) { measured = { error: e.message }; }
        if (before.box !== during.box || during.visibility !== 'visible' || during.dpr !== 4 || during.running)
          throw new Error(`${id}: control changed conditions`);
        for (const prop of ['display', 'opacity', 'rowOpacity', 'rowHover', 'focusWithin'])
          if (before[prop] !== during[prop]) throw new Error(`${id}: control changed ${prop}`);
        if (variant === 'neutral' && maskSize !== 0) throw new Error(`${id}: neutral style changed pixels`);
        if (['prescribed', 'tag-status-same-clip'].includes(variant) &&
          (!measured.error?.includes('weak foreground mask') || histogram[0].count / maskSize >= .30))
          throw new Error(`${id}: expected repeated floor rejection`);
        if (variant === 'diagnostic-ancestor-filter-none' && measured.error)
          throw new Error(`${id}: glow-free causal probe unexpectedly failed`);
        if (variant !== 'neutral' &&
          ([during.fill, during.stroke, during.color, during.backgroundColor].some(v => v !== 'rgba(0, 0, 0, 0)') ||
          [during.boxShadow, during.filter, during.textShadow].some(v => v !== 'none') ||
          during.descendants.some(d => d.visibility !== 'visible' || d.fill !== 'rgba(0, 0, 0, 0)' || d.stroke !== 'rgba(0, 0, 0, 0)')))
          throw new Error(`${id}: paint suppression was not applied`);
        const names = {};
        for (const [phase, bytes] of [['painted', painted], ['control', control]]) {
          names[phase] = `${id}-${phase}.png`; writeFileSync(resolve(scratch, names[phase]), bytes);
        }
        const result = { theme, variant, repeat, names, rule, before, during, box, maskSize,
          modeFraction: maskSize ? histogram[0].count / maskSize : null, histogram: histogram.slice(0, 8), measured,
          hashes: { painted: hash(painted), control: hash(control) } };
        comparisons.push(result);
        console.log(`${id}: mask=${maskSize}; mode=${result.modeFraction}; ${measured.error ? 'FAIL' : 'PASS'}`);
      }
      if (causal) await causal.evaluate(n => n.remove());
    }
  }
  for (const theme of ['veil', 'gilded', 'vector']) {
    const repeats = comparisons.filter(c => c.theme === theme && c.variant === 'prescribed');
    if (repeats.some(c => JSON.stringify(c.hashes) !== JSON.stringify(repeats[0].hashes)))
      throw new Error(`${theme}: repeated captures differ`);
  }
  if (errors.length || requests.length) throw new Error(JSON.stringify({ errors, requests }));
  writeFileSync(resolve(scratch, 'diagnostic.json'), JSON.stringify({ chromium: browser.version(), fixtureHash: hash(readFileSync(fixture)), errors, requests, comparisons }, null, 2) + '\n');
  console.log(`Repeated prescribed comparisons=${comparisons.filter(c => c.variant === 'prescribed').length}; errors=${errors.length}; networkRequests=${requests.length}`);
} finally { await browser.close(); }
