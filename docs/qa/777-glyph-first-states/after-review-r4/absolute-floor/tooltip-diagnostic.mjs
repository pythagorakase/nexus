import {createRequire} from 'node:module';
import {writeFileSync,readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const root=process.cwd(),scratch=process.env.STATE_SURFACES_SCRATCH;
const require=createRequire(resolve(root,'ui/package.json'));
const {chromium}=require('playwright');
const {decodePng,foreground}=await import(pathToFileURL(resolve(root,'ui/scripts/state-surfaces/png.mjs')));
const browser=await chromium.launch({headless:true});
const conditions={viewport:{width:639,height:900},deviceScaleFactor:4,colorScheme:'dark',reducedMotion:'reduce'};
const report={conditions,chromium:browser.version(),samples:[],requests:[],errors:[]};
const hash=b=>createHash('sha256').update(b).digest('hex');
try{
const page=await browser.newPage(conditions);
page.on('request',r=>{if(/^https?:/.test(r.url()))report.requests.push(r.url());});
page.on('pageerror',e=>report.errors.push(e.message));
await page.route(/^https?:/,r=>r.abort());
await page.goto(pathToFileURL(resolve(scratch,'isolated/fixture.html')).href);
await page.evaluate(()=>window.renderSurfaces('vector','delete','sea',true));
await page.getByTestId('lm-toggle-fixture').click();
await page.locator('.lm-trash').waitFor();
await page.mouse.move(0,0);await page.locator('body').click({position:{x:1,y:1}});
await page.locator('.lm-quant').hover();
await page.evaluate(()=>document.documentElement.style.setProperty('--state-delete-unarmed','hsl(185 40% 70%)'));
const settled=async()=>page.evaluate(async()=>{await new Promise(requestAnimationFrame);for(;;){const running=document.getAnimations().filter(a=>a.playState==='running');if(!running.length)return;await Promise.all(running.map(a=>a.finished));}});
await settled();
const el=page.locator('.lm-trash svg');await el.scrollIntoViewIfNeeded();await settled();
await page.locator('.lm-quant').hover();await page.getByRole('tooltip').waitFor();await settled();
report.readback=await el.evaluate(n=>{const props=['fill','stroke','color','background-color','opacity','filter','box-shadow','text-shadow','visibility','display','transition'];const style=e=>({tag:e.tagName,classes:e.getAttribute('class'),...Object.fromEntries(props.map(p=>[p,getComputedStyle(e).getPropertyValue(p)]))});const ancestors=[];for(let e=n;e;e=e.parentElement)ancestors.push(style(e));return{ancestors,children:[...n.querySelectorAll('*')].map(style),dpr:devicePixelRatio,armed:n.closest('.lm-trash').getAttribute('aria-pressed'),rowHover:n.closest('.lm-quant').matches(':hover'),hover:n.matches(':hover'),focusVisible:n.matches(':focus-visible'),animations:document.getAnimations().map(a=>({state:a.playState,target:a.effect?.target?.className}))};});
if(process.env.DIAGNOSTIC_NO_TIP_SHADOW)await page.addStyleTag({content:'.lm-tip {box-shadow:none!important;}'});
const box=await el.boundingBox();report.box=box;report.tooltip=await page.locator('.lm-tip').evaluate(n=>({text:n.textContent,box:n.getBoundingClientRect().toJSON(),shadow:getComputedStyle(n).boxShadow,html:n.outerHTML}));
for(let i=1;i<=3;i++){
await settled();const painted=await page.screenshot({clip:box});
await el.evaluate(n=>n.setAttribute('data-control-capture','diagnostic'));
const style=await page.addStyleTag({content:'[data-control-capture="diagnostic"], [data-control-capture="diagnostic"] * {fill:transparent!important;stroke:transparent!important;background-color:transparent!important;color:transparent!important;}'});
const suppressed=await el.evaluate(n=>({filter:getComputedStyle(n).filter,shadow:getComputedStyle(n).boxShadow,children:[...n.querySelectorAll('*')].map(e=>({fill:getComputedStyle(e).fill,stroke:getComputedStyle(e).stroke,color:getComputedStyle(e).color,filter:getComputedStyle(e).filter,shadow:getComputedStyle(e).boxShadow}))}));
const control=await page.screenshot({clip:box});await style.evaluate(n=>n.remove());await el.evaluate(n=>n.removeAttribute('data-control-capture'));
writeFileSync(resolve(scratch,`repeat-${i}-painted.png`),painted);writeFileSync(resolve(scratch,`repeat-${i}-control.png`),control);
const a=decodePng(painted),b=decodePng(control);let maskSize=0;const counts=new Map();
for(let j=0;j<a.pixels.length;j+=a.channels){if(a.pixels.subarray(j,j+a.channels).equals(b.pixels.subarray(j,j+b.channels)))continue;maskSize++;const key=[...a.pixels.subarray(j,j+3)].join(',');counts.set(key,(counts.get(key)||0)+1);}
const top8=[...counts].map(([key,count])=>({rgb:key.split(',').map(Number),count})).sort((a,b)=>b.count-a.count||a.rgb[0]-b.rgb[0]||a.rgb[1]-b.rgb[1]||a.rgb[2]-b.rgb[2]).slice(0,8);
let error;try{foreground(painted,control,'Vector/width-639/exceeds-row-hover/unarmed');}catch(e){error=e.message;}
report.samples.push({i,width:a.width,height:a.height,maskSize,modeCount:top8[0].count,modeFraction:top8[0].count/maskSize,top8,paintedHash:hash(painted),controlHash:hash(control),suppressed,error});
}
await page.screenshot({path:resolve(scratch,'full-shell.png')});
if(report.errors.length||report.requests.length)throw Error('Network/page error');
if(new Set(report.samples.map(s=>s.paintedHash)).size!==1||new Set(report.samples.map(s=>s.controlHash)).size!==1)throw Error('Nondeterministic captures');
writeFileSync(resolve(scratch,'diagnostic.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({tooltip:report.tooltip,box:report.box,pseudos:{rowHover:report.readback.rowHover,hover:report.readback.hover,armed:report.readback.armed},animations:report.readback.animations,conditions:report.conditions},null,2));
console.log('Tooltip-visible candidate: '+JSON.stringify(report.samples.map(s=>({mode:s.modeCount,mask:s.maskSize,error:s.error}))));
}finally{await browser.close();}
