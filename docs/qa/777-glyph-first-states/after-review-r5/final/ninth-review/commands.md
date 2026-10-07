# Ninth Review Commands

Scope is `ui/` and `docs/`; the coordinator gate at `198e4e03` stands.
The single full regeneration uses the checked-in 4123-second bound. UI suites
and plant children use 589-second bounds; wrapper exits and arguments are in
[gates.json](gates.json). Guarded reachability unsets PG/live/secret-store flags.

## Media/Declaration Regressions, Check, Build and Reachability

```sh
npm --prefix ui test -- media-state-shades
npm --prefix ui run check
npm --prefix ui run build
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT \
  -u NEXUS_RUN_POSTGRES -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_SECRET_STORE \
  PYTHONPATH="$PWD" /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py
```

95 unit regressions pass through the real PostCSS parse. Check and build exit 0.
Reachability passes 54 tests; secret-store guard active, `nexus-api` and disposable
keychain denied. [Unit](unit.log), [check](check.log), [build](build.log),
[reachability](reachability.log), [check/build exits](check-build.json),
[reachability exit](reachability.json).

## Full Regeneration and Baseline Comparison

```sh
STATE_SURFACES_SCRATCH="$PWD/scratchpad/777-S2/after-review-r9/capture" \
STATE_SURFACES_OUTPUT="$PWD/scratchpad/777-S2/after-review-r9/regenerated.json" \
  npm --prefix ui run resolve-state-surfaces
node --max-old-space-size=8192 scratchpad/777-S2/after-review-r9/compare.mjs
```

Both exit 0. One full regeneration captures 101,742 samples over 27 conditions,
with zero page errors and network requests. The declaration scan searches `if(`
and `light-dark(` across 4,707 declarations, with zero refusals. Baseline bytes
match `0ba97d93`’s LFS OID. The entire media inventory agrees except the new scan
record; every paint, mask, geometry, opacity and settled-state sample agrees.
No samples are missing or additional. Runtime settle timings, Escape-needed flags
and 327 exact trailing dismissal-action descriptions differ only in the established
bookkeeping exclusions. The shipping receipt is replaced only after comparison
passes. [Regeneration](regeneration.log), [exit](regeneration-exit.json),
[comparison](receipt-comparison.json), [comparison output](comparison.log).

## Focused and Full UI Suites

```sh
npm --prefix ui test -- state-shades StateGlyphs shell-accessibility
npm --prefix ui test
```

Both exit 0: focused 121 passed, full UI 599 passed.
[Focused](focused.log), [full](full.log), [arguments/exits/bounds](gates.json).

## Inline Conditional Plant and Restoration

```sh
STATE_SURFACES_SCRATCH="$PWD/scratchpad/777-S2/after-review-r9/plants" \
  node ui/scripts/state-surfaces/plants.mjs --stage control
# Each stage is invoked separately, in this order, with the same scratch:
# --plant inline-if-media --stage stale
# --plant inline-if-media --stage capture
# --plant inline-if-media --stage fresh
# --plant inline-if-media --stage restore
npm --prefix ui test -- state-shades
```

All protocol wrappers exit 0. The unplanted control passes 106 tests. The stale
Vitest child exits 1 with the named freshness rejection; regeneration exits 1 with:

```text
Error: Unemulatable at-rule/media preludes or declaration functions: .key-row.optional { opacity }: if(
```

The exact [emitted rule](plants/emitted-inline-rule.css) survives the production
build. The refusal occurs before browser capture and is the detection. The fresh
stage records that refusal; no shade change or filtered receipt is claimed.
Saved/live/scratch/HEAD restoration hashes agree, and the restored suite passes
106 tests. [Ledger](plants/plants-proof.json), [snapshot](plants/before-plants.json),
[control](plants/control.log), [stale](plants/inline-if-media-stale.log),
[refusal](plants/inline-if-media-regenerate-default.log), [restored](restored.log).

## Declared-Condition Coverage and Residual

Coverage is scoped to the emitted CSS’s declared conditions: at-rule preludes and
the inline conditionals refused above. Viewport-relative math in paint-affecting
properties (`opacity: calc(100vw / 2000px)`), `env()`, scripts reading `matchMedia`,
and user-agent or extension stylesheets are not inventoried or refused. This is
a documented residual; no code is added for it.

## Final Artifact Index and Self-Check

The [prior audit](prior-index-check.json) reproduces exactly three stale entries;
the other 1,113 match. The [negative check](prior-index-refusal.log) exits 1,
naming a stale artifact. After finalizing every indexed file, the final step is:

```sh
node docs/qa/777-glyph-first-states/after-review-r5/final/ninth-review/artifact-index.mjs --write \
  > docs/qa/777-glyph-first-states/after-review-r5/final/ninth-review/artifact-index-check.log
```

This writes the index last, re-reads it and every indexed file, and fails the stage
on any SHA-256 or byte-count mismatch. The check output is excluded from the index
because it is produced by the check. Exit 0; exact tail:

```text
Artifact index self-check: 1163 indexed files re-read; 0 mismatches; PASS
```

[Check output](artifact-index-check.log), [index](../artifact-hashes.json).

## Main Merge and Scope

```sh
git fetch origin main
git merge origin/main -m 'Merge origin/main before the ninth-review push' -m 'Codex, GPT-6.'
git diff --name-only 0ba97d93 HEAD
```

Merge exits 0 with `Already up to date.` [Merge output](merge-main.log).
The diff stays inside `ui/` and `docs/`; the coordinator gate at `198e4e03` stands.
PR #1099 remains open for the coordinator.

Codex, GPT-6.
