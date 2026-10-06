import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdirSync, readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { fixtureBuild, inputs } from './state-surfaces/inputs.mjs';
import { foreground } from './state-surfaces/png.mjs';
import { mediaConditions } from './state-surfaces/media.mjs';
import { START, roots, token, domain, themeTokens } from './state-surfaces/domain.mjs';

const ui = resolve(import.meta.dirname, '..'), root = resolve(ui, '..');
const scratch = process.env.STATE_SURFACES_SCRATCH;
if (!scratch) throw new Error('Set STATE_SURFACES_SCRATCH to the order-specific directory');
const deadline = setTimeout(() => { console.error('Capture command exceeded its 589-second bound'); process.exit(1); }, 589000);
deadline.unref();
const partial = ['STATE_SURFACES_CONDITION', 'STATE_SURFACES_THEME',
  'STATE_SURFACES_GROUP', 'STATE_SURFACES_PROBE'].some(key => process.env[key]);
if (partial && !process.env.STATE_SURFACES_OUTPUT)
  throw new Error('Filtered/probe captures require STATE_SURFACES_OUTPUT in scratch; they cannot replace the acceptance receipt');
mkdirSync(scratch, { recursive: true });
const require = createRequire(resolve(ui, 'package.json'));
const { build: viteBuild } = require('vite');
const { chromium } = require('playwright');
const bundle = await fixtureBuild(ui), fingerprint = await inputs(ui, bundle);
if (process.argv.includes('--assemble')) {
  const shards = readdirSync(resolve(scratch, 'shards')).filter(p => p.endsWith('.json')).sort().map(p => JSON.parse(readFileSync(resolve(scratch, 'shards', p), 'utf8')));
  if (!shards.length) throw new Error('No capture shards');
  const merged = { ...shards[0], conditions: {}, proof: { ...shards[0].proof, renderCount: 0, wallSeconds: 0, acceptanceComplete: true, matchedMedia: {}, shards: [] } };
  for (const shard of shards) {
    if (JSON.stringify(shard.inputs) !== JSON.stringify(fingerprint) || JSON.stringify(shard.media) !== JSON.stringify(merged.media) || shard.proof.failure)
      throw new Error('Stale, failed, or incompatible capture shard; run npm --prefix ui run resolve-state-surfaces');
    for (const [id, data] of Object.entries(shard.conditions)) {
      if (merged.conditions[id] || Object.keys(data).sort().join() !== 'Gilded,Vector,Veil') throw new Error(`Duplicate/incomplete shard ${id}`);
      merged.conditions[id] = data;
    }
    Object.assign(merged.proof.matchedMedia, shard.proof.matchedMedia);
    merged.proof.renderCount += shard.proof.renderCount;
    merged.proof.wallSeconds += shard.proof.wallSeconds;
    merged.proof.shards.push({ conditions: Object.keys(shard.conditions), renders: shard.proof.renderCount, wallSeconds: shard.proof.wallSeconds });
  }
  const ids = merged.media.variants.map(v => v.id);
  if (ids.some(id => !merged.conditions[id]) || Object.keys(merged.conditions).length !== ids.length) throw new Error('Incomplete media inventory');
  merged.conditions = Object.fromEntries(ids.map(id => [id, merged.conditions[id]]));
  const output = process.env.STATE_SURFACES_OUTPUT ?? resolve(ui, 'client/src/state-surfaces.resolved.json');
  writeFileSync(output, JSON.stringify(merged) + '\n');
  console.log(`Resolved painted state surfaces: renders=${merged.proof.renderCount}; wall=${merged.proof.wallSeconds.toFixed(3)}s (sum of bounded capture shards); Chromium ${fingerprint.chromium}; Playwright ${fingerprint.playwright}`);
  console.log(`Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; ${ids.length} media conditions; file://; network aborted; requests=0; errors=0`);
  console.log(`Wrote ${output}; module graph=${fingerprint.moduleGraph.length} inputs; SHA-256 ${fingerprint.sha256}`);
  process.exit(0);
}
writeFileSync(resolve(scratch, 'fixture.js'), bundle.outputFiles[0].contents);
const started = performance.now();
process.chdir(ui);
const built = await viteBuild({ configFile: resolve(ui, 'vite.config.ts'), logLevel: 'error',
  build: { outDir: resolve(scratch, 'production-build'), emptyOutDir: true } });
process.chdir(root);
const css = built.output.filter(o => o.type === 'asset' && o.fileName.endsWith('.css')).map(o => o.source).join('\n');
if (!css) throw new Error('Production Vite build emitted no CSS');
writeFileSync(resolve(scratch, 'production.css'), css);
const media = mediaConditions(css);
if (media.unsupported.length) throw new Error(`Unemulatable media/container preludes: ${media.unsupported.join('; ')}`);
const html = resolve(scratch, 'fixture.html');
writeFileSync(html, `<!doctype html><meta charset="utf-8"><style>${css}</style><div id="root"></div><script src="fixture.js"></script>`);
const base = execFileSync('git', ['show', `${START}:ui/client/src/index.css`], { cwd: root, encoding: 'utf8' });
const shipped = readFileSync(resolve(ui, 'client/src/index.css'), 'utf8');
const browser = await chromium.launch({ headless: true });
let renderCount = 0;
const progress = setInterval(() => console.log(`Painted capture progress: renders=${renderCount}; wall=${((performance.now()-started)/1000).toFixed(3)}s`), 45000);
const errors = [], requests = [];
const results = { inputs: fingerprint, media, conditions: {}, proof: { minimumMaskPixels: 16,
  measurement: 'painted/paint-suppressed control foreground mask; mean in linear sRGB over changed device pixels; visibility and layout retained',
  stylesheet: 'production Vite build emitted CSS, production order', pageErrors: errors, networkRequests: requests } };
let activeConditions = 0; const queue = [];
async function acquire() { if (activeConditions >= 4) await new Promise(r => queue.push(r)); activeConditions++; }
function release() { activeConditions--; queue.shift()?.(); }
try {
  await Promise.all(media.variants.filter(c => !process.env.STATE_SURFACES_CONDITION || process.env.STATE_SURFACES_CONDITION.split(',').includes(c.id)).map(async condition => {
    await acquire();
    try {
    results.conditions[condition.id] = {};
    await Promise.all(['Veil', 'Gilded', 'Vector'].filter(t => !process.env.STATE_SURFACES_THEME || t === process.env.STATE_SURFACES_THEME).map(async theme => {
    const page = await browser.newPage(condition);
    if (condition.media) await page.emulateMedia({ media: condition.media });
    const screenshot = box => page.screenshot({ clip: box });
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => { if (/^https?:/.test(r.url())) requests.push(r.url()); });
    await page.route(/^https?:/, route => route.abort());
    await page.goto(pathToFileURL(html).href);
    const matchedMedia = await page.evaluate(preludes => Object.fromEntries(preludes.map(p => [p, matchMedia(p.slice(6)).matches])), media.preludes);
    results.proof.matchedMedia ??= {}; results.proof.matchedMedia[condition.id] = matchedMedia;
    // Finite transitions/animations finish. Infinite animations have no finished
    // promise: pause the actual browser effect at its start and trough, separately.
    const settled = async () => page.evaluate(async ({ phase }) => {
      await new Promise(requestAnimationFrame);
      for (;;) {
        const all = document.getAnimations();
        for (const a of all) if (a.effect?.getTiming().iterations === Infinity) {
          a.pause(); a.currentTime = Number(a.effect.getTiming().duration) * (phase ?? 0);
        }
        // The whole document is a conservative superset of the surface, its
        // ancestors and overlapping siblings (including portalled tooltips).
        const running = all.filter(a => a.playState === 'running');
        if (!running.length) return;
        await Promise.all(running.map(a => a.finished.catch(() => {})));
      }
    }, { phase: condition.animationPhase });
    async function reset() {
      await page.mouse.move(0, 0);
      await page.locator('body').click({ position: { x: 1, y: 1 } });
      await settled();
    }
    async function keyboardFocus(selector) {
      // Click body resets the browser's sequential navigation starting point.
      await reset();
      for (let tabs = 1; tabs <= 100; tabs++) {
        await page.keyboard.press('Tab');
        if (await page.locator(selector).evaluate(n => n === document.activeElement)) return tabs;
      }
      throw new Error(`Measurement failure ${selector}: Tab did not reach target`);
    }
    async function sample(selector, action, label, tooltipExpected) {
      const el = page.locator(selector);
      await el.scrollIntoViewIfNeeded();
      // Held unarmed hover schedules delayed opening; click/leave cancels it.
      // Tab opens immediately, and the trigger's blur may close it again.
      // captureValues resolves that immediate final state once for all values.
      if (tooltipExpected === 'open') {
        await page.locator('.lm-quant[data-state="delayed-open"],.lm-quant[data-state="instant-open"]').waitFor();
        await page.getByRole('tooltip').waitFor();
      } else {
        await page.getByRole('tooltip').waitFor({ state: 'hidden' });
      }
      await settled();
      const settleCriteria = {
        tooltipExpected,
        tooltipState: await page.locator('.lm-quant').count()
          ? await page.locator('.lm-quant').getAttribute('data-state') : null,
        tooltipPresent: await page.getByRole('tooltip').count() > 0,
        animations: 'all document animations finished; infinite effects paused at the declared condition phase',
        scope: 'entire document, including surface, ancestors and overlapping/portalled siblings',
        animationPhase: condition.animationPhase ?? null,
        pseudoClasses: 'matched hover/focus-visible read back after the driving action',
      };
      const box = await el.boundingBox();
      if (!box || !box.width || !box.height) throw new Error(`Measurement failure ${label}: empty clip`);
      if (await page.evaluate(() => devicePixelRatio) !== 4) throw new Error('Measurement failure: device scale is not 4');
      const pseudos = await el.evaluate(n => ({ hover: n.matches(':hover'), focusVisible: n.matches(':focus-visible'),
        pinHover: n.closest('.map-pin')?.matches(':hover') ?? false,
        ancestorHover: n.closest('.key-row,.lm-quant,.map-place-row')?.matches(':hover') ?? false,
        focusWithin: n.closest('.key-row,.lm-quant,.map-place-row')?.matches(':focus-within') ?? false }));
      const painted = await screenshot(box);
      // Suppress only this tagged subtree's paint. Visibility, geometry and
      // opacity compositing remain identical to the painted capture.
      const captureId = `surface-${renderCount}`;
      await el.evaluate((n, id) => n.setAttribute('data-control-capture', id), captureId);
      const controlStyle = await page.addStyleTag({ content: `[data-control-capture="${captureId}"], [data-control-capture="${captureId}"] * { fill: transparent !important; stroke: transparent !important; background-color: transparent !important; color: transparent !important; }` });
      await settled();
      const control = await screenshot(box);
      await controlStyle.evaluate(n => n.remove());
      await el.evaluate(n => n.removeAttribute('data-control-capture'));
      await settled();
      renderCount++;
      let measured;
      try { measured = foreground(painted, control, label); }
      catch (error) {
        writeFileSync(resolve(scratch, 'measurement-failure-painted.png'), painted);
        writeFileSync(resolve(scratch, 'measurement-failure-control.png'), control);
        writeFileSync(resolve(scratch, 'measurement-failure.json'), JSON.stringify({ label, selector, box, action, pseudos, error: error.message }, null, 2));
        throw error;
      }
      if (Math.abs(measured.width - box.width * 4) > 4 || Math.abs(measured.height - box.height * 4) > 4) throw new Error(`Measurement failure ${label}: PNG is not at device scale 4`);
      const target = await el.evaluate(n => {const t=n.closest('.lm-trash') ?? n.closest('.key-row')?.querySelector('input') ?? n; return {hover:t.matches(':hover'), focusVisible:t.matches(':focus-visible')};});
      const stateAttributes = await el.evaluate(n => ({ mapState: n.closest('[data-map-state]')?.getAttribute('data-map-state') ?? null, keyNeed: n.closest('.key-row')?.classList.contains('optional') ? 'optional' : n.closest('.key-row') ? 'required' : null, armed: n.closest('.lm-trash')?.getAttribute('aria-pressed') ?? null }));
      const animationsRunning = await page.evaluate(() => document.getAnimations().filter(a => a.playState === 'running').length);
      return { ...measured, selector, box, action, pseudos, target, stateAttributes, animationsRunning, settleCriteria };
    }
      const result = { shipped: {}, before: {}, candidates: {}, reachability: {} };
      results.conditions[condition.id][theme] = result;
      console.log(`Resolving ${condition.id}/${theme}…`);
      const baseline = themeTokens(base, theme), now = themeTokens(shipped, theme);
      let overlay;
      async function mount(mode, terrain = 'sea', over = false, need = 'required') {
        await page.evaluate(args => window.renderSurfaces(...args), [theme.toLowerCase(), mode, terrain, over, need]);
        await page.locator('[data-testid="nexus-layout"]').waitFor();
        if (mode === 'memory') await page.locator('.mem-fill').waitFor();
        if (mode === 'delete') { await page.locator('[data-testid="lm-toggle-fixture"]').click(); await page.locator('.lm-trash').waitFor(); }
        if (mode === 'key') {
          await page.locator('[data-testid="key-verify-verified"]').click();
          await page.locator('.key-glyph-verified').waitFor();
        }
        if (mode === 'map') {
          await page.locator('[data-testid="map-svg"]').waitFor();
          await page.locator('[data-testid="map-zone-1"]').click();
        }
        await reset();
        if (mode === 'key') {
          const capture = `${condition.id}-${theme}-key-${need}.png`;
          result.reachability[need] = { capture, rows: await page.locator('.key-row').evaluateAll(rows => rows.map(n => ({id:n.getAttribute('data-testid'), need:n.classList.contains('optional') ? 'optional':'required'}))) };
          if (condition.id === 'default' && theme === 'Veil') await page.screenshot({path:resolve(scratch,capture)});
        }
      }
      async function select(id) {
        await page.locator(`[data-testid="map-place-row-${id}"]`).click();
        const dialog = page.getByTestId('map-place-dialog'); await dialog.waitFor();
        await dialog.getByRole('button', { name: 'Close', exact: true }).click();
        await dialog.waitFor({ state: 'hidden' }); await reset();
      }
      async function captureValues(group, state, context, selector, action) {
        const prop = token(group, state), values = domain(base, theme, group, state);
        if (group === 'map') {
          const actual = await page.locator(selector).evaluate(n => n.closest('[data-map-state]')?.getAttribute('data-map-state'));
          if (actual !== state) {
            const failure = { label: `${condition.id}/${theme}/${context}/${state}`, selector, action, expected: state, actual,
              hovered: await page.locator(selector).evaluate(n => ({pin: n.closest('.map-pin')?.matches(':hover') ?? false, row: n.closest('.map-place-row')?.matches(':hover') ?? false})) };
            writeFileSync(resolve(scratch, 'context-failure.json'), JSON.stringify(failure, null, 2));
            await page.screenshot({path:resolve(scratch, 'context-failure.png')});
            throw new Error(`Measurement failure ${failure.label}: real action produced ${actual}, expected ${state}; ${JSON.stringify(failure.hovered)}`);
          }
        }
        result.candidates[prop] ??= {};
        await settled();
        const tooltipExpected = context.startsWith('delete/ready-exceeds/') &&
          (state === 'unarmed' && context.endsWith('hover') || context.endsWith('focus-visible') &&
            await page.locator('.lm-quant').getAttribute('data-state') !== 'closed') ? 'open' : 'closed';
        for (const [phase, value] of [['shipped', now[prop]], ['before', baseline[roots[group][state]]], ...(process.env.STATE_SURFACES_PROBE ? [] : values.map(v => ['candidate', v]))]) {
          if (phase === 'before') {
            // Historical global declarations, including the pre-anchor colors,
            // are rendered on the same accepted geometry and production CSS.
            overlay = await page.addStyleTag({ content: `html.dark${theme === 'Veil' ? '' : `.theme-${theme.toLowerCase()}`} { ${Object.entries(baseline).filter(([p]) => p.startsWith('--')).map(([p,v]) => `${p}:${v};`).join('')} }` });
          }
          if (phase === 'shipped') {
            // Measure the production cascade, including media root overrides.
            await page.evaluate(p => document.documentElement.style.removeProperty(p), prop);
          } else {
            await page.evaluate(({ prop, value }) => document.documentElement.style.setProperty(prop, value), { prop, value: roots[group][state] === '--destructive' && phase === 'before' ? `hsl(${value})` : value });
          }
          const measured = await sample(selector, action, `${condition.id}/${theme}/${phase}/${context}/${state}/${value}`, tooltipExpected);
          if (phase === 'candidate') { result.candidates[prop][value] ??= {}; result.candidates[prop][value][context] = measured; }
          else { result[phase][context] ??= {}; result[phase][context][state] = measured; }
          if (overlay) { await overlay.evaluate(n => n.remove()); overlay = null; }
        }
        await page.evaluate(p => document.documentElement.style.removeProperty(p), prop);
      }
      if (!process.env.STATE_SURFACES_GROUP || process.env.STATE_SURFACES_GROUP === 'memory') for (const state of Object.keys(roots.memory)) {
        await mount('memory', 'sea', state === 'over');
        await captureValues('memory', state, 'memory/fill', '.mem-fill', `seed local-model usage ${state}`);
      }
      if (!process.env.STATE_SURFACES_GROUP || process.env.STATE_SURFACES_GROUP === 'delete') for (const row of ['ready', 'ready-exceeds']) {
        await mount('delete', 'sea', row === 'ready-exceeds');
        for (const action of ['rest', 'row-hover', 'button-hover', 'focus-visible']) {
          await reset();
          const button = '.lm-trash';
          const steps = ['expand model family by click'];
          if (action === 'row-hover') { await page.locator('.lm-quant').hover(); steps.push('mouse hover row'); }
          if (action === 'button-hover') { await page.locator(button).hover(); steps.push('mouse hover button'); }
          if (action === 'focus-visible') steps.push(`keyboard Tab ×${await keyboardFocus(button)}`);
          for (const state of Object.keys(roots.delete)) {
            if (state === 'armed') {
              // Space preserves Tab focus; a real click establishes button hover.
              const hit = await page.locator(button).boundingBox();
              if (!hit) throw new Error(`Measurement failure delete/${row}/${action}: missing button hit box`);
              await page.mouse.click(hit.x + hit.width / 2, hit.y + hit.height / 2);
              if (action === 'rest') await reset();
              if (action === 'row-hover') await page.locator('.lm-quant').hover();
              if (action === 'focus-visible') await keyboardFocus(button);
              await page.waitForFunction(() => document.querySelector('.lm-trash')?.getAttribute('aria-pressed') === 'true');
            }
            await captureValues('delete', state, `delete/${row}/${action}`, `${button} svg`, steps.join('; ') + (state === 'armed' ? '; first click arms; requested hover/Tab restored' : ''));
          }
          // Remount to disarm without a destructive second click or a timer sleep.
          await mount('delete', 'sea', row === 'ready-exceeds');
        }
      }
      if (!process.env.STATE_SURFACES_GROUP || process.env.STATE_SURFACES_GROUP === 'key') for (const need of ['required', 'optional']) {
        await mount('key', 'sea', false, need);
        for (const action of ['rest', 'hover', 'focus-visible']) for (const state of Object.keys(roots.key).filter(s => need === 'required' ? s !== 'optional-absent' : s !== 'required-missing')) {
          const row = `[data-testid="key-row-${state}"]`;
          await reset(); let steps = 'seed status; verified via fixture VERIFY click';
          if (action === 'hover') { await page.locator(row).hover(); steps += '; mouse hover row'; }
          if (action === 'focus-visible') steps += `; keyboard Tab ×${await keyboardFocus(`${row} input`)}`;
          await captureValues('key', state, `key/${need}/${action}`, `${row} .key-status svg`, steps);
        }
      }
      if (!process.env.STATE_SURFACES_GROUP || process.env.STATE_SURFACES_GROUP === 'map') for (const terrain of ['sea', 'land']) {
        await mount('map', terrain);
        await select(1);
        const ids = { rest: 2, current: 4, selected: 1, hovered: 3 };
        for (const [state, id] of Object.entries(ids)) {
          await page.mouse.move(0, 0);
          if (state === 'hovered') await page.locator('[data-testid="map-pin-3"] .map-state-glyph > path[fill="transparent"]').hover();
          for (const part of ['fill', 'ring']) {
            const selector = `[data-testid="map-pin-${id}"] [data-map-part="${part === 'ring' && state !== 'rest' ? 'outline' : 'fill'}"]`;
            await captureValues('map', state, `map/canvas-${terrain}/${part}`, selector, `select Place 1; close dialog; ${state === 'hovered' ? 'mouse hover pin 3' : 'pointer off map'}`);
          }
        }
      }
      if (!process.env.STATE_SURFACES_GROUP || process.env.STATE_SURFACES_GROUP === 'map') {
      await mount('map');
      for (const action of ['rest', 'hover', 'selected-current']) for (const [state, id] of Object.entries({ rest: 2, current: 4, selected: 1 })) {
        await select(action === 'selected-current' && state === 'current' ? 4 : 1);
        if (state === 'hovered') await page.locator('[data-testid="map-pin-3"] .map-state-glyph > path[fill="transparent"]').hover();
        if (action === 'hover') await page.locator(`[data-testid="map-place-row-${id}"]`).hover();
        for (const part of ['fill', 'ring']) {
          const selector = `[data-testid="map-place-row-${id}"] [data-map-part="${part === 'ring' && state !== 'rest' ? 'outline' : 'fill'}"]`;
          await captureValues('map', state, `map/sidebar/${action}/${part}`, selector, `select ${action === 'selected-current' && state === 'current' ? 4 : 1}; close dialog; ${action === 'hover' ? 'mouse hover row' : state === 'hovered' ? 'mouse hover pin 3' : 'pointer off row'}`);
        }
      }
      }
      console.log(`Completed ${condition.id}/${theme}; renders=${renderCount}; wall=${((performance.now() - started) / 1000).toFixed(3)}s`);
    await page.close();
    }));
    } finally { release(); }
  }));
  if (errors.length || requests.length) throw new Error(JSON.stringify({ errors, requests }));
  if (browser.version() !== fingerprint.chromium) throw new Error('Chromium version mismatch');
  results.proof.renderCount = renderCount; results.proof.wallSeconds = (performance.now() - started) / 1000;
  results.proof.acceptanceComplete = !partial;
  const output = process.env.STATE_SURFACES_OUTPUT ?? resolve(ui, 'client/src/state-surfaces.resolved.json');
  if (partial && resolve(output) === resolve(ui, 'client/src/state-surfaces.resolved.json'))
    throw new Error('Filtered/probe captures cannot replace the acceptance receipt');
  writeFileSync(output, JSON.stringify(results, null, 2) + '\n');
  console.log(`Resolved painted state surfaces: renders=${renderCount}; wall=${results.proof.wallSeconds.toFixed(3)}s; Chromium ${browser.version()}; Playwright ${fingerprint.playwright}`);
  console.log(`Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; ${Object.keys(results.conditions).length} media conditions; file://; network aborted; requests=${requests.length}; errors=${errors.length}`);
  console.log(`Wrote ${output}; module graph=${fingerprint.moduleGraph.length} inputs; SHA-256 ${fingerprint.sha256}`);
} catch (error) {
  results.proof.renderCount = renderCount;
  results.proof.wallSeconds = (performance.now() - started) / 1000;
  results.proof.acceptanceComplete = false;
  results.proof.failure = error.message;
  writeFileSync(resolve(scratch, 'incomplete-probe.json'), JSON.stringify(results, null, 2) + '\n');
  console.error(`Incomplete painted probe: renders=${renderCount}; wall=${results.proof.wallSeconds.toFixed(3)}s; acceptanceComplete=false`);
  throw error;
} finally { clearInterval(progress); await browser.close(); }
