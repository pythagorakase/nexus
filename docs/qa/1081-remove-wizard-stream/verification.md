# Verification: Remove the Dead Wizard Streaming Endpoint (#1081)

Branch `claude/1081-remove-wizard-stream`, cut from `origin/main` at `364fef4b`
(still the merge base when pushed). No migration, no paid call, no gateway lane,
no write to any `save_NN` or `NEXUS_template`.

## Why the Endpoint Was Dead

- `nexus/api/wizard_chat.py:858` (pre-change) declared `@router.post("/chat/stream")`.
- `nexus/api/wizard_chat.py:1071` iterated `async for streamed_result in agent.run_stream(...)`.
  In Pydantic AI 1.30.1, `Agent.run_stream` is an `@asynccontextmanager`, so the
  loop raised `TypeError` before any model call.
- `nexus/api/wizard_chat.py:1257` returned `StreamingResponse(event_stream(), media_type="application/x-ndjson")`.
- `rg -n "chat/stream" ui/client/src` finds nothing (exit 1): IRIS only calls
  `POST /api/story/new/chat`.

## Deleted Spans (Pre-Change Line Numbers at `364fef4b`)

| File | Lines | What |
| --- | --- | --- |
| `nexus/api/wizard_chat.py` | 858-1259 | `new_story_chat_stream_endpoint` (decorator through `return StreamingResponse(...)` and its two trailing blank lines), including the nested `wizard_events` generator and the `event_stream` NDJSON terminal-record wrapper |
| `nexus/api/wizard_chat.py` | 12 | `import json` (used only by the NDJSON records) |
| `nexus/api/wizard_chat.py` | 18 | `from fastapi.responses import StreamingResponse` |
| `nexus/api/wizard_chat.py` | 30 | `get_wizard_streaming_enabled` import |
| `nexus/api/wizard_chat.py` | 50 | `WizardConversationMoveError` import (only the stream handler caught it; the non-streaming handler lets it reach its generic 500 arm, unchanged; the class itself stays in `nexus/api/new_story_flow.py`) |
| `nexus/api/wizard_chat.py` | 63 | `WizardResponse` import (only the stream handler's `isinstance` checks used it) |
| `nexus/api/config_utils.py` | 40-43 | `get_wizard_streaming_enabled()` (its only caller was the stream handler) |
| `nexus/config/settings_models.py` | 3872-3874 | `WizardSettings.enable_streaming` (gated only the stream handler) |
| `nexus/config/loader.py` | 347 | legacy `settings.json` mapping of `enable_streaming` (the model forbids extra keys) |
| `nexus.toml` | 188 | `[wizard] enable_streaming = true` |
| `nexus/api/route_capabilities.py` | 192 | `("POST", "/api/story/new/chat/stream"): _WIZARD_TURN` |
| `config/exception_disposition_baseline.json` | 146-147 | the two `new_story_chat_stream_endpoint.event_stream` entries the lint reported stale |

Because `nexus.toml` is a declared source of `AGENTS.md` and
`docs/turn_flow_sequence.md`, both were re-read (neither mentions
`enable_streaming` or the stream route) and their `verified_commit` moved from
`41783c1d` to the merge base `364fef4b10ae0e7e0b63fc8e86cf292cca4087e4`.

## Shared Helpers Kept, with Their Remaining Callers

Line numbers are post-change `nexus/api/wizard_chat.py`; the non-streaming
`new_story_chat_endpoint` spans lines 382-850, `_handle_accept_fate_traits`
lines 242-348, and `_artifact_response` lines 358-379. "Other files" counts
files under `nexus`, `tests` and `scripts` besides `wizard_chat.py` that
name the symbol (`rg -l`).

| Helper | Remaining uses in `wizard_chat.py` | Other files |
| --- | --- | --- |
| `_reconcile_introduction` | 427 | 1 |
| `_is_introduction` | 434 | 0 |
| `_hydrate_character_context` | 530 | 1 |
| `resolve_wizard_model` | 180,555 | 2 |
| `wizard_model_lock_candidate` | 557 | 1 |
| `switch_wizard_model` | 581 | 2 |
| `_handle_accept_fate_traits` | 666 | 1 |
| `_accept_fate_prompt` | 686 | 0 |
| `_artifact_response` | 344,680,806 | 3 |
| `_record_set_design` | 744,781 | 1 |
| `_record_text_reply` | 826 | 0 |
| `get_wizard_history_limit` | 552 | 1 |
| `get_wizard_max_tokens` | 628 | 5 |
| `build_message_history` | 626 | 1 |
| `build_pydantic_ai_model_with_provider` | 627 | 7 |
| `record_pydantic_ai_result` | 314,638,696 | 7 |
| `write_wizard_choices` | 224,376,649 | 8 |
| `read_cache` | 139,298,355,361,415,465,878,910 | 21 |
| `DeferredToolRequests` | 329,809 | 7 |
| `generate_set_design` | 773 | 3 |
| `SettingCard` | 720 | 18 |
| `StorySeed` | 721 | 11 |
| `load_settings` | 725 | 190 |
| `query_wizard_cache` | 730,732 | 4 |
| `get_wizard_agent` | 306,688 | 10 |
| `wizard_debug_agent` | 631 | 3 |
| `WizardContext` | 243,613 | 8 |
| `ConversationsClient` | 180,204,252,558,589 | 15 |
| `frontmatter` | 591 | 4 |
| `WizardStateConflict` | 178,275,845,864 | 9 |
| `WizardConversationMoveError` | none | 1 |

Every helper the stream handler shared still has a caller in the
non-streaming endpoint; `WizardConversationMoveError` remains raised by
`switch_wizard_model` in `nexus/api/new_story_flow.py`.

## Tests

- `tests/test_api/test_wizard_stream_conflicts.py` targeted only the stream
  endpoint and is deleted. Its proof (a generated artifact that meets a changed
  session, a changed artifact, or a change seen under the write lock ends in a
  409 and never writes stale choices) is ported to the non-streaming endpoint as
  `tests/test_api/test_wizard_chat_conflicts.py`, which now also pins the exact
  409 detail for each variant (git records the pair as a rename).
- `tests/test_api/test_wizard_model_switch.py`: dropped the `streaming`
  parametrization from five tests, the `run_stream` fake and its `Turn` class,
  the NDJSON branch of `returned_thread_id` (now `response.json()["thread_id"]`)
  and the streaming-flag patch.
- `tests/test_api/test_wizard_confirmation.py`: dropped the `run_stream` fake,
  the streaming-flag patch, the stream endpoint from two endpoint loops and
  from two parametrizations, and the now-unused `json` import.
- `tests/test_api/test_wizard_resume.py`: dropped the `streaming`
  parametrization, the `run_stream` fake and the streaming-flag patch.
- `tests/test_api/test_slot_mutation_guard.py`: dropped the stream path from
  `BODY_MUTATIONS`; the non-streaming chat path stays.
- Baselines made stale by this deletion, updated entry by entry, rules intact:
  - `tests/test_prompt_lint.py` `PROSE_ALLOWLIST`: removed the one entry for the
    stream-only 409 message "Use the non-streaming wizard route to confirm or
    revise this artifact." (`test_allowlist_is_exact_and_has_no_stale_entries`
    failed on it).
  - `tests/test_api/test_set_designer_failure.py`
    `test_neither_provider_branch_swallows_set_design_errors`: the AST walk
    covers the one remaining endpoint; expected call counts move from
    `query_wizard_cache` 2, `generate_set_design` 2, `_record_set_design` 4 to
    1, 1, 2. The module docstring's "streaming live proof is deferred to #1081"
    sentence is removed. Review fix `1415c23e`: the check binds
    `new_story_chat_endpoint` directly instead of looping over a one-item tuple,
    and the inner-Try assertion is reduced to `ancestor is outer_boundary` (its
    endpoint-name half was always true); counts and rule are unchanged.

- `tests/test_api/test_route_capabilities.py`: added
  `test_retired_wizard_stream_route_is_not_served` beside the #807 precedent
  (`test_retired_chunk_state_route_is_not_served`). It posts an empty JSON
  body (`{}`, since review fix `1415c23e`; it first posted a slot-4 body) to
  `/api/story/new/chat/stream` and asserts 405, and asserts `("POST", "/api/story/new/chat/stream")` is absent from the
  gateway's route keys and from `ROUTE_CAPABILITIES`. The status is 405, not
  404: the only route that still matches the path is the GET shell catch-all
  (`static_ui.py:107` `/{full_path:path}` when the UI build is missing; the
  `SpaStaticFiles` mount at `/` when it exists, which also answers 405 to
  POST), so Starlette reports a method mismatch. Restoring the endpoint makes
  this test fail (red run below) with a 422 from request validation, which runs
  before the handler body, so the red case never opens a slot database.

## Remaining-Reference Grep

Rerun at `1415c23e`. The only hits are the four lines of the intentional removal
pin, which assert the route is absent; with that one test file excluded, the
same pattern finds nothing, so no live code, configuration, documentation or
other test still references the route. (The first version of this section,
recorded before the pin existed, read "no output".)

```
$ rg -n "chat/stream|chat_stream|new_story_chat_stream_endpoint|x-ndjson|run_stream|get_wizard_streaming_enabled|enable_streaming|non-streaming wizard route" -g '!temp/**' -g '!docs/qa/**' .
./tests/test_api/test_route_capabilities.py:436:    Its handler iterated ``agent.run_stream(...)``, an async context manager,
./tests/test_api/test_route_capabilities.py:442:    response = TestClient(narrative.app).post("/api/story/new/chat/stream", json={})
./tests/test_api/test_route_capabilities.py:444:    assert ("POST", "/api/story/new/chat/stream") not in _keys(narrative.app)
./tests/test_api/test_route_capabilities.py:445:    assert ("POST", "/api/story/new/chat/stream") not in ROUTE_CAPABILITIES
$ rg -n "chat/stream|chat_stream|new_story_chat_stream_endpoint|x-ndjson|run_stream|get_wizard_streaming_enabled|enable_streaming|non-streaming wizard route" -g '!temp/**' -g '!docs/qa/**' -g '!tests/test_api/test_route_capabilities.py' .
(no output; exit 1)
$ rg -n "chat/stream" ui/client/src
(no output; exit 1)
```

## Proof Tails

All runs from the worktree root with `PYTHONPATH=$PWD` and the shared
interpreter, with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset.

Ordered PostgreSQL proof (`tests/test_api/test_wizard_chat*.py` expands to
`test_wizard_chat_conflicts.py` and `test_wizard_chat_validation.py`):

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_wizard_model_switch.py tests/test_api/test_wizard_confirmation.py tests/test_api/test_wizard_resume.py tests/test_api/test_slot_mutation_guard.py tests/test_api/test_route_capabilities.py tests/test_reachability.py tests/test_api/test_wizard_chat*.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 6 targets: postgres, qa640_offline_gate_* x4, test_slot_guard_22ede8e6cd2e46e2b92c163451f728c9
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
235 passed, 7 warnings in 22.41s
```

Changed-baseline files under PostgreSQL:

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_set_designer_failure.py tests/test_prompt_lint.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 5 targets: postgres, qa640_840s3a_slot_* x2, qa640_840s3a_source_* x2
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
67 passed, 7 warnings in 29.74s
```

Offline suites, split by directory:

```
$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_api
secret-store guard: active; nexus-api: denied; disposable keychain: denied
627 passed, 262 skipped, 7 warnings in 34.60s
$ PYTHONPATH=$PWD $PY -m pytest -q tests/config tests/proofs tests/test_config tests/test_ir_eval_v2 tests/test_lore tests/test_memnon tests/test_runtime tests/test_scripts tests/test_util
secret-store guard: active; nexus-api: denied; disposable keychain: denied
958 passed, 81 skipped, 7 warnings in 132.09s (0:02:12)
$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1210 passed, 1107 skipped, 7 warnings in 12.77s
$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_*.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1985 passed, 476 skipped, 8 warnings in 387.98s (0:06:27)
```

Static and repository checks:

```
$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
$ PYTHONPATH=$PWD $PY scripts/check_reachability.py
exit 0; JSON report byte-identical to the same run on origin/main
("newly_unreachable": [], "lost_production_reachability": [])
$ $PY -m black --check <12 changed .py files>
12 files would be left unchanged.
$ $PY -m flake8 <changed .py files>
branch 74 diagnostics vs origin/main 78 on the same files; the branch set is a
strict subset (four E501 lines removed with the stream handler); none new.
$ $PY -m mypy --explicit-package-bases <changed .py files>
diagnostics in the changed files: branch 57 lines vs origin/main 67; the branch
set is a strict subset (ten wizard_chat.py arg-type/assignment errors removed
with the stream handler); none new.
```

`npm --prefix ui run build` is not needed: no client file changed.

## Removal Pin (Review Fix)

The pin was added in `57835814`; review fix `1415c23e` changed its request body
from `{"slot": 4, "message": "Begin"}` to `{}`. The tails below ran on the tree
of `1415c23e`.

Red run: `git archive origin/main` (`364fef4b`) into the scratch tree
`scratchpad/1081/red_main/`, with only the branch's
`tests/test_api/test_route_capabilities.py` copied in, so the stream handler
and its capability row are both present. On main the empty body fails request
validation before the handler body runs, so the test fails on its own 405
assertion and opens no database, offline or under `NEXUS_RUN_POSTGRES=1`:

```
$ PYTHONPATH=$PWD $PY -m pytest -q -p no:cacheprovider tests/test_api/test_route_capabilities.py::test_retired_wizard_stream_route_is_not_served
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_api/test_route_capabilities.py::test_retired_wizard_stream_route_is_not_served
1 failed, 7 warnings in 0.86s
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p no:cacheprovider -p tests.dbname_audit -W ignore::DeprecationWarning tests/test_api/test_route_capabilities.py::test_retired_wizard_stream_route_is_not_served
>       assert response.status_code == 405, response.text
E       AssertionError: {"detail":[{"type":"missing","loc":["body","slot"],"msg":"Field required"},{"type":"missing","loc":["body","message"],"msg":"Field required"}]}
E       assert 422 == 405
E        +  where 422 = <Response [422 Unprocessable Entity]>.status_code
tests/test_api/test_route_capabilities.py:443: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
FAILED tests/test_api/test_route_capabilities.py::test_retired_wizard_stream_route_is_not_served
1 failed in 0.76s
```

(The PostgreSQL tail is filtered to the assertion, guard and summary lines.)
`dbname audit: 0 targets` shows the red case connects to no database at all.
The earlier scratch probe that checked the route key and capability row
separately is no longer needed: the committed test itself fails on its first
assertion, and the two key assertions follow it.

Green, on the branch:

```
$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_route_capabilities.py tests/test_api/test_set_designer_failure.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
32 passed, 3 skipped, 7 warnings in 3.12s
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_route_capabilities.py tests/test_api/test_set_designer_failure.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 6 targets: postgres, qa640_840s3a_slot_* x2, qa640_840s3a_source_* x2, qa640_offline_gate_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
35 passed, 7 warnings in 15.31s
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_wizard_model_switch.py tests/test_api/test_wizard_confirmation.py tests/test_api/test_wizard_resume.py tests/test_api/test_slot_mutation_guard.py tests/test_api/test_route_capabilities.py tests/test_reachability.py tests/test_api/test_wizard_chat*.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 6 targets: postgres, qa640_offline_gate_* x4, test_slot_guard_e591467f03e4484d9853852951219789
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
236 passed, 7 warnings in 21.97s
$ $PY -m black --check tests/test_api/test_route_capabilities.py tests/test_api/test_set_designer_failure.py
1 file would be left unchanged. (each file)
$ $PY -m flake8 tests/test_api/test_route_capabilities.py tests/test_api/test_set_designer_failure.py
(no output; exit 0)
$ $PY -m mypy --explicit-package-bases tests/test_api/test_route_capabilities.py
Success: no issues found in 1 source file
$ $PY -m mypy --explicit-package-bases tests/test_api/test_set_designer_failure.py
Success: no issues found in 1 source file
```
