import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const root=process.cwd(), ui=resolve(root,'ui'), scratch=process.env.STATE_SURFACES_SCRATCH;
if (!scratch) throw new Error('Set order-specific scratch');
const require=createRequire(resolve(ui,'package.json'));
const {build}=createRequire(require.resolve('vite'))('esbuild');
const {build:viteBuild}=require('vite');
const {chromium}=require('playwright');
const {histogramPng}=await import(pathToFileURL(resolve(root,'docs/qa/777-glyph-first-states/after-review-r4/png.mjs')));
await build({entryPoints:[resolve(import.meta.dirname,'histogram-fixture.tsx')],nodePaths:[resolve(ui,'node_modules')],bundle:true,outfile:resolve(scratch,'fixture.js'),platform:'browser',format:'iife',jsx:'automatic',alias:{'@':resolve(ui,'client/src'),'@shared':resolve(ui,'shared')},loader:{'.css':'empty'}});
process.chdir(ui);
const out=await viteBuild({configFile:resolve(ui,'vite.config.ts'),logLevel:'error',build:{outDir:resolve(scratch,'production-build'),emptyOutDir:true}});
process.chdir(root);
const css=out.output.filter(o=>o.type==='asset'&&o.fileName.endsWith('.css')).map(o=>o.source).join('\n');
writeFileSync(resolve(scratch,'fixture.html'),`<!doctype html><style>${css}</style><div id="root"></div><script src="fixture.js"></script>`);
const browser=await chromium.launch({headless:true});
const report={sourceHead:'afbb27568aeb4a19c13103720b9c7134b48393d1',chromium:browser.version(),conditions:{viewport:{width:1200,height:900},deviceScaleFactor:4,colorScheme:'dark',reducedMotion:'reduce',origin:'file://',network:'aborted'},samples:[],errors:[],requests:[]};
try {const page=await browser.newPage(report.conditions);page.on('pageerror',e=>report.errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))report.requests.push(r.url())});await page.route(/^https?:/,r=>r.abort());await page.goto(pathToFileURL(resolve(scratch,'fixture.html')).href);await page.locator('[data-testid="map-svg"]').waitFor();
const settled=()=>page.evaluate(async()=>{await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);for(;;){const a=document.getAnimations().filter(a=>a.playState==='running');if(!a.length)return;await Promise.all(a.map(a=>a.finished));}});
async function sample(name,selector,property){const el=page.locator(selector);await el.scrollIntoViewIfNeeded();await settled();const box=await el.boundingBox();const bytes=await page.screenshot({clip:box});writeFileSync(resolve(scratch,`${name}.png`),bytes);const h=histogramPng(bytes);const computed=await el.evaluate((n,p)=>getComputedStyle(n).getPropertyValue(p),property);const result={name,selector,computed,box,width:h.width,height:h.height,histogram:h.histogram.slice(0,8),literalSelected:h.histogram[1]};report.samples.push(result);console.log(JSON.stringify(result));}
await sample('normal-memory-fill','.mem-fill','background-color');await page.evaluate(()=>window.setOver(true));await page.locator('.mem-fill.over').waitFor();await sample('over-memory-fill','.mem-fill.over','background-color');await sample('rest-map-fill','[data-testid="map-pin-2"] .map-state-fill','fill');await page.screenshot({path:resolve(scratch,'real-shell.png')});console.log(`Real NexusLayout=${await page.locator('[data-testid="nexus-layout"]').count()}; Chromium ${browser.version()}; deviceScaleFactor=4; page errors=${report.errors.length}; network requests=${report.requests.length}`);writeFileSync(resolve(scratch,'receipt.json'),JSON.stringify(report,null,2)+'\n');if(report.errors.length)throw new Error(JSON.stringify(report.errors));}finally{await browser.close()}
