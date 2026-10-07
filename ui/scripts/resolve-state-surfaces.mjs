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
const scratch = process.env.STATE_SURFACES_SCRATCH ?? resolve(root, 'scratchpad/777-S2/after-review-r5/capture');
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
const defaultCondition = media.variants.find(c => c.viewport.width === 1200 && c.viewport.height === 900 && c.reducedMotion === 'reduce' && c.colorScheme === 'dark');
if (!defaultCondition) throw new Error('Media inventory lost the documented default');
const boundSeconds = 589 * (partial ? 1 : Math.ceil(media.variants.length / 4));
const deadline = setTimeout(() => { console.error(`Capture command exceeded its ${boundSeconds}-second bound`); process.exit(1); }, boundSeconds * 1000);
deadline.unref();
// Reuse the test math exactly for the resolver calibration.
const { transformSync } = createRequire(require.resolve('vite'))('esbuild');
const math = transformSync(readFileSync(resolve(ui, 'client/src/state-shades-measurement.ts'), 'utf8'), { loader: 'ts', format: 'esm' }).code;
const { ciede2000, deutanLinearLab } = await import('data:text/javascript;base64,' + Buffer.from(math).toString('base64'));
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
  measurement: 'painted/paint-suppressed control foreground mask; mean in linear sRGB over the core at >=90% maximum linear-sRGB difference; visibility and layout retained',
  coreThreshold: .9, calibration: {},
  stylesheet: 'production Vite build emitted CSS, production order', pageErrors: errors, networkRequests: requests } };
let activeConditions = 0; const queue = [];
async function acquire() { if (activeConditions >= 4) await new Promise(r => queue.push(r)); activeConditions++; }
function release() { activeConditions--; queue.shift()?.(); }
async function renderInventory(condition, theme, calibrating = false) {
    const page = await browser.newPage(condition);
    try {
    if (condition.media) await page.emulateMedia({ media: condition.media });
    const screenshot = box => page.screenshot({ clip: box });
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => { if (/^https?:/.test(r.url())) requests.push(r.url()); });
    await page.route(/^https?:/, route => route.abort());
    await page.routeWebSocket(/.*/, () => {}); // in-page idle narrative transport; never connects to a server
    await page.route('**/fonts/**', route => route.fulfill({ path: resolve(ui, 'client/public', new URL(route.request().url()).pathname.slice(1)) }));
    await page.goto(pathToFileURL(html).href);
    const matchedMedia = await page.evaluate(preludes => Object.fromEntries(preludes.map(p => [p, matchMedia(p.slice(6)).matches])), media.preludes.filter(p => p.startsWith('media ') && !media.excluded.some(e => e.prelude === p)));
    for (const [feature, value] of Object.entries(condition.features))
      if (!await page.evaluate(([f, v]) => matchMedia(`(${f}: ${v})`).matches, [feature, value]))
        throw new Error(`Unemulatable media feature (${feature}: ${value}) in ${media.preludes.filter(p => p.includes(feature)).join('; ')}`);
    results.proof.matchedMedia ??= {}; results.proof.matchedMedia[condition.id] = matchedMedia;
    // Finite transitions/animations finish. Infinite animations have no finished
    // promise: pause the actual browser effect at its start and trough, separately.
    // Preserve the existing Playwright waitFor settle bound (30 seconds),
    // capped by the enclosing capture command's derived bound.
    const settleBoundMs = Math.min(30_000, boundSeconds * 1000);
    const settled = async (tooltipExpected) => page.evaluate(async ({ phase, tooltipExpected, settleBoundMs }) => {
      const started = performance.now();
      await new Promise(requestAnimationFrame);
      for (;;) {
        const all = document.getAnimations();
        for (const a of all) if (a.effect?.getTiming().iterations === Infinity) {
          a.pause(); a.currentTime = Number(a.effect.getTiming().duration) * (phase ?? 0);
        }
        // The whole document is a conservative superset of the surface, its
        // ancestors and overlapping siblings (including portalled tooltips).
        const running = all.filter(a => a.playState === 'running');
        if (running.length) await Promise.race([
          Promise.all(running.map(a => a.finished.catch(() => {}))),
          new Promise(r => setTimeout(r, Math.max(0, settleBoundMs - (performance.now() - started)))),
        ]);
        const tooltipState = document.querySelector('.lm-quant')?.getAttribute('data-state') ?? null;
        const tooltipPresent = !!document.querySelector('[role="tooltip"]');
        const matched = !document.getAnimations().some(a => a.playState === 'running') &&
          (tooltipExpected === undefined || (tooltipPresent === (tooltipExpected === 'open') &&
            (tooltipExpected !== 'open' || ['delayed-open', 'instant-open'].includes(tooltipState))));
        if (matched || performance.now() - started >= settleBoundMs)
          return { tooltipState, tooltipPresent, matched, settleWaitMs: performance.now() - started };
        await new Promise(requestAnimationFrame);
      }
    }, { phase: condition.animationPhase, tooltipExpected, settleBoundMs });
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
    async function dismissFocusTooltip(label) {
      const readback = async () => {
        const state = await page.evaluate(() => {
          const button = document.querySelector('.lm-trash');
          const tree = document.querySelector('#root').cloneNode(true);
          // Only the tooltip's own presence/state/description may change.
          tree.querySelectorAll('.lm-quant').forEach(n => {
            n.removeAttribute('data-state'); n.removeAttribute('aria-describedby');
          });
          return { signature: JSON.stringify({ dom: tree.outerHTML,
            dialogs: [...document.querySelectorAll('[role="dialog"],[role="alertdialog"]')].map(n => n.outerHTML),
            inputs: [...document.querySelectorAll('input,select,textarea')].map(n => [n.value, n.checked]),
          }), focusVisible: button === document.activeElement && button.matches(':focus-visible'),
          expanded: button.closest('.lm-group').querySelector('[aria-expanded]')?.getAttribute('aria-expanded') === 'true',
          armed: button.getAttribute('aria-pressed') };
        });
        return { ...state, signature: createHash('sha256').update(state.signature).digest('hex') };
      };
      const before = await readback();
      const escapePressed = await page.locator('[role="tooltip"]').count() > 0;
      if (escapePressed) await page.keyboard.press('Escape');
      const after = await readback();
      if (!before.focusVisible || !before.expanded || JSON.stringify(before) !== JSON.stringify(after)) {
        const prefix = resolve(scratch, `dismissal-failure-${label.replace(/[^a-zA-Z0-9-]/g, '_')}`);
        await page.screenshot({ path: `${prefix}.png` });
        writeFileSync(`${prefix}.json`, JSON.stringify({ label, condition, escapePressed, before, after }, null, 2));
        throw new Error(`Measurement failure ${label}: tooltip dismissal changed focus/expansion/DOM state; PNG/readback: ${prefix}`);
      }
      return { escapePressed, before, after };
    }
    async function sample(selector, action, label, tooltipExpected, tooltipDismissal) {
      const el = page.locator(selector);
      await el.scrollIntoViewIfNeeded();
      const paintedSettle = await settled(tooltipExpected);
      const settleCriteria = {
        tooltipExpected,
        tooltipState: paintedSettle.tooltipState,
        tooltipPresent: paintedSettle.tooltipPresent,
        animations: 'all document animations finished; infinite effects paused at the declared condition phase',
        scope: 'entire document, including surface, ancestors and overlapping/portalled siblings',
        animationPhase: condition.animationPhase ?? null,
        pseudoClasses: 'matched hover/focus-visible read back after the driving action',
        ...(tooltipDismissal ? { tooltipDismissal } : {}),
      };
      const box = await el.boundingBox();
      if (!box || !box.width || !box.height) throw new Error(`Measurement failure ${label}: empty clip`);
      if (await page.evaluate(() => devicePixelRatio) !== 4) throw new Error('Measurement failure: device scale is not 4');
      const pseudos = await el.evaluate(n => ({ hover: n.matches(':hover'), focusVisible: n.matches(':focus-visible'),
        pinHover: (n.closest('.map-pin') ?? document.querySelector(`[data-testid="map-pin-${n.closest('.map-place-row')?.getAttribute('data-testid')?.split('-').at(-1)}"]`))?.matches(':hover') ?? false,
        ancestorHover: n.closest('.key-row,.lm-quant,.map-place-row')?.matches(':hover') ?? false,
        focusWithin: n.closest('.key-row,.lm-quant,.map-place-row')?.matches(':focus-within') ?? false,
        rowFocusVisible: n.closest('.key-row,.lm-quant,.map-place-row')?.matches(':focus-visible') ?? false,
        controls: [...(n.closest('.key-row,.lm-quant,.map-place-row')?.querySelectorAll('button,input,[tabindex]') ?? [])]
          .map(c => ({ hover: c.matches(':hover'), focusVisible: c.matches(':focus-visible') })) }));
      const painted = await screenshot(box);
      // Suppress only this tagged subtree's paint. Visibility, geometry and
      // opacity compositing remain identical to the painted capture.
      const captureId = `surface-${renderCount}`;
      await el.evaluate((n, id) => n.setAttribute('data-control-capture', id), captureId);
      const subtree = [`[data-control-capture="${captureId}"]`, `[data-control-capture="${captureId}"] *`];
      const selectors = subtree.flatMap(s => [s, `${s}::before`, `${s}::after`]);
      const transparent = ['fill', 'stroke', 'background-color', 'color', 'border-color', 'outline-color',
        'text-decoration-color', 'column-rule-color', 'caret-color', 'stop-color', 'flood-color', 'lighting-color'];
      const controlStyle = await page.addStyleTag({ content: `${selectors.join(',')} { ${transparent.map(p => `${p}: transparent !important;`).join('')} background-image: none !important; }` });
      const controlSettle = await settled(tooltipExpected);
      const control = await screenshot(box);
      await controlStyle.evaluate(n => n.remove());
      await el.evaluate(n => n.removeAttribute('data-control-capture'));
      await settled();
      const settleWaitMs = paintedSettle.settleWaitMs + controlSettle.settleWaitMs;
      settleCriteria.captures = { painted: paintedSettle, control: controlSettle };
      if (!paintedSettle.matched || !controlSettle.matched) {
        const name = label.replace(/[^a-zA-Z0-9-]/g, '_');
        const prefix = resolve(scratch, `settle-failure-${name}`);
        writeFileSync(`${prefix}-painted.png`, painted);
        writeFileSync(`${prefix}-control.png`, control);
        writeFileSync(`${prefix}.json`, JSON.stringify({ label, condition, selector, box, action, pseudos,
          settleBoundMs, settleWaitMs, settleCriteria }, null, 2));
        throw new Error(`Measurement failure ${label}: tooltip did not settle ${tooltipExpected} within ${settleBoundMs}ms before both captures; PNGs/readback: ${prefix}`);
      }
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
      const paint = await el.evaluate(n => {
        let effectiveOpacity = 1;
        for (let ancestor = n; ancestor; ancestor = ancestor.parentElement) {
          effectiveOpacity *= Number(getComputedStyle(ancestor).opacity);
          if (ancestor.id === 'root') break;
        }
        return { effectiveOpacity, mapPart: n.getAttribute('data-map-part') };
      });
      let captures;
      if (calibrating) {
        const name = label.replace(/[^a-zA-Z0-9-]/g, '_');
        captures = { painted: `calibration/${name}-painted.png`, control: `calibration/${name}-control.png` };
        mkdirSync(resolve(scratch, 'calibration'), { recursive: true });
        writeFileSync(resolve(scratch, captures.painted), painted);
        writeFileSync(resolve(scratch, captures.control), control);
      }
      return { ...measured, ...paint, selector, box, action, pseudos, target, stateAttributes, animationsRunning, settleCriteria, settleWaitMs, ...(captures ? { captures } : {}) };
    }
      const result = { shipped: {}, before: {}, candidates: {}, reachability: {}, fonts: {} };
      const calibration = { condition: condition.id, pigments: {}, samples: {}, groups: {}, requiredPairs: [],
        tolerances: { opaque: 1, translucent: 2.5, backdrop: 1 }, passed: false };
      if (calibrating) results.proof.calibration[theme] = calibration;
      else results.conditions[condition.id][theme] = result;
      console.log(`Resolving ${condition.id}/${theme}…`);
      const baseline = themeTokens(base, theme), now = themeTokens(shipped, theme);
      let overlay;
      async function mount(mode, terrain = 'sea', over = false, need = 'required') {
        await page.evaluate(args => window.renderSurfaces(...args), [theme.toLowerCase(), mode, terrain, over, need]);
        await page.locator('[data-testid="nexus-layout"]').waitFor();
        await page.evaluate(() => document.fonts.ready);
        result.fonts[mode] = await page.evaluate(() => [...document.fonts].map(f => ({ family: f.family, status: f.status })));
        if (result.fonts[mode].some(f => f.status === 'error') || !result.fonts[mode].some(f => f.status === 'loaded'))
          throw new Error(`Font input failure ${condition.id}/${theme}/${mode}: ${JSON.stringify(result.fonts[mode])}`);
        if (mode === 'memory') await page.locator('.mem-fill').waitFor();
        if (mode === 'delete') { await page.getByRole('button', { name: 'Model', exact: true }).click(); await page.locator('[data-testid="lm-toggle-fixture"]').click(); await page.locator('.lm-trash').waitFor(); }
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
          if (condition.id === defaultCondition.id && theme === 'Veil') await page.screenshot({path:resolve(scratch,capture)});
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
          state === 'unarmed' && context.endsWith('hover') ? 'open' : 'closed';
        const tooltipDismissal = context === 'delete/ready-exceeds/focus-visible' ?
          await dismissFocusTooltip(`${condition.id}/${theme}/${context}/${state}`) : undefined;
        if (tooltipDismissal) action += tooltipDismissal.escapePressed ? '; keyboard Escape dismisses tooltip' : '; tooltip already dismissed';
        const restState = { memory: 'normal', delete: 'unarmed', map: 'rest', key: 'present' }[group];
        const pigment = now[token(group, restState)];
        if (calibrating) {
          calibration.pigments[group] = pigment;
          await page.evaluate(({ props, pigment }) => props.forEach(p => document.documentElement.style.setProperty(p, pigment)),
            { props: Object.keys(roots[group]).map(s => token(group, s)), pigment });
        }
        for (const [phase, value] of calibrating ? [['calibration', pigment]] : [['shipped', now[prop]], ['before', baseline[roots[group][state]]], ...(process.env.STATE_SURFACES_PROBE ? [] : values.map(v => ['candidate', v]))]) {
          if (phase === 'before') {
            // Historical global declarations, including the pre-anchor colors,
            // are rendered on the same accepted geometry and production CSS.
            overlay = await page.addStyleTag({ content: `html.dark${theme === 'Veil' ? '' : `.theme-${theme.toLowerCase()}`} { ${Object.entries(baseline).filter(([p]) => p.startsWith('--')).map(([p,v]) => `${p}:${v};`).join('')} }` });
          }
          if (phase === 'shipped') {
            // Measure the production cascade, including media root overrides.
            await page.evaluate(p => document.documentElement.style.removeProperty(p), prop);
          } else if (!calibrating) {
            await page.evaluate(({ prop, value }) => document.documentElement.style.setProperty(prop, value), { prop, value: roots[group][state] === '--destructive' && phase === 'before' ? `hsl(${value})` : value });
          }
          const measured = await sample(selector, action, `${condition.id}/${theme}/${phase}/${context}/${state}/${value}`, tooltipExpected, tooltipDismissal);
          if (calibrating) { calibration.samples[context] ??= {}; calibration.samples[context][state] = measured; }
          else if (phase === 'candidate') { result.candidates[prop][value] ??= {}; result.candidates[prop][value][context] = measured; }
          else { result[phase][context] ??= {}; result[phase][context][state] = measured; }
          if (overlay) { await overlay.evaluate(n => n.remove()); overlay = null; }
        }
        await page.evaluate(props => props.forEach(p => document.documentElement.style.removeProperty(p)),
          calibrating ? Object.keys(roots[group]).map(s => token(group, s)) : [prop]);
      }
      if (calibrating || !process.env.STATE_SURFACES_GROUP || process.env.STATE_SURFACES_GROUP === 'memory') for (const state of Object.keys(roots.memory)) {
        await mount('memory', 'sea', state === 'over');
        await captureValues('memory', state, 'memory/fill', '.mem-fill', `seed local-model usage ${state}`);
      }
      if (calibrating || !process.env.STATE_SURFACES_GROUP || process.env.STATE_SURFACES_GROUP === 'delete') for (const row of ['ready', 'ready-exceeds']) {
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
      if (calibrating || !process.env.STATE_SURFACES_GROUP || process.env.STATE_SURFACES_GROUP === 'key') for (const need of ['required', 'optional']) {
        await mount('key', 'sea', false, need);
        for (const action of ['rest', 'hover', 'focus-visible']) for (const state of Object.keys(roots.key).filter(s => need === 'required' ? s !== 'optional-absent' : s !== 'required-missing')) {
          const row = `[data-testid="key-row-${state}"]`;
          await reset(); let steps = 'seed status; verified via fixture VERIFY click';
          if (action === 'hover') { await page.locator(row).hover(); steps += '; mouse hover row'; }
          if (action === 'focus-visible') steps += `; keyboard Tab ×${await keyboardFocus(`${row} input`)}`;
          await captureValues('key', state, `key/${need}/${action}`, `${row} .key-status svg`, steps);
        }
      }
      if (calibrating || !process.env.STATE_SURFACES_GROUP || process.env.STATE_SURFACES_GROUP === 'map') for (const terrain of ['sea', 'land']) {
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
      if (calibrating || !process.env.STATE_SURFACES_GROUP || process.env.STATE_SURFACES_GROUP === 'map') {
      await mount('map');
      for (const action of ['rest', 'hover', 'selected-current']) for (const [state, id] of Object.entries({ rest: 2, current: 4, selected: 1, ...(action === 'hover' ? {} : { hovered: 3 }) })) {
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
      if (calibrating) {
        for (const [context, samples] of Object.entries(calibration.samples)) {
          const group = context.split('/')[0];
          calibration.groups[group] ??= { opaqueMaximum: 0, translucentMaximum: 0, pairs: [], skippedPairs: [] };
          const record = calibration.groups[group], states = Object.keys(samples);
          for (let i = 0; i < states.length; i++) for (let j = i + 1; j < states.length; j++) {
            const pair = [states[i], states[j]], [a, b] = pair.map(s => samples[s]);
            const witness = { context, states: pair, captures: pair.map(s => samples[s].captures) };
            if (a.mapPart !== b.mapPart) { record.skippedPairs.push({ ...witness, reason: 'part-distinct' }); continue; }
            const opacity = a.effectiveOpacity === 1 && b.effectiveOpacity === 1 ? 'opaque' : 'translucent';
            const backdropDelta = ciede2000(deutanLinearLab(a.controlMeanLinear), deutanLinearLab(b.controlMeanLinear));
            if (opacity === 'translucent' && backdropDelta > 1) {
              record.skippedPairs.push({ ...witness, reason: 'backdrop-distinct', backdropDelta }); continue;
            }
            const delta = ciede2000(deutanLinearLab(a.meanLinear), deutanLinearLab(b.meanLinear));
            record.pairs.push({ ...witness, opacity, delta, backdropDelta });
            record[`${opacity}Maximum`] = Math.max(record[`${opacity}Maximum`], delta);
          }
        }
        const failure = Object.values(calibration.groups).flatMap(g => g.pairs)
          .find(p => p.delta > calibration.tolerances[p.opacity]);
        if (failure) {
          throw new Error(`Calibration failure ${theme}/${failure.context}/${failure.states.join('/')}: ${failure.opacity} deutan delta=${failure.delta} > ${calibration.tolerances[failure.opacity]}; PNGs: ${failure.captures.map(c => resolve(scratch, c.painted)).join('; ')}`);
        }
        const required = [
          ...['required', 'optional'].map(need => ({ context: `key/${need}/rest`, states: ['present', 'verified'], opacity: need === 'optional' ? 'translucent' : 'opaque' })),
          ...['sea', 'land'].flatMap(terrain => ['current', 'selected', 'hovered'].map(state => ({ context: `map/canvas-${terrain}/fill`, states: ['rest', state], opacity: 'opaque' }))),
          ...['current', 'selected', 'hovered'].map(state => ({ context: 'map/sidebar/rest/fill', states: ['rest', state], opacity: 'opaque' })),
        ];
        for (const wanted of required) {
          const pair = calibration.groups[wanted.context.split('/')[0]].pairs.find(p => p.context === wanted.context && p.states.join('/') === wanted.states.join('/'));
          calibration.requiredPairs.push({ ...wanted, opacity: pair?.opacity ?? null });
          if (!pair || pair.opacity !== wanted.opacity)
            throw new Error(`Calibration non-vacuity failure ${theme}/${wanted.context}/${wanted.states.join('/')}: required ${wanted.opacity} pair, got ${pair?.opacity ?? 'skipped'}; effective opacities=${wanted.states.map(s => calibration.samples[wanted.context][s].effectiveOpacity).join('/')}`);
        }
        calibration.passed = true;
        console.log(`Calibration ${theme}: ${JSON.stringify(Object.fromEntries(Object.entries(calibration.groups).map(([g, r]) => [g, { opaqueMaximum: r.opaqueMaximum, translucentMaximum: r.translucentMaximum, skippedPairs: r.skippedPairs.length }])))}; passed`);
      }
    } finally { await page.close(); }
}
try {
  // Every regeneration calibrates the full inventory at the documented default
  // before any expensive candidate capture, even for filtered/probe runs.
  for (const theme of ['Veil', 'Gilded', 'Vector']) await renderInventory(defaultCondition, theme, true);
  await Promise.all(media.variants.filter(c => !process.env.STATE_SURFACES_CONDITION || process.env.STATE_SURFACES_CONDITION.split(',').some(id => id === c.id || id === 'default' && c.id === defaultCondition.id)).map(async condition => {
    await acquire();
    try {
      results.conditions[condition.id] = {};
      await Promise.all(['Veil', 'Gilded', 'Vector'].filter(t => !process.env.STATE_SURFACES_THEME || t === process.env.STATE_SURFACES_THEME).map(theme => renderInventory(condition, theme)));
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
} finally { clearTimeout(deadline); clearInterval(progress); await browser.close(); }
