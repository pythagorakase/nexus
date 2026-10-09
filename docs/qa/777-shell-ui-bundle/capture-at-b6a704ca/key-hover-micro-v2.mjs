import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const root='/Users/pythagor/.codex/worktrees/resume-shell-ui/nexus';
const ui=resolve(root,'ui');
const source=readFileSync(resolve(ui,'scripts/resolve-state-surfaces.mjs'),'utf8');
const start=source.indexOf('    async function hoverKeyRow(selector) {');
const end=source.indexOf('    async function keyboardFocus(selector) {',start);
assert(start>=0 && end>start);
const helper=source.slice(start,end);
// Execute the exact committed helper with the real page closure, not a reimplementation.
const bindHelper=new Function('page',`${helper}\nreturn hoverKeyRow;`);
const require=createRequire(resolve(ui,'package.json'));
const {chromium}=require('playwright');
const browser=await chromium.launch({headless:true});
const readings=[], errors=[], requests=[];
const deadline=setTimeout(()=>{throw new Error('Hover microverification exceeded120seconds');},120000);
try {
 for(const [width,coarse] of [[639,false],[639,true],[760,false],[1200,false]]) {
  const page=await browser.newPage({viewport:{width,height:900},hasTouch:coarse,isMobile:coarse,
   deviceScaleFactor:4,colorScheme:'dark',reducedMotion:'reduce'});
  try {
   page.on('pageerror',error=>errors.push(error.message));
   page.on('request',request=>{if(/^https?:/.test(request.url()))requests.push(request.url());});
   await page.route(/^https?:/,route=>route.abort());
   await page.routeWebSocket(/.*/,()=>{});
   await page.route('**/fonts/**',route=>route.fulfill({path:resolve(ui,'client/public',new URL(route.request().url()).pathname.slice(1))}));
   await page.goto(pathToFileURL('/tmp/nexus-777-shell-ui-4ae8b8d2/capture/batch-9/fixture.html').href);
   const hoverKeyRow=bindHelper(page);
   for(const theme of ['veil','gilded','vector']) for(const need of ['required','optional']) {
    await page.evaluate(({theme,need})=>window.renderSurfaces(theme,'key','sea',false,need),{theme,need});
    await page.locator('[data-testid="nexus-layout"]').waitFor();
    await page.evaluate(()=>document.fonts.ready);
    await page.locator('[data-testid="key-verify-verified"]').click();
    await page.locator('.key-glyph-verified').waitFor();
    for(const state of [need==='required'?'required-missing':'optional-absent','present','verified']) {
     await page.mouse.move(0,0);
     await page.locator('body').click({position:{x:1,y:1}});
     const selector=`[data-testid="key-row-${state}"]`, row=page.locator(selector);
     await row.hover();
     const centerGlyphHover=await row.locator('.key-status svg').evaluate(n=>n.matches(':hover'));
     const point=await hoverKeyRow(selector);
     await page.evaluate(async()=>{
      await Promise.all(document.getAnimations().map(a=>a.finished.catch(()=>{})));
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
     });
     const actual=await row.evaluate((n,point)=>({
      point,hitIsRow:document.elementFromPoint(point.x,point.y)===n,
      rowHover:n.matches(':hover'), rowFocusVisible:n.matches(':focus-visible'),
      glyphHover:n.querySelector('.key-status svg').matches(':hover'),
      glyphFocusVisible:n.querySelector('.key-status svg').matches(':focus-visible'),
      controls:[...n.querySelectorAll('button,input,[tabindex]')].map(c=>({hover:c.matches(':hover'),focusVisible:c.matches(':focus-visible')})),
      opacity:getComputedStyle(n).opacity,
     }),point);
     const label=`${width}/${coarse?'coarse':'fine'}/${theme}/${need}/${state}`;
     assert.equal(actual.hitIsRow,true,label); assert.equal(actual.rowHover,true,label);
     assert.equal(actual.glyphHover,false,label); assert.equal(actual.glyphFocusVisible,false,label);
     assert.equal(actual.rowFocusVisible,false,label);
     assert(actual.controls.every(c=>!c.hover && !c.focusVisible),label);
     assert.equal(actual.opacity,'1',label);
     readings.push({label,centerGlyphHover,...actual});
    }
   }
  }finally{await page.close();}
 }
 assert.equal(readings.length,72); assert.equal(readings.filter(r=>r.centerGlyphHover).length,36);
 assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
}finally{
 clearTimeout(deadline);await browser.close();
 writeFileSync('/tmp/nexus-777-shell-ui-4ae8b8d2/capture-v2/hover-micro.json',JSON.stringify({
  scope:'72 reduced-motion key-row cases, not full painted/color acceptance',
  helperSha256:createHash('sha256').update(helper).digest('hex'),readings,errors,requests},null,2)+'\n');
}
console.log('72/72 production-helper row hover cases passed:639fine/coarse,760fine,1200fine;3themes;2needs;3states.');
console.log('Old center hit hovered the SVG in36/72cases; corrected point in0/72. Network0; pageerrors0.');
