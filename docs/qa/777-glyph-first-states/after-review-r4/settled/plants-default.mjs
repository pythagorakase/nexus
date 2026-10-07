/** Amendment 8 adapter for the checked-in plants.mjs protocol.
 * Only scratch is mutated. Partial receipts stay partial on disk. The relocated
 * Vitest diagnostic scopes the production mask/table assertions to default;
 * it neither certifies media coverage nor runs a reduced-domain joint search.
 */
import { execFileSync, spawn } from 'node:child_process';
import { cpSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = process.cwd(), ui = resolve(root, 'ui');
const scratch = process.env.STATE_SURFACES_SCRATCH;
if (!scratch?.includes('/scratchpad/777-S2/after-review-r4/')) throw Error('Use order scratch');
const copy = resolve(scratch, 'plant-copy'), copiedUi = resolve(copy, 'ui');
const arg = name => process.argv[process.argv.indexOf(name) + 1];
const stage = arg('--stage'), name = arg('--plant');
const source = readFileSync(resolve(ui, 'scripts/state-surfaces/plants.mjs'), 'utf8');
const list = source.match(/const plants = \[[\s\S]*?\n\];/)[0];
const plants = new Function('layout', 'theme', `${list}\nreturn plants;`)(
  'ui/client/src/components/nexus/nexus-layout.css', 'ui/client/src/contexts/ThemeContext.tsx');
// Round 3's media root plant matched dark. Amendment 8 measures only dark:
// retain that matching prelude, rather than claiming a light paint was sampled.
// The production bundle loads index.css after layout CSS. Qualify the root
// with html so this test override wins that real cascade (no !important).
plants.find(p => p.name === 'media-root-override').append = plants.find(p => p.name === 'media-root-override').append
  .replace('color-scheme: light', 'color-scheme: dark').replace('.dark.theme-vector', 'html.dark.theme-vector');
const plant = plants.find(p => p.name === name);
mkdirSync(scratch, { recursive: true });
const ledger = resolve(scratch, 'plants-default-proof.json');
const report = stage === 'control' ? [] : JSON.parse(readFileSync(ledger, 'utf8'));
const receiptPath = resolve(copiedUi, 'client/src/state-surfaces.resolved.json');
const originalReceipt = readFileSync(resolve(ui, 'client/src/state-surfaces.resolved.json'));
const original = plant && readFileSync(resolve(root, plant.path), 'utf8');
const target = plant && resolve(copy, plant.path);
async function run(label, args, env = {}) {
  const child = spawn(args[0], args.slice(1), { cwd: root, env: { ...process.env,
    GIT_DIR: execFileSync('git', ['rev-parse', '--absolute-git-dir'], {encoding:'utf8'}).trim(), ...env } });
  const start = performance.now(); let output = '';
  for (const stream of [child.stdout, child.stderr]) stream.on('data', bytes => { output += bytes; });
  const timer = setTimeout(() => child.kill('SIGTERM'), 589000);
  const progress = setInterval(() => console.log(`${label}: running; latest output:\n${output.slice(-300)}`), 45000);
  const code = await new Promise(r => child.on('exit', r));
  clearTimeout(timer); clearInterval(progress);
  writeFileSync(resolve(scratch, `${label}.log`), output);
  const result = {name:label,args,code,wallSeconds:(performance.now()-start)/1000,tail:output.split('\n').slice(-35).join('\n')};
  report.push(result); console.log(`${label}: exit ${code}\n${result.tail}`); return result;
}
const restore = () => { if (plant) writeFileSync(target, original); writeFileSync(receiptPath, originalReceipt); };
function diagnostic(receipt) {
  const src = resolve(copiedUi, 'client/src');
  let test = readFileSync(resolve(src, 'state-shades.test.ts'), 'utf8')
    .replaceAll('import.meta.dirname', JSON.stringify(src))
    .replaceAll('from "../../scripts/state-surfaces/', 'from "../scripts/state-surfaces/')
    .replace('"./state-shades-measurement"', '"./src/state-shades-measurement"');
  test = test.replace('resolve(' + JSON.stringify(src) + ', "state-surfaces.resolved.json")', JSON.stringify(receipt));
  test = test.replace('if (receipt.proof.acceptanceComplete !== true)\n  throw new Error("Incomplete painted state surfaces: filtered/probe captures are not acceptance receipts.");',
    'if (!receipt.conditions.default) throw new Error("Missing default diagnostic capture");\nreceipt.media.variants = receipt.media.variants.filter(v => v.id === "default");\nreceipt.conditions = { default: receipt.conditions.default };');
  test = test.replace('toEqual(evidence.measurements)', 'toEqual(evidence.measurements.filter((m: {condition: string}) => m.condition === "default"))')
    .replace('toEqual(evidence.before)', 'toEqual(evidence.before.filter((m: {condition: string}) => m.condition === "default"))');
  // Outside Tailwind client/src, so this diagnostic cannot affect the input hash.
  writeFileSync(resolve(copiedUi, 'client/plant-default.test.ts'), test);
}
const diagnosticTests = 'browser_measurements_match_recorded_tables|same_value_has_exactly_the_same_settled_mask_mean|painted_mask_means_are_linear_and_interactions_are_real_and_settled';
try {
  if (stage === 'control') {
    cpSync(ui, copiedUi, {recursive:true,verbatimSymlinks:true,filter:p => p !== resolve(ui,'dist') && !p.startsWith(resolve(ui,'dist')+'/')});
    cpSync(resolve(root,'docs/qa/777-glyph-first-states'),resolve(copy,'docs/qa/777-glyph-first-states'),{recursive:true});
    diagnostic(receiptPath);
    const r = await run('default-control',['npm','--prefix',copiedUi,'test','--','plant-default','-t',diagnosticTests]);
    if (r.code !== 0) throw Error('Default control must pass');
  } else {
    if (!plant || !report.some(r => r.name === 'default-control' && r.code === 0)) throw Error('Plant or passing control missing');
    restore();
    if (stage !== 'restore') {
      if (plant.replace && !original.includes(plant.replace[0])) throw Error('Exact plant target missing');
      writeFileSync(target,plant.replace ? original.replace(...plant.replace) : original+plant.append);
    }
    if (stage === 'stale') {
      const r = await run(`${name}-stale`,['npm','--prefix',copiedUi,'test','--','state-shades']);
      if (r.code === 0 || !r.tail.includes('Stale browser-resolved state surfaces')) throw Error('Expected stale rejection');
    } else if (stage === 'capture') {
      const capture = resolve(scratch,`${name}-capture`); mkdirSync(capture,{recursive:true});
      const r = await run(`${name}-regenerate-default`,['npm','--prefix',copiedUi,'run','resolve-state-surfaces'],
        {STATE_SURFACES_SCRATCH:capture,STATE_SURFACES_CONDITION:'default',STATE_SURFACES_OUTPUT:resolve(capture,'default.json')});
      if (r.code !== 0 && !r.tail.includes('Measurement failure')) throw Error('Unrelated capture failure');
    } else if (stage === 'fresh') {
      const capture = report.findLast(r => r.name === `${name}-regenerate-default`);
      if (!capture) throw Error('Missing default regeneration');
      if (capture.code !== 0) report.push({name:`${name}-measurement-rejected`,reason:capture.tail});
      else {
        const path = resolve(scratch,`${name}-capture/default.json`);
        const partial = JSON.parse(readFileSync(path,'utf8'));
        if (partial.proof.acceptanceComplete !== false || Object.keys(partial.conditions).join() !== 'default') throw Error('Diagnostic scope escaped default');
        diagnostic(path);
        const r = await run(`${name}-fresh-default`,['npm','--prefix',copiedUi,'test','--','plant-default','-t',diagnosticTests]);
        if (r.code === 0) throw Error('Regenerated default plant unexpectedly accepted');
        report.push({name:`${name}-scope`,condition:'default',acceptanceComplete:false,renderCount:partial.proof.renderCount,mutatedPath:plant.path,mutation:plant.replace ?? plant.append});
      }
    } else if (stage === 'restore') {
      report.push({name:`${name}-restored`,byteIdentical:readFileSync(target,'utf8')===original,receiptRestored:readFileSync(receiptPath).equals(originalReceipt)});
    } else throw Error('Unknown stage');
  }
} finally { if (stage !== 'control') restore(); writeFileSync(ledger,JSON.stringify(report,null,2)+'\n'); }

// Codex, GPT-6.
