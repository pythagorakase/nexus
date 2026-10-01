# 840-S2a Verification: Place-Coordinate Costs for 840-Q4

Date: 2026-10-01 (America/Chicago). Branch `claude/840-coordinate-cost-measure`,
base `origin/main` at `9ac0caf6`; measured with the script at `055f4079`.
Refs #840.

This slice changes no product behavior. It measures two ways to meet the
owner's ruling that every later place stub must carry coordinates, and
recommends neither. No provider was called. The owner slots were read only
through `open_read_only_connection` (read-only, repeatable-read sessions).

## Cited Lines (Checked at `9ac0caf6`)

The line numbers the order cites at `41783c1d` are unchanged at `9ac0caf6`.

- Retrograde stub writer: `_insert_place_stub` at
  `nexus/agents/orrery/retrograde_persistence.py:3209-3229` writes
  `type 'other'`, the active zone, no point; `extra_data` from
  `_stub_extra_data` (`:3267-3272`), `RETROGRADE_SOURCE_KIND = "retrograde"`
  (`:60`); `MATURATION_EVENT_REF_PATTERN` (`:71`); `_insert_prologue_chunk`
  (`:2541-2558`).
- Trait-compiler writer: `_insert_place_stub` at
  `nexus/api/trait_compiler.py:1843-1867`, no point;
  `TRAIT_COMPILER_SOURCE = "trait_compiler"` (`:93`), `TRAIT_STUB_KIND`
  (`:94`), `_stub_extra_data` (`:1905-1910`); only the Domain trait reaches it
  (`:500-510`, `:1797`).
- Skald declaration writer: `_insert_declared_stub` place branch at
  `nexus/agents/orrery/retrograde_maturation.py:442-475` writes a point only
  when the declaration has one; `NewEntityDeclaration.coordinates` is optional
  (`nexus/agents/logon/apex_schema.py:170-173`); maturation fills a missing
  point later (`retrograde_maturation.py:1495-1526`).
- Expansion grammar: `RetrogradeExpansionWireResponse`
  (`nexus/agents/orrery/retrograde_expansion.py:383-401`), sent at `:794-797`;
  its only point is the optional `coordinates` (`:393-399`), required only for
  geo-only maturation (`:732-739`).
- Derivation grammar: `selected_trait_compile_inputs_model`
  (`nexus/api/trait_input_derivation.py:96-112`), sent at `:321-324`;
  `_DERIVABLE_TRAITS` at `:47`; `DomainTraitInput`
  (`nexus/api/trait_compiler_schemas.py:133-151`) carries no point.
- Dedicated call: `author_place_coordinates`
  (`nexus/agents/orrery/geo_authoring.py:56-92`) sends the rendered prompt as
  the system prompt (`:79`) and the user prompt (`:83-86`), with
  `GeoAuthoringResponse` (`:15-22`), on seat `geo_authoring` (`:81`);
  `render_geo_authoring_prompt` is keyword-only (`:25-31`).
  `scripts/gis_backfill.py:283-289` runs it with
  `orrery.retrograde.maturation.model_ref`.
- Schema forms: `strict_json_schema` (`nexus/api/native_structured_output.py:47`),
  `anthropic_json_schema` (`:162`), provider routing in
  `build_native_structured_provider` (`:229-270`).
- Token counter: `local_text_counter` (`nexus/telemetry/prompt_window.py:123`).
  Read-only session: `open_read_only_connection`
  (`scripts/entity_reference_parity.py:158`).
- Stub cap: `max_new_entity_stubs = 6` (`nexus.toml:721`).

## Slot Facts Against the Order

Every slot fact in the order holds:

- `save_03`: 5 places; 1 genesis row (place 1, point present) and 4 later
  rows (3 Retrograde stubs with no point, place 4 with no source and a
  point); 39 chunks after the first.
- `save_04`: 7 places; 1 genesis row and 6 later rows (5 Retrograde stubs
  with no point, place 4 with a point); 45 chunks after the first.
- On both slots, places 1 and 4 share the point `(-122.3321, 47.6062)`.
- `save_01` and `save_02`: 77 places each, 27 with no point, no stub source.
  `save_05` is empty (`"first_chunk": null`).
- On `save_04`, stubs 2, 3 and 5 name maturation jobs 3, 9 and 12, which exist
  only on `save_03`. The report therefore attributes them by `created_at`
  with `"job_row_found": false` (to chunks 5, 19 and 24). On `save_03` the
  same stubs attribute through their job rows (to chunks 5, 18 and 24).
  Stub 3 differs by one chunk between the two slots because the `created_at`
  fallback picks the latest chunk at or before the row, and the job's
  requesting chunk was 18.

On `save_03` and `save_04` the first chunk (id 1) is the Retrograde prologue
anchor (`authorial_directives` `["orrery:retrograde_prologue_anchor"]`),
written in the genesis transaction by `_insert_prologue_chunk`; place 1 has
the same `created_at` (`2026-07-30 00:55:20.251348-04`). The chunks after it
(39 on `save_03`, 45 on `save_04`) are all narrated chunks, the opening
narration (chunk 2) included; no other chunk on either slot carries
directives. The report keeps the lowest-id rule unchanged.

`save_01` and `save_02` are imported corpora whose places all postdate the
first chunk (all 77 rows attribute to chunk 1425 by `created_at`), so their
genesis and turn figures are not evidence. `save_04` repeats `save_03`'s
genesis (the same first-chunk `created_at`, the same places 1 to 5).

## Summary for 840-Q4

Tokens are `o200k_base` (the tokenizer of `gpt-5.6-terra`, the configured
`orrery.retrograde.maturation.model_ref`). Bytes and tokens are of
`json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`.
Transport framing is not counted.

### Grammar Weight of a Required Point

| Grammar | Form | Baseline (bytes / tokens) | Variant (bytes / tokens) | Delta (bytes / tokens) |
|---|---|---|---|---|
| Expansion (`new_place_points`) | strict | 6,754 / 1,535 | 7,746 / 1,772 | +992 / +237 |
| Expansion (`new_place_points`) | anthropic | 6,289 / 1,403 | 7,196 / 1,612 | +907 / +209 |
| Derivation, `["domain"]` | strict | 1,051 / 248 | 2,078 / 493 | +1,027 / +245 |
| Derivation, `["domain"]` | anthropic | 1,037 / 243 | 1,952 / 452 | +915 / +209 |
| Derivation, all ten traits | strict | 11,104 / 2,443 | 12,131 / 2,688 | +1,027 / +245 |
| Derivation, all ten traits | anthropic | 10,820 / 2,383 | 11,735 / 2,592 | +915 / +209 |

The strict form inlines `Coordinates` at a `$ref` that carries a sibling
`description` (OpenAI's `to_strict_json_schema` unravels it) and also keeps
the `Coordinates` entry in `$defs`, so in that form the point's object
appears twice on the wire.

### Output Tokens per Place

- The `coordinates` member a reply adds per place,
  `"coordinates":{"lat":47.6062,"lon":-122.3321}`: 18 tokens.
- A `new_place_points` entry for each Retrograde stub name read: Cinder Vault
  25, Early Continuity Registry 26, Pilgrim Stack 9 27, West Conduit Relay 26,
  Wickglass Dispatch House 27.

### Dedicated Call per Place

- Schema `GeoAuthoringResponse`: strict 1,231 bytes / 282 tokens; anthropic
  1,119 / 246. The configured model routes to OpenAI, so the request form is
  `strict_json_schema`.
- Request tokens = 2 x rendered prompt tokens + 282, over the 62 places with
  no point read: min 670, mean 766.65, max 1,088 (`save_01` and `save_02`: 27
  each, 670 / 774.15 / 1,088; `save_03`: 3, 712 / 716.0 / 720; `save_04`: 5,
  712 / 716.0 / 720).
- Output `{"coordinates":{"lat":47.6062,"lon":-122.3321}}`: 18 tokens.
- A batch call (840-Q4: "once per new place or batch") is not measured,
  because no batch grammar exists.

### New Places per Genesis and per Turn

| Slot | Genesis rows (source; point) | Later rows (source; point) | Chunks after first | Later rows per chunk (mean / max) | Histogram (rows: chunks) |
|---|---|---|---|---|---|
| `save_03` | 1 (none 1; present 1) | 4 (retrograde 3, none 1; null 3, present 1) | 39 | 0.103 / 1 | 0: 35, 1: 4 |
| `save_04` | 1 (none 1; present 1) | 6 (retrograde 5, none 1; null 5, present 1) | 45 | 0.133 / 2 | 0: 40, 1: 4, 2: 1 |
| `save_01`, `save_02` | 0 | 77 (none 77; present 50, null 27) | 1,424 | not evidence (imported) | 0: 1,423, 77: 1 |
| `save_05` | empty | empty | none | none | none |

Configured cap on charged stubs of all kinds per genesis expansion
(`orrery.retrograde.wizard.max_new_entity_stubs`): 6.

## Commands and Tails

### PostgreSQL Proof

```
NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit \
  tests/test_measure_place_coordinate_costs_pg.py tests/test_orrery/test_gis_stub_paths_live.py \
  tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
# NEXUS_GATEWAY_PORT, NEXUS_API_URL and NEXUS_SLOT unset
```

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 8 targets: postgres, qa640_840_cost_*, qa735_gis_stubs_* x5, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
147 passed in 15.81s
```

### Offline Suites

```
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
```

```
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2678 passed, 444 skipped, 8 warnings in 389.69s (0:06:29)
```

```
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_orrery
```

```
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1829 passed, 746 skipped, 7 warnings in 37.09s
```

The first offline run failed `tests/test_reachability.py` (two tests) and
`tests/test_runtime/test_readiness.py::test_doctor_ci_runner_passes_on_this_checkout`
because the new script was unclassified; the commit registers it as an
operator in `config/reachability.toml` and reclassifies
`scripts/entity_reference_parity.py` from test-only to operator (the new
operator imports it). The tails above are the reruns after that change.
`tests/test_reachability.py` runs inside the first offline suite.

### Lint and Types

```
black scripts/measure_place_coordinate_costs.py tests/test_measure_place_coordinate_costs.py tests/test_measure_place_coordinate_costs_pg.py
All done! ✨ 🍰 ✨
3 files left unchanged.
flake8 (same three files): exit 0, no output
mypy (same three files): Success: no issues found in 3 source files
```

### Report Run

```
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/measure_place_coordinate_costs.py \
  --dbname save_01 --dbname save_02 --dbname save_03 --dbname save_04 --dbname save_05
```

Exit status 0. Stderr carried only the five `Reading save_NN read-only` log
lines. A second run produced identical JSON. Full stdout:

```json
{
  "issue": 840,
  "question": "840-Q4",
  "model": "gpt-5.6-terra",
  "tokenizer": "o200k_base",
  "serialization": "json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(\",\", \":\"))",
  "sample_point": {
    "lat": 47.6062,
    "lon": -122.3321
  },
  "grammars": {
    "expansion": {
      "baseline_model": "RetrogradeExpansionWireResponse",
      "added_field": "new_place_points",
      "forms": {
        "strict_json_schema": {
          "baseline": {
            "bytes": 6754,
            "tokens": 1535
          },
          "variant": {
            "bytes": 7746,
            "tokens": 1772
          },
          "delta": {
            "bytes": 992,
            "tokens": 237
          }
        },
        "anthropic_json_schema": {
          "baseline": {
            "bytes": 6289,
            "tokens": 1403
          },
          "variant": {
            "bytes": 7196,
            "tokens": 1612
          },
          "delta": {
            "bytes": 907,
            "tokens": 209
          }
        }
      }
    },
    "derivation_domain": {
      "baseline_model": "TraitCompileInputsSelectedDomain",
      "added_field": "domain.coordinates",
      "forms": {
        "strict_json_schema": {
          "baseline": {
            "bytes": 1051,
            "tokens": 248
          },
          "variant": {
            "bytes": 2078,
            "tokens": 493
          },
          "delta": {
            "bytes": 1027,
            "tokens": 245
          }
        },
        "anthropic_json_schema": {
          "baseline": {
            "bytes": 1037,
            "tokens": 243
          },
          "variant": {
            "bytes": 1952,
            "tokens": 452
          },
          "delta": {
            "bytes": 915,
            "tokens": 209
          }
        }
      }
    },
    "derivation_all_derivable_traits": {
      "baseline_model": "TraitCompileInputsSelectedResourcesFameStatusAlliesContactsEnemiesDomainPatronDependentsObligations",
      "added_field": "domain.coordinates",
      "forms": {
        "strict_json_schema": {
          "baseline": {
            "bytes": 11104,
            "tokens": 2443
          },
          "variant": {
            "bytes": 12131,
            "tokens": 2688
          },
          "delta": {
            "bytes": 1027,
            "tokens": 245
          }
        },
        "anthropic_json_schema": {
          "baseline": {
            "bytes": 10820,
            "tokens": 2383
          },
          "variant": {
            "bytes": 11735,
            "tokens": 2592
          },
          "delta": {
            "bytes": 915,
            "tokens": 209
          }
        }
      }
    }
  },
  "per_place_output": {
    "coordinates_member": {
      "text": "\"coordinates\":{\"lat\":47.6062,\"lon\":-122.3321}",
      "tokens": 18
    },
    "new_place_entries_source": "retrograde_stubs",
    "new_place_entries": [
      {
        "name": "Cinder Vault",
        "text": "{\"place_ref\":\"Cinder Vault\",\"coordinates\":{\"lat\":47.6062,\"lon\":-122.3321}}",
        "tokens": 25
      },
      {
        "name": "Early Continuity Registry",
        "text": "{\"place_ref\":\"Early Continuity Registry\",\"coordinates\":{\"lat\":47.6062,\"lon\":-122.3321}}",
        "tokens": 26
      },
      {
        "name": "Pilgrim Stack 9",
        "text": "{\"place_ref\":\"Pilgrim Stack 9\",\"coordinates\":{\"lat\":47.6062,\"lon\":-122.3321}}",
        "tokens": 27
      },
      {
        "name": "West Conduit Relay",
        "text": "{\"place_ref\":\"West Conduit Relay\",\"coordinates\":{\"lat\":47.6062,\"lon\":-122.3321}}",
        "tokens": 26
      },
      {
        "name": "Wickglass Dispatch House",
        "text": "{\"place_ref\":\"Wickglass Dispatch House\",\"coordinates\":{\"lat\":47.6062,\"lon\":-122.3321}}",
        "tokens": 27
      }
    ]
  },
  "dedicated_call": {
    "schema": {
      "strict_json_schema": {
        "bytes": 1231,
        "tokens": 282
      },
      "anthropic_json_schema": {
        "bytes": 1119,
        "tokens": 246
      }
    },
    "request_schema_form": "strict_json_schema",
    "request": {
      "formula": "2 x tokens(render_geo_authoring_prompt(...)) + schema tokens of request_schema_form; the prompt is sent as both the system prompt and the user prompt",
      "places_measured": 62,
      "min": 670,
      "mean": 766.65,
      "max": 1088,
      "by_database": {
        "save_01": {
          "places_measured": 27,
          "min": 670,
          "mean": 774.15,
          "max": 1088
        },
        "save_02": {
          "places_measured": 27,
          "min": 670,
          "mean": 774.15,
          "max": 1088
        },
        "save_03": {
          "places_measured": 3,
          "min": 712,
          "mean": 716.0,
          "max": 720
        },
        "save_04": {
          "places_measured": 5,
          "min": 712,
          "mean": 716.0,
          "max": 720
        }
      }
    },
    "output": {
      "text": "{\"coordinates\":{\"lat\":47.6062,\"lon\":-122.3321}}",
      "tokens": 18
    },
    "transport_framing_counted": false,
    "batch_call_measured": false,
    "notes": [
      "Transport framing (request envelope, message roles, response_format or tool wrappers) is not counted; figures are compact JSON schema and rendered prompt text only.",
      "A batch call (840-Q4: 'once per new place or batch') is not measured because no batch grammar exists."
    ]
  },
  "configured_stub_cap": {
    "setting": "orrery.retrograde.wizard.max_new_entity_stubs",
    "value": 6,
    "meaning": "cap on charged new stubs of all kinds per genesis expansion"
  },
  "databases": {
    "save_01": {
      "places_total": 77,
      "shared_points": [],
      "first_chunk": {
        "id": 1,
        "created_at": "2025-04-13T09:01:01.189935+00:00",
        "authorial_directives": []
      },
      "genesis": {
        "rows": 0,
        "by_source": {
          "retrograde": 0,
          "trait_compiler": 0,
          "none": 0
        },
        "by_point": {
          "present": 0,
          "null": 0
        }
      },
      "later": {
        "rows": 77,
        "by_source": {
          "retrograde": 0,
          "trait_compiler": 0,
          "none": 77
        },
        "by_point": {
          "present": 50,
          "null": 27
        },
        "rows_detail": [
          {
            "place_id": 1,
            "name": "The Ghost",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 2,
            "name": "The Land Rig",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 3,
            "name": "The Salted Hash\n",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 11,
            "name": "Nomad Camp",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 12,
            "name": "Nomad Bazaar",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 13,
            "name": "Nomad MedTechs",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 21,
            "name": "Rusthaven",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 91,
            "name": "Leviathan",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 92,
            "name": "Data-Barge Okami",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 101,
            "name": "Coastal Safehouse",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 103,
            "name": "Coastal Highway",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 104,
            "name": "Halcyon Atrium",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 106,
            "name": "Omniframe Robotics",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 107,
            "name": "Bougie Mall High-End Fashion Outlet",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 109,
            "name": "Black Market Tech Bazaar",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 111,
            "name": "Skyline Lounge",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 113,
            "name": "Dead Circuit",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 114,
            "name": "Derelict Parking Structure",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 115,
            "name": "Citadel Suites",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 116,
            "name": "Black-Market Netrunner Den",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 119,
            "name": "Night City Streets",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 121,
            "name": "District 07 Shipping Yard",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 122,
            "name": "Alex's Night City Safehouse",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 123,
            "name": "Low Tide",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 124,
            "name": "Back-Alley Hacker Den",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 125,
            "name": "District 06 Hacker Den",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 126,
            "name": "The Eyrie",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 131,
            "name": "Sato's Night City Safehouse",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 132,
            "name": "Orchid Sovereign Institute",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 133,
            "name": "Specialized Underground Cyberclinic",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 141,
            "name": "Aerodyne Research Facility",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 142,
            "name": "Black Market Ripperdoc",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 151,
            "name": "Seaside Grill & Bar",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 152,
            "name": "Lag Siren Lounge",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 153,
            "name": "Blackout Drift Hotel",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 154,
            "name": "Murmur & Ink",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 155,
            "name": "Cliff Overlooking the Sea",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 159,
            "name": "Virginia Beach Streets",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 170,
            "name": "Frederick",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 181,
            "name": "The Silo",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 183,
            "name": "Ordnance Corridor M-7",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 184,
            "name": "Nomad Mechanic Outpost",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 185,
            "name": "Smuggler Shipyard",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 186,
            "name": "Half-Life Waystation",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 191,
            "name": "Data Tomb",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 192,
            "name": "Private Dynacorp Facility",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 193,
            "name": "Geotech Field Lab 226-B",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 301,
            "name": "Dynacorp Blacksite",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 311,
            "name": "Le Chat Noir",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 312,
            "name": "Boudreaux’s Haute-Creole Experience",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 313,
            "name": "Le Chuchotement",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 314,
            "name": "The Velvet Pulse",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 315,
            "name": "The Nest",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 316,
            "name": "The Lamplight",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 317,
            "name": "Preservation Hall",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 319,
            "name": "Streets of New Orleans",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 351,
            "name": "Steelgrave Depot",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 352,
            "name": "Abandoned DOT Weigh Station",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 501,
            "name": "Château du Clair de Lune",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 701,
            "name": "Freeport Hightide Breaker",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 710,
            "name": "The Grid",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 711,
            "name": "Skyline Loop Safehouse",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 721,
            "name": "Darknet Relay",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 722,
            "name": "Noctis Node",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 741,
            "name": "Sam's Ruins",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 742,
            "name": "The Cradle",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 743,
            "name": "Ancient Abyssal Megastructure",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 751,
            "name": "Helix Quay DeepVault",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 791,
            "name": "Crosswind Station",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 801,
            "name": "The Net",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 831,
            "name": "Dynacorp Central R&D Server Farm",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 911,
            "name": "Aurelia Spindle Orbital Station",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 912,
            "name": "Kuiper Watchpoint E-9",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 951,
            "name": "The Bridge",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 971,
            "name": "Dynacorp Black-Site Storage Facility",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 991,
            "name": "The Vault",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 999,
            "name": "out of game",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          }
        ]
      },
      "turns": {
        "chunks_after_first": 1424,
        "later_rows_on_first_chunk": 0,
        "later_rows_per_chunk": {
          "mean": 0.054,
          "max": 77,
          "histogram": {
            "0": 1423,
            "77": 1
          }
        }
      }
    },
    "save_02": {
      "places_total": 77,
      "shared_points": [],
      "first_chunk": {
        "id": 1,
        "created_at": "2025-04-13T09:01:01.189935+00:00",
        "authorial_directives": []
      },
      "genesis": {
        "rows": 0,
        "by_source": {
          "retrograde": 0,
          "trait_compiler": 0,
          "none": 0
        },
        "by_point": {
          "present": 0,
          "null": 0
        }
      },
      "later": {
        "rows": 77,
        "by_source": {
          "retrograde": 0,
          "trait_compiler": 0,
          "none": 77
        },
        "by_point": {
          "present": 50,
          "null": 27
        },
        "rows_detail": [
          {
            "place_id": 1,
            "name": "The Ghost",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 2,
            "name": "The Land Rig",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 3,
            "name": "The Salted Hash\n",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 11,
            "name": "Nomad Camp",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 12,
            "name": "Nomad Bazaar",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 13,
            "name": "Nomad MedTechs",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 21,
            "name": "Rusthaven",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 91,
            "name": "Leviathan",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 92,
            "name": "Data-Barge Okami",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 101,
            "name": "Coastal Safehouse",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 103,
            "name": "Coastal Highway",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 104,
            "name": "Halcyon Atrium",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 106,
            "name": "Omniframe Robotics",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 107,
            "name": "Bougie Mall High-End Fashion Outlet",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 109,
            "name": "Black Market Tech Bazaar",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 111,
            "name": "Skyline Lounge",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 113,
            "name": "Dead Circuit",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 114,
            "name": "Derelict Parking Structure",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 115,
            "name": "Citadel Suites",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 116,
            "name": "Black-Market Netrunner Den",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 119,
            "name": "Night City Streets",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 121,
            "name": "District 07 Shipping Yard",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 122,
            "name": "Alex's Night City Safehouse",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 123,
            "name": "Low Tide",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 124,
            "name": "Back-Alley Hacker Den",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 125,
            "name": "District 06 Hacker Den",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 126,
            "name": "The Eyrie",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 131,
            "name": "Sato's Night City Safehouse",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 132,
            "name": "Orchid Sovereign Institute",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 133,
            "name": "Specialized Underground Cyberclinic",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 141,
            "name": "Aerodyne Research Facility",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 142,
            "name": "Black Market Ripperdoc",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 151,
            "name": "Seaside Grill & Bar",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 152,
            "name": "Lag Siren Lounge",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 153,
            "name": "Blackout Drift Hotel",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 154,
            "name": "Murmur & Ink",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 155,
            "name": "Cliff Overlooking the Sea",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 159,
            "name": "Virginia Beach Streets",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 170,
            "name": "Frederick",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 181,
            "name": "The Silo",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 183,
            "name": "Ordnance Corridor M-7",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 184,
            "name": "Nomad Mechanic Outpost",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 185,
            "name": "Smuggler Shipyard",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 186,
            "name": "Half-Life Waystation",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 191,
            "name": "Data Tomb",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 192,
            "name": "Private Dynacorp Facility",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 193,
            "name": "Geotech Field Lab 226-B",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 301,
            "name": "Dynacorp Blacksite",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 311,
            "name": "Le Chat Noir",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 312,
            "name": "Boudreaux’s Haute-Creole Experience",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 313,
            "name": "Le Chuchotement",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 314,
            "name": "The Velvet Pulse",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 315,
            "name": "The Nest",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 316,
            "name": "The Lamplight",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 317,
            "name": "Preservation Hall",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 319,
            "name": "Streets of New Orleans",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 351,
            "name": "Steelgrave Depot",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 352,
            "name": "Abandoned DOT Weigh Station",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 501,
            "name": "Château du Clair de Lune",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 701,
            "name": "Freeport Hightide Breaker",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 710,
            "name": "The Grid",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 711,
            "name": "Skyline Loop Safehouse",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 721,
            "name": "Darknet Relay",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 722,
            "name": "Noctis Node",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 741,
            "name": "Sam's Ruins",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 742,
            "name": "The Cradle",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 743,
            "name": "Ancient Abyssal Megastructure",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 751,
            "name": "Helix Quay DeepVault",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 791,
            "name": "Crosswind Station",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 801,
            "name": "The Net",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 831,
            "name": "Dynacorp Central R&D Server Farm",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 911,
            "name": "Aurelia Spindle Orbital Station",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 912,
            "name": "Kuiper Watchpoint E-9",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 951,
            "name": "The Bridge",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 971,
            "name": "Dynacorp Black-Site Storage Facility",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 991,
            "name": "The Vault",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 999,
            "name": "out of game",
            "source": "none",
            "has_point": false,
            "turn_chunk_id": 1425,
            "turn_attribution": "created_at"
          }
        ]
      },
      "turns": {
        "chunks_after_first": 1424,
        "later_rows_on_first_chunk": 0,
        "later_rows_per_chunk": {
          "mean": 0.054,
          "max": 77,
          "histogram": {
            "0": 1423,
            "77": 1
          }
        }
      }
    },
    "save_03": {
      "places_total": 5,
      "shared_points": [
        {
          "lon": -122.3321,
          "lat": 47.6062,
          "place_ids": [
            1,
            4
          ],
          "names": [
            "Lantern Quay Memorial Hall",
            "Lantern Quay Coolant Lanes"
          ]
        }
      ],
      "first_chunk": {
        "id": 1,
        "created_at": "2026-07-30T04:55:20.251348+00:00",
        "authorial_directives": [
          "orrery:retrograde_prologue_anchor"
        ]
      },
      "genesis": {
        "rows": 1,
        "by_source": {
          "retrograde": 0,
          "trait_compiler": 0,
          "none": 1
        },
        "by_point": {
          "present": 1,
          "null": 0
        }
      },
      "later": {
        "rows": 4,
        "by_source": {
          "retrograde": 3,
          "trait_compiler": 0,
          "none": 1
        },
        "by_point": {
          "present": 1,
          "null": 3
        },
        "rows_detail": [
          {
            "place_id": 2,
            "name": "Cinder Vault",
            "source": "retrograde",
            "has_point": false,
            "turn_chunk_id": 5,
            "turn_attribution": "maturation_job",
            "job_id": 3
          },
          {
            "place_id": 3,
            "name": "Early Continuity Registry",
            "source": "retrograde",
            "has_point": false,
            "turn_chunk_id": 18,
            "turn_attribution": "maturation_job",
            "job_id": 9
          },
          {
            "place_id": 4,
            "name": "Lantern Quay Coolant Lanes",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 22,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 5,
            "name": "Pilgrim Stack 9",
            "source": "retrograde",
            "has_point": false,
            "turn_chunk_id": 24,
            "turn_attribution": "maturation_job",
            "job_id": 12
          }
        ]
      },
      "turns": {
        "chunks_after_first": 39,
        "later_rows_on_first_chunk": 0,
        "later_rows_per_chunk": {
          "mean": 0.103,
          "max": 1,
          "histogram": {
            "0": 35,
            "1": 4
          }
        }
      }
    },
    "save_04": {
      "places_total": 7,
      "shared_points": [
        {
          "lon": -122.3321,
          "lat": 47.6062,
          "place_ids": [
            1,
            4
          ],
          "names": [
            "Lantern Quay Memorial Hall",
            "Lantern Quay Coolant Lanes"
          ]
        }
      ],
      "first_chunk": {
        "id": 1,
        "created_at": "2026-07-30T04:55:20.251348+00:00",
        "authorial_directives": [
          "orrery:retrograde_prologue_anchor"
        ]
      },
      "genesis": {
        "rows": 1,
        "by_source": {
          "retrograde": 0,
          "trait_compiler": 0,
          "none": 1
        },
        "by_point": {
          "present": 1,
          "null": 0
        }
      },
      "later": {
        "rows": 6,
        "by_source": {
          "retrograde": 5,
          "trait_compiler": 0,
          "none": 1
        },
        "by_point": {
          "present": 1,
          "null": 5
        },
        "rows_detail": [
          {
            "place_id": 2,
            "name": "Cinder Vault",
            "source": "retrograde",
            "has_point": false,
            "turn_chunk_id": 5,
            "turn_attribution": "created_at",
            "job_id": 3,
            "job_row_found": false
          },
          {
            "place_id": 3,
            "name": "Early Continuity Registry",
            "source": "retrograde",
            "has_point": false,
            "turn_chunk_id": 19,
            "turn_attribution": "created_at",
            "job_id": 9,
            "job_row_found": false
          },
          {
            "place_id": 4,
            "name": "Lantern Quay Coolant Lanes",
            "source": "none",
            "has_point": true,
            "turn_chunk_id": 22,
            "turn_attribution": "created_at"
          },
          {
            "place_id": 5,
            "name": "Pilgrim Stack 9",
            "source": "retrograde",
            "has_point": false,
            "turn_chunk_id": 24,
            "turn_attribution": "created_at",
            "job_id": 12,
            "job_row_found": false
          },
          {
            "place_id": 6,
            "name": "West Conduit Relay",
            "source": "retrograde",
            "has_point": false,
            "turn_chunk_id": 46,
            "turn_attribution": "maturation_job",
            "job_id": 16
          },
          {
            "place_id": 7,
            "name": "Wickglass Dispatch House",
            "source": "retrograde",
            "has_point": false,
            "turn_chunk_id": 46,
            "turn_attribution": "maturation_job",
            "job_id": 16
          }
        ]
      },
      "turns": {
        "chunks_after_first": 45,
        "later_rows_on_first_chunk": 0,
        "later_rows_per_chunk": {
          "mean": 0.133,
          "max": 2,
          "histogram": {
            "0": 40,
            "1": 4,
            "2": 1
          }
        }
      }
    },
    "save_05": {
      "places_total": 0,
      "shared_points": [],
      "first_chunk": null
    }
  }
}
```
