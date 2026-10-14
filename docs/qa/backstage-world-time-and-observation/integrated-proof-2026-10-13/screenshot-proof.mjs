// Scratch visual check (never committed): the real NexusLayout + BackstageDrawer
// from a scratch copy of the state-surface fixture with Backstage health true.
import { mkdirSync, writeFileSync, readFileSync, readdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const ui = resolve(process.argv[2]);
const out = resolve(process.argv[3]);
const scratch = resolve(import.meta.dirname);
mkdirSync(out, { recursive: true });
const require = createRequire(resolve(ui, 'package.json'));
const { build } = createRequire(require.resolve('vite'))('esbuild');
const { chromium } = require('playwright');
const bundle = await build({ absWorkingDir: ui, entryPoints: [resolve(scratch, 'fixture-backstage.tsx')],
  bundle: true, write: false, platform: 'browser', format: 'iife', jsx: 'automatic',
  nodePaths: [resolve(ui, 'node_modules')],
  alias: { '@': resolve(ui, 'client/src'), '@shared': resolve(ui, 'shared') }, loader: { '.css': 'empty' } });
writeFileSync(resolve(scratch, 'fixture.js'), bundle.outputFiles[0].contents);
const assets = resolve(ui, 'dist/public/assets');
const css = readdirSync(assets).filter(n => n.endsWith('.css')).map(n => readFileSync(resolve(assets, n), 'utf8')).join('\n');
const html = resolve(scratch, 'fixture.html');
writeFileSync(html, `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>${css}</style><div id="root"></div><script src="fixture.js"></script>`);

const ACCEPTED = {
  schema_version: 3, generation_session: 'a-1', read_at: '2026-10-07T23:00:00Z', ledger_days_read: ['2026-10-07'],
  terminal_outcome: 'accepted', wall_time: { seconds: 11.059 }, choice_ready_at: '2026-10-07T22:59:58Z', seconds_to_choice_ready: 11.059,
  attempts: ['skald_writer', 'gaia'].map(seat => ({ generation_session: 'a-1', seat, attempt: 1, model: 'TEST', outcome: 'accepted',
    window: { provenance: 'attempt_manifest', input_tokens: 4420 }, usage: { provenance: 'provider_usage_ledger', input_tokens: 1000, output_tokens: 800 } })),
  usage_totals: {
    critical_path: { provenance: 'provider_usage_ledger', events: 2, providers: ['test'], comparable: true, input_tokens: 2000, output_tokens: 1600 },
    background: { provenance: 'unknown', events: 0, providers: [], comparable: true, input_tokens: 'unknown', output_tokens: 'unknown' },
    overall: { provenance: 'provider_usage_ledger', events: 2, providers: ['test'], comparable: true, input_tokens: 'unknown', output_tokens: 'unknown' } },
  jobs: { total: 1, entries: [{ queue: 'correspondence_compaction', id: 4, state: 'queued', terminal: false, usage: { provenance: 'unknown', input_tokens: 'unknown', output_tokens: 'unknown' } }] },
};
const PENDING = {
  schema_version: 3, generation_session: 'p-1', read_at: '2026-10-07T23:05:10Z', ledger_days_read: ['2026-10-07'],
  terminal_outcome: null, wall_time: { seconds: 6.2 }, choice_ready_at: '2026-10-07T23:05:06Z', seconds_to_choice_ready: 6.2,
  attempts: [{ generation_session: 'p-1', seat: 'skald_writer', attempt: 1, model: 'TEST', outcome: null,
    window: { provenance: 'attempt_manifest', input_tokens: 4420 }, usage: { provenance: 'provider_usage_ledger', input_tokens: 1000, output_tokens: 800 } }],
  usage_totals: {
    critical_path: { provenance: 'provider_usage_ledger', events: 1, providers: ['test'], comparable: true, input_tokens: 1000, output_tokens: 800 },
    background: { provenance: null, events: 0, providers: [], comparable: true, input_tokens: 0, output_tokens: 0 },
    overall: { provenance: 'provider_usage_ledger', events: 1, providers: ['test'], comparable: true, input_tokens: 1000, output_tokens: 800 } },
  jobs: { total: 0, entries: [] },
};
const base = {
  header: { slot: 4, chunk_id: 203, chunk_label: 'S01E07_203', turn_label: 't.17', world_time: '2026-10-07T21:07:00Z', elapsed_seconds: 420, skald_status: 'idle' },
  correspondence: { digest: null, compacted_through_chunk_id: null, digest_fresh: false, exchanges: [], held_threads: [] },
  state_writes: { rows: [], history: [] },
  orrery: { rows: [
    { template_id: 'stroll', actor_name: 'Celia', target_name: null, magnitude: 0.1, brief: 'Celia walks nearby.', branch_label: 'Pace the near ground', event_type: 'stroll_taken', drive_band: 'anchored_routine', attention: 'background' },
    { template_id: 'evade_pursuers', actor_name: 'Victor', target_name: null, magnitude: 0.75, brief: 'Victor moves toward safety.', branch_label: 'Take cover', event_type: 'threat_issued', drive_band: 'crisis_constraint', attention: 'meaningful' } ],
    counts: { fired: 2, pressures: 0, events: 2 }, history: [] },
};
const states = {
  'observed-with-pending': { ...base, economics: {
    accepted: { status: 'observed', generation_session: 'a-1', detail: null, observation: ACCEPTED },
    pending: { status: 'observed', generation_session: 'p-1', detail: null, observation: PENDING } } },
  'unavailable': { ...base, header: { ...base.header, elapsed_seconds: 3600 }, economics: {
    accepted: { status: 'unavailable', generation_session: null, detail: 'chunk 203: no generation session (accepted before session binding)', observation: null },
    pending: { status: 'unavailable', generation_session: 'p-1', detail: 'session p-1: no generation session (staged before session binding)', observation: null } } },
};

const browser = await chromium.launch({ headless: true });
const readback = {};
try {
  for (const [name, payload] of Object.entries(states)) {
    const page = await browser.newPage({ viewport: { width: 1200, height: 900 }, deviceScaleFactor: 2,
      colorScheme: 'dark', reducedMotion: 'reduce', hasTouch: false, isMobile: false });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route(/^https?:/, route => route.abort());
    await page.routeWebSocket(/.*/, () => {});
    await page.route('**/fonts/**', route => route.fulfill({
      path: resolve(ui, 'client/public', new URL(route.request().url()).pathname.slice(1)) }));
    await page.goto(pathToFileURL(html).href);
    await page.evaluate(p => window.setBackstageTurn(p), payload);
    await page.evaluate(() => window.renderSurfaces('veil', 'map', 'land'));
    await page.locator('[data-testid="nexus-layout"]').waitFor();
    await page.evaluate(() => document.fonts.ready);
    await page.keyboard.press('`');
    await page.getByRole('button', { name: /ECONOMICS/ }).waitFor();
    await page.evaluate(async () => {
      await Promise.all(document.getAnimations().map(a => a.finished.catch(() => {})));
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    });
    const data = await page.evaluate(() => {
      const drawer = document.querySelector('.nexus-backstage-drawer');
      const pending = document.querySelector('[data-testid="backstage-economics-pending"]');
      const econ = document.querySelector('.nexus-backstage-economics');
      const ps = pending ? getComputedStyle(pending) : null;
      return {
        theme: document.documentElement.getAttribute('data-theme') ?? document.documentElement.className,
        drawerRect: drawer?.getBoundingClientRect().toJSON() ?? null,
        headerLine: [...(drawer?.querySelectorAll('span') ?? [])].map(s => s.textContent).find(t => /^slot 04 · t\.17/.test(t ?? '')) ?? null,
        economicsHeader: [...document.querySelectorAll('button')].map(b => b.textContent).find(t => /ECONOMICS/.test(t ?? '')) ?? null,
        economicsLines: econ ? [...econ.querySelectorAll('.nexus-backstage-write-copy, .nexus-backstage-history span')].map(n => n.textContent) : [],
        overlaps: econ ? [...econ.querySelectorAll('.nexus-backstage-write-row')].map(row => {
          const kind = row.querySelector('.nexus-backstage-kind'), copy = row.querySelector('.nexus-backstage-write-copy');
          return kind && copy ? { kind: kind.textContent, kindRight: (() => { const r = document.createRange(); r.selectNodeContents(kind); return r.getBoundingClientRect().right; })(), copyLeft: copy.getBoundingClientRect().left } : null;
        }).filter(r => r && r.kindRight > r.copyLeft) : [],
        pendingStyle: ps ? { borderLeft: `${ps.borderLeftWidth} ${ps.borderLeftStyle} ${ps.borderLeftColor}`, opacity: ps.opacity } : null,
      };
    });
    data.pageErrors = errors;
    readback[name] = data;
    await page.screenshot({ path: resolve(out, `backstage-${name}-1200x900.png`) });
    const drawer = page.locator('.nexus-backstage-drawer');
    await drawer.screenshot({ path: resolve(out, `backstage-${name}-drawer.png`) });
    await page.close();
  }
} finally {
  await browser.close();
}
writeFileSync(resolve(out, 'screenshot-readback.json'), JSON.stringify(readback, null, 2) + '\n');
console.log(JSON.stringify(readback, null, 2));
