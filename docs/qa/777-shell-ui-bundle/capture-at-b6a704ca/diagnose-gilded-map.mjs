import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
const root = '/Users/pythagor/.codex/worktrees/resume-shell-ui/nexus';
const scratch = '/tmp/nexus-777-shell-ui-4ae8b8d2';
const require = createRequire(`${root}/ui/package.json`);
const { transformSync } = createRequire(require.resolve('vite'))('esbuild');
const mathSource = readFileSync(`${root}/ui/client/src/state-shades-measurement.ts`, 'utf8');
const math = transformSync(mathSource, { loader: 'ts', format: 'esm' }).code;
const { ciede2000, deutanLinearLab } = await import(`data:text/javascript;base64,${Buffer.from(math).toString('base64')}`);
const oid = '70925b79f007e7e632b063ba2434cb68d7769da404fca6b9e60295081c36a6e4';
const oldBytes = readFileSync(`/Users/pythagor/nexus/.git/lfs/objects/70/92/${oid}`);
assert.equal(createHash('sha256').update(oldBytes).digest('hex'), oid);
const old = JSON.parse(oldBytes);
const current = JSON.parse(readFileSync(`${root}/ui/client/src/state-surfaces.resolved.json`));
assert.equal(current.inputs.sha256, '4b8a9bbd8b880dc12ff8a534e7ef819eaa72fe376f0e28a8a295f9754d976fe7');
const oldTable = JSON.parse(execFileSync('git', ['show', 'HEAD:docs/qa/777-glyph-first-states/amendment-2/gilded-joint.json'], { cwd: root, maxBuffer: 20000000 }));
const newTable = JSON.parse(readFileSync(`${root}/docs/qa/777-shell-ui-bundle/state-surfaces/gilded-joint.json`));
const output = { input_fingerprint: current.inputs.sha256, legacy_oid: oid, math_sha256: createHash('sha256').update(mathSource).digest('hex'), cases: [] };
for (const [receiptName, receipt, table] of [['legacy', old, oldTable], ['v2', current, newTable]]) {
  for (const [paletteName, assignment] of [['old', oldTable.assignment], ['new_search_choice', newTable.assignment]]) {
    const measured = [];
    for (const row of table.measurements.filter(m => m.surface === 'map')) {
      const context = `map/${row.context}`;
      const phases = /\/motion\/(start|trough)$/.test(row.condition)
        ? Object.keys(receipt.conditions).filter(id => id.replace(/\/(start|trough)$/, '') === row.condition.replace(/\/(start|trough)$/, ''))
        : [row.condition];
      assert.equal(phases.length, row.condition.includes('/motion/') ? 2 : 1);
      let minimum = Infinity;
      let witness;
      for (const first of phases) for (const second of phases) {
        const colors = row.states.map((state, i) => {
          const pigment = `--state-map-${state}`;
          return receipt.conditions[i === 0 ? first : second].Gilded.candidates[pigment][assignment[pigment]][context].meanLinear;
        });
        const delta = ciede2000(...colors.map(deutanLinearLab));
        if (delta < minimum) { minimum = delta; witness = { phases: [first, second], colors }; }
      }
      measured.push({ condition: row.condition, context, states: row.states, delta: minimum, ...witness });
    }
    const minimum = Math.min(...measured.map(m => m.delta));
    output.cases.push({ receipt: receiptName, palette: paletteName, minimum,
      assignment: Object.fromEntries(Object.entries(assignment).filter(([key]) => key.startsWith('--state-map-'))),
      minimizers: measured.filter(m => m.delta === minimum) });
  }
}
writeFileSync(`${scratch}/capture-v2/gilded-map-candidate-diagnosis.json`, JSON.stringify(output, null, 2) + '\n');
const chosenAudit = [];
const roots = {
  memory: { normal: '--state-mem-normal', over: '--state-mem-over' },
  delete: { unarmed: '--state-delete-unarmed', armed: '--state-delete-armed' },
  map: Object.fromEntries(['rest', 'current', 'selected', 'hovered'].map(s => [s, `--state-map-${s}`])),
  key: { 'optional-absent': '--state-key-absent', 'required-missing': '--state-key-missing', present: '--state-key-present', verified: '--state-key-verified' },
};
for (const theme of ['Veil', 'Gilded', 'Vector']) {
  const table = JSON.parse(readFileSync(`${root}/docs/qa/777-shell-ui-bundle/state-surfaces/${theme.toLowerCase()}-joint.json`));
  const changed = [];
  for (const row of table.measurements) {
    const phases = /\/motion\/(start|trough)$/.test(row.condition)
      ? Object.keys(current.conditions).filter(id => id.replace(/\/(start|trough)$/, '') === row.condition.replace(/\/(start|trough)$/, ''))
      : [row.condition];
    let delta = Infinity, rgb;
    for (const first of phases) for (const second of phases) {
      const colors = row.states.map((state, i) => {
        const pigment = roots[row.surface][state];
        return current.conditions[i === 0 ? first : second][theme].candidates[pigment][table.assignment[pigment]][`${row.surface}/${row.context}`].meanLinear;
      });
      const next = ciede2000(...colors.map(deutanLinearLab));
      if (next < delta) { delta = next; rgb = colors; }
    }
    if (delta !== row.delta || JSON.stringify(rgb) !== JSON.stringify(row.rgb))
      changed.push({ condition: row.condition, surface: row.surface, context: row.context,
        states: row.states, shipped: { delta: row.delta, rgb: row.rgb }, chosen: { delta, rgb } });
  }
  chosenAudit.push({ theme, compared: table.measurements.length, changed_count: changed.length, changed });
}
writeFileSync(`${scratch}/capture-v2/chosen-vs-shipped-audit.json`, JSON.stringify(chosenAudit, null, 2) + '\n');
console.log(JSON.stringify({ cases: output.cases.map(({receipt, palette, minimum}) => ({receipt,palette,minimum})), chosen_vs_shipped: chosenAudit.map(({theme, compared, changed_count}) => ({theme,compared,changed_count})) }, null, 2));
