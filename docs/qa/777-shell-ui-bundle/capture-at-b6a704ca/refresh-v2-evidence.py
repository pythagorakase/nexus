"""Refresh external evidence from the unchanged evaluator's measured output."""

import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path('/Users/pythagor/.codex/worktrees/resume-shell-ui/nexus')
SCRATCH = Path('/tmp/nexus-777-shell-ui-4ae8b8d2')
OUT = ROOT / 'docs/qa/777-shell-ui-bundle/state-surfaces'
DEST = ROOT / 'docs/qa/777-glyph-first-states/amendment-2'
mapping = json.loads((SCRATCH / 'legacy-condition-map-v2.json').read_text())
old_manifest = json.loads((DEST / 'theme-exceptions.json').read_text())
new_manifest = {}
report = {'source_head': mapping['source_head'], 'files': {}, 'themes': {}}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def renamed(key):
    matches = [p for p in mapping['legacy_fine_mapping']
               if key.startswith(p['old_id'] + '/')]
    assert len(matches) == 1, key
    pair = matches[0]
    return pair['new_id'] + key[len(pair['old_id']):]


for theme in ['Veil', 'Gilded', 'Vector']:
    name = f'{theme.lower()}-joint.json'
    source = OUT / name
    data = json.loads(source.read_text())
    assert data['theme'] == theme
    for factor in data['factorMaxima']:
        if factor['feasible']:
            assert factor['shippedMinimum'] >= 15
        else:
            assert abs(factor['shippedMinimum'] - factor['best']) < 1e-10
    shortfalls = [m for m in data['measurements'] if m['delta'] < 15]
    assert all(m['signatures'][0] != m['signatures'][1] for m in shortfalls)
    keys = [f"{m['condition']}/{m['surface']}/{m['context']}/{'/'.join(m['states'])}"
            for m in shortfalls]
    assert len(keys) == len(set(keys))
    renamed_old = {renamed(key) for key in old_manifest[theme]}
    fine = {key for key in keys if '/pointer=fine/' in key}
    coarse = [key for key in keys if '/pointer=coarse/' in key]
    added = sorted(fine - renamed_old)
    removed = sorted(renamed_old - fine)
    assert all(key.startswith(('w1-639/', 'w640-760/')) for key in added + removed)
    report['themes'][theme] = {
        'old_count': len(old_manifest[theme]), 'new_count': len(keys),
        'retained_renamed_fine_count': len(fine & renamed_old),
        'narrow_fine_added': added, 'narrow_fine_removed': removed,
        'new_coarse_coverage': coarse, 'factorMaxima': data['factorMaxima'],
    }
    target = DEST / name
    report['files'][name] = {'before_sha256': digest(target),
                            'after_sha256': digest(source)}
    shutil.copyfile(source, target)
    new_manifest[theme] = keys

target = DEST / 'theme-exceptions.json'
old_hash = digest(target)
target.write_text(json.dumps(new_manifest, indent=2) + '\n')
report['files']['theme-exceptions.json'] = {
    'before_sha256': old_hash, 'after_sha256': digest(target)}
(OUT / 'manifest-refresh.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({theme: {key: len(value) if isinstance(value, list) else value
                         for key, value in values.items() if key != 'factorMaxima'}
                  for theme, values in report['themes'].items()}, indent=2))
