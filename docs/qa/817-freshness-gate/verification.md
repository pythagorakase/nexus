# 817-S2a Verification: The Document Freshness Gate

Work order 817-S2a (issue #817, decision 817-Q1). Branch
`claude/817-freshness-gate`, cut from `origin/main` at
`41783c1dfcb16ff94e31e26bf2723b597b97803b`. All commands ran from the worktree
root with the shared interpreter (`$PY` = `/Users/pythagor/nexus/.venv/bin/python`)
and with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset. No
database, gateway or paid call was used.

## The Red Run (Item 5)

Taken at commit `abd2d068` (items 1-4, 7 and 9 committed; items 6 and 8 not yet
made), before `AGENTS.md` and `docs/decisions/README.md` were re-stamped.

```
$ $PY -m pytest -q tests/test_doc_front_matter.py::test_declared_sources_carry_a_fresh_verified_commit
F                                                                        [100%]
=================================== FAILURES ===================================
_____________ test_declared_sources_carry_a_fresh_verified_commit ______________
    def test_declared_sources_carry_a_fresh_verified_commit() -> None:
        """This branch re-stamps every canonical document whose sources it changes."""
>       assert freshness_errors(ROOT) == []
E       AssertionError: assert ['AGENTS.md: ...ified_commit'] == []
E
E         Left contains 2 more items, first extra item: 'AGENTS.md: docs/agent_workflow.md, docs/turn_flow_sequence.md, tests/test_doc_front_matter.py changed since the merge base 41783c1dfcb1 without a re-stamped verified_commit'
E
E         Full diff:
E         - []
E         + [
E         +     'AGENTS.md: docs/agent_workflow.md, docs/turn_flow_sequence.md, '...
E
E         ...Full output truncated (5 lines hidden), use '-vv' to show
tests/test_doc_front_matter.py:538: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_doc_front_matter.py::test_declared_sources_carry_a_fresh_verified_commit
======================== 1 failed, 5 warnings in 0.72s =========================
```

The `-q` assertion diff above shows only the first error. The same test under
`-vv`, at the same commit, shows both. It ran in a temporary detached worktree
of `abd2d068` under the session scratchpad (`git worktree add --detach
<scratchpad>/817-S2a/red abd2d068`, removed afterwards with `git worktree
remove --force`), so the working tree held exactly that commit; `origin/main`
was `41783c1d` and the merge base `41783c1dfcb1`:

```
$ cd <scratchpad>/817-S2a/red && $PY -m pytest -vv tests/test_doc_front_matter.py::test_declared_sources_carry_a_fresh_verified_commit
=================================== FAILURES ===================================
_____________ test_declared_sources_carry_a_fresh_verified_commit ______________

    def test_declared_sources_carry_a_fresh_verified_commit() -> None:
        """This branch re-stamps every canonical document whose sources it changes."""
>       assert freshness_errors(ROOT) == []
E       AssertionError: assert ['AGENTS.md: docs/agent_workflow.md, docs/turn_flow_sequence.md, tests/test_doc_front_matter.py changed since the merge base 41783c1dfcb1 without a re-stamped verified_commit', 'docs/decisions/README.md: tests/test_doc_front_matter.py changed since the merge base 41783c1dfcb1 without a re-stamped verified_commit'] == []
E
E         Left contains 2 more items, first extra item: 'AGENTS.md: docs/agent_workflow.md, docs/turn_flow_sequence.md, tests/test_doc_front_matter.py changed since the merge base 41783c1dfcb1 without a re-stamped verified_commit'
E
E         Full diff:
E         - []
E         + [
E         +     'AGENTS.md: docs/agent_workflow.md, docs/turn_flow_sequence.md, '
E         +     'tests/test_doc_front_matter.py changed since the merge base 41783c1dfcb1 '
E         +     'without a re-stamped verified_commit',
E         +     'docs/decisions/README.md: tests/test_doc_front_matter.py changed since '
E         +     'the merge base 41783c1dfcb1 without a re-stamped verified_commit',
E         + ]

tests/test_doc_front_matter.py:538: AssertionError
=============================== warnings summary ===============================
tests/test_doc_front_matter.py::test_declared_sources_carry_a_fresh_verified_commit
tests/test_doc_front_matter.py::test_declared_sources_carry_a_fresh_verified_commit
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_doc_front_matter.py::test_declared_sources_carry_a_fresh_verified_commit
tests/test_doc_front_matter.py::test_declared_sources_carry_a_fresh_verified_commit
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_doc_front_matter.py::test_declared_sources_carry_a_fresh_verified_commit
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_doc_front_matter.py::test_declared_sources_carry_a_fresh_verified_commit - AssertionError: assert ['AGENTS.md: docs/agent_workflow.md, docs/turn_flow_sequence.md, tests/test_doc_front_matter.py changed since the merge base 41783c1dfcb1 without a re-stamped verified_commit', 'docs/decisions/README.md: tests/test_doc_front_matter.py changed since the merge base 41783c1dfcb1 without a re-stamped verified_commit'] == []

  Left contains 2 more items, first extra item: 'AGENTS.md: docs/agent_workflow.md, docs/turn_flow_sequence.md, tests/test_doc_front_matter.py changed since the merge base 41783c1dfcb1 without a re-stamped verified_commit'

  Full diff:
  - []
  + [
  +     'AGENTS.md: docs/agent_workflow.md, docs/turn_flow_sequence.md, '
  +     'tests/test_doc_front_matter.py changed since the merge base 41783c1dfcb1 '
  +     'without a re-stamped verified_commit',
  +     'docs/decisions/README.md: tests/test_doc_front_matter.py changed since '
  +     'the merge base 41783c1dfcb1 without a re-stamped verified_commit',
  + ]
======================== 1 failed, 5 warnings in 1.50s =========================
```

The list is exactly the one item 5 requires, with `<mb12>` = `41783c1dfcb1`.

## Mutation Checks on the New Tests

Each mutation was applied to a scratch copy of `tests/test_doc_front_matter.py`
and the synthetic-repository tests were run against it. Every mutation fails at
least one test.

| Mutation | Test that fails |
|---|---|
| Diff `merge_base..HEAD` (uncommitted edits ignored) | `test_source_change_without_restamp_fails` |
| Drop `git ls-files --others` (untracked files ignored) | `test_source_change_without_restamp_fails` |
| Read only the current `sources` | `test_dropping_a_source_does_not_evade` |
| Read only the current `status` | `test_dropping_a_source_does_not_evade` |
| Skip the checks on a moved stamp | `test_restamp_must_name_history_on_main` |
| Compare stamps as strings only | `test_document_edit_alone_is_not_a_restamp` |
| Count a document edit as a re-stamp | `test_document_edit_alone_is_not_a_restamp` |
| Walk documents through `repository_paths` (inherited `GIT_*`) | `test_inherited_git_environment_is_ignored` |
| Drop the on-disk directory check in `_path_error` | `test_unlisted_directory_source_is_named_a_directory` |

The last two rows were checked on the branch file itself rather than a scratch
copy: the walk row by running the new test before the walk fix (tail under
"After the Review Fixes"), the directory row by deleting the
`(root / value).is_dir()` clause, running the test (`1 failed`: "source file
'build' does not exist"), and restoring the file.

Each `test_missing_history_fails_loudly` case raises its own message (pinned
with `match=`): "is not a git checkout", "has no git checkout of its own",
"git fetch --unshallow", "git fetch origin main", "no merge base".

## AGENTS.md, Sentence by Sentence (Item 6)

Line numbers refer to `AGENTS.md` after this branch (the body moved from
`:20-41` to `:41-62` because the front matter grew). "Locator" and
"convention" rows have no source by the order's rule. Every claim is true at
`41783c1d`; no sentence was corrected, added or dropped, so the source list is
the order's list unchanged.

| Line | Claim | Evidence | Verdict |
|---|---|---|---|
| 44 | Core package lives in `nexus/`. | Locator. | True |
| 44 | `lore` orchestrates each turn (`lore.py`, `utils/turn_cycle.py`). | `nexus/agents/lore/lore.py:198` builds `TurnCycleManager`; `lore.py:329` `process_turn`; `nexus/agents/lore/utils/turn_cycle.py:219` `TurnCycleManager` with phase methods at `:279`, `:350`, `:440`, `:638`, `:754`. | True |
| 44 | `lore` hosts LOGON (`logon_utility.py`), the provider client for the Skald writer and Gaia seats. | `nexus/agents/lore/logon_utility.py:2-4` (API communication handler for providers), `:387` `LogonUtility`, `:913-933` composes the `writer` prompt, then the `gaia` prompt for a two-pass turn; `nexus/agents/lore/seat_blocks.py:8` `ContextSeat = Literal["writer", "gaia", ...]`. | True |
| 44 | `logon` holds the storyteller wire schemas and validators. | `nexus/agents/logon/skald_wire.py:1`, `apex_schema.py:2`, `gaia_registry_schema.py:1`, `apex_enums.py:2` (schemas and their enums); `orrery_tag_validation.py:1`, `place_reference_validation.py:1` (validators). | True |
| 44 | `memnon` handles retrieval. | `nexus/agents/memnon/memnon.py:2-8`, `:1580` `query_memory`. | True |
| 44 | `orrery` is the deterministic off-screen world engine. | `nexus/agents/orrery/worker.py:1` ("deterministic off-screen record worker"), `:40`, `:183`, `:242`. | True |
| 44 | GAIA, PSYCHE and NEMESIS modules were never built; their `docs/blueprint_*.md` files are historical. | `nexus/agents/` holds only `logon`, `lore`, `memnon`, `orrery`; `docs/blueprint_gaia.md:2`, `docs/blueprint_nemesis.md:2`, `docs/blueprint_psyche.md:2` read `status: historical`. | True |
| 44 | Gaia now names the second storyteller seat. | `nexus/agents/lore/logon_utility.py:508` ("the writer and gaia seats of a two-pass turn"), `:913-933` (writer prompt first, Gaia prompt second); `seat_blocks.py:8`. | True |
| 44 | Pass 1/Pass 2 memory lives in `nexus/memory/` (`manager.py`, `context_state.py`, `divergence.py`, `entity_detector.py`). | `nexus/memory/manager.py:378` ("Coordinate Pass 1 baseline storage and Pass 2 incremental retrieval"), `:775`, `:956`; `nexus/memory/context_state.py:92` `Pass2BaselineV2`, `:273`; `nexus/memory/divergence.py:10`; `nexus/memory/entity_detector.py:44`. | True |
| 44 | The FastAPI gateway and its turn routes live in `nexus/api/` (`narrative.py`). | `nexus/api/narrative.py:132` `app = FastAPI(...)`, `:834` `/api/narrative/continue`, `:1062` `/api/narrative/retry`. | True |
| 44 | Deferred work runs under `nexus/jobs/`. | `nexus/jobs/scheduler.py:1` ("One durable, preemptible recovery owner for each slot database"), `:61` `SlotScheduler`. | True |
| 44 | Model prompts are Markdown files under `prompts/`, loaded only through the catalog in `nexus/prompts/registry.py`. | `find prompts -type f ! -name '*.md'` finds nothing (147 `.md` files); `nexus/prompts/registry.py:928` `_PROMPTS_ROOT`, `:951` `load`; `tests/test_prompt_lint.py:495` `test_only_registry_constructs_prompt_paths`. | True |
| 44 | The IRIS client lives in `ui/`, tooling scripts in `scripts/`, SQL migrations in `migrations/`, reference material in `docs/`. | Locator. | True |
| 44 | `docs/turn_flow_sequence.md` traces the turn cycle through the code. | `docs/turn_flow_sequence.md:37` "# The Turn Cycle"; its front matter lists the code files it traces. | True |
| 44 | Tests live under `tests/`, grouped by subsystem (`tests/test_lore/`, `tests/test_api/`, `tests/test_orrery/`, and others). | Locator. | True |
| 44 | Runtime settings live in `nexus.toml`. | `CLAUDE.md:18` ("`nexus.toml` contains read-only runtime defaults and developer tunables"); `nexus.toml` exists. | True |
| 47 | `CLAUDE.md` is the canonical command reference, including the PostgreSQL test gate, migrations and pre-commit hooks. | `CLAUDE.md:9` (full gate), `:20-28` (pre-commit hooks), `:62-80` (migrations). | True |
| 47 | Bootstrap with `poetry install`. | Command convention. | True |
| 47 | Run the suite with `poetry run pytest`; narrow scope with `poetry run pytest tests/test_lore/test_memory_manager.py::test_explicit_base_budget_mode_configures_phase2`. | `tests/test_lore/test_memory_manager.py:186` defines that test. | True |
| 47 | Format via Black, type-check with mypy, lint with flake8. | Command convention; `pyproject.toml:40`, `:42`, `:44` list `black`, `mypy` and `flake8` as dev dependencies. | True |
| 50 | "Adopt Black (88 columns) and flake8." | Style convention; `pyproject.toml:40`, `:44` (dev dependencies); `.flake8:2` `max-line-length = 88`; `CLAUDE.md:36`. | True |
| 50 | "Group imports stdlib/third-party/local and alphabetize." | Style convention (`CLAUDE.md:37`). | True |
| 50 | "Use PascalCase for classes and snake_case elsewhere." | Style convention (`CLAUDE.md:39`). | True |
| 50 | "Public functions and classes need docstrings and explicit type hints." | Style convention (`CLAUDE.md:38`, `:42`). | True |
| 50 | Load configurable values from `nexus.toml` instead of literals. | `CLAUDE.md:18`; `nexus.toml`. | True |
| 50 | When shaping LLM responses, follow the structured-output practices in `CLAUDE.md` and prefer Pydantic models. | `CLAUDE.md:237-239` ("OpenAI API Best Practices", Pydantic patterns via the `openai-structured-output` skill). | True |
| 50 | Fail fast; do not add quiet fallbacks. | Style convention. | True |
| 53 | Pytest drives coverage; mirror test filenames to their targets (e.g., `test_chunk_operations.py`). | Convention; the example exists: `tests/test_lore/test_chunk_operations.py` mirrors `nexus/agents/lore/utils/chunk_operations.py`. | True |
| 53 | Reuse fixtures from `tests/test_lore/conftest.py`, and `tests/pg_fixtures.py` for PostgreSQL. | `tests/test_lore/conftest.py:27-36` (fixtures); `tests/pg_fixtures.py:1` ("Shared PostgreSQL helpers for disposable integration-test databases"). | True |
| 53 | Cover Pass 1 baseline assembly and Pass 2 divergence detection in `tests/test_lore/test_memory_manager.py`; mark async turn checks with `pytest.mark.asyncio`. | `tests/test_lore/test_memory_manager.py:198` `test_pass1_baseline_tracks_chunks_and_budget`, `:309` `test_pass2_divergence_triggers_incremental_retrieval`; `pytest.ini:4` configures pytest-asyncio. | True |
| 53 | "Tests that need PostgreSQL carry the `requires_postgres` marker and run only with `NEXUS_RUN_POSTGRES=1`; document the tables they depend on and keep mutations reversible." | `pytest.ini:6` declares the marker; `tests/conftest.py:214-218` skips it unless `NEXUS_RUN_POSTGRES` is set, `:85-94` fails an unmarked connection; the second clause is a convention. | True |
| 53 | "Prefer real code paths and real API calls over mocks." | Convention (`CLAUDE.md:186`). | True |
| 56 | "Write concise, imperative commits (`Add divergence guard`)." | Convention. | True |
| 56 | "Stage and commit your work proactively; don't leave useful changes sitting unstaged when you pause or hand off." | Convention. | True |
| 56 | "Pair code with its tests." | Convention. | True |
| 56 | Follow the autonomous branch/PR/review workflow in `docs/agent_workflow.md`. | `docs/agent_workflow.md:1-8`. | True |
| 56 | "PRs should summarize impact, call out touched agents or memory modules, list manual verification commands, and note any updates to `nexus.toml` or database schema." | Convention. | True |
| 56 | "Screenshots are only needed when changing rendered output." | Convention. | True |
| 59 | Fetch API credentials via `nexus.util.secret_manager.get_secret(<account>)`; write them only through `set_secret`. | `nexus/util/secret_manager.py:357` `get_secret`, `:392` `set_secret`. | True |
| 59 | The platform secret store is canonical (macOS Keychain service `nexus-api`, or `keyring` elsewhere), and the settings-pane API KEYS card is the supported write and rotation path. | `nexus/util/secret_manager.py:5-6`, `:13-14`, `:58` `SERVICE_NAME = "nexus-api"`; `ui/client/src/components/nexus/SettingsPane.tsx:458` (API KEYS card); `nexus/api/secrets_endpoints.py:284` (PUT). | True |
| 59 | 1Password is not a runtime dependency; `scripts/sync_secrets.py` is only a deprecated personal migration shim. | `scripts/sync_secrets.py:1-5`. | True |
| 59 | Each save slot is its own PostgreSQL database (`save_01` through `save_05`, selected by `NEXUS_SLOT`) with pgvector and PostGIS. | `nexus/api/slot_utils.py:5-11`, `:21`, `:51-59`; `migrations/014_add_2560d_4096d_embeddings.sql:8` (`vector`), `migrations/035_orrery_osm_route_graph.py:19` (`postgis`). | True |
| 59 | `NEXUS_template` is the canonical schema reference, and the old `NEXUS` database is deprecated. | `CLAUDE.md:56`. | True |
| 59 | Align local LLM endpoints with the models referenced in `nexus.toml`. | `nexus.toml:56-62` (`[global.model.api_models.local]` and its models). | True |
| 62 | When work needs extra permissions, try the action so the approval prompt can surface. | Convention. | True |

`verified_commit` moves from `ed9531e3` to `41783c1dfcb16ff94e31e26bf2723b597b97803b`
(`git merge-base origin/main HEAD`).

## How Often Each Source List Fires

The old list (13 entries, five directories) and the new list (34 files) against
the 73 first-parent commits on `main` from `ed9531e3` to `41783c1d`:

```
$ git rev-list --first-parent --count ed9531e3..41783c1d
73
$ git log --first-parent --format=%H ed9531e3..41783c1d -- CLAUDE.md nexus/agents/ nexus/memory/ nexus/api/narrative.py nexus/jobs/ nexus/prompts/registry.py prompts/ nexus/api/slot_utils.py nexus/util/secret_manager.py tests/ pytest.ini docs/agent_workflow.md docs/turn_flow_sequence.md | wc -l
66
$ git log --first-parent --format=%H ed9531e3..41783c1d -- $(git show HEAD:AGENTS.md | sed -n '/^sources:/,/^verified_commit/p' | grep '^  - ' | sed 's/^  - //') | wc -l
42
```

## Gate Tails

All at `47280681` (items 1-9 committed; this file untracked at the time, which
the freshness check reads and accepts), `origin/main` still at `41783c1d`.

```
$ $PY -m pytest -q tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
40 passed, 5 warnings in 5.49s

$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_doc_front_matter.py tests/test_owner_target_guard.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
120 passed in 7.87s

$ $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2636 passed, 419 skipped, 8 warnings in 445.25s (0:07:25)

$ $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1816 passed, 742 skipped, 7 warnings in 39.77s

$ $PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 11.83s

$ $PY -m black --check tests/test_doc_front_matter.py
1 file would be left unchanged.
$ $PY -m flake8 tests/test_doc_front_matter.py
(no output)
$ $PY -m mypy tests/test_doc_front_matter.py
Success: no issues found in 1 source file
```

The skips in the two offline runs are the PostgreSQL-marked tests, which run
only with `NEXUS_RUN_POSTGRES=1` (outside this order's named files).

## After the Review Fixes

Commit `08546633` applies the review findings: the freshness walk lists files
through `_history_paths` (the scrubbed `_history_git`, so an inherited
`GIT_DIR` or `GIT_WORK_TREE` no longer chooses the documents), `_path_error`
names an on-disk directory that git does not list as a directory, and
`_history_git` sets `GIT_OPTIONAL_LOCKS=0`. No claim of `AGENTS.md` changed, so
no stamp moved; the table rows above were split to one sentence each.

Before the walk fix (the directory check and both new tests in place, the walk
still on `repository_paths`), the new `GIT_DIR` test failed; excerpt of its tail:

```
$ $PY -m pytest -q tests/test_doc_front_matter.py -k "inherited_git or unlisted_directory"
>       assert freshness_errors(root, base_ref="main") == expected
E       AssertionError: assert [] == ['docs/a.md: ...ified_commit']
E         Right contains one more item: 'docs/a.md: src/app.py changed since the merge base 77c4bd912f30 without a re-stamped verified_commit'
FAILED tests/test_doc_front_matter.py::test_inherited_git_environment_is_ignored
1 failed, 1 passed, 40 deselected, 5 warnings in 0.61s
```

Tails at `08546633`, `origin/main` still at `41783c1d`:

```
$ $PY -m pytest -q tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
42 passed, 5 warnings in 6.84s

$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_doc_front_matter.py tests/test_owner_target_guard.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
122 passed in 9.41s

$ $PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 10.42s

$ $PY -m black --check tests/test_doc_front_matter.py
All done! ✨ 🍰 ✨
1 file would be left unchanged.
$ $PY -m flake8 tests/test_doc_front_matter.py
(no output)
$ $PY -m mypy tests/test_doc_front_matter.py
Success: no issues found in 1 source file
```

## After the Second Review Fix

Commit `74c9082c` removes `GIT_OPTIONAL_LOCKS=0` (and its comment) from
`_history_git`, so every git call of the check runs with `os.environ` minus every
`GIT_*` variable, as item 2 requires. No claim of `AGENTS.md` changed, so no
stamp moved.

Tails at `74c9082c`, `origin/main` at `e528cc08`, merge base still `41783c1d`:

```
$ $PY -m pytest -q tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
42 passed, 5 warnings in 7.07s

$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_doc_front_matter.py tests/test_owner_target_guard.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
122 passed in 8.54s

$ $PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 10.03s

$ $PY -m black tests/test_doc_front_matter.py
All done! ✨ 🍰 ✨
1 file left unchanged.
$ $PY -m flake8 tests/test_doc_front_matter.py
(no output)
$ $PY -m mypy tests/test_doc_front_matter.py
Success: no issues found in 1 source file
```
