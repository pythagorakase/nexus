/** Isolate the actual shipped/plant cascade and retain direct pixel comparisons. */
import {createRequire} from 'node:module';
import {readFileSync,mkdirSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {decodePng} from '../../../../../ui/scripts/state-surfaces/png.mjs';
const root=process.cwd(), scratch=process.env.STATE_SURFACES_SCRATCH;
if(!scratch?.includes('/scratchpad/777-S2/after-review-r4/'))throw Error('Use order scratch');
mkdirSync(scratch,{recursive:true});
const require=createRequire(resolve(root,'ui/package.json')),{chromium}=require('playwright'),postcss=require('postcss');
const base=scratch.replace(/\/gradient-proof$/, '');
const fixtures={shipping:resolve(base,'capture/batch-1/fixture.html'),plant:resolve(base,'plants/opaque-gradient-stop-capture/default/fixture.html')};
const report={errors:[],requests:[],renders:[]};
const browser=await chromium.launch({headless:true});
try{
 for(const [phase,fixture]of Object.entries(fixtures)){
  const markup=readFileSync(fixture,'utf8'),css=markup.match(/<style>([\s\S]*?)<\/style>/)[1],rules=[];
  postcss.parse(css).walkRules(r=>{if(r.selector.includes('.nexus-content'))rules.push(r.toString());});
  const p=await browser.newPage({viewport:{width:1200,height:900},deviceScaleFactor:4,colorScheme:'dark',reducedMotion:'reduce'});
  p.on('pageerror',e=>report.errors.push(e.message));p.on('request',r=>{if(/^https?:/.test(r.url()))report.requests.push(r.url());});await p.route(/^https?:/,r=>r.abort());await p.goto(pathToFileURL(fixture).href);
  await p.evaluate(()=>window.renderSurfaces('veil','map'));
  await p.getByTestId('map-zone-1').click();await p.getByTestId('map-place-row-1').click();await p.getByTestId('map-place-dialog').getByRole('button',{name:'Close',exact:true}).click();await p.mouse.move(0,0);await p.locator('body').click({position:{x:1,y:1}});
  await p.evaluate(async()=>{await new Promise(requestAnimationFrame);for(;;){const running=document.getAnimations().filter(a=>a.playState==='running');if(!running.length)return;await Promise.all(running.map(a=>a.finished));}});
  const computed=await p.locator('.nexus-content').evaluate(n=>({backgroundImage:getComputedStyle(n).backgroundImage,backgroundColor:getComputedStyle(n).backgroundColor,box:n.getBoundingClientRect().toJSON(),ancestry:[...document.querySelector('[data-testid="map-place-row-2"]').querySelectorAll('svg')].map(n=>{const rows=[];for(;n;n=n.parentElement)rows.push({tag:n.tagName,classes:n.getAttribute('class'),background:getComputedStyle(n).background});return rows;})}));
  const png=await p.screenshot();writeFileSync(resolve(scratch,phase+'.png'),png);
  report.renders.push({phase,rules,computed,file:phase+'.png'});await p.close();
 }
 const a=decodePng(readFileSync(resolve(scratch,'shipping.png'))),b=decodePng(readFileSync(resolve(scratch,'plant.png')));
 let changed=0;for(let i=0;i<a.pixels.length;i+=a.channels)if(!a.pixels.subarray(i,i+a.channels).equals(b.pixels.subarray(i,i+b.channels)))changed++;
 report.changedPixels=changed;writeFileSync(resolve(scratch,'proof.json'),JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify(report.renders.map(r=>({phase:r.phase,backgroundImage:r.computed.backgroundImage,backgroundColor:r.computed.backgroundColor,rules:r.rules})),null,2));
 console.log('Full default Veil map shell changed device pixels='+changed+'; requests='+report.requests.length+'; errors='+report.errors.length);
}finally{await browser.close();}
