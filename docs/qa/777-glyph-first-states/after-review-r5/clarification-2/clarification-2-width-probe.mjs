import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
const {chromium}=createRequire(resolve('ui/package.json'))('playwright');
const b=await chromium.launch(),p=await b.newPage({viewport:{width:320,height:900},deviceScaleFactor:4,colorScheme:'dark',reducedMotion:'reduce'});
await p.goto(pathToFileURL(resolve('scratchpad/777-S2/after-review-r5/capture/fixture.html')).href);
await p.evaluate(()=>window.renderSurfaces('vector','delete'));
await p.locator('[data-testid="lm-toggle-fixture"]').click();
const settle=async()=>{await p.evaluate(async()=>{for(const a of document.getAnimations()){if(a.effect.getTiming().iterations===Infinity){a.pause();a.currentTime=0;}else await a.finished.catch(()=>{});}})};
await settle();await p.locator('.lm-trash svg').scrollIntoViewIfNeeded();
const read=async()=>p.locator('.lm-trash').evaluate(n=>({paint:getComputedStyle(n).color,hit:document.elementFromPoint(n.getBoundingClientRect().x+4,n.getBoundingClientRect().y+4)?.outerHTML,chain:Array.from((function*(x){for(;x;x=x.parentElement)yield x})(n)).map(n=>({tag:n.tagName,cls:n.className,box:n.getBoundingClientRect().toJSON(),scroll:n.scrollLeft,scrollWidth:n.scrollWidth,clientWidth:n.clientWidth,overflow:getComputedStyle(n).overflow}))}));
console.log('before',JSON.stringify(await read()));
await p.screenshot({path:'scratchpad/width-320-before.png'});
await p.locator('body').click({position:{x:1,y:1}});
for(let i=0;i<100;i++){await p.keyboard.press('Tab');if(await p.locator('.lm-trash').evaluate(n=>n===document.activeElement)){console.log('tabs',i+1);break;}}
await p.mouse.move(0,0);await p.locator('body').click({position:{x:1,y:1}});await settle();
console.log('after',JSON.stringify(await read()));
await p.screenshot({path:'scratchpad/width-320-after.png'});await b.close();

// Codex, GPT-6.
