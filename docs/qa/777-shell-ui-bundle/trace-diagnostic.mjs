import { writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const ui='/Users/pythagor/.codex/worktrees/resume-shell-ui/nexus/ui';
const {chromium}=createRequire(resolve(ui,'package.json'))('playwright');
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1200,height:900},deviceScaleFactor:4,colorScheme:'dark',reducedMotion:'reduce'});
try {
  await page.route(/^https?:/,r=>r.abort());
  await page.routeWebSocket(/.*/,()=>{});
  await page.route('**/fonts/**',r=>r.fulfill({path:resolve(ui,'client/public',new URL(r.request().url()).pathname.slice(1))}));
  await page.goto(pathToFileURL(resolve(import.meta.dirname,'trace-green/fixture.html')).href);
  await page.evaluate(()=>window.renderSurfaces('veil','delete','sea',true));
  await page.evaluate(()=>document.fonts.ready);
  await page.getByRole('button',{name:'Model',exact:true}).click();
  await page.locator('[data-testid="lm-toggle-fixture"]').click();
  const row=page.locator('.lm-quant.exceeds');
  await row.locator('.lm-trash').waitFor();
  await page.evaluate(()=>{
    window.traceEvents=[];
    const row=document.querySelector('.lm-quant.exceeds');
    const record=(event,target)=>window.traceEvents.push({event,time:performance.now(),
      target:target?.getAttribute?.('data-testid') ?? target?.className ?? target?.nodeName,
      scrollTop:target?.scrollTop,containsRow:target?.contains?.(row),
      focused:document.activeElement?.getAttribute('data-testid'),
      state:row.getAttribute('data-state'),rowTop:row.getBoundingClientRect().top});
    for(const event of ['scroll','focusin','focusout']) document.addEventListener(event,e=>record(event,e.target),true);
    new MutationObserver(()=>record('state',row)).observe(row,{attributes:true,attributeFilter:['data-state']});
  });
  await page.locator('body').click({position:{x:1,y:1}});
  for(let tabs=0;tabs<100 && !await row.evaluate(n=>n===document.activeElement);tabs++) await page.keyboard.press('Tab');
  await page.evaluate(async()=>{
    await Promise.all(document.getAnimations().map(a=>a.finished.catch(()=>{})));
    await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
  });
  const result=await page.evaluate(()=>({events:window.traceEvents,
    atRow:{state:document.querySelector('.lm-quant.exceeds').getAttribute('data-state'),tooltip:!!document.querySelector('[role="tooltip"]')}}));
  writeFileSync(resolve(ui,'../docs/qa/777-shell-ui-bundle/trace-scroll-diagnostic.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result.events.slice(-14),null,2));
} finally { await browser.close(); }
