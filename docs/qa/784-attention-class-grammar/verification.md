# 784-S1 Verification: Attention-Class Wire Grammar and Card Blocks

- Date: 2026-10-01
- Probe commit: `a3e6d109` (the `commit` field of the JSON below; the later commits on the branch add only the reachability classification and this file)
- Base: `origin/main` at `56c884e7`
- Command: `PYTHONPATH=$PWD $PY scripts/qa_shift/attention_class_grammar_probe.py > probe.json` with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset; exit status 0. Stderr carried only the two `INFO Replaying cards and exposures on <corpus>` lines.
- Model and tokenizer: `gpt-6-astra` for both seats (`apex.gaia_model` is unset), `o200k_base`.

**The probe decides nothing.** It reports numbers for the coordinator, who records them on #784 and applies the owner's test (switch to replacing the flags only if that gives the smaller grammar).

Every database read is read-only: `main` prepends `-c default_transaction_read_only=on` to the ambient `PGOPTIONS` before the first read, checks `transaction_read_only = on` through `connection_kwargs(<dbname>)` for `save_04` and `ref_codex_bakeoff_2026_07`, and runs its own SQL through `read_only_cursor` (read-only, repeatable read, checked again). No paid call, no gateway, no write.

## Wire Section

Under both options the class is authored on the server, and no wire model reads `Branch`, `Template` or the draft dict, so `extend_off_wire` and `replace_off_wire` rebuild the production renderings. The probe walked every property name of every measured strict and lenient schema (`$defs` included) and found none of `drive_band`, `promotable` or `attention`. `class_on_wire_ceiling` is the cost if a later slice had to put the class on the wire, and it is the same under both options. The probe asserted its shape: only the adjudication definition changes, by the property `attention` (plus its `required` entry in strict), and each guide gains exactly one line at the end of the `OrreryAdjudication{...}` block.

| Seat | Rendering | Variant | Bytes | Tokens | Δ Bytes | Δ Tokens |
|---|---|---|---|---|---|---|
| gaia | strict | head | 14,427 | 3,260 | +0 | +0 |
| gaia | strict | extend_off_wire | 14,427 | 3,260 | +0 | +0 |
| gaia | strict | replace_off_wire | 14,427 | 3,260 | +0 | +0 |
| gaia | strict | class_on_wire_ceiling | 14,610 | 3,300 | +183 | +40 |
| gaia | lenient | head | 13,329 | 2,942 | +0 | +0 |
| gaia | lenient | extend_off_wire | 13,329 | 2,942 | +0 | +0 |
| gaia | lenient | replace_off_wire | 13,329 | 2,942 | +0 | +0 |
| gaia | lenient | class_on_wire_ceiling | 13,487 | 2,975 | +158 | +33 |
| gaia | guide | head | 2,372 | 615 | +0 | +0 |
| gaia | guide | extend_off_wire | 2,372 | 615 | +0 | +0 |
| gaia | guide | replace_off_wire | 2,372 | 615 | +0 | +0 |
| gaia | guide | class_on_wire_ceiling | 2,432 | 628 | +60 | +13 |
| gaia_registry | strict | head | 23,846 | 5,806 | +0 | +0 |
| gaia_registry | strict | extend_off_wire | 23,846 | 5,806 | +0 | +0 |
| gaia_registry | strict | replace_off_wire | 23,846 | 5,806 | +0 | +0 |
| gaia_registry | strict | class_on_wire_ceiling | 24,029 | 5,846 | +183 | +40 |
| single_pass | strict | head | 20,136 | 4,536 | +0 | +0 |
| single_pass | strict | extend_off_wire | 20,136 | 4,536 | +0 | +0 |
| single_pass | strict | replace_off_wire | 20,136 | 4,536 | +0 | +0 |
| single_pass | strict | class_on_wire_ceiling | 20,319 | 4,576 | +183 | +40 |
| single_pass | lenient | head | 18,596 | 4,092 | +0 | +0 |
| single_pass | lenient | extend_off_wire | 18,596 | 4,092 | +0 | +0 |
| single_pass | lenient | replace_off_wire | 18,596 | 4,092 | +0 | +0 |
| single_pass | lenient | class_on_wire_ceiling | 18,754 | 4,125 | +158 | +33 |
| single_pass | guide | head | 6,773 | 1,492 | +0 | +0 |
| single_pass | guide | extend_off_wire | 6,773 | 1,492 | +0 | +0 |
| single_pass | guide | replace_off_wire | 6,773 | 1,492 | +0 | +0 |
| single_pass | guide | class_on_wire_ceiling | 6,868 | 1,512 | +95 | +20 |

All `head` numbers match the coordinator's reference numbers: Gaia strict 14,427 / 3,260, lenient 13,329 / 2,942, guide 2,372 / 615; single-pass strict 20,136 / 4,536, lenient 18,596 / 4,092, guide 6,773 / 1,492; registry Gaia on `save_04` strict 23,846 / 5,806. The ceiling deltas match the prototype: Gaia strict +183 / +40, Gaia guide +60 / +13, single-pass guide +95 / +20.

## Card-Line Section

Per-line token delta of appending ` · <label>` to each line of the `head` card block (Gaia estimator).

| Corpus | Label | Lines | Min Δ Tokens | Max Δ Tokens |
|---|---|---|---|---|
| save_04 | background | 5 | +2 | +2 |
| save_04 | meaningful | 5 | +2 | +2 |
| save_04 | urgent | 5 | +2 | +2 |
| ref_codex_bakeoff_2026_07 | background | 5 | +2 | +2 |
| ref_codex_bakeoff_2026_07 | meaningful | 5 | +2 | +2 |
| ref_codex_bakeoff_2026_07 | urgent | 5 | +2 | +2 |

## Card-Block Replay

Each corpus's one incubator snapshot (`save_04` parent 49 with 22 resolutions, `ref_codex_bakeoff_2026_07` parent 147 with 8; both predate #924, so `position` is null and each card takes its index). Render caps from `load_settings().orrery.prompt` (`max_rendered_proposals` 5). Rosters are the 784-Q1 candidates: `R1` = `train`, `run_errands`, `stroll`, `upkeep`, `recreate`; `R2` = `R1` plus `sleep`, `eat`, `drink`, an upper bound because need severity is not stored. Tokens are the Gaia estimator on the arm's lines joined with a newline. The full proposal IDs are in the JSON below.

| Corpus | Roster | Arm | Lines | Tokens | Proposal IDs (template:hash prefix) |
|---|---|---|---|---|---|
| save_04 | — | head | 5 | 110 | honor_debt:ff450d8c, hide:85dcc9f3, stroll:a339b89d, upkeep:f0d332a1, drink:850b31cf |
| save_04 | R1 | drop_only | 3 | 70 | honor_debt:ff450d8c, hide:85dcc9f3, drink:850b31cf |
| save_04 | R1 | refill | 5 | 115 | honor_debt:ff450d8c, hide:85dcc9f3, drink:850b31cf, drink:9b2c010e, drink:b299bdd9 |
| save_04 | R1 | head_marked | 5 | 120 | honor_debt:ff450d8c, hide:85dcc9f3, stroll:a339b89d, upkeep:f0d332a1, drink:850b31cf |
| save_04 | R1 | refill_marked | 5 | 125 | honor_debt:ff450d8c, hide:85dcc9f3, drink:850b31cf, drink:9b2c010e, drink:b299bdd9 |
| save_04 | R2 | drop_only | 2 | 48 | honor_debt:ff450d8c, hide:85dcc9f3 |
| save_04 | R2 | refill | 5 | 135 | honor_debt:ff450d8c, hide:85dcc9f3, surveil:93626842, surveil:19b8dd6d, check_on_dependent:b141c5fd |
| save_04 | R2 | head_marked | 5 | 120 | honor_debt:ff450d8c, hide:85dcc9f3, stroll:a339b89d, upkeep:f0d332a1, drink:850b31cf |
| save_04 | R2 | refill_marked | 5 | 145 | honor_debt:ff450d8c, hide:85dcc9f3, surveil:93626842, surveil:19b8dd6d, check_on_dependent:b141c5fd |
| ref_codex_bakeoff_2026_07 | — | head | 5 | 119 | drink:495ac0c7, run_errands:cbeef034, run_errands:305e6e93, drink:2b39acf7, run_errands:2822439f |
| ref_codex_bakeoff_2026_07 | R1 | drop_only | 2 | 48 | drink:495ac0c7, drink:2b39acf7 |
| ref_codex_bakeoff_2026_07 | R1 | refill | 2 | 48 | drink:495ac0c7, drink:2b39acf7 |
| ref_codex_bakeoff_2026_07 | R1 | head_marked | 5 | 129 | drink:495ac0c7, run_errands:cbeef034, run_errands:305e6e93, drink:2b39acf7, run_errands:2822439f |
| ref_codex_bakeoff_2026_07 | R1 | refill_marked | 2 | 52 | drink:495ac0c7, drink:2b39acf7 |
| ref_codex_bakeoff_2026_07 | R2 | drop_only | 0 | 0 | — |
| ref_codex_bakeoff_2026_07 | R2 | refill | 0 | 0 | — |
| ref_codex_bakeoff_2026_07 | R2 | head_marked | 5 | 129 | drink:495ac0c7, run_errands:cbeef034, run_errands:305e6e93, drink:2b39acf7, run_errands:2822439f |
| ref_codex_bakeoff_2026_07 | R2 | refill_marked | 0 | 0 | — |

## Exposure Replay

Read-only SQL over `orrery_prompt_exposures` (kind `resolution`), `orrery_adjudication_log` and `orrery_resolutions`. The refill pool is the `orrery_resolutions` rows with no exposure row of the same `(tick_chunk_id, template_id, binding_hash)`. **The refill pool is an upper bound**: the rank of an unshown draft is not stored, so the replay cannot say which unshown drafts would have been next in line.

| Corpus | Roster | Ticks | Resolution Exposures | Roster Exposures | All-Roster Ticks | Defer | Replace | Void | Refill Pool | Refill Pool Outside Roster |
|---|---|---|---|---|---|---|---|---|---|---|
| save_04 | R1 | 44 | 173 | 99 | 4 | 33 | 1 | 22 | 53 | 16 |
| save_04 | R2 | 44 | 173 | 167 | 38 | 80 | 1 | 38 | 53 | 15 |
| ref_codex_bakeoff_2026_07 | R1 | 109 | 479 | 179 | 0 | 34 | 5 | 28 | 250 | 137 |
| ref_codex_bakeoff_2026_07 | R2 | 109 | 479 | 421 | 70 | 183 | 10 | 75 | 250 | 118 |

## 781-S1 Comparison

No 781-S1 pull request was open when this one was opened (2026-10-01), so its baseline rows could not be compared with the `head` rows above. The coordinator compares them when that PR exists; the `head` rows should be equal for the same seat and rendering.

## Test Tails

`NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_attention_class_grammar_probe.py tests/test_orrery/test_gaia_registry_schema_pg.py tests/test_skald_wire.py tests/test_owner_target_guard.py` (`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT` unset; the two skips are the live-LLM gates `NEXUS_638_ENUM_E2E` and `NEXUS_639_PRESENCE_E2E`):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 5 targets: postgres, qa638_*, qa640_784s1_*, qa640_811_gaia_scene_*, qa885_presence_baseline_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
184 passed, 2 skipped, 2 warnings in 9.74s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

`$PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery` (offline):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2667 passed, 428 skipped, 8 warnings in 395.65s (0:06:35)
```

`$PY -m pytest -q tests/test_api tests/test_orrery` (offline):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1824 passed, 745 skipped, 7 warnings in 35.60s
```

## Full Probe JSON

```json
{
  "header": {
    "commit": "a3e6d1095b9a372ee3f75c3d130ba35575168fa3",
    "gaia_model": "gpt-6-astra",
    "single_pass_model": "gpt-6-astra",
    "gaia_tokenizer": "o200k_base",
    "single_pass_tokenizer": "o200k_base",
    "registry_dbname": "save_04",
    "registry_digest": "5a2f4f690ad9",
    "corpora": [
      "save_04",
      "ref_codex_bakeoff_2026_07"
    ],
    "decides": "nothing"
  },
  "wire": [
    {
      "seat": "gaia",
      "rendering": "strict",
      "variant": "head",
      "bytes": 14427,
      "tokens": 3260,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "gaia",
      "rendering": "strict",
      "variant": "extend_off_wire",
      "bytes": 14427,
      "tokens": 3260,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "gaia",
      "rendering": "strict",
      "variant": "replace_off_wire",
      "bytes": 14427,
      "tokens": 3260,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "gaia",
      "rendering": "strict",
      "variant": "class_on_wire_ceiling",
      "bytes": 14610,
      "tokens": 3300,
      "delta_bytes": 183,
      "delta_tokens": 40
    },
    {
      "seat": "gaia",
      "rendering": "lenient",
      "variant": "head",
      "bytes": 13329,
      "tokens": 2942,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "gaia",
      "rendering": "lenient",
      "variant": "extend_off_wire",
      "bytes": 13329,
      "tokens": 2942,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "gaia",
      "rendering": "lenient",
      "variant": "replace_off_wire",
      "bytes": 13329,
      "tokens": 2942,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "gaia",
      "rendering": "lenient",
      "variant": "class_on_wire_ceiling",
      "bytes": 13487,
      "tokens": 2975,
      "delta_bytes": 158,
      "delta_tokens": 33
    },
    {
      "seat": "gaia",
      "rendering": "guide",
      "variant": "head",
      "bytes": 2372,
      "tokens": 615,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "gaia",
      "rendering": "guide",
      "variant": "extend_off_wire",
      "bytes": 2372,
      "tokens": 615,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "gaia",
      "rendering": "guide",
      "variant": "replace_off_wire",
      "bytes": 2372,
      "tokens": 615,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "gaia",
      "rendering": "guide",
      "variant": "class_on_wire_ceiling",
      "bytes": 2432,
      "tokens": 628,
      "delta_bytes": 60,
      "delta_tokens": 13
    },
    {
      "seat": "gaia_registry",
      "rendering": "strict",
      "variant": "head",
      "bytes": 23846,
      "tokens": 5806,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "gaia_registry",
      "rendering": "strict",
      "variant": "extend_off_wire",
      "bytes": 23846,
      "tokens": 5806,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "gaia_registry",
      "rendering": "strict",
      "variant": "replace_off_wire",
      "bytes": 23846,
      "tokens": 5806,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "gaia_registry",
      "rendering": "strict",
      "variant": "class_on_wire_ceiling",
      "bytes": 24029,
      "tokens": 5846,
      "delta_bytes": 183,
      "delta_tokens": 40
    },
    {
      "seat": "single_pass",
      "rendering": "strict",
      "variant": "head",
      "bytes": 20136,
      "tokens": 4536,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "single_pass",
      "rendering": "strict",
      "variant": "extend_off_wire",
      "bytes": 20136,
      "tokens": 4536,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "single_pass",
      "rendering": "strict",
      "variant": "replace_off_wire",
      "bytes": 20136,
      "tokens": 4536,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "single_pass",
      "rendering": "strict",
      "variant": "class_on_wire_ceiling",
      "bytes": 20319,
      "tokens": 4576,
      "delta_bytes": 183,
      "delta_tokens": 40
    },
    {
      "seat": "single_pass",
      "rendering": "lenient",
      "variant": "head",
      "bytes": 18596,
      "tokens": 4092,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "single_pass",
      "rendering": "lenient",
      "variant": "extend_off_wire",
      "bytes": 18596,
      "tokens": 4092,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "single_pass",
      "rendering": "lenient",
      "variant": "replace_off_wire",
      "bytes": 18596,
      "tokens": 4092,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "single_pass",
      "rendering": "lenient",
      "variant": "class_on_wire_ceiling",
      "bytes": 18754,
      "tokens": 4125,
      "delta_bytes": 158,
      "delta_tokens": 33
    },
    {
      "seat": "single_pass",
      "rendering": "guide",
      "variant": "head",
      "bytes": 6773,
      "tokens": 1492,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "single_pass",
      "rendering": "guide",
      "variant": "extend_off_wire",
      "bytes": 6773,
      "tokens": 1492,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "single_pass",
      "rendering": "guide",
      "variant": "replace_off_wire",
      "bytes": 6773,
      "tokens": 1492,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "seat": "single_pass",
      "rendering": "guide",
      "variant": "class_on_wire_ceiling",
      "bytes": 6868,
      "tokens": 1512,
      "delta_bytes": 95,
      "delta_tokens": 20
    }
  ],
  "card_lines": [
    {
      "corpus": "save_04",
      "label": "background",
      "lines": 5,
      "min_delta_tokens": 2,
      "max_delta_tokens": 2
    },
    {
      "corpus": "save_04",
      "label": "meaningful",
      "lines": 5,
      "min_delta_tokens": 2,
      "max_delta_tokens": 2
    },
    {
      "corpus": "save_04",
      "label": "urgent",
      "lines": 5,
      "min_delta_tokens": 2,
      "max_delta_tokens": 2
    },
    {
      "corpus": "ref_codex_bakeoff_2026_07",
      "label": "background",
      "lines": 5,
      "min_delta_tokens": 2,
      "max_delta_tokens": 2
    },
    {
      "corpus": "ref_codex_bakeoff_2026_07",
      "label": "meaningful",
      "lines": 5,
      "min_delta_tokens": 2,
      "max_delta_tokens": 2
    },
    {
      "corpus": "ref_codex_bakeoff_2026_07",
      "label": "urgent",
      "lines": 5,
      "min_delta_tokens": 2,
      "max_delta_tokens": 2
    }
  ],
  "card_blocks": [
    {
      "corpus": "save_04",
      "roster": null,
      "arm": "head",
      "lines": 5,
      "tokens": 110,
      "proposal_ids": [
        "honor_debt:ff450d8c71cd75a76aec92c5afd481e2255cbe01e41c61b718119e11871e591b",
        "hide:85dcc9f3819171e3e0ba0de152d371151c3b51cc44f39eb6803227245e505db8",
        "stroll:a339b89d4d913c763526bd612c4b3b2b567321e0aa43e1db0523d256f4f8bd68",
        "upkeep:f0d332a17697376889d58e07ecd49fe80011da3efe965a306a33e4a8184f474f",
        "drink:850b31cf78d19363dab4022fe809fcf7fbcd12cdf2186153da90e1414b8df208"
      ]
    },
    {
      "corpus": "save_04",
      "roster": "R1",
      "arm": "drop_only",
      "lines": 3,
      "tokens": 70,
      "proposal_ids": [
        "honor_debt:ff450d8c71cd75a76aec92c5afd481e2255cbe01e41c61b718119e11871e591b",
        "hide:85dcc9f3819171e3e0ba0de152d371151c3b51cc44f39eb6803227245e505db8",
        "drink:850b31cf78d19363dab4022fe809fcf7fbcd12cdf2186153da90e1414b8df208"
      ]
    },
    {
      "corpus": "save_04",
      "roster": "R1",
      "arm": "refill",
      "lines": 5,
      "tokens": 115,
      "proposal_ids": [
        "honor_debt:ff450d8c71cd75a76aec92c5afd481e2255cbe01e41c61b718119e11871e591b",
        "hide:85dcc9f3819171e3e0ba0de152d371151c3b51cc44f39eb6803227245e505db8",
        "drink:850b31cf78d19363dab4022fe809fcf7fbcd12cdf2186153da90e1414b8df208",
        "drink:9b2c010e4a4c1537cafa7e7f2373fa55ff656698e537bc3ee8e2efdbf76a87e1",
        "drink:b299bdd9b2bab66a667ba0b960db27a76b88a0b5e95f6546da63074b9bef07f4"
      ]
    },
    {
      "corpus": "save_04",
      "roster": "R1",
      "arm": "head_marked",
      "lines": 5,
      "tokens": 120,
      "proposal_ids": [
        "honor_debt:ff450d8c71cd75a76aec92c5afd481e2255cbe01e41c61b718119e11871e591b",
        "hide:85dcc9f3819171e3e0ba0de152d371151c3b51cc44f39eb6803227245e505db8",
        "stroll:a339b89d4d913c763526bd612c4b3b2b567321e0aa43e1db0523d256f4f8bd68",
        "upkeep:f0d332a17697376889d58e07ecd49fe80011da3efe965a306a33e4a8184f474f",
        "drink:850b31cf78d19363dab4022fe809fcf7fbcd12cdf2186153da90e1414b8df208"
      ]
    },
    {
      "corpus": "save_04",
      "roster": "R1",
      "arm": "refill_marked",
      "lines": 5,
      "tokens": 125,
      "proposal_ids": [
        "honor_debt:ff450d8c71cd75a76aec92c5afd481e2255cbe01e41c61b718119e11871e591b",
        "hide:85dcc9f3819171e3e0ba0de152d371151c3b51cc44f39eb6803227245e505db8",
        "drink:850b31cf78d19363dab4022fe809fcf7fbcd12cdf2186153da90e1414b8df208",
        "drink:9b2c010e4a4c1537cafa7e7f2373fa55ff656698e537bc3ee8e2efdbf76a87e1",
        "drink:b299bdd9b2bab66a667ba0b960db27a76b88a0b5e95f6546da63074b9bef07f4"
      ]
    },
    {
      "corpus": "save_04",
      "roster": "R2",
      "arm": "drop_only",
      "lines": 2,
      "tokens": 48,
      "proposal_ids": [
        "honor_debt:ff450d8c71cd75a76aec92c5afd481e2255cbe01e41c61b718119e11871e591b",
        "hide:85dcc9f3819171e3e0ba0de152d371151c3b51cc44f39eb6803227245e505db8"
      ]
    },
    {
      "corpus": "save_04",
      "roster": "R2",
      "arm": "refill",
      "lines": 5,
      "tokens": 135,
      "proposal_ids": [
        "honor_debt:ff450d8c71cd75a76aec92c5afd481e2255cbe01e41c61b718119e11871e591b",
        "hide:85dcc9f3819171e3e0ba0de152d371151c3b51cc44f39eb6803227245e505db8",
        "surveil:93626842f6a068b8dd938f29dc37571caf342204b7ff22142e501dacc4271838",
        "surveil:19b8dd6dbf3d6d7fa7307036406c3a1688bdaef1e43e0bb0e9cfdd6e70aef67e",
        "check_on_dependent:b141c5fd516f7d4baefd87daef69903692a70e4142f0b44a1f66af79b04f3b0e"
      ]
    },
    {
      "corpus": "save_04",
      "roster": "R2",
      "arm": "head_marked",
      "lines": 5,
      "tokens": 120,
      "proposal_ids": [
        "honor_debt:ff450d8c71cd75a76aec92c5afd481e2255cbe01e41c61b718119e11871e591b",
        "hide:85dcc9f3819171e3e0ba0de152d371151c3b51cc44f39eb6803227245e505db8",
        "stroll:a339b89d4d913c763526bd612c4b3b2b567321e0aa43e1db0523d256f4f8bd68",
        "upkeep:f0d332a17697376889d58e07ecd49fe80011da3efe965a306a33e4a8184f474f",
        "drink:850b31cf78d19363dab4022fe809fcf7fbcd12cdf2186153da90e1414b8df208"
      ]
    },
    {
      "corpus": "save_04",
      "roster": "R2",
      "arm": "refill_marked",
      "lines": 5,
      "tokens": 145,
      "proposal_ids": [
        "honor_debt:ff450d8c71cd75a76aec92c5afd481e2255cbe01e41c61b718119e11871e591b",
        "hide:85dcc9f3819171e3e0ba0de152d371151c3b51cc44f39eb6803227245e505db8",
        "surveil:93626842f6a068b8dd938f29dc37571caf342204b7ff22142e501dacc4271838",
        "surveil:19b8dd6dbf3d6d7fa7307036406c3a1688bdaef1e43e0bb0e9cfdd6e70aef67e",
        "check_on_dependent:b141c5fd516f7d4baefd87daef69903692a70e4142f0b44a1f66af79b04f3b0e"
      ]
    },
    {
      "corpus": "ref_codex_bakeoff_2026_07",
      "roster": null,
      "arm": "head",
      "lines": 5,
      "tokens": 119,
      "proposal_ids": [
        "drink:495ac0c75eac17d5b3108287f5c354dda89553f1e667e19a3e3406e1e96393b5",
        "run_errands:cbeef034c5cd3df5670c14327b2cc158b8ad86764fa9a95f42506ba71abf72d2",
        "run_errands:305e6e930250a204eecf64396bde0c2476157ebb2cf96da089fdfc03b55a5183",
        "drink:2b39acf7acea6e052bba785ac493505eb85f83c9d2c51d73ca6e083b221e8e60",
        "run_errands:2822439ff92aa7a08ad509f0b27c6f2fb76a9943d8eedee11aa33e1c553cc779"
      ]
    },
    {
      "corpus": "ref_codex_bakeoff_2026_07",
      "roster": "R1",
      "arm": "drop_only",
      "lines": 2,
      "tokens": 48,
      "proposal_ids": [
        "drink:495ac0c75eac17d5b3108287f5c354dda89553f1e667e19a3e3406e1e96393b5",
        "drink:2b39acf7acea6e052bba785ac493505eb85f83c9d2c51d73ca6e083b221e8e60"
      ]
    },
    {
      "corpus": "ref_codex_bakeoff_2026_07",
      "roster": "R1",
      "arm": "refill",
      "lines": 2,
      "tokens": 48,
      "proposal_ids": [
        "drink:495ac0c75eac17d5b3108287f5c354dda89553f1e667e19a3e3406e1e96393b5",
        "drink:2b39acf7acea6e052bba785ac493505eb85f83c9d2c51d73ca6e083b221e8e60"
      ]
    },
    {
      "corpus": "ref_codex_bakeoff_2026_07",
      "roster": "R1",
      "arm": "head_marked",
      "lines": 5,
      "tokens": 129,
      "proposal_ids": [
        "drink:495ac0c75eac17d5b3108287f5c354dda89553f1e667e19a3e3406e1e96393b5",
        "run_errands:cbeef034c5cd3df5670c14327b2cc158b8ad86764fa9a95f42506ba71abf72d2",
        "run_errands:305e6e930250a204eecf64396bde0c2476157ebb2cf96da089fdfc03b55a5183",
        "drink:2b39acf7acea6e052bba785ac493505eb85f83c9d2c51d73ca6e083b221e8e60",
        "run_errands:2822439ff92aa7a08ad509f0b27c6f2fb76a9943d8eedee11aa33e1c553cc779"
      ]
    },
    {
      "corpus": "ref_codex_bakeoff_2026_07",
      "roster": "R1",
      "arm": "refill_marked",
      "lines": 2,
      "tokens": 52,
      "proposal_ids": [
        "drink:495ac0c75eac17d5b3108287f5c354dda89553f1e667e19a3e3406e1e96393b5",
        "drink:2b39acf7acea6e052bba785ac493505eb85f83c9d2c51d73ca6e083b221e8e60"
      ]
    },
    {
      "corpus": "ref_codex_bakeoff_2026_07",
      "roster": "R2",
      "arm": "drop_only",
      "lines": 0,
      "tokens": 0,
      "proposal_ids": []
    },
    {
      "corpus": "ref_codex_bakeoff_2026_07",
      "roster": "R2",
      "arm": "refill",
      "lines": 0,
      "tokens": 0,
      "proposal_ids": []
    },
    {
      "corpus": "ref_codex_bakeoff_2026_07",
      "roster": "R2",
      "arm": "head_marked",
      "lines": 5,
      "tokens": 129,
      "proposal_ids": [
        "drink:495ac0c75eac17d5b3108287f5c354dda89553f1e667e19a3e3406e1e96393b5",
        "run_errands:cbeef034c5cd3df5670c14327b2cc158b8ad86764fa9a95f42506ba71abf72d2",
        "run_errands:305e6e930250a204eecf64396bde0c2476157ebb2cf96da089fdfc03b55a5183",
        "drink:2b39acf7acea6e052bba785ac493505eb85f83c9d2c51d73ca6e083b221e8e60",
        "run_errands:2822439ff92aa7a08ad509f0b27c6f2fb76a9943d8eedee11aa33e1c553cc779"
      ]
    },
    {
      "corpus": "ref_codex_bakeoff_2026_07",
      "roster": "R2",
      "arm": "refill_marked",
      "lines": 0,
      "tokens": 0,
      "proposal_ids": []
    }
  ],
  "exposures": [
    {
      "corpus": "save_04",
      "roster": "R1",
      "ticks": 44,
      "resolution_exposures": 173,
      "roster_exposures": 99,
      "all_roster_ticks": 4,
      "adjudications": {
        "defer": 33,
        "replace": 1,
        "void": 22
      },
      "refill_pool_total": 53,
      "refill_pool_outside_roster": 16,
      "refill_pool_upper_bound": true
    },
    {
      "corpus": "save_04",
      "roster": "R2",
      "ticks": 44,
      "resolution_exposures": 173,
      "roster_exposures": 167,
      "all_roster_ticks": 38,
      "adjudications": {
        "defer": 80,
        "replace": 1,
        "void": 38
      },
      "refill_pool_total": 53,
      "refill_pool_outside_roster": 15,
      "refill_pool_upper_bound": true
    },
    {
      "corpus": "ref_codex_bakeoff_2026_07",
      "roster": "R1",
      "ticks": 109,
      "resolution_exposures": 479,
      "roster_exposures": 179,
      "all_roster_ticks": 0,
      "adjudications": {
        "defer": 34,
        "replace": 5,
        "void": 28
      },
      "refill_pool_total": 250,
      "refill_pool_outside_roster": 137,
      "refill_pool_upper_bound": true
    },
    {
      "corpus": "ref_codex_bakeoff_2026_07",
      "roster": "R2",
      "ticks": 109,
      "resolution_exposures": 479,
      "roster_exposures": 421,
      "all_roster_ticks": 70,
      "adjudications": {
        "defer": 183,
        "replace": 10,
        "void": 75
      },
      "refill_pool_total": 250,
      "refill_pool_outside_roster": 118,
      "refill_pool_upper_bound": true
    }
  ]
}
```
