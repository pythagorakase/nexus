/** Fresh label/halo and native-pointer proof with the accepted production fixture. */
import { createRequire } from 'node:module';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { execFileSync } from 'node:child_process';
const root=process.cwd(), ui=resolve(root,'ui'), scratch=process.env.STATE_SURFACES_SCRATCH;
if(!scratch?.includes('/scratchpad/777-S2/after-review-r4/')) throw Error('Use order scratch');
mkdirSync(scratch,{recursive:true});
const {fixtureBuild,inputs,conditions}=await import(pathToFileURL(resolve(ui,'scripts/state-surfaces/inputs.mjs')));
const {decodePng}=await import(pathToFileURL(resolve(ui,'scripts/state-surfaces/png.mjs')));
const {themeTokens}=await import(pathToFileURL(resolve(ui,'scripts/state-surfaces/domain.mjs')));
const require=createRequire(resolve(ui,'package.json')), {build}=require('vite'), {chromium}=require('playwright');
// Only synthetic place spacing changes for this finite label visibility proof.
// The acceptance oracle retains its accepted fixture and reachable inventory.
const probeFixture=resolve(scratch,'fixture-labels.tsx');
writeFileSync(probeFixture,readFileSync(resolve(ui,'scripts/state-surfaces/fixture.tsx'),'utf8')
 .replace('id % 2 ? 0 : .05','id % 2 ? 0 : 1').replace('id < 3 ? 0 : .05','id < 3 ? 0 : 1'));
const {build:esbuild}=createRequire(require.resolve('vite'))('esbuild');
const bundle=await esbuild({absWorkingDir:ui,nodePaths:[resolve(ui,'node_modules')],entryPoints:[probeFixture],bundle:true,write:false,metafile:true,platform:'browser',format:'iife',jsx:'automatic',alias:{'@':resolve(ui,'client/src'),'@shared':resolve(ui,'shared')},loader:{'.css':'empty'},plugins:[{name:'private-sections',setup(b){b.onLoad({filter:/\/SettingsPane\.tsx$/},a=>({contents:readFileSync(a.path,'utf8')+'\nexport {ModelSection,KeysSection,SectionRail};',loader:'tsx',resolveDir:resolve(a.path,'..')}));}}]});
writeFileSync(resolve(scratch,'fixture.js'),bundle.outputFiles[0].contents);
process.chdir(ui); const out=await build({configFile:resolve(ui,'vite.config.ts'),logLevel:'error',build:{outDir:resolve(scratch,'build'),emptyOutDir:true}});process.chdir(root);
const css=out.output.filter(o=>o.type==='asset'&&o.fileName.endsWith('.css')).map(o=>o.source).join('\n');
if(!css)throw Error('No shipped CSS');
writeFileSync(resolve(scratch,'fixture.html'),`<!doctype html><style>${css}</style><div id="root"></div><script src="fixture.js"></script>`);
const base=execFileSync('git',['show','8ccd3008:ui/client/src/index.css'],{encoding:'utf8'});
const browser=await chromium.launch({headless:true});
const report={inputs:await inputs(ui,bundle),conditions,chromium:browser.version(),syntheticPlaceSpacingDegrees:1,labels:[],halos:[],pointer:[],pageErrors:[],networkRequests:[]};
try{
 const page=await browser.newPage(conditions);page.on('pageerror',e=>report.pageErrors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))report.networkRequests.push(r.url());});await page.route(/^https?:/,r=>r.abort());await page.goto(pathToFileURL(resolve(scratch,'fixture.html')).href);
 const settled=async()=>page.evaluate(async()=>{await new Promise(requestAnimationFrame);for(;;){const a=document.getAnimations().filter(a=>a.playState==='running');if(!a.length)return;await Promise.all(a.map(a=>a.finished));}});
 const mount=async(theme,mode,over=false)=>{await page.evaluate(a=>window.renderSurfaces(...a),[theme,mode,'sea',over]);await page.locator('[data-testid="nexus-layout"]').waitFor();await settled();};
 const reset=async()=>{await page.mouse.move(0,0);await page.locator('body').click({position:{x:1,y:1}});await settled();};
 const select=async(id)=>{await page.getByTestId(`map-place-row-${id}`).click();await page.getByTestId('map-place-dialog').getByRole('button',{name:'Close',exact:true}).click();await page.getByTestId('map-place-dialog').waitFor({state:'hidden'});await reset();};
 const shot=async(locator)=>{await locator.scrollIntoViewIfNeeded();await settled();const box=await locator.boundingBox();if(!box)throw Error('Missing visible clip');const bytes=await page.screenshot({clip:box});return {bytes,decoded:decodePng(bytes),box};};
 const changed=(a,b)=>{if(a.width!==b.width||a.height!==b.height)throw Error('Clip moved');let n=0;for(let i=0;i<a.pixels.length;i+=a.channels)if(!a.pixels.subarray(i,i+a.channels).equals(b.pixels.subarray(i,i+b.channels)))n++;return n;};
 for(const theme of ['veil','gilded','vector']){
  const globals=themeTokens(base,theme==='veil'?'Veil':theme==='gilded'?'Gilded':'Vector');
  await mount(theme,'map');await page.getByTestId('map-zone-1').click();await select(1);const mapBox=await page.getByTestId('map-svg').boundingBox();await page.mouse.move(mapBox.x+mapBox.width/2,mapBox.y+mapBox.height/2);for(let i=0;i<10;i++){await page.mouse.wheel(0,100);await settled();}await reset();
  for(const [state,id]of Object.entries({rest:2,current:4,selected:1,hovered:3})){
   await reset();if(state==='hovered')await page.locator('[data-testid="map-pin-3"] .map-state-glyph > path[fill="transparent"]').hover();
   const pin=page.getByTestId(`map-pin-${id}`),label=pin.locator('text');
   const actual=await pin.locator('[data-map-state]').getAttribute('data-map-state');if(actual!==state)throw Error(`Unreachable label ${theme}/${state}: ${actual}`);
   const afterColor=await label.evaluate(n=>getComputedStyle(n).fill),visible=await label.isVisible();
   if(!visible){report.labels.push({theme,state,visible,afterColor,note:'Culled rest label has no painted pixels in this action context'});continue;}
   const after=await shot(label),overlay=await page.addStyleTag({content:`html.dark {${Object.entries(globals).filter(([p])=>p.startsWith('--')).map(([p,v])=>`${p}:${v};`).join('')}}`});
   const beforeColor=await label.evaluate(n=>getComputedStyle(n).fill),before=await shot(label);await overlay.evaluate(n=>n.remove());
   const changedPixels=changed(after.decoded,before.decoded),anchor=theme==='veil'&&state==='selected';
   let anchorOnlyMatchesBaseline=false;
   if(theme==='veil'){
    const anchorOverlay=await page.addStyleTag({content:`html.dark {${['--brass','--magenta','--primary','--sidebar-primary','--sidebar-ring','--ring','--chart-1'].map(p=>`${p}:${globals[p]};`).join('')}}`});
    const anchorOnly=await shot(label);await anchorOverlay.evaluate(n=>n.remove());
    anchorOnlyMatchesBaseline=changed(anchorOnly.decoded,before.decoded)===0;
    if(!anchorOnlyMatchesBaseline)throw Error(`Non-anchor label change ${theme}/${state}`);
   }else if(changedPixels||afterColor!==beforeColor)throw Error(`Label freeze failed ${theme}/${state}`);
   for(const [phase,image]of [['before',before],['after',after]])writeFileSync(resolve(scratch,`${theme}-${state}-label-${phase}.png`),image.bytes);
   report.labels.push({theme,state,visible,beforeColor,afterColor,changedPixels,box:after.box,anchorCorrection:anchor,anchorOnlyMatchesBaseline});
  }
  await reset();const pin=page.getByTestId('map-pin-2'),hit=pin.locator('.map-state-glyph > path[fill="transparent"]');await hit.scrollIntoViewIfNeeded();const box=await hit.boundingBox(),x=box.x+box.width/2,y=box.y+box.height/2;
  await pin.evaluate(n=>window.probeNodes=[...n.querySelector('.map-state-glyph').children]);await page.mouse.move(x+2,y+1.6);await settled();const hovered=await pin.locator('[data-map-state]').getAttribute('data-map-state');await page.mouse.click(x+2,y+1.6);await page.getByTestId('map-place-dialog').waitFor();const selected=await pin.locator('[data-map-state]').getAttribute('data-map-state');await page.getByTestId('map-place-dialog').getByRole('button',{name:'Close',exact:true}).click();await select(1);const rest=await pin.locator('[data-map-state]').getAttribute('data-map-state'),identity=await pin.evaluate(n=>[...n.querySelector('.map-state-glyph').children].every((node,i)=>node===window.probeNodes[i]));
  if(hovered!=='hovered'||selected!=='selected'||rest!=='rest'||!identity)throw Error(`Pointer regression ${theme}`);report.pointer.push({theme,hovered,selected,rest,identity,corner:[2,1.6]});
  await page.locator('[data-testid="map-pin-3"] .map-state-glyph > path[fill="transparent"]').hover();await settled();await page.screenshot({path:resolve(scratch,`${theme}-map.png`)});
  const mono=await page.addStyleTag({content:'.map-state-fill{fill:#fff!important;stroke:none!important;filter:none!important}.map-state-ring{fill:none!important;stroke:#fff!important;filter:none!important}'});await page.screenshot({path:resolve(scratch,`${theme}-map-monochrome.png`)});await mono.evaluate(n=>n.remove());
  for(const over of [false,true]){
   await mount(theme,'memory',over);const meter=page.locator('.mem-track'),fill=page.locator('.mem-fill');const afterShadow=await fill.evaluate(n=>getComputedStyle(n).boxShadow),after=await shot(meter);const overlay=await page.addStyleTag({content:`html.dark {--glow-soft:${globals['--glow-soft']};}`});const beforeShadow=await fill.evaluate(n=>getComputedStyle(n).boxShadow),before=await shot(meter);await overlay.evaluate(n=>n.remove());const changedPixels=changed(after.decoded,before.decoded);if(changedPixels||afterShadow!==beforeShadow)throw Error(`Halo freeze failed ${theme}/${over}`);report.halos.push({theme,state:over?'over':'normal',beforeShadow,afterShadow,changedPixels,fillHeldFixed:true});
  }
 }
 if(report.pageErrors.length||report.networkRequests.length)throw Error('Unexpected page/network activity');
 writeFileSync(resolve(scratch,'product-proof.json'),JSON.stringify(report,null,2)+'\n');
 console.log(`Labels: ${report.labels.filter(l=>l.visible&&!l.anchorCorrection&&l.changedPixels===0).length} visible unchanged; ${report.labels.filter(l=>l.anchorCorrection).length} labeled Veil anchor correction; ${report.labels.filter(l=>!l.visible).length} culled`);
 console.log(`Halo-only comparisons: ${report.halos.length}/6 pixel-identical; computed shadows unchanged`);
 console.log(`Native corner-pointer sequences: ${report.pointer.length}/3 hovered -> selected -> rest; stable nodes`);
 console.log(`Chromium ${report.chromium}; deviceScaleFactor=4; requests=${report.networkRequests.length}; errors=${report.pageErrors.length}`);
}finally{await browser.close();}
