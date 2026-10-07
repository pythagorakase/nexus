/** Diagnose a single shipped/candidate witness with the accepted control. */
import {createRequire} from 'node:module';
import {mkdirSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const root=process.cwd(),scratch=process.env.STATE_SURFACES_SCRATCH,fixture=process.env.STATE_SURFACES_FIXTURE;
if(!scratch?.includes('/scratchpad/777-S2/after-review-r4/')||!fixture?.includes('/scratchpad/777-S2/after-review-r4/'))throw Error('Use order scratch');
mkdirSync(scratch,{recursive:true});
const require=createRequire(resolve(root,'ui/package.json')),{chromium}=require('playwright');
const {foreground}=await import(pathToFileURL(resolve(root,'ui/scripts/state-surfaces/png.mjs')));
const browser=await chromium.launch({headless:true});
const conditions={viewport:{width:639,height:900},deviceScaleFactor:4,colorScheme:'dark',reducedMotion:'reduce'};
const report={conditions,chromium:browser.version(),samples:[],requests:[],errors:[]};
try{
 const page=await browser.newPage(conditions);page.on('request',r=>{if(/^https?:/.test(r.url()))report.requests.push(r.url());});page.on('pageerror',e=>report.errors.push(e.message));await page.route(/^https?:/,r=>r.abort());await page.goto(pathToFileURL(fixture).href);
 const settled=async(selector=null)=>page.evaluate(async selector=>{await new Promise(requestAnimationFrame);for(;;){const n=selector?document.querySelector(selector):null,run=document.getAnimations().filter(a=>a.playState==='running'&&(!n||a.effect?.target instanceof Element&&(n.contains(a.effect.target)||a.effect.target.contains(n))));if(!run.length)return;await Promise.all(run.map(a=>a.finished.catch(()=>{})));}},selector);
 const el=page.locator('.lm-trash svg');
 const capture=async name=>{
  await el.scrollIntoViewIfNeeded();await settled('.lm-trash svg');const box=await el.boundingBox();
  const readback=await el.evaluate(n=>({color:getComputedStyle(n).color,armed:n.closest('.lm-trash').getAttribute('aria-pressed'),rowHover:n.closest('.lm-quant').matches(':hover'),buttonHover:n.closest('.lm-trash').matches(':hover'),focusVisible:n.closest('.lm-trash').matches(':focus-visible'),tooltip:[...document.querySelectorAll('[role="tooltip"]')].map(t=>({text:t.textContent,box:t.getBoundingClientRect().toJSON(),state:t.parentElement?.getAttribute('data-state')})),animations:document.getAnimations().map(a=>({state:a.playState,target:a.effect?.target?.className}))}));
  const painted=await page.screenshot({clip:box});await el.evaluate(n=>n.setAttribute('data-control-capture','witness'));const style=await page.addStyleTag({content:'[data-control-capture="witness"], [data-control-capture="witness"] * {fill:transparent!important;stroke:transparent!important;background-color:transparent!important;color:transparent!important;}'});const control=await page.screenshot({clip:box});await style.evaluate(n=>n.remove());await el.evaluate(n=>n.removeAttribute('data-control-capture'));
  writeFileSync(resolve(scratch,name+'-painted.png'),painted);writeFileSync(resolve(scratch,name+'-control.png'),control);const sample={name,box,readback,...foreground(painted,control,'Veil/width-639/ready-exceeds/row-hover/unarmed/'+name)};report.samples.push(sample);console.log(JSON.stringify(sample));return sample;
 };
 await page.evaluate(()=>window.renderSurfaces('veil','delete','sea',true));await page.getByTestId('lm-toggle-fixture').click();await el.waitFor();await page.mouse.move(0,0);await page.locator('body').click({position:{x:1,y:1}});await settled();await page.locator('.lm-quant').hover();
 const early=await capture('shipping-immediate');
 await page.getByRole('tooltip').waitFor();await settled();
 const later=await capture('shipping-tooltip-visible');
 await page.evaluate(()=>document.documentElement.style.setProperty('--state-delete-unarmed','hsl(42 30% 70%)'));
 const candidate=await capture('candidate-tooltip-visible');
 const repeated=await capture('candidate-repeat');
 if(early.readback.color!==later.readback.color||JSON.stringify(early.box)!==JSON.stringify(later.box)||JSON.stringify(later.meanLinear)!==JSON.stringify(candidate.meanLinear)||JSON.stringify(candidate.meanLinear)!==JSON.stringify(repeated.meanLinear))throw Error('Witness isolation failed');
 if(report.requests.length||report.errors.length)throw Error('Unexpected activity');
 await page.screenshot({path:resolve(scratch,'full-shell.png')});writeFileSync(resolve(scratch,'witness.json'),JSON.stringify(report,null,2)+'\n');console.log('Same color, geometry, mask, hover and zero running animations; delayed sibling tooltip changes the linear mean. Candidate and tooltip-visible shipping repeat exactly.');
}finally{await browser.close();}
