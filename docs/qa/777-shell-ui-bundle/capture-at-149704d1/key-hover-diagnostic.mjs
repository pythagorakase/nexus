import { writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const root = '/Users/pythagor/.codex/worktrees/resume-shell-ui/nexus';
const ui = resolve(root, 'ui');
const out = resolve(root, 'docs/qa/777-shell-ui-bundle/state-surfaces');
const require = createRequire(resolve(ui, 'package.json'));
const { chromium } = require('playwright');
const browser = await chromium.launch({ headless: true });
const readings = [], errors = [], requests = [];
const deadline = setTimeout(() => { throw new Error('Diagnostic exceeded 60 seconds'); }, 60000);
try {
  for (const [width, coarse] of [[639, false], [760, false], [639, true]]) {
    const page = await browser.newPage({ viewport: { width, height: 900 }, hasTouch: coarse,
      isMobile: coarse, deviceScaleFactor: 4, colorScheme: 'dark', reducedMotion: 'reduce' });
    try {
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()); });
      await page.route(/^https?:/, route => route.abort());
      await page.routeWebSocket(/.*/, () => {});
      await page.route('**/fonts/**', route => route.fulfill({
        path: resolve(ui, 'client/public', new URL(route.request().url()).pathname.slice(1)),
      }));
      await page.goto(pathToFileURL('/tmp/nexus-777-shell-ui-4ae8b8d2/capture/batch-9/fixture.html').href);
      await page.evaluate(() => {
        window.pointerReadback = null;
        document.addEventListener('mousemove', e => { window.pointerReadback = { x: e.clientX, y: e.clientY }; });
        window.renderSurfaces('veil', 'key', 'sea', false, 'required');
      });
      await page.locator('[data-testid="nexus-layout"]').waitFor();
      await page.evaluate(() => document.fonts.ready);
      await page.locator('[data-testid="key-verify-verified"]').click();
      await page.locator('.key-glyph-verified').waitFor();
      await page.mouse.move(0, 0);
      await page.locator('body').click({ position: { x: 1, y: 1 } });
      const row = page.locator('[data-testid="key-row-required-missing"]');
      await row.hover();
      await page.evaluate(async () => {
        await Promise.all(document.getAnimations().map(a => a.finished.catch(() => {})));
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      });
      const reading = await row.evaluate(row => {
        const box = n => { const r=n.getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height}; };
        const identify = n => n ? { tag: n.tagName, testid:n.getAttribute('data-testid'), class:n.getAttribute('class') } : null;
        const svg = row.querySelector('.key-status svg');
        const p = window.pointerReadback;
        const empty = [];
        const r = row.getBoundingClientRect();
        for (let y=r.top+2; y<r.bottom-1; y+=2) for (let x=r.left+2; x<Math.min(r.right-1,innerWidth-1); x+=2) {
          if (document.elementFromPoint(x,y)===row) { empty.push({x,y}); break; }
        }
        return { row:box(row), svg:box(svg), pointer:p, hit:identify(document.elementFromPoint(p.x,p.y)),
          rowHover:row.matches(':hover'), svgHover:svg.matches(':hover'),
          controls:[...row.querySelectorAll('button,input,[tabindex]')].map(n=>({ ...identify(n), box:box(n),hover:n.matches(':hover'),focusVisible:n.matches(':focus-visible') })),
          emptyRowPoints:empty, rowStyle:{display:getComputedStyle(row).display, padding:getComputedStyle(row).padding},
          scrollerScrollTop:row.closest('.set-scroller').scrollTop };
      });
      if (reading.emptyRowPoints.length) {
        const point=reading.emptyRowPoints[Math.floor(reading.emptyRowPoints.length/2)];
        await page.mouse.move(point.x,point.y);
        reading.emptyPointProbe=await row.evaluate((row,point)=>({point,
          hitIsRow:document.elementFromPoint(point.x,point.y)===row,rowHover:row.matches(':hover'),
          svgHover:row.querySelector('.key-status svg').matches(':hover'),
          controls:[...row.querySelectorAll('button,input,[tabindex]')].map(n=>({hover:n.matches(':hover'),focusVisible:n.matches(':focus-visible')}))}),point);
      }
      readings.push({width,coarse,...reading});
      await page.screenshot({ path:resolve(out,`key-hover-${width}-${coarse?'coarse':'fine'}.png`) });
    } finally { await page.close(); }
  }
} finally {
  clearTimeout(deadline);
  await browser.close();
  writeFileSync(resolve(out,'key-hover-diagnostic.json'),JSON.stringify({readings,errors,requests},null,2)+'\n');
}
if(errors.length || requests.length) throw new Error('Unexpected browser/network activity');
console.log(JSON.stringify({readings,errors,requests},null,2));
