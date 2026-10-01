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
