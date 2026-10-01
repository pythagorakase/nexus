# Verification: 756-S2 Deep-Query Candidate Count

## Disposition — 2026-10-01

The amended proof is complete. The real LORE/MEMNON corpus test passes for both
k=3 and k=15 using disposable data clones of `save_01`. Restoring the literal 15
fails the k=3 count assertion; removing that plant passes both cases. The required
PostgreSQL set, focused offline set, both broad offline suites, reachability,
Black, configuration validation, and no-new-diagnostics static gate are complete.
No time-truth or latency conclusion is drawn from the corpus.

Original starting commit: `5b977eabcba5f7aedf1a64a6ee20c021ab290911`.
Resumed from accepted stop-report commit `f844c0d4`, with implementation `d4752498`.
The resumed source/format commit was `0a99a005`. After fetching, the required
rebase onto `origin/main` at `36ec0b2601811a0f89972542352e36c272be90c7` replayed the
three patches without conflicts, squashing, or content edits. `git range-diff
5b977eab..0a99a005 origin/main..HEAD` reported `=` for each:

| Original | Rebased | Contents |
| --- | --- | --- |
| `d4752498` | `674455f1` | Implementation |
| `f844c0d4` | `8d4d4f9c` | Accepted stop-report |
| `0a99a005` | `c987ea33` | Amended source and description formatting |

The original stop-report is retained as a dated section below. Its blocker is
fixture issue **#1083**. Amendment 1 changes only the corpus source to `save_01`;
`tests/pg_fixtures.py` is unchanged. No source migration or bootstrap workaround
was introduced. Read order: common rules, frozen order, amendment, stop-report.
Issue #756 comments were also fetched and inspected; only 756-R6 is implemented.

## Verified Current Behavior and Scope

- `nexus.toml:264-266` adds only `deep_query_k = 15` to `[lore.retrieval]`.
  `nexus/config/settings_models.py:1253-1269` keeps `extra="forbid"`, adds the
  default 15 and `ge=1`, with the prescribed description (wrapped without changing
  its string). `LORESettings.retrieval` retains its default factory at line 1323.
- Before this change, `turn_cycle.py:692` at starting commit `5b977eab` supplied
  literal `"k": 15`; `_max_deep_queries` read its typed sibling at lines 244-247.
  Now `nexus/agents/lore/utils/turn_cycle.py:249-252` reads the new typed field,
  line 687 resolves it, line 698 supplies it, and line 709 calls real MEMNON.
  There is no fallback or clamp.
- `nexus/agents/memnon/memnon.py:1621-1629,1656-1664` passes k to hybrid search;
  line 1696 truncates to k, and lines 1721-1723 impose the independent reranker
  cap. MEMNON is unchanged. The shipped reranker `top_k=30` at `nexus.toml:1143`
  and deduplicator limit 30 at `turn_cycle.py:133-149` are unchanged. The raw-chunk
  query construction remains at lines 658-667 and deduplication at line 725.
- `tests/config/test_settings_models.py:996-1049` checks the explicit shipped
  TOML key, loaded value and model default; rejects 0, -1 and a misspelled key at
  the exact Pydantic error locations/types; and proves equal Pass-2 fingerprints
  for validated k=3 and k=15 configurations.
- `nexus/memory/baseline_compat.py:38-43,125-135` still fingerprints only `[memory]`
  and `[lore.token_budget]`. It is unchanged. `docs/settings_scopes.md:74` contains
  the prescribed scope paragraph; no baseline refresh is required.
- `nexus/config/loader.py:378-384` copies the whole typed LORE section.
  `tests/config/test_settings_parity.py:272-277` gives the new leaf its owner;
  the focused suite passes the parity gate at lines 846-854.
- `tests/test_lore/test_assembled_prompt_fingerprint.py:125,308` explicitly pins
  and projects 15. The expected request digests and pinned Pass-2 hash are
  unchanged in the diff against main; all assembled-prompt checks passed again
  after rebase. No prompt file, budget policy, or other tuning value is changed
  by this branch.

## Corpus and Mutation Evidence

`tests/test_lore/test_window_coverage_pg.py:213-283` is marked `requires_corpus`
and retains the module PostgreSQL marker. Lines 228-232 request
`disposable_slot_database("qa640_756_deep_query", source_db="save_01", include_data=True)`.
Slot 5 is routed to each clone at line 233. LORE receives the temporary TOML,
clone dbname, and TEST override at lines 234-240; `finally` closes it at line 283.
No retrieval function, model loader, or result is mocked. Shipped embedding,
hybrid-search and reranker settings are used unchanged.

The source is accessed through the fixture's `pg_dump` only
(`tests/pg_fixtures.py:200-212`). Restore targets `dbname` (lines 214-232), and
TEST pinning/migration target only that clone (lines 233-234).
`save_01` was never connected to for a write or passed to `migrate.py`.
The amendment describes it as migration 140 with 1,425 chunks; those source
statistics were not independently queried in this run and are not proof claims.

The first non-empty chunk selected on each clone was **id 1**. Its first 32 words:

```text
<!-- SCENE BREAK: S01E01_001 (episode heading) --> # S01E01: The Fall ## Storyteller Welcome to **Night City Stories**, a neon-lit sprawl where megacorporations own your soul, the streets chew you up, and
```

| Product Call Site | Configured k | Broad Count (k=30) | Queries Executed | Results Retrieved | Pool Count | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Typed reader | 3 | 30 | 1 | 3 | 3 | Pass |
| Typed reader | 15 | 30 | 1 | 15 | 15 | Pass |
| Mutation: literal 15 | 3 | 30 | 1 | 15 | 15 | Required failure: `assert 15 == 3` |
| Mutation: literal 15 | 15 | 30 | 1 | 15 | 15 | Pass |
| Restored typed reader | 3 | 30 | 1 | 3 | 3 | Pass |
| Restored typed reader | 15 | 30 | 1 | 15 | 15 | Pass |

Passing cases also assert that every `memory_identity` is non-NULL and distinct
(lines 274-281). The post-rebase full proof repeats both passing counts. No corpus
case skipped. All pytest runs kept the provider-only and secret-store guards;
no paid provider call was enabled and no gateway was launched for this order.
The audit reported no owner targets. Its documented gaps remain: subprocess
connections and the unaudited replication class are not covered by that audit.

## Proof Commands and Complete Tails

All commands ran from this worktree using the shared interpreter, never
`poetry install`. Import provenance was checked before proofs and after rebase:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus; print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/756-deep-query-count-setting/nexus/__init__.py
```

Exit 0. Each gate below used `<scratch>/run_gate.py <label> <command>` with a
570-second deadline and 120-second silence limit. Neither fired. The wrapper
sets `PYTHONPATH=$PWD`, `TMPDIR=<scratch>` and `PYTHONUNBUFFERED=1` and records the
exact argv, complete log and exit status. Scratch is exclusively:

`/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/`

Both broad offline suites ran completely before rebase. After main advanced by
one commit (#1063), the full required PostgreSQL proof and focused offline suite
ran again. All test files changed by that incoming commit plus reachability ran
as an additional offline gate. Broad-suite skips are their intentional offline
selection, not PostgreSQL proof. No #885 failure exemption was used.

### PostgreSQL Proof After Rebase

Log: `rebased-postgres.log`.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 NEXUS_RUN_CORPUS=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_lore/test_window_coverage_pg.py tests/test_memnon_model_failures_pg.py tests/test_orrery/test_recall_disclosure_pg.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
```

```text
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

tests/test_lore/test_window_coverage_pg.py: 1 warning
tests/test_memnon_model_failures_pg.py: 10 warnings
  /Users/pythagor/nexus/.claude/worktrees/756-deep-query-count-setting/nexus/agents/memnon/utils/cross_encoder.py:173: UserWarning: 'has_mps' is deprecated, please use 'torch.backends.mps.is_built()'
    elif hasattr(torch, "has_mps") and torch.backends.mps.is_built():

tests/test_lore/test_window_coverage_pg.py::test_window_coverage_is_written_only_from_post_render_kept_chunks
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/transformers/convert_slow_tokenizer.py:559: UserWarning: The sentencepiece tokenizer that you are converting to a fast tokenizer uses the byte fallback option which is not implemented in the fast tokenizers. In practice this means that the fast version of the tokenizer can produce unknown tokens whereas the sentencepiece version would have converted these unknown tokens into a sequence of byte tokens matching the original piece of text.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 24 targets: postgres, qa640_756_deep_query_* x2, qa640_historical_coverage_* x3, qa640_window_coverage_*, qa885_transaction_writer_*, qa_model_failures_* x15, qa_wt724_recall_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
183 passed, 19 warnings in 95.51s (0:01:35)

EXIT STATUS: 0
```

### Mutation Red

Log: `resumed-mutation-red.log`.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 NEXUS_RUN_CORPUS=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_lore/test_window_coverage_pg.py -k configured_k_bounds_the_deep_query_pool
```

```text
756-S2: k=3; chunk_id=1; query='<!-- SCENE BREAK: S01E01_001 (episode heading) --> # S01E01: The Fall ## Storyteller Welcome to **Night City Stories**, a neon-lit sprawl where megacorporations own your soul, the streets chew you up, and'; broad_count=30; results_retrieved=15; pool_count=15
F756-S2: k=15; chunk_id=1; query='<!-- SCENE BREAK: S01E01_001 (episode heading) --> # S01E01: The Fall ## Storyteller Welcome to **Night City Stories**, a neon-lit sprawl where megacorporations own your soul, the streets chew you up, and'; broad_count=30; results_retrieved=15; pool_count=15
.                                                                       [100%]
=================================== FAILURES ===================================
_______________ test_configured_k_bounds_the_deep_query_pool[3] ________________

tmp_path = PosixPath('/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/pytest-of-pythagor/pytest-3/test_configured_k_bounds_the_d0')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10fcdf810>
capsys = <_pytest.capture.CaptureFixture object at 0x10fce5110>, k = 3

    @pytest.mark.requires_corpus
    @pytest.mark.parametrize("k", [3, 15])
    def test_configured_k_bounds_the_deep_query_pool(
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        k: int,
    ) -> None:
        """Real corpus retrieval from narrative_chunks honors configured breadth."""
        config = tmp_path / "nexus.toml"
        config.write_text(
            Path("nexus.toml")
            .read_text()
            .replace("deep_query_k = 15", f"deep_query_k = {k}")
        )
        with disposable_slot_database(
            "qa640_756_deep_query",
            source_db="save_01",
            include_data=True,
        ) as dbname:
            route_slot_to_disposable(monkeypatch.setattr, slot=5, dbname=dbname)
            lore = LORE(
                settings_path=str(config),
                enable_logon=False,
                debug=False,
                dbname=dbname,
                model_override="TEST",
            )
            try:
                assert lore.memnon is not None
                assert lore.turn_manager is not None
                with lore.memnon.db_manager.engine.connect() as conn:
                    row = conn.execute(
                        text(
                            "SELECT id, raw_text FROM narrative_chunks "
                            "WHERE raw_text IS NOT NULL AND btrim(raw_text) <> '' "
                            "ORDER BY id LIMIT 1"
                        )
                    ).first()
                assert row is not None
                chunk_id, raw_text = row
                query = " ".join(raw_text.split()[:32])
                assert query
                broad = lore.memnon.query_memory(query=query, k=30, use_hybrid=True)
                broad_count = len(broad["results"])
                assert broad_count > 15
                context = TurnContext(
                    turn_id="756-deep-query-count",
                    user_input=query,
                    start_time=0,
                    warm_slice=[{"id": chunk_id, "is_target": True, "full_text": query}],
                )
                asyncio.run(lore.turn_manager.execute_deep_queries(context))
                state = context.phase_states["deep_queries"]
                with capsys.disabled():
                    print(
                        f"756-S2: k={k}; chunk_id={chunk_id}; query={query!r}; "
                        f"broad_count={broad_count}; "
                        f"results_retrieved={state['results_retrieved']}; "
                        f"pool_count={len(context.retrieved_passages)}"
                    )
                assert state["queries_executed"] == 1
>               assert state["results_retrieved"] == k
E               assert 15 == 3

tests/test_lore/test_window_coverage_pg.py:275: AssertionError
----------------------------- Captured stderr call -----------------------------

Loading checkpoint shards:   0%|          | 0/2 [00:00<?, ?it/s]
Loading checkpoint shards:  50%|█████     | 1/2 [00:00<00:00,  1.45it/s]
Loading checkpoint shards: 100%|██████████| 2/2 [00:01<00:00,  1.82it/s]
Loading checkpoint shards: 100%|██████████| 2/2 [00:01<00:00,  1.75it/s]
------------------------------ Captured log call -------------------------------
INFO     nexus.lore:lore.py:194 Initializing LORE components...
INFO     nexus.lore:lore.py:199 LORE turn cycle uses deterministic retrieval planning and direct MEMNON search.
INFO     nexus.lore:lore.py:263 MEMNON utility initialized with the configured database
INFO     nexus.lore:lore.py:222 Component initialization complete
INFO     nexus.lore:lore.py:158 LORE agent initialized successfully
INFO     nexus.lore.turn_cycle:turn_cycle.py:742 Deep queries complete: 1 queries executed ({'location': 1}), 15 unique results retrieved
INFO     nexus.lore:lore.py:327 LORE turn stack closed
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

tests/test_lore/test_window_coverage_pg.py::test_configured_k_bounds_the_deep_query_pool[3]
  /Users/pythagor/nexus/.claude/worktrees/756-deep-query-count-setting/nexus/agents/memnon/utils/cross_encoder.py:173: UserWarning: 'has_mps' is deprecated, please use 'torch.backends.mps.is_built()'
    elif hasattr(torch, "has_mps") and torch.backends.mps.is_built():

tests/test_lore/test_window_coverage_pg.py::test_configured_k_bounds_the_deep_query_pool[3]
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

tests/test_lore/test_window_coverage_pg.py::test_configured_k_bounds_the_deep_query_pool[3]
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

tests/test_lore/test_window_coverage_pg.py::test_configured_k_bounds_the_deep_query_pool[3]
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/transformers/convert_slow_tokenizer.py:559: UserWarning: The sentencepiece tokenizer that you are converting to a fast tokenizer uses the byte fallback option which is not implemented in the fast tokenizers. In practice this means that the fast version of the tokenizer can produce unknown tokens whereas the sentencepiece version would have converted these unknown tokens into a sequence of byte tokens matching the original piece of text.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 3 targets: postgres, qa640_756_deep_query_* x2
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_lore/test_window_coverage_pg.py::test_configured_k_bounds_the_deep_query_pool[3]
1 failed, 1 passed, 4 deselected, 9 warnings in 52.29s

EXIT STATUS: 1
```

### Mutation Green

Log: `resumed-mutation-green.log`.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 NEXUS_RUN_CORPUS=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_lore/test_window_coverage_pg.py -k configured_k_bounds_the_deep_query_pool
```

```text
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

tests/test_lore/test_window_coverage_pg.py::test_configured_k_bounds_the_deep_query_pool[3]
  /Users/pythagor/nexus/.claude/worktrees/756-deep-query-count-setting/nexus/agents/memnon/utils/cross_encoder.py:173: UserWarning: 'has_mps' is deprecated, please use 'torch.backends.mps.is_built()'
    elif hasattr(torch, "has_mps") and torch.backends.mps.is_built():

tests/test_lore/test_window_coverage_pg.py::test_configured_k_bounds_the_deep_query_pool[3]
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

tests/test_lore/test_window_coverage_pg.py::test_configured_k_bounds_the_deep_query_pool[3]
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

tests/test_lore/test_window_coverage_pg.py::test_configured_k_bounds_the_deep_query_pool[3]
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/transformers/convert_slow_tokenizer.py:559: UserWarning: The sentencepiece tokenizer that you are converting to a fast tokenizer uses the byte fallback option which is not implemented in the fast tokenizers. In practice this means that the fast version of the tokenizer can produce unknown tokens whereas the sentencepiece version would have converted these unknown tokens into a sequence of byte tokens matching the original piece of text.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 3 targets: postgres, qa640_756_deep_query_* x2
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
2 passed, 4 deselected, 9 warnings in 49.83s

EXIT STATUS: 0
```

### Focused Offline After Rebase

Log: `rebased-focused.log`.

```sh
env -u NEXUS_RUN_POSTGRES -u NEXUS_RUN_LIVE_LLM /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/config tests/test_lore/test_assembled_prompt_fingerprint.py tests/test_lore/test_turn_cycle.py
```

```text
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
151 passed, 5 warnings in 6.77s

EXIT STATUS: 0
```

### First Broad Offline Suite

Log: `resumed-offline-first.log`.

```sh
env -u NEXUS_RUN_POSTGRES -u NEXUS_RUN_LIVE_LLM /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
```

```text
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

tests/test_memnon_cross_encoder_artifact.py::test_qwen3_loads_its_local_folder_and_scores
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/transformers/tokenization_utils_base.py:2718: UserWarning: `max_length` is ignored when `padding`=`True` and there is no truncation strategy. To pad to max length, use `padding='max_length'`.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2737 passed, 459 skipped, 8 warnings in 440.80s (0:07:20)

EXIT STATUS: 0
```

### Second Broad Offline Suite

Log: `resumed-offline-second.log`.

```sh
env -u NEXUS_RUN_POSTGRES -u NEXUS_RUN_LIVE_LLM /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_orrery
```

```text
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1829 passed, 746 skipped, 7 warnings in 39.44s

EXIT STATUS: 0
```

### Reachability

Log: `resumed-reachability.log`.

```sh
env -u NEXUS_RUN_POSTGRES -u NEXUS_RUN_LIVE_LLM /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py
```

```text
=============================== warnings summary ===============================
tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 10.13s

EXIT STATUS: 0
```

### Incoming Main Changes and Reachability After Rebase

Log: `rebased-upstream-offline.log`.

```sh
env -u NEXUS_RUN_POSTGRES -u NEXUS_RUN_LIVE_LLM /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api/test_wizard_confirmation_pg.py tests/test_commit_handler_sync.py tests/test_entity_tag_manifest_apply.py tests/test_faction_table_audit.py tests/test_orrery/test_claim_propagation_live.py tests/test_orrery/test_composition_sources_live.py tests/test_orrery/test_retrograde_maturation.py tests/test_orrery/test_stage2a_status_live.py tests/test_orrery/test_tag_writer.py tests/test_orrery_tag_validation.py tests/test_orrery_tag_validation_pg.py tests/test_prompt_tag_vocabulary_pg.py tests/test_trait_compiler.py tests/test_reachability.py
```

```text
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
228 passed, 113 skipped, 5 warnings in 11.50s

EXIT STATUS: 0
```

### Black Final

Log: `resumed-black-complete.log`.

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check nexus/agents/lore/utils/turn_cycle.py nexus/config/settings_models.py tests/config/test_settings_models.py tests/config/test_settings_parity.py tests/test_lore/test_assembled_prompt_fingerprint.py tests/test_lore/test_window_coverage_pg.py
```

```text
All done! ✨ 🍰 ✨
6 files would be left unchanged.

EXIT STATUS: 0
```

### Configuration Validation

Log: `resumed-config.log`.

```sh
/Users/pythagor/nexus/.venv/bin/python scripts/validate_config_commit.py
```

```text

EXIT STATUS: 0
```

## Pre-existing Diagnostics

The no-new-diagnostics gate passes, although flake8 and mypy each exit 1 on
existing debt. The final flake8 output has 13 diagnostics and the final mypy
output has 12 errors plus 5 notes. All match main exactly modulo line shifts,
including multiplicity; a line mapping confirmed every diagnostic is on an
unchanged line. No suppression or existing-debt fix was added.

The six pre-existing changed Python files were copied using
`git show origin/main:<path>` into `<scratch>/origin-main/<path>`. Their bytes
were checked unchanged after main advanced to `36ec0b26`. Flake8 runs directly
against those copies. Mypy uses the sanctioned `--explicit-package-bases`
invocation with `--shadow-file <path> <scratch-copy>` for each file, preserving
normal module identities while analyzing the actual main file contents. Both
mypy outputs below were rerun after rebase.

An initial direct-path mypy experiment on six isolated copies could not resolve
three relative imports (14 errors). Adding the surrounding main Python tree and
MYPYPATH changed dependency traversal (291 errors). Neither is used as a valid
comparison. Their raw logs remain `resumed-mypy-main.log` and
`resumed-mypy-main-final.log`; the shadow-file run resolves this measurement issue.

During validation, Black first found one indentation artifact from removing the
mutation, and flake8 found the new description exceeded 88 columns. Both were
corrected without behavior changes. The final Black output above is clean;
the field description's exact string is preserved. Initial logs are retained as
`resumed-black.log` and `resumed-flake8.log`.

### Flake8 Branch

Log: `resumed-flake8-final.log`.

```sh
/Users/pythagor/nexus/.venv/bin/python -m flake8 nexus/agents/lore/utils/turn_cycle.py nexus/config/settings_models.py tests/config/test_settings_models.py tests/config/test_settings_parity.py tests/test_lore/test_assembled_prompt_fingerprint.py tests/test_lore/test_window_coverage_pg.py
```

```text
nexus/agents/lore/utils/turn_cycle.py:508:13: F401 'sqlalchemy.text' imported but unused
nexus/config/settings_models.py:79:89: E501 line too long (89 > 88 characters)
nexus/config/settings_models.py:126:89: E501 line too long (90 > 88 characters)
nexus/config/settings_models.py:141:89: E501 line too long (101 > 88 characters)
nexus/config/settings_models.py:149:89: E501 line too long (91 > 88 characters)
nexus/config/settings_models.py:2468:89: E501 line too long (93 > 88 characters)
nexus/config/settings_models.py:4404:89: E501 line too long (131 > 88 characters)
tests/test_lore/test_window_coverage_pg.py:39:89: E501 line too long (187 > 88 characters)
tests/test_lore/test_window_coverage_pg.py:48:89: E501 line too long (137 > 88 characters)
tests/test_lore/test_window_coverage_pg.py:57:89: E501 line too long (114 > 88 characters)
tests/test_lore/test_window_coverage_pg.py:84:89: E501 line too long (112 > 88 characters)
tests/test_lore/test_window_coverage_pg.py:103:89: E501 line too long (169 > 88 characters)
tests/test_lore/test_window_coverage_pg.py:198:89: E501 line too long (89 > 88 characters)

EXIT STATUS: 1
```

### Flake8 Main

Log: `resumed-flake8-main.log`.

```sh
/Users/pythagor/nexus/.venv/bin/python -m flake8 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/nexus/agents/lore/utils/turn_cycle.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/nexus/config/settings_models.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/tests/config/test_settings_models.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/tests/config/test_settings_parity.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/tests/test_lore/test_assembled_prompt_fingerprint.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/tests/test_lore/test_window_coverage_pg.py
```

```text
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/nexus/agents/lore/utils/turn_cycle.py:503:13: F401 'sqlalchemy.text' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/nexus/config/settings_models.py:79:89: E501 line too long (89 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/nexus/config/settings_models.py:126:89: E501 line too long (90 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/nexus/config/settings_models.py:141:89: E501 line too long (101 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/nexus/config/settings_models.py:149:89: E501 line too long (91 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/nexus/config/settings_models.py:2461:89: E501 line too long (93 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/nexus/config/settings_models.py:4397:89: E501 line too long (131 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/tests/test_lore/test_window_coverage_pg.py:29:89: E501 line too long (187 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/tests/test_lore/test_window_coverage_pg.py:38:89: E501 line too long (137 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/tests/test_lore/test_window_coverage_pg.py:47:89: E501 line too long (114 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/tests/test_lore/test_window_coverage_pg.py:74:89: E501 line too long (112 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/tests/test_lore/test_window_coverage_pg.py:93:89: E501 line too long (169 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/tests/test_lore/test_window_coverage_pg.py:188:89: E501 line too long (89 > 88 characters)

EXIT STATUS: 1
```

### Mypy Branch

Log: `rebased-mypy.log`.

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases nexus/agents/lore/utils/turn_cycle.py nexus/config/settings_models.py tests/config/test_settings_models.py tests/config/test_settings_parity.py tests/test_lore/test_assembled_prompt_fingerprint.py tests/test_lore/test_window_coverage_pg.py
```

```text
nexus/config/settings_models.py:130: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:130: note: Right operand is of type "int | None"
nexus/config/settings_models.py:131: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:131: error: Unsupported operand types for < ("int" and "None")  [operator]
nexus/config/settings_models.py:131: error: Unsupported left operand type for > ("None")  [operator]
nexus/config/settings_models.py:131: note: Both left and right operands are unions
nexus/config/settings_models.py:138: error: Unsupported operand types for + ("int" and "None")  [operator]
nexus/config/settings_models.py:138: note: Right operand is of type "int | None"
nexus/config/settings_models.py:138: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:4402: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:4402: note: Right operand is of type "int | None"
tests/config/test_settings_models.py:875: error: Item "None" of "RuntimeSettings | None" has no attribute "cli"  [union-attr]
nexus/agents/lore/utils/turn_cycle.py:230: note: By default the bodies of untyped functions are not checked, consider using --check-untyped-defs  [annotation-unchecked]
nexus/agents/lore/utils/turn_cycle.py:601: error: Argument 2 to "fetch_character_relationships" has incompatible type "list[Any | None]"; expected "list[int]"  [arg-type]
tests/test_lore/test_window_coverage_pg.py:181: error: "LogonUtility" has no attribute "_assembly_window_requests"  [attr-defined]
tests/test_lore/test_window_coverage_pg.py:193: error: "LogonUtility" has no attribute "record_rendered_coverage"  [attr-defined]
tests/test_lore/test_window_coverage_pg.py:194: error: "LogonUtility" has no attribute "record_rendered_coverage"  [attr-defined]
Found 12 errors in 4 files (checked 6 source files)

EXIT STATUS: 1
```

### Mypy Main

Log: `rebased-mypy-main.log`.

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases nexus/agents/lore/utils/turn_cycle.py nexus/config/settings_models.py tests/config/test_settings_models.py tests/config/test_settings_parity.py tests/test_lore/test_assembled_prompt_fingerprint.py tests/test_lore/test_window_coverage_pg.py --shadow-file nexus/agents/lore/utils/turn_cycle.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/nexus/agents/lore/utils/turn_cycle.py --shadow-file nexus/config/settings_models.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/nexus/config/settings_models.py --shadow-file tests/config/test_settings_models.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/tests/config/test_settings_models.py --shadow-file tests/config/test_settings_parity.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/tests/config/test_settings_parity.py --shadow-file tests/test_lore/test_assembled_prompt_fingerprint.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/tests/test_lore/test_assembled_prompt_fingerprint.py --shadow-file tests/test_lore/test_window_coverage_pg.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/origin-main/tests/test_lore/test_window_coverage_pg.py
```

```text
nexus/config/settings_models.py:130: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:130: note: Right operand is of type "int | None"
nexus/config/settings_models.py:131: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:131: error: Unsupported operand types for < ("int" and "None")  [operator]
nexus/config/settings_models.py:131: error: Unsupported left operand type for > ("None")  [operator]
nexus/config/settings_models.py:131: note: Both left and right operands are unions
nexus/config/settings_models.py:138: error: Unsupported operand types for + ("int" and "None")  [operator]
nexus/config/settings_models.py:138: note: Right operand is of type "int | None"
nexus/config/settings_models.py:138: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:4395: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:4395: note: Right operand is of type "int | None"
tests/config/test_settings_models.py:873: error: Item "None" of "RuntimeSettings | None" has no attribute "cli"  [union-attr]
nexus/agents/lore/utils/turn_cycle.py:230: note: By default the bodies of untyped functions are not checked, consider using --check-untyped-defs  [annotation-unchecked]
nexus/agents/lore/utils/turn_cycle.py:596: error: Argument 2 to "fetch_character_relationships" has incompatible type "list[Any | None]"; expected "list[int]"  [arg-type]
tests/test_lore/test_window_coverage_pg.py:171: error: "LogonUtility" has no attribute "_assembly_window_requests"  [attr-defined]
tests/test_lore/test_window_coverage_pg.py:183: error: "LogonUtility" has no attribute "record_rendered_coverage"  [attr-defined]
tests/test_lore/test_window_coverage_pg.py:184: error: "LogonUtility" has no attribute "record_rendered_coverage"  [attr-defined]
Found 12 errors in 4 files (checked 6 source files)

EXIT STATUS: 1
```

Diagnostic comparison output (paths and line offsets normalized, unchanged lines checked):

```text
flake8: 13 diagnostic lines match origin/main exactly modulo line shifts; all on unchanged lines; new diagnostics: 0
mypy: 17 diagnostic lines match origin/main exactly modulo line shifts; all on unchanged lines; new diagnostics: 0
EXIT STATUS: 0
```

## Commit Hook and Cleanup

The resumed source commit ran the normal hooks; its rebase preserved the patch.

### Resumed Source Commit Hook

Log: `resumed-commit.log`.

```sh
git -c core.fsmonitor=false commit -F /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/resumed-commit.txt
```

```text
Regenerate Orrery package catalog........................................Passed
Validate NEXUS config and model-ID drift.................................Passed
Require COMMENT ON for new migration objects.........(no files to check)Skipped
[claude/756-deep-query-count-setting 0a99a005] Verify deep-query breadth on the amended corpus (#756 S2, gpt-6-astra)
 2 files changed, 4 insertions(+), 2 deletions(-)

EXIT STATUS: 0
```

A read-only administrative connection to `postgres`, using `tests.pg_fixtures.connect`
and `conn.set_session(readonly=True)`, executed:

```sql
SELECT current_setting('transaction_read_only');
SELECT datname FROM pg_database
WHERE datname LIKE 'qa640_756_deep_query_%' ORDER BY datname;
```

```text
transaction_read_only: on
remaining 756-S2 disposable clones: []
EXIT STATUS: 0
```

No service belonging to the owner or another builder was started, stopped, or
reconfigured. Test fixtures owned their disposable databases. The order has no
gateway lane and no UI build.

## Coordinator Handoff

Refs #756. No open product question for this slice. Fixture defect #1083 remains
outside this PR; its old-stamp source issue is preserved in the accepted report.
Reinvestment and the separate owner questions stay deferred to their own orders.

Landing: **no migration number and no fleet application**. Product code and
`nexus.toml` change, so after pulling run **`nexus restart gateway`**. No client
bundle change, no UI rebuild, and no stored-baseline refresh. The coordinator
runs the whole-tree PostgreSQL gate at the final commit. Do not merge as part of
this implementation handoff.

## Accepted Stop-Report — 2026-10-01 (Before Amendment 1)

The following is the original report; its unrun gates and open question are historical.

<details>
<summary>Accepted Stop-Report From f844c0d4</summary>

# STOP-REPORT: 756-S2 Corpus Bootstrap Precondition

## Disposition

Implementation preserved locally; no PR, push, merge, or rebase. The frozen
proof cannot reach retrieval with the mandated corpus and fixture. Both new
parametrizations fail before LORE construction because the restored corpus lacks
`global_variables.gaia_model`. The fixture tries to write that column while
pinning TEST **before** it runs migrations. No fixture, migration, source database,
retrieval implementation, model loader, or result was changed to bypass this.

Starting commit: `5b977eabcba5f7aedf1a64a6ee20c021ab290911`.
Implementation commit: `d47524985b1bcb565a0ffc19de6c91133e49e191`. All code citations below were checked
at this implementation commit; this report is a subsequent documentation commit.
Branch: `claude/756-deep-query-count-setting`.
Worktree: `/Users/pythagor/nexus/.claude/worktrees/756-deep-query-count-setting`.

Read `_common_codex.md`, then `756-S2.md`, then the issue snapshot, and fetched
`gh issue view 756 --repo pythagorakase/nexus --comments`. No later comment changed
this slice's scope. Only 756-R6 was implemented; reinvestment remains outside it.

Import check (exit 0):

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/756-deep-query-count-setting/nexus/__init__.py
```

## Blocker Evidence

- `tests/test_lore/test_window_coverage_pg.py:228-232` names the required
  `ref_codex_bakeoff_2026_07` data source and `qa640_756_deep_query` disposable prefix.
- `tests/pg_fixtures.py:174-178` writes `StorySettings(skald_model="TEST", gaia_model=None)`.
- `tests/pg_fixtures.py:233-234` calls that pin writer before `migrate_database`.
- `nexus/config/story_model.py:80-90` turns the patch into an UPDATE including
  `gaia_model`; the exact failure is reproduced below for both k=3 and k=15.
- `migrations/117_story_settings.sql:1` adds the missing column. It was not applied
  by hand, to the source, or to any owner database.
- LORE construction at `tests/test_lore/test_window_coverage_pg.py:234` was not
  reached. Query selection at line 245 and the broad retrieval at line 256 were
  not reached. Query text, broad-query count, and pool counts for k=3 and k=15
  are therefore **unobserved**, not zero. Mutation proof is **not run**: it could
  only repeat the bootstrap failure, not prove the required assertion failure.
- Both parametrizations ran and failed; neither was skipped. No corpus timing
  or time-truth conclusion is drawn.

Exact exception:

```text
E       psycopg2.errors.UndefinedColumn: column "gaia_model" of relation "global_variables" does not exist
E       LINE 1: UPDATE global_variables SET "model" = 'TEST', "gaia_model" =...
E                                                             ^

nexus/config/story_model.py:88: UndefinedColumn
```

## Verified Implementation Citations

- At starting commit `5b977eab`, `turn_cycle.py:692` supplied literal `"k": 15`;
  the existing typed sibling reader was at lines 244-247. At `d4752498`,
  `nexus/agents/lore/utils/turn_cycle.py:249-252` reads the new typed field,
  line 687 resolves it, line 698 passes it, and line 709 calls real MEMNON.
- `nexus/config/settings_models.py:1253-1267` retains `extra="forbid"`, retains
  `max_deep_queries=5` with `ge=1`, and adds only `deep_query_k=15` with `ge=1`.
  `LORESettings.retrieval` still uses the default factory at line 1321.
- `nexus.toml:264-266` contains the one-line configuration addition. No other
  TOML value changed. Shipped reranker `top_k=30` remains at line 1143.
- `nexus/agents/memnon/memnon.py:1621-1629,1656-1664,1696,1721-1723`
  still forwards k to hybrid retrieval, truncates results to k, and applies the
  reranker's separate cap. MEMNON is unchanged.
- `nexus/agents/lore/utils/turn_cycle.py:658-667` still builds one raw-chunk
  query; line 725 deduplicates it. The separate default deduplication cap of 30
  remains at lines 133-149.
- `nexus/memory/baseline_compat.py:38-43,125-135` fingerprints only `[memory]`
  and `[lore.token_budget]`. This file is unchanged. New validation tests at
  `tests/config/test_settings_models.py:996-1049` prove the shipped/default 15,
  rejection of 0 and -1, misspelling rejection, and equal Pass-2 fingerprints
  for validated configurations with k=3 and k=15.
- `nexus/config/loader.py:378-384` copies the whole typed LORE section.
  `tests/config/test_settings_parity.py:272-277` owns the new leaf;
  its ownership gate at lines 846-854 passes in the focused suite.
- `tests/test_lore/test_assembled_prompt_fingerprint.py:125,308` pins and reads
  the new projection. The digest values at line 76 onward and the Pass-2 hash
  at lines 126-128 are unchanged; the assembled-prompt tests passed.
- `docs/settings_scopes.md:74` contains exactly the prescribed paragraph.
- The new corpus proof is at `tests/test_lore/test_window_coverage_pg.py:213-283`.
  It uses the real LORE/MEMNON paths, shipped model settings, slot routing to the
  clone, and TEST. Its count/identity assertions remain unproven due to bootstrap.

## Commands and Complete Tails

`PY=/Users/pythagor/nexus/.venv/bin/python`.
All commands ran from the worktree. Proof commands were launched by
`$PY <scratch>/run_gate.py <label> <command>` with a 570-second deadline and a
120-second no-output limit. Neither limit fired. The wrapper set
`PYTHONPATH=$PWD`, `TMPDIR=<scratch>`, and `PYTHONUNBUFFERED=1`; it saved the exact
argument lists, logs, and exit statuses under:

`/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2`

Formatting command (exit 0):

```sh
/Users/pythagor/nexus/.venv/bin/python -m black nexus/agents/lore/utils/turn_cycle.py nexus/config/settings_models.py tests/config/test_settings_models.py tests/config/test_settings_parity.py tests/test_lore/test_assembled_prompt_fingerprint.py tests/test_lore/test_window_coverage_pg.py
```

```text
reformatted tests/test_lore/test_window_coverage_pg.py
reformatted tests/config/test_settings_parity.py
reformatted tests/config/test_settings_models.py

All done! ✨ 🍰 ✨
3 files reformatted, 3 files left unchanged.
```

### Focused Offline

```sh
env -u NEXUS_RUN_POSTGRES -u NEXUS_RUN_LIVE_LLM /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/config tests/test_lore/test_assembled_prompt_fingerprint.py tests/test_lore/test_turn_cycle.py
```

```text
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
151 passed, 5 warnings in 8.20s

EXIT STATUS: 0
```

### PostgreSQL Proof

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 NEXUS_RUN_CORPUS=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_lore/test_window_coverage_pg.py tests/test_memnon_model_failures_pg.py tests/test_orrery/test_recall_disclosure_pg.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
```

```text
=================================== FAILURES ===================================
_______________ test_configured_k_bounds_the_deep_query_pool[3] ________________

tmp_path = PosixPath('/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/pytest-of-pythagor/pytest-1/test_configured_k_bounds_the_d0')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x16c05e2d0>
capsys = <_pytest.capture.CaptureFixture object at 0x176581290>, k = 3

    @pytest.mark.requires_corpus
    @pytest.mark.parametrize("k", [3, 15])
    def test_configured_k_bounds_the_deep_query_pool(
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        k: int,
    ) -> None:
        """Real corpus retrieval from narrative_chunks honors configured breadth."""
        config = tmp_path / "nexus.toml"
        config.write_text(
            Path("nexus.toml")
            .read_text()
            .replace("deep_query_k = 15", f"deep_query_k = {k}")
        )
>       with disposable_slot_database(
            "qa640_756_deep_query",
            source_db="ref_codex_bakeoff_2026_07",
            include_data=True,
        ) as dbname:

tests/test_lore/test_window_coverage_pg.py:228: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
../../../../.pyenv/versions/3.11.12/lib/python3.11/contextlib.py:137: in __enter__
    return next(self.gen)
tests/pg_fixtures.py:233: in disposable_slot_database
    pin_clone()
tests/pg_fixtures.py:177: in pin_clone
    write_story_settings(
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

cur = <cursor object at 0x1780cfb50; closed: -1>
patch = StorySettings(slot=None, dbname=None, skald_model='TEST', gaia_model=None, apex_context_window=None)

    def write_story_settings(cur: Any, patch: StorySettings) -> None:
        """Validate and persist explicit pins on the caller's transaction."""
        updates = patch.model_dump(exclude_unset=True)
        if not updates:
            raise ValueError("No story settings provided")
        settings = load_settings()
        for key in ("skald_model", "gaia_model"):
            if updates.get(key) is not None:
                settings.resolve_model_ref(updates[key])
        columns = {
            "skald_model": "model",
            "gaia_model": "gaia_model",
            "apex_context_window": "apex_context_window",
        }
        assignments = sql.SQL(", ").join(
            sql.SQL("{} = %s").format(sql.Identifier(columns[key])) for key in updates
        )
>       cur.execute(
            sql.SQL("UPDATE global_variables SET {} WHERE id = TRUE").format(assignments),
            tuple(updates.values()),
        )
E       psycopg2.errors.UndefinedColumn: column "gaia_model" of relation "global_variables" does not exist
E       LINE 1: UPDATE global_variables SET "model" = 'TEST', "gaia_model" =...
E                                                             ^

nexus/config/story_model.py:88: UndefinedColumn
_______________ test_configured_k_bounds_the_deep_query_pool[15] _______________

tmp_path = PosixPath('/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S2/pytest-of-pythagor/pytest-1/test_configured_k_bounds_the_d1')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x1780d9550>
capsys = <_pytest.capture.CaptureFixture object at 0x179841850>, k = 15

    @pytest.mark.requires_corpus
    @pytest.mark.parametrize("k", [3, 15])
    def test_configured_k_bounds_the_deep_query_pool(
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        k: int,
    ) -> None:
        """Real corpus retrieval from narrative_chunks honors configured breadth."""
        config = tmp_path / "nexus.toml"
        config.write_text(
            Path("nexus.toml")
            .read_text()
            .replace("deep_query_k = 15", f"deep_query_k = {k}")
        )
>       with disposable_slot_database(
            "qa640_756_deep_query",
            source_db="ref_codex_bakeoff_2026_07",
            include_data=True,
        ) as dbname:

tests/test_lore/test_window_coverage_pg.py:228: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
../../../../.pyenv/versions/3.11.12/lib/python3.11/contextlib.py:137: in __enter__
    return next(self.gen)
tests/pg_fixtures.py:233: in disposable_slot_database
    pin_clone()
tests/pg_fixtures.py:177: in pin_clone
    write_story_settings(
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

cur = <cursor object at 0x10c65aa70; closed: -1>
patch = StorySettings(slot=None, dbname=None, skald_model='TEST', gaia_model=None, apex_context_window=None)

    def write_story_settings(cur: Any, patch: StorySettings) -> None:
        """Validate and persist explicit pins on the caller's transaction."""
        updates = patch.model_dump(exclude_unset=True)
        if not updates:
            raise ValueError("No story settings provided")
        settings = load_settings()
        for key in ("skald_model", "gaia_model"):
            if updates.get(key) is not None:
                settings.resolve_model_ref(updates[key])
        columns = {
            "skald_model": "model",
            "gaia_model": "gaia_model",
            "apex_context_window": "apex_context_window",
        }
        assignments = sql.SQL(", ").join(
            sql.SQL("{} = %s").format(sql.Identifier(columns[key])) for key in updates
        )
>       cur.execute(
            sql.SQL("UPDATE global_variables SET {} WHERE id = TRUE").format(assignments),
            tuple(updates.values()),
        )
E       psycopg2.errors.UndefinedColumn: column "gaia_model" of relation "global_variables" does not exist
E       LINE 1: UPDATE global_variables SET "model" = 'TEST', "gaia_model" =...
E                                                             ^

nexus/config/story_model.py:88: UndefinedColumn
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

tests/test_lore/test_window_coverage_pg.py: 1 warning
tests/test_memnon_model_failures_pg.py: 10 warnings
  /Users/pythagor/nexus/.claude/worktrees/756-deep-query-count-setting/nexus/agents/memnon/utils/cross_encoder.py:173: UserWarning: 'has_mps' is deprecated, please use 'torch.backends.mps.is_built()'
    elif hasattr(torch, "has_mps") and torch.backends.mps.is_built():

tests/test_lore/test_window_coverage_pg.py::test_window_coverage_is_written_only_from_post_render_kept_chunks
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/transformers/convert_slow_tokenizer.py:559: UserWarning: The sentencepiece tokenizer that you are converting to a fast tokenizer uses the byte fallback option which is not implemented in the fast tokenizers. In practice this means that the fast version of the tokenizer can produce unknown tokens whereas the sentencepiece version would have converted these unknown tokens into a sequence of byte tokens matching the original piece of text.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 24 targets: postgres, qa640_756_deep_query_* x2, qa640_historical_coverage_* x3, qa640_window_coverage_*, qa885_transaction_writer_*, qa_model_failures_* x15, qa_wt724_recall_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_lore/test_window_coverage_pg.py::test_configured_k_bounds_the_deep_query_pool[3]
FAILED tests/test_lore/test_window_coverage_pg.py::test_configured_k_bounds_the_deep_query_pool[15]
2 failed, 181 passed, 19 warnings in 56.79s

EXIT STATUS: 1
```

### Hook Output

The implementation was committed with `git -c core.fsmonitor=false commit -F
<scratch>/implementation-commit.txt`. Hooks ran normally, including validate-config.

```text
Regenerate Orrery package catalog........................................Passed
Validate NEXUS config and model-ID drift.................................Passed
Require COMMENT ON for new migration objects.........(no files to check)Skipped
[claude/756-deep-query-count-setting d4752498] Add deep-query count setting and blocked corpus proof (#756 S2, gpt-6-astra)
 8 files changed, 165 insertions(+), 2 deletions(-)

EXIT STATUS: 0
```

### Cleanup Check

An enforced read-only connection to the administrative `postgres` database
(`conn.set_session(readonly=True)`) executed:

```sql
SELECT current_setting('transaction_read_only');
SELECT datname FROM pg_database
WHERE datname LIKE 'qa640_756_deep_query_%' ORDER BY datname;
```

```text
transaction_read_only: on
remaining 756-S2 disposable clones: []
```

Exit 0. Source access was only the fixture's pg_dump snapshot; tested product
paths did not connect to the source or owner databases. The audit's stated
coverage excludes subprocess drivers, as documented in `docs/agent_workflow.md`.
No gateway was launched. The provider-only and secret-store guards remained active.

## Unrun Gates and Static Diagnostics

Stopped on the frozen corpus prerequisite. The mutation/red-to-green proof,
first and second broad offline suites, reachability, Black --check, flake8,
mypy --explicit-package-bases and origin/main diagnostic comparison, and the
standalone validate_config_commit.py command were not run. Static cleanliness
is not claimed. The validate-config commit hook did run and passed, as above.
No pre-existing static debt was fixed. Rebase and push were not attempted because
this is a stop-report, not a completed proof set or merge-ready PR.

## Coordinator Handoff

Open question: provide a corpus compatible with the mandated pre-migration TEST
pin, or revise the frozen fixture/bootstrap instructions so the historical corpus
can be safely migrated while preserving TEST-only execution. No owner product
choice is required for this slice. Resume the required corpus/mutation and all
remaining gates after that prerequisite is resolved; rebase onto newest origin/main
before any push and preserve neighboring 785-S2/788-S7/756-S1 changes.

Landing notes if the slice is subsequently validated: no migration number or fleet
application; after pulling, run `nexus restart gateway`; no client bundle change,
UI rebuild, or baseline refresh. The coordinator owns the final whole-tree
PostgreSQL gate. No landing is requested from this stop-report.

Prepared by Codex — GPT-6 Astra (gpt-6-astra).

</details>

Prepared by Codex — GPT-6 Astra (gpt-6-astra).
