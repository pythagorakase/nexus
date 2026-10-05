/** Regenerate the offline shade oracle using the browser's actual CSS cascade. */
import { readFileSync, writeFileSync, mkdirSync, mkdtempSync, rmSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { resolve, dirname } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build as viteBuild } from 'vite';
import { chromium } from 'playwright';
import postcss from 'postcss';
import { inputs, conditions } from './state-surfaces/inputs.mjs';
const ui = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const scratch = process.env.STATE_SURFACES_SCRATCH ?? mkdtempSync(resolve(tmpdir(), 'nexus-state-surfaces-'));
mkdirSync(scratch, { recursive: true });
const { build } = createRequire(createRequire(import.meta.url).resolve('vite'))('esbuild');
await build({ entryPoints: [resolve(ui, 'scripts/state-surfaces/fixture.tsx')], bundle: true,
  outfile: resolve(scratch, 'fixture.js'), platform: 'browser', format: 'iife', jsx: 'automatic',
  alias: { '@': resolve(ui, 'client/src'), '@shared': resolve(ui, 'shared') },
  plugins: [{ name: 'real-settings-card', setup(b) { b.onLoad({ filter: /\/SettingsPane\.tsx$/ }, args => ({
    contents: readFileSync(args.path, 'utf8') + '\nexport { SettingsCard };\n', loader: 'tsx', resolveDir: dirname(args.path),
  })); } }],
});
// Vite runs the same PostCSS/Tailwind pipeline as the production bundle. No server.
const result = await viteBuild({ configFile: false, root: resolve(ui, 'client'), logLevel: 'error',
  build: { write: false, rollupOptions: { input: resolve(ui, 'scripts/state-surfaces/styles.css') } } });
const css = result.output.find(o => o.type === 'asset' && o.fileName.endsWith('.css'))?.source;
if (!css) throw new Error('Vite emitted no stylesheet');
const html = resolve(scratch, 'fixture.html');
writeFileSync(html, `<!doctype html><meta charset="utf-8"><style>${css}</style><style>.nexus-shell{height:auto;min-height:900px}.nexus-main{min-height:750px}.mappane{height:350px}.settings-pane-v2{height:650px}</style><div id="root"></div><script src="fixture.js"></script>`);
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: conditions.viewport, colorScheme: conditions.colorScheme, reducedMotion: conditions.reducedMotion });
  const errors = [], requests = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (r.url().includes('/api/')) requests.push(r.url()); });
  await page.route(/^https?:/, route => route.abort());
  await page.goto(pathToFileURL(html).href);
  const themes = {}, candidateColors = {};
  const base = execFileSync('git', ['show', '8ccd3008a48bdf8115232667399868e2bdf66f93:ui/client/src/index.css'], { cwd: ui, encoding: 'utf8' });
  const roots = { map: {rest:'--bronze',current:'--brass-bright',selected:'--brass',hovered:'--brass-bright'}, key: {'optional-absent':'--fg-dim','required-missing':'--bronze',present:'--fg-muted',verified:'--brass'}, memory:{normal:'--brass',over:'--bronze'}, delete:{unarmed:'--fg-muted',armed:'--destructive'} };
  // Candidate pigments use Chromium's color serialization too. This keeps
  // domain evaluation at the same precision as getComputedStyle measurements.
  for (const theme of ['Veil', 'Gilded', 'Vector']) {
    const tokens = {};
    postcss.parse(base).walkRules(rule => {
      if (rule.parent?.type === 'root' && (rule.selector === ':root' || rule.selector === '.dark' ||
        (theme !== 'Veil' && rule.selector.includes(`.dark.theme-${theme.toLowerCase()}`))))
        rule.walkDecls(d => { tokens[d.prop] = d.value; });
    });
    const values = new Set();
    for (const root of Object.values(roots).flatMap(Object.values)) {
      let [h, s, l] = tokens[root].match(/([\d.]+)\s+([\d.]+)%\s+([\d.]+)%/).slice(1).map(Number);
      if (theme === 'Veil' && root === '--brass') [h, s, l] = [330.2439024390244, 50.20408163265306, 48.03921568627451];
      if (theme === 'Veil' && ['--brass', '--brass-bright'].includes(root)) h = 330.2439024390244;
      for (const sat of new Set(root === '--destructive' ? [80, 90, 100] : [s, Math.min(100, s + 10), Math.min(100, s + 20)]))
        for (const light of new Set(root === '--destructive' ? [50, 55, 60, 65] : [l, 30, 40, 50, 60, 70]))
          values.add(`hsl(${h} ${sat}% ${light}%)`);
    }
    candidateColors[theme] = await page.evaluate(values => {
      const probe = document.createElement('span'); document.body.appendChild(probe);
      const result = {};
      for (const value of values) { probe.style.color = value; result[value] = getComputedStyle(probe).color; }
      probe.remove(); return result;
    }, [...values]);
  }
  // Baseline pigments are inserted on the current real geometry. The baseline
  // sidebar had no rings; its historical ring-context sample is opaque.
  const baseline = base.replace(/@import[^;]+;/g, '') + '\n.dark, .dark.theme-gilded, .dark.theme-vector { ' + Object.entries(roots).flatMap(([surface, states]) => Object.entries(states).map(([state, root]) => `--state-${surface === 'memory' ? 'mem' : surface}-${state === 'optional-absent' ? 'absent' : state === 'required-missing' ? 'missing' : state}: ${root === '--destructive' ? `hsl(var(${root}))` : `var(${root})`};`)).join(' ') + ' }\n.map-place-dot .map-state-ring { opacity: 1 !important; }';
  // Read colors and each ancestor's group opacity/background exactly as the
  // engine reports them. An opaque background inside a dimmed group is not a
  // stopping point: that group still needs its parent backdrop.
  async function read(selector, property, terrain, wash) {
    return page.locator(selector).evaluate((node, args) => {
      const alpha = c => c === 'transparent' ? 0 : c.startsWith('rgba(') ? Number(c.split(',').at(-1).replace(')', '')) : c.includes('/') ? Number(c.split('/').at(-1).replace(')', '')) : 1;
      const chain = [];
      // An opaque leaf can still be inside an outer opacity group. Find the
      // outermost group before choosing the opaque stopping backdrop.
      let outerOpacityGroup = null;
      for (let n = node; n; n = n.parentElement)
        if (Number(getComputedStyle(n).opacity) < 1) outerOpacityGroup = n;
      let outsideGroups = outerOpacityGroup === null;
      for (let n = node; n; n = n.parentElement) {
        const s = getComputedStyle(n);
        const layer = { tag: n.tagName.toLowerCase(), classes: n.getAttribute('class') ?? '', opacity: s.opacity,
          backgroundColor: s.backgroundColor, backgroundImage: s.backgroundImage, stackingContext: Number(s.opacity) < 1 };
        if (args.terrain && n.matches('.mappane-svg')) {
          const painted = n.querySelector(args.terrain === 'sea' ? '[fill="var(--map-sea)"]' : '[fill="var(--map-land)"]');
          if (!painted) throw new Error('Missing production terrain');
          layer.underlay = { color: getComputedStyle(painted).fill, opacity: getComputedStyle(painted).opacity, source: `SVG ${args.terrain}` };
        }
        if (n.matches('.nexus-content') && s.backgroundImage !== 'none') {
          // The order measures both endpoints of the radial wash, not a
          // location-dependent raster pixel. The stop is browser-resolved.
          const stop = s.backgroundImage.match(/(?:rgba?|color)\([^)]*\)/)?.[0];
          if (!stop) throw new Error(`Missing browser gradient stop: ${s.backgroundImage}`);
          layer.underlay = { color: args.wash === 0 ? 'rgba(0, 0, 0, 0)' : stop, opacity: '1', source: 'radial gradient endpoint' };
        } else if (s.backgroundImage !== 'none') throw new Error(`Unmeasured background image ${s.backgroundImage}`);
        chain.push(layer);
        if (outsideGroups && alpha(s.backgroundColor) === 1 && Number(s.opacity) === 1) break;
        if (n === outerOpacityGroup) outsideGroups = true;
      }
      return { property: args.property, color: getComputedStyle(node).getPropertyValue(args.property), chain };
    }, { property, terrain, wash });
  }
  for (const theme of ['Veil', 'Gilded', 'Vector']) {
    themes[theme] = {};
    for (const phase of ['shipped', 'before']) {
      console.log(`Resolving ${theme}/${phase}…`);
      const overlay = phase === 'before' ? await page.addStyleTag({ content: baseline }) : null;
      await page.evaluate(t => window.renderSurfaces(t), theme.toLowerCase());
      await page.locator('[data-testid="map-svg"]').waitFor();
      for (const row of ['ready', 'ready-exceeds']) await page.locator(`[data-delete="${row}"] [data-testid="lm-toggle-fixture"]`).click();
      await page.locator('[data-testid="map-zone-1"]').click();
      const contexts = {};
      const reset = async () => { await page.mouse.move(0, 0); await page.evaluate(() => document.activeElement?.blur()); };
      const interaction = async (selector, name) => {
        await reset();
        if (name === 'hover') await page.locator(selector).hover();
        if (name === 'focus') await page.locator(selector + (selector.includes('data-key') ? ' input' : ' .lm-trash')).focus();
        // Wait for production opacity transitions to reach the requested state.
        await page.waitForTimeout(170);
      };
      contexts['memory/fill'] = {};
      for (const state of ['normal', 'over']) contexts['memory/fill'][state] = await read(`[data-memory="${state}"] .mem-fill`, 'background-color');
      for (const row of ['ready', 'ready-exceeds']) for (const action of ['rest', 'hover', 'focus']) {
        contexts[`delete/${row}/${action}`] = {};
        const button = `[data-delete="${row}"] .lm-trash`;
        await interaction(`[data-delete="${row}"] .lm-quant`, action);
        await page.waitForTimeout(220);
        contexts[`delete/${row}/${action}`].unarmed = await read(button, 'color');
        await page.locator(button).dispatchEvent('click'); // first click only; native button is enabled
        await page.waitForFunction(sel => document.querySelector(sel)?.getAttribute('aria-pressed') === 'true', button);
        await page.waitForTimeout(220);
        contexts[`delete/${row}/${action}`].armed = await read(button, 'color');
        await page.waitForFunction(sel => document.querySelector(sel)?.getAttribute('aria-pressed') === 'false', button);
      }
      for (const need of ['required', 'optional']) for (const action of ['rest', 'hover', 'focus']) {
        contexts[`key/${need}/${action}`] = {};
        for (const state of Object.keys(roots.key)) {
          const row = `[data-key="${need}/${state}"]`;
          await interaction(row, action);
          contexts[`key/${need}/${action}`][state] = await read(`${row} .key-status svg`, 'stroke');
        }
      }
      const selectPlace = async id => {
        await page.locator(`[data-testid="map-place-row-${id}"]`).click();
        // Selection opens MapPlaceDialog. Use its existing close button and
        // wait for dismissal before driving the next sidebar context.
        const dialog = page.getByTestId('map-place-dialog');
        await dialog.waitFor({ state: 'visible' });
        await dialog.getByRole('button', { name: 'Close', exact: true }).click();
        await dialog.waitFor({ state: 'hidden' });
      };
      await reset();
      await selectPlace(1);
      await page.locator('[data-testid="map-pin-3"]').dispatchEvent('pointerover');
      await page.locator('[data-testid="map-pin-3"] [data-map-state="hovered"]').waitFor();
      const ids = { rest: 2, current: 4, selected: 1, hovered: 3 };
      for (const terrain of ['sea', 'land']) for (const part of ['fill', 'ring']) {
        contexts[`map/canvas-${terrain}/${part}`] = {};
        for (const [state, id] of Object.entries(ids)) contexts[`map/canvas-${terrain}/${part}`][state] = await read(`[data-testid="map-pin-${id}"] [data-map-part="${part === 'ring' && state !== 'rest' ? 'outline' : 'fill'}"]`, part === 'ring' && state !== 'rest' ? 'stroke' : 'fill', terrain);
      }
      for (const wash of [0, .07]) for (const action of ['rest', 'hover', 'selected-current']) for (const part of ['fill', 'ring'])
        contexts[`map/sidebar-wash-${wash}/${action}/${part}`] = {};
      // Both wash endpoints and parts share one interaction. Drive that state
      // once, then read all four samples; don't reopen the same dialog 4 times.
      for (const action of ['rest', 'hover', 'selected-current']) for (const [state, id] of Object.entries(ids)) {
        await reset();
        await selectPlace(action === 'selected-current' && state === 'current' ? 4 : 1);
        await page.locator('[data-testid="map-pin-3"]').dispatchEvent('pointerover');
        await page.locator('[data-testid="map-pin-3"] [data-map-state="hovered"]').waitFor();
        const row = `[data-testid="map-place-row-${id}"]`;
        if (action === 'hover') await page.locator(row).hover();
        await page.waitForTimeout(170);
        for (const wash of [0, .07]) for (const part of ['fill', 'ring'])
          contexts[`map/sidebar-wash-${wash}/${action}/${part}`][state] = await read(`${row} [data-map-part="${part === 'ring' && state !== 'rest' ? 'outline' : 'fill'}"]`, part === 'ring' && state !== 'rest' ? 'stroke' : 'fill', undefined, wash);
      }
      themes[theme][phase] = contexts;
      await overlay?.evaluate(n => n.remove());
      // Force a fresh component tree for the next phase.
      await page.evaluate(t => window.renderSurfaces(t + '-reset'), theme.toLowerCase());
    }
  }
  if (errors.length || requests.length) throw new Error(JSON.stringify({ errors, apiRequests: requests }));
  const output = resolve(ui, 'client/src/state-surfaces.resolved.json');
  writeFileSync(output, JSON.stringify({ inputs: { ...inputs(ui), chromium: browser.version() }, themes, candidateColors,
    proof: { pageErrors: errors, apiRequests: requests, stylesheet: 'Vite/PostCSS production pipeline',
      samples: 'opaque interiors; static strokes; no edge antialiasing/glow; sidebar radial wash endpoints' } }, null, 2) + '\n');
  console.log(`Resolved state surfaces: 3 themes × 29 contexts × 2 phases; Chromium ${browser.version()}; Playwright ${inputs(ui).playwright}`);
  console.log(`Emulation: 1200×900; colorScheme=dark; reducedMotion=reduce; file://; network aborted; API requests=${requests.length}; page errors=${errors.length}`);
  console.log(`Wrote ui/client/src/state-surfaces.resolved.json; inputs SHA-256 ${inputs(ui).sha256}`);
} finally { await browser.close(); rmSync(resolve(scratch, 'fixture.js'), { force: true }); }
