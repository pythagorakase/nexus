"""Compare stable painted metrics and geometry, with explicit legacy-ID mapping."""

from collections import Counter
import hashlib
import json
from pathlib import Path

SCRATCH = Path('/tmp/nexus-777-shell-ui-4ae8b8d2')
ROOT = Path('/Users/pythagor/.codex/worktrees/resume-shell-ui/nexus')
mapping = json.loads((SCRATCH / 'legacy-condition-map-v2.json').read_text())
oid = mapping['legacy_receipt_oid']
legacy_path = Path('/Users/pythagor/nexus/.git/lfs/objects') / oid[:2] / oid[2:4] / oid
assert hashlib.file_digest(legacy_path.open('rb'), 'sha256').hexdigest() == oid
old = json.loads(legacy_path.read_text())
new = json.loads((ROOT / 'ui/client/src/state-surfaces.resolved.json').read_text())
assert new['proof']['acceptanceComplete'] is True
assert new['inputs']['sha256'] == '4b8a9bbd8b880dc12ff8a534e7ef819eaa72fe376f0e28a8a295f9754d976fe7'
pairs = mapping['legacy_fine_mapping']
old_ids = [pair['old_id'] for pair in pairs]
fine_ids = [pair['new_id'] for pair in pairs]
coarse_ids = mapping['new_coarse_conditions']
assert len(old_ids) == len(set(old_ids)) == 27
assert len(fine_ids) == len(set(fine_ids)) == 27
assert len(coarse_ids) == len(set(coarse_ids)) == 6
assert set(old_ids) == set(old['conditions'])
assert set(fine_ids).isdisjoint(coarse_ids)
assert set(fine_ids) | set(coarse_ids) == set(new['conditions'])
old_variants = {item['id']: item for item in old['media']['variants']}
new_variants = {item['id']: item for item in new['media']['variants']}
assert len(old_variants) == len(old['media']['variants']) == 27
assert len(new_variants) == len(new['media']['variants']) == 33
assert set(old_variants) == set(old['conditions'])
assert set(new_variants) == set(new['conditions'])
for pair in pairs:
    for variant in (old_variants[pair['old_id']], new_variants[pair['new_id']]):
        assert variant['viewport'] == pair['viewport'], pair
        assert variant['reducedMotion'] == pair['motion'], pair
        assert variant.get('animationPhase') == pair['phase'], pair
    assert new_variants[pair['new_id']]['features']['pointer'] == 'fine', pair
for condition in coarse_ids:
    assert new_variants[condition]['features']['pointer'] == 'coarse'
    assert new_variants[condition]['viewport']['width'] <= 760
metrics = ('meanLinear', 'controlMeanLinear', 'maskSize', 'coreSize', 'histogram', 'width', 'height', 'effectiveOpacity')
geometry = ('box',)
interactions = ('selector', 'pseudos', 'target', 'stateAttributes', 'animationsRunning', 'mapPart')


def stable_settle(value):
    """Keep all settle semantics; omit only timings and the DOM signature hash."""
    if isinstance(value, dict):
        return {key: stable_settle(item) for key, item in value.items()
                if key not in ('settleWaitMs', 'signature')}
    if isinstance(value, list):
        return [stable_settle(item) for item in value]
    return value


def samples(data):
    for phase in ('shipped', 'before'):
        for context, states in data[phase].items():
            for state, sample in states.items():
                yield (phase, context, state), sample
    for root, values in data['candidates'].items():
        for value, contexts in values.items():
            for context, sample in contexts.items():
                yield ('candidate', root, value, context), sample


out = ROOT / 'docs/qa/777-shell-ui-bundle/state-surfaces'
out.mkdir(exist_ok=True)
counts = Counter()
changed_by_condition = Counter()
with (out / 'changed-samples.jsonl').open('w') as log:
    for pair in pairs:
        assert set(old['conditions'][pair['old_id']]) == {'Veil', 'Gilded', 'Vector'}
        assert set(new['conditions'][pair['new_id']]) == {'Veil', 'Gilded', 'Vector'}
        for theme in ('Veil', 'Gilded', 'Vector'):
            before = dict(samples(old['conditions'][pair['old_id']][theme]))
            after = dict(samples(new['conditions'][pair['new_id']][theme]))
            assert before.keys() == after.keys(), (pair, theme)
            for key in before:
                counts['compared'] += 1
                delta = {field: {'before': before[key][field], 'after': after[key][field]}
                         for field in metrics + geometry + interactions
                         if before[key][field] != after[key][field]}
                old_settle = stable_settle(before[key]['settleCriteria'])
                new_settle = stable_settle(after[key]['settleCriteria'])
                if old_settle != new_settle:
                    delta['settleCriteria'] = {'before': old_settle, 'after': new_settle}
                if not delta:
                    counts['identical_stable_fields'] += 1
                    continue
                metric_changed = any(field in delta for field in metrics)
                counts['metric_changed' if metric_changed else 'metadata_only_changed'] += 1
                counts['narrow_changed' if pair['viewport']['width'] <= 760 else 'wide_changed'] += 1
                changed_by_condition[pair['new_id']] += 1
                log.write(json.dumps({'old_condition': pair['old_id'], 'condition': pair['new_id'],
                    'viewport': pair['viewport'], 'theme': theme, 'sample': key,
                    'metric_changed': metric_changed, 'changes': delta}) + '\n')
summary = {'source_head': mapping['source_head'], 'legacy_receipt_oid': oid,
           'legacy_conditions_compared': len(mapping['legacy_fine_mapping']),
           'new_coarse_conditions': mapping['new_coarse_conditions'],
           'counts': dict(counts), 'changed_by_condition': dict(changed_by_condition),
           'comparison_fields': {'painted_metrics': metrics, 'geometry': geometry, 'interactions': interactions,
                                 'settleCriteria': 'all fields recursively except settleWaitMs and signature'},
           'excluded_observational_fields': ['action prose', 'settleWaitMs', 'settleCriteria timings and DOM signature', 'capture filenames'],
           'interpretation': 'Every changed sample is named; causes require source/geometry review, not automatic acceptance.'}
(out / 'comparison-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
