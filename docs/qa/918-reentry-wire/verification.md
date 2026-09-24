# STOP-REPORT: Missing Exact Replay Responses

Work order #918 cannot meet its mandatory exact-output replay gate with the
artifacts supplied in this worktree. Implementation stopped under the work
order's escape hatch. No production code or prompts were changed; no PR was
opened, no provider was called, and no gateway was started.

## Evidence Inspected

Read issue #918 with `gh issue view 918`, the repository guidance, every
`live/3A-*.json` artifact, the five corresponding session-prefixed prompt
artifacts, and the relevant gateway-log intervals. Checked the tracked artifact
inventory with `git ls-tree -r --name-only origin/main
docs/qa/909-long-absence-probe` and searched the evidence directory for all three
session IDs.

The session-prefixed JSON objects have only these top-level keys:
`run`, `seat`, `model`, `prompt`, `system_prompt`, `payload`. They capture
requests and assembly inputs. The two Gaia prompts contain finished writer
narrative, but do not supply the missing Gaia responses or the rejected writer
response. The window records contain counts, and the usage records contain
request IDs and token accounting. The failed incubator snapshots are empty.

| Failure | Missing Replay Input | Available Evidence |
| --- | --- | --- |
| Loading Arcade | Complete Gaia output for `71c52416-673f-4400-93de-4411368c9c5d` | `../909-long-absence-probe/live/3A-failed-session.json:8`; `../909-long-absence-probe/live/gateway.log:5546` |
| Reset plus crossings | Complete writer output for `1f6e283e-ca89-41ed-af93-1d7a43d668c4` | `../909-long-absence-probe/live/3A-retry-failed-session.json:8`; `../909-long-absence-probe/live/gateway.log:6473` shows only a truncated Pydantic input |
| Forewarned | Complete Gaia output for `d62347f1-cf28-468e-a44b-cd853c8d44f7` | `../909-long-absence-probe/live/3A-final-failed-session.json:8`; `../909-long-absence-probe/live/gateway.log:7408` |

Exact recorded errors:

```text
Unresolved place state update name 'Loading Arcade'
```

```text
Value error, scene_reset cannot be combined with enter or exit [type=value_error, input_value={'enter': [], 'exit': [{'...an Rook', 'id': None}]}}, input_type=dict]
```

```text
orrery_adjudications[0].replacement_state_delta.entity_tags_add: applied_tags: Tag 'forewarned' uses reapplication_policy='extend_expiry', which requires duration_override; storyteller tags_add cannot express duration_override. If the tag is already active, leave it unchanged; otherwise omit it.
```

These are historical errors from #909, not newly replayed failures. Synthesizing
payloads from their messages would not satisfy the exact recorded-output gate.
No remote response retrieval was attempted under the no-provider-call rule.

## Implementation Findings

- `nexus/agents/logon/skald_wire.py:135` explicitly rejects a reset combined
  with either crossing list.
- `nexus/api/commit_handler_sync.py:230` resolves name-addressed state updates
  by exact table name, without consulting place aliases.
- `nexus/agents/logon/orrery_tag_validation.py:616` already implements active
  extend-expiry normalization for `updates.characters`, `updates.places`, and
  `updates.factions`. The recorded failure is instead in an adjudication's
  `replacement_state_delta.entity_tags_add`. The gateway log at lines
  7406–7408 shows ordinary character-tag first applications being admitted
  immediately before that separate adjudication rejection. It does not
  establish whether the adjudication actor already had the tag active.
- `nexus/telemetry/prompt_window.py:158` defines the attempt record. It has a
  free-form `trimming` dictionary but no explicit validation-notes field on
  this branch.

## Commands Run and Results

Import provenance command, from the worktree root:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

Exact output:

```text
/Users/pythagor/nexus/.claude/worktrees/918-reentry-wire/nexus/__init__.py
```

Initial PostgreSQL staging baseline, run before discovering the missing replay
inputs:

```sh
NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api/test_acceptance_staging_pg.py -x
```

Verbatim tail:

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
18 passed, 7 warnings in 18.37s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

The tests used their existing disposable `qa640_acceptance_*` fixtures and
completed teardown. No hand-created database was used. The full offline suite,
the requested filtered PostgreSQL suite, and the exact replays were not run.
The baseline above is not a claim that the work-order gates passed. No build
was run.

## Coordinator Questions

1. Where are the complete provider response bodies for the three sessions
   listed above? Please supply the saved bodies in this worktree, or revise
   the exact-replay requirement explicitly if they were never retained.
2. Confirm that the tag ruling covers adjudication replacement deltas as well
   as ordinary `updates.*.tags_add`; the recorded failure is in the former.

Codex — GPT-6 Astra
