import { createRequire } from 'node:module';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { pathToFileURL } from 'node:url';
import { execFileSync } from 'node:child_process';
const root = process.cwd(), ui = resolve(root, 'ui');
const scratch = process.env.STATE_SURFACES_SCRATCH;
if (!scratch) throw new Error('Set STATE_SURFACES_SCRATCH to the order-specific scratch directory');
const require = createRequire(resolve(ui, 'package.json'));
const { build } = createRequire(require.resolve('vite'))('esbuild');
const { chromium } = require('playwright');
const { build: viteBuild } = require('vite');
const { decodePng } = await import(pathToFileURL(resolve(dirname(new URL(import.meta.url).pathname), 'png.mjs')).href);
await build({ entryPoints: [resolve(ui, 'scripts/state-surfaces/fixture.tsx')], bundle: true,
  outfile: resolve(scratch, 'product-fixture.js'), platform: 'browser', format: 'iife', jsx: 'automatic',
  alias: { '@': resolve(ui, 'client/src'), '@shared': resolve(ui, 'shared') },
  plugins: [{ name: 'private-renderer', setup(b) { b.onLoad({filter:/\/fixture\.tsx$/}, a=>({ contents:readFileSync(a.path,'utf8').replace('id % 2 ? 0 : 10, id < 3 ? 0 : 5','id % 2 ? 0 : .05, id < 3 ? 0 : .05'),loader:'tsx',resolveDir:dirname(a.path)})); b.onLoad({ filter: /\/SettingsPane\.tsx$/ }, a => ({
    contents: readFileSync(a.path, 'utf8') + '\nexport { SettingsCard };', loader: 'tsx', resolveDir: dirname(a.path),
  })); } }],
});
process.chdir(ui);
const out = await viteBuild({ configFile: resolve(ui, 'vite.config.ts'), logLevel: 'error',
  build: { outDir: resolve(scratch, 'production-build'), emptyOutDir: true } });
process.chdir(root);
const css = out.output.filter(o => o.type === 'asset' && o.fileName.endsWith('.css')).map(o => o.source).join('\n');
if (!css) throw new Error('No production CSS');
const file = resolve(scratch, 'product-fixture.html');
writeFileSync(file, `<!doctype html><style>${css}</style><style>.nexus-shell{height:auto}.nexus-main{height:750px}.mappane{height:700px}.settings-pane-v2{height:650px}</style><div id="root"></div><script src="product-fixture.js"></script>`);
const base = execFileSync('git', ['show', '8ccd3008:ui/client/src/index.css'], { encoding: 'utf8' });
const postcss = require('postcss');
const baseTokens = {};
for (const theme of ['veil','gilded','vector']) {
  const values = {};
  postcss.parse(base).walkRules(r => {
    if(r.parent?.type === 'root' && (r.selector === ':root' || r.selector === '.dark' || (theme !== 'veil' && r.selector.includes(`.dark.theme-${theme}`))))
      r.walkDecls(d => { if(d.prop.startsWith('--')) values[d.prop] = d.value; });
  });
  baseTokens[theme] = values;
}
const browser = await chromium.launch({ headless: true });
const report = { conditions: { viewport: {width:1200,height:900}, deviceScaleFactor:4, colorScheme:'dark', reducedMotion:'reduce', origin:'file://', network:'aborted' }, chromium: browser.version(), labels: [], halo: [], pointer: [] };
try {
  const page = await browser.newPage(report.conditions);
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.route(/^https?:/, r => r.abort());
  await page.goto(pathToFileURL(file).href);
  const settled = async () => page.evaluate(async () => {
    await new Promise(requestAnimationFrame); await new Promise(requestAnimationFrame);
    for (;;) { const running = document.getAnimations().filter(a => a.playState === 'running'); if(!running.length) break; await Promise.all(running.map(a => a.finished)); }
  });
  const pixels = async locator => {
    await locator.scrollIntoViewIfNeeded(); await settled();
    const box = await locator.boundingBox();
    const bytes = await page.screenshot({clip:box});
    return { bytes, image:decodePng(bytes) };
  };
  for(const theme of ['veil','gilded','vector']) {
    await page.evaluate(t => window.renderSurfaces(t), theme);
    await page.locator('[data-testid="map-svg"]').waitFor();
    await page.locator('[data-testid="map-zone-1"]').click();
    await page.locator('[data-testid="map-place-row-1"]').click();
    await page.getByTestId('map-place-dialog').getByRole('button',{name:'Close',exact:true}).click();
    await page.mouse.move(0,0); await settled();
    const label = page.locator('[data-testid="map-pin-1"] text');
    const after = await pixels(label);
    const afterColor = await label.evaluate(n=>getComputedStyle(n).fill);
    const overlay = await page.addStyleTag({content:`html.dark { ${Object.entries(baseTokens[theme]).map(([k,v])=>`${k}:${v};`).join(' ')} }`});
    const before = await pixels(label);
    const beforeColor = await label.evaluate(n=>getComputedStyle(n).fill);
    if(after.image.width !== before.image.width || after.image.height !== before.image.height) throw new Error('Clip moved');
    let changedPixels = 0;
    const n = after.image.channels;
    for(let i=0;i<after.image.pixels.length;i+=n) if(!after.image.pixels.subarray(i,i+n).equals(before.image.pixels.subarray(i,i+n))) changedPixels++;
    writeFileSync(resolve(scratch, `${theme}-selected-label-before.png`),before.bytes);
    writeFileSync(resolve(scratch, `${theme}-selected-label-after.png`),after.bytes);
    report.labels.push({theme,state:'selected',beforeColor,afterColor,changedPixels,width:after.image.width,height:after.image.height});
    await overlay.evaluate(n=>n.remove());
    for(const state of ['normal','over']) {
      const meter = page.locator(`[data-memory="${state}"] .mem-fill`);
      const afterShadow = await meter.evaluate(n=>getComputedStyle(n).boxShadow);
      const override = await page.addStyleTag({content:`html.dark { --glow-soft:${baseTokens[theme]['--glow-soft']}; }`});
      const beforeShadow = await meter.evaluate(n=>getComputedStyle(n).boxShadow);
      const beforeShot = await pixels(meter), afterShot = (await override.evaluate(n=>n.remove()),await pixels(meter));
      report.halo.push({theme,state,beforeShadow,afterShadow,pixelIdentical:beforeShot.image.pixels.equals(afterShot.image.pixels)});
    }
    writeFileSync(resolve(scratch,'product-proof.json'),JSON.stringify(report,null,2)+'\n');
    // A real mouse enters the original circular target at a corner, then clicks.
    const svg = page.getByTestId('map-svg'); await svg.scrollIntoViewIfNeeded();
    const bounds = await svg.boundingBox();
    await page.mouse.move(bounds.x+bounds.width/2,bounds.y+bounds.height/2);
    await page.mouse.wheel(0,800); await settled();
    const pin = page.getByTestId('map-pin-2');
    const hit = pin.locator('path').first(); const box = await hit.boundingBox();
    const x=box.x+box.width/2,y=box.y+box.height/2;
    await page.mouse.move(0,0);
    await pin.evaluate(n=>{window.probeNodes=[n.querySelector('[data-map-part="fill"]'),n.querySelector('[data-map-part="outline"]'),n.querySelector('path')];});
    await page.mouse.move(x+2,y+1.6); await settled();
    const hovered = await pin.locator('[data-map-state]').getAttribute('data-map-state');
    console.log(JSON.stringify({theme,box,x,y,hovered,hit:await page.evaluate(([x,y])=>document.elementFromPoint(x,y)?.outerHTML,[x+2,y+1.6])}));
    await page.mouse.click(x+2,y+1.6); await page.getByTestId('map-place-dialog').waitFor();
    const selected = await pin.locator('[data-map-state]').getAttribute('data-map-state');
    await page.getByTestId('map-place-dialog').getByRole('button',{name:'Close',exact:true}).click();
    await page.mouse.move(0,0); await settled();
    const identity = await pin.evaluate(n=>window.probeNodes.every((node,i)=>node===[n.querySelector('[data-map-part="fill"]'),n.querySelector('[data-map-part="outline"]'),n.querySelector('path')][i]));
    await page.getByTestId('map-place-row-1').click();
    await page.getByTestId('map-place-dialog').getByRole('button',{name:'Close',exact:true}).click();
    await page.mouse.move(0,0); await settled();
    const rest = await pin.locator('[data-map-state]').getAttribute('data-map-state');
    const restIdentity = await pin.evaluate(n=>window.probeNodes.every((node,i)=>node===[n.querySelector('[data-map-part="fill"]'),n.querySelector('[data-map-part="outline"]'),n.querySelector('path')][i]));
    if(hovered !== 'hovered' || selected !== 'selected' || rest !== 'rest' || !identity || !restIdentity) throw new Error('Pointer/identity regression');
    report.pointer.push({theme,hovered,selected,rest,identity,restIdentity});
  }
  if(errors.length) throw new Error(JSON.stringify(errors));
  report.pageErrors=errors;
  writeFileSync(resolve(scratch,'product-proof.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
  for(const label of report.labels) console.log(`${label.theme} selected label: ${label.beforeColor} -> ${label.afterColor}; changed device pixels=${label.changedPixels}`);
  console.log(`Halo-only comparisons: ${report.halo.filter(h=>h.pixelIdentical).length}/6 pixel-identical; computed shadows unchanged`);
  console.log(`Real pointer sequences: ${report.pointer.length}/3 hovered -> selected -> rest; stable fill/ring/hit node identity`);
  console.log(`Chromium ${report.chromium}; deviceScaleFactor=4; page errors=${report.pageErrors.length}`);
} finally { await browser.close(); }
