import { createRequire } from 'node:module';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const root=process.cwd(), scratch=process.env.STATE_SURFACES_SCRATCH;
const require=createRequire(resolve(root,'ui/package.json'));
const {chromium}=require('playwright');
const {decodePng,foreground,histogramPng}=await import(pathToFileURL(resolve(root,'ui/scripts/state-surfaces/png.mjs')));
const browser=await chromium.launch({headless:true});
const report=[];
try {
 const page=await browser.newPage({viewport:{width:1200,height:900},deviceScaleFactor:4,colorScheme:'dark',reducedMotion:'reduce'});
 await page.route(/^https?:/,r=>r.abort());
 await page.goto(pathToFileURL(resolve(scratch,'full-capture/batch-1/fixture.html')).href);
 const settle=()=>page.evaluate(async()=>{await new Promise(requestAnimationFrame);for(;;){const a=document.getAnimations().filter(a=>a.playState==='running');if(!a.length)return;await Promise.all(a.map(a=>a.finished.catch(()=>{})));}});
 for(const theme of ['veil','gilded','vector']) {
  await page.evaluate(t=>window.renderSurfaces(t,'key','sea',false,'optional'),theme);
  await page.getByTestId('key-verify-verified').click();await page.locator('.key-glyph-verified').waitFor();
  await page.mouse.move(0,0);await page.locator('body').click({position:{x:1,y:1}});await settle();
  for(const state of ['optional-absent','present']) {
   const n=page.locator(`[data-testid="key-row-${state}"] .key-status svg`);await n.scrollIntoViewIfNeeded();await settle();
   const box=await n.boundingBox();
   const props=await n.evaluate(n=>({svg:getComputedStyle(n).stroke,fill:getComputedStyle(n).fill,rowOpacity:getComputedStyle(n.closest('.key-row')).opacity,rowHover:n.closest('.key-row').matches(':hover'),rowFocus:n.closest('.key-row').matches(':focus-within'),running:document.getAnimations().filter(a=>a.playState==='running').length,deviceScale:devicePixelRatio}));
   const shots=[];
   for(const variant of ['neutral-style','hidden','transparent-stroke','opaque-row-hidden']) {
    const repeat=variant;
    let rowStyle;
    if(variant==='opaque-row-hidden') {rowStyle=await page.addStyleTag({content:'.key-row.optional {opacity:1!important}'});await settle();}
    const painted=await page.screenshot({clip:box});
    await n.evaluate(n=>n.setAttribute('data-control-capture',''));
    const content=variant==='neutral-style'?'[data-control-capture] {--control-diagnostic:1}':variant==='transparent-stroke'?'[data-control-capture], [data-control-capture] * {stroke:transparent!important;fill:transparent!important}':'[data-control-capture], [data-control-capture] * {visibility:hidden!important}';
    const style=await page.addStyleTag({content});
    const control=await page.screenshot({clip:box});
    await style.evaluate(n=>n.remove());await n.evaluate(n=>n.removeAttribute('data-control-capture'));await settle();
    writeFileSync(resolve(scratch,`${theme}-${state}-${repeat}-painted.png`),painted);
    writeFileSync(resolve(scratch,`${theme}-${state}-${repeat}-control.png`),control);
    const a=decodePng(painted),b=decodePng(control),pairCounts=new Map();
    for(let i=0;i<a.pixels.length;i+=a.channels){const x=Array.from(a.pixels.subarray(i,i+3)),y=Array.from(b.pixels.subarray(i,i+3));if(x.join()===y.join())continue;const key=x.join()+'=>'+y.join();pairCounts.set(key,(pairCounts.get(key)??0)+1);}
    const measured=(()=>{try{return foreground(painted,control,`${theme}/${state}`)}catch(e){return {error:e.message}}})();
    shots.push({repeat,foreground:measured,paintedTop:histogramPng(painted).histogram.slice(0,4),controlTop:histogramPng(control).histogram.slice(0,4),changedPairs:[...pairCounts].sort((a,b)=>b[1]-a[1]).slice(0,8)});
    if(rowStyle){await rowStyle.evaluate(n=>n.remove());await settle();}
   }
   report.push({theme,state,box,props,shots});
   console.log(JSON.stringify({theme,state,props,shots:shots.map(s=>({repeat:s.repeat,painted:s.foreground.painted,maskSize:s.foreground.maskSize,modeFraction:s.foreground.modeFraction,pairs:s.changedPairs.slice(0,3),controlTop:s.controlTop}))}));
  }
 }
 writeFileSync(resolve(scratch,'control-causality.json'),JSON.stringify(report,null,2)+'\n');
} finally {await browser.close();}
