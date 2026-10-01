# 783-S0 Verification: Routine-Delta Grammar Weight

Date: 2026-10-01. Branch `claude/783-routine-delta-grammar-probe`, rebased on
`origin/main` at `fedebf92`. Work order 783-S0; issue #783.

The probe measures only. It applies no threshold, makes no recommendation,
builds no provider client, and reads `save_04` through sessions whose
transactions are read-only (`default_transaction_read_only=on`, which `main`
sets in `PGOPTIONS` before any connection opens; `measure` proves
`transaction_read_only = on` before it reads anything else).

## Anchor and Baseline

- Database `save_04`, migration level 139, registry digest `5a2f4f690ad9`.
- Anchor chunk 49 (the newest committed chunk on `save_04`; `max(id)` is 49).
- Presence baseline at chunk 49: Mara Vey (character 1, the player), Kessa
  Brin (character 18); setting Wickglass Dispatch House (place 7).
- `character_routine_anchors` holds 0 rows on `save_01` through `save_05` and
  on `NEXUS_template` (read-only `count(*)` on each, 2026-10-01).

## Seats

| Seat | Model | Provider | Source |
| --- | --- | --- | --- |
| wizard | gpt-5.6-terra | openai | story_pin |
| orrery.retrograde.maturation.model_ref | gpt-5.6-terra | openai | seat_default |
| gaia | gpt-5.6-terra | openai | story_follow |

`[apex.tag_library] schema_enums = true`, so the Gaia strict grammar is the
per-slot registry model.

## Reproduction of the `before` Values

Every `before` value in the order reproduces: registry strict 25,743 bytes /
7,272 tokens; lenient format 14,241 / 3,625; prompt guide 2,372 / 615;
Retrograde wire format 7,334 / 1,968; digest `5a2f4f690ad9`. The probe's
self-check also proves, byte for byte, that placement `before` reproduces
`skald_gaia_strict_text_format(spec.model)`, `skald_gaia_lenient_schema()`, its
local-wire text format, `skald_gaia_prompt_guide()`, and
`openai_response_text_format(RetrogradeExpansionWireResponse)`.

## Markdown Table

Command: `PYTHONPATH=$PWD "$PY" scripts/qa_shift/routine_delta_grammar_probe.py --dbname save_04 --anchor-chunk 49 --markdown`

Database `save_04`, anchor chunk 49, registry digest `5a2f4f690ad9`, migration level 139

| Surface | Seat | Model | Placement | Bytes | Tokens | Δ Bytes | Δ Tokens |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| gaia_registry_strict | gaia | gpt-5.6-terra | before | 25,743 | 7,272 | +0 | +0 |
| gaia_registry_strict | gaia | gpt-5.6-terra | sub_object | 27,674 | 7,790 | +1,931 | +518 |
| gaia_registry_strict | gaia | gpt-5.6-terra | top_level_list | 27,807 | 7,827 | +2,064 | +555 |
| gaia_lenient | gaia | gpt-5.6-terra | before | 14,241 | 3,625 | +0 | +0 |
| gaia_lenient | gaia | gpt-5.6-terra | sub_object | 16,067 | 4,101 | +1,826 | +476 |
| gaia_lenient | gaia | gpt-5.6-terra | top_level_list | 16,225 | 4,148 | +1,984 | +523 |
| gaia_prompt_guide | gaia | gpt-5.6-terra | before | 2,372 | 615 | +0 | +0 |
| gaia_prompt_guide | gaia | gpt-5.6-terra | sub_object | 2,706 | 699 | +334 | +84 |
| gaia_prompt_guide | gaia | gpt-5.6-terra | top_level_list | 2,729 | 704 | +357 | +89 |
| retrograde_strict | wizard | gpt-5.6-terra | before | 7,334 | 1,968 | +0 | +0 |
| retrograde_strict | wizard | gpt-5.6-terra | sub_object | 9,368 | 2,516 | +2,034 | +548 |
| retrograde_strict | wizard | gpt-5.6-terra | top_level_list | 9,368 | 2,516 | +2,034 | +548 |
| retrograde_strict | orrery.retrograde.maturation.model_ref | gpt-5.6-terra | before | 7,334 | 1,968 | +0 | +0 |
| retrograde_strict | orrery.retrograde.maturation.model_ref | gpt-5.6-terra | sub_object | 9,368 | 2,516 | +2,034 | +548 |
| retrograde_strict | orrery.retrograde.maturation.model_ref | gpt-5.6-terra | top_level_list | 9,368 | 2,516 | +2,034 | +548 |

## JSON Runs

Command (twice): `PYTHONPATH=$PWD "$PY" scripts/qa_shift/routine_delta_grammar_probe.py --dbname save_04 --anchor-chunk 49`

`cmp run1.json run2.json` reports no difference. SHA-256 of run 1:
`b0ffb92b32b9016509f20bbceeeca623c7469ccec99536210e477c69b2662918`; of run 2: `b0ffb92b32b9016509f20bbceeeca623c7469ccec99536210e477c69b2662918`.

### Run 1

```json
{
  "dbname": "save_04",
  "anchor_chunk_id": 49,
  "migration_level": "139",
  "registry_digest": "5a2f4f690ad9",
  "presence_baseline": {
    "present": [
      {
        "kind": "character",
        "name": "Mara Vey",
        "id": 1
      },
      {
        "kind": "character",
        "name": "Kessa Brin",
        "id": 18
      }
    ],
    "setting": {
      "kind": "place",
      "name": "Wickglass Dispatch House",
      "id": 7
    },
    "player_character_id": 1
  },
  "seats": [
    {
      "seat": "wizard",
      "model": "gpt-5.6-terra",
      "provider": "openai",
      "source": "story_pin"
    },
    {
      "seat": "orrery.retrograde.maturation.model_ref",
      "model": "gpt-5.6-terra",
      "provider": "openai",
      "source": "seat_default"
    },
    {
      "seat": "gaia",
      "model": "gpt-5.6-terra",
      "provider": "openai",
      "source": "story_follow"
    }
  ],
  "rows": [
    {
      "surface": "gaia_registry_strict",
      "seat": "gaia",
      "model": "gpt-5.6-terra",
      "placement": "before",
      "bytes": 25743,
      "tokens": 7272,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "surface": "gaia_registry_strict",
      "seat": "gaia",
      "model": "gpt-5.6-terra",
      "placement": "sub_object",
      "bytes": 27674,
      "tokens": 7790,
      "delta_bytes": 1931,
      "delta_tokens": 518
    },
    {
      "surface": "gaia_registry_strict",
      "seat": "gaia",
      "model": "gpt-5.6-terra",
      "placement": "top_level_list",
      "bytes": 27807,
      "tokens": 7827,
      "delta_bytes": 2064,
      "delta_tokens": 555
    },
    {
      "surface": "gaia_lenient",
      "seat": "gaia",
      "model": "gpt-5.6-terra",
      "placement": "before",
      "bytes": 14241,
      "tokens": 3625,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "surface": "gaia_lenient",
      "seat": "gaia",
      "model": "gpt-5.6-terra",
      "placement": "sub_object",
      "bytes": 16067,
      "tokens": 4101,
      "delta_bytes": 1826,
      "delta_tokens": 476
    },
    {
      "surface": "gaia_lenient",
      "seat": "gaia",
      "model": "gpt-5.6-terra",
      "placement": "top_level_list",
      "bytes": 16225,
      "tokens": 4148,
      "delta_bytes": 1984,
      "delta_tokens": 523
    },
    {
      "surface": "gaia_prompt_guide",
      "seat": "gaia",
      "model": "gpt-5.6-terra",
      "placement": "before",
      "bytes": 2372,
      "tokens": 615,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "surface": "gaia_prompt_guide",
      "seat": "gaia",
      "model": "gpt-5.6-terra",
      "placement": "sub_object",
      "bytes": 2706,
      "tokens": 699,
      "delta_bytes": 334,
      "delta_tokens": 84
    },
    {
      "surface": "gaia_prompt_guide",
      "seat": "gaia",
      "model": "gpt-5.6-terra",
      "placement": "top_level_list",
      "bytes": 2729,
      "tokens": 704,
      "delta_bytes": 357,
      "delta_tokens": 89
    },
    {
      "surface": "retrograde_strict",
      "seat": "wizard",
      "model": "gpt-5.6-terra",
      "placement": "before",
      "bytes": 7334,
      "tokens": 1968,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "surface": "retrograde_strict",
      "seat": "wizard",
      "model": "gpt-5.6-terra",
      "placement": "sub_object",
      "bytes": 9368,
      "tokens": 2516,
      "delta_bytes": 2034,
      "delta_tokens": 548
    },
    {
      "surface": "retrograde_strict",
      "seat": "wizard",
      "model": "gpt-5.6-terra",
      "placement": "top_level_list",
      "bytes": 9368,
      "tokens": 2516,
      "delta_bytes": 2034,
      "delta_tokens": 548
    },
    {
      "surface": "retrograde_strict",
      "seat": "orrery.retrograde.maturation.model_ref",
      "model": "gpt-5.6-terra",
      "placement": "before",
      "bytes": 7334,
      "tokens": 1968,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "surface": "retrograde_strict",
      "seat": "orrery.retrograde.maturation.model_ref",
      "model": "gpt-5.6-terra",
      "placement": "sub_object",
      "bytes": 9368,
      "tokens": 2516,
      "delta_bytes": 2034,
      "delta_tokens": 548
    },
    {
      "surface": "retrograde_strict",
      "seat": "orrery.retrograde.maturation.model_ref",
      "model": "gpt-5.6-terra",
      "placement": "top_level_list",
      "bytes": 9368,
      "tokens": 2516,
      "delta_bytes": 2034,
      "delta_tokens": 548
    }
  ]
}
```

### Run 2

```json
{
  "dbname": "save_04",
  "anchor_chunk_id": 49,
  "migration_level": "139",
  "registry_digest": "5a2f4f690ad9",
  "presence_baseline": {
    "present": [
      {
        "kind": "character",
        "name": "Mara Vey",
        "id": 1
      },
      {
        "kind": "character",
        "name": "Kessa Brin",
        "id": 18
      }
    ],
    "setting": {
      "kind": "place",
      "name": "Wickglass Dispatch House",
      "id": 7
    },
    "player_character_id": 1
  },
  "seats": [
    {
      "seat": "wizard",
      "model": "gpt-5.6-terra",
      "provider": "openai",
      "source": "story_pin"
    },
    {
      "seat": "orrery.retrograde.maturation.model_ref",
      "model": "gpt-5.6-terra",
      "provider": "openai",
      "source": "seat_default"
    },
    {
      "seat": "gaia",
      "model": "gpt-5.6-terra",
      "provider": "openai",
      "source": "story_follow"
    }
  ],
  "rows": [
    {
      "surface": "gaia_registry_strict",
      "seat": "gaia",
      "model": "gpt-5.6-terra",
      "placement": "before",
      "bytes": 25743,
      "tokens": 7272,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "surface": "gaia_registry_strict",
      "seat": "gaia",
      "model": "gpt-5.6-terra",
      "placement": "sub_object",
      "bytes": 27674,
      "tokens": 7790,
      "delta_bytes": 1931,
      "delta_tokens": 518
    },
    {
      "surface": "gaia_registry_strict",
      "seat": "gaia",
      "model": "gpt-5.6-terra",
      "placement": "top_level_list",
      "bytes": 27807,
      "tokens": 7827,
      "delta_bytes": 2064,
      "delta_tokens": 555
    },
    {
      "surface": "gaia_lenient",
      "seat": "gaia",
      "model": "gpt-5.6-terra",
      "placement": "before",
      "bytes": 14241,
      "tokens": 3625,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "surface": "gaia_lenient",
      "seat": "gaia",
      "model": "gpt-5.6-terra",
      "placement": "sub_object",
      "bytes": 16067,
      "tokens": 4101,
      "delta_bytes": 1826,
      "delta_tokens": 476
    },
    {
      "surface": "gaia_lenient",
      "seat": "gaia",
      "model": "gpt-5.6-terra",
      "placement": "top_level_list",
      "bytes": 16225,
      "tokens": 4148,
      "delta_bytes": 1984,
      "delta_tokens": 523
    },
    {
      "surface": "gaia_prompt_guide",
      "seat": "gaia",
      "model": "gpt-5.6-terra",
      "placement": "before",
      "bytes": 2372,
      "tokens": 615,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "surface": "gaia_prompt_guide",
      "seat": "gaia",
      "model": "gpt-5.6-terra",
      "placement": "sub_object",
      "bytes": 2706,
      "tokens": 699,
      "delta_bytes": 334,
      "delta_tokens": 84
    },
    {
      "surface": "gaia_prompt_guide",
      "seat": "gaia",
      "model": "gpt-5.6-terra",
      "placement": "top_level_list",
      "bytes": 2729,
      "tokens": 704,
      "delta_bytes": 357,
      "delta_tokens": 89
    },
    {
      "surface": "retrograde_strict",
      "seat": "wizard",
      "model": "gpt-5.6-terra",
      "placement": "before",
      "bytes": 7334,
      "tokens": 1968,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "surface": "retrograde_strict",
      "seat": "wizard",
      "model": "gpt-5.6-terra",
      "placement": "sub_object",
      "bytes": 9368,
      "tokens": 2516,
      "delta_bytes": 2034,
      "delta_tokens": 548
    },
    {
      "surface": "retrograde_strict",
      "seat": "wizard",
      "model": "gpt-5.6-terra",
      "placement": "top_level_list",
      "bytes": 9368,
      "tokens": 2516,
      "delta_bytes": 2034,
      "delta_tokens": 548
    },
    {
      "surface": "retrograde_strict",
      "seat": "orrery.retrograde.maturation.model_ref",
      "model": "gpt-5.6-terra",
      "placement": "before",
      "bytes": 7334,
      "tokens": 1968,
      "delta_bytes": 0,
      "delta_tokens": 0
    },
    {
      "surface": "retrograde_strict",
      "seat": "orrery.retrograde.maturation.model_ref",
      "model": "gpt-5.6-terra",
      "placement": "sub_object",
      "bytes": 9368,
      "tokens": 2516,
      "delta_bytes": 2034,
      "delta_tokens": 548
    },
    {
      "surface": "retrograde_strict",
      "seat": "orrery.retrograde.maturation.model_ref",
      "model": "gpt-5.6-terra",
      "placement": "top_level_list",
      "bytes": 9368,
      "tokens": 2516,
      "delta_bytes": 2034,
      "delta_tokens": 548
    }
  ]
}
```

## Gate Tails

`NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_routine_delta_grammar_probe_pg.py tests/test_orrery/test_gaia_registry_schema_pg.py tests/test_slot_routed_entrypoints.py tests/test_owner_target_guard.py`
(`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset). The one skip is
`tests/test_orrery/test_gaia_registry_schema_pg.py:347`, the paid live gate
behind `NEXUS_638_ENUM_E2E=1`.

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 5 targets: postgres, qa638_*, qa640_783_probe_*, qa640_811_gaia_scene_*, qa885_entrypoints_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
120 passed, 1 skipped, 2 warnings in 38.35s
```

`$PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery -p no:cacheprovider`
(offline; the skips are the PostgreSQL-marked tests):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2676 passed, 448 skipped, 8 warnings in 392.89s (0:06:32)
```

`$PY -m pytest -q tests/test_api tests/test_orrery` (offline):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1820 passed, 743 skipped, 7 warnings in 36.50s
```

`$PY -m pytest -q tests/test_reachability.py`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 9.66s
```

Black, flake8 and mypy on `scripts/qa_shift/routine_delta_grammar_probe.py`,
`tests/test_routine_delta_grammar_probe_pg.py` and
`tests/test_slot_routed_entrypoints.py`:

```text
All done! ✨ 🍰 ✨
3 files left unchanged.
Success: no issues found in 3 source files
```

## After Rebasing on `origin/main` at `9ac0caf6`

The branch was rebased over #1074 (784-S1) and #1075 (781-S1); the only
conflict was adjacent README sections, kept both. The gates were rerun:

PostgreSQL proof command (same as above):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 5 targets: postgres, qa638_*, qa640_783_probe_*, qa640_811_gaia_scene_*, qa885_entrypoints_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
120 passed, 1 skipped, 2 warnings in 39.68s
```

`$PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2676 passed, 448 skipped, 8 warnings in 421.09s (0:07:01)
```

`$PY -m pytest -q tests/test_api tests/test_orrery`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1829 passed, 746 skipped, 7 warnings in 36.39s
```

`$PY -m pytest -q tests/test_reachability.py`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 10.28s
```

The probe's JSON on `save_04` at chunk 49 after the rebase is byte-identical
to run 1 above (`cmp` reports no difference).
