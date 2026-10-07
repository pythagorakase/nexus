# Eighth Review Commands

The single full regeneration uses the checked-in 4123-second bound and writes
to scratch for comparison against `743ddab3` before replacing the shipping
receipt. Focused/full UI suite invocations and plant children are bounded at 589 seconds.
Reachability keeps the secret-store guard active and unsets PG/live/secret-store
flags. Scope is `ui/` and `docs/`; the coordinator gate at `198e4e03` stands.

## Media Regressions

```sh
npm --prefix ui test -- media-state-shades
```

82 passed. [Complete output](unit.log).

## Check and Build

```sh
npm --prefix ui run check
npm --prefix ui run build
```

Both exit 0. [Check output](check.log), [build output](build.log).

## Reachability

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT \
  -u NEXUS_RUN_POSTGRES -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_SECRET_STORE \
  PYTHONPATH="$PWD" /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py
```

54 passed. Secret-store guard active; `nexus-api` and disposable keychain denied.
[Complete output](reachability.log).

## Full Regeneration and Comparison

```sh
STATE_SURFACES_SCRATCH="$PWD/scratchpad/777-S2/after-review-r8/capture" \
STATE_SURFACES_OUTPUT="$PWD/scratchpad/777-S2/after-review-r8/regenerated.json" \
  npm --prefix ui run resolve-state-surfaces
node --max-old-space-size=8192 scratchpad/777-S2/after-review-r8/compare.mjs
```

Both exit 0. The single full regeneration captures 101,742 samples over 27
conditions, with zero page errors and zero network requests. Its fingerprint is
`d56158e33b4af8e762b64af496ab2418b5c74ff60fc68c25bad59bf763c847af`.
[Complete regeneration output](regeneration.log).

[Comparison](receipt-comparison.json) confirms the baseline bytes match
`743ddab3`'s LFS OID, all 27 condition variants agree, all 101,742 samples agree,
and no samples are missing or additional. Every paint, mask, geometry, opacity
and settled-state field agrees. Runtime settle timings, Escape-needed flags and
the exact action-description suffix for that same dismissal branch are excluded,
as in Round 7; 382 raw action descriptions differ only in that branch.
The measured-sample hash remains
`1d57b4ebf342ac17f64427645e9c110b0dffc05fe8b27abc10d30fdcb0e45f97`.
[Comparison output](comparison.log). The shipping receipt was replaced only
after this comparison passed; no palette, table or exception changed.

## Focused and Full UI Suites

```sh
npm --prefix ui test -- state-shades StateGlyphs shell-accessibility
npm --prefix ui test
```

Both exit 0 under individual 589-second bounds: focused **108 passed**, full
**586 passed**. [Focused output](focused.log), [full output](full.log),
[exact arguments, exits and bounds](gates.json).

## Uppercase-Media Plant

```sh
STATE_SURFACES_SCRATCH="$PWD/scratchpad/777-S2/after-review-r8/plants" \
  node ui/scripts/state-surfaces/plants.mjs --stage control
# Each stage below was invoked separately, in this order:
# --plant uppercase-media-width --stage stale
# --plant uppercase-media-width --stage capture
# --plant uppercase-media-width --stage fresh
# --plant uppercase-media-width --stage restore
python3 scratchpad/777-S2/after-review-r8/plant-means.py
npm --prefix ui test -- state-shades
```

Every protocol stage exits 0 under the checked-in 589-second child bound; the
stale and fresh Vitest children exit 1 as required. Control and restored suites
both pass **93 tests**. The exact `@MEDIA` rule survives the production build
[unchanged](plants/emitted-uppercase-rule.css), contributes the 759px band, and
changes all [nine optional-key rest means](plants/optional-key-means.json) at
759×900/dark/reduce (.5 → .35 opacity). The filtered capture succeeds with
3,982 samples and stays `acceptanceComplete=false`.

The fresh `browser_measurements_match_recorded_tables` shade assertion is red;
four other diagnostics pass and six full-inventory assertions are skipped.
Restoration compares saved hashes with the live worktree, scratch copy and HEAD
before restoration writes; all agree. [Ledger with exact mutation, arguments,
exits, viewport and hashes](plants/plants-proof.json), [before snapshot](plants/before-plants.json),
[uncertified partial receipt](plants/partial-receipt.json), [control output](plants/control.log),
[stale output](plants/uppercase-media-width-stale.log),
[capture output](plants/uppercase-media-width-regenerate-default.log),
[fresh output](plants/uppercase-media-width-fresh-default.log),
[restored output](restored.log). The restored invocation has a separate
589-second bound recorded in [gates.json](gates.json).

Codex, GPT-6.
