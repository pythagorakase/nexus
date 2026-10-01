# Verification for #788 S0: Place-Scale Grammar Measurement

Date: 2026-10-01. Branch `claude/788-place-scale-grammar-measure`, cut from `origin/main` at 4a063652, rebased onto fedebf92 before work began and onto 9ac0caf6 (the newest `origin/main` when this was written); the run and the test tails below were made at the rebased head (5924fb62, before this file was committed). All commands ran from the worktree root with the shared interpreter `/Users/pythagor/nexus/.venv/bin/python` (`$PY`) and `PYTHONPATH=$PWD`; `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` were unset. The import check printed `/Users/pythagor/nexus/.claude/worktrees/788-place-scale-grammar-measure/nexus/__init__.py`. No migration, no gateway, no paid call. `save_02` was only read, through sessions opened with `default_transaction_read_only=on`; the tests used disposable `qa640_788_scale_*` clones of `NEXUS_template`.

## Cited Facts (Checked at 9ac0caf6)

- No place has a scale. Read-only SQL on `NEXUS_template`: `places` has no column matching `%scale%`; `enum_range(null::place_type)` is `{fixed_location,vehicle,virtual,other}`; `tag_category_registry` has no category matching `%scale%`. The promptable place tags (non-deprecated tags in non-deprecated `place` categories) are 38, in `place_access` 2, `place_environment` 13, `place_function` 18, `place_threat` 3 and `place_visibility` 2. `select count(*), md5(string_agg(tag||':'||category, ',' order by tag)) from tags` returns `465|10308d53909726994b4a2a22b0b32f43` on `NEXUS_template` and on each of `save_01` to `save_05`.
- `nexus.toml:1243` is `turn_pipeline = "two_pass"`; `:1274` is `schema_enums = true`.
- `_gaia_schema_model` starts at `nexus/agents/lore/logon_utility.py:2344`; `:2434` is `else skald_gaia_strict_text_format(gaia_schema_model)`; `:2302` is `kwargs = {"text_format": skald_wire_strict_text_format()}`; `:2356-2357` return the static `SkaldGaiaWire` when the wire is not OpenAI or `schema_enums` is false.
- `nexus/agents/logon/gaia_registry_schema.py:341` builds the one `PlaceTagName` alias; the place declaration arm (`:408-412`) and the place update arm (`:449-454`) both reference it; the declaration arms subclass the module global `NewEntityDeclaration` (`:377-380`).
- `SkaldTurnWire` starts at `nexus/agents/logon/skald_wire.py:434`; `skald_wire_strict_text_format` at `:766`. `PlaceUpdateDelta.tags_add`/`tags_clear` and `NewEntityDeclaration.tag_hints` are `List[str]`.
- `SetDesignerOutput` (`nexus/api/new_story_generator.py:487-498`) has `location: PlaceProfile`; the structured call is at `:557-560`; `scripts/api_openai.py:844` sends `text_format or openai_response_text_format(schema_model)`.
- `scripts/token_counter.py:107-111` resolves the writer seat and builds no schema.

## Owner State at the Run

`resolve_seat("wizard")` reads `wizard_model` from `[runtime].state_dir/preferences.toml` when that file exists. With `NEXUS_HOME` unset the path resolves to `<checkout>/.nexus/runtime/preferences.toml`; it did not exist in this worktree, nor at `/Users/pythagor/nexus/.nexus/runtime/preferences.toml`. All three seats resolved to `gpt-6-astra` (provider `openai`, source `repository_default`, `tokenizer_encoding = "o200k_base"`).

## The Run

`PYTHONPATH=$PWD $PY scripts/measure_place_scale_grammar.py --dbname save_02` exited 0. Its stderr carried one line, `INFO Measured 3 entry points on save_02`. An earlier run on fedebf92, before the rebase onto 9ac0caf6, printed byte-identical stdout. Stdout:

```json
{
  "dbname": "save_02",
  "read_only_session": true,
  "scale_values": [
    "room",
    "building",
    "site",
    "district",
    "settlement"
  ],
  "scale_tag_names": [
    "scale_room",
    "scale_building",
    "scale_site",
    "scale_district",
    "scale_settlement"
  ],
  "serialization": "json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(\",\", \":\"))",
  "entry_points": [
    {
      "name": "gaia_two_pass_openai",
      "seat": "gaia",
      "model": "gpt-6-astra",
      "builder": "skald_gaia_strict_text_format(load_gaia_registry_wire_spec(dbname, ...).model) @ nexus/agents/lore/logon_utility.py:2434",
      "tag_form_changes_grammar": true,
      "baseline": {
        "bytes": 23846,
        "tokens": 5806,
        "enum_values": 528
      },
      "tag_form": {
        "bytes": 23925,
        "tokens": 5824,
        "enum_values": 533,
        "delta_bytes": 79,
        "delta_tokens": 18
      },
      "column_form": {
        "bytes": 24379,
        "tokens": 5938,
        "enum_values": 533,
        "delta_bytes": 533,
        "delta_tokens": 132
      }
    },
    {
      "name": "skald_single_pass_openai",
      "seat": "skald",
      "model": "gpt-6-astra",
      "builder": "skald_wire_strict_text_format() @ nexus/agents/lore/logon_utility.py:2302",
      "tag_form_changes_grammar": false,
      "baseline": {
        "bytes": 20136,
        "tokens": 4536,
        "enum_values": 54
      },
      "tag_form": {
        "bytes": 20136,
        "tokens": 4536,
        "enum_values": 54,
        "delta_bytes": 0,
        "delta_tokens": 0
      },
      "column_form": {
        "bytes": 20413,
        "tokens": 4602,
        "enum_values": 59,
        "delta_bytes": 277,
        "delta_tokens": 66
      }
    },
    {
      "name": "wizard_set_designer_openai",
      "seat": "wizard",
      "model": "gpt-6-astra",
      "builder": "openai_response_text_format(SetDesignerOutput) @ scripts/api_openai.py:844 via nexus/api/new_story_generator.py:557-560",
      "tag_form_changes_grammar": false,
      "baseline": {
        "bytes": 8995,
        "tokens": 2079,
        "enum_values": 14
      },
      "tag_form": {
        "bytes": 8995,
        "tokens": 2079,
        "enum_values": 14,
        "delta_bytes": 0,
        "delta_tokens": 0
      },
      "column_form": {
        "bytes": 9350,
        "tokens": 2170,
        "enum_values": 19,
        "delta_bytes": 355,
        "delta_tokens": 91
      }
    }
  ]
}
```

## Table

| Entry point | Baseline bytes / tokens / enum values | Tag form bytes / tokens / enum values (delta bytes / tokens) | Column form bytes / tokens / enum values (delta bytes / tokens) |
|---|---|---|---|
| `gaia_two_pass_openai` | 23,846 / 5,806 / 528 | 23,925 / 5,824 / 533 (+79 / +18) | 24,379 / 5,938 / 533 (+533 / +132) |
| `skald_single_pass_openai` | 20,136 / 4,536 / 54 | 20,136 / 4,536 / 54 (0 / 0) | 20,413 / 4,602 / 59 (+277 / +66) |
| `wizard_set_designer_openai` | 8,995 / 2,079 / 14 | 8,995 / 2,079 / 14 (0 / 0) | 9,350 / 2,170 / 19 (+355 / +91) |

Tokens are `o200k_base` counts of the serialized schema (`json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`), not provider usage.

## Comparison With the Coordinator's Prototype

The prototype (read-only, `save_02`, `o200k_base`) measured Gaia 23,846 / 5,806 (528 enum values), Skald single-pass 20,136 / 4,536, wizard 8,995 / 2,079; tag form Gaia +79 / +18 (533 enum values), Skald and wizard 0; column form Gaia +533 / +132, Skald +277 / +66, wizard +355 / +91. Every figure matches. The Gaia baseline also matches the budget recorded in `tests/test_orrery/test_gaia_registry_schema_pg.py:44-54` for a fresh `NEXUS_template` clone (23,846 bytes, 5,806 tokens, 528 enum values), as expected: the `tags` table on `save_02` is identical to the template's.

## Test Tails

PostgreSQL proof (`NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_measure_place_scale_grammar_pg.py tests/test_orrery/test_gaia_registry_schema_pg.py tests/test_owner_target_guard.py tests/test_pg_disposable_target.py`). The one skip is the paid live Gaia gate (`test_gaia_registry_schema_pg.py:347`, "Set NEXUS_638_ENUM_E2E=1 for the live Gaia enum-schema gate.").

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 6 targets: postgres, qa638_*, qa640_788_scale_* x2, qa640_811_gaia_scene_*, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
146 passed, 1 skipped in 12.83s
```

Offline (`$PY -m pytest -q tests/test_measure_place_scale_grammar.py`):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
4 passed, 5 warnings in 0.76s
```

Offline suite (`$PY -m pytest -q -p no:cacheprovider tests --ignore=tests/test_api --ignore=tests/test_orrery`):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2679 passed, 445 skipped, 8 warnings in 394.70s (0:06:34)
```

Offline suite (`$PY -m pytest -q -p no:cacheprovider tests/test_api tests/test_orrery`):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1829 passed, 746 skipped, 7 warnings in 37.08s
```

Reachability (`$PY -m pytest -q tests/test_reachability.py`):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 12.44s
```

Black, flake8 and mypy on `scripts/measure_place_scale_grammar.py`, `tests/test_measure_place_scale_grammar.py` and `tests/test_measure_place_scale_grammar_pg.py`:

```
$ $PY -m black --check <three files>
All done! ✨ 🍰 ✨
3 files would be left unchanged.
$ $PY -m flake8 <three files>; echo $?
0
$ $PY -m mypy <three files>
Success: no issues found in 3 source files
```

## Rerun After the Rebase Onto ffc2d6b8

`origin/main` gained ffc2d6b8 (#815 S1: CLI HTTP handlers; it touches `nexus.toml`, `nexus/cli.py`, `nexus/cli_contract.py` and `nexus/config/settings_models.py`) while the branch was being pushed, so the branch was rebased onto it and these were rerun at the rebased head. `nexus.toml:1243` and `:1274` still hold `turn_pipeline = "two_pass"` and `schema_enums = true`, and none of the measured builders changed. The script on `save_02` exited 0 with stdout byte-identical to the JSON above.

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_measure_place_scale_grammar_pg.py tests/test_orrery/test_gaia_registry_schema_pg.py tests/test_owner_target_guard.py tests/test_pg_disposable_target.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 6 targets: postgres, qa638_*, qa640_788_scale_* x2, qa640_811_gaia_scene_*, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
146 passed, 1 skipped in 9.78s
$ $PY -m pytest -q tests/test_reachability.py tests/test_measure_place_scale_grammar.py
58 passed, 5 warnings in 10.51s
$ $PY -m pytest -q -p no:cacheprovider tests/test_api tests/test_orrery
1829 passed, 746 skipped, 7 warnings in 34.53s
$ $PY -m pytest -q -p no:cacheprovider tests --ignore=tests/test_api --ignore=tests/test_orrery
2719 passed, 445 skipped, 8 warnings in 428.03s (0:07:08)
```

