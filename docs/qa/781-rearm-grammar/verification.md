# 781-S1 Verification: Rearm Grammar Weight

- Date: 2026-10-01 (America/Chicago).
- Base commit: `56c884e7` (`origin/main`); the script and tests are the ones committed on `claude/781-rearm-grammar-measure` beside this file.
- Interpreter: the shared `/Users/pythagor/nexus/.venv/bin/python`, run from the worktree root with `PYTHONPATH=$PWD`; `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset.
- Token counts are local estimates from the configured models' registered counters (`estimator_for`), not billed counts. Read deltas, not absolutes.

## Offline Report, Two Runs

```sh
PYTHONPATH=$PWD "$PY" scripts/qa_shift/rearm_grammar_weight.py --skip-registry > offline_1.md
PYTHONPATH=$PWD "$PY" scripts/qa_shift/rearm_grammar_weight.py --skip-registry > offline_2.md
cmp offline_1.md offline_2.md   # no output, exit 0
```

- gaia_model: gpt-6-astra
- gaia_tokenizer: {"token_count_safety_margin": 0, "tokenizer_encoding": "o200k_base", "tokenizer_repository": null}
- single_pass_model: gpt-6-astra
- single_pass_tokenizer: {"token_count_safety_margin": 0, "tokenizer_encoding": "o200k_base", "tokenizer_repository": null}
- registry: skipped

| seat | surface | variant | bytes | tokens | Δ bytes | Δ tokens | Δ bytes % |
|---|---|---|---:|---:|---:|---:|---:|
| gaia | strict | baseline | 14,427 | 3,260 | +0 | +0 | +0.00% |
| gaia | strict | typed_fields | 15,535 | 3,529 | +1,108 | +269 | +7.68% |
| gaia | strict | minimal_typed | 15,093 | 3,420 | +666 | +160 | +4.62% |
| gaia | strict | compact_string | 14,595 | 3,316 | +168 | +56 | +1.16% |
| gaia | strict | package_default | 14,600 | 3,311 | +173 | +51 | +1.20% |
| gaia | lenient | baseline | 13,329 | 2,942 | +0 | +0 | +0.00% |
| gaia | lenient | typed_fields | 14,328 | 3,174 | +999 | +232 | +7.49% |
| gaia | lenient | minimal_typed | 13,974 | 3,094 | +645 | +152 | +4.84% |
| gaia | lenient | compact_string | 13,476 | 2,990 | +147 | +48 | +1.10% |
| gaia | lenient | package_default | 13,481 | 2,985 | +152 | +43 | +1.14% |
| gaia | guide | baseline | 2,372 | 615 | +0 | +0 | +0.00% |
| gaia | guide | typed_fields | 2,543 | 670 | +171 | +55 | +7.21% |
| gaia | guide | minimal_typed | 2,500 | 657 | +128 | +42 | +5.40% |
| gaia | guide | compact_string | 2,386 | 620 | +14 | +5 | +0.59% |
| gaia | guide | package_default | 2,386 | 620 | +14 | +5 | +0.59% |
| single_pass | strict | baseline | 20,136 | 4,536 | +0 | +0 | +0.00% |
| single_pass | strict | typed_fields | 21,244 | 4,805 | +1,108 | +269 | +5.50% |
| single_pass | strict | minimal_typed | 20,802 | 4,696 | +666 | +160 | +3.31% |
| single_pass | strict | compact_string | 20,304 | 4,592 | +168 | +56 | +0.83% |
| single_pass | strict | package_default | 20,309 | 4,587 | +173 | +51 | +0.86% |
| single_pass | lenient | baseline | 18,596 | 4,092 | +0 | +0 | +0.00% |
| single_pass | lenient | typed_fields | 19,595 | 4,324 | +999 | +232 | +5.37% |
| single_pass | lenient | minimal_typed | 19,241 | 4,244 | +645 | +152 | +3.47% |
| single_pass | lenient | compact_string | 18,743 | 4,140 | +147 | +48 | +0.79% |
| single_pass | lenient | package_default | 18,748 | 4,135 | +152 | +43 | +0.82% |
| single_pass | guide | baseline | 6,773 | 1,492 | +0 | +0 | +0.00% |
| single_pass | guide | typed_fields | 7,245 | 1,608 | +472 | +116 | +6.97% |
| single_pass | guide | minimal_typed | 7,073 | 1,567 | +300 | +75 | +4.43% |
| single_pass | guide | compact_string | 6,849 | 1,521 | +76 | +29 | +1.12% |
| single_pass | guide | package_default | 6,854 | 1,516 | +81 | +24 | +1.20% |

The baseline rows equal the coordinator's measurements: Gaia strict 14,427 / 3,260, lenient 13,329 / 2,942, guide 2,372 / 615; single-pass strict 20,136 / 4,536, lenient 18,596 / 4,092, guide 6,773 / 1,492.

## Registry Report on `save_04`

The only owner read. `main()` prepends `-c default_transaction_read_only=on` to `PGOPTIONS`, proves `SHOW transaction_read_only` is `on` on one session, then builds the registry model without scene entities.

```sh
PYTHONPATH=$PWD "$PY" scripts/qa_shift/rearm_grammar_weight.py --registry-dbname save_04
```

- gaia_model: gpt-6-astra
- gaia_tokenizer: {"token_count_safety_margin": 0, "tokenizer_encoding": "o200k_base", "tokenizer_repository": null}
- single_pass_model: gpt-6-astra
- single_pass_tokenizer: {"token_count_safety_margin": 0, "tokenizer_encoding": "o200k_base", "tokenizer_repository": null}
- registry_dbname: save_04
- registry_digest: 5a2f4f690ad9

| seat | surface | variant | bytes | tokens | Δ bytes | Δ tokens | Δ bytes % |
|---|---|---|---:|---:|---:|---:|---:|
| gaia | strict | baseline | 14,427 | 3,260 | +0 | +0 | +0.00% |
| gaia | strict | typed_fields | 15,535 | 3,529 | +1,108 | +269 | +7.68% |
| gaia | strict | minimal_typed | 15,093 | 3,420 | +666 | +160 | +4.62% |
| gaia | strict | compact_string | 14,595 | 3,316 | +168 | +56 | +1.16% |
| gaia | strict | package_default | 14,600 | 3,311 | +173 | +51 | +1.20% |
| gaia | lenient | baseline | 13,329 | 2,942 | +0 | +0 | +0.00% |
| gaia | lenient | typed_fields | 14,328 | 3,174 | +999 | +232 | +7.49% |
| gaia | lenient | minimal_typed | 13,974 | 3,094 | +645 | +152 | +4.84% |
| gaia | lenient | compact_string | 13,476 | 2,990 | +147 | +48 | +1.10% |
| gaia | lenient | package_default | 13,481 | 2,985 | +152 | +43 | +1.14% |
| gaia | guide | baseline | 2,372 | 615 | +0 | +0 | +0.00% |
| gaia | guide | typed_fields | 2,543 | 670 | +171 | +55 | +7.21% |
| gaia | guide | minimal_typed | 2,500 | 657 | +128 | +42 | +5.40% |
| gaia | guide | compact_string | 2,386 | 620 | +14 | +5 | +0.59% |
| gaia | guide | package_default | 2,386 | 620 | +14 | +5 | +0.59% |
| single_pass | strict | baseline | 20,136 | 4,536 | +0 | +0 | +0.00% |
| single_pass | strict | typed_fields | 21,244 | 4,805 | +1,108 | +269 | +5.50% |
| single_pass | strict | minimal_typed | 20,802 | 4,696 | +666 | +160 | +3.31% |
| single_pass | strict | compact_string | 20,304 | 4,592 | +168 | +56 | +0.83% |
| single_pass | strict | package_default | 20,309 | 4,587 | +173 | +51 | +0.86% |
| single_pass | lenient | baseline | 18,596 | 4,092 | +0 | +0 | +0.00% |
| single_pass | lenient | typed_fields | 19,595 | 4,324 | +999 | +232 | +5.37% |
| single_pass | lenient | minimal_typed | 19,241 | 4,244 | +645 | +152 | +3.47% |
| single_pass | lenient | compact_string | 18,743 | 4,140 | +147 | +48 | +0.79% |
| single_pass | lenient | package_default | 18,748 | 4,135 | +152 | +43 | +0.82% |
| single_pass | guide | baseline | 6,773 | 1,492 | +0 | +0 | +0.00% |
| single_pass | guide | typed_fields | 7,245 | 1,608 | +472 | +116 | +6.97% |
| single_pass | guide | minimal_typed | 7,073 | 1,567 | +300 | +75 | +4.43% |
| single_pass | guide | compact_string | 6,849 | 1,521 | +76 | +29 | +1.12% |
| single_pass | guide | package_default | 6,854 | 1,516 | +81 | +24 | +1.20% |
| gaia_registry | strict | baseline | 23,846 | 5,806 | +0 | +0 | +0.00% |
| gaia_registry | strict | typed_fields | 24,948 | 6,076 | +1,102 | +270 | +4.62% |
| gaia_registry | strict | minimal_typed | 24,512 | 5,966 | +666 | +160 | +2.79% |
| gaia_registry | strict | compact_string | 24,014 | 5,862 | +168 | +56 | +0.70% |
| gaia_registry | strict | package_default | 24,019 | 5,857 | +173 | +51 | +0.73% |

The registry baseline equals the coordinator's 23,846 bytes / 5,806 tokens at digest `5a2f4f690ad9`.

## Tests

```sh
NEXUS_RUN_POSTGRES=1 "$PY" -m pytest -q -p tests.dbname_audit tests/test_orrery/test_rearm_grammar_weight.py tests/test_orrery/test_gaia_registry_schema_pg.py tests/test_skald_wire.py tests/test_owner_target_guard.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 5 targets: postgres, qa638_*, qa640_781s1_*, qa640_811_gaia_scene_*, qa885_presence_baseline_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
184 passed, 2 skipped, 2 warnings in 10.46s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

The two skips are the paid live gates (`NEXUS_638_ENUM_E2E`, `NEXUS_639_PRESENCE_E2E`).

```sh
"$PY" -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2667 passed, 428 skipped, 8 warnings in 398.30s (0:06:38)
```

```sh
"$PY" -m pytest -q tests/test_api tests/test_orrery
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1825 passed, 744 skipped, 7 warnings in 38.56s
```

```sh
"$PY" -m pytest -q tests/test_reachability.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 9.95s
```

```sh
"$PY" -m black --check scripts/qa_shift/rearm_grammar_weight.py tests/test_orrery/test_rearm_grammar_weight.py
"$PY" -m flake8 scripts/qa_shift/rearm_grammar_weight.py tests/test_orrery/test_rearm_grammar_weight.py
"$PY" -m mypy scripts/qa_shift/rearm_grammar_weight.py tests/test_orrery/test_rearm_grammar_weight.py
```

```text
All done! ✨ 🍰 ✨
2 files would be left unchanged.
black exit 0
flake8 exit 0
Success: no issues found in 2 source files
mypy exit 0
```
