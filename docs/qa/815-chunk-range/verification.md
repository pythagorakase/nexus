# Bounded Chunk Range and Inspect Dependency Proof

Refs #815 (815-S2 and 815-S7). Implementation follows the frozen order at
`temp/orders_2026_10_07/815-S2.md` from the coordinator's primary checkout.
The branch merges main `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8` through
`25532a662b3ae3e4de90a71903d2de5d9bbc7e43`; no history was rewritten.

## Behavior and Source Review

`get_chunk_range` in `nexus/api/reader_endpoints.py:310` serves one keyset page in
ascending or descending ID order. Both bounds are exclusive; the existing
`ui.reader.max_page_size` caps the response, and one extra row determines
whether to return the page's last ID as `nextCursor`. Payloads come from the
same `_chunk_payload` as the single-chunk route. The reader feed, latest,
adjacent, and single-chunk routes remain unchanged.

`_inspect_chunks` (`nexus/cli.py:1524`) and `_chunk_page` (`:1488`) follow pages rather than
making one adjacent-chunk request per row. `--last` reverses the collected
newest-first pages for display; a range keeps its upper bound on every request.
Malformed shapes, non-integer IDs/cursors (including booleans and floats),
oversized pages, nonadvancing IDs within/across pages, out-of-bound IDs, and
invalid continuation cursors fail with `invalid_response`.

The exact legacy `_inspect_chunks` exception-baseline entry ending
`e4bcef6ba89efbed878149ed9cb4e246fa2e7a8e6073ea30d56e47006b5476ac|1`
is deleted with the swallowed 404 body parse. No new exception handler or
fallback is added.

The CLI passes character, place, and faction responses through field for field.
Serving-boundary spoiler gating remains #769 (`_entity_family`,
`nexus/cli.py:1592`, and `_print_inspection`, `:1665`, are unchanged). The real gateway comparison covers
all three families; this lane does not implement field filtering. The current
character projection already removes exact diagnostic placeholders on legacy
Retrograde stubs; that existing behavior is retained and is not spoiler gating.
The coordinator must record on #769 the additional character `personality` and
`background` fields and place/faction `extraData`. 815-R8 stays open until #769.

Two independent source reviews (coordinator and `inventory_worktrees`) found no
blocking defect in the single SQL query, bound/probe behavior, cursor checks,
remaining-count traversal, or unchanged entity projections. These were source
reviews, not claims of additional test runs.

## Fresh Read-Only Gap Survey

On 2026-10-08, the following command ran for each of `save_03` and `save_04`:

```sh
PGOPTIONS='-c default_transaction_read_only=on' \
  /Applications/Postgres.app/Contents/Versions/17/bin/psql -X -d save_03 -Atc \
  "SELECT current_database(), current_setting('default_transaction_read_only'), count(*), min(nc.id), max(nc.id) FROM narrative_chunks nc JOIN chunk_metadata cm ON cm.chunk_id = nc.id"
```

[Raw output](gap-survey.txt): `save_03|on|40|1|100` and
`save_04|on|46|1|49`. These are joined committed-row counts, not counts of the
new route's playable rows. No owner writes were performed.

## Initial Red Proof

Before changing product code, main's old implementation failed all seven new
selected checks in 6.09 seconds: six real-PG route cases received 404; the
classification case raised `KeyError` for the absent route. The imported
`nexus.__file__` was inside this exact worktree.

```sh
nice -n 15 env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT \
  -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_CORPUS \
  PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 \
  /Users/pythagor/nexus/.venv/bin/python -m pytest -q \
  -p tests.dbname_audit -p no:cacheprovider \
  tests/test_api/test_reader_chunk_range_pg.py \
  tests/test_api/test_route_capabilities.py::test_chunk_range_is_player_read_without_provider_effect
```

[Raw red output](initial-red.txt) records `7 failed, 7 warnings in 6.09s`,
secret-store guard active, receipts untouched, and owner targets none. Both
clone targets use the ordered `qa640_815s2_range*` prefixes. The suite reported
its normal circular-FK pg_dump warnings; neither clone preparation nor cleanup
failed.

## Focused Green and Reverted Controls

The focused run passed **458 tests**, with **2 opt-in corpus skips** and
**9 warnings**, in **273.96 seconds**. The six new real-PG route cases, real
TEST-provider gateway inspect traversal and pass-through comparison, malformed
and repeated-page HTTP checks, route classification, existing reader tests,
owner-target guards, lifecycle consumers, reachability, document freshness and
CLI reference check all ran. `NEXUS_RUN_CORPUS` was unset as ordered.

```sh
nice -n 15 env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT \
  -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_CORPUS \
  PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 \
  /Users/pythagor/nexus/.venv/bin/python -m pytest -q \
  -p tests.dbname_audit -p no:cacheprovider \
  tests/test_api/test_reader_chunk_range_pg.py \
  tests/test_api/test_reader_feed_pg.py \
  tests/test_api/test_reader_asset_endpoints.py \
  tests/test_cli_inspect_pg.py tests/test_api/test_route_capabilities.py \
  tests/test_cli_contract.py tests/test_owner_target_guard.py \
  tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py \
  tests/test_reachability.py tests/test_doc_front_matter.py \
  tests/test_cli_reference_doc.py
```

[Raw green output](focused-green.txt) ends with:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner targets: none
458 passed, 2 skipped, 9 warnings in 273.96s (0:04:33)
```

The connection lifecycle test also registered two disposable PostgreSQL
clusters on local ports 51970/51971, where its isolated `save_04` names were
admitted. Neither was an owner target. The audit discloses its existing
unaudited replication-connection class; no claim of universal instrumentation
is made. Warnings were existing OpenTelemetry/SWIG deprecations and real
local-model test warnings, not paid inference.

The two corpus skips are the synchronous/asynchronous variants of
`test_card_exposure_rank_joint_and_backstage_parity`; no owner-corpus proof is
claimed.

The [raw control runner](red-controls.py.txt) ran the following scratch plants
serially, restoring each original byte sequence in `finally`. It checked load
below 24, applied `nice -n 15` to each pytest process, enforced all three guard
lines, and required exactly the selected test to fail.

| Plant | Observed failure | Result and raw proof |
| --- | --- | --- |
| Bind `LIMIT` to `page_size` instead of `page_size + 1` | Desc walk returns `[10, 9, 7]`, losing four later rows | `1 failed, 5 warnings in 2.90s`; [log](route-probe-red.txt), [patch](route-probe-red.patch.txt) |
| Stop descending CLI traversal after its first page | `--last 3` returns `[3, 4]` instead of `[2, 3, 4]` | `1 failed, 4 warnings in 17.04s`; [log](cli-desc-first-page-red.txt), [patch](cli-desc-first-page-red.patch.txt) |
| Stop ascending CLI traversal after its first page | Full range returns `[1, 2]` instead of `[1, 2, 3, 4]` | `1 failed, 4 warnings in 18.89s`; [log](cli-asc-first-page-red.txt), [patch](cli-asc-first-page-red.patch.txt) |

The route control selected
`tests/test_api/test_reader_chunk_range_pg.py::test_desc_pages_walk_every_playable_chunk_across_gaps`.
Both CLI controls selected
`tests/test_cli_inspect_pg.py::test_continue_waits_then_inspect_reads_the_played_clone`.
The CLI plants ran separately so the first failed assertion could not conceal
the second traversal's failure. Each log includes its exact command, initial
load and final guard/receipt/owner-audit tail. All ended with owner targets none.

[Restoration receipt](control-restoration.txt) and a final independent
`shasum -a 256` check agree:

```text
ca346db83d506dcbc60979b8e7e784cc797a2bb6d3ad9d5fb67504944a7ce2f2  nexus/api/reader_endpoints.py
08dbf12479cbc1f6cc148bf05ac8d625088dba5f7043504a3597e924ee5c5547  nexus/cli.py
```

`git diff --check` passed after restoration and the suite's 8018 listener was
absent. The source tested green is unchanged; no duplicate focused run was
needed. No whole-tree or separate full offline run is claimed here; the
coordinator owns the combined gate before push/PR.

## Static Checks and Freshness Adaptation

Black checks all eight changed Python files: [output](black.txt). Flake8 reports
15 existing long-line diagnostics, matching the original main files by path and
message; none is on a changed line ([branch](flake8.txt), [main](flake8-main.txt)).
Mypy with `--explicit-package-bases` reports seven existing optional-integer
comparison diagnostics in `settings_models.py`, identical to main
([branch](mypy.txt), [main](mypy-main.txt)). The new tests and modified production
logic add no diagnostics. All static commands checked the same eight changed
Python files, with the new range-test file absent from the seven-file main
comparison; Black used `--check`, flake8 used its repository configuration, and
mypy used `--explicit-package-bases` with this worktree in `PYTHONPATH`. Main source files were copied using
`git show origin/main:<path>` into `/tmp/nexus-815-static-main` for the same
sanctioned checks; no main worktree file was edited.

The [exception-disposition check](exception-dispositions.txt) passes with
`--baseline-base-ref origin/main` and the one required baseline deletion.
`python -m scripts.render_cli_reference --write` regenerated the two inspect
help descriptions added to the canonical CLI inventory by landed #817.

The frozen order's assertion that no declared source changes is stale after
#817. Decision records 0009, 0020, and 0050 now declare `cli.py` or
`reader_endpoints.py`; their rulings still hold (token-only usage, no inferred
claim/scene evidence, continuous-book reader). Their `verified_commit` stamps
advance to main `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`. Quoted rulings and
source URLs are unchanged. No unrelated document stamp is changed.

## Landing Boundaries

No migration, fleet application, UI change, UI build, state-surface regeneration,
model download or artifact modification, paid call, or owner service operation belongs to this lane.
Product Python changes require the gateway to pick up the code when the
coordinator later starts services. `nexus.toml` remains unchanged, including its
now-incomplete “Feed page bounds” comment, as explicitly deferred by the order.
Other #815 slices and owner question 815-Q1 remain outside this scope.

## Shared Integration Validation

The assembled integration `2cc9a5fcff76e0c643ca41490eb2508b870b4850`, including this lane input `5fcc76e43428a570f095e10d8944fdc93b321e27`, passed the full PostgreSQL-enabled Python gate: **7,056 passed, 72 skipped, 41 warnings**. [Exact commands, immutable tree/input ancestry, complete logs and audit limits](https://github.com/pythagorakase/nexus/blob/bf229051e3d046b76ab8d18b34e9ee054a03bbf6/docs/qa/resume-wave-a-2026-10-08/verification.md). All three pieces reported active secret-store protection, untouched receipts and owner targets none. This is assembled-tree coverage; no separate standalone branch full gate or whole-suite offline run is claimed. Later changes here are evidence only; any landing merge/freshness changes require their own delta record.

Codex — GPT-6

## Review follow-up

The reviewer found no blocking correctness issue. Condensed the UIReaderSettings docstring; compilation and an AST comparison excluding docstrings confirm unchanged executable code. The route already documents the configured cap and both continuation directions. Required raw red/green/control logs remain durable evidence. The next landing check revalidates canonical freshness after merging current main.

Codex — GPT-6

## Landing merge

Merged `origin/main` at `54ee3dc1f811d1504d60bcdf0ecf3440c4e86397` by an ordinary merge, without conflicts. Re-read decisions 0009, 0020 and 0050 against the remaining source delta: chunk pagination does not add prices, revelation-scene links or a different reader policy. Their bodies and rulings remain unchanged; verified stamps now name this merge base. The route matches the assembled gate bytes. CLI differences from that integration are the separately verified type-only grouping and absent, not-yet-landed 812 model verbs; settings also lacks the pending 777 announcer schema and has the docstring-only review fix. No executable source was newly edited during landing.

Codex — GPT-6

Final landing check on `fcfd53599e98b6c31bc83fc6c7da5e184abaf98e`: 76 document-freshness and generated-CLI-reference cases passed, with active secret-store protection, untouched receipts and owner targets none. Commands, exact tree, import admission and logs are under `landing/`. This evidence-only commit does not alter the checked source.

Codex — GPT-6
