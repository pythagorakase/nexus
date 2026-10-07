import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
const root=process.cwd(), require=createRequire(resolve(root,'ui/package.json'));
const {chromium}=require('playwright'), browser=await chromium.launch({headless:true});
const results=[];
try {
 for(const theme of ['veil','gilded','vector']) {
  const p=await browser.newPage({viewport:{width:1200,height:900},deviceScaleFactor:4,reducedMotion:'reduce'});
  await p.route(/^https?:/,r=>r.abort()); await p.routeWebSocket(/.*/,()=>{});
  const fontRoutes=[]; await p.route('**/fonts/**',r=>{fontRoutes.push(r.request().url());return r.fulfill({path:resolve(root,'ui/client/public',new URL(r.request().url()).pathname.slice(1))});});
  await p.goto(pathToFileURL(resolve(root,'scratchpad/777-S2/after-review-r5/clarification-4/provider-font-probe/fixture.html')).href);
  await p.evaluate(theme=>window.renderSurfaces(theme,'key','sea',false,'required'),theme);
  await p.locator('[data-testid="key-verify-verified"]').waitFor(); await p.evaluate(()=>document.fonts.ready);
  const state=await p.evaluate(()=>({fonts:[...document.fonts].map(f=>({family:f.family,status:f.status})),tab:new URLSearchParams(location.search).get('tab'),panes:document.querySelectorAll('.settings-pane-v2').length,scrollers:document.querySelectorAll('.set-scroller').length,inlineFonts:document.documentElement.style.cssText}));
  results.push({theme,fontRoutes,...state}); await p.close();
 }
 writeFileSync(resolve(root,'scratchpad/777-S2/after-review-r5/clarification-4/font-readback.json'),JSON.stringify(results,null,2)+'\n');
 console.log(results.map(r=>({theme:r.theme,routes:r.fontRoutes.length,loaded:r.fonts.filter(f=>f.status==='loaded').length,errors:r.fonts.filter(f=>f.status==='error'),tab:r.tab,panes:r.panes,scrollers:r.scrollers})));
} finally {await browser.close();}
